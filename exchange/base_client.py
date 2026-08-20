#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
交易所客户端抽象基类
定义统一的交易所接口规范
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List, Union
from enum import Enum
from dataclasses import dataclass
from utils.logger import logger
from .websocket_state_machine import WebSocketStateMachine, WebSocketStatus


class ExchangeType(Enum):
    """交易所类型枚举"""
    OKX = "okx"
    BINANCE = "binance"
    BYBIT = "bybit"
    GATE = "gate"
    HYPERLIQUID = "hyperliquid"


class OrderSide(Enum):
    """订单方向枚举"""
    BUY = "buy"
    SELL = "sell"


class OrderType(Enum):
    """订单类型枚举"""
    MARKET = "market"
    LIMIT = "limit"
    STOP = "stop"
    STOP_LIMIT = "stop_limit"


class OrderStatus(Enum):
    """订单状态枚举"""
    PENDING = "pending"
    FILLED = "filled"
    CANCELLED = "cancelled"
    REJECTED = "rejected"
    PARTIALLY_FILLED = "partially_filled"


@dataclass
class OrderRequest:
    """订单请求数据类"""
    symbol: str
    side: OrderSide
    order_type: OrderType
    quantity: float
    price: Optional[float] = None
    stop_price: Optional[float] = None
    time_in_force: str = "GTC"
    client_order_id: Optional[str] = None
    reduce_only: bool = False
    # OKX 特定参数
    td_mode: Optional[str] = None  # 交易模式 (cross, isolated)
    pos_side: Optional[str] = None  # 持仓方向 (long, short, net)
    lever: Optional[str] = None    # 杠杆倍数


@dataclass
class OrderResponse:
    """订单响应数据类"""
    order_id: str
    client_order_id: Optional[str]
    symbol: str
    side: OrderSide
    order_type: OrderType
    quantity: float
    price: Optional[float]
    status: OrderStatus
    filled_quantity: float = 0.0
    remaining_quantity: float = 0.0
    timestamp: int = 0
    exchange: ExchangeType = None


@dataclass
class Position:
    """持仓数据类"""
    symbol: str
    side: str  # long/short
    size: float
    entry_price: float
    mark_price: float
    unrealized_pnl: float
    margin: float
    leverage: float
    exchange: ExchangeType = None


@dataclass
class Balance:
    """余额数据类"""
    asset: str
    free: float
    locked: float
    total: float
    exchange: ExchangeType = None


@dataclass
class Ticker:
    """行情数据类"""
    symbol: str
    price: float
    volume: float
    timestamp: int
    exchange: ExchangeType
    bid_price: float = 0.0
    ask_price: float = 0.0
    high_24h: float = 0.0
    low_24h: float = 0.0
    change_24h: float = 0.0
    change_percent_24h: float = 0.0


@dataclass
class FundingRate:
    """资金费率数据类"""
    symbol: str
    funding_rate: float
    funding_time: int
    next_funding_time: int
    exchange: ExchangeType


@dataclass
class OpenInterest:
    """持仓量数据类"""
    symbol: str
    open_interest: float
    timestamp: int
    exchange: ExchangeType


@dataclass
class MarkPrice:
    """标记价格数据类"""
    symbol: str
    mark_price: float
    index_price: float
    timestamp: int
    exchange: ExchangeType


@dataclass
class LiquidationOrder:
    """强平订单数据类"""
    symbol: str
    side: OrderSide
    size: float
    price: float
    timestamp: int
    exchange: ExchangeType


@dataclass
class TradeFee:
    """交易手续费数据类"""
    symbol: str
    maker_fee: float
    taker_fee: float
    category: str
    exchange: ExchangeType


@dataclass
class MarginBalance:
    """保证金余额数据类"""
    asset: str
    total: float
    available: float
    frozen: float
    borrowed: float
    interest: float
    exchange: ExchangeType


@dataclass
class Instrument:
    """交易产品数据类"""
    symbol: str
    base_asset: str
    quote_asset: str
    min_qty: float
    max_qty: float
    step_size: float
    min_notional: float
    status: str
    exchange: ExchangeType


