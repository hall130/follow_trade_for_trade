#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
币安REST API客户端
提供币安交易所的REST API接口
"""

import hmac
import hashlib
import json
import time
import aiohttp
from typing import Dict, Any, Optional, List
from urllib.parse import urlencode
from utils.logger import logger


class BinanceRESTClient:
    """币安REST API客户端"""
    
    # 鉴权类型常量
    AUTH_NONE = "NONE"           # 无需鉴权
    AUTH_TRADE = "TRADE"         # 交易权限
    AUTH_USER_DATA = "USER_DATA" # 用户数据权限
    AUTH_USER_STREAM = "USER_STREAM" # 用户流权限
    
    def __init__(self, api_key: str, api_secret: str, is_demo: bool = True):
        self.api_key = api_key
        self.api_secret = api_secret
        self.is_demo = is_demo
        
        # 根据是否为演示账户选择不同的URL
        if is_demo:
            self.base_url = "https://testnet.binance.vision"
            self.api_url = "https://testnet.binance.vision/api"
        else:
            self.base_url = "https://api.binance.com"
            self.api_url = "https://api.binance.com/api"
        
        # 默认recvWindow设置（5秒，适合大多数情况）
        self.default_recv_window = 5000
    
    def _get_timestamp(self) -> int:
        """获取当前时间戳（毫秒）"""
        return int(time.time() * 1000)
    
    def _sign(self, params: Dict[str, Any]) -> str:
        """生成签名"""
        # 将参数转换为查询字符串
        query_string = urlencode(params)
        
        # 使用HMAC SHA256生成签名
        signature = hmac.new(
            self.api_secret.encode('utf-8'),
            query_string.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
        
        return signature
    
    def _get_headers(self, auth_type: str = AUTH_NONE) -> Dict[str, str]:
        """获取请求头
        
        Args:
            auth_type: 鉴权类型 (NONE, TRADE, USER_DATA, USER_STREAM)
        """
        headers = {
            'Content-Type': 'application/json'
        }
        
        # 除了NONE类型，其他都需要API密钥
        if auth_type != self.AUTH_NONE:
            if not self.api_key:
                raise ValueError(f"鉴权类型 {auth_type} 需要API密钥")
            headers['X-MBX-APIKEY'] = self.api_key
        
        return headers
    
    async def _request(self, method: str, endpoint: str, params: Optional[Dict] = None, 
                       auth_type: str = AUTH_NONE, recv_window: Optional[int] = None) -> Dict[str, Any]:
        """发送HTTP请求
        
        Args:
            method: HTTP方法 (GET, POST, DELETE)
            endpoint: API端点
            params: 请求参数
            auth_type: 鉴权类型 (NONE, TRADE, USER_DATA, USER_STREAM)
            recv_window: 请求有效期（毫秒），默认5000ms，最大60000ms
        """
        url = f"{self.api_url}{endpoint}"
        
        if params is None:
            params = {}
        
        # 除了NONE类型，其他都需要添加时间戳和签名
        if auth_type != self.AUTH_NONE:
            # 添加时间戳（毫秒）
            params['timestamp'] = self._get_timestamp()
            
            # 添加recvWindow参数
            if recv_window is None:
                recv_window = self.default_recv_window
            else:
                # 验证recvWindow范围
                if recv_window < 1 or recv_window > 60000:
                    raise ValueError("recvWindow必须在1-60000毫秒之间")
            
            params['recvWindow'] = recv_window
            
            # 生成签名
            params['signature'] = self._sign(params)
        
        # 构建查询字符串
        query_string = urlencode(params)
        full_url = f"{url}?{query_string}"
        
        headers = self._get_headers(auth_type)
        
        logger.debug(f"发送请求: {method} {full_url}")
        
        try:
            async with aiohttp.ClientSession() as session:
                if method == 'GET':
                    async with session.get(full_url, headers=headers) as response:
                        result = await response.json()
                elif method == 'POST':
                    async with session.post(full_url, headers=headers) as response:
                        result = await response.json()
                elif method == 'DELETE':
                    async with session.delete(full_url, headers=headers) as response:
                        result = await response.json()
                else:
                    raise ValueError(f"不支持的HTTP方法: {method}")
                
                if response.status != 200:
                    logger.error(f"API请求失败: {response.status} - {result}")
                    raise Exception(f"API请求失败: {result}")
                
                return result
                
        except Exception as e:
            logger.error(f"请求异常: {e}")
            raise
    
    # 账户相关接口
    async def get_account_info(self) -> Dict[str, Any]:
        """获取账户信息 (USER_DATA)"""
        return await self._request('GET', '/v3/account', auth_type=self.AUTH_USER_DATA)
    
    async def get_balance(self) -> List[Dict[str, Any]]:
        """获取账户余额 (USER_DATA)"""
        account_info = await self.get_account_info()
        return account_info.get('balances', [])
    
    # 交易相关接口
    async def place_order(self, symbol: str, side: str, order_type: str, 
                         quantity: float, price: Optional[float] = None,
                         time_in_force: str = 'GTC', recv_window: Optional[int] = None) -> Dict[str, Any]:
        """
        下单 (TRADE)
        
        Args:
            symbol: 交易对
            side: 买卖方向 (BUY/SELL)
            order_type: 订单类型 (LIMIT/MARKET/STOP_LOSS_LIMIT)
            quantity: 数量
            price: 价格（市价单可为空）
            time_in_force: 有效期 (GTC/IOC/FOK)
            recv_window: 请求有效期（毫秒），默认5000ms
        """
        params = {
            'symbol': symbol,
            'side': side,
            'type': order_type,
            'quantity': quantity,
            'timeInForce': time_in_force
        }
        
        if price:
            params['price'] = price
        
        return await self._request('POST', '/v3/order', params, 
                                 auth_type=self.AUTH_TRADE, recv_window=recv_window)
    
    async def cancel_order(self, symbol: str, order_id: int, recv_window: Optional[int] = None) -> Dict[str, Any]:
        """取消订单 (TRADE)"""
        params = {
            'symbol': symbol,
            'orderId': order_id
        }
        return await self._request('DELETE', '/v3/order', params, 
                                 auth_type=self.AUTH_TRADE, recv_window=recv_window)
    
    async def get_order_status(self, symbol: str, order_id: int, recv_window: Optional[int] = None) -> Dict[str, Any]:
        """获取订单状态 (USER_DATA)"""
        params = {
            'symbol': symbol,
            'orderId': order_id
        }
        return await self._request('GET', '/v3/order', params, 
                                 auth_type=self.AUTH_USER_DATA, recv_window=recv_window)
    
    async def get_open_orders(self, symbol: Optional[str] = None, recv_window: Optional[int] = None) -> List[Dict[str, Any]]:
        """获取未成交订单 (USER_DATA)"""
        params = {}
        if symbol:
            params['symbol'] = symbol
        return await self._request('GET', '/v3/openOrders', params, 
                                 auth_type=self.AUTH_USER_DATA, recv_window=recv_window)
    
    # 市场数据接口
    async def get_ticker_price(self, symbol: Optional[str] = None) -> Dict[str, Any]:
        """获取价格信息 (NONE)"""
        endpoint = '/v3/ticker/price'
        if symbol:
            endpoint += f'?symbol={symbol}'
        return await self._request('GET', endpoint, auth_type=self.AUTH_NONE)
    
    async def get_klines(self, symbol: str, interval: str, 
                         start_time: Optional[int] = None, 
                         end_time: Optional[int] = None,
                         limit: int = 500) -> List[List]:
        """
        获取K线数据 (NONE)
        
        Args:
            symbol: 交易对
            interval: 时间间隔 (1m, 3m, 5m, 15m, 30m, 5m, 15m, 30m, 1h, 2h, 4h, 6h, 8h, 12h, 1d, 3d, 1w, 1M)
            start_time: 开始时间（毫秒时间戳）
            end_time: 结束时间（毫秒时间戳）
            limit: 返回数量限制
        """
        params = {
            'symbol': symbol,
            'interval': interval,
            'limit': limit
        }
        
        if start_time:
            params['startTime'] = start_time
        if end_time:
            params['endTime'] = end_time
        
        return await self._request('GET', '/v3/klines', params, auth_type=self.AUTH_NONE)
    
    async def get_exchange_info(self) -> Dict[str, Any]:
        """获取交易所信息 (NONE)"""
        return await self._request('GET', '/v3/exchangeInfo', auth_type=self.AUTH_NONE)
    
    # 持仓相关接口
    async def get_position_info(self, symbol: Optional[str] = None) -> List[Dict[str, Any]]:
        """获取持仓信息（仅适用于合约交易）"""
        # 注意：现货交易没有持仓概念，这里返回空列表
        # 如果需要合约交易，需要实现合约相关的API
        logger.warning("现货交易不支持持仓查询，返回空列表")
        return []
    
    # 用户数据流管理 (USER_STREAM)
    async def create_listen_key(self) -> str:
        """创建listenKey用于用户数据流订阅 (USER_STREAM)"""
        result = await self._request('POST', '/v3/userDataStream', auth_type=self.AUTH_USER_STREAM)
        return result.get('listenKey', '')
    
    async def extend_listen_key(self, listen_key: str) -> Dict[str, Any]:
        """延长listenKey有效期 (USER_STREAM)"""
        params = {'listenKey': listen_key}
        return await self._request('PUT', '/v3/userDataStream', params, auth_type=self.AUTH_USER_STREAM)
    
    async def close_listen_key(self, listen_key: str) -> Dict[str, Any]:
        """关闭listenKey (USER_STREAM)"""
        params = {'listen_key': listen_key}
        return await self._request('DELETE', '/v3/userDataStream', params, auth_type=self.AUTH_USER_STREAM)
    
    # 交易历史 (USER_DATA)
    async def get_trade_history(self, symbol: str, limit: int = 500, 
                               from_id: Optional[int] = None, recv_window: Optional[int] = None) -> List[Dict[str, Any]]:
        """获取交易历史 (USER_DATA)"""
        params = {
            'symbol': symbol,
            'limit': limit
        }
        if from_id:
            params['fromId'] = from_id
        
        return await self._request('GET', '/v3/myTrades', params, 
                                 auth_type=self.AUTH_USER_DATA, recv_window=recv_window)
    
    # 账户交易统计 (USER_DATA)
    async def get_account_trades(self, symbol: Optional[str] = None, 
                                order_id: Optional[int] = None, recv_window: Optional[int] = None) -> List[Dict[str, Any]]:
        """获取账户交易统计 (USER_DATA)"""
        params = {}
        if symbol:
            params['symbol'] = symbol
        if order_id:
            params['orderId'] = order_id
        
        return await self._request('GET', '/v3/myTrades', params, 
                                 auth_type=self.AUTH_USER_DATA, recv_window=recv_window)
    
    # 工具方法
    def calculate_order_size(self, symbol: str, quantity: float, price: float) -> float:
        """计算订单价值"""
        return quantity * price
    
    def format_quantity(self, symbol: str, quantity: float) -> float:
        """格式化数量（根据交易对精度要求）"""
        # 这里可以根据不同交易对的精度要求进行格式化
        # 暂时返回原值
        return quantity
    
    def validate_auth_requirements(self, auth_type: str) -> bool:
        """验证鉴权要求
        
        Args:
            auth_type: 鉴权类型
            
        Returns:
            是否满足鉴权要求
        """
        if auth_type == self.AUTH_NONE:
            return True
        
        if not self.api_key or not self.api_secret:
            logger.error(f"鉴权类型 {auth_type} 需要API密钥和密钥")
            return False
        
        return True
    
    def get_auth_info(self) -> Dict[str, Any]:
        """获取鉴权信息"""
        return {
            'has_api_key': bool(self.api_key),
            'has_api_secret': bool(self.api_secret),
            'is_demo': self.is_demo,
            'supported_auth_types': [
                self.AUTH_NONE,
                self.AUTH_TRADE if self.api_key else None,
                self.AUTH_USER_DATA if self.api_key else None,
                self.AUTH_USER_STREAM if self.api_key else None
            ]
        } 