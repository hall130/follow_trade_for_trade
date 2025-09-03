#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
日志配置文件
用于控制各种日志的输出级别和频率
"""

# ==================== 健康检查日志控制 ====================

# 是否启用健康检查日志
ENABLE_HEALTH_CHECK_LOGGING = False

# 健康检查日志级别
HEALTH_CHECK_LOG_LEVEL = "WARNING"  # 只在有问题时记录

# 健康检查成功时是否记录日志
LOG_HEALTH_CHECK_SUCCESS = False

# 健康检查失败时是否记录日志
LOG_HEALTH_CHECK_FAILURE = True

# 健康检查间隔（秒）
HEALTH_CHECK_INTERVAL = 300  # 5分钟

# ==================== 监控日志控制 ====================

# 是否启用监控日志
ENABLE_MONITOR_LOGGING = True

# 监控日志级别
MONITOR_LOG_LEVEL = "WARNING"

# 监控成功时是否记录日志
LOG_MONITOR_SUCCESS = False

# 监控失败时是否记录日志
LOG_MONITOR_FAILURE = True

# 监控日志记录频率（每N次检查记录一次成功状态）
MONITOR_SUCCESS_LOG_FREQUENCY = 10

# ==================== 系统资源日志控制 ====================

# 是否启用系统资源日志
ENABLE_SYSTEM_RESOURCE_LOGGING = False

# 系统资源日志级别
SYSTEM_RESOURCE_LOG_LEVEL = "WARNING"

# 系统资源使用率阈值（超过此值才记录日志）
SYSTEM_RESOURCE_WARNING_THRESHOLD = 80

# ==================== 连接状态日志控制 ====================

# 是否启用连接状态日志
ENABLE_CONNECTION_STATUS_LOGGING = False

# 连接状态日志级别
CONNECTION_STATUS_LOG_LEVEL = "WARNING"

# 连接状态成功时是否记录日志
LOG_CONNECTION_STATUS_SUCCESS = False

# 连接状态失败时是否记录日志
LOG_CONNECTION_STATUS_FAILURE = True

# ==================== 交易日志控制 ====================

# 是否启用交易日志
ENABLE_TRADE_LOGGING = True

# 交易日志级别
TRADE_LOG_LEVEL = "INFO"

# 是否记录详细的交易信息
LOG_DETAILED_TRADE_INFO = True

# 是否记录价格信息
LOG_PRICE_INFO = False

# ==================== WebSocket日志控制 ====================

# 是否启用WebSocket日志
ENABLE_WEBSOCKET_LOGGING = True

# WebSocket日志级别
WEBSOCKET_LOG_LEVEL = "WARNING"

# 是否记录WebSocket连接状态
LOG_WEBSOCKET_CONNECTION_STATUS = False

# 是否记录WebSocket消息
LOG_WEBSOCKET_MESSAGES = False

# ==================== 数据库日志控制 ====================

# 是否启用数据库日志
ENABLE_DATABASE_LOGGING = True

# 数据库日志级别
DATABASE_LOG_LEVEL = "WARNING"

# 是否记录SQL查询
LOG_SQL_QUERIES = False

# 是否记录数据库连接状态
LOG_DATABASE_CONNECTION_STATUS = False

# ==================== 通用日志控制 ====================

# 默认日志级别
DEFAULT_LOG_LEVEL = "INFO"

# 是否启用时间戳
ENABLE_TIMESTAMP = True

# 是否启用日志文件轮转
ENABLE_LOG_ROTATION = True

# 日志文件最大大小（字节）
MAX_LOG_FILE_SIZE = 10 * 1024 * 1024  # 10MB

# 保留的日志文件数量
MAX_LOG_FILES = 5

# ==================== 日志格式 ====================

# 日志格式
LOG_FORMAT = "[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s"

# 日期格式
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

# ==================== 日志文件配置 ====================

# 主日志文件
MAIN_LOG_FILE = "trades.log"

# 错误日志文件
ERROR_LOG_FILE = "error.log"

# 监控日志文件
MONITOR_LOG_FILE = "monitor.log"

# 健康检查日志文件
HEALTH_CHECK_LOG_FILE = "health_check.log" 

def get_logger_config():
    """获取日志配置"""
    return {
        'default_level': DEFAULT_LOG_LEVEL,
        'enable_timestamp': ENABLE_TIMESTAMP,
        'enable_rotation': ENABLE_LOG_ROTATION,
        'max_file_size': MAX_LOG_FILE_SIZE,
        'max_files': MAX_LOG_FILES,
        'format': LOG_FORMAT,
        'date_format': DATE_FORMAT,
        'main_file': MAIN_LOG_FILE,
        'error_file': ERROR_LOG_FILE,
        'monitor_file': MONITOR_LOG_FILE,
        'health_check_file': HEALTH_CHECK_LOG_FILE,
        'health_check': {
            'enabled': ENABLE_HEALTH_CHECK_LOGGING,
            'level': HEALTH_CHECK_LOG_LEVEL,
            'log_success': LOG_HEALTH_CHECK_SUCCESS,
            'log_failure': LOG_HEALTH_CHECK_FAILURE,
            'interval': HEALTH_CHECK_INTERVAL
        },
        'monitor': {
            'enabled': ENABLE_MONITOR_LOGGING,
            'level': MONITOR_LOG_LEVEL,
            'log_success': LOG_MONITOR_SUCCESS,
            'log_failure': LOG_MONITOR_FAILURE,
            'frequency': MONITOR_SUCCESS_LOG_FREQUENCY
        },
        'system_resource': {
            'enabled': ENABLE_SYSTEM_RESOURCE_LOGGING,
            'level': SYSTEM_RESOURCE_LOG_LEVEL,
            'warning_threshold': SYSTEM_RESOURCE_WARNING_THRESHOLD
        },
        'connection_status': {
            'enabled': ENABLE_CONNECTION_STATUS_LOGGING,
            'level': CONNECTION_STATUS_LOG_LEVEL,
            'log_success': LOG_CONNECTION_STATUS_SUCCESS,
            'log_failure': LOG_CONNECTION_STATUS_FAILURE
        },
        'trade': {
            'enabled': ENABLE_TRADE_LOGGING,
            'level': TRADE_LOG_LEVEL,
            'detailed_info': LOG_DETAILED_TRADE_INFO,
            'price_info': LOG_PRICE_INFO
        },
        'websocket': {
            'enabled': ENABLE_WEBSOCKET_LOGGING,
            'level': WEBSOCKET_LOG_LEVEL,
            'connection_status': LOG_WEBSOCKET_CONNECTION_STATUS,
            'messages': LOG_WEBSOCKET_MESSAGES
        },
        'database': {
            'enabled': ENABLE_DATABASE_LOGGING,
            'level': DATABASE_LOG_LEVEL,
            'sql_queries': LOG_SQL_QUERIES,
            'connection_status': LOG_DATABASE_CONNECTION_STATUS
        }
    } 