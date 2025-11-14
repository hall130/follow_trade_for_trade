"""
MACD策略
基于MACD指标金叉死叉的趋势跟踪策略
"""

from typing import Dict, List, Any
from datetime import datetime

from ..base import StrategyBase
from ...base_strategy import MarketData, Signal
from utils.logger import get_logger

logger = get_logger(__name__)

class MACDStrategy(StrategyBase):
    """MACD策略"""
    
    def __init__(self, name: str, symbol: str, config: Dict[str, Any]):
        super().__init__(name, symbol, config)
        
        # 策略参数
        self.fast_period = self.get_parameter('fast_period', 12)
        self.slow_period = self.get_parameter('slow_period', 26)
        self.signal_period = self.get_parameter('signal_period', 9)
        self.volume_threshold = self.get_parameter('volume_threshold', 1.2)
        
        logger.info(f"MACD策略初始化: 快线={self.fast_period}, 慢线={self.slow_period}, 信号线={self.signal_period}")
    
    def on_market_data(self, data: MarketData) -> None:
        """处理市场数据"""
        # 🔧 回测模式：注释掉交易间隔检查
        # if not self.should_trade():
        #     return
        
        # 检查数据长度
        if len(self.price_data) < max(self.fast_period, self.slow_period, self.signal_period):
            return
        
        # 获取MACD信号
        signal = self.get_macd_signal()
        
        if signal == 'BUY':
            self._handle_buy_signal(data)
        elif signal == 'SELL':
            self._handle_sell_signal(data)
    
    def _handle_buy_signal(self, data: MarketData) -> None:
        """处理买入信号"""
        # 🔧 回测模式：禁用持仓检查
        # if any(pos.side == 'LONG' for pos in self.positions):
        #     return
        
        # 检查MACD柱状图确认
        if not self._check_histogram_confirmation():
            return
        
        # 检查成交量确认
        if not self._check_volume_confirmation():
            return
        
        # 创建买入信号
        volume = self.calculate_position_size()
        logger.info(f"✅ MACD买入信号: 金叉")
        self.create_signal(
            direction='BUY',
            strength=0.8,
            volume=volume,
            reason="MACD金叉信号"
        )
    
    def _handle_sell_signal(self, data: MarketData) -> None:
        """处理卖出信号"""
        # 🔧 回测模式：禁用持仓检查
        # long_positions = [pos for pos in self.positions if pos.side == 'LONG']
        # if not long_positions:
        #     return
        
        # 创建卖出信号
        volume = self.calculate_position_size()
        logger.info(f"✅ MACD卖出信号: 死叉")
        self.create_signal(
            direction='SELL',
            strength=0.8,
            volume=volume,
            reason="MACD死叉信号"
        )
    
    def _check_histogram_confirmation(self) -> bool:
        """检查MACD柱状图确认"""
        histogram = self.get_indicator('macd_histogram')
        if histogram is None:
            return True
        
        # 检查柱状图是否在增长
        return histogram > 0
    
    def _check_volume_confirmation(self) -> bool:
        """检查成交量确认"""
        if len(self.volume_data) < 10:
            return True
        
        current_volume = self.volume_data[-1]
        avg_volume = sum(self.volume_data[-10:]) / 10
        
        return current_volume > avg_volume * self.volume_threshold
    
    def generate_signals(self) -> List[Signal]:
        """生成交易信号"""
        return super().generate_signals()
