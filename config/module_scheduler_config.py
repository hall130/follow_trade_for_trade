#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
模块调度配置文件 - 定义各个模块的调度参数和配置

包含:
- 模块启动顺序配置
- 模块依赖关系配置
- 模块超时配置
- 重试策略配置
"""

import os
from typing import Dict, List, Any

# 模块启动配置
MODULE_STARTUP_CONFIG = {
    "database": {
        "priority": 1,
        "timeout": 30,
        "retry_count": 3,
        "retry_delay": 5,
        "required": True,
        "description": "数据库连接模块"
    },
    "config": {
        "priority": 1,
        "timeout": 10,
        "retry_count": 2,
        "retry_delay": 2,
        "required": True,
        "description": "配置管理模块"
    },
    "exchange": {
        "priority": 2,
        "timeout": 60,
        "retry_count": 3,
        "retry_delay": 10,
        "required": True,
        "description": "交易所客户端模块",
        "dependencies": ["config"]
    },
    "trade_service": {
        "priority": 3,
        "timeout": 45,
        "retry_count": 2,
        "retry_delay": 5,
        "required": True,
        "description": "交易服务模块",
        "dependencies": ["database", "exchange"]
    },
    "signal_service": {
        "priority": 3,
        "timeout": 45,
        "retry_count": 2,
        "retry_delay": 5,
        "required": True,
        "description": "信号服务模块",
        "dependencies": ["database", "exchange"]
    },
    "limit_follow_service": {
        "priority": 4,
        "timeout": 60,
        "retry_count": 2,
        "retry_delay": 5,
        "required": False,
        "description": "限价跟单服务模块",
        "dependencies": ["database", "exchange"]
    },
    "limit_follow_executor": {
        "priority": 5,
        "timeout": 60,
        "retry_count": 2,
        "retry_delay": 5,
        "required": False,
        "description": "限价跟单执行器模块",
        "dependencies": ["database", "exchange", "limit_follow_service"]
    },
    "api_server": {
        "priority": 6,
        "timeout": 30,
        "retry_count": 2,
        "retry_delay": 5,
        "required": True,
        "description": "API服务器模块",
        "dependencies": ["database", "trade_service", "signal_service"]
    }
}

# 模块健康检查配置
MODULE_HEALTH_CHECK_CONFIG = {
    "check_interval": 30,  # 健康检查间隔（秒）
    "timeout": 10,         # 健康检查超时时间
    "max_failures": 3,     # 最大失败次数
    "recovery_timeout": 300,  # 恢复超时时间
}

# 模块监控配置
MODULE_MONITORING_CONFIG = {
    "enable_metrics": True,
    "metrics_interval": 60,  # 指标收集间隔（秒）
    "log_level": "INFO",
    "performance_thresholds": {
        "response_time": 1000,  # 响应时间阈值（毫秒）
        "error_rate": 0.05,     # 错误率阈值（5%）
        "memory_usage": 0.8,    # 内存使用率阈值（80%）
        "cpu_usage": 0.8        # CPU使用率阈值（80%）
    }
}

# 模块间通信配置
MODULE_COMMUNICATION_CONFIG = {
    "enable_events": True,
    "event_queue_size": 1000,
    "event_timeout": 30,
    "enable_callbacks": True,
    "callback_timeout": 60,
}

# 错误处理和恢复配置
ERROR_HANDLING_CONFIG = {
    "enable_auto_recovery": True,
    "max_recovery_attempts": 3,
    "recovery_delay": 30,
    "circuit_breaker": {
        "enabled": True,
        "failure_threshold": 5,
        "recovery_timeout": 300,
        "expected_exception": Exception
    }
}

# 性能优化配置
PERFORMANCE_CONFIG = {
    "enable_connection_pooling": True,
    "connection_pool_size": 10,
    "enable_caching": True,
    "cache_ttl": 300,
    "enable_async_operations": True,
    "max_concurrent_operations": 100,
}

# 安全配置
SECURITY_CONFIG = {
    "enable_rate_limiting": True,
    "rate_limit_per_minute": 1000,
    "enable_authentication": True,
    "enable_authorization": True,
    "session_timeout": 3600,
}

def get_module_config(module_name: str) -> Dict[str, Any]:
    """获取指定模块的配置"""
    return MODULE_STARTUP_CONFIG.get(module_name, {})

def get_all_modules() -> List[str]:
    """获取所有模块名称"""
    return list(MODULE_STARTUP_CONFIG.keys())

def get_required_modules() -> List[str]:
    """获取必需的模块"""
    return [
        name for name, config in MODULE_STARTUP_CONFIG.items() 
        if config.get("required", False)
    ]

def get_optional_modules() -> List[str]:
    """获取可选的模块"""
    return [
        name for name, config in MODULE_STARTUP_CONFIG.items() 
        if not config.get("required", False)
    ]

def get_module_dependencies(module_name: str) -> List[str]:
    """获取指定模块的依赖"""
    config = get_module_config(module_name)
    return config.get("dependencies", [])

def get_module_priority(module_name: str) -> int:
    """获取指定模块的优先级"""
    config = get_module_config(module_name)
    return config.get("priority", 999)

def get_sorted_modules() -> List[str]:
    """获取按优先级排序的模块列表"""
    return sorted(
        MODULE_STARTUP_CONFIG.keys(),
        key=lambda x: get_module_priority(x)
    )

def validate_module_config() -> List[str]:
    """验证模块配置的有效性"""
    errors = []
    
    for module_name, config in MODULE_STARTUP_CONFIG.items():
        # 检查依赖是否存在
        dependencies = config.get("dependencies", [])
        for dep in dependencies:
            if dep not in MODULE_STARTUP_CONFIG:
                errors.append(f"模块 {module_name} 的依赖 {dep} 不存在")
        
        # 检查优先级是否为正数
        priority = config.get("priority", 0)
        if priority <= 0:
            errors.append(f"模块 {module_name} 的优先级必须大于0")
    
    return errors

def get_environment_specific_config() -> Dict[str, Any]:
    """获取环境特定的配置"""
    env = os.getenv("ENVIRONMENT", "development").lower()
    
    if env == "production":
        return {
            "log_level": "WARNING",
            "enable_debug": False,
            "performance_thresholds": {
                "response_time": 500,
                "error_rate": 0.01,
                "memory_usage": 0.9,
                "cpu_usage": 0.9
            }
        }
    elif env == "testing":
        return {
            "log_level": "DEBUG",
            "enable_debug": True,
            "performance_thresholds": {
                "response_time": 2000,
                "error_rate": 0.1,
                "memory_usage": 0.6,
                "cpu_usage": 0.6
            }
        }
    else:  # development
        return {
            "log_level": "INFO",
            "enable_debug": True,
            "performance_thresholds": {
                "response_time": 1000,
                "error_rate": 0.05,
                "memory_usage": 0.8,
                "cpu_usage": 0.8
            }
        }

# 导出配置
__all__ = [
    "MODULE_STARTUP_CONFIG",
    "MODULE_HEALTH_CHECK_CONFIG", 
    "MODULE_MONITORING_CONFIG",
    "MODULE_COMMUNICATION_CONFIG",
    "ERROR_HANDLING_CONFIG",
    "PERFORMANCE_CONFIG",
    "SECURITY_CONFIG",
    "get_module_config",
    "get_all_modules",
    "get_required_modules",
    "get_optional_modules",
    "get_module_dependencies",
    "get_module_priority",
    "get_sorted_modules",
    "validate_module_config",
    "get_environment_specific_config"
] 