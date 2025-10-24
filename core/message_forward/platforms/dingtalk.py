"""
钉钉消息平台实现
支持钉钉群机器人和钉钉 Stream 模式
"""

from typing import Callable, Dict, List, Optional, Any
import asyncio
import aiohttp
import hmac
import hashlib
import base64
import time
import urllib.parse

from ..base import MessagePlatform
from ..models import Message, MessageType, PlatformType
from utils.logger import get_logger

logger = get_logger(__name__)

class DingTalkPlatform(MessagePlatform):
    """钉钉消息平台"""
    
    def __init__(self, config: Dict[str, Any]):
        super().__init__(PlatformType.DINGTALK, config)
        
        # 群机器人配置
        self.webhook_url = config.get('webhook_url')
        self.secret = config.get('secret')  # 加签密钥
        
        # Stream 模式配置（用于接收消息）
        self.client_id = config.get('client_id')
        self.client_secret = config.get('client_secret')
        
        # 运行时状态
        self.session = None
        self.stream_task = None
        
        if not self.webhook_url:
            logger.warning("钉钉 webhook_url 未配置")
            self.enabled = False
    
    async def connect(self) -> bool:
        """连接到钉钉"""
        if not self.enabled:
            logger.warning("钉钉平台未启用")
            return False
        
        try:
            logger.info("正在连接钉钉...")
            
            # 创建 HTTP 会话
            self.session = aiohttp.ClientSession()
            
            # 测试 Webhook
            test_result = await self._test_webhook()
            if not test_result:
                logger.warning("钉钉 Webhook 测试失败")
            
            self.connected = True
            logger.info("✅ 钉钉连接成功")
            
            # 如果配置了 Stream 模式，启动消息监听
            if self.client_id and self.client_secret:
                asyncio.create_task(self._start_stream_listener())
            
            return True
            
        except Exception as e:
            logger.error(f"钉钉连接失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
            self.connected = False
            return False
    
    async def disconnect(self) -> bool:
        """断开钉钉连接"""
        try:
            if self.stream_task:
                self.stream_task.cancel()
            
            if self.session:
                await self.session.close()
            
            logger.info("钉钉连接已断开")
            self.connected = False
            return True
        except Exception as e:
            logger.error(f"钉钉断开连接失败: {e}")
            return False
    
    def _generate_sign(self) -> tuple:
        """生成钉钉签名"""
        if not self.secret:
            return None, None
        
        timestamp = str(round(time.time() * 1000))
        secret_enc = self.secret.encode('utf-8')
        string_to_sign = f'{timestamp}\n{self.secret}'
        string_to_sign_enc = string_to_sign.encode('utf-8')
        hmac_code = hmac.new(secret_enc, string_to_sign_enc, digestmod=hashlib.sha256).digest()
        sign = urllib.parse.quote_plus(base64.b64encode(hmac_code))
        return timestamp, sign
    
    async def send_message(self, chat_id: str, message: Message) -> bool:
        """发送消息到钉钉"""
        if not self.connected or not self.session:
            logger.error("钉钉未连接")
            return False
        
        try:
            # 构造请求 URL（添加签名）
            url = self.webhook_url
            if self.secret:
                timestamp, sign = self._generate_sign()
                url = f"{self.webhook_url}&timestamp={timestamp}&sign={sign}"
            
            # 构造消息体
            if message.message_type == MessageType.MARKDOWN:
                payload = {
                    "msgtype": "markdown",
                    "markdown": {
                        "title": "消息转发",
                        "text": message.formatted_content or message.content
                    }
                }
            elif message.message_type == MessageType.LINK:
                payload = {
                    "msgtype": "link",
                    "link": {
                        "title": "消息转发",
                        "text": message.content,
                        "messageUrl": message.extra_data.get('url', ''),
                        "picUrl": message.extra_data.get('pic_url', '')
                    }
                }
            else:
                # 普通文本消息
                payload = {
                    "msgtype": "text",
                    "text": {
                        "content": message.content
                    }
                }
            
            # 发送消息
            async with self.session.post(url, json=payload) as response:
                result = await response.json()
                
                if result.get('errcode') == 0:
                    logger.debug(f"✅ 消息已发送到钉钉")
                    return True
                else:
                    logger.error(f"钉钉发送消息失败: {result}")
                    return False
                    
        except Exception as e:
            logger.error(f"钉钉发送消息失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return False
    
    async def listen(self, callback: Callable[[Message], None]) -> None:
        """监听钉钉消息"""
        self.add_message_handler(callback)
        logger.info("钉钉消息监听已启动")
    
    async def _test_webhook(self) -> bool:
        """测试 Webhook 连接"""
        try:
            # 发送测试消息
            test_message = Message(
                content="[测试] 钉钉消息转发系统连接测试",
                message_type=MessageType.TEXT
            )
            return await self.send_message("", test_message)
        except Exception as e:
            logger.error(f"钉钉 Webhook 测试失败: {e}")
            return False
    
    async def _start_stream_listener(self):
        """
        启动 Stream 模式消息监听
        注意：这需要钉钉企业内部应用的权限
        """
        try:
            logger.info("启动钉钉 Stream 模式监听...")
            # TODO: 实现钉钉 Stream 模式
            # 这需要使用钉钉开放平台的 Stream SDK
            # https://open.dingtalk.com/document/isvapp/stream-overview
            
            logger.warning("钉钉 Stream 模式暂未实现，仅支持发送消息")
            
        except Exception as e:
            logger.error(f"钉钉 Stream 监听失败: {e}")
    
    async def get_chat_info(self, chat_id: str) -> Optional[Dict[str, Any]]:
        """获取钉钉聊天信息"""
        # 钉钉群机器人模式无法获取群信息
        # 如果需要，可以通过 OpenAPI 实现
        return {
            'id': chat_id,
            'platform': 'dingtalk',
            'type': 'group'
        }

