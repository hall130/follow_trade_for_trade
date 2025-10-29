#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
WebSocket状态机模块
提供统一的WebSocket连接状态管理
"""

import asyncio
import time
from enum import Enum
from typing import Dict, List, Callable, Optional, Any
from dataclasses import dataclass, field
from utils.logger import logger


class WebSocketStatus(Enum):
    """WebSocket连接状态枚举"""
    INIT = "初始化"
    CONNECTING = "连接中"
    CONNECTED = "已连接"
    AUTHENTICATED = "已认证"
    SUBSCRIBED = "已订阅"
    READY = "就绪"
    STABLE = "稳定"
    RECONNECTING = "重连中"
    DISCONNECTED = "已断开"
    ERROR = "错误"


@dataclass
class ConnectionMetrics:
    """连接指标数据类"""
    # 连接信息
    connect_time: Optional[float] = None
    conn_id: Optional[str] = None
    
    # 消息统计
    message_count: int = 0
    last_message_time: Optional[float] = None
    
    # 错误统计
    error_count: int = 0
    last_error_time: Optional[float] = None
    last_error_message: Optional[str] = None
    
    # 重连统计
    reconnect_count: int = 0
    last_reconnect_time: Optional[float] = None
    
    # 性能指标
    avg_message_interval: float = 0.0
    max_message_interval: float = 0.0
    
    def update_message(self):
        """更新消息统计"""
        current_time = time.time()
        if self.last_message_time:
            interval = current_time - self.last_message_time
            self.avg_message_interval = (self.avg_message_interval + interval) / 2
            self.max_message_interval = max(self.max_message_interval, interval)
        
        self.message_count += 1
        self.last_message_time = current_time
    
    def update_error(self, error_message: str):
        """更新错误统计"""
        self.error_count += 1
        self.last_error_time = time.time()
        self.last_error_message = error_message
    
    def update_reconnect(self):
        """更新重连统计"""
        self.reconnect_count += 1
        self.last_reconnect_time = time.time()


class WebSocketStateMachine:
    """WebSocket状态机"""
    
    def __init__(self, exchange_name: str = "Unknown"):
        self.exchange_name = exchange_name
        self._current_status = WebSocketStatus.INIT
        self._transitions = self._define_transitions()
        self._lock = asyncio.Lock()
        self._status_change_callbacks: List[Callable] = []
        self._metrics = ConnectionMetrics()
        self._status_history: List[tuple] = []  # (timestamp, status, reason)
    
    def _define_transitions(self) -> Dict[WebSocketStatus, List[WebSocketStatus]]:
        """定义状态转换规则"""
        return {
            WebSocketStatus.INIT: [
                WebSocketStatus.CONNECTING, 
                WebSocketStatus.DISCONNECTED, 
                WebSocketStatus.ERROR
            ],
            WebSocketStatus.CONNECTING: [
                WebSocketStatus.CONNECTED, 
                WebSocketStatus.DISCONNECTED, 
                WebSocketStatus.ERROR,
                WebSocketStatus.AUTHENTICATED
            ],
            WebSocketStatus.CONNECTED: [
                WebSocketStatus.AUTHENTICATED, 
                WebSocketStatus.DISCONNECTED, 
                WebSocketStatus.ERROR,
                WebSocketStatus.SUBSCRIBED,
                WebSocketStatus.READY,
                WebSocketStatus.STABLE
            ],
            WebSocketStatus.AUTHENTICATED: [
                WebSocketStatus.SUBSCRIBED, 
                WebSocketStatus.READY, 
                WebSocketStatus.STABLE,
                WebSocketStatus.DISCONNECTED, 
                WebSocketStatus.ERROR,
                WebSocketStatus.CONNECTING
            ],
            WebSocketStatus.SUBSCRIBED: [
                WebSocketStatus.READY, 
                WebSocketStatus.STABLE,
                WebSocketStatus.DISCONNECTED, 
                WebSocketStatus.ERROR,
                WebSocketStatus.CONNECTING
            ],
            WebSocketStatus.READY: [
                WebSocketStatus.STABLE,
                WebSocketStatus.DISCONNECTED, 
                WebSocketStatus.ERROR,
                WebSocketStatus.CONNECTING,
                WebSocketStatus.AUTHENTICATED,
                WebSocketStatus.SUBSCRIBED
            ],
            WebSocketStatus.STABLE: [
                WebSocketStatus.READY,
                WebSocketStatus.DISCONNECTED, 
                WebSocketStatus.ERROR,
                WebSocketStatus.CONNECTING,
                WebSocketStatus.AUTHENTICATED,
                WebSocketStatus.SUBSCRIBED,
                WebSocketStatus.RECONNECTING
            ],
            WebSocketStatus.RECONNECTING: [
                WebSocketStatus.CONNECTING,
                WebSocketStatus.CONNECTED,
                WebSocketStatus.DISCONNECTED, 
                WebSocketStatus.ERROR
            ],
            WebSocketStatus.DISCONNECTED: [
                WebSocketStatus.CONNECTING,
                WebSocketStatus.CONNECTED,
                WebSocketStatus.INIT,
                WebSocketStatus.ERROR
            ],
            WebSocketStatus.ERROR: [
                WebSocketStatus.CONNECTING,
                WebSocketStatus.CONNECTED,
                WebSocketStatus.DISCONNECTED,
                WebSocketStatus.INIT
            ]
        }
    
    @property
    def current_status(self) -> WebSocketStatus:
        """当前状态"""
        return self._current_status
    
    @property
    def metrics(self) -> ConnectionMetrics:
        """连接指标"""
        return self._metrics
    
    def can_transition_to(self, target_status: WebSocketStatus) -> bool:
        """检查是否可以转换到目标状态"""
        return target_status in self._transitions.get(self._current_status, [])
    
    async def transition_to(self, target_status: WebSocketStatus, reason: str = "") -> bool:
        """转换到目标状态 - 异步方法，线程安全"""
        async with self._lock:
            if self.can_transition_to(target_status):
                old_status = self._current_status
                self._current_status = target_status
                
                # 记录状态历史
                self._status_history.append((time.time(), target_status, reason))
                
                # 更新指标
                self._update_metrics_for_transition(old_status, target_status)
                
                # 触发回调
                await self._trigger_status_change_callbacks(old_status, target_status, reason)
                
                logger.info(f"[{self.exchange_name}] 状态转换: {old_status.value} -> {target_status.value} ({reason})")
                return True
            else:
                logger.warning(f"[{self.exchange_name}] 无效的状态转换: {self._current_status.value} -> {target_status.value}")
                return False
    
    def _update_metrics_for_transition(self, old_status: WebSocketStatus, new_status: WebSocketStatus):
        """根据状态转换更新指标"""
        if new_status == WebSocketStatus.CONNECTED:
            self._metrics.connect_time = time.time()
        elif new_status == WebSocketStatus.RECONNECTING:
            self._metrics.update_reconnect()
        elif new_status == WebSocketStatus.ERROR:
            self._metrics.update_error(f"状态转换到错误: {old_status.value} -> {new_status.value}")
    
    async def _trigger_status_change_callbacks(self, old_status: WebSocketStatus, 
                                             new_status: WebSocketStatus, reason: str):
        """触发状态变化回调"""
        for callback in self._status_change_callbacks:
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(old_status, new_status, reason)
                else:
                    callback(old_status, new_status, reason)
            except Exception as e:
                logger.error(f"[{self.exchange_name}] 状态变化回调执行失败: {e}")
    
    def add_status_change_callback(self, callback: Callable):
        """添加状态变化回调"""
        self._status_change_callbacks.append(callback)
    
    def remove_status_change_callback(self, callback: Callable):
        """移除状态变化回调"""
        if callback in self._status_change_callbacks:
            self._status_change_callbacks.remove(callback)
    
    def get_status_history(self, limit: int = 10) -> List[tuple]:
        """获取状态历史"""
        return self._status_history[-limit:] if limit > 0 else self._status_history
    
    def is_connected(self) -> bool:
        """检查是否已连接"""
        return self._current_status in [
            WebSocketStatus.CONNECTED, 
            WebSocketStatus.AUTHENTICATED, 
            WebSocketStatus.SUBSCRIBED, 
            WebSocketStatus.READY, 
            WebSocketStatus.STABLE
        ]
    
    def is_ready(self) -> bool:
        """检查是否就绪"""
        return self._current_status in [
            WebSocketStatus.READY, 
            WebSocketStatus.STABLE
        ]
    
    def is_stable(self) -> bool:
        """检查是否稳定"""
        return self._current_status == WebSocketStatus.STABLE
    
    def can_reconnect(self) -> bool:
        """检查是否可以重连"""
        return self._current_status in [
            WebSocketStatus.DISCONNECTED, 
            WebSocketStatus.ERROR
        ]
    
    def get_status_info(self) -> Dict[str, Any]:
        """获取状态信息"""
        return {
            "exchange": self.exchange_name,
            "current_status": self._current_status.value,
            "is_connected": self.is_connected(),
            "is_ready": self.is_ready(),
            "is_stable": self.is_stable(),
            "can_reconnect": self.can_reconnect(),
            "metrics": {
                "message_count": self._metrics.message_count,
                "error_count": self._metrics.error_count,
                "reconnect_count": self._metrics.reconnect_count,
                "avg_message_interval": self._metrics.avg_message_interval,
                "max_message_interval": self._metrics.max_message_interval
            },
            "status_history": self.get_status_history(5)
        }
