"""
消息转发模块 - MySQL数据库操作层
提供对 message_platforms 和 message_forward_rules 表的 CRUD 操作
"""

import json
from typing import List, Dict, Any, Optional
from datetime import datetime
from utils.logger import get_logger

logger = get_logger(__name__)


class MessageForwardDB:
    """消息转发MySQL数据库操作类"""
    
    def __init__(self, db_pool):
        """
        初始化数据库操作
        
        Args:
            db_pool: MySQL连接池实例
        """
        self.db_pool = db_pool
        self._init_tables()
    
    def _init_tables(self):
        """初始化数据库表"""
        try:
            # 读取并执行MySQL schema
            import os
            schema_path = os.path.join('database', 'message_forward_schema_mysql.sql')
            
            if os.path.exists(schema_path):
                with open(schema_path, 'r', encoding='utf-8') as f:
                    sql_content = f.read()
                    # 分割多个SQL语句
                    statements = [s.strip() for s in sql_content.split(';') if s.strip() and not s.strip().startswith('--')]
                    for statement in statements:
                        if statement:
                            self.db_pool.execute(statement)
                logger.info("✅ 消息转发数据库表初始化成功")
            else:
                logger.warning(f"⚠️ Schema文件不存在: {schema_path}")
                
        except Exception as e:
            logger.error(f"❌ 初始化消息转发数据库表失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
    
    # ==================== 平台管理 ====================
    
    def add_platform(self, platform_data: Dict[str, Any]) -> Optional[int]:
        """
        添加新平台
        
        Args:
            platform_data: 平台数据字典
                - platform_type: 平台类型 (telegram/dingtalk/wechat)
                - platform_name: 平台名称
                - enabled: 是否启用 (默认True)
                - config: 配置字典
        
        Returns:
            新平台的ID，失败返回None
        """
        try:
            config_json = json.dumps(platform_data.get('config', {}), ensure_ascii=False)
            
            sql = """
            INSERT INTO message_platforms 
            (platform_type, platform_name, enabled, config, status)
            VALUES (%s, %s, %s, %s, 'inactive')
            """
            
            platform_id = self.db_pool.execute(sql, (
                platform_data['platform_type'],
                platform_data['platform_name'],
                1 if platform_data.get('enabled', True) else 0,
                config_json
            ))
            
            logger.info(f"✅ 添加平台成功: {platform_data['platform_name']} (ID: {platform_id})")
            return platform_id
            
        except Exception as e:
            logger.error(f"❌ 添加平台失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return None
    
    def get_platforms(self) -> List[Dict[str, Any]]:
        """
        获取所有平台
        
        Returns:
            平台列表
        """
        try:
            sql = "SELECT * FROM message_platforms ORDER BY created_at DESC"
            rows = self.db_pool.query(sql)
            
            platforms = []
            for row in rows:
                platform = dict(row)
                # 解析JSON配置
                if platform.get('config'):
                    try:
                        platform['config'] = json.loads(platform['config'])
                    except:
                        platform['config'] = {}
                platforms.append(platform)
            
            return platforms
            
        except Exception as e:
            logger.error(f"❌ 获取平台列表失败: {e}")
            return []
    
    def get_platform_by_id(self, platform_id: int) -> Optional[Dict[str, Any]]:
        """
        根据ID获取平台
        
        Args:
            platform_id: 平台ID
        
        Returns:
            平台数据字典，未找到返回None
        """
        try:
            sql = "SELECT * FROM message_platforms WHERE id = %s"
            rows = self.db_pool.query(sql, (platform_id,))
            
            if rows:
                platform = dict(rows[0])
                if platform.get('config'):
                    try:
                        platform['config'] = json.loads(platform['config'])
                    except:
                        platform['config'] = {}
                return platform
            
            return None
            
        except Exception as e:
            logger.error(f"❌ 获取平台失败 (ID: {platform_id}): {e}")
            return None
    
    def update_platform(self, platform_id: int, update_data: Dict[str, Any]) -> bool:
        """
        更新平台信息
        
        Args:
            platform_id: 平台ID
            update_data: 更新的数据字典
        
        Returns:
            成功返回True，失败返回False
        """
        try:
            set_clauses = []
            values = []
            
            if 'platform_name' in update_data:
                set_clauses.append("platform_name = %s")
                values.append(update_data['platform_name'])
            
            if 'enabled' in update_data:
                set_clauses.append("enabled = %s")
                values.append(1 if update_data['enabled'] else 0)
            
            if 'config' in update_data:
                set_clauses.append("config = %s")
                values.append(json.dumps(update_data['config'], ensure_ascii=False))
            
            if 'status' in update_data:
                set_clauses.append("status = %s")
                values.append(update_data['status'])
            
            if 'error_message' in update_data:
                set_clauses.append("error_message = %s")
                values.append(update_data['error_message'])
            
            if 'last_connected_at' in update_data:
                set_clauses.append("last_connected_at = %s")
                values.append(update_data['last_connected_at'])
            
            set_clauses.append("updated_at = NOW()")
            
            if not set_clauses:
                return True
            
            values.append(platform_id)
            
            sql = f"""
            UPDATE message_platforms 
            SET {', '.join(set_clauses)}
            WHERE id = %s
            """
            
            rowcount = self.db_pool.execute_with_rowcount(sql, values)
            
            if rowcount > 0:
                logger.info(f"✅ 更新平台成功 (ID: {platform_id})")
                return True
            else:
                logger.warning(f"⚠️ 平台不存在或未更新 (ID: {platform_id})")
                return False
            
        except Exception as e:
            logger.error(f"❌ 更新平台失败 (ID: {platform_id}): {e}")
            return False
    
    def delete_platform(self, platform_id: int) -> bool:
        """
        删除平台
        
        Args:
            platform_id: 平台ID
        
        Returns:
            成功返回True，失败返回False
        """
        try:
            sql = "DELETE FROM message_platforms WHERE id = %s"
            rowcount = self.db_pool.execute_with_rowcount(sql, (platform_id,))
            
            if rowcount > 0:
                logger.info(f"✅ 删除平台成功 (ID: {platform_id})")
                return True
            else:
                logger.warning(f"⚠️ 平台不存在 (ID: {platform_id})")
                return False
            
        except Exception as e:
            logger.error(f"❌ 删除平台失败 (ID: {platform_id}): {e}")
            return False
    
    def enable_platform(self, platform_id: int) -> bool:
        """启用平台"""
        return self.update_platform(platform_id, {'enabled': True})
    
    def disable_platform(self, platform_id: int) -> bool:
        """禁用平台"""
        return self.update_platform(platform_id, {'enabled': False})
    
    # ==================== 转发规则管理 ====================
    
    def add_rule(self, rule_data: Dict[str, Any]) -> Optional[str]:
        """
        添加转发规则
        
        Args:
            rule_data: 规则数据字典
        
        Returns:
            规则ID，失败返回None
        """
        try:
            import uuid
            rule_id = rule_data.get('rule_id', str(uuid.uuid4()))
            
            sql = """
            INSERT INTO message_forward_rules
            (rule_id, rule_name, enabled, source_platform, source_chat_ids,
             target_platforms, target_chat_ids, keywords, exclude_keywords,
             add_prefix, add_suffix, enable_markdown)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """
            
            self.db_pool.execute(sql, (
                rule_id,
                rule_data['rule_name'],
                1 if rule_data.get('enabled', True) else 0,
                rule_data['source_platform'],
                json.dumps(rule_data.get('source_chat_ids', []), ensure_ascii=False),
                json.dumps(rule_data.get('target_platforms', []), ensure_ascii=False),
                json.dumps(rule_data.get('target_chat_ids', {}), ensure_ascii=False),
                json.dumps(rule_data.get('keywords', []), ensure_ascii=False),
                json.dumps(rule_data.get('exclude_keywords', []), ensure_ascii=False),
                rule_data.get('add_prefix', ''),
                rule_data.get('add_suffix', ''),
                1 if rule_data.get('enable_markdown', False) else 0
            ))
            
            logger.info(f"✅ 添加转发规则成功: {rule_data['rule_name']} ({rule_id})")
            return rule_id
            
        except Exception as e:
            logger.error(f"❌ 添加转发规则失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return None
    
    def get_rules(self) -> List[Dict[str, Any]]:
        """获取所有转发规则"""
        try:
            sql = "SELECT * FROM message_forward_rules ORDER BY created_at DESC"
            rows = self.db_pool.query(sql)
            
            rules = []
            for row in rows:
                rule = dict(row)
                # 解析JSON字段
                for field in ['source_chat_ids', 'target_platforms', 'target_chat_ids', 
                              'keywords', 'exclude_keywords']:
                    if rule.get(field):
                        try:
                            rule[field] = json.loads(rule[field])
                        except:
                            rule[field] = [] if field != 'target_chat_ids' else {}
                
                rules.append(rule)
            
            return rules
            
        except Exception as e:
            logger.error(f"❌ 获取转发规则列表失败: {e}")
            return []
    
    def get_rule_by_id(self, rule_id: str) -> Optional[Dict[str, Any]]:
        """根据ID获取规则"""
        try:
            sql = "SELECT * FROM message_forward_rules WHERE rule_id = %s"
            rows = self.db_pool.query(sql, (rule_id,))
            
            if rows:
                rule = dict(rows[0])
                # 解析JSON字段
                for field in ['source_chat_ids', 'target_platforms', 'target_chat_ids',
                              'keywords', 'exclude_keywords']:
                    if rule.get(field):
                        try:
                            rule[field] = json.loads(rule[field])
                        except:
                            rule[field] = [] if field != 'target_chat_ids' else {}
                return rule
            
            return None
            
        except Exception as e:
            logger.error(f"❌ 获取转发规则失败 ({rule_id}): {e}")
            return None
    
    def update_rule(self, rule_id: str, update_data: Dict[str, Any]) -> bool:
        """更新转发规则"""
        try:
            set_clauses = []
            values = []
            
            if 'rule_name' in update_data:
                set_clauses.append("rule_name = %s")
                values.append(update_data['rule_name'])
            
            if 'enabled' in update_data:
                set_clauses.append("enabled = %s")
                values.append(1 if update_data['enabled'] else 0)
            
            for field in ['source_platform', 'add_prefix', 'add_suffix']:
                if field in update_data:
                    set_clauses.append(f"{field} = %s")
                    values.append(update_data[field])
            
            for field in ['source_chat_ids', 'target_platforms', 'target_chat_ids',
                          'keywords', 'exclude_keywords']:
                if field in update_data:
                    set_clauses.append(f"{field} = %s")
                    values.append(json.dumps(update_data[field], ensure_ascii=False))
            
            if 'enable_markdown' in update_data:
                set_clauses.append("enable_markdown = %s")
                values.append(1 if update_data['enable_markdown'] else 0)
            
            set_clauses.append("updated_at = NOW()")
            
            if not set_clauses:
                return True
            
            values.append(rule_id)
            
            sql = f"""
            UPDATE message_forward_rules
            SET {', '.join(set_clauses)}
            WHERE rule_id = %s
            """
            
            rowcount = self.db_pool.execute_with_rowcount(sql, values)
            
            if rowcount > 0:
                logger.info(f"✅ 更新转发规则成功 ({rule_id})")
                return True
            else:
                logger.warning(f"⚠️ 转发规则不存在或未更新 ({rule_id})")
                return False
            
        except Exception as e:
            logger.error(f"❌ 更新转发规则失败 ({rule_id}): {e}")
            return False
    
    def delete_rule(self, rule_id: str) -> bool:
        """删除转发规则"""
        try:
            sql = "DELETE FROM message_forward_rules WHERE rule_id = %s"
            rowcount = self.db_pool.execute_with_rowcount(sql, (rule_id,))
            
            if rowcount > 0:
                logger.info(f"✅ 删除转发规则成功 ({rule_id})")
                return True
            else:
                logger.warning(f"⚠️ 转发规则不存在 ({rule_id})")
                return False
            
        except Exception as e:
            logger.error(f"❌ 删除转发规则失败 ({rule_id}): {e}")
            return False
    
    def enable_rule(self, rule_id: str) -> bool:
        """启用规则"""
        return self.update_rule(rule_id, {'enabled': True})
    
    def disable_rule(self, rule_id: str) -> bool:
        """禁用规则"""
        return self.update_rule(rule_id, {'enabled': False})
    
    def increment_rule_counter(self, rule_id: str) -> bool:
        """增加规则转发计数"""
        try:
            sql = """
            UPDATE message_forward_rules
            SET messages_forwarded = messages_forwarded + 1,
                updated_at = NOW()
            WHERE rule_id = %s
            """
            
            rowcount = self.db_pool.execute_with_rowcount(sql, (rule_id,))
            return rowcount > 0
            
        except Exception as e:
            logger.error(f"❌ 增加规则计数失败 ({rule_id}): {e}")
            return False
    
    # ==================== 消息历史 ====================
    
    def add_message_history(self, message_data: Dict[str, Any]) -> Optional[int]:
        """添加消息历史记录"""
        try:
            sql = """
            INSERT INTO message_history
            (message_id, source_platform, source_chat_id, content, forwarded_to)
            VALUES (%s, %s, %s, %s, %s)
            """
            
            message_id = self.db_pool.execute(sql, (
                message_data.get('message_id', ''),
                message_data['source_platform'],
                message_data.get('source_chat_id', ''),
                message_data['content'],
                json.dumps(message_data.get('forwarded_to', []), ensure_ascii=False)
            ))
            
            return message_id
            
        except Exception as e:
            logger.error(f"❌ 添加消息历史失败: {e}")
            return None
    
    def get_message_history(self, limit: int = 100) -> List[Dict[str, Any]]:
        """获取消息历史"""
        try:
            sql = """
            SELECT * FROM message_history
            ORDER BY timestamp DESC
            LIMIT %s
            """
            
            rows = self.db_pool.query(sql, (limit,))
            
            messages = []
            for row in rows:
                msg = dict(row)
                if msg.get('forwarded_to'):
                    try:
                        msg['forwarded_to'] = json.loads(msg['forwarded_to'])
                    except:
                        msg['forwarded_to'] = []
                messages.append(msg)
            
            return messages
            
        except Exception as e:
            logger.error(f"❌ 获取消息历史失败: {e}")
            return []


# 全局实例
_db_instance: Optional[MessageForwardDB] = None


def get_message_forward_db(db_pool=None) -> MessageForwardDB:
    """
    获取全局数据库实例
    
    Args:
        db_pool: MySQL连接池实例，如果为None则从全局获取
    """
    global _db_instance
    if _db_instance is None:
        if db_pool is None:
            # 尝试从全局获取
            from database.global_db_manager import get_global_db_pool
            db_pool = get_global_db_pool()
        _db_instance = MessageForwardDB(db_pool)
    return _db_instance

