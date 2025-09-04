import asyncio
from typing import Dict, List, Optional, Any, Callable
from datetime import datetime, timedelta
import pandas as pd
import numpy as np
from concurrent.futures import ThreadPoolExecutor
import json

from .base_strategy import BaseStrategy, TradingSignal, Position
from .strategy_db import StrategyDB
from .backtest_engine import BacktestEngine
from config.strategy_config import get_strategy_template
from database.db import get_db_pool
from utils.logger import get_logger

logger = get_logger(__name__)

class StrategyEngine:
    """增强版策略引擎 - 负责执行和管理策略"""
    
    def __init__(self, db_pool=None):
        self.db_pool = db_pool
        self.strategies: Dict[str, BaseStrategy] = {}
        self.strategy_instances: Dict[str, int] = {}  # 策略名 -> 实例ID
        self.is_running = False
        self.update_interval = 60  # 秒
        self._task = None
        self._executor = ThreadPoolExecutor(max_workers=4)
        self.market_data_cache = {}
        self.signal_handlers: List[Callable] = []
        self.risk_monitor = RiskMonitor()
        self.backtest_mode = False
        
        # 数据库接口
        self.db = StrategyDB(db_pool)
        
        # 性能监控
        self.performance_monitor = PerformanceMonitor()
        
        # 错误重试配置
        self.max_retries = 3
        self.retry_delay = 5  # 秒
        
    async def add_strategy(self, strategy: BaseStrategy, account_id: str = 'default', 
                          created_by: str = 'system'):
        """添加策略到引擎"""
        try:
            self.strategies[strategy.name] = strategy
            logger.info(f"策略 {strategy.name} 已添加到引擎")
            
            # 保存策略配置到数据库
            await self.db.save_strategy_config(
                strategy_name=strategy.name,
                strategy_type=strategy.__class__.__name__,
                config=strategy.config,
                is_active=False,
                created_by=created_by
            )
            
            # 创建策略实例
            instance_id = await self.db.create_strategy_instance(
                instance_name=f"{strategy.name}_instance",
                strategy_name=strategy.name,
                account_id=account_id,
                symbol=strategy.symbol,
                timeframe=strategy.timeframe,
                config=strategy.config,
                created_by=created_by
            )
            
            if instance_id > 0:
                self.strategy_instances[strategy.name] = instance_id
                logger.info(f"策略实例已创建: {strategy.name}, 实例ID: {instance_id}")
            
            # 初始化策略配置
            await self._initialize_strategy(strategy)
            
        except Exception as e:
            logger.error(f"添加策略失败 {strategy.name}: {e}")
            raise
    
    async def _initialize_strategy(self, strategy: BaseStrategy):
        """初始化策略"""
        try:
            # 设置默认配置
            if 'risk_config' not in strategy.config:
                strategy.config['risk_config'] = {
                    'max_daily_loss': 0.05,
                    'max_position_size': 0.1,
                    'max_drawdown': 0.2,
                    'stop_loss_pct': 0.02,
                    'take_profit_pct': 0.06,
                    'max_leverage': 1.0,
                    'max_concentration': 0.3
                }
            
            # 设置时间间隔
            if 'min_signal_interval' not in strategy.config:
                strategy.config['min_signal_interval'] = 300  # 5分钟
            
            # 初始化风险管理器
            strategy.risk_manager = strategy.risk_manager or RiskManager(strategy.config.get('risk_config', {}))
            
            logger.info(f"策略 {strategy.name} 初始化完成")
        except Exception as e:
            logger.error(f"策略 {strategy.name} 初始化失败: {e}")
            raise

    async def start_strategy(self, strategy_name: str) -> bool:
        """启动策略"""
        try:
            if strategy_name not in self.strategies:
                raise ValueError(f"策略 {strategy_name} 不存在")
            
            strategy = self.strategies[strategy_name]
            strategy.is_active = True
            
            # 更新数据库状态
            if strategy_name in self.strategy_instances:
                instance_id = self.strategy_instances[strategy_name]
                await self.db.update_strategy_instance_status(
                    instance_id, 'RUNNING', started_at=datetime.now()
                )
            
            # 启动性能监控
            self.performance_monitor.start_monitoring(strategy_name)
            
            logger.info(f"策略 {strategy_name} 已启动")
            return True
            
        except Exception as e:
            logger.error(f"启动策略失败 {strategy_name}: {e}")
            return False
    
    async def stop_strategy(self, strategy_name: str) -> bool:
        """停止策略"""
        try:
            if strategy_name not in self.strategies:
                raise ValueError(f"策略 {strategy_name} 不存在")
            
            strategy = self.strategies[strategy_name]
            strategy.is_active = False
            
            # 关闭所有持仓
            await self._close_all_positions(strategy)
            
            # 更新数据库状态
            if strategy_name in self.strategy_instances:
                instance_id = self.strategy_instances[strategy_name]
                await self.db.update_strategy_instance_status(
                    instance_id, 'STOPPED', stopped_at=datetime.now()
                )
            
            # 停止性能监控
            self.performance_monitor.stop_monitoring(strategy_name)
            
            logger.info(f"策略 {strategy_name} 已停止")
            return True
            
        except Exception as e:
            logger.error(f"停止策略失败 {strategy_name}: {e}")
            return False

    async def remove_strategy(self, strategy_name: str):
        """从引擎移除策略"""
        try:
            if strategy_name not in self.strategies:
                raise ValueError(f"策略 {strategy_name} 不存在")
            
            # 停止策略
            await self.stop_strategy(strategy_name)
            
            # 从内存中移除
            del self.strategies[strategy_name]
            if strategy_name in self.strategy_instances:
                del self.strategy_instances[strategy_name]
            
            # 从数据库删除（可选，通常只标记为删除）
            # await self.db.delete_strategy_config(strategy_name)
            
            logger.info(f"策略 {strategy_name} 已从引擎移除")
            
        except Exception as e:
            logger.error(f"移除策略失败 {strategy_name}: {e}")
            raise
    
    async def _close_all_positions(self, strategy: BaseStrategy):
        """关闭策略的所有持仓"""
        try:
            for symbol in list(strategy.positions.keys()):
                # 获取当前市场价格
                current_price = await self._get_current_price(symbol)
                if current_price > 0:
                    strategy.close_position(symbol, current_price, "strategy_stopped")
                    
                    # 保存到数据库
                    if strategy.name in self.strategy_instances:
                        instance_id = self.strategy_instances[strategy.name]
                        await self.db.close_position(
                            position_id=f"{symbol}_{strategy.positions[symbol].entry_time.isoformat()}",
                            exit_price=current_price,
                            realized_pnl=strategy.positions[symbol].unrealized_pnl,
                            exit_time=datetime.now()
                        )
                        
        except Exception as e:
            logger.error(f"关闭持仓失败: {e}")
    
    async def _get_current_price(self, symbol: str) -> float:
        """获取当前市场价格"""
        try:
            # 这里应该从实际的市场数据源获取价格
            # 暂时从缓存获取或返回默认值
            if symbol in self.market_data_cache:
                return self.market_data_cache[symbol].iloc[-1]['close']
            return 50000.0  # 默认价格
        except Exception as e:
            logger.error(f"获取价格失败 {symbol}: {e}")
            return 0.0

    async def start(self):
        """启动策略引擎"""
        if self.is_running:
            logger.warning("策略引擎已在运行")
            return
        
        self.is_running = True
        self._task = asyncio.create_task(self._run_engine())
        logger.info("策略引擎已启动")
    
    async def stop(self):
        """停止策略引擎"""
        if not self.is_running:
            logger.warning("策略引擎未在运行")
            return
        
        self.is_running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        
        # 关闭线程池
        self._executor.shutdown(wait=True)
        logger.info("策略引擎已停止")
    
    async def _run_engine(self):
        """引擎主循环"""
        while self.is_running:
            try:
                # 更新策略
                await self._update_strategies()
                
                # 更新市场数据
                await self._update_market_data()
                
                # 处理信号
                await self._process_signals()
                
                # 更新风险监控
                await self._update_risk_monitor()
                
                # 更新性能监控
                await self._update_performance_monitor()
                
                # 保存性能数据到数据库
                await self._save_performance_data()
                
                await asyncio.sleep(self.update_interval)
                
            except Exception as e:
                logger.error(f"策略引擎运行错误: {e}")
                await asyncio.sleep(self.retry_delay)
    
    async def _update_strategies(self):
        """更新所有活跃策略"""
        for strategy_name, strategy in self.strategies.items():
            if not strategy.is_active:
                continue
                
            retry_count = 0
            while retry_count < self.max_retries:
                try:
                    # 更新持仓状态
                    if hasattr(strategy, 'update_positions') and strategy.symbol in self.market_data_cache:
                        await self._run_in_executor(strategy.update_positions, self.market_data_cache[strategy.symbol])
                    
                    # 生成新信号
                    if strategy.should_generate_signal(datetime.now()):
                        await self._generate_strategy_signals(strategy)
                    
                    # 更新性能监控
                    self.performance_monitor.update_strategy_metrics(strategy_name, strategy.get_performance_summary())
                    
                    break  # 成功执行，退出重试循环
                    
                except Exception as e:
                    retry_count += 1
                    logger.error(f"更新策略 {strategy_name} 失败 (重试 {retry_count}/{self.max_retries}): {e}")
                    
                    if retry_count >= self.max_retries:
                        # 达到最大重试次数，暂停策略
                        strategy.is_active = False
                        logger.error(f"策略 {strategy_name} 因连续错误被暂停")
                        
                        if strategy_name in self.strategy_instances:
                            instance_id = self.strategy_instances[strategy_name]
                            await self.db.update_strategy_instance_status(instance_id, 'ERROR')
                    else:
                        await asyncio.sleep(self.retry_delay)
    
    async def _run_in_executor(self, func, *args):
        """在线程池中运行函数"""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(self._executor, func, *args)
    
    async def _generate_strategy_signals(self, strategy: BaseStrategy):
        """生成策略信号"""
        try:
            # 获取策略相关的市场数据
            symbol = strategy.symbol
            if symbol not in self.market_data_cache:
                logger.warning(f"策略 {strategy.name} 缺少市场数据: {symbol}")
                return
            
            data = self.market_data_cache[symbol]
            
            # 生成信号
            signals = await self._run_in_executor(strategy.generate_signals, data)
            
            # 验证和处理信号
            for signal in signals:
                if strategy.validate_signal(signal):
                    await self._process_signal(signal, strategy)
                    strategy.set_last_signal_time(datetime.now())
                    
                    # 保存信号到数据库
                    if strategy.name in self.strategy_instances:
                        instance_id = self.strategy_instances[strategy.name]
                        await self.db.save_trading_signal(instance_id, signal)
                else:
                    logger.warning(f"策略 {strategy.name} 信号验证失败: {signal}")
                    
        except Exception as e:
            logger.error(f"生成策略信号失败 {strategy.name}: {e}")
    
    async def _process_signal(self, signal: TradingSignal, strategy: BaseStrategy):
        """处理交易信号"""
        try:
            # 检查风险限制
            current_portfolio_value = await self._get_portfolio_value(strategy)
            if not self.risk_monitor.validate_signal(signal, strategy, current_portfolio_value):
                logger.warning(f"信号被风险监控拒绝: {signal}")
                return
            
            # 执行交易
            if signal.action in ['BUY', 'SELL']:
                await self._execute_trade(signal, strategy)
            elif signal.action == 'CLOSE':
                await self._close_position_by_signal(signal, strategy)
            
            # 通知信号处理器
            await self._notify_signal_handlers(signal, strategy)
            
        except Exception as e:
            logger.error(f"处理信号失败: {e}")
    
    async def _execute_trade(self, signal: TradingSignal, strategy: BaseStrategy):
        """执行交易"""
        try:
            # 计算仓位大小
            account_balance = await self._get_account_balance(strategy)
            quantity = strategy.calculate_position_size(signal, account_balance)
            
            # 更新信号数量
            signal.quantity = quantity
            
            # 检查资金充足性
            required_capital = signal.price * quantity
            if required_capital > account_balance * 0.95:  # 保留5%缓冲
                logger.warning(f"资金不足，无法执行交易: {signal}")
                return
            
            # 开仓
            if strategy.open_position(signal, signal.price):
                logger.info(f"策略 {strategy.name} 开仓成功: {signal}")
                
                # 保存持仓到数据库
                if strategy.name in self.strategy_instances:
                    instance_id = self.strategy_instances[strategy.name]
                    position = strategy.positions[signal.symbol]
                    await self.db.save_position(instance_id, position)
                
                # 更新风险监控
                self.risk_monitor.update_position(signal, strategy)
                
                # 记录交易
                await self._record_trade(strategy, signal, 'OPEN')
            else:
                logger.warning(f"策略 {strategy.name} 开仓失败: {signal}")
                
        except Exception as e:
            logger.error(f"执行交易失败: {e}")
    
    async def _close_position_by_signal(self, signal: TradingSignal, strategy: BaseStrategy):
        """根据信号关闭持仓"""
        try:
            if strategy.close_position(signal.symbol, signal.price, "signal"):
                logger.info(f"策略 {strategy.name} 平仓成功: {signal}")
                
                # 更新数据库
                if strategy.name in self.strategy_instances:
                    position_id = f"{signal.symbol}_{datetime.now().isoformat()}"
                    await self.db.close_position(
                        position_id=position_id,
                        exit_price=signal.price,
                        realized_pnl=0,  # 实际应该计算真实盈亏
                        exit_time=datetime.now()
                    )
                
                # 记录交易
                await self._record_trade(strategy, signal, 'CLOSE')
            else:
                logger.warning(f"策略 {strategy.name} 平仓失败: {signal}")
        except Exception as e:
            logger.error(f"关闭持仓失败: {e}")
    
    async def _record_trade(self, strategy: BaseStrategy, signal: TradingSignal, trade_type: str):
        """记录交易到数据库"""
        try:
            if strategy.name not in self.strategy_instances:
                return
            
            instance_id = self.strategy_instances[strategy.name]
            trade_data = {
                'trade_id': f"{signal.symbol}_{signal.timestamp.isoformat()}",
                'symbol': signal.symbol,
                'side': 'BUY' if signal.action == 'BUY' else 'SELL',
                'quantity': signal.quantity,
                'price': signal.price,
                'amount': signal.price * signal.quantity,
                'commission': signal.price * signal.quantity * 0.001,  # 假设0.1%手续费
                'trade_type': trade_type,
                'reason': 'strategy_signal',
                'executed_at': datetime.now(),
                'metadata': signal.metadata or {}
            }
            
            await self.db.save_trade(instance_id, trade_data)
            
        except Exception as e:
            logger.error(f"记录交易失败: {e}")
    
    async def _get_portfolio_value(self, strategy: BaseStrategy) -> float:
        """获取策略组合价值"""
        # 这里应该实现真实的组合价值计算
        return 100000.0  # 临时返回固定值
    
    async def _get_account_balance(self, strategy: BaseStrategy) -> float:
        """获取账户余额"""
        # 这里应该从交易所API获取真实余额
        return 100000.0  # 临时返回固定值
    
    async def _update_market_data(self):
        """更新市场数据"""
        try:
            # 这里应该从实际的数据源获取市场数据
            # 暂时生成模拟数据
            symbols = set()
            for strategy in self.strategies.values():
                symbols.add(strategy.symbol)
            
            for symbol in symbols:
                # 生成模拟数据或从缓存更新
                if symbol not in self.market_data_cache:
                    self.market_data_cache[symbol] = self._generate_sample_data(symbol)
                else:
                    # 添加新的数据点
                    self._update_sample_data(symbol)
                    
        except Exception as e:
            logger.error(f"更新市场数据失败: {e}")
    
    def _generate_sample_data(self, symbol: str) -> pd.DataFrame:
        """生成样本数据"""
        dates = pd.date_range(start=datetime.now() - timedelta(days=30), 
                             end=datetime.now(), freq='1H')
        
        # 简单的随机价格数据
        base_price = 50000
        data = []
        current_price = base_price
        
        for date in dates:
            change = np.random.normal(0, 0.02)  # 2%波动率
            current_price *= (1 + change)
            
            data.append({
                'timestamp': date,
                'open': current_price * 0.999,
                'high': current_price * 1.005,
                'low': current_price * 0.995,
                'close': current_price,
                'volume': np.random.uniform(100, 1000)
            })
        
        df = pd.DataFrame(data)
        df.set_index('timestamp', inplace=True)
        return df
    
    def _update_sample_data(self, symbol: str):
        """更新样本数据"""
        try:
            df = self.market_data_cache[symbol]
            last_price = df.iloc[-1]['close']
            
            change = np.random.normal(0, 0.02)
            new_price = last_price * (1 + change)
            
            new_row = {
                'open': last_price,
                'high': max(last_price, new_price) * 1.002,
                'low': min(last_price, new_price) * 0.998,
                'close': new_price,
                'volume': np.random.uniform(100, 1000)
            }
            
            new_index = df.index[-1] + timedelta(hours=1)
            df.loc[new_index] = new_row
            
            # 保持最近1000条数据
            if len(df) > 1000:
                df = df.tail(1000)
                self.market_data_cache[symbol] = df
                
        except Exception as e:
            logger.error(f"更新样本数据失败 {symbol}: {e}")
    
    async def _process_signals(self):
        """处理所有待处理的信号"""
        # 这里可以添加信号队列处理逻辑
        pass
    
    async def _update_risk_monitor(self):
        """更新风险监控"""
        try:
            await self.risk_monitor.update()
            
            # 检查风险警报
            risk_alerts = self.risk_monitor.get_risk_alerts()
            for alert in risk_alerts:
                logger.warning(f"风险警报: {alert}")
                
                # 如果是严重风险，可以自动暂停策略
                if alert.get('severity') == 'CRITICAL':
                    strategy_name = alert.get('strategy_name')
                    if strategy_name and strategy_name in self.strategies:
                        await self.stop_strategy(strategy_name)
                        logger.critical(f"因严重风险警报自动停止策略: {strategy_name}")
                        
        except Exception as e:
            logger.error(f"更新风险监控失败: {e}")
    
    async def _update_performance_monitor(self):
        """更新性能监控"""
        try:
            self.performance_monitor.update_system_metrics({
                'active_strategies': len([s for s in self.strategies.values() if s.is_active]),
                'total_strategies': len(self.strategies),
                'engine_uptime': self.performance_monitor.get_uptime(),
                'memory_usage': self.performance_monitor.get_memory_usage()
            })
        except Exception as e:
            logger.error(f"更新性能监控失败: {e}")
    
    async def _save_performance_data(self):
        """保存性能数据到数据库"""
        try:
            current_date = datetime.now().date()
            
            for strategy_name, strategy in self.strategies.items():
                if strategy_name not in self.strategy_instances:
                    continue
                
                instance_id = self.strategy_instances[strategy_name]
                performance_data = strategy.get_performance_summary()
                
                await self.db.update_daily_performance(instance_id, current_date, performance_data)
                
        except Exception as e:
            logger.error(f"保存性能数据失败: {e}")
    
    async def _notify_signal_handlers(self, signal: TradingSignal, strategy: BaseStrategy):
        """通知信号处理器"""
        for handler in self.signal_handlers:
            try:
                if asyncio.iscoroutinefunction(handler):
                    await handler(signal, strategy)
                else:
                    await self._run_in_executor(handler, signal, strategy)
            except Exception as e:
                logger.error(f"信号处理器错误: {e}")
    
    def add_signal_handler(self, handler: Callable):
        """添加信号处理器"""
        self.signal_handlers.append(handler)
    
    def get_strategies_status(self) -> List[Dict[str, Any]]:
        """获取所有策略状态"""
        return [strategy.get_performance_summary() for strategy in self.strategies.values()]
    
    def get_strategy_performance(self, strategy_name: str) -> Optional[Dict[str, Any]]:
        """获取特定策略性能"""
        if strategy_name in self.strategies:
            return self.strategies[strategy_name].get_performance_summary()
        return None
    
    async def update_strategy_config(self, strategy_name: str, new_config: Dict[str, Any]):
        """更新策略配置"""
        try:
            if strategy_name not in self.strategies:
                raise ValueError(f"策略 {strategy_name} 不存在")
            
            strategy = self.strategies[strategy_name]
            old_config = strategy.config.copy()
            strategy.config.update(new_config)
            
            # 重新初始化策略
            await self._initialize_strategy(strategy)
            
            # 保存到数据库
            await self.db.save_strategy_config(
                strategy_name=strategy_name,
                strategy_type=strategy.__class__.__name__,
                config=strategy.config,
                is_active=strategy.is_active
            )
            
            logger.info(f"策略 {strategy_name} 配置已更新: {new_config}")
            
        except Exception as e:
            logger.error(f"更新策略配置失败 {strategy_name}: {e}")
            raise
    
    async def run_backtest(self, strategy_name: str, start_date: str, end_date: str, 
                          initial_capital: float = 100000, backtest_name: str = None) -> Dict[str, Any]:
        """运行策略回测"""
        try:
            if strategy_name not in self.strategies:
                raise ValueError(f"策略 {strategy_name} 不存在")
            
            strategy = self.strategies[strategy_name]
            backtester = BacktestEngine(strategy, initial_capital)
            
            # 设置回测名称
            if backtest_name:
                backtester.backtest_name = backtest_name
            
            return await backtester.run_backtest(start_date, end_date, strategy.symbol, strategy.timeframe)
            
        except Exception as e:
            logger.error(f"运行回测失败 {strategy_name}: {e}")
            raise
    
    def get_engine_status(self) -> Dict[str, Any]:
        """获取引擎状态"""
        return {
            "is_running": self.is_running,
            "strategies_count": len(self.strategies),
            "active_strategies": len([s for s in self.strategies.values() if s.is_active]),
            "update_interval": self.update_interval,
            "risk_monitor_status": self.risk_monitor.get_status(),
            "market_data_symbols": list(self.market_data_cache.keys()),
            "performance_metrics": self.performance_monitor.get_system_metrics(),
            "error_statistics": self.performance_monitor.get_error_statistics()
        }

