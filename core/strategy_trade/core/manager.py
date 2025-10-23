"""
策略管理器
提供策略的生命周期管理和监控功能
"""

from abc import ABC, abstractmethod
from typing import Dict, List, Any, Optional, Union, Type
from datetime import datetime
from dataclasses import dataclass
import asyncio
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor

from .strategy import IStrategy, BaseStrategy
from .backtest import IBacktestEngine, BacktestEngine, BacktestConfig, BacktestResult
from .events import EventEngine, Event
from utils.logger import get_logger

logger = get_logger(__name__)

@dataclass
class StrategyInfo:
    """策略信息"""
    id: str
    name: str
    strategy_type: str
    strategy: IStrategy
    status: str  # 'STOPPED', 'RUNNING', 'PAUSED', 'ERROR'
    created_time: datetime
    last_update: datetime
    performance: Dict[str, Any]
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            'id': self.id,
            'name': self.name,
            'strategy_type': self.strategy_type,
            'status': self.status,
            'created_time': self.created_time.isoformat(),
            'last_update': self.last_update.isoformat(),
            'performance': self.performance
        }

class IStrategyManager(ABC):
    """策略管理器接口"""
    
    @abstractmethod
    def add_strategy(self, strategy: IStrategy, strategy_type: str) -> str:
        """添加策略"""
        pass
    
    @abstractmethod
    def remove_strategy(self, strategy_id: str) -> bool:
        """移除策略"""
        pass
    
    @abstractmethod
    def start_strategy(self, strategy_id: str) -> bool:
        """启动策略"""
        pass
    
    @abstractmethod
    def stop_strategy(self, strategy_id: str) -> bool:
        """停止策略"""
        pass
    
    @abstractmethod
    def pause_strategy(self, strategy_id: str) -> bool:
        """暂停策略"""
        pass
    
    @abstractmethod
    def resume_strategy(self, strategy_id: str) -> bool:
        """恢复策略"""
        pass
    
    @abstractmethod
    def get_strategy(self, strategy_id: str) -> Optional[StrategyInfo]:
        """获取策略信息"""
        pass
    
    @abstractmethod
    def get_all_strategies(self) -> List[StrategyInfo]:
        """获取所有策略"""
        pass
    
    @abstractmethod
    def run_backtest(self, strategy_id: str, data: Any, config: BacktestConfig) -> Optional[BacktestResult]:
        """运行回测"""
        pass

