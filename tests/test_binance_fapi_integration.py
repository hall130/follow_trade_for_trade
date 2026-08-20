#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Binance USDT-M(fapi) 接入 + 动态合约规格 + 对账缩短 的 mock 单元测试。

不连真实交易所（无 testnet），全部用 mock 覆盖：
- 动态合约规格：符号映射 / 精度推导 / OKX & Binance 刷新
- fapi REST：符号转换 / 下单回执 OKX 形状 / 持仓翻译 / 状态映射
- fapi WS：ORDER_TRADE_UPDATE & ACCOUNT_UPDATE -> OKX 形状 / 分发路由
- 路由：Binance 客户端接口与 OKX 客户端对齐

运行：venv/Scripts/python.exe -m pytest tests/test_binance_fapi_integration.py -q
或   venv/Scripts/python.exe tests/test_binance_fapi_integration.py
"""

import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import contract_spec_manager as csm
from exchange.binance.binance_fapi_rest_client import BinanceFapiRESTClient
from exchange.binance.binance_fapi_ws_client import BinanceFapiWebSocketClient


# ---------------- 动态合约规格 ----------------
def test_symbol_mapping_and_precision():
    assert csm.binance_symbol_to_okx('BTCUSDT') == 'BTC-USDT-SWAP'
    assert csm.binance_symbol_to_okx('1000PEPEUSDT') == 'PEPE-USDT-SWAP'
    assert csm.binance_symbol_to_okx('ETHUSDC') == 'ETH-USDC-SWAP'
    assert csm.binance_symbol_to_okx('') is None
    assert csm._precision_from_step(0.001) == 3
    assert csm._precision_from_step(1) == 0
    assert csm._precision_from_step('0.00001') == 5


class _FakeFapiInstruments:
    async def get_instruments_legacy(self, inst_type='SWAP'):
        return [
            {'symbol': 'BTCUSDT', 'status': 'TRADING', 'contractType': 'PERPETUAL',
             'filters': [{'filterType': 'LOT_SIZE', 'stepSize': '0.001', 'minQty': '0.001'},
                         {'filterType': 'PRICE_FILTER', 'tickSize': '0.10'}]},
            {'symbol': '1000PEPEUSDT', 'status': 'TRADING', 'contractType': 'PERPETUAL',
             'filters': [{'filterType': 'LOT_SIZE', 'stepSize': '1', 'minQty': '1'},
                         {'filterType': 'PRICE_FILTER', 'tickSize': '0.0000001'}]},
            {'symbol': 'ETHUSDT', 'status': 'BREAK', 'contractType': 'PERPETUAL', 'filters': []},
        ]


def test_refresh_from_binance():
    n = asyncio.run(csm.refresh_from_binance(_FakeFapiInstruments()))
    assert n == 2
    s = csm.get_spec('BTC-USDT-SWAP')
    assert s['multiplier'] == 1.0 and s['sz_precision'] == 3 and s['min_sz'] == 0.001
    assert s['binance_symbol'] == 'BTCUSDT'
    pep = csm.get_spec('PEPE-USDT-SWAP')
    assert pep['binance_symbol'] == '1000PEPEUSDT'


# ---------------- fapi REST ----------------
def test_rest_symbol_translation():
    c = BinanceFapiRESTClient(is_demo=True)
    assert c.okx_to_binance_symbol('BTC-USDT-SWAP') == 'BTCUSDT'
    assert c.okx_to_binance_symbol('BTC-USD-SWAP') == 'BTCUSDT'  # inverse folded
    assert c.binance_to_okx_symbol('BTCUSDT') == 'BTC-USDT-SWAP'
    # 1000x override reverse lookup (relies on spec loaded above)
    asyncio.run(csm.refresh_from_binance(_FakeFapiInstruments()))
    assert c.okx_to_binance_symbol('PEPE-USDT-SWAP') == '1000PEPEUSDT'


def test_rest_order_ack_shape():
    c = BinanceFapiRESTClient(is_demo=True)
    ok = c._to_okx_order_ack({'orderId': 123, 'clientOrderId': 'abc'}, 'abc')
    assert ok['code'] == '0' and ok['sCode'] == '0' and ok['data'][0]['ordId'] == '123'
    bad = c._to_okx_order_ack({'code': -2010, 'msg': 'insufficient'}, 'abc')
    assert bad['code'] == '1' and bad['data'][0]['sMsg'] == 'insufficient'
    err = c._to_okx_order_ack({'_error': 'timeout'}, 'x')
    assert err['code'] == '1' and err['data'][0]['sMsg'] == 'timeout'


def test_rest_status_map():
    c = BinanceFapiRESTClient(is_demo=True)
    assert c._binance_status_to_okx('FILLED') == 'filled'
    assert c._binance_status_to_okx('NEW') == 'live'
    assert c._binance_status_to_okx('CANCELED') == 'canceled'
    assert c._binance_status_to_okx('PARTIALLY_FILLED') == 'partially_filled'


def test_rest_get_positions_translation():
    c = BinanceFapiRESTClient(is_demo=True)

    async def fake_req(method, endpoint, params=None, signed=False):
        return [
            {'symbol': 'BTCUSDT', 'positionAmt': '0.5', 'positionSide': 'LONG',
             'entryPrice': '60000', 'markPrice': '61000', 'unRealizedProfit': '500', 'leverage': '10'},
            {'symbol': 'ETHUSDT', 'positionAmt': '0', 'positionSide': 'SHORT'},
            {'symbol': 'XRPUSDT', 'positionAmt': '100', 'positionSide': 'SHORT',
             'entryPrice': '0.5', 'markPrice': '0.4'},
        ]

    c._request = fake_req
    res = asyncio.run(c.get_positions())
    assert res['success'] and res['code'] == '0'
    ps = res['positions']
    assert len(ps) == 2  # zero filtered
    assert ps[0]['instId'] == 'BTC-USDT-SWAP' and ps[0]['posSide'] == 'long' and ps[0]['pos'] == '0.5'
    assert ps[1]['instId'] == 'XRP-USDT-SWAP' and ps[1]['posSide'] == 'short' and ps[1]['pos'] == '100.0'


def test_rest_get_positions_error():
    c = BinanceFapiRESTClient(is_demo=True)

    async def err_req(method, endpoint, params=None, signed=False):
        return {'code': -2015, 'msg': 'invalid key'}

    c._request = err_req
    res = asyncio.run(c.get_positions())
    assert not res['success'] and res['positions'] == []


def test_rest_place_order_maps_params():
    c = BinanceFapiRESTClient(is_demo=True)
    captured = {}

    async def ord_req(method, endpoint, params=None, signed=False):
        captured.update(params)
        return {'orderId': 999, 'clientOrderId': params.get('newClientOrderId')}

    c._request = ord_req
    ack = asyncio.run(c.place_order('BTC-USDT-SWAP', 'buy', 'market', 0.5,
                                    client_order_id='cid1', posSide='long',
                                    reduceOnly='false', tag='x'))
    assert ack['code'] == '0' and ack['data'][0]['ordId'] == '999'
    assert captured['symbol'] == 'BTCUSDT' and captured['side'] == 'BUY'
    assert captured['positionSide'] == 'LONG' and captured['type'] == 'MARKET'


# ---------------- fapi WS 事件翻译 ----------------
def test_ws_order_event_open_long():
    w = BinanceFapiWebSocketClient(is_demo=True)
    ev = {'e': 'ORDER_TRADE_UPDATE', 'o': {'i': 111, 'c': 'cid1', 'X': 'FILLED', 'z': '0.5',
          'l': '0.5', 'ap': '60000', 'S': 'BUY', 'ps': 'LONG', 's': 'BTCUSDT', 'q': '0.5', 'R': False}}
    d = w._order_event_to_okx(ev)['data'][0]
    assert d['ordId'] == '111' and d['state'] == 'filled' and d['reduceOnly'] == 'false'
    assert d['instId'] == 'BTC-USDT-SWAP' and d['posSide'] == 'long' and d['side'] == 'buy'
    assert d['accFillSz'] == '0.5' and d['avgPx'] == '60000' and d['fillNotionalUsd'] == '30000.0'


def test_ws_order_event_infer_close():
    w = BinanceFapiWebSocketClient(is_demo=True)
    # 卖多 -> 推断平仓
    ev = {'e': 'ORDER_TRADE_UPDATE', 'o': {'i': 112, 'X': 'FILLED', 'z': '0.5', 'ap': '61000',
          'S': 'SELL', 'ps': 'LONG', 's': 'BTCUSDT', 'R': False}}
    assert w._order_event_to_okx(ev)['data'][0]['reduceOnly'] == 'true'
    # 买空 -> 推断平仓
    ev2 = {'e': 'ORDER_TRADE_UPDATE', 'o': {'i': 113, 'X': 'FILLED', 'z': '100', 'ap': '0.4',
           'S': 'BUY', 'ps': 'SHORT', 's': 'XRPUSDT', 'R': False}}
    assert w._order_event_to_okx(ev2)['data'][0]['reduceOnly'] == 'true'
    # 显式 R=True 尊重
    ev3 = {'e': 'ORDER_TRADE_UPDATE', 'o': {'i': 114, 'X': 'FILLED', 'z': '1', 'ap': '10',
           'S': 'SELL', 'ps': 'SHORT', 's': 'DOGEUSDT', 'R': True}}
    assert w._order_event_to_okx(ev3)['data'][0]['reduceOnly'] == 'true'


def test_ws_account_event():
    w = BinanceFapiWebSocketClient(is_demo=True)
    ac = {'e': 'ACCOUNT_UPDATE', 'a': {'B': [{'a': 'USDT', 'wb': '12345.6', 'cw': '12345.6'},
          {'a': 'BNB', 'wb': '1'}]}}
    assert w._account_event_to_okx(ac)['data'][0]['totalEq'] == '12345.6'


def test_ws_dispatch_routing():
    async def run():
        w = BinanceFapiWebSocketClient(is_demo=True)
        got = {}

        async def on_order(d):
            got['order'] = d

        async def on_account(d):
            got['account'] = d

        await w.subscribe('orders', on_order, instType='SWAP')
        await w.subscribe('account', on_account)
        await w._dispatch({'e': 'ORDER_TRADE_UPDATE', 'o': {'i': 1, 'X': 'FILLED', 'z': '1',
                          'ap': '2', 'S': 'BUY', 'ps': 'LONG', 's': 'BTCUSDT', 'R': False}})
        await w._dispatch({'e': 'ACCOUNT_UPDATE', 'a': {'B': [{'a': 'USDT', 'wb': '99'}]}})
        await w._dispatch({'e': 'SOMETHING', 'x': 1})  # ignored
        assert got['order']['data'][0]['ordId'] == '1'
        assert got['account']['data'][0]['totalEq'] == '99'

    asyncio.run(run())


def test_ws_interface_parity_with_okx():
    w = BinanceFapiWebSocketClient(is_demo=True)
    for attr in ('connect', 'subscribe', 'place_order', 'get_positions', 'get_order',
                 'cancel_order', 'is_connection_healthy', 'close',
                 '_consecutive_auth_errors', '_max_auth_errors', '_connected'):
        assert hasattr(w, attr), f"missing {attr}"
    assert w.is_connection_healthy() is False


# ---------------- 对账配置 ----------------
def test_reconcile_config():
    from config import get_reconcile_config
    cfg = get_reconcile_config()
    assert cfg['interval_seconds'] == 300  # 从 1800 缩短
    assert cfg['on_fill'] is True
    assert 'on_fill_throttle' in cfg and 'on_fill_delay' in cfg


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
