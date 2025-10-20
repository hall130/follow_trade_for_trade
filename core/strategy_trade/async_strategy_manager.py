"""
异步策略管理器
正确处理异步/同步混合架构
"""

import asyncio
from typing import Dict, List, Optional, Any
from config.strategy_config import strategy_config_manager, get_strategy_template, validate_strategy_config
from utils.logger import get_logger

# 声明为全局变量，确保在任何作用域都能访问
logger = get_logger(__name__)

class AsyncStrategyManager:
    """异步策略管理器 - 正确的实现"""
    
    def __init__(self, db_pool):
        self.db_pool = db_pool  # 同步的MySQLPool
        self.strategies = {}  # 存储策略信息
        self.strategy_instances = {}  # 存储策略实例缓存
        self.available_strategies = {
            "MA_Cross_Strategy": "core.strategy_trade.strategies.ma_cross_strategy.MACrossStrategy",
            "RSI_Strategy": "core.strategy_trade.strategies.rsi_strategy.RSIStrategy",
            "Bollinger_Strategy": "core.strategy_trade.strategies.bollinger_strategy.BollingerStrategy",
            "MACD_Strategy": "core.strategy_trade.strategies.macd_strategy.MACDStrategy",
            "Grid_Strategy": "core.strategy_trade.strategies.grid_strategy.GridStrategy",
            "High_Frequency_Strategy": "core.strategy_trade.strategies.high_frequency_strategy.HighFrequencyStrategy",
        }
        
        # 使用配置管理器
        self.config_manager = strategy_config_manager
        logger.info("异步策略管理器初始化完成")
    
    async def _run_sync(self, func, *args, **kwargs):
        """在异步环境中安全运行同步函数"""
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, func, *args, **kwargs)
    
    async def _db_query(self, sql: str, args: tuple = None):
        """异步数据库查询"""
        return await self._run_sync(self.db_pool.query, sql, args)
    
    async def _db_execute(self, sql: str, args: tuple = None):
        """异步数据库执行"""
        return await self._run_sync(self.db_pool.execute, sql, args)
    
    async def create_strategy(self, strategy_type: str, name: str, config: Dict = None) -> bool:
        """创建新策略"""
        try:
            if strategy_type not in self.available_strategies:
                logger.error(f"未知策略类型: {strategy_type}")
                return False
            
            # 验证配置
            if config is not None:
                is_valid, errors = await self._run_sync(validate_strategy_config, strategy_type, config)
                if not is_valid:
                    logger.error(f"策略配置验证失败: {errors}")
                    return False
            
            # 使用配置模板创建配置
            if config is None:
                template = await self._run_sync(get_strategy_template, strategy_type)
                if template:
                    config = template.default_config.copy()
                else:
                    logger.error(f"无法获取策略模板: {strategy_type}")
                    return False
            
            # 创建策略信息
            import time
            strategy_info = {
                'name': name,
                'strategy_type': strategy_type,
                'config': config,
                'status': 'STOPPED',
                'is_active': False,
                'created_at': time.strftime('%Y-%m-%d %H:%M:%S'),
                # 模拟性能数据
                'total_return': 0.0,
                'win_rate': 0.0,
                'total_trades': 0,
                'max_drawdown': 0.0,
                'sharpe_ratio': 0.0,
                'symbol': config.get('symbol', 'BTC-USDT'),
                'timeframe': config.get('timeframe', '1h')
            }
            
            # 保存到数据库（如果表存在）
            try:
                import json
                await self._db_execute(
                    """INSERT INTO strategy_configs 
                       (strategy_name, strategy_type, config_json, is_active, created_by) 
                       VALUES (%s, %s, %s, %s, %s)""",
                    (name, strategy_type, json.dumps(config), False, 'system')
                )
                logger.info(f"策略配置已保存到数据库: {name}")
            except Exception as db_error:
                logger.warning(f"保存策略配置到数据库失败（继续运行）: {db_error}")
            
            # 保存到内存
            self.strategies[name] = strategy_info
            
            logger.info(f"策略 {name} 创建成功")
            return True
            
        except Exception as e:
            logger.error(f"创建策略失败: {e}")
            return False
    
    async def start_strategy(self, strategy_name: str) -> bool:
        """启动策略"""
        try:
            if strategy_name in self.strategies:
                self.strategies[strategy_name]['status'] = 'RUNNING'
                self.strategies[strategy_name]['is_active'] = True
                
                # 更新数据库状态
                try:
                    await self._db_execute(
                        "UPDATE strategy_configs SET is_active = %s WHERE strategy_name = %s",
                        (True, strategy_name)
                    )
                except Exception as db_error:
                    logger.warning(f"更新数据库策略状态失败: {db_error}")
                
                logger.info(f"策略 {strategy_name} 已启动")
                return True
            else:
                logger.error(f"策略 {strategy_name} 不存在")
                return False
        except Exception as e:
            logger.error(f"启动策略失败: {e}")
            return False
    
    async def stop_strategy(self, strategy_name: str) -> bool:
        """停止策略"""
        try:
            if strategy_name in self.strategies:
                self.strategies[strategy_name]['status'] = 'STOPPED'
                self.strategies[strategy_name]['is_active'] = False
                
                # 更新数据库状态
                try:
                    await self._db_execute(
                        "UPDATE strategy_configs SET is_active = %s WHERE strategy_name = %s",
                        (False, strategy_name)
                    )
                except Exception as db_error:
                    logger.warning(f"更新数据库策略状态失败: {db_error}")
                
                logger.info(f"策略 {strategy_name} 已停止")
                return True
            else:
                logger.error(f"策略 {strategy_name} 不存在")
                return False
        except Exception as e:
            logger.error(f"停止策略失败: {e}")
            return False
    
    async def remove_strategy(self, strategy_name: str) -> bool:
        """移除策略"""
        try:
            if strategy_name in self.strategies:
                # 先停止策略
                await self.stop_strategy(strategy_name)
                
                # 从数据库删除
                try:
                    await self._db_execute(
                        "DELETE FROM strategy_configs WHERE strategy_name = %s",
                        (strategy_name,)
                    )
                except Exception as db_error:
                    logger.warning(f"从数据库删除策略失败: {db_error}")
                
                # 从内存删除
                del self.strategies[strategy_name]
                logger.info(f"策略 {strategy_name} 已移除")
                return True
            else:
                logger.error(f"策略 {strategy_name} 不存在")
                return False
        except Exception as e:
            logger.error(f"移除策略失败: {e}")
            return False
    
    async def get_strategy_status(self, strategy_name: str) -> Optional[Dict]:
        """获取策略状态"""
        return self.strategies.get(strategy_name)
    
    async def get_all_strategies_status(self) -> Dict[str, Any]:
        """获取所有策略状态"""
        return self.strategies.copy()
    
    async def get_strategies_list(self) -> List[Dict]:
        """获取策略列表"""
        return list(self.strategies.values())
    
    async def load_strategies_from_db(self):
        """从数据库加载已存在的策略"""
        try:
            strategies = await self._db_query(
                "SELECT strategy_name, strategy_type, config_json, is_active, created_at FROM strategy_configs"
            )
            
            for strategy in strategies:
                import json
                try:
                    config = json.loads(strategy['config_json'])
                    strategy_info = {
                        'name': strategy['strategy_name'],
                        'strategy_type': strategy['strategy_type'],
                        'config': config,
                        'status': 'RUNNING' if strategy['is_active'] else 'STOPPED',
                        'is_active': strategy['is_active'],
                        'created_at': str(strategy['created_at']),
                        # 模拟性能数据
                        'total_return': 0.0,
                        'win_rate': 0.0,
                        'total_trades': 0,
                        'max_drawdown': 0.0,
                        'sharpe_ratio': 0.0,
                        'symbol': config.get('symbol', 'BTC-USDT'),
                        'timeframe': config.get('timeframe', '1h')
                    }
                    self.strategies[strategy['strategy_name']] = strategy_info
                    
                except Exception as parse_error:
                    logger.error(f"解析策略配置失败: {strategy['strategy_name']}, {parse_error}")
            
            logger.info(f"从数据库加载了 {len(strategies)} 个策略")
            
        except Exception as e:
            logger.warning(f"从数据库加载策略失败（继续运行）: {e}")
    
    async def start_engine(self):
        """启动策略引擎"""
        try:
            # 加载已存在的策略
            await self.load_strategies_from_db()
            
            logger.info("异步策略引擎启动成功")
            
        except Exception as e:
            logger.error(f"启动策略引擎失败: {e}")
    
    async def stop_engine(self):
        """停止策略引擎"""
        try:
            # 停止所有运行中的策略
            for strategy_name, strategy_info in self.strategies.items():
                if strategy_info['status'] == 'RUNNING':
                    await self.stop_strategy(strategy_name)
            
            # 清理策略实例缓存
            self.strategy_instances.clear()
            logger.info("策略实例缓存已清理")
            
            logger.info("异步策略引擎已停止")
            
        except Exception as e:
            logger.error(f"停止策略引擎失败: {e}")
    
    async def get_strategy_info(self, strategy_name: str) -> Optional[Dict]:
        """获取策略信息"""
        try:
            if strategy_name in self.strategies:
                return self.strategies[strategy_name]
            return None
        except Exception as e:
            logger.error(f"获取策略信息失败: {e}")
            return None

    async def clear_strategy_cache(self, strategy_name: str = None):
        """清理策略实例缓存"""
        try:
            if strategy_name:
                # 清理指定策略的缓存
                if strategy_name in self.strategy_instances:
                    del self.strategy_instances[strategy_name]
                    logger.info(f"已清理策略缓存: {strategy_name}")
            else:
                # 清理所有策略缓存
                self.strategy_instances.clear()
                logger.info("已清理所有策略实例缓存")
                
        except Exception as e:
            logger.error(f"清理策略缓存失败: {e}")
    
    async def get_or_create_strategy_instance(self, strategy_name: str) -> Optional[Any]:
        """获取或创建策略实例（支持缓存复用）"""
        try:
            if strategy_name not in self.strategies:
                logger.error(f"策略 {strategy_name} 不存在")
                return None
            
            # 检查是否已有缓存的实例
            if strategy_name in self.strategy_instances:
                logger.info(f"复用缓存的策略实例: {strategy_name}")
                return self.strategy_instances[strategy_name]
            
            # 创建新的策略实例
            strategy_info = self.strategies[strategy_name]
            strategy_type = strategy_info['strategy_type']
            
            if strategy_type not in self.available_strategies:
                logger.error(f"未知策略类型: {strategy_type}")
                return None
            
            # 动态导入策略类
            module_path = self.available_strategies[strategy_type]
            module_name, class_name = module_path.rsplit('.', 1)
            
            import importlib
            module = importlib.import_module(module_name)
            strategy_class = getattr(module, class_name)
            
            # 创建策略实例
            strategy_config = strategy_info['config']
            
            # 确保配置是字典类型
            if isinstance(strategy_config, str):
                import json
                try:
                    strategy_config = json.loads(strategy_config)
                except json.JSONDecodeError:
                    logger.error(f"策略配置JSON解析失败: {strategy_config}")
                    return None
            
            strategy_instance = strategy_class(
                name=strategy_name,
                config=strategy_config
            )
            
            # 缓存策略实例
            self.strategy_instances[strategy_name] = strategy_instance
            logger.info(f"创建并缓存策略实例: {strategy_name}")
            
            return strategy_instance
            
        except Exception as e:
            logger.error(f"获取策略实例失败: {e}")
            return None

    async def update_strategy_config(self, strategy_name: str, new_config: Dict) -> bool:
        """更新策略配置参数（不重新创建策略实例）"""
        try:
            if strategy_name not in self.strategies:
                logger.error(f"策略 {strategy_name} 不存在")
                return False
            
            # 更新内存中的策略配置
            self.strategies[strategy_name]['config'].update(new_config)
            
            # 如果策略实例已缓存，更新其实例配置
            if strategy_name in self.strategy_instances:
                strategy_instance = self.strategy_instances[strategy_name]
                strategy_instance.config.update(new_config)
                logger.info(f"已更新缓存策略实例的配置: {strategy_name}")
            
            # 更新数据库中的配置
            import json
            await self._db_execute(
                "UPDATE strategy_configs SET config_json = %s WHERE strategy_name = %s",
                (json.dumps(self.strategies[strategy_name]['config']), strategy_name)
            )
            
            logger.info(f"策略 {strategy_name} 配置已更新")
            return True
            
        except Exception as e:
            logger.error(f"更新策略配置失败: {e}")
            return False

    async def run_strategy_backtest(self, strategy_name: str, start_date: str, 
                                  end_date: str, initial_capital: float = 10000,
                                  backtest_name: str = None, 
                                  strategy_config: Dict = None) -> Optional[Dict]:
        """运行策略回测（支持参数更新）"""
        try:
            if not backtest_name:
                from datetime import datetime
                backtest_name = f"{strategy_name}_backtest_{int(datetime.now().timestamp())}"
            
            # 如果提供了新的策略配置，先更新策略参数
            if strategy_config:
                logger.info(f"更新策略 {strategy_name} 的参数配置")
                update_success = await self.update_strategy_config(strategy_name, strategy_config)
                if not update_success:
                    logger.warning(f"策略参数更新失败，使用现有配置")
            
            # 检查策略是否存在于内存中
            if strategy_name not in self.strategies:
                logger.error(f"策略 {strategy_name} 不存在于当前管理器中")
                return None
            
            strategy_info = self.strategies[strategy_name]
            
            # 获取或创建策略实例（支持缓存复用）
            strategy_instance = await self.get_or_create_strategy_instance(strategy_name)
            if not strategy_instance:
                logger.error(f"无法获取策略实例: {strategy_name}")
                return None
            
            # 直接使用缓存的策略实例进行回测
            def run_backtest_sync():
                # 使用全局logger
                global logger
                
                try:
                    
                    # 创建回测引擎并运行
                    from .backtest_engine import BacktestEngine
                    backtester = BacktestEngine(strategy_instance, initial_capital)
                    
                    if backtest_name:
                        backtester.backtest_name = backtest_name
                    
                    # 使用asyncio运行回测
                    import asyncio
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    try:
                        return loop.run_until_complete(backtester.run_backtest(
                            start_date, end_date, 
                            strategy_instance.symbol, 
                            strategy_instance.timeframe
                        ))
                    finally:
                        loop.close()
                        
                except Exception as e:
                    logger.error(f"同步回测执行失败: {e}")
                    raise
            
            result = await self._run_sync(run_backtest_sync)
            return result
            
        except Exception as e:

            logger.error(f"运行策略回测失败: {e}")
            return None
    
    async def get_engine_status(self) -> Dict[str, Any]:
        """获取引擎状态"""
        running_count = len([s for s in self.strategies.values() if s['status'] == 'RUNNING'])
        total_count = len(self.strategies)
        
        return {
            'status': 'running',
            'total_strategies': total_count,
            'running_strategies': running_count,
            'stopped_strategies': total_count - running_count,
            'uptime': '异步运行中',
            'last_update': asyncio.get_event_loop().time()
        }
    
    async def update_strategy_full_config(self, strategy_name: str, new_name: str, 
                                        config: Dict, signal_sources: List = None, 
                                        customers: List = None) -> bool:
        """更新策略完整配置（包括名称、信号源、客户等）"""
        try:
            if strategy_name not in self.strategies:
                logger.error(f"策略 {strategy_name} 不存在")
                return False
            
            # 更新内存中的策略信息
            strategy_info = self.strategies[strategy_name]
            
            # 如果名称发生变化，需要重新存储
            if new_name != strategy_name:
                self.strategies[new_name] = strategy_info
                del self.strategies[strategy_name]
                strategy_info['name'] = new_name
            
            # 更新配置
            strategy_info['config'].update(config)
            
            # 更新关联的账号信息（这里可以扩展存储到数据库）
            if signal_sources is not None:
                strategy_info['signal_sources'] = signal_sources
            if customers is not None:
                strategy_info['customers'] = customers
            
            # 更新数据库中的配置
            try:
                import json
                await self._db_execute(
                    """UPDATE strategy_configs 
                       SET strategy_name = %s, config_json = %s 
                       WHERE strategy_name = %s""",
                    (new_name, json.dumps(strategy_info['config']), strategy_name)
                )
                logger.info(f"策略配置已更新到数据库: {new_name}")
            except Exception as db_error:
                logger.warning(f"更新数据库中的策略配置失败: {db_error}")
            
            logger.info(f"策略配置更新成功: {strategy_name} -> {new_name}")
            return True
            
        except Exception as e:
            logger.error(f"更新策略配置失败: {e}")
            return False 