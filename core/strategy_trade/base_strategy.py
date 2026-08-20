"""
统一策略基类
所有策略（包括用户自定义策略）必须继承此类
提供标准化的策略接口和通用功能
"""

from abc import ABC, abstractmethod
from typing import Dict, List, Any, Optional
from datetime import datetime
from dataclasses import dataclass
import pandas as pd

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
        return {
            'symbol': self.symbol,
            'timestamp': self.timestamp.isoformat(),
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
    price: float
    volume: float
    timestamp: datetime
    strength: float = 1.0  # 信号强度 0-1
    reason: str = ""  # 信号原因
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'symbol': self.symbol,
            'direction': self.direction,
            'price': self.price,
            'volume': self.volume,
            'timestamp': self.timestamp.isoformat(),
            'strength': self.strength,
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
        self.current_price = price
        if self.side == 'LONG':
            self.unrealized_pnl = (price - self.entry_price) * self.size
        else:
            self.unrealized_pnl = (self.entry_price - price) * self.size


class BaseStrategy(ABC):
    """
    统一策略基类
    
    所有策略必须继承此类并实现以下方法：
    - on_market_data: 处理市场数据
    - get_signals: 获取交易信号
    
    可选实现的方法：
    - on_initialize: 策略初始化
    - on_start: 策略启动
    - on_stop: 策略停止
    """
    
    def __init__(self, name: str, symbol: str, config: Dict[str, Any]):
        """
        初始化策略
        
        Args:
            name: 策略名称
            symbol: 交易对（如 BTC-USDT）
            config: 策略配置字典
        """
        self.name = name
        self.symbol = symbol
        self.config = config
        
        # 策略状态
        self.initialized = False
        self.running = False

        # 触发粒度：默认按 K 线收盘触发（技术指标类策略的正确语义）。
        # 逐 tick 报价类策略（高频/做市/网格）应在子类中置为 True，
        # 以在每次行情推送（含未收盘 bar）时都被调用。
        self.tick_level = False

        # 数据缓存（限制大小防止内存溢出）
        self.market_data: List[MarketData] = []
        self.max_data_cache = 1000  # 最大缓存数据量
        
        # 信号缓存
        self.pending_signals: List[Signal] = []
        
        # 持仓管理
        self.positions: List[Position] = []
        
        # 性能统计
        self.total_trades = 0
        self.winning_trades = 0
        self.total_pnl = 0.0
        
        logger.info(f"策略初始化: {name} (symbol: {symbol})")
    
    def initialize(self) -> None:
        """策略初始化（由引擎调用）"""
        if self.initialized:
            return
        
        self.initialized = True
        self.on_initialize()
        logger.info(f"策略 {self.name} 初始化完成")
    
    def start(self) -> None:
        """启动策略"""
        if not self.initialized:
            self.initialize()
        
        self.running = True
        self.on_start()
        logger.info(f"策略 {self.name} 已启动")
    
    def stop(self) -> None:
        """停止策略"""
        self.running = False
        self.on_stop()
        logger.info(f"策略 {self.name} 已停止")
    
    def process_market_data(self, data: MarketData) -> None:
        """
        处理市场数据（由引擎调用）
        
        Args:
            data: 市场数据
        """
        if not self.running:
            return
        
        # 更新数据缓存
        self.market_data.append(data)
        if len(self.market_data) > self.max_data_cache:
            self.market_data = self.market_data[-self.max_data_cache // 2:]
        
        # 调用策略逻辑
        self.on_market_data(data)
    
    def get_signals(self) -> List[Signal]:
        """
        获取交易信号（由引擎调用）
        
        Returns:
            交易信号列表
        """
        signals = self.pending_signals.copy()
        self.pending_signals.clear()
        return signals
    
    def get_positions(self) -> List[Position]:
        """获取持仓信息"""
        return self.positions.copy()
    
    def get_performance(self) -> Dict[str, Any]:
        """获取策略性能"""
        win_rate = self.winning_trades / self.total_trades if self.total_trades > 0 else 0
        
        return {
            'name': self.name,
            'symbol': self.symbol,
            'running': self.running,
            'total_trades': self.total_trades,
            'winning_trades': self.winning_trades,
            'win_rate': win_rate,
            'total_pnl': self.total_pnl,
            'positions_count': len(self.positions),
            'data_points': len(self.market_data)
        }
    
    # ========== 必须实现的方法 ==========
    
    @abstractmethod
    def on_market_data(self, data: MarketData) -> None:
        """
        处理市场数据（必须实现）
        
        在此方法中实现策略逻辑，生成交易信号
        
        Args:
            data: 市场数据
        """
        pass
    
    # ========== 可选实现的方法 ==========
    
    def on_initialize(self) -> None:
        """策略初始化（可选实现）"""
        pass
    
    def on_start(self) -> None:
        """策略启动（可选实现）"""
        pass
    
    def on_stop(self) -> None:
        """策略停止（可选实现）"""
        pass
    
    # ========== 辅助方法 ==========
    
    def get_parameter(self, key: str, default: Any = None) -> Any:
        """获取配置参数"""
        return self.config.get(key, default)
    
    def set_parameter(self, key: str, value: Any) -> None:
        """设置配置参数"""
        self.config[key] = value
        logger.debug(f"设置参数 {key} = {value}")
    
    def create_signal(self, direction: str, price: float, volume: float, 
                     strength: float = 1.0, reason: str = "") -> Signal:
        """
        创建交易信号
        
        Args:
            direction: 方向 ('BUY', 'SELL', 'HOLD')
            price: 价格
            volume: 数量
            strength: 信号强度 (0-1)
            reason: 信号原因
            
        Returns:
            信号对象
        """
        signal = Signal(
            symbol=self.symbol,
            direction=direction,
            price=price,
            volume=volume,
            timestamp=datetime.now(),
            strength=strength,
            reason=reason
        )
        
        self.pending_signals.append(signal)
        logger.debug(f"生成信号: {direction} {self.symbol} @ {price:.4f} x {volume:.4f} - {reason}")
        
        return signal
    
    def add_position(self, position: Position) -> None:
        """添加持仓"""
        self.positions.append(position)
        logger.info(f"添加持仓: {position.symbol} {position.side} {position.size}")
    
    def remove_position(self, symbol: str, side: str) -> Optional[Position]:
        """移除持仓"""
        for i, pos in enumerate(self.positions):
            if pos.symbol == symbol and pos.side == side:
                return self.positions.pop(i)
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
    
    def get_price_data(self, length: Optional[int] = None) -> List[float]:
        """获取价格数据"""
        prices = [data.close for data in self.market_data]
        if length:
            return prices[-length:]
        return prices
    
    def get_current_price(self) -> Optional[float]:
        """获取当前价格"""
        if self.market_data:
            return self.market_data[-1].close
        return None
    
    def get_historical_data(self, length: int = 100) -> pd.DataFrame:
        """获取历史数据DataFrame"""
        if not self.market_data or len(self.market_data) < length:
            length = len(self.market_data)
        
        data = self.market_data[-length:]
        return pd.DataFrame({
            'timestamp': [d.timestamp for d in data],
            'open': [d.open for d in data],
            'high': [d.high for d in data],
            'low': [d.low for d in data],
            'close': [d.close for d in data],
            'volume': [d.volume for d in data]
        })

