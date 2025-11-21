"""
消息转发模块 - API服务集成层
提供与 Flask API 的集成接口
"""

from typing import Dict, Any, List, Optional
from datetime import datetime, timezone, timedelta
import json
from utils.logger import get_logger

# 根据环境选择数据库操作层
try:
    # 尝试导入MySQL版本
    from core.message_forward.db_operations_mysql import get_message_forward_db
    logger = get_logger(__name__)
    logger.info("✅ 使用MySQL数据库操作层")
except ImportError:
    # 回退到SQLite版本
    from core.message_forward.db_operations import get_message_forward_db
    logger = get_logger(__name__)
    logger.info("✅ 使用SQLite数据库操作层")

from core.message_forward.manager import MessageForwardManager
from core.message_forward.models import PlatformConfig, ForwardRule
from core.message_forward.listener_service import UnifiedListenerService


class MessageForwardAPIService:
    """消息转发API服务"""
    
    def __init__(self, db_pool=None):
        """
        初始化服务
        
        Args:
            db_pool: MySQL连接池实例（可选，如果提供则使用MySQL）
        """
        if db_pool:
            self.db = get_message_forward_db(db_pool)
        else:
            self.db = get_message_forward_db()
        self.manager: Optional[MessageForwardManager] = None
        self.listener_service: Optional[UnifiedListenerService] = None
        self.reminder_service = None
        self.is_running = False
        
        # 注意：跨 HTTP 请求缓存 Telethon 客户端实例会导致 event loop 错误
        # 因为 Flask 的不同请求可能使用不同的 event loop
        # 解决方案：使用独立的登录脚本 telegram_platform_login.py
        # self._login_instances: Dict[int, Any] = {}  # ❌ 不能这样做
        
        logger.info("📨 消息转发API服务初始化完成")
    
    # ==================== 服务控制 ====================
    
    async def start_service(self) -> Dict[str, Any]:
        """
        启动消息转发服务
        
        Returns:
            操作结果
        """
        try:
            logger.info("=" * 80)
            logger.info("🚀 [消息转发] 开始启动服务...")
            logger.info("=" * 80)
            
            if self.is_running:
                logger.warning("⚠️ 服务已在运行中，跳过启动")
                return {
                    'success': True,
                    'message': '服务已在运行中'
                }
            
            # 从数据库加载规则
            logger.info("📥 正在从数据库加载转发规则...")
            rules = self.db.get_rules()
            enabled_rules_count = len([r for r in rules if r.get('enabled', False)])
            logger.info(f"📋 从数据库加载了 {len(rules)} 个转发规则，其中 {enabled_rules_count} 个已启用")
            
            # 创建管理器实例（传入数据库连接以支持订阅服务）
            from config.message_forward_config import MESSAGE_FORWARD_CONFIG
            # 获取数据库连接池（从db对象中获取）
            db_pool_for_subscription = None
            if hasattr(self.db, '_db_pool'):
                db_pool_for_subscription = self.db._db_pool
            elif hasattr(self.db, 'db_pool'):
                db_pool_for_subscription = self.db.db_pool
            
            self.manager = await MessageForwardManager.create_from_config(
                MESSAGE_FORWARD_CONFIG, 
                db=db_pool_for_subscription
            )
            
            # 初始化转发交易服务
            if self.manager._forward_trade_service:
                try:
                    await self.manager._forward_trade_service.initialize()
                    logger.info("✅ 转发交易服务初始化完成")
                except Exception as e:
                    logger.warning(f"⚠️ 转发交易服务初始化失败: {e}")
            
            # 从数据库加载并添加规则到管理器
            loaded_count = 0
            for rule_data in rules:
                if rule_data.get('enabled', False):
                    try:
                        # 如果规则有 source_platform_id 但没有 source_platform，从数据库查询并填充
                        source_platform_id = rule_data.get('source_platform_id')
                        source_platform = rule_data.get('source_platform', '')
                        # 优先使用 JOIN 查询得到的 source_platform_type
                        if not source_platform and rule_data.get('source_platform_type'):
                            source_platform = rule_data.get('source_platform_type', '')
                        # 如果还是没有，从数据库查询
                        if source_platform_id and not source_platform:
                            # 从数据库查询平台类型
                            platform_data = self.db.get_platform_by_id(source_platform_id)
                            if platform_data:
                                source_platform = platform_data.get('platform_type', '')
                                logger.info(f"ℹ️ 规则 {rule_data['rule_name']} 通过平台ID {source_platform_id} 获取平台类型: {source_platform}")
                        
                        # 如果规则有 target_platform_ids 但没有，尝试从订阅记录获取
                        target_platform_ids = rule_data.get('target_platform_ids', [])
                        if not target_platform_ids:
                            # 从订阅记录获取目标平台ID
                            try:
                                from database.global_db_manager import get_global_db_pool
                                db_pool = get_global_db_pool()
                                subscription_sql = "SELECT DISTINCT target_platform_id FROM forward_rule_subscriptions WHERE rule_id = %s"
                                subscription_rows = db_pool.query(subscription_sql, (rule_data['rule_id'],))
                                if subscription_rows:
                                    target_platform_ids = [row['target_platform_id'] for row in subscription_rows]
                                    logger.info(f"ℹ️ 规则 {rule_data['rule_name']} 从订阅记录获取目标平台ID: {target_platform_ids}")
                            except Exception as e:
                                logger.warning(f"⚠️ 从订阅记录获取目标平台ID失败: {e}")
                        
                        forward_rule = ForwardRule(
                            rule_id=rule_data['rule_id'],
                            rule_name=rule_data['rule_name'],
                            enabled=True,
                            source_platform_id=source_platform_id,  # 新字段
                            source_platform=source_platform,  # 兼容旧数据，如果为空则从平台ID查询
                            source_chat_ids=rule_data.get('source_chat_ids', []),
                            target_platform_ids=target_platform_ids,  # 新增：目标平台实例ID列表，如果为空则从订阅记录获取
                            target_platforms=rule_data.get('target_platforms', []),  # 保留：兼容旧数据
                            target_chat_ids=rule_data.get('target_chat_ids', {}),
                            keywords=rule_data.get('keywords', []),
                            exclude_keywords=rule_data.get('exclude_keywords', []),
                            add_prefix=rule_data.get('add_prefix', ''),
                            add_suffix=rule_data.get('add_suffix', ''),
                            enable_markdown=rule_data.get('enable_markdown', False)
                        )
                        self.manager.add_forward_rule(forward_rule)
                        loaded_count += 1
                        logger.info(f"✅ 已加载转发规则: {rule_data['rule_name']} (源平台ID: {source_platform_id}, 源平台: {source_platform}, 目标平台ID: {target_platform_ids})")
                    except Exception as e:
                        logger.error(f"❌ 加载规则失败 {rule_data['rule_name']}: {e}")
                        import traceback
                        logger.error(traceback.format_exc())
            
            logger.info(f"📊 规则加载完成: 共加载 {loaded_count} 个启用规则到管理器")
            
            # 创建统一监听服务
            # 监听服务会根据已加载的规则自动连接和启动平台监听
            logger.info(f"📦 创建统一监听服务，已加载 {len([r for r in rules if r.get('enabled', False)])} 个启用规则")
            self.listener_service = UnifiedListenerService(self.manager, self.db)
            
            # 将监听服务引用设置到 manager（用于获取平台实例映射）
            self.manager.set_listener_service(self.listener_service)
            
            # 启动监听服务（根据规则自动管理平台监听）
            logger.info("🚀 准备启动统一监听服务...")
            await self.listener_service.start()
            logger.info(f"✅ 统一监听服务已启动，当前监听平台数: {len(self.listener_service.listening_platforms)}")
            
            # 启动管理器
            await self.manager.start()
            self.is_running = True
            
            # 启动订阅到期提醒服务
            try:
                from core.message_forward.subscription_reminder import SubscriptionReminderService
                self.reminder_service = SubscriptionReminderService(self.db, self.manager)
                self.reminder_service.start()
                logger.info("✅ 订阅到期提醒服务已启动")
            except Exception as e:
                logger.warning(f"⚠️ 启动订阅提醒服务失败: {e}")
                import traceback
                logger.error(traceback.format_exc())
            
            logger.info("✅ 消息转发服务启动成功")
            return {
                'success': True,
                'message': '消息转发服务启动成功',
                'data': {
                    'rules_loaded': len(rules),
                    'listening_platforms': len(self.listener_service.listening_platforms)
                }
            }
            
        except Exception as e:
            logger.error(f"❌ 启动消息转发服务失败: {e}")
            return {
                'success': False,
                'message': f'启动失败: {str(e)}'
            }
    
    async def stop_service(self) -> Dict[str, Any]:
        """
        停止消息转发服务
        
        Returns:
            操作结果
        """
        try:
            if not self.is_running or not self.manager:
                return {
                    'success': True,
                    'message': '服务未在运行'
                }
            
            # 停止监听服务
            if self.listener_service:
                await self.listener_service.stop()
                self.listener_service = None
            
            await self.manager.stop()
            self.is_running = False
            self.manager = None
            
            logger.info("✅ 消息转发服务已停止")
            return {
                'success': True,
                'message': '消息转发服务已停止'
            }
            
        except Exception as e:
            logger.error(f"❌ 停止消息转发服务失败: {e}")
            return {
                'success': False,
                'message': f'停止失败: {str(e)}'
            }
    
    def get_service_status(self) -> Dict[str, Any]:
        """
        获取服务状态
        
        Returns:
            服务状态信息
        """
        try:
            platforms = self.db.get_platforms()
            rules = self.db.get_rules()
            
            # 统计连接的平台数（检查实时状态）
            # 如果服务正在运行，统计 listener_service 中的活跃连接
            if self.is_running and self.listener_service:
                connected_platforms = len(self.listener_service.listening_platforms)
            else:
                # 服务未运行时，从数据库状态统计
                connected_platforms = sum(1 for p in platforms if p.get('status') in ['active', 'connected'] and p['enabled'])
            
            # 统计活跃规则数
            active_rules = sum(1 for r in rules if r['enabled'])
            
            # 统计今日转发消息数（简化版，从所有规则计数）
            today_forwarded = sum(r.get('messages_forwarded', 0) for r in rules)
            
            return {
                'success': True,
                'data': {
                    'running': self.is_running,
                    'connected_platforms': connected_platforms,
                    'active_rules': active_rules,
                    'today_forwarded': today_forwarded
                }
            }
            
        except Exception as e:
            logger.error(f"❌ 获取服务状态失败: {e}")
            return {
                'success': False,
                'message': f'获取状态失败: {str(e)}'
            }
    
    # ==================== 平台管理 ====================
    
    async def add_platform(self, platform_data: Dict[str, Any]) -> Dict[str, Any]:
        """添加平台"""
        try:
            # 保存到数据库
            platform_id = self.db.add_platform(platform_data)
            
            if not platform_id:
                return {
                    'success': False,
                    'message': '添加平台失败，可能平台名称已存在'
                }
            
            # 平台添加成功，监听服务会在有规则需要时自动连接此平台
            # 不需要手动添加到管理器，UnifiedListenerService 会根据规则自动管理
            logger.info(f"平台 {platform_data['platform_name']} 已添加到数据库，等待规则激活")
            
            return {
                'success': True,
                'message': '平台添加成功',
                'data': {'platform_id': platform_id}
            }
            
        except Exception as e:
            logger.error(f"❌ 添加平台失败: {e}")
            return {
                'success': False,
                'message': f'添加失败: {str(e)}'
            }
    
    def get_platforms(self, page: int = 1, page_size: int = 20) -> Dict[str, Any]:
        """获取平台列表（包含实时连接状态，支持分页）"""
        try:
            all_platforms = self.db.get_platforms()
            
            # 分页处理
            total = len(all_platforms)
            start = (page - 1) * page_size
            end = start + page_size
            platforms = all_platforms[start:end]
            
            # Webhook类型的平台（不需要主动连接，被动接收消息）
            webhook_platform_types = ['tradingview', 'dingtalk', 'wechat_official', 'bicoin', 'coinglass']
            
            # 如果服务正在运行，更新实时连接状态
            if self.is_running and self.listener_service:
                for platform in platforms:
                    platform_id = platform['id']
                    platform_type = platform.get('platform_type', '').lower()
                    
                    # Webhook类型平台：只要已启用就显示为已连接
                    if platform_type in webhook_platform_types:
                        if platform.get('enabled', False):
                            platform['status'] = 'connected'
                            # 使用中国时区时间
                            china_tz = timezone(timedelta(hours=8))
                            platform['last_active_at'] = datetime.now(china_tz).strftime('%Y-%m-%d %H:%M:%S')
                            logger.debug(f"平台 {platform_id} ({platform_type}) 是Webhook类型，已启用，状态：已连接")
                        else:
                            platform['status'] = 'inactive'
                            logger.debug(f"平台 {platform_id} ({platform_type}) 是Webhook类型，未启用")
                    # 检查平台是否在监听服务中
                    elif platform_id in self.listener_service.listening_platforms:
                        platform_instance = self.listener_service.listening_platforms[platform_id]
                        # 更新实时状态（兼容 is_connected 和 connected 两种属性名）
                        is_connected = getattr(platform_instance, 'is_connected', None) or getattr(platform_instance, 'connected', False)
                        platform['status'] = 'connected' if is_connected else 'disconnected'
                        # 使用中国时区时间
                        china_tz = timezone(timedelta(hours=8))
                        platform['last_active_at'] = datetime.now(china_tz).strftime('%Y-%m-%d %H:%M:%S')
                        logger.debug(f"平台 {platform_id} 实时状态: {platform['status']}")
                    else:
                        # 平台未在监听服务中
                        platform['status'] = 'disconnected'
                        logger.debug(f"平台 {platform_id} 未在监听服务中")
            else:
                # 服务未运行，但Webhook类型平台如果已启用仍显示为就绪
                for platform in platforms:
                    platform_id = platform['id']
                    platform_type = platform.get('platform_type', '').lower()
                    if platform_type in webhook_platform_types and platform.get('enabled', False):
                        platform['status'] = 'ready'  # Webhook类型平台就绪状态
                        # 使用中国时区时间
                        china_tz = timezone(timedelta(hours=8))
                        platform['last_active_at'] = datetime.now(china_tz).strftime('%Y-%m-%d %H:%M:%S')
                        logger.debug(f"平台 {platform_id} ({platform_type}) 是Webhook类型，服务未运行但已启用，状态：就绪")
            
            # 过滤敏感信息
            for platform in platforms:
                if 'config' in platform and platform['config']:
                    config = platform['config']
                    if isinstance(config, str):
                        try:
                            import json
                            config = json.loads(config)
                        except:
                            continue
                    
                    # 脱敏处理
                    if 'api_id' in config:
                        config['api_id'] = str(config['api_id'])[:4] + '***' if config['api_id'] else None
                    if 'api_hash' in config:
                        config['api_hash'] = config['api_hash'][:8] + '***' if config['api_hash'] else None
                    if 'session_string' in config:
                        config['session_string'] = '***' if config['session_string'] else None
                    if 'phone' in config:
                        # 手机号只显示前3位和后4位
                        phone = str(config['phone'])
                        if len(phone) > 7:
                            config['phone'] = phone[:3] + '****' + phone[-4:]
                    if 'webhook_url' in config:
                        # Webhook URL只显示域名部分
                        url = config['webhook_url']
                        if url and '://' in url:
                            try:
                                from urllib.parse import urlparse
                                parsed = urlparse(url)
                                config['webhook_url'] = f"{parsed.scheme}://{parsed.netloc}/***"
                            except:
                                config['webhook_url'] = '***'
                    if 'secret' in config:
                        config['secret'] = '***'
                    if 'client_secret' in config:
                        config['client_secret'] = '***'
                    if 'access_token' in config:
                        config['access_token'] = '***'
                    if 'token' in config:
                        config['token'] = '***'
                    
                    # 更新platform的config
                    platform['config'] = config
            
            return {
                'success': True,
                'data': platforms,
                'pagination': {
                    'page': page,
                    'page_size': page_size,
                    'total': total,
                    'total_pages': (total + page_size - 1) // page_size if page_size > 0 else 0
                }
            }
        except Exception as e:
            logger.error(f"❌ 获取平台列表失败: {e}")
            return {
                'success': False,
                'message': f'获取失败: {str(e)}'
            }
    
    def get_platform(self, platform_id: int) -> Dict[str, Any]:
        """获取单个平台"""
        try:
            platform = self.db.get_platform_by_id(platform_id)
            if platform:
                # 过滤敏感信息
                if 'config' in platform and platform['config']:
                    config = platform['config']
                    if isinstance(config, str):
                        try:
                            import json
                            config = json.loads(config)
                        except:
                            pass
                    
                    if isinstance(config, dict):
                        # 脱敏处理
                        if 'api_id' in config:
                            config['api_id'] = str(config['api_id'])[:4] + '***' if config['api_id'] else None
                        if 'api_hash' in config:
                            config['api_hash'] = config['api_hash'][:8] + '***' if config['api_hash'] else None
                        if 'session_string' in config:
                            config['session_string'] = '***' if config['session_string'] else None
                        if 'phone' in config:
                            # 手机号只显示前3位和后4位
                            phone = str(config['phone'])
                            if len(phone) > 7:
                                config['phone'] = phone[:3] + '****' + phone[-4:]
                        if 'webhook_url' in config:
                            # Webhook URL只显示域名部分
                            url = config['webhook_url']
                            if url and '://' in url:
                                try:
                                    from urllib.parse import urlparse
                                    parsed = urlparse(url)
                                    config['webhook_url'] = f"{parsed.scheme}://{parsed.netloc}/***"
                                except:
                                    config['webhook_url'] = '***'
                        if 'secret' in config:
                            config['secret'] = '***'
                        if 'client_secret' in config:
                            config['client_secret'] = '***'
                        if 'access_token' in config:
                            config['access_token'] = '***'
                        if 'token' in config:
                            config['token'] = '***'
                        
                        # 更新platform的config
                        platform['config'] = config
                
                return {
                    'success': True,
                    'data': platform
                }
            else:
                return {
                    'success': False,
                    'message': '平台不存在'
                }
        except Exception as e:
            logger.error(f"❌ 获取平台失败: {e}")
            return {
                'success': False,
                'message': f'获取失败: {str(e)}'
            }
    
    async def update_platform(self, platform_id: int, update_data: Dict[str, Any]) -> Dict[str, Any]:
        """更新平台"""
        try:
            success = self.db.update_platform(platform_id, update_data)
            
            if success:
                # 如果更新了monitored_chats且服务正在运行，重新启动监听以应用新配置
                if 'monitored_chats' in update_data and self.is_running and self.listener_service:
                    # 检查平台是否正在监听（需要检查是否有规则使用该平台）
                    platform_data = self.db.get_platform_by_id(platform_id)
                    if platform_data and platform_data.get('enabled'):
                        # 检查是否有启用的规则使用该平台
                        rules = self.db.get_rules()
                        has_active_rule = any(
                            r.get('enabled') and r.get('source_platform_id') == platform_id
                            for r in rules
                        )
                        
                        if has_active_rule:
                            # 先停止
                            await self.listener_service._stop_platform_listening(platform_id)
                            # 再启动（会读取新的monitored_chats配置）
                            await self.listener_service._start_platform_listening(platform_id)
                        else:
                            # 没有规则使用该平台，但monitored_chats已更新，记录日志
                            logger.info(f"平台 {platform_id} 的monitored_chats已更新，但当前没有启用的规则使用该平台")
                
                return {
                    'success': True,
                    'message': '平台更新成功'
                }
            else:
                return {
                    'success': False,
                    'message': '平台更新失败'
                }
        except Exception as e:
            logger.error(f"❌ 更新平台失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return {
                'success': False,
                'message': f'更新失败: {str(e)}'
            }
    
    async def delete_platform(self, platform_id: int) -> Dict[str, Any]:
        """删除平台"""
        try:
            success = self.db.delete_platform(platform_id)
            
            if success:
                # TODO: 如果服务正在运行，从管理器中删除平台
                return {
                    'success': True,
                    'message': '平台删除成功'
                }
            else:
                return {
                    'success': False,
                    'message': '平台不存在'
                }
        except Exception as e:
            logger.error(f"❌ 删除平台失败: {e}")
            return {
                'success': False,
                'message': f'删除失败: {str(e)}'
            }
    
    async def enable_platform(self, platform_id: int) -> Dict[str, Any]:
        """启用平台"""
        try:
            success = self.db.enable_platform(platform_id)
            
            if success:
                return {
                    'success': True,
                    'message': '平台已启用'
                }
            else:
                return {
                    'success': False,
                    'message': '启用失败'
                }
        except Exception as e:
            logger.error(f"❌ 启用平台失败: {e}")
            return {
                'success': False,
                'message': f'启用失败: {str(e)}'
            }
    
    async def disable_platform(self, platform_id: int) -> Dict[str, Any]:
        """禁用平台"""
        try:
            success = self.db.disable_platform(platform_id)
            
            if success:
                # 如果服务正在运行，停止该平台的监听
                if self.is_running and self.manager:
                    await self._stop_platform_listening(platform_id)
                
                return {
                    'success': True,
                    'message': '平台已禁用'
                }
            else:
                return {
                    'success': False,
                    'message': '禁用失败'
                }
        except Exception as e:
            logger.error(f"❌ 禁用平台失败: {e}")
            return {
                'success': False,
                'message': f'禁用失败: {str(e)}'
            }
    
    async def test_platform(self, platform_id: int, duration: int = 30) -> Dict[str, Any]:
        """
        测试平台监听功能
        
        Args:
            platform_id: 平台ID
            duration: 测试持续时间（秒），默认30秒
        
        Returns:
            测试结果
        """
        try:
            # 获取平台信息
            platform_data = self.db.get_platform_by_id(platform_id)
            if not platform_data:
                return {
                    'success': False,
                    'message': '平台不存在'
                }
            
            # 创建临时平台实例进行测试
            from core.message_forward.platforms import create_platform_instance
            from core.message_forward.models import Message, MessageType, PlatformType
            import asyncio
            
            platform_instance = create_platform_instance(
                platform_type=platform_data['platform_type'],
                config=platform_data['config']
            )
            
            if not platform_instance:
                return {
                    'success': False,
                    'message': f'不支持的平台类型: {platform_data["platform_type"]}'
                }
            
            # 初始化平台（兼容不同的方法名）
            try:
                init_result = False
                if hasattr(platform_instance, 'initialize'):
                    init_result = await platform_instance.initialize()
                elif hasattr(platform_instance, 'connect'):
                    init_result = await platform_instance.connect()
                else:
                    return {
                        'success': False,
                        'message': '平台实例没有 initialize() 或 connect() 方法'
                    }
                
                if not init_result:
                    # 如果初始化失败，检查是否已连接但未认证
                    if hasattr(platform_instance, 'is_connected') and platform_instance.is_connected:
                        # 已连接但未认证，继续检查认证状态（会在下面处理）
                        logger.info("平台已连接但未认证，将尝试登录流程")
                    elif hasattr(platform_instance, 'is_connected') and not platform_instance.is_connected:
                        # 连接失败
                        await platform_instance.disconnect()
                        return {
                            'success': False,
                            'message': '平台连接失败，请检查网络或配置'
                        }
                    else:
                        # 其他初始化失败
                        await platform_instance.disconnect()
                        return {
                            'success': False,
                            'message': '平台初始化失败，请检查配置（api_id、api_hash、session_string等）'
                        }
            except Exception as e:
                logger.error(f"平台初始化异常: {e}")
                import traceback
                logger.error(traceback.format_exc())
                try:
                    await platform_instance.disconnect()
                except:
                    pass
                return {
                    'success': False,
                    'message': f'平台初始化异常: {str(e)}'
                }
            
            # 检查认证状态 - 如果未认证但有手机号，尝试自动登录
            if hasattr(platform_instance, 'is_authenticated') and not platform_instance.is_authenticated:
                logger.info(f"平台未认证，检查是否有手机号: {hasattr(platform_instance, 'phone') and platform_instance.phone}")
                # 如果有手机号，尝试发送验证码
                if hasattr(platform_instance, 'phone') and platform_instance.phone:
                    try:
                        logger.info(f"尝试发送验证码到 {platform_instance.phone}")
                        # 尝试发送验证码（不传phone_code参数，会自动发送验证码）
                        login_result = await platform_instance.login()
                        
                        # 获取 phone_code_hash（如果已保存）
                        phone_code_hash = None
                        if hasattr(platform_instance, '_phone_code_hash'):
                            phone_code_hash = platform_instance._phone_code_hash
                        
                        # 保存 phone_code_hash 到数据库的 config 中（临时存储）
                        if phone_code_hash:
                            updated_config = platform_data['config'].copy()
                            updated_config['_temp_phone_code_hash'] = phone_code_hash
                            # 更新数据库（临时保存 phone_code_hash）
                            self.db.update_platform(platform_id, {
                                'config': updated_config
                            })
                            logger.info(f"[test_platform] 已保存 phone_code_hash 到数据库（临时）: {phone_code_hash[:10] if phone_code_hash else 'N/A'}...")
                        else:
                            logger.warning("[test_platform] 未能获取 phone_code_hash")
                        
                        logger.info(f"登录结果: {login_result}")
                        if login_result is False:  # 需要验证码（这是正常情况）
                            logger.info("需要登录，建议使用命令行工具")
                            await platform_instance.disconnect()
                            return {
                                'success': False,
                                'message': f'该平台需要登录。\n\n由于技术限制，请使用命令行工具：\n\npython telegram_platform_login.py {platform_id}\n\n完成登录后即可正常使用。',
                                'needs_manual_login': True,
                                'platform_id': platform_id
                            }
                        elif login_result is True:
                            # 已经登录成功（可能session_string有效）
                            logger.info("登录成功，继续测试")
                            # 继续执行测试流程
                        else:
                            logger.warning(f"登录返回未知结果: {login_result}")
                            await platform_instance.disconnect()
                            return {
                                'success': False,
                                'message': '登录失败',
                                'needs_login': True,
                                'phone': platform_instance.phone
                            }
                    except Exception as e:
                        logger.error(f"发送验证码失败: {e}")
                        import traceback
                        logger.error(traceback.format_exc())
                        await platform_instance.disconnect()
                        return {
                            'success': False,
                            'message': f'发送验证码失败: {str(e)}',
                            'needs_login': True,
                            'phone': platform_instance.phone if hasattr(platform_instance, 'phone') else None
                        }
                else:
                    logger.warning("平台未认证且没有手机号配置")
                    await platform_instance.disconnect()
                    return {
                        'success': False,
                        'message': '平台未认证，请先完成登录（需要配置phone或session_string）',
                        'needs_login': True,
                        'needs_phone': True
                    }
            
            # 钉钉平台特殊处理：直接发送测试消息
            if platform_data['platform_type'] == 'dingtalk':
                logger.info("钉钉平台测试：发送测试消息")
                try:
                    from core.message_forward.models import Message, MessageType
                    # 获取中国时区时间（UTC+8）
                    china_tz = timezone(timedelta(hours=8))
                    local_time = datetime.now(china_tz)
                    test_message = Message(
                        content="[测试] 钉钉消息转发系统连接测试\n测试时间: " + local_time.strftime("%Y-%m-%d %H:%M:%S"),
                        message_type=MessageType.TEXT
                    )
                    
                    send_result = await platform_instance.send_message("", test_message)
                    await platform_instance.disconnect()
                    
                    if send_result:
                        # 返回符合前端期望的格式
                        # 使用中国时区时间
                        china_tz = timezone(timedelta(hours=8))
                        local_time = datetime.now(china_tz)
                        test_msg = {
                            'content': test_message.content,
                            'timestamp': local_time.isoformat(),
                            'chat_id': '',
                            'chat_title': '钉钉群'
                        }
                        return {
                            'success': True,
                            'message': '✅ 钉钉测试消息发送成功！',
                            'data': {
                                'messages_count': 1,
                                'messages': [test_msg],
                                'platform_name': platform_data['platform_name']
                            }
                        }
                    else:
                        return {
                            'success': False,
                            'message': '钉钉测试消息发送失败，请检查 webhook_url 和 secret 配置是否正确'
                        }
                except Exception as e:
                    logger.error(f"钉钉测试消息发送异常: {e}")
                    import traceback
                    logger.error(traceback.format_exc())
                    try:
                        await platform_instance.disconnect()
                    except:
                        pass
                    return {
                        'success': False,
                        'message': f'钉钉测试失败: {str(e)}'
                    }
            
            # 收集测试消息
            test_messages = []
            
            async def test_message_handler(message_data: Dict[str, Any]):
                """测试消息处理器"""
                # 使用中国时区时间
                china_tz = timezone(timedelta(hours=8))
                default_timestamp = datetime.now(china_tz)
                # 构建统一消息对象
                message = Message(
                    content=message_data.get('text', ''),
                    message_type=MessageType.TEXT,
                    timestamp=message_data.get('date', default_timestamp),
                    source_platform_id=platform_id,
                    source_platform=PlatformType(platform_data['platform_type']) if hasattr(PlatformType, platform_data['platform_type'].upper()) else None,
                    source_chat_id=str(message_data.get('chat_id', '')),
                    source_user_id=str(message_data.get('sender_id', '')),
                    source_username=message_data.get('sender_username'),
                    message_id=str(message_data.get('id', '')),
                    extra_data={
                        'chat_title': message_data.get('chat_title'),
                        'platform': platform_data['platform_type'],
                        'is_test': True
                    }
                )
                
                test_messages.append({
                    'content': message.content[:100],
                    'chat_id': message.source_chat_id,
                    'chat_title': message_data.get('chat_title', ''),
                    'timestamp': message.timestamp.isoformat(),
                    'message_id': message.message_id
                })
                
                # 保存测试消息到历史记录
                try:
                    self.db.add_message_history(
                        message_id=message.message_id or f"test_{len(test_messages)}",
                        source_platform_id=platform_id,
                        source_platform=platform_data['platform_type'],
                        source_chat_id=message.source_chat_id,
                        content=message.content,
                        is_test=True
                    )
                except Exception as e:
                    logger.warning(f"保存测试消息失败: {e}")
            
            # 添加测试消息处理器
            platform_instance.add_message_handler(test_message_handler)
            
            # 获取要监听的群组列表（从monitored_chats配置，测试时也使用）
            monitored_chat_ids = None
            monitored_chats = platform_data.get('monitored_chats')
            if monitored_chats:
                try:
                    if isinstance(monitored_chats, str):
                        monitored_chats_list = json.loads(monitored_chats)
                    else:
                        monitored_chats_list = monitored_chats
                    
                    if monitored_chats_list and isinstance(monitored_chats_list, list):
                        monitored_chat_ids = [str(chat.get('chat_id', '')) for chat in monitored_chats_list if chat.get('chat_id')]
                        if monitored_chat_ids:
                            logger.info(f"测试时将监听 {len(monitored_chat_ids)} 个配置的群组")
                except Exception as e:
                    logger.warning(f"解析monitored_chats失败: {e}")
            
            # 开始监听（测试模式，传递要监听的群组列表）
            logger.info(f"开始测试平台 {platform_data['platform_name']} (ID: {platform_id})，持续 {duration} 秒")
            
            try:
                # 启动监听（传递monitored_chat_ids）
                listen_task = asyncio.create_task(platform_instance.start_listening(monitored_chat_ids=monitored_chat_ids))
                
                # 等待指定时间
                await asyncio.sleep(duration)
                
                # 停止监听
                listen_task.cancel()
                try:
                    await listen_task
                except asyncio.CancelledError:
                    pass
                
                await platform_instance.stop_listening()
                await platform_instance.disconnect()
                
                logger.info(f"平台测试完成，收到 {len(test_messages)} 条测试消息")
                
                return {
                    'success': True,
                    'message': f'测试完成，收到 {len(test_messages)} 条消息',
                    'data': {
                        'platform_id': platform_id,
                        'platform_name': platform_data['platform_name'],
                        'messages_count': len(test_messages),
                        'messages': test_messages[:10],  # 只返回前10条
                        'duration': duration
                    }
                }
                
            except Exception as e:
                logger.error(f"测试过程中出错: {e}")
                try:
                    await platform_instance.stop_listening()
                    await platform_instance.disconnect()
                except:
                    pass
                return {
                    'success': False,
                    'message': f'测试失败: {str(e)}'
                }
            
        except Exception as e:
            logger.error(f"❌ 测试平台失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return {
                'success': False,
                'message': f'测试失败: {str(e)}'
            }
    
    async def _stop_platform_listening(self, platform_id: int):
        """停止平台的监听（内部方法）"""
        # 如果服务正在运行，停止该平台的监听
        if self.is_running and self.listener_service:
            await self.listener_service._stop_platform_listening(platform_id)
    
    async def get_platform_chats(self, platform_id: int) -> Dict[str, Any]:
        """
        获取平台的群组/频道列表（仅支持Telegram等支持此功能的平台）
        
        性能优化：
        - 优先复用已运行的平台实例（避免重复连接）
        - 限制返回数量（避免获取过多数据）
        - 添加超时控制（避免长时间等待）
        
        Args:
            platform_id: 平台ID
        
        Returns:
            群组列表
        """
        try:
            # 获取平台信息
            platform_data = self.db.get_platform_by_id(platform_id)
            if not platform_data:
                return {
                    'success': False,
                    'message': '平台不存在'
                }
            
            # 只支持Telegram平台
            if platform_data['platform_type'] not in ('telegram', 'telegram_mtproto'):
                return {
                    'success': False,
                    'message': f'平台类型 {platform_data["platform_type"]} 不支持获取群组列表'
                }
            
            # 性能优化调整：不复用运行中的实例，避免 event loop 冲突
            # 为了避免复杂的 event loop 管理问题，每次都创建新的临时实例
            platform_instance = None
            should_disconnect = True  # 总是断开临时实例
            
            logger.info(f"为获取群组列表创建临时平台实例 (ID: {platform_id})")
            
            # 创建临时实例（避免复用，防止 event loop 冲突）
            if True:  # 总是创建新实例
                from core.message_forward.platforms import create_platform_instance
                
                platform_instance = create_platform_instance(
                    platform_type=platform_data['platform_type'],
                    config=platform_data['config']
                )
                
                if not platform_instance:
                    return {
                        'success': False,
                        'message': '无法创建平台实例'
                    }
                
                # 初始化平台（兼容不同的方法名）
                init_result = False
                if hasattr(platform_instance, 'initialize'):
                    init_result = await platform_instance.initialize()
                elif hasattr(platform_instance, 'connect'):
                    init_result = await platform_instance.connect()
                
                if not init_result:
                    await platform_instance.disconnect()
                    return {
                        'success': False,
                        'message': '平台初始化失败'
                    }
                
                # 检查认证状态
                if hasattr(platform_instance, 'is_authenticated') and not platform_instance.is_authenticated:
                    await platform_instance.disconnect()
                    return {
                        'success': False,
                        'message': '平台未认证，请先完成登录'
                    }
            
            # 获取群组列表（带超时控制）
            import asyncio
            try:
                logger.info(f"开始获取平台 {platform_id} 的群组列表（超时60秒）...")
                chats = await asyncio.wait_for(
                    platform_instance.get_chats(limit=200),  # 限制数量
                    timeout=60.0  # 60秒超时（Telegram API 可能较慢）
                )
                logger.info(f"成功获取到 {len(chats)} 个群组")
            except asyncio.TimeoutError:
                logger.error(f"获取群组列表超时（60秒）")
                if should_disconnect:
                    try:
                        await platform_instance.disconnect()
                    except:
                        pass
                return {
                    'success': False,
                    'message': '获取群组列表超时（60秒），这可能是因为：\n1. Telegram API 响应慢\n2. 网络连接不稳定\n3. 账号有大量对话\n\n请稍后重试，或联系管理员检查日志。'
                }
            except Exception as e:
                logger.error(f"获取群组列表异常: {e}")
                import traceback
                logger.error(traceback.format_exc())
                if should_disconnect:
                    try:
                        await platform_instance.disconnect()
                    except:
                        pass
                return {
                    'success': False,
                    'message': f'获取群组列表失败: {str(e)}'
                }
            
            # 断开临时创建的连接
            if should_disconnect:
                await platform_instance.disconnect()
                logger.info(f"临时平台实例已断开 (ID: {platform_id})")
            
            # chats 已在 get_chats 中过滤了私聊，直接返回
            logger.info(f"成功获取 {len(chats)} 个群组/频道")
            
            return {
                'success': True,
                'data': chats,
                'message': f'获取到 {len(chats)} 个群组/频道'
            }
            
        except Exception as e:
            logger.error(f"❌ 获取平台群组列表失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return {
                'success': False,
                'message': f'获取失败: {str(e)}'
            }
    
    async def add_monitored_chat(self, platform_id: int, chat_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        添加要监听的群组/频道
        
        Args:
            platform_id: 平台ID
            chat_data: 群组数据
                - chat_id: 群组ID
                - chat_name: 群组名称
                - chat_type: 群组类型 (group/channel)
                - username: 用户名（可选）
        
        Returns:
            操作结果
        """
        try:
            # 获取平台信息
            platform_data = self.db.get_platform_by_id(platform_id)
            if not platform_data:
                return {
                    'success': False,
                    'message': '平台不存在'
                }
            
            # 获取现有的monitored_chats
            monitored_chats = platform_data.get('monitored_chats', [])
            if not isinstance(monitored_chats, list):
                monitored_chats = []
            
            # 检查是否已存在
            chat_id = str(chat_data.get('chat_id', ''))
            existing = [c for c in monitored_chats if str(c.get('chat_id', '')) == chat_id]
            if existing:
                return {
                    'success': False,
                    'message': '该群组已在监听列表中'
                }
            
            # 添加新群组
            monitored_chats.append({
                'chat_id': chat_id,
                'chat_name': chat_data.get('chat_name', ''),
                'chat_type': chat_data.get('chat_type', 'group'),
                'username': chat_data.get('username')
            })
            
            # 更新数据库
            success = self.db.update_platform(platform_id, {
                'monitored_chats': monitored_chats
            })
            
            if success:
                # 如果服务正在运行，重新启动监听以应用新配置
                if self.is_running and self.listener_service:
                    # 先停止
                    await self.listener_service._stop_platform_listening(platform_id)
                    # 再启动（会读取新的monitored_chats配置）
                    await self.listener_service._start_platform_listening(platform_id)
                
                return {
                    'success': True,
                    'message': '群组已添加到监听列表',
                    'data': {
                        'monitored_chats': monitored_chats
                    }
                }
            else:
                return {
                    'success': False,
                    'message': '更新失败'
                }
                
        except Exception as e:
            logger.error(f"❌ 添加监听群组失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return {
                'success': False,
                'message': f'添加失败: {str(e)}'
            }
    
    async def remove_monitored_chat(self, platform_id: int, chat_id: str) -> Dict[str, Any]:
        """
        移除要监听的群组/频道
        
        Args:
            platform_id: 平台ID
            chat_id: 群组ID
        
        Returns:
            操作结果
        """
        try:
            # 获取平台信息
            platform_data = self.db.get_platform_by_id(platform_id)
            if not platform_data:
                return {
                    'success': False,
                    'message': '平台不存在'
                }
            
            # 获取现有的monitored_chats
            monitored_chats = platform_data.get('monitored_chats', [])
            if not isinstance(monitored_chats, list):
                monitored_chats = []
            
            # 移除指定群组
            chat_id_str = str(chat_id)
            original_count = len(monitored_chats)
            monitored_chats = [c for c in monitored_chats if str(c.get('chat_id', '')) != chat_id_str]
            
            if len(monitored_chats) == original_count:
                return {
                    'success': False,
                    'message': '该群组不在监听列表中'
                }
            
            # 更新数据库
            success = self.db.update_platform(platform_id, {
                'monitored_chats': monitored_chats
            })
            
            if success:
                # 如果服务正在运行，重新启动监听以应用新配置
                if self.is_running and self.listener_service:
                    # 先停止
                    await self.listener_service._stop_platform_listening(platform_id)
                    # 再启动（会读取新的monitored_chats配置）
                    await self.listener_service._start_platform_listening(platform_id)
                
                return {
                    'success': True,
                    'message': '群组已从监听列表移除',
                    'data': {
                        'monitored_chats': monitored_chats
                    }
                }
            else:
                return {
                    'success': False,
                    'message': '更新失败'
                }
                
        except Exception as e:
            logger.error(f"❌ 移除监听群组失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return {
                'success': False,
                'message': f'移除失败: {str(e)}'
            }
    
    # ==================== 转发规则管理 ====================
    
    async def add_rule(self, rule_data: Dict[str, Any]) -> Dict[str, Any]:
        """添加转发规则"""
        try:
            rule_id = self.db.add_rule(rule_data)
            
            if not rule_id:
                return {
                    'success': False,
                    'message': '添加规则失败'
                }
            
            # 自动为每个目标平台和群组创建订阅（有效期30天）
            await self._create_subscriptions_for_rule(rule_id, rule_data)
            
            # 如果服务未运行，自动启动服务
            if not self.is_running:
                logger.info("🔄 检测到添加规则，自动启动消息转发服务...")
                start_result = await self.start_service()
                if not start_result.get('success'):
                    logger.warning(f"⚠️ 自动启动服务失败: {start_result.get('message')}")
                    logger.info("💡 请手动启动服务以激活转发规则")
            
            # 如果服务正在运行，动态添加到管理器并更新监听
            if self.is_running and self.manager and rule_data.get('enabled', True):
                try:
                    forward_rule = ForwardRule(
                        rule_id=rule_id,
                        rule_name=rule_data['rule_name'],
                        enabled=True,
                        source_platform_id=rule_data.get('source_platform_id'),  # 新字段
                        source_platform=rule_data.get('source_platform', ''),  # 兼容旧数据
                        source_chat_ids=rule_data.get('source_chat_ids', []),
                        target_platform_ids=rule_data.get('target_platform_ids', []),  # 新增：目标平台实例ID列表
                        target_platforms=rule_data.get('target_platforms', []),  # 保留：兼容旧数据
                        target_chat_ids=rule_data.get('target_chat_ids', {}),
                        keywords=rule_data.get('keywords', []),
                        exclude_keywords=rule_data.get('exclude_keywords', []),
                        add_prefix=rule_data.get('add_prefix', ''),
                        add_suffix=rule_data.get('add_suffix', ''),
                        enable_markdown=rule_data.get('enable_markdown', False)
                    )
                    self.manager.add_forward_rule(forward_rule)
                    
                    # 更新监听服务（根据新规则启动/停止平台监听）
                    if self.listener_service:
                        await self.listener_service._update_listening_platforms()
                        logger.info("✅ 已根据新规则自动更新平台监听状态")
                except Exception as e:
                    logger.warning(f"动态添加规则到管理器失败: {e}")
            
            return {
                'success': True,
                'message': '规则添加成功',
                'data': {'rule_id': rule_id}
            }
            
        except Exception as e:
            logger.error(f"❌ 添加规则失败: {e}")
            return {
                'success': False,
                'message': f'添加失败: {str(e)}'
            }
    
    async def _create_subscriptions_for_rule(self, rule_id: str, rule_data: Dict[str, Any]):
        """
        为规则的所有目标平台和群组创建订阅（有效期30天）
        
        Args:
            rule_id: 规则ID
            rule_data: 规则数据
        """
        try:
            from core.message_forward.invitation_service import SubscriptionService
            subscription_service = SubscriptionService(self.db)
            
            target_platform_ids = rule_data.get('target_platform_ids', [])
            target_chat_ids = rule_data.get('target_chat_ids', {})
            
            # 如果没有target_platform_ids，尝试从target_platforms获取
            if not target_platform_ids:
                target_platforms = rule_data.get('target_platforms', [])
                if target_platforms:
                    # 获取所有平台，查找匹配的平台类型
                    all_platforms = self.db.get_platforms()
                    for platform in all_platforms:
                        if platform.get('platform_type', '').lower() in [pt.lower() for pt in target_platforms]:
                            if platform.get('enabled', False):
                                target_platform_ids.append(platform['id'])
            
            # 为每个目标平台和群组创建订阅
            for platform_id in target_platform_ids:
                # 获取该平台对应的群组列表
                platform_data = self.db.get_platform_by_id(platform_id)
                if not platform_data:
                    continue
                
                platform_type = platform_data.get('platform_type', '').lower()
                chat_ids = target_chat_ids.get(platform_type, []) or target_chat_ids.get('dingtalk', [])
                
                # 如果没有指定chat_ids，使用default
                if not chat_ids:
                    chat_ids = ['default']
                
                for chat_id in chat_ids:
                    try:
                        subscription_service.create_subscription(
                            rule_id=rule_id,
                            target_platform_id=platform_id,
                            target_chat_id=str(chat_id),
                            duration_days=30  # 默认30天有效期
                        )
                        logger.info(f"✅ 已为规则 {rule_id} 创建订阅: 平台ID={platform_id}, 群组={chat_id}")
                    except Exception as e:
                        logger.warning(f"⚠️ 创建订阅失败: 规则ID={rule_id}, 平台ID={platform_id}, 群组={chat_id}, 错误={e}")
        except Exception as e:
            logger.error(f"❌ 为规则创建订阅失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
    
    def get_rules(self, page: int = 1, page_size: int = 20) -> Dict[str, Any]:
        """获取规则列表（支持分页）"""
        try:
            all_rules = self.db.get_rules()
            
            # 分页处理
            total = len(all_rules)
            start = (page - 1) * page_size
            end = start + page_size
            rules = all_rules[start:end]
            
            return {
                'success': True,
                'data': rules,
                'pagination': {
                    'page': page,
                    'page_size': page_size,
                    'total': total,
                    'total_pages': (total + page_size - 1) // page_size if page_size > 0 else 0
                }
            }
        except Exception as e:
            logger.error(f"❌ 获取规则列表失败: {e}")
            return {
                'success': False,
                'message': f'获取失败: {str(e)}'
            }
    
    def get_rule(self, rule_id: str) -> Dict[str, Any]:
        """获取单个规则"""
        try:
            rule = self.db.get_rule_by_id(rule_id)
            if rule:
                return {
                    'success': True,
                    'data': rule
                }
            else:
                return {
                    'success': False,
                    'message': '规则不存在'
                }
        except Exception as e:
            logger.error(f"❌ 获取规则失败: {e}")
            return {
                'success': False,
                'message': f'获取失败: {str(e)}'
            }
    
    async def update_rule(self, rule_id: str, update_data: Dict[str, Any]) -> Dict[str, Any]:
        """更新规则"""
        try:
            success = self.db.update_rule(rule_id, update_data)
            
            if success:
                # 如果更新了目标平台或群组，更新订阅
                if 'target_platform_ids' in update_data or 'target_chat_ids' in update_data:
                    # 获取完整规则数据
                    rule = self.db.get_rule_by_id(rule_id)
                    if rule:
                        # 合并更新数据
                        full_rule_data = dict(rule)
                        full_rule_data.update(update_data)
                        await self._create_subscriptions_for_rule(rule_id, full_rule_data)
                
                return {
                    'success': True,
                    'message': '规则更新成功'
                }
            else:
                return {
                    'success': False,
                    'message': '规则更新失败'
                }
        except Exception as e:
            logger.error(f"❌ 更新规则失败: {e}")
            return {
                'success': False,
                'message': f'更新失败: {str(e)}'
            }
    
    async def delete_rule(self, rule_id: str) -> Dict[str, Any]:
        """删除规则"""
        try:
            success = self.db.delete_rule(rule_id)
            
            if success:
                return {
                    'success': True,
                    'message': '规则删除成功'
                }
            else:
                return {
                    'success': False,
                    'message': '规则不存在'
                }
        except Exception as e:
            logger.error(f"❌ 删除规则失败: {e}")
            return {
                'success': False,
                'message': f'删除失败: {str(e)}'
            }
    
    async def enable_rule(self, rule_id: str) -> Dict[str, Any]:
        """启用规则"""
        try:
            success = self.db.enable_rule(rule_id)
            
            if success:
                # 如果服务正在运行，更新监听服务
                if self.is_running and self.listener_service:
                    await self.listener_service._update_listening_platforms()
                
                return {
                    'success': True,
                    'message': '规则已启用'
                }
            else:
                return {
                    'success': False,
                    'message': '启用失败'
                }
        except Exception as e:
            logger.error(f"❌ 启用规则失败: {e}")
            return {
                'success': False,
                'message': f'启用失败: {str(e)}'
            }
    
    async def disable_rule(self, rule_id: str) -> Dict[str, Any]:
        """禁用规则"""
        try:
            success = self.db.disable_rule(rule_id)
            
            if success:
                # 如果服务正在运行，更新监听服务
                if self.is_running and self.listener_service:
                    await self.listener_service._update_listening_platforms()
                
                return {
                    'success': True,
                    'message': '规则已禁用'
                }
            else:
                return {
                    'success': False,
                    'message': '禁用失败'
                }
        except Exception as e:
            logger.error(f"❌ 禁用规则失败: {e}")
            return {
                'success': False,
                'message': f'禁用失败: {str(e)}'
            }
    
    # ==================== 平台登录 ====================
    
    async def send_login_code(self, platform_id: int) -> Dict[str, Any]:
        """
        发送登录验证码（仅支持Telegram等需要验证码的平台）
        
        Args:
            platform_id: 平台ID
        
        Returns:
            操作结果
        """
        try:
            # 获取平台信息
            platform_data = self.db.get_platform_by_id(platform_id)
            if not platform_data:
                return {
                    'success': False,
                    'message': '平台不存在'
                }
            
            # 只支持Telegram平台
            if platform_data['platform_type'] not in ('telegram', 'telegram_mtproto'):
                return {
                    'success': False,
                    'message': f'平台类型 {platform_data["platform_type"]} 不支持验证码登录'
                }
            
            # 检查是否有手机号
            config = platform_data.get('config', {})
            phone = config.get('phone')
            if not phone:
                return {
                    'success': False,
                    'message': '平台配置中缺少手机号，无法发送验证码'
                }
            
            # 创建临时平台实例
            from core.message_forward.platforms import create_platform_instance
            
            platform_instance = create_platform_instance(
                platform_type=platform_data['platform_type'],
                config=config
            )
            
            if not platform_instance:
                return {
                    'success': False,
                    'message': '无法创建平台实例'
                }
            
            # 初始化平台（兼容不同的方法名）
            init_result = False
            if hasattr(platform_instance, 'initialize'):
                init_result = await platform_instance.initialize()
            elif hasattr(platform_instance, 'connect'):
                init_result = await platform_instance.connect()
            
            if not init_result:
                await platform_instance.disconnect()
                return {
                    'success': False,
                    'message': '平台初始化失败'
                }
            
            # 发送验证码
            try:
                login_result = await platform_instance.login()
                
                # 获取 phone_code_hash（如果已保存）
                phone_code_hash = None
                if hasattr(platform_instance, '_phone_code_hash'):
                    phone_code_hash = platform_instance._phone_code_hash
                
                # 保存 phone_code_hash 到数据库的 config 中（临时存储）
                if phone_code_hash:
                    updated_config = config.copy()
                    updated_config['_temp_phone_code_hash'] = phone_code_hash
                    # 更新数据库（临时保存 phone_code_hash）
                    self.db.update_platform(platform_id, {
                        'config': updated_config
                    })
                    logger.info(f"已保存 phone_code_hash 到数据库（临时）")
                
                await platform_instance.disconnect()
                
                if login_result is False:  # 需要验证码（这是正常情况）
                    # 注意：跨 HTTP 请求缓存实例会导致 event loop 错误
                    # 建议使用独立的登录脚本 telegram_platform_login.py
                    
                    return {
                        'success': True,
                        'message': f'需要使用命令行工具完成登录',
                        'manual_login_required': True,
                        'manual_login_command': f'python telegram_platform_login.py {platform_id}',
                        'platform_id': platform_id
                    }
                elif login_result is True:
                    # 已经登录成功（可能session_string有效）
                    await platform_instance.disconnect()
                    return {
                        'success': True,
                        'message': '平台已认证，无需登录',
                        'authenticated': True
                    }
                else:
                    await platform_instance.disconnect()
                    return {
                        'success': False,
                        'message': '发送验证码失败'
                    }
            except Exception as e:
                await platform_instance.disconnect()
                logger.error(f"发送验证码异常: {e}")
                import traceback
                logger.error(traceback.format_exc())
                return {
                    'success': False,
                    'message': f'发送验证码失败: {str(e)}'
                }
                
        except Exception as e:
            logger.error(f"❌ 发送登录验证码失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return {
                'success': False,
                'message': f'发送验证码失败: {str(e)}'
            }
    
    async def verify_login_code(self, platform_id: int, phone_code: str, password: Optional[str] = None) -> Dict[str, Any]:
        """
        验证登录验证码并完成登录
        
        Args:
            platform_id: 平台ID
            phone_code: 手机验证码
            password: 两步验证密码（如果需要）
        
        Returns:
            操作结果，包含session_string（如果登录成功）
        """
        try:
            # 获取平台信息
            platform_data = self.db.get_platform_by_id(platform_id)
            if not platform_data:
                return {
                    'success': False,
                    'message': '平台不存在'
                }
            
            # 只支持Telegram平台
            if platform_data['platform_type'] not in ('telegram', 'telegram_mtproto'):
                return {
                    'success': False,
                    'message': f'平台类型 {platform_data["platform_type"]} 不支持验证码登录'
                }
            
            # Web 界面不支持验证验证码（event loop 限制）
            return {
                'success': False,
                'message': f'由于技术限制，Web 界面无法完成 Telegram 登录验证。\n\n请使用命令行工具：\n\npython telegram_platform_login.py {platform_id}\n\n该工具会引导您完成整个登录流程。',
                'needs_manual_login': True,
                'platform_id': platform_id
            }
            
            # 验证验证码并登录
            try:
                # 确保客户端已连接
                if not platform_instance.is_connected:
                    logger.error("客户端未连接，无法验证验证码")
                    await platform_instance.disconnect()
                    return {
                        'success': False,
                        'message': '客户端未连接，请重新发送验证码',
                        'step': 'phone_code',
                        'needs_resend': True
                    }
                
                # 从数据库 config 中获取之前保存的 phone_code_hash
                # 注意：平台实例创建时已经从 config 中读取了 _temp_phone_code_hash
                temp_phone_code_hash = platform_data['config'].get('_temp_phone_code_hash')
                if temp_phone_code_hash:
                    logger.info(f"数据库中有保存的 phone_code_hash: {temp_phone_code_hash[:10]}...")
                    logger.info(f"平台实例中的 phone_code_hash: {platform_instance._phone_code_hash[:10] if platform_instance._phone_code_hash else 'None'}...")
                else:
                    logger.warning("数据库中没有 phone_code_hash，需要重新发送验证码")
                    # 重新发送验证码
                    try:
                        await platform_instance.login()  # 不传 phone_code，会发送验证码
                        # 获取新的 phone_code_hash 并保存
                        if hasattr(platform_instance, '_phone_code_hash') and platform_instance._phone_code_hash:
                            updated_config = platform_data['config'].copy()
                            updated_config['_temp_phone_code_hash'] = platform_instance._phone_code_hash
                            self.db.update_platform(platform_id, {
                                'config': updated_config
                            })
                            logger.info("已重新发送验证码并保存 phone_code_hash")
                            await platform_instance.disconnect()
                            return {
                                'success': False,
                                'message': '验证码已过期，已重新发送验证码，请使用新的验证码',
                                'step': 'phone_code',
                                'needs_resend': True,
                                'phone': platform_data['config'].get('phone')
                            }
                    except Exception as send_error:
                        logger.error(f"重新发送验证码失败: {send_error}")
                        await platform_instance.disconnect()
                        return {
                            'success': False,
                            'message': '无法发送验证码，请稍后重试',
                            'step': 'phone_code'
                        }
                
                # 现在尝试验证验证码
                try:
                    login_result = await platform_instance.login(phone_code=phone_code, password=password)
                except ValueError as e:
                    error_str = str(e)
                    # 检查是否是验证码过期或 phone_code_hash 缺失错误
                    if 'PHONE_CODE_EXPIRED' in error_str or 'PHONE_CODE_HASH_MISSING' in error_str:
                        if 'PHONE_CODE_EXPIRED' in error_str:
                            logger.warning("检测到验证码已过期，重新发送验证码")
                        else:
                            logger.warning("检测到 phone_code_hash 缺失，重新发送验证码")
                        
                        # 重新发送验证码
                        try:
                            await platform_instance.login()  # 不传 phone_code，会发送验证码
                            
                            # 获取新的 phone_code_hash 并保存
                            if hasattr(platform_instance, '_phone_code_hash') and platform_instance._phone_code_hash:
                                updated_config = platform_data['config'].copy()
                                updated_config['_temp_phone_code_hash'] = platform_instance._phone_code_hash
                                self.db.update_platform(platform_id, {
                                    'config': updated_config
                                })
                                logger.info("已重新发送验证码并保存新的 phone_code_hash")
                            
                            await platform_instance.disconnect()
                            return {
                                'success': False,
                                'message': '验证码已过期，已重新发送新的验证码，请使用新的验证码',
                                'step': 'phone_code',
                                'needs_resend': True,
                                'phone': platform_data['config'].get('phone')
                            }
                        except Exception as resend_error:
                            logger.error(f"重新发送验证码失败: {resend_error}")
                            await platform_instance.disconnect()
                            return {
                                'success': False,
                                'message': f'验证失败，且无法重新发送验证码: {str(resend_error)}',
                                'step': 'phone_code'
                            }
                    else:
                        raise
                
                if login_result:
                    # 登录成功，获取session_string
                    session_string = await platform_instance.get_session_string()
                    
                    if session_string:
                        # 更新数据库中的session_string，并清理临时的 phone_code_hash
                        updated_config = platform_data['config'].copy()
                        updated_config['session_string'] = session_string
                        # 清理临时的 phone_code_hash
                        updated_config.pop('_temp_phone_code_hash', None)
                        
                        # 更新平台配置
                        self.db.update_platform(platform_id, {
                            'config': updated_config
                        })
                        
                        logger.info(f"✅ 平台 {platform_id} 登录成功，session_string已保存，临时数据已清理")
                        
                        # 清理缓存的实例
                        if platform_id in self._login_instances:
                            del self._login_instances[platform_id]
                            logger.info(f"清理缓存的平台实例 {platform_id}")
                        
                        await platform_instance.disconnect()
                        return {
                            'success': True,
                            'message': '登录成功，session_string已保存',
                            'authenticated': True
                        }
                    else:
                        # 清理缓存的实例
                        if platform_id in self._login_instances:
                            del self._login_instances[platform_id]
                        await platform_instance.disconnect()
                        return {
                            'success': False,
                            'message': '登录成功，但无法获取session_string'
                        }
                else:
                    # 验证失败，清理缓存并断开
                    if platform_id in self._login_instances:
                        del self._login_instances[platform_id]
                    await platform_instance.disconnect()
                    return {
                        'success': False,
                        'message': '验证码错误或登录失败',
                        'step': 'phone_code'  # 需要重新输入验证码
                    }
                    
            except ValueError as ve:
                # 检查是否是 phone_code_hash 缺失错误（如果内层没有捕获到）
                if 'PHONE_CODE_HASH_MISSING' in str(ve):
                    logger.warning("外层捕获到 phone_code_hash 缺失，重新发送验证码")
                    try:
                        await platform_instance.login()  # 不传 phone_code，会发送验证码
                        await platform_instance.disconnect()
                        return {
                            'success': False,
                            'message': '验证码已过期，已重新发送验证码，请使用新的验证码',
                            'step': 'phone_code',
                            'needs_resend': True,
                            'phone': platform_data['config'].get('phone')
                        }
                    except Exception as resend_error:
                        logger.error(f"重新发送验证码失败: {resend_error}")
                        await platform_instance.disconnect()
                        return {
                            'success': False,
                            'message': f'验证失败，且无法重新发送验证码: {str(ve)}',
                            'step': 'phone_code'
                        }
                else:
                    # 其他 ValueError，继续抛出
                    raise
            except Exception as e:
                await platform_instance.disconnect()
                logger.error(f"验证验证码异常: {e}")
                import traceback
                logger.error(traceback.format_exc())
                
                # 检查是否是两步验证错误
                from telethon.errors import SessionPasswordNeededError
                if isinstance(e, SessionPasswordNeededError):
                    return {
                        'success': False,
                        'message': '需要两步验证密码',
                        'step': 'password'  # 需要输入两步验证密码
                    }
                
                # 检查是否是 phone_code_hash 相关错误
                error_msg = str(e)
                if 'phone_code_hash' in error_msg.lower():
                    logger.warning("检测到 phone_code_hash 错误，尝试重新发送验证码")
                    try:
                        # 重新初始化并发送验证码（兼容不同的方法名）
                        if hasattr(platform_instance, 'initialize'):
                            await platform_instance.initialize()
                        elif hasattr(platform_instance, 'connect'):
                            await platform_instance.connect()
                        await platform_instance.login()  # 不传 phone_code，会发送验证码
                        await platform_instance.disconnect()
                        return {
                            'success': False,
                            'message': '验证码已过期，已重新发送验证码，请使用新的验证码',
                            'step': 'phone_code',
                            'needs_resend': True,
                            'phone': platform_data['config'].get('phone')
                        }
                    except Exception as resend_error:
                        logger.error(f"重新发送验证码失败: {resend_error}")
                        await platform_instance.disconnect()
                        return {
                            'success': False,
                            'message': f'验证失败: {str(e)}',
                            'step': 'phone_code'
                        }
                
                return {
                    'success': False,
                    'message': f'验证失败: {str(e)}'
                }
                
        except Exception as e:
            logger.error(f"❌ 验证登录验证码失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return {
                'success': False,
                'message': f'验证失败: {str(e)}'
            }
    
    # ==================== 消息历史 ====================
    
    def get_message_history(self, page: int = 1, page_size: int = 20) -> Dict[str, Any]:
        """获取消息历史（支持分页）"""
        try:
            # 获取总数（需要查询数据库获取总数）
            all_messages = self.db.get_message_history(limit=10000)  # 获取足够多的数据用于分页
            total = len(all_messages)
            
            # 分页处理
            start = (page - 1) * page_size
            end = start + page_size
            messages = all_messages[start:end]
            
            return {
                'success': True,
                'data': messages,
                'pagination': {
                    'page': page,
                    'page_size': page_size,
                    'total': total,
                    'total_pages': (total + page_size - 1) // page_size if page_size > 0 else 0
                }
            }
        except Exception as e:
            logger.error(f"❌ 获取消息历史失败: {e}")
            return {
                'success': False,
                'message': f'获取失败: {str(e)}'
            }


# 全局实例
_service_instance: Optional[MessageForwardAPIService] = None


def get_message_forward_service(db_pool=None, force_reload: bool = False) -> MessageForwardAPIService:
    """
    获取全局服务实例
    
    Args:
        db_pool: MySQL连接池实例（可选）
        force_reload: 是否强制重新创建实例（用于代码更新后重新加载）
    """
    global _service_instance
    if _service_instance is None or force_reload:
        _service_instance = MessageForwardAPIService(db_pool)
    return _service_instance

