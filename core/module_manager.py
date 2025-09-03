#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
模块管理器 - 协调各个模块之间的交互和初始化

负责:
- 模块初始化顺序管理
- 模块间依赖关系管理
- 全局状态管理
- 错误处理和恢复
"""

import asyncio
import threading
import time
from typing import Dict, List, Optional, Any
from contextlib import asynccontextmanager

from utils.logger import logger
from database import get_db_pool
from config import get_mysql_config, get_okx_config
from exchange.okx import OKXRESTClient, OKXWebSocketClient
from core.market_trade.trade_service import TradeService
from core.market_trade.signal_service import SignalService
from core.limit_trade.limit_follow_service import LimitFollowService
from core.limit_trade.limit_follow_executor import LimitFollowExecutor


class ModuleManager:
    """模块管理器"""
    
    def __init__(self):
        self.modules = {}
        self.module_status = {}
        self.dependencies = {}
        self.initialization_order = []
        self.is_initialized = False
        self.lock = threading.Lock()
        
        # 定义模块依赖关系
        self._setup_dependencies()
        
    def _setup_dependencies(self):
        """设置模块依赖关系"""
        self.dependencies = {
            'database': [],
            'config': [],
            'exchange': ['config'],
            'trade_service': ['database', 'exchange'],
            'signal_service': ['database', 'exchange'],
            'limit_follow_service': ['database', 'exchange'],
            'limit_follow_executor': ['database', 'exchange', 'limit_follow_service'],
            'api_server': ['database', 'trade_service', 'signal_service', 'limit_follow_service']
        }
        
        # 计算初始化顺序
        self._calculate_init_order()
    
    def _calculate_init_order(self):
        """计算模块初始化顺序（拓扑排序）"""
        visited = set()
        temp_visited = set()
        order = []
        
        def dfs(module):
            if module in temp_visited:
                raise ValueError(f"检测到循环依赖: {module}")
            if module in visited:
                return
            
            temp_visited.add(module)
            
            for dep in self.dependencies.get(module, []):
                dfs(dep)
            
            temp_visited.remove(module)
            visited.add(module)
            order.append(module)
        
        for module in self.dependencies.keys():
            if module not in visited:
                dfs(module)
        
        self.initialization_order = order
        logger.info(f"模块初始化顺序: {self.initialization_order}")
    
    async def initialize_all(self):
        """初始化所有模块"""
        if self.is_initialized:
            logger.warning("模块已经初始化，跳过重复初始化")
            return
        
        logger.info("开始初始化所有模块...")
        
        try:
            for module_name in self.initialization_order:
                await self._initialize_module(module_name)
            
            self.is_initialized = True
            logger.info("所有模块初始化完成")
            
        except Exception as e:
            logger.error(f"模块初始化失败: {e}")
            await self.cleanup()
            raise
    
    async def _initialize_module(self, module_name: str):
        """初始化单个模块"""
        logger.info(f"正在初始化模块: {module_name}")
        
        try:
            if module_name == 'database':
                await self._init_database()
            elif module_name == 'config':
                await self._init_config()
            elif module_name == 'exchange':
                await self._init_exchange()
            elif module_name == 'trade_service':
                await self._init_trade_service()
            elif module_name == 'signal_service':
                await self._init_signal_service()
            elif module_name == 'limit_follow_service':
                await self._init_limit_follow_service()
            elif module_name == 'limit_follow_executor':
                await self._init_limit_follow_executor()
            elif module_name == 'api_server':
                await self._init_api_server()
            
            self.module_status[module_name] = 'initialized'
            logger.info(f"模块 {module_name} 初始化完成")
            
        except Exception as e:
            logger.error(f"模块 {module_name} 初始化失败: {e}")
            self.module_status[module_name] = 'failed'
            raise
    
    async def _init_database(self):
        """初始化数据库连接"""
        try:
            db_pool = get_db_pool()
            await db_pool.test_connection()
            self.modules['database'] = db_pool
            logger.info("数据库连接初始化成功")
        except Exception as e:
            logger.error(f"数据库初始化失败: {e}")
            raise
    
    async def _init_config(self):
        """初始化配置"""
        try:
            mysql_config = get_mysql_config()
            okx_config = get_okx_config()
            self.modules['config'] = {
                'mysql': mysql_config,
                'okx': okx_config
            }
            logger.info("配置初始化成功")
        except Exception as e:
            logger.error(f"配置初始化失败: {e}")
            raise
    
    async def _init_exchange(self):
        """初始化交易所客户端"""
        try:
            # OKX配置从数据库中的客户和信号源获取，这里只初始化基础配置
            # 实际的API客户端会在需要时动态创建
            self.modules['exchange'] = {
                'okx_rest': None,  # 动态创建
                'okx_ws': None,    # 动态创建
                'base_config': {
                    'base_url': 'https://www.okx.com',
                    'api_url': 'https://www.okx.com/api/v5',
                    'ws_url': 'wss://ws.okx.com:8443/ws/v5/public',
                    'ws_private_url': 'wss://ws.okx.com:8443/ws/v5/private'
                }
            }
            logger.info("交易所基础配置初始化成功")
        except Exception as e:
            logger.error(f"交易所基础配置初始化失败: {e}")
            raise
    
    async def _init_trade_service(self):
        """初始化交易服务"""
        try:
            db_pool = self.modules['database']
            exchange_clients = self.modules['exchange']
            
            trade_service = TradeService(db_pool, exchange_clients)
            await trade_service.initialize()
            
            self.modules['trade_service'] = trade_service
            logger.info("交易服务初始化成功")
        except Exception as e:
            logger.error(f"交易服务初始化失败: {e}")
            raise
    
    async def _init_signal_service(self):
        """初始化信号服务"""
        try:
            db_pool = self.modules['database']
            exchange_clients = self.modules['exchange']
            
            signal_service = SignalService(db_pool, exchange_clients)
            await signal_service.initialize()
            
            self.modules['signal_service'] = signal_service
            logger.info("信号服务初始化成功")
        except Exception as e:
            logger.error(f"信号服务初始化失败: {e}")
            raise
    
    async def _init_limit_follow_service(self):
        """初始化限价跟单服务"""
        try:
            db_pool = self.modules['database']
            exchange_clients = self.modules['exchange']
            
            limit_follow_service = LimitFollowService(db_pool, exchange_clients)
            await limit_follow_service.initialize()
            
            self.modules['limit_follow_service'] = limit_follow_service
            logger.info("限价跟单服务初始化成功")
        except Exception as e:
            logger.error(f"限价跟单服务初始化失败: {e}")
            raise
    
    async def _init_limit_follow_executor(self):
        """初始化限价跟单执行器"""
        try:
            db_pool = self.modules['database']
            exchange_clients = self.modules['exchange']
            limit_follow_service = self.modules['limit_follow_service']
            
            executor = LimitFollowExecutor(db_pool, exchange_clients, limit_follow_service)
            await executor.initialize()
            
            self.modules['limit_follow_executor'] = executor
            logger.info("限价跟单执行器初始化成功")
        except Exception as e:
            logger.error(f"限价跟单执行器初始化失败: {e}")
            raise
    
    async def _init_api_server(self):
        """初始化API服务器"""
        try:
            # API服务器在api_server.py中已经初始化
            # 这里只需要确保依赖的服务都已就绪
            logger.info("API服务器依赖检查完成")
        except Exception as e:
            logger.error(f"API服务器初始化失败: {e}")
            raise
    
    def get_module(self, module_name: str) -> Any:
        """获取已初始化的模块"""
        if not self.is_initialized:
            raise RuntimeError("模块管理器尚未初始化")
        
        if module_name not in self.modules:
            raise ValueError(f"模块 {module_name} 不存在或未初始化")
        
        return self.modules[module_name]
    
    def get_module_status(self) -> Dict[str, str]:
        """获取所有模块状态"""
        return self.module_status.copy()
    
    async def cleanup(self):
        """清理所有模块"""
        logger.info("开始清理所有模块...")
        
        cleanup_order = list(reversed(self.initialization_order))
        
        for module_name in cleanup_order:
            try:
                await self._cleanup_module(module_name)
            except Exception as e:
                logger.error(f"清理模块 {module_name} 时出错: {e}")
        
        self.modules.clear()
        self.module_status.clear()
        self.is_initialized = False
        logger.info("所有模块清理完成")
    
    async def _cleanup_module(self, module_name: str):
        """清理单个模块"""
        if module_name not in self.modules:
            return
        
        try:
            module = self.modules[module_name]
            if hasattr(module, 'cleanup'):
                await module.cleanup()
            elif hasattr(module, 'close'):
                await module.close()
            
            self.module_status[module_name] = 'cleaned'
            logger.info(f"模块 {module_name} 清理完成")
            
        except Exception as e:
            logger.error(f"清理模块 {module_name} 失败: {e}")
    
    @asynccontextmanager
    async def managed_context(self):
        """异步上下文管理器"""
        try:
            await self.initialize_all()
            yield self
        finally:
            await self.cleanup()


# 全局模块管理器实例
_global_module_manager = None

def get_module_manager() -> ModuleManager:
    """获取全局模块管理器实例"""
    global _global_module_manager
    if _global_module_manager is None:
        _global_module_manager = ModuleManager()
    return _global_module_manager

async def initialize_system():
    """初始化整个系统"""
    manager = get_module_manager()
    await manager.initialize_all()
    return manager

async def cleanup_system():
    """清理整个系统"""
    global _global_module_manager
    if _global_module_manager:
        await _global_module_manager.cleanup()
        _global_module_manager = None 