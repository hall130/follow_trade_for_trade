#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
微信公众号用户管理
管理关注公众号的用户和订阅信息
"""

from typing import Dict, List, Optional, Any
from datetime import datetime
import json
from database.global_db_manager import get_global_db_pool
from utils.logger import get_logger

logger = get_logger(__name__)


class WeChatOfficialUserManager:
    """微信公众号用户管理器"""
    
    def __init__(self):
        self.db_pool = get_global_db_pool()
    
    def get_or_create_user(self, openid: str, user_info: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
        """
        获取或创建用户
        
        Args:
            openid: 用户openid
            user_info: 用户信息（可选，包含昵称、头像等）
        
        Returns:
            用户信息字典，失败返回None
        """
        if not self.db_pool:
            logger.error("数据库连接池不可用")
            return None
        
        try:
            # 先查询用户是否存在
            sql = "SELECT * FROM wechat_official_users WHERE openid = %s"
            user = self.db_pool.query_one(sql, (openid,))
            
            if user:
                # 用户存在，更新信息
                update_fields = []
                update_values = []
                
                if user_info:
                    if 'nickname' in user_info:
                        update_fields.append("nickname = %s")
                        update_values.append(user_info.get('nickname'))
                    if 'headimgurl' in user_info:
                        update_fields.append("headimgurl = %s")
                        update_values.append(user_info.get('headimgurl'))
                    if 'sex' in user_info:
                        update_fields.append("sex = %s")
                        update_values.append(user_info.get('sex'))
                    if 'city' in user_info:
                        update_fields.append("city = %s")
                        update_values.append(user_info.get('city'))
                    if 'province' in user_info:
                        update_fields.append("province = %s")
                        update_values.append(user_info.get('province'))
                    if 'country' in user_info:
                        update_fields.append("country = %s")
                        update_values.append(user_info.get('country'))
                    if 'language' in user_info:
                        update_fields.append("language = %s")
                        update_values.append(user_info.get('language'))
                
                # 更新最后交互时间
                update_fields.append("last_interaction_at = %s")
                update_values.append(datetime.now())
                
                if update_fields:
                    update_values.append(openid)
                    sql = f"UPDATE wechat_official_users SET {', '.join(update_fields)} WHERE openid = %s"
                    self.db_pool.execute(sql, tuple(update_values))
                
                # 重新查询
                user = self.db_pool.query_one("SELECT * FROM wechat_official_users WHERE openid = %s", (openid,))
                return user
            else:
                # 用户不存在，创建新用户
                subscribe_time = datetime.now()
                sql = """
                INSERT INTO wechat_official_users 
                (openid, nickname, headimgurl, sex, city, province, country, language, 
                 subscribe, subscribe_time, status, last_interaction_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """
                values = (
                    openid,
                    user_info.get('nickname') if user_info else None,
                    user_info.get('headimgurl') if user_info else None,
                    user_info.get('sex') if user_info else None,
                    user_info.get('city') if user_info else None,
                    user_info.get('province') if user_info else None,
                    user_info.get('country') if user_info else None,
                    user_info.get('language', 'zh_CN') if user_info else 'zh_CN',
                    1,  # subscribe
                    subscribe_time,
                    'active',
                    subscribe_time
                )
                self.db_pool.execute(sql, values)
                
                # 查询新创建的用户
                user = self.db_pool.query_one("SELECT * FROM wechat_official_users WHERE openid = %s", (openid,))
                logger.info(f"✅ 创建新用户: openid={openid}")
                return user
                
        except Exception as e:
            logger.error(f"获取或创建用户失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return None
    
    def update_user_subscribe_status(self, openid: str, subscribe: bool) -> bool:
        """
        更新用户关注状态
        
        Args:
            openid: 用户openid
            subscribe: 是否关注（True=关注，False=取消关注）
        
        Returns:
            成功返回True，失败返回False
        """
        if not self.db_pool:
            return False
        
        try:
            if subscribe:
                sql = """
                UPDATE wechat_official_users 
                SET subscribe = 1, subscribe_time = %s, status = 'active', unsubscribe_time = NULL
                WHERE openid = %s
                """
                self.db_pool.execute(sql, (datetime.now(), openid))
                logger.info(f"✅ 用户关注: openid={openid}")
            else:
                sql = """
                UPDATE wechat_official_users 
                SET subscribe = 0, unsubscribe_time = %s, status = 'inactive'
                WHERE openid = %s
                """
                self.db_pool.execute(sql, (datetime.now(), openid))
                logger.info(f"✅ 用户取消关注: openid={openid}")
            
            return True
        except Exception as e:
            logger.error(f"更新用户关注状态失败: {e}")
            return False
    
    def get_user(self, openid: str) -> Optional[Dict[str, Any]]:
        """获取用户信息"""
        if not self.db_pool:
            return None
        
        try:
            sql = "SELECT * FROM wechat_official_users WHERE openid = %s"
            return self.db_pool.query_one(sql, (openid,))
        except Exception as e:
            logger.error(f"获取用户信息失败: {e}")
            return None
    
    def get_all_subscribed_users(self, subscription_type: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        获取所有已订阅的用户
        
        Args:
            subscription_type: 订阅类型（可选，如果指定则只返回订阅该类型的用户）
        
        Returns:
            用户列表
        """
        if not self.db_pool:
            return []
        
        try:
            if subscription_type:
                # 获取订阅了指定类型的用户
                sql = """
                SELECT u.*, s.subscription_type, s.enabled as subscription_enabled, s.config as subscription_config
                FROM wechat_official_users u
                INNER JOIN wechat_official_subscriptions s ON u.id = s.user_id
                WHERE u.subscribe = 1 AND u.status = 'active' 
                  AND s.subscription_type = %s AND s.enabled = 1
                ORDER BY u.subscribe_time DESC
                """
                return self.db_pool.query(sql, (subscription_type,))
            else:
                # 获取所有已关注的用户
                sql = """
                SELECT * FROM wechat_official_users 
                WHERE subscribe = 1 AND status = 'active'
                ORDER BY subscribe_time DESC
                """
                return self.db_pool.query(sql)
        except Exception as e:
            logger.error(f"获取订阅用户失败: {e}")
            return []
    
    def add_subscription(self, openid: str, subscription_type: str, config: Optional[Dict[str, Any]] = None) -> bool:
        """
        添加订阅
        
        Args:
            openid: 用户openid
            subscription_type: 订阅类型（trade/alert/system/signal等）
            config: 订阅配置（可选）
        
        Returns:
            成功返回True，失败返回False
        """
        if not self.db_pool:
            return False
        
        try:
            # 先获取用户ID
            user = self.get_user(openid)
            if not user:
                logger.warning(f"用户不存在: openid={openid}")
                return False
            
            user_id = user['id']
            
            # 检查是否已存在订阅
            sql = "SELECT * FROM wechat_official_subscriptions WHERE user_id = %s AND subscription_type = %s"
            existing = self.db_pool.query_one(sql, (user_id, subscription_type))
            
            if existing:
                # 更新现有订阅
                sql = """
                UPDATE wechat_official_subscriptions 
                SET enabled = 1, config = %s, updated_at = %s
                WHERE user_id = %s AND subscription_type = %s
                """
                config_json = json.dumps(config, ensure_ascii=False) if config else None
                self.db_pool.execute(sql, (config_json, datetime.now(), user_id, subscription_type))
            else:
                # 创建新订阅
                sql = """
                INSERT INTO wechat_official_subscriptions 
                (user_id, openid, subscription_type, enabled, config)
                VALUES (%s, %s, %s, 1, %s)
                """
                config_json = json.dumps(config, ensure_ascii=False) if config else None
                self.db_pool.execute(sql, (user_id, openid, subscription_type, config_json))
            
            logger.info(f"✅ 添加订阅: openid={openid}, type={subscription_type}")
            return True
        except Exception as e:
            logger.error(f"添加订阅失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return False
    
    def remove_subscription(self, openid: str, subscription_type: str) -> bool:
        """移除订阅（禁用）"""
        if not self.db_pool:
            return False
        
        try:
            user = self.get_user(openid)
            if not user:
                return False
            
            sql = """
            UPDATE wechat_official_subscriptions 
            SET enabled = 0, updated_at = %s
            WHERE user_id = %s AND subscription_type = %s
            """
            self.db_pool.execute(sql, (datetime.now(), user['id'], subscription_type))
            logger.info(f"✅ 移除订阅: openid={openid}, type={subscription_type}")
            return True
        except Exception as e:
            logger.error(f"移除订阅失败: {e}")
            return False
    
    def get_user_subscriptions(self, openid: str) -> List[Dict[str, Any]]:
        """获取用户的所有订阅"""
        if not self.db_pool:
            return []
        
        try:
            user = self.get_user(openid)
            if not user:
                return []
            
            sql = """
            SELECT * FROM wechat_official_subscriptions 
            WHERE user_id = %s AND enabled = 1
            ORDER BY subscription_type
            """
            return self.db_pool.query(sql, (user['id'],))
        except Exception as e:
            logger.error(f"获取用户订阅失败: {e}")
            return []
    
    def log_message(self, openid: str, message_type: str, subscription_type: Optional[str], 
                   content: str, template_id: Optional[str] = None, 
                   status: str = 'sent', error_message: Optional[str] = None) -> bool:
        """记录消息发送日志"""
        if not self.db_pool:
            return False
        
        try:
            user = self.get_user(openid)
            user_id = user['id'] if user else None
            
            sql = """
            INSERT INTO wechat_official_message_logs 
            (user_id, openid, message_type, subscription_type, content, template_id, status, error_message, sent_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """
            sent_at = datetime.now() if status == 'sent' else None
            self.db_pool.execute(sql, (
                user_id, openid, message_type, subscription_type, content, 
                template_id, status, error_message, sent_at
            ))
            return True
        except Exception as e:
            logger.error(f"记录消息日志失败: {e}")
            return False


# 全局实例
_wechat_official_user_manager = None

def get_wechat_official_user_manager() -> WeChatOfficialUserManager:
    """获取微信公众号用户管理器实例（单例）"""
    global _wechat_official_user_manager
    if _wechat_official_user_manager is None:
        _wechat_official_user_manager = WeChatOfficialUserManager()
    return _wechat_official_user_manager

