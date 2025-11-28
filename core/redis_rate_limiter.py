#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
基于 Redis 的分布式限流器
支持多进程/多服务器环境下的统一限流
如果 Redis 不可用，自动降级到内存模式
"""

import time
from typing import Optional, Tuple, Callable
from functools import wraps
from flask import request, jsonify
from utils.logger import logger

try:
    from core.redis_manager import get_redis_manager
    REDIS_MANAGER_AVAILABLE = True
except ImportError:
    REDIS_MANAGER_AVAILABLE = False
    logger.warning("Redis 管理器不可用，将使用内存限流")


class RedisRateLimiter:
    """基于 Redis 的分布式限流器"""
    
    def __init__(self, max_requests: int = 100, time_window: int = 60):
        """
        初始化限流器
        
        Args:
            max_requests: 时间窗口内最大请求数
            time_window: 时间窗口（秒）
        """
        self.max_requests = max_requests
        self.time_window = time_window
        self.redis_manager = None
        
        if REDIS_MANAGER_AVAILABLE:
            try:
                self.redis_manager = get_redis_manager()
            except:
                pass
    
    def is_allowed(self, key: str = 'default') -> Tuple[bool, int]:
        """
        检查是否允许请求
        
        Args:
            key: 限流键(可以按用户ID、IP等区分)
            
        Returns:
            (是否允许, 剩余请求次数)
        """
        rate_key = f"rate_limit:{key}"
        count_key = f"{rate_key}:count"
        window_key = f"{rate_key}:window"
        
        now = int(time.time())
        window_start = now - (now % self.time_window)
        
        if self.redis_manager and self.redis_manager.is_connected():
            try:
                # 使用 Redis 实现滑动窗口限流
                current_window = self.redis_manager.get(window_key)
                
                if current_window is None or current_window != window_start:
                    # 新时间窗口，重置计数
                    self.redis_manager.set(count_key, 1, ttl=self.time_window)
                    self.redis_manager.set(window_key, window_start, ttl=self.time_window)
                    return True, self.max_requests - 1
                
                # 增加计数
                current_count = self.redis_manager.incr(count_key)
                self.redis_manager.expire(count_key, self.time_window)
                
                if current_count > self.max_requests:
                    remaining = 0
                else:
                    remaining = max(0, self.max_requests - current_count)
                
                return current_count <= self.max_requests, remaining
                
            except Exception as e:
                logger.warning(f"Redis 限流失败，降级到内存模式: {e}")
        
        # 降级到内存模式（使用线程本地存储）
        return self._memory_rate_limit(key, rate_key, window_start)
    
    def _memory_rate_limit(self, key: str, rate_key: str, window_start: int) -> Tuple[bool, int]:
        """内存模式限流（单进程）"""
        # 使用模块级字典存储（简单实现）
        if not hasattr(self, '_memory_cache'):
            self._memory_cache = {}
            self._memory_windows = {}
        
        if rate_key not in self._memory_cache or self._memory_windows.get(rate_key) != window_start:
            # 新时间窗口
            self._memory_cache[rate_key] = 1
            self._memory_windows[rate_key] = window_start
            return True, self.max_requests - 1
        
        # 增加计数
        self._memory_cache[rate_key] += 1
        current_count = self._memory_cache[rate_key]
        
        if current_count > self.max_requests:
            remaining = 0
        else:
            remaining = max(0, self.max_requests - current_count)
        
        return current_count <= self.max_requests, remaining


def redis_rate_limit(max_requests: int = 100, time_window: int = 60, key_func: Optional[Callable] = None):
    """
    Redis 分布式限流装饰器
    
    Args:
        max_requests: 时间窗口内最大请求数
        time_window: 时间窗口（秒）
        key_func: 自定义限流键生成函数，默认使用用户ID或IP
    """
    limiter = RedisRateLimiter(max_requests, time_window)
    
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            # 生成限流键
            if key_func:
                rate_key = key_func()
            else:
                # 默认：尝试从 g 获取用户ID，否则使用IP
                try:
                    from flask import g
                    if hasattr(g, 'current_user_id') and g.current_user_id:
                        rate_key = f"user_{g.current_user_id}"
                    else:
                        rate_key = f"ip_{request.remote_addr}"
                except:
                    rate_key = f"ip_{request.remote_addr}"
            
            # 检查限流
            allowed, remaining = limiter.is_allowed(rate_key)
            
            if not allowed:
                logger.warning(f"[Redis限流] 请求被限流: {rate_key}")
                return jsonify({
                    'success': False,
                    'message': '请求过于频繁，请稍后再试',
                    'retry_after': time_window,
                    'remaining': 0
                }), 429
            
            # 添加响应头
            response = func(*args, **kwargs)
            if hasattr(response, 'headers'):
                response.headers['X-RateLimit-Limit'] = str(max_requests)
                response.headers['X-RateLimit-Remaining'] = str(remaining)
                response.headers['X-RateLimit-Reset'] = str(int(time.time()) + time_window)
            
            return response
        return wrapper
    return decorator

