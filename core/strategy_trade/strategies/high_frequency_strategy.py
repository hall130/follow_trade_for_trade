#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
高频交易策略
基于短期技术指标的高频交易策略，适合测试回测系统
"""

import pandas as pd
import numpy as np
from typing import List, Dict, Any
from datetime import datetime
from ..base_strategy import BaseStrategy, TradingSignal, Position
from ..utils.indicators import calculate_sma, calculate_ema, calculate_rsi, calculate_macd


class HighFrequencyStrategy(BaseStrategy):
    """高频交易策略"""
    
    def __init__(self, name: str, config: Dict[str, Any]):
        super().__init__(name, config)
        
        # 策略参数
        self.fast_ema_period = config.get('fast_ema_period', 5)
        self.slow_ema_period = config.get('slow_ema_period', 10)
        self.rsi_period = config.get('rsi_period', 14)
        self.rsi_oversold = config.get('rsi_oversold', 30)
        self.rsi_overbought = config.get('rsi_overbought', 70)
        self.volume_threshold = config.get('volume_threshold', 1.5)  # 成交量倍数阈值
        self.price_change_threshold = config.get('price_change_threshold', 0.01)  # 价格变化阈值 1%
        self.min_trade_interval = config.get('min_trade_interval', 5)  # 最小交易间隔（分钟）
        
        # 内部状态
        self.last_trade_time = None
        self.trade_count = 0
        self.max_trades_per_day = config.get('max_trades_per_day', 50)
        
        print(f"🚀 高频策略初始化: {name}")
        print(f"📊 参数: 快线EMA={self.fast_ema_period}, 慢线EMA={self.slow_ema_period}")
        print(f"📊 RSI参数: 周期={self.rsi_period}, 超卖={self.rsi_oversold}, 超买={self.rsi_overbought}")
    
    def generate_signals(self, data: pd.DataFrame) -> List[TradingSignal]:
        """生成高频交易信号"""
        signals = []
        
        if len(data) < max(self.fast_ema_period, self.slow_ema_period, self.rsi_period):
            return signals
        
        try:
            # 计算技术指标
            fast_ema = calculate_ema(data['close'], self.fast_ema_period)
            slow_ema = calculate_ema(data['close'], self.slow_ema_period)
            rsi = calculate_rsi(data['close'], self.rsi_period)
            
            # 计算成交量移动平均
            volume_ma = data['volume'].rolling(window=20).mean()
            current_volume = data['volume'].iloc[-1]
            volume_ratio = current_volume / volume_ma.iloc[-1] if volume_ma.iloc[-1] > 0 else 1
            
            # 计算价格变化率
            price_change = abs(data['close'].pct_change().iloc[-1]) if len(data) > 1 else 0
            
            current_price = data['close'].iloc[-1]
            current_time = data.index[-1]
            
            # 检查交易频率限制
            if self.last_trade_time is not None:
                time_diff = (current_time - self.last_trade_time).total_seconds() / 60
                if time_diff < self.min_trade_interval:
                    return signals
            
            # 检查每日交易次数限制
            if self.trade_count >= self.max_trades_per_day:
                return signals
            
            # 信号1: EMA交叉 + RSI确认
            if len(fast_ema) >= 2 and len(slow_ema) >= 2:
                # 金叉：快线上穿慢线
                if (fast_ema.iloc[-1] > slow_ema.iloc[-1] and 
                    fast_ema.iloc[-2] <= slow_ema.iloc[-2] and
                    rsi.iloc[-1] < self.rsi_overbought and
                    volume_ratio > self.volume_threshold):
                    
                    signal = TradingSignal(
                        symbol=self.symbol,
                        action='BUY',
                        price=current_price,
                        quantity=1.0,
                        timestamp=current_time,
                        confidence=0.8,
                        strategy_name=self.name,
                        metadata={
                            'signal_type': 'ema_cross_golden',
                            'fast_ema': float(fast_ema.iloc[-1]),
                            'slow_ema': float(slow_ema.iloc[-1]),
                            'rsi': float(rsi.iloc[-1]),
                            'volume_ratio': float(volume_ratio)
                        }
                    )
                    signals.append(signal)
                    self.last_trade_time = current_time
                    self.trade_count += 1
                
                # 死叉：快线下穿慢线
                elif (fast_ema.iloc[-1] < slow_ema.iloc[-1] and 
                      fast_ema.iloc[-2] >= slow_ema.iloc[-2] and
                      rsi.iloc[-1] > self.rsi_oversold and
                      volume_ratio > self.volume_threshold):
                    
                    signal = TradingSignal(
                        symbol=self.symbol,
                        action='SELL',
                        price=current_price,
                        quantity=1.0,
                        timestamp=current_time,
                        confidence=0.8,
                        strategy_name=self.name,
                        metadata={
                            'signal_type': 'ema_cross_death',
                            'fast_ema': float(fast_ema.iloc[-1]),
                            'slow_ema': float(slow_ema.iloc[-1]),
                            'rsi': float(rsi.iloc[-1]),
                            'volume_ratio': float(volume_ratio)
                        }
                    )
                    signals.append(signal)
                    self.last_trade_time = current_time
                    self.trade_count += 1
            
            # 信号2: RSI极值反转
            if len(rsi) >= 1:
                # RSI超卖反弹
                if (rsi.iloc[-1] < self.rsi_oversold and 
                    price_change > self.price_change_threshold and
                    volume_ratio > self.volume_threshold):
                    
                    signal = TradingSignal(
                        symbol=self.symbol,
                        action='BUY',
                        price=current_price,
                        quantity=1.0,
                        timestamp=current_time,
                        confidence=0.7,
                        strategy_name=self.name,
                        metadata={
                            'signal_type': 'rsi_oversold_bounce',
                            'rsi': float(rsi.iloc[-1]),
                            'price_change': float(price_change),
                            'volume_ratio': float(volume_ratio)
                        }
                    )
                    signals.append(signal)
                    self.last_trade_time = current_time
                    self.trade_count += 1
                
                # RSI超买回调
                elif (rsi.iloc[-1] > self.rsi_overbought and 
                      price_change > self.price_change_threshold and
                      volume_ratio > self.volume_threshold):
                    
                    signal = TradingSignal(
                        symbol=self.symbol,
                        action='SELL',
                        price=current_price,
                        quantity=1.0,
                        timestamp=current_time,
                        confidence=0.7,
                        strategy_name=self.name,
                        metadata={
                            'signal_type': 'rsi_overbought_pullback',
                            'rsi': float(rsi.iloc[-1]),
                            'price_change': float(price_change),
                            'volume_ratio': float(volume_ratio)
                        }
                    )
                    signals.append(signal)
                    self.last_trade_time = current_time
                    self.trade_count += 1
            
            # 信号3: 价格突破 + 成交量确认
            if len(data) >= 20:
                # 计算布林带
                bb_period = 20
                bb_std = 2
                bb_middle = data['close'].rolling(window=bb_period).mean()
                bb_std_val = data['close'].rolling(window=bb_period).std()
                bb_upper = bb_middle + (bb_std_val * bb_std)
                bb_lower = bb_middle - (bb_std_val * bb_std)
                
                # 上轨突破
                if (current_price > bb_upper.iloc[-1] and 
                    current_price > bb_upper.iloc[-2] and
                    volume_ratio > self.volume_threshold * 1.5):
                    
                    signal = TradingSignal(
                        symbol=self.symbol,
                        action='BUY',
                        price=current_price,
                        quantity=1.0,
                        timestamp=current_time,
                        confidence=0.75,
                        strategy_name=self.name,
                        metadata={
                            'signal_type': 'bollinger_upper_break',
                            'bb_upper': float(bb_upper.iloc[-1]),
                            'bb_middle': float(bb_middle.iloc[-1]),
                            'volume_ratio': float(volume_ratio)
                        }
                    )
                    signals.append(signal)
                    self.last_trade_time = current_time
                    self.trade_count += 1
                
                # 下轨突破
                elif (current_price < bb_lower.iloc[-1] and 
                      current_price < bb_lower.iloc[-2] and
                      volume_ratio > self.volume_threshold * 1.5):
                    
                    signal = TradingSignal(
                        symbol=self.symbol,
                        action='SELL',
                        price=current_price,
                        quantity=1.0,
                        timestamp=current_time,
                        confidence=0.75,
                        strategy_name=self.name,
                        metadata={
                            'signal_type': 'bollinger_lower_break',
                            'bb_lower': float(bb_lower.iloc[-1]),
                            'bb_middle': float(bb_middle.iloc[-1]),
                            'volume_ratio': float(volume_ratio)
                        }
                    )
                    signals.append(signal)
                    self.last_trade_time = current_time
                    self.trade_count += 1
            
        except Exception as e:
            print(f"❌ 高频策略信号生成失败: {e}")
        
        return signals
    
    def should_exit_position(self, position: Position, current_data: pd.DataFrame) -> bool:
        """判断是否应该退出持仓"""
        if len(current_data) < 5:
            return False
        
        try:
            current_price = current_data['close'].iloc[-1]
            entry_price = position.entry_price
            
            # 计算收益率
            if position.side == 'LONG':
                pnl_ratio = (current_price - entry_price) / entry_price
            else:
                pnl_ratio = (entry_price - current_price) / entry_price
            
            # 止盈止损
            take_profit = 0.02  # 2% 止盈
            stop_loss = 0.01    # 1% 止损
            
            # 止盈
            if pnl_ratio >= take_profit:
                print(f"🎯 止盈退出: {position.side} 收益率 {pnl_ratio:.2%}")
                return True
            
            # 止损
            if pnl_ratio <= -stop_loss:
                print(f"🛑 止损退出: {position.side} 收益率 {pnl_ratio:.2%}")
                return True
            
            # 时间止损（持仓超过30分钟）
            if position.entry_time:
                time_diff = (current_data.index[-1] - position.entry_time).total_seconds() / 60
                if time_diff > 30:
                    print(f"⏰ 时间止损: {position.side} 持仓时间 {time_diff:.1f}分钟")
                    return True
            
        except Exception as e:
            print(f"❌ 持仓退出判断失败: {e}")
        
        return False
    
    def get_strategy_info(self) -> Dict[str, Any]:
        """获取策略信息"""
        return {
            'name': self.name,
            'type': 'HighFrequencyStrategy',
            'parameters': {
                'fast_ema_period': self.fast_ema_period,
                'slow_ema_period': self.slow_ema_period,
                'rsi_period': self.rsi_period,
                'rsi_oversold': self.rsi_oversold,
                'rsi_overbought': self.rsi_overbought,
                'volume_threshold': self.volume_threshold,
                'price_change_threshold': self.price_change_threshold,
                'min_trade_interval': self.min_trade_interval,
                'max_trades_per_day': self.max_trades_per_day
            },
            'status': {
                'trade_count': self.trade_count,
                'last_trade_time': self.last_trade_time
            }
        }
