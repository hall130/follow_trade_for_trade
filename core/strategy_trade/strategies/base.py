"""
策略基类
提供策略开发的基础功能
"""

from typing import Dict, List, Any, Optional
from datetime import datetime
import pandas as pd
import numpy as np

from ..core.strategy import BaseStrategy, MarketData, Signal, Position
from ..utils.indicators import TechnicalIndicators
from utils.logger import get_logger

logger = get_logger(__name__)

class StrategyBase(BaseStrategy):
    """策略基类"""
    
    def __init__(self, name: str, symbol: str, config: Dict[str, Any]):
        super().__init__(name, symbol, config)
        
        # 技术指标缓存
        self.price_data: List[float] = []
        self.volume_data: List[float] = []
        self.indicators: Dict[str, List[float]] = {}
        
        # 信号缓存
        self.pending_signals: List[Signal] = []
        
        # 交易记录
        self.trades: List[Dict[str, Any]] = []
        
        logger.info(f"策略基类初始化: {name}")
    
    def on_data(self, data: MarketData) -> None:
        """处理市场数据"""
        # 更新数据缓存
        self.price_data.append(data.close)
        self.volume_data.append(data.volume)
        
        # 限制缓存大小
        if len(self.price_data) > 1000:
            self.price_data = self.price_data[-500:]
            self.volume_data = self.volume_data[-500:]
        
        # 计算技术指标
        self._calculate_indicators()
        
        # 调用策略逻辑
        self.on_market_data(data)
    
    def generate_signals(self) -> List[Signal]:
        """生成交易信号"""
        signals = self.pending_signals.copy()
        if signals:
            logger.info(f"🎯 策略产生 {len(signals)} 个信号: {[s.direction for s in signals]}")
        self.pending_signals.clear()
        return signals
    
    def get_signals(self) -> List[Signal]:
        """
        获取交易信号（回测引擎使用）
        
        重写父类方法，从 pending_signals 而不是 signals 获取信号
        """
        signals = self.pending_signals.copy()
        self.pending_signals.clear()
        return signals
    
    def _calculate_indicators(self) -> None:
        """计算技术指标"""
        if len(self.price_data) < 20:
            return
        
        price_series = pd.Series(self.price_data)
        volume_series = pd.Series(self.volume_data)
        
        # 移动平均线
        self.indicators['sma_5'] = TechnicalIndicators.sma(price_series, 5).tolist()
        self.indicators['sma_10'] = TechnicalIndicators.sma(price_series, 10).tolist()
        self.indicators['sma_20'] = TechnicalIndicators.sma(price_series, 20).tolist()
        
        # EMA
        self.indicators['ema_5'] = TechnicalIndicators.ema(price_series, 5).tolist()
        self.indicators['ema_10'] = TechnicalIndicators.ema(price_series, 10).tolist()
        self.indicators['ema_20'] = TechnicalIndicators.ema(price_series, 20).tolist()
        
        # RSI
        self.indicators['rsi'] = TechnicalIndicators.rsi(price_series, 14).tolist()
        
        # MACD
        macd_line, signal_line, histogram = TechnicalIndicators.macd(price_series)
        self.indicators['macd'] = macd_line.tolist()
        self.indicators['macd_signal'] = signal_line.tolist()
        self.indicators['macd_histogram'] = histogram.tolist()
        
        # 布林带
        upper, middle, lower = TechnicalIndicators.bollinger_bands(price_series, 20, 2)
        self.indicators['bb_upper'] = upper.tolist()
        self.indicators['bb_middle'] = middle.tolist()
        self.indicators['bb_lower'] = lower.tolist()
        
        # 成交量指标
        self.indicators['volume_sma'] = TechnicalIndicators.sma(volume_series, 10).tolist()
    
    def get_indicator(self, name: str, index: int = -1) -> Optional[float]:
        """获取技术指标值"""
        if name not in self.indicators or not self.indicators[name]:
            return None
        
        values = self.indicators[name]
        if abs(index) > len(values):
            return None
        
        return values[index]
    
    def get_current_price(self) -> Optional[float]:
        """获取当前价格"""
        return self.price_data[-1] if self.price_data else None
    
    def get_current_volume(self) -> Optional[float]:
        """获取当前成交量"""
        return self.volume_data[-1] if self.volume_data else None
    
    def create_signal(self, direction: str, strength: float = 1.0, volume: float = 1.0, reason: str = "") -> Signal:
        """创建交易信号"""
        current_price = self.get_current_price()
        if not current_price:
            return None
        
        signal = Signal(
            symbol=self.symbol,
            direction=direction,
            strength=strength,
            price=current_price,
            volume=volume,
            timestamp=datetime.now(),
            reason=reason
        )
        
        self.pending_signals.append(signal)
        logger.info(f"生成信号: {direction} {self.symbol} @ {current_price:.2f} - {reason}")
        
        return signal
    
    def is_trending_up(self, period: int = 5) -> bool:
        """判断是否上涨趋势"""
        if len(self.price_data) < period:
            return False
        
        recent_prices = self.price_data[-period:]
        return all(recent_prices[i] <= recent_prices[i+1] for i in range(len(recent_prices)-1))
    
    def is_trending_down(self, period: int = 5) -> bool:
        """判断是否下跌趋势"""
        if len(self.price_data) < period:
            return False
        
        recent_prices = self.price_data[-period:]
        return all(recent_prices[i] >= recent_prices[i+1] for i in range(len(recent_prices)-1))
    
    def is_oversold(self, threshold: float = 30.0) -> bool:
        """判断是否超卖"""
        rsi = self.get_indicator('rsi')
        return rsi is not None and rsi < threshold
    
    def is_overbought(self, threshold: float = 70.0) -> bool:
        """判断是否超买"""
        rsi = self.get_indicator('rsi')
        return rsi is not None and rsi > threshold
    
    def is_above_ma(self, period: int = 20) -> bool:
        """判断价格是否在移动平均线之上"""
        current_price = self.get_current_price()
        ma = self.get_indicator(f'sma_{period}')
        
        if not current_price or not ma:
            return False
        
        return current_price > ma
    
    def is_below_ma(self, period: int = 20) -> bool:
        """判断价格是否在移动平均线之下"""
        current_price = self.get_current_price()
        ma = self.get_indicator(f'sma_{period}')
        
        if not current_price or not ma:
            return False
        
        return current_price < ma
    
    def get_ma_cross_signal(self, fast_period: int = 5, slow_period: int = 10) -> Optional[str]:
        """获取移动平均线交叉信号"""
        fast_ma = self.get_indicator(f'sma_{fast_period}')
        slow_ma = self.get_indicator(f'sma_{slow_period}')
        
        if not fast_ma or not slow_ma:
            return None
        
        if fast_ma > slow_ma:
            return 'BUY'
        elif fast_ma < slow_ma:
            return 'SELL'
        else:
            return 'HOLD'
    
    def get_rsi_signal(self, oversold: float = 30.0, overbought: float = 70.0) -> Optional[str]:
        """获取RSI信号"""
        rsi = self.get_indicator('rsi')
        
        if not rsi:
            return None
        
        if rsi < oversold:
            return 'BUY'
        elif rsi > overbought:
            return 'SELL'
        else:
            return 'HOLD'
    
    def get_macd_signal(self) -> Optional[str]:
        """获取MACD信号"""
        macd = self.get_indicator('macd')
        signal = self.get_indicator('macd_signal')
        
        if not macd or not signal:
            return None
        
        if macd > signal:
            return 'BUY'
        elif macd < signal:
            return 'SELL'
        else:
            return 'HOLD'
    
    def get_bollinger_signal(self) -> Optional[str]:
        """获取布林带信号"""
        current_price = self.get_current_price()
        bb_upper = self.get_indicator('bb_upper')
        bb_lower = self.get_indicator('bb_lower')
        
        if not current_price or not bb_upper or not bb_lower:
            return None
        
        if current_price < bb_lower:
            return 'BUY'
        elif current_price > bb_upper:
            return 'SELL'
        else:
            return 'HOLD'
    
    def calculate_position_size(self, risk_percent: float = 0.02) -> float:
        """计算仓位大小"""
        current_price = self.get_current_price()
        if not current_price:
            return 0.0
        
        # 基于风险百分比计算仓位大小
        risk_amount = self.get_parameter('initial_capital', 100000) * risk_percent
        position_size = risk_amount / current_price
        
        return position_size
    
    def should_trade(self, min_interval: int = 5, current_time: datetime = None) -> bool:
        """判断是否应该交易"""
        # 🔧 修复：支持回测时传入历史时间
        if current_time is None:
            current_time = datetime.now()
        
        # 检查最小交易间隔
        if len(self.trades) > 0:
            last_trade_time = self.trades[-1].get('timestamp')
            if last_trade_time:
                # 如果是字符串，转换为datetime
                if isinstance(last_trade_time, str):
                    try:
                        last_trade_time = datetime.fromisoformat(last_trade_time.replace('Z', '+00:00'))
                    except:
                        last_trade_time = datetime.now()
                
                time_diff = (current_time - last_trade_time).total_seconds()
                if time_diff < min_interval * 60:  # 转换为秒
                    logger.debug(f"交易间隔不足: {time_diff}秒 < {min_interval * 60}秒")
                    return False
        
        logger.debug(f"可以交易 (trades数量: {len(self.trades)})")
        return True
