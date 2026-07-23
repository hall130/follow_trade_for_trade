"""
永续合约网格策略（Perpetual Futures Grid Strategy）
参考: https://www.fmz.com/digest-topic/5930

策略原理（与现货比例网格 FMZGridStrategy 不同）：
1. 以基准价 base_price 为中心，按等比间距 grid_spacing 划分网格线
2. 价格每上穿一个网格线 → 做空 grid_value USDT（不用持币即可做空）
3. 价格每下穿一个网格线 → 做多 grid_value USDT
4. 依靠震荡行情反复开平仓赚取网格利润；价格回到初始价时兑现全部网格利润
5. 支持杠杆、价格区间限制与最大持仓价值保护（防爆仓）

风险提示（来自参考文章）：
- 爆仓风险：期货带杠杆，网格逆趋势加仓，仓位过大时单边行情可能爆仓
- 建议设置价格区间 [lower_bound, upper_bound]，超出区间停止逆势加仓
- 建议设置 max_position_value 限制单方向最大持仓价值
"""

from typing import Dict, List, Any, Optional
from datetime import datetime
import math

from ..base import StrategyBase
from ...base_strategy import MarketData, Signal
from utils.logger import get_logger

logger = get_logger(__name__)


class PerpGridStrategy(StrategyBase):
    """
    永续合约价格锚定网格策略

    区别于 FMZGridStrategy（现货比例平衡网格），本策略：
    - 锚定价格而非币/资金比例
    - 支持做空（价格上涨时开空、下跌时开多）
    - 面向 USDT 本位永续合约，可加杠杆
    """

    # 引擎据此标志允许"裸卖空"信号开空仓；不设置的策略行为完全不受影响
    allow_short = True

    def __init__(self, name: str, symbol: str, config: Dict[str, Any]):
        super().__init__(name, symbol, config)

        # ── 核心网格参数 ──────────────────────────────────
        grid_value_v = self.get_parameter('grid_value', 500.0)
        self.grid_value = float(grid_value_v) if grid_value_v is not None else 500.0  # 单格交易价值（USDT）

        grid_spacing_v = self.get_parameter('grid_spacing', 0.01)
        self.grid_spacing = float(grid_spacing_v) if grid_spacing_v is not None else 0.01  # 网格间距比例（1%）

        base_price_v = self.get_parameter('base_price', 0.0)
        self.base_price = float(base_price_v) if base_price_v is not None else 0.0  # 基准价（0=用首个价格）

        leverage_v = self.get_parameter('leverage', 1.0)
        self.leverage = float(leverage_v) if leverage_v is not None else 1.0  # 杠杆倍数

        # ── 风控参数 ──────────────────────────────────────
        upper_v = self.get_parameter('upper_bound', 0.0)
        self.upper_bound = float(upper_v) if upper_v is not None else 0.0  # 价格上界（0=无限制）

        lower_v = self.get_parameter('lower_bound', 0.0)
        self.lower_bound = float(lower_v) if lower_v is not None else 0.0  # 价格下界（0=无限制）

        max_pos_v = self.get_parameter('max_position_value', 0.0)
        self.max_position_value = float(max_pos_v) if max_pos_v is not None else 0.0  # 单方向最大持仓价值（USDT，0=无限制）

        amount_prec_v = self.get_parameter('amount_precision', 6)
        self.amount_precision = int(amount_prec_v) if amount_prec_v is not None else 6  # 下单数量精度

        # ── 参数校验 ──────────────────────────────────────
        if self.grid_spacing <= 0:
            raise ValueError('网格间距比例必须大于0')
        if self.grid_value <= 0:
            raise ValueError('网格交易价值必须大于0')
        if self.leverage <= 0:
            raise ValueError('杠杆倍数必须大于0')
        if self.upper_bound > 0 and self.lower_bound > 0 and self.lower_bound >= self.upper_bound:
            raise ValueError('价格下界必须小于上界')

        # ── 运行状态 ──────────────────────────────────────
        self.last_level: Optional[int] = None  # 上一次价格所处的网格档位
        self.net_position = 0.0                 # 净持仓（币，+多 / -空），用于风控估算
        self.last_price = 0.0
        self.grid_trades = 0                    # 网格触发次数

        logger.info(
            f"永续网格策略初始化: 单格价值={self.grid_value} USDT, "
            f"间距={self.grid_spacing:.2%}, 杠杆={self.leverage}x, "
            f"区间=[{self.lower_bound}, {self.upper_bound}]"
        )

    def on_initialize(self) -> None:
        """策略初始化：确定基准价与初始档位"""
        if self.base_price <= 0 and self.market_data:
            self.base_price = self.market_data[-1].close
            logger.info(f"未指定基准价，使用首个价格作为基准: {self.base_price}")

        if self.base_price > 0 and self.market_data:
            self.last_price = self.market_data[-1].close
            self.last_level = self._price_to_level(self.last_price)

    def _price_to_level(self, price: float) -> int:
        """
        将价格映射到网格档位（等比网格）

        网格线 k 位于 base_price * (1 + grid_spacing)^k
        档位 = floor( log(price/base_price) / log(1+grid_spacing) )
        """
        if price <= 0 or self.base_price <= 0:
            return 0
        return math.floor(math.log(price / self.base_price) / math.log(1 + self.grid_spacing))

    def _within_bounds(self, price: float) -> bool:
        """价格是否在允许交易区间内"""
        if self.upper_bound > 0 and price > self.upper_bound:
            return False
        if self.lower_bound > 0 and price < self.lower_bound:
            return False
        return True

    def on_market_data(self, data: MarketData) -> None:
        """处理市场数据：检测网格穿越并生成开/平仓信号"""
        if not self.running:
            return

        price = data.close
        if price <= 0:
            return

        # 首次拿到数据时初始化基准价与档位
        if self.base_price <= 0:
            self.base_price = price
            logger.info(f"运行中确定基准价: {self.base_price}")
        if self.last_level is None:
            self.last_level = self._price_to_level(price)
            self.last_price = price
            return

        current_level = self._price_to_level(price)

        # 无穿越，仅更新价格
        if current_level == self.last_level:
            self.last_price = price
            return

        # 价格区间保护：超出区间不再逆势加仓，但更新档位避免回到区间后重复触发
        if not self._within_bounds(price):
            logger.warning(f"价格 {price} 超出交易区间 [{self.lower_bound}, {self.upper_bound}]，跳过本次网格加仓")
            self.last_level = current_level
            self.last_price = price
            return

        crossed = current_level - self.last_level  # >0 上穿(做空), <0 下穿(做多)

        if crossed > 0:
            self._open_grid('SELL', crossed, price)
        elif crossed < 0:
            self._open_grid('BUY', -crossed, price)

        self.last_level = current_level
        self.last_price = price

    def _open_grid(self, direction: str, grids: int, price: float) -> None:
        """
        对穿越的每一格生成交易信号

        Args:
            direction: 'SELL'(做空) 或 'BUY'(做多)
            grids: 穿越的网格数
            price: 当前价格
        """
        # 本次交易总价值 = 穿越格数 × 单格价值
        total_value = grids * self.grid_value
        volume = round(total_value / price, self.amount_precision)
        if volume <= 0:
            return

        # 最大持仓价值保护：仅限制"逆势加仓"方向（继续放大净持仓的方向）
        if self.max_position_value > 0:
            signed = volume if direction == 'BUY' else -volume
            new_net = self.net_position + signed
            # 若新方向使净持仓绝对价值超限，且是在放大敞口，则跳过
            if abs(new_net) > abs(self.net_position) and abs(new_net) * price > self.max_position_value:
                logger.warning(
                    f"持仓价值将超过上限 {self.max_position_value} USDT，跳过 {direction} 加仓"
                )
                return

        reason = (
            f"网格{'做空' if direction == 'SELL' else '做多'}: "
            f"穿越{grids}格 @ {price:.4f}, 价值={total_value:.2f} USDT"
        )
        self.create_signal(direction=direction, strength=1.0, volume=volume, reason=reason)

        # 更新净持仓估算
        self.net_position += volume if direction == 'BUY' else -volume
        self.grid_trades += 1

    def get_performance(self) -> Dict[str, Any]:
        """获取策略性能"""
        base = super().get_performance()
        base.update({
            'base_price': self.base_price,
            'grid_spacing': self.grid_spacing,
            'grid_value': self.grid_value,
            'leverage': self.leverage,
            'net_position': self.net_position,
            'net_position_value': self.net_position * self.last_price,
            'grid_trades': self.grid_trades,
            'current_level': self.last_level,
        })
        return base

    def on_stop(self) -> None:
        """策略停止"""
        logger.info(f"永续网格策略停止，共触发 {self.grid_trades} 次网格交易，净持仓={self.net_position:.6f}")
