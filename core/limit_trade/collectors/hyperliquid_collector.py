#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Hyperliquid交易员数据采集器
用于发现和获取Hyperliquid平台上的交易员（Vault）信息
"""

import aiohttp
from typing import Dict, List, Optional, Any
from utils.logger import logger


class HyperliquidTraderCollector:
    """Hyperliquid交易员采集器"""
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        初始化Hyperliquid交易员采集器
        
        Args:
            config: 配置字典，可包含：
                - api_base_url: API基础URL（默认：Hyperliquid公开API）
                - timeout: 请求超时时间（秒，默认：10）
        """
        self.config = config or {}
        self.api_base_url = self.config.get(
            'api_base_url',
            'https://api.hyperliquid.xyz/info'
        )
        self.timeout = self.config.get('timeout', 10)
    
    async def get_traders_async(
        self,
        session: aiohttp.ClientSession,
        limit: int = 50,
        sort_by: str = 'pnl'
    ) -> List[Dict]:
        """
        异步获取Hyperliquid交易员（Vault）列表
        
        Hyperliquid API: POST https://api.hyperliquid.xyz/info
        Request body: {"type": "vaults"}
        
        注意：API不直接支持limit和sort_by参数，需要在客户端处理
        
        Args:
            session: aiohttp会话对象
            limit: 返回数量限制（客户端截取）
            sort_by: 排序方式（pnl, apy等，客户端排序）
            
        Returns:
            交易员列表
        """
        # Hyperliquid API 只支持 type: "vaults"，不直接支持limit和sort_by
        payload = {"type": "vaults"}
        
        try:
            timeout = aiohttp.ClientTimeout(total=self.timeout)
            async with session.post(
                self.api_base_url,
                json=payload,
                timeout=timeout,
                headers={'Content-Type': 'application/json'}
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    
                    # 处理不同的返回格式
                    traders = []
                    if isinstance(data, list):
                        traders = data
                    elif isinstance(data, dict):
                        # 可能返回 {"data": [...]} 或直接是字典
                        if 'data' in data:
                            traders = data['data']
                        else:
                            # 如果整个响应就是数据
                            traders = [data] if data else []
                    
                    # 客户端排序
                    if sort_by == 'pnl':
                        traders.sort(key=lambda x: float(x.get('pnl', 0) or x.get('totalPnl', 0) or 0), reverse=True)
                    elif sort_by == 'apy' or sort_by == 'yield_ratio':
                        traders.sort(key=lambda x: float(x.get('apy', 0) or x.get('yieldRatio', 0) or 0), reverse=True)
                    elif sort_by == 'aum':
                        traders.sort(key=lambda x: float(x.get('aum', 0) or x.get('totalValue', 0) or 0), reverse=True)
                    
                    # 客户端限制数量
                    if limit and len(traders) > limit:
                        traders = traders[:limit]
                    
                    logger.info(f"[Hyperliquid] 获取到 {len(traders)} 个交易员（排序: {sort_by}, 限制: {limit}）")
                    return traders
                else:
                    error_text = await response.text()
                    logger.error(f"[Hyperliquid] 请求失败，状态码: {response.status}, 错误: {error_text}")
                    return []
                    
        except aiohttp.ClientError as e:
            logger.error(f"[Hyperliquid] 网络请求失败: {e}")
            return []
        except Exception as e:
            logger.error(f"[Hyperliquid] 异步请求失败: {e}")
            return []
    
    def normalize_trader(self, raw_trader: Dict) -> Dict:
        """
        将Hyperliquid原始交易员数据标准化
        
        根据Hyperliquid API文档，Vault数据结构可能包含：
        - address: Vault地址
        - name: Vault名称
        - aum: 管理资产总额
        - pnl: 总盈亏
        - apy: 年化收益率
        - 其他字段...
        
        Args:
            raw_trader: Hyperliquid原始数据
            
        Returns:
            标准化的交易员信息
        """
        try:
            # 提取地址作为唯一标识
            address = raw_trader.get('address') or raw_trader.get('vault') or raw_trader.get('id', '')
            
            # 提取AUM（管理资产）
            aum = 0.0
            if 'aum' in raw_trader:
                aum = float(raw_trader['aum'] or 0)
            elif 'totalValue' in raw_trader:
                aum = float(raw_trader['totalValue'] or 0)
            elif 'totalAssets' in raw_trader:
                aum = float(raw_trader['totalAssets'] or 0)
            
            # 提取PNL（总盈亏）
            pnl = 0.0
            if 'pnl' in raw_trader:
                pnl = float(raw_trader['pnl'] or 0)
            elif 'totalPnl' in raw_trader:
                pnl = float(raw_trader['totalPnl'] or 0)
            elif 'unrealizedPnl' in raw_trader:
                pnl = float(raw_trader['unrealizedPnl'] or 0)
            
            # 提取APY（年化收益率），转换为小数
            apy = 0.0
            if 'apy' in raw_trader:
                apy_value = raw_trader['apy']
                if isinstance(apy_value, (int, float)):
                    apy = float(apy_value) / 100 if apy_value > 1 else float(apy_value)
            elif 'yieldRatio' in raw_trader:
                apy_value = raw_trader['yieldRatio']
                apy = float(apy_value) / 100 if apy_value > 1 else float(apy_value)
            
            # 提取胜率
            win_rate = 0.0
            if 'winRate' in raw_trader:
                win_rate_value = raw_trader['winRate']
                win_rate = float(win_rate_value) / 100 if win_rate_value > 1 else float(win_rate_value)
            elif 'winRatio' in raw_trader:
                win_rate_value = raw_trader['winRatio']
                win_rate = float(win_rate_value) / 100 if win_rate_value > 1 else float(win_rate_value)
            
            # 提取跟单人数
            follower_count = int(raw_trader.get('followerCount') or raw_trader.get('followerNum') or raw_trader.get('followers', 0))
            
            # 提取杠杆
            leverage = 0.0
            if 'leverage' in raw_trader:
                leverage = float(raw_trader['leverage'] or 0)
            elif 'lever' in raw_trader:
                leverage = float(raw_trader['lever'] or 0)
            
            return {
                'unique_name': address,
                'nick_name': raw_trader.get('name') or raw_trader.get('nickname') or raw_trader.get('displayName') or address[:10] + '...',
                'portrait': raw_trader.get('avatar') or raw_trader.get('portrait') or raw_trader.get('image') or '',
                'aum': aum,
                'pnl': pnl,
                'yield_ratio': apy,  # 已经是小数格式
                'win_ratio': win_rate,  # 已经是小数格式
                'follower_num': follower_count,
                'follower_limit': int(raw_trader.get('maxFollowers') or raw_trader.get('followerLimit') or raw_trader.get('maxFollowerCount', 0)),
                'initial_day': int(raw_trader.get('tradingDays') or raw_trader.get('initialDay') or raw_trader.get('daysActive', 0)),
                'lever': leverage,
                'instruments': raw_trader.get('instruments') or raw_trader.get('symbols') or raw_trader.get('markets', []),
                'tier': raw_trader.get('tier') or raw_trader.get('level') or {},
                'full_status': raw_trader.get('isFull') or raw_trader.get('fullStatus') or raw_trader.get('isFull', False),
                'source': 'hyperliquid'  # 数据来源
            }
        except Exception as e:
            logger.error(f"[Hyperliquid] 标准化交易员数据失败: {e}, 原始数据: {raw_trader}")
            return {}

