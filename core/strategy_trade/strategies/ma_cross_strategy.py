import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Any
from datetime import datetime
from ..base_strategy import BaseStrategy, TradingSignal, Position
from ..utils.indicators import TechnicalIndicators
from utils.logger import get_logger

logger = get_logger(__name__)

class MACrossStrategy(BaseStrategy):
    """增强版移动平均交叉策略"""
    
    def __init__(self, name: str = "MA_Cross_Strategy", config: Dict[str, any] = None):
        if config is None:
            config = {}
        super().__init__(name, config)
        
        # 移动平均参数
        self.short_period = config.get('short_period', 10)
        self.long_period = config.get('long_period', 20)
        self.ema_period = config.get('ema_period', 12)  # 指数移动平均
        
        # 信号过滤参数
        self.min_volume_ratio = config.get('min_volume_ratio', 1.2)  # 最小成交量比率
        self.min_price_change = config.get('min_price_change', 0.005)  # 最小价格变化
        self.rsi_period = config.get('rsi_period', 14)
        self.rsi_oversold = config.get('rsi_oversold', 30)
        self.rsi_overbought = config.get('rsi_overbought', 70)
        
        # 止损止盈参数
        self.stop_loss_pct = config.get('stop_loss_pct', 0.02)  # 2%止损
        self.take_profit_pct = config.get('take_profit_pct', 0.06)  # 6%止盈
        self.trailing_stop = config.get('trailing_stop', True)  # 启用追踪止损
        self.trailing_stop_pct = config.get('trailing_stop_pct', 0.01)  # 1%追踪止损
        
        # 趋势确认参数
        self.adx_period = config.get('adx_period', 14)
        self.adx_threshold = config.get('adx_threshold', 25)  # ADX阈值
        
        # 波动率参数
        self.atr_period = config.get('atr_period', 14)
        self.volatility_threshold = config.get('volatility_threshold', 0.02)  # 2%波动率阈值
        
        self.symbol = config.get('symbol', 'BTC-USDT')
        self.timeframe = config.get('timeframe', '1h')
        
        # 策略状态
        self.last_cross_direction = None  # 上次交叉方向
        self.cross_count = 0  # 交叉次数计数
        self.false_signal_count = 0  # 假信号计数
        
    def generate_signals(self, data: pd.DataFrame) -> List[TradingSignal]:
        """生成增强版移动平均交叉信号"""
        signals = []
        
        if len(data) < max(self.long_period, self.adx_period, self.rsi_period):
            return signals
        
        # 计算技术指标
        indicators = self._calculate_indicators(data)
        
        # 获取最新数据
        latest = data.iloc[-1]
        prev = data.iloc[-2] if len(data) > 1 else latest
        
        # 检查移动平均交叉
        cross_signal = self._check_ma_cross(indicators, latest, prev)
        
        if cross_signal:
            # 应用信号过滤
            if self._validate_signal_conditions(indicators, latest, cross_signal):
                # 计算信号强度
                signal_strength = self._calculate_signal_strength(indicators, latest, cross_signal)
                
                # 计算止损止盈价格
                stop_loss, take_profit = self._calculate_stop_loss_take_profit(
                    latest['close'], cross_signal.action
                )
                
                # 创建交易信号
                signal = TradingSignal(
                    symbol=self.symbol,
                    action=cross_signal.action,
                    price=latest['close'],
                    quantity=1.0,  # 实际应该根据资金计算
                    timestamp=datetime.now(),
                    confidence=signal_strength,
                    strategy_name=self.name,
                    metadata={
                        'ma_short': indicators['MA_short'].iloc[-1],
                        'ma_long': indicators['MA_long'].iloc[-1],
                        'rsi': indicators['RSI'].iloc[-1],
                        'adx': indicators['ADX'].iloc[-1],
                        'atr': indicators['ATR'].iloc[-1],
                        'volume_ratio': indicators['volume_ratio'].iloc[-1],
                        'cross_direction': cross_signal.metadata['cross_direction']
                    },
                    stop_loss=stop_loss,
                    take_profit=take_profit,
                    signal_strength=signal_strength
                )
                
                signals.append(signal)
                self.last_cross_direction = cross_signal.metadata['cross_direction']
                self.cross_count += 1
        
        return signals
    
    def should_exit_position(self, position: Position, current_data: pd.DataFrame) -> bool:
        """判断是否应该退出持仓"""
        if len(current_data) < 1:
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
        
        # 检查追踪止损
        if self.trailing_stop:
            if self._should_trailing_stop(position, current_price):
                return True
        
        # 检查趋势反转
        if self._should_exit_on_trend_reversal(position, current_data):
            return True
        
        return False
    
    def _calculate_indicators(self, data: pd.DataFrame) -> Dict[str, pd.Series]:
        """计算技术指标"""
        indicators = {}
        
        # 移动平均
        indicators['MA_short'] = data['close'].rolling(window=self.short_period).mean()
        indicators['MA_long'] = data['close'].rolling(window=self.long_period).mean()
        indicators['EMA'] = data['close'].ewm(span=self.ema_period).mean()
        
        # RSI
        indicators['RSI'] = self._calculate_rsi(data['close'], self.rsi_period)
        
        # ADX (趋势强度)
        indicators['ADX'] = self._calculate_adx(data, self.adx_period)
        
        # ATR (平均真实波幅)
        indicators['ATR'] = self._calculate_atr(data, self.atr_period)
        
        # 成交量比率
        indicators['volume_ratio'] = data['volume'] / data['volume'].rolling(window=20).mean()
        
        # 价格变化率
        indicators['price_change'] = data['close'].pct_change()
        
        # 波动率
        indicators['volatility'] = data['close'].rolling(window=20).std() / data['close'].rolling(window=20).mean()
        
        return indicators
    
    def _calculate_rsi(self, prices: pd.Series, period: int) -> pd.Series:
        """计算RSI指标"""
        delta = prices.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))
        return rsi
    
    def _calculate_adx(self, data: pd.DataFrame, period: int) -> pd.Series:
        """计算ADX指标"""
        high = data['high']
        low = data['low']
        close = data['close']
        
        # 计算+DM和-DM
        plus_dm = high.diff()
        minus_dm = low.diff()
        
        plus_dm[plus_dm < 0] = 0
        minus_dm[minus_dm > 0] = 0
        
        # 计算TR
        tr1 = high - low
        tr2 = abs(high - close.shift(1))
        tr3 = abs(low - close.shift(1))
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        
        # 计算平滑值
        atr = tr.rolling(window=period).mean()
        plus_di = 100 * (plus_dm.rolling(window=period).mean() / atr)
        minus_di = 100 * (minus_dm.rolling(window=period).mean() / atr)
        
        # 计算DX和ADX
        dx = 100 * abs(plus_di - minus_di) / (plus_di + minus_di)
        adx = dx.rolling(window=period).mean()
        
        return adx
    
    def _calculate_atr(self, data: pd.DataFrame, period: int) -> pd.Series:
        """计算ATR指标"""
        high = data['high']
        low = data['low']
        close = data['close']
        
        tr1 = high - low
        tr2 = abs(high - close.shift(1))
        tr3 = abs(low - close.shift(1))
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        
        atr = tr.rolling(window=period).mean()
        return atr
    
    def _check_ma_cross(self, indicators: Dict, latest: pd.Series, prev: pd.Series) -> Optional[TradingSignal]:
        """检查移动平均交叉"""
        ma_short = indicators['MA_short'].iloc[-1]
        ma_long = indicators['MA_long'].iloc[-1]
        ma_short_prev = indicators['MA_short'].iloc[-2]
        ma_long_prev = indicators['MA_long'].iloc[-2]
        
        # 金叉信号（短期均线上穿长期均线）
        if (ma_short > ma_long and ma_short_prev <= ma_long_prev):
            return TradingSignal(
                symbol=self.symbol,
                action='BUY',
                price=latest['close'],
                quantity=1.0,
                timestamp=datetime.now(),
                confidence=0.8,
                strategy_name=self.name,
                metadata={'cross_direction': 'golden_cross'}
            )
        
        # 死叉信号（短期均线下穿长期均线）
        elif (ma_short < ma_long and ma_short_prev >= ma_long_prev):
            return TradingSignal(
                symbol=self.symbol,
                action='SELL',
                price=latest['close'],
                quantity=1.0,
                timestamp=datetime.now(),
                confidence=0.8,
                strategy_name=self.name,
                metadata={'cross_direction': 'death_cross'}
            )
        
        return None
    
    def _validate_signal_conditions(self, indicators: Dict, latest: pd.Series, signal: TradingSignal) -> bool:
        """验证信号条件"""
        # 检查成交量
        volume_ratio = indicators['volume_ratio'].iloc[-1]
        if volume_ratio < self.min_volume_ratio:
            return False
        
        # 检查价格变化
        price_change = abs(indicators['price_change'].iloc[-1])
        if price_change < self.min_price_change:
            return False
        
        # 检查RSI
        rsi = indicators['RSI'].iloc[-1]
        if signal.action == 'BUY' and rsi > self.rsi_overbought:
            return False
        if signal.action == 'SELL' and rsi < self.rsi_oversold:
            return False
        
        # 检查趋势强度
        adx = indicators['ADX'].iloc[-1]
        if adx < self.adx_threshold:
            return False
        
        # 检查波动率
        volatility = indicators['volatility'].iloc[-1]
        if volatility < self.volatility_threshold:
            return False
        
        # 检查假信号
        if self._is_false_signal(signal):
            return False
        
        return True
    
    def _is_false_signal(self, signal: TradingSignal) -> bool:
        """检查是否为假信号"""
        # 如果连续出现相同方向的交叉，可能是假信号
        if (self.last_cross_direction == signal.metadata['cross_direction'] and 
            self.cross_count > 0):
            self.false_signal_count += 1
            
            # 如果假信号过多，降低置信度
            if self.false_signal_count > 3:
                return True
        
        return False
    
    def _calculate_signal_strength(self, indicators: Dict, latest: pd.Series, signal: TradingSignal) -> float:
        """计算信号强度"""
        strength = 0.5  # 基础强度
        
        # RSI调整
        rsi = indicators['RSI'].iloc[-1]
        if signal.action == 'BUY':
            if rsi < 30:
                strength += 0.2
            elif rsi < 50:
                strength += 0.1
        else:  # SELL
            if rsi > 70:
                strength += 0.2
            elif rsi > 50:
                strength += 0.1
        
        # ADX调整
        adx = indicators['ADX'].iloc[-1]
        if adx > 40:
            strength += 0.2
        elif adx > 25:
            strength += 0.1
        
        # 成交量调整
        volume_ratio = indicators['volume_ratio'].iloc[-1]
        if volume_ratio > 2.0:
            strength += 0.1
        
        # 假信号调整
        if self.false_signal_count > 0:
            strength -= min(0.2, self.false_signal_count * 0.05)
        
        return max(0.1, min(1.0, strength))
    
    def _calculate_stop_loss_take_profit(self, entry_price: float, action: str) -> tuple:
        """计算止损止盈价格"""
        if action == 'BUY':
            stop_loss = entry_price * (1 - self.stop_loss_pct)
            take_profit = entry_price * (1 + self.take_profit_pct)
        else:  # SELL
            stop_loss = entry_price * (1 + self.stop_loss_pct)
            take_profit = entry_price * (1 - self.take_profit_pct)
        
        return stop_loss, take_profit
    
    def _should_trailing_stop(self, position: Position, current_price: float) -> bool:
        """检查是否应该触发追踪止损"""
        if not self.trailing_stop:
            return False
        
        if position.side == 'LONG':
            # 更新追踪止损价格
            new_stop = current_price * (1 - self.trailing_stop_pct)
            if new_stop > position.stop_loss:
                position.stop_loss = new_stop
                return False
        else:  # SHORT
            new_stop = current_price * (1 + self.trailing_stop_pct)
            if new_stop < position.stop_loss:
                position.stop_loss = new_stop
                return False
        
        return False
    
    def _should_exit_on_trend_reversal(self, position: Position, current_data: pd.DataFrame) -> bool:
        """检查是否应该因趋势反转而退出"""
        if len(current_data) < self.long_period:
            return False
        
        # 计算当前趋势
        ma_short = current_data['close'].rolling(window=self.short_period).mean().iloc[-1]
        ma_long = current_data['close'].rolling(window=self.long_period).mean().iloc[-1]
        
        if position.side == 'LONG' and ma_short < ma_long:
            return True
        elif position.side == 'SHORT' and ma_short > ma_long:
            return True
        
        return False
    
    def get_strategy_info(self) -> Dict[str, Any]:
        """获取策略信息"""
        return {
            'name': self.name,
            'symbol': self.symbol,
            'timeframe': self.timeframe,
            'parameters': {
                'short_period': self.short_period,
                'long_period': self.long_period,
                'ema_period': self.ema_period,
                'rsi_period': self.rsi_period,
                'adx_period': self.adx_period,
                'atr_period': self.atr_period,
                'stop_loss_pct': self.stop_loss_pct,
                'take_profit_pct': self.take_profit_pct
            },
            'status': {
                'cross_count': self.cross_count,
                'false_signal_count': self.false_signal_count,
                'last_cross_direction': self.last_cross_direction
            }
        }