@dataclass
class BillDetail:
    """账单详情数据类"""
    bill_id: str
    asset: str
    amount: float
    fee: float
    bill_type: str
    timestamp: int
    exchange: ExchangeType = None


class BaseRESTClient(ABC):
    """REST客户端抽象基类"""
    
    def __init__(self, api_key: str, api_secret: str, passphrase: str = None, is_demo: bool = True):
        self.api_key = api_key
        self.api_secret = api_secret
        self.passphrase = passphrase
        self.is_demo = is_demo
        self.exchange_type = self._get_exchange_type()
        # 出网代理（国内网络环境访问交易所需要）。为空则直连。
        self.proxy = self._resolve_proxy()

    @staticmethod
    def _resolve_proxy() -> Optional[str]:
        """解析代理地址，失败时安全退化为直连（返回 None）。"""
        try:
            from config.config import get_proxy_url
            return get_proxy_url()
        except Exception:
            return None

    @abstractmethod
    def _get_exchange_type(self) -> ExchangeType:
        """获取交易所类型"""
        pass
    
    @abstractmethod
    async def place_order(self, order_request: OrderRequest) -> OrderResponse:
        """下单"""
        pass
    
    @abstractmethod
    async def cancel_order(self, symbol: str, order_id: str) -> bool:
        """取消订单"""
        pass
    
    @abstractmethod
    async def get_order(self, symbol: str, order_id: str) -> Optional[OrderResponse]:
        """获取订单信息"""
        pass
    
    @abstractmethod
    async def get_open_orders(self, symbol: Optional[str] = None) -> List[OrderResponse]:
        """获取未成交订单"""
        pass
    
    @abstractmethod
    async def get_positions(self, symbol: Optional[str] = None) -> List[Position]:
        """获取持仓信息"""
        pass
    
    @abstractmethod
    async def get_balance(self) -> List[Balance]:
        """获取账户余额"""
        pass
    
    @abstractmethod
    async def get_ticker(self, symbol: str) -> Ticker:
        """获取行情信息"""
        pass
    
    @abstractmethod
    async def get_klines(self, symbol: str, interval: str, 
                        start_time: Optional[int] = None, 
                        end_time: Optional[int] = None,
                        limit: int = 500) -> List[List]:
        """获取K线数据"""
        pass
    
    @abstractmethod
    async def get_funding_rate(self, symbol: str) -> FundingRate:
        """获取资金费率"""
        pass
    
    @abstractmethod
    async def get_open_interest(self, symbol: str) -> OpenInterest:
        """获取持仓量"""
        pass
    
    @abstractmethod
    async def get_mark_price(self, symbol: str) -> MarkPrice:
        """获取标记价格"""
        pass
    
    @abstractmethod
    async def get_liquidation_orders(self, symbol: Optional[str] = None, 
                                   limit: int = 100) -> List[LiquidationOrder]:
        """获取强平订单"""
        pass
    
    @abstractmethod
    async def get_trade_fee(self, symbol: str, category: str = "spot") -> TradeFee:
        """获取交易手续费"""
        pass
    
    @abstractmethod
    async def get_margin_balance(self, asset: Optional[str] = None) -> List[MarginBalance]:
        """获取保证金余额"""
        pass
    
    @abstractmethod
    async def get_instruments(self, inst_type: str = "SPOT") -> List[Instrument]:
        """获取交易产品基础信息"""
        pass
    
    @abstractmethod
    async def get_bill_details(self, asset: Optional[str] = None, 
                             limit: int = 100) -> List[BillDetail]:
        """获取账单详情"""
        pass


