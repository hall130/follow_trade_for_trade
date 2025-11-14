#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
交易所客户端工厂
用于创建具体的交易所客户端实例
"""

from typing import Union
from .base_client import BaseRESTClient, BaseWebSocketClient, ExchangeType
from .okx.okx_rest_client import OKXRESTClient
from .okx.okx_ws_client import OKXWebSocketClient
from .binance.binance_rest_client import BinanceRESTClient
from .binance.binance_ws_client import BinanceWebSocketClient
from .bybit.bybit_rest_client import BybitRESTClient
from .bybit.bybit_ws_client import BybitWebSocketClient
from .hyperliquid.hyperliquid_rest_client import HyperliquidRESTClient
from .hyperliquid.hyperliquid_ws_client import HyperliquidWebSocketClient
from utils.logger import logger


class ExchangeClientFactory:
    """交易所客户端工厂类"""
    
    @staticmethod
    def create_rest_client(exchange: ExchangeType, api_key: str, api_secret: str, 
                          passphrase: str = None, is_demo: bool = True) -> BaseRESTClient:
        """
        创建REST客户端
        
        Args:
            exchange: 交易所类型
            api_key: API密钥
            api_secret: API密钥
            passphrase: 密码短语（仅OKX需要）
            is_demo: 是否使用演示模式
        
        Returns:
            具体的REST客户端实例
        """
        if exchange == ExchangeType.OKX:
            return OKXRESTClient(api_key, api_secret, passphrase, is_demo)
        elif exchange == ExchangeType.BINANCE:
            return BinanceRESTClient(api_key, api_secret, passphrase, is_demo)
        elif exchange == ExchangeType.BYBIT:
            return BybitRESTClient(api_key, api_secret, passphrase, is_demo)
        elif exchange == ExchangeType.HYPERLIQUID:
            return HyperliquidRESTClient(api_key, api_secret, passphrase, is_demo)
        else:
            raise ValueError(f"不支持的交易所类型: {exchange}")
    
    @staticmethod
    def create_ws_client(exchange: ExchangeType, api_key: str = None, api_secret: str = None, 
                        passphrase: str = None, is_demo: bool = True) -> BaseWebSocketClient:
        """
        创建WebSocket客户端
        
        Args:
            exchange: 交易所类型
            api_key: API密钥（可选）
            api_secret: API密钥（可选）
            passphrase: 密码短语（仅OKX需要，可选）
            is_demo: 是否使用演示模式
        
        Returns:
            具体的WebSocket客户端实例
        """
        if exchange == ExchangeType.OKX:
            return OKXWebSocketClient(api_key, api_secret, passphrase, is_demo)
        elif exchange == ExchangeType.BINANCE:
            return BinanceWebSocketClient(api_key, api_secret, passphrase, is_demo)
        elif exchange == ExchangeType.BYBIT:
            return BybitWebSocketClient(api_key, api_secret, passphrase, is_demo)
        elif exchange == ExchangeType.HYPERLIQUID:
            return HyperliquidWebSocketClient(api_key, api_secret, passphrase, is_demo)
        else:
            raise ValueError(f"不支持的交易所类型: {exchange}")
    
    @staticmethod
    def get_supported_exchanges() -> list:
        """获取支持的交易所列表"""
        return [exchange.value for exchange in ExchangeType]
    
    @staticmethod
    def is_exchange_supported(exchange: str) -> bool:
        """检查是否支持指定交易所"""
        try:
            ExchangeType(exchange.lower())
            return True
        except ValueError:
            return False
