# 可选导入DBUtils
import pymysql
import uuid
from utils.logger import logger

try:
    from dbutils.pooled_db import PooledDB
    DBUTILS_AVAILABLE = True
except ImportError:
    DBUTILS_AVAILABLE = False
    PooledDB = None
    logger.warning("DBUtils不可用，将使用简化的数据库连接")


class MySQLPool:
    def __init__(self, host, user, password, db, port=3306, mincached=2, maxcached=10):
        self.host = host
        self.user = user
        self.password = password
        self.db = db
        self.port = port
        
        if DBUTILS_AVAILABLE and PooledDB:
            # 使用连接池，优化配置
            self.pool = PooledDB(
                creator=pymysql,
                host=host, user=user, password=password, db=db, port=port,
                charset='utf8mb4', 
                autocommit=True,  # 查询操作自动提交
                cursorclass=pymysql.cursors.DictCursor,
                mincached=mincached, 
                maxcached=maxcached,
                maxconnections=maxcached * 3,  # 最大连接数（提高以支持更多并发，100用户建议150+）
                blocking=True,  # 阻塞等待连接
                ping=7  # 每7次查询ping一次数据库
            )
        else:
            # Fallback: 使用简单的连接
            self.pool = None
            logger.warning("使用简化的数据库连接（无连接池）")

    def get_conn(self):
        if self.pool:
            return self.pool.connection()
        else:
            # Fallback: 直接创建连接
            return pymysql.connect(
                host=self.host,
                user=self.user,
                password=self.password,
                db=self.db,
                port=self.port,
                charset='utf8mb4',
                cursorclass=pymysql.cursors.DictCursor,
                autocommit=True
            )

    def query(self, sql, args=None):
        conn = None
        try:
            conn = self.get_conn()
            if conn is None:
                raise Exception("无法获取数据库连接")
            
            with conn.cursor() as cursor:
                cursor.execute(sql, args or ())
                result = cursor.fetchall()
                conn.commit()  # 提交查询事务
                return result
        except Exception as e:
            if conn:
                try:
                    conn.rollback()  # 回滚查询事务
                except:
                    pass
            logger.error(f"查询失败: {e}")
            raise e
        finally:
            if conn:
                try:
                    conn.close()
                except:
                    pass
    
    def query_one(self, sql, args=None):
        """查询单条记录，返回第一条结果或None"""
        result = self.query(sql, args)
        if result and len(result) > 0:
            return result[0]
        return None

    def execute(self, sql, args=None, max_retries=3):
        """执行SQL语句，带重试机制和连接异常处理"""
        for attempt in range(max_retries):
            conn = None
            try:
                conn = self.get_conn()
                if conn is None:
                    raise Exception("无法获取数据库连接")
                
                with conn.cursor() as cursor:
                    cursor.execute(sql, args or ())
                    # 对于UPDATE/DELETE操作，返回影响的行数；对于INSERT操作，返回lastrowid
                    if sql.strip().upper().startswith(('UPDATE', 'DELETE')):
                        result = cursor.rowcount
                    else:
                        result = cursor.lastrowid
                    conn.commit()  # 提交执行事务
                    return result
            except (pymysql.OperationalError, pymysql.InterfaceError, pymysql.DatabaseError) as e:
                if conn:
                    try:
                        conn.rollback()  # 回滚执行事务
                    except:
                        pass
                logger.warning(f"数据库连接异常 (尝试 {attempt + 1}/{max_retries}): {e}")
                if attempt == max_retries - 1:
                    logger.error(f"数据库操作最终失败: {sql[:100]}...")
                    raise e
                # 等待后重试
                import time
                time.sleep(0.1 * (attempt + 1))  # 递增等待时间
            except Exception as e:
                if conn:
                    try:
                        conn.rollback()  # 回滚执行事务
                    except:
                        pass
                logger.error(f"数据库操作异常: {e}")
                if attempt == max_retries - 1:
                    raise e
                import time
                time.sleep(0.1 * (attempt + 1))
            finally:
                # 确保连接被正确关闭
                if conn:
                    try:
                        conn.close()
                    except:
                        pass

    def execute_with_rowcount(self, sql, args=None):
        with self.get_conn().cursor() as cursor:
            cursor.execute(sql, args or ())
            return cursor.rowcount

    def executemany(self, sql, args_list):
        with self.get_conn().cursor() as cursor:
            cursor.executemany(sql, args_list)
            return cursor.rowcount

    def execute_transaction(self, operations, max_retries=3):
        """执行事务操作，带重试机制"""
        for attempt in range(max_retries):
            conn = None
            try:
                conn = self.get_conn()
                conn.begin()  # 开始事务
                
                with conn.cursor() as cursor:
                    results = []
                    for sql, args in operations:
                        cursor.execute(sql, args or ())
                        if sql.strip().upper().startswith(('UPDATE', 'DELETE')):
                            results.append(cursor.rowcount)
                        else:
                            results.append(cursor.lastrowid)
                
                conn.commit()  # 提交事务
                logger.info(f"✅ 事务执行成功 (尝试 {attempt + 1})")
                return results
                
            except Exception as e:
                if conn:
                    try:
                        conn.rollback()  # 回滚事务
                        logger.warning(f"⚠️ 事务回滚 (尝试 {attempt + 1}/{max_retries}): {e}")
                    except:
                        pass
                
                # 对于某些错误，不应该重试（如表不存在、语法错误等）
                if self._should_not_retry(e):
                    logger.error(f"❌ 事务执行失败，不重试: {e}")
                    raise e
                
                if attempt == max_retries - 1:
                    logger.error(f"❌ 事务执行最终失败: {e}")
                    raise e
                
                # 等待后重试
                import time
                time.sleep(0.1 * (attempt + 1))
                
            finally:
                if conn:
                    try:
                        conn.close()
                    except:
                        pass
    
    def _should_not_retry(self, error):
        """判断是否不应该重试的错误"""
        error_str = str(error).lower()
        # 表不存在、语法错误、权限错误等不应该重试
        no_retry_errors = [
            "table '",
            "doesn't exist",
            "syntax error",
            "access denied",
            "unknown column",
            "duplicate key",
            "foreign key constraint"
        ]
        
        for no_retry_error in no_retry_errors:
            if no_retry_error in error_str:
                return True
        
        return False

