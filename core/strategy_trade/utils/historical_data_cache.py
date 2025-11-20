#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
回测历史数据缓存工具
将回测获取的历史数据缓存到 Redis，避免重复请求 API
"""

import json
import hashlib
from typing import List, Optional, Dict, Any
from datetime import datetime
from utils.logger import get_logger
from core.redis_manager import get_redis_manager

logger = get_logger(__name__)

# 缓存键前缀
CACHE_PREFIX = "backtest:historical_data"

# 默认缓存时间（7天）
DEFAULT_CACHE_TTL = 7 * 24 * 60 * 60  # 7天


def generate_cache_key(symbol: str, timeframe: str, start_date: str, end_date: str) -> str:
    """
    生成缓存键
    
    Args:
        symbol: 交易对（如 BTC-USDT）
        timeframe: 时间周期（如 1H, 4H, 1D）
        start_date: 开始日期（格式：YYYY-MM-DD）
        end_date: 结束日期（格式：YYYY-MM-DD）
    
    Returns:
        缓存键字符串
    """
    # 使用参数生成唯一键
    key_data = f"{symbol}:{timeframe}:{start_date}:{end_date}"
    key_hash = hashlib.md5(key_data.encode()).hexdigest()[:16]
    return f"{CACHE_PREFIX}:{key_hash}"


def _extract_data_by_time_range(historical_data: List[List], start_date: str, end_date: str) -> List[List]:
    """
    从历史数据中提取指定时间范围的数据
    
    Args:
        historical_data: 历史数据列表（OKX格式：[[timestamp, open, high, low, close, volume], ...]）
        start_date: 开始日期（格式：YYYY-MM-DD）
        end_date: 结束日期（格式：YYYY-MM-DD）
    
    Returns:
        提取的数据列表
    """
    try:
        start_dt = datetime.strptime(start_date, '%Y-%m-%d')
        end_dt = datetime.strptime(end_date, '%Y-%m-%d').replace(hour=23, minute=59, second=59)
        start_timestamp = int(start_dt.timestamp() * 1000)
        end_timestamp = int(end_dt.timestamp() * 1000)
        
        extracted_data = []
        for kline in historical_data:
            # 确保 timestamp 是整数
            timestamp_ms = int(kline[0]) if not isinstance(kline[0], int) else kline[0]
            
            # 只保留在指定时间范围内的数据
            if start_timestamp <= timestamp_ms <= end_timestamp:
                extracted_data.append(kline)
        
        return extracted_data
    except Exception as e:
        logger.warning(f"[历史数据缓存] 提取时间范围数据失败: {e}")
        return []


def get_cached_historical_data(symbol: str, timeframe: str, start_date: str, end_date: str) -> Optional[List[List]]:
    """
    从 Redis 获取缓存的历史数据
    
    支持两种模式：
    1. 完全匹配：如果存在完全相同的参数缓存，直接返回
    2. 时间范围包含：如果存在包含请求时间范围的缓存，从缓存中提取对应数据
    
    Args:
        symbol: 交易对
        timeframe: 时间周期
        start_date: 开始日期
        end_date: 结束日期
    
    Returns:
        历史数据列表，如果缓存不存在或不符合要求则返回 None
    """
    try:
        redis_manager = get_redis_manager()
        
        if not redis_manager.is_connected():
            logger.debug("[历史数据缓存] Redis 未连接，无法使用缓存")
            return None
        
        # 首先尝试完全匹配
        cache_key = generate_cache_key(symbol, timeframe, start_date, end_date)
        cached_data = redis_manager.get(cache_key)
        
        if cached_data and isinstance(cached_data, dict):
            cache_meta = cached_data.get('meta', {})
            if (cache_meta.get('symbol') == symbol and
                cache_meta.get('timeframe') == timeframe and
                cache_meta.get('start_date') == start_date and
                cache_meta.get('end_date') == end_date):
                historical_data = cached_data.get('data', [])
                logger.info(f"[历史数据缓存] ✅ 完全匹配缓存: {cache_key}, 数据量: {len(historical_data)} 条")
                return historical_data
        
        # 如果没有完全匹配，查找包含时间范围的缓存
        logger.debug(f"[历史数据缓存] 完全匹配未命中，查找包含时间范围的缓存...")
        
        # 解析请求的时间范围
        request_start_dt = datetime.strptime(start_date, '%Y-%m-%d')
        request_end_dt = datetime.strptime(end_date, '%Y-%m-%d').replace(hour=23, minute=59, second=59)
        
        # 遍历所有缓存，查找匹配的
        pattern = f"{CACHE_PREFIX}:*"
        try:
            keys = redis_manager.client.keys(pattern)
        except Exception as e:
            logger.warning(f"[历史数据缓存] 获取缓存键列表失败: {e}")
            return None
        
        best_match = None
        best_match_key = None
        
        for key in keys:
            try:
                cached_data = redis_manager.get(key)
                if not cached_data or not isinstance(cached_data, dict):
                    continue
                
                cache_meta = cached_data.get('meta', {})
                
                # 检查 symbol 和 timeframe 是否匹配
                if (cache_meta.get('symbol') != symbol or
                    cache_meta.get('timeframe') != timeframe):
                    continue
                
                # 检查时间范围是否包含请求的时间范围
                cache_start_date = cache_meta.get('start_date')
                cache_end_date = cache_meta.get('end_date')
                
                if not cache_start_date or not cache_end_date:
                    continue
                
                try:
                    cache_start_dt = datetime.strptime(cache_start_date, '%Y-%m-%d')
                    cache_end_dt = datetime.strptime(cache_end_date, '%Y-%m-%d').replace(hour=23, minute=59, second=59)
                    
                    # 检查缓存的时间范围是否包含请求的时间范围
                    if cache_start_dt <= request_start_dt and request_end_dt <= cache_end_dt:
                        # 找到包含时间范围的缓存，记录为最佳匹配
                        # 优先选择时间范围最接近的缓存（避免使用过大的缓存）
                        cache_range = (cache_end_dt - cache_start_dt).days
                        request_range = (request_end_dt - request_start_dt).days
                        
                        if best_match is None or cache_range < (best_match['end'] - best_match['start']).days:
                            best_match = {
                                'start': cache_start_dt,
                                'end': cache_end_dt,
                                'data': cached_data.get('data', []),
                                'key': key
                            }
                            best_match_key = key
                except ValueError as e:
                    logger.warning(f"[历史数据缓存] 解析缓存时间范围失败 {key}: {e}")
                    continue
                    
            except Exception as e:
                logger.warning(f"[历史数据缓存] 检查缓存键失败 {key}: {e}")
                continue
        
        # 如果找到包含时间范围的缓存，提取对应数据
        if best_match:
            logger.info(f"[历史数据缓存] ✅ 找到包含时间范围的缓存: {best_match_key}")
            logger.info(f"[历史数据缓存] 缓存范围: {best_match['start'].strftime('%Y-%m-%d')} -> {best_match['end'].strftime('%Y-%m-%d')}")
            logger.info(f"[历史数据缓存] 请求范围: {start_date} -> {end_date}")
            
            # 从缓存数据中提取请求的时间范围
            extracted_data = _extract_data_by_time_range(best_match['data'], start_date, end_date)
            
            if extracted_data:
                logger.info(f"[历史数据缓存] ✅ 从缓存中提取数据: {len(extracted_data)} 条")
                return extracted_data
            else:
                logger.warning(f"[历史数据缓存] ⚠️ 从缓存中提取的数据为空")
                return None
        
        logger.debug(f"[历史数据缓存] 未找到包含时间范围的缓存")
        return None
        
    except Exception as e:
        logger.warning(f"[历史数据缓存] 获取缓存失败: {e}")
        import traceback
        logger.warning(traceback.format_exc())
        return None


def cache_historical_data(symbol: str, timeframe: str, start_date: str, end_date: str, 
                         historical_data: List[List], ttl: Optional[int] = None) -> bool:
    """
    将历史数据缓存到 Redis
    
    Args:
        symbol: 交易对
        timeframe: 时间周期
        start_date: 开始日期
        end_date: 结束日期
        historical_data: 历史数据列表
        ttl: 缓存过期时间（秒），默认7天
    
    Returns:
        是否缓存成功
    """
    try:
        cache_key = generate_cache_key(symbol, timeframe, start_date, end_date)
        redis_manager = get_redis_manager()
        
        # 构建缓存数据结构
        cache_data = {
            'meta': {
                'symbol': symbol,
                'timeframe': timeframe,
                'start_date': start_date,
                'end_date': end_date,
                'data_count': len(historical_data),
                'cached_at': datetime.now().isoformat()
            },
            'data': historical_data
        }
        
        # 设置缓存
        cache_ttl = ttl if ttl is not None else DEFAULT_CACHE_TTL
        success = redis_manager.set(cache_key, cache_data, ttl=cache_ttl)
        
        if success:
            logger.info(f"[历史数据缓存] ✅ 已缓存: {cache_key}, 数据量: {len(historical_data)} 条, TTL: {cache_ttl}秒")
        else:
            logger.warning(f"[历史数据缓存] ❌ 缓存失败: {cache_key}")
        
        return success
        
    except Exception as e:
        logger.warning(f"[历史数据缓存] 缓存数据失败: {e}")
        return False


def clear_historical_data_cache(symbol: Optional[str] = None, timeframe: Optional[str] = None) -> int:
    """
    清除历史数据缓存
    
    Args:
        symbol: 交易对（可选，如果指定则只清除该交易对的缓存）
        timeframe: 时间周期（可选，如果指定则只清除该周期的缓存）
    
    Returns:
        清除的缓存数量
    """
    try:
        redis_manager = get_redis_manager()
        
        if not redis_manager.is_connected():
            logger.warning("[历史数据缓存] Redis 未连接，无法清除缓存")
            return 0
        
        # 如果指定了 symbol 或 timeframe，需要遍历所有键
        # 否则直接清除所有以 CACHE_PREFIX 开头的键
        if symbol or timeframe:
            # 需要遍历所有键（性能较低，但更精确）
            pattern = f"{CACHE_PREFIX}:*"
            keys = redis_manager.client.keys(pattern)
            deleted_count = 0
            
            for key in keys:
                try:
                    cached_data = redis_manager.get(key)
                    if cached_data and isinstance(cached_data, dict):
                        cache_meta = cached_data.get('meta', {})
                        if symbol and cache_meta.get('symbol') != symbol:
                            continue
                        if timeframe and cache_meta.get('timeframe') != timeframe:
                            continue
                        redis_manager.delete(key)
                        deleted_count += 1
                except Exception as e:
                    logger.warning(f"[历史数据缓存] 清除缓存键失败 {key}: {e}")
            
            logger.info(f"[历史数据缓存] 清除缓存: {deleted_count} 个")
            return deleted_count
        else:
            # 清除所有历史数据缓存
            pattern = f"{CACHE_PREFIX}:*"
            keys = redis_manager.client.keys(pattern)
            deleted_count = 0
            
            for key in keys:
                try:
                    redis_manager.delete(key)
                    deleted_count += 1
                except Exception as e:
                    logger.warning(f"[历史数据缓存] 清除缓存键失败 {key}: {e}")
            
            logger.info(f"[历史数据缓存] 清除所有缓存: {deleted_count} 个")
            return deleted_count
            
    except Exception as e:
        logger.warning(f"[历史数据缓存] 清除缓存失败: {e}")
        return 0

