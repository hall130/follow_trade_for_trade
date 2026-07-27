#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Telegram Bot 平台实现
支持用户订阅 TradingView 交易信号
"""

from typing import Dict, List, Optional, Any, Callable
import asyncio
import logging
import uuid
from datetime import datetime

from ..base import MessagePlatform
from ..models import Message, MessageType, PlatformType
from utils.logger import get_logger
from core.message_forward.telegram_bot.message_formatter import format_tradingview_message_for_telegram

logger = get_logger(__name__)

try:
    from telegram import Bot, Update
    from telegram.constants import ParseMode
    from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters
    from telegram import InlineKeyboardMarkup, InlineKeyboardButton
    TELEGRAM_AVAILABLE = True
except ImportError:
    TELEGRAM_AVAILABLE = False
    logger.warning("python-telegram-bot 未安装，Telegram Bot 功能不可用")


class TelegramBotPlatform(MessagePlatform):
    """Telegram Bot 平台实现"""
    
    # 类级别的锁和状态跟踪（线程安全）
    _polling_lock = None  # 延迟初始化
    _polling_instances = {}  # {bot_token_key: instance}
    _polling_threads = {}  # {bot_token_key: thread}
    
    @classmethod
    def _get_polling_lock(cls):
        """获取轮询锁（延迟初始化，确保线程安全）"""
        if cls._polling_lock is None:
            import threading
            cls._polling_lock = threading.Lock()
        return cls._polling_lock
    
    def __init__(self, config: Dict[str, Any]):
        """
        初始化 Telegram Bot 平台
        
        Args:
            config: 配置字典
                - bot_token: Bot Token（必需）
                - webhook_url: Webhook URL（可选，用于生产环境）
                - webhook_secret: Webhook Secret（可选）
                - admin_user_ids: 管理员用户ID列表（可选）
        """
        if not TELEGRAM_AVAILABLE:
            raise ImportError("python-telegram-bot 未安装，请运行: pip install python-telegram-bot")
        
        super().__init__(PlatformType.TELEGRAM_BOT, config)
        
        self.bot_token = config.get('bot_token')
        self.webhook_url = config.get('webhook_url')
        self.webhook_secret = config.get('webhook_secret')
        self.admin_user_ids = config.get('admin_user_ids', [])
        
        # Bot 实例
        self.bot: Optional[Bot] = None
        self.application: Optional[Application] = None
        
        # 消息处理器
        self.message_handlers: List[Callable] = []
        
        # 订阅服务（延迟导入，避免循环依赖）
        self._subscription_service = None
        
        if not self.bot_token:
            logger.warning("Telegram Bot Token 未配置")
            self.enabled = False
        else:
            self.enabled = True
    
    def _truncate_message(self, message: str, max_length: int = 200) -> str:
        """
        截断消息以确保不超过 Telegram 的限制
        
        Args:
            message: 原始消息
            max_length: 最大长度（默认 200，Telegram callback query answer 的限制）
        
        Returns:
            截断后的消息
        """
        if len(message) <= max_length:
            return message
        return message[:max_length - 3] + "..."
    
    async def connect(self) -> bool:
        """连接到 Telegram Bot"""
        if not self.enabled:
            logger.warning("Telegram Bot 平台未启用")
            return False
        
        try:
            # 创建 Bot 实例
            self.bot = Bot(token=self.bot_token)
            
            # 创建 Application（用于处理更新）
            self.application = Application.builder().token(self.bot_token).build()
            
            # 设置处理器
            await self.setup_handlers()
            
            # 测试连接
            bot_info = await self.bot.get_me()
            logger.info(f"✅ Telegram Bot 连接成功: @{bot_info.username} ({bot_info.first_name})")
            
            # 如果配置了 webhook_url，使用 webhook 模式；否则使用轮询模式
            if self.webhook_url:
                try:
                    await self.setup_webhook()
                    logger.info(f"✅ Telegram Bot Webhook 已设置: {self.webhook_url}")
                except Exception as e:
                    logger.warning(f"⚠️ 设置 Webhook 失败，将使用轮询模式: {e}")
                    self.webhook_url = None  # 回退到轮询模式
            
            self.connected = True
            return True
            
        except Exception as e:
            logger.error(f"❌ Telegram Bot 连接失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
            self.connected = False
            return False
    
    async def setup_handlers(self):
        """设置消息和命令处理器"""
        if not self.application:
            logger.warning("⚠️ Application 未初始化，无法设置 handlers")
            return
        
        # 命令处理器
        self.application.add_handler(CommandHandler("start", self.handle_start))
        logger.debug("✅ 已注册 /start 命令处理器")
        
        self.application.add_handler(CommandHandler("help", self.handle_help))
        logger.debug("✅ 已注册 /help 命令处理器")
        
        self.application.add_handler(CommandHandler("status", self.handle_status))
        logger.debug("✅ 已注册 /status 命令处理器")
        
        # 文本消息处理器（处理固定按钮点击）
        self.application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_text_message))
        logger.debug("✅ 已注册文本消息处理器")
        
        # 回调查询处理器（处理 Inline 按钮点击）
        self.application.add_handler(CallbackQueryHandler(self.handle_callback_query))
        logger.debug("✅ 已注册回调查询处理器")
        
        handler_count = len(self.application.handlers) if self.application.handlers else 0
        logger.info(f"✅ Telegram Bot 处理器已设置，共 {handler_count} 个 handlers")
    
    async def disconnect(self) -> bool:
        """断开连接"""
        try:
            if self.application:
                await self.application.stop()
                await self.application.shutdown()
            if self.bot:
                await self.bot.close()
            
            self.connected = False
            logger.info("Telegram Bot 已断开连接")
            return True
        except Exception as e:
            logger.error(f"断开 Telegram Bot 连接失败: {e}")
            return False
    
    async def send_message(self, chat_id: str, message: Message) -> bool:
        """
        发送消息到 Telegram 用户
        
        Args:
            chat_id: 用户ID（Telegram user_id）
            message: 消息对象
        
        Returns:
            是否发送成功
        """
        if not self.connected or not self.bot:
            logger.error("Telegram Bot 未连接")
            return False
        
        try:
            # 如果是 TradingView 消息，使用专用格式化函数
            if message.source_platform == PlatformType.TRADINGVIEW:
                message_text = format_tradingview_message_for_telegram(message)
                parse_mode = ParseMode.MARKDOWN
            else:
                # 其他消息类型，使用原始内容
                message_text = message.content
                parse_mode = None
            
            # 发送消息
            await self.bot.send_message(
                chat_id=int(chat_id),
                text=message_text,
                parse_mode=parse_mode
            )
            
            logger.debug(f"✅ Telegram 消息已发送: 用户ID={chat_id}")
            return True
            
        except Exception as e:
            logger.error(f"❌ 发送 Telegram 消息失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return False
    
    # ==================== 命令处理器 ====================
    
    async def handle_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """处理 /start 命令（包含用户验证）"""
        try:
            user = update.effective_user
            logger.info(f"📨 收到 /start 命令 - 用户 {user.id} (@{user.username})")
            
            # 验证用户是否是平台用户
            user_service = self.get_user_service()
            if not user_service:
                await update.effective_message.reply_text(
                    "❌ 用户服务暂时不可用，请稍后再试。"
                )
                return
            
            platform_user = user_service.get_user_by_telegram_id(user.id)
            
            if not platform_user:
                # 用户未绑定，询问是否注册
                welcome_message = """👋 *欢迎使用交易信号订阅 Bot！*

⚠️ *账号验证*

检测到您尚未绑定平台账号。请选择：

1️⃣ *自动注册* - 系统将为您自动生成账号和密码
2️⃣ *绑定现有账号* - 如果您已有平台账号，请输入用户名和密码

💡 绑定账号后，您可以使用所有功能。"""
                
                from core.message_forward.telegram_bot.keyboard_builder import KeyboardBuilder
                reply_markup = KeyboardBuilder.build_registration_menu()
                
                await update.effective_message.reply_text(
                    welcome_message,
                    reply_markup=reply_markup,
                    parse_mode=ParseMode.MARKDOWN
                )
                return
            
            # 用户已绑定，显示欢迎信息
            welcome_message = f"""👋 *欢迎回来，{platform_user.get('username', '用户')}！*

📊 您可以订阅来自 TradingView 的交易信号，并自定义选择接收哪些时间周期和策略的信号。

✨ *主要功能*
• 📊 订阅管理 - 自定义订阅交易信号
• 👤 我的 - 管理账号和 API 配置
• 📈 查看状态 - 查看当前订阅信息

💡 使用下方按钮开始使用，或发送 /help 查看帮助信息。"""
            
            # 显示主菜单（固定按钮）
            from core.message_forward.telegram_bot.keyboard_builder import KeyboardBuilder
            reply_markup = KeyboardBuilder.build_main_menu()
            
            logger.info(f"📤 准备回复 /start 命令给用户 {user.id}")
            await update.effective_message.reply_text(
                welcome_message,
                reply_markup=reply_markup,
                parse_mode=ParseMode.MARKDOWN
            )
            logger.info(f"✅ 已成功回复 /start 命令给用户 {user.id}")
        except Exception as e:
            logger.error(f"❌ 处理 /start 命令失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
            # 尝试发送错误消息
            try:
                await update.effective_message.reply_text("❌ 抱歉，处理您的请求时出错了。请稍后再试。")
            except:
                pass
    
    async def handle_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """处理 /help 命令"""
        help_text = """📖 使用帮助

*命令列表*:
/start - 开始使用 Bot
/help - 显示帮助信息
/status - 查看订阅状态

*功能说明*:
1. 点击"📊 订阅管理"来管理您的订阅
2. 选择您想要接收的时间周期（3m, 5m, 15m, 30m, 1h, 2h, 4h, 1天）
3. 选择您想要接收的策略（如 ASR-VC, ASR-SC 等）
4. 保存配置后，您将收到匹配的交易信号

*注意事项*:
- 订阅需要有效的邀请码
- 订阅有有效期限制
- 可以随时修改订阅配置"""
        
        await update.effective_message.reply_text(
            help_text,
            parse_mode=ParseMode.MARKDOWN
        )
    
    async def handle_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """处理 /status 命令"""
        user = update.effective_user
        user_id = user.id
        
        # 获取用户订阅状态
        subscription_service = self.get_subscription_service()
        if not subscription_service:
            error_text = "❌ 订阅服务暂时不可用，请稍后再试。"
            if update.callback_query:
                await update.callback_query.answer(error_text, show_alert=True)
            else:
                await update.effective_message.reply_text(error_text)
            return
        
        # 查询用户订阅
        subscriptions = subscription_service.get_user_subscriptions(user_id)
        
        if not subscriptions:
            status_text = """📋 *订阅状态*

您当前没有活跃的订阅。

