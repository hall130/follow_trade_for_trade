#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Telegram 登录辅助脚本
用于登录 Telegram 并获取 session_string，更新到配置文件中
"""

import asyncio
import sys
import json
import signal
from pathlib import Path
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.errors import SessionPasswordNeededError, PhoneCodeInvalidError

# 添加项目根目录到Python路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

# 配置文件路径
CONFIG_FILE = project_root / "config" / "telegram_listener_config.json"

# 全局变量用于控制中断
client_instance = None
shutdown_requested = False

def signal_handler(signum, frame):
    """信号处理函数"""
    global shutdown_requested
    print("\n\n⚠️  收到中断信号，正在退出...")
    shutdown_requested = True
    if client_instance:
        try:
            # 尝试断开连接
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    loop.create_task(client_instance.disconnect())
            except RuntimeError:
                # 如果没有事件循环，直接退出
                pass
        except:
            pass

async def safe_input(prompt: str) -> str:
    """安全的输入函数，支持 Ctrl+C 中断"""
    try:
        # 使用线程来执行 input，避免阻塞事件循环
        # 这样可以在等待输入时响应 Ctrl+C
        import concurrent.futures
        loop = asyncio.get_event_loop()
        with concurrent.futures.ThreadPoolExecutor() as executor:
            future = executor.submit(input, prompt)
            try:
                # 等待输入完成（input 本身就能响应 Ctrl+C）
                result = await asyncio.wrap_future(future)
                # 检查是否收到中断信号
                if shutdown_requested:
                    raise KeyboardInterrupt()
                return result
            except (KeyboardInterrupt, concurrent.futures.CancelledError):
                # 取消任务
                try:
                    future.cancel()
                except:
                    pass
                raise KeyboardInterrupt()
    except KeyboardInterrupt:
        raise

async def login_and_get_session():
    """登录并获取 session_string"""
    global client_instance
    
    print("=" * 60)
    print("🔐 Telegram 登录辅助工具")
    print("💡 提示：按 Ctrl+C 可随时中断")
    print("=" * 60)
    
    # 检查中断信号
    if shutdown_requested:
        return False
    
    # 读取配置文件
    if not CONFIG_FILE.exists():
        print(f"❌ 配置文件不存在: {CONFIG_FILE}")
        print("请先创建配置文件")
        return False
    
    try:
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            config = json.load(f)
    except Exception as e:
        print(f"❌ 读取配置文件失败: {e}")
        return False
    
    telegram_config = config.get('telegram', {})
    api_id = telegram_config.get('api_id')
    api_hash = telegram_config.get('api_hash')
    phone = telegram_config.get('phone')
    
    if not api_id or not api_hash:
        print("❌ 配置文件中缺少 api_id 或 api_hash")
        return False
    
    if not phone:
        print("❌ 配置文件中缺少 phone")
        return False
    
    print(f"\n📱 手机号: {phone}")
    print(f"🔑 API ID: {api_id}")
    print(f"🔑 API Hash: {api_hash[:10]}...")
    
    # 创建客户端（使用临时会话）
    print("\n🔌 正在连接 Telegram...")
    client = TelegramClient(StringSession(), api_id, api_hash)
    client_instance = client
    
    try:
        # 检查中断信号
        if shutdown_requested:
            return False
            
        await client.connect()
        
        # 检查中断信号
        if shutdown_requested:
            return False
            
        print("✅ 连接成功")
        
        # 检查是否已认证
        if await client.is_user_authorized():
            
            # 检查中断信号
            if shutdown_requested:
                return False
            print("✅ 已认证，获取 session_string...")
            session_string = client.session.save()
            
            # 更新配置文件
            config['telegram']['session_string'] = session_string
            with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
                json.dump(config, f, ensure_ascii=False, indent=2)
            
            print(f"\n✅ session_string 已保存到配置文件")
            print(f"📁 配置文件: {CONFIG_FILE}")
            print("\n💡 提示：现在可以重启 Telegram 监听服务了")
            return True
        else:
            print("⚠️  未认证，需要登录")
            
            # 发送验证码
            print(f"\n📤 正在发送验证码到 {phone}...")
            await client.send_code_request(phone)
            
            # 检查中断信号
            if shutdown_requested:
                return False
                
            print("✅ 验证码已发送，请查看 Telegram 应用")
            
            # 输入验证码
            try:
                code = await safe_input("\n📝 请输入收到的验证码: ")
                code = code.strip()
            except KeyboardInterrupt:
                print("\n⚠️  用户中断")
                return False
                
            if not code:
                print("❌ 验证码不能为空")
                return False
            
            try:
                # 检查中断信号
                if shutdown_requested:
                    return False
                    
                # 使用验证码登录
                await client.sign_in(phone, code)
                
                # 检查中断信号
                if shutdown_requested:
                    return False
                    
                print("✅ 登录成功")
                
                # 获取 session_string
                session_string = client.session.save()
                
                # 更新配置文件
                config['telegram']['session_string'] = session_string
                with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
                    json.dump(config, f, ensure_ascii=False, indent=2)
                
                print(f"\n✅ session_string 已保存到配置文件")
                print(f"📁 配置文件: {CONFIG_FILE}")
                print("\n💡 提示：现在可以重启 Telegram 监听服务了")
                return True
                
            except SessionPasswordNeededError:
                # 需要两步验证密码
                print("🔐 需要两步验证密码")
                try:
                    password = await safe_input("请输入两步验证密码: ")
                    password = password.strip()
                except KeyboardInterrupt:
                    print("\n⚠️  用户中断")
                    return False
                
                if not password:
                    print("❌ 密码不能为空")
                    return False
                
                # 检查中断信号
                if shutdown_requested:
                    return False
                    
                await client.sign_in(password=password)
                
                # 检查中断信号
                if shutdown_requested:
                    return False
                    
                print("✅ 两步验证成功")
                
                # 获取 session_string
                session_string = client.session.save()
                
                # 更新配置文件
                config['telegram']['session_string'] = session_string
                with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
                    json.dump(config, f, ensure_ascii=False, indent=2)
                
                print(f"\n✅ session_string 已保存到配置文件")
                print(f"📁 配置文件: {CONFIG_FILE}")
                print("\n💡 提示：现在可以重启 Telegram 监听服务了")
                return True
                
            except PhoneCodeInvalidError:
                print("❌ 验证码无效")
                return False
                
    except KeyboardInterrupt:
        print("\n⚠️  用户中断")
        return False
    except Exception as e:
        print(f"❌ 登录失败: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        try:
            if client and client.is_connected():
                await client.disconnect()
                print("✅ 已断开连接")
        except:
            pass
        client_instance = None

async def main():
    """主函数"""
    try:
        success = await login_and_get_session()
        if success:
            print("\n" + "=" * 60)
            print("✅ 登录完成！")
            print("=" * 60)
        else:
            if shutdown_requested:
                print("\n" + "=" * 60)
                print("⚠️  用户中断，退出")
                print("=" * 60)
            else:
                print("\n" + "=" * 60)
                print("❌ 登录失败")
                print("=" * 60)
    except KeyboardInterrupt:
        print("\n\n👋 用户中断，退出")
    except Exception as e:
        print(f"\n❌ 发生错误: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    # 设置信号处理（Windows 和 Unix 都支持）
    if sys.platform != 'win32':
        # Unix/Linux 系统
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
    else:
        # Windows 系统
        signal.signal(signal.SIGINT, signal_handler)
        # Windows 可能不支持 SIGTERM，但尝试设置
        try:
            signal.signal(signal.SIGTERM, signal_handler)
        except:
            pass
    
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n👋 程序已退出")
    except Exception as e:
        print(f"\n❌ 程序异常退出: {e}")
        import traceback
        traceback.print_exc()

