#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Telegram Bot 主处理器
用于启动和管理 Bot 实例
"""

import asyncio
from typing import Dict, Any, Optional
from utils.logger import get_logger

logger = get_logger(__name__)


class TelegramBotHandler:
    """Telegram Bot 处理器"""
    
    def __init__(self, platform_instance):
        """
        初始化 Bot 处理器
        
        Args:
            platform_instance: TelegramBotPlatform 实例
        """
        self.platform = platform_instance
        self.running = False
    
    async def start(self):
        """启动 Bot（轮询模式）"""
        if not self.platform.connected:
            await self.platform.connect()
        
        if not self.platform.application:
            logger.error("Bot Application 未初始化")
            return
        
        try:
            logger.info("🚀 启动 Telegram Bot 轮询...")
            await self.platform.start_polling()
            self.running = True
            logger.info("✅ Telegram Bot 轮询已启动")
        except Exception as e:
            logger.error(f"❌ 启动 Telegram Bot 失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
    
    async def stop(self):
        """停止 Bot"""
        if self.running:
            try:
                await self.platform.stop_polling()
                self.running = False
                logger.info("✅ Telegram Bot 已停止")
            except Exception as e:
                logger.error(f"❌ 停止 Telegram Bot 失败: {e}")
    
    async def run_forever(self):
        """运行 Bot（阻塞）"""
        await self.start()
        try:
            # 保持运行
            while self.running:
                await asyncio.sleep(1)
        except KeyboardInterrupt:
            logger.info("收到停止信号，正在关闭 Bot...")
        finally:
            await self.stop()

