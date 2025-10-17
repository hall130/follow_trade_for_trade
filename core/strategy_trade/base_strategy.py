from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass
from datetime import datetime
import pandas as pd
import numpy as np
import asyncio
from utils.logger import get_logger

logger = get_logger(__name__)

@dataclass
class TradingSignal:
    """交易信号"""
    symbol: str
    action: str  # 'BUY', 'SELL', 'HOLD', 'CLOSE'
    price: float
    quantity: float
    timestamp: datetime
    confidence: float = 1.0
    strategy_name: str = ""
    metadata: Dict[str, Any] = None
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    signal_strength: float = 1.0  # 信号强度 0-1

@dataclass
class Position:
    """持仓信息"""
    symbol: str
    side: str  # 'LONG', 'SHORT'
    quantity: float
    entry_price: float
    current_price: float
    unrealized_pnl: float
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    entry_time: datetime = None
    metadata: Optional[Dict[str, Any]] = None
    
    def __init__(self, symbol: str, side: str, quantity: float, entry_price: float, 
                 current_price: float = None, stop_loss: float = None, 
                 take_profit: float = None, entry_time: datetime = None, 
                 metadata: Dict[str, Any] = None):
        self.symbol = symbol
        self.side = side
        self.quantity = quantity
        self.entry_price = entry_price
        self.current_price = current_price or entry_price
        self.unrealized_pnl = 0.0
        self.stop_loss = stop_loss
        self.take_profit = take_profit
        self.entry_time = entry_time or datetime.now()
        self.metadata = metadata or {}

