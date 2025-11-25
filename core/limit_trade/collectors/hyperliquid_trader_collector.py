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
        limit: int = 1,
        start_time_ms: Optional[int] = None
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
            start_time_ms: 起始时间（毫秒时间戳），如果提供则使用此时间，否则使用默认的default_days
            
        Returns:
            交易记录列表
        """
        # Hyperliquid使用钱包地址作为标识符
        address = trader_identifier
        
        if not self.validate_trader_identifier(address):
            logger.error(f"[Hyperliquid] 无效的带单员地址: {address}")
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
                        def get_sort_key(record):
                            time_value = record.get('time', 0)
                            # 确保是数字类型（Hyperliquid返回的是毫秒时间戳整数）
                            if isinstance(time_value, (int, float)):
                                return time_value
                            elif isinstance(time_value, str):
                                # 如果是字符串，尝试转换为数字
                                try:
                                    return float(time_value)
                                except (ValueError, TypeError):
                                    return 0
                            return 0
                        
                        records.sort(key=get_sort_key, reverse=True)
                        # 限制数量
                        if limit and len(records) > limit:
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
        
        实际 Hyperliquid API 返回格式：
        {
            "coin": "BTC",
            "px": "87893.0",
            "sz": "0.11358",
            "side": "A" (Ask/Sell) / "B" (Buy),
            "time": 1764005655887,  # 毫秒时间戳（整数）
            "startPosition": "0.4557",  # 起始持仓（字符串）
            "dir": "Close Long",  # 方向：Close Long, Open Short 等
            "hash": "0x808c2e906e174b75820504301c9de102073c0076091a6a472454d9e32d1b2560",
            "oid": 247407563348,
            "closedPnl": "455.22864",
            "fee": "1.497433",
            ...
        }
        
        转换为标准格式：
        {
            'ordId': '订单ID（hash或oid）',
            'instId': 'BTC' -> 'BTC-USDT-PERP',
            'side': 'buy'/'sell',
            'posSide': 'long'/'short' (根据dir或startPosition判断),
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
            # Hyperliquid API 实际返回的 time 字段是毫秒时间戳（整数），不是 ISO 字符串
            time_value = raw_record.get('time', '')
            if time_value:
                try:
                    # 如果是数字（整数或浮点数），直接使用
                    if isinstance(time_value, (int, float)):
                        c_time = int(time_value)
                    elif isinstance(time_value, str):
                        # 如果是字符串，先尝试转换为数字
                        if time_value.isdigit() or ('.' in time_value and time_value.replace('.', '').isdigit()):
                            c_time = int(float(time_value))
                        else:
                            # 如果是 ISO 格式字符串，尝试解析
                            dt = datetime.fromisoformat(time_value.replace('Z', '+00:00'))
                            c_time = int(dt.timestamp() * 1000)
                    else:
                        c_time = int(time.time() * 1000)
                except (ValueError, TypeError, AttributeError) as e:
                    logger.warning(f"[Hyperliquid] 解析时间字段失败: {e}, 使用当前时间")
                    c_time = int(time.time() * 1000)
            else:
                c_time = int(time.time() * 1000)
            
            # 提取持仓方向
            # Hyperliquid 实际数据中有 startPosition 和 dir 字段
            # dir 字段如 "Close Long", "Open Short" 等可以直接判断
            pos_side = 'long'  # 默认值
            
            # 优先使用 dir 字段判断
            dir_str = raw_record.get('dir', '').upper()
            if 'LONG' in dir_str:
                pos_side = 'long'
            elif 'SHORT' in dir_str:
                pos_side = 'short'
            else:
                # 如果没有 dir 字段，使用 startPosition 判断
                start_pos = raw_record.get('startPosition', '')
                if start_pos:
                    try:
                        start_pos_float = float(start_pos)
                        if start_pos_float > 0:
                            pos_side = 'long'
                        elif start_pos_float < 0:
                            pos_side = 'short'
                    except (ValueError, TypeError):
                        pass
                
                # 如果都没有，尝试从 side_info 中判断（兼容旧格式）
                side_info = raw_record.get('side_info', [])
                if side_info:
                    for info in side_info:
                        start_pos_info = info.get('start_pos', '0')
                        try:
                            start_pos_float = float(start_pos_info)
                            if start_pos_float > 0:
                                pos_side = 'long'
                            elif start_pos_float < 0:
                                pos_side = 'short'
                            break
                        except (ValueError, TypeError):
                            continue
            
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

