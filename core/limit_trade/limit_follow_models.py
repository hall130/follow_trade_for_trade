#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
限价跟单数据模型
定义限价跟单相关的数据结构
"""

from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
from datetime import datetime
from enum import Enum

class OrderStatus(Enum):
    """订单状态枚举"""
    PENDING = 'pending'      # 待处理
    LIVE = 'live'           # 活跃（已提交到交易所）
    FILLED = 'filled'       # 已成交
    CANCELED = 'canceled'   # 已撤销
    EXPIRED = 'expired'     # 已过期
    REJECTED = 'rejected'   # 被拒绝

class ExecutionStatus(Enum):
    """执行状态枚举"""
    PENDING = 'pending'      # 待执行
    EXECUTING = 'executing'  # 执行中
    COMPLETED = 'completed'  # 已完成
    FAILED = 'failed'        # 执行失败
    CANCELLED = 'cancelled'  # 已取消

class FollowType(Enum):
    """跟单类型枚举"""
    PERCENTAGE = 'percentage'  # 百分比
    FIXED = 'fixed'           # 固定价格

class PosSide(Enum):
    """持仓方向枚举"""
    LONG = 'long'    # 多仓
    SHORT = 'short'  # 空仓
    BOTH = 'both'    # 双向跟随

@dataclass
class LimitFollowStrategy:
    """限价跟单策略"""
    id: Optional[int] = None
    strategy_name: str = ''
    trader_unique_name: str = ''
    customer_uid: str = ''
    symbol: str = ''
    pos_side: str = 'both'  # 默认双向跟随
    follow_type: str = 'percentage'
    follow_value: float = 0.0
    min_follow_value: float = 0.5
    max_follow_value: float = 5.0
    max_orders_per_signal: int = 4
    max_net_leverage: float = 10.0  # 最大净杠杆值
    proportional_position: bool = False  # 是否启用按比例开仓
    auto_cancel_on_signal_close: bool = True
    enabled: bool = True
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    
    def __post_init__(self):
        if self.pos_side not in [e.value for e in PosSide]:
            raise ValueError(f"无效的持仓方向: {self.pos_side}")
        if self.follow_type not in [e.value for e in FollowType]:
            raise ValueError(f"无效的跟单类型: {self.follow_type}")

@dataclass
class LimitFollowOrder:
    """限价跟单订单"""
    id: Optional[int] = None
    order_uid: str = ''
    strategy_id: int = 0
    trader_unique_name: str = ''
    customer_uid: str = ''
    symbol: str = ''
    pos_side: str = 'long'
    follow_value: float = 0.0
    target_price: float = 0.0
    order_size: float = 0.0
    order_type: str = 'limit'
    status: str = 'pending'
    order_id: Optional[str] = None
    exchange_order_id: Optional[str] = None
    filled_price: Optional[float] = None
    filled_size: Optional[float] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    
    def __post_init__(self):
        if self.status not in [e.value for e in OrderStatus]:
            raise ValueError(f"无效的订单状态: {self.status}")
        if self.pos_side not in [e.value for e in PosSide]:
            raise ValueError(f"无效的持仓方向: {self.pos_side}")

@dataclass
class LimitFollowExecution:
    """限价跟单执行记录"""
    id: Optional[int] = None
    execution_uid: str = ''
    strategy_id: int = 0
    order_uid: str = ''
    trader_unique_name: str = ''
    customer_uid: str = ''
    symbol: str = ''
    pos_side: str = 'long'
    execution_type: str = 'order_placement'
    execution_status: str = 'pending'
    execution_data: Dict[str, Any] = field(default_factory=dict)
    error_message: Optional[str] = None
    retry_count: int = 0
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    
    def __post_init__(self):
        if self.execution_status not in [e.value for e in ExecutionStatus]:
            raise ValueError(f"无效的执行状态: {self.execution_status}")

@dataclass
class LimitFollowConfig:
    """限价跟单配置"""
    id: Optional[int] = None
    config_key: str = ''
    config_value: str = ''
    config_type: str = 'string'
    description: Optional[str] = None
    enabled: bool = True
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

@dataclass
class LimitFollowLog:
    """限价跟单日志"""
    id: Optional[int] = None
    log_level: str = 'INFO'
    message: str = ''
    order_uid: Optional[str] = None
    strategy_id: Optional[int] = None
    customer_uid: Optional[str] = None
    trader_unique_name: Optional[str] = None
    extra_data: Optional[Dict[str, Any]] = None
    created_at: Optional[datetime] = None

@dataclass
class FollowOrderRequest:
    """跟单订单请求"""
    trader_unique_name: str
    customer_uid: str
    symbol: str
    pos_side: str
    signal_price: float
    signal_volume: float
    follow_percentages: Optional[List[float]] = None
    strategy_id: Optional[int] = None
    
    def __post_init__(self):
        if self.pos_side not in [e.value for e in PosSide]:
            raise ValueError(f"无效的持仓方向: {self.pos_side}")
        if self.follow_percentages is None:
            self.follow_percentages = [1.0, 2.0, 3.0, 4.0]

@dataclass
class FollowOrderResponse:
    """跟单订单响应"""
    success: bool
    message: str
    orders: List[LimitFollowOrder]
    strategy: Optional[LimitFollowStrategy] = None
    error_code: Optional[str] = None

@dataclass
class CancelFollowOrdersRequest:
    """撤销跟单订单请求"""
    trader_unique_name: str
    symbol: str
    pos_side: str
    strategy_id: Optional[int] = None
    
    def __post_init__(self):
        if self.pos_side not in [e.value for e in PosSide]:
            raise ValueError(f"无效的持仓方向: {self.pos_side}")

@dataclass
class CancelFollowOrdersResponse:
    """撤销跟单订单响应"""
    success: bool
    message: str
    canceled_count: int
    error_code: Optional[str] = None

@dataclass
class LimitFollowStatus:
    """限价跟单状态"""
    total_strategies: int = 0
    active_strategies: int = 0
    total_orders: int = 0
    pending_orders: int = 0
    live_orders: int = 0
    filled_orders: int = 0
    canceled_orders: int = 0
    total_executions: int = 0
    completed_executions: int = 0
    last_update: Optional[datetime] = None

@dataclass
class CustomerLimitFollowSummary:
    """客户限价跟单汇总"""
    customer_uid: str
    customer_name: str
    total_strategies: int = 0
    active_strategies: int = 0
    total_orders: int = 0
    pending_orders: int = 0
    live_orders: int = 0
    filled_orders: int = 0
    canceled_orders: int = 0
    total_executions: int = 0
    completed_executions: int = 0
    last_activity: Optional[datetime] = None

@dataclass
class LimitFollowTrader:
    """限价跟单员"""
    unique_name: str = ''
    name: str = ''
    description: Optional[str] = None
    enabled: bool = True
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

@dataclass
class TraderLimitFollowSummary:
    """跟单员限价跟单汇总"""
    trader_unique_name: str
    trader_name: str
    total_followers: int = 0
    total_orders: int = 0
    pending_orders: int = 0
    live_orders: int = 0
    filled_orders: int = 0
    canceled_orders: int = 0
    last_activity: Optional[datetime] = None

@dataclass
class PriceCalculationResult:
    """价格计算结果"""
    original_price: float
    pos_side: str
    follow_percentages: List[float]
    calculated_prices: List[float]
    order_sizes: List[float]
    
    def __post_init__(self):
        if len(self.calculated_prices) != len(self.follow_percentages):
            raise ValueError("价格数量与百分比数量不匹配")
        if len(self.order_sizes) != len(self.follow_percentages):
            raise ValueError("订单数量与百分比数量不匹配")

@dataclass
class OrderPlacementResult:
    """订单提交结果"""
    order_uid: str
    exchange_order_id: Optional[str]
    status: str
    message: str
    target_price: float
    order_size: float
    follow_percentage: float
    success: bool = False
    error_code: Optional[str] = None

@dataclass
class SignalEvent:
    """信号事件"""
    event_type: str  # 'open_position', 'close_position', 'place_order', 'cancel_order'
    trader_unique_name: str
    symbol: str
    pos_side: str
    price: float
    volume: float
    timestamp: datetime
    event_data: Dict[str, Any] = field(default_factory=dict)
    
    def __post_init__(self):
        if self.pos_side not in [e.value for e in PosSide]:
            raise ValueError(f"无效的持仓方向: {self.pos_side}")

# 工具函数
def create_order_uid() -> str:
    """生成订单UID"""
    import uuid
    return str(uuid.uuid4())

def create_execution_uid() -> str:
    """生成执行记录UID"""
    import uuid
    return str(uuid.uuid4())

def validate_price(price: float) -> bool:
    """验证价格有效性"""
    return isinstance(price, (int, float)) and price > 0

def validate_volume(volume: float) -> bool:
    """验证数量有效性"""
    return isinstance(volume, (int, float)) and volume > 0

def format_price(price: float, precision: int = 8) -> float:
    """格式化价格精度"""
    return round(price, precision)

def format_volume(volume: float, precision: int = 8) -> float:
    """格式化数量精度"""
    return round(volume, precision)

def calculate_follow_price(original_price: float, percentage: float, pos_side: str) -> float:
    """
    计算跟单价格
    
    Args:
        original_price: 原始价格
        percentage: 跟单百分比
        pos_side: 持仓方向 ('long' 或 'short')
    
    Returns:
        计算后的跟单价格
    """
    if pos_side == 'long':
        # 多仓：低于原始价格
        return original_price * (1 - percentage / 100)
    elif pos_side == 'short':
        # 空仓：高于原始价格
        return original_price * (1 + percentage / 100)
    else:
        raise ValueError(f"无效的持仓方向: {pos_side}")

def calculate_order_size(base_volume: float, follow_percentage: float, strategy: LimitFollowStrategy) -> float:
    """
    计算订单数量
    
    Args:
        base_volume: 基础数量（信号源数量）
        follow_percentage: 跟单百分比
        strategy: 跟单策略
    
    Returns:
        计算后的订单数量
    """
    # 根据跟单百分比和策略配置计算数量
    if strategy.follow_type == 'percentage':
        # 百分比类型：按比例计算
        return base_volume * (follow_percentage / 100)
    else:
        # 固定价格类型：使用固定数量
        return strategy.follow_value

def get_status_text(status: str) -> str:
    """获取状态文本"""
    status_map = {
        'pending': '待处理',
        'live': '活跃',
        'filled': '已成交',
        'canceled': '已撤销',
        'expired': '已过期',
        'rejected': '被拒绝'
    }
    return status_map.get(status, status)

def get_status_class(status: str) -> str:
    """获取状态CSS类"""
    status_map = {
        'pending': 'warning',
        'live': 'info',
        'filled': 'success',
        'canceled': 'secondary',
        'expired': 'danger',
        'rejected': 'danger'
    }
    return status_map.get(status, 'secondary') 