"""
回测引擎
提供策略回测的核心功能
"""

from abc import ABC, abstractmethod
from typing import Dict, List, Any, Optional, Union
from datetime import datetime, timedelta
from dataclasses import dataclass
import pandas as pd
import numpy as np
import asyncio
import threading
from concurrent.futures import ThreadPoolExecutor

from .strategy import IStrategy, BaseStrategy, MarketData, Signal, Position
from .events import EventEngine, Event, MarketDataEvent, SignalEvent
from utils.logger import get_logger

logger = get_logger(__name__)

@dataclass
class BacktestConfig:
    """回测配置"""
    initial_capital: float = 100000.0
    commission_rate: float = 0.0003
    slippage_rate: float = 0.001
    start_date: datetime = None
    end_date: datetime = None
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            'initial_capital': self.initial_capital,
            'commission_rate': self.commission_rate,
            'slippage_rate': self.slippage_rate,
            'start_date': self.start_date.isoformat() if self.start_date else None,
            'end_date': self.end_date.isoformat() if self.end_date else None
        }

@dataclass
class BacktestResult:
    """回测结果"""
    total_return: float
    annual_return: float
    max_drawdown: float
    sharpe_ratio: float
    win_rate: float
    total_trades: int
    equity_curve: List[Dict[str, Any]]
    trades: List[Dict[str, Any]]
    positions: List[Dict[str, Any]]
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        # 转换交易记录格式以匹配前端期望
        trade_history = []
        for trade in self.trades:
            trade_side = trade.get('side', 'BUY')
            formatted_trade = {
                'timestamp': trade.get('timestamp'),
                'type': 'BUY' if trade_side == 'BUY' else 'CLOSE',  # BUY 开仓, SELL 改为 CLOSE 平仓
                'side': 'LONG',  # 目前只做多，统一为 LONG
                'price': trade.get('price'),
                'quantity': trade.get('size'),  # size -> quantity
                'amount': trade.get('price', 0) * trade.get('size', 0),
                'pnl': trade.get('pnl', 0) if trade_side == 'SELL' else 0,  # 只有平仓才有盈亏
                'commission': trade.get('commission', 0),
                'reason': trade.get('reason', '')
            }
            trade_history.append(formatted_trade)
        
        return {
            'total_return': self.total_return,
            'annual_return': self.annual_return,
            'max_drawdown': self.max_drawdown,
            'sharpe_ratio': self.sharpe_ratio,
            'win_rate': self.win_rate,
            'total_trades': self.total_trades,
            'equity_curve': self.equity_curve,
            'trade_history': trade_history,  # trades -> trade_history
            'trades': self.trades,  # 保留原始数据
            'positions': self.positions
        }

class IBacktestEngine(ABC):
    """回测引擎接口"""
    
    @abstractmethod
    def run(self, strategy: IStrategy, data: pd.DataFrame, config: BacktestConfig) -> BacktestResult:
        """运行回测"""
        pass
    
    @abstractmethod
    def run_async(self, strategy: IStrategy, data: pd.DataFrame, config: BacktestConfig) -> BacktestResult:
        """异步运行回测"""
        pass

