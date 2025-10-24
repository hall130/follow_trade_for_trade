"""
策略自动扫描器
自动发现和注册 strategies 目录下的所有策略类
"""

import os
import sys
import importlib
import inspect
from pathlib import Path
from typing import Dict, List, Type, Optional, Any
from dataclasses import dataclass

from .core.strategy import IStrategy, BaseStrategy
from .strategies.base import StrategyBase
from utils.logger import get_logger

logger = get_logger(__name__)

@dataclass
class StrategyMetadata:
    """策略元数据"""
    name: str
    class_name: str
    display_name: str
    description: str
    module_path: str
    category: str
    file_path: str
    strategy_class: Optional[Type[IStrategy]] = None

class StrategyScanner:
    """策略扫描器 - 自动发现和注册策略"""
    
    def __init__(self, strategies_dir: str = None):
        if strategies_dir is None:
            # 默认扫描 strategies 目录
            current_dir = Path(__file__).parent
            self.strategies_dir = current_dir / "strategies"
        else:
            self.strategies_dir = Path(strategies_dir)
        
        self.discovered_strategies: Dict[str, StrategyMetadata] = {}
        logger.info(f"策略扫描器初始化: {self.strategies_dir}")
    
    def scan_all_strategies(self) -> Dict[str, StrategyMetadata]:
        """扫描所有策略"""
        logger.info("🔍 开始扫描策略文件...")
        
        # 扫描 technical 和 advanced 目录
        technical_dir = self.strategies_dir / "technical"
        advanced_dir = self.strategies_dir / "advanced"
        
        if technical_dir.exists():
            self._scan_directory(technical_dir, "技术指标")
        
        if advanced_dir.exists():
            self._scan_directory(advanced_dir, "高级策略")
        
        logger.info(f"✅ 扫描完成，发现 {len(self.discovered_strategies)} 个策略")
        return self.discovered_strategies
    
    def _scan_directory(self, directory: Path, category: str):
        """扫描指定目录"""
        logger.info(f"📁 扫描目录: {directory} (分类: {category})")
        
        for file_path in directory.glob("*.py"):
            # 跳过 __init__.py 和私有文件
            if file_path.name.startswith('_'):
                continue
            
            try:
                self._scan_file(file_path, category)
            except Exception as e:
                logger.error(f"扫描文件失败 {file_path}: {e}")
    
    def _scan_file(self, file_path: Path, category: str):
        """扫描单个文件"""
        # 构建模块路径
        # 例如: core.strategy_trade.strategies.technical.rsi
        relative_path = file_path.relative_to(self.strategies_dir.parent)
        module_path = str(relative_path.with_suffix('')).replace(os.sep, '.')
        module_path = f"core.strategy_trade.strategies.{module_path.split('strategies.')[-1]}"
        
        logger.debug(f"尝试导入模块: {module_path}")
        
        try:
            # 动态导入模块
            module = importlib.import_module(module_path)
            
            # 查找策略类
            for name, obj in inspect.getmembers(module, inspect.isclass):
                # 检查是否是策略类
                if (issubclass(obj, (StrategyBase, BaseStrategy)) and 
                    obj not in [StrategyBase, BaseStrategy, IStrategy] and
                    obj.__module__ == module_path):
                    
                    # 提取策略元数据
                    metadata = self._extract_metadata(obj, name, module_path, category, file_path)
                    
                    if metadata:
                        self.discovered_strategies[metadata.name] = metadata
                        logger.info(f"✅ 发现策略: {metadata.name} ({metadata.display_name})")
        
        except Exception as e:
            logger.error(f"导入模块失败 {module_path}: {e}")
            import traceback
            logger.debug(traceback.format_exc())
    
    def _extract_metadata(self, strategy_class: Type, class_name: str, 
                         module_path: str, category: str, file_path: Path) -> Optional[StrategyMetadata]:
        """提取策略元数据"""
        try:
            # 生成策略名称（遵循命名规范）
            strategy_name = f"{class_name.replace('Strategy', '')}_Strategy"
            if not strategy_name.endswith('_Strategy'):
                strategy_name = f"{class_name}_Strategy"
            
            # 从类文档字符串提取信息
            doc = inspect.getdoc(strategy_class) or ""
            lines = doc.split('\n')
            display_name = lines[0].strip() if lines else class_name
            description = lines[1].strip() if len(lines) > 1 else display_name
            
            metadata = StrategyMetadata(
                name=strategy_name,
                class_name=class_name,
                display_name=display_name,
                description=description,
                module_path=module_path,
                category=category,
                file_path=str(file_path),
                strategy_class=strategy_class
            )
            
            return metadata
            
        except Exception as e:
            logger.error(f"提取策略元数据失败 {class_name}: {e}")
            return None
    
    def get_strategy_class(self, strategy_name: str) -> Optional[Type[IStrategy]]:
        """获取策略类"""
        metadata = self.discovered_strategies.get(strategy_name)
        if metadata:
            return metadata.strategy_class
        return None
    
    def get_all_strategy_names(self) -> List[str]:
        """获取所有策略名称"""
        return list(self.discovered_strategies.keys())
    
    def get_strategies_by_category(self, category: str) -> List[StrategyMetadata]:
        """按分类获取策略"""
        return [
            metadata for metadata in self.discovered_strategies.values()
            if metadata.category == category
        ]
    
    def reload_strategies(self):
        """重新加载所有策略"""
        logger.info("🔄 重新扫描策略...")
        self.discovered_strategies.clear()
        self.scan_all_strategies()
    
    def add_custom_strategy(self, strategy_code: str, strategy_name: str, 
                           category: str = "自定义策略") -> bool:
        """
        添加自定义策略
        
        Args:
            strategy_code: 策略代码（Python代码字符串）
            strategy_name: 策略名称
            category: 策略分类
            
        Returns:
            是否添加成功
        """
        try:
            # 创建自定义策略目录
            custom_dir = self.strategies_dir / "custom"
            custom_dir.mkdir(exist_ok=True)
            
            # 确保有 __init__.py
            init_file = custom_dir / "__init__.py"
            if not init_file.exists():
                init_file.write_text("")
            
            # 保存策略代码到文件
            file_name = f"{strategy_name.lower().replace('_strategy', '')}.py"
            file_path = custom_dir / file_name
            
            file_path.write_text(strategy_code, encoding='utf-8')
            logger.info(f"✅ 自定义策略已保存: {file_path}")
            
            # 重新扫描
            self.reload_strategies()
            
            return True
            
        except Exception as e:
            logger.error(f"添加自定义策略失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return False
    
    def generate_strategy_template(self, strategy_name: str, 
                                   display_name: str,
                                   description: str,
                                   parameters: Dict[str, Any]) -> str:
        """
        生成策略代码模板
        
        Args:
            strategy_name: 策略名称
            display_name: 显示名称
            description: 策略描述
            parameters: 策略参数
            
        Returns:
            策略代码字符串
        """
        class_name = strategy_name.replace('_Strategy', 'Strategy')
        
        # 生成参数初始化代码
        param_init = []
        for param_name, param_config in parameters.items():
            default_value = param_config.get('default', 0)
            if isinstance(default_value, str):
                param_init.append(f"        self.{param_name} = config.get('{param_name}', '{default_value}')")
            else:
                param_init.append(f"        self.{param_name} = config.get('{param_name}', {default_value})")
        
        param_init_code = '\n'.join(param_init)
        
        template = f'''"""
{display_name}
{description}
"""

from typing import Dict, Any
from datetime import datetime

from ..base import StrategyBase
from core.strategy_trade.core.strategy import Signal, MarketData
from utils.logger import get_logger

logger = get_logger(__name__)

class {class_name}(StrategyBase):
    """{display_name}"""
    
    def __init__(self, name: str, symbol: str, config: Dict[str, Any]):
        super().__init__(name, symbol, config)
        
        # 策略参数
{param_init_code}
        
        logger.info(f"{display_name}初始化: {{self.name}}")
    
    def on_market_data(self, data: MarketData) -> None:
        """处理市场数据"""
        # TODO: 在这里实现你的策略逻辑
        
        # 确保有足够的数据
        if len(self.price_data) < 50:
            return
        
        current_price = data.close
        
        # 示例：简单的买入信号
        # 你可以根据需要修改这里的逻辑
        if self._should_buy(current_price):
            signal = Signal(
                symbol=self.symbol,
                side='BUY',
                price=current_price,
                quantity=self.calculate_position_size(current_price),
                timestamp=datetime.now(),
                reason="买入信号"
            )
            self.pending_signals.append(signal)
            logger.info(f"✅ 生成买入信号: {{current_price}}")
    
    def _should_buy(self, price: float) -> bool:
        """判断是否应该买入"""
        # TODO: 实现你的买入逻辑
        return False
    
    def calculate_position_size(self, price: float) -> float:
        """计算仓位大小"""
        # 简单实现：固定数量
        return 1.0
'''
        return template

# 全局扫描器实例
_global_scanner = None

def get_strategy_scanner() -> StrategyScanner:
    """获取全局策略扫描器实例"""
    global _global_scanner
    if _global_scanner is None:
        _global_scanner = StrategyScanner()
        _global_scanner.scan_all_strategies()
    return _global_scanner

