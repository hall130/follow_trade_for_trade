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

logger = get_logger(__name__)

class StrategyTradeIntegration:
    """
    策略交易集成器
    
    负责将策略交易服务集成到现有的交易框架中
    """
    
    def __init__(self, db_pool: MySQLPool, trade_service: TradeService):
        self.db_pool = db_pool
        self.trade_service = trade_service
        
        # 创建策略管理器
        self.strategy_manager = StrategyManager()
        
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
            # TODO: 实现从数据库加载策略
            # 可以复用 database/strategy_tables.sql 中的表结构
            
            logger.info("从数据库加载策略配置")
            
            # 示例：假设有 strategy_instances 表
            # query = "SELECT * FROM strategy_instances WHERE is_active = 1"
            # strategies = await self.db_pool.fetch_all(query)
            # 
            # for strategy_data in strategies:
            #     # 注册策略到 strategy_manager
            #     pass
            
        except Exception as e:
            logger.error(f"加载策略配置失败: {e}")
    
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
        API: 创建新策略
        
        Args:
            strategy_type: 策略类型 (RSI_Strategy, MA_Cross_Strategy, etc.)
            name: 策略名称
            config: 策略配置
        
        Returns:
            {'success': True, 'strategy_id': 'xxx'}
        """
        try:
            # 注册策略到 strategy_manager
            from core.strategy_trade.strategies import strategy_factory
            
            strategy_class = strategy_factory.get_strategy_class(strategy_type)
            if not strategy_class:
                return {'success': False, 'message': f'未知策略类型: {strategy_type}'}
            
            # 创建策略实例
            strategy = strategy_class(**config)
            
            # 添加到管理器
            strategy_id = self.strategy_manager.add_strategy(strategy, strategy_type)
            
            # 保存到数据库
            await self._save_strategy_to_db(strategy_id, strategy_type, name, config)
            
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
        API: 启动策略实盘交易
        
        Args:
            strategy_id: 策略ID
            config: 实盘配置 (symbol, exchange, is_demo, etc.)
        
        Returns:
            {'success': True}
        """
        try:
            # 构造策略交易配置
            trade_config = StrategyTradeConfig(
                strategy_id=strategy_id,
                symbol=config.get('symbol', 'BTC-USDT-SWAP'),
                exchange=config.get('exchange', 'okx'),
                is_demo=config.get('is_demo', True),
                initial_capital=config.get('initial_capital', 10000.0),
                max_position_value=config.get('max_position_value', 5000.0),
                stop_loss_pct=config.get('stop_loss_pct', 0.03),
                take_profit_pct=config.get('take_profit_pct', 0.06)
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
    
    async def _save_strategy_to_db(self, strategy_id: str, strategy_type: str, name: str, config: dict):
        """保存策略到数据库"""
        try:
            # TODO: 实现数据库保存
            # INSERT INTO strategy_instances ...
            pass
        except Exception as e:
            logger.error(f"保存策略到数据库失败: {e}")
    
    async def _update_strategy_status(self, strategy_id: str, status: str):
        """更新策略状态"""
        try:
            # TODO: 实现数据库更新
            # UPDATE strategy_instances SET status = ? WHERE id = ?
            pass
        except Exception as e:
            logger.error(f"更新策略状态失败: {e}")

