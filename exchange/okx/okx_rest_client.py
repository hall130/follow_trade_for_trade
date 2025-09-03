#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
OKX REST API客户端
用于真实的下单、查询等操作
"""

import aiohttp
import asyncio
import hmac
import hashlib
import base64
import json
import time
from typing import Dict, Any, Optional
from utils.logger import logger


class OKXRESTClient:
    """OKX REST API客户端"""
    
    def __init__(self, api_key: str, api_secret: str, passphrase: str, is_demo: bool = True):
        self.api_key = api_key
        self.api_secret = api_secret
        self.passphrase = passphrase
        self.is_demo = is_demo
        
        # 根据是否为演示账户选择不同的URL
        if is_demo:
            self.base_url = "https://www.okx.com"
            self.api_url = "https://www.okx.com/api/v5"
        else:
            self.base_url = "https://www.okx.com"
            self.api_url = "https://www.okx.com/api/v5"
    
    def _get_timestamp(self) -> str:
        """获取ISO 8601格式的时间戳"""
        from datetime import datetime
        # OKX API要求的时间戳格式：2020-12-08T09:08:57.715Z
        timestamp = datetime.utcnow().isoformat()
        # 确保毫秒部分有3位数字
        if '.' in timestamp:
            timestamp = timestamp.split('.')[0] + '.' + timestamp.split('.')[1][:3] + 'Z'
        else:
            timestamp = timestamp + '.000Z'
        return timestamp
    
    def _sign(self, timestamp: str, method: str, request_path: str, body: str = '') -> str:
        """生成签名"""
        # OKX API签名格式: timestamp + method + request_path + body
        message = timestamp + method + request_path + body
        logger.debug(f"签名消息: {message}")
        logger.debug(f"API密钥长度: {len(self.api_secret)}")
        
        # 确保使用正确的编码
        mac = hmac.new(
            self.api_secret.encode('utf-8'),
            message.encode('utf-8'),
            digestmod=hashlib.sha256
        )
        signature = base64.b64encode(mac.digest()).decode('utf-8')
        logger.debug(f"生成的签名: {signature}")
        return signature
    
    def _get_headers(self, method: str, request_path: str, body: str = '') -> Dict[str, str]:
        """获取请求头"""
        timestamp = self._get_timestamp()
        sign = self._sign(timestamp, method, request_path, body)
        
        headers = {
            'OK-ACCESS-KEY': self.api_key,
            'OK-ACCESS-SIGN': sign,
            'OK-ACCESS-TIMESTAMP': timestamp,
            'OK-ACCESS-PASSPHRASE': self.passphrase,
            'Content-Type': 'application/json'
        }
        
        # 如果是演示账户，添加演示标记
        if self.is_demo:
            headers['x-simulated-trading'] = '1'
        
        logger.debug(f"请求头: {headers}")
        return headers
    
    async def _request(self, method: str, endpoint: str, data: Optional[Dict] = None) -> Dict[str, Any]:
        """发送HTTP请求"""
        url = f"{self.api_url}{endpoint}"
        
        # 确保body格式正确
        if data:
            body = json.dumps(data, separators=(',', ':'))  # 使用紧凑格式，避免空格
        else:
            body = ''
        
        # 构建完整的请求路径（包含/api/v5前缀）
        request_path = f"/api/v5{endpoint}"
        
        headers = self._get_headers(method, request_path, body)
        
        logger.debug(f"发送请求: {method} {url}")
        logger.debug(f"签名路径: {request_path}")
        logger.debug(f"请求体: {body}")
        
        try:
            async with aiohttp.ClientSession() as session:
                if method == 'GET':
                    async with session.get(url, headers=headers) as response:
                        result = await response.json()
                elif method == 'POST':
                    # 确保POST请求使用正确的数据格式
                    if data:
                        # 使用data=body确保与签名一致
                        async with session.post(url, headers=headers, data=body) as response:
                            result = await response.json()
                    else:
                        async with session.post(url, headers=headers) as response:
                            result = await response.json()
                else:
                    raise ValueError(f"不支持的HTTP方法: {method}")
                
                logger.info(f"REST API请求: {method} {endpoint}, 响应: {result}")
                
                # 检查API响应中的错误
                if result.get('code') != '0':
                    logger.error(f"OKX API错误: {result}")
                    return result
                
                return result
                
        except Exception as e:
            logger.error(f"REST API请求失败: {method} {endpoint}, 错误: {e}")
            return {"code": "1", "msg": f"请求失败: {str(e)}"}
    
    async def place_order(self, **kwargs) -> Dict[str, Any]:
        """下单"""
        endpoint = "/trade/order"
        return await self._request('POST', endpoint, kwargs)
    
    async def cancel_order(self, instId: str, ordId: str = None, clOrdId: str = None) -> Dict[str, Any]:
        """撤单"""
        endpoint = "/trade/cancel-order"
        data = {"instId": instId}
        if ordId:
            data["ordId"] = ordId
        if clOrdId:
            data["clOrdId"] = clOrdId
        
        logger.info(f"[REST] 撤单请求数据: {data}")
        return await self._request('POST', endpoint, data)
    
    async def get_order(self, instId: str, ordId: str = None, clOrdId: str = None) -> Dict[str, Any]:
        """查询订单"""
        endpoint = "/trade/order"
        params = f"?instId={instId}"
        if ordId:
            params += f"&ordId={ordId}"
        if clOrdId:
            params += f"&clOrdId={clOrdId}"
        
        # 对于GET请求，需要将查询参数包含在签名路径中
        request_path = endpoint + params
        return await self._request('GET', request_path)
    
    async def get_positions(self, instId: str = None) -> Dict[str, Any]:
        """查询持仓"""
        endpoint = "/account/positions"
        if instId:
            endpoint += f"?instId={instId}"
        return await self._request('GET', endpoint)
    
    async def get_account_info(self) -> Dict[str, Any]:
        """查询账户信息"""
        endpoint = "/account/balance"
        return await self._request('GET', endpoint)
    
    async def get_ticker(self, instId: str) -> Dict[str, Any]:
        """获取价格"""
        endpoint = f"/market/ticker?instId={instId}"
        return await self._request('GET', endpoint)
    
    async def set_leverage(self, lever: str, mgnMode: str, instId: str = None, 
                          ccy: str = None, posSide: str = None) -> Dict[str, Any]:
        """设置杠杆"""
        endpoint = "/account/set-leverage"
        data = {
            "lever": lever,
            "mgnMode": mgnMode
        }
        if instId:
            data["instId"] = instId
        if ccy:
            data["ccy"] = ccy
        if posSide:
            data["posSide"] = posSide
        return await self._request('POST', endpoint, data)
    
    async def set_position_mode(self, posMode: str) -> Dict[str, Any]:
        """设置持仓模式"""
        endpoint = "/account/set-position-mode"
        data = {"posMode": posMode}
        return await self._request('POST', endpoint, data)


 