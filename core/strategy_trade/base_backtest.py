"""
回测基类
提供统一的回测引擎接口
"""

from abc import ABC, abstractmethod
from typing import Dict, List, Any, Optional
from datetime import datetime
import pandas as pd

from .base_strategy import BaseStrategy, MarketData, Signal, Position
from utils.logger import get_logger

logger = get_logger(__name__)


class BaseBacktest(ABC):
    """
    回测基类
    
    所有回测引擎必须继承此类并实现：
    - run: 执行回测
    """
    
    def __init__(self, strategy: BaseStrategy, initial_capital: float = 100000.0):
        """
        初始化回测引擎
        
        Args:
            strategy: 策略实例
            initial_capital: 初始资金
        """
        self.strategy = strategy
        self.initial_capital = initial_capital
        
        # 回测状态
        self.current_capital = initial_capital
        self.cash = initial_capital  # 现金
        self.equity = 0.0  # 持仓市值
        
        # 回测记录
        self.trades: List[Dict[str, Any]] = []
        self.equity_curve: List[Dict[str, Any]] = []
        
        # 统计信息
        self.total_return = 0.0
        self.max_drawdown = 0.0
        self.sharpe_ratio = 0.0
        
        logger.info(f"回测引擎初始化: 初始资金={initial_capital:.2f}")
    
    @abstractmethod
    def run(self, data: pd.DataFrame) -> Dict[str, Any]:
        """
        执行回测（必须实现）
        
        Args:
            data: 历史数据DataFrame，包含列：timestamp, open, high, low, close, volume
            
        Returns:
            回测结果字典
        """
        pass
    
    def execute_signal(self, signal: Signal, current_price: float) -> bool:
        """
        执行交易信号
        
        Args:
            signal: 交易信号
            current_price: 当前价格
            
        Returns:
            是否执行成功
        """
        if signal.direction == 'HOLD':
            return False
        
        try:
            if signal.direction == 'BUY':
                return self._execute_buy(signal, current_price)
            elif signal.direction == 'SELL':
                return self._execute_sell(signal, current_price)
        except Exception as e:
            logger.error(f"执行信号失败: {e}")
            return False
    
    def _execute_buy(self, signal: Signal, current_price: float) -> bool:
        """执行买入"""
        cost = signal.price * signal.volume
        
        if cost > self.cash:
            logger.warning(f"资金不足，无法买入: 需要{cost:.2f}, 当前{self.cash:.2f}")
            return False
        
        # 扣除现金，增加持仓
        self.cash -= cost
        
        # 记录持仓
        position = Position(
            symbol=signal.symbol,
            side='LONG',
            size=signal.volume,
            entry_price=signal.price,
            entry_time=signal.timestamp,
            current_price=signal.price
        )
        self.strategy.add_position(position)
        
        # 记录交易
        self.trades.append({
            'timestamp': signal.timestamp,
            'direction': 'BUY',
            'price': signal.price,
            'volume': signal.volume,
            'cost': cost,
            'cash_before': self.cash + cost,
            'cash_after': self.cash
        })
        
        logger.debug(f"买入: {signal.volume:.4f} @ {signal.price:.4f}, 花费: {cost:.2f}")
        return True
    
    def _execute_sell(self, signal: Signal, current_price: float) -> bool:
        """执行卖出"""
        # 查找对应的持仓
        position = None
        for pos in self.strategy.positions:
            if pos.symbol == signal.symbol and pos.side == 'LONG':
                if pos.size >= signal.volume:
                    position = pos
                    break
        
        if not position:
            logger.warning(f"无足够持仓，无法卖出: 需要{signal.volume:.4f}")
            return False
        
        # 计算收益
        revenue = signal.price * signal.volume
        cost = position.entry_price * signal.volume
        pnl = revenue - cost
        
        # 增加现金
        self.cash += revenue
        
        # 更新持仓
        position.size -= signal.volume
        if position.size <= 0.0001:  # 浮点数误差处理
            self.strategy.remove_position(signal.symbol, 'LONG')
        
        # 记录交易
        self.trades.append({
            'timestamp': signal.timestamp,
            'direction': 'SELL',
            'price': signal.price,
            'volume': signal.volume,
            'revenue': revenue,
            'cost': cost,
            'pnl': pnl,
            'cash_before': self.cash - revenue,
            'cash_after': self.cash
        })
        
        # 记录策略收益
        self.strategy.record_trade(pnl)
        
        logger.debug(f"卖出: {signal.volume:.4f} @ {signal.price:.4f}, 收益: {pnl:.2f}")
        return True
    
    def calculate_equity(self, current_price: float) -> float:
        """计算总权益"""
        self.equity = 0.0
        for position in self.strategy.positions:
            position.update_price(current_price)
            self.equity += position.size * current_price
        
        return self.cash + self.equity
    
    def record_equity(self, timestamp: datetime, current_price: float):
        """记录权益曲线"""
        total_equity = self.calculate_equity(current_price)
        self.equity_curve.append({
            'timestamp': timestamp,
            'price': current_price,
            'cash': self.cash,
            'equity': self.equity,
            'total_equity': total_equity,
            'return': (total_equity - self.initial_capital) / self.initial_capital
        })
    
    def get_results(self) -> Dict[str, Any]:
        """获取回测结果"""
        if not self.equity_curve:
            return {
                'total_return': 0.0,
                'max_drawdown': 0.0,
                'total_trades': 0,
                'win_rate': 0.0
            }
        
        final_equity = self.equity_curve[-1]['total_equity']
        self.total_return = (final_equity - self.initial_capital) / self.initial_capital
        
        # 计算最大回撤
        peak = self.initial_capital
        self.max_drawdown = 0.0
        for point in self.equity_curve:
            equity = point['total_equity']
            if equity > peak:
                peak = equity
            drawdown = (peak - equity) / peak
            if drawdown > self.max_drawdown:
                self.max_drawdown = drawdown
        
        # 计算胜率
        winning_trades = sum(1 for t in self.trades if t.get('pnl', 0) > 0)
        win_rate = winning_trades / len(self.trades) if self.trades else 0.0
        
        return {
            'total_return': self.total_return,
            'max_drawdown': self.max_drawdown,
            'total_trades': len(self.trades),
            'winning_trades': winning_trades,
            'win_rate': win_rate,
            'final_capital': final_equity,
            'initial_capital': self.initial_capital,
            'total_pnl': final_equity - self.initial_capital,
            'equity_curve': self.equity_curve[-100:]  # 只返回最近100个点
        }