👉 点击「📊 订阅管理」来创建订阅。"""
        else:
            status_text = "📋 *我的订阅状态*\n\n"
            for idx, sub in enumerate(subscriptions, 1):
                status_text += f"*订阅 #{idx}*\n"
                status_text += f"━━━━━━━━━━━━━━\n"
                status_text += f"📋 *规则名称*: {sub.get('rule_name', '未知')}\n"
                
                # 状态显示
                status = sub.get('subscription_status', '未知')
                if status == 'active':
                    status_text += f"✅ *状态*: 活跃中\n"
                elif status == 'expired':
                    status_text += f"⏰ *状态*: 已过期\n"
                elif status == 'cancelled':
                    status_text += f"❌ *状态*: 已取消\n"
                else:
                    status_text += f"❓ *状态*: {status}\n"
                
                # 过期时间
                if sub.get('expire_date'):
                    try:
                        expire_date = sub['expire_date']
                        if isinstance(expire_date, str):
                            from datetime import datetime
                            expire_date = datetime.fromisoformat(expire_date.replace('Z', '+00:00'))
                        days_left = (expire_date - datetime.now()).days
                        if days_left > 0:
                            status_text += f"⏳ *剩余天数*: {days_left} 天\n"
                        else:
                            status_text += f"⚠️ *已过期*: {abs(days_left)} 天前\n"
                    except Exception:
                        pass
                
                # 周期和策略
                intervals = sub.get('intervals', [])
                strategies = sub.get('strategies', [])
                if intervals:
                    status_text += f"⏱️ *时间周期*: {', '.join(intervals)}\n"
                if strategies:
                    status_text += f"📈 *策略*: {', '.join(strategies)}\n"
                
                status_text += "\n"
        
        # 添加返回按钮（如果是查看订阅页面）
        from core.message_forward.telegram_bot.keyboard_builder import KeyboardBuilder
        from core.message_forward.telegram_bot.state_manager import StateManager
        
        state_manager = StateManager(self.get_db_pool())
        session = state_manager.get_session(user_id)
        current_state = session.get('current_state', '')
        
        # 如果是查看订阅状态，添加返回按钮
        if current_state == 'view_subscription':
            back_button = KeyboardBuilder.build_back_button("back_to_subscription_menu")
            # 创建带返回按钮的键盘
            from telegram import InlineKeyboardMarkup
            reply_markup = InlineKeyboardMarkup([back_button])
        else:
            reply_markup = None
        
        # 根据消息类型选择发送方式
        if update.callback_query:
            try:
                await update.callback_query.edit_message_text(
                    status_text,
                    parse_mode=ParseMode.MARKDOWN,
                    reply_markup=reply_markup
                )
                await update.callback_query.answer()
            except Exception as e:
                # 如果编辑失败（消息内容相同），发送新消息
                logger.debug(f"编辑消息失败，发送新消息: {e}")
                await update.callback_query.message.reply_text(
                    status_text,
                    parse_mode=ParseMode.MARKDOWN,
                    reply_markup=reply_markup
                )
                await update.callback_query.answer()
        else:
            await update.effective_message.reply_text(
                status_text,
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=reply_markup
            )
    
    # ==================== 消息处理器 ====================
    
    async def handle_text_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """处理文本消息（固定按钮点击和状态输入）"""
        user = update.effective_user
        text = update.effective_message.text
        
        logger.info(f"用户 {user.id} 发送文本消息: {text}")
        
        # 获取用户当前状态
        from core.message_forward.telegram_bot.state_manager import StateManager
        state_manager = StateManager(self.get_db_pool())
        session = state_manager.get_session(user.id)
        current_state = session.get('current_state', '')
        context_data = session.get('context_data', {})
        
        # 首先检查是否是主菜单按钮文本（优先级最高，即使有状态也要先处理按钮）
        # 这样可以避免在配置状态下误将按钮文本当作输入
        if text == "📊 订阅管理":
            # 清除当前状态，返回主菜单
            state_manager.update_session(user.id, current_state='main_menu', context_data={})
            # 验证用户是否已绑定
            if not await self._check_user_verified(update, context):
                return
            await self.handle_subscription_menu(update, context)
            return
        elif text == "👤 我的":
            # 清除当前状态，返回主菜单
            state_manager.update_session(user.id, current_state='main_menu', context_data={})
            await self.handle_my_account(update, context)
            return
        elif text == "💬 联系客服":
            # 清除当前状态，返回主菜单
            state_manager.update_session(user.id, current_state='main_menu', context_data={})
            await update.effective_message.reply_text(
                "💬 *联系客服*\n\n"
                "如有任何问题，请直接联系客服：\n"
                "[@Hongniugegege](https://t.me/Hongniugegege)\n\n"
                "点击上方用户名即可跳转到客服 Telegram。",
                parse_mode=ParseMode.MARKDOWN,
                disable_web_page_preview=True
            )
            return
        
        # 根据状态处理输入（只有在不是按钮文本时才处理状态输入）
        if current_state == 'bind_account_username':
            # 等待输入用户名
            context_data['username'] = text
            context_data['step'] = 'password'
            state_manager.update_session(user.id, current_state='bind_account_password', context_data=context_data)
            await update.effective_message.reply_text(
                "📝 请输入您的密码：",
                parse_mode=ParseMode.MARKDOWN
            )
            return
        elif current_state == 'bind_account_password':
            # 绑定账号
            username = context_data.get('username')
            password = text
            user_service = self.get_user_service()
            
            if not user_service:
                await update.effective_message.reply_text("❌ 用户服务不可用")
                return
            
            result = user_service.bind_existing_user(
                telegram_user_id=user.id,
                telegram_username=user.username,
                username=username,
                password=password
            )
            
            if result.get('success'):
                from core.message_forward.telegram_bot.keyboard_builder import KeyboardBuilder
                reply_markup = KeyboardBuilder.build_main_menu()
                state_manager.update_session(user.id, current_state='main_menu', context_data={})
                
                await update.effective_message.reply_text(
                    f"✅ *绑定成功！*\n\n"
                    f"您的账号 `{result.get('username')}` 已成功绑定。\n\n"
                    f"现在可以使用所有功能了！",
                    reply_markup=reply_markup,
                    parse_mode=ParseMode.MARKDOWN
                )
            else:
                await update.effective_message.reply_text(
                    f"❌ *绑定失败*\n\n{result.get('message', '未知错误')}",
                    parse_mode=ParseMode.MARKDOWN
                )
            return
        elif current_state.startswith('input_redemption_code_'):
            # 处理兑换码输入
            exchange = current_state.replace('input_redemption_code_', '')
            await self._process_redemption_code(update, context, exchange, text)
            return
        elif current_state.startswith('input_api_key_'):
            # 处理 API Key 输入
            exchange = current_state.replace('input_api_key_', '')
            context_data['api_key'] = text
            context_data['step'] = 'api_secret'
            state_manager.update_session(
                user.id,
                current_state=f'input_api_secret_{exchange}',
                context_data=context_data
            )
            await update.effective_message.reply_text(
                f"📝 请输入您的 {exchange.upper()} API Secret：",
                parse_mode=ParseMode.MARKDOWN
            )
            return
        elif current_state.startswith('input_api_secret_'):
            # 处理 API Secret 输入
            exchange = current_state.replace('input_api_secret_', '')
            context_data['api_secret'] = text
            
            if exchange == 'okx':
                # OKX 需要 Passphrase
                context_data['step'] = 'passphrase'
                state_manager.update_session(
                    user.id,
                    current_state=f'input_passphrase_{exchange}',
                    context_data=context_data
                )
                await update.effective_message.reply_text(
                    "📝 请输入您的 OKX Passphrase：",
                    parse_mode=ParseMode.MARKDOWN
                )
            else:
                # Binance 不需要 Passphrase，直接保存
                await self._save_api_config(update, context, exchange, context_data)
            return
        elif current_state.startswith('input_passphrase_'):
            # 处理 Passphrase 输入（仅 OKX）
            exchange = current_state.replace('input_passphrase_', '')
            context_data['passphrase'] = text
            await self._save_api_config(update, context, exchange, context_data)
            return
        elif current_state.startswith('configure_account'):
            # 处理账号配置输入
            step = context_data.get('step', '')
            if step == 'username':
                # 更新用户名
                user_service = self.get_user_service()
                platform_user = user_service.get_user_by_telegram_id(user.id)
                if not platform_user:
                    await update.effective_message.reply_text("❌ 请先绑定账号")
                    return
                
                result = user_service.update_user_credentials(
                    user_id=platform_user['user_id'],
                    username=text
                )
                
                if result.get('success'):
                    await update.effective_message.reply_text(
                        f"✅ 用户名已更新为: `{text}`",
                        parse_mode=ParseMode.MARKDOWN
                    )
                    state_manager.update_session(user.id, current_state='main_menu', context_data={})
                else:
                    await update.effective_message.reply_text(
                        f"❌ {result.get('message', '更新失败')}",
                        parse_mode=ParseMode.MARKDOWN
                    )
            elif step == 'password':
                # 更新密码
                user_service = self.get_user_service()
                platform_user = user_service.get_user_by_telegram_id(user.id)
                if not platform_user:
                    await update.effective_message.reply_text("❌ 请先绑定账号")
                    return
                
                result = user_service.update_user_credentials(
                    user_id=platform_user['user_id'],
                    password=text
                )
                
                if result.get('success'):
                    await update.effective_message.reply_text(
                        "✅ 密码已更新",
                        parse_mode=ParseMode.MARKDOWN
                    )
                    state_manager.update_session(user.id, current_state='main_menu', context_data={})
                else:
                    await update.effective_message.reply_text(
                        f"❌ {result.get('message', '更新失败')}",
                        parse_mode=ParseMode.MARKDOWN
                    )
            return
        elif current_state.startswith('create_forward_trade_config_name'):
            # 处理配置名称输入
            config_name = text.strip()
            if not config_name:
                await update.effective_message.reply_text("❌ 配置名称不能为空，请重新输入：")
                return
            
            context_data['config_name'] = config_name
            state_manager.update_session(
                user.id,
                current_state='create_forward_trade_config_ratio',
                context_data=context_data
            )
            await update.effective_message.reply_text(
                "📝 *输入金额比例*\n\n"
                "请输入金额比例（0.0001-1.0000）：\n"
                "例如：0.5 表示使用 50% 的金额\n"
                "例如：1.0 表示使用 100% 的金额",
                parse_mode=ParseMode.MARKDOWN
            )
            return
        elif current_state == 'create_forward_trade_config_ratio':
            # 处理金额比例输入
            try:
                ratio = float(text.strip())
                if ratio < 0.0001 or ratio > 1.0:
                    await update.effective_message.reply_text(
                        "❌ 金额比例必须在 0.0001 到 1.0000 之间，请重新输入："
                    )
                    return
            except ValueError:
                await update.effective_message.reply_text("❌ 请输入有效的数字，请重新输入：")
                return
            
            context_data['amount_ratio'] = ratio
            state_manager.update_session(
                user.id,
                current_state='create_forward_trade_config_confirm',
                context_data=context_data
            )
            
            # 显示配置摘要并确认
            source_platform_name = context_data.get('source_platform_name', '未知')
            exchange = context_data.get('exchange', '未知').upper()
            customer_name = context_data.get('customer_name', '未知')
            
            summary_text = f"""📋 *配置摘要*

• 配置名称: `{context_data.get('config_name')}`
• 源平台: {source_platform_name}
• 交易所: {exchange}
• 账户: {customer_name}
• 金额比例: {ratio * 100:.2f}%

💡 点击下方按钮确认创建，或输入其他内容取消。"""
            
            keyboard = [
                [InlineKeyboardButton("✅ 确认创建", callback_data="confirm_create_forward_trade")],
                [InlineKeyboardButton("❌ 取消", callback_data="forward_trade_config")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await update.effective_message.reply_text(
                summary_text,
                reply_markup=reply_markup,
                parse_mode=ParseMode.MARKDOWN
            )
            return
        
        # 如果执行到这里，说明不是状态输入，也不是按钮文本，显示未知命令提示
        # 注意：按钮文本的处理已经在上面完成了，这里只处理未知命令
        await update.effective_message.reply_text(
            "❓ 未知命令。\n\n"
            "使用 /help 查看帮助信息，或点击下方按钮使用功能。",
            parse_mode=ParseMode.MARKDOWN
        )
    
    async def _process_redemption_code(self, update: Update, context: ContextTypes.DEFAULT_TYPE, exchange: str, code: str):
        """处理兑换码"""
        user = update.effective_user
        user_service = self.get_user_service()
        api_service = self.get_exchange_api_service()
        
        if not user_service or not api_service:
            await update.effective_message.reply_text("❌ 服务不可用")
            return
        
        platform_user = user_service.get_user_by_telegram_id(user.id)
        if not platform_user:
            await update.effective_message.reply_text("❌ 请先绑定账号")
            return
        
        user_id = platform_user['user_id']
        
        # 验证兑换码
        validation = api_service.validate_redemption_code(code, exchange, user_id)
        
        if not validation['valid']:
            await update.effective_message.reply_text(
                f"❌ *兑换码验证失败*\n\n{validation.get('message', '未知错误')}",
                parse_mode=ParseMode.MARKDOWN
            )
            return
        
        # 使用兑换码
        use_result = api_service.use_redemption_code(code, exchange, user_id)
        
        if use_result.get('success'):
            from core.message_forward.telegram_bot.state_manager import StateManager
            state_manager = StateManager(self.get_db_pool())
            state_manager.update_session(user.id, current_state='main_menu', context_data={})
            
            await update.effective_message.reply_text(
                f"✅ *兑换码使用成功！*\n\n"
                f"您现在可以配置 {exchange.upper()} API 了。\n\n"
                f"请前往「我的」菜单配置 API。",
                parse_mode=ParseMode.MARKDOWN
            )
        else:
            await update.effective_message.reply_text(
                f"❌ {use_result.get('message', '使用失败')}",
                parse_mode=ParseMode.MARKDOWN
            )
    
    async def _save_api_config(self, update: Update, context: ContextTypes.DEFAULT_TYPE, exchange: str, context_data: dict):
        """保存 API 配置"""
        user = update.effective_user
        user_service = self.get_user_service()
        api_service = self.get_exchange_api_service()
        
        if not user_service or not api_service:
            await update.effective_message.reply_text("❌ 服务不可用")
            return
        
        platform_user = user_service.get_user_by_telegram_id(user.id)
        if not platform_user:
            await update.effective_message.reply_text("❌ 请先绑定账号")
            return
        
        user_id = platform_user['user_id']
        api_key = context_data.get('api_key')
        api_secret = context_data.get('api_secret')
        passphrase = context_data.get('passphrase')
        
        if not api_key or not api_secret:
            await update.effective_message.reply_text("❌ API Key 或 Secret 不能为空")
            return
        
        # 保存配置
        result = api_service.save_exchange_api_config(
            user_id=user_id,
            exchange=exchange,
            api_key=api_key,
            api_secret=api_secret,
            passphrase=passphrase
        )
        
        from core.message_forward.telegram_bot.state_manager import StateManager
        state_manager = StateManager(self.get_db_pool())
        state_manager.update_session(user.id, current_state='main_menu', context_data={})
        
        if result.get('success'):
            from core.message_forward.telegram_bot.keyboard_builder import KeyboardBuilder
            reply_markup = KeyboardBuilder.build_main_menu()
            
            # 转义特殊字符以避免 Markdown 解析错误
            exchange_upper = exchange.upper()
            await update.effective_message.reply_text(
                f"✅ {exchange_upper} API 配置成功！\n\n"
                f"您的 API 配置已保存。",
                reply_markup=reply_markup
            )
        else:
            error_message = result.get('message', '未知错误')
            # 转义特殊字符以避免 Markdown 解析错误
            await update.effective_message.reply_text(
                f"❌ 配置失败\n\n{error_message}"
            )
    
    async def handle_callback_query(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """处理回调查询（Inline 按钮点击）"""
        query = update.callback_query
        user = update.effective_user
        data = query.data
        
        logger.info(f"用户 {user.id} 点击回调按钮: {data}")
        
        # 解析回调数据
        if data.startswith("toggle_interval:"):
            interval = data.split(":")[1]
            await self.handle_toggle_interval(update, context, interval)
        elif data.startswith("toggle_strategy:"):
            strategy = data.split(":")[1]
            await self.handle_toggle_strategy(update, context, strategy)
        elif data == "select_intervals":
            await self.handle_select_intervals(update, context)
        elif data == "select_strategies":
            await self.handle_select_strategies(update, context)
        elif data == "confirm_intervals":
            await self.handle_confirm_intervals(update, context)
        elif data == "confirm_strategies":
            await self.handle_confirm_strategies(update, context)
        elif data == "save_subscription":
            await self.handle_save_subscription(update, context)
        elif data == "view_subscription":
            await self.handle_view_subscription(update, context)
        elif data == "cancel_subscription":
            await self.handle_cancel_subscription(update, context)
        elif data.startswith("confirm_cancel_subscription:"):
            rule_id = data.split(":")[1]
            await self.handle_confirm_cancel_subscription(update, context, rule_id)
        elif data == "back_to_main":
            await self.handle_back_to_main(update, context)
        elif data == "back_to_subscription_menu":
            await self.handle_back_to_subscription_menu(update, context)
        elif data == "back_to_previous":
            await self.handle_back_to_previous(update, context)
        elif data == "auto_register":
            await self.handle_auto_register(update, context)
        elif data == "bind_existing_account":
            await self.handle_bind_existing_account(update, context)
        elif data == "my_account_menu":
            await self.handle_my_account(update, context)
        elif data == "configure_account":
            await self.handle_configure_account(update, context)
        elif data == "configure_okx_api":
            await self.handle_configure_exchange_api(update, context, 'okx')
        elif data == "configure_binance_api":
            await self.handle_configure_exchange_api(update, context, 'binance')
        elif data == "forward_trade_config":
            await self.handle_forward_trade_config(update, context)
        elif data == "create_forward_trade_config":
            await self.handle_create_forward_trade_config(update, context)
        elif data.startswith("toggle_forward_trade:"):
            config_id = int(data.split(":")[1])
            await self.handle_toggle_forward_trade_config(update, context, config_id)
        elif data.startswith("select_tradingview_platform:"):
            platform_id = int(data.split(":")[1])
            await self.handle_select_tradingview_platform_for_trade(update, context, platform_id)
        elif data.startswith("select_exchange_for_trade:"):
            exchange = data.split(":")[1]
            await self.handle_select_exchange_for_trade(update, context, exchange)
        elif data == "confirm_create_forward_trade":
            await self.handle_confirm_create_forward_trade(update, context)
        elif data.startswith("input_redemption_code:"):
            exchange = data.split(":")[1]
            await self.handle_input_redemption_code(update, context, exchange)
        elif data.startswith("input_api_key:"):
            exchange = data.split(":")[1]
            await self.handle_input_api_key(update, context, exchange)
        elif data.startswith("input_api_secret:"):
            exchange = data.split(":")[1]
            await self.handle_input_api_secret(update, context, exchange)
        elif data.startswith("input_passphrase:"):
            exchange = data.split(":")[1]
            await self.handle_input_passphrase(update, context, exchange)
        elif data == "input_username":
            await self.handle_input_username(update, context)
        elif data == "input_password":
            await self.handle_input_password(update, context)
        else:
            await query.answer("未知操作")
    
    # ==================== 订阅管理处理器 ====================
    
    async def handle_subscription_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """显示订阅管理菜单"""
        from core.message_forward.telegram_bot.keyboard_builder import KeyboardBuilder
        from core.message_forward.telegram_bot.state_manager import StateManager
        
        user_id = update.effective_user.id
        state_manager = StateManager(self.get_db_pool())
        
        # 推入导航栈
        state_manager.push_navigation(user_id, 'subscription_menu')
        state_manager.update_session(user_id, current_state='subscription_menu')
        
        menu_text = """📊 *订阅管理*

