#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
限价跟单数据库操作模块
提供限价跟单相关的数据库操作
"""

import logging
import json
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime
from database.db import MySQLPool
from core.limit_trade.limit_follow_models import (
    LimitFollowStrategy, LimitFollowOrder, LimitFollowExecution, 
    LimitFollowConfig, LimitFollowLog, LimitFollowStatus,
    CustomerLimitFollowSummary, TraderLimitFollowSummary
)

logger = logging.getLogger(__name__)

class LimitFollowDB:
    """限价跟单数据库操作类"""
    
    def __init__(self, db_pool: MySQLPool):
        self.db_pool = db_pool
    
    # ==================== 策略管理 ====================
    
    def create_strategy(self, strategy: LimitFollowStrategy) -> bool:
        """创建跟单策略"""
        try:
            sql = """INSERT INTO limit_follow_strategies 
                     (strategy_name, trader_unique_name, customer_uid, symbol, pos_side, 
                      follow_type, follow_value, min_follow_value, max_follow_value, 
                      max_orders_per_signal, max_net_leverage, proportional_position, 
                      auto_cancel_on_signal_close, enabled) 
                     VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"""
            
            params = (
                strategy.strategy_name, strategy.trader_unique_name, strategy.customer_uid,
                strategy.symbol, strategy.pos_side, strategy.follow_type, strategy.follow_value,
                strategy.min_follow_value, strategy.max_follow_value, strategy.max_orders_per_signal,
                strategy.max_net_leverage, strategy.proportional_position,
                strategy.auto_cancel_on_signal_close, strategy.enabled
            )
            
            result = self.db_pool.execute(sql, params)
            return result > 0
            
        except Exception as e:
            logger.error(f"创建策略失败: {e}")
            return False
    
    def get_strategy(self, strategy_id: int) -> Optional[LimitFollowStrategy]:
        """根据ID获取策略"""
        try:
            sql = "SELECT * FROM limit_follow_strategies WHERE id=%s"
            result = self.db_pool.query(sql, (strategy_id,))
            
            if result:
                return self._dict_to_strategy(result[0])
            return None
            
        except Exception as e:
            logger.error(f"获取策略失败: {e}")
            return None
    
    def get_strategies(self, filters: Optional[Dict[str, Any]] = None) -> List[LimitFollowStrategy]:
        """获取跟单策略列表"""
        try:
            sql = """SELECT lfs.*, lt.name as trader_name 
                     FROM limit_follow_strategies lfs
                     LEFT JOIN limit_follow_traders lt ON lfs.trader_unique_name = lt.unique_name
                     WHERE 1=1"""
            params = []
            
            if filters:
                if 'customer_uid' in filters:
                    sql += " AND lfs.customer_uid=%s"
                    params.append(filters['customer_uid'])
                
                if 'trader_unique_name' in filters:
                    sql += " AND lfs.trader_unique_name=%s"
                    params.append(filters['trader_unique_name'])
                
                if 'symbol' in filters:
                    sql += " AND lfs.symbol=%s"
                    params.append(filters['symbol'])
                
                if 'enabled' in filters:
                    sql += " AND lfs.enabled=%s"
                    params.append(filters['enabled'])
            
            sql += " ORDER BY lfs.created_at DESC"
            
            result = self.db_pool.query(sql, tuple(params) if params else None)
            return [self._dict_to_strategy(row) for row in result]
            
        except Exception as e:
            logger.error(f"获取策略列表失败: {e}")
            return []
    
    def update_strategy(self, strategy_id: int, updates: Dict[str, Any]) -> bool:
        """更新策略"""
        try:
            if not updates:
                return False
            
            set_clauses = []
            params = []
            
            for key, value in updates.items():
                if key in ['follow_type', 'follow_value', 'min_follow_value', 'max_follow_value',
                          'max_orders_per_signal', 'max_net_leverage', 'proportional_position',
                          'auto_cancel_on_signal_close', 'enabled']:
                    set_clauses.append(f"{key}=%s")
                    params.append(value)
            
            if not set_clauses:
                return False
            
            set_clauses.append("updated_at=CURRENT_TIMESTAMP")
            params.append(strategy_id)
            
            sql = f"UPDATE limit_follow_strategies SET {', '.join(set_clauses)} WHERE id=%s"
            result = self.db_pool.execute(sql, tuple(params))
            
            return result > 0
            
        except Exception as e:
            logger.error(f"更新策略失败: {e}")
            return False
    
    def delete_strategy(self, strategy_id: int) -> bool:
        """删除策略"""
        try:
            sql = "DELETE FROM limit_follow_strategies WHERE id=%s"
            result = self.db_pool.execute(sql, (strategy_id,))
            return result > 0
            
        except Exception as e:
            logger.error(f"删除策略失败: {e}")
            return False
    
    def get_active_strategies_for_signal(self, trader_unique_name: str, symbol: str, pos_side: str) -> List[LimitFollowStrategy]:
        """获取指定信号源的活跃策略"""
        try:
            sql = """SELECT * FROM limit_follow_strategies 
                     WHERE trader_unique_name=%s AND symbol=%s 
                     AND (pos_side='both' OR pos_side=%s) AND enabled=1"""
            
            result = self.db_pool.query(sql, (trader_unique_name, symbol, pos_side))
            return [self._dict_to_strategy(row) for row in result]
            
        except Exception as e:
            logger.error(f"获取活跃策略失败: {e}")
            return []
    
    # ==================== 订单管理 ====================
    
    def create_order(self, order: LimitFollowOrder) -> bool:
        """创建跟单订单"""
        try:
            sql = """INSERT INTO limit_follow_orders 
                     (order_uid, strategy_id, trader_unique_name, customer_uid, symbol, pos_side, 
                      follow_value, target_price, order_size, order_type, status) 
                     VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"""
            
            params = (
                order.order_uid, order.strategy_id, order.trader_unique_name, order.customer_uid,
                order.symbol, order.pos_side, order.follow_value, order.target_price,
                order.order_size, order.order_type, order.status
            )
            
            result = self.db_pool.execute(sql, params)
            return result > 0
            
        except Exception as e:
            logger.error(f"创建订单失败: {e}")
            return False
    
    def get_order(self, order_uid: str) -> Optional[LimitFollowOrder]:
        """根据UID获取订单"""
        try:
            sql = "SELECT * FROM limit_follow_orders WHERE order_uid=%s"
            result = self.db_pool.query(sql, (order_uid,))
            
            if result:
                return self._dict_to_order(result[0])
            return None
            
        except Exception as e:
            logger.error(f"获取订单失败: {e}")
            return None
    
    def get_orders(self, filters: Optional[Dict[str, Any]] = None) -> List[LimitFollowOrder]:
        """获取跟单订单列表"""
        try:
            sql = """SELECT lfo.*, c.name as customer_name, lt.name as trader_name
                     FROM limit_follow_orders lfo
                     LEFT JOIN customers c ON lfo.customer_uid = c.customer_uid
                     LEFT JOIN limit_follow_traders lt ON lfo.trader_unique_name = lt.unique_name
                     WHERE 1=1"""
            params = []
            
            if filters:
                if 'customer_uid' in filters:
                    sql += " AND lfo.customer_uid=%s"
                    params.append(filters['customer_uid'])
                
                if 'trader_unique_name' in filters:
                    sql += " AND lfo.trader_unique_name=%s"
                    params.append(filters['trader_unique_name'])
                
                if 'strategy_id' in filters:
                    sql += " AND lfo.strategy_id=%s"
                    params.append(filters['strategy_id'])
                
                if 'status' in filters:
                    sql += " AND lfo.status=%s"
                    params.append(filters['status'])
                
                if 'symbol' in filters:
                    sql += " AND lfo.symbol=%s"
                    params.append(filters['symbol'])
                
                if 'pos_side' in filters:
                    sql += " AND lfo.pos_side=%s"
                    params.append(filters['pos_side'])
            
            sql += " ORDER BY lfo.created_at DESC"
            
            result = self.db_pool.query(sql, tuple(params) if params else None)
            return [self._dict_to_order(row) for row in result]
            
        except Exception as e:
            logger.error(f"获取订单列表失败: {e}")
            return []
    
    def update_order_status(self, order_uid: str, status: str, exchange_order_id: Optional[str] = None,
                           filled_price: Optional[float] = None, filled_size: Optional[float] = None) -> bool:
        """更新订单状态"""
        try:
            sql = "UPDATE limit_follow_orders SET status=%s, updated_at=CURRENT_TIMESTAMP"
            params = [status]
            
            if exchange_order_id:
                sql += ", exchange_order_id=%s"
                params.append(exchange_order_id)
            
            if filled_price is not None:
                sql += ", filled_price=%s"
                params.append(filled_price)
            
            if filled_size is not None:
                sql += ", filled_size=%s"
                params.append(filled_size)
            
            sql += " WHERE order_uid=%s"
            params.append(order_uid)
            
            result = self.db_pool.execute(sql, tuple(params))
            return result > 0
            
        except Exception as e:
            logger.error(f"更新订单状态失败: {e}")
            return False
    
    def cancel_pending_orders(self, strategy_id: int) -> int:
        """撤销策略下的所有待处理订单"""
        try:
            sql = """UPDATE limit_follow_orders 
                     SET status='canceled', updated_at=CURRENT_TIMESTAMP 
                     WHERE strategy_id=%s AND status IN ('pending', 'live')"""
            
            result = self.db_pool.execute(sql, (strategy_id,))
            return result
            
        except Exception as e:
            logger.error(f"撤销待处理订单失败: {e}")
            return 0
    
    def get_pending_orders(self) -> List[LimitFollowOrder]:
        """获取所有待处理的订单"""
        try:
            sql = "SELECT * FROM limit_follow_orders WHERE status IN ('pending', 'live') ORDER BY created_at ASC"
            result = self.db_pool.query(sql, ())
            return [self._dict_to_order(row) for row in result]
            
        except Exception as e:
            logger.error(f"获取待处理订单失败: {e}")
            return []
    
    # ==================== 执行记录管理 ====================
    
    def create_execution(self, execution: LimitFollowExecution) -> bool:
        """创建执行记录"""
        try:
            sql = """INSERT INTO limit_follow_executions 
                     (execution_uid, strategy_id, order_uid, trader_unique_name, customer_uid,
                      symbol, pos_side, execution_type, execution_status, execution_data) 
                     VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"""
            
            params = (
                execution.execution_uid, execution.strategy_id, execution.order_uid,
                execution.trader_unique_name, execution.customer_uid, execution.symbol,
                execution.pos_side, execution.execution_type, execution.execution_status,
                json.dumps(execution.execution_data) if execution.execution_data else '{}'
            )
            
            result = self.db_pool.execute(sql, params)
            return result > 0
            
        except Exception as e:
            logger.error(f"创建执行记录失败: {e}")
            return False
    
    def update_execution_status(self, execution_uid: str, status: str, error_message: Optional[str] = None) -> bool:
        """更新执行状态"""
        try:
            sql = "UPDATE limit_follow_executions SET execution_status=%s, updated_at=CURRENT_TIMESTAMP"
            params = [status]
            
            if error_message:
                sql += ", error_message=%s"
                params.append(error_message)
            
            sql += " WHERE execution_uid=%s"
            params.append(execution_uid)
            
            result = self.db_pool.execute(sql, tuple(params))
            return result > 0
            
        except Exception as e:
            logger.error(f"更新执行状态失败: {e}")
            return False
    
    def get_executions(self, filters: Optional[Dict[str, Any]] = None) -> List[LimitFollowExecution]:
        """获取执行记录列表"""
        try:
            sql = "SELECT * FROM limit_follow_executions WHERE 1=1"
            params = []
            
            if filters:
                if 'strategy_id' in filters:
                    sql += " AND strategy_id=%s"
                    params.append(filters['strategy_id'])
                
                if 'order_uid' in filters:
                    sql += " AND order_uid=%s"
                    params.append(filters['order_uid'])
                
                if 'execution_status' in filters:
                    sql += " AND execution_status=%s"
                    params.append(filters['execution_status'])
            
            sql += " ORDER BY created_at DESC"
            
            result = self.db_pool.query(sql, tuple(params) if params else None)
            return [self._dict_to_execution(row) for row in result]
            
        except Exception as e:
            logger.error(f"获取执行记录失败: {e}")
            return []
    
    # ==================== 配置管理 ====================
    
    def get_config(self, config_key: str) -> Optional[LimitFollowConfig]:
        """获取配置"""
        try:
            sql = "SELECT * FROM limit_follow_configs WHERE config_key=%s AND enabled=1"
            result = self.db_pool.query(sql, (config_key,))
            
            if result:
                return self._dict_to_config(result[0])
            return None
            
        except Exception as e:
            logger.error(f"获取配置失败: {e}")
            return None
    
    def update_config(self, config: LimitFollowConfig) -> bool:
        """更新配置"""
        try:
            sql = """INSERT INTO limit_follow_configs 
                     (config_key, config_value, config_type, description, enabled) 
                     VALUES (%s, %s, %s, %s, %s)
                     ON DUPLICATE KEY UPDATE 
                     config_value = VALUES(config_value), 
                     config_type = VALUES(config_type),
                     description = VALUES(description),
                     enabled = VALUES(enabled),
                     updated_at = CURRENT_TIMESTAMP"""
            
            params = (
                config.config_key, config.config_value, config.config_type,
                config.description, config.enabled
            )
            
            result = self.db_pool.execute(sql, params)
            return result > 0
            
        except Exception as e:
            logger.error(f"更新配置失败: {e}")
            return False
    
    # ==================== 日志管理 ====================
    
    def add_log(self, log: LimitFollowLog) -> bool:
        """添加日志"""
        try:
            sql = """INSERT INTO limit_follow_logs 
                     (log_level, message, order_uid, strategy_id, customer_uid, trader_unique_name, extra_data) 
                     VALUES (%s, %s, %s, %s, %s, %s, %s)"""
            
            params = (
                log.log_level, log.message, log.order_uid, log.strategy_id,
                log.customer_uid, log.trader_unique_name,
                json.dumps(log.extra_data) if log.extra_data else None
            )
            
            result = self.db_pool.execute(sql, params)
            return result > 0
            
        except Exception as e:
            logger.error(f"添加日志失败: {e}")
            return False
    
    def get_logs(self, filters: Optional[Dict[str, Any]] = None, limit: int = 100) -> List[LimitFollowLog]:
        """获取日志列表"""
        try:
            sql = "SELECT * FROM limit_follow_logs WHERE 1=1"
            params = []
            
            if filters:
                if 'log_level' in filters:
                    sql += " AND log_level=%s"
                    params.append(filters['log_level'])
                
                if 'order_uid' in filters:
                    sql += " AND order_uid=%s"
                    params.append(filters['order_uid'])
                
                if 'strategy_id' in filters:
                    sql += " AND strategy_id=%s"
                    params.append(filters['strategy_id'])
            
            sql += " ORDER BY created_at DESC LIMIT %s"
            params.append(limit)
            
            result = self.db_pool.query(sql, tuple(params))
            return [self._dict_to_log(row) for row in result]
            
        except Exception as e:
            logger.error(f"获取日志失败: {e}")
            return []
    
    # ==================== 统计查询 ====================
    
    def get_status_summary(self) -> LimitFollowStatus:
        """获取状态汇总"""
        try:
            # 策略统计
            strategy_stats = self.db_pool.query(
                "SELECT COUNT(*) as total, SUM(CASE WHEN enabled=1 THEN 1 ELSE 0 END) as active FROM limit_follow_strategies",
                None
            )
            
            # 订单统计
            order_stats = self.db_pool.query(
                """SELECT 
                    COUNT(*) as total,
                    SUM(CASE WHEN status='pending' THEN 1 ELSE 0 END) as pending,
                    SUM(CASE WHEN status='live' THEN 1 ELSE 0 END) as live,
                    SUM(CASE WHEN status='filled' THEN 1 ELSE 0 END) as filled,
                    SUM(CASE WHEN status='canceled' THEN 1 ELSE 0 END) as canceled
                   FROM limit_follow_orders""",
                None
            )
            
            # 执行记录统计
            execution_stats = self.db_pool.query(
                """SELECT 
                    COUNT(*) as total,
                    SUM(CASE WHEN execution_status='completed' THEN 1 ELSE 0 END) as completed
                   FROM limit_follow_executions""",
                None
            )
            
            return LimitFollowStatus(
                total_strategies=strategy_stats[0]['total'] if strategy_stats else 0,
                active_strategies=strategy_stats[0]['active'] if strategy_stats else 0,
                total_orders=order_stats[0]['total'] if order_stats else 0,
                pending_orders=order_stats[0]['pending'] if order_stats else 0,
                live_orders=order_stats[0]['live'] if order_stats else 0,
                filled_orders=order_stats[0]['filled'] if order_stats else 0,
                canceled_orders=order_stats[0]['canceled'] if order_stats else 0,
                total_executions=execution_stats[0]['total'] if execution_stats else 0,
                completed_executions=execution_stats[0]['completed'] if execution_stats else 0,
                last_update=datetime.now()
            )
            
        except Exception as e:
            logger.error(f"获取状态汇总失败: {e}")
            return LimitFollowStatus()
    
    def get_customer_summary(self, customer_uid: str) -> Optional[CustomerLimitFollowSummary]:
        """获取客户汇总"""
        try:
            # 获取客户名称
            customer = self.db_pool.query(
                "SELECT name FROM customers WHERE customer_uid=%s", (customer_uid,)
            )
            
            if not customer:
                return None
            
            customer_name = customer[0]['name']
            
            # 获取策略统计
            strategy_stats = self.db_pool.query(
                """SELECT COUNT(*) as total, SUM(CASE WHEN enabled=1 THEN 1 ELSE 0 END) as active 
                   FROM limit_follow_strategies WHERE customer_uid=%s""",
                (customer_uid,)
            )
            
            # 获取订单统计
            order_stats = self.db_pool.query(
                """SELECT 
                    COUNT(*) as total,
                    SUM(CASE WHEN status='pending' THEN 1 ELSE 0 END) as pending,
                    SUM(CASE WHEN status='live' THEN 1 ELSE 0 END) as live,
                    SUM(CASE WHEN status='filled' THEN 1 ELSE 0 END) as filled,
                    SUM(CASE WHEN status='canceled' THEN 1 ELSE 0 END) as canceled
                   FROM limit_follow_orders WHERE customer_uid=%s""",
                (customer_uid,)
            )
            
            # 获取执行记录统计
            execution_stats = self.db_pool.query(
                """SELECT 
                    COUNT(*) as total,
                    SUM(CASE WHEN execution_status='completed' THEN 1 ELSE 0 END) as completed
                   FROM limit_follow_executions WHERE customer_uid=%s""",
                (customer_uid,)
            )
            
            # 获取最后活动时间
            activity_result = self.db_pool.query(
                """SELECT MAX(created_at) as last_activity FROM (
                    SELECT created_at FROM limit_follow_orders WHERE customer_uid=%s
                    UNION ALL
                    SELECT created_at FROM limit_follow_executions WHERE customer_uid=%s
                ) as activities""",
                (customer_uid, customer_uid)
            )
            
            return CustomerLimitFollowSummary(
                customer_uid=customer_uid,
                customer_name=customer_name,
                total_strategies=strategy_stats[0]['total'] if strategy_stats else 0,
                active_strategies=strategy_stats[0]['active'] if strategy_stats else 0,
                total_orders=order_stats[0]['total'] if order_stats else 0,
                pending_orders=order_stats[0]['pending'] if order_stats else 0,
                live_orders=order_stats[0]['live'] if order_stats else 0,
                filled_orders=order_stats[0]['filled'] if order_stats else 0,
                canceled_orders=order_stats[0]['canceled'] if order_stats else 0,
                total_executions=execution_stats[0]['total'] if execution_stats else 0,
                completed_executions=execution_stats[0]['completed'] if execution_stats else 0,
                last_activity=activity_result[0]['last_activity'] if activity_result else None
            )
            
        except Exception as e:
            logger.error(f"获取客户汇总失败: {e}")
            return None
    
    # ==================== 数据转换方法 ====================
    
    def _dict_to_strategy(self, data: Dict[str, Any]) -> LimitFollowStrategy:
        """字典转策略对象"""
        return LimitFollowStrategy(
            id=data.get('id'),
            strategy_name=data.get('strategy_name', ''),
            trader_unique_name=data.get('trader_unique_name', ''),
            customer_uid=data.get('customer_uid', ''),
            symbol=data.get('symbol', ''),
            pos_side=data.get('pos_side', 'both'),
            follow_type=data.get('follow_type', 'percentage'),
            follow_value=float(data.get('follow_value', 0)),
            min_follow_value=float(data.get('min_follow_value', 0.5)),
            max_follow_value=float(data.get('max_follow_value', 5.0)),
            max_orders_per_signal=int(data.get('max_orders_per_signal', 4)),
            max_net_leverage=float(data.get('max_net_leverage', 1.5)),
            proportional_position=bool(data.get('proportional_position', False)),
            auto_cancel_on_signal_close=bool(data.get('auto_cancel_on_signal_close', True)),
            enabled=bool(data.get('enabled', True)),
            created_at=data.get('created_at'),
            updated_at=data.get('updated_at')
        )
    
    def _dict_to_order(self, data: Dict[str, Any]) -> LimitFollowOrder:
        """字典转订单对象"""
        return LimitFollowOrder(
            id=data.get('id'),
            order_uid=data.get('order_uid', ''),
            strategy_id=data.get('strategy_id', 0),
            trader_unique_name=data.get('trader_unique_name', ''),
            customer_uid=data.get('customer_uid', ''),
            symbol=data.get('symbol', ''),
            pos_side=data.get('pos_side', 'long'),
            follow_value=float(data.get('follow_value', 0)),
            target_price=float(data.get('target_price', 0)),
            order_size=float(data.get('order_size', 0)),
            order_type=data.get('order_type', 'limit'),
            status=data.get('status', 'pending'),
            exchange_order_id=data.get('exchange_order_id'),
            filled_price=float(data.get('filled_price')) if data.get('filled_price') else None,
            filled_size=float(data.get('filled_size')) if data.get('filled_size') else None,
            created_at=data.get('created_at'),
            updated_at=data.get('updated_at')
        )
    
    def _dict_to_execution(self, data: Dict[str, Any]) -> LimitFollowExecution:
        """字典转执行记录对象"""
        execution_data = {}
        if data.get('execution_data'):
            try:
                execution_data = json.loads(data['execution_data'])
            except:
                execution_data = {}
        
        return LimitFollowExecution(
            id=data.get('id'),
            execution_uid=data.get('execution_uid', ''),
            strategy_id=data.get('strategy_id', 0),
            order_uid=data.get('order_uid', ''),
            trader_unique_name=data.get('trader_unique_name', ''),
            customer_uid=data.get('customer_uid', ''),
            symbol=data.get('symbol', ''),
            pos_side=data.get('pos_side', 'long'),
            execution_type=data.get('execution_type', 'order_placement'),
            execution_status=data.get('execution_status', 'pending'),
            execution_data=execution_data,
            error_message=data.get('error_message'),
            retry_count=int(data.get('retry_count', 0)),
            created_at=data.get('created_at'),
            updated_at=data.get('updated_at')
        )
    
    def _dict_to_config(self, data: Dict[str, Any]) -> LimitFollowConfig:
        """字典转配置对象"""
        return LimitFollowConfig(
            id=data.get('id'),
            config_key=data.get('config_key', ''),
            config_value=data.get('config_value', ''),
            config_type=data.get('config_type', 'string'),
            description=data.get('description'),
            enabled=bool(data.get('enabled', True)),
            created_at=data.get('created_at'),
            updated_at=data.get('updated_at')
        )
    
    def _dict_to_log(self, data: Dict[str, Any]) -> LimitFollowLog:
        """字典转日志对象"""
        extra_data = {}
        if data.get('extra_data'):
            try:
                extra_data = json.loads(data['extra_data'])
            except:
                extra_data = {}
        
        return LimitFollowLog(
            id=data.get('id'),
            log_level=data.get('log_level', 'INFO'),
            message=data.get('message', ''),
            order_uid=data.get('order_uid'),
            strategy_id=data.get('strategy_id'),
            customer_uid=data.get('customer_uid'),
            trader_unique_name=data.get('trader_unique_name'),
            extra_data=extra_data,
            created_at=data.get('created_at')
        )
    
    # ==================== 客户账户信息查询 ====================
    
    def get_customer_config(self, customer_uid: str) -> Optional[Dict]:
        """获取客户配置"""
        try:
            sql = "SELECT * FROM limit_follow_configs WHERE customer_uid=%s AND enabled=1"
            result = self.db_pool.query(sql, (customer_uid,))
            
            if result:
                return result[0]
            return None
            
        except Exception as e:
            logger.error(f"获取客户配置失败: {e}")
            return None
    
    def get_customer_positions(self, customer_uid: str, symbol: str) -> List[Dict]:
        """获取客户在指定交易对上的持仓"""
        try:
            # 查询客户持仓表
            sql = """SELECT * FROM customer_positions 
                     WHERE customer_uid=%s AND symbol=%s AND status='open'"""
            result = self.db_pool.query(sql, (customer_uid, symbol))
            
            if not result:
                return []
            
            # 转换为标准格式
            positions = []
            for row in result:
                position = {
                    'pos': row.get('pos', 0),
                    'pos_side': row.get('pos_side', 'long'),
                    'avg_px': row.get('avg_px', 0),
                    'upl': row.get('upl', 0),
                    'margin': row.get('margin', 0),
                    'status': row.get('status', 'open')
                }
                positions.append(position)
            
            return positions
            
        except Exception as e:
            logger.error(f"获取客户持仓失败: {e}")
            return []
    
    def get_customer_account_balance(self, customer_uid: str) -> Optional[Dict]:
        """获取客户账户余额"""
        try:
            # 查询客户资产表
            sql = """SELECT * FROM customer_assets 
                     WHERE customer_uid=%s AND currency='USDT'"""
            result = self.db_pool.query(sql, (customer_uid,))
            
            if not result:
                return None
            
            # 计算总余额
            total_balance = 0.0
            available_balance = 0.0
            
            for row in result:
                total_balance += float(row.get('total_balance', 0))
                available_balance += float(row.get('available_balance', 0))
            
            return {
                'total_balance': total_balance,
                'available_balance': available_balance,
                'currency': 'USDT'
            }
            
        except Exception as e:
            logger.error(f"获取客户账户余额失败: {e}")
            return None 