# 下面是所有CURD操作的函数，直接调用
# 假设全局db_pool = MySQLPool(...)

def get_enabled_signal_accounts(db_pool, is_demo):
    """获取所有启用的信号源账户（按环境隔离）"""
    rows = db_pool.query("SELECT * FROM signal_sources WHERE enabled=1 AND is_demo=%s", (is_demo,))
    return rows


def upsert_signal_account_asset(db_pool, signal_source_uid, asset):
    asset_uid = uuid.uuid4().hex
    return db_pool.execute(
        "INSERT INTO signal_account_assets (asset_uid, signal_source_uid, asset) VALUES (%s, %s, %s) "
        "ON DUPLICATE KEY UPDATE asset_uid=VALUES(asset_uid), asset=VALUES(asset), snapshot_time=NOW()",
        (asset_uid, signal_source_uid, asset)
    )

def insert_signal_account_trade(db_pool, signal_source_uid, symbol, direction, pos_side, volume, order_id, trade_type, trade_uid=None, open_px=None, is_demo=None, volume_contract=None):
    """
    插入或更新信号源账户交易（如trade_uid已存在则update），支持volume_contract字段
    """
    import uuid
    from utils.logger import logger
    if not trade_uid:
        trade_uid = uuid.uuid4().hex
    try:
        # 先查是否已存在
        rows = db_pool.query("SELECT 1 FROM signal_account_trades WHERE trade_uid=%s", (trade_uid,))
        if rows:
            # 已存在则update
            logger.info(f"信号源成交单已存在，执行update: {trade_uid}")
            db_pool.execute(
                "UPDATE signal_account_trades SET volume=%s, order_id=%s, open_px=%s, is_demo=%s, volume_contract=%s WHERE trade_uid=%s",
                (volume, order_id, open_px, is_demo, volume_contract, trade_uid)
            )
        else:
            logger.info(f"插入信号源成交单: {trade_uid}, {signal_source_uid}, {symbol}, {direction}, {pos_side}, {volume}, {order_id}, {trade_type}, open_px={open_px}, is_demo={is_demo}, volume_contract={volume_contract}")
            db_pool.execute(
                "INSERT INTO signal_account_trades (trade_uid, signal_source_uid, symbol, direction, pos_side, volume, volume_contract, order_id, trade_type, open_px, status, is_demo) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'open', %s)",
                (trade_uid, signal_source_uid, symbol, direction, pos_side, volume, volume_contract, order_id, trade_type, open_px, is_demo)
            )
    except Exception as e:
        logger.error(f"插入/更新信号源成交单失败: {e}")
    return trade_uid

