#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
币安交易所配置文件
"""

# 币安交易所配置
BINANCE_CONFIG = {
    'api_key': 'your_binance_api_key_here',
    'api_secret': 'your_binance_api_secret_here',
    'is_demo': True,  # 是否使用测试网
    'base_url': 'https://api.binance.com',  # 主网API基础URL
    'testnet_url': 'https://testnet.binance.vision',  # 测试网API基础URL
    'ws_url': 'wss://stream.binance.com:9443/ws',  # 主网WebSocket URL
    'testnet_ws_url': 'wss://testnet.binance.vision/ws',  # 测试网WebSocket URL
    'timeout': 30,  # 请求超时时间（秒）
    'max_retries': 3,  # 最大重试次数
    'rate_limit': {
        'requests_per_minute': 1200,  # 每分钟请求限制
        'orders_per_second': 10,  # 每秒订单限制
        'orders_per_day': 200000,  # 每日订单限制
    }
}

def get_binance_config():
    """获取币安交易所配置"""
    return BINANCE_CONFIG.copy()

def get_binance_api_config():
    """获取币安API配置"""
    config = get_binance_config()
    return {
        'api_key': config['api_key'],
        'api_secret': config['api_secret'],
        'is_demo': config['is_demo'],
        'base_url': config['testnet_url'] if config['is_demo'] else config['base_url'],
        'timeout': config['timeout'],
        'max_retries': config['max_retries']
    }

def get_binance_ws_config():
    """获取币安WebSocket配置"""
    config = get_binance_config()
    return {
        'api_key': config['api_key'],
        'api_secret': config['api_secret'],
        'is_demo': config['is_demo'],
        'ws_url': config['testnet_ws_url'] if config['is_demo'] else config['ws_url'],
        'timeout': config['timeout']
    }

def get_binance_rate_limit():
    """获取币安速率限制配置"""
    config = get_binance_config()
    return config['rate_limit']

def update_binance_config(updates: dict):
    """更新币安配置"""
    global BINANCE_CONFIG
    BINANCE_CONFIG.update(updates)

def set_binance_demo_mode(is_demo: bool):
    """设置币安演示模式"""
    update_binance_config({'is_demo': is_demo})

def set_binance_api_credentials(api_key: str, api_secret: str):
    """设置币安API凭据"""
    update_binance_config({
        'api_key': api_key,
        'api_secret': api_secret
    })

def validate_binance_config():
    """验证币安配置"""
    config = get_binance_config()
    
    if not config['api_key'] or config['api_key'] == 'your_binance_api_key_here':
        return False, "币安API密钥未设置"
    
    if not config['api_secret'] or config['api_secret'] == 'your_binance_api_secret_here':
        return False, "币安API密钥未设置"
    
    return True, "币安配置验证通过"

def get_binance_status():
    """获取币安配置状态"""
    is_valid, message = validate_binance_config()
    
    return {
        'enabled': is_valid,
        'is_demo': get_binance_config()['is_demo'],
        'message': message,
        'api_key_set': bool(get_binance_config()['api_key'] and get_binance_config()['api_key'] != 'your_binance_api_key_here'),
        'api_secret_set': bool(get_binance_config()['api_secret'] and get_binance_config()['api_secret'] != 'your_binance_api_secret_here')
    } 