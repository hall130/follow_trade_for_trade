#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Bybit REST API客户端
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


class BybitRESTClient(BaseRESTClient):
    """Bybit REST API客户端"""
    
    def __init__(self, api_key: str, api_secret: str, passphrase: str = None, is_demo: bool = True):
        super().__init__(api_key, api_secret, passphrase, is_demo)
        
        # 根据是否为演示账户选择不同的URL
        if is_demo:
            self.base_url = "https://api-testnet.bybit.com"
            self.api_url = "https://api-testnet.bybit.com/v5"
        else:
            self.base_url = "https://api.bybit.com"
            self.api_url = "https://api.bybit.com/v5"
    
    def _get_exchange_type(self) -> ExchangeType:
        """获取交易所类型"""
        return ExchangeType.BYBIT
    
    def _sign(self, timestamp: str, method: str, request_path: str, body: str = '') -> str:
        """生成签名"""
        message = timestamp + self.api_key + '5000' + body
        signature = hmac.new(
            self.api_secret.encode('utf-8'),
            message.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
        return signature
    
    def _get_headers(self, method: str, request_path: str, body: str = '') -> Dict[str, str]:
        """获取请求头"""
        timestamp = str(int(time.time() * 1000))
        sign = self._sign(timestamp, method, request_path, body)
        
        headers = {
            'X-BAPI-API-KEY': self.api_key,
            'X-BAPI-SIGN': sign,
            'X-BAPI-SIGN-TYPE': '2',
            'X-BAPI-TIMESTAMP': timestamp,
            'X-BAPI-RECV-WINDOW': '5000',
            'Content-Type': 'application/json'
        }
        
        return headers
    
    async def _request(self, method: str, endpoint: str, data: Optional[Dict] = None, params: Optional[Dict] = None) -> Dict[str, Any]:
        """发送HTTP请求"""
        url = f"{self.api_url}{endpoint}"
        
        # 处理查询参数
        if params and method == 'GET':
            query_string = '&'.join([f"{k}={v}" for k, v in params.items()])
            url += f"?{query_string}"
            request_path = f"/v5{endpoint}?{query_string}"
        else:
            request_path = f"/v5{endpoint}"
        
        # 对于公共接口，不需要签名
        if endpoint.startswith('/v5/market/'):
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
        logger.debug(f"请求体: {body}")
        
        try:
            async with aiohttp.ClientSession() as session:
                if method == 'GET':
                    async with session.get(url, headers=headers, proxy=self.proxy) as response:
                        result = await response.json()
                elif method == 'POST':
                    if data:
                        async with session.post(url, headers=headers, data=body, proxy=self.proxy) as response:
                            result = await response.json()
                    else:
                        async with session.post(url, headers=headers, proxy=self.proxy) as response:
                            result = await response.json()
                else:
                    raise ValueError(f"不支持的HTTP方法: {method}")
                
                # 检查API响应中的错误
                if result.get('retCode') != 0:
                    logger.error(f"Bybit API错误: {result}")
                    return result
                
                return result
                
        except Exception as e:
            logger.error(f"REST API请求失败: {method} {endpoint}, 错误: {e}")
            return {"retCode": 1, "retMsg": f"请求失败: {str(e)}"}
    
    async def place_order(self, order_request: OrderRequest) -> OrderResponse:
        """下单（统一接口）"""
        try:
            # 转换统一格式到Bybit格式
            bybit_data = {
                'category': 'linear',  # 默认线性合约
                'symbol': order_request.symbol,
                'side': order_request.side.value.capitalize(),
                'orderType': order_request.order_type.value.capitalize(),
                'qty': str(order_request.quantity)
            }
            
            if order_request.price:
                bybit_data['price'] = str(order_request.price)
            
            if order_request.client_order_id:
                bybit_data['orderLinkId'] = order_request.client_order_id
            
            if order_request.reduce_only:
                bybit_data['reduceOnly'] = True
            
            response = await self._request('POST', "/order/create", bybit_data)
            
            if response.get('retCode') == 0 and response.get('result'):
                order_data = response['result']
                return OrderResponse(
                    order_id=order_data.get('orderId', ''),
                    client_order_id=order_data.get('orderLinkId', order_request.client_order_id),
                    symbol=order_request.symbol,
                    side=order_request.side,
                    order_type=order_request.order_type,
                    quantity=order_request.quantity,
                    price=order_request.price,
                    status=OrderStatus.PENDING,  # Bybit下单后默认为pending
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
    
    async def cancel_order(self, symbol: str, order_id: str) -> bool:
        """取消订单（统一接口）"""
        try:
            data = {
                'category': 'linear',
                'symbol': symbol,
                'orderId': order_id
            }
            response = await self._request('POST', "/order/cancel", data)
            return response.get('retCode') == 0
        except Exception as e:
            logger.error(f"取消订单异常: {e}")
            return False
    
    async def get_order(self, symbol: str, order_id: str) -> Optional[OrderResponse]:
        """获取订单信息（统一接口）"""
        try:
            params = {
                'category': 'linear',
                'symbol': symbol,
                'orderId': order_id
            }
            response = await self._request('GET', "/order/realtime", params=params)
            
            if response.get('retCode') == 0 and response.get('result', {}).get('list'):
                order_data = response['result']['list'][0]
                return OrderResponse(
                    order_id=order_data.get('orderId', ''),
                    client_order_id=order_data.get('orderLinkId', ''),
                    symbol=order_data.get('symbol', ''),
                    side=OrderSide(order_data.get('side', '').lower()),
                    order_type=OrderType(order_data.get('orderType', '').lower()),
                    quantity=float(order_data.get('qty', '0')),
                    price=float(order_data.get('price', '0')) if order_data.get('price') else None,
                    status=OrderStatus(order_data.get('orderStatus', '').lower()),
                    filled_quantity=float(order_data.get('cumExecQty', '0')),
                    remaining_quantity=float(order_data.get('qty', '0')) - float(order_data.get('cumExecQty', '0')),
                    timestamp=int(order_data.get('createdTime', '0')),
                    exchange=self.exchange_type
                )
            return None
            
        except Exception as e:
            logger.error(f"获取订单异常: {e}")
            return None
    
    async def get_positions(self, symbol: Optional[str] = None) -> List[Position]:
        """获取持仓信息（统一接口）"""
        try:
            params = {'category': 'linear'}
            if symbol:
                params['symbol'] = symbol
            
            response = await self._request('GET', "/position/list", params=params)
            
            if response.get('retCode') == 0 and response.get('result', {}).get('list'):
                positions = []
                for pos_data in response['result']['list']:
                    # 安全地转换数值，处理空字符串情况
                    size_str = pos_data.get('size', '0')
                    if size_str == '' or size_str is None:
                        size_str = '0'
                    
                    size = float(size_str)
                    if size > 0:  # 只返回有持仓的记录
                        # 安全转换所有数值字段
                        avg_price_str = pos_data.get('avgPrice', '0')
                        mark_price_str = pos_data.get('markPrice', '0')
                        pnl_str = pos_data.get('unrealisedPnl', '0')
                        balance_str = pos_data.get('positionBalance', '0')
                        leverage_str = pos_data.get('leverage', '1')
                        
                        position = Position(
                            symbol=pos_data.get('symbol', ''),
                            side=pos_data.get('side', '').lower(),
                            size=size,
                            entry_price=float(avg_price_str if avg_price_str != '' else '0'),
                            mark_price=float(mark_price_str if mark_price_str != '' else '0'),
                            unrealized_pnl=float(pnl_str if pnl_str != '' else '0'),
                            margin=float(balance_str if balance_str != '' else '0'),
                            leverage=float(leverage_str if leverage_str != '' else '1'),
                            exchange=self.exchange_type
                        )
                        positions.append(position)
                
                return positions
            else:
                logger.error(f"获取持仓失败: {response}")
                return []
            
        except Exception as e:
            logger.error(f"获取持仓异常: {e}")
            return []
    
    async def get_balance(self) -> List[Balance]:
        """获取账户余额（统一接口）"""
        try:
            response = await self._request('GET', "/account/wallet-balance")
            
            if response.get('retCode') == 0 and response.get('result', {}).get('list'):
                balances = []
                for account in response['result']['list']:
                    for coin in account.get('coin', []):
                        total = float(coin.get('walletBalance', '0'))
                        if total > 0:  # 只返回有余额的记录
                            balance = Balance(
                                asset=coin.get('coin', ''),
                                free=float(coin.get('availableToWithdraw', '0')),
                                locked=total - float(coin.get('availableToWithdraw', '0')),
                                total=total,
                                exchange=self.exchange_type
                            )
                            balances.append(balance)
                
                return balances
            else:
                logger.error(f"获取余额失败: {response}")
                return []
            
        except Exception as e:
            logger.error(f"获取余额异常: {e}")
            return []
    
    async def get_ticker(self, symbol: str) -> Ticker:
        """获取行情信息（统一接口）"""
        try:
            params = {
                'category': 'linear',
                'symbol': symbol
            }
            response = await self._request('GET', "/market/tickers", params=params)
            
            if response.get('retCode') == 0 and response.get('result', {}).get('list'):
                data = response['result']['list'][0]
                return Ticker(
                    symbol=data.get('symbol', ''),
                    price=float(data.get('lastPrice', '0')),
                    volume=float(data.get('volume24h', '0')),
                    timestamp=int(data.get('time', '0')),
                    exchange=self.exchange_type,
                    bid_price=float(data.get('bid1Price', '0')),
                    ask_price=float(data.get('ask1Price', '0')),
                    high_24h=float(data.get('highPrice24h', '0')),
                    low_24h=float(data.get('lowPrice24h', '0')),
                    change_24h=float(data.get('price24hPcnt', '0')),
                    change_percent_24h=float(data.get('price24hPcnt', '0')) * 100
                )
            else:
                raise Exception(f"获取行情失败: {response}")
                
        except Exception as e:
            logger.error(f"获取行情异常: {e}")
            raise
    
    async def get_klines(self, symbol: str, interval: str, 
                        start_time: Optional[int] = None, 
                        end_time: Optional[int] = None,
                        limit: int = 500) -> List[List]:
        """获取K线数据（统一接口）"""
        try:
            params = {
                'category': 'linear',
                'symbol': symbol,
                'interval': interval,
                'limit': limit
            }
            
            if start_time:
                params['start'] = start_time
            if end_time:
                params['end'] = end_time
            
            response = await self._request('GET', "/market/kline", params=params)
            
            if response.get('retCode') == 0 and response.get('result', {}).get('list'):
                return response['result']['list']
            else:
                logger.error(f"获取K线数据失败: {response}")
                return []
                
        except Exception as e:
            logger.error(f"获取K线数据异常: {e}")
            return []
    
    async def get_open_orders(self, symbol: Optional[str] = None) -> List[OrderResponse]:
        """获取未成交订单（统一接口）"""
        try:
            params = {'category': 'linear'}
            if symbol:
                params['symbol'] = symbol
            
            response = await self._request('GET', "/order/realtime", params=params)
            
            if response.get('retCode') == 0 and response.get('result', {}).get('list'):
                orders = []
                for order_data in response['result']['list']:
                    if order_data.get('orderStatus') in ['New', 'PartiallyFilled']:
                        order = OrderResponse(
                            order_id=order_data.get('orderId', ''),
                            client_order_id=order_data.get('orderLinkId', ''),
                            symbol=order_data.get('symbol', ''),
                            side=OrderSide(order_data.get('side', '').lower()),
                            order_type=OrderType(order_data.get('orderType', '').lower()),
                            quantity=float(order_data.get('qty', '0')),
                            price=float(order_data.get('price', '0')) if order_data.get('price') else None,
                            status=OrderStatus(order_data.get('orderStatus', '').lower()),
                            filled_quantity=float(order_data.get('cumExecQty', '0')),
                            remaining_quantity=float(order_data.get('qty', '0')) - float(order_data.get('cumExecQty', '0')),
                            timestamp=int(order_data.get('createdTime', '0')),
                            exchange=self.exchange_type
                        )
                        orders.append(order)
                return orders
            else:
                logger.error(f"获取未成交订单失败: {response}")
                return []
            
        except Exception as e:
            logger.error(f"获取未成交订单异常: {e}")
            return []
    
    # 实现其他抽象方法
    async def get_funding_rate(self, symbol: str) -> FundingRate:
        """获取资金费率（统一接口）"""
        try:
            params = {
                'category': 'linear',
                'symbol': symbol
            }
            response = await self._request('GET', "/market/funding/history", params=params)
            
            if response.get('retCode') == 0 and response.get('result', {}).get('list'):
                data = response['result']['list'][0]
                return FundingRate(
                    symbol=data.get('symbol', ''),
                    funding_rate=float(data.get('fundingRate', '0')),
                    funding_time=int(data.get('fundingRateTimestamp', '0')),
                    next_funding_time=int(data.get('nextFundingTime', '0')),
                    exchange=self.exchange_type
                )
            else:
                raise Exception(f"获取资金费率失败: {response}")
                
        except Exception as e:
            logger.error(f"获取资金费率异常: {e}")
            raise
    
    async def get_open_interest(self, symbol: str) -> OpenInterest:
        """获取持仓量（统一接口）"""
        try:
            params = {
                'category': 'linear',
                'symbol': symbol
            }
            response = await self._request('GET', "/market/open-interest", params=params)
            
            if response.get('retCode') == 0 and response.get('result', {}).get('list'):
                data = response['result']['list'][0]
                return OpenInterest(
                    symbol=data.get('symbol', ''),
                    open_interest=float(data.get('openInterest', '0')),
                    timestamp=int(data.get('timestamp', '0')),
                    exchange=self.exchange_type
                )
            else:
                raise Exception(f"获取持仓量失败: {response}")
                
        except Exception as e:
            logger.error(f"获取持仓量异常: {e}")
            raise
    
    async def get_mark_price(self, symbol: str) -> MarkPrice:
        """获取标记价格（统一接口）"""
        try:
            params = {
                'category': 'linear',
                'symbol': symbol
            }
            response = await self._request('GET', "/market/mark-price-kline", params=params)
            
            if response.get('retCode') == 0 and response.get('result', {}).get('list'):
                data = response['result']['list'][0]
                return MarkPrice(
                    symbol=data.get('symbol', ''),
                    mark_price=float(data.get('markPrice', '0')),
                    index_price=float(data.get('indexPrice', '0')),
                    timestamp=int(data.get('timestamp', '0')),
                    exchange=self.exchange_type
                )
            else:
                raise Exception(f"获取标记价格失败: {response}")
                
        except Exception as e:
            logger.error(f"获取标记价格异常: {e}")
            raise
    
    async def get_liquidation_orders(self, symbol: Optional[str] = None, limit: int = 100) -> List[LiquidationOrder]:
        """获取强平订单（统一接口）"""
        try:
            params = {
                'category': 'linear',
                'limit': limit
            }
            if symbol:
                params['symbol'] = symbol
            
            response = await self._request('GET', "/market/liq-records", params=params)
            
            if response.get('retCode') == 0 and response.get('result', {}).get('list'):
                orders = []
                for order_data in response['result']['list']:
                    order = LiquidationOrder(
                        symbol=order_data.get('symbol', ''),
                        side=OrderSide(order_data.get('side', '').lower()),
                        size=float(order_data.get('qty', '0')),
                        price=float(order_data.get('price', '0')),
                        timestamp=int(order_data.get('time', '0')),
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
    
    async def get_trade_fee(self, symbol: str, category: str = "spot") -> TradeFee:
        """获取交易手续费（统一接口）"""
        # 返回默认手续费
        return TradeFee(
            symbol=symbol,
            maker_fee=0.0001,
            taker_fee=0.0006,
            category=category,
            exchange=self.exchange_type
        )
    
    async def get_margin_balance(self, asset: Optional[str] = None) -> List[MarginBalance]:
        """获取保证金余额（统一接口）"""
        # Bybit没有单独的保证金余额API
        return []
    
    async def get_instruments(self, inst_type: str = "SPOT") -> List[Instrument]:
        """获取交易产品基础信息（统一接口）"""
        try:
            params = {'category': 'linear'}
            response = await self._request('GET', "/market/instruments-info", params=params)
            
            if response.get('retCode') == 0 and response.get('result', {}).get('list'):
                instruments = []
                for inst_data in response['result']['list']:
                    if inst_data.get('status') == 'Trading':
                        instrument = Instrument(
                            symbol=inst_data.get('symbol', ''),
                            base_asset=inst_data.get('baseCoin', ''),
                            quote_asset=inst_data.get('quoteCoin', ''),
                            min_qty=float(inst_data.get('lotSizeFilter', {}).get('minOrderQty', '0')),
                            max_qty=float(inst_data.get('lotSizeFilter', {}).get('maxOrderQty', '0')),
                            step_size=float(inst_data.get('lotSizeFilter', {}).get('qtyStep', '0')),
                            min_notional=float(inst_data.get('priceFilter', {}).get('minPrice', '0')),
                            status=inst_data.get('status', ''),
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
    
    async def get_bill_details(self, asset: Optional[str] = None, limit: int = 100) -> List[BillDetail]:
        """获取账单详情（统一接口）"""
        try:
            params = {
                'category': 'linear',
                'limit': limit
            }
            if asset:
                params['coin'] = asset
            
            response = await self._request('GET', "/account/transaction-log", params=params)
            
            if response.get('retCode') == 0 and response.get('result', {}).get('list'):
                bills = []
                for bill_data in response['result']['list']:
                    bill = BillDetail(
                        bill_id=bill_data.get('id', ''),
                        asset=bill_data.get('coin', ''),
                        amount=float(bill_data.get('amount', '0')),
                        fee=float(bill_data.get('fee', '0')),
                        bill_type=bill_data.get('type', ''),
                        timestamp=int(bill_data.get('time', '0')),
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