请选择要执行的操作：

• 🆕 新建订阅 - 选择时间周期和策略，创建新的订阅
• 📋 查看订阅 - 查看当前订阅状态和详情"""
        
        reply_markup = KeyboardBuilder.build_subscription_menu()
        
        if update.callback_query:
            try:
                await update.callback_query.edit_message_text(
                    menu_text,
                    reply_markup=reply_markup,
                    parse_mode="Markdown"
                )
                await update.callback_query.answer()
            except Exception:
                await update.callback_query.message.reply_text(
                    menu_text,
                    reply_markup=reply_markup,
                    parse_mode="Markdown"
                )
                await update.callback_query.answer()
        else:
            await update.effective_message.reply_text(
                menu_text,
                reply_markup=reply_markup,
                parse_mode="Markdown"
            )
    
    async def handle_select_intervals(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """显示时间周期选择界面"""
        from core.message_forward.telegram_bot.keyboard_builder import KeyboardBuilder
        from core.message_forward.telegram_bot.state_manager import StateManager
        
        user_id = update.effective_user.id
        
        # 获取用户当前选择的周期（从会话状态）
        state_manager = StateManager(self.get_db_pool())
        session = state_manager.get_session(user_id)
        selected_intervals = session.get('context_data', {}).get('selected_intervals', [])
        
        # 推入导航栈
        state_manager.push_navigation(user_id, 'select_intervals')
        state_manager.update_session(user_id, current_state='select_intervals')
        
        menu_text = """⏱️ *选择时间周期*

请选择您想要接收的时间周期（可多选）：

💡 点击周期名称进行选择/取消，已选择的周期会显示 ✅"""
        
        reply_markup = KeyboardBuilder.build_interval_selection(selected_intervals, show_back=True, back_to="back_to_subscription_menu")
        
        await update.callback_query.edit_message_text(
            menu_text,
            reply_markup=reply_markup,
            parse_mode="Markdown"
        )
        await update.callback_query.answer()
    
    async def handle_select_strategies(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """显示策略选择界面"""
        from core.message_forward.telegram_bot.keyboard_builder import KeyboardBuilder
        from core.message_forward.telegram_bot.state_manager import StateManager
        
        user_id = update.effective_user.id
        
        # 获取用户当前选择的策略（从会话状态）
        state_manager = StateManager(self.get_db_pool())
        session = state_manager.get_session(user_id)
        selected_strategies = session.get('context_data', {}).get('selected_strategies', [])
        
        # 推入导航栈
        state_manager.push_navigation(user_id, 'select_strategies')
        state_manager.update_session(user_id, current_state='select_strategies')
        
        menu_text = """📈 *选择策略*

请选择您想要接收的策略（可多选）：

💡 点击策略名称进行选择/取消，已选择的策略会显示 ✅"""
        
        reply_markup = KeyboardBuilder.build_strategy_selection(selected_strategies, show_back=True, back_to="back_to_subscription_menu")
        
        await update.callback_query.edit_message_text(
            menu_text,
            reply_markup=reply_markup,
            parse_mode="Markdown"
        )
        await update.callback_query.answer()
    
    async def handle_toggle_interval(self, update: Update, context: ContextTypes.DEFAULT_TYPE, interval: str):
        """切换时间周期选择"""
        from core.message_forward.telegram_bot.keyboard_builder import KeyboardBuilder
        from core.message_forward.telegram_bot.state_manager import StateManager
        
        user_id = update.effective_user.id
        state_manager = StateManager(self.get_db_pool())
        
        # 获取当前会话
        session = state_manager.get_session(user_id)
        context_data = session.get('context_data', {})
        selected_intervals = context_data.get('selected_intervals', [])
        
        # 切换选择状态
        if interval in selected_intervals:
            selected_intervals.remove(interval)
        else:
            selected_intervals.append(interval)
        
        # 更新会话状态
        context_data['selected_intervals'] = selected_intervals
        state_manager.update_session(user_id, context_data=context_data)
        
        # 更新键盘显示
        reply_markup = KeyboardBuilder.build_interval_selection(selected_intervals, show_back=True, back_to="back_to_subscription_menu")
        await update.callback_query.edit_message_reply_markup(reply_markup=reply_markup)
        action = "✅ 已选择" if interval in selected_intervals else "❌ 已取消"
        await update.callback_query.answer(f"{action}: {interval}")
    
    async def handle_toggle_strategy(self, update: Update, context: ContextTypes.DEFAULT_TYPE, strategy: str):
        """切换策略选择"""
        from core.message_forward.telegram_bot.keyboard_builder import KeyboardBuilder
        from core.message_forward.telegram_bot.state_manager import StateManager
        
        user_id = update.effective_user.id
        state_manager = StateManager(self.get_db_pool())
        
        # 获取当前会话
        session = state_manager.get_session(user_id)
        context_data = session.get('context_data', {})
        selected_strategies = context_data.get('selected_strategies', [])
        
        # 切换选择状态
        if strategy in selected_strategies:
            selected_strategies.remove(strategy)
        else:
            selected_strategies.append(strategy)
        
        # 更新会话状态
        context_data['selected_strategies'] = selected_strategies
        state_manager.update_session(user_id, context_data=context_data)
        
        # 更新键盘显示
        reply_markup = KeyboardBuilder.build_strategy_selection(selected_strategies, show_back=True, back_to="back_to_subscription_menu")
        await update.callback_query.edit_message_reply_markup(reply_markup=reply_markup)
        action = "✅ 已选择" if strategy in selected_strategies else "❌ 已取消"
        await update.callback_query.answer(f"{action}: {strategy}")
    
    async def handle_confirm_intervals(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """确认时间周期选择"""
        from core.message_forward.telegram_bot.state_manager import StateManager
        
        user_id = update.effective_user.id
        state_manager = StateManager(self.get_db_pool())
        
        session = state_manager.get_session(user_id)
        selected_intervals = session.get('context_data', {}).get('selected_intervals', [])
        
        if not selected_intervals:
            await update.callback_query.answer("⚠️ 请至少选择一个时间周期", show_alert=True)
            return
        
        # 更新状态
        state_manager.update_session(user_id, current_state='select_strategies')
        
        # 显示策略选择界面
        await self.handle_select_strategies(update, context)
    
    async def handle_confirm_strategies(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """确认策略选择"""
        from core.message_forward.telegram_bot.state_manager import StateManager
        
        user_id = update.effective_user.id
        state_manager = StateManager(self.get_db_pool())
        
        session = state_manager.get_session(user_id)
        selected_strategies = session.get('context_data', {}).get('selected_strategies', [])
        
        if not selected_strategies:
            await update.callback_query.answer("⚠️ 请至少选择一个策略", show_alert=True)
            return
        
        # 显示保存确认界面
        await self.handle_show_save_confirmation(update, context)
    
    async def handle_show_save_confirmation(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """显示保存确认界面"""
        from core.message_forward.telegram_bot.keyboard_builder import KeyboardBuilder
        from core.message_forward.telegram_bot.state_manager import StateManager
        
        user_id = update.effective_user.id
        state_manager = StateManager(self.get_db_pool())
        
        session = state_manager.get_session(user_id)
        context_data = session.get('context_data', {})
        selected_intervals = context_data.get('selected_intervals', [])
        selected_strategies = context_data.get('selected_strategies', [])
        
        # 推入导航栈
        state_manager.push_navigation(user_id, 'save_confirmation')
        state_manager.update_session(user_id, current_state='save_confirmation')
        
        confirmation_text = f"""✅ *确认订阅配置*

请确认以下配置信息：

⏱️ *时间周期*:
{', '.join(selected_intervals) if selected_intervals else '未选择'}

📈 *策略*:
{', '.join(selected_strategies) if selected_strategies else '未选择'}

━━━━━━━━━━━━━━

💡 点击「✅ 保存订阅」确认，或点击「🔙 返回」修改。"""
        
        reply_markup = KeyboardBuilder.build_save_confirmation(show_back=True)
        
        await update.callback_query.edit_message_text(
            confirmation_text,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=reply_markup
        )
        await update.callback_query.answer()
    
    async def handle_save_subscription(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """保存订阅配置"""
        from core.message_forward.telegram_bot.state_manager import StateManager
        
        user_id = update.effective_user.id
        username = update.effective_user.username or ''
        state_manager = StateManager(self.get_db_pool())
        subscription_service = self.get_subscription_service()
        
        if not subscription_service:
            await update.callback_query.answer("❌ 订阅服务不可用", show_alert=True)
            return
        
        # 获取用户选择的配置
        session = state_manager.get_session(user_id)
        context_data = session.get('context_data', {})
        selected_intervals = context_data.get('selected_intervals', [])
        selected_strategies = context_data.get('selected_strategies', [])
        
        # 获取或创建默认规则ID（匹配所有 TradingView 平台）
        rule_id = self.config.get('default_rule_id')
        
        # 获取当前平台ID（从配置或数据库）
        target_platform_id = self._get_platform_id()
        if not target_platform_id:
            await update.callback_query.answer("❌ 无法获取平台ID，请检查配置", show_alert=True)
            return
        
        # 如果没有配置 rule_id，尝试从数据库查找或创建
        if not rule_id:
            rule_id = self._get_or_create_default_rule(target_platform_id)
        
        # source_platform_id 设置为 None，表示匹配所有 TradingView 平台
        # 在订阅表中，source_platform_id 可以存储为 0 或 NULL，表示匹配所有
        source_platform_id = None  # 不绑定特定的 TradingView 平台，接收所有 TradingView 消息
        
        try:
            # 创建或更新订阅
            result = subscription_service.create_or_update_subscription(
                user_id=user_id,
                username=username,
                rule_id=rule_id,
                source_platform_id=source_platform_id,
                target_platform_id=target_platform_id,
                intervals=selected_intervals,
                strategies=selected_strategies,
                duration_days=30
            )
            
            if result.get('success'):
                # 清除会话状态
                state_manager.update_session(user_id, current_state='main_menu', context_data={})
                
                success_text = f"""✅ *订阅配置已保存！*

您的订阅配置如下：

⏱️ *时间周期*: {', '.join(selected_intervals) if selected_intervals else '未选择'}
📈 *策略*: {', '.join(selected_strategies) if selected_strategies else '未选择'}

━━━━━━━━━━━━━━

🎉 您将开始接收匹配的交易信号！

