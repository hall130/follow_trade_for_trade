"""
布林带策略
基于布林带突破和回归的均值回归策略
"""

from typing import Dict, List, Any
from datetime import datetime

from ..base import StrategyBase
from ...core.strategy import MarketData, Signal
from utils.logger import get_logger

logger = get_logger(__name__)

class BollingerStrategy(StrategyBase):
    """布林带策略"""
    
    def __init__(self, name: str, symbol: str, config: Dict[str, Any]):
        super().__init__(name, symbol, config)
        
        # 策略参数
        self.bb_period = self.get_parameter('bb_period', 20)
        self.bb_std = self.get_parameter('bb_std', 2.0)
        self.volume_threshold = self.get_parameter('volume_threshold', 1.2)
        self.exit_threshold = self.get_parameter('exit_threshold', 0.5)
        
        logger.info(f"布林带策略初始化: 周期={self.bb_period}, 标准差={self.bb_std}")
    
    def on_market_data(self, data: MarketData) -> None:
        """处理市场数据"""
        # 🔧 回测模式：注释掉交易间隔检查
        # if not self.should_trade():
        #     return
        
        # 检查数据长度
        if len(self.price_data) < self.bb_period:
            return
        
        # 获取布林带信号
        signal = self.get_bollinger_signal()
        
        if signal == 'BUY':
            self._handle_buy_signal(data)
        elif signal == 'SELL':
            self._handle_sell_signal(data)
        else:
            # 检查退出条件
            self._check_exit_conditions(data)
    
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
        logger.info(f"✅ 布林带买入信号: 价格触及下轨")
        self.create_signal(
            direction='BUY',
            strength=0.8,
            volume=volume,
            reason="价格触及布林带下轨"
        )
    
    def _handle_sell_signal(self, data: MarketData) -> None:
        """处理卖出信号"""
        # 🔧 回测模式：禁用持仓检查
        # long_positions = [pos for pos in self.positions if pos.side == 'LONG']
        # if not long_positions:
        #     return
        
        # 创建卖出信号
        volume = self.calculate_position_size()
        logger.info(f"✅ 布林带卖出信号: 价格触及上轨")
        self.create_signal(
            direction='SELL',
            strength=0.8,
            volume=volume,
            reason="价格触及布林带上轨"
        )
    
    def _check_exit_conditions(self, data: MarketData) -> None:
        """检查退出条件"""
        current_price = self.get_current_price()
        bb_upper = self.get_indicator('bb_upper')
        bb_lower = self.get_indicator('bb_lower')
        bb_middle = self.get_indicator('bb_middle')
        
        if not all([current_price, bb_upper, bb_lower, bb_middle]):
            return
        
        # 计算价格在布林带中的位置
        bb_position = (current_price - bb_lower) / (bb_upper - bb_lower)
        
        # 如果价格回到布林带中部区域，考虑退出
        if 0.4 <= bb_position <= 0.6:
            long_positions = [pos for pos in self.positions if pos.side == 'LONG']
            if long_positions:
                total_volume = sum(pos.size for pos in long_positions)
                self.create_signal(
                    direction='SELL',
                    strength=0.5,
                    volume=total_volume,
                    reason=f"价格回到布林带中部: {bb_position:.2f}"
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
