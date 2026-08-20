"""
马丁剥头皮网格策略
结合马丁格尔、剥头皮和网格交易的优势

策略特点：
1. 马丁格尔：亏损后加倍下注，快速回本
2. 剥头皮：快速进出，赚取小额价差（0.1%-0.5%）
3. 网格：在价格区间内设置多个买卖挂单，捕捉震荡行情

适用场景：
- 震荡行情
- 波动率适中的市场
- 资金充足的情况
"""

from typing import Dict, List, Any, Optional
from datetime import datetime
import math

from ..base import StrategyBase
from ...base_strategy import MarketData, Signal
from utils.logger import get_logger

logger = get_logger(__name__)


class MartinScalpGridStrategy(StrategyBase):
    """
    马丁剥头皮网格策略
    
    策略原理：
    - 初始买入一定数量的币种
    - 如果价格下跌，按照马丁格尔逻辑加仓（加倍）
    - 如果价格上涨，快速卖出赚取剥头皮利润
    - 在价格区间内设置多个网格挂单，捕捉震荡行情
    - 达到止盈目标后平仓，重置层级，重新开始
    """
    
    def __init__(self, name: str, symbol: str, config: Dict[str, Any]):
        super().__init__(name, symbol, config)
        self.tick_level = True  # 逐 tick 报价：每次行情推送都触发
        
        # 基础参数
        self.initial_amount = float(self.get_parameter('initial_amount', 0.01))  # 初始下单金额（USDT）
        self.martin_multiplier = float(self.get_parameter('martin_multiplier', 2.0))  # 马丁格尔倍数
        self.max_levels = int(self.get_parameter('max_levels', 10))  # 最大持仓层级
        
        # 剥头皮参数
        self.scalp_profit_pct = float(self.get_parameter('scalp_profit_pct', 0.002))  # 剥头皮利润比例（0.2%）
        self.scalp_stop_loss_pct = float(self.get_parameter('scalp_stop_loss_pct', 0.005))  # 剥头皮止损比例（0.5%）
        
        # 网格参数
        self.grid_spacing_pct = float(self.get_parameter('grid_spacing_pct', 0.001))  # 网格间距（0.1%）
        self.grid_count = int(self.get_parameter('grid_count', 10))  # 网格数量（上下各5个）
        
        # 止盈止损参数
        self.take_profit_pct = float(self.get_parameter('take_profit_pct', 0.01))  # 总持仓止盈比例（1%）
        self.stop_loss_pct = float(self.get_parameter('stop_loss_pct', 0.05))  # 总持仓止损比例（5%）
        
        # 风控参数
        self.max_position_value = float(self.get_parameter('max_position_value', 10000.0))  # 最大持仓价值（USDT）
        self.min_price_change = float(self.get_parameter('min_price_change', 0.0001))  # 最小价格变化（0.01%）
        
        # 精度设置
        self.price_precision = int(self.get_parameter('price_precision', 2))
        self.amount_precision = int(self.get_parameter('amount_precision', 6))
        
        # 状态变量
        self.current_level = 0  # 当前持仓层级（0表示无持仓）
        self.entry_price = 0.0  # 初始入场价格
        self.entry_prices = []  # 所有入场价格（多层加仓）
        self.entry_amounts = []  # 各层级的买入金额
        self.total_invested = 0.0  # 总投入金额
        self.total_amount = 0.0  # 总持仓数量
        
        # 网格订单
        self.grid_orders = []  # 网格挂单列表
        
        # 统计数据
        self.total_trades = 0
        self.total_profit = 0.0
        self.max_drawdown = 0.0
        self.win_rate = 0.0
        self.winning_trades = 0
        
        logger.info(f"马丁剥头皮网格策略初始化: {name}")
        logger.info(f"  初始金额={self.initial_amount}, 马丁倍数={self.martin_multiplier}, 最大层级={self.max_levels}")
        logger.info(f"  剥头皮利润={self.scalp_profit_pct:.4f}, 网格间距={self.grid_spacing_pct:.4f}")
    
    def on_initialize(self) -> None:
        """策略初始化"""
        self.current_level = 0
        self.entry_price = 0.0
        self.entry_prices = []
        self.entry_amounts = []
        self.total_invested = 0.0
        self.total_amount = 0.0
        self.grid_orders = []
        logger.info("策略初始化完成，等待市场数据")
    
    def on_market_data(self, data: MarketData) -> None:
        """处理市场数据"""
        if not data.close or data.close <= 0:
            return
        
        current_price = data.close
        
        # 如果还没有持仓，进行初始买入
        if self.current_level == 0:
            self._initial_buy(current_price)
            return
        
        # 检查止盈止损
        if self._check_exit_conditions(current_price):
            return
        
        # 检查剥头皮机会
        if self._check_scalp_opportunity(current_price):
            return
        
        # 检查马丁格尔加仓条件
        if self._check_martin_add_position(current_price):
            return
        
        # 更新网格订单
        self._update_grid_orders(current_price)
    
    def _initial_buy(self, price: float) -> None:
        """初始买入"""
        if price <= 0:
            return
        
        # 计算买入数量
        amount = self.initial_amount / price
        amount = round(amount, self.amount_precision)
        
        if amount <= 0:
            return
        
        # 创建买入信号
        signal = self.create_signal(
            direction='BUY',
            volume=amount,
            strength=1.0,
            reason=f"初始买入，价格={price:.{self.price_precision}f}, 金额={self.initial_amount:.2f}"
        )
        
        if signal:
            # 信号会自动添加到父类的signals列表
            pass
            
            # 更新状态
            self.current_level = 1
            self.entry_price = price
            self.entry_prices = [price]
            self.entry_amounts = [self.initial_amount]
            self.total_invested = self.initial_amount
            self.total_amount = amount
            
            logger.info(f"初始买入: 价格={price:.{self.price_precision}f}, 数量={amount:.{self.amount_precision}f}, 金额={self.initial_amount:.2f}")
    
    def _check_exit_conditions(self, price: float) -> bool:
        """检查止盈止损条件"""
        if self.current_level == 0 or self.total_amount <= 0:
            return False
        
        # 计算平均成本价
        avg_cost = self.total_invested / self.total_amount if self.total_amount > 0 else 0
        if avg_cost <= 0:
            return False
        
        # 计算盈亏比例
        profit_pct = (price - avg_cost) / avg_cost
        
        # 检查止盈
        if profit_pct >= self.take_profit_pct:
            self._close_all_positions(price, f"止盈平仓，盈利={profit_pct:.4%}")
            return True
        
        # 检查止损
        if profit_pct <= -self.stop_loss_pct:
            self._close_all_positions(price, f"止损平仓，亏损={profit_pct:.4%}")
            return True
        
        return False
    
    def _check_scalp_opportunity(self, price: float) -> bool:
        """检查剥头皮机会"""
        if self.current_level == 0 or self.total_amount <= 0:
            return False
        
        # 计算平均成本价
        avg_cost = self.total_invested / self.total_amount if self.total_amount > 0 else 0
        if avg_cost <= 0:
            return False
        
        # 计算盈利比例
        profit_pct = (price - avg_cost) / avg_cost
        
        # 如果达到剥头皮利润目标，部分平仓
        if profit_pct >= self.scalp_profit_pct:
            # 平仓50%持仓
            scalp_amount = self.total_amount * 0.5
            scalp_amount = round(scalp_amount, self.amount_precision)
            
            if scalp_amount > 0:
                signal = self.create_signal(
                    direction='SELL',
                    volume=scalp_amount,
                    strength=1.0,
                    reason=f"剥头皮平仓，盈利={profit_pct:.4%}"
                )
                
                if signal:
                    # 信号会自动添加到父类的signals列表
                    pass
                    
                    # 更新状态（按比例减少）
                    reduction_ratio = scalp_amount / self.total_amount
                    self.total_amount -= scalp_amount
                    self.total_invested *= (1 - reduction_ratio)
                    
                    # 更新统计
                    profit = scalp_amount * (price - avg_cost)
                    self.total_profit += profit
                    self.total_trades += 1
                    self.winning_trades += 1
                    
                    logger.info(f"剥头皮平仓: 数量={scalp_amount:.{self.amount_precision}f}, 价格={price:.{self.price_precision}f}, 盈利={profit:.2f}")
                    
                    # 如果全部平仓，重置状态
                    if self.total_amount <= 0.0001:  # 浮点数精度问题
                        self._reset_state()
                    
                    return True
        
        return False
    
    def _check_martin_add_position(self, price: float) -> bool:
        """检查马丁格尔加仓条件"""
        if self.current_level == 0:
            return False
        
        if self.current_level >= self.max_levels:
            logger.warning(f"已达到最大层级{self.max_levels}，不再加仓")
            return False
        
        # 检查是否需要加仓（价格下跌一定比例）
        if len(self.entry_prices) > 0:
            last_entry_price = self.entry_prices[-1]
            price_drop_pct = (last_entry_price - price) / last_entry_price
            
            # 如果价格下跌超过网格间距，进行马丁格尔加仓
            if price_drop_pct >= self.grid_spacing_pct:
                # 计算加仓金额（马丁格尔：上一次金额的倍数）
                last_amount = self.entry_amounts[-1] if self.entry_amounts else self.initial_amount
                add_amount = last_amount * self.martin_multiplier
                
                # 检查最大持仓限制
                total_value = self.total_invested + add_amount
                if total_value > self.max_position_value:
                    logger.warning(f"加仓金额将超过最大持仓限制{self.max_position_value}")
                    return False
                
                # 计算买入数量
                buy_amount = add_amount / price
                buy_amount = round(buy_amount, self.amount_precision)
                
                if buy_amount <= 0:
                    return False
                
                # 创建买入信号
                signal = self.create_signal(
                    direction='BUY',
                    volume=buy_amount,
                    strength=1.0,
                    reason=f"马丁格尔加仓（层级{self.current_level+1}），价格={price:.{self.price_precision}f}, 金额={add_amount:.2f}"
                )
                
                if signal:
                    # 信号会自动添加到父类的signals列表
                    pass
                    
                    # 更新状态
                    self.current_level += 1
                    self.entry_prices.append(price)
                    self.entry_amounts.append(add_amount)
                    self.total_invested += add_amount
                    self.total_amount += buy_amount
                    
                    logger.info(f"马丁格尔加仓: 层级={self.current_level}, 价格={price:.{self.price_precision}f}, 数量={buy_amount:.{self.amount_precision}f}, 金额={add_amount:.2f}")
                    return True
        
        return False
    
    def _update_grid_orders(self, price: float) -> None:
        """更新网格订单"""
        # 简化实现：如果有持仓，在价格区间设置网格挂单
        # 实际应该根据持仓情况动态调整网格
        
        if self.current_level == 0:
            return
        
        # 这里可以添加更复杂的网格逻辑
        # 比如：在平均成本价上下各设置N个网格挂单
        pass
    
    def _close_all_positions(self, price: float, reason: str) -> None:
        """平仓所有持仓"""
        if self.total_amount <= 0:
            return
        
        amount = round(self.total_amount, self.amount_precision)
        
        signal = self.create_signal(
            direction='SELL',
            volume=amount,
            strength=1.0,
            reason=reason
        )
        
        if signal:
            # 信号会自动添加到父类的signals列表
            pass
            
            # 计算盈亏
            avg_cost = self.total_invested / self.total_amount if self.total_amount > 0 else 0
            profit = amount * (price - avg_cost)
            
            # 更新统计
            self.total_profit += profit
            self.total_trades += 1
            if profit > 0:
                self.winning_trades += 1
            
            logger.info(f"平仓: {reason}, 数量={amount:.{self.amount_precision}f}, 价格={price:.{self.price_precision}f}, 盈亏={profit:.2f}")
            
            # 重置状态
            self._reset_state()
    
    def _reset_state(self) -> None:
        """重置状态"""
        self.current_level = 0
        self.entry_price = 0.0
        self.entry_prices = []
        self.entry_amounts = []
        self.total_invested = 0.0
        self.total_amount = 0.0
        self.grid_orders = []
        logger.info("状态已重置，等待下一次机会")
    
    def get_performance(self) -> Dict[str, Any]:
        """获取策略性能数据"""
        win_rate = (self.winning_trades / self.total_trades * 100) if self.total_trades > 0 else 0.0
        
        return {
            'total_trades': self.total_trades,
            'winning_trades': self.winning_trades,
            'win_rate': win_rate,
            'total_profit': self.total_profit,
            'max_drawdown': self.max_drawdown,
            'current_level': self.current_level,
            'total_invested': self.total_invested,
            'total_amount': self.total_amount,
            'avg_cost': self.total_invested / self.total_amount if self.total_amount > 0 else 0.0
        }

