# config_example.py
# 止损模块配置示例文件

# 复制这个文件为 config.py 并根据需要修改配置

MYSQL_CONFIG = {
    'host': 'localhost',      # 修改为你的MySQL主机
    'port': 3306,            # MySQL端口
    'user': 'root',     # MySQL用户名
    'password': 'root', # MySQL密码
    'db': 'trade_db',        # 数据库名
    'mincached': 2,
    'maxcached': 10
}

def get_mysql_config():
    return MYSQL_CONFIG 

def get_websocket_config():
    """获取WebSocket配置"""
    return {
        'connection_check_interval': 15,      # WebSocket连接检查间隔（秒）
        'health_check_interval': 60,          # 健康检查间隔（秒）
        'max_reconnect_attempts': 5,          # 最大重连次数
        'reconnect_delay': 5,                 # 重连延迟（秒）
        'heartbeat_interval': 30,             # 心跳间隔（秒）
        'max_silence_time': 60,               # 最大静默时间（秒）
        'connection_timeout': 30,             # 连接超时（秒）
        'message_timeout': 180,               # 消息超时（秒）
        'auto_reconnect': True,               # 是否启用自动重连
        'health_monitoring': True,            # 是否启用健康监控
    }

def get_api_server_config():
    """获取API服务器配置"""
    return {
        'host': '0.0.0.0',
        'port': 5000,
        'debug': False,
        'threaded': True,
        'processes': 1,
        'max_connections': 100,
    }

def get_stop_loss_config():
    """获取止损模块配置"""
    return {
        # ==================== 止损模块开关 ====================
        'enabled': False,                     # 是否启用止损监控（默认禁用）
        
        # ==================== 监控参数 ====================
        'check_interval': 60,                 # 检查间隔（秒）
        
        # ==================== 止损百分比 ====================
        'customer_stop_loss_percent': 10.0,   # 客户默认止损百分比
        'signal_stop_loss_percent': 15.0,     # 信号源默认止损百分比
        
        # ==================== 功能开关 ====================
        'notification_enabled': True,          # 是否启用通知
        'auto_close_positions': True,         # 是否自动平仓
        'max_stop_loss_count': 5,             # 最大止损次数
        
        # ==================== 高级配置 ====================
        'enable_dynamic_stop_loss': False,     # 是否启用动态止损（根据市场波动调整）
        'market_volatility_threshold': 0.05,  # 市场波动阈值
        'volatility_adjustment_factor': 0.8,  # 波动调整因子
        
        # ==================== 通知配置 ====================
        'dingtalk_notification': True,        # 钉钉通知
        'email_notification': False,          # 邮件通知
        'sms_notification': False,            # 短信通知
        
        # ==================== 日志配置 ====================
        'log_level': 'INFO',                  # 日志级别
        'log_stop_loss_history': True,        # 是否记录止损历史
        'log_asset_changes': True,            # 是否记录资产变化
    }

# ==================== 配置说明 ====================
"""
止损模块配置说明：

1. enabled: 主开关
   - False: 完全禁用止损监控
   - True: 启用止损监控

2. check_interval: 检查频率
   - 60: 每分钟检查一次
   - 300: 每5分钟检查一次
   - 3600: 每小时检查一次

3. 止损百分比设置
   - customer_stop_loss_percent: 客户止损百分比，如10.0表示10%
   - signal_stop_loss_percent: 信号源止损百分比，如15.0表示15%

4. 功能开关
   - notification_enabled: 是否发送止损通知
   - auto_close_positions: 是否自动平仓
   - max_stop_loss_count: 最大止损次数限制

5. 高级功能
   - enable_dynamic_stop_loss: 动态止损（根据市场波动调整止损线）
   - market_volatility_threshold: 市场波动阈值
   - volatility_adjustment_factor: 波动调整因子

使用示例：
1. 完全禁用止损：'enabled': False
2. 启用止损但降低频率：'enabled': True, 'check_interval': 300
3. 启用止损但禁用通知：'enabled': True, 'notification_enabled': False
4. 启用动态止损：'enabled': True, 'enable_dynamic_stop_loss': True
""" 