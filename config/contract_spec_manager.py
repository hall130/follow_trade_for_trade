#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
动态合约规格管理器

启动时从交易所拉取真实合约规格（最小张数、张数精度、乘数、价格精度），
覆盖 config/contract_config.py 里的静态 OKX 表。

设计要点：
- 缓存 key 统一用 OKX 格式符号（XXX-USDT-SWAP / XXX-USD-SWAP），
  因为整个系统所有 contract_config 调用点传的都是 OKX 格式符号
  （Binance 数据已被 binance_collector.py 归一化成该格式）。
- OKX U 本位/币本位：乘数 = ctVal（张->币 或 张->USDT）。
- Binance U 本位合约：下单量就是币数量，等效乘数 = 1.0。
- 拉取失败时不清空缓存，保留静态表兜底，仅告警。

contract_config.py 的 8 个 getter 会优先查这里的缓存，未命中再落静态表。
"""
import math
from utils.logger import logger

# 动态规格缓存：okx_symbol -> {min_sz, sz_precision, multiplier, tick_sz, source}
_DYNAMIC_SPECS = {}

# Binance 特殊符号映射：Binance 原生符号 -> OKX 格式符号
# 处理 1000x 代币、USDC 报价等无法用简单切分还原的情况。
# 说明：Binance 的 1000PEPEUSDT 对应现货 PEPE 的 1000 倍计价，
# 归一化到 OKX 的 PEPE-USDT-SWAP（系统内其他地方也用 PEPE-USDT-SWAP）。
_BINANCE_SYMBOL_OVERRIDES = {
    '1000PEPEUSDT': 'PEPE-USDT-SWAP',
    '1000BONKUSDT': 'BONK-USDT-SWAP',
    '1000SHIBUSDT': 'SHIB-USDT-SWAP',
    '1000FLOKIUSDT': 'FLOKI-USDT-SWAP',
    '1000LUNCUSDT': 'LUNC-USDT-SWAP',
    '1000XECUSDT': 'XEC-USDT-SWAP',
    '1000SATSUSDT': 'SATS-USDT-SWAP',
    '1000RATSUSDT': 'RATS-USDT-SWAP',
    '1000CATUSDT': 'CAT-USDT-SWAP',
    '1000WHYUSDT': 'WHY-USDT-SWAP',
    '1000000MOGUSDT': 'MOG-USDT-SWAP',
    '1000CHEEMSUSDT': 'CHEEMS-USDT-SWAP',
    '1MBABYDOGEUSDT': 'BABYDOGE-USDT-SWAP',
}

# 已知的报价币后缀（按长度从长到短匹配，避免 USDT/USDC 切错）
_QUOTE_SUFFIXES = ['USDT', 'USDC', 'USD', 'BUSD']


def _precision_from_step(step):
    """由步长（如 0.001 / 1 / 10）推导小数精度位数。

    step >= 1 时精度为 0；step < 1 时取小数位数。
    """
    try:
        step = float(step)
    except (TypeError, ValueError):
        return 0
    if step <= 0:
        return 0
    if step >= 1:
        return 0
    # 用 round 消除浮点误差后取小数位
    d = round(-math.log10(step))
    return max(0, int(d))


def binance_symbol_to_okx(binance_symbol):
    """把 Binance 原生符号（BTCUSDT）转成 OKX 格式（BTC-USDT-SWAP）。

    找不到合理切分时返回 None（调用方跳过该符号）。
    """
    if not binance_symbol:
        return None
    sym = binance_symbol.upper()
    if sym in _BINANCE_SYMBOL_OVERRIDES:
        return _BINANCE_SYMBOL_OVERRIDES[sym]
    for quote in _QUOTE_SUFFIXES:
        if sym.endswith(quote) and len(sym) > len(quote):
            base = sym[:-len(quote)]
            # USD 结尾统一映射为 USDT-SWAP（本系统 U 本位主用 USDT）
            quote_norm = 'USDT' if quote in ('USD', 'BUSD') else quote
            return f"{base}-{quote_norm}-SWAP"
    return None


def get_spec(symbol):
    """返回该符号的动态规格 dict，未命中返回 None。"""
    return _DYNAMIC_SPECS.get(symbol)


def has_spec(symbol):
    return symbol in _DYNAMIC_SPECS


def spec_count():
    return len(_DYNAMIC_SPECS)


async def refresh_from_okx(rest_client):
    """从 OKX 拉取 SWAP（U本位+币本位）合约规格并写入缓存。

    使用 get_instruments_legacy 拿原始字段（minSz/lotSz/ctVal/tickSz），
    因为统一 dataclass 丢失了 ctVal/lotSz。
    """
    added = 0
    try:
        instruments = await rest_client.get_instruments_legacy("SWAP")
        if not instruments:
            logger.warning("[合约规格] OKX SWAP 合约列表为空，保留静态表")
            return 0
        for inst in instruments:
            inst_id = inst.get('instId')
            if not inst_id:
                continue
            try:
                min_sz = float(inst.get('minSz') or 0) or 1.0
                lot_sz = inst.get('lotSz') or inst.get('minSz')
                ct_val = float(inst.get('ctVal') or 1) or 1.0
                tick_sz = float(inst.get('tickSz') or 0) or 0.01
            except (TypeError, ValueError):
                continue
            _DYNAMIC_SPECS[inst_id] = {
                'min_sz': min_sz,
                'sz_precision': _precision_from_step(lot_sz),
                'multiplier': ct_val,
                'tick_sz': tick_sz,
                'source': 'okx',
            }
            added += 1
        logger.info(f"[合约规格] 已从 OKX 加载 {added} 个 SWAP 合约规格")
    except Exception as e:
        logger.error(f"[合约规格] 从 OKX 拉取失败，保留静态表: {e}")
    return added


def _extract_binance_filter(symbol_data, filter_type, key):
    """从 Binance exchangeInfo 的 filters 数组里按 filterType 取字段。"""
    for f in symbol_data.get('filters', []) or []:
        if f.get('filterType') == filter_type:
            return f.get(key)
    return None


async def refresh_from_binance(fapi_rest_client):
    """从 Binance USDT-M(fapi) 拉取合约规格并写入缓存（key 为 OKX 格式）。

    LOT_SIZE.stepSize -> min_sz + 精度
    PRICE_FILTER.tickSize -> tick_sz
    Binance 下单量即币数量 -> multiplier = 1.0

    使用 get_instruments_legacy() 拿原始 exchangeInfo symbols（含 filters），
    因为统一 Instrument dataclass 没有 tick_size 字段。
    """
    added = 0
    skipped = 0
    try:
        symbols = await fapi_rest_client.get_instruments_legacy()
        if not symbols:
            logger.warning("[合约规格] Binance fapi 合约列表为空")
            return 0
        for sym_data in symbols:
            # 只处理正在交易的永续合约
            if sym_data.get('status') and sym_data.get('status') != 'TRADING':
                continue
            if sym_data.get('contractType') and sym_data.get('contractType') != 'PERPETUAL':
                continue
            binance_symbol = sym_data.get('symbol')
            okx_symbol = binance_symbol_to_okx(binance_symbol)
            if not okx_symbol:
                skipped += 1
                continue
            step_size = _extract_binance_filter(sym_data, 'LOT_SIZE', 'stepSize')
            min_qty = _extract_binance_filter(sym_data, 'LOT_SIZE', 'minQty')
            tick_size = _extract_binance_filter(sym_data, 'PRICE_FILTER', 'tickSize')
            try:
                step_f = float(step_size) if step_size else 0.001
                min_f = float(min_qty) if min_qty else step_f
                tick_f = float(tick_size) if tick_size else 0.01
            except (TypeError, ValueError):
                skipped += 1
                continue
            _DYNAMIC_SPECS[okx_symbol] = {
                'min_sz': min_f or step_f or 0.001,
                'sz_precision': _precision_from_step(step_f),
                'multiplier': 1.0,
                'tick_sz': tick_f or 0.01,
                'source': 'binance',
                'binance_symbol': binance_symbol,  # 保留原始 Binance 符号，供 OKX->Binance 反查（含 1000x 覆盖）
            }
            added += 1
        logger.info(f"[合约规格] 已从 Binance fapi 加载 {added} 个合约规格"
                    f"（跳过 {skipped} 个无法映射符号）")
    except Exception as e:
        logger.error(f"[合约规格] 从 Binance fapi 拉取失败: {e}")
    return added
