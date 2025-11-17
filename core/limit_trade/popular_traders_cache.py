#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
热门带单员缓存管理
使用 Redis 缓存，支持降级到内存缓存
"""

import time
from typing import Dict, List, Optional, Any
from utils.logger import logger
from core.redis_manager import get_redis_manager

# 缓存键前缀
CACHE_PREFIX = "popular_traders"


class PopularTradersCache:
    """热门带单员缓存管理器（支持 Redis 和内存缓存）"""
    
    def __init__(self, default_ttl: int = 1800):
        """
        初始化缓存管理器
        
        Args:
            default_ttl: 默认缓存过期时间（秒），默认30分钟（1800秒）
        """
        self.redis = get_redis_manager()
        self.cache: Dict[str, Dict[str, Any]] = {}  # 内存缓存（降级使用）
        self.default_ttl = default_ttl
        self.use_redis = self.redis.is_connected()
        
        if self.use_redis:
            logger.info(f"[热门带单员缓存] 使用 Redis 缓存，默认TTL: {default_ttl}秒（30分钟）")
        else:
            logger.info(f"[热门带单员缓存] Redis 不可用，使用内存缓存，默认TTL: {default_ttl}秒（30分钟）")
    
    def _generate_cache_key(self, exchange: str, **kwargs) -> str:
        """
        生成缓存键
        
        Args:
            exchange: 交易所类型
            **kwargs: 其他参数
            
        Returns:
            缓存键字符串（带前缀）
        """
        # 构建缓存键，包含关键参数
        key_parts = [f"exchange:{exchange}"]
        
        # 添加关键筛选参数
        if 'time_range' in kwargs:
            key_parts.append(f"time_range:{kwargs['time_range']}")
        if 'data_type' in kwargs:
            key_parts.append(f"data_type:{kwargs['data_type']}")
        if 'order' in kwargs:
            key_parts.append(f"order:{kwargs['order']}")
        if 'country_id' in kwargs:
            key_parts.append(f"country_id:{kwargs['country_id']}")
        if 'okx_data_type' in kwargs:
            key_parts.append(f"okx_data_type:{kwargs['okx_data_type']}")
        if 'binance_data_type' in kwargs:
            key_parts.append(f"binance_data_type:{kwargs['binance_data_type']}")
        
        # 添加前缀
        cache_key = "|".join(key_parts)
        return f"{CACHE_PREFIX}:{cache_key}"
    
    def get(self, exchange: str, **kwargs) -> Optional[Any]:
        """
        从缓存获取数据（优先使用 Redis，降级到内存缓存）
        
        Args:
            exchange: 交易所类型（或自定义缓存键）
            **kwargs: 其他参数
            
        Returns:
            缓存的数据，如果不存在或已过期则返回None
        """
        # 如果exchange是自定义缓存键（以"whale_"开头），直接使用
        if isinstance(exchange, str) and exchange.startswith('whale_'):
            cache_key = f"{CACHE_PREFIX}:{exchange}"
        else:
            cache_key = self._generate_cache_key(exchange, **kwargs)
        
        # 优先使用 Redis
        if self.use_redis:
            try:
                cached_data = self.redis.get(cache_key)
                if cached_data is not None:
                    # Redis 中的数据直接是数据本身（TTL 由 Redis 管理）
                    logger.debug(f"[热门带单员缓存] Redis 缓存命中: {cache_key}")
                    return cached_data
                else:
                    logger.debug(f"[热门带单员缓存] Redis 缓存未命中: {cache_key}")
            except Exception as e:
                logger.warning(f"[热门带单员缓存] Redis 获取失败，降级到内存缓存: {e}")
                self.use_redis = False
        
        # 降级到内存缓存
        if cache_key not in self.cache:
            logger.debug(f"[热门带单员缓存] 内存缓存未命中: {cache_key}")
            return None
        
        cached_data = self.cache[cache_key]
        current_time = time.time()
        
        # 检查是否过期
        if current_time > cached_data['expire_time']:
            logger.info(f"[热门带单员缓存] 内存缓存已过期: {cache_key}")
            del self.cache[cache_key]
            return None
        
        # 计算剩余时间
        remaining_time = int(cached_data['expire_time'] - current_time)
        logger.debug(f"[热门带单员缓存] 内存缓存命中: {cache_key}, 剩余时间: {remaining_time}秒")
        
        return cached_data['data']
    
    def set(self, exchange: str, data: Dict[str, List[Dict]], ttl: Optional[int] = None, **kwargs):
        """
        设置缓存数据（优先使用 Redis，降级到内存缓存）
        
        Args:
            exchange: 交易所类型（或自定义缓存键）
            data: 要缓存的数据（可以是字典或列表）
            ttl: 缓存过期时间（秒），如果为None则使用默认值
            **kwargs: 其他参数
        """
        # 如果exchange是自定义缓存键（以"whale_"开头），直接使用
        if isinstance(exchange, str) and exchange.startswith('whale_'):
            cache_key = f"{CACHE_PREFIX}:{exchange}"
        else:
            cache_key = self._generate_cache_key(exchange, **kwargs)
        
        ttl = ttl or self.default_ttl
        
        # 计算数据量（支持多种数据格式）
        if isinstance(data, dict):
            # 检查是否是 API 响应格式 (包含 success, data, cached 等键)
            if 'data' in data and isinstance(data.get('data'), (list, dict)):
                # Echosync API 响应格式
                if isinstance(data['data'], list):
                    data_count = len(data['data'])
                elif isinstance(data['data'], dict):
                    data_count = sum(len(v) for v in data['data'].values() if isinstance(v, list))
                else:
                    data_count = 0
            else:
                # 普通字典格式 (如 {okx: [...], binance: [...]})
                data_count = sum(len(v) for v in data.values() if isinstance(v, list))
        elif isinstance(data, list):
            data_count = len(data)
        else:
            data_count = 0
        
        # 优先使用 Redis
        if self.use_redis:
            try:
                success = self.redis.set(cache_key, data, ttl=ttl)
                if success:
                    logger.info(f"[热门带单员缓存] Redis 缓存已设置: {cache_key}, TTL: {ttl}秒（30分钟）, 数据量: {data_count}")
                    return
                else:
                    logger.warning(f"[热门带单员缓存] Redis 设置失败，降级到内存缓存")
                    self.use_redis = False
            except Exception as e:
                logger.warning(f"[热门带单员缓存] Redis 设置异常，降级到内存缓存: {e}")
                self.use_redis = False
        
        # 降级到内存缓存
        expire_time = time.time() + ttl
        self.cache[cache_key] = {
            'data': data,
            'expire_time': expire_time,
            'created_time': time.time()
        }
        logger.info(f"[热门带单员缓存] 内存缓存已设置: {cache_key}, TTL: {ttl}秒（30分钟）, 数据量: {data_count}")
    
    def clear(self, exchange: Optional[str] = None):
        """
        清除缓存（Redis 和内存缓存）
        
        Args:
            exchange: 交易所类型，如果为None则清除所有缓存
        """
        deleted_count = 0
        
        # 清除 Redis 缓存
        if self.use_redis:
            try:
                if exchange is None:
                    # 清除所有热门带单员缓存
                    pattern = f"{CACHE_PREFIX}:*"
                    cursor = 0
                    while True:
                        cursor, keys = self.redis.client.scan(
                            cursor=cursor,
                            match=pattern,
                            count=100
                        )
                        if keys:
                            self.redis.client.delete(*keys)
                            deleted_count += len(keys)
                        if cursor == 0:
                            break
                else:
                    # 清除指定交易所的缓存
                    pattern = f"{CACHE_PREFIX}:exchange:{exchange}*"
                    cursor = 0
                    while True:
                        cursor, keys = self.redis.client.scan(
                            cursor=cursor,
                            match=pattern,
                            count=100
                        )
                        if keys:
                            self.redis.client.delete(*keys)
                            deleted_count += len(keys)
                        if cursor == 0:
                            break
            except Exception as e:
                logger.warning(f"[热门带单员缓存] Redis 清除失败: {e}")
        
        # 清除内存缓存
        if exchange is None:
            count = len(self.cache)
            self.cache.clear()
            deleted_count += count
            logger.info(f"[热门带单员缓存] 已清除所有缓存，共 {deleted_count} 条")
        else:
            # 清除指定交易所的缓存
            keys_to_delete = [key for key in self.cache.keys() if f"exchange:{exchange}" in key]
            for key in keys_to_delete:
                del self.cache[key]
            deleted_count += len(keys_to_delete)
            logger.info(f"[热门带单员缓存] 已清除 {exchange} 的缓存，共 {deleted_count} 条")
    
    def get_cache_info(self) -> Dict[str, Any]:
        """
        获取缓存信息（包括 Redis 和内存缓存）
        
        Returns:
            缓存统计信息
        """
        info = {
            'default_ttl': self.default_ttl,
            'use_redis': self.use_redis,
            'memory_cache': {
                'total': 0,
                'valid': 0,
                'expired': 0
            },
            'redis_cache': {
                'total': 0
            }
        }
        
        # 统计内存缓存
        current_time = time.time()
        valid_count = 0
        expired_count = 0
        
        for cached_data in self.cache.values():
            if current_time <= cached_data['expire_time']:
                valid_count += 1
            else:
                expired_count += 1
        
        info['memory_cache'] = {
            'total': len(self.cache),
            'valid': valid_count,
            'expired': expired_count
        }
        
        # 统计 Redis 缓存
        if self.use_redis:
            try:
                cursor = 0
                redis_count = 0
                while True:
                    cursor, keys = self.redis.client.scan(
                        cursor=cursor,
                        match=f"{CACHE_PREFIX}:*",
                        count=100
                    )
                    redis_count += len(keys)
                    if cursor == 0:
                        break
                info['redis_cache']['total'] = redis_count
            except Exception as e:
                logger.warning(f"[热门带单员缓存] 获取 Redis 统计失败: {e}")
        
        return info
    
    def cleanup_expired(self):
        """
        清理过期的缓存项
        """
        current_time = time.time()
        expired_keys = []
        
        for key, cached_data in self.cache.items():
            if current_time > cached_data['expire_time']:
                expired_keys.append(key)
        
        for key in expired_keys:
            del self.cache[key]
        
        if expired_keys:
            logger.info(f"[热门带单员缓存] 已清理 {len(expired_keys)} 个过期缓存项")


# 全局缓存实例
_global_cache: Optional[PopularTradersCache] = None


def get_cache(ttl: int = 1800) -> PopularTradersCache:
    """
    获取全局缓存实例（单例模式）
    
    Args:
        ttl: 默认缓存过期时间（秒），默认30分钟（1800秒）
        
    Returns:
        缓存管理器实例
    """
    global _global_cache
    if _global_cache is None:
        _global_cache = PopularTradersCache(default_ttl=ttl)
    return _global_cache

