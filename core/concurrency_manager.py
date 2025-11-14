#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
并发管理器
提供请求限流、资源管理、并发控制等功能，确保高并发下的稳定性
"""

import time
import threading
from collections import defaultdict, deque
from typing import Dict, Optional, Callable
from functools import wraps
from utils.logger import logger
from datetime import datetime, timedelta


class RateLimiter:
    """请求限流器"""
    
    def __init__(self, max_requests: int = 100, time_window: int = 60):
        """
        初始化限流器
        
        Args:
            max_requests: 时间窗口内最大请求数
            time_window: 时间窗口（秒）
        """
        self.max_requests = max_requests
        self.time_window = time_window
        self.requests: Dict[str, deque] = defaultdict(lambda: deque())
        self._lock = threading.Lock()
    
    def is_allowed(self, key: str = 'default') -> bool:
        """
        检查是否允许请求
        
        Args:
            key: 限流键（可以按用户ID、IP等区分）
            
        Returns:
            True 表示允许，False 表示限流
        """
        now = time.time()
        
        with self._lock:
            # 清理过期请求
            request_times = self.requests[key]
            while request_times and now - request_times[0] > self.time_window:
                request_times.popleft()
            
            # 检查是否超过限制
            if len(request_times) >= self.max_requests:
                return False
            
            # 记录本次请求
            request_times.append(now)
            return True
    
    def get_remaining(self, key: str = 'default') -> int:
        """获取剩余请求次数"""
        now = time.time()
        
        with self._lock:
            request_times = self.requests[key]
            while request_times and now - request_times[0] > self.time_window:
                request_times.popleft()
            
            return max(0, self.max_requests - len(request_times))


class ConcurrencyLimiter:
    """并发限制器"""
    
    def __init__(self, max_concurrent: int = 50):
        """
        初始化并发限制器
        
        Args:
            max_concurrent: 最大并发数
        """
        self.max_concurrent = max_concurrent
        self.current_count = 0
        self._lock = threading.Lock()
        self._condition = threading.Condition(self._lock)
    
    def acquire(self, timeout: Optional[float] = None) -> bool:
        """
        获取并发许可
        
        Args:
            timeout: 超时时间（秒），None 表示无限等待
            
        Returns:
            True 表示获取成功，False 表示超时
        """
        with self._condition:
            end_time = time.time() + timeout if timeout else None
            
            while self.current_count >= self.max_concurrent:
                if timeout is None:
                    self._condition.wait()
                else:
                    remaining = end_time - time.time()
                    if remaining <= 0:
                        return False
                    self._condition.wait(remaining)
            
            self.current_count += 1
            return True
    
    def release(self):
        """释放并发许可"""
        with self._condition:
            self.current_count -= 1
            self._condition.notify()
    
    def __enter__(self):
        """上下文管理器入口"""
        self.acquire()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """上下文管理器出口"""
        self.release()


class ConcurrencyManager:
    """并发管理器"""
    
    def __init__(self):
        """初始化并发管理器"""
        # 全局限流器
        self.global_rate_limiter = RateLimiter(max_requests=1000, time_window=60)
        
        # 按用户限流（每个用户每分钟最多100个请求）
        self.user_rate_limiter = RateLimiter(max_requests=100, time_window=60)
        
        # 并发限制器
        self.concurrency_limiter = ConcurrencyLimiter(max_concurrent=100)
        
        # 统计信息
        self.stats = {
            'total_requests': 0,
            'rate_limited_requests': 0,
            'concurrency_limited_requests': 0,
            'active_requests': 0
        }
        self._stats_lock = threading.Lock()
    
    def rate_limit(self, key: Optional[str] = None):
        """
        请求限流装饰器
        
        Args:
            key: 限流键，如果为 None 则使用全局限流
        """
        def decorator(func):
            @wraps(func)
            def wrapper(*args, **kwargs):
                # 尝试从请求中获取用户ID
                user_id = None
                if hasattr(kwargs, 'get') or 'user_id' in kwargs:
                    user_id = kwargs.get('user_id')
                
                # 选择限流键
                rate_key = f"user_{user_id}" if user_id else (key or 'global')
                
                # 检查限流
                if not self.user_rate_limiter.is_allowed(rate_key):
                    with self._stats_lock:
                        self.stats['rate_limited_requests'] += 1
                    logger.warning(f"[并发管理] 请求被限流: {rate_key}")
                    from flask import jsonify
                    return jsonify({
                        'success': False,
                        'message': '请求过于频繁，请稍后再试',
                        'retry_after': 60
                    }), 429
                
                with self._stats_lock:
                    self.stats['total_requests'] += 1
                
                return func(*args, **kwargs)
            return wrapper
        return decorator
    
    def concurrency_limit(self, max_concurrent: Optional[int] = None):
        """
        并发限制装饰器
        
        Args:
            max_concurrent: 最大并发数，None 使用默认值
        """
        def decorator(func):
            @wraps(func)
            def wrapper(*args, **kwargs):
                limiter = self.concurrency_limiter
                if max_concurrent:
                    limiter = ConcurrencyLimiter(max_concurrent)
                
                if not limiter.acquire(timeout=5):
                    with self._stats_lock:
                        self.stats['concurrency_limited_requests'] += 1
                    logger.warning("[并发管理] 请求因并发限制被拒绝")
                    from flask import jsonify
                    return jsonify({
                        'success': False,
                        'message': '服务器繁忙，请稍后再试'
                    }), 503
                
                try:
                    with self._stats_lock:
                        self.stats['active_requests'] += 1
                    return func(*args, **kwargs)
                finally:
                    limiter.release()
                    with self._stats_lock:
                        self.stats['active_requests'] -= 1
            return wrapper
        return decorator
    
    def get_stats(self) -> Dict:
        """获取统计信息"""
        with self._stats_lock:
            return self.stats.copy()


# 全局并发管理器实例
_global_concurrency_manager: Optional[ConcurrencyManager] = None


def get_concurrency_manager() -> ConcurrencyManager:
    """获取全局并发管理器（单例）"""
    global _global_concurrency_manager
    if _global_concurrency_manager is None:
        _global_concurrency_manager = ConcurrencyManager()
    return _global_concurrency_manager

