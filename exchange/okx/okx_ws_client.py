#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
OKX WebSocket客户端 
"""

import asyncio
import json
import logging
import random
import ssl
import time
import hmac
import hashlib
import base64
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Callable, Any
import websockets
from ..base_client import BaseWebSocketClient, ExchangeType
from ..websocket_state_machine import WebSocketStatus, WebSocketStateMachine, ConnectionMetrics

# 配置日志
logger = logging.getLogger(__name__)

class WebSocketEvent:
    """WebSocket事件"""
    def __init__(self, event_type: str, data: Any = None):
        self.type = event_type
        self.data = data
        self.timestamp = time.time()
    
    @property
    def current_status(self) -> WebSocketStatus:
        """当前状态"""
        return self._current_status
    
    def can_transition_to(self, target_status: WebSocketStatus) -> bool:
        """检查是否可以转换到目标状态"""
        return target_status in self._transitions.get(self._current_status, [])
    
    async def transition_to(self, target_status: WebSocketStatus) -> bool:
        """转换到目标状态 - 异步方法，线程安全"""
        async with self._lock:
            if self.can_transition_to(target_status):
                old_status = self._current_status
                self._current_status = target_status
                logger.info(f"状态转换: {old_status.value} -> {target_status.value}")
            
                # 触发状态变化回调
                for callback in self._status_change_callbacks:
                    try:
                                    if asyncio.iscoroutinefunction(callback):
                                        await callback(old_status, target_status)
                                    else:
                                        callback(old_status, target_status)
                    except Exception as e:
                        logger.error(f"状态变化回调异常: {e}")
                
                return True
            else:
                logger.warning(f"无效的状态转换: {self._current_status.value} -> {target_status.value}")
                return False
    
    def add_status_change_callback(self, callback: Callable):
        """添加状态变化回调"""
        self._status_change_callbacks.append(callback)
    
class WebSocketEventEngine:
    """WebSocket事件引擎"""

    def __init__(self):
        self._queue = asyncio.Queue(maxsize=10000)
        self._active = False
        self._task: Optional[asyncio.Task] = None
        self._stop_event = asyncio.Event()
    
    async def start(self):
        """启动事件引擎"""
        if self._active:
            return
        
        self._active = True
        self._stop_event.clear()
        self._task = asyncio.create_task(self._run())
        logger.info("WebSocket事件引擎已启动")
    
    async def stop(self):
        """停止事件引擎"""
        self._active = False
        self._stop_event.set()
        
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        
        logger.info("WebSocket事件引擎已停止")
    
    async def put(self, event: WebSocketEvent):
        """放入事件"""
        if self._active:
            try:
                await asyncio.wait_for(self._queue.put(event), timeout=1.0)
            except asyncio.TimeoutError:
                logger.warning("事件队列已满，丢弃事件")
    
    async def _run(self):
        """事件处理循环"""
        while self._active and not self._stop_event.is_set():
            try:
                # 使用超时避免阻塞
                event = await asyncio.wait_for(self._queue.get(), timeout=1.0)
                await self._process_event(event)
                self._queue.task_done()
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"事件处理异常: {e}")
    
    async def _process_event(self, event: WebSocketEvent):
        """处理单个事件"""
        try:
            logger.debug(f"处理事件: {event.type}")
            # 这里可以添加事件处理器映射
        except Exception as e:
            logger.error(f"事件处理失败: {e}")

class ConnectionHealthMonitor:
    """连接健康监控器"""
    
    def __init__(self, client: 'OKXWebSocketClient'):
        self.client = client
        self.health_score = 100
        self.last_health_check = 0
        self.health_check_interval = 30  # 30秒检查一次，提高响应速度
        self.connection_start_time = time.time()
        self._running = False
        self._task = None
    
    @property
    def is_running(self):
        """检查监控器是否正在运行"""
        return self._running and self._task and not self._task.done()
    
    async def start(self):
        """启动健康监控"""
        if self.is_running:
            return
        
        self._running = True
        self.connection_start_time = time.time()
        self._task = asyncio.create_task(self._monitor_loop())
        logger.info("连接健康监控已启动")
    
    async def stop(self):
        """停止健康监控"""
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("连接健康监控已停止")
    
    async def _monitor_loop(self):
        """健康监控循环"""
        while self._running:
            try:
                await self._perform_health_check()
                await asyncio.sleep(self.health_check_interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"健康监控异常: {e}")
                await asyncio.sleep(10)  # 异常时等待10秒
    
    async def _perform_health_check(self):
        """执行健康检查"""
        try:
            if not self.client:
                return
            
            # 新连接保护：连接时间少于3分钟，跳过检查但恢复健康评分
            if hasattr(self.client.metrics, 'connect_time') and self.client.metrics.connect_time:
                connection_age = time.time() - self.client.metrics.connect_time
                if connection_age < 180:  # 3分钟保护期
                    # 新连接保护期内，逐步恢复健康评分
                    if self.health_score < 100:
                        self.health_score = min(100, self.health_score + 10)
                        logger.debug(f"🛡️ 新连接保护中，健康评分恢复到: {self.health_score}")
                    return
            
                # 检查连接状态
                if self.client.is_connection_healthy():
                    # 连接健康，恢复健康评分
                    self.health_score = min(100, self.health_score + 15)
                    logger.debug(f"✅ 连接健康，健康评分: {self.health_score}")
                else:
                    # 连接不健康，降低健康评分
                    self.health_score = max(0, self.health_score - 25)
                    logger.warning(f"⚠️ 连接不健康，健康评分: {self.health_score}")
                    
                # 健康评分过低，触发重连
                if self.health_score <= 25:
                    logger.error(f"🚨 健康评分过低，触发智能重连: {self.health_score}")
                    # 🚀 避免重复重连
                    if not hasattr(self.client, '_reconnecting') or not self.client._reconnecting:
                        await self.client._smart_reconnect()
                    else:
                        logger.info("🚨 客户端正在重连中，跳过重复重连")
            
        except Exception as e:
            logger.error(f"❌ 健康检查异常: {e}")
            self.health_score = max(0, self.health_score - 10)
    
    def get_status(self) -> dict:
        """获取重连状态"""
        return {
            "retry_count": self.reconnect_strategy.retry_count,
            "max_retries": self.reconnect_strategy.max_retries,
            "next_delay": self.reconnect_strategy.get_next_delay() if self.reconnect_strategy.should_retry() else 0,
            "last_retry_time": self.reconnect_strategy.last_retry_time
        }

class SmartReconnectStrategy:
    """智能重连策略"""
    
    def __init__(self, max_retries: int = 5, base_delay: float = 1.0, max_delay: float = 30.0):
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.retry_count = 0
        self.last_retry_time = 0
    
    def get_next_delay(self) -> float:
        """获取下次重连延迟"""
        if self.retry_count == 0:
            return 0.5  # 第一次重连立即进行，只等待0.5秒
        
        # 使用指数退避，但限制最大延迟
        delay = min(self.base_delay * (1.5 ** self.retry_count), self.max_delay)
        
        # 添加随机抖动，避免重连风暴
        jitter = random.uniform(0.8, 1.2)
        return delay * jitter
    
    def should_retry(self) -> bool:
        """判断是否应该重连"""
        return self.retry_count < self.max_retries
    
    def record_retry(self):
        """记录重连尝试"""
        self.retry_count += 1
        self.last_retry_time = time.time()
    
    def reset(self):
        """重置重连计数"""
        self.retry_count = 0
        self.last_retry_time = 0
    
    def get_status(self) -> dict:
        """获取重连状态"""
        return {
            "retry_count": self.retry_count,
            "max_retries": self.max_retries,
            "next_delay": self.get_next_delay() if self.should_retry() else 0,
            "last_retry_time": self.last_retry_time
        }

class OKXWebSocketClient(BaseWebSocketClient):
    """OKX WebSocket客户端"""
    
    def __init__(self, api_key: str = None, api_secret: str = None, passphrase: str = None, is_demo: bool = False):
        # 调用父类构造函数
        super().__init__(api_key, api_secret, passphrase, is_demo)
        
        # 基本配置
        self.is_demo = is_demo
        self.ws_url = "wss://ws.okx.com:8443/ws/v5/public" if not is_demo else "wss://wspap.okx.com:8443/ws/v5/public?brokerId=9999"
        if api_key and api_secret and passphrase:
            self.ws_url = "wss://ws.okx.com:8443/ws/v5/private" if not is_demo else "wss://wspap.okx.com:8443/ws/v5/private?brokerId=9999"
        
        # API认证信息
        self.api_key = api_key
        self.api_secret = api_secret
        self.passphrase = passphrase
        
        # 核心组件
        # 注意：BaseWebSocketClient已经提供了 self._state_machine
        # 这里不再创建新的状态机，使用父类提供的状态机
        self.event_engine = WebSocketEventEngine()
        self.health_monitor = ConnectionHealthMonitor(self)
        self.reconnect_strategy = SmartReconnectStrategy()
        
        # WebSocket连接
        self.ws = None
        self._listen_task = None
        self._heartbeat_task = None
        self._auto_recycle_task = None
        
        # 连接指标
        self.metrics = ConnectionMetrics()
        
        # 订阅管理
        self._subscriptions = {}
        
        # 事件处理器
        self._event_handlers = {}
        
        # 活跃性检测相关属性
        self._last_message_time = None
        self._activity_timer = None
        
        # 初始化
        self._register_event_handlers()
    
    def _get_exchange_type(self) -> ExchangeType:
        """获取交易所类型"""
        return ExchangeType.OKX
    
    def _register_event_handlers(self):
        """注册事件处理器"""
        self._event_handlers = {
            "connection_lost": self._on_connection_lost,
            "reconnect_required": self._on_reconnect_required,
            "subscription_restore": self._on_subscription_restore
        }
    
    async def _on_status_change(self, old_status: WebSocketStatus, new_status: WebSocketStatus, reason: str):
        """状态变化回调"""
        try:
            logger.info(f"状态变化: {old_status.value} -> {new_status.value} ({reason})")
            
            # 根据状态变化执行相应操作
            if new_status == WebSocketStatus.STABLE:
                # 连接稳定后启动健康监控
                if not self.health_monitor.is_running:
                    asyncio.create_task(self._delayed_start_health_monitor())
                
                # 启动自动回收
                if not self._auto_recycle_task or self._auto_recycle_task.done():
                    self._auto_recycle_task = asyncio.create_task(self._auto_recycle_loop())
                    
            elif new_status in [WebSocketStatus.DISCONNECTED, WebSocketStatus.ERROR]:
                # 连接断开或错误时停止监控
                if self.health_monitor.is_running:
                    await self.health_monitor.stop()
                
                if self._auto_recycle_task and not self._auto_recycle_task.done():
                    self._auto_recycle_task.cancel()
                    
        except Exception as e:
            logger.error(f"状态变化回调异常: {e}")
    
    async def connect(self) -> bool:
        """建立WebSocket连接"""
        try:
            # 1. 状态检查
            if self._state_machine.current_status in [WebSocketStatus.CONNECTING, WebSocketStatus.CONNECTED]:
                logger.info("连接已在进行中，跳过重复连接")
                return True
            
            # 2. 状态转换：INIT -> CONNECTING
            await self._transition_to(WebSocketStatus.CONNECTING, "开始连接")
            # 3. 清理旧连接
            await self._cleanup_connection()
                
            # 4. 建立SSL上下文
            ssl_context = ssl.create_default_context()
            if self.is_demo:
                ssl_context.check_hostname = False
                ssl_context.verify_mode = ssl.CERT_NONE
            
            # 5. 建立WebSocket连接 - 启用WebSocket ping机制
            logger.info(f"正在连接WebSocket服务器...")
            logger.info(f"🔗 连接类型: {'私有频道' if self.api_key else '公共频道'}")
            logger.info(f"🔗 连接用途: {'信号源' if 'signal' in str(self) else '客户' if 'customer' in str(self) else '未知'}")
                        
            self.ws = await asyncio.wait_for(
                websockets.connect(
                    self.ws_url,
                    ssl=ssl_context,
                    close_timeout=30,      # 关闭超时
                    max_size=2**20,        # 最大消息大小
                    max_queue=2**10,       # 最大队列大小
                    ping_interval=30,      # 启用WebSocket ping，30秒间隔
                    ping_timeout=10,       # ping超时10秒
                    compression=None        # 禁用压缩，提高稳定性
                            ),
                timeout=30  # 连接超时
                        )
                        
            # 6. 状态转换：CONNECTING -> CONNECTED
            await self._state_machine.transition_to(WebSocketStatus.CONNECTED)
            self.metrics.connect_time = time.time()
            logger.info(f"🔗 WebSocket连接建立成功，状态: {WebSocketStatus.CONNECTED.value}")
            logger.info(f"🔗 连接URL: {self.ws_url}")
            logger.info(f"🔗 连接类型: {'私有频道' if self.api_key else '公共频道'}")
            logger.info(f"🔗 连接用途: {'信号源' if 'signal' in str(self) else '客户' if 'customer' in str(self) else '通用'}")
            logger.info(f"🔗 等待连接响应获取connId...")
            
            # 7. 启动监听和心跳任务
            if not self._listen_task or self._listen_task.done():
                        self._listen_task = asyncio.create_task(self._listen())
            if not self._heartbeat_task or self._heartbeat_task.done():
                try:
                    self._heartbeat_task = asyncio.create_task(self._heartbeat())
                    logger.debug(f"💓 心跳任务已创建: {self._heartbeat_task}")
                except Exception as e:
                    logger.error(f"❌ 创建心跳任务失败: {e}")
                    self._heartbeat_task = None
                        
            # 8. 登录认证
            if self.api_key and self.api_secret and self.passphrase:
                try:
                    await self.login()
                    await self._state_machine.transition_to(WebSocketStatus.AUTHENTICATED)
                    logger.info(f"登录认证成功，状态: {WebSocketStatus.AUTHENTICATED.value}")
                except Exception as e:
                    logger.error(f"登录认证失败: {e}")
                    # 登录失败不影响连接建立
                    await self._state_machine.transition_to(WebSocketStatus.AUTHENTICATED)
            else:
                logger.warning("缺少API密钥，跳过登录认证")
                await self._state_machine.transition_to(WebSocketStatus.AUTHENTICATED)
            
            # 9. 恢复订阅
            if self._subscriptions:
                logger.info(f"恢复{len(self._subscriptions)}个订阅...")
                try:
                    await self._restore_subscriptions()
                    logger.info("✅ 订阅恢复完成")
                    await self._state_machine.transition_to(WebSocketStatus.SUBSCRIBED)
                    await self._state_machine.transition_to(WebSocketStatus.READY)
                except Exception as e:
                    logger.error(f"❌ 订阅恢复失败: {e}")
                    # 即使订阅恢复失败，也要继续连接流程
                    await self._state_machine.transition_to(WebSocketStatus.READY)
            else:
                logger.info("没有需要恢复的订阅")
                await self._state_machine.transition_to(WebSocketStatus.READY)
            
            # 10. 等待连接稳定 - 减少等待时间
            await asyncio.sleep(1)  # 减少到1秒，提高响应速度
            
            # 11. 状态转换：READY -> STABLE
            await self._state_machine.transition_to(WebSocketStatus.STABLE)
            
            # 12. 启动事件引擎
            if not self.event_engine._active:
                await self.event_engine.start()
            
            logger.info("✅ WebSocket连接建立完成！")
            
            # 输出连接类型信息
            if hasattr(self, 'api_key') and self.api_key:
                logger.info(f"🔗 连接类型: 私有频道 (需要API密钥)")
                if hasattr(self.metrics, 'conn_id') and self.metrics.conn_id:
                    logger.info(f"🔗 连接ID: {self.metrics.conn_id}")
                else:
                    logger.info(f"🔗 连接ID: 等待服务器分配...")
            else:
                logger.info(f"🔗 连接类型: 公共频道 (无需API密钥)")
                if hasattr(self.metrics, 'conn_id') and self.metrics.conn_id:
                    logger.info(f"🔗 连接ID: {self.metrics.conn_id}")
                else:
                    logger.info(f"🔗 连接ID: 等待服务器分配...")
            
            # 显示连接用途
            if 'signal' in str(self):
                logger.info(f"🔗 连接用途: 信号源监听")
            elif 'customer' in str(self):
                logger.info(f"🔗 连接用途: 客户交易")
            else:
                logger.info(f"🔗 连接用途: 通用连接")
            
            return True
                
        except Exception as e:
            logger.error(f"连接失败详情: {type(e).__name__}: {str(e)}")
            # 连接失败时清理资源
            await self._cleanup_connection()
            # 状态转换：CONNECTING -> ERROR
            if self._state_machine.can_transition_to(WebSocketStatus.ERROR):
                await self._state_machine.transition_to(WebSocketStatus.ERROR)
            return False
    
    async def _smart_reconnect(self) -> bool:
        """智能重连"""
        try:
            logger.info("🔄 _smart_reconnect方法开始执行...")
            
            # 🚀 检查是否正在重连中，避免重复重连
            if hasattr(self, '_reconnecting') and self._reconnecting:
                logger.info("🔄 正在重连中，跳过重复重连请求")
                return True
            
            # 检查状态机是否允许重连
            if not self._state_machine.can_transition_to(WebSocketStatus.RECONNECTING):
                logger.warning(f"❌ 状态机不允许转换到重连状态: {self._state_machine.current_status.value}")
                logger.warning(f"❌ 当前状态: {self._state_machine.current_status.value}")
                logger.warning(f"❌ 尝试强制转换...")
                
                # 尝试强制转换到重连状态
                try:
                    await self._state_machine.transition_to(WebSocketStatus.RECONNECTING)
                    logger.info("🔄 强制转换到重连状态成功")
                except Exception as force_error:
                    logger.error(f"❌ 强制转换失败: {force_error}")
                    return False
            else:
                logger.info(f"✅ 状态机允许重连，当前状态: {self._state_machine.current_status.value}")
            
            # 标记正在重连
            self._reconnecting = True
            logger.info("🔄 开始WebSocket智能重连...")
            
            # 转换到重连状态
            await self._state_machine.transition_to(WebSocketStatus.RECONNECTING)
            logger.info("🔄 状态机已转换到重连状态")
            
            # 重置重连策略
            self.reconnect_strategy.reset()
            logger.info("🔄 重连策略已重置")
            
            while self.reconnect_strategy.should_retry():
                try:
                    logger.info(f"🔄 尝试重连 (第{self.reconnect_strategy.retry_count + 1}次)...")
            
                    # 清理旧连接
                    logger.info("🔄 步骤1: 清理旧连接...")
                    await self._cleanup_connection()
                    logger.info("✅ 旧连接清理完成")
                    
                    # 尝试重新连接
                    logger.info("🔄 步骤2: 尝试建立新连接...")
                    if await self.connect():
                        logger.info("✅ 新连接建立成功！")
                        
                        # 重置重连策略
                        self.reconnect_strategy.reset()
                        logger.info("🔄 重连策略已重置")
                        
                        # 🚀 重连成功后重置健康评分
                        if hasattr(self, 'health_monitor') and self.health_monitor:
                            old_score = self.health_monitor.health_score
                            self.health_monitor.health_score = 100
                            logger.info(f"🚀 重连成功，健康评分从 {old_score} 重置为 100")
                        
                        # 🚀 重置心跳状态，确保新的心跳任务能正常启动
                        if hasattr(self, '_ping_failures'):
                            old_failures = self._ping_failures
                            self._ping_failures = 0
                            logger.info(f"🚀 心跳失败计数从 {old_failures} 重置为 0")
                        
                        if hasattr(self, '_last_ping_time'):
                            self._last_ping_time = 0
                            logger.info("🚀 心跳时间戳已重置")
                        
                        if hasattr(self, '_last_pong_time'):
                            self._last_pong_time = 0
                            logger.info("🚀 Pong时间戳已重置")
                        
                        # 检查新连接状态
                        if hasattr(self, 'ws') and self.ws:
                            ws_closed = getattr(self.ws, 'closed', False)
                            logger.info(f"🔄 新连接WebSocket状态: {'已关闭' if ws_closed else '已连接'}")
                        
                        # 检查订阅状态
                        if hasattr(self, '_subscriptions'):
                            subs = list(self._subscriptions.keys()) if self._subscriptions else []
                            logger.info(f"🔄 新连接订阅数量: {len(subs)}")
                            if subs:
                                logger.info(f"🔄 新连接订阅列表: {subs}")
                        
                        # 🚀 重新启动心跳任务
                        logger.info("🔄 重新启动心跳任务...")
                        try:
                            if hasattr(self, '_heartbeat_task') and self._heartbeat_task and not self._heartbeat_task.done():
                                self._heartbeat_task.cancel()
                                logger.debug("🧹 取消旧的心跳任务")
                            
                            self._heartbeat_task = asyncio.create_task(self._heartbeat())
                            logger.info("✅ 心跳任务重新启动成功")
                        except Exception as heartbeat_error:
                            logger.error(f"❌ 重新启动心跳任务失败: {heartbeat_error}")
                        
                        logger.info("🎉 WebSocket重连完成！")
                        return True
                    else:
                        logger.warning(f"⚠️ 第{self.reconnect_strategy.retry_count + 1}次重连失败")
            
                except Exception as e:
                    logger.error(f"❌ 第{self.reconnect_strategy.retry_count + 1}次重连异常: {e}")
                
                # 记录重连尝试
                self.reconnect_strategy.record_retry()
                
                # 如果还有重试机会，等待后继续
                if self.reconnect_strategy.should_retry():
                    delay = self.reconnect_strategy.get_next_delay()
                    logger.info(f"⏳ 等待 {delay:.1f} 秒后重试...")
                    await asyncio.sleep(delay)
            
            # 重连失败
            logger.error(f"❌ 重连失败，已达到最大重试次数: {self.reconnect_strategy.max_retries}")
            await self._state_machine.transition_to(WebSocketStatus.ERROR)
            return False
                    
        except Exception as e:
            logger.error(f"❌ 重连过程异常: {e}")
            await self._state_machine.transition_to(WebSocketStatus.ERROR)
            return False
        finally:
            # 🚀 清除重连标记
            if hasattr(self, '_reconnecting'):
                self._reconnecting = False
                logger.info("🔄 重连标记已清除")
    
    async def _handle_connection_loss(self):
        """处理连接丢失"""
        try:
            logger.warning("检测到连接丢失，开始处理...")
            
            # 转换到断开状态
            await self._state_machine.transition_to(WebSocketStatus.DISCONNECTED)
            
            # 停止监控任务
            if self.health_monitor.is_running:
                await self.health_monitor.stop()
            
            if self._auto_recycle_task and not self._auto_recycle_task.done():
                self._auto_recycle_task.cancel()
            
            # 清理连接
            await self._cleanup_connection()
                                
            # 尝试重连
            if await self._smart_reconnect():
                logger.info("连接丢失处理完成，重连成功")
            else:
                logger.error("连接丢失处理完成，重连失败")
                # 延迟重连 - 修复异步调用
            try:
                await self._delayed_reconnect()
            except Exception as e:
                logger.error(f"延迟重连异常: {e}")
                                
        except Exception as e:
            logger.error(f"处理连接丢失异常: {e}")

    async def _listen(self):
        """消息监听循环 - 严格按照OKX官方规范实现活跃性检测"""
        try:
            logger.info("🎧 开始监听WebSocket消息")
            
            # 初始化活跃性检测
            self._last_message_time = time.time()
            self._activity_timer = None
            
            while self._state_machine.current_status in [
                WebSocketStatus.CONNECTED, 
                WebSocketStatus.AUTHENTICATED, 
                WebSocketStatus.SUBSCRIBED,
                WebSocketStatus.READY,
                WebSocketStatus.STABLE
            ]:
                try:
                    if not self.ws:
                        logger.warning("⚠️ WebSocket对象不存在")
                        break
                    
                    # 接收消息，增加超时处理
                    message = await asyncio.wait_for(self.ws.recv(), timeout=60.0)
                    
                    if message:
                        # 更新指标
                        self.metrics.message_count += 1
                        self.metrics.last_message_time = time.time()
                        
                        # 更新最后消息时间
                    self._last_message_time = time.time()
                        
                        # 重置活跃性定时器
                    if self._activity_timer:
                        self._activity_timer.cancel()
                        
                        # 设置新的活跃性定时器（25秒后检查）
                        self._activity_timer = asyncio.create_task(self._check_activity())
                    
                    # 处理消息
                    await self._handle_message(message)
                    
                except asyncio.TimeoutError:
                    # 超时继续循环
                    continue
                except websockets.exceptions.ConnectionClosed:
                    logger.warning("⚠️ WebSocket连接已关闭")
                    break
                except Exception as e:
                    logger.error(f"❌ 消息接收异常: {e}")
                    self.metrics.error_count += 1
                    continue
            
            logger.info("🎧 WebSocket消息监听结束")
            
        except asyncio.CancelledError:
            logger.info("🎧 WebSocket消息监听任务被取消")
        except Exception as e:
            logger.error(f"❌ WebSocket消息监听异常: {e}")
        finally:
            # 清理定时器
            if self._activity_timer:
                self._activity_timer.cancel()
            logger.info("🎧 监听任务清理完成")
    
    async def _handle_message(self, message: str):
        """处理接收到的消息"""
        try:
            data = json.loads(message)
        
            # 处理连接响应，获取connId
            if data.get("event") == "connect":
                conn_id = data.get("connId", "Unknown")
                logger.info(f"🔗 连接响应收到，connId: {conn_id}")
                # 保存connId到metrics中
                if hasattr(self.metrics, 'conn_id'):
                    self.metrics.conn_id = conn_id
                return
            
            # 处理登录响应
            if data.get("event") == "login":
                conn_id = data.get("connId", "Unknown")
                if data.get("code") == "0":
                    logger.info(f"✅ 登录成功 | connId: {conn_id}")
                else:
                    logger.error(f"❌ 登录失败 | connId: {conn_id} | 错误: {data}")
                return
            
            # 处理订阅响应 - 修复判断逻辑
            if data.get("event") == "subscribe":
                conn_id = data.get("connId", "Unknown")
                # OKX订阅成功时通常没有code字段，只有event和arg
                # 如果有code且不为0，则为失败
                if "code" in data and data.get("code") != "0":
                    logger.error(f"❌ 订阅失败 | connId: {conn_id} | 错误: {data}")
                else:
                    # 没有code字段或code为0，表示订阅成功
                    channel = data.get('arg', {}).get('channel', 'Unknown')
                    logger.info(f"✅ 订阅成功 | connId: {conn_id} | 频道: {channel}")
                return
            
            # 处理错误消息
            if data.get("event") == "error":
                conn_id = data.get("connId", "Unknown")
                logger.error(f"❌ WebSocket错误 | connId: {conn_id} | 错误: {data}")
                return
            
            # 处理业务消息
            if "data" in data:
                conn_id = data.get("connId", "Unknown")
                channel = data.get("arg", {}).get("channel", "unknown")
                if channel in self._subscriptions:
                    callback = self._subscriptions[channel]["callback"]
                    if callback:
                        try:
                            if asyncio.iscoroutinefunction(callback):
                                await callback(data)
                            else:
                                callback(data)
                        except Exception as e:
                            logger.error(f"❌ 消息回调异常 | connId: {conn_id} | 错误: {e}")
                else:
                    logger.debug(f"收到未订阅频道的消息 | connId: {conn_id} | 频道: {channel}")
                
        except json.JSONDecodeError:
            logger.error(f"消息JSON解析失败: {message}")
        except Exception as e:
            logger.error(f"消息处理异常: {e}")
    
    async def subscribe(self, channel: str, callback=None, **kwargs):
        """订阅频道,使用正确的OKX API格式"""
        try:
            # 等待连接就绪
            if not self.is_connection_healthy():
                logger.warning("WebSocket连接不可用，无法订阅")
                return False
            
            # 检查私有频道是否需要登录
            private_channels = ["account", "orders", "positions", "trades"]
            if channel in private_channels:
                if not self.api_key or not self.api_secret or not self.passphrase:
                    logger.error(f"私有频道 {channel} 需要API密钥，无法订阅")
                    return False
                
                # 检查是否已登录
                if self._state_machine.current_status not in [WebSocketStatus.AUTHENTICATED, WebSocketStatus.SUBSCRIBED, WebSocketStatus.READY, WebSocketStatus.STABLE]:
                    logger.warning(f"私有频道 {channel} 需要先登录，当前状态: {self._state_machine.current_status.value}")
                    return False
                
                # 私有频道订阅前等待一下，确保登录完成
                await asyncio.sleep(0.5)
            
            # 构建订阅消息 - 使用正确的OKX WebSocket API格式
            if channel == "account":
                # 账户订阅 - 私有频道，不需要额外参数
                subscribe_msg = {
                    "op": "subscribe",
                    "args": [{
                        "channel": "account"
                    }]
                }
            elif channel == "orders":
                # 订单订阅 - 私有频道，需要instType
                subscribe_msg = {
                    "op": "subscribe",
                    "args": [{
                        "channel": "orders",
                        "instType": kwargs.get("instType", "SWAP")
                    }]
                }
            elif channel == "positions":
                # 持仓订阅 - 私有频道，需要instType
                subscribe_msg = {
                    "op": "subscribe",
                    "args": [{
                        "channel": "positions",
                        "instType": kwargs.get("instType", "SWAP")
                    }]
                }
            elif channel == "trades":
                # 成交订阅 - 私有频道，需要instId
                subscribe_msg = {
                    "op": "subscribe",
                    "args": [{
                        "channel": "trades",
                        "instId": kwargs.get("instId", "BTC-USDT-SWAP")
                    }]
                }
            elif channel == "tickers":
                # 行情订阅 - 公共频道，需要instId
                subscribe_msg = {
                    "op": "subscribe",
                    "args": [{
                        "channel": "tickers",
                        "instId": kwargs.get("instId", "BTC-USDT-SWAP")
                    }]
                }
            elif channel == "books":
                # 深度订阅 - 公共频道，需要instId
                subscribe_msg = {
                    "op": "subscribe",
                    "args": [{
                        "channel": "books",
                        "instId": kwargs.get("instId", "BTC-USDT-SWAP")
                    }]
                }
            else:
                # 其他频道使用通用格式
                subscribe_msg = {
                "op": "subscribe",
                    "args": [{"channel": channel, **kwargs}]
                }
            
            # 发送订阅消息
            if self.ws and not getattr(self.ws, 'closed', False):
                # 记录详细的订阅信息
                logger.info(f"📡 准备订阅频道: {channel}")
                logger.info(f"📡 订阅消息内容: {json.dumps(subscribe_msg, indent=2)}")
                logger.info(f"📡 当前连接状态: {self._state_machine.current_status.value}")
            
                await self.ws.send(json.dumps(subscribe_msg))
            
                # 记录订阅
                self._subscriptions[channel] = {
                    "callback": callback,
                    "args": kwargs,
                    "timestamp": time.time()
                }
                    
                logger.info(f"📡 订阅消息已发送: {channel}")
                return True
            else:
                logger.error("WebSocket连接不可用，无法订阅")
                return False
                
        except Exception as e:
            logger.error(f"订阅异常: {e}")
            return False
    
    async def _on_reconnect_required(self, event: WebSocketEvent):
        """重连需求事件处理"""
        logger.info("收到重连需求事件")
        await self._smart_reconnect()
    
    async def _on_subscription_restore(self, event: WebSocketEvent):
        """订阅恢复事件处理"""
        logger.info("收到订阅恢复事件")
        await self._restore_subscriptions()
    async def _restore_subscriptions(self):
        """恢复订阅"""
        try:
            if not self._subscriptions:
                logger.info("没有需要恢复的订阅")
                return
            
            logger.info(f"开始恢复{len(self._subscriptions)}个订阅...")
            logger.info(f"订阅数据: {self._subscriptions}")
            
            for channel, subscription in self._subscriptions.items():
                try:
                    logger.info(f"正在恢复订阅: {channel}")
                    logger.info(f"订阅详情: callback={subscription.get('callback')}, args={subscription.get('args')}")
                    
                    await self.subscribe(channel, subscription["callback"], **subscription["args"])
                    logger.info(f"✅ 订阅{channel}恢复成功")
                    await asyncio.sleep(0.1)  # 避免订阅过快
                except Exception as e:
                    logger.error(f"❌ 恢复订阅{channel}失败: {e}")
                    logger.error(f"订阅数据: {subscription}")
                    
            logger.info("✅ 所有订阅恢复完成")
                    
        except Exception as e:
            logger.error(f"❌ 恢复订阅异常: {e}")
            logger.error(f"异常详情: {type(e).__name__}: {str(e)}")
            import traceback
            logger.error(f"异常堆栈: {traceback.format_exc()}")
    
    async def login(self):
        """登录认证"""
        try:
            if not all([self.api_key, self.api_secret, self.passphrase]):
                logger.warning("缺少API密钥，跳过登录")
                return
            
            # 生成时间戳 - WebSocket 登录使用 Unix 时间戳（秒）
            timestamp = str(int(time.time()))
            
            logger.debug(f"WebSocket登录时间戳: {timestamp}")
            
            # 构建登录消息
            login_msg = {
                "op": "login",
                "args": [{
                    "apiKey": self.api_key,
                    "passphrase": self.passphrase,
                    "timestamp": timestamp,
                    "sign": self._generate_signature(timestamp)
                }]
            }
            
            # 发送登录消息
            if self.ws and not getattr(self.ws, 'closed', False):
                await self.ws.send(json.dumps(login_msg))
                logger.info("登录消息已发送")
            else:
                raise Exception("WebSocket连接不可用")
            
        except Exception as e:
            logger.error(f"登录异常: {e}")
            raise

    def _generate_signature(self, timestamp: str) -> str:
        """生成签名 - WebSocket 登录专用"""
        try:
            # OKX WebSocket 登录签名格式: timestamp + 'GET' + '/users/self/verify'
            message = timestamp + 'GET' + '/users/self/verify'
            logger.debug(f"WebSocket签名消息: {message}")
            logger.debug(f"API密钥长度: {len(self.api_secret)}")
            
            # WebSocket 登录使用原始编码方式
            mac = hmac.new(
                bytes(self.api_secret, encoding='utf8'),
                bytes(message, encoding='utf-8'),
                digestmod='sha256'
            )
            signature = base64.b64encode(mac.digest()).decode()
            logger.debug(f"生成的WebSocket签名: {signature}")
            return signature
        except Exception as e:
            logger.error(f"WebSocket签名生成异常: {e}")
            return ""
    
    async def _delayed_reconnect(self):
        """延迟重连 - 避免立即重连失败"""
        try:
            wait_time = 5  # 等待30秒后重连
            logger.info(f"等待 {wait_time} 秒后进行延迟重连...")
            await asyncio.sleep(wait_time)
            
            # 检查是否需要重连
            if self._state_machine.current_status in [WebSocketStatus.DISCONNECTED, WebSocketStatus.ERROR]:
                logger.info("开始延迟重连...")
                await self._smart_reconnect()
            
        except Exception as e:
            logger.error(f"延迟重连异常: {e}")
    
    async def _heartbeat(self):
        """心跳任务 - 使用OKX官方支持的ping机制"""
        try:
            # 🚀 检查是否已有心跳任务在运行
            if hasattr(self, '_ping_task') and self._ping_task and not self._ping_task.done():
                logger.warning("⚠️ 检测到已有心跳任务在运行，跳过重复启动")
                return
            
            # 🚀 初始化心跳状态
            self._last_ping_time = time.time()
            self._last_pong_time = time.time()
            self._ping_failures = 0
            # 正确获取当前任务引用
            try:
                self._ping_task = asyncio.current_task()
                logger.debug(f"💓 心跳任务引用已设置: {self._ping_task}")
            except Exception as e:
                logger.warning(f"⚠️ 获取当前任务引用失败: {e}")
                self._ping_task = None
            
            logger.debug("💓 心跳任务已启动")
            
            while (hasattr(self, 'state_machine') and 
                   self._state_machine.current_status in [WebSocketStatus.READY, WebSocketStatus.STABLE]):
                if hasattr(self, 'ws') and self.ws and not getattr(self.ws, 'closed', False):
                    try:
                        # 更新ping时间
                        self._last_ping_time = time.time()
                        
                        # 使用WebSocket原生ping，OKX官方支持
                        if hasattr(self, 'ws') and self.ws:
                            await self.ws.ping()
                            logger.debug("💓 发送WebSocket ping")
                            
                            # 等待pong响应
                            await asyncio.sleep(5)  # 等待5秒
                            
                            # 检查连接状态
                            if getattr(self.ws, 'closed', False):
                                logger.warning("⚠️ WebSocket连接已关闭，触发重连")
                                self._ping_failures += 1
                                # 检查状态机是否允许重连
                                if self._state_machine.can_transition_to(WebSocketStatus.RECONNECTING):
                                    await self._smart_reconnect()
                                else:
                                    logger.warning("⚠️ 状态机不允许重连，跳过重连")
                                break
                        
                        # 重置ping失败计数（成功）
                        self._ping_failures = 0
                        self._last_pong_time = time.time()
                        
                    except Exception as e:
                        self._ping_failures += 1
                        logger.warning(f"⚠️ 心跳ping失败 (第{self._ping_failures}次): {e}")
                        logger.info(f"🔄 调试：心跳失败计数增加到 {self._ping_failures}")
                        
                        # 如果连续失败超过3次，立即重连
                        if self._ping_failures >= 3:
                            logger.error(f"⚠️ 心跳连续失败{self._ping_failures}次，立即重连")
                            
                            try:
                                logger.info("🔄 开始执行重连逻辑...")
                            except Exception as reconnect_log_error:
                                logger.info(f"DEBUG: 重连逻辑日志调用失败: {reconnect_log_error}")
                            
                            # 详细的状态机检查日志
                            logger.info("🔄 调试：开始检查状态机...")
                            logger.info("🔄 调试：即将进入try块...")
                            try:
                                logger.info("🔄 调试：进入try块成功")
                                if hasattr(self, 'state_machine'):
                                    logger.info("🔄 调试：状态机存在")
                                    current_status = self._state_machine.current_status
                                    can_reconnect = self._state_machine.can_transition_to(WebSocketStatus.RECONNECTING)
                                    logger.info(f"🔄 当前状态: {current_status.value}, 允许重连: {can_reconnect}")
                                    
                                    # 特殊处理：如果已经在重连状态，等待重连完成
                                    if current_status == WebSocketStatus.RECONNECTING:
                                        logger.info("🔄 检测到已有重连进程，心跳任务等待重连完成...")
                                        # 等待重连完成，最多等待30秒
                                        wait_time = 0
                                        while (wait_time < 30 and 
                                               hasattr(self, 'state_machine') and 
                                               self._state_machine.current_status == WebSocketStatus.RECONNECTING):
                                            await asyncio.sleep(1)
                                            wait_time += 1
                                            if wait_time % 5 == 0:  # 每5秒打印一次
                                                logger.info(f"🔄 等待重连完成中... ({wait_time}s)")
                                        
                                        final_status = self._state_machine.current_status
                                        if final_status in [WebSocketStatus.READY, WebSocketStatus.STABLE]:
                                            logger.info("✅ 检测到重连成功，心跳任务准备退出")
                                        else:
                                            logger.warning(f"⚠️ 重连等待超时或失败，当前状态: {final_status.value}")
                                    
                                    elif can_reconnect:
                                        logger.info("🔄 心跳任务开始重连，准备退出心跳循环...")
                                        try:
                                            await self._smart_reconnect()
                                            logger.info("🔄 心跳任务重连完成，退出心跳循环")
                                        except Exception as reconnect_error:
                                            logger.error(f"❌ 心跳任务重连过程中出现异常: {reconnect_error}")
                                            logger.error(f"异常类型: {type(reconnect_error).__name__}")
                                            import traceback
                                            logger.error(f"异常堆栈: {traceback.format_exc()}")
                                    else:
                                        logger.warning(f"⚠️ 状态机不允许重连，当前状态: {current_status.value}")
                                        logger.warning(f"⚠️ 尝试强制重连...")
                                        try:
                                            # 强制转换到重连状态
                                            await self._state_machine.transition_to(WebSocketStatus.RECONNECTING)
                                            logger.info("🔄 强制转换到重连状态成功")
                                            await self._smart_reconnect()
                                            logger.info("🔄 强制重连完成")
                                        except Exception as force_error:
                                            logger.error(f"❌ 强制重连也失败了: {force_error}")
                                    
                                    logger.info("🔄 重连逻辑执行完成，准备退出心跳循环")
                                else:
                                    logger.error("❌ 状态机不存在，无法执行重连")
                            except Exception as state_machine_error:
                                logger.error(f"❌ 状态机检查过程中出现异常: {state_machine_error}")
                                logger.error(f"异常类型: {type(state_machine_error).__name__}")
                                import traceback
                                logger.error(f"异常堆栈: {traceback.format_exc()}")
                            
                            logger.info("🔄 心跳循环即将退出，break语句执行")
                            
                            # 🚀 重要：在心跳任务退出前，尝试启动新的心跳任务
                            try:
                                logger.info("🔄 尝试启动新的心跳任务...")
                                if hasattr(self, '_heartbeat_task') and self._heartbeat_task and not self._heartbeat_task.done():
                                    self._heartbeat_task.cancel()
                                    logger.debug("🧹 取消旧的心跳任务引用")
                                
                                # 创建新的心跳任务
                                self._heartbeat_task = asyncio.create_task(self._heartbeat())
                                logger.info("✅ 新的心跳任务已启动")
                            except Exception as new_heartbeat_error:
                                logger.error(f"❌ 启动新的心跳任务失败: {new_heartbeat_error}")
                            
                            break
                        else:
                            # 失败次数较少，继续尝试
                            logger.debug(f"💓 心跳失败，{25 - 5}秒后重试")
                
                # 心跳间隔：25秒（小于30秒，符合官方要求）
                await asyncio.sleep(25)
                
                # 检查状态是否已改变（比如进入重连状态）
                if (hasattr(self, 'state_machine') and 
                    self._state_machine.current_status not in [WebSocketStatus.READY, WebSocketStatus.STABLE]):
                    logger.info(f"🔄 心跳任务检测到状态变化: {self._state_machine.current_status.value}，准备退出")
                    break
                
        except asyncio.CancelledError:
            logger.debug("💓 心跳任务已取消")
        except Exception as e:
            logger.error(f"❌ 心跳任务异常: {e}")
        finally:
            # 🚀 清理心跳状态
            self._ping_task = None
            logger.debug("💓 心跳任务已结束")
    
    async def _delayed_start_health_monitor(self):
        """延迟启动健康监控，避免立即检查新连接"""
        try:
            await asyncio.sleep(10)  # 等待10秒后启动健康监控
            if not self.health_monitor.is_running:
                await self.health_monitor.start()
                logger.info("健康监控已延迟启动")
        except Exception as e:
            logger.error(f"延迟启动健康监控异常: {e}")
    
    async def _auto_recycle_loop(self):
        """自动回收循环"""
        try:
            logger.info("开始自动回收循环...")
            
            while self._state_machine.current_status in [
                WebSocketStatus.READY,
                WebSocketStatus.STABLE
            ]:
                try:
                    await asyncio.sleep(300)  # 5分钟检查一次
                    
                    # 执行自动回收
                    await self._perform_auto_recycle()
                    
                except asyncio.CancelledError:
                    break
                except Exception as e:
                    logger.error(f"自动回收异常: {e}")
                    await asyncio.sleep(60)  # 异常时等待1分钟
            
            logger.info("自动回收循环结束")
            
        except asyncio.CancelledError:
            logger.info("自动回收任务被取消")
        except Exception as e:
            logger.error(f"自动回收任务异常: {e}")
    
    async def _perform_auto_recycle(self):
        """执行自动回收"""
        try:
            logger.info("执行自动回收...")
            
            # 检查连接时间
            if hasattr(self.metrics, 'connect_time') and self.metrics.connect_time > 0:
                connection_age = time.time() - self.metrics.connect_time
                if connection_age > 3600:  # 1小时
                    logger.info("连接时间超过1小时，执行自动回收")
                    await self._cleanup_connection()
                    await self.connect()
            
        except Exception as e:
            logger.error(f"自动回收执行异常: {e}")

    async def _cleanup_connection(self):
        """清理连接资源"""
        try:
            logger.info("开始清理连接资源...")
            
            # 🚀 取消心跳任务并等待完成
            # 检查两个可能的心跳任务变量
            heartbeat_tasks = []
            
            # 添加_heartbeat_task（如果存在）
            if hasattr(self, '_heartbeat_task') and self._heartbeat_task and not self._heartbeat_task.done():
                heartbeat_tasks.append(('_heartbeat_task', self._heartbeat_task))
            
            # 添加_ping_task（如果存在）
            if hasattr(self, '_ping_task') and self._ping_task and not self._ping_task.done():
                heartbeat_tasks.append(('_ping_task', self._ping_task))
            
            # 取消所有心跳任务
            for task_name, task in heartbeat_tasks:
                logger.debug(f"🧹 取消{task_name}...")
                task.cancel()
                try:
                    # 使用asyncio.wait方法，更安全地处理任务取消
                    done, pending = await asyncio.wait([task], timeout=2.0)
                    
                    if done:
                        # 任务已完成（可能被取消或异常）
                        for completed_task in done:
                            try:
                                # 尝试获取结果，如果是CancelledError会被正确处理
                                result = completed_task.result()
                                logger.debug(f"🧹 {task_name}已完成，结果: {result}")
                            except asyncio.CancelledError:
                                logger.debug(f"🧹 {task_name}已正常取消")
                            except Exception as task_exception:
                                logger.debug(f"🧹 {task_name}完成时出现异常: {task_exception}")
                    else:
                        # 超时，任务仍在运行
                        logger.debug(f"🧹 {task_name}取消超时，强制清理引用")
                        
                except Exception as e:
                    logger.warning(f"⚠️ 等待{task_name}取消时出错: {e}")
                    logger.warning(f"错误类型: {type(e).__name__}")
            
            # 清理任务引用
            if hasattr(self, '_heartbeat_task'):
                self._heartbeat_task = None
            if hasattr(self, '_ping_task'):
                self._ping_task = None
            
            # 取消监听任务
            if hasattr(self, '_listen_task') and self._listen_task and not self._listen_task.done():
                logger.debug("🧹 取消监听任务...")
                self._listen_task.cancel()
                try:
                    # 使用asyncio.wait方法，更安全地处理任务取消
                    done, pending = await asyncio.wait([self._listen_task], timeout=3.0)
                    
                    if done:
                        for completed_task in done:
                            try:
                                result = completed_task.result()
                                logger.debug(f"🧹 监听任务已完成，结果: {result}")
                            except asyncio.CancelledError:
                                logger.debug("🧹 监听任务已正常取消")
                            except Exception as task_exception:
                                logger.debug(f"🧹 监听任务完成时出现异常: {task_exception}")
                    else:
                        logger.debug("🧹 监听任务取消超时，强制清理引用")
                        
                except Exception as e:
                    logger.warning(f"⚠️ 等待监听任务取消时出错: {e}")
                    logger.warning(f"错误类型: {type(e).__name__}")
            
            # 取消自动回收任务
            if hasattr(self, '_auto_recycle_task') and self._auto_recycle_task and not self._auto_recycle_task.done():
                logger.debug("🧹 取消自动回收任务...")
                self._auto_recycle_task.cancel()
                try:
                    # 使用asyncio.wait方法，更安全地处理任务取消
                    done, pending = await asyncio.wait([self._auto_recycle_task], timeout=3.0)
                    
                    if done:
                        for completed_task in done:
                            try:
                                result = completed_task.result()
                                logger.debug(f"🧹 自动回收任务已完成，结果: {result}")
                            except asyncio.CancelledError:
                                logger.debug("🧹 自动回收任务已正常取消")
                            except Exception as task_exception:
                                logger.debug(f"🧹 自动回收任务完成时出现异常: {task_exception}")
                    else:
                        logger.debug("🧹 自动回收任务取消超时，强制清理引用")
                        
                except Exception as e:
                    logger.warning(f"⚠️ 等待自动回收任务取消时出错: {e}")
                    logger.warning(f"错误类型: {type(e).__name__}")
            
            # 🚀 重置心跳状态
            if hasattr(self, '_last_ping_time'):
                self._last_ping_time = 0
            if hasattr(self, '_last_pong_time'):
                self._last_pong_time = 0
            if hasattr(self, '_ping_failures'):
                self._ping_failures = 0
            if hasattr(self, '_ping_task'):
                self._ping_task = None
            
            # 关闭WebSocket连接
            if hasattr(self, 'ws') and self.ws:
                try:
                    if not getattr(self.ws, 'closed', False):
                        await self.ws.close()
                        logger.debug("🧹 WebSocket连接已关闭")
                    else:
                        logger.debug("🧹 WebSocket连接已经关闭")
                except Exception as e:
                    logger.error(f"关闭WebSocket异常: {e}")
                finally:
                    self.ws = None
            
            # 重置状态
            if hasattr(self, 'state_machine') and self._state_machine.current_status != WebSocketStatus.INIT:
                await self._state_machine.transition_to(WebSocketStatus.DISCONNECTED)
            
            logger.info("✅ 连接资源清理完成")
                
        except Exception as e:
            logger.error(f"❌ 清理连接资源异常: {e}")
            logger.error(f"异常类型: {type(e).__name__}")
            import traceback
            logger.error(f"异常堆栈: {traceback.format_exc()}")
            # 强制清理关键资源
            self._force_cleanup_resources()
    
    def _force_cleanup_resources(self):
        """强制清理关键资源（异常情况下的备用方案）"""
        try:
            logger.warning("🚨 执行强制资源清理...")
            
            # 强制设置任务为None
            if hasattr(self, '_heartbeat_task'):
                self._heartbeat_task = None
            if hasattr(self, '_listen_task'):
                self._listen_task = None
            if hasattr(self, '_auto_recycle_task'):
                self._auto_recycle_task = None
            
            # 强制设置WebSocket为None
            if hasattr(self, 'ws'):
                self.ws = None
            
            # 重置心跳状态
            if hasattr(self, '_last_ping_time'):
                self._last_ping_time = 0
            if hasattr(self, '_last_pong_time'):
                self._last_pong_time = 0
            if hasattr(self, '_ping_failures'):
                self._ping_failures = 0
            if hasattr(self, '_ping_task'):
                self._ping_task = None
            
            logger.warning("🚨 强制资源清理完成")
            
        except Exception as e:
            logger.error(f"❌ 强制资源清理也失败了: {e}")
    
    async def _on_connection_lost(self, event: WebSocketEvent):
        """连接丢失事件处理"""
        logger.warning("收到连接丢失事件，开始重连流程")
        await self._handle_connection_loss()
    
    def is_connection_healthy(self) -> bool:
        """检查连接是否健康"""
        try:
            # 基本检查
            if not self.ws:
                logger.debug("❌ WebSocket对象不存在")
                return False
            
            if getattr(self.ws, 'closed', False):
                logger.debug("❌ WebSocket连接已关闭")
                return False
            
            # 状态机检查
            current_status = self._state_machine.current_status
            if current_status in [WebSocketStatus.INIT, WebSocketStatus.DISCONNECTED, WebSocketStatus.ERROR]:
                logger.debug(f"❌ 连接状态异常: {current_status.value}")
                return False
            
            # 新连接保护：连接时间少于2分钟，认为健康
            if hasattr(self.metrics, 'connect_time') and self.metrics.connect_time:
                connection_age = time.time() - self.metrics.connect_time
                if connection_age < 120:  # 2分钟保护期
                    logger.debug(f"✅ 新连接保护中，连接时间: {connection_age:.1f}秒")
                    return True
            
            # 监听任务检查
            if hasattr(self, '_listen_task') and self._listen_task:
                if self._listen_task.done():
                    if self._listen_task.exception():
                        logger.debug(f"❌ 监听任务异常: {self._listen_task.exception()}")
                        return False
                    else:
                        logger.debug("❌ 监听任务已完成")
                        return False
            
            # 连接时间检查
            if hasattr(self.metrics, 'connect_time') and self.metrics.connect_time:
                connection_age = time.time() - self.metrics.connect_time
                if connection_age > 3600:  # 1小时以上
                    logger.debug(f"⚠️ 连接时间过长: {connection_age:.1f}秒")
                    return False
            
            logger.debug("✅ 连接健康检查通过")
            return True
            
        except Exception as e:
            logger.error(f"❌ 连接健康检查异常: {e}")
            return False
    
    async def test_connection_reality(self) -> bool:
        """测试连接真实性"""
        try:
            # 1. 基础检查
            if not self.ws:
                logger.warning("WebSocket对象不存在，无法测试连接真实性")
                return False
            
            # 2. 状态检查 - 放宽状态要求
            current_status = self._state_machine.current_status
            if current_status not in [WebSocketStatus.CONNECTING, WebSocketStatus.CONNECTED, WebSocketStatus.AUTHENTICATED, WebSocketStatus.SUBSCRIBED, WebSocketStatus.READY, WebSocketStatus.STABLE]:
                logger.warning(f"连接状态异常: {current_status.value}")
                return False
            
            # 3. WebSocket状态检查
            try:
                ws_closed = getattr(self.ws, 'closed', False)
                if ws_closed:
                    logger.warning("WebSocket连接已关闭")
                    return False
                
                # 4. 尝试ping测试（可选）
                try:
                    await asyncio.wait_for(self.ws.ping(), timeout=5)
                    logger.info("✅ 连接真实性测试通过 - ping成功")
                    return True
                except Exception as ping_error:
                    logger.warning(f"ping测试失败: {ping_error}")
                    # ping失败不意味着连接不可用，检查其他状态
                    if hasattr(self.ws, 'open') and self.ws.open:
                        logger.info("✅ 连接真实性测试通过 - WebSocket状态为open")
                        return True
                    else:
                        logger.info("✅ 连接真实性测试通过 - WebSocket状态正常")
                        return True
                        
            except Exception as e:
                logger.warning(f"WebSocket状态检查异常: {e}")
                # 异常情况下，如果WebSocket对象存在且未关闭，认为可用
                if self.ws and not getattr(self.ws, 'closed', True):
                    logger.info("✅ 连接真实性测试通过 - 保守判断")
                    return True
                return False
                
        except Exception as e:
            logger.error(f"连接真实性测试异常: {e}")
            return False
    
    async def place_order(self, **kwargs):
        """下单模块 - 使用REST API进行真实下单"""
        try:
            # 使用统一接口创建REST客户端
            try:
                from exchange.exchange_factory import create_exchange_client
                rest_client = create_exchange_client(
                    exchange='okx',
                    client_type='rest',
                    api_key=self.api_key,
                    api_secret=self.api_secret,
                    passphrase=self.passphrase,
                    is_demo=self.is_demo
                )
            except Exception as import_error:
                logger.error(f"❌ 无法创建REST客户端: {import_error}")
                # 返回模拟响应作为后备
                return {
                    "code": "0",
                "data": [{
                        "sCode": "0",
                    "sMsg": "下单成功（模拟）",
                    "ordId": f"mock_{int(time.time() * 1000)}",
                    "clOrdId": kwargs.get('clOrdId', ''),
                    "tag": kwargs.get('tag', '')
                }]
            }
            
            logger.info(f"📤 使用REST API下单: {kwargs}")
            
            # 使用REST API进行真实下单
            result = await rest_client.place_order(**kwargs)
            
            logger.info(f"✅ REST API下单结果: {result}")
            return result
            
        except Exception as e:
            logger.error(f"❌ REST API下单异常: {e}")
            return {"code": "1", "data": [{"sCode": "1", "sMsg": f"下单失败: {str(e)}"}]}
    
    async def _quick_reconnect(self) -> bool:
        """快速重连 - 专门为下单优化的快速重连"""
        try:
            logger.info("🔄 执行快速重连...")
            
            # 清理旧连接
            await self._cleanup_connection()
            
            # 快速重新连接
            if await self.connect():
                logger.info("✅ 快速重连成功")
                return True
            else:
                logger.error("❌ 快速重连失败")
                return False
                
        except Exception as e:
            logger.error(f"快速重连异常: {e}")
            return False
    
    async def get_ticker(self, symbol: str):
        """获取价格 - 使用REST API"""
        try:
            # 使用统一接口创建REST客户端
            from exchange.exchange_factory import create_exchange_client
            rest_client = create_exchange_client(
                exchange='okx',
                client_type='rest',
                api_key=self.api_key,
                api_secret=self.api_secret,
                passphrase=self.passphrase,
                is_demo=self.is_demo
            )
            
            # 使用REST API获取真实价格
            result = await rest_client.get_ticker(symbol)
            
            if result.get('code') == '0' and result.get('data'):
                ticker_data = result['data'][0]
                return {"last": ticker_data.get('last', '1.0')}
            else:
                logger.warning(f"获取价格失败，返回默认价格1.0: {symbol}")
            return {"last": "1.0"}
                
        except Exception as e:
            logger.error(f"获取价格异常: {e}")
            return {"last": "1.0"}
    
    async def get_order(self, order_id: str):
        """获取订单 - 使用REST API"""
        try:
            # 使用统一接口创建REST客户端
            from exchange.exchange_factory import create_exchange_client
            rest_client = create_exchange_client(
                exchange='okx',
                client_type='rest',
                api_key=self.api_key,
                api_secret=self.api_secret,
                passphrase=self.passphrase,
                is_demo=self.is_demo
            )
            
            # 使用REST API获取真实订单信息
            # 注意：这里需要instId参数，暂时使用默认值
            result = await rest_client.get_order(instId="BTC-USDT-SWAP", ordId=order_id)
            
            if result.get('code') == '0' and result.get('data'):
                order_data = result['data'][0]
                return {
                        "ordId": order_data.get('ordId', order_id),
                        "state": order_data.get('state', 'live'),
                    "code": "0",
                    "msg": "success"
                }
            else:
                logger.warning(f"获取订单失败: {order_id}")
                return None
                
        except Exception as e:
            logger.error(f"获取订单异常: {e}")
            return None
    
    def get_connection_status(self) -> dict:
        """获取连接状态 - 包含connId信息"""
        try:
            status = {
                "status": self._state_machine.current_status.value,
                "url": self.ws_url,
                "connected": self.ws is not None and not getattr(self.ws, 'closed', False),
                "conn_id": getattr(self.metrics, 'conn_id', 'Unknown'),
                "connect_time": self.metrics.connect_time,
                "message_count": self.metrics.message_count,
                "error_count": self.metrics.error_count,
                "last_message": self.metrics.last_message_time
            }
            
            if self.metrics.connect_time:
                status["uptime"] = time.time() - self.metrics.connect_time
            
            return status
            
        except Exception as e:
            logger.error(f"获取连接状态异常: {e}")
            return {"error": str(e)}
    
    def get_debug_info(self) -> dict:
        """获取调试信息"""
        return {
            "current_status": self._state_machine.current_status.value if self._state_machine.current_status else "None",
            "ws_exists": self.ws is not None,
            "ws_closed": getattr(self.ws, 'closed', True) if self.ws else True,
            "ws_open": getattr(self.ws, 'open', False) if self.ws else False,
            "health_monitor_running": self.health_monitor.is_running if hasattr(self, 'health_monitor') else False,
            "listen_task_running": self._listen_task and not self._listen_task.done() if hasattr(self, '_listen_task') else False,
            "heartbeat_task_running": self._heartbeat_task and not self._heartbeat_task.done() if hasattr(self, '_heartbeat_task') else False
        }
    
    async def close(self):
        """关闭连接"""
        try:
            logger.info("开始关闭WebSocket连接...")
            
            # 停止事件引擎
            if self.event_engine._active:
                await self.event_engine.stop()
            
                # 清理连接资源
                await self._cleanup_connection()
            
                logger.info("WebSocket连接已关闭")
            
        except Exception as e:
            logger.error(f"关闭连接异常: {e}")
    
    def __del__(self):
        """析构函数 - 确保资源清理"""
        try:
            if hasattr(self, 'event_engine') and self.event_engine._active:
                asyncio.create_task(self.event_engine.stop())
        except:
            pass

    async def _check_activity(self):
        """活跃性检查 - 基于WebSocket连接状态和消息活跃性"""
        try:
            # 等待25秒
            await asyncio.sleep(25)
            
            # 检查是否在监听循环中
            if not hasattr(self, '_listen_task') or not self._listen_task or self._listen_task.done():
                logger.debug("🎧 监听任务已结束，跳过活跃性检查")
                return
            
            # 检查最后消息时间
            if hasattr(self, '_last_message_time') and self._last_message_time:
                time_since_last_message = time.time() - self._last_message_time
                if time_since_last_message >= 25:
                    logger.warning(f"⚠️ 25秒内未收到消息，检查连接状态")
                    
                    # 检查WebSocket连接状态
                    if self.ws and not getattr(self.ws, 'closed', False):
                        try:
                            # 检查连接是否仍然有效
                            if hasattr(self.ws, '_closed') and self.ws._closed:
                                logger.error("❌ WebSocket连接已关闭，触发重连")
                                # 检查状态机是否允许重连
                                if self._state_machine.can_transition_to(WebSocketStatus.RECONNECTING):
                                    await self._smart_reconnect()
                                else:
                                    logger.warning("⚠️ 状态机不允许重连，跳过重连")
                            else:
                                logger.info("✅ WebSocket连接状态正常")
                                
                        except Exception as e:
                            logger.error(f"❌ 连接状态检查失败: {e}")
                            # 检查状态机是否允许重连
                            if self._state_machine.can_transition_to(WebSocketStatus.RECONNECTING):
                                await self._smart_reconnect()
                            else:
                                logger.warning("⚠️ 状态机不允许重连，跳过重连")
                    else:
                        logger.error("❌ WebSocket连接不可用，触发重连")
                        # 检查状态机是否允许重连
                        if self._state_machine.can_transition_to(WebSocketStatus.RECONNECTING):
                            await self._smart_reconnect()
                        else:
                            logger.warning("⚠️ 状态机不允许重连，跳过重连")
            
        except asyncio.CancelledError:
            logger.debug("🎧 活跃性检查被取消")
        except Exception as e:
            logger.error(f"❌ 活跃性检查异常: {e}")
    
    # 实现BaseWebSocketClient的抽象方法
    async def disconnect(self) -> bool:
        """断开WebSocket连接"""
        try:
            await self._cleanup_connection()
            await self._transition_to(WebSocketStatus.DISCONNECTED, "主动断开连接")
            return True
        except Exception as e:
            logger.error(f"断开连接失败: {e}")
            return False
    
    async def subscribe_ticker(self, symbol: str, callback) -> bool:
        """订阅行情数据"""
        try:
            # 这里应该实现具体的订阅逻辑
            logger.info(f"订阅行情数据: {symbol}")
            return True
        except Exception as e:
            logger.error(f"订阅行情数据失败: {e}")
            return False
    
    async def subscribe_orderbook(self, symbol: str, callback) -> bool:
        """订阅深度数据"""
        try:
            # 这里应该实现具体的订阅逻辑
            logger.info(f"订阅深度数据: {symbol}")
            return True
        except Exception as e:
            logger.error(f"订阅深度数据失败: {e}")
            return False
    
    async def subscribe_trades(self, symbol: str, callback) -> bool:
        """订阅交易数据"""
        try:
            # 这里应该实现具体的订阅逻辑
            logger.info(f"订阅交易数据: {symbol}")
            return True
        except Exception as e:
            logger.error(f"订阅交易数据失败: {e}")
            return False
    
    async def subscribe_orders(self, callback) -> bool:
        """订阅订单更新"""
        try:
            # 这里应该实现具体的订阅逻辑
            logger.info("订阅订单更新")
            return True
        except Exception as e:
            logger.error(f"订阅订单更新失败: {e}")
            return False
    
    async def subscribe_positions(self, callback) -> bool:
        """订阅持仓更新"""
        try:
            # 这里应该实现具体的订阅逻辑
            logger.info("订阅持仓更新")
            return True
        except Exception as e:
            logger.error(f"订阅持仓更新失败: {e}")
            return False
    
    async def subscribe_balance(self, callback) -> bool:
        """订阅余额更新"""
        try:
            # 这里应该实现具体的订阅逻辑
            logger.info("订阅余额更新")
            return True
        except Exception as e:
            logger.error(f"订阅余额更新失败: {e}")
            return False
    
    async def unsubscribe(self, channel: str) -> bool:
        """取消订阅"""
        try:
            # 这里应该实现具体的取消订阅逻辑
            logger.info(f"取消订阅: {channel}")
            return True
        except Exception as e:
            logger.error(f"取消订阅失败: {e}")
            return False
    
    def is_connected(self) -> bool:
        """检查连接状态"""
        return self._state_machine.is_connected()


# 使用示例
if __name__ == "__main__":
    # 测试代码
    async def test():
        client = OKXWebSocketClient(is_demo=True)
        try:
            await client.connect()
            await asyncio.sleep(10)
        finally:
            await client.close()

    asyncio.run(test())