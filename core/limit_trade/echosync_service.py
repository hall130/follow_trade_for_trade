#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Echosync 服务层
管理 Echosync API 数据的获取和缓存
"""

import aiohttp
import time
from typing import Dict, List, Optional
from utils.logger import logger
from core.limit_trade.collectors.echosync_collector import EchosyncCollector
from core.limit_trade.popular_traders_cache import get_cache


class EchosyncService:
    """Echosync 服务"""
    
    def __init__(self, config: Optional[Dict] = None):
        """
        初始化 Echosync 服务
        
        Args:
            config: 配置字典
        """
        self.config = config or {}
        self.collector = EchosyncCollector(self.config.get('echosync', {}))
        # 使用5分钟缓存
        self.cache = get_cache(ttl=self.config.get('cache_ttl', 300))
    
    async def get_leaderboard(
        self,
        sort_by: str = 'total_pnl',
        period_days: int = 180,
        page_size: int = 100,
        use_cache: bool = True
    ) -> Dict:
        """
        获取排行榜数据（带缓存）
        
        Args:
            sort_by: 排序字段
            period_days: 统计周期
            page_size: 每页数量
            use_cache: 是否使用缓存
            
        Returns:
            排行榜数据
        """
        # 生成缓存键
        cache_key = f"echosync_leaderboard_{sort_by}_{period_days}_{page_size}"
        
        # 检查缓存
        if use_cache:
            cached_data = self.cache.get(cache_key)
            if cached_data is not None:
                logger.info(f"[Echosync服务] 使用缓存数据: {cache_key}")
                return cached_data
        
        # 获取数据（添加延迟，避免频繁请求）
        import asyncio
        import random
        # 添加随机延迟（0.5-1.5秒），避免请求过于频繁
        await asyncio.sleep(random.uniform(0.5, 1.5))
        
        async with aiohttp.ClientSession() as session:
            result = await self.collector.get_leaderboard(
                session,
                sort_by=sort_by,
                period_days=period_days,
                page=1,  # 只获取第一页
                page_size=page_size
            )
        
        # 缓存数据
        if use_cache and result.get('success'):
            self.cache.set(cache_key, result)
            logger.info(f"[Echosync服务] 缓存数据: {cache_key}, 数据量={len(result.get('data', []))}")
        
        return result
    
    async def get_whale_orders(
        self,
        min_trade_amount: float = 100000,
        start_date: Optional[int] = None,
        end_date: Optional[int] = None,
        page_size: int = 100,
        trade_type: str = 'perpetual',
        use_cache: bool = False  # 巨鲸订单不缓存，实时性要求高
    ) -> Dict:
        """
        获取巨鲸订单数据
        
        Args:
            min_trade_amount: 最小交易金额
            start_date: 开始时间（毫秒时间戳）
            end_date: 结束时间（毫秒时间戳）
            page_size: 每页数量
            trade_type: 交易类型
            use_cache: 是否使用缓存
            
        Returns:
            巨鲸订单数据
        """
        # 生成缓存键
        if use_cache:
            cache_key = f"echosync_whale_orders_{min_trade_amount}_{trade_type}_{int(time.time() // 60)}"
            cached_data = self.cache.get(cache_key)
            if cached_data is not None:
                logger.info(f"[Echosync服务] 使用缓存数据: {cache_key}")
                return cached_data
        
        # 获取数据（添加延迟，避免频繁请求）
        import asyncio
        import random
        # 添加随机延迟（0.5-1.5秒），避免请求过于频繁
        await asyncio.sleep(random.uniform(0.5, 1.5))
        
        async with aiohttp.ClientSession() as session:
            result = await self.collector.get_whale_orders(
                session,
                min_trade_amount=min_trade_amount,
                start_date=start_date,
                end_date=end_date,
                page=1,
                page_size=page_size,
                trade_type=trade_type
            )
        
        # 缓存数据（1分钟缓存）
        if use_cache and result.get('success'):
            self.cache.set(cache_key, result)
        
        return result
    
    async def get_whale_moves(
        self,
        min_amount: float = 10000,
        max_amount: float = 99999999999,
        start_date: Optional[int] = None,
        end_date: Optional[int] = None,
        page_size: int = 20,
        use_cache: bool = False  # 巨鲸转移不缓存，实时性要求高
    ) -> Dict:
        """
        获取巨鲸资金转移数据
        
        Args:
            min_amount: 最小金额
            max_amount: 最大金额
            start_date: 开始时间（秒时间戳）
            end_date: 结束时间（秒时间戳）
            page_size: 每页数量
            use_cache: 是否使用缓存
            
        Returns:
            巨鲸资金转移数据
        """
        # 生成缓存键
        if use_cache:
            cache_key = f"echosync_whale_moves_{min_amount}_{int(time.time() // 60)}"
            cached_data = self.cache.get(cache_key)
            if cached_data is not None:
                logger.info(f"[Echosync服务] 使用缓存数据: {cache_key}")
                return cached_data
        
        # 获取数据（添加延迟，避免频繁请求）
        import asyncio
        import random
        # 添加随机延迟（0.5-1.5秒），避免请求过于频繁
        await asyncio.sleep(random.uniform(0.5, 1.5))
        
        async with aiohttp.ClientSession() as session:
            result = await self.collector.get_whale_moves(
                session,
                min_amount=min_amount,
                max_amount=max_amount,
                start_date=start_date,
                end_date=end_date,
                page=1,
                page_size=page_size
            )
        
        # 缓存数据（1分钟缓存）
        if use_cache and result.get('success'):
            self.cache.set(cache_key, result)
        
        return result
    
    async def get_user_portfolio(
        self,
        user_address: str,
        use_cache: bool = True
    ) -> Dict:
        """
        获取用户详细信息
        
        Args:
            user_address: 用户地址
            use_cache: 是否使用缓存
            
        Returns:
            用户详细信息
        """
        # 生成缓存键
        cache_key = f"hyperliquid_portfolio_{user_address}"
        
        # 检查缓存
        if use_cache:
            cached_data = self.cache.get(cache_key)
            if cached_data is not None:
                logger.info(f"[Echosync服务] 使用缓存数据: {cache_key}")
                return cached_data
        
        # 获取数据
        async with aiohttp.ClientSession() as session:
            result = await self.collector.get_user_portfolio(session, user_address)
        
        # 缓存数据
        if use_cache and result.get('success'):
            self.cache.set(cache_key, result)
        
        return result

