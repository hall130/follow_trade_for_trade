"""
策略交易核心模块
提供统一的策略交易接口和核心功能
"""

from .strategy import IStrategy, BaseStrategy
from .backtest import IBacktestEngine, BacktestEngine
from .manager import IStrategyManager, StrategyManager
from .events import EventEngine, Event, MarketDataEvent, SignalEvent

__all__ = [
    'IStrategy', 'BaseStrategy',
    'IBacktestEngine', 'BacktestEngine', 
    'IStrategyManager', 'StrategyManager',
    'EventEngine', 'Event', 'MarketDataEvent', 'SignalEvent'
]
