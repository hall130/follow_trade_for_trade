"""
网格交易策略
基于价格区间的网格交易策略
"""

from typing import Dict, List, Any
from datetime import datetime
import math

from ..base import StrategyBase
from ...core.strategy import MarketData, Signal, Position
from utils.logger import get_logger

logger = get_logger(__name__)

class GridStrategy(StrategyBase):
    """网格交易策略"""
    
    def __init__(self, name: str, symbol: str, config: Dict[str, Any]):
        super().__init__(name, symbol, config)
        
        # 策略参数
        self.base_price = self.get_parameter('base_price', 100.0)
        self.grid_spacing = self.get_parameter('grid_spacing', 0.02)  # 2%
        self.grid_levels = self.get_parameter('grid_levels', 10)
        self.position_size = self.get_parameter('position_size', 1.0)
        self.max_positions = self.get_parameter('max_positions', 5)
        
        # 网格状态
        self.grid_levels_buy = []
        self.grid_levels_sell = []
        self.grid_positions = {}
        
        self._initialize_grid()
        
        logger.info(f"网格策略初始化: 基准价格={self.base_price}, 网格间距={self.grid_spacing}, 网格层数={self.grid_levels}")
    
    def _initialize_grid(self) -> None:
        """初始化网格"""
        # 计算买入网格
        for i in range(1, self.grid_levels + 1):
            price = self.base_price * (1 - self.grid_spacing * i)
            self.grid_levels_buy.append(price)
        
        # 计算卖出网格
        for i in range(1, self.grid_levels + 1):
            price = self.base_price * (1 + self.grid_spacing * i)
            self.grid_levels_sell.append(price)
        
        logger.info(f"买入网格: {self.grid_levels_buy}")
        logger.info(f"卖出网格: {self.grid_levels_sell}")
    
    def on_market_data(self, data: MarketData) -> None:
        """处理市场数据"""
        current_price = data.close
        
        # 检查买入网格
        self._check_buy_grids(current_price)
        
        # 检查卖出网格
        self._check_sell_grids(current_price)
        
        # 更新网格价格（可选）
        if self.get_parameter('dynamic_grid', False):
            self._update_grid_prices(current_price)
    
    def _check_buy_grids(self, current_price: float) -> None:
        """检查买入网格"""
        for i, grid_price in enumerate(self.grid_levels_buy):
            if current_price <= grid_price:
                # 检查是否已经在该网格买入
                grid_key = f"buy_{i}"
                if grid_key not in self.grid_positions:
                    # 检查最大持仓数量
                    if len(self.positions) >= self.max_positions:
                        continue
                    
                    # 创建买入信号
                    self.create_signal(
                        direction='BUY',
                        strength=1.0,
                        volume=self.position_size,
                        reason=f"网格买入信号: 价格{current_price:.2f} <= 网格价格{grid_price:.2f}"
                    )
                    
                    # 记录网格位置
                    self.grid_positions[grid_key] = {
                        'price': grid_price,
                        'level': i,
                        'timestamp': datetime.now()
                    }
    
    def _check_sell_grids(self, current_price: float) -> None:
        """检查卖出网格"""
        for i, grid_price in enumerate(self.grid_levels_sell):
            if current_price >= grid_price:
                # 检查是否有对应的买入持仓
                buy_grid_key = f"buy_{i}"
                if buy_grid_key in self.grid_positions:
                    # 创建卖出信号
                    self.create_signal(
                        direction='SELL',
                        strength=1.0,
                        volume=self.position_size,
                        reason=f"网格卖出信号: 价格{current_price:.2f} >= 网格价格{grid_price:.2f}"
                    )
                    
                    # 移除网格位置
                    del self.grid_positions[buy_grid_key]
    
    def _update_grid_prices(self, current_price: float) -> None:
        """更新网格价格"""
        # 如果价格偏离基准价格太远，重新设置网格
        price_deviation = abs(current_price - self.base_price) / self.base_price
        
        if price_deviation > self.grid_spacing * 2:
            self.base_price = current_price
            self._initialize_grid()
            logger.info(f"重新设置网格基准价格: {self.base_price}")
    
    def generate_signals(self) -> List[Signal]:
        """生成交易信号"""
        return super().generate_signals()
    
    def get_grid_status(self) -> Dict[str, Any]:
        """获取网格状态"""
        return {
            'base_price': self.base_price,
            'grid_spacing': self.grid_spacing,
            'grid_levels': self.grid_levels,
            'buy_grids': self.grid_levels_buy,
            'sell_grids': self.grid_levels_sell,
            'active_positions': len(self.grid_positions),
            'max_positions': self.max_positions
        }
