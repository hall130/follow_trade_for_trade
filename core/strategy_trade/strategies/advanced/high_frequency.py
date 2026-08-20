"""
高频交易策略
基于短期技术指标的高频交易策略
"""

from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta
import random

from ..base import StrategyBase
from ...base_strategy import MarketData, Signal
from utils.logger import get_logger

logger = get_logger(__name__)

class HighFrequencyStrategy(StrategyBase):
    """高频交易策略"""
    
    def __init__(self, name: str, symbol: str, config: Dict[str, Any]):
        super().__init__(name, symbol, config)
        self.tick_level = True  # 逐 tick 报价：每次行情推送都触发
        
        # 策略参数
        self.fast_ema_period = self.get_parameter('fast_ema_period', 5)
        self.slow_ema_period = self.get_parameter('slow_ema_period', 10)
        self.rsi_period = self.get_parameter('rsi_period', 14)
        self.rsi_oversold = self.get_parameter('rsi_oversold', 30.0)
        self.rsi_overbought = self.get_parameter('rsi_overbought', 70.0)
        self.volume_threshold = self.get_parameter('volume_threshold', 1.2)
        self.price_change_threshold = self.get_parameter('price_change_threshold', 0.005)
        self.min_trade_interval = self.get_parameter('min_trade_interval', 1)  # 分钟
        self.max_trades_per_day = self.get_parameter('max_trades_per_day', 50)
        
        # 交易控制
        self.last_trade_time = None
        self.trade_count = 0
        self.current_day = None
        
        logger.info(f"高频策略初始化: 快线={self.fast_ema_period}, 慢线={self.slow_ema_period}")
    
    def on_market_data(self, data: MarketData) -> None:
        """处理市场数据"""
        # 检查交易时间间隔
        if not self._check_trade_interval():
            return
        
        # 检查每日交易限制
        if not self._check_daily_trade_limit():
            return
        
        # 检查数据长度
        if len(self.price_data) < max(self.fast_ema_period, self.slow_ema_period, self.rsi_period):
            return
        
        # 生成交易信号
        self._generate_signals(data)
    
    def _check_trade_interval(self) -> bool:
        """检查交易时间间隔"""
        if self.last_trade_time is None:
            return True
        
        time_diff = (datetime.now() - self.last_trade_time).total_seconds() / 60
        return time_diff >= self.min_trade_interval
    
    def _check_daily_trade_limit(self) -> bool:
        """检查每日交易限制"""
        current_day = datetime.now().date()
        
        # 如果是新的一天，重置交易计数
        if self.current_day != current_day:
            self.trade_count = 0
            self.current_day = current_day
        
        return self.trade_count < self.max_trades_per_day
    
    def _generate_signals(self, data: MarketData) -> None:
        """生成交易信号"""
        # 获取技术指标
        fast_ema = self.get_indicator(f'ema_{self.fast_ema_period}', -1)
        slow_ema = self.get_indicator(f'ema_{self.slow_ema_period}', -1)
        rsi = self.get_indicator('rsi', -1)
        
        if not all([fast_ema, slow_ema, rsi]):
            return
        
        # 检查成交量
        if not self._check_volume():
            return
        
        # 检查价格变化
        if not self._check_price_change():
            return
        
        # 生成信号
        signal = self._analyze_signals(fast_ema, slow_ema, rsi, data)
        
        if signal:
            self._execute_signal(signal, data)
    
    def _check_volume(self) -> bool:
        """检查成交量"""
        if len(self.volume_data) < 10:
            return True
        
        current_volume = self.volume_data[-1]
        avg_volume = sum(self.volume_data[-10:]) / 10
        
        return current_volume > avg_volume * self.volume_threshold
    
    def _check_price_change(self) -> bool:
        """检查价格变化"""
        if len(self.price_data) < 2:
            return False
        
        current_price = self.price_data[-1]
        prev_price = self.price_data[-2]
        price_change = abs(current_price - prev_price) / prev_price
        
        return price_change >= self.price_change_threshold
    
    def _analyze_signals(self, fast_ema: float, slow_ema: float, rsi: float, data: MarketData) -> Optional[str]:
        """分析交易信号"""
        # EMA交叉信号
        if fast_ema > slow_ema:
            if rsi < self.rsi_oversold:
                return 'BUY'
        elif fast_ema < slow_ema:
            if rsi > self.rsi_overbought:
                return 'SELL'
        
        # RSI超买超卖信号
        if rsi < self.rsi_oversold:
            return 'BUY'
        elif rsi > self.rsi_overbought:
            return 'SELL'
        
        # 随机信号（用于测试）
        if self.get_parameter('enable_random_signals', False):
            if random.random() < 0.1:  # 10%概率
                return random.choice(['BUY', 'SELL'])
        
        return None
    
    def _execute_signal(self, signal: str, data: MarketData) -> None:
        """执行交易信号"""
        if signal == 'BUY':
            self._execute_buy_signal(data)
        elif signal == 'SELL':
            self._execute_sell_signal(data)
    
    def _execute_buy_signal(self, data: MarketData) -> None:
        """执行买入信号"""
        # 检查是否已有持仓
        if any(pos.side == 'LONG' for pos in self.positions):
            return
        
        # 创建买入信号
        volume = self.calculate_position_size(0.01)  # 1%风险
        self.create_signal(
            direction='BUY',
            strength=0.9,
            volume=volume,
            reason="高频策略买入信号"
        )
        
        self._update_trade_status()
    
    def _execute_sell_signal(self, data: MarketData) -> None:
        """执行卖出信号"""
        # 检查是否有持仓
        long_positions = [pos for pos in self.positions if pos.side == 'LONG']
        if not long_positions:
            return
        
        # 创建卖出信号
        total_volume = sum(pos.size for pos in long_positions)
        self.create_signal(
            direction='SELL',
            strength=0.9,
            volume=total_volume,
            reason="高频策略卖出信号"
        )
        
        self._update_trade_status()
    
    def _update_trade_status(self) -> None:
        """更新交易状态"""
        self.last_trade_time = datetime.now()
        self.trade_count += 1
    
    def generate_signals(self) -> List[Signal]:
        """生成交易信号"""
        return super().generate_signals()
    
    def get_strategy_status(self) -> Dict[str, Any]:
        """获取策略状态"""
        return {
            'last_trade_time': self.last_trade_time,
            'trade_count': self.trade_count,
            'current_day': self.current_day,
            'max_trades_per_day': self.max_trades_per_day,
            'min_trade_interval': self.min_trade_interval
        }