class BaseWebSocketClient(ABC):
    """WebSocket客户端抽象基类"""
    
    def __init__(self, api_key: str = None, api_secret: str = None, 
                 passphrase: str = None, is_demo: bool = True):
        self.api_key = api_key
        self.api_secret = api_secret
        self.passphrase = passphrase
        self.is_demo = is_demo
        self.exchange_type = self._get_exchange_type()
        self._subscriptions = {}
        self._callbacks = {}
        # 出网代理（国内网络环境访问交易所 WS 需要）。为空则直连。
        self.proxy = BaseRESTClient._resolve_proxy()

        # 初始化状态机
        self._state_machine = WebSocketStateMachine(self.exchange_type.value)
        self._setup_state_callbacks()
    
    def _setup_state_callbacks(self):
        """设置状态变化回调"""
        self._state_machine.add_status_change_callback(self._on_status_change)
    
    def _on_status_change(self, old_status: WebSocketStatus, new_status: WebSocketStatus, reason: str):
        """状态变化回调"""
        logger.info(f"[{self.exchange_type.value}] WebSocket状态变化: {old_status.value} -> {new_status.value} ({reason})")
    
    @property
    def status(self) -> WebSocketStatus:
        """获取当前状态"""
        return self._state_machine.current_status
    
    @property
    def is_connected(self) -> bool:
        """检查是否已连接"""
        return self._state_machine.is_connected()
    
    @property
    def is_ready(self) -> bool:
        """检查是否就绪"""
        return self._state_machine.is_ready()
    
    @property
    def is_stable(self) -> bool:
        """检查是否稳定"""
        return self._state_machine.is_stable()
    
    def get_status_info(self) -> Dict[str, Any]:
        """获取状态信息"""
        return self._state_machine.get_status_info()
    
    async def _transition_to(self, status: WebSocketStatus, reason: str = "") -> bool:
        """转换状态"""
        return await self._state_machine.transition_to(status, reason)
    
    @abstractmethod
    def _get_exchange_type(self) -> ExchangeType:
        """获取交易所类型"""
        pass
    
    @abstractmethod
    async def connect(self) -> bool:
        """建立WebSocket连接"""
        pass
    
    @abstractmethod
    async def disconnect(self) -> bool:
        """断开WebSocket连接"""
        pass
    
    @abstractmethod
    async def subscribe_ticker(self, symbol: str, callback) -> bool:
        """订阅行情数据"""
        pass
    
    @abstractmethod
    async def subscribe_orderbook(self, symbol: str, callback) -> bool:
        """订阅深度数据"""
        pass
    
    @abstractmethod
    async def subscribe_trades(self, symbol: str, callback) -> bool:
        """订阅交易数据"""
        pass
    
    @abstractmethod
    async def subscribe_orders(self, callback) -> bool:
        """订阅订单更新"""
        pass
    
    @abstractmethod
    async def subscribe_positions(self, callback) -> bool:
        """订阅持仓更新"""
        pass
    
    @abstractmethod
    async def subscribe_balance(self, callback) -> bool:
        """订阅余额更新"""
        pass
    
    @abstractmethod
    async def unsubscribe(self, channel: str) -> bool:
        """取消订阅"""
        pass
    
    @abstractmethod
    def is_connected(self) -> bool:
        """检查连接状态"""
        pass


