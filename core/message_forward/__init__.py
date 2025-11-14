"""
消息转发模块
支持 Telegram、钉钉、微信等多平台消息监听和转发

使用方法:
    from core.message_forward import MessageForwardManager, Message
    
    # 创建管理器
    manager = await MessageForwardManager.create_from_config(config)
    
    # 启动服务
    await manager.start()
"""

from .manager import MessageForwardManager, get_message_forward_manager, set_message_forward_manager
from .models import Message, MessageType, PlatformType, ForwardRule
from .base import MessagePlatform
from .platforms import TelegramMTProtoPlatform, DingTalkPlatform, WeChatPlatform, BicoinPlatform, CoinGlassPlatform

__all__ = [
    'MessageForwardManager',
    'get_message_forward_manager',
    'set_message_forward_manager',
    'Message',
    'MessageType',
    'PlatformType',
    'ForwardRule',
    'MessagePlatform',
    'TelegramMTProtoPlatform',
    'DingTalkPlatform',
    'WeChatPlatform',
    'BicoinPlatform',
    'CoinGlassPlatform'
]

__version__ = '1.0.0'