def get_strategies_by_signal_account(db_pool, signal_source_uid):
    """获取信号源关联的所有策略（多对多）"""
    return db_pool.query(
        "SELECT s.* FROM strategy_signal_source sss JOIN strategies s ON sss.strategy_uid = s.strategy_uid WHERE sss.source_uid=%s AND sss.enabled=1 AND s.enabled=1",
        (signal_source_uid,)
    )

def get_rule_by_signal_and_strategy(db_pool, signal_source_uid, strategy_uid):
    """获取信号源和策略唯一对应的规则（假设一对一）"""
    # 先查 rules where strategy_uid=... and enabled=1，再可选校验信号源唯一性
    rows = db_pool.query(
        "SELECT * FROM rules WHERE strategy_uid=%s AND enabled=1",
        (strategy_uid,)
    )
    return rows[0] if rows else None

def get_rules_by_strategy(db_pool, strategy_uid):
    """获取策略下所有启用规则"""
    return db_pool.query("SELECT * FROM rules WHERE strategy_uid=%s AND enabled=1", (strategy_uid,))

# 修正：增加JOIN和条件，保证客户、策略、跟单关系都启用
# 并且增加is_demo条件，防止混用实盘和模拟盘

def get_customers_by_strategy_and_rule(db_pool, strategy_uid, rule_uid, is_demo):
    """获取跟随指定策略和规则的所有客户"""
    return db_pool.query(
        """
        SELECT c.*
        FROM customers c
        JOIN customer_strategy cs ON c.customer_uid = cs.customer_uid
        WHERE cs.strategy_uid = %s AND cs.enabled=1 AND c.enabled=1 AND c.is_demo=%s
        """,
        (strategy_uid, is_demo)
    )

def insert_customer_trade(db_pool, customer_uid, strategy_uid, rule_uid, symbol, volume, direction, pos_side, trade_uid=None, is_demo=None, volume_contract=None, open_px=None, execution_type='auto', execution_reason=None, parent_operation_id=None):
    """插入或更新客户跟单交易，返回 trade_uid 字符串"""
    import uuid
    from utils.logger import logger
    if not trade_uid:
        trade_uid = uuid.uuid4().hex
    try:
        # 先查是否已存在
        rows = db_pool.query("SELECT 1 FROM customer_trades WHERE trade_uid=%s", (trade_uid,))
        if rows:
            # 已存在则update
            logger.info(f"客户跟单已存在，执行update: {trade_uid}")
            db_pool.execute(
                "UPDATE customer_trades SET volume=%s, direction=%s, pos_side=%s, is_demo=%s, volume_contract=%s, open_px=%s, execution_type=%s, execution_reason=%s, parent_operation_id=%s WHERE trade_uid=%s",
                (volume, direction, pos_side, is_demo, volume_contract, open_px, execution_type, execution_reason, parent_operation_id, trade_uid)
            )
        else:
            logger.info(f"插入客户跟单: {customer_uid}, {strategy_uid}, {rule_uid}, {symbol}, {volume}, {direction}, {pos_side}, trade_uid={trade_uid}, is_demo={is_demo}, volume_contract={volume_contract}, open_px={open_px}, execution_type={execution_type}, execution_reason={execution_reason}")
            db_pool.execute(
                "INSERT INTO customer_trades (trade_uid, customer_uid, strategy_uid, rule_uid, symbol, volume, volume_contract, direction, pos_side, open_px, status, is_demo, execution_type, execution_reason, parent_operation_id) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'open', %s, %s, %s, %s)",
                (trade_uid, customer_uid, strategy_uid, rule_uid, symbol, volume, volume_contract, direction, pos_side, open_px, is_demo, execution_type, execution_reason, parent_operation_id)
            )
    except Exception as e:
        logger.error(f"插入/更新客户跟单失败: {e}")
    return trade_uid

def update_customer_trade_order_id(db_pool, trade_uid, order_id):
    """更新客户跟单交易的订单ID"""
    return db_pool.execute("UPDATE customer_trades SET order_id=%s WHERE trade_uid=%s", (order_id, trade_uid))

def update_customer_trade_open_px(db_pool, trade_uid, open_px):
    """更新客户跟单交易的开仓均价"""
    return db_pool.execute("UPDATE customer_trades SET open_px=%s WHERE trade_uid=%s", (open_px, trade_uid))

