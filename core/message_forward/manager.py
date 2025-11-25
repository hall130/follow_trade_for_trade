"""
消息转发管理器
统一管理所有消息平台和转发规则
"""

from typing import Dict, List, Optional, Any
import asyncio
import uuid

from .base import MessagePlatform
from .models import Message, ForwardRule, PlatformType
from .platforms import TelegramMTProtoPlatform, DingTalkPlatform, WeChatPlatform, BicoinPlatform, CoinGlassPlatform, TradingViewPlatform
from .platforms.wxauto_wechat import WxAutoWeChatPlatform
from .platforms.telegram_mtproto import TelegramMTProtoPlatform, telegram_manager
from .wechat_config_manager import WeChatGroupConfigManager
from .wxauto_config_manager import WxAutoGroupConfigManager
from utils.logger import get_logger

logger = get_logger(__name__)

class MessageForwardManager:
    """消息转发管理器"""
    
    def __init__(self, db=None):
        self.platforms: Dict[PlatformType, MessagePlatform] = {}
        self.forward_rules: Dict[str, ForwardRule] = {}
        self.message_history: List[Message] = []
        self.max_history_size = 1000
        self.running = False
        self.wechat_config_manager = WeChatGroupConfigManager()
        self.wxauto_config_manager = WxAutoGroupConfigManager()
        
        # Telegram MTProto 管理器
        self.telegram_mtproto_manager = telegram_manager
        
        # 订阅服务（如果提供了数据库连接）
        self._subscription_service = None
        if db:
            try:
                from .invitation_service import SubscriptionService
                self._subscription_service = SubscriptionService(db)
                logger.info("✅ 订阅服务已初始化")
            except Exception as e:
                logger.warning(f"⚠️ 订阅服务初始化失败: {e}")
        
        # 监听服务引用（由 api_service 设置）
        self._listener_service = None
        
        # 数据库操作实例（用于动态创建平台实例）
        self._db = db
        
        # 转发交易服务（如果提供了数据库连接）
        self._forward_trade_service = None
        if db:
            try:
                from core.forward_trade import ForwardTradeService
                self._forward_trade_service = ForwardTradeService(db)
                logger.info("✅ 转发交易服务已初始化")
            except Exception as e:
                logger.warning(f"⚠️ 转发交易服务初始化失败: {e}")
        
        logger.info("消息转发管理器初始化")
    
    def set_listener_service(self, listener_service):
        """设置监听服务引用（用于获取平台实例映射）"""
        self._listener_service = listener_service
        logger.debug("监听服务引用已设置")
    
    def _get_platform_id_map(self) -> Optional[Dict[int, MessagePlatform]]:
        """
        获取平台ID到平台实例的映射
        
        Returns:
            平台ID到平台实例的字典，如果无法获取则返回None
        """
        try:
            # 优先从监听服务获取
            if self._listener_service and hasattr(self._listener_service, 'listening_platforms'):
                platform_map = self._listener_service.listening_platforms.copy()
                
                # 对于 webhook 平台（如钉钉、TradingView），如果不在 listening_platforms 中，
                # 需要动态创建。但这里只返回已有的映射，动态创建在 _forward_message 中处理
                return platform_map if platform_map else None
            
            # 如果没有监听服务，尝试从数据库动态创建平台实例
            # 注意：这需要数据库连接，但 manager 可能没有直接的 db 引用
            logger.debug("无法从监听服务获取平台实例映射，将使用回退逻辑")
            return None
        except Exception as e:
            logger.warning(f"获取平台实例映射失败: {e}")
            return None
    
    def _get_platform_instance_by_id(self, platform_id: int) -> Optional[MessagePlatform]:
        """
        根据平台ID获取平台实例（优先从映射中获取，如果不存在则动态创建）
        
        Args:
            platform_id: 平台ID
            
        Returns:
            平台实例，如果无法获取则返回None
        """
        try:
            # 优先从监听服务获取
            if self._listener_service and hasattr(self._listener_service, 'listening_platforms'):
                if platform_id in self._listener_service.listening_platforms:
                    return self._listener_service.listening_platforms[platform_id]
            
            # 如果不在映射中，尝试动态创建
            return self._get_or_create_platform_instance(platform_id)
        except Exception as e:
            logger.warning(f"获取平台实例失败 (ID: {platform_id}): {e}")
            return None
    
    def _get_or_create_platform_instance(self, platform_id: int) -> Optional[MessagePlatform]:
        """
        根据平台ID获取或创建平台实例（用于 webhook 平台等不需要监听的平台）
        
        Args:
            platform_id: 平台ID
            
        Returns:
            平台实例，如果无法创建则返回None
        """
        try:
            # 如果没有数据库连接，无法动态创建
            if not self._db:
                logger.debug(f"无法动态创建平台实例 (ID: {platform_id})：缺少数据库连接")
                return None
            
            # 从数据库获取平台信息
            try:
                # 尝试使用 db_operations 的方法
                if hasattr(self._db, 'get_platform_by_id'):
                    platform_data = self._db.get_platform_by_id(platform_id)
                else:
                    # 如果没有这个方法，尝试直接查询
                    db_pool = None
                    if hasattr(self._db, 'db_pool'):
                        db_pool = self._db.db_pool
                    elif hasattr(self._db, '_db_pool'):
                        db_pool = self._db._db_pool
                    elif hasattr(self._db, 'query'):
                        # 如果 _db 本身就是数据库连接池（有 query 方法），直接使用
                        db_pool = self._db
                    else:
                        logger.warning(f"无法获取数据库连接池")
                        return None
                    
                    if not db_pool:
                        logger.warning(f"无法获取数据库连接池")
                        return None
                    
                    sql = "SELECT * FROM message_platforms WHERE id = %s"
                    rows = db_pool.query(sql, (platform_id,))
                    if not rows:
                        logger.warning(f"平台不存在 (ID: {platform_id})")
                        return None
                    platform_data = dict(rows[0])
                
                if not platform_data:
                    logger.warning(f"平台不存在 (ID: {platform_id})")
                    return None
                
                if not platform_data.get('enabled', False):
                    logger.warning(f"平台未启用 (ID: {platform_id})")
                    return None
                
                # 解析配置
                config = platform_data.get('config', {})
                if isinstance(config, str):
                    import json
                    config = json.loads(config)
                
                # 创建平台实例
                from .platforms import create_platform_instance
                platform_instance = create_platform_instance(
                    platform_type=platform_data.get('platform_type'),
                    config=config
                )
                
                if not platform_instance:
                    logger.warning(f"无法创建平台实例 (ID: {platform_id}, 类型: {platform_data.get('platform_type')})")
                    return None
                
                # 对于 webhook 平台，不需要连接，直接返回
                webhook_platforms = ['dingtalk', 'tradingview', 'wechat_official', 'bicoin', 'coinglass']
                platform_type_str = platform_data.get('platform_type', '').lower()
                
                # Telegram Bot 需要初始化 application 和 bot（用于处理 webhook 更新或轮询）
                if platform_type_str == 'telegram_bot':
                    # 设置 platform_id（用于后续查询）
                    if hasattr(platform_instance, 'platform_id'):
                        platform_instance.platform_id = platform_id
                    # 设置 message_manager（用于获取数据库连接池）
                    if hasattr(platform_instance, 'message_manager'):
                        platform_instance.message_manager = self
                    
                    # 需要初始化 application 和 bot（connect 方法会检查 webhook 是否已设置）
                    import asyncio
                    try:
                        loop = asyncio.get_event_loop()
                    except RuntimeError:
                        loop = asyncio.new_event_loop()
                        asyncio.set_event_loop(loop)
                    
                    try:
                        if not loop.is_running():
                            success = loop.run_until_complete(platform_instance.connect())
                            
                            # 如果没有配置 webhook（webhook_url 为空或 None），启动轮询模式（用于本地测试环境）
                            webhook_url = platform_instance.webhook_url or ''
                            if success and not webhook_url.strip():
                                try:
                                    # 使用线程运行轮询（使用阻塞式方法）
                                    import threading
                                    polling_thread = threading.Thread(
                                        target=platform_instance.run_polling_blocking,
                                        daemon=True,
                                        name=f"TelegramBotPolling-{platform_id}"
                                    )
                                    polling_thread.start()
                                    logger.info("✅ Telegram Bot 轮询已在后台线程启动（未配置 webhook，本地测试环境）")
                                except Exception as e:
                                    logger.warning(f"⚠️ 启动 Telegram Bot 轮询失败: {e}")
                                    import traceback
                                    logger.error(traceback.format_exc())
                        else:
                            # 如果事件循环正在运行，使用线程运行初始化和轮询
                            import threading
                            def init_and_poll_in_thread():
                                thread_loop = None
                                try:
                                    thread_loop = asyncio.new_event_loop()
                                    asyncio.set_event_loop(thread_loop)
                                    
                                    success = thread_loop.run_until_complete(platform_instance.connect())
                                    # 如果没有配置 webhook（webhook_url 为空或 None），启动轮询模式
                                    webhook_url = platform_instance.webhook_url or ''
                                    if success and not webhook_url.strip():
                                        # 使用阻塞式方法运行轮询
                                        platform_instance.run_polling_blocking()
                                        logger.info("✅ Telegram Bot 轮询已启动（未配置 webhook，本地测试环境）")
                                except Exception as e:
                                    logger.error(f"初始化或启动轮询失败: {e}")
                                    import traceback
                                    logger.error(traceback.format_exc())
                                finally:
                                    # 清理事件循环（如果还有的话）
                                    if thread_loop and not thread_loop.is_closed():
                                        try:
                                            thread_loop.close()
                                        except Exception:
                                            pass
                            
                            init_thread = threading.Thread(target=init_and_poll_in_thread, daemon=True)
                            init_thread.start()
                            success = True  # 假设成功，实际结果在后台处理
                        logger.debug(f"✅ 动态创建 Telegram Bot 平台实例 (ID: {platform_id})，已初始化")
                    except Exception as e:
                        logger.warning(f"初始化 Telegram Bot 平台实例失败: {e}")
                        import traceback
                        logger.error(traceback.format_exc())
                        # 即使初始化失败，也返回实例（可能后续会重试）
                    
                    return platform_instance
                
                if platform_type_str in webhook_platforms:
                    # 设置 connected 状态（webhook 平台总是"已连接"）
                    if hasattr(platform_instance, 'connected'):
                        platform_instance.connected = True
                    # 设置 platform_id（用于后续查询）
                    if hasattr(platform_instance, 'platform_id'):
                        platform_instance.platform_id = platform_id
                    logger.debug(f"✅ 动态创建 webhook 平台实例 (ID: {platform_id}, 类型: {platform_type_str})")
                    return platform_instance
                
                # 对于需要连接的平台，尝试连接
                import asyncio
                try:
                    loop = asyncio.get_event_loop()
                except RuntimeError:
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                
                connected = loop.run_until_complete(platform_instance.connect())
                if connected:
                    logger.debug(f"✅ 动态创建并连接平台实例 (ID: {platform_id})")
                    return platform_instance
                else:
                    logger.warning(f"平台连接失败 (ID: {platform_id})")
                    return None
                    
            except Exception as e:
                logger.error(f"动态创建平台实例失败 (ID: {platform_id}): {e}")
                import traceback
                logger.error(traceback.format_exc())
                return None
                
        except Exception as e:
            logger.error(f"获取或创建平台实例失败 (ID: {platform_id}): {e}")
            return None
    
    async def add_platform(self, platform: MessagePlatform) -> bool:
        """
        添加消息平台
        
        Args:
            platform: 消息平台实例
            
        Returns:
            是否添加成功
        """
        try:
            # 设置 message_manager 引用（用于 Telegram Bot 获取数据库连接池）
            if hasattr(platform, 'message_manager'):
                platform.message_manager = self
            
            # 连接平台
            if await platform.connect():
                self.platforms[platform.platform_type] = platform
                
                # 添加消息处理器
                platform.add_message_handler(self._on_message_received)
                
                # 对于 Telegram Bot 平台，如果未配置 webhook，则启动轮询
                if hasattr(platform, 'webhook_url') and hasattr(platform, 'run_polling_blocking'):
                    if not platform.webhook_url:
                        # 未配置 webhook，使用轮询模式（开发环境）
                        try:
                            # 检查是否已经有轮询在运行
                            if hasattr(platform.application, 'updater') and platform.application.updater.running:
                                logger.warning("⚠️ Telegram Bot 轮询已在运行，跳过重复启动")
                            else:
                                # 使用线程运行阻塞式轮询
                                import threading
                                polling_thread = threading.Thread(
                                    target=platform.run_polling_blocking,
                                    daemon=True,
                                    name=f"TelegramBotPolling-{getattr(platform, 'platform_id', 'unknown')}"
                                )
                                polling_thread.start()
                                logger.info("✅ Telegram Bot 轮询已在后台线程启动（未配置 webhook）")
                        except Exception as e:
                            logger.warning(f"⚠️ 启动 Telegram Bot 轮询失败: {e}")
                            import traceback
                            logger.error(traceback.format_exc())
                    else:
                        logger.info("✅ Telegram Bot 使用 Webhook 模式（生产环境推荐）")
                
                logger.info(f"✅ 平台已添加: {platform.platform_type.value}")
                return True
            else:
                logger.error(f"❌ 平台连接失败: {platform.platform_type.value}")
                return False
        except Exception as e:
            logger.error(f"添加平台失败: {e}")
            return False
    
    async def remove_platform(self, platform_type: PlatformType) -> bool:
        """移除消息平台"""
        if platform_type in self.platforms:
            platform = self.platforms[platform_type]
            await platform.disconnect()
            del self.platforms[platform_type]
            logger.info(f"平台已移除: {platform_type.value}")
            return True
        return False
    
    def add_forward_rule(self, rule: ForwardRule):
        """添加转发规则"""
        self.forward_rules[rule.rule_id] = rule
        logger.info(f"转发规则已添加: {rule.rule_name} ({rule.rule_id})")
    
    def remove_forward_rule(self, rule_id: str) -> bool:
        """移除转发规则"""
        if rule_id in self.forward_rules:
            rule = self.forward_rules[rule_id]
            del self.forward_rules[rule_id]
            logger.info(f"转发规则已移除: {rule.rule_name} ({rule_id})")
            return True
        return False
    
    def get_forward_rule(self, rule_id: str) -> Optional[ForwardRule]:
        """获取转发规则"""
        return self.forward_rules.get(rule_id)
    
    def list_forward_rules(self) -> List[ForwardRule]:
        """列出所有转发规则"""
        return list(self.forward_rules.values())
    
    async def _on_message_received(self, message: Message):
        """处理接收到的消息"""
        try:
            source_platform_str = message.source_platform.value if isinstance(message.source_platform, PlatformType) else str(message.source_platform)
            logger.info(f"📨 收到消息: [{source_platform_str}] {message.content[:50]}...")
            
            # 保存到历史记录
            self._add_to_history(message)
            
            # 获取平台实例映射（用于支持多个同类型平台实例）
            platform_id_map = self._get_platform_id_map()
            
            # 检查是否有转发规则
            if not self.forward_rules:
                logger.warning(f"⚠️ 没有配置转发规则，消息不会被转发 (当前规则数: {len(self.forward_rules)})")
                return
            
            logger.info(f"📋 检查 {len(self.forward_rules)} 个转发规则...")
            logger.info(f"   规则列表: {[rule.rule_name for rule in self.forward_rules.values()]}")
            
            # 应用转发规则
            matched_rules = []
            for rule_id, rule in self.forward_rules.items():
                if not rule.enabled:
                    logger.info(f"规则 {rule.rule_name} 未启用，跳过")
                    continue
                
                # 详细日志：检查规则匹配条件
                logger.info(f"🔍 检查规则: {rule.rule_name} (ID: {rule_id})")
                logger.info(f"   - 规则源平台ID: {rule.source_platform_id}")
                logger.info(f"   - 规则源平台类型: {rule.source_platform}")
                logger.info(f"   - 消息源平台: {message.source_platform.value if isinstance(message.source_platform, PlatformType) else message.source_platform}")
                logger.info(f"   - 消息源平台ID: {getattr(message, 'source_platform_id', None)}")
                logger.info(f"   - 规则源聊天ID: {rule.source_chat_ids}")
                logger.info(f"   - 消息源聊天ID: {message.source_chat_id}")
                
                # 检查规则是否匹配
                if not rule.matches(message):
                    logger.info(f"❌ 规则 {rule.rule_name} 不匹配")
                    continue
                
                # 如果规则指定了源平台ID，检查该平台实例的策略过滤器
                if rule.source_platform_id is not None:
                    source_platform = self._get_platform_instance_by_id(rule.source_platform_id)
                    if source_platform and hasattr(source_platform, 'strategy_filter') and source_platform.strategy_filter:
                        # 从消息的 extra_data 中获取原始数据
                        original_data = message.extra_data.get('trade_info', {}).get('original_data', {})
                        type_ = original_data.get('type_')
                        strategy = type_ or original_data.get('strategy') or original_data.get('indicator')
                        
                        if strategy:
                            if strategy not in source_platform.strategy_filter:
                                logger.info(f"❌ 规则 {rule.rule_name} 的源平台实例 (ID: {rule.source_platform_id}) 策略过滤器不匹配: '{strategy}' 不在 {source_platform.strategy_filter} 中")
                                continue
                            else:
                                logger.info(f"✅ 规则 {rule.rule_name} 的源平台实例策略过滤器匹配: '{strategy}' 在 {source_platform.strategy_filter} 中")
                        else:
                            # 如果没有策略标识，但平台配置了过滤器，则不匹配
                            logger.info(f"❌ 规则 {rule.rule_name} 的源平台实例 (ID: {rule.source_platform_id}) 配置了策略过滤器 {source_platform.strategy_filter}，但消息没有策略标识")
                            continue
                
                matched_rules.append(rule)
                logger.info(f"✅ 消息匹配规则: {rule.rule_name} (ID: {rule_id})")
            
            if not matched_rules:
                source_platform_str = message.source_platform.value if isinstance(message.source_platform, PlatformType) else str(message.source_platform)
                source_platform_id = getattr(message, 'source_platform_id', None)
                logger.warning(f"⚠️ 没有规则匹配此消息 (来源: {source_platform_str}, 平台ID: {source_platform_id})")
                return
            
            # 转发到匹配的规则
            for rule in matched_rules:
                await self._forward_message(message, rule, platform_id_map)
            
            # 处理转发交易（如果消息来自 TradingView）
            if self._forward_trade_service and message.source_platform == PlatformType.TRADINGVIEW:
                try:
                    await self._forward_trade_service.handle_message(message)
                except Exception as e:
                    logger.error(f"处理转发交易失败: {e}")
                    import traceback
                    logger.error(traceback.format_exc())
                    
        except Exception as e:
            logger.error(f"处理消息失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
    
    async def _forward_message(self, message: Message, rule: ForwardRule, platform_id_map: Optional[Dict[int, MessagePlatform]] = None):
        """
        根据规则转发消息
        
        Args:
            message: 要转发的消息
            rule: 转发规则
            platform_id_map: 平台ID到平台实例的映射（可选，用于支持多个同类型平台实例）
        """
        try:
            # 检查订阅服务是否可用
            subscription_service = getattr(self, '_subscription_service', None)
            
            # 转换消息
            transformed_message = rule.transform_message(message)
            
            # 优先使用target_platform_ids（平台实例ID列表）
            if rule.target_platform_ids:
                # 如果 platform_id_map 为空，尝试从监听服务获取
                if not platform_id_map:
                    platform_id_map = self._get_platform_id_map()
                
                # 如果启用了订阅系统，从订阅表中获取所有有效的订阅平台ID
                # 这样可以确保转发到所有有有效订阅的平台，而不仅仅是规则中配置的平台
                platform_ids_to_forward = list(rule.target_platform_ids)
                if subscription_service:
                    try:
                        # 获取该规则的所有有效订阅
                        subscriptions = subscription_service.get_subscriptions_by_rule(rule.rule_id)
                        # 提取所有有效的平台ID（使用订阅服务的验证方法确保一致性）
                        valid_platform_ids = set()
                        for sub in subscriptions:
                            platform_id = sub.get('target_platform_id')
                            chat_id = sub.get('target_chat_id', 'default')
                            # 使用订阅服务的验证方法（确保日期解析逻辑一致）
                            if subscription_service.check_subscription_valid(
                                rule.rule_id, platform_id, chat_id
                            ):
                                valid_platform_ids.add(platform_id)
                        
                        if valid_platform_ids:
                            # 合并规则中的平台ID和订阅表中的有效平台ID
                            platform_ids_to_forward = list(set(rule.target_platform_ids) | valid_platform_ids)
                            logger.info(f"📋 规则 {rule.rule_name} 的有效订阅平台ID: {sorted(platform_ids_to_forward)} (规则配置: {rule.target_platform_ids}, 订阅表: {sorted(valid_platform_ids)})")
                        else:
                            logger.info(f"📋 规则 {rule.rule_name} 没有有效的订阅，仅使用规则配置的平台ID: {rule.target_platform_ids}")
                    except Exception as e:
                        logger.warning(f"⚠️ 从订阅表获取有效订阅失败: {e}，使用规则配置的平台ID")
                        import traceback
                        logger.debug(traceback.format_exc())
                
                for platform_id in platform_ids_to_forward:
                    platform = None
                    
                    # 尝试从 platform_id_map 获取
                    if platform_id_map and platform_id in platform_id_map:
                        platform = platform_id_map[platform_id]
                    else:
                        # 如果不在映射中，尝试动态创建（特别是 webhook 平台）
                        logger.debug(f"平台实例不在映射中 (ID: {platform_id})，尝试动态创建")
                        platform = self._get_or_create_platform_instance(platform_id)
                        if platform and platform_id_map is not None:
                            # 将新创建的实例添加到映射中
                            platform_id_map[platform_id] = platform
                    
                    if not platform:
                        logger.warning(f"目标平台实例未连接且无法创建 (ID: {platform_id})")
                        continue
                    
                    # 获取平台类型，用于查找target_chat_ids
                    platform_type_str = getattr(platform, 'platform_type', None)
                    if isinstance(platform_type_str, PlatformType):
                        platform_type_str = platform_type_str.value
                    
                    # 获取目标聊天ID
                    target_chats = rule.target_chat_ids.get(platform_type_str, [])
                    if not target_chats:
                        # 尝试使用PlatformType作为key
                        if platform_type_str:
                            try:
                                platform_type = PlatformType(platform_type_str)
                                target_chats = rule.target_chat_ids.get(platform_type, [])
                            except:
                                pass
                    
                    # 某些平台（如钉钉webhook）可能不需要chat_id，允许为空
                    # 如果为空，使用默认值"default"
                    if not target_chats:
                        # 对于webhook类型的平台，允许没有chat_id
                        webhook_platforms = ['dingtalk', 'wechat_official']
                        if platform_type_str in webhook_platforms:
                            target_chats = ['default']  # 使用默认值，平台实现会忽略
                            logger.debug(f"平台 {platform_type_str} 使用默认chat_id")
                        else:
                            logger.warning(f"规则 {rule.rule_name} 未配置平台 {platform_id} 的目标聊天")
                            continue
                    
                    logger.info(f"📋 规则 {rule.rule_name} 平台 {platform_id} ({platform_type_str}) 的目标聊天列表: {target_chats} (共 {len(target_chats)} 个)")
                    
                    # 发送到每个目标聊天
                    for chat_id in target_chats:
                        logger.info(f"📤 准备转发消息到: 平台ID={platform_id}, 聊天ID={chat_id}")
                        # 检查订阅是否有效（如果启用了订阅系统）
                        if subscription_service:
                            is_valid = subscription_service.check_subscription_valid(
                                rule.rule_id, platform_id, chat_id
                            )
                            if not is_valid:
                                logger.warning(f"⚠️ 订阅已过期，跳过转发: 规则ID={rule.rule_id}, 平台ID={platform_id}, 群组={chat_id}")
                                continue
                            else:
                                logger.debug(f"✅ 订阅有效: 规则ID={rule.rule_id}, 平台ID={platform_id}, 群组={chat_id}")
                        
                        # 对于 Telegram Bot 平台，检查用户订阅过滤条件
                        # 检查是否是 Telegram Bot 平台（通过检查是否有 get_subscription_service 方法）
                        if hasattr(platform, 'get_subscription_service'):
                            # Telegram Bot 的 chat_id 就是 user_id
                            try:
                                user_id = int(chat_id)
                                # 获取 Telegram 订阅服务
                                telegram_subscription_service = platform.get_subscription_service()
                                if telegram_subscription_service:
                                    # 检查消息是否匹配用户的订阅条件
                                    is_match = telegram_subscription_service.check_message_match(
                                        user_id, rule.rule_id, transformed_message
                                    )
                                    if not is_match:
                                        logger.debug(f"⚠️ 消息不匹配用户订阅条件，跳过转发: 用户ID={user_id}, 规则ID={rule.rule_id}")
                                        continue
                                    # 更新消息计数
                                    telegram_subscription_service.increment_message_count(user_id, rule.rule_id)
                            except (ValueError, TypeError) as e:
                                logger.warning(f"⚠️ 无效的 Telegram 用户ID: {chat_id}, 错误: {e}")
                                continue
                        
                        try:
                            logger.info(f"🔄 调用平台 send_message: 平台ID={platform_id}, 平台类型={platform_type_str}, 聊天ID={chat_id}")
                            logger.debug(f"   消息内容预览: {transformed_message.content[:100]}...")
                            success = await platform.send_message(chat_id, transformed_message)
                            if success:
                                logger.info(f"✅ 消息已转发成功: 平台ID={platform_id}, 平台类型={platform_type_str}, 聊天ID={chat_id}")
                            else:
                                logger.error(f"❌ 消息转发失败（返回False）: 平台ID={platform_id}, 平台类型={platform_type_str}, 聊天ID={chat_id}")
                                logger.error(f"   请检查平台配置和网络连接")
                        except Exception as e:
                            logger.error(f"❌ 转发消息到 {chat_id} 异常: 平台ID={platform_id}, 平台类型={platform_type_str}, 错误={e}")
                            import traceback
                            logger.error(f"异常堆栈:\n{traceback.format_exc()}")
            
            # 兼容旧规则：如果没有target_platform_ids，使用target_platforms（平台类型）
            elif rule.target_platforms:
                for target_platform_str in rule.target_platforms:
                    # 转换为 PlatformType
                    try:
                        if isinstance(target_platform_str, PlatformType):
                            target_platform = target_platform_str
                        else:
                            target_platform = PlatformType(target_platform_str)
                    except ValueError:
                        logger.warning(f"无效的目标平台类型: {target_platform_str}")
                        continue
                    
                    if target_platform not in self.platforms:
                        logger.warning(f"目标平台未连接: {target_platform.value}")
                        continue
                    
                    platform = self.platforms[target_platform]
                    
                    # 获取目标聊天ID（支持字符串键和PlatformType键）
                    target_chats = rule.target_chat_ids.get(target_platform_str, [])
                    if not target_chats:
                        target_chats = rule.target_chat_ids.get(target_platform, [])
                    
                    # 某些平台（如钉钉webhook）可能不需要chat_id，允许为空
                    if not target_chats:
                        # 对于webhook类型的平台，允许没有chat_id
                        webhook_platforms = ['dingtalk', 'wechat_official']
                        if target_platform.value in webhook_platforms:
                            target_chats = ['default']  # 使用默认值，平台实现会忽略
                            logger.debug(f"平台 {target_platform.value} 使用默认chat_id")
                        else:
                            logger.warning(f"规则 {rule.rule_name} 未配置 {target_platform.value} 的目标聊天")
                            continue
                    
                    # 发送到每个目标聊天
                    for chat_id in target_chats:
                        try:
                            success = await platform.send_message(chat_id, transformed_message)
                            if success:
                                logger.info(f"✅ 消息已转发: {target_platform.value} -> {chat_id}")
                            else:
                                logger.error(f"❌ 消息转发失败: {target_platform.value} -> {chat_id}")
                        except Exception as e:
                            logger.error(f"转发消息到 {chat_id} 失败: {e}")
                        
        except Exception as e:
            logger.error(f"转发消息失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
    
    async def send_message_to(self, platform_type: PlatformType, 
                              chat_id: str, message: Message) -> bool:
        """手动发送消息到指定平台和聊天"""
        if platform_type not in self.platforms:
            logger.error(f"平台未连接: {platform_type.value}")
            return False
        
        platform = self.platforms[platform_type]
        return await platform.send_message(chat_id, message)
    
    def _add_to_history(self, message: Message):
        """添加消息到历史记录"""
        self.message_history.append(message)
        
        # 限制历史记录大小
        if len(self.message_history) > self.max_history_size:
            self.message_history = self.message_history[-self.max_history_size:]
    
    def get_message_history(self, limit: int = 100) -> List[Message]:
        """获取消息历史记录"""
        return self.message_history[-limit:]
    
    async def start(self):
        """启动消息转发服务"""
        if self.running:
            logger.warning("消息转发服务已经在运行")
            return
        
        logger.info("🚀 启动消息转发服务...")
        self.running = True
        
        # 连接所有平台
        for platform in self.platforms.values():
            if not platform.connected:
                await platform.connect()
        
        logger.info("✅ 消息转发服务已启动")
    
    async def stop(self):
        """停止消息转发服务"""
        logger.info("停止消息转发服务...")
        self.running = False
        
        # 断开所有平台
        for platform in self.platforms.values():
            await platform.disconnect()
        
        logger.info("✅ 消息转发服务已停止")
    
    def get_status(self) -> Dict[str, Any]:
        """获取服务状态"""
        return {
            'running': self.running,
            'platforms': {
                pt.value: platform.get_status()
                for pt, platform in self.platforms.items()
            },
            'forward_rules_count': len(self.forward_rules),
            'active_rules_count': sum(1 for r in self.forward_rules.values() if r.enabled),
            'message_history_count': len(self.message_history)
        }
    
    async def test_platform_connection(self, platform_type: PlatformType) -> bool:
        """测试平台连接"""
        if platform_type not in self.platforms:
            return False
        
        platform = self.platforms[platform_type]
        return await platform.test_connection()
    
    @classmethod
    async def create_from_config(cls, config: Dict[str, Any], db=None) -> 'MessageForwardManager':
        """从配置创建管理器实例"""
        manager = cls(db=db)
        
        # 添加平台
        platforms_config = config.get('platforms', {})
        
        if platforms_config.get('telegram', {}).get('enabled'):
            tg_platform = TelegramMTProtoPlatform(platforms_config['telegram'])
            await manager.add_platform(tg_platform)
        
        if platforms_config.get('dingtalk', {}).get('enabled'):
            dt_platform = DingTalkPlatform(platforms_config['dingtalk'])
            await manager.add_platform(dt_platform)
        
        if platforms_config.get('wechat', {}).get('enabled'):
            wx_platform = WeChatPlatform(platforms_config['wechat'])
            await manager.add_platform(wx_platform)
        
        if platforms_config.get('bicoin', {}).get('enabled'):
            bicoin_platform = BicoinPlatform(platforms_config['bicoin'])
            await manager.add_platform(bicoin_platform)
        
        if platforms_config.get('coinglass', {}).get('enabled'):
            coinglass_platform = CoinGlassPlatform(platforms_config['coinglass'])
            await manager.add_platform(coinglass_platform)
        
        if platforms_config.get('tradingview', {}).get('enabled'):
            tradingview_platform = TradingViewPlatform(platforms_config['tradingview'])
            await manager.add_platform(tradingview_platform)
        
        # 添加转发规则
        rules_config = config.get('forward_rules', [])
        for rule_config in rules_config:
            rule = ForwardRule(
                rule_id=rule_config.get('rule_id', str(uuid.uuid4())),
                rule_name=rule_config.get('rule_name', rule_config.get('name', '未命名规则')),
                enabled=rule_config.get('enabled', True),
                source_platform=PlatformType(rule_config['source_platform']) if rule_config.get('source_platform') else None,
                source_chat_ids=rule_config.get('source_chat_ids', []),
                target_platforms=[PlatformType(p) for p in rule_config.get('target_platforms', [])],
                target_chat_ids={
                    PlatformType(k): v 
                    for k, v in rule_config.get('target_chat_ids', {}).items()
                },
                keywords=rule_config.get('keywords', []),
                exclude_keywords=rule_config.get('exclude_keywords', []),
                add_prefix=rule_config.get('add_prefix'),
                add_suffix=rule_config.get('add_suffix'),
                enable_markdown=rule_config.get('enable_markdown', False)
            )
            manager.add_forward_rule(rule)
        
        # 加载微信群配置
        if PlatformType.WECHAT in manager.platforms:
            await manager.load_wechat_group_config()
        
        # 加载wxauto配置
        if PlatformType.WECHAT in manager.platforms:
            await manager.load_wxauto_group_config()
        
        logger.info(f"✅ 管理器已从配置创建: {len(manager.platforms)} 个平台, {len(manager.forward_rules)} 条规则")
        return manager
    
    async def load_wechat_group_config(self):
        """加载微信群配置"""
        try:
            if PlatformType.WECHAT not in self.platforms:
                return
            
            wechat_platform = self.platforms[PlatformType.WECHAT]
            if not isinstance(wechat_platform, WeChatPlatform):
                return
            
            # 加载配置文件
            config = wechat_platform.load_config()
            if not config:
                logger.warning("未找到微信群配置文件")
                return
            
            # 添加转发规则
            rules_config = self.wechat_config_manager.get_forward_rules_for_manager()
            for rule_config in rules_config:
                rule = ForwardRule.from_dict(rule_config)
                self.add_forward_rule(rule)
            
            logger.info(f"✅ 已加载 {len(rules_config)} 条微信群转发规则")
            
        except Exception as e:
            logger.error(f"加载微信群配置失败: {e}")
    
    async def load_wxauto_group_config(self):
        """加载wxauto配置"""
        try:
            if PlatformType.WECHAT not in self.platforms:
                return
            
            wechat_platform = self.platforms[PlatformType.WECHAT]
            if not isinstance(wechat_platform, WxAutoWeChatPlatform):
                return
            
            # 加载配置文件
            config = wechat_platform.load_config()
            if not config:
                logger.warning("未找到wxauto配置文件")
                return
            
            # 添加转发规则
            rules_config = self.wxauto_config_manager.get_forward_rules_for_manager()
            for rule_config in rules_config:
                rule = ForwardRule.from_dict(rule_config)
                self.add_forward_rule(rule)
            
            logger.info(f"✅ 已加载 {len(rules_config)} 条wxauto转发规则")
            
        except Exception as e:
            logger.error(f"加载wxauto配置失败: {e}")
    
    async def configure_wechat_groups(self):
        """配置微信群"""
        try:
            if PlatformType.WECHAT not in self.platforms:
                logger.error("微信平台未连接")
                return False
            
            wechat_platform = self.platforms[PlatformType.WECHAT]
            if not isinstance(wechat_platform, WeChatPlatform):
                logger.error("微信平台类型错误")
                return False
            
            # 使用配置管理器进行交互式配置
            await self.wechat_config_manager.initialize_wechat_platform()
            await self.wechat_config_manager.discover_groups()
            
            # 这里可以添加交互式配置逻辑
            logger.info("微信群配置功能已就绪")
            return True
            
        except Exception as e:
            logger.error(f"配置微信群失败: {e}")
            return False
    
    def get_wechat_groups(self) -> List[Dict[str, Any]]:
        """获取微信群列表"""
        if PlatformType.WECHAT not in self.platforms:
            return []
        
        wechat_platform = self.platforms[PlatformType.WECHAT]
        if isinstance(wechat_platform, WeChatPlatform):
            return wechat_platform.discover_groups()
        
        return []
    
    def get_wechat_config_summary(self) -> Dict[str, Any]:
        """获取微信群配置摘要"""
        return {
            'groups_count': len(self.wechat_config_manager.config.get('discovered_groups', [])),
            'selected_groups_count': len([g for g in self.wechat_config_manager.config.get('discovered_groups', []) if g.get('is_selected', False)]),
            'keywords_count': len(self.wechat_config_manager.config.get('keywords', [])),
            'forward_targets_count': len(self.wechat_config_manager.config.get('forward_targets', [])),
            'config_file': self.wechat_config_manager.config_file,
            'wxauto_config': {
                'groups_count': len(self.wxauto_config_manager.config.get('discovered_groups', [])),
                'listening_groups_count': len(self.wxauto_config_manager.get_listening_groups()),
                'keywords_count': len(self.wxauto_config_manager.config.get('keywords', [])),
                'forward_targets_count': len(self.wxauto_config_manager.config.get('forward_targets', [])),
                'config_file': self.wxauto_config_manager.config_file,
                'wechat_version': self.wxauto_config_manager.config.get('wechat_version', '3.9.8'),
                'max_listeners': self.wxauto_config_manager.config.get('max_listeners', 40)
            }
        }
    
    # Telegram MTProto 相关方法
    async def add_telegram_mtproto_platform(self, platform_id: str, config: Dict[str, Any]) -> bool:
        """添加 Telegram MTProto 平台"""
        try:
            success = await self.telegram_mtproto_manager.add_platform(platform_id, config)
            if success:
                logger.info(f"添加 Telegram MTProto 平台成功: {platform_id}")
            return success
        except Exception as e:
            logger.error(f"添加 Telegram MTProto 平台失败: {e}")
            return False
    
    async def remove_telegram_mtproto_platform(self, platform_id: str) -> bool:
        """移除 Telegram MTProto 平台"""
        try:
            success = await self.telegram_mtproto_manager.remove_platform(platform_id)
            if success:
                logger.info(f"移除 Telegram MTProto 平台成功: {platform_id}")
            return success
        except Exception as e:
            logger.error(f"移除 Telegram MTProto 平台失败: {e}")
            return False
    
    async def login_telegram_mtproto_platform(self, platform_id: str, phone_code: Optional[str] = None, password: Optional[str] = None) -> bool:
        """登录 Telegram MTProto 平台"""
        try:
            success = await self.telegram_mtproto_manager.login_platform(platform_id, phone_code, password)
            if success:
                logger.info(f"Telegram MTProto 平台登录成功: {platform_id}")
            return success
        except Exception as e:
            logger.error(f"Telegram MTProto 平台登录失败: {e}")
            return False
    
    async def send_telegram_mtproto_message(self, platform_id: str, chat_id: str, message: str) -> bool:
        """通过 Telegram MTProto 发送消息"""
        try:
            success = await self.telegram_mtproto_manager.send_message(platform_id, chat_id, message)
            if success:
                logger.info(f"Telegram MTProto 消息发送成功: {platform_id} -> {chat_id}")
            return success
        except Exception as e:
            logger.error(f"Telegram MTProto 消息发送失败: {e}")
            return False
    
    async def get_telegram_mtproto_chats(self, platform_id: str) -> List[Dict[str, Any]]:
        """获取 Telegram MTProto 聊天列表"""
        try:
            chats = await self.telegram_mtproto_manager.get_platform_chats(platform_id)
            logger.info(f"获取 Telegram MTProto 聊天列表成功: {platform_id}, 共 {len(chats)} 个聊天")
            return chats
        except Exception as e:
            logger.error(f"获取 Telegram MTProto 聊天列表失败: {e}")
            return []
    
    def get_telegram_mtproto_platform_status(self, platform_id: str) -> Dict[str, Any]:
        """获取 Telegram MTProto 平台状态"""
        return self.telegram_mtproto_manager.get_platform_status(platform_id)
    
    def list_telegram_mtproto_platforms(self) -> List[str]:
        """列出所有 Telegram MTProto 平台"""
        return self.telegram_mtproto_manager.list_platforms()
    
    def get_telegram_mtproto_config_summary(self) -> Dict[str, Any]:
        """获取 Telegram MTProto 配置摘要"""
        platforms = self.list_telegram_mtproto_platforms()
        platform_statuses = {}
        
        for platform_id in platforms:
            status = self.get_telegram_mtproto_platform_status(platform_id)
            platform_statuses[platform_id] = status
        
        return {
            'platforms_count': len(platforms),
            'platforms': platform_statuses,
            'config_file': self.telegram_mtproto_manager.config_file
        }
    
    # 全局管理器实例
_global_manager: Optional[MessageForwardManager] = None

def get_message_forward_manager() -> Optional[MessageForwardManager]:
    """获取全局消息转发管理器实例"""
    return _global_manager

def set_message_forward_manager(manager: MessageForwardManager):
    """设置全局消息转发管理器实例"""
    global _global_manager
    _global_manager = manager

