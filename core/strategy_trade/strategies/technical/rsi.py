"""
RSI策略
基于相对强弱指数的超买超卖策略
"""

from typing import Dict, List, Any
from datetime import datetime

from ..base import StrategyBase
from ...core.strategy import MarketData, Signal
from utils.logger import get_logger

logger = get_logger(__name__)

class RSIStrategy(StrategyBase):
    """RSI策略"""
    
    def __init__(self, name: str, symbol: str, config: Dict[str, Any]):
        super().__init__(name, symbol, config)
        
        # 策略参数
        self.rsi_period = self.get_parameter('rsi_period', 14)
        self.oversold_threshold = self.get_parameter('oversold_threshold', 30.0)
        self.overbought_threshold = self.get_parameter('overbought_threshold', 70.0)
        self.exit_threshold = self.get_parameter('exit_threshold', 50.0)
        
        logger.info(f"RSI策略初始化: 周期={self.rsi_period}, 超卖={self.oversold_threshold}, 超买={self.overbought_threshold}")
    
    def on_market_data(self, data: MarketData) -> None:
        """处理市场数据"""
        # 检查数据长度
        if len(self.price_data) < self.rsi_period + 1:
            logger.debug(f"RSI策略: 数据长度不足 {len(self.price_data)} < {self.rsi_period + 1}")
            return
        
        # 获取RSI信号
        signal = self.get_rsi_signal(self.oversold_threshold, self.overbought_threshold)
        rsi_value = self.get_indicator('rsi')
        
        if signal == 'BUY':
            logger.info(f"RSI策略: 检测到买入信号, RSI={rsi_value:.2f} < {self.oversold_threshold}")
            self._handle_buy_signal(data)
        elif signal == 'SELL':
            logger.info(f"RSI策略: 检测到卖出信号, RSI={rsi_value:.2f} > {self.overbought_threshold}")
            self._handle_sell_signal(data)
        else:
            # 检查退出条件
            self._check_exit_conditions(data)
    
    def _handle_buy_signal(self, data: MarketData) -> None:
        """处理买入信号"""
        # 可选：检查趋势确认（可以通过配置参数禁用）
        enable_trend_confirm = self.get_parameter('enable_trend_confirm', False)  # 默认关闭
        if enable_trend_confirm:
            if not self._check_trend_confirmation():
                current_price = self.get_current_price()
                ma_20 = self.get_indicator('sma_20')
                ma_20_str = f"{ma_20:.2f}" if ma_20 else 'N/A'
                logger.info(f"趋势确认失败，跳过买入信号 (价格={current_price:.2f}, MA20={ma_20_str})")
                return
        
        # 创建买入信号
        volume = self.calculate_position_size()
        logger.info(f"创建买入信号: volume={volume}, RSI={self.get_indicator('rsi'):.2f}")
        self.create_signal(
            direction='BUY',
            strength=0.9,
            volume=volume,
            reason=f"RSI超卖信号: {self.get_indicator('rsi'):.2f}"
        )
    
    def _handle_sell_signal(self, data: MarketData) -> None:
        """处理卖出信号"""
        # 创建卖出信号（回测引擎会根据实际持仓决定是否执行）
        volume = self.calculate_position_size()
        logger.info(f"创建卖出信号: volume={volume}, RSI={self.get_indicator('rsi'):.2f}")
        self.create_signal(
            direction='SELL',
            strength=0.9,
            volume=volume,
            reason=f"RSI超买信号: {self.get_indicator('rsi'):.2f}"
        )
    
    def _check_exit_conditions(self, data: MarketData) -> None:
        """检查退出条件"""
        rsi = self.get_indicator('rsi')
        if not rsi:
            return
        
        # 如果RSI回到中性区域，考虑退出
        if self.exit_threshold - 5 <= rsi <= self.exit_threshold + 5:
            # 🔧 回测模式：不检查持仓，直接发出信号
            volume = self.calculate_position_size()
            logger.info(f"✅ 创建退出信号: volume={volume}, RSI={rsi:.2f}")
            self.create_signal(
                direction='SELL',
                strength=0.5,
                volume=volume,
                reason=f"RSI回到中性区域: {rsi:.2f}"
            )
    
    def _check_trend_confirmation(self) -> bool:
        """检查趋势确认"""
        # 检查价格是否在移动平均线之上
        return self.is_above_ma(20)
    
    def generate_signals(self) -> List[Signal]:
        """生成交易信号"""
        return super().generate_signals()
