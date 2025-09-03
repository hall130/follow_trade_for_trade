#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
交易所工厂类
用于统一管理不同交易所的客户端
"""

from typing import Dict, Any, Optional, Union
from utils.logger import logger

# 导入所有交易所客户端
from .okx.okx_rest_client import OKXRESTClient
from .okx.okx_ws_client import OKXWebSocketClient
from .binance.binance_rest_client import BinanceRESTClient
from .binance.binance_ws_client import BinanceWebSocketClient

# 导入配置
from config import get_okx_config, get_binance_config


class ExchangeFactory:
    """交易所工厂类"""
    
    def __init__(self):
        self.rest_clients = {}
        self.ws_clients = {}
        self.supported_exchanges = ['okx', 'binance']
    
    def create_rest_client(self, exchange: str, api_key: str, api_secret: str, 
                          passphrase: str = None, is_demo: bool = True) -> Union[OKXRESTClient, BinanceRESTClient]:
        """
        创建REST API客户端
        
        Args:
            exchange: 交易所名称 ('okx', 'binance')
            api_key: API密钥
            api_secret: API密钥
            passphrase: 密码短语（仅OKX需要）
            is_demo: 是否使用演示模式
        
        Returns:
            REST API客户端实例
        """
        exchange = exchange.lower()
        
        if exchange == 'okx':
            client = OKXRESTClient(api_key, api_secret, passphrase, is_demo)
            self.rest_clients[f'okx_{api_key}'] = client
            logger.info(f"已创建OKX REST客户端: {api_key}")
            return client
            
        elif exchange == 'binance':
            client = BinanceRESTClient(api_key, api_secret, is_demo)
            self.rest_clients[f'binance_{api_key}'] = client
            logger.info(f"已创建币安REST客户端: {api_key}")
            return client
            
        else:
            raise ValueError(f"不支持的交易所: {exchange}")
    
    def create_ws_client(self, exchange: str, api_key: str = None, api_secret: str = None, 
                        is_demo: bool = True) -> Union[OKXWebSocketClient, BinanceWebSocketClient]:
        """
        创建WebSocket客户端
        
        Args:
            exchange: 交易所名称 ('okx', 'binance')
            api_key: API密钥（可选）
            api_secret: API密钥（可选）
            is_demo: 是否使用演示模式
        
        Returns:
            WebSocket客户端实例
        """
        exchange = exchange.lower()
        
        if exchange == 'okx':
            client = OKXWebSocketClient(api_key, api_secret, is_demo)
            self.ws_clients[f'okx_{api_key or "public"}'] = client
            logger.info(f"已创建OKX WebSocket客户端: {api_key or 'public'}")
            return client
            
        elif exchange == 'binance':
            client = BinanceWebSocketClient(api_key, api_secret, is_demo)
            self.ws_clients[f'binance_{api_key or "public"}'] = client
            logger.info(f"已创建币安WebSocket客户端: {api_key or 'public'}")
            return client
            
        else:
            raise ValueError(f"不支持的交易所: {exchange}")
    
    def get_rest_client(self, exchange: str, api_key: str) -> Optional[Union[OKXRESTClient, BinanceRESTClient]]:
        """获取已创建的REST客户端"""
        key = f'{exchange.lower()}_{api_key}'
        return self.rest_clients.get(key)
    
    def get_ws_client(self, exchange: str, api_key: str = None) -> Optional[Union[OKXWebSocketClient, BinanceWebSocketClient]]:
        """获取已创建的WebSocket客户端"""
        key = f'{exchange.lower()}_{api_key or "public"}'
        return self.ws_clients.get(key)
    
    def create_client_from_config(self, exchange: str, is_demo: bool = True) -> Union[OKXRESTClient, BinanceRESTClient]:
        """
        从配置文件创建客户端
        
        Args:
            exchange: 交易所名称
            is_demo: 是否使用演示模式
        
        Returns:
            REST API客户端实例
        """
        exchange = exchange.lower()
        
        if exchange == 'okx':
            config = get_okx_config()
            return self.create_rest_client(
                'okx',
                config['api_key'],
                config['api_secret'],
                config['passphrase'],
                is_demo
            )
            
        elif exchange == 'binance':
            config = get_binance_config()
            return self.create_rest_client(
                'binance',
                config['api_key'],
                config['api_secret'],
                is_demo=is_demo
            )
            
        else:
            raise ValueError(f"不支持的交易所: {exchange}")
    
    def get_all_clients(self) -> Dict[str, Any]:
        """获取所有客户端"""
        return {
            'rest_clients': self.rest_clients,
            'ws_clients': self.ws_clients
        }
    
    def close_all_clients(self):
        """关闭所有客户端连接"""
        # 关闭WebSocket连接
        for client in self.ws_clients.values():
            try:
                if hasattr(client, 'close_all'):
                    asyncio.create_task(client.close_all())
                elif hasattr(client, 'close'):
                    client.close()
            except Exception as e:
                logger.error(f"关闭WebSocket客户端失败: {e}")
        
        # 清理客户端引用
        self.rest_clients.clear()
        self.ws_clients.clear()
        
        logger.info("所有交易所客户端已关闭")
    
    def get_supported_exchanges(self) -> list:
        """获取支持的交易所列表"""
        return self.supported_exchanges.copy()
    
    def validate_exchange(self, exchange: str) -> bool:
        """验证交易所是否支持"""
        return exchange.lower() in self.supported_exchanges


# 全局交易所工厂实例
_global_exchange_factory = None

def get_exchange_factory() -> ExchangeFactory:
    """获取全局交易所工厂实例"""
    global _global_exchange_factory
    if _global_exchange_factory is None:
        _global_exchange_factory = ExchangeFactory()
    return _global_exchange_factory

def create_exchange_client(exchange: str, client_type: str = 'rest', 
                          api_key: str = None, api_secret: str = None,
                          passphrase: str = None, is_demo: bool = True):
    """
    创建交易所客户端的便捷函数
    
    Args:
        exchange: 交易所名称
        client_type: 客户端类型 ('rest' 或 'ws')
        api_key: API密钥
        api_secret: API密钥
        passphrase: 密码短语（仅OKX需要）
        is_demo: 是否使用演示模式
    
    Returns:
        交易所客户端实例
    """
    factory = get_exchange_factory()
    
    if client_type.lower() == 'rest':
        return factory.create_rest_client(exchange, api_key, api_secret, passphrase, is_demo)
    elif client_type.lower() == 'ws':
        return factory.create_ws_client(exchange, api_key, api_secret, is_demo)
    else:
        raise ValueError(f"不支持的客户端类型: {client_type}")

def get_exchange_client(exchange: str, client_type: str = 'rest', api_key: str = None):
    """
    获取已创建的交易所客户端的便捷函数
    
    Args:
        exchange: 交易所名称
        client_type: 客户端类型 ('rest' 或 'ws')
        api_key: API密钥
    
    Returns:
        交易所客户端实例或None
    """
    factory = get_exchange_factory()
    
    if client_type.lower() == 'rest':
        return factory.get_rest_client(exchange, api_key)
    elif client_type.lower() == 'ws':
        return factory.get_ws_client(exchange, api_key)
    else:
        raise ValueError(f"不支持的客户端类型: {client_type}") 