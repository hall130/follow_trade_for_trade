#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Binance带单员数据采集器
"""

import aiohttp
import time
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
from utils.logger import logger
from .base_collector import BaseTraderCollector


class BinanceTraderCollector(BaseTraderCollector):
    """Binance带单员数据采集器"""
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        初始化Binance采集器
        
        Args:
            config: 配置字典，可包含：
                - api_base_url: API基础URL（默认：Binance带单员API）
                - timeout: 请求超时时间（秒，默认：10）
                - default_days: 默认查询天数（默认：7天）
        """
        super().__init__(config)
        self.api_base_url = self.config.get(
            'api_base_url',
            'https://www.binance.com/bapi/futures/v1/friendly/future/copy-trade/lead-portfolio/order-history'
        )
        self.timeout = self.config.get('timeout', 10)
        self.default_days = self.config.get('default_days', 7)
    
    def get_collector_type(self) -> str:
        """获取采集器类型"""
        return 'binance'
    
    async def get_trade_records_async(
        self, 
        session: aiohttp.ClientSession, 
        trader_identifier: str, 
        limit: int = 1,
        start_time_ms: Optional[int] = None
    ) -> List[Dict]:
        """
        异步获取Binance带单员交易记录
        
        Args:
            session: aiohttp会话对象
            trader_identifier: Binance带单员portfolioId（在数据库中，trader_unique_name存储的就是portfolioId）
            limit: 获取的记录数量限制（Binance使用pageSize）
            start_time_ms: 起始时间（毫秒时间戳），如果提供则使用此时间，否则使用默认的default_days
            
        Returns:
            交易记录列表
        """
        # Binance使用portfolioId作为标识符，在数据库中trader_unique_name字段存储的就是portfolioId
        portfolio_id = trader_identifier
        
        if not self.validate_trader_identifier(portfolio_id):
            logger.error(f"[Binance] 无效的带单员标识符: {portfolio_id}")
            return []
        
        # 计算时间范围
        now = datetime.now()
        end_time = int(now.timestamp() * 1000)
        
        # 如果提供了start_time_ms，使用它；否则使用默认的default_days
        if start_time_ms is not None:
            start_time = start_time_ms
            # 确保时间范围不超过默认天数（避免查询过多历史数据）
            min_start_time = int((now - timedelta(days=self.default_days)).timestamp() * 1000)
            start_time = max(start_time, min_start_time)
        else:
            start_time = int((now - timedelta(days=self.default_days)).timestamp() * 1000)
        
        payload = {
            "portfolioId": portfolio_id,
            "startTime": start_time,
            "endTime": end_time,
            "pageSize": limit
        }
        
        headers = {
            'Content-Type': 'application/json',
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        
        try:
            timeout = aiohttp.ClientTimeout(total=self.timeout)
            async with session.post(
                self.api_base_url,
                headers=headers,
                json=payload,
                timeout=timeout
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    
                    # Binance API响应格式：{"code": "000000", "data": {"list": [...], ...}}
                    if data.get("code") == "000000" or data.get("success") is not False:
                        records = data.get("data", {}).get("list", [])
                        
                        # 按时间倒序排序（最新的在前），确保顺序正确
                        if records:
                            def get_sort_key(record):
                                # 优先使用 orderTime，其次 orderUpdateTime
                                time_value = record.get('orderTime') or record.get('orderUpdateTime') or 0
                                # 确保是数字类型
                                if isinstance(time_value, (int, float)):
                                    return time_value
                                elif isinstance(time_value, str) and time_value.isdigit():
                                    return int(time_value)
                                return 0
                            
                            records.sort(key=get_sort_key, reverse=True)
                            # 限制数量
                            if limit and len(records) > limit:
                                records = records[:limit]
                        
                        logger.debug(f"[Binance] 获取到 {len(records)} 条交易记录")
                        return records
                    else:
                        logger.error(f"[Binance] 获取交易记录失败: {data.get('message', '未知错误')}")
                        return []
                else:
                    error_text = await response.text()
                    logger.error(f"[Binance] 请求失败，状态码: {response.status}, 错误: {error_text}")
                    return []
                    
        except Exception as e:
            logger.error(f"[Binance] 异步请求失败: {e}")
            return []
    
    def normalize_trade_record(self, raw_record: Dict) -> Dict:
        """
        将Binance原始交易记录标准化为OKX格式
        
        Binance原始格式（可能没有orderId）：
        {
            'symbol': 'BTCUSDT',
            'side': 'BUY',
            'positionSide': 'SHORT',
            'executedQty': 0.534,
            'avgPrice': 86099.9,
            'orderTime': 1763998112892,
            'orderUpdateTime': 1763998112892,
            'type': 'MARKET',
            ...
        }
        
        转换为标准格式：
        {
            'ordId': '订单ID（如果没有则生成唯一标识符）',
            'instId': 'BTCUSDT' -> 'BTC-USDT-SWAP',
            'side': 'BUY'/'SELL' -> 'buy'/'sell',
            'posSide': 'LONG'/'SHORT' -> 'long'/'short',
            'sz': '数量',
            'avgPx': '平均价格',
            'cTime': '创建时间（毫秒）'
        }
        """
        try:
            # 提取时间（优先使用orderTime，其次orderUpdateTime，最后其他字段）
            c_time = (
                raw_record.get('orderTime') or 
                raw_record.get('orderUpdateTime') or 
                raw_record.get('createTime') or 
                raw_record.get('time') or 
                raw_record.get('cTime') or 
                ''
            )
            
            # 处理时间戳
            if isinstance(c_time, (int, float)):
                c_time_ms = int(c_time)
            elif isinstance(c_time, str):
                if c_time.isdigit():
                    c_time_ms = int(c_time)
                else:
                    # 如果是字符串格式的时间，尝试转换
                    try:
                        from datetime import datetime
                        dt = datetime.fromisoformat(c_time.replace('Z', '+00:00'))
                        c_time_ms = int(dt.timestamp() * 1000)
                    except:
                        c_time_ms = int(time.time() * 1000)
            else:
                c_time_ms = int(time.time() * 1000)
            
            # 提取订单ID（如果没有，则使用时间戳+交易对+方向+数量生成唯一标识符）
            ord_id = str(raw_record.get('orderId') or raw_record.get('id') or '')
            
            # 如果没有订单ID，生成唯一标识符
            if not ord_id:
                symbol = raw_record.get('symbol', '')
                side = raw_record.get('side', '')
                pos_side = raw_record.get('positionSide', '')
                # 使用时间戳+交易对+方向+数量生成唯一标识符
                sz = float(raw_record.get('executedQty') or raw_record.get('quantity') or raw_record.get('qty') or 0)
                avg_px = float(raw_record.get('avgPrice') or raw_record.get('price') or raw_record.get('avgPx') or 0)
                # 使用时间戳+交易对+方向+持仓方向+数量+价格生成唯一标识符，确保唯一性
                ord_id = f"BINANCE_{c_time_ms}_{symbol}_{side}_{pos_side}_{sz}_{avg_px}"
                logger.debug(f"[Binance] 订单没有orderId，生成唯一标识符: {ord_id}")
            
            # 提取交易对并转换格式（Binance: BTCUSDT -> OKX: BTC-USDT-SWAP）
            symbol = raw_record.get('symbol', '')
            if symbol and not '-' in symbol:
                # 假设是永续合约，转换为OKX格式
                # 简单处理：BTCUSDT -> BTC-USDT-SWAP
                if len(symbol) >= 6:
                    base = symbol[:-4]  # BTC
                    quote = symbol[-4:]  # USDT
                    inst_id = f"{base}-{quote}-SWAP"
                else:
                    inst_id = symbol
            else:
                inst_id = symbol
            
            # 提取交易方向并转换
            side_raw = raw_record.get('side', '').upper()
            side = 'buy' if side_raw in ['BUY', 'BUY_OPEN', 'BUY_CLOSE'] else 'sell'
            
            # 提取持仓方向并转换
            pos_side_raw = (raw_record.get('positionSide') or raw_record.get('posSide') or '').upper()
            pos_side = 'long' if pos_side_raw in ['LONG', 'L'] else 'short'
            
            # 提取数量和价格（优先使用executedQty和avgPrice）
            sz = float(
                raw_record.get('executedQty') or 
                raw_record.get('quantity') or 
                raw_record.get('qty') or 
                0
            )
            avg_px = float(
                raw_record.get('avgPrice') or 
                raw_record.get('price') or 
                raw_record.get('avgPx') or 
                0
            )
            
            return {
                'ordId': ord_id,
                'instId': inst_id,
                'side': side,
                'posSide': pos_side,
                'sz': sz,
                'avgPx': avg_px,
                'cTime': str(c_time_ms),
                'source': 'binance'  # 标记数据来源
            }
        except Exception as e:
            logger.error(f"[Binance] 标准化交易记录失败: {e}, 原始数据: {raw_record}")
            return {}
    
    def get_trader_identifier_key(self) -> str:
        """Binance使用portfolio_id作为标识符"""
        return 'portfolio_id'
    
    def validate_trader_identifier(self, trader_identifier: str) -> bool:
        """验证Binance portfolioId格式（通常是数字字符串）"""
        if not trader_identifier or not trader_identifier.strip():
            return False
        # Binance portfolioId通常是纯数字
        return trader_identifier.strip().isdigit()

