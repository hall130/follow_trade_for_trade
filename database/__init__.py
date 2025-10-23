"""
数据库模块 - 处理数据库连接和操作

包含以下功能:
- MySQL连接池管理
- 数据库操作封装
- 连接池配置
"""

# 使用global_db_manager代替直接导入db模块
from .global_db_manager import get_global_db_pool, get_global_db_pool_async

__all__ = [
    "get_global_db_pool",
    "get_global_db_pool_async"
] 