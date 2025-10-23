"""
事件系统
提供事件驱动的架构支持
"""

from abc import ABC, abstractmethod
from typing import Dict, List, Any, Callable, Optional
from datetime import datetime
from dataclasses import dataclass
import asyncio
import threading
from queue import Queue, Empty
import time

from utils.logger import get_logger

logger = get_logger(__name__)

@dataclass
class Event:
    """基础事件"""
    type: str
    data: Any
    timestamp: datetime = None
    
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now()

@dataclass
class MarketDataEvent(Event):
    """市场数据事件"""
    def __init__(self, symbol: str, data: Dict[str, Any], timestamp: datetime = None):
        super().__init__(
            type="market_data",
            data={
                "symbol": symbol,
                "data": data
            },
            timestamp=timestamp
        )

@dataclass
class SignalEvent(Event):
    """信号事件"""
    def __init__(self, signal: Dict[str, Any], timestamp: datetime = None):
        super().__init__(
            type="signal",
            data=signal,
            timestamp=timestamp
        )

@dataclass
class OrderEvent(Event):
    """委托事件"""
    def __init__(self, order: Dict[str, Any], timestamp: datetime = None):
        super().__init__(
            type="order",
            data=order,
            timestamp=timestamp
        )

@dataclass
class TradeEvent(Event):
    """成交事件"""
    def __init__(self, trade: Dict[str, Any], timestamp: datetime = None):
        super().__init__(
            type="trade",
            data=trade,
            timestamp=timestamp
        )

class IEventEngine(ABC):
    """事件引擎接口"""
    
    @abstractmethod
    def register(self, event_type: str, handler: Callable) -> None:
        """注册事件处理器"""
        pass
    
    @abstractmethod
    def unregister(self, event_type: str, handler: Callable) -> None:
        """注销事件处理器"""
        pass
    
    @abstractmethod
    def put(self, event: Event) -> None:
        """发送事件"""
        pass
    
    @abstractmethod
    def start(self) -> None:
        """启动事件引擎"""
        pass
    
    @abstractmethod
    def stop(self) -> None:
        """停止事件引擎"""
        pass

class EventEngine(IEventEngine):
    """事件引擎实现"""
    
    def __init__(self):
        self.handlers: Dict[str, List[Callable]] = {}
        self.event_queue = Queue()
        self.running = False
        self.thread = None
        
        logger.info("事件引擎初始化完成")
    
    def register(self, event_type: str, handler: Callable) -> None:
        """注册事件处理器"""
        if event_type not in self.handlers:
            self.handlers[event_type] = []
        
        if handler not in self.handlers[event_type]:
            self.handlers[event_type].append(handler)
            logger.info(f"注册事件处理器: {event_type}")
    
    def unregister(self, event_type: str, handler: Callable) -> None:
        """注销事件处理器"""
        if event_type in self.handlers and handler in self.handlers[event_type]:
            self.handlers[event_type].remove(handler)
            logger.info(f"注销事件处理器: {event_type}")
    
    def put(self, event: Event) -> None:
        """发送事件"""
        if self.running:
            self.event_queue.put(event)
    
    def start(self) -> None:
        """启动事件引擎"""
        if self.running:
            return
        
        self.running = True
        self.thread = threading.Thread(target=self._process_events, daemon=True)
        self.thread.start()
        logger.info("事件引擎启动")
    
    def stop(self) -> None:
        """停止事件引擎"""
        self.running = False
        if self.thread:
            self.thread.join(timeout=1)
        logger.info("事件引擎停止")
    
    def _process_events(self) -> None:
        """处理事件循环"""
        while self.running:
            try:
                # 获取事件，设置超时避免阻塞
                event = self.event_queue.get(timeout=0.1)
                self._handle_event(event)
            except Empty:
                continue
            except Exception as e:
                logger.error(f"处理事件时出错: {e}")
    
    def _handle_event(self, event: Event) -> None:
        """处理单个事件"""
        event_type = event.type
        
        if event_type in self.handlers:
            for handler in self.handlers[event_type]:
                try:
                    handler(event)
                except Exception as e:
                    logger.error(f"事件处理器执行失败: {e}")
        else:
            logger.warning(f"未找到事件处理器: {event_type}")

class AsyncEventEngine(IEventEngine):
    """异步事件引擎"""
    
    def __init__(self):
        self.handlers: Dict[str, List[Callable]] = {}
        self.event_queue = asyncio.Queue()
        self.running = False
        self.task = None
        
        logger.info("异步事件引擎初始化完成")
    
    def register(self, event_type: str, handler: Callable) -> None:
        """注册事件处理器"""
        if event_type not in self.handlers:
            self.handlers[event_type] = []
        
        if handler not in self.handlers[event_type]:
            self.handlers[event_type].append(handler)
            logger.info(f"注册异步事件处理器: {event_type}")
    
    def unregister(self, event_type: str, handler: Callable) -> None:
        """注销事件处理器"""
        if event_type in self.handlers and handler in self.handlers[event_type]:
            self.handlers[event_type].remove(handler)
            logger.info(f"注销异步事件处理器: {event_type}")
    
    def put(self, event: Event) -> None:
        """发送事件"""
        if self.running:
            asyncio.create_task(self._put_event(event))
    
    async def _put_event(self, event: Event) -> None:
        """异步发送事件"""
        await self.event_queue.put(event)
    
    def start(self) -> None:
        """启动异步事件引擎"""
        if self.running:
            return
        
        self.running = True
        self.task = asyncio.create_task(self._process_events())
        logger.info("异步事件引擎启动")
    
    def stop(self) -> None:
        """停止异步事件引擎"""
        self.running = False
        if self.task:
            self.task.cancel()
        logger.info("异步事件引擎停止")
    
    async def _process_events(self) -> None:
        """异步处理事件循环"""
        while self.running:
            try:
                event = await asyncio.wait_for(self.event_queue.get(), timeout=0.1)
                await self._handle_event(event)
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                logger.error(f"异步处理事件时出错: {e}")
    
    async def _handle_event(self, event: Event) -> None:
        """异步处理单个事件"""
        event_type = event.type
        
        if event_type in self.handlers:
            for handler in self.handlers[event_type]:
                try:
                    if asyncio.iscoroutinefunction(handler):
                        await handler(event)
                    else:
                        handler(event)
                except Exception as e:
                    logger.error(f"异步事件处理器执行失败: {e}")
        else:
            logger.warning(f"未找到异步事件处理器: {event_type}")

# 创建全局事件引擎实例
event_engine = EventEngine()
async_event_engine = AsyncEventEngine()
