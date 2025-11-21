#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Redis 管理器
提供 Redis 连接、缓存、分布式限流等功能
支持可选使用（如果 Redis 不可用，自动降级到内存模式）
"""

import time
import threading
from typing import Optional, Dict, Any, Callable
from functools import wraps
from utils.logger import logger

# 尝试导入 Redis
try:
    import redis
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False
    logger.warning("Redis 模块不可用，将使用内存模式")

# 全局 Redis 客户端
_redis_client: Optional[Any] = None
_redis_lock = threading.Lock()


class RedisManager:
    """Redis 管理器（单例模式）"""
    
    def __init__(self, host: str = 'localhost', port: int = 6379, db: int = 0, 
                 password: Optional[str] = None, decode_responses: bool = True):
        """
        初始化 Redis 管理器
        
        Args:
            host: Redis 主机
            port: Redis 端口
            db: Redis 数据库编号
            password: Redis 密码
            decode_responses: 是否自动解码响应
        """
        self.host = host
        self.port = port
        self.db = db
        self.password = password
        self.decode_responses = decode_responses
        self.client: Optional[Any] = None
        self._fallback_cache: Dict[str, Any] = {}  # 内存缓存（降级使用）
        self._fallback_timestamps: Dict[str, float] = {}
        self._fallback_lock = threading.Lock()
        self._is_connected = False
        
    def connect(self) -> bool:
        """连接 Redis"""
        if not REDIS_AVAILABLE:
            logger.warning("Redis 模块不可用，使用内存模式")
            self._is_connected = False
            return False
        
        try:
            self.client = redis.Redis(
                host=self.host,
                port=self.port,
                db=self.db,
                password=self.password,
                decode_responses=self.decode_responses,
                socket_connect_timeout=2,
                socket_timeout=2
            )
            # 测试连接
            self.client.ping()
            self._is_connected = True
            logger.info(f"✅ Redis 连接成功: {self.host}:{self.port}")
            return True
        except Exception as e:
            logger.warning(f"Redis 连接失败，使用内存模式: {e}")
            self._is_connected = False
            return False
    
    def is_connected(self) -> bool:
        """检查是否已连接"""
        if not self._is_connected or not self.client:
            return False
        try:
            self.client.ping()
            return True
        except:
            self._is_connected = False
            return False
    
    def get(self, key: str, default: Any = None) -> Any:
        """获取缓存值"""
        if self.is_connected():
            try:
                value = self.client.get(key)
                if value is None:
                    return default
                # 尝试解析 JSON
                try:
                    import json
                    return json.loads(value)
                except:
                    return value
            except Exception as e:
                logger.warning(f"Redis get 失败，使用内存缓存: {e}")
                self._is_connected = False
        
        # 降级到内存缓存
        with self._fallback_lock:
            if key in self._fallback_cache:
                return self._fallback_cache[key]
            return default
    
    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> bool:
        """设置缓存值"""
        if self.is_connected():
            try:
                import json
                from datetime import datetime, date
                
                # 自定义 JSON 序列化函数，处理 datetime 和 date 对象
                def json_serializer(obj):
                    if isinstance(obj, (datetime, date)):
                        return obj.isoformat()
                    raise TypeError(f"Object of type {type(obj)} is not JSON serializable")
                
                if isinstance(value, (dict, list)):
                    # 使用自定义序列化函数处理 datetime 对象
                    value = json.dumps(value, default=json_serializer)
                if ttl:
                    self.client.setex(key, ttl, value)
                else:
                    self.client.set(key, value)
                return True
            except Exception as e:
                logger.warning(f"Redis set 失败，使用内存缓存: {e}")
                self._is_connected = False
        
        # 降级到内存缓存
        with self._fallback_lock:
            self._fallback_cache[key] = value
            if ttl:
                self._fallback_timestamps[key] = time.time() + ttl
            return True
    
    def delete(self, key: str) -> bool:
        """删除缓存值"""
        if self.is_connected():
            try:
                self.client.delete(key)
                return True
            except Exception as e:
                logger.warning(f"Redis delete 失败: {e}")
                self._is_connected = False
        
        # 降级到内存缓存
        with self._fallback_lock:
            self._fallback_cache.pop(key, None)
            self._fallback_timestamps.pop(key, None)
            return True
    
    def incr(self, key: str, amount: int = 1) -> int:
        """递增计数器"""
        if self.is_connected():
            try:
                return self.client.incrby(key, amount)
            except Exception as e:
                logger.warning(f"Redis incr 失败，使用内存缓存: {e}")
                self._is_connected = False
        
        # 降级到内存缓存
        with self._fallback_lock:
            current = self._fallback_cache.get(key, 0)
            new_value = current + amount
            self._fallback_cache[key] = new_value
            return new_value
    
    def expire(self, key: str, ttl: int) -> bool:
        """设置过期时间"""
        if self.is_connected():
            try:
                return bool(self.client.expire(key, ttl))
            except Exception as e:
                logger.warning(f"Redis expire 失败: {e}")
                self._is_connected = False
        
        # 降级到内存缓存
        with self._fallback_lock:
            if key in self._fallback_cache:
                self._fallback_timestamps[key] = time.time() + ttl
            return True
    
    def cleanup_expired(self):
        """清理过期的内存缓存"""
        if not self.is_connected():
            with self._fallback_lock:
                now = time.time()
                expired_keys = [
                    key for key, expire_time in self._fallback_timestamps.items()
                    if expire_time < now
                ]
                for key in expired_keys:
                    self._fallback_cache.pop(key, None)
                    self._fallback_timestamps.pop(key, None)


# 全局 Redis 管理器实例
_global_redis_manager: Optional[RedisManager] = None


def get_redis_manager() -> RedisManager:
    """获取全局 Redis 管理器（单例）"""
    global _global_redis_manager
    
    if _global_redis_manager is None:
        with _redis_lock:
            if _global_redis_manager is None:
                # 从配置读取 Redis 设置
                try:
                    from config.config import get_redis_config
                    redis_config = get_redis_config()
                except:
                    redis_config = {
                        'host': 'localhost',
                        'port': 6379,
                        'db': 0,
                        'password': None
                    }
                
                _global_redis_manager = RedisManager(**redis_config)
                _global_redis_manager.connect()
    
    return _global_redis_manager


def redis_cache(key_prefix: str = '', ttl: int = 300):
    """
    Redis 缓存装饰器（自动降级到内存缓存）
    
    Args:
        key_prefix: 缓存键前缀
        ttl: 缓存过期时间（秒）
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            # 生成缓存键
            import hashlib
            import json
            from datetime import datetime, date
            
            # 自定义 JSON 序列化函数，处理 datetime 和 date 对象
            def json_serializer(obj):
                if isinstance(obj, (datetime, date)):
                    return obj.isoformat()
                raise TypeError(f"Object of type {type(obj)} is not JSON serializable")
            
            cache_key = f"{key_prefix}:{func.__name__}:{hashlib.md5(json.dumps({'args': args, 'kwargs': kwargs}, sort_keys=True, default=json_serializer).encode()).hexdigest()}"
            
            # 尝试从缓存获取
            redis_manager = get_redis_manager()
            cached_value = redis_manager.get(cache_key)
            if cached_value is not None:
                logger.debug(f"[Redis缓存] 命中: {cache_key}")
                return cached_value
            
            # 执行函数
            result = func(*args, **kwargs)
            
            # 存入缓存
            redis_manager.set(cache_key, result, ttl=ttl)
            logger.debug(f"[Redis缓存] 存储: {cache_key}")
            
            return result
        return wrapper
    return decorator