💡 使用下方按钮继续操作。"""
                
                from core.message_forward.telegram_bot.keyboard_builder import KeyboardBuilder
                reply_markup = KeyboardBuilder.build_main_menu()
                
                try:
                    await update.callback_query.edit_message_text(
                        success_text,
                        parse_mode=ParseMode.MARKDOWN,
                        reply_markup=reply_markup
                    )
                except Exception:
                    # 如果编辑失败，发送新消息
                    await update.callback_query.message.reply_text(
                        success_text,
                        parse_mode=ParseMode.MARKDOWN,
                        reply_markup=reply_markup
                    )
                await update.callback_query.answer("✅ 订阅已保存", show_alert=True)
            else:
                # Telegram callback query answer 消息限制为 200 字符
                error_msg = result.get('message', '未知错误')
                full_msg = f"保存失败: {error_msg}"
                await update.callback_query.answer(self._truncate_message(full_msg), show_alert=True)
                
        except Exception as e:
            logger.error(f"保存订阅失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
            # 截断错误消息，确保不超过 200 字符
            error_msg = f"保存失败: {str(e)}"
            await update.callback_query.answer(self._truncate_message(error_msg), show_alert=True)
    
    async def handle_cancel_subscription(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """取消订阅"""
        from core.message_forward.telegram_bot.state_manager import StateManager
        from core.message_forward.telegram_bot.keyboard_builder import KeyboardBuilder
        
        user_id = update.effective_user.id
        subscription_service = self.get_subscription_service()
        
        if not subscription_service:
            await update.callback_query.answer("❌ 订阅服务不可用", show_alert=True)
            return
        
        # 获取用户的订阅
        subscriptions = subscription_service.get_user_subscriptions(user_id)
        if not subscriptions:
            await update.callback_query.answer("❌ 您当前没有活跃的订阅", show_alert=True)
            return
        
        # 获取默认规则ID
        rule_id = self.config.get('default_rule_id')
        if not rule_id:
            # 如果没有配置，使用第一个订阅的规则ID
            rule_id = subscriptions[0].get('rule_id')
        
        # 确认取消
        confirm_text = f"""⚠️ *确认取消订阅*

确定要取消订阅吗？

取消后，您将不再接收交易信号。

此操作可以随时恢复。"""
        
        from telegram import InlineKeyboardMarkup, InlineKeyboardButton
        confirm_keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ 确认取消", callback_data=f"confirm_cancel_subscription:{rule_id}")],
            [InlineKeyboardButton("❌ 取消", callback_data="back_to_subscription_menu")]
        ])
        
        try:
            await update.callback_query.edit_message_text(
                confirm_text,
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=confirm_keyboard
            )
        except Exception:
            await update.callback_query.message.reply_text(
                confirm_text,
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=confirm_keyboard
            )
        await update.callback_query.answer()
    
    async def handle_confirm_cancel_subscription(self, update: Update, context: ContextTypes.DEFAULT_TYPE, rule_id: str):
        """确认取消订阅"""
        from core.message_forward.telegram_bot.state_manager import StateManager
        from core.message_forward.telegram_bot.keyboard_builder import KeyboardBuilder
        
        user_id = update.effective_user.id
        subscription_service = self.get_subscription_service()
        
        if not subscription_service:
            await update.callback_query.answer("❌ 订阅服务不可用", show_alert=True)
            return
        
        # 取消订阅
        success = subscription_service.cancel_subscription(user_id, rule_id)
        
        if success:
            state_manager = StateManager(self.get_db_pool())
            state_manager.update_session(user_id, current_state='main_menu', context_data={})
            
            reply_markup = KeyboardBuilder.build_main_menu()
            
            success_text = """✅ *订阅已取消*

您已成功取消订阅。

如需重新订阅，请前往「📊 订阅管理」菜单。"""
            
            try:
                await update.callback_query.edit_message_text(
                    success_text,
                    parse_mode=ParseMode.MARKDOWN,
                    reply_markup=reply_markup
                )
            except Exception:
                await update.callback_query.message.reply_text(
                    success_text,
                    parse_mode=ParseMode.MARKDOWN,
                    reply_markup=reply_markup
                )
            await update.callback_query.answer("✅ 订阅已取消", show_alert=True)
        else:
            await update.callback_query.answer("❌ 取消订阅失败，请稍后重试", show_alert=True)
    
    async def handle_view_subscription(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """查看当前订阅详情"""
        from core.message_forward.telegram_bot.state_manager import StateManager
        from core.message_forward.telegram_bot.keyboard_builder import KeyboardBuilder
        from telegram import InlineKeyboardMarkup
        from datetime import datetime
        
        user_id = update.effective_user.id
        state_manager = StateManager(self.get_db_pool())
        
        # 推入导航栈
        state_manager.push_navigation(user_id, 'view_subscription')
        state_manager.update_session(user_id, current_state='view_subscription')
        
        # 获取订阅服务
        subscription_service = self.get_subscription_service()
        if not subscription_service:
            error_text = "❌ 订阅服务暂时不可用，请稍后再试。"
            if update.callback_query:
                await update.callback_query.answer(error_text, show_alert=True)
            else:
                await update.effective_message.reply_text(error_text)
            return
        
        # 获取用户的所有订阅
        subscriptions = subscription_service.get_user_subscriptions(user_id)
        
        if not subscriptions:
            detail_text = """📋 *订阅详情*

您当前没有活跃的订阅。

👉 点击「📊 订阅管理」来创建订阅。"""
            reply_markup = KeyboardBuilder.build_subscription_menu()
        else:
            detail_text = "📋 *我的订阅详情*\n\n"
            
            for idx, sub in enumerate(subscriptions, 1):
                detail_text += f"━━━━━━━━━━━━━━━━━━━━\n"
                detail_text += f"*订阅 #{idx}*\n\n"
                
                # 规则名称
                rule_name = sub.get('rule_name', '未知规则')
                detail_text += f"📋 *规则名称*: {rule_name}\n"
                
                # 订阅状态
                status = sub.get('subscription_status', '未知')
                status_emoji = {
                    'active': '✅',
                    'expired': '⏰',
                    'cancelled': '❌',
                    'paused': '⏸️'
                }.get(status, '❓')
                status_text = {
                    'active': '活跃中',
                    'expired': '已过期',
                    'cancelled': '已取消',
                    'paused': '已暂停'
                }.get(status, status)
                detail_text += f"{status_emoji} *状态*: {status_text}\n\n"
                
                # 时间周期
                intervals = sub.get('intervals', [])
                if intervals:
                    detail_text += f"⏱️ *订阅时间周期*\n"
                    detail_text += f"   {', '.join(intervals)}\n\n"
                else:
                    detail_text += f"⏱️ *订阅时间周期*: 未选择\n\n"
                
                # 策略
                strategies = sub.get('strategies', [])
                if strategies:
                    detail_text += f"📈 *订阅策略*\n"
                    detail_text += f"   {', '.join(strategies)}\n\n"
                else:
                    detail_text += f"📈 *订阅策略*: 未选择\n\n"
                
                # 时间信息
                start_date = sub.get('start_date')
                expire_date = sub.get('expire_date')
                
                if start_date:
                    try:
                        if isinstance(start_date, str):
                            start_date = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
                        detail_text += f"📅 *开始时间*: {start_date.strftime('%Y-%m-%d %H:%M:%S')}\n"
                    except Exception:
                        pass
                
                if expire_date:
                    try:
                        if isinstance(expire_date, str):
                            expire_date = datetime.fromisoformat(expire_date.replace('Z', '+00:00'))
                        days_left = (expire_date - datetime.now()).days
                        detail_text += f"📅 *过期时间*: {expire_date.strftime('%Y-%m-%d %H:%M:%S')}\n"
                        if days_left > 0:
                            detail_text += f"⏳ *剩余天数*: {days_left} 天\n"
                        else:
                            detail_text += f"⚠️ *已过期*: {abs(days_left)} 天前\n"
                    except Exception:
                        pass
                else:
                    detail_text += f"📅 *过期时间*: 永不过期\n"
                
                # 统计信息
                messages_received = sub.get('messages_received', 0)
                last_message_at = sub.get('last_message_at')
                
                detail_text += f"\n📊 *统计信息*\n"
                detail_text += f"   📨 已接收消息: {messages_received} 条\n"
                
                if last_message_at:
                    try:
                        if isinstance(last_message_at, str):
                            last_message_at = datetime.fromisoformat(last_message_at.replace('Z', '+00:00'))
                        detail_text += f"   🕐 最后接收: {last_message_at.strftime('%Y-%m-%d %H:%M:%S')}\n"
                    except Exception:
                        detail_text += f"   🕐 最后接收: 未知\n"
                else:
                    detail_text += f"   🕐 最后接收: 暂无\n"
                
                detail_text += "\n"
            
            # 添加返回按钮
            back_button = KeyboardBuilder.build_back_button("back_to_subscription_menu")
            reply_markup = InlineKeyboardMarkup([back_button])
        
        # 发送消息
        if update.callback_query:
            try:
                await update.callback_query.edit_message_text(
                    detail_text,
                    parse_mode=ParseMode.MARKDOWN,
                    reply_markup=reply_markup
                )
                await update.callback_query.answer()
            except Exception as e:
                # 如果编辑失败，发送新消息
                logger.debug(f"编辑消息失败，发送新消息: {e}")
                await update.callback_query.message.reply_text(
                    detail_text,
                    parse_mode=ParseMode.MARKDOWN,
                    reply_markup=reply_markup
                )
                await update.callback_query.answer()
        else:
            await update.effective_message.reply_text(
                detail_text,
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=reply_markup
            )
    
    async def handle_back_to_main(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """返回主菜单（统一入口）"""
        from core.message_forward.telegram_bot.keyboard_builder import KeyboardBuilder
        from core.message_forward.telegram_bot.state_manager import StateManager
        
        user_id = update.effective_user.id
        state_manager = StateManager(self.get_db_pool())
        
        # 清空导航栈并重置状态
        state_manager.clear_navigation(user_id)
        state_manager.update_session(user_id, current_state='main_menu', context_data={'navigation_stack': []})
        
        main_text = """👋 *欢迎使用交易信号订阅 Bot！*

📊 您可以订阅来自 TradingView 的交易信号，并自定义选择接收哪些时间周期和策略的信号。

✨ *主要功能*
• 📊 订阅管理 - 自定义订阅交易信号
• 📈 查看状态 - 查看当前订阅信息
• ⚙️ 灵活配置 - 选择时间周期和策略

💡 使用下方按钮开始使用，或发送 /help 查看帮助信息。"""
        
        reply_markup = KeyboardBuilder.build_main_menu()
        
        # 如果是回调查询，编辑消息；如果是普通消息，发送新消息
        if update.callback_query:
            try:
                await update.callback_query.edit_message_text(
                    main_text,
                    reply_markup=reply_markup,
                    parse_mode=ParseMode.MARKDOWN
                )
            except Exception:
                # 如果编辑失败，发送新消息
                await update.callback_query.message.reply_text(
                    main_text,
                    reply_markup=reply_markup,
                    parse_mode=ParseMode.MARKDOWN
                )
            await update.callback_query.answer()
        else:
            await update.effective_message.reply_text(
                main_text,
                reply_markup=reply_markup,
                parse_mode=ParseMode.MARKDOWN
            )
    
    async def handle_back_to_subscription_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """返回订阅管理菜单"""
        from core.message_forward.telegram_bot.state_manager import StateManager
        
        user_id = update.effective_user.id
        state_manager = StateManager(self.get_db_pool())
        
        # 弹出当前页面，返回到订阅管理菜单
        state_manager.pop_navigation(user_id)
        
        # 显示订阅管理菜单
        await self.handle_subscription_menu(update, context)
    
    async def handle_back_to_previous(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """返回上一页（根据导航栈）"""
        from core.message_forward.telegram_bot.state_manager import StateManager
        
        user_id = update.effective_user.id
        state_manager = StateManager(self.get_db_pool())
        
        # 获取上一页
        previous_page = state_manager.pop_navigation(user_id)
        
        if previous_page == 'subscription_menu':
            await self.handle_subscription_menu(update, context)
        elif previous_page == 'select_intervals':
            await self.handle_select_intervals(update, context)
        elif previous_page == 'select_strategies':
            await self.handle_select_strategies(update, context)
        elif previous_page == 'save_confirmation':
            await self.handle_show_save_confirmation(update, context)
        else:
            # 如果没有上一页或未知页面，返回主菜单
            await self.handle_back_to_main(update, context)
    
    # ==================== 用户验证和账号管理 ====================
    
    async def handle_auto_register(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """处理自动注册"""
        user = update.effective_user
        user_service = self.get_user_service()
        
        if not user_service:
            await update.callback_query.answer("❌ 用户服务不可用", show_alert=True)
            return
        
        # 创建账号
        result = user_service.create_user_account(
            telegram_user_id=user.id,
            telegram_username=user.username,
            auto_generate=True
        )
        
        if result.get('success'):
            username = result['username']
            password = result['password']
            
            success_text = f"""✅ *账号创建成功！*

📋 *您的账号信息*:
• 用户名: `{username}`
• 密码: `{password}`

⚠️ *重要提示*:
请妥善保管您的密码，建议您稍后在「我的」菜单中修改密码。

💡 您现在可以使用所有功能了！"""
            
            # 使用内联键盘（因为原始消息是内联键盘）
            from telegram import InlineKeyboardMarkup, InlineKeyboardButton
            from core.message_forward.telegram_bot.keyboard_builder import KeyboardBuilder
            
            # 构建内联键盘，包含返回主菜单按钮
            inline_keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("🏠 返回主菜单", callback_data="back_to_main")]
            ])
            
            await update.callback_query.edit_message_text(
                success_text,
                reply_markup=inline_keyboard,
                parse_mode=ParseMode.MARKDOWN
            )
            
            # 发送固定键盘消息（用于主菜单）
            await update.callback_query.message.reply_text(
                "💡 您可以使用以下按钮快速访问功能：",
                reply_markup=KeyboardBuilder.build_main_menu()
            )
            
            await update.callback_query.answer("✅ 账号创建成功！")
        else:
            await update.callback_query.answer(
                result.get('message', '注册失败'),
                show_alert=True
            )
    
    async def handle_bind_existing_account(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """处理绑定现有账号"""
        from core.message_forward.telegram_bot.state_manager import StateManager
        
        user_id = update.effective_user.id
        state_manager = StateManager(self.get_db_pool())
        
        # 设置状态为等待输入用户名
        state_manager.update_session(
            user_id,
            current_state='bind_account_username',
            context_data={'step': 'username'}
        )
        
        text = """🔗 *绑定现有账号*

