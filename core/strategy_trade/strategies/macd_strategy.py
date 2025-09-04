import pandas as pd
import numpy as np
from typing import Dict, List
from datetime import datetime
from ..base_strategy import BaseStrategy, TradingSignal
from ..utils.indicators import TechnicalIndicators

class MACDStrategy(BaseStrategy):
    """MACD策略"""
    
    def __init__(self, name: str = "MACD_Strategy", config: Dict[str, any] = None):
        if config is None:
            config = {}
        super().__init__(name, config)
        self.fast_period = config.get('fast_period', 12)
        self.slow_period = config.get('slow_period', 26)
        self.signal_period = config.get('signal_period', 9)
        self.symbol = config.get('symbol', 'BTC-USDT')
        
    def generate_signals(self, data: pd.DataFrame) -> List[TradingSignal]:
        """生成MACD信号"""
        signals = []
        
        if len(data) < self.slow_period + self.signal_period:
            return signals
        
        # 计算MACD
        macd_line, signal_line, histogram = TechnicalIndicators.macd(
            data['close'], self.fast_period, self.slow_period, self.signal_period
        )
        
        # 获取最新数据
        latest = data.iloc[-1]
        prev = data.iloc[-2] if len(data) > 1 else latest
        
        # MACD金叉信号
        if (macd_line.iloc[-1] > signal_line.iloc[-1] and 
            macd_line.iloc[-2] <= signal_line.iloc[-2]):
            
            signal = TradingSignal(
                symbol=self.symbol,
                action='BUY',
                price=latest['close'],
                quantity=1.0,
                timestamp=datetime.now(),
                confidence=0.8,
                strategy_name=self.name,
                metadata={
                    'macd': macd_line.iloc[-1],
                    'signal': signal_line.iloc[-1],
                    'histogram': histogram.iloc[-1]
                }
            )
            signals.append(signal)
        
        # MACD死叉信号
        elif (macd_line.iloc[-1] < signal_line.iloc[-1] and 
              macd_line.iloc[-2] >= signal_line.iloc[-2]):
            
            signal = TradingSignal(
                symbol=self.symbol,
                action='SELL',
                price=latest['close'],
                quantity=1.0,
                timestamp=datetime.now(),
                confidence=0.8,
                strategy_name=self.name,
                metadata={
                    'macd': macd_line.iloc[-1],
                    'signal': signal_line.iloc[-1],
                    'histogram': histogram.iloc[-1]
                }
            )
            signals.append(signal)
        
        return signals