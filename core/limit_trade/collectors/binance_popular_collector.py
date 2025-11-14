#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Binance热门带单员采集器
"""

import aiohttp
import asyncio
import random
from typing import Dict, List, Optional, Any
from utils.logger import logger


class BinancePopularTraderCollector:
    """Binance热门带单员采集器"""
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        初始化Binance热门带单员采集器
        
        Args:
            config: 配置字典，可包含：
                - api_base_url: API基础URL
                - timeout: 请求超时时间（秒，默认：10）
        """
        self.config = config or {}
        self.api_base_url = self.config.get(
            'api_base_url',
            'https://www.binance.com/bapi/futures/v1/friendly/future/copy-trade/home-page/query-list'
        )
        self.timeout = self.config.get('timeout', 10)
    
    async def get_popular_traders_async(
        self,
        session: aiohttp.ClientSession,
        page_number: int = 1,
        page_size: int = 18,
        time_range: str = '30D',
        data_type: str = 'PNL',  # 排序类型（data_type 参数，严格区分大小写，使用大写）：PNL=总盈亏, ROI=收益率, COPY_COUNT=跟单人数, SHARP_RATIO=夏普比率（可当作胜率，但要注明）, 空字符串或None=综合排序（使用AUM）
        favorite_only: bool = False,
        hide_full: bool = False,
        nickname: str = '',
        order: str = 'DESC',
        user_asset: int = 0,
        portfolio_type: str = 'ALL',
        use_ai_recommended: bool = True,
        fetch_all: bool = False,
        max_pages: Optional[int] = None
    ) -> List[Dict]:
        """
        异步获取Binance热门带单员列表
        
        Args:
            session: aiohttp会话对象
            page_number: 页码
            page_size: 每页数量
            time_range: 时间范围（7D, 30D, 90D, ALL）
            data_type: 排序类型（data_type 参数，严格区分大小写，使用大写）：PNL=总盈亏, ROI=收益率, COPY_COUNT=跟单人数, SHARP_RATIO=夏普比率（可当作胜率，但要注明）, 空字符串或None=综合排序（使用AUM作为默认排序）
            favorite_only: 是否只显示收藏的
            hide_full: 是否隐藏已满员的
            nickname: 昵称搜索
            order: 排序方式（DESC=降序, ASC=升序）
            user_asset: 用户资产过滤
            portfolio_type: 组合类型（ALL=全部）
            use_ai_recommended: 是否使用AI推荐
            
        Returns:
            热门带单员列表
        """
        payload = {
            "pageNumber": page_number,
            "pageSize": page_size,
            "timeRange": time_range,
            "dataType": data_type,
            "favoriteOnly": favorite_only,
            "hideFull": hide_full,
            "nickname": nickname,
            "order": order,
            "userAsset": user_asset,
            "portfolioType": portfolio_type,
            "useAiRecommended": use_ai_recommended
        }
        
        headers = {
            'Content-Type': 'application/json',
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        
        all_traders = []
        current_page = page_number
        total_count = 0
        
        try:
            while True:
                # 如果 data_type 为空或 None，Binance 没有综合排序，使用 AUM 作为默认排序
                # 但 API 仍然需要 dataType 参数，我们使用 'PNL' 作为默认值，然后在客户端按 AUM 排序
                api_data_type = data_type if data_type else 'PNL'
                
                payload = {
                    "pageNumber": current_page,
                    "pageSize": page_size,
                    "timeRange": time_range,
                    "dataType": api_data_type,  # API 需要此参数，但如果是综合排序，我们会在客户端按 AUM 排序
                    "favoriteOnly": favorite_only,
                    "hideFull": hide_full,
                    "nickname": nickname,
                    "order": order,
                    "userAsset": user_asset,
                    "portfolioType": portfolio_type,
                    "useAiRecommended": use_ai_recommended
                }
                
                timeout = aiohttp.ClientTimeout(total=self.timeout)
                async with session.post(
                    self.api_base_url,
                    headers=headers,
                    json=payload,
                    timeout=timeout
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        
                        # Binance API响应格式：{"code": "000000", "data": {"list": [...], "total": 386, ...}}
                        if data.get("code") == "000000" or data.get("success") is not False:
                            data_obj = data.get("data", {})
                            traders = data_obj.get("list", [])
                            total = data_obj.get("total", 0)
                            
                            if total_count == 0:
                                total_count = total
                            
                            if traders:
                                all_traders.extend(traders)
                                logger.info(f"[Binance热门] 第 {current_page} 页获取到 {len(traders)} 个热门带单员，总数: {total}")
                            
                            # 检查最大页数限制（优先检查）
                            if max_pages and current_page >= max_pages:
                                logger.info(f"[Binance热门] 已达到最大页数限制: {max_pages}页，停止获取")
                                break
                            
                            # 如果不需要获取所有页面，或者已经获取完所有数据，则退出
                            if not fetch_all or not traders or len(all_traders) >= total_count:
                                break
                            
                            # 添加请求延迟，避免频率过高（1-3秒随机延迟）
                            await asyncio.sleep(random.uniform(1.0, 3.0))
                            current_page += 1
                        else:
                            logger.error(f"[Binance热门] 获取热门带单员失败: {data.get('message', '未知错误')}")
                            break
                    else:
                        error_text = await response.text()
                        logger.error(f"[Binance热门] 请求失败，状态码: {response.status}, 错误: {error_text}")
                        break
                        
        except Exception as e:
            logger.error(f"[Binance热门] 异步请求失败: {e}")
        
        logger.info(f"[Binance热门] 总共获取到 {len(all_traders)} 个热门带单员")
        return all_traders
    
    def normalize_popular_trader(self, raw_trader: Dict) -> Dict:
        """
        将Binance原始热门带单员数据标准化
        
        Args:
            raw_trader: Binance原始数据
            
        Returns:
            标准化的带单员信息
        """
        try:
            # Binance的数据结构可能不同，需要根据实际API响应调整
            return {
                'portfolio_id': str(raw_trader.get('portfolioId') or raw_trader.get('id') or ''),
                'unique_name': str(raw_trader.get('portfolioId') or raw_trader.get('id') or ''),  # 使用portfolioId作为unique_name
                'nick_name': raw_trader.get('nickname') or raw_trader.get('nickName') or '',
                'portrait': raw_trader.get('avatarUrl') or raw_trader.get('avatar') or raw_trader.get('portrait') or '',
                'aum': float(raw_trader.get('aum') or raw_trader.get('totalAsset') or 0),  # 管理资产（优先使用aum）
                'pnl': float(raw_trader.get('pnl') or raw_trader.get('totalPnl') or 0),  # 总盈亏（优先使用pnl）
                'follow_pnl': float(raw_trader.get('followerPnl') or raw_trader.get('followPnl') or 0),  # 跟单盈亏
                'yield_ratio': float(raw_trader.get('roi') or raw_trader.get('ROI') or raw_trader.get('yieldRatio') or 0),  # 收益率（优先使用roi）
                'win_ratio': float(raw_trader.get('winRate') or raw_trader.get('winRatio') or 0),  # 胜率（优先使用winRate）
                'follower_num': int(raw_trader.get('currentCopyCount') or raw_trader.get('COPY_COUNT') or raw_trader.get('followerCount') or raw_trader.get('followerNum') or 0),  # 当前跟单人数（优先使用currentCopyCount）
                'follower_limit': int(raw_trader.get('maxCopyCount') or raw_trader.get('followerLimit') or raw_trader.get('maxFollowers') or 0),  # 跟单人数限制（优先使用maxCopyCount）
                'history_follower_num': int(raw_trader.get('totalFollowers') or raw_trader.get('historyFollowerNum') or 0),  # 历史跟单人数
                'initial_day': int(raw_trader.get('tradingDays') or raw_trader.get('initialDay') or 0),  # 交易天数
                'lever': float(raw_trader.get('leverage') or raw_trader.get('lever') or 0) if raw_trader.get('leverage') or raw_trader.get('lever') else 0,  # 杠杆
                'sharp_ratio': float(raw_trader.get('sharpRatio') or raw_trader.get('SHARP_RATIO') or 0),  # 夏普比率
                'mdd': float(raw_trader.get('mdd') or 0),  # 最大回撤
                'instruments': raw_trader.get('instruments') or raw_trader.get('symbols') or [],  # 交易对列表
                'tier': raw_trader.get('tier') or raw_trader.get('level') or {},  # 等级信息
                'full_status': raw_trader.get('isFull') or raw_trader.get('fullStatus') or False,  # 是否已满员
                'source': 'binance'  # 数据来源
            }
        except Exception as e:
            logger.error(f"[Binance热门] 标准化带单员数据失败: {e}, 原始数据: {raw_trader}")
            return {}

