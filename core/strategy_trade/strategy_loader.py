"""
策略加载器
统一加载系统策略和用户策略
"""

from typing import Dict, List, Optional, Type, Any
from pathlib import Path
import importlib
import inspect

from .base_strategy import BaseStrategy
from .user_strategy_manager import get_user_strategy_manager
from utils.logger import get_logger

logger = get_logger(__name__)


class StrategyLoader:
    """策略加载器 - 统一加载所有策略"""
    
    def __init__(self):
        self.system_strategies: Dict[str, Type[BaseStrategy]] = {}
        self.user_strategies: Dict[str, Type[BaseStrategy]] = {}
        self.user_manager = get_user_strategy_manager()
        
        # 加载系统策略
        self.load_system_strategies()
        
        # 加载用户策略
        self.load_user_strategies()
    
    def load_system_strategies(self) -> None:
        """加载系统内置策略"""
        logger.info("加载系统策略...")
        
        # 扫描strategies目录下的所有策略
        strategies_dir = Path(__file__).parent / "strategies"
        
        for category_dir in ['technical', 'advanced']:
            category_path = strategies_dir / category_dir
            if not category_path.exists():
                continue
            
            for file_path in category_path.glob("*.py"):
                if file_path.name.startswith('_'):
                    continue
                
                try:
                    self._load_strategy_file(file_path, 'system')
                except Exception as e:
                    logger.error(f"加载系统策略失败 {file_path}: {e}")
        
        logger.info(f"已加载 {len(self.system_strategies)} 个系统策略")
    
    def load_user_strategies(self) -> None:
        """加载用户策略"""
        logger.info("加载用户策略...")
        
        user_strategies = self.user_manager.list_strategies()
        for strategy_info in user_strategies:
            strategy_id = strategy_info['id']
            strategy_class = self.user_manager.get_strategy(strategy_id)
            
            if strategy_class:
                self.user_strategies[strategy_id] = strategy_class
                logger.info(f"✅ 加载用户策略: {strategy_id}")
        
        logger.info(f"已加载 {len(self.user_strategies)} 个用户策略")
    
    def _load_strategy_file(self, file_path: Path, source: str) -> None:
        """加载策略文件"""
        # 构建模块路径
        # 从 core/strategy_trade/strategies/technical/ma_cross.py
        # 转换为 core.strategy_trade.strategies.technical.ma_cross
        base_dir = Path(__file__).parent  # core/strategy_trade
        relative_path = file_path.relative_to(base_dir.parent.parent)  # 相对于项目根目录
        module_path = str(relative_path.with_suffix('')).replace('\\', '.').replace('/', '.')
        
        try:
            module = importlib.import_module(module_path)
            
            # 查找策略类
            for name, obj in inspect.getmembers(module, inspect.isclass):
                if (obj != BaseStrategy and 
                    issubclass(obj, BaseStrategy) and 
                    obj.__module__ == module_path):
                    
                    # 生成策略ID
                    strategy_id = self._generate_strategy_id(name, source)
                    
                    if source == 'system':
                        self.system_strategies[strategy_id] = obj
                    else:
                        self.user_strategies[strategy_id] = obj
                    
                    logger.debug(f"发现策略: {strategy_id} ({name})")
        
        except Exception as e:
            logger.error(f"导入模块失败 {module_path}: {e}")
    
    def _generate_strategy_id(self, class_name: str, source: str) -> str:
        """生成策略ID"""
        # 移除Strategy后缀
        if class_name.endswith('Strategy'):
            name = class_name[:-8]
        else:
            name = class_name
        
        # 转换为下划线格式
        strategy_id = name + '_Strategy'
        
        return strategy_id
    
    def get_strategy(self, strategy_id: str) -> Optional[Type[BaseStrategy]]:
        """
        获取策略类
        
        Args:
            strategy_id: 策略ID
            
        Returns:
            策略类或None
        """
        # 优先查找系统策略
        if strategy_id in self.system_strategies:
            return self.system_strategies[strategy_id]
        
        # 查找用户策略
        if strategy_id in self.user_strategies:
            return self.user_strategies[strategy_id]
        
        # 尝试从用户管理器重新加载
        strategy_class = self.user_manager.get_strategy(strategy_id)
        if strategy_class:
            self.user_strategies[strategy_id] = strategy_class
            return strategy_class
        
        return None
    
    def list_all_strategies(self) -> Dict[str, List[Dict[str, Any]]]:
        """列出所有策略"""
        system_list = []
        for strategy_id, strategy_class in self.system_strategies.items():
            system_list.append({
                'id': strategy_id,
                'name': strategy_class.__name__,
                'description': inspect.getdoc(strategy_class) or '',
                'source': 'system'
            })
        
        user_list = []
        for strategy_id, strategy_class in self.user_strategies.items():
            metadata = self.user_manager.get_strategy_metadata(strategy_id) or {}
            user_list.append({
                'id': strategy_id,
                'name': metadata.get('name', strategy_class.__name__),
                'description': metadata.get('description', ''),
                'source': 'user',
                **metadata
            })
        
        return {
            'system': system_list,
            'user': user_list,
            'total': len(system_list) + len(user_list)
        }
    
    def create_strategy_instance(self, strategy_id: str, name: str, 
                                 symbol: str, config: Dict[str, Any]) -> Optional[BaseStrategy]:
        """
        创建策略实例
        
        Args:
            strategy_id: 策略ID
            name: 策略实例名称
            symbol: 交易对
            config: 配置
            
        Returns:
            策略实例或None
        """
        strategy_class = self.get_strategy(strategy_id)
        if not strategy_class:
            logger.error(f"策略不存在: {strategy_id}")
            return None
        
        try:
            instance = strategy_class(name, symbol, config)
            return instance
        except Exception as e:
            logger.error(f"创建策略实例失败 {strategy_id}: {e}")
            import traceback
            logger.debug(traceback.format_exc())
            return None
    
    def reload_user_strategies(self) -> None:
        """重新加载用户策略"""
        logger.info("重新加载用户策略...")
        self.user_strategies.clear()
        self.user_manager.load_all_strategies()
        self.load_user_strategies()


# 全局加载器实例
_strategy_loader = None

def get_strategy_loader() -> StrategyLoader:
    """获取全局策略加载器实例"""
    global _strategy_loader
    if _strategy_loader is None:
        _strategy_loader = StrategyLoader()
    return _strategy_loader

