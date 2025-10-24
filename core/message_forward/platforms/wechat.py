"""
微信消息平台实现
使用 itchat 库（需要扫码登录）
"""

from typing import Callable, Dict, List, Optional, Any
import asyncio
import threading

from ..base import MessagePlatform
from ..models import Message, MessageType, PlatformType
from utils.logger import get_logger

logger = get_logger(__name__)

class WeChatPlatform(MessagePlatform):
    """微信消息平台"""
    
    def __init__(self, config: Dict[str, Any]):
        super().__init__(PlatformType.WECHAT, config)
        
        self.hot_reload = config.get('hot_reload', True)  # 热登录
        self.qr_callback = config.get('qr_callback')  # 二维码回调
        
        self.itchat = None
        self.login_thread = None
        self.is_logged_in = False
        
        # 检查是否安装了 itchat
        try:
            import itchat
            self.itchat = itchat
        except ImportError:
            logger.error("未安装 itchat 库，请运行: pip install itchat")
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
            # 注册消息处理器
            @self.itchat.msg_register(self.itchat.content.TEXT)
            def text_handler(msg):
                self._handle_wechat_message(msg, MessageType.TEXT)
            
            @self.itchat.msg_register(self.itchat.content.PICTURE)
            def picture_handler(msg):
                self._handle_wechat_message(msg, MessageType.IMAGE)
            
            @self.itchat.msg_register(self.itchat.content.ATTACHMENT)
            def file_handler(msg):
                self._handle_wechat_message(msg, MessageType.FILE)
            
            # 登录
            self.itchat.auto_login(
                hotReload=self.hot_reload,
                qrCallback=self.qr_callback
            )
            
            self.is_logged_in = True
            logger.info("微信登录成功，开始监听消息...")
            
            # 开始运行（阻塞）
            self.itchat.run()
            
        except Exception as e:
            logger.error(f"微信登录失败: {e}")
            self.is_logged_in = False
    
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

