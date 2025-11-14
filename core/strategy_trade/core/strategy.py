"""
策略基类定义（已完全弃用 - 不再使用）

⚠️ 警告：此模块已完全弃用，所有代码已迁移到新架构
新的策略必须使用 base_strategy.BaseStrategy

此文件保留仅作为参考，不应再被任何代码引用。
所有功能已迁移到：
- base_strategy.BaseStrategy - 统一策略基类
- core/backtest.py - 已更新为新架构
- core/manager.py - 已更新为新架构

如需使用策略接口，请：
- from core.strategy_trade.base_strategy import BaseStrategy, MarketData, Signal
"""

from abc import ABC, abstractmethod
from typing import Dict, List, Any, Optional, Union
from datetime import datetime
from dataclasses import dataclass
import pandas as pd
import numpy as np

from utils.logger import get_logger

logger = get_logger(__name__)

@dataclass
class MarketData:
    """市场数据"""
    symbol: str
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            'symbol': self.symbol,
            'timestamp': self.timestamp,
            'open': self.open,
            'high': self.high,
            'low': self.low,
            'close': self.close,
            'volume': self.volume
        }

@dataclass
class Signal:
    """交易信号"""
    symbol: str
    direction: str  # 'BUY', 'SELL', 'HOLD'
    strength: float  # 信号强度 0-1
    price: float
    volume: float
    timestamp: datetime
    reason: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            'symbol': self.symbol,
            'direction': self.direction,
            'strength': self.strength,
            'price': self.price,
            'volume': self.volume,
            'timestamp': self.timestamp,
            'reason': self.reason
        }

@dataclass
class Position:
    """持仓信息"""
    symbol: str
    side: str  # 'LONG', 'SHORT'
    size: float
    entry_price: float
    entry_time: datetime
    current_price: float = 0.0
    unrealized_pnl: float = 0.0
    
    def update_price(self, price: float):
        """更新价格"""
        self.current_price = price
        if self.side == 'LONG':
            self.unrealized_pnl = (price - self.entry_price) * self.size
        else:  # SHORT
            self.unrealized_pnl = (self.entry_price - price) * self.size

class IStrategy(ABC):
    """策略接口"""
    
    @abstractmethod
    def initialize(self) -> None:
        """策略初始化"""
        pass
    
    @abstractmethod
    def on_market_data(self, data: MarketData) -> None:
        """处理市场数据"""
        pass
    
    @abstractmethod
    def get_signals(self) -> List[Signal]:
        """获取交易信号"""
        pass
    
    @abstractmethod
    def get_positions(self) -> List[Position]:
        """获取持仓信息"""
        pass
    
    @abstractmethod
    def get_performance(self) -> Dict[str, Any]:
        """获取策略性能"""
        pass

class BaseStrategy(IStrategy):
    """策略基类"""
    
    def __init__(self, name: str, symbol: str, config: Dict[str, Any]):
        self.name = name
        self.symbol = symbol
        self.config = config
        
        # 策略状态
        self.initialized = False
        self.running = False
        
        # 数据缓存
        self.market_data: List[MarketData] = []
        self.signals: List[Signal] = []
        self.positions: List[Position] = []
        
        # 性能统计
        self.total_trades = 0
        self.winning_trades = 0
        self.total_pnl = 0.0
        
        logger.info(f"策略初始化: {name}")
    
    def initialize(self) -> None:
        """策略初始化"""
        self.initialized = True
        self.on_initialize()
        logger.info(f"策略 {self.name} 初始化完成")
    
    def start(self) -> None:
        """启动策略"""
        if not self.initialized:
            self.initialize()
        self.running = True
        self.on_start()
        logger.info(f"策略 {self.name} 启动")
    
    def stop(self) -> None:
        """停止策略"""
        self.running = False
        self.on_stop()
        logger.info(f"策略 {self.name} 停止")
    
    def on_market_data(self, data: MarketData) -> None:
        """处理市场数据"""
        if not self.running:
            return
            
        # 更新数据缓存
        self.market_data.append(data)
        if len(self.market_data) > 1000:
            self.market_data = self.market_data[-500:]
        
        # 调用策略逻辑
        self.on_data(data)
        
        # 生成信号
        signals = self.generate_signals()
        self.signals.extend(signals)
    
    def get_signals(self) -> List[Signal]:
        """获取交易信号"""
        return self.signals.copy()
    
    def get_positions(self) -> List[Position]:
        """获取持仓信息"""
        return self.positions.copy()
    
    def get_performance(self) -> Dict[str, Any]:
        """获取策略性能"""
        win_rate = self.winning_trades / self.total_trades if self.total_trades > 0 else 0
        
        return {
            'total_trades': self.total_trades,
            'winning_trades': self.winning_trades,
            'win_rate': win_rate,
            'total_pnl': self.total_pnl,
            'positions': len(self.positions)
        }
    
    # 子类需要实现的方法
    def on_initialize(self) -> None:
        """策略初始化（子类实现）"""
        pass
    
    def on_start(self) -> None:
        """策略启动（子类实现）"""
        pass
    
    def on_stop(self) -> None:
        """策略停止（子类实现）"""
        pass
    
    def on_data(self, data: MarketData) -> None:
        """处理数据（子类实现）"""
        pass
    
    @abstractmethod
    def generate_signals(self) -> List[Signal]:
        """生成交易信号（子类必须实现）"""
        pass
    
    # 辅助方法
    def add_position(self, position: Position) -> None:
        """添加持仓"""
        self.positions.append(position)
        logger.info(f"添加持仓: {position.symbol} {position.side} {position.size}")
    
    def remove_position(self, symbol: str, side: str) -> Optional[Position]:
        """移除持仓"""
        for i, pos in enumerate(self.positions):
            if pos.symbol == symbol and pos.side == side:
                position = self.positions.pop(i)
                logger.info(f"移除持仓: {position.symbol} {position.side}")
                return position
        return None
    
    def update_positions(self, current_price: float) -> None:
        """更新持仓价格"""
        for position in self.positions:
            position.update_price(current_price)
    
    def record_trade(self, pnl: float) -> None:
        """记录交易"""
        self.total_trades += 1
        self.total_pnl += pnl
        if pnl > 0:
            self.winning_trades += 1
    
    def get_parameter(self, key: str, default: Any = None) -> Any:
        """获取策略参数"""
        return self.config.get(key, default)
    
    def set_parameter(self, key: str, value: Any) -> None:
        """设置策略参数"""
        self.config[key] = value
        logger.info(f"设置参数 {key} = {value}")
