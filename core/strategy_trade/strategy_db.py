"""
策略交易数据库接口层
提供策略配置、信号、持仓、交易记录等数据的持久化功能
"""

import asyncio
import json
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime, date
import pandas as pd
from decimal import Decimal

from database.db import get_db_pool
from utils.logger import get_logger
from .base_strategy import TradingSignal, Position

logger = get_logger(__name__)

class StrategyDB:
    """策略交易数据库操作类"""
    
    def __init__(self, db_pool=None):
        self.db_pool = db_pool
    
    async def ensure_db_pool(self):
        """确保数据库连接池存在"""
        if self.db_pool is None:
            self.db_pool = await get_db_pool()
        return self.db_pool
    
    # ==================== 策略配置相关 ====================
    
    async def save_strategy_config(self, strategy_name: str, strategy_type: str, 
                                 config: Dict[str, Any], is_active: bool = False, 
                                 is_template: bool = False, created_by: str = 'system') -> bool:
        """保存策略配置"""
        try:
            pool = await self.ensure_db_pool()
            async with pool.acquire() as conn:
                await conn.execute("""
                    INSERT INTO strategy_configs 
                    (strategy_name, strategy_type, config_json, is_active, is_template, created_by)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    ON DUPLICATE KEY UPDATE
                    strategy_type = VALUES(strategy_type),
                    config_json = VALUES(config_json),
                    is_active = VALUES(is_active),
                    updated_at = CURRENT_TIMESTAMP
                """, strategy_name, strategy_type, json.dumps(config), is_active, is_template, created_by)
                
                logger.info(f"策略配置已保存: {strategy_name}")
                return True
        except Exception as e:
            logger.error(f"保存策略配置失败: {e}")
            return False
    
    async def load_strategy_config(self, strategy_name: str) -> Optional[Dict[str, Any]]:
        """加载策略配置"""
        try:
            pool = await self.ensure_db_pool()
            async with pool.acquire() as conn:
                result = await conn.fetchone("""
                    SELECT strategy_type, config_json, is_active, created_at, updated_at
                    FROM strategy_configs 
                    WHERE strategy_name = %s
                """, strategy_name)
                
                if result:
                    return {
                        'strategy_name': strategy_name,
                        'strategy_type': result['strategy_type'],
                        'config': json.loads(result['config_json']),
                        'is_active': result['is_active'],
                        'created_at': result['created_at'],
                        'updated_at': result['updated_at']
                    }
                return None
        except Exception as e:
            logger.error(f"加载策略配置失败: {e}")
            return None
    
    async def get_all_strategy_configs(self, include_templates: bool = True) -> List[Dict[str, Any]]:
        """获取所有策略配置"""
        try:
            pool = await self.ensure_db_pool()
            async with pool.acquire() as conn:
                where_clause = "" if include_templates else "WHERE is_template = FALSE"
                results = await conn.fetch(f"""
                    SELECT strategy_name, strategy_type, config_json, is_active, is_template, 
                           created_at, updated_at, created_by
                    FROM strategy_configs 
                    {where_clause}
                    ORDER BY created_at DESC
                """)
                
                configs = []
                for result in results:
                    configs.append({
                        'strategy_name': result['strategy_name'],
                        'strategy_type': result['strategy_type'],
                        'config': json.loads(result['config_json']),
                        'is_active': result['is_active'],
                        'is_template': result['is_template'],
                        'created_at': result['created_at'],
                        'updated_at': result['updated_at'],
                        'created_by': result['created_by']
                    })
                return configs
        except Exception as e:
            logger.error(f"获取策略配置失败: {e}")
            return []
    
    async def delete_strategy_config(self, strategy_name: str) -> bool:
        """删除策略配置"""
        try:
            pool = await self.ensure_db_pool()
            async with pool.acquire() as conn:
                await conn.execute("""
                    DELETE FROM strategy_configs WHERE strategy_name = %s
                """, strategy_name)
                logger.info(f"策略配置已删除: {strategy_name}")
                return True
        except Exception as e:
            logger.error(f"删除策略配置失败: {e}")
            return False
    
    # ==================== 策略实例相关 ====================
    
    async def create_strategy_instance(self, instance_name: str, strategy_name: str, 
                                     account_id: str, symbol: str, timeframe: str, 
                                     config: Dict[str, Any], created_by: str = 'system') -> int:
        """创建策略实例"""
        try:
            pool = await self.ensure_db_pool()
            async with pool.acquire() as conn:
                result = await conn.fetchone("""
                    INSERT INTO strategy_instances 
                    (instance_name, strategy_name, account_id, symbol, timeframe, config_json, created_by)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                """, instance_name, strategy_name, account_id, symbol, timeframe, 
                   json.dumps(config), created_by)
                
                instance_id = result.lastrowid
                logger.info(f"策略实例已创建: {instance_name}, ID: {instance_id}")
                return instance_id
        except Exception as e:
            logger.error(f"创建策略实例失败: {e}")
            return -1
    
    async def update_strategy_instance_status(self, instance_id: int, status: str, 
                                            started_at: datetime = None, stopped_at: datetime = None) -> bool:
        """更新策略实例状态"""
        try:
            pool = await self.ensure_db_pool()
            async with pool.acquire() as conn:
                update_fields = ["status = %s"]
                params = [status]
                
                if started_at:
                    update_fields.append("started_at = %s")
                    params.append(started_at)
                
                if stopped_at:
                    update_fields.append("stopped_at = %s")
                    params.append(stopped_at)
                
                params.append(instance_id)
                
                await conn.execute(f"""
                    UPDATE strategy_instances 
                    SET {', '.join(update_fields)}, updated_at = CURRENT_TIMESTAMP
                    WHERE id = %s
                """, *params)
                
                return True
        except Exception as e:
            logger.error(f"更新策略实例状态失败: {e}")
            return False
    
    async def get_strategy_instances(self, strategy_name: str = None, 
                                   status: str = None) -> List[Dict[str, Any]]:
        """获取策略实例列表"""
        try:
            pool = await self.ensure_db_pool()
            async with pool.acquire() as conn:
                where_conditions = []
                params = []
                
                if strategy_name:
                    where_conditions.append("strategy_name = %s")
                    params.append(strategy_name)
                
                if status:
                    where_conditions.append("status = %s")
                    params.append(status)
                
                where_clause = "WHERE " + " AND ".join(where_conditions) if where_conditions else ""
                
                results = await conn.fetch(f"""
                    SELECT * FROM v_strategy_instances_overview
                    {where_clause}
                    ORDER BY created_at DESC
                """, *params)
                
                return [dict(result) for result in results]
        except Exception as e:
            logger.error(f"获取策略实例失败: {e}")
            return []
    
    # ==================== 交易信号相关 ====================
    
    async def save_trading_signal(self, instance_id: int, signal: TradingSignal) -> bool:
        """保存交易信号"""
        try:
            pool = await self.ensure_db_pool()
            async with pool.acquire() as conn:
                await conn.execute("""
                    INSERT INTO strategy_signals 
                    (instance_id, signal_id, symbol, action, price, quantity, confidence, 
                     signal_strength, stop_loss, take_profit, metadata_json)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """, instance_id, f"{signal.symbol}_{signal.timestamp.isoformat()}", signal.symbol, 
                   signal.action, Decimal(str(signal.price)), Decimal(str(signal.quantity)), 
                   Decimal(str(signal.confidence)), Decimal(str(signal.signal_strength)), 
                   Decimal(str(signal.stop_loss)) if signal.stop_loss else None,
                   Decimal(str(signal.take_profit)) if signal.take_profit else None,
                   json.dumps(signal.metadata) if signal.metadata else None)
                
                return True
        except Exception as e:
            logger.error(f"保存交易信号失败: {e}")
            return False
    
    async def get_trading_signals(self, instance_id: int = None, symbol: str = None, 
                                action: str = None, limit: int = 50) -> List[Dict[str, Any]]:
        """获取交易信号历史"""
        try:
            pool = await self.ensure_db_pool()
            async with pool.acquire() as conn:
                where_conditions = []
                params = []
                
                if instance_id:
                    where_conditions.append("instance_id = %s")
                    params.append(instance_id)
                
                if symbol:
                    where_conditions.append("symbol = %s")
                    params.append(symbol)
                
                if action:
                    where_conditions.append("action = %s")
                    params.append(action)
                
                where_clause = "WHERE " + " AND ".join(where_conditions) if where_conditions else ""
                params.append(limit)
                
                results = await conn.fetch(f"""
                    SELECT * FROM strategy_signals
                    {where_clause}
                    ORDER BY created_at DESC
                    LIMIT %s
                """, *params)
                
                signals = []
                for result in results:
                    signals.append({
                        'id': result['id'],
                        'instance_id': result['instance_id'],
                        'signal_id': result['signal_id'],
                        'symbol': result['symbol'],
                        'action': result['action'],
                        'price': float(result['price']),
                        'quantity': float(result['quantity']),
                        'confidence': float(result['confidence']),
                        'signal_strength': float(result['signal_strength']) if result['signal_strength'] else 0,
                        'stop_loss': float(result['stop_loss']) if result['stop_loss'] else None,
                        'take_profit': float(result['take_profit']) if result['take_profit'] else None,
                        'metadata': json.loads(result['metadata_json']) if result['metadata_json'] else {},
                        'status': result['status'],
                        'created_at': result['created_at']
                    })
                
                return signals
        except Exception as e:
            logger.error(f"获取交易信号失败: {e}")
            return []
    
    # ==================== 持仓管理相关 ====================
    
    async def save_position(self, instance_id: int, position: Position) -> bool:
        """保存持仓信息"""
        try:
            pool = await self.ensure_db_pool()
            async with pool.acquire() as conn:
                await conn.execute("""
                    INSERT INTO strategy_positions 
                    (instance_id, position_id, symbol, side, quantity, entry_price, 
                     current_price, unrealized_pnl, stop_loss, take_profit, entry_time)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON DUPLICATE KEY UPDATE
                    current_price = VALUES(current_price),
                    unrealized_pnl = VALUES(unrealized_pnl),
                    updated_at = CURRENT_TIMESTAMP
                """, instance_id, f"{position.symbol}_{position.entry_time.isoformat()}", 
                   position.symbol, position.side, Decimal(str(position.quantity)), 
                   Decimal(str(position.entry_price)), Decimal(str(position.current_price)), 
                   Decimal(str(position.unrealized_pnl)),
                   Decimal(str(position.stop_loss)) if position.stop_loss else None,
                   Decimal(str(position.take_profit)) if position.take_profit else None,
                   position.entry_time)
                
                return True
        except Exception as e:
            logger.error(f"保存持仓信息失败: {e}")
            return False
    
    async def update_position(self, position_id: str, current_price: float, 
                            unrealized_pnl: float, status: str = 'OPEN') -> bool:
        """更新持仓信息"""
        try:
            pool = await self.ensure_db_pool()
            async with pool.acquire() as conn:
                await conn.execute("""
                    UPDATE strategy_positions 
                    SET current_price = %s, unrealized_pnl = %s, status = %s, updated_at = CURRENT_TIMESTAMP
                    WHERE position_id = %s
                """, Decimal(str(current_price)), Decimal(str(unrealized_pnl)), status, position_id)
                
                return True
        except Exception as e:
            logger.error(f"更新持仓信息失败: {e}")
            return False
    
    async def close_position(self, position_id: str, exit_price: float, 
                           realized_pnl: float, exit_time: datetime) -> bool:
        """关闭持仓"""
        try:
            pool = await self.ensure_db_pool()
            async with pool.acquire() as conn:
                await conn.execute("""
                    UPDATE strategy_positions 
                    SET exit_price = %s, realized_pnl = %s, exit_time = %s, 
                        status = 'CLOSED', updated_at = CURRENT_TIMESTAMP
                    WHERE position_id = %s
                """, Decimal(str(exit_price)), Decimal(str(realized_pnl)), exit_time, position_id)
                
                return True
        except Exception as e:
            logger.error(f"关闭持仓失败: {e}")
            return False
    
    async def get_positions(self, instance_id: int = None, symbol: str = None, 
                          status: str = 'OPEN') -> List[Dict[str, Any]]:
        """获取持仓列表"""
        try:
            pool = await self.ensure_db_pool()
            async with pool.acquire() as conn:
                where_conditions = []
                params = []
                
                if instance_id:
                    where_conditions.append("instance_id = %s")
                    params.append(instance_id)
                
                if symbol:
                    where_conditions.append("symbol = %s")
                    params.append(symbol)
                
                if status:
                    where_conditions.append("status = %s")
                    params.append(status)
                
                where_clause = "WHERE " + " AND ".join(where_conditions) if where_conditions else ""
                
                results = await conn.fetch(f"""
                    SELECT * FROM strategy_positions
                    {where_clause}
                    ORDER BY entry_time DESC
                """, *params)
                
                positions = []
                for result in results:
                    positions.append({
                        'id': result['id'],
                        'instance_id': result['instance_id'],
                        'position_id': result['position_id'],
                        'symbol': result['symbol'],
                        'side': result['side'],
                        'quantity': float(result['quantity']),
                        'entry_price': float(result['entry_price']),
                        'current_price': float(result['current_price']) if result['current_price'] else 0,
                        'unrealized_pnl': float(result['unrealized_pnl']),
                        'stop_loss': float(result['stop_loss']) if result['stop_loss'] else None,
                        'take_profit': float(result['take_profit']) if result['take_profit'] else None,
                        'entry_time': result['entry_time'],
                        'exit_time': result['exit_time'],
                        'exit_price': float(result['exit_price']) if result['exit_price'] else None,
                        'realized_pnl': float(result['realized_pnl']),
                        'status': result['status']
                    })
                
                return positions
        except Exception as e:
            logger.error(f"获取持仓列表失败: {e}")
            return []
    
    # ==================== 交易记录相关 ====================
    
    async def save_trade(self, instance_id: int, trade_data: Dict[str, Any]) -> bool:
        """保存交易记录"""
        try:
            pool = await self.ensure_db_pool()
            async with pool.acquire() as conn:
                await conn.execute("""
                    INSERT INTO strategy_trades 
                    (instance_id, trade_id, position_id, symbol, side, quantity, price, 
                     amount, commission, slippage, pnl, trade_type, reason, metadata_json, executed_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """, instance_id, trade_data['trade_id'], trade_data.get('position_id'),
                   trade_data['symbol'], trade_data['side'], Decimal(str(trade_data['quantity'])),
                   Decimal(str(trade_data['price'])), Decimal(str(trade_data['amount'])),
                   Decimal(str(trade_data.get('commission', 0))), Decimal(str(trade_data.get('slippage', 0))),
                   Decimal(str(trade_data.get('pnl', 0))), trade_data['trade_type'],
                   trade_data.get('reason'), json.dumps(trade_data.get('metadata', {})),
                   trade_data['executed_at'])
                
                return True
        except Exception as e:
            logger.error(f"保存交易记录失败: {e}")
            return False
    
    # ==================== 性能统计相关 ====================
    
    async def update_daily_performance(self, instance_id: int, date: date, 
                                     performance_data: Dict[str, Any]) -> bool:
        """更新日性能统计"""
        try:
            pool = await self.ensure_db_pool()
            async with pool.acquire() as conn:
                await conn.execute("""
                    INSERT INTO strategy_performance 
                    (instance_id, date, total_trades, winning_trades, losing_trades, win_rate,
                     total_pnl, realized_pnl, unrealized_pnl, max_drawdown, profit_factor,
                     sharpe_ratio, max_consecutive_losses, current_consecutive_losses,
                     average_win, average_loss, max_single_win, max_single_loss,
                     daily_return, cumulative_return)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON DUPLICATE KEY UPDATE
                    total_trades = VALUES(total_trades),
                    winning_trades = VALUES(winning_trades),
                    losing_trades = VALUES(losing_trades),
                    win_rate = VALUES(win_rate),
                    total_pnl = VALUES(total_pnl),
                    realized_pnl = VALUES(realized_pnl),
                    unrealized_pnl = VALUES(unrealized_pnl),
                    max_drawdown = VALUES(max_drawdown),
                    profit_factor = VALUES(profit_factor),
                    sharpe_ratio = VALUES(sharpe_ratio),
                    max_consecutive_losses = VALUES(max_consecutive_losses),
                    current_consecutive_losses = VALUES(current_consecutive_losses),
                    average_win = VALUES(average_win),
                    average_loss = VALUES(average_loss),
                    max_single_win = VALUES(max_single_win),
                    max_single_loss = VALUES(max_single_loss),
                    daily_return = VALUES(daily_return),
                    cumulative_return = VALUES(cumulative_return),
                    updated_at = CURRENT_TIMESTAMP
                """, instance_id, date, performance_data.get('total_trades', 0),
                   performance_data.get('winning_trades', 0), performance_data.get('losing_trades', 0),
                   Decimal(str(performance_data.get('win_rate', 0))), 
                   Decimal(str(performance_data.get('total_pnl', 0))),
                   Decimal(str(performance_data.get('realized_pnl', 0))),
                   Decimal(str(performance_data.get('unrealized_pnl', 0))),
                   Decimal(str(performance_data.get('max_drawdown', 0))),
                   Decimal(str(performance_data.get('profit_factor', 0))),
                   Decimal(str(performance_data.get('sharpe_ratio', 0))),
                   performance_data.get('max_consecutive_losses', 0),
                   performance_data.get('current_consecutive_losses', 0),
                   Decimal(str(performance_data.get('average_win', 0))),
                   Decimal(str(performance_data.get('average_loss', 0))),
                   Decimal(str(performance_data.get('max_single_win', 0))),
                   Decimal(str(performance_data.get('max_single_loss', 0))),
                   Decimal(str(performance_data.get('daily_return', 0))),
                   Decimal(str(performance_data.get('cumulative_return', 0))))
                
                return True
        except Exception as e:
            logger.error(f"更新性能统计失败: {e}")
            return False
    
    async def get_performance_history(self, instance_id: int, 
                                    days: int = 30) -> List[Dict[str, Any]]:
        """获取性能历史数据"""
        try:
            pool = await self.ensure_db_pool()
            async with pool.acquire() as conn:
                results = await conn.fetch("""
                    SELECT * FROM strategy_performance 
                    WHERE instance_id = %s 
                    AND date >= DATE_SUB(CURDATE(), INTERVAL %s DAY)
                    ORDER BY date DESC
                """, instance_id, days)
                
                return [dict(result) for result in results]
        except Exception as e:
            logger.error(f"获取性能历史失败: {e}")
            return [] 