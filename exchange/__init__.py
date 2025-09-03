"""
交易所模块 - 处理与各交易所的交互

包含以下功能:
- OKX交易所REST API客户端
- OKX交易所WebSocket客户端
- 币安交易所REST API客户端
- 币安交易所WebSocket客户端
- 其他交易所客户端 (可扩展)
"""

from .okx.okx_rest_client import OKXRESTClient
from .okx.okx_ws_client import OKXWebSocketClient
from .binance.binance_rest_client import BinanceRESTClient
from .binance.binance_ws_client import BinanceWebSocketClient
from .exchange_factory import ExchangeFactory, get_exchange_factory, create_exchange_client, get_exchange_client

__all__ = [
    "OKXRESTClient",
    "OKXWebSocketClient",
    "BinanceRESTClient",
    "BinanceWebSocketClient",
    "ExchangeFactory",
    "get_exchange_factory",
    "create_exchange_client",
    "get_exchange_client"
] 