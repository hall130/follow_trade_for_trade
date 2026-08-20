#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
币安WebSocket客户端
提供币安交易所的WebSocket接口
"""

import asyncio
import json
import time
import hmac
import hashlib
from typing import Dict, Any, Optional, Callable, List
from urllib.parse import urlencode
import aiohttp
import websockets
from utils.logger import logger
from ..base_client import BaseWebSocketClient, ExchangeType
from ..websocket_state_machine import WebSocketStatus, WebSocketStateMachine


class BinanceWebSocketClient(BaseWebSocketClient):
    """币安WebSocket客户端"""
    
    def __init__(self, api_key: str = None, api_secret: str = None, is_demo: bool = True):
        # 调用父类构造函数
        super().__init__(api_key, api_secret, None, is_demo)
        
        # 基本配置
        self.api_key = api_key
        self.api_secret = api_secret
        self.is_demo = is_demo
        
        # 根据是否为演示账户选择不同的URL
        if is_demo:
            self.ws_base_url = "wss://testnet.binance.vision/ws"
            self.ws_stream_url = "wss://testnet.binance.vision/stream"
        else:
            self.ws_base_url = "wss://stream.binance.com:9443/ws"
            self.ws_stream_url = "wss://stream.binance.com:9443/stream"
        
        self.connections = {}  # 存储不同的WebSocket连接
        self.callbacks = {}    # 存储回调函数
        self.running = False
        self.reconnect_delay = 5
        self.max_reconnect_attempts = 5
        
        # 会话身份验证相关
        self.authenticated_sessions = {}  # {connection_id: {'api_key': str, 'timestamp': int}}
        self.session_requests = {}        # 存储会话请求的响应
    
    def _get_exchange_type(self) -> ExchangeType:
        """获取交易所类型"""
        return ExchangeType.BINANCE
        
    def _get_timestamp(self) -> int:
        """获取当前时间戳（毫秒）"""
        return int(time.time() * 1000)
    
    def _sign(self, params: Dict[str, Any]) -> str:
        """生成签名"""
        if not self.api_secret:
            return ""
        
        # 将参数转换为查询字符串
        query_string = urlencode(params)
        
        # 使用HMAC SHA256生成签名
        signature = hmac.new(
            self.api_secret.encode('utf-8'),
            query_string.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
        
        return signature
    
    async def _create_connection(self, stream_name: str, is_private: bool = False) -> websockets.WebSocketServerProtocol:
        """创建WebSocket连接"""
        try:
            if is_private and self.api_key and self.api_secret:
                # 私有流需要认证
                timestamp = self._get_timestamp()
                params = {
                    'timestamp': timestamp
                }
                signature = self._sign(params)
                
                auth_url = f"{self.ws_base_url}/{stream_name}?{urlencode(params)}&signature={signature}"
                headers = {'X-MBX-APIKEY': self.api_key}
            else:
                # 公共流
                auth_url = f"{self.ws_base_url}/{stream_name}"
                headers = {}
            
            logger.info(f"连接币安WebSocket: {auth_url}")
            # 注：websockets 14+ 将 extra_headers 重命名为 additional_headers
            websocket = await websockets.connect(auth_url, additional_headers=headers, proxy=self.proxy)
            logger.info(f"币安WebSocket连接成功: {stream_name}")
            return websocket
            
        except Exception as e:
            logger.error(f"币安WebSocket连接失败 {stream_name}: {e}")
            raise
    
    async def _handle_message(self, websocket: websockets.WebSocketServerProtocol, stream_name: str):
        """处理WebSocket消息"""
        try:
            async for message in websocket:
                try:
                    data = json.loads(message)
                    logger.debug(f"收到币安WebSocket消息: {stream_name} - {data}")
                    
                    # 处理会话身份验证响应
                    if 'id' in data and data['id']:
                        request_id = data['id']
                        if request_id.startswith(('auth_', 'status_', 'logout_')):
                            self.session_requests[request_id] = data
                            continue
                    
                    # 调用对应的回调函数
                    if stream_name in self.callbacks:
                        for callback in self.callbacks[stream_name]:
                            try:
                                await callback(data)
                            except Exception as e:
                                logger.error(f"回调函数执行失败: {e}")
                    
                except json.JSONDecodeError as e:
                    logger.error(f"JSON解析失败: {e} - {message}")
                except Exception as e:
                    logger.error(f"处理消息失败: {e}")
                    
        except websockets.exceptions.ConnectionClosed:
            logger.warning(f"币安WebSocket连接已关闭: {stream_name}")
        except Exception as e:
            logger.error(f"WebSocket消息处理异常: {e}")
    
    async def subscribe_ticker(self, symbol: str, callback: Callable):
        """订阅价格行情"""
        stream_name = f"{symbol.lower()}@ticker"
        
        if stream_name not in self.connections:
            websocket = await self._create_connection(stream_name)
            self.connections[stream_name] = websocket
            
            # 启动消息处理
            asyncio.create_task(self._handle_message(websocket, stream_name))
        
        if stream_name not in self.callbacks:
            self.callbacks[stream_name] = []
        self.callbacks[stream_name].append(callback)
        
        logger.info(f"已订阅币安价格行情: {symbol}")
    
    async def subscribe_kline(self, symbol: str, interval: str, callback: Callable):
        """订阅K线数据"""
        stream_name = f"{symbol.lower()}@kline_{interval}"
        
        if stream_name not in self.connections:
            websocket = await self._create_connection(stream_name)
            self.connections[stream_name] = websocket
            
            # 启动消息处理
            asyncio.create_task(self._handle_message(websocket, stream_name))
        
        if stream_name not in self.callbacks:
            self.callbacks[stream_name] = []
        self.callbacks[stream_name].append(callback)
        
        logger.info(f"已订阅币安K线数据: {symbol} {interval}")
    
    async def subscribe_trade(self, symbol: str, callback: Callable):
        """订阅交易数据"""
        stream_name = f"{symbol.lower()}@trade"
        
        if stream_name not in self.connections:
            websocket = await self._create_connection(stream_name)
            self.connections[stream_name] = websocket
            
            # 启动消息处理
            asyncio.create_task(self._handle_message(websocket, stream_name))
        
        if stream_name not in self.callbacks:
            self.callbacks[stream_name] = []
        self.callbacks[stream_name].append(callback)
        
        logger.info(f"已订阅币安交易数据: {symbol}")
    
    async def subscribe_depth(self, symbol: str, callback: Callable):
        """订阅深度数据"""
        stream_name = f"{symbol.lower()}@depth"
        
        if stream_name not in self.connections:
            websocket = await self._create_connection(stream_name)
            self.connections[stream_name] = websocket
            
            # 启动消息处理
            asyncio.create_task(self._handle_message(websocket, stream_name))
        
        if stream_name not in self.callbacks:
            self.callbacks[stream_name] = []
        self.callbacks[stream_name].append(callback)
        
        logger.info(f"已订阅币安深度数据: {symbol}")
    
    async def subscribe_user_data(self, listen_key: str, callback: Callable):
        """订阅用户数据流 (USER_STREAM)
        
        Args:
            listen_key: 从REST API获取的listenKey
            callback: 回调函数
        """
        if not listen_key:
            logger.error("订阅用户数据需要有效的listenKey")
            return
        
        stream_name = f"{listen_key}"
        
        if stream_name not in self.connections:
            websocket = await self._create_connection(stream_name, is_private=False)
            self.connections[stream_name] = websocket
            
            # 启动消息处理
            asyncio.create_task(self._handle_message(websocket, stream_name))
        
        if stream_name not in self.callbacks:
            self.callbacks[stream_name] = []
        self.callbacks[stream_name].append(callback)
        
        logger.info(f"已订阅币安用户数据流: {listen_key[:10]}...")
    
    async def subscribe_user_data_with_rest_client(self, rest_client, callback: Callable):
        """使用REST客户端自动管理listenKey并订阅用户数据
        
        Args:
            rest_client: 币安REST客户端实例
            callback: 回调函数
        """
        try:
            # 创建listenKey
            listen_key = await rest_client.create_listen_key()
            if not listen_key:
                logger.error("创建listenKey失败")
                return
            
            # 订阅用户数据流
            await self.subscribe_user_data(listen_key, callback)
            
            # 启动定时延长listenKey的任务
            asyncio.create_task(self._extend_listen_key_periodically(rest_client, listen_key))
            
            return listen_key
            
        except Exception as e:
            logger.error(f"订阅用户数据流失败: {e}")
            return None
    
    async def _extend_listen_key_periodically(self, rest_client, listen_key: str):
        """定期延长listenKey有效期（每30分钟）"""
        while True:
            try:
                await asyncio.sleep(30 * 60)  # 30分钟
                await rest_client.extend_listen_key(listen_key)
                logger.debug(f"已延长listenKey: {listen_key[:10]}...")
            except Exception as e:
                logger.error(f"延长listenKey失败: {e}")
                break
    
    # 会话身份验证方法
    async def session_logon(self, connection_id: str, api_key: str, api_secret: str) -> bool:
        """进行会话身份验证 (USER_STREAM)
        
        Args:
            connection_id: 连接ID
            api_key: API密钥
            api_secret: API密钥
            
        Returns:
            是否认证成功
        """
        try:
            # 生成签名
            timestamp = self._get_timestamp()
            params = {
                'apiKey': api_key,
                'timestamp': timestamp
            }
            signature = self._sign(params)
            
            # 构建认证请求
            auth_request = {
                'id': f'auth_{int(time.time() * 1000)}',
                'method': 'session.logon',
                'params': {
                    'apiKey': api_key,
                    'signature': signature,
                    'timestamp': timestamp
                }
            }
            
            # 发送认证请求
            if connection_id in self.connections:
                websocket = self.connections[connection_id]
                await websocket.send(json.dumps(auth_request))
                
                # 等待响应
                response = await self._wait_for_response(auth_request['id'], timeout=10)
                
                if response and response.get('status') == 200:
                    # 认证成功，记录会话信息
                    self.authenticated_sessions[connection_id] = {
                        'api_key': api_key,
                        'timestamp': timestamp
                    }
                    logger.info(f"会话身份验证成功: {connection_id}")
                    return True
                else:
                    logger.error(f"会话身份验证失败: {response}")
                    return False
            else:
                logger.error(f"连接不存在: {connection_id}")
                return False
                
        except Exception as e:
            logger.error(f"会话身份验证异常: {e}")
            return False
    
    async def session_status(self, connection_id: str) -> Dict[str, Any]:
        """检查会话状态 (USER_STREAM)
        
        Args:
            connection_id: 连接ID
            
        Returns:
            会话状态信息
        """
        try:
            request = {
                'id': f'status_{int(time.time() * 1000)}',
                'method': 'session.status',
                'params': {}
            }
            
            if connection_id in self.connections:
                websocket = self.connections[connection_id]
                await websocket.send(json.dumps(request))
                
                # 等待响应
                response = await self._wait_for_response(request['id'], timeout=10)
                return response or {}
            else:
                logger.error(f"连接不存在: {connection_id}")
                return {}
                
        except Exception as e:
            logger.error(f"检查会话状态异常: {e}")
            return {}
    
    async def session_logout(self, connection_id: str) -> bool:
        """登出会话 (USER_STREAM)
        
        Args:
            connection_id: 连接ID
            
        Returns:
            是否登出成功
        """
        try:
            request = {
                'id': f'logout_{int(time.time() * 1000)}',
                'method': 'session.logout',
                'params': {}
            }
            
            if connection_id in self.connections:
                websocket = self.connections[connection_id]
                await websocket.send(json.dumps(request))
                
                # 等待响应
                response = await self._wait_for_response(request['id'], timeout=10)
                
                if response and response.get('status') == 200:
                    # 登出成功，清除会话信息
                    if connection_id in self.authenticated_sessions:
                        del self.authenticated_sessions[connection_id]
                    logger.info(f"会话登出成功: {connection_id}")
                    return True
                else:
                    logger.error(f"会话登出失败: {response}")
                    return False
            else:
                logger.error(f"连接不存在: {connection_id}")
                return False
                
        except Exception as e:
            logger.error(f"会话登出异常: {e}")
            return False
    
    async def _wait_for_response(self, request_id: str, timeout: int = 10) -> Optional[Dict[str, Any]]:
        """等待特定请求的响应
        
        Args:
            request_id: 请求ID
            timeout: 超时时间（秒）
            
        Returns:
            响应数据或None
        """
        start_time = time.time()
        while time.time() - start_time < timeout:
            if request_id in self.session_requests:
                response = self.session_requests[request_id]
                del self.session_requests[request_id]
                return response
            await asyncio.sleep(0.1)
        
        logger.warning(f"等待响应超时: {request_id}")
        return None
    
    def is_session_authenticated(self, connection_id: str) -> bool:
        """检查会话是否已认证
        
        Args:
            connection_id: 连接ID
            
        Returns:
            是否已认证
        """
        return connection_id in self.authenticated_sessions
    
    def get_session_api_key(self, connection_id: str) -> Optional[str]:
        """获取会话的API密钥
        
        Args:
            connection_id: 连接ID
            
        Returns:
            API密钥或None
        """
        if connection_id in self.authenticated_sessions:
            return self.authenticated_sessions[connection_id]['api_key']
        return None
    
    async def subscribe_multiple_streams(self, streams: List[str], callback: Callable):
        """订阅多个流（使用组合流）"""
        # 币安支持组合流，多个流用/分隔
        combined_stream = "/".join(streams)
        stream_name = f"!stream={combined_stream}"
        
        if stream_name not in self.connections:
            websocket = await self._create_connection(stream_name)
            self.connections[stream_name] = websocket
            
            # 启动消息处理
            asyncio.create_task(self._handle_message(websocket, stream_name))
        
        if stream_name not in self.callbacks:
            self.callbacks[stream_name] = []
        self.callbacks[stream_name].append(callback)
        
        logger.info(f"已订阅币安组合流: {combined_stream}")
    
    async def unsubscribe(self, stream_name: str):
        """取消订阅"""
        if stream_name in self.connections:
            websocket = self.connections[stream_name]
            await websocket.close()
            del self.connections[stream_name]
            
        if stream_name in self.callbacks:
            del self.callbacks[stream_name]
            
        logger.info(f"已取消订阅币安流: {stream_name}")
    
    async def ping(self, stream_name: str):
        """发送ping消息保持连接"""
        if stream_name in self.connections:
            websocket = self.connections[stream_name]
            try:
                await websocket.ping()
                logger.debug(f"币安WebSocket ping成功: {stream_name}")
            except Exception as e:
                logger.error(f"币安WebSocket ping失败: {stream_name} - {e}")
    
    async def close_all(self):
        """关闭所有连接"""
        for stream_name, websocket in self.connections.items():
            try:
                await websocket.close()
                logger.info(f"已关闭币安WebSocket连接: {stream_name}")
            except Exception as e:
                logger.error(f"关闭币安WebSocket连接失败: {stream_name} - {e}")
        
        self.connections.clear()
        self.callbacks.clear()
        logger.info("所有币安WebSocket连接已关闭")
    
    async def get_status(self) -> Dict[str, Any]:
        """获取连接状态"""
        return {
            "running": self.running,
            "connections_count": len(self.connections),
            "active_streams": list(self.connections.keys()),
            "callbacks_count": {k: len(v) for k, v in self.callbacks.items()},
            "authenticated_sessions": len(self.authenticated_sessions),
            "session_requests": len(self.session_requests)
        }
    
    async def send_signed_request(self, connection_id: str, method: str, params: Dict[str, Any], 
                                 api_key: str = None, api_secret: str = None, 
                                 recv_window: int = 5000) -> Optional[Dict[str, Any]]:
        """发送需要签名的请求（支持临时授权）
        
        Args:
            connection_id: 连接ID
            method: 请求方法
            params: 请求参数
            api_key: 临时API密钥（如果为None，使用会话密钥）
            api_secret: 临时API密钥（如果为None，使用会话密钥）
            recv_window: 请求有效期（毫秒）
            
        Returns:
            响应数据或None
        """
        try:
            # 如果没有提供临时密钥，使用会话密钥
            if not api_key or not api_secret:
                if connection_id not in self.authenticated_sessions:
                    logger.error("会话未认证，无法发送签名请求")
                    return None
                
                api_key = self.authenticated_sessions[connection_id]['api_key']
                # 注意：会话认证后，不需要在请求中提供api_secret
                api_secret = None
            
            # 添加时间戳和recvWindow
            params['timestamp'] = self._get_timestamp()
            params['recvWindow'] = recv_window
            
            # 如果提供了临时密钥，需要生成签名
            if api_secret:
                params['apiKey'] = api_key
                params['signature'] = self._sign(params)
            else:
                # 会话认证后，只需要apiKey
                params['apiKey'] = api_key
            
            # 构建请求
            request = {
                'id': f'request_{int(time.time() * 1000)}',
                'method': method,
                'params': params
            }
            
            # 发送请求
            if connection_id in self.connections:
                websocket = self.connections[connection_id]
                await websocket.send(json.dumps(request))
                
                # 等待响应
                response = await self._wait_for_response(request['id'], timeout=10)
                return response
            else:
                logger.error(f"连接不存在: {connection_id}")
                return None
                
        except Exception as e:
            logger.error(f"发送签名请求异常: {e}")
            return None
    
    def get_authenticated_sessions(self) -> Dict[str, Dict[str, Any]]:
        """获取所有已认证的会话信息"""
        return self.authenticated_sessions.copy()
    
    def clear_authenticated_sessions(self):
        """清除所有会话认证信息"""
        self.authenticated_sessions.clear()
        logger.info("已清除所有会话认证信息")


# 全局客户端管理器
_global_binance_ws_clients = {}

async def get_binance_ws_client(client_key: str, api_key: str = None, 
                               api_secret: str = None, is_demo: bool = True) -> BinanceWebSocketClient:
    """获取全局币安WebSocket客户端"""
    if client_key not in _global_binance_ws_clients:
        client = BinanceWebSocketClient(api_key, api_secret, is_demo)
        _global_binance_ws_clients[client_key] = client
    
    return _global_binance_ws_clients[client_key]

def get_global_binance_client_manager():
    """获取全局币安客户端管理器"""
    return _global_binance_ws_clients

    # 实现BaseWebSocketClient的抽象方法
    async def disconnect(self) -> bool:
        """断开WebSocket连接"""
        try:
            self.running = False
            for connection in self.connections.values():
                if connection:
                    await connection.close()
            self.connections.clear()
            await self._transition_to(WebSocketStatus.DISCONNECTED, "主动断开连接")
            return True
        except Exception as e:
            logger.error(f"断开连接失败: {e}")
            return False
    
    async def subscribe_ticker(self, symbol: str, callback) -> bool:
        """订阅行情数据"""
        try:
            # 这里应该实现具体的订阅逻辑
            logger.info(f"订阅行情数据: {symbol}")
            return True
        except Exception as e:
            logger.error(f"订阅行情数据失败: {e}")
            return False
    
    async def subscribe_orderbook(self, symbol: str, callback) -> bool:
        """订阅深度数据"""
        try:
            # 这里应该实现具体的订阅逻辑
            logger.info(f"订阅深度数据: {symbol}")
            return True
        except Exception as e:
            logger.error(f"订阅深度数据失败: {e}")
            return False
    
    async def subscribe_trades(self, symbol: str, callback) -> bool:
        """订阅交易数据"""
        try:
            # 这里应该实现具体的订阅逻辑
            logger.info(f"订阅交易数据: {symbol}")
            return True
        except Exception as e:
            logger.error(f"订阅交易数据失败: {e}")
            return False
    
    async def subscribe_orders(self, callback) -> bool:
        """订阅订单更新"""
        try:
            # 这里应该实现具体的订阅逻辑
            logger.info("订阅订单更新")
            return True
        except Exception as e:
            logger.error(f"订阅订单更新失败: {e}")
            return False
    
    async def subscribe_positions(self, callback) -> bool:
        """订阅持仓更新"""
        try:
            # 这里应该实现具体的订阅逻辑
            logger.info("订阅持仓更新")
            return True
        except Exception as e:
            logger.error(f"订阅持仓更新失败: {e}")
            return False
    
    async def subscribe_balance(self, callback) -> bool:
        """订阅余额更新"""
        try:
            # 这里应该实现具体的订阅逻辑
            logger.info("订阅余额更新")
            return True
        except Exception as e:
            logger.error(f"订阅余额更新失败: {e}")
            return False
    
    async def unsubscribe(self, channel: str) -> bool:
        """取消订阅"""
        try:
            # 这里应该实现具体的取消订阅逻辑
            logger.info(f"取消订阅: {channel}")
            return True
        except Exception as e:
            logger.error(f"取消订阅失败: {e}")
            return False
    
    def is_connected(self) -> bool:
        """检查连接状态"""
        return self._state_machine.is_connected() 