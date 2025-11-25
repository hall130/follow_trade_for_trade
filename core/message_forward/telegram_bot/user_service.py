#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Telegram Bot 用户服务
处理用户验证、注册、账号绑定等功能
"""

from typing import Dict, Optional, Any
import bcrypt
import secrets
import string
from datetime import datetime
from utils.logger import get_logger

logger = get_logger(__name__)


class TelegramBotUserService:
    """Telegram Bot 用户服务"""
    
    def __init__(self, db_pool):
        """
        初始化用户服务
        
        Args:
            db_pool: 数据库连接池
        """
        self.db_pool = db_pool
    
    def get_user_by_telegram_id(self, telegram_user_id: int) -> Optional[Dict[str, Any]]:
        """
        根据 Telegram 用户ID获取平台用户信息
        
        Args:
            telegram_user_id: Telegram 用户ID
        
        Returns:
            用户信息字典，如果不存在返回None
        """
        if not self.db_pool:
            logger.error("数据库连接池不可用")
            return None
        
        try:
            sql = """
                SELECT 
                    b.id as binding_id,
                    b.telegram_user_id,
                    b.telegram_username,
                    b.platform_user_id,
                    u.id as user_id,
                    u.username,
                    u.full_name,
                    u.email,
                    u.role,
                    u.status,
                    u.created_at,
                    u.customer_uid
                FROM telegram_bot_user_bindings b
                INNER JOIN users u ON b.platform_user_id = u.id
                WHERE b.telegram_user_id = %s
            """
            rows = self.db_pool.query(sql, (telegram_user_id,))
            if rows:
                return dict(rows[0])
            return None
        except Exception as e:
            logger.error(f"获取用户信息失败: {e}")
            return None
    
    def create_user_account(
        self,
        telegram_user_id: int,
        telegram_username: Optional[str] = None,
        auto_generate: bool = True
    ) -> Dict[str, Any]:
        """
        创建平台用户账号（自动生成或手动）
        
        Args:
            telegram_user_id: Telegram 用户ID
            telegram_username: Telegram 用户名（可选）
            auto_generate: 是否自动生成用户名和密码
        
        Returns:
            创建结果: {'success': bool, 'user_id': int, 'username': str, 'password': str, 'message': str}
        """
        if not self.db_pool:
            return {
                'success': False,
                'message': '数据库连接不可用'
            }
        
        try:
            # 检查是否已绑定
            existing = self.get_user_by_telegram_id(telegram_user_id)
            if existing:
                return {
                    'success': False,
                    'message': '您已经绑定过账号了',
                    'user_id': existing['user_id'],
                    'username': existing['username']
                }
            
            # 生成用户名和密码
            if auto_generate:
                username = self._generate_username(telegram_user_id)
                password = self._generate_password()
            else:
                # 手动创建需要用户提供用户名和密码
                return {
                    'success': False,
                    'message': '请提供用户名和密码',
                    'need_input': True
                }
            
            # 检查用户名是否已存在
            check_sql = "SELECT id FROM users WHERE username = %s"
            existing_user = self.db_pool.query(check_sql, (username,))
            if existing_user:
                # 如果用户名已存在，添加后缀
                username = f"{username}_{secrets.token_hex(4)}"
            
            # 加密密码
            password_hash = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
            
            # 创建用户
            create_user_sql = """
                INSERT INTO users (username, password_hash, role, status, created_at)
                VALUES (%s, %s, 'user', 'active', NOW())
            """
            self.db_pool.execute(create_user_sql, (username, password_hash))
            user_id = self.db_pool.lastrowid
            
            # 创建绑定关系
            binding_sql = """
                INSERT INTO telegram_bot_user_bindings 
                (telegram_user_id, telegram_username, platform_user_id, created_at)
                VALUES (%s, %s, %s, NOW())
            """
            self.db_pool.execute(binding_sql, (telegram_user_id, telegram_username, user_id))
            
            logger.info(f"✅ 已为用户 {telegram_user_id} 创建平台账号: {username}")
            
            return {
                'success': True,
                'user_id': user_id,
                'username': username,
                'password': password,
                'message': '账号创建成功'
            }
            
        except Exception as e:
            logger.error(f"创建用户账号失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return {
                'success': False,
                'message': f'创建账号失败: {str(e)}'
            }
    
    def bind_existing_user(
        self,
        telegram_user_id: int,
        telegram_username: Optional[str],
        username: str,
        password: str
    ) -> Dict[str, Any]:
        """
        绑定现有平台用户账号
        
        Args:
            telegram_user_id: Telegram 用户ID
            telegram_username: Telegram 用户名
            username: 平台用户名
            password: 平台密码
        
        Returns:
            绑定结果: {'success': bool, 'message': str, 'user_id': int}
        """
        if not self.db_pool:
            return {
                'success': False,
                'message': '数据库连接不可用'
            }
        
        try:
            # 验证用户名和密码
            from auth.auth_service import AuthService
            auth_service = AuthService()
            user = auth_service.get_user_by_username(username)
            
            if not user:
                return {
                    'success': False,
                    'message': '用户名不存在'
                }
            
            # 验证密码
            if not auth_service.verify_password(password, user.password_hash):
                return {
                    'success': False,
                    'message': '密码错误'
                }
            
            # 检查用户状态
            if user.status != 'active':
                return {
                    'success': False,
                    'message': '账号已被禁用或锁定'
                }
            
            # 检查是否已绑定
            existing = self.get_user_by_telegram_id(telegram_user_id)
            if existing:
                if existing['user_id'] == user.id:
                    return {
                        'success': True,
                        'message': '您已经绑定过该账号了',
                        'user_id': user.id
                    }
                else:
                    return {
                        'success': False,
                        'message': '该 Telegram 账号已绑定其他平台账号'
                    }
            
            # 检查该平台账号是否已绑定其他 Telegram 账号
            check_binding_sql = """
                SELECT telegram_user_id FROM telegram_bot_user_bindings 
                WHERE platform_user_id = %s
            """
            existing_binding = self.db_pool.query(check_binding_sql, (user.id,))
            if existing_binding:
                return {
                    'success': False,
                    'message': '该平台账号已绑定其他 Telegram 账号'
                }
            
            # 创建绑定关系
            binding_sql = """
                INSERT INTO telegram_bot_user_bindings 
                (telegram_user_id, telegram_username, platform_user_id, created_at)
                VALUES (%s, %s, %s, NOW())
            """
            self.db_pool.execute(binding_sql, (telegram_user_id, telegram_username, user.id))
            
            logger.info(f"✅ 已绑定 Telegram 用户 {telegram_user_id} 到平台账号: {username}")
            
            return {
                'success': True,
                'message': '绑定成功',
                'user_id': user.id,
                'username': user.username
            }
            
        except Exception as e:
            logger.error(f"绑定用户账号失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return {
                'success': False,
                'message': f'绑定失败: {str(e)}'
            }
    
    def update_user_credentials(
        self,
        user_id: int,
        username: Optional[str] = None,
        password: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        更新用户登录凭据
        
        Args:
            user_id: 平台用户ID
            username: 新用户名（可选）
            password: 新密码（可选）
        
        Returns:
            更新结果: {'success': bool, 'message': str}
        """
        if not self.db_pool:
            return {
                'success': False,
                'message': '数据库连接不可用'
            }
        
        try:
            updates = []
            params = []
            
            if username:
                # 检查用户名是否已存在
                check_sql = "SELECT id FROM users WHERE username = %s AND id != %s"
                existing = self.db_pool.query(check_sql, (username, user_id))
                if existing:
                    return {
                        'success': False,
                        'message': '用户名已存在'
                    }
                updates.append("username = %s")
                params.append(username)
            
            if password:
                # 加密密码
                password_hash = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
                updates.append("password_hash = %s")
                updates.append("is_password_changed = 1")
                updates.append("password_changed_at = NOW()")
                params.append(password_hash)
            
            if not updates:
                return {
                    'success': False,
                    'message': '没有需要更新的内容'
                }
            
            params.append(user_id)
            update_sql = f"""
                UPDATE users 
                SET {', '.join(updates)}, updated_at = NOW()
                WHERE id = %s
            """
            self.db_pool.execute(update_sql, tuple(params))
            
            logger.info(f"✅ 已更新用户 {user_id} 的登录凭据")
            
            return {
                'success': True,
                'message': '更新成功'
            }
            
        except Exception as e:
            logger.error(f"更新用户凭据失败: {e}")
            return {
                'success': False,
                'message': f'更新失败: {str(e)}'
            }
    
    def _generate_username(self, telegram_user_id: int) -> str:
        """生成用户名"""
        # 使用 telegram_user_id 生成唯一用户名
        return f"tg_{telegram_user_id}"
    
    def _generate_password(self, length: int = 12) -> str:
        """生成随机密码"""
        alphabet = string.ascii_letters + string.digits + "!@#$%^&*"
        password = ''.join(secrets.choice(alphabet) for _ in range(length))
        return password

