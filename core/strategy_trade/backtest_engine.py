"""
策略回测引擎
提供完整的策略历史数据回测功能和性能分析
"""

import asyncio
import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime, timedelta
import json
from decimal import Decimal

from .base_strategy import BaseStrategy, TradingSignal, Position
from .strategy_db import StrategyDB
from utils.logger import get_logger

logger = get_logger(__name__)

class BacktestEngine:
    """策略回测引擎"""
    
    def __init__(self, strategy: BaseStrategy, initial_capital: float = 100000):
        self.strategy = strategy
        self.initial_capital = initial_capital
        self.current_capital = initial_capital
        self.available_cash = initial_capital
        self.backtest_name = None  # 回测名称，稍后设置
        
        # 回测状态
        self.positions = {}
        self.trade_history = []
        self.equity_curve = []
        self.drawdown_series = []
        
        # 性能统计
        self.performance_stats = {
            'total_trades': 0,
            'winning_trades': 0,
            'losing_trades': 0,
            'win_rate': 0.0,
            'total_return': 0.0,
            'annual_return': 0.0,
            'max_drawdown': 0.0,
            'sharpe_ratio': 0.0,
            'sortino_ratio': 0.0,
            'calmar_ratio': 0.0,
            'profit_factor': 0.0,
            'average_win': 0.0,
            'average_loss': 0.0,
            'largest_win': 0.0,
            'largest_loss': 0.0,
            'max_consecutive_wins': 0,
            'max_consecutive_losses': 0,
            'average_trade_duration': 0,
            'total_commission': 0.0,
            'total_slippage': 0.0
        }
        
        # 配置参数
        self.commission_rate = 0.001  # 手续费率 0.1%
        self.slippage_rate = 0.0005   # 滑点率 0.05%
        
        self.db = StrategyDB()
    
    async def run_backtest(self, start_date: str, end_date: str, 
                          symbol: str = 'BTC-USDT-SWAP', timeframe: str = '1h') -> Dict[str, Any]:
        """运行策略回测"""
        try:
            # 获取历史数据
            historical_data = await self._get_historical_data_with_fallback(
                symbol=symbol,
                timeframe=timeframe,
                start_date=start_date,
                end_date=end_date
            )
            
            if historical_data.empty:
                logger.error("无法获取历史数据，回测终止")
                return None
            
            # 初始化回测环境
            self._initialize_backtest()
            
            # 逐步执行回测
            for i in range(len(historical_data)):
                current_time = historical_data.index[i]
                current_data = historical_data.iloc[:i+1]  # 当前时间点及之前的数据
                
                if len(current_data) < 50:  # 确保有足够的数据计算指标
                    continue
                
                # 更新持仓价格
                self._update_positions(historical_data.iloc[i])
                
                # 生成交易信号
                try:
                    signals = self.strategy.generate_signals(current_data)
                    
                    # 处理信号
                    for signal in signals:
                        if self._validate_signal(signal):
                            await self._execute_signal(signal, historical_data.iloc[i], current_time)
                            
                except Exception as e:
                    logger.warning(f"信号生成失败 {current_time}: {e}")
                    continue
                
                # 更新资产曲线
                self._update_equity_curve(current_time, historical_data.iloc[i]['close'])
                
                # 检查止损止盈和策略退出条件
                self._check_stop_conditions(historical_data.iloc[i], current_time, current_data)
            
            # 平仓所有持仓
            final_price = historical_data.iloc[-1]['close']
            await self._close_all_positions(final_price, historical_data.index[-1])
            
            # 计算最终性能
            self._calculate_performance_stats(start_date, end_date)
            
            # 保存回测结果
            backtest_results = self._generate_backtest_report()
            await self._save_backtest_results(backtest_results, start_date, end_date)
            
            logger.info(f"回测完成 - 总收益率: {self.performance_stats['total_return']:.2%}")
            return backtest_results
            
        except Exception as e:
            logger.error(f"回测执行失败: {e}")
            raise
    
    def _initialize_backtest(self):
        """初始化回测环境"""
        self.current_capital = self.initial_capital
        self.available_cash = self.initial_capital
        self.positions = {}
        self.trade_history = []
        self.equity_curve = []
        self.drawdown_series = []
        
        # 重置策略状态
        self.strategy.positions = {}
        self.strategy.trade_history = []
        self.strategy.performance = {
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
    
    async def _get_historical_data(self, symbol: str, timeframe: str, 
                             start_date: str, end_date: str) -> pd.DataFrame:
        """获取历史数据"""
        try:
            logger.info(f"获取历史数据: {symbol} {timeframe} {start_date} -> {end_date}")
            
            # 转换时间格式
            start_dt = datetime.strptime(start_date, '%Y-%m-%d')
            end_dt = datetime.strptime(end_date, '%Y-%m-%d')
            
            # 转换时间框架为OKX格式
            timeframe_map = {
                '1m': '1m',
                '5m': '5m', 
                '15m': '15m',
                '1h': '1H',
                '4h': '4H',
                '1d': '1D'
            }
            
            okx_timeframe = timeframe_map.get(timeframe, '1H')
            
            # 使用OKX REST客户端获取历史数据
            from exchange.okx.okx_rest_client import OKXRESTClient
            
            # 这里需要配置API密钥，或者使用公共接口
            # 对于历史数据，通常可以使用公共接口
            client = OKXRESTClient(
                api_key="",  # 可以为空，使用公共接口
                api_secret="",
                passphrase="",
                is_demo=False
            )
            
            # 获取K线数据
            kline_data = await client.get_historical_klines(
                symbol=symbol,
                interval=okx_timeframe,
                start_time=int(start_dt.timestamp() * 1000),
                end_time=int(end_dt.timestamp() * 1000),
                limit=1000  # 每次最多1000条
            )
            
            if not kline_data:
                logger.warning(f"未获取到 {symbol} 的历史数据")
                return pd.DataFrame()
            
            # 转换为DataFrame
            data = []
            for kline in kline_data:
                data.append({
                    'timestamp': pd.to_datetime(int(kline[0]), unit='ms'),
                    'open': float(kline[1]),
                    'high': float(kline[2]),
                    'low': float(kline[3]),
                    'close': float(kline[4]),
                    'volume': float(kline[5])
                })
            
            df = pd.DataFrame(data)
            df.set_index('timestamp', inplace=True)
            df.sort_index(inplace=True)
            
            logger.info(f"成功获取 {len(df)} 条历史数据")
            return df
            
        except Exception as e:
            logger.error(f"获取历史数据失败: {e}")
            # 如果API调用失败，返回空DataFrame或使用备用数据源
            return pd.DataFrame()
    
    async def _get_historical_data_with_fallback(self, symbol: str, timeframe: str, 
                                            start_date: str, end_date: str) -> pd.DataFrame:
        """获取历史数据（带备用方案）"""
        try:
            # 首先尝试使用现有的 _get_historical_data 方法
            df = await self._get_historical_data(symbol, timeframe, start_date, end_date)
            
            if not df.empty:
                return self._validate_and_clean_data(df, symbol)
            
            # 如果获取失败，使用模拟数据作为备用
            logger.warning("真实数据获取失败，使用模拟数据...")
            return await self._get_historical_data(symbol, timeframe, start_date, end_date)
            
        except Exception as e:
            logger.error(f"获取历史数据失败: {e}")
            return pd.DataFrame()

    def _validate_and_clean_data(self, df: pd.DataFrame, symbol: str) -> pd.DataFrame:
        """验证和清洗数据"""
        if df.empty:
            return df
        
        # 检查价格合理性
        price_ranges = {
            'BTC-USDT-SWAP': (1000, 200000),
            'ETH-USDT-SWAP': (50, 50000),
            'BNB-USDT-SWAP': (10, 1000),
            'ADA-USDT-SWAP': (0.01, 10),
            'SOL-USDT-SWAP': (1, 1000)
        }
        
        min_price, max_price = price_ranges.get(symbol, (0, float('inf')))
        
        # 过滤异常价格
        original_len = len(df)
        df = df[(df['close'] >= min_price) & (df['close'] <= max_price)]
        df = df[(df['high'] >= df['low']) & (df['high'] >= df['close']) & (df['low'] <= df['close'])]
        
        if len(df) < original_len:
            logger.warning(f"过滤了 {original_len - len(df)} 条异常数据")
        
        # 检查时间连续性
        if len(df) > 1:
            time_diff = df.index[1] - df.index[0]
            expected_freq = pd.Timedelta(hours=1) if 'H' in str(time_diff) else pd.Timedelta(days=1)
            
            # 填充缺失的时间点
            full_range = pd.date_range(start=df.index.min(), end=df.index.max(), freq=expected_freq)
            df = df.reindex(full_range, method='ffill')
        
        return df

    def _validate_signal(self, signal: TradingSignal) -> bool:
        """验证信号是否可执行"""
        try:
            # 检查资金是否充足
            required_cash = signal.price * signal.quantity
            if signal.action in ['BUY'] and required_cash > self.available_cash:
                return False
            
            # 检查是否已有相同方向的持仓
            if signal.symbol in self.positions:
                existing_side = self.positions[signal.symbol]['side']
                if (signal.action == 'BUY' and existing_side == 'LONG') or \
                   (signal.action == 'SELL' and existing_side == 'SHORT'):
                    return False
            
            return True
            
        except Exception as e:
            logger.error(f"信号验证失败: {e}")
            return False
    
    async def _execute_signal(self, signal: TradingSignal, market_data: pd.Series, timestamp: datetime):
        """执行交易信号"""
        try:
            if signal.action in ['BUY', 'SELL']:
                # 检查是否已有该symbol的持仓
                if signal.symbol in self.positions:
                    existing_position = self.positions[signal.symbol]
                    
                    # 如果信号方向与现有持仓相反，先平仓再开新仓（合约交易）
                    if ((signal.action == 'BUY' and existing_position['side'] == 'SHORT') or
                        (signal.action == 'SELL' and existing_position['side'] == 'LONG')):
                        logger.info(f"检测到反向信号，先平仓后开仓: {signal.symbol} {existing_position['side']} -> {signal.action}")
                        await self._close_position(signal.symbol, market_data['close'], timestamp, 'reverse_signal')
                        
                # 开新仓
                await self._open_position(signal, market_data, timestamp)
            elif signal.action == 'CLOSE':
                await self._close_position(signal.symbol, market_data['close'], timestamp, 'signal')
                
        except Exception as e:
            logger.error(f"执行信号失败: {e}")
    
    async def _open_position(self, signal: TradingSignal, market_data: pd.Series, timestamp: datetime):
        """开仓"""
        try:
            # 计算实际执行价格（包含滑点）
            slippage = signal.price * self.slippage_rate
            if signal.action == 'BUY':
                execution_price = signal.price + slippage
                side = 'LONG'
            else:
                execution_price = signal.price - slippage
                side = 'SHORT'
            
            # 计算手续费
            position_value = execution_price * signal.quantity
            commission = position_value * self.commission_rate
            
            # 更新可用资金
            if signal.action == 'BUY':
                self.available_cash -= (position_value + commission)
            
            # 创建持仓记录
            position = {
                'symbol': signal.symbol,
                'side': side,
                'quantity': signal.quantity,
                'entry_price': execution_price,
                'entry_time': timestamp,
                'stop_loss': signal.stop_loss,
                'take_profit': signal.take_profit,
                'commission': commission,
                'unrealized_pnl': 0.0
            }
            
            self.positions[signal.symbol] = position
            
            # 记录交易
            trade_record = {
                'symbol': signal.symbol,
                'action': signal.action,
                'side': side,
                'quantity': signal.quantity,
                'price': execution_price,
                'value': position_value,
                'commission': commission,
                'slippage': slippage,
                'timestamp': timestamp,
                'type': 'OPEN',
                'pnl': -commission  # 开仓时的成本
            }
            
            self.trade_history.append(trade_record)
            self.performance_stats['total_commission'] += commission
            self.performance_stats['total_slippage'] += slippage
            
            logger.debug(f"开仓: {signal.symbol} {side} {signal.quantity}@{execution_price}")
            
        except Exception as e:
            logger.error(f"开仓失败: {e}")
    
    async def _close_position(self, symbol: str, current_price: float, 
                            timestamp: datetime, reason: str = 'manual'):
        """平仓"""
        try:
            if symbol not in self.positions:
                return
            
            position = self.positions[symbol]
            
            # 计算实际执行价格（包含滑点）
            slippage = current_price * self.slippage_rate
            if position['side'] == 'LONG':
                execution_price = current_price - slippage
            else:
                execution_price = current_price + slippage
            
            # 计算盈亏
            if position['side'] == 'LONG':
                pnl = (execution_price - position['entry_price']) * position['quantity']
            else:
                pnl = (position['entry_price'] - execution_price) * position['quantity']
            
            # 计算手续费
            position_value = execution_price * position['quantity']
            commission = position_value * self.commission_rate
            
            # 净盈亏（扣除手续费）
            net_pnl = pnl - commission - position['commission']
            
            # 更新可用资金
            if position['side'] == 'LONG':
                self.available_cash += position_value - commission
            else:
                # 做空平仓
                self.available_cash += position['entry_price'] * position['quantity'] + pnl - commission
            
            # 记录交易
            trade_record = {
                'symbol': symbol,
                'action': 'SELL' if position['side'] == 'LONG' else 'BUY',
                'side': position['side'],
                'quantity': position['quantity'],
                'price': execution_price,
                'value': position_value,
                'commission': commission,
                'slippage': slippage,
                'timestamp': timestamp,
                'type': 'CLOSE',
                'pnl': net_pnl,
                'entry_price': position['entry_price'],
                'entry_time': position['entry_time'],
                'hold_duration': (timestamp - position['entry_time']).total_seconds() / 3600,  # 小时
                'reason': reason
            }
            
            self.trade_history.append(trade_record)
            
            # 更新统计
            self.performance_stats['total_trades'] += 1
            self.performance_stats['total_commission'] += commission
            self.performance_stats['total_slippage'] += slippage
            
            if net_pnl > 0:
                self.performance_stats['winning_trades'] += 1
                if net_pnl > self.performance_stats['largest_win']:
                    self.performance_stats['largest_win'] = net_pnl
            else:
                self.performance_stats['losing_trades'] += 1
                if net_pnl < self.performance_stats['largest_loss']:
                    self.performance_stats['largest_loss'] = net_pnl
            
            # 移除持仓
            del self.positions[symbol]
            
            logger.debug(f"平仓: {symbol} {position['side']} PnL: {net_pnl:.2f}")
            
        except Exception as e:
            logger.error(f"平仓失败: {e}")
    
    def _update_positions(self, market_data: pd.Series):
        """更新持仓状态"""
        current_price = market_data['close']
        
        for symbol, position in self.positions.items():
            if symbol == market_data.name or 'close' in market_data:
                position['current_price'] = current_price
                
                # 计算未实现盈亏
                if position['side'] == 'LONG':
                    unrealized_pnl = (current_price - position['entry_price']) * position['quantity']
                else:
                    unrealized_pnl = (position['entry_price'] - current_price) * position['quantity']
                
                position['unrealized_pnl'] = unrealized_pnl
    
    def _check_stop_conditions(self, market_data: pd.Series, timestamp: datetime, current_data: pd.DataFrame = None):
        """检查止损止盈条件和策略退出逻辑"""
        current_price = market_data['close']
        
        positions_to_close = []
        
        for symbol, position in self.positions.items():
            should_close = False
            reason = ""
            
            # 检查止损
            if position['stop_loss']:
                if position['side'] == 'LONG' and current_price <= position['stop_loss']:
                    should_close = True
                    reason = "stop_loss"
                elif position['side'] == 'SHORT' and current_price >= position['stop_loss']:
                    should_close = True
                    reason = "stop_loss"
            
            # 检查止盈
            if position['take_profit'] and not should_close:
                if position['side'] == 'LONG' and current_price >= position['take_profit']:
                    should_close = True
                    reason = "take_profit"
                elif position['side'] == 'SHORT' and current_price <= position['take_profit']:
                    should_close = True
                    reason = "take_profit"
            
            # 检查策略特定退出条件（如RSI、布林带等）
            if not should_close and current_data is not None:
                try:
                    # 将字典格式的position转换为Position对象以兼容策略接口
                    from core.strategy_trade.base_strategy import Position
                    position_obj = Position(
                        symbol=position['symbol'],
                        side=position['side'],
                        quantity=position['quantity'],
                        entry_price=position['entry_price'],
                        current_price=current_price,
                        unrealized_pnl=position.get('unrealized_pnl', 0.0),
                        stop_loss=position.get('stop_loss'),
                        take_profit=position.get('take_profit'),
                        entry_time=position.get('entry_time')
                    )
                    
                    # 调用策略的退出判断逻辑
                    if self.strategy.should_exit_position(position_obj, current_data):
                        should_close = True
                        reason = "strategy_exit"
                        logger.info(f"策略退出信号触发: {symbol} {position['side']} @ {current_price}")
                        
                except Exception as e:
                    logger.warning(f"检查策略退出条件失败 {symbol}: {e}")
            
            if should_close:
                positions_to_close.append((symbol, reason))
        
        # 执行平仓
        for symbol, reason in positions_to_close:
            asyncio.create_task(self._close_position(symbol, current_price, timestamp, reason))
    
    async def _close_all_positions(self, final_price: float, timestamp: datetime):
        """平仓所有持仓"""
        symbols_to_close = list(self.positions.keys())
        for symbol in symbols_to_close:
            await self._close_position(symbol, final_price, timestamp, "backtest_end")
    
    def _update_equity_curve(self, timestamp: datetime, current_price: float):
        """更新资产曲线"""
        # 计算当前总资产
        total_value = self.available_cash
        
        for position in self.positions.values():
            if position['side'] == 'LONG':
                position_value = current_price * position['quantity']
            else:
                # 做空持仓价值
                position_value = position['entry_price'] * position['quantity'] + position['unrealized_pnl']
            
            total_value += position_value
        
        self.current_capital = total_value
        
        # 记录资产曲线点
        equity_point = {
            'timestamp': timestamp,
            'total_value': total_value,
            'available_cash': self.available_cash,
            'unrealized_pnl': sum(pos['unrealized_pnl'] for pos in self.positions.values()),
            'drawdown': (total_value - max([ep['total_value'] for ep in self.equity_curve] + [self.initial_capital])) / max([ep['total_value'] for ep in self.equity_curve] + [self.initial_capital])
        }
        
        self.equity_curve.append(equity_point)
    
    def _calculate_performance_stats(self, start_date: str, end_date: str):
        """计算性能统计"""
        try:
            if not self.trade_history:
                return
            
            # 基础统计
            total_trades = self.performance_stats['total_trades']
            winning_trades = self.performance_stats['winning_trades']
            losing_trades = self.performance_stats['losing_trades']
            
            if total_trades > 0:
                self.performance_stats['win_rate'] = winning_trades / total_trades
            
            # 收益率计算
            self.performance_stats['total_return'] = (self.current_capital - self.initial_capital) / self.initial_capital
            
            # 年化收益率
            start_dt = datetime.strptime(start_date, '%Y-%m-%d')
            end_dt = datetime.strptime(end_date, '%Y-%m-%d')
            days = (end_dt - start_dt).days
            if days > 0:
                total_return = self.performance_stats['total_return']
                # 避免负数导致的无效值
                if total_return > -1:
                    self.performance_stats['annual_return'] = (1 + total_return) ** (365.25 / days) - 1
                else:
                    # 如果亏损超过100%，年化收益率设为-100%
                    self.performance_stats['annual_return'] = -1.0
            
            # 盈亏统计
            trade_pnls = [t['pnl'] for t in self.trade_history if t['type'] == 'CLOSE']
            
            if trade_pnls:
                winning_pnls = [pnl for pnl in trade_pnls if pnl > 0]
                losing_pnls = [pnl for pnl in trade_pnls if pnl < 0]
                
                if winning_pnls:
                    self.performance_stats['average_win'] = np.mean(winning_pnls)
                
                if losing_pnls:
                    self.performance_stats['average_loss'] = np.mean(losing_pnls)
                
                # 盈亏因子
                total_wins = sum(winning_pnls) if winning_pnls else 0
                total_losses = abs(sum(losing_pnls)) if losing_pnls else 0
                
                if total_losses > 0:
                    self.performance_stats['profit_factor'] = total_wins / total_losses
            
            # 最大回撤
            if self.equity_curve:
                peak = self.initial_capital
                max_dd = 0
                
                for point in self.equity_curve:
                    if point['total_value'] > peak:
                        peak = point['total_value']
                    
                    drawdown = (peak - point['total_value']) / peak
                    if drawdown > max_dd:
                        max_dd = drawdown
                
                self.performance_stats['max_drawdown'] = max_dd
            
            # 夏普比率和索提诺比率
            if len(self.equity_curve) > 1:
                returns = []
                for i in range(1, len(self.equity_curve)):
                    ret = (self.equity_curve[i]['total_value'] - self.equity_curve[i-1]['total_value']) / self.equity_curve[i-1]['total_value']
                    returns.append(ret)
                
                if returns:
                    mean_return = np.mean(returns)
                    std_return = np.std(returns)
                    
                    if std_return > 0:
                        self.performance_stats['sharpe_ratio'] = mean_return / std_return * np.sqrt(252)  # 年化
                    
                    # 索提诺比率（只考虑下行风险）
                    downside_returns = [r for r in returns if r < 0]
                    if downside_returns:
                        downside_std = np.std(downside_returns)
                        if downside_std > 0:
                            self.performance_stats['sortino_ratio'] = mean_return / downside_std * np.sqrt(252)
            
            # 卡尔玛比率
            if self.performance_stats['max_drawdown'] > 0:
                self.performance_stats['calmar_ratio'] = self.performance_stats['annual_return'] / self.performance_stats['max_drawdown']
            
            # 平均持仓时间
            hold_durations = [t['hold_duration'] for t in self.trade_history if t['type'] == 'CLOSE' and 'hold_duration' in t]
            if hold_durations:
                self.performance_stats['average_trade_duration'] = np.mean(hold_durations)
            
            # 连续盈亏统计
            consecutive_wins = 0
            consecutive_losses = 0
            max_consecutive_wins = 0
            max_consecutive_losses = 0
            
            for trade in [t for t in self.trade_history if t['type'] == 'CLOSE']:
                if trade['pnl'] > 0:
                    consecutive_wins += 1
                    consecutive_losses = 0
                    max_consecutive_wins = max(max_consecutive_wins, consecutive_wins)
                else:
                    consecutive_losses += 1
                    consecutive_wins = 0
                    max_consecutive_losses = max(max_consecutive_losses, consecutive_losses)
            
            self.performance_stats['max_consecutive_wins'] = max_consecutive_wins
            self.performance_stats['max_consecutive_losses'] = max_consecutive_losses
            
        except Exception as e:
            logger.error(f"计算性能统计失败: {e}")
    
    def _generate_backtest_report(self) -> Dict[str, Any]:
        """生成回测报告"""
        return {
            'strategy_name': self.strategy.name,
            'initial_capital': self.initial_capital,
            'final_capital': self.current_capital,
            'performance_stats': self.performance_stats,
            'trade_history': self.trade_history,
            'equity_curve': self.equity_curve,
            'total_trades': len([t for t in self.trade_history if t['type'] == 'CLOSE']),
            'backtest_completed_at': datetime.now().isoformat()
        }
    
    def _convert_to_json_serializable(self, obj):
        """将对象转换为JSON可序列化格式"""
        import pandas as pd
        
        if isinstance(obj, dict):
            return {key: self._convert_to_json_serializable(value) for key, value in obj.items()}
        elif isinstance(obj, list):
            return [self._convert_to_json_serializable(item) for item in obj]
        elif isinstance(obj, pd.Timestamp):
            return obj.strftime('%Y-%m-%d %H:%M:%S')
        elif isinstance(obj, datetime):
            return obj.strftime('%Y-%m-%d %H:%M:%S')
        elif isinstance(obj, (pd.Series, pd.DataFrame)):
            # 转换 pandas 对象为字典或列表
            if isinstance(obj, pd.Series):
                return obj.to_dict()
            else:
                return obj.to_dict('records')
        elif hasattr(obj, 'item'):  # numpy数据类型
            value = obj.item()
            # 处理NaN和Infinity
            if isinstance(value, (int, float)):
                import math
                if math.isnan(value) or math.isinf(value):
                    return 0.0
            return value
        elif isinstance(obj, (int, float, str, bool)) or obj is None:
            # 处理NaN和Infinity
            if isinstance(obj, float):
                import math
                if math.isnan(obj) or math.isinf(obj):
                    return 0.0
            return obj
        else:
            # 尝试转换为字符串
            return str(obj)

    async def _save_backtest_results(self, results: Dict[str, Any],
                                   start_date: str, end_date: str):
        """保存回测结果到数据库"""
        try:
            # 使用同步数据库连接池
            from database.db import MySQLPool
            from config.config import get_mysql_config
            
            # 获取数据库配置
            mysql_config = get_mysql_config()
            db_pool = MySQLPool(**mysql_config)
            
            # 准备回测名称
            backtest_name = self.backtest_name or f"{self.strategy.name}_{start_date}_{end_date}"
            
            # 转换results为JSON安全格式
            safe_results = self._convert_to_json_serializable(results)
            
            # 执行插入
            sql = """
                INSERT INTO strategy_backtests 
                (strategy_name, backtest_name, start_date, end_date, initial_capital, 
                 final_capital, total_return, max_drawdown, sharpe_ratio, total_trades, 
                 win_rate, profit_factor, config_json, results_json, status, completed_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """
            
            params = (
                self.strategy.name,
                backtest_name,
                start_date,
                end_date,
                float(self.initial_capital),
                float(self.current_capital),
                float(self.performance_stats['total_return']),
                float(self.performance_stats['max_drawdown']),
                float(self.performance_stats['sharpe_ratio']),
                int(self.performance_stats['total_trades']),
                float(self.performance_stats['win_rate']),
                float(self.performance_stats['profit_factor']),
                json.dumps(self.strategy.config),
                json.dumps(safe_results),
                'COMPLETED',
                datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            )
            
            db_pool.execute(sql, params)
            logger.info(f"回测结果已保存到数据库: {backtest_name}")
            
        except Exception as e:
            logger.error(f"保存回测结果失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
    
    def get_detailed_analysis(self) -> Dict[str, Any]:
        """获取详细分析报告"""
        analysis = {
            'performance_summary': self.performance_stats,
            'trade_analysis': self._analyze_trades(),
            'risk_analysis': self._analyze_risk(),
            'monthly_returns': self._calculate_monthly_returns(),
            'drawdown_analysis': self._analyze_drawdowns()
        }
        
        return analysis
    
    def _analyze_trades(self) -> Dict[str, Any]:
        """分析交易统计"""
        close_trades = [t for t in self.trade_history if t['type'] == 'CLOSE']
        
        if not close_trades:
            return {}
        
        trade_pnls = [t['pnl'] for t in close_trades]
        trade_durations = [t.get('hold_duration', 0) for t in close_trades]
        
        return {
            'total_trades': len(close_trades),
            'profitable_trades': len([p for p in trade_pnls if p > 0]),
            'losing_trades': len([p for p in trade_pnls if p < 0]),
            'average_pnl': np.mean(trade_pnls),
            'median_pnl': np.median(trade_pnls),
            'std_pnl': np.std(trade_pnls),
            'best_trade': max(trade_pnls),
            'worst_trade': min(trade_pnls),
            'average_duration_hours': np.mean(trade_durations),
            'longest_trade_hours': max(trade_durations) if trade_durations else 0,
            'shortest_trade_hours': min(trade_durations) if trade_durations else 0
        }
    
    def _analyze_risk(self) -> Dict[str, Any]:
        """分析风险指标"""
        if not self.equity_curve:
            return {}
        
        returns = []
        for i in range(1, len(self.equity_curve)):
            ret = (self.equity_curve[i]['total_value'] - self.equity_curve[i-1]['total_value']) / self.equity_curve[i-1]['total_value']
            returns.append(ret)
        
        if not returns:
            return {}
        
        return {
            'volatility': np.std(returns) * np.sqrt(252),  # 年化波动率
            'var_95': np.percentile(returns, 5),  # 95% VaR
            'var_99': np.percentile(returns, 1),  # 99% VaR
            'skewness': float(pd.Series(returns).skew()),
            'kurtosis': float(pd.Series(returns).kurtosis()),
            'max_daily_loss': min(returns),
            'max_daily_gain': max(returns)
        }
    
    def _calculate_monthly_returns(self) -> List[Dict[str, Any]]:
        """计算月度收益率"""
        if not self.equity_curve:
            return []
        
        df = pd.DataFrame(self.equity_curve)
        df['timestamp'] = pd.to_datetime(df['timestamp'])
        df.set_index('timestamp', inplace=True)
        
        monthly_returns = []
        monthly_data = df.resample('M').last()
        
        for i in range(1, len(monthly_data)):
            start_value = monthly_data.iloc[i-1]['total_value']
            end_value = monthly_data.iloc[i]['total_value']
            monthly_return = (end_value - start_value) / start_value
            
            monthly_returns.append({
                'month': monthly_data.index[i].strftime('%Y-%m'),
                'return': monthly_return,
                'start_value': start_value,
                'end_value': end_value
            })
        
        return monthly_returns
    
    def _analyze_drawdowns(self) -> Dict[str, Any]:
        """分析回撤情况"""
        if not self.equity_curve:
            return {}
        
        values = [point['total_value'] for point in self.equity_curve]
        peak = values[0]
        drawdowns = []
        current_dd = {'start': 0, 'peak_value': peak, 'trough_value': peak, 'recovery': None}
        
        for i, value in enumerate(values):
            if value > peak:
                # 新高点
                if current_dd['trough_value'] < current_dd['peak_value']:
                    # 结束当前回撤
                    current_dd['recovery'] = i
                    current_dd['duration'] = i - current_dd['start']
                    current_dd['depth'] = (current_dd['peak_value'] - current_dd['trough_value']) / current_dd['peak_value']
                    drawdowns.append(current_dd)
                
                # 开始新的监控
                peak = value
                current_dd = {'start': i, 'peak_value': peak, 'trough_value': peak, 'recovery': None}
            else:
                # 更新最低点
                if value < current_dd['trough_value']:
                    current_dd['trough_value'] = value
        
        # 处理未结束的回撤
        if current_dd['trough_value'] < current_dd['peak_value']:
            current_dd['duration'] = len(values) - current_dd['start']
            current_dd['depth'] = (current_dd['peak_value'] - current_dd['trough_value']) / current_dd['peak_value']
            current_dd['recovery'] = None  # 尚未恢复
            drawdowns.append(current_dd)
        
        if drawdowns:
            max_drawdown = max(drawdowns, key=lambda x: x['depth'])
            avg_drawdown_depth = np.mean([dd['depth'] for dd in drawdowns])
            avg_recovery_time = np.mean([dd['duration'] for dd in drawdowns if dd['recovery']])
            
            return {
                'total_drawdown_periods': len(drawdowns),
                'max_drawdown_depth': max_drawdown['depth'],
                'max_drawdown_duration': max_drawdown['duration'],
                'average_drawdown_depth': avg_drawdown_depth,
                'average_recovery_time': avg_recovery_time,
                'current_drawdown': drawdowns[-1]['depth'] if drawdowns and not drawdowns[-1]['recovery'] else 0
            }
        
        return {} 