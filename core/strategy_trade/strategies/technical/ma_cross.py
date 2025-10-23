"""
移动平均线交叉策略
基于短期和长期移动平均线交叉的交易策略
"""

from typing import Dict, List, Any
from datetime import datetime

from ..base import StrategyBase
from ...core.strategy import MarketData, Signal
from utils.logger import get_logger

logger = get_logger(__name__)

class MACrossStrategy(StrategyBase):
    """移动平均线交叉策略"""
    
    def __init__(self, name: str, symbol: str, config: Dict[str, Any]):
        super().__init__(name, symbol, config)
        
        # 策略参数
        self.fast_period = self.get_parameter('fast_period', 5)
        self.slow_period = self.get_parameter('slow_period', 20)
        self.volume_threshold = self.get_parameter('volume_threshold', 1.2)
        
        logger.info(f"MA交叉策略初始化: 快线={self.fast_period}, 慢线={self.slow_period}")
    
    def on_market_data(self, data: MarketData) -> None:
        """处理市场数据"""
        # 🔧 回测模式：注释掉交易间隔检查
        # if not self.should_trade():
        #     return
        
        # 检查数据长度
        if len(self.price_data) < max(self.fast_period, self.slow_period):
            return
        
        # 获取移动平均线交叉信号
        signal = self.get_ma_cross_signal(self.fast_period, self.slow_period)
        
        if signal == 'BUY':
            self._handle_buy_signal(data)
        elif signal == 'SELL':
            self._handle_sell_signal(data)
    
    def _handle_buy_signal(self, data: MarketData) -> None:
        """处理买入信号"""
        # 🔧 回测模式：禁用持仓检查
        # if any(pos.side == 'LONG' for pos in self.positions):
        #     return
        
        # 检查成交量确认
        if not self._check_volume_confirmation():
            return
        
        # 创建买入信号
        volume = self.calculate_position_size()
        logger.info(f"✅ MA均线买入信号: MA{self.fast_period} 上穿 MA{self.slow_period}")
        self.create_signal(
            direction='BUY',
            strength=0.8,
            volume=volume,
            reason=f"MA{self.fast_period}上穿MA{self.slow_period}"
        )
    
    def _handle_sell_signal(self, data: MarketData) -> None:
        """处理卖出信号"""
        # 🔧 回测模式：禁用持仓检查
        # long_positions = [pos for pos in self.positions if pos.side == 'LONG']
        # if not long_positions:
        #     return
        
        # 创建卖出信号
        volume = self.calculate_position_size()
        logger.info(f"✅ MA均线卖出信号: MA{self.fast_period} 下穿 MA{self.slow_period}")
        self.create_signal(
            direction='SELL',
            strength=0.8,
            volume=volume,
            reason=f"MA{self.fast_period}下穿MA{self.slow_period}"
        )
    
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
