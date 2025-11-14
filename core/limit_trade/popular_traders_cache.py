#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
热门带单员缓存管理
"""

import time
from typing import Dict, List, Optional, Any
from utils.logger import logger


class PopularTradersCache:
    """热门带单员缓存管理器"""
    
    def __init__(self, default_ttl: int = 300):
        """
        初始化缓存管理器
        
        Args:
            default_ttl: 默认缓存过期时间（秒），默认5分钟
        """
        self.cache: Dict[str, Dict[str, Any]] = {}
        self.default_ttl = default_ttl
        logger.info(f"[热门带单员缓存] 初始化缓存管理器，默认TTL: {default_ttl}秒")
    
    def _generate_cache_key(self, exchange: str, **kwargs) -> str:
        """
        生成缓存键
        
        Args:
            exchange: 交易所类型
            **kwargs: 其他参数
            
        Returns:
            缓存键字符串
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
        
        return "|".join(key_parts)
    
    def get(self, exchange: str, **kwargs) -> Optional[Any]:
        """
        从缓存获取数据
        
        Args:
            exchange: 交易所类型（或自定义缓存键）
            **kwargs: 其他参数
            
        Returns:
            缓存的数据，如果不存在或已过期则返回None
        """
        # 如果exchange是自定义缓存键（以"whale_"开头），直接使用
        if isinstance(exchange, str) and exchange.startswith('whale_'):
            cache_key = exchange
        else:
            cache_key = self._generate_cache_key(exchange, **kwargs)
        
        if cache_key not in self.cache:
            logger.debug(f"[热门带单员缓存] 缓存未命中: {cache_key}")
            return None
        
        cached_data = self.cache[cache_key]
        current_time = time.time()
        
        # 检查是否过期
        if current_time > cached_data['expire_time']:
            logger.info(f"[热门带单员缓存] 缓存已过期: {cache_key}")
            del self.cache[cache_key]
            return None
        
        # 计算剩余时间
        remaining_time = int(cached_data['expire_time'] - current_time)
        logger.debug(f"[热门带单员缓存] 缓存命中: {cache_key}, 剩余时间: {remaining_time}秒")
        
        return cached_data['data']
    
    def set(self, exchange: str, data: Dict[str, List[Dict]], ttl: Optional[int] = None, **kwargs):
        """
        设置缓存数据
        
        Args:
            exchange: 交易所类型（或自定义缓存键）
            data: 要缓存的数据（可以是字典或列表）
            ttl: 缓存过期时间（秒），如果为None则使用默认值
            **kwargs: 其他参数
        """
        # 如果exchange是自定义缓存键（以"whale_"开头），直接使用
        if isinstance(exchange, str) and exchange.startswith('whale_'):
            cache_key = exchange
        else:
            cache_key = self._generate_cache_key(exchange, **kwargs)
        
        ttl = ttl or self.default_ttl
        expire_time = time.time() + ttl
        
        self.cache[cache_key] = {
            'data': data,
            'expire_time': expire_time,
            'created_time': time.time()
        }
        
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
        
        logger.info(f"[热门带单员缓存] 缓存已设置: {cache_key}, TTL: {ttl}秒, 数据量: {data_count}")
    
    def clear(self, exchange: Optional[str] = None):
        """
        清除缓存
        
        Args:
            exchange: 交易所类型，如果为None则清除所有缓存
        """
        if exchange is None:
            count = len(self.cache)
            self.cache.clear()
            logger.info(f"[热门带单员缓存] 已清除所有缓存，共 {count} 条")
        else:
            # 清除指定交易所的缓存
            keys_to_delete = [key for key in self.cache.keys() if key.startswith(f"exchange:{exchange}|")]
            for key in keys_to_delete:
                del self.cache[key]
            logger.info(f"[热门带单员缓存] 已清除 {exchange} 的缓存，共 {len(keys_to_delete)} 条")
    
    def get_cache_info(self) -> Dict[str, Any]:
        """
        获取缓存信息
        
        Returns:
            缓存统计信息
        """
        current_time = time.time()
        valid_count = 0
        expired_count = 0
        
        for cached_data in self.cache.values():
            if current_time <= cached_data['expire_time']:
                valid_count += 1
            else:
                expired_count += 1
        
        return {
            'total': len(self.cache),
            'valid': valid_count,
            'expired': expired_count,
            'default_ttl': self.default_ttl
        }
    
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


def get_cache(ttl: int = 300) -> PopularTradersCache:
    """
    获取全局缓存实例（单例模式）
    
    Args:
        ttl: 默认缓存过期时间（秒）
        
    Returns:
        缓存管理器实例
    """
    global _global_cache
    if _global_cache is None:
        _global_cache = PopularTradersCache(default_ttl=ttl)
    return _global_cache

