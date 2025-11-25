#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Telegram Bot 订阅服务
管理用户的订阅配置
"""

from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
import json
from utils.logger import get_logger

logger = get_logger(__name__)


class TelegramSubscriptionService:
    """Telegram 订阅服务"""
    
    def __init__(self, db_pool):
        """
        初始化订阅服务
        
        Args:
            db_pool: 数据库连接池
        """
        self.db_pool = db_pool
    
    def create_or_update_subscription(
        self,
        user_id: int,
        username: str,
        rule_id: str,
        source_platform_id: Optional[int],  # 可以为 None，表示匹配所有 TradingView 平台
        target_platform_id: int,
        intervals: List[str],
        strategies: List[str],
        duration_days: int = 30
    ) -> Dict[str, Any]:
        """
        创建或更新用户订阅
        
        Args:
            user_id: 用户ID
            username: 用户名
            rule_id: 规则ID
            source_platform_id: 源平台ID
            target_platform_id: 目标平台ID
            intervals: 时间周期列表
            strategies: 策略列表
            duration_days: 订阅天数
        
        Returns:
            操作结果
        """
        try:
            # 检查是否已存在订阅
            existing = self.get_user_subscription(user_id, rule_id)
            
            start_date = datetime.now()
            if existing and existing.get('expire_date'):
                # 如果订阅未过期，从过期时间开始续订
                expire_date = existing['expire_date']
                if isinstance(expire_date, str):
                    expire_date = datetime.fromisoformat(expire_date.replace('Z', '+00:00'))
                if expire_date > datetime.now():
                    start_date = expire_date
                else:
                    start_date = datetime.now()
            
            expire_date = start_date + timedelta(days=duration_days)
            
            # 序列化 JSON 字段
            intervals_json = json.dumps(intervals, ensure_ascii=False)
            strategies_json = json.dumps(strategies, ensure_ascii=False)
            
            if existing:
                # 更新现有订阅
                sql = """
                    UPDATE telegram_user_subscriptions 
                    SET username = %s,
                        intervals = %s,
                        strategies = %s,
                        subscription_status = 'active',
                        start_date = %s,
                        expire_date = %s,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE user_id = %s AND rule_id = %s
                """
                self.db_pool.execute(sql, (
                    username, intervals_json, strategies_json,
                    start_date, expire_date, user_id, rule_id
                ))
                logger.info(f"✅ 更新订阅成功: 用户ID={user_id}, 规则ID={rule_id}")
            else:
                # 创建新订阅
                # 如果 source_platform_id 为 None，存储为 0 表示匹配所有 TradingView 平台
                stored_source_platform_id = source_platform_id if source_platform_id is not None else 0
                sql = """
                    INSERT INTO telegram_user_subscriptions 
                    (user_id, username, rule_id, source_platform_id, target_platform_id,
                     intervals, strategies, subscription_status, start_date, expire_date)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, 'active', %s, %s)
                """
                self.db_pool.execute(sql, (
                    user_id, username, rule_id, stored_source_platform_id, target_platform_id,
                    intervals_json, strategies_json, start_date, expire_date
                ))
                logger.info(f"✅ 创建订阅成功: 用户ID={user_id}, 规则ID={rule_id}, 源平台ID={stored_source_platform_id} (0表示所有TradingView)")
            
            return {
                'success': True,
                'message': '订阅已保存',
                'user_id': user_id,
                'rule_id': rule_id,
                'intervals': intervals,
                'strategies': strategies,
                'expire_date': expire_date
            }
            
        except Exception as e:
            logger.error(f"❌ 创建/更新订阅失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return {
                'success': False,
                'message': f'操作失败: {str(e)}'
            }
    
    def get_user_subscription(
        self,
        user_id: int,
        rule_id: str
    ) -> Optional[Dict[str, Any]]:
        """
        获取用户订阅信息
        
        Args:
            user_id: 用户ID
            rule_id: 规则ID
        
        Returns:
            订阅信息，如果不存在返回 None
        """
        try:
            sql = """
                SELECT s.*, r.rule_name
                FROM telegram_user_subscriptions s
                LEFT JOIN message_forward_rules r ON s.rule_id = r.rule_id
                WHERE s.user_id = %s AND s.rule_id = %s
            """
            rows = self.db_pool.query(sql, (user_id, rule_id))
            
            if rows:
                subscription = dict(rows[0])
                # 解析 JSON 字段
                if subscription.get('intervals'):
                    if isinstance(subscription['intervals'], str):
                        subscription['intervals'] = json.loads(subscription['intervals'])
                else:
                    subscription['intervals'] = []
                
                if subscription.get('strategies'):
                    if isinstance(subscription['strategies'], str):
                        subscription['strategies'] = json.loads(subscription['strategies'])
                else:
                    subscription['strategies'] = []
                
                return subscription
            return None
            
        except Exception as e:
            logger.error(f"查询用户订阅失败: {e}")
            return None
    
    def get_user_subscriptions(self, user_id: int) -> List[Dict[str, Any]]:
        """
        获取用户的所有订阅
        
        Args:
            user_id: 用户ID
        
        Returns:
            订阅列表
        """
        try:
            sql = """
                SELECT s.*, r.rule_name
                FROM telegram_user_subscriptions s
                LEFT JOIN message_forward_rules r ON s.rule_id = r.rule_id
                WHERE s.user_id = %s
                ORDER BY s.created_at DESC
            """
            rows = self.db_pool.query(sql, (user_id,))
            
            subscriptions = []
            for row in rows:
                subscription = dict(row)
                # 解析 JSON 字段
                if subscription.get('intervals'):
                    if isinstance(subscription['intervals'], str):
                        subscription['intervals'] = json.loads(subscription['intervals'])
                else:
                    subscription['intervals'] = []
                
                if subscription.get('strategies'):
                    if isinstance(subscription['strategies'], str):
                        subscription['strategies'] = json.loads(subscription['strategies'])
                else:
                    subscription['strategies'] = []
                
                subscriptions.append(subscription)
            
            return subscriptions
            
        except Exception as e:
            logger.error(f"查询用户订阅列表失败: {e}")
            return []
    
    def update_subscription_filters(
        self,
        user_id: int,
        rule_id: str,
        intervals: List[str],
        strategies: List[str]
    ) -> bool:
        """
        更新订阅过滤条件
        
        Args:
            user_id: 用户ID
            rule_id: 规则ID
            intervals: 时间周期列表
            strategies: 策略列表
        
        Returns:
            是否更新成功
        """
        try:
            intervals_json = json.dumps(intervals, ensure_ascii=False)
            strategies_json = json.dumps(strategies, ensure_ascii=False)
            
            sql = """
                UPDATE telegram_user_subscriptions 
                SET intervals = %s,
                    strategies = %s,
                    updated_at = CURRENT_TIMESTAMP
                WHERE user_id = %s AND rule_id = %s
            """
            self.db_pool.execute(sql, (intervals_json, strategies_json, user_id, rule_id))
            
            logger.info(f"✅ 更新订阅过滤条件成功: 用户ID={user_id}, 规则ID={rule_id}")
            return True
            
        except Exception as e:
            logger.error(f"❌ 更新订阅过滤条件失败: {e}")
            return False
    
    def cancel_subscription(
        self,
        user_id: int,
        rule_id: str
    ) -> bool:
        """
        取消订阅
        
        Args:
            user_id: 用户ID
            rule_id: 规则ID
        
        Returns:
            是否取消成功
        """
        try:
            sql = """
                UPDATE telegram_user_subscriptions 
                SET subscription_status = 'cancelled',
                    updated_at = CURRENT_TIMESTAMP
                WHERE user_id = %s AND rule_id = %s
            """
            self.db_pool.execute(sql, (user_id, rule_id))
            
            logger.info(f"✅ 取消订阅成功: 用户ID={user_id}, 规则ID={rule_id}")
            return True
            
        except Exception as e:
            logger.error(f"❌ 取消订阅失败: {e}")
            return False
    
    def check_message_match(
        self,
        user_id: int,
        rule_id: str,
        message: 'Message'
    ) -> bool:
        """
        检查消息是否匹配用户的订阅条件
        
        Args:
            user_id: 用户ID
            rule_id: 规则ID
            message: 消息对象
        
        Returns:
            是否匹配
        """
        try:
            # 获取用户订阅
            subscription = self.get_user_subscription(user_id, rule_id)
            if not subscription:
                return False
            
            # 检查订阅状态
            if subscription.get('subscription_status') != 'active':
                return False
            
            # 检查是否过期
            expire_date = subscription.get('expire_date')
            if expire_date:
                if isinstance(expire_date, str):
                    expire_date = datetime.fromisoformat(expire_date.replace('Z', '+00:00'))
                if expire_date < datetime.now():
                    return False
            
            # 检查时间周期过滤
            intervals = subscription.get('intervals', [])
            if intervals:
                trade_info = message.extra_data.get('trade_info', {})
                message_interval = trade_info.get('interval', '')
                if message_interval:
                    # 标准化周期格式（统一大小写）
                    message_interval_upper = message_interval.upper()
                    intervals_upper = [i.upper() for i in intervals]
                    if message_interval_upper not in intervals_upper:
                        return False
            
            # 检查策略过滤
            strategies = subscription.get('strategies', [])
            if strategies:
                trade_info = message.extra_data.get('trade_info', {})
                original_data = trade_info.get('original_data', {})
                message_strategy = original_data.get('type_', '')
                if message_strategy and message_strategy not in strategies:
                    return False
            
            return True
            
        except Exception as e:
            logger.error(f"检查消息匹配失败: {e}")
            return False
    
    def increment_message_count(
        self,
        user_id: int,
        rule_id: str
    ) -> bool:
        """
        增加用户接收消息计数
        
        Args:
            user_id: 用户ID
            rule_id: 规则ID
        
        Returns:
            是否更新成功
        """
        try:
            sql = """
                UPDATE telegram_user_subscriptions 
                SET messages_received = messages_received + 1,
                    last_message_at = CURRENT_TIMESTAMP,
                    updated_at = CURRENT_TIMESTAMP
                WHERE user_id = %s AND rule_id = %s
            """
            self.db_pool.execute(sql, (user_id, rule_id))
            return True
        except Exception as e:
            logger.error(f"更新消息计数失败: {e}")
            return False

