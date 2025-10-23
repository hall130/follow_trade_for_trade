from database.db import (
    get_enabled_signal_accounts, upsert_signal_account_asset, insert_signal_account_trade,
    get_strategies_by_signal_account, get_rules_by_strategy, get_customers_by_strategy_and_rule,
    get_signal_source_init_asset, update_signal_source_init_asset, update_customer_trade_order_id,
    update_customer_trade_open_px, close_customer_trade, close_signal_account_trade,
    get_rule_by_signal_and_strategy, get_rule_by_signal_source, update_signal_account_trade_close_volume_contract
)
from model.models import Rule, Strategy, SignalAccount, Customer, CustomerTrade
from core.market_trade.trade_service import TradeService, get_global_is_demo
import asyncio
from utils.logger import logger
from dataclasses import fields
import traceback
import time
from exchange.exchange_factory import create_exchange_client
from exchange.base_client import ExchangeType
from exchange.unified_ws_client import get_global_client_manager
# 导入合约配置
from config.contract_config import get_contract_sz_precision, get_contract_min_sz, get_contract_multiplier

# 导入屏蔽规则配置
from config.blocking_config import get_blocking_rules, get_blocked_symbols, is_signal_source_blocked

def safe_float(val, default=0.0):
    try:
        if val is None:
            return default
        return float(val)
    except Exception:
        return default

def get_global_is_demo():
    import os
    return int(os.environ.get('IS_DEMO', '1'))

