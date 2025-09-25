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
import uuid

class OrderStatus(Enum):
    """订单状态枚举"""
    PENDING = 'pending'      # 待处理
    LIVE = 'live'           # 活跃（已提交到交易所）
    FILLED = 'filled'       # 已成交
    CANCELED = 'canceled'   # 已撤销
    EXPIRED = 'expired'     # 已过期
    REJECTED = 'rejected'   # 被拒绝
    PARTIALLY_FILLED = 'partially_filled'  # 部分成交

class ExecutionStatus(Enum):
    """执行状态枚举"""
    PENDING = 'pending'      # 待执行
    EXECUTING = 'executing'  # 执行中
    COMPLETED = 'completed'  # 已完成
    FAILED = 'failed'        # 执行失败
    CANCELLED = 'cancelled'  # 已取消
    RETRYING = 'retrying'    # 重试中

class FollowType(Enum):
    """跟单类型枚举"""
    PERCENTAGE = 'percentage'  # 百分比
    FIXED = 'fixed'           # 固定价格
    DYNAMIC = 'dynamic'       # 动态调整

class PosSide(Enum):
    """持仓方向枚举"""
    LONG = 'long'    # 多仓
    SHORT = 'short'  # 空仓
    BOTH = 'both'    # 双向跟随

class RiskLevel(Enum):
    """风险等级枚举"""
    LOW = 'low'      # 低风险
    MEDIUM = 'medium'  # 中等风险
    HIGH = 'high'    # 高风险

class OrderType(Enum):
    """订单类型枚举"""
    LIMIT = 'limit'      # 限价单
    MARKET = 'market'    # 市价单
    STOP_LIMIT = 'stop_limit'  # 止损限价单

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
    risk_level: str = 'medium'  # 风险等级
    price_offset_range: List[float] = field(default_factory=lambda: [0.5, 1.0, 1.5, 2.0])
    volume_scale_factors: List[float] = field(default_factory=lambda: [0.8, 1.0, 1.2, 1.5])
    stop_loss_percentage: float = 5.0  # 止损百分比
    take_profit_percentage: float = 10.0  # 止盈百分比
    max_position_size: float = 1000.0  # 最大持仓数量
    min_position_size: float = 0.01  # 最小持仓数量
    enabled: bool = True
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    
    def __post_init__(self):
        if self.pos_side not in [e.value for e in PosSide]:
            raise ValueError(f"无效的持仓方向: {self.pos_side}")
        if self.follow_type not in [e.value for e in FollowType]:
            raise ValueError(f"无效的跟单类型: {self.follow_type}")
        if self.risk_level not in [e.value for e in RiskLevel]:
            raise ValueError(f"无效的风险等级: {self.risk_level}")
        
        # 验证数值范围
        if self.follow_value < 0:
            raise ValueError("跟单值不能为负数")
        if self.max_net_leverage <= 0:
            raise ValueError("最大净杠杆必须大于0")
        if self.stop_loss_percentage < 0:
            raise ValueError("止损百分比不能为负数")
        if self.take_profit_percentage < 0:
            raise ValueError("止盈百分比不能为负数")

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
    exchange_order_id: Optional[str] = None
    filled_price: Optional[float] = None
    filled_size: Optional[float] = None
    limit_close_size: Optional[float] = None
    remaining_size: Optional[float] = None
    order_time: Optional[datetime] = None
    filled_time: Optional[datetime] = None
    cancel_time: Optional[datetime] = None
    stop_loss_price: Optional[float] = None
    take_profit_price: Optional[float] = None
    risk_score: Optional[float] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    
    def __post_init__(self):
        if self.status not in [e.value for e in OrderStatus]:
            raise ValueError(f"无效的订单状态: {self.status}")
        if self.pos_side not in [e.value for e in PosSide]:
            raise ValueError(f"无效的持仓方向: {self.pos_side}")
        if self.order_type not in [e.value for e in OrderType]:
            raise ValueError(f"无效的订单类型: {self.order_type}")
        
        # 生成订单UID
        if not self.order_uid:
            self.order_uid = f"FOLLOW_{uuid.uuid4().hex[:8].upper()}"
        
        # 设置时间戳
        if not self.created_at:
            self.created_at = datetime.now()
        if not self.updated_at:
            self.updated_at = datetime.now()

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
    max_retries: int = 3
    next_retry_time: Optional[datetime] = None
    execution_time: Optional[datetime] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    
    def __post_init__(self):
        if self.execution_status not in [e.value for e in ExecutionStatus]:
            raise ValueError(f"无效的执行状态: {self.execution_status}")
        
        # 生成执行UID
        if not self.execution_uid:
            self.execution_uid = f"EXEC_{uuid.uuid4().hex[:8].upper()}"
        
        # 设置时间戳
        if not self.created_at:
            self.created_at = datetime.now()
        if not self.updated_at:
            self.updated_at = datetime.now()

