#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
全局数据库连接池管理器
确保整个系统只使用一个连接池实例，避免连接数爆炸
支持同步和异步两种模式
"""

import asyncio
import threading
from typing import Optional, Union
import concurrent.futures
import pymysql
from config.config import get_mysql_config
from utils.logger import logger

# 直接导入DBUtils，避免循环导入
try:
    from dbutils.pooled_db import PooledDB
    DBUTILS_AVAILABLE = True
except ImportError:
    logger.warning("DBUtils不可用，将使用简化的数据库连接")
    DBUTILS_AVAILABLE = False
    PooledDB = None

class MySQLPool:
    """MySQL连接池包装类"""
    def __init__(self, host, user, password, db, port=3306, mincached=2, maxcached=10):
        self.host = host
        self.user = user
        self.password = password
        self.db = db
        self.port = port
        
        if DBUTILS_AVAILABLE and PooledDB:
            self.pool = PooledDB(
                creator=pymysql,
                host=host, user=user, password=password, db=db, port=port,
                mincached=mincached, maxcached=maxcached,
                charset='utf8mb4',
                cursorclass=pymysql.cursors.DictCursor,
                autocommit=True
            )
        else:
            # Fallback: 使用简单的连接
            self.pool = None
            logger.warning("使用简化的数据库连接（无连接池）")
    
    def get_conn(self):
        """获取数据库连接"""
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
        """执行查询"""
        with self.get_conn().cursor() as cursor:
            cursor.execute(sql, args or ())
            return cursor.fetchall()
    
    def query_one(self, sql, args=None):
        """查询单条记录，返回第一条结果或None"""
        result = self.query(sql, args)
        if result and len(result) > 0:
            return result[0]
        return None
    
    def execute(self, sql, args=None):
        """执行更新并返回最后插入的ID"""
        with self.get_conn().cursor() as cursor:
            cursor.execute(sql, args or ())
            return cursor.lastrowid
    
    def execute_with_rowcount(self, sql, args=None):
        """执行更新并返回影响的行数"""
        with self.get_conn().cursor() as cursor:
            cursor.execute(sql, args or ())
            return cursor.rowcount
    
    def executemany(self, sql, args_list):
        """批量执行更新"""
        with self.get_conn().cursor() as cursor:
            cursor.executemany(sql, args_list)
            return cursor.rowcount


class GlobalDBManager:
    """全局数据库连接池管理器（单例模式）"""
    
    _instance = None
    _lock = threading.Lock()
    _async_lock = asyncio.Lock()
    _pool = None
    _executor = None
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        # 避免重复初始化
        if hasattr(self, "_initialized"):
            return
        self._initialized = True
        
        # 创建线程池执行器用于异步操作
        self._executor = concurrent.futures.ThreadPoolExecutor(
            max_workers=5, 
            thread_name_prefix="db_pool_async"
        )
        
    def get_pool(self) -> Optional[MySQLPool]:
        """获取全局数据库连接池"""
        if self._pool is None:
            with self._lock:
                if self._pool is None:
                    self._pool = self._create_pool()
        return self._pool
    
    async def get_pool_async(self) -> Optional[MySQLPool]:
        """异步获取全局数据库连接池"""
        if self._pool is None:
            try:
                # 使用asyncio.Lock来保证异步环境下的线程安全
                if not hasattr(self, '_async_lock_instance'):
                    self._async_lock_instance = asyncio.Lock()
                    
                async with self._async_lock_instance:
                    if self._pool is None:
                        # 在线程池中执行同步的连接池创建
                        loop = asyncio.get_event_loop()
                        self._pool = await loop.run_in_executor(
                            self._executor, 
                            self._create_pool
                        )
            except Exception as e:
                logger.error(f"❌ 异步获取数据库连接池失败: {e}")
                return None
        return self._pool
    
    def _create_pool(self) -> Optional[MySQLPool]:
        """创建数据库连接池的内部方法"""
        try:
            mysql_config = get_mysql_config()
            # 优化连接池配置（提高并发能力）
            mysql_config["mincached"] = 20     # 最小连接数（提高以应对高并发）
            mysql_config["maxcached"] = 100    # 最大连接数（提高以应对高并发）
            
            # 移除所有不支持的参数
            mysql_config.pop("blocking", None)
            mysql_config.pop("maxconnections", None)
            mysql_config.pop("connect_timeout", None)
            mysql_config.pop("read_timeout", None)
            mysql_config.pop("write_timeout", None)
            
            pool = MySQLPool(**mysql_config)
            logger.info(f"🎯 全局数据库连接池创建成功: min={mysql_config['mincached']}, max={mysql_config['maxcached']}")
            return pool
        except Exception as e:
            logger.error(f"❌ 全局数据库连接池创建失败: {e}")
            import traceback
            logger.error(f"详细错误: {traceback.format_exc()}")
            return None

    async def query_async(self, sql: str, args=None):
        """异步数据库查询"""
        pool = await self.get_pool_async()
        if pool is None:
            raise RuntimeError("数据库连接池不可用")
        
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            self._executor,
            lambda: pool.query(sql, args)
        )
    
    async def execute_async(self, sql: str, args=None):
        """异步数据库执行"""
        pool = await self.get_pool_async()
        if pool is None:
            raise RuntimeError("数据库连接池不可用")
        
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            self._executor,
            lambda: pool.execute(sql, args)
        )

    def close_pool(self):
        """关闭连接池"""
        if self._pool is not None:
            with self._lock:
                if self._pool is not None:
                    # PyMySQL连接池没有显式关闭方法，设为None让GC处理
                    self._pool = None
                    logger.info("🔒 全局数据库连接池已关闭")
        
        # 关闭线程池执行器
        if self._executor is not None:
            self._executor.shutdown(wait=True)
            self._executor = None
            logger.info("🔒 数据库异步执行器已关闭")
    
    def get_pool_stats(self) -> dict:
        """获取连接池统计信息"""
        if self._pool is None:
            return {"status": "not_initialized"}
        
        # dbutils.pooled_db 没有直接的统计接口，返回基本信息
        return {
            "status": "active",
            "pool_created": self._pool is not None,
            "config": "single_global_pool"
        }


# 全局实例
_global_db_manager = GlobalDBManager()


# ==================== 同步接口 ====================

def get_global_db_pool() -> Optional[MySQLPool]:
    """获取全局数据库连接池的便捷函数（同步）"""
    return _global_db_manager.get_pool()


def close_global_db_pool():
    """关闭全局数据库连接池"""
    _global_db_manager.close_pool()


def get_db_pool_stats() -> dict:
    """获取数据库连接池统计信息"""
    return _global_db_manager.get_pool_stats()


# ==================== 异步接口 ====================

async def get_global_db_pool_async() -> Optional[MySQLPool]:
    """获取全局数据库连接池的便捷函数（异步）"""
    return await _global_db_manager.get_pool_async()


async def query_async(sql: str, args=None):
    """异步数据库查询的便捷函数"""
    return await _global_db_manager.query_async(sql, args)


async def execute_async(sql: str, args=None):
    """异步数据库执行的便捷函数"""
    return await _global_db_manager.execute_async(sql, args)


# ==================== 统一接口（自动检测环境） ====================

def db_query(sql: str, args=None):
    """统一数据库查询接口（自动检测同步/异步环境）"""
    try:
        # 检查是否在异步环境中
        loop = asyncio.get_running_loop()
        if loop and loop.is_running():
            # 在异步环境中，返回协程
            return query_async(sql, args)
    except RuntimeError:
        # 不在异步环境中，使用同步方式
        pass
    
    # 同步调用
    pool = get_global_db_pool()
    if pool is None:
        raise RuntimeError("数据库连接池不可用")
    return pool.query(sql, args)


def db_execute(sql: str, args=None):
    """统一数据库执行接口（自动检测同步/异步环境）"""
    try:
        # 检查是否在异步环境中
        loop = asyncio.get_running_loop()
        if loop and loop.is_running():
            # 在异步环境中，返回协程
            return execute_async(sql, args)
    except RuntimeError:
        # 不在异步环境中，使用同步方式
        pass
    
    # 同步调用
    pool = get_global_db_pool()
    if pool is None:
        raise RuntimeError("数据库连接池不可用")
    return pool.execute(sql, args)