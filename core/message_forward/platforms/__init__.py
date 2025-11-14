"""
消息平台实现
"""

from typing import Optional, Dict, Any

# 从父目录导入MessagePlatform基类
from ..base import MessagePlatform

from .telegram_mtproto import TelegramMTProtoPlatform
try:
    from .dingtalk import DingTalkPlatform
except ImportError:
    DingTalkPlatform = None
try:
    from .wechat import WeChatPlatform
except ImportError:
    WeChatPlatform = None
try:
    from .wechat_official import WeChatOfficialPlatform
except ImportError:
    WeChatOfficialPlatform = None
try:
    from .bicoin import BicoinPlatform
except ImportError:
    BicoinPlatform = None
try:
    from .coinglass import CoinGlassPlatform
except ImportError:
    CoinGlassPlatform = None
try:
    from .tradingview import TradingViewPlatform
except ImportError:
    TradingViewPlatform = None
try:
    from .wxauto_wechat import WxAutoWeChatPlatform
except ImportError:
    WxAutoWeChatPlatform = None

__all__ = [
    'TelegramMTProtoPlatform',
    'DingTalkPlatform',
    'WeChatPlatform',
    'WeChatOfficialPlatform',
    'BicoinPlatform',
    'CoinGlassPlatform',
    'TradingViewPlatform',
    'WxAutoWeChatPlatform',
    'create_platform_instance'
]


def create_platform_instance(platform_type: str, config: Dict[str, Any]) -> Optional[MessagePlatform]:
    """
    创建平台实例的工厂函数
    
    Args:
        platform_type: 平台类型 (telegram, dingtalk, wechat, wechat_official, bicoin, coinglass, tradingview)
        config: 平台配置字典
    
    Returns:
        平台实例，如果不支持的类型返回None
    """
    platform_type_lower = platform_type.lower()
    
    if platform_type_lower in ('telegram', 'telegram_mtproto'):
        return TelegramMTProtoPlatform(config)
    elif platform_type_lower == 'dingtalk' and DingTalkPlatform is not None:
        return DingTalkPlatform(config)
    elif platform_type_lower == 'wechat_official' and WeChatOfficialPlatform is not None:
        return WeChatOfficialPlatform(config)
    elif platform_type_lower in ('wechat', 'wxauto') and WxAutoWeChatPlatform is not None:
        return WxAutoWeChatPlatform(config)
    elif platform_type_lower == 'bicoin' and BicoinPlatform is not None:
        return BicoinPlatform(config)
    elif platform_type_lower == 'coinglass' and CoinGlassPlatform is not None:
        return CoinGlassPlatform(config)
    elif platform_type_lower == 'tradingview' and TradingViewPlatform is not None:
        return TradingViewPlatform(config)
    else:
        return None

