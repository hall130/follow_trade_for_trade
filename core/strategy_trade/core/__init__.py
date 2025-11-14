"""
策略交易核心模块
提供统一的策略交易接口和核心功能
"""

from ..base_strategy import BaseStrategy, MarketData, Signal, Position
from .backtest import IBacktestEngine, BacktestEngine
from .manager import IStrategyManager, StrategyManager
from .events import EventEngine, Event, MarketDataEvent, SignalEvent

# IStrategy 接口已统一到 BaseStrategy（向后兼容）
IStrategy = BaseStrategy

__all__ = [
    'IStrategy', 'BaseStrategy', 'MarketData', 'Signal', 'Position',
    'IBacktestEngine', 'BacktestEngine', 
    'IStrategyManager', 'StrategyManager',
    'EventEngine', 'Event', 'MarketDataEvent', 'SignalEvent'
]
