#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
转发交易服务
根据消息转发系统的 TradingView 消息自动执行交易
"""

import asyncio
import json
from typing import Dict, List, Optional, Any
from datetime import datetime
from decimal import Decimal

from utils.logger import get_logger
from database.db import MySQLPool
from core.message_forward.models import Message, PlatformType
from core.market_trade.trade_service import TradeService
from exchange.exchange_factory import create_exchange_client
from exchange.base_client import OrderRequest, OrderSide, OrderType

logger = get_logger(__name__)


class ForwardTradeService:
    """转发交易服务"""
    
    def __init__(self, db_pool: MySQLPool):
        self.db_pool = db_pool
        self.trade_service = TradeService(db_pool)
        self.enabled = True
        self.configs_cache: Dict[int, Dict] = {}  # 配置缓存
        self._last_cache_update = None
        
    async def initialize(self):
        """初始化服务"""
        await self._refresh_configs_cache()
        logger.info(f"✅ 转发交易服务初始化完成，已加载 {len(self.configs_cache)} 个配置")
    
    async def _refresh_configs_cache(self):
        """刷新配置缓存"""
        try:
            query = """
                SELECT 
                    ftc.id,
                    ftc.config_name,
                    ftc.user_id,
                    ftc.source_platform_id,
                    ftc.source_platform_name,
                    ftc.customer_uid,
                    ftc.customer_name,
                    ftc.amount_ratio,
                    ftc.min_amount,
                    ftc.max_amount,
                    ftc.enabled,
                    ftc.symbol_filter,
                    ftc.action_filter,
                    ftc.risk_control,
                    c.exchange,
                    c.api_key,
                    c.api_secret,
                    c.passphrase,
                    c.is_demo
                FROM forward_trade_configs ftc
                LEFT JOIN customers c ON ftc.customer_uid COLLATE utf8mb4_general_ci = c.customer_uid COLLATE utf8mb4_general_ci
                WHERE ftc.enabled = 1
            """
            rows = self.db_pool.query(query)
            
            self.configs_cache = {}
            for row in rows:
                config = {
                    'id': row['id'],
                    'config_name': row['config_name'],
                    'user_id': row['user_id'],
                    'source_platform_id': row['source_platform_id'],
                    'source_platform_name': row['source_platform_name'],
                    'customer_uid': row['customer_uid'],
                    'customer_name': row['customer_name'],
                    'amount_ratio': float(row['amount_ratio']),
                    'min_amount': float(row['min_amount']) if row['min_amount'] else None,
                    'max_amount': float(row['max_amount']) if row['max_amount'] else None,
                    'symbol_filter': json.loads(row['symbol_filter']) if row['symbol_filter'] else None,
                    'action_filter': json.loads(row['action_filter']) if row['action_filter'] else None,
                    'risk_control': json.loads(row['risk_control']) if row['risk_control'] else {},
                    'exchange': row['exchange'],
                    'api_key': row['api_key'],
                    'api_secret': row['api_secret'],
                    'passphrase': row['passphrase'],
                    'is_demo': bool(row['is_demo']) if row['is_demo'] is not None else False
                }
                self.configs_cache[row['id']] = config
            
            self._last_cache_update = datetime.now()
            logger.info(f"✅ 已刷新转发交易配置缓存，共 {len(self.configs_cache)} 个配置")
            
        except Exception as e:
            logger.error(f"刷新转发交易配置缓存失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
    
    async def handle_message(self, message: Message):
        """
        处理接收到的消息
        
        Args:
            message: 消息对象
        """
        if not self.enabled:
            return
        
        # 只处理 TradingView 平台的消息
        if message.source_platform != PlatformType.TRADINGVIEW:
            return
        
        # 检查是否有匹配的配置
        source_platform_id = getattr(message, 'source_platform_id', None)
        if not source_platform_id:
            # 如果没有 source_platform_id，尝试从 extra_data 获取
            source_platform_id = message.extra_data.get('source_platform_id')
        
        if not source_platform_id:
            logger.debug("消息没有 source_platform_id，跳过转发交易处理")
            return
        
        # 查找匹配的配置
        matching_configs = []
        for config_id, config in self.configs_cache.items():
            if config['source_platform_id'] == source_platform_id:
                matching_configs.append(config)
        
        if not matching_configs:
            logger.debug(f"没有找到匹配的转发交易配置（source_platform_id: {source_platform_id}）")
            return
        
        logger.info(f"📊 找到 {len(matching_configs)} 个匹配的转发交易配置")
        
        # 解析交易信息
        trade_info = self._parse_trade_info(message)
        if not trade_info:
            logger.warning("无法解析交易信息，跳过转发交易")
            return
        
        # 执行每个配置的交易
        for config in matching_configs:
            try:
                await self._execute_trade(config, trade_info, message)
            except Exception as e:
                logger.error(f"执行转发交易失败（配置ID: {config['id']}）: {e}")
                import traceback
                logger.error(traceback.format_exc())
    
    def _parse_trade_info(self, message: Message) -> Optional[Dict[str, Any]]:
        """
        从消息中解析交易信息
        
        Args:
            message: 消息对象
            
        Returns:
            交易信息字典，包含 symbol, action, price, quantity 等
        """
        try:
            # 从 extra_data 中获取交易信息
            trade_info = message.extra_data.get('trade_info', {})
            if not trade_info:
                logger.warning("消息中没有 trade_info，尝试从内容解析")
                return None
            
            original_data = trade_info.get('original_data', {})
            
            # 提取交易信息
            symbol = original_data.get('symbol') or trade_info.get('symbol')
            action = original_data.get('action') or trade_info.get('action')
            direct = original_data.get('direct') or trade_info.get('direct')
            price = original_data.get('price') or trade_info.get('price')
            quantity = original_data.get('quantity') or trade_info.get('quantity')
            message_text = original_data.get('message') or trade_info.get('message', '')
            
            if not symbol or not action or not price:
                logger.warning(f"交易信息不完整: symbol={symbol}, action={action}, price={price}")
                return None
            
            # 标准化交易对格式
            if not symbol.endswith('USDT') and not symbol.endswith('BTC') and not symbol.endswith('ETH'):
                symbol = f"{symbol}USDT"
            
            # 解析交易动作
            trade_action = self._parse_trade_action(action, direct)
            if not trade_action:
                logger.warning(f"无法解析交易动作: action={action}, direct={direct}")
                return None
            
            return {
                'symbol': symbol,
                'action': trade_action,
                'direct': direct,
                'price': float(price),
                'quantity': float(quantity) if quantity else None,
                'message': message_text,
                'original_data': original_data
            }
            
        except Exception as e:
            logger.error(f"解析交易信息失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return None
    
    def _parse_trade_action(self, action: str, direct: Optional[str] = None) -> Optional[str]:
        """
        解析交易动作
        
        Args:
            action: 动作（BUY/SELL）
            direct: 方向（LONG/SHORT）
            
        Returns:
            交易动作（buy/sell/close）
        """
        action = str(action).upper()
        direct = str(direct).upper() if direct else None
        
        if direct:
            # 有 direct 字段，需要结合 action 和 direct 判断
            if direct in ['LONG', '多', '做多']:
                if action in ['BUY', '买入']:
                    return 'buy'  # 开多
                elif action in ['SELL', '卖出']:
                    return 'close'  # 平多
            elif direct in ['SHORT', '空', '做空']:
                if action in ['SELL', '卖出']:
                    return 'sell'  # 开空
                elif action in ['BUY', '买入']:
                    return 'close'  # 平空
        else:
            # 没有 direct 字段，只根据 action 判断
            if action in ['BUY', 'LONG', '开多', '做多', '买入']:
                return 'buy'
            elif action in ['SELL', 'SHORT', '开空', '做空', '卖出']:
                return 'sell'
            elif action in ['CLOSE', '平仓', '关闭']:
                return 'close'
        
        return None
    
    async def _execute_trade(self, config: Dict, trade_info: Dict, message: Message):
        """
        执行转发交易
        
        Args:
            config: 转发交易配置
            trade_info: 交易信息
            message: 原始消息
        """
        try:
            # 检查交易对过滤
            if config['symbol_filter']:
                if trade_info['symbol'] not in config['symbol_filter']:
                    logger.debug(f"交易对 {trade_info['symbol']} 不在过滤列表中，跳过")
                    return
            
            # 检查交易动作过滤
            if config['action_filter']:
                if trade_info['action'] not in config['action_filter']:
                    logger.debug(f"交易动作 {trade_info['action']} 不在过滤列表中，跳过")
                    return
            
            # 计算交易金额
            amount = self._calculate_trade_amount(config, trade_info)
            if not amount:
                logger.warning("无法计算交易金额，跳过")
                return
            
            # 检查金额限制
            if config['min_amount'] and amount < config['min_amount']:
                logger.warning(f"交易金额 {amount} 小于最小金额 {config['min_amount']}，跳过")
                return
            
            if config['max_amount'] and amount > config['max_amount']:
                logger.warning(f"交易金额 {amount} 大于最大金额 {config['max_amount']}，跳过")
                amount = config['max_amount']
            
            # 创建执行记录
            record_id = self._create_trade_record(config, trade_info, message, amount)
            
            # 执行交易
            logger.info(f"📈 执行转发交易: {config['config_name']} - {trade_info['symbol']} {trade_info['action']} @ {trade_info['price']}, 金额: {amount} USDT")
            
            # 创建交易所客户端
            try:
                exchange_client = create_exchange_client(
                    exchange=config['exchange'].lower(),
                    client_type='rest',
                    api_key=config['api_key'],
                    api_secret=config['api_secret'],
                    passphrase=config.get('passphrase'),  # customers 表有 passphrase
                    is_demo=config.get('is_demo', False)
                )
            except Exception as e:
                raise Exception(f"创建交易所客户端失败: {e}")
            
            # 计算数量（根据金额和价格）
            quantity = amount / trade_info['price']
            
            # 根据交易动作执行订单（使用统一接口）
            order_result = None
            if trade_info['action'] == 'buy':
                # 开多仓
                try:
                    # 使用统一接口（兼容旧格式）
                    response = await exchange_client.place_order(
                        symbol=trade_info['symbol'],
                        side='buy',
                        order_type='market',
                        quantity=quantity,
                        tdMode='cross'  # 全仓模式
                    )
                    
                    # 解析响应（兼容不同格式）
                    if isinstance(response, dict):
                        if 'unified_format' in response:
                            unified = response['unified_format']
                            order_id = unified.get('order_id') or (response.get('data', [{}])[0].get('ordId') if response.get('data') else None)
                        elif response.get('data') and len(response['data']) > 0:
                            order_id = response['data'][0].get('ordId')
                        else:
                            order_id = response.get('order_id')
                    else:
                        order_id = getattr(response, 'order_id', None)
                    
                    order_result = {
                        'status': 'success',
                        'order_id': order_id,
                        'message': '买入订单已提交'
                    }
                except Exception as e:
                    raise Exception(f"买入订单失败: {e}")
                    
            elif trade_info['action'] == 'sell':
                # 开空仓
                try:
                    response = await exchange_client.place_order(
                        symbol=trade_info['symbol'],
                        side='sell',
                        order_type='market',
                        quantity=quantity,
                        tdMode='cross'
                    )
                    
                    # 解析响应
                    if isinstance(response, dict):
                        if 'unified_format' in response:
                            unified = response['unified_format']
                            order_id = unified.get('order_id') or (response.get('data', [{}])[0].get('ordId') if response.get('data') else None)
                        elif response.get('data') and len(response['data']) > 0:
                            order_id = response['data'][0].get('ordId')
                        else:
                            order_id = response.get('order_id')
                    else:
                        order_id = getattr(response, 'order_id', None)
                    
                    order_result = {
                        'status': 'success',
                        'order_id': order_id,
                        'message': '卖出订单已提交'
                    }
                except Exception as e:
                    raise Exception(f"卖出订单失败: {e}")
                    
            elif trade_info['action'] == 'close':
                # 平仓：先查询持仓，然后平掉所有持仓
                try:
                    positions_response = await exchange_client.get_positions(symbol=trade_info['symbol'])
                    
                    # 解析持仓响应（统一接口返回字典格式）
                    if isinstance(positions_response, dict):
                        if positions_response.get('success') and positions_response.get('positions'):
                            positions = positions_response['positions']
                        elif positions_response.get('positions'):
                            positions = positions_response['positions']
                        else:
                            positions = []
                    elif isinstance(positions_response, list):
                        positions = positions_response
                    else:
                        positions = []
                    
                    if not positions:
                        order_result = {
                            'status': 'success',
                            'message': '没有持仓，无需平仓'
                        }
                    else:
                        # 平掉所有持仓
                        closed_count = 0
                        last_order_id = None
                        for pos in positions:
                            # 解析持仓大小（兼容不同格式）
                            pos_size = 0
                            if isinstance(pos, dict):
                                pos_size = float(pos.get('size', 0) or pos.get('position_size', 0) or 0)
                                pos_side = pos.get('pos_side', pos.get('position_side', 'long'))
                            else:
                                pos_size = float(getattr(pos, 'size', 0) or 0)
                                pos_side = getattr(pos, 'pos_side', 'long')
                            
                            if abs(pos_size) > 0:
                                # 根据持仓方向决定平仓方向
                                close_side = 'sell' if pos_side == 'long' else 'buy'
                                
                                close_response = await exchange_client.place_order(
                                    symbol=trade_info['symbol'],
                                    side=close_side,
                                    order_type='market',
                                    quantity=abs(pos_size),
                                    tdMode='cross',
                                    reduceOnly=True  # 只减仓
                                )
                                
                                # 解析订单ID
                                if isinstance(close_response, dict):
                                    if 'unified_format' in close_response:
                                        unified = close_response['unified_format']
                                        last_order_id = unified.get('order_id')
                                    elif close_response.get('data') and len(close_response['data']) > 0:
                                        last_order_id = close_response['data'][0].get('ordId')
                                    else:
                                        last_order_id = close_response.get('order_id')
                                else:
                                    last_order_id = getattr(close_response, 'order_id', None)
                                
                                closed_count += 1
                                
                        order_result = {
                            'status': 'success',
                            'message': f'已平仓 {closed_count} 个持仓',
                            'order_id': last_order_id
                        }
                except Exception as e:
                    raise Exception(f"平仓失败: {e}")
            else:
                raise ValueError(f"未知的交易动作: {trade_info['action']}")
            
            # 更新执行记录
            if order_result:
                self._update_trade_record(record_id, order_result, 'success')
                logger.info(f"✅ 转发交易执行成功: {config['config_name']} - 订单ID: {order_result.get('order_id', 'N/A')}")
            else:
                raise Exception("订单执行失败：未返回结果")
            
        except Exception as e:
            logger.error(f"执行转发交易失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
            
            # 更新执行记录
            if 'record_id' in locals():
                self._update_trade_record(record_id, None, 'failed', str(e))
    
    def _calculate_trade_amount(self, config: Dict, trade_info: Dict) -> Optional[float]:
        """
        计算交易金额
        
        Args:
            config: 转发交易配置
            trade_info: 交易信息
            
        Returns:
            交易金额（USDT）
        """
        try:
            # 如果原始消息有 quantity，使用 quantity * price
            if trade_info.get('quantity'):
                base_amount = trade_info['quantity'] * trade_info['price']
            else:
                # 否则使用固定金额（需要从配置中获取）
                base_amount = config.get('default_amount', 100.0)  # 默认 100 USDT
            
            # 应用金额比例
            amount = base_amount * config['amount_ratio']
            
            return amount
            
        except Exception as e:
            logger.error(f"计算交易金额失败: {e}")
            return None
    
    def _create_trade_record(self, config: Dict, trade_info: Dict, message: Message, amount: float) -> int:
        """创建交易执行记录"""
        try:
            query = """
                INSERT INTO forward_trade_records 
                (config_id, message_id, source_platform_id, symbol, action, direct, price, quantity, amount, amount_ratio, execution_status)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """
            params = (
                config['id'],
                message.message_id,
                config['source_platform_id'],
                trade_info['symbol'],
                trade_info['action'],
                trade_info.get('direct'),
                trade_info['price'],
                trade_info.get('quantity'),
                amount,
                config['amount_ratio'],
                'pending'
            )
            return self.db_pool.execute(query, params)
        except Exception as e:
            logger.error(f"创建交易执行记录失败: {e}")
            return 0
    
    def _update_trade_record(self, record_id: int, order_result: Optional[Dict], status: str, error_message: Optional[str] = None):
        """更新交易执行记录"""
        try:
            if status == 'success':
                query = """
                    UPDATE forward_trade_records 
                    SET order_id = %s, order_status = %s, execution_status = %s, executed_at = NOW()
                    WHERE id = %s
                """
                params = (
                    order_result.get('order_id') if order_result else None,
                    order_result.get('status') if order_result else None,
                    status,
                    record_id
                )
            else:
                query = """
                    UPDATE forward_trade_records 
                    SET execution_status = %s, error_message = %s, executed_at = NOW()
                    WHERE id = %s
                """
                params = (status, error_message, record_id)
            
            self.db_pool.execute(query, params)
        except Exception as e:
            logger.error(f"更新交易执行记录失败: {e}")

