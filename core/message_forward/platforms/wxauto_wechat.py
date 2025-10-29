#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
基于wxauto的微信平台实现
更稳定的微信自动化方案，支持多群聊监听
"""

from typing import Callable, Dict, List, Optional, Any
import asyncio
import threading
import time
import json
import os
from datetime import datetime

from ..base import MessagePlatform
from ..models import Message, MessageType, PlatformType
from utils.logger import get_logger

logger = get_logger(__name__)

class WxAutoWeChatPlatform(MessagePlatform):
    """基于wxauto的微信平台（更稳定）"""
    
    def __init__(self, config: Dict[str, Any]):
        super().__init__(PlatformType.WECHAT, config)
        
        self.wechat_version = config.get('wechat_version', '3.9.8')  # 推荐版本
        self.max_listeners = config.get('max_listeners', 40)  # 最大监听数
        self.config_file = config.get('config_file', 'wxauto_group_config.json')
        
        self.wx = None
        self.is_logged_in = False
        self.listeners = []  # 监听器列表
        self.chatrooms = []  # 缓存的群聊信息
        self.friends = []    # 缓存的好友信息
        
        # 检查是否安装了 wxauto
        try:
            from wxauto import WeChat
            self.WeChat = WeChat
            logger.info("✅ 使用 wxauto 库")
        except ImportError:
            logger.error("❌ 未安装 wxauto 库")
            logger.error("请运行: pip install wxauto")
            self.enabled = False
    
    async def connect(self) -> bool:
        """连接到微信"""
        if not self.enabled or not self.WeChat:
            logger.warning("微信平台未启用或未安装 wxauto")
            return False
        
        try:
            logger.info("正在连接微信...")
            logger.info(f"💡 建议使用微信版本: {self.wechat_version}")
            logger.info("💡 请确保微信客户端已打开并登录")
            
            # 在后台线程中连接（因为 wxauto 是同步的）
            self.login_thread = threading.Thread(target=self._connect_sync, daemon=True)
            self.login_thread.start()
            
            # 等待连接完成
            for i in range(30):  # 最多等待30秒
                await asyncio.sleep(1)
                if self.is_logged_in:
                    break
            
            if self.is_logged_in:
                self.connected = True
                logger.info("✅ 微信连接成功")
                
                # 缓存群聊和好友信息
                self._cache_chat_info()
                
                return True
            else:
                logger.warning("微信连接超时")
                return False
                
        except Exception as e:
            logger.error(f"微信连接失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
            self.connected = False
            return False
    
    def _connect_sync(self):
        """同步连接（在后台线程中运行）"""
        try:
            # 创建微信实例
            self.wx = self.WeChat()
            
            # 检查是否已登录
            if self.wx.IsLogin():
                self.is_logged_in = True
                logger.info("微信已登录，开始监听消息...")
            else:
                logger.warning("微信未登录，请先登录微信客户端")
                self.is_logged_in = False
                return
            
            # 设置消息监听
            self._setup_message_listeners()
            
        except Exception as e:
            logger.error(f"微信连接失败: {e}")
            self.is_logged_in = False
    
    def _setup_message_listeners(self):
        """设置消息监听器"""
        try:
            # 加载配置的监听群聊
            config = self.load_config()
            if config and config.get('listening_groups'):
                for group_info in config['listening_groups']:
                    self._add_group_listener(group_info)
            
            logger.info(f"已设置 {len(self.listeners)} 个群聊监听器")
            
        except Exception as e:
            logger.error(f"设置消息监听器失败: {e}")
    
    def _add_group_listener(self, group_info: Dict[str, Any]):
        """添加群聊监听器"""
        try:
            group_name = group_info.get('name', '')
            group_id = group_info.get('id', '')
            
            if not group_name:
                logger.warning("群聊名称为空，跳过监听")
                return
            
            # 切换到群聊
            if self.wx.ChatWith(group_name):
                # 添加消息监听
                listener_id = self.wx.AddListenMessage(
                    callback=self._on_message_received,
                    chat_name=group_name
                )
                
                if listener_id:
                    self.listeners.append({
                        'id': listener_id,
                        'name': group_name,
                        'group_id': group_id,
                        'info': group_info
                    })
                    logger.info(f"✅ 已添加群聊监听: {group_name}")
                else:
                    logger.warning(f"❌ 添加群聊监听失败: {group_name}")
            else:
                logger.warning(f"❌ 无法找到群聊: {group_name}")
                
        except Exception as e:
            logger.error(f"添加群聊监听器失败: {e}")
    
    def _on_message_received(self, msg_info):
        """处理接收到的消息"""
        try:
            # 解析消息信息
            content = msg_info.get('content', '')
            sender = msg_info.get('sender', '')
            chat_name = msg_info.get('chat_name', '')
            msg_type = msg_info.get('type', 'text')
            
            # 构造统一消息对象
            message = Message(
                content=content,
                message_type=self._convert_message_type(msg_type),
                source_platform=PlatformType.WECHAT,
                source_chat_id=chat_name,
                source_user_id=sender,
                source_username=sender,
                extra_data={
                    'wxauto_data': msg_info,
                    'chat_name': chat_name
                }
            )
            
            # 异步处理消息
            asyncio.create_task(self._handle_message(message))
            
        except Exception as e:
            logger.error(f"处理微信消息失败: {e}")
    
    def _convert_message_type(self, msg_type: str) -> MessageType:
        """转换消息类型"""
        type_mapping = {
            'text': MessageType.TEXT,
            'image': MessageType.IMAGE,
            'file': MessageType.FILE,
            'link': MessageType.LINK
        }
        return type_mapping.get(msg_type, MessageType.TEXT)
    
    def _cache_chat_info(self):
        """缓存群聊和好友信息"""
        try:
            # 获取聊天记录
            self.chatrooms = self.wx.GetAllMessage()
            logger.info(f"缓存了 {len(self.chatrooms)} 条聊天记录")
            
            # 获取联系人
            self.friends = self.wx.GetAllContacts()
            logger.info(f"缓存了 {len(self.friends)} 个联系人")
            
        except Exception as e:
            logger.error(f"缓存聊天信息失败: {e}")
    
    def discover_groups(self) -> List[Dict[str, Any]]:
        """发现微信群（返回群聊信息）"""
        groups = []
        try:
            # 从聊天记录中筛选群聊
            for chat in self.chatrooms:
                # 根据群聊特征判断（群聊通常有多个成员）
                if isinstance(chat, dict) and chat.get('is_group', False):
                    groups.append({
                        'name': chat.get('name', 'Unknown'),
                        'id': chat.get('id', ''),
                        'member_count': chat.get('member_count', 0),
                        'type': 'group'
                    })
            
            logger.info(f"发现 {len(groups)} 个微信群")
            return groups
            
        except Exception as e:
            logger.error(f"发现微信群失败: {e}")
            return []
    
    def add_group_listener(self, group_name: str) -> bool:
        """添加群聊监听"""
        try:
            if len(self.listeners) >= self.max_listeners:
                logger.warning(f"已达到最大监听数限制: {self.max_listeners}")
                return False
            
            # 切换到群聊
            if self.wx.ChatWith(group_name):
                # 添加消息监听
                listener_id = self.wx.AddListenMessage(
                    callback=self._on_message_received,
                    chat_name=group_name
                )
                
                if listener_id:
                    self.listeners.append({
                        'id': listener_id,
                        'name': group_name,
                        'group_id': '',
                        'info': {'name': group_name}
                    })
                    logger.info(f"✅ 已添加群聊监听: {group_name}")
                    return True
                else:
                    logger.warning(f"❌ 添加群聊监听失败: {group_name}")
                    return False
            else:
                logger.warning(f"❌ 无法找到群聊: {group_name}")
                return False
                
        except Exception as e:
            logger.error(f"添加群聊监听失败: {e}")
            return False
    
    def remove_group_listener(self, group_name: str) -> bool:
        """移除群聊监听"""
        try:
            for i, listener in enumerate(self.listeners):
                if listener['name'] == group_name:
                    # 移除监听器
                    if self.wx.RemoveListenMessage(listener['id']):
                        del self.listeners[i]
                        logger.info(f"✅ 已移除群聊监听: {group_name}")
                        return True
                    else:
                        logger.warning(f"❌ 移除群聊监听失败: {group_name}")
                        return False
            
            logger.warning(f"❌ 未找到群聊监听: {group_name}")
            return False
            
        except Exception as e:
            logger.error(f"移除群聊监听失败: {e}")
            return False
    
    def get_listening_groups(self) -> List[Dict[str, Any]]:
        """获取正在监听的群聊列表"""
        return self.listeners.copy()
    
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
    
    async def disconnect(self) -> bool:
        """断开微信连接"""
        try:
            if self.wx and self.is_logged_in:
                # 移除所有监听器
                for listener in self.listeners:
                    try:
                        self.wx.RemoveListenMessage(listener['id'])
                    except:
                        pass
                
                self.listeners.clear()
                logger.info("微信连接已断开")
            
            self.connected = False
            self.is_logged_in = False
            return True
        except Exception as e:
            logger.error(f"微信断开连接失败: {e}")
            return False
    
    async def send_message(self, chat_id: str, message: Message) -> bool:
        """发送消息到微信"""
        if not self.connected or not self.wx or not self.is_logged_in:
            logger.error("微信未连接")
            return False
        
        try:
            # 切换到目标聊天
            if self.wx.ChatWith(chat_id):
                # 发送消息
                if message.message_type == MessageType.IMAGE and message.attachments:
                    # 发送图片
                    success = self.wx.SendFiles(message.attachments[0])
                elif message.message_type == MessageType.FILE and message.attachments:
                    # 发送文件
                    success = self.wx.SendFiles(message.attachments[0])
                else:
                    # 发送文本消息
                    success = self.wx.SendMsg(message.content)
                
                if success:
                    logger.debug(f"✅ 消息已发送到微信: {chat_id}")
                    return True
                else:
                    logger.error(f"❌ 消息发送失败: {chat_id}")
                    return False
            else:
                logger.error(f"❌ 无法找到聊天: {chat_id}")
                return False
                
        except Exception as e:
            logger.error(f"微信发送消息失败: {e}")
            return False
    
    async def listen(self, callback: Callable[[Message], None]) -> None:
        """监听微信消息"""
        self.add_message_handler(callback)
        logger.info("微信消息监听已启动")
    
    async def get_chat_info(self, chat_id: str) -> Optional[Dict[str, Any]]:
        """获取微信聊天信息"""
        if not self.connected or not self.wx or not self.is_logged_in:
            return None
        
        try:
            # 尝试获取聊天信息
            if self.wx.ChatWith(chat_id):
                return {
                    'id': chat_id,
                    'name': chat_id,
                    'type': 'group' if '@@' in chat_id else 'friend'
                }
            return None
            
        except Exception as e:
            logger.error(f"获取微信聊天信息失败: {e}")
            return None
    
    def get_status(self) -> Dict[str, Any]:
        """获取平台状态"""
        status = super().get_status()
        status.update({
            'wechat_version': self.wechat_version,
            'listeners_count': len(self.listeners),
            'max_listeners': self.max_listeners,
            'is_logged_in': self.is_logged_in
        })
        return status
