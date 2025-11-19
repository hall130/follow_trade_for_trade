#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
热门带单员服务
统一管理OKX和Binance的热门带单员数据
"""

import aiohttp
from typing import Dict, List, Optional, Any
from utils.logger import logger
from core.limit_trade.collectors.okx_popular_collector import OKXPopularTraderCollector
from core.limit_trade.collectors.binance_popular_collector import BinancePopularTraderCollector
from core.limit_trade.popular_traders_cache import get_cache


class PopularTradersService:
    """热门带单员服务"""
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        初始化热门带单员服务
        
        Args:
            config: 配置字典
        """
        self.config = config or {}
        self.okx_collector = OKXPopularTraderCollector(
            self.config.get('okx', {})
        )
        self.binance_collector = BinancePopularTraderCollector(
            self.config.get('binance', {})
        )
        self.cache = get_cache(ttl=self.config.get('cache_ttl', 3600))  # 默认1小时缓存
        self.max_pages = self.config.get('max_pages', 4)  # 默认最多获取4页
        # 公开/私域检测配置
        self.check_public_enabled = self.config.get('check_public', True)  # 是否检测公开/私域
        self.check_public_concurrent = self.config.get('check_public_concurrent', 5)  # 并发检测数量
        self.check_public_interval = self.config.get('check_public_interval', 0.5)  # 检测间隔（秒）
    
    async def get_popular_traders(
        self,
        exchange: str = 'all',
        fetch_all: bool = True,
        use_cache: bool = True,
        **kwargs
    ) -> Dict[str, List[Dict]]:
        """
        获取热门带单员列表
        
        Args:
            exchange: 交易所类型 ('okx', 'binance', 'all')
            fetch_all: 是否获取所有页面的数据（默认True，但实际最多获取max_pages页）
            use_cache: 是否使用缓存（默认True）
            **kwargs: 其他参数，传递给对应的采集器
            
        Returns:
            字典格式：{'okx': [...], 'binance': [...]}
        """
        # 如果使用缓存，尝试从缓存获取
        if use_cache:
            cached_data = self.cache.get(exchange, **kwargs)
            if cached_data is not None:
                logger.info(f"[热门带单员服务] 使用缓存数据: {exchange}, 数据量: {sum(len(traders) for traders in cached_data.values())}")
                return cached_data
        
        # 限制获取的页数（如果fetch_all为True，但实际只获取前max_pages页）
        if fetch_all:
            # 设置最大页数限制
            if 'okx' in exchange or exchange == 'all':
                # OKX: size=9, 4页 = 36个
                kwargs['max_pages'] = self.max_pages
            if 'binance' in exchange or exchange == 'all':
                # Binance: page_size=18, 4页 = 72个
                kwargs['max_pages'] = self.max_pages
        
        result = {}
        
        # 确保 aiohttp.ClientSession 在正确的事件循环中创建
        import asyncio
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = asyncio.get_event_loop()
        
        # 创建 ClientSession 时显式指定 timeout
        # 注意：在 Python 3.10+ 中，loop 参数已弃用，不再使用
        timeout = aiohttp.ClientTimeout(total=30, connect=10)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            if exchange in ['okx', 'all']:
                try:
                    okx_params = {
                        'size': kwargs.get('size', 9),
                        'start': kwargs.get('start', 1),
                        'latest_num': kwargs.get('latest_num', 90),
                        'full_state': kwargs.get('full_state', 1),
                        'country_id': kwargs.get('country_id', 'CN'),
                        'api_trader': kwargs.get('api_trader', 0),
                        'inst_num_limit': kwargs.get('inst_num_limit', 4),
                        'data_type': kwargs.get('okx_data_type', kwargs.get('data_type', '')),  # OKX type 参数（严格区分大小写，使用驼峰命名）：空字符串=综合排序, yieldRatio=收益率, pnl=收益额/总盈亏, traderFollowerLimit=跟单人数, winRatio=胜率
                        'fetch_all': fetch_all,
                        'max_pages': kwargs.get('max_pages', self.max_pages) if fetch_all else None
                    }
                    
                    raw_traders = await self.okx_collector.get_popular_traders_async(
                        session, **okx_params
                    )
                    
                    # 标准化数据
                    normalized_traders = []
                    for trader in raw_traders:
                        normalized = self.okx_collector.normalize_popular_trader(trader, is_public=None)
                        if normalized:
                            normalized_traders.append(normalized)
                    
                    # 批量检测公开/私域（异步并发，带间隔控制）
                    if self.check_public_enabled and normalized_traders:
                        try:
                            logger.info(f"[OKX热门] 开始批量检测 {len(normalized_traders)} 个带单员的公开/私域状态...")
                            await self._batch_check_public_status(session, normalized_traders, 'okx')
                        except (RuntimeError, ValueError) as e:
                            error_msg = str(e).lower()
                            if 'attached to a different loop' in error_msg or 'event loop is closed' in error_msg:
                                logger.warning(f"[OKX热门] 事件循环错误，跳过公开/私域检测: {e}")
                                # 将所有带单员标记为未检测
                                for trader in normalized_traders:
                                    trader['is_public'] = None
                            else:
                                raise
                    
                    result['okx'] = normalized_traders
                    logger.info(f"获取到 {len(normalized_traders)} 个OKX热门带单员")
                    
                except Exception as e:
                    logger.error(f"获取OKX热门带单员失败: {e}")
                    result['okx'] = []
            
            if exchange in ['binance', 'all']:
                try:
                    # Binance 默认排序：如果没有指定 data_type 或为空，使用 AUM 作为默认排序
                    binance_data_type = kwargs.get('binance_data_type', kwargs.get('data_type', ''))
                    if not binance_data_type:
                        # 综合排序时，Binance 没有此选项，使用 AUM 作为默认排序
                        # 但 API 仍需要 dataType 参数，我们使用 'PNL'，然后在客户端按 AUM 排序
                        binance_data_type = 'PNL'
                    
                    binance_params = {
                        'page_number': kwargs.get('page_number', 1),
                        'page_size': kwargs.get('page_size', 18),
                        'time_range': kwargs.get('time_range', '30D'),
                        'data_type': binance_data_type,  # Binance data_type 参数（严格区分大小写，使用大写）：PNL=总盈亏, ROI=收益率, COPY_COUNT=跟单人数, SHARP_RATIO=夏普比率（可当作胜率，但要注明）, 空字符串=综合排序（使用AUM）
                        'favorite_only': kwargs.get('favorite_only', False),
                        'hide_full': kwargs.get('hide_full', False),
                        'nickname': kwargs.get('nickname', ''),
                        'order': kwargs.get('order', 'DESC'),
                        'user_asset': kwargs.get('user_asset', 0),
                        'portfolio_type': kwargs.get('portfolio_type', 'ALL'),
                        'use_ai_recommended': kwargs.get('use_ai_recommended', True),
                        'fetch_all': fetch_all,
                        'max_pages': kwargs.get('max_pages', self.max_pages) if fetch_all else None
                    }
                    
                    raw_traders = await self.binance_collector.get_popular_traders_async(
                        session, **binance_params
                    )
                    
                    # 标准化数据
                    normalized_traders = []
                    for trader in raw_traders:
                        normalized = self.binance_collector.normalize_popular_trader(trader, is_public=None)
                        if normalized:
                            normalized_traders.append(normalized)
                    
                    # 批量检测公开/私域（异步并发，带间隔控制）
                    if self.check_public_enabled and normalized_traders:
                        try:
                            logger.info(f"[Binance热门] 开始批量检测 {len(normalized_traders)} 个带单员的公开/私域状态...")
                            await self._batch_check_public_status(session, normalized_traders, 'binance')
                        except (RuntimeError, ValueError) as e:
                            error_msg = str(e).lower()
                            if 'attached to a different loop' in error_msg or 'event loop is closed' in error_msg:
                                logger.warning(f"[Binance热门] 事件循环错误，跳过公开/私域检测: {e}")
                                # 将所有带单员标记为未检测
                                for trader in normalized_traders:
                                    trader['is_public'] = None
                            else:
                                raise
                    
                    result['binance'] = normalized_traders
                    logger.info(f"获取到 {len(normalized_traders)} 个Binance热门带单员")
                    
                except Exception as e:
                    logger.error(f"获取Binance热门带单员失败: {e}")
                    result['binance'] = []
        
        # 如果使用缓存，将结果缓存起来
        if use_cache:
            self.cache.set(exchange, result, **kwargs)
        
        return result
    
    async def get_merged_popular_traders(
        self,
        exchange: str = 'all',
        limit: Optional[int] = None,
        sort_by: str = 'yield_ratio',
        fetch_all: bool = True,
        use_cache: bool = True,
        **kwargs
    ) -> List[Dict]:
        """
        获取合并后的热门带单员列表（按指定字段排序）
        
        Args:
            exchange: 交易所类型
            limit: 限制返回数量
            sort_by: 排序字段（yield_ratio, win_ratio, follower_num等）
            fetch_all: 是否获取所有页面（默认True，但实际最多获取max_pages页）
            use_cache: 是否使用缓存（默认True）
            **kwargs: 其他参数
            
        Returns:
            合并并排序后的带单员列表
        """
        traders_dict = await self.get_popular_traders(exchange, fetch_all=fetch_all, use_cache=use_cache, **kwargs)
        
        # 合并所有交易所的带单员
        all_traders = []
        for exchange_type, traders in traders_dict.items():
            all_traders.extend(traders)
        
        # 排序逻辑
        # 检查是否已经通过 API 端排序
        okx_data_type = kwargs.get('okx_data_type', kwargs.get('data_type', ''))
        binance_data_type = kwargs.get('binance_data_type', kwargs.get('data_type', ''))
        
        # 判断是否需要客户端排序
        # 1. 如果只选择一个交易所，且该交易所已经通过 API 排序，则保持 API 排序
        # 2. 如果选择多个交易所（all），需要合并后统一排序
        # 3. 如果 API 排序类型与 sort_by 不匹配，需要客户端排序
        
        need_client_sort = False
        
        if exchange == 'all':
            # 多交易所合并，需要统一排序
            need_client_sort = True
        elif exchange == 'okx':
            # 只选择 OKX，检查 API 排序是否匹配
            if sort_by == 'yield_ratio' and okx_data_type == 'yieldRatio':
                # API 已按收益率排序，保持排序
                need_client_sort = False
            elif sort_by == 'pnl' and okx_data_type == 'pnl':
                # API 已按收益额排序，保持排序
                need_client_sort = False
            elif sort_by == 'follower_num' and okx_data_type == 'traderFollowerLimit':
                # API 已按跟单人数排序，保持排序
                need_client_sort = False
            elif sort_by == 'win_ratio' and okx_data_type == 'winRatio':
                # API 已按胜率排序，保持排序
                need_client_sort = False
            elif (sort_by == 'comprehensive' or sort_by == '') and okx_data_type == '':
                # API 已按综合排序，保持排序
                need_client_sort = False
            else:
                # API 排序类型不匹配，需要客户端排序
                need_client_sort = True
        elif exchange == 'binance':
            # 只选择 Binance，检查 API 排序是否匹配
            if sort_by == 'yield_ratio' and binance_data_type == 'ROI':
                # API 已按收益率排序，保持排序
                need_client_sort = False
            elif sort_by == 'pnl' and binance_data_type == 'PNL':
                # API 已按总盈亏排序，保持排序
                need_client_sort = False
            elif sort_by == 'follower_num' and binance_data_type == 'COPY_COUNT':
                # API 已按跟单人数排序，保持排序
                need_client_sort = False
            elif sort_by == 'win_ratio' and binance_data_type == 'SHARP_RATIO':
                # API 已按夏普比率排序（当作胜率），保持排序
                need_client_sort = False
            elif (sort_by == 'comprehensive' or sort_by == '' or sort_by == 'aum') and binance_data_type == '':
                # API 已按综合排序（AUM），保持排序
                need_client_sort = False
            else:
                # API 排序类型不匹配，需要客户端排序
                need_client_sort = True
        
        # 如果需要客户端排序，执行排序
        if need_client_sort:
            if sort_by == 'comprehensive' or sort_by == '':
                # 综合排序：按 AUM 降序排序
                reverse = True
                try:
                    all_traders.sort(key=lambda x: float(x.get('aum', 0) or 0), reverse=reverse)
                except Exception as e:
                    logger.warning(f"综合排序失败: {e}, 使用默认顺序")
            elif sort_by == 'yield_ratio':
                # 收益率排序：按 yield_ratio 降序排序
                reverse = True
                try:
                    all_traders.sort(key=lambda x: float(x.get('yield_ratio', 0) or 0), reverse=reverse)
                except Exception as e:
                    logger.warning(f"收益率排序失败: {e}, 使用默认顺序")
            else:
                # 其他排序字段
                reverse = sort_by in ['win_ratio', 'follower_num', 'pnl', 'aum']
                try:
                    all_traders.sort(key=lambda x: float(x.get(sort_by, 0) or 0), reverse=reverse)
                except Exception as e:
                    logger.warning(f"排序失败: {e}, 使用默认顺序")
        else:
            # 保持 API 排序，但记录日志
            logger.debug(f"保持 API 排序，exchange={exchange}, sort_by={sort_by}, okx_data_type={okx_data_type}, binance_data_type={binance_data_type}")
        
        # 限制数量
        if limit and limit > 0:
            all_traders = all_traders[:limit]
        
        return all_traders
    
    async def _batch_check_public_status(
        self,
        session: aiohttp.ClientSession,
        traders: List[Dict],
        exchange: str
    ):
        """
        批量检测带单员的公开/私域状态（异步并发，带间隔控制）
        
        Args:
            session: aiohttp会话对象
            traders: 带单员列表
            exchange: 交易所类型（'okx' 或 'binance'）
        """
        if not traders:
            return
        
        import asyncio
        import time
        
        # 使用信号量控制并发数量（自动使用当前事件循环）
        semaphore = asyncio.Semaphore(self.check_public_concurrent)
        # 使用锁保护共享的时间戳（自动使用当前事件循环）
        time_lock = asyncio.Lock()
        last_request_time = [0]  # 使用列表以便在闭包中修改
        
        async def check_single_trader(trader: Dict, index: int):
            """检测单个带单员的公开/私域状态"""
            try:
                async with semaphore:
                    try:
                        # 控制请求间隔，避免过于频繁（使用锁保护共享时间戳）
                        async with time_lock:
                            current_time = time.time()
                            time_since_last = current_time - last_request_time[0]
                            if time_since_last < self.check_public_interval:
                                sleep_time = self.check_public_interval - time_since_last
                                last_request_time[0] = current_time + sleep_time
                            else:
                                sleep_time = 0
                                last_request_time[0] = current_time
                        
                        # 在锁外执行sleep，避免阻塞其他任务
                        if sleep_time > 0:
                            await asyncio.sleep(sleep_time)
                        
                        # 检查 session 是否仍然有效
                        if session.closed:
                            logger.debug(f"[{exchange}公开检测] {trader.get('unique_name', 'unknown')}: Session已关闭，跳过检测")
                            trader['is_public'] = False
                            return
                        
                        # 执行检测
                        if exchange == 'okx':
                            unique_name = trader.get('unique_name', '')
                            if unique_name:
                                is_public = await self.okx_collector.check_trader_public(session, unique_name)
                                trader['is_public'] = is_public
                        elif exchange == 'binance':
                            portfolio_id = trader.get('portfolio_id') or trader.get('unique_name', '')
                            if portfolio_id:
                                is_public = await self.binance_collector.check_trader_public(session, portfolio_id)
                                trader['is_public'] = is_public
                    except (RuntimeError, ValueError) as e:
                        error_msg = str(e).lower()
                        # 捕获事件循环相关的错误
                        if 'attached to a different loop' in error_msg or 'event loop is closed' in error_msg or 'no running event loop' in error_msg or 'timeout should be used inside a task' in error_msg:
                            logger.debug(f"[{exchange}公开检测] {trader.get('unique_name', 'unknown')}: 事件循环错误，跳过检测: {e}")
                            trader['is_public'] = False
                        else:
                            raise
            except Exception as e:
                error_msg = str(e).lower()
                # 只记录非事件循环相关的错误
                if 'attached to a different loop' not in error_msg and 'event loop is closed' not in error_msg:
                    logger.warning(f"[{exchange}公开检测] {trader.get('unique_name', 'unknown')}: 检测失败: {e}，默认判断为私域")
                trader['is_public'] = False
        
        # 创建所有检测任务（带索引，用于日志）
        tasks = [
            check_single_trader(trader, index)
            for index, trader in enumerate(traders)
        ]
        
        # 并发执行所有检测任务（使用 return_exceptions=True 确保所有任务都能完成）
        try:
            results = await asyncio.gather(*tasks, return_exceptions=True)
            # 检查是否有异常（除了我们已经处理的）
            for i, result in enumerate(results):
                if isinstance(result, Exception):
                    error_msg = str(result).lower()
                    if 'attached to a different loop' not in error_msg and 'event loop is closed' not in error_msg:
                        logger.warning(f"[{exchange}公开检测] 任务 {i} 出现未处理的异常: {result}")
        except Exception as e:
            logger.error(f"[{exchange}公开检测] 批量检测过程中出现错误: {e}")
            import traceback
            logger.error(traceback.format_exc())
        
        # 统计结果
        public_count = sum(1 for trader in traders if trader.get('is_public') is True)
        private_count = sum(1 for trader in traders if trader.get('is_public') is False)
        unknown_count = sum(1 for trader in traders if trader.get('is_public') is None)
        
        logger.info(
            f"[{exchange}公开检测] 检测完成 - "
            f"公开: {public_count}, 私域: {private_count}, 未知: {unknown_count}, "
            f"总计: {len(traders)}"
        )

