import pandas as pd
import numpy as np
from typing import Dict, List, Any
from datetime import datetime
from ..base_strategy import BaseStrategy, TradingSignal

class BollingerStrategy(BaseStrategy):
    """布林带策略"""
    
    def __init__(self, name: str = "Bollinger_Strategy", config: Dict[str, Any] = None):
        if config is None:
            config = {}
        super().__init__(name, config)
        self.period = config.get('period', 20)
        self.std_dev = config.get('std_dev', 2)
        self.symbol = config.get('symbol', 'BTC-USDT')
        
    def calculate_bollinger_bands(self, prices: pd.Series, period: int, std_dev: float):
        """计算布林带"""
        sma = prices.rolling(window=period).mean()
        std = prices.rolling(window=period).std()
        upper_band = sma + (std * std_dev)
        lower_band = sma - (std * std_dev)
        return upper_band, sma, lower_band
        
    def generate_signals(self, data: pd.DataFrame) -> List[TradingSignal]:
        """生成布林带信号"""
        signals = []
        
        if len(data) < self.period:
            return signals
        
        # 计算布林带
        upper, middle, lower = self.calculate_bollinger_bands(
            data['close'], self.period, self.std_dev
        )
        
        # 获取最新数据
        latest = data.iloc[-1]
        prev = data.iloc[-2] if len(data) > 1 else latest
        
        # 价格触及下轨（买入信号）
        if (latest['close'] <= latest[lower.name] and 
            prev['close'] > prev[lower.name]):
            
            signal = TradingSignal(
                symbol=self.symbol,
                action='BUY',
                price=latest['close'],
                quantity=1.0,
                timestamp=datetime.now(),
                confidence=0.75,
                strategy_name=self.name,
                metadata={
                    'upper_band': latest[upper.name],
                    'middle_band': latest[middle.name],
                    'lower_band': latest[lower.name]
                }
            )
            signals.append(signal)
        
        # 价格触及上轨（卖出信号）
        elif (latest['close'] >= latest[upper.name] and 
              prev['close'] < prev[upper.name]):
            
            signal = TradingSignal(
                symbol=self.symbol,
                action='SELL',
                price=latest['close'],
                quantity=1.0,
                timestamp=datetime.now(),
                confidence=0.75,
                strategy_name=self.name,
                metadata={
                    'upper_band': latest[upper.name],
                    'middle_band': latest[middle.name],
                    'lower_band': latest[lower.name]
                }
            )
            signals.append(signal)
        
        return signals
    
    def should_exit_position(self, position, current_data):
        """判断是否应该退出持仓"""
        if len(current_data) < self.period:
            return False
            
        # 计算布林带
        upper_band, middle_band, lower_band = self.calculate_bollinger_bands(
            current_data['close'], self.period, self.std_dev
        )
        
        current_price = current_data['close'].iloc[-1]
        latest_upper = upper_band.iloc[-1]
        latest_lower = lower_band.iloc[-1]
        latest_middle = middle_band.iloc[-1]
        
        # 根据仓位方向判断退出条件
        if position.side == 'LONG':
            # 多头仓位：价格触及上轨或止损
            if current_price >= latest_upper:
                return True
            # 止损条件
            stop_loss_price = position.entry_price * (1 - self.config.get('stop_loss_pct', 0.025))
            if current_price <= stop_loss_price:
                return True
                
        elif position.side == 'SHORT':
            # 空头仓位：价格触及下轨或止损
            if current_price <= latest_lower:
                return True
            # 止损条件
            stop_loss_price = position.entry_price * (1 + self.config.get('stop_loss_pct', 0.025))
            if current_price >= stop_loss_price:
                return True
        
        return False