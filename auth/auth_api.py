#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
认证API模块
提供登录、登出、用户管理、权限管理等API端点
"""

import os
import sys
from datetime import datetime, timedelta
from flask import Blueprint, request, jsonify, session, g

# 添加项目根目录到Python路径
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from auth import (
    auth_service, 
    permission_service, 
    login_required, 
    admin_required,
    require_permission,
    validate_json_data,
    log_api_access,
    handle_exceptions,
    get_current_user_id,
    get_current_user
)
from auth.crypto_middleware import crypto_middleware
from utils.logger import get_logger

logger = get_logger(__name__)

# 创建认证蓝图
auth_bp = Blueprint('auth', __name__, url_prefix='/api/v1/auth')

# =====================================================
# 认证相关API
# =====================================================

@auth_bp.route('/encryption-key', methods=['GET'])
@log_api_access('auth')
@handle_exceptions
def get_encryption_key():
    """获取临时加密密钥（用于前端加密请求）"""
    try:
        temp_key = crypto_middleware.generate_temp_key()
        return jsonify({
            'success': True,
            'data': temp_key
        })
    except Exception as e:
        logger.error(f"获取加密密钥失败: {e}")
        return jsonify({
            'success': False,
            'message': '获取加密密钥失败',
            'code': 'ENCRYPTION_KEY_ERROR'
        }), 500

@auth_bp.route('/login', methods=['POST'])
@log_api_access('auth')
@handle_exceptions
def login():
    """用户登录（支持加密请求）"""
    try:
        # 检查是否是加密请求
        is_encrypted = request.headers.get('X-Encrypted', '').lower() == 'true'
        
        if is_encrypted:
            # 解密请求数据
            decrypted_data = crypto_middleware.decrypt_request_body()
            if not decrypted_data:
                return jsonify({
                    'success': False,
                    'message': '请求解密失败',
                    'code': 'DECRYPT_ERROR'
                }), 400
            data = decrypted_data
        else:
            # 普通请求，使用原有验证
            if not request.is_json:
                return jsonify({
                    'success': False,
                    'message': '请求格式错误',
                    'code': 'INVALID_REQUEST'
                }), 400
            data = request.get_json()
        
        # 验证必需字段
        username = data.get('username')
        password = data.get('password')
        if not username or not password:
            return jsonify({
                'success': False,
                'message': '用户名和密码不能为空',
                'code': 'MISSING_CREDENTIALS'
            }), 400
        
        remember_me = data.get('remember_me', False)
        
        # 获取客户端IP
        ip_address = request.remote_addr
        
        # 用户认证
        user_info = auth_service.authenticate_user(username, password, ip_address)
        if not user_info:
            return jsonify({
                'success': False,
                'message': '用户名或密码错误',
                'code': 'INVALID_CREDENTIALS'
            }), 401
        
        # 创建会话
        session_obj = auth_service.create_session(
            user_info['id'], 
            ip_address, 
            remember_me
        )
        
        if not session_obj:
            return jsonify({
                'success': False,
                'message': '会话创建失败',
                'code': 'SESSION_ERROR'
            }), 500
        
        # 设置Flask Session
        session['user_id'] = user_info['id']
        session['username'] = user_info['username']
        session['session_id'] = session_obj.session_id
        
        # 获取用户权限
        permissions = permission_service.get_user_permissions(user_info['id'])
        
        logger.info(f"用户 {username} 登录成功")
        
        # 检查是否需要强制修改密码
        need_change_password = user_info.get('need_change_password', False)
        
        return jsonify({
            'success': True,
            'message': '登录成功',
            'data': {
                'user': user_info,
                'session_id': session_obj.session_id,
                'token': session_obj.token,
                'permissions': permissions,
                'expires_at': session_obj.expires_at.isoformat(),
                'need_change_password': need_change_password  # 是否需要强制修改密码
            }
        })
        
    except Exception as e:
        logger.error(f"登录失败: {e}")
        return jsonify({
            'success': False,
            'message': '登录失败',
            'code': 'LOGIN_ERROR'
        }), 500

@auth_bp.route('/logout', methods=['POST'])
@login_required
@log_api_access('auth')
@handle_exceptions
def logout():
    """用户登出"""
    try:
        # 获取会话ID
        session_id = session.get('session_id')
        
        if session_id:
            # 使会话失效
            auth_service.invalidate_session(session_id)
        
        # 清除Flask Session
        session.clear()
        
        logger.info(f"用户 {g.current_user['username']} 登出成功")
        
        return jsonify({
            'success': True,
            'message': '登出成功'
        })
        
    except Exception as e:
        logger.error(f"登出失败: {e}")
        return jsonify({
            'success': False,
            'message': '登出失败',
            'code': 'LOGOUT_ERROR'
        }), 500

@auth_bp.route('/me', methods=['GET'])
@login_required
@log_api_access('auth')
@handle_exceptions
def get_current_user_info():
    """获取当前用户信息"""
    try:
        user_id = g.current_user_id
        
        # 获取用户详细信息
        user = auth_service.get_user_by_id(user_id)
        if not user:
            return jsonify({
                'success': False,
                'message': '用户不存在',
                'code': 'USER_NOT_FOUND'
            }), 404
        
        # 获取用户权限
        permissions = permission_service.get_user_permissions(user_id)
        
        return jsonify({
            'success': True,
            'data': {
                'id': user.id,
                'username': user.username,
                'full_name': user.full_name,
                'email': user.email,
                'role': user.role,
                'status': user.status,
                'created_at': user.created_at.isoformat(),
                'last_login_at': user.last_login_at.isoformat() if user.last_login_at else None,
                'permissions': permissions
            }
        })
        
    except Exception as e:
        logger.error(f"获取用户信息失败: {e}")
        return jsonify({
            'success': False,
            'message': '获取用户信息失败',
            'code': 'USER_INFO_ERROR'
        }), 500

@auth_bp.route('/refresh', methods=['POST'])
@login_required
@log_api_access('auth')
@handle_exceptions
def refresh_token():
    """刷新Token"""
    try:
        user_id = g.current_user_id
        
        # 获取用户信息
        user = auth_service.get_user_by_id(user_id)
        if not user:
            return jsonify({
                'success': False,
                'message': '用户不存在',
                'code': 'USER_NOT_FOUND'
            }), 404
        
        # 生成新的Token
        token = auth_service.generate_jwt_token(user_id, user.username, user.role)
        
        return jsonify({
            'success': True,
            'data': {
                'token': token,
                'expires_at': (datetime.utcnow() + timedelta(hours=24)).isoformat()
            }
        })
        
    except Exception as e:
        logger.error(f"刷新Token失败: {e}")
        return jsonify({
            'success': False,
            'message': '刷新Token失败',
            'code': 'REFRESH_ERROR'
        }), 500

@auth_bp.route('/permissions', methods=['GET'])
@login_required
@log_api_access('auth')
@handle_exceptions
def get_user_permissions():
    """获取当前用户权限列表"""
    try:
        user_id = g.current_user_id
        
        # 获取用户权限
        permissions = permission_service.get_user_permissions(user_id)
        
        # 获取所有模块信息
        modules = permission_service.get_all_modules()
        
        # 组织权限数据
        permission_data = []
        for module in modules:
            module_code = module['module_code']
            permission_level = permissions.get(module_code, 'none')
            
            permission_data.append({
                'module_code': module_code,
                'module_name': module['module_name'],
                'description': module['description'],
                'permission_level': permission_level
            })
        
        return jsonify({
            'success': True,
            'data': {
                'permissions': permission_data,
                'user_role': g.current_user['role']
            }
        })
        
    except Exception as e:
        logger.error(f"获取用户权限失败: {e}")
        return jsonify({
            'success': False,
            'message': '获取用户权限失败',
            'code': 'PERMISSIONS_ERROR'
        }), 500

@auth_bp.route('/change-password', methods=['POST'])
@login_required
@log_api_access('auth')
@handle_exceptions
def change_password():
    """
    修改密码
    支持强制修改（首次登录时不需要旧密码）
    """
    try:
        data = request.get_json()
        user_id = g.current_user_id
        
        # 检查是否是强制修改密码（首次登录）
        force = data.get('force', False)
        
        if force:
            # 强制修改：不需要旧密码
            new_password = data.get('new_password')
            if not new_password:
                return jsonify({
                    'success': False,
                    'message': '新密码不能为空',
                    'code': 'PASSWORD_REQUIRED'
                }), 400
        else:
            # 正常修改：需要旧密码
            old_password = data.get('old_password')
            new_password = data.get('new_password')
            
            if not old_password:
                return jsonify({
                    'success': False,
                    'message': '原密码不能为空',
                    'code': 'OLD_PASSWORD_REQUIRED'
                }), 400
            
            if not new_password:
                return jsonify({
                    'success': False,
                    'message': '新密码不能为空',
                    'code': 'PASSWORD_REQUIRED'
                }), 400
        
        # 验证新密码长度
        if len(new_password) < 6:
            return jsonify({
                'success': False,
                'message': '新密码长度不能少于6位',
                'code': 'PASSWORD_TOO_SHORT'
            }), 400
        
        # 修改密码
        success = auth_service.change_password(
            user_id, 
            old_password if not force else '', 
            new_password, 
            force=force
        )
        
        if success:
            logger.info(f"用户 {g.current_user['username']} 修改密码成功（强制: {force}）")
            return jsonify({
                'success': True,
                'message': '密码修改成功'
            })
        else:
            return jsonify({
                'success': False,
                'message': '原密码错误' if not force else '密码修改失败',
                'code': 'INVALID_OLD_PASSWORD' if not force else 'CHANGE_PASSWORD_FAILED'
            }), 400
        
    except Exception as e:
        logger.error(f"修改密码失败: {e}")
        return jsonify({
            'success': False,
            'message': '修改密码失败',
            'code': 'CHANGE_PASSWORD_ERROR'
        }), 500

# =====================================================
# 用户管理API（仅管理员）
# =====================================================

@auth_bp.route('/users', methods=['GET'])
@admin_required
@log_api_access('user_management')
@handle_exceptions
def get_users():
    """获取用户列表（仅管理员）"""
    try:
        page = request.args.get('page', 1, type=int)
        page_size = request.args.get('page_size', 20, type=int)
        search = request.args.get('search', '')
        
        # 计算偏移量
        offset = (page - 1) * page_size
        
        # 构建查询条件
        where_conditions = []
        params = []
        
        if search:
            where_conditions.append("(username LIKE %s OR full_name LIKE %s OR email LIKE %s)")
            search_param = f"%{search}%"
            params.extend([search_param, search_param, search_param])
        
        where_clause = ""
        if where_conditions:
            where_clause = "WHERE " + " AND ".join(where_conditions)
        
        # 查询用户总数
        from database.db import get_db_pool
        conn = get_db_pool()
        count_sql = f"SELECT COUNT(*) as count FROM users {where_clause}"
        count_result = conn.query(count_sql, params)
        total_count = count_result[0]['count'] if count_result else 0
        
        # 查询用户列表
        users_sql = f"""
            SELECT id, username, full_name, email, role, status, 
                   created_at, last_login_at, last_login_ip
            FROM users {where_clause}
            ORDER BY created_at DESC
            LIMIT %s OFFSET %s
        """
        users = conn.query(users_sql, params + [page_size, offset])
        
        # 组织返回数据
        user_list = []
        for user in users:
            user_list.append({
                'id': user['id'],
                'username': user['username'],
                'full_name': user['full_name'],
                'email': user['email'],
                'role': user['role'],
                'status': user['status'],
                'created_at': user['created_at'].isoformat() if user['created_at'] else None,
                'last_login_at': user['last_login_at'].isoformat() if user['last_login_at'] else None,
                'last_login_ip': user['last_login_ip']
            })
        
        return jsonify({
            'success': True,
            'data': {
                'users': user_list,
                'pagination': {
                    'page': page,
                    'page_size': page_size,
                    'total_count': total_count,
                    'total_pages': (total_count + page_size - 1) // page_size
                }
            }
        })
        
    except Exception as e:
        logger.error(f"获取用户列表失败: {e}")
        return jsonify({
            'success': False,
            'message': '获取用户列表失败',
            'code': 'GET_USERS_ERROR'
        }), 500

@auth_bp.route('/users', methods=['POST'])
@admin_required
@log_api_access('user_management')
@handle_exceptions
def create_user():
    """
    创建用户（仅管理员）
    支持绑定customer_uid或通过customer_name自动查找
    默认密码为123456（如果role是user，需要首次登录强制修改）
    """
    try:
        data = request.get_json()
        username = data.get('username')
        password = data.get('password', '123456')  # 默认密码123456
        full_name = data.get('full_name', '')
        email = data.get('email', '')
        role = data.get('role', 'user')
        customer_uid = data.get('customer_uid')  # 可选的客户UID
        customer_name = data.get('customer_name')  # 可选的客户名称（会自动查找customer_uid）
        
        if not username:
            return jsonify({
                'success': False,
                'message': '用户名不能为空',
                'code': 'USERNAME_REQUIRED'
            }), 400
        
        # 验证角色
        if role not in ['admin', 'user']:
            return jsonify({
                'success': False,
                'message': '角色必须是admin或user',
                'code': 'INVALID_ROLE'
            }), 400
        
        # 验证密码长度
        if len(password) < 6:
            return jsonify({
                'success': False,
                'message': '密码长度不能少于6位',
                'code': 'PASSWORD_TOO_SHORT'
            }), 400
        
        # 如果提供了customer_name，查找对应的customer_uid
        if customer_name and not customer_uid:
            from database.db import get_db_pool
            conn = get_db_pool()
            customer_result = conn.query(
                "SELECT customer_uid FROM customers WHERE name = %s LIMIT 1",
                (customer_name,)
            )
            if customer_result:
                customer_uid = customer_result[0]['customer_uid']
                logger.info(f"通过客户名称 {customer_name} 找到客户UID: {customer_uid}")
        
        # 创建用户（使用auth_service.create_user）
        user = auth_service.create_user(
            username=username,
            password=password,
            full_name=full_name,
            email=email,
            role=role,
            customer_uid=customer_uid
        )
        
        if not user:
            return jsonify({
                'success': False,
                'message': '用户名已存在或创建失败',
                'code': 'CREATE_USER_FAILED'
            }), 400
        
        # 为普通用户授予基本权限
        if role == 'user':
            from database.db import get_db_pool
            conn = get_db_pool()
            basic_permissions = ['customers', 'strategies', 'backtest', 'strategy_live']
            for module_code in basic_permissions:
                try:
                    conn.execute("""
                        INSERT INTO user_permissions (user_id, module_code, permission_level, granted_by)
                        VALUES (%s, %s, %s, %s)
                    """, (user.id, module_code, 'write', g.current_user_id))
                except Exception as e:
                    logger.warning(f"授予权限失败 {module_code}: {e}")
        
        logger.info(f"管理员 {g.current_user['username']} 创建用户 {username} 成功 (ID: {user.id}, 客户UID: {customer_uid})")
        
        return jsonify({
            'success': True,
            'message': '用户创建成功',
            'data': {
                'user_id': user.id,
                'username': user.username,
                'customer_uid': user.customer_uid,
                'need_change_password': user.is_password_changed == 0 if user.role != 'admin' else False
            }
        })
        
    except Exception as e:
        logger.error(f"创建用户失败: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return jsonify({
            'success': False,
            'message': '创建用户失败',
            'code': 'CREATE_USER_ERROR'
        }), 500

@auth_bp.route('/users/<int:user_id>', methods=['GET'])
@admin_required
@log_api_access('user_management')
@handle_exceptions
def get_user_by_id(user_id):
    """获取用户详情（仅管理员）"""
    try:
        user = auth_service.get_user_by_id(user_id)
        if not user:
            return jsonify({
                'success': False,
                'message': '用户不存在',
                'code': 'USER_NOT_FOUND'
            }), 404
        
        return jsonify({
            'success': True,
            'data': {
                'id': user.id,
                'username': user.username,
                'full_name': user.full_name,
                'email': user.email,
                'role': user.role,
                'status': user.status,
                'customer_uid': user.customer_uid,
                'is_password_changed': user.is_password_changed,
                'created_at': user.created_at.isoformat() if user.created_at else None,
                'last_login_at': user.last_login_at.isoformat() if user.last_login_at else None
            }
        })
        
    except Exception as e:
        logger.error(f"获取用户详情失败: {e}")
        return jsonify({
            'success': False,
            'message': '获取用户详情失败',
            'code': 'GET_USER_ERROR'
        }), 500

@auth_bp.route('/users/<int:user_id>', methods=['PUT'])
@admin_required
@log_api_access('user_management')
@handle_exceptions
def update_user(user_id):
    """更新用户（仅管理员）"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({
                'success': False,
                'message': '请求数据不能为空',
                'code': 'INVALID_DATA'
            }), 400
        
        success = auth_service.update_user(
            user_id=user_id,
            username=data.get('username'),
            full_name=data.get('full_name'),
            email=data.get('email'),
            role=data.get('role'),
            status=data.get('status')
        )
        
        if success:
            logger.info(f"管理员 {g.current_user['username']} 更新用户 {user_id} 成功")
            return jsonify({
                'success': True,
                'message': '用户更新成功'
            })
        else:
            return jsonify({
                'success': False,
                'message': '用户更新失败',
                'code': 'UPDATE_USER_FAILED'
            }), 400
            
    except Exception as e:
        logger.error(f"更新用户失败: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return jsonify({
            'success': False,
            'message': '更新用户失败',
            'code': 'UPDATE_USER_ERROR'
        }), 500

