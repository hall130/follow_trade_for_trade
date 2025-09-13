#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
限价跟单执行器
监控跟单员交易，自动执行跟单策略
"""

import json
import time
import asyncio
import aiohttp
from typing import Dict, List, Optional
from utils.logger import logger
from database.db import MySQLPool
from core.limit_trade.limit_follow_models import LimitFollowStrategy, LimitFollowOrder
from core.limit_trade.limit_follow_db import LimitFollowDB

class LimitFollowExecutor:
    def __init__(self, db_pool: MySQLPool):
        self.db_pool = db_pool
        self.limit_follow_db = LimitFollowDB(db_pool)
        
        # 去重机制：记录每个跟单员的最后处理订单ID
        self.last_ord_ids = {}
        
        # 从数据库加载最新的订单ID
        self._load_latest_ord_ids()
        
        # 配置
        self.config = {
            'polling_interval': 5,  # 轮询间隔（秒）
            'trade_limit': 1,  # 每次获取的交易记录数量
            'okx_api_base': 'https://www.okx.com/priapi/v5/ecotrade/public/community/user/trade-records',  # OKX API基础URL
            'max_retry_attempts': 3,  # 最大重试次数
            'retry_delay': 5,  # 重试延迟（秒）
            'request_timeout': 10,  # 请求超时时间（秒）
            'enable_logging': True,  # 启用日志记录
            'log_level': 'INFO'  # 日志级别
        }
    
    def _load_latest_ord_ids(self):
        """从数据库加载最新的订单ID"""
        try:
            # 从limit_follow_logs表获取最新的订单ID
            query = """
                SELECT trader_unique_name, extra_data 
                FROM limit_follow_logs 
                WHERE log_level = 'INFO' 
                AND message LIKE %s
                ORDER BY created_at DESC
            """
            # 使用参数化查询避免格式化字符串问题
            records = self.db_pool.query(query, ('%发现新交易%',))
            
            for record in records:
                trader_unique_name = record['trader_unique_name']
                extra_data = json.loads(record['extra_data']) if record['extra_data'] else {}
                ord_id = extra_data.get('ord_id', '')
                if ord_id:
                    self.last_ord_ids[trader_unique_name] = ord_id
            
            # logger.info(f"从数据库加载了 {len(self.last_ord_ids)} 个跟单员的最新订单ID")
            
        except Exception as e:
            logger.error(f"加载最新订单ID失败: {e}")
    
    def get_trade_records(self, unique_name: str, limit: int = 1) -> List[Dict]:
        """获取交易记录"""
        params = {
            'uniqueName': unique_name,
            'instType': 'SWAP',
            'limit': limit
        }
        
        try:
            response = requests.get(self.config['okx_api_base'], params=params, timeout=10)
            response.raise_for_status()
            data = response.json()
            
            if data.get('code') == '0':
                return data.get('data', [])
            else:
                logger.error(f"获取交易记录失败: {data}")
                return []
                
        except Exception as e:
            logger.error(f"请求失败: {e}")
            return []
    
    async def get_trade_records_async(self, session: aiohttp.ClientSession, unique_name: str, limit: int = 1) -> List[Dict]:
        """异步获取交易记录"""
        params = {
            'uniqueName': unique_name,
            'instType': 'SWAP',
            'limit': limit
        }
        
        try:
            async with session.get(self.config['okx_api_base'], params=params, timeout=aiohttp.ClientTimeout(total=10)) as response:
                if response.status == 200:
                    data = await response.json()
                    if data.get('code') == '0':
                        return data.get('data', [])
                    else:
                        logger.error(f"获取交易记录失败: {data}")
                        return []
                else:
                    logger.error(f"请求失败，状态码: {response.status}")
                    return []
                    
        except Exception as e:
            logger.error(f"异步请求失败: {e}")
            return []
    
    # 同步方法已删除，使用异步方法替代
    
    def _log_new_trade(self, trader_unique_name: str, trade: Dict):
        """记录新交易到日志"""
        try:
            log_data = {
                'trader_unique_name': trader_unique_name,
                'ord_id': trade.get('ordId', ''),
                'side': trade.get('side', ''),
                'sz': trade.get('sz', ''),
                'avgPx': trade.get('avgPx', ''),
                'instId': trade.get('instId', ''),
                'cTime': trade.get('cTime', '')
            }
            
                    # 创建LimitFollowLog对象
            from model.limit_follow_models import LimitFollowLog
            log_entry = LimitFollowLog(
                log_level='INFO',
                message=f'发现新交易: {trader_unique_name} - {trade.get("ordId", "")}',
                trader_unique_name=trader_unique_name,
                extra_data=log_data
            )
            
            self.limit_follow_db.add_log(log_entry)
            
        except Exception as e:
            logger.error(f"记录新交易日志失败: {e}")
    
    def get_follow_strategies(self, trader_unique_name: str, symbol: str, pos_side: str) -> List[LimitFollowStrategy]:
        """获取跟单策略"""
        try:
            # 查找所有启用的策略，然后过滤出要跟随这个信号源的策略
            # 注意：trader_unique_name 实际上是信号源ID，不是跟单员ID
            all_strategies = self.limit_follow_db.get_strategies({'enabled': 1})
            
            # 过滤出匹配的策略
            matching_strategies = []
            for strategy in all_strategies:
                # 检查策略是否要跟随这个信号源
                # 这里需要根据业务逻辑来判断，暂时先返回所有策略
                if strategy.enabled:
                    matching_strategies.append(strategy)
            
            logger.info(f"找到 {len(matching_strategies)} 个匹配的跟单策略")
            return matching_strategies
            
        except Exception as e:
            logger.error(f"获取跟单策略失败: {e}")
            return []
    
    async def calculate_follow_order_size(self, strategy: LimitFollowStrategy, signal_price: float, signal_size: float) -> float:
        """计算跟单订单数量"""
        try:
            if strategy.follow_type == 'percentage':
                # 百分比跟单
                follow_percentage = strategy.follow_value / 100.0
                follow_size = signal_size * follow_percentage
            else:
                # 固定数量跟单
                follow_size = strategy.follow_value
            
            # 应用最小/最大限制
            min_size = strategy.min_follow_value
            max_size = strategy.max_follow_value
            
            if strategy.follow_type == 'percentage':
                min_size = signal_size * (min_size / 100.0)
                max_size = signal_size * (max_size / 100.0)
            
            follow_size = max(min_size, min(follow_size, max_size))
            
            # 如果启用按比例开仓，根据净杠杆控制调整数量
            if strategy.proportional_position:
                follow_size = await self._adjust_size_by_leverage(strategy, follow_size, signal_price)
            
            # 确保数量符合合约要求（这里需要根据具体合约调整）
            # 对于USDT合约，通常最小数量单位是0.01
            min_lot_size = 0.01  # 这个值应该从合约信息中获取
            follow_size = round(follow_size / min_lot_size) * min_lot_size
            
            logger.info(f"跟单数量计算: 信号数量={signal_size}, 跟单比例={strategy.follow_value}%, 计算结果={follow_size}")
            return follow_size
            
        except Exception as e:
            logger.error(f"计算跟单数量失败: {e}")
            return 0.0
    
    async def _adjust_size_by_leverage(self, strategy: LimitFollowStrategy, base_size: float, signal_price: float) -> float:
        """根据净杠杆控制调整开仓数量"""
        try:
            customer_uid = strategy.customer_uid
            symbol = strategy.symbol
            
            logger.info(f"按比例开仓: 策略={strategy.strategy_name}, 基础数量={base_size}, 最大净杠杆={strategy.max_net_leverage}")
            
            # 1. 获取客户当前持仓信息
            current_positions = await self._get_customer_positions(customer_uid, symbol)
            
            # 2. 获取客户账户余额和保证金信息
            account_info = await self._get_customer_account_info(customer_uid, symbol)
            
            if not account_info:
                logger.warning(f"无法获取客户账户信息: {customer_uid}")
                return base_size
            
            # 3. 计算当前净杠杆
            current_leverage = self._calculate_current_leverage(current_positions, account_info, signal_price)
            
            # 4. 根据最大净杠杆限制调整数量
            adjusted_size = self._adjust_size_by_leverage_limit(
                base_size, current_leverage, strategy.max_net_leverage, 
                account_info, signal_price
            )
            
            logger.info(f"净杠杆调整: 当前杠杆={current_leverage:.2f}, 最大杠杆={strategy.max_net_leverage}, 调整后数量={adjusted_size}")
            
            return adjusted_size
            
        except Exception as e:
            logger.error(f"根据净杠杆调整数量失败: {e}")
            return base_size
    
    async def _get_customer_positions(self, customer_uid: str, symbol: str) -> List[Dict]:
        """获取客户当前持仓"""
        try:
            # 直接从OKX API获取实时持仓信息
            if not hasattr(self, 'limit_follow_service'):
                from limit_follow_service import LimitFollowService
                self.limit_follow_service = LimitFollowService(self.db_pool)
            
            # 获取客户持仓
            positions = await self.limit_follow_service._get_customer_positions(customer_uid, symbol)
            
            if not positions:
                logger.info(f"客户 {customer_uid} 在 {symbol} 上没有持仓")
                return []
            
            logger.info(f"获取到客户 {customer_uid} 在 {symbol} 上的 {len(positions)} 个持仓")
            return positions
            
        except Exception as e:
            logger.error(f"获取客户持仓失败: {e}")
            return []
    
    async def _get_customer_account_info(self, customer_uid, symbol: str) -> Optional[Dict]:
        """获取客户账户信息"""
        try:
            # 直接从OKX API获取实时账户信息
            if not hasattr(self, 'limit_follow_service'):
                from limit_follow_service import LimitFollowService
                self.limit_follow_service = LimitFollowService(self.db_pool)
            
            # 获取账户余额和保证金信息
            account_info = await self.limit_follow_service._get_customer_account_info(customer_uid)
            
            return account_info
            
        except Exception as e:
            logger.error(f"获取客户账户信息失败: {e}")
            return None
    
    def _calculate_current_leverage(self, positions: List[Dict], account_info: Dict, current_price: float) -> float:
        """计算当前净杠杆"""
        try:
            if not positions or not account_info:
                return 0.0
            
            # 计算总持仓价值
            total_position_value = 0.0
            for position in positions:
                pos_size = float(position.get('pos', 0))
                pos_side = position.get('pos_side', 'long')
                
                # 根据持仓方向计算价值
                if pos_side == 'long':
                    position_value = pos_size * current_price
                else:  # short
                    position_value = pos_size * current_price
                
                total_position_value += position_value
            
            # 获取可用保证金
            available_margin = float(account_info.get('available_balance', 0))
            
            if available_margin <= 0:
                logger.warning("可用保证金为0，无法计算杠杆")
                return float('inf')  # 返回无穷大表示风险极高
            
            # 计算净杠杆 = 总持仓价值 / 可用保证金
            current_leverage = total_position_value / available_margin
            
            logger.info(f"杠杆计算: 总持仓价值={total_position_value:.2f}, 可用保证金={available_margin:.2f}, 当前杠杆={current_leverage:.2f}")
            
            return current_leverage
            
        except Exception as e:
            logger.error(f"计算当前杠杆失败: {e}")
            return 0.0
    
    def _adjust_size_by_leverage_limit(self, base_size: float, current_leverage: float, 
                                     max_leverage: float, account_info: Dict, signal_price: float) -> float:
        """根据最大杠杆限制调整开仓数量"""
        try:
            if current_leverage >= max_leverage:
                logger.warning(f"当前杠杆 {current_leverage:.2f} 已达到最大限制 {max_leverage}, 不允许开新仓")
                return 0.0
            
            # 计算剩余可用杠杆
            remaining_leverage = max_leverage - current_leverage
            
            # 获取可用保证金
            available_margin = float(account_info.get('available_balance', 0))
            
            # 计算基于剩余杠杆的最大可开仓价值
            max_position_value = available_margin * remaining_leverage
            
            # 计算基于剩余杠杆的最大可开仓数量
            max_position_size = max_position_value / signal_price
            
            # 取较小值作为最终开仓数量
            adjusted_size = min(base_size, max_position_size)
            
            # 确保数量不为负数
            adjusted_size = max(0, adjusted_size)
            
            logger.info(f"杠杆限制调整: 剩余杠杆={remaining_leverage:.2f}, 最大可开仓价值={max_position_value:.2f}, 调整后数量={adjusted_size}")
            
            return adjusted_size
            
        except Exception as e:
            logger.error(f"根据杠杆限制调整数量失败: {e}")
            return base_size
    
    async def create_follow_orders(self, strategy: LimitFollowStrategy, trade: Dict, trade_direction: str) -> List[LimitFollowOrder]:
        """创建跟单订单 - 按价格偏移策略"""
        try:
            side = trade.get('side', '')
            sz = float(trade.get('sz', '0'))
            avg_px = float(trade.get('avgPx', '0'))
            inst_id = trade.get('instId', '')
            ord_id = trade.get('ordId', '')
            
            # 使用传入的trade_direction
            follow_side = trade_direction
            
            # 计算跟单数量（按策略配置的百分比）
            follow_size = await self.calculate_follow_order_size(strategy, avg_px, sz)
            if follow_size <= 0:
                logger.warning(f"跟单数量为0，跳过创建订单")
                return []
            
            # 创建跟单订单
            orders = []
            max_orders = strategy.max_orders_per_signal
            
            # 根据策略配置创建多个不同价位的订单
            for i in range(max_orders):
                # 计算价格偏移百分比 (1%, 2%, 3%, 4%)
                price_offset_percent = (i + 1) * strategy.follow_value / 100.0
                
                # 计算目标价格
                if follow_side == 'long':
                    # 多仓跟单：比跟单员便宜
                    target_price = avg_px * (1 - price_offset_percent)
                else:
                    # 空仓跟单：比跟单员贵
                    target_price = avg_px * (1 + price_offset_percent)
                
                # 订单数量就是计算出的 follow_size（所有订单数量相同）
                order_size = follow_size
                
                # 创建订单对象
                order = LimitFollowOrder(
                    order_uid=f"FOLLOW_{ord_id}_{strategy.id}_{strategy.customer_uid}_{i+1}",
                    strategy_id=strategy.id,
                    trader_unique_name=strategy.trader_unique_name,
                    customer_uid=strategy.customer_uid,
                    symbol=inst_id,
                    pos_side=follow_side,
                    follow_value=price_offset_percent * 100,  # 记录实际使用的偏移百分比
                    target_price=target_price,
                    order_size=order_size,
                    order_type='limit',
                    status='pending'
                )
                
                orders.append(order)
            
            return orders
            
        except Exception as e:
            logger.error(f"创建跟单订单失败: {e}")
            return []
    
    async def execute_follow_orders(self, orders: List[LimitFollowOrder]) -> bool:
        """执行跟单订单"""
        try:
            success_count = 0
            
            # 使用已初始化的限价跟单服务
            if not hasattr(self, 'limit_follow_service'):
                from core.limit_trade.limit_follow_service import LimitFollowService
                self.limit_follow_service = LimitFollowService(self.db_pool)
            
            limit_follow_service = self.limit_follow_service
            
            for order in orders:
                # 保存订单到数据库
                if self.limit_follow_db.create_order(order):
                    logger.info(f"跟单订单创建成功: {order.order_uid}")
                    
                    # 向交易所发送实际订单
                    import asyncio
                    try:
                        # 尝试获取现有事件循环
                        loop = asyncio.get_event_loop()
                        if loop.is_running():
                            # 如果事件循环正在运行，创建任务
                            task = loop.create_task(limit_follow_service._submit_order_to_exchange(order))
                            # 等待任务完成
                            result = await task
                        else:
                            # 如果事件循环没有运行，运行到完成
                            result = asyncio.run(limit_follow_service._submit_order_to_exchange(order))
                    except RuntimeError:
                        # 如果没有事件循环，创建一个新的
                        result = asyncio.run(limit_follow_service._submit_order_to_exchange(order))
                    
                    if result:
                        success_count += 1
                        logger.success(f"跟单订单发送到交易所成功: {order.order_uid}")
                        
                        # 记录成功日志
                        from model.limit_follow_models import LimitFollowLog
                        log_entry = LimitFollowLog(
                            log_level='INFO',
                            message=f'跟单订单发送到交易所成功: {order.order_uid}',
                            order_uid=order.order_uid,
                            strategy_id=order.strategy_id,
                            customer_uid=order.customer_uid,
                            trader_unique_name=order.trader_unique_name,
                            extra_data={
                                'target_price': order.target_price,
                                'order_size': order.order_size,
                                'follow_value': order.follow_value,
                                'status': 'sent_to_exchange'
                            }
                        )
                        self.limit_follow_db.add_log(log_entry)
                    else:
                        logger.error(f"跟单订单发送到交易所失败: {order.order_uid}")
                        
                        # 记录失败日志
                        from model.limit_follow_models import LimitFollowLog
                        log_entry = LimitFollowLog(
                            log_level='ERROR',
                            message=f'跟单订单发送到交易所失败: {order.order_uid}',
                            order_uid=order.order_uid,
                            strategy_id=order.strategy_id,
                            customer_uid=order.customer_uid,
                            trader_unique_name=order.trader_unique_name,
                            extra_data={
                                'target_price': order.target_price,
                                'order_size': order.order_size,
                                'follow_value': order.follow_value,
                                'status': 'exchange_failed'
                            }
                        )
                        self.limit_follow_db.add_log(log_entry)
                else:
                    logger.error(f"跟单订单创建失败: {order.order_uid}")
            
            logger.info(f"跟单订单执行完成: {success_count}/{len(orders)} 成功")
            return success_count > 0
            
        except Exception as e:
            logger.error(f"执行跟单订单失败: {e}")
            return False
    
    async def process_new_trade(self, trader_unique_name: str, trade: Dict):
        """处理新交易"""
        try:
            side = trade.get('side', '')
            pos_side = trade.get('posSide', '')
            sz = float(trade.get('sz', '0'))
            avg_px = float(trade.get('avgPx', '0'))
            inst_id = trade.get('instId', '')
            ord_id = trade.get('ordId', '')
            
            logger.info(f"处理新交易: {trader_unique_name} {side} {sz} {inst_id} @ {avg_px}, posSide: {pos_side}")
            
            # 只处理posSide为long或short的情况，其他情况跳过
            if pos_side not in ['long', 'short']:
                logger.info(f"跳过非双向开仓模式: posSide={pos_side}")
                return
            
            # 确定持仓方向和操作类型
            trade_direction, operation_type = self._analyze_trade_direction(side, pos_side)
            
            if not trade_direction:
                logger.error(f"无法确定交易方向: side={side}, posSide={pos_side}")
                return
            
            # 只处理开仓操作，不处理平仓操作
            if operation_type == 'close':
                logger.info(f"跳过平仓操作: {side} {pos_side}")
                return
            
            logger.info(f"交易解析结果: 方向={trade_direction}, 操作类型={operation_type}")
            
            # 获取跟单策略
            strategies = self.get_follow_strategies(trader_unique_name, inst_id, trade_direction)
            
            if not strategies:
                logger.info(f"没有找到匹配的跟单策略: {trader_unique_name} {inst_id} {trade_direction}")
                return
            
            # 为每个策略创建跟单订单
            for strategy in strategies:
                logger.info(f"执行跟单策略: {strategy.strategy_name} (客户: {strategy.customer_uid})")
                
                # 创建跟单订单
                orders = await self.create_follow_orders(strategy, trade, trade_direction)
                
                if orders:
                    # 执行跟单订单
                    try:
                        result = await self.execute_follow_orders(orders)
                        if result:
                            logger.success(f"跟单策略执行成功: {strategy.strategy_name}")
                        else:
                            logger.error(f"跟单策略执行失败: {strategy.strategy_name}")
                    except Exception as e:
                        logger.error(f"执行跟单策略失败: {strategy.strategy_name} - {e}")
                else:
                    logger.warning(f"没有创建任何跟单订单: {strategy.strategy_name}")
            
        except Exception as e:
            logger.error(f"处理新交易失败: {e}")

    def _analyze_trade_direction(self, side: str, pos_side: str) -> tuple:
        """
        分析交易方向和操作类型（只处理双向开仓模式）
        
        Args:
            side: 交易方向 ('buy' 或 'sell')
            pos_side: 持仓方向 ('long' 或 'short')
        
        Returns:
            tuple: (trade_direction, operation_type)
            - trade_direction: 'long' 或 'short' 或 None
            - operation_type: 'open' 或 'close'
        """
        try:
            # 只处理双向开仓模式
            if pos_side == 'long':
                if side == 'buy':
                    return 'long', 'open'  # 开多仓
                elif side == 'sell':
                    return 'long', 'close'  # 平多仓
                else:
                    return None, None
            
            elif pos_side == 'short':
                if side == 'buy':
                    return 'short', 'open'  # 开空仓
                elif side == 'sell':
                    return 'short', 'close'  # 平空仓
                else:
                    return None, None
            
            else:
                # 这里不应该到达，因为外层已经过滤了
                logger.warning(f"意外的posSide: {pos_side}")
                return None, None
                
        except Exception as e:
            logger.error(f"分析交易方向失败: {e}")
            return None, None

    # 同步检查方法已删除，使用异步方法替代
    
    async def check_trader_async(self, session: aiohttp.ClientSession, trader_unique_name: str):
        """异步检查单个跟单员"""
        try:
            logger.info(f"检查跟单员: {trader_unique_name}")
            
            # 异步获取交易记录
            trades = await self.get_trade_records_async(session, trader_unique_name, self.config['trade_limit'])
            new_trades = []
            
            if trades:
                # 获取最新一条交易
                latest_trade = trades[0]
                ord_id = latest_trade.get('ordId', '')
                
                if ord_id:
                    # 检查是否是新的订单ID
                    last_ord_id = self.last_ord_ids.get(trader_unique_name, '')
                    
                    if ord_id != last_ord_id:
                        # 新的订单ID，添加到新交易列表
                        new_trades.append(latest_trade)
                        # 更新最后处理的订单ID
                        self.last_ord_ids[trader_unique_name] = ord_id
                        
                        # 记录到日志
                        self._log_new_trade(trader_unique_name, latest_trade)
                        
                        logger.info(f"发现新交易: {trader_unique_name} - {ord_id}")
                    else:
                        logger.info(f"订单已处理: {trader_unique_name} - {ord_id}")
            
            if new_trades:
                logger.info(f"发现 {len(new_trades)} 笔新交易")
                for trade in new_trades:
                    await self.process_new_trade(trader_unique_name, trade)
            else:
                logger.info(f"没有新交易")
                
        except Exception as e:
            logger.error(f"检查跟单员失败: {e}")
    
    def get_monitored_traders(self) -> List[str]:
        """获取所有被监控的跟单员"""
        try:
            # 从数据库获取所有启用的策略中的跟单员
            query = """
                SELECT DISTINCT trader_unique_name 
                FROM limit_follow_strategies 
                WHERE enabled = 1 
                AND follow_mode = 'follow_trader'
            """
            # 修复：传递空元组作为参数，因为查询没有占位符
            records = self.db_pool.query(query, ())
            
            traders = [record['trader_unique_name'] for record in records]
            logger.info(f"获取到 {len(traders)} 个被监控的跟单员")
            
            return traders
            
        except Exception as e:
            logger.error(f"获取被监控跟单员失败: {e}")
            return []
    
    # 同步监控方法已删除，使用异步方法替代
    
    async def run_monitoring_async(self):
        """运行并发监控"""
        logger.info("开始并发限价跟单监控...")
        
        # 创建HTTP会话
        async with aiohttp.ClientSession() as session:
            while True:
                try:
                    # 获取被监控的跟单员
                    traders = self.get_monitored_traders()
                    
                    if not traders:
                        logger.info("没有需要监控的跟单员")
                        await asyncio.sleep(self.config['polling_interval'])
                        continue
                    
                    logger.info(f"开始并发检查 {len(traders)} 个跟单员...")
                    
                    # 创建所有跟单员的检查任务
                    tasks = []
                    for trader in traders:
                        task = self.check_trader_async(session, trader)
                        tasks.append(task)
                    
                    # 并发执行所有任务
                    start_time = time.time()
                    await asyncio.gather(*tasks, return_exceptions=True)
                    end_time = time.time()
                    
                    execution_time = end_time - start_time
                    logger.info(f"并发检查完成，耗时: {execution_time:.2f} 秒")
                    
                    # 等待下次轮询
                    interval = self.config['polling_interval']
                    logger.info(f"等待 {interval} 秒后进行下次检查...")
                    await asyncio.sleep(interval)
                    
                except KeyboardInterrupt:
                    logger.info("监控已停止")
                    break
                except Exception as e:
                    logger.error(f"监控异常: {e}")
                    await asyncio.sleep(10)  # 异常后等待10秒再继续


async def main():
    """主函数"""
    # 初始化数据库连接
    from config import get_mysql_config
    db_pool = MySQLPool(
        **get_mysql_config()
    )
    
    # 创建跟单执行器
    executor = LimitFollowExecutor(db_pool)
    
    # 开始监控
    await executor.run_monitoring_async()

def main_sync():
    """同步主函数"""
    asyncio.run(main())

if __name__ == "__main__":
    main_sync() 