class BacktestEngine(IBacktestEngine):
    """回测引擎实现"""
    
    def __init__(self):
        self.event_engine = EventEngine()
        self.running = False
        
        # 回测状态
        self.current_capital = 0.0
        self.available_cash = 0.0
        self.positions: List[Position] = []
        self.trades: List[Dict[str, Any]] = []
        self.equity_curve: List[Dict[str, Any]] = []
        
        logger.info("回测引擎初始化完成")
    
    def run(self, strategy: IStrategy, data: pd.DataFrame, config: BacktestConfig) -> BacktestResult:
        """运行回测"""
        # 初始化回测状态
        self._initialize_backtest(config)
        
        # 注册事件处理器
        self.event_engine.register("market_data", self._handle_market_data_event)
        
        # 启动事件引擎
        self.event_engine.start()
        self.running = True
        
        try:
            # 初始化策略
            strategy.initialize()
            
            # 启动策略
            strategy.start()
            
            # 处理历史数据
            self._process_historical_data(strategy, data, config)
            
            # 停止策略
            strategy.stop()
            
            # 计算回测结果
            result = self._calculate_results(strategy, config)
            
            logger.info(f"回测完成: 总交易数={len(self.trades)}, 总收益率={result.total_return:.2%}")
            return result
            
        except Exception as e:
            logger.error(f"回测执行异常: {e}")
            logger.error(f"堆栈: {traceback.format_exc()}")
            raise
        finally:
            # 停止事件引擎
            self.event_engine.stop()
            self.running = False
    
    async def run_async(self, strategy: IStrategy, data: pd.DataFrame, config: BacktestConfig) -> BacktestResult:
        """异步运行回测"""
        logger.info("开始异步回测...")
        
        # 在线程池中运行回测
        loop = asyncio.get_event_loop()
        with ThreadPoolExecutor() as executor:
            result = await loop.run_in_executor(executor, self.run, strategy, data, config)
        
        logger.info("异步回测完成")
        return result
    
    def _initialize_backtest(self, config: BacktestConfig) -> None:
        """初始化回测状态"""
        self.current_capital = config.initial_capital
        self.available_cash = config.initial_capital
        self.positions = []
        self.trades = []
        self.equity_curve = []
        
        # 添加初始权益曲线点
        initial_timestamp = config.start_date or datetime.now()
        if isinstance(initial_timestamp, str):
            initial_timestamp = pd.to_datetime(initial_timestamp)
        
        # 确保时间戳不为None
        if initial_timestamp is None:
            initial_timestamp = datetime.now()
        
        self.equity_curve.append({
            'timestamp': initial_timestamp.isoformat() if hasattr(initial_timestamp, 'isoformat') else str(initial_timestamp),
            'equity': float(config.initial_capital),
            'cash': float(config.initial_capital),
            'positions_value': 0.0
        })
        
        logger.info(f"初始化回测: 初始资金 {config.initial_capital}")
    
    def _process_historical_data(self, strategy: IStrategy, data: pd.DataFrame, config: BacktestConfig) -> None:
        """处理历史数据"""
        total_bars = len(data)
        
        if total_bars == 0:
            logger.warning("数据为空，跳过回测")
            return
        
        logger.info(f"开始处理历史数据，共 {total_bars} 条")
        
        for i, (timestamp, row) in enumerate(data.iterrows()):
            try:
                # 创建市场数据
                # 使用策略的 symbol，而不是数据中的 symbol
                strategy_symbol = strategy.symbol if hasattr(strategy, 'symbol') else 'BTCUSDT'
                market_data = MarketData(
                    symbol=strategy_symbol,
                    timestamp=timestamp,
                    open=row['open'],
                    high=row['high'],
                    low=row['low'],
                    close=row['close'],
                    volume=row['volume']
                )
                
                # 发送市场数据事件
                event = MarketDataEvent(
                    symbol=market_data.symbol,
                    data=market_data.to_dict(),
                    timestamp=timestamp
                )
                self.event_engine.put(event)
                
                # 处理策略 - on_data 会自动更新价格数据并调用 on_market_data
                strategy.on_data(market_data)
                
                # 处理交易信号
                self._process_signals(strategy, market_data, config)
                
                # 更新账户
                self._update_account(market_data)
                
                # 更新权益曲线
                self._update_equity_curve(timestamp)
                
                # 进度显示
                if (i + 1) % 100 == 0 or i == total_bars - 1:
                    progress = (i + 1) / total_bars * 100
                    logger.info(f"回测进度: {progress:.1f}% ({i+1}/{total_bars})")
                    
            except Exception as e:
                logger.error(f"处理第 {i+1} 条数据时异常: {e}")
                # 继续处理下一条数据
                continue
    
    def _handle_market_data_event(self, event: Event) -> None:
        """处理市场数据事件"""
        try:
            # 从事件中提取市场数据
            if event.type == "market_data" and "data" in event.data:
                market_data_dict = event.data["data"]
                
                # 创建MarketData对象
                market_data = MarketData(
                    symbol=market_data_dict.get("symbol", "BTCUSDT"),
                    timestamp=market_data_dict.get("timestamp"),
                    open=market_data_dict.get("open", 0.0),
                    high=market_data_dict.get("high", 0.0),
                    low=market_data_dict.get("low", 0.0),
                    close=market_data_dict.get("close", 0.0),
                    volume=market_data_dict.get("volume", 0.0)
                )
                
                # 更新权益曲线
                self._update_equity_curve(market_data.timestamp)
                
                logger.debug(f"处理市场数据事件: {market_data.symbol} @ {market_data.close}")
                
        except Exception as e:
            logger.error(f"处理市场数据事件失败: {e}")
    
    def _process_signals(self, strategy: IStrategy, market_data: MarketData, config: BacktestConfig) -> None:
        """处理交易信号"""
        signals = strategy.get_signals()
        
        for signal in signals:
            if signal.direction == 'BUY':
                logger.info(f"执行买入订单: {signal.symbol} @ {signal.price:.2f}, volume={signal.volume}")
                self._execute_buy_order(signal, market_data, config)
            elif signal.direction == 'SELL':
                logger.info(f"执行卖出订单: {signal.symbol} @ {signal.price:.2f}, volume={signal.volume}")
                self._execute_sell_order(signal, market_data, config)
    
    def _execute_buy_order(self, signal: Signal, market_data: MarketData, config: BacktestConfig) -> None:
        """执行买入订单"""
        # 计算可买入数量
        available_cash = self.available_cash
        if available_cash <= 0:
            logger.debug(f"买入失败: 可用资金不足 (available_cash={available_cash})")
            return
        
        # 计算买入价格（考虑滑点）
        buy_price = market_data.close * (1 + config.slippage_rate)
        
        # 计算买入数量
        max_volume = available_cash / buy_price
        volume = min(signal.volume, max_volume)
        
        if volume <= 0:
            logger.debug(f"买入失败: 计算数量<=0 (volume={volume})")
            return
        
        # 计算手续费
        commission = buy_price * volume * config.commission_rate
        total_cost = buy_price * volume + commission
        
        if total_cost > available_cash:
            logger.debug(f"买入失败: 资金不足 (total_cost={total_cost:.2f} > available_cash={available_cash:.2f})")
            return
        
        # 执行交易
        self.available_cash -= total_cost
        
        # 创建持仓
        position = Position(
            symbol=signal.symbol,
            side='LONG',
            size=volume,
            entry_price=buy_price,
            entry_time=market_data.timestamp
        )
        self.positions.append(position)
        
        # 记录交易
        trade = {
            'symbol': signal.symbol or '',
            'side': 'BUY',  # 改为 BUY 更清晰
            'size': float(volume),
            'price': float(buy_price),
            'commission': float(commission),
            'timestamp': market_data.timestamp.isoformat() if hasattr(market_data.timestamp, 'isoformat') else str(market_data.timestamp),
            'reason': signal.reason or ''
        }
        self.trades.append(trade)
        
        logger.info(f"✅ 买入成功: {signal.symbol} 数量={volume:.4f} @ {buy_price:.2f}, 手续费={commission:.2f}, 剩余资金={self.available_cash:.2f}")
    
    def _execute_sell_order(self, signal: Signal, market_data: MarketData, config: BacktestConfig) -> None:
        """执行卖出订单"""
        # 查找对应持仓
        position = None
        for pos in self.positions:
            if pos.symbol == signal.symbol and pos.side == 'LONG':
                position = pos
                break
        
        if not position:
            logger.debug(f"卖出失败: 没有对应的持仓 (symbol={signal.symbol})")
            return
        
        # 计算卖出数量
        volume = min(signal.volume, position.size)
        if volume <= 0:
            logger.debug(f"卖出失败: 计算数量<=0 (volume={volume})")
            return
        
        # 计算卖出价格（考虑滑点）
        sell_price = market_data.close * (1 - config.slippage_rate)
        
        # 计算手续费
        commission = sell_price * volume * config.commission_rate
        net_proceeds = sell_price * volume - commission
        
        # 执行交易
        self.available_cash += net_proceeds
        
        # 更新持仓
        position.size -= volume
        if position.size <= 0:
            self.positions.remove(position)
        
        # 计算盈亏
        pnl = (sell_price - position.entry_price) * volume - commission
        
        # 记录交易
        trade = {
            'symbol': signal.symbol or '',
            'side': 'SELL',
            'size': float(volume),
            'price': float(sell_price),
            'commission': float(commission),
            'pnl': float(pnl),
            'timestamp': market_data.timestamp.isoformat() if hasattr(market_data.timestamp, 'isoformat') else str(market_data.timestamp),
            'reason': signal.reason or '',
            'entry_price': float(position.entry_price)  # 添加买入价格以便前端显示
        }
        self.trades.append(trade)
        
        logger.info(f"✅ 卖出成功: {signal.symbol} 数量={volume:.4f} @ {sell_price:.2f}, 手续费={commission:.2f}, 盈亏={pnl:.2f}, 剩余资金={self.available_cash:.2f}")
    
    def _update_account(self, market_data: MarketData) -> None:
        """更新账户"""
        # 更新持仓价格
        for position in self.positions:
            position.update_price(market_data.close)
        
        # 计算总权益
        total_equity = self.available_cash
        for position in self.positions:
            total_equity += position.size * market_data.close
        
        self.current_capital = total_equity
    
    def _update_equity_curve(self, timestamp: datetime) -> None:
        """更新权益曲线"""
        # 确保时间戳类型一致
        if isinstance(timestamp, str):
            timestamp = pd.to_datetime(timestamp)
        
        # 确保数值不为None或NaN
        equity = self.current_capital if self.current_capital is not None else 0.0
        cash = self.available_cash if self.available_cash is not None else 0.0
        positions_value = equity - cash if equity is not None and cash is not None else 0.0
        
        # 确保时间戳不为None
        if timestamp is None:
            timestamp = datetime.now()
        
        self.equity_curve.append({
            'timestamp': timestamp.isoformat() if hasattr(timestamp, 'isoformat') else str(timestamp),
            'equity': float(equity),
            'cash': float(cash),
            'positions_value': float(positions_value)
        })
    
    def _calculate_results(self, strategy: IStrategy, config: BacktestConfig) -> BacktestResult:
        """计算回测结果"""
        logger.info(f"计算回测结果: 权益曲线点数={len(self.equity_curve)}, 交易数={len(self.trades)}, 持仓数={len(self.positions)}")
        
        if not self.equity_curve:
            logger.warning("权益曲线为空，返回默认结果")
            # 创建默认的权益曲线数据
            default_equity_curve = [{
                'timestamp': datetime.now().isoformat(),
                'equity': float(config.initial_capital),
                'cash': float(config.initial_capital),
                'positions_value': 0.0
            }]
            return BacktestResult(0, 0, 0, 0, 0, 0, default_equity_curve, [], [])
        
        # 计算基本指标
        initial_equity = self.equity_curve[0]['equity']
        final_equity = self.equity_curve[-1]['equity']
        total_return = (final_equity - initial_equity) / initial_equity
        
        logger.info(f"回测指标: 初始资金={initial_equity}, 最终资金={final_equity}, 总收益率={total_return:.4f}")
        
        # 计算年化收益率
        start_date = self.equity_curve[0]['timestamp']
        end_date = self.equity_curve[-1]['timestamp']
        
        # 确保时间戳类型一致
        if isinstance(start_date, str):
            start_date = pd.to_datetime(start_date)
        if isinstance(end_date, str):
            end_date = pd.to_datetime(end_date)
        
        days = (end_date - start_date).days
        annual_return = (1 + total_return) ** (365 / days) - 1 if days > 0 else 0
        
        # 计算最大回撤
        max_drawdown = self._calculate_max_drawdown()
        
        # 计算夏普比率
        sharpe_ratio = self._calculate_sharpe_ratio()
        
        # 计算胜率
        winning_trades = sum(1 for trade in self.trades if trade.get('pnl', 0) > 0)
        total_trades = len(self.trades)
        win_rate = winning_trades / total_trades if total_trades > 0 else 0
        
        # 转换持仓数据
        positions_data = []
        for position in self.positions:
            positions_data.append({
                'symbol': position.symbol or '',
                'side': position.side or '',
                'size': float(position.size) if position.size is not None else 0.0,
                'entry_price': float(position.entry_price) if position.entry_price is not None else 0.0,
                'current_price': float(position.current_price) if position.current_price is not None else 0.0,
                'unrealized_pnl': float(position.unrealized_pnl) if position.unrealized_pnl is not None else 0.0,
                'entry_time': position.entry_time.isoformat() if hasattr(position.entry_time, 'isoformat') else str(position.entry_time)
            })
        
        # 确保权益曲线数据格式正确
        formatted_equity_curve = []
        for point in self.equity_curve:
            formatted_point = {
                'timestamp': point['timestamp'].isoformat() if hasattr(point['timestamp'], 'isoformat') else str(point['timestamp']),
                'equity': float(point['equity']) if point['equity'] is not None else 0.0,
                'cash': float(point['cash']) if point['cash'] is not None else 0.0,
                'positions_value': float(point['positions_value']) if point['positions_value'] is not None else 0.0
            }
            formatted_equity_curve.append(formatted_point)
        
        return BacktestResult(
            total_return=total_return,
            annual_return=annual_return,
            max_drawdown=max_drawdown,
            sharpe_ratio=sharpe_ratio,
            win_rate=win_rate,
            total_trades=total_trades,
            equity_curve=formatted_equity_curve,
            trades=self.trades,
            positions=positions_data
        )
    
    def _calculate_max_drawdown(self) -> float:
        """计算最大回撤"""
        if not self.equity_curve:
            return 0.0
        
        peak = self.equity_curve[0]['equity']
        max_drawdown = 0.0
        
        for point in self.equity_curve:
            if point['equity'] > peak:
                peak = point['equity']
            drawdown = (peak - point['equity']) / peak
            if drawdown > max_drawdown:
                max_drawdown = drawdown
        
        return max_drawdown
    
    def _calculate_sharpe_ratio(self) -> float:
        """计算夏普比率"""
        if len(self.equity_curve) < 2:
            return 0.0
        
        # 计算收益率序列
        returns = []
        for i in range(1, len(self.equity_curve)):
            prev_equity = self.equity_curve[i-1]['equity']
            curr_equity = self.equity_curve[i]['equity']
            ret = (curr_equity - prev_equity) / prev_equity
            returns.append(ret)
        
        if not returns:
            return 0.0
        
        mean_return = np.mean(returns)
        std_return = np.std(returns)
        
        if std_return == 0:
            return 0.0
        
        return mean_return / std_return * np.sqrt(252)
