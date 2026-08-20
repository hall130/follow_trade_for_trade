"""
市商对冲策略（Market Maker Hedge Strategy）
参考: https://github.com/yanowo/Backpack-MM-Simple/

在做市商基础上增加对冲功能：
1. 检测持仓方向风险
2. 通过反向对冲减少单向暴露
3. 维持市场中性
"""

from typing import Dict, List, Any, Optional
from datetime import datetime
import math

from .market_maker import MarketMakerStrategy
from ...base_strategy import MarketData, Signal
from utils.logger import get_logger

logger = get_logger(__name__)


class MarketMakerHedgeStrategy(MarketMakerStrategy):
    """
    市商对冲策略
    
    在做市商策略基础上，增加对冲机制以减少方向性风险
    """
    
    def __init__(self, name: str, symbol: str, config: Dict[str, Any]):
        super().__init__(name, symbol, config)
        self.tick_level = True  # 逐 tick 报价：每次行情推送都触发
        
        # 对冲参数
        self.enable_hedge = self.get_parameter('enable_hedge', True)  # 是否启用对冲
        self.hedge_threshold = float(self.get_parameter('hedge_threshold', 0.5))  # 对冲触发阈值（持仓/总资产比例）
        self.hedge_size_ratio = float(self.get_parameter('hedge_size_ratio', 0.8))  # 对冲比例（80%）
        self.max_position_exposure = float(self.get_parameter('max_position_exposure', 1.0))  # 最大持仓暴露倍数
        
        # 对冲状态
        self.hedge_position = 0.0  # 对冲持仓
        self.hedge_entry_price = 0.0  # 对冲开仓价格
        self.is_hedged = False  # 是否已对冲
        
        logger.info(f"市商对冲策略初始化: 对冲阈值={self.hedge_threshold:.2%}, 对冲比例={self.hedge_size_ratio:.2%}")
    
    def on_market_data(self, data: MarketData) -> None:
        """处理市场数据"""
        # 调用父类方法
        super().on_market_data(data)
        
        # 检查并执行对冲
        if self.enable_hedge:
            self._check_and_hedge()
    
    def _check_and_hedge(self) -> None:
        """检查并执行对冲"""
        try:
            # 确保 signals 属性存在
            if not hasattr(self, 'signals'):
                self.signals: List[Signal] = []
            
            if not self.enable_hedge or self.current_price == 0:
                return
            
            # 计算当前持仓暴露
            total_value = self.base_balance * self.current_price + self.quote_balance
            if total_value == 0:
                return
            
            position_value = abs(self.position_size) * self.current_price
            position_exposure_ratio = position_value / total_value if total_value > 0 else 0
            
            # 检查是否需要对冲
            if position_exposure_ratio > self.hedge_threshold and not self.is_hedged:
                # 需要开对冲
                hedge_size = abs(self.position_size) * self.hedge_size_ratio
                hedge_side = 'SELL' if self.position_size > 0 else 'BUY'  # 反向对冲
                
                logger.info(f"触发对冲: 持仓暴露={position_exposure_ratio:.2%}, 对冲数量={hedge_size:.4f}")
                
                signal = Signal(
                    symbol=self.symbol,
                    direction=hedge_side,
                    price=self.current_price,
                    volume=hedge_size,
                    timestamp=datetime.now(),
                    reason=f'对冲开仓: 减少方向性风险'
                )
                self.signals.append(signal)
                self.is_hedged = True
                self.hedge_position = hedge_size
                self.hedge_entry_price = self.current_price
                
            elif position_exposure_ratio <= self.hedge_threshold * 0.5 and self.is_hedged:
                # 对冲已不再需要，平掉对冲
                logger.info(f"平掉对冲: 持仓暴露已降低到 {position_exposure_ratio:.2%}")
                
                close_side = 'BUY' if self.hedge_position > 0 else 'SELL'
                signal = Signal(
                    symbol=self.symbol,
                    direction=close_side,
                    price=self.current_price,
                    volume=abs(self.hedge_position),
                    timestamp=datetime.now(),
                    reason='对冲平仓: 风险已降低'
                )
                self.signals.append(signal)
                self.is_hedged = False
                self.hedge_position = 0.0
                
        except Exception as e:
            logger.error(f"检查对冲失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
    
    def get_performance(self) -> Dict[str, Any]:
        """获取策略表现"""
        perf = super().get_performance()
        perf.update({
            'is_hedged': self.is_hedged,
            'hedge_position': self.hedge_position,
            'hedge_entry_price': self.hedge_entry_price,
            'position_exposure': self.position_size * self.current_price / (self.base_balance * self.current_price + self.quote_balance) if (self.base_balance * self.current_price + self.quote_balance) > 0 else 0
        })
        return perf

