#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Binance Pay 支付监听器
通过轮询 Binance Pay API 或接收 Webhook 检查支付状态
"""

import logging
import hmac
import hashlib
import json
import aiohttp
from datetime import datetime
from decimal import Decimal
from typing import Optional, Dict, Any

from core.payment.listeners.base_listener import BasePaymentListener

logger = logging.getLogger(__name__)


class BinancePayListener(BasePaymentListener):
    """Binance Pay 支付监听器"""
    
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.api_key = config.get('api_key')
        self.api_secret = config.get('api_secret')
        self.api_url = config.get('api_url', 'https://bpay.binanceapi.com')
    
    async def check_payment(
        self,
        order_no: str,
        payment_info: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """
        检查 Binance Pay 支付状态
        
        通过 Binance Pay 查询接口检查订单状态
        """
        try:
            # 构建查询请求
            timestamp = int(datetime.now().timestamp() * 1000)
            query_params = {
                'merchantId': self.api_key,
                'prepayId': order_no,  # 使用订单号作为 prepayId
                'timestamp': timestamp
            }
            
            # 生成签名
            query_string = '&'.join([f"{k}={v}" for k, v in sorted(query_params.items())])
            signature = hmac.new(
                self.api_secret.encode('utf-8'),
                query_string.encode('utf-8'),
                hashlib.sha256
            ).hexdigest()
            
            query_params['signature'] = signature
            
            # 发送查询请求
            url = f"{self.api_url}/binancepay/openapi/v2/order/query"
            headers = {
                'Content-Type': 'application/json',
                'BinancePay-Timestamp': str(timestamp),
                'BinancePay-Nonce': str(timestamp),
                'BinancePay-Certificate-SN': self.api_key
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=query_params, headers=headers) as response:
                    if response.status != 200:
                        logger.error(f"查询 Binance Pay API 失败: {response.status}")
                        return None
                    
                    data = await response.json()
                    
                    # 检查订单状态
                    if data.get('status') == 'SUCCESS' and data.get('data', {}).get('status') == 'PAID':
                        order_data = data.get('data', {})
                        return {
                            'tx_id': order_data.get('transactionId'),
                            'amount': Decimal(str(order_data.get('totalFee', '0'))),
                            'paid_at': datetime.fromtimestamp(order_data.get('transactionTime', 0) / 1000),
                            'proof': order_data.get('transactionId')
                        }
            
            return None
            
        except Exception as e:
            logger.error(f"检查Binance Pay支付失败: {e}")
            return None
    
    def verify_payment(
        self,
        order_no: str,
        payment_data: Dict[str, Any]
    ) -> bool:
        """验证 Binance Pay 支付信息"""
        try:
            # 验证签名（如果是从Webhook接收的）
            # TODO: 实现签名验证
            
            # 检查交易ID是否已处理（防重复）
            from database.global_db_manager import get_global_db_pool
            db_pool = get_global_db_pool()
            
            check_sql = """
                SELECT id FROM membership_payment_orders
                WHERE payment_tx_id = %s AND status = 'paid'
            """
            result = db_pool.query(check_sql, (payment_data.get('tx_id'),))
            if result:
                logger.warning(f"交易ID已处理: {payment_data.get('tx_id')}")
                return False
            
            # 验证金额
            order = self._get_order(order_no)
            if not order:
                return False
            
            expected_amount = Decimal(str(order['final_amount']))
            actual_amount = payment_data.get('amount', Decimal('0'))
            
            if actual_amount != expected_amount:
                logger.warning(f"支付金额不匹配: expected={expected_amount}, actual={actual_amount}")
                return False
            
            return True
            
        except Exception as e:
            logger.error(f"验证Binance Pay支付失败: {e}")
            return False
    
    def verify_webhook_signature(self, payload: str, signature: str) -> bool:
        """验证 Webhook 签名"""
        try:
            expected_signature = hmac.new(
                self.api_secret.encode('utf-8'),
                payload.encode('utf-8'),
                hashlib.sha256
            ).hexdigest()
            
            return hmac.compare_digest(expected_signature, signature)
        except Exception as e:
            logger.error(f"验证Webhook签名失败: {e}")
            return False
    
    def _get_order(self, order_no: str) -> Optional[Dict[str, Any]]:
        """获取订单信息"""
        from database.global_db_manager import get_global_db_pool
        db_pool = get_global_db_pool()
        
        sql = "SELECT * FROM membership_payment_orders WHERE order_no = %s"
        result = db_pool.query(sql, (order_no,))
        if result:
            return dict(result[0])
        return None

