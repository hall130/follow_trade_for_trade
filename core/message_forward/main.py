#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
消息转发系统工具脚本
用于测试、配置和管理微信群监听转发功能
注意：这不是系统的主启动入口，主启动入口是根目录的main.py
"""

import asyncio
import json
import os
import sys
from typing import Dict, Any

# 添加项目根目录到Python路径
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.message_forward.manager import MessageForwardManager
from core.message_forward.platforms.wechat import WeChatPlatform
from core.message_forward.platforms.wxauto_wechat import WxAutoWeChatPlatform
from core.message_forward.wechat_config_manager import WeChatGroupConfigManager
from core.message_forward.wxauto_config_manager import WxAutoGroupConfigManager
from utils.logger import get_logger

logger = get_logger(__name__)

class MessageForwardSystem:
    """消息转发系统"""
    
    def __init__(self):
        self.manager = MessageForwardManager()
        self.running = False
    
    async def initialize(self):
        """初始化系统"""
        logger.info("🚀 初始化消息转发系统...")
        
        # 初始化微信平台
        wechat_config = {
            'enabled': True,
            'hot_reload': True,
            'config_file': 'wechat_group_config.json'
        }
        
        wechat_platform = WeChatPlatform(wechat_config)
        await self.manager.add_platform(wechat_platform)
        
        # 加载微信群配置
        await self.manager.load_wechat_group_config()
        
        logger.info("✅ 系统初始化完成")
    
    async def start(self):
        """启动系统"""
        if self.running:
            logger.warning("系统已经在运行")
            return
        
        logger.info("🚀 启动消息转发系统...")
        self.running = True
        
        await self.manager.start()
        
        logger.info("✅ 消息转发系统已启动")
    
    async def stop(self):
        """停止系统"""
        logger.info("⏹️  停止消息转发系统...")
        self.running = False
        
        await self.manager.stop()
        
        logger.info("✅ 消息转发系统已停止")
    
    def get_status(self) -> Dict[str, Any]:
        """获取系统状态"""
        status = self.manager.get_status()
        status['wechat_config'] = self.manager.get_wechat_config_summary()
        return status
    
    def print_status(self):
        """打印系统状态"""
        status = self.get_status()
        
        print("\n" + "=" * 60)
        print("📊 消息转发系统状态")
        print("=" * 60)
        
        print(f"🔄 运行状态: {'✅ 运行中' if status['running'] else '❌ 已停止'}")
        print(f"📱 连接平台: {len(status['platforms'])}")
        
        for platform_name, platform_status in status['platforms'].items():
            status_icon = "✅" if platform_status['connected'] else "❌"
            print(f"  {status_icon} {platform_name}: {'已连接' if platform_status['connected'] else '未连接'}")
        
        print(f"📋 转发规则: {status['forward_rules_count']} (活跃: {status['active_rules_count']})")
        print(f"💬 消息历史: {status['message_history_count']}")
        
        # 微信群配置状态
        wechat_config = status.get('wechat_config', {})
        if wechat_config:
            print(f"\n📱 微信群配置:")
            print(f"  📊 总群数: {wechat_config['groups_count']}")
            print(f"  ✅ 已选择: {wechat_config['selected_groups_count']}")
            print(f"  🔑 关键词: {wechat_config['keywords_count']}")
            print(f"  🎯 转发目标: {wechat_config['forward_targets_count']}")
            print(f"  📄 配置文件: {wechat_config['config_file']}")
        
        print("=" * 60)


async def interactive_menu():
    """交互式菜单"""
    system = MessageForwardSystem()
    
    while True:
        print("\n" + "=" * 60)
        print("🤖 消息转发系统控制台")
        print("=" * 60)
        print("1. 🔧 配置微信群 (itchat)")
        print("2. 🔧 配置微信群 (wxauto)")
        print("3. 📊 查看系统状态")
        print("4. 🚀 启动系统")
        print("5. ⏹️  停止系统")
        print("6. 📋 查看转发规则")
        print("7. 💬 查看消息历史")
        print("8. 🔍 发现微信群")
        print("9. ❌ 退出")
        print("-" * 60)
        
        try:
            choice = input("请选择操作 (1-9): ").strip()
            
            if choice == '1':
                await configure_wechat_groups(system, 'itchat')
            elif choice == '2':
                await configure_wechat_groups(system, 'wxauto')
            elif choice == '3':
                system.print_status()
            elif choice == '4':
                await system.start()
            elif choice == '5':
                await system.stop()
            elif choice == '6':
                print_forward_rules(system)
            elif choice == '7':
                print_message_history(system)
            elif choice == '8':
                await discover_groups(system)
            elif choice == '9':
                print("👋 再见！")
                break
            else:
                print("❌ 无效选择，请输入 1-9")
                
        except KeyboardInterrupt:
            print("\n👋 再见！")
            break
        except Exception as e:
            logger.error(f"操作失败: {e}")
            print(f"❌ 操作失败: {e}")


async def configure_wechat_groups(system: MessageForwardSystem, platform_type: str = 'itchat'):
    """配置微信群"""
    print(f"\n🔧 配置微信群 ({platform_type})...")
    
    try:
        if platform_type == 'wxauto':
            # 使用wxauto配置管理器
            config_manager = WxAutoGroupConfigManager()
            
            # 初始化wxauto平台
            if await config_manager.initialize_wxauto_platform():
                # 发现群聊
                groups = await config_manager.discover_groups()
                
                if groups:
                    config_manager.print_groups()
                    
                    # 这里可以添加交互式选择逻辑
                    print("💡 请使用独立的配置工具进行详细配置:")
                    print("   python core/message_forward/wxauto_config_manager.py")
                else:
                    print("❌ 没有发现群聊")
            else:
                print("❌ wxauto平台连接失败")
        else:
            # 使用itchat配置管理器
            config_manager = WeChatGroupConfigManager()
            
            # 初始化微信平台
            if await config_manager.initialize_wechat_platform():
                # 发现群聊
                groups = await config_manager.discover_groups()
                
                if groups:
                    config_manager.print_groups()
                    
                    # 这里可以添加交互式选择逻辑
                    print("💡 请使用独立的配置工具进行详细配置:")
                    print("   python core/message_forward/wechat_config_manager.py")
                else:
                    print("❌ 没有发现群聊")
            else:
                print("❌ 微信平台连接失败")
            
    except Exception as e:
        logger.error(f"配置微信群失败: {e}")
        print(f"❌ 配置失败: {e}")


def print_forward_rules(system: MessageForwardSystem):
    """打印转发规则"""
    rules = system.manager.list_forward_rules()
    
    print(f"\n📋 转发规则 ({len(rules)} 条):")
    print("-" * 60)
    
    if not rules:
        print("❌ 没有配置转发规则")
        return
    
    for i, rule in enumerate(rules, 1):
        status = "✅ 启用" if rule.enabled else "❌ 禁用"
        print(f"{i:2d}. {rule.rule_name} - {status}")
        print(f"    源平台: {rule.source_platform}")
        print(f"    源聊天: {', '.join(rule.source_chat_ids) if rule.source_chat_ids else '全部'}")
        print(f"    目标平台: {', '.join(rule.target_platforms)}")
        print(f"    关键词: {', '.join(rule.keywords[:3])}{'...' if len(rule.keywords) > 3 else ''}")
        print()


def print_message_history(system: MessageForwardSystem):
    """打印消息历史"""
    history = system.manager.get_message_history(10)
    
    print(f"\n💬 最近消息 ({len(history)} 条):")
    print("-" * 60)
    
    if not history:
        print("❌ 没有消息历史")
        return
    
    for i, message in enumerate(history, 1):
        platform = message.source_platform.value if message.source_platform else 'Unknown'
        content = message.content[:50] + '...' if len(message.content) > 50 else message.content
        print(f"{i:2d}. [{platform}] {content}")
        print(f"    时间: {message.timestamp.strftime('%H:%M:%S')}")
        print(f"    用户: {message.source_username or 'Unknown'}")
        print()


async def discover_groups(system: MessageForwardSystem):
    """发现微信群"""
    print("\n🔍 发现微信群...")
    
    try:
        groups = system.manager.get_wechat_groups()
        
        if groups:
            print(f"📊 发现 {len(groups)} 个微信群:")
            print("-" * 60)
            
            for i, group in enumerate(groups, 1):
                print(f"{i:2d}. {group.get('name', 'Unknown')}")
                print(f"     ID: {group.get('id', '')}")
                print(f"     成员数: {group.get('member_count', 0)}")
                print()
        else:
            print("❌ 没有发现群聊")
            
    except Exception as e:
        logger.error(f"发现微信群失败: {e}")
        print(f"❌ 发现失败: {e}")


async def main():
    """主函数"""
    print("🔧 消息转发系统工具")
    print("📖 用于测试、配置和管理微信群监听转发功能")
    print("⚠️  注意：这不是系统的主启动入口")
    print("💡 系统主启动入口：python main.py")
    print()
    
    try:
        await interactive_menu()
    except KeyboardInterrupt:
        print("\n👋 用户中断，退出程序")
    except Exception as e:
        logger.error(f"程序运行出错: {e}")
        print(f"❌ 程序出错: {e}")


if __name__ == "__main__":
    print("=" * 60)
    print("🔧 消息转发系统工具脚本")
    print("=" * 60)
    print("⚠️  重要提示：")
    print("   这不是系统的主启动入口！")
    print("   主启动入口是根目录的 main.py")
    print()
    print("💡 使用方法：")
    print("   1. 配置微信群：python core/message_forward/wechat_config_manager.py")
    print("   2. 测试转发功能：python core/message_forward/main.py")
    print("   3. 启动完整系统：python main.py")
    print("=" * 60)
    print()
    
    asyncio.run(main())
