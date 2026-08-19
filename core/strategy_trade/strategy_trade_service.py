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
from core.strategy_trade.base_strategy import MarketData, Signal
from core.market_trade.trade_service import TradeService

logger = get_logger(__name__)

@dataclass
class StrategyTradeConfig:
    """策略交易配置"""
    strategy_id: str
    symbol: str
    exchange: str = 'okx'  # 备用字段，实际从数据库读取
    is_demo: bool = True  # 备用字段，实际从数据库读取
    initial_capital: float = 10000.0
    max_position_value: float = 5000.0
    stop_loss_pct: float = 0.03
    take_profit_pct: float = 0.06
    # 多用户支持：客户ID（必需）
    # 所有账户数据（api_key, api_secret, passphrase, exchange等）都从数据库读取
    customer_id: str = ''  # 客户ID（customer_uid），必需，用于从数据库读取账户信息

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
        
        # WebSocket 客户端管理（仅用于接收市场数据，不用于下单）
        self.ws_clients: Dict[str, any] = {}
        
        # REST 客户端缓存（用于下单，复用客户端实例以减少连接开销）
        self.rest_clients: Dict[str, any] = {}  # key: f"{exchange}_{api_key}_{is_demo}"
        
        # 任务管理
        self.strategy_tasks: Dict[str, asyncio.Task] = {}
        
        logger.info("策略交易服务初始化完成")
    
    async def start_strategy(self, config: StrategyTradeConfig):
        """
        启动策略实盘交易
        
        Args:
            config: 策略交易配置（必须包含customer_id，所有账户数据从数据库读取）
        """
        strategy_id = config.strategy_id
        
        # 验证必需参数
        if not config.customer_id:
            logger.error(f"策略 {strategy_id} 启动失败：缺少customer_id（所有账户数据必须从数据库读取）")
            return False
        
        # 检查策略是否已在运行
        if strategy_id in self.running_strategies:
            logger.warning(f"策略 {strategy_id} 已在运行")
            return False
        
        try:
            # 验证客户账户是否存在（从数据库读取所有账户信息）
            from database.db import get_customer_by_id
            # 尝试从config.is_demo读取，如果失败则尝试另一个is_demo值
            customer_data = get_customer_by_id(self.db_pool, config.customer_id, config.is_demo)
            if not customer_data:
                # 尝试另一个is_demo值
                customer_data = get_customer_by_id(self.db_pool, config.customer_id, not config.is_demo)
                if customer_data:
                    logger.warning(f"策略 {strategy_id} 找到客户但is_demo不匹配，使用数据库中的值")
            
            if not customer_data:
                logger.error(f"策略 {strategy_id} 启动失败：无法找到客户 {config.customer_id}")
                return False
            
            # 更新config中的exchange和is_demo为数据库中的值（所有账户信息都从数据库读取）
            config.exchange = customer_data.get('exchange', 'OKX').lower()
            config.is_demo = customer_data.get('is_demo', config.is_demo)
            
            # 验证账户信息完整性
            if not customer_data.get('api_key') or not customer_data.get('api_secret'):
                logger.error(f"策略 {strategy_id} 启动失败：客户 {config.customer_id} 的API凭证不完整")
                return False
            
            # 获取策略实例
            strategy_info = self.strategy_manager.get_strategy(strategy_id)
            if not strategy_info:
                logger.error(f"策略 {strategy_id} 不存在")
                return False
            
            strategy = strategy_info.strategy

            # 历史数据预热：在初始化之前填充数据，避免冷启动初期指标失真
            logger.info(f"🔥 策略 {strategy_id} 开始历史数据预热...")
            await self._preheat_historical_data(strategy, config)

            # 初始化策略（此时已有历史数据）
            if hasattr(strategy, 'on_initialize'):
                strategy.on_initialize()
            elif hasattr(strategy, 'on_init'):
                strategy.on_init()

            if hasattr(strategy, 'on_start'):
                strategy.on_start()

            # 保存配置
            self.running_strategies[strategy_id] = config

            # 启动市场数据订阅任务
            task = asyncio.create_task(self._run_strategy_loop(strategy_id, strategy, config))
            self.strategy_tasks[strategy_id] = task
            
            logger.info(f"✅ 策略 {strategy_id} 已启动实盘交易（客户: {config.customer_id}, 交易所: {config.exchange})")
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
            
            # 关闭 WebSocket 连接（仅用于市场数据，不用于下单）
            if strategy_id in self.ws_clients:
                await self._cleanup_ws_client(strategy_id)
            
            # 注意：不清理REST客户端，因为可能被其他策略复用
            
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

            # 注意：历史数据预热已在 start_strategy() 中完成，这里直接订阅实时流
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
            bar_ts = int(kline[0])

            # 触发粒度按策略类型区分：
            # - tick_level=True（高频/做市/网格）：逐 tick 报价，每帧都喂，不去重。
            # - tick_level=False（技术指标类，默认）：只在 K 线收盘后喂一次。
            #   OKX candle 频道对"未收盘"的当前 bar 会反复推送（confirm index 8:
            #   "0"=未收盘 "1"=已收盘），若每帧都喂会让同一根 bar 重复计入
            #   price_data 污染指标，也会与历史预热衔接处产生重复根。
            tick_level = getattr(strategy, 'tick_level', False)
            if not tick_level:
                confirm = str(kline[8]) if len(kline) > 8 else '1'
                if confirm != '1':
                    # 未收盘：不喂策略逻辑
                    return
                # 与预热/上一根去重：只处理时间戳更新的已收盘根
                last_ts = getattr(strategy, '_last_bar_ts', None)
                if last_ts is not None and bar_ts <= last_ts:
                    return
                strategy._last_bar_ts = bar_ts

            # 创建 MarketData 对象
            market_data = MarketData(
                symbol=data['arg']['instId'],
                timestamp=datetime.fromtimestamp(bar_ts / 1000),
                open=float(kline[1]),
                high=float(kline[2]),
                low=float(kline[3]),
                close=float(kline[4]),
                volume=float(kline[5])
            )

            logger.debug(f"📊 策略 {strategy_id} 接收数据: 价格={market_data.close}, 时间={market_data.timestamp}")

            # 喂给策略 - 使用新架构统一接口
            if hasattr(strategy, 'process_market_data'):
                strategy.process_market_data(market_data)
            elif hasattr(strategy, 'on_market_data'):
                strategy.on_market_data(market_data)
            else:
                logger.error(f"策略 {strategy_id} 没有实现 process_market_data 或 on_market_data 方法")
            
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
            
            # 获取信号字段（兼容direction/volume和side/quantity）
            signal_direction = getattr(signal, 'direction', getattr(signal, 'side', 'BUY'))
            signal_volume = getattr(signal, 'volume', getattr(signal, 'quantity', 0))
            
            logger.info(f"""
╔══════════════════════════════════════════════
║ 📈 策略信号
╠══════════════════════════════════════════════
║ 策略ID: {strategy_id}
║ 信号类型: {signal_direction}
║ 交易对: {signal.symbol}
║ 价格: {signal.price}
║ 数量: {signal_volume}
║ 原因: {getattr(signal, 'reason', 'N/A')}
╚══════════════════════════════════════════════
            """)
            
            # 风险检查
            if not await self._risk_check(strategy_id, signal, config):
                logger.warning(f"⚠️ 策略 {strategy_id} 信号未通过风险检查")
                return
            
            # 转换为实际订单
            # 这里接入你的 TradeService
            if signal_direction == 'BUY':
                # 开多仓
                await self._execute_buy_order(strategy_id, signal, config)
            elif signal_direction == 'SELL':
                # 平多仓或平空仓
                await self._execute_sell_order(strategy_id, signal, config)
            
        except Exception as e:
            logger.error(f"执行信号失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
    
    async def _execute_buy_order(self, strategy_id: str, signal: Signal, config: StrategyTradeConfig):
        """
        执行买入订单 - 通过REST API（不通过WebSocket，减少WebSocket压力）
        
        架构说明：
        - WebSocket：仅用于接收实时市场数据（K线、深度等）
        - REST API：用于执行交易订单（买入、卖出）
        - 多用户支持：从数据库读取客户账户信息（所有账户数据都在数据库中）
        """
        try:
            # 1. 从数据库读取客户账户信息（所有账户数据都在数据库中）
            if not config.customer_id:
                logger.error(f"策略 {strategy_id} 缺少customer_id，无法从数据库读取账户信息")
                return
            
            try:
                from database.db import get_customer_by_id
                customer_data = get_customer_by_id(self.db_pool, config.customer_id, config.is_demo)
                if not customer_data:
                    logger.error(f"策略 {strategy_id} 无法找到客户: {config.customer_id} (is_demo={config.is_demo})")
                    return
                
                # 从数据库读取所有账户信息
                api_key = customer_data.get('api_key', '')
                api_secret = customer_data.get('api_secret', '')
                passphrase = customer_data.get('passphrase', '')
                exchange = customer_data.get('exchange', 'OKX').lower()  # 从数据库读取交易所
                is_demo = customer_data.get('is_demo', config.is_demo)
                
                if not api_key or not api_secret:
                    logger.error(f"策略 {strategy_id} 客户 {config.customer_id} 的API凭证不完整")
                    return
                
                logger.info(f"✅ 策略 {strategy_id} 使用客户账户: {config.customer_id} (交易所: {exchange})")
                
            except Exception as e:
                logger.error(f"策略 {strategy_id} 读取客户信息失败: {e}")
                import traceback
                logger.error(traceback.format_exc())
                return
            
            # 2. 获取或创建REST客户端（复用客户端实例，减少连接开销）
            # 使用customer_id作为key的一部分，确保不同客户使用不同的客户端
            client_key = f"{exchange}_{api_key}_{is_demo}"
            if client_key not in self.rest_clients:
                # 创建新的REST客户端（仅用于下单，不使用WebSocket）
                # 所有参数都从数据库读取，不使用config中的值
                client = create_exchange_client(
                    exchange=exchange,  # 从数据库读取
                    client_type='rest',  # 明确指定为REST，不使用WebSocket
                    api_key=api_key,  # 从数据库读取
                    api_secret=api_secret,  # 从数据库读取
                    passphrase=passphrase,  # 从数据库读取
                    is_demo=is_demo  # 从数据库读取
                )
                self.rest_clients[client_key] = client
                logger.info(f"✅ 策略 {strategy_id} 创建REST客户端（用于下单）: {client_key}")
            else:
                # 复用已有的REST客户端
                client = self.rest_clients[client_key]
                logger.debug(f"♻️ 策略 {strategy_id} 复用REST客户端: {client_key}")
            
            signal_volume = getattr(signal, 'volume', getattr(signal, 'quantity', 0))
            client_order_id = f"strategy_{strategy_id}_{int(datetime.now().timestamp())}"
            
            # 通过REST API下单（不通过WebSocket，减少WebSocket压力）
            logger.info(f"📤 策略 {strategy_id} 通过REST API下单: {signal.symbol} BUY {signal_volume}")
            response = await client.place_order(
                symbol=signal.symbol,
                side='buy',
                order_type='market',
                quantity=signal_volume,
                price=None,  # 市价单不需要价格
                client_order_id=client_order_id
            )
            
            # 解析响应
            if isinstance(response, dict):
                # OKX格式
                if response.get('code') == '0' and response.get('data'):
                    order_id = response['data'][0].get('ordId', '')
                    logger.info(f"✅ 策略 {strategy_id} 买入订单已提交: order_id={order_id}")
                    
                    # 记录到数据库
                    await self._record_trade(strategy_id, {
                        'order_id': order_id,
                        'symbol': signal.symbol,
                        'side': 'BUY',
                        'price': signal.price,
                        'quantity': signal_volume,
                        'timestamp': datetime.now(),
                        'status': 'submitted'
                    })
                else:
                    error_msg = response.get('msg', '未知错误')
                    logger.error(f"❌ 策略 {strategy_id} 买入订单失败: {error_msg}")
            else:
                # 统一格式响应
                if hasattr(response, 'order_id') and response.order_id:
                    logger.info(f"✅ 策略 {strategy_id} 买入订单已提交: order_id={response.order_id}")
                    await self._record_trade(strategy_id, {
                        'order_id': response.order_id,
                        'symbol': signal.symbol,
                        'side': 'BUY',
                        'price': getattr(response, 'avg_price', signal.price),
                        'quantity': getattr(response, 'filled_quantity', signal_volume),
                        'timestamp': datetime.now(),
                        'status': getattr(response, 'status', 'submitted').value if hasattr(getattr(response, 'status', None), 'value') else 'submitted'
                    })
                else:
                    logger.error(f"❌ 策略 {strategy_id} 买入订单失败")
            
        except Exception as e:
            logger.error(f"执行买入订单异常: {e}")
            import traceback
            logger.error(traceback.format_exc())
    
    async def _execute_sell_order(self, strategy_id: str, signal: Signal, config: StrategyTradeConfig):
        """
        执行卖出订单 - 通过REST API（不通过WebSocket，减少WebSocket压力）
        
        架构说明：
        - WebSocket：仅用于接收实时市场数据（K线、深度等）
        - REST API：用于执行交易订单（买入、卖出）
        - 多用户支持：从数据库读取客户账户信息（所有账户数据都在数据库中）
        """
        try:
            # 1. 从数据库读取客户账户信息（所有账户数据都在数据库中）
            if not config.customer_id:
                logger.error(f"策略 {strategy_id} 缺少customer_id，无法从数据库读取账户信息")
                return
            
            try:
                from database.db import get_customer_by_id
                customer_data = get_customer_by_id(self.db_pool, config.customer_id, config.is_demo)
                if not customer_data:
                    logger.error(f"策略 {strategy_id} 无法找到客户: {config.customer_id} (is_demo={config.is_demo})")
                    return
                
                # 从数据库读取所有账户信息
                api_key = customer_data.get('api_key', '')
                api_secret = customer_data.get('api_secret', '')
                passphrase = customer_data.get('passphrase', '')
                exchange = customer_data.get('exchange', 'OKX').lower()  # 从数据库读取交易所
                is_demo = customer_data.get('is_demo', config.is_demo)
                
                if not api_key or not api_secret:
                    logger.error(f"策略 {strategy_id} 客户 {config.customer_id} 的API凭证不完整")
                    return
                
                logger.info(f"✅ 策略 {strategy_id} 使用客户账户: {config.customer_id} (交易所: {exchange})")
                
            except Exception as e:
                logger.error(f"策略 {strategy_id} 读取客户信息失败: {e}")
                import traceback
                logger.error(traceback.format_exc())
                return
            
            # 2. 获取或创建REST客户端（复用客户端实例，减少连接开销）
            # 使用customer_id作为key的一部分，确保不同客户使用不同的客户端
            client_key = f"{exchange}_{api_key}_{is_demo}"
            if client_key not in self.rest_clients:
                # 创建新的REST客户端（仅用于下单，不使用WebSocket）
                client = create_exchange_client(
                    exchange=exchange,  # 使用数据库中的交易所
                    client_type='rest',  # 明确指定为REST，不使用WebSocket
                    api_key=api_key,
                    api_secret=api_secret,
                    passphrase=passphrase,
                    is_demo=is_demo  # 使用数据库中的is_demo
                )
                self.rest_clients[client_key] = client
                logger.info(f"✅ 策略 {strategy_id} 创建REST客户端（用于下单）: {client_key}")
            else:
                # 复用已有的REST客户端
                client = self.rest_clients[client_key]
                logger.debug(f"♻️ 策略 {strategy_id} 复用REST客户端: {client_key}")
            
            signal_volume = getattr(signal, 'volume', getattr(signal, 'quantity', 0))
            client_order_id = f"strategy_{strategy_id}_{int(datetime.now().timestamp())}"
            
            # 通过REST API下单（不通过WebSocket，减少WebSocket压力）
            logger.info(f"📤 策略 {strategy_id} 通过REST API下单: {signal.symbol} SELL {signal_volume}")
            response = await client.place_order(
                symbol=signal.symbol,
                side='sell',
                order_type='market',
                quantity=signal_volume,
                price=None,
                client_order_id=client_order_id,
                reduce_only=True  # 只平仓
            )
            
            # 解析响应（同买入订单）
            if isinstance(response, dict):
                # OKX格式
                if response.get('code') == '0' and response.get('data'):
                    order_id = response['data'][0].get('ordId', '')
                    logger.info(f"✅ 策略 {strategy_id} 卖出订单已提交: order_id={order_id}")
                    
                    # 记录到数据库
                    await self._record_trade(strategy_id, {
                        'order_id': order_id,
                        'symbol': signal.symbol,
                        'side': 'SELL',
                        'price': signal.price,
                        'quantity': signal_volume,
                        'timestamp': datetime.now(),
                        'status': 'submitted'
                    })
                else:
                    error_msg = response.get('msg', '未知错误')
                    logger.error(f"❌ 策略 {strategy_id} 卖出订单失败: {error_msg}")
            else:
                # 统一格式响应
                if hasattr(response, 'order_id') and response.order_id:
                    logger.info(f"✅ 策略 {strategy_id} 卖出订单已提交: order_id={response.order_id}")
                    await self._record_trade(strategy_id, {
                        'order_id': response.order_id,
                        'symbol': signal.symbol,
                        'side': 'SELL',
                        'price': getattr(response, 'avg_price', signal.price),
                        'quantity': getattr(response, 'filled_quantity', signal_volume),
                        'timestamp': datetime.now(),
                        'status': getattr(response, 'status', 'submitted').value if hasattr(getattr(response, 'status', None), 'value') else 'submitted'
                    })
                else:
                    logger.error(f"❌ 策略 {strategy_id} 卖出订单失败")
            
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
            signal_volume = getattr(signal, 'volume', getattr(signal, 'quantity', 0))
            order_value = signal.price * signal_volume
            if order_value > config.max_position_value:
                logger.warning(f"订单价值 {order_value} 超过限制 {config.max_position_value}")
                return False
            
            # 2. 检查总持仓
            try:
                instance_result = self.db_pool.query(
                    "SELECT id FROM strategy_instances WHERE instance_name = %s",
                    (strategy_id,)
                )
                if instance_result:
                    instance_id = instance_result[0]['id']
                    positions = self.db_pool.query(
                        """SELECT SUM(quantity * current_price) as total_value 
                           FROM strategy_positions 
                           WHERE instance_id = %s AND status = 'OPEN'""",
                        (instance_id,)
                    )
                    if positions and positions[0].get('total_value'):
                        total_position_value = float(positions[0]['total_value'])
                        if total_position_value + order_value > config.max_position_value:
                            logger.warning(f"总持仓价值 {total_position_value + order_value} 超过限制 {config.max_position_value}")
                            return False
            except Exception as e:
                logger.warning(f"检查持仓失败: {e}")
            
            # 3. 检查日交易次数
            try:
                if instance_result:
                    instance_id = instance_result[0]['id']
                    today = datetime.now().date()
                    today_trades = self.db_pool.query(
                        """SELECT COUNT(*) as count 
                           FROM strategy_trades 
                           WHERE instance_id = %s AND DATE(executed_at) = %s""",
                        (instance_id, today)
                    )
                    if today_trades:
                        trade_count = today_trades[0].get('count', 0)
                        # 默认限制：每天最多100笔交易
                        max_daily_trades = getattr(config, 'max_daily_trades', 100)
                        if trade_count >= max_daily_trades:
                            logger.warning(f"日交易次数 {trade_count} 超过限制 {max_daily_trades}")
                            return False
            except Exception as e:
                logger.warning(f"检查日交易次数失败: {e}")
            
            # 4. 其他风险检查
            
            return True
            
        except Exception as e:
            logger.error(f"风险检查异常: {e}")
            return False
    
    async def _record_trade(self, strategy_id: str, trade_data: dict):
        """记录交易到数据库"""
        try:
            import uuid
            from datetime import datetime
            
            # 获取策略实例ID
            instance_result = self.db_pool.query(
                "SELECT id FROM strategy_instances WHERE instance_name = %s",
                (strategy_id,)
            )
            
            if not instance_result:
                logger.warning(f"策略实例 {strategy_id} 不存在，无法记录交易")
                return
            
            instance_id = instance_result[0]['id']
            trade_id = trade_data.get('trade_id') or f"trade_{uuid.uuid4().hex[:16]}"
            
            # 插入交易记录
            self.db_pool.execute(
                """INSERT INTO strategy_trades 
                   (instance_id, trade_id, position_id, symbol, side, quantity, price, amount, 
                    commission, slippage, pnl, trade_type, reason, metadata_json, executed_at)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                (
                    instance_id,
                    trade_id,
                    trade_data.get('position_id'),
                    trade_data.get('symbol'),
                    trade_data.get('side', 'BUY'),
                    trade_data.get('quantity', 0),
                    trade_data.get('price', 0),
                    trade_data.get('amount', 0),
                    trade_data.get('commission', 0),
                    trade_data.get('slippage', 0),
                    trade_data.get('pnl', 0),
                    trade_data.get('trade_type', 'OPEN'),
                    trade_data.get('reason', ''),
                    json.dumps(trade_data.get('metadata', {}), ensure_ascii=False) if trade_data.get('metadata') else None,
                    trade_data.get('executed_at', datetime.now())
                )
            )
            
            logger.info(f"📝 记录交易到数据库: {trade_id} for {strategy_id}")
            
        except Exception as e:
            logger.error(f"记录交易失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
    
    async def _close_all_positions(self, strategy_id: str):
        """平掉策略的所有持仓"""
        try:
            config = self.running_strategies[strategy_id]
            
            # 查询当前持仓
            instance_result = self.db_pool.query(
                "SELECT id FROM strategy_instances WHERE instance_name = %s",
                (strategy_id,)
            )
            
            if not instance_result:
                logger.warning(f"策略实例 {strategy_id} 不存在")
                return
            
            instance_id = instance_result[0]['id']
            positions = self.db_pool.query(
                "SELECT position_id, symbol, side, quantity, entry_price FROM strategy_positions WHERE instance_id = %s AND status = 'OPEN'",
                (instance_id,)
            )
            
            if not positions:
                logger.info(f"策略 {strategy_id} 没有持仓")
                return
            
            logger.info(f"🔄 策略 {strategy_id} 平仓 {len(positions)} 个持仓")
            
            # 平仓每个持仓
            for position in positions:
                try:
                    # 创建平仓信号
                    close_signal = Signal(
                        symbol=position['symbol'],
                        direction='SELL' if position['side'] == 'LONG' else 'BUY',
                        price=0,  # 市价单
                        volume=position['quantity'],
                        timestamp=datetime.now(),
                        reason='策略停止平仓'
                    )
                    
                    # 执行平仓
                    await self._execute_signal(strategy_id, close_signal, config)
                    
                except Exception as e:
                    logger.error(f"平仓持仓 {position['position_id']} 失败: {e}")
            
        except Exception as e:
            logger.error(f"平仓所有持仓失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
    
    async def _cleanup_ws_client(self, strategy_id: str):
        """
        清理 WebSocket 客户端（仅用于接收市场数据，不用于下单）
        
        注意：REST客户端不在这里清理，因为它们可能被多个策略复用
        """
        try:
            if strategy_id in self.ws_clients:
                client = self.ws_clients[strategy_id]
                # 获取策略配置以取消订阅
                config = self.running_strategies.get(strategy_id)
                
                # 取消订阅和关闭连接
                if hasattr(client, 'unsubscribe') and config:
                    try:
                        await client.unsubscribe(config.symbol)
                    except Exception as e:
                        logger.warning(f"取消订阅失败: {e}")
                
                if hasattr(client, 'close'):
                    try:
                        await client.close()
                    except Exception as e:
                        logger.warning(f"关闭WebSocket连接失败: {e}")
                del self.ws_clients[strategy_id]
                logger.info(f"✅ 策略 {strategy_id} WebSocket 已清理（仅用于市场数据）")
        except Exception as e:
            logger.error(f"清理 WebSocket 失败: {e}")
    
    async def _mark_strategy_error(self, strategy_id: str, error_msg: str):
        """标记策略为错误状态"""
        try:
            strategy_info = self.strategy_manager.get_strategy(strategy_id)
            if strategy_info:
                strategy_info.status = 'ERROR'
                # 更新数据库状态
                try:
                    self.db_pool.execute(
                        "UPDATE strategy_instances SET status = 'ERROR', updated_at = NOW() WHERE instance_name = %s",
                        (strategy_id,)
                    )
                except Exception as e:
                    logger.warning(f"更新数据库状态失败: {e}")
                logger.error(f"❌ 策略 {strategy_id} 错误: {error_msg}")
        except Exception as e:
            logger.error(f"标记策略错误失败: {e}")
    
    async def _preheat_historical_data(self, strategy, config: StrategyTradeConfig,
                                       preheat_bars: int = 300):
        """
        历史数据预热：在订阅实时流之前，用历史K线填满策略数据缓存。

        解决冷启动问题：策略启动后 market_data/price_data 从空开始累积，
        依赖历史窗口的指标（MA/MACD/布林/RSI）在攒够 N 根之前信号失真。

        关键安全约束：只填充数据缓冲区，**不**调用 process_market_data /
        on_market_data，因此历史 bar 绝不会触发策略逻辑或产生真实下单信号。

        Args:
            strategy: 策略实例
            config: 策略配置
            preheat_bars: 预热根数（OKX 单次上限 300）
        """
        strategy_id = config.strategy_id
        try:
            # 用公共 REST 客户端拉历史（历史数据无需密钥）
            rest_client = create_exchange_client(
                exchange='okx', client_type='rest', is_demo=config.is_demo)

            timeframe = getattr(strategy, 'timeframe', '') or ''
            if not timeframe:
                logger.info(f"策略 {strategy_id} 未声明 timeframe，跳过历史预热")
                return
            bar = self._get_interval_str(timeframe)
            # get_historical_klines 单次上限 300；不传 after 即返回最新 N 根（倒序）
            rows = await rest_client.get_historical_klines(
                symbol=config.symbol, interval=bar,
                start_time=None, end_time=None, limit=min(preheat_bars, 300))

            if not rows:
                logger.warning(f"⚠️ 策略 {strategy_id} 历史预热未获取到数据，将冷启动")
                return

            # OKX 返回倒序（新→旧），预热需按时间升序喂入
            rows_sorted = sorted(rows, key=lambda r: int(r[0]))

            has_price_data = hasattr(strategy, 'price_data')
            count = 0
            for row in rows_sorted:
                try:
                    md = MarketData(
                        symbol=config.symbol,
                        timestamp=datetime.fromtimestamp(int(row[0]) / 1000),
                        open=float(row[1]),
                        high=float(row[2]),
                        low=float(row[3]),
                        close=float(row[4]),
                        volume=float(row[5]),
                    )
                except (ValueError, IndexError, TypeError):
                    continue

                # 直接填充缓冲区，绕过 process_market_data（不触发策略逻辑/信号）
                strategy.market_data.append(md)
                if has_price_data:
                    strategy.price_data.append(md.close)
                    strategy.volume_data.append(md.volume)
                count += 1

            # 记录预热最后一根的时间戳，实时流据此去重续接（避免衔接处重复根）
            if count > 0:
                strategy._last_bar_ts = int(rows_sorted[-1][0])

            # 预热完成后计算一次指标，使指标缓存与预热数据对齐
            if has_price_data and hasattr(strategy, '_calculate_indicators'):
                try:
                    strategy._calculate_indicators()
                except Exception as e:
                    logger.debug(f"策略 {strategy_id} 预热后计算指标失败（忽略）: {e}")

            logger.info(f"🔥 策略 {strategy_id} 历史预热完成: {count} 根 {bar} K线 "
                        f"({config.symbol})，实时流将在此基础上续接")
        except Exception as e:
            # 预热失败不应阻断策略启动，退化为冷启动
            logger.warning(f"⚠️ 策略 {strategy_id} 历史预热失败，退化为冷启动: {e}")

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