@auth_bp.route('/users/<int:user_id>', methods=['DELETE'])
@admin_required
@log_api_access('user_management')
@handle_exceptions
def delete_user(user_id):
    """删除用户（仅管理员）"""
    try:
        # 不能删除自己
        current_user_id = get_current_user_id()
        if current_user_id == user_id:
            return jsonify({
                'success': False,
                'message': '不能删除自己的账户',
                'code': 'CANNOT_DELETE_SELF'
            }), 400
        
        success = auth_service.delete_user(user_id)
        
        if success:
            logger.info(f"管理员 {g.current_user['username']} 删除用户 {user_id} 成功")
            return jsonify({
                'success': True,
                'message': '用户删除成功'
            })
        else:
            return jsonify({
                'success': False,
                'message': '用户删除失败',
                'code': 'DELETE_USER_FAILED'
            }), 400
            
    except Exception as e:
        logger.error(f"删除用户失败: {e}")
        return jsonify({
            'success': False,
            'message': '删除用户失败',
            'code': 'DELETE_USER_ERROR'
        }), 500

# =====================================================
# 权限管理API（仅管理员）
# =====================================================

@auth_bp.route('/permissions/modules', methods=['GET'])
@admin_required
@log_api_access('permission_management')
@handle_exceptions
def get_all_modules():
    """获取所有模块列表（仅管理员）"""
    try:
        modules = permission_service.get_all_modules()
        
        return jsonify({
            'success': True,
            'data': modules
        })
        
    except Exception as e:
        logger.error(f"获取模块列表失败: {e}")
        return jsonify({
            'success': False,
            'message': '获取模块列表失败',
            'code': 'GET_MODULES_ERROR'
        }), 500

