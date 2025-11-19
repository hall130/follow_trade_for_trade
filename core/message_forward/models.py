"""
消息转发数据模型
定义消息的统一数据结构
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
from datetime import datetime
from enum import Enum

class MessageType(Enum):
    """消息类型"""
    TEXT = "text"
    IMAGE = "image"
    FILE = "file"
    LINK = "link"
    MARKDOWN = "markdown"
    CARD = "card"

class PlatformType(Enum):
    """平台类型"""
    TELEGRAM = "telegram"
    DINGTALK = "dingtalk"
    WECHAT = "wechat"
    WECHAT_OFFICIAL = "wechat_official"  # 微信公众号平台
    BICOIN = "bicoin"  # 币coin平台
    COINGLASS = "coinglass"  # CoinGlass平台
    TRADINGVIEW = "tradingview"  # TradingView平台

@dataclass
class Message:
    """统一消息模型"""
    content: str
    message_type: MessageType = MessageType.TEXT
    timestamp: datetime = field(default_factory=datetime.now)
    source_platform_id: Optional[int] = None  # 源平台ID（关联message_platforms.id）
    source_platform: Optional[PlatformType] = None
    source_chat_id: Optional[str] = None
    source_chat_title: Optional[str] = None  # 源群组标题
    source_user_id: Optional[str] = None
    source_username: Optional[str] = None
    extra_data: Dict[str, Any] = field(default_factory=dict)
    
    # 消息元数据
    message_id: Optional[str] = None
    reply_to_message_id: Optional[str] = None
    
    # 附件
    attachments: List[str] = field(default_factory=list)
    
    # 格式化内容（Markdown等）
    formatted_content: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            'content': self.content,
            'message_type': self.message_type.value if self.message_type else None,
            'timestamp': self.timestamp.isoformat(),
            'source_platform': self.source_platform.value if self.source_platform else None,
            'source_chat_id': self.source_chat_id,
            'source_user_id': self.source_user_id,
            'source_username': self.source_username,
            'message_id': self.message_id,
            'reply_to_message_id': self.reply_to_message_id,
            'attachments': self.attachments,
            'formatted_content': self.formatted_content,
            'extra_data': self.extra_data
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Message':
        """从字典创建"""
        return cls(
            content=data.get('content', ''),
            message_type=MessageType(data['message_type']) if data.get('message_type') else MessageType.TEXT,
            timestamp=datetime.fromisoformat(data['timestamp']) if data.get('timestamp') else datetime.now(),
            source_platform=PlatformType(data['source_platform']) if data.get('source_platform') else None,
            source_chat_id=data.get('source_chat_id'),
            source_user_id=data.get('source_user_id'),
            source_username=data.get('source_username'),
            message_id=data.get('message_id'),
            reply_to_message_id=data.get('reply_to_message_id'),
            attachments=data.get('attachments', []),
            formatted_content=data.get('formatted_content'),
            extra_data=data.get('extra_data', {})
        )

@dataclass
class PlatformConfig:
    """平台配置"""
    platform_type: str  # telegram, dingtalk, wechat
    platform_name: str
    enabled: bool = True
    config: Dict[str, Any] = field(default_factory=dict)
    
    # 状态信息
    status: str = 'inactive'  # inactive, active, error
    error_message: Optional[str] = None
    last_connected_at: Optional[datetime] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            'platform_type': self.platform_type,
            'platform_name': self.platform_name,
            'enabled': self.enabled,
            'config': self.config,
            'status': self.status,
            'error_message': self.error_message,
            'last_connected_at': self.last_connected_at.isoformat() if self.last_connected_at else None
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'PlatformConfig':
        """从字典创建"""
        return cls(
            platform_type=data['platform_type'],
            platform_name=data['platform_name'],
            enabled=data.get('enabled', True),
            config=data.get('config', {}),
            status=data.get('status', 'inactive'),
            error_message=data.get('error_message'),
            last_connected_at=datetime.fromisoformat(data['last_connected_at']) if data.get('last_connected_at') else None
        )

@dataclass
class ForwardRule:
    """转发规则"""
    rule_id: str
    rule_name: str
    enabled: bool = True
    
    # 源配置
    source_platform_id: Optional[int] = None  # 源平台ID（优先使用，支持选择具体账户）
    source_platform: str = ''  # 源平台类型（兼容旧数据，新规则应使用source_platform_id）
    source_chat_ids: List[str] = field(default_factory=list)
    
    # 目标配置
    target_platform_ids: List[int] = field(default_factory=list)  # 目标平台实例ID列表（优先使用，支持选择具体账户）
    target_platforms: List[str] = field(default_factory=list)  # 目标平台类型列表（兼容旧数据，新规则应使用target_platform_ids）
    target_chat_ids: Dict[str, List[str]] = field(default_factory=dict)  # 改为字符串键
    
    # 过滤条件
    keywords: List[str] = field(default_factory=list)  # 关键词过滤
    exclude_keywords: List[str] = field(default_factory=list)  # 排除关键词
    message_types: List[MessageType] = field(default_factory=list)  # 消息类型过滤
    
    # 转换配置
    add_prefix: Optional[str] = None
    add_suffix: Optional[str] = None
    enable_markdown: bool = False
    
    def matches(self, message: Message) -> bool:
        """检查消息是否匹配规则"""
        from utils.logger import get_logger
        match_logger = get_logger(__name__)
        
        # 优先检查平台ID（如果规则指定了具体平台账户）
        if self.source_platform_id is not None:
            message_platform_id = getattr(message, 'source_platform_id', None)
            if message_platform_id is not None and message_platform_id != self.source_platform_id:
                # 如果消息有 platform_id 但与规则不匹配，则不匹配
                match_logger.info(f"❌ 平台ID不匹配: 规则要求 {self.source_platform_id}, 消息是 {message_platform_id}")
                return False
            elif message_platform_id is None:
                # 如果消息没有 platform_id，但规则有，回退到检查平台类型
                # 这样可以支持通过平台类型匹配（即使规则指定了 platform_id）
                if not self.source_platform:
                    # 如果规则既没有 platform_id 也没有 platform 类型，则不匹配
                    match_logger.info(f"❌ 规则只指定了平台ID {self.source_platform_id}，但消息没有平台ID，且规则没有指定平台类型")
                    return False
                # 继续检查平台类型
                match_logger.info(f"ℹ️ 消息没有平台ID，回退到检查平台类型匹配")
        
        # 检查平台类型（如果规则指定了平台类型，或者消息没有 platform_id）
        if self.source_platform:
            # 获取消息的平台类型字符串
            if isinstance(message.source_platform, PlatformType):
                source_platform_str = message.source_platform.value
            else:
                source_platform_str = str(message.source_platform)
            
            # 规则中的 source_platform 可能是平台类型字符串（如 "tradingview"）或平台名称
            # 先尝试直接匹配
            if source_platform_str.lower() != self.source_platform.lower():
                # 如果不匹配，尝试通过平台类型枚举匹配
                try:
                    rule_platform_type = PlatformType(self.source_platform.lower())
                    if message.source_platform != rule_platform_type:
                        match_logger.info(f"❌ 平台类型不匹配: 规则要求 '{self.source_platform}' (转换为 {rule_platform_type.value}), 消息是 '{source_platform_str}'")
                        return False
                    else:
                        match_logger.info(f"✅ 平台类型匹配: {source_platform_str} == {rule_platform_type.value}")
                except (ValueError, AttributeError):
                    # 如果无法转换为 PlatformType，则不匹配
                    match_logger.info(f"❌ 无法将规则平台类型 '{self.source_platform}' 转换为 PlatformType 枚举")
                    return False
            else:
                match_logger.info(f"✅ 平台类型匹配: {source_platform_str} == {self.source_platform}")
        
        # 检查聊天ID（如果规则指定了 source_chat_ids，则必须匹配）
        if self.source_chat_ids:
            if message.source_chat_id not in self.source_chat_ids:
                # 详细日志：为什么聊天ID不匹配
                from utils.logger import get_logger
                logger = get_logger(__name__)
                logger.info(f"❌ 聊天ID不匹配: 规则要求 {self.source_chat_ids}, 消息是 {message.source_chat_id}")
                return False
        
        # 检查消息类型
        if self.message_types and message.message_type not in self.message_types:
            return False
        
        # 检查关键词
        if self.keywords:
            if not any(keyword in message.content for keyword in self.keywords):
                return False
        
        # 检查排除关键词
        if self.exclude_keywords:
            if any(keyword in message.content for keyword in self.exclude_keywords):
                return False
        
        return True
    
    def transform_message(self, message: Message) -> Message:
        """转换消息内容"""
        transformed = Message(
            content=message.content,
            message_type=message.message_type,
            timestamp=message.timestamp,
            source_platform=message.source_platform,
            source_chat_id=message.source_chat_id,
            source_user_id=message.source_user_id,
            source_username=message.source_username,
            message_id=message.message_id,
            reply_to_message_id=message.reply_to_message_id,
            attachments=message.attachments.copy(),
            formatted_content=message.formatted_content,
            extra_data=message.extra_data.copy()
        )
        
        # 添加前缀
        if self.add_prefix:
            transformed.content = f"{self.add_prefix}{transformed.content}"
        
        # 添加后缀
        if self.add_suffix:
            transformed.content = f"{transformed.content}{self.add_suffix}"
        
        # Markdown 转换
        if self.enable_markdown and not transformed.formatted_content:
            transformed.formatted_content = transformed.content
        
        return transformed
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            'rule_id': self.rule_id,
            'rule_name': self.rule_name,
            'enabled': self.enabled,
            'source_platform': self.source_platform,
            'source_chat_ids': self.source_chat_ids,
            'target_platforms': self.target_platforms,
            'target_chat_ids': self.target_chat_ids,
            'keywords': self.keywords,
            'exclude_keywords': self.exclude_keywords,
            'add_prefix': self.add_prefix,
            'add_suffix': self.add_suffix,
            'enable_markdown': self.enable_markdown
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ForwardRule':
        """从字典创建"""
        return cls(
            rule_id=data['rule_id'],
            rule_name=data['rule_name'],
            enabled=data.get('enabled', True),
            source_platform=data.get('source_platform', ''),
            source_chat_ids=data.get('source_chat_ids', []),
            target_platforms=data.get('target_platforms', []),
            target_chat_ids=data.get('target_chat_ids', {}),
            keywords=data.get('keywords', []),
            exclude_keywords=data.get('exclude_keywords', []),
            add_prefix=data.get('add_prefix'),
            add_suffix=data.get('add_suffix'),
            enable_markdown=data.get('enable_markdown', False)
        )

