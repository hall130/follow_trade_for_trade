#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
统一监听服务管理器
根据转发规则自动管理平台监听
"""

import asyncio
from typing import Dict, List, Optional, Set, Any
from datetime import datetime
from utils.logger import get_logger

from .manager import MessageForwardManager
from .models import ForwardRule, Message, MessageType, PlatformType
from .platforms import create_platform_instance

logger = get_logger(__name__)


class UnifiedListenerService:
    """统一监听服务管理器"""
    
    def __init__(self, forward_manager: MessageForwardManager, db):
        """
        初始化统一监听服务
        
        Args:
            forward_manager: 消息转发管理器
            db: 数据库操作实例
        """
        self.forward_manager = forward_manager
        self.db = db
        
        # 平台监听状态：platform_id -> platform_instance
        self.listening_platforms: Dict[int, Any] = {}
        
        # 平台ID到平台类型的映射
        self.platform_id_to_type: Dict[int, str] = {}
        
        # 平台监听任务：platform_id -> asyncio.Task
        self.listening_tasks: Dict[int, asyncio.Task] = {}
        
        # 运行状态
        self.running = False
        
        logger.info("统一监听服务管理器初始化完成")
    
    async def start(self):
        """启动监听服务"""
        if self.running:
            logger.warning("监听服务已在运行")

            return
        
        logger.info("🚀 启动统一监听服务...")

        self.running = True
        
        # 根据启用的转发规则启动平台监听
        await self._update_listening_platforms()
        
        logger.info("✅ 统一监听服务已启动")
    
    async def stop(self):
        """停止监听服务"""
        if not self.running:
            return
        
        logger.info("🛑 停止统一监听服务...")

        self.running = False
        
        # 取消所有监听任务
        for platform_id, listen_task in list(self.listening_tasks.items()):
            try:
                if not listen_task.done():
                    logger.info(f"🛑 [监听服务] 正在取消监听任务 (平台ID: {platform_id})")
                    listen_task.cancel()
                    try:
                        await asyncio.wait_for(listen_task, timeout=2.0)
                    except (asyncio.CancelledError, asyncio.TimeoutError):
                        logger.info(f"✅ [监听服务] 监听任务已取消 (平台ID: {platform_id})")
            except Exception as e:
                logger.error(f"取消监听任务失败 (ID: {platform_id}): {e}")
        
        self.listening_tasks.clear()
        
        # 停止所有平台监听
        for platform_id, platform_instance in list(self.listening_platforms.items()):
            try:
                if hasattr(platform_instance, 'stop_listening'):
                    await platform_instance.stop_listening()
                if hasattr(platform_instance, 'disconnect'):
                    await platform_instance.disconnect()
                logger.info(f"已停止平台监听 (ID: {platform_id})")
            except Exception as e:
                logger.error(f"停止平台监听失败 (ID: {platform_id}): {e}")
        
        self.listening_platforms.clear()
        self.platform_id_to_type.clear()
        
        logger.info("✅ 统一监听服务已停止")

    async def _update_listening_platforms(self):
        """
        根据转发规则更新监听平台
        启动需要监听的平台，停止不再需要的平台
        """
        try:
            logger.info("🔄 开始更新监听平台配置...")

            # 获取所有启用的转发规则
            rules = self.db.get_rules()
            enabled_rules = [r for r in rules if r.get('enabled', False)]
            
            logger.info(f"📋 找到 {len(rules)} 个转发规则，其中 {len(enabled_rules)} 个已启用")
            
            if not enabled_rules:
                logger.warning("⚠️ 没有启用的转发规则，不会启动任何平台监听")

                return
            
            # 收集需要监听的源平台ID和需要连接的目标平台
            required_platform_ids: Set[int] = set()  # 需要监听的源平台ID
            required_target_platform_ids: Set[int] = set()  # 需要连接的目标平台ID（用于转发消息）
            target_platform_types: Set[str] = set()  # 记录需要的目标平台类型
            
            for rule in enabled_rules:
                rule_name = rule.get('rule_name', '未知规则')
                logger.debug(f"📝 处理规则: {rule_name}")
                # 源平台ID（需要监听）
                source_platform_id = rule.get('source_platform_id')
                if source_platform_id:
                    required_platform_ids.add(source_platform_id)
                # 兼容旧规则：如果没有platform_id，使用platform_type
                elif rule.get('source_platform'):
                    # 对于旧规则，需要找到对应的平台ID
                    # 这里暂时跳过，因为需要知道具体是哪个平台账户
                    pass
                
                # 收集目标平台实例ID（优先使用）
                target_platform_ids = rule.get('target_platform_ids', [])
                if target_platform_ids:
                    # 直接使用指定的平台实例ID
                    for platform_id in target_platform_ids:
                        required_target_platform_ids.add(platform_id)  # 记录目标平台ID
                        if platform_id not in required_platform_ids:
                            if platform_id not in self.listening_platforms:
                                await self._init_target_platform(platform_id)
                else:
                    # 兼容旧规则：如果没有target_platform_ids，使用target_platforms（平台类型）
                    target_platforms = rule.get('target_platforms', [])
                    if target_platforms:
                        target_platform_types = set(target_platforms)
                        # 为目标平台找到对应的平台ID并准备连接
                        all_platforms = self.db.get_platforms()
                        for platform in all_platforms:
                            if platform.get('enabled') and platform['platform_type'] in target_platform_types:
                                platform_id = platform['id']
                                required_target_platform_ids.add(platform_id)  # 记录目标平台ID
                                # 如果这个平台不是源平台，也要初始化它（但不启动监听）
                                if platform_id not in required_platform_ids:
                                    if platform_id not in self.listening_platforms:
                                        await self._init_target_platform(platform_id)
            
            logger.info(f"🎯 需要监听的源平台ID: {required_platform_ids}")
            logger.info(f"🎯 需要连接的目标平台ID: {required_target_platform_ids}")
            logger.info(f"🎯 需要连接的目标平台类型: {target_platform_types}")


            # 启动需要监听但未启动的平台
            for platform_id in required_platform_ids:
                if platform_id not in self.listening_platforms:
                    logger.info(f"🚀 启动平台监听 (ID: {platform_id})")
                    await self._start_platform_listening(platform_id)
                else:
                    logger.info(f"ℹ️ 平台已在监听中 (ID: {platform_id})")
            
            # 停止不再需要的平台监听（排除目标平台，因为它们需要用于转发消息）
            # 只停止那些既不是源平台也不是目标平台的平台
            platforms_to_stop = [
                pid for pid in self.listening_platforms.keys() 
                if pid not in required_platform_ids and pid not in required_target_platform_ids
            ]
            if platforms_to_stop:
                logger.info(f"🛑 需要停止监听的平台: {platforms_to_stop}")

                for platform_id in platforms_to_stop:
                    await self._stop_platform_listening(platform_id)
            
            logger.info(f"✅ 监听平台配置更新完成，当前监听平台数: {len(self.listening_platforms)}")
            
        except Exception as e:
            logger.error(f"❌ 更新监听平台失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
    
    async def _start_platform_listening(self, platform_id: int):
        """启动平台监听"""
        try:
            logger.info(f"🔍 开始启动平台监听 (ID: {platform_id})")
            
            # 获取平台信息
            platform_data = self.db.get_platform_by_id(platform_id)
            if not platform_data:
                error_msg = f"平台不存在 (ID: {platform_id})"
                logger.error(error_msg)

                return False
            
            
            if not platform_data.get('enabled', False):
                error_msg = f"平台未启用 (ID: {platform_id})"
                logger.warning(error_msg)

                return False
            
            # 创建平台实例
            platform_instance = create_platform_instance(
                platform_type=platform_data['platform_type'],
                config=platform_data['config']
            )
            
            if not platform_instance:
                error_msg = f"不支持的平台类型: {platform_data['platform_type']}"
                logger.error(error_msg)

                return False
            
            # 初始化平台（兼容不同的方法名）

            init_success = False
            if hasattr(platform_instance, 'initialize'):
                init_success = await platform_instance.initialize()
            elif hasattr(platform_instance, 'connect'):
                init_success = await platform_instance.connect()
            else:
                error_msg = f"平台实例没有 initialize() 或 connect() 方法"
                logger.error(error_msg)

                return False
            
            if not init_success:
                error_msg = f"平台初始化失败 (ID: {platform_id})"
                logger.error(error_msg)

                return False

            # 检查认证状态（仅对需要认证的平台）
            if hasattr(platform_instance, 'is_authenticated'):
                if not platform_instance.is_authenticated:
                    error_msg = f"平台未认证 (ID: {platform_id})"
                    logger.error(error_msg)
                    await platform_instance.disconnect()
                    return False
            
            # 添加消息处理器（使用闭包确保platform_id被正确捕获）
            async def message_handler_wrapper(msg_data):
                """消息处理器包装器，确保platform_id被正确捕获"""
                try:
                    logger.info(f"🔄 消息处理器被调用 (平台ID: {platform_id})")
                    await self._handle_platform_message(platform_id, msg_data)
                except Exception as e:
                    error_msg = f"❌ 消息处理器执行失败 (平台ID: {platform_id}): {e}"
                    logger.error(error_msg)

                    import traceback
                    logger.error(traceback.format_exc())
            
            platform_instance.add_message_handler(message_handler_wrapper)
            logger.info(f"📝 已注册消息处理器 (平台ID: {platform_id})")
            
            # 获取要监听的群组列表（从monitored_chats配置）
            monitored_chat_ids = None
            monitored_chats = platform_data.get('monitored_chats')
            if monitored_chats:
                try:
                    import json
                    if isinstance(monitored_chats, str):
                        monitored_chats_list = json.loads(monitored_chats)
                    else:
                        monitored_chats_list = monitored_chats
                    
                    if monitored_chats_list and isinstance(monitored_chats_list, list):
                        # 提取chat_id列表
                        monitored_chat_ids = [str(chat.get('chat_id', '')) for chat in monitored_chats_list if chat.get('chat_id')]
                        if monitored_chat_ids:
                            logger.info(f"平台 {platform_data['platform_name']} 配置了 {len(monitored_chat_ids)} 个监听群组")
                except Exception as e:
                    logger.warning(f"解析monitored_chats失败: {e}")
            
            # 启动监听（在后台任务中，传递要监听的群组列表）
            listen_info = f"ID: {platform_id}, 名称: {platform_data['platform_name']}, 监听群组数: {len(monitored_chat_ids) if monitored_chat_ids else '全部'}"
            logger.info(f"准备启动平台监听任务 ({listen_info})")
            
            try:
                # 创建监听任务
                listen_task = asyncio.create_task(platform_instance.start_listening(monitored_chat_ids=monitored_chat_ids))
                
                # 添加任务完成回调
                def task_done_callback(task):
                    try:
                        if task.cancelled():
                            logger.warning(f"监听任务被取消 (平台ID: {platform_id})")
                        elif task.exception():
                            logger.error(f"监听任务异常 (平台ID: {platform_id}): {task.exception()}")
                    except Exception as e:
                        logger.error(f"任务回调异常: {e}")
                
                listen_task.add_done_callback(task_done_callback)
                
                # 保存任务引用，防止被垃圾回收
                self.listening_tasks[platform_id] = listen_task
                
                # 让事件循环有机会调度刚创建的任务
                await asyncio.sleep(0)
            except Exception as task_error:
                error_msg = f"创建监听任务失败: {task_error}"
                logger.error(error_msg)

                import traceback
                logger.error(traceback.format_exc())
                return False
            
            # 保存平台实例
            self.listening_platforms[platform_id] = platform_instance
            self.platform_id_to_type[platform_id] = platform_data['platform_type']
            
            success_msg = f"✅ 已启动平台监听 (ID: {platform_id}, 名称: {platform_data['platform_name']})"
            logger.info(success_msg)

            return True
            
        except Exception as e:
            error_msg = f"启动平台监听失败 (ID: {platform_id}): {e}"
            logger.error(error_msg)

            import traceback
            logger.error(traceback.format_exc())
            return False
    
    async def _init_target_platform(self, platform_id: int):
        """
        初始化目标平台（仅连接，不启动监听）
        用于准备发送消息的目标平台，如钉钉、微信等
        """
        try:
            # 获取平台信息
            platform_data = self.db.get_platform_by_id(platform_id)
            if not platform_data:
                logger.error(f"平台不存在 (ID: {platform_id})")
                return False
            
            if not platform_data.get('enabled', False):
                logger.warning(f"平台未启用 (ID: {platform_id})")
                return False
            
            # 创建平台实例
            platform_instance = create_platform_instance(
                platform_type=platform_data['platform_type'],
                config=platform_data['config']
            )
            
            if not platform_instance:
                logger.error(f"不支持的平台类型: {platform_data['platform_type']}")
                return False
            
            # 初始化平台连接（但不启动监听）
            # 兼容不同平台的方法名：Telegram 用 initialize()，其他用 connect()
            init_success = False
            if hasattr(platform_instance, 'initialize'):
                init_success = await platform_instance.initialize()
            elif hasattr(platform_instance, 'connect'):
                init_success = await platform_instance.connect()
            else:
                logger.error(f"平台实例没有 initialize() 或 connect() 方法")
                return False
            
            if not init_success:
                logger.warning(f"目标平台初始化失败 (ID: {platform_id})，将在发送消息时重试")
                # 对于目标平台，即使初始化失败也保存实例，在发送时可以重试
            
            # 保存平台实例
            self.listening_platforms[platform_id] = platform_instance
            self.platform_id_to_type[platform_id] = platform_data['platform_type']
            
            logger.info(f"✅ 已初始化目标平台 (ID: {platform_id}, 名称: {platform_data['platform_name']}, 类型: {platform_data['platform_type']})")
            return True
            
        except Exception as e:
            logger.error(f"初始化目标平台失败 (ID: {platform_id}): {e}")
            import traceback
            logger.error(traceback.format_exc())
            return False
    
    async def _stop_platform_listening(self, platform_id: int):
        """停止平台监听"""
        try:
            # 取消监听任务
            if platform_id in self.listening_tasks:
                listen_task = self.listening_tasks[platform_id]
                if not listen_task.done():
                    logger.info(f"🛑 [监听服务] 正在取消监听任务 (平台ID: {platform_id})")
                    listen_task.cancel()
                    try:
                        await asyncio.wait_for(listen_task, timeout=2.0)
                    except (asyncio.CancelledError, asyncio.TimeoutError):
                        logger.info(f"✅ [监听服务] 监听任务已取消 (平台ID: {platform_id})")
                del self.listening_tasks[platform_id]
            
            if platform_id not in self.listening_platforms:
                return True
            
            platform_instance = self.listening_platforms[platform_id]
            
            # 停止监听（如果平台支持）
            if hasattr(platform_instance, 'stop_listening'):
                try:
                    await platform_instance.stop_listening()
                except Exception as e:
                    logger.warning(f"停止平台监听失败 (ID: {platform_id}): {e}")
            else:
                logger.debug(f"平台 (ID: {platform_id}) 不支持 stop_listening 方法，跳过")
            
            # 断开连接
            if hasattr(platform_instance, 'disconnect'):
                try:
                    await platform_instance.disconnect()
                except Exception as e:
                    logger.warning(f"断开平台连接失败 (ID: {platform_id}): {e}")
            
            # 移除
            del self.listening_platforms[platform_id]
            if platform_id in self.platform_id_to_type:
                del self.platform_id_to_type[platform_id]
            
            logger.info(f"✅ 已停止平台监听 (ID: {platform_id})")
            return True
            
        except Exception as e:
            logger.error(f"停止平台监听失败 (ID: {platform_id}): {e}")
            return False
    
    async def _handle_platform_message(self, platform_id: int, message_data: Dict[str, Any]):
        """处理平台消息"""
        try:
            logger.info(f"📥 开始处理平台消息 (平台ID: {platform_id})")
            
            # 构建统一消息对象
            platform_type_str = self.platform_id_to_type.get(platform_id, '')
            
            try:
                platform_type = PlatformType(platform_type_str)
            except (ValueError, AttributeError):
                platform_type = None
            
            message = Message(
                content=message_data.get('text', ''),
                message_type=MessageType.TEXT,
                timestamp=message_data.get('date', datetime.now()),
                source_platform_id=platform_id,
                source_platform=platform_type,
                source_chat_id=str(message_data.get('chat_id', '')),
                source_chat_title=message_data.get('chat_title'),
                source_user_id=str(message_data.get('sender_id', '')),
                source_username=message_data.get('sender_username'),
                message_id=str(message_data.get('id', '')),
                extra_data={
                    'platform': platform_type_str
                }
            )
            
            logger.info(f"📨 收到消息 (平台ID: {platform_id}, 聊天ID: {message.source_chat_id}, 内容: {message.content[:50]}...)")
            
            # 应用转发规则
            matched_rules = []
            matched_rule_ids = []
            for rule_id, rule in self.forward_manager.forward_rules.items():
                if rule.enabled and rule.matches(message):
                    matched_rules.append(rule)
                    matched_rule_ids.append(rule_id)
                    logger.info(f"✅ 消息匹配规则: {rule.rule_name} (ID: {rule_id})")
            
            # 保存到历史记录（只保存一次，如果匹配到规则则记录rule_id）
            try:
                rule_id_to_save = matched_rule_ids[0] if matched_rule_ids else None
                history_id = self.db.add_message_history(
                    message_id=message.message_id,
                    source_platform_id=platform_id,
                    source_platform=platform_type_str,
                    source_chat_id=message.source_chat_id,
                    source_chat_title=message.source_chat_title,
                    content=message.content,
                    is_test=False,
                    rule_id=rule_id_to_save
                )
                if history_id:
                    logger.info(f"💾 消息已保存到历史 (历史ID: {history_id}, 规则ID: {rule_id_to_save})")
                else:
                    logger.warning(f"⚠️ 保存消息历史失败 (消息ID: {message.message_id})")
            except Exception as e:
                logger.error(f"❌ 保存消息历史失败: {e}")

                import traceback
                logger.error(traceback.format_exc())
            
            # 转发消息（传入平台ID映射，支持多个同类型平台实例）
            if matched_rules:
                for rule in matched_rules:
                    try:
                        logger.info(f"📤 开始转发消息到规则: {rule.rule_name}")

                        await self.forward_manager._forward_message(
                            message, 
                            rule, 
                            platform_id_map=self.listening_platforms  # 传入平台ID到实例的映射
                        )
                        logger.info(f"✅ 消息转发成功: {rule.rule_name}")

                    except Exception as e:
                        logger.error(f"❌ 转发消息失败 ({rule.rule_name}): {e}")
                        import traceback
                        logger.error(traceback.format_exc())
            
            if not matched_rules:
                logger.info(f"ℹ️ 消息未匹配任何规则 (平台ID: {platform_id}, 聊天ID: {message.source_chat_id})")
                    
        except Exception as e:
            logger.error(f"❌ 处理平台消息失败: {e}")

            import traceback
            logger.error(traceback.format_exc())
    
    def get_status(self) -> Dict[str, Any]:
        """获取服务状态"""
        return {
            'running': self.running,
            'listening_platforms_count': len(self.listening_platforms),
            'listening_platform_ids': list(self.listening_platforms.keys())
        }

