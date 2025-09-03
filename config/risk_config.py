#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
风险控制配置文件
读取risk_config.json中的风控参数
"""

import json
import os
from typing import Dict, Any

def get_risk_config() -> Dict[str, Any]:
    """获取风险控制配置"""
    try:
        # 获取当前文件所在目录
        current_dir = os.path.dirname(os.path.abspath(__file__))
        config_file = os.path.join(current_dir, 'risk_config.json')
        
        if os.path.exists(config_file):
            with open(config_file, 'r', encoding='utf-8') as f:
                config = json.load(f)
            return config
        else:
            # 如果配置文件不存在，返回默认配置
            return get_default_risk_config()
            
    except Exception as e:
        print(f"读取风险控制配置失败: {e}")
        return get_default_risk_config()

def get_default_risk_config() -> Dict[str, Any]:
    """获取默认风险控制配置"""
    return {
        "max_positions_per_direction": 10,
        "min_trade_interval_minutes": 30,
        "max_leverage": 10.0,
        "enable_time_interval_check": True,
        "enable_position_limit_check": True,
        "description": "默认风控配置"
    }

def update_risk_config(new_config: Dict[str, Any]) -> bool:
    """更新风险控制配置"""
    try:
        current_dir = os.path.dirname(os.path.abspath(__file__))
        config_file = os.path.join(current_dir, 'risk_config.json')
        
        with open(config_file, 'w', encoding='utf-8') as f:
            json.dump(new_config, f, indent=2, ensure_ascii=False)
        
        return True
    except Exception as e:
        print(f"更新风险控制配置失败: {e}")
        return False

def reset_risk_config() -> bool:
    """重置风险控制配置为默认值"""
    default_config = get_default_risk_config()
    return update_risk_config(default_config) 