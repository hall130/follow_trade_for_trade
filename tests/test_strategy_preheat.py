#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
策略历史预热 + K线触发粒度的 mock 单元测试。

覆盖：
- 预热：REST 历史K线升序填充 market_data/price_data，不触发策略逻辑（零信号）
- 预热去重续接：设置 _last_bar_ts
- 收盘触发：未收盘 bar(confirm=0) 跳过；已收盘去重（<=last_ts 跳过）
- tick_level 策略：每帧都喂，不去重

运行：venv/Scripts/python.exe -m pytest tests/test_strategy_preheat.py -q
或   venv/Scripts/python.exe tests/test_strategy_preheat.py
"""

import asyncio
import os
import sys
import types
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# psutil 未安装于此环境，且与被测逻辑无关：注入桩以打通导入链
if 'psutil' not in sys.modules:
    _stub = types.ModuleType('psutil')
    _stub.cpu_percent = lambda *a, **k: 0.0
    _stub.virtual_memory = lambda: types.SimpleNamespace(percent=0.0, used=0, total=0)
    _stub.Process = lambda *a, **k: types.SimpleNamespace(
        memory_info=lambda: types.SimpleNamespace(rss=0),
        cpu_percent=lambda *a, **k: 0.0)
    sys.modules['psutil'] = _stub

from core.strategy_trade.strategy_trade_service import StrategyTradeService, StrategyTradeConfig
from core.strategy_trade.base_strategy import MarketData


class _FakeStrategy:
    """最小策略桩：模拟 StrategyBase 的数据缓冲 + 触发计数。"""
    def __init__(self, timeframe='1H', tick_level=False):
        self.timeframe = timeframe
        self.tick_level = tick_level
        self.market_data = []
        self.price_data = []
        self.volume_data = []
        self.process_calls = 0        # 策略逻辑被触发次数
        self.emitted_signals = []
        self.indicators_calc = 0

    def process_market_data(self, data):
        # 模拟 StrategyBase：填充 + 触发逻辑
        self.price_data.append(data.close)
        self.volume_data.append(data.volume)
        self.market_data.append(data)
        self.process_calls += 1

    def _calculate_indicators(self):
        self.indicators_calc += 1

    def get_signals(self):
        s = list(self.emitted_signals)
        self.emitted_signals.clear()
        return s


def _svc():
    # 不触发 __init__ 的重依赖，直接构造空壳
    return StrategyTradeService.__new__(StrategyTradeService)


def _make_rows(n, start_ts=1_000_000_000_000, step=3_600_000):
    """构造 OKX 倒序历史K线：[ts, o, h, l, c, v, ...]，新→旧。"""
    rows = []
    for i in range(n):
        ts = start_ts + i * step
        px = 100 + i
        rows.append([str(ts), str(px), str(px + 1), str(px - 1), str(px + 0.5), str(10 + i)])
    rows.reverse()  # OKX 返回倒序（新在前）
    return rows


# ---------------- 预热 ----------------
def test_preheat_fills_ascending_no_signals(monkeypatch=None):
    svc = _svc()
    strat = _FakeStrategy(timeframe='1H')
    cfg = StrategyTradeConfig(strategy_id='s1', symbol='BTC-USDT-SWAP', is_demo=True)
    rows = _make_rows(50)

    class _FakeRest:
        async def get_historical_klines(self, symbol, interval, start_time, end_time, limit):
            assert interval == '1H'
            return rows

    import core.strategy_trade.strategy_trade_service as mod
    orig = mod.create_exchange_client
    mod.create_exchange_client = lambda **kw: _FakeRest()
    try:
        asyncio.run(svc._preheat_historical_data(strat, cfg, preheat_bars=300))
    finally:
        mod.create_exchange_client = orig

    # 填充了 50 根，升序（时间戳递增）
    assert len(strat.market_data) == 50
    assert len(strat.price_data) == 50
    ts = [int(m.timestamp.timestamp() * 1000) for m in strat.market_data]
    assert ts == sorted(ts), "预热数据必须升序"
    # 关键：预热绝不触发策略逻辑（零信号）
    assert strat.process_calls == 0
    # 设置了续接时间戳 = 最新一根
    assert strat._last_bar_ts == max(int(r[0]) for r in rows)
    # 预热后算了一次指标
    assert strat.indicators_calc == 1


def test_preheat_missing_timeframe_skips():
    svc = _svc()
    strat = _FakeStrategy(timeframe='')  # 无 timeframe
    cfg = StrategyTradeConfig(strategy_id='s2', symbol='BTC-USDT-SWAP', is_demo=True)
    # 不应调用 REST，也不应抛异常
    asyncio.run(svc._preheat_historical_data(strat, cfg))
    assert len(strat.market_data) == 0


def test_preheat_empty_rows_cold_start():
    svc = _svc()
    strat = _FakeStrategy(timeframe='1H')
    cfg = StrategyTradeConfig(strategy_id='s3', symbol='X-USDT-SWAP', is_demo=True)

    class _EmptyRest:
        async def get_historical_klines(self, **kw):
            return []

    import core.strategy_trade.strategy_trade_service as mod
    orig = mod.create_exchange_client
    mod.create_exchange_client = lambda **kw: _EmptyRest()
    try:
        asyncio.run(svc._preheat_historical_data(strat, cfg))
    finally:
        mod.create_exchange_client = orig
    assert len(strat.market_data) == 0


# ---------------- 触发粒度 ----------------
def _feed(svc, strat, ts, close, confirm='1'):
    data = {'arg': {'channel': 'candle1H', 'instId': 'BTC-USDT-SWAP'},
            'data': [[str(ts), '100', '101', '99', str(close), '10', '0', '0', confirm]]}
    asyncio.run(svc._handle_market_data('sid', strat, data))


def test_closed_bar_trigger_and_dedup():
    svc = _svc()
    strat = _FakeStrategy(tick_level=False)
    strat._last_bar_ts = 1000  # 模拟预热续接点

    # 未收盘 -> 跳过
    _feed(svc, strat, 2000, 105, confirm='0')
    assert strat.process_calls == 0
    # 已收盘、时间戳更新 -> 触发
    _feed(svc, strat, 2000, 106, confirm='1')
    assert strat.process_calls == 1
    # 同一根重复推送 -> 去重跳过
    _feed(svc, strat, 2000, 107, confirm='1')
    assert strat.process_calls == 1
    # 更旧的 bar(<=last) -> 跳过
    _feed(svc, strat, 1500, 108, confirm='1')
    assert strat.process_calls == 1
    # 新一根 -> 触发
    _feed(svc, strat, 5600, 109, confirm='1')
    assert strat.process_calls == 2


def test_tick_level_feeds_every_frame():
    svc = _svc()
    strat = _FakeStrategy(tick_level=True)
    # 未收盘也喂、同时间戳也喂、不去重
    _feed(svc, strat, 2000, 105, confirm='0')
    _feed(svc, strat, 2000, 106, confirm='0')
    _feed(svc, strat, 2000, 107, confirm='1')
    assert strat.process_calls == 3


def _run_all():
    fns = [v for k, v in sorted(globals().items()) if k.startswith('test_') and callable(v)]
    passed = 0
    for fn in fns:
        fn()
        print(f"  PASS {fn.__name__}")
        passed += 1
    print(f"\n{passed}/{len(fns)} tests passed")


if __name__ == '__main__':
    _run_all()
