"""
消息平台实现
"""

from .telegram import TelegramPlatform
from .dingtalk import DingTalkPlatform
from .wechat import WeChatPlatform

__all__ = [
    'TelegramPlatform',
    'DingTalkPlatform',
    'WeChatPlatform'
]

