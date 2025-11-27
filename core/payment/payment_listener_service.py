#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
支付监听服务
后台定时任务，轮询检查待支付订单
"""

import logging
import asyncio
from datetime import datetime, timedelta
from typing import Dict, Any, Optional

from database.global_db_manager import get_global_db_pool
from core.payment.order_service import PaymentOrderService
from core.payment.listeners.usdt_listener import USDTTRC20Listener
from core.payment.listeners.alipay_listener import AlipayListener
from core.payment.listeners.binance_listener import BinancePayListener
from core.membership.membership_service import MembershipService

logger = logging.getLogger(__name__)


class PaymentListenerService:
    """支付监听服务"""
    
    def __init__(self):
        self.db_pool = get_global_db_pool()
        self.order_service = PaymentOrderService()
        self.membership_service = MembershipService()
        
        # 初始化监听器
        from config.config import PAYMENT_CONFIG
        self.listeners = {
            'usdt_trc20': USDTTRC20Listener(PAYMENT_CONFIG.get('usdt_trc20', {})),
            'alipay': AlipayListener(PAYMENT_CONFIG.get('alipay', {})),
            'binance': BinancePayListener(PAYMENT_CONFIG.get('binance', {}))
        }
        
        self._running = False
        self._task = None
    
    async def start(self):
        """启动支付监听服务"""
        if self._running:
            logger.warning("支付监听服务已在运行")
            return
        
        self._running = True
        logger.info("支付监听服务已启动")
        
        # 启动监听循环
        self._task = asyncio.create_task(self._listener_loop())
    
    async def stop(self):
        """停止支付监听服务"""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("支付监听服务已停止")
    
    async def _listener_loop(self):
        """监听循环"""
        while self._running:
            try:
                # 获取所有待支付的订单
                pending_orders = self._get_pending_orders()
                
                for order in pending_orders:
                    try:
                        await self._check_order_payment(order)
                    except Exception as e:
                        logger.error(f"检查订单支付失败: order_no={order['order_no']}, error={e}")
                
                # 清理过期订单
                self._cleanup_expired_orders()
                
                # 等待下次轮询
                await asyncio.sleep(30)  # 30秒轮询一次
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"支付监听循环错误: {e}")
                await asyncio.sleep(30)
    
    def _get_pending_orders(self) -> list:
        """获取待支付订单"""
        sql = """
            SELECT * FROM membership_payment_orders
            WHERE status = 'pending'
            AND (expires_at IS NULL OR expires_at > NOW())
            ORDER BY created_at ASC
            LIMIT 50
        """
        result = self.db_pool.query(sql)
        return [dict(row) for row in result] if result else []
    
    async def _check_order_payment(self, order: Dict[str, Any]):
        """检查订单支付状态"""
        order_no = order['order_no']
        payment_method = order['payment_method']
        
        # 获取对应的监听器
        listener = self.listeners.get(payment_method)
        if not listener or not listener.enabled:
            return
        
        # 构建支付信息
        payment_info = {
            'address': order.get('payment_tx_hash'),  # 对于USDT，这是收款地址
            'amount': str(order['final_amount']),
            'memo': order_no
        }
        
        # 检查支付
        try:
            if payment_method == 'usdt_trc20':
                payment_data = await listener.check_payment(order_no, payment_info)
            elif payment_method == 'alipay':
                payment_data = listener.check_payment(order_no, payment_info)
            elif payment_method == 'binance':
                payment_data = await listener.check_payment(order_no, payment_info)
            else:
                return
            
            # 如果检测到支付
            if payment_data:
                # 验证支付
                if listener.verify_payment(order_no, payment_data):
                    # 更新订单状态
                    self.order_service.update_order_status(
                        order_no=order_no,
                        status='paid',
                        payment_tx_hash=payment_data.get('tx_hash'),
                        payment_tx_id=payment_data.get('tx_id'),
                        payment_proof=payment_data.get('proof'),
                        callback_data=payment_data
                    )
                    
                    # 激活/续费会员
                    await self._activate_membership(order)
                    
                    # 记录日志
                    self._log_listener_action(
                        order_no, payment_method, 'payment_confirmed', 'success',
                        f"支付确认成功: {payment_data.get('tx_hash') or payment_data.get('tx_id')}"
                    )
                    
                    logger.info(f"订单支付成功: order_no={order_no}")
                else:
                    logger.warning(f"订单支付验证失败: order_no={order_no}")
                    self._log_listener_action(
                        order_no, payment_method, 'payment_verification_failed', 'failed',
                        "支付验证失败"
                    )
        
        except Exception as e:
            logger.error(f"检查订单支付异常: order_no={order_no}, error={e}")
            self._log_listener_action(
                order_no, payment_method, 'check_payment_error', 'failed',
                str(e)
            )
    
    async def _activate_membership(self, order: Dict[str, Any]):
        """激活/续费会员"""
        try:
            user_id = order['user_id']
            level_id = order['membership_level_id']
            billing_period = order['billing_period']
            order_type = order['order_type']
            
            # 计算到期时间
            from datetime import datetime, timedelta
            if billing_period == 'monthly':
                expires_at = datetime.now() + timedelta(days=30)
            elif billing_period == 'yearly':
                expires_at = datetime.now() + timedelta(days=365)
            else:
                expires_at = None
            
            # 激活或续费会员
            if order_type == 'subscribe':
                # 订阅（升级）
                self.membership_service.activate_membership(
                    user_id=user_id,
                    level_id=level_id,
                    expires_at=expires_at
                )
            elif order_type == 'renew':
                # 续费
                self.membership_service.renew_membership(
                    user_id=user_id,
                    billing_period=billing_period,
                    auto_renew=False
                )
            
            logger.info(f"会员激活/续费成功: user_id={user_id}, level_id={level_id}")
            
        except Exception as e:
            logger.error(f"激活/续费会员失败: {e}")
            raise
    
    def _cleanup_expired_orders(self):
        """清理过期订单"""
        try:
            sql = """
                UPDATE membership_payment_orders
                SET status = 'expired'
                WHERE status = 'pending'
                AND expires_at IS NOT NULL
                AND expires_at < NOW()
            """
            self.db_pool.execute(sql)
        except Exception as e:
            logger.error(f"清理过期订单失败: {e}")
    
    def _log_listener_action(
        self,
        order_no: str,
        listener_type: str,
        action: str,
        status: str,
        message: str,
        data: Optional[Dict] = None
    ):
        """记录监听日志"""
        try:
            import json
            sql = """
                INSERT INTO payment_listener_logs
                (order_no, listener_type, action, status, message, data)
                VALUES (%s, %s, %s, %s, %s, %s)
            """
            self.db_pool.execute(sql, (
                order_no, listener_type, action, status, message,
                json.dumps(data) if data else None
            ))
        except Exception as e:
            logger.error(f"记录监听日志失败: {e}")

