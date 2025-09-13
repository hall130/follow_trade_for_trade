import pandas as pd
import numpy as np
from typing import Dict, List
from datetime import datetime
from ..base_strategy import BaseStrategy, TradingSignal

pd.options.mode.chained_assignment = None  # 忽略链式赋值警告

class RSIStrategy(BaseStrategy):
    """RSI策略"""
    
    def __init__(self, name: str = "RSI_Strategy", config: Dict[str, any] = None):
        if config is None:
            config = {}
        super().__init__(name, config)
        self.rsi_period = config.get('rsi_period', 14)
        self.oversold_level = config.get('rsi_oversold', config.get('oversold_level', 30))
        self.overbought_level = config.get('rsi_overbought', config.get('overbought_level', 70))
        # symbol 和 timeframe 已经在基类中设置，不需要重复设置
        
    def calculate_rsi(self, prices: pd.Series, period: int) -> pd.Series:
        """计算RSI指标"""
        delta = prices.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))
        return rsi
        
    def generate_signals(self, data: pd.DataFrame) -> List[TradingSignal]:
        """生成RSI信号"""
        signals = []
        
        if len(data) < self.rsi_period + 1:
            return signals
        
        # 计算RSI
        data['RSI'] = self.calculate_rsi(data['close'], self.rsi_period)
        
        # 获取最新数据
        latest = data.iloc[-1]
        prev = data.iloc[-2]
        
        # RSI超卖信号（买入）
        if (latest['RSI'] < self.oversold_level and 
            prev['RSI'] >= self.oversold_level):
            
            signal = TradingSignal(
                symbol=self.symbol,
                action='BUY',
                price=latest['close'],
                quantity=1.0,
                timestamp=datetime.now(),
                confidence=0.7,
                strategy_name=self.name,
                metadata={'rsi': latest['RSI']}
            )
            signals.append(signal)
        
        # RSI超买信号（卖出）
        elif (latest['RSI'] > self.overbought_level and 
              prev['RSI'] <= self.overbought_level):
            
            signal = TradingSignal(
                symbol=self.symbol,
                action='SELL',
                price=latest['close'],
                quantity=1.0,
                timestamp=datetime.now(),
                confidence=0.7,
                strategy_name=self.name,
                metadata={'rsi': latest['RSI']}
            )
            signals.append(signal)
        
        return signals
    
    def should_exit_position(self, position, current_data: pd.DataFrame) -> bool:
        """判断是否应该退出持仓"""
        if len(current_data) < self.rsi_period:
            return False
            
        # 计算RSI
        current_data['RSI'] = self.calculate_rsi(current_data['close'], self.rsi_period)
        latest_rsi = current_data['RSI'].iloc[-1]
        current_price = current_data['close'].iloc[-1]
        
        # 根据仓位方向判断退出条件
        if position.side == 'LONG':
            # 多头仓位：RSI超买或止损
            if latest_rsi > self.overbought_level:
                return True
            # 止损条件
            if current_price < position.entry_price * (1 - self.config.get('stop_loss_pct', 0.03)):
                return True
                
        elif position.side == 'SHORT':
            # 空头仓位：RSI超卖或止损
            if latest_rsi < self.oversold_level:
                return True
            # 止损条件
            if current_price > position.entry_price * (1 + self.config.get('stop_loss_pct', 0.03)):
                return True
        
        return False