"""
消息平台基类
定义统一的消息平台接口
"""

from abc import ABC, abstractmethod
from typing import Callable, Dict, List, Optional, Any
import asyncio

from .models import Message, PlatformType
from utils.logger import get_logger

logger = get_logger(__name__)

class MessagePlatform(ABC):
    """消息平台基类"""
    
    def __init__(self, platform_type: PlatformType, config: Dict[str, Any]):
        self.platform_type = platform_type
        self.config = config
        self.enabled = config.get('enabled', True)
        self.connected = False
        self.message_handlers: List[Callable] = []
        
        logger.info(f"{self.platform_type.value} 平台初始化")
    
    @abstractmethod
    async def connect(self) -> bool:
        """
        连接到消息平台
        
        Returns:
            是否连接成功
        """
        pass
    
    @abstractmethod
    async def disconnect(self) -> bool:
        """
        断开与消息平台的连接
        
        Returns:
            是否断开成功
        """
        pass
    
    @abstractmethod
    async def send_message(self, chat_id: str, message: Message) -> bool:
        """
        发送消息
        
        Args:
            chat_id: 聊天ID/群ID/频道ID
            message: 消息对象
            
        Returns:
            是否发送成功
        """
        pass
    
    @abstractmethod
    async def listen(self, callback: Callable[[Message], None]) -> None:
        """
        监听消息
        
        Args:
            callback: 收到消息时的回调函数
        """
        pass
    
    @abstractmethod
    async def get_chat_info(self, chat_id: str) -> Optional[Dict[str, Any]]:
        """
        获取聊天信息
        
        Args:
            chat_id: 聊天ID
            
        Returns:
            聊天信息字典
        """
        pass
    
    def add_message_handler(self, handler: Callable[[Message], None]):
        """添加消息处理器"""
        self.message_handlers.append(handler)
        logger.info(f"已添加消息处理器: {handler.__name__}")
    
    def remove_message_handler(self, handler: Callable[[Message], None]):
        """移除消息处理器"""
        if handler in self.message_handlers:
            self.message_handlers.remove(handler)
            logger.info(f"已移除消息处理器: {handler.__name__}")
    
    async def _handle_message(self, message: Message):
        """处理接收到的消息"""
        logger.debug(f"收到消息: {message.content[:50]}...")
        
        for handler in self.message_handlers:
            try:
                if asyncio.iscoroutinefunction(handler):
                    await handler(message)
                else:
                    handler(message)
            except Exception as e:
                logger.error(f"消息处理器 {handler.__name__} 执行失败: {e}")
    
    def get_status(self) -> Dict[str, Any]:
        """获取平台状态"""
        return {
            'platform': self.platform_type.value,
            'enabled': self.enabled,
            'connected': self.connected,
            'handlers_count': len(self.message_handlers)
        }
    
    async def test_connection(self) -> bool:
        """测试连接"""
        try:
            if not self.connected:
                await self.connect()
            return self.connected
        except Exception as e:
            logger.error(f"{self.platform_type.value} 连接测试失败: {e}")
            return False