请输入您的平台用户名："""
        
        await update.callback_query.edit_message_text(
            text,
            parse_mode=ParseMode.MARKDOWN
        )
        await update.callback_query.answer()
    
    async def _check_user_verified(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
        """
        检查用户是否已绑定平台账号
        
        Args:
            update: Telegram Update 对象
            context: Context 对象
        
        Returns:
            True 如果用户已绑定，False 如果未绑定（已发送提示消息）
        """
        user = update.effective_user
        user_service = self.get_user_service()
        
        if not user_service:
            error_text = "❌ 用户服务暂时不可用，请稍后再试。"
            if update.callback_query:
                await update.callback_query.answer(error_text, show_alert=True)
            else:
                await update.effective_message.reply_text(error_text)
            return False
        
        platform_user = user_service.get_user_by_telegram_id(user.id)
        
        if not platform_user:
            # 用户未绑定，提示注册
            welcome_message = """⚠️ *账号验证*
            
检测到您尚未绑定平台账号。请先绑定账号才能使用此功能。

请选择：
1️⃣ *自动注册* - 系统将为您自动生成账号和密码
2️⃣ *绑定现有账号* - 如果您已有平台账号，请输入用户名和密码

💡 绑定账号后，您可以使用所有功能。"""
            
            from core.message_forward.telegram_bot.keyboard_builder import KeyboardBuilder
            reply_markup = KeyboardBuilder.build_registration_menu()
            
            if update.callback_query:
                await update.callback_query.answer("请先绑定账号", show_alert=True)
                await update.callback_query.message.reply_text(
                    welcome_message,
                    reply_markup=reply_markup,
                    parse_mode=ParseMode.MARKDOWN
                )
            else:
                await update.effective_message.reply_text(
                    welcome_message,
                    reply_markup=reply_markup,
                    parse_mode=ParseMode.MARKDOWN
                )
            return False
        
        return True
    
    async def handle_my_account(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """显示我的账号菜单"""
        user = update.effective_user
        user_service = self.get_user_service()
        
        if not user_service:
            error_text = "❌ 用户服务暂时不可用，请稍后再试。"
            if update.callback_query:
                await update.callback_query.answer(error_text, show_alert=True)
            else:
                await update.effective_message.reply_text(error_text)
            return
        
        platform_user = user_service.get_user_by_telegram_id(user.id)
        
        if not platform_user:
            # 用户未绑定，提示注册
            from core.message_forward.telegram_bot.keyboard_builder import KeyboardBuilder
            reply_markup = KeyboardBuilder.build_registration_menu()
            
            text = """⚠️ *账号验证*

您尚未绑定平台账号。

请选择：
1️⃣ 自动注册 - 系统将为您自动生成账号
2️⃣ 绑定现有账号 - 如果您已有平台账号"""
            
            if update.callback_query:
                await update.callback_query.edit_message_text(
                    text,
                    reply_markup=reply_markup,
                    parse_mode=ParseMode.MARKDOWN
                )
                await update.callback_query.answer()
            else:
                await update.effective_message.reply_text(
                    text,
                    reply_markup=reply_markup,
                    parse_mode=ParseMode.MARKDOWN
                )
            return
        
        # 显示我的账号菜单
        from core.message_forward.telegram_bot.keyboard_builder import KeyboardBuilder
        reply_markup = KeyboardBuilder.build_my_account_menu()
        
        # 检查转发交易配置状态
        db_pool = self.get_db_pool()
        forward_trade_status = "❌ 未配置"
        if db_pool:
            try:
                sql = """
                    SELECT COUNT(*) as count, SUM(enabled) as enabled_count
                    FROM forward_trade_configs
                    WHERE user_id = %s
                """
                rows = db_pool.query(sql, (platform_user['user_id'],))
                if rows:
                    total = rows[0].get('count', 0)
                    enabled = rows[0].get('enabled_count', 0)
                    if total > 0:
                        forward_trade_status = f"✅ {enabled}/{total} 个配置已启用"
            except Exception as e:
                logger.debug(f"查询转发交易配置失败: {e}")
        
        account_text = f"""👤 *我的账号*

📋 *账号信息*:
• 用户名: `{platform_user.get('username', '未知')}`
• 状态: {'✅ 活跃' if platform_user.get('status') == 'active' else '❌ 已禁用'}

🔧 *功能*:
• 配置登录凭据（用户名/密码）
• 配置 OKX API
• 配置 Binance API
• 转发交易配置: {forward_trade_status}

💡 *提示*:
配置 API 后，您可以在"转发交易配置"中设置自动跟单交易。"""
        
        if update.callback_query:
            await update.callback_query.edit_message_text(
                account_text,
                reply_markup=reply_markup,
                parse_mode=ParseMode.MARKDOWN
            )
            await update.callback_query.answer()
        else:
            await update.effective_message.reply_text(
                account_text,
                reply_markup=reply_markup,
                parse_mode=ParseMode.MARKDOWN
            )
    
    async def handle_configure_account(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """配置账号（用户名/密码）"""
        from core.message_forward.telegram_bot.keyboard_builder import KeyboardBuilder
        from core.message_forward.telegram_bot.state_manager import StateManager
        
        user_id = update.effective_user.id
        state_manager = StateManager(self.get_db_pool())
        
        # 设置状态为配置账号
        state_manager.update_session(
            user_id,
            current_state='configure_account',
            context_data={'step': 'username'}
        )
        
        text = """⚙️ *配置账号*

请选择要配置的内容："""
        
        reply_markup = KeyboardBuilder.build_configure_account_menu()
        
        await update.callback_query.edit_message_text(
            text,
            reply_markup=reply_markup,
            parse_mode=ParseMode.MARKDOWN
        )
        await update.callback_query.answer()
    
    async def handle_configure_exchange_api(self, update: Update, context: ContextTypes.DEFAULT_TYPE, exchange: str):
        """配置交易所 API"""
        user = update.effective_user
        user_service = self.get_user_service()
        api_service = self.get_exchange_api_service()
        
        if not user_service or not api_service:
            await update.callback_query.answer("❌ 服务不可用", show_alert=True)
            return
        
        platform_user = user_service.get_user_by_telegram_id(user.id)
        if not platform_user:
            await update.callback_query.answer("❌ 请先绑定账号", show_alert=True)
            return
        
        user_id = platform_user['user_id']
        
        # 检查是否已使用兑换码
        has_redemption = api_service.check_user_has_redemption_code(user_id, exchange)
        
        if not has_redemption:
            # 提示用户获取兑换码
            text = f"""⚠️ *配置 {exchange.upper()} API*

在配置 API 之前，您需要先使用兑换码获取配置权限。

📝 *获取兑换码*:
请前往 https://qianlijin.com 获取 {exchange.upper()} API 兑换码。

💡 获取兑换码后，点击下方按钮输入兑换码。"""
            
            from core.message_forward.telegram_bot.keyboard_builder import KeyboardBuilder
            reply_markup = KeyboardBuilder.build_redemption_code_menu(exchange)
            
            await update.callback_query.edit_message_text(
                text,
                reply_markup=reply_markup,
                parse_mode=ParseMode.MARKDOWN
            )
            await update.callback_query.answer()
            return
        
        # 已使用兑换码，显示 API 配置状态
        api_config = api_service.get_exchange_api_config(user_id, exchange)
        
        if api_config and api_config.get('api_key_status') == '已配置':
            text = f"""✅ *{exchange.upper()} API 已配置*

📋 *配置状态*:
• API Key: {api_config.get('api_key_status', '未知')}
• API Secret: {api_config.get('api_secret_status', '未知')}
• 交易所: {api_config.get('exchange', exchange).upper()}

💡 您可以重新配置 API。"""
        else:
            text = f"""⚙️ *配置 {exchange.upper()} API*

📋 *当前状态*: 未配置

💡 请按顺序输入：
1. API Key
2. API Secret
{f"3. Passphrase（仅 {exchange.upper()} 需要）" if exchange == 'okx' else ""}"""
        
        from core.message_forward.telegram_bot.keyboard_builder import KeyboardBuilder
        from core.message_forward.telegram_bot.state_manager import StateManager
        
        state_manager = StateManager(self.get_db_pool())
        state_manager.update_session(
            user_id,
            current_state=f'configure_{exchange}_api',
            context_data={'exchange': exchange, 'step': 'api_key'}
        )
        
        reply_markup = KeyboardBuilder.build_configure_api_menu(exchange, api_config is not None)
        
        await update.callback_query.edit_message_text(
            text,
            reply_markup=reply_markup,
            parse_mode=ParseMode.MARKDOWN
        )
        await update.callback_query.answer()
    
    async def handle_input_redemption_code(self, update: Update, context: ContextTypes.DEFAULT_TYPE, exchange: str):
        """处理输入兑换码"""
        from core.message_forward.telegram_bot.state_manager import StateManager
        
        user_id = update.effective_user.id
        state_manager = StateManager(self.get_db_pool())
        
        # 设置状态为等待输入兑换码
        state_manager.update_session(
            user_id,
            current_state=f'input_redemption_code_{exchange}',
            context_data={'exchange': exchange}
        )
        
        text = f"""📝 *输入 {exchange.upper()} 兑换码*

请输入您从 qianlijin.com 获取的兑换码："""
        
        await update.callback_query.edit_message_text(
            text,
            parse_mode=ParseMode.MARKDOWN
        )
        await update.callback_query.answer()
    
    async def handle_input_api_key(self, update: Update, context: ContextTypes.DEFAULT_TYPE, exchange: str):
        """处理输入 API Key"""
        from core.message_forward.telegram_bot.state_manager import StateManager
        
        user_id = update.effective_user.id
        state_manager = StateManager(self.get_db_pool())
        
        # 设置状态为等待输入 API Key
        state_manager.update_session(
            user_id,
            current_state=f'input_api_key_{exchange}',
            context_data={'exchange': exchange, 'step': 'api_key'}
        )
        
        text = f"""📝 *输入 {exchange.upper()} API Key*

请输入您的 API Key："""
        
        await update.callback_query.edit_message_text(
            text,
            parse_mode=ParseMode.MARKDOWN
        )
        await update.callback_query.answer()
    
    async def handle_input_api_secret(self, update: Update, context: ContextTypes.DEFAULT_TYPE, exchange: str):
        """处理输入 API Secret"""
        from core.message_forward.telegram_bot.state_manager import StateManager
        
        user_id = update.effective_user.id
        state_manager = StateManager(self.get_db_pool())
        
        # 设置状态为等待输入 API Secret
        state_manager.update_session(
            user_id,
            current_state=f'input_api_secret_{exchange}',
            context_data={'exchange': exchange, 'step': 'api_secret'}
        )
        
        text = f"""📝 *输入 {exchange.upper()} API Secret*

请输入您的 API Secret："""
        
        await update.callback_query.edit_message_text(
            text,
            parse_mode=ParseMode.MARKDOWN
        )
        await update.callback_query.answer()
    
    async def handle_input_passphrase(self, update: Update, context: ContextTypes.DEFAULT_TYPE, exchange: str):
        """处理输入 Passphrase（仅 OKX）"""
        from core.message_forward.telegram_bot.state_manager import StateManager
        
        user_id = update.effective_user.id
        state_manager = StateManager(self.get_db_pool())
        
        # 设置状态为等待输入 Passphrase
        state_manager.update_session(
            user_id,
            current_state=f'input_passphrase_{exchange}',
            context_data={'exchange': exchange, 'step': 'passphrase'}
        )
        
        text = f"""📝 *输入 {exchange.upper()} Passphrase*

请输入您的 Passphrase："""
        
        await update.callback_query.edit_message_text(
            text,
            parse_mode=ParseMode.MARKDOWN
        )
        await update.callback_query.answer()
    
    async def handle_forward_trade_config(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """显示转发交易配置菜单"""
        user = update.effective_user
        user_service = self.get_user_service()
        
        if not user_service:
            await update.callback_query.answer("❌ 用户服务不可用", show_alert=True)
            return
        
        platform_user = user_service.get_user_by_telegram_id(user.id)
        if not platform_user:
            await update.callback_query.answer("❌ 请先绑定账号", show_alert=True)
            return
        
        db_pool = self.get_db_pool()
        if not db_pool:
            await update.callback_query.answer("❌ 数据库连接不可用", show_alert=True)
            return
        
        user_id = platform_user['user_id']
        customer_uid = platform_user.get('customer_uid')
        
        # 查询用户的转发交易配置
        try:
            sql = """
                SELECT 
                    ftc.id,
                    ftc.config_name,
                    ftc.source_platform_name,
                    ftc.customer_name,
                    ftc.amount_ratio,
                    ftc.enabled,
                    ftc.created_at
                FROM forward_trade_configs ftc
                WHERE ftc.user_id = %s
                ORDER BY ftc.created_at DESC
                LIMIT 10
            """
            configs = db_pool.query(sql, (user_id,))
            
            # 查询用户已配置的 API
            api_sql = """
                SELECT exchange, customer_uid
                FROM customers
                WHERE customer_uid = %s AND enabled = 1
            """
            apis = db_pool.query(api_sql, (customer_uid,)) if customer_uid else []
            has_api = len(apis) > 0
            
            config_text = f"""📈 *转发交易配置*