class BaseStrategy(ABC):
    """策略基类"""
    
    def __init__(self, name: str, config: Dict[str, Any]):
        self.name = name
        self.config = config
        self.is_active = False
        self.positions: Dict[str, Position] = {}
        self.performance = {
            'total_trades': 0,
            'winning_trades': 0,
            'losing_trades': 0,
            'total_pnl': 0.0,
            'realized_pnl': 0.0,
            'unrealized_pnl': 0.0,
            'max_drawdown': 0.0,
            'sharpe_ratio': 0.0,
            'max_consecutive_losses': 0,
            'current_consecutive_losses': 0,
            'profit_factor': 0.0,
            'average_win': 0.0,
            'average_loss': 0.0,
            'max_single_loss': 0.0,
            'max_single_win': 0.0
        }
        self.trade_history = []
        self.last_signal_time = None
        self.risk_manager = RiskManager(config.get('risk_config', {}))
        
        # 策略参数
        self.symbol = config.get('symbol', 'BTC-USDT')
        self.timeframe = config.get('timeframe', '1h')
        self.max_positions = config.get('max_positions', 3)
        self.position_sizing = config.get('position_sizing', 'fixed')  # fixed, kelly, martingale
    
    @abstractmethod
    def generate_signals(self, data: pd.DataFrame) -> List[TradingSignal]:
        """生成交易信号 - 子类必须实现"""
        pass
    
    @abstractmethod
    def should_exit_position(self, position: Position, current_data: pd.DataFrame) -> bool:
        """判断是否应该退出持仓 - 子类必须实现"""
        pass

    def calculate_position_size(self, signal: TradingSignal, account_balance: float) -> float:
        """计算仓位大小"""
        try:
            if self.position_sizing == 'fixed':
                risk_per_trade = self.config.get('risk_per_trade', 0.02)  # 默认2%风险
                position_value = account_balance * risk_per_trade
                return position_value / signal.price
            elif self.position_sizing == 'kelly':
                # Kelly公式计算仓位
                win_rate = self.performance.get('win_rate', 0.5)
                avg_win = self.performance.get('average_win', 0.01)
                avg_loss = self.performance.get('average_loss', 0.01)
                if avg_loss > 0:
                    kelly_fraction = (win_rate * avg_win - (1 - win_rate) * avg_loss) / avg_win
                    kelly_fraction = max(0, min(kelly_fraction, 0.25))  # 限制最大仓位25%
                    return account_balance * kelly_fraction / signal.price
                else:
                    return self.calculate_position_size_fixed(signal, account_balance)
            elif self.position_sizing == 'volatility_adjusted':
                # 基于波动率调整仓位
                atr = self.config.get('atr', 0.02)  # 平均真实波幅
                volatility_factor = max(0.5, min(2.0, 0.02 / atr))  # 波动率调整因子
                risk_per_trade = self.config.get('risk_per_trade', 0.02) * volatility_factor
                position_value = account_balance * risk_per_trade
                return position_value / signal.price
            else:
                return self.calculate_position_size_fixed(signal, account_balance)
        except Exception as e:
            logger.error(f"计算仓位大小失败: {e}")
            return self.calculate_position_size_fixed(signal, account_balance)
    
    def calculate_position_size_fixed(self, signal: TradingSignal, account_balance: float) -> float:
        """固定比例仓位计算"""
        risk_per_trade = self.config.get('risk_per_trade', 0.02)
        position_value = account_balance * risk_per_trade
        return position_value / signal.price
    
    def validate_signal(self, signal: TradingSignal) -> bool:
        """验证信号有效性"""
        basic_validation = (
            signal.action in ['BUY', 'SELL', 'HOLD', 'CLOSE'] and
            signal.price > 0 and
            signal.quantity > 0 and
            0 <= signal.confidence <= 1
        )
        
        if not basic_validation:
            return False
        
        # 检查是否已有相同方向的持仓
        if signal.action == 'BUY' and self.has_long_position(signal.symbol):
            return False
        if signal.action == 'SELL' and self.has_short_position(signal.symbol):
            return False
        
        # 检查风险限制
        return self.risk_manager.validate_signal(signal)
    
    def has_long_position(self, symbol: str) -> bool:
        """检查是否有做多持仓"""
        return symbol in self.positions and self.positions[symbol].side == 'LONG'
    
    def has_short_position(self, symbol: str) -> bool:
        """检查是否有做空持仓"""
        return symbol in self.positions and self.positions[symbol].side == 'SHORT'
    
    def open_position(self, signal: TradingSignal, current_price: float):
        """开仓"""
        if len(self.positions) >= self.max_positions:
            return False
        
        position = Position(
            symbol=signal.symbol,
            side='LONG' if signal.action == 'BUY' else 'SHORT',
            quantity=signal.quantity,
            entry_price=current_price,
            current_price=current_price,
            stop_loss=signal.stop_loss,
            take_profit=signal.take_profit,
            entry_time=datetime.now(),
            metadata=signal.metadata or {}
        )
        
        self.positions[signal.symbol] = position
        return True
    
    def close_position(self, symbol: str, current_price: float, reason: str = "manual"):
        """平仓"""
        if symbol not in self.positions:
            return False
        
        position = self.positions[symbol]
        exit_price = current_price
        
        # 计算盈亏
        if position.side == 'LONG':
            pnl = (exit_price - position.entry_price) * position.quantity
        else:
            pnl = (position.entry_price - exit_price) * position.quantity
        
        # 记录交易历史
        trade_record = {
            'symbol': symbol,
            'side': position.side,
            'entry_price': position.entry_price,
            'exit_price': exit_price,
            'quantity': position.quantity,
            'pnl': pnl,
            'entry_time': position.entry_time,
            'exit_time': datetime.now(),
            'reason': reason,
            'strategy': self.name
        }
        
        self.trade_history.append(trade_record)
        
        # 更新性能统计
        self.update_performance({'pnl': pnl})
        
        # 移除持仓
        del self.positions[symbol]
        return True
    
    def update_performance(self, trade_result: Dict[str, Any]):
        """更新策略性能"""
        self.performance['total_trades'] += 1
        pnl = trade_result.get('pnl', 0)
        
        if pnl > 0:
            self.performance['winning_trades'] += 1
            self.performance['current_consecutive_losses'] = 0
            self.performance['max_single_win'] = max(self.performance['max_single_win'], pnl)
        else:
            self.performance['losing_trades'] += 1
            self.performance['current_consecutive_losses'] += 1
            self.performance['max_consecutive_losses'] = max(
                self.performance['max_consecutive_losses'],
                self.performance['current_consecutive_losses']
            )
            self.performance['max_single_loss'] = min(self.performance['max_single_loss'], pnl)
        
        self.performance['total_pnl'] += pnl
        self.performance['realized_pnl'] += pnl
        
        # 更新胜率
        if self.performance['total_trades'] > 0:
            self.performance['win_rate'] = self.performance['winning_trades'] / self.performance['total_trades']
        
        # 更新平均盈亏
        if self.performance['winning_trades'] > 0:
            total_wins = sum([t.get('pnl', 0) for t in self.trade_history if t.get('pnl', 0) > 0])
            self.performance['average_win'] = total_wins / self.performance['winning_trades']
        
        if self.performance['losing_trades'] > 0:
            total_losses = sum([t.get('pnl', 0) for t in self.trade_history if t.get('pnl', 0) < 0])
            self.performance['average_loss'] = total_losses / self.performance['losing_trades']
        
        # 更新最大回撤
        if self.performance['total_pnl'] < 0:
            self.performance['max_drawdown'] = min(
                self.performance['max_drawdown'],
                self.performance['total_pnl']
            )
        
        # 计算盈亏因子
        if abs(self.performance['average_loss']) > 0:
            self.performance['profit_factor'] = abs(self.performance['average_win'] / self.performance['average_loss'])
        
        # 计算夏普比率（简化版）
        if len(self.trade_history) > 1:
            returns = [t.get('pnl', 0) for t in self.trade_history[-30:]]  # 最近30次交易
            if len(returns) > 1:
                mean_return = np.mean(returns)
                std_return = np.std(returns)
                if std_return > 0:
                    self.performance['sharpe_ratio'] = mean_return / std_return
    
    def get_performance_summary(self) -> Dict[str, Any]:
        """获取策略性能摘要"""
        total_trades = self.performance['total_trades']
        if total_trades == 0:
            return {
                'strategy_name': self.name,
                'is_active': self.is_active,
                'total_trades': 0,
                'winning_trades': 0,
                'win_rate': 0.0,
                'total_pnl': 0.0,
                'realized_pnl': 0.0,
                'unrealized_pnl': 0.0,
                'max_drawdown': 0.0,
                'profit_factor': 0.0,
                'sharpe_ratio': 0.0,
                'max_consecutive_losses': 0,
                'current_consecutive_losses': 0
            }
        
        win_rate = (self.performance['winning_trades'] / total_trades * 100)
        
        return {
            'strategy_name': self.name,
            'is_active': self.is_active,
            'total_trades': total_trades,
            'winning_trades': self.performance['winning_trades'],
            'losing_trades': self.performance['losing_trades'],
            'win_rate': round(win_rate, 2),
            'total_pnl': round(self.performance['total_pnl'], 2),
            'realized_pnl': round(self.performance['realized_pnl'], 2),
            'unrealized_pnl': round(self.performance['unrealized_pnl'], 2),
            'max_drawdown': round(self.performance['max_drawdown'], 2),
            'profit_factor': round(self.performance['profit_factor'], 2),
            'sharpe_ratio': round(self.performance['sharpe_ratio'], 2),
            'max_consecutive_losses': self.performance['max_consecutive_losses'],
            'current_consecutive_losses': self.performance['current_consecutive_losses'],
            'average_win': round(self.performance['average_win'], 2),
            'average_loss': round(self.performance['average_loss'], 2),
            'max_single_win': round(self.performance['max_single_win'], 2),
            'max_single_loss': round(self.performance['max_single_loss'], 2)
        }
    
    def should_generate_signal(self, current_time: datetime) -> bool:
        """检查是否应该生成信号（避免频繁交易）"""
        if self.last_signal_time is None:
            return True
        
        min_interval = self.config.get('min_signal_interval', 300)  # 默认5分钟
        return (current_time - self.last_signal_time).total_seconds() >= min_interval
    
    def set_last_signal_time(self, signal_time: datetime):
        """设置最后信号时间"""
        self.last_signal_time = signal_time
    
    def update_positions(self, current_data: pd.DataFrame):
        """更新持仓状态"""
        for symbol, position in list(self.positions.items()):
            if symbol in current_data.index:
                current_price = current_data.loc[symbol, 'close']
                position.current_price = current_price
                
                # 计算未实现盈亏
                if position.side == 'LONG':
                    position.unrealized_pnl = (current_price - position.entry_price) * position.quantity
                else:
                    position.unrealized_pnl = (position.entry_price - current_price) * position.quantity
                
                # 检查止损止盈
                if self.should_exit_position(position, current_data):
                    self.close_position(symbol, current_price, "stop_loss_or_take_profit")
    
    def get_current_positions(self) -> List[Dict[str, Any]]:
        """获取当前持仓信息"""
        positions = []
        for symbol, position in self.positions.items():
            positions.append({
                'symbol': position.symbol,
                'side': position.side,
                'quantity': position.quantity,
                'entry_price': position.entry_price,
                'current_price': position.current_price,
                'unrealized_pnl': position.unrealized_pnl,
                'entry_time': position.entry_time.isoformat() if position.entry_time else None
            })
        return positions

