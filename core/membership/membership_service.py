#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
会员服务模块
提供会员等级管理、权限检查、功能限制等功能
"""

import os
import sys
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta

# 添加项目根目录到Python路径
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from database.db import get_db_pool
from utils.logger import get_logger

logger = get_logger(__name__)


class MembershipService:
    """会员服务类"""
    
    def __init__(self):
        self.db_pool = get_db_pool()
    
    def get_user_membership(self, user_id: int) -> Optional[Dict[str, Any]]:
        """
        获取用户当前会员信息
        
        Args:
            user_id: 用户ID
            
        Returns:
            会员信息字典，包含等级、到期时间等
        """
        try:
            sql = """
                SELECT 
                    ml.id as level_id,
                    ml.level_code,
                    ml.level_name,
                    ml.level_order,
                    ml.price_monthly,
                    ml.price_yearly,
                    ml.max_customers,
                    ml.max_strategies,
                    ml.max_backtests_per_day,
                    ml.max_forward_rules,
                    um.started_at,
                    um.expires_at,
                    um.auto_renew,
                    um.status as membership_status,
                    CASE 
                        WHEN um.expires_at IS NULL THEN 'permanent'
                        WHEN um.expires_at > NOW() THEN 'active'
                        ELSE 'expired'
                    END as membership_status_display
                FROM users u
                LEFT JOIN user_memberships um ON u.id = um.user_id AND um.status = 'active'
                LEFT JOIN membership_levels ml ON um.level_id = ml.id
                WHERE u.id = %s
                ORDER BY um.started_at DESC
                LIMIT 1
            """
            
            result = self.db_pool.query_one(sql, (user_id,))
            
            if result and result.get('level_id'):
                return result
            else:
                # 返回免费会员信息
                return {
                    'level_id': None,
                    'level_code': 'free',
                    'level_name': '免费会员',
                    'level_order': 1,
                    'price_monthly': 0.00,
                    'price_yearly': 0.00,
                    'max_customers': 1,
                    'max_strategies': 3,
                    'max_backtests_per_day': 5,
                    'max_forward_rules': 1,
                    'started_at': None,
                    'expires_at': None,
                    'auto_renew': False,
                    'membership_status': 'active',
                    'membership_status_display': 'active'
                }
                
        except Exception as e:
            logger.error(f"获取用户会员信息失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return None
    
    def get_membership_level_permissions(self, level_id: int) -> Dict[str, str]:
        """
        获取会员等级的模块权限
        
        Args:
            level_id: 会员等级ID
            
        Returns:
            权限字典 {module_code: permission_level}
        """
        try:
            sql = """
                SELECT module_code, permission_level
                FROM membership_level_permissions
                WHERE level_id = %s
            """
            
            results = self.db_pool.query(sql, (level_id,))
            
            permissions = {}
            for row in results:
                permissions[row['module_code']] = row['permission_level']
            
            return permissions
            
        except Exception as e:
            logger.error(f"获取会员等级权限失败: {e}")
            return {}
    
    def check_membership_permission(
        self, 
        user_id: int, 
        module_code: str, 
        required_level: str = 'read'
    ) -> bool:
        """
        检查用户会员权限
        
        Args:
            user_id: 用户ID
            module_code: 模块代码
            required_level: 需要的权限级别
            
        Returns:
            是否有权限
        """
        try:
            # 获取用户会员信息
            membership = self.get_user_membership(user_id)
            
            if not membership or not membership.get('level_id'):
                # 没有会员，返回 False（除非是管理员）
                return False
            
            # 检查会员是否有效
            if membership.get('membership_status_display') != 'active':
                return False
            
            # 获取会员等级权限
            level_id = membership['level_id']
            permissions = self.get_membership_level_permissions(level_id)
            
            if module_code not in permissions:
                return False
            
            # 权限级别权重
            permission_weights = {
                'none': 0,
                'read': 1,
                'write': 2,
                'admin': 3
            }
            
            user_permission = permissions[module_code]
            user_weight = permission_weights.get(user_permission, 0)
            required_weight = permission_weights.get(required_level, 1)
            
            return user_weight >= required_weight
            
        except Exception as e:
            logger.error(f"检查会员权限失败: {e}")
            return False
    
    def check_resource_limit(
        self, 
        user_id: int, 
        resource_type: str
    ) -> Dict[str, Any]:
        """
        检查用户资源限制
        
        Args:
            user_id: 用户ID
            resource_type: 资源类型 (customers, strategies, backtests, forward_rules)
            
        Returns:
            {
                'allowed': bool,
                'current': int,
                'max': int,
                'remaining': int
            }
        """
        try:
            membership = self.get_user_membership(user_id)
            
            if not membership:
                return {
                    'allowed': False,
                    'current': 0,
                    'max': 0,
                    'remaining': 0
                }
            
            # 获取限制值
            max_limit = 0
            if resource_type == 'customers':
                max_limit = membership.get('max_customers', 0)
                sql = "SELECT COUNT(*) as count FROM customers WHERE owner_user_id = %s"
            elif resource_type == 'strategies':
                max_limit = membership.get('max_strategies', 0)
                sql = "SELECT COUNT(*) as count FROM strategy_instances WHERE created_by_user_id = %s"
            elif resource_type == 'backtests':
                max_limit = membership.get('max_backtests_per_day', 0)
                # 今日回测次数
                sql = """
                    SELECT COUNT(*) as count 
                    FROM strategy_backtests 
                    WHERE created_by_user_id = %s 
                    AND DATE(created_at) = CURDATE()
                """
            elif resource_type == 'forward_rules':
                max_limit = membership.get('max_forward_rules', 0)
                sql = """
                    SELECT COUNT(*) as count 
                    FROM message_forward_rules 
                    WHERE created_by_user_id = %s
                """
            else:
                return {
                    'allowed': False,
                    'current': 0,
                    'max': 0,
                    'remaining': 0
                }
            
            # 获取当前数量
            result = self.db_pool.query_one(sql, (user_id,))
            current = result['count'] if result else 0
            
            # 无限制（max_limit = 0）
            if max_limit == 0:
                return {
                    'allowed': True,
                    'current': current,
                    'max': 0,
                    'remaining': -1  # -1 表示无限制
                }
            
            # 检查是否超过限制
            allowed = current < max_limit
            remaining = max(0, max_limit - current)
            
            return {
                'allowed': allowed,
                'current': current,
                'max': max_limit,
                'remaining': remaining
            }
            
        except Exception as e:
            logger.error(f"检查资源限制失败: {e}")
            return {
                'allowed': False,
                'current': 0,
                'max': 0,
                'remaining': 0
            }
    
    def get_all_membership_levels(self) -> List[Dict[str, Any]]:
        """
        获取所有会员等级
        
        Returns:
            会员等级列表
        """
        try:
            sql = """
                SELECT 
                    ml.*,
                    (SELECT COUNT(*) FROM membership_level_permissions WHERE level_id = ml.id) as permission_count
                FROM membership_levels ml
                WHERE ml.is_active = 1
                ORDER BY ml.level_order ASC
            """
            
            results = self.db_pool.query(sql)
            return results if results else []
            
        except Exception as e:
            logger.error(f"获取会员等级列表失败: {e}")
            return []
    
    def create_membership_order(
        self,
        user_id: int,
        level_id: int,
        billing_period: str,
        amount: float,
        payment_method: str = None
    ) -> Optional[Dict[str, Any]]:
        """
        创建会员订单
        
        Args:
            user_id: 用户ID
            level_id: 会员等级ID
            billing_period: 计费周期 (monthly, yearly)
            amount: 订单金额
            payment_method: 支付方式
            
        Returns:
            订单信息
        """
        try:
            import uuid
            order_no = f"MEM{datetime.now().strftime('%Y%m%d%H%M%S')}{uuid.uuid4().hex[:8].upper()}"
            
            # 计算到期时间
            if billing_period == 'yearly':
                expires_at = datetime.now() + timedelta(days=365)
            else:
                expires_at = datetime.now() + timedelta(days=30)
            
            sql = """
                INSERT INTO membership_orders 
                (order_no, user_id, level_id, billing_period, amount, payment_method, expires_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            """
            
            self.db_pool.execute(
                sql,
                (order_no, user_id, level_id, billing_period, amount, payment_method, expires_at)
            )
            
            # 获取订单信息
            order = self.db_pool.query_one(
                "SELECT * FROM membership_orders WHERE order_no = %s",
                (order_no,)
            )
            
            return order
            
        except Exception as e:
            logger.error(f"创建会员订单失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return None
    
    def activate_membership(
        self,
        user_id: int,
        level_id: int,
        order_id: int = None,
        expires_at: datetime = None
    ) -> bool:
        """
        激活会员
        
        Args:
            user_id: 用户ID
            level_id: 会员等级ID
            order_id: 订单ID（可选）
            expires_at: 到期时间（可选，默认从订单获取）
            
        Returns:
            是否成功
        """
        try:
            # 如果提供了订单ID，从订单获取到期时间
            if order_id:
                order = self.db_pool.query_one(
                    "SELECT expires_at FROM membership_orders WHERE id = %s",
                    (order_id,)
                )
                if order:
                    expires_at = order['expires_at']
            
            # 取消用户现有的会员（如果有）
            self.db_pool.execute(
                "UPDATE user_memberships SET status = 'cancelled' WHERE user_id = %s AND status = 'active'",
                (user_id,)
            )
            
            # 创建新的会员记录
            sql = """
                INSERT INTO user_memberships 
                (user_id, level_id, started_at, expires_at, status)
                VALUES (%s, %s, NOW(), %s, 'active')
            """
            
            self.db_pool.execute(sql, (user_id, level_id, expires_at))
            
            # 同步权限（通过触发器自动完成，但也可以手动调用）
            self.db_pool.execute(
                "CALL sync_user_membership_permissions(%s)",
                (user_id,)
            )
            
            logger.info(f"用户 {user_id} 会员激活成功，等级ID: {level_id}")
            return True
            
        except Exception as e:
            logger.error(f"激活会员失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return False

