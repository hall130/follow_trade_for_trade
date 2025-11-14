#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Echosync.io API 数据采集器
用于获取 Hyperliquid 排行榜、巨鲸订单、巨鲸资金转移等数据
"""

import aiohttp
import time
from typing import Dict, List, Optional
from utils.logger import logger


class EchosyncCollector:
    """Echosync.io 数据采集器"""
    
    def __init__(self, config: Optional[Dict] = None):
        """
        初始化 Echosync 采集器
        
        Args:
            config: 配置字典
        """
        self.config = config or {}
        self.base_url = self.config.get('base_url', 'https://echosync.io/api/v1')
        self.timeout = self.config.get('timeout', 30)
    
    async def get_leaderboard(
        self,
        session: aiohttp.ClientSession,
        sort_by: str = 'total_pnl',
        period_days: int = 30,
        page: int = 1,
        page_size: int = 100
    ) -> Dict:
        """
        获取排行榜数据
        
        Args:
            session: aiohttp 会话
            sort_by: 排序字段
                - 'total_pnl': 总盈亏
                - 'avg_win_rate': 平均胜率
                - 'total_winning_trades': 总胜利次数
                - 'updated_at': 最新操作时间
            period_days: 统计周期（天）
            page: 页码
            page_size: 每页数量
            
        Returns:
            {
                'success': bool,
                'message': str,
                'data': List[Dict],
                'pagination': {
                    'page': int,
                    'page_size': int,
                    'total': int,
                    'total_pages': int
                }
            }
        """
        try:
            url = f"{self.base_url}/period-stats"
            params = {
                'page': page,
                'pageSize': page_size,
                'period_days': period_days,
                'sort_by': sort_by,
                'order': 'desc'
            }
            
            timeout = aiohttp.ClientTimeout(total=self.timeout)
            async with session.get(url, params=params, timeout=timeout) as response:
                if response.status == 200:
                    data = await response.json()
                    logger.info(
                        f"[Echosync排行榜] 获取成功，排序={sort_by}, "
                        f"数据量={len(data.get('data', []))}"
                    )
                    return data
                else:
                    error_text = await response.text()
                    logger.error(f"[Echosync排行榜] 请求失败，状态码={response.status}, 错误={error_text}")
                    return {'success': False, 'message': error_text, 'data': []}
                    
        except Exception as e:
            logger.error(f"[Echosync排行榜] 异常: {e}")
            return {'success': False, 'message': str(e), 'data': []}
    
    async def get_whale_orders(
        self,
        session: aiohttp.ClientSession,
        min_trade_amount: float = 100000,
        start_date: Optional[int] = None,
        end_date: Optional[int] = None,
        page: int = 1,
        page_size: int = 100,
        trade_type: str = 'perpetual',
        sort_by: str = 'time'
    ) -> Dict:
        """
        获取巨鲸订单数据
        
        Args:
            session: aiohttp 会话
            min_trade_amount: 最小交易金额
            start_date: 开始时间（毫秒时间戳）
            end_date: 结束时间（毫秒时间戳）
            page: 页码
            page_size: 每页数量
            trade_type: 交易类型（perpetual/spot）
            sort_by: 排序字段
            
        Returns:
            {
                'success': bool,
                'data': List[Dict],
                'pagination': {...}
            }
        """
        try:
            # 如果没有指定时间范围，使用最近24小时
            if end_date is None:
                end_date = int(time.time() * 1000)
            if start_date is None:
                start_date = end_date - (24 * 60 * 60 * 1000)
            
            url = f"{self.base_url}/node-fills/"
            params = {
                'page': page,
                'page_size': page_size,
                'min_trade_amount': min_trade_amount,
                'start_date': start_date,
                'end_date': end_date,
                'sort_by': sort_by,
                'trade_type': trade_type,
                'sort_order': 'desc'
            }
            
            timeout = aiohttp.ClientTimeout(total=self.timeout)
            async with session.get(url, params=params, timeout=timeout) as response:
                if response.status == 200:
                    data = await response.json()
                    logger.info(
                        f"[Echosync巨鲸订单] 获取成功，最小金额={min_trade_amount}, "
                        f"数据量={len(data.get('data', []))}"
                    )
                    return data
                else:
                    error_text = await response.text()
                    logger.error(f"[Echosync巨鲸订单] 请求失败，状态码={response.status}")
                    return {'success': False, 'message': error_text, 'data': []}
                    
        except Exception as e:
            logger.error(f"[Echosync巨鲸订单] 异常: {e}")
            return {'success': False, 'message': str(e), 'data': []}
    
    async def get_whale_moves(
        self,
        session: aiohttp.ClientSession,
        min_amount: float = 10000,
        max_amount: float = 99999999999,
        start_date: Optional[int] = None,
        end_date: Optional[int] = None,
        page: int = 1,
        page_size: int = 20,
        sort_by: str = 'event_time'
    ) -> Dict:
        """
        获取巨鲸资金转移数据
        
        Args:
            session: aiohttp 会话
            min_amount: 最小金额
            max_amount: 最大金额
            start_date: 开始时间（秒时间戳）
            end_date: 结束时间（秒时间戳）
            page: 页码
            page_size: 每页数量
            sort_by: 排序字段
            
        Returns:
            {
                'success': bool,
                'data': List[Dict],
                'pagination': {...}
            }
        """
        try:
            url = f"{self.base_url}/deposits/"
            params = {
                'page': page,
                'page_size': page_size,
                'min_amount': min_amount,
                'max_amount': max_amount,
                'sort_by': sort_by,
                'sort_order': 'desc'
            }
            
            # 只在提供了时间范围时才添加时间参数
            # 根据 Echosync API 文档，deposits 接口的时间参数是可选的
            if start_date is not None:
                params['start_date'] = start_date
            if end_date is not None:
                params['end_date'] = end_date
            
            timeout = aiohttp.ClientTimeout(total=self.timeout)
            async with session.get(url, params=params, timeout=timeout) as response:
                if response.status == 200:
                    data = await response.json()
                    logger.info(
                        f"[Echosync巨鲸转移] 获取成功，最小金额={min_amount}, "
                        f"数据量={len(data.get('data', []))}"
                    )
                    return data
                else:
                    error_text = await response.text()
                    logger.error(f"[Echosync巨鲸转移] 请求失败，状态码={response.status}")
                    return {'success': False, 'message': error_text, 'data': []}
                    
        except Exception as e:
            logger.error(f"[Echosync巨鲸转移] 异常: {e}")
            return {'success': False, 'message': str(e), 'data': []}
    
    async def get_user_portfolio(
        self,
        session: aiohttp.ClientSession,
        user_address: str
    ) -> Dict:
        """
        获取用户详细信息（通过 Hyperliquid API）
        
        Args:
            session: aiohttp 会话
            user_address: 用户地址（0x...）
            
        Returns:
            用户详细信息
        """
        try:
            url = "https://api.hyperliquid.xyz/info"
            payload = {
                "type": "clearinghouseState",
                "user": user_address
            }
            
            timeout = aiohttp.ClientTimeout(total=self.timeout)
            async with session.post(
                url,
                json=payload,
                timeout=timeout,
                headers={'Content-Type': 'application/json'}
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    
                    logger.info(
                        f"[Hyperliquid Portfolio] 原始数据: 类型={type(data).__name__}, "
                        f"长度={len(data) if isinstance(data, (list, dict)) else 'N/A'}"
                    )
                    
                    # Hyperliquid API 返回的数据可能是数组或对象
                    # 根据 Hyperliquid API 文档，portfolio 类型返回的是列表，包含多个账户
                    # 通常第一个是主账户，但我们需要找到包含 marginSummary 的账户
                    portfolio_data = None
                    
                    if isinstance(data, list):
                        # 如果是列表，需要处理嵌套列表的情况
                        # Hyperliquid API 可能返回 [[marginSummary, assetPositions, ...], ...]
                        # 或者 [{marginSummary: {...}, assetPositions: [...]}, ...]
                        
                        # 首先尝试查找字典格式的元素
                        for item in data:
                            if isinstance(item, dict) and 'marginSummary' in item:
                                portfolio_data = item
                                break
                        
                        # 如果没找到字典，可能是嵌套列表格式
                        # 根据 Hyperliquid API 文档，portfolio 返回格式是：
                        # [marginSummary, assetPositions, ...]
                        if portfolio_data is None and len(data) > 0:
                            first_item = data[0]
                            
                            # 如果第一个元素是列表，说明是嵌套列表格式
                            if isinstance(first_item, list):
                                # 尝试从嵌套列表中提取数据
                                # 通常格式是: [marginSummary, assetPositions, ...]
                                portfolio_data = {}
                                for idx, item in enumerate(data):
                                    if isinstance(item, list) and len(item) > 0:
                                        # 第一个列表通常是 marginSummary
                                        if idx == 0 and isinstance(item[0], dict):
                                            portfolio_data['marginSummary'] = item[0]
                                        # 第二个列表通常是 assetPositions
                                        elif idx == 1 and isinstance(item, list):
                                            portfolio_data['assetPositions'] = item
                                    elif isinstance(item, dict):
                                        # 如果直接是字典，合并到 portfolio_data
                                        portfolio_data.update(item)
                                
                                logger.info(
                                    f"[Hyperliquid Portfolio] 检测到嵌套列表格式，"
                                    f"已提取 marginSummary: {'marginSummary' in portfolio_data}, "
                                    f"assetPositions: {'assetPositions' in portfolio_data}"
                                )
                            elif isinstance(first_item, dict):
                                # 如果第一个元素是字典，直接使用
                                portfolio_data = first_item
                            else:
                                # 其他情况，尝试构建字典
                                portfolio_data = {}
                                for idx, item in enumerate(data):
                                    if isinstance(item, dict):
                                        portfolio_data.update(item)
                                    elif isinstance(item, (str, int, float)):
                                        # 可能是 withdrawable 等简单值
                                        if idx == 2:  # 通常第三个是 withdrawable
                                            portfolio_data['withdrawable'] = str(item)
                                
                                logger.warning(
                                    f"[Hyperliquid Portfolio] 列表格式未知，尝试解析，"
                                    f"结果字段: {list(portfolio_data.keys())}"
                                )
                    elif isinstance(data, dict):
                        # 如果是字典，检查是否有嵌套的 data 字段
                        if 'data' in data:
                            portfolio_data = data['data']
                        elif 'marginSummary' in data:
                            portfolio_data = data
                        else:
                            # 如果都没有，直接使用
                            portfolio_data = data
                    else:
                        portfolio_data = data
                    
                    logger.info(
                        f"[Hyperliquid Portfolio] 获取用户 {user_address[:10]}... 成功, "
                        f"数据结构: {type(portfolio_data).__name__}"
                    )
                    
                    # 记录调试信息
                    if isinstance(portfolio_data, dict):
                        keys = list(portfolio_data.keys())
                        logger.debug(
                            f"[Hyperliquid Portfolio] 数据字段: {keys}"
                        )
                        # 检查关键字段
                        if 'marginSummary' in portfolio_data:
                            logger.debug(
                                f"[Hyperliquid Portfolio] marginSummary 存在: {type(portfolio_data['marginSummary'])}"
                            )
                        if 'assetPositions' in portfolio_data:
                            logger.debug(
                                f"[Hyperliquid Portfolio] assetPositions 存在: {type(portfolio_data['assetPositions'])}, "
                                f"长度={len(portfolio_data['assetPositions']) if isinstance(portfolio_data['assetPositions'], list) else 'N/A'}"
                            )
                    else:
                        logger.warning(
                            f"[Hyperliquid Portfolio] portfolio_data 不是字典类型: {type(portfolio_data)}"
                        )
                    
                    return {'success': True, 'data': portfolio_data}
                else:
                    error_text = await response.text()
                    logger.error(
                        f"[Hyperliquid Portfolio] 请求失败，状态码={response.status}, "
                        f"错误: {error_text}"
                    )
                    return {'success': False, 'message': error_text, 'data': None}
                    
        except Exception as e:
            logger.error(f"[Hyperliquid Portfolio] 异常: {e}")
            return {'success': False, 'message': str(e), 'data': None}