def update_customer_trade_close_order_id(db_pool, trade_uid, close_order_id):
    """更新客户跟单交易的平仓订单ID"""
    return db_pool.execute("UPDATE customer_trades SET close_order_id=%s WHERE trade_uid=%s", (close_order_id, trade_uid))

def update_customer_trade_close_volume_contract(db_pool, trade_uid, close_sz):
    """
    累加更新客户trade的close_volume_contract字段
    """
    db_pool.execute(
        "UPDATE customer_trades SET close_volume_contract=IFNULL(close_volume_contract,0)+%s WHERE trade_uid=%s",
        (close_sz, trade_uid)
    )

def update_signal_account_trade_close_volume_contract(db_pool, trade_uid, close_sz):
    """
    累加更新信号源trade的close_volume_contract字段
    """
    db_pool.execute(
        "UPDATE signal_account_trades SET close_volume_contract=IFNULL(close_volume_contract,0)+%s WHERE trade_uid=%s",
        (close_sz, trade_uid)
    )

def log_trade_failure(db_pool, customer_trade_uid, reason):
    """记录交易失败"""
    failure_uid = uuid.uuid4().hex
    return db_pool.execute(
        "INSERT INTO trade_failures (failure_uid, customer_trade_uid, reason) VALUES (%s, %s, %s)",
        (failure_uid, customer_trade_uid, reason)
    )

def get_open_trades_by_customer(db_pool, customer_uid, is_demo):
    """获取客户所有未平仓的跟单交易"""
    return db_pool.query("SELECT * FROM customer_trades WHERE customer_uid=%s AND status='open' AND is_demo=%s", (customer_uid, is_demo))

def close_customer_trade(db_pool, trade_uid, profit, close_px=None):
    """平仓客户跟单交易，更新profit和close_px"""
    if close_px is not None:
        db_pool.execute("UPDATE customer_trades SET profit=%s, close_px=%s, status='closed', closed_at=NOW() WHERE trade_uid=%s", (profit, close_px, trade_uid))
    else:
        db_pool.execute("UPDATE customer_trades SET profit=%s, status='closed', closed_at=NOW() WHERE trade_uid=%s", (profit, trade_uid))

def get_open_trades_by_symbol_pos(db_pool, symbol, pos_side, is_demo):
    """获取指定品种和持仓方向的所有未平仓客户跟单交易"""
    return db_pool.query("SELECT * FROM customer_trades WHERE symbol=%s AND pos_side=%s AND status='open' AND is_demo=%s", (symbol, pos_side, is_demo))

def close_trader_trade(db_pool, trade_uid, close_order_id, close_px, profit):
    """平仓带单员成交记录，更新平仓订单ID、平仓均价、盈亏与状态"""
    db_pool.execute(
        "UPDATE trader_trades SET close_order_id=%s, close_px=%s, profit=%s, "
        "status='closed', closed_at=NOW() WHERE trade_uid=%s",
        (close_order_id, close_px, profit, trade_uid)
    )

def get_customer_by_id(db_pool, customer_uid, is_demo):
    """根据客户UID获取客户信息"""
    rows = db_pool.query("SELECT * FROM customers WHERE customer_uid=%s AND is_demo=%s", (customer_uid, is_demo))
    return rows[0] if rows else None

def get_signal_source_by_id(db_pool, signal_source_uid, is_demo):
    """根据信号源UID获取信号源信息"""
    rows = db_pool.query("SELECT * FROM signal_sources WHERE source_uid=%s AND is_demo=%s", (signal_source_uid, is_demo))
    return rows[0] if rows else None

def get_customer_effective_asset(db_pool, customer_uid, is_demo):
    """
    获取客户的有效资产用于计算跟单比例 - 应用固定开仓资产逻辑
    逻辑：
    1. 如果设置了开仓资产，优先使用开仓资产
    2. 如果当前总资产 > 开仓资产（盈利），使用当前总资产
    3. 如果当前总资产 <= 开仓资产（亏损或持平），使用开仓资产（保持不变）
    4. 如果未设置开仓资产，使用初始资产和当前总资产的最大值
    """
    customer = get_customer_by_id(db_pool, customer_uid, is_demo)
    if not customer:
        return None
    
    # 获取各种资产值
    trading_asset = customer.get('trading_asset')
    init_asset = float(customer.get('init_asset', 0))
    total_asset = float(customer.get('total_asset', 0))
    
    # 固定开仓资产逻辑
    if trading_asset is not None and float(trading_asset) > 0:
        trading_asset_float = float(trading_asset)
        total_asset_float = float(total_asset) if total_asset else 0
        
        if total_asset_float > trading_asset_float:
            # 盈利时使用当前总资产
            return total_asset_float
        else:
            # 亏损或持平时使用开仓资产（保持不变）
            return trading_asset_float
    else:
        # 没有开仓资产，使用初始资产和当前总资产的最大值
        return max(init_asset, total_asset) if total_asset > 0 else init_asset

