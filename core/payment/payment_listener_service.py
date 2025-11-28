#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
支付监听服务
按订单启动/停止监听，支持地址池模式
"""

import logging
import asyncio
from datetime import datetime, timedelta
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

from database.global_db_manager import get_global_db_pool
from core.payment.order_service import PaymentOrderService
from core.payment.listeners.usdt_listener import USDTTRC20Listener
from core.membership.membership_service import MembershipService

# 可选导入：支付宝和Binance Pay监听器（如果不存在则使用占位符）
try:
    from core.payment.listeners.alipay_listener import AlipayListener
except ImportError:
    logger.warning("支付宝监听器模块不存在，将使用占位符")
    AlipayListener = None

try:
    from core.payment.listeners.binance_listener import BinancePayListener
except ImportError:
    logger.warning("Binance Pay监听器模块不存在，将使用占位符")
    BinancePayListener = None


class PaymentListenerService:
    """支付监听服务（按订单启动/停止）"""
    
    def __init__(self):
        self.db_pool = get_global_db_pool()
        self.order_service = PaymentOrderService()
        self.membership_service = MembershipService()
        
        # 初始化监听器
        from config.config import PAYMENT_CONFIG
        self.listeners = {
            'usdt_trc20': USDTTRC20Listener(PAYMENT_CONFIG.get('usdt_trc20', {}))
        }
        
        # 可选监听器：如果模块存在则初始化
        if AlipayListener is not None:
            try:
                self.listeners['alipay'] = AlipayListener(PAYMENT_CONFIG.get('alipay', {}))
            except Exception as e:
                logger.warning(f"初始化支付宝监听器失败: {e}")
        
        if BinancePayListener is not None:
            try:
                self.listeners['binance'] = BinancePayListener(PAYMENT_CONFIG.get('binance', {}))
            except Exception as e:
                logger.warning(f"初始化Binance Pay监听器失败: {e}")
        
        # 订单监听任务：order_no -> asyncio.Task
        self._order_tasks: Dict[str, asyncio.Task] = {}
        
        # 全局事件循环（用于创建任务）
        self._loop = None
    
    async def start_order_listening(self, order_no: str, payment_info: Dict[str, Any]):
        """
        为指定订单启动监听
        
        Args:
            order_no: 订单号
            payment_info: 支付信息（包含地址等）
        """
        if order_no in self._order_tasks:
            logger.warning(f"订单 {order_no} 的监听任务已存在")
            return
        
        # 获取订单信息
        order = self.order_service.get_order(order_no)
        if not order:
            logger.error(f"订单不存在: {order_no}")
            return
        
        if order['status'] != 'pending':
            logger.warning(f"订单状态不是 pending，不启动监听: order_no={order_no}, status={order['status']}")
            return
        
        # 创建监听任务（使用当前事件循环）
        loop = asyncio.get_event_loop()
        task = loop.create_task(self._listen_order(order_no, payment_info))
        self._order_tasks[order_no] = task
        
        logger.info(f"已为订单 {order_no} 启动支付监听")
    
    async def stop_order_listening(self, order_no: str):
        """
        停止指定订单的监听
        
        Args:
            order_no: 订单号
        """
        if order_no not in self._order_tasks:
            return
        
        task = self._order_tasks[order_no]
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        
        del self._order_tasks[order_no]
        logger.info(f"已停止订单 {order_no} 的支付监听")
    
    async def _listen_order(self, order_no: str, payment_info: Dict[str, Any]):
        """
        监听单个订单的支付状态
        
        Args:
            order_no: 订单号
            payment_info: 支付信息
        """
        try:
            # 获取订单信息
            order = self.order_service.get_order(order_no)
            if not order:
                logger.error(f"订单不存在: {order_no}")
                return
            
            payment_method = order['payment_method']
            listener = self.listeners.get(payment_method)
            
            if not listener or not listener.enabled:
                logger.warning(f"支付方式 {payment_method} 的监听器未启用")
                return
            
            # 获取轮询间隔
            poll_interval = listener.poll_interval
            
            # 开始轮询
            while True:
                try:
                    # 检查订单状态（可能已被其他进程更新）
                    order = self.order_service.get_order(order_no)
                    if not order:
                        logger.warning(f"订单不存在，停止监听: {order_no}")
                        break
                    
                    # 如果订单已完成或过期，停止监听
                    if order['status'] in ('paid', 'expired', 'cancelled', 'failed'):
                        logger.info(f"订单状态为 {order['status']}，停止监听: {order_no}")
                        break
                    
                    # 检查订单是否过期
                    if order.get('expires_at'):
                        expires_at = order['expires_at']
                        if isinstance(expires_at, str):
                            expires_at = datetime.fromisoformat(expires_at.replace('Z', '+00:00'))
                        if expires_at < datetime.now():
                            logger.info(f"订单已过期，停止监听: {order_no}")
                            # 更新订单状态为过期
                            self.order_service.update_order_status(order_no, 'expired')
                            break
                    
                    # 检查支付
                    await self._check_order_payment(order, payment_info)
                    
                    # 等待下次轮询
                    await asyncio.sleep(poll_interval)
                    
                except asyncio.CancelledError:
                    logger.info(f"订单 {order_no} 的监听任务被取消")
                    break
                except Exception as e:
                    logger.error(f"监听订单 {order_no} 时出错: {e}")
                    await asyncio.sleep(poll_interval)
        
        finally:
            # 清理任务
            if order_no in self._order_tasks:
                del self._order_tasks[order_no]
    
    async def _check_order_payment(self, order: Dict[str, Any], payment_info: Dict[str, Any]):
        """检查订单支付状态"""
        order_no = order['order_no']
        payment_method = order['payment_method']
        
        # 获取对应的监听器
        listener = self.listeners.get(payment_method)
        if not listener or not listener.enabled:
            return
        
        # 使用传入的 payment_info，补充订单号和金额信息
        # 添加订单创建时间，用于过滤订单创建前的交易
        order_created_at = order.get('created_at')
        check_payment_info = {
            'address': payment_info.get('address'),
            'amount': str(order['final_amount']),
            'memo': order_no,
            'order_created_at': order_created_at  # 订单创建时间，用于过滤历史交易
        }
        
        # 检查支付
        try:
            if payment_method == 'usdt_trc20':
                payment_data = await listener.check_payment(order_no, check_payment_info)
            elif payment_method == 'alipay':
                # 支付宝监听器可能是同步的
                if hasattr(listener, 'check_payment') and not asyncio.iscoroutinefunction(listener.check_payment):
                    payment_data = listener.check_payment(order_no, check_payment_info)
                else:
                    payment_data = await listener.check_payment(order_no, check_payment_info)
            elif payment_method == 'binance':
                payment_data = await listener.check_payment(order_no, check_payment_info)
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
                    
                    # 停止监听（订单已完成）
                    await self.stop_order_listening(order_no)
                    
                    # 记录日志
                    self._log_listener_action(
                        order_no, payment_method, 'payment_confirmed', 'success',
                        f"支付确认成功: {payment_data.get('tx_hash') or payment_data.get('tx_id')}"
                    )
                    
                    logger.info(f"订单支付成功: order_no={order_no}")
                else:
                    # 金额不匹配或其他验证失败，继续监听直到15分钟结束
                    logger.warning(f"订单支付验证失败（金额不匹配或其他原因），继续监听: order_no={order_no}")
                    self._log_listener_action(
                        order_no, payment_method, 'payment_verification_failed', 'failed',
                        "支付验证失败（金额不匹配），继续监听"
                    )
                    # 不停止监听，继续轮询直到15分钟结束
        
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

