#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
基于wxauto的微信群配置管理器
支持多群聊监听和配置
"""

import asyncio
import json
import os
import time
from typing import Dict, List, Optional, Any

from core.message_forward.platforms.wxauto_wechat import WxAutoWeChatPlatform
from core.message_forward.models import ForwardRule, PlatformType
from utils.logger import get_logger

logger = get_logger(__name__)

class WxAutoGroupConfigManager:
    """基于wxauto的微信群配置管理器"""
    
    def __init__(self, config_file: str = 'wxauto_group_config.json'):
        self.config_file = config_file
        self.wxauto_platform = None
        self.config = self.load_config()
    
    def load_config(self) -> Dict[str, Any]:
        """加载配置文件"""
        try:
            if os.path.exists(self.config_file):
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
        except Exception as e:
            logger.error(f"加载配置文件失败: {e}")
        
        # 返回默认配置
        return {
            "forward_rules": [],
            "discovered_groups": [],
            "listening_groups": [],
            "keywords": ["买入", "卖出", "开仓", "平仓", "BTC", "ETH", "USDT"],
            "forward_targets": [],
            "wechat_version": "3.9.8",
            "max_listeners": 40,
            "created_at": time.strftime("%Y-%m-%d %H:%M:%S")
        }
    
    def save_config(self) -> bool:
        """保存配置文件"""
        try:
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(self.config, f, ensure_ascii=False, indent=2)
            logger.info(f"配置已保存到: {self.config_file}")
            return True
        except Exception as e:
            logger.error(f"保存配置文件失败: {e}")
            return False
    
    async def initialize_wxauto_platform(self) -> bool:
        """初始化wxauto平台"""
        try:
            wxauto_config = {
                'enabled': True,
                'wechat_version': self.config.get('wechat_version', '3.9.8'),
                'max_listeners': self.config.get('max_listeners', 40),
                'config_file': self.config_file
            }
            
            self.wxauto_platform = WxAutoWeChatPlatform(wxauto_config)
            
            # 连接到微信
            if await self.wxauto_platform.connect():
                logger.info("✅ wxauto平台连接成功")
                return True
            else:
                logger.error("❌ wxauto平台连接失败")
                return False
                
        except Exception as e:
            logger.error(f"初始化wxauto平台失败: {e}")
            return False
    
    async def discover_groups(self) -> List[Dict[str, Any]]:
        """发现微信群"""
        if not self.wxauto_platform or not self.wxauto_platform.is_logged_in:
            logger.error("wxauto平台未连接")
            return []
        
        try:
            groups = self.wxauto_platform.discover_groups()
            self.config["discovered_groups"] = groups
            
            logger.info(f"发现 {len(groups)} 个微信群")
            return groups
            
        except Exception as e:
            logger.error(f"发现微信群失败: {e}")
            return []
    
    def select_groups(self, group_indices: List[int]) -> List[Dict[str, Any]]:
        """选择要监听的群"""
        all_groups = self.config.get("discovered_groups", [])
        selected_groups = []
        
        for idx in group_indices:
            if 0 <= idx < len(all_groups):
                selected_groups.append(all_groups[idx])
        
        # 更新配置中的选择状态
        for group in self.config["discovered_groups"]:
            group["is_selected"] = group in selected_groups
        
        return selected_groups
    
    def configure_keywords(self, keywords: List[str]):
        """配置关键词"""
        self.config["keywords"] = keywords
        logger.info(f"已配置 {len(keywords)} 个关键词")
    
    def configure_forward_targets(self, targets: List[str]):
        """配置转发目标"""
        self.config["forward_targets"] = targets
        logger.info(f"已配置 {len(targets)} 个转发目标")
    
    def add_group_listener(self, group_name: str) -> bool:
        """添加群聊监听"""
        if not self.wxauto_platform:
            logger.error("wxauto平台未初始化")
            return False
        
        try:
            success = self.wxauto_platform.add_group_listener(group_name)
            if success:
                # 更新配置
                self.config["listening_groups"].append({
                    'name': group_name,
                    'added_at': time.strftime("%Y-%m-%d %H:%M:%S")
                })
                self.save_config()
            
            return success
            
        except Exception as e:
            logger.error(f"添加群聊监听失败: {e}")
            return False
    
    def remove_group_listener(self, group_name: str) -> bool:
        """移除群聊监听"""
        if not self.wxauto_platform:
            logger.error("wxauto平台未初始化")
            return False
        
        try:
            success = self.wxauto_platform.remove_group_listener(group_name)
            if success:
                # 更新配置
                self.config["listening_groups"] = [
                    g for g in self.config["listening_groups"] 
                    if g.get('name') != group_name
                ]
                self.save_config()
            
            return success
            
        except Exception as e:
            logger.error(f"移除群聊监听失败: {e}")
            return False
    
    def get_listening_groups(self) -> List[Dict[str, Any]]:
        """获取正在监听的群聊列表"""
        if not self.wxauto_platform:
            return []
        
        return self.wxauto_platform.get_listening_groups()
    
    def generate_forward_rules(self, selected_groups: List[Dict[str, Any]]) -> List[ForwardRule]:
        """生成转发规则"""
        rules = []
        keywords = self.config.get("keywords", [])
        forward_targets = self.config.get("forward_targets", [])
        
        for i, group in enumerate(selected_groups, 1):
            rule = ForwardRule(
                rule_id=f"wxauto_rule_{i}",
                rule_name=f"wxauto群监听规则 {i}",
                enabled=True,
                source_platform="wechat",
                source_chat_ids=[group["name"]],
                target_platforms=["wechat"] if forward_targets else [],
                target_chat_ids={
                    "wechat": forward_targets
                } if forward_targets else {},
                keywords=keywords,
                add_prefix="[wxauto转发] ",
                add_suffix=""
            )
            rules.append(rule)
        
        return rules
    
    def get_forward_rules_for_manager(self) -> List[Dict[str, Any]]:
        """获取用于管理器的转发规则配置"""
        rules_config = []
        
        for rule in self.generate_forward_rules(
            [g for g in self.config["discovered_groups"] if g.get("is_selected", False)]
        ):
            rules_config.append(rule.to_dict())
        
        return rules_config
    
    def print_groups(self):
        """打印群聊列表"""
        groups = self.config.get("discovered_groups", [])
        
        if not groups:
            print("❌ 没有发现群聊")
            return
        
        print(f"\n📊 发现 {len(groups)} 个微信群:")
        print("-" * 60)
        
        for i, group in enumerate(groups, 1):
            status = "✅ 已选择" if group.get("is_selected", False) else "❌ 未选择"
            print(f"{i:2d}. {group.get('name', 'Unknown')} - {status}")
            print(f"     ID: {group.get('id', '')}")
            print(f"     成员数: {group.get('member_count', 0)}")
            print()
    
    def print_listening_groups(self):
        """打印正在监听的群聊"""
        listening_groups = self.get_listening_groups()
        
        if not listening_groups:
            print("❌ 没有正在监听的群聊")
            return
        
        print(f"\n🎧 正在监听 {len(listening_groups)} 个群聊:")
        print("-" * 60)
        
        for i, group in enumerate(listening_groups, 1):
            print(f"{i:2d}. {group.get('name', 'Unknown')}")
            print(f"     监听ID: {group.get('id', '')}")
            print(f"     添加时间: {group.get('info', {}).get('added_at', 'Unknown')}")
            print()
    
    def print_keywords(self):
        """打印关键词配置"""
        keywords = self.config.get("keywords", [])
        
        print(f"\n🔑 已配置 {len(keywords)} 个关键词:")
        print("-" * 40)
        
        for i, keyword in enumerate(keywords, 1):
            print(f"{i:2d}. {keyword}")
        print()
    
    def print_forward_targets(self):
        """打印转发目标"""
        targets = self.config.get("forward_targets", [])
        
        if not targets:
            print("\n🎯 未配置转发目标")
            return
        
        print(f"\n🎯 已配置 {len(targets)} 个转发目标:")
        print("-" * 40)
        
        for i, target in enumerate(targets, 1):
            print(f"{i:2d}. {target}")
        print()
    
    def print_config_summary(self):
        """打印配置摘要"""
        print("\n" + "=" * 60)
        print("📋 wxauto微信群配置摘要")
        print("=" * 60)
        
        groups = self.config.get("discovered_groups", [])
        selected_groups = [g for g in groups if g.get("is_selected", False)]
        listening_groups = self.get_listening_groups()
        keywords = self.config.get("keywords", [])
        targets = self.config.get("forward_targets", [])
        
        print(f"📊 总群数: {len(groups)}")
        print(f"✅ 已选择: {len(selected_groups)}")
        print(f"🎧 正在监听: {len(listening_groups)}")
        print(f"🔑 关键词: {len(keywords)}")
        print(f"🎯 转发目标: {len(targets)}")
        print(f"📱 微信版本: {self.config.get('wechat_version', '3.9.8')}")
        print(f"🔢 最大监听数: {self.config.get('max_listeners', 40)}")
        
        if selected_groups:
            print(f"\n📌 选择的群:")
            for group in selected_groups:
                print(f"  - {group.get('name', 'Unknown')}")
        
        if listening_groups:
            print(f"\n🎧 正在监听的群:")
            for group in listening_groups:
                print(f"  - {group.get('name', 'Unknown')}")
        
        if keywords:
            print(f"\n🔑 关键词:")
            print(f"  {', '.join(keywords[:5])}{'...' if len(keywords) > 5 else ''}")
        
        if targets:
            print(f"\n🎯 转发目标:")
            for target in targets:
                print(f"  - {target}")
        
        print("=" * 60)
    
    async def cleanup(self):
        """清理资源"""
        if self.wxauto_platform:
            await self.wxauto_platform.disconnect()


async def interactive_config():
    """交互式配置"""
    print("=" * 60)
    print("🔧 wxauto微信群配置管理工具")
    print("=" * 60)
    
    manager = WxAutoGroupConfigManager()
    
    try:
        # 初始化wxauto平台
        print("📱 正在连接微信...")
        print("💡 请确保微信客户端已打开并登录")
        print("💡 建议使用微信版本 3.9.8")
        print("-" * 60)
        
        if not await manager.initialize_wxauto_platform():
            print("❌ 微信连接失败")
            return
        
        # 发现群聊
        print("🔍 正在发现微信群...")
        groups = await manager.discover_groups()
        
        if not groups:
            print("❌ 没有发现群聊")
            return
        
        # 显示群聊列表
        manager.print_groups()
        
        # 选择要监听的群
        print("🎯 选择要监听的微信群:")
        print("💡 输入群号（用逗号分隔），例如: 1,3,5")
        print("💡 输入 'all' 选择所有群")
        print("💡 输入 'none' 不选择任何群")
        print("-" * 60)
        
        while True:
            try:
                choice = input("请选择: ").strip()
                
                if choice.lower() == 'all':
                    selected_groups = manager.select_groups(list(range(len(groups))))
                    break
                elif choice.lower() == 'none':
                    selected_groups = []
                    break
                else:
                    indices = [int(x.strip()) - 1 for x in choice.split(',')]
                    selected_groups = manager.select_groups(indices)
                    if selected_groups:
                        break
                    else:
                        print("❌ 没有选择有效的群，请重新选择")
                        
            except ValueError:
                print("❌ 输入格式错误，请输入数字或 'all'/'none'")
            except KeyboardInterrupt:
                print("\n⏹️  用户取消配置")
                return
        
        # 添加群聊监听
        print("\n🎧 添加群聊监听...")
        for group in selected_groups:
            group_name = group.get('name', '')
            if group_name:
                success = manager.add_group_listener(group_name)
                if success:
                    print(f"✅ 已添加监听: {group_name}")
                else:
                    print(f"❌ 添加监听失败: {group_name}")
        
        # 配置关键词
        print("\n🔑 配置监听关键词:")
        print("💡 输入关键词（用逗号分隔），例如: 买入,卖出,BTC,ETH")
        print("💡 输入 'default' 使用默认交易关键词")
        print("-" * 60)
        
        default_keywords = ["买入", "卖出", "开仓", "平仓", "BTC", "ETH", "USDT", "交易", "信号"]
        
        while True:
            try:
                choice = input("请输入关键词: ").strip()
                
                if choice.lower() == 'default':
                    keywords = default_keywords
                    break
                elif choice:
                    keywords = [kw.strip() for kw in choice.split(',') if kw.strip()]
                    if keywords:
                        break
                    else:
                        print("❌ 请输入有效的关键词")
                else:
                    print("❌ 请输入关键词")
                    
            except KeyboardInterrupt:
                print("\n⏹️  用户取消配置")
                return
        
        manager.configure_keywords(keywords)
        
        # 配置转发目标
        print("\n🎯 配置转发目标:")
        print("💡 输入目标群名（用逗号分隔），例如: 跟单执行群,策略执行群")
        print("💡 输入 'none' 不转发")
        print("-" * 60)
        
        while True:
            try:
                choice = input("请输入转发目标: ").strip()
                
                if choice.lower() == 'none':
                    targets = []
                    break
                elif choice:
                    targets = [target.strip() for target in choice.split(',') if target.strip()]
                    if targets:
                        break
                    else:
                        print("❌ 请输入有效的目标群名")
                else:
                    print("❌ 请输入转发目标")
                    
            except KeyboardInterrupt:
                print("\n⏹️  用户取消配置")
                return
        
        manager.configure_forward_targets(targets)
        
        # 保存配置
        if manager.save_config():
            print("\n💾 配置已保存")
        
        # 显示配置摘要
        manager.print_config_summary()
        
        print("\n🎉 配置完成！")
        print("💡 现在可以运行消息转发管理器:")
        print("   python core/message_forward/main.py")
        
    except KeyboardInterrupt:
        print("\n⏹️  用户取消操作")
    except Exception as e:
        logger.error(f"配置过程出错: {e}")
    finally:
        await manager.cleanup()


if __name__ == "__main__":
    asyncio.run(interactive_config())
