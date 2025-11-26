#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
限价跟单核心服务模块
增强版本 - 包含WebSocket监听、定时同步、健康检查等功能
"""

import asyncio
import time
import json
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from concurrent.futures import ThreadPoolExecutor
import threading
from config.contract_config import get_contract_tick_sz_from_usdt_value, get_contract_min_sz, get_contract_tick_sz, get_contract_multiplier, get_contract_sz_precision, get_contract_value_in_usdt, get_contract_sz_from_usdt_value
from exchange.exchange_factory import create_exchange_client
from exchange.base_client import ExchangeType
from utils.logger import logger
from core.limit_trade.limit_follow_db import LimitFollowDB
from core.limit_trade.limit_follow_models import LimitFollowOrder, LimitFollowStrategy, FollowOrderRequest, FollowOrderResponse
from core.limit_trade.limit_follow_monitor_config import (
    get_monitor_config, MonitorStatus, MonitorMetrics, OrderSyncResult
)
from core.market_trade.trade_service import get_global_is_demo, make_clOrdId
from database.global_db_manager import get_global_db_pool

class EnhancedLimitFollowService:
    """增强的限价跟单服务"""
    
    def __init__(self, db_pool=None):
        """初始化服务"""
        # 基础配置
        self.config = get_monitor_config()
        
        # 初始化数据库连接 - 使用全局连接池
        if db_pool is None:
            
            db_pool = get_global_db_pool()
            logger.info("🎯 限价跟单服务使用全局数据库连接池")
        
        self.db = LimitFollowDB(db_pool)
        self.db_pool = db_pool
        
        # 运行状态
        self.running = False
        self.monitor_task = None
        self.health_check_task = None
        
        # 监控指标
        self.metrics = MonitorMetrics()
        self.metrics.uptime_start = datetime.now()
        
        # WebSocket更新通过信号服务处理
        self.websocket_enabled = self.config['enable_websocket_updates']
        
        # 线程池用于并发处理
        self.executor = ThreadPoolExecutor(max_workers=self.config['max_concurrent_checks'])
        
        # 状态锁
        self.status_lock = threading.Lock()
        self.current_status = MonitorStatus.STOPPED
        
        logger.info("✅ 增强限价跟单服务初始化完成")

    # ==================== 主要监控方法 ====================
    
    async def start_monitoring(self):
        """启动监控服务"""
        try:
            if self.running:
                logger.warning("监控服务已在运行中")
                return
            
            logger.info("🚀 启动增强限价跟单监控服务...")
            
            self.running = True
            self._set_status(MonitorStatus.HEALTHY)
            
            # 启动主监控循环
            self.monitor_task = asyncio.create_task(self._enhanced_monitor_loop())
            
            # 启动健康检查
            self.health_check_task = asyncio.create_task(self._health_check_loop())
            
            # WebSocket监听通过现有的信号服务处理，不需要单独启动
            
            logger.info("✅ 增强限价跟单监控服务启动成功")
            
            # 等待所有任务完成
            await asyncio.gather(
                self.monitor_task,
                self.health_check_task
            )
                
        except Exception as e:
            logger.error(f"启动监控服务失败: {e}")
            self._set_status(MonitorStatus.ERROR)
            raise
    
    def stop_monitoring(self):
        """停止监控服务"""
        try:
            logger.info("🛑 停止限价跟单监控服务...")
            
            self.running = False
            self._set_status(MonitorStatus.STOPPED)
            
            # 取消所有任务
            for task in [self.monitor_task, self.health_check_task]:
                if task and not task.done():
                    task.cancel()
            
            # 关闭线程池
            if self.executor:
                self.executor.shutdown(wait=True)
            
            logger.info("✅ 限价跟单监控服务已停止")
                
        except Exception as e:
            logger.error(f"停止监控服务失败: {e}")

    async def _enhanced_monitor_loop(self):
        """增强的监控循环"""
        check_interval = self.config['check_interval']
        status_sync_interval = self.config['status_sync_interval']
        last_full_sync = 0
        
        logger.info(f"📊 监控循环启动 - 检查间隔: {check_interval}秒, 同步间隔: {status_sync_interval}秒")
        
        while self.running:
            try:
                loop_start_time = time.time()
                current_time = time.time()
                
                # 1. 检查待处理订单
                await self._check_pending_orders_enhanced()
                
                # 2. 检查活跃订单状态
                await self._check_live_orders_enhanced()
                
                # 3. 定期执行完整状态同步
                if current_time - last_full_sync > status_sync_interval:
                    await self._full_status_sync()
                    last_full_sync = current_time
                    self.metrics.record_sync_cycle()
                
                # 4. 自动修复异常订单（如果启用）
                if self.config['enable_auto_repair']:
                    await self._auto_repair_orders()
                
                # 5. 检查并修复订单与持仓状态不一致的问题
                await self._check_position_status_consistency()
                
                # 5. 记录性能指标
                loop_duration = time.time() - loop_start_time
                if self.config['log_performance_metrics']:
                    logger.debug(f"📈 监控循环耗时: {loop_duration:.2f}秒")
                
                # 等待下次检查
                await asyncio.sleep(check_interval)
                
            except asyncio.CancelledError:
                logger.info("监控循环被取消")
                break
            except Exception as e:
                logger.error(f"监控循环异常: {e}")
                self.metrics.record_error()
                
                # 检查连续失败次数
                if self.metrics.consecutive_failures >= self.config['max_consecutive_failures']:
                    logger.error(f"连续失败次数过多({self.metrics.consecutive_failures})，设置为警告状态")
                    self._set_status(MonitorStatus.WARNING)
                
                await asyncio.sleep(check_interval)

    async def _check_pending_orders_enhanced(self):
        """增强的待处理订单检查"""
        try:
            pending_orders = self.db.get_pending_orders()
            
            if not pending_orders:
                return
            
            logger.debug(f"🔍 检查 {len(pending_orders)} 个待处理订单")
            
            # 并发处理订单
            tasks = []
            for order in pending_orders[:self.config['batch_sync_size']]:  # 限制批量大小
                if order.status == 'pending':
                    tasks.append(self._submit_order_to_exchange_enhanced(order))
                elif order.status == 'live':
                    tasks.append(self._check_order_status_enhanced(order))
            
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)
                
        except Exception as e:
            logger.error(f"检查待处理订单失败: {e}")
            self.metrics.record_error()

    async def _check_live_orders_enhanced(self):
        """增强的活跃订单检查"""
        try:
            # 只查询限价单，跳过市价单（市价单应该直接为filled状态）
            live_orders = self.db.get_orders({'status': 'live', 'order_type': 'limit'})
            
            if not live_orders:
                return
            
            logger.debug(f"🔍 检查 {len(live_orders)} 个活跃限价订单")
            
            # 分批处理，避免API限制
            batch_size = self.config['batch_sync_size']
            for i in range(0, len(live_orders), batch_size):
                batch = live_orders[i:i + batch_size]
                
                tasks = [self._check_order_status_enhanced(order) for order in batch]
                await asyncio.gather(*tasks, return_exceptions=True)
                
                # API调用间隔
                if i + batch_size < len(live_orders):
                    await asyncio.sleep(self.config['api_rate_limit_delay'])
                
        except Exception as e:
            logger.error(f"检查活跃订单失败: {e}")
            self.metrics.record_error()

    async def _check_order_status_enhanced(self, order: LimitFollowOrder):
        """增强的订单状态检查"""
        try:
            self.metrics.record_api_call()
            
            # 获取客户API信息
            customer = await self._get_customer_info(order.customer_uid)
            if not customer:
                logger.error(f"获取客户信息失败: {order.customer_uid}")
                self.metrics.record_api_call(success=False)
                return
            
            # 创建统一交易所客户端
            customer_data = {
                'api_key': customer['api_key'],
                'api_secret': customer.get('secret_key') or customer.get('api_secret'),
                'passphrase': customer['passphrase'],
                'is_demo': get_global_is_demo(),
                'exchange': customer.get('exchange', 'okx')
            }
            exchange_client = create_exchange_client(
                exchange=customer_data['exchange'],
                client_type='rest',
                api_key=customer_data['api_key'],
                api_secret=customer_data['api_secret'],
                passphrase=customer_data['passphrase'],
                is_demo=customer_data['is_demo']
            )
            
            # 添加重试机制处理50011错误
            max_retries = 3
            retry_delay = 2.0
            
            for attempt in range(max_retries):
                try:
                    # 查询订单状态（支持多交易所）
                    response = await exchange_client.get_order(order.symbol, order.exchange_order_id)
                    
                    # 处理不同交易所的响应格式
                    order_data = None
                    exchange_status = None
                    exchange_type = customer_data['exchange'].lower()
                    
                    if exchange_type == 'okx':
                        # OKX格式：{'code': '0', 'data': [{...}]}
                        if response and response.get('code') == '0' and response.get('data'):
                            order_data = response['data'][0]
                            exchange_status = order_data.get('state')
                    else:
                        # 其他交易所：可能是统一格式或自定义格式
                        if isinstance(response, dict):
                            if 'data' in response:
                                order_data = response['data'][0] if isinstance(response['data'], list) else response['data']
                            elif 'order' in response:
                                order_data = response['order']
                            else:
                                order_data = response
                            
                            # 尝试多种状态字段名
                            exchange_status = order_data.get('state') or order_data.get('status') or order_data.get('order_status')
                        elif hasattr(response, 'status'):
                            # 统一接口返回OrderResponse对象
                            exchange_status = response.status.value if hasattr(response.status, 'value') else str(response.status)
                    
                    if order_data and exchange_status:
                        
                        # 如果状态有变化，更新数据库
                        if exchange_status != order.status:
                            await self._update_order_status_from_exchange(order, order_data)
                            self.metrics.record_order_check(success=True)
                            
                            if self.config['log_order_updates']:
                                logger.info(f"订单状态更新: {order.order_uid} {order.status} -> {exchange_status}")
                        else:
                            self.metrics.record_order_check(success=True)
                        
                        # 成功获取状态，跳出重试循环
                        break
                        
                    elif isinstance(response, dict) and response.get('code') == '50011':
                        # 处理Too Many Requests错误
                        if attempt < max_retries - 1:
                            wait_time = retry_delay * (2 ** attempt)  # 指数退避
                            logger.warning(f"API请求频率过高，{wait_time}秒后重试 (第{attempt + 1}次): {order.order_uid}")
                            await asyncio.sleep(wait_time)
                            continue
                        else:
                            logger.error(f"API请求频率过高，重试次数已用完: {order.order_uid}")
                            self.metrics.record_api_call(success=False)
                            self.metrics.record_order_check(success=False)
                            break
                    else:
                        logger.warning(f"查询订单状态失败: {order.order_uid} - {response}")
                        self.metrics.record_api_call(success=False)
                        self.metrics.record_order_check(success=False)
                        break
                        
                except Exception as e:
                    if attempt < max_retries - 1:
                        wait_time = retry_delay * (2 ** attempt)
                        logger.warning(f"查询订单状态异常，{wait_time}秒后重试: {order.order_uid} - {e}")
                        await asyncio.sleep(wait_time)
                        continue
                    else:
                        logger.error(f"查询订单状态异常，重试次数已用完: {order.order_uid} - {e}")
                        self.metrics.record_api_call(success=False)
                        self.metrics.record_order_check(success=False)
                        break
                
        except Exception as e:
            logger.error(f"检查订单状态失败 {order.order_uid}: {e}")
            self.metrics.record_api_call(success=False)
            self.metrics.record_order_check(success=False)

    async def _update_order_status_from_exchange(self, order: LimitFollowOrder, order_data: dict):
        """从交易所数据更新订单状态（支持多交易所）"""
        try:
            # 尝试多种状态字段名（兼容不同交易所）
            exchange_status = (
                order_data.get('state') or 
                order_data.get('status') or 
                order_data.get('order_status') or
                order_data.get('orderState')
            )
            
            if not exchange_status:
                logger.warning(f"无法从订单数据中提取状态: {order.order_uid}, 数据: {order_data}")
                return
            
            if exchange_status == 'filled' or exchange_status == 'FILLED' or exchange_status == 'completed':
                # 订单已成交
                # 尝试多种价格字段名
                filled_price = float(
                    order_data.get('avgPx') or 
                    order_data.get('avg_px') or 
                    order_data.get('average_price') or
                    order_data.get('filled_price') or
                    order_data.get('price') or
                    0
                )
                # 尝试多种数量字段名
                filled_size = float(
                    order_data.get('accFillSz') or 
                    order_data.get('acc_fill_sz') or
                    order_data.get('filled_size') or
                    order_data.get('filled_quantity') or
                    order_data.get('executed_qty') or
                    order_data.get('quantity') or
                    0
                )
                
                success = self.db.update_order_status(
                        order.order_uid, 'filled',
                        filled_price=filled_price,
                        filled_size=filled_size
                    )
                    
                if success:
                    logger.info(f"✅ 订单成交: {order.order_uid} - 价格: {filled_price}, 数量: {filled_size}")
                    
                    # 发送通知（如果启用）
                    if self.config['enable_notifications']:
                        await self._send_order_notification(order, 'filled', {
                            'filled_price': filled_price,
                            'filled_size': filled_size
                        })
                
            elif exchange_status in ['canceled', 'expired', 'rejected']:
                # 订单被取消/过期/拒绝
                success = self.db.update_order_status(order.order_uid, exchange_status)
                
                if success:
                    logger.info(f"🚫 订单状态更新: {order.order_uid} -> {exchange_status}")
                    
                    if self.config['enable_notifications']:
                        await self._send_order_notification(order, exchange_status, {})
                    
        except Exception as e:
            logger.error(f"更新订单状态失败: {e}")

    async def _full_status_sync(self):
        """完整的状态同步"""
        try:
            logger.info("🔄 开始完整订单状态同步...")
            start_time = datetime.now()
            
            # 获取所有可能有问题的订单
            problematic_orders = await self._get_problematic_orders()
            
            if not problematic_orders:
                logger.info("✅ 未发现异常订单")
                return
            
            sync_result = OrderSyncResult(success=True)
            sync_result.start_time = start_time
            sync_result.total_checked = len(problematic_orders)
            
            # 分批同步
            batch_size = self.config['batch_sync_size']
            for i in range(0, len(problematic_orders), batch_size):
                batch = problematic_orders[i:i + batch_size]
                
                for order in batch:
                    try:
                        await self._sync_single_order_status(order)
                        sync_result.updated_count += 1
                    except Exception as e:
                        sync_result.error_count += 1
                        sync_result.errors.append(f"订单 {order.get('order_uid', 'unknown')}: {str(e)}")
                
                # API调用间隔
                if i + batch_size < len(problematic_orders):
                    await asyncio.sleep(self.config['api_rate_limit_delay'])
            
            sync_result.end_time = datetime.now()
            
            logger.info(f"✅ 完整状态同步完成 - 耗时: {sync_result.duration:.2f}秒, "
                       f"检查: {sync_result.total_checked}, 更新: {sync_result.updated_count}, "
                       f"错误: {sync_result.error_count}")
            
            # 如果有很多错误，设置警告状态
            if sync_result.error_count > self.config['notification_threshold']:
                self._set_status(MonitorStatus.WARNING)
            
        except Exception as e:
            logger.error(f"完整状态同步失败: {e}")
            self.metrics.record_error()

    async def _get_problematic_orders(self):
        """获取可能有问题的订单"""
        try:
            # 查找长时间未更新的live订单
            stale_timeout_minutes = self.config['stale_order_timeout'] // 60
            
            query = f"""
                SELECT * FROM limit_follow_orders 
                WHERE status = 'live' 
                AND exchange_order_id IS NOT NULL
                AND updated_at < DATE_SUB(NOW(), INTERVAL {stale_timeout_minutes} MINUTE)
                ORDER BY updated_at ASC
                LIMIT {self.config['auto_repair_max_orders']}
            """
            
            return self.db.db_pool.query(query)
            
        except Exception as e:
            logger.error(f"获取异常订单失败: {e}")
            return []

    async def _auto_repair_orders(self):
        """自动修复异常订单"""
        try:
            if not self.config['enable_auto_repair']:
                return
            
            problematic_orders = await self._get_problematic_orders()
            
            if len(problematic_orders) > self.config['notification_threshold']:
                logger.warning(f"⚠️ 发现 {len(problematic_orders)} 个异常订单，开始自动修复...")
                
                repaired_count = 0
                for order in problematic_orders[:self.config['auto_repair_max_orders']]:
                    try:
                        # 检查订单是否超时（超过2小时）
                        # order_age = datetime.now() - order['created_at']
                        # if order_age.total_seconds() > 7200:  # 2小时
                        #     logger.warning(f"订单超时，取消订单: {order['order_uid']}")
                        #     # 取消超时订单
                        #     await self._cancel_timeout_order(order)
                        # else:
                        await self._sync_single_order_status(order)
                        repaired_count += 1
                    except Exception as e:
                        logger.error(f"自动修复订单失败 {order.get('order_uid', 'unknown')}: {e}")
                
                logger.info(f"🔧 自动修复完成，成功修复 {repaired_count} 个订单")
            
        except Exception as e:
            logger.error(f"自动修复订单失败: {e}")

    async def _cancel_timeout_order(self, order):
        """取消超时订单"""
        try:
            logger.info(f"🔄 开始取消超时订单: {order['order_uid']}")
            
            # 获取客户信息
            customer_info = await self._get_customer_info(order['customer_uid'])
            if not customer_info:
                logger.error(f"无法获取客户信息: {order['customer_uid']}")
                return False
            
            # 创建统一REST客户端
            
            customer_data = {
                'api_key': customer_info['api_key'],
                'api_secret': customer_info.get('secret_key') or customer_info.get('api_secret'),
                'passphrase': customer_info['passphrase'],
                'is_demo': get_global_is_demo(),
                'exchange': customer_info.get('exchange', 'okx')
            }
            rest_client = create_exchange_client(
                exchange=customer_data['exchange'],
                client_type='rest',
                api_key=customer_data['api_key'],
                api_secret=customer_data['api_secret'],
                passphrase=customer_data['passphrase'],
                is_demo=customer_data['is_demo']
            )
            
            # 如果有交易所订单ID，尝试取消订单
            if order.get('exchange_order_id'):
                try:
                    cancel_result = await rest_client.cancel_order(
                        instId=order['symbol'],
                        ordId=order['exchange_order_id']
                    )
                    
                    if cancel_result and cancel_result.get('code') == '0':
                        logger.info(f"✅ 成功取消交易所订单: {order['exchange_order_id']}")
                    else:
                        error_msg = cancel_result.get('msg', '未知错误') if cancel_result else '请求失败'
                        logger.warning(f"⚠️ 取消交易所订单失败: {error_msg}")
                        
                except Exception as e:
                    logger.warning(f"⚠️ 取消交易所订单异常: {e}")
            
            # 更新本地订单状态为已取消
            success = self.db.db_pool.execute("""
                UPDATE limit_follow_orders 
                SET status='canceled', updated_at=NOW()
                WHERE order_uid=%s
            """, (order['order_uid'],))
            
            if success:
                logger.info(f"✅ 超时订单已标记为取消: {order['order_uid']}")
                return True
            else:
                logger.error(f"❌ 更新订单状态失败: {order['order_uid']}")
                return False
                
        except Exception as e:
            logger.error(f"❌ 取消超时订单异常: {order['order_uid']} - {e}")
            return False

    async def _check_position_status_consistency(self):
        """检查并修复订单与持仓状态的一致性"""
        try:
            # 查找所有已成交但相关持仓已完全平仓的限价跟单订单（排除市价单）
            inconsistent_orders = self.db_pool.query("""
                SELECT lfo.order_uid, lfo.customer_uid, lfo.symbol, lfo.pos_side, lfo.trader_unique_name
                FROM limit_follow_orders lfo
                WHERE lfo.status = 'filled'
                AND lfo.order_type = 'limit'  -- 只检查限价单，不检查市价单
                AND NOT EXISTS (
                    SELECT 1 FROM customer_trades ct 
                    WHERE ct.customer_uid = lfo.customer_uid 
                    AND ct.symbol = lfo.symbol 
                    AND ct.pos_side = lfo.pos_side
                    AND ct.status = 'open'
                    AND (ct.volume_contract - IFNULL(ct.close_volume_contract, 0)) > 0
                )
                AND NOT EXISTS (
                    SELECT 1 FROM signal_account_trades sat
                    WHERE sat.signal_source_uid = lfo.trader_unique_name
                    AND sat.symbol = lfo.symbol
                    AND sat.pos_side = lfo.pos_side
                    AND sat.status = 'open'
                    AND (sat.volume_contract - IFNULL(sat.close_volume_contract, 0)) > 0
                )
                AND NOT EXISTS (
                    SELECT 1 FROM limit_follow_orders lfo2
                    WHERE lfo2.customer_uid = lfo.customer_uid
                    AND lfo2.symbol = lfo.symbol
                    AND lfo2.pos_side = lfo.pos_side
                    AND lfo2.status IN ('pending', 'live')
                )
            """)
            
            if inconsistent_orders:
                logger.debug(f"🔧 发现 {len(inconsistent_orders)} 个状态不一致的订单，正在修复...")
                
                fixed_count = 0
                for order in inconsistent_orders:
                    # 更新订单状态为closed
                    success = self.db_pool.execute("""
                        UPDATE limit_follow_orders 
                        SET status='closed', updated_at=NOW() 
                        WHERE order_uid=%s
                    """, (order['order_uid'],))
                    
                    if success:
                        fixed_count += 1
                        logger.debug(f"✅ 自动修复订单状态: {order['order_uid']} -> closed")
                
                if fixed_count > 0:
                    logger.info(f"🔧 自动修复了 {fixed_count} 个订单状态")
                    
        except Exception as e:
            logger.error(f"检查持仓状态一致性失败: {e}")
            self.metrics.record_error()

    # ==================== 订单状态更新接口 ====================
    
    def on_order_status_update(self, exchange_order_id: str, order_data: dict):
        """接收来自信号服务的订单状态更新（同步方法）"""
        try:
            # 创建异步任务处理更新
            asyncio.create_task(self._handle_order_status_update(exchange_order_id, order_data))
        except Exception as e:
            logger.error(f"处理订单状态更新失败: {e}")
    
    async def _handle_order_status_update(self, exchange_order_id: str, order_data: dict):
        """处理订单状态更新（异步方法）"""
        try:
            # 查找对应的限价跟单订单
            orders = self.db.db_pool.query(
                "SELECT * FROM limit_follow_orders WHERE exchange_order_id = %s",
                (exchange_order_id,)
            )
            
            if not orders:
                return  # 不是限价跟单订单，忽略
            
            for order_row in orders:
                order_status = order_data.get('state')
                
                if order_row['status'] != order_status:
                    # 更新订单状态
                    if order_status == 'filled':
                        # 订单已成交
                        filled_price = float(order_data.get('avgPx', 0))
                        filled_size = float(order_data.get('accFillSz', 0))
                        
                        success = self.db.db_pool.execute("""
                            UPDATE limit_follow_orders 
                            SET status='filled', filled_price=%s, filled_size=%s, updated_at=NOW()
                            WHERE order_uid=%s
                        """, (filled_price, filled_size, order_row['order_uid']))
                        
                        if success:
                            logger.info(f"🔄 [实时] 限价跟单订单成交: {order_row['order_uid']} - 价格: {filled_price}")
                            self.metrics.record_order_check(success=True)
                    
                    elif order_status in ['canceled', 'expired', 'rejected']:
                        # 订单取消/过期/拒绝
                        success = self.db.db_pool.execute("""
                            UPDATE limit_follow_orders 
                            SET status=%s, updated_at=NOW()
                            WHERE order_uid=%s
                        """, (order_status, order_row['order_uid']))
                        
                        if success:
                            logger.info(f"🔄 [实时] 限价跟单订单状态更新: {order_row['order_uid']} -> {order_status}")
                            self.metrics.record_order_check(success=True)
                    
                    # 记录WebSocket消息（虽然实际上是通过信号服务）
                    self.metrics.record_websocket_message()
                    
        except Exception as e:
            logger.error(f"处理限价跟单订单状态更新失败: {e}")
            self.metrics.record_order_check(success=False)

    # ==================== 健康检查 ====================
    
    async def _health_check_loop(self):
        """健康检查循环"""
        check_interval = self.config['health_check_interval']
        
        while self.running:
            try:
                await self._perform_health_check()
                await asyncio.sleep(check_interval)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"健康检查异常: {e}")
                await asyncio.sleep(check_interval)

    async def _perform_health_check(self):
        """执行健康检查"""
        try:
            # 检查数据库连接
            db_healthy = await self._check_database_health()
            
            # 检查API连接
            api_healthy = await self._check_api_health()
            
            # 检查WebSocket连接
            ws_healthy = await self._check_websocket_health()
            
            # 检查异常订单数量
            problematic_count = len(await self._get_problematic_orders())
            
            # 确定整体健康状态
            if db_healthy and api_healthy and problematic_count < self.config['problematic_order_threshold']:
                self._set_status(MonitorStatus.HEALTHY)
            elif problematic_count < self.config['problematic_order_threshold'] * 2:
                self._set_status(MonitorStatus.WARNING)
            else:
                self._set_status(MonitorStatus.ERROR)
            
            logger.debug(f"🏥 健康检查完成 - DB: {db_healthy}, API: {api_healthy}, WS: {ws_healthy}, 异常订单: {problematic_count}")
            
        except Exception as e:
            logger.error(f"健康检查失败: {e}")
            self._set_status(MonitorStatus.ERROR)
            
            # 尝试重新初始化数据库连接
            try:
                if 'database' in str(e).lower() or 'none' in str(e).lower():
                    logger.info("尝试重新获取全局数据库连接...")
                    
                    self.db_pool = get_global_db_pool()
                    self.db = LimitFollowDB(self.db_pool)
                    logger.info("全局数据库连接重新获取成功")
            except Exception as reconnect_error:
                logger.error(f"数据库重连失败: {reconnect_error}")

    # ==================== 辅助方法 ====================
    
    def _set_status(self, status: str):
        """设置监控状态"""
        with self.status_lock:
            if self.current_status != status:
                old_status = self.current_status
                self.current_status = status
                logger.info(f"📊 监控状态变更: {old_status} -> {status}")

    def get_status(self):
        """获取当前状态"""
        with self.status_lock:
            return {
                'status': self.current_status.value if self.current_status else 'unknown',
                'running': self.running,
                'metrics': {
                    'orders_checked': self.metrics.orders_checked,
                    'orders_updated': self.metrics.orders_updated,
                    'orders_failed': self.metrics.orders_failed,
                    'success_rate': self.metrics.success_rate,
                    'api_success_rate': self.metrics.api_success_rate,
                    'websocket_messages': self.metrics.websocket_messages,
                    'sync_cycles': self.metrics.sync_cycles_completed,
                    'last_sync_time': str(self.metrics.last_sync_time) if self.metrics.last_sync_time else None,
                    'consecutive_failures': self.metrics.consecutive_failures,
                    'uptime_seconds': (datetime.now() - self.metrics.uptime_start).total_seconds() if self.metrics.uptime_start else 0
                },
                'config': {
                    'check_interval': self.config['check_interval'],
                    'websocket_enabled': self.websocket_enabled,
                    'auto_repair_enabled': self.config['enable_auto_repair']
                }
            }

    # 保持原有的方法签名以兼容现有代码
    async def _get_customer_info(self, customer_uid):
        """获取客户或信号源信息"""
        try:
            # 获取当前盘口模式
            is_demo = get_global_is_demo()
            
            # 先尝试从客户表查询（根据当前盘口模式）
            customers = self.db.db_pool.query(
                "SELECT customer_uid, api_key, api_secret as secret_key, passphrase, enabled, is_demo, COALESCE(exchange, 'okx') as exchange FROM customers WHERE customer_uid = %s AND enabled = 1 AND is_demo = %s",
                (customer_uid, is_demo)
            )
            if customers:
                return customers[0]
            
            # 如果客户表没有，尝试从信号源表查询（兼容旧数据，根据当前盘口模式）
            signal_sources = self.db.db_pool.query(
                "SELECT source_uid as customer_uid, api_key, api_secret as secret_key, passphrase, enabled, is_demo, COALESCE(exchange, 'okx') as exchange FROM signal_sources WHERE source_uid = %s AND enabled = 1 AND is_demo = %s",
                (customer_uid, is_demo)
            )
            if signal_sources:
                logger.info(f"使用信号源账户作为客户: {customer_uid}（{'模拟盘' if is_demo else '实盘'}）")
                return signal_sources[0]
            
            logger.warning(f"未找到账户 {customer_uid} 在当前盘口模式（{'模拟盘' if is_demo else '实盘'}）的配置")
            return None
        except Exception as e:
            logger.error(f"获取客户信息失败: {e}")
            return None

    async def _get_active_customers(self):
        """获取活跃客户列表"""
        try:
            # 获取当前盘口模式
            is_demo = get_global_is_demo()
            
            return self.db.db_pool.query(
                "SELECT * FROM customers WHERE enabled = 1 AND is_demo = %s",
                (is_demo,)
            )
        except Exception as e:
            logger.error(f"获取活跃客户列表失败: {e}")
            return []

    async def _check_database_health(self):
        """检查数据库健康状态"""
        try:
            # 检查数据库连接池是否可用
            if self.db_pool is None:
                logger.warning("数据库连接池为空")
                return False
            
            result = self.db.db_pool.query("SELECT 1 as test")
            return result is not None and len(result) > 0
        except Exception as e:
            logger.warning(f"数据库健康检查失败: {e}")
            return False

    async def _check_api_health(self):
        """检查API健康状态"""
        # 简单返回True，实际可以做一个轻量级API调用测试
        return True

    async def _check_websocket_health(self):
        """检查WebSocket健康状态"""
        if not self.websocket_enabled:
            return True
        
        # WebSocket连接通过信号服务管理，这里总是返回True
        # 实际的WebSocket健康状态可以通过信号服务的健康检查来确认
        return True

    async def _sync_single_order_status(self, order_dict):
        """同步单个订单状态"""
        # 这里复用现有的检查逻辑
        order = LimitFollowOrder()
        order.order_uid = order_dict['order_uid']
        order.customer_uid = order_dict['customer_uid']
        order.symbol = order_dict['symbol']
        order.exchange_order_id = order_dict['exchange_order_id']
        order.status = order_dict['status']
        
        await self._check_order_status_enhanced(order)

    async def _send_order_notification(self, order, status, data):
        """发送订单通知"""
        try:
            if not self.config['enable_notifications']:
                return
                
            # 这里可以集成钉钉通知或其他通知方式
            logger.info(f"📢 订单通知: {order.order_uid} 状态变更为 {status}")
            
        except Exception as e:
            logger.error(f"发送订单通知失败: {e}")

    # ==================== 向后兼容的方法 ====================
    
    async def _get_customer_positions(self, customer_uid: str, symbol: str) -> List[Dict]:
        """获取客户在指定交易对上的持仓"""
        try:
            # 获取客户配置
            customer = await self._get_customer_info(customer_uid)
            if not customer:
                logger.error(f"客户配置不存在: {customer_uid}")
                return []
            
            # 获取统一交易所客户端（支持多交易所）
            customer_data = {
                'api_key': customer['api_key'],
                'api_secret': customer.get('secret_key') or customer.get('api_secret'),
                'passphrase': customer['passphrase'],
                'is_demo': get_global_is_demo(),
                'exchange': customer.get('exchange', 'okx')
            }
            exchange_client = create_exchange_client(
                exchange=customer_data['exchange'],
                client_type='rest',
                api_key=customer_data['api_key'],
                api_secret=customer_data['api_secret'],
                passphrase=customer_data['passphrase'],
                is_demo=customer_data['is_demo']
            )
            
            # 获取持仓信息（支持多交易所）
            exchange_type = customer_data['exchange'].lower()
            positions_response = None
            
            if exchange_type == 'okx':
                # OKX格式：使用instId参数
                positions_response = await exchange_client.get_positions(instId=symbol)
            else:
                # 其他交易所：使用symbol参数
                positions_response = await exchange_client.get_positions(symbol=symbol)
            
            if not positions_response:
                logger.warning(f"获取持仓信息失败: {customer_uid} {symbol} (交易所: {exchange_type})")
                return []
            
            # 解析持仓数据（根据交易所类型处理不同格式）
            positions = []
            
            if exchange_type == 'okx':
                # OKX格式：{'data': [{...}]}
                if 'data' in positions_response:
                    for pos_data in positions_response['data']:
                        pos_size = float(pos_data.get('pos', '0'))
                        if pos_size > 0:  # 只返回有持仓的记录
                            position = {
                                'pos': pos_size,
                                'pos_side': pos_data.get('posSide', 'long'),
                                'avg_px': float(pos_data.get('avgPx', '0')),
                                'upl': float(pos_data.get('upl', '0')),
                                'margin': float(pos_data.get('margin', '0')),
                                'status': 'open'
                            }
                            positions.append(position)
            else:
                # 其他交易所：可能是统一格式或列表格式
                positions_data = positions_response
                if isinstance(positions_response, dict):
                    if 'positions' in positions_response:
                        positions_data = positions_response['positions']
                    elif 'data' in positions_response:
                        positions_data = positions_response['data']
                
                if isinstance(positions_data, list):
                    for pos_data in positions_data:
                        # 尝试多种字段名（兼容不同交易所）
                        pos_size = float(pos_data.get('size', pos_data.get('pos', pos_data.get('position', '0'))))
                        if pos_size > 0:
                            position = {
                                'pos': pos_size,
                                'pos_side': pos_data.get('pos_side', pos_data.get('posSide', 'long')),
                                'avg_px': float(pos_data.get('entry_price', pos_data.get('avgPx', pos_data.get('avg_px', '0')))),
                                'upl': float(pos_data.get('unrealized_pnl', pos_data.get('upl', '0'))),
                                'margin': float(pos_data.get('margin', '0')),
                                'status': 'open'
                            }
                            positions.append(position)
            
            logger.info(f"获取到客户 {customer_uid} 在 {symbol} 上的 {len(positions)} 个持仓")
            return positions
            
        except Exception as e:
            logger.error(f"获取客户持仓失败: {e}")
            return []

    async def _get_customer_account_info(self, customer_uid: str) -> Optional[Dict]:
        """获取客户账户信息（余额、保证金等）"""
        try:
            # 获取客户配置
            customer = await self._get_customer_info(customer_uid)
            if not customer:
                logger.error(f"客户配置不存在: {customer_uid}")
                return None
            
            # 获取统一交易所客户端（支持多交易所）
            customer_data = {
                'api_key': customer['api_key'],
                'api_secret': customer.get('secret_key') or customer.get('api_secret'),
                'passphrase': customer['passphrase'],
                'is_demo': get_global_is_demo(),
                'exchange': customer.get('exchange', 'okx')
            }
            exchange_client = create_exchange_client(
                exchange=customer_data['exchange'],
                client_type='rest',
                api_key=customer_data['api_key'],
                api_secret=customer_data['api_secret'],
                passphrase=customer_data['passphrase'],
                is_demo=customer_data['is_demo']
            )
            
            # 获取账户余额（支持多交易所）
            exchange_type = customer_data['exchange'].lower()
            account_info = None
            
            # 使用统一接口获取余额
            try:
                balances = await exchange_client.get_balance()
                
                # 处理不同交易所的响应格式
                total_balance = 0.0
                available_balance = 0.0
                
                if isinstance(balances, list):
                    # 统一接口返回Balance对象列表
                    for balance in balances:
                        if balance.asset == 'USDT':
                            total_balance = balance.total
                            available_balance = balance.free
                            break
                elif isinstance(balances, dict):
                    # 兼容旧格式（OKX格式）
                    if 'data' in balances:
                        balance_data = balances['data']
                        for balance in balance_data:
                            if balance.get('ccy') == 'USDT':
                                total_balance = float(balance.get('bal', 0))
                                available_balance = float(balance.get('availBal', 0))
                                break
                    elif 'balances' in balances:
                        # 其他交易所格式
                        for balance in balances['balances']:
                            if balance.get('asset') == 'USDT' or balance.get('currency') == 'USDT':
                                total_balance = float(balance.get('total', balance.get('balance', 0)))
                                available_balance = float(balance.get('free', balance.get('available', 0)))
                                break
                
                if total_balance == 0 and available_balance == 0:
                    logger.warning(f"未找到USDT余额: {customer_uid} (交易所: {exchange_type})")
                    return None
                
                return {
                    'total_balance': total_balance,
                    'available_balance': available_balance,
                    'currency': 'USDT',
                    'customer_uid': customer_uid
                }
                
            except Exception as e:
                logger.error(f"获取账户余额失败: {e}")
                return None
                
        except Exception as e:
            logger.error(f"获取客户账户信息失败: {e}")
            return None

    async def _get_strategy_leverage(self, strategy_id: int, customer_uid: str) -> int:
        """获取策略杠杆设置（支持客户自定义杠杆）"""
        try:
            # 首先查询客户是否有自定义杠杆设置
            custom_leverage = self.db_pool.query(
                """SELECT custom_leverage FROM limit_follow_strategy_customers 
                   WHERE strategy_id=%s AND customer_uid=%s AND enabled=1""",
                (strategy_id, customer_uid)
            )
            
            if custom_leverage and custom_leverage[0]['custom_leverage']:
                return int(custom_leverage[0]['custom_leverage'])
            
            # 如果没有自定义杠杆，使用策略默认杠杆
            strategy_data = self.db_pool.query(
                "SELECT leverage FROM limit_follow_strategies WHERE id=%s",
                (strategy_id,)
            )
            
            if strategy_data and strategy_data[0]['leverage']:
                return int(strategy_data[0]['leverage'])
            
            # 默认杠杆
            return 10
            
        except Exception as e:
            logger.error(f"获取策略杠杆失败: {e}")
            return 10

    # 为了兼容现有代码，保留一些原有方法的引用
    async def _submit_order_to_exchange_enhanced(self, order):
        """增强的订单提交方法"""
        return await self._submit_order_to_exchange(order)
    
    async def _submit_order_to_exchange(self, order):
        """提交订单到交易所"""
        try:
            # 获取客户信息
            customer_info = await self._get_customer_info(order.customer_uid)
            if not customer_info:
                logger.error(f"无法获取客户信息: {order.customer_uid}")
                return False
            
            # 创建统一REST客户端
            
            customer_data = {
                'api_key': customer_info['api_key'],
                'api_secret': customer_info.get('secret_key') or customer_info.get('api_secret'),
                'passphrase': customer_info['passphrase'],
                'is_demo': get_global_is_demo(),
                'exchange': customer_info.get('exchange', 'okx')
            }
            rest_client = create_exchange_client(
                exchange=customer_data['exchange'],
                client_type='rest',
                api_key=customer_data['api_key'],
                api_secret=customer_data['api_secret'],
                passphrase=customer_data['passphrase'],
                is_demo=customer_data['is_demo']
            )
            
            # 调整订单数量精度
            min_sz = get_contract_min_sz(order.symbol)
            sz_precision = get_contract_sz_precision(order.symbol)
            tick_sz = get_contract_tick_sz(order.symbol)
            
            # 确保数量是最小单位的倍数
            adjusted_size = round(order.order_size / min_sz) * min_sz
            adjusted_size = round(adjusted_size, sz_precision)  # sz_precision 是整数
            
            # 确保不小于最小数量
            if adjusted_size < min_sz:
                adjusted_size = min_sz
            
            # 调整价格精度
            adjusted_price = None
            if order.order_type == "limit" and order.target_price:
                # 确保价格是tick size的倍数
                adjusted_price = round(order.target_price / tick_sz) * tick_sz
                # 根据tick size确定价格精度（计算小数位数）
                if tick_sz >= 1:
                    price_precision = 0
                elif tick_sz >= 0.1:
                    price_precision = 1
                elif tick_sz >= 0.01:
                    price_precision = 2
                elif tick_sz >= 0.001:
                    price_precision = 3
                elif tick_sz >= 0.0001:
                    price_precision = 4
                elif tick_sz >= 0.00001:
                    price_precision = 5
                elif tick_sz >= 0.000001:
                    price_precision = 6
                elif tick_sz >= 0.0000001:
                    price_precision = 7
                elif tick_sz >= 0.00000001:
                    price_precision = 8
                elif tick_sz >= 0.000000001:
                    price_precision = 9
                else:
                    # 对于更小的tick size，使用更高的精度
                    price_precision = 12
                
                adjusted_price = round(adjusted_price, price_precision)
                
                # 确保价格不是科学计数法格式
                if 'e' in str(adjusted_price).lower():
                    # 将科学计数法转换为普通小数格式
                    adjusted_price = float(f"{adjusted_price:.{price_precision}f}")
            
            # 生成客户端订单ID（兼容多交易所）
            import time
            
            timestamp = str(int(time.time() * 1000))[-8:]
            order_hash = str(hash(order.order_uid))[-8:]
            client_order_id = f"LF{timestamp}{order_hash}"
            
            # 获取策略杠杆设置
            strategy_leverage = await self._get_strategy_leverage(order.strategy_id, order.customer_uid)
            logger.info(f"开始设置杠杆: {order.symbol} {strategy_leverage}倍 (交易所: {customer_data['exchange']})")

            # 设置杠杆（仅当交易所支持时，某些交易所可能不支持或使用不同接口）
            try:
                # 检查交易所客户端是否支持set_leverage方法
                if hasattr(rest_client, 'set_leverage'):
                    leverage_data = await rest_client.set_leverage(strategy_leverage, "cross", order.symbol)
                    logger.info(f"🔧 杠杆设置响应: {leverage_data}")
                    
                    # 处理不同交易所的响应格式
                    leverage_success = False
                    if isinstance(leverage_data, dict):
                        if leverage_data.get('code') == '0':  # OKX格式
                            leverage_success = True
                        elif leverage_data.get('success'):  # 其他交易所统一格式
                            leverage_success = True
                    
                    if leverage_success:
                        logger.info(f"✅ 设置杠杆成功: {order.symbol} {strategy_leverage}倍")
                    else:
                        error_msg = leverage_data.get('msg', '未知错误') if isinstance(leverage_data, dict) else '请求失败'
                        logger.warning(f"⚠️ 设置杠杆失败: {order.symbol} {strategy_leverage}倍 - {error_msg}，继续下单")
                else:
                    logger.info(f"交易所 {customer_data['exchange']} 不支持set_leverage方法，跳过杠杆设置")
                    
            except Exception as e:
                logger.warning(f"⚠️ 设置杠杆异常: {order.symbol} {strategy_leverage}倍 - {e}，继续下单")


            # 构建订单参数（使用统一接口，支持多交易所）
            from exchange.base_client import OrderRequest, OrderSide, OrderType
            
            # 确定订单方向
            order_side = OrderSide.BUY if order.pos_side == "long" else OrderSide.SELL
            order_type_enum = OrderType.LIMIT if order.order_type == "limit" else OrderType.MARKET
            
            # 构建OrderRequest对象（统一接口）
            order_request = OrderRequest(
                symbol=order.symbol,
                side=order_side,
                order_type=order_type_enum,
                quantity=adjusted_size,
                price=adjusted_price if order.order_type == "limit" and adjusted_price else None,
                client_order_id=client_order_id,
                reduce_only=order.reduce_only if hasattr(order, 'reduce_only') else False,
                # OKX特定参数（其他交易所可能忽略）
                td_mode="cross",  # 全仓模式
                pos_side=order.pos_side,  # 持仓方向
                lever=str(strategy_leverage) if strategy_leverage else None  # 杠杆倍数
            )
            
            logger.info(f"√ 提交限价跟单订单到交易所: {order.order_uid} (交易所: {customer_data['exchange']})")
            if order.order_type == "limit" and adjusted_price:
                price_str = f"{adjusted_price:.{price_precision}f}" if 'price_precision' in locals() else f"{adjusted_price:.8f}"
                logger.info(f"订单参数: 数量={adjusted_size}, 价格={price_str}, 合约={order.symbol}")
            else:
                logger.info(f"订单参数: 数量={adjusted_size}, 合约={order.symbol}")
            
            # 提交订单（使用统一接口）
            try:
                order_response = await rest_client.place_order(order_request)
                
                # 处理不同交易所的响应格式
                exchange_order_id = None
                if hasattr(order_response, 'order_id'):
                    # 统一接口返回OrderResponse对象
                    exchange_order_id = order_response.order_id
                elif isinstance(order_response, dict):
                    # 兼容旧格式（OKX legacy格式）
                    if order_response.get('code') == '0':
                        order_info = order_response.get('data', [{}])[0]
                        exchange_order_id = order_info.get('ordId')
                    elif order_response.get('success'):
                        # 其他交易所的统一格式
                        exchange_order_id = order_response.get('order_id')
                
                if exchange_order_id:
                    # 更新数据库中的交易所订单ID
                    try:
                        success = self.db.db_pool.execute("""
                            UPDATE limit_follow_orders 
                            SET exchange_order_id=%s, status='live', updated_at=NOW()
                            WHERE order_uid=%s
                        """, (exchange_order_id, order.order_uid))
                        
                        if success:
                            logger.info(f"✅ 限价跟单订单提交成功: {order.order_uid} -> {exchange_order_id} (交易所: {customer_data['exchange']})")
                            return True
                        else:
                            logger.error(f"❌ 更新交易所订单ID失败: {order.order_uid}, exchange_order_id={exchange_order_id}")
                            return False
                    except Exception as e:
                        logger.error(f"❌ 更新交易所订单ID异常: {order.order_uid}, error={e}")
                        return False
                else:
                    logger.error(f"❌ 交易所未返回订单ID: {order.order_uid}, 响应: {order_response}")
                    return False
            except Exception as order_error:
                # 订单提交异常
                error_msg = str(order_error)
                logger.error(f"❌ 限价跟单订单提交失败: {order.order_uid} (交易所: {customer_data['exchange']}) - {error_msg}")
                
                # 更新订单状态为失败
                self.db.db_pool.execute("""
                    UPDATE limit_follow_orders 
                    SET status='rejected', updated_at=NOW()
                    WHERE order_uid=%s
                """, (order.order_uid,))
                
                return False
                
        except Exception as e:
            logger.error(f"❌ 提交订单到交易所异常: {order.order_uid} - {e}")
            
            # 更新订单状态为失败
            try:
                self.db.db_pool.execute("""
                    UPDATE limit_follow_orders 
                    SET status='rejected', updated_at=NOW()
                    WHERE order_uid=%s
                """, (order.order_uid,))
            except:
                pass
            
            return False

# ==================== 向后兼容性 ====================
# 为向后兼容，提供旧类名的别名
LimitFollowService = EnhancedLimitFollowService

# ==================== 全局服务实例管理 ====================

_limit_follow_service = None

def get_limit_follow_service() -> EnhancedLimitFollowService:
    """获取增强限价跟单服务实例"""
    global _limit_follow_service
    if _limit_follow_service is None:
        _limit_follow_service = EnhancedLimitFollowService()
    return _limit_follow_service

def reset_limit_follow_service():
    """重置服务实例（用于重启）"""
    global _limit_follow_service
    if _limit_follow_service:
        _limit_follow_service.stop_monitoring()
    _limit_follow_service = None

def notify_limit_follow_order_update(exchange_order_id: str, order_data: dict):
    """通知限价跟单服务有订单状态更新（供信号服务调用）"""
    global _limit_follow_service
    if _limit_follow_service:
        _limit_follow_service.on_order_status_update(exchange_order_id, order_data)

# 如果直接运行此文件，启动服务
if __name__ == '__main__':
    service = EnhancedLimitFollowService()
    try:
        import asyncio
        asyncio.run(service.start_monitoring())
    except KeyboardInterrupt:
        logger.info("收到中断信号，停止服务...")
        service.stop_monitoring()
    except Exception as e:
        logger.error(f"服务运行异常: {e}")
        service.stop_monitoring() 
