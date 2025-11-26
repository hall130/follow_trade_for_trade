#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Hyperliquid WebSocket 管理器
管理多个 Hyperliquid 地址的 WebSocket 连接和订阅
"""

import asyncio
from typing import Dict, List, Optional, Callable, Any
from utils.logger import logger
from exchange.hyperliquid.hyperliquid_ws_client import HyperliquidWebSocketClient
from core.limit_trade.collectors.hyperliquid_trader_collector import HyperliquidTraderCollector


class HyperliquidWebSocketManager:
    """Hyperliquid WebSocket 管理器"""
    
    def __init__(self, is_demo: bool = False):
        """
        初始化管理器
        
        Args:
            is_demo: 是否使用测试网
        """
        self.is_demo = is_demo
        self._ws_client: Optional[HyperliquidWebSocketClient] = None
        self._subscribed_addresses: Dict[str, Callable] = {}  # {address: callback}
        self._connected = False
        self._lock = asyncio.Lock()
        
        # 采集器用于标准化消息
        self._collector = HyperliquidTraderCollector()
    
    async def start(self) -> bool:
        """启动 WebSocket 连接"""
        async with self._lock:
            if self._connected:
                logger.warning("[Hyperliquid WS Manager] 已经启动")
                return True
            
            try:
                # 创建 WebSocket 客户端（不需要 API 密钥，因为订阅的是公开地址）
                self._ws_client = HyperliquidWebSocketClient(
                    api_key=None,
                    api_secret=None,
                    is_demo=self.is_demo
                )
                
                # 连接
                success = await self._ws_client.connect()
                if success:
                    self._connected = True
                    logger.info("[Hyperliquid WS Manager] 启动成功")
                    return True
                else:
                    logger.error("[Hyperliquid WS Manager] 启动失败")
                    return False
                    
            except Exception as e:
                logger.error(f"[Hyperliquid WS Manager] 启动异常: {e}")
                self._connected = False
                return False
    
    async def stop(self) -> bool:
        """停止 WebSocket 连接"""
        async with self._lock:
            if not self._connected:
                return True
            
            try:
                if self._ws_client:
                    await self._ws_client.disconnect()
                    self._ws_client = None
                
                self._subscribed_addresses.clear()
                self._connected = False
                logger.info("[Hyperliquid WS Manager] 已停止")
                return True
                
            except Exception as e:
                logger.error(f"[Hyperliquid WS Manager] 停止异常: {e}")
                return False
    
    async def subscribe_address(self, address: str, callback: Callable) -> bool:
        """
        订阅地址的交易记录
        
        Args:
            address: Hyperliquid 钱包地址（0x开头）
            callback: 回调函数，接收标准化的交易数据
        
        Returns:
            是否订阅成功
        """
        async with self._lock:
            if not self._connected or not self._ws_client:
                logger.error("[Hyperliquid WS Manager] 未连接，无法订阅")
                return False
            
            try:
                # 创建包装回调，将原始数据标准化
                async def wrapped_callback(data: Dict):
                    try:
                        # 从 WebSocket 消息中提取交易数据
                        # 根据 Hyperliquid WebSocket API 的实际格式调整
                        fills = data.get('data', [])
                        if not fills:
                            fills = data if isinstance(data, list) else []
                        
                        for fill in fills:
                            # 标准化交易记录
                            normalized = self._collector.normalize_trade_record(fill)
                            if normalized:
                                # 调用用户回调
                                await callback(address, normalized)
                    except Exception as e:
                        logger.error(f"[Hyperliquid WS Manager] 处理交易数据失败: {e}")
                
                # 订阅
                success = await self._ws_client.subscribe_user_fills(address, wrapped_callback)
                if success:
                    self._subscribed_addresses[address] = callback
                    logger.info(f"[Hyperliquid WS Manager] 已订阅地址: {address}")
                else:
                    logger.error(f"[Hyperliquid WS Manager] 订阅地址失败: {address}")
                
                return success
                
            except Exception as e:
                logger.error(f"[Hyperliquid WS Manager] 订阅地址异常: {e}")
                return False
    
    async def unsubscribe_address(self, address: str) -> bool:
        """取消订阅地址"""
        async with self._lock:
            if not self._connected or not self._ws_client:
                return False
            
            try:
                success = await self._ws_client.unsubscribe_user_fills(address)
                if success:
                    self._subscribed_addresses.pop(address, None)
                    logger.info(f"[Hyperliquid WS Manager] 已取消订阅地址: {address}")
                return success
                
            except Exception as e:
                logger.error(f"[Hyperliquid WS Manager] 取消订阅异常: {e}")
                return False
    
    def is_connected(self) -> bool:
        """检查是否已连接"""
        return self._connected and self._ws_client and self._ws_client.is_connected()
    
    def get_subscribed_addresses(self) -> List[str]:
        """获取已订阅的地址列表"""
        return list(self._subscribed_addresses.keys())
    
    async def resubscribe_all(self):
        """重新订阅所有地址（用于重连后）"""
        async with self._lock:
            if not self._connected or not self._ws_client:
                return
            
            addresses = list(self._subscribed_addresses.keys())
            callbacks = dict(self._subscribed_addresses)
            
            # 清空当前订阅
            self._subscribed_addresses.clear()
            
            # 重新订阅
            for address, callback in callbacks.items():
                await self.subscribe_address(address, callback)
            
            logger.info(f"[Hyperliquid WS Manager] 已重新订阅 {len(addresses)} 个地址")

