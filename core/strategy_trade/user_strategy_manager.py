"""
用户策略管理器
管理用户上传的自定义策略
"""

import os
import sys
import importlib
import importlib.util
import inspect
from pathlib import Path
from typing import Dict, List, Optional, Type, Any
from datetime import datetime
import json
import hashlib

from .base_strategy import BaseStrategy
from utils.logger import get_logger

logger = get_logger(__name__)


class UserStrategyManager:
    """用户策略管理器"""
    
    def __init__(self, strategies_dir: str = "core/strategy_trade/strategies/user"):
        """
        初始化管理器
        
        Args:
            strategies_dir: 用户策略存储目录
        """
        self.strategies_dir = Path(strategies_dir)
        self.strategies_dir.mkdir(parents=True, exist_ok=True)
        
        # 策略注册表 {strategy_id: {class, metadata}}
        self.strategies: Dict[str, Dict[str, Any]] = {}
        
        # 加载已有策略
        self.load_all_strategies()
        
        logger.info(f"用户策略管理器初始化: {self.strategies_dir}")
    
    def load_all_strategies(self) -> None:
        """加载所有用户策略"""
        logger.info("开始加载用户策略...")
        
        for file_path in self.strategies_dir.glob("*.py"):
            if file_path.name.startswith('_'):
                continue
            
            try:
                strategy_id = file_path.stem
                self.load_strategy(strategy_id)
            except Exception as e:
                logger.error(f"加载策略失败 {file_path}: {e}")
        
        logger.info(f"已加载 {len(self.strategies)} 个用户策略")
    
    def load_strategy(self, strategy_id: str) -> Optional[Type[BaseStrategy]]:
        """
        加载单个策略
        
        Args:
            strategy_id: 策略ID（文件名，不含.py）
            
        Returns:
            策略类或None
        """
        file_path = self.strategies_dir / f"{strategy_id}.py"
        
        if not file_path.exists():
            logger.warning(f"策略文件不存在: {file_path}")
            return None
        
        try:
            # 动态导入模块
            spec = importlib.util.spec_from_file_location(
                f"user_strategy_{strategy_id}",
                file_path
            )
            
            if spec is None or spec.loader is None:
                raise ImportError(f"无法创建模块规范: {strategy_id}")
            
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            
            # 查找策略类（继承自BaseStrategy的类）
            strategy_class = None
            for name, obj in inspect.getmembers(module, inspect.isclass):
                if (obj != BaseStrategy and 
                    issubclass(obj, BaseStrategy) and 
                    obj.__module__ == module.__name__):
                    strategy_class = obj
                    break
            
            if not strategy_class:
                raise ValueError(f"未找到继承BaseStrategy的类: {strategy_id}")
            
            # 提取策略元数据
            metadata = self._extract_metadata(strategy_class, file_path)
            
            # 注册策略
            self.strategies[strategy_id] = {
                'class': strategy_class,
                'metadata': metadata,
                'file_path': str(file_path),
                'loaded_at': datetime.now().isoformat()
            }
            
            logger.info(f"✅ 成功加载用户策略: {strategy_id}")
            return strategy_class
            
        except Exception as e:
            logger.error(f"加载策略失败 {strategy_id}: {e}")
            import traceback
            logger.debug(traceback.format_exc())
            return None
    
    def _extract_metadata(self, strategy_class: Type[BaseStrategy], file_path: Path) -> Dict[str, Any]:
        """提取策略元数据"""
        metadata = {
            'name': strategy_class.__name__,
            'description': inspect.getdoc(strategy_class) or '',
            'file_path': str(file_path),
            'file_size': file_path.stat().st_size,
            'file_hash': self._calculate_file_hash(file_path)
        }
        
        # 尝试从类文档字符串获取更多信息
        doc = metadata['description']
        if doc:
            lines = doc.split('\n')
            metadata['short_description'] = lines[0].strip() if lines else ''
        
        return metadata
    
    def _calculate_file_hash(self, file_path: Path) -> str:
        """计算文件哈希值"""
        with open(file_path, 'rb') as f:
            return hashlib.md5(f.read()).hexdigest()
    
    def save_strategy(self, strategy_id: str, code: str, metadata: Dict[str, Any] = None) -> bool:
        """
        保存用户策略
        
        Args:
            strategy_id: 策略ID
            code: Python代码字符串
            metadata: 策略元数据（可选）
            
        Returns:
            是否保存成功
        """
        try:
            # 验证代码语法
            compile(code, f'<strategy_{strategy_id}>', 'exec')
            
            file_path = self.strategies_dir / f"{strategy_id}.py"
            
            # 保存代码
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(code)
            
            # 保存元数据（如果有）
            if metadata:
                metadata_path = self.strategies_dir / f"{strategy_id}.json"
                with open(metadata_path, 'w', encoding='utf-8') as f:
                    json.dump(metadata, f, indent=2, ensure_ascii=False)
            
            # 重新加载策略
            self.load_strategy(strategy_id)
            
            logger.info(f"✅ 策略已保存: {strategy_id}")
            return True
            
        except SyntaxError as e:
            logger.error(f"策略代码语法错误 {strategy_id}: {e}")
            raise ValueError(f"代码语法错误: {str(e)}")
        except Exception as e:
            logger.error(f"保存策略失败 {strategy_id}: {e}")
            return False
    
    def delete_strategy(self, strategy_id: str) -> bool:
        """删除策略"""
        try:
            file_path = self.strategies_dir / f"{strategy_id}.py"
            metadata_path = self.strategies_dir / f"{strategy_id}.json"
            
            if file_path.exists():
                file_path.unlink()
            
            if metadata_path.exists():
                metadata_path.unlink()
            
            if strategy_id in self.strategies:
                del self.strategies[strategy_id]
            
            logger.info(f"✅ 策略已删除: {strategy_id}")
            return True
            
        except Exception as e:
            logger.error(f"删除策略失败 {strategy_id}: {e}")
            return False
    
    def get_strategy(self, strategy_id: str) -> Optional[Type[BaseStrategy]]:
        """获取策略类"""
        if strategy_id in self.strategies:
            return self.strategies[strategy_id]['class']
        return None
    
    def get_strategy_metadata(self, strategy_id: str) -> Optional[Dict[str, Any]]:
        """获取策略元数据"""
        if strategy_id in self.strategies:
            return self.strategies[strategy_id]['metadata']
        return None
    
    def list_strategies(self) -> List[Dict[str, Any]]:
        """列出所有策略"""
        result = []
        for strategy_id, info in self.strategies.items():
            result.append({
                'id': strategy_id,
                'name': info['metadata'].get('name', strategy_id),
                'description': info['metadata'].get('description', ''),
                'loaded_at': info.get('loaded_at', ''),
                **info['metadata']
            })
        return result
    
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
            return None
    
    def validate_strategy_code(self, code: str) -> tuple[bool, Optional[str]]:
        """
        验证策略代码
        
        Args:
            code: Python代码字符串
            
        Returns:
            (是否有效, 错误信息)
        """
        try:
            # 语法检查
            compile(code, '<validation>', 'exec')
            
            # 检查是否包含策略类
            # 这里可以添加更多验证逻辑
            if 'class' not in code or 'BaseStrategy' not in code:
                return False, "代码必须包含继承BaseStrategy的类"
            
            return True, None
            
        except SyntaxError as e:
            return False, f"语法错误: {str(e)}"
        except Exception as e:
            return False, f"验证失败: {str(e)}"
    
    def get_strategy_code(self, strategy_id: str) -> Optional[str]:
        """获取策略代码"""
        file_path = self.strategies_dir / f"{strategy_id}.py"
        if file_path.exists():
            with open(file_path, 'r', encoding='utf-8') as f:
                return f.read()
        return None


# 全局管理器实例
_user_strategy_manager = None

def get_user_strategy_manager() -> UserStrategyManager:
    """获取全局用户策略管理器实例"""
    global _user_strategy_manager
    if _user_strategy_manager is None:
        _user_strategy_manager = UserStrategyManager()
    return _user_strategy_manager

