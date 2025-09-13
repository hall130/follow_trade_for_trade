"""
简化的同步策略管理器
专门用于Flask API，避免异步问题
"""

from typing import Dict, List, Optional, Any
from config.strategy_config import strategy_config_manager, get_strategy_template, validate_strategy_config
from utils.logger import get_logger

logger = get_logger(__name__)

class SimpleStrategyManager:
    """简化的同步策略管理器"""
    
    def __init__(self, db_pool):
        self.db_pool = db_pool
        self.strategies = {}  # 存储策略实例
        self.available_strategies = {
            "MA_Cross_Strategy": "移动平均交叉策略",
            "RSI_Strategy": "RSI超买超卖策略", 
            "Bollinger_Strategy": "布林带策略",
            "MACD_Strategy": "MACD策略",
            "Grid_Strategy": "网格交易策略",
        }
        
        # 使用配置管理器
        self.config_manager = strategy_config_manager
        logger.info("简化策略管理器初始化完成")
    
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
            
            # 创建策略信息（简化版本，不实际创建策略对象）
            strategy_info = {
                'name': name,
                'strategy_type': strategy_type,
                'config': config,
                'status': 'STOPPED',
                'is_active': False,
                'created_at': logger.handlers[0].formatter.formatTime(logger.makeRecord('', 0, '', 0, '', (), None)),
                # 模拟性能数据
                'total_return': 0.0,
                'win_rate': 0.0,
                'total_trades': 0,
                'max_drawdown': 0.0,
                'sharpe_ratio': 0.0,
                'symbol': config.get('symbol', 'BTC-USDT'),
                'timeframe': config.get('timeframe', '1h')
            }
            
            self.strategies[name] = strategy_info
            
            logger.info(f"策略 {name} 创建成功")
            return True
            
        except Exception as e:
            logger.error(f"创建策略失败: {e}")
            return False
    
    def start_strategy(self, strategy_name: str) -> bool:
        """启动策略"""
        try:
            if strategy_name in self.strategies:
                self.strategies[strategy_name]['status'] = 'RUNNING'
                self.strategies[strategy_name]['is_active'] = True
                logger.info(f"策略 {strategy_name} 已启动")
                return True
            else:
                logger.error(f"策略 {strategy_name} 不存在")
                return False
        except Exception as e:
            logger.error(f"启动策略失败: {e}")
            return False
    
    def stop_strategy(self, strategy_name: str) -> bool:
        """停止策略"""
        try:
            if strategy_name in self.strategies:
                self.strategies[strategy_name]['status'] = 'STOPPED'
                self.strategies[strategy_name]['is_active'] = False
                logger.info(f"策略 {strategy_name} 已停止")
                return True
            else:
                logger.error(f"策略 {strategy_name} 不存在")
                return False
        except Exception as e:
            logger.error(f"停止策略失败: {e}")
            return False
    
    def remove_strategy(self, strategy_name: str) -> bool:
        """移除策略"""
        try:
            if strategy_name in self.strategies:
                # 先停止策略
                self.stop_strategy(strategy_name)
                # 然后移除
                del self.strategies[strategy_name]
                logger.info(f"策略 {strategy_name} 已移除")
                return True
            else:
                logger.error(f"策略 {strategy_name} 不存在")
                return False
        except Exception as e:
            logger.error(f"移除策略失败: {e}")
            return False
    
    def get_strategy_status(self, strategy_name: str) -> Optional[Dict]:
        """获取策略状态"""
        return self.strategies.get(strategy_name)
    
    def get_all_strategies_status(self) -> Dict[str, Any]:
        """获取所有策略状态"""
        return self.strategies.copy()
    
    def get_strategies_list(self) -> List[Dict]:
        """获取策略列表"""
        return list(self.strategies.values())
    
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
    
    def get_engine_status(self) -> Dict[str, Any]:
        """获取引擎状态"""
        running_count = len([s for s in self.strategies.values() if s['status'] == 'RUNNING'])
        total_count = len(self.strategies)
        
        return {
            'status': 'running',
            'total_strategies': total_count,
            'running_strategies': running_count,
            'stopped_strategies': total_count - running_count,
            'uptime': '模拟运行时间',
            'last_update': logger.handlers[0].formatter.formatTime(logger.makeRecord('', 0, '', 0, '', (), None))
        } 