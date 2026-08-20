#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Binance USDT-M 永续合约(fapi) REST 客户端

设计目标：客户端边界隔离。对外暴露与 OKX 客户端一致的方法签名与返回结构，
内部完成 OKX<->Binance 的符号转换、参数映射、以及 OKX 形状的响应伪造，
使上层 trade_service 无需感知这是 Binance。

关键差异处理：
- 符号：OKX `BTC-USDT-SWAP` <-> Binance `BTCUSDT`（复用 contract_spec_manager 的映射）。
- 张数：OKX 用「张」× ctVal；Binance USDT-M 的 quantity 直接是币数量（乘数=1）。
  因此本客户端对外的 quantity 即币数量，pos 也是币数量，multiplier 由动态规格给出 1.0。
- 持仓方向：OKX posSide=long/short；Binance 双向持仓(Hedge) positionSide=LONG/SHORT。
- 下单方向：OKX side=buy/sell + posSide；Binance side=BUY/SELL + positionSide。
"""

import aiohttp
import hmac
import hashlib
import time
import json
from typing import Dict, Any, Optional, List
from utils.logger import logger
from config.binance_config import get_binance_fapi_config
from config import contract_spec_manager


class BinanceFapiRESTClient:
    """Binance USDT-M 合约 REST 客户端（OKX 形状对外）"""

    def __init__(self, api_key: str = "", api_secret: str = "",
                 passphrase: str = None, is_demo: bool = True):
        # passphrase 仅为与 OKX 客户端签名一致而保留，Binance 不使用
        self.api_key = api_key or ""
        self.api_secret = api_secret or ""
        self.is_demo = is_demo
        cfg = get_binance_fapi_config()
        # 允许 is_demo 覆盖配置默认
        if is_demo:
            self.base_url = "https://testnet.binancefuture.com"
        else:
            self.base_url = "https://fapi.binance.com"
        self.timeout = cfg.get('timeout', 30)
        self.exchange_type = 'binance'
        # 出网代理（国内网络环境访问 Binance 需要）。为空则直连。
        try:
            from config.config import get_proxy_url
            self.proxy = get_proxy_url()
        except Exception:
            self.proxy = None

    # ---------------- 符号转换 ----------------
    @staticmethod
    def okx_to_binance_symbol(okx_symbol: str) -> str:
        """OKX 符号 -> Binance fapi 符号。BTC-USDT-SWAP -> BTCUSDT。

        依赖 contract_spec_manager 已建立的反向映射；无缓存时回退到规则拼接。
        """
        if not okx_symbol:
            return okx_symbol
        # 优先查动态规格里记录的 binance_symbol
        spec = contract_spec_manager.get_spec(okx_symbol)
        if spec and spec.get('binance_symbol'):
            return spec['binance_symbol']
        # 规则回退：XXX-USDT-SWAP -> XXXUSDT；XXX-USDC-SWAP -> XXXUSDC
        parts = okx_symbol.split('-')
        if len(parts) == 3 and parts[2] == 'SWAP':
            base, quote = parts[0], parts[1]
            # USD 本位（反向）在 Binance USDT-M 不存在，按 USDT 处理
            if quote == 'USD':
                quote = 'USDT'
            return f"{base}{quote}"
        return okx_symbol.replace('-', '')

    @staticmethod
    def binance_to_okx_symbol(binance_symbol: str) -> str:
        """Binance fapi 符号 -> OKX 符号。复用 contract_spec_manager 的转换。"""
        return contract_spec_manager.binance_symbol_to_okx(binance_symbol)

    # ---------------- 签名与请求 ----------------
    def _sign(self, query_string: str) -> str:
        return hmac.new(self.api_secret.encode('utf-8'),
                        query_string.encode('utf-8'),
                        hashlib.sha256).hexdigest()

    def _headers(self) -> Dict[str, str]:
        return {'X-MBX-APIKEY': self.api_key}

    async def _request(self, method: str, endpoint: str,
                       params: Optional[Dict] = None, signed: bool = False) -> Any:
        """发送 fapi 请求。signed=True 时附加时间戳并签名。

        返回原始 JSON（dict 或 list）；网络异常时返回 {'_error': ...}。
        """
        params = dict(params or {})
        url = f"{self.base_url}{endpoint}"
        if signed:
            params['timestamp'] = int(time.time() * 1000)
            params.setdefault('recvWindow', 5000)
            query = '&'.join(f"{k}={v}" for k, v in params.items())
            params['signature'] = self._sign(query)
        headers = self._headers()
        try:
            timeout = aiohttp.ClientTimeout(total=self.timeout)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                if method == 'GET':
                    async with session.get(url, headers=headers, params=params, proxy=self.proxy) as resp:
                        return await resp.json()
                elif method == 'POST':
                    async with session.post(url, headers=headers, params=params, proxy=self.proxy) as resp:
                        return await resp.json()
                elif method == 'PUT':
                    async with session.put(url, headers=headers, params=params, proxy=self.proxy) as resp:
                        return await resp.json()
                elif method == 'DELETE':
                    async with session.delete(url, headers=headers, params=params, proxy=self.proxy) as resp:
                        return await resp.json()
                else:
                    raise ValueError(f"不支持的HTTP方法: {method}")
        except Exception as e:
            logger.error(f"[Binance-fapi] 请求失败 {method} {endpoint}: {e}")
            return {'_error': str(e)}
    # ---------------- 下单 ----------------
    async def place_order(self, symbol: str, side: str, order_type: str,
                          quantity: float, price: Optional[float] = None,
                          client_order_id: Optional[str] = None, **kwargs) -> Dict[str, Any]:
        """下单。对外签名/返回与 OKX WS 客户端一致（OKX 形状 dict）。

        入参 symbol 为 OKX 格式；side=buy/sell；posSide=long/short（kwargs）；
        reduceOnly=true/false（kwargs，字符串）。内部转 Binance fapi 下单。
        """
        try:
            b_symbol = self.okx_to_binance_symbol(symbol)
            b_side = 'BUY' if str(side).lower() == 'buy' else 'SELL'
            pos_side = str(kwargs.get('posSide', '')).lower()
            b_pos_side = 'LONG' if pos_side == 'long' else ('SHORT' if pos_side == 'short' else 'BOTH')
            b_type = 'MARKET' if str(order_type).lower() == 'market' else 'LIMIT'

            params = {
                'symbol': b_symbol,
                'side': b_side,
                'type': b_type,
                'quantity': self._fmt_qty(symbol, quantity),
                'positionSide': b_pos_side,
            }
            if client_order_id:
                params['newClientOrderId'] = client_order_id[:36]
            if b_type == 'LIMIT':
                params['timeInForce'] = kwargs.get('time_in_force', 'GTC')
                if price is not None:
                    params['price'] = price
            # 双向持仓模式下 Binance 不接受 reduceOnly（由 positionSide 决定），
            # 单向模式才需要；这里按双向模式处理，忽略 reduceOnly 参数。

            resp = await self._request('POST', '/fapi/v1/order', params, signed=True)
            return self._to_okx_order_ack(resp, client_order_id)
        except Exception as e:
            logger.error(f"[Binance-fapi] 下单异常: {e}")
            return {"code": "1", "data": [{"sCode": "1", "sMsg": f"下单失败: {str(e)}"}]}

    def _fmt_qty(self, okx_symbol: str, quantity: float):
        """按合约数量精度格式化 quantity（避免科学计数法/多余小数）。"""
        try:
            from config.contract_config import get_contract_sz_precision
            prec = get_contract_sz_precision(okx_symbol)
            q = round(float(quantity), int(prec)) if prec and prec > 0 else round(float(quantity))
            if prec and prec > 0:
                return f"{q:.{int(prec)}f}"
            return str(int(q))
        except Exception:
            return str(quantity)

    def _to_okx_order_ack(self, resp: Any, client_order_id: Optional[str]) -> Dict[str, Any]:
        """把 Binance 下单响应转为 OKX 下单回执形状。

        OKX 成功: {"code":"0","data":[{"ordId","clOrdId","sCode":"0","sMsg":"success"}]}
        trade_service 还会读取 top-level res.get('sCode')（用于 51016 判定）。
        """
        if isinstance(resp, dict) and resp.get('orderId'):
            ord_id = str(resp.get('orderId'))
            cl_id = resp.get('clientOrderId') or client_order_id or ''
            return {
                "code": "0",
                "sCode": "0",
                "data": [{
                    "ordId": ord_id,
                    "clOrdId": cl_id,
                    "sCode": "0",
                    "sMsg": "success",
                }],
            }
        # 失败：Binance 返回 {"code":-2010,"msg":"..."} 或 {"_error":...}
        b_code = resp.get('code') if isinstance(resp, dict) else None
        b_msg = resp.get('msg') if isinstance(resp, dict) else str(resp)
        if isinstance(resp, dict) and resp.get('_error'):
            b_msg = resp['_error']
        return {
            "code": "1",
            "sCode": str(b_code) if b_code is not None else "1",
            "data": [{
                "sCode": str(b_code) if b_code is not None else "1",
                "sMsg": b_msg or "下单失败",
            }],
        }
    # ---------------- 撤单/查单 ----------------
    async def cancel_order(self, symbol: str, order_id: str) -> bool:
        """撤单（统一接口，返回 bool，与 OKX 客户端一致）。"""
        try:
            b_symbol = self.okx_to_binance_symbol(symbol)
            params = {'symbol': b_symbol, 'orderId': order_id}
            resp = await self._request('DELETE', '/fapi/v1/order', params, signed=True)
            return isinstance(resp, dict) and str(resp.get('orderId', '')) != '' and not resp.get('_error')
        except Exception as e:
            logger.error(f"[Binance-fapi] 撤单异常: {e}")
            return False

    async def get_order(self, symbol: str, order_id: str) -> Optional[Dict[str, Any]]:
        """查单。返回 OKX 形状精简 dict（与 okx_ws_client.get_order 对齐）。"""
        try:
            b_symbol = self.okx_to_binance_symbol(symbol)
            params = {'symbol': b_symbol, 'orderId': order_id}
            resp = await self._request('GET', '/fapi/v1/order', params, signed=True)
            if isinstance(resp, dict) and resp.get('orderId'):
                return {
                    "ordId": str(resp.get('orderId')),
                    "clOrdId": resp.get('clientOrderId', ''),
                    "state": self._binance_status_to_okx(resp.get('status', '')),
                    "code": "0",
                    "msg": "success",
                }
            return None
        except Exception as e:
            logger.error(f"[Binance-fapi] 查单异常: {e}")
            return None

    @staticmethod
    def _binance_status_to_okx(status: str) -> str:
        """Binance 订单状态 -> OKX 状态。"""
        m = {
            'NEW': 'live',
            'PARTIALLY_FILLED': 'partially_filled',
            'FILLED': 'filled',
            'CANCELED': 'canceled',
            'EXPIRED': 'canceled',
            'REJECTED': 'canceled',
        }
        return m.get(str(status).upper(), 'live')

    # ---------------- 持仓 ----------------
    async def get_positions(self, symbol: Optional[str] = None, **kwargs) -> Dict[str, Any]:
        """获取持仓。返回 OKX 形状：{"success":True,"code":"0","positions":[...]}。

        每个 position 含 instId(OKX符号)、posSide(long/short)、pos(币数量)。
        Binance /fapi/v2/positionRisk 返回 positionAmt（带符号，双向持仓下按
        positionSide 区分 LONG/SHORT，均为正数量或 0）。
        """
        try:
            params = {}
            if symbol:
                params['symbol'] = self.okx_to_binance_symbol(symbol)
            resp = await self._request('GET', '/fapi/v2/positionRisk', params, signed=True)
            if isinstance(resp, dict) and resp.get('_error'):
                return {"success": False, "code": "1", "error": resp['_error'], "positions": []}
            if not isinstance(resp, list):
                # 可能是错误 dict {"code":-xxxx,"msg":...}
                return {"success": False, "code": str(resp.get('code', '1')) if isinstance(resp, dict) else "1",
                        "error": resp.get('msg') if isinstance(resp, dict) else str(resp), "positions": []}
            positions = []
            for p in resp:
                amt = float(p.get('positionAmt', 0) or 0)
                if amt == 0:
                    continue
                okx_symbol = self.binance_to_okx_symbol(p.get('symbol', ''))
                b_pos_side = str(p.get('positionSide', 'BOTH')).upper()
                if b_pos_side == 'LONG':
                    okx_pos_side = 'long'
                elif b_pos_side == 'SHORT':
                    okx_pos_side = 'short'
                else:
                    # 单向持仓：按数量符号推断
                    okx_pos_side = 'long' if amt > 0 else 'short'
                positions.append({
                    "instId": okx_symbol,
                    "posSide": okx_pos_side,
                    "pos": str(abs(amt)),
                    "avgPx": p.get('entryPrice', '0'),
                    "markPx": p.get('markPrice', '0'),
                    "upl": p.get('unRealizedProfit', '0'),
                    "lever": p.get('leverage', '1'),
                })
            return {"success": True, "code": "0", "positions": positions}
        except Exception as e:
            logger.error(f"[Binance-fapi] 获取持仓异常: {e}")
            return {"success": False, "code": "1", "error": str(e), "positions": []}
    # ---------------- 合约信息（供动态规格刷新） ----------------
    async def get_instruments_legacy(self, inst_type: str = "SWAP") -> List[Dict]:
        """获取 fapi exchangeInfo 的原始 symbols 数组（公共接口，无需签名）。

        contract_spec_manager.refresh_from_binance 消费此结构：读取每个 symbol 的
        contractType/status/filters(LOT_SIZE/PRICE_FILTER)。
        """
        try:
            resp = await self._request('GET', '/fapi/v1/exchangeInfo', signed=False)
            if isinstance(resp, dict) and isinstance(resp.get('symbols'), list):
                return resp['symbols']
            logger.error(f"[Binance-fapi] exchangeInfo 结构异常: {resp}")
            return []
        except Exception as e:
            logger.error(f"[Binance-fapi] 获取合约信息异常: {e}")
            return []

    # ---------------- ListenKey（用户数据流，供 WS 客户端使用） ----------------
    async def create_listen_key(self) -> Optional[str]:
        """创建用户数据流 listenKey（fapi 需 API-Key 头，无需签名）。"""
        try:
            resp = await self._request('POST', '/fapi/v1/listenKey', signed=False)
            if isinstance(resp, dict) and resp.get('listenKey'):
                return resp['listenKey']
            logger.error(f"[Binance-fapi] 创建 listenKey 失败: {resp}")
            return None
        except Exception as e:
            logger.error(f"[Binance-fapi] 创建 listenKey 异常: {e}")
            return None

    async def extend_listen_key(self) -> bool:
        """延长 listenKey 有效期（每 <60min 调用一次）。"""
        try:
            resp = await self._request('PUT', '/fapi/v1/listenKey', signed=False)
            return isinstance(resp, dict) and not resp.get('_error')
        except Exception as e:
            logger.error(f"[Binance-fapi] 延长 listenKey 异常: {e}")
            return False

    async def set_position_mode_hedge(self) -> bool:
        """设置账户为双向持仓(Hedge)模式，与 OKX long/short 对齐。

        已是该模式时 Binance 返回 code=-4059，视为成功。
        """
        try:
            params = {'dualSidePosition': 'true'}
            resp = await self._request('POST', '/fapi/v1/positionSide/dual', params, signed=True)
            if isinstance(resp, dict):
                if resp.get('code') in (200, '200') or resp.get('msg') == 'success':
                    return True
                if str(resp.get('code')) == '-4059':  # No need to change position side
                    return True
            return False
        except Exception as e:
            logger.error(f"[Binance-fapi] 设置双向持仓模式异常: {e}")
            return False

    async def close(self):
        """兼容接口：无长连接资源，空实现。"""
        return True
