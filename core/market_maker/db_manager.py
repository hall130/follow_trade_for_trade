"""
做市账号数据库管理模块
支持用户级别的账号管理
"""
import json
from typing import Dict, List, Any, Optional
from datetime import datetime, date
from database.db import get_db_pool
from utils.logger import logger


class MarketMakerDBManager:
    """做市账号数据库管理器"""
    
    def __init__(self):
        """初始化数据库管理器"""
        self.db_pool = get_db_pool()
    
    def get_user_accounts(self, user_id: int, include_disabled: bool = False) -> List[Dict[str, Any]]:
        """
        获取用户的所有做市账号
        
        Args:
            user_id: 用户ID
            include_disabled: 是否包含禁用的账号
            
        Returns:
            账号列表
        """
        try:
            if include_disabled:
                sql = """
                    SELECT * FROM market_maker_accounts 
                    WHERE user_id = %s 
                    ORDER BY created_at DESC
                """
                params = (user_id,)
            else:
                sql = """
                    SELECT * FROM market_maker_accounts 
                    WHERE user_id = %s AND enabled = 1 
                    ORDER BY created_at DESC
                """
                params = (user_id,)
            
            results = self.db_pool.query(sql, params)
            
            accounts = []
            for row in results:
                account = {
                    'id': row.get('id'),
                    'name': row.get('account_name'),
                    'user_id': row.get('user_id'),
                    'exchange': row.get('exchange', 'backpack'),
                    'market_type': row.get('market_type', 'spot'),
                    'api_key': row.get('api_key'),
                    'api_secret': row.get('api_secret'),
                    'base_url': row.get('base_url', 'https://api.backpack.work'),
                    'ws_proxy': row.get('ws_proxy'),
                    'symbols': json.loads(row.get('symbols', '[]')) if isinstance(row.get('symbols'), str) else row.get('symbols', []),
                    'params': json.loads(row.get('params', '{}')) if isinstance(row.get('params'), str) else row.get('params', {}),
                    'enabled': bool(row.get('enabled', 1)),
                    'created_at': row.get('created_at'),
                    'updated_at': row.get('updated_at')
                }
                accounts.append(account)
            
            return accounts
        except Exception as e:
            logger.error(f"获取用户做市账号失败: {e}")
            return []
    
    def get_account(self, account_name: str, user_id: Optional[int] = None) -> Optional[Dict[str, Any]]:
        """
        获取指定账号
        
        Args:
            account_name: 账号名称
            user_id: 用户ID（如果提供，会验证所有权）
            
        Returns:
            账号配置，如果不存在或无权访问返回None
        """
        try:
            if user_id:
                sql = """
                    SELECT * FROM market_maker_accounts 
                    WHERE account_name = %s AND user_id = %s
                """
                params = (account_name, user_id)
            else:
                sql = """
                    SELECT * FROM market_maker_accounts 
                    WHERE account_name = %s
                """
                params = (account_name,)
            
            results = self.db_pool.query(sql, params)
            if not results:
                return None
            
            row = results[0]
            return {
                'id': row.get('id'),
                'name': row.get('account_name'),
                'user_id': row.get('user_id'),
                'exchange': row.get('exchange', 'backpack'),
                'market_type': row.get('market_type', 'spot'),
                'api_key': row.get('api_key'),
                'api_secret': row.get('api_secret'),
                'base_url': row.get('base_url', 'https://api.backpack.work'),
                'ws_proxy': row.get('ws_proxy'),
                'symbols': json.loads(row.get('symbols', '[]')) if isinstance(row.get('symbols'), str) else row.get('symbols', []),
                'params': json.loads(row.get('params', '{}')) if isinstance(row.get('params'), str) else row.get('params', {}),
                'enabled': bool(row.get('enabled', 1)),
                'created_at': row.get('created_at'),
                'updated_at': row.get('updated_at')
            }
        except Exception as e:
            logger.error(f"获取做市账号失败: {e}")
            return None
    
    def add_account(self, account: Dict[str, Any], user_id: int) -> bool:
        """
        添加做市账号
        
        Args:
            account: 账号配置
            user_id: 用户ID
            
        Returns:
            是否添加成功
        """
        try:
            # 检查账号名称是否已存在
            existing = self.get_account(account.get('name'))
            if existing:
                logger.warning(f"账号 {account.get('name')} 已存在")
                return False
            
            sql = """
                INSERT INTO market_maker_accounts 
                (account_name, user_id, exchange, market_type, api_key, api_secret, 
                 base_url, ws_proxy, symbols, params, enabled, created_by_user_id)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """
            
            params = (
                account.get('name'),
                user_id,
                account.get('exchange', 'backpack'),
                account.get('market_type', 'spot'),
                account.get('api_key', ''),
                account.get('api_secret', ''),
                account.get('base_url', 'https://api.backpack.work'),
                account.get('ws_proxy'),
                json.dumps(account.get('symbols', [])),
                json.dumps(account.get('params', {})),
                1,  # enabled
                user_id  # created_by_user_id
            )
            
            self.db_pool.execute(sql, params)
            logger.info(f"已添加做市账号: {account.get('name')} (用户ID: {user_id})")
            return True
        except Exception as e:
            logger.error(f"添加做市账号失败: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def update_account(self, account_name: str, account: Dict[str, Any], user_id: int) -> bool:
        """
        更新做市账号
        
        Args:
            account_name: 账号名称
            account: 账号配置
            user_id: 用户ID（用于验证所有权）
            
        Returns:
            是否更新成功
        """
        try:
            # 验证所有权
            existing = self.get_account(account_name, user_id)
            if not existing:
                logger.warning(f"账号 {account_name} 不存在或无权访问")
                return False
            
            sql = """
                UPDATE market_maker_accounts 
                SET exchange = %s, market_type = %s, api_key = %s, api_secret = %s,
                    base_url = %s, ws_proxy = %s, symbols = %s, params = %s,
                    updated_at = NOW()
                WHERE account_name = %s AND user_id = %s
            """
            
            params = (
                account.get('exchange', 'backpack'),
                account.get('market_type', 'spot'),
                account.get('api_key', ''),
                account.get('api_secret', ''),
                account.get('base_url', 'https://api.backpack.work'),
                account.get('ws_proxy'),
                json.dumps(account.get('symbols', [])),
                json.dumps(account.get('params', {})),
                account_name,
                user_id
            )
            
            self.db_pool.execute(sql, params)
            logger.info(f"已更新做市账号: {account_name}")
            return True
        except Exception as e:
            logger.error(f"更新做市账号失败: {e}")
            return False
    
    def delete_account(self, account_name: str, user_id: int) -> bool:
        """
        删除做市账号
        
        Args:
            account_name: 账号名称
            user_id: 用户ID（用于验证所有权）
            
        Returns:
            是否删除成功
        """
        try:
            # 验证所有权
            existing = self.get_account(account_name, user_id)
            if not existing:
                logger.warning(f"账号 {account_name} 不存在或无权访问")
                return False
            
            sql = """
                DELETE FROM market_maker_accounts 
                WHERE account_name = %s AND user_id = %s
            """
            
            self.db_pool.execute(sql, (account_name, user_id))
            logger.info(f"已删除做市账号: {account_name}")
            return True
        except Exception as e:
            logger.error(f"删除做市账号失败: {e}")
            return False
    
    def get_account_status(self, account_name: str, symbol: str) -> Optional[Dict[str, Any]]:
        """
        获取账号运行状态
        
        Args:
            account_name: 账号名称
            symbol: 交易对
            
        Returns:
            状态信息
        """
        try:
            sql = """
                SELECT * FROM market_maker_status 
                WHERE account_name = %s AND symbol = %s
            """
            results = self.db_pool.query(sql, (account_name, symbol))
            
            if results:
                row = results[0]
                return {
                    'status': row.get('status', 'stopped'),
                    'process_id': row.get('process_id'),
                    'start_time': row.get('start_time'),
                    'stop_time': row.get('stop_time'),
                    'error_message': row.get('error_message')
                }
            return None
        except Exception as e:
            logger.error(f"获取账号状态失败: {e}")
            return None
    
    def update_account_status(self, account_name: str, symbol: str, status: str, 
                             process_id: Optional[int] = None, error_message: Optional[str] = None) -> bool:
        """
        更新账号运行状态
        
        Args:
            account_name: 账号名称
            symbol: 交易对
            status: 状态（running/stopped/error）
            process_id: 进程ID
            error_message: 错误信息
            
        Returns:
            是否更新成功
        """
        try:
            sql = """
                INSERT INTO market_maker_status 
                (account_name, symbol, status, process_id, start_time, error_message)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (account_name, symbol) DO UPDATE SET
                    status = EXCLUDED.status,
                    process_id = EXCLUDED.process_id,
                    start_time = CASE WHEN EXCLUDED.status = 'running' AND start_time IS NULL THEN NOW() ELSE start_time END,
                    stop_time = CASE WHEN EXCLUDED.status = 'stopped' THEN NOW() ELSE stop_time END,
                    error_message = EXCLUDED.error_message,
                    last_update = NOW()
            """
            
            start_time = datetime.now() if status == 'running' else None
            params = (account_name, symbol, status, process_id, start_time, error_message)
            
            self.db_pool.execute(sql, params)
            return True
        except Exception as e:
            logger.error(f"更新账号状态失败: {e}")
            return False
    
    def get_account_stats(self, account_name: str, symbol: str, date: Optional[date] = None) -> Optional[Dict[str, Any]]:
        """
        获取账号统计数据
        
        Args:
            account_name: 账号名称
            symbol: 交易对
            date: 统计日期（默认为今天）
            
        Returns:
            统计数据
        """
        try:
            if not date:
                date = datetime.now().date()
            
            sql = """
                SELECT * FROM market_maker_stats 
                WHERE account_name = %s AND symbol = %s AND date = %s
            """
            results = self.db_pool.query(sql, (account_name, symbol, date))
            
            if results:
                row = results[0]
                return {
                    'buy_volume': float(row.get('buy_volume', 0)),
                    'sell_volume': float(row.get('sell_volume', 0)),
                    'maker_buy_volume': float(row.get('maker_buy_volume', 0)),
                    'maker_sell_volume': float(row.get('maker_sell_volume', 0)),
                    'taker_buy_volume': float(row.get('taker_buy_volume', 0)),
                    'taker_sell_volume': float(row.get('taker_sell_volume', 0)),
                    'realized_profit': float(row.get('realized_profit', 0)),
                    'total_fees': float(row.get('total_fees', 0)),
                    'net_profit': float(row.get('net_profit', 0)),
                    'trade_count': int(row.get('trade_count', 0))
                }
            return None
        except Exception as e:
            logger.error(f"获取账号统计失败: {e}")
            return None

