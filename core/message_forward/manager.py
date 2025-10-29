"""
消息转发管理器
统一管理所有消息平台和转发规则
"""

from typing import Dict, List, Optional, Any
import asyncio
import uuid

from .base import MessagePlatform
from .models import Message, ForwardRule, PlatformType
from .platforms import TelegramPlatform, DingTalkPlatform, WeChatPlatform
from .platforms.wxauto_wechat import WxAutoWeChatPlatform
from .wechat_config_manager import WeChatGroupConfigManager
from .wxauto_config_manager import WxAutoGroupConfigManager
from utils.logger import get_logger

logger = get_logger(__name__)

class MessageForwardManager:
    """消息转发管理器"""
    
    def __init__(self):
        self.platforms: Dict[PlatformType, MessagePlatform] = {}
        self.forward_rules: Dict[str, ForwardRule] = {}
        self.message_history: List[Message] = []
        self.max_history_size = 1000
        self.running = False
        self.wechat_config_manager = WeChatGroupConfigManager()
        self.wxauto_config_manager = WxAutoGroupConfigManager()
        
        logger.info("消息转发管理器初始化")
    
    async def add_platform(self, platform: MessagePlatform) -> bool:
        """
        添加消息平台
        
        Args:
            platform: 消息平台实例
            
        Returns:
            是否添加成功
        """
        try:
            # 连接平台
            if await platform.connect():
                self.platforms[platform.platform_type] = platform
                
                # 添加消息处理器
                platform.add_message_handler(self._on_message_received)
                
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
        logger.info(f"转发规则已添加: {rule.name} ({rule.rule_id})")
    
    def remove_forward_rule(self, rule_id: str) -> bool:
        """移除转发规则"""
        if rule_id in self.forward_rules:
            rule = self.forward_rules[rule_id]
            del self.forward_rules[rule_id]
            logger.info(f"转发规则已移除: {rule.name} ({rule_id})")
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
            logger.info(f"收到消息: [{message.source_platform.value}] {message.content[:50]}...")
            
            # 保存到历史记录
            self._add_to_history(message)
            
            # 应用转发规则
            for rule_id, rule in self.forward_rules.items():
                if rule.enabled and rule.matches(message):
                    logger.info(f"消息匹配规则: {rule.name}")
                    await self._forward_message(message, rule)
                    
        except Exception as e:
            logger.error(f"处理消息失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
    
    async def _forward_message(self, message: Message, rule: ForwardRule):
        """根据规则转发消息"""
        try:
            # 转换消息
            transformed_message = rule.transform_message(message)
            
            # 转发到目标平台
            for target_platform in rule.target_platforms:
                if target_platform not in self.platforms:
                    logger.warning(f"目标平台未连接: {target_platform.value}")
                    continue
                
                platform = self.platforms[target_platform]
                target_chats = rule.target_chat_ids.get(target_platform, [])
                
                if not target_chats:
                    logger.warning(f"规则 {rule.name} 未配置 {target_platform.value} 的目标聊天")
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
    async def create_from_config(cls, config: Dict[str, Any]) -> 'MessageForwardManager':
        """从配置创建管理器实例"""
        manager = cls()
        
        # 添加平台
        platforms_config = config.get('platforms', {})
        
        if platforms_config.get('telegram', {}).get('enabled'):
            tg_platform = TelegramPlatform(platforms_config['telegram'])
            await manager.add_platform(tg_platform)
        
        if platforms_config.get('dingtalk', {}).get('enabled'):
            dt_platform = DingTalkPlatform(platforms_config['dingtalk'])
            await manager.add_platform(dt_platform)
        
        if platforms_config.get('wechat', {}).get('enabled'):
            wx_platform = WeChatPlatform(platforms_config['wechat'])
            await manager.add_platform(wx_platform)
        
        # 添加转发规则
        rules_config = config.get('forward_rules', [])
        for rule_config in rules_config:
            rule = ForwardRule(
                rule_id=rule_config.get('rule_id', str(uuid.uuid4())),
                name=rule_config['name'],
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

# 全局管理器实例
_global_manager: Optional[MessageForwardManager] = None

def get_message_forward_manager() -> Optional[MessageForwardManager]:
    """获取全局消息转发管理器实例"""
    return _global_manager

def set_message_forward_manager(manager: MessageForwardManager):
    """设置全局消息转发管理器实例"""
    global _global_manager
    _global_manager = manager