💡 *说明*:
转发交易功能会根据您订阅的 TradingView 信号自动执行交易。

📋 *当前配置*:"""
            
            if configs:
                for cfg in configs:
                    status = "✅ 已启用" if cfg.get('enabled') else "❌ 已禁用"
                    config_text += f"\n• {cfg.get('config_name')} - {status}"
            else:
                config_text += "\n• 暂无配置"
            
            config_text += f"\n\n🔑 *API 配置状态*:"
            if has_api:
                exchanges = [api.get('exchange', '').upper() for api in apis]
                config_text += f"\n• 已配置: {', '.join(exchanges)}"
            else:
                config_text += "\n• ❌ 未配置 API"
                config_text += "\n\n⚠️ 请先在「我的」菜单中配置交易所 API"
            
            config_text += "\n\n💡 *提示*:"
            config_text += "\n配置 API 后，系统会自动使用您的 API 执行交易。"
            
            from core.message_forward.telegram_bot.keyboard_builder import KeyboardBuilder
            keyboard = []
            
            # 如果有配置，显示管理选项
            if configs:
                for cfg in configs:
                    config_id = cfg.get('id')
                    enabled = cfg.get('enabled')
                    toggle_text = "❌ 禁用" if enabled else "✅ 启用"
                    keyboard.append([
                        InlineKeyboardButton(
                            f"{toggle_text} {cfg.get('config_name')}",
                            callback_data=f"toggle_forward_trade:{config_id}"
                        )
                    ])
            
            # 如果有 API 配置，显示创建按钮
            if has_api:
                keyboard.append([InlineKeyboardButton("➕ 创建新配置", callback_data="create_forward_trade_config")])
            
            keyboard.append([InlineKeyboardButton("🔙 返回", callback_data="my_account_menu")])
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await update.callback_query.edit_message_text(
                config_text,
                reply_markup=reply_markup,
                parse_mode=ParseMode.MARKDOWN
            )
            await update.callback_query.answer()
            
        except Exception as e:
            logger.error(f"查询转发交易配置失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
            await update.callback_query.answer("查询配置失败", show_alert=True)
    
    async def handle_create_forward_trade_config(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """开始创建转发交易配置"""
        user = update.effective_user
        user_service = self.get_user_service()
        
        if not user_service:
            await update.callback_query.answer("❌ 用户服务不可用", show_alert=True)
            return
        
        platform_user = user_service.get_user_by_telegram_id(user.id)
        if not platform_user:
            await update.callback_query.answer("❌ 请先绑定账号", show_alert=True)
            return
        
        db_pool = self.get_db_pool()
        if not db_pool:
            await update.callback_query.answer("❌ 数据库连接不可用", show_alert=True)
            return
        
        user_id = platform_user['user_id']
        customer_uid = platform_user.get('customer_uid')
        
        # 查询可用的 TradingView 平台
        try:
            tv_platforms_sql = """
                SELECT id, platform_name, config
                FROM message_platforms
                WHERE platform_type = 'tradingview' AND enabled = 1
                ORDER BY id DESC
            """
            tv_platforms = db_pool.query(tv_platforms_sql)
            
            if not tv_platforms:
                await update.callback_query.answer("❌ 没有可用的 TradingView 平台", show_alert=True)
                return
            
            # 查询用户已配置的 API
            api_sql = """
                SELECT exchange, customer_uid, name
                FROM customers
                WHERE customer_uid = %s AND enabled = 1
            """
            apis = db_pool.query(api_sql, (customer_uid,)) if customer_uid else []
            
            if not apis:
                await update.callback_query.answer("❌ 请先配置交易所 API", show_alert=True)
                return
            
            # 显示选择 TradingView 平台
            text = """📈 *创建转发交易配置*

请选择要订阅的 TradingView 信号源："""
            
            keyboard = []
            for platform in tv_platforms:
                platform_id = platform.get('id')
                platform_name = platform.get('platform_name', f'TradingView #{platform_id}')
                keyboard.append([
                    InlineKeyboardButton(
                        platform_name,
                        callback_data=f"select_tradingview_platform:{platform_id}"
                    )
                ])
            keyboard.append([InlineKeyboardButton("🔙 返回", callback_data="forward_trade_config")])
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await update.callback_query.edit_message_text(
                text,
                reply_markup=reply_markup,
                parse_mode=ParseMode.MARKDOWN
            )
            await update.callback_query.answer()
            
        except Exception as e:
            logger.error(f"查询 TradingView 平台失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
            await update.callback_query.answer("查询失败", show_alert=True)
    
    async def handle_select_tradingview_platform_for_trade(self, update: Update, context: ContextTypes.DEFAULT_TYPE, platform_id: int):
        """选择 TradingView 平台后，选择交易所"""
        user = update.effective_user
        user_service = self.get_user_service()
        
        if not user_service:
            await update.callback_query.answer("❌ 用户服务不可用", show_alert=True)
            return
        
        platform_user = user_service.get_user_by_telegram_id(user.id)
        if not platform_user:
            await update.callback_query.answer("❌ 请先绑定账号", show_alert=True)
            return
        
        db_pool = self.get_db_pool()
        if not db_pool:
            await update.callback_query.answer("❌ 数据库连接不可用", show_alert=True)
            return
        
        user_id = platform_user['user_id']
        customer_uid = platform_user.get('customer_uid')
        
        try:
            # 获取平台信息
            platform_sql = """
                SELECT id, platform_name
                FROM message_platforms
                WHERE id = %s AND platform_type = 'tradingview'
            """
            platform_rows = db_pool.query(platform_sql, (platform_id,))
            if not platform_rows:
                await update.callback_query.answer("❌ 平台不存在", show_alert=True)
                return
            
            platform_name = platform_rows[0].get('platform_name', f'TradingView #{platform_id}')
            
            # 查询用户已配置的 API
            api_sql = """
                SELECT exchange, customer_uid, name
                FROM customers
                WHERE customer_uid = %s AND enabled = 1
            """
            apis = db_pool.query(api_sql, (customer_uid,)) if customer_uid else []
            
            if not apis:
                await update.callback_query.answer("❌ 请先配置交易所 API", show_alert=True)
                return
            
            # 保存选择的平台到会话状态
            from core.message_forward.telegram_bot.state_manager import StateManager
            state_manager = StateManager(db_pool)
            state_manager.update_session(
                user.id,
                current_state='create_forward_trade_config',
                context_data={
                    'source_platform_id': platform_id,
                    'source_platform_name': platform_name
                }
            )
            
            # 显示选择交易所
            text = f"""📈 *创建转发交易配置*

✅ 已选择信号源: {platform_name}

请选择要使用的交易所账户："""
            
            keyboard = []
            for api in apis:
                exchange = api.get('exchange', '').upper()
                account_name = api.get('name', f'{exchange} 账户')
                keyboard.append([
                    InlineKeyboardButton(
                        f"{exchange} - {account_name}",
                        callback_data=f"select_exchange_for_trade:{api.get('exchange')}"
                    )
                ])
            keyboard.append([InlineKeyboardButton("🔙 返回", callback_data="create_forward_trade_config")])
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await update.callback_query.edit_message_text(
                text,
                reply_markup=reply_markup,
                parse_mode=ParseMode.MARKDOWN
            )
            await update.callback_query.answer()
            
        except Exception as e:
            logger.error(f"选择 TradingView 平台失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
            await update.callback_query.answer("操作失败", show_alert=True)
    
    async def handle_select_exchange_for_trade(self, update: Update, context: ContextTypes.DEFAULT_TYPE, exchange: str):
        """选择交易所后，输入配置名称"""
        user = update.effective_user
        user_service = self.get_user_service()
        
        if not user_service:
            await update.callback_query.answer("❌ 用户服务不可用", show_alert=True)
            return
        
        platform_user = user_service.get_user_by_telegram_id(user.id)
        if not platform_user:
            await update.callback_query.answer("❌ 请先绑定账号", show_alert=True)
            return
        
        db_pool = self.get_db_pool()
        if not db_pool:
            await update.callback_query.answer("❌ 数据库连接不可用", show_alert=True)
            return
        
        user_id = platform_user['user_id']
        
        try:
            # 从 customers 表查询该用户的交易所账户信息
            # 注意：需要根据 user_id 或 owner_user_id 查询，而不是使用 platform_user 中的 customer_uid
            # 使用 COLLATE 确保大小写不敏感匹配
            api_sql = """
                SELECT exchange, customer_uid, name
                FROM customers
                WHERE (user_id = %s OR owner_user_id = %s)
                AND exchange = %s
                AND enabled = 1
                LIMIT 1
            """
            api_rows = db_pool.query(api_sql, (user_id, user_id, exchange))
            if not api_rows:
                # 添加调试日志
                logger.warning(f"用户 {user_id} 未找到交易所 {exchange} 的配置。查询条件: user_id={user_id}, owner_user_id={user_id}, exchange={exchange}")
                # 检查是否有其他交易所的配置
                check_all_sql = """
                    SELECT exchange, customer_uid, name
                    FROM customers
                    WHERE (user_id = %s OR owner_user_id = %s) AND enabled = 1
                """
                all_configs = db_pool.query(check_all_sql, (user_id, user_id))
                if all_configs:
                    available_exchanges = [row.get('exchange') for row in all_configs]
                    logger.info(f"用户 {user_id} 已配置的交易所: {available_exchanges}")
                await update.callback_query.answer("❌ 该交易所 API 未配置，请先配置交易所 API", show_alert=True)
                return
            
            customer_uid = api_rows[0].get('customer_uid')
            customer_name = api_rows[0].get('name', f'{exchange.upper()} 账户')
            
            if not customer_uid:
                await update.callback_query.answer("❌ 无法获取客户账户信息", show_alert=True)
                return
            
            # 确保 customer_uid 是字符串类型，并去除可能的空白字符
            customer_uid = str(customer_uid).strip()
            logger.info(f"选择交易所 {exchange}，customer_uid={customer_uid!r}, customer_name={customer_name}")
            
            # 更新会话状态
            from core.message_forward.telegram_bot.state_manager import StateManager
            state_manager = StateManager(db_pool)
            session = state_manager.get_session(user.id)
            context_data = session.get('context_data', {})
            context_data['exchange'] = exchange
            context_data['customer_uid'] = customer_uid  # 使用清理后的值
            context_data['customer_name'] = customer_name
            
            state_manager.update_session(
                user.id,
                current_state='create_forward_trade_config_name',
                context_data=context_data
            )
            
            # 提示输入配置名称
            text = f"""📈 *创建转发交易配置*

✅ 已选择交易所: {exchange.upper()} - {customer_name}

📝 请输入配置名称（用于标识此配置）："""
            
            keyboard = [
                [InlineKeyboardButton("🔙 返回", callback_data="create_forward_trade_config")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await update.callback_query.edit_message_text(
                text,
                reply_markup=reply_markup,
                parse_mode=ParseMode.MARKDOWN
            )
            await update.callback_query.answer()
            
        except Exception as e:
            logger.error(f"选择交易所失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
            await update.callback_query.answer("操作失败", show_alert=True)
    
    async def handle_confirm_create_forward_trade(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """确认创建转发交易配置"""
        user = update.effective_user
        user_service = self.get_user_service()
        
        if not user_service:
            await update.callback_query.answer("❌ 用户服务不可用", show_alert=True)
            return
        
        platform_user = user_service.get_user_by_telegram_id(user.id)
        if not platform_user:
            await update.callback_query.answer("❌ 请先绑定账号", show_alert=True)
            return
        
        db_pool = self.get_db_pool()
        if not db_pool:
            await update.callback_query.answer("❌ 数据库连接不可用", show_alert=True)
            return
        
        user_id = platform_user['user_id']
        
        # 获取会话数据
        from core.message_forward.telegram_bot.state_manager import StateManager
        state_manager = StateManager(db_pool)
        session = state_manager.get_session(user.id)
        context_data = session.get('context_data', {})
        
        config_name = context_data.get('config_name')
        source_platform_id = context_data.get('source_platform_id')
        source_platform_name = context_data.get('source_platform_name')
        customer_uid = context_data.get('customer_uid')
        customer_name = context_data.get('customer_name')
        amount_ratio = context_data.get('amount_ratio', 1.0)
        
        # 清理 customer_uid（确保是字符串且去除空白）
        if customer_uid:
            customer_uid = str(customer_uid).strip()
        
        if not all([config_name, source_platform_id, customer_uid]):
            logger.warning(f"配置信息不完整: config_name={config_name}, source_platform_id={source_platform_id}, customer_uid={customer_uid!r}")
            await update.callback_query.answer("❌ 配置信息不完整", show_alert=True)
            return
        
        logger.info(f"准备创建转发交易配置: user_id={user_id}, customer_uid={customer_uid!r}, config_name={config_name}")
        
        try:
            # 检查配置名称是否已存在
            check_sql = """
                SELECT id FROM forward_trade_configs WHERE config_name = %s
            """
            existing = db_pool.query(check_sql, (config_name,))
            if existing:
                await update.callback_query.answer("❌ 配置名称已存在，请使用其他名称", show_alert=True)
                return
            
            # 验证 customer_uid 是否存在于 customers 表中
            check_customer_sql = """
                SELECT customer_uid, name, exchange, enabled
                FROM customers
                WHERE customer_uid = %s
            """
            customer_exists = db_pool.query(check_customer_sql, (customer_uid,))
            if not customer_exists:
                logger.error(f"客户 {customer_uid} 不存在于 customers 表中。用户ID: {user_id}")
                # 尝试查找该用户的所有 customers 记录
                debug_sql = """
                    SELECT customer_uid, name, exchange, enabled 
                    FROM customers 
                    WHERE (user_id = %s OR owner_user_id = %s)
                """
                all_customers = db_pool.query(debug_sql, (user_id, user_id))
                logger.error(f"用户 {user_id} 的所有 customers 记录: {all_customers}")
                await update.callback_query.answer("❌ 客户账户不存在，请先配置交易所 API", show_alert=True)
                return
            
            # 使用从数据库查询到的实际 customer_uid（确保字符编码和值完全一致）
            verified_customer_uid = customer_exists[0].get('customer_uid')
            verified_customer_name = customer_exists[0].get('name', customer_name)
            
            # 记录验证信息
            logger.info(f"验证 customer_uid: 会话中的={customer_uid!r}, 数据库中的={verified_customer_uid!r}, 是否匹配={customer_uid == verified_customer_uid}")
            
            # 如果值不匹配，使用数据库中的值
            if verified_customer_uid != customer_uid:
                logger.warning(f"customer_uid 值不匹配，使用数据库中的值: {verified_customer_uid}")
                customer_uid = verified_customer_uid
                customer_name = verified_customer_name
            
            # 插入配置（使用验证后的 customer_uid）
            # 排序规则已统一为 utf8mb4_general_ci，直接使用已验证的 customer_uid
            # 同时确保 amount_ratio 是 Decimal 类型
            from decimal import Decimal
            amount_ratio_decimal = Decimal(str(amount_ratio)).quantize(Decimal('0.0001'))
            
            # 使用已验证的 customer_uid（从数据库查询得到的值，确保完全匹配）
            insert_sql = """
                INSERT INTO forward_trade_configs
                (config_name, user_id, source_platform_id, source_platform_name,
                 customer_uid, customer_name, amount_ratio, enabled, created_by_user_id)
                VALUES (%s, %s, %s, %s, %s, %s, %s, 1, %s)
            """
            logger.info(f"准备插入转发交易配置: customer_uid={verified_customer_uid!r}, user_id={user_id}, config_name={config_name}, amount_ratio={amount_ratio_decimal}")
            logger.info(f"customer_uid 类型: {type(verified_customer_uid)}, 值: {repr(verified_customer_uid)}")
            db_pool.execute(insert_sql, (
                config_name, user_id, source_platform_id, source_platform_name,
                verified_customer_uid, customer_name, amount_ratio_decimal, user_id
            ))
            
            # 清除会话状态
            state_manager.update_session(user.id, current_state='main_menu', context_data={})
            
            success_text = f"""✅ *转发交易配置创建成功！*

