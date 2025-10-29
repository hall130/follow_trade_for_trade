#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
认证服务模块
提供用户登录、会话管理、密码验证等功能
"""

import os
import sys
import hashlib
import bcrypt
import jwt
import secrets
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
from dataclasses import dataclass

# 添加项目根目录到Python路径
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database.db import get_db_pool
from utils.logger import get_logger

logger = get_logger(__name__)

@dataclass
class User:
    """用户数据类"""
    id: int
    username: str
    password_hash: str
    full_name: str
    email: str
    role: str
    status: str
    created_at: datetime
    last_login_at: Optional[datetime] = None
    last_login_ip: Optional[str] = None

@dataclass
class Session:
    """会话数据类"""
    id: int
    session_id: str
    user_id: int
    token: str
    created_at: datetime
    expires_at: datetime
    ip_address: str
    is_active: bool

class AuthService:
    """认证服务类"""
    
    def __init__(self):
        # JWT密钥，生产环境应该从环境变量获取
        self.jwt_secret = os.getenv('JWT_SECRET', 'your-secret-key-change-in-production')
        self.jwt_algorithm = 'HS256'
        self.session_expire_hours = 24  # 会话过期时间（小时）
        self.remember_me_days = 7  # 记住我功能过期时间（天）
    
    def hash_password(self, password: str) -> str:
        """使用bcrypt加密密码"""
        try:
            salt = bcrypt.gensalt()
            return bcrypt.hashpw(password.encode('utf-8'), salt).decode('utf-8')
        except Exception as e:
            logger.error(f"密码加密失败: {e}")
            raise
    
    def verify_password(self, password: str, hashed: str) -> bool:
        """验证密码"""
        try:
            return bcrypt.checkpw(password.encode('utf-8'), hashed.encode('utf-8'))
        except Exception as e:
            logger.error(f"密码验证失败: {e}")
            return False
    
    def generate_session_id(self) -> str:
        """生成会话ID"""
        return secrets.token_urlsafe(32)
    
    def generate_jwt_token(self, user_id: int, username: str, role: str, expires_delta: Optional[timedelta] = None) -> str:
        """生成JWT Token"""
        try:
            if expires_delta:
                expire = datetime.utcnow() + expires_delta
            else:
                expire = datetime.utcnow() + timedelta(hours=self.session_expire_hours)
            
            payload = {
                'user_id': user_id,
                'username': username,
                'role': role,
                'exp': expire,
                'iat': datetime.utcnow()
            }
            
            token = jwt.encode(payload, self.jwt_secret, algorithm=self.jwt_algorithm)
            return token
        except Exception as e:
            logger.error(f"JWT Token生成失败: {e}")
            raise
    
    def verify_jwt_token(self, token: str) -> Optional[Dict[str, Any]]:
        """验证JWT Token"""
        try:
            payload = jwt.decode(token, self.jwt_secret, algorithms=[self.jwt_algorithm])
            return payload
        except jwt.ExpiredSignatureError:
            logger.warning("JWT Token已过期")
            return None
        except jwt.InvalidTokenError as e:
            logger.warning(f"JWT Token无效: {e}")
            return None
        except Exception as e:
            logger.error(f"JWT Token验证失败: {e}")
            return None
    
    def get_user_by_username(self, username: str) -> Optional[User]:
        """根据用户名获取用户信息"""
        try:
            db_pool = get_db_pool()
            if not db_pool:
                logger.error("数据库连接池未初始化")
                return None
            
            result = db_pool.query("""
                SELECT id, username, password_hash, full_name, email, role, status, 
                       created_at, last_login_at, last_login_ip
                FROM users 
                WHERE username = %s AND status = 'active'
            """, (username,))
            
            if not result:
                return None
            
            user_data = result[0]
            return User(
                id=user_data['id'],
                username=user_data['username'],
                password_hash=user_data['password_hash'],
                full_name=user_data['full_name'],
                email=user_data['email'],
                role=user_data['role'],
                status=user_data['status'],
                created_at=user_data['created_at'],
                last_login_at=user_data['last_login_at'],
                last_login_ip=user_data['last_login_ip']
            )
            
        except Exception as e:
            logger.error(f"获取用户信息失败: {e}")
            return None
    
    def get_user_by_id(self, user_id: int) -> Optional[User]:
        """根据用户ID获取用户信息"""
        try:
            conn = get_db_pool()
            
            result = conn.query("""
                SELECT id, username, password_hash, full_name, email, role, status, 
                       created_at, last_login_at, last_login_ip
                FROM users 
                WHERE id = %s AND status = 'active'
            """, (user_id,))
            
            if result:
                user_data = result[0]  # 获取第一条记录
                return User(
                    id=user_data['id'],
                    username=user_data['username'],
                    password_hash=user_data['password_hash'],
                    full_name=user_data['full_name'],
                    email=user_data['email'],
                    role=user_data['role'],
                    status=user_data['status'],
                    created_at=user_data['created_at'],
                    last_login_at=user_data['last_login_at'],
                    last_login_ip=user_data['last_login_ip']
                )
            return None
            
        except Exception as e:
            logger.error(f"获取用户信息失败: {e}")
            return None
    
    def authenticate_user(self, username: str, password: str, ip_address: str = None) -> Optional[Dict[str, Any]]:
        """用户认证"""
        try:
            # 获取用户信息
            user = self.get_user_by_username(username)
            if not user:
                self.log_login_attempt(username, ip_address, False, "用户不存在")
                return None
            
            # 验证密码
            if not self.verify_password(password, user.password_hash):
                self.log_login_attempt(username, ip_address, False, "密码错误")
                return None
            
            # 更新最后登录信息
            self.update_last_login(user.id, ip_address)
            
            # 记录成功登录
            self.log_login_attempt(username, ip_address, True, "登录成功")
            
            # 返回用户信息（不包含密码）
            return {
                'id': user.id,
                'username': user.username,
                'full_name': user.full_name,
                'email': user.email,
                'role': user.role,
                'status': user.status,
                'created_at': user.created_at.isoformat(),
                'last_login_at': user.last_login_at.isoformat() if user.last_login_at else None
            }
            
        except Exception as e:
            logger.error(f"用户认证失败: {e}")
            self.log_login_attempt(username, ip_address, False, f"认证异常: {e}")
            return None
    
    def create_session(self, user_id: int, ip_address: str = None, remember_me: bool = False) -> Optional[Session]:
        """创建用户会话"""
        try:
            conn = get_db_pool()
            # 生成会话ID和Token
            session_id = self.generate_session_id()
            
            # 设置过期时间
            if remember_me:
                expires_at = datetime.utcnow() + timedelta(days=self.remember_me_days)
            else:
                expires_at = datetime.utcnow() + timedelta(hours=self.session_expire_hours)
            
            # 生成JWT Token
            user = self.get_user_by_id(user_id)
            if not user:
                return None
            
            token = self.generate_jwt_token(user_id, user.username, user.role, expires_at - datetime.utcnow())
            
            # 创建会话记录
            session_db_id = conn.execute("""
                INSERT INTO sessions (session_id, user_id, token, created_at, expires_at, ip_address, is_active)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            """, (session_id, user_id, token, datetime.utcnow(), expires_at, ip_address, True))
            
            return Session(
                id=session_db_id,
                session_id=session_id,
                user_id=user_id,
                token=token,
                created_at=datetime.utcnow(),
                expires_at=expires_at,
                ip_address=ip_address or '',
                is_active=True
            )
            
        except Exception as e:
            logger.error(f"创建会话失败: {e}")
            return None
    
    def get_session(self, session_id: str) -> Optional[Session]:
        """获取会话信息"""
        try:
            conn = get_db_pool()
            
            conn.execute("""
                SELECT id, session_id, user_id, token, created_at, expires_at, ip_address, is_active
                FROM sessions 
                WHERE session_id = %s AND is_active = 1 AND expires_at > NOW()
            """, (session_id,))
            
            result = conn.query("""
                SELECT id, session_id, user_id, token, created_at, expires_at, ip_address, is_active
                FROM sessions 
                WHERE session_id = %s AND is_active = 1 AND expires_at > NOW()
            """, (session_id,))
            
            if result:
                return Session(
                    id=result[0],
                    session_id=result[1],
                    user_id=result[2],
                    token=result[3],
                    created_at=result[4],
                    expires_at=result[5],
                    ip_address=result[6],
                    is_active=bool(result[7])
                )
            return None
            
        except Exception as e:
            logger.error(f"获取会话信息失败: {e}")
            return None
    
    def invalidate_session(self, session_id: str) -> bool:
        """使会话失效"""
        try:
            conn = get_db_pool()
            
            conn.execute("""
                UPDATE sessions 
                SET is_active = 0 
                WHERE session_id = %s
            """, (session_id,))
            
            return conn.execute_with_rowcount("""
                UPDATE sessions 
                SET is_active = 0 
                WHERE session_id = %s
            """, (session_id,)) > 0
            
        except Exception as e:
            logger.error(f"会话失效失败: {e}")
            return False
    
    def cleanup_expired_sessions(self) -> int:
        """清理过期会话"""
        try:
            conn = get_db_pool()
            
            cleaned_count = conn.execute_with_rowcount("DELETE FROM sessions WHERE expires_at < NOW()")
            
            logger.info(f"清理了 {cleaned_count} 个过期会话")
            return cleaned_count
            
        except Exception as e:
            logger.error(f"清理过期会话失败: {e}")
            return 0
    
    def update_last_login(self, user_id: int, ip_address: str = None) -> bool:
        """更新最后登录信息"""
        try:
            conn = get_db_pool()
            
            conn.execute("""
                UPDATE users 
                SET last_login_at = NOW(), last_login_ip = %s 
                WHERE id = %s
            """, (ip_address, user_id))
            
            return True
            
        except Exception as e:
            logger.error(f"更新最后登录信息失败: {e}")
            return False
    
    def log_login_attempt(self, username: str, ip_address: str = None, success: bool = True, reason: str = None) -> bool:
        """记录登录尝试"""
        try:
            conn = get_db_pool()
            
            # 获取用户ID
            user_id = None
            if success:
                results = conn.query("SELECT id FROM users WHERE username = %s", (username,))
                if results:
                    user_id = results[0]['id']
            
            # 记录登录日志
            conn.execute("""
                INSERT INTO login_logs (user_id, username, login_ip, login_status, fail_reason)
                VALUES (%s, %s, %s, %s, %s)
            """, (user_id, username, ip_address, 'success' if success else 'failed', reason or ''))
            
            return True
            
        except Exception as e:
            logger.error(f"记录登录日志失败: {e}")
            return False
    
    def change_password(self, user_id: int, old_password: str, new_password: str) -> bool:
        """修改密码"""
        try:
            # 获取用户信息
            user = self.get_user_by_id(user_id)
            if not user:
                return False
            
            # 验证旧密码
            if not self.verify_password(old_password, user.password_hash):
                return False
            
            # 加密新密码
            new_password_hash = self.hash_password(new_password)
            
            # 更新密码
            db_pool = get_db_pool()
            
            success = db_pool.execute("""
                UPDATE users 
                SET password_hash = %s, updated_at = NOW() 
                WHERE id = %s
            """, (new_password_hash, user_id))
            
            if success:
                logger.info(f"用户 {user.username} 密码修改成功")
                return True
            else:
                logger.error(f"密码修改失败: ID {user_id}")
                return False
            
        except Exception as e:
            logger.error(f"修改密码失败: {e}")
            return False
    
    def reset_password(self, user_id: int, new_password: str) -> bool:
        """重置密码（管理员功能）"""
        try:
            # 加密新密码
            new_password_hash = self.hash_password(new_password)
            
            # 更新密码
            db_pool = get_db_pool()
            
            success = db_pool.execute("""
                UPDATE users 
                SET password_hash = %s, updated_at = NOW() 
                WHERE id = %s
            """, (new_password_hash, user_id))
            
            if success:
                logger.info(f"用户 {user_id} 密码重置成功")
                return True
            else:
                logger.error(f"密码重置失败: ID {user_id}")
                return False
            
        except Exception as e:
            logger.error(f"重置密码失败: {e}")
            return False

    def get_all_users(self):
        """获取所有用户列表"""
        try:
            query = """
                SELECT id, username, full_name, email, role, status, 
                       created_at, last_login_at
                FROM users 
                ORDER BY created_at DESC
            """
            db_pool = get_db_pool()
            result = db_pool.query(query)
            
            logger.info(f"数据库查询结果: {len(result) if result else 0} 条记录")
            logger.info(f"查询SQL: {query}")
            
            users = []
            if result:
                for row in result:
                    logger.info(f"处理用户数据: {row}")
                    users.append({
                        'id': row['id'],
                        'username': row['username'],
                        'full_name': row['full_name'],
                        'email': row['email'],
                        'role': row['role'],
                        'status': row['status'],
                        'created_at': row['created_at'].isoformat() if row['created_at'] else None,
                        'last_login_at': row['last_login_at'].isoformat() if row['last_login_at'] else None
                    })
            
            logger.info(f"返回用户列表: {len(users)} 个用户")
            return users
            
        except Exception as e:
            logger.error(f"获取用户列表失败: {e}")
            return []

    def create_user(self, username: str, password: str, full_name: str = '', 
                   email: str = '', role: str = 'user'):
        """创建新用户"""
        try:
            # 检查用户名是否已存在
            if self.get_user_by_username(username):
                logger.warning(f"用户名已存在: {username}")
                return None
            
            # 加密密码
            hashed_password = self.hash_password(password)
            
            # 插入新用户
            query = """
                INSERT INTO users (username, password_hash, full_name, email, role, status, created_at)
                VALUES (%s, %s, %s, %s, %s, 'active', NOW())
            """
            db_pool = get_db_pool()
            user_id = db_pool.execute(query, (username, hashed_password, full_name, email, role))
            
            if user_id:
                logger.info(f"用户创建成功: {username} (ID: {user_id})")
                return self.get_user_by_id(user_id)
            else:
                logger.error(f"用户创建失败: {username}")
                return None
                
        except Exception as e:
            logger.error(f"创建用户失败: {e}")
            return None

    def update_user(self, user_id: int, username: str = None, full_name: str = None,
                   email: str = None, role: str = None, status: str = None):
        """更新用户信息"""
        try:
            update_fields = []
            params = []
            
            if username is not None:
                update_fields.append("username = %s")
                params.append(username)
            
            if full_name is not None:
                update_fields.append("full_name = %s")
                params.append(full_name)
            
            if email is not None:
                update_fields.append("email = %s")
                params.append(email)
            
            if role is not None:
                update_fields.append("role = %s")
                params.append(role)
            
            if status is not None:
                update_fields.append("status = %s")
                params.append(status)
            
            if not update_fields:
                return True
            
            update_fields.append("updated_at = NOW()")
            params.append(user_id)
            
            query = f"""
                UPDATE users 
                SET {', '.join(update_fields)}
                WHERE id = %s
            """
            
            db_pool = get_db_pool()
            success = db_pool.execute(query, params)
            
            if success:
                logger.info(f"用户更新成功: ID {user_id}")
                return True
            else:
                logger.error(f"用户更新失败: ID {user_id}")
                return False
                
        except Exception as e:
            logger.error(f"更新用户失败: {e}")
            return False

    def delete_user(self, user_id: int):
        """删除用户"""
        try:
            # 不能删除管理员用户
            user = self.get_user_by_id(user_id)
            if not user:
                logger.warning(f"用户不存在: ID {user_id}")
                return False
            
            if user.role == 'admin':
                logger.warning(f"不能删除管理员用户: ID {user_id}")
                return False
            
            # 删除用户
            query = "DELETE FROM users WHERE id = %s"
            db_pool = get_db_pool()
            success = db_pool.execute(query, (user_id,))
            
            if success:
                logger.info(f"用户删除成功: ID {user_id}")
                return True
            else:
                logger.error(f"用户删除失败: ID {user_id}")
                return False
                
        except Exception as e:
            logger.error(f"删除用户失败: {e}")
            return False

    def reset_user_password(self, user_id: int, new_password: str):
        """重置用户密码"""
        try:
            hashed_password = self.hash_password(new_password)
            
            query = """
                UPDATE users 
                SET password_hash = %s, updated_at = NOW()
                WHERE id = %s
            """
            
            db_pool = get_db_pool()
            success = db_pool.execute(query, (hashed_password, user_id))
            
            if success:
                logger.info(f"用户密码重置成功: ID {user_id}")
                return True
            else:
                logger.error(f"用户密码重置失败: ID {user_id}")
                return False
                
        except Exception as e:
            logger.error(f"重置用户密码失败: {e}")
            return False

    def update_user_status(self, user_id: int, status: str):
        """更新用户状态"""
        try:
            if status not in ['active', 'inactive']:
                logger.error(f"无效的用户状态: {status}")
                return False
            
            query = """
                UPDATE users 
                SET status = %s, updated_at = NOW()
                WHERE id = %s
            """
            
            db_pool = get_db_pool()
            success = db_pool.execute(query, (status, user_id))
            
            if success:
                logger.info(f"用户状态更新成功: ID {user_id} -> {status}")
                return True
            else:
                logger.error(f"用户状态更新失败: ID {user_id}")
                return False
                
        except Exception as e:
            logger.error(f"更新用户状态失败: {e}")
            return False

# 全局认证服务实例
auth_service = AuthService()
