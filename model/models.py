from dataclasses import dataclass
from datetime import datetime
from typing import Optional

@dataclass
class SignalAccount:
    source_uid: str
    name: str
    api_key: str
    api_secret: str
    passphrase: str
    exchange: str
    enabled: bool
    init_assets: Optional[float] = None  # 新增
    total_assets: Optional[float] = None
    leverage: Optional[int] = 1  # 信号源当前使用的杠杆倍率
    is_demo: Optional[bool] = None
    created_at: Optional[datetime] = None
    unique_name: Optional[str] = None
    # 新增止损相关字段
    stop_loss_percent: Optional[float] = None  # 止损百分比
    recently_assets: Optional[float] = None  # 最近资产（止损前）
    last_stop_loss_time: Optional[datetime] = None  # 上次止损时间
    stop_loss_count: Optional[int] = None  # 止损次数


@dataclass
class Strategy:
    strategy_uid: str
    name: str
    signal_source_uid: str
    enabled: bool
    created_at: Optional[datetime] = None

@dataclass
class Rule:
    rule_uid: str
    strategy_uid: str
    name: str
    position_ratio: float
    max_leverage: float
    enabled: bool

@dataclass
class Customer:
    customer_uid: str
    name: str
    api_key: str
    api_secret: str
    passphrase: str
    init_asset: float
    trading_asset: Optional[float] = None  # 开仓资产，用于计算跟单比例，如果为空则使用init_asset
    total_asset: float = 0.0
    exchange: str = "OKX"
    enabled: bool = True
    leverage: Optional[int] = 1  # 客户当前使用的杠杆倍率
    is_demo: Optional[bool] = None
    created_at: Optional[datetime] = None
    # 新增止损相关字段
    stop_loss_percent: Optional[float] = None  # 止损百分比
    recently_assets: Optional[float] = None  # 最近资产（止损前）
    last_stop_loss_time: Optional[datetime] = None  # 上次止损时间
    stop_loss_count: Optional[int] = None  # 止损次数

@dataclass
class CustomerStrategy:
    id: int
    customer_uid: str
    strategy_uid: str

@dataclass
class CustomerRule:
    id: int
    customer_uid: str
    rule_uid: str
    enabled: bool

@dataclass
class SignalAccountAsset:
    asset_uid: str
    signal_source_uid: str
    asset: float
    snapshot_time: Optional[str]

@dataclass
class SignalAccountTrade:
    trade_uid: str
    signal_source_uid: str
    symbol: str
    direction: str
    pos_side: str
    volume: float
    order_id: Optional[str]
    trade_type: str
    close_order_id: Optional[str] = None  # 新增
    open_px: Optional[float] = None      # 新增
    close_px: Optional[float] = None     # 新增
    profit: Optional[float] = None       # 新增
    status: Optional[str] = 'open'       # 新增
    created_at: Optional[str] = None
    closed_at: Optional[str] = None      # 新增
    close_volume_contract: Optional[float] = None
    volume_contract: Optional[float] = None
    is_demo: Optional[bool] = None
    execution_type: Optional[str] = 'auto'
    execution_reason: Optional[str] = None

@dataclass
class CustomerTrade:
    trade_uid: str
    customer_uid: str
    strategy_uid: str
    rule_uid: str
    symbol: str
    volume: float  # 名义价值

    direction: str
    pos_side: str
    order_id: Optional[str]
    close_order_id: Optional[str]  # 新增
    profit: Optional[float]
    clOrdId:Optional[str]
    parent_ordId: Optional[str]
    parent_clOrdId: Optional[str]
    split_ratio: Optional[float]
    status: str
    created_at: Optional[str]
    closed_at: Optional[str]
    execution_reason: Optional[str]
    parent_operation_id: Optional[str]
    open_px: Optional[float] = None
    close_px: Optional[float] = None
    is_demo: Optional[bool] = None
    close_volume_contract: Optional[float] = None
    volume_contract: Optional[float] = None
    execution_type: Optional[str] = 'auto'

@dataclass
class TradeFailure:
    failure_uid: str
    customer_trade_uid: Optional[str]
    reason: Optional[str]
    created_at: Optional[str] 