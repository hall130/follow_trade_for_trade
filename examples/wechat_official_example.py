#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
微信公众号推送示例
演示如何使用微信公众号推送工具发送各种类型的消息
"""

import asyncio
import sys
import os

# 添加项目根目录到路径
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.wechat_official_bot import (
    init_wechat_official_bot,
    send_text,
    send_template_message,
    send_trade_notification,
    send_alert_notification
)
from config.wechat_official_config import (
    get_wechat_official_config,
    get_user_openids,
    get_user_openid
)


async def example_send_text():
    """示例：发送文本消息"""
    print("\n=== 示例1：发送文本消息 ===")
    
    # 获取配置
    config = get_wechat_official_config()
    if not config:
        print("❌ 微信公众号未配置或未启用")
        return
    
    # 初始化
    init_wechat_official_bot(config['app_id'], config['app_secret'])
    
    # 获取用户 openid（示例）
    openids = get_user_openids()
    if not openids:
        print("⚠️  没有配置用户 openid，请先在配置文件中添加")
        print("   示例：在 config/wechat_official_config.py 的 users 中添加")
        return
    
    # 发送文本消息
    openid = openids[0]  # 使用第一个用户
    content = "这是一条测试消息\n\n来自微信公众号推送工具"
    
    success = await send_text(openid, content)
    if success:
        print(f"✅ 文本消息发送成功")
    else:
        print(f"❌ 文本消息发送失败")
    
    print("\n注意：如果用户超过48小时未与公众号交互，客服消息将无法发送")
    print("建议：使用模板消息（不受48小时限制）")


async def example_send_template():
    """示例：发送模板消息"""
    print("\n=== 示例2：发送模板消息 ===")
    
    # 获取配置
    config = get_wechat_official_config()
    if not config:
        print("❌ 微信公众号未配置或未启用")
        return
    
    # 初始化
    init_wechat_official_bot(config['app_id'], config['app_secret'])
    
    # 获取用户 openid
    openids = get_user_openids()
    if not openids:
        print("⚠️  没有配置用户 openid")
        return
    
    openid = openids[0]
    
    # 模板ID（需要在微信公众平台申请）
    template_id = "your_template_id_here"  # 替换为实际的模板ID
    
    # 模板数据（根据模板格式填写）
    template_data = {
        'first': {
            'value': '系统通知',
            'color': '#173177'
        },
        'keyword1': {
            'value': '测试消息',
            'color': '#173177'
        },
        'keyword2': {
            'value': '2024-01-01 12:00:00',
            'color': '#173177'
        },
        'remark': {
            'value': '这是一条测试模板消息',
            'color': '#173177'
        }
    }
    
    # 发送模板消息
    success = await send_template_message(openid, template_id, template_data)
    if success:
        print(f"✅ 模板消息发送成功")
    else:
        print(f"❌ 模板消息发送失败")
        print("请检查：")
        print("  1. 模板ID是否正确")
        print("  2. 模板数据格式是否匹配")
        print("  3. 用户是否已关注公众号")


async def example_send_trade_notification():
    """示例：发送交易通知"""
    print("\n=== 示例3：发送交易通知 ===")
    
    # 获取配置
    config = get_wechat_official_config()
    if not config:
        print("❌ 微信公众号未配置或未启用")
        return
    
    # 初始化
    init_wechat_official_bot(config['app_id'], config['app_secret'])
    
    # 获取用户 openid
    openids = get_user_openids()
    if not openids:
        print("⚠️  没有配置用户 openid")
        return
    
    openid = openids[0]
    
    # 模拟交易信息
    trade_info = {
        'trade_uid': 'trade_123456',
        'symbol': 'BTCUSDT',
        'direction': '买入',
        'pos_side': 'long',
        'volume': '100',
        'price': '50000',
        'customer_uid': 'customer_001',
        'strategy_uid': 'strategy_001',
        'rule_uid': 'rule_001',
        'time': '2024-01-01 12:00:00',
        'success': True
    }
    
    # 获取通知配置
    trade_config = config.get('notifications', {}).get('trade', {})
    use_template = trade_config.get('use_template', False)
    template_id = trade_config.get('template_id', '')
    
    # 发送交易通知
    success = await send_trade_notification(
        openid, 
        trade_info, 
        use_template=use_template,
        template_id=template_id if template_id else None
    )
    
    if success:
        print(f"✅ 交易通知发送成功")
    else:
        print(f"❌ 交易通知发送失败")


async def example_send_alert_notification():
    """示例：发送告警通知"""
    print("\n=== 示例4：发送告警通知 ===")
    
    # 获取配置
    config = get_wechat_official_config()
    if not config:
        print("❌ 微信公众号未配置或未启用")
        return
    
    # 初始化
    init_wechat_official_bot(config['app_id'], config['app_secret'])
    
    # 获取用户 openid
    openids = get_user_openids()
    if not openids:
        print("⚠️  没有配置用户 openid")
        return
    
    openid = openids[0]
    
    # 模拟告警信息
    alert_info = {
        'title': '系统异常告警',
        'level': 'error',
        'time': '2024-01-01 12:00:00',
        'message': '账户余额不足',
        'account': 'account_001',
        'strategy': 'strategy_001',
        'symbol': 'BTCUSDT',
        'suggestion': '请及时充值'
    }
    
    # 获取通知配置
    alert_config = config.get('notifications', {}).get('alert', {})
    use_template = alert_config.get('use_template', False)
    template_id = alert_config.get('template_id', '')
    
    # 发送告警通知
    success = await send_alert_notification(
        openid,
        'error',
        alert_info,
        use_template=use_template,
        template_id=template_id if template_id else None
    )
    
    if success:
        print(f"✅ 告警通知发送成功")
    else:
        print(f"❌ 告警通知发送失败")


async def main():
    """主函数"""
    print("=" * 60)
    print("微信公众号推送工具示例")
    print("=" * 60)
    print("\n使用前请确保：")
    print("1. 已在 config/wechat_official_config.py 中配置 AppID 和 AppSecret")
    print("2. 已添加用户 openid")
    print("3. 如需使用模板消息，已申请并配置模板ID")
    print("=" * 60)
    
    # 运行示例
    # 取消注释以下行来运行对应的示例
    
    # await example_send_text()
    # await example_send_template()
    # await example_send_trade_notification()
    # await example_send_alert_notification()
    
    print("\n💡 提示：取消注释 example.py 中的对应示例函数来运行测试")


if __name__ == "__main__":
    asyncio.run(main())

