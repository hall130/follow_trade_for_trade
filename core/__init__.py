"""
核心模块 - 系统核心业务逻辑

包含以下核心功能:
- 市场交易服务
- 限价跟单服务
- 信号处理服务
- 交易执行服务
- 模块管理器
"""

# 延迟导入，避免在导入core包时立即触发所有依赖
# 这样可以让消息转发模块等独立模块能够正常导入
try:
    from .market_trade.trade_service import TradeService
    from .market_trade.signal_service import SignalService
    from .market_trade.trade_server import TradeServer
    from .limit_trade.limit_follow_service import LimitFollowService
    from .limit_trade.limit_follow_executor import LimitFollowExecutor
    from .module_manager import ModuleManager, get_module_manager, initialize_system, cleanup_system
except ImportError as e:
    # 如果导入失败，不影响其他模块的使用
    # 静默处理，不阻止其他模块的导入
    pass
except Exception as e:
    # 其他异常也静默处理
    pass

__all__ = [
    "TradeService",
    "SignalService", 
    "TradeServer",
    "LimitFollowService",
    "LimitFollowExecutor",
    "ModuleManager",
    "get_module_manager",
    "initialize_system",
    "cleanup_system"
] 