📋 *配置信息*:
• 配置名称: `{config_name}`
• 信号源: {source_platform_name}
• 交易所: {customer_name}
• 金额比例: {amount_ratio * 100:.2f}%

💡 配置已启用，系统将自动使用您的 API 执行交易。"""
            
            keyboard = [
                [InlineKeyboardButton("📈 查看配置", callback_data="forward_trade_config")],
                [InlineKeyboardButton("🔙 返回主菜单", callback_data="back_to_main")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await update.callback_query.edit_message_text(
                success_text,
                reply_markup=reply_markup,
                parse_mode=ParseMode.MARKDOWN
            )
            await update.callback_query.answer("✅ 配置已创建", show_alert=True)
            
        except Exception as e:
            logger.error(f"创建转发交易配置失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
            
            # 如果是外键约束错误，提供更详细的错误信息和调试
            error_msg = str(e)
            if "foreign key constraint" in error_msg.lower() or "1452" in error_msg:
                logger.error(f"外键约束错误详情: customer_uid={customer_uid!r}, user_id={user_id}, config_name={config_name}")
                
                # 再次检查 customer_uid 是否存在（使用多种方式）
                final_check_sql1 = """
                    SELECT customer_uid, name, exchange, enabled 
                    FROM customers 
                    WHERE customer_uid = %s
                """
                final_check1 = db_pool.query(final_check_sql1, (customer_uid,))
                
                # 也检查该用户的所有 customers
                final_check_sql2 = """
                    SELECT customer_uid, name, exchange, enabled 
                    FROM customers 
                    WHERE (user_id = %s OR owner_user_id = %s) AND enabled = 1
                """
                final_check2 = db_pool.query(final_check_sql2, (user_id, user_id))
                
                logger.error(f"最终验证1 (精确匹配): {final_check1}")
                logger.error(f"最终验证2 (用户所有记录): {final_check2}")
                
                if not final_check1:
                    logger.error(f"customer_uid={customer_uid!r} 确实不存在于 customers 表中")
                    await update.callback_query.answer("❌ 客户账户不存在，请重新选择交易所", show_alert=True)
                else:
                    logger.error(f"验证成功但插入失败，可能是字符编码或数据库约束问题")
                    await update.callback_query.answer("❌ 创建失败，请稍后重试或联系管理员", show_alert=True)
            else:
                await update.callback_query.answer("创建失败，请稍后重试", show_alert=True)
    
    async def handle_toggle_forward_trade_config(self, update: Update, context: ContextTypes.DEFAULT_TYPE, config_id: int):
        """切换转发交易配置的启用状态"""
        user = update.effective_user
        user_service = self.get_user_service()
        
        if not user_service:
            await update.callback_query.answer("❌ 用户服务不可用", show_alert=True)
            return
        
        platform_user = user_service.get_user_by_telegram_id(user.id)
        if not platform_user:
            await update.callback_query.answer("❌ 请先绑定账号", show_alert=True)
            return
        
        db_pool = self.get_db_pool()
        if not db_pool:
            await update.callback_query.answer("❌ 数据库连接不可用", show_alert=True)
            return
        
        user_id = platform_user['user_id']
        
        try:
            # 检查配置是否属于当前用户
            check_sql = """
                SELECT id, enabled, config_name
                FROM forward_trade_configs
                WHERE id = %s AND user_id = %s
            """
            config_rows = db_pool.query(check_sql, (config_id, user_id))
            if not config_rows:
                await update.callback_query.answer("❌ 配置不存在或无权限", show_alert=True)
                return
            
            current_enabled = config_rows[0].get('enabled')
            new_enabled = 0 if current_enabled else 1
            config_name = config_rows[0].get('config_name')
            
            # 更新配置
            update_sql = """
                UPDATE forward_trade_configs
                SET enabled = %s, updated_at = NOW()
                WHERE id = %s AND user_id = %s
            """
            db_pool.execute(update_sql, (new_enabled, config_id, user_id))
            
            status_text = "已启用" if new_enabled else "已禁用"
            await update.callback_query.answer(f"✅ 配置 {config_name} {status_text}", show_alert=True)
            
            # 刷新配置列表
            await self.handle_forward_trade_config(update, context)
            
        except Exception as e:
            logger.error(f"切换转发交易配置状态失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
            await update.callback_query.answer("操作失败", show_alert=True)
    
    async def handle_input_username(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """处理输入用户名"""
        from core.message_forward.telegram_bot.state_manager import StateManager
        
        user_id = update.effective_user.id
        state_manager = StateManager(self.get_db_pool())
        
        # 设置状态为等待输入用户名
        state_manager.update_session(
            user_id,
            current_state='configure_account',
            context_data={'step': 'username'}
        )
        
        text = """📝 *修改用户名*

请输入新的用户名："""
        
        await update.callback_query.edit_message_text(
            text,
            parse_mode=ParseMode.MARKDOWN
        )
        await update.callback_query.answer()
    
    async def handle_input_password(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """处理输入密码"""
        from core.message_forward.telegram_bot.state_manager import StateManager
        
        user_id = update.effective_user.id
        state_manager = StateManager(self.get_db_pool())
        
        # 设置状态为等待输入密码
        state_manager.update_session(
            user_id,
            current_state='configure_account',
            context_data={'step': 'password'}
        )
        
        text = """🔒 *修改密码*

