#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Binance REST API客户端
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


class BinanceRESTClient(BaseRESTClient):
    """Binance REST API客户端"""
    
    def __init__(self, api_key: str, api_secret: str, passphrase: str = None, is_demo: bool = True):
        super().__init__(api_key, api_secret, passphrase, is_demo)
        
        # 根据是否为演示账户选择不同的URL
        if is_demo:
            self.base_url = "https://testnet.binance.vision"
            self.api_url = "https://testnet.binance.vision/api/v3"
        else:
            self.base_url = "https://api.binance.com"
            self.api_url = "https://api.binance.com/api/v3"
    
    def _get_exchange_type(self) -> ExchangeType:
        """获取交易所类型"""
        return ExchangeType.BINANCE
    
    def _sign(self, params: Dict[str, Any]) -> str:
        """生成签名"""
        query_string = '&'.join([f"{k}={v}" for k, v in sorted(params.items())])
        signature = hmac.new(
            self.api_secret.encode('utf-8'),
            query_string.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
        return signature
    
    def _get_headers(self) -> Dict[str, str]:
        """获取请求头"""
        return {
            'X-MBX-APIKEY': self.api_key,
            'Content-Type': 'application/json'
        }
    
    async def _request(self, method: str, endpoint: str, data: Optional[Dict] = None, params: Optional[Dict] = None) -> Dict[str, Any]:
        """发送HTTP请求"""
        url = f"{self.api_url}{endpoint}"
        
        # 添加时间戳
        if params is None:
            params = {}
        params['timestamp'] = int(time.time() * 1000)
        
        # 生成签名
        signature = self._sign(params)
        params['signature'] = signature
        
        headers = self._get_headers()
        
        logger.debug(f"发送请求: {method} {url}")
        logger.debug(f"参数: {params}")
        
        try:
            async with aiohttp.ClientSession() as session:
                if method == 'GET':
                    async with session.get(url, headers=headers, params=params, proxy=self.proxy) as response:
                        result = await response.json()
                elif method == 'POST':
                    if data:
                        async with session.post(url, headers=headers, params=params, data=json.dumps(data), proxy=self.proxy) as response:
                            result = await response.json()
                    else:
                        async with session.post(url, headers=headers, params=params, proxy=self.proxy) as response:
                            result = await response.json()
                else:
                    raise ValueError(f"不支持的HTTP方法: {method}")
                
                return result
                
        except Exception as e:
            logger.error(f"REST API请求失败: {method} {endpoint}, 错误: {e}")
            return {"error": f"请求失败: {str(e)}"}
    
    async def place_order(self, order_request: OrderRequest) -> OrderResponse:
        """下单（统一接口）"""
        try:
            # 转换统一格式到Binance格式
            binance_data = {
                'symbol': order_request.symbol,
                'side': order_request.side.value.upper(),
                'type': order_request.order_type.value.upper(),
                'quantity': str(order_request.quantity)
            }
            
            if order_request.price:
                binance_data['price'] = str(order_request.price)
            
            if order_request.client_order_id:
                binance_data['newClientOrderId'] = order_request.client_order_id
            
            if order_request.reduce_only:
                binance_data['reduceOnly'] = 'true'
            
            response = await self._request('POST', "/order", data=binance_data)
            
            if 'orderId' in response:
                return OrderResponse(
                    order_id=str(response.get('orderId', '')),
                    client_order_id=response.get('clientOrderId', order_request.client_order_id),
                    symbol=order_request.symbol,
                    side=order_request.side,
                    order_type=order_request.order_type,
                    quantity=order_request.quantity,
                    price=order_request.price,
                    status=OrderStatus(response.get('status', '').lower()),
                    filled_quantity=float(response.get('executedQty', '0')),
                    remaining_quantity=float(response.get('origQty', '0')) - float(response.get('executedQty', '0')),
                    timestamp=int(response.get('transactTime', 0)),
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
            params = {
                'symbol': symbol,
                'orderId': order_id
            }
            response = await self._request('DELETE', "/order", params=params)
            return 'orderId' in response
        except Exception as e:
            logger.error(f"取消订单异常: {e}")
            return False
    
    async def get_order(self, symbol: str, order_id: str) -> Optional[OrderResponse]:
        """获取订单信息（统一接口）"""
        try:
            params = {
                'symbol': symbol,
                'orderId': order_id
            }
            response = await self._request('GET', "/order", params=params)
            
            if 'orderId' in response:
                return OrderResponse(
                    order_id=str(response.get('orderId', '')),
                    client_order_id=response.get('clientOrderId', ''),
                    symbol=response.get('symbol', ''),
                    side=OrderSide(response.get('side', '').lower()),
                    order_type=OrderType(response.get('type', '').lower()),
                    quantity=float(response.get('origQty', '0')),
                    price=float(response.get('price', '0')) if response.get('price') else None,
                    status=OrderStatus(response.get('status', '').lower()),
                    filled_quantity=float(response.get('executedQty', '0')),
                    remaining_quantity=float(response.get('origQty', '0')) - float(response.get('executedQty', '0')),
                    timestamp=int(response.get('time', 0)),
                    exchange=self.exchange_type
                )
            return None
            
        except Exception as e:
            logger.error(f"获取订单异常: {e}")
            return None
    
    async def get_positions(self, symbol: Optional[str] = None) -> List[Position]:
        """获取持仓信息（统一接口）"""
        try:
            response = await self._request('GET', "/account")
            
            if 'balances' in response:
                positions = []
                for balance in response['balances']:
                    # 安全地转换数值，处理空字符串情况
                    free_str = balance.get('free', '0')
                    locked_str = balance.get('locked', '0')
                    
                    free = float(free_str if free_str != '' else '0')
                    locked = float(locked_str if locked_str != '' else '0')
                    total = free + locked
                    
                    if total > 0:  # 只返回有余额的记录
                        position = Position(
                            symbol=balance.get('asset', ''),
                            side='long',  # Binance现货只有多头
                            size=total,
                            entry_price=0.0,  # 现货没有开仓价格
                            mark_price=0.0,
                            unrealized_pnl=0.0,
                            margin=0.0,
                            leverage=1.0,
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
            response = await self._request('GET', "/account")
            
            if 'balances' in response:
                balances = []
                for balance_data in response['balances']:
                    free = float(balance_data.get('free', '0'))
                    locked = float(balance_data.get('locked', '0'))
                    total = free + locked
                    
                    if total > 0:  # 只返回有余额的记录
                        balance = Balance(
                            asset=balance_data.get('asset', ''),
                            free=free,
                            locked=locked,
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
            params = {'symbol': symbol}
            response = await self._request('GET', "/ticker/24hr", params=params)
            
            if 'symbol' in response:
                return Ticker(
                    symbol=response.get('symbol', ''),
                    price=float(response.get('lastPrice', '0')),
                    volume=float(response.get('volume', '0')),
                    timestamp=int(response.get('closeTime', 0)),
                    exchange=self.exchange_type,
                    bid_price=float(response.get('bidPrice', '0')),
                    ask_price=float(response.get('askPrice', '0')),
                    high_24h=float(response.get('highPrice', '0')),
                    low_24h=float(response.get('lowPrice', '0')),
                    change_24h=float(response.get('priceChange', '0')),
                    change_percent_24h=float(response.get('priceChangePercent', '0'))
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
                'symbol': symbol,
                'interval': interval,
                'limit': limit
            }
            
            if start_time:
                params['startTime'] = start_time
            if end_time:
                params['endTime'] = end_time
            
            response = await self._request('GET', "/klines", params=params)
            
            if isinstance(response, list):
                return response
            else:
                logger.error(f"获取K线数据失败: {response}")
                return []
                
        except Exception as e:
            logger.error(f"获取K线数据异常: {e}")
            return []
    
    async def get_open_orders(self, symbol: Optional[str] = None) -> List[OrderResponse]:
        """获取未成交订单（统一接口）"""
        try:
            params = {}
            if symbol:
                params['symbol'] = symbol
            
            response = await self._request('GET', "/openOrders", params=params)
            
            if isinstance(response, list):
                orders = []
                for order_data in response:
                    order = OrderResponse(
                        order_id=str(order_data.get('orderId', '')),
                        client_order_id=order_data.get('clientOrderId', ''),
                        symbol=order_data.get('symbol', ''),
                        side=OrderSide(order_data.get('side', '').lower()),
                        order_type=OrderType(order_data.get('type', '').lower()),
                        quantity=float(order_data.get('origQty', '0')),
                        price=float(order_data.get('price', '0')) if order_data.get('price') else None,
                        status=OrderStatus(order_data.get('status', '').lower()),
                        filled_quantity=float(order_data.get('executedQty', '0')),
                        remaining_quantity=float(order_data.get('origQty', '0')) - float(order_data.get('executedQty', '0')),
                        timestamp=int(order_data.get('time', 0)),
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
    
    # 实现其他抽象方法（简化版本）
    async def get_funding_rate(self, symbol: str) -> FundingRate:
        """获取资金费率（统一接口）"""
        # Binance现货没有资金费率，返回默认值
        return FundingRate(
            symbol=symbol,
            funding_rate=0.0,
            funding_time=0,
            next_funding_time=0,
            exchange=self.exchange_type
        )
    
    async def get_open_interest(self, symbol: str) -> OpenInterest:
        """获取持仓量（统一接口）"""
        # Binance现货没有持仓量概念，返回默认值
        return OpenInterest(
            symbol=symbol,
            open_interest=0.0,
            timestamp=int(time.time() * 1000),
            exchange=self.exchange_type
        )
    
    async def get_mark_price(self, symbol: str) -> MarkPrice:
        """获取标记价格（统一接口）"""
        # 使用当前价格作为标记价格
        ticker = await self.get_ticker(symbol)
        return MarkPrice(
            symbol=symbol,
            mark_price=ticker.price,
            index_price=ticker.price,
            timestamp=ticker.timestamp,
            exchange=self.exchange_type
        )
    
    async def get_liquidation_orders(self, symbol: Optional[str] = None, limit: int = 100) -> List[LiquidationOrder]:
        """获取强平订单（统一接口）"""
        # Binance现货没有强平订单
        return []
    
    async def get_trade_fee(self, symbol: str, category: str = "spot") -> TradeFee:
        """获取交易手续费（统一接口）"""
        # 返回默认手续费
        return TradeFee(
            symbol=symbol,
            maker_fee=0.001,
            taker_fee=0.001,
            category=category,
            exchange=self.exchange_type
        )
    
    async def get_margin_balance(self, asset: Optional[str] = None) -> List[MarginBalance]:
        """获取保证金余额（统一接口）"""
        # Binance现货没有保证金概念
        return []
    
    async def get_instruments(self, inst_type: str = "SPOT") -> List[Instrument]:
        """获取交易产品基础信息（统一接口）"""
        try:
            response = await self._request('GET', "/exchangeInfo")
            
            if 'symbols' in response:
                instruments = []
                for symbol_data in response['symbols']:
                    if symbol_data.get('status') == 'TRADING':
                        instrument = Instrument(
                            symbol=symbol_data.get('symbol', ''),
                            base_asset=symbol_data.get('baseAsset', ''),
                            quote_asset=symbol_data.get('quoteAsset', ''),
                            min_qty=float(symbol_data.get('filters', [{}])[0].get('minQty', '0')),
                            max_qty=float(symbol_data.get('filters', [{}])[0].get('maxQty', '0')),
                            step_size=float(symbol_data.get('filters', [{}])[0].get('stepSize', '0')),
                            min_notional=float(symbol_data.get('filters', [{}])[0].get('minNotional', '0')),
                            status=symbol_data.get('status', ''),
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
        # Binance现货没有账单详情API
        return []