#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
USDT TRC20 支付监听器
通过轮询 TronGrid API 检查区块链交易
"""

import logging
import aiohttp
import asyncio
from datetime import datetime
from decimal import Decimal
from typing import Optional, Dict, Any

from core.payment.listeners.base_listener import BasePaymentListener

logger = logging.getLogger(__name__)


class USDTTRC20Listener(BasePaymentListener):
    """USDT TRC20 支付监听器"""
    
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.api_url = config.get('api_url', 'https://api.trongrid.io')
        self.usdt_contract = 'TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t'  # USDT TRC20 合约地址
    
    async def check_payment(
        self,
        order_no: str,
        payment_info: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """
        检查 USDT TRC20 支付
        
        通过 TronGrid API 查询收款地址的 TRC20 交易
        """
        try:
            receive_address = payment_info.get('address')
            expected_amount = Decimal(payment_info.get('amount', '0'))
            memo = payment_info.get('memo', '')
            
            if not receive_address:
                logger.error(f"订单 {order_no} 缺少收款地址")
                return None
            
            # 查询地址的 TRC20 交易
            url = f"{self.api_url}/v1/accounts/{receive_address}/transactions/trc20"
            params = {
                'limit': 50,
                'contract_address': self.usdt_contract,
                'only_confirmed': True
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params) as response:
                    if response.status != 200:
                        logger.error(f"查询 TronGrid API 失败: {response.status}")
                        return None
                    
                    data = await response.json()
                    transactions = data.get('data', [])
                    
                    # 查找匹配的交易
                    for tx in transactions:
                        # 检查交易方向（to 必须是收款地址）
                        if tx.get('to') != receive_address:
                            continue
                        
                        # 检查金额（考虑网络费用，允许略大于订单金额）
                        tx_amount = Decimal(str(tx.get('value', 0))) / Decimal('1000000')  # USDT 6位小数
                        if tx_amount < expected_amount * Decimal('0.99'):  # 允许1%误差
                            continue
                        
                        # 检查备注（如果有）
                        if memo and memo not in str(tx.get('memo', '')):
                            continue
                        
                        # 检查交易时间（应该在订单创建后）
                        tx_timestamp = tx.get('block_timestamp', 0)
                        # TODO: 验证交易时间在订单创建后
                        
                        # 找到匹配的交易
                        tx_hash = tx.get('transaction_id', '')
                        logger.info(f"找到匹配的USDT交易: order_no={order_no}, tx_hash={tx_hash}, amount={tx_amount}")
                        
                        return {
                            'tx_hash': tx_hash,
                            'amount': tx_amount,
                            'paid_at': datetime.fromtimestamp(tx_timestamp / 1000),
                            'proof': f"https://tronscan.org/#/transaction/{tx_hash}"
                        }
            
            return None
            
        except Exception as e:
            logger.error(f"检查USDT支付失败: {e}")
            return None
    
    def verify_payment(
        self,
        order_no: str,
        payment_data: Dict[str, Any]
    ) -> bool:
        """验证USDT支付信息"""
        try:
            # 检查交易哈希是否已处理（防重复）
            from database.global_db_manager import get_global_db_pool
            db_pool = get_global_db_pool()
            
            check_sql = """
                SELECT id FROM membership_payment_orders
                WHERE payment_tx_hash = %s AND status = 'paid'
            """
            result = db_pool.query(check_sql, (payment_data.get('tx_hash'),))
            if result:
                logger.warning(f"交易哈希已处理: {payment_data.get('tx_hash')}")
                return False
            
            # 验证金额
            order = self._get_order(order_no)
            if not order:
                return False
            
            expected_amount = Decimal(str(order['final_amount']))
            actual_amount = payment_data.get('amount', Decimal('0'))
            
            # 允许1%误差（考虑网络费用）
            if actual_amount < expected_amount * Decimal('0.99'):
                logger.warning(f"支付金额不足: expected={expected_amount}, actual={actual_amount}")
                return False
            
            return True
            
        except Exception as e:
            logger.error(f"验证USDT支付失败: {e}")
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

