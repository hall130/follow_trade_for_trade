#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
支付监听器基类
"""

import logging
from abc import ABC, abstractmethod
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)


class BasePaymentListener(ABC):
    """支付监听器基类"""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.enabled = config.get('enabled', True)
        self.poll_interval = config.get('poll_interval', 30)  # 轮询间隔（秒）
    
    @abstractmethod
    def check_payment(self, order_no: str, payment_info: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        检查支付状态
        
        Args:
            order_no: 订单号
            payment_info: 支付信息（地址/二维码/链接等）
        
        Returns:
            如果支付成功，返回支付信息字典，包含：
            {
                'tx_hash': str,  # 交易哈希/ID
                'amount': Decimal,  # 实际支付金额
                'paid_at': datetime,  # 支付时间
                'proof': str  # 支付凭证
            }
            如果未支付，返回 None
        """
        pass
    
    @abstractmethod
    def verify_payment(self, order_no: str, payment_data: Dict[str, Any]) -> bool:
        """
        验证支付信息
        
        Args:
            order_no: 订单号
            payment_data: 支付数据
        
        Returns:
            True 如果验证通过，False 否则
        """
        pass

