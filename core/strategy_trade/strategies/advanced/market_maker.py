"""
做市商策略（Market Maker Strategy）
参考: https://github.com/yanowo/Backpack-MM-Simple/

策略原理：
1. 在买卖两侧同时挂单，通过维持买卖价差赚取利润
2. 支持止损/止盈功能
3. 支持重平衡功能，维持基础资产目标比例
"""

from typing import Dict, List, Any, Optional
from datetime import datetime
import math

from ..base import StrategyBase
from ...base_strategy import MarketData, Signal
from utils.logger import get_logger

logger = get_logger(__name__)


class MarketMakerStrategy(StrategyBase):
    """
    做市商策略
    
    通过维持买卖价差来赚取利润，适合流动性较好的市场
    """
    
    def __init__(self, name: str, symbol: str, config: Dict[str, Any]):
        super().__init__(name, symbol, config)
        
        # 初始化 signals 属性（基类 BaseStrategy 没有此属性，需要手动初始化）
        if not hasattr(self, 'signals'):
            self.signals: List[Signal] = []
        
        # 做市参数
        self.spread = float(self.get_parameter('spread', 0.002))  # 价差（0.2%）
        self.quantity = float(self.get_parameter('quantity', 0.1))  # 每单数量
        self.max_orders = int(self.get_parameter('max_orders', 5))  # 每侧最大订单数
        
        # 止损止盈参数
        self.stop_loss = float(self.get_parameter('stop_loss', -25.0))  # 止损金额（USDC）
        self.take_profit = float(self.get_parameter('take_profit', 50.0))  # 止盈金额（USDC）
        self.enable_stop_loss = self.get_parameter('enable_stop_loss', True)
        self.enable_take_profit = self.get_parameter('enable_take_profit', True)
        
        # 重平衡参数
        self.enable_rebalance = self.get_parameter('enable_rebalance', False)
        self.base_asset_target = float(self.get_parameter('base_asset_target', 30.0))  # 基础资产目标比例（%）
        self.rebalance_threshold = float(self.get_parameter('rebalance_threshold', 15.0))  # 重平衡触发阈值（%）
        
        # 订单管理
        self.buy_orders: List[Dict[str, Any]] = []  # 买单列表
        self.sell_orders: List[Dict[str, Any]] = []  # 卖单列表
        self.active_orders: Dict[str, Dict[str, Any]] = {}  # 活跃订单字典
        
        # 账户状态
        self.base_balance = 0.0  # 基础资产余额（如SOL）
        self.quote_balance = 0.0  # 报价资产余额（如USDC）
        self.position_size = 0.0  # 当前持仓
        self.unrealized_pnl = 0.0  # 未实现盈亏
        
        # 价格追踪
        self.current_price = 0.0
        self.best_bid = 0.0  # 最优买价
        self.best_ask = 0.0  # 最优卖价
        self.entry_price = 0.0  # 开仓价格
        
        # 统计信息
        self.total_trades = 0
        self.total_profit = 0.0
        self.last_rebalance_time = datetime.now()
        
        logger.info(f"做市商策略初始化: 价差={self.spread:.2%}, 数量={self.quantity}, 最大订单={self.max_orders}")
    
    def on_initialize(self) -> None:
        """策略初始化"""
        logger.info("做市商策略初始化...")
        # 取消所有现有订单
        self._cancel_all_orders()
        # 更新账户信息
        self._update_account()
    
    def on_market_data(self, data: MarketData) -> None:
        """处理市场数据"""
        self.current_price = data.close
        
        # 计算最优买卖价
        self.best_bid = self.current_price * (1 - self.spread / 2)
        self.best_ask = self.current_price * (1 + self.spread / 2)
        
        # 更新订单
        self._update_orders()
        
        # 检查止损止盈
        if self.enable_stop_loss or self.enable_take_profit:
            self._check_stop_loss_take_profit()
        
        # 检查重平衡
        if self.enable_rebalance:
            self._check_rebalance()
    
    def get_signals(self) -> List[Signal]:
        """获取交易信号"""
        signals = []
        
        # 做市商策略通过订单管理实现，信号主要用于记录
        # 实际交易通过_update_orders()中的订单管理实现
        
        return signals
    
    def _update_orders(self) -> None:
        """更新订单（维持做市报价）"""
        try:
            # 确保 signals 属性存在
            if not hasattr(self, 'signals'):
                self.signals: List[Signal] = []
            
            # 获取当前活跃订单
            active_buy_count = len([o for o in self.buy_orders if o.get('active', False)])
            active_sell_count = len([o for o in self.sell_orders if o.get('active', False)])
            
            # 补充买单（如果不足）
            while active_buy_count < self.max_orders:
                buy_price = self.best_bid * (1 - active_buy_count * self.spread / 10)
                signal = Signal(
                    symbol=self.symbol,
                    direction='BUY',
                    price=buy_price,
                    volume=self.quantity,
                    timestamp=datetime.now(),
                    reason=f'做市买单 #{active_buy_count + 1}'
                )
                self.signals.append(signal)
                active_buy_count += 1
            
            # 补充卖单（如果不足）
            while active_sell_count < self.max_orders:
                sell_price = self.best_ask * (1 + active_sell_count * self.spread / 10)
                signal = Signal(
                    symbol=self.symbol,
                    direction='SELL',
                    price=sell_price,
                    volume=self.quantity,
                    timestamp=datetime.now(),
                    reason=f'做市卖单 #{active_sell_count + 1}'
                )
                self.signals.append(signal)
                active_sell_count += 1
                
        except Exception as e:
            logger.error(f"更新订单失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
    
    def _check_stop_loss_take_profit(self) -> None:
        """检查止损止盈"""
        try:
            # 确保 signals 属性存在
            if not hasattr(self, 'signals'):
                self.signals: List[Signal] = []
            
            # 计算未实现盈亏（如果有持仓）
            if self.position_size != 0:
                if self.position_size > 0:  # 多头
                    self.unrealized_pnl = (self.current_price - self.entry_price) * abs(self.position_size)
                else:  # 空头
                    self.unrealized_pnl = (self.entry_price - self.current_price) * abs(self.position_size)
                
                # 检查止损
                if self.enable_stop_loss and self.unrealized_pnl <= self.stop_loss:
                    logger.warning(f"止损触发: 未实现亏损 {self.unrealized_pnl:.2f} USDC")
                    self._cancel_all_orders()
                    # 平仓信号
                    signal = Signal(
                        symbol=self.symbol,
                        direction='SELL' if self.position_size > 0 else 'BUY',
                        price=self.current_price,
                        volume=abs(self.position_size),
                        timestamp=datetime.now(),
                        reason='止损平仓'
                    )
                    self.signals.append(signal)
                    return
                
                # 检查止盈
                if self.enable_take_profit and self.unrealized_pnl >= self.take_profit:
                    logger.info(f"止盈触发: 未实现盈利 {self.unrealized_pnl:.2f} USDC")
                    self._cancel_all_orders()
                    # 平仓信号
                    signal = Signal(
                        symbol=self.symbol,
                        direction='SELL' if self.position_size > 0 else 'BUY',
                        price=self.current_price,
                        volume=abs(self.position_size),
                        timestamp=datetime.now(),
                        reason='止盈平仓'
                    )
                    self.signals.append(signal)
                    
        except Exception as e:
            logger.error(f"检查止损止盈失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
    
    def _check_rebalance(self) -> None:
        """检查并执行重平衡"""
        try:
            # 确保 signals 属性存在
            if not hasattr(self, 'signals'):
                self.signals: List[Signal] = []
            
            if not self.enable_rebalance:
                return
            
            # 计算当前资产比例
            total_value = self.base_balance * self.current_price + self.quote_balance
            if total_value == 0:
                return
            
            base_asset_ratio = (self.base_balance * self.current_price) / total_value * 100
            target_ratio = self.base_asset_target
            threshold = self.rebalance_threshold
            
            # 检查是否需要重平衡
            deviation = base_asset_ratio - target_ratio
            
            if abs(deviation) > threshold:
                logger.info(f"触发重平衡: 当前比例={base_asset_ratio:.2f}%, 目标={target_ratio:.2f}%, 偏差={deviation:.2f}%")
                
                # 计算需要交易的金额
                target_base_value = total_value * target_ratio / 100
                current_base_value = self.base_balance * self.current_price
                trade_value = abs(target_base_value - current_base_value) / 2  # 分两次调整
                
                if deviation > 0:  # 基础资产过多，需要卖出
                    signal = Signal(
                        symbol=self.symbol,
                        direction='SELL',
                        price=self.current_price,
                        volume=trade_value / self.current_price,
                        timestamp=datetime.now(),
                        reason=f'重平衡: 卖出基础资产（比例过高）'
                    )
                else:  # 基础资产过少，需要买入
                    signal = Signal(
                        symbol=self.symbol,
                        direction='BUY',
                        price=self.current_price,
                        volume=trade_value / self.current_price,
                        timestamp=datetime.now(),
                        reason=f'重平衡: 买入基础资产（比例过低）'
                    )
                
                self.signals.append(signal)
                self.last_rebalance_time = datetime.now()
                
        except Exception as e:
            logger.error(f"检查重平衡失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
    
    def _cancel_all_orders(self) -> None:
        """取消所有订单"""
        try:
            # 这里应该调用交易所API取消订单
            # 示例：self.exchange.cancel_all_orders(self.symbol)
            self.buy_orders = []
            self.sell_orders = []
            self.active_orders = {}
            logger.info("已取消所有订单")
        except Exception as e:
            logger.error(f"取消订单失败: {e}")
    
    def _update_account(self) -> None:
        """更新账户信息"""
        try:
            # 这里应该调用交易所API获取账户信息
            # 示例：
            # account = self.exchange.get_account()
            # self.base_balance = account['base_balance']
            # self.quote_balance = account['quote_balance']
            # positions = self.exchange.get_positions()
            # if positions:
            #     self.position_size = positions[0]['size']
            #     self.entry_price = positions[0]['entry_price']
            pass
        except Exception as e:
            logger.error(f"更新账户信息失败: {e}")
    
    def get_performance(self) -> Dict[str, Any]:
        """获取策略表现"""
        return {
            'total_trades': self.total_trades,
            'total_profit': self.total_profit,
            'unrealized_pnl': self.unrealized_pnl,
            'current_price': self.current_price,
            'position_size': self.position_size,
            'base_balance': self.base_balance,
            'quote_balance': self.quote_balance,
            'active_buy_orders': len([o for o in self.buy_orders if o.get('active', False)]),
            'active_sell_orders': len([o for o in self.sell_orders if o.get('active', False)])
        }