@auth_bp.route('/permissions/user/<int:user_id>', methods=['GET'])
@admin_required
@log_api_access('permission_management')
@handle_exceptions
def get_user_permissions_by_id(user_id):
    """获取指定用户的权限（仅管理员）"""
    try:
        # 获取用户信息
        user = auth_service.get_user_by_id(user_id)
        if not user:
            return jsonify({
                'success': False,
                'message': '用户不存在',
                'code': 'USER_NOT_FOUND'
            }), 404
        
        # 获取用户权限
        permissions = permission_service.get_user_permissions(user_id)
        
        # 获取所有模块信息
        modules = permission_service.get_all_modules()
        
        # 组织权限数据
        permission_data = []
        for module in modules:
            module_code = module['module_code']
            permission_level = permissions.get(module_code, 'none')
            
            permission_data.append({
                'module_code': module_code,
                'module_name': module['module_name'],
                'description': module['description'],
                'permission_level': permission_level
            })
        
        return jsonify({
            'success': True,
            'data': {
                'user': {
                    'id': user.id,
                    'username': user.username,
                    'full_name': user.full_name,
                    'role': user.role
                },
                'permissions': permission_data
            }
        })
        
    except Exception as e:
        logger.error(f"获取用户权限失败: {e}")
        return jsonify({
            'success': False,
            'message': '获取用户权限失败',
            'code': 'GET_USER_PERMISSIONS_ERROR'
        }), 500

