"""
API模块 - 提供RESTful API接口

包含以下主要功能:
- 客户管理API
- 信号源管理API
- 策略管理API
- 交易管理API
- 风险控制API
- 限价跟单API
"""

from .api_server import app, get_trade_service, init_db, get_global_is_demo

__all__ = [
    "app",
    "get_trade_service", 
    "init_db",
    "get_global_is_demo"
] 