"""
Telegram 消息平台实现
使用 python-telegram-bot 库
"""

from typing import Callable, Dict, List, Optional, Any
import asyncio

from ..base import MessagePlatform
from ..models import Message, MessageType, PlatformType
from utils.logger import get_logger

logger = get_logger(__name__)

class TelegramPlatform(MessagePlatform):
    """Telegram 消息平台"""
    
    def __init__(self, config: Dict[str, Any]):
        super().__init__(PlatformType.TELEGRAM, config)
        
        self.bot_token = config.get('bot_token')
        self.bot = None
        self.application = None
        self.polling_task = None
        
        if not self.bot_token:
            logger.warning("Telegram bot_token 未配置")
            self.enabled = False
    
    async def connect(self) -> bool:
        """连接到 Telegram"""
        if not self.enabled:
            logger.warning("Telegram 平台未启用")
            return False
        
        try:
            # 动态导入 telegram 库
            try:
                from telegram import Bot
                from telegram.ext import Application, MessageHandler, filters
            except ImportError:
                logger.error("未安装 python-telegram-bot 库，请运行: pip install python-telegram-bot")
                self.enabled = False
                return False
            
            logger.info("正在连接 Telegram...")
            
            # 创建 Application
            self.application = Application.builder().token(self.bot_token).build()
            self.bot = self.application.bot
            
            # 测试连接
            bot_info = await self.bot.get_me()
            logger.info(f"✅ Telegram 连接成功: @{bot_info.username}")
            
            # 添加消息处理器
            message_handler = MessageHandler(
                filters.TEXT & ~filters.COMMAND,
                self._on_message
            )
            self.application.add_handler(message_handler)
            
            # 启动轮询（在后台）
            asyncio.create_task(self._start_polling())
            
            self.connected = True
            return True
            
        except Exception as e:
            logger.error(f"Telegram 连接失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
            self.connected = False
            return False
    
    async def _start_polling(self):
        """启动消息轮询"""
        try:
            logger.info("Telegram 开始轮询消息...")
            await self.application.initialize()
            await self.application.start()
            await self.application.updater.start_polling()
        except Exception as e:
            logger.error(f"Telegram 轮询失败: {e}")
    
    async def disconnect(self) -> bool:
        """断开 Telegram 连接"""
        try:
            if self.application:
                await self.application.updater.stop()
                await self.application.stop()
                await self.application.shutdown()
                logger.info("Telegram 连接已断开")
            
            self.connected = False
            return True
        except Exception as e:
            logger.error(f"Telegram 断开连接失败: {e}")
            return False
    
    async def send_message(self, chat_id: str, message: Message) -> bool:
        """发送消息到 Telegram"""
        if not self.connected or not self.bot:
            logger.error("Telegram 未连接")
            return False
        
        try:
            # 根据消息类型发送
            if message.message_type == MessageType.MARKDOWN:
                await self.bot.send_message(
                    chat_id=chat_id,
                    text=message.formatted_content or message.content,
                    parse_mode='Markdown'
                )
            elif message.message_type == MessageType.IMAGE:
                if message.attachments:
                    await self.bot.send_photo(
                        chat_id=chat_id,
                        photo=message.attachments[0],
                        caption=message.content
                    )
                else:
                    logger.warning("图片消息但没有附件")
                    return False
            else:
                # 普通文本消息
                await self.bot.send_message(
                    chat_id=chat_id,
                    text=message.content
                )
            
            logger.debug(f"✅ 消息已发送到 Telegram chat: {chat_id}")
            return True
            
        except Exception as e:
            logger.error(f"Telegram 发送消息失败: {e}")
            return False
    
    async def listen(self, callback: Callable[[Message], None]) -> None:
        """监听 Telegram 消息"""
        self.add_message_handler(callback)
        logger.info("Telegram 消息监听已启动")
    
    async def _on_message(self, update, context):
        """处理接收到的 Telegram 消息"""
        try:
            tg_message = update.message
            
            # 构造统一消息对象
            message = Message(
                content=tg_message.text or "",
                message_type=MessageType.TEXT,
                source_platform=PlatformType.TELEGRAM,
                source_chat_id=str(tg_message.chat_id),
                source_user_id=str(tg_message.from_user.id),
                source_username=tg_message.from_user.username,
                message_id=str(tg_message.message_id),
                extra_data={
                    'chat_type': tg_message.chat.type,
                    'chat_title': tg_message.chat.title if tg_message.chat.title else None
                }
            )
            
            # 处理图片
            if tg_message.photo:
                message.message_type = MessageType.IMAGE
                # 获取最大尺寸的图片
                photo = tg_message.photo[-1]
                file = await context.bot.get_file(photo.file_id)
                message.attachments = [file.file_path]
                message.content = tg_message.caption or ""
            
            # 处理文件
            elif tg_message.document:
                message.message_type = MessageType.FILE
                file = await context.bot.get_file(tg_message.document.file_id)
                message.attachments = [file.file_path]
                message.content = tg_message.caption or tg_message.document.file_name or ""
            
            # 调用消息处理器
            await self._handle_message(message)
            
        except Exception as e:
            logger.error(f"处理 Telegram 消息失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
    
    async def get_chat_info(self, chat_id: str) -> Optional[Dict[str, Any]]:
        """获取 Telegram 聊天信息"""
        if not self.connected or not self.bot:
            return None
        
        try:
            chat = await self.bot.get_chat(chat_id)
            return {
                'id': str(chat.id),
                'title': chat.title,
                'type': chat.type,
                'username': chat.username,
                'description': chat.description
            }
        except Exception as e:
            logger.error(f"获取 Telegram 聊天信息失败: {e}")
            return None

