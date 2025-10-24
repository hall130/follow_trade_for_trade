"""
消息转发模块 - 数据库操作层
提供对 message_platforms 和 message_forward_rules 表的 CRUD 操作
"""

import sqlite3
import json
from typing import List, Dict, Any, Optional
from datetime import datetime
from utils.logger import get_logger

logger = get_logger(__name__)


class MessageForwardDB:
    """消息转发数据库操作类"""
    
    def __init__(self, db_path: str = "database/trading_system.db"):
        """
        初始化数据库连接
        
        Args:
            db_path: 数据库文件路径
        """
        self.db_path = db_path
        self._init_tables()
    
    def _init_tables(self):
        """初始化数据库表"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # 创建平台表
                cursor.execute("""
                CREATE TABLE IF NOT EXISTS message_platforms (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    platform_type TEXT NOT NULL,
                    platform_name TEXT NOT NULL UNIQUE,
                    enabled INTEGER DEFAULT 1,
                    config TEXT NOT NULL,
                    status TEXT DEFAULT 'inactive',
                    error_message TEXT,
                    last_connected_at TIMESTAMP,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """)
                
                # 创建转发规则表
                cursor.execute("""
                CREATE TABLE IF NOT EXISTS message_forward_rules (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    rule_id TEXT NOT NULL UNIQUE,
                    rule_name TEXT NOT NULL,
                    enabled INTEGER DEFAULT 1,
                    source_platform TEXT NOT NULL,
                    source_chat_ids TEXT,
                    target_platforms TEXT NOT NULL,
                    target_chat_ids TEXT,
                    keywords TEXT,
                    exclude_keywords TEXT,
                    add_prefix TEXT,
                    add_suffix TEXT,
                    enable_markdown INTEGER DEFAULT 0,
                    messages_forwarded INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """)
                
                # 创建消息历史表
                cursor.execute("""
                CREATE TABLE IF NOT EXISTS message_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    message_id TEXT NOT NULL,
                    source_platform TEXT NOT NULL,
                    source_chat_id TEXT,
                    content TEXT NOT NULL,
                    forwarded_to TEXT,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """)
                
                conn.commit()
                logger.info("✅ 消息转发数据库表初始化成功")
                
        except Exception as e:
            logger.error(f"❌ 初始化消息转发数据库表失败: {e}")
            raise
    
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
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                config_json = json.dumps(platform_data.get('config', {}))
                
                cursor.execute("""
                INSERT INTO message_platforms 
                (platform_type, platform_name, enabled, config, status)
                VALUES (?, ?, ?, ?, 'inactive')
                """, (
                    platform_data['platform_type'],
                    platform_data['platform_name'],
                    1 if platform_data.get('enabled', True) else 0,
                    config_json
                ))
                
                conn.commit()
                platform_id = cursor.lastrowid
                
                logger.info(f"✅ 添加平台成功: {platform_data['platform_name']} (ID: {platform_id})")
                return platform_id
                
        except sqlite3.IntegrityError:
            logger.error(f"❌ 平台名称已存在: {platform_data['platform_name']}")
            return None
        except Exception as e:
            logger.error(f"❌ 添加平台失败: {e}")
            return None
    
    def get_platforms(self) -> List[Dict[str, Any]]:
        """
        获取所有平台
        
        Returns:
            平台列表
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                
                cursor.execute("""
                SELECT * FROM message_platforms
                ORDER BY created_at DESC
                """)
                
                rows = cursor.fetchall()
                platforms = []
                
                for row in rows:
                    platform = dict(row)
                    # 解析JSON配置
                    if platform['config']:
                        platform['config'] = json.loads(platform['config'])
                    # 解析JSON字段
                    if platform.get('source_chat_ids'):
                        platform['source_chat_ids'] = json.loads(platform['source_chat_ids'])
                    
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
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                
                cursor.execute("""
                SELECT * FROM message_platforms WHERE id = ?
                """, (platform_id,))
                
                row = cursor.fetchone()
                if row:
                    platform = dict(row)
                    if platform['config']:
                        platform['config'] = json.loads(platform['config'])
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
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # 构建更新语句
                set_clauses = []
                values = []
                
                if 'platform_name' in update_data:
                    set_clauses.append("platform_name = ?")
                    values.append(update_data['platform_name'])
                
                if 'enabled' in update_data:
                    set_clauses.append("enabled = ?")
                    values.append(1 if update_data['enabled'] else 0)
                
                if 'config' in update_data:
                    set_clauses.append("config = ?")
                    values.append(json.dumps(update_data['config']))
                
                if 'status' in update_data:
                    set_clauses.append("status = ?")
                    values.append(update_data['status'])
                
                if 'error_message' in update_data:
                    set_clauses.append("error_message = ?")
                    values.append(update_data['error_message'])
                
                if 'last_connected_at' in update_data:
                    set_clauses.append("last_connected_at = ?")
                    values.append(update_data['last_connected_at'])
                
                set_clauses.append("updated_at = CURRENT_TIMESTAMP")
                
                if not set_clauses:
                    return True
                
                values.append(platform_id)
                
                sql = f"""
                UPDATE message_platforms 
                SET {', '.join(set_clauses)}
                WHERE id = ?
                """
                
                cursor.execute(sql, values)
                conn.commit()
                
                logger.info(f"✅ 更新平台成功 (ID: {platform_id})")
                return True
                
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
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                cursor.execute("""
                DELETE FROM message_platforms WHERE id = ?
                """, (platform_id,))
                
                conn.commit()
                
                if cursor.rowcount > 0:
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
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                import uuid
                rule_id = rule_data.get('rule_id', str(uuid.uuid4()))
                
                cursor.execute("""
                INSERT INTO message_forward_rules
                (rule_id, rule_name, enabled, source_platform, source_chat_ids,
                 target_platforms, target_chat_ids, keywords, exclude_keywords,
                 add_prefix, add_suffix, enable_markdown)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    rule_id,
                    rule_data['rule_name'],
                    1 if rule_data.get('enabled', True) else 0,
                    rule_data['source_platform'],
                    json.dumps(rule_data.get('source_chat_ids', [])),
                    json.dumps(rule_data.get('target_platforms', [])),
                    json.dumps(rule_data.get('target_chat_ids', {})),
                    json.dumps(rule_data.get('keywords', [])),
                    json.dumps(rule_data.get('exclude_keywords', [])),
                    rule_data.get('add_prefix', ''),
                    rule_data.get('add_suffix', ''),
                    1 if rule_data.get('enable_markdown', False) else 0
                ))
                
                conn.commit()
                
                logger.info(f"✅ 添加转发规则成功: {rule_data['rule_name']} ({rule_id})")
                return rule_id
                
        except Exception as e:
            logger.error(f"❌ 添加转发规则失败: {e}")
            return None
    
    def get_rules(self) -> List[Dict[str, Any]]:
        """获取所有转发规则"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                
                cursor.execute("""
                SELECT * FROM message_forward_rules
                ORDER BY created_at DESC
                """)
                
                rows = cursor.fetchall()
                rules = []
                
                for row in rows:
                    rule = dict(row)
                    # 解析JSON字段
                    for field in ['source_chat_ids', 'target_platforms', 'target_chat_ids', 
                                  'keywords', 'exclude_keywords']:
                        if rule.get(field):
                            rule[field] = json.loads(rule[field])
                    
                    rules.append(rule)
                
                return rules
                
        except Exception as e:
            logger.error(f"❌ 获取转发规则列表失败: {e}")
            return []
    
    def get_rule_by_id(self, rule_id: str) -> Optional[Dict[str, Any]]:
        """根据ID获取规则"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                
                cursor.execute("""
                SELECT * FROM message_forward_rules WHERE rule_id = ?
                """, (rule_id,))
                
                row = cursor.fetchone()
                if row:
                    rule = dict(row)
                    # 解析JSON字段
                    for field in ['source_chat_ids', 'target_platforms', 'target_chat_ids',
                                  'keywords', 'exclude_keywords']:
                        if rule.get(field):
                            rule[field] = json.loads(rule[field])
                    return rule
                
                return None
                
        except Exception as e:
            logger.error(f"❌ 获取转发规则失败 ({rule_id}): {e}")
            return None
    
    def update_rule(self, rule_id: str, update_data: Dict[str, Any]) -> bool:
        """更新转发规则"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                set_clauses = []
                values = []
                
                if 'rule_name' in update_data:
                    set_clauses.append("rule_name = ?")
                    values.append(update_data['rule_name'])
                
                if 'enabled' in update_data:
                    set_clauses.append("enabled = ?")
                    values.append(1 if update_data['enabled'] else 0)
                
                for field in ['source_platform', 'add_prefix', 'add_suffix']:
                    if field in update_data:
                        set_clauses.append(f"{field} = ?")
                        values.append(update_data[field])
                
                for field in ['source_chat_ids', 'target_platforms', 'target_chat_ids',
                              'keywords', 'exclude_keywords']:
                    if field in update_data:
                        set_clauses.append(f"{field} = ?")
                        values.append(json.dumps(update_data[field]))
                
                if 'enable_markdown' in update_data:
                    set_clauses.append("enable_markdown = ?")
                    values.append(1 if update_data['enable_markdown'] else 0)
                
                set_clauses.append("updated_at = CURRENT_TIMESTAMP")
                
                if not set_clauses:
                    return True
                
                values.append(rule_id)
                
                sql = f"""
                UPDATE message_forward_rules
                SET {', '.join(set_clauses)}
                WHERE rule_id = ?
                """
                
                cursor.execute(sql, values)
                conn.commit()
                
                logger.info(f"✅ 更新转发规则成功 ({rule_id})")
                return True
                
        except Exception as e:
            logger.error(f"❌ 更新转发规则失败 ({rule_id}): {e}")
            return False
    
    def delete_rule(self, rule_id: str) -> bool:
        """删除转发规则"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                cursor.execute("""
                DELETE FROM message_forward_rules WHERE rule_id = ?
                """, (rule_id,))
                
                conn.commit()
                
                if cursor.rowcount > 0:
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
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                cursor.execute("""
                UPDATE message_forward_rules
                SET messages_forwarded = messages_forwarded + 1,
                    updated_at = CURRENT_TIMESTAMP
                WHERE rule_id = ?
                """, (rule_id,))
                
                conn.commit()
                return True
                
        except Exception as e:
            logger.error(f"❌ 增加规则计数失败 ({rule_id}): {e}")
            return False
    
    # ==================== 消息历史 ====================
    
    def add_message_history(self, message_data: Dict[str, Any]) -> Optional[int]:
        """添加消息历史记录"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                cursor.execute("""
                INSERT INTO message_history
                (message_id, source_platform, source_chat_id, content, forwarded_to)
                VALUES (?, ?, ?, ?, ?)
                """, (
                    message_data.get('message_id', ''),
                    message_data['source_platform'],
                    message_data.get('source_chat_id', ''),
                    message_data['content'],
                    json.dumps(message_data.get('forwarded_to', []))
                ))
                
                conn.commit()
                return cursor.lastrowid
                
        except Exception as e:
            logger.error(f"❌ 添加消息历史失败: {e}")
            return None
    
    def get_message_history(self, limit: int = 100) -> List[Dict[str, Any]]:
        """获取消息历史"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                
                cursor.execute("""
                SELECT * FROM message_history
                ORDER BY timestamp DESC
                LIMIT ?
                """, (limit,))
                
                rows = cursor.fetchall()
                messages = []
                
                for row in rows:
                    msg = dict(row)
                    if msg.get('forwarded_to'):
                        msg['forwarded_to'] = json.loads(msg['forwarded_to'])
                    messages.append(msg)
                
                return messages
                
        except Exception as e:
            logger.error(f"❌ 获取消息历史失败: {e}")
            return []


# 全局实例
_db_instance: Optional[MessageForwardDB] = None


def get_message_forward_db() -> MessageForwardDB:
    """获取全局数据库实例"""
    global _db_instance
    if _db_instance is None:
        _db_instance = MessageForwardDB()
    return _db_instance

