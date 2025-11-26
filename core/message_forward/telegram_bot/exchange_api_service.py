#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
交易所 API 配置服务
处理兑换码验证和 API 配置
"""

from typing import Dict, Optional, Any
from datetime import datetime
from utils.logger import get_logger

logger = get_logger(__name__)


class ExchangeAPIService:
    """交易所 API 配置服务"""
    
    def __init__(self, db_pool):
        """
        初始化服务
        
        Args:
            db_pool: 数据库连接池
        """
        self.db_pool = db_pool
    
    def validate_redemption_code(
        self,
        code: str,
        exchange: str,
        user_id: int
    ) -> Dict[str, Any]:
        """
        验证兑换码
        
        Args:
            code: 兑换码
            exchange: 交易所类型 ('okx' 或 'binance')
            user_id: 用户ID
        
        Returns:
            验证结果: {'valid': bool, 'message': str, 'code_info': dict}
        """
        if not self.db_pool:
            return {
                'valid': False,
                'message': '数据库连接不可用'
            }
        
        try:
            sql = """
                SELECT * FROM exchange_api_redemption_codes
                WHERE code COLLATE utf8mb4_general_ci = %s COLLATE utf8mb4_general_ci 
                AND exchange COLLATE utf8mb4_general_ci = %s COLLATE utf8mb4_general_ci
            """
            rows = self.db_pool.query(sql, (code, exchange))
            
            if not rows:
                return {
                    'valid': False,
                    'message': '兑换码不存在'
                }
            
            code_info = dict(rows[0])
            
            # 检查是否激活
            if not code_info.get('is_active', 0):
                return {
                    'valid': False,
                    'message': '兑换码已被禁用'
                }
            
            # 检查是否过期
            expires_at = code_info.get('expires_at')
            if expires_at:
                if isinstance(expires_at, str):
                    from datetime import datetime
                    expires_at = datetime.fromisoformat(expires_at.replace('Z', '+00:00'))
                if datetime.now() > expires_at:
                    return {
                        'valid': False,
                        'message': '兑换码已过期'
                    }
            
            # 检查是否已被使用
            if code_info.get('user_id'):
                if code_info['user_id'] != user_id:
                    return {
                        'valid': False,
                        'message': '兑换码已被其他用户使用'
                    }
            
            return {
                'valid': True,
                'message': '兑换码有效',
                'code_info': code_info
            }
            
        except Exception as e:
            logger.error(f"验证兑换码失败: {e}")
            return {
                'valid': False,
                'message': f'验证失败: {str(e)}'
            }
    
    def use_redemption_code(
        self,
        code: str,
        exchange: str,
        user_id: int
    ) -> Dict[str, Any]:
        """
        使用兑换码
        
        Args:
            code: 兑换码
            exchange: 交易所类型
            user_id: 用户ID
        
        Returns:
            使用结果: {'success': bool, 'message': str}
        """
        if not self.db_pool:
            return {
                'success': False,
                'message': '数据库连接不可用'
            }
        
        try:
            # 验证兑换码
            validation = self.validate_redemption_code(code, exchange, user_id)
            if not validation['valid']:
                return {
                    'success': False,
                    'message': validation['message']
                }
            
            # 标记兑换码为已使用
            update_sql = """
                UPDATE exchange_api_redemption_codes
                SET user_id = %s, used_at = NOW(), updated_at = NOW()
                WHERE code COLLATE utf8mb4_general_ci = %s COLLATE utf8mb4_general_ci 
                AND exchange COLLATE utf8mb4_general_ci = %s COLLATE utf8mb4_general_ci
            """
            self.db_pool.execute(update_sql, (user_id, code, exchange))
            
            logger.info(f"✅ 用户 {user_id} 已使用兑换码 {code} ({exchange})")
            
            return {
                'success': True,
                'message': '兑换码使用成功，您现在可以配置 API 了'
            }
            
        except Exception as e:
            logger.error(f"使用兑换码失败: {e}")
            return {
                'success': False,
                'message': f'使用失败: {str(e)}'
            }
    
    def check_user_has_redemption_code(
        self,
        user_id: int,
        exchange: str
    ) -> bool:
        """
        检查用户是否已使用过该交易所的兑换码
        
        Args:
            user_id: 用户ID
            exchange: 交易所类型
        
        Returns:
            是否已使用过兑换码
        """
        if not self.db_pool:
            return False
        
        try:
            sql = """
                SELECT id FROM exchange_api_redemption_codes
                WHERE user_id = %s AND exchange COLLATE utf8mb4_general_ci = %s COLLATE utf8mb4_general_ci
                LIMIT 1
            """
            rows = self.db_pool.query(sql, (user_id, exchange))
            return len(rows) > 0
        except Exception as e:
            logger.error(f"检查兑换码使用记录失败: {e}")
            return False
    
    def save_exchange_api_config(
        self,
        user_id: int,
        exchange: str,
        api_key: str,
        api_secret: str,
        passphrase: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        保存交易所 API 配置到 customers 表
        
        Args:
            user_id: 用户ID
            exchange: 交易所类型 ('okx' 或 'binance')
            api_key: API Key
            api_secret: API Secret
            passphrase: Passphrase（仅 OKX 需要）
        
        Returns:
            保存结果: {'success': bool, 'message': str, 'customer_uid': str}
        """
        if not self.db_pool:
            return {
                'success': False,
                'message': '数据库连接不可用'
            }
        
        try:
            # 检查用户是否已使用兑换码
            if not self.check_user_has_redemption_code(user_id, exchange):
                return {
                    'success': False,
                    'message': '请先使用兑换码获取配置权限。前往 qianlijin.com 获取兑换码。'
                }
            
            # 获取用户信息
            user_sql = "SELECT customer_uid FROM users WHERE id = %s"
            user_rows = self.db_pool.query(user_sql, (user_id,))
            if not user_rows:
                return {
                    'success': False,
                    'message': '用户不存在'
                }
            
            user_data = dict(user_rows[0])
            customer_uid = user_data.get('customer_uid')
            
            # 如果用户没有 customer_uid，创建一个
            if not customer_uid:
                import uuid
                customer_uid = f"tg_{user_id}_{uuid.uuid4().hex[:8]}"
                
                # 更新用户的 customer_uid
                update_user_sql = "UPDATE users SET customer_uid = %s WHERE id = %s"
                self.db_pool.execute(update_user_sql, (customer_uid, user_id))
            
            # 检查 customers 表中是否已存在
            check_customer_sql = "SELECT id FROM customers WHERE customer_uid = %s"
            customer_rows = self.db_pool.query(check_customer_sql, (customer_uid,))
            
            if customer_rows:
                # 更新现有记录
                customer_id = customer_rows[0]['id']
                # 检查 customers 表是否有 passphrase 字段
                try:
                    # 尝试更新（包含 passphrase）
                    update_sql = """
                        UPDATE customers 
                        SET api_key = %s, api_secret = %s, exchange = %s, updated_at = NOW()
                        WHERE customer_uid = %s
                    """
                    params = [api_key, api_secret, exchange, customer_uid]
                    # 如果 customers 表有 passphrase 字段，添加它
                    if passphrase:
                        update_sql = """
                            UPDATE customers 
                            SET api_key = %s, api_secret = %s, passphrase = %s, 
                                exchange = %s, updated_at = NOW()
                            WHERE customer_uid = %s
                        """
                        params = [api_key, api_secret, passphrase, exchange, customer_uid]
                    self.db_pool.execute(update_sql, tuple(params))
                except Exception as e:
                    # 如果 passphrase 字段不存在，只更新 api_key 和 api_secret
                    logger.debug(f"更新 customers 表时 passphrase 字段可能不存在: {e}")
                    update_sql = """
                        UPDATE customers 
                        SET api_key = %s, api_secret = %s, exchange = %s, updated_at = NOW()
                        WHERE customer_uid = %s
                    """
                    self.db_pool.execute(update_sql, (api_key, api_secret, exchange, customer_uid))
            else:
                # 创建新记录
                try:
                    # 尝试插入（包含 passphrase）
                    insert_sql = """
                        INSERT INTO customers 
                        (customer_uid, name, api_key, api_secret, exchange, enabled, created_at)
                        VALUES (%s, %s, %s, %s, %s, 1, NOW())
                    """
                    params = [customer_uid, f"tg_user_{user_id}", api_key, api_secret, exchange]
                    # 如果 customers 表有 passphrase 字段，添加它
                    if passphrase:
                        insert_sql = """
                            INSERT INTO customers 
                            (customer_uid, name, api_key, api_secret, passphrase, exchange, enabled, created_at)
                            VALUES (%s, %s, %s, %s, %s, %s, 1, NOW())
                        """
                        params = [customer_uid, f"tg_user_{user_id}", api_key, api_secret, passphrase, exchange]
                    self.db_pool.execute(insert_sql, tuple(params))
                except Exception as e:
                    # 如果 passphrase 字段不存在，只插入 api_key 和 api_secret
                    logger.debug(f"插入 customers 表时 passphrase 字段可能不存在: {e}")
                    insert_sql = """
                        INSERT INTO customers 
                        (customer_uid, name, api_key, api_secret, exchange, enabled, created_at)
                        VALUES (%s, %s, %s, %s, %s, 1, NOW())
                    """
                    self.db_pool.execute(insert_sql, (customer_uid, f"tg_user_{user_id}", api_key, api_secret, exchange))
            
            logger.info(f"✅ 用户 {user_id} 已保存 {exchange.upper()} API 配置")
            
            return {
                'success': True,
                'message': f'{exchange.upper()} API 配置保存成功',
                'customer_uid': customer_uid
            }
            
        except Exception as e:
            logger.error(f"保存 API 配置失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return {
                'success': False,
                'message': f'保存失败: {str(e)}'
            }
    
    def get_exchange_api_config(
        self,
        user_id: int,
        exchange: str
    ) -> Optional[Dict[str, Any]]:
        """
        获取用户的交易所 API 配置（不返回敏感信息）
        
        Args:
            user_id: 用户ID
            exchange: 交易所类型
        
        Returns:
            API 配置信息（隐藏敏感字段）
        """
        if not self.db_pool:
            return None
        
        try:
            sql = """
                SELECT 
                    c.customer_uid,
                    c.name,
                    c.exchange,
                    c.enabled,
                    c.is_demo,
                    CASE 
                        WHEN c.api_key IS NOT NULL AND c.api_key != '' THEN '已配置'
                        ELSE '未配置'
                    END as api_key_status,
                    CASE 
                        WHEN c.api_secret IS NOT NULL AND c.api_secret != '' THEN '已配置'
                        ELSE '未配置'
                    END as api_secret_status
                FROM users u
                LEFT JOIN customers c ON u.customer_uid COLLATE utf8mb4_general_ci = c.customer_uid COLLATE utf8mb4_general_ci
                WHERE u.id = %s AND (c.exchange COLLATE utf8mb4_general_ci = %s COLLATE utf8mb4_general_ci OR c.exchange IS NULL)
            """
            rows = self.db_pool.query(sql, (user_id, exchange))
            if rows:
                return dict(rows[0])
            return None
        except Exception as e:
            logger.error(f"获取 API 配置失败: {e}")
            return None

