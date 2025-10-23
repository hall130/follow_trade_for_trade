"""
策略交易服务
将策略交易模块接入实盘交易框架
"""

import asyncio
from typing import Dict, List, Optional
from datetime import datetime
from dataclasses import dataclass

from utils.logger import get_logger
from database.db import MySQLPool
from exchange.exchange_factory import create_exchange_client
from exchange.unified_ws_client import get_global_client_manager
from core.strategy_trade.core.manager import StrategyManager
from core.strategy_trade.core.strategy import MarketData, Signal
from core.market_trade.trade_service import TradeService

logger = get_logger(__name__)

@dataclass
class StrategyTradeConfig:
    """策略交易配置"""
    strategy_id: str
    symbol: str
    exchange: str = 'okx'
    is_demo: bool = True
    initial_capital: float = 10000.0
    max_position_value: float = 5000.0
    stop_loss_pct: float = 0.03
    take_profit_pct: float = 0.06

class StrategyTradeService:
    """
    策略交易服务
    
    功能：
    1. 订阅市场数据（WebSocket）
    2. 将数据喂给策略实例
    3. 接收策略信号
    4. 转换为交易订单并执行
    """
    
    def __init__(self, db_pool: MySQLPool, trade_service: TradeService, strategy_manager: StrategyManager):
        self.db_pool = db_pool
        self.trade_service = trade_service
        self.strategy_manager = strategy_manager
        
        # 运行中的策略
        self.running_strategies: Dict[str, StrategyTradeConfig] = {}
        
        # WebSocket 客户端管理
        self.ws_clients: Dict[str, any] = {}
        
        # 任务管理
        self.strategy_tasks: Dict[str, asyncio.Task] = {}
        
        logger.info("策略交易服务初始化完成")
    
    async def start_strategy(self, config: StrategyTradeConfig):
        """
        启动策略实盘交易
        
        Args:
            config: 策略交易配置
        """
        strategy_id = config.strategy_id
        
        # 检查策略是否已在运行
        if strategy_id in self.running_strategies:
            logger.warning(f"策略 {strategy_id} 已在运行")
            return False
        
        try:
            # 获取策略实例
            strategy_info = self.strategy_manager.get_strategy(strategy_id)
            if not strategy_info:
                logger.error(f"策略 {strategy_id} 不存在")
                return False
            
            strategy = strategy_info.strategy
            
            # 初始化策略
            strategy.on_init()
            strategy.on_start()
            
            # 保存配置
            self.running_strategies[strategy_id] = config
            
            # 启动市场数据订阅任务
            task = asyncio.create_task(self._run_strategy_loop(strategy_id, strategy, config))
            self.strategy_tasks[strategy_id] = task
            
            logger.info(f"✅ 策略 {strategy_id} 已启动实盘交易")
            return True
            
        except Exception as e:
            logger.error(f"启动策略 {strategy_id} 失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return False
    
    async def stop_strategy(self, strategy_id: str, close_positions: bool = True):
        """
        停止策略实盘交易
        
        Args:
            strategy_id: 策略ID
            close_positions: 是否平仓
        """
        if strategy_id not in self.running_strategies:
            logger.warning(f"策略 {strategy_id} 未在运行")
            return False
        
        try:
            # 取消任务
            if strategy_id in self.strategy_tasks:
                task = self.strategy_tasks[strategy_id]
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
                del self.strategy_tasks[strategy_id]
            
            # 关闭 WebSocket 连接
            if strategy_id in self.ws_clients:
                await self._cleanup_ws_client(strategy_id)
            
            # 平仓（如果需要）
            if close_positions:
                await self._close_all_positions(strategy_id)
            
            # 停止策略
            strategy_info = self.strategy_manager.get_strategy(strategy_id)
            if strategy_info:
                strategy_info.strategy.on_stop()
            
            # 移除配置
            del self.running_strategies[strategy_id]
            
            logger.info(f"✅ 策略 {strategy_id} 已停止")
            return True
            
        except Exception as e:
            logger.error(f"停止策略 {strategy_id} 失败: {e}")
            return False
    
    async def _run_strategy_loop(self, strategy_id: str, strategy, config: StrategyTradeConfig):
        """
        策略运行主循环
        
        工作流程：
        1. 连接 WebSocket 订阅市场数据
        2. 接收实时数据
        3. 喂给策略处理
        4. 接收策略信号
        5. 执行交易
        """
        try:
            # 获取全局客户端管理器
            client_manager = get_global_client_manager()
            
            # 创建 WebSocket 客户端
            client = await client_manager.get_client(
                exchange_type='okx',
                api_key='',  # 公共数据不需要密钥
                api_secret='',
                passphrase='',
                is_demo=config.is_demo
            )
            
            self.ws_clients[strategy_id] = client
            
            # 订阅K线数据
            channel = f"candle{self._get_interval_str(strategy.timeframe)}"
            inst_id = config.symbol
            
            logger.info(f"📡 策略 {strategy_id} 订阅市场数据: {inst_id} {channel}")
            
            # 订阅回调
            async def on_message(data):
                try:
                    await self._handle_market_data(strategy_id, strategy, data)
                except Exception as e:
                    logger.error(f"处理市场数据异常: {e}")
            
            # 开始订阅
            await client.subscribe_public(
                channel=channel,
                inst_id=inst_id,
                callback=on_message
            )
            
            # 保持连接
            logger.info(f"🔄 策略 {strategy_id} 开始接收实时数据...")
            
            while True:
                await asyncio.sleep(1)
                
                # 定期检查策略状态
                if strategy_id not in self.running_strategies:
                    logger.info(f"策略 {strategy_id} 已被停止，退出循环")
                    break
                
        except asyncio.CancelledError:
            logger.info(f"策略 {strategy_id} 任务已取消")
            raise
        except Exception as e:
            logger.error(f"策略 {strategy_id} 运行异常: {e}")
            import traceback
            logger.error(traceback.format_exc())
            # 标记策略为错误状态
            await self._mark_strategy_error(strategy_id, str(e))
    
    async def _handle_market_data(self, strategy_id: str, strategy, data: dict):
        """
        处理市场数据
        
        Args:
            strategy_id: 策略ID
            strategy: 策略实例
            data: 市场数据
        """
        try:
            # 解析 OKX K线数据格式
            # data = {
            #     'arg': {'channel': 'candle1H', 'instId': 'BTC-USDT-SWAP'},
            #     'data': [[timestamp, open, high, low, close, volume, ...]]
            # }
            
            if 'data' not in data or not data['data']:
                return
            
            kline = data['data'][0]
            
            # 创建 MarketData 对象
            market_data = MarketData(
                symbol=data['arg']['instId'],
                timestamp=datetime.fromtimestamp(int(kline[0]) / 1000),
                open=float(kline[1]),
                high=float(kline[2]),
                low=float(kline[3]),
                close=float(kline[4]),
                volume=float(kline[5])
            )
            
            logger.debug(f"📊 策略 {strategy_id} 接收数据: 价格={market_data.close}, 时间={market_data.timestamp}")
            
            # 喂给策略
            strategy.on_data(market_data)
            
            # 获取策略信号
            signals = strategy.get_signals()
            
            if signals:
                logger.info(f"🎯 策略 {strategy_id} 产生 {len(signals)} 个信号")
                # 处理信号
                for signal in signals:
                    await self._execute_signal(strategy_id, signal, market_data)
            
        except Exception as e:
            logger.error(f"处理市场数据失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
    
    async def _execute_signal(self, strategy_id: str, signal: Signal, market_data: MarketData):
        """
        执行策略信号
        
        Args:
            strategy_id: 策略ID
            signal: 交易信号
            market_data: 市场数据
        """
        try:
            config = self.running_strategies[strategy_id]
            
            logger.info(f"""
╔══════════════════════════════════════════════
║ 📈 策略信号
╠══════════════════════════════════════════════
║ 策略ID: {strategy_id}
║ 信号类型: {signal.side}
║ 交易对: {signal.symbol}
║ 价格: {signal.price}
║ 数量: {signal.quantity}
║ 原因: {signal.reason if hasattr(signal, 'reason') else 'N/A'}
╚══════════════════════════════════════════════
            """)
            
            # 风险检查
            if not await self._risk_check(strategy_id, signal, config):
                logger.warning(f"⚠️ 策略 {strategy_id} 信号未通过风险检查")
                return
            
            # 转换为实际订单
            # 这里接入你的 TradeService
            if signal.side == 'BUY':
                # 开多仓
                await self._execute_buy_order(strategy_id, signal, config)
            elif signal.side == 'SELL':
                # 平多仓
                await self._execute_sell_order(strategy_id, signal, config)
            
        except Exception as e:
            logger.error(f"执行信号失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
    
    async def _execute_buy_order(self, strategy_id: str, signal: Signal, config: StrategyTradeConfig):
        """执行买入订单"""
        try:
            # 创建 REST 客户端
            client = create_exchange_client(
                exchange=config.exchange,
                client_type='rest',
                is_demo=config.is_demo
            )
            
            # 构造订单请求
            from exchange.base_client import OrderRequest, OrderSide, OrderType
            
            order_request = OrderRequest(
                symbol=signal.symbol,
                side=OrderSide.BUY,
                order_type=OrderType.MARKET,  # 市价单
                quantity=signal.quantity,
                price=None,  # 市价单不需要价格
                client_order_id=f"strategy_{strategy_id}_{int(datetime.now().timestamp())}"
            )
            
            # 下单
            response = await client.place_order(order_request)
            
            if response.success:
                logger.info(f"✅ 策略 {strategy_id} 买入订单已提交: order_id={response.order_id}")
                
                # 记录到数据库
                await self._record_trade(strategy_id, {
                    'order_id': response.order_id,
                    'symbol': signal.symbol,
                    'side': 'BUY',
                    'price': response.avg_price or signal.price,
                    'quantity': response.filled_quantity,
                    'timestamp': datetime.now(),
                    'status': response.status
                })
            else:
                logger.error(f"❌ 策略 {strategy_id} 买入订单失败: {response.message}")
            
        except Exception as e:
            logger.error(f"执行买入订单异常: {e}")
            import traceback
            logger.error(traceback.format_exc())
    
    async def _execute_sell_order(self, strategy_id: str, signal: Signal, config: StrategyTradeConfig):
        """执行卖出订单"""
        try:
            # 创建 REST 客户端
            client = create_exchange_client(
                exchange=config.exchange,
                client_type='rest',
                is_demo=config.is_demo
            )
            
            # 构造订单请求
            from exchange.base_client import OrderRequest, OrderSide, OrderType
            
            order_request = OrderRequest(
                symbol=signal.symbol,
                side=OrderSide.SELL,
                order_type=OrderType.MARKET,
                quantity=signal.quantity,
                price=None,
                reduce_only=True,  # 只平仓
                client_order_id=f"strategy_{strategy_id}_{int(datetime.now().timestamp())}"
            )
            
            # 下单
            response = await client.place_order(order_request)
            
            if response.success:
                logger.info(f"✅ 策略 {strategy_id} 卖出订单已提交: order_id={response.order_id}")
                
                # 记录到数据库
                await self._record_trade(strategy_id, {
                    'order_id': response.order_id,
                    'symbol': signal.symbol,
                    'side': 'SELL',
                    'price': response.avg_price or signal.price,
                    'quantity': response.filled_quantity,
                    'timestamp': datetime.now(),
                    'status': response.status
                })
            else:
                logger.error(f"❌ 策略 {strategy_id} 卖出订单失败: {response.message}")
            
        except Exception as e:
            logger.error(f"执行卖出订单异常: {e}")
            import traceback
            logger.error(traceback.format_exc())
    
    async def _risk_check(self, strategy_id: str, signal: Signal, config: StrategyTradeConfig) -> bool:
        """
        风险检查
        
        检查项：
        1. 单笔订单价值是否超限
        2. 总持仓价值是否超限
        3. 日交易次数是否超限
        4. 是否在允许交易时间
        """
        try:
            # 1. 检查订单价值
            order_value = signal.price * signal.quantity
            if order_value > config.max_position_value:
                logger.warning(f"订单价值 {order_value} 超过限制 {config.max_position_value}")
                return False
            
            # 2. 检查总持仓（TODO: 实现持仓查询）
            
            # 3. 检查日交易次数（TODO: 实现交易次数统计）
            
            # 4. 其他风险检查
            
            return True
            
        except Exception as e:
            logger.error(f"风险检查异常: {e}")
            return False
    
    async def _record_trade(self, strategy_id: str, trade_data: dict):
        """记录交易到数据库"""
        try:
            # TODO: 实现交易记录入库
            # 可以复用现有的 insert_signal_account_trade 或创建新表
            logger.info(f"📝 记录交易: {trade_data}")
        except Exception as e:
            logger.error(f"记录交易失败: {e}")
    
    async def _close_all_positions(self, strategy_id: str):
        """平掉策略的所有持仓"""
        try:
            config = self.running_strategies[strategy_id]
            
            # TODO: 查询当前持仓并平仓
            logger.info(f"🔄 策略 {strategy_id} 平仓所有持仓")
            
        except Exception as e:
            logger.error(f"平仓失败: {e}")
    
    async def _cleanup_ws_client(self, strategy_id: str):
        """清理 WebSocket 客户端"""
        try:
            if strategy_id in self.ws_clients:
                client = self.ws_clients[strategy_id]
                # TODO: 取消订阅和关闭连接
                del self.ws_clients[strategy_id]
                logger.info(f"✅ 策略 {strategy_id} WebSocket 已清理")
        except Exception as e:
            logger.error(f"清理 WebSocket 失败: {e}")
    
    async def _mark_strategy_error(self, strategy_id: str, error_msg: str):
        """标记策略为错误状态"""
        try:
            strategy_info = self.strategy_manager.get_strategy(strategy_id)
            if strategy_info:
                strategy_info.status = 'ERROR'
                # TODO: 更新数据库状态
                logger.error(f"❌ 策略 {strategy_id} 错误: {error_msg}")
        except Exception as e:
            logger.error(f"标记策略错误失败: {e}")
    
    def _get_interval_str(self, timeframe: str) -> str:
        """将时间周期转换为 OKX K线订阅格式"""
        # 1m -> 1m, 5m -> 5m, 1h -> 1H, 1d -> 1D
        if 'h' in timeframe.lower():
            return timeframe.replace('h', 'H')
        elif 'd' in timeframe.lower():
            return timeframe.replace('d', 'D')
        return timeframe
    
    async def get_strategy_status(self, strategy_id: str) -> dict:
        """获取策略运行状态"""
        if strategy_id not in self.running_strategies:
            return {
                'status': 'STOPPED',
                'message': '策略未运行'
            }
        
        strategy_info = self.strategy_manager.get_strategy(strategy_id)
        config = self.running_strategies[strategy_id]
        
        return {
            'status': strategy_info.status if strategy_info else 'UNKNOWN',
            'strategy_id': strategy_id,
            'symbol': config.symbol,
            'exchange': config.exchange,
            'is_demo': config.is_demo,
            'running_time': datetime.now() - strategy_info.created_time if strategy_info else None,
            'has_ws_connection': strategy_id in self.ws_clients
        }
    
    async def list_running_strategies(self) -> List[dict]:
        """列出所有运行中的策略"""
        strategies = []
        for strategy_id in self.running_strategies.keys():
            status = await self.get_strategy_status(strategy_id)
            strategies.append(status)
        return strategies