@dataclass
class LimitFollowConfig:
    """限价跟单配置"""
    id: Optional[int] = None
    config_key: str = ''
    config_value: str = ''
    config_type: str = 'string'
    description: Optional[str] = None
    category: str = 'general'  # 配置分类
    priority: int = 0  # 优先级
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
    source: str = 'system'  # 日志来源
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
    risk_level: str = 'medium'
    stop_loss_percentage: Optional[float] = None
    take_profit_percentage: Optional[float] = None
    max_position_size: Optional[float] = None
    
    def __post_init__(self):
        if self.pos_side not in [e.value for e in PosSide]:
            raise ValueError(f"无效的持仓方向: {self.pos_side}")
        if self.risk_level not in [e.value for e in RiskLevel]:
            raise ValueError(f"无效的风险等级: {self.risk_level}")
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
    warnings: List[str] = field(default_factory=list)
    execution_time: Optional[datetime] = None

@dataclass
class CancelFollowOrdersRequest:
    """撤销跟单订单请求"""
    trader_unique_name: str
    symbol: str
    pos_side: str
    strategy_id: Optional[int] = None
    cancel_reason: str = 'manual'
    
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
    canceled_orders: List[str] = field(default_factory=list)

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
    partially_filled_orders: int = 0
    total_executions: int = 0
    completed_executions: int = 0
    failed_executions: int = 0
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
    total_profit_loss: float = 0.0
    success_rate: float = 0.0
    last_activity: Optional[datetime] = None

@dataclass
class LimitFollowTrader:
    """限价跟单员"""
    unique_name: str = ''
    name: str = ''
    description: Optional[str] = None
    enabled: bool = True
    risk_level: str = 'medium'
    max_followers: int = 100
    current_followers: int = 0
    success_rate: float = 0.0
    total_signals: int = 0
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
    success_rate: float = 0.0
    avg_fill_time: Optional[float] = None
    last_activity: Optional[datetime] = None

@dataclass
class PriceCalculationResult:
    """价格计算结果"""
    original_price: float
    pos_side: str
    follow_percentages: List[float]
    calculated_prices: List[float]
    order_sizes: List[float]
    risk_scores: List[float] = field(default_factory=list)
    
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
    execution_time: Optional[float] = None
    risk_score: Optional[float] = None

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

@dataclass
class RiskAssessment:
    """风险评估"""
    order_uid: str
    risk_score: float
    risk_factors: List[str] = field(default_factory=list)
    recommendations: List[str] = field(default_factory=list)
    max_allowed_size: float = 0.0
    leverage_warning: bool = False
    position_concentration_warning: bool = False
    created_at: Optional[datetime] = None

# 工具函数
def create_order_uid() -> str:
    """生成订单UID"""
    return f"FOLLOW_{uuid.uuid4().hex[:8].upper()}"

def create_execution_uid() -> str:
    """生成执行记录UID"""
    return f"EXEC_{uuid.uuid4().hex[:8].upper()}"

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

def calculate_risk_score(order: LimitFollowOrder, account_info: Dict[str, Any]) -> float:
    """
    计算订单风险分数
    
    Args:
        order: 跟单订单
        account_info: 账户信息
    
    Returns:
        风险分数 (0-100，越高风险越大)
    """
    risk_score = 0.0
    
    # 基于持仓方向的风险
    if order.pos_side == 'short':
        risk_score += 10  # 空仓风险较高
    
    # 基于订单大小的风险
    account_balance = account_info.get('available_balance', 0)
    if account_balance > 0:
        position_ratio = (order.target_price * order.order_size) / account_balance
        if position_ratio > 0.5:
            risk_score += 30
        elif position_ratio > 0.3:
            risk_score += 20
        elif position_ratio > 0.1:
            risk_score += 10
    
    # 基于价格的波动风险
    # 这里可以添加更复杂的波动率计算
    
    return min(risk_score, 100.0)

def get_status_text(status: str) -> str:
    """获取状态文本"""
    status_map = {
        'pending': '待处理',
        'live': '活跃',
        'filled': '已成交',
        'canceled': '已撤销',
        'expired': '已过期',
        'rejected': '被拒绝',
        'partially_filled': '部分成交'
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
        'rejected': 'danger',
        'partially_filled': 'warning'
    }
    return status_map.get(status, 'secondary')

def get_risk_level_class(risk_level: str) -> str:
    """获取风险等级CSS类"""
    risk_map = {
        'low': 'success',
        'medium': 'warning',
        'high': 'danger'
    }
    return risk_map.get(risk_level, 'secondary')

def format_percentage(value: float) -> str:
    """格式化百分比显示"""
    return f"{value:.2f}%"

def format_currency(value: float, currency: str = 'USD') -> str:
    """格式化货币显示"""
    return f"{value:,.2f} {currency}"

def calculate_profit_loss(entry_price: float, current_price: float, pos_side: str, size: float) -> float:
    """
    计算盈亏
    
    Args:
        entry_price: 入场价格
        current_price: 当前价格
        pos_side: 持仓方向
        size: 持仓数量
    
    Returns:
        盈亏金额
    """
    if pos_side == 'long':
        return (current_price - entry_price) * size
    elif pos_side == 'short':
        return (entry_price - current_price) * size
    else:
        return 0.0

def calculate_profit_loss_percentage(entry_price: float, current_price: float, pos_side: str) -> float:
    """
    计算盈亏百分比
    
    Args:
        entry_price: 入场价格
        current_price: 当前价格
        pos_side: 持仓方向
    
    Returns:
        盈亏百分比
    """
    if pos_side == 'long':
        return ((current_price - entry_price) / entry_price) * 100
    elif pos_side == 'short':
        return ((entry_price - current_price) / entry_price) * 100
    else:
        return 0.0 