def check_signal_trade_exists(db_pool, order_id, signal_source_uid, symbol, pos_side, is_demo):
    """检查信号源交易是否已存在"""
    rows = db_pool.query(
        "SELECT 1 FROM signal_account_trades WHERE order_id=%s AND signal_source_uid=%s AND symbol=%s AND pos_side=%s AND is_demo=%s",
        (order_id, signal_source_uid, symbol, pos_side, is_demo)
    )
    return len(rows) > 0

def check_signal_close_exists(db_pool, close_order_id, signal_source_uid, symbol, pos_side, is_demo):
    """检查信号源平仓是否已存在"""
    rows = db_pool.query(
        "SELECT 1 FROM signal_account_trades WHERE close_order_id=%s AND signal_source_uid=%s AND symbol=%s AND pos_side=%s AND is_demo=%s",
        (close_order_id, signal_source_uid, symbol, pos_side, is_demo)
    )
    return len(rows) > 0

def check_customer_trade_exists(db_pool, trade_uid):
    """检查客户交易是否已存在"""
    rows = db_pool.query("SELECT 1 FROM customer_trades WHERE trade_uid=%s", (trade_uid,))
    return len(rows) > 0

def check_customer_trade_updated(db_pool, trade_uid, close_order_id):
    """检查客户交易是否已被特定平仓订单更新过"""
    rows = db_pool.query(
        "SELECT 1 FROM customer_trades WHERE trade_uid=%s AND close_order_id=%s",
        (trade_uid, close_order_id)
    )
    return len(rows) > 0

def get_customer_trades_with_lock(db_pool, customer_uid, symbol, pos_side, is_demo):
    """获取客户持仓（带锁保护）"""
    # 使用数据库事务确保数据一致性
    with db_pool.get_conn() as conn:
        with conn.cursor() as cursor:
            conn.begin()
            try:
                cursor.execute(
                    "SELECT * FROM customer_trades WHERE customer_uid=%s AND symbol=%s AND pos_side=%s AND status='open' AND is_demo=%s FOR UPDATE",
                    (customer_uid, symbol, pos_side, is_demo)
                )
                result = cursor.fetchall()
                conn.commit()
                return result
            except Exception as e:
                conn.rollback()
                logger.error(f"获取客户持仓异常: {e}")
                raise e

def update_customer_trade_with_lock(db_pool, trade_uid, **kwargs):
    """更新客户交易记录（带锁保护）"""
    with db_pool.get_conn() as conn:
        with conn.cursor() as cursor:
            conn.begin()
            try:
                set_clause = ", ".join([f"{k}=%s" for k in kwargs.keys()])
                values = list(kwargs.values()) + [trade_uid]
                cursor.execute(
                    f"UPDATE customer_trades SET {set_clause} WHERE trade_uid=%s",
                    values
                )
                conn.commit()
                return cursor.rowcount
            except Exception as e:
                conn.rollback()
                logger.error(f"更新客户交易记录异常: {e}")
                raise e

def get_customer_trades_by_symbol_and_pos(db_pool, customer_uid, symbol, pos_side, is_demo):
    """获取客户指定币种和方向的持仓"""
    return db_pool.query(
        "SELECT * FROM customer_trades WHERE customer_uid=%s AND symbol=%s AND pos_side=%s AND status='open' AND is_demo=%s",
        (customer_uid, symbol, pos_side, is_demo)
    )

def get_signal_trades_by_symbol_and_pos(db_pool, signal_source_uid, symbol, pos_side, is_demo):
    """获取信号源指定币种和方向的持仓"""
    return db_pool.query(
        "SELECT * FROM signal_account_trades WHERE signal_source_uid=%s AND symbol=%s AND pos_side=%s AND status='open' AND is_demo=%s",
        (signal_source_uid, symbol, pos_side, is_demo)
    )

