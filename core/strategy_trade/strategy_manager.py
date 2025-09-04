from typing import Dict, List, Optional, Any
from .base_strategy import BaseStrategy
from .strategy_engine import StrategyEngine
# 数据库相关导入已在初始化时处理
from config.strategy_config import strategy_config_manager, get_strategy_template, validate_strategy_config
from utils.logger import get_logger

logger = get_logger(__name__)

class StrategyManager:
    """策略管理器"""
    
    def __init__(self, db_pool):
        self.db_pool = db_pool
        self.strategy_engine = StrategyEngine(db_pool)
        self.available_strategies = {
            "MA_Cross_Strategy": "core.strategy_trade.strategies.ma_cross_strategy.MACrossStrategy",
            "RSI_Strategy": "core.strategy_trade.strategies.rsi_strategy.RSIStrategy",
            "Bollinger_Strategy": "core.strategy_trade.strategies.bollinger_strategy.BollingerStrategy",
            "MACD_Strategy": "core.strategy_trade.strategies.macd_strategy.MACDStrategy",
            "Grid_Strategy": "core.strategy_trade.strategies.grid_strategy.GridStrategy",
        }
        
        # 使用配置管理器
        self.config_manager = strategy_config_manager
    
    def create_strategy(self, strategy_type: str, name: str, config: Dict = None) -> bool:
        """创建新策略"""
        try:
            if strategy_type not in self.available_strategies:
                logger.error(f"未知策略类型: {strategy_type}")
                return False
            
            # 验证配置
            if config is not None:
                is_valid, errors = validate_strategy_config(strategy_type, config)
                if not is_valid:
                    logger.error(f"策略配置验证失败: {errors}")
                    return False
            
            # 使用配置模板创建配置
            if config is None:
                template = get_strategy_template(strategy_type)
                if template:
                    config = template.default_config.copy()
                else:
                    logger.error(f"无法获取策略模板: {strategy_type}")
                    return False
            
            # 动态导入策略类
            module_path, class_name = self.available_strategies[strategy_type].rsplit(".", 1)
            module = __import__(module_path, fromlist=[class_name])
            strategy_class = getattr(module, class_name)
            
            # 创建策略实例
            strategy = strategy_class(config)
            strategy.name = name
            
            # 添加到引擎 (同步版本，暂时只保存配置)
            self.strategy_engine.strategies[name] = strategy
            
            logger.info(f"策略 {name} 创建成功")
            return True
            
        except Exception as e:
            logger.error(f"创建策略失败: {e}")
            return False
    
    def create_strategy_from_template(self, strategy_type: str, name: str, 
                                         custom_config: Dict = None) -> bool:
        """从模板创建策略"""
        try:
            # 使用配置管理器创建配置
            config = self.config_manager.create_config_from_template(strategy_type, custom_config)
            if config is None:
                logger.error(f"无法从模板创建配置: {strategy_type}")
                return False
            
            # 创建策略
            return self.create_strategy(strategy_type, name, config)
            
        except Exception as e:
            logger.error(f"从模板创建策略失败: {e}")
            return False
    
    def start_strategy(self, strategy_name: str) -> bool:
        """启动策略"""
        try:
            if strategy_name in self.strategy_engine.strategies:
                self.strategy_engine.strategies[strategy_name].is_active = True
                logger.info(f"策略 {strategy_name} 已启动")
                return True
            return False
        except Exception as e:
            logger.error(f"启动策略失败: {e}")
            return False
    
    def stop_strategy(self, strategy_name: str) -> bool:
        """停止策略"""
        try:
            if strategy_name in self.strategy_engine.strategies:
                self.strategy_engine.strategies[strategy_name].is_active = False
                logger.info(f"策略 {strategy_name} 已停止")
                return True
            return False
        except Exception as e:
            logger.error(f"停止策略失败: {e}")
            return False
    
    async def get_strategies_list(self) -> List[Dict]:
        """获取策略列表"""
        return self.strategy_engine.get_strategies_status()
    
    async def start_engine(self):
        """启动策略引擎"""
        await self.strategy_engine.start()
    
    async def stop_engine(self):
        """停止策略引擎"""
        await self.strategy_engine.stop()
    
    async def remove_strategy(self, strategy_name: str) -> bool:
        """移除策略"""
        try:
            await self.strategy_engine.remove_strategy(strategy_name)
            logger.info(f"策略 {strategy_name} 已移除")
            return True
        except Exception as e:
            logger.error(f"移除策略失败: {e}")
            return False
    
    def get_available_strategies(self) -> Dict[str, str]:
        """获取可用策略类型"""
        return self.available_strategies.copy()
    
    def get_strategy_templates(self) -> Dict[str, Dict]:
        """获取策略模板"""
        templates = {}
        for name, template in self.config_manager.get_all_templates().items():
            templates[name] = {
                "name": template.display_name,
                "description": template.description,
                "category": template.category,
                "risk_profile": template.risk_profile,
                "complexity": template.complexity,
                "default_config": template.default_config
            }
        return templates
    
    def get_strategy_template(self, strategy_type: str) -> Optional[Dict]:
        """获取特定策略模板"""
        template = self.config_manager.get_template(strategy_type)
        if template:
            return {
                "name": template.display_name,
                "description": template.description,
                "category": template.category,
                "risk_profile": template.risk_profile,
                "complexity": template.complexity,
                "default_config": template.default_config
            }
        return None
    
    async def get_strategy_performance(self, strategy_name: str) -> Optional[Dict]:
        """获取策略性能"""
        return self.strategy_engine.get_strategy_performance(strategy_name)
    
    async def update_strategy_config(self, strategy_name: str, new_config: Dict) -> bool:
        """更新策略配置"""
        try:
            await self.strategy_engine.update_strategy_config(strategy_name, new_config)
            logger.info(f"策略 {strategy_name} 配置已更新")
            return True
        except Exception as e:
            logger.error(f"更新策略配置失败: {e}")
            return False
    
    async def get_strategy_positions(self, strategy_name: str) -> List[Dict]:
        """获取策略持仓"""
        try:
            if strategy_name in self.strategy_engine.strategies:
                strategy = self.strategy_engine.strategies[strategy_name]
                return strategy.get_current_positions()
            return []
        except Exception as e:
            logger.error(f"获取策略持仓失败: {e}")
            return []
    
    async def get_strategy_info(self, strategy_name: str) -> Optional[Dict]:
        """获取策略详细信息"""
        try:
            if strategy_name in self.strategy_engine.strategies:
                strategy = self.strategy_engine.strategies[strategy_name]
                if hasattr(strategy, 'get_strategy_info'):
                    return strategy.get_strategy_info()
                else:
                    return {
                        'name': strategy.name,
                        'symbol': getattr(strategy, 'symbol', 'Unknown'),
                        'timeframe': getattr(strategy, 'timeframe', 'Unknown'),
                        'is_active': strategy.is_active
                    }
            return None
        except Exception as e:
            logger.error(f"获取策略信息失败: {e}")
            return None
    
    async def run_strategy_backtest(self, strategy_name: str, start_date: str, 
                                  end_date: str, initial_capital: float = 10000,
                                  backtest_name: str = None) -> Optional[Dict]:
        """运行策略回测"""
        try:
            if not backtest_name:
                backtest_name = f"{strategy_name}_backtest_{int(datetime.now().timestamp())}"
            
            return await self.strategy_engine.run_backtest(
                strategy_name, start_date, end_date, initial_capital, backtest_name
            )
        except Exception as e:
            logger.error(f"运行策略回测失败: {e}")
            return None
    
    def get_engine_status(self) -> Dict:
        """获取引擎状态"""
        return self.strategy_engine.get_engine_status()
    
    async def get_all_strategies_status(self) -> Dict[str, Any]:
        """获取所有策略的详细状态"""
        try:
            strategies_status = {}
            
            for strategy_name, strategy in self.strategy_engine.strategies.items():
                # 基础状态
                status = strategy.get_performance_summary()
                
                # 持仓信息
                positions = strategy.get_current_positions()
                status['positions'] = positions
                
                # 策略特定信息
                if hasattr(strategy, 'get_strategy_info'):
                    strategy_info = strategy.get_strategy_info()
                    status.update(strategy_info)
                
                # 网格策略特殊处理
                if hasattr(strategy, 'get_grid_status'):
                    grid_status = strategy.get_grid_status()
                    status['grid_status'] = grid_status
                
                strategies_status[strategy_name] = status
            
            return strategies_status
            
        except Exception as e:
            logger.error(f"获取策略状态失败: {e}")
            return {}
    
    async def batch_operation(self, operation: str, strategy_names: List[str], **kwargs) -> Dict[str, bool]:
        """批量操作策略"""
        results = {}
        
        for strategy_name in strategy_names:
            try:
                if operation == 'start':
                    results[strategy_name] = await self.start_strategy(strategy_name)
                elif operation == 'stop':
                    results[strategy_name] = await self.stop_strategy(strategy_name)
                elif operation == 'remove':
                    results[strategy_name] = await self.remove_strategy(strategy_name)
                elif operation == 'update_config':
                    new_config = kwargs.get('config', {})
                    results[strategy_name] = await self.update_strategy_config(strategy_name, new_config)
                else:
                    results[strategy_name] = False
                    
            except Exception as e:
                logger.error(f"批量操作失败 {strategy_name}: {e}")
                results[strategy_name] = False
        
        return results
    
    def validate_strategy_config(self, strategy_type: str, config: Dict) -> tuple[bool, str]:
        """验证策略配置"""
        try:
            is_valid, errors = validate_strategy_config(strategy_type, config)
            if is_valid:
                return True, "配置验证通过"
            else:
                return False, "; ".join(errors)
            
        except Exception as e:
            return False, f"配置验证失败: {e}"