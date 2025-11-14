#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
OKX热门带单员采集器
"""

import aiohttp
import asyncio
import random
from typing import Dict, List, Optional, Any
from utils.logger import logger


class OKXPopularTraderCollector:
    """OKX热门带单员采集器"""
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        初始化OKX热门带单员采集器
        
        Args:
            config: 配置字典，可包含：
                - api_base_url: API基础URL
                - timeout: 请求超时时间（秒，默认：10）
        """
        self.config = config or {}
        self.api_base_url = self.config.get(
            'api_base_url',
            'https://www.okx.com/priapi/v5/ecotrade/public/follow-rank'
        )
        self.timeout = self.config.get('timeout', 10)
    
    async def get_popular_traders_async(
        self,
        session: aiohttp.ClientSession,
        size: int = 9,
        start: int = 1,
        latest_num: int = 90,
        full_state: int = 1,
        country_id: str = 'CN',
        api_trader: int = 0,
        inst_num_limit: int = 4,
        data_type: str = '',  # 排序类型（type 参数，严格区分大小写，使用驼峰命名）：空字符串=综合排序, yieldRatio=收益率, pnl=收益额/总盈亏, traderFollowerLimit=跟单人数, winRatio=胜率
        fetch_all: bool = False,
        max_pages: Optional[int] = None
    ) -> List[Dict]:
        """
        异步获取OKX热门带单员列表
        
        Args:
            session: aiohttp会话对象
            size: 每页数量
            start: 起始页码
            latest_num: 最新数量
            full_state: 是否显示已满员（1=显示，0=隐藏）
            country_id: 国家ID（CN=中国）
            api_trader: API交易员（0=否，1=是）
            inst_num_limit: 交易对数量限制
            data_type: 排序类型（type 参数，严格区分大小写，使用驼峰命名）：空字符串=综合排序, yieldRatio=收益率, pnl=收益额/总盈亏, traderFollowerLimit=跟单人数, winRatio=胜率
            
        Returns:
            热门带单员列表
        """
        params = {
            'size': size,
            'type': data_type,  # 排序类型（空字符串表示综合排序）
            'start': start,
            'latestNum': latest_num,
            'fullState': full_state,
            'countryId': country_id,
            'apiTrader': api_trader,
            'instNumLimit': inst_num_limit
        }
        
        all_ranks = []
        current_start = start
        
        try:
            while True:
                params = {
                    'size': size,
                    'type': data_type,  # 使用传入的 data_type 参数
                    'start': current_start,
                    'latestNum': latest_num,
                    'fullState': full_state,
                    'countryId': country_id,
                    'apiTrader': api_trader,
                    'instNumLimit': inst_num_limit
                }
                
                timeout = aiohttp.ClientTimeout(total=self.timeout)
                async with session.get(
                    self.api_base_url,
                    params=params,
                    timeout=timeout
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        if data.get('code') == '0':
                            # OKX返回格式：{"code":"0","data":[{"dataVersion":"...","pages":25,"ranks":[...]}],"msg":""}
                            data_list = data.get('data', [])
                            if data_list and len(data_list) > 0:
                                ranks = data_list[0].get('ranks', [])
                                total_pages = data_list[0].get('pages', 1)
                                
                                if ranks:
                                    all_ranks.extend(ranks)
                                    logger.info(f"[OKX热门] 第 {current_start} 页获取到 {len(ranks)} 个热门带单员，总页数: {total_pages}")
                                
                                # 检查最大页数限制（优先检查）
                                if max_pages and current_start >= max_pages:
                                    logger.info(f"[OKX热门] 已达到最大页数限制: {max_pages}页，停止获取")
                                    break
                                
                                # 如果不需要获取所有页面，或者已经获取完所有页面，则退出
                                if not fetch_all or current_start >= total_pages or not ranks:
                                    break
                                
                                # 添加请求延迟，避免频率过高（1-3秒随机延迟）
                                await asyncio.sleep(random.uniform(1.0, 3.0))
                                current_start += 1
                            else:
                                break
                        else:
                            logger.error(f"[OKX热门] 获取热门带单员失败: {data.get('msg', '未知错误')}")
                            break
                    else:
                        error_text = await response.text()
                        logger.error(f"[OKX热门] 请求失败，状态码: {response.status}, 错误: {error_text}")
                        break
                    
        except Exception as e:
            logger.error(f"[OKX热门] 异步请求失败: {e}")
        
        logger.info(f"[OKX热门] 总共获取到 {len(all_ranks)} 个热门带单员")
        return all_ranks
    
    def normalize_popular_trader(self, raw_trader: Dict) -> Dict:
        """
        将OKX原始热门带单员数据标准化
        
        Args:
            raw_trader: OKX原始数据
            
        Returns:
            标准化的带单员信息
        """
        try:
            # OKX API 返回的 yieldRatio 是百分比的小数形式（如 5.4629 表示 546.29%）
            # 需要乘以 100 转换为百分比数值
            yield_ratio_raw = raw_trader.get('yieldRatio', 0)
            yield_ratio = float(yield_ratio_raw) * 100 if yield_ratio_raw else 0
            
            return {
                'unique_name': raw_trader.get('uniqueName', ''),
                'nick_name': raw_trader.get('nickName', ''),
                'portrait': raw_trader.get('portrait', ''),
                'aum': float(raw_trader.get('aum', 0)),  # 管理资产
                'pnl': float(raw_trader.get('pnl', 0)),  # 总盈亏
                'follow_pnl': float(raw_trader.get('followPnl', 0)),  # 跟单盈亏
                'yield_ratio': yield_ratio,  # 收益率（已转换为百分比数值，如 546.29）
                'win_ratio': float(raw_trader.get('winRatio', 0)),  # 胜率（已经是小数形式，如 0.5455 表示 54.55%）
                'follower_num': int(raw_trader.get('followerNum', 0)),  # 当前跟单人数
                'follower_limit': int(raw_trader.get('traderFollowerLimit', raw_trader.get('followerLimit', 0))),  # 跟单人数限制（优先使用 traderFollowerLimit）
                'history_follower_num': int(raw_trader.get('historyFollowerNum', 0)),  # 历史跟单人数
                'initial_day': int(raw_trader.get('initialDay', 0)),  # 初始天数
                'lever': float(raw_trader.get('lever', 0)) if raw_trader.get('lever') else 0,  # 杠杆
                'instruments': raw_trader.get('instruments', []),  # 交易对列表
                'tier': raw_trader.get('tier', {}),  # 等级信息
                'full_status': raw_trader.get('fullStatus', False),  # 是否已满员
                'source': 'okx'  # 数据来源
            }
        except Exception as e:
            logger.error(f"[OKX热门] 标准化带单员数据失败: {e}, 原始数据: {raw_trader}")
            return {}