class ExchangeClientFactory:
    """交易所客户端工厂类"""
    
    _rest_clients = {}
    _ws_clients = {}
    
    @classmethod
    def create_rest_client(cls, exchange: ExchangeType, api_key: str, 
                          api_secret: str, passphrase: str = None, 
                          is_demo: bool = True) -> BaseRESTClient:
        """创建REST客户端"""
        client_key = f"{exchange.value}_{api_key}"
        
        if client_key in cls._rest_clients:
            return cls._rest_clients[client_key]
        
        if exchange == ExchangeType.OKX:
            from .okx.okx_rest_client import OKXRESTClient
            client = OKXRESTClient(api_key, api_secret, passphrase, is_demo)
        elif exchange == ExchangeType.BINANCE:
            from .binance.binance_rest_client import BinanceRESTClient
            client = BinanceRESTClient(api_key, api_secret, is_demo)
        else:
            raise ValueError(f"不支持的交易所: {exchange}")
        
        cls._rest_clients[client_key] = client
        return client
    
    @classmethod
    def create_ws_client(cls, exchange: ExchangeType, api_key: str = None,
                        api_secret: str = None, passphrase: str = None,
                        is_demo: bool = True) -> BaseWebSocketClient:
        """创建WebSocket客户端"""
        client_key = f"{exchange.value}_{api_key or 'public'}"
        
        if client_key in cls._ws_clients:
            return cls._ws_clients[client_key]
        
        if exchange == ExchangeType.OKX:
            from .okx.okx_ws_client import OKXWebSocketClient
            client = OKXWebSocketClient(api_key, api_secret, passphrase, is_demo)
        elif exchange == ExchangeType.BINANCE:
            from .binance.binance_ws_client import BinanceWebSocketClient
            client = BinanceWebSocketClient(api_key, api_secret, is_demo)
        else:
            raise ValueError(f"不支持的交易所: {exchange}")
        
        cls._ws_clients[client_key] = client
        return client
    
    @classmethod
    def get_rest_client(cls, exchange: ExchangeType, api_key: str) -> Optional[BaseRESTClient]:
        """获取已创建的REST客户端"""
        client_key = f"{exchange.value}_{api_key}"
        return cls._rest_clients.get(client_key)
    
    @classmethod
    def get_ws_client(cls, exchange: ExchangeType, api_key: str = None) -> Optional[BaseWebSocketClient]:
        """获取已创建的WebSocket客户端"""
        client_key = f"{exchange.value}_{api_key or 'public'}"
        return cls._ws_clients.get(client_key)
    
    @classmethod
    def close_all_clients(cls):
        """关闭所有客户端"""
        # 关闭REST客户端
        for client in cls._rest_clients.values():
            if hasattr(client, 'close'):
                try:
                    client.close()
                except Exception as e:
                    logger.error(f"关闭REST客户端失败: {e}")
        
        # 关闭WebSocket客户端
        for client in cls._ws_clients.values():
            if hasattr(client, 'close'):
                try:
                    import asyncio
                    if asyncio.iscoroutinefunction(client.close):
                        asyncio.create_task(client.close())
                    else:
                        client.close()
                except Exception as e:
                    logger.error(f"关闭WebSocket客户端失败: {e}")
        
        cls._rest_clients.clear()
        cls._ws_clients.clear()
        logger.info("所有交易所客户端已关闭")


# 便捷函数
def create_exchange_client(exchange: str, client_type: str = 'rest', 
                          api_key: str = None, api_secret: str = None,
                          passphrase: str = None, is_demo: bool = True):
    """
    创建交易所客户端的便捷函数
    
    Args:
        exchange: 交易所名称 ('okx', 'binance', 'bybit')
        client_type: 客户端类型 ('rest' 或 'ws')
        api_key: API密钥
        api_secret: API密钥
        passphrase: 密码短语（仅OKX需要）
        is_demo: 是否使用演示模式
    
    Returns:
        交易所客户端实例
    """
    try:
        exchange_type = ExchangeType(exchange.lower())
    except ValueError:
        raise ValueError(f"不支持的交易所: {exchange}")
    
    if client_type.lower() == 'rest':
        return ExchangeClientFactory.create_rest_client(
            exchange_type, api_key, api_secret, passphrase, is_demo
        )
    elif client_type.lower() == 'ws':
        return ExchangeClientFactory.create_ws_client(
            exchange_type, api_key, api_secret, passphrase, is_demo
        )
    else:
        raise ValueError(f"不支持的客户端类型: {client_type}")


def get_exchange_client(exchange: str, client_type: str = 'rest', api_key: str = None):
    """
    获取已创建的交易所客户端的便捷函数
    
    Args:
        exchange: 交易所名称
        client_type: 客户端类型 ('rest' 或 'ws')
        api_key: API密钥
    
    Returns:
        交易所客户端实例或None
    """
    try:
        exchange_type = ExchangeType(exchange.lower())
    except ValueError:
        raise ValueError(f"不支持的交易所: {exchange}")
    
    if client_type.lower() == 'rest':
        return ExchangeClientFactory.get_rest_client(exchange_type, api_key)
    elif client_type.lower() == 'ws':
        return ExchangeClientFactory.get_ws_client(exchange_type, api_key)
    else:
        raise ValueError(f"不支持的客户端类型: {client_type}")
