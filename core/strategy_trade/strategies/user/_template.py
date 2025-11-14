"""
用户策略模板示例
复制此文件并修改即可创建自己的策略
"""

from typing import Dict, Any
from datetime import datetime

from ...base_strategy import BaseStrategy, MarketData, Signal
from utils.logger import get_logger

logger = get_logger(__name__)


class MyCustomStrategy(BaseStrategy):
    """
    自定义策略示例
    
    说明：
    - 必须继承BaseStrategy
    - 必须实现on_market_data方法
    - 使用self.create_signal()创建交易信号
    """
    
    def __init__(self, name: str, symbol: str, config: Dict[str, Any]):
        super().__init__(name, symbol, config)
        
        # 从配置中获取参数
        self.param1 = self.get_parameter('param1', 10)
        self.param2 = self.get_parameter('param2', 0.5)
        
        logger.info(f"自定义策略初始化: {name}, param1={self.param1}, param2={self.param2}")
    
    def on_market_data(self, data: MarketData) -> None:
        """
        处理市场数据（必须实现）
        
        在此方法中实现你的策略逻辑
        """
        current_price = data.close
        
        # 获取价格数据
        prices = self.get_price_data(length=20)  # 获取最近20个价格
        
        if len(prices) < 20:
            return  # 数据不足，等待更多数据
        
        # 示例策略逻辑：简单的移动平均策略
        ma_short = sum(prices[-5:]) / 5  # 5日均线
        ma_long = sum(prices[-20:]) / 20  # 20日均线
        
        # 生成买入信号
        if ma_short > ma_long and prices[-1] > ma_short:
            self.create_signal(
                direction='BUY',
                price=current_price,
                volume=self.param2,  # 使用配置中的参数
                strength=0.8,
                reason=f"短期均线上穿长期均线: {ma_short:.2f} > {ma_long:.2f}"
            )
        
        # 生成卖出信号
        elif ma_short < ma_long and prices[-1] < ma_short:
            self.create_signal(
                direction='SELL',
                price=current_price,
                volume=self.param2,
                strength=0.8,
                reason=f"短期均线下穿长期均线: {ma_short:.2f} < {ma_long:.2f}"
            )
    
    def on_initialize(self) -> None:
        """策略初始化时的额外操作（可选）"""
        logger.info(f"策略 {self.name} 初始化完成")
    
    def on_start(self) -> None:
        """策略启动时的操作（可选）"""
        logger.info(f"策略 {self.name} 已启动")
    
    def on_stop(self) -> None:
        """策略停止时的操作（可选）"""
        logger.info(f"策略 {self.name} 已停止")

