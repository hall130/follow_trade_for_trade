"""
Avellaneda-Stoikov 被动做市策略模块

基于论文 "High-frequency Trading in a Limit Order Book" 实现
特性：
- 保留价格（Reservation Price）计算，根据库存偏离目标动态调整
- 最优价差（Optimal Spread）计算，基于波动率、流动性和风险因子
- 订单大小动态调整（eta参数）
- 自动将交易费计入价差
- 目标库存=0（中性做市）
"""
from __future__ import annotations

import math
import time
from collections import deque
from datetime import datetime
from typing import Dict, List, Optional, Tuple, Any

from logger import setup_logger
from strategies.perp_market_maker import PerpetualMarketMaker, format_balance
from utils.helpers import round_to_precision, round_to_tick_size

logger = setup_logger("avellaneda_stoikov")


class AvellanedaStoikovStrategy(PerpetualMarketMaker):
    """
    Avellaneda-Stoikov 被动做市策略
    
    核心参数：
    - risk_factor (gamma): 风险厌恶系数，控制保留价格和最优价差的敏感度
    - reservation_price: 保留价格，根据库存偏离目标计算
    - optimal_spread: 最优价差，基于波动率、流动性和时间
    - inventory_target: 目标库存（通常为0，中性做市）
    - order_amount_shape_factor (eta): 订单大小调整因子
    - volatility_buffer_size: 波动率缓冲区大小
    - trading_intensity_buffer_size: 交易强度缓冲区大小
    - add_transaction_costs: 是否将交易费计入价差
    """

    def __init__(
        self,
        api_key: str,
        secret_key: str,
        symbol: str,
        # Avellaneda-Stoikov 核心参数
        risk_factor: float = 1.0,  # gamma，风险厌恶系数
        inventory_target: float = 0.0,  # 目标库存（中性）
        order_amount_shape_factor: float = 1.0,  # eta，订单大小调整因子
        volatility_buffer_size: int = 200,  # 波动率缓冲区大小
        trading_intensity_buffer_size: int = 200,  # 交易强度缓冲区大小
        add_transaction_costs: bool = True,  # 是否将交易费计入价差
        min_spread: float = 0.0,  # 最小价差（作为硬限制）
        # 交易费（用于计算保留价格和价差）
        maker_fee: float = 0.0,  # Maker手续费率（如0.001 = 0.1%）
        taker_fee: float = 0.0,  # Taker手续费率（如0.001 = 0.1%）
        # 其他参数
        ws_proxy: Optional[str] = None,
        exchange: str = 'backpack',
        exchange_config: Optional[Dict[str, Any]] = None,
        **kwargs,
    ) -> None:
        """
        初始化 Avellaneda-Stoikov 策略
        
        Args:
            risk_factor: 风险厌恶系数（gamma），控制保留价格和最优价差的敏感度
                        - 接近0：更对称的订单，保留价格接近中间价，库存风险较高
                        - 较高值：更激进地追求目标库存，保留价格远离中间价
                        - 常见值：1-20，可以更高
            inventory_target: 目标库存（通常为0，中性做市）
            order_amount_shape_factor: 订单大小调整因子（eta）
                                     - 1.0：买卖订单大小相同
                                     - >1.0：不对称订单大小，更快达到目标库存
            volatility_buffer_size: 波动率缓冲区大小（用于计算瞬时波动率）
            trading_intensity_buffer_size: 交易强度缓冲区大小（用于估计订单簿流动性）
            add_transaction_costs: 是否自动将交易费计入价差
            min_spread: 最小价差（作为硬限制，防止订单过近）
            maker_fee: Maker手续费率（如0.001 = 0.1%）
            taker_fee: Taker手续费率（如0.001 = 0.1%）
        """
        # 确保目标库存为0（中性做市）
        kwargs.setdefault("target_position", inventory_target)
        kwargs.setdefault("enable_rebalance", False)  # 通过报价调整而非主动平仓
        
        super().__init__(
            api_key=api_key,
            secret_key=secret_key,
            symbol=symbol,
            ws_proxy=ws_proxy,
            exchange=exchange,
            exchange_config=exchange_config,
            **kwargs,
        )
        
        # Avellaneda-Stoikov 核心参数
        self.risk_factor = max(0.001, risk_factor)  # 避免除零
        self.inventory_target = inventory_target
        self.order_amount_shape_factor = order_amount_shape_factor
        self.add_transaction_costs = add_transaction_costs
        self.min_spread = min_spread
        self.maker_fee = maker_fee
        self.taker_fee = taker_fee
        
        # 波动率和流动性估计缓冲区
        self.volatility_buffer_size = volatility_buffer_size
        self.trading_intensity_buffer_size = trading_intensity_buffer_size
        
        # 价格变化历史（用于计算波动率）
        self.price_changes: deque = deque(maxlen=volatility_buffer_size)
        self.last_price: Optional[float] = None
        self.last_price_time: Optional[float] = None
        
        # 订单簿变化历史（用于估计交易强度）
        self.orderbook_snapshots: deque = deque(maxlen=trading_intensity_buffer_size)
        self.last_orderbook_time: Optional[float] = None
        
        # 估计的参数（alpha, kappa）
        self.alpha: Optional[float] = None  # 交易强度参数
        self.kappa: Optional[float] = None  # 订单簿流动性参数
        self.volatility: Optional[float] = None  # 瞬时波动率
        
        # 时间框架（默认为无限）
        self.timeframe = "infinite"
        self.session_start_time: Optional[float] = None
        self.session_end_time: Optional[float] = None
        
        logger.info(
            "初始化 Avellaneda-Stoikov 策略: %s | 风险因子: %.2f | 目标库存: %.3f | "
            "订单大小因子: %.2f | 最小价差: %.4f%%",
            symbol,
            self.risk_factor,
            self.inventory_target,
            self.order_amount_shape_factor,
            self.min_spread,
        )
        
        if self.add_transaction_costs:
            logger.info(
                "交易费已计入价差: Maker=%.4f%% | Taker=%.4f%%",
                self.maker_fee * 100,
                self.taker_fee * 100,
            )

    def _update_price_history(self, current_price: float) -> None:
        """更新价格历史，用于计算波动率"""
        current_time = time.time()
        
        if self.last_price is not None:
            # 计算价格变化
            price_change = abs(current_price - self.last_price) / self.last_price if self.last_price > 0 else 0
            time_delta = current_time - self.last_price_time if self.last_price_time else 1.0
            
            if time_delta > 0:
                # 标准化价格变化（按时间）
                normalized_change = price_change / math.sqrt(time_delta)
                self.price_changes.append(normalized_change)
        
        self.last_price = current_price
        self.last_price_time = current_time

    def _calculate_volatility(self) -> Optional[float]:
        """计算瞬时波动率"""
        if len(self.price_changes) < 10:  # 至少需要10个数据点
            return None
        
        # 计算价格变化的均值和标准差
        changes = list(self.price_changes)
        mean_change = sum(changes) / len(changes)
        variance = sum((x - mean_change) ** 2 for x in changes) / len(changes)
        
        # 波动率 = 标准差
        volatility = math.sqrt(variance)
        return volatility

    def _update_orderbook_history(self, orderbook: Dict[str, Any]) -> None:
        """更新订单簿历史，用于估计交易强度"""
        current_time = time.time()
        
        # 检查订单簿是否变化
        if orderbook and 'bids' in orderbook and 'asks' in orderbook:
            if orderbook['bids'] and orderbook['asks']:
                best_bid = float(orderbook['bids'][0][0])
                best_ask = float(orderbook['asks'][0][0])
                
                # 只有当订单簿价格变化时才记录
                if self.last_orderbook_time is None or current_time - self.last_orderbook_time > 0.1:
                    self.orderbook_snapshots.append({
                        'time': current_time,
                        'bid': best_bid,
                        'ask': best_ask,
                        'mid': (best_bid + best_ask) / 2,
                        'spread': best_ask - best_bid,
                    })
                    self.last_orderbook_time = current_time

    def _estimate_trading_intensity(self) -> Tuple[Optional[float], Optional[float]]:
        """
        估计交易强度参数（alpha, kappa）
        
        返回:
            (alpha, kappa) - 交易强度参数和订单簿流动性参数
        """
        if len(self.orderbook_snapshots) < 20:  # 至少需要20个快照
            return None, None
        
        # 简化的估计方法：基于订单簿价差和变化频率
        snapshots = list(self.orderbook_snapshots)
        
        # 计算平均价差
        spreads = [s['spread'] for s in snapshots if s['spread'] > 0]
        if not spreads:
            return None, None
        
        avg_spread = sum(spreads) / len(spreads)
        avg_mid = sum(s['mid'] for s in snapshots) / len(snapshots)
        
        # 简化的alpha和kappa估计
        # alpha: 与价差成反比（价差越小，交易强度越高）
        # kappa: 与价差成正比（价差越大，流动性越低）
        if avg_mid > 0:
            alpha = 1.0 / (avg_spread / avg_mid + 0.001)  # 避免除零
            kappa = avg_spread / avg_mid
        else:
            return None, None
        
        return alpha, kappa

    def _calculate_reservation_price(
        self, 
        mid_price: float, 
        inventory: float,
        volatility: float,
        time_to_end: Optional[float] = None,
    ) -> float:
        """
        计算保留价格（Reservation Price）
        
        保留价格 = 中间价 - (风险因子 * 波动率^2 * 库存偏离)
        
        Args:
            mid_price: 市场中间价
            inventory: 当前库存（净持仓）
            volatility: 瞬时波动率
            time_to_end: 距离交易结束的时间（None表示无限时间框架）
            
        Returns:
            保留价格
        """
        # 库存偏离目标
        inventory_deviation = inventory - self.inventory_target
        
        # 对于无限时间框架，不使用时间因子
        if time_to_end is None or self.timeframe == "infinite":
            # 无限时间框架的保留价格公式
            reservation_price = mid_price - (self.risk_factor * volatility ** 2 * inventory_deviation)
        else:
            # 有限时间框架的保留价格公式（考虑时间因子）
            time_factor = 1.0 / (1.0 + time_to_end) if time_to_end > 0 else 1.0
            reservation_price = mid_price - (self.risk_factor * volatility ** 2 * inventory_deviation * time_factor)
        
        return reservation_price

    def _calculate_optimal_spread(
        self,
        reservation_price: float,
        volatility: float,
        alpha: Optional[float],
        kappa: Optional[float],
        time_to_end: Optional[float] = None,
    ) -> Tuple[float, float]:
        """
        计算最优价差（Optimal Spread）
        
        最优价差 = (风险因子 * 波动率^2) + (2 / kappa) * ln(1 + kappa / alpha)
        
        Args:
            reservation_price: 保留价格
            volatility: 瞬时波动率
            alpha: 交易强度参数
            kappa: 订单簿流动性参数
            time_to_end: 距离交易结束的时间（None表示无限时间框架）
            
        Returns:
            (最优买价差, 最优卖价差) - 相对于保留价格的价差
        """
        # 基础价差 = 风险因子 * 波动率^2
        base_spread = self.risk_factor * volatility ** 2
        
        # 如果alpha和kappa可用，添加流动性调整
        if alpha is not None and kappa is not None and alpha > 0 and kappa > 0:
            # 流动性调整项
            liquidity_adjustment = (2.0 / kappa) * math.log(1.0 + kappa / alpha)
            optimal_spread = base_spread + liquidity_adjustment
        else:
            # 如果没有流动性参数，只使用基础价差
            optimal_spread = base_spread
        
        # 时间因子（对于有限时间框架）
        if time_to_end is not None and self.timeframe != "infinite" and time_to_end > 0:
            time_factor = 1.0 / (1.0 + time_to_end)
            optimal_spread = optimal_spread * time_factor
        
        # 应用最小价差限制
        min_spread_absolute = reservation_price * (self.min_spread / 100.0) if self.min_spread > 0 else 0
        optimal_spread = max(optimal_spread, min_spread_absolute)
        
        # 计算买卖价差（相对于保留价格）
        half_spread = optimal_spread / 2.0
        
        # 如果开启了交易费，将费用计入价差
        if self.add_transaction_costs:
            # 费用调整：买入时支付maker费，卖出时支付maker费
            # 实际价差需要补偿这些费用
            fee_adjustment = reservation_price * (self.maker_fee + self.taker_fee) / 2.0
            half_spread = half_spread + fee_adjustment
        
        return half_spread, half_spread

    def calculate_prices(self) -> Tuple[List[float], List[float]]:
        """
        计算买卖订单价格（基于Avellaneda-Stoikov模型）
        
        Returns:
            (buy_prices, sell_prices) - 买卖价格列表
        """
        try:
            # 获取市场数据
            bid_price, ask_price = self.get_market_depth()
            if bid_price is None or ask_price is None:
                current_price = self.get_current_price()
                if current_price is None:
                    logger.error("无法获取价格信息，无法设置订单")
                    return [], []
                mid_price = current_price
            else:
                mid_price = (bid_price + ask_price) / 2.0
            
            # 更新价格历史
            self._update_price_history(mid_price)
            
            # 获取订单簿
            orderbook = self.client.get_order_book(self.symbol)
            if orderbook:
                self._update_orderbook_history(orderbook)
            
            # 计算波动率
            volatility = self._calculate_volatility()
            if volatility is None:
                # 如果波动率不可用，使用默认值
                volatility = 0.001  # 0.1%的默认波动率
                logger.warning("波动率估计不可用，使用默认值: %.4f", volatility)
            
            # 估计交易强度参数
            self.alpha, self.kappa = self._estimate_trading_intensity()
            if self.alpha is None or self.kappa is None:
                logger.warning("交易强度参数估计不可用，使用简化计算")
            
            # 获取当前库存
            inventory = self.get_net_position()
            
            # 计算时间因子（对于有限时间框架）
            time_to_end = None
            if self.timeframe != "infinite" and self.session_end_time:
                current_time = time.time()
                time_to_end = max(0, self.session_end_time - current_time)
            
            # 计算保留价格
            reservation_price = self._calculate_reservation_price(
                mid_price=mid_price,
                inventory=inventory,
                volatility=volatility,
                time_to_end=time_to_end,
            )
            
            # 计算最优价差
            buy_half_spread, sell_half_spread = self._calculate_optimal_spread(
                reservation_price=reservation_price,
                volatility=volatility,
                alpha=self.alpha,
                kappa=self.kappa,
                time_to_end=time_to_end,
            )
            
            # 计算最优买卖价格
            optimal_bid_price = reservation_price - buy_half_spread
            optimal_ask_price = reservation_price + sell_half_spread
            
            # 确保价格合理（不能为负）
            if optimal_bid_price <= 0 or optimal_ask_price <= 0:
                logger.error("计算出的价格无效: bid=%.4f, ask=%.4f", optimal_bid_price, optimal_ask_price)
                # 回退到简单的中间价计算
                return super().calculate_prices()
            
            # 确保买卖价差合理
            if optimal_ask_price <= optimal_bid_price:
                optimal_ask_price = optimal_bid_price + self.tick_size
                logger.warning("价差过小，调整卖价为: %.4f", optimal_ask_price)
            
            # 四舍五入到tick size
            optimal_bid_price = round_to_tick_size(optimal_bid_price, self.tick_size)
            optimal_ask_price = round_to_tick_size(optimal_ask_price, self.tick_size)
            
            # 记录计算结果
            logger.info("=== Avellaneda-Stoikov 价格计算 ===")
            logger.info("市场中间价: %.4f", mid_price)
            logger.info("保留价格: %.4f (偏移: %.4f%%)", 
                       reservation_price, 
                       (reservation_price - mid_price) / mid_price * 100)
            logger.info("当前库存: %.4f (目标: %.4f)", inventory, self.inventory_target)
            logger.info("瞬时波动率: %.6f", volatility)
            if self.alpha and self.kappa:
                logger.info("交易强度参数: alpha=%.4f, kappa=%.6f", self.alpha, self.kappa)
            logger.info("最优买价: %.4f | 最优卖价: %.4f", optimal_bid_price, optimal_ask_price)
            logger.info("价差: %.4f (%.4f%%)", 
                       optimal_ask_price - optimal_bid_price,
                       (optimal_ask_price - optimal_bid_price) / mid_price * 100)
            
            # 生成多级订单价格（如果有max_orders > 1）
            buy_prices = [optimal_bid_price]
            sell_prices = [optimal_ask_price]
            
            if self.max_orders > 1:
                # 计算层间距（基于最优价差的百分比）
                level_distance_pct = 0.1  # 默认10%的价差
                level_spread = (optimal_ask_price - optimal_bid_price) * level_distance_pct
                
                for i in range(1, self.max_orders):
                    buy_price = optimal_bid_price - (i * level_spread)
                    sell_price = optimal_ask_price + (i * level_spread)
                    
                    # 确保价格合理
                    if buy_price > 0:
                        buy_prices.append(round_to_tick_size(buy_price, self.tick_size))
                    if sell_price > optimal_ask_price:
                        sell_prices.append(round_to_tick_size(sell_price, self.tick_size))
            
            return buy_prices, sell_prices
            
        except Exception as e:
            logger.error(f"计算价格时出错: {e}", exc_info=True)
            # 回退到父类方法
            return super().calculate_prices()

    def _calculate_order_sizes(self, buy_price: float, sell_price: float) -> Tuple[float, float]:
        """
        计算订单大小（基于eta参数）
        
        如果eta != 1.0，会根据库存偏离调整订单大小
        """
        base_quantity = self.order_quantity or self.min_order_size
        
        if self.order_amount_shape_factor == 1.0:
            # eta = 1.0，买卖订单大小相同
            return base_quantity, base_quantity
        
        # 计算库存偏离
        inventory = self.get_net_position()
        inventory_deviation = inventory - self.inventory_target
        
        # 根据库存偏离调整订单大小
        # 如果库存过多，减少买入订单，增加卖出订单
        # 如果库存不足，增加买入订单，减少卖出订单
        
        if inventory_deviation > 0:
            # 库存过多，需要卖出
            buy_size = base_quantity / (1.0 + self.order_amount_shape_factor * abs(inventory_deviation))
            sell_size = base_quantity * (1.0 + self.order_amount_shape_factor * abs(inventory_deviation))
        elif inventory_deviation < 0:
            # 库存不足，需要买入
            buy_size = base_quantity * (1.0 + self.order_amount_shape_factor * abs(inventory_deviation))
            sell_size = base_quantity / (1.0 + self.order_amount_shape_factor * abs(inventory_deviation))
        else:
            # 库存平衡
            buy_size = base_quantity
            sell_size = base_quantity
        
        # 确保订单大小不小于最小订单量
        buy_size = max(buy_size, self.min_order_size)
        sell_size = max(sell_size, self.min_order_size)
        
        return buy_size, sell_size