请输入新密码："""
        
        await update.callback_query.edit_message_text(
            text,
            parse_mode=ParseMode.MARKDOWN
        )
        await update.callback_query.answer()
    
    # ==================== 辅助方法 ====================
    
    def get_db_pool(self):
        """获取数据库连接池（带多重回退）"""
        # 方法1: 从消息管理器获取数据库连接池
        if hasattr(self, 'message_manager') and self.message_manager:
            # 尝试从 _db 获取
            if hasattr(self.message_manager, '_db') and self.message_manager._db:
                db = self.message_manager._db
                if hasattr(db, 'db_pool') and db.db_pool:
                    return db.db_pool
                elif hasattr(db, '_db_pool') and db._db_pool:
                    return db._db_pool
                # 如果 _db 本身就是连接池（有 query 方法）
                elif hasattr(db, 'query'):
                    return db
        
        # 方法2: 从消息转发服务获取
        try:
            from core.message_forward.api_service import get_message_forward_service
            service = get_message_forward_service()
            if service and hasattr(service, 'db'):
                db = service.db
                if hasattr(db, '_db_pool') and db._db_pool:
                    return db._db_pool
                elif hasattr(db, 'db_pool') and db.db_pool:
                    return db.db_pool
                elif hasattr(db, 'query'):
                    return db
        except Exception as e:
            logger.debug(f"从消息转发服务获取数据库连接池失败: {e}")
        
        # 方法3: 从全局数据库管理器获取
        try:
            from database.global_db_manager import get_global_db_pool
            db_pool = get_global_db_pool()
            if db_pool:
                return db_pool
        except Exception as e:
            logger.debug(f"从全局数据库管理器获取数据库连接池失败: {e}")
        
        # 方法4: 从 api_server 获取
        try:
            from api.api_server import get_db_pool as api_get_db_pool
            db_pool = api_get_db_pool()
            if db_pool:
                return db_pool
        except Exception as e:
            logger.debug(f"从 api_server 获取数据库连接池失败: {e}")
        
        logger.error("❌ 无法获取数据库连接池，所有回退方法都失败了")
        return None
    
    def get_subscription_service(self):
        """获取订阅服务实例"""
        if not hasattr(self, '_subscription_service') or self._subscription_service is None:
            from core.message_forward.telegram_bot.subscription_service import TelegramSubscriptionService
            db_pool = self.get_db_pool()
            if db_pool:
                self._subscription_service = TelegramSubscriptionService(db_pool)
            else:
                return None
        return self._subscription_service
    
    def get_user_service(self):
        """获取用户服务实例"""
        if not hasattr(self, '_user_service') or self._user_service is None:
            from core.message_forward.telegram_bot.user_service import TelegramBotUserService
            db_pool = self.get_db_pool()
            if db_pool:
                self._user_service = TelegramBotUserService(db_pool)
            else:
                return None
        return self._user_service
    
    def get_exchange_api_service(self):
        """获取交易所 API 服务实例"""
        if not hasattr(self, '_exchange_api_service') or self._exchange_api_service is None:
            from core.message_forward.telegram_bot.exchange_api_service import ExchangeAPIService
            db_pool = self.get_db_pool()
            if db_pool:
                self._exchange_api_service = ExchangeAPIService(db_pool)
            else:
                return None
        return self._exchange_api_service
    
    def _get_platform_id(self) -> Optional[int]:
        """
        获取当前平台的数据库ID
        
        Returns:
            平台ID，如果不存在则返回None
        """
        # 首先尝试从配置中获取
        platform_id = self.config.get('platform_id')
        if platform_id:
            return int(platform_id)
        
        # 如果配置中没有，从数据库查询
        try:
            db_pool = self.get_db_pool()
            if not db_pool:
                logger.warning("数据库连接池不可用，无法查询平台ID")
                return None
            
            # 根据 bot_token 查询平台ID
            sql = """
                SELECT id FROM message_platforms 
                WHERE platform_type = 'telegram_bot' 
                AND config->>'$.bot_token' = %s
                AND enabled = 1
                LIMIT 1
            """
            rows = db_pool.query(sql, (self.bot_token,))
            if rows:
                platform_id = rows[0].get('id')
                # 缓存到配置中，避免重复查询
                self.config['platform_id'] = platform_id
                return platform_id
            
            logger.warning(f"未找到对应的平台记录（bot_token: {self.bot_token[:10]}...）")
            return None
        except Exception as e:
            logger.error(f"查询平台ID失败: {e}")
            return None
    
    def _get_or_create_default_rule(self, target_platform_id: int) -> str:
        """
        获取或创建默认转发规则（匹配所有 TradingView 平台）
        
        Args:
            target_platform_id: 目标平台ID（Telegram Bot）
        
        Returns:
            规则ID
        """
        try:
            db_pool = self.get_db_pool()
            if not db_pool:
                logger.warning("数据库连接不可用，无法创建默认规则")
                return str(uuid.uuid4())
            
            from core.message_forward.models import PlatformType
            import json
            
            # 查找是否已存在匹配所有 TradingView 的规则（source_platform_id 为 NULL）
            sql = """
                SELECT rule_id 
                FROM message_forward_rules 
                WHERE source_platform = 'tradingview' 
                AND source_platform_id IS NULL
                AND JSON_CONTAINS(target_platform_ids, %s)
                AND enabled = 1
                LIMIT 1
            """
            target_ids_json = json.dumps([target_platform_id])
            rows = db_pool.query(sql, (target_ids_json,))
            
            if rows:
                logger.info(f"✅ 找到现有默认规则: {rows[0]['rule_id']}")
                return rows[0]['rule_id']
            
            # 创建新规则（source_platform_id 为 NULL，匹配所有 TradingView 平台）
            rule_id = str(uuid.uuid4())
            rule_name = f"TradingView -> Telegram Bot (自动创建-匹配所有)"
            
            insert_sql = """
                INSERT INTO message_forward_rules 
                (rule_id, rule_name, enabled, source_platform, source_platform_id, 
                 target_platforms, target_platform_ids, target_chat_ids)
                VALUES (%s, %s, 1, 'tradingview', NULL, 
                        %s, %s, %s)
            """
            target_platforms_json = json.dumps(['telegram_bot'])
            target_platform_ids_json = json.dumps([target_platform_id])
            target_chat_ids_json = json.dumps({'telegram_bot': []})
            
            db_pool.execute(insert_sql, (
                rule_id, rule_name,
                target_platforms_json,
                target_platform_ids_json,
                target_chat_ids_json
            ))
            
            logger.info(f"✅ 已创建默认转发规则: {rule_id} (匹配所有 TradingView 平台)")
            return rule_id
            
        except Exception as e:
            logger.error(f"获取或创建默认规则失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
            # 返回一个随机 UUID 作为 fallback
            return str(uuid.uuid4())
    
    def add_message_handler(self, handler: Callable):
        """添加消息处理器"""
        self.message_handlers.append(handler)
    
    async def setup_webhook(self, force: bool = False):
        """
        设置 Webhook（生产环境推荐）
        
        Args:
            force: 是否强制设置（即使 webhook 已经设置过）
        """
        if not self.application or not self.webhook_url:
            return
        
        try:
            # 检查当前 webhook 信息
            webhook_info = await self.bot.get_webhook_info()
            
            # 如果 webhook 已经设置且 URL 匹配，且不强制设置，则跳过
            if not force and webhook_info.url and webhook_info.url == self.webhook_url:
                logger.info(f"✅ Webhook 已设置: {webhook_info.url}，跳过重复设置")
                return
            
            # 删除旧的 webhook（如果有）
            await self.bot.delete_webhook(drop_pending_updates=True)
            
            # 设置新的 webhook
            await self.bot.set_webhook(
                url=self.webhook_url,
                secret_token=self.webhook_secret if self.webhook_secret else None,
                drop_pending_updates=True
            )
            
            # 获取 webhook 信息验证
            webhook_info = await self.bot.get_webhook_info()
            logger.info(f"✅ Webhook 信息: URL={webhook_info.url}, 待处理更新数={webhook_info.pending_update_count}")
            
        except Exception as e:
            logger.error(f"❌ 设置 Webhook 失败: {e}")
            raise
    
    async def remove_webhook(self):
        """删除 Webhook（带超时）"""
        if not self.bot:
            return
        
        try:
            import asyncio
            # 设置超时，避免长时间阻塞
            await asyncio.wait_for(
                self.bot.delete_webhook(drop_pending_updates=True),
                timeout=5.0
            )
            logger.info("✅ Webhook 已删除")
        except asyncio.TimeoutError:
            logger.warning("⚠️ 删除 Webhook 超时（可能没有 webhook 或网络问题）")
        except Exception as e:
            logger.warning(f"⚠️ 删除 Webhook 失败（可能没有 webhook）: {e}")
    
    async def start_polling(self):
        """开始轮询（用于开发环境或 webhook 不可用时）"""
        if not self.application:
            logger.error("Application 未初始化")
            return
        
        # 如果已设置 webhook，先删除
        if self.webhook_url:
            await self.remove_webhook()
        
        logger.info("开始 Telegram Bot 轮询...")
        # 使用 run_polling() 方法，这是 python-telegram-bot 推荐的方式
        # 它会自动处理 initialize、start 和 polling
        await self.application.initialize()
        await self.application.start()
        await self.application.updater.start_polling()
        logger.info("✅ Telegram Bot 轮询已启动")
    
    def run_polling_blocking(self):
        """
        阻塞式运行轮询（用于在线程中运行）
        这是同步方法，内部会创建事件循环并运行
        使用线程锁确保只有一个实例在运行
        """
        if not self.application:
            logger.error("❌ Application 未初始化，无法启动轮询")
            return
        
        bot_token_key = self.bot_token[:10] if self.bot_token else 'unknown'
        
        # 获取锁，确保线程安全
        lock = self._get_polling_lock()
        
        # 尝试获取锁（非阻塞，如果已有实例在运行则直接返回）
        if not lock.acquire(blocking=False):
            logger.warning(f"⚠️ 无法获取轮询锁，可能已有实例正在启动 (Token: {bot_token_key}...)")
            return
        
        try:
            # 检查是否已有实例在运行
            if bot_token_key in TelegramBotPlatform._polling_instances:
                existing_instance = TelegramBotPlatform._polling_instances[bot_token_key]
                existing_thread = TelegramBotPlatform._polling_threads.get(bot_token_key)
                
                # 检查线程是否还在运行
                if existing_thread and existing_thread.is_alive():
                    logger.warning(f"⚠️ 检测到另一个 Bot 实例正在运行轮询 (Token: {bot_token_key}...)，线程: {existing_thread.name}，跳过重复启动")
                    return
                else:
                    # 线程已停止，清理旧记录
                    logger.info(f"清理已停止的轮询实例记录 (Token: {bot_token_key}...)")
                    TelegramBotPlatform._polling_instances.pop(bot_token_key, None)
                    TelegramBotPlatform._polling_threads.pop(bot_token_key, None)
            
            # 检查是否已经有轮询在运行（通过检查 updater 状态）
            if hasattr(self.application, 'updater') and self.application.updater.running:
                logger.warning("⚠️ 轮询已在运行，跳过重复启动")
                return
            
            # 注册当前实例和线程
            import threading
            import asyncio
            current_thread = threading.current_thread()
            TelegramBotPlatform._polling_instances[bot_token_key] = self
            TelegramBotPlatform._polling_threads[bot_token_key] = current_thread
            logger.info(f"✅ 已注册轮询实例 (Token: {bot_token_key}..., 线程: {current_thread.name})")
            
            # 创建并设置事件循环（这个循环将被 run_polling() 使用）
            # 清除当前线程可能存在的旧事件循环
            try:
                old_loop = asyncio.get_event_loop()
                if not old_loop.is_closed():
                    old_loop.close()
            except RuntimeError:
                pass  # 没有事件循环，继续
            
            # 创建新的事件循环（这个循环将被 run_polling() 使用）
            main_loop = asyncio.new_event_loop()
            asyncio.set_event_loop(main_loop)
            # 先删除 webhook（如果存在），确保不会冲突
            logger.info("🔍 检查并删除现有 webhook（如果存在）...")
            try:
                # 使用主循环删除 webhook
                main_loop.run_until_complete(self.remove_webhook())
                logger.info("✅ 已删除现有 webhook（如果存在）")
            except Exception as e:
                logger.warning(f"⚠️ 删除 webhook 时出错（可能没有 webhook）: {e}")
            
            # 确保 handlers 已设置
            if not self.application.handlers:
                logger.warning("⚠️ Application 没有 handlers，尝试重新设置...")
                try:
                    main_loop.run_until_complete(self.setup_handlers())
                    logger.info("✅ Handlers 已重新设置")
                except Exception as e:
                    logger.error(f"❌ 设置 handlers 失败: {e}")
                    import traceback
                    logger.error(traceback.format_exc())
                    # 清理注册
                    TelegramBotPlatform._polling_instances.pop(bot_token_key, None)
                    TelegramBotPlatform._polling_threads.pop(bot_token_key, None)
                    return
            else:
                logger.info(f"✅ Application 已有 handlers")
            
            logger.info("=" * 60)
            logger.info("🚀 开始 Telegram Bot 轮询（阻塞模式）...")
            logger.info(f"📋 Bot Token: {bot_token_key}... (已脱敏)")
            logger.info(f"📋 Application 状态: connected={self.connected}, enabled={self.enabled}")
            logger.info(f"📋 事件循环: {main_loop} (ID: {id(main_loop)})")
            logger.info("=" * 60)
            
            # 使用 application.run_polling() 阻塞式运行
            # 注意：run_polling() 内部会使用当前线程的事件循环（main_loop）
            # 它会自动管理事件循环的生命周期，包括启动和关闭
            try:
                logger.info("📡 调用 application.run_polling()...")
                # run_polling() 会使用当前线程的事件循环（main_loop）
                # 它会自动处理 initialize、start、polling 和 shutdown
                self.application.run_polling(
                    drop_pending_updates=True,
                    stop_signals=None,  # 不处理信号，让线程管理生命周期
                    close_loop=False  # 不要关闭事件循环，我们会在 finally 中处理
                )
                logger.info("✅ Telegram Bot 轮询已启动（阻塞模式）")
            except Exception as polling_error:
                logger.error(f"❌ run_polling() 执行出错: {polling_error}")
                import traceback
                logger.error(traceback.format_exc())
                raise
        except KeyboardInterrupt:
            logger.info("收到停止信号，正在停止轮询...")
        except Exception as e:
            logger.error(f"❌ 轮询运行出错: {e}")
            import traceback
            logger.error(traceback.format_exc())
        finally:
            # 清理注册（在 finally 中确保一定会执行）
            TelegramBotPlatform._polling_instances.pop(bot_token_key, None)
            TelegramBotPlatform._polling_threads.pop(bot_token_key, None)
            logger.info(f"✅ 已从轮询注册表中移除 (Token: {bot_token_key}...)")
            
            # 释放锁
            lock.release()
            logger.info(f"✅ 已释放轮询锁 (Token: {bot_token_key}...)")
            
            # 清理事件循环
            # 清理事件循环
            try:
                if 'main_loop' in locals() and main_loop and not main_loop.is_closed():
                    # 尝试取消所有待处理的任务
                    try:
                        pending = asyncio.all_tasks(main_loop)
                        if pending:
                            logger.info(f"清理 {len(pending)} 个待处理任务...")
                            for task in pending:
                                task.cancel()
                            # 等待任务完成（或取消），但设置超时避免无限等待
                            try:
                                main_loop.run_until_complete(
                                    asyncio.wait_for(
                                        asyncio.gather(*pending, return_exceptions=True),
                                        timeout=5.0
                                    )
                                )
                            except asyncio.TimeoutError:
                                logger.warning("⚠️ 清理任务超时，强制关闭事件循环")
                    except RuntimeError as e:
                        # 事件循环可能已经关闭或正在关闭
                        logger.debug(f"清理任务时出错（可能事件循环已关闭）: {e}")
                    
                    # 关闭事件循环
                    try:
                        main_loop.close()
                        logger.info("✅ 事件循环已关闭")
                    except RuntimeError as e:
                        logger.debug(f"关闭事件循环时出错（可能已经关闭）: {e}")
            except Exception as e:
                logger.warning(f"⚠️ 清理事件循环时出错: {e}")
            finally:
                # 清除事件循环引用
                try:
                    asyncio.set_event_loop(None)
                except Exception:
                    pass
    
    async def stop_polling(self):
        """停止轮询"""
        if not self.application:
            return
        
        logger.info("停止 Telegram Bot 轮询...")
        await self.application.updater.stop()
        await self.application.stop()
        await self.application.shutdown()
        logger.info("✅ Telegram Bot 轮询已停止")
    
    def process_webhook_update(self, update_dict: dict):
        """
        处理 Webhook 更新（同步方法，用于 Flask 路由）
        
        Args:
            update_dict: Telegram 更新字典
        """
        if not self.application:
            logger.error("Application 未初始化")
            return
        
        try:
            from telegram import Update
            update = Update.de_json(update_dict, self.bot)
            
            # 在 gevent 环境中，使用 run_async_safe 或直接创建新的事件循环
            import asyncio
            import threading
            
            # 检查是否在 gevent 环境中
            try:
                import gevent
                in_gevent = True
            except ImportError:
                in_gevent = False
            
            if in_gevent:
                # 在 gevent 环境中，使用线程运行异步代码
                def run_async():
                    try:
                        loop = asyncio.new_event_loop()
                        asyncio.set_event_loop(loop)
                        loop.run_until_complete(self.application.process_update(update))
                        loop.close()
                    except Exception as e:
                        logger.error(f"处理 Webhook 更新失败: {e}")
                        import traceback
                        logger.error(traceback.format_exc())
                
                thread = threading.Thread(target=run_async, daemon=True)
                thread.start()
            else:
                # 在普通环境中，直接运行
                try:
                    loop = asyncio.get_event_loop()
                except RuntimeError:
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                
                # 如果事件循环正在运行，使用 create_task
                if loop.is_running():
                    loop.create_task(self.application.process_update(update))
                else:
                    loop.run_until_complete(self.application.process_update(update))
            
        except Exception as e:
            logger.error(f"❌ 处理 Webhook 更新失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
    
    async def listen(self, callback: Callable[[Message], None]) -> None:
        """
        监听 Telegram Bot 消息
        
        Args:
            callback: 收到消息时的回调函数
        
        Note:
            Telegram Bot 通过 webhook 或 polling 接收消息，此方法主要用于添加消息处理器
        """
        self.add_message_handler(callback)
        logger.info("Telegram Bot 消息监听已启动")
    
    async def get_chat_info(self, chat_id: str) -> Optional[Dict[str, Any]]:
        """
        获取 Telegram 聊天信息
        
        Args:
            chat_id: 聊天ID（用户ID或群组ID）
        
        Returns:
            聊天信息字典
        """
        if not self.bot:
            logger.warning("Bot 未初始化，无法获取聊天信息")
            return None
        
        try:
            chat_id_int = int(chat_id)
            chat = await self.bot.get_chat(chat_id_int)
            
            return {
                'id': str(chat.id),
                'type': chat.type,
                'title': getattr(chat, 'title', None) or getattr(chat, 'first_name', None) or getattr(chat, 'username', None) or 'Unknown',
                'username': getattr(chat, 'username', None),
                'description': getattr(chat, 'description', None),
                'extra_data': {
                    'is_bot': getattr(chat, 'is_bot', False),
                    'first_name': getattr(chat, 'first_name', None),
                    'last_name': getattr(chat, 'last_name', None),
                }
            }
        except Exception as e:
            logger.error(f"获取 Telegram 聊天信息失败: {e}")
            # 返回基本信息
            return {
                'id': chat_id,
                'type': 'private',
                'title': f'Chat {chat_id}',
                'username': None,
                'description': None,
                'extra_data': {}
            }

