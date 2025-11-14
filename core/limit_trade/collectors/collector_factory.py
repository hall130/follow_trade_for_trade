#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
带单员数据采集器工厂
根据配置创建不同类型的采集器实例
"""

from typing import Dict, Optional, Any
from utils.logger import logger
from .base_collector import BaseTraderCollector
from .okx_collector import OKXTraderCollector
from .binance_collector import BinanceTraderCollector
from .hyperliquid_trader_collector import HyperliquidTraderCollector


class TraderCollectorFactory:
    """带单员数据采集器工厂"""
    
    # 注册的采集器类型
    _collectors = {
        'okx': OKXTraderCollector,
        'binance': BinanceTraderCollector,
        'hyperliquid': HyperliquidTraderCollector,
    }
    
    @classmethod
    def create_collector(
        cls, 
        collector_type: str, 
        config: Optional[Dict[str, Any]] = None
    ) -> Optional[BaseTraderCollector]:
        """
        创建采集器实例
        
        Args:
            collector_type: 采集器类型 ('okx', 'binance' 等)
            config: 采集器配置字典
            
        Returns:
            采集器实例，如果类型不支持则返回None
        """
        collector_type = collector_type.lower().strip()
        
        if collector_type not in cls._collectors:
            logger.error(f"不支持的采集器类型: {collector_type}, 支持的类型: {list(cls._collectors.keys())}")
            return None
        
        try:
            collector_class = cls._collectors[collector_type]
            collector = collector_class(config)
            logger.info(f"创建{collector_type}采集器成功")
            return collector
        except Exception as e:
            logger.error(f"创建{collector_type}采集器失败: {e}")
            return None
    
    @classmethod
    def register_collector(cls, collector_type: str, collector_class: type):
        """
        注册新的采集器类型（用于扩展）
        
        Args:
            collector_type: 采集器类型标识
            collector_class: 采集器类（必须继承自BaseTraderCollector）
        """
        if not issubclass(collector_class, BaseTraderCollector):
            raise ValueError(f"采集器类必须继承自BaseTraderCollector")
        
        cls._collectors[collector_type.lower()] = collector_class
        logger.info(f"注册新的采集器类型: {collector_type}")
    
    @classmethod
    def get_supported_types(cls) -> list:
        """
        获取支持的采集器类型列表
        
        Returns:
            支持的采集器类型列表
        """
        return list(cls._collectors.keys())
    
    @classmethod
    def get_collector_for_trader(
        cls,
        trader_config: Dict[str, Any]
    ) -> Optional[BaseTraderCollector]:
        """
        根据带单员配置创建对应的采集器
        
        Args:
            trader_config: 带单员配置字典，应包含：
                - collector_type: 采集器类型 ('okx', 'binance' 等)
                - collector_config: 采集器特定配置（可选）
                
        Returns:
            采集器实例
        """
        collector_type = trader_config.get('collector_type', 'okx')  # 默认使用OKX
        collector_config = trader_config.get('collector_config', {})
        
        return cls.create_collector(collector_type, collector_config)

