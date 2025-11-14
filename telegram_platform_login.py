#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Telegram 平台登录助手
用于获取 session_string 并保存到数据库
"""

import asyncio
import sys
from telethon import TelegramClient
from telethon.errors import SessionPasswordNeededError, PhoneCodeInvalidError
from telethon.sessions import StringSession

# 添加项目路径
sys.path.insert(0, 'D:\\follow_trade_for_trade')

from database.db import get_db_pool
from core.message_forward.db_operations_mysql import MessageForwardDB
from utils.logger import get_logger

logger = get_logger(__name__)


async def login_telegram_platform(platform_id: int):
    """
    登录 Telegram 平台并保存 session_string
    
    Args:
        platform_id: 数据库中的平台 ID
    """
    # 获取数据库连接
    db_pool = get_db_pool()
    db = MessageForwardDB(db_pool)
    
    # 获取平台信息
    platform_data = db.get_platform_by_id(platform_id)
    if not platform_data:
        print(f"❌ 平台 {platform_id} 不存在")
        return False
    
    config = platform_data.get('config', {})
    api_id = config.get('api_id')
    api_hash = config.get('api_hash')
    phone = config.get('phone')
    
    if not api_id or not api_hash:
        print("❌ 缺少 api_id 或 api_hash")
        return False
    
    if not phone:
        print("❌ 缺少 phone")
        return False
    
    print("=" * 60)
    print(f"🔐 Telegram 平台登录助手 - 平台 ID: {platform_id}")
    print(f"📱 手机号: {phone}")
    print("=" * 60)
    
    # 创建客户端（使用空的 StringSession）
    client = TelegramClient(StringSession(), api_id, api_hash)
    
    try:
        # 连接
        await client.connect()
        print("✅ 已连接到 Telegram")
        
        # 检查是否已认证
        if await client.is_user_authorized():
            print("✅ 已经认证，无需登录")
            me = await client.get_me()
            print(f"👤 当前用户: {me.first_name} (@{me.username or 'N/A'})")
        else:
            print(f"\n📤 正在发送验证码到 {phone}...")
            
            # 发送验证码
            await client.send_code_request(phone)
            print("✅ 验证码已发送到您的 Telegram 应用")
            
            # 输入验证码
            print("\n" + "=" * 60)
            code = input("📝 请输入收到的验证码: ").strip()
            
            if not code:
                print("❌ 验证码不能为空")
                return False
            
            try:
                # 使用验证码登录
                print("🔐 正在验证...")
                await client.sign_in(phone, code)
                
                me = await client.get_me()
                print(f"✅ 登录成功: {me.first_name} (@{me.username or 'N/A'})")
                
            except SessionPasswordNeededError:
                # 需要两步验证密码
                print("\n🔐 需要两步验证密码")
                password = input("请输入两步验证密码: ").strip()
                
                if not password:
                    print("❌ 密码不能为空")
                    return False
                
                await client.sign_in(password=password)
                me = await client.get_me()
                print(f"✅ 两步验证成功: {me.first_name} (@{me.username or 'N/A'})")
                
            except PhoneCodeInvalidError:
                print("❌ 验证码无效")
                return False
        
        # 获取 session_string
        session_string = client.session.save()
        print(f"\n✅ 成功获取 session_string（长度: {len(session_string)}）")
        
        # 保存到数据库
        updated_config = config.copy()
        updated_config['session_string'] = session_string
        # 清理临时数据
        updated_config.pop('_temp_phone_code_hash', None)
        
        db.update_platform(platform_id, {
            'config': updated_config
        })
        
        print(f"✅ session_string 已保存到数据库（平台 ID: {platform_id}）")
        print("\n" + "=" * 60)
        print("🎉 登录完成！现在可以在 Web 界面使用该平台了")
        print("=" * 60)
        
        return True
        
    except Exception as e:
        print(f"\n❌ 登录失败: {e}")
        import traceback
        traceback.print_exc()
        return False
        
    finally:
        await client.disconnect()
        print("✅ 已断开连接")


def main():
    """主函数"""
    print("\n" + "=" * 60)
    print("🚀 Telegram 平台登录助手")
    print("=" * 60)
    
    # 获取平台 ID
    if len(sys.argv) > 1:
        try:
            platform_id = int(sys.argv[1])
        except ValueError:
            print("❌ 平台 ID 必须是数字")
            print(f"用法: python {sys.argv[0]} <platform_id>")
            return
    else:
        try:
            platform_id = int(input("\n请输入平台 ID: ").strip())
        except ValueError:
            print("❌ 平台 ID 必须是数字")
            return
    
    # 运行登录
    success = asyncio.run(login_telegram_platform(platform_id))
    
    if success:
        print("\n✅ 操作成功完成")
    else:
        print("\n❌ 操作失败")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n👋 用户中断")
    except Exception as e:
        print(f"\n❌ 发生错误: {e}")
        import traceback
        traceback.print_exc()