class StrategyManager(IStrategyManager):
    """策略管理器实现"""
    
    def __init__(self, backtest_engine: Optional[IBacktestEngine] = None):
        self.strategies: Dict[str, StrategyInfo] = {}
        self.strategy_types: Dict[str, Type[IStrategy]] = {}
        self.backtest_engine = backtest_engine or BacktestEngine()
        self.event_engine = EventEngine()
        self.monitoring = False
        self.monitor_thread = None
        
        # 注册策略类型
        self._register_default_strategies()
        
        logger.info("策略管理器初始化完成")
    
    def _register_default_strategies(self) -> None:
        """注册默认策略类型"""
        # 这里可以注册默认的策略类型
        # 具体实现将在策略模块中完成
        pass
    
    def register_strategy_type(self, strategy_type: str, strategy_class: Type[IStrategy]) -> None:
        """注册策略类型"""
        self.strategy_types[strategy_type] = strategy_class
        logger.info(f"注册策略类型: {strategy_type}")
    
    def add_strategy(self, strategy: IStrategy, strategy_type: str) -> str:
        """添加策略"""
        strategy_id = str(uuid.uuid4())
        
        strategy_info = StrategyInfo(
            id=strategy_id,
            name=strategy.name,
            strategy_type=strategy_type,
            strategy=strategy,
            status='STOPPED',
            created_time=datetime.now(),
            last_update=datetime.now(),
            performance={}
        )
        
        self.strategies[strategy_id] = strategy_info
        
        logger.info(f"添加策略: {strategy.name} (ID: {strategy_id})")
        return strategy_id
    
    def remove_strategy(self, strategy_id: str) -> bool:
        """移除策略"""
        if strategy_id not in self.strategies:
            logger.warning(f"策略不存在: {strategy_id}")
            return False
        
        strategy_info = self.strategies[strategy_id]
        
        # 如果策略正在运行，先停止
        if strategy_info.status == 'RUNNING':
            self.stop_strategy(strategy_id)
        
        del self.strategies[strategy_id]
        logger.info(f"移除策略: {strategy_info.name} (ID: {strategy_id})")
        return True
    
    def start_strategy(self, strategy_id: str) -> bool:
        """启动策略"""
        if strategy_id not in self.strategies:
            logger.warning(f"策略不存在: {strategy_id}")
            return False
        
        strategy_info = self.strategies[strategy_id]
        
        if strategy_info.status == 'RUNNING':
            logger.warning(f"策略已在运行: {strategy_info.name}")
            return True
        
        try:
            # 使用线程池异步启动策略，避免阻塞
            if not hasattr(self, '_executor'):
                self._executor = ThreadPoolExecutor(max_workers=4)
            
            # 异步启动策略
            future = self._executor.submit(self._start_strategy_async, strategy_info)
            
            # 立即返回，不等待完成
            strategy_info.status = 'STARTING'
            strategy_info.last_update = datetime.now()
            
            logger.info(f"启动策略: {strategy_info.name}")
            return True
            
        except Exception as e:
            logger.error(f"启动策略失败: {e}")
            strategy_info.status = 'ERROR'
            return False
    
    def _start_strategy_async(self, strategy_info: StrategyInfo) -> None:
        """异步启动策略"""
        try:
            strategy_info.strategy.start()
            strategy_info.status = 'RUNNING'
            strategy_info.last_update = datetime.now()
            logger.info(f"策略启动完成: {strategy_info.name}")
        except Exception as e:
            logger.error(f"策略启动失败: {e}")
            strategy_info.status = 'ERROR'
    
    def stop_strategy(self, strategy_id: str) -> bool:
        """停止策略"""
        if strategy_id not in self.strategies:
            logger.warning(f"策略不存在: {strategy_id}")
            return False
        
        strategy_info = self.strategies[strategy_id]
        
        if strategy_info.status != 'RUNNING':
            logger.warning(f"策略未在运行: {strategy_info.name}")
            return True
        
        try:
            strategy_info.strategy.stop()
            strategy_info.status = 'STOPPED'
            strategy_info.last_update = datetime.now()
            
            logger.info(f"停止策略: {strategy_info.name}")
            return True
            
        except Exception as e:
            logger.error(f"停止策略失败: {e}")
            return False
    
    def pause_strategy(self, strategy_id: str) -> bool:
        """暂停策略"""
        if strategy_id not in self.strategies:
            logger.warning(f"策略不存在: {strategy_id}")
            return False
        
        strategy_info = self.strategies[strategy_id]
        
        if strategy_info.status != 'RUNNING':
            logger.warning(f"策略未在运行: {strategy_info.name}")
            return True
        
        try:
            # 这里可以实现暂停逻辑
            strategy_info.status = 'PAUSED'
            strategy_info.last_update = datetime.now()
            
            logger.info(f"暂停策略: {strategy_info.name}")
            return True
            
        except Exception as e:
            logger.error(f"暂停策略失败: {e}")
            return False
    
    def resume_strategy(self, strategy_id: str) -> bool:
        """恢复策略"""
        if strategy_id not in self.strategies:
            logger.warning(f"策略不存在: {strategy_id}")
            return False
        
        strategy_info = self.strategies[strategy_id]
        
        if strategy_info.status != 'PAUSED':
            logger.warning(f"策略未暂停: {strategy_info.name}")
            return True
        
        try:
            # 这里可以实现恢复逻辑
            strategy_info.status = 'RUNNING'
            strategy_info.last_update = datetime.now()
            
            logger.info(f"恢复策略: {strategy_info.name}")
            return True
            
        except Exception as e:
            logger.error(f"恢复策略失败: {e}")
            return False
    
    def get_strategy(self, strategy_id: str) -> Optional[StrategyInfo]:
        """获取策略信息"""
        return self.strategies.get(strategy_id)
    
    def get_all_strategies(self) -> List[StrategyInfo]:
        """获取所有策略"""
        return list(self.strategies.values())
    
    def run_backtest(self, strategy_id: str, data: Any, config: BacktestConfig) -> Optional[BacktestResult]:
        """运行回测"""
        if strategy_id not in self.strategies:
            logger.warning(f"策略不存在: {strategy_id}")
            return None
        
        strategy_info = self.strategies[strategy_id]
        
        try:
            logger.info(f"开始回测策略: {strategy_info.name}, 类型={strategy_info.strategy_type}")
            
            result = self.backtest_engine.run(strategy_info.strategy, data, config)
            
            logger.info(f"回测完成: {strategy_info.name}")
            return result
            
        except Exception as e:
            logger.error(f"回测失败: {e}")
            logger.error(f"堆栈: {traceback.format_exc()}")
            return None
    
    def start_monitoring(self) -> None:
        """启动监控"""
        if self.monitoring:
            logger.warning("监控已在运行")
            return
        
        self.monitoring = True
        self.monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self.monitor_thread.start()
        logger.info("启动策略监控")
    
    def stop_monitoring(self) -> None:
        """停止监控"""
        self.monitoring = False
        if self.monitor_thread:
            self.monitor_thread.join()
        logger.info("停止策略监控")
    
    def _monitor_loop(self) -> None:
        """监控循环"""
        while self.monitoring:
            try:
                for strategy_info in self.strategies.values():
                    if strategy_info.status == 'RUNNING':
                        # 更新性能数据
                        performance = strategy_info.strategy.get_performance()
                        if performance != strategy_info.performance:
                            strategy_info.performance = performance
                            strategy_info.last_update = datetime.now()
                
                # 休眠1秒
                threading.Event().wait(1)
                
            except Exception as e:
                logger.error(f"监控循环错误: {e}")
    
    def create_strategy(self, strategy_type: str, name: str, symbol: str, config: Dict[str, Any]) -> Optional[str]:
        """创建策略实例"""
        if strategy_type not in self.strategy_types:
            logger.error(f"未注册的策略类型: {strategy_type}")
            return None
        
        try:
            strategy_class = self.strategy_types[strategy_type]
            strategy = strategy_class(name, symbol, config)
            return self.add_strategy(strategy, strategy_type)
            
        except Exception as e:
            logger.error(f"创建策略失败: {e}")
            return None
    
    def get_strategy_types(self) -> List[str]:
        """获取所有策略类型"""
        return list(self.strategy_types.keys())
    
    def export_strategies(self) -> Dict[str, Any]:
        """导出策略配置"""
        export_data = {}
        for strategy_id, strategy_info in self.strategies.items():
            export_data[strategy_id] = {
                'name': strategy_info.name,
                'strategy_type': strategy_info.strategy_type,
                'status': strategy_info.status,
                'created_time': strategy_info.created_time.isoformat(),
                'last_update': strategy_info.last_update.isoformat(),
                'performance': strategy_info.performance
            }
        return export_data
    
    def import_strategies(self, data: Dict[str, Any]) -> bool:
        """导入策略配置"""
        try:
            for strategy_id, info in data.items():
                # 这里可以实现策略配置的导入逻辑
                pass
            return True
        except Exception as e:
            logger.error(f"导入策略配置失败: {e}")
            return False