class RiskMonitor:
    """增强版风险监控器"""
    
    def __init__(self):
        self.max_total_exposure = 0.8  # 最大总敞口80%
        self.max_single_exposure = 0.2  # 最大单笔敞口20%
        self.max_daily_loss = 0.05     # 最大日亏损5%
        self.current_exposure = 0.0
        self.daily_loss = 0.0
        self.reset_date = datetime.now().date()
        self.risk_alerts = []
        
        # 策略风险统计
        self.strategy_risks = {}
    
    def validate_signal(self, signal: TradingSignal, strategy: BaseStrategy, 
                       current_portfolio_value: float = 100000) -> bool:
        """验证信号是否符合风险要求"""
        try:
            # 检查日亏损限制
            current_date = datetime.now().date()
            if current_date != self.reset_date:
                self.daily_loss = 0.0
                self.reset_date = current_date
            
            if self.daily_loss <= -self.max_daily_loss * current_portfolio_value:
                self._add_risk_alert("daily_loss_limit", "CRITICAL", 
                                   f"日亏损超限: {self.daily_loss:.2f}")
                return False
            
            # 检查单笔仓位大小
            position_size = signal.price * signal.quantity
            position_ratio = position_size / current_portfolio_value
            if position_ratio > self.max_single_exposure:
                self._add_risk_alert("position_size_limit", "HIGH",
                                   f"单笔仓位过大: {position_ratio:.2%}")
                return False
            
            # 检查总敞口
            if (self.current_exposure + position_size) / current_portfolio_value > self.max_total_exposure:
                self._add_risk_alert("total_exposure_limit", "HIGH",
                                   f"总敞口超限: {(self.current_exposure + position_size) / current_portfolio_value:.2%}")
                return False
            
            # 检查策略特定风险
            if not self._validate_strategy_risk(signal, strategy):
                return False
            
            return True
            
        except Exception as e:
            logger.error(f"风险验证失败: {e}")
            return False
    
    def _validate_strategy_risk(self, signal: TradingSignal, strategy: BaseStrategy) -> bool:
        """验证策略特定风险"""
        strategy_name = strategy.name
        
        # 初始化策略风险统计
        if strategy_name not in self.strategy_risks:
            self.strategy_risks[strategy_name] = {
                'consecutive_losses': 0,
                'daily_trades': 0,
                'max_drawdown': 0.0,
                'last_trade_time': None
            }
        
        strategy_risk = self.strategy_risks[strategy_name]
        
        # 检查连续亏损
        if strategy_risk['consecutive_losses'] >= 5:
            self._add_risk_alert("consecutive_losses", "HIGH",
                               f"策略 {strategy_name} 连续亏损次数过多: {strategy_risk['consecutive_losses']}")
            return False
        
        # 检查交易频率
        current_time = datetime.now()
        if strategy_risk['last_trade_time']:
            time_diff = (current_time - strategy_risk['last_trade_time']).total_seconds()
            if time_diff < 300:  # 5分钟内不能重复交易
                self._add_risk_alert("trade_frequency", "MEDIUM",
                                   f"策略 {strategy_name} 交易过于频繁")
                return False
        
        strategy_risk['last_trade_time'] = current_time
        return True
    
    def update_position(self, signal: TradingSignal, strategy: BaseStrategy):
        """更新持仓信息"""
        position_value = signal.price * signal.quantity
        self.current_exposure += position_value
    
    def update_trade_result(self, strategy_name: str, pnl: float):
        """更新交易结果"""
        if strategy_name not in self.strategy_risks:
            return
        
        strategy_risk = self.strategy_risks[strategy_name]
        
        if pnl < 0:
            strategy_risk['consecutive_losses'] += 1
        else:
            strategy_risk['consecutive_losses'] = 0
        
        strategy_risk['daily_trades'] += 1
        self.daily_loss += pnl
    
    def _add_risk_alert(self, alert_type: str, severity: str, message: str):
        """添加风险警报"""
        alert = {
            'type': alert_type,
            'severity': severity,
            'message': message,
            'timestamp': datetime.now(),
            'strategy_name': None
        }
        
        self.risk_alerts.append(alert)
        
        # 只保留最近100个警报
        if len(self.risk_alerts) > 100:
            self.risk_alerts = self.risk_alerts[-100:]
    
    def get_risk_alerts(self) -> List[Dict[str, Any]]:
        """获取风险警报"""
        # 返回最近的警报
        recent_alerts = [alert for alert in self.risk_alerts 
                        if (datetime.now() - alert['timestamp']).total_seconds() < 3600]  # 1小时内
        return recent_alerts
    
    async def update(self):
        """更新风险监控状态"""
        try:
            # 清理过期的风险数据
            current_date = datetime.now().date()
            if current_date != self.reset_date:
                self.daily_loss = 0.0
                for strategy_risk in self.strategy_risks.values():
                    strategy_risk['daily_trades'] = 0
                self.reset_date = current_date
                
        except Exception as e:
            logger.error(f"更新风险监控失败: {e}")
    
    def get_status(self) -> Dict[str, Any]:
        """获取风险监控状态"""
        return {
            "current_exposure": self.current_exposure,
            "max_exposure": self.max_total_exposure,
            "daily_loss": self.daily_loss,
            "max_daily_loss": self.max_daily_loss,
            "active_alerts": len(self.get_risk_alerts()),
            "strategy_risks": self.strategy_risks
        }