def get_customer_total_leverage(db_pool, customer_uid, is_demo):
    """获取客户总杠杆"""
    # 查询客户所有持仓的名义价值总和
    trades = db_pool.query(
        "SELECT volume FROM customer_trades WHERE customer_uid=%s AND status='open' AND is_demo=%s",
        (customer_uid, is_demo)
    )
    total_nominal = sum(float(trade['volume'] or 0) for trade in trades)
    
    # 使用有效资产计算杠杆
    effective_asset = get_customer_effective_asset(db_pool, customer_uid, is_demo)
    if effective_asset and effective_asset > 0:
        return total_nominal / effective_asset
    return 0

def get_customer_signal_source_trades(db_pool, customer_uid, signal_source_uid, is_demo):
    """获取客户跟随指定信号源的持仓"""
    return db_pool.query(
        """
        SELECT ct.* FROM customer_trades ct 
        JOIN rules r ON ct.rule_uid = r.rule_uid 
        JOIN strategies s ON r.strategy_uid = s.strategy_uid 
        WHERE ct.customer_uid=%s AND s.signal_source_uid=%s AND ct.status='open' AND ct.is_demo=%s
        """,
        (customer_uid, signal_source_uid, is_demo)
    )

def get_signal_source_init_asset(db_pool, signal_source_uid):
    rows = db_pool.query("SELECT init_assets FROM signal_sources WHERE source_uid=%s", (signal_source_uid,))
    return rows[0]['init_assets'] if rows else None

def update_signal_source_init_asset(db_pool, signal_source_uid, asset):
    return db_pool.execute("UPDATE signal_sources SET init_assets=%s WHERE source_uid=%s", (asset, signal_source_uid))

def get_enabled_customers(db_pool, is_demo):
    """获取所有启用的客户账户"""
    return db_pool.query("SELECT * FROM customers WHERE enabled=1 AND is_demo=%s", (is_demo,))

def close_signal_account_trade(db_pool, trade_uid, close_order_id, close_px, profit, is_demo):
    """更新信号源账户交易为平仓"""
    # 先查询原始持仓量
    rows = db_pool.query(
        "SELECT volume_contract FROM signal_account_trades WHERE trade_uid=%s AND is_demo=%s",
        (trade_uid, is_demo)
    )
    
    if rows:
        volume_contract = float(rows[0]['volume_contract'] or 0)
        logger.info(f"[信号源减仓] 找到原始持仓记录: trade_uid={trade_uid}, volume_contract={volume_contract}")
        # 更新为平仓状态，同时设置close_volume_contract为原始持仓量
        db_pool.execute(
            "UPDATE signal_account_trades SET close_order_id=%s, close_px=%s, profit=%s, close_volume_contract=%s, status='closed', closed_at=NOW() WHERE trade_uid=%s AND is_demo=%s",
            (close_order_id, close_px, profit, volume_contract, trade_uid, is_demo)
        )
        logger.info(f"[信号源减仓] 更新完成: trade_uid={trade_uid}, close_volume_contract={volume_contract}")
    else:
        logger.warning(f"[信号源减仓] 未找到原始持仓记录: trade_uid={trade_uid}, is_demo={is_demo}")
        # 如果找不到记录，只更新基本字段
        db_pool.execute(
            "UPDATE signal_account_trades SET close_order_id=%s, close_px=%s, profit=%s, status='closed', closed_at=NOW() WHERE trade_uid=%s AND is_demo=%s",
            (close_order_id, close_px, profit, trade_uid, is_demo)
        )

def get_signal_sources_by_strategy(db_pool, strategy_uid):
    """获取策略关联的所有信号源（多对多）"""
    return db_pool.query(
        "SELECT ss.* FROM strategy_signal_source sss JOIN signal_sources ss ON sss.source_uid=ss.source_uid WHERE sss.strategy_uid=%s AND sss.enabled=1 AND ss.enabled=1",
        (strategy_uid,)
    )

def get_signal_sources_and_rules_by_strategy(db_pool, strategy_uid):
    """查询同一策略下关联的信号源和信号源对应的规则"""
    sql = '''
    SELECT *
    FROM signal_sources
    LEFT JOIN rules ON signal_sources.source_uid = rules.rule_uid
    LEFT JOIN strategy_signal_source ON signal_sources.source_uid = strategy_signal_source.signal_source_uid
    WHERE strategy_signal_source.enabled = 1 AND strategy_signal_source.strategy_uid = %s
    '''
    return db_pool.query(sql, (strategy_uid,))