class SignalService:
    """
    信号源监听与分发服务：
    - 负责监听信号源账户的资产和订单推送
    - 资产快照、信号源交易自动入库
    - 信号源有新成交订单时自动触发所有关联客户的跟单逻辑
    """
    def __init__(self, db_pool, trade_service: TradeService):
        self.db_pool = db_pool
        self.trade_service = trade_service
        # 限制信号队列大小，防止内存溢出
        self.signal_queue = asyncio.Queue(maxsize=1000)  # 最大1000条消息
        self._signal_consumer_task = None
        self._processing_follow_signals = set()  # 防止重复处理跟单信号
        self._processing_open_signals = set()    # 防止重复处理开仓信号
        self._processed_order_ids = set()        # 防止重复处理订单
        logger.info("信号服务初始化完成，信号队列大小限制: 1000")

    async def start_signal_consumer(self):
        if self._signal_consumer_task is None:
            self._signal_consumer_task = asyncio.create_task(self._signal_consumer())

    async def _signal_consumer(self):
        while True:
            signal_account, order = await self.signal_queue.get()
            try:
                await self._on_signal_trade_inner(signal_account, order)
            except Exception as e:
                import traceback
                logger.error(f"[信号队列] 消费信号异常: {e}\n{traceback.format_exc()}")
            finally:
                self.signal_queue.task_done()

    async def listen_signal_account(self, signal_account: SignalAccount):
        """监听信号源账户的资产和订单推送"""
        
        client = None
        reconnect_count = 0
        max_reconnect_attempts = 5
        
        while reconnect_count < max_reconnect_attempts:
            try:
                # 使用全局客户端管理器获取客户端
                client_manager = get_global_client_manager()
                client = await client_manager.get_client(
                    client_key=f"signal_{signal_account.source_uid}",
                    is_demo=signal_account.is_demo if hasattr(signal_account, 'is_demo') else False,
                    api_key=signal_account.api_key,
                    api_secret=signal_account.api_secret,
                    passphrase=signal_account.passphrase
                )
                    
                logger.info(f"[信号源监听] 开始监听信号源: {signal_account.source_uid}")
                
                async def on_account(data):
                    try:
                        if 'data' in data and isinstance(data['data'], list) and len(data['data']) > 0:
                            asset = safe_float(data['data'][0].get('totalEq'))
                            upsert_signal_account_asset(self.db_pool, signal_account.source_uid, asset)
                            init_asset = get_signal_source_init_asset(self.db_pool, signal_account.source_uid)
                            if init_asset is None:
                                update_signal_source_init_asset(self.db_pool, signal_account.source_uid, asset)
                        else:
                            logger.warning(f"signal_service.on_account: data 为空或格式异常: {data}")
                    except Exception as e:
                        logger.error(f"on_account回调异常: {e}\n{traceback.format_exc()}")

                async def on_order(data):
                    try:
                        from database.db import insert_signal_account_trade, close_signal_account_trade
                        for order in data['data']:
                            # 添加订单去重逻辑，避免重复处理
                            ordId = order.get('ordId')
                            if not ordId:
                                logger.warning(f"[信号源订单] ordId为空，跳过处理: {order}")
                                continue

                            # 检查是否已经处理过这个订单
                            if not hasattr(self, '_processed_order_ids'):
                                self._processed_order_ids = set()
                            
                            # 只对已成交的订单进行去重，未成交的订单不加入去重集合
                            if order['state'] == 'filled':
                                if ordId in self._processed_order_ids:
                                    logger.info(f"[信号源订单去重] 已成交订单{ordId}已处理过，跳过")
                                    continue
                                # 只有已成交的订单才加入去重集合
                                self._processed_order_ids.add(ordId)
                            else:
                                logger.info(f"[信号源订单] 跳过非filled状态订单: ordId={ordId}, state={order['state']}")
                                continue

                            # 精简日志输出
                            logger.info(
                                f"signal_service order: ordId={order.get('ordId')}, clOrdId={order.get('clOrdId')}, symbol={order.get('instId')}, side={order.get('side')}, posSide={order.get('posSide')}, ordType={order.get('ordType')}, state={order.get('state')}, sz={order.get('sz')}, avgPx={order.get('avgPx')}, cTime={order.get('cTime')}, uTime={order.get('uTime')}, code={order.get('code')}, msg={order.get('msg')}"
                            )

                            # 只处理filled状态的订单
                            if order['state'] != 'filled':
                                logger.info(f"[信号源订单] 跳过非filled状态订单: ordId={ordId}, state={order['state']}")
                                continue

                            # 统一用 target_uid 作为唯一标识
                            target_uid = order.get('clOrdId') or order.get('trade_uid')
                            ordId = order.get('ordId')
                            logger.info(f"signal_service target_uid初值: {target_uid}, ordId: {ordId}")
                            # 如果 target_uid 为空，直接用 ordId 兜底
                            if not target_uid and ordId:
                                target_uid = ordId
                                logger.info(f"signal_service on_order兜底: clOrdId为空，直接用ordId={ordId}作为target_uid")
                            logger.info(f"signal_service target_uid最终: {target_uid}, ordId: {ordId}, side: {order.get('side')}, posSide: {order.get('posSide')}, state: {order.get('state')}, reduceOnly: {order.get('reduceOnly')}")

                            # 信号源完整生命周期：开仓插入，平仓更新
                            if order.get('side') in ['buy', 'sell']:
                                avgPx = safe_float(order.get('avgPx')) or safe_float(order.get('fillPx'))
                                symbol = order.get('instId')
                                multiplier = get_contract_multiplier(symbol)
                                # 对于开仓订单，使用累计成交数量accFillSz，避免部分成交的问题
                                if order.get('reduceOnly') == 'true':
                                    # 减仓订单使用订单数量sz
                                    fill_sz = safe_float(order.get('sz'))
                                else:
                                    # 开仓订单使用累计成交数量accFillSz
                                    fill_sz = safe_float(order.get('accFillSz', order.get('sz')))
                                logger.info(f"[信号源订单解析] sz={order.get('sz')}, fillSz={order.get('fillSz')}, accFillSz={order.get('accFillSz')}, 最终fill_sz={fill_sz}")
                                volume_usdt = fill_sz * avgPx * multiplier
                                # 获取is_demo状态，用于所有逻辑
                                is_demo = get_global_is_demo()

                                # 判断是否为开仓信号
                                is_open_long = order['side'] == 'buy' and order['posSide'] == 'long'
                                is_open_short = order['side'] == 'sell' and order['posSide'] == 'short'
                                is_close_long = order['side'] == 'sell' and order['posSide'] == 'long'
                                is_close_short = order['side'] == 'buy' and order['posSide'] == 'short'
                                logger.info(f"[信号源订单类型判断] is_open_long={is_open_long}, is_open_short={is_open_short}, is_close_long={is_close_long}, is_close_short={is_close_short}")

                                    # 处理开仓信号
                                if is_open_long or is_open_short:
                                    # 生成唯一的开仓标识，用于内存级别去重
                                    open_key = f"{ordId}_{signal_account.source_uid}_{symbol}_{order['posSide']}_{is_demo}"

                                    # 检查是否已经在处理中
                                    if hasattr(self, '_processing_open_signals') and open_key in self._processing_open_signals:
                                        logger.info(f"[信号源开仓] 开仓操作已在处理中，跳过重复请求: {open_key}")
                                        continue

                                    # 添加到处理中集合
                                    if not hasattr(self, '_processing_open_signals'):
                                        self._processing_open_signals = set()
                                    self._processing_open_signals.add(open_key)

                                    try:
                                        # 检查是否已经处理过这个开仓订单
                                        from database.db import check_signal_trade_exists
                                        if check_signal_trade_exists(self.db_pool, ordId, signal_account.source_uid, symbol, order['posSide'], is_demo):
                                            logger.info(f"[信号源订单去重] 开仓订单{ordId}已处理过，跳过")
                                            continue

                                        # 检查是否是手动开仓
                                        manual_operation = self.db_pool.query(
                                            "SELECT 1 FROM manual_operations WHERE order_id=%s AND operation_type='open' AND execution_status='success'",
                                            (ordId,)
                                        )
                                        
                                        # 确定交易类型
                                        trade_type = 'manual' if manual_operation else 'open'
                                        
                                        # 开仓插入，volume 用USDT名义价值，volume_contract用张数
                                        insert_signal_account_trade(
                                            self.db_pool, signal_account.source_uid, symbol, order['side'], order['posSide'], volume_usdt, ordId, trade_type, trade_uid=ordId, open_px=avgPx, is_demo=is_demo, volume_contract=fill_sz
                                        )
                                        
                                        # 如果是手动开仓，更新手动操作记录
                                        if manual_operation:
                                            self.db_pool.execute(
                                                "UPDATE manual_operations SET related_trade_uid=%s and status='filled' WHERE order_id=%s AND operation_type='open'",
                                                (ordId, ordId)
                                            )
                                            logger.info(f"[信号源开仓] 手动开仓记录已处理: order_id={ordId}, trade_type={trade_type}")
                                        
                                        # 发送开仓信号到队列
                                        await self.on_signal_trade(signal_account, order)
                                        
                                    finally:
                                        # 从处理中集合移除
                                        if hasattr(self, '_processing_open_signals'):
                                            self._processing_open_signals.discard(open_key)

                                    # 处理减仓信号
                                elif is_close_long or is_close_short:
                                    # 平仓更新 - 查找对应的开仓记录进行更新
                                    logger.info(f"[信号源减仓] 开始查找信号源开仓记录: signal_source_uid={signal_account.source_uid}, symbol={symbol}, pos_side={order['posSide']}, is_demo={is_demo}")
                                    
                                    # 查找对应的开仓记录
                                    # 跳过已经被手动平仓处理的订单（有close_order_id的记录）
                                    logger.info(f"[信号源减仓] 查询条件: signal_source_uid={signal_account.source_uid}, symbol={symbol}, pos_side={order['posSide']}, is_demo={is_demo}")
                                    
                                    # 先查询所有相关记录，看看有什么
                                    all_trades = self.db_pool.query(
                                        "SELECT trade_uid, volume_contract, close_volume_contract, status, close_order_id, trade_type FROM signal_account_trades WHERE signal_source_uid=%s AND symbol=%s AND pos_side=%s AND is_demo=%s",
                                        (signal_account.source_uid, symbol, order['posSide'], is_demo)
                                    )
                                    # logger.info(f"[信号源减仓] 所有相关记录: {len(all_trades)}条")
                                    
                                    # 查找开仓记录，包括正常开仓和补偿开仓
                                    open_trades = self.db_pool.query(
                                        "SELECT trade_uid, volume_contract, close_volume_contract FROM signal_account_trades WHERE signal_source_uid=%s AND symbol=%s AND pos_side=%s AND is_demo=%s AND status='open' AND trade_type='open' ORDER BY created_at ASC",
                                        (signal_account.source_uid, symbol, order['posSide'], is_demo)
                                    )
                                    
                                    logger.info(f"[信号源减仓] 找到{len(open_trades)}个开仓记录:")
                                    for i, trade in enumerate(open_trades):
                                        logger.info(f"[信号源减仓] 开仓记录{i+1}: trade_uid={trade['trade_uid']}, volume_contract={trade['volume_contract']}, close_volume_contract={trade['close_volume_contract']}")
                                    
                                    if open_trades:
                                        # FIFO原则分配减仓量到多个开仓记录
                                        # 计算当前总持仓量（用于计算减仓比例）
                                        current_total_position = sum(float(trade['volume_contract'] or 0) for trade in open_trades)
                                        remaining_reduce = fill_sz
                                        logger.info(f"[信号源减仓] 开始FIFO分配减仓量: 总减仓量={fill_sz}, 开仓记录数={len(open_trades)}")
                                        
                                        for i, open_trade in enumerate(open_trades):
                                            if remaining_reduce <= 0:
                                                break
                                                
                                            trade_uid = open_trade['trade_uid']
                                            logger.info(f"[信号源减仓] 处理第{i+1}个开仓记录: trade_uid={trade_uid}, 剩余减仓量={remaining_reduce}")
                                            
                                            # 先查询原始持仓量，判断本次分配多少减仓量
                                            original_trade = self.db_pool.query(
                                                "SELECT volume_contract, close_volume_contract FROM signal_account_trades WHERE trade_uid=%s AND is_demo=%s",
                                                (trade_uid, is_demo)
                                            )[0]
                                            
                                            original_volume = float(original_trade['volume_contract'] or 0)
                                            current_closed = float(original_trade['close_volume_contract'] or 0)
                                            available_volume = original_volume - current_closed  # 剩余可减仓量
                                            
                                            # 计算本次分配给这个仓位的减仓量
                                            this_reduce = min(remaining_reduce, available_volume)
                                            total_closed = current_closed + this_reduce
                                            
                                            logger.info(f"[信号源减仓] 仓位{i+1}: 原始持仓={original_volume}, 已减仓={current_closed}, 剩余可减仓={available_volume}, 本次分配={this_reduce}")
                                            
                                            # 判断是否完全平仓
                                            is_fully_closed = total_closed >= original_volume
                                            if is_fully_closed:
                                                # 完全平仓
                                                status = 'closed'
                                                closed_at = 'NOW()'
                                                logger.info(f"[信号源减仓] 仓位{i+1}完全平仓: trade_uid={trade_uid}, 原始持仓={original_volume}, 累计减仓={total_closed}")
                                            else:
                                                # 部分减仓
                                                status = 'open'
                                                closed_at = None
                                                logger.info(f"[信号源减仓] 仓位{i+1}部分减仓: trade_uid={trade_uid}, 原始持仓={original_volume}, 累计减仓={total_closed}, 剩余={original_volume-total_closed}")
                                            
                                            # 更新减仓量
                                            if closed_at == 'NOW()':
                                                # 完全平仓，使用NOW()
                                                self.db_pool.execute(
                                                    "UPDATE signal_account_trades SET close_order_id=%s, close_px=%s, profit=%s, close_volume_contract=%s, status=%s, closed_at=NOW() WHERE trade_uid=%s AND is_demo=%s",
                                                    (ordId, avgPx, 0, total_closed, status, trade_uid, is_demo)
                                                )
                                            else:
                                                # 部分减仓，closed_at为NULL
                                                self.db_pool.execute(
                                                    "UPDATE signal_account_trades SET close_order_id=%s, close_px=%s, profit=%s, close_volume_contract=%s, status=%s, closed_at=NULL WHERE trade_uid=%s AND is_demo=%s",
                                                    (ordId, avgPx, 0, total_closed, status, trade_uid, is_demo)
                                                )
                                            logger.info(f"[信号源减仓] 仓位{i+1}更新完成: trade_uid={trade_uid}, 本次分配减仓量={this_reduce}")
                                            
                                            # 记录这个减仓订单的信息，稍后统一发送
                                            if not hasattr(self, '_current_reduce_orders'):
                                                self._current_reduce_orders = []
                                            self._current_reduce_orders.append({
                                                'signal_source_uid': signal_account.source_uid,
                                                'target_uid': target_uid,
                                                'symbol': symbol,
                                                'pos_side': order['posSide'],
                                                'close_side': order['side'],
                                                'reduce_volume': this_reduce,
                                                'signal_trade_uid': trade_uid,
                                                'signal_original_volume': original_volume,
                                                'signal_reduce_ratio': this_reduce / current_total_position if current_total_position > 0 else 0,
                                                'is_fully_closed': is_fully_closed
                                            })
                                            
                                            # 更新剩余减仓量
                                            remaining_reduce -= this_reduce
                                            
                                            if remaining_reduce <= 0:
                                                logger.info(f"[信号源减仓] 减仓分配完成，剩余减仓量=0")
                                                break
                                        
                                        # 发送所有减仓信号
                                        if hasattr(self, '_current_reduce_orders') and self._current_reduce_orders:
                                            logger.info(f"[信号源减仓] 发送{len(self._current_reduce_orders)}个减仓信号")
                                            for reduce_order in self._current_reduce_orders:
                                                await self.on_close_signal(
                                                    reduce_order['signal_source_uid'],
                                                    reduce_order['target_uid'],
                                                    reduce_order['symbol'],
                                                    reduce_order['pos_side'],
                                                    reduce_order['close_side'],
                                                    reduce_order['reduce_volume'],
                                                    reduce_order['signal_trade_uid'],
                                                    reduce_order['signal_original_volume'],
                                                    reduce_order['signal_reduce_ratio'],
                                                    reduce_order['is_fully_closed']
                                                )
                                            # 清空减仓订单列表
                                    # ==================== 处理限价跟单减仓 ====================
                                        logger.info(f"[限价跟单] 信号源减仓，处理限价跟单: {signal_account.source_uid} {symbol} {order['posSide']}")
                                        if hasattr(self, '_current_reduce_orders') and self._current_reduce_orders: # 如果有减仓信息就按照减仓信息处理
                                            for reduce_order in self._current_reduce_orders:
                                                await self._handle_limit_follow_close(
                                                    reduce_order['signal_source_uid'],
                                                    reduce_order['symbol'],
                                                    reduce_order['pos_side'],
                                                    reduce_order['signal_trade_uid'],
                                                    reduce_order['signal_reduce_ratio']
                                                )
                                            
                                        else: # 如果没有减仓信息就按照原本的逻辑处理
                                            await self._handle_limit_follow_close(signal_account.source_uid, symbol, order['posSide'], trade_uid)
                                        self._current_reduce_orders = [] # 清空减仓订单列表
                                    else:
                                        logger.warning(f"[信号源减仓] 未找到对应的开仓记录: signal_source_uid={signal_account.source_uid}, symbol={symbol}, pos_side={order['posSide']}")
                                        
                                        # ==================== 处理限价跟单减仓 ====================
                                        logger.info(f"[限价跟单] 信号源减仓，处理限价跟单: {signal_account.source_uid} {symbol} {order['posSide']}")
                                        trade_uid = None
                                        await self._handle_limit_follow_close(signal_account.source_uid, symbol, order['posSide'], trade_uid)
                                    # 注意：这里不需要再次调用on_signal_trade，因为开仓和减仓时已经调用了

                    except Exception as e:
                        logger.error(f"on_order回调异常: {e}\n{traceback.format_exc()}")

                # 先连接WebSocket
                if not client.is_connection_healthy():
                    logger.info(f"[信号源监听] 信号源 {signal_account.source_uid} 开始连接WebSocket...")
                    await client.connect()
                    
                # 设置回调函数
                account_subscribed = await client.subscribe("account", on_account)
                # 订阅订单频道，指定合约类型为SWAP
                orders_subscribed = await client.subscribe("orders", on_order, instType="SWAP")
                
                if not account_subscribed or not orders_subscribed:
                    logger.error(f"[信号源监听] 信号源 {signal_account.source_uid} 订阅失败，等待重连...")
                    continue
                    
                logger.info(f"[信号源监听] 信号源 {signal_account.source_uid} 监听任务已启动，开始持续运行...")
                
                # 持续运行，直到任务被取消或连接断开
                try:
                    consecutive_failures = 0  # 连续失败计数
                    max_consecutive_failures = 3  # 最大连续失败次数
                    
                    while True:
                        await asyncio.sleep(5)  # 每5秒检查一次状态
                        
                        # 检查客户端是否还存在
                        if not client or not hasattr(client, 'is_connection_healthy'):
                            logger.warning(f"[信号源监听] 信号源 {signal_account.source_uid} 客户端已失效")
                            consecutive_failures += 1
                            if consecutive_failures >= max_consecutive_failures:
                                logger.error(f"[信号源监听] 信号源 {signal_account.source_uid} 连续{consecutive_failures}次检查失败，退出监听")
                                break
                            continue  # 继续尝试，不立即退出
                    
                        # 检查连接状态 - 更宽容的健康检查
                        if not client.is_connection_healthy():
                            consecutive_failures += 1
                            
                            # 对于新连接，给予更多时间
                            current_status = getattr(client, 'state_machine', None)
                            if current_status:
                                status_value = getattr(current_status, 'current_status', None)
                                if status_value:
                                    status_name = getattr(status_value, 'value', 'unknown')
                                    if status_name in ['初始化', '连接中', '已连接']:
                                        logger.debug(f"[信号源监听] 信号源 {signal_account.source_uid} 连接正在建立中，状态: {status_name}")
                                        consecutive_failures = 0  # 重置失败计数
                                        continue  # 继续等待，不退出
                            
                            # 检查连接建立时间
                            connection_age = 0
                            if hasattr(client, 'metrics') and hasattr(client.metrics, 'connect_time'):
                                connection_age = time.time() - client.metrics.connect_time
                            
                            # 新连接（前60秒）给予更多时间
                            if connection_age < 60:
                                logger.debug(f"[信号源监听] 信号源 {signal_account.source_uid} 连接建立中，跳过健康检查，连接时间: {connection_age:.1f}秒")
                                consecutive_failures = 0  # 重置失败计数
                                continue  # 继续等待，不退出
                            
                            # 检查是否达到最大连续失败次数
                            if consecutive_failures >= max_consecutive_failures:
                                logger.error(f"[信号源监听] 信号源 {signal_account.source_uid} 连续{consecutive_failures}次健康检查失败，尝试重连...")
                                try:
                                    await client.connect()
                                    consecutive_failures = 0  # 重连成功后重置计数
                                    logger.info(f"[信号源监听] 信号源 {signal_account.source_uid} 重连成功")
                                    
                                    # 重连成功后检查仓位同步，防止信号丢失
                                    try:
                                        logger.info(f"[信号源监听] 重连成功后开始检查仓位同步: {signal_account.source_uid}")
                                        await self.trade_service._check_signal_source_position_sync(signal_account)
                                        logger.info(f"[信号源监听] 仓位同步检查完成: {signal_account.source_uid}")
                                    except Exception as sync_error:
                                        logger.error(f"[信号源监听] 仓位同步检查失败: {signal_account.source_uid}, error: {sync_error}")
                                    
                                    continue
                                except Exception as reconnect_error:
                                    logger.error(f"[信号源监听] 信号源 {signal_account.source_uid} 重连失败: {reconnect_error}")
                                    if consecutive_failures >= max_consecutive_failures * 2:
                                        logger.error(f"[信号源监听] 信号源 {signal_account.source_uid} 重连失败次数过多，退出监听")
                                        break
                                    continue
                            
                            logger.warning(f"[信号源监听] 信号源 {signal_account.source_uid} 连接健康检查失败 ({consecutive_failures}/{max_consecutive_failures})")
                            continue  # 不退出，继续尝试
                        
                        # 连接健康，重置失败计数
                        consecutive_failures = 0
                        
                        # 检查WebSocket对象 - 更宽容的检查
                        if not client.ws:
                            logger.warning(f"[信号源监听] 信号源 {signal_account.source_uid} WebSocket对象缺失，尝试重连...")
                            try:
                                await client.connect()
                                logger.info(f"[信号源监听] 信号源 {signal_account.source_uid} WebSocket重连成功")
                                
                                # WebSocket重连成功后检查仓位同步，防止信号丢失
                                try:
                                    logger.info(f"[信号源监听] WebSocket重连成功后开始检查仓位同步: {signal_account.source_uid}")
                                    await self.trade_service._check_signal_source_position_sync(signal_account)
                                    logger.info(f"[信号源监听] WebSocket重连后仓位同步检查完成: {signal_account.source_uid}")
                                except Exception as sync_error:
                                    logger.error(f"[信号源监听] WebSocket重连后仓位同步检查失败: {signal_account.source_uid}, error: {sync_error}")
                                
                                continue
                            except Exception as reconnect_error:
                                logger.error(f"[信号源监听] 信号源 {signal_account.source_uid} WebSocket重连失败: {reconnect_error}")
                                consecutive_failures += 1
                                if consecutive_failures >= max_consecutive_failures:
                                    logger.error(f"[信号源监听] 信号源 {signal_account.source_uid} WebSocket重连失败次数过多，退出监听")
                                    break
                                continue
                        
                        # 检查监听任务状态 - 如果任务结束，尝试重启
                        if hasattr(client, '_listen_task') and client._listen_task and client._listen_task.done():
                            logger.warning(f"[信号源监听] 信号源 {signal_account.source_uid} 监听任务已结束，尝试重启...")
                            try:
                                # 检查任务是否因为异常而结束
                                if client._listen_task.exception():
                                    logger.error(f"[信号源监听] 信号源 {signal_account.source_uid} 监听任务异常: {client._listen_task.exception()}")
                                    consecutive_failures += 1
                                    if consecutive_failures >= max_consecutive_failures:
                                        logger.error(f"[信号源监听] 信号源 {signal_account.source_uid} 监听任务异常次数过多，退出监听")
                                        break
                                    continue
                                
                                # 重启监听任务
                                client._listen_task = asyncio.create_task(client._listen())
                                logger.info(f"[信号源监听] 信号源 {signal_account.source_uid} 监听任务重启成功")
                                consecutive_failures = 0  # 重置失败计数
                                
                                # 监听任务重启成功后检查仓位同步，防止信号丢失
                                try:
                                    logger.info(f"[信号源监听] 监听任务重启成功后开始检查仓位同步: {signal_account.source_uid}")
                                    await self.trade_service._check_signal_source_position_sync(signal_account)
                                    logger.info(f"[信号源监听] 监听任务重启后仓位同步检查完成: {signal_account.source_uid}")
                                except Exception as sync_error:
                                    logger.error(f"[信号源监听] 监听任务重启后仓位同步检查失败: {signal_account.source_uid}, error: {sync_error}")
                                
                                continue
                            except Exception as restart_error:
                                logger.error(f"[信号源监听] 信号源 {signal_account.source_uid} 监听任务重启失败: {restart_error}")
                                consecutive_failures += 1
                                if consecutive_failures >= max_consecutive_failures:
                                    logger.error(f"[信号源监听] 信号源 {signal_account.source_uid} 监听任务重启失败次数过多，退出监听")
                                    break
                                continue
                            
                except asyncio.CancelledError:
                    logger.info(f"[信号源监听] 信号源 {signal_account.source_uid} 监听任务被取消")
                    break
                except Exception as e:
                    logger.error(f"[信号源监听] 信号源 {signal_account.source_uid} 监听任务异常: {e}")
                    logger.error(f"[信号源监听] 异常详情: {traceback.format_exc()}")
                    consecutive_failures += 1
                    if consecutive_failures >= max_consecutive_failures:
                        logger.error(f"[信号源监听] 信号源 {signal_account.source_uid} 异常次数过多，退出监听")
                        break
                    continue  # 继续尝试，不立即退出
                
                # 如果到达这里，说明监听正常结束
                logger.info(f"[信号源监听] 信号源 {signal_account.source_uid} 监听正常结束")
                break
                
            except Exception as e:
                reconnect_count += 1
                logger.error(f"[信号源监听] 信号源 {signal_account.source_uid} 监听异常 (第{reconnect_count}次): {e}")
                logger.error(f"[信号源监听] 异常详情: {traceback.format_exc()}")
                
                if reconnect_count < max_reconnect_attempts:
                    logger.info(f"[信号源监听] 等待重连... (第{reconnect_count}次尝试)")
                    await asyncio.sleep(min(5 * reconnect_count, 30))  # 指数退避，最大30秒
                    
                    # 尝试重新创建客户端
                    try:
                        logger.info(f"[信号源监听] 尝试重新创建信号源 {signal_account.source_uid} 的客户端...")
                        client = await self._create_signal_client(signal_account)
                        if client:
                            logger.info(f"[信号源监听] 信号源 {signal_account.source_uid} 客户端重新创建成功，继续监听")
                            
                            # 客户端重新创建成功后检查仓位同步，防止信号丢失
                            try:
                                logger.info(f"[信号源监听] 客户端重新创建成功后开始检查仓位同步: {signal_account.source_uid}")
                                await self.trade_service._check_signal_source_position_sync(signal_account)
                                logger.info(f"[信号源监听] 客户端重新创建后仓位同步检查完成: {signal_account.source_uid}")
                            except Exception as sync_error:
                                logger.error(f"[信号源监听] 客户端重新创建后仓位同步检查失败: {signal_account.source_uid}, error: {sync_error}")
                            
                            continue  # 继续监听循环
                        else:
                            logger.error(f"[信号源监听] 信号源 {signal_account.source_uid} 客户端重新创建失败")
                    except Exception as recreate_error:
                        logger.error(f"[信号源监听] 重新创建客户端异常: {recreate_error}")
                else:
                    logger.error(f"[信号源监听] 信号源 {signal_account.source_uid} 重连次数已达上限，停止重连")
                    break
                    
        # 清理资源
        if client:
            try:
                await client.close()
                logger.info(f"[信号源监听] 信号源 {signal_account.source_uid} 客户端已关闭")
            except Exception as e:
                logger.error(f"[信号源监听] 关闭客户端时异常: {e}")

    async def on_signal_trade(self, signal_account, order):
        # 检查队列大小，防止内存溢出
        queue_size = self.signal_queue.qsize()
        if queue_size >= 900:  # 接近队列上限时警告
            logger.warning(f"⚠️ 信号队列接近上限: {queue_size}/1000，可能影响系统性能")
        
        if queue_size >= 1000:  # 队列已满时拒绝新消息
            logger.error(f"🚨 信号队列已满({queue_size}/1000)，拒绝新消息，可能导致信号丢失")
            return
        
        # 入队，交由全局队列串行消费
        try:
            await self.signal_queue.put((signal_account, order))
            await self.start_signal_consumer()
        except asyncio.QueueFull:
            logger.error(f"🚨 信号队列已满，无法添加新消息: {order.get('ordId', 'unknown')}")
        except Exception as e:
            logger.error(f"添加信号到队列失败: {e}")
            logger.error(f"异常详情: {traceback.format_exc()}")

    async def _on_signal_trade_inner(self, signal_account, order):
        try:
            target_uid = order.get('ordId')
            symbol = order.get('instId')
            pos_side = order.get('posSide')

            logger.info(f"[信号队列] 处理信号: target_uid={target_uid}, symbol={symbol}, pos_side={pos_side}, inst_id={order['instId']}, state={order['state']}, side={order['side']}, posSide={order['posSide']}, fee={order['fee']},fill_sz={order.get('accFillSz')}, fill_px={order.get('fillPx')}")
            
            # 币种屏蔽检查
            if self.is_symbol_blocked(signal_account.source_uid, symbol):
                logger.warning(f"[币种屏蔽] 信号源{signal_account.source_uid}的{symbol}合约被屏蔽，跳过处理")
                return
            
            is_open_long = order['side'] == 'buy' and order['posSide'] == 'long'
            is_open_short = order['side'] == 'sell' and order['posSide'] == 'short'
            if is_open_long or is_open_short and order['state'] == 'filled':
                # 生成唯一的跟单标识，用于防重复
                # 使用ordId确保每个订单都有唯一标识
                is_demo = get_global_is_demo()
                follow_key = f"{target_uid}_{signal_account.source_uid}_{symbol}_{pos_side}_{is_demo}"
                
                # 检查是否已经在处理中
                if hasattr(self, '_processing_follow_signals') and follow_key in self._processing_follow_signals:
                    logger.info(f"[信号源开仓] 开仓操作已在处理中，跳过重复请求: {follow_key}")
                    return
                
                # 添加到处理中集合
                if not hasattr(self, '_processing_follow_signals'):
                    self._processing_follow_signals = set()
                self._processing_follow_signals.add(follow_key)
                
                try:
                    logger.info(f"on_order_trade: {order}")
                    strategies = get_strategies_by_signal_account(self.db_pool, signal_account.source_uid)
                    logger.info(f"on_signal_trade: 查到 strategies: {strategies}")
                    for strategy in strategies:
                        strategy_uid = strategy['strategy_uid'] if isinstance(strategy, dict) else getattr(strategy, 'strategy_uid', '未知')
                        logger.info(f"[客户跟单] 处理策略: strategy_uid={strategy_uid}")
                        
                        customers = self.db_pool.query(
                            "SELECT c.* FROM customers c JOIN customer_strategy cs ON c.customer_uid = cs.customer_uid WHERE cs.strategy_uid = %s AND c.enabled=1 AND c.is_demo=%s",
                            (strategy_uid, get_global_is_demo())
                        )
                        logger.info(f"[客户跟单] 策略{strategy_uid}查询到的客户数量: {len(customers)}")
                        for i, customer in enumerate(customers):
                            logger.info(f"[客户跟单] 客户{i+1}: customer_uid={customer.get('customer_uid')}, enabled={customer.get('enabled')}, is_demo={customer.get('is_demo')}")
                        
                        customer_objs = [self.trade_service.safe_customer(c) for c in customers]
                        logger.info(f"on_signal_trade: strategy_uid={strategy_uid} 查到客户数: {len(customer_objs)}")
                        
                        if not customer_objs:
                            logger.warning(f"[客户跟单] 策略{strategy_uid}没有找到启用的客户，跳过")
                            continue
                        
                        rule = get_rule_by_signal_source(self.db_pool, signal_account.source_uid, strategy_uid)
                        if not rule:
                            logger.warning(f"on_signal_trade: source_uid={signal_account.source_uid} 未查到规则，跳过")
                            continue
                        rule_uid = rule['rule_uid'] if isinstance(rule, dict) else getattr(rule, 'rule_uid', '未知')
                        logger.info(f"on_signal_trade: source_uid={signal_account.source_uid} 对应 rule_uid={rule_uid}")
                        
                        # 使用信号源实际成交量，而不是订单下单量
                        sz = safe_float(order.get('accFillSz')) if order.get('accFillSz') is not None else safe_float(order.get('fillSz', order.get('sz')))
                        position_share = safe_float(order.get('position_share', 1))
                        logger.info(f"on_signal_trade: 分发客户跟单 symbol={order['instId']}, pos_side={order['posSide']}, sz={sz}, position_share={position_share}, rule_uid={rule_uid}, 客户数={len(customer_objs)}")
                        
                        # 组装集合下单参数
                        signal_orders = [{
                            'signal_source_uid': signal_account.source_uid,
                            'rule_uid': rule_uid,
                            'strategy_uid': strategy_uid,
                            'sz': sz,
                            'max_leverage': safe_float(rule.get('max_leverage', 10) if isinstance(rule, dict) else getattr(rule, 'max_leverage', 10)),
                            'position_share': position_share,
                            'position_ratio': safe_float(rule.get('position_ratio', 1) if isinstance(rule, dict) else getattr(rule, 'position_ratio', 1)),
                            'signal_ordId': target_uid  # 传递信号源订单的ordId
                        }]
                        
                        logger.info(f"[客户跟单] 信号订单参数: {signal_orders}")
                        
                        # ==================== 1. 普通跟单（市价单） ====================
                        # 使用信号源级别的锁防止同一信号源并发处理
                        from trade_service import get_signal_processing_lock
                        signal_lock = get_signal_processing_lock(signal_account.source_uid, order['instId'], order['posSide'])
                        
                        # 创建客户跟单任务列表
                        customer_tasks = []
                        for customer in customer_objs:
                            customer_uid = getattr(customer, 'customer_uid', 'unknown')
                            logger.info(f"[客户跟单] 为客户{customer_uid}创建跟单任务")
                            customer_tasks.append(
                                self.trade_service.aggregate_and_place_orders(
                                    customer,
                                    order['instId'],
                                    order['side'],
                                    order['posSide'],
                                    signal_orders
                                )
                            )
                        # 使用信号源锁控制并发，然后串行执行客户跟单
                        with signal_lock:
                            logger.info(f"[信号源跟单] 开始串行处理{len(customer_tasks)}个客户的跟单任务")
                            results = []
                            for task in customer_tasks:
                                try:
                                    result = await task
                                    results.append(result)
                                except Exception as e:
                                    logger.error(f"[信号源跟单] 客户跟单任务异常: {e}")
                                    results.append(e)
                            logger.info(f"[信号源跟单] 完成所有客户跟单任务，结果: {results}")
                            
                        # ==================== 2. 限价跟单 ====================
                        # 2. 处理限价跟单（新增逻辑）
                finally:
                    # 清理处理中标识
                    self._processing_follow_signals.discard(follow_key)
            # 平仓信号不在这里处理
            await self._handle_limit_follow(signal_account, order)
        except Exception as e:
            logger.error(f"on_signal_trade回调异常: {e}\n{traceback.format_exc()}")

    def get_strategies_by_signal_source(self, signal_source_uid: str):
        rows = self.db_pool.query("SELECT s.* FROM strategies s JOIN signal_source_strategy ss ON s.strategy_uid=ss.strategy_uid WHERE ss.signal_source_uid=%s AND s.enabled=1", (signal_source_uid,))
        return [Strategy(**row) for row in rows]

    def get_rules_by_strategy(self, strategy_uid: str):
        rows = self.db_pool.query("SELECT * FROM rules WHERE strategy_uid=%s AND enabled=1", (strategy_uid,))
        return [Rule(**row) for row in rows]

    def is_symbol_blocked(self, signal_source_uid: str, symbol: str) -> bool:
        """
        检查指定信号源的指定币种是否被屏蔽
        """
        # 检查信号源是否被禁用
        if is_signal_source_blocked(signal_source_uid):
            logger.info(f"[币种屏蔽] 信号源{signal_source_uid}已被禁用")
            return True
        
        # 获取屏蔽币种列表
        blocked_symbols = get_blocked_symbols(signal_source_uid)
        
        # 检查币种是否被屏蔽（支持部分匹配，不区分大小写）
        for blocked_symbol in blocked_symbols:
            if blocked_symbol.lower() in symbol.lower():
                logger.info(f"[币种屏蔽] 信号源{signal_source_uid}的{symbol}匹配屏蔽规则{blocked_symbol}")
                return True
        
        return False

    async def on_signal(self, signal_source_uid, symbol, direction, pos_side, volume, signal_type):
        strategies = self.get_strategies_by_signal_source(signal_source_uid)
        for strategy in strategies:
            rules = self.get_rules_by_strategy(strategy.strategy_uid)
            for rule in rules:
                customers = self.trade_service.get_customers_by_rule(rule.rule_uid)
                # 组装集合下单参数
                signal_orders = [{
                    'signal_source_uid': signal_source_uid,
                    'rule_uid': rule.rule_uid,
                    'strategy_uid': strategy.strategy_uid,
                    'sz': volume,
                    'max_leverage': safe_float(getattr(rule, 'max_leverage', 10)),
                    'position_share': 1
                }]
                for customer in customers:
                    await self.trade_service.aggregate_and_place_orders(
                        customer,
                        symbol,
                        direction,
                        pos_side,
                        signal_orders
                    )

    async def on_close_signal(self, signal_source_uid, target_uid, symbol, pos_side, close_side, signal_volume=None, signal_trade_uid=None, signal_original_volume=None, signal_reduce_ratio=None, is_fully_closed=None):
        try:
            logger.info(f"on_close_signal: target_uid={target_uid}, symbol={symbol}, pos_side={pos_side}, close_side={close_side}")
            
            # 币种屏蔽检查
            if self.is_symbol_blocked(signal_source_uid, symbol):
                logger.warning(f"[币种屏蔽] 信号源{signal_source_uid}的{symbol}合约被屏蔽，跳过平仓处理")
                return
            
            # 生成唯一的平仓标识，用于防重复
            is_demo = get_global_is_demo()
            close_key = f"{signal_source_uid}_{symbol}_{pos_side}_{is_demo}_{target_uid}"
            
            # 检查是否已经在处理中
            if hasattr(self, '_processing_close_signals') and close_key in self._processing_close_signals:
                logger.info(f"[平仓信号] 平仓信号已在处理中，跳过重复请求: {close_key}")
                return
            
            # 添加到处理中集合
            if not hasattr(self, '_processing_close_signals'):
                self._processing_close_signals = set()
            self._processing_close_signals.add(close_key)
            
            try:
                # 多字段查找所有 open 单
                strategies = get_strategies_by_signal_account(self.db_pool, signal_source_uid)
                trades_to_close = []
                for strategy in strategies:
                    rules = get_rules_by_strategy(self.db_pool, strategy['strategy_uid'])
                    for rule in rules:
                        customers = get_customers_by_strategy_and_rule(self.db_pool, strategy['strategy_uid'], rule['rule_uid'], get_global_is_demo())
                        for customer in customers:
                            is_demo = get_global_is_demo()
                            rows = self.db_pool.query(
                                "SELECT * FROM customer_trades WHERE customer_uid=%s AND strategy_uid=%s AND rule_uid=%s AND symbol=%s AND pos_side=%s AND status='open' AND is_demo=%s",
                                (customer['customer_uid'], strategy['strategy_uid'], rule['rule_uid'], symbol, pos_side, is_demo)
                            )
                            trades_to_close.extend([CustomerTrade(**row) for row in rows])
                if trades_to_close:
                    logger.info(f"on_close_signal: 批量平仓 symbol={symbol}, pos_side={pos_side}, trades_count={len(trades_to_close)}, signal_volume={signal_volume}")
                    await self.trade_service.batch_close_trades(trades_to_close, symbol, pos_side, signal_volume, signal_source_uid=signal_source_uid, signal_trade_uid=signal_trade_uid, signal_original_volume=signal_original_volume, signal_reduce_ratio=signal_reduce_ratio, is_fully_closed=is_fully_closed)
                else:
                    logger.info(f"on_close_signal: 未找到可平仓的客户单 symbol={symbol}, pos_side={pos_side}")
            finally:
                # 清理处理中标识
                self._processing_close_signals.discard(close_key)
        except Exception as e:
            logger.error(f"on_close_signal回调异常: {e}\n{traceback.format_exc()}") 

    async def _create_signal_client(self, signal_account):
        """创建信号源客户端"""
        try:
            # 使用全局客户端管理器
            client_manager = get_global_client_manager()
            
            client = await client_manager.get_client(
                client_key=f"signal_{signal_account.source_uid}",
                is_demo=signal_account.is_demo if hasattr(signal_account, 'is_demo') else False,
                api_key=signal_account.api_key,
                api_secret=signal_account.api_secret,
                passphrase=signal_account.passphrase
            )
            
            # 确保WebSocket连接建立
            logger.info(f"正在建立信号源 {signal_account.source_uid} 的WebSocket连接...")
            await client.connect()
            logger.info(f"信号源 {signal_account.source_uid} 的WebSocket连接建立完成")
            
            # 测试连接的真实性
            logger.info(f"正在测试信号源 {signal_account.source_uid} 的连接真实性...")
            if hasattr(client, 'test_connection_reality'):
                reality_test_result = await client.test_connection_reality()
                if reality_test_result:
                    logger.info(f"✅ 信号源 {signal_account.source_uid} 的连接真实性测试通过")
                else:
                    logger.error(f"❌ 信号源 {signal_account.source_uid} 的连接真实性测试失败")
                    logger.error("连接可能没有真正建立成功")
                    return None
            else:
                logger.warning(f"信号源 {signal_account.source_uid} 的客户端不支持连接真实性测试")
            
            return client
            
        except Exception as e:
            logger.error(f"创建信号源 {signal_account.source_uid} 客户端失败: {e}")
            return None 

    async def _handle_limit_follow(self, signal_account, order):
        """处理限价跟单"""
        try:
            signal_source_uid = signal_account.source_uid
            symbol = order['instId']
            pos_side = order['posSide']
            
            logger.info(f"[限价跟单] 开始处理限价跟单: signal_source_uid={signal_source_uid}, symbol={symbol}, pos_side={pos_side}")
            
            # 1. 检查是否有该信号源的限价跟单策略
            # 查询条件：匹配具体交易对、全部交易对或指定交易对列表中的策略
            strategies = self.db_pool.query(
                """SELECT * FROM limit_follow_strategies 
                WHERE trader_unique_name=%s AND enabled=1 
                AND (
                    symbol='ALL' 
                    OR symbol=%s 
                    OR (symbol='SPECIFIC' AND JSON_CONTAINS(symbols, %s))
                )""",
                (signal_source_uid, symbol, f'"{symbol}"')
            )
            
            logger.info(f"[限价跟单] 查询策略结果: 找到 {len(strategies) if strategies else 0} 个策略")
            
            if not strategies:
                logger.info(f"[限价跟单] 信号源 {signal_source_uid} 没有限价跟单策略，跳过")
                return
            
            logger.info(f"[限价跟单] 信号源 {signal_source_uid} 有 {len(strategies)} 个限价跟单策略")
            
            # 2. 判断是开仓还是平仓
            is_open = self._is_open_position(order['side'], order['posSide'])
            logger.info(f"[限价跟单] 订单类型判断: side={order['side']}, pos_side={order['posSide']}, is_open={is_open}")
            
            if is_open:
                # 开仓 - 触发限价跟单
                logger.info(f"[限价跟单] 处理开仓信号")
                await self._handle_limit_follow_open(signal_source_uid, symbol, pos_side, order)
            else:
                # 平仓 - 处理平仓逻辑
                logger.info(f"[限价跟单] 处理平仓信号")
                await self._handle_limit_follow_close(signal_source_uid, symbol, pos_side, order)
                
        except Exception as e:
            logger.error(f"处理限价跟单失败: {e}")
            import traceback
            logger.error(f"处理限价跟单异常详情: {traceback.format_exc()}")

    def _is_open_position(self, side, pos_side):
        """判断是否为开仓"""
        return (side == 'buy' and pos_side == 'long') or (side == 'sell' and pos_side == 'short')

    async def _handle_limit_follow_open(self, signal_source_uid, symbol, pos_side, order):
        """处理限价跟单开仓"""
        try:
            # 获取信号价格
            signal_price = safe_float(order.get('fillPx', order.get('px', 0)))
            if signal_price <= 0:
                logger.warning(f"[限价跟单] 信号价格无效，跳过: fillPx={order.get('fillPx')}, px={order.get('px')}")
                return
            
            logger.info(f"[限价跟单] 信号源 {signal_source_uid} 开仓，触发限价跟单: {symbol} {pos_side} @ {signal_price}")
            
            # 调用 trade_service 处理限价跟单
            logger.info(f"[限价跟单]: 信号源订单号{order.get('ordId', '')}")
            await self.trade_service.trigger_limit_follow_orders(
                signal_source_uid,
                symbol,
                pos_side,
                signal_price,
                order.get('ordId', '')
            )
            
        except Exception as e:
            logger.error(f"处理限价跟单开仓失败: {e}")

    async def _handle_limit_follow_close(self, signal_source_uid, symbol, pos_side, signal_trade_uid, reduce_ratio=None):
        """处理限价跟单平仓"""
        try:
            logger.info(f"[限价跟单] 信号源 {signal_source_uid} 平仓，处理限价跟单: {symbol} {pos_side}")
            trade_uid = signal_trade_uid
            if signal_trade_uid is not None and type(signal_trade_uid) != str:
                trade_uid = signal_trade_uid.get('ordId', '')
            elif signal_trade_uid is None:
                trade_uid = None
            # 调用 trade_service 处理平仓，传递减仓比例
            await self.trade_service.handle_signal_close(
                signal_source_uid,
                symbol,
                pos_side,
                trade_uid,
                reduce_ratio  # 传递减仓比例
            )
            
        except Exception as e:
            logger.error(f"处理限价跟单平仓失败: {e}")
            import traceback
            logger.error(f"[限价跟单平仓] 异常堆栈: {traceback.format_exc()}")
