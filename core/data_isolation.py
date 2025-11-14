#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
数据隔离模块（增强版）
确保每个用户的数据完全隔离，防止数据泄露
注意：此模块是对 auth/decorators.py 中 filter_by_owner 的增强，提供更多功能
如果 auth 模块可用，优先使用 auth 模块的装饰器
"""

from functools import wraps
from typing import Optional, Callable, Any
from flask import g, request, jsonify
from utils.logger import logger

# 尝试导入现有的 auth 装饰器
try:
    from auth.decorators import filter_by_owner as auth_filter_by_owner
    AUTH_DECORATORS_AVAILABLE = True
except ImportError:
    AUTH_DECORATORS_AVAILABLE = False
    auth_filter_by_owner = None


class DataIsolation:
    """数据隔离管理器"""
    
    @staticmethod
    def get_user_id() -> Optional[int]:
        """获取当前用户ID"""
        if hasattr(g, 'current_user_id'):
            return g.current_user_id
        return None
    
    @staticmethod
    def is_admin() -> bool:
        """检查是否为管理员"""
        if hasattr(g, 'current_user'):
            return getattr(g.current_user, 'role', 'user') == 'admin'
        return False
    
    @staticmethod
    def require_user_id():
        """要求用户ID的装饰器"""
        def decorator(func):
            @wraps(func)
            def wrapper(*args, **kwargs):
                user_id = DataIsolation.get_user_id()
                if not user_id:
                    return jsonify({
                        'success': False,
                        'message': '需要登录才能访问此资源'
                    }), 401
                return func(*args, **kwargs)
            return wrapper
        return decorator
    
    @staticmethod
    def filter_by_owner(table_name: str, owner_field: str = 'owner_user_id'):
        """
        数据隔离装饰器 - 自动过滤数据
        
        Args:
            table_name: 表名
            owner_field: 所有者字段名
        """
        def decorator(func):
            @wraps(func)
            def wrapper(*args, **kwargs):
                user_id = DataIsolation.get_user_id()
                is_admin = DataIsolation.is_admin()
                
                # 管理员不过滤数据
                if is_admin:
                    # 将过滤条件设为空，允许管理员查看所有数据
                    if not hasattr(g, 'data_filters'):
                        g.data_filters = {}
                    g.data_filters[table_name] = ""
                elif user_id:
                    # 普通用户只能看到自己的数据
                    filter_condition = f"{owner_field} = {user_id}"
                    if not hasattr(g, 'data_filters'):
                        g.data_filters = {}
                    g.data_filters[table_name] = filter_condition
                else:
                    # 未登录用户不能访问
                    return jsonify({
                        'success': False,
                        'message': '需要登录才能访问此资源'
                    }), 401
                
                return func(*args, **kwargs)
            return wrapper
        return decorator
    
    @staticmethod
    def validate_ownership(resource_id: Any, table_name: str, id_field: str = 'id', owner_field: str = 'owner_user_id'):
        """
        验证资源所有权
        
        Args:
            resource_id: 资源ID
            table_name: 表名
            id_field: ID字段名
            owner_field: 所有者字段名
            
        Returns:
            True 表示有权限，False 表示无权限
        """
        user_id = DataIsolation.get_user_id()
        is_admin = DataIsolation.is_admin()
        
        # 管理员有所有权限
        if is_admin:
            return True
        
        # 未登录用户无权限
        if not user_id:
            return False
        
        try:
            from database.global_db_manager import get_global_db_pool
            db_pool = get_global_db_pool()
            if not db_pool:
                logger.error("[数据隔离] 数据库连接池不可用")
                return False
            
            # 查询资源的所有者
            result = db_pool.query(
                f"SELECT {owner_field} FROM {table_name} WHERE {id_field} = %s LIMIT 1",
                (resource_id,)
            )
            
            if not result:
                # 资源不存在，返回False（防止信息泄露）
                return False
            
            owner_id = result[0].get(owner_field)
            return owner_id == user_id
            
        except Exception as e:
            logger.error(f"[数据隔离] 验证资源所有权失败: {e}")
            return False  # 出错时拒绝访问，保证安全
    
    @staticmethod
    def ensure_ownership(resource_id: Any, table_name: str, id_field: str = 'id', owner_field: str = 'owner_user_id'):
        """
        确保资源所有权的装饰器（用于修改/删除操作）
        
        Args:
            resource_id: 资源ID（可以从请求参数中获取）
            table_name: 表名
            id_field: ID字段名
            owner_field: 所有者字段名
        """
        def decorator(func):
            @wraps(func)
            def wrapper(*args, **kwargs):
                # 尝试从kwargs或request中获取resource_id
                rid = resource_id
                if callable(resource_id):
                    rid = resource_id(*args, **kwargs)
                elif resource_id is None:
                    # 尝试从请求参数中获取
                    if request.method == 'GET':
                        rid = request.args.get('id') or request.args.get(f'{id_field}')
                    else:
                        data = request.get_json() or {}
                        rid = data.get('id') or data.get(f'{id_field}')
                
                if not rid:
                    return jsonify({
                        'success': False,
                        'message': '缺少资源ID'
                    }), 400
                
                # 验证所有权
                if not DataIsolation.validate_ownership(rid, table_name, id_field, owner_field):
                    logger.warning(
                        f"[数据隔离] 用户 {DataIsolation.get_user_id()} 尝试访问不属于自己的资源 "
                        f"{table_name}.{id_field}={rid}"
                    )
                    return jsonify({
                        'success': False,
                        'message': '无权访问此资源'
                    }), 403
                
                return func(*args, **kwargs)
            return wrapper
        return decorator
    
    @staticmethod
    def auto_set_owner(table_name: str, owner_field: str = 'owner_user_id'):
        """
        自动设置所有者的装饰器（用于创建操作）
        
        Args:
            table_name: 表名
            owner_field: 所有者字段名
        """
        def decorator(func):
            @wraps(func)
            def wrapper(*args, **kwargs):
                user_id = DataIsolation.get_user_id()
                
                if not user_id:
                    return jsonify({
                        'success': False,
                        'message': '需要登录才能创建资源'
                    }), 401
                
                # 在g中设置owner，供后续使用
                if not hasattr(g, 'auto_owner'):
                    g.auto_owner = {}
                g.auto_owner[table_name] = {
                    'field': owner_field,
                    'value': user_id
                }
                
                return func(*args, **kwargs)
            return wrapper
        return decorator


# 便捷函数
def require_user_id():
    """要求用户ID的装饰器"""
    return DataIsolation.require_user_id()


def filter_by_owner(table_name: str, owner_field: str = 'owner_user_id'):
    """
    数据隔离装饰器（增强版）
    
    注意：如果 auth 模块可用，此函数会优先使用 auth 模块的装饰器
    如果 auth 模块不可用，则使用本模块的实现
    """
    if AUTH_DECORATORS_AVAILABLE and auth_filter_by_owner:
        # 使用 auth 模块的装饰器（避免冲突）
        logger.debug(f"[数据隔离] 使用 auth 模块的 filter_by_owner")
        return auth_filter_by_owner(owner_field)
    else:
        # 使用本模块的实现
        return DataIsolation.filter_by_owner(table_name, owner_field)


def validate_ownership(resource_id: Any, table_name: str, id_field: str = 'id', owner_field: str = 'owner_user_id'):
    """验证资源所有权"""
    return DataIsolation.validate_ownership(resource_id, table_name, id_field, owner_field)


def ensure_ownership(resource_id: Any, table_name: str, id_field: str = 'id', owner_field: str = 'owner_user_id'):
    """确保资源所有权的装饰器"""
    return DataIsolation.ensure_ownership(resource_id, table_name, id_field, owner_field)


def auto_set_owner(table_name: str, owner_field: str = 'owner_user_id'):
    """自动设置所有者的装饰器"""
    return DataIsolation.auto_set_owner(table_name, owner_field)

