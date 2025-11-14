"""
Backpack WebSocket客户端
适配当前项目的统一接口架构
"""
import json
import time
import threading
from collections import deque
from typing import Dict, Any, Optional, Callable
import websocket as ws
from urllib.parse import urlparse
from ..base_client import BaseWebSocketClient, ExchangeType
from .backpack_rest_client import BackpackRESTClient
from .backpack_auth import create_signature
from utils.logger import logger


class BackpackWebSocketClient(BaseWebSocketClient):
    """Backpack WebSocket客户端"""
    
    WS_URL = "wss://ws.backpack.work"
    DEFAULT_WINDOW = "5000"
    
    def __init__(self, api_key: str = None, api_secret: str = None, 
                 passphrase: str = None, is_demo: bool = True, 
                 symbol: str = None, proxy: str = None):
        """
        初始化WebSocket客户端
        
        Args:
            api_key: API密钥
            api_secret: API密钥
            passphrase: 密码短语（Backpack不需要）
            is_demo: 是否演示模式
            symbol: 交易对符号
            proxy: WebSocket代理
        """
        super().__init__(api_key, api_secret, passphrase, is_demo)
        self.symbol = symbol
        self.proxy = proxy
        self.ws = None
        self.connected = False
        self.running = False
        self.ws_thread = None
        self.ws_lock = threading.Lock()
        
        # 价格数据
        self.last_price = None
        self.bid_price = None
        self.ask_price = None
        self.orderbook = {"bids": [], "asks": []}
        self.order_updates = []
        self.historical_prices = deque(maxlen=100)
        
        # 重连相关
        self.auto_reconnect = True
        self.reconnect_delay = 1
        self.max_reconnect_delay = 30
        self.reconnect_attempts = 0
        self.max_reconnect_attempts = 10
        self.reconnecting = False
        
        # 订阅记录
        self.subscriptions = []
        
        # 心跳检测
        self.last_heartbeat = time.time()
        self.heartbeat_interval = 30
        self.heartbeat_thread = None
        
        # REST API备援
        self.api_fallback_thread = None
        self.api_fallback_active = False
        self.api_poll_interval = 2
        self._client_cache = {}
        self._fallback_bootstrapped = False
        self._seen_fill_ids = deque(maxlen=200)
        self._seen_fill_id_set = set()
        self._last_fill_timestamp = 0
    
    def _get_exchange_type(self) -> ExchangeType:
        """获取交易所类型"""
        return ExchangeType.OKX  # 临时使用，需要扩展
    
    def _get_client(self):
        """获取缓存的REST客户端实例"""
        cache_key = "public"
        if cache_key not in self._client_cache:
            self._client_cache[cache_key] = BackpackRESTClient(
                self.api_key or "",
                self.api_secret or "",
                is_demo=self.is_demo,
                base_url="https://api.backpack.work"
            )
        return self._client_cache[cache_key]
    
    async def connect(self) -> bool:
        """建立WebSocket连接"""
        if self.connected:
            return True
        
        try:
            self.running = True
            self.ws_thread = threading.Thread(target=self._run_websocket, daemon=True)
            self.ws_thread.start()
            
            # 等待连接建立
            wait_time = 0
            max_wait = 10
            while not self.connected and wait_time < max_wait:
                time.sleep(0.5)
                wait_time += 0.5
            
            if self.connected:
                logger.info("Backpack WebSocket连接已建立")
                return True
            else:
                logger.warning("WebSocket连接建立超时")
                return False
        except Exception as e:
            logger.error(f"建立WebSocket连接失败: {e}")
            return False
    
    async def disconnect(self) -> bool:
        """断开WebSocket连接"""
        self.running = False
        self.auto_reconnect = False
        
        if self.ws:
            try:
                self.ws.close()
            except:
                pass
        
        if self.ws_thread and self.ws_thread.is_alive():
            self.ws_thread.join(timeout=5)
        
        self.connected = False
        logger.info("Backpack WebSocket连接已断开")
        return True
    
    def _run_websocket(self):
        """运行WebSocket连接（在独立线程中）"""
        while self.running:
            try:
                # 构建WebSocket URL
                ws_url = self.WS_URL
                
                # 设置代理
                http_proxy_host = None
                http_proxy_port = None
                if self.proxy:
                    parsed = urlparse(self.proxy)
                    http_proxy_host = parsed.hostname
                    http_proxy_port = parsed.port
                
                # 创建WebSocket连接
                self.ws = ws.WebSocketApp(
                    ws_url,
                    on_message=self._on_message,
                    on_error=self._on_error,
                    on_close=self._on_close,
                    on_open=self._on_open
                )
                
                # 运行WebSocket
                self.ws.run_forever(
                    http_proxy_host=http_proxy_host,
                    http_proxy_port=http_proxy_port,
                    ping_interval=20,
                    ping_timeout=10
                )
                
                # 如果断开连接且需要重连
                if self.running and self.auto_reconnect and not self.reconnecting:
                    self._reconnect()
                
            except Exception as e:
                logger.error(f"WebSocket运行异常: {e}")
                if self.running and self.auto_reconnect:
                    self._reconnect()
                else:
                    break
    
    def _on_open(self, ws):
        """WebSocket连接打开回调"""
        logger.info("WebSocket连接已打开")
        self.connected = True
        self.reconnect_attempts = 0
        
        # 如果已配置交易对，自动订阅
        if self.symbol:
            self.initialize_orderbook()
            self.subscribe_depth()
            self.subscribe_bookTicker()
            self.subscribe_order_updates()
    
    def _on_message(self, ws, message):
        """WebSocket消息回调"""
        try:
            data = json.loads(message)
            self._handle_message(data)
        except Exception as e:
            logger.error(f"处理WebSocket消息失败: {e}")
    
    def _on_error(self, ws, error):
        """WebSocket错误回调"""
        logger.error(f"WebSocket错误: {error}")
        self.connected = False
    
    def _on_close(self, ws, close_status_code, close_msg):
        """WebSocket关闭回调"""
        logger.warning(f"WebSocket连接已关闭: {close_status_code}, {close_msg}")
        self.connected = False
    
    def _handle_message(self, data: Dict):
        """处理WebSocket消息"""
        if not isinstance(data, dict):
            return
        
        # 处理不同类型的消息
        event_type = data.get("e") or data.get("event")
        
        if event_type == "depth":
            self._handle_depth_update(data)
        elif event_type == "bookTicker" or event_type == "ticker":
            self._handle_ticker_update(data)
        elif event_type == "orderFill" or event_type == "fill":
            self._handle_order_fill(data)
        elif event_type == "orderUpdate":
            self._handle_order_update(data)
    
    def _handle_depth_update(self, data: Dict):
        """处理深度更新"""
        bids = data.get("b", [])
        asks = data.get("a", [])
        
        if bids:
            self.orderbook["bids"] = [[float(p), float(q)] for p, q in bids]
            if self.orderbook["bids"]:
                self.bid_price = self.orderbook["bids"][0][0]
        
        if asks:
            self.orderbook["asks"] = [[float(p), float(q)] for p, q in asks]
            if self.orderbook["asks"]:
                self.ask_price = self.orderbook["asks"][0][0]
    
    def _handle_ticker_update(self, data: Dict):
        """处理行情更新"""
        bid = data.get("b") or data.get("bidPrice")
        ask = data.get("a") or data.get("askPrice")
        price = data.get("p") or data.get("lastPrice")
        
        if bid:
            self.bid_price = float(bid)
        if ask:
            self.ask_price = float(ask)
        if price:
            self.last_price = float(price)
            self.add_price_to_history(self.last_price)
    
    def _handle_order_fill(self, data: Dict):
        """处理订单成交"""
        self.order_updates.append(data)
        # 触发回调
        if hasattr(self, '_callbacks') and 'order_fill' in self._callbacks:
            for callback in self._callbacks['order_fill']:
                try:
                    callback(data)
                except Exception as e:
                    logger.error(f"订单成交回调执行失败: {e}")
    
    def _handle_order_update(self, data: Dict):
        """处理订单更新"""
        self.order_updates.append(data)
    
    def add_price_to_history(self, price: float):
        """添加价格到历史记录"""
        self.historical_prices.append(price)
    
    def initialize_orderbook(self) -> bool:
        """初始化订单簿"""
        try:
            client = self._get_client()
            orderbook = client.get_order_book(self.symbol, 50)
            
            if "error" not in orderbook:
                self.orderbook["bids"] = orderbook.get("bids", [])
                self.orderbook["asks"] = orderbook.get("asks", [])
                
                if self.orderbook["bids"]:
                    self.bid_price = self.orderbook["bids"][0][0]
                if self.orderbook["asks"]:
                    self.ask_price = self.orderbook["asks"][0][0]
                
                return True
        except Exception as e:
            logger.error(f"初始化订单簿失败: {e}")
        return False
    
    def subscribe_depth(self) -> bool:
        """订阅深度数据"""
        if not self.connected or not self.ws:
            return False
        
        try:
            subscribe_msg = {
                "method": "subscribe",
                "params": [f"depth.{self.symbol}"]
            }
            self.ws.send(json.dumps(subscribe_msg))
            self.subscriptions.append(f"depth.{self.symbol}")
            return True
        except Exception as e:
            logger.error(f"订阅深度数据失败: {e}")
            return False
    
    def subscribe_bookTicker(self) -> bool:
        """订阅行情数据"""
        if not self.connected or not self.ws:
            return False
        
        try:
            subscribe_msg = {
                "method": "subscribe",
                "params": [f"bookTicker.{self.symbol}"]
            }
            self.ws.send(json.dumps(subscribe_msg))
            self.subscriptions.append(f"bookTicker.{self.symbol}")
            return True
        except Exception as e:
            logger.error(f"订阅行情数据失败: {e}")
            return False
    
    def subscribe_order_updates(self) -> bool:
        """订阅订单更新"""
        if not self.connected or not self.ws or not self.api_key:
            return False
        
        try:
            # Backpack需要认证订阅
            timestamp = str(int(time.time() * 1000))
            window = self.DEFAULT_WINDOW
            message = f"instruction=orderSubscribe&timestamp={timestamp}&window={window}"
            signature = create_signature(self.api_secret, message)
            
            subscribe_msg = {
                "method": "subscribe",
                "params": ["orderUpdates"],
                "id": timestamp,
                "apiKey": self.api_key,
                "signature": signature,
                "timestamp": timestamp,
                "window": window
            }
            self.ws.send(json.dumps(subscribe_msg))
            self.subscriptions.append("orderUpdates")
            return True
        except Exception as e:
            logger.error(f"订阅订单更新失败: {e}")
            return False
    
    def _reconnect(self):
        """重连WebSocket"""
        if self.reconnecting:
            return
        
        self.reconnecting = True
        self.reconnect_attempts += 1
        
        if self.reconnect_attempts > self.max_reconnect_attempts:
            logger.error("达到最大重连次数，停止重连")
            self.running = False
            self.reconnecting = False
            return
        
        wait_time = min(self.reconnect_delay * (2 ** (self.reconnect_attempts - 1)), 
                       self.max_reconnect_delay)
        logger.info(f"等待 {wait_time} 秒后重连... (尝试 {self.reconnect_attempts}/{self.max_reconnect_attempts})")
        time.sleep(wait_time)
        
        self.reconnecting = False
        self.connected = False
    
    def close(self):
        """关闭连接"""
        self.running = False
        self.auto_reconnect = False
        if self.ws:
            try:
                self.ws.close()
            except:
                pass
    
    # 实现BaseWebSocketClient的抽象方法
    async def subscribe_ticker(self, symbol: str, callback) -> bool:
        """订阅行情数据"""
        self.symbol = symbol
        if self.connected:
            return self.subscribe_bookTicker()
        return False
    
    async def subscribe_orderbook(self, symbol: str, callback) -> bool:
        """订阅深度数据"""
        self.symbol = symbol
        if self.connected:
            return self.subscribe_depth()
        return False
    
    async def subscribe_trades(self, symbol: str, callback) -> bool:
        """订阅交易数据"""
        # Backpack可能不支持，使用订单更新代替
        return await self.subscribe_orders(callback)
    
    async def subscribe_orders(self, callback) -> bool:
        """订阅订单更新"""
        if 'order_fill' not in self._callbacks:
            self._callbacks['order_fill'] = []
        self._callbacks['order_fill'].append(callback)
        return self.subscribe_order_updates()
    
    async def subscribe_positions(self, callback) -> bool:
        """订阅持仓更新（Backpack可能不支持）"""
        logger.warning("Backpack不支持持仓更新订阅")
        return False
    
    async def subscribe_balance(self, callback) -> bool:
        """订阅余额更新（Backpack可能不支持）"""
        logger.warning("Backpack不支持余额更新订阅")
        return False
    
    async def unsubscribe(self, channel: str) -> bool:
        """取消订阅"""
        if not self.connected or not self.ws:
            return False
        
        try:
            unsubscribe_msg = {
                "method": "unsubscribe",
                "params": [channel]
            }
            self.ws.send(json.dumps(unsubscribe_msg))
            if channel in self.subscriptions:
                self.subscriptions.remove(channel)
            return True
        except Exception as e:
            logger.error(f"取消订阅失败: {e}")
            return False
    
    def is_connected(self) -> bool:
        """检查连接状态"""
        return self.connected

