import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Any
from datetime import datetime
from ..base_strategy import BaseStrategy, TradingSignal, Position
from utils.logger import get_logger
pd.options.mode.chained_assignment = None  # 忽略链式赋值警告
logger = get_logger(__name__)

class GridStrategy(BaseStrategy):
    """网格交易策略"""
    
    def __init__(self, name: str = "Grid_Strategy", config: Dict[str, any] = None):
        if config is None:
            config = {}
        super().__init__(name, config)
        
        # 网格参数
        self.grid_levels = config.get('grid_levels', 10)  # 网格层数
        self.grid_spacing = config.get('grid_spacing', 0.02)  # 网格间距2%
        self.base_price = config.get('base_price', 50000)  # 基准价格
        self.investment_per_grid = config.get('investment_per_grid', 1000)  # 每格投资金额
        
        # 动态网格参数
        self.dynamic_grid = config.get('dynamic_grid', True)  # 是否启用动态网格
        self.grid_adjustment_threshold = config.get('grid_adjustment_threshold', 0.1)  # 网格调整阈值10%
        self.max_grid_adjustments = config.get('max_grid_adjustments', 3)  # 最大网格调整次数
        
        # 风险管理参数
        self.max_grid_positions = config.get('max_grid_positions', 5)  # 最大同时持仓数
        self.stop_loss_pct = config.get('stop_loss_pct', 0.05)  # 5%止损
        self.take_profit_pct = config.get('take_profit_pct', 0.15)  # 15%止盈
        
        # 策略状态
        self.grid_prices = []  # 网格价格列表
        self.grid_positions = {}  # 网格持仓
        self.grid_adjustment_count = 0  # 网格调整次数
        self.last_grid_adjustment = None  # 上次网格调整时间
        
        # 初始化网格
        self._initialize_grid()
    
    def _initialize_grid(self):
        """初始化网格价格"""
        self.grid_prices = []
        center_price = self.base_price
        
        # 计算上下网格价格
        for i in range(-self.grid_levels // 2, self.grid_levels // 2 + 1):
            grid_price = center_price * (1 + i * self.grid_spacing)
            self.grid_prices.append(grid_price)
        
        self.grid_prices.sort()
        logger.info(f"网格初始化完成，共{len(self.grid_prices)}个价格点")
    
    def generate_signals(self, data: pd.DataFrame) -> List[TradingSignal]:
        """生成网格交易信号"""
        signals = []
        
        if len(data) < 1:
            return signals
        
        current_price = data.iloc[-1]['close']
        
        # 检查是否需要调整网格
        if self.dynamic_grid and self._should_adjust_grid(current_price):
            self._adjust_grid(current_price)
        
        # 生成网格信号
        grid_signals = self._generate_grid_signals(current_price, data)
        signals.extend(grid_signals)
        
        # 生成趋势跟踪信号（可选）
        if self.config.get('enable_trend_following', False):
            trend_signals = self._generate_trend_signals(data)
            signals.extend(trend_signals)
        
        return signals
    
    def _should_adjust_grid(self, current_price: float) -> bool:
        """判断是否需要调整网格"""
        if self.grid_adjustment_count >= self.max_grid_adjustments:
            return False
        
        # 检查价格是否偏离网格中心过远
        center_price = self.base_price
        deviation = abs(current_price - center_price) / center_price
        
        return deviation > self.grid_adjustment_threshold
    
    def _adjust_grid(self, current_price: float):
        """调整网格"""
        try:
            old_center = self.base_price
            self.base_price = current_price
            
            # 重新计算网格价格
            self._initialize_grid()
            
            # 更新现有持仓的网格价格
            self._update_grid_positions()
            
            self.grid_adjustment_count += 1
            self.last_grid_adjustment = datetime.now()
            
            logger.info(f"网格已调整，新基准价格: {self.base_price}")
            
        except Exception as e:
            logger.error(f"网格调整失败: {e}")
    
    def _update_grid_positions(self):
        """更新网格持仓"""
        for symbol, position in self.grid_positions.items():
            # 找到最近的网格价格
            closest_grid = min(self.grid_prices, key=lambda x: abs(x - position.entry_price))
            position.metadata['grid_price'] = closest_grid
    
    def _generate_grid_signals(self, current_price: float, data: pd.DataFrame) -> List[TradingSignal]:
        """生成网格信号"""
        signals = []
        
        # 检查每个网格价格
        for grid_price in self.grid_prices:
            if self._should_generate_grid_signal(current_price, grid_price):
                signal = self._create_grid_signal(current_price, grid_price, data)
                if signal:
                    signals.append(signal)
        
        return signals
    
    def _should_generate_grid_signal(self, current_price: float, grid_price: float) -> bool:
        """判断是否应该生成网格信号"""
        # 检查价格是否接近网格线
        price_diff = abs(current_price - grid_price) / grid_price
        if price_diff > self.grid_spacing * 0.5:  # 价格偏离网格线超过50%间距
            return False
        
        # 检查是否已有该网格的持仓
        grid_key = f"{self.symbol}_{grid_price:.2f}"
        if grid_key in self.grid_positions:
            return False
        
        # 检查最大持仓限制
        if len(self.grid_positions) >= self.max_grid_positions:
            return False
        
        return True
    
    def _create_grid_signal(self, current_price: float, grid_price: float, data: pd.DataFrame) -> Optional[TradingSignal]:
        """创建网格信号"""
        try:
            # 判断买卖方向
            if current_price < grid_price:
                action = 'BUY'  # 价格低于网格线，买入
                confidence = 0.8
            else:
                action = 'SELL'  # 价格高于网格线，卖出
                confidence = 0.8
            
            # 计算数量
            quantity = self.investment_per_grid / current_price
            
            # 计算止损止盈
            stop_loss, take_profit = self._calculate_grid_stop_loss_take_profit(
                current_price, action
            )
            
            signal = TradingSignal(
                symbol=self.symbol,
                action=action,
                price=current_price,
                quantity=quantity,
                timestamp=datetime.now(),
                confidence=confidence,
                strategy_name=self.name,
                metadata={
                    'grid_price': grid_price,
                    'grid_level': self.grid_prices.index(grid_price),
                    'grid_type': 'grid_trade'
                },
                stop_loss=stop_loss,
                take_profit=take_profit,
                signal_strength=confidence
            )
            
            return signal
            
        except Exception as e:
            logger.error(f"创建网格信号失败: {e}")
            return None
    
    def _calculate_grid_stop_loss_take_profit(self, entry_price: float, action: str) -> tuple:
        """计算网格止损止盈"""
        if action == 'BUY':
            stop_loss = entry_price * (1 - self.stop_loss_pct)
            take_profit = entry_price * (1 + self.take_profit_pct)
        else:  # SELL
            stop_loss = entry_price * (1 + self.stop_loss_pct)
            take_profit = entry_price * (1 - self.take_profit_pct)
        
        return stop_loss, take_profit
    
    def _generate_trend_signals(self, data: pd.DataFrame) -> List[TradingSignal]:
        """生成趋势跟踪信号"""
        signals = []
        
        if len(data) < 20:
            return signals
        
        # 计算趋势指标
        ma_short = data['close'].rolling(window=10).mean()
        ma_long = data['close'].rolling(window=20).mean()
        
        current_price = data.iloc[-1]['close']
        
        # 趋势确认
        if ma_short.iloc[-1] > ma_long.iloc[-1] and ma_short.iloc[-2] <= ma_long.iloc[-2]:
            # 上升趋势确认
            signal = TradingSignal(
                symbol=self.symbol,
                action='BUY',
                price=current_price,
                quantity=self.investment_per_grid / current_price,
                timestamp=datetime.now(),
                confidence=0.7,
                strategy_name=self.name,
                metadata={'grid_type': 'trend_following', 'trend': 'uptrend'}
            )
            signals.append(signal)
        
        elif ma_short.iloc[-1] < ma_long.iloc[-1] and ma_short.iloc[-2] >= ma_long.iloc[-2]:
            # 下降趋势确认
            signal = TradingSignal(
                symbol=self.symbol,
                action='SELL',
                price=current_price,
                quantity=self.investment_per_grid / current_price,
                timestamp=datetime.now(),
                confidence=0.7,
                strategy_name=self.name,
                metadata={'grid_type': 'trend_following', 'trend': 'downtrend'}
            )
            signals.append(signal)
        
        return signals
    
    def should_exit_position(self, position: Position, current_data: pd.DataFrame) -> bool:
        """判断是否应该退出网格持仓"""
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
        
        # 检查网格反转信号
        if self._should_exit_on_grid_reversal(position, current_price):
            return True
        
        return False
    
    def _should_exit_on_grid_reversal(self, position: Position, current_price: float) -> bool:
        """检查是否应该因网格反转而退出"""
        if 'grid_price' not in position.metadata:
            return False
        
        grid_price = position.metadata['grid_price']
        
        # 如果价格穿越网格线，考虑平仓
        if position.side == 'LONG' and current_price < grid_price * 0.98:
            return True
        elif position.side == 'SHORT' and current_price > grid_price * 1.02:
            return True
        
        return False
    
    def open_position(self, signal: TradingSignal, current_price: float):
        """开仓并记录网格信息"""
        success = super().open_position(signal, current_price)
        
        if success and 'grid_price' in signal.metadata:
            # 记录网格持仓
            grid_key = f"{signal.symbol}_{signal.metadata['grid_price']:.2f}"
            self.grid_positions[grid_key] = self.positions[signal.symbol]
            
            # 添加网格元数据
            self.positions[signal.symbol].metadata['grid_price'] = signal.metadata['grid_price']
            self.positions[signal.symbol].metadata['grid_level'] = signal.metadata.get('grid_level', 0)
        
        return success
    
    def close_position(self, symbol: str, current_price: float, reason: str = "manual"):
        """平仓并清理网格记录"""
        # 清理网格持仓记录
        for grid_key, position in list(self.grid_positions.items()):
            if position.symbol == symbol:
                del self.grid_positions[grid_key]
                break
        
        return super().close_position(symbol, current_price, reason)
    
    def get_grid_status(self) -> Dict[str, Any]:
        """获取网格状态"""
        return {
            'base_price': self.base_price,
            'grid_levels': self.grid_levels,
            'grid_spacing': self.grid_spacing,
            'grid_prices': self.grid_prices,
            'active_grids': len(self.grid_positions),
            'max_grids': self.max_grid_positions,
            'grid_adjustment_count': self.grid_adjustment_count,
            'last_adjustment': self.last_grid_adjustment.isoformat() if self.last_grid_adjustment else None,
            'grid_positions': [
                {
                    'grid_key': key,
                    'symbol': pos.symbol,
                    'side': pos.side,
                    'quantity': pos.quantity,
                    'entry_price': pos.entry_price,
                    'grid_price': pos.metadata.get('grid_price', 0),
                    'grid_level': pos.metadata.get('grid_level', 0)
                }
                for key, pos in self.grid_positions.items()
            ]
        }
    
    def get_strategy_info(self) -> Dict[str, Any]:
        """获取策略信息"""
        base_info = super().get_strategy_info()
        base_info.update({
            'strategy_type': 'Grid Trading',
            'grid_config': {
                'grid_levels': self.grid_levels,
                'grid_spacing': self.grid_spacing,
                'base_price': self.base_price,
                'investment_per_grid': self.investment_per_grid,
                'dynamic_grid': self.dynamic_grid,
                'max_grid_positions': self.max_grid_positions
            },
            'grid_status': self.get_grid_status()
        })
        return base_info 