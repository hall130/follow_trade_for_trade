#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Hyperliquid带单员数据采集器
用于获取Hyperliquid平台上的交易员交易记录
"""

import aiohttp
import time
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
from utils.logger import logger
from .base_collector import BaseTraderCollector


class HyperliquidTraderCollector(BaseTraderCollector):
    """Hyperliquid带单员数据采集器"""
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        初始化Hyperliquid采集器
        
        Args:
            config: 配置字典，可包含：
                - api_base_url: API基础URL（默认：Hyperliquid公开API）
                - timeout: 请求超时时间（秒，默认：10）
                - default_days: 默认查询天数（默认：7天）
        """
        super().__init__(config)
        self.api_base_url = self.config.get(
            'api_base_url',
            'https://api.hyperliquid.xyz/info'
        )
        self.timeout = self.config.get('timeout', 10)
        self.default_days = self.config.get('default_days', 7)
    
    def get_collector_type(self) -> str:
        """获取采集器类型"""
        return 'hyperliquid'
    
    async def get_trade_records_async(
        self, 
        session: aiohttp.ClientSession, 
        trader_identifier: str, 
        limit: int = 1
    ) -> List[Dict]:
        """
        异步获取Hyperliquid带单员交易记录
        
        根据 Hyperliquid API 文档：
        - 使用 POST /info 端点
        - Request body: {"type": "userFills", "user": address}
        - 可选参数: startTime, endTime
        
        Args:
            session: aiohttp会话对象
            trader_identifier: Hyperliquid带单员地址（0x开头的钱包地址）
            limit: 获取的记录数量限制
            
        Returns:
            交易记录列表
        """
        # Hyperliquid使用钱包地址作为标识符
        address = trader_identifier
        
        if not self.validate_trader_identifier(address):
            logger.error(f"[Hyperliquid] 无效的带单员地址: {address}")
            return []
        
        # 计算时间范围（默认最近7天）
        now = datetime.now()
        end_time = int(now.timestamp() * 1000)
        start_time = int((now - timedelta(days=self.default_days)).timestamp() * 1000)
        
        payload = {
            "type": "userFills",
            "user": address,
            "startTime": start_time,
            "endTime": end_time
        }
        
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
                    
                    # Hyperliquid API 可能返回数组或包含data字段的对象
                    if isinstance(data, list):
                        records = data
                    elif isinstance(data, dict):
                        records = data.get('data', [])
                    else:
                        records = []
                    
                    # 按时间倒序排序（最新的在前），然后限制数量
                    if records:
                        # 确保按时间戳排序（如果有time字段）
                        records.sort(key=lambda x: x.get('time', 0), reverse=True)
                        records = records[:limit]
                    
                    logger.debug(f"[Hyperliquid] 获取到 {len(records)} 条交易记录")
                    return records
                else:
                    error_text = await response.text()
                    logger.error(f"[Hyperliquid] 请求失败，状态码: {response.status}, 错误: {error_text}")
                    return []
                    
        except Exception as e:
            logger.error(f"[Hyperliquid] 异步请求失败: {e}")
            return []
    
    def normalize_trade_record(self, raw_record: Dict) -> Dict:
        """
        将Hyperliquid原始交易记录标准化为统一格式
        
        根据 Hyperliquid L1 数据架构文档，交易记录格式：
        {
            "coin": "BTC",
            "side": "B" (Buy) / "A" (Ask/Sell),
            "time": "2024-07-26T08:26:25.899",
            "px": "51.367",
            "sz": "0.31",
            "hash": "0x...",
            "side_info": [
                {
                    "user": "0x...",
                    "start_pos": "996.67",
                    "oid": 12212201265,
                    ...
                },
                ...
            ]
        }
        
        转换为标准格式：
        {
            'ordId': '订单ID',
            'instId': 'BTC' -> 'BTC-USDT-PERP' (需要根据实际情况调整),
            'side': 'buy'/'sell',
            'posSide': 'long'/'short' (根据start_pos判断),
            'sz': '数量',
            'avgPx': '价格',
            'cTime': '创建时间（毫秒）'
        }
        """
        try:
            # 提取订单ID（使用hash或oid）
            order_id = str(raw_record.get('hash') or raw_record.get('oid') or '')
            
            # 提取交易对
            coin = raw_record.get('coin', '')
            # Hyperliquid 使用币种名称，需要转换为标准格式
            # 假设是永续合约，格式为 COIN-USDT-PERP
            inst_id = f"{coin}-USDT-PERP" if coin else ''
            
            # 提取交易方向并转换
            # Hyperliquid: "B" = Buy, "A" = Ask/Sell
            side_raw = raw_record.get('side', '').upper()
            side = 'buy' if side_raw == 'B' else 'sell'
            
            # 提取数量和价格
            sz = float(raw_record.get('sz', '0'))
            px = float(raw_record.get('px', '0'))
            
            # 提取时间并转换为毫秒时间戳
            time_str = raw_record.get('time', '')
            if time_str:
                try:
                    # 解析 ISO 格式时间: "2024-07-26T08:26:25.899"
                    dt = datetime.fromisoformat(time_str)
                    c_time = int(dt.timestamp() * 1000)
                except:
                    # 如果解析失败，使用当前时间
                    c_time = int(time.time() * 1000)
            else:
                c_time = int(time.time() * 1000)
            
            # 提取持仓方向（从side_info中判断）
            # 如果start_pos为正，可能是long；为负可能是short
            pos_side = 'long'  # 默认值
            side_info = raw_record.get('side_info', [])
            if side_info:
                # 查找当前用户的side_info
                for info in side_info:
                    start_pos = float(info.get('start_pos', '0'))
                    if start_pos > 0:
                        pos_side = 'long'
                    elif start_pos < 0:
                        pos_side = 'short'
                    break  # 使用第一个匹配的
            
            return {
                'ordId': order_id,
                'instId': inst_id,
                'side': side,
                'posSide': pos_side,
                'sz': sz,
                'avgPx': px,
                'cTime': str(c_time),
                'source': 'hyperliquid',  # 标记数据来源
                'coin': coin,  # 保留原始币种名称
                'hash': raw_record.get('hash', ''),  # 保留交易哈希
            }
        except Exception as e:
            logger.error(f"[Hyperliquid] 标准化交易记录失败: {e}, 原始数据: {raw_record}")
            return {}
    
    def get_trader_identifier_key(self) -> str:
        """Hyperliquid使用钱包地址作为标识符"""
        return 'address'
    
    def validate_trader_identifier(self, trader_identifier: str) -> bool:
        """验证Hyperliquid地址格式（0x开头的以太坊地址）"""
        if not trader_identifier or not trader_identifier.strip():
            return False
        # Hyperliquid使用以太坊地址格式（0x开头，42个字符）
        addr = trader_identifier.strip()
        return addr.startswith('0x') and len(addr) == 42