class PerformanceMonitor:
    """性能监控器"""
    
    def __init__(self):
        self.start_time = datetime.now()
        self.strategy_metrics = {}
        self.system_metrics = {}
        self.error_counts = {}
        
    def start_monitoring(self, strategy_name: str):
        """开始监控策略"""
        self.strategy_metrics[strategy_name] = {
            'start_time': datetime.now(),
            'trade_count': 0,
            'signal_count': 0,
            'error_count': 0,
            'last_update': datetime.now()
        }
    
    def stop_monitoring(self, strategy_name: str):
        """停止监控策略"""
        if strategy_name in self.strategy_metrics:
            self.strategy_metrics[strategy_name]['end_time'] = datetime.now()
    
    def update_strategy_metrics(self, strategy_name: str, performance_data: Dict[str, Any]):
        """更新策略性能指标"""
        if strategy_name not in self.strategy_metrics:
            self.start_monitoring(strategy_name)
        
        metrics = self.strategy_metrics[strategy_name]
        metrics.update({
            'performance': performance_data,
            'last_update': datetime.now()
        })
    
    def update_system_metrics(self, system_data: Dict[str, Any]):
        """更新系统指标"""
        self.system_metrics.update({
            **system_data,
            'last_update': datetime.now()
        })
    
    def record_error(self, component: str, error_type: str):
        """记录错误"""
        key = f"{component}_{error_type}"
        if key not in self.error_counts:
            self.error_counts[key] = 0
        self.error_counts[key] += 1
    
    def get_uptime(self) -> float:
        """获取运行时间（小时）"""
        return (datetime.now() - self.start_time).total_seconds() / 3600
    
    def get_memory_usage(self) -> Dict[str, Any]:
        """获取内存使用情况"""
        import psutil
        process = psutil.Process()
        return {
            'memory_percent': process.memory_percent(),
            'memory_mb': process.memory_info().rss / 1024 / 1024
        }
    
    def get_system_metrics(self) -> Dict[str, Any]:
        """获取系统性能指标"""
        return self.system_metrics
    
    def get_error_statistics(self) -> Dict[str, Any]:
        """获取错误统计"""
        return {
            'total_errors': sum(self.error_counts.values()),
            'error_breakdown': self.error_counts,
            'error_rate': sum(self.error_counts.values()) / max(1, self.get_uptime())
        }