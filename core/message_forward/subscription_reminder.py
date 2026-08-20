"""
订阅到期提醒服务
在订阅到期前3天，每天发送提醒消息
"""

import asyncio
import threading
from typing import Dict, Any, List
from datetime import datetime, timedelta
from utils.logger import get_logger

logger = get_logger(__name__)


class SubscriptionReminderService:
    """订阅到期提醒服务"""
    
    def __init__(self, db, forward_manager=None):
        """
        初始化提醒服务
        
        Args:
            db: 数据库操作实例
            forward_manager: 消息转发管理器（用于发送提醒消息）
        """
        self.db = db
        self.forward_manager = forward_manager
        self.running = False
        self.reminder_task = None
        self._last_reminder_date = {}  # 记录每个订阅最后提醒的日期，避免同一天重复提醒
    
    def start(self):
        """启动提醒服务"""
        if self.running:
            logger.warning("订阅提醒服务已在运行")
            return
        
        self.running = True
        self.reminder_task = threading.Thread(target=self._run_reminder_loop, daemon=True)
        self.reminder_task.start()
        logger.info("✅ 订阅到期提醒服务已启动")
    
    def stop(self):
        """停止提醒服务"""
        self.running = False
        if self.reminder_task:
            self.reminder_task.join(timeout=5)
        logger.info("订阅到期提醒服务已停止")
    
    def _run_reminder_loop(self):
        """运行提醒循环"""
        import time
        
        while self.running:
            try:
                # 检查即将到期的订阅
                self._check_and_send_reminders()
                
                # 每24小时检查一次（每天检查一次）
                time.sleep(3600)  # 1小时检查一次，确保不会错过
            except Exception as e:
                logger.error(f"订阅提醒服务运行异常: {e}")
                import traceback
                logger.error(traceback.format_exc())
                time.sleep(3600)  # 出错后等待1小时再重试
    
    def _check_and_send_reminders(self):
        """检查并发送提醒"""
        try:
            from core.message_forward.invitation_service import SubscriptionService
            subscription_service = SubscriptionService(self.db)
            
            # 获取数据库连接池
            db_pool = None
            if hasattr(self.db, 'db_pool'):
                db_pool = self.db.db_pool
            elif hasattr(self.db, '_db_pool'):
                db_pool = self.db._db_pool
            
            if not db_pool:
                logger.error("无法获取数据库连接池")
                return
            
            # 获取所有活跃的订阅（即将在3天内到期）
            sql = """
                SELECT * FROM forward_rule_subscriptions 
                WHERE subscription_status = 'active'
                AND expire_date > NOW()
                AND expire_date <= NOW() + INTERVAL '3 day'
                ORDER BY expire_date ASC
            """
            subscriptions = db_pool.query(sql)
            
            if not subscriptions:
                return
            
            today = datetime.now().date()
            
            for sub in subscriptions:
                try:
                    expire_date = sub.get('expire_date')
                    if isinstance(expire_date, str):
                        expire_date = datetime.fromisoformat(expire_date.replace('Z', '+00:00'))
                    elif expire_date is None:
                        continue
                    
                    expire_date_only = expire_date.date() if hasattr(expire_date, 'date') else expire_date
                    
                    # 计算剩余天数
                    days_left = (expire_date_only - today).days
                    
                    # 只处理前3天的订阅（3天、2天、1天）
                    if days_left < 1 or days_left > 3:
                        continue
                    
                    # 检查今天是否已经提醒过（避免重复提醒）
                    sub_key = f"{sub['rule_id']}_{sub['target_platform_id']}_{sub['target_chat_id']}"
                    last_reminder = self._last_reminder_date.get(sub_key)
                    if last_reminder == today:
                        continue
                    
                    # 发送提醒
                    self._send_reminder(sub, days_left)
                    
                    # 记录今天已提醒
                    self._last_reminder_date[sub_key] = today
                    
                except Exception as e:
                    logger.error(f"处理订阅提醒失败: {e}")
                    import traceback
                    logger.error(traceback.format_exc())
                    
        except Exception as e:
            logger.error(f"检查订阅提醒失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
    
    def _send_reminder(self, subscription: Dict[str, Any], days_left: int):
        """
        发送提醒消息
        
        Args:
            subscription: 订阅信息
            days_left: 剩余天数
        """
        try:
            if not self.forward_manager:
                logger.warning("消息转发管理器未初始化，无法发送提醒")
                return
            
            rule_id = subscription['rule_id']
            target_platform_id = subscription['target_platform_id']
            target_chat_id = subscription['target_chat_id']
            expire_date = subscription.get('expire_date')
            
            # 格式化过期时间
            if isinstance(expire_date, str):
                expire_date = datetime.fromisoformat(expire_date.replace('Z', '+00:00'))
            
            expire_str = expire_date.strftime('%Y-%m-%d %H:%M:%S') if hasattr(expire_date, 'strftime') else str(expire_date)
            
            # 构建提醒消息（Markdown 格式，优化显示效果）
            message_content = f"### ⚠️ 订阅即将到期提醒\n\n"
            message_content += f"📅 **剩余天数：** {days_left} 天\n\n"
            message_content += f"⏰ **到期时间：** `{expire_str}`\n\n"
            message_content += f"---\n\n"
            message_content += f"💡 如需继续使用，请联系客服获取更多订阅。"
            
            # 获取数据库连接池
            db_pool = None
            if hasattr(self.db, 'db_pool'):
                db_pool = self.db.db_pool
            elif hasattr(self.db, '_db_pool'):
                db_pool = self.db._db_pool
            
            if not db_pool:
                logger.error("无法获取数据库连接池")
                return
            
            # 查询平台信息
            platform_sql = "SELECT * FROM message_platforms WHERE id = %s"
            platform_rows = db_pool.query(platform_sql, (target_platform_id,))
            if not platform_rows:
                logger.warning(f"平台 {target_platform_id} 不存在，无法发送提醒")
                return
            
            platform_data = dict(platform_rows[0])
            # 解析JSON字段
            if platform_data.get('config'):
                try:
                    import json
                    platform_data['config'] = json.loads(platform_data['config'])
                except:
                    pass
            
            platform_type_str = platform_data.get('platform_type', '').lower()
            
            try:
                from .models import PlatformType, Message, MessageType
                from .platforms import create_platform_instance
                import aiohttp
                
                platform_type = PlatformType(platform_type_str)
                
                # 尝试从 forward_manager 获取平台实例
                platform_instance = None
                if self.forward_manager and platform_type in self.forward_manager.platforms:
                    platform_instance = self.forward_manager.platforms[platform_type]
                    logger.debug(f"从 forward_manager 获取平台实例: {platform_type_str}")
                else:
                    # 如果 forward_manager 中没有，则根据平台数据动态创建实例
                    logger.debug(f"forward_manager 中没有 {platform_type_str} 平台实例，尝试动态创建")
                    try:
                        # create_platform_instance 需要 platform_type 和 config 参数
                        platform_instance = create_platform_instance(
                            platform_type=platform_data.get('platform_type'),
                            config=platform_data.get('config', {})
                        )
                        if platform_instance:
                            # 尝试连接（对于需要连接的平台）
                            import asyncio
                            try:
                                loop = asyncio.get_event_loop()
                            except RuntimeError:
                                loop = asyncio.new_event_loop()
                                asyncio.set_event_loop(loop)
                            
                            # 对于 Webhook 类型平台（如 DingTalk），不需要连接，直接发送
                            webhook_platforms = ['dingtalk', 'tradingview', 'wechat_official', 'bicoin', 'coinglass']
                            if platform_type_str not in webhook_platforms:
                                # 非 Webhook 平台需要先连接
                                connected = loop.run_until_complete(platform_instance.connect())
                                if not connected:
                                    logger.warning(f"平台 {platform_type_str} 连接失败")
                                    return
                            else:
                                # Webhook 平台：设置 connected 为 True，确保可以发送消息
                                # 对于 DingTalk，需要确保 session 已创建
                                if hasattr(platform_instance, 'connected'):
                                    platform_instance.connected = True
                                # 确保 session 存在（DingTalk 需要）
                                if hasattr(platform_instance, 'session') and platform_instance.session is None:
                                    try:
                                        platform_instance.session = aiohttp.ClientSession()
                                    except:
                                        pass
                                logger.debug(f"Webhook 平台 {platform_type_str} 已就绪，无需连接")
                            logger.debug(f"动态创建平台实例成功: {platform_type_str}")
                    except Exception as e:
                        logger.error(f"动态创建平台实例失败: {e}")
                        import traceback
                        logger.error(traceback.format_exc())
                        return
                
                if not platform_instance:
                    logger.warning(f"无法获取或创建平台实例: {platform_type_str}")
                    return
                
                # 创建消息对象（使用 Markdown 格式）
                reminder_message = Message(
                    content=message_content,
                    message_type=MessageType.MARKDOWN
                )
                
                # 发送消息（使用异步方式）
                import asyncio
                try:
                    loop = asyncio.get_event_loop()
                except RuntimeError:
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                
                try:
                    success = loop.run_until_complete(
                        platform_instance.send_message(str(target_chat_id), reminder_message)
                    )
                    
                    if success:
                        logger.info(f"✅ 订阅到期提醒已发送: 规则ID={rule_id}, 平台ID={target_platform_id}, 群组={target_chat_id}, 剩余{days_left}天")
                    else:
                        logger.warning(f"⚠️ 发送订阅到期提醒失败: 规则ID={rule_id}, 平台ID={target_platform_id}, 群组={target_chat_id}")
                        # 记录更详细的错误信息
                        if hasattr(platform_instance, 'webhook_url'):
                            logger.warning(f"   钉钉 Webhook URL: {platform_instance.webhook_url[:50]}..." if platform_instance.webhook_url else "   钉钉 Webhook URL: 未配置")
                except Exception as send_error:
                    logger.error(f"发送提醒消息时发生异常: {send_error}")
                    import traceback
                    logger.error(traceback.format_exc())
                    logger.warning(f"⚠️ 发送订阅到期提醒失败: 规则ID={rule_id}, 平台ID={target_platform_id}, 群组={target_chat_id}, 错误: {send_error}")
                    
            except (ValueError, AttributeError) as e:
                logger.warning(f"无效的平台类型: {platform_type_str}, 错误: {e}")
            except Exception as e:
                logger.error(f"发送提醒消息失败: {e}")
                import traceback
                logger.error(traceback.format_exc())
                
        except Exception as e:
            logger.error(f"发送订阅提醒失败: {e}")
            import traceback
            logger.error(traceback.format_exc())

