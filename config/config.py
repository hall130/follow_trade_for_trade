# config.py

MYSQL_CONFIG = {
    'host': 'localhost',      # 修改为你的MySQL主机
    'port': 3306,            # MySQL端口
    'user': 'root',     # MySQL用户名
    'password': 'Aa11223344..', # MySQL密码
    'db': 'trade_db',        # 数据库名
    'mincached': 2,
    'maxcached': 10
}

REDIS_CONFIG = {
    'host': 'localhost',
    'port': 6379,
    'db': 0,
    'password': 'Aa11223344..',  # 与 Redis 配置的密码一致
    'decode_responses': True,
    'enabled': True  # 启用 Redis
}


def get_mysql_config():
    return MYSQL_CONFIG 

def get_websocket_config():
    """获取WebSocket配置"""
    return {
        'connection_check_interval': 15,      # WebSocket连接检查间隔（秒）- 提高响应速度
        'health_check_interval': 30,          # 健康检查间隔（秒）- 提高监控频率
        'max_reconnect_attempts': 3,          # 最大重连次数 - 减少重连次数避免循环
        'reconnect_delay': 10,                # 重连延迟（秒）- 增加延迟避免频繁重连
        'heartbeat_interval': 30,             # 心跳间隔（秒）
        'max_silence_time': 120,              # 最大静默时间（秒）- 增加容忍度
        'connection_timeout': 30,             # 连接超时（秒）
        'message_timeout': 180,               # 消息超时（秒）
        'auto_reconnect': True,               # 是否启用自动重连
        'health_monitoring': True,            # 是否启用健康监控
    }

def get_api_server_config():
    """获取API服务器配置"""
    return {
        'host': '0.0.0.0',
        'port': 5001,
        'debug': False,
        'threaded': True,
        'processes': 1,
        'max_connections': 100,
    }

def get_stop_loss_config():
    """获取止损模块配置"""
    return {
        'enabled': True,                     # 是否启用止损监控（默认禁用）
        'check_interval': 5,                 # 检查间隔（秒）
        'customer_stop_loss_percent': 0.1,   # 客户默认止损百分比
        'signal_stop_loss_percent': 0.1,     # 信号源默认止损百分比
        'notification_enabled': True,          # 是否启用通知
        'auto_close_positions': True,         # 是否自动平仓
        'max_stop_loss_count': 5,             # 最大止损次数
    } 

# 内存管理配置
MEMORY_CONFIG = {
    'memory_warning_threshold': 500,      # 内存警告阈值 (MB)
    'memory_critical_threshold': 800,     # 内存严重警告阈值 (MB)
    'memory_restart_threshold': 1000,    # 内存自动重启阈值 (MB)
    'memory_check_interval': 60,         # 内存检查间隔 (秒)
    'queue_max_size': 1000,              # 信号队列最大大小
    'db_pool_warning_size': 50,          # 数据库连接池警告大小
    'db_pool_critical_size': 80,         # 数据库连接池严重警告大小
    'aggressive_cleanup_threshold': 800, # 激进清理阈值 (MB)
    'auto_restart_interval': 600,        # 自动重启检查间隔 (秒)
}

# 获取内存配置
def get_memory_config():
    return MEMORY_CONFIG.copy() 

# OKX交易所配置
OKX_CONFIG = {
    'api_key': 'your_api_key_here',
    'api_secret': 'your_api_secret_here',
    'passphrase': 'your_passphrase_here',
    'is_demo': True,  # 是否使用模拟盘
    'base_url': 'https://www.okx.com',  # OKX API基础URL
    'ws_url': 'wss://ws.okx.com:8443/ws/v5/public',  # WebSocket URL
    'ws_private_url': 'wss://ws.okx.com:8443/ws/v5/private',  # 私有WebSocket URL
}

def get_okx_config():
    """获取OKX交易所配置"""
    return OKX_CONFIG.copy()

# 注意：REDIS_CONFIG 已在文件开头定义（第13行），这里不再重复定义

def get_redis_config():
    """获取 Redis 配置（过滤掉 RedisManager 不支持的参数）"""
    config = REDIS_CONFIG.copy()
    # 只返回 RedisManager 支持的参数
    return {
        'host': config.get('host', 'localhost'),
        'port': config.get('port', 6379),
        'db': config.get('db', 0),
        'password': config.get('password'),
        'decode_responses': config.get('decode_responses', True)
    } 
