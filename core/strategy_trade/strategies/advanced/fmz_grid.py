"""
发明者量化网格交易策略
基于币种比例平衡的网格交易策略
维持固定的币/资金比例，通过买卖来平衡持仓
"""

from typing import Dict, List, Any, Optional
from datetime import datetime
import math

from ..base import StrategyBase
from ...base_strategy import MarketData, Signal
from utils.logger import get_logger

logger = get_logger(__name__)


class FMZGridStrategy(StrategyBase):
    """
    发明者量化网格交易策略
    
    策略原理：
    - 维持一个固定的币/资金比例（Ratio）
    - 当实际比例偏离目标比例时，通过买卖来平衡
    - 使用Grid_Ratio来设置网格密度
    - 根据当前持仓和资金计算买入/卖出价格和数量
    """
    
    def __init__(self, name: str, symbol: str, config: Dict[str, Any]):
        super().__init__(name, symbol, config)
        self.tick_level = True  # 逐 tick 报价：每次行情推送都触发
        
        # 策略参数（确保类型转换）
        ratio_value = self.get_parameter('ratio', 0.5)
        self.ratio = float(ratio_value) if ratio_value is not None else 0.5  # 目标币种比例（0-1之间）
        
        grid_ratio_value = self.get_parameter('grid_ratio', 0.01)
        self.grid_ratio = float(grid_ratio_value) if grid_ratio_value is not None else 0.01  # 网格密度（1%）
        
        self.min_grid_ratio = 0.0005  # 最小网格密度（万分之5）
        
        interval_value = self.get_parameter('interval', 1000)
        self.interval = int(interval_value) if interval_value is not None else 1000  # 更新间隔（毫秒）
        
        # 验证参数
        if self.grid_ratio < self.min_grid_ratio:
            raise ValueError(f'网格密度勿小于万分之5（{self.min_grid_ratio}）')
        
        if not 0 < self.ratio < 1:
            raise ValueError('目标比例必须在0-1之间')
        
        # 订单状态
        self.buy_order = {
            'price': 0.0,
            'amount': 0.0,
            'order_id': None,
            'active': False
        }
        
        self.sell_order = {
            'price': 0.0,
            'amount': 0.0,
            'order_id': None,
            'active': False
        }
        
        # 账户状态（需要从交易所获取）
        self.account = {
            'balance': 0.0,  # 资金余额
            'frozen_balance': 0.0,  # 冻结资金
            'stocks': 0.0,  # 币种数量
            'frozen_stocks': 0.0  # 冻结币种数量
        }
        
        # 初始值记录（用于收益计算）
        self.init_value = self.get_parameter('init_value', None)
        self.init_account = self.get_parameter('init_account', None)
        
        # 统计信息
        self.last_price = 0.0
        self.total_trade_volume = 0.0
        self.log_profit_time = 0
        self.update_status_time = 0
        
        # 精度设置（确保类型转换）
        price_precision_value = self.get_parameter('price_precision', 2)
        self.price_precision = int(price_precision_value) if price_precision_value is not None else 2
        
        amount_precision_value = self.get_parameter('amount_precision', 6)
        self.amount_precision = int(amount_precision_value) if amount_precision_value is not None else 6
        
        logger.info(f"发明者网格策略初始化: 目标比例={self.ratio:.2%}, 网格密度={self.grid_ratio:.2%}")
    
    def on_initialize(self) -> None:
        """策略初始化"""
        # 取消所有现有订单
        self._cancel_all_orders()

        # 获取初始账户信息
        self._update_account()

        # 获取初始价格
        if self.market_data and len(self.market_data) > 0:
            self.last_price = self.market_data[-1].close
            logger.info(f"✅ 策略初始化成功，当前价格: {self.last_price}，历史数据: {len(self.market_data)} 根K线")
        else:
            logger.warning("⚠️ 没有市场数据，无法获取初始价格。策略将在接收到第一根K线后初始化。")
            return

        # 初始化初始值
        if self.init_value is None or self.init_account is None:
            if self.last_price > 0:
                self._init_values()
    
    def _init_values(self) -> None:
        """初始化初始值和账户"""
        total_stocks = self.account['stocks'] + self.account['frozen_stocks']
        total_balance = self.account['balance'] + self.account['frozen_balance']
        self.init_value = round(total_balance + total_stocks * self.last_price, 6)
        self.init_account = {
            'balance': total_balance,
            'amount': total_stocks
        }
        logger.info(f"第一次启动策略, 初始总价值为: {self.init_value}")
    
    def on_market_data(self, data: MarketData) -> None:
        """处理市场数据"""
        if not self.running:
            return
        
        # 更新价格
        self.last_price = data.close
        
        # 更新账户信息
        self._update_account()
        
        # 执行交易逻辑
        self._on_tick()
        
        # 更新状态
        self._update_status()
    
    def _update_account(self) -> None:
        """
        更新账户信息
        
        注意：这个方法需要从实际交易所API获取账户信息
        这里提供框架，实际使用时需要注入exchange_client
        """
        # TODO: 从交易所API获取账户信息
        # account = self.exchange_client.get_account(self.symbol)
        # if account:
        #     old_stocks = self.account['stocks'] + self.account['frozen_stocks']
        #     self.account.update(account)
        #     new_stocks = self.account['stocks'] + self.account['frozen_stocks']
        #     
        #     # 记录成交
        #     if abs(new_stocks - old_stocks) > 0.000001:
        #         diff = new_stocks - old_stocks
        #         if diff > 0:
        #             logger.info(f"买单成交: {diff:.6f}, 数量变动: {old_stocks:.6f} -> {new_stocks:.6f}")
        #         else:
        #             logger.info(f"卖单成交: {abs(diff):.6f}, 数量变动: {old_stocks:.6f} -> {new_stocks:.6f}")
        #         self.total_trade_volume += abs(diff)
        
        pass
    
    def _on_tick(self) -> None:
        """执行交易逻辑（对应原代码的onTick函数）"""
        if self.last_price == 0:
            return
        
        # 计算当前币种和资金
        m = self.account['stocks'] + self.account['frozen_stocks']  # 币种数量
        b = self.account['balance'] + self.account['frozen_balance']  # 资金余额
        
        # 计算当前比例
        total_value = m * self.last_price + b
        if total_value == 0:
            return
        
        r = (m * self.last_price) / total_value
        
        # 检查比例是否偏离过大（需要手动调整）
        # 在回测环境中，允许自动调整，只记录警告
        # 在实盘环境中，如果偏离过大则需要手动调整以避免冲击市场
        is_backtest = self.get_parameter('is_backtest', False)  # 从配置中获取是否回测
        
        if abs(r - self.ratio) > 0.3 * self.ratio:
            if is_backtest:
                # 回测环境：记录警告，允许继续运行
                logger.warning(f'当前比例 {r:.2%} 偏离目标比例 {self.ratio:.2%} 较大（>{0.3*self.ratio:.2%}），但在回测环境中允许自动调整')
            else:
                # 实盘环境：抛出错误，需要手动调整
                raise ValueError('为避免冲击市场，需要手动交易到持仓比例附近，再由策略进行交易')
        
        # 计算目标比例
        buy_r = self.ratio - self.grid_ratio  # 买入目标比例
        sell_r = self.ratio + self.grid_ratio  # 卖出目标比例
        
        # 特殊处理：初始状态（m=0，没有持仓）
        if m == 0:
            # 初始状态：直接使用当前市场价格买入，计算达到目标比例需要买入的数量
            # 目标：币种价值 / 总价值 = ratio
            # (amount * price) / (b - amount * price + amount * price) = ratio
            # amount * price / b = ratio
            # amount = ratio * b / price
            # 但我们要分批买入，只买入一部分来接近目标
            buy_price = self.last_price  # 使用当前市场价格
            # 计算目标币种价值
            target_stock_value = total_value * self.ratio
            # 分批买入：每次买入网格比例的量
            buy_value = total_value * self.grid_ratio
            buy_price = self.last_price  # 直接用当前价格
        else:
            # 正常情况：计算买入价格
            # buy_r = m * buy_price / (m * buy_price + b)
            # buy_r * (m * buy_price + b) = m * buy_price
            # buy_r * b = buy_price * (m - buy_r * m)
            # buy_price = buy_r * b / (m * (1 - buy_r))
            if m * (1 - buy_r) > 0:
                buy_price = round((b * buy_r) / (m * (1 - buy_r)), self.price_precision)
            else:
                buy_price = 0
            
            # 计算买入价值
            buy_value = (m * buy_price + b) * self.grid_ratio
        
        # 计算卖出价格
        if m > 0 and m * (1 - sell_r) > 0:
            # sell_r = m * sell_price / (m * sell_price + b)
            # sell_r * b = sell_price * (m - sell_r * m)
            sell_price = round((b * sell_r) / (m * (1 - sell_r)), self.price_precision)
            # 计算卖出价值
            sell_value = (m * sell_price + b) * self.grid_ratio
        else:
            sell_price = 0
            sell_value = 0
        
        # 执行交易
        self._trade('buy', buy_price, buy_value, '买入平衡')
        self._trade('sell', sell_price, sell_value, '卖出平衡')
    
    def _trade(self, direction: str, price: float, value: float, msg: str) -> None:
        """执行交易（对应原代码的trade函数）"""
        if price <= 0:
            return
        
        # 计算数量
        amount = round(value / price, self.amount_precision)
        
        # 判断是否需要新建订单
        new_order = False
        order = self.buy_order if direction == 'buy' else self.sell_order
        
        # 如果没有订单，需要新建
        if not order['order_id']:
            new_order = True
        
        # 如果价格变化超过网格比例的10%，需要新建订单
        if order['price'] > 0 and abs(price - order['price']) / order['price'] > self.grid_ratio / 10.0:
            new_order = True
        
        # 如果有足够资金/币种，需要新建订单
        if direction == 'buy':
            if (self.account['frozen_balance'] == 0 and 
                self.account['balance'] > 1.5 * value):
                new_order = True
        else:  # sell
            if (self.account['frozen_stocks'] == 0 and 
                self.account['stocks'] > 1.5 * amount):
                new_order = True
        
        # 更新订单价格
        order['price'] = price
        
        # 如果需要新建订单
        if new_order:
            # 取消旧订单
            if order['order_id']:
                self._cancel_order(order['order_id'])
                order['order_id'] = None
                order['price'] = 0.0
            
            # 创建新订单
            order_id = None
            if direction == 'buy':
                if self.account['balance'] < 1.5 * value:
                    logger.warning('资金不足, 无法挂买单')
                else:
                    # 创建买入信号
                    self.create_signal(
                        direction='BUY',
                        strength=1.0,
                        volume=amount,
                        reason=f"{msg}: 价格={price:.2f}, 数量={amount:.6f}"
                    )
                    order_id = f"buy_{int(datetime.now().timestamp() * 1000)}"  # 模拟订单ID
            
            else:  # sell
                if self.account['stocks'] < 1.5 * amount:
                    logger.warning('余币不足, 无法挂卖单')
                else:
                    # 创建卖出信号
                    self.create_signal(
                        direction='SELL',
                        strength=1.0,
                        volume=amount,
                        reason=f"{msg}: 价格={price:.2f}, 数量={amount:.6f}"
                    )
                    order_id = f"sell_{int(datetime.now().timestamp() * 1000)}"  # 模拟订单ID
            
            order['order_id'] = order_id
            order['price'] = price
            order['amount'] = amount
            order['active'] = True
    
    def _cancel_order(self, order_id: str) -> None:
        """取消订单"""
        # TODO: 从交易所API取消订单
        # self.exchange_client.cancel_order(order_id)
        logger.debug(f"取消订单: {order_id}")
    
    def _cancel_all_orders(self) -> None:
        """取消所有订单"""
        logger.info('撤销所有订单')
        # TODO: 从交易所API获取并取消所有订单
        # orders = self.exchange_client.get_orders(self.symbol)
        # for order in orders:
        #     self.exchange_client.cancel_order(order['id'])
        
        self.buy_order['order_id'] = None
        self.buy_order['active'] = False
        self.sell_order['order_id'] = None
        self.sell_order['active'] = False
    
    def _update_status(self) -> None:
        """更新状态（对应原代码的updateStatus函数）"""
        current_time = datetime.now().timestamp() * 1000
        
        # 限制更新频率（4秒）
        if current_time - self.update_status_time < 4000:
            return
        
        self.update_status_time = current_time
        
        # 计算当前价值
        m = self.account['stocks'] + self.account['frozen_stocks']
        b = self.account['balance'] + self.account['frozen_balance']
        now_value = m * self.last_price + b
        
        # 计算收益
        if self.init_account and self.last_price > 0:
            profit = round(
                now_value - self.init_account['amount'] * self.last_price - self.init_account['balance'],
                6
            )
        else:
            profit = 0.0
        
        # 计算当前比例
        current_ratio = (m * self.last_price / now_value) if now_value > 0 else 0
        
        # 生成状态信息（可以用于日志或API返回）
        status = {
            'initial_stocks': round(self.init_account['amount'], 6) if self.init_account else 0,
            'initial_balance': round(self.init_account['balance'], 6) if self.init_account else 0,
            'current_stocks': round(m, 6),
            'current_balance': round(b, 6),
            'current_ratio': round(current_ratio, 6),
            'current_price': round(self.last_price, 6),
            'initial_value': round(self.init_value, 6) if self.init_value else 0,
            'current_value': round(now_value, 6),
            'total_trade_volume': round(self.total_trade_volume, 4),
            'profit': profit,
            'buy_order': {
                'price': self.buy_order['price'],
                'amount': self.buy_order['amount'],
                'active': self.buy_order['active']
            },
            'sell_order': {
                'price': self.sell_order['price'],
                'amount': self.sell_order['amount'],
                'active': self.sell_order['active']
            }
        }
        
        logger.info(f"策略状态: 当前价值={now_value:.2f}, 收益={profit:.2f}, 当前比例={current_ratio:.2%}")
        
        # 记录收益（如果是实盘，按Log_profit间隔记录）
        # 回测模式下可以设置更短的间隔
        log_profit_interval = 24 * 60 * 60 * 1000  # 24小时
        if current_time - self.log_profit_time > log_profit_interval:
            self.log_profit_time = current_time
            logger.info(f"记录收益: {profit:.6f}")
    
    def get_performance(self) -> Dict[str, Any]:
        """获取策略性能"""
        base_performance = super().get_performance()
        
        m = self.account['stocks'] + self.account['frozen_stocks']
        b = self.account['balance'] + self.account['frozen_balance']
        now_value = m * self.last_price + b if self.last_price > 0 else 0
        
        performance = {
            **base_performance,
            'current_value': now_value,
            'initial_value': self.init_value if self.init_value else 0,
            'total_profit': (now_value - self.init_value) if self.init_value else 0,
            'total_trade_volume': self.total_trade_volume,
            'current_ratio': (m * self.last_price / now_value) if now_value > 0 else 0,
            'target_ratio': self.ratio,
            'buy_order': self.buy_order.copy(),
            'sell_order': self.sell_order.copy()
        }
        
        return performance
    
    def on_stop(self) -> None:
        """策略停止时取消所有订单"""
        self._cancel_all_orders()
        logger.info("策略停止，已取消所有订单")