class RiskManager:
    """增强版风险管理器"""
    
    def __init__(self, config: Dict[str, Any]):
        self.max_daily_loss = config.get('max_daily_loss', 0.05)  # 最大日亏损5%
        self.max_position_size = config.get('max_position_size', 0.1)  # 最大单笔仓位10%
        self.max_correlation = config.get('max_correlation', 0.7)  # 最大相关性
        self.max_drawdown = config.get('max_drawdown', 0.2)  # 最大回撤20%
        self.max_leverage = config.get('max_leverage', 1.0)  # 最大杠杆倍数
        self.max_concentration = config.get('max_concentration', 0.3)  # 最大持仓集中度
        
        self.daily_loss = 0.0
        self.reset_date = datetime.now().date()
        self.position_count = 0
        self.total_exposure = 0.0
        
        # 风险限制历史
        self.risk_violations = []
        
    def validate_signal(self, signal: TradingSignal, current_portfolio_value: float = 100000) -> bool:
        """验证信号是否符合风险要求"""
        try:
            # 检查日亏损限制
            current_date = datetime.now().date()
            if current_date != self.reset_date:
                self.daily_loss = 0.0
                self.reset_date = current_date
            
            if self.daily_loss <= -self.max_daily_loss * current_portfolio_value:
                self._record_violation("daily_loss_limit", self.daily_loss, -self.max_daily_loss * current_portfolio_value)
                return False
            
            # 检查单笔仓位大小
            position_size = signal.price * signal.quantity
            position_ratio = position_size / current_portfolio_value
            if position_ratio > self.max_position_size:
                self._record_violation("position_size_limit", position_ratio, self.max_position_size)
                return False
            
            # 检查总敞口
            if (self.total_exposure + position_size) / current_portfolio_value > self.max_leverage:
                self._record_violation("leverage_limit", (self.total_exposure + position_size) / current_portfolio_value, self.max_leverage)
                return False
            
            return True
        except Exception as e:
            logger.error(f"风险验证失败: {e}")
            return False
    
    def update_daily_loss(self, pnl: float):
        """更新日亏损"""
        self.daily_loss += pnl
    
    def update_exposure(self, position_change: float):
        """更新总敞口"""
        self.total_exposure += position_change
        self.total_exposure = max(0, self.total_exposure)  # 确保不为负数
    
    def _record_violation(self, violation_type: str, current_value: float, limit_value: float):
        """记录风险违规"""
        violation = {
            'type': violation_type,
            'timestamp': datetime.now(),
            'current_value': current_value,
            'limit_value': limit_value,
            'severity': self._calculate_severity(current_value, limit_value)
        }
        self.risk_violations.append(violation)
        logger.warning(f"风险违规: {violation}")
    
    def _calculate_severity(self, current: float, limit: float) -> str:
        """计算违规严重程度"""
        ratio = abs(current) / abs(limit) if limit != 0 else float('inf')
        if ratio > 2:
            return 'CRITICAL'
        elif ratio > 1.5:
            return 'HIGH'
        elif ratio > 1.2:
            return 'MEDIUM'
        else:
            return 'LOW'
    
    def get_risk_report(self) -> Dict[str, Any]:
        """获取风险报告"""
        return {
            'daily_loss': self.daily_loss,
            'max_daily_loss_limit': self.max_daily_loss,
            'total_exposure': self.total_exposure,
            'max_leverage': self.max_leverage,
            'recent_violations': self.risk_violations[-10:],  # 最近10次违规
            'risk_utilization': {
                'daily_loss_usage': abs(self.daily_loss) / abs(self.max_daily_loss) if self.max_daily_loss != 0 else 0,
                'leverage_usage': self.total_exposure / self.max_leverage if self.max_leverage != 0 else 0
            }
        }