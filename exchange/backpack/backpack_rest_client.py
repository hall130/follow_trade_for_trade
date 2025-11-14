"""
Backpack交易所REST客户端
适配当前项目的统一接口架构
"""
import json
import time
import requests
from typing import Dict, Any, Optional, List, Tuple, Iterable
from ..base_client import BaseRESTClient, ExchangeType, OrderRequest, OrderResponse, OrderSide, OrderType, OrderStatus
from ..base_client import Position, Balance, Ticker, Instrument
from .backpack_auth import create_signature
from utils.logger import logger


class BackpackRESTClient(BaseRESTClient):
    """Backpack交易所REST客户端"""
    
    API_URL = "https://api.backpack.work"
    API_VERSION = "v1"
    DEFAULT_WINDOW = "5000"
    
    def __init__(self, api_key: str, api_secret: str, passphrase: str = None, is_demo: bool = True, base_url: str = None):
        """
        初始化Backpack客户端
        
        Args:
            api_key: API密钥
            api_secret: API密钥（base64编码）
            passphrase: 密码短语（Backpack不需要，保留兼容性）
            is_demo: 是否演示模式
            base_url: API基础URL
        """
        super().__init__(api_key, api_secret, passphrase, is_demo)
        self.base_url = base_url or self.API_URL
        self.api_version = self.API_VERSION
        self.default_window = self.DEFAULT_WINDOW
    
    def _get_exchange_type(self) -> ExchangeType:
        """获取交易所类型"""
        # 如果ExchangeType没有BACKPACK，需要添加
        # 暂时返回一个值，后续需要扩展ExchangeType枚举
        return ExchangeType.OKX  # 临时使用，需要扩展
    
    def _make_request(self, method: str, endpoint: str, instruction: str = None,
                     params: Dict = None, data: Dict = None, retry_count: int = 3) -> Dict:
        """
        执行API请求，支持重试机制
        
        Args:
            method: HTTP方法 (GET, POST, DELETE)
            endpoint: API端点
            instruction: API指令
            params: 查询参数
            data: 请求体数据
            retry_count: 重试次数
            
        Returns:
            API响应数据
        """
        url = f"{self.base_url}{endpoint}"
        headers = {
            'Content-Type': 'application/json',
            'X-Broker-Id': '1500'
        }
        
        # 构建签名信息（如需要）
        if self.api_key and self.api_secret and instruction:
            timestamp = str(int(time.time() * 1000))
            window = self.default_window
            
            # 构建签名消息
            query_string = ""
            if params:
                sorted_params = sorted(params.items())
                query_string = "&".join([f"{k}={v}" for k, v in sorted_params])
            
            sign_message = f"instruction={instruction}"
            if query_string:
                sign_message += f"&{query_string}"
            sign_message += f"&timestamp={timestamp}&window={window}"
            
            signature = create_signature(self.api_secret, sign_message)
            if not signature:
                return {"error": "签名创建失败"}
            
            headers.update({
                'X-API-KEY': self.api_key,
                'X-SIGNATURE': signature,
                'X-TIMESTAMP': timestamp,
                'X-WINDOW': window
            })
        
        # 添加查询参数到URL
        if params and method.upper() in ['GET', 'DELETE']:
            query_string = "&".join([f"{k}={v}" for k, v in params.items()])
            url += f"?{query_string}"
        
        # 实施重试机制
        for attempt in range(retry_count):
            try:
                if method.upper() == 'GET':
                    response = requests.get(url, headers=headers, timeout=10)
                elif method.upper() == 'POST':
                    response = requests.post(url, headers=headers, data=json.dumps(data) if data else None, timeout=10)
                elif method.upper() == 'DELETE':
                    response = requests.delete(url, headers=headers, data=json.dumps(data) if data else None, timeout=10)
                else:
                    return {"error": f"不支持的请求方法: {method}"}
                
                # 处理响应
                if response.status_code in [200, 201]:
                    return response.json() if response.text.strip() else {}
                elif response.status_code == 429:  # 速率限制
                    wait_time = 1 * (2 ** attempt)  # 指数退避
                    logger.warning(f"遇到速率限制，等待 {wait_time} 秒后重试")
                    time.sleep(wait_time)
                    continue
                else:
                    error_msg = f"状态码: {response.status_code}, 消息: {response.text}"
                    if attempt < retry_count - 1:
                        logger.warning(f"请求失败 ({attempt+1}/{retry_count}): {error_msg}")
                        time.sleep(1)
                        continue
                    return {"error": error_msg}
            
            except requests.exceptions.Timeout:
                if attempt < retry_count - 1:
                    logger.warning(f"请求超时 ({attempt+1}/{retry_count})，重试中...")
                    continue
                return {"error": "请求超时"}
            except requests.exceptions.ConnectionError:
                if attempt < retry_count - 1:
                    logger.warning(f"连接错误 ({attempt+1}/{retry_count})，重试中...")
                    time.sleep(2)
                    continue
                return {"error": "连接错误"}
            except Exception as e:
                if attempt < retry_count - 1:
                    logger.warning(f"请求异常 ({attempt+1}/{retry_count}): {str(e)}，重试中...")
                    continue
                return {"error": f"请求失败: {str(e)}"}
        
        return {"error": "达到最大重试次数"}
    
    async def place_order(self, order_request: OrderRequest) -> OrderResponse:
        """下单"""
        endpoint = f"/api/{self.api_version}/order"
        instruction = "orderExecute"
        
        # 构建订单详情
        order_details = {
            "symbol": order_request.symbol,
            "side": order_request.side.value.upper(),
            "orderType": order_request.order_type.value.upper(),
            "quantity": str(order_request.quantity),
        }
        
        if order_request.price:
            order_details["price"] = str(order_request.price)
        if order_request.client_order_id:
            order_details["clientId"] = order_request.client_order_id
        
        # 构建签名参数
        params = {}
        for key, value in order_details.items():
            if value is None:
                continue
            if isinstance(value, bool):
                params[key] = str(value).lower()
            else:
                params[key] = str(value)
        
        result = self._make_request("POST", endpoint, instruction, params, order_details)
        
        if "error" in result:
            logger.error(f"下单失败: {result['error']}")
            return OrderResponse(
                order_id="",
                client_order_id=order_request.client_order_id,
                symbol=order_request.symbol,
                side=order_request.side,
                order_type=order_request.order_type,
                quantity=order_request.quantity,
                price=order_request.price,
                status=OrderStatus.REJECTED,
                exchange=self.exchange_type
            )
        
        # 解析响应
        order_id = result.get("id") or result.get("orderId") or ""
        
        return OrderResponse(
            order_id=order_id,
            client_order_id=order_request.client_order_id,
            symbol=order_request.symbol,
            side=order_request.side,
            order_type=order_request.order_type,
            quantity=order_request.quantity,
            price=order_request.price,
            status=OrderStatus.PENDING,
            exchange=self.exchange_type
        )
    
    async def cancel_order(self, symbol: str, order_id: str) -> bool:
        """取消订单"""
        endpoint = f"/api/{self.api_version}/order"
        instruction = "orderCancel"
        params = {"orderId": order_id, "symbol": symbol}
        data = {"orderId": order_id, "symbol": symbol}
        
        result = self._make_request("DELETE", endpoint, instruction, params, data)
        return "error" not in result
    
    async def get_order(self, symbol: str, order_id: str) -> Optional[OrderResponse]:
        """获取订单信息"""
        endpoint = f"/api/{self.api_version}/order"
        instruction = "orderQuery"
        params = {"orderId": order_id, "symbol": symbol}
        
        result = self._make_request("GET", endpoint, instruction, params)
        
        if "error" in result:
            return None
        
        # 解析订单信息
        # 根据实际API响应格式解析
        return None  # TODO: 实现订单信息解析
    
    async def get_open_orders(self, symbol: Optional[str] = None) -> List[OrderResponse]:
        """获取未成交订单"""
        endpoint = f"/api/{self.api_version}/orders"
        instruction = "orderQueryAll"
        params = {}
        if symbol:
            params["symbol"] = symbol
        
        result = self._make_request("GET", endpoint, instruction, params)
        
        if "error" in result:
            return []
        
        # 解析订单列表
        orders = []
        # TODO: 实现订单列表解析
        return orders
    
    async def get_positions(self, symbol: Optional[str] = None) -> List[Position]:
        """获取持仓信息"""
        endpoint = f"/api/{self.api_version}/position"
        instruction = "positionQuery"
        params = {}
        if symbol:
            params["symbol"] = symbol
        
        result = self._make_request("GET", endpoint, instruction, params, retry_count=1)
        
        # 特殊处理404错误 - 对于持仓查询，404表示没有持仓
        if isinstance(result, dict) and "error" in result:
            error_msg = result["error"]
            if "404" in error_msg or "RESOURCE_NOT_FOUND" in error_msg:
                return []
        
        # 解析持仓信息
        positions = []
        # TODO: 实现持仓信息解析
        return positions
    
    async def get_balance(self) -> List[Balance]:
        """获取账户余额"""
        endpoint = f"/api/{self.api_version}/capital"
        instruction = "balanceQuery"
        
        result = self._make_request("GET", endpoint, instruction)
        
        if "error" in result:
            return []
        
        # 解析余额信息
        balances = []
        if isinstance(result, dict):
            for asset, details in result.items():
                if isinstance(details, dict):
                    available = float(details.get('available', 0))
                    locked = float(details.get('locked', 0))
                    balances.append(Balance(
                        asset=asset,
                        free=available,
                        locked=locked,
                        total=available + locked,
                        exchange=self.exchange_type
                    ))
        
        return balances
    
    def get_collateral(self, subaccount_id: Optional[str] = None) -> Dict:
        """获取抵押品余额"""
        endpoint = f"/api/{self.api_version}/capital/collateral"
        params = {}
        if subaccount_id is not None:
            params["subaccountId"] = str(subaccount_id)
        instruction = "collateralQuery" if self.api_key and self.api_secret else None
        return self._make_request("GET", endpoint, instruction, params)
    
    async def get_ticker(self, symbol: str) -> Ticker:
        """获取行情信息"""
        endpoint = f"/api/{self.api_version}/ticker"
        params = {"symbol": symbol}
        response = self._make_request("GET", endpoint, params=params)
        
        if "error" in response:
            raise Exception(f"获取行情失败: {response['error']}")
        
        parsed = self._parse_ticker_snapshot(response)
        if not parsed:
            raise Exception("无法解析ticker数据")
        
        return Ticker(
            symbol=symbol,
            price=float(parsed.get("lastPrice", parsed.get("price", 0))),
            volume=float(parsed.get("volume", 0)),
            timestamp=int(time.time() * 1000),
            exchange=self.exchange_type,
            bid_price=float(parsed.get("bidPrice", 0)),
            ask_price=float(parsed.get("askPrice", 0))
        )
    
    def get_order_book(self, symbol: str, limit: int = 20) -> Dict:
        """获取市场深度"""
        endpoint = f"/api/{self.api_version}/depth"
        params = {"symbol": symbol, "limit": str(limit)}
        response = self._make_request("GET", endpoint, params=params)
        
        if "error" in response:
            return response
        
        bids, asks = self._parse_order_book_snapshot(response)
        result = {
            "bids": bids,
            "asks": asks,
        }
        
        timestamp = self._extract_from_payload(response, ("ts", "timestamp", "time"))
        if timestamp is not None:
            result["timestamp"] = timestamp
        
        sequence = self._extract_from_payload(response, ("sequence", "seq", "lastUpdateId"))
        if sequence is not None:
            result["sequence"] = sequence
        
        symbol_value = self._extract_from_payload(response, ("symbol", "s"))
        if symbol_value:
            result["symbol"] = symbol_value
        
        return result
    
    def get_markets(self) -> List[Dict]:
        """获取所有交易对信息"""
        endpoint = f"/api/{self.api_version}/markets"
        return self._make_request("GET", endpoint) or []
    
    def get_market_limits(self, symbol: str) -> Optional[Dict]:
        """获取交易对的最低订单量和价格精度"""
        markets_info = self.get_markets()
        
        if isinstance(markets_info, list):
            for market_info in markets_info:
                if market_info.get('symbol') == symbol:
                    base_asset = market_info.get('baseSymbol')
                    quote_asset = market_info.get('quoteSymbol')
                    
                    filters = market_info.get('filters', {})
                    base_precision = 8
                    quote_precision = 8
                    min_order_size = "0"
                    tick_size = "0.00000001"
                    
                    if 'price' in filters:
                        tick_size = filters['price'].get('tickSize', '0.00000001')
                        quote_precision = len(tick_size.split('.')[-1]) if '.' in tick_size else 0
                    
                    if 'quantity' in filters:
                        min_order_size = filters['quantity'].get('minQuantity', '0')
                        min_value = filters['quantity'].get('minQuantity', '0.00000001')
                        base_precision = len(min_value.split('.')[-1]) if '.' in min_value else 0
                    
                    return {
                        'base_asset': base_asset,
                        'quote_asset': quote_asset,
                        'base_precision': base_precision,
                        'quote_precision': quote_precision,
                        'min_order_size': min_order_size,
                        'tick_size': tick_size
                    }
        
        logger.error(f"找不到交易对 {symbol} 的信息")
        return None
    
    def get_fill_history(self, symbol: Optional[str] = None, limit: int = 100) -> Dict:
        """获取历史成交记录"""
        endpoint = f"/wapi/{self.api_version}/history/fills"
        instruction = "fillHistoryQueryAll"
        params = {"limit": str(limit)}
        if symbol:
            params["symbol"] = symbol
        return self._make_request("GET", endpoint, instruction, params)
    
    def cancel_all_orders(self, symbol: str) -> bool:
        """取消所有订单"""
        endpoint = f"/api/{self.api_version}/orders"
        instruction = "orderCancelAll"
        params = {"symbol": symbol}
        data = {"symbol": symbol}
        result = self._make_request("DELETE", endpoint, instruction, params, data)
        return "error" not in result
    
    # 辅助方法
    @staticmethod
    def _extract_from_payload(payload: Dict[str, Any], keys: Iterable[str]) -> Optional[Any]:
        """从payload中提取指定键的值"""
        data = payload.get("data") if isinstance(payload, dict) else None
        for key in keys:
            if isinstance(payload, dict) and key in payload and payload[key] not in (None, ""):
                return payload[key]
            if isinstance(data, dict) and key in data and data[key] not in (None, ""):
                return data[key]
        return None
    
    @classmethod
    def _parse_order_book_snapshot(cls, payload: Dict[str, Any]) -> Tuple[List[List[float]], List[List[float]]]:
        """解析订单簿数据"""
        if not isinstance(payload, dict):
            return [], []
        
        data = payload.get("data", payload)
        bids_raw = data.get("bids", []) or []
        asks_raw = data.get("asks", []) or []
        
        def _normalise_level(level: Any) -> Optional[List[float]]:
            if isinstance(level, dict):
                price = cls._extract_from_payload(level, ("price", "px", "p"))
                quantity = cls._extract_from_payload(level, ("size", "quantity", "q", "sz"))
            elif isinstance(level, (list, tuple)) and len(level) >= 2:
                price, quantity = level[0], level[1]
            else:
                return None
            
            try:
                return [float(price), float(quantity)]
            except (TypeError, ValueError):
                return None
        
        bids = [item for item in (_normalise_level(level) for level in bids_raw) if item]
        asks = [item for item in (_normalise_level(level) for level in asks_raw) if item]
        
        bids.sort(key=lambda x: x[0], reverse=True)
        asks.sort(key=lambda x: x[0])
        return bids, asks
    
    @classmethod
    def _parse_ticker_snapshot(cls, payload: Dict[str, Any]) -> Dict[str, Optional[str]]:
        """解析ticker响应"""
        if not isinstance(payload, dict):
            return {}
        
        data = payload.get("data", payload)
        
        def _safe_float(value: Any) -> Optional[float]:
            try:
                return float(value)
            except (TypeError, ValueError):
                return None
        
        bid = _safe_float(cls._extract_from_payload(data, ("bidPrice", "bestBidPrice", "bid", "bestBid", "buy")))
        ask = _safe_float(cls._extract_from_payload(data, ("askPrice", "bestAskPrice", "ask", "bestAsk", "sell")))
        last = _safe_float(cls._extract_from_payload(data, ("lastPrice", "price", "last", "close", "markPrice")))
        
        result: Dict[str, Optional[str]] = {}
        if bid is not None:
            result["bidPrice"] = f"{bid}"
            result["bestBidPrice"] = result["bidPrice"]
        if ask is not None:
            result["askPrice"] = f"{ask}"
            result["bestAskPrice"] = result["askPrice"]
        if last is not None:
            result["lastPrice"] = f"{last}"
            result["price"] = result["lastPrice"]
        
        volume = cls._extract_from_payload(data, ("volume", "baseVolume", "quoteVolume"))
        if volume is not None:
            result["volume"] = str(volume)
        
        return result
    
    # 实现其他必需的抽象方法（简化实现）
    async def get_klines(self, symbol: str, interval: str, start_time: Optional[int] = None, 
                        end_time: Optional[int] = None, limit: int = 500) -> List[List]:
        """获取K线数据"""
        endpoint = f"/api/{self.api_version}/klines"
        current_time = int(time.time())
        
        interval_seconds = {
            "1m": 60, "3m": 180, "5m": 300, "15m": 900, "30m": 1800,
            "1h": 3600, "2h": 7200, "4h": 14400, "6h": 21600, "8h": 28800,
            "12h": 43200, "1d": 86400, "3d": 259200, "1w": 604800, "1month": 2592000
        }
        
        duration = interval_seconds.get(interval, 3600)
        start = start_time or (current_time - (duration * limit))
        
        params = {
            "symbol": symbol,
            "interval": interval,
            "startTime": str(start)
        }
        
        result = self._make_request("GET", endpoint, params=params)
        return result.get("data", []) if isinstance(result, dict) else []
    
    async def get_funding_rate(self, symbol: str):
        """获取资金费率（Backpack可能不支持）"""
        raise NotImplementedError("Backpack不支持资金费率查询")
    
    async def get_open_interest(self, symbol: str):
        """获取持仓量（Backpack可能不支持）"""
        raise NotImplementedError("Backpack不支持持仓量查询")
    
    async def get_mark_price(self, symbol: str):
        """获取标记价格"""
        # 使用ticker价格作为标记价格
        ticker = await self.get_ticker(symbol)
        return ticker.price
    
    async def get_liquidation_orders(self, symbol: Optional[str] = None, limit: int = 100):
        """获取强平订单（Backpack可能不支持）"""
        raise NotImplementedError("Backpack不支持强平订单查询")
    
    async def get_trade_fee(self, symbol: str, category: str = "spot"):
        """获取交易手续费"""
        # Backpack可能不提供此API，返回默认值
        from ..base_client import TradeFee
        return TradeFee(
            symbol=symbol,
            maker_fee=0.001,  # 默认值
            taker_fee=0.001,
            category=category,
            exchange=self.exchange_type
        )
    
    async def get_margin_balance(self, asset: Optional[str] = None):
        """获取保证金余额"""
        collateral = self.get_collateral()
        # TODO: 转换为MarginBalance格式
        return []
    
    async def get_instruments(self, inst_type: str = "SPOT"):
        """获取交易产品基础信息"""
        markets = self.get_markets()
        instruments = []
        for market in markets:
            if market.get('status') == 'TRADING':
                instruments.append(Instrument(
                    symbol=market.get('symbol'),
                    base_asset=market.get('baseSymbol'),
                    quote_asset=market.get('quoteSymbol'),
                    min_qty=float(market.get('filters', {}).get('quantity', {}).get('minQuantity', 0)),
                    max_qty=float(market.get('filters', {}).get('quantity', {}).get('maxQuantity', 0)),
                    step_size=float(market.get('filters', {}).get('quantity', {}).get('stepSize', 0)),
                    min_notional=float(market.get('filters', {}).get('notional', {}).get('minNotional', 0)),
                    status=market.get('status', 'UNKNOWN'),
                    exchange=self.exchange_type
                ))
        return instruments
    
    async def get_bill_details(self, asset: Optional[str] = None, limit: int = 100):
        """获取账单详情"""
        fills = self.get_fill_history(None, limit)
        # TODO: 转换为BillDetail格式
        return []

