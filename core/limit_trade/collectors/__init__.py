"""
带单员数据采集器模块
提供统一的接口来采集不同交易所/平台的带单员交易记录和热门带单员
"""

from .base_collector import BaseTraderCollector
from .okx_collector import OKXTraderCollector
from .binance_collector import BinanceTraderCollector
from .hyperliquid_trader_collector import HyperliquidTraderCollector
from .collector_factory import TraderCollectorFactory
from .okx_popular_collector import OKXPopularTraderCollector
from .binance_popular_collector import BinancePopularTraderCollector

__all__ = [
    'BaseTraderCollector',
    'OKXTraderCollector',
    'BinanceTraderCollector',
    'HyperliquidTraderCollector',
    'TraderCollectorFactory',
    'OKXPopularTraderCollector',
    'BinancePopularTraderCollector'
]

