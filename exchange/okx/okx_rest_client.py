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
from typing import Dict, Any, Optional, List
from utils.logger import logger
from ..base_client import (
    BaseRESTClient, ExchangeType, OrderRequest, OrderResponse, Position, Balance, Ticker, 
    OrderSide, OrderType, OrderStatus, FundingRate, OpenInterest, MarkPrice, 
    LiquidationOrder, TradeFee, MarginBalance, Instrument, BillDetail
)


class OKXRESTClient(BaseRESTClient):
    """OKX REST API客户端"""
    
    def __init__(self, api_key: str, api_secret: str, passphrase: str, is_demo: bool = True):
        super().__init__(api_key, api_secret, passphrase, is_demo)
        
        # 根据是否为演示账户选择不同的URL
        if is_demo:
            self.base_url = "https://www.okx.com"
            self.api_url = "https://www.okx.com/api/v5"
        else:
            self.base_url = "https://www.okx.com"
            self.api_url = "https://www.okx.com/api/v5"
    
    def _get_exchange_type(self) -> ExchangeType:
        """获取交易所类型"""
        return ExchangeType.OKX
    
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
    
    async def _request(self, method: str, endpoint: str, data: Optional[Dict] = None, params: Optional[Dict] = None, retry_count: int = 3) -> Dict[str, Any]:
        """发送HTTP请求（带重试机制）"""
        url = f"{self.api_url}{endpoint}"
        
        # 处理查询参数
        if params and method == 'GET':
            query_string = '&'.join([f"{k}={v}" for k, v in params.items()])
            url += f"?{query_string}"
            request_path = f"/api/v5{endpoint}?{query_string}"
        else:
            request_path = f"/api/v5{endpoint}"
        
        # 对于公共接口，不需要签名
        if endpoint.startswith('/market/'):
            headers = {
                'Content-Type': 'application/json'
            }
        else:
            headers = self._get_headers(method, request_path, json.dumps(data) if data else '')
        
        # 确保body格式正确
        if data and method != 'GET':
            body = json.dumps(data, separators=(',', ':'))
        else:
            body = ''
        
        logger.debug(f"发送请求: {method} {url}")
        logger.debug(f"签名路径: {request_path}")
        logger.debug(f"请求体: {body}")
        
        # 重试机制
        last_error = None
        for attempt in range(retry_count):
            try:
                # 设置超时时间（连接超时30秒，总超时60秒）
                timeout = aiohttp.ClientTimeout(total=60, connect=30)
                
                async with aiohttp.ClientSession(timeout=timeout) as session:
                    if method == 'GET':
                        async with session.get(url, headers=headers) as response:
                            result = await response.json()
                    elif method == 'POST':
                        if data:
                            async with session.post(url, headers=headers, data=body) as response:
                                result = await response.json()
                        else:
                            async with session.post(url, headers=headers) as response:
                                result = await response.json()
                    else:
                        raise ValueError(f"不支持的HTTP方法: {method}")
                    
                    # 检查API响应中的错误
                    if result.get('code') != '0':
                        logger.error(f"OKX API错误: {result}")
                        return result
                    
                    return result
                    
            except asyncio.TimeoutError as e:
                last_error = e
                logger.warning(f"请求超时 (尝试 {attempt + 1}/{retry_count}): {method} {endpoint}")
                if attempt < retry_count - 1:
                    await asyncio.sleep(1)  # 等待1秒后重试
                continue
                
            except aiohttp.ClientError as e:
                last_error = e
                logger.warning(f"网络错误 (尝试 {attempt + 1}/{retry_count}): {method} {endpoint}, 错误: {e}")
                if attempt < retry_count - 1:
                    await asyncio.sleep(1)  # 等待1秒后重试
                continue
                
            except Exception as e:
                last_error = e
                logger.error(f"未知错误 (尝试 {attempt + 1}/{retry_count}): {method} {endpoint}, 错误: {e}")
                if attempt < retry_count - 1:
                    await asyncio.sleep(1)  # 等待1秒后重试
                continue
        
        # 所有重试都失败
        logger.error(f"REST API请求失败（{retry_count}次重试后）: {method} {endpoint}, 最后错误: {last_error}")
        return {"code": "1", "msg": f"请求失败: {str(last_error)}"}
    
    async def place_order(self, order_request: OrderRequest) -> OrderResponse:
        """下单（统一接口）"""
        try:
            # 转换统一格式到OKX格式
            okx_data = {
                'instId': order_request.symbol,
                'tdMode': 'cross',  # 默认全仓模式
                'side': order_request.side.value,
                'ordType': order_request.order_type.value,
                'sz': str(order_request.quantity)
            }
            
            if order_request.price:
                okx_data['px'] = str(order_request.price)
            
            if order_request.client_order_id:
                okx_data['clOrdId'] = order_request.client_order_id
            
            if order_request.reduce_only:
                okx_data['reduceOnly'] = 'true'
            
            response = await self._request('POST', "/trade/order", okx_data)
            
            if response.get('code') == '0' and response.get('data'):
                order_data = response['data'][0]
                return OrderResponse(
                    order_id=order_data.get('ordId', ''),
                    client_order_id=order_data.get('clOrdId', order_request.client_order_id),
                    symbol=order_request.symbol,
                    side=order_request.side,
                    order_type=order_request.order_type,
                    quantity=order_request.quantity,
                    price=order_request.price,
                    status=OrderStatus.PENDING,  # OKX下单后默认为pending
                    filled_quantity=0.0,
                    remaining_quantity=order_request.quantity,
                    timestamp=int(time.time() * 1000),
                    exchange=self.exchange_type
                )
            else:
                raise Exception(f"下单失败: {response}")
                
        except Exception as e:
            logger.error(f"下单异常: {e}")
            raise
    
    async def place_order_legacy(self, **kwargs) -> Dict[str, Any]:
        """下单（保持向后兼容）"""
        endpoint = "/trade/order"
        return await self._request('POST', endpoint, kwargs)
    
    async def cancel_order(self, symbol: str, order_id: str) -> bool:
        """取消订单（统一接口）"""
        try:
            data = {"instId": symbol, "ordId": order_id}
            response = await self._request('POST', "/trade/cancel-order", data)
            return response.get('code') == '0'
        except Exception as e:
            logger.error(f"取消订单异常: {e}")
            return False
    
    async def cancel_order_legacy(self, instId: str, ordId: str = None, clOrdId: str = None) -> Dict[str, Any]:
        """撤单（保持向后兼容）"""
        endpoint = "/trade/cancel-order"
        data = {"instId": instId}
        if ordId:
            data["ordId"] = ordId
        if clOrdId:
            data["clOrdId"] = clOrdId
        
        logger.info(f"[REST] 撤单请求数据: {data}")
        return await self._request('POST', endpoint, data)
    
    async def get_order(self, symbol: str, order_id: str) -> Optional[OrderResponse]:
        """获取订单信息（统一接口）"""
        try:
            params = f"?instId={symbol}&ordId={order_id}"
            request_path = "/trade/order" + params
            response = await self._request('GET', request_path)
            
            if response.get('code') == '0' and response.get('data'):
                order_data = response['data'][0]
                return OrderResponse(
                    order_id=order_data.get('ordId', ''),
                    client_order_id=order_data.get('clOrdId', ''),
                    symbol=order_data.get('instId', ''),
                    side=OrderSide(order_data.get('side', '').lower()),
                    order_type=OrderType(order_data.get('ordType', '').lower()),
                    quantity=float(order_data.get('sz', '0')),
                    price=float(order_data.get('px', '0')) if order_data.get('px') else None,
                    status=OrderStatus(order_data.get('state', '').lower()),
                    filled_quantity=float(order_data.get('accFillSz', '0')),
                    remaining_quantity=float(order_data.get('sz', '0')) - float(order_data.get('accFillSz', '0')),
                    timestamp=int(order_data.get('cTime', '0')),
                    exchange=self.exchange_type
                )
            return None
            
        except Exception as e:
            logger.error(f"获取订单异常: {e}")
            return None
    
    async def get_order_legacy(self, instId: str, ordId: str = None, clOrdId: str = None) -> Dict[str, Any]:
        """查询订单（保持向后兼容）"""
        endpoint = "/trade/order"
        params = f"?instId={instId}"
        if ordId:
            params += f"&ordId={ordId}"
        if clOrdId:
            params += f"&clOrdId={clOrdId}"
        
        # 对于GET请求，需要将查询参数包含在签名路径中
        request_path = endpoint + params
        return await self._request('GET', request_path)
    
    async def get_positions(self, symbol: Optional[str] = None) -> List[Position]:
        """获取持仓信息（统一接口）"""
        try:
            endpoint = "/account/positions"
            if symbol:
                endpoint += f"?instId={symbol}"
            
            response = await self._request('GET', endpoint)
            
            if response.get('code') != '0':
                logger.error(f"获取持仓失败: {response}")
                return []
            
            positions = []
            for pos_data in response.get('data', []):
                if float(pos_data.get('pos', '0')) > 0:  # 只返回有持仓的记录
                    position = Position(
                        symbol=pos_data.get('instId', ''),
                        side=pos_data.get('posSide', '').lower(),
                        size=float(pos_data.get('pos', '0')),
                        entry_price=float(pos_data.get('avgPx', '0')),
                        mark_price=float(pos_data.get('markPx', '0')),
                        unrealized_pnl=float(pos_data.get('upl', '0')),
                        margin=float(pos_data.get('margin', '0')),
                        leverage=float(pos_data.get('lever', '1')),
                        exchange=self.exchange_type
                    )
                    positions.append(position)
            
            return positions
            
        except Exception as e:
            logger.error(f"获取持仓异常: {e}")
            return []
    
    async def get_positions_legacy(self, instId: str = None) -> Dict[str, Any]:
        """查询持仓（保持向后兼容）"""
        endpoint = "/account/positions"
        if instId:
            endpoint += f"?instId={instId}"
        return await self._request('GET', endpoint)
    
    async def get_account_info(self) -> Dict[str, Any]:
        """查询账户信息（保持向后兼容）"""
        endpoint = "/account/balance"
        return await self._request('GET', endpoint)
    
    async def get_balance(self) -> List[Balance]:
        """获取账户余额（统一接口）"""
        try:
            response = await self._request('GET', "/account/balance")
            
            if response.get('code') != '0':
                logger.error(f"获取余额失败: {response}")
                return []
            
            balances = []
            for detail in response.get('data', []):
                for detail_item in detail.get('details', []):
                    balance = Balance(
                        asset=detail_item.get('ccy', ''),
                        free=float(detail_item.get('availBal', '0') or '0'),
                        locked=float(detail_item.get('frozenBal', '0') or '0'),
                        total=float(detail_item.get('eq', '0') or '0'),
                        exchange=self.exchange_type
                    )
                    balances.append(balance)
            
            return balances
            
        except Exception as e:
            logger.error(f"获取余额异常: {e}")
            return []
    
    async def get_ticker(self, symbol: str) -> Ticker:
        """获取行情信息（统一接口）"""
        try:
            endpoint = f"/market/ticker?instId={symbol}"
            response = await self._request('GET', endpoint)
            
            if response.get('code') == '0' and response.get('data'):
                ticker_data = response['data'][0]
                return Ticker(
                    symbol=ticker_data.get('instId', ''),
                    price=float(ticker_data.get('last', '0')),
                    volume=float(ticker_data.get('vol24h', '0')),
                    timestamp=int(ticker_data.get('ts', '0')),
                    exchange=self.exchange_type
                )
            else:
                raise Exception(f"获取行情失败: {response}")
                
        except Exception as e:
            logger.error(f"获取行情异常: {e}")
            raise
    
    async def get_ticker_legacy(self, instId: str) -> Dict[str, Any]:
        """获取价格（保持向后兼容）"""
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

    async def get_klines(self, symbol: str, interval: str, 
                        start_time: Optional[int] = None, 
                        end_time: Optional[int] = None,
                        limit: int = 500) -> List[List]:
        """获取K线数据（统一接口）"""
        try:
            endpoint = "/market/history-candles"
            params = {
                'instId': symbol,
                'bar': interval,
                'limit': str(limit)
            }
            
            if start_time:
                params['before'] = str(start_time)  # 获取start_time之后的数据
            if end_time:
                params['after'] = str(end_time)    # 获取end_time之前的数据
            
            response = await self._request('GET', endpoint, params=params)
            
            if response.get('code') == '0':
                return response.get('data', [])
            else:
                logger.error(f"获取K线数据失败: {response}")
                return []
                
        except Exception as e:
            logger.error(f"获取K线数据异常: {e}")
            return []
    
    async def get_open_orders(self, symbol: Optional[str] = None) -> List[OrderResponse]:
        """获取未成交订单（统一接口）"""
        try:
            endpoint = "/trade/orders-pending"
            if symbol:
                endpoint += f"?instId={symbol}"
            
            response = await self._request('GET', endpoint)
            
            if response.get('code') != '0':
                logger.error(f"获取未成交订单失败: {response}")
                return []
            
            orders = []
            for order_data in response.get('data', []):
                order = OrderResponse(
                    order_id=order_data.get('ordId', ''),
                    client_order_id=order_data.get('clOrdId', ''),
                    symbol=order_data.get('instId', ''),
                    side=OrderSide(order_data.get('side', '').lower()),
                    order_type=OrderType(order_data.get('ordType', '').lower()),
                    quantity=float(order_data.get('sz', '0')),
                    price=float(order_data.get('px', '0')) if order_data.get('px') else None,
                    status=OrderStatus(order_data.get('state', '').lower()),
                    filled_quantity=float(order_data.get('accFillSz', '0')),
                    remaining_quantity=float(order_data.get('sz', '0')) - float(order_data.get('accFillSz', '0')),
                    timestamp=int(order_data.get('cTime', '0')),
                    exchange=self.exchange_type
                )
                orders.append(order)
            
            return orders
            
        except Exception as e:
            logger.error(f"获取未成交订单异常: {e}")
            return []
    
    async def get_historical_klines(self, symbol: str, interval: str, 
                                start_time: int = None, end_time: int = None, 
                                limit: int = 100) -> List:
        """获取历史K线数据
        
        OKX API官方参数说明（/market/history-candles）：
        - instId: 产品ID，如 BTC-USDT
        - bar: 时间粒度，如 1m/3m/5m/15m/30m/1H/2H/4H/6H/12H/1D/1W/1M
        - after: 请求此时间戳**之前**（更旧的数据）的分页内容
        - before: 请求此时间戳**之后**（更新的数据）的分页内容，单独使用时返回最新数据
        - limit: 分页返回的结果集数量，最大为300，默认100条
        
        参数说明：
        - start_time: 不使用（保留接口兼容性）
        - end_time: 用作 after 参数，获取此时间戳之前的数据（用于分页向过去翻页）
        
        注意：
        1. OKX返回的数据是**倒序**排列（最新的在前）
        2. 不传 after/before 时，返回最新的 limit 条数据
        """
        try:
            endpoint = "/market/history-candles"
            
            # 限制 limit 最大值为 300
            actual_limit = min(limit, 300)
            
            params = {
                'instId': symbol,
                'bar': interval,
                'limit': str(actual_limit)
            }
            
            # 使用 end_time 作为 after 参数（用于向过去翻页）
            if end_time:
                params['after'] = str(end_time)
                logger.info(f"🔍 OKX历史K线分页请求: symbol={symbol}, interval={interval}, after={end_time}, limit={actual_limit}")
            else:
                logger.info(f"🔍 OKX历史K线请求: symbol={symbol}, interval={interval}, limit={actual_limit}")
            
            response = await self._request('GET', endpoint, params=params)
            
            data = response.get('data', [])
            logger.info(f"🔍 OKX API响应: code={response.get('code')}, msg={response.get('msg', 'success')}, data_count={len(data)}")
            
            if response.get('code') == '0':
                if len(data) > 0:
                    # 打印数据时间范围（OKX返回的数据是倒序的，第一条是最新的）
                    first_time = int(data[-1][0])  # 最旧的数据（数组末尾）
                    last_time = int(data[0][0])    # 最新的数据（数组开头）
                    from datetime import datetime
                    first_dt = datetime.fromtimestamp(first_time / 1000).strftime('%Y-%m-%d %H:%M:%S')
                    last_dt = datetime.fromtimestamp(last_time / 1000).strftime('%Y-%m-%d %H:%M:%S')
                    logger.info(f"🔍 数据时间范围: {first_dt} (旧) -> {last_dt} (新)")
                else:
                    logger.warning(f"⚠️ 获取到0条数据，可能是产品ID不正确或该产品没有K线数据")
                return data
            else:
                logger.error(f"❌ 获取历史K线失败: code={response.get('code')}, msg={response.get('msg')}")
                return []
                
        except Exception as e:
            logger.error(f"❌ 获取历史K线异常: {e}")
            return []
    
    # ==================== 新增功能方法 ====================
    
    async def get_funding_rate(self, symbol: str) -> FundingRate:
        """获取资金费率（统一接口）"""
        try:
            endpoint = f"/public/funding-rate?instId={symbol}"
            response = await self._request('GET', endpoint)
            
            if response.get('code') == '0' and response.get('data'):
                data = response['data'][0]
                return FundingRate(
                    symbol=data.get('instId', ''),
                    funding_rate=float(data.get('fundingRate', '0')),
                    funding_time=int(data.get('fundingTime', '0')),
                    next_funding_time=int(data.get('nextFundingTime', '0')),
                    exchange=self.exchange_type
                )
            else:
                logger.error(f"获取资金费率失败: {response}")
                raise Exception(f"获取资金费率失败: {response}")
                
        except Exception as e:
            logger.error(f"获取资金费率异常: {e}")
            raise
    
    async def get_funding_rate_legacy(self, symbol: str) -> Dict[str, Any]:
        """获取资金费率（保持向后兼容）"""
        try:
            endpoint = f"/public/funding-rate?instId={symbol}"
            response = await self._request('GET', endpoint)
            
            if response.get('code') == '0' and response.get('data'):
                return response['data'][0]
            else:
                logger.error(f"获取资金费率失败: {response}")
                return {}
                
        except Exception as e:
            logger.error(f"获取资金费率异常: {e}")
            return {}
    
    async def get_funding_rate_history(self, symbol: str, limit: int = 100) -> List[Dict]:
        """获取资金费率历史"""
        try:
            endpoint = f"/public/funding-rate-history?instId={symbol}&limit={limit}"
            response = await self._request('GET', endpoint)
            
            if response.get('code') == '0':
                return response.get('data', [])
            else:
                logger.error(f"获取资金费率历史失败: {response}")
                return []
                
        except Exception as e:
            logger.error(f"获取资金费率历史异常: {e}")
            return []
    
    async def get_open_interest(self, symbol: str) -> OpenInterest:
        """获取持仓量（统一接口）"""
        try:
            endpoint = f"/public/open-interest?instId={symbol}"
            response = await self._request('GET', endpoint)
            
            if response.get('code') == '0' and response.get('data'):
                data = response['data'][0]
                return OpenInterest(
                    symbol=data.get('instId', ''),
                    open_interest=float(data.get('oi', '0')),
                    timestamp=int(data.get('ts', '0')),
                    exchange=self.exchange_type
                )
            else:
                logger.error(f"获取持仓量失败: {response}")
                raise Exception(f"获取持仓量失败: {response}")
                
        except Exception as e:
            logger.error(f"获取持仓量异常: {e}")
            raise
    
    async def get_open_interest_legacy(self, symbol: str) -> Dict[str, Any]:
        """获取持仓量（保持向后兼容）"""
        try:
            endpoint = f"/public/open-interest?instId={symbol}"
            response = await self._request('GET', endpoint)
            
            if response.get('code') == '0' and response.get('data'):
                return response['data'][0]
            else:
                logger.error(f"获取持仓量失败: {response}")
                return {}
                
        except Exception as e:
            logger.error(f"获取持仓量异常: {e}")
            return {}
    
    async def get_mark_price(self, symbol: str) -> MarkPrice:
        """获取标记价格（统一接口）"""
        try:
            endpoint = f"/public/mark-price?instId={symbol}"
            response = await self._request('GET', endpoint)
            
            if response.get('code') == '0' and response.get('data'):
                data = response['data'][0]
                return MarkPrice(
                    symbol=data.get('instId', ''),
                    mark_price=float(data.get('markPx', '0')),
                    index_price=float(data.get('idxPx', '0')),
                    timestamp=int(data.get('ts', '0')),
                    exchange=self.exchange_type
                )
            else:
                logger.error(f"获取标记价格失败: {response}")
                raise Exception(f"获取标记价格失败: {response}")
                
        except Exception as e:
            logger.error(f"获取标记价格异常: {e}")
            raise
    
    async def get_mark_price_legacy(self, symbol: str) -> Dict[str, Any]:
        """获取标记价格（保持向后兼容）"""
        try:
            endpoint = f"/public/mark-price?instId={symbol}"
            response = await self._request('GET', endpoint)
            
            if response.get('code') == '0' and response.get('data'):
                return response['data'][0]
            else:
                logger.error(f"获取标记价格失败: {response}")
                return {}
                
        except Exception as e:
            logger.error(f"获取标记价格异常: {e}")
            return {}
    
    async def get_liquidation_orders(self, symbol: Optional[str] = None, limit: int = 100) -> List[LiquidationOrder]:
        """获取强平订单（统一接口）"""
        try:
            endpoint = "/public/liquidation-orders"
            params = {'limit': str(limit)}
            if symbol:
                params['instId'] = symbol
            
            response = await self._request('GET', endpoint, params=params)
            
            if response.get('code') == '0':
                orders = []
                for order_data in response.get('data', []):
                    order = LiquidationOrder(
                        symbol=order_data.get('instId', ''),
                        side=OrderSide(order_data.get('side', '').lower()),
                        size=float(order_data.get('sz', '0')),
                        price=float(order_data.get('px', '0')),
                        timestamp=int(order_data.get('ts', '0')),
                        exchange=self.exchange_type
                    )
                    orders.append(order)
                return orders
            else:
                logger.error(f"获取强平订单失败: {response}")
                return []
                
        except Exception as e:
            logger.error(f"获取强平订单异常: {e}")
            return []
    
    async def get_liquidation_orders_legacy(self, symbol: str = None, limit: int = 100) -> List[Dict]:
        """获取强平订单（保持向后兼容）"""
        try:
            endpoint = "/public/liquidation-orders"
            params = {'limit': str(limit)}
            if symbol:
                params['instId'] = symbol
            
            response = await self._request('GET', endpoint, params=params)
            
            if response.get('code') == '0':
                return response.get('data', [])
            else:
                logger.error(f"获取强平订单失败: {response}")
                return []
                
        except Exception as e:
            logger.error(f"获取强平订单异常: {e}")
            return []
    
    async def get_trade_fee(self, symbol: str, category: str = "spot") -> TradeFee:
        """获取交易手续费（统一接口）"""
        try:
            endpoint = "/account/trade-fee"
            params = {
                'instType': category,
                'instId': symbol
            }
            response = await self._request('GET', endpoint, params=params)
            
            if response.get('code') == '0' and response.get('data'):
                data = response['data'][0]
                return TradeFee(
                    symbol=data.get('instId', ''),
                    maker_fee=float(data.get('maker', '0')),
                    taker_fee=float(data.get('taker', '0')),
                    category=data.get('category', category),
                    exchange=self.exchange_type
                )
            else:
                logger.error(f"获取交易手续费失败: {response}")
                raise Exception(f"获取交易手续费失败: {response}")
                
        except Exception as e:
            logger.error(f"获取交易手续费异常: {e}")
            raise
    
    async def get_trade_fee_legacy(self, symbol: str, category: str = "spot") -> Dict[str, Any]:
        """获取交易手续费（保持向后兼容）"""
        try:
            endpoint = "/account/trade-fee"
            params = {
                'instType': category,
                'instId': symbol
            }
            response = await self._request('GET', endpoint, params=params)
            
            if response.get('code') == '0' and response.get('data'):
                return response['data'][0]
            else:
                logger.error(f"获取交易手续费失败: {response}")
                return {}
                
        except Exception as e:
            logger.error(f"获取交易手续费异常: {e}")
            return {}
    
    async def get_margin_balance(self, asset: Optional[str] = None) -> List[MarginBalance]:
        """获取保证金余额（统一接口）"""
        try:
            endpoint = "/account/margin-balance"
            params = {}
            if asset:
                params['ccy'] = asset
            
            response = await self._request('GET', endpoint, params=params)
            
            if response.get('code') == '0':
                balances = []
                for balance_data in response.get('data', []):
                    balance = MarginBalance(
                        asset=balance_data.get('ccy', ''),
                        total=float(balance_data.get('eq', '0')),
                        available=float(balance_data.get('availEq', '0')),
                        frozen=float(balance_data.get('frozenBal', '0')),
                        borrowed=float(balance_data.get('borrow', '0')),
                        interest=float(balance_data.get('interest', '0')),
                        exchange=self.exchange_type
                    )
                    balances.append(balance)
                return balances
            else:
                logger.error(f"获取保证金余额失败: {response}")
                return []
                
        except Exception as e:
            logger.error(f"获取保证金余额异常: {e}")
            return []
    
    async def get_margin_balance_legacy(self, ccy: str = None) -> List[Dict]:
        """获取保证金余额（保持向后兼容）"""
        try:
            endpoint = "/account/margin-balance"
            params = {}
            if ccy:
                params['ccy'] = ccy
            
            response = await self._request('GET', endpoint, params=params)
            
            if response.get('code') == '0':
                return response.get('data', [])
            else:
                logger.error(f"获取保证金余额失败: {response}")
                return []
                
        except Exception as e:
            logger.error(f"获取保证金余额异常: {e}")
            return []
    
    async def get_borrow_repay_history(self, ccy: str = None, limit: int = 100) -> List[Dict]:
        """获取借币还币历史"""
        try:
            endpoint = "/account/borrow-repay-history"
            params = {'limit': str(limit)}
            if ccy:
                params['ccy'] = ccy
            
            response = await self._request('GET', endpoint, params=params)
            
            if response.get('code') == '0':
                return response.get('data', [])
            else:
                logger.error(f"获取借币还币历史失败: {response}")
                return []
                
        except Exception as e:
            logger.error(f"获取借币还币历史异常: {e}")
            return []
    
    async def get_interest_limits(self, ccy: str = None) -> List[Dict]:
        """获取计息记录"""
        try:
            endpoint = "/account/interest-limits"
            params = {}
            if ccy:
                params['ccy'] = ccy
            
            response = await self._request('GET', endpoint, params=params)
            
            if response.get('code') == '0':
                return response.get('data', [])
            else:
                logger.error(f"获取计息记录失败: {response}")
                return []
                
        except Exception as e:
            logger.error(f"获取计息记录异常: {e}")
            return []
    
    async def get_max_order_size(self, symbol: str, side: str, order_type: str) -> Dict[str, Any]:
        """获取最大可交易数量"""
        try:
            endpoint = "/account/max-order-size"
            params = {
                'instId': symbol,
                'side': side,
                'ordType': order_type
            }
            response = await self._request('GET', endpoint, params=params)
            
            if response.get('code') == '0' and response.get('data'):
                return response['data'][0]
            else:
                logger.error(f"获取最大可交易数量失败: {response}")
                return {}
                
        except Exception as e:
            logger.error(f"获取最大可交易数量异常: {e}")
            return {}
    
    async def get_max_avail_size(self, symbol: str, side: str) -> Dict[str, Any]:
        """获取最大可用数量"""
        try:
            endpoint = "/account/max-avail-size"
            params = {
                'instId': symbol,
                'side': side
            }
            response = await self._request('GET', endpoint, params=params)
            
            if response.get('code') == '0' and response.get('data'):
                return response['data'][0]
            else:
                logger.error(f"获取最大可用数量失败: {response}")
                return {}
                
        except Exception as e:
            logger.error(f"获取最大可用数量异常: {e}")
            return {}
    
    async def get_fee_rates(self, category: str = "spot") -> List[Dict]:
        """获取手续费等级"""
        try:
            endpoint = "/account/fee-rates"
            params = {'category': category}
            response = await self._request('GET', endpoint, params=params)
            
            if response.get('code') == '0':
                return response.get('data', [])
            else:
                logger.error(f"获取手续费等级失败: {response}")
                return []
                
        except Exception as e:
            logger.error(f"获取手续费等级异常: {e}")
            return []
    
    async def get_instruments(self, inst_type: str = "SPOT") -> List[Instrument]:
        """获取交易产品基础信息（统一接口）"""
        try:
            endpoint = f"/public/instruments?instType={inst_type}"
            response = await self._request('GET', endpoint)
            
            if response.get('code') == '0':
                instruments = []
                for inst_data in response.get('data', []):
                    instrument = Instrument(
                        symbol=inst_data.get('instId', ''),
                        base_asset=inst_data.get('baseCcy', ''),
                        quote_asset=inst_data.get('quoteCcy', ''),
                        min_qty=float(inst_data.get('minSz', '0')),
                        max_qty=float(inst_data.get('maxSz', '0')),
                        step_size=float(inst_data.get('tickSz', '0')),
                        min_notional=float(inst_data.get('minSz', '0')),
                        status=inst_data.get('state', ''),
                        exchange=self.exchange_type
                    )
                    instruments.append(instrument)
                return instruments
            else:
                logger.error(f"获取交易产品信息失败: {response}")
                return []
                
        except Exception as e:
            logger.error(f"获取交易产品信息异常: {e}")
            return []
    
    async def get_instruments_legacy(self, inst_type: str = "SPOT") -> List[Dict]:
        """获取交易产品基础信息（保持向后兼容）"""
        try:
            endpoint = f"/public/instruments?instType={inst_type}"
            response = await self._request('GET', endpoint)
            
            if response.get('code') == '0':
                return response.get('data', [])
            else:
                logger.error(f"获取交易产品信息失败: {response}")
                return []
                
        except Exception as e:
            logger.error(f"获取交易产品信息异常: {e}")
            return []
    
    async def get_delivery_exercise_history(self, symbol: str = None, limit: int = 100) -> List[Dict]:
        """获取交割/行权历史"""
        try:
            endpoint = "/account/delivery-exercise-history"
            params = {'limit': str(limit)}
            if symbol:
                params['instId'] = symbol
            
            response = await self._request('GET', endpoint, params=params)
            
            if response.get('code') == '0':
                return response.get('data', [])
            else:
                logger.error(f"获取交割/行权历史失败: {response}")
                return []
                
        except Exception as e:
            logger.error(f"获取交割/行权历史异常: {e}")
            return []
    
    async def get_bill_details(self, asset: Optional[str] = None, limit: int = 100) -> List[BillDetail]:
        """获取账单详情（统一接口）"""
        try:
            endpoint = "/account/bills-details"
            params = {'limit': str(limit)}
            if asset:
                params['ccy'] = asset
            
            response = await self._request('GET', endpoint, params=params)
            
            if response.get('code') == '0':
                bills = []
                for bill_data in response.get('data', []):
                    bill = BillDetail(
                        bill_id=bill_data.get('billId', ''),
                        asset=bill_data.get('ccy', ''),
                        amount=float(bill_data.get('bal', '0')),
                        fee=float(bill_data.get('fee', '0')),
                        bill_type=bill_data.get('type', ''),
                        timestamp=int(bill_data.get('ts', '0')),
                        exchange=self.exchange_type
                    )
                    bills.append(bill)
                return bills
            else:
                logger.error(f"获取账单详情失败: {response}")
                return []
                
        except Exception as e:
            logger.error(f"获取账单详情异常: {e}")
            return []
    
    async def get_bill_details_legacy(self, ccy: str = None, limit: int = 100) -> List[Dict]:
        """获取账单详情（保持向后兼容）"""
        try:
            endpoint = "/account/bills-details"
            params = {'limit': str(limit)}
            if ccy:
                params['ccy'] = ccy
            
            response = await self._request('GET', endpoint, params=params)
            
            if response.get('code') == '0':
                return response.get('data', [])
            else:
                logger.error(f"获取账单详情失败: {response}")
                return []
                
        except Exception as e:
            logger.error(f"获取账单详情异常: {e}")
            return []
    
    async def get_config(self) -> Dict[str, Any]:
        """获取系统配置"""
        try:
            endpoint = "/public/config"
            response = await self._request('GET', endpoint)
            
            if response.get('code') == '0' and response.get('data'):
                return response['data'][0]
            else:
                logger.error(f"获取系统配置失败: {response}")
                return {}
                
        except Exception as e:
            logger.error(f"获取系统配置异常: {e}")
            return {}
    
    async def get_system_time(self) -> Dict[str, Any]:
        """获取系统时间"""
        try:
            endpoint = "/public/time"
            response = await self._request('GET', endpoint)
            
            if response.get('code') == '0' and response.get('data'):
                return response['data'][0]
            else:
                logger.error(f"获取系统时间失败: {response}")
                return {}
                
        except Exception as e:
            logger.error(f"获取系统时间异常: {e}")
            return {}
    
    async def get_exchange_rate(self, ccy: str = None) -> List[Dict]:
        """获取汇率"""
        try:
            endpoint = "/public/exchange-rate"
            params = {}
            if ccy:
                params['ccy'] = ccy
            
            response = await self._request('GET', endpoint, params=params)
            
            if response.get('code') == '0':
                return response.get('data', [])
            else:
                logger.error(f"获取汇率失败: {response}")
                return []
                
        except Exception as e:
            logger.error(f"获取汇率异常: {e}")
            return []
 