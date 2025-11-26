#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Hyperliquid WebSocket客户端
用于实时监控账户变动和成交信息
"""

import json
import asyncio
import websockets
from typing import Dict, List, Optional, Any, Callable
from exchange.base_client import BaseWebSocketClient, ExchangeType, WebSocketStatus
from utils.logger import logger


class HyperliquidWebSocketClient(BaseWebSocketClient):
    """Hyperliquid WebSocket客户端"""
    
    def __init__(self, api_key: str = None, api_secret: str = None, passphrase: str = None, is_demo: bool = True):
        super().__init__(api_key, api_secret, passphrase, is_demo)
        
        # Hyperliquid WebSocket URL
        if is_demo:
            self.ws_url = "wss://api.hyperliquid-testnet.xyz/ws"
        else:
            self.ws_url = "wss://api.hyperliquid.xyz/ws"
        
        # WebSocket 连接对象
        self._ws = None
        self._receive_task = None
        self._heartbeat_task = None
        self._reconnect_attempts = 0
        self._max_reconnect_attempts = 10
        self._reconnect_interval = 5
        self._heartbeat_interval = 30
        
        # 订阅的地址和回调函数
        self._subscribed_addresses = {}  # {address: callback}
        self._message_callbacks = {}  # {channel: callback}
        
        # 连接状态
        self._should_reconnect = False
    
    def _get_exchange_type(self) -> ExchangeType:
        """获取交易所类型"""
        return ExchangeType.HYPERLIQUID
    
    async def connect(self) -> bool:
        """建立WebSocket连接"""
        try:
            if self.is_connected:
                logger.warning("[Hyperliquid WS] 已经连接，无需重复连接")
                return True
            
            await self._transition_to(WebSocketStatus.CONNECTING, "开始连接")
            
            logger.info(f"[Hyperliquid WS] 正在连接到 {self.ws_url}")
            self._ws = await websockets.connect(
                self.ws_url,
                ping_interval=None,  # 禁用自动ping，手动处理心跳
                close_timeout=10
            )
            
            await self._transition_to(WebSocketStatus.CONNECTED, "连接成功")
            self._reconnect_attempts = 0
            self._should_reconnect = True
            
            # 启动消息接收任务
            self._receive_task = asyncio.create_task(self._receive_messages())
            
            # 启动心跳任务
            self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())
            
            logger.info("[Hyperliquid WS] 连接成功")
            return True
            
        except Exception as e:
            logger.error(f"[Hyperliquid WS] 连接失败: {e}")
            await self._transition_to(WebSocketStatus.DISCONNECTED, f"连接失败: {e}")
            return False
    
    async def disconnect(self) -> bool:
        """断开WebSocket连接"""
        try:
            self._should_reconnect = False
            
            # 取消任务
            if self._receive_task:
                self._receive_task.cancel()
                try:
                    await self._receive_task
                except asyncio.CancelledError:
                    pass
            
            if self._heartbeat_task:
                self._heartbeat_task.cancel()
                try:
                    await self._heartbeat_task
                except asyncio.CancelledError:
                    pass
            
            # 关闭连接
            if self._ws:
                await self._ws.close()
                self._ws = None
            
            await self._transition_to(WebSocketStatus.DISCONNECTED, "主动断开")
            logger.info("[Hyperliquid WS] 已断开连接")
            return True
            
        except Exception as e:
            logger.error(f"[Hyperliquid WS] 断开连接失败: {e}")
            return False
    
    async def _receive_messages(self):
        """接收消息循环"""
        try:
            while self._should_reconnect and self._ws:
                try:
                    message = await self._ws.recv()
                    await self._handle_message(message)
                except websockets.exceptions.ConnectionClosed:
                    logger.warning("[Hyperliquid WS] 连接已关闭")
                    if self._should_reconnect:
                        await self._reconnect()
                    break
                except Exception as e:
                    logger.error(f"[Hyperliquid WS] 接收消息错误: {e}")
                    if self._should_reconnect:
                        await asyncio.sleep(1)
        except asyncio.CancelledError:
            logger.info("[Hyperliquid WS] 消息接收任务已取消")
        except Exception as e:
            logger.error(f"[Hyperliquid WS] 消息接收循环异常: {e}")
    
    async def _handle_message(self, message: str):
        """处理接收到的消息"""
        try:
            data = json.loads(message)
            
            # Hyperliquid WebSocket 消息格式可能不同，需要根据实际API文档调整
            # 这里假设消息格式为: {"channel": "userFills", "data": {...}}
            channel = data.get('channel') or data.get('type')
            
            if channel:
                callback = self._message_callbacks.get(channel)
                if callback:
                    await callback(data)
                else:
                    logger.debug(f"[Hyperliquid WS] 收到未订阅的消息: {channel}")
            else:
                # 如果没有channel字段，可能是直接的数据推送
                # 尝试所有回调
                for callback in self._message_callbacks.values():
                    try:
                        await callback(data)
                    except Exception as e:
                        logger.error(f"[Hyperliquid WS] 回调执行失败: {e}")
                        
        except json.JSONDecodeError as e:
            logger.error(f"[Hyperliquid WS] 消息解析失败: {e}, 消息: {message[:100]}")
        except Exception as e:
            logger.error(f"[Hyperliquid WS] 处理消息失败: {e}")
    
    async def _heartbeat_loop(self):
        """心跳循环"""
        try:
            while self._should_reconnect and self._ws:
                await asyncio.sleep(self._heartbeat_interval)
                if self._ws and not self._ws.closed:
                    try:
                        # Hyperliquid 可能需要发送ping消息，根据实际API调整
                        # await self._ws.ping()
                        pass
                    except Exception as e:
                        logger.warning(f"[Hyperliquid WS] 心跳失败: {e}")
        except asyncio.CancelledError:
            logger.info("[Hyperliquid WS] 心跳任务已取消")
    
    async def _reconnect(self):
        """重连逻辑"""
        if self._reconnect_attempts >= self._max_reconnect_attempts:
            logger.error(f"[Hyperliquid WS] 达到最大重连次数 {self._max_reconnect_attempts}，停止重连")
            self._should_reconnect = False
            return
        
        self._reconnect_attempts += 1
        logger.info(f"[Hyperliquid WS] 尝试重连 ({self._reconnect_attempts}/{self._max_reconnect_attempts})")
        
        await asyncio.sleep(self._reconnect_interval)
        
        # 重新连接
        if await self.connect():
            # 重新订阅所有地址
            for address, callback in self._subscribed_addresses.items():
                await self.subscribe_user_fills(address, callback)
    
    async def subscribe_user_fills(self, address: str, callback: Callable) -> bool:
        """
        订阅用户交易记录（userFills）
        
        Args:
            address: Hyperliquid 钱包地址（0x开头）
            callback: 回调函数，接收交易数据
        
        Returns:
            是否订阅成功
        """
        try:
            if not self.is_connected:
                logger.error("[Hyperliquid WS] 未连接，无法订阅")
                return False
            
            # 根据 Hyperliquid API 文档，订阅消息格式可能需要调整
            # 这里使用一个通用的订阅格式
            subscribe_msg = {
                "method": "subscribe",
                "subscription": {
                    "type": "userFills",
                    "user": address
                }
            }
            
            await self._ws.send(json.dumps(subscribe_msg))
            
            # 保存订阅信息
            self._subscribed_addresses[address] = callback
            self._message_callbacks[f"userFills_{address}"] = callback
            
            logger.info(f"[Hyperliquid WS] 已订阅地址 {address} 的交易记录")
            return True
            
        except Exception as e:
            logger.error(f"[Hyperliquid WS] 订阅失败: {e}")
            return False
    
    async def unsubscribe_user_fills(self, address: str) -> bool:
        """取消订阅用户交易记录"""
        try:
            if not self.is_connected:
                return False
            
            unsubscribe_msg = {
                "method": "unsubscribe",
                "subscription": {
                    "type": "userFills",
                    "user": address
                }
            }
            
            await self._ws.send(json.dumps(unsubscribe_msg))
            
            # 移除订阅信息
            self._subscribed_addresses.pop(address, None)
            self._message_callbacks.pop(f"userFills_{address}", None)
            
            logger.info(f"[Hyperliquid WS] 已取消订阅地址 {address}")
            return True
            
        except Exception as e:
            logger.error(f"[Hyperliquid WS] 取消订阅失败: {e}")
            return False
    
    # 实现基类的抽象方法（部分方法对于限价跟单场景不需要，提供默认实现）
    
    async def subscribe_ticker(self, symbol: str, callback) -> bool:
        """订阅行情数据（限价跟单不需要）"""
        logger.warning("[Hyperliquid WS] subscribe_ticker 未实现，限价跟单不需要")
        return False
    
    async def subscribe_orderbook(self, symbol: str, callback) -> bool:
        """订阅深度数据（限价跟单不需要）"""
        logger.warning("[Hyperliquid WS] subscribe_orderbook 未实现，限价跟单不需要")
        return False
    
    async def subscribe_trades(self, symbol: str, callback) -> bool:
        """订阅交易数据（限价跟单不需要）"""
        logger.warning("[Hyperliquid WS] subscribe_trades 未实现，限价跟单不需要")
        return False
    
    async def subscribe_orders(self, callback) -> bool:
        """订阅订单更新（限价跟单不需要）"""
        logger.warning("[Hyperliquid WS] subscribe_orders 未实现，限价跟单不需要")
        return False
    
    async def subscribe_positions(self, callback) -> bool:
        """订阅持仓更新（限价跟单不需要）"""
        logger.warning("[Hyperliquid WS] subscribe_positions 未实现，限价跟单不需要")
        return False
    
    async def subscribe_balance(self, callback) -> bool:
        """订阅余额更新（限价跟单不需要）"""
        logger.warning("[Hyperliquid WS] subscribe_balance 未实现，限价跟单不需要")
        return False
    
    async def unsubscribe(self, channel: str) -> bool:
        """取消订阅"""
        # 尝试从地址中提取
        if channel.startswith("userFills_"):
            address = channel.replace("userFills_", "")
            return await self.unsubscribe_user_fills(address)
        return False
    
    def is_connected(self) -> bool:
        """检查连接状态（重写基类方法，避免递归）"""
        return self._ws is not None and not self._ws.closed and self.status == WebSocketStatus.CONNECTED

