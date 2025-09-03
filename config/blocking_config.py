#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
币种屏蔽规则配置文件
用于管理不同信号源的币种屏蔽规则
"""

# 屏蔽规则配置
BLOCKING_RULES = {
    'signal_01': {
        'description': '信号源01屏蔽规则',
        'blocked_symbols': ['pepe', 'fartcoin'],
        'enabled': True
    },
    # 可以添加更多信号源的屏蔽规则
    # 'signal_02': {
    #     'description': '信号源02屏蔽规则',
    #     'blocked_symbols': ['other_coin'],
    #     'enabled': True
    # },
}

def get_blocking_rules():
    """获取屏蔽规则"""
    return BLOCKING_RULES

def is_signal_source_blocked(signal_source_uid: str) -> bool:
    """检查信号源是否被禁用"""
    if signal_source_uid in BLOCKING_RULES:
        return not BLOCKING_RULES[signal_source_uid].get('enabled', True)
    return False

def get_blocked_symbols(signal_source_uid: str) -> list:
    """获取指定信号源的屏蔽币种列表"""
    if signal_source_uid in BLOCKING_RULES:
        return BLOCKING_RULES[signal_source_uid].get('blocked_symbols', [])
    return []

def add_blocking_rule(signal_source_uid: str, blocked_symbols: list, description: str = ""):
    """添加屏蔽规则"""
    BLOCKING_RULES[signal_source_uid] = {
        'description': description,
        'blocked_symbols': blocked_symbols,
        'enabled': True
    }

def remove_blocking_rule(signal_source_uid: str):
    """移除屏蔽规则"""
    if signal_source_uid in BLOCKING_RULES:
        del BLOCKING_RULES[signal_source_uid]

def update_blocked_symbols(signal_source_uid: str, blocked_symbols: list):
    """更新指定信号源的屏蔽币种列表"""
    if signal_source_uid in BLOCKING_RULES:
        BLOCKING_RULES[signal_source_uid]['blocked_symbols'] = blocked_symbols
    else:
        add_blocking_rule(signal_source_uid, blocked_symbols)

def print_blocking_rules():
    """打印当前屏蔽规则"""
    print("=" * 80)
    print("当前币种屏蔽规则")
    print("=" * 80)
    
    for signal_source, rule in BLOCKING_RULES.items():
        print(f"\n信号源: {signal_source}")
        print(f"描述: {rule.get('description', '无描述')}")
        print(f"状态: {'启用' if rule.get('enabled', True) else '禁用'}")
        print(f"屏蔽币种: {', '.join(rule.get('blocked_symbols', []))}")
    
    print("\n" + "=" * 80)

if __name__ == "__main__":
    print_blocking_rules() 