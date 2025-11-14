#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Telegram 7x24小时消息监听与转发服务
集成消息转发管理器，实现消息过滤和转发
"""

import asyncio
import sys
import os
import json
from typing import Dict, List, Optional, Any
from datetime import datetime
from pathlib import Path
import signal

# 添加项目根目录到Python路径
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from core.message_forward.platforms.telegram_mtproto import TelegramMTProtoPlatform, telegram_manager
from core.message_forward.manager import MessageForwardManager
from core.message_forward.models import Message, MessageType, PlatformType, ForwardRule
from utils.logger import get_logger

logger = get_logger(__name__)

class TelegramListenerService:
    """Telegram 7x24小时消息监听与转发服务"""
    
    def __init__(self, config: Dict[str, Any]):
        """
        初始化服务
        
        Args:
            config: 配置字典，包含：
                - telegram: Telegram配置（api_id, api_hash, phone, session_string等）
                - forward_rules: 转发规则列表
                - target_platforms: 目标平台配置（钉钉、微信、微信公众号等）
        """
        self.config = config
        self.telegram_config = config.get('telegram', {})
        self.forward_rules_config = config.get('forward_rules', [])
        self.target_platforms_config = config.get('target_platforms', {})
        
        # 初始化消息转发管理器
        self.forward_manager = MessageForwardManager()
        
        # Telegram 平台实例
        self.telegram_platform: Optional[TelegramMTProtoPlatform] = None
        
        # 运行状态
        self.running = False
        self.should_stop = False
        
        # 统计信息
        self.stats = {
            'total_messages': 0,
            'filtered_messages': 0,
            'forwarded_messages': 0,
            'failed_forwards': 0,
            'start_time': None,
            'last_message_time': None
        }
        
        logger.info("Telegram 监听服务初始化完成")
    
    async def initialize(self) -> bool:
        """初始化服务"""
        try:
            logger.info("🚀 正在初始化 Telegram 监听服务...")
            
            # 1. 初始化 Telegram 平台
            if not await self._initialize_telegram():
                logger.error("❌ Telegram 平台初始化失败")
                return False
            
            # 2. 初始化目标平台（钉钉、微信等）
            if not await self._initialize_target_platforms():
                logger.warning("⚠️  部分目标平台初始化失败，但服务将继续运行")
            
            # 3. 加载转发规则
            await self._load_forward_rules()
            
            logger.info("✅ Telegram 监听服务初始化成功")
            return True
            
        except Exception as e:
            logger.error(f"❌ 初始化服务失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return False
    
    async def _initialize_telegram(self) -> bool:
        """初始化 Telegram 平台"""
        try:
            # 创建 Telegram 平台实例
            self.telegram_platform = TelegramMTProtoPlatform(self.telegram_config)
            
            # 初始化客户端
            if not await self.telegram_platform.initialize():
                logger.error("Telegram 客户端初始化失败")
                return False
            
            # 如果未认证，提示用户需要先登录
            if not self.telegram_platform.is_authenticated:
                logger.error("=" * 60)
                logger.error("❌ Telegram 客户端未认证，无法启动监听服务")
                logger.error("=" * 60)
                logger.error("💡 解决方案：")
                logger.error("   1. 运行登录脚本: python telegram_login_helper.py")
                logger.error("   2. 或者使用测试脚本: python test_telegram_mtproto.py")
                logger.error("   3. 登录成功后，session_string 会自动保存到配置文件")
                logger.error("   4. 然后重启 Telegram 监听服务")
                logger.error("=" * 60)
                return False
            
            # 添加消息处理器
            self.telegram_platform.add_message_handler(self._handle_telegram_message)
            
            logger.info("✅ Telegram 平台初始化成功")
            return True
            
        except Exception as e:
            logger.error(f"初始化 Telegram 平台失败: {e}")
            return False
    
    async def _initialize_target_platforms(self) -> bool:
        """初始化目标平台（钉钉、微信等）"""
        success_count = 0
        total_count = 0
        
        # 初始化钉钉
        if self.target_platforms_config.get('dingtalk', {}).get('enabled'):
            total_count += 1
            try:
                from core.message_forward.platforms.dingtalk import DingTalkPlatform
                dingtalk_platform = DingTalkPlatform(self.target_platforms_config['dingtalk'])
                if await self.forward_manager.add_platform(dingtalk_platform):
                    success_count += 1
                    logger.info("✅ 钉钉平台初始化成功")
                else:
                    logger.warning("⚠️  钉钉平台初始化失败")
            except Exception as e:
                logger.error(f"初始化钉钉平台失败: {e}")
        
        # 初始化微信公众号
        if self.target_platforms_config.get('wechat_official', {}).get('enabled'):
            total_count += 1
            try:
                from core.message_forward.platforms.wechat_official import WeChatOfficialPlatform
                wechat_official_platform = WeChatOfficialPlatform(self.target_platforms_config['wechat_official'])
                if await self.forward_manager.add_platform(wechat_official_platform):
                    success_count += 1
                    logger.info("✅ 微信公众号平台初始化成功")
                else:
                    logger.warning("⚠️  微信公众号平台初始化失败")
            except Exception as e:
                logger.error(f"初始化微信公众号平台失败: {e}")
        
        # 初始化微信（wxauto）
        if self.target_platforms_config.get('wechat', {}).get('enabled'):
            total_count += 1
            try:
                from core.message_forward.platforms.wxauto_wechat import WxAutoWeChatPlatform
                wechat_platform = WxAutoWeChatPlatform(self.target_platforms_config['wechat'])
                if await self.forward_manager.add_platform(wechat_platform):
                    success_count += 1
                    logger.info("✅ 微信平台初始化成功")
                else:
                    logger.warning("⚠️  微信平台初始化失败")
            except Exception as e:
                logger.error(f"初始化微信平台失败: {e}")
        
        logger.info(f"目标平台初始化完成: {success_count}/{total_count}")
        return success_count > 0
    
    async def _load_forward_rules(self):
        """加载转发规则"""
        try:
            # 如果配置中没有规则，创建一个默认规则来转发所有消息
            if not self.forward_rules_config:
                logger.info("⚠️  转发规则列表为空，将创建默认规则转发所有消息")
                
                # 获取所有已启用的目标平台
                enabled_platforms = []
                target_chat_ids = {}
                
                if self.target_platforms_config.get('dingtalk', {}).get('enabled'):
                    enabled_platforms.append('dingtalk')
                    # 钉钉使用 webhook_url 作为 chat_id
                    webhook_url = self.target_platforms_config['dingtalk'].get('webhook_url')
                    if webhook_url:
                        target_chat_ids['dingtalk'] = [webhook_url]
                
                if self.target_platforms_config.get('wechat_official', {}).get('enabled'):
                    enabled_platforms.append('wechat_official')
                    # 微信公众号需要配置接收者列表，这里先留空，需要用户配置
                    target_chat_ids['wechat_official'] = []
                
                if self.target_platforms_config.get('wechat', {}).get('enabled'):
                    enabled_platforms.append('wechat')
                    # 微信需要配置接收者列表，这里先留空，需要用户配置
                    target_chat_ids['wechat'] = []
                
                if enabled_platforms:
                    # 创建默认规则：转发所有消息到所有已启用的平台
                    default_rule = ForwardRule(
                        rule_id='default_rule_all_messages',
                        rule_name='默认规则：转发所有消息',
                        enabled=True,
                        source_platform='telegram_mtproto',
                        source_chat_ids=[],  # 空列表表示所有聊天
                        target_platforms=enabled_platforms,
                        target_chat_ids=target_chat_ids,
                        keywords=[],  # 空列表表示不限制关键词
                        exclude_keywords=[],
                        add_prefix=None,
                        add_suffix=None,
                        enable_markdown=False
                    )
                    
                    self.forward_manager.add_forward_rule(default_rule)
                    logger.info(f"✅ 已创建默认转发规则: 转发所有消息到 {', '.join(enabled_platforms)}")
                else:
                    logger.warning("⚠️  没有已启用的目标平台，无法创建默认转发规则")
            
            # 加载用户配置的规则
            for rule_config in self.forward_rules_config:
                try:
                    rule = ForwardRule(
                        rule_id=rule_config.get('rule_id', f"rule_{len(self.forward_manager.forward_rules)}"),
                        rule_name=rule_config.get('rule_name', '未命名规则'),
                        enabled=rule_config.get('enabled', True),
                        source_platform=rule_config.get('source_platform', 'telegram_mtproto'),
                        source_chat_ids=rule_config.get('source_chat_ids', []),
                        target_platforms=rule_config.get('target_platforms', []),
                        target_chat_ids=rule_config.get('target_chat_ids', {}),
                        keywords=rule_config.get('keywords', []),
                        exclude_keywords=rule_config.get('exclude_keywords', []),
                        add_prefix=rule_config.get('add_prefix'),
                        add_suffix=rule_config.get('add_suffix'),
                        enable_markdown=rule_config.get('enable_markdown', False)
                    )
                    
                    self.forward_manager.add_forward_rule(rule)
                    logger.info(f"✅ 转发规则已加载: {rule.rule_name} (ID: {rule.rule_id})")
                    
                except Exception as e:
                    logger.error(f"加载转发规则失败: {e}")
            
            logger.info(f"共加载 {len(self.forward_manager.forward_rules)} 条转发规则")
            
        except Exception as e:
            logger.error(f"加载转发规则失败: {e}")
    
    async def _forward_message(self, message: Message, rule: ForwardRule):
        """根据规则转发消息"""
        try:
            # 转换消息
            transformed_message = rule.transform_message(message)
            
            # 转发到目标平台
            for target_platform_str in rule.target_platforms:
                # 转换为 PlatformType
                try:
                    target_platform = PlatformType(target_platform_str)
                except ValueError:
                    logger.warning(f"无效的目标平台类型: {target_platform_str}")
                    continue
                
                if target_platform not in self.forward_manager.platforms:
                    logger.warning(f"目标平台未连接: {target_platform.value}")
                    continue
                
                platform = self.forward_manager.platforms[target_platform]
                target_chats = rule.target_chat_ids.get(target_platform_str, [])
                
                if not target_chats:
                    logger.warning(f"规则 {rule.rule_name} 未配置 {target_platform.value} 的目标聊天")
                    continue
                
                # 发送到每个目标聊天
                for chat_id in target_chats:
                    try:
                        success = await platform.send_message(chat_id, transformed_message)
                        if success:
                            logger.info(f"✅ 消息已转发: {target_platform.value} -> {chat_id}")
                        else:
                            logger.error(f"❌ 消息转发失败: {target_platform.value} -> {chat_id}")
                    except Exception as e:
                        logger.error(f"转发消息到 {chat_id} 失败: {e}")
                        
        except Exception as e:
            logger.error(f"转发消息失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
    
    async def _handle_telegram_message(self, message_data: Dict[str, Any]):
        """
        处理 Telegram 消息
        
        Args:
            message_data: 消息数据字典，包含：
                - id: 消息ID
                - chat_id: 聊天ID
                - chat_title: 聊天标题
                - sender_id: 发送者ID
                - sender_username: 发送者用户名
                - text: 消息文本
                - date: 消息时间
                - platform: 平台标识
        """
        try:
            self.stats['total_messages'] += 1
            self.stats['last_message_time'] = datetime.now()
            
            # 构建统一消息对象
            message = Message(
                content=message_data.get('text', ''),
                message_type=MessageType.TEXT,
                timestamp=message_data.get('date', datetime.now()),
                source_platform=PlatformType.TELEGRAM,
                source_chat_id=str(message_data.get('chat_id', '')),
                source_user_id=str(message_data.get('sender_id', '')),
                source_username=message_data.get('sender_username'),
                message_id=str(message_data.get('id', '')),
                extra_data={
                    'chat_title': message_data.get('chat_title'),
                    'platform': 'telegram_mtproto'
                }
            )
            
            # 记录消息
            logger.info(f"📨 收到消息: [{message_data.get('chat_title', '未知')}] {message.content[:50]}...")
            
            # 应用转发规则
            matched_rules = []
            for rule_id, rule in self.forward_manager.forward_rules.items():
                if rule.enabled and rule.matches(message):
                    matched_rules.append(rule)
                    logger.info(f"✅ 消息匹配规则: {rule.rule_name}")
            
            if matched_rules:
                self.stats['filtered_messages'] += 1
                
                # 转发消息
                for rule in matched_rules:
                    try:
                        await self._forward_message(message, rule)
                        self.stats['forwarded_messages'] += 1
                    except Exception as e:
                        logger.error(f"转发消息失败: {e}")
                        self.stats['failed_forwards'] += 1
            else:
                logger.debug("消息未匹配任何转发规则")
                
        except Exception as e:
            logger.error(f"处理 Telegram 消息失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
    
    async def start(self):
        """启动7x24小时监听服务"""
        if self.running:
            logger.warning("服务已经在运行")
            return
        
        if not self.telegram_platform:
            logger.error("Telegram 平台未初始化，无法启动服务")
            # 保存错误状态
            self.get_status()
            return
        
        try:
            logger.info("🚀 启动 Telegram 7x24小时监听服务...")
            self.running = True
            self.should_stop = False
            self.stats['start_time'] = datetime.now()
            
            # 立即保存一次状态，表示服务正在启动
            # 这会在状态文件中标记 running=True，让前端知道服务已启动
            status = self.get_status()
            logger.info(f"✅ 服务状态已更新: running={status['running']}, telegram_connected={status['telegram_connected']}")
            
            # 启动消息转发管理器
            await self.forward_manager.start()
            
            # 启动统计任务（每小时输出一次）
            stats_task = asyncio.create_task(self._stats_task())
            
            # 启动状态保存任务（每60秒保存一次，减少IO操作）
            status_save_task = asyncio.create_task(self._status_save_task())
            
            # 启动 Telegram 监听（阻塞运行）
            listen_task = asyncio.create_task(self.telegram_platform.start_listening())
            
            # 等待任务完成或被中断
            try:
                await asyncio.gather(stats_task, status_save_task, listen_task)
            except asyncio.CancelledError:
                logger.info("监听任务被取消")
            except KeyboardInterrupt:
                logger.info("收到中断信号")
            finally:
                stats_task.cancel()
                status_save_task.cancel()
                await self.stop()
                
        except Exception as e:
            logger.error(f"启动服务失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
            await self.stop()
    
    async def _stats_task(self):
        """统计任务（每小时输出一次）"""
        try:
            while self.running and not self.should_stop:
                await asyncio.sleep(3600)  # 每小时
                
                if self.stats['start_time']:
                    elapsed = datetime.now() - self.stats['start_time']
                    hours = int(elapsed.total_seconds() // 3600)
                    minutes = int((elapsed.total_seconds() % 3600) // 60)
                    
                    logger.info("=" * 60)
                    logger.info("📊 服务运行统计")
                    logger.info("=" * 60)
                    logger.info(f"⏱️  运行时间: {hours}小时{minutes}分钟")
                    logger.info(f"📨 总消息数: {self.stats['total_messages']}")
                    logger.info(f"🔍 过滤消息数: {self.stats['filtered_messages']}")
                    logger.info(f"✅ 转发成功: {self.stats['forwarded_messages']}")
                    logger.info(f"❌ 转发失败: {self.stats['failed_forwards']}")
                    if self.stats['last_message_time']:
                        logger.info(f"🕐 最后消息时间: {self.stats['last_message_time']}")
                    logger.info("=" * 60)
                    
        except asyncio.CancelledError:
            logger.info("统计任务已取消")
        except Exception as e:
            logger.error(f"统计任务失败: {e}")
    
    async def _status_save_task(self):
        """状态保存任务（每60秒保存一次，减少IO操作）"""
        try:
            # 立即保存一次初始状态
            self.get_status()
            
            while self.running and not self.should_stop:
                await asyncio.sleep(60)  # 每60秒（从30秒优化为60秒，减少IO操作）
                # 保存状态
                self.get_status()  # 这会自动保存到文件
        except asyncio.CancelledError:
            logger.info("状态保存任务已取消")
        except Exception as e:
            logger.error(f"状态保存任务失败: {e}")
    
    async def stop(self):
        """停止服务"""
        if not self.running:
            return
        
        logger.info("🛑 正在停止 Telegram 监听服务...")
        self.running = False
        self.should_stop = True
        
        # 停止消息转发管理器
        await self.forward_manager.stop()
        
        # 断开 Telegram 连接
        if self.telegram_platform:
            await self.telegram_platform.stop_listening()
            await self.telegram_platform.disconnect()
        
        logger.info("✅ Telegram 监听服务已停止")
    
    def get_status(self) -> Dict[str, Any]:
        """获取服务状态"""
        status = {
            'running': self.running,
            'stats': self.stats.copy(),
            'telegram_connected': self.telegram_platform.is_connected if self.telegram_platform else False,
            'telegram_authenticated': self.telegram_platform.is_authenticated if self.telegram_platform else False,
            'forward_rules_count': len(self.forward_manager.forward_rules),
            'active_rules_count': sum(1 for r in self.forward_manager.forward_rules.values() if r.enabled),
            'target_platforms_count': len(self.forward_manager.platforms)
        }
        
        # 保存状态到文件（用于进程管理器读取）
        self._save_status_to_file(status)
        
        return status
    
    def _save_status_to_file(self, status: Dict[str, Any]):
        """保存状态到文件"""
        try:
            # 使用绝对路径，确保与管理器使用相同的路径
            # 获取项目根目录（相对于当前文件）
            project_root = Path(__file__).parent.parent.parent
            status_file = project_root / "telegram_listener_status.json"
            with open(status_file, 'w', encoding='utf-8') as f:
                json.dump(status, f, ensure_ascii=False, indent=2, default=str)
        except Exception as e:
            logger.warning(f"保存状态文件失败: {e}")


async def main():
    """主函数 - 用于测试"""
    # 示例配置
    config = {
        'telegram': {
            'api_id': 37878745,
            'api_hash': '1b87612d3752d55fc17384d2d4932f19',
            'phone': '+1234567890',  # 替换为实际手机号
            # 'session_string': '...'  # 如果有会话字符串，使用这个
        },
        'forward_rules': [
            {
                'rule_id': 'rule_1',
                'rule_name': '交易信号转发',
                'enabled': True,
                'source_platform': 'telegram_mtproto',
                'source_chat_ids': ['-1001234567890'],  # 替换为实际群组ID
                'target_platforms': ['dingtalk', 'wechat_official'],
                'target_chat_ids': {
                    'dingtalk': ['webhook_url_1'],
                    'wechat_official': ['openid_1']
                },
                'keywords': ['BTC', 'ETH', '买入', '卖出'],
                'exclude_keywords': ['广告', '推广'],
                'add_prefix': '[TG转发] ',
                'enable_markdown': False
            }
        ],
        'target_platforms': {
            'dingtalk': {
                'enabled': True,
                'webhook_url': 'https://oapi.dingtalk.com/robot/send?access_token=xxx',
                'secret': 'xxx'  # 可选
            },
            'wechat_official': {
                'enabled': True,
                'app_id': 'xxx',
                'app_secret': 'xxx'
            },
            'wechat': {
                'enabled': False,  # wxauto 需要额外配置
                'wechat_version': '3.9.8'
            }
        }
    }
    
    # 创建服务实例
    service = TelegramListenerService(config)
    
    # 初始化服务
    if not await service.initialize():
        logger.error("服务初始化失败")
        return
    
    # 设置信号处理（优雅退出）
    def signal_handler(signum, frame):
        logger.info(f"收到信号 {signum}，正在停止服务...")
        asyncio.create_task(service.stop())
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # 启动服务（7x24小时运行）
    try:
        await service.start()
    except KeyboardInterrupt:
        logger.info("收到中断信号，正在停止服务...")
        await service.stop()


if __name__ == "__main__":
    asyncio.run(main())

