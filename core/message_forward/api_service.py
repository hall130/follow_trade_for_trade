"""
消息转发模块 - API服务集成层
提供与 Flask API 的集成接口
"""

from typing import Dict, Any, List, Optional
from datetime import datetime
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
        self.is_running = False
        logger.info("📨 消息转发API服务初始化完成")
    
    # ==================== 服务控制 ====================
    
    async def start_service(self) -> Dict[str, Any]:
        """
        启动消息转发服务
        
        Returns:
            操作结果
        """
        try:
            if self.is_running:
                return {
                    'success': True,
                    'message': '服务已在运行中'
                }
            
            # 从数据库加载配置
            platforms = self.db.get_platforms()
            rules = self.db.get_rules()
            
            # 创建管理器实例
            from config.message_forward_config import MESSAGE_FORWARD_CONFIG
            self.manager = await MessageForwardManager.create_from_config(MESSAGE_FORWARD_CONFIG)
            
            # 从数据库加载并添加平台
            for platform_data in platforms:
                if platform_data['enabled']:
                    try:
                        platform_config = PlatformConfig(
                            platform_type=platform_data['platform_type'],
                            platform_name=platform_data['platform_name'],
                            enabled=True,
                            config=platform_data['config']
                        )
                        await self.manager.add_platform(platform_config)
                    except Exception as e:
                        logger.error(f"加载平台失败 {platform_data['platform_name']}: {e}")
            
            # 从数据库加载并添加规则
            for rule_data in rules:
                if rule_data['enabled']:
                    try:
                        forward_rule = ForwardRule(
                            rule_id=rule_data['rule_id'],
                            rule_name=rule_data['rule_name'],
                            enabled=True,
                            source_platform=rule_data['source_platform'],
                            source_chat_ids=rule_data.get('source_chat_ids', []),
                            target_platforms=rule_data.get('target_platforms', []),
                            target_chat_ids=rule_data.get('target_chat_ids', {}),
                            keywords=rule_data.get('keywords', []),
                            exclude_keywords=rule_data.get('exclude_keywords', []),
                            add_prefix=rule_data.get('add_prefix', ''),
                            add_suffix=rule_data.get('add_suffix', ''),
                            enable_markdown=rule_data.get('enable_markdown', False)
                        )
                        await self.manager.add_rule(forward_rule)
                    except Exception as e:
                        logger.error(f"加载规则失败 {rule_data['rule_name']}: {e}")
            
            # 启动管理器
            await self.manager.start()
            self.is_running = True
            
            logger.info("✅ 消息转发服务启动成功")
            return {
                'success': True,
                'message': '消息转发服务启动成功',
                'data': {
                    'platforms_loaded': len(platforms),
                    'rules_loaded': len(rules)
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
            
            # 统计连接的平台数
            connected_platforms = sum(1 for p in platforms if p['status'] == 'active' and p['enabled'])
            
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
            
            # 如果服务正在运行，动态添加到管理器
            if self.is_running and self.manager and platform_data.get('enabled', True):
                try:
                    platform_config = PlatformConfig(
                        platform_type=platform_data['platform_type'],
                        platform_name=platform_data['platform_name'],
                        enabled=True,
                        config=platform_data.get('config', {})
                    )
                    await self.manager.add_platform(platform_config)
                except Exception as e:
                    logger.warning(f"动态添加平台到管理器失败: {e}")
            
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
    
    def get_platforms(self) -> Dict[str, Any]:
        """获取平台列表"""
        try:
            platforms = self.db.get_platforms()
            return {
                'success': True,
                'data': platforms
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
                # TODO: 如果服务正在运行，更新管理器中的平台
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
            
            # 如果服务正在运行，动态添加到管理器
            if self.is_running and self.manager and rule_data.get('enabled', True):
                try:
                    forward_rule = ForwardRule(
                        rule_id=rule_id,
                        rule_name=rule_data['rule_name'],
                        enabled=True,
                        source_platform=rule_data['source_platform'],
                        source_chat_ids=rule_data.get('source_chat_ids', []),
                        target_platforms=rule_data.get('target_platforms', []),
                        target_chat_ids=rule_data.get('target_chat_ids', {}),
                        keywords=rule_data.get('keywords', []),
                        exclude_keywords=rule_data.get('exclude_keywords', []),
                        add_prefix=rule_data.get('add_prefix', ''),
                        add_suffix=rule_data.get('add_suffix', ''),
                        enable_markdown=rule_data.get('enable_markdown', False)
                    )
                    await self.manager.add_rule(forward_rule)
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
    
    def get_rules(self) -> Dict[str, Any]:
        """获取规则列表"""
        try:
            rules = self.db.get_rules()
            return {
                'success': True,
                'data': rules
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
    
    # ==================== 消息历史 ====================
    
    def get_message_history(self, limit: int = 100) -> Dict[str, Any]:
        """获取消息历史"""
        try:
            messages = self.db.get_message_history(limit)
            return {
                'success': True,
                'data': messages
            }
        except Exception as e:
            logger.error(f"❌ 获取消息历史失败: {e}")
            return {
                'success': False,
                'message': f'获取失败: {str(e)}'
            }


# 全局实例
_service_instance: Optional[MessageForwardAPIService] = None


def get_message_forward_service(db_pool=None) -> MessageForwardAPIService:
    """
    获取全局服务实例
    
    Args:
        db_pool: MySQL连接池实例（可选）
    """
    global _service_instance
    if _service_instance is None:
        _service_instance = MessageForwardAPIService(db_pool)
    return _service_instance

