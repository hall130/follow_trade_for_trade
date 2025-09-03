#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
限价跟单核心服务模块
提供限价跟单的核心业务逻辑
"""

import logging
import time
import threading
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime
from exchange.okx.okx_rest_client import OKXRESTClient
from config.limit_follow_config import get_limit_follow_config, get_customer_limit_follow_config
from .limit_follow_db import LimitFollowDB
from .limit_follow_models import (
    LimitFollowStrategy, LimitFollowOrder, LimitFollowExecution,
    FollowOrderRequest, FollowOrderResponse, CancelFollowOrdersRequest,
    CancelFollowOrdersResponse, PriceCalculationResult, OrderPlacementResult,
    SignalEvent, create_order_uid, create_execution_uid,
    calculate_follow_price, calculate_order_size, validate_price, validate_volume
)

logger = logging.getLogger(__name__)

class LimitFollowService:
    """限价跟单服务配置"""
    
    def __init__(self, db_pool=None):
        # 初始化数据库连接
        if db_pool is None:
            from config import get_mysql_config
            from database.db import MySQLPool
            db_pool = MySQLPool(**get_mysql_config())
        
        self.db = LimitFollowDB(db_pool)
        self.config = get_limit_follow_config()
        self.running = False
        self.monitor_thread = None
        self.okx_clients: Dict[str, OKXRESTClient] = {}
        
        # 初始化日志
        self._setup_logging()
        
        # 启动监控线程
        # self._start_monitor_thread()  # 暂时注释掉，避免初始化时启动
    
    def _setup_logging(self):
        """设置日志"""
        if self.config.get('enable_logging', True):
            log_level = getattr(logging, self.config.get('log_level', 'INFO').upper())
            logging.basicConfig(level=log_level)
    
    def _start_monitor_thread(self):
        """启动监控任务"""
        if not self.running:
            self.running = True
            # 使用asyncio.create_task而不是threading.Thread
            import asyncio
            try:
                loop = asyncio.get_event_loop()
                self.monitor_task = loop.create_task(self._monitor_loop())
                logger.info("限价跟单监控任务已启动")
            except RuntimeError:
                # 如果没有事件循环，创建一个新的
                self.monitor_task = asyncio.create_task(self._monitor_loop())
                logger.info("限价跟单监控任务已启动")
    
    def start_monitoring(self):
        """启动监控"""
        if not self.running:
            self._start_monitor_thread()
    
    def stop_monitoring(self):
        """停止监控"""
        self._stop_monitor_thread()
    
    def _stop_monitor_thread(self):
        """停止监控任务"""
        self.running = False
        if hasattr(self, 'monitor_task') and self.monitor_task:
            self.monitor_task.cancel()
            logger.info("限价跟单监控任务已停止")
    
    async def _monitor_loop(self):
        """监控循环"""
        check_interval = self.config.get('check_interval', 1)
        
        while self.running:
            try:
                            # 检查待处理订单
                await self._check_pending_orders()
                
                # 检查活跃订单状态
                await self._check_live_orders()
                    
                # 等待下次检查
                await asyncio.sleep(check_interval)
                
            except Exception as e:
                logger.error(f"监控循环异常: {e}")
                await asyncio.sleep(check_interval)
    
    async def _check_pending_orders(self):
        """检查待处理订单"""
        try:
            pending_orders = self.db.get_pending_orders()
            
            for order in pending_orders:
                if order.status == 'pending':
                    # 提交订单到交易所
                    await self._submit_order_to_exchange(order)
                elif order.status == 'live':
                    # 检查订单状态
                    await self._check_order_status(order)
                    
        except Exception as e:
            logger.error(f"检查待处理订单失败: {e}")
    
    async def _check_live_orders(self):
        """检查活跃订单状态"""
        try:
            live_orders = self.db.get_orders({'status': 'live'})
            
            for order in live_orders:
                await self._check_order_status(order)
                
        except Exception as e:
            logger.error(f"检查活跃订单失败: {e}")
    
    async def _submit_order_to_exchange(self, order: LimitFollowOrder) -> bool:
        """提交订单到交易所"""
        try:
            # 获取客户配置
            customer_config = get_customer_limit_follow_config(order.customer_uid)
            if not customer_config or 'customer_info' not in customer_config:
                logger.error(f"客户配置不存在: {order.customer_uid}")
                return False
            
            customer_info = customer_config['customer_info']
            
            # 获取或创建OKX客户端
            okx_client = self._get_okx_client(customer_info)
            if not okx_client:
                return False
            
            # 构建订单参数
            order_params = {
                'instId': order.symbol,
                'tdMode': 'cross',
                'side': 'buy' if order.pos_side == 'long' else 'sell',
                'ordType': 'limit',
                'sz': str(order.order_size),
                'px': str(order.target_price)
            }
            
            # 提交订单（异步调用）
            response = await okx_client.place_order(**order_params)
            
            if response and response.get('code') == '0':
                # 订单提交成功
                exchange_order_id = response['data'][0]['ordId']
                
                # 更新订单状态
                self.db.update_order_status(
                    order.order_uid, 'live', 
                    exchange_order_id=exchange_order_id
                )
                
                # 记录执行日志
                self._log_execution(
                    order, 'order_placement', 'completed',
                    {'exchange_order_id': exchange_order_id}
                )
                
                logger.info(f"订单提交成功: {order.order_uid} -> {exchange_order_id}")
                return True
            else:
                # 订单提交失败
                error_msg = response.get('msg', '未知错误') if response else '请求失败'
                
                # 更新订单状态
                self.db.update_order_status(order.order_uid, 'rejected')
                
                # 记录执行日志
                self._log_execution(
                    order, 'order_placement', 'failed',
                    {'error': error_msg}
                )
                
                logger.error(f"订单提交失败: {order.order_uid} - {error_msg}")
                return False
                
        except Exception as e:
            logger.error(f"提交订单到交易所失败: {e}")
            
            # 记录执行日志
            self._log_execution(
                order, 'order_placement', 'failed',
                {'error': str(e)}
            )
            
            return False
    
    async def _check_order_status(self, order: LimitFollowOrder):
        """检查订单状态"""
        try:
            if not order.exchange_order_id:
                return
            
            # 获取客户配置
            customer_config = get_customer_limit_follow_config(order.customer_uid)
            if not customer_config or 'customer_info' not in customer_config:
                return
            
            customer_info = customer_config['customer_info']
            
            # 获取OKX客户端
            okx_client = self._get_okx_client(customer_info)
            if not okx_client:
                return
            
            # 查询订单状态
            response = await okx_client.get_order(order.symbol, order.exchange_order_id)
            
            if response and response.get('code') == '0':
                order_data = response['data'][0]
                order_status = order_data['state']
                
                if order_status == 'filled':
                    # 订单已成交
                    filled_price = float(order_data['avgPx'])
                    filled_size = float(order_data['accFillSz'])
                    
                    # 更新订单状态
                    self.db.update_order_status(
                        order.order_uid, 'filled',
                        filled_price=filled_price,
                        filled_size=filled_size
                    )
                    
                    # 记录执行日志
                    self._log_execution(
                        order, 'order_filled', 'completed',
                        {'filled_price': filled_price, 'filled_size': filled_size}
                    )
                    
                    logger.info(f"订单已成交: {order.order_uid} - 价格: {filled_price}, 数量: {filled_size}")
                    
                    # 处理成交后的逻辑（如平仓等）
                    self._handle_order_filled(order, filled_price, filled_size)
                    
                elif order_status in ['canceled', 'expired']:
                    # 订单已撤销或过期
                    new_status = 'canceled' if order_status == 'canceled' else 'expired'
                    
                    # 更新订单状态
                    self.db.update_order_status(order.order_uid, new_status)
                    
                    # 记录执行日志
                    self._log_execution(
                        order, 'order_status_update', 'completed',
                        {'new_status': new_status}
                    )
                    
                    logger.info(f"订单状态更新: {order.order_uid} -> {new_status}")
                    
        except Exception as e:
            logger.error(f"检查订单状态失败: {e}")
    
    def _handle_order_filled(self, order: LimitFollowOrder, filled_price: float, filled_size: float):
        """处理订单成交后的逻辑"""
        try:
            # 这里可以添加成交后的处理逻辑
            # 例如：自动平仓、风险控制等
            
            logger.info(f"处理订单成交: {order.order_uid}")
            
            # 记录成交信息
            self._log_execution(
                order, 'order_filled_handling', 'completed',
                {'filled_price': filled_price, 'filled_size': filled_size}
            )
            
        except Exception as e:
            logger.error(f"处理订单成交失败: {e}")
    
    def _get_okx_client(self, customer_info: Dict[str, Any]) -> Optional[OKXRESTClient]:
        """获取或创建OKX客户端"""
        try:
            customer_uid = customer_info['customer_uid']
            
            if customer_uid in self.okx_clients:
                return self.okx_clients[customer_uid]
            
            # 创建新的OKX客户端
            api_key = customer_info.get('api_key')
            api_secret = customer_info.get('api_secret')
            passphrase = customer_info.get('passphrase')
            is_sandbox = bool(customer_info.get('is_demo', False))
            
            if not all([api_key, api_secret, passphrase]):
                logger.error(f"客户API配置不完整: {customer_uid}")
                return None
            
            okx_client = OKXRESTClient(
                api_key=api_key,
                api_secret=api_secret,
                passphrase=passphrase,
                is_demo=is_sandbox
            )
            
            self.okx_clients[customer_uid] = okx_client
            return okx_client
            
        except Exception as e:
            logger.error(f"创建OKX客户端失败: {e}")
            return None
    
    async def _get_customer_account_info(self, customer_uid: str) -> Optional[Dict]:
        """获取客户账户信息（余额、保证金等）"""
        try:
            # 获取客户配置
            customer_info = self.config.get('customers', {}).get(customer_uid, {})
            if not customer_info:
                logger.error(f"客户配置不存在: {customer_uid}")
                return None
            
            # 获取OKX客户端
            okx_client = self._get_okx_client(customer_info)
            if not okx_client:
                return None
            
            # 获取账户余额
            account_info = await okx_client.get_account_balance()
            
            if not account_info or 'data' not in account_info:
                logger.warning(f"获取账户余额失败: {customer_uid}")
                return None
            
            # 解析账户信息
            balance_data = account_info['data']
            total_balance = 0.0
            available_balance = 0.0
            
            for balance in balance_data:
                if balance.get('ccy') == 'USDT':
                    total_balance = float(balance.get('bal', 0))
                    available_balance = float(balance.get('availBal', 0))
                    break
            
            return {
                'total_balance': total_balance,
                'available_balance': available_balance,
                'currency': 'USDT',
                'customer_uid': customer_uid
            }
            
        except Exception as e:
            logger.error(f"获取客户账户信息失败: {e}")
            return None
    
    async def _get_customer_positions(self, customer_uid: str, symbol: str) -> List[Dict]:
        """获取客户在指定交易对上的持仓"""
        try:
            # 获取客户配置
            customer_info = self.config.get('customers', {}).get(customer_uid, {})
            if not customer_info:
                logger.error(f"客户配置不存在: {customer_uid}")
                return []
            
            # 获取OKX客户端
            okx_client = self._get_okx_client(customer_info)
            if not okx_client:
                return []
            
            # 获取持仓信息
            positions_response = await okx_client.get_positions(instType='SWAP', instId=symbol)
            
            if not positions_response or 'data' not in positions_response:
                logger.warning(f"获取持仓信息失败: {customer_uid} {symbol}")
                return []
            
            # 解析持仓数据
            positions = []
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
            
            logger.info(f"获取到客户 {customer_uid} 在 {symbol} 上的 {len(positions)} 个持仓")
            return positions
            
        except Exception as e:
            logger.error(f"获取客户持仓失败: {e}")
            return []
    
    def _log_execution(self, order: LimitFollowOrder, execution_type: str, 
                       execution_status: str, execution_data: Dict[str, Any]):
        """记录执行日志"""
        try:
            execution = LimitFollowExecution(
                execution_uid=create_execution_uid(),
                strategy_id=order.strategy_id,  # 使用strategy_id而不是strategy_uid
                order_uid=order.order_uid,
                customer_uid=order.customer_uid,
                symbol=order.symbol,
                pos_side=order.pos_side,
                execution_type=execution_type,
                execution_status=execution_status,
                execution_data=execution_data
            )
            
            self.db.create_execution(execution)
            
        except Exception as e:
            logger.error(f"记录执行日志失败: {e}")
    
    # ==================== 公共接口 ====================
    
    def execute_limit_follow(self, request: FollowOrderRequest) -> FollowOrderResponse:
        """执行限价跟单"""
        try:
            # 验证请求参数
            if not self._validate_follow_request(request):
                return FollowOrderResponse(
                    success=False,
                    message="请求参数验证失败",
                    orders=[],
                    error_code="INVALID_PARAMS"
                )
            
            # 获取跟单策略
            strategies = self.db.get_active_strategies_for_signal(
                request.signal_source_uid, request.symbol, request.pos_side
            )
            
            if not strategies:
                return FollowOrderResponse(
                    success=False,
                    message="未找到有效的跟单策略",
                    orders=[],
                    error_code="NO_STRATEGY"
                )
            
            # 使用指定的策略或第一个可用策略
            strategy = None
            if request.strategy_uid:
                strategy = next((s for s in strategies if s.strategy_uid == request.strategy_uid), None)
                if not strategy:
                    return FollowOrderResponse(
                        success=False,
                        message="指定的策略不存在或未启用",
                        orders=[],
                        error_code="STRATEGY_NOT_FOUND"
                    )
            else:
                strategy = strategies[0]
            
            # 计算跟单价格和数量
            price_result = self._calculate_follow_prices(
                request.signal_price, request.pos_side, 
                request.follow_percentages, strategy
            )
            
            # 创建跟单订单
            orders = []
            for i, (price, size, percentage) in enumerate(zip(
                price_result.calculated_prices, 
                price_result.order_sizes, 
                request.follow_percentages
            )):
                order = LimitFollowOrder(
                    order_uid=create_order_uid(),
                    strategy_uid=strategy.strategy_uid,
                    signal_source_uid=request.signal_source_uid,
                    customer_uid=request.customer_uid,
                    symbol=request.symbol,
                    pos_side=request.pos_side,
                    follow_value=percentage,
                    target_price=price,
                    order_size=size,
                    order_type='limit',
                    status='pending'
                )
                
                # 保存订单到数据库
                if self.db.create_order(order):
                    orders.append(order)
                    
                    # 记录执行日志
                    self._log_execution(
                        order, 'order_creation', 'completed',
                        {'target_price': price, 'order_size': size, 'follow_percentage': percentage}
                    )
                else:
                    logger.error(f"创建订单失败: {order.order_uid}")
            
            if not orders:
                return FollowOrderResponse(
                    success=False,
                    message="创建跟单订单失败",
                    orders=[],
                    error_code="ORDER_CREATION_FAILED"
                )
            
            # 记录日志
            self.db.add_log(LimitFollowLog(
                log_level='INFO',
                message=f"成功创建 {len(orders)} 个跟单订单",
                signal_source_uid=request.signal_source_uid,
                customer_uid=request.customer_uid,
                extra_data={
                    'symbol': request.symbol,
                    'pos_side': request.pos_side,
                    'signal_price': request.signal_price,
                    'orders_count': len(orders)
                }
            ))
            
            return FollowOrderResponse(
                success=True,
                message=f"成功创建 {len(orders)} 个跟单订单",
                orders=orders,
                strategy=strategy
            )
            
        except Exception as e:
            logger.error(f"执行限价跟单失败: {e}")
            
            # 记录错误日志
            self.db.add_log(LimitFollowLog(
                log_level='ERROR',
                message=f"执行限价跟单失败: {str(e)}",
                signal_source_uid=request.signal_source_uid if 'request' in locals() else None,
                customer_uid=request.customer_uid if 'request' in locals() else None,
                extra_data={'error': str(e)}
            ))
            
            return FollowOrderResponse(
                success=False,
                message=f"执行限价跟单失败: {str(e)}",
                orders=[],
                error_code="EXECUTION_FAILED"
            )
    
    def cancel_orders_on_signal_close(self, request: CancelFollowOrdersRequest) -> CancelFollowOrdersResponse:
        """信号源平仓时撤销跟单订单"""
        try:
            # 查找需要撤销的策略
            strategies = self.db.get_active_strategies_for_signal(
                request.signal_source_uid, request.symbol, request.pos_side
            )
            
            if not strategies:
                return CancelFollowOrdersResponse(
                    success=True,
                    message="没有需要撤销的跟单订单",
                    canceled_count=0
                )
            
            canceled_count = 0
            
            for strategy in strategies:
                if strategy.auto_cancel_on_signal_close:
                    # 撤销该策略下的所有待处理订单
                    count = self.db.cancel_pending_orders(strategy.strategy_uid)
                    canceled_count += count
                    
                    # 记录日志
                    if count > 0:
                        self.db.add_log(LimitFollowLog(
                            log_level='INFO',
                            message=f"信号源平仓，撤销策略 {strategy.strategy_uid} 下的 {count} 个订单",
                            signal_source_uid=request.signal_source_uid,
                            strategy_uid=strategy.strategy_uid,
                            extra_data={
                                'symbol': request.symbol,
                                'pos_side': request.pos_side,
                                'canceled_count': count
                            }
                        ))
            
            return CancelFollowOrdersResponse(
                success=True,
                message=f"成功撤销 {canceled_count} 个跟单订单",
                canceled_count=canceled_count
            )
            
        except Exception as e:
            logger.error(f"撤销跟单订单失败: {e}")
            
            # 记录错误日志
            self.db.add_log(LimitFollowLog(
                log_level='ERROR',
                message=f"撤销跟单订单失败: {str(e)}",
                signal_source_uid=request.signal_source_uid,
                extra_data={'error': str(e)}
            ))
            
            return CancelFollowOrdersResponse(
                success=False,
                message=f"撤销跟单订单失败: {str(e)}",
                canceled_count=0,
                error_code="CANCEL_FAILED"
            )
    
    def handle_signal_event(self, event: SignalEvent):
        """处理信号事件"""
        try:
            if event.event_type == 'open_position':
                # 处理开仓信号
                logger.info(f"收到开仓信号: {event.signal_source_uid} - {event.symbol} - {event.pos_side}")
                
                # 这里可以添加自动跟单逻辑
                # 例如：根据配置自动执行跟单
                
            elif event.event_type == 'close_position':
                # 处理平仓信号
                logger.info(f"收到平仓信号: {event.signal_source_uid} - {event.symbol} - {event.pos_side}")
                
                # 撤销相关跟单订单
                request = CancelFollowOrdersRequest(
                    signal_source_uid=event.signal_source_uid,
                    symbol=event.symbol,
                    pos_side=event.pos_side
                )
                
                response = self.cancel_orders_on_signal_close(request)
                logger.info(f"平仓信号处理结果: {response.message}")
                
            elif event.event_type == 'place_order':
                # 处理挂单信号
                logger.info(f"收到挂单信号: {event.signal_source_uid} - {event.symbol} - {event.pos_side}")
                
            elif event.event_type == 'cancel_order':
                # 处理撤单信号
                logger.info(f"收到撤单信号: {event.signal_source_uid} - {event.symbol} - {event.pos_side}")
            
            # 记录信号事件
            self.db.add_log(LimitFollowLog(
                log_level='INFO',
                message=f"处理信号事件: {event.event_type}",
                signal_source_uid=event.signal_source_uid,
                extra_data={
                    'event_type': event.event_type,
                    'symbol': event.symbol,
                    'pos_side': event.pos_side,
                    'price': event.price,
                    'volume': event.volume
                }
            ))
            
        except Exception as e:
            logger.error(f"处理信号事件失败: {e}")
    
    # ==================== 辅助方法 ====================
    
    def _validate_follow_request(self, request: FollowOrderRequest) -> bool:
        """验证跟单请求"""
        try:
            # 验证基本参数
            if not all([request.signal_source_uid, request.customer_uid, 
                       request.symbol, request.pos_side]):
                return False
            
            # 验证价格和数量
            if not validate_price(request.signal_price) or not validate_volume(request.signal_volume):
                return False
            
            # 验证持仓方向
            if request.pos_side not in ['long', 'short']:
                return False
            
            # 验证跟单百分比
            if request.follow_percentages:
                config = get_limit_follow_config()
                min_percentage = config.get('min_follow_percentage', 0.5)
                max_percentage = config.get('max_follow_percentage', 10.0)
                
                for percentage in request.follow_percentages:
                    if not isinstance(percentage, (int, float)):
                        return False
                    if percentage < min_percentage or percentage > max_percentage:
                        return False
            
            return True
            
        except Exception as e:
            logger.error(f"验证跟单请求失败: {e}")
            return False
    
    def _calculate_follow_prices(self, signal_price: float, pos_side: str, 
                                follow_percentages: List[float], 
                                strategy: LimitFollowStrategy) -> PriceCalculationResult:
        """计算跟单价格和数量"""
        try:
            calculated_prices = []
            order_sizes = []
            
            for percentage in follow_percentages:
                # 计算跟单价格
                price = calculate_follow_price(signal_price, percentage, pos_side)
                calculated_prices.append(price)
                
                # 计算订单数量
                size = calculate_order_size(signal_price, percentage, strategy)
                order_sizes.append(size)
            
            return PriceCalculationResult(
                original_price=signal_price,
                pos_side=pos_side,
                follow_percentages=follow_percentages,
                calculated_prices=calculated_prices,
                order_sizes=order_sizes
            )
            
        except Exception as e:
            logger.error(f"计算跟单价格失败: {e}")
            raise
    
    def get_service_status(self) -> Dict[str, Any]:
        """获取服务状态"""
        try:
            status = self.db.get_status_summary()
            
            return {
                'running': self.running,
                'total_strategies': status.total_strategies,
                'active_strategies': status.active_strategies,
                'total_orders': status.total_orders,
                'pending_orders': status.pending_orders,
                'live_orders': status.live_orders,
                'filled_orders': status.filled_orders,
                'canceled_orders': status.canceled_orders,
                'last_update': status.last_update.isoformat() if status.last_update else None
            }
            
        except Exception as e:
            logger.error(f"获取服务状态失败: {e}")
            return {'running': self.running, 'error': str(e)}
    
    def start_service(self):
        """启动服务"""
        try:
            if not self.running:
                self._start_monitor_thread()
                logger.info("限价跟单服务已启动")
            
        except Exception as e:
            logger.error(f"启动服务失败: {e}")
    
    def stop_service(self):
        """停止服务"""
        try:
            self._stop_monitor_thread()
            logger.info("限价跟单服务已停止")
            
        except Exception as e:
            logger.error(f"停止服务失败: {e}")
    
    def __del__(self):
        """析构函数"""
        self.stop_service()

# 全局服务实例
_limit_follow_service = None

def get_limit_follow_service() -> LimitFollowService:
    """获取限价跟单服务实例"""
    global _limit_follow_service
    if _limit_follow_service is None:
        _limit_follow_service = LimitFollowService()
    return _limit_follow_service

if __name__ == "__main__":
    # 测试服务
    service = LimitFollowService()
    
    try:
        # 启动服务
        service.start_service()
        
        # 保持运行
        while True:
            time.sleep(1)
            
    except KeyboardInterrupt:
        print("正在停止服务...")
        service.stop_service()
        print("服务已停止") 