@auth_bp.route('/permissions/grant', methods=['POST'])
@admin_required
@validate_json_data(['user_id', 'module_code', 'permission_level'])
@log_api_access('permission_management')
@handle_exceptions
def grant_permission():
    """授予权限（仅管理员）"""
    try:
        data = g.validated_data
        user_id = data['user_id']
        module_code = data['module_code']
        permission_level = data['permission_level']
        
        # 检查用户是否存在
        user = auth_service.get_user_by_id(user_id)
        if not user:
            return jsonify({
                'success': False,
                'message': '用户不存在',
                'code': 'USER_NOT_FOUND'
            }), 404
        
        # 授予权限
        success = permission_service.grant_permission(
            user_id, module_code, permission_level, g.current_user_id
        )
        
        if success:
            logger.info(f"管理员 {g.current_user['username']} 为用户 {user.username} 授予 {module_code} 模块的 {permission_level} 权限")
            return jsonify({
                'success': True,
                'message': '权限授予成功'
            })
        else:
            return jsonify({
                'success': False,
                'message': '权限授予失败',
                'code': 'GRANT_PERMISSION_ERROR'
            }), 500
        
    except Exception as e:
        logger.error(f"授予权限失败: {e}")
        return jsonify({
            'success': False,
            'message': '授予权限失败',
            'code': 'GRANT_PERMISSION_ERROR'
        }), 500

