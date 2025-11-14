#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Telegram MTProto 配置工具
用于配置和管理 Telegram 客户端登录
"""

import asyncio
import json
import os
import sys
from typing import Dict, Any, Optional, List

# 添加项目根目录到Python路径
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from core.message_forward.platforms.telegram_mtproto import TelegramMTProtoPlatform, telegram_manager
from utils.logger import get_logger

logger = get_logger(__name__)

class TelegramMTProtoConfigTool:
    """Telegram MTProto 配置工具"""
    
    def __init__(self):
        self.manager = telegram_manager
        self.config_file = "telegram_mtproto_config.json"
    
    def print_menu(self):
        """打印主菜单"""
        print("\n" + "=" * 60)
        print("🔧 Telegram MTProto 配置工具")
        print("=" * 60)
        print("1. 📱 添加 Telegram 账户")
        print("2. 📋 查看已配置的账户")
        print("3. 🔐 登录账户")
        print("4. 💬 获取聊天列表")
        print("5. 📤 发送测试消息")
        print("6. 🗑️ 删除账户")
        print("7. 📊 查看账户状态")
        print("8. 🔄 重新加载配置")
        print("9. ❌ 退出")
        print("-" * 60)
    
    def get_api_credentials(self) -> Dict[str, Any]:
        """获取 API 凭据"""
        print("\n📱 配置 Telegram API 凭据")
        print("请访问 https://my.telegram.org/apps 获取 API ID 和 API Hash")
        print("-" * 40)
        
        api_id = input("请输入 API ID: ").strip()
        api_hash = input("请输入 API Hash: ").strip()
        phone = input("请输入手机号码 (格式: +8613800138000): ").strip()
        
        if not api_id or not api_hash or not phone:
            print("❌ 所有字段都是必填的")
            return {}
        
        try:
            api_id = int(api_id)
        except ValueError:
            print("❌ API ID 必须是数字")
            return {}
        
        return {
            'api_id': api_id,
            'api_hash': api_hash,
            'phone': phone
        }
    
    async def add_account(self):
        """添加账户"""
        print("\n📱 添加 Telegram 账户")
        
        # 获取平台ID
        platform_id = input("请输入平台ID (用于标识此账户): ").strip()
        if not platform_id:
            print("❌ 平台ID不能为空")
            return
        
        # 检查是否已存在
        if platform_id in self.manager.list_platforms():
            print(f"❌ 平台ID '{platform_id}' 已存在")
            return
        
        # 获取API凭据
        credentials = self.get_api_credentials()
        if not credentials:
            return
        
        # 添加平台
        success = await self.manager.add_platform(platform_id, credentials)
        if success:
            print(f"✅ 账户 '{platform_id}' 添加成功")
            print("💡 请使用 '登录账户' 功能完成登录")
        else:
            print(f"❌ 账户 '{platform_id}' 添加失败")
    
    def list_accounts(self):
        """列出所有账户"""
        print("\n📋 已配置的 Telegram 账户")
        print("-" * 40)
        
        platforms = self.manager.list_platforms()
        if not platforms:
            print("📭 暂无配置的账户")
            return
        
        for i, platform_id in enumerate(platforms, 1):
            status = self.manager.get_platform_status(platform_id)
            status_text = "✅ 已认证" if status.get('is_authenticated') else "❌ 未认证"
            phone = status.get('phone', '未知')
            print(f"{i}. {platform_id} ({phone}) - {status_text}")
    
    async def login_account(self):
        """登录账户"""
        print("\n🔐 登录 Telegram 账户")
        
        platforms = self.manager.list_platforms()
        if not platforms:
            print("📭 暂无配置的账户")
            return
        
        # 选择账户
        print("请选择要登录的账户:")
        for i, platform_id in enumerate(platforms, 1):
            status = self.manager.get_platform_status(platform_id)
            status_text = "已认证" if status.get('is_authenticated') else "未认证"
            print(f"{i}. {platform_id} ({status_text})")
        
        try:
            choice = int(input("请输入选择 (数字): ")) - 1
            if 0 <= choice < len(platforms):
                platform_id = platforms[choice]
            else:
                print("❌ 无效选择")
                return
        except ValueError:
            print("❌ 请输入有效数字")
            return
        
        # 检查是否已认证
        status = self.manager.get_platform_status(platform_id)
        if status.get('is_authenticated'):
            print(f"✅ 账户 '{platform_id}' 已经认证")
            return
        
        # 开始登录流程
        print(f"\n🔐 开始登录账户: {platform_id}")
        
        # 发送验证码
        success = await self.manager.login_platform(platform_id)
        if not success:
            print("❌ 登录失败")
            return
        
        # 输入验证码
        phone_code = input("请输入收到的验证码: ").strip()
        if not phone_code:
            print("❌ 验证码不能为空")
            return
        
        # 使用验证码登录
        success = await self.manager.login_platform(platform_id, phone_code)
        if success:
            print(f"✅ 账户 '{platform_id}' 登录成功")
            
            # 获取会话字符串
            platform = self.manager.platforms.get(platform_id)
            if platform:
                session_string = await platform.get_session_string()
                if session_string:
                    print(f"💾 会话字符串已保存，下次登录将自动使用")
        else:
            print("❌ 登录失败，请检查验证码")
    
    async def get_chats(self):
        """获取聊天列表"""
        print("\n💬 获取聊天列表")
        
        platforms = self.manager.list_platforms()
        if not platforms:
            print("📭 暂无配置的账户")
            return
        
        # 选择账户
        print("请选择要查看聊天列表的账户:")
        for i, platform_id in enumerate(platforms, 1):
            status = self.manager.get_platform_status(platform_id)
            status_text = "已认证" if status.get('is_authenticated') else "未认证"
            print(f"{i}. {platform_id} ({status_text})")
        
        try:
            choice = int(input("请输入选择 (数字): ")) - 1
            if 0 <= choice < len(platforms):
                platform_id = platforms[choice]
            else:
                print("❌ 无效选择")
                return
        except ValueError:
            print("❌ 请输入有效数字")
            return
        
        # 检查认证状态
        status = self.manager.get_platform_status(platform_id)
        if not status.get('is_authenticated'):
            print(f"❌ 账户 '{platform_id}' 未认证，请先登录")
            return
        
        # 获取聊天列表
        print(f"\n📋 正在获取账户 '{platform_id}' 的聊天列表...")
        chats = await self.manager.get_platform_chats(platform_id)
        
        if chats:
            print(f"\n📋 找到 {len(chats)} 个聊天:")
            print("-" * 60)
            for i, chat in enumerate(chats, 1):
                chat_type = chat.get('type', 'unknown')
                title = chat.get('title', '未知')
                username = chat.get('username', '')
                chat_id = chat.get('id', '')
                
                username_text = f"(@{username})" if username else ""
                print(f"{i}. {title} {username_text}")
                print(f"   ID: {chat_id}, 类型: {chat_type}")
                print()
        else:
            print("📭 未找到任何聊天")
    
    async def send_test_message(self):
        """发送测试消息"""
        print("\n📤 发送测试消息")
        
        platforms = self.manager.list_platforms()
        if not platforms:
            print("📭 暂无配置的账户")
            return
        
        # 选择账户
        print("请选择发送账户:")
        for i, platform_id in enumerate(platforms, 1):
            status = self.manager.get_platform_status(platform_id)
            status_text = "已认证" if status.get('is_authenticated') else "未认证"
            print(f"{i}. {platform_id} ({status_text})")
        
        try:
            choice = int(input("请输入选择 (数字): ")) - 1
            if 0 <= choice < len(platforms):
                platform_id = platforms[choice]
            else:
                print("❌ 无效选择")
                return
        except ValueError:
            print("❌ 请输入有效数字")
            return
        
        # 检查认证状态
        status = self.manager.get_platform_status(platform_id)
        if not status.get('is_authenticated'):
            print(f"❌ 账户 '{platform_id}' 未认证，请先登录")
            return
        
        # 输入接收者
        chat_id = input("请输入接收者 (用户名或ID): ").strip()
        if not chat_id:
            print("❌ 接收者不能为空")
            return
        
        # 输入消息内容
        message = input("请输入消息内容: ").strip()
        if not message:
            print("❌ 消息内容不能为空")
            return
        
        # 发送消息
        print(f"\n📤 正在发送消息到 {chat_id}...")
        success = await self.manager.send_message(platform_id, chat_id, message)
        
        if success:
            print("✅ 消息发送成功")
        else:
            print("❌ 消息发送失败")
    
    async def delete_account(self):
        """删除账户"""
        print("\n🗑️ 删除 Telegram 账户")
        
        platforms = self.manager.list_platforms()
        if not platforms:
            print("📭 暂无配置的账户")
            return
        
        # 选择账户
        print("请选择要删除的账户:")
        for i, platform_id in enumerate(platforms, 1):
            status = self.manager.get_platform_status(platform_id)
            status_text = "已认证" if status.get('is_authenticated') else "未认证"
            print(f"{i}. {platform_id} ({status_text})")
        
        try:
            choice = int(input("请输入选择 (数字): ")) - 1
            if 0 <= choice < len(platforms):
                platform_id = platforms[choice]
            else:
                print("❌ 无效选择")
                return
        except ValueError:
            print("❌ 请输入有效数字")
            return
        
        # 确认删除
        confirm = input(f"确认删除账户 '{platform_id}'? (y/N): ").strip().lower()
        if confirm != 'y':
            print("❌ 取消删除")
            return
        
        # 删除账户
        success = await self.manager.remove_platform(platform_id)
        if success:
            print(f"✅ 账户 '{platform_id}' 删除成功")
        else:
            print(f"❌ 账户 '{platform_id}' 删除失败")
    
    def show_account_status(self):
        """显示账户状态"""
        print("\n📊 Telegram 账户状态")
        print("-" * 40)
        
        platforms = self.manager.list_platforms()
        if not platforms:
            print("📭 暂无配置的账户")
            return
        
        for platform_id in platforms:
            status = self.manager.get_platform_status(platform_id)
            print(f"\n🔹 账户: {platform_id}")
            print(f"   手机号: {status.get('phone', '未知')}")
            print(f"   连接状态: {'✅ 已连接' if status.get('is_connected') else '❌ 未连接'}")
            print(f"   认证状态: {'✅ 已认证' if status.get('is_authenticated') else '❌ 未认证'}")
    
    def reload_config(self):
        """重新加载配置"""
        print("\n🔄 重新加载配置")
        
        try:
            self.manager.load_config()
            print("✅ 配置重新加载成功")
        except Exception as e:
            print(f"❌ 配置重新加载失败: {e}")
    
    async def run(self):
        """运行配置工具"""
        print("🚀 Telegram MTProto 配置工具启动")
        
        while True:
            self.print_menu()
            choice = input("请选择操作 (1-9): ").strip()
            
            try:
                if choice == '1':
                    await self.add_account()
                elif choice == '2':
                    self.list_accounts()
                elif choice == '3':
                    await self.login_account()
                elif choice == '4':
                    await self.get_chats()
                elif choice == '5':
                    await self.send_test_message()
                elif choice == '6':
                    await self.delete_account()
                elif choice == '7':
                    self.show_account_status()
                elif choice == '8':
                    self.reload_config()
                elif choice == '9':
                    print("👋 退出配置工具")
                    break
                else:
                    print("❌ 无效选择，请输入 1-9")
                    
            except KeyboardInterrupt:
                print("\n\n👋 用户中断，退出配置工具")
                break
            except Exception as e:
                print(f"❌ 操作失败: {e}")

async def main():
    """主函数"""
    tool = TelegramMTProtoConfigTool()
    await tool.run()

if __name__ == "__main__":
    asyncio.run(main())
