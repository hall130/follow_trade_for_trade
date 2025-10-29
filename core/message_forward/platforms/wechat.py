"""
微信消息平台实现
使用 itchat-uos 库（解决登录问题）
"""

from typing import Callable, Dict, List, Optional, Any
import asyncio
import threading
import time
import json
import os

from ..base import MessagePlatform
from ..models import Message, MessageType, PlatformType
from utils.logger import get_logger

logger = get_logger(__name__)

class WeChatPlatform(MessagePlatform):
    """微信消息平台（基于itchat-uos）"""
    
    def __init__(self, config: Dict[str, Any]):
        super().__init__(PlatformType.WECHAT, config)
        
        self.hot_reload = config.get('hot_reload', True)  # 热登录
        self.qr_callback = config.get('qr_callback')  # 二维码回调
        self.config_file = config.get('config_file', 'wechat_listener_config.json')
        
        self.itchat = None
        self.login_thread = None
        self.is_logged_in = False
        self.chatrooms = []  # 缓存的群聊信息
        self.friends = []    # 缓存的好友信息
        
        # 检查是否安装了 itchat-uos
        try:
            import itchat_uos as itchat
            self.itchat = itchat
            logger.info("✅ 使用 itchat-uos 库")
        except ImportError:
            try:
                import itchat
                self.itchat = itchat
                logger.warning("⚠️  使用原版 itchat 库，建议安装 itchat-uos")
            except ImportError:
                logger.error("❌ 未安装 itchat 或 itchat-uos 库")
                logger.error("请运行: pip install itchat-uos==1.5.0.dev0")
                self.enabled = False
    
    async def connect(self) -> bool:
        """连接到微信"""
        if not self.enabled or not self.itchat:
            logger.warning("微信平台未启用或未安装 itchat")
            return False
        
        try:
            logger.info("正在连接微信...")
            logger.info("请使用微信扫描二维码登录")
            
            # 在后台线程中登录（因为 itchat 是同步的）
            self.login_thread = threading.Thread(target=self._login_sync, daemon=True)
            self.login_thread.start()
            
            # 等待登录完成
            for i in range(60):  # 最多等待60秒
                await asyncio.sleep(1)
                if self.is_logged_in:
                    break
            
            if self.is_logged_in:
                self.connected = True
                logger.info("✅ 微信连接成功")
                return True
            else:
                logger.warning("微信登录超时")
                return False
                
        except Exception as e:
            logger.error(f"微信连接失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
            self.connected = False
            return False
    
    def _login_sync(self):
        """同步登录（在后台线程中运行）"""
        try:
            # 注册消息处理器（兼容itchat-uos和原版itchat）
            if hasattr(self.itchat, 'content'):
                # 原版itchat
                @self.itchat.msg_register(self.itchat.content.TEXT)
                def text_handler(msg):
                    self._handle_wechat_message(msg, MessageType.TEXT)
                
                @self.itchat.msg_register(self.itchat.content.PICTURE)
                def picture_handler(msg):
                    self._handle_wechat_message(msg, MessageType.IMAGE)
                
                @self.itchat.msg_register(self.itchat.content.ATTACHMENT)
                def file_handler(msg):
                    self._handle_wechat_message(msg, MessageType.FILE)
            else:
                # itchat-uos使用字符串
                @self.itchat.msg_register('Text')
                def text_handler(msg):
                    self._handle_wechat_message(msg, MessageType.TEXT)
                
                @self.itchat.msg_register('Picture')
                def picture_handler(msg):
                    self._handle_wechat_message(msg, MessageType.IMAGE)
                
                @self.itchat.msg_register('Attachment')
                def file_handler(msg):
                    self._handle_wechat_message(msg, MessageType.FILE)
            
            # 登录
            self.itchat.auto_login(
                hotReload=self.hot_reload,
                enableCmdQR=2,  # 在终端显示二维码
                picDir='itchat_uos_pics',
                qrCallback=self.qr_callback
            )
            
            self.is_logged_in = True
            logger.info("微信登录成功，开始监听消息...")
            
            # 缓存群聊和好友信息
            self._cache_chat_info()
            
            # 开始运行（阻塞）
            self.itchat.run()
            
        except Exception as e:
            logger.error(f"微信登录失败: {e}")
            self.is_logged_in = False
    
    def _cache_chat_info(self):
        """缓存群聊和好友信息"""
        try:
            # 获取群聊信息
            self.chatrooms = self.itchat.get_chatrooms()
            logger.info(f"缓存了 {len(self.chatrooms)} 个群聊")
            
            # 获取好友信息
            self.friends = self.itchat.get_friends()
            logger.info(f"缓存了 {len(self.friends)} 个好友")
            
        except Exception as e:
            logger.error(f"缓存聊天信息失败: {e}")
    
    def get_chatrooms(self) -> List[Dict[str, Any]]:
        """获取群聊列表"""
        return self.chatrooms
    
    def get_friends(self) -> List[Dict[str, Any]]:
        """获取好友列表"""
        return self.friends
    
    def discover_groups(self) -> List[Dict[str, Any]]:
        """发现微信群（返回群聊信息）"""
        groups = []
        for chatroom in self.chatrooms:
            if chatroom.get('UserName', '').startswith('@@'):
                groups.append({
                    'name': chatroom.get('NickName', 'Unknown'),
                    'id': chatroom.get('UserName', ''),
                    'member_count': len(chatroom.get('MemberList', [])),
                    'type': 'group'
                })
        return groups
    
    def load_config(self) -> Optional[Dict[str, Any]]:
        """加载配置文件"""
        try:
            if os.path.exists(self.config_file):
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
        except Exception as e:
            logger.error(f"加载配置文件失败: {e}")
        return None
    
    def save_config(self, config: Dict[str, Any]) -> bool:
        """保存配置文件"""
        try:
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(config, f, ensure_ascii=False, indent=2)
            logger.info(f"配置已保存到: {self.config_file}")
            return True
        except Exception as e:
            logger.error(f"保存配置文件失败: {e}")
            return False
    
    def _handle_wechat_message(self, msg, message_type: MessageType):
        """处理微信消息"""
        try:
            # 构造统一消息对象
            message = Message(
                content=msg.get('Text', '') or msg.get('FileName', ''),
                message_type=message_type,
                source_platform=PlatformType.WECHAT,
                source_chat_id=msg.get('FromUserName', ''),
                source_user_id=msg.get('FromUserName', ''),
                source_username=msg.get('ActualNickName', '') or msg.get('NickName', ''),
                message_id=msg.get('MsgId', ''),
                extra_data={
                    'type': msg.get('Type', ''),
                    'msg_type': msg.get('MsgType', 0)
                }
            )
            
            # 处理附件
            if message_type in [MessageType.IMAGE, MessageType.FILE]:
                file_path = msg.get('FileName', '')
                if file_path:
                    message.attachments = [file_path]
            
            # 异步处理消息
            asyncio.create_task(self._handle_message(message))
            
        except Exception as e:
            logger.error(f"处理微信消息失败: {e}")
    
    async def disconnect(self) -> bool:
        """断开微信连接"""
        try:
            if self.itchat and self.is_logged_in:
                self.itchat.logout()
                logger.info("微信连接已断开")
            
            self.connected = False
            self.is_logged_in = False
            return True
        except Exception as e:
            logger.error(f"微信断开连接失败: {e}")
            return False
    
    async def send_message(self, chat_id: str, message: Message) -> bool:
        """发送消息到微信"""
        if not self.connected or not self.itchat or not self.is_logged_in:
            logger.error("微信未连接")
            return False
        
        try:
            # 在后台线程中发送（因为 itchat 是同步的）
            def send_sync():
                try:
                    if message.message_type == MessageType.IMAGE and message.attachments:
                        # 发送图片
                        self.itchat.send_image(message.attachments[0], toUserName=chat_id)
                    elif message.message_type == MessageType.FILE and message.attachments:
                        # 发送文件
                        self.itchat.send_file(message.attachments[0], toUserName=chat_id)
                    else:
                        # 发送文本消息
                        self.itchat.send(message.content, toUserName=chat_id)
                    
                    logger.debug(f"✅ 消息已发送到微信 chat: {chat_id}")
                    return True
                except Exception as e:
                    logger.error(f"微信发送消息失败: {e}")
                    return False
            
            # 在线程池中执行
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(None, send_sync)
            return result
            
        except Exception as e:
            logger.error(f"微信发送消息失败: {e}")
            return False
    
    async def listen(self, callback: Callable[[Message], None]) -> None:
        """监听微信消息"""
        self.add_message_handler(callback)
        logger.info("微信消息监听已启动")
    
    async def get_chat_info(self, chat_id: str) -> Optional[Dict[str, Any]]:
        """获取微信聊天信息"""
        if not self.connected or not self.itchat or not self.is_logged_in:
            return None
        
        try:
            def get_info_sync():
                try:
                    # 获取用户信息
                    user = self.itchat.search_friends(userName=chat_id)
                    if user:
                        return {
                            'id': user.get('UserName', ''),
                            'nickname': user.get('NickName', ''),
                            'remark': user.get('RemarkName', ''),
                            'type': 'friend'
                        }
                    
                    # 获取群聊信息
                    chatroom = self.itchat.search_chatrooms(userName=chat_id)
                    if chatroom:
                        return {
                            'id': chatroom.get('UserName', ''),
                            'nickname': chatroom.get('NickName', ''),
                            'type': 'group',
                            'member_count': len(chatroom.get('MemberList', []))
                        }
                    
                    return None
                except Exception as e:
                    logger.error(f"获取微信聊天信息失败: {e}")
                    return None
            
            # 在线程池中执行
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(None, get_info_sync)
            return result
            
        except Exception as e:
            logger.error(f"获取微信聊天信息失败: {e}")
            return None

