#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
统一REST客户端
提供统一的交易所REST API接口
"""

from typing import Dict, Any, Optional, List, Union
from .base_client import (
    BaseRESTClient, ExchangeType, OrderRequest, OrderResponse, 
    Position, Balance, Ticker, OrderSide, OrderType, OrderStatus,
    FundingRate, OpenInterest, MarkPrice, LiquidationOrder, TradeFee, 
    MarginBalance, Instrument, BillDetail
)
from .exchange_client_factory import ExchangeClientFactory
from utils.logger import logger


class UnifiedRESTClient:
    """统一REST客户端"""
    
    def __init__(self, exchange: ExchangeType, api_key: str, api_secret: str, 
                 passphrase: str = None, is_demo: bool = True):
        self.exchange = exchange
        self.api_key = api_key
        self.api_secret = api_secret
        self.passphrase = passphrase
        self.is_demo = is_demo
        
        # 创建底层交易所客户端
        self._client = ExchangeClientFactory.create_rest_client(
            exchange, api_key, api_secret, passphrase, is_demo
        )
    
    async def place_order(self, symbol: str, side: str, order_type: str, 
                         quantity: float, price: Optional[float] = None,
                         client_order_id: Optional[str] = None, **kwargs) -> Dict[str, Any]:
        """
        统一下单接口
        
        Args:
            symbol: 交易对
            side: 买卖方向 (buy/sell)
            order_type: 订单类型 (market/limit/stop)
            quantity: 数量
            price: 价格（限价单必需）
            client_order_id: 客户端订单ID
            **kwargs: 其他参数
        
        Returns:
            订单响应
        """
        try:
            # 从 kwargs 中提取 OrderRequest 支持的参数
            order_request_params = {}
            if 'reduce_only' in kwargs:
                order_request_params['reduce_only'] = kwargs['reduce_only']
            if 'stop_price' in kwargs:
                order_request_params['stop_price'] = kwargs['stop_price']
            if 'time_in_force' in kwargs:
                order_request_params['time_in_force'] = kwargs['time_in_force']
            # OKX 特定参数
            if 'tdMode' in kwargs:
                order_request_params['td_mode'] = kwargs['tdMode']
            if 'posSide' in kwargs:
                order_request_params['pos_side'] = kwargs['posSide']
            if 'lever' in kwargs:
                order_request_params['lever'] = kwargs['lever']
            
            # 构建订单请求（传递所有支持的参数）
            order_request = OrderRequest(
                symbol=symbol,
                side=OrderSide(side.lower()),
                order_type=OrderType(order_type.lower()),
                quantity=quantity,
                price=price,
                client_order_id=client_order_id,
                **order_request_params
            )
            
            # 调用底层客户端
            response = await self._client.place_order(order_request)
            
            # 转换为统一格式
            formatted_response = self._format_order_response(response)
            
            # 为了向后兼容，同时返回 OKX 原始格式
            if self.exchange == ExchangeType.OKX:
                return {
                    "code": "0",
                    "data": [{
                        "ordId": response.order_id,
                        "clOrdId": response.client_order_id,
                        "sCode": "0",
                        "sMsg": "success"
                    }],
                    # 同时包含统一格式数据
                    "unified_format": formatted_response
                }
            
            return formatted_response
            
        except Exception as e:
            logger.error(f"下单失败: {e}")
            return {"success": False, "error": str(e)}
    
    async def cancel_order(self, symbol: str, order_id: str) -> Dict[str, Any]:
        """
        统一取消订单接口
        
        Args:
            symbol: 交易对
            order_id: 订单ID
        
        Returns:
            取消结果
        """
        try:
            success = await self._client.cancel_order(symbol, order_id)
            return {"success": success}
            
        except Exception as e:
            logger.error(f"取消订单失败: {e}")
            return {"success": False, "error": str(e)}
    
    async def get_order(self, symbol: str, order_id: str) -> Dict[str, Any]:
        """
        统一获取订单接口
        
        Args:
            symbol: 交易对
            order_id: 订单ID
        
        Returns:
            订单信息
        """
        try:
            order = await self._client.get_order(symbol, order_id)
            if order:
                return self._format_order_response(order)
            else:
                return {"success": False, "error": "订单不存在"}
                
        except Exception as e:
            logger.error(f"获取订单失败: {e}")
            return {"success": False, "error": str(e)}
    
    async def get_open_orders(self, symbol: Optional[str] = None) -> Dict[str, Any]:
        """
        统一获取未成交订单接口
        
        Args:
            symbol: 交易对（可选）
        
        Returns:
            未成交订单列表
        """
        try:
            orders = await self._client.get_open_orders(symbol)
            return {
                "success": True,
                "orders": [self._format_order_response(order) for order in orders]
            }
            
        except Exception as e:
            logger.error(f"获取未成交订单失败: {e}")
            return {"success": False, "error": str(e)}
    
    async def get_positions(self, symbol: Optional[str] = None) -> Dict[str, Any]:
        """
        统一获取持仓接口
        
        Args:
            symbol: 交易对（可选）
        
        Returns:
            持仓列表
        """
        try:
            positions = await self._client.get_positions(symbol)
            return {
                "success": True,
                "positions": [self._format_position(position) for position in positions]
            }
            
        except Exception as e:
            logger.error(f"获取持仓失败: {e}")
            return {"success": False, "error": str(e)}
    
    async def get_balance(self) -> Dict[str, Any]:
        """
        统一获取余额接口
        
        Returns:
            余额列表
        """
        try:
            balances = await self._client.get_balance()
            return {
                "success": True,
                "balances": [self._format_balance(balance) for balance in balances]
            }
            
        except Exception as e:
            logger.error(f"获取余额失败: {e}")
            return {"success": False, "error": str(e)}
    
    async def get_account_info(self) -> Dict[str, Any]:
        """
        获取账户信息（兼容旧接口）
        
        Returns:
            账户信息
        """
        try:
            # 对于OKX，使用get_balance获取账户信息
            if self.exchange == ExchangeType.OKX:
                balances = await self._client.get_balance()
                # 计算总资产（USDT）
                total_usdt = 0
                for balance in balances:
                    if balance.asset == 'USDT':
                        total_usdt += balance.total
                
                return {
                    "success": True,
                    "data": [{
                        "totalEq": str(total_usdt),
                        "details": [self._format_balance(balance) for balance in balances]
                    }]
                }
            else:
                # 其他交易所使用get_balance
                balances = await self._client.get_balance()
                return {
                    "success": True,
                    "data": [self._format_balance(balance) for balance in balances]
                }
                
        except Exception as e:
            logger.error(f"获取账户信息失败: {e}")
            return {"success": False, "error": str(e)}
    
    async def get_ticker(self, symbol: str) -> Dict[str, Any]:
        """
        统一获取行情接口
        
        Args:
            symbol: 交易对
        
        Returns:
            行情信息
        """
        try:
            ticker = await self._client.get_ticker(symbol)
            return {
                "success": True,
                "ticker": self._format_ticker(ticker)
            }
            
        except Exception as e:
            logger.error(f"获取行情失败: {e}")
            return {"success": False, "error": str(e)}
    
    async def get_klines(self, symbol: str, interval: str, 
                        start_time: Optional[int] = None,
                        end_time: Optional[int] = None,
                        limit: int = 500) -> Dict[str, Any]:
        """
        统一获取K线数据接口
        
        Args:
            symbol: 交易对
            interval: 时间间隔
            start_time: 开始时间（毫秒时间戳）
            end_time: 结束时间（毫秒时间戳）
            limit: 返回数量限制
        
        Returns:
            K线数据
        """
        try:
            klines = await self._client.get_klines(symbol, interval, start_time, end_time, limit)
            return {
                "success": True,
                "klines": klines
            }
            
        except Exception as e:
            logger.error(f"获取K线数据失败: {e}")
            return {"success": False, "error": str(e)}
    
    async def get_funding_rate(self, symbol: str) -> Dict[str, Any]:
        """
        统一获取资金费率接口
        
        Returns:
            资金费率信息
        """
        try:
            funding_rate = await self._client.get_funding_rate(symbol)
            return {
                "success": True,
                "funding_rate": self._format_funding_rate(funding_rate)
            }
            
        except Exception as e:
            logger.error(f"获取资金费率失败: {e}")
            return {"success": False, "error": str(e)}
    
    async def get_open_interest(self, symbol: str) -> Dict[str, Any]:
        """
        统一获取持仓量接口
        
        Returns:
            持仓量信息
        """
        try:
            open_interest = await self._client.get_open_interest(symbol)
            return {
                "success": True,
                "open_interest": self._format_open_interest(open_interest)
            }
            
        except Exception as e:
            logger.error(f"获取持仓量失败: {e}")
            return {"success": False, "error": str(e)}
    
    async def get_mark_price(self, symbol: str) -> Dict[str, Any]:
        """
        统一获取标记价格接口
        
        Returns:
            标记价格信息
        """
        try:
            mark_price = await self._client.get_mark_price(symbol)
            return {
                "success": True,
                "mark_price": self._format_mark_price(mark_price)
            }
            
        except Exception as e:
            logger.error(f"获取标记价格失败: {e}")
            return {"success": False, "error": str(e)}
    
    async def get_liquidation_orders(self, symbol: Optional[str] = None, limit: int = 100) -> Dict[str, Any]:
        """
        统一获取强平订单接口
        
        Returns:
            强平订单列表
        """
        try:
            liquidation_orders = await self._client.get_liquidation_orders(symbol, limit)
            return {
                "success": True,
                "liquidation_orders": [self._format_liquidation_order(order) for order in liquidation_orders]
            }
            
        except Exception as e:
            logger.error(f"获取强平订单失败: {e}")
            return {"success": False, "error": str(e)}
    
    async def get_trade_fee(self, symbol: str, category: str = "spot") -> Dict[str, Any]:
        """
        统一获取交易手续费接口
        
        Returns:
            交易手续费信息
        """
        try:
            trade_fee = await self._client.get_trade_fee(symbol, category)
            return {
                "success": True,
                "trade_fee": self._format_trade_fee(trade_fee)
            }
            
        except Exception as e:
            logger.error(f"获取交易手续费失败: {e}")
            return {"success": False, "error": str(e)}
    
    async def get_margin_balance(self, asset: Optional[str] = None) -> Dict[str, Any]:
        """
        统一获取保证金余额接口
        
        Returns:
            保证金余额列表
        """
        try:
            margin_balances = await self._client.get_margin_balance(asset)
            return {
                "success": True,
                "margin_balances": [self._format_margin_balance(balance) for balance in margin_balances]
            }
            
        except Exception as e:
            logger.error(f"获取保证金余额失败: {e}")
            return {"success": False, "error": str(e)}
    
    async def get_instruments(self, inst_type: str = "SPOT") -> Dict[str, Any]:
        """
        统一获取交易产品基础信息接口
        
        Returns:
            交易产品列表
        """
        try:
            instruments = await self._client.get_instruments(inst_type)
            return {
                "success": True,
                "instruments": [self._format_instrument(instrument) for instrument in instruments]
            }
            
        except Exception as e:
            logger.error(f"获取交易产品信息失败: {e}")
            return {"success": False, "error": str(e)}
    
    async def get_bill_details(self, asset: Optional[str] = None, limit: int = 100) -> Dict[str, Any]:
        """
        统一获取账单详情接口
        
        Returns:
            账单详情列表
        """
        try:
            bill_details = await self._client.get_bill_details(asset, limit)
            return {
                "success": True,
                "bill_details": [self._format_bill_detail(bill) for bill in bill_details]
            }
            
        except Exception as e:
            logger.error(f"获取账单详情失败: {e}")
            return {"success": False, "error": str(e)}
    
    def _format_order_response(self, order: OrderResponse) -> Dict[str, Any]:
        """格式化订单响应"""
        return {
            "order_id": order.order_id,
            "client_order_id": order.client_order_id,
            "symbol": order.symbol,
            "side": order.side.value,
            "order_type": order.order_type.value,
            "quantity": order.quantity,
            "price": order.price,
            "status": order.status.value,
            "filled_quantity": order.filled_quantity,
            "remaining_quantity": order.remaining_quantity,
            "timestamp": order.timestamp,
            "exchange": order.exchange.value if order.exchange else self.exchange.value
        }
    
    def _format_position(self, position: Position) -> Dict[str, Any]:
        """格式化持仓信息"""
        return {
            "symbol": position.symbol,
            "side": position.side,
            "size": position.size,
            "entry_price": position.entry_price,
            "mark_price": position.mark_price,
            "unrealized_pnl": position.unrealized_pnl,
            "margin": position.margin,
            "leverage": position.leverage,
            "exchange": position.exchange.value if position.exchange else self.exchange.value
        }
    
    def _format_balance(self, balance: Balance) -> Dict[str, Any]:
        """格式化余额信息"""
        return {
            "asset": balance.asset,
            "free": balance.free,
            "locked": balance.locked,
            "total": balance.total,
            "exchange": balance.exchange.value if balance.exchange else self.exchange.value
        }
    
    def _format_ticker(self, ticker: Ticker) -> Dict[str, Any]:
        """格式化行情信息"""
        return {
            "symbol": ticker.symbol,
            "price": ticker.price,
            "volume": ticker.volume,
            "timestamp": ticker.timestamp,
            "exchange": ticker.exchange.value if ticker.exchange else self.exchange.value,
            "bid_price": ticker.bid_price,
            "ask_price": ticker.ask_price,
            "high_24h": ticker.high_24h,
            "low_24h": ticker.low_24h,
            "change_24h": ticker.change_24h,
            "change_percent_24h": ticker.change_percent_24h
        }
    
    def _format_funding_rate(self, funding_rate: FundingRate) -> Dict[str, Any]:
        """格式化资金费率数据"""
        return {
            "symbol": funding_rate.symbol,
            "funding_rate": funding_rate.funding_rate,
            "funding_time": funding_rate.funding_time,
            "next_funding_time": funding_rate.next_funding_time,
            "exchange": funding_rate.exchange.value
        }
    
    def _format_open_interest(self, open_interest: OpenInterest) -> Dict[str, Any]:
        """格式化持仓量数据"""
        return {
            "symbol": open_interest.symbol,
            "open_interest": open_interest.open_interest,
            "timestamp": open_interest.timestamp,
            "exchange": open_interest.exchange.value
        }
    
    def _format_mark_price(self, mark_price: MarkPrice) -> Dict[str, Any]:
        """格式化标记价格数据"""
        return {
            "symbol": mark_price.symbol,
            "mark_price": mark_price.mark_price,
            "index_price": mark_price.index_price,
            "timestamp": mark_price.timestamp,
            "exchange": mark_price.exchange.value
        }
    
    def _format_liquidation_order(self, order: LiquidationOrder) -> Dict[str, Any]:
        """格式化强平订单数据"""
        return {
            "symbol": order.symbol,
            "side": order.side.value,
            "size": order.size,
            "price": order.price,
            "timestamp": order.timestamp,
            "exchange": order.exchange.value
        }
    
    def _format_trade_fee(self, trade_fee: TradeFee) -> Dict[str, Any]:
        """格式化交易手续费数据"""
        return {
            "symbol": trade_fee.symbol,
            "maker_fee": trade_fee.maker_fee,
            "taker_fee": trade_fee.taker_fee,
            "category": trade_fee.category,
            "exchange": trade_fee.exchange.value
        }
    
    def _format_margin_balance(self, balance: MarginBalance) -> Dict[str, Any]:
        """格式化保证金余额数据"""
        return {
            "asset": balance.asset,
            "total": balance.total,
            "available": balance.available,
            "frozen": balance.frozen,
            "borrowed": balance.borrowed,
            "interest": balance.interest,
            "exchange": balance.exchange.value
        }
    
    def _format_instrument(self, instrument: Instrument) -> Dict[str, Any]:
        """格式化交易产品数据"""
        return {
            "symbol": instrument.symbol,
            "base_asset": instrument.base_asset,
            "quote_asset": instrument.quote_asset,
            "min_qty": instrument.min_qty,
            "max_qty": instrument.max_qty,
            "step_size": instrument.step_size,
            "min_notional": instrument.min_notional,
            "status": instrument.status,
            "exchange": instrument.exchange.value
        }
    
    def _format_bill_detail(self, bill: BillDetail) -> Dict[str, Any]:
        """格式化账单详情数据"""
        return {
            "bill_id": bill.bill_id,
            "asset": bill.asset,
            "amount": bill.amount,
            "fee": bill.fee,
            "bill_type": bill.bill_type,
            "timestamp": bill.timestamp,
            "exchange": bill.exchange.value if bill.exchange else None
        }
    
    def get_exchange_type(self) -> str:
        """获取交易所类型"""
        return self.exchange.value
    
    def is_demo_mode(self) -> bool:
        """检查是否为演示模式"""
        return self.is_demo
    
    async def get_historical_klines(self, symbol: str, interval: str, 
                                  start_time: int = None, end_time: int = None, 
                                  limit: int = 100) -> List:
        """获取历史K线数据"""
        return await self._client.get_historical_klines(
            symbol, interval, start_time, end_time, limit
        )


# 便捷函数
def create_unified_rest_client(exchange: str, api_key: str, api_secret: str,
                             passphrase: str = None, is_demo: bool = True) -> UnifiedRESTClient:
    """
    创建统一REST客户端的便捷函数
    
    Args:
        exchange: 交易所名称 ('okx', 'binance', 'bybit')
        api_key: API密钥
        api_secret: API密钥
        passphrase: 密码短语（仅OKX需要）
        is_demo: 是否使用演示模式
    
    Returns:
        统一REST客户端实例
    """
    try:
        exchange_type = ExchangeType(exchange.lower())
    except ValueError:
        raise ValueError(f"不支持的交易所: {exchange}")
    
    return UnifiedRESTClient(exchange_type, api_key, api_secret, passphrase, is_demo)
