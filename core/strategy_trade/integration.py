"""
策略交易系统集成模块
将策略交易服务集成到 TradeServer 中
"""

import asyncio
from typing import Optional
from utils.logger import get_logger
from database.db import MySQLPool
from core.market_trade.trade_service import TradeService
from core.strategy_trade.core.manager import StrategyManager
from core.strategy_trade.strategy_trade_service import StrategyTradeService, StrategyTradeConfig
from datetime import datetime

logger = get_logger(__name__)

# 可选导入权限服务
try:
    from auth.decorators import get_current_user_id, get_current_user
    from auth.permission_service import permission_service
    AUTH_AVAILABLE = True
except ImportError:
    AUTH_AVAILABLE = False
    def get_current_user_id():
        return None
    def get_current_user():
        return None
    permission_service = None

class StrategyTradeIntegration:
    """
    策略交易集成器
    
    负责将策略交易服务集成到现有的交易框架中
    """
    
    def __init__(self, db_pool: MySQLPool, trade_service: TradeService, strategy_manager: Optional[StrategyManager] = None):
        self.db_pool = db_pool
        self.trade_service = trade_service

        # 策略管理器：优先复用外部传入的共享实例（与 /strategy/create、/strategy/instances
        # 使用同一个管理器），避免"创建/列表"与"启动实盘"读写两个不同的内存管理器，
        # 导致启动时按名称查不到刚创建的策略（策略 xxx 不存在）。
        self.strategy_manager = strategy_manager or StrategyManager()
        
        # 创建策略交易服务
        self.strategy_trade_service = StrategyTradeService(
            db_pool=db_pool,
            trade_service=trade_service,
            strategy_manager=self.strategy_manager
        )
        
        self._monitor_task: Optional[asyncio.Task] = None
        
        logger.info("✅ 策略交易集成器初始化完成")
    
    async def start(self):
        """启动策略交易系统"""
        try:
            # 从数据库加载策略配置
            await self._load_strategies_from_db()
            
            # 启动需要自动运行的策略
            await self._start_auto_strategies()
            
            # 启动监控任务
            self._monitor_task = asyncio.create_task(self._monitor_strategies())
            
            logger.info("✅ 策略交易系统已启动")
            
        except Exception as e:
            logger.error(f"启动策略交易系统失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
    
    async def stop(self):
        """停止策略交易系统"""
        try:
            # 停止监控任务
            if self._monitor_task:
                self._monitor_task.cancel()
                try:
                    await self._monitor_task
                except asyncio.CancelledError:
                    pass
            
            # 停止所有运行中的策略
            running = await self.strategy_trade_service.list_running_strategies()
            for strategy in running:
                await self.strategy_trade_service.stop_strategy(
                    strategy['strategy_id'],
                    close_positions=True
                )
            
            logger.info("✅ 策略交易系统已停止")
            
        except Exception as e:
            logger.error(f"停止策略交易系统失败: {e}")
    
    async def _load_strategies_from_db(self):
        """从数据库加载策略配置"""
        try:
            import json
            from core.strategy_trade.strategy_loader import get_strategy_loader
            
            logger.info("从数据库加载策略配置")
            
            # 查询所有未删除的策略实例
            strategies = self.db_pool.query(
                "SELECT instance_name, strategy_name, symbol, timeframe, status, config_json "
                "FROM strategy_instances "
                "WHERE status != 'DELETED' "
                "ORDER BY created_at DESC"
            )
            
            strategy_loader = get_strategy_loader()
            loaded_count = 0
            
            for row in strategies:
                try:
                    instance_name = row.get('instance_name')
                    strategy_type = row.get('strategy_name')
                    symbol = row.get('symbol', 'BTC-USDT-SWAP')
                    config_json_str = row.get('config_json')
                    
                    # 解析配置
                    config = {}
                    if config_json_str:
                        if isinstance(config_json_str, str):
                            config = json.loads(config_json_str)
                        else:
                            config = config_json_str
                    
                    # 获取策略类
                    strategy_class = strategy_loader.get_strategy(strategy_type)
                    if not strategy_class:
                        logger.warning(f"策略类型 {strategy_type} 不存在，跳过实例 {instance_name}")
                        continue
                    
                    # 创建策略实例
                    strategy = strategy_class(name=instance_name, symbol=symbol, config=config)
                    
                    # 添加到管理器
                    strategy_id = self.strategy_manager.add_strategy(strategy, strategy_type)
                    
                    if strategy_id:
                        loaded_count += 1
                        logger.debug(f"从数据库加载策略实例: {instance_name} ({strategy_type})")
                    
                except Exception as load_error:
                    logger.error(f"加载策略实例 {row.get('instance_name')} 失败: {load_error}")
                    import traceback
                    logger.error(traceback.format_exc())
            
            logger.info(f"从数据库加载了 {loaded_count} 个策略实例")
            
        except Exception as e:
            logger.error(f"加载策略配置失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
    
    async def _start_auto_strategies(self):
        """启动设置为自动运行的策略"""
        try:
            # TODO: 查询数据库中 auto_start = 1 的策略
            # 并启动它们
            
            logger.info("启动自动运行策略")
            
        except Exception as e:
            logger.error(f"启动自动策略失败: {e}")
    
    async def _monitor_strategies(self):
        """监控策略运行状态"""
        while True:
            try:
                await asyncio.sleep(60)  # 每分钟检查一次
                
                # 获取所有运行中的策略
                strategies = await self.strategy_trade_service.list_running_strategies()
                
                logger.info(f"📊 当前运行策略数: {len(strategies)}")
                
                # 检查每个策略的健康状态
                for strategy in strategies:
                    if strategy['status'] == 'ERROR':
                        logger.error(f"⚠️ 策略 {strategy['strategy_id']} 处于错误状态")
                        # TODO: 发送告警
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"监控策略异常: {e}")
    
    # ==================== API 接口 ====================
    
    async def api_create_strategy(self, strategy_type: str, name: str, config: dict) -> dict:
        """
        API: 创建新策略（带权限控制）
        
        权限规则：
        - 普通用户：只能创建自己的策略
        - 管理员：可以创建任意策略
        
        Args:
            strategy_type: 策略类型 (RSI_Strategy, MA_Cross_Strategy, etc.)
            name: 策略名称
            config: 策略配置
        
        Returns:
            {'success': True, 'strategy_id': 'xxx'}
        """
        try:
            # 获取当前用户信息（用于记录策略创建者）
            user_id = None
            if AUTH_AVAILABLE:
                user_id = get_current_user_id()
            
            # 从策略加载器获取策略类
            from core.strategy_trade.strategy_loader import get_strategy_loader
            
            strategy_loader = get_strategy_loader()
            strategy_class = strategy_loader.get_strategy(strategy_type)
            if not strategy_class:
                return {'success': False, 'message': f'未知策略类型: {strategy_type}'}
            
            # 创建策略实例
            strategy_name = config.get('name', f'{strategy_type}_{datetime.now().timestamp()}')
            strategy_symbol = config.get('symbol', 'BTC-USDT')
            strategy = strategy_class(name=strategy_name, symbol=strategy_symbol, config=config)
            
            # 添加到管理器
            strategy_id = self.strategy_manager.add_strategy(strategy, strategy_type)
            
            # 保存到数据库（包含用户ID信息）
            await self._save_strategy_to_db(strategy_id, strategy_type, name, config, user_id=user_id)
            
            return {
                'success': True,
                'strategy_id': strategy_id,
                'message': '策略创建成功'
            }
            
        except Exception as e:
            logger.error(f"创建策略失败: {e}")
            return {'success': False, 'message': str(e)}
    
    async def api_start_strategy(self, strategy_id: str, config: dict) -> dict:
        """
        API: 启动策略实盘交易（带权限控制）
        
        权限规则：
        - 普通用户：只能使用自己的账号（自动选择owner_user_id=当前用户ID的账号）
        - 管理员：可以选择任意账号（可以指定customer_id）
        
        Args:
            strategy_id: 策略ID
            config: 实盘配置
                - customer_id: 客户ID（customer_uid），管理员可选，普通用户自动选择自己的账号
                - signal_source_uid: 信号源UID（仅管理员可选，普通用户不能选择）
                - symbol: 交易对
                - initial_capital: 初始资金
                - max_position_value: 最大持仓价值
                - stop_loss_pct: 止损百分比
                - take_profit_pct: 止盈百分比
                - exchange/is_demo: 可选，但会从数据库读取客户信息覆盖
        
        Returns:
            {'success': True}
        
        注意：所有账户信息（api_key, api_secret, passphrase, exchange, is_demo）都从数据库读取
        """
        try:
            # 1. 获取当前用户信息
            # 注意：本协程通常由 run_async_safe 在独立线程中执行，那里访问不到
            # Flask 的 session/request，因此优先使用端点在请求线程内透传进来的身份。
            user_id = config.get('_auth_user_id')
            is_admin = config.get('_auth_is_admin')

            if user_id is None and AUTH_AVAILABLE:
                # 回退：若确实运行在请求线程内，仍尝试从上下文获取
                user_id = get_current_user_id()

            if is_admin is None:
                is_admin = False
                if user_id and permission_service:
                    is_admin = permission_service.is_admin(user_id)
            
            # 2. 权限控制：确定使用的customer_id和signal_source_uid
            customer_id = config.get('customer_id', '')
            signal_source_uid = config.get('signal_source_uid', '')  # 信号源UID（如果有需要）
            
            if not is_admin:
                # 普通用户：只能使用自己的账号，不能选择信号源
                # 2.1 处理customer_id
                if customer_id:
                    # 验证用户是否有权限使用该账号
                    if not self._check_customer_ownership(customer_id, user_id):
                        return {
                            'success': False,
                            'message': f'无权使用客户账号 {customer_id}，只能使用自己的账号'
                        }
                else:
                    # 自动选择用户的第一个账号
                    customer_id, selected_is_demo = self._get_user_customer_id(user_id, config.get('is_demo', True))
                    if not customer_id:
                        return {
                            'success': False,
                            'message': '未找到您的账号，请先创建客户账号'
                        }
                    # 以实际选中账号的 is_demo 为准（避免前端传入的模式与账号不一致导致后续校验失败）
                    if selected_is_demo is not None:
                        config['is_demo'] = bool(selected_is_demo)
                    logger.info(f"普通用户 {user_id} 自动选择客户账号: {customer_id} (is_demo={config.get('is_demo')})")
                
                # 2.2 普通用户不能选择信号源（如果提供了，忽略）
                if signal_source_uid:
                    logger.warning(f"普通用户 {user_id} 尝试指定信号源 {signal_source_uid}，已忽略（只能使用自己的账号）")
                    signal_source_uid = ''  # 清空，不使用信号源
            else:
                # 管理员：可以选择任意账号和信号源
                # 2.1 处理customer_id
                if not customer_id:
                    # 如果没有指定，尝试使用第一个可用账号（可以是任何账号）
                    customer_id, selected_is_demo = self._get_default_customer_id(config.get('is_demo', True))
                    if customer_id:
                        # 以实际选中账号的 is_demo 为准
                        if selected_is_demo is not None:
                            config['is_demo'] = bool(selected_is_demo)
                        logger.info(f"管理员未指定账号，使用默认账号: {customer_id} (is_demo={config.get('is_demo')})")
                    else:
                        return {
                            'success': False,
                            'message': '未找到可用账号，请指定customer_id'
                        }
                else:
                    # 验证账号是否存在（不按 is_demo 过滤，存在则以账号真实 is_demo 为准）
                    existing_is_demo = self._get_customer_is_demo(customer_id)
                    if existing_is_demo is None:
                        return {
                            'success': False,
                            'message': f'客户账号 {customer_id} 不存在'
                        }
                    config['is_demo'] = bool(existing_is_demo)
                    logger.info(f"管理员选择客户账号: {customer_id} (is_demo={config.get('is_demo')})")
                
                # 2.2 管理员可以选择信号源（如果提供了，验证是否存在）
                if signal_source_uid:
                    if not self._check_signal_source_exists(signal_source_uid, config.get('is_demo', True)):
                        return {
                            'success': False,
                            'message': f'信号源 {signal_source_uid} 不存在'
                        }
                    logger.info(f"管理员选择信号源: {signal_source_uid}")
                # 如果不提供signal_source_uid，则不使用信号源（仅使用客户账号）
            
            # 3. 验证必需参数
            if not customer_id:
                return {
                    'success': False,
                    'message': '缺少必需参数：customer_id（客户ID，所有账户数据将从数据库读取）'
                }
            
            # 构造策略交易配置（所有账户数据从数据库读取，不需要传递API凭证）
            trade_config = StrategyTradeConfig(
                strategy_id=strategy_id,
                symbol=config.get('symbol', 'BTC-USDT-SWAP'),
                exchange=config.get('exchange', 'okx'),  # 备用，实际从数据库读取
                is_demo=config.get('is_demo', True),  # 备用，实际从数据库读取
                initial_capital=config.get('initial_capital', 10000.0),
                max_position_value=config.get('max_position_value', 5000.0),
                stop_loss_pct=config.get('stop_loss_pct', 0.03),
                take_profit_pct=config.get('take_profit_pct', 0.06),
                customer_id=customer_id  # 必需：客户ID，所有账户信息从数据库读取
            )
            
            # 启动策略
            success = await self.strategy_trade_service.start_strategy(trade_config)
            
            if success:
                # 更新数据库状态
                await self._update_strategy_status(strategy_id, 'RUNNING')
                
                return {
                    'success': True,
                    'message': '策略已启动'
                }
            else:
                return {
                    'success': False,
                    'message': '策略启动失败'
                }
            
        except Exception as e:
            logger.error(f"启动策略失败: {e}")
            return {'success': False, 'message': str(e)}
    
    async def api_stop_strategy(self, strategy_id: str, close_positions: bool = True) -> dict:
        """
        API: 停止策略
        
        Args:
            strategy_id: 策略ID
            close_positions: 是否平仓
        
        Returns:
            {'success': True}
        """
        try:
            success = await self.strategy_trade_service.stop_strategy(
                strategy_id,
                close_positions=close_positions
            )
            
            if success:
                await self._update_strategy_status(strategy_id, 'STOPPED')
                return {'success': True, 'message': '策略已停止'}
            else:
                return {'success': False, 'message': '策略停止失败'}
            
        except Exception as e:
            logger.error(f"停止策略失败: {e}")
            return {'success': False, 'message': str(e)}
    
    async def api_get_strategy_config(self, strategy_id: str) -> dict:
        """
        API: 获取策略配置（用于编辑）
        
        Args:
            strategy_id: 策略ID
        
        Returns:
            {'success': True, 'data': {...}}
        """
        try:
            import json
            
            # 从数据库读取策略配置
            result = self.db_pool.query(
                "SELECT instance_name, strategy_name, symbol, timeframe, status, config_json "
                "FROM strategy_instances WHERE instance_name = %s",
                (strategy_id,)
            )
            
            if not result:
                # 尝试从内存中的策略管理器获取
                strategy_info = self.strategy_manager.get_strategy(strategy_id)
                if strategy_info:
                    # 从策略对象获取 symbol 和 timeframe
                    symbol = getattr(strategy_info.strategy, 'symbol', '') if hasattr(strategy_info, 'strategy') else ''
                    timeframe = getattr(strategy_info.strategy, 'timeframe', '') if hasattr(strategy_info, 'strategy') else ''

                    # 获取配置
                    config = {}
                    if hasattr(strategy_info.strategy, 'config'):
                        config = strategy_info.strategy.config
                    elif hasattr(strategy_info, 'config'):
                        config = strategy_info.config

                    return {
                        'success': True,
                        'data': {
                            'name': strategy_info.name,
                            'strategy_type': strategy_info.strategy_type if hasattr(strategy_info, 'strategy_type') else '',
                            'symbol': symbol,
                            'timeframe': timeframe,
                            'status': strategy_info.status if hasattr(strategy_info, 'status') else 'unknown',
                            'config': config
                        }
                    }
                else:
                    return {'success': False, 'message': f'策略 {strategy_id} 不存在'}
            
            row = result[0]
            
            # 解析配置
            config = {}
            config_json_str = row.get('config_json')
            if config_json_str:
                if isinstance(config_json_str, str):
                    config = json.loads(config_json_str)
                else:
                    config = config_json_str
            
            return {
                'success': True,
                'data': {
                    'name': row.get('instance_name'),
                    'strategy_type': row.get('strategy_name'),
                    'symbol': row.get('symbol'),
                    'timeframe': row.get('timeframe'),
                    'status': row.get('status'),
                    'config': config
                }
            }
            
        except Exception as e:
            logger.error(f"获取策略配置失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return {'success': False, 'message': str(e)}
    
    async def api_get_strategy_status(self, strategy_id: str) -> dict:
        """
        API: 获取策略状态
        
        Returns:
            策略状态信息
        """
        try:
            status = await self.strategy_trade_service.get_strategy_status(strategy_id)
            return {'success': True, 'data': status}
        except Exception as e:
            logger.error(f"获取策略状态失败: {e}")
            return {'success': False, 'message': str(e)}
    
    async def api_list_strategies(self) -> dict:
        """
        API: 列出所有策略
        
        Returns:
            策略列表
        """
        try:
            # 从 strategy_manager 获取所有策略
            all_strategies = self.strategy_manager.get_all_strategies()
            
            # 获取运行状态
            running_strategies = await self.strategy_trade_service.list_running_strategies()
            running_ids = {s['strategy_id'] for s in running_strategies}
            
            strategies = []
            for info in all_strategies:
                strategies.append({
                    'id': info.id,
                    'name': info.name,
                    'type': info.strategy_type,
                    'status': 'RUNNING' if info.id in running_ids else info.status,
                    'created_time': info.created_time.isoformat(),
                    'performance': info.performance
                })
            
            return {
                'success': True,
                'data': strategies
            }
            
        except Exception as e:
            logger.error(f"列出策略失败: {e}")
            return {'success': False, 'message': str(e)}
    
    # ==================== 数据库操作 ====================
    
    async def _save_strategy_to_db(self, strategy_id: str, strategy_type: str, name: str, config: dict, user_id: Optional[int] = None):
        """保存策略到数据库"""
        try:
            import json
            from datetime import datetime
            
            # 检查策略实例是否已存在
            existing = self.db_pool.query(
                "SELECT id FROM strategy_instances WHERE instance_name = %s",
                (strategy_id,)
            )
            
            config_json = json.dumps(config, ensure_ascii=False)
            
            if existing:
                # 更新现有策略实例
                self.db_pool.execute(
                    """UPDATE strategy_instances 
                       SET config_json = %s, updated_at = NOW()
                       WHERE instance_name = %s""",
                    (config_json, strategy_id)
                )
                logger.info(f"更新策略实例配置: {strategy_id}")
            else:
                # 创建新策略实例
                self.db_pool.execute(
                    """INSERT INTO strategy_instances 
                       (instance_name, strategy_name, symbol, timeframe, status, config_json, created_at)
                       VALUES (%s, %s, %s, %s, %s, %s, NOW())""",
                    (
                        strategy_id,
                        strategy_type,
                        config.get('symbol', 'BTC-USDT-SWAP'),
                        config.get('timeframe', '1h'),
                        'STOPPED',
                        config_json
                    )
                )
                logger.info(f"保存策略实例到数据库: {strategy_id}")
                
        except Exception as e:
            logger.error(f"保存策略到数据库失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
    
    async def _update_strategy_status(self, strategy_id: str, status: str):
        """更新策略状态"""
        try:
            from datetime import datetime
            
            # 更新状态
            update_fields = ["status = %s", "updated_at = NOW()"]
            update_params = [status]
            
            # 根据状态更新相应的时间字段
            if status == 'RUNNING':
                update_fields.append("started_at = NOW()")
            elif status in ['STOPPED', 'ERROR']:
                update_fields.append("stopped_at = NOW()")
            
            update_params.insert(0, strategy_id)
            
            self.db_pool.execute(
                f"UPDATE strategy_instances SET {', '.join(update_fields)} WHERE instance_name = %s",
                tuple(update_params)
            )
            
            logger.debug(f"更新策略状态: {strategy_id} -> {status}")
            
        except Exception as e:
            logger.error(f"更新策略状态失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
    
    def _check_customer_ownership(self, customer_id: str, user_id: Optional[int]) -> bool:
        """
        检查用户是否有权限使用指定的客户账号
        
        Args:
            customer_id: 客户ID
            user_id: 用户ID
        
        Returns:
            True if user owns the customer account
        """
        if not user_id:
            return False
        
        try:
            customer_data = self.db_pool.query(
                "SELECT owner_user_id FROM customers WHERE customer_uid = %s",
                (customer_id,)
            )
            
            if not customer_data:
                return False
            
            owner_user_id = customer_data[0].get('owner_user_id')
            return owner_user_id == user_id
            
        except Exception as e:
            logger.error(f"检查客户账号所有权失败: {e}")
            return False
    
    def _get_user_customer_id(self, user_id: Optional[int], is_demo: bool):
        """
        获取用户的客户账号ID（返回第一个启用的账号）
        
        Args:
            user_id: 用户ID
            is_demo: 是否模拟盘
        
        Returns:
            客户账号ID，如果不存在则返回None
        """
        if not user_id:
            return None, None

        try:
            customers = self.db_pool.query(
                "SELECT customer_uid, is_demo FROM customers WHERE owner_user_id = %s AND enabled = 1 AND is_demo = %s ORDER BY created_at DESC LIMIT 1",
                (user_id, is_demo)
            )
            if customers:
                return customers[0].get('customer_uid'), customers[0].get('is_demo')

            # 回退：请求的 is_demo 无匹配时，选用该用户任意启用账号（其真实 is_demo 以数据库为准）
            customers = self.db_pool.query(
                "SELECT customer_uid, is_demo FROM customers WHERE owner_user_id = %s AND enabled = 1 ORDER BY created_at DESC LIMIT 1",
                (user_id,)
            )
            if customers:
                logger.info(f"用户 {user_id} 无 is_demo={is_demo} 的账号，回退选用其账号 {customers[0].get('customer_uid')} (is_demo={customers[0].get('is_demo')})")
                return customers[0].get('customer_uid'), customers[0].get('is_demo')
            return None, None

        except Exception as e:
            logger.error(f"获取用户客户账号失败: {e}")
            return None, None
    
    def _get_default_customer_id(self, is_demo: bool):
        """
        获取默认客户账号ID（管理员使用，返回第一个启用的账号）
        
        Args:
            is_demo: 是否模拟盘
        
        Returns:
            客户账号ID，如果不存在则返回None
        """
        try:
            customers = self.db_pool.query(
                "SELECT customer_uid, is_demo FROM customers WHERE enabled = 1 AND is_demo = %s ORDER BY created_at DESC LIMIT 1",
                (is_demo,)
            )
            if customers:
                return customers[0].get('customer_uid'), customers[0].get('is_demo')

            # 回退：请求的 is_demo 无匹配时，选用任意启用账号（其真实 is_demo 以数据库为准）
            customers = self.db_pool.query(
                "SELECT customer_uid, is_demo FROM customers WHERE enabled = 1 ORDER BY created_at DESC LIMIT 1"
            )
            if customers:
                logger.info(f"无 is_demo={is_demo} 的可用账号，回退选用账号 {customers[0].get('customer_uid')} (is_demo={customers[0].get('is_demo')})")
                return customers[0].get('customer_uid'), customers[0].get('is_demo')
            return None, None

        except Exception as e:
            logger.error(f"获取默认客户账号失败: {e}")
            return None, None
    
    def _get_customer_is_demo(self, customer_id: str) -> Optional[int]:
        """
        查询客户账号的 is_demo（不按 is_demo 过滤）。

        Returns:
            账号的 is_demo 值（0/1），账号不存在则返回 None
        """
        try:
            rows = self.db_pool.query(
                "SELECT is_demo FROM customers WHERE customer_uid = %s LIMIT 1",
                (customer_id,)
            )
            if rows:
                return rows[0].get('is_demo')
            return None
        except Exception as e:
            logger.error(f"查询客户账号 is_demo 失败: {e}")
            return None

    def _check_customer_exists(self, customer_id: str, is_demo: bool) -> bool:
        """
        检查客户账号是否存在
        
        Args:
            customer_id: 客户ID
            is_demo: 是否模拟盘
        
        Returns:
            True if customer exists
        """
        try:
            customers = self.db_pool.query(
                "SELECT customer_uid FROM customers WHERE customer_uid = %s AND is_demo = %s",
                (customer_id, is_demo)
            )
            return len(customers) > 0
            
        except Exception as e:
            logger.error(f"检查客户账号是否存在失败: {e}")
            return False
    
    def _check_signal_source_exists(self, signal_source_uid: str, is_demo: bool) -> bool:
        """
        检查信号源是否存在
        
        Args:
            signal_source_uid: 信号源UID
            is_demo: 是否模拟盘
        
        Returns:
            True if signal source exists
        """
        try:
            from database.db import get_signal_source_by_id
            signal_source = get_signal_source_by_id(self.db_pool, signal_source_uid, is_demo)
            return signal_source is not None
            
        except Exception as e:
            logger.error(f"检查信号源是否存在失败: {e}")
            return False

