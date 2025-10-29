#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
认证模块初始化文件
"""

# 可选导入auth_service，避免bcrypt依赖问题
try:
    from .auth_service import AuthService, auth_service
    AUTH_SERVICE_AVAILABLE = True
except ImportError as e:
    print(f"警告: auth_service不可用: {e}")
    AUTH_SERVICE_AVAILABLE = False
    AuthService = None
    auth_service = None

# 可选导入permission_service
try:
    from .permission_service import PermissionService, permission_service
    PERMISSION_SERVICE_AVAILABLE = True
except ImportError as e:
    print(f"警告: permission_service不可用: {e}")
    PERMISSION_SERVICE_AVAILABLE = False
    PermissionService = None
    permission_service = None

# 导入装饰器（这些通常不依赖外部包）
from .decorators import (
    login_required,
    require_permission,
    admin_required,
    filter_by_owner,
    filter_customers,
    filter_strategies,
    filter_instances,
    filter_backtests,
    filter_traders,
    validate_json_data,
    log_api_access,
    handle_exceptions,
    get_current_user_id,
    get_current_user
)

__all__ = [
    'login_required',
    'require_permission',
    'admin_required',
    'filter_by_owner',
    'filter_customers',
    'filter_strategies',
    'filter_instances',
    'filter_backtests',
    'filter_traders',
    'validate_json_data',
    'log_api_access',
    'handle_exceptions',
    'get_current_user_id',
    'get_current_user'
]

# 只有在可用时才添加到__all__
if AUTH_SERVICE_AVAILABLE:
    __all__.extend(['AuthService', 'auth_service'])

if PERMISSION_SERVICE_AVAILABLE:
    __all__.extend(['PermissionService', 'permission_service'])