@auth_bp.route('/permissions/revoke', methods=['POST'])
@admin_required
@validate_json_data(['user_id', 'module_code'])
@log_api_access('permission_management')
@handle_exceptions
def revoke_permission():
    """撤销权限（仅管理员）"""
    try:
        data = g.validated_data
        user_id = data['user_id']
        module_code = data['module_code']
        
        # 检查用户是否存在
        user = auth_service.get_user_by_id(user_id)
        if not user:
            return jsonify({
                'success': False,
                'message': '用户不存在',
                'code': 'USER_NOT_FOUND'
            }), 404
        
        # 撤销权限
        success = permission_service.revoke_permission(user_id, module_code)
        
        if success:
            logger.info(f"管理员 {g.current_user['username']} 撤销用户 {user.username} 的 {module_code} 模块权限")
            return jsonify({
                'success': True,
                'message': '权限撤销成功'
            })
        else:
            return jsonify({
                'success': False,
                'message': '权限撤销失败',
                'code': 'REVOKE_PERMISSION_ERROR'
            }), 500
        
    except Exception as e:
        logger.error(f"撤销权限失败: {e}")
        return jsonify({
            'success': False,
            'message': '撤销权限失败',
            'code': 'REVOKE_PERMISSION_ERROR'
        }), 500

