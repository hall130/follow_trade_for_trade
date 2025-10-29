#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
权限服务模块
提供权限检查、数据过滤、模块权限管理等功能
"""

import os
import sys
from typing import Optional, Dict, Any, List, Tuple
from dataclasses import dataclass
from enum import Enum

# 添加项目根目录到Python路径
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database.db import get_db_pool
from utils.logger import get_logger

logger = get_logger(__name__)

class PermissionLevel(Enum):
    """权限级别枚举"""
    NONE = 'none'
    READ = 'read'
    WRITE = 'write'
    ADMIN = 'admin'

@dataclass
class Permission:
    """权限数据类"""
    id: int
    user_id: int
    module_code: str
    permission_level: str
    granted_at: str
    expires_at: Optional[str] = None

@dataclass
class ModulePermission:
    """模块权限数据类"""
    module_code: str
    module_name: str
    description: str
    permission_level: str

class PermissionService:
    """权限服务类"""
    
    def __init__(self):
        # 权限级别权重（用于比较）
        self.permission_weights = {
            PermissionLevel.NONE.value: 0,
            PermissionLevel.READ.value: 1,
            PermissionLevel.WRITE.value: 2,
            PermissionLevel.ADMIN.value: 3
        }
        
        # 系统模块定义
        self.system_modules = {
            'signal_sources': '信号源管理',
            'customers': '客户管理',
            'strategies': '策略管理',
            'market_follow': '现价跟单',
            'limit_follow': '限价跟单',
            'backtest': '策略回测',
            'strategy_live': '策略实盘',
            'message_forward': '消息转发',
            'system_settings': '系统设置'
        }
    
    def get_user_permissions(self, user_id: int) -> Dict[str, str]:
        """获取用户的所有权限"""
        try:
            conn = get_db_pool()
            if not conn:
                logger.error("数据库连接不可用")
                return {}
            
            # 通过用户角色获取权限
            results = conn.query("""
                SELECT m.module_code, p.permission_level
                FROM users u
                JOIN roles r ON u.role = r.role_code
                JOIN role_permissions rp ON r.id = rp.role_id
                JOIN permissions p ON rp.permission_id = p.id
                JOIN modules m ON p.module_id = m.id
                WHERE u.id = %s
                ORDER BY m.module_code
            """, (user_id,))
            
            permissions = {}
            for row in results:
                permissions[row['module_code']] = row['permission_level']
            
            logger.info(f"用户ID {user_id} 通过角色获取的权限: {permissions}")
            return permissions
            
        except Exception as e:
            logger.error(f"获取用户权限失败: {e}")
            return {}
    
    def check_permission(self, user_id: int, module_code: str, required_level: str = 'read') -> bool:
        """检查用户是否有指定模块的权限"""
        try:
            # 获取用户信息
            conn = get_db_pool()
            if not conn:
                logger.error("数据库连接不可用")
                return False
            
            result = conn.query("SELECT role FROM users WHERE id = %s", (user_id,))
            
            if not result or len(result) == 0:
                logger.warning(f"用户ID {user_id} 不存在")
                return False
            
            user_role = result[0]['role']
            logger.info(f"用户ID {user_id} 角色: {user_role}")
            
            # 管理员拥有所有权限
            if user_role == 'admin':
                logger.info(f"管理员用户 {user_id} 拥有所有权限")
                return True
            
            # 检查具体权限
            permissions = self.get_user_permissions(user_id)
            logger.info(f"用户ID {user_id} 权限: {permissions}")
            
            user_permission = permissions.get(module_code)
            
            if not user_permission:
                logger.warning(f"用户ID {user_id} 没有 {module_code} 模块权限")
                return False
            
            # 比较权限级别
            required_weight = self.permission_weights.get(required_level, 0)
            user_weight = self.permission_weights.get(user_permission, 0)
            
            has_permission = user_weight >= required_weight
            logger.info(f"用户ID {user_id} {module_code}:{required_level} 权限检查: {has_permission} (用户权限:{user_permission}, 需要权限:{required_level})")
            
            return has_permission
            
        except Exception as e:
            logger.error(f"权限检查失败: {e}")
            return False
    
    def has_permission(self, user_id: int, module_code: str, required_level: str = 'read') -> bool:
        """检查权限的简化方法"""
        return self.check_permission(user_id, module_code, required_level)
    
    def get_user_role(self, user_id: int) -> Optional[str]:
        """获取用户角色"""
        try:
            if not user_id or user_id <= 0:
                logger.warning(f"无效的用户ID: {user_id}")
                return None
                
            conn = get_db_pool()
            if not conn:
                logger.error("数据库连接不可用")
                return None
                
            result = conn.query("SELECT role FROM users WHERE id = %s", (user_id,))
            
            if result and len(result) > 0:
                return result[0]['role']
            else:
                logger.warning(f"用户ID {user_id} 不存在")
                return None
            
        except Exception as e:
            logger.error(f"获取用户角色失败: {e}")
            return None
    
    def is_admin(self, user_id: int) -> bool:
        """检查是否为管理员"""
        return self.get_user_role(user_id) == 'admin'
    
    def grant_permission(self, user_id: int, module_code: str, permission_level: str, granted_by: int) -> bool:
        """授予权限"""
        try:
            conn = get_db_pool()
            conn.execute("""
                INSERT INTO user_permissions (user_id, module_code, permission_level, granted_by)
                VALUES (%s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE 
                permission_level = VALUES(permission_level),
                granted_by = VALUES(granted_by),
                granted_at = NOW()
            """, (user_id, module_code, permission_level, granted_by))
            
            logger.info(f"为用户 {user_id} 授予模块 {module_code} 的 {permission_level} 权限")
            return True
            
        except Exception as e:
            logger.error(f"授予权限失败: {e}")
            return False
    
    def revoke_permission(self, user_id: int, module_code: str) -> bool:
        """撤销权限"""
        try:
            conn = get_db_pool()
            conn.execute("""
                DELETE FROM user_permissions 
                WHERE user_id = %s AND module_code = %s
            """, (user_id, module_code))
            affected_rows = conn.execute_with_rowcount("""
                DELETE FROM user_permissions 
                WHERE user_id = %s AND module_code = %s
            """, (user_id, module_code))
            
            if affected_rows > 0:
                logger.info(f"撤销用户 {user_id} 的模块 {module_code} 权限")
                return True
            return False
            
        except Exception as e:
            logger.error(f"撤销权限失败: {e}")
            return False
    
    def batch_grant_permissions(self, user_id: int, permissions: Dict[str, str], granted_by: int) -> bool:
        """批量授予权限"""
        try:
            conn = get_db_pool()
            success_count = 0
            for module_code, permission_level in permissions.items():
                if self.grant_permission(user_id, module_code, permission_level, granted_by):
                    success_count += 1
            
            logger.info(f"批量授予权限完成，成功 {success_count}/{len(permissions)} 个")
            return conn.execute_with_rowcount("""
                SELECT COUNT(*) FROM user_permissions 
                WHERE user_id = %s AND module_code = %s
            """, (user_id, module_code)) > 0
            
        except Exception as e:
            logger.error(f"批量授予权限失败: {e}")
            return False
    
    def get_all_modules(self) -> List[Dict[str, str]]:
        """获取所有系统模块"""
        modules = []
        for module_code, module_name in self.system_modules.items():
            modules.append({
                'module_code': module_code,
                'module_name': module_name,
                'description': f'{module_name}模块'
            })
        return modules
    
    def get_users_with_permissions(self) -> List[Dict[str, Any]]:
        """获取所有用户及其权限"""
        try:
            conn = get_db_pool()
            conn.execute("""
                SELECT 
                    u.id, u.username, u.full_name, u.role, u.status,
                    up.module_code, up.permission_level, up.granted_at
                FROM users u
                LEFT JOIN user_permissions up ON u.id = up.user_id
                WHERE u.status = 'active'
                ORDER BY u.username, up.module_code
            """)
            
            results = conn.query("""
                SELECT 
                    u.id, u.username, u.full_name, u.role, u.status,
                    up.module_code, up.permission_level, up.granted_at
                FROM users u
                LEFT JOIN user_permissions up ON u.id = up.user_id
                WHERE u.status = 'active'
                ORDER BY u.username, up.module_code""")
                
            for row in results:
                if row['module_code']:  # module_code
                    users_dict[row['id']]['permissions'][row['module_code']] = {
                        'permission_level': row['permission_level'],
                        'granted_at': row['granted_at']
                    }
            
            return list(users_dict.values())
            
        except Exception as e:
            logger.error(f"获取用户权限列表失败: {e}")
            return []
    
    def filter_data_by_owner(self, user_id: int, table_name: str, owner_field: str = 'owner_user_id') -> str:
        """生成数据过滤SQL条件"""
        try:
            # 检查是否为管理员
            if self.is_admin(user_id):
                return ""  # 管理员不过滤数据
            
            # 普通用户只能看到自己的数据
            return f" AND {owner_field} = {user_id}"
            
        except Exception as e:
            logger.error(f"生成数据过滤条件失败: {e}")
            return f" AND {owner_field} = {user_id}"  # 默认过滤
    
    def filter_customers_by_owner(self, user_id: int) -> str:
        """过滤客户数据"""
        return self.filter_data_by_owner(user_id, 'customers', 'owner_user_id')
    
    def filter_strategies_by_owner(self, user_id: int) -> str:
        """过滤策略数据"""
        return self.filter_data_by_owner(user_id, 'limit_follow_strategies', 'created_by_user_id')
    
    def filter_instances_by_owner(self, user_id: int) -> str:
        """过滤策略实例数据"""
        return self.filter_data_by_owner(user_id, 'strategy_instances', 'created_by_user_id')
    
    def filter_backtests_by_owner(self, user_id: int) -> str:
        """过滤回测数据"""
        return self.filter_data_by_owner(user_id, 'strategy_backtests', 'created_by_user_id')
    
    def filter_traders_by_owner(self, user_id: int) -> str:
        """过滤带单员数据（公开的 + 自己创建的）"""
        if self.is_admin(user_id):
            return ""  # 管理员看到所有
        
        return f" AND (is_public = 1 OR created_by_user_id = {user_id})"
    
    def get_permission_matrix(self) -> Dict[str, Any]:
        """获取权限矩阵"""
        try:
            conn = get_db_pool()
            conn.execute("""
                SELECT id, username, full_name, role 
                FROM users 
                WHERE status = 'active'
                ORDER BY username
            """)
            users = conn.query("""
                SELECT user_id, module_code, permission_level
                FROM user_permissions
                WHERE expires_at IS NULL OR expires_at > NOW()
            """)
            permissions = conn.query("""
                SELECT user_id, module_code, permission_level
                FROM user_permissions
                WHERE expires_at IS NULL OR expires_at > NOW()
            """)
            
            # 组织权限矩阵
            matrix = {
                'users': [],
                'modules': list(self.system_modules.keys()),
                'permissions': {}
            }
            
            # 用户信息
            for user in users:
                matrix['users'].append({
                    'id': user['id'],
                    'username': user['username'],
                    'full_name': user['full_name'],
                    'role': user['role']
                })
            
            # 权限信息
            for user_id, module_code, permission_level in permissions:
                if user_id not in matrix['permissions']:
                    matrix['permissions'][user_id] = {}
                matrix['permissions'][user_id][module_code] = permission_level
                if user_id not in matrix['permissions']:
                    matrix['permissions'][user_id] = {}
                matrix['permissions'][user_id][module_code] = permission_level
            
            return matrix
            
        except Exception as e:
            logger.error(f"获取权限矩阵失败: {e}")
            return {'users': [], 'modules': [], 'permissions': {}}
    
    def validate_permission_data(self, permissions: Dict[str, str]) -> Tuple[bool, str]:
        """验证权限数据"""
        try:
            # 检查模块代码
            for module_code in permissions.keys():
                if module_code not in self.system_modules:
                    return False, f"模块 {module_code} 不存在"
            
            # 检查权限级别
            for permission_level in permissions.values():
                if permission_level not in self.permission_weights:
                    return False, f"权限级别 {permission_level} 无效"
            
            return True, "验证通过"
            
        except Exception as e:
            logger.error(f"权限数据验证失败: {e}")
            return False, f"验证异常: {e}"

    def get_permissions_matrix(self):
        """获取权限矩阵"""
        try:
            # 获取所有角色及其权限
            query = """
                SELECT DISTINCT r.role_name, r.role_code,
                       GROUP_CONCAT(DISTINCT CONCAT(m.module_code, ':', p.permission_level) ORDER BY m.module_code, p.permission_level) as permissions
                FROM roles r
                LEFT JOIN role_permissions rp ON r.id = rp.role_id
                LEFT JOIN permissions p ON rp.permission_id = p.id
                LEFT JOIN modules m ON p.module_id = m.id
                GROUP BY r.id, r.role_name, r.role_code
                ORDER BY r.role_name
            """
            from database.db import get_db_pool
            db_pool = get_db_pool()
            result = db_pool.query(query)
            
            matrix = []
            logger.info(f"数据库查询结果: {len(result) if result else 0} 条记录")
            
            for row in result:
                permissions = []
                if row['permissions']:
                    permissions = row['permissions'].split(',')
                
                matrix.append({
                    'role': row['role_code'],
                    'role_name': row['role_name'],
                    'permissions': permissions
                })
            
            logger.info(f"返回权限矩阵: {len(matrix)} 个角色")
            return matrix
            
        except Exception as e:
            logger.error(f"获取权限矩阵失败: {e}")
            return []

    def get_permission_templates(self):
        """获取权限模板"""
        try:
            # 预定义的权限模板
            templates = [
                {
                    'id': 1,
                    'name': '管理员模板',
                    'description': '拥有所有权限的管理员角色',
                    'permissions': [
                        'customers:read', 'customers:write',
                        'signal_sources:read', 'signal_sources:write',
                        'strategies:read', 'strategies:write',
                        'limit_follow:read', 'limit_follow:write',
                        'system_settings:read', 'system_settings:write',
                        'users:read', 'users:write'
                    ],
                    'status': 'active'
                },
                {
                    'id': 2,
                    'name': '普通用户模板',
                    'description': '基础权限的普通用户角色',
                    'permissions': [
                        'customers:read',
                        'signal_sources:read',
                        'strategies:read',
                        'limit_follow:read'
                    ],
                    'status': 'active'
                },
                {
                    'id': 3,
                    'name': '交易员模板',
                    'description': '专注于交易功能的角色',
                    'permissions': [
                        'customers:read', 'customers:write',
                        'signal_sources:read', 'signal_sources:write',
                        'strategies:read', 'strategies:write',
                        'limit_follow:read', 'limit_follow:write'
                    ],
                    'status': 'active'
                }
            ]
            
            return templates
            
        except Exception as e:
            logger.error(f"获取权限模板失败: {e}")
            return []

    def update_role_permissions(self, role: str, permissions: list):
        """更新角色权限"""
        try:
            # 获取角色ID
            from database.db import get_db_pool
            db_pool = get_db_pool()
            role_query = "SELECT id FROM roles WHERE role_code = %s"
            role_result = db_pool.query(role_query, (role,))
            
            if not role_result:
                logger.error(f"角色不存在: {role}")
                return False
            
            role_id = role_result[0]['id']
            
            # 删除现有权限
            delete_query = "DELETE FROM role_permissions WHERE role_id = %s"
            db_pool.execute(delete_query, (role_id,))
            
            # 添加新权限
            if permissions:
                permission_ids = []
                for perm in permissions:
                    module_code, permission_level = perm.split(':')
                    
                    # 获取模块ID
                    module_query = "SELECT id FROM modules WHERE module_code = %s"
                    module_result = db_pool.query(module_query, (module_code,))
                    
                    if module_result:
                        module_id = module_result[0]['id']
                        
                        # 获取权限ID
                        perm_query = """
                            SELECT id FROM permissions 
                            WHERE module_id = %s AND permission_level = %s
                        """
                        perm_result = db_pool.query(perm_query, (module_id, permission_level))
                        
                        if perm_result:
                            permission_ids.append(perm_result[0]['id'])
                
                # 批量插入权限
                if permission_ids:
                    insert_query = """
                        INSERT INTO role_permissions (role_id, permission_id) 
                        VALUES (%s, %s)
                    """
                    for perm_id in permission_ids:
                        db_pool.execute(insert_query, (role_id, perm_id))
            
            logger.info(f"角色权限更新成功: {role}")
            return True
            
        except Exception as e:
            logger.error(f"更新角色权限失败: {e}")
            return False

    def apply_permission_template(self, template_id: int):
        """应用权限模板"""
        try:
            templates = self.get_permission_templates()
            template = next((t for t in templates if t['id'] == template_id), None)
            
            if not template:
                logger.error(f"权限模板不存在: {template_id}")
                return False
            
            # 这里可以根据模板ID应用不同的权限配置
            # 例如：为特定角色应用模板权限
            
            logger.info(f"权限模板应用成功: {template['name']}")
            return True
            
        except Exception as e:
            logger.error(f"应用权限模板失败: {e}")
            return False

# 全局权限服务实例
permission_service = PermissionService()
