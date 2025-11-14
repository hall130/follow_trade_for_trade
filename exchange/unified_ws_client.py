#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
统一WebSocket客户端
提供统一的交易所WebSocket接口
"""

import asyncio
import time
from typing import Dict, Any, Optional, Callable, List
from .base_client import BaseWebSocketClient, ExchangeType
from .exchange_client_factory import ExchangeClientFactory
from .websocket_state_machine import WebSocketStatus
from utils.logger import logger
from dataclasses import dataclass, field
from enum import Enum


class UnifiedWebSocketClient:
    """统一WebSocket客户端"""
    
    def __init__(self, exchange: ExchangeType, api_key: str = None, 
                 api_secret: str = None, passphrase: str = None, is_demo: bool = True):
        self.exchange = exchange
        self.api_key = api_key
        self.api_secret = api_secret
        self.passphrase = passphrase
        self.is_demo = is_demo
        
        # 创建底层交易所客户端
        self._client = ExchangeClientFactory.create_ws_client(
            exchange, api_key, api_secret, passphrase, is_demo
        )
    
    async def connect(self) -> bool:
        """
        建立WebSocket连接
        
        Returns:
            连接是否成功
        """
        try:
            return await self._client.connect()
        except Exception as e:
            logger.error(f"WebSocket连接失败: {e}")
            return False
    
    async def disconnect(self) -> bool:
        """
        断开WebSocket连接
        
        Returns:
            断开是否成功
        """
        try:
            return await self._client.disconnect()
        except Exception as e:
            logger.error(f"WebSocket断开失败: {e}")
            return False
    
    def close(self):
        """
        同步关闭WebSocket连接
        为了兼容现有代码，提供同步版本的close方法
        """
        try:
            # 检查客户端是否存在
            if not self._client:
                logger.warning("WebSocket客户端不存在，无需关闭")
                return
                
            import asyncio
            
            # 如果底层客户端有同步close方法，直接调用
            if hasattr(self._client, 'close') and not asyncio.iscoroutinefunction(self._client.close):
                self._client.close()
            else:
                # 否则调用异步close或disconnect方法
                try:
                    loop = asyncio.get_event_loop()
                    if loop.is_running():
                        # 如果事件循环正在运行，创建任务
                        if hasattr(self._client, 'close'):
                            asyncio.create_task(self._client.close())
                        else:
                            asyncio.create_task(self._client.disconnect())
                    else:
                        # 如果事件循环没有运行，直接运行
                        if hasattr(self._client, 'close'):
                            loop.run_until_complete(self._client.close())
                        else:
                            loop.run_until_complete(self._client.disconnect())
                except RuntimeError:
                    # 如果没有事件循环，创建新的
                    if hasattr(self._client, 'close'):
                        asyncio.run(self._client.close())
                    else:
                        asyncio.run(self._client.disconnect())
        except Exception as e:
            logger.error(f"WebSocket关闭失败: {e}")
    
    def is_connection_healthy(self) -> bool:
        """
        检查连接是否健康
        
        Returns:
            连接是否健康
        """
        try:
            # 检查客户端是否存在
            if not self._client:
                return False
                
            # 如果底层客户端有is_connection_healthy方法，直接调用
            if hasattr(self._client, 'is_connection_healthy'):
                return self._client.is_connection_healthy()
            
            # 否则进行基本检查
            if not hasattr(self._client, 'ws'):
                return False
            
            ws = getattr(self._client, 'ws', None)
            if not ws:
                return False
            
            # 检查WebSocket状态
            if hasattr(ws, 'closed'):
                return not ws.closed
            
            return True
            
        except Exception as e:
            logger.error(f"检查连接健康状态失败: {e}")
            return False
    
    @property
    def _connected(self) -> bool:
        """连接状态属性"""
        try:
            if hasattr(self._client, '_connected'):
                return self._client._connected
            return False
        except Exception:
            return False
    
    @property
    def _listen_task(self):
        """监听任务属性"""
        try:
            if hasattr(self._client, '_listen_task'):
                return self._client._listen_task
            return None
        except Exception:
            return None
    
    @_listen_task.setter
    def _listen_task(self, value):
        """设置监听任务"""
        try:
            if hasattr(self._client, '_listen_task'):
                self._client._listen_task = value
        except Exception as e:
            logger.error(f"设置监听任务失败: {e}")
    
    @property
    def state_machine(self):
        """状态机属性"""
        try:
            if hasattr(self._client, 'state_machine'):
                return self._client.state_machine
            return None
        except Exception:
            return None
    
    @property
    def ws(self):
        """WebSocket对象属性"""
        try:
            if hasattr(self._client, 'ws'):
                return self._client.ws
            return None
        except Exception:
            return None
    
    async def _listen(self):
        """监听方法"""
        try:
            if hasattr(self._client, '_listen'):
                return await self._client._listen()
            else:
                logger.warning("底层客户端没有_listen方法")
                return None
        except Exception as e:
            logger.error(f"监听方法调用失败: {e}")
            return None
    
    async def subscribe(self, channel: str, callback=None, **kwargs):
        """订阅频道"""
        try:
            if hasattr(self._client, 'subscribe'):
                return await self._client.subscribe(channel, callback, **kwargs)
            else:
                logger.error("底层客户端没有subscribe方法")
                return False
        except Exception as e:
            logger.error(f"订阅频道失败: {e}")
            return False
    
    async def unsubscribe(self, channel: str, **kwargs):
        """取消订阅频道"""
        try:
            if hasattr(self._client, 'unsubscribe'):
                return await self._client.unsubscribe(channel, **kwargs)
            else:
                logger.error("底层客户端没有unsubscribe方法")
                return False
        except Exception as e:
            logger.error(f"取消订阅频道失败: {e}")
            return False
    
    async def place_order(self, **kwargs):
        """下单模块 - 使用REST API进行真实下单"""
        try:
            if hasattr(self._client, 'place_order'):
                return await self._client.place_order(**kwargs)
            else:
                logger.error("底层客户端没有place_order方法")
                return {"code": "1", "data": [{"sCode": "1", "sMsg": "底层客户端没有place_order方法"}]}
        except Exception as e:
            logger.error(f"下单失败: {e}")
            return {"code": "1", "data": [{"sCode": "1", "sMsg": f"下单失败: {str(e)}"}]}
    
    async def get_account_info(self, **kwargs):
        """获取账户信息"""
        try:
            if hasattr(self._client, 'get_account_info'):
                return await self._client.get_account_info(**kwargs)
            else:
                logger.error("底层客户端没有get_account_info方法")
                return {"success": False, "error": "底层客户端没有get_account_info方法"}
        except Exception as e:
            logger.error(f"获取账户信息失败: {e}")
            return {"success": False, "error": f"获取账户信息失败: {str(e)}"}
    
    async def get_positions(self, **kwargs):
        """获取持仓信息"""
        try:
            if hasattr(self._client, 'get_positions'):
                return await self._client.get_positions(**kwargs)
            else:
                logger.error("底层客户端没有get_positions方法")
                return {"success": False, "error": "底层客户端没有get_positions方法"}
        except Exception as e:
            logger.error(f"获取持仓信息失败: {e}")
            return {"success": False, "error": f"获取持仓信息失败: {str(e)}"}
    
    async def get_balance(self, **kwargs):
        """获取余额信息"""
        try:
            if hasattr(self._client, 'get_balance'):
                return await self._client.get_balance(**kwargs)
            else:
                logger.error("底层客户端没有get_balance方法")
                return {"success": False, "error": "底层客户端没有get_balance方法"}
        except Exception as e:
            logger.error(f"获取余额信息失败: {e}")
            return {"success": False, "error": f"获取余额信息失败: {str(e)}"}
    
    async def subscribe_ticker(self, symbol: str, callback: Callable) -> bool:
        """
        订阅行情数据
        
        Args:
            symbol: 交易对
            callback: 回调函数
        
        Returns:
            订阅是否成功
        """
        try:
            return await self._client.subscribe_ticker(symbol, callback)
        except Exception as e:
            logger.error(f"订阅行情失败: {e}")
            return False
    
    async def subscribe_orderbook(self, symbol: str, callback: Callable) -> bool:
        """
        订阅深度数据
        
        Args:
            symbol: 交易对
            callback: 回调函数
        
        Returns:
            订阅是否成功
        """
        try:
            return await self._client.subscribe_orderbook(symbol, callback)
        except Exception as e:
            logger.error(f"订阅深度失败: {e}")
            return False
    
    async def subscribe_trades(self, symbol: str, callback: Callable) -> bool:
        """
        订阅交易数据
        
        Args:
            symbol: 交易对
            callback: 回调函数
        
        Returns:
            订阅是否成功
        """
        try:
            return await self._client.subscribe_trades(symbol, callback)
        except Exception as e:
            logger.error(f"订阅交易数据失败: {e}")
            return False
    
    async def subscribe_orders(self, callback: Callable) -> bool:
        """
        订阅订单更新
        
        Args:
            callback: 回调函数
        
        Returns:
            订阅是否成功
        """
        try:
            return await self._client.subscribe_orders(callback)
        except Exception as e:
            logger.error(f"订阅订单更新失败: {e}")
            return False
    
    async def subscribe_positions(self, callback: Callable) -> bool:
        """
        订阅持仓更新
        
        Args:
            callback: 回调函数
        
        Returns:
            订阅是否成功
        """
        try:
            return await self._client.subscribe_positions(callback)
        except Exception as e:
            logger.error(f"订阅持仓更新失败: {e}")
            return False
    
    async def subscribe_balance(self, callback: Callable) -> bool:
        """
        订阅余额更新
        
        Args:
            callback: 回调函数
        
        Returns:
            订阅是否成功
        """
        try:
            return await self._client.subscribe_balance(callback)
        except Exception as e:
            logger.error(f"订阅余额更新失败: {e}")
            return False
    
    async def unsubscribe(self, channel: str) -> bool:
        """
        取消订阅
        
        Args:
            channel: 频道名称
        
        Returns:
            取消订阅是否成功
        """
        try:
            return await self._client.unsubscribe(channel)
        except Exception as e:
            logger.error(f"取消订阅失败: {e}")
            return False
    
    def is_connected(self) -> bool:
        """
        检查连接状态
        
        Returns:
            是否已连接
        """
        try:
            return self._client.is_connected()
        except Exception as e:
            logger.error(f"检查连接状态失败: {e}")
            return False
    
    def get_connection_status(self) -> Dict[str, Any]:
        """
        获取连接状态信息
        
        Returns:
            连接状态信息
        """
        try:
            if hasattr(self._client, 'get_connection_status'):
                status = self._client.get_connection_status()
                status['exchange'] = self.exchange.value
                return status
            else:
                return {
                    "exchange": self.exchange.value,
                    "connected": self.is_connected(),
                    "is_demo": self.is_demo
                }
        except Exception as e:
            logger.error(f"获取连接状态失败: {e}")
            return {
                "exchange": self.exchange.value,
                "connected": False,
                "error": str(e)
            }
    
    def get_exchange_type(self) -> str:
        """获取交易所类型"""
        return self.exchange.value
    
    def is_demo_mode(self) -> bool:
        """检查是否为演示模式"""
        return self.is_demo


# 全局客户端管理器
_global_client_manager = None

def get_global_client_manager():
    """获取全局客户端管理器"""
    global _global_client_manager
    if _global_client_manager is None:
        _global_client_manager = WebSocketClientManager()
    return _global_client_manager


class WebSocketClientManager:
    """WebSocket客户端管理器"""
    
    def __init__(self):
        
        self._clients = {}  # 客户端池
        self._client_locks = {}  # 客户端锁
        self._connection_pool = {}  # 连接池
        self._stats = {
            'total_clients': 0,
            'active_clients': 0,
            'total_connections': 0,
            'failed_connections': 0,
            'memory_usage_mb': 0.0
        }
        self._cleanup_task = None
        self._running = False
        
        # 延迟启动清理任务（避免在__init__中创建异步任务）
        self._cleanup_task = None
    
    async def get_client(self, client_key: str, is_demo: bool = False, 
                        api_key: str = '', api_secret: str = '', passphrase: str = ''):
        """获取或创建WebSocket客户端 - 防止重复创建"""
        try:
            # 启动清理任务（如果还没有启动）
            if not self._running:
                await self._start_cleanup_task()
            # 检查是否已存在客户端
            if client_key in self._clients:
                client = self._clients[client_key]
                if client and client.is_connection_healthy():
                    logger.info(f"复用现有客户端: {client_key}")
                    return client
                else:
                    # 客户端存在但不健康，清理后重新创建
                    logger.warning(f"客户端 {client_key} 不健康，清理后重新创建")
                    await self._cleanup_client(client_key)
            
            # 创建新客户端
            async with self._get_client_lock(client_key):
                # 双重检查，防止重复创建
                if client_key in self._clients:
                    return self._clients[client_key]
                
                logger.info(f"创建新客户端: {client_key}")
                # 使用统一接口创建客户端
                from exchange.exchange_factory import create_exchange_client
                client = create_exchange_client(
                    exchange='okx',
                    client_type='ws',
                    api_key=api_key,
                    api_secret=api_secret,
                    passphrase=passphrase,
                    is_demo=is_demo
                )
                
                # 设置客户端唯一标识
                client._connection_id = client_key
                
                # 添加到客户端池
                self._clients[client_key] = client
                self._stats['total_clients'] += 1
                self._stats['active_clients'] += 1
                
                # 记录连接信息
                self._connection_pool[client_key] = {
                    'created_time': time.time(),
                    'last_used': time.time(),
                    'connection_count': 0,
                    'is_demo': is_demo
                }
                
                logger.info(f"客户端 {client_key} 创建成功")
                return client
                
        except Exception as e:
            logger.error(f"获取客户端 {client_key} 失败: {e}")
            self._stats['failed_connections'] += 1
            raise
    
    def _get_client_lock(self, client_key: str):
        """获取客户端锁"""
        if client_key not in self._client_locks:
            self._client_locks[client_key] = asyncio.Lock()
        return self._client_locks[client_key]
    
    async def _cleanup_client(self, client_key: str):
        """清理指定客户端"""
        try:
            if client_key in self._clients:
                client = self._clients[client_key]
                if client:
                    try:
                        # 检查客户端状态，避免无效的状态转换
                        if hasattr(client, 'state_machine') and client.state_machine is not None:
                            # 安全访问current_status
                            try:
                                current_status = getattr(client.state_machine, 'current_status', None)
                                if current_status and current_status != 'INIT':
                                    # 安全调用close方法
                                    if hasattr(client, 'close'):
                                        close_method = getattr(client, 'close')
                                        if asyncio.iscoroutinefunction(close_method):
                                            await close_method()
                                        else:
                                            close_method()
                                else:
                                    # 如果客户端处于INIT状态或没有状态，直接清理资源
                                    if hasattr(client, '_cleanup_connection'):
                                        cleanup_method = getattr(client, '_cleanup_connection')
                                        if asyncio.iscoroutinefunction(cleanup_method):
                                            await cleanup_method()
                                        else:
                                            cleanup_method()
                                    elif hasattr(client, 'close'):
                                        close_method = getattr(client, 'close')
                                        if asyncio.iscoroutinefunction(close_method):
                                            await close_method()
                                        else:
                                            close_method()
                            except AttributeError:
                                # state_machine存在但没有current_status属性，直接清理
                                if hasattr(client, '_cleanup_connection'):
                                    cleanup_method = getattr(client, '_cleanup_connection')
                                    if asyncio.iscoroutinefunction(cleanup_method):
                                        await cleanup_method()
                                    else:
                                        cleanup_method()
                                elif hasattr(client, 'close'):
                                    close_method = getattr(client, 'close')
                                    if asyncio.iscoroutinefunction(close_method):
                                        await close_method()
                                    else:
                                        close_method()
                        else:
                            # 没有state_machine，直接调用close
                            if hasattr(client, 'close'):
                                close_method = getattr(client, 'close')
                                if asyncio.iscoroutinefunction(close_method):
                                    await close_method()
                                else:
                                    close_method()
                            elif hasattr(client, '_cleanup_connection'):
                                cleanup_method = getattr(client, '_cleanup_connection')
                                if asyncio.iscoroutinefunction(cleanup_method):
                                    await cleanup_method()
                                else:
                                    cleanup_method()
                    except Exception as e:
                        logger.error(f"关闭客户端 {client_key} 异常: {e}")
                        import traceback
                        logger.debug(traceback.format_exc())
                
                # 从池中移除
                del self._clients[client_key]
                if client_key in self._connection_pool:
                    del self._connection_pool[client_key]
                
                self._stats['active_clients'] = max(0, self._stats['active_clients'] - 1)
                logger.info(f"客户端 {client_key} 已清理")
                
        except Exception as e:
            logger.error(f"清理客户端 {client_key} 异常: {e}")
            import traceback
            logger.debug(traceback.format_exc())
    
    async def _start_cleanup_task(self):
        """启动清理任务"""
        if self._running:
            return
        
        self._running = True
        self._cleanup_task = asyncio.create_task(self._cleanup_loop())
        logger.info("WebSocket客户端管理器清理任务已启动")
    
    async def _cleanup_loop(self):
        """清理循环"""
        try:
            while self._running:
                await asyncio.sleep(300)  # 5分钟清理一次
                await self._perform_cleanup()
        except asyncio.CancelledError:
            logger.info("清理任务被取消")
        except Exception as e:
            logger.error(f"清理任务异常: {e}")
    
    async def _perform_cleanup(self):
        """执行清理"""
        try:
            current_time = time.time()
            clients_to_cleanup = []
            
            # 检查需要清理的客户端
            for client_key, client_info in self._connection_pool.items():
                # 检查连接超时（1小时）
                if current_time - client_info['created_time'] > 3600:
                    clients_to_cleanup.append(client_key)
                    continue
                
                # 检查最后使用时间（30分钟）
                if current_time - client_info['last_used'] > 1800:
                    clients_to_cleanup.append(client_key)
                    continue
            
            # 执行清理
            for client_key in clients_to_cleanup:
                await self._cleanup_client(client_key)
            
            # 更新统计信息
            self._update_stats()
            
            if clients_to_cleanup:
                logger.info(f"清理了 {len(clients_to_cleanup)} 个客户端")
                
        except Exception as e:
            logger.error(f"执行清理异常: {e}")
    
    def _update_stats(self):
        """更新统计信息"""
        try:
            # 计算内存使用
            total_memory = 0
            for client in self._clients.values():
                if client and hasattr(client, 'metrics'):
                    # 估算每个客户端的内存使用（约1-2MB）
                    total_memory += 1.5
            
            self._stats['memory_usage_mb'] = total_memory
            self._stats['active_clients'] = len(self._clients)
            
        except Exception as e:
            logger.error(f"更新统计信息异常: {e}")
    
    def get_stats(self) -> Dict:
        """获取管理器统计信息"""
        self._update_stats()
        return self._stats.copy()
    
    def get_client_status(self) -> Dict:
        """获取所有客户端状态"""
        status = {}
        for client_key, client in self._clients.items():
            if client:
                try:
                    status[client_key] = client.get_connection_status()
                except Exception as e:
                    status[client_key] = {'error': str(e)}
        return status
    
    async def close_all_clients(self):
        """关闭所有客户端"""
        try:
            logger.info("开始关闭所有WebSocket客户端...")
            
            # 停止清理任务
            self._running = False
            if self._cleanup_task:
                self._cleanup_task.cancel()
                try:
                    await self._cleanup_task
                except asyncio.CancelledError:
                    pass
            
            # 关闭所有客户端
            cleanup_tasks = []
            for client_key in list(self._clients.keys()):
                cleanup_tasks.append(self._cleanup_client(client_key))
            
            if cleanup_tasks:
                await asyncio.gather(*cleanup_tasks, return_exceptions=True)
            
            logger.info("所有WebSocket客户端已关闭")
            
        except Exception as e:
            logger.error(f"关闭所有客户端异常: {e}")
    
    def __del__(self):
        """析构函数"""
        try:
            if self._running:
                asyncio.create_task(self.close_all_clients())
        except:
            pass

# 便捷函数
def create_unified_ws_client(exchange: str, api_key: str = None, 
                            api_secret: str = None, passphrase: str = None, 
                            is_demo: bool = True) -> UnifiedWebSocketClient:
    """
    创建统一WebSocket客户端的便捷函数
    
    Args:
        exchange: 交易所名称 ('okx', 'binance', 'bybit')
        api_key: API密钥（可选）
        api_secret: API密钥（可选）
        passphrase: 密码短语（仅OKX需要，可选）
        is_demo: 是否使用演示模式
    
    Returns:
        统一WebSocket客户端实例
    """
    try:
        exchange_type = ExchangeType(exchange.lower())
    except ValueError:
        raise ValueError(f"不支持的交易所: {exchange}")
    
    return UnifiedWebSocketClient(exchange_type, api_key, api_secret, passphrase, is_demo)
                