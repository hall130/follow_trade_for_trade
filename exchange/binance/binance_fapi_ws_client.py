#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Binance USDT-M 永续合约(fapi) WebSocket 客户端

客户端边界隔离：对外暴露与 OKX WS 客户端一致的接口
(connect / subscribe("account"|"orders", cb, **kwargs) / place_order /
 get_positions / get_order / is_connection_healthy / close)，
内部把 Binance 用户数据流(user data stream)事件翻译成 OKX 形状的回调 payload，
喂给上层共享的 on_account / on_order 回调，使 trade_service 无需感知交易所差异。

Binance 用户数据流：
- 先用 REST 创建 listenKey，连接 wss://fstream.binance.com/ws/<listenKey>
- listenKey 需每 <60min PUT 续期一次
- 事件 ORDER_TRADE_UPDATE(o=...) -> OKX orders 频道形状
- 事件 ACCOUNT_UPDATE(a=...) -> OKX account 频道形状（USDT 钱包余额近似 totalEq）
"""

import asyncio
import json
import time
from typing import Dict, Any, Optional, Callable
from utils.logger import logger
from config.binance_config import get_binance_fapi_ws_config
from .binance_fapi_rest_client import BinanceFapiRESTClient

try:
    import websockets
except Exception:  # pragma: no cover - 运行环境应已安装
    websockets = None


class BinanceFapiWebSocketClient:
    """Binance USDT-M 合约 WS 客户端（OKX 形状对外）"""

    def __init__(self, api_key: str = "", api_secret: str = "",
                 passphrase: str = None, is_demo: bool = True):
        self.api_key = api_key or ""
        self.api_secret = api_secret or ""
        self.is_demo = is_demo
        cfg = get_binance_fapi_ws_config()
        self.ws_base = cfg.get('ws_url', 'wss://fstream.binance.com/ws')
        self.timeout = cfg.get('timeout', 30)
        # 出网代理（国内网络环境访问 Binance WS 需要）。为空则直连。
        try:
            from config.config import get_proxy_url
            self.proxy = get_proxy_url()
        except Exception:
            self.proxy = None

        # 底层 REST 客户端（下单/查仓/listenKey 复用）
        self.rest = BinanceFapiRESTClient(api_key=self.api_key,
                                          api_secret=self.api_secret,
                                          is_demo=is_demo)
        # 连接状态
        self.ws = None
        self._connected = False
        self._listen_key = None
        self._listen_task = None
        self._keepalive_task = None
        self._closed = False

        # 回调注册：channel -> callback
        self._callbacks = {}

        # 与 OKX 客户端接口对齐：认证错误计数（trade_service 会读取）
        self._consecutive_auth_errors = 0
        self._max_auth_errors = 5

    # ---------------- 连接管理 ----------------
    async def connect(self) -> bool:
        """建立用户数据流连接：创建 listenKey -> 连接 WS -> 设置双向持仓 -> 启动续期。"""
        if websockets is None:
            logger.error("[Binance-fapi-ws] 未安装 websockets 库，无法连接")
            return False
        try:
            # 确保账户为双向持仓(Hedge)模式，与 OKX long/short 对齐
            try:
                await self.rest.set_position_mode_hedge()
            except Exception as e:
                logger.warning(f"[Binance-fapi-ws] 设置双向持仓模式失败(忽略): {e}")

            self._listen_key = await self.rest.create_listen_key()
            if not self._listen_key:
                logger.error("[Binance-fapi-ws] 无法获取 listenKey，连接失败")
                self._consecutive_auth_errors += 1
                return False

            url = f"{self.ws_base}/{self._listen_key}"
            self.ws = await websockets.connect(url, proxy=self.proxy, ping_interval=180, ping_timeout=60)
            self._connected = True
            self._closed = False
            self._consecutive_auth_errors = 0

            # 启动监听与续期任务
            self._listen_task = asyncio.create_task(self._listen_loop())
            self._keepalive_task = asyncio.create_task(self._keepalive_loop())
            logger.info("[Binance-fapi-ws] 用户数据流连接成功")
            return True
        except Exception as e:
            logger.error(f"[Binance-fapi-ws] 连接失败: {e}")
            self._connected = False
            return False

    async def disconnect(self) -> bool:
        return await self._close_async()

    def close(self):
        """同步关闭（兼容 UnifiedWebSocketClient.close 调用约定）。"""
        try:
            self._closed = True
            self._connected = False
            loop = None
            try:
                loop = asyncio.get_event_loop()
            except RuntimeError:
                loop = None
            if loop and loop.is_running():
                asyncio.create_task(self._close_async())
            elif loop:
                loop.run_until_complete(self._close_async())
        except Exception as e:
            logger.error(f"[Binance-fapi-ws] 关闭失败: {e}")

    async def _close_async(self) -> bool:
        self._closed = True
        self._connected = False
        for task in (self._listen_task, self._keepalive_task):
            if task and not task.done():
                task.cancel()
        try:
            if self.ws:
                await self.ws.close()
        except Exception:
            pass
        self.ws = None
        return True

    def is_connection_healthy(self) -> bool:
        """连接健康检查（供 ConnectionManager 复用判断）。"""
        try:
            if not self._connected or self._closed or self.ws is None:
                return False
            closed = getattr(self.ws, 'closed', False)
            return not closed
        except Exception:
            return False

    def is_connected(self) -> bool:
        return self._connected

    # ---------------- 订阅 ----------------
    async def subscribe(self, channel: str, callback: Callable = None, **kwargs) -> bool:
        """注册频道回调。

        Binance 用户数据流是单条连接同时推送订单与账户事件，故 subscribe 仅登记
        回调，不发送订阅报文。支持的 channel 与 OKX 对齐："account"、"orders"。
        """
        try:
            if callback is not None:
                self._callbacks[channel] = callback
            logger.info(f"[Binance-fapi-ws] 已登记频道回调: {channel}")
            return True
        except Exception as e:
            logger.error(f"[Binance-fapi-ws] 订阅 {channel} 失败: {e}")
            return False

    async def unsubscribe(self, channel: str, **kwargs) -> bool:
        self._callbacks.pop(channel, None)
        return True

    async def _keepalive_loop(self):
        """每 ~30 分钟续期一次 listenKey（Binance 要求 <60min）。"""
        while not self._closed:
            try:
                await asyncio.sleep(30 * 60)
                if self._closed:
                    break
                ok = await self.rest.extend_listen_key()
                if not ok:
                    logger.warning("[Binance-fapi-ws] listenKey 续期失败")
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"[Binance-fapi-ws] listenKey 续期异常: {e}")

    async def _listen_loop(self):
        """接收用户数据流事件并分发翻译。"""
        try:
            async for raw in self.ws:
                if self._closed:
                    break
                try:
                    msg = json.loads(raw)
                except Exception:
                    continue
                await self._dispatch(msg)
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"[Binance-fapi-ws] 监听循环异常: {e}")
            self._connected = False

    async def _dispatch(self, msg: Dict[str, Any]):
        """按事件类型翻译成 OKX 形状并回调。"""
        event = msg.get('e')
        try:
            if event == 'ORDER_TRADE_UPDATE':
                okx_data = self._order_event_to_okx(msg)
                cb = self._callbacks.get('orders')
                if cb and okx_data:
                    await cb(okx_data)
            elif event == 'ACCOUNT_UPDATE':
                okx_data = self._account_event_to_okx(msg)
                cb = self._callbacks.get('account')
                if cb and okx_data:
                    await cb(okx_data)
            elif event == 'listenKeyExpired':
                logger.warning("[Binance-fapi-ws] listenKey 已过期，触发重连")
                self._connected = False
        except Exception as e:
            logger.error(f"[Binance-fapi-ws] 事件分发异常: {e}, msg={msg}")

    # ---------------- 事件翻译 ----------------
    def _order_event_to_okx(self, msg: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """ORDER_TRADE_UPDATE -> OKX orders 频道形状。

        Binance o 字段: i=orderId, c=clientOrderId, X=订单状态, z=累计成交量,
        l=最近成交量, ap=平均成交价, S=side(BUY/SELL), ps=positionSide(LONG/SHORT),
        s=symbol, R=reduceOnly。
        输出 data[i] 键与 _handle_customer_order_update 消费一致：
        ordId, clOrdId, state, reduceOnly('true'/'false'), fillPx, avgPx,
        accFillSz, fillSz, instId, posSide, side。
        """
        o = msg.get('o') or {}
        if not o:
            return None
        b_status = str(o.get('X', '')).upper()
        state = self.rest._binance_status_to_okx(b_status)
        b_side = str(o.get('S', '')).upper()
        okx_side = 'buy' if b_side == 'BUY' else 'sell'
        b_pos_side = str(o.get('ps', 'BOTH')).upper()
        if b_pos_side == 'LONG':
            okx_pos_side = 'long'
        elif b_pos_side == 'SHORT':
            okx_pos_side = 'short'
        else:
            okx_pos_side = 'net'
        # reduceOnly：优先用 Binance R 字段；双向持仓下 R 常为 false，
        # 此时用 (side, positionSide) 推断平仓：卖多/买空为平仓。
        r_flag = o.get('R')
        if isinstance(r_flag, bool):
            reduce_only = r_flag
        else:
            reduce_only = str(r_flag).lower() == 'true'
        if not reduce_only and okx_pos_side in ('long', 'short'):
            if (okx_pos_side == 'long' and okx_side == 'sell') or \
               (okx_pos_side == 'short' and okx_side == 'buy'):
                reduce_only = True

        avg_px = o.get('ap', '0')
        acc_fill = o.get('z', '0')
        last_fill = o.get('l', '0')
        okx_symbol = self.rest.binance_to_okx_symbol(o.get('s', ''))
        return {
            "arg": {"channel": "orders", "instType": "SWAP"},
            "data": [{
                "ordId": str(o.get('i', '')),
                "clOrdId": o.get('c', ''),
                "state": state,
                "reduceOnly": 'true' if reduce_only else 'false',
                "fillPx": str(avg_px),
                "avgPx": str(avg_px),
                "accFillSz": str(acc_fill),
                "fillSz": str(last_fill),
                "sz": str(o.get('q', acc_fill)),
                "instId": okx_symbol,
                "posSide": okx_pos_side,
                "side": okx_side,
                "fillNotionalUsd": self._safe_notional(acc_fill, avg_px),
            }],
        }

    @staticmethod
    def _safe_notional(sz, px) -> Optional[str]:
        try:
            v = float(sz) * float(px)
            return str(round(v, 3)) if v > 0 else None
        except Exception:
            return None

    def _account_event_to_okx(self, msg: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """ACCOUNT_UPDATE -> OKX account 频道形状（USDT 钱包余额近似 totalEq）。

        Binance a.B 为余额数组，元素含 a=资产, wb=钱包余额, cw=全仓钱包余额。
        取 USDT 的 wb 作为 totalEq 近似值（trade_service 只读 totalEq）。
        """
        a = msg.get('a') or {}
        balances = a.get('B') or []
        total_eq = None
        for bal in balances:
            if str(bal.get('a', '')).upper() == 'USDT':
                total_eq = bal.get('wb', bal.get('cw'))
                break
        if total_eq is None:
            return None
        return {
            "arg": {"channel": "account"},
            "data": [{"totalEq": str(total_eq)}],
        }

    # ---------------- 交易操作（委托给 REST，保持 OKX 形状） ----------------
    async def place_order(self, **kwargs):
        return await self.rest.place_order(**kwargs)

    async def get_positions(self, **kwargs):
        return await self.rest.get_positions(**kwargs)

    async def get_order(self, symbol: str, order_id: str):
        return await self.rest.get_order(symbol, order_id)

    async def cancel_order(self, symbol: str, order_id: str):
        return await self.rest.cancel_order(symbol, order_id)
