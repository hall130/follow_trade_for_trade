import pandas as pd
import numpy as np
from typing import Dict, List
from datetime import datetime
from ..base_strategy import BaseStrategy, TradingSignal, Position
from ..utils.indicators import TechnicalIndicators
pd.options.mode.chained_assignment = None  # 忽略链式赋值警告

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
                timestamp=data.index[-1],  # 使用数据的时间戳而不是当前时间
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
                timestamp=data.index[-1],  # 使用数据的时间戳而不是当前时间
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
    
    def should_exit_position(self, position: Position, current_data: pd.DataFrame) -> bool:
        """判断是否应该退出持仓"""
        if len(current_data) < self.slow_period + self.signal_period:
            return False
        
        current_price = current_data.iloc[-1]['close']
        
        # 检查止损
        if position.stop_loss and (
            (position.side == 'LONG' and current_price <= position.stop_loss) or
            (position.side == 'SHORT' and current_price >= position.stop_loss)
        ):
            return True
        
        # 检查止盈
        if position.take_profit and (
            (position.side == 'LONG' and current_price >= position.take_profit) or
            (position.side == 'SHORT' and current_price <= position.take_profit)
        ):
            return True
        
        # 检查MACD反转信号
        try:
            # 计算MACD
            macd_line, signal_line, histogram = TechnicalIndicators.macd(
                current_data['close'], self.fast_period, self.slow_period, self.signal_period
            )
            
            # 检查MACD反转
            if position.side == 'LONG':
                # 多头持仓，检查死叉
                if (macd_line.iloc[-1] < signal_line.iloc[-1] and 
                    macd_line.iloc[-2] >= signal_line.iloc[-2]):
                    return True
            else:  # SHORT
                # 空头持仓，检查金叉
                if (macd_line.iloc[-1] > signal_line.iloc[-1] and 
                    macd_line.iloc[-2] <= signal_line.iloc[-2]):
                    return True
                    
        except Exception as e:
            # 如果计算MACD失败，不退出持仓
            pass
        
        return False