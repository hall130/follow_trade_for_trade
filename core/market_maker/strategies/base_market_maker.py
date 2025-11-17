"""
做市策略基类
提供做市策略的基础框架和通用方法
"""
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List, Tuple
from utils.logger import logger


class BaseMarketMaker(ABC):
    """做市策略基类"""
    
    def __init__(self, api_key: str, api_secret: str, symbol: str, 
                 base_spread_percentage: float = 0.2, order_quantity: Optional[float] = None,
                 max_orders: int = 3, ws_proxy: Optional[str] = None,
                 exchange: str = 'backpack', exchange_config: Optional[Dict] = None,
                 enable_database: bool = False):
        """
        初始化做市策略
        
        Args:
            api_key: API密钥
            api_secret: API密钥
            symbol: 交易对
            base_spread_percentage: 基础价差百分比
            order_quantity: 订单数量
            max_orders: 每侧最大订单数
            ws_proxy: WebSocket代理
            exchange: 交易所名称
            exchange_config: 交易所配置
            enable_database: 是否启用数据库
        """
        self.api_key = api_key
        self.api_secret = api_secret
        self.symbol = symbol
        self.base_spread_percentage = base_spread_percentage
        self.order_quantity = order_quantity
        self.max_orders = max_orders
        self.ws_proxy = ws_proxy
        self.exchange = exchange
        self.exchange_config = exchange_config or {}
        self.enable_database = enable_database
        
        # 初始化交易所客户端
        self._init_client()
        
        # 初始化WebSocket（如果支持）
        self._init_websocket()
    
    def _init_client(self):
        """初始化交易所客户端"""
        if self.exchange == 'backpack':
            from exchange.backpack.backpack_rest_client import BackpackRESTClient
            self.client = BackpackRESTClient(
                self.api_key,
                self.api_secret,
                is_demo=False,
                base_url=self.exchange_config.get('base_url', 'https://api.backpack.work')
            )
        else:
            raise ValueError(f"不支持的交易所: {self.exchange}")
    
    def _init_websocket(self):
        """初始化WebSocket连接"""
        if self.exchange == 'backpack':
            from exchange.backpack.backpack_ws_client import BackpackWebSocketClient
            self.ws = BackpackWebSocketClient(
                api_key=self.api_key,
                api_secret=self.api_secret,
                is_demo=False,
                symbol=self.symbol,
                proxy=self.ws_proxy
            )
            # 异步连接
            import asyncio
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    # 如果事件循环正在运行，在专用线程中运行
                    import threading
                    import concurrent.futures
                    future = concurrent.futures.Future()
                    def run_in_thread():
                        new_loop = asyncio.new_event_loop()
                        asyncio.set_event_loop(new_loop)
                        try:
                            result = new_loop.run_until_complete(self.ws.connect())
                            future.set_result(result)
                        except Exception as e:
                            future.set_exception(e)
                        finally:
                            new_loop.close()
                    thread = threading.Thread(target=run_in_thread, daemon=True)
                    thread.start()
                    thread.join(timeout=30)
                    if thread.is_alive():
                        raise TimeoutError("WebSocket连接超时")
                    future.result()
                else:
                    # 事件循环存在但未运行，为了安全也在专用线程中运行
                    import concurrent.futures
                    future = concurrent.futures.Future()
                    def run_in_thread():
                        new_loop = asyncio.new_event_loop()
                        asyncio.set_event_loop(new_loop)
                        try:
                            result = new_loop.run_until_complete(self.ws.connect())
                            future.set_result(result)
                        except Exception as e:
                            future.set_exception(e)
                        finally:
                            new_loop.close()
                    thread = threading.Thread(target=run_in_thread, daemon=True)
                    thread.start()
                    thread.join(timeout=30)
                    if thread.is_alive():
                        raise TimeoutError("WebSocket连接超时")
                    future.result()
            except RuntimeError:
                # 没有事件循环，在专用线程中创建并运行
                import concurrent.futures
                future = concurrent.futures.Future()
                def run_in_thread():
                    new_loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(new_loop)
                    try:
                        result = new_loop.run_until_complete(self.ws.connect())
                        future.set_result(result)
                    except Exception as e:
                        future.set_exception(e)
                    finally:
                        new_loop.close()
                thread = threading.Thread(target=run_in_thread, daemon=True)
                thread.start()
                thread.join(timeout=30)
                if thread.is_alive():
                    raise TimeoutError("WebSocket连接超时")
                future.result()
        else:
            self.ws = None
    
    @abstractmethod
    def run(self, duration_seconds: int = 3600, interval_seconds: int = 60):
        """
        运行做市策略
        
        Args:
            duration_seconds: 运行时长（秒）
            interval_seconds: 更新间隔（秒）
        """
        pass
    
    @abstractmethod
    def place_limit_orders(self):
        """下限价单"""
        pass
    
    @abstractmethod
    def cancel_existing_orders(self):
        """取消现有订单"""
        pass
    
    @abstractmethod
    def check_order_fills(self):
        """检查订单成交情况"""
        pass