# 修正：用JOIN查找信号源和规则一一对应，且都启用

def get_rule_by_signal_source(db_pool, source_uid, strategy_uid):
    """根据信号源 source_uid 和策略 strategy_uid 查找规则"""
    # 查询规则，其中rule_uid等于signal_source_uid，且属于指定策略
    rows = db_pool.query(
        "SELECT r.* FROM rules r WHERE r.rule_uid = %s AND r.strategy_uid = %s AND r.enabled = 1",
        (source_uid, strategy_uid)
    )
    return rows[0] if rows else None

def get_signal_source_current_asset(db_pool, signal_source_uid):
    """获取信号源的当前快照资产"""
    rows = db_pool.query(
        "SELECT asset FROM signal_account_assets WHERE signal_source_uid=%s ORDER BY snapshot_time DESC LIMIT 1",
        (signal_source_uid,)
    )
    return rows[0]['asset'] if rows else None

def get_customer_strategies(db_pool, customer_uid):
    """获取客户绑定的所有策略"""
    return db_pool.query(
        "SELECT s.* FROM strategies s JOIN customer_strategy cs ON s.strategy_uid = cs.strategy_uid WHERE cs.customer_uid = %s",
        (customer_uid, )
    )

def get_strategy_customers(db_pool, strategy_uid):
    """获取策略绑定的所有客户"""
    return db_pool.query(
        "SELECT c.* FROM customers c JOIN customer_strategy cs ON c.customer_uid = cs.customer_uid WHERE cs.strategy_uid = %s",
        (strategy_uid, )
    )

def bind_customer_to_strategy(db_pool, customer_uid, strategy_uid):
    """绑定客户到策略"""
    try:
        # 检查是否已存在绑定关系
        existing = db_pool.query(
            "SELECT 1 FROM customer_strategy WHERE customer_uid = %s AND strategy_uid = %s",
            (customer_uid, strategy_uid)
        )
        if existing:
            return False, "客户与策略已存在绑定关系"
        
        # 插入绑定关系
        db_pool.execute(
            "INSERT INTO customer_strategy (customer_uid, strategy_uid) VALUES (%s, %s)",
            (customer_uid, strategy_uid)
        )
        return True, "绑定成功"
    except Exception as e:
        logger.error(f"绑定客户到策略失败: {e}")
        return False, f"绑定失败: {str(e)}"

def unbind_customer_from_strategy(db_pool, customer_uid, strategy_uid):
    """解除客户与策略的绑定关系"""
    try:
        result = db_pool.execute(
            "DELETE FROM customer_strategy WHERE customer_uid = %s AND strategy_uid = %s",
            (customer_uid, strategy_uid)
        )
        if result:
            return True, "解除绑定成功"
        else:
            return False, "未找到绑定关系"
    except Exception as e:
        logger.error(f"解除客户与策略绑定失败: {e}")
        return False, f"解除绑定失败: {str(e)}"

def get_customer_strategy_bindings(db_pool, is_demo):
    """获取启用状态下所有客户策略绑定关系"""
    return db_pool.query(
        """
        SELECT cs.*, c.name as customer_name, s.name as strategy_name 
        FROM customer_strategy cs 
        JOIN customers c ON cs.customer_uid = c.customer_uid 
        JOIN strategies s ON cs.strategy_uid = s.strategy_uid 
        where c.enabled = 1 and s.enabled = 1
        """
    )

def get_customer_strategy_all(db_pool):
    """获取所有客户策略绑定关系"""
    return db_pool.query(
        """
        SELECT cs.*, c.name as customer_name, s.name as strategy_name 
        FROM customer_strategy cs 
        JOIN customers c ON cs.customer_uid = c.customer_uid 
        JOIN strategies s ON cs.strategy_uid = s.strategy_uid
        """
    )

# 全局数据库连接池实例
_global_db_pool = None

def get_db_pool():
    """获取全局数据库连接池实例"""
    from database.global_db_manager import get_global_db_pool
    return get_global_db_pool()

def get_db_connection():
    """获取一个原始数据库连接（供脚本使用 cursor 直接操作）"""
    return get_db_pool().get_conn()

def set_db_pool(db_pool):
    """设置全局数据库连接池实例"""
    global _global_db_pool
    _global_db_pool = db_pool