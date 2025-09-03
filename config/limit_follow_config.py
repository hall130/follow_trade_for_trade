#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
限价跟单配置模块
提供限价跟单的配置管理和默认值设置
"""

import json
import logging
from typing import Dict, Any, List, Optional
from database.db import get_db_pool

logger = logging.getLogger(__name__)

# 默认限价跟单配置
DEFAULT_LIMIT_FOLLOW_CONFIG = {
    'max_orders_per_signal': 4,  # 每个信号源最大跟单数4
    'default_follow_percentages': [1.0, 2.0, 3.0, 4.0],  # 默认跟单百分比
    'min_follow_percentage': 0.5,  # 最小跟单百分比
    'max_follow_percentage': 10.0,  # 最大跟单百分比
    'auto_cancel_on_signal_close': True,  # 信号源平仓时自动撤单
    'price_precision': 8,  # 价格精度
    'volume_precision': 8,  # 数量精度
    'check_interval': 1,  # 检查间隔（秒）
    'max_retry_attempts': 3,  # 最大重试3次
    'retry_delay': 5,  # 重试延迟（5秒）
    'enable_logging': True,  # 启用日志记录
    'log_level': 'INFO',  # 日志级别
    'max_net_leverage': 10.0,  # 最大净杠杆
    'enable_proportional_position': True,  # 启用按比例开仓
    'default_follow_type': 'percentage',  # 默认跟单类型
    'risk_control_enabled': True,  # 启用风险控制
    'max_position_size': 1000.0,  # 最大持仓数量
    'min_position_size': 0.01,  # 最小持仓数量
    'price_offset_range': [0.5, 1.0, 1.5, 2.0],  # 价格偏移范围
    'volume_scale_factors': [0.8, 1.0, 1.2, 1.5]  # 数量缩放因子
}

# 跟单策略配置
FOLLOW_STRATEGY_CONFIG = {
    'default_follow_type': 'percentage',  # 默认跟单类型：percentage(百分比) fixed(固定价格)
    'default_max_orders': 4,  # 默认最大订单数
    'default_auto_cancel': True,  # 默认自动撤单
    'supported_pos_sides': ['long', 'short', 'both'],  # 支持的持仓方向
    'supported_follow_types': ['percentage', 'fixed'],  # 支持的跟单类型
    'supported_order_types': ['limit', 'market'],  # 支持的订单类型
    'default_risk_level': 'medium',  # 默认风险等级
    'risk_levels': {
        'low': {'max_leverage': 5.0, 'max_position_size': 500.0},
        'medium': {'max_leverage': 10.0, 'max_position_size': 1000.0},
        'high': {'max_leverage': 20.0, 'max_position_size': 2000.0}
    }
}

# 交易所特定配置
EXCHANGE_CONFIGS = {
    'okx': {
        'min_order_size': 0.01,
        'price_precision': 8,
        'volume_precision': 8,
        'max_leverage': 125,
        'supported_inst_types': ['SPOT', 'SWAP', 'MARGIN'],
        'api_rate_limit': 20,  # 每秒请求数
        'order_timeout': 30  # 订单超时时间（秒）
    },
    'binance': {
        'min_order_size': 0.001,
        'price_precision': 8,
        'volume_precision': 8,
        'max_leverage': 125,
        'supported_inst_types': ['SPOT', 'FUTURES', 'MARGIN'],
        'api_rate_limit': 10,
        'order_timeout': 30
    }
}

def get_limit_follow_config() -> Dict[str, Any]:
    """
    获取限价跟单配置
    优先从数据库获取，如果没有则使用默认配置
    """
    try:
        # 尝试从数据库获取配置
        config = get_config_from_db()
        if config:
            # 合并默认配置和数据库配置
            merged_config = DEFAULT_LIMIT_FOLLOW_CONFIG.copy()
            merged_config.update(config)
            return merged_config
    except Exception as e:
        logger.warning(f"从数据库获取配置失败，使用默认配置: {e}")
    
    return DEFAULT_LIMIT_FOLLOW_CONFIG.copy()

def get_config_from_db() -> Optional[Dict[str, Any]]:
    """
    从数据库获取限价跟单配置
    """
    try:
        db_pool = get_db_pool()
        if not db_pool:
            return None
            
        configs = db_pool.query("SELECT config_key, config_value, config_type FROM limit_follow_configs WHERE enabled=1")
        
        if not configs:
            return None
        
        config_data = {}
        for config in configs:
            key = config['config_key']
            value = config['config_value']
            value_type = config['config_type']
            
            # 根据类型转换
            if value_type == 'number':
                try:
                    config_data[key] = float(value)
                except ValueError:
                    config_data[key] = value
            elif value_type == 'boolean':
                config_data[key] = value.lower() == 'true'
            elif value_type == 'json':
                try:
                    config_data[key] = json.loads(value)
                except json.JSONDecodeError:
                    config_data[key] = value
            else:
                config_data[key] = value
        
        return config_data
        
    except Exception as e:
        logger.error(f"从数据库获取配置失败: {e}")
        return None

def update_config_in_db(config_data: Dict[str, Any]) -> bool:
    """
    更新数据库中的限价跟单配置
    """
    try:
        db_pool = get_db_pool()
        if not db_pool:
            return False
        
        for key, value in config_data.items():
            # 确定配置类型
            if isinstance(value, bool):
                config_type = 'boolean'
            elif isinstance(value, (int, float)):
                config_type = 'number'
            elif isinstance(value, (list, dict)):
                config_type = 'json'
                value = json.dumps(value)
            else:
                config_type = 'string'
            
            # 更新配置
            db_pool.execute(
                """INSERT INTO limit_follow_configs (config_key, config_value, config_type) 
                   VALUES (%s, %s, %s)
                   ON DUPLICATE KEY UPDATE 
                   config_value = VALUES(config_value), 
                   config_type = VALUES(config_type),
                   updated_at = CURRENT_TIMESTAMP""",
                (key, str(value), config_type)
            )
        
        return True
        
    except Exception as e:
        logger.error(f"更新数据库配置失败: {e}")
        return False

def get_customer_limit_follow_config(customer_uid: str) -> Dict[str, Any]:
    """
    获取客户特定的限价跟单配置
    """
    try:
        db_pool = get_db_pool()
        if not db_pool:
            return {}
        
        # 根据customer_uid前缀判断是客户还是信号源
        if customer_uid.startswith('c'):  # 客户账户
            table_name = 'customers'
            uid_field = 'customer_uid'
        elif customer_uid.startswith('s'):  # 信号源
            table_name = 'signal_sources'
            uid_field = 'source_uid'
        else:
            # 未知类型
            logger.error(f"未知的标识符类型: {customer_uid}")
            return {}
        
        # 查询对应的表
        customer = db_pool.query(
            f"SELECT {uid_field} as customer_uid, name, api_key, api_secret, passphrase, is_demo, exchange FROM {table_name} WHERE {uid_field}=%s",
            (customer_uid,)
        )
        
        if not customer:
            logger.error(f"在{table_name}表中找不到标识符: {customer_uid}")
            return {}
        
        customer_info = customer[0]
        # 使用is_demo字段，并添加is_sandbox别名以保持兼容性
        customer_info['is_sandbox'] = customer_info.get('is_demo', False)
        
        # 获取客户的跟单策略
        strategies = db_pool.query(
            "SELECT * FROM limit_follow_strategies WHERE customer_uid=%s AND enabled=1",
            (customer_uid,)
        )
        
        # 获取全局配置
        global_config = get_limit_follow_config()
        
        # 获取交易所特定配置
        exchange = customer_info.get('exchange', 'okx')
        exchange_config = EXCHANGE_CONFIGS.get(exchange, {})
        
        return {
            'customer_info': customer_info,
            'strategies': strategies,
            'global_config': global_config,
            'exchange_config': exchange_config
        }
        
    except Exception as e:
        logger.error(f"获取客户配置失败: {e}")
        return {}

def validate_follow_percentages(percentages: List[float]) -> bool:
    """
    验证跟单百分比配置
    """
    if not percentages or len(percentages) == 0:
        return False
    
    config = get_limit_follow_config()
    min_percentage = config.get('min_follow_percentage', 0.5)
    max_percentage = config.get('max_follow_percentage', 10.0)
    
    for percentage in percentages:
        if not isinstance(percentage, (int, float)):
            return False
        if percentage < min_percentage or percentage > max_percentage:
            return False
    
    return True

def get_default_follow_percentages() -> List[float]:
    """
    获取默认跟单百分比
    """
    config = get_limit_follow_config()
    return config.get('default_follow_percentages', [1.0, 2.0, 3.0, 4.0])

def is_limit_follow_enabled() -> bool:
    """
    检查限价跟单功能是否启用
    """
    try:
        config = get_limit_follow_config()
        return config.get('enable_logging', True)
    except Exception:
        return True  # 默认启用

def get_price_precision() -> int:
    """
    获取价格精度
    """
    config = get_limit_follow_config()
    return config.get('price_precision', 8)

def get_volume_precision() -> int:
    """
    获取数量精度
    """
    config = get_limit_follow_config()
    return config.get('volume_precision', 8)

def get_max_orders_per_signal() -> int:
    """
    获取每个信号源最大跟单数量
    """
    config = get_limit_follow_config()
    return config.get('max_orders_per_signal', 4)

def get_check_interval() -> int:
    """
    获取检查间隔
    """
    config = get_limit_follow_config()
    return config.get('check_interval', 1)

def get_max_retry_attempts() -> int:
    """
    获取最大重试次数
    """
    config = get_limit_follow_config()
    return config.get('max_retry_attempts', 3)

def get_retry_delay() -> int:
    """
    获取重试延迟
    """
    config = get_limit_follow_config()
    return config.get('retry_delay', 5)

def get_exchange_config(exchange: str) -> Dict[str, Any]:
    """
    获取交易所特定配置
    """
    return EXCHANGE_CONFIGS.get(exchange, {})

def get_risk_level_config(risk_level: str) -> Dict[str, Any]:
    """
    获取风险等级配置
    """
    return FOLLOW_STRATEGY_CONFIG['risk_levels'].get(risk_level, {})

def validate_strategy_config(strategy_config: Dict[str, Any]) -> Dict[str, Any]:
    """
    验证策略配置
    """
    errors = []
    warnings = []
    
    # 验证必要字段
    required_fields = ['strategy_name', 'trader_unique_name', 'customer_uid', 'symbol']
    for field in required_fields:
        if not strategy_config.get(field):
            errors.append(f"缺少必要字段: {field}")
    
    # 验证数值字段
    if strategy_config.get('follow_value'):
        follow_value = float(strategy_config['follow_value'])
        config = get_limit_follow_config()
        min_percentage = config.get('min_follow_percentage', 0.5)
        max_percentage = config.get('max_follow_percentage', 10.0)
        
        if follow_value < min_percentage or follow_value > max_percentage:
            warnings.append(f"跟单百分比 {follow_value}% 超出建议范围 ({min_percentage}% - {max_percentage}%)")
    
    # 验证杠杆设置
    if strategy_config.get('max_net_leverage'):
        max_leverage = float(strategy_config['max_net_leverage'])
        if max_leverage > 20:
            warnings.append(f"最大净杠杆 {max_leverage} 较高，请注意风险控制")
    
    return {
        'valid': len(errors) == 0,
        'errors': errors,
        'warnings': warnings
    }

def get_config_summary() -> Dict[str, Any]:
    """
    获取配置摘要
    """
    try:
        config = get_limit_follow_config()
        
        return {
            'global_config': {
                'max_orders_per_signal': config.get('max_orders_per_signal'),
                'default_follow_percentages': config.get('default_follow_percentages'),
                'risk_control_enabled': config.get('risk_control_enabled'),
                'max_net_leverage': config.get('max_net_leverage')
            },
            'strategy_config': FOLLOW_STRATEGY_CONFIG,
            'exchange_configs': list(EXCHANGE_CONFIGS.keys()),
            'last_updated': 'now'  # 这里可以添加实际的时间戳
        }
        
    except Exception as e:
        logger.error(f"获取配置摘要失败: {e}")
        return {}

if __name__ == "__main__":
    # 测试配置
    config = get_limit_follow_config()
    print("限价跟单配置:")
    print(json.dumps(config, indent=2, ensure_ascii=False))
    
    # 测试配置验证
    test_strategy = {
        'strategy_name': 'Test Strategy',
        'trader_unique_name': 'test_trader',
        'customer_uid': 'c001',
        'symbol': 'BTC-USDT-SWAP',
        'follow_value': 2.5,
        'max_net_leverage': 15.0
    }
    
    validation_result = validate_strategy_config(test_strategy)
    print("\n策略配置验证结果:")
    print(json.dumps(validation_result, indent=2, ensure_ascii=False)) 
