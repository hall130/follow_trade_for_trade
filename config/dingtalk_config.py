#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# 钉钉机器人配置
DINGTALK_CONFIG = {
    "webhook_url": "https://oapi.dingtalk.com/robot/send?access_token=975dac051a1123148bb57ead53fbef34705b52d3317ac43a20d966fab8135af7",
    "secret": "SECabf44154148d047463cec76ae4a0dbe09a1ba70d1fe260077ee0ee372dbd0e2a",
    "enabled": False,  # 临时启用用于测试
    "notifications": {
        "trade": {
            "enabled": True,
            "at_all": False,
            "at_mobiles": [],
        },
        "alert": {
            "enabled": True,
            "at_all": True,
            "at_mobiles": [],
            "levels": ["error", "warning"],
        },
        "system": {
            "enabled": True,
            "at_all": False,
            "at_mobiles": [],
        }
    }
}

def get_dingtalk_config():
    """获取钉钉配置"""
    try:
        # 检查配置是否有效
        config = DINGTALK_CONFIG.copy()
        
        # 如果没有webhook_url，返回None
        if not config.get("webhook_url"):
            return None
        
        # 如果配置被禁用，返回None
        if not config.get("enabled", False):
            return None
            
        return config
        
    except Exception as e:
        print(f"获取钉钉配置失败: {e}")
        return None

def is_dingtalk_enabled():
    """检查钉钉是否启用"""
    return DINGTALK_CONFIG.get("enabled", False)

def should_send_trade_notification():
    """检查是否应该发送交易通知"""
    config = DINGTALK_CONFIG.get("notifications", {}).get("trade", {})
    return config.get("enabled", False)

def should_send_alert_notification(alert_type: str):
    """检查是否应该发送告警通知"""
    config = DINGTALK_CONFIG.get("notifications", {}).get("alert", {})
    if not config.get("enabled", False):
        return False
    
    # 检查告警级别
    levels = config.get("levels", ["error", "warning"])
    return alert_type in levels

def get_notification_at_settings(notification_type: str):
    """获取通知的@设置"""
    config = DINGTALK_CONFIG.get("notifications", {}).get(notification_type, {})
    return {
        "at_all": config.get("at_all", False),
        "at_mobiles": config.get("at_mobiles", [])
    } 