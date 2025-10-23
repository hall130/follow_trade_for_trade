"""
技术指标工具类
提供常用的技术分析指标计算功能
"""

import pandas as pd
import numpy as np
from typing import List, Tuple, Optional, Dict, Any
from utils.logger import get_logger

logger = get_logger(__name__)

class TechnicalIndicators:
    """技术指标计算类"""
    
    @staticmethod
    def sma(data: pd.Series, period: int) -> pd.Series:
        """简单移动平均线"""
        return data.rolling(window=period).mean()
    
    @staticmethod
    def ema(data: pd.Series, period: int) -> pd.Series:
        """指数移动平均线"""
        return data.ewm(span=period).mean()
    
    @staticmethod
    def wma(data: pd.Series, period: int) -> pd.Series:
        """加权移动平均线"""
        weights = np.arange(1, period + 1)
        return data.rolling(window=period).apply(lambda x: np.dot(x, weights) / weights.sum(), raw=True)
    
    @staticmethod
    def rsi(data: pd.Series, period: int = 14) -> pd.Series:
        """相对强弱指数"""
        delta = data.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        
        # 避免除零错误
        rs = gain / loss.replace(0, np.nan)  # 将0替换为NaN，避免除零
        rsi = 100 - (100 / (1 + rs))
        
        # 处理特殊情况
        rsi = rsi.fillna(50)  # 当gain和loss都为0时，RSI设为50（中性）
        
        return rsi
    
    @staticmethod
    def macd(data: pd.Series, fast_period: int = 12, slow_period: int = 26, signal_period: int = 9) -> Tuple[pd.Series, pd.Series, pd.Series]:
        """MACD指标"""
        ema_fast = data.ewm(span=fast_period).mean()
        ema_slow = data.ewm(span=slow_period).mean()
        macd_line = ema_fast - ema_slow
        signal_line = macd_line.ewm(span=signal_period).mean()
        histogram = macd_line - signal_line
        return macd_line, signal_line, histogram
    
    @staticmethod
    def bollinger_bands(data: pd.Series, period: int = 20, std_dev: float = 2) -> Tuple[pd.Series, pd.Series, pd.Series]:
        """布林带"""
        ma = TechnicalIndicators.sma(data, period)
        std = data.rolling(window=period).std()
        upper_band = ma + (std * std_dev)
        lower_band = ma - (std * std_dev)
        return upper_band, ma, lower_band
    
    @staticmethod
    def stochastic(high: pd.Series, low: pd.Series, close: pd.Series, 
                   k_period: int = 14, d_period: int = 3) -> Tuple[pd.Series, pd.Series]:
        """随机指标"""
        lowest_low = low.rolling(window=k_period).min()
        highest_high = high.rolling(window=k_period).max()
        k_percent = 100 * ((close - lowest_low) / (highest_high - lowest_low))
        d_percent = k_percent.rolling(window=d_period).mean()
        return k_percent, d_percent
    
    @staticmethod
    def atr(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
        """平均真实波幅"""
        high_low = high - low
        high_close = np.abs(high - close.shift())
        low_close = np.abs(low - close.shift())
        true_range = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
        return true_range.rolling(window=period).mean()
    
    @staticmethod
    def adx(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> Tuple[pd.Series, pd.Series, pd.Series]:
        """平均方向性指数（ADX）和方向性指标（DI）"""
        try:
            # 计算真实波幅
            tr = TechnicalIndicators.atr(high, low, close, 1)
            
            # 计算方向性移动
            plus_dm = high.diff()
            minus_dm = -low.diff()
            
            # 只保留正向移动
            plus_dm = plus_dm.where((plus_dm > minus_dm) & (plus_dm > 0), 0)
            minus_dm = minus_dm.where((minus_dm > plus_dm) & (minus_dm > 0), 0)
            
            # 平滑处理
            atr_smooth = tr.rolling(window=period).mean()
            plus_di = 100 * (plus_dm.rolling(window=period).mean() / atr_smooth)
            minus_di = 100 * (minus_dm.rolling(window=period).mean() / atr_smooth)
            
            # 计算ADX
            dx = 100 * np.abs(plus_di - minus_di) / (plus_di + minus_di)
            adx = dx.rolling(window=period).mean()
            
            return adx, plus_di, minus_di
        except Exception as e:
            logger.error(f"ADX计算失败: {e}")
            return pd.Series(index=high.index), pd.Series(index=high.index), pd.Series(index=high.index)
    
    @staticmethod
    def williams_r(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
        """威廉指标"""
        highest_high = high.rolling(window=period).max()
        lowest_low = low.rolling(window=period).min()
        williams_r = -100 * ((highest_high - close) / (highest_high - lowest_low))
        return williams_r
    
    @staticmethod
    def cci(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
        """商品通道指数"""
        typical_price = (high + low + close) / 3
        sma_tp = typical_price.rolling(window=period).mean()
        mad = typical_price.rolling(window=period).apply(lambda x: np.mean(np.abs(x - x.mean())))
        cci = (typical_price - sma_tp) / (0.015 * mad)
        return cci
    
    @staticmethod
    def obv(close: pd.Series, volume: pd.Series) -> pd.Series:
        """能量潮指标"""
        price_change = close.diff()
        obv = pd.Series(index=close.index, dtype=float)
        obv.iloc[0] = volume.iloc[0]
        
        for i in range(1, len(close)):
            if price_change.iloc[i] > 0:
                obv.iloc[i] = obv.iloc[i-1] + volume.iloc[i]
            elif price_change.iloc[i] < 0:
                obv.iloc[i] = obv.iloc[i-1] - volume.iloc[i]
            else:
                obv.iloc[i] = obv.iloc[i-1]
        
        return obv
    
    @staticmethod
    def vwap(high: pd.Series, low: pd.Series, close: pd.Series, volume: pd.Series) -> pd.Series:
        """成交量加权平均价格"""
        typical_price = (high + low + close) / 3
        return (typical_price * volume).cumsum() / volume.cumsum()
    
    @staticmethod
    def keltner_channels(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 20, multiplier: float = 2.0) -> Tuple[pd.Series, pd.Series, pd.Series]:
        """肯特纳通道"""
        ema_close = TechnicalIndicators.ema(close, period)
        atr = TechnicalIndicators.atr(high, low, close, period)
        upper_channel = ema_close + (multiplier * atr)
        lower_channel = ema_close - (multiplier * atr)
        return upper_channel, ema_close, lower_channel
    
    @staticmethod
    def ichimoku(high: pd.Series, low: pd.Series, close: pd.Series, 
                 tenkan_period: int = 9, kijun_period: int = 26, senkou_span_b_period: int = 52) -> Dict[str, pd.Series]:
        """一目均衡表"""
        try:
            # 转换线（Tenkan-sen）
            tenkan_sen = (high.rolling(window=tenkan_period).max() + low.rolling(window=tenkan_period).min()) / 2
            
            # 基准线（Kijun-sen）
            kijun_sen = (high.rolling(window=kijun_period).max() + low.rolling(window=kijun_period).min()) / 2
            
            # 先行带A（Senkou Span A）
            senkou_span_a = ((tenkan_sen + kijun_sen) / 2).shift(kijun_period)
            
            # 先行带B（Senkou Span B）
            senkou_span_b = ((high.rolling(window=senkou_span_b_period).max() + 
                             low.rolling(window=senkou_span_b_period).min()) / 2).shift(kijun_period)
            
            # 迟行线（Chikou Span）
            chikou_span = close.shift(-kijun_period)
            
            return {
                'tenkan_sen': tenkan_sen,
                'kijun_sen': kijun_sen,
                'senkou_span_a': senkou_span_a,
                'senkou_span_b': senkou_span_b,
                'chikou_span': chikou_span
            }
        except Exception as e:
            logger.error(f"一目均衡表计算失败: {e}")
            return {}
    
    @staticmethod
    def parabolic_sar(high: pd.Series, low: pd.Series, close: pd.Series, 
                      af_start: float = 0.02, af_increment: float = 0.02, af_max: float = 0.2) -> pd.Series:
        """抛物线SAR"""
        try:
            length = len(close)
            sar = pd.Series(index=close.index, dtype=float)
            trend = pd.Series(index=close.index, dtype=int)
            af = pd.Series(index=close.index, dtype=float)
            ep = pd.Series(index=close.index, dtype=float)
            
            # 初始化
            sar.iloc[0] = low.iloc[0]
            trend.iloc[0] = 1  # 1为上升，-1为下降
            af.iloc[0] = af_start
            ep.iloc[0] = high.iloc[0]
            
            for i in range(1, length):
                if trend.iloc[i-1] == 1:  # 上升趋势
                    sar.iloc[i] = sar.iloc[i-1] + af.iloc[i-1] * (ep.iloc[i-1] - sar.iloc[i-1])
                    
                    if low.iloc[i] <= sar.iloc[i]:
                        # 趋势反转
                        trend.iloc[i] = -1
                        sar.iloc[i] = ep.iloc[i-1]
                        ep.iloc[i] = low.iloc[i]
                        af.iloc[i] = af_start
                    else:
                        trend.iloc[i] = 1
                        if high.iloc[i] > ep.iloc[i-1]:
                            ep.iloc[i] = high.iloc[i]
                            af.iloc[i] = min(af.iloc[i-1] + af_increment, af_max)
                        else:
                            ep.iloc[i] = ep.iloc[i-1]
                            af.iloc[i] = af.iloc[i-1]
                else:  # 下降趋势
                    sar.iloc[i] = sar.iloc[i-1] + af.iloc[i-1] * (ep.iloc[i-1] - sar.iloc[i-1])
                    
                    if high.iloc[i] >= sar.iloc[i]:
                        # 趋势反转
                        trend.iloc[i] = 1
                        sar.iloc[i] = ep.iloc[i-1]
                        ep.iloc[i] = high.iloc[i]
                        af.iloc[i] = af_start
                    else:
                        trend.iloc[i] = -1
                        if low.iloc[i] < ep.iloc[i-1]:
                            ep.iloc[i] = low.iloc[i]
                            af.iloc[i] = min(af.iloc[i-1] + af_increment, af_max)
                        else:
                            ep.iloc[i] = ep.iloc[i-1]
                            af.iloc[i] = af.iloc[i-1]
            
            return sar
        except Exception as e:
            logger.error(f"抛物线SAR计算失败: {e}")
            return pd.Series(index=close.index)

    @staticmethod
    def fibonacci_retracement(high_price: float, low_price: float) -> Dict[str, float]:
        """斐波那契回撤位"""
        price_range = high_price - low_price
        levels = {
            '0%': high_price,
            '23.6%': high_price - (price_range * 0.236),
            '38.2%': high_price - (price_range * 0.382),
            '50%': high_price - (price_range * 0.5),
            '61.8%': high_price - (price_range * 0.618),
            '78.6%': high_price - (price_range * 0.786),
            '100%': low_price
        }
        return levels

    @staticmethod
    def support_resistance(data: pd.Series, window: int = 20, min_touches: int = 2) -> Tuple[List[float], List[float]]:
        """支撑阻力位识别（改进版）"""
        try:
            # 寻找局部极值
            highs = []
            lows = []
            
            for i in range(window, len(data) - window):
                # 局部最高点
                if data.iloc[i] == data.iloc[i-window:i+window+1].max():
                    highs.append(data.iloc[i])
                
                # 局部最低点
                if data.iloc[i] == data.iloc[i-window:i+window+1].min():
                    lows.append(data.iloc[i])
            
            # 聚类相似的价格水平
            def cluster_levels(levels, tolerance=0.01):
                if not levels:
                    return []
                
                levels = sorted(levels)
                clusters = []
                current_cluster = [levels[0]]
                
                for level in levels[1:]:
                    if abs(level - current_cluster[-1]) / current_cluster[-1] <= tolerance:
                        current_cluster.append(level)
                    else:
                        if len(current_cluster) >= min_touches:
                            clusters.append(np.mean(current_cluster))
                        current_cluster = [level]
                
                if len(current_cluster) >= min_touches:
                    clusters.append(np.mean(current_cluster))
                
                return clusters
            
            resistance_levels = cluster_levels(highs)
            support_levels = cluster_levels(lows)
            
            return support_levels, resistance_levels
        except Exception as e:
            logger.error(f"支撑阻力位计算失败: {e}")
            return [], []
    
    @staticmethod
    def trend_direction(data: pd.Series, short_period: int = 10, long_period: int = 30) -> pd.Series:
        """趋势方向判断"""
        short_ma = TechnicalIndicators.sma(data, short_period)
        long_ma = TechnicalIndicators.sma(data, long_period)
        
        trend = pd.Series(index=data.index, dtype=int)
        trend[short_ma > long_ma] = 1  # 上升趋势
        trend[short_ma < long_ma] = -1  # 下降趋势
        trend[short_ma == long_ma] = 0  # 横盘
        
        return trend
    
    @staticmethod
    def volatility(data: pd.Series, period: int = 20) -> pd.Series:
        """波动率计算"""
        returns = data.pct_change()
        return returns.rolling(window=period).std() * np.sqrt(252)  # 年化波动率
    
    @staticmethod
    def momentum(data: pd.Series, period: int = 10) -> pd.Series:
        """动量指标"""
        return data / data.shift(period) - 1
    
    @staticmethod
    def price_channels(high: pd.Series, low: pd.Series, period: int = 20) -> Tuple[pd.Series, pd.Series]:
        """价格通道"""
        upper_channel = high.rolling(window=period).max()
        lower_channel = low.rolling(window=period).min()
        return upper_channel, lower_channel
    
    @staticmethod
    def elder_ray(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 13) -> Tuple[pd.Series, pd.Series]:
        """艾达透视指标"""
        ema = TechnicalIndicators.ema(close, period)
        bull_power = high - ema
        bear_power = low - ema
        return bull_power, bear_power
    
    @staticmethod
    def commodity_channel_index(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 20) -> pd.Series:
        """商品通道指数（改进版）"""
        typical_price = (high + low + close) / 3
        sma_tp = typical_price.rolling(window=period).mean()
        mad = typical_price.rolling(window=period).apply(lambda x: np.mean(np.abs(x - x.mean())))
        return (typical_price - sma_tp) / (0.015 * mad)
    
    @staticmethod
    def calculate_all_indicators(high: pd.Series, low: pd.Series, close: pd.Series, volume: pd.Series = None) -> Dict[str, Any]:
        """计算所有常用技术指标"""
        indicators = {}
        
        try:
            # 移动平均线
            indicators['SMA_5'] = TechnicalIndicators.sma(close, 5)
            indicators['SMA_10'] = TechnicalIndicators.sma(close, 10)
            indicators['SMA_20'] = TechnicalIndicators.sma(close, 20)
            indicators['SMA_50'] = TechnicalIndicators.sma(close, 50)
            indicators['EMA_12'] = TechnicalIndicators.ema(close, 12)
            indicators['EMA_26'] = TechnicalIndicators.ema(close, 26)
            
            # 震荡指标
            indicators['RSI'] = TechnicalIndicators.rsi(close)
            macd_line, signal_line, histogram = TechnicalIndicators.macd(close)
            indicators['MACD'] = macd_line
            indicators['MACD_Signal'] = signal_line
            indicators['MACD_Histogram'] = histogram
            
            # 布林带
            bb_upper, bb_middle, bb_lower = TechnicalIndicators.bollinger_bands(close)
            indicators['BB_Upper'] = bb_upper
            indicators['BB_Middle'] = bb_middle
            indicators['BB_Lower'] = bb_lower
            
            # 波动率指标
            indicators['ATR'] = TechnicalIndicators.atr(high, low, close)
            
            # 趋势指标
            adx, plus_di, minus_di = TechnicalIndicators.adx(high, low, close)
            indicators['ADX'] = adx
            indicators['Plus_DI'] = plus_di
            indicators['Minus_DI'] = minus_di
            
            # 随机指标
            stoch_k, stoch_d = TechnicalIndicators.stochastic(high, low, close)
            indicators['Stoch_K'] = stoch_k
            indicators['Stoch_D'] = stoch_d
            
            # 威廉指标
            indicators['Williams_R'] = TechnicalIndicators.williams_r(high, low, close)
            
            # 成交量指标（如果有成交量数据）
            if volume is not None:
                indicators['OBV'] = TechnicalIndicators.obv(close, volume)
                indicators['VWAP'] = TechnicalIndicators.vwap(high, low, close, volume)
            
            # 其他指标
            indicators['Momentum'] = TechnicalIndicators.momentum(close)
            indicators['Volatility'] = TechnicalIndicators.volatility(close)
            
        except Exception as e:
            logger.error(f"计算技术指标失败: {e}")
        
        return indicators

# 为了向后兼容，保留原有的函数名
def calculate_ma(data: pd.Series, period: int) -> pd.Series:
    """计算移动平均线"""
    return TechnicalIndicators.sma(data, period)

def calculate_sma(data: pd.Series, period: int) -> pd.Series:
    """计算简单移动平均线"""
    return TechnicalIndicators.sma(data, period)

def calculate_ema(data: pd.Series, period: int) -> pd.Series:
    """计算指数移动平均线"""
    return TechnicalIndicators.ema(data, period)

def calculate_rsi(data: pd.Series, period: int = 14) -> pd.Series:
    """计算RSI指标"""
    return TechnicalIndicators.rsi(data, period)

def calculate_bollinger_bands(data: pd.Series, period: int = 20, std_dev: float = 2) -> Tuple[pd.Series, pd.Series, pd.Series]:
    """计算布林带"""
    return TechnicalIndicators.bollinger_bands(data, period, std_dev)

def calculate_macd(data: pd.Series, fast_period: int = 12, slow_period: int = 26, signal_period: int = 9) -> Tuple[pd.Series, pd.Series, pd.Series]:
    """计算MACD指标"""
    return TechnicalIndicators.macd(data, fast_period, slow_period, signal_period)
