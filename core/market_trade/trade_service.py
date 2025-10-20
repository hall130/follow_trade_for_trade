from database.db import (
    insert_customer_trade, update_customer_trade_order_id, log_trade_failure, get_open_trades_by_customer, close_customer_trade, get_customer_by_id, update_customer_trade_open_px, update_customer_trade_close_order_id, update_customer_trade_close_volume_contract,
    get_customer_effective_asset, get_signal_source_current_asset, MySQLPool
)
from exchange.okx.okx_ws_client import OKXWebSocketClient, WebSocketStatus, get_global_client_manager
from model.models import Customer, Rule, CustomerTrade
import asyncio
from typing import List, Optional, Dict, Any
from utils.logger import logger
import uuid
from dataclasses import fields
import hashlib
import time
import aiohttp
import re
import time
from threading import Lock
import threading
from datetime import datetime
import psutil
import gc
import tracemalloc
import traceback

from config.contract_config import get_contract_sz_precision, get_contract_min_sz, get_contract_multiplier, get_contract_info, get_contract_value_in_usdt, get_contract_sz_precision
from database.db import get_enabled_customers, get_enabled_signal_accounts
from utils.dingtalk_bot import send_trade_notification, send_alert_notification, send_alert_notification_async, get_dingtalk_bot, init_dingtalk_bot, send_trade_notification_async
from config.dingtalk_config import should_send_trade_notification, should_send_alert_notification, get_notification_at_settings, get_dingtalk_config
from datetime import datetime
from exchange.okx.okx_rest_client import OKXRESTClient
import os
from config.config import get_websocket_config
from database.global_db_manager import get_global_db_pool
from config.limit_follow_config import get_customer_limit_follow_config


TICKER_CACHE = {}
TICKER_CACHE_TIME = {}  # 记录每个价格的时间戳
CACHE_EXPIRE_TIME = 30  # 缓存30秒
clordid_lock = Lock()
# 用于跟踪正在处理的trade_uid，防止重复处理
processing_trades = set()
processing_lock = Lock()

# 添加多客户并发控制
customer_processing_locks = {}
customer_lock = Lock()

# 添加跨信号源的客户锁
customer_cross_signal_locks = {}
customer_cross_signal_lock = Lock()

# 全局锁字典，用于防止重复修复
_auto_fix_locks = {}
_auto_fix_locks_lock = threading.Lock()

# 进程ID，用于确保只有一个进程在运行自动补仓
_CURRENT_PID = os.getpid()

# 仓位检查锁，用于确保只有一个进程在运行仓位检查
_position_check_lock = threading.Lock()
_position_check_running = False

# 合约最小下单量已从contract_config.py获取，无需缓存

def get_customer_processing_lock(customer_uid):
    """获取客户专用的处理锁"""
    with customer_lock:
        if customer_uid not in customer_processing_locks:
            customer_processing_locks[customer_uid] = Lock()
        return customer_processing_locks[customer_uid]

def get_customer_cross_signal_lock(customer_uid):
    """获取客户跨信号源的全局锁"""
    with customer_cross_signal_lock:
        if customer_uid not in customer_cross_signal_locks:
            customer_cross_signal_locks[customer_uid] = Lock()
        return customer_cross_signal_locks[customer_uid]

def get_signal_processing_lock(signal_source_uid, symbol, pos_side):
    """获取信号源专用的处理锁"""
    lock_key = f"{signal_source_uid}_{symbol}_{pos_side}"
    with customer_lock:
        if lock_key not in customer_processing_locks:
            customer_processing_locks[lock_key] = Lock()
        return customer_processing_locks[lock_key]

# 移除全局锁相关定义
# order_locks = {}
# def get_order_lock_key(...):
#     ...

# 1. 修正 make_clOrdId，确保唯一

def make_clOrdId(trade_uid, attempt=1):
    base = re.sub(r'[^A-Za-z0-9]', '', str(trade_uid))
    # 使用更精确的时间戳（纳秒级）
    ts = str(int(time.time() * 1000000))[-8:]  # 使用微秒级时间戳
    # 使用更长的随机数
    rand = uuid.uuid4().hex[:6]  # 增加到6位
    # 添加进程ID确保唯一性
    import os
    pid = str(os.getpid())[-3:]  # 进程ID后3位
    clOrdId = f'C{base}r{attempt}{ts}{rand}{pid}'
    return clOrdId[:32]

# 获取唯一锁key

def get_order_lock_key(customer_uid, symbol, pos_side, rule_uid=None):
    return f'{customer_uid}_{symbol}_{pos_side}_{rule_uid or ""}'

# 合约最小下单量已从contract_config.py获取，无需异步函数

async def get_price_on_demand(symbol):
    """按需获取价格，用于风控判断"""
    import time
    
    current_time = time.time()
    
    try:
        # 先检查缓存是否有效
        if symbol in TICKER_CACHE and symbol in TICKER_CACHE_TIME:
            cache_time = TICKER_CACHE_TIME[symbol]
            if current_time - cache_time < CACHE_EXPIRE_TIME:
                tick = TICKER_CACHE[symbol]
                price = safe_float(tick.get('last', tick.get('lastPx', 0)))
                if price > 0:
                    logger.debug(f"[价格获取] 使用缓存价格: {symbol} = {price}")
                    return price
        
        # 缓存中没有或价格无效，从REST API获取
        logger.info(f"[价格获取] 从REST API获取价格: {symbol}")
        
        # 🚀 修复：使用专门的REST客户端，避免创建WebSocket任务
        import aiohttp
        
        # 构建OKX REST API URL
        url = "https://www.okx.com/api/v5/market/ticker"
        params = {"instId": symbol}
        
        # 使用aiohttp快速获取价格，不创建WebSocket任务
        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params, timeout=2.0) as response:
                if response.status == 200:
                    data = await response.json()
                    if data.get("code") == "0" and data.get("data"):
                        ticker_data = data["data"][0]
                        last_price = ticker_data.get("last", "0")
                        logger.info(f"✅ 快速获取价格成功: {symbol} = {last_price}")
                        ticker_data = {"last": last_price}
                    else:
                        logger.warning(f"⚠️ 价格获取失败，使用默认价格: {symbol}")
                        ticker_data = {"last": "1.0"}
                else:
                    logger.warning(f"⚠️ 价格获取失败，使用默认价格: {symbol}")
                    ticker_data = {"last": "1.0"}
        
        if ticker_data:
            price = safe_float(ticker_data.get('last', ticker_data.get('lastPx', 0)))
            if price > 0:
                # 更新缓存和时间戳
                TICKER_CACHE[symbol] = ticker_data
                TICKER_CACHE_TIME[symbol] = current_time
                logger.info(f"[价格获取] 获取成功: {symbol} = {price}")
                return price
            else:
                logger.warning(f"[价格获取] 价格无效: {symbol} = {price}")
        else:
            logger.error(f"[价格获取] 获取失败: {symbol}")
            
    except Exception as e:
        logger.error(f"[价格获取] 异常: {symbol} - {e}")
    
    # 获取失败时返回默认价格
    logger.warning(f"[价格获取] 使用默认价格: {symbol} = 1")
    return 1

# 移除持续订阅功能，改为按需获取
async def subscribe_all_tickers(symbols):
    """已废弃：改为按需获取价格"""
    logger.info("价格订阅功能已废弃，改为按需获取价格")
    return

def check_price_cache():
    """检查价格缓存状态（简化版）"""
    if not TICKER_CACHE:
        logger.info("[价格缓存] 价格缓存为空，将按需获取")
        return False
    
    logger.info(f"[价格缓存] 当前缓存了 {len(TICKER_CACHE)} 个品种的价格")
    return True

def safe_float(val, default=0.0):
    try:
        if val is None:
            return default
        return float(val)
    except Exception:
        return default

def safe_float_from_dict(dict_obj, key, default=0.0):
    """从字典中安全获取float值，处理None情况"""
    value = dict_obj.get(key)
    if value is None:
        return default
    return safe_float(value, default)

def safe_volume(val, ndigits=3):
    try:
        if val is None:
            return 0.0
        return round(float(val), ndigits)
    except Exception:
        return 0.0



# 导入合约配置




# 全局实盘/模拟盘切换开关
global_is_demo = 1  # True为模拟盘，False为实盘

def set_global_is_demo(is_demo: int):
    global global_is_demo
    global_is_demo = is_demo
    logger.info(f"[切换盘环境] 已切换为{'模拟盘' if is_demo else '实盘'}")

def get_global_is_demo():
    import os
    return int(os.environ.get('IS_DEMO', '1'))

def safe_get_attr(obj, attr_name, default=None):
    """安全获取对象或字典的属性值"""
    if isinstance(obj, dict):
        return obj.get(attr_name, default)
    else:
        return getattr(obj, attr_name, default)

def get_customer_uid(customer):
    """获取客户UID，支持对象和字典两种类型"""
    return safe_get_attr(customer, 'customer_uid')

def get_trade_field(trade, field):
    if isinstance(trade, dict):
        return trade.get(field)
    return getattr(trade, field, None)

def get_customer_field(customer, field, default=None):
    """获取客户字段，支持对象和字典两种类型"""
    if isinstance(customer, dict):
        return customer.get(field, default)
    return getattr(customer, field, default)

def get_is_demo_from_obj(obj):
    # 兼容对象和dict
    if hasattr(obj, 'is_demo'):
        return getattr(obj, 'is_demo', None)
    if isinstance(obj, dict):
        return obj.get('is_demo')
    return None

# ==================== 统一连接管理系统 ====================

class ConnectionManager:
    """统一连接管理器"""
    
    def __init__(self):
        self._clients = {}  # 所有客户端连接
        self._client_locks = {}  # 客户端创建锁
        self._connection_health = {}  # 连接健康状态
        self._reconnect_protection = {}  # 重连保护
        self._max_reconnect_attempts = 3
        self._reconnect_cooldown = 300  # 5分钟
        self._customer_reconnect_cooldown = 60  # 1分钟
        
    async def get_or_create_client(self, client_type: str, client_id: str, 
                                  is_demo: bool = False, api_key: str = '', 
                                  api_secret: str = '', passphrase: str = ''):
        """获取或创建客户端连接"""
        client_key = f"{client_type}_{client_id}"
        
        # 检查现有连接
        if client_key in self._clients:
            client = self._clients[client_key]
            if client and self._is_client_healthy(client):
                logger.debug(f"复用现有连接: {client_key}")
                return client
            else:
                logger.warning(f"连接 {client_key} 不健康，需要重新创建")
                await self._cleanup_client(client_key)
        
        # 检查重连保护
        if self._is_reconnect_protected(client_key):
            logger.warning(f"连接 {client_key} 处于重连保护期")
            return None
        
        # 创建新连接
        async with self._get_client_lock(client_key):
            # 双重检查
            if client_key in self._clients:
                return self._clients[client_key]
            
            try:
                logger.info(f"创建新连接: {client_key}")
                
                # 使用全局客户端管理器
                client_manager = get_global_client_manager()
                
                client = await client_manager.get_client(
                    client_key=client_key,
                    is_demo=is_demo,
                    api_key=api_key,
                    api_secret=api_secret,
                    passphrase=passphrase
                )
                
                # 确保连接建立
                if not self._is_client_healthy(client):
                    await client.connect()
                
                # 存储连接
                self._clients[client_key] = client
                self._connection_health[client_key] = {
                    'created_time': time.time(),
                    'last_health_check': time.time(),
                    'is_healthy': True
                }
                
                logger.info(f"连接 {client_key} 创建成功")
                return client
                
            except Exception as e:
                logger.error(f"创建连接 {client_key} 失败: {e}")
                return None
    
    def _is_client_healthy(self, client):
        """检查客户端健康状态"""
        try:
            if not client:
                return False
            
            if hasattr(client, 'is_connection_healthy'):
                return client.is_connection_healthy()
            
            if hasattr(client, 'ws') and client.ws:
                return not getattr(client.ws, 'closed', False)
            
            return False
        except Exception:
            return False
    
    def _is_reconnect_protected(self, client_key):
        """检查是否处于重连保护期"""
        if client_key not in self._reconnect_protection:
            return False
        
        protection_info = self._reconnect_protection[client_key]
        current_time = time.time()
        
        # 检查冷却期
        cooldown = self._customer_reconnect_cooldown if 'customer_' in client_key else self._reconnect_cooldown
        if current_time - protection_info.get('last_attempt', 0) < cooldown:
            return True
        
        # 检查重连次数
        if protection_info.get('attempt_count', 0) >= self._max_reconnect_attempts:
            return True
        
        return False
    
    def _record_reconnect_attempt(self, client_key):
        """记录重连尝试"""
        current_time = time.time()
        
        if client_key not in self._reconnect_protection:
            self._reconnect_protection[client_key] = {
                'attempt_count': 0,
                'last_attempt': 0,
                'first_attempt': current_time
            }
        
        protection_info = self._reconnect_protection[client_key]
        
        # 重置计数（如果超过冷却期）
        cooldown = self._customer_reconnect_cooldown if 'customer_' in client_key else self._reconnect_cooldown
        if current_time - protection_info.get('last_attempt', 0) > cooldown:
            protection_info['attempt_count'] = 0
            protection_info['first_attempt'] = current_time
        
        protection_info['attempt_count'] += 1
        protection_info['last_attempt'] = current_time
        
        logger.info(f"重连尝试: {client_key} ({protection_info['attempt_count']}/{self._max_reconnect_attempts})")
    
    def _reset_reconnect_protection(self, client_key):
        """重置重连保护"""
        if client_key in self._reconnect_protection:
            del self._reconnect_protection[client_key]
            logger.info(f"重置重连保护: {client_key}")
    
    def _get_client_lock(self, client_key):
        """获取客户端锁"""
        if client_key not in self._client_locks:
            self._client_locks[client_key] = asyncio.Lock()
        return self._client_locks[client_key]
    
    async def _cleanup_client(self, client_key):
        """清理客户端连接"""
        try:
            if client_key in self._clients:
                client = self._clients[client_key]
                if client:
                    try:
                        await client.close()
                    except Exception as e:
                        logger.warning(f"关闭连接 {client_key} 时出错: {e}")
                
                del self._clients[client_key]
                if client_key in self._connection_health:
                    del self._connection_health[client_key]
                
                logger.info(f"清理连接: {client_key}")
        except Exception as e:
            logger.error(f"清理连接 {client_key} 失败: {e}")
    
    async def reconnect_client(self, client_type: str, client_id: str, 
                             is_demo: bool = False, api_key: str = '', 
                             api_secret: str = '', passphrase: str = ''):
        """重连客户端"""
        client_key = f"{client_type}_{client_id}"
        
        # 检查重连保护
        if self._is_reconnect_protected(client_key):
            logger.warning(f"连接 {client_key} 处于重连保护期，跳过重连")
            return None
        
        # 记录重连尝试
        self._record_reconnect_attempt(client_key)
        
        # 清理旧连接
        await self._cleanup_client(client_key)
        
        # 创建新连接
        new_client = await self.get_or_create_client(client_type, client_id, is_demo, api_key, api_secret, passphrase)
        
        if new_client:
            self._reset_reconnect_protection(client_key)
            logger.info(f"重连成功: {client_key}")
        else:
            logger.error(f"重连失败: {client_key}")
        
        return new_client
    
    async def cleanup_all_clients(self):
        """清理所有客户端连接"""
        try:
            logger.info("开始清理所有客户端连接...")
            
            cleanup_tasks = []
            for client_key in list(self._clients.keys()):
                cleanup_tasks.append(self._cleanup_client(client_key))
            
            if cleanup_tasks:
                await asyncio.gather(*cleanup_tasks, return_exceptions=True)
            
            logger.info("所有客户端连接已清理")
        except Exception as e:
            logger.error(f"清理所有客户端连接失败: {e}")
    
    def get_client_status(self):
        """获取所有客户端状态"""
        status = {}
        for client_key, client in self._clients.items():
            status[client_key] = {
                'is_healthy': self._is_client_healthy(client),
                'created_time': self._connection_health.get(client_key, {}).get('created_time', 0),
                'last_health_check': self._connection_health.get(client_key, {}).get('last_health_check', 0)
            }
        return status

# 全局连接管理器实例
_connection_manager = None

def get_connection_manager():
    """获取全局连接管理器"""
    global _connection_manager
    if _connection_manager is None:
        _connection_manager = ConnectionManager()
    return _connection_manager

class TradeService:
    """
    跟单交易服务：
    - 负责客户跟单下单、风控、失败记录、平仓等核心业务
    - 所有数据库操作均通过db.py的CURD函数实现
    """
    def _get_customer_field(self, customer, field, default=None):
        """安全获取客户字段值，兼容字典和数据库查询结果对象"""
        if hasattr(customer, 'get'):
            # 如果是字典对象
            return customer.get(field, default)
        else:
            # 如果是数据库查询结果对象，使用属性访问
            return getattr(customer, field, default)

    def __init__(self, db_pool):
        self.db_pool = db_pool
        self.customers = []
        self.rules = []
        self.signal_sources = []
        self.strategies = []
        self.dingtalk_bot = None
        self.stop_loss_monitor = None  # 止损监控器
        self.monitor_task = None  # 监控任务
        
        # 使用统一连接管理器
        self.connection_manager = get_connection_manager()
        
        # 添加clients属性初始化，保持向后兼容
        self.clients = {}
        
        # 监控相关属性
        self.connection_health_monitor_task = None
        self.memory_monitor_task = None
        self.cleanup_task = None

        self.last_cleanup_time = time.time()
        self.connection_activity_timestamps = {}  # 记录每个连接的最后活动时间
        self.websocket_health_status = {}  # 记录每个连接的健康状态
        self.memory_usage_history = []  # 记录内存使用历史
        self.max_memory_usage = 500 * 1024 * 1024  # 500MB内存限制
        self.cleanup_interval = 150  # 5分钟清理一次
        self.health_check_interval = 30  # 30秒健康检查一次，提高响应速度
        
        self._ensure_dingtalk_initialized()
    
    def _ensure_dingtalk_initialized(self):
        """确保钉钉机器人已初始化"""
        try:
            
            
            # 检查是否已初始化
            bot = get_dingtalk_bot()
            if bot:
                logger.info("✅ 交易服务检测到钉钉机器人已初始化")
                return
            
            # 如果未初始化，尝试初始化
            config = get_dingtalk_config()
            if config.get("enabled", False):
                webhook_url = config.get("webhook_url")
                secret = config.get("secret")
                if webhook_url and webhook_url != "YOUR_ACCESS_TOKEN" and secret and secret != "YOUR_SECRET_KEY":
                    init_dingtalk_bot(webhook_url, secret)
                    logger.info("✅ 交易服务初始化钉钉机器人成功")
                else:
                    logger.warning("⚠️ 交易服务钉钉机器人配置不完整")
            else:
                logger.info("ℹ️ 交易服务检测到钉钉通知已禁用")
                
        except Exception as e:
            logger.error(f"❌ 交易服务钉钉机器人初始化失败: {e}")
    
    def _sync_clients_with_connection_manager(self):
        """同步clients和connection_manager，保持向后兼容"""
        try:
            # 从connection_manager获取所有客户连接
            client_status = self.connection_manager.get_client_status()
            
            # 更新self.clients
            for client_key, status in client_status.items():
                if client_key.startswith('customer_'):
                    customer_uid = client_key.replace('customer_', '')
                    if status.get('is_healthy', False):
                        # 获取实际的客户端对象
                        client = self.connection_manager._clients.get(client_key)
                        if client:
                            self.clients[customer_uid] = client
                        else:
                            # 如果connection_manager中没有客户端，从clients中移除
                            self.clients.pop(customer_uid, None)
                    else:
                        # 不健康的连接从clients中移除
                        self.clients.pop(customer_uid, None)
            
            logger.debug(f"同步完成，当前clients数量: {len(self.clients)}")
            
        except Exception as e:
            logger.error(f"同步clients和connection_manager失败: {e}")
    
    async def get_client(self, customer):
        """获取客户WebSocket客户端 - 兼容旧接口"""
        try:
            customer_uid = get_customer_uid(customer)
            
            # 先检查clients中是否有
            if customer_uid in self.clients:
                client = self.clients[customer_uid]
                # 检查客户端是否健康
                if hasattr(client, 'is_connection_healthy') and client.is_connection_healthy():
                    return client
                else:
                    # 不健康，从clients中移除
                    del self.clients[customer_uid]
            
            # 从connection_manager获取或创建
            client = await self.connection_manager.get_or_create_client(
                client_type="customer",
                client_id=customer_uid,
                is_demo=get_is_demo_from_obj(customer),
                api_key=getattr(customer, 'api_key', ''),
                api_secret=getattr(customer, 'api_secret', ''),
                passphrase=getattr(customer, 'passphrase', '')
            )
            
            if client:
                # 同步到clients中
                self.clients[customer_uid] = client
                return client
            else:
                logger.error(f"无法获取客户 {customer_uid} 的客户端")
                return None
                
        except Exception as e:
            logger.error(f"获取客户客户端失败: {e}")
            return None
    
    async def cleanup_all_clients(self):
        """清理所有WebSocket客户端连接"""
        try:
            logger.info("开始清理所有WebSocket客户端连接...")
            await self.connection_manager.cleanup_all_clients()
            logger.info("所有WebSocket客户端连接已清理")
        except Exception as e:
            logger.error(f"清理WebSocket客户端连接失败: {e}")

    async def check_websocket_connections(self):
        """检查WebSocket连接状态并自动重连"""
        config = get_websocket_config()
        check_interval = config['connection_check_interval']
        
        while True:
            try:
                # 获取所有客户端状态
                client_status = self.connection_manager.get_client_status()
            
                # 检查客户连接
                for client_key, status in client_status.items():
                    if client_key.startswith('customer_'):
                        customer_uid = client_key.replace('customer_', '')
                        
                        if not status['is_healthy']:
                            logger.warning(f"检测到不健康的客户连接: {customer_uid}")
                            
                            # 查找对应的客户对象
                            customer = None
                            for c in self.customers:
                                if get_customer_uid(c) == customer_uid:
                                    customer = c
                                    break
                            
                            if customer:
                                logger.info(f"重连客户: {customer_uid}")
                                await self._smart_reconnect_customer(customer)
                            else:
                                logger.warning(f"未找到客户对象: {customer_uid}")
                
                # 检查信号源连接
                for client_key, status in client_status.items():
                    if client_key.startswith('signal_'):
                        source_uid = client_key.replace('signal_', '')
                        
                        if not status['is_healthy']:
                            logger.warning(f"检测到不健康的信号源连接: {source_uid}")
                            
                            # 查找对应的信号源对象
                            signal_source = None
                            for s in self.signal_sources:
                                if s.source_uid == source_uid:
                                    signal_source = s
                                    break
                            
                            if signal_source:
                                logger.info(f"重连信号源: {source_uid}")
                                await self._smart_reconnect_signal_source(signal_source)
                            else:
                                logger.warning(f"未找到信号源对象: {source_uid}")
            
                await asyncio.sleep(check_interval)
            except Exception as e:
                logger.error(f"WebSocket连接检查循环出错: {e}")
                await asyncio.sleep(60)

    def set_db_pool(self, db_pool):
        self.db_pool = db_pool

    def reload_rules_from_db(self):
        """从数据库拉取最新规则，更新到内存"""
        self.rules = self.db_pool.query("SELECT * FROM rules WHERE enabled=1")
        logger.info(f"[热重载] 已加载{len(self.rules)}条规则")
    
    def reload_customers_from_db(self):
        """从数据库拉取最新客户信息，更新到内存"""
        is_demo = get_global_is_demo()
        self.customers = self.db_pool.query("SELECT * FROM customers WHERE enabled=1 AND is_demo=%s", (is_demo,))
        logger.info(f"[热重载] 已加载{len(self.customers)}个客户")
    
    def reload_signal_sources_from_db(self):
        """从数据库拉取最新信号源信息，更新到内存"""
        is_demo = get_global_is_demo()
        self.signal_sources = self.db_pool.query("SELECT * FROM signal_sources WHERE enabled=1 AND is_demo=%s", (is_demo,))
        logger.info(f"[热重载] 已加载{len(self.signal_sources)}个信号源")
    
    def reload_strategies_from_db(self):
        """从数据库拉取最新策略信息，更新到内存"""
        self.strategies = self.db_pool.query("SELECT * FROM strategies WHERE enabled=1")
        logger.info(f"[热重载] 已加载{len(self.strategies)}个策略")
    
    def reload_all_from_db(self):
        """重新加载所有配置信息"""
        self.reload_rules_from_db()
        self.reload_customers_from_db()
        self.reload_signal_sources_from_db()
        self.reload_strategies_from_db()
        logger.info("[热重载] 所有配置信息已重新加载")

    def get_rule_by_uid(self, rule_uid):
        for rule in self.rules:
            if rule['rule_uid'] == rule_uid:
                return rule
        return None

    def get_open_trades(self, customer_uid: str) -> List[CustomerTrade]:
        """
        获取客户所有未平仓的跟单交易
        """
        is_demo = get_global_is_demo()
        rows = self.db_pool.query("SELECT * FROM customer_trades WHERE customer_uid=%s AND status='open' AND is_demo=%s", (customer_uid, is_demo))
        return [CustomerTrade(**row) for row in rows]

    def get_open_trades_by_symbol(self, symbol: str, pos_side: str) -> List[CustomerTrade]:
        is_demo = get_global_is_demo()
        rows = self.db_pool.query("SELECT * FROM customer_trades WHERE symbol=%s AND pos_side=%s AND status='open' AND is_demo=%s", (symbol, pos_side, is_demo))
        return [CustomerTrade(**row) for row in rows]

    def get_rules_by_symbol(self, symbol: str) -> List[Rule]:
        rows = self.db_pool.query("SELECT * FROM rules WHERE symbol=%s", (symbol,))
        return [Rule(**row) for row in rows]

    def safe_customer(self, row):
        from model.models import Customer
        customer_fields = {f.name for f in fields(Customer)}
        data = {k: v for k, v in row.items() if k in customer_fields}
        # enabled 字段类型兼容
        if 'enabled' in data:
            data['enabled'] = bool(data['enabled'])
        if 'is_demo' in row:
            data['is_demo'] = int(row['is_demo']) if row['is_demo'] is not None else 0
        return Customer(**data)

    async def _cleanup_client_connection(self, client, customer_uid: str):
        """清理客户端旧连接"""
        try:
            logger.info(f"🧹 开始清理客户{customer_uid}的旧连接...")
            
            # 1. 取消监听任务
            if hasattr(client, '_listen_task') and client._listen_task and not client._listen_task.done():
                logger.info(f"🧹 取消客户{customer_uid}的监听任务...")
                client._listen_task.cancel()
                try:
                    # 使用asyncio.wait方法，更安全地处理任务取消
                    done, pending = await asyncio.wait([client._listen_task], timeout=2.0)
                    if done:
                        for completed_task in done:
                            try:
                                result = completed_task.result()
                                logger.debug(f"🧹 客户{customer_uid}的监听任务已完成，结果: {result}")
                            except asyncio.CancelledError:
                                logger.debug(f"🧹 客户{customer_uid}的监听任务已正常取消")
                            except Exception as task_exception:
                                logger.debug(f"🧹 客户{customer_uid}的监听任务完成时出现异常: {task_exception}")
                    else:
                        logger.debug(f"🧹 客户{customer_uid}的监听任务取消超时")
                except Exception as e:
                    logger.warning(f"⚠️ 等待客户{customer_uid}的监听任务取消时出错: {e}")
                logger.info(f"🧹 客户{customer_uid}的监听任务已取消")
            
            # 2. 取消心跳任务
            if hasattr(client, '_ping_task') and client._ping_task and not client._ping_task.done():
                logger.info(f"🧹 取消客户{customer_uid}的心跳任务...")
                client._ping_task.cancel()
                try:
                    # 使用asyncio.wait方法，更安全地处理任务取消
                    done, pending = await asyncio.wait([client._ping_task], timeout=2.0)
                    if done:
                        for completed_task in done:
                            try:
                                result = completed_task.result()
                                logger.debug(f"🧹 客户{customer_uid}的心跳任务已完成，结果: {result}")
                            except asyncio.CancelledError:
                                logger.debug(f"🧹 客户{customer_uid}的心跳任务已正常取消")
                            except Exception as task_exception:
                                logger.debug(f"🧹 客户{customer_uid}的心跳任务完成时出现异常: {task_exception}")
                    else:
                        logger.debug(f"🧹 客户{customer_uid}的心跳任务取消超时")
                except Exception as e:
                    logger.warning(f"⚠️ 等待客户{customer_uid}的心跳任务取消时出错: {e}")
                logger.info(f"🧹 客户{customer_uid}的心跳任务已取消")
            
            # 3. 关闭WebSocket连接
            if hasattr(client, 'ws') and client.ws and not getattr(client.ws, 'closed', False):
                logger.info(f"🧹 关闭客户{customer_uid}的WebSocket连接...")
                try:
                    await client.ws.close()
                    logger.info(f"🧹 客户{customer_uid}的WebSocket连接已关闭")
                except Exception as e:
                    logger.warning(f"🧹 关闭WebSocket连接时出现异常: {e}")
            
            # 4. 清理订阅状态
            if hasattr(client, '_active_subscriptions'):
                old_count = len(client._active_subscriptions)
                client._active_subscriptions.clear()
                logger.info(f"🧹 清理客户{customer_uid}的订阅状态，清除了{old_count}个订阅")
            
            # 5. 重置连接状态
            if hasattr(client, 'state_machine'):
                try:
                    # 状态机只有 transition_to 方法，没有 set_status 方法
                    if hasattr(client.state_machine, 'transition_to'):
                        await client.state_machine.transition_to(WebSocketStatus.DISCONNECTED)
                        logger.info(f"🧹 重置客户{customer_uid}的连接状态为已断开")
                    else:
                        logger.warning(f"🧹 客户{customer_uid}的状态机不支持状态重置")
                except Exception as e:
                    logger.warning(f"🧹 重置连接状态时出现异常: {e}")
            
            # 6. 清理连接指标
            if hasattr(client, 'metrics'):
                try:
                    # ConnectionMetrics类没有reset方法，手动重置关键指标
                    if hasattr(client.metrics, 'message_count'):
                        client.metrics.message_count = 0
                    if hasattr(client.metrics, 'last_message_time'):
                        client.metrics.last_message_time = None
                    if hasattr(client.metrics, 'connect_time'):
                        client.metrics.connect_time = None
                    if hasattr(client.metrics, 'conn_id'):
                        client.metrics.conn_id = None
                    if hasattr(client.metrics, 'error_count'):
                        client.metrics.error_count = 0
                    if hasattr(client.metrics, 'latency'):
                        client.metrics.latency = 0.0
                    logger.info(f"🧹 手动重置客户{customer_uid}的连接指标")
                except Exception as e:
                    logger.warning(f"🧹 重置连接指标时出现异常: {e}")
            
            # 7. 重置心跳相关状态
            if hasattr(client, '_last_ping_time'):
                client._last_ping_time = 0
            if hasattr(client, '_last_pong_time'):
                client._last_pong_time = 0
            if hasattr(client, '_ping_failures'):
                client._ping_failures = 0
            
            logger.info(f"✅ 客户{customer_uid}的旧连接清理完成")
            
        except Exception as e:
            logger.error(f"❌ 清理客户{customer_uid}的旧连接时出现异常: {e}")
    
    async def _ensure_client_listening(self, customer_uid: str, client):
        """确保客户端正在监听"""
        try:
            # 检查客户端是否已经在监听
            if hasattr(client, '_listen_task') and client._listen_task and not client._listen_task.done():
                logger.info(f"客户{customer_uid}的监听任务已在运行")
                return
            
            # 如果客户端没有监听任务，启动监听
            if hasattr(client, 'start_listening'):
                await client.start_listening()
                logger.info(f"客户{customer_uid}的监听任务已启动")
            elif hasattr(client, '_listen') and hasattr(client, '_listen_task'):
                # 如果客户端有_listen方法但任务已完成，重新启动
                if not client._listen_task or client._listen_task.done():
                    # 确保没有重复任务
                    if client._listen_task and not client._listen_task.done():
                        client._listen_task.cancel()
                        try:
                            # 使用asyncio.wait方法，更安全地处理任务取消
                            done, pending = await asyncio.wait([client._listen_task], timeout=2.0)
                            if done:
                                for completed_task in done:
                                    try:
                                        result = completed_task.result()
                                        logger.debug(f"🧹 客户{customer_uid}的监听任务已完成，结果: {result}")
                                    except asyncio.CancelledError:
                                        logger.debug(f"🧹 客户{customer_uid}的监听任务已正常取消")
                                    except Exception as task_exception:
                                        logger.debug(f"🧹 客户{customer_uid}的监听任务完成时出现异常: {task_exception}")
                            else:
                                logger.debug(f"🧹 客户{customer_uid}的监听任务取消超时")
                        except Exception as e:
                            logger.warning(f"⚠️ 等待客户{customer_uid}的监听任务取消时出错: {e}")
                    
                    client._listen_task = asyncio.create_task(client._listen())
                    logger.info(f"客户{customer_uid}的监听任务已重新启动")
                else:
                    logger.info(f"客户{customer_uid}的监听任务已在运行")
            else:
                logger.warning(f"客户{customer_uid}的客户端不支持监听方法")
                
        except Exception as e:
            logger.error(f"启动客户{customer_uid}监听任务时出错: {e}")

    async def _cleanup_invalid_connections(self):
        """定期清理无效连接"""
        try:
            logger.info("🧹 开始清理无效连接...")
            
            # 先同步clients和connection_manager
            self._sync_clients_with_connection_manager()
            
            invalid_clients = []
            
            for customer_uid, client in self.clients.items():
                try:
                    # 检查连接是否真的健康
                    is_healthy = True
                    
                    # 1. 检查WebSocket状态
                    if hasattr(client, 'ws') and (not client.ws or getattr(client.ws, 'closed', True)):
                        is_healthy = False
                        logger.debug(f"🧹 客户{customer_uid} WebSocket已关闭")
                    
                    # 2. 检查心跳状态
                    if hasattr(client, '_last_pong_time') and hasattr(client, '_ping_failures'):
                        current_time = time.time()
                        last_pong_time = getattr(client, '_last_pong_time', 0)
                        ping_failures = getattr(client, '_ping_failures', 0)
                        
                        if (current_time - last_pong_time > 120) or (ping_failures > 5):  # 2分钟无pong或5次ping失败
                            is_healthy = False
                            logger.debug(f"🧹 客户{customer_uid} 心跳异常: last_pong={current_time - last_pong_time:.1f}秒前, ping_failures={ping_failures}")
                    
                    # 3. 检查监听任务状态
                    if hasattr(client, '_listen_task') and (not client._listen_task or client._listen_task.done()):
                        is_healthy = False
                        logger.debug(f"🧹 客户{customer_uid} 监听任务异常")
                    
                    # 4. 检查连接健康状态方法
                    if hasattr(client, 'is_connection_healthy') and not client.is_connection_healthy():
                        is_healthy = False
                        logger.debug(f"🧹 客户{customer_uid} 连接健康检查失败")
                    
                    if not is_healthy:
                        invalid_clients.append(customer_uid)
                        logger.warning(f"🧹 发现无效连接: 客户{customer_uid}")
                        
                except Exception as e:
                    logger.error(f"🧹 检查客户{customer_uid}连接状态时出错: {e}")
                    invalid_clients.append(customer_uid)
            
            # 清理无效连接
            for customer_uid in invalid_clients:
                try:
                    client = self.clients[customer_uid]
                    await self._cleanup_client_connection(client, customer_uid)
                    del self.clients[customer_uid]
                    logger.info(f"🧹 已清理无效连接: 客户{customer_uid}")
                except Exception as e:
                    logger.error(f"🧹 清理客户{customer_uid}无效连接时出错: {e}")
            
            if invalid_clients:
                logger.info(f"🧹 清理完成，共清理了{len(invalid_clients)}个无效连接")
            else:
                logger.debug("🧹 未发现无效连接")
                
        except Exception as e:
            logger.error(f"🧹 清理无效连接时出错: {e}")

    def calc_nominal_and_leverage(self, customer: Customer, rule: Rule) -> tuple[float, float, float]:
        """
        计算客户本次应开仓名义价值和净杠杆（用最新规则参数）
        """
        # 优先用内存热重载的规则
        rule_obj = self.get_rule_by_uid(rule.rule_uid) if hasattr(rule, 'rule_uid') else None
        position_ratio = safe_float(rule_obj['position_ratio']) if rule_obj else safe_float(rule.position_ratio)
        max_leverage = safe_float(rule_obj['max_leverage']) if rule_obj else safe_float(getattr(rule, 'max_leverage', 10))
        trades = self.get_open_trades(get_customer_uid(customer))
        
        # 只计算跟随当前信号源的持仓名义价值
        signal_following_nominal = 0
        current_signal_source_uid = rule.rule_uid if hasattr(rule, 'rule_uid') else None
        for trade in trades:
            if get_trade_field(trade, 'rule_uid') == current_signal_source_uid:
                signal_following_nominal += safe_float(trade.volume)
        
        # 优先用实时资产 total_asset，没有再用客户初始本金 init_asset
        total_asset = None
        if hasattr(customer, 'total_asset') and safe_float(getattr(customer, 'total_asset', 0)) > 0:
            total_asset = float(safe_float(customer.total_asset))
        elif hasattr(customer, 'init_asset') and safe_float(getattr(customer, 'init_asset', 0)) > 0:
            total_asset = float(safe_float(customer.init_asset))
        else:
            total_asset = 1.0  # 默认兜底
        this_nominal = position_ratio * total_asset
        net_leverage = (signal_following_nominal + this_nominal) / total_asset if total_asset > 0 else 0
        return this_nominal, net_leverage, max_leverage

    async def restart_critical_tasks(self):
        """重启关键任务 - 当内存使用过高时调用"""
        try:
            logger.warning("🔄 开始重启关键任务...")
            
            # 重启信号服务消费者
            if hasattr(self, 'signal_service') and self.signal_service:
                if self.signal_service._signal_consumer_task and not self.signal_service._signal_consumer_task.done():
                    self.signal_service._signal_consumer_task.cancel()
                    logger.info("已取消旧的信号消费者任务")
                
                # 启动新的信号消费者
                await self.signal_service.start_signal_consumer()
                logger.info("已重启信号消费者任务")
            
            # 清理内存
            import gc
            collected = gc.collect()
            logger.info(f"垃圾回收清理了 {collected} 个对象")
            
            # 强制内存清理
            try:
                import psutil
                process = psutil.Process()
                memory_before = process.memory_info().rss / 1024 / 1024
                
                # 等待一段时间让GC生效
                await asyncio.sleep(5)
                
                memory_after = process.memory_info().rss / 1024 / 1024
                logger.info(f"内存清理效果: {memory_before:.2f} MB -> {memory_after:.2f} MB")
                
            except ImportError:
                logger.info("psutil未安装，跳过内存清理效果检查")
            
            logger.info("✅ 关键任务重启完成")
            
        except Exception as e:
            logger.error(f"重启关键任务失败: {e}")
            logger.error(f"异常详情: {traceback.format_exc()}")

    async def check_memory_and_restart(self):
        """检查内存使用并在必要时重启关键任务"""
        try:
            import psutil
            process = psutil.Process()
            memory_mb = process.memory_info().rss / 1024 / 1024
            
            if memory_mb > 800:  # 超过800MB时自动重启
                logger.error(f"🚨 内存使用严重过高({memory_mb:.2f} MB)，自动重启关键任务...")
                await self.restart_critical_tasks()
            elif memory_mb > 600:  # 超过600MB时警告
                logger.warning(f"⚠️ 内存使用较高({memory_mb:.2f} MB)，建议关注")
                
        except ImportError:
            logger.debug("psutil未安装，跳过内存检查")
        except Exception as e:
            logger.error(f"内存检查和重启失败: {e}")

    def log_failure(self, trade_uid: Optional[str], reason: str):
        """
        记录失败日志
        """
        log_trade_failure(self.db_pool, trade_uid, reason)
        
        # 发送告警通知
        if should_send_alert_notification("error"):
            alert_info = {
                "title": "交易失败告警",
                "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "level": "error",
                "message": f"交易失败: {reason}",
                "account": "N/A",
                "strategy": "N/A",
                "symbol": "N/A",
                "suggestion": "请检查交易系统和网络连接"
            }
            send_alert_notification("error", alert_info)
    
    def send_trade_notification_to_dingtalk(self, trade_info: Dict[str, Any]):
        """发送交易通知到钉钉"""
        if should_send_trade_notification():
            send_trade_notification(trade_info)
    
    def send_alert_notification_to_dingtalk(self, alert_type: str, alert_info: Dict[str, Any]):
        """发送告警通知到钉钉"""
        if should_send_alert_notification(alert_type):
            send_alert_notification(alert_type, alert_info)
    
    async def send_customer_trade_notification_async(self, customer_uid: str, symbol: str, direction: str, pos_side: str, 
                                                   volume: float, order_id: str = None, trade_uid: str = None, 
                                                   success: bool = True, error: str = None, order_price: float = None,
                                                   signal_source_uid: str = None):
        """异步发送客户成交通知到钉钉（仅在异常情况下）"""
        try:
            
            # 快速检查是否应该发送通知
            if not should_send_trade_notification():
                return
            
            # 只在异常情况下发送通知
            if not success or error:
                # 快速检查钉钉机器人是否已初始化
                bot = get_dingtalk_bot()
                if not bot:
                    logger.debug(f"[钉钉通知] 钉钉机器人未初始化，跳过异常通知: customer={customer_uid}, symbol={symbol}")
                    return
                
                # 获取客户名称
                customer_name = customer_uid
                try:
                    customer_info = self.db_pool.query("SELECT name FROM customers WHERE customer_uid=%s", (customer_uid,))
                    if customer_info:
                        customer_name = customer_info[0]['name'] or customer_uid
                except Exception as e:
                    logger.warning(f"[钉钉通知] 获取客户名称失败: {e}")
                
                # 获取信号源名称
                signal_source_name = signal_source_uid or "未知信号源"
                if signal_source_uid:
                    try:
                        signal_info = self.db_pool.query("SELECT name FROM signal_sources WHERE source_uid=%s", (signal_source_uid,))
                        if signal_info:
                            signal_source_name = signal_info[0]['name'] or signal_source_uid
                    except Exception as e:
                        logger.warning(f"[钉钉通知] 获取信号源名称失败: {e}")
                
                # 获取当前价格
                current_price = get_price_on_demand(symbol) or 0
                if current_price == 0 and order_price:
                    current_price = order_price
                
                # volume已经是USDT金额，不需要再乘以价格
                volume_usdt = volume
                
                # 构建异常通知信息
                trade_info = {
                    "trade_uid": trade_uid or "unknown",
                    "symbol": symbol,
                    "direction": direction,
                    "pos_side": pos_side,
                    "volume": str(volume),
                    "volume_usdt": str(round(volume_usdt, 2)),
                    "price": str(current_price),
                    "customer_uid": customer_uid,
                    "customer_name": customer_name,
                    "signal_source_uid": signal_source_uid,
                    "signal_source_name": signal_source_name,
                    "strategy_uid": "auto_follow",
                    "rule_uid": "auto_rule",
                    "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "success": success,
                    "order_id": order_id,
                    "error": error or "交易异常"
                }
                
                # 异步发送异常通知
                try:
                    await send_trade_notification_async(trade_info)
                    logger.info(f"[钉钉通知] 异常通知已发送: customer={customer_name}, signal_source={signal_source_name}, symbol={symbol}, error={error}")
                except Exception as notify_error:
                    logger.warning(f"[钉钉通知] 异常通知发送失败: {notify_error}")
            
        except Exception as e:
            logger.debug(f"[钉钉通知] 异常通知处理异常: {e}")
    
    def send_customer_trade_notification(self, customer_uid: str, symbol: str, direction: str, pos_side: str, 
                                       volume: float, order_id: str = None, trade_uid: str = None, 
                                       success: bool = True, error: str = None):
        """发送客户成交通知到钉钉（同步方式，保持向后兼容）"""
        try:
            
            # 快速检查是否应该发送通知
            if not should_send_trade_notification():
                return
            
            # 快速检查钉钉机器人是否已初始化
            bot = get_dingtalk_bot()
            if not bot:
                # 钉钉机器人未初始化，但不影响交易流程，只记录日志
                logger.debug(f"[钉钉通知] 钉钉机器人未初始化，跳过通知: customer={customer_uid}, symbol={symbol}")
                return
            
            # 获取当前价格
            current_price = get_price_on_demand(symbol)
            
            # volume已经是USDT金额，不需要再乘以价格
            volume_usdt = volume
            
            # 构建交易信息
            trade_info = {
                "trade_uid": trade_uid or "unknown",
                "symbol": symbol,
                "direction": direction,
                "pos_side": pos_side,
                "volume": str(volume),
                "volume_usdt": str(round(volume_usdt, 2)),
                "price": str(current_price),
                "customer_uid": customer_uid,
                "strategy_uid": "auto_follow",
                "rule_uid": "auto_rule",
                "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "success": success,
                "order_id": order_id
            }
            
            if not success and error:
                trade_info["error"] = error
            
            # 发送通知（不阻塞交易流程）
            try:
                send_trade_notification(trade_info)
                logger.info(f"[钉钉通知] 客户成交通知已发送: customer={customer_uid}, symbol={symbol}, success={success}")
            except Exception as notify_error:
                # 通知发送失败不影响交易流程
                logger.warning(f"[钉钉通知] 通知发送失败但不影响交易: {notify_error}")
            
        except Exception as e:
            # 任何异常都不影响交易流程
            logger.debug(f"[钉钉通知] 通知处理异常但不影响交易: {e}")
    
    # 2. 在 async_place_order 下单前查本地未完成单
    async def async_place_order(self, customer, symbol, direction, pos_side, sz, trade_uid, attempt=1, reduceOnly=False, rule_uid=None, **kwargs):
        try:
            # 确保 sz 为 float
            sz = float(sz)
            # 防重复处理检查
            with processing_lock:
                if trade_uid in processing_trades:
                    logger.warning(f"[防重复处理] trade_uid={trade_uid} 正在处理中，跳过")
                    return {'target_uid': trade_uid, 'error': '正在处理中，跳过重复请求'}
                processing_trades.add(trade_uid)
            try:
                # 查本地未完成单
                open_trades = self.get_open_trades_by_symbol(symbol, pos_side)
                # 生成唯一 clOrdId
                clOrdId = make_clOrdId(trade_uid, attempt)
                client = await self.get_client(customer)
                max_retry = 3
                if not trade_uid:
                    trade_uid = uuid.uuid4().hex[:16]
                for retry in range(max_retry):
                    # 每次重试都自增 attempt，生成新 clOrdId
                    clOrdId = make_clOrdId(trade_uid, attempt+retry)
                    
                    # 🚀 重试前连接检查：确保每次重试都有健康连接
                    if retry > 0:
                        logger.info(f"🔄 第{retry}次重试，检查连接状态...")
                        if hasattr(client, 'is_connection_healthy') and not client.is_connection_healthy():
                            logger.warning(f"⚠️ 重试前发现连接不健康，尝试重新连接...")
                            try:
                                # 先清理旧连接
                                await self._cleanup_client_connection(client, get_customer_uid(customer))
                                # 从连接池中移除旧连接
                                customer_uid = get_customer_uid(customer)
                                if customer_uid in self.clients:
                                    del self.clients[customer_uid]
                                    logger.info(f"🧹 从连接池中移除客户{customer_uid}的旧连接")
                                # 同步clients和connection_manager
                                self._sync_clients_with_connection_manager()
                                # 重新连接
                                await client.connect()
                                logger.info(f"✅ 重试前重新连接成功")
                            except Exception as reconnect_error:
                                logger.error(f"❌ 重试前重新连接失败: {reconnect_error}")
                                # 如果重连失败，尝试重新获取客户端
                                try:
                                    client = await self.get_client(customer)
                                    logger.info(f"✅ 重试前重新获取客户端成功")
                                except Exception as get_client_error:
                                    logger.error(f"❌ 重试前重新获取客户端失败: {get_client_error}")
                                    continue  # 继续下一次重试
                    
                    try:
                        # 🚀 性能优化：跳过连接检查，直接下单
                        # 如果连接有问题，下单时会自动处理
                        min_sz = get_contract_min_sz(symbol)
                        sz_precision = get_contract_sz_precision(symbol)
                        
                        logger.info(f"[下单量计算] 原始sz={sz}, min_sz={min_sz}, sz_precision={sz_precision}")
                        
                        # 整数张修正逻辑
                        if min_sz >= 1:
                            sz = int(sz)
                            logger.info(f"[下单量计算] 整数张修正后sz={sz}")
                        else:
                            sz = round(sz / min_sz) * min_sz
                            sz = round(sz, sz_precision)
                            logger.info(f"[下单量计算] 小数张修正后sz={sz}")
                        
                        logger.info(f"[下单量验证] 最终sz={sz}, min_sz={min_sz}")
                        
                        if sz < min_sz:
                            logger.warning(f"下单张数 {sz} 小于最小要求 {min_sz}，已跳过下单: symbol={symbol}")
                            return {'target_uid': trade_uid, 'error': f'下单张数 {sz} 小于最小要求 {min_sz}'}
                        if abs(sz / min_sz - round(sz / min_sz)) > 1e-8:
                            logger.warning(f"下单张数 {sz} 不是最小单位{min_sz}的整数倍，已跳过下单: symbol={symbol}")
                            return {'target_uid': trade_uid, 'error': f'下单张数 {sz} 不是最小单位{min_sz}的整数倍'}
                        
                        logger.info(f"async_place_order: 下单前 trade_uid={trade_uid}, clOrdId={clOrdId}, symbol={symbol}, direction={direction}, pos_side={pos_side}, sz(张数)={sz}, min_sz={min_sz}, precision={sz_precision}, reduceOnly={reduceOnly}")
                        
                        # 🚀 连接健康检查：下单前确保连接正常
                        if hasattr(client, 'is_connection_healthy') and not client.is_connection_healthy():
                            logger.warning(f"⚠️ 客户{get_customer_uid(customer)}连接不健康，尝试重新连接...")
                            try:
                                # 🚀 检查是否正在重连中，避免重复操作
                                if hasattr(client, '_reconnecting') and client._reconnecting:
                                    logger.info(f"⚠️ 客户{get_customer_uid(customer)}正在重连中，等待完成...")
                                    # 等待重连完成，最多等待10秒
                                    for _ in range(20):  # 20次 * 0.5秒 = 10秒
                                        await asyncio.sleep(0.5)
                                        if hasattr(client, 'is_connection_healthy') and client.is_connection_healthy():
                                            logger.info(f"✅ 客户{get_customer_uid(customer)}重连完成，连接已恢复")
                                            break
                                    else:
                                        logger.warning(f"⚠️ 客户{get_customer_uid(customer)}重连等待超时，继续下单流程")
                                else:
                                    # 标记正在重连
                                    client._reconnecting = True
                                    try:
                                        # 先清理旧连接
                                        await self._cleanup_client_connection(client, get_customer_uid(customer))
                                        # 从连接池中移除旧连接
                                        customer_uid = get_customer_uid(customer)
                                        if customer_uid in self.clients:
                                            del self.clients[customer_uid]
                                            logger.info(f"🧹 从连接池中移除客户{customer_uid}的旧连接")
                                        # 重新连接
                                        await client.connect()
                                        logger.info(f"✅ 客户{get_customer_uid(customer)}重新连接成功")
                                    finally:
                                        # 清除重连标记
                                        client._reconnecting = False
                            except Exception as reconnect_error:
                                logger.error(f"❌ 客户{get_customer_uid(customer)}重新连接失败: {reconnect_error}")
                                # 清除重连标记
                                if hasattr(client, '_reconnecting'):
                                    client._reconnecting = False
                                # 如果重连失败，尝试重新获取客户端
                                try:
                                    client = await self.get_client(customer)
                                    logger.info(f"✅ 客户{get_customer_uid(customer)}重新获取客户端成功")
                                except Exception as get_client_error:
                                    logger.error(f"❌ 重新获取客户端失败: {get_client_error}")
                                    return {'target_uid': trade_uid, 'error': f'连接失败，无法下单: {get_client_error}'}
                        
                        # 🚀 心跳状态检查：检查心跳是否正常
                        if hasattr(client, '_last_pong_time') and hasattr(client, '_ping_failures'):
                            current_time = time.time()
                            last_pong_time = getattr(client, '_last_pong_time', 0)
                            ping_failures = getattr(client, '_ping_failures', 0)
                            
                            # 如果超过60秒没有收到pong，或者连续ping失败超过3次，认为连接有问题
                            if (current_time - last_pong_time > 60) or (ping_failures > 3):
                                logger.warning(f"⚠️ 客户{get_customer_uid(customer)}心跳异常，last_pong={current_time - last_pong_time:.1f}秒前，ping_failures={ping_failures}")
                                try:
                                    # 🚀 检查是否正在重连中，避免重复操作
                                    if hasattr(client, '_reconnecting') and client._reconnecting:
                                        logger.info(f"⚠️ 客户{get_customer_uid(customer)}心跳异常但正在重连中，等待完成...")
                                        # 等待重连完成，最多等待10秒
                                        for _ in range(20):  # 20次 * 0.5秒 = 10秒
                                            await asyncio.sleep(0.5)
                                            if hasattr(client, 'is_connection_healthy') and client.is_connection_healthy():
                                                logger.info(f"✅ 客户{get_customer_uid(customer)}重连完成，连接已恢复")
                                                break
                                        else:
                                            logger.warning(f"⚠️ 客户{get_customer_uid(customer)}重连等待超时，继续下单流程")
                                    else:
                                        # 标记正在重连
                                        client._reconnecting = True
                                        try:
                                            # 先清理旧连接
                                            await self._cleanup_client_connection(client, get_customer_uid(customer))
                                            # 从连接池中移除旧连接
                                            customer_uid = get_customer_uid(customer)
                                            if customer_uid in self.clients:
                                                del self.clients[customer_uid]
                                                logger.info(f"🧹 从连接池中移除客户{customer_uid}的旧连接")
                                            # 重新连接
                                            await client.connect()
                                            logger.info(f"✅ 客户{get_customer_uid(customer)}心跳异常后重新连接成功")
                                        finally:
                                            # 清除重连标记
                                            client._reconnecting = False
                                except Exception as reconnect_error:
                                    logger.error(f"❌ 客户{get_customer_uid(customer)}心跳异常后重新连接失败: {reconnect_error}")
                                    # 清除重连标记
                                    if hasattr(client, '_reconnecting'):
                                        client._reconnecting = False
                                    # 如果重连失败，尝试重新获取客户端
                                    try:
                                        client = await self.get_client(customer)
                                        logger.info(f"✅ 客户{get_customer_uid(customer)}心跳异常后重新获取客户端成功")
                                    except Exception as get_client_error:
                                        logger.error(f"❌ 心跳异常后重新获取客户端失败: {get_client_error}")
                                        return {'target_uid': trade_uid, 'error': f'心跳异常，无法下单: {get_client_error}'}
                        
                        # 🚀 性能监控：记录下单开始时间
                        order_start_time = time.time()
                        
                        res = await client.place_order(
                            instId=symbol,
                            tdMode='cross',
                            side=direction,
                            ordType='market',
                            sz=str(sz),
                            clOrdId=clOrdId,
                            reduceOnly='true' if reduceOnly else 'false',
                            posSide=pos_side,
                            tag='6618f740e7f1BCDE'
                        )
                        
                        # 🚀 性能监控：记录下单耗时
                        order_time = time.time() - order_start_time
                        logger.info(f"🚀 下单耗时: {order_time:.3f}秒")
                        
                        if order_time > 1.0:
                            logger.warning(f"⚠️ 下单耗时过长: {order_time:.3f}秒，超过1秒阈值")
                        
                        # 对 51016 错误终止重试
                        if res.get('sCode') == '51016':
                            logger.error(f"[下单终止] clOrdId 冲突，终止重试: {clOrdId}")
                            return {'error': 'clOrdId 冲突，终止重试'}
                        # 下单成功
                        if res.get('code') == '0' and res.get('data') and res['data'][0].get('ordId'):
                            ordId = res['data'][0]['ordId']
                            update_customer_trade_order_id(self.db_pool, trade_uid, ordId)
                            self.db_pool.execute("UPDATE customer_trades SET order_id=%s, clOrdId=%s WHERE trade_uid=%s", (ordId, clOrdId, trade_uid))
                            logger.info(f"[下单补全] 已写入order_id: trade_uid={trade_uid}, ordId={ordId}, clOrdId={clOrdId}")
                            

                            
                            return {'target_uid': trade_uid, 'ordId': ordId, 'sz': sz, 'clOrdId': clOrdId}
                        else:
                            # 获取错误信息
                            sCode = res.get('data', [{}])[0].get('sCode')
                            sMsg = res.get('data', [{}])[0].get('sMsg')
                            error_msg = f"OKX下单失败: {res}, code={res.get('code')}, sCode={sCode}, sMsg={sMsg}"
                            logger.error(f"{error_msg}, order_params={{symbol={symbol}, direction={direction}, sz={sz}, pos_side={pos_side}, reduceOnly={reduceOnly}, clOrdId={clOrdId}}}")
                            
                            # 🚀 特殊处理：连接超时错误，尝试重新连接
                            if 'No data received in 30s' in str(sMsg) or '4004' in str(sCode):
                                logger.warning(f"🔌 检测到连接超时错误，尝试重新连接...")
                                try:
                                    # 先清理旧连接
                                    await self._cleanup_client_connection(client, get_customer_uid(customer))
                                    # 从连接池中移除旧连接
                                    customer_uid = get_customer_uid(customer)
                                    if customer_uid in self.clients:
                                        del self.clients[customer_uid]
                                        logger.info(f"🧹 从连接池中移除客户{customer_uid}的旧连接")
                                    # 重新连接
                                    await client.connect()
                                    logger.info(f"✅ 连接超时后重新连接成功，继续重试")
                                    continue  # 继续重试，不增加重试计数
                                except Exception as reconnect_error:
                                    logger.error(f"❌ 连接超时后重新连接失败: {reconnect_error}")
                                    # 如果重连失败，尝试重新获取客户端
                                    try:
                                        client = await self.get_client(customer)
                                        logger.info(f"✅ 连接超时后重新获取客户端成功，继续重试")
                                        continue  # 继续重试，不增加重试计数
                                    except Exception as get_client_error:
                                        logger.error(f"❌ 连接超时后重新获取客户端失败: {get_client_error}")
                                        # 继续正常重试流程
                            
                            # 特殊处理：如果错误码是51169（没有持仓），直接更新数据库状态为closed
                            if sCode == '51169' and reduceOnly:
                                logger.warning(f"[持仓检查] 检测到没有持仓错误(sCode=51169)，更新trade状态为closed: trade_uid={trade_uid}")
                                try:
                                    # 查询当前trade信息
                                    trade_info = self.db_pool.query("SELECT volume_contract, close_volume_contract FROM customer_trades WHERE trade_uid=%s", (trade_uid,))
                                    if trade_info:
                                        volume_contract = float(trade_info[0]['volume_contract'] or 0)
                                        current_closed = float(trade_info[0]['close_volume_contract'] or 0)
                                        
                                        # 如果close_volume_contract为0，设置为volume_contract（全平）
                                        if current_closed == 0:
                                            update_customer_trade_close_volume_contract(self.db_pool, trade_uid, volume_contract)
                                            logger.info(f"[持仓检查] 更新close_volume_contract: trade_uid={trade_uid}, volume_contract={volume_contract}")
                                        
                                        # 更新状态为closed
                                        self.db_pool.execute(
                                            "UPDATE customer_trades SET status='closed' WHERE trade_uid=%s",
                                            (trade_uid,)
                                        )
                                        logger.info(f"[持仓检查] 更新状态为closed: trade_uid={trade_uid}")
                                        
                                        return {'target_uid': trade_uid, 'ordId': None, 'sz': sz, 'clOrdId': clOrdId, 'status': 'closed'}
                                    else:
                                        logger.error(f"[持仓检查] 未找到trade记录: trade_uid={trade_uid}")
                                except Exception as e:
                                    logger.error(f"[持仓检查] 更新trade状态失败: {e}")
                            
                            # 获取信号源信息
                            signal_source_uid = None
                            try:
                                trade_info = self.db_pool.query("SELECT rule_uid FROM customer_trades WHERE trade_uid=%s", (trade_uid,))
                                if trade_info:
                                    signal_source_uid = trade_info[0]['rule_uid']
                            except Exception as e:
                                logger.warning(f"[钉钉通知] 获取信号源信息失败: {e}")
                            
                            # 异步发送客户成交失败通知
                            await self.send_customer_trade_notification_async(
                                customer_uid=get_customer_uid(customer),
                                symbol=symbol,
                                direction=direction,
                                pos_side=pos_side,
                                volume=sz,
                                order_id=None,
                                trade_uid=trade_uid,
                                success=False,
                                error=error_msg,
                                signal_source_uid=signal_source_uid
                            )
                            
                            if attempt < max_retry:
                                continue
                            return {'target_uid': trade_uid, 'error': f"{error_msg}, clOrdId={clOrdId}", 'clOrdId': clOrdId}
                    except Exception as e:
                        error_msg = f"async_place_order异常: {e}"
                        logger.error(f"{error_msg}, clOrdId={clOrdId}")
                        
                        # 🚀 特殊处理：连接相关异常，尝试重新连接
                        if 'No data received' in str(e) or '4004' in str(e) or 'WebSocket' in str(e):
                            logger.warning(f"🔌 检测到连接相关异常，尝试重新连接...")
                            try:
                                # 先清理旧连接
                                await self._cleanup_client_connection(client, get_customer_uid(customer))
                                # 从连接池中移除旧连接
                                customer_uid = get_customer_uid(customer)
                                if customer_uid in self.clients:
                                    del self.clients[customer_uid]
                                    logger.info(f"🧹 从连接池中移除客户{customer_uid}的旧连接")
                                # 重新连接
                                await client.connect()
                                logger.info(f"✅ 异常后重新连接成功，继续重试")
                                continue  # 继续重试，不增加重试计数
                            except Exception as reconnect_error:
                                logger.error(f"❌ 异常后重新连接失败: {reconnect_error}")
                                # 如果重连失败，尝试重新获取客户端
                                try:
                                    client = await self.get_client(customer)
                                    logger.info(f"✅ 异常后重新获取客户端成功，继续重试")
                                    continue  # 继续重试，不增加重试计数
                                except Exception as get_client_error:
                                    logger.error(f"❌ 异常后重新获取客户端失败: {get_client_error}")
                                    # 继续正常重试流程
                        
                        # 获取信号源信息
                        signal_source_uid = None
                        try:
                            trade_info = self.db_pool.query("SELECT signal_source_uid FROM customer_trades WHERE trade_uid=%s", (trade_uid,))
                            if trade_info:
                                signal_source_uid = trade_info[0]['signal_source_uid']
                        except Exception as e:
                            logger.warning(f"[钉钉通知] 获取信号源信息失败: {e}")
                        
                        # 异步发送客户成交异常通知
                        await self.send_customer_trade_notification_async(
                            customer_uid=get_customer_uid(customer),
                            symbol=symbol,
                            direction=direction,
                            pos_side=pos_side,
                            volume=sz,
                            order_id=None,
                            trade_uid=trade_uid,
                            success=False,
                            error=error_msg,
                            signal_source_uid=signal_source_uid
                        )
                        
                        if attempt < max_retry:
                            continue
                        return {'target_uid': trade_uid, 'error': str(e), 'clOrdId': clOrdId}
                logger.error(f"[下单最终失败] customer={get_customer_uid(customer)}, symbol={symbol}, pos_side={pos_side}, clOrdId={clOrdId}")
                return {'error': '下单最终失败'}
            except Exception as e:
                logger.error(f"async_place_order异常: {e}, clOrdId={locals().get('clOrdId', '')}")
                return {'error': str(e)}
            finally:
                # 清理processing_trades
                with processing_lock:
                    processing_trades.discard(trade_uid)
        except Exception as e:
            logger.error(f"async_place_order异常: {e}, clOrdId={locals().get('clOrdId', '')}")
            return {'error': str(e)}

    async def batch_place_orders(self, customers, rule, symbol, direction, pos_side, target_uid=None, signal_volume=None, position_share=1):
        """
        兼容老接口，自动组装 signal_orders 并调用 aggregate_and_place_orders
        """
        for customer in customers:
            raw_ratio = safe_float(rule.position_ratio)
            position_ratio = 1.0 / raw_ratio if raw_ratio > 0 else 0
            max_leverage = safe_float(getattr(rule, 'max_leverage', 10))
            if signal_volume is not None:
                this_sz = safe_float(signal_volume) * position_ratio * safe_float(position_share)
            else:
                nominal, _, _ = self.calc_nominal_and_leverage(customer, rule)
                this_sz = nominal / ((get_contract_multiplier(symbol)) * (await get_price_on_demand(symbol) or 1))
            signal_orders = [{
                'signal_source_uid': getattr(rule, 'rule_uid', ''),
                'rule_uid': getattr(rule, 'rule_uid', ''),
                'strategy_uid': getattr(rule, 'strategy_uid', ''),
                'sz': this_sz,
                'max_leverage': max_leverage,
                'position_share': position_share
            }]
            await self.aggregate_and_place_orders(customer, symbol, direction, pos_side, signal_orders)

    async def batch_aggregate_place_orders(self, customer, symbol, direction, pos_side, signal_orders):
        """
        集合下单：同一币种/方向/时刻的所有信号源规则的应下单量合并为一个总单，按份额拆分写入customer_trades。
        signal_orders: List[dict]，每个dict包含signal_source_uid, rule_uid, strategy_uid, sz(应下单张数), max_leverage等
        """
        try:
            customer_uid = get_customer_uid(customer)
            
            # 风控检查
            if not self.check_customer_risk_control(customer_uid, symbol, direction, pos_side):
                logger.warning(f"[集合下单] 客户{customer_uid}风控检查未通过，跳过下单: symbol={symbol}, direction={direction}, pos_side={pos_side}")
                return
            
            valid_orders = []
            logger.info(f"[集合下单] 入口参数: customer={customer_uid}, symbol={symbol}, signal_orders={signal_orders}")
            trades = self.get_open_trades(customer_uid)
            
            # 使用db.py中的get_customer_by_id函数获取完整的客户信息
            is_demo = get_global_is_demo()
            customer_data = get_customer_by_id(self.db_pool, customer_uid, is_demo)
            
            if customer_data:
                # 使用新的有效资产获取逻辑，优先使用开仓资产
                total_asset = get_customer_effective_asset(self.db_pool, customer_uid, is_demo)
                if total_asset is None or total_asset <= 0:
                    total_asset = 10000.0  # 默认值
                    logger.warning(f"[集合下单] 客户{customer_uid}有效资产为空或无效，使用默认资产值{total_asset}")
                else:
                    # 计算使用的资产类型
                    trading_asset = customer_data.get('trading_asset')
                    init_asset = customer_data.get('init_asset')
                    current_total_asset = customer_data.get('total_asset')
                    
                    if trading_asset and float(trading_asset) > 0:
                        asset_type = "开仓资产"
                    elif current_total_asset and float(current_total_asset) > float(init_asset or 0):
                        asset_type = "当前总资产(max值)"
                    else:
                        asset_type = "初始资产(max值)"
                    
                    logger.info(f"[集合下单] 客户{customer_uid}有效资产: {total_asset} (trading_asset={trading_asset}, init_asset={init_asset}, total_asset={current_total_asset}, 使用{asset_type})")
            else:
                total_asset = 10000.0  # 默认值
                logger.warning(f"[集合下单] 未找到客户{customer_uid}数据，使用默认资产值{total_asset}")
            
            latest_px = await get_price_on_demand(symbol) or 1
            multiplier = get_contract_multiplier(symbol)
            split_sz_list = []
            valid_orders = []
            for order in signal_orders:
                logger.info(f"[集合下单] for 循环开始，信号单数: {len(signal_orders)}")
                logger.info(f"[集合下单] 检查信号单: {order}")
                min_sz = get_contract_min_sz(symbol)
                logger.info(f"[集合下单] symbol={symbol}, sz={order['sz']}, min_sz={min_sz}")
                try:
                    # 获取信号源账户额
                    signal_source_uid = order.get('signal_source_uid')
                    if not signal_source_uid:
                        logger.error(f"[集合下单] 信号单缺少signal_source_uid: {order}")
                        continue
                    
                    # 获取信号源当前快照资产
                    signal_current_asset_raw = get_signal_source_current_asset(self.db_pool, signal_source_uid)
                    if signal_current_asset_raw is None:
                        logger.warning(f"[集合下单] 信号源{signal_source_uid}当前快照资产为空，使用默认值10000")
                        signal_current_asset = 10000.0
                    else:
                        # 确保转换为float类型
                        signal_current_asset = float(signal_current_asset_raw)
                    
                    logger.info(f"[集合下单] 客户{customer_uid}资产: {total_asset}, 信号源{signal_source_uid}当前快照资产: {signal_current_asset}")
                    
                    # 计算客户与信号源的资产比例
                    asset_ratio = float(total_asset) / float(signal_current_asset) if signal_current_asset > 0 else 1.0
                    logger.info(f"[集合下单] 资产比例: {asset_ratio} (客户资产/信号源当前资产)")
                    
                    # 获取信号源实际成交张数
                    raw_sz = order.get('accFillSz', order.get('sz'))
                    if not raw_sz:
                        logger.error(f"[集合下单] 信号单缺少成交张数: {order}")
                        continue
                    
                    # 按照新逻辑计算实际开仓量：实际开仓 = 客户资金/信号源资金 × 开仓数量 ÷ 仓位比例
                    signal_sz = safe_float(raw_sz)
                    position_ratio = safe_float(order.get('position_ratio', 1.0))
                    
                    # 计算实际开仓量（减半）
                    actual_customer_sz = float(signal_sz) * float(asset_ratio) / float(position_ratio)
                    
                    logger.info(f"[集合下单] 新逻辑计算: 信号源成交{signal_sz}张, 资产比例{asset_ratio}, 仓位比例{position_ratio}, 实际客户开仓量{actual_customer_sz}张")
                    
                    # 精度处理
                    sz_precision = get_contract_sz_precision(symbol)
                    # 所有USDT永续合约都是小数张合约，按最小下单量精度处理
                    actual_customer_sz = round(round(actual_customer_sz / min_sz) * min_sz, sz_precision)
                    logger.info(f"[集合下单] 精度处理后: {actual_customer_sz}张")
                    
                    # 如果计算结果为0，但有资产比例，说明信号源成交量太小
                    if actual_customer_sz <= 0 and asset_ratio > 0:
                        logger.warning(f"[集合下单] 客户资产比例{asset_ratio}，但信号源成交{signal_sz}张太小，无法下单")
                        continue
                    
                    # 风控检查：判断实际开仓是否超过净杠杆
                    latest_px = await get_price_on_demand(symbol)
                    
                    # 只计算跟随当前信号源的持仓名义价值
                    signal_following_nominal = 0
                    current_signal_source_uid = order.get('signal_source_uid')
                    for trade in trades:
                        if get_trade_field(trade, 'rule_uid') == current_signal_source_uid:
                            signal_following_nominal += safe_float(trade.volume)
                    
                    this_nominal = actual_customer_sz * multiplier * latest_px
                    max_leverage = safe_float(order.get('max_leverage', 10))
                    # 净杠杆计算（减半）
                    net_leverage = (signal_following_nominal + this_nominal) / total_asset if total_asset > 0 else 0
                    
                    logger.info(f"[风控检查] 客户{customer_uid}实际开仓{actual_customer_sz}张, 合约乘数{multiplier}, 当前价格{latest_px}, 名义价值{this_nominal}, 跟随信号源持仓名义价值{signal_following_nominal}, 净杠杆{net_leverage}, 最大杠杆{max_leverage}")
                    
                    if net_leverage > max_leverage:
                        # 计算最大杠杆下可开仓的张数
                        max_allowed_nominal = max_leverage * total_asset - signal_following_nominal
                        if max_allowed_nominal > 0:
                            # 按最大杠杆剩余值计算可开仓张数
                            max_allowed_sz = max_allowed_nominal / (multiplier * latest_px)
                            # 精度处理
                            max_allowed_sz = round(round(max_allowed_sz / min_sz) * min_sz, sz_precision)
                            
                            if max_allowed_sz >= min_sz:
                                split_sz = max_allowed_sz
                                msg = f'[集合下单] 客户{customer_uid}净杠杆超出限制，按最大杠杆剩余值开仓: {split_sz}张 (原计划{actual_customer_sz}张)'
                                logger.warning(msg)
                                self.log_failure(None, msg)
                            else:
                                msg = f'[集合下单] 客户{customer_uid}最大杠杆剩余值{max_allowed_nominal:.2f}USDT过小，无法满足最小下单量{min_sz}张，跳过该信号'
                                logger.warning(msg)
                                self.log_failure(None, msg)
                                continue
                        else:
                            msg = f'[集合下单] 客户{customer_uid}已达到最大杠杆{max_leverage}，无法继续开仓，跳过该信号'
                            logger.warning(msg)
                            self.log_failure(None, msg)
                            continue
                    else:
                        # 风控通过，使用实际开仓量
                        split_sz = actual_customer_sz
                        logger.info(f"[集合下单] 风控检查通过，最终客户下单量: {split_sz}张")
                except Exception as e:
                    logger.error(f"[集合下单] sz转换异常: {e}, order={order}")
                    continue
                if split_sz <= 0:
                    logger.warning(f"[集合下单] sz<=0, 跳过: {order}")
                    continue
                if split_sz < min_sz:
                    logger.warning(f"[集合下单] split_sz<{min_sz}，客户下单量过小被过滤: split_sz={split_sz}, min_sz={min_sz}, order={order}")
                    continue
                
                # 更新跟随信号源的持仓名义价值（用于下一个信号的风控检查）
                latest_px = await get_price_on_demand(symbol)
                
                this_nominal = split_sz * multiplier * latest_px
                signal_following_nominal += this_nominal
                valid_orders.append(order)
                split_sz_list.append(split_sz)
                logger.info(f"[集合下单] for 循环结束")
            total_sz = round(sum(split_sz_list), 2)
            if total_sz <= 0:
                
                logger.warning(f"[集合下单] 所有信号均未通过净杠杆风控，总下单量为0，跳过: symbol={symbol}")
                return
            # 使用更精确的时间戳和随机数确保唯一性
            import time
            import uuid
            timestamp = int(time.time() * 1000000)  # 微秒级时间戳
            random_suffix = uuid.uuid4().hex[:8]  # 8位随机数
            clOrdId = f'C{customer.customer_uid}{symbol}{timestamp}{random_suffix}'[:32]
            logger.info(f"aggregate_and_place_orders: clOrdId={clOrdId}")
            res = await self.async_place_order(
                    customer=customer,
                    symbol=symbol,
                    direction=direction,
                    pos_side=pos_side,
                    sz=total_sz,
                    trade_uid=clOrdId
                )

            if res and res.get('ordId'):
                ordId = res['ordId']
                avgPx = res.get('avgPx', 0)
                for order in valid_orders:
                    # 计算名义价值：split_sz * multiplier * avgPx
                    multiplier = get_contract_multiplier(symbol)
                    volume_usdt = split_sz * multiplier * avgPx if avgPx > 0 else split_sz * multiplier * latest_px
                    
                    # 为每个order生成唯一的trade_uid
                    order_timestamp = int(time.time() * 1000000)  # 微秒级时间戳
                    order_random = uuid.uuid4().hex[:8]  # 8位随机数
                    # 优化trade_uid长度，确保不超过128个字符
                    # 使用clOrdId的前20位，rule_uid的前10位，时间戳后6位
                    order_trade_uid = f"{clOrdId[:20]}_{order['rule_uid'][:10]}_{order_timestamp % 1000000}_{order_random}"
                    
                    # 使用信号源价格作为初始价格，如果没有则使用缓存价格
                    initial_open_px = avgPx if avgPx > 0 else latest_px
                    
                    logger.info(f"[插入客户单] split_sz={split_sz}, volume_usdt={volume_usdt}, avgPx={avgPx}, latest_px={latest_px}, initial_open_px={initial_open_px}, order={order}")
                    logger.info(f"[插入客户单] trade_uid长度: {len(order_trade_uid)}, trade_uid: {order_trade_uid}")
                    
                    # 检查trade_uid长度
                    if len(order_trade_uid) > 128:
                        logger.error(f"[插入客户单] trade_uid长度超限: {len(order_trade_uid)} > 128, trade_uid: {order_trade_uid}")
                        # 进一步缩短trade_uid
                        order_trade_uid = f"{clOrdId[:15]}_{order['rule_uid'][:8]}_{order_timestamp % 100000}_{order_random}"
                        logger.info(f"[插入客户单] 缩短后trade_uid长度: {len(order_trade_uid)}, trade_uid: {order_trade_uid}")
                    
                    insert_customer_trade(
                        self.db_pool,
                        customer.customer_uid,
                        order['strategy_uid'],
                        order['rule_uid'],
                        symbol,
                        volume_usdt,  # 使用名义价值
                        direction,
                        pos_side,
                        trade_uid=order_trade_uid,
                        is_demo=getattr(customer, 'is_demo', None),
                        volume_contract=split_sz,  # 使用张数
                        open_px=initial_open_px  # 使用初始价格
                    )
                    # 获取信号源订单的ordId作为parent_ordId
                    signal_ordId = None
                    for signal_order in signal_orders:
                        if signal_order.get('signal_source_uid'):
                            signal_ordId = signal_order.get('signal_ordId')
                            break
                    
                    # 确保signal_ordId不为空，如果为空则使用ordId作为备选
                    if not signal_ordId:
                        signal_ordId = ordId
                    
                    self.db_pool.execute(
                        "UPDATE customer_trades SET parent_clOrdId=%s, parent_ordId=%s, split_ratio=%s WHERE trade_uid=%s",
                        (clOrdId, signal_ordId, split_sz / total_sz if total_sz > 0 else 0, order_trade_uid)
                    )
                logger.info(f"[集合下单] 总单clOrdId={clOrdId}, ordId={ordId}, 总下单量={total_sz}, 子单数={len(valid_orders)}")
            else:
                logger.error(f"[集合下单] 总单下单失败: {res}")
        except Exception as e:
            logger.error(f"batch_aggregate_place_orders异常: {e}")

    async def batch_aggregate_close_orders(self, customer, symbol, direction, pos_side, signal_orders):
        """
        集合平单：同一币种/方向/时刻的所有需平仓子单合并为一个总单，按份额拆分写入customer_trades。
        signal_orders: List[dict]，每个dict包含signal_source_uid, rule_uid, strategy_uid, sz(应下单张数), max_leverage等
        """
        try:
            valid_orders = []
            logger.info(f"[集合平单] 入口参数: customer={get_customer_uid(customer)}, symbol={symbol}, signal_orders={signal_orders}")
            trades = self.get_open_trades(get_customer_uid(customer))
            total_nominal = sum([safe_float(t.volume) for t in trades])
            if hasattr(customer, 'total_asset') and safe_float(getattr(customer, 'total_asset', 0)) > 0:
                total_asset = float(safe_float(customer.total_asset))
            elif hasattr(customer, 'init_asset') and safe_float(getattr(customer, 'init_asset', 0)) > 0:
                total_asset = float(safe_float(customer.init_asset))
            else:
                total_asset = 1.0
            latest_px = await get_price_on_demand(symbol) or 1
            multiplier = get_contract_multiplier(symbol)
            split_sz_list = []
            valid_orders = []
            for order in signal_orders:
                logger.info(f"[集合平单] for 循环开始，信号单数: {len(signal_orders)}")
                logger.info(f"[集合平单] 检查信号单: {order}")
                min_sz = get_contract_min_sz(symbol)
                logger.info(f"[集合平单] symbol={symbol}, sz={order['sz']}, min_sz={min_sz}")
                try:
                    # 获取信号源账户额
                    signal_source_uid = order.get('signal_source_uid')
                    if not signal_source_uid:
                        logger.error(f"[集合平单] 信号单缺少signal_source_uid: {order}")
                        continue
                    
                    # 获取信号源当前快照资产
                    signal_current_asset_raw = get_signal_source_current_asset(self.db_pool, signal_source_uid)
                    if signal_current_asset_raw is None:
                        logger.warning(f"[集合平单] 信号源{signal_source_uid}当前快照资产为空，使用默认值10000")
                        signal_current_asset = 10000.0
                    else:
                        # 确保转换为float类型
                        signal_current_asset = float(signal_current_asset_raw)
                    
                    logger.info(f"[集合平单] 客户{get_customer_uid(customer)}资产: {total_asset}, 信号源{signal_source_uid}当前快照资产: {signal_current_asset}")
                    
                    # 计算客户与信号源的资产比例
                    asset_ratio = float(total_asset) / float(signal_current_asset) if signal_current_asset > 0 else 1.0
                    logger.info(f"[集合平单] 资产比例: {asset_ratio} (客户资产/信号源当前资产)")
                    
                    # 获取信号源实际成交张数
                    raw_sz = order.get('accFillSz', order.get('sz'))
                    if not raw_sz:
                        logger.error(f"[集合平单] 信号单缺少成交张数: {order}")
                        continue
                    
                    # 按照新逻辑计算实际平仓量：实际平仓 = 客户资金/信号源资金 × 平仓数量 ÷ 仓位比例
                    signal_sz = safe_float(raw_sz)
                    position_ratio = safe_float(order.get('position_ratio', 1.0))
                    
                    # 计算实际平仓量
                    actual_customer_sz = float(signal_sz) * float(asset_ratio) / float(position_ratio)
                    
                    logger.info(f"[集合平单] 新逻辑计算: 信号源成交{signal_sz}张, 资产比例{asset_ratio}, 仓位比例{position_ratio}, 实际客户平仓量{actual_customer_sz}张")
                    
                    # 精度处理
                    sz_precision = get_contract_sz_precision(symbol)
                    # 所有USDT永续合约都是小数张合约，按最小下单量精度处理
                    actual_customer_sz = round(round(actual_customer_sz / min_sz) * min_sz, sz_precision)
                    logger.info(f"[集合平单] 精度处理后: {actual_customer_sz}张")
                    
                    # 如果计算结果为0，但有资产比例，说明信号源成交量太小
                    if actual_customer_sz <= 0 and asset_ratio > 0:
                        logger.warning(f"[集合平单] 客户资产比例{asset_ratio}，但信号源成交{signal_sz}张太小，无法平仓")
                        continue
                    
                    # 平仓不需要风控检查，直接使用实际平仓量
                    split_sz = actual_customer_sz
                    logger.info(f"[集合平单] 最终客户平仓量: {split_sz}张")
                except Exception as e:
                    logger.error(f"[集合平单] sz转换异常: {e}, order={order}")
                    continue
                if split_sz <= 0:
                    logger.warning(f"[集合平单] sz<=0, 跳过: {order}")
                    continue
                if split_sz < min_sz:
                    logger.warning(f"[集合平单] split_sz<{min_sz}，客户平仓量过小被过滤: split_sz={split_sz}, min_sz={min_sz}, order={order}")
                    logger.warning(f"[集合平单] sz<{min_sz}, 跳过: {order}")
                    continue
                this_nominal = split_sz * multiplier * latest_px
                max_leverage = safe_float(order.get('max_leverage', 10))
                # 平仓时净杠杆应该减少，而不是增加
                net_leverage = (total_nominal - this_nominal) / total_asset if total_asset > 0 else 0
                # 新增风控调试日志
                logger.info(f"[风控调试] customer={get_customer_uid(customer)}, total_asset={total_asset}, split_sz={split_sz}, multiplier={multiplier}, latest_px={latest_px}, this_nominal={this_nominal}, total_nominal={total_nominal}, net_leverage={net_leverage}, max_leverage={max_leverage}")

                if net_leverage > max_leverage:
                    msg = f'[集合平单] 客户{get_customer_uid(customer)}信号{order.get("rule_uid")}净杠杆{net_leverage:.2f}超出最大限制{max_leverage}，跳过该信号'
                    logger.warning(msg)
                    self.log_failure(None, msg)
                    continue
                valid_orders.append(order)
                split_sz_list.append(split_sz)
                # 平仓时应该减少总名义价值，而不是增加
                total_nominal -= this_nominal
                logger.info(f"[集合平单] for 循环结束")
            total_sz = round(sum(split_sz_list), 2)
            if total_sz <= 0:
                logger.warning(f"[集合平单] 所有信号均未通过净杠杆风控，总平仓量为0，跳过: symbol={symbol}")
                return
            # 使用更精确的时间戳和随机数确保唯一性
            import time
            import uuid
            timestamp = int(time.time() * 1000000)  # 微秒级时间戳
            random_suffix = uuid.uuid4().hex[:8]  # 8位随机数
            clOrdId = f'C{customer.customer_uid}{symbol}{timestamp}{random_suffix}'[:32]
            logger.info(f"aggregate_and_close_orders: clOrdId={clOrdId}")
            res = await self.async_place_order(
                    customer=customer,
                    symbol=symbol,
                    direction=direction,
                    pos_side=pos_side,
                    sz=total_sz,
                    trade_uid=clOrdId,
                    reduceOnly=True,
                    tag='6618f740e7f1BCDE'
                )

            if res and res.get('ordId'):
                ordId = res['ordId']
                avgPx = res.get('avgPx', 0)
                for order in valid_orders:
                    # 为每个order生成唯一的trade_uid
                    order_timestamp = int(time.time() * 1000000)  # 微秒级时间戳
                    order_random = uuid.uuid4().hex[:8]  # 8位随机数
                    # 优化trade_uid长度，确保不超过128个字符
                    # 使用clOrdId的前20位，rule_uid的前10位，时间戳后6位
                    order_trade_uid = f"{clOrdId[:20]}_{order['rule_uid'][:10]}_{order_timestamp % 1000000}_{order_random}"
                    
                    # 使用信号源价格作为初始价格，如果没有则使用缓存价格
                    initial_open_px = avgPx if avgPx > 0 else latest_px
                    
                    # logger.info(f"[插入客户单] split_sz={split_sz}, volume_usdt={volume_usdt}, avgPx={avgPx}, latest_px={latest_px}, initial_open_px={initial_open_px}, order={order}")
                    # logger.info(f"[插入客户单] trade_uid长度: {len(order_trade_uid)}, trade_uid: {order_trade_uid}")
                    
                    # 检查trade_uid长度
                    if len(order_trade_uid) > 128:
                        logger.error(f"[插入客户单] trade_uid长度超限: {len(order_trade_uid)} > 128, trade_uid: {order_trade_uid}")
                        # 进一步缩短trade_uid
                        order_trade_uid = f"{clOrdId[:15]}_{order['rule_uid'][:8]}_{order_timestamp % 100000}_{order_random}"
                        logger.info(f"[插入客户单] 缩短后trade_uid长度: {len(order_trade_uid)}, trade_uid: {order_trade_uid}")
                    
                    insert_customer_trade(
                        self.db_pool,
                        customer.customer_uid,
                        order['strategy_uid'],
                        order['rule_uid'],
                        symbol,
                        volume_usdt,  # 使用名义价值
                        direction,
                        pos_side,
                        trade_uid=order_trade_uid,
                        is_demo=getattr(customer, 'is_demo', None),
                        volume_contract=split_sz,  # 使用张数
                        open_px=initial_open_px  # 使用初始价格
                    )
                    self.db_pool.execute(
                        "UPDATE customer_trades SET parent_clOrdId=%s, parent_ordId=%s, status='closed' WHERE trade_uid=%s",
                        (clOrdId, ordId, order_trade_uid)
                    )
                logger.info(f"[集合平单] 总单clOrdId={clOrdId}, ordId={ordId}, 总平仓量={total_sz}, 子单数={len(valid_orders)}")
            else:
                logger.error(f"[集合平单] 总单平仓失败: {res}")
        except Exception as e:
            logger.error(f"batch_aggregate_close_orders异常: {e}")

    async def batch_close_trades_total_order(self, trades: List[CustomerTrade], symbol: str, pos_side: str):
        """
        批量平仓：处理多个客户都根据相同信号源连续开仓的情况
        - 每个客户内部：总单分摊（合并该客户的所有持仓）
        - 不同客户之间：分别平仓（每个客户独立平仓）
        """
        # 强制查库，确保 trades 列表完整
        is_demo = get_global_is_demo()
        trade_uids = [get_trade_field(t, 'trade_uid') for t in trades]
        if not trade_uids:
            logger.error(f"[批量平仓] 传入trades为空，symbol={symbol}, pos_side={pos_side}")
            return
        
        # 生成唯一的平仓标识，用于防重复
        signal_source_uid = get_trade_field(trades[0], 'rule_uid') if trades else None
        close_key = f"{signal_source_uid}_{symbol}_{pos_side}_{is_demo}"
        
        # 检查是否已经在处理中
        if hasattr(self, '_processing_close_keys') and close_key in self._processing_close_keys:
            logger.info(f"[批量平仓] 平仓操作已在处理中，跳过重复请求: {close_key}")
            return
        
        # 添加到处理中集合
        if not hasattr(self, '_processing_close_keys'):
            self._processing_close_keys = set()
        self._processing_close_keys.add(close_key)
        
        # 使用信号源级别的锁防止同一信号源并发平仓
        signal_lock = get_signal_processing_lock(signal_source_uid, symbol, pos_side)
        
        try:
            # 在信号源锁保护下执行平仓逻辑
            with signal_lock:
                # 查库获取所有 open 状态、同 symbol、同 pos_side 的 trade
                db_trades = self.db_pool.query(
                    "SELECT * FROM customer_trades WHERE symbol=%s AND pos_side=%s AND status='open' AND is_demo=%s",
                    (symbol, pos_side, is_demo)
                )
                
                # 过滤掉已经处理过的持仓（通过检查status字段）
                filtered_trades = []
                for trade in db_trades:
                    status = get_trade_field(trade, 'status')
                    if status == 'open':  # 状态为open说明还没有平仓
                        filtered_trades.append(trade)
                    else:
                        logger.info(f"[批量平仓] 跳过已平仓的持仓: {get_trade_field(trade, 'trade_uid')}, status={status}")
                
                if filtered_trades:
                    trades = filtered_trades
                    logger.info(f"[批量平仓] 过滤后剩余 {len(filtered_trades)} 个未平仓的持仓")
                else:
                    logger.info(f"[批量平仓] 所有持仓都已平仓，无需重复处理")
                    return
                logger.info(f"[批量平仓] batch_close_trades_total_order trades count={len(trades)}, trade_uids={[get_trade_field(t, 'trade_uid') for t in trades]}, is_demo={is_demo}")
                
                # 按客户分组
                customer_trades = {}
                for trade in trades:
                    customer_uid = get_trade_field(trade, 'customer_uid')
                    if customer_uid not in customer_trades:
                        customer_trades[customer_uid] = []
                    customer_trades[customer_uid].append(trade)
                
                logger.info(f"[批量平仓] 按客户分组: {list(customer_trades.keys())}")
                
                # 创建客户平仓任务列表
                customer_close_tasks = []
                
                # 处理每个客户的平仓
                for customer_uid, customer_trade_list in customer_trades.items():
                    logger.info(f"[客户平仓] 处理客户{customer_uid}，持仓数量: {len(customer_trade_list)}")
                    
                    # 计算该客户的总平仓量
                    total_sz = sum(safe_float(get_trade_field(t, 'volume_contract')) for t in customer_trade_list)
                    if total_sz <= 0:
                        logger.warning(f"[客户平仓] 客户{customer_uid}总平仓张数为0，跳过")
                        continue
                    
                    # 获取客户信息
                    customer_data = get_customer_by_id(self.db_pool, customer_uid, is_demo=is_demo)
                    if not customer_data:
                        logger.error(f"[客户平仓] 未找到客户{customer_uid}，跳过")
                        continue
                    
                    # 将字典转换为Customer对象
                    customer = self.safe_customer(customer_data)
                    
                    direction = 'sell' if get_trade_field(customer_trade_list[0], 'pos_side') == 'long' else 'buy'
                    
                    # 生成客户专用的clOrdId
                    if len(customer_trade_list) == 1:
                        # 单个持仓，直接平仓
                        trade_uid = get_trade_field(customer_trade_list[0], 'trade_uid')
                        customer_clOrdId = f"SINGLE_CLOSE_{customer_uid}_{symbol}_{pos_side}_{int(time.time())}"[:32]
                        logger.info(f"[客户平仓] 客户{customer_uid}单个持仓平仓: symbol={symbol}, pos_side={pos_side}, total_sz={total_sz}, clOrdId={customer_clOrdId}")
                    else:
                        # 多个持仓，总单分摊
                        customer_clOrdId = f"TOTAL_CLOSE_{customer_uid}_{symbol}_{pos_side}_{int(time.time())}"[:32]
                        logger.info(f"[客户平仓] 客户{customer_uid}多持仓总单分摊: symbol={symbol}, pos_side={pos_side}, total_sz={total_sz}, clOrdId={customer_clOrdId}, 持仓数={len(customer_trade_list)}")
                    
                    # 创建客户平仓任务
                    customer_close_tasks.append(self._execute_customer_close(
                        customer, symbol, direction, pos_side, total_sz, customer_clOrdId, customer_trade_list
                    ))
                
                # 并发执行所有客户的平仓任务
                if customer_close_tasks:
                    logger.info(f"[批量平仓] 开始并发执行{len(customer_close_tasks)}个客户的平仓任务")
                    results = await asyncio.gather(*customer_close_tasks, return_exceptions=True)
                    logger.info(f"[批量平仓] 完成所有客户平仓任务")
                    
                    # 检查结果
                    success_count = 0
                    error_count = 0
                    for i, result in enumerate(results):
                        if isinstance(result, Exception):
                            logger.error(f"[批量平仓] 客户{i+1}平仓异常: {result}")
                            error_count += 1
                        elif result and result.get('success'):
                            success_count += 1
                        else:
                            error_count += 1
                    
                    logger.info(f"[批量平仓] 平仓结果: 成功{success_count}个，失败{error_count}个")
                    
                    # 返回结果
                    if error_count == 0:
                        return {'success': True, 'message': f'所有客户平仓成功({success_count}个)'}
                    elif success_count > 0:
                        return {'success': True, 'message': f'部分客户平仓成功({success_count}/{len(customer_close_tasks)}个)'}
                    else:
                        return {'success': False, 'error': '所有客户平仓失败'}
                else:
                    logger.info(f"[批量平仓] 没有需要平仓的客户")
                    return {'success': True, 'message': '没有需要平仓的客户'}
                    
        finally:
            # 清理处理中标识
            self._processing_close_keys.discard(close_key)

    async def batch_close_trades(self, trades: List[CustomerTrade], symbol: str, pos_side: str, signal_volume: float = None, rule_ratio_map: dict = None, signal_source_uid: str = None, signal_trade_uid: str = None, signal_original_volume: float = None, signal_reduce_ratio: float = None, is_fully_closed: bool = None):
        """
        按信号源减仓比例FIFO分配到客户所有open持仓，累加close_volume_contract，只平需要平的单。
        """
        
        # 强制过滤trades，只保留status=open的trade，避免处理已closed的trade
        trades = [t for t in trades if get_trade_field(t, 'status') == 'open']
        if not trades:
            logger.info(f"[客户减仓] 没有找到status=open的trade，跳过处理")
            return
        
        # 使用trade_uid进行去重，避免重复处理同一个trade
        unique_trades = []
        processed_trade_uids = set()
        for trade in trades:
            trade_uid = get_trade_field(trade, 'trade_uid')
            if trade_uid not in processed_trade_uids:
                unique_trades.append(trade)
                processed_trade_uids.add(trade_uid)
            else:
                logger.warning(f"[客户减仓] 发现重复trade_uid，跳过: {trade_uid}")
        
        trades = unique_trades
        logger.info(f"[客户减仓] 去重后trades数量: {len(trades)}")
        
        # 查询信号源累计减仓张数和总持仓张数
        is_demo = get_global_is_demo()
        logger.info(f"[客户减仓] 查询信号源持仓: signal_source_uid={signal_source_uid}, symbol={symbol}, pos_side={pos_side}, is_demo={is_demo}")
        
        if signal_source_uid:
            # 如果有指定信号源ID，则查询该信号源的所有持仓（包括已关闭的）
            signal_rows = self.db_pool.query(
                "SELECT * FROM signal_account_trades WHERE signal_source_uid=%s AND symbol=%s AND pos_side=%s AND is_demo=%s and status='open' ORDER BY created_at ASC",
                (signal_source_uid, symbol, pos_side, is_demo)
            )
            logger.info(f"[客户减仓] 查询指定信号源持仓结果: {len(signal_rows)}条记录")
        else:
            # 如果没有指定信号源ID，则查询所有信号源的持仓（兼容旧逻辑）
            signal_rows = self.db_pool.query(
                "SELECT * FROM signal_account_trades WHERE symbol=%s AND pos_side=%s AND is_demo=%s ORDER BY created_at ASC",
                (symbol, pos_side, is_demo)
            )
            logger.info(f"[客户减仓] 查询所有信号源持仓结果: {len(signal_rows)}条记录")
        
        # 打印查询到的信号源持仓详情
        for i, row in enumerate(signal_rows):
            logger.info(f"[客户减仓] 信号源持仓{i+1}: signal_source_uid={row.get('signal_source_uid')}, volume_contract={row.get('volume_contract')}, close_volume_contract={row.get('close_volume_contract')}, status={row.get('status')}")
        
        # 计算指定信号源的总原始持仓张数（包括已平仓的）
        # total_signal_original = sum(float(row.get('volume_contract', 0) or 0) for row in signal_rows if row.get('signal_source_uid') == signal_source_uid)
        # 计算指定信号源的open持仓的总张数和累计已减仓张数
        total_signal_contract = sum(float(row.get('volume_contract', 0) or 0) for row in signal_rows if row.get('signal_source_uid') == signal_source_uid and row.get('status') == 'open')
        total_signal_closed = sum(float(row.get('close_volume_contract', 0) or 0) for row in signal_rows if row.get('signal_source_uid') == signal_source_uid and row.get('status') == 'open')
        
                # 如果有具体的信号源订单信息，使用订单级别的减仓逻辑
        if signal_trade_uid and signal_original_volume and signal_reduce_ratio is not None:
            logger.info(f"[客户减仓] 使用订单级别减仓逻辑: signal_trade_uid={signal_trade_uid}, signal_original_volume={signal_original_volume}, signal_reduce_ratio={signal_reduce_ratio}")
            
            # 找到跟随这个信号源订单的客户订单
            # 首先尝试通过parent_ordId精确匹配
            customer_trades_for_signal_order = [trade for trade in trades if get_trade_field(trade, 'parent_ordId') == signal_trade_uid and get_trade_field(trade, 'status') == 'open']
            
            # 如果没有找到，尝试通过rule_uid和信号源ID匹配（兼容旧逻辑）
            if not customer_trades_for_signal_order:
                logger.info(f"[客户减仓] 通过parent_ordId未找到跟随订单，尝试通过rule_uid匹配: signal_trade_uid={signal_trade_uid}")
                customer_trades_for_signal_order = [trade for trade in trades if get_trade_field(trade, 'rule_uid') == signal_source_uid and get_trade_field(trade, 'status') == 'open']
                if customer_trades_for_signal_order:
                    logger.info(f"[客户减仓] 通过rule_uid找到{len(customer_trades_for_signal_order)}个跟随订单")
            
            # 如果还是没有找到，尝试通过信号源ID匹配所有相关订单（最后的备选方案）
            if not customer_trades_for_signal_order:
                logger.info(f"[客户减仓] 通过rule_uid也未找到跟随订单，尝试通过信号源ID匹配所有相关订单: signal_source_uid={signal_source_uid}")
                customer_trades_for_signal_order = [trade for trade in trades if get_trade_field(trade, 'status') == 'open']
                if customer_trades_for_signal_order:
                    logger.info(f"[客户减仓] 通过信号源ID匹配找到{len(customer_trades_for_signal_order)}个相关订单")
            
            # 添加调试日志，显示所有trades的parent_ordId和rule_uid
            logger.info(f"[客户减仓] 调试信息: 总trades数量={len(trades)}, signal_trade_uid={signal_trade_uid}, signal_source_uid={signal_source_uid}")
            for i, trade in enumerate(trades[:5]):  # 只显示前5个，避免日志过长
                trade_parent_ordId = get_trade_field(trade, 'parent_ordId')
                trade_rule_uid = get_trade_field(trade, 'rule_uid')
                trade_status = get_trade_field(trade, 'status')
                logger.info(f"[客户减仓] trade{i+1}: trade_uid={get_trade_field(trade, 'trade_uid')}, parent_ordId={trade_parent_ordId}, rule_uid={trade_rule_uid}, status={trade_status}")
            
            if customer_trades_for_signal_order:
                logger.info(f"[客户减仓] 找到{len(customer_trades_for_signal_order)}个跟随信号源订单的客户订单")
                total_customer_reduce = 0
                
                # 为每个跟随的客户订单计算减仓量
                for customer_trade in customer_trades_for_signal_order:
                    customer_volume = float(get_trade_field(customer_trade, 'volume_contract') or 0)
                    
                    # 判断信号源订单是否全平
                    if is_fully_closed:
                        # 信号源订单全平，客户订单也全平
                        customer_reduce = customer_volume
                        logger.info(f"[客户减仓] 信号源订单全平，客户订单也全平")
                    else:
                        # 信号源订单部分减仓，客户订单按比例减仓（减半）
                        customer_reduce = customer_volume * signal_reduce_ratio
                    
                    # 按照合约张数精度进行收敛
                    sz_precision = get_contract_sz_precision(symbol)
                    customer_reduce = round(customer_reduce, sz_precision)
                    
                    trade_uid = get_trade_field(customer_trade, 'trade_uid')
                    logger.info(f"[客户减仓] 客户订单{trade_uid}: 原始持仓={customer_volume}, 减仓比例={signal_reduce_ratio}, 减仓量={customer_reduce}")
                    total_customer_reduce += customer_reduce
                
                logger.info(f"[客户减仓] 订单级别减仓总计: {total_customer_reduce}")
                
                # 执行订单级别减仓下单
                if total_customer_reduce > 0:
                    logger.info(f"[客户减仓] 开始执行订单级别减仓下单")
                    # 按客户分组执行减仓
                    customer_reduce_map = {}
                    for customer_trade in customer_trades_for_signal_order:
                        customer_uid = get_trade_field(customer_trade, 'customer_uid')
                        if customer_uid not in customer_reduce_map:
                            customer_reduce_map[customer_uid] = []
                        customer_reduce_map[customer_uid].append(customer_trade)
                    
                    # 🚀 性能优化：并行处理所有客户减仓
                    logger.info(f"[客户减仓] 🚀 开始并行处理{len(customer_reduce_map)}个客户减仓")
                    start_time = time.time()
                    
                    # 创建并行任务列表
                    parallel_tasks = []
                    
                    # 为每个客户创建减仓任务
                    for customer_uid, customer_trades in customer_reduce_map.items():
                        # 计算该客户的总减仓量（注意：在上面2278-2296行已经计算过每个订单的减仓量了，这里需要汇总）
                        # 需要从customer_trades_for_signal_order中找到对应的已计算减仓量
                        customer_total_reduce = 0
                        for customer_trade in customer_trades:
                            customer_volume = float(get_trade_field(customer_trade, 'volume_contract') or 0)
                            # 判断信号源订单是否全平
                            if is_fully_closed:
                                # 信号源订单全平，客户订单也全平
                                customer_reduce = customer_volume
                            else:
                                # 信号源订单部分减仓，客户订单按比例减仓
                                customer_reduce = customer_volume * signal_reduce_ratio
                            # 按照合约张数精度进行收敛
                            sz_precision = get_contract_sz_precision(symbol)
                            customer_reduce = round(customer_reduce, sz_precision)
                            customer_total_reduce += customer_reduce
                        
                        if customer_total_reduce > 0:
                            # 创建异步减仓任务
                            task = self._execute_customer_reduce_order(
                                customer_uid, customer_trades, symbol, pos_side, 
                                customer_total_reduce, signal_reduce_ratio, is_demo
                            )
                            parallel_tasks.append(task)
                    
                    # 并行执行所有减仓任务
                    if parallel_tasks:
                        logger.info(f"[客户减仓] 🚀 并行执行{len(parallel_tasks)}个减仓任务")
                        results = await asyncio.gather(*parallel_tasks, return_exceptions=True)
                        
                        # 处理结果
                        success_count = 0
                        for i, result in enumerate(results):
                            if isinstance(result, Exception):
                                logger.error(f"[客户减仓] 客户{i+1}减仓任务异常: {result}")
                            else:
                                success_count += 1
                        
                        end_time = time.time()
                        total_time = end_time - start_time
                        logger.info(f"[客户减仓] 🚀 并行减仓完成: {success_count}/{len(parallel_tasks)}成功, 总耗时: {total_time:.2f}秒")
                    else:
                        logger.info(f"[客户减仓] 没有需要减仓的客户")
                    
                    # 标记已经执行了订单级别减仓，跳过FIFO分配
                    has_executed_order_level_reduce = True
                else:
                    logger.info(f"[客户减仓] 订单级别减仓量为0，跳过下单")
                    has_executed_order_level_reduce = False
            else:
                logger.warning(f"[客户减仓] 未找到跟随信号源订单{signal_trade_uid}的客户订单")
                total_customer_reduce = 0
                has_executed_order_level_reduce = False
        else:
            # 使用原有的总减仓逻辑
            has_executed_order_level_reduce = False
            # 计算本次减仓比例：本次减仓量 / 总原始持仓量
            # 如果有传入signal_volume，使用本次减仓量；否则使用累计减仓比例
            if signal_volume is not None and signal_volume > 0:
                # 使用本次减仓量计算比例（基于当前open持仓，而不是总原始持仓）
                signal_reduce_ratio = signal_volume / total_signal_contract if total_signal_contract > 0 else 0
                logger.info(f"[客户减仓] 信号源当前open持仓={total_signal_contract}, 本次减仓量={signal_volume}, 减仓比例={signal_reduce_ratio}")
                
                # 计算客户总减仓量：按信号源减仓比例计算
                # 计算跟随当前信号源的客户总持仓量
                customer_trades_for_signal = [trade for trade in trades if get_trade_field(trade, 'rule_uid') == signal_source_uid and get_trade_field(trade, 'status') == 'open']
                total_customer_contract = sum(float(get_trade_field(trade, 'volume_contract') or 0) for trade in customer_trades_for_signal)
                
                # 按比例计算客户减仓量：客户总持仓量 × 信号源减仓比例（减半）
                total_customer_reduce = total_customer_contract * signal_reduce_ratio
                
                # 按照合约张数精度进行收敛
                sz_precision = get_contract_sz_precision(symbol)
                total_customer_reduce = round(total_customer_reduce, sz_precision)
                logger.info(f"[客户减仓] 信号源减仓比例={signal_reduce_ratio}, 客户总持仓量={total_customer_contract}, 计算客户减仓量={total_customer_reduce}")
            else:
                # 使用累计减仓比例
                ratio = min((total_signal_closed) / total_signal_contract if total_signal_contract > 0 else 1, 1.0)
                logger.info(f"[客户减仓] 信号源总持仓={total_signal_contract}, 累计已减仓={total_signal_closed}, 减仓比例={ratio}")
                total_customer_reduce = 0
        
        # 检查信号源是否全平
        signal_source_closed = False
        if signal_source_uid:
            # 查询信号源是否还有open持仓
            open_signal_trades = self.db_pool.query(
                "SELECT 1 FROM signal_account_trades WHERE signal_source_uid=%s AND symbol=%s AND pos_side=%s AND is_demo=%s AND status='open'",
                (signal_source_uid, symbol, pos_side, is_demo)
            )
            if not open_signal_trades:
                signal_source_closed = True
                logger.info(f"[客户减仓] 信号源已全平，强制客户全平")
        
        # 如果信号源全平，查询所有相关客户的所有open持仓，一次性处理
        if signal_source_closed:
            logger.info(f"[客户减仓] 信号源全平，查询所有相关客户持仓")
            # 先查询所有相关客户持仓（限制状态为open）- 修复JOIN重复问题
            all_customer_trades_debug = self.db_pool.query(
                "SELECT DISTINCT ct.* FROM customer_trades ct WHERE ct.rule_uid = %s AND ct.symbol = %s AND ct.pos_side = %s AND ct.is_demo = %s and status='open'",
                (signal_source_uid, symbol, pos_side, is_demo)
            )
            # logger.info(f"[客户减仓] 查询条件: rule_uid={signal_source_uid}, symbol={symbol}, pos_side={pos_side}, is_demo={is_demo}")
            logger.info(f"[客户减仓] 所有相关客户持仓（限制状态为open）: {len(all_customer_trades_debug)}条")
            for i, trade in enumerate(all_customer_trades_debug):
                logger.info(f"[客户减仓] 客户持仓{i+1}: customer_uid={get_trade_field(trade, 'customer_uid')}, trade_uid={get_trade_field(trade, 'trade_uid')}, volume_contract={get_trade_field(trade, 'volume_contract')}, status={get_trade_field(trade, 'status')}, rule_uid={get_trade_field(trade, 'rule_uid')}")
            
            # 查询所有使用该信号源的客户持仓 - 修复JOIN重复问题
            all_customer_trades = self.db_pool.query(
                "SELECT DISTINCT ct.* FROM customer_trades ct WHERE ct.rule_uid = %s AND ct.symbol = %s AND ct.pos_side = %s AND ct.status = 'open' AND ct.is_demo = %s",
                (signal_source_uid, symbol, pos_side, is_demo)
            )
            if all_customer_trades:
                logger.info(f"[客户减仓] 找到{len(all_customer_trades)}个客户持仓需要全平")
                # 打印每个客户的详细信息
                for i, trade in enumerate(all_customer_trades):
                    logger.info(f"[客户减仓] 客户持仓{i+1}: customer_uid={get_trade_field(trade, 'customer_uid')}, trade_uid={get_trade_field(trade, 'trade_uid')}, volume_contract={get_trade_field(trade, 'volume_contract')}, status={get_trade_field(trade, 'status')}")
                # 一次性处理所有客户持仓
                await self.batch_close_trades_total_order(all_customer_trades, symbol, pos_side)
                # 继续执行全平补全逻辑，确保数据库状态正确更新
                logger.info(f"[客户减仓] 信号源全平，执行全平补全逻辑")
                # 强制设置total_customer_reduce为无穷大，表示全平
                total_customer_reduce = float('inf')
            else:
                logger.info(f"[客户减仓] 没有找到需要平仓的客户持仓")
                return
        
        # 如果信号源全平，强制客户全平
        if signal_source_closed:
            total_customer_reduce = float('inf')  # 设置为无穷大，表示全平
        
        # 客户侧FIFO分配减仓（只对open的trade，且每个trade只分配一次且不超过自身持仓）
        # 如果信号源全平，跳过减仓分配循环，直接执行全平补全逻辑
        # 如果已经使用订单级别减仓逻辑，跳过FIFO分配
        if not signal_source_closed and not (signal_trade_uid and signal_original_volume and signal_reduce_ratio is not None) and not has_executed_order_level_reduce:
            # 按客户分组处理减仓（只处理跟随当前信号源的客户）
            customer_trades_map = {}
            for trade in trades:
                if get_trade_field(trade, 'status') == 'open' and get_trade_field(trade, 'rule_uid') == signal_source_uid:
                    customer_uid = get_trade_field(trade, 'customer_uid')
                    if customer_uid not in customer_trades_map:
                        customer_trades_map[customer_uid] = []
                    customer_trades_map[customer_uid].append(trade)
            
            logger.info(f"[客户减仓] 按客户分组: {list(customer_trades_map.keys())}")
            
            # 为每个客户单独处理减仓（客户跟随信号源的FIFO减仓模式）
            for customer_uid, customer_trades in customer_trades_map.items():
                # 按时间排序该客户的订单（FIFO原则）
                customer_trades_sorted = sorted(customer_trades, key=lambda t: getattr(t, 'created_at', 0))
                
                # 计算该客户的总持仓量
                customer_total_volume = sum(float(get_trade_field(t, 'volume_contract')) for t in customer_trades_sorted)
                
                # 按信号源减仓比例计算客户总减仓量
                customer_reduce_ratio = signal_reduce_ratio if 'signal_reduce_ratio' in locals() else 0
                customer_total_reduce = customer_total_volume * customer_reduce_ratio
                
                # 按照合约张数精度进行收敛
                sz_precision = get_contract_sz_precision(symbol)
                customer_total_reduce = round(customer_total_reduce, sz_precision)
                
                logger.info(f"[客户减仓] 客户{customer_uid}总持仓量={customer_total_volume}, 信号源减仓比例={customer_reduce_ratio}, 客户总减仓量={customer_total_reduce}")
                
                # FIFO分配客户减仓量（跟随信号源减仓模式）
                customer_remaining_reduce = customer_total_reduce
                sz_precision = get_contract_sz_precision(symbol)
                min_sz = get_contract_min_sz(symbol)
                logger.info(f"[客户减仓] 客户{customer_uid}精度设置: sz_precision={sz_precision}, min_sz={min_sz}")
                
                for trade in customer_trades_sorted:
                    if customer_remaining_reduce <= 0:
                        break
                    
                    trade_uid = get_trade_field(trade, 'trade_uid')
                    volume_contract = float(get_trade_field(trade, 'volume_contract'))
                    closed_contract = float(get_trade_field(trade, 'close_volume_contract') or 0)
                    
                    # 计算剩余持仓量
                    remain = volume_contract - closed_contract
                    
                    # FIFO模式分配减仓量（优先减仓最早开的仓位）
                    # 确保不超过剩余持仓和剩余减仓量
                    this_reduce = min(remain, customer_remaining_reduce)
                # 如果减仓量太小，尝试分配更多给这个trade
                if this_reduce > 0 and this_reduce < min_sz:
                    # 尝试分配最小单位给这个trade
                    this_reduce = min(remain, customer_remaining_reduce, min_sz)
                # 如果还是太小，尝试分配更多
                if this_reduce < min_sz and customer_remaining_reduce >= min_sz:
                    this_reduce = min(remain, customer_remaining_reduce)
                    
                    if this_reduce <= 0:
                        continue
                    # 按精度处理客户减仓量
                    this_reduce = round(this_reduce, sz_precision)
                    logger.info(f"[客户减仓] trade_uid={trade_uid}, volume_contract={volume_contract}, remain={remain}, this_reduce={this_reduce}, min_sz={min_sz}")
                    if this_reduce < min_sz:
                        logger.info(f"[客户减仓] 客户减仓量{this_reduce}小于最小单位{min_sz}，跳过: trade_uid={trade_uid}")
                        continue
                # 真实下单
                customer_uid = get_trade_field(trade, 'customer_uid')
                customer_data = get_customer_by_id(self.db_pool, customer_uid, is_demo=is_demo)
                if not customer_data:
                    logger.error(f"[客户减仓] 未找到客户{customer_uid}，跳过")
                    continue
                
                # 将字典转换为Customer对象
                customer = self.safe_customer(customer_data)
                direction = 'sell' if get_trade_field(trade, 'pos_side') == 'long' else 'buy'
                clOrdId = f"REDUCE_{customer_uid}_{symbol}_{pos_side}_{int(time.time())}"[:32]
                logger.info(f"[客户减仓] 客户{customer_uid}减仓下单: symbol={symbol}, pos_side={pos_side}, sz={this_reduce}, clOrdId={clOrdId}")
                res = await self.async_place_order(
                    customer=customer,
                    symbol=symbol,
                    direction=direction,
                    pos_side=pos_side,
                    sz=this_reduce,
                    trade_uid=clOrdId,
                    reduceOnly=True,
                    tag='6618f740e7f1BCDE'
                )
                ordId = res.get('ordId') if res else None
                status = res.get('status') if res else None
                
                # 如果返回状态是closed，说明已经通过持仓检查更新了状态
                if status == 'closed':
                    logger.info(f"[客户减仓] 客户{customer_uid}减仓已完成（通过持仓检查）: trade_uid={trade_uid}")
                    # 更新该客户的剩余减仓量
                    customer_remaining_reduce -= this_reduce
                elif ordId:
                    update_customer_trade_order_id(self.db_pool, trade_uid, ordId)
                    logger.info(f"[客户减仓补全] 已写入order_id: trade_uid={trade_uid}, ordId={ordId}")
                    # 只更新当前trade的close_volume_contract
                    update_customer_trade_close_volume_contract(self.db_pool, trade_uid, this_reduce)
                    logger.info(f"[客户减仓] trade_uid={trade_uid}, volume_contract={volume_contract}, closed_contract={closed_contract}, this_reduce={this_reduce}, remaining={remain - this_reduce}, remaining_reduce={customer_remaining_reduce}")
                    # 判断是否已全平，及时更新status
                    new_closed_contract = closed_contract + this_reduce
                    if new_closed_contract >= volume_contract:
                        self.db_pool.execute(
                            "UPDATE customer_trades SET status='closed' WHERE trade_uid=%s",
                            (trade_uid,)
                        )
                        logger.info(f"[客户减仓] 持仓已全平: trade_uid={trade_uid}, status=closed")
                    # 更新该客户的剩余减仓量
                    customer_remaining_reduce -= this_reduce
                else:
                    logger.error(f"[客户减仓] 客户{customer_uid}减仓下单失败: {res}")
                    # 即使下单失败，也要更新剩余减仓量，避免无限循环
                    customer_remaining_reduce -= this_reduce
        else:
            logger.info(f"[客户减仓] 信号源全平，跳过减仓分配循环，直接执行全平补全逻辑")

        # 全平补全逻辑（只在真正信号源全平时执行，且只补差值，绝不对已closed的trade补全）
        if signal_source_closed and (signal_volume is None or signal_volume >= total_signal_contract):
            # 检查是否已经通过batch_close_trades_total_order处理过
            # 查询数据库中是否已经有相关的平仓订单
            trade_uids = [get_trade_field(t, 'trade_uid') for t in trades]
            if trade_uids:
                # 添加短暂延迟，确保数据库更新完成
                await asyncio.sleep(0.1)
                
                # 查询这些trade是否已经有close_order_id
                placeholders = ','.join(['%s'] * len(trade_uids))
                existing_closes = self.db_pool.query(
                    f"SELECT trade_uid, close_order_id FROM customer_trades WHERE trade_uid IN ({placeholders}) AND close_order_id IS NOT NULL",
                    trade_uids
                )
                
                if existing_closes:
                    logger.info(f"[客户减仓] 检测到已通过并发平仓处理过的订单: {[close['trade_uid'] for close in existing_closes]}，跳过全平补全逻辑")
                    # 记录所有trades的详细信息，便于调试
                    all_trades_info = []
                    for trade in trades:
                        trade_uid = get_trade_field(trade, 'trade_uid')
                        status = get_trade_field(trade, 'status')
                        close_order_id = get_trade_field(trade, 'close_order_id')
                        all_trades_info.append(f"{trade_uid}(status={status}, close_order_id={close_order_id})")
                    logger.info(f"[客户减仓] 所有trades信息: {all_trades_info}")
                else:
                    open_trades = [t for t in trades if get_trade_field(t, 'status') == 'open']
                    for trade in open_trades:
                        trade_uid = get_trade_field(trade, 'trade_uid')
                        volume_contract = float(get_trade_field(trade, 'volume_contract'))
                        closed_contract = float(get_trade_field(trade, 'close_volume_contract') or 0)
                        # 只对未处理的trade进行补全
                        if closed_contract == 0:
                            update_customer_trade_close_volume_contract(self.db_pool, trade_uid, volume_contract)
                            self.db_pool.execute(
                                "UPDATE customer_trades SET status='closed' WHERE trade_uid=%s",
                                (trade_uid,)
                            )
                            logger.info(f"[客户全平补全] trade_uid={trade_uid}, close_volume_contract={volume_contract}, status=closed, 补全量={volume_contract}")
            else:
                logger.warning(f"[客户减仓] trades列表为空，跳过全平补全逻辑")
        # 如果信号源全平但trades中没有包含所有相关trade，则查询并补全所有open的trade
        elif signal_source_closed and signal_source_uid:
            logger.info(f"[客户减仓] 信号源全平，查询所有相关客户持仓进行补全")
            all_open_trades = self.db_pool.query(
                "SELECT ct.* FROM customer_trades ct JOIN rules r ON ct.rule_uid = r.rule_uid WHERE r.rule_uid = %s AND ct.symbol = %s AND ct.pos_side = %s AND ct.status = 'open' AND ct.is_demo = %s",
                (signal_source_uid, symbol, pos_side, is_demo)
            )
            for trade in all_open_trades:
                trade_uid = get_trade_field(trade, 'trade_uid')
                volume_contract = float(get_trade_field(trade, 'volume_contract'))
                closed_contract = float(get_trade_field(trade, 'close_volume_contract') or 0)
                # 只对未处理的trade进行补全
                if closed_contract == 0:
                    update_customer_trade_close_volume_contract(self.db_pool, trade_uid, volume_contract)
                    self.db_pool.execute(
                        "UPDATE customer_trades SET status='closed' WHERE trade_uid=%s",
                        (trade_uid,)
                    )
                    logger.info(f"[客户全平补全] trade_uid={trade_uid}, close_volume_contract={volume_contract}, status=closed, 补全量={volume_contract}")

    async def auto_batch_close_trades(self, trades: List[CustomerTrade], symbol: str, pos_side: str, signal_volume: float):
        """
        自动根据规则表分仓比例，分批为每个规则trade平仓。
        trades: 需平仓的trade列表
        symbol: 币种
        pos_side: 方向
        signal_volume: 信号源本次平仓张数（如1ETH）
        """
        # 自动生成rule_ratio_map
        rule_ratio_map = {}
        # 先从内存热重载的规则查找
        for rule in self.rules:
            if float(rule.get('position_ratio', 0)) > 0:
                rule_ratio_map[rule['rule_uid']] = 1 / float(rule['position_ratio'])
        logger.info(f"[auto_batch_close_trades] 生成rule_ratio_map: {rule_ratio_map}")
        
        # 从trades中获取rule_uid，rule_uid就是signal_source_uid
        signal_source_uid = None
        if trades:
            # 取第一个trade的rule_uid，rule_uid就是signal_source_uid
            signal_source_uid = get_trade_field(trades[0], 'rule_uid')
            logger.info(f"[auto_batch_close_trades] 从trade获取signal_source_uid: {signal_source_uid}")
        else:
            logger.warning(f"[auto_batch_close_trades] trades为空，无法获取signal_source_uid")
        
        await self.batch_close_trades(trades, symbol, pos_side, signal_volume, rule_ratio_map, signal_source_uid)

    async def listen_customer_account(self, customer: Customer):
        client = await self.get_client(customer)
        
        async def on_account(data):
            try:
                customer_uid = get_customer_uid(customer)
                is_demo = get_global_is_demo()
                
                # 添加详细的调试日志
                logger.debug(f"[客户资产更新] 收到账户数据: customer_uid={customer_uid}, data={data}")
                
                if 'data' in data and isinstance(data['data'], list) and len(data['data']) > 0:
                    asset = safe_float(data['data'][0].get('totalEq', 0))
                    logger.info(f"[客户资产更新] 客户{customer_uid} 当前资产: {asset}")
                    
                    # 更新客户资产到数据库（优化：只在init_asset为NULL时更新，减少更新频率）
                    customer_data = get_customer_by_id(self.db_pool, customer_uid, is_demo)

                    if customer_data:
                        logger.debug(f"[客户资产更新] 客户{customer_uid} 数据库数据: {customer_data}")
                        # 只在init_asset为NULL时更新init_asset
                        if customer_data.get('init_asset') is None:
                            self.db_pool.execute(
                                "UPDATE customers SET init_asset=%s WHERE customer_uid=%s AND is_demo=%s",
                                (asset, customer_uid, is_demo)
                            )
                            logger.info(
                                f"[客户资产更新] 客户{customer_uid} init_asset为NULL，已更新为交易所资产: {asset}")

                        # 检查total_asset是否需要更新（只在变化超过1%时更新）
                        current_total_asset = customer_data.get('total_asset')
                        if current_total_asset is None:
                            # 如果total_asset为NULL，立即更新
                            self.db_pool.execute(
                                "UPDATE customers SET total_asset=%s WHERE customer_uid=%s AND is_demo=%s",
                                (asset, customer_uid, is_demo)
                            )
                            logger.info(f"[客户资产更新] 客户{customer_uid} total_asset为NULL，已更新为: {asset}")
                        else:
                            # 确保类型一致，转换为float进行比较
                            current_total_asset_float = float(current_total_asset)
                            change_ratio = abs(asset - current_total_asset_float) / current_total_asset_float
                            
                            logger.info(f"[客户资产更新] 客户{customer_uid} 资产变动检查: 当前={current_total_asset_float}, 新值={asset}, 变动比例={change_ratio:.4f} ({change_ratio*100:.2f}%)")
                            
                            if change_ratio > 0.01:
                                # 如果资产变化超过1%，才更新
                                self.db_pool.execute(
                                    "UPDATE customers SET total_asset=%s WHERE customer_uid=%s AND is_demo=%s",
                                    (asset, customer_uid, is_demo)
                                )
                                logger.info(
                                    f"[客户资产更新] 客户{customer_uid} total_asset变化超过1%，已更新为: {asset}")
                            else:
                                logger.debug(f"[客户资产更新] 客户{customer_uid} 资产变动未超过1%，跳过更新")

                    else:
                        logger.warning(f"[客户资产更新] 未找到客户{customer_uid}数据")
                else:
                    logger.warning(f"[警告] on_account: data 为空或格式异常: {data}")
            except Exception as e:
                logger.error(f"[客户资产更新异常] customer_uid={get_customer_uid(customer)}, error={e}")
                import traceback
                logger.error(f"[客户资产更新异常] 堆栈信息: {traceback.format_exc()}")

        async def on_order(data):
            try:
                if 'data' not in data or not data['data']:
                    return
                for order in data['data']:
                    ordId = order.get('ordId')
                    target_uid = order.get('clOrdId')
                    
                    # 统一通过order_id查找trade_uid，因为clOrdId和trade_uid格式不一致
                    reduceOnly = order.get('reduceOnly', 'false')
                    # 只在filled时写入volume和openPx
                    if order['state'] == 'filled':
                        avgPx = safe_float(order.get('fillPx')) or safe_float(order.get('avgPx'))
                        fillSz = safe_float(order.get('accFillSz', order.get('fillSz', order.get('sz'))))
                        notional_usd = order.get('fillNotionalUsd') or order.get('notionalUsd')
                        if reduceOnly == 'false':
                            # 只在开仓时写 volume、openPx
                            if avgPx:
                                update_customer_trade_open_px(self.db_pool, target_uid, avgPx)
                            if notional_usd:
                                volume = round(float(notional_usd), 3)
                            elif avgPx and fillSz:
                                # 计算名义价值：fillSz * multiplier * avgPx
                                multiplier = get_contract_multiplier(order.get('instId', ''))
                                volume = round(avgPx * fillSz * multiplier, 3)
                            else:
                                volume = 0
                            
                            # 更新volume和volume_contract
                            self.db_pool.execute("UPDATE customer_trades SET volume=%s, volume_contract=%s WHERE trade_uid=%s", (volume, fillSz, target_uid))
                            logger.info(f"[开仓成交] trade_uid={target_uid}, volume={volume}, volume_contract={fillSz}, openPx={avgPx}, notional_usd={notional_usd}")

                        elif reduceOnly == 'true':
                            # 分摊调试日志
                            order_ordId = order.get('ordId')
                            order_clOrdId = order.get('clOrdId')
                            fillSz = safe_float(order.get('accFillSz', order.get('fillSz', order.get('sz'))))
                            avgPx = safe_float(order.get('fillPx')) or safe_float(order.get('avgPx'))
                            logger.info(f"[分摊调试] on_order ordId={order_ordId}, clOrdId={order_clOrdId}, fillSz={fillSz}, avgPx={avgPx}")
                            
                            # 检查是否有pending的总单分摊
                            if hasattr(self, '_pending_total_close'):
                                pending = self._pending_total_close
                                pending_ordId = pending.get('ordId')
                                pending_clOrdId = pending.get('clOrdId')
                                logger.info(f"[分摊调试] 有pending总单分摊: pending_ordId={pending_ordId}, pending_clOrdId={pending_clOrdId}")
                            else:
                                logger.info(f"[分摊调试] 没有pending总单分摊")
                            
                            # 检查是否已经处理过这个平仓订单
                            processed_close_key = f"{order_ordId}_{order_clOrdId}_{fillSz}_{avgPx}"
                            if hasattr(self, '_processed_close_orders') and processed_close_key in self._processed_close_orders:
                                logger.info(f"[平仓去重] 平仓订单已处理过，跳过: {processed_close_key}")
                                return
                            
                            # 添加到已处理集合
                            if not hasattr(self, '_processed_close_orders'):
                                self._processed_close_orders = set()
                            self._processed_close_orders.add(processed_close_key)
                            
                            if hasattr(self, '_pending_total_close'):
                                pending = self._pending_total_close
                                pending_ordId = pending.get('ordId')
                                pending_clOrdId = pending.get('clOrdId')
                                logger.info(f"[分摊调试] pending_ordId={pending_ordId}, pending_clOrdId={pending_clOrdId}")
                                # 支持ordId和clOrdId两种方式匹配
                                if (pending_ordId == order_ordId) or (pending_clOrdId and pending_clOrdId == order_clOrdId):
                                    trades = pending['trades']
                                    total_sz = pending['total_sz']
                                    logger.info(f"[分摊调试] trades count={len(trades)}, trade_uids={[get_trade_field(t, 'trade_uid') for t in trades]}")
                                    for trade in trades:
                                        volume_contract = safe_float(get_trade_field(trade, 'volume_contract'))
                                        ratio = volume_contract / total_sz if total_sz > 0 else 0
                                        closePx = avgPx
                                        ordId = order_ordId
                                        openPx = safe_float(get_trade_field(trade, 'open_px'))
                                        direction_str = get_trade_field(trade, 'direction')
                                        volume_usdt = safe_float(get_trade_field(trade, 'volume'))
                                        if openPx == 0 or volume_usdt == 0:
                                            logger.error(f'[总单分摊] openPx或volume_usdt为0, trade_uid={get_trade_field(trade, "trade_uid")})')
                                            profit = 0
                                        else:
                                            if direction_str == 'buy':
                                                profit = (closePx - openPx) * (volume_usdt / openPx)
                                            elif direction_str == 'sell':
                                                profit = (openPx - closePx) * (volume_usdt / openPx)
                                            else:
                                                profit = (closePx - openPx) * (volume_usdt / openPx)
                                        
                                        # 检查是否已经更新过这个trade
                                        trade_uid = get_trade_field(trade, 'trade_uid')
                                        if hasattr(self, '_updated_trades') and trade_uid in self._updated_trades:
                                            logger.info(f"[总单分摊] trade_uid={trade_uid}已更新过，跳过")
                                            continue
                                        
                                        self.db_pool.execute(
                                            "UPDATE customer_trades SET close_px=%s, close_order_id=%s, profit=%s, status='closed', close_volume_contract=volume_contract WHERE trade_uid=%s",
                                            (closePx, ordId, round(profit, 3), get_trade_field(trade, 'trade_uid'))
                                        )
                                        
                                        # 记录已更新的trade
                                        if not hasattr(self, '_updated_trades'):
                                            self._updated_trades = set()
                                        self._updated_trades.add(trade_uid)
                                        
                                        logger.info(f"[总单分摊] 更新trade: trade_uid={get_trade_field(trade, 'trade_uid')}, closePx={closePx}, openPx={openPx}, fillSz={fillSz}, ratio={ratio:.4f}, profit={round(profit, 3)}, status=closed, close_volume_contract={volume_contract}")
                                        
                                        # 移除成功的平仓通知，只在异常情况下发送通知
                                    del self._pending_total_close
                                    return
                                else:
                                    # 如果没有匹配到总单分摊，检查是否是单个trade的平仓
                                    logger.info(f"[分摊调试] 未匹配到总单分摊，检查单个trade平仓")
                                    # 查询所有使用该order_id的trade
                                    related_trades = self.db_pool.query("SELECT * FROM customer_trades WHERE order_id=%s", (order_ordId,))
                                    logger.info(f"[分摊调试] 单个平仓查询结果: {len(related_trades) if related_trades else 0} 条记录")
                                    if related_trades:
                                        logger.info(f"[分摊调试] 找到{len(related_trades)}个相关trade")
                                    else:
                                        # 兜底逻辑：如果都没有匹配到，尝试直接发送通知
                                        logger.info(f"[分摊调试] 兜底逻辑：尝试直接发送平仓通知")
                                        try:
                                            # 通过order_id查找trade记录
                                            trade_rows = self.db_pool.query("SELECT * FROM customer_trades WHERE order_id=%s", (order_ordId,))
                                            if trade_rows:
                                                for trade_row in trade_rows:
                                                    trade_uid = trade_row['trade_uid']
                                                    volume_usdt = safe_float(trade_row['volume'])
                                                    openPx = safe_float(trade_row['open_px'])
                                                    
                                                    # 计算盈亏
                                                    if openPx > 0 and volume_usdt > 0:
                                                        direction_str = trade_row['direction']
                                                        if direction_str == 'buy':
                                                            profit = (avgPx - openPx) * (volume_usdt / openPx)
                                                        elif direction_str == 'sell':
                                                            profit = (openPx - avgPx) * (volume_usdt / openPx)
                                                        else:
                                                            profit = (avgPx - openPx) * (volume_usdt / openPx)
                                                    else:
                                                        profit = 0

                                            else:
                                                logger.warning(f"[分摊调试] 兜底逻辑也未找到相关trade记录: order_id={order_ordId}")
                                        except Exception as notify_error:
                                            logger.warning(f"[钉钉通知] 兜底平仓通知发送失败: {notify_error}")
                                        for trade_row in related_trades:
                                            trade_uid = trade_row['trade_uid']
                                            
                                            # 检查是否已经更新过这个trade
                                            if hasattr(self, '_updated_trades') and trade_uid in self._updated_trades:
                                                logger.info(f"[单个平仓] trade_uid={trade_uid}已更新过，跳过")
                                                continue
                                            
                                            openPx = safe_float(trade_row['open_px'])
                                            direction_str = trade_row['direction']
                                            volume_usdt = safe_float(trade_row['volume'])
                                            if openPx == 0 or volume_usdt == 0:
                                                logger.error(f'[单个平仓] openPx或volume_usdt为0, trade_uid={trade_uid}')
                                                profit = 0
                                            else:
                                                if direction_str == 'buy':
                                                    profit = (avgPx - openPx) * (volume_usdt / openPx)
                                                elif direction_str == 'sell':
                                                    profit = (openPx - avgPx) * (volume_usdt / openPx)
                                                else:
                                                    profit = (avgPx - openPx) * (volume_usdt / openPx)
                                            
                                            self.db_pool.execute(
                                                "UPDATE customer_trades SET close_px=%s, close_order_id=%s, profit=%s, status='closed', close_volume_contract=volume_contract WHERE trade_uid=%s",
                                                (avgPx, order_ordId, round(profit, 3), trade_uid)
                                            )
                                            
                                            # 记录已更新的trade
                                            if not hasattr(self, '_updated_trades'):
                                                self._updated_trades = set()
                                            self._updated_trades.add(trade_uid)
                                            
                                            logger.info(f"[单个平仓] 更新trade: trade_uid={trade_uid}, closePx={avgPx}, openPx={openPx}, profit={round(profit, 3)}, status=closed, close_volume_contract={volume_contract}")
                                            
                                            # 发送平仓通知
                                            # 移除成功的平仓通知，只在异常情况下发送通知
                                            logger.info(f"[钉钉通知] 平仓成功: trade_uid={trade_uid}, volume_usdt={volume_usdt}, profit={round(profit, 3)}")
                    else:
                        if reduceOnly == 'false':
                            if not target_uid:
                                logger.error(f"[开仓异常] 未找到trade_uid, ordId={ordId}")
                        elif reduceOnly == 'true':
                            if not target_uid:
                                logger.error(f"[平仓异常] 未找到trade_uid, ordId={ordId}")
                            else:
                                # 直接发送平仓成交通知（不查询数据库）
                                # 计算平仓的USDT金额
                                fillSz = safe_float(order.get('accFillSz', order.get('fillSz', order.get('sz'))))
                                avgPx = safe_float(order.get('fillPx')) or safe_float(order.get('avgPx'))
                                volume = fillSz * avgPx if fillSz > 0 and avgPx > 0 else 0
                                
                                logger.info(f"[钉钉通知] 发送平仓成交通知: ordId={ordId}, volume={volume}")
                                try:
                                    # 从clOrdId中提取客户信息
                                    clOrdId = order.get('clOrdId', '')
                                    if clOrdId and clOrdId.startswith('CREDUCEcust'):
                                        # 解析客户ID，例如：CREDUCEcust001XRPUSDTSWAPlor1109
                                        # 提取cust_001，格式是CREDUCEcust001...
                                        customer_uid = 'cust_' + clOrdId[13:16]  # 提取001并加上cust_前缀
                                        symbol = order.get('instId', '')
                                        direction = order.get('side', '')
                                        pos_side = order.get('posSide', '')
                                        
                                        # 移除成功的平仓通知，只在异常情况下发送通知
                                        logger.info(f"[钉钉通知] 平仓成功: customer_uid={customer_uid}, volume_usdt={volume}")
                                    else:
                                        logger.warning(f"[钉钉通知] 无法解析平仓客户信息: clOrdId={clOrdId}")
                                except Exception as notify_error:
                                    logger.warning(f"[钉钉通知] 平仓成交通知发送失败: {notify_error}")
            except Exception as e:
                logger.error(f"回调处理异常: {e}, data={data}")
        
        # 检查连接状态，避免重复连接
        # 使用客户端的类级别计数器
        while client._consecutive_auth_errors < client._max_auth_errors:
            try:
                # 检查是否已经连接
                if not hasattr(client, '_connected') or not client._connected:
                    await client.connect()
                
                # 订阅账户和订单
                await client.subscribe("account", on_account)
                break  # 连接成功，退出循环
            except Exception as e:
                error_msg = str(e)
                logger.error(f"[客户账户监听] 连接失败: customer_uid={get_customer_uid(customer)}, error={error_msg}")
                
                # 检查是否是API密钥错误
                if '60005' in error_msg or 'Invalid apiKey' in error_msg:
                    client._consecutive_auth_errors += 1
                    logger.error(f"[客户账户监听] API密钥错误 (第{client._consecutive_auth_errors}次): customer_uid={get_customer_uid(customer)}")
                    
                    if client._consecutive_auth_errors >= client._max_auth_errors:
                        logger.error(f"[客户账户监听] 连续{client._max_auth_errors}次API密钥错误，停止重连: customer_uid={get_customer_uid(customer)}")
                        
                        # 发送钉钉通知
                        try:
                            bot = get_dingtalk_bot()
                            if bot:
                                alert_info = {
                                    "title": "客户API密钥错误告警",
                                    "level": "ERROR", 
                                    "message": f"客户 {get_customer_uid(customer)} 连续{client._max_auth_errors}次API密钥错误",
                                    "account": f"客户UID: {get_customer_uid(customer)}",
                                    "strategy": "客户账户监听",
                                    "symbol": f"API密钥: {client.api_key[:8] if client.api_key else 'N/A'}...",
                                    "suggestion": "请检查该客户的API密钥配置是否正确，并重新设置有效的API密钥"
                                }
                                asyncio.create_task(bot.send_alert_notification_async("error", alert_info))
                            else:
                                logger.warning("钉钉机器人未初始化，跳过通知")
                        except Exception as e:
                            logger.error(f"发送钉钉通知失败: {e}")
                        
                        return  # 直接退出，不再重连
                    # 认证错误时继续循环，不break
                else:
                    # 非认证错误，等待后重试
                    logger.error(f"[客户账户监听] 非认证错误，等待重试: customer_uid={get_customer_uid(customer)}")
                    await asyncio.sleep(5)  # 等待5秒后重试

    async def listen_customer_accounts(self):
        is_demo = get_global_is_demo()
        logger.info(f"[日志] listen_customer_accounts: is_demo={is_demo}")
        customers = get_enabled_customers(self.db_pool, is_demo)
        logger.info(f"[日志] listen_customer_accounts: 查到客户: {[ (c['customer_uid'], c['is_demo']) for c in customers ]}")
        tasks = [self.listen_customer_account(self.safe_customer(c)) for c in customers]
        await asyncio.gather(*tasks)

    async def force_update_customer_assets(self, customer_uid=None, is_demo=None):
            """强制更新客户资产 - 用于调试"""
            try:
                
                if is_demo is None:
                    is_demo = get_global_is_demo()
                
                if customer_uid:
                    # 更新指定客户
                    customers = [get_customer_by_id(self.db_pool, customer_uid, is_demo)]
                    if not customers[0]:
                        logger.error(f"[强制资产更新] 客户{customer_uid}不存在")
                        return
                else:
                    # 更新所有客户
                    customers = get_enabled_customers(self.db_pool, is_demo)
                
                logger.info(f"[强制资产更新] 开始更新 {len(customers)} 个客户的资产")
                
                for customer_data in customers:
                    try:
                        customer_uid = customer_data['customer_uid']
                        logger.info(f"[强制资产更新] 正在更新客户 {customer_uid} 的资产")
                        
                        # 创建REST客户端
                        client = OKXRESTClient(
                            api_key=customer_data['api_key'],
                            api_secret=customer_data['api_secret'],
                            passphrase=customer_data['passphrase'],
                            is_demo=is_demo
                        )
                        
                        # 获取账户信息
                        account_info = await client.get_account_info()
                        if 'data' in account_info and account_info['data']:
                            asset = safe_float(account_info['data'][0].get('totalEq', 0))
                            logger.info(f"[强制资产更新] 客户{customer_uid} 当前资产: {asset}")
                            
                            # 直接更新数据库
                            self.db_pool.execute(
                                "UPDATE customers SET total_asset=%s WHERE customer_uid=%s AND is_demo=%s",
                                (asset, customer_uid, is_demo)
                            )
                            logger.info(f"[强制资产更新] 客户{customer_uid} 资产已更新为: {asset}")
                        else:
                            logger.warning(f"[强制资产更新] 客户{customer_uid} 获取账户信息失败")
                            
                    except Exception as e:
                        logger.error(f"[强制资产更新] 客户{customer_uid} 更新失败: {e}")
                        
            except Exception as e:
                logger.error(f"[强制资产更新] 批量更新失败: {e}")

    async def compensate_close_trades(self, interval_sec=30):
        """
        补偿/重试平仓逻辑加锁，防止同一笔单被多次平仓。
        """
        compensate_lock = Lock()
        while True:
            try:
                with compensate_lock:
                    is_demo = get_global_is_demo()
                    logger.info(f"[日志] compensate_close_trades: is_demo={is_demo}")
                    customers = self.db_pool.query("SELECT * FROM customers WHERE enabled=1 AND is_demo=%s", (is_demo,))
                    logger.info(f"[日志] compensate_close_trades: 查到客户: {[ (c['customer_uid'], c['is_demo']) for c in customers ]}")
                    for customer_row in customers:
                        customer = self.safe_customer(customer_row)
                        open_trades = self.db_pool.query("SELECT * FROM customer_trades WHERE customer_uid=%s AND status='open' AND is_demo=%s", (get_customer_uid(customer), is_demo))
                        if not open_trades:
                            continue
                        client = await self.get_client(customer)
                        # 1. 补偿order_id为空的trade
                        for trade in open_trades:
                            trade_uid = get_trade_field(trade, 'trade_uid')
                            order_id = get_trade_field(trade, 'order_id')
                            clOrdId = get_trade_field(trade, 'trade_uid')  # 假设clOrdId就是trade_uid
                            symbol = get_trade_field(trade, 'symbol')
                            if not order_id and clOrdId:
                                # 查询OKX订单列表，尝试通过clOrdId查ordId
                                try:
                                    res = await client.get_order(symbol, clOrdId)
                                    if res.get('code') == '0' and res.get('data'):
                                        ordId = res['data'][0].get('ordId')
                                        if ordId:
                                            update_customer_trade_order_id(self.db_pool, trade_uid, ordId)
                                            logger.info(f"[补偿order_id] 已补写order_id: trade_uid={trade_uid}, ordId={ordId}")
                                except Exception as e:
                                    logger.error(f"[补偿order_id异常] trade_uid={trade_uid}, symbol={symbol}, err={e}")
                        # 2. 正常补偿平仓逻辑（原有代码）
                        for trade in open_trades:
                            ordId = get_trade_field(trade, 'order_id')
                            trade_uid = get_trade_field(trade, 'trade_uid')
                            symbol = get_trade_field(trade, 'symbol')
                            pos_side = get_trade_field(trade, 'pos_side')
                            if not ordId:
                                continue
                            try:
                                res = await client.get_order(symbol, ordId)
                                if res.get('code') == '0' and res.get('data'):
                                    order_info = res['data'][0]
                                    state = order_info.get('state')
                                    reduceOnly = order_info.get('reduceOnly')
                                    avgPx = safe_float(order_info.get('avgPx')) or safe_float(order_info.get('fillPx'))
                                    fillSz = safe_float(order_info.get('fillSz', order_info.get('accFillSz', order_info.get('sz'))))
                                    sz = safe_float(order_info.get('sz'))
                                    cumSz = safe_float(order_info.get('accFillSz', order_info.get('fillSz', 0)))
                                    if (state == 'filled' or (state == 'partially_filled' and abs(sz-cumSz)<1e-8)) and reduceOnly == 'true':
                                        rows = self.db_pool.query("SELECT open_px, direction, volume FROM customer_trades WHERE trade_uid=%s", (trade_uid,))
                                        openPx = safe_float(rows[0]['open_px']) if rows and rows[0]['open_px'] is not None else 0
                                        direction_str = rows[0]['direction'] if rows and 'direction' in rows[0] else ''
                                        volume_usdt = safe_float(rows[0]['volume']) if rows and 'volume' in rows[0] else 0
                                        closePx = avgPx
                                        if openPx == 0 and avgPx > 0:
                                            update_customer_trade_open_px(self.db_pool, trade_uid, avgPx)
                                            openPx = avgPx
                                            logger.warning(f'[补偿自动补全] 平仓时openPx为0，已用closePx补写: trade_uid={trade_uid}, openPx={openPx}')
                                        if openPx == 0 or volume_usdt == 0:
                                            logger.error(f'[补偿异常] openPx或volume_usdt为0，跳过profit计算: openPx={openPx}, volume_usdt={volume_usdt}, trade_uid={trade_uid}')
                                            profit = 0
                                        else:
                                            if direction_str == 'buy':
                                                profit = (avgPx - openPx) * (volume_usdt / openPx)
                                            elif direction_str == 'sell':
                                                profit = (openPx - avgPx) * (volume_usdt / openPx)
                                            else:
                                                profit = (avgPx - openPx) * (volume_usdt / openPx)
                                        close_customer_trade(self.db_pool, trade_uid, profit, closePx)
                                        logger.info(f"[补偿平仓] closePx={closePx}, profit={profit}, volume(USDT)={volume_usdt}, openPx={openPx}, trade_uid={trade_uid}")
                                    elif state == 'canceled' and reduceOnly == 'true':
                                        try:
                                            pos = await client.get_position(symbol)
                                            found = False
                                            for p in pos.get('data', []):
                                                if p.get('posSide', '').lower() == str(pos_side).lower() and safe_float(p.get('availPos', 0)) > 0:
                                                    found = True
                                                    break
                                            if not found:
                                                close_customer_trade(self.db_pool, trade_uid, 0, None)
                                                logger.info(f"[补偿撤销平仓] trade_uid={trade_uid}, symbol={symbol}, pos_side={pos_side}")
                                        except Exception as e:
                                            logger.error(f"[补偿异常] 查询持仓异常: trade_uid={trade_uid}, symbol={symbol}, pos_side={pos_side}, err={e}")
                            except Exception as e:
                                logger.error(f"[补偿异常] 查询OKX订单状态异常: trade_uid={trade_uid}, ordId={ordId}, err={e}")
            except Exception as e:
                logger.error(f"[补偿异常] compensate_close_trades主循环异常: {e}")
            await asyncio.sleep(interval_sec)

    def find_trade_by_volume_contract(self, trades, volume_contract):
        v = safe_volume(volume_contract, 3)
        for t in trades:
            if safe_volume(get_trade_field(t, 'volume_contract'), 3) == v:
                return t
        return None

    async def aggregate_and_place_orders(self, customer, symbol, direction, pos_side, signal_order_requests):
        """
        自动聚合同一币种/方向/时刻的所有信号源规则下单请求，调用集合下单。
        signal_order_requests: List[dict]，每个dict包含signal_source_uid, rule_uid, strategy_uid, sz(应下单张数)
        """
        customer_uid = get_customer_uid(customer)
        customer_lock = get_customer_processing_lock(customer_uid)
        customer_cross_signal_lock = get_customer_cross_signal_lock(customer_uid)
        
        # 使用跨信号源的客户锁防止同一客户被多个信号源同时操作
        with customer_cross_signal_lock:
            # 使用客户级别的锁防止同一客户并发下单
            with customer_lock:
                logger.info(f"aggregate_and_place_orders: customer_uid={customer_uid}, signal_order_requests={signal_order_requests}")
                # 直接进入业务逻辑，无需加锁
                await self.batch_aggregate_place_orders(customer, symbol, direction, pos_side, signal_order_requests)

    async def aggregate_and_close_orders(self, customer, symbol, direction, pos_side, all_trades: list):
        """
        自动聚合同一币种/方向/时刻的所有需平仓子单，调用集合平单。
        all_trades: List[CustomerTrade]，每个为需平仓的子单
        """
        # 可在此处做分组、风控等
        await self.batch_aggregate_close_orders(customer, symbol, direction, pos_side, all_trades) 

    def check_customer_risk_control(self, customer_uid, symbol, direction, pos_side):
        """
        检查客户风控，允许双向开仓，只阻止客户重复开仓
        """
        try:
            logger.info(f"[风控检查] 开始检查客户{customer_uid}: symbol={symbol}, direction={direction}, pos_side={pos_side}")
            
            # 查询客户当前持仓
            open_trades = self.get_open_trades_by_symbol(symbol, pos_side)
            customer_trades = [t for t in open_trades if get_customer_uid(t) == customer_uid]
            
            logger.info(f"[风控检查] 客户{customer_uid}当前持仓数量: {len(customer_trades)}")
            for i, trade in enumerate(customer_trades):
                logger.info(f"[风控检查] 持仓{i+1}: trade_uid={get_trade_field(trade, 'trade_uid')}, volume={get_trade_field(trade, 'volume')}, pos_side={get_trade_field(trade, 'pos_side')}")
            
            if not customer_trades:
                logger.info(f"[风控检查] 客户{customer_uid}没有持仓，允许开仓")
                return True  # 没有持仓，可以开仓
            
            # 修正：检查客户是否已经执行过相同方向的订单
            # 当前要开仓的方向：direction + pos_side
            current_trade_direction = f"{direction}_{pos_side}"
            
            # 查询客户所有持仓，检查是否有相同方向的已执行订单
            all_customer_trades = self.get_open_trades(customer_uid)
            same_direction_executed_trades = []
            
            for trade in all_customer_trades:
                if get_trade_field(trade, 'symbol') == symbol:
                    trade_direction = get_trade_field(trade, 'direction')
                    trade_pos_side = get_trade_field(trade, 'pos_side')
                    trade_direction_key = f"{trade_direction}_{trade_pos_side}"
                    
                    # 判断是否为相同方向且已执行的订单
                    is_same_direction_executed = False
                    
                    # 检查是否为相同方向的已执行订单
                    if current_trade_direction == "buy_long" and trade_direction_key == "buy_long":
                        # 检查是否已有order_id（已执行）
                        if get_trade_field(trade, 'order_id'):
                            is_same_direction_executed = True  # 重复做多且已执行
                    elif current_trade_direction == "sell_short" and trade_direction_key == "sell_short":
                        # 检查是否已有order_id（已执行）
                        if get_trade_field(trade, 'order_id'):
                            is_same_direction_executed = True  # 重复做空且已执行
                    elif current_trade_direction == "sell_long" and trade_direction_key == "sell_long":
                        # 检查是否已有order_id（已执行）
                        if get_trade_field(trade, 'order_id'):
                            is_same_direction_executed = True  # 重复平多且已执行
                    elif current_trade_direction == "buy_short" and trade_direction_key == "buy_short":
                        # 检查是否已有order_id（已执行）
                        if get_trade_field(trade, 'order_id'):
                            is_same_direction_executed = True  # 重复平空且已执行
                    
                    if is_same_direction_executed:
                        same_direction_executed_trades.append(trade)
            
            logger.info(f"[风控检查] 客户{customer_uid}相同方向已执行订单数量: {len(same_direction_executed_trades)}")
            for i, trade in enumerate(same_direction_executed_trades):
                logger.info(f"[风控检查] 相同方向已执行订单{i+1}: trade_uid={get_trade_field(trade, 'trade_uid')}, direction={get_trade_field(trade, 'direction')}, pos_side={get_trade_field(trade, 'pos_side')}, order_id={get_trade_field(trade, 'order_id')}")
            
            if same_direction_executed_trades:
                # 检查最近一笔相同方向订单的时间，如果超过30秒就不是重复订单
                import time
                current_time = int(time.time())
                latest_trade_time = 0
                
                for trade in same_direction_executed_trades:
                    # 获取订单创建时间，优先使用cTime
                    trade_time = get_trade_field(trade, 'cTime')
                    if trade_time:
                        try:
                            trade_timestamp = int(trade_time) / 1000  # 转换为秒
                            if trade_timestamp > latest_trade_time:
                                latest_trade_time = trade_timestamp
                        except (ValueError, TypeError):
                            pass
                
                # 计算时间间隔（秒）
                time_interval = current_time - latest_trade_time
                min_interval_seconds = 10  # 10秒内认为是重复订单
                
                logger.info(f"[风控检查] 客户{customer_uid}最近一笔相同方向订单时间: {latest_trade_time}, 当前时间: {current_time}, 时间间隔: {time_interval}秒, 最小间隔: {min_interval_seconds}秒")
                
                if time_interval < min_interval_seconds:
                    remaining_time = min_interval_seconds - time_interval
                    logger.warning(f"[风控检查] 客户{customer_uid}相同方向开仓时间间隔过短，还需等待{remaining_time}秒，认为是重复订单: 当前={current_trade_direction}")
                    return False
                else:
                    logger.info(f"[风控检查] 客户{customer_uid}相同方向开仓时间间隔足够({time_interval}秒)，不认为是重复订单，允许开仓: 当前={current_trade_direction}")
                    # 时间间隔足够，不认为是重复订单，继续检查其他风控条件
            
            # 检查杠杆是否超限
            total_nominal = sum([safe_float(t.volume) for t in customer_trades])
            customer_data = get_customer_by_id(self.db_pool, customer_uid, is_demo=get_global_is_demo())
            if customer_data:
                logger.info(f"[风控检查] 客户{customer_uid}总名义价值: {total_nominal}")
                # 这里可以添加更复杂的风控逻辑
                # 比如检查总杠杆、单币种杠杆等
                pass
            
            logger.info(f"[风控检查] 客户{customer_uid}风控检查通过，允许下单")
            return True
        except Exception as e:
            logger.error(f"[风控检查异常] customer_uid={customer_uid}, symbol={symbol}, error={e}")
            return False  # 异常情况下保守处理，不允许下单

    async def _execute_customer_close(self, customer, symbol, direction, pos_side, total_sz, customer_clOrdId, customer_trade_list):
        """执行单个客户的平仓逻辑"""
        try:
            res = await self.async_place_order(
                customer=customer,
                symbol=symbol,
                direction=direction,
                pos_side=pos_side,
                sz=total_sz,
                trade_uid=customer_clOrdId,
                reduceOnly=True,
                tag='6618f740e7f1BCDE'
            )
            
            ordId = res.get('ordId')
            status = res.get('status')
            customer_uid = get_customer_uid(customer)
            
            # 如果返回状态是closed，说明已经通过持仓检查更新了状态
            if status == 'closed':
                logger.info(f"[客户平仓] 客户{customer_uid}平仓已完成（通过持仓检查）")
                # 更新所有相关trade的状态为closed
                for trade in customer_trade_list:
                    trade_uid = get_trade_field(trade, 'trade_uid')
                    volume_contract = float(get_trade_field(trade, 'volume_contract') or 0)
                    current_closed = float(get_trade_field(trade, 'close_volume_contract') or 0)
                    
                    # 如果close_volume_contract为0，设置为volume_contract（全平）
                    if current_closed == 0:
                        update_customer_trade_close_volume_contract(self.db_pool, trade_uid, volume_contract)
                        logger.info(f"[客户平仓] 更新close_volume_contract: trade_uid={trade_uid}, volume_contract={volume_contract}")
                    
                    # 更新状态为closed
                    self.db_pool.execute(
                        "UPDATE customer_trades SET status='closed' WHERE trade_uid=%s",
                        (trade_uid,)
                    )
                    logger.info(f"[客户平仓] 更新状态为closed: trade_uid={trade_uid}")
                
                logger.info(f"[客户平仓] 客户{customer_uid}平仓已完成（通过持仓检查）")
                return {'success': True, 'message': '平仓已完成（通过持仓检查）'}
            elif ordId:
                # 写入order_id到该客户的所有trade
                for trade in customer_trade_list:
                    update_customer_trade_order_id(self.db_pool, get_trade_field(trade, 'trade_uid'), ordId)
                    logger.info(f"[客户平仓补全] 已写入order_id: trade_uid={get_trade_field(trade, 'trade_uid')}, ordId={ordId}")
                
                # 记录该客户的平仓信息（只记录最后一个客户的，因为on_order回调会处理）
                self._pending_total_close = {
                    'symbol': symbol,
                    'pos_side': pos_side,
                    'ordId': ordId,
                    'clOrdId': customer_clOrdId,
                    'trades': customer_trade_list,
                    'total_sz': total_sz,
                    'customer_uid': customer_uid  # 新增：记录是哪个客户的平仓
                }
                
                logger.info(f"[客户平仓] 客户{customer_uid}平仓成功: ordId={ordId}, clOrdId={customer_clOrdId}")
                
                # 立即更新客户订单状态为closed
                try:
                    for trade in customer_trade_list:
                        trade_uid = get_trade_field(trade, 'trade_uid')
                        if trade_uid:
                            # 更新状态为closed
                            self.db_pool.execute(
                                "UPDATE customer_trades SET status='closed', execution_type='compensation', execution_reason='平仓信号丢失补偿' WHERE trade_uid=%s",
                                (trade_uid,)
                            )
                            logger.info(f"[客户平仓] 客户{customer_uid}订单状态已更新为closed: {trade_uid}")
                except Exception as e:
                    logger.error(f"[客户平仓] 更新客户{customer_uid}订单状态失败: {e}")
                
                return {'success': True, 'message': f'平仓成功', 'ordId': ordId}
            else:
                logger.error(f"[客户平仓] 客户{customer_uid}平仓失败: {res}")
                return {'success': False, 'error': f'平仓失败: {res}'}
        except Exception as e:
            logger.error(f"[客户平仓] 客户{get_customer_uid(customer)}平仓异常: {e}")
            return {'success': False, 'error': str(e)}

    async def check_position_anomalies(self):
        """检查仓位异常并自动修复"""
        global _position_check_running
        
        # 使用锁确保只有一个进程在运行仓位检查
        if not _position_check_lock.acquire(blocking=False):
            logger.debug("[仓位检查] 另一个进程正在运行仓位检查，跳过")
            return
        
        try:
            if _position_check_running:
                logger.debug("[仓位检查] 仓位检查已在运行中，跳过")
                return
            
            _position_check_running = True
            logger.info("[仓位检查] 开始检查仓位异常")
            
            is_demo = get_global_is_demo()
            
            # 获取所有启用的客户
            customers = get_enabled_customers(self.db_pool, is_demo)
            
            for customer_data in customers:
                customer_uid = customer_data['customer_uid']
                
                try:
                    # 获取客户所有持仓
                    trades = self.get_open_trades(customer_uid)
                    
                    for trade in trades:
                        symbol = trade.symbol
                        pos_side = trade.pos_side
                        
                        # 从交易所获取实际持仓
                        # 获取完整的客户信息
                        customer_data = get_customer_by_id(self.db_pool, customer_uid, is_demo)
                        if customer_data:
                            customer = self.safe_customer(customer_data)
                            # 检查是否已有连接，如果没有则跳过（避免在异常检测时创建新连接）
                            customer_uid_key = get_customer_uid(customer)
                            if customer_uid_key in self.clients:
                                client = self.clients[customer_uid_key]
                            else:
                                logger.debug(f"[仓位检查] 客户{customer_uid}没有活跃连接，跳过检查")
                                continue
                        else:
                            logger.error(f"[仓位检查] 未找到客户{customer_uid}信息")
                            continue
                        
                        try:
                            positions = await client.get_positions()
                            
                            # 检查API响应是否正常
                            if positions.get('code') == '50106':
                                logger.warning(f"[仓位检查] 客户{customer_uid} API密钥错误，跳过检查")
                                continue
                            elif positions.get('code') != '0':
                                logger.warning(f"[仓位检查] 客户{customer_uid} 获取持仓失败: {positions}")
                                continue
                            
                            if 'data' in positions and positions['data']:
                                actual_sz = 0
                                for pos in positions['data']:
                                    if pos.get('instId') == symbol and pos.get('posSide') == pos_side:
                                        actual_sz = float(pos.get('pos', 0))
                                        break
                                
                                # 计算期望持仓
                                expected_sz = float(trade.volume_contract or 0)
                                difference_sz = actual_sz - expected_sz
                                
                                # 获取合约最小张数作为误差阈值
                                min_sz = get_contract_min_sz(symbol)
                                
                                # 检查是否有异常 - 提高阈值，减少误报
                                if abs(difference_sz) > min_sz * 3:  # 提高到3倍最小张数
                                    anomaly_type = 'overflow' if difference_sz > 0 else 'underflow'
                                    
                                    # 检查是否已经有未解决的相同异常
                                    existing_anomaly = self.db_pool.query(
                                        "SELECT * FROM position_anomalies WHERE customer_uid=%s AND symbol=%s AND pos_side=%s AND status='pending'",
                                        (customer_uid, symbol, pos_side)
                                    )
                                    
                                    if not existing_anomaly:
                                        # 检查最近是否已经修复过相同异常（防止频繁修复）
                                        recent_fixed = self.db_pool.query(
                                            "SELECT * FROM position_anomalies WHERE customer_uid=%s AND symbol=%s AND pos_side=%s AND status='resolved' AND resolved_at > DATE_SUB(NOW(), INTERVAL 1 HOUR)",
                                            (customer_uid, symbol, pos_side)
                                        )
                                        
                                        if not recent_fixed:
                                            # 记录异常
                                            self.db_pool.execute(
                                                "INSERT INTO position_anomalies (customer_uid, symbol, pos_side, expected_sz, actual_sz, difference_sz, anomaly_type, is_demo) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
                                                (customer_uid, symbol, pos_side, expected_sz, actual_sz, abs(difference_sz), anomaly_type, is_demo)
                                            )
                                            
                                            logger.warning(f"[仓位异常] 客户{customer_uid} {symbol} {pos_side} 期望{expected_sz}张, 实际{actual_sz}张, 差异{abs(difference_sz)}张")
                                            
                                            # 自动修复（提高阈值，减少误报）
                                            if abs(difference_sz) > min_sz * 5:  # 差异超过5倍最小张数才自动修复
                                                await self.auto_fix_position_anomaly(customer_uid, symbol, pos_side, difference_sz, is_demo)
                                        else:
                                            logger.debug(f"[仓位异常] 客户{customer_uid} {symbol} {pos_side} 最近1小时内已修复过，跳过")
                                    else:
                                        # 减少重复检测的日志输出，只在DEBUG模式下显示
                                        logger.debug(f"[仓位异常] 客户{customer_uid} {symbol} {pos_side} 异常已存在，跳过重复检测")
                                        
                        except Exception as e:
                            error_msg = str(e)
                            if "50106" in error_msg or "API密钥" in error_msg:
                                logger.warning(f"[仓位检查] 客户{customer_uid} API密钥问题，跳过检查: {error_msg}")
                            else:
                                logger.error(f"[仓位检查] 获取客户{customer_uid}持仓失败: {error_msg}")
                            
                except Exception as e:
                    logger.error(f"[仓位检查] 检查客户{customer_uid}异常: {e}")
                    
        except Exception as e:
            logger.error(f"[仓位检查] 整体异常: {e}")
        finally:
            # 释放仓位检查锁
            _position_check_running = False
            _position_check_lock.release()
            logger.info("[仓位检查] 仓位检查完成")

    async def auto_fix_position_anomaly(self, customer_uid, symbol, pos_side, difference_sz, is_demo):
        """自动修复仓位异常"""
        temp_client = None
        
        # 尝试获取自动修复锁
        if not self.acquire_auto_fix_lock(customer_uid, symbol, pos_side, timeout=300):  # 5分钟锁
            logger.warning(f"[自动修复] 客户{customer_uid} {symbol} {pos_side} 正在被其他进程修复，跳过")
            return
        
        try:
            # 清理过期的锁
            self.cleanup_expired_locks()
            
            # 再次检查是否已经有未解决的异常（双重保险）
            existing_anomaly = self.db_pool.query(
                "SELECT * FROM position_anomalies WHERE customer_uid=%s AND symbol=%s AND pos_side=%s AND status='pending'",
                (customer_uid, symbol, pos_side)
            )
            
            if not existing_anomaly:
                logger.warning(f"[自动修复] 客户{customer_uid} {symbol} {pos_side} 异常记录不存在，跳过修复")
                return
            
            # 检查最近是否已经修复过（防止频繁修复）
            recent_fixed = self.db_pool.query(
                "SELECT * FROM position_anomalies WHERE customer_uid=%s AND symbol=%s AND pos_side=%s AND status='resolved' AND resolved_at > DATE_SUB(NOW(), INTERVAL 30 MINUTE)",
                (customer_uid, symbol, pos_side)
            )
            
            if recent_fixed:
                logger.warning(f"[自动修复] 客户{customer_uid} {symbol} {pos_side} 最近30分钟内已修复过，跳过")
                return
            
            # 获取完整的客户信息
            customer_data = get_customer_by_id(self.db_pool, customer_uid, is_demo)
            if not customer_data:
                logger.error(f"[自动修复] 未找到客户{customer_uid}信息")
                return
            customer = self.safe_customer(customer_data)
            
            # 检查是否已有连接，如果没有则创建临时连接
            customer_uid_key = get_customer_uid(customer)
            if customer_uid_key in self.clients:
                # 使用现有连接
                client = self.clients[customer_uid_key]
                logger.debug(f"[自动修复] 使用现有连接: {customer_uid}")
            else:
                # 创建临时连接
                logger.info(f"[自动修复] 创建临时连接: {customer_uid}")
                temp_client = OKXWebSocketClient(
                    is_demo=customer.is_demo if hasattr(customer, 'is_demo') else False,
                    api_key=customer.api_key,
                    api_secret=customer.api_secret,
                    passphrase=customer.passphrase
                )
                await temp_client.connect()
                client = temp_client
            
            # 再次获取实际持仓，确保数据是最新的
            try:
                positions = await client.get_positions()
                if 'data' in positions and positions['data']:
                    actual_sz = 0
                    for pos in positions['data']:
                        if pos.get('instId') == symbol and pos.get('posSide') == pos_side:
                            actual_sz = float(pos.get('pos', 0))
                            break
                    
                    # 重新计算差异
                    trades = self.get_open_trades(customer_uid)
                    expected_sz = 0
                    for trade in trades:
                        if trade.symbol == symbol and trade.pos_side == pos_side:
                            expected_sz = float(trade.volume_contract or 0)
                            break
                    
                    current_difference = actual_sz - expected_sz
                    
                    # 如果差异已经很小，说明可能已经被其他操作修复了
                    min_sz = get_contract_min_sz(symbol)
                    if abs(current_difference) <= min_sz * 2:
                        logger.info(f"[自动修复] 客户{customer_uid} {symbol} {pos_side} 差异已减小到{current_difference}张，跳过修复")
                        # 更新异常记录状态
                        self.db_pool.execute(
                            "UPDATE position_anomalies SET status='resolved', resolution_method='auto_skip', resolved_at=NOW() WHERE customer_uid=%s AND symbol=%s AND pos_side=%s AND status='pending'",
                            (customer_uid, symbol, pos_side)
                        )
                        return
                    
                    # 使用最新的差异值进行修复
                    difference_sz = current_difference
                    
            except Exception as e:
                logger.error(f"[自动修复] 重新获取持仓失败: {e}")
                return
            
            logger.info(f"[自动修复] 开始修复客户{customer_uid} {symbol} {pos_side} 差异{difference_sz}张")
            
            if difference_sz > 0:  # 实际持仓过多，需要平仓
                close_side = 'sell' if pos_side == 'long' else 'buy'
                
                # 生成订单ID
                import time
                import uuid
                timestamp = int(time.time() * 1000000)
                random_suffix = uuid.uuid4().hex[:8]
                clOrdId = f'FIX{customer_uid}{symbol}{timestamp}{random_suffix}'[:32]
                
                # 执行平仓
                result = await self.async_place_order(
                    customer=customer,
                    symbol=symbol,
                    direction=close_side,
                    pos_side=pos_side,
                    sz=abs(difference_sz),
                    trade_uid=clOrdId,
                    reduceOnly=True
                )
                
                if result and result.get('ordId'):
                    logger.info(f"[自动修复] 客户{customer_uid} {symbol} {pos_side} 平仓{abs(difference_sz)}张成功")
                    
                    # 生成唯一的trade_uid
                    import time
                    import uuid
                    timestamp = int(time.time() * 1000000)
                    random_suffix = uuid.uuid4().hex[:8]
                    trade_uid = f'AUTOFIX{customer_uid}{symbol}{timestamp}{random_suffix}'[:128]
                    
                    # 计算名义价值
                    multiplier = get_contract_multiplier(symbol)
                    latest_px = get_price_on_demand(symbol) or 1
                    volume_usdt = abs(difference_sz) * multiplier * latest_px
                    
                    # 插入customer_trades记录
                    insert_customer_trade(
                        self.db_pool,
                        customer_uid,
                        'auto_fix',  # strategy_uid
                        'auto_fix',  # rule_uid
                        symbol,
                        volume_usdt,
                        close_side,
                        pos_side,
                        trade_uid=trade_uid,
                        is_demo=is_demo,
                        volume_contract=abs(difference_sz),
                        open_px=latest_px,
                        execution_type='auto_fix',
                        execution_reason=f'自动修复仓位异常，差异{difference_sz}张'
                    )
                    
                    # 更新异常记录状态
                    self.db_pool.execute(
                        "UPDATE position_anomalies SET status='resolved', resolution_method='auto_close', resolved_at=NOW() WHERE customer_uid=%s AND symbol=%s AND pos_side=%s AND status='pending'",
                        (customer_uid, symbol, pos_side)
                    )
                    
            else:  # 实际持仓不足，需要开仓
                open_side = 'buy' if pos_side == 'long' else 'sell'
                
                # 生成订单ID
                import time
                import uuid
                timestamp = int(time.time() * 1000000)
                random_suffix = uuid.uuid4().hex[:8]
                clOrdId = f'FIX{customer_uid}{symbol}{timestamp}{random_suffix}'[:32]
                
                # 执行开仓
                result = await self.async_place_order(
                    customer=customer,
                    symbol=symbol,
                    direction=open_side,
                    pos_side=pos_side,
                    sz=abs(difference_sz),
                    trade_uid=clOrdId
                )
                
                if result and result.get('ordId'):
                    logger.info(f"[自动修复] 客户{customer_uid} {symbol} {pos_side} 开仓{abs(difference_sz)}张成功")
                    
                    # 生成唯一的trade_uid
                    import time
                    import uuid
                    timestamp = int(time.time() * 1000000)
                    random_suffix = uuid.uuid4().hex[:8]
                    trade_uid = f'AUTOFIX{customer_uid}{symbol}{timestamp}{random_suffix}'[:128]
                    
                    # 计算名义价值
                    multiplier = get_contract_multiplier(symbol)
                    latest_px = await get_price_on_demand(symbol) or 1
                    volume_usdt = abs(difference_sz) * multiplier * latest_px
                    
                    # 插入customer_trades记录
                    insert_customer_trade(
                        self.db_pool,
                        customer_uid,
                        'auto_fix',  # strategy_uid
                        'auto_fix',  # rule_uid
                        symbol,
                        volume_usdt,
                        open_side,
                        pos_side,
                        trade_uid=trade_uid,
                        is_demo=is_demo,
                        volume_contract=abs(difference_sz),
                        open_px=latest_px,
                        execution_type='auto_fix',
                        execution_reason=f'自动修复仓位异常，差异{difference_sz}张'
                    )
                    
                    # 更新异常记录状态
                    self.db_pool.execute(
                        "UPDATE position_anomalies SET status='resolved', resolution_method='auto_open', resolved_at=NOW() WHERE customer_uid=%s AND symbol=%s AND pos_side=%s AND status='pending'",
                        (customer_uid, symbol, pos_side)
                    )
                    
        except Exception as e:
            logger.error(f"[自动修复] 客户{customer_uid} {symbol} {pos_side} 修复失败: {e}")
        finally:
            # 释放自动修复锁
            self.release_auto_fix_lock(customer_uid, symbol, pos_side)
            
            # 清理临时连接
            if temp_client:
                try:
                    await temp_client.close()
                    logger.info(f"[自动修复] 已清理临时连接: {customer_uid}")
                except Exception as e:
                    logger.error(f"[自动修复] 清理临时连接失败: {customer_uid}, error={e}")

    async def get_position_anomalies(self, customer_uid=None, status='pending'):
        """获取仓位异常记录"""
        try:
            if customer_uid:
                sql = "SELECT * FROM position_anomalies WHERE customer_uid=%s AND status=%s ORDER BY created_at DESC"
                anomalies = self.db_pool.query(sql, (customer_uid, status))
            else:
                sql = "SELECT * FROM position_anomalies WHERE status=%s ORDER BY created_at DESC"
                anomalies = self.db_pool.query(sql, (status,))
            
            return anomalies
        except Exception as e:
            logger.error(f"[获取异常] 获取仓位异常记录失败: {e}")
            return []

    def get_auto_fix_lock_key(self, customer_uid, symbol, pos_side):
        """生成自动修复锁的键"""
        return f"{customer_uid}_{symbol}_{pos_side}"

    def acquire_auto_fix_lock(self, customer_uid, symbol, pos_side, timeout=60):
        """获取自动修复锁，防止重复修复"""
        lock_key = self.get_auto_fix_lock_key(customer_uid, symbol, pos_side)
        
        with _auto_fix_locks_lock:
            if lock_key in _auto_fix_locks:
                lock_info = _auto_fix_locks[lock_key]
                # 检查锁是否过期
                if time.time() - lock_info['timestamp'] > timeout:
                    # 锁过期，删除旧锁
                    del _auto_fix_locks[lock_key]
                else:
                    # 锁仍然有效，返回False表示无法获取锁
                    return False
            
            # 创建新锁
            _auto_fix_locks[lock_key] = {
                'timestamp': time.time(),
                'customer_uid': customer_uid,
                'symbol': symbol,
                'pos_side': pos_side
            }
            return True

    def release_auto_fix_lock(self, customer_uid, symbol, pos_side):
        """释放自动修复锁"""
        lock_key = self.get_auto_fix_lock_key(customer_uid, symbol, pos_side)
        
        with _auto_fix_locks_lock:
            if lock_key in _auto_fix_locks:
                del _auto_fix_locks[lock_key]

    def cleanup_expired_locks(self):
        """清理过期的锁"""
        try:
            current_time = time.time()
            cleaned_count = 0
            
            # 清理客户处理锁
            for key in list(customer_processing_locks.keys()):
                if hasattr(customer_processing_locks[key], 'timestamp'):
                    lock_info = customer_processing_locks[key]
                    if current_time - lock_info['timestamp'] > 3600:  # 1小时过期
                        del customer_processing_locks[key]
                        cleaned_count += 1
            
            # 清理自动修复锁
            for key in list(_auto_fix_locks.keys()):
                if hasattr(_auto_fix_locks[key], 'timestamp'):
                    lock_info = _auto_fix_locks[key]
                    if current_time - lock_info['timestamp'] > 1800:  # 30分钟过期
                        del _auto_fix_locks[key]
                        cleaned_count += 1
            
            if cleaned_count > 0:
                logger.info(f"过期锁清理完成，清理了 {cleaned_count} 个锁")
            
        except Exception as e:
            logger.error(f"清理过期锁失败: {e}")

    async def _cleanup_stale_tasks(self):
        """清理过期的异步任务"""
        try:
            # 获取所有正在运行的任务
            tasks = [task for task in asyncio.all_tasks() if not task.done()]
            
            # 检查任务是否卡住
            current_time = time.time()
            stale_tasks = []
            
            for task in tasks:
                # 如果任务运行时间超过10分钟，标记为过期
                if hasattr(task, '_start_time'):
                    if current_time - task._start_time > 600:
                        stale_tasks.append(task)
            
            if stale_tasks:
                logger.warning(f"发现 {len(stale_tasks)} 个过期任务，准备取消")
                
                for task in stale_tasks:
                    try:
                        task.cancel()
                        logger.info(f"已取消过期任务: {task.get_name()}")
                    except Exception as e:
                        logger.error(f"取消任务失败: {e}")
            
        except Exception as e:
            logger.error(f"清理过期任务失败: {e}")

    # ==================== 主监控系统启动和停止 ====================
    
    async def start_all_monitoring_systems(self):
        """启动所有监控系统"""
        try:
            logger.info("正在启动所有监控系统...")
            
            # 启动连接健康监控
            await self.start_connection_health_monitor()
            
            # 启动内存监控
            await self.start_memory_monitor()
            
            # 启动定期清理调度器
            await self.start_periodic_cleanup()
            
            # 启动仓位同步监控
            await self.start_position_sync_monitor()
            
            logger.info("所有监控系统已启动")
            
        except Exception as e:
            logger.error(f"启动监控系统失败: {e}")
    
    async def start_memory_monitor(self):
        """启动内存监控系统"""
        if hasattr(self, 'memory_monitor_task') and self.memory_monitor_task and not self.memory_monitor_task.done():
            return
        
        async def memory_monitor_loop():
            while True:
                try:
                    await self._check_memory_usage()
                    await asyncio.sleep(300)  # 每5分钟检查一次
                except Exception as e:
                    logger.error(f"内存监控循环出错: {e}")
                    await asyncio.sleep(60)
        
        self.memory_monitor_task = asyncio.create_task(memory_monitor_loop())
        logger.info("内存监控系统已启动")

    async def _check_memory_usage(self):
        """检查内存使用情况"""
        try:
            # 获取当前进程内存信息
            import psutil
            process = psutil.Process()
            memory_info = process.memory_info()
            
            # 获取系统内存信息
            system_memory = psutil.virtual_memory()
            
            # 记录内存使用
            memory_mb = memory_info.rss / 1024 / 1024
            
            # 记录内存使用历史
            if not hasattr(self, 'memory_usage_history'):
                self.memory_usage_history = []
            
            self.memory_usage_history.append({
                'timestamp': time.time(),
                'memory_mb': memory_mb,
                'system_percent': system_memory.percent
            })
            
            # 只保留最近100条记录
            if len(self.memory_usage_history) > 100:
                self.memory_usage_history = self.memory_usage_history[-100:]
            
            # 如果内存使用过高，触发清理
            max_memory_usage = getattr(self, 'max_memory_usage', 1024 * 1024 * 1024)  # 默认1GB
            if memory_info.rss > max_memory_usage:
                logger.warning(f"[内存监控] 内存使用过高 ({memory_mb:.2f} MB)，开始清理...")
                await self._perform_memory_cleanup()
            
            # 如果系统内存不足，记录警告
            if system_memory.percent > 90:
                logger.warning(f"[内存监控] 系统内存不足: {system_memory.percent:.1f}%")
            
        except Exception as e:
            logger.error(f"检查内存使用情况失败: {e}")

    async def _perform_memory_cleanup(self):
        """执行内存清理"""
        try:
            # 1. 清理价格缓存
            await self._cleanup_price_cache()
            
            # 2. 清理过期的连接对象
            # await self._cleanup_expired_connections()  # 方法已删除
            
            # 3. 清理过期的锁
            self.cleanup_expired_locks()
            
            # 4. 强制垃圾回收
            import gc
            collected = gc.collect()
            
            # 5. 清理异步任务
            await self._cleanup_stale_tasks()
            
            # 6. 清理内存使用历史
            if hasattr(self, 'memory_usage_history') and len(self.memory_usage_history) > 50:
                self.memory_usage_history = self.memory_usage_history[-50:]
            
            # 7. 🚀 新增：清理无效连接
            await self._cleanup_invalid_connections()
            
        except Exception as e:
            logger.error(f"执行内存清理失败: {e}")

    async def _cleanup_price_cache(self):
        """清理价格缓存"""
        try:
            if 'TICKER_CACHE' in globals():
                global TICKER_CACHE, TICKER_CACHE_TIME
            old_cache_size = len(TICKER_CACHE)
            current_time = time.time()
            keys_to_remove = []
            
            for key, value in TICKER_CACHE.items():
                if key in TICKER_CACHE_TIME:
                    if current_time - TICKER_CACHE_TIME[key] > 3600:  # 1小时过期
                        keys_to_remove.append(key)
            
            for key in keys_to_remove:
                del TICKER_CACHE[key]
                if key in TICKER_CACHE_TIME:
                    del TICKER_CACHE_TIME[key]
            
            if keys_to_remove:
                    logger.info(f"[内存清理] 清理了 {len(keys_to_remove)} 个过期价格缓存")
            
        except Exception as e:
            logger.error(f"清理价格缓存失败: {e}")

    async def stop_all_monitoring_systems(self):
        """停止所有监控系统"""
        try:
            logger.info("正在停止所有监控系统...")
            
            # 停止连接健康监控
            if self.connection_health_monitor_task:
                self.connection_health_monitor_task.cancel()
                try:
                    await self.connection_health_monitor_task
                except asyncio.CancelledError:
                    pass
            
            # 停止内存监控
            if self.memory_monitor_task:
                self.memory_monitor_task.cancel()
                try:
                    await self.memory_monitor_task
                except asyncio.CancelledError:
                    pass
            
            # 停止定期清理调度器
            if self.cleanup_task:
                self.cleanup_task.cancel()
                try:
                    await self.cleanup_task
                except asyncio.CancelledError:
                    pass
            
            logger.info("所有监控系统已停止")
            
        except Exception as e:
            logger.error(f"停止监控系统失败: {e}")

    # ==================== 连接活动时间更新 ====================
    
    def _update_connection_activity(self, client):
        """更新连接活动时间"""
        try:
            if hasattr(client, 'last_activity'):
                client.last_activity = time.time()
        except Exception as e:
            logger.error(f"更新连接活动时间失败: {e}")

    # ==================== 诊断和状态报告 ====================
    
    async def diagnose_websocket_status(self):
        """诊断WebSocket连接状态"""
        try:
            logger.info("=== WebSocket连接状态诊断 ===")
            
            for customer in self.customers:
                if hasattr(customer, 'ws_client'):
                    client = customer.ws_client
                    status = getattr(client, 'is_connected', lambda: 'Unknown')()
                    last_heartbeat = getattr(client, 'last_heartbeat', 'Unknown')
                    customer_uid = customer.customer_uid if hasattr(customer, 'customer_uid') else customer.get('customer_uid', 'unknown')
                    
                    logger.info(f"客户 {customer_uid}:")
                    logger.info(f"  - 连接状态: {status}")
                    logger.info(f"  - 最后心跳: {last_heartbeat}")
                    logger.info(f"  - 订阅状态: {getattr(client, 'subscriptions', 'Unknown')}")
            
            # 检查价格缓存
            cache_count = len(TICKER_CACHE) if 'TICKER_CACHE' in globals() else 0
            logger.info(f"价格缓存数量: {cache_count}")
            
            # 检查活跃连接数
            active_connections = sum(1 for c in self.customers if hasattr(c, 'ws_client') and getattr(c.ws_client, 'is_connected', lambda: False)())
            logger.info(f"活跃连接数: {active_connections}/{len(self.customers)}")
            
        except Exception as e:
            logger.error(f"诊断WebSocket状态失败: {e}")

    def log_connection_status(self):
        """记录所有连接状态"""
        try:
            logger.info("=== 当前连接状态 ===")
            
            # 客户连接状态
            for customer in self.customers:
                if hasattr(customer, 'ws_client'):
                    client = customer.ws_client
                    status = getattr(client, 'is_connected', lambda: 'Unknown')()
                    last_activity = getattr(client, 'last_activity', 'Unknown')
                    customer_uid = customer.customer_uid if hasattr(customer, 'customer_uid') else customer.get('customer_uid', 'unknown')
                    
                    logger.info(f"客户 {customer_uid}: 连接={status}, 最后活动={last_activity}")
            
            # 信号源连接状态
            for signal_source in self.signal_sources:
                if hasattr(signal_source, 'ws_client'):
                    client = signal_source.ws_client
                    status = getattr(client, 'is_connected', lambda: 'Unknown')()
                    last_activity = getattr(client, 'last_activity', 'Unknown')
                    source_uid = signal_source.source_uid if hasattr(signal_source, 'source_uid') else signal_source.get('source_uid', 'unknown')
                    
                    logger.info(f"信号源 {source_uid}: 连接={status}, 最后活动={last_activity}")
            
            # 价格缓存状态
            cache_count = len(TICKER_CACHE) if 'TICKER_CACHE' in globals() else 0
            logger.info(f"价格缓存: {cache_count} 个品种")
            
            logger.info("=== 连接状态记录完成 ===")
            
        except Exception as e:
            logger.error(f"记录连接状态失败: {e}")



    # ==================== 连接健康监控系统 ====================
    
    async def start_connection_health_monitor(self):
        """启动连接健康监控系统"""
        if self.connection_health_monitor_task and not self.connection_health_monitor_task.done():
            return
        
        async def health_monitor_loop():
            while True:
                try:
                    await self._perform_connection_health_check()
                    await asyncio.sleep(self.health_check_interval)
                except Exception as e:
                    logger.error(f"连接健康监控循环出错: {e}")
                    await asyncio.sleep(60)
        
        self.connection_health_monitor_task = asyncio.create_task(health_monitor_loop())
        logger.info("连接健康监控系统已启动")

    # ==================== 定期清理调度器 ====================
    
    async def start_periodic_cleanup(self):
        """启动定期清理调度器"""
        if self.cleanup_task and not self.cleanup_task.done():
            return
        
        async def cleanup_loop():
            while True:
                try:
                    await self._perform_periodic_cleanup()
                    await asyncio.sleep(300)  # 5分钟执行一次清理
                except Exception as e:
                    logger.error(f"定期清理循环出错: {e}")
                    await asyncio.sleep(60)
        
        self.cleanup_task = asyncio.create_task(cleanup_loop())
        logger.info("定期清理调度器已启动")
        
    async def _perform_periodic_cleanup(self):
        """执行定期清理任务"""
        try:
            # 清理已完成的WebSocket任务
            await self._cleanup_completed_websocket_tasks()

            # 清理过期的价格缓存
            await self._cleanup_price_cache()

            # 清理过期的连接状态
            await self._cleanup_expired_connection_status()
            
        except Exception as e:
            logger.error(f"执行定期清理失败: {e}")

    async def _cleanup_completed_websocket_tasks(self):
        """清理已完成的WebSocket任务"""
        try:
            # 清理已完成的连接健康监控任务
            if (self.connection_health_monitor_task and
                self.connection_health_monitor_task.done()):
                self.connection_health_monitor_task = None

            # 清理已完成的定期清理任务
            if (self.cleanup_task and
                self.cleanup_task.done()):
                self.cleanup_task = None



            # 清理已完成的WebSocket客户端任务
            for customer in self.customers:
                if hasattr(customer, 'ws_client'):
                    client = customer.ws_client
                    if hasattr(client, '_listen_task') and client._listen_task and client._listen_task.done():
                        client._listen_task = None
                    if hasattr(client, '_heartbeat_task') and client._heartbeat_task and client._heartbeat_task.done():
                        client._heartbeat_task = None
                    if hasattr(client, '_activity_timer') and client._activity_timer and client._activity_timer.done():
                        client._activity_timer = None
            
        except Exception as e:
            logger.error(f"清理WebSocket任务失败: {e}")

    async def _cleanup_expired_connection_status(self):
        """清理过期的连接状态"""
        try:
            # 清理超过1小时的连接状态记录
            current_time = time.time()
            expired_keys = []

            for key, status in self.websocket_health_status.items():
                if current_time - status.get('last_check', 0) > 3600:  # 1小时
                    expired_keys.append(key)

            for key in expired_keys:
                del self.websocket_health_status[key]
            
        except Exception as e:
            logger.error(f"清理连接状态失败: {e}")

    async def _perform_connection_health_check(self):
        """执行连接健康检查"""
        try:
            # 只在有问题时才记录日志，减少正常情况下的日志输出
            current_time = time.time()
            
            # 检查客户连接
            for customer in self.customers:
                await self._check_customer_connection_health(customer, current_time)
            
            # 检查信号源连接
            for signal_source in self.signal_sources:
                await self._check_signal_source_connection_health(signal_source, current_time)
            
            # 更新连接健康状态
            await self._update_connection_health_status()
            
        except Exception as e:
            logger.error(f"执行连接健康检查失败: {e}")

    async def _check_customer_connection_health(self, customer, current_time):
        """检查单个客户连接健康状态"""
        try:
            customer_uid = customer.customer_uid if hasattr(customer, 'customer_uid') else customer.get('customer_uid', 'unknown')
            
            if not hasattr(customer, 'ws_client'):
                logger.warning(f"🔍 客户 {customer_uid} 没有WebSocket客户端")
                return
            
            client = customer.ws_client
            health_status = await self._verify_websocket_connection(client)
            
            # 更新健康状态
            self.websocket_health_status[customer_uid] = {
                'is_healthy': health_status,
                'last_check': current_time,
                'last_activity': getattr(client, 'last_activity', current_time),
                'connection_age': current_time - getattr(client, 'connection_start_time', current_time)
            }
            
            # 如果连接不健康，尝试重连
            if not health_status:
                logger.warning(f"🔍 客户 {customer_uid} 连接不健康，开始重连...")
                # 🚀 增加详细的连接状态信息
                if hasattr(client, '_last_pong_time') and hasattr(client, '_ping_failures'):
                    last_pong_time = getattr(client, '_last_pong_time', 0)
                    ping_failures = getattr(client, '_ping_failures', 0)
                    logger.info(f"🔍 客户 {customer_uid} 心跳状态: last_pong={current_time - last_pong_time:.1f}秒前, ping_failures={ping_failures}")
                
                await self._smart_reconnect_customer(customer)
            else:
                logger.debug(f"🔍 客户 {customer_uid} 连接健康")
            
        except Exception as e:
            logger.error(f"🔍 检查客户 {customer_uid} 连接健康状态失败: {e}")

    async def _check_signal_source_connection_health(self, signal_source, current_time):
        """检查单个信号源连接健康状态"""
        try:
            source_uid = signal_source.source_uid if hasattr(signal_source, 'source_uid') else signal_source.get('source_uid', 'unknown')
            
            if not hasattr(signal_source, 'ws_client'):
                logger.warning(f"信号源 {source_uid} 没有WebSocket客户端")
                await self._send_signal_source_connection_alert(signal_source, "没有WebSocket客户端")
                return
            
            client = signal_source.ws_client
            health_status = await self._verify_websocket_connection(client)
            
            # 更新健康状态
            self.websocket_health_status[f"signal_{source_uid}"] = {
                'is_healthy': health_status,
                'last_check': current_time,
                'last_activity': getattr(client, 'last_activity', current_time),
                'connection_age': current_time - getattr(client, 'connection_start_time', current_time)
            }
            
            # 如果连接不健康，尝试重连并发送警报
            if not health_status:
                logger.warning(f"信号源 {source_uid} 连接不健康，开始重连...")
                await self._send_signal_source_connection_alert(signal_source, "连接不健康，开始重连")
                await self._smart_reconnect_signal_source(signal_source)
                
                # 重连后检查仓位同步
                await self._check_signal_source_position_sync(signal_source)
            
        except Exception as e:
            source_uid = signal_source.source_uid if hasattr(signal_source, 'source_uid') else signal_source.get('source_uid', 'unknown')
            logger.error(f"检查信号源 {source_uid} 连接健康状态失败: {e}")
            await self._send_signal_source_connection_alert(signal_source, f"健康检查失败: {e}")

    async def _check_signal_source_position_sync(self, signal_source):
        """检查信号源仓位同步状态，防止错过开仓、平仓、减仓信号"""
        try:
            source_uid = signal_source.source_uid if hasattr(signal_source, 'source_uid') else signal_source.get('source_uid', 'unknown')
            source_name = signal_source.name if hasattr(signal_source, 'name') else signal_source.get('name', '未知')
            
            logger.info(f"[仓位同步检查] 开始检查信号源 {source_uid} 仓位同步状态")
            
            # 1. 从交易所获取信号源实际持仓
            exchange_positions = await self._get_signal_source_exchange_positions(signal_source)
            
            # 2. 从数据库获取本地记录的持仓
            local_positions = await self._get_signal_source_local_positions(source_uid)
            
            # 3. 检查开仓信号丢失（现有逻辑）
            missing_positions = await self._find_missing_positions(exchange_positions, local_positions)
            
            # 4. 新增：检查平仓信号丢失
            closed_positions = await self._find_closed_positions(exchange_positions, local_positions)
            
            # 5. 新增：检查减仓信号丢失
            reduced_positions = await self._find_reduced_positions(exchange_positions, local_positions)
            
            # 6. 处理各种信号丢失情况
            if missing_positions:
                logger.warning(f"[仓位同步检查] 发现 {len(missing_positions)} 个缺失的持仓（开仓信号丢失），开始补全...")
                await self._handle_missing_positions(signal_source, missing_positions)
            
            if closed_positions:
                logger.warning(f"[仓位同步检查] 发现 {len(closed_positions)} 个已平仓但本地未更新的持仓（平仓信号丢失），开始处理...")
                await self._handle_closed_positions(signal_source, closed_positions)
            
            if reduced_positions:
                logger.warning(f"[仓位同步检查] 发现 {len(reduced_positions)} 个已减仓但本地未更新的持仓（减仓信号丢失），开始处理...")
                await self._handle_reduced_positions(signal_source, reduced_positions)
            
            # 7. 新增：检查客户仓位同步状态
            await self._check_customer_positions_sync(signal_source, exchange_positions)
            
            if not missing_positions and not closed_positions and not reduced_positions:
                logger.info(f"[仓位同步检查] 信号源 {source_uid} 仓位同步正常，无信号丢失")
            else:
                # 发送仓位异常警报
                await self._send_position_sync_alert(signal_source, missing_positions, closed_positions, reduced_positions)
                
        except Exception as e:
            source_uid = signal_source.source_uid if hasattr(signal_source, 'source_uid') else signal_source.get('source_uid', 'unknown')
            logger.error(f"[仓位同步检查] 检查信号源 {source_uid} 仓位同步失败: {e}")
            await self._send_signal_source_connection_alert(signal_source, f"仓位同步检查失败: {e}")

    async def _get_signal_source_exchange_positions(self, signal_source):
        """从交易所获取信号源实际持仓"""
        try:
            source_uid = signal_source.source_uid if hasattr(signal_source, 'source_uid') else signal_source.get('source_uid', 'unknown')
            
            # 获取信号源的API配置
            is_demo = signal_source.is_demo if hasattr(signal_source, 'is_demo') else signal_source.get('is_demo', False)
            api_key = signal_source.api_key if hasattr(signal_source, 'api_key') else signal_source.get('api_key', '')
            api_secret = signal_source.api_secret if hasattr(signal_source, 'api_secret') else signal_source.get('api_secret', '')
            passphrase = signal_source.passphrase if hasattr(signal_source, 'passphrase') else signal_source.get('passphrase', '')
            
            if not api_key or not api_secret or not passphrase:
                logger.warning(f"[仓位同步检查] 信号源 {source_uid} API配置不完整")
                return []
            
            # 创建REST API客户端
            
            rest_client = OKXRESTClient(
                api_key=api_key,
                api_secret=api_secret,
                passphrase=passphrase,
                is_demo=is_demo
            )
            
            # 调用REST API获取持仓
            positions_response = await rest_client.get_positions()
            
            if not positions_response or 'data' not in positions_response:
                logger.warning(f"[仓位同步检查] 获取信号源 {source_uid} 持仓失败: {positions_response}")
                return []
            
            # 过滤出有持仓的记录
            positions = []
            for pos in positions_response['data']:
                try:
                    sz = float(pos.get('pos', '0') or '0')
                    if sz > 0:  # 有持仓
                        avg_px = float(pos.get('avgPx', '0') or '0')
                        upl = float(pos.get('upl', '0') or '0')
                        margin = float(pos.get('margin', '0') or '0')
                        
                        positions.append({
                            'symbol': pos.get('instId'),
                            'pos_side': pos.get('posSide'),
                            'size': sz,
                            'avg_px': avg_px,
                            'upl': upl,
                            'margin': margin
                        })
                except (ValueError, TypeError) as e:
                    logger.warning(f"[仓位同步检查] 跳过无效持仓数据: {pos}, 错误: {e}")
                    continue
            
            logger.info(f"[仓位同步检查] 信号源 {source_uid} 交易所持仓: {len(positions)} 个")
            return positions
            
        except Exception as e:
            source_uid = signal_source.source_uid if hasattr(signal_source, 'source_uid') else signal_source.get('source_uid', 'unknown')
            logger.error(f"[仓位同步检查] 获取信号源 {source_uid} 交易所持仓失败: {e}")
            return []

    async def _get_signal_source_local_positions(self, source_uid):
        """从数据库获取本地记录的信号源持仓"""
        try:
            # 查询本地数据库中的信号源持仓 - 使用全局连接池
            db_pool = get_global_db_pool()
            
            # 查询状态为open的持仓，必须包含trade_uid字段
            positions = db_pool.query(
                "SELECT trade_uid, symbol, pos_side, (volume_contract - IFNULL(close_volume_contract, 0)) as volume_contract, open_px FROM signal_account_trades WHERE signal_source_uid=%s AND status='open'",
                (source_uid,)
            )
            
            logger.info(f"[仓位同步检查] 信号源 {source_uid} 本地持仓: {len(positions)} 个")
            return positions
            
        except Exception as e:
            logger.error(f"[仓位同步检查] 获取信号源 {source_uid} 本地持仓失败: {e}")
            return []

    async def _find_missing_positions(self, exchange_positions, local_positions):
        """找出缺失的持仓"""
        try:
            missing_positions = []
            
            # 将本地持仓转换为字典，方便查找
            local_positions_dict = {}
            for pos in local_positions:
                key = f"{pos['symbol']}_{pos['pos_side']}"
                local_positions_dict[key] = pos
            
            # 检查交易所持仓是否在本地存在
            for exchange_pos in exchange_positions:
                key = f"{exchange_pos['symbol']}_{exchange_pos['pos_side']}"
                
                if key not in local_positions_dict:
                    # 本地没有记录，说明错过了开仓信号
                    missing_positions.append(exchange_pos)
                    logger.warning(f"[仓位同步检查] 发现缺失持仓: {exchange_pos['symbol']} {exchange_pos['pos_side']} {exchange_pos['size']}张")
            
            return missing_positions
            
        except Exception as e:
            logger.error(f"[仓位同步检查] 查找缺失持仓失败: {e}")
            return []

    async def _handle_missing_positions(self, signal_source, missing_positions):
        """处理缺失的持仓 - 补全丢失的信号"""
        try:
            source_uid = signal_source.source_uid if hasattr(signal_source, 'source_uid') else signal_source.get('source_uid', 'unknown')
            source_name = signal_source.name if hasattr(signal_source, 'name') else signal_source.get('name', '未知')
            
            # 发送仓位异常警报
            alert_message = f"🚨 信号源仓位异常警报\n\n" \
                           f"信号源: {source_name} ({source_uid})\n" \
                           f"异常原因: 发现 {len(missing_positions)} 个缺失持仓\n" \
                           f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n" \
                           f"⚠️ 可能因断连错过开仓信号，正在自动补全..."
            
            # 发送钉钉通知
            if should_send_alert_notification("warning"):
                alert_info = {
                    'title': '信号源开仓信号丢失',
                    'level': 'warning',
                    'time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                    'message': f"信号源 {source_uid} 发现 {len(missing_positions)} 个缺失的持仓",
                    'account': source_uid,
                    'strategy': '仓位同步检查',
                    'symbol': ', '.join([pos['symbol'] for pos in missing_positions]),
                    'suggestion': '系统正在自动补全丢失的信号'
                }
                await send_alert_notification_async("warning", alert_info)
            
            logger.error(f"[仓位异常警报] {alert_message}")
            
            # 自动补全：为每个缺失的持仓创建记录并触发跟单
            for missing_pos in missing_positions:
                await self._fix_missing_position(signal_source, missing_pos)
                
        except Exception as e:
            logger.error(f"[仓位同步检查] 处理缺失持仓失败: {e}")

    async def _fix_missing_position(self, signal_source, missing_position):
        """修复缺失的持仓 - 补全丢失的信号"""
        try:
            source_uid = signal_source.source_uid if hasattr(signal_source, 'source_uid') else signal_source.get('source_uid', 'unknown')
            
            symbol = missing_position['symbol']
            pos_side = missing_position['pos_side']
            size = missing_position['size']
            avg_px = missing_position['avg_px']
            
            logger.info(f"[仓位补全] 开始补全缺失持仓: {symbol} {pos_side} {size}张 @ {avg_px}")
            
            # 1. 在数据库中创建信号源持仓记录
            trade_uid = await self._create_signal_source_trade_record(source_uid, symbol, pos_side, size, avg_px)
            
            if trade_uid:
                # 2. 触发客户跟单
                await self._trigger_customer_follow_for_missing_position(signal_source, symbol, pos_side, size, avg_px, trade_uid)
                
                logger.info(f"[仓位补全] 缺失持仓补全完成: {trade_uid}")
            else:
                logger.error(f"[仓位补全] 创建信号源持仓记录失败")
                
        except Exception as e:
            logger.error(f"[仓位补全] 补全缺失持仓失败: {e}")

    async def _create_signal_source_trade_record(self, source_uid, symbol, pos_side, size, avg_px):
        """创建信号源持仓记录 - 补全丢失的信号"""
        try:
            from config import get_mysql_config
            import uuid
            
            db_pool = get_global_db_pool()
            is_demo = get_global_is_demo()
            # 生成交易UID
            trade_uid = f"SYNC_{uuid.uuid4().hex[:16]}"
            
            # 确定交易方向
            direction = 'buy' if pos_side == 'long' else 'sell'
            
            # 计算名义价值
            multiplier = get_contract_multiplier(symbol)
            volume_usdt = size * multiplier * avg_px
            
            # 插入信号源交易记录
            db_pool.execute(
                "INSERT INTO signal_account_trades (trade_uid, signal_source_uid, symbol, direction, pos_side, volume, volume_contract, open_px, status, trade_type, is_demo, created_at) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())",
                (trade_uid, source_uid, symbol, direction, pos_side, volume_usdt, size, avg_px, 'open', 'open', is_demo)
            )
            
            logger.info(f"[仓位补全] 创建信号源持仓记录成功: {trade_uid}")
            return trade_uid
            
        except Exception as e:
            logger.error(f"[仓位补全] 创建信号源持仓记录失败: {e}")
            return None

    async def _trigger_customer_follow_for_missing_position(self, signal_source, symbol, pos_side, size, avg_px, trade_uid):
        """为缺失的持仓触发客户跟单 - 补全丢失的信号"""
        try:
            source_uid = signal_source.source_uid if hasattr(signal_source, 'source_uid') else signal_source.get('source_uid', 'unknown')
            
            logger.info(f"[仓位补全] 为缺失持仓触发客户跟单: {symbol} {pos_side} {size}张 @ {avg_px}")
            
            # 查找跟随该信号源的客户
            customers = await self.get_following_customers(source_uid)
            
            if not customers:
                logger.info(f"[仓位补全] 没有客户跟随信号源: {source_uid}")
                return
            
            # 为每个客户执行跟单
            success_count = 0
            for customer in customers:
                try:
                    # 确定开仓方向
                    direction = 'buy' if pos_side == 'long' else 'sell'
                    
                    # 执行客户跟单
                    result = await self.execute_customer_follow_trade(customer, signal_source, symbol, direction, pos_side, size, avg_px, trade_uid)
                    
                    if result and result.get('success'):
                        logger.info(f"[仓位补全] 客户 {customer.customer_uid} 跟单成功")
                        success_count += 1
                    else:
                        error_msg = result.get('error', '未知错误') if result else '执行失败'
                        logger.error(f"[仓位补全] 客户 {customer.customer_uid} 跟单失败: {error_msg}")
                    
                except Exception as e:
                    logger.error(f"[仓位补全] 客户 {customer.customer_uid} 跟单异常: {e}")
                    continue
            
            logger.info(f"[仓位补全] 客户跟单完成，成功 {success_count}/{len(customers)} 个客户")
            
        except Exception as e:
            logger.error(f"[仓位补全] 触发客户跟单失败: {e}")

    async def _send_signal_source_connection_alert(self, signal_source, reason):
        """发送信号源连接异常警报"""
        try:
            source_uid = signal_source.source_uid if hasattr(signal_source, 'source_uid') else signal_source.get('source_uid', 'unknown')
            source_name = signal_source.name if hasattr(signal_source, 'name') else signal_source.get('name', '未知')
            
            alert_message = f"🚨 信号源连接异常警报\n\n" \
                           f"信号源: {source_name} ({source_uid})\n" \
                           f"异常原因: {reason}\n" \
                           f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n" \
                           f"⚠️ 可能错过信号源开仓信号，请立即检查！"
            
            # 发送钉钉通知
            if should_send_alert_notification("error"):
                alert_info = {
                    'title': '信号源连接异常',
                    'level': 'error',
                    'time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                    'message': f"信号源 {source_uid} 连接异常: {reason}",
                    'account': source_uid,
                    'strategy': '连接监控',
                    'suggestion': '请立即检查信号源连接状态'
                }
                await send_alert_notification_async("error", alert_info)
            
            logger.error(f"[信号源警报] {alert_message}")
            
        except Exception as e:
            logger.error(f"发送信号源连接警报失败: {e}")

    async def _update_connection_health_status(self):
        """更新连接健康状态"""
        try:
            healthy_count = sum(1 for status in self.websocket_health_status.values() if status.get('is_healthy', False))
            total_count = len(self.websocket_health_status)
            
            # 只在有不健康连接时才记录日志
            if healthy_count < total_count:
                logger.warning(f"连接健康状态: {healthy_count}/{total_count} 健康，发现 {total_count - healthy_count} 个不健康的连接")
                
        except Exception as e:
            logger.error(f"更新连接健康状态失败: {e}")

    # ==================== 智能重连系统 ====================
    
    async def _resubscribe_customer_data(self, customer):
        """重新订阅客户数据"""
        try:
            customer_uid = customer.customer_uid if hasattr(customer, 'customer_uid') else customer.get('customer_uid', 'unknown')
            logger.info(f"📡 开始重新订阅客户 {customer_uid} 数据...")
            
            if not hasattr(customer, 'ws_client') or not customer.ws_client:
                logger.error(f"📡 客户 {customer_uid} 没有WebSocket客户端，无法重新订阅")
                return False
            
            client = customer.ws_client
            
            # 等待连接稳定
            await asyncio.sleep(1)
            
            # 重新订阅账户数据
            try:
                async def on_account(data):
                    try:
                        logger.debug(f"[账户数据] 客户{customer_uid}: {data}")
                    except Exception as e:
                        logger.error(f"[账户数据] 处理异常: {e}")
                
                account_subscribed = await client.subscribe("account", on_account)
                if account_subscribed:
                    logger.info(f"✅ 客户{customer_uid}的账户订阅重新订阅成功")
                else:
                    logger.warning(f"⚠️ 客户{customer_uid}的账户订阅重新订阅失败")
                    return False
            except Exception as e:
                logger.error(f"❌ 重新订阅客户{customer_uid}的账户数据失败: {e}")
                return False
            
            # 重新订阅订单数据（可选）
            try:
                async def on_order(data):
                    try:
                        logger.debug(f"[订单数据] 客户{customer_uid}: {data}")
                    except Exception as e:
                        logger.error(f"[订单数据] 处理异常: {e}")
                
                orders_subscribed = await client.subscribe("orders", on_order, instType="SWAP")
                if orders_subscribed:
                    logger.info(f"✅ 客户{customer_uid}的订单订阅重新订阅成功")
                else:
                    logger.warning(f"⚠️ 客户{customer_uid}的订单订阅重新订阅失败")
            except Exception as e:
                logger.error(f"❌ 重新订阅客户{customer_uid}的订单数据失败: {e}")
                # 订单订阅失败不影响整体结果
            
            logger.info(f"📡 客户 {customer_uid} 核心数据重新订阅完成")
            return True
            
        except Exception as e:
            customer_uid = customer.customer_uid if hasattr(customer, 'customer_uid') else customer.get('customer_uid', 'unknown')
            logger.error(f"📡 重新订阅客户 {customer_uid} 数据失败: {e}")
            return False

    async def _resubscribe_signal_source_data(self, signal_source):
        """重新订阅信号源数据"""
        try:
            source_uid = signal_source.source_uid if hasattr(signal_source, 'source_uid') else signal_source.get('source_uid', 'unknown')
            logger.info(f"📡 开始重新订阅信号源 {source_uid} 数据...")
            
            if not hasattr(signal_source, 'ws_client') or not signal_source.ws_client:
                logger.error(f"📡 信号源 {source_uid} 没有WebSocket客户端，无法重新订阅")
                return False
            
            client = signal_source.ws_client
            
            # 等待连接稳定
            await asyncio.sleep(1)
            
            # 重新订阅账户数据
            try:
                async def on_account(data):
                    try:
                        logger.debug(f"[信号源账户] {source_uid}: {data}")
                    except Exception as e:
                        logger.error(f"[信号源账户] 处理异常: {e}")
                
                account_subscribed = await client.subscribe("account", on_account)
                if account_subscribed:
                    logger.info(f"✅ 信号源{source_uid}的账户订阅重新订阅成功")
                else:
                    logger.warning(f"⚠️ 信号源{source_uid}的账户订阅重新订阅失败")
                    return False
            except Exception as e:
                logger.error(f"❌ 重新订阅信号源{source_uid}的账户数据失败: {e}")
                return False
            
            # 重新订阅订单数据
            try:
                async def on_order(data):
                    try:
                        logger.debug(f"[信号源订单] {source_uid}: {data}")
                    except Exception as e:
                        logger.error(f"[信号源订单] 处理异常: {e}")
                
                orders_subscribed = await client.subscribe("orders", on_order, instType="SWAP")
                if orders_subscribed:
                    logger.info(f"✅ 信号源{source_uid}的订单订阅重新订阅成功")
                else:
                    logger.warning(f"⚠️ 信号源{source_uid}的订单订阅重新订阅失败")
                    return False
            except Exception as e:
                logger.error(f"❌ 重新订阅信号源{source_uid}的订单数据失败: {e}")
                return False
            
            logger.info(f"📡 信号源 {source_uid} 数据重新订阅完成")
            return True
            
        except Exception as e:
            source_uid = signal_source.source_uid if hasattr(signal_source, 'source_uid') else signal_source.get('source_uid', 'unknown')
            logger.error(f"📡 重新订阅信号源 {source_uid} 数据失败: {e}")
            return False

    async def _smart_reconnect_customer(self, customer):
        """智能重连客户"""
        try:
            customer_uid = customer.customer_uid if hasattr(customer, 'customer_uid') else customer.get('customer_uid', 'unknown')
            logger.info(f"🔄 开始智能重连客户: {customer_uid}")
            
            # 检查客户重连保护（使用统一连接管理器）
            client_key = f"customer_{customer_uid}"
            if self.connection_manager._is_reconnect_protected(client_key):
                logger.warning(f"⚠️ 客户 {customer_uid} 处于重连保护期，跳过本次重连")
                return False
            
            # 记录重连尝试（使用统一连接管理器）
            self.connection_manager._record_reconnect_attempt(client_key)
            
            # 设置重连标记，避免重复重连
            if hasattr(customer, 'ws_client') and hasattr(customer.ws_client, '_reconnecting'):
                if customer.ws_client._reconnecting:
                    logger.info(f"🔄 客户 {customer_uid} 正在重连中，跳过重复重连")
                    return True
                customer.ws_client._reconnecting = True
            
            # 1. 关闭旧连接
            logger.info(f"🔄 步骤1: 关闭客户 {customer_uid} 旧连接...")
            if hasattr(customer, 'ws_client'):
                old_client = customer.ws_client
                try:
                    # 检查旧连接状态
                    if hasattr(old_client, 'ws') and old_client.ws:
                        ws_closed = getattr(old_client.ws, 'closed', False)
                        logger.info(f"🔄 旧连接WebSocket状态: {'已关闭' if ws_closed else '已连接'}")
                    
                    # 检查旧连接的订阅
                    if hasattr(old_client, '_subscriptions'):
                        old_subs = list(old_client._subscriptions.keys()) if old_client._subscriptions else []
                        logger.info(f"🔄 旧连接订阅数量: {len(old_subs)}")
                        if old_subs:
                            logger.info(f"🔄 旧连接订阅列表: {old_subs}")
                    
                    await old_client.close()
                    logger.info(f"✅ 客户 {customer_uid} 旧连接已关闭")
                except Exception as e:
                    logger.warning(f"⚠️ 关闭旧连接时出错: {e}")
            
            # 2. 等待连接完全关闭
            logger.info(f"🔄 步骤2: 等待连接完全关闭...")
            await asyncio.sleep(2)
            
            # 3. 创建新连接
            logger.info(f"🔄 步骤3: 创建客户 {customer_uid} 新连接...")
            new_client = await self.connection_manager.reconnect_client(
                client_type="customer",
                client_id=customer_uid,
                is_demo=customer.is_demo if hasattr(customer, 'is_demo') else False,
                api_key=customer.api_key,
                api_secret=customer.api_secret,
                passphrase=customer.passphrase
            )
            customer.ws_client = new_client
            
            # 4. 设置连接开始时间
            logger.info(f"🔄 步骤4: 设置新连接参数...")
            new_client.connection_start_time = time.time()
            new_client.last_activity = time.time()
            new_client._reconnecting = False  # 重连完成
            
            # 5. 验证新连接
            logger.info(f"🔄 步骤5: 验证新连接健康状态...")
            if not await self._verify_websocket_connection(new_client):
                logger.error(f"❌ 客户 {customer_uid} 新连接验证失败")
                return False
            logger.info(f"✅ 客户 {customer_uid} 新连接验证成功")
            
            # 6. 重新订阅数据
            logger.info(f"🔄 步骤6: 重新订阅客户 {customer_uid} 数据...")
            resubscribe_success = await self._resubscribe_customer_data(customer)
            if not resubscribe_success:
                logger.error(f"❌ 客户 {customer_uid} 重新订阅失败")
                return False
            logger.info(f"✅ 客户 {customer_uid} 重新订阅成功")
            
            # 7. 验证订阅是否成功
            logger.info(f"🔄 步骤7: 等待订阅生效...")
            await asyncio.sleep(3)  # 等待3秒让订阅生效
            
            # 8. 最终验证
            logger.info(f"🔄 步骤8: 最终验证重连结果...")
            
            # 检查连接状态
            final_health_check = await self._verify_websocket_connection(new_client)
            logger.info(f"🔄 最终健康检查: {'通过' if final_health_check else '失败'}")
            
            # 检查订阅状态
            if hasattr(new_client, '_subscriptions'):
                final_subs = list(new_client._subscriptions.keys()) if new_client._subscriptions else []
                logger.info(f"🔄 最终订阅数量: {len(final_subs)}")
                if final_subs:
                    logger.info(f"🔄 最终订阅列表: {final_subs}")
                else:
                    logger.warning(f"⚠️ 重连后没有订阅，可能有问题")
            
            # 检查健康评分
            if hasattr(new_client, 'health_monitor') and new_client.health_monitor:
                final_health_score = new_client.health_monitor.health_score
                logger.info(f"🔄 最终健康评分: {final_health_score}")
                if final_health_score > 50:
                    logger.info(f"✅ 客户 {customer_uid} 重连成功，健康评分恢复正常")
                else:
                    logger.warning(f"⚠️ 客户 {customer_uid} 重连后健康评分仍较低: {final_health_score}")
            
            logger.info(f"🎉 客户 {customer_uid} 智能重连完成！")
            
            # 重连成功，重置保护状态（使用统一连接管理器）
            self.connection_manager._reset_reconnect_protection(client_key)
            
            return True
            
        except Exception as e:
            logger.error(f"❌ 智能重连客户 {customer_uid} 失败: {e}")
            # 清除重连标记
            if hasattr(customer, 'ws_client') and hasattr(customer.ws_client, '_reconnecting'):
                customer.ws_client._reconnecting = False
            return False

    async def _smart_reconnect_signal_source(self, signal_source):
        """智能重连信号源"""
        try:
            source_uid = signal_source.source_uid if hasattr(signal_source, 'source_uid') else signal_source.get('source_uid', 'unknown')
            logger.info(f"🔄 开始智能重连信号源: {source_uid}")
            
            # 检查重连保护（使用统一连接管理器）
            client_key = f"signal_{source_uid}"
            if self.connection_manager._is_reconnect_protected(client_key):
                protection_info = self.connection_manager._reconnect_protection.get(client_key, {})
                attempt_count = protection_info.get('attempt_count', 0)
                logger.warning(f"⚠️ 信号源 {source_uid} 处于重连保护期，已尝试 {attempt_count} 次重连，跳过本次重连")
                await self._send_signal_source_connection_alert(signal_source, f"重连保护期，已尝试 {attempt_count} 次重连")
                return False
            
            # 记录重连尝试（使用统一连接管理器）
            self.connection_manager._record_reconnect_attempt(client_key)
            
            # 1. 关闭旧连接
            logger.info(f"🔄 步骤1: 关闭信号源 {source_uid} 旧连接...")
            if hasattr(signal_source, 'ws_client'):
                old_client = signal_source.ws_client
                try:
                    # 检查旧连接状态
                    if hasattr(old_client, 'ws') and old_client.ws:
                        ws_closed = getattr(old_client.ws, 'closed', False)
                        logger.info(f"🔄 旧连接WebSocket状态: {'已关闭' if ws_closed else '已连接'}")
                    
                    # 检查旧连接的订阅
                    if hasattr(old_client, '_subscriptions'):
                        old_subs = list(old_client._subscriptions.keys()) if old_client._subscriptions else []
                        logger.info(f"🔄 旧连接订阅数量: {len(old_subs)}")
                        if old_subs:
                            logger.info(f"🔄 旧连接订阅列表: {old_subs}")
                    
                    await old_client.close()
                    logger.info(f"✅ 信号源 {source_uid} 旧连接已关闭")
                except Exception as e:
                    logger.warning(f"⚠️ 关闭旧连接时出错: {e}")
            
            # 2. 等待连接完全关闭
            logger.info(f"🔄 步骤2: 等待连接完全关闭...")
            await asyncio.sleep(2)
            
            # 3. 创建新连接
            logger.info(f"🔄 步骤3: 创建信号源 {source_uid} 新连接...")
            new_client = await self.connection_manager.reconnect_client(
                client_type="signal",
                client_id=source_uid,
                is_demo=signal_source.is_demo if hasattr(signal_source, 'is_demo') else False,
                api_key=signal_source.api_key,
                api_secret=signal_source.api_secret,
                passphrase=signal_source.passphrase
            )
            if new_client:
                signal_source.ws_client = new_client
                
                # 4. 设置连接开始时间
                logger.info(f"🔄 步骤4: 设置新连接参数...")
                new_client.connection_start_time = time.time()
                new_client.last_activity = time.time()
                
                # 5. 验证新连接
                logger.info(f"🔄 步骤5: 验证新连接健康状态...")
                if not await self._verify_websocket_connection(new_client):
                    logger.error(f"❌ 信号源 {source_uid} 新连接验证失败")
                    return False
                logger.info(f"✅ 信号源 {source_uid} 新连接验证成功")
                
                # 6. 重新订阅数据
                logger.info(f"🔄 步骤6: 重新订阅信号源 {source_uid} 数据...")
                resubscribe_success = await self._resubscribe_signal_source_data(signal_source)
                if not resubscribe_success:
                    logger.error(f"❌ 信号源 {source_uid} 重新订阅失败")
                    return False
                logger.info(f"✅ 信号源 {source_uid} 重新订阅成功")
                
                # 7. 验证订阅是否成功
                logger.info(f"🔄 步骤7: 等待订阅生效...")
                await asyncio.sleep(3)  # 等待3秒让订阅生效
                
                # 8. 最终验证
                logger.info(f"🔄 步骤8: 最终验证重连结果...")
                
                # 检查连接状态
                final_health_check = await self._verify_websocket_connection(new_client)
                logger.info(f"🔄 最终健康检查: {'通过' if final_health_check else '失败'}")
                
                # 检查订阅状态
                if hasattr(new_client, '_subscriptions'):
                    final_subs = list(new_client._subscriptions.keys()) if new_client._subscriptions else []
                    logger.info(f"🔄 最终订阅数量: {len(final_subs)}")
                    if final_subs:
                        logger.info(f"🔄 最终订阅列表: {final_subs}")
                    else:
                        logger.warning(f"⚠️ 重连后没有订阅，可能有问题")
                
                # 检查健康评分
                if hasattr(new_client, 'health_monitor') and new_client.health_monitor:
                    final_health_score = new_client.health_monitor.health_score
                    logger.info(f"🔄 最终健康评分: {final_health_score}")
                    if final_health_score > 50:
                        logger.info(f"✅ 信号源 {source_uid} 重连成功，健康评分恢复正常")
                    else:
                        logger.warning(f"⚠️ 信号源 {source_uid} 重连后健康评分仍较低: {final_health_score}")
                
                logger.info(f"🎉 信号源 {source_uid} 智能重连完成！")
                
                # 重连成功，重置保护状态（使用统一连接管理器）
                self.connection_manager._reset_reconnect_protection(client_key)
                
                # 重连成功后，立即检查仓位同步
                logger.info(f"[仓位同步] 重连成功后检查仓位同步: {source_uid}")
                await self._check_signal_source_position_sync(signal_source)
                
                return True
            else:
                logger.error(f"❌ 信号源 {source_uid} 无法创建新客户端")
                return False
            
        except Exception as e:
            logger.error(f"❌ 智能重连信号源 {source_uid} 失败: {e}")
            return False

    # ==================== 连接验证系统 ====================
    
    async def _verify_websocket_connection(self, client):
        """验证WebSocket连接是否真的有效"""
        try:
            # 检查连接状态
            if not hasattr(client, 'is_connected') or not client.is_connected():
                logger.debug("WebSocket连接状态检查失败")
                return False
            
            # 🚀 检查心跳状态（新增）
            current_time = time.time()
            if hasattr(client, '_last_pong_time') and hasattr(client, '_ping_failures'):
                last_pong_time = getattr(client, '_last_pong_time', 0)
                ping_failures = getattr(client, '_ping_failures', 0)
                
                # 如果超过120秒没有收到pong，或者连续ping失败超过5次，认为连接有问题
                if (current_time - last_pong_time > 120) or (ping_failures > 5):
                    logger.warning(f"WebSocket心跳异常: last_pong={current_time - last_pong_time:.1f}秒前, ping_failures={ping_failures}")
                return False
            
            # 检查最后活动时间
            if hasattr(client, 'last_activity'):
                time_since_activity = time.time() - client.last_activity
                if time_since_activity > 300:  # 5分钟无活动
                    logger.warning(f"连接 {time_since_activity/60:.1f} 分钟无活动")
                    return False
            
            # 尝试发送ping测试
            try:
                if hasattr(client, 'ping'):
                    await asyncio.wait_for(client.ping(), timeout=5.0)
                    # 更新最后活动时间
                    client.last_activity = time.time()
                    return True
            except asyncio.TimeoutError:
                logger.warning("WebSocket ping超时")
                return False
            except Exception as e:
                logger.warning(f"WebSocket ping失败: {e}")
                return False
            
            return True
            
        except Exception as e:
            logger.error(f"验证WebSocket连接失败: {e}")
            return False

    async def _verify_customer_subscriptions(self, customer):
        """验证客户订阅是否成功"""
        try:
            customer_uid = customer.customer_uid if hasattr(customer, 'customer_uid') else customer.get('customer_uid', 'unknown')
            
            # 等待一段时间看是否收到价格更新
            initial_cache_size = len(TICKER_CACHE) if 'TICKER_CACHE' in globals() else 0
            
            # 等待15秒
            await asyncio.sleep(15)
            
            # 检查是否有新的价格更新
            current_cache_size = len(TICKER_CACHE) if 'TICKER_CACHE' in globals() else 0
            if current_cache_size > initial_cache_size:
                logger.info(f"客户 {customer_uid} 订阅验证成功，收到价格更新")
                return True
            else:
                logger.warning(f"客户 {customer_uid} 订阅验证失败，未收到价格更新")
                return False
            
        except Exception as e:
            logger.error(f"验证客户订阅失败: {e}")
            return False

    async def _verify_signal_source_subscriptions(self, signal_source):
        """验证信号源订阅是否成功"""
        try:
            source_uid = signal_source.source_uid if hasattr(signal_source, 'source_uid') else signal_source.get('source_uid', 'unknown')
            
            # 这里可以添加信号源订阅验证逻辑
            # 比如检查是否收到了订单更新等
            
            logger.info(f"信号源 {source_uid} 订阅验证完成")
            return True
            
        except Exception as e:
            logger.error(f"验证信号源订阅失败: {e}")
            return False


    # ==================== 止损监控方法 ====================
    
    async def start_stop_loss_monitor(self):
        """启动止损监控"""
        try:
            # 从配置文件读取止损监控开关
            from config import get_stop_loss_config
            stop_loss_config = get_stop_loss_config()
            stop_loss_enabled = stop_loss_config.get('enabled', False)
            
            if not stop_loss_enabled:
                logger.info("[止损监控] 止损监控已通过配置文件禁用")
                return None
            
            logger.info("启动止损监控...")
            
            async def stop_loss_loop():
                while True:
                    try:
                        await self.check_all_stop_loss()
                        await asyncio.sleep(60)  # 每分钟检查一次
                    except Exception as e:
                        logger.error(f"止损监控循环出错: {e}")
                        await asyncio.sleep(60)
            
            # 创建监控任务
            monitor_task = asyncio.create_task(stop_loss_loop())
            logger.info("止损监控已启动")
            
            return monitor_task
            
        except Exception as e:
            logger.error(f"启动止损监控失败: {e}")
            return None

    async def start_no_trading_monitor(self):
        """启动长时间无开仓监控"""
        try:
            logger.info("启动长时间无开仓监控...")
            
            async def no_trading_monitor_loop():
                while True:
                    try:
                        await self.check_no_trading_alert()
                        await asyncio.sleep(3600)  # 每小时检查一次
                    except Exception as e:
                        logger.error(f"长时间无开仓监控出错: {e}")
                        await asyncio.sleep(3600)
            
            # 创建监控任务
            monitor_task = asyncio.create_task(no_trading_monitor_loop())
            logger.info("长时间无开仓监控已启动")
            
            return monitor_task
            
        except Exception as e:
            logger.error(f"启动长时间无开仓监控失败: {e}")
            return None

    async def check_no_trading_alert(self):
        """检查长时间无开仓告警"""
        try:
            # 这里实现您的长时间无开仓检查逻辑
            # 暂时返回空实现
            logger.debug("检查长时间无开仓告警...")
            
        except Exception as e:
            logger.error(f"检查长时间无开仓告警失败: {e}")

    async def check_all_stop_loss(self):
        """检查所有止损条件"""
        try:
            logger.info("[止损监控] 开始检查所有止损条件...")
            
            # 获取当前环境
            is_demo = get_global_is_demo()
            env_name = "模拟盘" if is_demo else "实盘"
            logger.info(f"[止损监控] 当前环境: {env_name}")
            
            # 检查客户止损
            await self._check_customer_stop_loss(is_demo)
            
            # 检查信号源止损
            await self._check_signal_source_stop_loss(is_demo)
            
            logger.info("[止损监控] 止损检查完成")
            
        except Exception as e:
            logger.error(f"检查所有止损条件失败: {e}")
            import traceback
            traceback.print_exc()

    async def _check_customer_stop_loss(self, is_demo):
        """检查客户止损条件"""
        try:
            logger.info("[客户止损] 开始检查客户止损条件...")
            
            # 获取所有启用的客户
            customers = self.db_pool.query(
                "SELECT * FROM customers WHERE enabled=1 AND is_demo=%s",
                (is_demo,)
            )
            
            if not customers:
                logger.info("[客户止损] 没有找到启用的客户")
                return
            
            logger.info(f"[客户止损] 找到 {len(customers)} 个客户，开始检查...")
            
            for customer in customers:
                try:
                    await self._check_single_customer_stop_loss(customer)
                except Exception as e:
                    # 使用辅助函数安全获取客户字段
                    customer_uid = self._get_customer_field(customer, 'customer_uid', 'unknown')
                    logger.error(f"[客户止损] 检查客户 {customer_uid} 止损失败: {e}")
                    continue
                    
        except Exception as e:
            logger.error(f"[客户止损] 检查客户止损条件失败: {e}")

    async def _check_single_customer_stop_loss(self, customer):
        """检查单个客户止损条件"""
        try:
            # 使用辅助函数安全获取客户字段
            customer_uid = self._get_customer_field(customer, 'customer_uid')
            init_assets = float(self._get_customer_field(customer, 'init_asset', 0))
            stop_loss_percent = float(self._get_customer_field(customer, 'stop_loss_percent', 10.0))
            
            if init_assets <= 0:
                logger.warning(f"[客户止损] 客户 {customer_uid} 初始资产为0，跳过检查")
                return
            
            # 获取客户实际总资产（用于止损检查）
            actual_total_assets = await self._get_customer_actual_total_assets(customer_uid)
            if actual_total_assets is None:
                logger.warning(f"[客户止损] 无法获取客户 {customer_uid} 实际总资产")
                return
            
            # 计算止损线 - 基于初始资产计算止损线，与当前实际总资产比较
            # 止损线 = 初始资产 * (1 - 止损比例)
            stop_loss_line = init_assets * (1 - stop_loss_percent / 100)
            
            # logger.info(f"[客户止损] 客户 {customer_uid}: 初始资产={init_assets:.2f}, 实际总资产={actual_total_assets:.2f}, 止损线={stop_loss_line:.2f}, 止损比例={stop_loss_percent}%")
            
            # 检查是否触发止损
            if actual_total_assets < stop_loss_line:
                logger.warning(f"[客户止损] 客户 {customer_uid} 触发止损！实际总资产 {actual_total_assets:.2f} < 止损线 {stop_loss_line:.2f}")
                
                # 执行客户止损
                await self._execute_customer_stop_loss(customer, actual_total_assets, init_assets)
            
            else:
                logger.debug(f"[客户止损] 客户 {customer_uid} 未触发止损")
                
        except Exception as e:
            logger.error(f"[客户止损] 检查单个客户止损失败: {e}")

    async def _execute_customer_stop_loss(self, customer, current_assets, old_init_assets):
        """执行客户止损"""
        try:
            # 使用辅助函数安全获取客户字段
            customer_uid = self._get_customer_field(customer, 'customer_uid')
            logger.info(f"[客户止损] 开始执行客户 {customer_uid} 止损...")
            
            # 1. 平掉所有open持仓
            await self._close_all_customer_positions(customer_uid)
            
            # 2. 更新客户资产记录
            await self._update_customer_assets_after_stop_loss(customer_uid, old_init_assets, current_assets)
            
            # 3. 发送止损通知
            await self._send_customer_stop_loss_notification(customer, old_init_assets, current_assets)
            
            logger.info(f"[客户止损] 客户 {customer_uid} 止损执行完成")
            
        except Exception as e:
            logger.error(f"[客户止损] 执行客户止损失败: {e}")

    async def _check_signal_source_stop_loss(self, is_demo):
        """检查信号源止损条件"""
        try:
            logger.info("[信号源止损] 开始检查信号源止损条件...")
            
            # 获取所有启用的信号源
            signal_sources = self.db_pool.query(
                "SELECT * FROM signal_sources WHERE enabled=1 AND is_demo=%s",
                (is_demo,)
            )
            
            if not signal_sources:
                logger.info("[信号源止损] 没有找到启用的信号源")
                return
            
            logger.info(f"[信号源止损] 找到 {len(signal_sources)} 个信号源，开始检查...")
            
            for signal_source in signal_sources:
                try:
                    await self._check_single_signal_source_stop_loss(signal_source)
                except Exception as e:
                    source_uid = signal_source.get('source_uid', 'unknown')
                    logger.error(f"[信号源止损] 检查信号源 {source_uid} 止损失败: {e}")
                    continue
                    
        except Exception as e:
            logger.error(f"[信号源止损] 检查信号源止损条件失败: {e}")

    async def _check_single_signal_source_stop_loss(self, signal_source):
        """检查单个信号源止损条件"""
        try:
            source_uid = signal_source.get('source_uid')
            init_assets = float(signal_source.get('init_assets', 0))
            stop_loss_percent = float(signal_source.get('stop_loss_percent', 15.0))
            
            if init_assets <= 0:
                logger.warning(f"[信号源止损] 信号源 {source_uid} 初始资产为0，跳过检查")
                return
            
            # 获取信号源当前资产
            current_assets = await self._get_signal_source_current_assets(source_uid)
            if current_assets is None:
                logger.warning(f"[信号源止损] 无法获取信号源 {source_uid} 当前资产")
                return
            
            # 计算止损线 - 基于初始资产计算止损线，与当前实际资产比较
            # 止损线 = 初始资产 * (1 - 止损比例)
            stop_loss_line = init_assets * (1 - stop_loss_percent / 100)
            
            # logger.info(f"[信号源止损] 信号源 {source_uid}: 初始资产={init_assets:.2f}, 当前资产={current_assets:.2f}, 止损线={stop_loss_line:.2f}, 止损比例={stop_loss_percent}%")
            
            # 检查是否触发止损
            if current_assets < stop_loss_line:
                logger.warning(f"[信号源止损] 信号源 {source_uid} 触发止损！当前资产 {current_assets:.2f} < 止损线 {stop_loss_line:.2f}")
                
                # 执行信号源止损
                await self._execute_signal_source_stop_loss(signal_source, current_assets, init_assets)
            else:
                logger.debug(f"[信号源止损] 信号源 {source_uid} 未触发止损")
                
        except Exception as e:
            logger.error(f"[信号源止损] 检查单个信号源止损失败: {e}")

    async def _execute_signal_source_stop_loss(self, signal_source, current_assets, old_init_assets):
        """执行信号源止损"""
        try:
            source_uid = signal_source.get('source_uid')
            logger.info(f"[信号源止损] 开始执行信号源 {source_uid} 止损...")
            
            # 1. 平掉信号源所有open持仓
            await self._close_all_signal_source_positions(source_uid)
            
            # 2. 平掉所有跟随该信号源的客户持仓
            await self._close_all_following_customer_positions(source_uid)
            
            # 3. 更新信号源资产记录
            await self._update_signal_source_assets_after_stop_loss(source_uid, old_init_assets, current_assets)
            
            # 4. 发送止损通知
            await self._send_signal_source_stop_loss_notification(signal_source, old_init_assets, current_assets)
            
            logger.info(f"[信号源止损] 信号源 {source_uid} 止损执行完成")
            
        except Exception as e:
            logger.error(f"[信号源止损] 执行信号源止损失败: {e}")

    async def _get_customer_current_assets(self, customer_uid):
        """获取客户当前资产（用于跟单计算）- 应用固定开仓资产逻辑"""
        try:
            logger.debug(f"[客户止损] 获取客户 {customer_uid} 当前资产...")
            
            # 从数据库读取客户当前资产
            is_demo = get_global_is_demo()
            customer_data = self.db_pool.query(
                "SELECT total_asset, init_asset, trading_asset FROM customers WHERE customer_uid=%s AND is_demo=%s",
                (customer_uid, is_demo)
            )
            
            if customer_data:
                customer = customer_data[0]
                # 使用辅助函数安全获取客户字段
                trading_asset = self._get_customer_field(customer, 'trading_asset')
                total_asset = self._get_customer_field(customer, 'total_asset')
                init_asset = self._get_customer_field(customer, 'init_asset')
                
                # 固定开仓资产逻辑：
                # 1. 优先使用 trading_asset（开仓资产）
                # 2. 如果没有设置开仓资产，使用初始资产
                # 3. 如果当前总资产 > 开仓资产（盈利），使用当前总资产
                # 4. 否则使用开仓资产（亏损时保持不变）
                
                if trading_asset is not None and float(trading_asset) > 0:
                    # 有开仓资产，检查是否需要更新
                    total_asset_float = float(total_asset) if total_asset else 0
                    trading_asset_float = float(trading_asset)
                    
                    if total_asset_float > trading_asset_float:
                        # 盈利时使用当前总资产
                        current_assets = total_asset_float
                        asset_type = "当前总资产(盈利)"
                    else:
                        # 亏损或持平时使用开仓资产
                        current_assets = trading_asset_float
                        asset_type = "开仓资产(固定)"
                else:
                    # 没有开仓资产，使用初始资产
                    init_asset_float = float(init_asset) if init_asset else 0
                    total_asset_float = float(total_asset) if total_asset else 0
                    current_assets = max(init_asset_float, total_asset_float)
                    asset_type = "最大资产值(无开仓资产)"
                
                if current_assets is not None and float(current_assets) > 0:
                    logger.debug(f"[客户止损] 客户 {customer_uid} 当前资产: {current_assets} (使用{asset_type})")
                    return float(current_assets)
                else:
                    logger.warning(f"[客户止损] 客户 {customer_uid} 资产数据无效: trading_asset={trading_asset}, total_asset={total_asset}, init_asset={init_asset}")
                    return None
            else:
                logger.warning(f"[客户止损] 未找到客户 {customer_uid} 数据")
                return None
            
        except Exception as e:
            logger.error(f"[客户止损] 获取客户当前资产失败: {e}")
            return None

    async def _get_customer_actual_total_assets(self, customer_uid):
        """获取客户实际总资产（用于止损检查）"""
        try:
            logger.debug(f"[客户止损] 获取客户 {customer_uid} 实际总资产...")
            
            # 从数据库读取客户实际总资产
            is_demo = get_global_is_demo()
            customer_data = self.db_pool.query(
                "SELECT total_asset FROM customers WHERE customer_uid=%s AND is_demo=%s",
                (customer_uid, is_demo)
            )
            
            if customer_data:
                customer = customer_data[0]
                total_asset = customer.get('total_asset')
                
                if total_asset is not None and float(total_asset) > 0:
                    logger.debug(f"[客户止损] 客户 {customer_uid} 实际总资产: {total_asset}")
                    return float(total_asset)
                else:
                    logger.warning(f"[客户止损] 客户 {customer_uid} 实际总资产无效: total_asset={total_asset}")
                    return None
            else:
                logger.warning(f"[客户止损] 未找到客户 {customer_uid} 数据")
                return None
            
        except Exception as e:
            logger.error(f"[客户止损] 获取客户实际总资产失败: {e}")
            return None

    async def _get_signal_source_current_assets(self, source_uid):
        """获取信号源当前资产"""
        try:
            logger.debug(f"[信号源止损] 获取信号源 {source_uid} 当前资产...")
            
            # 从数据库读取信号源当前资产
            is_demo = get_global_is_demo()
            signal_data = self.db_pool.query(
                "SELECT init_assets FROM signal_sources WHERE source_uid=%s AND is_demo=%s",
                (source_uid, is_demo)
            )
            
            if signal_data:
                signal = signal_data[0]
                # 从信号源资产快照表获取最新资产
                asset_data = self.db_pool.query(
                    "SELECT asset FROM signal_account_assets WHERE signal_source_uid=%s ORDER BY snapshot_time DESC LIMIT 1",
                    (source_uid,)
                )
                
                if asset_data:
                    current_assets = asset_data[0].get('asset')
                    if current_assets is not None and float(current_assets) > 0:
                        logger.debug(f"[信号源止损] 信号源 {source_uid} 当前资产: {current_assets}")
                        return float(current_assets)
                
                # 如果没有快照数据，使用初始资产
                init_assets = signal.get('init_assets')
                if init_assets is not None and float(init_assets) > 0:
                    logger.debug(f"[信号源止损] 信号源 {source_uid} 使用初始资产: {init_assets}")
                    return float(init_assets)
                
                logger.warning(f"[信号源止损] 信号源 {source_uid} 资产数据无效: init_assets={init_assets}")
                return None
            else:
                logger.warning(f"[信号源止损] 未找到信号源 {source_uid} 数据")
                return None
            
        except Exception as e:
            logger.error(f"[信号源止损] 获取信号源当前资产失败: {e}")
            return None

    async def _close_all_customer_positions(self, customer_uid):
        """平掉客户所有持仓"""
        try:
            logger.info(f"[客户止损] 开始平掉客户 {customer_uid} 所有持仓...")
            
            # 获取客户所有open持仓
            open_positions = self.db_pool.query(
                "SELECT * FROM customer_trades WHERE customer_uid=%s AND status='open'",
                (customer_uid,)
            )
            
            if not open_positions:
                logger.info(f"[客户止损] 客户 {customer_uid} 没有open持仓")
                return
            
            logger.info(f"[客户止损] 客户 {customer_uid} 有 {len(open_positions)} 个open持仓需要平仓")
            
            # 获取客户信息
            is_demo = get_global_is_demo()
            customer_data = self.db_pool.query(
                "SELECT * FROM customers WHERE customer_uid=%s AND is_demo=%s",
                (customer_uid, is_demo)
            )
            
            if not customer_data:
                logger.error(f"[客户止损] 未找到客户 {customer_uid} 信息")
                return
            
            customer = customer_data[0]
            
            # 为每个持仓执行平仓
            for position in open_positions:
                try:
                    trade_uid = position.get('trade_uid')
                    symbol = position.get('symbol')
                    pos_side = position.get('pos_side')
                    volume_contract = position.get('volume_contract', 0)
                    
                    logger.info(f"[客户止损] 开始平仓: trade_uid={trade_uid}, symbol={symbol}, pos_side={pos_side}, volume_contract={volume_contract}")
                    
                    # 确定平仓方向
                    if pos_side == 'long':
                        close_side = 'sell'
                    elif pos_side == 'short':
                        close_side = 'buy'
                    else:
                        logger.error(f"[客户止损] 未知持仓方向: {pos_side}")
                        continue
                    
                    # 执行平仓下单
                    close_order = await self._place_customer_close_order(
                        customer, symbol, close_side, pos_side, volume_contract, trade_uid
                    )
                    
                    if close_order and close_order.get('code') == '0':
                        logger.info(f"[客户止损] 平仓下单成功: trade_uid={trade_uid}, order_id={close_order.get('data', [{}])[0].get('ordId')}")
                        
                        # 更新交易记录状态
                        self.db_pool.execute(
                            "UPDATE customer_trades SET status='closed' WHERE trade_uid=%s",
                            (trade_uid,)
                        )
                    else:
                        # 检查是否是"没有仓位"的错误
                        error_code = None
                        error_msg = ""
                        if close_order and close_order.get('data'):
                            for data_item in close_order.get('data', []):
                                if data_item.get('sCode'):
                                    error_code = data_item.get('sCode')
                                    error_msg = data_item.get('sMsg', '')
                                    break
                        
                        # 如果是"没有仓位"的错误，直接标记为已平仓
                        if error_code == '51169' and "don't have any positions" in error_msg:
                            logger.info(f"[客户止损] 持仓已不存在，直接标记为已平仓: trade_uid={trade_uid}, symbol={symbol}")
                            
                            # 更新交易记录状态为已平仓
                            self.db_pool.execute(
                                "UPDATE customer_trades SET status='closed' WHERE trade_uid=%s and symbol=%s",
                                (trade_uid,symbol)
                            )
                        else:
                            logger.error(f"[客户止损] 平仓下单失败: trade_uid={trade_uid}, response={close_order}")
                        
                except Exception as e:
                    logger.error(f"[客户止损] 平仓单个持仓失败: trade_uid={position.get('trade_uid')}, error={e}")
                    continue
            
            logger.info(f"[客户止损] 客户 {customer_uid} 所有持仓平仓下单完成")
            
        except Exception as e:
            logger.error(f"[客户止损] 平掉客户持仓失败: {e}")

    async def _close_all_signal_source_positions(self, source_uid):
        """平掉信号源所有持仓"""
        try:
            logger.info(f"[信号源止损] 开始平掉信号源 {source_uid} 所有持仓...")
            
            # 获取信号源所有open持仓
            open_positions = self.db_pool.query(
                "SELECT * FROM signal_account_trades WHERE signal_source_uid=%s AND status='open'",
                (source_uid,)
            )
            
            if not open_positions:
                logger.info(f"[信号源止损] 信号源 {source_uid} 没有open持仓")
                return
            
            logger.info(f"[信号源止损] 信号源 {source_uid} 有 {len(open_positions)} 个open持仓需要平仓")
            
            # 获取信号源信息
            is_demo = get_global_is_demo()
            signal_data = self.db_pool.query(
                "SELECT * FROM signal_sources WHERE source_uid=%s AND is_demo=%s",
                (source_uid, is_demo)
            )
            
            if not signal_data:
                logger.error(f"[信号源止损] 未找到信号源 {source_uid} 信息")
                return
            
            signal_source = signal_data[0]
            
            # 为每个持仓执行平仓
            for position in open_positions:
                try:
                    trade_uid = position.get('trade_uid')
                    symbol = position.get('symbol')
                    pos_side = position.get('pos_side')
                    volume_contract = position.get('volume_contract', 0)
                    
                    logger.info(f"[信号源止损] 开始平仓: trade_uid={trade_uid}, symbol={symbol}, pos_side={pos_side}, volume_contract={volume_contract}")
                    
                    # 确定平仓方向
                    if pos_side == 'long':
                        close_side = 'sell'
                    elif pos_side == 'short':
                        close_side = 'buy'
                    else:
                        logger.error(f"[信号源止损] 未知持仓方向: {pos_side}")
                        continue
                    
                    # 执行平仓下单
                    close_order = await self._place_signal_source_close_order(
                        signal_source, symbol, close_side, pos_side, volume_contract, trade_uid
                    )
                    
                    if close_order and close_order.get('code') == '0':
                        logger.info(f"[信号源止损] 平仓下单成功: trade_uid={trade_uid}, order_id={close_order.get('data', [{}])[0].get('ordId')}")
                        
                        # 更新交易记录状态
                        self.db_pool.execute(
                            "UPDATE signal_account_trades SET status='closed' WHERE trade_uid=%s",
                            (trade_uid,)
                        )
                    else:
                        # 检查是否是"没有仓位"的错误
                        error_code = None
                        error_msg = ""
                        if close_order and close_order.get('data'):
                            for data_item in close_order.get('data', []):
                                if data_item.get('sCode'):
                                    error_code = data_item.get('sCode')
                                    error_msg = data_item.get('sMsg', '')
                                    break
                        
                        # 如果是"没有仓位"的错误，直接标记为已平仓
                        if error_code == '51169' and "don't have any positions" in error_msg:
                            logger.info(f"[信号源止损] 持仓已不存在，直接标记为已平仓: trade_uid={trade_uid}, symbol={symbol}")
                            
                            # 更新交易记录状态为已平仓
                            self.db_pool.execute(
                                "UPDATE signal_account_trades SET status='closed' WHERE trade_uid=%s and symbol=%s",
                                (trade_uid,symbol)
                            )
                        else:
                            logger.error(f"[信号源止损] 平仓下单失败: trade_uid={trade_uid}, response={close_order}")
                        
                except Exception as e:
                    logger.error(f"[信号源止损] 平仓单个持仓失败: trade_uid={position.get('trade_uid')}, error={e}")
                    continue
            
            logger.info(f"[信号源止损] 信号源 {source_uid} 所有持仓平仓下单完成")
            
        except Exception as e:
            logger.error(f"[信号源止损] 平掉信号源持仓失败: {e}")



    async def _close_all_following_customer_positions(self, source_uid):
        """平掉所有跟随该信号源的客户持仓"""
        try:
            logger.info(f"[信号源止损] 开始平掉所有跟随信号源 {source_uid} 的客户持仓...")
            
            # 获取所有跟随该信号源的客户持仓
            following_positions = self.db_pool.query(
                """
                SELECT distinct ct.* FROM customer_trades ct 
                JOIN rules r ON ct.rule_uid = r.rule_uid 
                WHERE r.rule_uid = %s AND ct.status = 'open'
                """,
                (source_uid,)
            )
            
            if not following_positions:
                logger.info(f"[信号源止损] 没有客户跟随信号源 {source_uid}")
                return
            
            logger.info(f"[信号源止损] 有 {len(following_positions)} 个客户持仓需要平仓")
            
            # 按客户分组处理
            customer_positions = {}
            for position in following_positions:
                customer_uid = position.get('customer_uid')
                if customer_uid not in customer_positions:
                    customer_positions[customer_uid] = []
                customer_positions[customer_uid].append(position)
            
            # 为每个客户平仓
            for customer_uid, positions in customer_positions.items():
                try:
                    logger.info(f"[信号源止损] 开始平仓客户 {customer_uid} 的 {len(positions)} 个持仓")
                    
                    # 获取客户信息
                    is_demo = get_global_is_demo()
                    customer_data = self.db_pool.query(
                        "SELECT * FROM customers WHERE customer_uid=%s AND is_demo=%s",
                        (customer_uid, is_demo)
                    )
                    
                    if not customer_data:
                        logger.error(f"[信号源止损] 未找到客户 {customer_uid} 信息")
                        continue
                    
                    customer = customer_data[0]
                    
                    # 平仓该客户的所有持仓
                    for position in positions:
                        try:
                            trade_uid = position.get('trade_uid')
                            symbol = position.get('symbol')
                            pos_side = position.get('pos_side')
                            volume_contract = position.get('volume_contract', 0)
                            
                            logger.info(f"[信号源止损] 平仓客户持仓: customer_uid={customer_uid}, trade_uid={trade_uid}, symbol={symbol}, pos_side={pos_side}")
            
                            # 确定平仓方向
                            if pos_side == 'long':
                                close_side = 'sell'
                            elif pos_side == 'short':
                                close_side = 'buy'
                            else:
                                logger.error(f"[信号源止损] 未知持仓方向: {pos_side}")
                                continue
                            
                            # 执行平仓下单
                            close_order = await self._place_customer_close_order(
                                customer, symbol, close_side, pos_side, volume_contract, trade_uid
                            )
                            
                            if close_order and close_order.get('code') == '0':
                                logger.info(f"[信号源止损] 客户平仓下单成功: customer_uid={customer_uid}, trade_uid={trade_uid}")
                                
                                # 更新交易记录状态
                                self.db_pool.execute(
                                    "UPDATE customer_trades SET status='closed' WHERE trade_uid=%s and symbol=%s",
                                    (trade_uid,symbol)
                                )
                            else:
                                # 检查是否是"没有仓位"的错误
                                error_code = None
                                error_msg = ""
                                if close_order and close_order.get('data'):
                                    for data_item in close_order.get('data', []):
                                        if data_item.get('sCode'):
                                            error_code = data_item.get('sCode')
                                            error_msg = data_item.get('sMsg', '')
                                            break
                                
                                # 如果是"没有仓位"的错误，直接标记为已平仓
                                if error_code == '51169' and "don't have any positions" in error_msg:
                                    logger.info(f"[信号源止损] 客户持仓已不存在，直接标记为已平仓: customer_uid={customer_uid}, trade_uid={trade_uid}, symbol={symbol}")
                                    
                                    # 更新交易记录状态为已平仓
                                    self.db_pool.execute(
                                        "UPDATE customer_trades SET status='closed' WHERE trade_uid=%s",
                                        (trade_uid,)
                                    )
                                else:
                                    logger.error(f"[信号源止损] 客户平仓下单失败: customer_uid={customer_uid}, trade_uid={trade_uid}")
                                
                        except Exception as e:
                            logger.error(f"[信号源止损] 平仓单个客户持仓失败: customer_uid={customer_uid}, trade_uid={position.get('trade_uid')}, error={e}")
                            continue
                    
                    logger.info(f"[信号源止损] 客户 {customer_uid} 所有持仓平仓完成")
                    
                except Exception as e:
                    logger.error(f"[信号源止损] 平仓客户 {customer_uid} 持仓失败: {e}")
                    continue
            
            logger.info(f"[信号源止损] 所有跟随客户持仓平仓完成")
            
        except Exception as e:
            logger.error(f"[信号源止损] 平掉跟随客户持仓失败: {e}")

    async def _update_customer_assets_after_stop_loss(self, customer_uid, old_init_assets, current_assets):
        """止损后更新客户资产记录 - 实现固定开仓资产逻辑"""
        try:
            logger.info(f"[客户止损] 更新客户 {customer_uid} 资产记录...")
            
            # 获取客户当前的开仓资产
            is_demo = get_global_is_demo()
            customer_data = self.db_pool.query(
                "SELECT trading_asset FROM customers WHERE customer_uid=%s AND is_demo=%s",
                (customer_uid, is_demo)
            )
            
            if customer_data:
                current_trading_asset = customer_data[0].get('trading_asset')
                
                # 固定开仓资产逻辑：
                # 1. 如果当前资产 > 开仓资产（盈利），则更新开仓资产为当前资产
                # 2. 如果当前资产 <= 开仓资产（亏损或持平），则保持开仓资产不变
                new_trading_asset = current_trading_asset
                if current_assets > float(current_trading_asset or 0):
                    new_trading_asset = current_assets
                    logger.info(f"[客户止损] 客户 {customer_uid} 盈利，开仓资产从 {current_trading_asset} 更新为 {new_trading_asset}")
                else:
                    logger.info(f"[客户止损] 客户 {customer_uid} 亏损或持平，开仓资产保持 {current_trading_asset} 不变")
            
                # 更新客户资产记录
                self.db_pool.execute(
                    """
                    UPDATE customers 
                    SET recently_assets = %s, 
                        init_asset = %s, 
                                trading_asset = %s,
                        last_stop_loss_time = NOW(), 
                        stop_loss_count = stop_loss_count + 1
                    WHERE customer_uid = %s
                    """,
                            (old_init_assets, current_assets, new_trading_asset, customer_uid)
                )
            
                logger.info(f"[客户止损] 客户 {customer_uid} 资产记录更新完成 - 开仓资产: {new_trading_asset}")
            else:
                logger.warning(f"[客户止损] 未找到客户 {customer_uid} 数据，无法更新开仓资产")
            
        except Exception as e:
            logger.error(f"[客户止损] 更新客户资产记录失败: {e}")

    async def _update_signal_source_assets_after_stop_loss(self, source_uid, old_init_assets, current_assets):
        """止损后更新信号源资产记录 - 实现固定开仓资产逻辑"""
        try:
            logger.info(f"[信号源止损] 更新信号源 {source_uid} 资产记录...")
            
            # 获取信号源当前的开仓资产
            is_demo = get_global_is_demo()
            signal_data = self.db_pool.query(
                "SELECT init_assets FROM signal_sources WHERE source_uid=%s AND is_demo=%s",
                (source_uid, is_demo)
            )
            
            if signal_data:
                current_init_assets = signal_data[0].get('init_assets')
                
                # 固定开仓资产逻辑：
                # 1. 如果当前资产 > 初始资产（盈利），则更新初始资产为当前资产
                # 2. 如果当前资产 <= 初始资产（亏损或持平），则保持初始资产不变
                new_init_assets = current_init_assets
                if current_assets > float(current_init_assets or 0):
                    new_init_assets = current_assets
                    logger.info(f"[信号源止损] 信号源 {source_uid} 盈利，初始资产从 {current_init_assets} 更新为 {new_init_assets}")
                else:
                    logger.info(f"[信号源止损] 信号源 {source_uid} 亏损或持平，初始资产保持 {current_init_assets} 不变")
            
                # 更新信号源资产记录
                self.db_pool.execute(
                    """
                    UPDATE signal_sources 
                    SET recently_assets = %s, 
                                init_assets = %s, 
                        last_stop_loss_time = NOW(), 
                        stop_loss_count = stop_loss_count + 1
                    WHERE source_uid = %s
                    """,
                            (old_init_assets, new_init_assets, source_uid)
                )
                
                # 同步更新 signal_account_assets 表
                await self._sync_signal_source_assets_after_stop_loss(source_uid, current_assets)
                
                logger.info(f"[信号源止损] 信号源 {source_uid} 资产记录更新完成 - 初始资产: {new_init_assets}")
            else:
                logger.warning(f"[信号源止损] 未找到信号源 {source_uid} 数据，无法更新初始资产")
        
        except Exception as e:
            logger.error(f"[信号源止损] 更新信号源资产记录失败: {e}")

    async def _sync_signal_source_assets_after_stop_loss(self, source_uid, current_assets):
        """止损后同步更新信号源实时资产信息"""
        try:
            logger.info(f"[资产同步] 止损后开始同步信号源 {source_uid} 实时资产信息")
            
            # 1. 获取信号源信息
            is_demo = get_global_is_demo()
            signal_data = self.db_pool.query(
                "SELECT api_key, api_secret as secret_key, passphrase FROM signal_sources WHERE source_uid=%s AND is_demo=%s",
                (source_uid, is_demo)
            )
            
            if not signal_data:
                logger.warning(f"[资产同步] 未找到信号源 {source_uid} 的API信息")
                return
            
            signal_info = signal_data[0]
            api_key = signal_info.get('api_key')
            secret_key = signal_info.get('secret_key')
            passphrase = signal_info.get('passphrase')
            
            if not all([api_key, secret_key, passphrase]):
                logger.error(f"[资产同步] 信号源 {source_uid} API凭证不完整")
                return
            
            # 2. 创建REST客户端查询实时资产
            rest_client = OKXRESTClient(api_key, secret_key, passphrase, is_demo)
            response = await rest_client.get_account_info()
            
            if response and response.get('code') == '0':
                data = response.get('data', [])
                
                # 3. 更新 signal_account_assets 表（只处理USDT总资产）
                usdt_total = 0
                for asset in data:
                    details = asset.get('details', [])
                    # 遍历每个币种的详情
                    for detail in details:
                        ccy = detail.get('ccy')
                        # 使用 availBal（可用余额）或 cashBal（现金余额）
                        bal = detail.get('availBal', '0') or detail.get('cashBal', '0')
                        
                        logger.debug(f"[资产同步] 处理资产: 币种={ccy}, 可用余额={detail.get('availBal', '0')}, 现金余额={detail.get('cashBal', '0')}")
                        
                        # 累加USDT资产
                        if ccy == 'USDT' and bal:
                            usdt_total += float(bal)
                
                if usdt_total > 0:
                    # 更新或插入USDT总资产记录
                    asset_uid = f"asset_{uuid.uuid4().hex[:12]}"
            
                    # 更新或插入USDT总资产记录
                    self.db_pool.execute(
                        "INSERT INTO signal_account_assets (asset_uid, signal_source_uid, asset) "
                        "VALUES (%s, %s, %s) "
                        "ON DUPLICATE KEY UPDATE "
                        "asset_uid = VALUES(asset_uid), "
                        "asset = VALUES(asset), "
                        "snapshot_time = NOW()",
                        (asset_uid, source_uid, usdt_total)
                    )
                    logger.info(f"[资产同步] 止损后信号源 {source_uid} USDT总资产已更新: {usdt_total}")
                else:
                    logger.warning(f"[资产同步] 止损后信号源 {source_uid} 未找到USDT资产信息")
            else:
                logger.error(f"[资产同步] 止损后查询信号源 {source_uid} 资产失败: {response}")
                
        except Exception as e:
            logger.error(f"[资产同步] 止损后同步信号源 {source_uid} 资产信息失败: {e}")

    async def _send_customer_stop_loss_notification(self, customer, old_init_assets, current_assets):
        """发送客户止损通知"""
        try:
            customer_uid = customer.get('customer_uid')
            customer_name = customer.get('customer_name', customer_uid)
            
            notification_info = {
                "title": "客户止损通知",
                "level": "WARNING",
                "message": f"客户 {customer_name} 触发止损",
                "account": f"客户UID: {customer_uid}",
                "strategy": "止损监控",
                "symbol": f"原资产: {old_init_assets:.2f} → 当前资产: {current_assets:.2f}",
                "suggestion": "请检查客户账户状态和交易策略"
            }
            
            # 发送钉钉通知
            if hasattr(self, 'dingtalk_bot') and self.dingtalk_bot:
                await self.dingtalk_bot.send_alert_notification_async("warning", notification_info)
                logger.info(f"[客户止损] 客户 {customer_uid} 止损通知已发送")
            else:
                logger.warning(f"[客户止损] 钉钉机器人未初始化，无法发送通知")
                
        except Exception as e:
            logger.error(f"[客户止损] 发送止损通知失败: {e}")

    async def _send_signal_source_stop_loss_notification(self, signal_source, old_init_assets, current_assets):
        """发送信号源止损通知"""
        try:
            source_uid = signal_source.get('source_uid')
            source_name = signal_source.get('source_name', source_uid)
            
            notification_info = {
                "title": "信号源止损通知",
                "level": "WARNING",
                "message": f"信号源 {source_name} 触发止损",
                "account": f"信号源UID: {source_uid}",
                "strategy": "止损监控",
                "symbol": f"原资产: {old_init_assets:.2f} → 当前资产: {current_assets:.2f}",
                "suggestion": "请检查信号源账户状态和交易策略"
            }
            
            # 发送钉钉通知
            if hasattr(self, 'dingtalk_bot') and self.dingtalk_bot:
                await self.dingtalk_bot.send_alert_notification_async("warning", notification_info)
                logger.info(f"[信号源止损] 信号源 {source_uid} 止损通知已发送")
            else:
                logger.warning(f"[信号源止损] 钉钉机器人未初始化，无法发送通知")
                
        except Exception as e:
            logger.error(f"[信号源止损] 发送止损通知失败: {e}")

    async def stop_stop_loss_monitor(self):
        """停止止损监控"""
        try:
            logger.info("停止止损监控...")
            
            if hasattr(self, 'stop_loss_monitor') and self.stop_loss_monitor:
                self.stop_loss_monitor.cancel()
                self.stop_loss_monitor = None
                logger.info("止损监控已停止")
            else:
                logger.info("止损监控未运行")
                
        except Exception as e:
            logger.error(f"停止止损监控失败: {e}")

    # ==================== 并行减仓辅助方法 ====================
    
    async def _execute_customer_reduce_order(self, customer_uid: str, customer_trades: List, symbol: str, 
                                           pos_side: str, customer_total_reduce: float, 
                                           signal_reduce_ratio: float, is_demo: bool):
        """执行单个客户的减仓订单 - 用于并行处理"""
        try:
            # 获取客户信息
            customer_data = get_customer_by_id(self.db_pool, customer_uid, is_demo=is_demo)
            if not customer_data:
                logger.error(f"[客户减仓] 未找到客户{customer_uid}，跳过")
                return False
            
            # 将字典转换为Customer对象
            customer = self.safe_customer(customer_data)
            
            direction = 'sell' if get_trade_field(customer_trades[0], 'pos_side') == 'long' else 'buy'
            clOrdId = f"ORDER_REDUCE_{customer_uid}_{symbol}_{pos_side}_{int(time.time())}"[:32]
            
            logger.info(f"[客户减仓] 🚀 并行执行客户{customer_uid}减仓: symbol={symbol}, pos_side={pos_side}, sz={customer_total_reduce}, clOrdId={clOrdId}")
            
            res = await self.async_place_order(
                customer=customer,
                symbol=symbol,
                direction=direction,
                pos_side=pos_side,
                sz=customer_total_reduce,
                trade_uid=clOrdId,
                reduceOnly=True,
                tag='6618f740e7f1BCDE'
            )
            
            ordId = res.get('ordId') if res else None
            status = res.get('status') if res else None
            
            # 如果返回状态是closed，说明已经通过持仓检查更新了状态
            if status == 'closed':
                logger.info(f"[客户减仓] 🚀 客户{customer_uid}并行减仓已完成（通过持仓检查）")
                return True
            elif ordId:
                # 更新所有相关trade的order_id和close_volume_contract
                for trade in customer_trades:
                    trade_uid = get_trade_field(trade, 'trade_uid')
                    customer_volume = float(get_trade_field(trade, 'volume_contract') or 0)
                    customer_reduce = customer_volume * signal_reduce_ratio
                    customer_reduce = round(customer_reduce, get_contract_sz_precision(symbol))
                    
                    # 更新order_id
                    update_customer_trade_order_id(self.db_pool, trade_uid, ordId)
                    # 更新close_volume_contract
                    update_customer_trade_close_volume_contract(self.db_pool, trade_uid, customer_reduce)
                    
                    logger.info(f"[客户减仓] 🚀 并行减仓已写入: trade_uid={trade_uid}, ordId={ordId}, close_volume_contract={customer_reduce}")
                    
                    # 检查是否需要更新status为closed
                    current_closed = float(get_trade_field(trade, 'close_volume_contract') or 0)
                    new_closed = current_closed + customer_reduce
                    if new_closed >= customer_volume:
                        self.db_pool.execute(
                            "UPDATE customer_trades SET status='closed' WHERE trade_uid=%s",
                            (trade_uid,)
                        )
                        logger.info(f"[客户减仓] 🚀 并行减仓持仓已全平: trade_uid={trade_uid}, status=closed")
                
                logger.info(f"[客户减仓] 🚀 客户{customer_uid}并行减仓成功完成")
                return True
            else:
                logger.error(f"[客户减仓] 🚀 客户{customer_uid}并行减仓下单失败: {res}")
                return False
                
        except Exception as e:
            logger.error(f"[客户减仓] 🚀 客户{customer_uid}并行减仓异常: {e}")
            return False

    async def _place_signal_source_close_order(self, signal_source, symbol, side, pos_side, volume_contract, trade_uid):
        """为信号源平仓下单 - 等待连接就绪后执行"""
        try:
            source_uid = safe_get_attr(signal_source, 'source_uid')
            logger.info(f"[信号源止损] 开始为信号源 {source_uid} 执行平仓...")
            
            # 1. 等待信号源WebSocket连接就绪
            client = await self._wait_for_signal_source_client_ready(signal_source)
            if not client:
                logger.error(f"[信号源止损] 信号源 {source_uid} 客户端未就绪，无法平仓")
                return None
            
            # 2. 构建平仓订单参数
            close_order_params = {
                "instId": symbol,
                "tdMode": "cross",
                "side": side,
                "posSide": pos_side,
                "ordType": "market",
                "sz": str(volume_contract),
                "reduceOnly": "true"
            }
            
            logger.info(f"[信号源止损] 开始平仓下单: {close_order_params}")
            
            # 3. 执行平仓下单
            try:
                response = await client.place_order(**close_order_params)
                logger.info(f"[信号源止损] 平仓下单成功: {response}")
                return response
            except Exception as e:
                logger.error(f"[信号源止损] 平仓下单异常: {e}")
                return None
                
        except Exception as e:
            source_uid = safe_get_attr(signal_source, 'source_uid', 'unknown')
            logger.error(f"[信号源止损] 信号源 {source_uid} 平仓下单失败: {e}")
            return None
    
    async def _place_customer_close_order(self, customer, symbol, side, pos_side, volume_contract, trade_uid):
        """为客户平仓下单 - 等待连接就绪后执行"""
        try:
            customer_uid = get_customer_uid(customer)
            logger.info(f"[客户止损] 开始为客户 {customer_uid} 执行平仓...")
            
            # 1. 等待客户WebSocket连接就绪
            client = await self._wait_for_customer_client_ready(customer)
            if not client:
                logger.error(f"[客户止损] 客户 {customer_uid} 客户端未就绪，无法平仓")
                return None
            
            # 2. 构建平仓订单参数
            close_order_params = {
                "instId": symbol,
                "tdMode": "cross",
                "side": side,
                "posSide": pos_side,
                "ordType": "market",
                "sz": str(volume_contract),
                "reduceOnly": "true"
            }
            
            logger.info(f"[客户止损] 开始平仓下单: {close_order_params}")
            
            # 3. 执行平仓下单
            try:
                response = await client.place_order(**close_order_params)
                logger.info(f"[客户止损] 平仓下单成功: {response}")
                return response
            except Exception as e:
                logger.error(f"[客户止损] 平仓下单异常: {e}")
                return None
                
        except Exception as e:
            customer_uid = get_customer_uid(customer)
            logger.error(f"[客户止损] 客户 {customer_uid} 平仓下单失败: {e}")
            return None
    
    async def _wait_for_signal_source_client_ready(self, signal_source, timeout=30):
        """等待信号源客户端就绪"""
        try:
            source_uid = safe_get_attr(signal_source, 'source_uid')
            logger.info(f"[信号源止损] 等待信号源 {source_uid} 客户端就绪...")
            
            start_time = time.time()
            while time.time() - start_time < timeout:
                # 尝试获取现有客户端
                client = await self._get_existing_signal_source_client(signal_source)
                if client and client.is_connection_healthy():
                    logger.info(f"[信号源止损] 信号源 {source_uid} 客户端已就绪")
                    return client
                
                # 等待1秒后重试
                await asyncio.sleep(1)
            
            logger.error(f"[信号源止损] 信号源 {source_uid} 客户端等待超时")
            return None
            
        except Exception as e:
            source_uid = safe_get_attr(signal_source, 'source_uid', 'unknown')
            logger.error(f"[信号源止损] 等待信号源 {source_uid} 客户端就绪失败: {e}")
            return None
    
    async def _wait_for_customer_client_ready(self, customer, timeout=30):
        """等待客户客户端就绪"""
        try:
            customer_uid = get_customer_uid(customer)
            logger.info(f"[客户止损] 等待客户 {customer_uid} 客户端就绪...")
            
            start_time = time.time()
            while time.time() - start_time < timeout:
                # 尝试获取现有客户端
                client = await self._get_existing_customer_client(customer)
                if client and client.is_connection_healthy():
                    logger.info(f"[客户止损] 客户 {customer_uid} 客户端已就绪")
                    return client
                
                # 等待1秒后重试
                await asyncio.sleep(1)
            
            logger.error(f"[客户止损] 客户 {customer_uid} 客户端等待超时")
            return None
            
        except Exception as e:
            customer_uid = get_customer_uid(customer)
            logger.error(f"[客户止损] 等待客户 {customer_uid} 客户端就绪失败: {e}")
            return None
    
    async def _get_existing_signal_source_client(self, signal_source):
        """获取现有的信号源客户端"""
        try:
            source_uid = safe_get_attr(signal_source, 'source_uid')
            if not source_uid:
                return None
            
            # 使用全局客户端管理器获取现有客户端
            client_manager = get_global_client_manager()
            
            # 构建客户端key
            client_key = f"signal_{source_uid}"
            
            # 检查是否已有客户端
            if hasattr(client_manager, '_clients') and client_key in client_manager._clients:
                existing_client = client_manager._clients[client_key]
                if existing_client and existing_client.is_connection_healthy():
                    logger.debug(f"[信号源止损] 找到现有信号源客户端: {source_uid}")
                    return existing_client
            
            logger.debug(f"[信号源止损] 未找到就绪的信号源客户端: {source_uid}")
            return None
            
        except Exception as e:
            logger.error(f"[信号源止损] 获取现有信号源客户端失败: {e}")
            return None
    
    async def _get_existing_customer_client(self, customer):
        """获取现有的客户客户端"""
        try:
            customer_uid = get_customer_uid(customer)
            if not customer_uid:
                return None
            
            # 使用全局客户端管理器获取现有客户端
            client_manager = get_global_client_manager()
            
            # 构建客户端key
            client_key = f"customer_{customer_uid}"
            
            # 检查是否已有客户端
            if hasattr(client_manager, '_clients') and client_key in client_manager._clients:
                existing_client = client_manager._clients[client_key]
                if existing_client and existing_client.is_connection_healthy():
                    logger.debug(f"[客户止损] 找到现有客户客户端: {customer_uid}")
                    return existing_client
            
            logger.debug(f"[客户止损] 未找到就绪的客户客户端: {customer_uid}")
            return None
            
        except Exception as e:
            logger.error(f"[客户止损] 获取现有客户客户端失败: {e}")
            return None

    # ==================== 限价跟单模块 ====================
    
    async def trigger_limit_follow_orders(self, signal_source_uid, symbol, pos_side, signal_price, signal_trade_uid):
        """触发限价跟单订单 - 支持限价和市价跟单"""
        try:
            logger.info(f"[限价跟单] 触发限价跟单: {signal_source_uid} {symbol} {pos_side} @ {signal_price} - 订单号{signal_trade_uid}")
            
            # 查询相关的限价跟单策略（支持多客户）
            strategies = self.db_pool.query(
                """SELECT lfs.*, sc.customer_uid, sc.enabled as customer_enabled, 
                          sc.custom_leverage, sc.custom_follow_value
                   FROM limit_follow_strategies lfs
                   LEFT JOIN limit_follow_strategy_customers sc ON lfs.id = sc.strategy_id
                   WHERE lfs.trader_unique_name=%s AND lfs.enabled=1 
                   AND (
                       lfs.symbol='ALL' 
                       OR lfs.symbol=%s 
                       OR (lfs.symbol='SPECIFIC' AND JSON_CONTAINS(lfs.symbols, %s))
                   )
                   AND (lfs.pos_side='both' OR lfs.pos_side=%s)
                   AND (sc.enabled=1 OR sc.enabled IS NULL)
                   ORDER BY lfs.id, sc.id""",
                (signal_source_uid, symbol, f'"{symbol}"', pos_side)
            )
            
            # 如果没有关联客户，使用传统的customer_uid字段（向后兼容）
            if not strategies:
                strategies = self.db_pool.query(
                    """SELECT *, customer_uid, 1 as customer_enabled, 
                              leverage as custom_leverage, follow_value as custom_follow_value
                       FROM limit_follow_strategies 
                       WHERE trader_unique_name=%s AND enabled=1 
                       AND (
                           symbol='ALL' 
                           OR symbol=%s 
                           OR (symbol='SPECIFIC' AND JSON_CONTAINS(symbols, %s))
                       )
                       AND (pos_side='both' OR pos_side=%s)
                       AND customer_uid IS NOT NULL""",
                    (signal_source_uid, symbol, f'"{symbol}"', pos_side)
                )
            
            if not strategies:
                logger.info(f"[限价跟单] 未找到相关策略: {signal_source_uid} {symbol} {pos_side}")
                return
            
            logger.info(f"[限价跟单] 找到 {len(strategies)} 个限价跟单策略记录")
            
            # 按策略ID分组处理多客户策略
            strategy_groups = {}
            for strategy in strategies:
                strategy_id = strategy['id']
                if strategy_id not in strategy_groups:
                    strategy_groups[strategy_id] = {
                        'strategy': strategy,
                        'customers': []
                    }
                # 检查客户字段（可能是sc.customer_uid或customer_uid）
                customer_uid = strategy.get('sc.customer_uid') or strategy.get('customer_uid')
                if customer_uid:
                    strategy_groups[strategy_id]['customers'].append({
                        'customer_uid': customer_uid,
                        'customer_enabled': strategy.get('customer_enabled', 1),
                        'custom_leverage': strategy.get('custom_leverage'),
                        'custom_follow_value': strategy.get('custom_follow_value')
                    })
            
            # 为每个策略的每个客户处理限价跟单
            for strategy_id, group in strategy_groups.items():
                strategy = group['strategy']
                customers = group['customers']
                
                if not customers:
                    logger.warning(f"[限价跟单] 策略 {strategy_id} 没有关联客户，跳过处理")
                    continue
                
                logger.info(f"[限价跟单] 策略 {strategy_id} 关联 {len(customers)} 个客户")
                
                for customer in customers:
                    try:
                        # 创建客户特定的策略副本
                        customer_strategy = strategy.copy()
                        customer_strategy['customer_uid'] = customer['customer_uid']
                        customer_strategy['customer_enabled'] = customer['customer_enabled']
                        customer_strategy['custom_leverage'] = customer['custom_leverage']
                        customer_strategy['custom_follow_value'] = customer['custom_follow_value']
                        
                        # 根据策略配置的跟单订单类型处理
                        follow_order_types = customer_strategy.get('follow_order_types', 'limit_only')
                        
                        if follow_order_types in ['limit_only', 'both']:
                            await self._process_limit_follow_strategy(
                                customer_strategy, signal_source_uid, symbol, pos_side, 
                                signal_price, signal_trade_uid, 'limit'
                            )
                        
                        if follow_order_types in ['market_only', 'both']:
                            await self._process_market_follow_strategy(
                                customer_strategy, signal_source_uid, symbol, pos_side, 
                                signal_price, signal_trade_uid
                            )
                    except Exception as e:
                        logger.error(f"[限价跟单] 策略 {strategy_id} 客户 {customer['customer_uid']} 处理失败: {e}")
                    
        except Exception as e:
            logger.error(f"[限价跟单] 触发限价跟单失败: {e}")

    async def _process_limit_follow_strategy(self, strategy, signal_source_uid, symbol, pos_side, signal_price, signal_trade_uid):
        """处理限价跟单策略 - 完善FIFO机制"""
        try:
            logger.info(f"[限价跟单] 处理策略: 客户={strategy['customer_uid']}, 信号源={signal_source_uid}")
            logger.info(f"[限价跟单] 策略详情: {strategy}")
            
            # 1. 计算目标仓位（使用单次交易仓位，处理连续开仓情况）
            signal_position = await self._get_signal_position_for_single_trade(signal_source_uid, symbol, pos_side)
            if signal_position <= 0:
                logger.warning(f"[限价跟单] 信号源无当前交易持仓，跳过处理")
                return
                
            target_position = await self._calculate_target_position(strategy, signal_source_uid, signal_position)
            if target_position <= 0:
                logger.warning(f"[限价跟单] 目标仓位为0，跳过处理")
                return
            
            # 2. 获取客户当前状态
            current_position = await self._get_customer_position(strategy['customer_uid'], symbol, pos_side)
            
            # 3. 获取挂单状态
            pending_orders = self.db_pool.query(
                """SELECT * FROM limit_follow_orders 
                WHERE strategy_id=%s AND symbol=%s AND pos_side=%s 
                AND status IN ('pending', 'live')""",
                (strategy['id'], symbol, pos_side)
            )
            
            # 4. 计算需要新增的仓位
            need_position = target_position - current_position
            
            if need_position <= 0:
                logger.info(f"[限价跟单] 无需新增仓位，当前仓位已满足")
                return
            
            # 5. 检查杠杆限制
            if not await self._check_leverage_limit(strategy, need_position, signal_price):
                logger.warning(f"[限价跟单] 超过最大净杠杆限制，尝试FIFO撤单")
                # 调用杠杆超限处理函数
                await self._handle_leverage_limit_exceeded(
                    strategy, signal_source_uid, symbol, pos_side, signal_price, signal_trade_uid, need_position
                )
                return
            
            # 6. 创建限价单 - 使用策略配置的订单数量
            max_orders = int(strategy.get('max_orders_per_signal', 1))
            logger.info(f"[限价跟单] 创建限价单: 目标仓位={need_position}, 最大订单数={max_orders}")
            
            await self._create_limit_orders(
                strategy, signal_source_uid, symbol, pos_side, signal_price, 
                need_position, max_orders, signal_trade_uid
            )
            
        except Exception as e:
            logger.error(f"[限价跟单] 处理策略失败: {e}")

    async def _adjust_order_size_precision(self, symbol, order_size):
        """调整订单数量精度"""
        try:
            # 获取合约信息
            contract_info = get_contract_info(symbol)
            
            if not contract_info:
                # 默认精度调整
                return round(order_size, 2)
            
            # 获取最小单位
            min_size = contract_info.get('min_size', 0.01)
            
            # 计算精度
            if min_size >= 1:
                # 整数精度
                precision = 0
            elif min_size >= 0.1:
                # 1位小数
                precision = 1
            elif min_size >= 0.01:
                # 2位小数
                precision = 2
            elif min_size >= 0.001:
                # 3位小数
                precision = 3
            else:
                # 4位小数
                precision = 4
            
            # 调整精度
            adjusted_size = round(order_size, precision)
            
            # 确保是最小单位的倍数
            if min_size > 0:
                adjusted_size = round(adjusted_size / min_size) * min_size
            
            logger.info(f"[限价跟单] 订单数量精度调整: 原始={order_size}, 调整后={adjusted_size}, 最小单位={min_size}")
            
            return adjusted_size
            
        except Exception as e:
            logger.error(f"[限价跟单] 调整订单数量精度失败: {e}")
            return round(order_size, 2)  # 默认2位小数

    async def _calculate_target_position(self, strategy, signal_source_uid, signal_position):
        """计算客户目标仓位"""
        logger.info(f"目标策略: {strategy}")
        try:
            follow_mode = strategy['follow_mode']
            
            if follow_mode == 'follow_trader':
                # 跟单员模式：使用固定比例
                follow_ratio = float(strategy.get('trader_follow_ratio', 0.05))  # 默认5%
                target_position = signal_position * follow_ratio
                logger.info(f"[限价跟单] 跟单员模式: 信号仓位={signal_position}, 跟单比例={follow_ratio}, 目标仓位={target_position}")
                
            elif follow_mode == 'follow_signal_source':
                # 信号源模式：动态计算资金比例
                customer_funds = await self._get_customer_funds(strategy['customer_uid'])
                signal_funds = await self._get_signal_funds(signal_source_uid)
                
                if signal_funds <= 0:
                    logger.warning(f"[限价跟单] 信号源资金为0，跳过: {signal_source_uid}")
                    return 0
                
                # 计算资金比例
                if strategy['proportional_position']:
                    fund_ratio = customer_funds / signal_funds
                else:
                    fund_ratio = 1.0
                
                # 获取跟单比例（优先使用客户自定义值）
                if strategy.get('custom_follow_value'):
                    follow_ratio = float(strategy['custom_follow_value']) / 100
                    logger.info(f"[限价跟单] 使用客户自定义跟单值: {strategy['custom_follow_value']}%")
                else:
                    follow_ratio = float(strategy.get('follow_value', 2.0)) / 100  # 跟单比例
                
                # 计算目标仓位
                target_position = signal_position * fund_ratio * follow_ratio
                
                logger.info(f"[限价跟单] 信号源模式: 信号仓位={signal_position}, 客户资金={customer_funds}, 信号资金={signal_funds}, 资金比例={fund_ratio:.4f}, 跟单比例={follow_ratio:.4f}, 目标仓位={target_position}")
                
            else:
                logger.error(f"[限价跟单] 未知的跟单模式: {follow_mode}")
                return 0
            
            return target_position
            
        except Exception as e:
            logger.error(f"[限价跟单] 计算目标仓位失败: {e}")
            return 0

    async def _get_follow_ratio(self, strategy, signal_source_uid):
        """获取跟单比例"""
        try:
            logger.info(strategy)
            follow_mode = strategy['follow_mode']
            
            if follow_mode == 'follow_trader':
                # 跟单员模式：使用固定比例
                follow_ratio = float(strategy.get('trader_follow_ratio', 0.05))  # 默认5%
                logger.info(f"[限价跟单] 跟单员模式，跟单比例: {follow_ratio}")
                
            elif follow_mode == 'follow_signal_source':
                # 信号源模式：动态计算资金比例
                customer_funds = await self._get_customer_funds(strategy['customer_uid'])
                signal_funds = await self._get_signal_funds(signal_source_uid)
                
                if signal_funds <= 0:
                    logger.warning(f"[限价跟单] 信号源资金为0，使用默认比例: {signal_source_uid}")
                    return 1.0  # 默认1:1比例
                
                # 计算资金比例
                fund_ratio = customer_funds / signal_funds
                
                # 获取跟单比例
                follow_ratio = float(strategy.get('follow_value', 2.0)) / 100  # 跟单比例
                
                # 最终比例 = 资金比例 × 跟单比例
                final_ratio = fund_ratio * follow_ratio
                
                logger.info(f"[限价跟单] 信号源模式: 客户资金={customer_funds}, 信号资金={signal_funds}, 资金比例={fund_ratio:.4f}, 跟单比例={follow_ratio:.4f}, 最终比例={final_ratio:.4f}")
                
            else:
                logger.error(f"[限价跟单] 未知的跟单模式: {follow_mode}")
                return 1.0  # 默认1:1比例
            
            return final_ratio
            
        except Exception as e:
            logger.error(f"[限价跟单] 获取跟单比例失败: {e}")
            return 1.0  # 默认1:1比例

    async def _get_signal_funds(self, signal_source_uid):
        """获取信号源当前资金"""
        try:
            signal_source = self.db_pool.query(
                "SELECT asset FROM signal_account_assets WHERE signal_source_uid=%s",
                (signal_source_uid,)
            )
            
            if signal_source and signal_source[0]['asset']:
                return float(signal_source[0]['asset'])
            return 0.0
            
        except Exception as e:
            logger.error(f"[限价跟单] 获取信号源资金失败: {e}")
            return 0.0

    async def _get_customer_funds(self, customer_uid):
        """获取客户当前资金"""
        try:
            customer = self.db_pool.query(
                "SELECT total_asset FROM customers WHERE customer_uid=%s",
                (customer_uid,)
            )
            
            if customer and customer[0]['total_asset']:
                return float(customer[0]['total_asset'])
            return 0.0
            
        except Exception as e:
            logger.error(f"[限价跟单] 获取客户资金失败: {e}")
            return 0.0

    async def _get_signal_position(self, signal_source_uid, symbol, pos_side, signal_trade_uid=None):
        """获取信号源当前仓位"""
        try:
            if signal_trade_uid:
                position = self.db_pool.query(
                    """SELECT SUM(volume_contract - IFNULL(close_volume_contract, 0)) as total_volume 
                    FROM signal_account_trades 
                    WHERE order_id=%s""",
                    (signal_trade_uid, )
                )
            else:
                # 查询信号源当前仓位
                position = self.db_pool.query(
                    """SELECT SUM(volume_contract) as total_volume 
                    FROM signal_account_trades 
                    WHERE signal_source_uid=%s AND symbol=%s AND pos_side=%s AND status='open'""",
                    (signal_source_uid, symbol, pos_side)
                )
            
            if position and position[0]['total_volume']:
                return float(position[0]['total_volume'])
            return 0.0
            
        except Exception as e:
            logger.error(f"[限价跟单] 获取信号源仓位失败: {e}")
            return 0.0

    async def _get_signal_position_for_trade(self, signal_source_uid, symbol, pos_side, signal_trade_uid=None):
        """获取信号源当前交易相关的仓位（排除历史持仓）"""
        try:
            if signal_trade_uid:
                # 如果指定了交易ID，只计算该交易的持仓
                position = self.db_pool.query(
                    """SELECT SUM(volume_contract - IFNULL(close_volume_contract, 0)) as total_volume 
                    FROM signal_account_trades 
                    WHERE order_id=%s""",
                    (signal_trade_uid, )
                )
            else:
                # 智能获取当前交易相关的仓位
                # 1. 先尝试获取最近30分钟内的仓位（最精确）
                position = self.db_pool.query(
                    """SELECT
                            ifnull(SUM( volume_contract - IFNULL( close_volume_contract, 0 ) ), 0) AS total_volume 
                        FROM
                            signal_account_trades 
                    WHERE signal_source_uid=%s AND symbol=%s AND pos_side=%s 
                    AND status='open' 
                    AND created_at >= DATE_SUB(NOW(), INTERVAL 30 MINUTE)""",
                    (signal_source_uid, symbol, pos_side)
                )
                
                # 2. 如果最近30分钟内没有仓位，则获取最近1小时内的仓位
                if not position or not position[0]['total_volume'] or float(position[0]['total_volume']) <= 0:
                    logger.info(f"[限价跟单] 最近30分钟内无仓位，查询最近1小时内的仓位")
                    position = self.db_pool.query(
                        """SELECT
                                ifnull(SUM( volume_contract - IFNULL( close_volume_contract, 0 ) ), 0) AS total_volume 
                            FROM
                                signal_account_trades 
                        WHERE signal_source_uid=%s AND symbol=%s AND pos_side=%s 
                        AND status='open' 
                        AND created_at >= DATE_SUB(NOW(), INTERVAL 1 HOUR)""",
                        (signal_source_uid, symbol, pos_side)
                    )
                
                # 3. 如果最近1小时内没有仓位，则获取最近2小时内的仓位
                if not position or not position[0]['total_volume'] or float(position[0]['total_volume']) <= 0:
                    logger.info(f"[限价跟单] 最近1小时内无仓位，查询最近2小时内的仓位")
                    position = self.db_pool.query(
                        """SELECT
                                ifnull(SUM( volume_contract - IFNULL( close_volume_contract, 0 ) ), 0) AS total_volume 
                            FROM
                                signal_account_trades 
                        WHERE signal_source_uid=%s AND symbol=%s AND pos_side=%s 
                        AND status='open' 
                        AND created_at >= DATE_SUB(NOW(), INTERVAL 2 HOUR)""",
                        (signal_source_uid, symbol, pos_side)
                    )
                
                # 4. 如果还是没有，则获取最近4小时内的仓位（兜底）
                if not position or not position[0]['total_volume'] or float(position[0]['total_volume']) <= 0:
                    logger.info(f"[限价跟单] 最近2小时内无仓位，查询最近4小时内的仓位")
                    position = self.db_pool.query(
                        """SELECT
                                ifnull(SUM( volume_contract - IFNULL( close_volume_contract, 0 ) ), 0) AS total_volume 
                            FROM
                                signal_account_trades 
                        WHERE signal_source_uid=%s AND symbol=%s AND pos_side=%s 
                        AND status='open' 
                        AND created_at >= DATE_SUB(NOW(), INTERVAL 4 HOUR)""",
                        (signal_source_uid, symbol, pos_side)
                    )
            
            if position and position[0]['total_volume']:
                total_volume = float(position[0]['total_volume'])
                logger.info(f"[限价跟单] 信号源当前交易仓位: {total_volume} (排除历史持仓)")
                return total_volume
            return 0.0
            
        except Exception as e:
            logger.error(f"[限价跟单] 获取信号源交易仓位失败: {e}")
            return 0.0

    async def _get_signal_position_for_single_trade(self, signal_source_uid, symbol, pos_side, signal_trade_uid=None):
        """获取信号源单次交易的仓位（处理连续开仓情况）"""
        try:
            if signal_trade_uid:
                # 如果指定了交易ID，只计算该交易的持仓
                position = self.db_pool.query(
                    """SELECT SUM(volume_contract - IFNULL(close_volume_contract, 0)) as total_volume 
                    FROM signal_account_trades 
                    WHERE order_id=%s""",
                    (signal_trade_uid, )
                )
            else:
                # 获取最近一次开仓的仓位（处理连续开仓情况）
                # 查询最近一次开仓的时间
                latest_trade = self.db_pool.query(
                    """SELECT created_at, volume_contract, close_volume_contract
                    FROM signal_account_trades 
                    WHERE signal_source_uid=%s AND symbol=%s AND pos_side=%s 
                    AND status='open' 
                    ORDER BY created_at DESC 
                    LIMIT 1""",
                    (signal_source_uid, symbol, pos_side)
                )
                
                if not latest_trade:
                    logger.info(f"[限价跟单] 信号源无任何持仓")
                    return 0.0
                
                # 获取最近一次开仓的时间
                latest_time = latest_trade[0]['created_at']
                logger.info(f"[限价跟单] 最近一次开仓时间: {latest_time}")
                
                # 查询最近一次开仓的仓位
                position = self.db_pool.query(
                    """SELECT
                            ifnull(SUM( volume_contract - IFNULL( close_volume_contract, 0 ) ), 0) AS total_volume 
                        FROM
                            signal_account_trades 
                    WHERE signal_source_uid=%s AND symbol=%s AND pos_side=%s 
                    AND status='open' 
                    AND created_at >= %s""",
                    (signal_source_uid, symbol, pos_side, latest_time)
                )
            
            if position and position[0]['total_volume']:
                total_volume = float(position[0]['total_volume'])
                logger.info(f"[限价跟单] 信号源单次交易仓位: {total_volume} (最近一次开仓)")
                return total_volume
            return 0.0
            
        except Exception as e:
            logger.error(f"[限价跟单] 获取信号源单次交易仓位失败: {e}")
            return 0.0

    async def _get_customer_position(self, customer_uid, symbol, pos_side, signal_trade_uid=None):
        """获取客户当前仓位"""
        try:
            # 查询客户当前仓位（包括已成交和挂单）
            if signal_trade_uid:
                position = self.db_pool.query(
                    """SELECT SUM(order_size) as total_volume 
                    FROM limit_follow_orders 
                    WHERE signal_order_id=%s 
                    AND status='filled'""",
                    (signal_trade_uid, )
                )
            else:
                # 查询客户当前仓位（包括已成交和挂单）
                position = self.db_pool.query(
                    """SELECT SUM(order_size) as total_volume 
                    FROM limit_follow_orders 
                    WHERE customer_uid=%s AND symbol=%s AND pos_side=%s 
                    AND status='filled'""",
                    (customer_uid, symbol, pos_side)
                )
            
            if position and position[0]['total_volume']:
                return float(position[0]['total_volume'])
            return 0.0
            
        except Exception as e:
            logger.error(f"[限价跟单] 获取客户仓位失败: {e}")
            return 0.0

    async def _check_leverage_limit(self, strategy, need_position, current_price=None):
        """检查最大净杠杆限制"""
        try:
            customer_uid = strategy['customer_uid']
            symbol = strategy['symbol']
            pos_side = strategy.get('pos_side', 'both')
            
            # 获取客户当前资金
            customer = self.db_pool.query(
                "SELECT total_asset FROM customers WHERE customer_uid=%s",
                (customer_uid,)
            )
            
            if not customer:
                logger.warning(f"[杠杆检查] 无法获取客户资产: {customer_uid}")
                return False
            
            current_asset = float(customer[0]['total_asset'])
            max_leverage = float(strategy['max_net_leverage'])
            
            # 获取当前价格
            if not current_price:
                current_price = await get_price_on_demand(symbol)
                if not current_price:
                    logger.warning(f"[杠杆检查] 无法获取价格: {symbol}")
                    return False
            
            # 1. 获取已成交持仓（考虑方向）
            current_position = await self._get_customer_position(customer_uid, symbol, pos_side)
            
            # 2. 获取未成交挂单
            if pos_side == 'both':
                pending_orders = self.db_pool.query(
                    """SELECT order_size FROM limit_follow_orders 
                    WHERE customer_uid=%s AND symbol=%s 
                    AND status IN ('pending', 'live')""",
                    (customer_uid, symbol)
                )
            else:
                pending_orders = self.db_pool.query(
                    """SELECT order_size FROM limit_follow_orders 
                    WHERE customer_uid=%s AND symbol=%s AND pos_side=%s 
                    AND status IN ('pending', 'live')""",
                    (customer_uid, symbol, pos_side)
                )
            
            # 3. 计算总风险敞口（考虑方向性）
            pending_exposure = sum(float(order['order_size']) for order in pending_orders)
            
            # 计算总风险敞口：已成交持仓 + 挂单 + 新增仓位
            # 注意：这里应该考虑持仓的方向性，多空持仓应该分别计算
            total_exposure = abs(current_position) + pending_exposure + need_position
            
            # 4. 计算所需保证金
            margin_rate = 0.1  # 默认10%保证金
            risk_multiplier = 1.2  # 20%风险缓冲
            required_margin = total_exposure * current_price * margin_rate * risk_multiplier
            
            # 5. 检查杠杆限制
            leverage_ratio = required_margin / current_asset
            
            logger.info(f"[杠杆检查] 客户={customer_uid}, 资产={current_asset}, 已成交={current_position}, 挂单={pending_exposure}, 新增={need_position}, 总敞口={total_exposure}, 杠杆比例={leverage_ratio:.2%}, 最大杠杆={max_leverage:.2%}")
            
            return leverage_ratio <= max_leverage
            
        except Exception as e:
            logger.error(f"[杠杆检查] 检查失败: {e}")
            return False

    async def _handle_leverage_limit_exceeded(self, strategy, signal_source_uid, symbol, pos_side, signal_price, signal_trade_uid, need_position):
        """处理净杠杆超限 - FIFO撤单"""
        try:
            logger.info(f"[限价跟单] 开始处理杠杆超限: 客户={strategy['customer_uid']}, 信号源={signal_source_uid}")
            
            # 1. 撤销最老的未成交限价单（按创建时间和ID排序）
            pending_orders = self.db_pool.query(
                """SELECT * FROM limit_follow_orders 
                WHERE strategy_id=%s AND symbol=%s AND pos_side=%s 
                AND status IN ('pending', 'live')
                ORDER BY created_at ASC, id ASC""",
                (strategy['id'], symbol, pos_side)
            )
            
            if not pending_orders:
                logger.warning(f"[限价跟单] 没有可撤销的限价单: 客户={strategy['customer_uid']}")
                return
            
            # 2. 逐步撤销限价单直到满足杠杆要求
            canceled_count = 0
            for order in pending_orders:
                try:
                    # 撤单
                    self.db_pool.execute(
                        "UPDATE limit_follow_orders SET status='canceled', updated_at=NOW() WHERE order_uid=%s",
                        (order['order_uid'],)
                    )
                    
                    canceled_count += 1
                    logger.info(f"[限价跟单] 杠杆超限撤单: {order['order_uid']}, 创建时间: {order['created_at']}")
                    
                    # 重新检查杠杆限制
                    if await self._check_leverage_limit(strategy, need_position, signal_price):
                        logger.info(f"[限价跟单] 杠杆限制已满足，停止撤单，共撤销{canceled_count}个订单")
                        break
                        
                except Exception as e:
                    logger.error(f"[限价跟单] 撤单失败: {order['order_uid']}, 错误: {e}")
                    continue
            
            # 3. 重新尝试创建限价单
            if canceled_count > 0:
                logger.info(f"[限价跟单] 重新尝试创建限价单")
                await self._process_limit_follow_strategy(
                    strategy, signal_source_uid, symbol, pos_side, signal_price, signal_trade_uid
                )
            
        except Exception as e:
            logger.error(f"[限价跟单] 处理杠杆超限失败: {e}")

    async def _create_limit_orders(self, strategy, signal_source_uid, symbol, pos_side, signal_price, order_size, orders_count, signal_trade_uid):
        """创建限价单 - 支持多个订单，平均分配仓位"""
        try:
            # 🚀 风控检查：创建限价单前进行止损和净杠杆检查
            customer_uid = strategy['customer_uid']
            logger.info(f"[限价跟单] 开始为客户 {customer_uid} 创建限价单")
            
            # 1. 止损检查
            try:
                customer_data = self.db_pool.query(
                    "SELECT * FROM customers WHERE customer_uid=%s",
                    (customer_uid,)
                )
                if customer_data:
                    await self._check_single_customer_stop_loss(customer_data[0])
            except Exception as e:
                logger.error(f"[限价单风控] 止损检查失败: {e}")
            
            # 2. 净杠杆检查
            try:
                max_leverage = float(strategy.get('max_net_leverage', 10.0))
                
                # 获取客户API凭证创建REST客户端
                customer_data = self.db_pool.query(
                    "SELECT api_key, api_secret, passphrase FROM customers WHERE customer_uid=%s",
                    (customer_uid,)
                )
                
                if not customer_data:
                    logger.warning(f"[限价单风控] 客户{customer_uid}配置不存在，跳过净杠杆检查")
                    current_leverage = 0.0
                else:
                    from trade_service import get_global_is_demo
                    rest_client = OKXRESTClient(
                        customer_data[0]['api_key'],
                        customer_data[0]['api_secret'],
                        customer_data[0]['passphrase'],
                        is_demo=get_global_is_demo()
                    )
                    
                    current_leverage = await self._calculate_net_leverage_for_customer(
                        customer_uid, symbol, pos_side, rest_client
                    )
                
                if current_leverage > max_leverage:
                    logger.warning(f"[限价单风控] 客户{customer_uid}净杠杆超限: {current_leverage:.2f} > {max_leverage:.2f}")
                    return  # 跳过创建限价单
                
                logger.info(f"[限价单风控] 客户{customer_uid}净杠杆检查通过: {current_leverage:.2f} <= {max_leverage:.2f}")
            except Exception as e:
                logger.error(f"[限价单风控] 净杠杆检查失败: {e}")
            
            # 获取基础偏移值
            base_offset = float(strategy['min_follow_value'])  # 基础偏移百分比
            logger.info(f"[限价跟单] 信号源订单号: {signal_trade_uid}")
            
            # 计算每个订单的大小（平均分配）
            order_size_per_order = order_size / orders_count
            logger.info(f"[限价跟单] 创建限价单: 订单数量={orders_count}, 总仓位={order_size}, 每单大小={order_size_per_order}, 基础偏移={base_offset}%")
            
            # 创建限价单
            for i in range(orders_count):
                # 计算累积偏移：第i个订单的偏移 = base_offset * (i + 1)
                cumulative_offset = base_offset * (i + 1)
                
                # 计算目标价格
                # 🚀 修复：正确处理正负偏移量
                if pos_side == 'long':
                    # 多头：负偏移表示更低价格（买入），正偏移表示更高价格（买入）
                    target_price = float(signal_price) * (1 - cumulative_offset / 100)
                else:
                    # 空头：负偏移表示更高价格（卖出），正偏移表示更低价格（卖出）
                    target_price = float(signal_price) * (1 + cumulative_offset / 100)
                
                # 创建订单记录
                order_uid = str(uuid.uuid4())
                self.db_pool.execute(
                    """INSERT INTO limit_follow_orders 
                    (order_uid, strategy_id, exchange_order_id, trader_unique_name, customer_uid, 
                        symbol, pos_side, follow_value, target_price, order_size,
                        order_type, status, signal_order_id) 
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                (order_uid, strategy['id'], None, signal_source_uid, 
                strategy['customer_uid'], symbol, pos_side, cumulative_offset, target_price, 
                order_size_per_order, 'limit', 'pending', signal_trade_uid)
            )
                
                logger.info(f"[限价跟单] 创建订单{i+1}: {order_uid} {symbol} {pos_side} @ {target_price} (偏移{cumulative_offset}%, 大小={order_size_per_order})")
            
            logger.info(f"[限价跟单] 完成，共创建 {orders_count} 个限价跟单订单，总仓位={order_size}")
            
        except Exception as e:
            logger.error(f"[限价跟单] 创建限价单失败: {e}")

    async def handle_signal_close(self, signal_source_uid, symbol, pos_side, signal_trade_uid, reduce_ratio=None):
        """处理信号源平仓 - 使用传入的减仓比例"""
        try:
            logger.info(f"[限价跟单] 信号源平仓: {signal_source_uid} {symbol} {pos_side} - 订单号: {signal_trade_uid}")
            
            # 1. 检查是否完全平仓
            remaining_position = await self._get_signal_position(signal_source_uid, symbol, pos_side)
            
            if remaining_position <= 0:
                # 完全平仓 - 撤销所有限价单（强制全部撤单）
                logger.info(f"[限价跟单] 信号源完全平仓，强制撤销所有限价单")
                await self.cancel_limit_follow_orders_on_signal_close(
                    signal_source_uid, symbol, pos_side, None, force_cancel_all=True
                )
                await self._close_all_filled_orders(signal_source_uid, symbol, pos_side)
            else:
                # 部分平仓 - 智能撤单和减仓逻辑
                if signal_trade_uid:
                    # 检查该信号源交易是否完全平仓
                    signal_trade_closed = await self._check_signal_trade_fully_closed(signal_source_uid, signal_trade_uid)
                    
                    if signal_trade_closed:
                        # 该信号源交易完全平仓，撤销跟随该交易的挂单
                        logger.info(f"[限价跟单] 信号源交易 {signal_trade_uid} 完全平仓，撤销跟随该交易的挂单")
                        await self.cancel_limit_follow_orders_on_signal_close(
                            signal_source_uid, symbol, pos_side, None, force_cancel_all=False, signal_trade_uid=signal_trade_uid
                        )
                    else:
                        # 该信号源交易只是部分减仓，不撤销挂单，只进行减仓
                        logger.info(f"[限价跟单] 信号源交易 {signal_trade_uid} 部分减仓，保留挂单，只进行减仓")
                    
                    # 如果有减仓比例，进行减仓操作
                    if reduce_ratio and reduce_ratio > 0:
                        logger.info(f"[限价跟单] 信号源部分平仓，同时进行减仓操作: {reduce_ratio:.2%}")
                        await self._adjust_customer_position_by_ratio(
                            signal_source_uid, symbol, pos_side, reduce_ratio, signal_trade_uid
                        )
                    else:
                        # 没有减仓比例时，进行精确减仓（按信号源交易ID）
                        logger.info(f"[限价跟单] 信号源部分平仓，进行精确减仓操作")
                        await self._adjust_customer_position_by_signal_trade(
                            signal_source_uid, symbol, pos_side, signal_trade_uid, reduce_ratio
                        )
                elif reduce_ratio and reduce_ratio > 0:
                    # 使用传入的减仓比例
                    logger.info(f"[限价跟单] 使用传入的减仓比例: {reduce_ratio:.2%}")
                    await self._adjust_customer_position_by_ratio(
                        signal_source_uid, symbol, pos_side, reduce_ratio, signal_trade_uid
                    )
                else:
                    logger.warning(f"[限价跟单] 未提供减仓比例或交易ID，跳过调整")
                    
        except Exception as e:
            logger.error(f"[限价跟单] 处理信号源平仓失败: {e}")

    async def _check_signal_trade_fully_closed(self, signal_source_uid, signal_trade_uid):
        """检查特定的信号源交易是否完全平仓"""
        try:
            is_demo = get_global_is_demo()
            
            # 查询该信号源交易的状态
            signal_trade = self.db_pool.query(
                "SELECT * FROM signal_account_trades WHERE signal_source_uid=%s AND trade_uid=%s AND is_demo=%s",
                (signal_source_uid, signal_trade_uid, is_demo)
            )
            
            if not signal_trade:
                logger.warning(f"[限价跟单] 未找到信号源交易: {signal_trade_uid}")
                return False
            
            trade = signal_trade[0]
            volume_contract = float(trade.get('volume_contract', 0))
            close_volume_contract = float(trade.get('close_volume_contract', 0))
            
            # 如果已减仓量 >= 原始持仓量，说明完全平仓
            is_fully_closed = close_volume_contract >= volume_contract
            
            logger.info(f"[限价跟单] 信号源交易 {signal_trade_uid} 状态检查: 原始持仓={volume_contract}, 已减仓={close_volume_contract}, 完全平仓={is_fully_closed}")
            
            return is_fully_closed
            
        except Exception as e:
            logger.error(f"[限价跟单] 检查信号源交易状态失败: {e}")
            return False

    async def _handle_limit_follow_close_with_ratio(self, signal_source_uid, symbol, pos_side, signal_trade_uid, reduce_ratio):
        """处理限价跟单平仓（使用预计算的减仓比例）"""
        try:
            logger.info(f"[限价跟单] 信号源平仓: {signal_source_uid} {symbol} {pos_side}")
            
            # 检查是否完全平仓
            remaining_position = await self._get_signal_position(signal_source_uid, symbol, pos_side)
            
            if remaining_position <= 0:
                # 完全平仓 - 撤销所有限价单（强制全部撤单）
                logger.info(f"[限价跟单] 信号源完全平仓，强制撤销所有限价单")
                await self.cancel_limit_follow_orders_on_signal_close(
                    signal_source_uid, symbol, pos_side, None, force_cancel_all=True
                )
                # 平仓已成交的限价单
                logger.info(f"[限价跟单] 开始平仓已成交的限价单")
                await self._close_all_filled_orders(signal_source_uid, symbol, pos_side)
            else:
                # 部分平仓 - 使用预计算的减仓比例
                logger.info(f"[限价跟单] 信号源部分平仓，剩余仓位: {remaining_position}")
                logger.info(f"[限价跟单] 减仓比例: {reduce_ratio:.2%}")
                await self._adjust_customer_position_by_ratio(
                    signal_source_uid, symbol, pos_side, reduce_ratio, signal_trade_uid
                )
                        
        except Exception as e:
            logger.error(f"[限价跟单] 处理信号源平仓失败: {e}")

    async def _adjust_customer_position_by_ratio(self, signal_source_uid, symbol, pos_side, reduce_ratio, signal_trade_uid):
        """按减仓比例调整客户仓位 - 结合净杠杆控制"""
        try:
            logger.info(f"[限价跟单] 按减仓比例调整客户仓位: 减仓比例={reduce_ratio:.2%}")
            
            # 验证减仓比例
            if not reduce_ratio or reduce_ratio <= 0:
                logger.warning(f"[限价跟单] 减仓比例无效: {reduce_ratio}")
                return
            
            # 查询相关策略（支持SPECIFIC模式）
            strategies = self.db_pool.query(
                """SELECT * FROM limit_follow_strategies 
                WHERE trader_unique_name=%s AND enabled=1 
                AND (
                    symbol='ALL' 
                    OR symbol=%s 
                    OR (symbol='SPECIFIC' AND JSON_CONTAINS(symbols, %s))
                )
                AND (pos_side='both' OR pos_side=%s)""",
                (signal_source_uid, symbol, f'"{symbol}"', pos_side)
            )
            
            for strategy in strategies:
                customer_uid = strategy['customer_uid']
                
                # 获取客户当前状态
                current_position = await self._get_customer_position(customer_uid, symbol, pos_side)
                
                # 获取挂单状态
                pending_orders = self.db_pool.query(
                    """SELECT * FROM limit_follow_orders 
                    WHERE customer_uid=%s AND symbol=%s AND pos_side=%s 
                    AND status IN ('pending', 'live')""",
                    (customer_uid, symbol, pos_side)
                )
                
                logger.info(f"[限价跟单] 客户{customer_uid} 当前状态: 已成交={current_position}, 挂单数={len(pending_orders)}")
                
                # 根据三种情况处理
                if current_position <= 0 and not pending_orders:
                    # 情况1: 无持仓无挂单 - 跳过
                    logger.info(f"[限价跟单] 客户{customer_uid} 无持仓无挂单，跳过调整")
                    continue
                    
                elif current_position <= 0 and pending_orders:
                    # 情况2: 无持仓有挂单 - 检查净杠杆，超标则撤单
                    logger.info(f"[限价跟单] 客户{customer_uid} 无持仓有挂单，检查净杠杆控制")
                    await self._check_leverage_and_cancel_orders(strategy, symbol, pos_side)
                    continue
                    
                elif current_position > 0 and not pending_orders:
                    # 情况3: 有持仓无挂单 - 根据策略配置选择减仓方式
                    await self._reduce_customer_position_by_strategy_config(
                        strategy, symbol, pos_side, reduce_ratio, signal_trade_uid
                    )
                        
                elif current_position > 0 and pending_orders:
                    # 情况4: 有持仓有挂单 - 根据策略配置选择减仓方式
                    await self._reduce_customer_position_by_strategy_config(
                        strategy, symbol, pos_side, reduce_ratio, signal_trade_uid
                    )
                    
                    # 减仓后检查净杠杆，超标则撤单
                    logger.info(f"[限价跟单] 客户{customer_uid} 减仓完成，检查净杠杆控制")
                    await self._check_leverage_and_cancel_orders(strategy, symbol, pos_side)

                
                # 新增：检查是否有仓位被完全平掉，撤销相关挂单
                await self._check_and_cancel_fully_closed_positions(customer_uid, symbol, pos_side, reduce_ratio)
                        
        except Exception as e:
            logger.error(f"[限价跟单] 按比例调整仓位失败: {e}")

    async def _check_and_cancel_fully_closed_positions(self, customer_uid, symbol, pos_side, reduce_ratio):
        """检查是否有仓位被完全平掉，撤销相关挂单"""
        try:
            logger.info(f"[限价跟单] 检查客户{customer_uid}是否有仓位被完全平掉")
            
            # 查询客户当前持仓
            current_trades = self.db_pool.query(
                """SELECT * FROM customer_trades 
                WHERE customer_uid=%s AND symbol=%s AND pos_side=%s 
                AND status='open'""",
                (customer_uid, symbol, pos_side)
            )
            
            if not current_trades:
                logger.info(f"[限价跟单] 客户{customer_uid}没有持仓，跳过检查")
                return
            
            # 检查每个持仓是否被完全平掉
            for trade in current_trades:
                trade_uid = trade['trade_uid']
                volume_contract = float(trade['volume_contract'])
                close_volume_contract = safe_float_from_dict(trade, 'close_volume_contract', 0)
                remaining_volume = volume_contract - close_volume_contract
                
                # 如果剩余仓位为0或负数，说明该仓位被完全平掉
                if remaining_volume <= 0:
                    logger.info(f"[限价跟单] 客户{customer_uid}的仓位{trade_uid}被完全平掉，撤销相关挂单")
                    
                    # 查询跟随该仓位的挂单（通过signal_order_id关联）
                    # 这里需要根据您的数据库设计来查询，假设有字段关联
                    related_orders = self.db_pool.query(
                        """SELECT * FROM limit_follow_orders 
                        WHERE customer_uid=%s AND symbol=%s AND pos_side=%s 
                        AND status IN ('pending', 'live')
                        AND signal_order_id IN (
                            SELECT order_id FROM signal_account_trades 
                            WHERE trade_uid=%s
                        )""",
                        (customer_uid, symbol, pos_side, trade_uid)
                    )
                    
                    if related_orders:
                        logger.info(f"[限价跟单] 找到{len(related_orders)}个跟随该仓位的挂单，开始撤销")
                        
                        # 撤销这些挂单
                        for order in related_orders:
                            try:
                                # 调用撤单API
                                await self._cancel_single_limit_order(order)
                                logger.info(f"[限价跟单] 撤销挂单成功: {order['order_uid']}")
                            except Exception as e:
                                logger.error(f"[限价跟单] 撤销挂单失败: {order['order_uid']} - {e}")
                    else:
                        logger.info(f"[限价跟单] 没有找到跟随该仓位的挂单")
                        
        except Exception as e:
            logger.error(f"[限价跟单] 检查完全平掉仓位失败: {e}")

    async def _cancel_single_limit_order(self, order):
        """撤销单个限价单"""
        try:
            # 调用撤单API
            import aiohttp
            import json
            
            api_url = f"http://localhost:5000/api/v1/limit-follow/cancel-on-signal-close"
            payload = {
                'trader_unique_name': order.get('trader_unique_name', ''),
                'symbol': order['symbol'],
                'pos_side': order['pos_side'],
                'order_uid': order['order_uid'],
                'force_cancel_all': False
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.post(api_url, json=payload) as response:
                    if response.status == 200:
                        result = await response.json()
                        logger.info(f"[限价跟单] 撤单API调用成功: {order['order_uid']}")
                    else:
                        logger.warning(f"[限价跟单] 撤单API调用失败: {order['order_uid']} - {response.status}")
                        
        except Exception as e:
            logger.error(f"[限价跟单] 撤销挂单失败: {e}")

    async def _adjust_customer_position_by_signal_trade(self, signal_source_uid, symbol, pos_side, signal_trade_uid, reduce_ratio=None):
        """按信号源交易ID进行精确减仓 - 支持按比例减仓"""
        try:
            logger.info(f"[限价跟单] 按信号源交易进行精确减仓: signal_trade_uid={signal_trade_uid}, reduce_ratio={reduce_ratio}")
            
            # 查询相关策略（支持SPECIFIC模式）
            strategies = self.db_pool.query(
                """SELECT * FROM limit_follow_strategies 
                WHERE trader_unique_name=%s AND enabled=1 
                AND (
                    symbol='ALL' 
                    OR symbol=%s 
                    OR (symbol='SPECIFIC' AND JSON_CONTAINS(symbols, %s))
                )
                AND (pos_side='both' OR pos_side=%s)""",
                (signal_source_uid, symbol, f'"{symbol}"', pos_side)
            )
            
            for strategy in strategies:
                customer_uid = strategy['customer_uid']
                
                # 查询跟随该信号源交易的所有订单（包括已成交和未成交）
                all_orders = self.db_pool.query(
                    """SELECT * FROM limit_follow_orders 
                    WHERE customer_uid=%s AND symbol=%s AND pos_side=%s 
                    AND signal_order_id=%s
                    ORDER BY created_at ASC""",
                    (customer_uid, symbol, pos_side, signal_trade_uid)
                )
                
                if not all_orders:
                    logger.info(f"[限价跟单] 客户{customer_uid} 没有跟随该信号源交易的订单")
                    continue
                
                # 分离已成交和未成交订单
                filled_orders = [order for order in all_orders if order['status'] == 'filled']
                pending_orders = [order for order in all_orders if order['status'] in ['pending', 'live']]
                
                logger.info(f"[限价跟单] 客户{customer_uid} 跟随该交易的订单: 已成交={len(filled_orders)}个, 未成交={len(pending_orders)}个")
                
                # 计算需要减仓的总量
                if reduce_ratio and reduce_ratio > 0:
                    # 按比例减仓：基于客户当前总持仓计算减仓量
                    current_position = await self._get_customer_position(customer_uid, symbol, pos_side)
                    reduce_amount = current_position * reduce_ratio
                    logger.info(f"[限价跟单] 客户{customer_uid} 按比例减仓: 当前持仓={current_position}, 减仓比例={reduce_ratio:.2%}, 减仓量={reduce_amount}")
                else:
                    # 精确减仓：基于已成交订单计算减仓量
                    reduce_amount = sum(float(order['order_size']) for order in filled_orders)
                    logger.info(f"[限价跟单] 客户{customer_uid} 精确减仓: 跟随该交易的已成交总量={reduce_amount}")
                
                # 如果有减仓量，进行FIFO减仓
                if reduce_amount > 0:
                    await self._reduce_customer_position_fifo(
                        strategy, symbol, pos_side, reduce_amount, signal_trade_uid
                    )
                
                # 如果有未成交订单，记录日志（这些订单应该已经被撤销了）
                if pending_orders:
                    total_pending = sum(float(order['order_size']) for order in pending_orders)
                    logger.info(f"[限价跟单] 客户{customer_uid} 跟随该交易的未成交总量: {total_pending} (应该已被撤销)")
                    
        except Exception as e:
            logger.error(f"[限价跟单] 按信号源交易减仓失败: {e}")

    async def _reduce_customer_position_fifo(self, strategy, symbol, pos_side, reduce_amount, signal_trade_uid):
        """按FIFO方式减仓客户仓位"""
        try:
            customer_uid = strategy['customer_uid']
            logger.info(f"[限价跟单] 客户{customer_uid} FIFO减仓: {reduce_amount}")
            
            # 查询客户当前持仓（按时间正序，最早的先减）
            current_trades = self.db_pool.query(
                """SELECT * FROM customer_trades 
                WHERE customer_uid=%s AND symbol=%s AND pos_side=%s 
                AND status='open' AND close_volume_contract < volume_contract
                ORDER BY created_at ASC""",
                (customer_uid, symbol, pos_side)
            )
            
            if not current_trades:
                logger.info(f"[限价跟单] 客户{customer_uid} 没有可减仓的持仓")
                return
            
            remaining_reduce = reduce_amount
            logger.info(f"[限价跟单] 客户{customer_uid} 开始FIFO减仓，目标减仓量: {remaining_reduce}")
            
            # 记录减仓前的总持仓
            total_position_before = sum(
                float(trade['volume_contract']) - safe_float_from_dict(trade, 'close_volume_contract', 0)
                for trade in current_trades
            )
            logger.info(f"[限价跟单] 客户{customer_uid} 减仓前总持仓: {total_position_before}")
            
            for trade in current_trades:
                if remaining_reduce <= 0:
                    break
                    
                trade_uid = trade['trade_uid']
                current_volume = float(trade['volume_contract'])
                closed_volume = safe_float_from_dict(trade, 'close_volume_contract', 0)
                available_volume = current_volume - closed_volume
                
                if available_volume <= 0:
                    continue
                
                # 计算本次减仓量
                reduce_this_trade = min(remaining_reduce, available_volume)
                
                logger.info(f"[限价跟单] 减仓交易 {trade_uid}: 当前={available_volume}, 减仓={reduce_this_trade}")
                
                # 执行减仓
                await self._execute_position_reduction(
                    trade_uid, reduce_this_trade, signal_trade_uid
                )
                
                remaining_reduce -= reduce_this_trade
                logger.info(f"[限价跟单] 剩余减仓量: {remaining_reduce}")
            
            # 记录减仓后的总持仓
            current_trades_after = self.db_pool.query(
                """SELECT * FROM customer_trades 
                WHERE customer_uid=%s AND symbol=%s AND pos_side=%s 
                AND status='open'""",
                (customer_uid, symbol, pos_side)
            )
            total_position_after = sum(
                float(trade['volume_contract']) - safe_float_from_dict(trade, 'close_volume_contract', 0)
                for trade in current_trades_after
            )
            
            actual_reduced = total_position_before - total_position_after
            logger.info(f"[限价跟单] 客户{customer_uid} 减仓完成: 减仓前={total_position_before}, 减仓后={total_position_after}, 实际减仓={actual_reduced}")
            
            if remaining_reduce > 0:
                logger.warning(f"[限价跟单] 客户{customer_uid} 减仓未完成，剩余: {remaining_reduce}")
            else:
                logger.info(f"[限价跟单] 客户{customer_uid} FIFO减仓完成")
                
        except Exception as e:
            logger.error(f"[限价跟单] FIFO减仓失败: {e}")

    async def _execute_position_reduction(self, trade_uid, reduce_amount, signal_trade_uid):
        """执行仓位减仓"""
        try:
            # 更新数据库中的减仓量
            self.db_pool.execute(
                """UPDATE customer_trades 
                SET close_volume_contract = close_volume_contract + %s 
                WHERE trade_uid=%s""",
                (reduce_amount, trade_uid)
            )
            
            logger.info(f"[限价跟单] 交易 {trade_uid} 减仓 {reduce_amount} 完成")
            
        except Exception as e:
            logger.error(f"[限价跟单] 执行减仓失败: {e}")

    async def _check_leverage_and_cancel_orders(self, strategy, symbol, pos_side):
        """检查净杠杆并撤单 - 集成到减平仓逻辑中"""
        try:
            customer_uid = strategy['customer_uid']
            max_leverage = float(strategy.get('max_net_leverage', 10.0))
            
            logger.info(f"[限价跟单] 检查客户{customer_uid}净杠杆控制，最大杠杆: {max_leverage}")
            
            # 获取客户配置
            customer_config = get_customer_limit_follow_config(customer_uid)
            if not customer_config or 'customer_info' not in customer_config:
                logger.warning(f"[限价跟单] 客户{customer_uid}配置不存在，跳过净杠杆检查")
                return
            
            customer_info = customer_config['customer_info']
            
            # 创建REST客户端
            from trade_service import get_global_is_demo
            rest_client = OKXRESTClient(
                api_key=customer_info['api_key'],
                api_secret=customer_info['api_secret'],
                passphrase=customer_info['passphrase'],
                is_demo=customer_info.get('is_demo', False)
            )
            
            # 计算当前净杠杆
            current_leverage = await self._calculate_net_leverage_for_customer(
                customer_uid, symbol, pos_side, rest_client
            )
            
            logger.info(f"[限价跟单] 客户{customer_uid}当前净杠杆: {current_leverage:.2f}, 最大杠杆: {max_leverage}")
            
            # 如果净杠杆超标，按时间顺序撤单
            if current_leverage > max_leverage:
                logger.warning(f"[限价跟单] 客户{customer_uid}净杠杆超标，开始按时间顺序撤单")
                await self._cancel_orders_by_leverage_control(strategy, symbol, pos_side, rest_client, max_leverage)
            else:
                logger.info(f"[限价跟单] 客户{customer_uid}净杠杆正常，无需撤单")
                
        except Exception as e:
            logger.error(f"[限价跟单] 检查净杠杆并撤单失败: {e}")

    async def _calculate_net_leverage_for_customer(self, customer_uid, symbol, pos_side, rest_client):
        """计算客户净杠杆（简化版，复用api_server.py中的逻辑）"""
        try:
            import asyncio
            
            # 1. 获取账户信息
            account_info = await rest_client.get_account_info()
            if not account_info or account_info.get('code') != '0':
                logger.warning(f"[净杠杆计算] 获取账户信息失败")
                return 0.0
            
            # 获取账户总权益（USDT）
            total_equity = 0.0
            for detail in account_info.get('data', []):
                for detail_item in detail.get('details', []):
                    if detail_item.get('ccy') == 'USDT':
                        total_equity = float(detail_item.get('eq', 0))
                        break
            
            if total_equity <= 0:
                logger.warning(f"[净杠杆计算] 账户总权益为0")
                return 0.0
            
            # 2. 获取持仓信息
            positions_response = await rest_client.get_positions()
            if not positions_response or positions_response.get('code') != '0':
                logger.warning(f"[净杠杆计算] 获取持仓信息失败")
                positions = []
            else:
                positions = positions_response.get('data', [])
            
            # 3. 计算持仓价值
            position_value = 0.0
            for pos in positions:
                pos_inst_id = pos.get('instId', '')
                pos_pos_side = pos.get('posSide', '')
                pos_size = float(pos.get('pos', 0))
                
                # 过滤：如果指定了symbol，只计算该symbol；如果指定了pos_side，只计算该方向
                if symbol != 'ALL' and pos_inst_id != symbol:
                    continue
                if pos_side != 'both' and pos_pos_side != pos_side:
                    continue
                
                if pos_size > 0:
                    # 计算持仓价值 = 持仓数量 * 合约面值（USDT）
                    contract_value = get_contract_value_in_usdt(pos_inst_id, pos_size)
                    position_value += contract_value
            
            # 4. 获取挂单信息
            if symbol == 'ALL':
                # 查询所有挂单
                pending_orders = self.db_pool.query(
                    """SELECT * FROM limit_follow_orders 
                       WHERE customer_uid=%s AND status IN ('pending', 'live')""",
                    (customer_uid,)
                )
            else:
                # 查询指定交易对的挂单
                pending_orders = self.db_pool.query(
                    """SELECT * FROM limit_follow_orders 
                       WHERE customer_uid=%s AND symbol=%s AND status IN ('pending', 'live')""",
                    (customer_uid, symbol)
                )
            
            # 5. 计算挂单价值
            pending_value = 0.0
            for order in pending_orders:
                order_symbol = order['symbol']
                order_pos_side = order['pos_side']
                order_size = float(order.get('order_size', 0))
                
                # 过滤：如果指定了pos_side，只计算该方向
                if pos_side != 'both' and order_pos_side != pos_side:
                    continue
                
                if order_size > 0:
                    # 计算挂单价值 = 挂单数量 * 合约面值（USDT）
                    order_value = get_contract_value_in_usdt(order_symbol, order_size)
                    pending_value += order_value
            
            # 6. 计算净杠杆
            total_value = position_value + pending_value
            net_leverage = total_value / total_equity if total_equity > 0 else 0.0
            
            logger.info(f"[净杠杆计算] 客户{customer_uid}: 账户权益={total_equity:.2f} USDT, "
                       f"持仓价值={position_value:.2f} USDT, 挂单价值={pending_value:.2f} USDT, "
                       f"总价值={total_value:.2f} USDT, 净杠杆={net_leverage:.2f}")
            
            return net_leverage
            
        except Exception as e:
            logger.error(f"[净杠杆计算] 计算客户净杠杆失败: {e}")
            return 0.0

    async def _cancel_orders_by_leverage_control(self, strategy, symbol, pos_side, rest_client, max_leverage):
        """按净杠杆控制撤单"""
        try:
            customer_uid = strategy['customer_uid']
            
            # 查询待撤销订单，按创建时间正序排列（最早的先撤）
            orders = self.db_pool.query(
                """SELECT * FROM limit_follow_orders 
                   WHERE strategy_id=%s AND pos_side=%s AND status IN ('pending', 'live')
                   ORDER BY created_at ASC""",
                (strategy['id'], pos_side)
            )
            
            if not orders:
                logger.info(f"[撤单] 没有需要撤销的订单: strategy_id={strategy['id']}, pos_side={pos_side}")
                return
            
            logger.info(f"[撤单] 净杠杆控制模式：找到 {len(orders)} 个待撤销订单，按时间顺序撤单直到净杠杆达标")
            
            canceled_count = 0
            for order in orders:
                # 1. 计算当前净杠杆（使用订单的客户UID）
                order_customer_uid = order['customer_uid']
                
                # 为每个订单创建对应的REST客户端
                try:
                    # 获取订单客户的API凭证
                    customer_data = self.db_pool.query(
                        "SELECT api_key, api_secret, passphrase FROM customers WHERE customer_uid=%s",
                        (order_customer_uid,)
                    )
                    
                    if not customer_data:
                        logger.warning(f"[撤单] 客户{order_customer_uid}配置不存在，跳过撤单: {order['order_uid']}")
                        continue
                    
                    from trade_service import get_global_is_demo
                    order_rest_client = OKXRESTClient(
                        customer_data[0]['api_key'],
                        customer_data[0]['api_secret'],
                        customer_data[0]['passphrase'],
                        is_demo=get_global_is_demo()
                    )
                    
                except Exception as e:
                    logger.error(f"[撤单] 创建客户{order_customer_uid}的REST客户端失败: {e}")
                    continue
                
                current_leverage = await self._calculate_net_leverage_for_customer(
                    order_customer_uid, symbol, pos_side, order_rest_client
                )
                
                logger.info(f"[撤单] 当前净杠杆: {current_leverage:.2f}, 最大杠杆: {max_leverage}")
                
                # 2. 如果净杠杆已经不超过上限，停止撤单
                if current_leverage <= max_leverage:
                    logger.info(f"[撤单] 净杠杆已在控制范围内，停止撤单。已撤销: {canceled_count} 个，剩余: {len(orders) - canceled_count} 个")
                    break
                
                # 3. 净杠杆超过上限，继续撤单
                inst_id = order['symbol']
                exchange_order_id = order['exchange_order_id']
                
                if not exchange_order_id:
                    logger.warning(f"[撤单] 订单没有交易所ID，跳过: {order['order_uid']}")
                    continue
                
                # 调用交易所API撤销
                logger.info(f"[撤单] 调用REST API撤单: instId={inst_id}, ordId={exchange_order_id}, customer={order_customer_uid}")
                cancel_result = await order_rest_client.cancel_order(inst_id, ordId=exchange_order_id)
                
                if cancel_result and cancel_result.get('code') == '0':
                    # 更新数据库状态
                    self.db_pool.execute(
                        "UPDATE limit_follow_orders SET status='canceled', updated_at=NOW() WHERE order_uid=%s",
                        (order['order_uid'],)
                    )
                    canceled_count += 1
                    logger.info(f"[撤单] 订单撤销成功: {order['order_uid']} (第{canceled_count}/{len(orders)}个)")
                else:
                    error_msg = cancel_result.get('msg', '未知错误') if cancel_result else '请求失败'
                    logger.warning(f"[撤单] 订单撤销失败: {order['order_uid']} - {error_msg}")
            
            logger.info(f"[撤单] 净杠杆控制：撤单完成，共撤销: {canceled_count}/{len(orders)} 个订单")
            
        except Exception as e:
            logger.error(f"[撤单] 按净杠杆控制撤单失败: {e}")

    async def _reduce_limit_orders_by_ratio(self, strategy, symbol, pos_side, reduce_ratio, signal_order_id=None):
        """按比例减少限价挂单"""
        try:
            logger.info(f"[限价跟单] 按比例减少限价挂单: 减仓比例={reduce_ratio:.2%}")
            
            # 获取当前挂单
            pending_orders = self.db_pool.query(
                """SELECT * FROM limit_follow_orders 
                WHERE strategy_id=%s AND symbol=%s AND pos_side=%s 
                AND status IN ('pending', 'live')
                ORDER BY created_at ASC, id ASC""",
                (strategy['id'], symbol, pos_side)
            )
            
            if not pending_orders:
                logger.info(f"[限价跟单] 没有可减少的挂单")
                return
            
            # 计算需要减少的总量
            total_pending = sum(float(order['order_size']) for order in pending_orders)
            need_reduce = total_pending * reduce_ratio
            
            if need_reduce <= 0:
                logger.info(f"[限价跟单] 无需减少挂单")
                return
            
            # 按FIFO顺序减少挂单
            reduced_amount = 0
            for order in pending_orders:
                if reduced_amount >= need_reduce:
                    break
                    
                order_size = float(order['order_size'])
                reduce_amount = min(order_size, need_reduce - reduced_amount)
                
                if reduce_amount >= order_size:
                    # 完全撤销这个订单
                    self.db_pool.execute(
                        "UPDATE limit_follow_orders SET status='canceled', updated_at=NOW() WHERE order_uid=%s",
                        (order['order_uid'],)
                    )
                    logger.info(f"[限价跟单] 完全撤销挂单: {order['order_uid']}")
                else:
                    # 部分减少订单数量
                    remaining_size = order_size - reduce_amount
                    self.db_pool.execute(
                        "UPDATE limit_follow_orders SET order_size=%s, updated_at=NOW() WHERE order_uid=%s",
                        (remaining_size, order['order_uid'])
                    )
                    logger.info(f"[限价跟单] 部分减少挂单: {order['order_uid']}, 从{order_size}减少到{remaining_size}")
                
                reduced_amount += reduce_amount
            
            logger.info(f"[限价跟单] 挂单减仓完成: 总挂单={total_pending}, 减少={reduced_amount}")
            
        except Exception as e:
            logger.error(f"[限价跟单] 按比例减少挂单失败: {e}")

    async def _close_all_filled_orders(self, signal_source_uid, symbol, pos_side, signal_trade_uid=None):
        """平仓所有已成交的限价单"""
        try:
            logger.info(f"[限价跟单] 开始平仓所有已成交订单: {signal_source_uid} {symbol} {pos_side}")
            
            # 查询相关策略（支持SPECIFIC模式）
            strategies = self.db_pool.query(
                """SELECT * FROM limit_follow_strategies
                WHERE trader_unique_name=%s AND enabled=1 
                AND (
                    symbol='ALL' 
                    OR symbol=%s 
                    OR (symbol='SPECIFIC' AND JSON_CONTAINS(symbols, %s))
                )
                AND (pos_side='both' OR pos_side=%s)""",
                (signal_source_uid, symbol, f'"{symbol}"', pos_side)
            )
            
            total_closed = 0.0
            for strategy in strategies:
                # 查询该策略下已成交的限价单
                filled_orders = self.db_pool.query(
                    """SELECT * FROM limit_follow_orders
                    WHERE strategy_id=%s AND symbol=%s AND pos_side=%s
                    AND status='filled'
                    ORDER BY created_at ASC""",
                    (strategy['id'], symbol, pos_side)
                )
                
                if filled_orders:
                    logger.info(f"[限价跟单] 策略 {strategy['id']} 有 {len(filled_orders)} 个已成交订单需要平仓")
                    
                    # 计算总需要平仓的数量
                    total_need_close = sum(float(order['order_size']) for order in filled_orders)
                    
                    # 调用平仓方法
                    closed = await self._close_filled_orders(strategy, symbol, pos_side, total_need_close)
                    total_closed += closed
                    
                    logger.info(f"[限价跟单] 策略 {strategy['id']} 平仓完成，平仓数量: {closed}")
                else:
                    logger.info(f"[限价跟单] 策略 {strategy['id']} 没有已成交订单")
            
            logger.info(f"[限价跟单] 所有已成交订单平仓完成，总平仓数量: {total_closed}")
            return total_closed
            
        except Exception as e:
            logger.error(f"[限价跟单] 平仓所有已成交订单失败: {e}")
            return 0

    async def _reduce_customer_position(self, strategy, symbol, pos_side, need_reduce):
        """减少客户仓位 - FIFO方式按比例减仓"""
        try:
            logger.info(f"[限价跟单] 开始减少客户仓位: 策略ID={strategy['id']}, 需要减少={need_reduce}")
            
            # 获取所有已成交的限价单订单（按创建时间排序，FIFO）
            filled_orders = self.db_pool.query(
                """SELECT * FROM limit_follow_orders 
                WHERE strategy_id=%s AND symbol=%s AND pos_side=%s 
                AND status='filled' AND order_size > 0
                ORDER BY created_at ASC, id ASC""",
                (strategy['id'], symbol, pos_side)
            )
            
            if not filled_orders:
                logger.info(f"[限价跟单] 没有已成交的限价单")
                return
            
            # 计算总持仓量
            # 计算总持仓量（使用数据库中的实际数量，考虑精度调整）
            total_position = 0.0
            for order in filled_orders:
                order_size = float(order['order_size'])
                current_reduced = float(order.get('limit_close_size', 0) or 0)
                available_size = order_size - current_reduced
                total_position += available_size

            if total_position <= 0:
                logger.info(f"[限价跟单] 总持仓量为0")
                return
            
            # 计算减仓比例
            reduce_ratio = need_reduce / total_position
            logger.info(f"[限价跟单] 减仓比例: {reduce_ratio:.2%}, 总持仓={total_position}, 需要减仓={need_reduce}")
            
            # 按FIFO顺序减仓每个限价单订单
            remaining_reduce = need_reduce
            
            for order in filled_orders:
                if remaining_reduce <= 0:
                    break
                    
                order_uid = order['order_uid']
                order_size = float(order['order_size'])
                
                # 获取已减仓数量
                current_reduced = float(order.get('limit_close_size', 0) or 0)
                available_size = order_size - current_reduced  # 剩余可减仓量
                
                if available_size <= 0:
                    logger.info(f"[限价跟单] 订单{order_uid}已完全减仓，跳过")
                    continue
                
                # 计算这个订单需要减仓的量
                order_reduce = min(remaining_reduce, available_size)
                
                if order_reduce > 0:
                    logger.info(f"[限价跟单] 订单{order_uid}: 总持仓={order_size}, 已减仓={current_reduced}, 剩余可减仓={available_size}, 本次减仓={order_reduce}")
                    
                    # 调用修改后的_close_filled_orders方法，传递单个订单和减仓量
                    actual_closed = await self._close_filled_orders(
                        strategy, symbol, pos_side, 
                        need_close=order_reduce, 
                        order_uid=order_uid, 
                        reduce_volume=order_reduce
                    )
                    
                    # 使用实际平仓数量更新剩余需要减仓的量
                    remaining_reduce -= actual_closed
                    
                    # 检查是否完全减仓
                    new_reduced = current_reduced + actual_closed
                    if new_reduced >= order_size:
                        logger.info(f"[限价跟单] 订单{order_uid}完全减仓")
                    else:
                        logger.info(f"[限价跟单] 订单{order_uid}部分减仓: {new_reduced}/{order_size}")
            
            logger.info(f"[限价跟单] FIFO减仓完成，剩余需要减仓: {remaining_reduce}")
            
        except Exception as e:
            logger.error(f"[限价跟单] 减少客户仓位失败: {e}")

    async def _close_filled_orders(self, strategy, symbol, pos_side, need_close, signal_trade_uid=None, order_uid=None, reduce_volume=None):
        """平已成交订单 - FIFO，支持按指定量减仓或按订单减仓"""
        try:
            logger.info(f"[限价跟单] 开始平已成交订单: 策略ID={strategy['id']}, 需要平仓={need_close}")
            
            # 如果指定了单个订单，只处理该订单
            if order_uid:
                filled_orders = self.db_pool.query(
                    """SELECT * FROM limit_follow_orders 
                    WHERE order_uid=%s AND status='filled'""",
                    (order_uid,)
                )
            elif signal_trade_uid:
                filled_orders = self.db_pool.query(
                    """SELECT * FROM limit_follow_orders 
                    WHERE status='filled' AND signal_order_id=%s
                    ORDER BY created_at ASC""",
                    (signal_trade_uid,)
                )
            else:
                filled_orders = self.db_pool.query(
                    """SELECT * FROM limit_follow_orders 
                    WHERE status='filled' AND strategy_id=%s AND symbol=%s AND pos_side=%s
                    ORDER BY created_at ASC""",
                    (strategy['id'], symbol, pos_side)
                )
            
            if not filled_orders:
                logger.info(f"[限价跟单] 没有已成交的限价单需要平仓")
                return 0
            
            closed = 0.0
            # 调用API接口平仓限价跟单订单
            import aiohttp
            import json
            
            api_url = f"http://localhost:5000/api/v1/limit-follow/limit-follow-closed-by-order-id"
            
            for order in filled_orders:
                if closed >= need_close:
                    break
                    
                try:
                    # 计算这个订单需要平仓的量
                    order_size = float(order['order_size'])
                    current_reduced = float(order.get('limit_close_size', 0) or 0)
                    available_size = order_size - current_reduced
                    
                    if available_size <= 0:
                        logger.info(f"[限价跟单] 订单{order['order_uid']}已完全减仓，跳过")
                        continue
                    
                    # 计算本次平仓量
                    if reduce_volume is not None:
                        # 按指定量减仓
                        close_amount = min(reduce_volume, available_size)
                    else:
                        # 按需要平仓量减仓
                        close_amount = min(need_close - closed, available_size)
                    
                    # 对平仓量进行精度调整
                    adjusted_close_amount = await self._adjust_order_size_precision(symbol, close_amount)
                    
                    payload = {
                        'order_uid': order['order_uid'],
                        'reduce_volume': adjusted_close_amount  # 传递调整后的减仓量
                    }
                    
                    async with aiohttp.ClientSession() as session:
                        async with session.post(api_url, json=payload) as response:
                            if response.status == 200:
                                result = await response.json()
                                if result.get('success') == 200:
                                    # 使用调整后的数量更新closed计数
                                    closed += adjusted_close_amount
                                    logger.info(f"[限价跟单] 平仓成功: {order['order_uid']}, 数量: {adjusted_close_amount}")
                                    
                                    # 注意：数据库更新由API接口处理，这里不需要重复更新
                                    
                                else:
                                    logger.warning(f"[限价跟单] 平仓失败: {order['order_uid']}, 原因: {result.get('message')}")
                            else:
                                logger.error(f"[限价跟单] API请求失败: {response.status}")
                                
                except Exception as e:
                    logger.error(f"[限价跟单] 平仓订单异常: {order['order_uid']}, 错误: {e}")
                    continue
            
            logger.info(f"[限价跟单] 平仓完成，共平仓: {closed}")
            return closed
            
        except Exception as e:
            logger.error(f"[限价跟单] 平已成交订单失败: {e}")
            return 0

    async def _increase_customer_position(self, strategy, signal_source_uid, symbol, pos_side, need_increase, signal_trade_uid):
        """增加客户仓位"""
        try:
            # 获取当前信号价格
            latest_trade = self.db_pool.query(
                """SELECT close_px FROM signal_account_trades 
                WHERE signal_source_uid=%s AND symbol=%s AND pos_side=%s 
                ORDER BY created_at DESC LIMIT 1""",
                (signal_source_uid, symbol, pos_side)
            )
            
            if not latest_trade:
                logger.warning(f"[限价跟单] 无法获取信号价格: {signal_source_uid} {symbol} {pos_side}")
                return
            
            signal_price = float(latest_trade[0]['close_px'])
            
            # 计算每个限价单的数量
            orders_per_signal = strategy['max_orders_per_signal']
            order_size = need_increase / orders_per_signal
            
            # 创建新的限价单
            await self._create_limit_orders(
                strategy, signal_source_uid, symbol, pos_side, 
                signal_price, order_size, orders_per_signal, signal_trade_uid
            )
            
        except Exception as e:
            logger.error(f"[限价跟单] 增加客户仓位失败: {e}")

    # 保留原有的撤单函数
    async def cancel_limit_follow_orders_on_signal_close(self, signal_source_uid, symbol, pos_side, order_uid=None, force_cancel_all=False, signal_trade_uid=None):
        """信号源平仓时取消相关限价跟单订单
        
        Args:
            signal_source_uid: 信号源ID
            symbol: 交易对
            pos_side: 持仓方向
            order_uid: 指定订单ID（可选），如果为None则批量撤销
            force_cancel_all: 是否强制全部撤单（信号全平时为True）
            signal_trade_uid: 信号源交易ID（可选），用于精确撤单
        """
        try:
            if force_cancel_all:
                logger.info(f"[限价跟单撤单] 信号源完全平仓，强制撤销所有限价跟单: {signal_source_uid} {symbol} {pos_side}")
            elif signal_trade_uid:
                logger.info(f"[限价跟单撤单] 信号源部分平仓，撤销跟随交易 {signal_trade_uid} 的挂单: {signal_source_uid} {symbol} {pos_side}")
            else:
                logger.info(f"[限价跟单撤单] 信号源部分平仓，按净杠杆控制撤单: {signal_source_uid} {symbol} {pos_side}")
            
            # 调用API接口取消限价跟单订单
            import aiohttp
            import json
            
            api_url = f"http://localhost:5000/api/v1/limit-follow/cancel-on-signal-close"
            payload = {
                'trader_unique_name': signal_source_uid,
                'symbol': symbol,
                'pos_side': pos_side,
                'force_cancel_all': force_cancel_all
            }
            
            # 如果指定了订单ID，添加到payload中
            if order_uid:
                payload['order_uid'] = order_uid
            
            # 如果指定了信号源交易ID，添加到payload中
            if signal_trade_uid:
                payload['signal_trade_uid'] = signal_trade_uid
            
            async with aiohttp.ClientSession() as session:
                async with session.post(api_url, json=payload) as response:
                    if response.status == 200:
                        result = await response.json()
                        if result.get('success') == 200:
                            logger.info(f"[限价跟单撤单] 撤单成功: {result.get('message')}")
                            return result.get('data', {}).get('canceled_count', 0)
                        else:
                            logger.warning(f"[限价跟单撤单] 撤单失败: {result.get('message')}")
                            return 0
                    else:
                        logger.error(f"[限价跟单撤单] API请求失败: {response.status}")
                        return 0
                            
        except Exception as e:
            logger.error(f"[限价跟单撤单] 取消限价跟单失败: {e}")
            return 0

    # ==================== 信号丢失检测和补全模块 ====================
    
    async def _find_closed_positions(self, exchange_positions, local_positions):
        """找出已平仓但本地未更新的持仓（平仓信号丢失）"""
        try:
            closed_positions = []
            
            # 将交易所持仓转换为字典，方便查找
            exchange_positions_dict = {}
            for pos in exchange_positions:
                key = f"{pos['symbol']}_{pos['pos_side']}"
                exchange_positions_dict[key] = pos
            
            # 检查本地持仓是否在交易所还存在
            for local_pos in local_positions:
                key = f"{local_pos['symbol']}_{local_pos['pos_side']}"
                
                if key not in exchange_positions_dict:
                    # 本地有记录，但交易所没有，说明已经平仓
                    closed_positions.append(local_pos)
                    logger.warning(f"[仓位同步检查] 发现已平仓持仓（平仓信号丢失）: {local_pos['symbol']} {local_pos['pos_side']} {local_pos['volume_contract']}张")
            
            return closed_positions
            
        except Exception as e:
            logger.error(f"[仓位同步检查] 查找已平仓持仓失败: {e}")
            return []

    async def _find_reduced_positions(self, exchange_positions, local_positions):
        """找出已减仓但本地未更新的持仓（减仓信号丢失）"""
        try:
            reduced_positions = []
            
            # 按币种和方向分组计算总持仓量
            local_total_by_symbol = {}
            for local_pos in local_positions:
                key = f"{local_pos['symbol']}_{local_pos['pos_side']}"
                if key not in local_total_by_symbol:
                    local_total_by_symbol[key] = {
                        'symbol': local_pos['symbol'],
                        'pos_side': local_pos['pos_side'],
                        'total_size': 0,
                        'positions': []
                    }
                
                local_size = float(local_pos.get('volume_contract', 0))
                local_total_by_symbol[key]['total_size'] += local_size
                local_total_by_symbol[key]['positions'].append(local_pos)
            
            # 将交易所持仓转换为字典，方便查找
            exchange_positions_dict = {}
            for pos in exchange_positions:
                key = f"{pos['symbol']}_{pos['pos_side']}"
                if key not in exchange_positions_dict:
                    exchange_positions_dict[key] = {
                        'symbol': pos['symbol'],
                        'pos_side': pos['pos_side'],
                        'total_size': 0
                    }
                exchange_positions_dict[key]['total_size'] += float(pos.get('size', 0))
            
            # 检查每个币种和方向的总持仓量
            for key, local_info in local_total_by_symbol.items():
                symbol = local_info['symbol']
                pos_side = local_info['pos_side']
                local_total_size = safe_float(local_info['total_size'], 3)
                
                if key in exchange_positions_dict:
                    exchange_total_size = exchange_positions_dict[key]['total_size']
                    
                    logger.info(f"[仓位同步检查] 比较总持仓: {symbol} {pos_side} 本地总计{local_total_size}张 vs 交易所总计{exchange_total_size}张")
                    
                    if exchange_total_size < local_total_size:
                        # 交易所总持仓量小于本地总记录，说明发生了减仓
                        reduced_amount = local_total_size - exchange_total_size
                        
                        # 为每个本地持仓创建减仓记录（用于FIFO处理）
                        for local_pos in local_info['positions']:
                            reduced_positions.append({
                                'symbol': symbol,
                                'pos_side': pos_side,
                                'local_size': float(local_pos.get('volume_contract', 0)),
                                'exchange_size': exchange_total_size,  # 交易所总持仓
                                'reduced_amount': reduced_amount,  # 总减仓量
                                'trade_uid': local_pos.get('trade_uid'),
                                'open_px': local_pos.get('open_px'),
                                'total_local_size': local_total_size,
                                'total_exchange_size': exchange_total_size
                            })
                        
                        logger.warning(f"[仓位同步检查] 发现已减仓持仓（减仓信号丢失）: {symbol} {pos_side} 本地总计{local_total_size}张 -> 交易所总计{exchange_total_size}张，减仓{reduced_amount}张")
                else:
                    # 交易所没有该币种和方向的持仓，说明全部平仓
                    logger.warning(f"[仓位同步检查] 发现已平仓持仓（平仓信号丢失）: {symbol} {pos_side} 本地总计{local_total_size}张 -> 交易所0张")
            
            return reduced_positions
            
        except Exception as e:
            logger.error(f"[仓位同步检查] 查找已减仓持仓失败: {e}")
            return []

    async def _handle_closed_positions(self, signal_source, closed_positions):
        """处理已平仓的持仓 - 补全丢失的平仓信号"""
        try:
            source_uid = signal_source.source_uid if hasattr(signal_source, 'source_uid') else signal_source.get('source_uid', 'unknown')
            source_name = signal_source.name if hasattr(signal_source, 'name') else signal_source.get('name', '未知')
            
            logger.info(f"[平仓信号补全] 开始处理 {len(closed_positions)} 个已平仓持仓")
            
            # 发送钉钉告警
            alert_message = f"🚨 信号源平仓信号丢失警报\n\n" \
                           f"信号源: {source_name} ({source_uid})\n" \
                           f"异常原因: 发现 {len(closed_positions)} 个平仓信号丢失\n" \
                           f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n" \
                           f"⚠️ 正在自动补全平仓信号..."
            
            if should_send_alert_notification("warning"):
                alert_info = {
                    'title': '信号源平仓信号丢失',
                    'level': 'warning',
                    'time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                    'message': f"信号源 {source_uid} 发现 {len(closed_positions)} 个平仓信号丢失",
                    'account': source_uid,
                    'strategy': '仓位同步检查',
                    'symbol': ', '.join([pos['symbol'] for pos in closed_positions]),
                    'suggestion': '系统正在自动补全平仓信号'
                }
                await send_alert_notification_async("warning", alert_info)
            
            # 处理每个已平仓的持仓
            for closed_pos in closed_positions:
                await self._fix_closed_position(signal_source, closed_pos)
                
            logger.info(f"[平仓信号补全] 信号源 {source_uid} 平仓信号补全完成")
            
        except Exception as e:
            logger.error(f"[平仓信号补全] 处理已平仓持仓失败: {e}")

    async def _handle_reduced_positions(self, signal_source, reduced_positions):
        """处理已减仓的持仓 - 补全丢失的减仓信号"""
        try:
            source_uid = signal_source.source_uid if hasattr(signal_source, 'source_uid') else signal_source.get('source_uid', 'unknown')
            source_name = signal_source.name if hasattr(signal_source, 'name') else signal_source.get('name', '未知')
            
            logger.info(f"[减仓信号补全] 开始处理 {len(reduced_positions)} 个已减仓持仓")
            
            # 发送钉钉告警
            alert_message = f"🚨 信号源减仓信号丢失警报\n\n" \
                           f"信号源: {source_name} ({source_uid})\n" \
                           f"异常原因: 发现 {len(reduced_positions)} 个减仓信号丢失\n" \
                           f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n" \
                           f"⚠️ 正在自动补全减仓信号..."
            
            if should_send_alert_notification("warning"):
                alert_info = {
                    'title': '信号源减仓信号丢失',
                    'level': 'warning',
                    'time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                    'message': f"信号源 {source_uid} 发现 {len(reduced_positions)} 个减仓信号丢失",
                    'account': source_uid,
                    'strategy': '仓位同步检查',
                    'symbol': ', '.join([pos['symbol'] for pos in reduced_positions]),
                    'suggestion': '系统正在自动补全减仓信号'
                }
                await send_alert_notification_async("warning", alert_info)
            
            # 按币种和方向分组，避免重复触发客户减仓
            reduced_by_symbol = {}
            for reduced_pos in reduced_positions:
                key = f"{reduced_pos['symbol']}_{reduced_pos['pos_side']}"
                if key not in reduced_by_symbol:
                    # 计算该币种方向的总持仓量
                    total_local_size = sum(float(pos.get('local_size', 0)) for pos in reduced_positions if pos['symbol'] == reduced_pos['symbol'] and pos['pos_side'] == reduced_pos['pos_side'])
                    total_exchange_size = sum(float(pos.get('size', 0)) for pos in reduced_positions if pos['symbol'] == reduced_pos['symbol'] and pos['pos_side'] == reduced_pos['pos_side'])
                    
                    reduced_by_symbol[key] = {
                        'symbol': reduced_pos['symbol'],
                        'pos_side': reduced_pos['pos_side'],
                        'total_reduced_amount': reduced_pos['reduced_amount'],  # 直接使用，不需要累加
                        'positions': [],
                        'total_local_size': total_local_size,  # 新增：总持仓量
                        'total_exchange_size': total_exchange_size  # 新增：交易所总持仓量
                    }
                # 移除错误的累加逻辑，因为reduced_amount已经是总减仓量
                
                reduced_by_symbol[key]['positions'].append(reduced_pos)
            
            logger.info(f"[减仓信号补全] 按币种分组后，需要处理 {len(reduced_by_symbol)} 个减仓事件")
            
            # 处理每个币种和方向的减仓事件（使用FIFO逻辑）
            for key, reduced_info in reduced_by_symbol.items():
                symbol = reduced_info['symbol']
                pos_side = reduced_info['pos_side']
                total_reduced_amount = reduced_info['total_reduced_amount']
                positions = reduced_info['positions']
                
                logger.info(f"[减仓信号补全] 处理 {symbol} {pos_side} 减仓事件，总减仓量: {total_reduced_amount}张")
                
                # 直接使用传入的总持仓量计算减仓比例（避免重复查询数据库）
                total_local_size = reduced_info['total_local_size']
                signal_reduce_ratio = total_reduced_amount / total_local_size if total_local_size > 0 else 0
                logger.info(f"[减仓信号补全] 信号源当前减仓涉及持仓: {total_local_size}张, 减仓量: {total_reduced_amount}张, 减仓比例: {signal_reduce_ratio:.2%}")
                
                # 如果计算失败，使用默认减仓比例
                if signal_reduce_ratio <= 0:
                    signal_reduce_ratio = 0.5  # 默认50%
                    logger.warning(f"[减仓信号补全] 无法计算信号源持仓，使用默认减仓比例: {signal_reduce_ratio:.2%}")
                
                # 1. 使用FIFO逻辑更新信号源订单
                await self._fix_reduced_position_fifo(signal_source, symbol, pos_side, total_reduced_amount, positions)
                
                # 2. 触发一次客户减仓（传递减仓比例，而不是总减仓量）
                await self._trigger_customer_reduce_for_missing_position(
                    signal_source, symbol, pos_side, signal_reduce_ratio, 
                    positions[0].get('open_px'), positions[0].get('trade_uid')
                )
                
            logger.info(f"[减仓信号补全] 信号源 {source_uid} 减仓信号补全完成")
            
            # 同步更新信号源资产信息
            await self._sync_signal_source_assets_after_reduction(signal_source, symbol, pos_side, total_reduced_amount)
            
        except Exception as e:
            logger.error(f"[减仓信号补全] 处理已减仓持仓失败: {e}")

    async def _fix_closed_position(self, signal_source, closed_position):
        """修复已平仓的持仓 - 补全丢失的平仓信号"""
        try:
            source_uid = signal_source.source_uid if hasattr(signal_source, 'source_uid') else signal_source.get('source_uid', 'unknown')
            
            symbol = closed_position['symbol']
            pos_side = closed_position['pos_side']
            trade_uid = closed_position.get('trade_uid')
            
            logger.info(f"[平仓信号补全] 开始补全平仓信号: {symbol} {pos_side} {trade_uid}")
            logger.info(f"[平仓信号补全] 调试信息: source_uid={source_uid}, trade_uid={trade_uid}, trade_uid类型={type(trade_uid)}")
            
            # 1. 更新信号源持仓状态为已平仓
            if trade_uid:
                await self._update_signal_source_trade_status(trade_uid, source_uid, 'closed', 'compensation', '平仓信号丢失补偿')
            else:
                logger.error(f"[平仓信号补全] trade_uid为空，无法更新信号源状态")
                return
            
            # 2. 触发客户平仓
            await self._trigger_customer_close_for_missing_position(signal_source, symbol, pos_side, trade_uid)
            
            logger.info(f"[平仓信号补全] 平仓信号补全完成: {trade_uid}")
            
            # 同步更新信号源资产信息
            await self._sync_signal_source_assets_after_reduction(signal_source, symbol, pos_side, 0)
            
        except Exception as e:
            logger.error(f"[平仓信号补全] 补全平仓信号失败: {e}")

    async def _fix_reduced_position(self, signal_source, reduced_position, skip_customer_trigger=False):
        """修复已减仓的持仓 - 补全丢失的减仓信号"""
        try:
            source_uid = signal_source.source_uid if hasattr(signal_source, 'source_uid') else signal_source.get('source_uid', 'unknown')
            
            symbol = reduced_position['symbol']
            pos_side = reduced_position['pos_side']
            trade_uid = reduced_position.get('trade_uid')
            reduced_amount = reduced_position['reduced_amount']
            open_px = reduced_position.get('open_px')
            total_local_size = reduced_position.get('total_local_size', 0)
            total_exchange_size = reduced_position.get('total_exchange_size', 0)
            
            logger.info(f"[减仓信号补全] 开始补全减仓信号: {symbol} {pos_side} {trade_uid} 减仓{reduced_amount}张")
            logger.info(f"[减仓信号补全] 总持仓对比: 本地总计{total_local_size}张 -> 交易所总计{total_exchange_size}张")
            
            # 1. 更新信号源持仓数量（使用FIFO逻辑）
            if trade_uid:
                # 使用FIFO逻辑，而不是按比例分配
                current_order_size = float(reduced_position.get('local_size', 0))
                # 直接使用当前订单的减仓量，因为这是FIFO处理的结果
                await self._update_signal_source_trade_volume(trade_uid, source_uid, reduced_amount, 'compensation', '减仓信号丢失补偿')
                logger.info(f"[减仓信号补全] 订单 {trade_uid} FIFO减仓: {reduced_amount}张")
            
            # 2. 触发客户减仓（传递总减仓量）- 只有在不跳过时才触发
            if not skip_customer_trigger:
                await self._trigger_customer_reduce_for_missing_position(signal_source, symbol, pos_side, reduced_amount, open_px, trade_uid)
            
            logger.info(f"[减仓信号补全] 减仓信号补全完成: {trade_uid}")
            
        except Exception as e:
            logger.error(f"[减仓信号补全] 补全减仓信号失败: {e}")

    async def _sync_signal_source_assets_after_reduction(self, signal_source, symbol, pos_side, reduced_amount):
        """减仓补偿完成后，同步更新信号源资产信息"""
        try:
            source_uid = signal_source.source_uid if hasattr(signal_source, 'source_uid') else signal_source.get('source_uid', 'unknown')
            
            logger.info(f"[资产同步] 开始同步信号源 {source_uid} 减仓后的资产信息")
            
            # 1. 获取信号源当前交易所资产
            exchange_assets = await self._get_signal_source_exchange_assets(signal_source)
            if not exchange_assets:
                logger.warning(f"[资产同步] 无法获取信号源 {source_uid} 交易所资产信息")
                return
            
            # 2. 更新本地数据库中的资产信息（只处理USDT总资产）
            usdt_total = 0
            for account in exchange_assets:
                details = account.get('details', [])
                logger.info(f"[资产同步] 处理账户详情，共{len(details)}个币种")
            
                # 遍历每个币种的详情
                for detail in details:
                    ccy = detail.get('ccy')
                    # 使用 availBal（可用余额）或 cashBal（现金余额）
                    bal = detail.get('availBal', '0') or detail.get('cashBal', '0')
                    
                    logger.debug(f"[资产同步] 处理资产: 币种={ccy}, 可用余额={detail.get('availBal', '0')}, 现金余额={detail.get('cashBal', '0')}")
                    
                    # 累加USDT资产
                    if ccy == 'USDT' and bal:
                        usdt_total += float(bal)
            
            if usdt_total > 0:
                # 更新或插入USDT总资产记录
                asset_uid = f"{uuid.uuid4().hex[:32]}"
                self.db_pool.execute(
                    "INSERT INTO signal_account_assets (asset_uid, signal_source_uid, asset) "
                    "VALUES (%s, %s, %s) "
                    "ON DUPLICATE KEY UPDATE "
                    "signal_source_uid = VALUES(signal_source_uid), "
                    "asset = VALUES(asset), "
                    "snapshot_time = NOW()",
                    (asset_uid, source_uid, usdt_total)
                )
                logger.info(f"[资产同步] 信号源 {source_uid} USDT总资产已更新: {usdt_total}")
            else:
                logger.warning(f"[资产同步] 信号源 {source_uid} 未找到USDT资产信息")
            
        except Exception as e:
            logger.error(f"[资产同步] 同步信号源资产信息失败: {e}")

    async def _get_signal_source_exchange_assets(self, signal_source):
        """获取信号源交易所资产信息"""
        try:
            source_uid = signal_source.source_uid if hasattr(signal_source, 'source_uid') else signal_source.get('source_uid', 'unknown')
            
            # 获取API凭证
            if hasattr(signal_source, 'api_key'):
                api_key = signal_source.api_key
                secret_key = signal_source.api_secret
                passphrase = signal_source.passphrase
                is_demo = signal_source.is_demo
            else:
                api_key = signal_source.get('api_key')
                secret_key = signal_source.get('api_secret')
                passphrase = signal_source.get('passphrase')
                is_demo = signal_source.get('is_demo', False)
            
            if not all([api_key, secret_key, passphrase]):
                logger.error(f"[资产查询] 信号源 {source_uid} API凭证不完整")
                return None
            
            # 创建REST客户端
            rest_client = OKXRESTClient(api_key, secret_key, passphrase, is_demo)
            
            # 查询账户资产
            response = await rest_client.get_account_info()
            if response and response.get('code') == '0':
                data = response.get('data', [])
                logger.info(f"[资产查询] 信号源 {source_uid} 资产查询成功，共{len(data)}个币种")
                return data
            else:
                logger.error(f"[资产查询] 信号源 {source_uid} 资产查询失败: {response}")
                return None
                
        except Exception as e:
            logger.error(f"[资产查询] 获取信号源 {source_uid} 资产信息失败: {e}")
            return None

    async def get_following_customers(self, source_uid):
        """获取跟随指定信号源的客户"""
        try:
            # 查询跟随该信号源的客户
            customers = self.db_pool.query(
                "SELECT DISTINCT c.* FROM customers c " \
                "JOIN customer_strategy cs ON c.customer_uid = cs.customer_uid " \
                "JOIN strategy_signal_source sss ON cs.strategy_uid = sss.strategy_uid " \
                "WHERE sss.source_uid = %s AND c.enabled = 1 AND c.is_demo = %s",
                (source_uid, get_global_is_demo())
            )
            
            # 转换为Customer对象
            customer_objs = [self.safe_customer(c) for c in customers]
            
            logger.info(f"[客户查询] 找到 {len(customer_objs)} 个跟随信号源 {source_uid} 的客户")
            return customer_objs
            
        except Exception as e:
            logger.error(f"[客户查询] 获取跟随客户失败: {e}")
            return []

    async def _trigger_customer_close_for_missing_position(self, signal_source, symbol, pos_side, trade_uid):
        """为丢失的平仓信号触发客户平仓"""
        try:
            source_uid = signal_source.source_uid if hasattr(signal_source, 'source_uid') else signal_source.get('source_uid', 'unknown')
            
            logger.info(f"[平仓信号补全] 为丢失的平仓信号触发客户平仓: {symbol} {pos_side} {trade_uid}")
            
            # 查找跟随该信号源的客户
            customers = await self.get_following_customers(source_uid)
            
            if not customers:
                logger.info(f"[平仓信号补全] 没有客户跟随信号源: {source_uid}")
                return
            
            # 为每个客户执行平仓
            success_count = 0
            for customer in customers:
                try:
                    # 执行客户平仓
                    result = await self.execute_customer_close_for_missing_position(customer, signal_source, symbol, pos_side, trade_uid)
                    
                    if result and result.get('success'):
                        logger.info(f"[平仓信号补全] 客户 {customer.customer_uid} 平仓成功")
                        success_count += 1
                    else:
                        error_msg = result.get('error', '未知错误') if result else '执行失败'
                        logger.error(f"[平仓信号补全] 客户 {customer.customer_uid} 平仓失败: {error_msg}")
                    
                except Exception as e:
                    logger.error(f"[平仓信号补全] 客户 {customer.customer_uid} 平仓异常: {e}")
                    continue
            
            logger.info(f"[平仓信号补全] 客户平仓完成，成功 {success_count}/{len(customers)} 个客户")
            
        except Exception as e:
            logger.error(f"[平仓信号补全] 触发客户平仓失败: {e}")

    async def _trigger_customer_reduce_for_missing_position(self, signal_source, symbol, pos_side, reduce_ratio, open_px, trade_uid):
        """为丢失的减仓信号触发客户减仓"""
        try:
            source_uid = signal_source.source_uid if hasattr(signal_source, 'source_uid') else signal_source.get('source_uid', 'unknown')
            
            logger.info(f"[减仓信号补全] 为丢失的减仓信号触发客户减仓: {symbol} {pos_side} {trade_uid} 减仓比例{reduce_ratio:.2%}")
            
            # 查找跟随该信号源的客户
            customers = await self.get_following_customers(source_uid)
            
            if not customers:
                logger.info(f"[减仓信号补全] 没有客户跟随信号源: {source_uid}")
                return
            
            # 为每个客户执行减仓
            success_count = 0
            for customer in customers:
                try:
                    # 按照信号源的FIFO逻辑为客户减仓
                    # 信号源减仓了2张，按照FIFO逻辑，前两个仓位完全平仓
                    # 客户也应该按照FIFO逻辑，前两个仓位完全平仓
                    
                    # 获取客户的所有open订单（按FIFO顺序）
                    is_demo = get_global_is_demo()
                    customer_open_trades = self.db_pool.query(
                        "SELECT * FROM customer_trades WHERE customer_uid=%s AND symbol=%s AND pos_side=%s AND status='open' AND is_demo=%s ORDER BY created_at ASC",
                        (customer.customer_uid, symbol, pos_side, is_demo)
                    )
                    
                    if not customer_open_trades:
                        logger.warning(f"[减仓信号补全] 客户 {customer.customer_uid} 没有找到open订单")
                        continue
                    
                    # 按照信号源的FIFO逻辑为客户减仓
                    # 需要根据信号源的实际减仓情况来计算客户减仓
                    
                    # 获取信号源的实际减仓情况（基于信号源总持仓的减仓比例）
                    # 信号源总持仓4ETH，减仓2ETH，减仓比例50%
                    # 客户也应该按50%比例减仓
                    
                    # 直接使用传入的减仓比例（在信号源减仓补全之前已经计算好）
                    # 信号源减仓比例50%，客户也应该按50%比例减仓
                    
                    # 计算客户减仓量
                    total_customer_volume = sum(float(trade.get('volume_contract') or 0) for trade in customer_open_trades)
                    customer_reduce_amount = total_customer_volume * reduce_ratio
                    
                    logger.info(f"[减仓信号补全] 客户 {customer.customer_uid} 总持仓: {total_customer_volume}张, 信号源减仓比例: {reduce_ratio:.2%}, 客户应减仓: {customer_reduce_amount:.2f}张")
                    MIN_CUSTOMER_REDUCE_THRESHOLD = 0.001  # 最小客户减仓量阈值
                    if customer_reduce_amount < MIN_CUSTOMER_REDUCE_THRESHOLD:
                        logger.warning(f"[减仓信号补全] 客户 {customer.customer_uid} 减仓量过小({customer_reduce_amount}张)，跳过减仓")
                        continue
                    # 按照FIFO逻辑为客户减仓
                    total_customer_reduce = 0
                    remaining_reduce = customer_reduce_amount  # 客户总减仓量
                    
                    for i, trade in enumerate(customer_open_trades):
                        if remaining_reduce <= 0:
                            break
                            
                        trade_uid = trade.get('trade_uid')
                        trade_volume = float(trade.get('volume_contract') or 0)
                        
                        # 计算本次减仓量（FIFO逻辑）
                        this_reduce = min(remaining_reduce, trade_volume)
                        remaining_reduce -= this_reduce
                        
                        # 精度处理
                        sz_precision = get_contract_sz_precision(symbol)
                        this_reduce = round(this_reduce, sz_precision)
                        
                        if this_reduce > 0:
                            # 执行减仓
                            result = await self._execute_customer_reduce_trade(trade, this_reduce)
                            if result and result.get('success'):
                                total_customer_reduce += this_reduce
                                logger.info(f"[减仓信号补全] 客户 {customer.customer_uid} 订单{i+1}减仓: {trade_uid}, 减仓{this_reduce}张 (FIFO顺序)")
                            else:
                                logger.error(f"[减仓信号补全] 客户 {customer.customer_uid} 订单{i+1}减仓失败: {trade_uid}")
                        else:
                            logger.info(f"[减仓信号补全] 客户 {customer.customer_uid} 订单{i+1}无需减仓: {trade_uid}")
                    
                    logger.info(f"[减仓信号补全] 客户 {customer.customer_uid} FIFO减仓完成，总计减仓{total_customer_reduce}张")
                    
                    # 设置成功标志
                    success = total_customer_reduce > 0
                    
                    if success:
                        logger.info(f"[减仓信号补全] 客户 {customer.customer_uid} 减仓成功")
                        success_count += 1
                    else:
                        logger.error(f"[减仓信号补全] 客户 {customer.customer_uid} 减仓失败")
                    
                except Exception as e:
                    logger.error(f"[减仓信号补全] 客户 {customer.customer_uid} 减仓异常: {e}")
                    continue
            
            logger.info(f"[减仓信号补全] 客户减仓完成，成功 {success_count}/{len(customers)} 个客户")
            
        except Exception as e:
            logger.error(f"[减仓信号补全] 触发客户减仓失败: {e}")

    async def _send_position_sync_alert(self, signal_source, missing_positions, closed_positions, reduced_positions):
        """发送仓位同步异常警报"""
        try:
            source_uid = signal_source.source_uid if hasattr(signal_source, 'source_uid') else signal_source.get('source_uid', 'unknown')
            source_name = signal_source.name if hasattr(signal_source, 'name') else signal_source.get('name', '未知')
            
            total_issues = len(missing_positions) + len(closed_positions) + len(reduced_positions)
            
            alert_message = f"🚨 信号源仓位同步异常警报\n\n" \
                           f"信号源: {source_name} ({source_uid})\n" \
                           f"异常原因: 发现 {total_issues} 个信号丢失\n" \
                           f"开仓信号丢失: {len(missing_positions)} 个\n" \
                           f"平仓信号丢失: {len(closed_positions)} 个\n" \
                           f"减仓信号丢失: {len(reduced_positions)} 个\n" \
                           f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n" \
                           f"⚠️ 正在自动补全丢失的信号..."
            
            # 发送钉钉通知
            if should_send_alert_notification("warning"):
                alert_info = {
                    'title': '信号源仓位同步异常',
                    'level': 'warning',
                    'time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                    'message': f"信号源 {source_uid} 发现 {total_issues} 个信号丢失",
                    'account': source_uid,
                    'strategy': '仓位同步检查',
                    'symbol': f"开仓:{len(missing_positions)}, 平仓:{len(closed_positions)}, 减仓:{len(reduced_positions)}",
                    'suggestion': '系统正在自动补全丢失的信号'
                }
                await send_alert_notification_async("warning", alert_info)
            
            logger.error(f"[仓位同步警报] {alert_message}")
            
        except Exception as e:
            logger.error(f"发送仓位同步警报失败: {e}")

    async def start_position_sync_monitor(self):
        """启动仓位同步监控任务"""
        async def monitor_loop():
            while True:
                try:
                    logger.info("[仓位同步监控] 开始定期检查所有信号源的仓位同步状态...")
                    
                    # 获取所有启用的信号源
                    signal_sources = get_enabled_signal_accounts(self.db_pool, get_global_is_demo())
                    
                    for signal_source in signal_sources:
                        try:
                            await self._check_signal_source_position_sync(signal_source)
                        except Exception as e:
                            logger.error(f"[仓位同步监控] 检查信号源 {signal_source.get('source_uid', 'unknown')} 失败: {e}")
                            continue
                    
                    logger.info("[仓位同步监控] 定期检查完成，等待下次检查...")
                    await asyncio.sleep(300)  # 5分钟检查一次
                    
                except Exception as e:
                    logger.error(f"[仓位同步监控] 监控循环异常: {e}")
                    await asyncio.sleep(60)  # 异常后1分钟重试
        
        self.position_sync_monitor_task = asyncio.create_task(monitor_loop())
        logger.info("仓位同步监控任务已启动，每5分钟检查一次")

    # 新增：客户平仓和减仓的执行方法
    async def execute_customer_close_for_missing_position(self, customer, signal_source, symbol, pos_side, trade_uid):
        """执行客户平仓（针对丢失的平仓信号）"""
        try:
            customer_uid = get_customer_uid(customer)
            logger.info(f"[客户平仓补全] 执行客户 {customer_uid} 平仓: {symbol} {pos_side}")
            
            # 查找客户的对应持仓
            open_trades = self.get_open_trades_by_symbol(symbol, pos_side)
            customer_trades = [t for t in open_trades if get_trade_field(t, 'customer_uid') == customer_uid]
            
            if not customer_trades:
                logger.warning(f"[客户平仓补全] 客户 {customer_uid} 没有对应的持仓: {symbol} {pos_side}")
                return {'success': False, 'error': '没有对应的持仓'}
            
            # 检查客户在交易所的实际持仓
            
            db_pool = get_global_db_pool()
            
            try:
                # 获取客户的API配置
                api_key = getattr(customer, 'api_key', '')
                api_secret = getattr(customer, 'api_secret', '')
                passphrase = getattr(customer, 'passphrase', '')
                is_demo = getattr(customer, 'is_demo', False)
                
                if not api_key or not api_secret or not passphrase:
                    logger.warning(f"[客户平仓补全] 客户 {customer_uid} API配置不完整，跳过持仓检查")
                else:
                    # 创建REST API客户端查询客户实际持仓
                    
                    rest_client = OKXRESTClient(
                        api_key=api_key,
                        api_secret=api_secret,
                        passphrase=passphrase,
                        is_demo=is_demo
                    )
                    
                    # 查询客户在交易所的实际持仓
                    positions_response = await rest_client.get_positions()
                    
                    if positions_response and 'data' in positions_response:
                        # 检查是否还有对应的持仓
                        has_position = False
                        for pos in positions_response['data']:
                            if (pos.get('instId') == symbol and 
                                pos.get('posSide') == pos_side and 
                                float(pos.get('pos', '0') or '0') > 0):
                                has_position = True
                                break
                        
                        if not has_position:
                            # 客户持仓已经平仓，直接更新数据库状态
                            logger.info(f"[客户平仓补全] 客户 {customer_uid} 在交易所已无持仓，更新数据库状态")
                            for trade in customer_trades:
                                trade_uid = get_trade_field(trade, 'trade_uid')
                                if trade_uid:
                                    db_pool.execute(
                                        "UPDATE customer_trades SET status='closed', execution_type='compensation', execution_reason='平仓信号丢失补偿' WHERE trade_uid=%s",
                                        (trade_uid,)
                                    )
                                    logger.info(f"[客户平仓补全] 客户 {customer_uid} 持仓状态已更新: {trade_uid}")
                            
                            logger.info(f"[客户平仓补全] 客户 {customer_uid} 平仓补偿完成（持仓已平仓）")
                            return {'success': True, 'message': '平仓补偿完成（持仓已平仓）'}
                        else:
                            logger.info(f"[客户平仓补全] 客户 {customer_uid} 在交易所仍有持仓，需要发送平仓订单")
                    else:
                        logger.warning(f"[客户平仓补全] 客户 {customer_uid} 持仓查询失败，尝试发送平仓订单")
                        
            except Exception as e:
                logger.error(f"[客户平仓补全] 检查客户持仓失败: {e}，尝试发送平仓订单")
            
            # 执行平仓
            result = await self.batch_close_trades_total_order(customer_trades, symbol, pos_side)
            
            if result and result.get('success'):
                logger.info(f"[客户平仓补全] 客户 {customer_uid} 平仓成功")
                return {'success': True, 'message': '平仓成功'}
            else:
                error_msg = result.get('error', '未知错误') if result else '平仓失败'
                logger.error(f"[客户平仓补全] 客户 {customer_uid} 平仓失败: {error_msg}")
                return {'success': False, 'error': error_msg}
                
        except Exception as e:
            logger.error(f"[客户平仓补全] 执行客户平仓异常: {e}")
            return {'success': False, 'error': str(e)}

    async def execute_customer_follow_trade(self, customer, signal_source, symbol, direction, pos_side, size, avg_px, trade_uid):
        """执行客户跟单（针对丢失的开仓信号）"""
        try:
            customer_uid = get_customer_uid(customer)
            logger.info(f"[客户跟单补全] 执行客户 {customer_uid} 跟单: {symbol} {direction} {pos_side} {size}张 @ {avg_px}")
            
            # 计算客户交易数量（按照资产比例计算）
            customer_size = await self._calculate_customer_compensation_size(customer, signal_source, symbol, size, avg_px)
            
            if customer_size <= 0:
                logger.warning(f"[客户跟单补全] 客户 {customer_uid} 计算的下单量为0，跳过跟单")
                return {'success': False, 'error': '计算的下单量为0'}
            
            
            # 获取客户策略信息
            strategy_uid = None
            rule_uid = None
            
            # 查询客户策略配置
            strategy_query = """
                SELECT cs.strategy_uid, sss.strategy_uid as signal_strategy_uid
                FROM customer_strategy cs
                JOIN strategy_signal_source sss ON cs.strategy_uid = sss.strategy_uid
                WHERE cs.customer_uid = %s AND sss.source_uid = %s
                LIMIT 1
            """
            source_uid = signal_source.source_uid if hasattr(signal_source, 'source_uid') else signal_source.get('source_uid', 'unknown')
            strategy_result = self.db_pool.query(strategy_query, (customer_uid, source_uid))
            
            if strategy_result:
                strategy_uid = strategy_result[0]['strategy_uid']
                # 获取规则UID
                rule_query = "SELECT rule_uid FROM rules WHERE strategy_uid = %s AND enabled = 1 LIMIT 1"
                rule_result = self.db_pool.query(rule_query, (strategy_uid,))
                if rule_result:
                    rule_uid = rule_result[0]['rule_uid']
            
            # 生成唯一的trade_uid
            import uuid
            customer_trade_uid = f"COMP_{uuid.uuid4().hex[:16]}"
            
            # 插入客户开仓记录
            insert_customer_trade(
                self.db_pool,
                customer_uid,
                strategy_uid or 'unknown',
                rule_uid or 'unknown',
                symbol,
                float(customer_size) * float(avg_px) if avg_px else 0,  # volume (USDT价值)
                direction,
                pos_side,
                trade_uid=customer_trade_uid,
                is_demo=getattr(customer, 'is_demo', 0),
                volume_contract=customer_size,  # 张数
                open_px=avg_px,  # 开仓价格
                execution_type='compensation',
                execution_reason='客户开仓信号丢失补偿'
            )
            
            # 更新客户订单，设置与信号源的关联关系
            try:
                # 设置parent_ordId为信号源的trade_uid
                self.db_pool.execute(
                    "UPDATE customer_trades SET parent_ordId=%s WHERE trade_uid=%s",
                    (trade_uid, customer_trade_uid)
                )
                logger.info(f"[客户跟单补全] 客户 {customer_uid} 订单关联信号源成功: parent_ordId={trade_uid}")
            except Exception as e:
                logger.warning(f"[客户跟单补全] 设置客户订单关联失败: {e}")
            
            logger.info(f"[客户跟单补全] 客户 {customer_uid} 开仓记录已保存到数据库: trade_uid={customer_trade_uid}")
            
            # 执行客户开仓
            result = await self.async_place_order(
                customer=customer,
                symbol=symbol,
                direction=direction,
                pos_side=pos_side,
                sz=customer_size,
                trade_uid=trade_uid,
                reduceOnly=False
            )
            
            if result and result.get('ordId'):
                logger.info(f"[客户跟单补全] 客户 {customer_uid} 跟单成功")
                return {'success': True, 'message': '跟单成功'}
            else:
                error_msg = result.get('error', '未知错误') if result else '跟单失败'
                logger.error(f"[客户跟单补全] 客户 {customer_uid} 跟单失败: {error_msg}")
                return {'success': False, 'error': error_msg}
                
        except Exception as e:
            logger.error(f"[客户跟单补全] 执行客户跟单异常: {e}")
            return {'success': False, 'error': str(e)}

    async def execute_customer_reduce_for_missing_position(self, customer, signal_source, symbol, pos_side, reduced_amount, open_px, trade_uid):
        """执行客户减仓（针对丢失的减仓信号）"""
        try:
            customer_uid = get_customer_uid(customer)
            logger.info(f"[客户减仓补全] 执行客户 {customer_uid} 减仓: {symbol} {pos_side} 减仓{reduced_amount}张")
            
            # 计算客户减仓数量（按比例计算）
            customer_reduce_amount = await self._calculate_customer_compensation_size(customer, signal_source, symbol, reduced_amount, open_px)
            
            if customer_reduce_amount <= 0:
                logger.warning(f"[客户减仓补全] 客户 {customer_uid} 计算的减仓量为0，跳过减仓")
                return {'success': False, 'error': '计算的减仓量为0'}
            
            logger.info(f"[客户减仓补全] 客户 {customer_uid} 按比例计算减仓量: {customer_reduce_amount}张")
            
            # 查找客户的对应持仓，按开仓时间排序（FIFO）
            open_trades = self.get_open_trades_by_symbol(symbol, pos_side)
            customer_trades = [t for t in open_trades if get_trade_field(t, 'customer_uid') == customer_uid]
            
            if not customer_trades:
                logger.warning(f"[客户减仓补全] 客户 {customer_uid} 没有对应的持仓: {symbol} {pos_side}")
                return {'success': False, 'error': '没有对应的持仓'}
            
            # 按开仓时间排序，实现FIFO逻辑
            customer_trades.sort(key=lambda x: get_trade_field(x, 'created_at'))
            logger.info(f"[客户减仓补全] 客户 {customer_uid} 持仓按FIFO排序，共{len(customer_trades)}个订单")
            
            # 按FIFO原则分配减仓量
            remaining_reduce = customer_reduce_amount
            success_count = 0
            processed_trades = []
            
            for i, trade in enumerate(customer_trades):
                if remaining_reduce <= 0:
                    break
                    
                trade_uid = get_trade_field(trade, 'trade_uid')
                trade_volume = safe_float(get_trade_field(trade, 'volume_contract'))
                current_closed = safe_float(get_trade_field(trade, 'close_volume_contract'))
                available_volume = trade_volume - current_closed  # 可减仓数量
                
                if available_volume <= 0:
                    logger.info(f"[客户减仓补全] 订单 {trade_uid} 已完全平仓，跳过")
                    continue
                
                # 计算本次减仓数量
                reduce_amount = min(remaining_reduce, available_volume)
                
                logger.info(f"[客户减仓补全] FIFO处理第{i+1}个订单: {trade_uid}, 总持仓{trade_volume}张, 已平仓{current_closed}张, 可减仓{available_volume}张, 本次减仓{reduce_amount}张")
                
                # 执行减仓
                result = await self._execute_customer_reduce_trade(trade, reduce_amount)
                
                if result and result.get('success'):
                    success_count += 1
                    remaining_reduce -= reduce_amount
                    processed_trades.append({
                        'trade_uid': trade_uid,
                        'reduced_amount': reduce_amount,
                        'remaining_volume': trade_volume - current_closed - reduce_amount
                    })
                    logger.info(f"[客户减仓补全] 客户 {customer_uid} 订单 {trade_uid} 减仓成功: {reduce_amount}张")
                else:
                    logger.error(f"[客户减仓补全] 客户 {customer_uid} 订单 {trade_uid} 减仓失败: {result.get('error', '未知错误')}")
            
            # 记录FIFO减仓详情
            logger.info(f"[客户减仓补全] 客户 {customer_uid} FIFO减仓详情: {processed_trades}")
            
            if remaining_reduce == 0:
                logger.info(f"[客户减仓补全] 客户 {customer_uid} 减仓完成，成功平仓 {customer_reduce_amount}张")
                return {'success': True, 'message': f'减仓完成，平仓{customer_reduce_amount}张', 'processed_trades': processed_trades}
            else:
                logger.warning(f"[客户减仓补全] 客户 {customer_uid} 减仓部分完成，剩余{remaining_reduce}张")
                return {'success': False, 'error': f'减仓部分完成，剩余{remaining_reduce}张', 'processed_trades': processed_trades}
                
        except Exception as e:
            logger.error(f"[客户减仓补全] 执行客户减仓异常: {e}")
            return {'success': False, 'error': str(e)}

    async def _execute_customer_reduce_fifo(self, customer, signal_source, signal_trade, total_reduced_amount, symbol, pos_side):
        """按照FIFO逻辑为客户执行减仓（参考信号源的FIFO逻辑）"""
        try:
            customer_uid = get_customer_uid(customer)
            source_uid = signal_source.source_uid if hasattr(signal_source, 'source_uid') else signal_source.get('source_uid', 'unknown')
            
            logger.info(f"[客户FIFO减仓] 开始为客户 {customer_uid} 执行FIFO减仓: 总减仓量={total_reduced_amount}张")
            
            # 1. 获取客户的所有open订单（按FIFO顺序）
            is_demo = get_global_is_demo()
            customer_open_trades = self.db_pool.query(
                "SELECT * FROM customer_trades WHERE customer_uid=%s AND symbol=%s AND pos_side=%s AND status='open' AND is_demo=%s ORDER BY created_at ASC",
                (customer_uid, symbol, pos_side, is_demo)
            )
            
            if not customer_open_trades:
                logger.warning(f"[客户FIFO减仓] 客户 {customer_uid} 没有找到open订单")
                return
            
            logger.info(f"[客户FIFO减仓] 客户 {customer_uid} 持仓按FIFO排序，共{len(customer_open_trades)}个订单")
            
            # 2. 按照FIFO逻辑分配减仓量
            remaining_reduce = total_reduced_amount
            reduced_details = []
            
            for i, trade in enumerate(customer_open_trades):
                if remaining_reduce <= 0:
                    break
                    
                trade_uid = trade.get('trade_uid')
                original_volume = float(trade.get('volume_contract') or 0)
                current_closed = float(trade.get('close_volume_contract') or 0)
                available_volume = original_volume - current_closed
                
                # 计算本次分配给这个订单的减仓量
                this_reduce = min(remaining_reduce, available_volume)
                
                logger.info(f"[客户FIFO减仓] FIFO处理第{i+1}个订单: {trade_uid}, 总持仓{original_volume}张, 已平仓{current_closed}张, 可减仓{available_volume}张, 本次减仓{this_reduce}张")
                
                # 3. 执行减仓
                if this_reduce > 0:
                    result = await self._execute_customer_reduce_trade(trade, this_reduce)
                    if result.get('success'):
                        remaining_reduce -= this_reduce
                        reduced_details.append({
                            'trade_uid': trade_uid,
                            'reduced_amount': this_reduce,
                            'remaining_volume': available_volume - this_reduce
                        })
                        logger.info(f"[客户FIFO减仓] 客户 {customer_uid} 订单 {trade_uid} 减仓成功: {this_reduce}张")
                    else:
                        logger.error(f"[客户FIFO减仓] 客户 {customer_uid} 订单 {trade_uid} 减仓失败: {result.get('error')}")
                else:
                    logger.info(f"[客户FIFO减仓] 订单 {trade_uid} 无需减仓")
            
            # 4. 记录FIFO减仓详情
            logger.info(f"[客户FIFO减仓] 客户 {customer_uid} FIFO减仓详情: {reduced_details}")
            
            # 5. 计算总减仓量
            total_customer_reduced = sum(detail['reduced_amount'] for detail in reduced_details)
            logger.info(f"[客户FIFO减仓] 客户 {customer_uid} 减仓完成，成功平仓 {total_customer_reduced}张")
            
            return {
                'success': True,
                'total_reduced': total_customer_reduced,
                'reduced_details': reduced_details
            }
            
        except Exception as e:
            customer_uid = customer.get('customer_uid')
            logger.error(f"[客户FIFO减仓] 为客户 {customer_uid} 执行FIFO减仓失败: {e}")
            return {'success': False, 'error': str(e)}

    async def _execute_customer_reduce_trade(self, trade, reduce_amount):
        """执行客户单个订单的减仓"""
        try:
            trade_uid = get_trade_field(trade, 'trade_uid')
            customer_uid = get_trade_field(trade, 'customer_uid')
            symbol = get_trade_field(trade, 'symbol')
            pos_side = get_trade_field(trade, 'pos_side')
            current_volume = safe_float(get_trade_field(trade, 'volume_contract'))
            current_closed = safe_float(get_trade_field(trade, 'close_volume_contract'))
            
            logger.info(f"[客户减仓] 执行订单减仓: {trade_uid}, 当前持仓{current_volume}张, 已平仓{current_closed}张, 减仓{reduce_amount}张")
            
            # 1. 发送减仓订单到交易所
            # 获取客户信息
            customer_data = get_customer_by_id(self.db_pool, customer_uid, is_demo=get_global_is_demo())
            if not customer_data:
                logger.error(f"[客户减仓] 未找到客户 {customer_uid}")
                return {'success': False, 'error': '未找到客户'}
            
            customer = self.safe_customer(customer_data)
            direction = 'sell' if pos_side == 'long' else 'buy'
            
            # 生成减仓订单ID
            reduce_clOrdId = f"REDUCE_{customer_uid}_{symbol}_{pos_side}_{int(time.time())}"[:32]
            
            # 发送减仓订单
            res = await self.async_place_order(
                customer=customer,
                symbol=symbol,
                direction=direction,
                pos_side=pos_side,
                sz=reduce_amount,
                trade_uid=reduce_clOrdId,
                reduceOnly=True,
                tag='6618f740e7f1BCDE'
            )
            
            ordId = res.get('ordId')
            if ordId:
                # 2. 更新数据库中的close_volume_contract和状态
                new_closed_amount = current_closed + reduce_amount
                
                # 判断是否完全平仓
                if new_closed_amount >= current_volume:
                    # 完全平仓
                    status = 'closed'
                    closed_at = 'NOW()'
                    logger.info(f"[客户减仓] 订单 {trade_uid} 已完全平仓，状态更新为closed")
                else:
                    # 部分减仓
                    status = 'open'
                    closed_at = None
                    logger.info(f"[客户减仓] 订单 {trade_uid} 部分减仓，状态保持open")
                
                # 更新数据库
                if closed_at == 'NOW()':
                    # 完全平仓，使用NOW()
                    self.db_pool.execute(
                        "UPDATE customer_trades SET close_volume_contract=%s, status=%s, closed_at=NOW(), execution_type='compensation', execution_reason='减仓信号丢失补偿' WHERE trade_uid=%s",
                        (new_closed_amount, status, trade_uid)
                    )
                else:
                    # 部分减仓，closed_at为NULL
                    self.db_pool.execute(
                        "UPDATE customer_trades SET close_volume_contract=%s, status=%s, execution_type='compensation', execution_reason='减仓信号丢失补偿' WHERE trade_uid=%s",
                        (new_closed_amount, status, trade_uid)
                    )
                
                logger.info(f"[客户减仓] 订单 {trade_uid} 减仓成功: ordId={ordId}, 减仓{reduce_amount}张, 累计平仓{new_closed_amount}张, 状态={status}")
                return {'success': True, 'message': '减仓成功', 'ordId': ordId, 'reduced_amount': reduce_amount, 'status': status}
            else:
                logger.error(f"[客户减仓] 订单 {trade_uid} 减仓失败: {res}")
                return {'success': False, 'error': f'减仓失败: {res}'}
                
        except Exception as e:
            logger.error(f"[客户减仓] 执行订单减仓异常: {e}")
            return {'success': False, 'error': str(e)}

    # 客户仓位同步检查相关方法
    async def _check_customer_positions_sync(self, signal_source, signal_exchange_positions):
        """检查客户仓位同步状态，确保客户仓位与信号源仓位一致"""
        try:
            source_uid = signal_source.source_uid if hasattr(signal_source, 'source_uid') else signal_source.get('source_uid', 'unknown')
            source_name = signal_source.name if hasattr(signal_source, 'name') else signal_source.get('name', '未知')
            
            logger.info(f"[客户仓位同步] 开始检查信号源 {source_uid} 的客户仓位同步状态")
            
            # 1. 获取该信号源的所有客户
            customers = await self._get_signal_source_customers(source_uid)
            if not customers:
                logger.info(f"[客户仓位同步] 信号源 {source_uid} 没有关联的客户")
                return
            
            # 2. 获取信号源本地数据库记录
            signal_local_positions = await self._get_signal_source_local_positions(source_uid)
            
            # 3. 为每个客户检查仓位同步
            for customer in customers:
                customer_uid = customer.get('customer_uid')
                customer_name = customer.get('name', '未知')
                
                logger.info(f"[客户仓位同步] 检查客户 {customer_uid} ({customer_name}) 仓位同步")
                
                # 获取客户实际持仓
                customer_exchange_positions = await self._get_customer_exchange_positions(customer)
                
                # 获取客户本地数据库记录
                customer_local_positions = await self._get_customer_local_positions(customer_uid, source_uid)
                
                # 检查客户仓位与信号源仓位的一致性
                await self._sync_customer_with_signal_source(
                    customer, signal_source, 
                    signal_exchange_positions, signal_local_positions,
                    customer_exchange_positions, customer_local_positions
                )
                
        except Exception as e:
            source_uid = signal_source.source_uid if hasattr(signal_source, 'source_uid') else signal_source.get('source_uid', 'unknown')
            logger.error(f"[客户仓位同步] 检查信号源 {source_uid} 客户仓位同步失败: {e}")
            await self._send_signal_source_connection_alert(signal_source, f"客户仓位同步检查失败: {e}")

    async def _sync_customer_with_signal_source(self, customer, signal_source, 
                                              signal_exchange_positions, signal_local_positions,
                                              customer_exchange_positions, customer_local_positions):
        """同步客户仓位与信号源仓位"""
        try:
            customer_uid = customer.get('customer_uid')
            customer_name = customer.get('name', '未知')
            source_uid = signal_source.source_uid if hasattr(signal_source, 'source_uid') else signal_source.get('source_uid', 'unknown')
            
            # 1. 检查信号源开仓但客户未跟随的情况
            for signal_pos in signal_exchange_positions:
                inst_id = signal_pos.get('instId')
                pos_side = signal_pos.get('posSide')
                pos = float(signal_pos.get('pos', '0'))
                
                if pos > 0:  # 信号源有持仓
                    # 检查本地是否有对应的开仓记录
                    signal_trade = self._find_signal_trade_by_position(signal_local_positions, inst_id, pos_side)
                    
                    if not signal_trade:
                        # 信号源开仓信号丢失，需要补全
                        logger.warning(f"[客户仓位同步] 信号源 {source_uid} 开仓信号丢失: {inst_id} {pos_side}")
                        await self._handle_signal_source_missing_open(signal_source, signal_pos)
                    
                    # 检查客户是否跟随开仓
                    customer_trade = self._find_customer_trade_by_position(customer_local_positions, inst_id, pos_side)
                    
                    if not customer_trade and signal_trade:
                        # 客户未跟随开仓，需要补全
                        logger.warning(f"[客户仓位同步] 客户 {customer_uid} 未跟随信号源开仓: {inst_id} {pos_side}")
                        await self._handle_customer_missing_follow_open(customer, signal_source, signal_trade)
            
            # 2. 检查信号源平仓但客户未跟随的情况
            for signal_local_pos in signal_local_positions:
                inst_id = signal_local_pos.get('inst_id')
                pos_side = signal_local_pos.get('pos_side')
                status = signal_local_pos.get('status')
                
                if status == 'open':  # 本地记录显示信号源持仓
                    # 检查交易所实际持仓
                    exchange_pos = self._find_position_by_inst(signal_exchange_positions, inst_id, pos_side)
                    
                    if not exchange_pos or float(exchange_pos.get('pos', '0')) <= 0:
                        # 信号源已平仓但本地未更新
                        logger.warning(f"[客户仓位同步] 信号源 {source_uid} 平仓信号丢失: {inst_id} {pos_side}")
                        await self._handle_signal_source_missing_close(signal_source, signal_local_pos)
                        
                        # 检查客户是否跟随平仓
                        customer_trade = self._find_customer_trade_by_position(customer_local_positions, inst_id, pos_side)
                        if customer_trade and get_trade_field(customer_trade, 'status') == 'open':
                            # 检查客户是否已经有order_id（已平仓）
                            order_id = get_trade_field(customer_trade, 'order_id')
                            if not order_id:
                                logger.warning(f"[客户仓位同步] 客户 {customer_uid} 未跟随信号源平仓: {inst_id} {pos_side}")
                                await self._handle_customer_missing_follow_close(customer, signal_source, signal_local_pos)
                            else:
                                logger.info(f"[客户仓位同步] 客户 {customer_uid} 已经平仓，无需重复处理: {inst_id} {pos_side}")
            
            # 3. 检查信号源减仓但客户未跟随的情况
            for signal_local_pos in signal_local_positions:
                inst_id = signal_local_pos.get('inst_id')
                pos_side = signal_local_pos.get('pos_side')
                status = signal_local_pos.get('status')
                
                if status == 'open':
                    exchange_pos = self._find_position_by_inst(signal_exchange_positions, inst_id, pos_side)
                    if exchange_pos:
                        local_sz = float(signal_local_pos.get('sz', '0'))
                        exchange_sz = float(exchange_pos.get('pos', '0'))
                        
                        if exchange_sz < local_sz and exchange_sz > 0:
                            # 信号源减仓但本地未更新
                            logger.warning(f"[客户仓位同步] 信号源 {source_uid} 减仓信号丢失: {inst_id} {pos_side}")
                            await self._handle_signal_source_missing_reduce(signal_source, signal_local_pos, exchange_sz)
                            
                            # 检查客户是否跟随减仓
                            customer_trade = self._find_customer_trade_by_position(customer_local_positions, inst_id, pos_side)
                            if customer_trade and customer_trade.get('status') == 'open':
                                logger.warning(f"[客户仓位同步] 客户 {customer_uid} 未跟随信号源减仓: {inst_id} {pos_side}")
                                await self._handle_customer_missing_follow_reduce(customer, signal_source, signal_local_pos, exchange_sz)
                                
        except Exception as e:
            customer_uid = customer.get('customer_uid')
            logger.error(f"[客户仓位同步] 同步客户 {customer_uid} 仓位失败: {e}")

    async def _handle_signal_source_missing_open(self, signal_source, exchange_position):
        """处理信号源开仓信号丢失"""
        try:
            source_uid = signal_source.source_uid if hasattr(signal_source, 'source_uid') else signal_source.get('source_uid', 'unknown')
            inst_id = exchange_position.get('instId')
            pos_side = exchange_position.get('posSide')
            pos = float(exchange_position.get('pos', '0'))
            avg_px = float(exchange_position.get('avgPx', '0'))
            
            # 创建信号源开仓记录
            trade_uid = f"comp_open_{source_uid}_{inst_id}_{pos_side}_{int(time.time())}"
            
            trade_data = {
                'trade_uid': trade_uid,
                'signal_source_uid': source_uid,
                'inst_id': inst_id,
                'trade_type': 'open',
                'pos_side': pos_side,
                'sz': pos,
                'px': avg_px,
                'status': 'open',
                'execution_type': 'compensation',
                'execution_reason': '信号源开仓信号丢失补偿',
                'created_at': datetime.now(),
                'is_demo': signal_source.is_demo if hasattr(signal_source, 'is_demo') else signal_source.get('is_demo', False)
            }
            
            # 插入数据库
            await self._insert_signal_source_trade(trade_data)
            
            logger.info(f"[信号补偿] 信号源 {source_uid} 开仓信号补偿完成: {inst_id} {pos_side} {pos}")
            
            # 发送钉钉通知
            await self._send_compensation_notification(signal_source, "开仓信号丢失补偿", trade_data)
            
        except Exception as e:
            source_uid = signal_source.source_uid if hasattr(signal_source, 'source_uid') else signal_source.get('source_uid', 'unknown')
            logger.error(f"[信号补偿] 处理信号源 {source_uid} 开仓信号丢失失败: {e}")

    async def _handle_signal_source_missing_close(self, signal_source, local_position):
        """处理信号源平仓信号丢失"""
        try:
            source_uid = signal_source.source_uid if hasattr(signal_source, 'source_uid') else signal_source.get('source_uid', 'unknown')
            trade_uid = local_position.get('trade_uid')
            inst_id = local_position.get('inst_id')
            pos_side = local_position.get('pos_side')
            
            # 更新信号源交易记录为已平仓
            await self._update_signal_source_trade_status(
                trade_uid, source_uid, 'closed', 
                execution_type='compensation',
                execution_reason='信号源平仓信号丢失补偿'
            )
            
            logger.info(f"[信号补偿] 信号源 {source_uid} 平仓信号补偿完成: {inst_id} {pos_side}")
            
            # 发送钉钉通知
            await self._send_compensation_notification(signal_source, "平仓信号丢失补偿", {
                'trade_uid': trade_uid,
                'inst_id': inst_id,
                'pos_side': pos_side
            })
            
        except Exception as e:
            source_uid = signal_source.source_uid if hasattr(signal_source, 'source_uid') else signal_source.get('source_uid', 'unknown')
            logger.error(f"[信号补偿] 处理信号源 {source_uid} 平仓信号丢失失败: {e}")

    async def _handle_signal_source_missing_reduce(self, signal_source, local_position, new_size):
        """处理信号源减仓信号丢失"""
        try:
            source_uid = signal_source.source_uid if hasattr(signal_source, 'source_uid') else signal_source.get('source_uid', 'unknown')
            trade_uid = local_position.get('trade_uid')
            symbol = local_position.get('symbol')
            pos_side = local_position.get('pos_side')
            old_size = float(local_position.get('volume_contract', '0'))
            current_closed = float(local_position.get('close_volume_contract', '0'))
            
            # 计算减仓数量
            reduced_amount = old_size - new_size
            logger.info(f"[信号补偿] 信号源 {source_uid} 减仓计算: 原持仓{old_size}张, 现持仓{new_size}张, 减仓{reduced_amount}张")
            
            # 更新信号源交易记录为减仓
            await self._update_signal_source_trade_volume(
                trade_uid, source_uid, reduced_amount,
                execution_type='compensation',
                execution_reason='信号源减仓信号丢失补偿'
            )
            
            logger.info(f"[信号补偿] 信号源 {source_uid} 减仓信号补偿完成: {symbol} {pos_side} {old_size} -> {new_size} (减仓{reduced_amount}张)")
            
            # 发送钉钉通知
            await self._send_compensation_notification(signal_source, "减仓信号丢失补偿", {
                'trade_uid': trade_uid,
                'symbol': symbol,
                'pos_side': pos_side,
                'old_size': old_size,
                'new_size': new_size,
                'reduced_amount': reduced_amount
            })
            
        except Exception as e:
            source_uid = signal_source.source_uid if hasattr(signal_source, 'source_uid') else signal_source.get('source_uid', 'unknown')
            logger.error(f"[信号补偿] 处理信号源 {source_uid} 减仓信号丢失失败: {e}")

    async def _handle_customer_missing_follow_open(self, customer, signal_source, signal_trade):
        """处理客户未跟随信号源开仓"""
        try:
            customer_uid = customer.get('customer_uid')
            customer_name = customer.get('name', '未知')
            source_uid = signal_source.source_uid if hasattr(signal_source, 'source_uid') else signal_source.get('source_uid', 'unknown')
            
            inst_id = signal_trade.get('symbol')
            pos_side = signal_trade.get('pos_side')
            sz = signal_trade.get('volume_contract')
            px = signal_trade.get('open_px')
            
            # 为客户执行跟随开仓
            result = await self._execute_customer_follow_trade(
                customer, signal_source, signal_trade, 'open',
                execution_type='compensation',
                execution_reason='客户开仓信号丢失补偿'
            )
            
            if result and result.get('success'):
                logger.info(f"[客户补偿] 客户 {customer_uid} 开仓补偿完成: {inst_id} {pos_side}")
            else:
                error_msg = result.get('error', '未知错误') if result else '执行失败'
                logger.error(f"[客户补偿] 客户 {customer_uid} 开仓补偿失败: {error_msg}")
                raise Exception(f"客户开仓补偿失败: {error_msg}")
            
        except Exception as e:
            customer_uid = customer.get('customer_uid')
            logger.error(f"[客户补偿] 处理客户 {customer_uid} 开仓补偿失败: {e}")

    async def _handle_customer_missing_follow_close(self, customer, signal_source, signal_trade):
        """处理客户未跟随信号源平仓"""
        try:
            customer_uid = customer.get('customer_uid')
            customer_name = customer.get('name', '未知')
            source_uid = signal_source.source_uid if hasattr(signal_source, 'source_uid') else signal_source.get('source_uid', 'unknown')
            
            inst_id = signal_trade.get('symbol')
            pos_side = signal_trade.get('pos_side')
            
            # 为客户执行跟随平仓
            result = await self._execute_customer_follow_trade(
                customer, signal_source, signal_trade, 'close',
                execution_type='compensation',
                execution_reason='客户平仓信号丢失补偿'
            )
            
            if result and result.get('success'):
                logger.info(f"[客户补偿] 客户 {customer_uid} 平仓补偿完成: {inst_id} {pos_side}")
            else:
                error_msg = result.get('error', '未知错误') if result else '执行失败'
                logger.error(f"[客户补偿] 客户 {customer_uid} 平仓补偿失败: {error_msg}")
                raise Exception(f"客户平仓补偿失败: {error_msg}")
            
        except Exception as e:
            customer_uid = customer.get('customer_uid')
            logger.error(f"[客户补偿] 处理客户 {customer_uid} 平仓补偿失败: {e}")

    async def _handle_customer_missing_follow_reduce(self, customer, signal_source, signal_trade, new_size):
        """处理客户未跟随信号源减仓"""
        try:
            customer_uid = customer.get('customer_uid')
            customer_name = customer.get('name', '未知')
            source_uid = signal_source.source_uid if hasattr(signal_source, 'source_uid') else signal_source.get('source_uid', 'unknown')
            
            inst_id = signal_trade.get('symbol')
            pos_side = signal_trade.get('pos_side')
            
            # 计算信号源实际减仓量（参考正常逻辑）
            original_size = float(signal_trade.get('volume_contract', 0))
            reduced_amount = original_size - new_size
            
            logger.info(f"[客户减仓补偿] 信号源 {source_uid} 订单 {signal_trade.get('trade_uid')}: 原始持仓{original_size}张 -> 现持仓{new_size}张, 减仓{reduced_amount}张")
            
            # 按照FIFO逻辑为客户执行减仓（参考信号源的FIFO逻辑）
            await self._execute_customer_reduce_fifo(
                customer, signal_source, signal_trade, reduced_amount, inst_id, pos_side
            )
            
            logger.info(f"[客户补偿] 客户 {customer_uid} 减仓补偿完成: {inst_id} {pos_side}")
            
        except Exception as e:
            customer_uid = customer.get('customer_uid')
            logger.error(f"[客户补偿] 处理客户 {customer_uid} 减仓补偿失败: {e}")

    async def _execute_customer_follow_trade(self, customer, signal_source, signal_trade, trade_type, 
                                           execution_type='compensation', execution_reason='', reduce_size=None):
        """执行客户跟随交易"""
        try:
            customer_uid = customer.get('customer_uid')
            source_uid = signal_source.source_uid if hasattr(signal_source, 'source_uid') else signal_source.get('source_uid', 'unknown')
            
            inst_id = signal_trade.get('symbol')
            pos_side = signal_trade.get('pos_side')
            signal_sz = signal_trade.get('volume_contract')
            signal_px = signal_trade.get('open_px')
            
            # 计算客户交易数量
            if trade_type == 'reduce' and reduce_size is not None:
                # 减仓时，使用减仓量（需要按照FIFO逻辑分配到客户订单）
                if reduce_size > 0:
                    # 这里不直接计算customer_sz，而是让调用方处理FIFO逻辑
                    customer_sz = reduce_size  # 临时值，实际会在FIFO逻辑中重新计算
                    logger.info(f"[客户跟随交易] 减仓交易，收到减仓量: {reduce_size}张，将在FIFO逻辑中重新计算")
                else:
                    customer_sz = 0
                    logger.warning(f"[客户跟随交易] 减仓交易，减仓量为0")
            else:
                # 其他交易类型，使用原有逻辑
                customer_sz = self._calculate_customer_trade_size(customer, signal_sz, trade_type, reduce_size)
            
            # 执行客户交易
            result = None
            if trade_type == 'open':
                result = await self._place_customer_open_order(customer, inst_id, pos_side, customer_sz, signal_px, 
                                                     signal_trade, execution_type, execution_reason)
            elif trade_type == 'close':
                result = await self._place_customer_close_order(customer, inst_id, pos_side, customer_sz, signal_px,
                                                      signal_trade, execution_type, execution_reason)
            elif trade_type == 'reduce':
                result = await self._place_customer_reduce_order(customer, inst_id, pos_side, customer_sz, signal_px,
                                                       signal_trade, execution_type, execution_reason)
            
            # 返回执行结果
            if result and result.get('success'):
                logger.info(f"[客户跟随交易] 客户 {customer_uid} {trade_type}交易执行成功")
                return {'success': True, 'message': f'{trade_type}交易执行成功'}
            else:
                error_msg = result.get('error', '未知错误') if result else '执行失败'
                logger.error(f"[客户跟随交易] 客户 {customer_uid} {trade_type}交易执行失败: {error_msg}")
                return {'success': False, 'error': error_msg}
                
        except Exception as e:
            customer_uid = customer.get('customer_uid')
            logger.error(f"[客户补偿] 执行客户 {customer_uid} 跟随交易失败: {e}")
            return {'success': False, 'error': str(e)}

    async def _send_compensation_notification(self, signal_source, compensation_type, trade_data):
        """发送补偿通知"""
        try:
            source_uid = signal_source.source_uid if hasattr(signal_source, 'source_uid') else signal_source.get('source_uid', 'unknown')
            source_name = signal_source.name if hasattr(signal_source, 'name') else signal_source.get('name', '未知')
            
            alert_info = {
                'title': f'信号丢失补偿通知',
                'content': f'信号源: {source_name} ({source_uid})\n补偿类型: {compensation_type}\n交易信息: {trade_data}',
                'level': 'warning',
                'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            }
            
            if should_send_alert_notification("warning"):
                await send_alert_notification_async("warning", alert_info)
                
        except Exception as e:
            logger.error(f"[补偿通知] 发送补偿通知失败: {e}")

    # 辅助方法
    def _find_signal_trade_by_position(self, local_positions, inst_id, pos_side):
        """根据持仓信息查找信号源交易记录"""
        for pos in local_positions:
            if pos.get('symbol') == inst_id and pos.get('pos_side') == pos_side:
                return pos
        return None

    def _find_customer_trade_by_position(self, customer_positions, inst_id, pos_side):
        """根据持仓信息查找客户交易记录"""
        for pos in customer_positions:
            if get_trade_field(pos, 'symbol') == inst_id and get_trade_field(pos, 'pos_side') == pos_side:
                return pos
        return None

    def _find_position_by_inst(self, exchange_positions, inst_id, pos_side):
        """根据合约和方向查找交易所持仓"""
        for pos in exchange_positions:
            if pos.get('instId') == inst_id and pos.get('posSide') == pos_side:
                return pos
        return None

    def _calculate_customer_trade_size(self, customer, signal_sz, trade_type, reduce_size=None):
        """计算客户交易数量"""
        # 这里可以根据客户的杠杆比例、风险设置等计算实际交易数量
        # 简化处理，直接使用信号源的数量
        if trade_type == 'reduce' and reduce_size is not None:
            return reduce_size
        return signal_sz

    async def _calculate_customer_compensation_size(self, customer, signal_source, symbol, signal_size, signal_price):
        """计算客户补偿下单量（按照资产比例）"""
        try:
            customer_uid = get_customer_uid(customer)
            source_uid = signal_source.source_uid if hasattr(signal_source, 'source_uid') else signal_source.get('source_uid', 'unknown')
            
            logger.info(f"[补偿计算] 开始计算客户 {customer_uid} 补偿下单量")
            
            # 1. 获取客户有效资产
            is_demo = get_global_is_demo()
            customer_data = get_customer_by_id(self.db_pool, customer_uid, is_demo)
            
            if not customer_data:
                logger.warning(f"[补偿计算] 未找到客户 {customer_uid} 数据，使用默认计算")
                return signal_size
            
            total_asset = get_customer_effective_asset(self.db_pool, customer_uid, is_demo)
            if total_asset is None or total_asset <= 0:
                total_asset = 10000.0  # 默认值
                logger.warning(f"[补偿计算] 客户 {customer_uid} 有效资产为空，使用默认值 {total_asset}")
            
            # 2. 获取信号源当前资产
            signal_current_asset_raw = get_signal_source_current_asset(self.db_pool, source_uid)
            if signal_current_asset_raw is None:
                signal_current_asset = 10000.0  # 默认值
                logger.warning(f"[补偿计算] 信号源 {source_uid} 当前资产为空，使用默认值 {signal_current_asset}")
            else:
                signal_current_asset = float(signal_current_asset_raw)
            
            # 3. 计算资产比例
            asset_ratio = float(total_asset) / float(signal_current_asset) if signal_current_asset > 0 else 1.0
            logger.info(f"[补偿计算] 客户 {customer_uid} 资产: {total_asset}, 信号源 {source_uid} 资产: {signal_current_asset}, 资产比例: {asset_ratio}")
            
            # 4. 获取客户的仓位比例（从策略配置中获取）
            position_ratio = await self._get_customer_position_ratio(customer_uid, source_uid)
            logger.info(f"[补偿计算] 客户 {customer_uid} 仓位比例: {position_ratio}")
            
            # 5. 计算实际下单量：实际下单 = 信号源下单量 × 资产比例 ÷ 仓位比例
            actual_customer_sz = float(signal_size) * float(asset_ratio) / float(position_ratio)
            logger.info(f"[补偿计算] 信号源下单 {signal_size}张, 资产比例 {asset_ratio}, 仓位比例 {position_ratio}, 计算客户下单量 {actual_customer_sz}张")
            
            # 6. 精度处理
            min_sz = get_contract_min_sz(symbol)
            sz_precision = get_contract_sz_precision(symbol)
            actual_customer_sz = round(round(actual_customer_sz / min_sz) * min_sz, sz_precision)
            
            # 7. 风控检查
            if actual_customer_sz < min_sz:
                logger.warning(f"[补偿计算] 客户 {customer_uid} 计算下单量 {actual_customer_sz}张 小于最小下单量 {min_sz}张")
                return 0
            
            # 8. 杠杆风控检查
            max_leverage = await self._get_customer_max_leverage(customer_uid, source_uid)
            if not await self._check_leverage_risk(customer_uid, symbol, actual_customer_sz, total_asset, max_leverage):
                logger.warning(f"[补偿计算] 客户 {customer_uid} 杠杆风控检查未通过")
                return 0
            
            logger.info(f"[补偿计算] 客户 {customer_uid} 最终补偿下单量: {actual_customer_sz}张")
            return actual_customer_sz
            
        except Exception as e:
            logger.error(f"[补偿计算] 计算客户 {customer_uid} 补偿下单量失败: {e}")
            return signal_size  # 出错时使用信号源数量作为默认值

    async def _get_customer_position_ratio(self, customer_uid, source_uid):
        """获取客户的仓位比例"""
        try:
            # 查询客户策略配置中的仓位比例（从rules表中获取）
            query = """
                SELECT r.position_ratio 
                FROM customer_strategy cs
                JOIN strategy_signal_source sss ON cs.strategy_uid = sss.strategy_uid
                JOIN rules r ON cs.strategy_uid = r.strategy_uid
                WHERE cs.customer_uid = %s AND sss.source_uid = %s AND r.enabled = 1
                LIMIT 1
            """
            result = self.db_pool.query(query, (customer_uid, source_uid))
            
            if result and len(result) > 0:
                position_ratio = safe_float(result[0].get('position_ratio', 1.0))
                return position_ratio if position_ratio > 0 else 1.0
            else:
                logger.warning(f"[仓位比例] 未找到客户 {customer_uid} 对信号源 {source_uid} 的仓位比例配置，使用默认值1.0")
                return 1.0
                
        except Exception as e:
            logger.error(f"[仓位比例] 获取客户 {customer_uid} 仓位比例失败: {e}")
            return 1.0

    async def _get_customer_max_leverage(self, customer_uid, source_uid):
        """获取客户的最大杠杆"""
        try:
            # 查询客户策略配置中的最大杠杆（从rules表中获取）
            query = """
                SELECT r.max_leverage 
                FROM customer_strategy cs
                JOIN strategy_signal_source sss ON cs.strategy_uid = sss.strategy_uid
                JOIN rules r ON cs.strategy_uid = r.strategy_uid
                WHERE cs.customer_uid = %s AND sss.source_uid = %s AND r.enabled = 1
                LIMIT 1
            """
            result = self.db_pool.query(query, (customer_uid, source_uid))
            
            if result and len(result) > 0:
                max_leverage = safe_float(result[0].get('max_leverage', 10.0))
                return max_leverage if max_leverage > 0 else 10.0
            else:
                logger.warning(f"[最大杠杆] 未找到客户 {customer_uid} 对信号源 {source_uid} 的最大杠杆配置，使用默认值10.0")
                return 10.0
                
        except Exception as e:
            logger.error(f"[最大杠杆] 获取客户 {customer_uid} 最大杠杆失败: {e}")
            return 10.0

    async def _check_leverage_risk(self, customer_uid, symbol, customer_sz, total_asset, max_leverage):
        """检查杠杆风控"""
        try:
            # 获取当前价格
            latest_px = await get_price_on_demand(symbol) or 1
            multiplier = get_contract_multiplier(symbol)
            
            # 获取客户当前持仓
            trades = self.get_open_trades(customer_uid)
            current_nominal = sum(safe_float(trade.volume) for trade in trades)
            
            # 计算新开仓的名义价值
            new_nominal = customer_sz * multiplier * latest_px
            
            # 计算总杠杆
            total_nominal = current_nominal + new_nominal
            net_leverage = total_nominal / total_asset if total_asset > 0 else 0
            
            logger.info(f"[杠杆风控] 客户 {customer_uid} 当前持仓名义价值: {current_nominal}, 新开仓名义价值: {new_nominal}, 总杠杆: {net_leverage}, 最大杠杆: {max_leverage}")
            
            if net_leverage > max_leverage:
                logger.warning(f"[杠杆风控] 客户 {customer_uid} 总杠杆 {net_leverage} 超过最大杠杆 {max_leverage}")
                return False
            
            return True
            
        except Exception as e:
            logger.error(f"[杠杆风控] 检查客户 {customer_uid} 杠杆风控失败: {e}")
            return True  # 出错时允许下单

    async def _get_signal_source_customers(self, source_uid):
        """获取信号源关联的客户列表"""
        try:
            # 直接使用现有的客户查询逻辑，它已经正确处理了信号源→策略→客户的关系
            customers = await self.get_following_customers(source_uid)
            if customers:
                # 转换为字典格式
                customer_list = []
                for customer in customers:
                    customer_dict = {
                        'customer_uid': get_customer_uid(customer),
                        'name': get_customer_field(customer, 'name', '未知'),
                        'api_key': get_customer_field(customer, 'api_key', ''),
                        'api_secret': get_customer_field(customer, 'api_secret', ''),
                        'passphrase': get_customer_field(customer, 'passphrase', ''),
                        'is_demo': get_customer_field(customer, 'is_demo', False)
                    }
                    customer_list.append(customer_dict)
                logger.info(f"[客户仓位同步] 获取到 {len(customer_list)} 个客户")
                return customer_list
            else:
                logger.info(f"[客户仓位同步] 信号源 {source_uid} 没有关联的客户")
                return []
        except Exception as e:
            logger.error(f"获取信号源 {source_uid} 关联客户失败: {e}")
            return []

    async def _get_customer_exchange_positions(self, customer):
        """获取客户交易所持仓"""
        try:
            customer_uid = customer.get('customer_uid')
            api_key = customer.get('api_key')
            api_secret = customer.get('api_secret')
            passphrase = customer.get('passphrase')
            is_demo = customer.get('is_demo', False)
            
            if not api_key or not api_secret or not passphrase:
                logger.warning(f"客户 {customer_uid} API配置不完整")
                return []
            
            
            rest_client = OKXRESTClient(
                api_key=api_key,
                api_secret=api_secret,
                passphrase=passphrase,
                is_demo=is_demo
            )
            
            positions_response = await rest_client.get_positions()
            
            if not positions_response or 'data' not in positions_response:
                logger.warning(f"获取客户 {customer_uid} 持仓失败: {positions_response}")
                return []
            
            return [pos for pos in positions_response['data'] if float(pos.get('pos', '0')) > 0]
            
        except Exception as e:
            customer_uid = customer.get('customer_uid')
            logger.error(f"获取客户 {customer_uid} 交易所持仓失败: {e}")
            return []

    async def _get_customer_local_positions(self, customer_uid, source_uid):
        """获取客户本地数据库持仓记录"""
        try:
            # 使用现有的客户持仓查询逻辑
            open_trades = self.get_open_trades(customer_uid)
            # 过滤出跟随指定信号源的持仓
            filtered_trades = []
            for trade in open_trades:
                if get_trade_field(trade, 'signal_source_uid') == source_uid:
                    filtered_trades.append(trade)
            return filtered_trades
        except Exception as e:
            logger.error(f"获取客户 {customer_uid} 本地持仓记录失败: {e}")
            return []

    async def _insert_signal_source_trade(self, trade_data):
        """插入信号源交易记录"""
        try:
            query = """
                INSERT INTO signal_account_trades (
                    trade_uid, signal_source_uid, inst_id, trade_type, pos_side, 
                    volume_contract, open_px, status, execution_type, execution_reason, created_at, is_demo
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """
            self.db_pool.execute(query, (
                trade_data['trade_uid'], trade_data['signal_source_uid'], trade_data['inst_id'],
                trade_data['trade_type'], trade_data['pos_side'], trade_data['sz'], trade_data['px'],
                trade_data['status'], trade_data['execution_type'], trade_data['execution_reason'],
                trade_data['created_at'], trade_data['is_demo']
            ))
        except Exception as e:
            logger.error(f"插入信号源交易记录失败: {e}")

    async def _update_signal_source_trade_status(self, trade_uid, source_uid, status, execution_type=None, execution_reason=None):
        """更新信号源交易状态"""
        try:
            if execution_type and execution_reason:
                query = """
                    UPDATE signal_account_trades 
                    SET status = %s, execution_type = %s, execution_reason = %s
                    WHERE trade_uid = %s AND signal_source_uid = %s
                """
                self.db_pool.execute(query, (status, execution_type, execution_reason, trade_uid, source_uid))
            else:
                query = """
                    UPDATE signal_account_trades 
                    SET status = %s
                    WHERE trade_uid = %s AND signal_source_uid = %s
                """
                self.db_pool.execute(query, (status, trade_uid, source_uid))
        except Exception as e:
            logger.error(f"更新信号源交易状态失败: {e}")

    async def _update_signal_source_trade_volume(self, trade_uid, source_uid, reduced_amount, execution_type=None, execution_reason=None):
        """更新信号源交易数量（减仓）"""
        try:
            if execution_type and execution_reason:
                query = """
                    UPDATE signal_account_trades 
                    SET close_volume_contract = ifnull(close_volume_contract, 0) + %s, execution_type = %s, execution_reason = %s
                    WHERE trade_uid = %s AND signal_source_uid = %s
                """
                self.db_pool.execute(query, (reduced_amount, execution_type, execution_reason, trade_uid, source_uid))
            else:
                query = """
                    UPDATE signal_account_trades 
                    SET close_volume_contract = close_volume_contract + %s
                    WHERE trade_uid = %s AND signal_source_uid = %s
                """
                self.db_pool.execute(query, (reduced_amount, trade_uid, source_uid))
            
            logger.info(f"[数据库更新] 信号源交易减仓数量已更新: {trade_uid} 减仓{reduced_amount}张")
            
            # 检查是否需要将订单状态改为closed
            try:
                # 查询当前订单的总持仓量和已平仓量
                check_query = """
                    SELECT volume_contract, close_volume_contract, status
                    FROM signal_account_trades 
                    WHERE trade_uid = %s AND signal_source_uid = %s
                """
                result = self.db_pool.query(check_query, (trade_uid, source_uid))
                
                if result:
                    order_info = result[0]
                    volume_contract = float(order_info.get('volume_contract', 0))
                    close_volume_contract = float(order_info.get('close_volume_contract', 0))
                    current_status = order_info.get('status', 'open')
                    
                    logger.info(f"[状态检查] 订单 {trade_uid}: 总持仓{volume_contract}张, 已平仓{close_volume_contract}张, 当前状态{current_status}")
                    
                    # 如果已平仓量 >= 总持仓量，且当前状态不是closed，则更新为closed
                    if close_volume_contract >= volume_contract and current_status != 'closed':
                        update_status_query = """
                            UPDATE signal_account_trades 
                            SET status = 'closed', closed_at = NOW()
                            WHERE trade_uid = %s AND signal_source_uid = %s
                        """
                        self.db_pool.execute(update_status_query, (trade_uid, source_uid))
                        logger.info(f"[状态更新] 订单 {trade_uid} 已完全平仓，状态更新为closed")
                    elif close_volume_contract < volume_contract and current_status == 'closed':
                        # 如果已平仓量 < 总持仓量，但状态是closed，则改回open
                        update_status_query = """
                            UPDATE signal_account_trades 
                            SET status = 'open', closed_at = NULL
                            WHERE trade_uid = %s AND signal_source_uid = %s
                        """
                        self.db_pool.execute(update_status_query, (trade_uid, source_uid))
                        logger.info(f"[状态更新] 订单 {trade_uid} 未完全平仓，状态改回open")
                        
            except Exception as e:
                logger.error(f"[状态检查] 检查订单 {trade_uid} 状态失败: {e}")
                
        except Exception as e:
            logger.error(f"更新信号源交易数量失败: {e}")

    async def _fix_reduced_position_fifo(self, signal_source, symbol, pos_side, total_reduced_amount, positions):
        """使用FIFO逻辑修复信号源减仓 - 参考正常减仓逻辑"""
        try:
            source_uid = signal_source.source_uid if hasattr(signal_source, 'source_uid') else signal_source.get('source_uid', 'unknown')
            
            logger.info(f"[FIFO减仓补全] 开始FIFO分配减仓量: 总减仓量={total_reduced_amount}张, 开仓记录数={len(positions)}")
            
            # 按创建时间排序，确保FIFO顺序
            sorted_positions = sorted(positions, key=lambda x: x.get('trade_uid', ''))
            
            remaining_reduce = total_reduced_amount
            
            for i, reduced_pos in enumerate(sorted_positions):
                if remaining_reduce <= 0:
                    logger.info(f"[FIFO减仓补全] 减仓分配完成，剩余减仓量=0")
                    break
                    
                trade_uid = reduced_pos.get('trade_uid')
                current_order_size = float(reduced_pos.get('local_size', 0))
                
                logger.info(f"[FIFO减仓补全] 处理第{i+1}个开仓记录: trade_uid={trade_uid}, 剩余减仓量={remaining_reduce}")
                
                # 查询当前订单的已减仓量
                check_query = """
                    SELECT volume_contract, close_volume_contract
                    FROM signal_account_trades 
                    WHERE trade_uid = %s AND signal_source_uid = %s
                """
                result = self.db_pool.query(check_query, (trade_uid, source_uid))
                
                if result:
                    order_info = result[0]
                    original_volume = float(order_info.get('volume_contract') or 0)
                    current_closed = float(order_info.get('close_volume_contract') or 0)
                    available_volume = original_volume - current_closed  # 剩余可减仓量
                    
                    # 计算本次分配给这个仓位的减仓量
                    this_reduce = min(remaining_reduce, available_volume)
                    total_closed = current_closed + this_reduce
                    
                    logger.info(f"[FIFO减仓补全] 仓位{i+1}: 原始持仓={original_volume}, 已减仓={current_closed}, 剩余可减仓={available_volume}, 本次分配={this_reduce}")
                    
                    # 更新减仓量
                    await self._update_signal_source_trade_volume(trade_uid, source_uid, this_reduce, 'compensation', '减仓信号丢失补偿')
                    
                    # 更新剩余减仓量
                    remaining_reduce -= this_reduce
                    
                    logger.info(f"[FIFO减仓补全] 仓位{i+1}更新完成: trade_uid={trade_uid}, 本次分配减仓量={this_reduce}")
                else:
                    logger.warning(f"[FIFO减仓补全] 未找到订单记录: trade_uid={trade_uid}")
            
            if remaining_reduce > 0:
                logger.warning(f"[FIFO减仓补全] 减仓分配后仍有剩余: {remaining_reduce}张")
                
        except Exception as e:
            logger.error(f"[FIFO减仓补全] FIFO减仓补全失败: {e}")

    async def _place_customer_open_order(self, customer, inst_id, pos_side, sz, px, signal_trade, execution_type, execution_reason):
        """为客户下开仓订单"""
        try:
            customer_uid = customer.get('customer_uid')
            
            # 获取客户策略信息
            strategy_uid = None
            rule_uid = None
            
            # 查询客户策略配置
            # 从signal_trade中获取signal_source_uid，如果没有则从其他地方获取
            signal_source_uid = signal_trade.get('signal_source_uid')
            if not signal_source_uid:
                # 尝试从其他地方获取，比如从方法参数或全局变量
                signal_source_uid = getattr(self, 'current_signal_source_uid', 'unknown')
            
            strategy_query = """
                SELECT cs.strategy_uid, sss.strategy_uid as signal_strategy_uid
                FROM customer_strategy cs
                JOIN strategy_signal_source sss ON cs.strategy_uid = sss.strategy_uid
                WHERE cs.customer_uid = %s AND sss.source_uid = %s
                LIMIT 1
            """
            strategy_result = self.db_pool.query(strategy_query, (customer_uid, signal_source_uid))
            
            if strategy_result:
                strategy_uid = strategy_result[0]['strategy_uid']
                # 获取规则UID
                rule_query = "SELECT rule_uid FROM rules WHERE strategy_uid = %s AND enabled = 1 LIMIT 1"
                rule_result = self.db_pool.query(rule_query, (strategy_uid,))
                if rule_result:
                    rule_uid = rule_result[0]['rule_uid']
            
            # 生成唯一的trade_uid
            import uuid
            trade_uid = f"COMP_{uuid.uuid4().hex[:16]}"
            
            # 插入客户开仓记录
            insert_customer_trade(
                self.db_pool,
                customer_uid,
                strategy_uid or 'unknown',
                rule_uid or 'unknown',
                inst_id,
                float(sz) * float(px) if px else 0,  # volume (USDT价值)
                'buy' if pos_side == 'long' else 'sell',
                pos_side,
                trade_uid=trade_uid,
                is_demo=getattr(customer, 'is_demo', 0),
                volume_contract=sz,  # 张数
                open_px=px,  # 开仓价格
                execution_type=execution_type,
                execution_reason=execution_reason
            )
            
            # 更新客户订单，设置与信号源的关联关系
            try:
                # 设置parent_ordId为信号源的trade_uid
                signal_trade_uid = signal_trade.get('trade_uid')
                if signal_trade_uid:
                    self.db_pool.execute(
                        "UPDATE customer_trades SET parent_ordId=%s WHERE trade_uid=%s",
                        (signal_trade_uid, trade_uid)
                    )
                    logger.info(f"[客户补偿] 客户 {customer_uid} 订单关联信号源成功: parent_ordId={signal_trade_uid}")
            except Exception as e:
                logger.warning(f"[客户补偿] 设置客户订单关联失败: {e}")
            
            logger.info(f"[客户补偿] 客户 {customer_uid} 开仓记录已保存到数据库: trade_uid={trade_uid}")
            
            # 可以根据实际的客户开仓方法进行调整
            order_result = await self.async_place_order(
                customer_uid=customer_uid,
                symbol=inst_id,
                direction='buy' if pos_side == 'long' else 'sell',
                sz=sz,
                pos_side=pos_side,
                reduceOnly=False,
                execution_type=execution_type,
                execution_reason=execution_reason
            )
            
            logger.info(f"[客户补偿] 客户 {customer_uid} 开仓订单执行结果: {order_result}")
            
            # 返回执行结果
            if order_result and order_result.get('ordId'):
                return {'success': True, 'message': '开仓订单执行成功', 'order_result': order_result}
            else:
                error_msg = order_result.get('error', '未知错误') if order_result else '开仓订单执行失败'
                return {'success': False, 'error': error_msg}
            
        except Exception as e:
            customer_uid = customer.get('customer_uid')
            logger.error(f"[客户补偿] 客户 {customer_uid} 开仓订单执行失败: {e}")
            return {'success': False, 'error': str(e)}

    async def _place_customer_close_order(self, customer, inst_id, pos_side, sz, px, signal_trade, execution_type, execution_reason):
        """为客户下平仓订单"""
        try:
            customer_uid = customer.get('customer_uid')
            
            # 这里调用现有的客户平仓逻辑
            order_result = await self.async_place_order(
                customer_uid=customer_uid,
                symbol=inst_id,
                direction='sell' if pos_side == 'long' else 'buy',
                sz=sz,
                pos_side=pos_side,
                reduceOnly=True,
                execution_type=execution_type,
                execution_reason=execution_reason
            )
            
            logger.info(f"[客户补偿] 客户 {customer_uid} 平仓订单执行结果: {order_result}")
            
            # 返回执行结果
            if order_result and order_result.get('ordId'):
                return {'success': True, 'message': '平仓订单执行成功', 'order_result': order_result}
            else:
                error_msg = order_result.get('error', '未知错误') if order_result else '平仓订单执行失败'
                return {'success': False, 'error': error_msg}
            
        except Exception as e:
            customer_uid = customer.get('customer_uid')
            logger.error(f"[客户补偿] 客户 {customer_uid} 平仓订单执行失败: {e}")
            return {'success': False, 'error': str(e)}

    async def _place_customer_reduce_order(self, customer, inst_id, pos_side, sz, px, signal_trade, execution_type, execution_reason):
        """为客户下减仓订单"""
        try:
            customer_uid = customer.get('customer_uid')
            
            # 这里调用现有的客户减仓逻辑
            order_result = await self.async_place_order(
                customer_uid=customer_uid,
                symbol=inst_id,
                direction='sell' if pos_side == 'long' else 'buy',
                sz=sz,
                pos_side=pos_side,
                reduceOnly=True,
                execution_type=execution_type,
                execution_reason=execution_reason
            )
            
            logger.info(f"[客户补偿] 客户 {customer_uid} 减仓订单执行结果: {order_result}")
            
            # 返回执行结果
            if order_result and order_result.get('ordId'):
                return {'success': True, 'message': '减仓订单执行成功', 'order_result': order_result}
            else:
                error_msg = order_result.get('error', '未知错误') if order_result else '减仓订单执行失败'
                return {'success': False, 'error': error_msg}
            
        except Exception as e:
            customer_uid = customer.get('customer_uid')
            logger.error(f"[客户补偿] 客户 {customer_uid} 减仓订单执行失败: {e}")
            return {'success': False, 'error': str(e)}

    # ==================== 带单员市价跟单模块 ====================
    
    async def _process_market_follow_strategy(self, strategy, signal_source_uid, symbol, pos_side, signal_price, signal_trade_uid):
        """处理带单员市价跟单策略 - 立即以市价跟单"""
        try:
            logger.info(f"[带单员-市价跟单] 处理市价跟单策略: 客户={strategy['customer_uid']}, 信号源={signal_source_uid}")
            
            # 1. 计算目标仓位
            signal_position = await self._get_signal_position_for_single_trade(signal_source_uid, symbol, pos_side)
            if signal_position <= 0:
                logger.warning(f"[带单员-市价跟单] 信号源无当前交易持仓，跳过处理")
                return
                
            target_position = await self._calculate_target_position(strategy, signal_source_uid, signal_position)
            if target_position <= 0:
                logger.warning(f"[带单员-市价跟单] 计算目标仓位为0，跳过处理")
                return
            
            logger.info(f"[带单员-市价跟单] 目标仓位: {target_position}")
            
            # 2. 根据比例分配限价和市价仓位
            limit_position, market_position = self._calculate_limit_market_positions(
                target_position, strategy.get('limit_market_ratio', '1:1')
            )
            
            logger.info(f"[带单员-比例跟单] 总仓位: {target_position}, 限价仓位: {limit_position}, 市价仓位: {market_position}")
            
            # 3. 获取客户信息
            customer_uid = strategy['customer_uid']
            customer_data = self.db_pool.query(
                "SELECT * FROM customers WHERE customer_uid=%s AND enabled=1",
                (customer_uid,)
            )
            if not customer_data:
                logger.error(f"[带单员-市价跟单] 客户 {customer_uid} 不存在")
                return
            customer = customer_data[0]
            
            # 3. 获取客户客户端
            customer_client = await self._get_existing_customer_client(customer)
            if not customer_client:
                logger.error(f"[带单员-市价跟单] 无法获取客户 {strategy['customer_uid']} 的客户端")
                return
            
            # 4. 根据比例执行不同的开仓策略
            if strategy.get('follow_order_types') == 'both':
                # 限价+市价模式：分别执行限价和市价开仓
                await self._execute_limit_market_follow(
                    customer_client, strategy, signal_source_uid, symbol, pos_side,
                    limit_position, market_position, signal_trade_uid
                )
            else:
                # 单一模式：只执行市价开仓
                order_uid = f"{strategy['id']}{strategy['customer_uid'][-6:].replace('_', '').replace('-', '')}{signal_trade_uid[-8:]}"
                
                order_result = await self._place_market_follow_order(
                    customer_client, order_uid, symbol, pos_side, 
                    market_position, 0, strategy  # 使用市价仓位
                )
                
                if order_result and order_result.get('success'):
                    logger.info(f"[带单员-市价跟单] 市价跟单成功: {order_uid}")
                    
                    await self._save_market_follow_order(
                        order_uid, strategy, signal_source_uid, symbol, pos_side,
                        market_position, 0, signal_trade_uid, order_result
                    )
                else:
                    logger.error(f"[带单员-市价跟单] 市价跟单失败: {order_uid}")
                
        except Exception as e:
            logger.error(f"[带单员-市价跟单] 处理市价跟单策略失败: {e}")

    async def _place_market_follow_order(self, customer_client, order_uid, symbol, pos_side, size, price, strategy):
        """下市价跟单订单"""
        try:
            # 调整数量精度，确保符合交易对的最小数量单位
            adjusted_size = self._adjust_order_size(symbol, abs(size))
            if adjusted_size <= 0:
                logger.warning(f"[带单员-市价跟单] 调整后数量为0，跳过下单")
                return False
            
            # 构建订单参数
            order_params = {
                'instId': symbol,
                'tdMode': 'cross',  # 全仓模式
                'side': 'buy' if pos_side == 'long' else 'sell',
                'posSide': pos_side,  # 开仓方向
                'ordType': 'market',  # 市价单
                'sz': str(adjusted_size),  # 调整后的数量
                'clOrdId': order_uid,  # 客户端订单ID
            }
            
            # 设置杠杆
            leverage = strategy.get('custom_leverage') or strategy.get('leverage', 10)
            order_params['lever'] = str(leverage)
            
            logger.info(f"[带单员-市价跟单] 下市价单参数: {order_params}")
            
            # 下市价单
            result = await customer_client.place_order(**order_params)
            
            if result and result.get('code') == '0':
                logger.info(f"[带单员-市价跟单] 市价单下单成功: {result}")
                # 返回订单信息，包含交易所订单ID
                order_data = result.get('data', [{}])[0]
                return {
                    'success': True,
                    'ordId': order_data.get('ordId'),
                    'clOrdId': order_data.get('clOrdId'),
                    'result': result
                }
            else:
                logger.error(f"[带单员-市价跟单] 市价单下单失败: {result}")
                return {'success': False, 'result': result}
                
        except Exception as e:
            logger.error(f"[带单员-市价跟单] 下市价单异常: {e}")
            return False

    async def _save_market_follow_order(self, order_uid, strategy, signal_source_uid, symbol, pos_side, size, price, signal_trade_uid, order_result=None):
        """保存市价跟单订单到数据库"""
        try:
            # 获取交易所订单ID和成交信息
            exchange_order_id = None
            filled_price = 0.0
            filled_size = abs(size)
            
            if order_result and order_result.get('success'):
                exchange_order_id = order_result.get('ordId')
                # 市价单立即成交，使用目标价格作为成交价格
                filled_price = price if price > 0 else 0.0
            
            # 插入市价跟单订单记录
            self.db_pool.execute(
                """INSERT INTO limit_follow_orders 
                   (order_uid, strategy_id, trader_unique_name, customer_uid, symbol, pos_side, 
                    follow_value, target_price, order_size, order_type, status, signal_order_id, 
                    exchange_order_id, filled_price, filled_size, created_at)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())""",
                (order_uid, strategy['id'], signal_source_uid, strategy['customer_uid'], 
                 symbol, pos_side, round(float(strategy.get('custom_follow_value') or strategy.get('follow_value') or 0.4), 4),
                 round(float(price), 8), round(float(abs(size)), 8), 'market', 'filled', signal_trade_uid,
                 exchange_order_id, round(float(filled_price), 8), round(float(filled_size), 8))
            )
            
            logger.info(f"[带单员-市价跟单] 市价跟单订单已保存: {order_uid}")
            
        except Exception as e:
            logger.error(f"[带单员-市价跟单] 保存市价跟单订单失败: {e}")

    def _calculate_limit_market_positions(self, total_position, ratio_str):
        """根据比例计算限价和市价仓位"""
        try:
            if ':' not in ratio_str:
                # 默认1:1比例
                limit_ratio, market_ratio = 1, 1
            else:
                limit_ratio, market_ratio = map(int, ratio_str.split(':'))
            
            total_ratio = limit_ratio + market_ratio
            limit_position = total_position * limit_ratio / total_ratio
            market_position = total_position * market_ratio / total_ratio
            
            return limit_position, market_position
            
        except Exception as e:
            logger.error(f"[比例计算] 计算限价市价比例失败: {e}")
            # 默认1:1比例
            return total_position / 2, total_position / 2

    async def _execute_limit_market_follow(self, customer_client, strategy, signal_source_uid, symbol, pos_side, limit_position, market_position, signal_trade_uid):
        """执行限价+市价跟单"""
        try:
            # 1. 执行限价跟单
            if limit_position > 0:
                logger.info(f"[比例跟单] 执行限价跟单: {limit_position}")
                await self._process_limit_follow_strategy(
                    strategy, signal_source_uid, symbol, pos_side, 
                    limit_position, signal_trade_uid, 'limit'
                )
            
            # 2. 执行市价跟单
            if market_position > 0:
                logger.info(f"[比例跟单] 执行市价跟单: {market_position}")
                # 生成市价订单ID
                market_order_uid = f"MF_{strategy['id']}{strategy['customer_uid'][-6:].replace('_', '').replace('-', '')}{signal_trade_uid[-8:]}"
                
                market_result = await self._place_market_follow_order(
                    customer_client, market_order_uid, symbol, pos_side,
                    market_position, 0, strategy
                )
                
                if market_result and market_result.get('success'):
                    logger.info(f"[比例跟单] 市价跟单成功: {market_order_uid}")
                    
                    await self._save_market_follow_order(
                        market_order_uid, strategy, signal_source_uid, symbol, pos_side,
                        market_position, 0, signal_trade_uid, market_result
                    )
                else:
                    logger.error(f"[比例跟单] 市价跟单失败: {market_order_uid}")
            
        except Exception as e:
            logger.error(f"[比例跟单] 执行限价+市价跟单失败: {e}")

    # ==================== 订单数量调整模块 ====================
    
    def _adjust_order_size(self, symbol, size):
        """调整订单数量，确保符合交易对的最小数量单位"""
        try:
            # 导入合约配置
            
            # 获取交易对的最小张数和精度
            min_size = get_contract_min_sz(symbol)
            precision = get_contract_sz_precision(symbol)
            
            # 根据精度四舍五入
            adjusted_size = round(size, precision)
            
            # 确保不小于最小数量单位
            if adjusted_size < min_size:
                adjusted_size = min_size
            
            logger.info(f"[数量调整] {symbol} 原始数量: {size}, 最小张数: {min_size}, 精度: {precision}, 调整后: {adjusted_size}")
            return adjusted_size
            
        except Exception as e:
            logger.error(f"[数量调整] 调整订单数量失败: {e}")
            return size

    # ==================== 减仓/平仓优化模块 ====================
    
    async def _reduce_customer_position_by_market(self, strategy, symbol, pos_side, reduce_ratio, signal_trade_uid):
        """使用市价单减仓客户仓位"""
        try:
            customer_uid = strategy['customer_uid']
            logger.info(f"[带单员-市价减仓] 客户{customer_uid} 市价减仓: {symbol} {pos_side} 比例: {reduce_ratio:.2%}")
            
            # 获取客户当前持仓
            current_position = await self._get_customer_position(customer_uid, symbol, pos_side)
            if current_position <= 0:
                logger.info(f"[带单员-市价减仓] 客户{customer_uid} 无持仓，跳过市价减仓")
                return
            
            # 计算减仓数量
            need_reduce = current_position * reduce_ratio
            if need_reduce <= 0:
                logger.info(f"[带单员-市价减仓] 客户{customer_uid} 减仓数量为0，跳过")
                return
            
            logger.info(f"[带单员-市价减仓] 客户{customer_uid} 需要减仓: {need_reduce}")
            
            # 获取客户信息
            customer_data = self.db_pool.query(
                "SELECT * FROM customers WHERE customer_uid=%s AND enabled=1",
                (customer_uid,)
            )
            if not customer_data:
                logger.error(f"[带单员-市价减仓] 客户 {customer_uid} 不存在")
                return
            customer = customer_data[0]
            
            # 获取客户客户端
            customer_client = await self._get_existing_customer_client(customer)
            if not customer_client:
                logger.error(f"[带单员-市价减仓] 无法获取客户 {customer_uid} 的客户端")
                return
            
            # 创建市价减仓订单（市价单不需要指定价格）
            order_uid = f"{strategy['id']}{customer_uid[-6:].replace('_', '').replace('-', '')}{signal_trade_uid[-8:]}"
            
            # 下市价减仓单（市价单会自动以最优价格成交）
            order_result = await self._place_market_reduce_order(
                customer_client, order_uid, symbol, pos_side, 
                need_reduce, 0, strategy  # 市价单不需要价格参数
            )
            
            if order_result and order_result.get('success'):
                logger.info(f"[带单员-市价减仓] 市价减仓单下单成功: {order_uid}")
                
                # 记录市价减仓订单到数据库，包含交易所订单ID
                await self._save_market_reduce_order(
                    order_uid, strategy, symbol, pos_side,
                    need_reduce, 0, signal_trade_uid, order_result  # 传递订单结果
                )
            else:
                logger.error(f"[带单员-市价减仓] 市价减仓单下单失败: {order_uid}")
                
        except Exception as e:
            logger.error(f"[带单员-市价减仓] 市价减仓失败: {e}")


    async def _place_market_reduce_order(self, customer_client, order_uid, symbol, pos_side, size, price, strategy):
        """下市价减仓订单"""
        try:
            # 调整数量精度，确保符合交易对的最小数量单位
            adjusted_size = self._adjust_order_size(symbol, abs(size))
            if adjusted_size <= 0:
                logger.warning(f"[带单员-市价减仓] 调整后数量为0，跳过下单")
                return False
            
            # 构建订单参数
            order_params = {
                'instId': symbol,
                'tdMode': 'cross',  # 全仓模式
                'side': 'sell' if pos_side == 'long' else 'buy',
                'ordType': 'market',  # 市价单
                'sz': str(adjusted_size),  # 调整后的数量
                'clOrdId': order_uid,  # 客户端订单ID
                'reduceOnly': True,  # 减仓标识
            }
            
            # 设置杠杆
            leverage = strategy.get('custom_leverage') or strategy.get('leverage', 10)
            order_params['lever'] = str(leverage)
            
            logger.info(f"[带单员-市价减仓] 下市价减仓单参数: {order_params}")
            
            # 下市价单
            result = await customer_client.place_order(**order_params)
            
            if result and result.get('code') == '0':
                logger.info(f"[带单员-市价减仓] 市价减仓单下单成功: {result}")
                # 返回订单信息，包含交易所订单ID
                order_data = result.get('data', [{}])[0]
                return {
                    'success': True,
                    'ordId': order_data.get('ordId'),
                    'clOrdId': order_data.get('clOrdId'),
                    'result': result
                }
            else:
                logger.error(f"[带单员-市价减仓] 市价减仓单下单失败: {result}")
                return {'success': False, 'result': result}
                
        except Exception as e:
            logger.error(f"[带单员-市价减仓] 下市价减仓单异常: {e}")
            return False


    async def _save_market_reduce_order(self, order_uid, strategy, symbol, pos_side, size, price, signal_trade_uid, order_result=None):
        """保存市价减仓订单到数据库"""
        try:
            # 获取交易所订单ID和成交信息
            exchange_order_id = None
            filled_price = 0.0
            filled_size = abs(size)
            
            if order_result and order_result.get('success'):
                exchange_order_id = order_result.get('ordId')
                # 市价单立即成交，使用目标价格作为成交价格
                filled_price = price if price > 0 else 0.0
            
            # 插入市价减仓订单记录
            self.db_pool.execute(
                """INSERT INTO limit_follow_orders 
                   (order_uid, strategy_id, trader_unique_name, customer_uid, symbol, pos_side, 
                    follow_value, target_price, order_size, order_type, status, signal_order_id, 
                    exchange_order_id, filled_price, filled_size, created_at)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())""",
                (order_uid, strategy['id'], strategy['trader_unique_name'], strategy['customer_uid'], 
                 symbol, pos_side, round(float(strategy.get('custom_follow_value') or strategy.get('follow_value') or 0.4), 4),
                 round(float(price), 8), round(float(abs(size)), 8), 'market', 'filled', signal_trade_uid,
                 exchange_order_id, round(float(filled_price), 8), round(float(filled_size), 8))
            )
            
            logger.info(f"[带单员-市价减仓] 市价减仓订单已保存: {order_uid}")
            
        except Exception as e:
            logger.error(f"[带单员-市价减仓] 保存市价减仓订单失败: {e}")

    async def _reduce_customer_position_by_strategy_config(self, strategy, symbol, pos_side, reduce_ratio, signal_trade_uid):
        """保持原有减仓比例逻辑，统一使用市价减仓"""
        try:
            customer_uid = strategy['customer_uid']
            logger.info(f"[统一市价减仓] 客户{customer_uid} 减仓: {symbol} {pos_side} 比例: {reduce_ratio:.2%}")
            
            # 获取客户当前持仓
            current_position = await self._get_customer_position(customer_uid, symbol, pos_side)
            if current_position <= 0:
                logger.info(f"[统一市价减仓] 客户{customer_uid} 无持仓，跳过减仓")
                return
            
            # 保持原有的信号源减仓比例逻辑，不进行额外调整
            # 计算减仓数量：客户持仓 × 信号源减仓比例
            need_reduce = current_position * reduce_ratio
            if need_reduce <= 0:
                logger.info(f"[统一市价减仓] 客户{customer_uid} 减仓数量为0，跳过减仓")
                return
            
            logger.info(f"[统一市价减仓] 客户{customer_uid} 信号源减仓比例: {reduce_ratio:.2%}, 减仓数量: {need_reduce}")
            
            # 统一使用市价减仓（保持原有比例逻辑）
            await self._reduce_customer_position_by_market_optimized(
                strategy, symbol, pos_side, need_reduce, signal_trade_uid
            )
                
        except Exception as e:
            logger.error(f"[统一市价减仓] 减仓失败: {e}")

    async def _reduce_customer_position_by_market_optimized(self, strategy, symbol, pos_side, need_reduce, signal_trade_uid):
        """优化的市价减仓"""
        try:
            customer_uid = strategy['customer_uid']
            logger.info(f"[优化市价减仓] 客户{customer_uid} 市价减仓: {symbol} {pos_side} 数量: {need_reduce}")
            
            # 获取客户信息
            customer_data = self.db_pool.query(
                "SELECT * FROM customers WHERE customer_uid=%s AND enabled=1",
                (customer_uid,)
            )
            if not customer_data:
                logger.error(f"[优化市价减仓] 客户 {customer_uid} 不存在")
                return
            customer = customer_data[0]
            
            # 获取客户客户端
            customer_client = await self._get_existing_customer_client(customer)
            if not customer_client:
                logger.error(f"[优化市价减仓] 无法获取客户 {customer_uid} 的客户端")
                return
            
            # 市价减仓不需要获取价格，直接使用market类型   
            
            # 大额减仓分批执行，减少市场冲击
            if need_reduce > 1000:  # 只有大额减仓才分批
                batch_size = min(1000, need_reduce // 3)  # 每批最多1000张，分3批
                batches = []
                remaining = need_reduce
                
                while remaining > 0:
                    current_batch = min(batch_size, remaining)
                    batches.append(current_batch)
                    remaining -= current_batch
                
                logger.info(f"[优化市价减仓] 大额减仓分批执行: 总数量={need_reduce}, 批次={len(batches)}")
                
                # 执行分批减仓
                for i, batch_size in enumerate(batches):
                    if batch_size <= 0:
                        continue
                        
                    order_uid = f"{strategy['id']}{customer_uid[-4:].replace('_', '').replace('-', '')}{i+1}{signal_trade_uid[-6:]}"
                    
                    # 下市价减仓单
                    order_result = await self._place_market_reduce_order(
                        customer_client, order_uid, symbol, pos_side, 
                        batch_size, 0, strategy  # 市价单不需要价格参数
                    )
                    
                    if order_result and order_result.get('success'):
                        logger.info(f"[优化市价减仓] 批次{i+1}减仓成功: {order_uid}")
                        
                        # 记录减仓订单，包含交易所订单ID
                        await self._save_market_reduce_order(
                            order_uid, strategy, symbol, pos_side,
                            batch_size, 0, signal_trade_uid, order_result  # 传递订单结果
                        )
                        
                        # 批次间延迟，减少市场冲击
                        if i < len(batches) - 1:  # 不是最后一批
                            import asyncio
                            await asyncio.sleep(0.5)  # 延迟500ms
                    else:
                        logger.error(f"[优化市价减仓] 批次{i+1}减仓失败: {order_uid}")
            else:
                # 小额减仓直接执行
                order_uid = f"{strategy['id']}{customer_uid[-6:].replace('_', '').replace('-', '')}{signal_trade_uid[-8:]}"
                
                # 下市价减仓单
                order_result = await self._place_market_reduce_order(
                    customer_client, order_uid, symbol, pos_side, 
                    need_reduce, 0, strategy  # 市价单不需要价格参数
                )
                
                if order_result and order_result.get('success'):
                    logger.info(f"[优化市价减仓] 小额减仓成功: {order_uid}")
                    
                    # 记录减仓订单，包含交易所订单ID
                    await self._save_market_reduce_order(
                        order_uid, strategy, symbol, pos_side,
                        need_reduce, 0, signal_trade_uid, order_result  # 传递订单结果
                    )
                else:
                    logger.error(f"[优化市价减仓] 小额减仓失败: {order_uid}")
                
        except Exception as e:
            logger.error(f"[优化市价减仓] 减仓失败: {e}")