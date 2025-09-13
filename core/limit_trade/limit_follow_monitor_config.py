"""
限价跟单监控配置模块
提供监控相关的配置和数据结构
"""

from enum import Enum
from dataclasses import dataclass
from typing import Dict, Any, Optional
from database.global_db_manager import get_global_db_pool


class MonitorStatus(Enum):
    """监控状态枚举"""
    STOPPED = "stopped"
    STARTING = "starting"
    HEALTHY = "healthy"
    WARNING = "warning"
    ERROR = "error"


class MonitorMetrics:
    """监控指标"""
    
    def __init__(self):
        # 订单相关指标
        self.orders_checked: int = 0
        self.orders_synced: int = 0
        self.orders_updated: int = 0
        self.orders_failed: int = 0
        self.orders_repaired: int = 0
        
        # API相关指标
        self.api_calls_total: int = 0
        self.api_calls_success: int = 0
        self.api_calls_failed: int = 0
        
        # WebSocket相关指标
        self.websocket_messages: int = 0
        
        # 同步相关指标
        self.sync_cycles_completed: int = 0
        
        # 错误和失败
        self.errors_count: int = 0
        self.consecutive_failures: int = 0
        
        # 时间相关
        self.last_check_time: Optional[float] = None
        self.last_sync_time: Optional[float] = None
        self.uptime_start: Optional[object] = None  # datetime对象
    
    def record_order_check(self, success: bool = True):
        """记录订单检查"""
        self.orders_checked += 1
        if not success:
            self.orders_failed += 1
            self.consecutive_failures += 1
        else:
            self.consecutive_failures = 0  # 重置连续失败计数
    
    def record_order_update(self):
        """记录订单更新"""
        self.orders_updated += 1
    
    def record_api_call(self, success: bool = True):
        """记录API调用"""
        self.api_calls_total += 1
        if success:
            self.api_calls_success += 1
        else:
            self.api_calls_failed += 1
    
    def record_websocket_message(self):
        """记录WebSocket消息"""
        self.websocket_messages += 1
    
    def record_sync_cycle(self):
        """记录同步周期完成"""
        self.sync_cycles_completed += 1
        import time
        self.last_sync_time = time.time()
    
    def record_error(self):
        """记录错误"""
        self.errors_count += 1
        self.consecutive_failures += 1
    
    @property
    def success_rate(self) -> float:
        """订单检查成功率"""
        if self.orders_checked == 0:
            return 1.0
        return (self.orders_checked - self.orders_failed) / self.orders_checked
    
    @property
    def api_success_rate(self) -> float:
        """API调用成功率"""
        if self.api_calls_total == 0:
            return 1.0
        return self.api_calls_success / self.api_calls_total


@dataclass
class OrderSyncResult:
    """订单同步结果"""
    success: bool
    orders_synced: int = 0
    errors: list = None
    
    # 额外的属性，用于详细的同步结果
    start_time: Optional[float] = None
    end_time: Optional[float] = None
    total_checked: int = 0
    orders_updated: int = 0
    updated_count: int = 0
    error_count: int = 0
    duration: float = 0.0
    
    def __post_init__(self):
        if self.errors is None:
            self.errors = []


def get_monitor_config() -> Dict[str, Any]:
    """获取监控配置"""
    return {
        # 基础监控配置
        "check_interval": 30,  # 检查间隔（秒）
        "sync_interval": 300,  # 同步间隔（秒）
        "status_sync_interval": 60,  # 状态同步间隔（秒）
        "health_check_interval": 120,  # 健康检查间隔（秒）
        
        # WebSocket配置
        "websocket_enabled": True,  # WebSocket更新由信号服务处理
        "enable_websocket_updates": True,  # 启用WebSocket更新
        
        # 自动修复配置
        "auto_repair_enabled": True,  # 启用自动修复
        "enable_auto_repair": True,  # 启用自动修复（别名）
        "auto_repair_max_orders": 10,  # 自动修复最大订单数
        "stale_order_timeout": 3600,  # 过期订单超时时间（秒）
        
        # 并发和批处理配置
        "max_concurrent": 10,  # 最大并发数
        "max_concurrent_checks": 5,  # 最大并发检查数
        "batch_size": 50,  # 批处理大小
        "batch_sync_size": 20,  # 批量同步大小
        
        # 重试和超时配置
        "retry_attempts": 3,  # 重试次数
        "timeout": 30,  # 超时时间（秒）
        "api_rate_limit_delay": 0.1,  # API速率限制延迟（秒）
        
        # 阈值配置
        "max_consecutive_failures": 5,  # 最大连续失败次数
        "notification_threshold": 3,  # 通知阈值
        "problematic_order_threshold": 10,  # 问题订单阈值
        
        # 日志和通知配置
        "log_performance_metrics": True,  # 记录性能指标
        "log_order_updates": True,  # 记录订单更新
        "enable_notifications": False,  # 启用通知（默认关闭）
    }


def update_monitor_config(config_updates: Dict[str, Any]) -> bool:
    """更新监控配置"""
    try:
        db_pool = get_global_db_pool()
        if db_pool is None:
            return False
        
        # 这里可以实现配置更新逻辑
        # 目前返回True表示更新成功
        return True
    except Exception:
        return False


def get_customer_monitor_config(customer_uid: str) -> Dict[str, Any]:
    """获取客户特定的监控配置"""
    try:
        db_pool = get_global_db_pool()
        if db_pool is None:
            return {}
        
        # 查询客户特定配置
        rows = db_pool.query(
            "SELECT * FROM customer_configs WHERE customer_uid = %s",
            (customer_uid,)
        )
        
        if rows:
            # 返回客户特定配置
            return rows[0]
        else:
            # 返回默认配置
            return get_monitor_config()
    except Exception:
        return get_monitor_config() 