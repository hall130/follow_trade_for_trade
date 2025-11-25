#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
OKX带单员数据采集器
"""

import aiohttp
from typing import Dict, List, Optional, Any
from utils.logger import logger
from .base_collector import BaseTraderCollector


class OKXTraderCollector(BaseTraderCollector):
    """OKX带单员数据采集器"""
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        初始化OKX采集器
        
        Args:
            config: 配置字典，可包含：
                - api_base_url: API基础URL（默认：OKX公开API）
                - timeout: 请求超时时间（秒，默认：10）
        """
        super().__init__(config)
        self.api_base_url = self.config.get(
            'api_base_url', 
            'https://www.okx.com/priapi/v5/ecotrade/public/community/user/trade-records'
        )
        self.timeout = self.config.get('timeout', 10)
    
    def get_collector_type(self) -> str:
        """获取采集器类型"""
        return 'okx'
    
    async def get_trade_records_async(
        self, 
        session: aiohttp.ClientSession, 
        trader_identifier: str, 
        limit: int = 1,
        start_time_ms: Optional[int] = None
    ) -> List[Dict]:
        """
        异步获取OKX带单员交易记录
        
        Args:
            session: aiohttp会话对象
            trader_identifier: OKX带单员uniqueName
            limit: 获取的记录数量限制
            start_time_ms: 起始时间（毫秒时间戳），可选，OKX API可能不支持此参数，但保留接口一致性
            
        Returns:
            交易记录列表
        """
        if not self.validate_trader_identifier(trader_identifier):
            logger.error(f"[OKX] 无效的带单员标识符: {trader_identifier}")
            return []
        
        params = {
            'uniqueName': trader_identifier,
            'instType': 'SWAP',
            'limit': limit
        }
        
        try:
            timeout = aiohttp.ClientTimeout(total=self.timeout)
            async with session.get(
                self.api_base_url, 
                params=params, 
                timeout=timeout
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    if data.get('code') == '0':
                        records = data.get('data', [])
                        logger.debug(f"[OKX] 获取到 {len(records)} 条交易记录")
                        return records
                    else:
                        logger.error(f"[OKX] 获取交易记录失败: {data.get('msg', '未知错误')}")
                        return []
                else:
                    error_text = await response.text()
                    logger.error(f"[OKX] 请求失败，状态码: {response.status}, 错误: {error_text}")
                    return []
                    
        except Exception as e:
            logger.error(f"[OKX] 异步请求失败: {e}")
            return []
    
    def normalize_trade_record(self, raw_record: Dict) -> Dict:
        """
        将OKX原始交易记录标准化
        
        OKX原始格式：
        {
            'ordId': '订单ID',
            'instId': 'BTC-USDT-SWAP',
            'side': 'buy'/'sell',
            'posSide': 'long'/'short',
            'sz': '数量',
            'avgPx': '平均价格',
            'cTime': '创建时间（毫秒）'
        }
        """
        try:
            return {
                'ordId': raw_record.get('ordId', ''),
                'instId': raw_record.get('instId', ''),
                'side': raw_record.get('side', '').lower(),
                'posSide': raw_record.get('posSide', '').lower(),
                'sz': float(raw_record.get('sz', '0')),
                'avgPx': float(raw_record.get('avgPx', '0')),
                'cTime': raw_record.get('cTime', ''),
                'source': 'okx'  # 标记数据来源
            }
        except Exception as e:
            logger.error(f"[OKX] 标准化交易记录失败: {e}, 原始数据: {raw_record}")
            return {}
    
    def get_trader_identifier_key(self) -> str:
        """OKX使用trader_unique_name作为标识符"""
        return 'trader_unique_name'