@auth_bp.route('/permissions/batch-grant', methods=['POST'])
@admin_required
@validate_json_data(['user_id', 'permissions'])
@log_api_access('permission_management')
@handle_exceptions
def batch_grant_permissions():
    """批量授予权限（仅管理员）"""
    try:
        data = g.validated_data
        user_id = data['user_id']
        permissions = data['permissions']
        
        # 检查用户是否存在
        user = auth_service.get_user_by_id(user_id)
        if not user:
            return jsonify({
                'success': False,
                'message': '用户不存在',
                'code': 'USER_NOT_FOUND'
            }), 404
        
        # 验证权限数据
        is_valid, error_msg = permission_service.validate_permission_data(permissions)
        if not is_valid:
            return jsonify({
                'success': False,
                'message': error_msg,
                'code': 'INVALID_PERMISSION_DATA'
            }), 400
        
        # 批量授予权限
        success = permission_service.batch_grant_permissions(
            user_id, permissions, g.current_user_id
        )
        
        if success:
            logger.info(f"管理员 {g.current_user['username']} 为用户 {user.username} 批量授予权限")
            return jsonify({
                'success': True,
                'message': '批量权限授予成功'
            })
        else:
            return jsonify({
                'success': False,
                'message': '批量权限授予失败',
                'code': 'BATCH_GRANT_ERROR'
            }), 500
        
    except Exception as e:
        logger.error(f"批量授予权限失败: {e}")
        return jsonify({
            'success': False,
            'message': '批量授予权限失败',
            'code': 'BATCH_GRANT_ERROR'
        }), 500
