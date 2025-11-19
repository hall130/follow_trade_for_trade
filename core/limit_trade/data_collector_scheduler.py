#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
数据采集调度器
定时采集热门带单员和巨鲸交易员数据，预热缓存
"""

import asyncio
import time
import threading
from typing import Dict, Optional, Any
from utils.logger import logger
from core.limit_trade.popular_traders_service import PopularTradersService
from core.limit_trade.echosync_service import EchosyncService
from core.limit_trade.popular_traders_cache import get_cache


class DataCollectorScheduler:
    """数据采集调度器（后台定时任务）"""
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        初始化调度器
        
        Args:
            config: 配置字典
                - popular_traders_interval: 热门带单员采集间隔（秒），默认1800（30分钟）
                - whale_traders_interval: 巨鲸交易员采集间隔（秒），默认3600（1小时）
                - enable_popular_traders: 是否启用热门带单员采集，默认True
                - enable_whale_traders: 是否启用巨鲸交易员采集，默认True
                - initial_delay: 初始延迟（秒），默认60（1分钟）
        """
        self.config = config or {}
        self.running = False
        self.thread = None
        
        # 采集间隔配置
        self.popular_traders_interval = self.config.get('popular_traders_interval', 3600)  # 1小时
        self.whale_traders_interval = self.config.get('whale_traders_interval', 3600)  # 1小时
        self.enable_popular_traders = self.config.get('enable_popular_traders', True)
        self.enable_whale_traders = self.config.get('enable_whale_traders', True)
        self.initial_delay = self.config.get('initial_delay', 60)  # 1分钟后开始
        
        # 服务实例
        self.popular_traders_service = PopularTradersService(
            config={
                'cache_ttl': self.popular_traders_interval,  # 缓存时间与采集间隔一致
                'check_public': True,  # 启用公开/私域检测
                'check_public_concurrent': 5,  # 并发检测数量
                'check_public_interval': 0.5  # 检测间隔（秒）
            }
        )
        self.echosync_service = EchosyncService(
            config={'cache_ttl': self.whale_traders_interval}  # 缓存时间与采集间隔一致
        )
        
        # 统计信息
        self.stats = {
            'popular_traders': {
                'last_collect_time': None,
                'last_collect_count': 0,
                'total_collects': 0,
                'errors': 0
            },
            'whale_traders': {
                'last_collect_time': None,
                'last_collect_count': 0,
                'total_collects': 0,
                'errors': 0
            }
        }
        
        logger.info(
            f"[数据采集调度器] 初始化完成 - "
            f"热门带单员间隔: {self.popular_traders_interval}秒（{self.popular_traders_interval//60}分钟）, "
            f"巨鲸交易员间隔: {self.whale_traders_interval}秒（{self.whale_traders_interval//60}分钟）"
        )
    
    def start(self):
        """启动调度器"""
        if self.running:
            logger.warning("[数据采集调度器] 调度器已在运行")
            return
        
        self.running = True
        self.thread = threading.Thread(target=self._run_scheduler, daemon=True)
        self.thread.start()
        logger.info("[数据采集调度器] 调度器已启动")
    
    def stop(self):
        """停止调度器"""
        if not self.running:
            return
        
        self.running = False
        if self.thread:
            self.thread.join(timeout=10)
        logger.info("[数据采集调度器] 调度器已停止")
    
    def _run_scheduler(self):
        """运行调度器（在后台线程中）"""
        # 初始延迟
        time.sleep(self.initial_delay)
        
        # 立即执行一次预热
        logger.info("[数据采集调度器] 开始预热缓存...")
        self._warmup_cache()
        
        # 计算下次采集时间
        last_popular_time = time.time()
        last_whale_time = time.time()
        
        while self.running:
            try:
                current_time = time.time()
                
                # 检查是否需要采集热门带单员
                if self.enable_popular_traders:
                    if current_time - last_popular_time >= self.popular_traders_interval:
                        logger.info("[数据采集调度器] 开始采集热门带单员数据...")
                        self._collect_popular_traders()
                        last_popular_time = current_time
                
                # 检查是否需要采集巨鲸交易员
                if self.enable_whale_traders:
                    if current_time - last_whale_time >= self.whale_traders_interval:
                        logger.info("[数据采集调度器] 开始采集巨鲸交易员数据...")
                        self._collect_whale_traders()
                        last_whale_time = current_time
                
                # 每10秒检查一次
                time.sleep(10)
                
            except Exception as e:
                logger.error(f"[数据采集调度器] 调度器运行异常: {e}")
                import traceback
                logger.error(traceback.format_exc())
                time.sleep(60)  # 出错后等待1分钟再继续
    
    def _warmup_cache(self):
        """预热缓存（采集所有数据）"""
        try:
            # 预热热门带单员
            if self.enable_popular_traders:
                logger.info("[数据采集调度器] 预热热门带单员缓存...")
                self._collect_popular_traders()
            
            # 预热巨鲸交易员
            if self.enable_whale_traders:
                logger.info("[数据采集调度器] 预热巨鲸交易员缓存...")
                self._collect_whale_traders()
            
            logger.info("[数据采集调度器] 缓存预热完成")
        except Exception as e:
            logger.error(f"[数据采集调度器] 缓存预热失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
    
    def _collect_popular_traders(self):
        """采集热门带单员数据"""
        try:
            # 使用 asyncio 运行异步函数
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            try:
                # 采集所有交易所的数据（使用缓存，但会更新缓存）
                result = loop.run_until_complete(
                    self.popular_traders_service.get_popular_traders(
                        exchange='all',
                        fetch_all=True,
                        use_cache=False,  # 不使用缓存，强制采集
                        time_range='30D',
                        order='DESC',
                        country_id='CN'
                    )
                )
                
                # 统计数据量
                total_count = sum(len(traders) for traders in result.values() if isinstance(traders, list))
                
                # 更新统计信息
                self.stats['popular_traders']['last_collect_time'] = time.time()
                self.stats['popular_traders']['last_collect_count'] = total_count
                self.stats['popular_traders']['total_collects'] += 1
                
                logger.info(
                    f"[数据采集调度器] 热门带单员采集完成 - "
                    f"OKX: {len(result.get('okx', []))}, "
                    f"Binance: {len(result.get('binance', []))}, "
                    f"总计: {total_count}"
                )
                
            finally:
                loop.close()
                
        except Exception as e:
            logger.error(f"[数据采集调度器] 热门带单员采集失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
            self.stats['popular_traders']['errors'] += 1
    
    def _collect_whale_traders(self):
        """采集巨鲸交易员数据"""
        try:
            # 使用 asyncio 运行异步函数
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            try:
                # 采集不同排序方式的排行榜数据
                sort_types = ['total_pnl', 'avg_win_rate', 'updated_at']
                period_days_list = [1, 7, 30, 180]  # 不同时间周期
                
                total_count = 0
                for sort_by in sort_types:
                    for period_days in period_days_list:
                        result = loop.run_until_complete(
                            self.echosync_service.get_leaderboard(
                                sort_by=sort_by,
                                period_days=period_days,
                                page_size=100,
                                use_cache=False  # 不使用缓存，强制采集
                            )
                        )
                        
                        if result.get('success') and result.get('data'):
                            total_count += len(result.get('data', []))
                
                # 更新统计信息
                self.stats['whale_traders']['last_collect_time'] = time.time()
                self.stats['whale_traders']['last_collect_count'] = total_count
                self.stats['whale_traders']['total_collects'] += 1
                
                logger.info(
                    f"[数据采集调度器] 巨鲸交易员采集完成 - "
                    f"总计: {total_count} 条记录"
                )
                
            finally:
                loop.close()
                
        except Exception as e:
            logger.error(f"[数据采集调度器] 巨鲸交易员采集失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
            self.stats['whale_traders']['errors'] += 1
    
    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        return {
            'running': self.running,
            'config': {
                'popular_traders_interval': self.popular_traders_interval,
                'whale_traders_interval': self.whale_traders_interval,
                'enable_popular_traders': self.enable_popular_traders,
                'enable_whale_traders': self.enable_whale_traders
            },
            'stats': self.stats.copy()
        }


# 全局调度器实例
_global_scheduler: Optional[DataCollectorScheduler] = None


def get_scheduler(config: Optional[Dict[str, Any]] = None) -> DataCollectorScheduler:
    """
    获取全局调度器实例（单例模式）
    
    Args:
        config: 配置字典
        
    Returns:
        调度器实例
    """
    global _global_scheduler
    if _global_scheduler is None:
        _global_scheduler = DataCollectorScheduler(config)
    return _global_scheduler

