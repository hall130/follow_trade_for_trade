#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Bybit WebSocket客户端
用于实时数据订阅
"""

import asyncio
import json
import time
import websockets
from typing import Dict, Any, Optional, List, Callable
from utils.logger import logger
from ..base_client import BaseWebSocketClient, ExchangeType
from ..websocket_state_machine import WebSocketStatus, WebSocketStateMachine


class BybitWebSocketClient(BaseWebSocketClient):
    """Bybit WebSocket客户端"""
    
    def __init__(self, api_key: str = None, api_secret: str = None, 
                 passphrase: str = None, is_demo: bool = True):
        super().__init__(api_key, api_secret, passphrase, is_demo)
        
        # 根据是否为演示账户选择不同的URL
        if is_demo:
            self.ws_url = "wss://stream-testnet.bybit.com/v5/public/linear"
            self.private_ws_url = "wss://stream-testnet.bybit.com/v5/private"
        else:
            self.ws_url = "wss://stream.bybit.com/v5/public/linear"
            self.private_ws_url = "wss://stream.bybit.com/v5/private"
        
        self._websocket = None
        self._private_websocket = None
        self._connected = False
        self._private_connected = False
    
    def _get_exchange_type(self) -> ExchangeType:
        """获取交易所类型"""
        return ExchangeType.BYBIT
    
    async def connect(self) -> bool:
        """连接WebSocket"""
        try:
            if not self._connected:
                self._websocket = await websockets.connect(self.ws_url, proxy=self.proxy)
                self._connected = True
                logger.info("Bybit公共WebSocket连接成功")

            if self.api_key and not self._private_connected:
                self._private_websocket = await websockets.connect(self.private_ws_url, proxy=self.proxy)
                self._private_connected = True
                logger.info("Bybit私有WebSocket连接成功")
            
            return True
            
        except Exception as e:
            logger.error(f"Bybit WebSocket连接失败: {e}")
            return False
    
    async def disconnect(self):
        """断开WebSocket连接"""
        try:
            if self._websocket:
                await self._websocket.close()
                self._connected = False
                logger.info("Bybit公共WebSocket连接已断开")
            
            if self._private_websocket:
                await self._private_websocket.close()
                self._private_connected = False
                logger.info("Bybit私有WebSocket连接已断开")
                
        except Exception as e:
            logger.error(f"断开Bybit WebSocket连接失败: {e}")
    
    async def subscribe_ticker(self, symbol: str, callback: Callable):
        """订阅行情数据"""
        try:
            if not self._connected:
                await self.connect()
            
            subscription = {
                "op": "subscribe",
                "args": [f"tickers.{symbol}"]
            }
            
            await self._websocket.send(json.dumps(subscription))
            self._subscriptions[f"ticker_{symbol}"] = callback
            logger.info(f"已订阅Bybit行情数据: {symbol}")
            
        except Exception as e:
            logger.error(f"订阅Bybit行情数据失败: {e}")
    
    async def subscribe_orderbook(self, symbol: str, callback: Callable):
        """订阅订单簿数据"""
        try:
            if not self._connected:
                await self.connect()
            
            subscription = {
                "op": "subscribe",
                "args": [f"orderbook.1.{symbol}"]
            }
            
            await self._websocket.send(json.dumps(subscription))
            self._subscriptions[f"orderbook_{symbol}"] = callback
            logger.info(f"已订阅Bybit订单簿数据: {symbol}")
            
        except Exception as e:
            logger.error(f"订阅Bybit订单簿数据失败: {e}")
    
    async def subscribe_trades(self, symbol: str, callback: Callable):
        """订阅交易数据"""
        try:
            if not self._connected:
                await self.connect()
            
            subscription = {
                "op": "subscribe",
                "args": [f"publicTrade.{symbol}"]
            }
            
            await self._websocket.send(json.dumps(subscription))
            self._subscriptions[f"trades_{symbol}"] = callback
            logger.info(f"已订阅Bybit交易数据: {symbol}")
            
        except Exception as e:
            logger.error(f"订阅Bybit交易数据失败: {e}")
    
    async def subscribe_positions(self, callback: Callable):
        """订阅持仓数据"""
        try:
            if not self._private_connected:
                await self.connect()
            
            subscription = {
                "op": "subscribe",
                "args": ["position"]
            }
            
            await self._private_websocket.send(json.dumps(subscription))
            self._subscriptions["positions"] = callback
            logger.info("已订阅Bybit持仓数据")
            
        except Exception as e:
            logger.error(f"订阅Bybit持仓数据失败: {e}")
    
    async def subscribe_orders(self, callback: Callable):
        """订阅订单数据"""
        try:
            if not self._private_connected:
                await self.connect()
            
            subscription = {
                "op": "subscribe",
                "args": ["order"]
            }
            
            await self._private_websocket.send(json.dumps(subscription))
            self._subscriptions["orders"] = callback
            logger.info("已订阅Bybit订单数据")
            
        except Exception as e:
            logger.error(f"订阅Bybit订单数据失败: {e}")
    
    async def start_listening(self):
        """开始监听消息"""
        try:
            # 监听公共频道
            if self._connected and self._websocket:
                asyncio.create_task(self._listen_public())
            
            # 监听私有频道
            if self._private_connected and self._private_websocket:
                asyncio.create_task(self._listen_private())
                
        except Exception as e:
            logger.error(f"开始监听Bybit消息失败: {e}")
    
    async def _listen_public(self):
        """监听公共频道消息"""
        try:
            async for message in self._websocket:
                data = json.loads(message)
                await self._handle_public_message(data)
                
        except Exception as e:
            logger.error(f"监听Bybit公共频道消息失败: {e}")
    
    async def _listen_private(self):
        """监听私有频道消息"""
        try:
            async for message in self._private_websocket:
                data = json.loads(message)
                await self._handle_private_message(data)
                
        except Exception as e:
            logger.error(f"监听Bybit私有频道消息失败: {e}")
    
    async def _handle_public_message(self, data: Dict[str, Any]):
        """处理公共频道消息"""
        try:
            if 'topic' in data:
                topic = data['topic']
                
                if 'tickers' in topic:
                    symbol = topic.split('.')[-1]
                    callback = self._subscriptions.get(f"ticker_{symbol}")
                    if callback:
                        await callback(data)
                
                elif 'orderbook' in topic:
                    symbol = topic.split('.')[-1]
                    callback = self._subscriptions.get(f"orderbook_{symbol}")
                    if callback:
                        await callback(data)
                
                elif 'publicTrade' in topic:
                    symbol = topic.split('.')[-1]
                    callback = self._subscriptions.get(f"trades_{symbol}")
                    if callback:
                        await callback(data)
                        
        except Exception as e:
            logger.error(f"处理Bybit公共频道消息失败: {e}")
    
    async def _handle_private_message(self, data: Dict[str, Any]):
        """处理私有频道消息"""
        try:
            if 'topic' in data:
                topic = data['topic']
                
                if topic == 'position':
                    callback = self._subscriptions.get('positions')
                    if callback:
                        await callback(data)
                
                elif topic == 'order':
                    callback = self._subscriptions.get('orders')
                    if callback:
                        await callback(data)
                        
        except Exception as e:
            logger.error(f"处理Bybit私有频道消息失败: {e}")
    
    def is_connected(self) -> bool:
        """检查连接状态"""
        return self._connected or self._private_connected
    
    def get_connection_status(self) -> Dict[str, bool]:
        """获取连接状态详情"""
        return {
            'public_connected': self._connected,
            'private_connected': self._private_connected,
            'overall_connected': self.is_connected()
        }
    
    async def subscribe_balance(self, callback: Callable):
        """订阅余额数据"""
        try:
            if not self._private_connected:
                logger.warning("私有WebSocket未连接，无法订阅余额数据")
                return False
            
            # 这里应该实现具体的订阅逻辑
            logger.info("订阅Bybit余额数据")
            return True
        except Exception as e:
            logger.error(f"订阅Bybit余额数据失败: {e}")
            return False
    
    async def unsubscribe(self, channel: str) -> bool:
        """取消订阅"""
        try:
            # 这里应该实现具体的取消订阅逻辑
            logger.info(f"取消订阅Bybit频道: {channel}")
            return True
        except Exception as e:
            logger.error(f"取消订阅Bybit频道失败: {e}")
            return False
