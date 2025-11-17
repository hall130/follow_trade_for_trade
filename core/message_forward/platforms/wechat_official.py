"""
微信公众号消息平台实现
基于微信公众平台API，支持客服消息和模板消息推送
"""

from typing import Callable, Dict, List, Optional, Any
import asyncio
import aiohttp
import time
import json

from ..base import MessagePlatform
from ..models import Message, MessageType, PlatformType
from utils.logger import get_logger

logger = get_logger(__name__)


class WeChatOfficialPlatform(MessagePlatform):
    """微信公众号消息平台"""
    
    def __init__(self, config: Dict[str, Any]):
        super().__init__(PlatformType.WECHAT_OFFICIAL, config)
        
        # 微信公众号配置
        self.app_id = config.get('app_id')
        self.app_secret = config.get('app_secret')
        self.token = config.get('token')  # 用于验证的token（可选）
        
        # API配置
        self.api_base_url = 'https://api.weixin.qq.com'
        self.access_token = None
        self.access_token_expires_at = 0
        
        # 运行时状态
        self.session = None
        
        if not self.app_id or not self.app_secret:
            logger.warning("微信公众号 app_id 或 app_secret 未配置")
            self.enabled = False
    
    async def connect(self) -> bool:
        """连接到微信公众号"""
        if not self.enabled:
            logger.warning("微信公众号平台未启用")
            return False
        
        try:
            logger.info("正在连接微信公众号...")
            
            # 创建 HTTP 会话
            self.session = aiohttp.ClientSession()
            
            # 获取 Access Token
            token_result = await self._get_access_token()
            if not token_result:
                logger.error("获取微信公众号 Access Token 失败")
                self.connected = False
                return False
            
            self.connected = True
            logger.info("✅ 微信公众号连接成功")
            return True
            
        except Exception as e:
            logger.error(f"微信公众号连接失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
            self.connected = False
            return False
    
    async def disconnect(self) -> bool:
        """断开微信公众号连接"""
        try:
            if self.session:
                await self.session.close()
            
            logger.info("微信公众号连接已断开")
            self.connected = False
            return True
        except Exception as e:
            logger.error(f"微信公众号断开连接失败: {e}")
            return False
    
    async def _get_access_token(self) -> bool:
        """获取 Access Token"""
        try:
            url = f"{self.api_base_url}/cgi-bin/token"
            params = {
                'grant_type': 'client_credential',
                'appid': self.app_id,
                'secret': self.app_secret
            }
            
            async with self.session.get(url, params=params) as response:
                if response.status != 200:
                    logger.error(f"获取 Access Token 失败，HTTP状态码: {response.status}")
                    return False
                
                result = await response.json()
                
                if 'access_token' in result:
                    self.access_token = result['access_token']
                    # Access Token 有效期通常是 7200 秒，提前 5 分钟刷新
                    expires_in = result.get('expires_in', 7200)
                    self.access_token_expires_at = time.time() + expires_in - 300
                    logger.info("✅ 获取 Access Token 成功")
                    return True
                else:
                    error_code = result.get('errcode', 'unknown')
                    error_msg = result.get('errmsg', 'unknown error')
                    logger.error(f"获取 Access Token 失败: [{error_code}] {error_msg}")
                    return False
                    
        except Exception as e:
            logger.error(f"获取 Access Token 异常: {e}")
            return False
    
    async def _ensure_access_token(self) -> bool:
        """确保 Access Token 有效"""
        # 如果 token 不存在或即将过期，重新获取
        if not self.access_token or time.time() >= self.access_token_expires_at:
            return await self._get_access_token()
        return True
    
    async def send_message(self, chat_id: str, message: Message) -> bool:
        """发送消息到微信公众号
        
        Args:
            chat_id: 用户的 openid（微信公众号用户的唯一标识）
            message: 消息对象
        
        注意：此方法会检查用户是否订阅了该类型的消息
        """
        if not self.connected or not self.session:
            logger.error("微信公众号未连接")
            return False
        
        try:
            # 检查用户订阅状态（如果消息包含订阅类型信息）
            subscription_type = getattr(message, 'subscription_type', None) or message.extra_data.get('subscription_type') if hasattr(message, 'extra_data') else None
            
            if subscription_type:
                # 检查用户是否订阅了该类型
                try:
                    from core.message_forward.wechat_official_user_manager import get_wechat_official_user_manager
                    user_manager = get_wechat_official_user_manager()
                    user = user_manager.get_user(chat_id)
                    
                    if not user or not user.get('subscribe') or user.get('status') != 'active':
                        logger.debug(f"用户未关注或已取消关注: openid={chat_id}")
                        return False
                    
                    # 检查订阅
                    subscriptions = user_manager.get_user_subscriptions(chat_id)
                    subscribed_types = [s['subscription_type'] for s in subscriptions if s.get('enabled')]
                    
                    if subscription_type not in subscribed_types:
                        logger.debug(f"用户未订阅该类型消息: openid={chat_id}, type={subscription_type}")
                        return False
                except Exception as e:
                    logger.warning(f"检查用户订阅状态失败: {e}，继续发送消息")
            
            # 确保 Access Token 有效
            if not await self._ensure_access_token():
                logger.error("无法获取有效的 Access Token")
                return False
            
            # 根据消息类型选择发送方式
            if message.message_type == MessageType.IMAGE and message.attachments:
                # 发送图片消息
                return await self._send_image_message(chat_id, message.attachments[0])
            elif message.message_type == MessageType.LINK:
                # 发送图文消息
                return await self._send_news_message(chat_id, message)
            else:
                # 发送文本消息（客服消息）
                return await self._send_customer_service_message(chat_id, message.content)
                    
        except Exception as e:
            logger.error(f"微信公众号发送消息失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return False
    
    async def _send_customer_service_message(self, openid: str, content: str) -> bool:
        """发送客服消息（文本）"""
        try:
            url = f"{self.api_base_url}/cgi-bin/message/custom/send"
            params = {'access_token': self.access_token}
            
            payload = {
                'touser': openid,
                'msgtype': 'text',
                'text': {
                    'content': content
                }
            }
            
            async with self.session.post(url, params=params, json=payload) as response:
                if response.status != 200:
                    logger.error(f"发送客服消息失败，HTTP状态码: {response.status}")
                    return False
                
                result = await response.json()
                
                if result.get('errcode') == 0:
                    logger.debug(f"✅ 客服消息已发送到用户: {openid}")
                    return True
                else:
                    error_code = result.get('errcode', 'unknown')
                    error_msg = result.get('errmsg', 'unknown error')
                    
                    # 处理常见错误
                    if error_code == 45015:  # 回复时间超过限制
                        logger.warning(f"用户 {openid} 超过48小时未交互，无法发送客服消息")
                    elif error_code == 40001:  # Access Token 无效
                        logger.warning("Access Token 无效，尝试重新获取")
                        await self._get_access_token()
                    else:
                        logger.error(f"发送客服消息失败: [{error_code}] {error_msg}")
                    
                    return False
                    
        except Exception as e:
            logger.error(f"发送客服消息异常: {e}")
            return False
    
    async def _send_image_message(self, openid: str, media_id: str) -> bool:
        """发送图片消息（客服消息）"""
        try:
            url = f"{self.api_base_url}/cgi-bin/message/custom/send"
            params = {'access_token': self.access_token}
            
            payload = {
                'touser': openid,
                'msgtype': 'image',
                'image': {
                    'media_id': media_id
                }
            }
            
            async with self.session.post(url, params=params, json=payload) as response:
                if response.status != 200:
                    logger.error(f"发送图片消息失败，HTTP状态码: {response.status}")
                    return False
                
                result = await response.json()
                
                if result.get('errcode') == 0:
                    logger.debug(f"✅ 图片消息已发送到用户: {openid}")
                    return True
                else:
                    error_code = result.get('errcode', 'unknown')
                    error_msg = result.get('errmsg', 'unknown error')
                    logger.error(f"发送图片消息失败: [{error_code}] {error_msg}")
                    return False
                    
        except Exception as e:
            logger.error(f"发送图片消息异常: {e}")
            return False
    
    async def _send_news_message(self, openid: str, message: Message) -> bool:
        """发送图文消息（客服消息）"""
        try:
            url = f"{self.api_base_url}/cgi-bin/message/custom/send"
            params = {'access_token': self.access_token}
            
            url_link = message.extra_data.get('url', '')
            pic_url = message.extra_data.get('pic_url', '')
            title = message.extra_data.get('title', '消息通知')
            description = message.content
            
            payload = {
                'touser': openid,
                'msgtype': 'news',
                'news': {
                    'articles': [
                        {
                            'title': title,
                            'description': description,
                            'url': url_link,
                            'picurl': pic_url
                        }
                    ]
                }
            }
            
            async with self.session.post(url, params=params, json=payload) as response:
                if response.status != 200:
                    logger.error(f"发送图文消息失败，HTTP状态码: {response.status}")
                    return False
                
                result = await response.json()
                
                if result.get('errcode') == 0:
                    logger.debug(f"✅ 图文消息已发送到用户: {openid}")
                    return True
                else:
                    error_code = result.get('errcode', 'unknown')
                    error_msg = result.get('errmsg', 'unknown error')
                    logger.error(f"发送图文消息失败: [{error_code}] {error_msg}")
                    return False
                    
        except Exception as e:
            logger.error(f"发送图文消息异常: {e}")
            return False
    
    async def send_template_message(self, openid: str, template_id: str, 
                                   data: Dict[str, Any], url: Optional[str] = None,
                                   miniprogram: Optional[Dict[str, Any]] = None) -> bool:
        """发送模板消息
        
        Args:
            openid: 用户的 openid
            template_id: 模板ID
            data: 模板数据（格式：{"first": {"value": "..."}, "keyword1": {"value": "..."}, ...}）
            url: 跳转链接（可选）
            miniprogram: 小程序跳转配置（可选）
        """
        if not self.connected or not self.session:
            logger.error("微信公众号未连接")
            return False
        
        try:
            # 确保 Access Token 有效
            if not await self._ensure_access_token():
                logger.error("无法获取有效的 Access Token")
                return False
            
            api_url = f"{self.api_base_url}/cgi-bin/message/template/send"
            params = {'access_token': self.access_token}
            
            payload = {
                'touser': openid,
                'template_id': template_id,
                'data': data
            }
            
            if url:
                payload['url'] = url
            
            if miniprogram:
                payload['miniprogram'] = miniprogram
            
            async with self.session.post(api_url, params=params, json=payload) as response:
                if response.status != 200:
                    logger.error(f"发送模板消息失败，HTTP状态码: {response.status}")
                    return False
                
                result = await response.json()
                
                if result.get('errcode') == 0:
                    logger.debug(f"✅ 模板消息已发送到用户: {openid}")
                    return True
                else:
                    error_code = result.get('errcode', 'unknown')
                    error_msg = result.get('errmsg', 'unknown error')
                    logger.error(f"发送模板消息失败: [{error_code}] {error_msg}")
                    return False
                    
        except Exception as e:
            logger.error(f"发送模板消息异常: {e}")
            return False
    
    async def listen(self, callback: Callable[[Message], None]) -> None:
        """监听微信公众号消息（需要配置服务器）"""
        self.add_message_handler(callback)
        logger.info("微信公众号消息监听已启动（需要配置服务器接收消息）")
    
    async def get_chat_info(self, chat_id: str) -> Optional[Dict[str, Any]]:
        """获取用户信息（通过 openid）"""
        if not self.connected or not self.session:
            return None
        
        try:
            # 确保 Access Token 有效
            if not await self._ensure_access_token():
                return None
            
            url = f"{self.api_base_url}/cgi-bin/user/info"
            params = {
                'access_token': self.access_token,
                'openid': chat_id,
                'lang': 'zh_CN'
            }
            
            async with self.session.get(url, params=params) as response:
                if response.status != 200:
                    return None
                
                result = await response.json()
                
                if 'openid' in result:
                    return {
                        'id': result['openid'],
                        'nickname': result.get('nickname', ''),
                        'headimgurl': result.get('headimgurl', ''),
                        'platform': 'wechat_official'
                    }
                
                return None
                
        except Exception as e:
            logger.error(f"获取用户信息失败: {e}")
            return None

