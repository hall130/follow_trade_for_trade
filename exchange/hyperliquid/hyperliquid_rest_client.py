#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Hyperliquid REST API客户端
"""

import hmac
import hashlib
import json
import time
from typing import Dict, List, Optional, Any
from exchange.base_client import BaseRESTClient, ExchangeType, OrderRequest, OrderResponse, Position, Balance, Ticker
from utils.logger import logger
import aiohttp


class HyperliquidRESTClient(BaseRESTClient):
    """Hyperliquid REST API客户端"""
    
    def __init__(self, api_key: str, api_secret: str, passphrase: str = None, is_demo: bool = True):
        super().__init__(api_key, api_secret, passphrase, is_demo)
        
        # Hyperliquid API 基础URL
        if is_demo:
            self.base_url = "https://api.hyperliquid-testnet.xyz"
        else:
            self.base_url = "https://api.hyperliquid.xyz"
        
        self.api_url = f"{self.base_url}/info"
        self.exchange_url = f"{self.base_url}/exchange"
    
    def _get_exchange_type(self) -> ExchangeType:
        """获取交易所类型"""
        return ExchangeType.HYPERLIQUID
    
    def _sign(self, params: Dict[str, Any]) -> str:
        """生成签名（Hyperliquid使用特殊的签名方式）"""
        # Hyperliquid 使用特殊的签名方式，这里先实现基础版本
        message = json.dumps(params, separators=(',', ':'))
        signature = hmac.new(
            self.api_secret.encode('utf-8'),
            message.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
        return signature
    
    async def _request(self, method: str, endpoint: str, data: Optional[Dict] = None, params: Optional[Dict] = None) -> Dict[str, Any]:
        """
        发送HTTP请求
        
        Hyperliquid API 使用 POST 请求到 /info 端点，请求体包含 type 字段
        对于需要认证的请求，使用 /exchange 端点
        """
        # 确定使用哪个基础URL
        if endpoint.startswith('/exchange') or (data and data.get('type') in ['order', 'cancel', 'updateLeverage']):
            base_url = self.exchange_url
        else:
            base_url = self.api_url
        
        url = f"{base_url}{endpoint}" if endpoint.startswith('/') else f"{base_url}/{endpoint}"
        
        headers = {
            'Content-Type': 'application/json',
            'Accept': 'application/json'
        }
        
        # Hyperliquid 使用特殊的认证方式，对于需要签名的请求
        if self.api_key and self.api_secret and endpoint.startswith('/exchange'):
            # 对于 exchange 端点，需要签名
            # 这里先实现基础版本，具体签名逻辑需要根据文档完善
            pass
        
        try:
            async with aiohttp.ClientSession() as session:
                if method.upper() == 'GET':
                    async with session.get(url, headers=headers, params=params, proxy=self.proxy) as response:
                        if response.status != 200:
                            error_text = await response.text()
                            logger.error(f"Hyperliquid API请求失败: {response.status}, {error_text}")
                            raise Exception(f"API请求失败: {response.status}")
                        result = await response.json()
                        return result
                elif method.upper() == 'POST':
                    async with session.post(url, headers=headers, json=data, proxy=self.proxy) as response:
                        if response.status != 200:
                            error_text = await response.text()
                            logger.error(f"Hyperliquid API请求失败: {response.status}, {error_text}")
                            raise Exception(f"API请求失败: {response.status}")
                        result = await response.json()
                        return result
                else:
                    raise ValueError(f"不支持的HTTP方法: {method}")
        except aiohttp.ClientError as e:
            logger.error(f"Hyperliquid API请求网络错误: {e}")
            raise
        except Exception as e:
            logger.error(f"Hyperliquid API请求失败: {e}")
            raise
    
    async def place_order(self, order_request: OrderRequest) -> OrderResponse:
        """下单"""
        # TODO: 实现Hyperliquid下单逻辑
        raise NotImplementedError("Hyperliquid下单功能待实现")
    
    async def cancel_order(self, symbol: str, order_id: str) -> bool:
        """取消订单"""
        # TODO: 实现Hyperliquid取消订单逻辑
        raise NotImplementedError("Hyperliquid取消订单功能待实现")
    
    async def get_order(self, symbol: str, order_id: str) -> Optional[OrderResponse]:
        """获取订单信息"""
        # TODO: 实现Hyperliquid获取订单逻辑
        raise NotImplementedError("Hyperliquid获取订单功能待实现")
    
    async def get_open_orders(self, symbol: Optional[str] = None) -> List[OrderResponse]:
        """获取未成交订单"""
        # TODO: 实现Hyperliquid获取未成交订单逻辑
        raise NotImplementedError("Hyperliquid获取未成交订单功能待实现")
    
    async def get_positions(self, symbol: Optional[str] = None) -> List[Position]:
        """获取持仓信息"""
        # TODO: 实现Hyperliquid获取持仓逻辑
        raise NotImplementedError("Hyperliquid获取持仓功能待实现")
    
    async def get_balance(self) -> List[Balance]:
        """获取账户余额"""
        # TODO: 实现Hyperliquid获取余额逻辑
        raise NotImplementedError("Hyperliquid获取余额功能待实现")
    
    async def get_ticker(self, symbol: str) -> Ticker:
        """获取行情信息"""
        try:
            data = {"type": "allMids"}
            result = await self._request('POST', '/info', data=data)
            # 解析结果并返回Ticker对象
            # TODO: 实现具体的解析逻辑
            raise NotImplementedError("Hyperliquid获取行情功能待实现")
        except Exception as e:
            logger.error(f"获取Hyperliquid行情失败: {e}")
            raise
    
    async def get_klines(self, symbol: str, interval: str, 
                        start_time: Optional[int] = None, 
                        end_time: Optional[int] = None,
                        limit: int = 500) -> List[List]:
        """获取K线数据"""
        # TODO: 实现Hyperliquid获取K线逻辑
        raise NotImplementedError("Hyperliquid获取K线功能待实现")
    
    async def get_funding_rate(self, symbol: str):
        """获取资金费率"""
        # TODO: 实现Hyperliquid获取资金费率逻辑
        raise NotImplementedError("Hyperliquid获取资金费率功能待实现")
    
    async def get_open_interest(self, symbol: str):
        """获取持仓量"""
        # TODO: 实现Hyperliquid获取持仓量逻辑
        raise NotImplementedError("Hyperliquid获取持仓量功能待实现")
    
    # ==================== Hyperliquid 特有方法 ====================
    
    async def get_vaults(self, limit: int = 50) -> List[Dict]:
        """
        获取Vault列表（交易员列表）
        
        Hyperliquid API: POST /info
        Request body: {"type": "vaults"}
        
        Args:
            limit: 返回数量限制（注意：API可能不支持limit参数，需要在返回后截取）
            
        Returns:
            Vault列表
        """
        try:
            # Hyperliquid Vault API - 根据文档，type为"vaults"时返回所有vaults
            data = {"type": "vaults"}
            result = await self._request('POST', '', data=data)
            
            # Hyperliquid API 直接返回数组或包含data字段的对象
            if isinstance(result, list):
                vaults = result[:limit] if limit else result
                logger.info(f"获取到 {len(vaults)} 个Hyperliquid Vaults")
                return vaults
            elif isinstance(result, dict):
                vaults = result.get('data', [])
                if limit and len(vaults) > limit:
                    vaults = vaults[:limit]
                logger.info(f"获取到 {len(vaults)} 个Hyperliquid Vaults")
                return vaults
            else:
                logger.warning(f"Hyperliquid Vault API返回格式异常: {type(result)}")
                return []
        except Exception as e:
            logger.error(f"获取Hyperliquid Vault列表失败: {e}")
            return []
    
    async def get_vault_performance(self, vault_address: str) -> Dict:
        """
        获取Vault业绩数据
        
        Hyperliquid API: POST /info
        Request body: {"type": "vaultPerformance", "vault": vault_address}
        
        Args:
            vault_address: Vault地址
            
        Returns:
            Vault业绩数据
        """
        try:
            data = {"type": "vaultPerformance", "vault": vault_address}
            result = await self._request('POST', '', data=data)
            
            # 处理返回格式
            if isinstance(result, dict):
                return result.get('data', result)
            return result if isinstance(result, dict) else {}
        except Exception as e:
            logger.error(f"获取Hyperliquid Vault业绩失败: {e}")
            return {}
    
    async def get_user_state(self, address: str) -> Dict:
        """
        获取用户状态（持仓、余额等）
        
        Hyperliquid API: POST /info
        Request body: {"type": "clearinghouseState", "user": address}
        
        Args:
            address: 用户地址（钱包地址）
            
        Returns:
            用户状态数据，包含：
            - marginSummary: 保证金摘要
            - assetPositions: 资产持仓
            - withdrawable: 可提取余额
        """
        try:
            data = {"type": "clearinghouseState", "user": address}
            result = await self._request('POST', '', data=data)
            
            # 处理返回格式
            if isinstance(result, dict):
                return result.get('data', result)
            return result if isinstance(result, dict) else {}
        except Exception as e:
            logger.error(f"获取Hyperliquid用户状态失败: {e}")
            return {}
    
    async def get_all_mids(self) -> Dict[str, float]:
        """
        获取所有交易对的中间价
        
        Hyperliquid API: POST /info
        Request body: {"type": "allMids"}
        
        Returns:
            字典格式：{symbol: mid_price}
        """
        try:
            data = {"type": "allMids"}
            result = await self._request('POST', '', data=data)
            
            if isinstance(result, dict):
                return result.get('data', {})
            return result if isinstance(result, dict) else {}
        except Exception as e:
            logger.error(f"获取Hyperliquid所有中间价失败: {e}")
            return {}
    
    async def get_user_fills(self, address: str, start_time: Optional[int] = None, end_time: Optional[int] = None) -> List[Dict]:
        """
        获取用户成交记录
        
        Hyperliquid API: POST /info
        Request body: {"type": "userFills", "user": address}
        
        Args:
            address: 用户地址
            start_time: 开始时间戳（可选）
            end_time: 结束时间戳（可选）
            
        Returns:
            成交记录列表
        """
        try:
            data = {"type": "userFills", "user": address}
            if start_time:
                data["startTime"] = start_time
            if end_time:
                data["endTime"] = end_time
            
            result = await self._request('POST', '', data=data)
            
            if isinstance(result, list):
                return result
            elif isinstance(result, dict):
                return result.get('data', [])
            return []
        except Exception as e:
            logger.error(f"获取Hyperliquid用户成交记录失败: {e}")
            return []
    
    async def get_user_funding(self, address: str) -> List[Dict]:
        """
        获取用户资金费率历史
        
        Hyperliquid API: POST /info
        Request body: {"type": "userFunding", "user": address}
        
        Args:
            address: 用户地址
            
        Returns:
            资金费率历史列表
        """
        try:
            data = {"type": "userFunding", "user": address}
            result = await self._request('POST', '', data=data)
            
            if isinstance(result, list):
                return result
            elif isinstance(result, dict):
                return result.get('data', [])
            return []
        except Exception as e:
            logger.error(f"获取Hyperliquid用户资金费率失败: {e}")
            return []
    
    async def get_meta(self) -> Dict:
        """
        获取交易所元数据（交易对信息、资金费率等）
        
        Hyperliquid API: POST /info
        Request body: {"type": "meta"}
        
        Returns:
            元数据字典
        """
        try:
            data = {"type": "meta"}
            result = await self._request('POST', '', data=data)
            
            if isinstance(result, dict):
                return result.get('data', result)
            return result if isinstance(result, dict) else {}
        except Exception as e:
            logger.error(f"获取Hyperliquid元数据失败: {e}")
            return {}

    # ── 以下为BaseRESTClient要求的抽象方法存根 ──────────────────────────
    # Hyperliquid不支持这些接口，返回空/None保证可实例化

    async def get_mark_price(self, symbol: str):
        """Hyperliquid暂不支持标记价格接口"""
        return None

    async def get_liquidation_orders(self, symbol=None, limit: int = 100):
        """Hyperliquid暂不支持强平订单查询"""
        return []

    async def get_trade_fee(self, symbol: str, category: str = "spot"):
        """Hyperliquid暂不支持手续费查询接口"""
        return None

    async def get_margin_balance(self, asset=None):
        """Hyperliquid暂不支持保证金余额查询"""
        return []

    async def get_instruments(self, inst_type: str = "SPOT"):
        """Hyperliquid暂不支持交易产品列表接口"""
        return []

    async def get_bill_details(self, asset=None, limit: int = 100):
        """Hyperliquid暂不支持账单详情接口"""
        return []

