#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Telegram MTProto 平台实现
使用 Telethon 库实现客户端登录和消息处理
"""

import asyncio
import json
import os
import sys
from typing import Dict, List, Optional, Any, Callable, Set
from datetime import datetime
import logging

# 添加项目根目录到Python路径
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from telethon import TelegramClient, events
from telethon.tl.types import User, Chat, Channel
from telethon.errors import SessionPasswordNeededError, PhoneCodeInvalidError, PhoneCodeExpiredError
from telethon.sessions import StringSession

from utils.logger import get_logger

logger = get_logger(__name__)

class TelegramMTProtoPlatform:
    """Telegram MTProto 平台实现"""
    
    def __init__(self, config: Dict[str, Any]):
        """
        初始化 Telegram MTProto 平台
        
        Args:
            config: 配置字典，包含 api_id, api_hash, phone, session_string 等
        """
        self.config = config
        self.client: Optional[TelegramClient] = None
        self.is_connected = False
        self.is_authenticated = False
        
        # 从配置中获取参数
        self.api_id = config.get('api_id')
        self.api_hash = config.get('api_hash')
        self.phone = config.get('phone')
        self.session_string = config.get('session_string')
        
        # 记录配置状态
        logger.info(f"初始化 TelegramMTProtoPlatform - phone: {self.phone}, has_session_string: {bool(self.session_string)}, session_length: {len(self.session_string) if self.session_string else 0}")
        
        # 临时存储 phone_code_hash（用于验证验证码）
        # 注意：phone_code_hash 只在内存中，但会临时保存到数据库的 config 中
        # 从 config 中恢复 phone_code_hash（如果有的话）
        self._phone_code_hash: Optional[str] = config.get('_temp_phone_code_hash')
        if self._phone_code_hash:
            logger.info(f"从配置中恢复 phone_code_hash: {self._phone_code_hash[:10]}...")
        
        # 消息处理器
        self.message_handlers: List[Callable] = []
        
        # 验证必要参数
        if not self.api_id or not self.api_hash:
            raise ValueError("缺少 api_id 或 api_hash")
        
        if not self.phone and not self.session_string:
            raise ValueError("需要提供 phone 或 session_string")
    
    async def initialize(self) -> bool:
        """初始化客户端连接"""
        try:
            # 创建客户端（始终使用 StringSession 以便获取 session_string）
            if self.session_string:
                # 使用现有会话
                logger.info(f"使用现有 session_string 创建客户端（长度: {len(self.session_string)}）")
                self.client = TelegramClient(
                    StringSession(self.session_string),
                    self.api_id,
                    self.api_hash
                )
            else:
                # 创建新的空 StringSession
                logger.info("创建新的空 StringSession 用于登录")
                self.client = TelegramClient(
                    StringSession(),
                    self.api_id,
                    self.api_hash
                )
            
            # 连接客户端
            await self.client.connect()
            self.is_connected = True
            
            # 检查是否已认证
            is_authorized = await self.client.is_user_authorized()
            logger.info(f"检查认证状态: is_authorized={is_authorized}, has_session_string={bool(self.session_string)}")
            
            if is_authorized:
                self.is_authenticated = True
                logger.info(f"✅ Telegram 客户端已认证（使用 session_string），无需登录: {self.phone}")
                return True
            else:
                logger.warning(f"⚠️ Telegram 客户端未认证，需要登录: {self.phone}")
                if self.session_string:
                    logger.warning("注意：虽然有 session_string，但认证失败（可能已过期）")
                return False
                
        except Exception as e:
            logger.error(f"初始化 Telegram 客户端失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
            # 清理状态
            self.is_connected = False
            self.is_authenticated = False
            if self.client:
                try:
                    await self.client.disconnect()
                except:
                    pass
                self.client = None
            return False
    
    async def login(self, phone_code: Optional[str] = None, password: Optional[str] = None) -> bool:
        """
        登录 Telegram 账户
        
        Args:
            phone_code: 手机验证码
            password: 两步验证密码（如果需要）
        
        Returns:
            登录是否成功
        """
        if not self.client or not self.is_connected:
            logger.error("客户端未连接，无法登录")
            return False
        
        try:
            if not self.is_authenticated:
                if not self.phone:
                    logger.error("缺少手机号码")
                    return False
                
                # 发送验证码
                if not phone_code:
                    result = await self.client.send_code_request(self.phone)
                    phone_code_hash = result.phone_code_hash if hasattr(result, 'phone_code_hash') else None
                    logger.info(f"验证码已发送到 {self.phone}, phone_code_hash: {phone_code_hash[:10] if phone_code_hash else 'N/A'}...")
                    # 保存 phone_code_hash 到实例变量，以便后续使用
                    # 注意：Telethon 的 phone_code_hash 是保存在内存中的，不会自动保存到 session 文件
                    self._phone_code_hash = phone_code_hash
                    return False  # 需要验证码
                
                # 使用验证码登录
                # 使用保存的 phone_code_hash（如果有的话）
                try:
                    # 检查是否有保存的 phone_code_hash
                    if self._phone_code_hash:
                        logger.info(f"使用保存的 phone_code_hash: {self._phone_code_hash[:10]}...")
                        await self.client.sign_in(self.phone, phone_code, phone_code_hash=self._phone_code_hash)
                    else:
                        # 没有 phone_code_hash，尝试不传（Telethon 可能会自动从 session 中获取）
                        logger.warning("没有保存的 phone_code_hash，尝试不传递")
                        await self.client.sign_in(self.phone, phone_code)
                    
                    self.is_authenticated = True
                    logger.info(f"Telegram 登录成功: {self.phone}")
                    return True
                    
                except SessionPasswordNeededError:
                    # 需要两步验证密码
                    if not password:
                        logger.info("需要两步验证密码")
                        return False
                    
                    await self.client.sign_in(password=password)
                    self.is_authenticated = True
                    logger.info(f"Telegram 两步验证成功: {self.phone}")
                    return True
                    
                except PhoneCodeInvalidError:
                    logger.error("验证码无效")
                    return False
                except PhoneCodeExpiredError:
                    logger.error("验证码已过期")
                    # 抛出特殊异常，让调用者知道需要重新发送验证码
                    raise ValueError("PHONE_CODE_EXPIRED: 验证码已过期，需要重新发送")
                except Exception as e:
                    # 检查是否是 phone_code_hash 相关的错误
                    error_msg = str(e)
                    if 'phone_code_hash' in error_msg.lower():
                        logger.error(f"phone_code_hash 错误: {e}")
                        logger.error("这可能是因为 session 中没有保存 phone_code_hash。需要重新发送验证码。")
                        # 抛出特殊异常，让调用者知道需要重新发送验证码
                        raise ValueError("PHONE_CODE_HASH_MISSING: 需要重新发送验证码")
                    raise
                    
        except Exception as e:
            logger.error(f"Telegram 登录失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return False
        
        return True
    
    async def get_session_string(self) -> Optional[str]:
        """获取会话字符串，用于保存登录状态"""
        try:
            if not self.client:
                logger.error("无法获取 session_string: 客户端未初始化")
                return None
            
            if not self.is_authenticated:
                logger.error("无法获取 session_string: 客户端未认证")
                return None
            
            session_string = self.client.session.save()
            if session_string:
                logger.info(f"成功获取 session_string，长度: {len(session_string)}")
                return session_string
            else:
                logger.error("session.save() 返回空值")
                return None
        except Exception as e:
            logger.error(f"获取 session_string 失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return None
    
    async def send_message(self, chat_id: str, message, parse_mode: str = 'HTML') -> bool:
        """
        发送消息
        
        Args:
            chat_id: 聊天ID（用户名或数字ID）
            message: 消息内容（可以是Message对象或字符串，兼容旧代码）
            parse_mode: 解析模式
        
        Returns:
            发送是否成功
        """
        if not self.client or not self.is_authenticated:
            logger.error("客户端未认证，无法发送消息")
            return False
        
        try:
            # 处理Message对象或字符串
            from .models import Message as MessageModel, MessageType
            if isinstance(message, MessageModel):
                # 使用formatted_content（如果有）或content
                message_text = message.formatted_content or message.content
                # 如果启用markdown，使用Markdown解析模式
                if message.message_type == MessageType.MARKDOWN:
                    parse_mode = 'Markdown'
            else:
                # 兼容旧代码：直接使用字符串
                message_text = str(message)
            
            # 发送消息
            await self.client.send_message(chat_id, message_text, parse_mode=parse_mode)
            logger.info(f"消息已发送到 {chat_id}")
            return True
            
        except Exception as e:
            logger.error(f"发送消息失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return False
    
    async def get_chats(self, limit: int = None) -> List[Dict[str, Any]]:
        """
        获取聊天列表
        
        性能优化：
        - 支持限制数量（避免获取过多数据）
        - 优先返回群组和频道（跳过私聊用户）
        
        Args:
            limit: 限制返回数量，None表示不限制
        
        Returns:
            聊天列表
        """
        if not self.client or not self.is_authenticated:
            logger.error("客户端未认证，无法获取聊天列表")
            return []
        
        try:
            # 🔧 修复 event loop 冲突问题 + 性能优化
            import asyncio
            import time
            
            start_time = time.time()
            logger.info("⏱️ 开始获取聊天列表...")
            
            # 确保客户端在当前 event loop 中正确连接
            current_loop = asyncio.get_event_loop()
            client_loop = getattr(self.client, '_loop', None)
            
            needs_reconnect = False
            if not self.client.is_connected():
                logger.info("📡 客户端未连接，准备连接...")
                needs_reconnect = True
            elif client_loop and client_loop != current_loop:
                logger.warning("⚠️ 检测到 event loop 变化，需要重新连接")
                needs_reconnect = True
            
            # 执行重连（如果需要）
            if needs_reconnect:
                try:
                    if self.client.is_connected():
                        logger.info("断开旧连接...")
                        await self.client.disconnect()
                    
                    logger.info("重新连接到 Telegram...")
                    await self.client.connect()
                    
                    # 验证连接状态
                    if not self.client.is_connected():
                        logger.error("❌ 重连后仍未连接")
                        return []
                    
                    # 验证认证状态
                    is_authorized = await self.client.is_user_authorized()
                    if not is_authorized:
                        logger.error("❌ 重连后认证失败")
                        self.is_authenticated = False
                        return []
                    
                    logger.info("✅ Telegram 客户端重连成功")
                    connect_time = time.time() - start_time
                    logger.info(f"⏱️ 连接耗时: {connect_time:.2f}秒")
                    
                except Exception as e:
                    logger.error(f"❌ 重连失败: {e}")
                    import traceback
                    logger.error(traceback.format_exc())
                    return []
            
            # 开始获取对话列表
            chats = []
            count = 0
            fetch_start = time.time()
            logger.info(f"📋 开始迭代对话列表（限制: {limit if limit else '无'}）...")
            
            async for dialog in self.client.iter_dialogs():
                # 如果设置了限制且已达到，提前退出
                if limit and count >= limit:
                    break
                
                entity = dialog.entity
                
                # 判断类型
                if isinstance(entity, User):
                    chat_type = 'private'
                elif isinstance(entity, Chat):
                    chat_type = 'group'
                elif isinstance(entity, Channel):
                    chat_type = 'channel'
                else:
                    chat_type = 'unknown'
                
                # 性能优化：只收集群组和频道，跳过私聊（减少数据量）
                if chat_type not in ('group', 'channel'):
                    continue
                
                chat_info = {
                    'id': dialog.id,
                    'chat_id': str(dialog.id),  # 字符串形式的ID
                    'title': dialog.title,
                    'username': getattr(entity, 'username', None),
                    'type': chat_type,
                    'is_group': chat_type == 'group',
                    'is_channel': chat_type == 'channel',
                    'is_private': False,  # 已过滤私聊
                    'unread_count': dialog.unread_count
                }
                chats.append(chat_info)
                count += 1
            
            # 计算总耗时
            fetch_time = time.time() - fetch_start
            total_time = time.time() - start_time
            logger.info(f"✅ 获取到 {len(chats)} 个聊天（群组和频道）" + (f"，限制: {limit}" if limit else ""))
            logger.info(f"⏱️ 迭代耗时: {fetch_time:.2f}秒，总耗时: {total_time:.2f}秒")
            return chats
            
        except Exception as e:
            logger.error(f"获取聊天列表失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return []
    
    async def get_chat_members(self, chat_id: str) -> List[Dict[str, Any]]:
        """获取聊天成员列表"""
        if not self.client or not self.is_authenticated:
            logger.error("客户端未认证，无法获取成员列表")
            return []
        
        try:
            members = []
            async for participant in self.client.iter_participants(chat_id):
                member_info = {
                    'id': participant.id,
                    'username': participant.username,
                    'first_name': participant.first_name,
                    'last_name': participant.last_name,
                    'phone': participant.phone
                }
                members.append(member_info)
            
            logger.info(f"获取到 {len(members)} 个成员")
            return members
            
        except Exception as e:
            logger.error(f"获取成员列表失败: {e}")
            return []
    
    def add_message_handler(self, handler: Callable):
        """添加消息处理器"""
        self.message_handlers.append(handler)
    
    async def start_listening(self, monitored_chat_ids: Optional[List[str]] = None):
        """
        开始监听消息
        
        Args:
            monitored_chat_ids: 要监听的群组/频道ID列表，如果为None则监听所有
        """
        import asyncio
        
        if not self.client or not self.is_authenticated:
            logger.error("客户端未认证，无法开始监听")
            return
        
        # 如果指定了要监听的群组，转换为集合以便快速查找
        monitored_chat_set = None
        if monitored_chat_ids:
            # 转换为字符串集合，支持多种格式（数字ID、字符串ID、用户名等）
            monitored_chat_set = set()
            for chat_id in monitored_chat_ids:
                # 支持数字ID和字符串ID
                monitored_chat_set.add(str(chat_id))
                # 如果是数字，也添加负数形式（Telegram群组ID通常是负数）
                try:
                    num_id = int(chat_id)
                    monitored_chat_set.add(str(-abs(num_id)))
                    monitored_chat_set.add(str(abs(num_id)))
                except ValueError:
                    pass
            
            logger.info(f"开始监听 {len(monitored_chat_ids)} 个指定的群组/频道")
        else:
            logger.info("开始监听所有群组/频道")
        
        # 注册消息事件处理器
        message_received_count = {'total': 0, 'filtered': 0, 'processed': 0}
        
        @self.client.on(events.NewMessage)
        async def handle_new_message(event):
            try:
                message_received_count['total'] += 1
                
                event_chat_id = str(event.chat_id)
                chat_title = getattr(event.chat, 'title', None)
                message_text = event.message.text or ''
                
                # 如果指定了要监听的群组，进行过滤
                if monitored_chat_set is not None:
                    # 检查是否在监听列表中
                    matched = False
                    if event_chat_id in monitored_chat_set:
                        matched = True
                    else:
                        # 也检查负数形式（Telegram群组ID通常是负数）
                        try:
                            num_id = int(event.chat_id)
                            if (str(num_id) in monitored_chat_set or 
                                str(abs(num_id)) in monitored_chat_set or
                                str(-abs(num_id)) in monitored_chat_set):
                                matched = True
                        except (ValueError, TypeError):
                            if event_chat_id in monitored_chat_set:
                                matched = True
                    
                    if not matched:
                        message_received_count['filtered'] += 1
                        return
                
                message_received_count['processed'] += 1
                
                logger.info(f"收到消息: {chat_title} - {message_text[:50]}...")
                
                # 构建消息数据
                message_data = {
                    'id': event.message.id,
                    'chat_id': event.chat_id,
                    'chat_title': chat_title,
                    'sender_id': event.sender_id,
                    'sender_username': getattr(event.sender, 'username', None),
                    'text': message_text,
                    'date': event.message.date,
                    'platform': 'telegram_mtproto'
                }
                
                # 调用所有注册的处理器
                for handler in self.message_handlers:
                    try:
                        await handler(message_data)
                    except Exception as e:
                        logger.error(f"消息处理器执行失败: {e}")
                        import traceback
                        logger.error(traceback.format_exc())
                        
            except Exception as e:
                logger.error(f"处理新消息失败: {e}")
                import traceback
                logger.error(traceback.format_exc())
        
        # 检查客户端连接状态
        if self.client and not self.client.is_connected():
            try:
                await self.client.connect()
            except Exception as e:
                logger.error(f"客户端重新连接失败: {e}")
        
        # 等待客户端断开连接
        try:
            await self.client.disconnected
        except KeyboardInterrupt:
            logger.info("收到中断信号")
            raise
        except Exception as e:
            logger.error(f"监听任务异常: {e}")
            import traceback
            logger.error(traceback.format_exc())
    
    async def stop_listening(self):
        """停止监听消息"""
        if self.client:
            await self.client.disconnect()
            self.is_connected = False
            logger.info("已停止监听 Telegram 消息")
    
    async def disconnect(self):
        """断开连接"""
        if self.client:
            await self.client.disconnect()
            self.is_connected = False
            self.is_authenticated = False
            logger.info("Telegram 客户端已断开连接")

class TelegramMTProtoManager:
    """Telegram MTProto 管理器"""
    
    def __init__(self):
        self.platforms: Dict[str, TelegramMTProtoPlatform] = {}
        self.config_file = "telegram_mtproto_config.json"
        self.load_config()
    
    def load_config(self):
        """加载配置"""
        try:
            if os.path.exists(self.config_file):
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    config_data = json.load(f)
                    
                for platform_id, config in config_data.items():
                    try:
                        platform = TelegramMTProtoPlatform(config)
                        self.platforms[platform_id] = platform
                        logger.info(f"加载 Telegram 平台配置: {platform_id}")
                    except Exception as e:
                        logger.error(f"加载平台 {platform_id} 配置失败: {e}")
                        
        except Exception as e:
            logger.error(f"加载 Telegram 配置失败: {e}")
    
    def save_config(self):
        """保存配置"""
        try:
            config_data = {}
            for platform_id, platform in self.platforms.items():
                config_data[platform_id] = platform.config
            
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(config_data, f, ensure_ascii=False, indent=2)
            
            logger.info(f"Telegram 配置已保存到: {self.config_file}")
            return True
            
        except Exception as e:
            logger.error(f"保存 Telegram 配置失败: {e}")
            return False
    
    async def add_platform(self, platform_id: str, config: Dict[str, Any]) -> bool:
        """添加平台"""
        try:
            platform = TelegramMTProtoPlatform(config)
            await platform.initialize()
            
            self.platforms[platform_id] = platform
            self.save_config()
            
            logger.info(f"添加 Telegram 平台成功: {platform_id}")
            return True
            
        except Exception as e:
            logger.error(f"添加 Telegram 平台失败: {e}")
            return False
    
    async def remove_platform(self, platform_id: str) -> bool:
        """移除平台"""
        try:
            if platform_id in self.platforms:
                platform = self.platforms[platform_id]
                await platform.disconnect()
                del self.platforms[platform_id]
                self.save_config()
                
                logger.info(f"移除 Telegram 平台成功: {platform_id}")
                return True
            else:
                logger.warning(f"平台不存在: {platform_id}")
                return False
                
        except Exception as e:
            logger.error(f"移除 Telegram 平台失败: {e}")
            return False
    
    async def login_platform(self, platform_id: str, phone_code: Optional[str] = None, password: Optional[str] = None) -> bool:
        """登录平台"""
        if platform_id not in self.platforms:
            logger.error(f"平台不存在: {platform_id}")
            return False
        
        platform = self.platforms[platform_id]
        return await platform.login(phone_code, password)
    
    async def send_message(self, platform_id: str, chat_id: str, message: str) -> bool:
        """发送消息"""
        if platform_id not in self.platforms:
            logger.error(f"平台不存在: {platform_id}")
            return False
        
        platform = self.platforms[platform_id]
        return await platform.send_message(chat_id, message)
    
    async def get_platform_chats(self, platform_id: str) -> List[Dict[str, Any]]:
        """获取平台聊天列表"""
        if platform_id not in self.platforms:
            logger.error(f"平台不存在: {platform_id}")
            return []
        
        platform = self.platforms[platform_id]
        return await platform.get_chats()
    
    def get_platform_status(self, platform_id: str) -> Dict[str, Any]:
        """获取平台状态"""
        if platform_id not in self.platforms:
            return {'exists': False}
        
        platform = self.platforms[platform_id]
        return {
            'exists': True,
            'is_connected': platform.is_connected,
            'is_authenticated': platform.is_authenticated,
            'phone': platform.phone
        }
    
    def list_platforms(self) -> List[str]:
        """列出所有平台ID"""
        return list(self.platforms.keys())

# 全局管理器实例
telegram_manager = TelegramMTProtoManager()

async def main():
    """测试函数"""
    # 示例配置
    config = {
        'api_id': 'YOUR_API_ID',
        'api_hash': 'YOUR_API_HASH',
        'phone': '+1234567890'
    }
    
    # 创建平台
    platform = TelegramMTProtoPlatform(config)
    
    # 初始化
    if await platform.initialize():
        print("客户端初始化成功")
        
        # 登录
        if await platform.login():
            print("登录成功")
            
            # 获取聊天列表
            chats = await platform.get_chats()
            print(f"获取到 {len(chats)} 个聊天")
            
            # 断开连接
            await platform.disconnect()
        else:
            print("登录失败")
    else:
        print("客户端初始化失败")

if __name__ == "__main__":
    asyncio.run(main())
