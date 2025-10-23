"""
策略交易模块
重构后的策略交易系统，提供统一的策略开发、回测和管理功能

新架构特点：
- 统一的策略基类
- 事件驱动的回测引擎
- 模块化的策略设计
- 完整的API接口
- 高性能执行
"""

from .core import *
from .strategies import *
from .api import *

__all__ = [
    # 核心模块
    'IStrategy', 'BaseStrategy',
    'IBacktestEngine', 'BacktestEngine',
    'IStrategyManager', 'StrategyManager',
    'EventEngine', 'Event', 'MarketDataEvent', 'SignalEvent',
    # 策略模块
    'StrategyBase',
    'MACrossStrategy', 'RSIStrategy', 'MACDStrategy', 'BollingerStrategy',
    'GridStrategy', 'HighFrequencyStrategy',
    # API模块
    'StrategyTradeAPI'
]