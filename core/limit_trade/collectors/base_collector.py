#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
带单员数据采集器基类
定义统一的接口，供不同交易所/平台实现
"""

from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Any
import aiohttp
from utils.logger import logger


class BaseTraderCollector(ABC):
    """带单员数据采集器基类"""
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        初始化采集器
        
        Args:
            config: 采集器配置字典
        """
        self.config = config or {}
        self.collector_type = self.get_collector_type()
    
    @abstractmethod
    def get_collector_type(self) -> str:
        """
        获取采集器类型标识
        
        Returns:
            采集器类型字符串，如 'okx', 'binance' 等
        """
        pass
    
    @abstractmethod
    async def get_trade_records_async(
        self, 
        session: aiohttp.ClientSession, 
        trader_identifier: str, 
        limit: int = 1,
        start_time_ms: Optional[int] = None
    ) -> List[Dict]:
        """
        异步获取交易记录
        
        Args:
            session: aiohttp会话对象
            trader_identifier: 带单员标识符（OKX为uniqueName，Binance为portfolioId等）
            limit: 获取的记录数量限制
            start_time_ms: 起始时间（毫秒时间戳），可选，用于动态计算查询时间范围
            
        Returns:
            交易记录列表，每个记录为字典格式
        """
        pass
    
    @abstractmethod
    def normalize_trade_record(self, raw_record: Dict) -> Dict:
        """
        将原始交易记录标准化为统一格式
        
        Args:
            raw_record: 原始交易记录（来自不同交易所的格式）
            
        Returns:
            标准化的交易记录字典，包含以下字段：
            - ordId: 订单ID
            - instId: 交易对
            - side: 交易方向 (buy/sell)
            - posSide: 持仓方向 (long/short)
            - sz: 数量
            - avgPx: 平均价格
            - cTime: 创建时间（毫秒时间戳）
        """
        pass
    
    async def get_latest_trade(
        self, 
        session: aiohttp.ClientSession, 
        trader_identifier: str
    ) -> Optional[Dict]:
        """
        获取最新一条交易记录（便捷方法）
        
        Args:
            session: aiohttp会话对象
            trader_identifier: 带单员标识符
            
        Returns:
            最新交易记录，如果没有则返回None
        """
        try:
            records = await self.get_trade_records_async(session, trader_identifier, limit=1)
            if records:
                return self.normalize_trade_record(records[0])
            return None
        except Exception as e:
            logger.error(f"[{self.collector_type}] 获取最新交易记录失败: {e}")
            return None
    
    def get_trader_identifier_key(self) -> str:
        """
        获取带单员标识符在数据库中的字段名
        
        Returns:
            字段名，如 'trader_unique_name', 'portfolio_id' 等
        """
        # 默认使用 trader_unique_name，子类可以重写
        return 'trader_unique_name'
    
    def validate_trader_identifier(self, trader_identifier: str) -> bool:
        """
        验证带单员标识符格式
        
        Args:
            trader_identifier: 带单员标识符
            
        Returns:
            是否有效
        """
        return bool(trader_identifier and trader_identifier.strip())

