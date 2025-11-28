#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
支付订单服务
负责创建、查询、更新支付订单
"""

import uuid
import logging
import random
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from decimal import Decimal

from database.global_db_manager import get_global_db_pool

logger = logging.getLogger(__name__)


class PaymentOrderService:
    """支付订单服务"""
    
    def __init__(self):
        self.db_pool = get_global_db_pool()
    
    def generate_order_no(self) -> str:
        """生成唯一订单号"""
        # 格式: PAY + 时间戳 + 随机字符串
        timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
        random_str = str(uuid.uuid4()).replace('-', '')[:8].upper()
        return f"PAY{timestamp}{random_str}"
    
    def create_order(
        self,
        user_id: int,
        membership_level_id: int,
        order_type: str,  # 'subscribe' 或 'renew'
        billing_period: str,  # 'monthly' 或 'yearly'
        original_amount: Decimal,
        payment_method: str,  # 'usdt_trc20', 'alipay', 'binance'
        discount_code: Optional[str] = None,
        discount_amount: Decimal = Decimal('0.00')
    ) -> Dict[str, Any]:
        """
        创建支付订单
        
        Returns:
            {
                'order_no': str,
                'payment_info': dict,  # 支付信息（地址/二维码/链接等）
                'expires_at': datetime
            }
        """
        try:
            # 生成订单号
            order_no = self.generate_order_no()
            
            # 计算最终金额
            final_amount = original_amount - discount_amount
            if final_amount < 0:
                final_amount = Decimal('0.00')
            
            # 根据支付方式计算实际支付金额和币种
            payment_amount, payment_currency = self._calculate_payment_amount(
                payment_method, final_amount
            )
            
            # 设置订单过期时间（15分钟）
            expires_at = datetime.now() + timedelta(minutes=15)
            
            # 插入订单
            insert_sql = """
                INSERT INTO membership_payment_orders
                (order_no, user_id, membership_level_id, order_type, billing_period,
                 original_amount, discount_amount, final_amount, payment_method,
                 payment_amount, payment_currency, discount_code, status, expires_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'pending', %s)
            """
            self.db_pool.execute(insert_sql, (
                order_no, user_id, membership_level_id, order_type, billing_period,
                original_amount, discount_amount, final_amount, payment_method,
                payment_amount, payment_currency, discount_code, expires_at
            ))
            
            # 获取支付信息（根据支付方式生成）
            payment_info = self._generate_payment_info(
                order_no, payment_method, payment_amount, payment_currency
            )
            
            logger.info(f"创建支付订单成功: order_no={order_no}, user_id={user_id}, amount={final_amount}")
            
            return {
                'order_no': order_no,
                'payment_info': payment_info,
                'expires_at': expires_at.isoformat()
            }
            
        except Exception as e:
            logger.error(f"创建支付订单失败: {e}")
            raise
    
    def get_order(self, order_no: str) -> Optional[Dict[str, Any]]:
        """获取订单信息"""
        try:
            sql = """
                SELECT * FROM membership_payment_orders
                WHERE order_no = %s
            """
            result = self.db_pool.query(sql, (order_no,))
            if result:
                return dict(result[0])
            return None
        except Exception as e:
            logger.error(f"获取订单失败: {e}")
            return None
    
    def update_order_status(
        self,
        order_no: str,
        status: str,
        payment_tx_hash: Optional[str] = None,
        payment_tx_id: Optional[str] = None,
        payment_proof: Optional[str] = None,
        callback_data: Optional[Dict] = None
    ) -> bool:
        """更新订单状态"""
        try:
            update_fields = ['status = %s']
            params = [status]
            
            if payment_tx_hash:
                update_fields.append('payment_tx_hash = %s')
                params.append(payment_tx_hash)
            
            if payment_tx_id:
                update_fields.append('payment_tx_id = %s')
                params.append(payment_tx_id)
            
            if payment_proof:
                update_fields.append('payment_proof = %s')
                params.append(payment_proof)
            
            if callback_data:
                import json
                update_fields.append('callback_data = %s')
                params.append(json.dumps(callback_data))
            
            if status == 'paid':
                update_fields.append('paid_at = NOW()')
            
            params.append(order_no)
            
            sql = f"""
                UPDATE membership_payment_orders
                SET {', '.join(update_fields)}, updated_at = NOW()
                WHERE order_no = %s
            """
            self.db_pool.execute(sql, tuple(params))
            
            logger.info(f"更新订单状态成功: order_no={order_no}, status={status}")
            return True
            
        except Exception as e:
            logger.error(f"更新订单状态失败: {e}")
            return False
    
    def _calculate_payment_amount(
        self,
        payment_method: str,
        amount_usd: Decimal
    ) -> tuple:
        """计算实际支付金额和币种"""
        if payment_method == 'alipay':
            # 转换为人民币（汇率从配置获取，默认7.2）
            from config.config import PAYMENT_CONFIG
            exchange_rate = PAYMENT_CONFIG.get('exchange_rate', {}).get('usd_to_cny', 7.2)
            amount_cny = amount_usd * Decimal(str(exchange_rate))
            return amount_cny, 'CNY'
        else:
            return amount_usd, 'USD'
    
    def _generate_payment_info(
        self,
        order_no: str,
        payment_method: str,
        payment_amount: Decimal,
        payment_currency: str
    ) -> Dict[str, Any]:
        """生成支付信息（地址/二维码/链接）"""
        from config.config import PAYMENT_CONFIG
        
        if payment_method == 'usdt_trc20':
            # USDT TRC20: 从地址池随机选择收款地址
            config = PAYMENT_CONFIG.get('usdt_trc20', {})
            
            # 优先使用地址池，如果地址池为空则使用单个地址（向后兼容）
            address_pool = config.get('address_pool', [])
            if address_pool and len(address_pool) > 0:
                # 从地址池中随机选择一个地址
                receive_address = random.choice(address_pool)
                logger.info(f"从地址池随机选择地址: {receive_address} (订单: {order_no}, 地址池大小: {len(address_pool)})")
            else:
                # 使用单个地址（向后兼容）
                receive_address = config.get('receive_address', '')
                if not receive_address:
                    raise ValueError("USDT TRC20 收款地址未配置，请配置 receive_address 或 address_pool")
                logger.info(f"使用单个收款地址: {receive_address} (订单: {order_no})")
            
            return {
                'type': 'address',
                'address': receive_address,
                'amount': str(payment_amount),
                'currency': payment_currency,
                'memo': order_no,  # 备注订单号
                'network': 'TRC20'
            }
        
        elif payment_method == 'alipay':
            # 支付宝: 调用支付宝API创建订单，返回二维码
            # TODO: 集成支付宝SDK
            return {
                'type': 'qrcode',
                'qrcode_url': f'https://your-domain.com/payment/qrcode/{order_no}',
                'amount': str(payment_amount),
                'currency': payment_currency
            }
        
        elif payment_method == 'binance':
            # Binance Pay: 调用Binance Pay API创建订单，返回支付链接
            # TODO: 集成Binance Pay API
            return {
                'type': 'link',
                'payment_url': f'https://your-domain.com/payment/binance/{order_no}',
                'amount': str(payment_amount),
                'currency': payment_currency
            }
        
        else:
            raise ValueError(f"不支持的支付方式: {payment_method}")

