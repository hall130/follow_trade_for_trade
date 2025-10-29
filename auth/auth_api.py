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
from utils.logger import get_logger

logger = get_logger(__name__)

# 创建认证蓝图
auth_bp = Blueprint('auth', __name__, url_prefix='/api/v1/auth')

# =====================================================
# 认证相关API
# =====================================================

@auth_bp.route('/login', methods=['POST'])
@validate_json_data(['username', 'password'])
@log_api_access('auth')
@handle_exceptions
def login():
    """用户登录"""
    try:
        data = g.validated_data
        username = data['username']
        password = data['password']
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
        
        return jsonify({
            'success': True,
            'message': '登录成功',
            'data': {
                'user': user_info,
                'session_id': session_obj.session_id,
                'token': session_obj.token,
                'permissions': permissions,
                'expires_at': session_obj.expires_at.isoformat()
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
@validate_json_data(['old_password', 'new_password'])
@log_api_access('auth')
@handle_exceptions
def change_password():
    """修改密码"""
    try:
        data = g.validated_data
        user_id = g.current_user_id
        old_password = data['old_password']
        new_password = data['new_password']
        
        # 验证新密码长度
        if len(new_password) < 6:
            return jsonify({
                'success': False,
                'message': '新密码长度不能少于6位',
                'code': 'PASSWORD_TOO_SHORT'
            }), 400
        
        # 修改密码
        success = auth_service.change_password(user_id, old_password, new_password)
        
        if success:
            logger.info(f"用户 {g.current_user['username']} 修改密码成功")
            return jsonify({
                'success': True,
                'message': '密码修改成功'
            })
        else:
            return jsonify({
                'success': False,
                'message': '原密码错误',
                'code': 'INVALID_OLD_PASSWORD'
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
@validate_json_data(['username', 'password', 'full_name', 'email', 'role'])
@log_api_access('user_management')
@handle_exceptions
def create_user():
    """创建用户（仅管理员）"""
    try:
        data = g.validated_data
        username = data['username']
        password = data['password']
        full_name = data['full_name']
        email = data['email']
        role = data['role']
        
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
        
        # 加密密码
        password_hash = auth_service.hash_password(password)
        
        # 创建用户
        from database.db import get_db_pool
        conn = get_db_pool()
        
        try:
            user_id = conn.execute("""
                INSERT INTO users (username, password_hash, full_name, email, role, status)
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (username, password_hash, full_name, email, role, 'active'))
            
            # 为普通用户授予基本权限
            if role == 'user':
                basic_permissions = ['customers', 'strategies', 'backtest', 'strategy_live']
                for module_code in basic_permissions:
                    conn.execute("""
                        INSERT INTO user_permissions (user_id, module_code, permission_level, granted_by)
                        VALUES (%s, %s, %s, %s)
                    """, (user_id, module_code, 'write', g.current_user_id))            
            logger.info(f"管理员 {g.current_user['username']} 创建用户 {username} 成功")
            
            return jsonify({
                'success': True,
                'message': '用户创建成功',
                'data': {'user_id': user_id}
            })
            
        except Exception as e:
            if 'Duplicate entry' in str(e):
                return jsonify({
                    'success': False,
                    'message': '用户名已存在',
                    'code': 'USERNAME_EXISTS'
                }), 400
            raise e
        
    except Exception as e:
        logger.error(f"创建用户失败: {e}")
        return jsonify({
            'success': False,
            'message': '创建用户失败',
            'code': 'CREATE_USER_ERROR'
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
