"""
策略配置管理模块
统一管理所有策略的配置模板、参数验证和配置持久化
"""

import json
import os
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime
from dataclasses import dataclass
from utils.logger import get_logger

logger = get_logger(__name__)

@dataclass
class StrategyTemplate:
    """策略模板配置"""
    name: str
    display_name: str
    description: str
    category: str
    default_config: Dict[str, Any]
    required_fields: List[str] = None
    validation_rules: Dict[str, Any] = None
    risk_profile: str = "MEDIUM"  # LOW, MEDIUM, HIGH
    complexity: str = "INTERMEDIATE"  # BEGINNER, INTERMEDIATE, ADVANCED
    
    def __post_init__(self):
        if self.required_fields is None:
            self.required_fields = []
        if self.validation_rules is None:
            self.validation_rules = {}

class StrategyConfigManager:
    """策略配置管理器"""
    
    def __init__(self, config_dir: str = "config/strategy_configs"):
        self.config_dir = config_dir
        self.templates = {}
        self.ensure_config_dir()
        self._load_default_templates()
    
    def ensure_config_dir(self):
        """确保配置目录存在"""
        if not os.path.exists(self.config_dir):
            os.makedirs(self.config_dir)
    
    def _load_default_templates(self):
        """加载默认策略模板"""
        
        # 移动平均交叉策略模板
        self.templates["MA_Cross_Strategy"] = StrategyTemplate(
            name="MA_Cross_Strategy",
            display_name="移动平均交叉策略",
            description="基于短期和长期移动平均线交叉的经典趋势跟踪策略，适合捕捉中长期趋势",
            category="趋势跟踪",
            risk_profile="MEDIUM",
            complexity="INTERMEDIATE",
            required_fields=["symbol", "timeframe", "short_period", "long_period"],
            validation_rules={
                "short_period": {"min": 5, "max": 50, "type": "int"},
                "long_period": {"min": 10, "max": 200, "type": "int"},
                "risk_per_trade": {"min": 0.01, "max": 0.1, "type": "float"},
                "stop_loss_pct": {"min": 0.005, "max": 0.1, "type": "float"},
                "take_profit_pct": {"min": 0.01, "max": 0.5, "type": "float"}
            },
            default_config={
                # 基础参数
                "symbol": "BTC-USDT",
                "timeframe": "1h",
                "risk_per_trade": 0.02,
                "max_positions": 3,
                "position_sizing": "fixed",
                
                # 移动平均参数
                "short_period": 10,
                "long_period": 20,
                "ema_period": 12,
                
                # 信号过滤参数
                "min_volume_ratio": 1.2,
                "min_price_change": 0.005,
                "rsi_period": 14,
                "rsi_oversold": 30,
                "rsi_overbought": 70,
                
                # 趋势确认参数
                "adx_period": 14,
                "adx_threshold": 25,
                "atr_period": 14,
                "volatility_threshold": 0.02,
                
                # 止损止盈参数
                "stop_loss_pct": 0.02,
                "take_profit_pct": 0.06,
                "trailing_stop": True,
                "trailing_stop_pct": 0.01,
                
                # 风险管理
                "risk_config": {
                    "max_daily_loss": 0.05,
                    "max_position_size": 0.1,
                    "max_drawdown": 0.2,
                    "max_leverage": 1.0,
                    "max_concentration": 0.3
                }
            }
        )
        
        # 高频交易策略模板
        self.templates["High_Frequency_Strategy"] = StrategyTemplate(
            name="High_Frequency_Strategy",
            display_name="高频交易策略",
            description="基于短期技术指标的高频交易策略，适合测试回测系统，产生大量交易信号",
            category="高频交易",
            risk_profile="HIGH",
            complexity="ADVANCED",
            required_fields=["symbol", "timeframe", "fast_ema_period", "slow_ema_period"],
            validation_rules={
                "fast_ema_period": {"min": 3, "max": 20, "type": "int"},
                "slow_ema_period": {"min": 5, "max": 50, "type": "int"},
                "rsi_period": {"min": 5, "max": 30, "type": "int"},
                "rsi_oversold": {"min": 10, "max": 40, "type": "int"},
                "rsi_overbought": {"min": 60, "max": 90, "type": "int"},
                "volume_threshold": {"min": 1.0, "max": 5.0, "type": "float"},
                "price_change_threshold": {"min": 0.001, "max": 0.05, "type": "float"},
                "min_trade_interval": {"min": 1, "max": 60, "type": "int"},
                "max_trades_per_day": {"min": 10, "max": 200, "type": "int"}
            },
            default_config={
                # 基础参数
                "symbol": "ETH-USDT-SWAP",
                "timeframe": "5m",  # 5分钟K线，适合高频交易
                "risk_per_trade": 0.01,  # 1% 风险
                "max_positions": 3,
                "position_sizing": "fixed",
                
                # EMA参数
                "fast_ema_period": 5,
                "slow_ema_period": 10,
                
                # RSI参数
                "rsi_period": 14,
                "rsi_oversold": 35,  # 放宽超卖条件
                "rsi_overbought": 65,  # 放宽超买条件
                
                # 成交量确认参数
                "volume_threshold": 1.2,  # 降低成交量要求
                "price_change_threshold": 0.005,  # 降低价格变化要求
                
                # 交易频率控制
                "min_trade_interval": 1,  # 减少最小交易间隔到1分钟
                "max_trades_per_day": 100,  # 增加每日最大交易次数
                
                # 止损止盈参数
                "stop_loss_pct": 0.01,  # 1% 止损
                "take_profit_pct": 0.02,  # 2% 止盈
                "trailing_stop": True,
                "trailing_stop_pct": 0.005,
                
                # 风险管理
                "risk_config": {
                    "max_daily_loss": 0.03,
                    "max_position_size": 0.05,
                    "max_drawdown": 0.1,
                    "max_leverage": 2.0,
                    "max_concentration": 0.2
                }
            }
        )
        
        # 网格交易策略模板
        self.templates["Grid_Strategy"] = StrategyTemplate(
            name="Grid_Strategy",
            display_name="网格交易策略",
            description="在价格区间内设置多个网格点进行高抛低吸，适合震荡市场和横盘行情",
            category="量化套利",
            risk_profile="LOW",
            complexity="ADVANCED",
            required_fields=["symbol", "timeframe", "grid_levels", "grid_spacing", "base_price"],
            validation_rules={
                "grid_levels": {"min": 3, "max": 50, "type": "int"},
                "grid_spacing": {"min": 0.005, "max": 0.1, "type": "float"},
                "base_price": {"min": 0.01, "max": 1000000, "type": "float"},
                "investment_per_grid": {"min": 10, "max": 100000, "type": "float"}
            },
            default_config={
                # 基础参数
                "symbol": "BTC-USDT",
                "timeframe": "4h",
                "risk_per_trade": 0.02,
                "max_positions": 5,
                "position_sizing": "fixed",
                
                # 网格参数
                "grid_levels": 10,
                "grid_spacing": 0.02,
                "base_price": 50000,
                "investment_per_grid": 1000,
                
                # 动态网格参数
                "dynamic_grid": True,
                "grid_adjustment_threshold": 0.1,
                "max_grid_adjustments": 3,
                "max_grid_positions": 5,
                
                # 止损止盈参数
                "stop_loss_pct": 0.05,
                "take_profit_pct": 0.15,
                "enable_trend_following": False,
                
                # 风险管理
                "risk_config": {
                    "max_daily_loss": 0.03,
                    "max_position_size": 0.05,
                    "max_drawdown": 0.1,
                    "max_leverage": 1.0,
                    "max_concentration": 0.8
                }
            }
        )
        
        # 发明者量化网格交易策略模板
        self.templates["FMZGrid_Strategy"] = StrategyTemplate(
            name="FMZGrid_Strategy",
            display_name="发明者量化网格交易策略",
            description="基于币种比例平衡的网格交易策略，维持固定的币/资金比例，通过买卖来平衡持仓",
            category="量化套利",
            risk_profile="LOW",
            complexity="ADVANCED",
            required_fields=["symbol", "timeframe", "ratio", "grid_ratio"],
            validation_rules={
                "ratio": {"min": 0.1, "max": 0.9, "type": "float"},
                "grid_ratio": {"min": 0.0005, "max": 0.1, "type": "float"},
                "interval": {"min": 100, "max": 10000, "type": "int"},
                "price_precision": {"min": 2, "max": 8, "type": "int"},
                "amount_precision": {"min": 2, "max": 8, "type": "int"}
            },
            default_config={
                # 基础参数
                "symbol": "BTC-USDT",
                "timeframe": "1h",
                "risk_per_trade": 0.02,
                "max_positions": 1,
                "position_sizing": "fixed",
                
                # 比例平衡参数
                "ratio": 0.5,  # 目标币种比例（50%）
                "grid_ratio": 0.01,  # 网格密度（1%）
                "interval": 1000,  # 更新间隔（毫秒）
                
                # 精度设置
                "price_precision": 2,
                "amount_precision": 6,
                
                # 风险管理
                "risk_config": {
                    "max_daily_loss": 0.05,
                    "max_position_size": 1.0,
                    "max_drawdown": 0.2,
                    "max_leverage": 1.0,
                    "max_concentration": 1.0
                }
            }
        )
        
        # 马丁剥头皮网格策略模板
        # 做市商策略模板
        self.templates["MarketMaker_Strategy"] = StrategyTemplate(
            name="MarketMaker_Strategy",
            display_name="做市商策略",
            description="在买卖两侧同时挂单，通过维持买卖价差赚取利润。支持止损/止盈和重平衡功能，适合流动性较好的市场。参考: https://github.com/yanowo/Backpack-MM-Simple/",
            category="做市交易",
            risk_profile="MEDIUM",
            complexity="ADVANCED",
            required_fields=["symbol", "spread", "quantity"],
            validation_rules={
                "spread": {"min": 0.0001, "max": 0.1, "type": "float"},
                "quantity": {"min": 0.001, "max": 1000, "type": "float"},
                "max_orders": {"min": 1, "max": 20, "type": "int"},
                "stop_loss": {"min": -1000, "max": 0, "type": "float"},
                "take_profit": {"min": 0, "max": 10000, "type": "float"},
                "base_asset_target": {"min": 0, "max": 100, "type": "float"},
                "rebalance_threshold": {"min": 1, "max": 50, "type": "float"}
            },
            default_config={
                "symbol": "SOL-USDT",
                "timeframe": "1m",
                "risk_per_trade": 0.01,
                
                # 做市参数
                "spread": 0.002,  # 价差（0.2%）
                "quantity": 0.1,  # 每单数量
                "max_orders": 5,  # 每侧最大订单数
                
                # 止损止盈参数
                "enable_stop_loss": True,
                "enable_take_profit": True,
                "stop_loss": -25.0,  # 止损金额（USDC）
                "take_profit": 50.0,  # 止盈金额（USDC）
                
                # 重平衡参数
                "enable_rebalance": False,
                "base_asset_target": 30.0,  # 基础资产目标比例（%）
                "rebalance_threshold": 15.0,  # 重平衡触发阈值（%）
                
                # 风险管理
                "risk_config": {
                    "max_daily_loss": 0.05,
                    "max_position_size": 0.3,
                    "max_drawdown": 0.2,
                    "max_leverage": 1.0,
                    "max_concentration": 0.5
                }
            }
        )
        
        # 市商对冲策略模板
        self.templates["MarketMakerHedge_Strategy"] = StrategyTemplate(
            name="MarketMakerHedge_Strategy",
            display_name="市商对冲策略",
            description="在做市商策略基础上增加对冲机制，检测持仓方向风险，通过反向对冲减少单向暴露，维持市场中性。适合需要降低方向性风险的做市场景。",
            category="做市交易",
            risk_profile="LOW",
            complexity="ADVANCED",
            required_fields=["symbol", "spread", "quantity", "enable_hedge"],
            validation_rules={
                "spread": {"min": 0.0001, "max": 0.1, "type": "float"},
                "quantity": {"min": 0.001, "max": 1000, "type": "float"},
                "max_orders": {"min": 1, "max": 20, "type": "int"},
                "hedge_threshold": {"min": 0.1, "max": 1.0, "type": "float"},
                "hedge_size_ratio": {"min": 0.1, "max": 1.0, "type": "float"},
                "max_position_exposure": {"min": 0.1, "max": 5.0, "type": "float"}
            },
            default_config={
                "symbol": "SOL-USDT",
                "timeframe": "1m",
                "risk_per_trade": 0.01,
                
                # 做市参数（继承自做市商策略）
                "spread": 0.002,
                "quantity": 0.1,
                "max_orders": 5,
                
                # 止损止盈参数
                "enable_stop_loss": True,
                "enable_take_profit": True,
                "stop_loss": -25.0,
                "take_profit": 50.0,
                
                # 重平衡参数
                "enable_rebalance": False,
                "base_asset_target": 30.0,
                "rebalance_threshold": 15.0,
                
                # 对冲参数
                "enable_hedge": True,  # 是否启用对冲
                "hedge_threshold": 0.5,  # 对冲触发阈值（持仓/总资产比例）
                "hedge_size_ratio": 0.8,  # 对冲比例（80%）
                "max_position_exposure": 1.0,  # 最大持仓暴露倍数
                
                # 风险管理
                "risk_config": {
                    "max_daily_loss": 0.03,
                    "max_position_size": 0.25,
                    "max_drawdown": 0.15,
                    "max_leverage": 1.0,
                    "max_concentration": 0.4
                }
            }
        )
        
        self.templates["MartinScalpGrid_Strategy"] = StrategyTemplate(
            name="MartinScalpGrid_Strategy",
            display_name="马丁剥头皮网格策略",
            description="结合马丁格尔、剥头皮和网格交易的优势，亏损后加倍下注快速回本，快速进出赚取小额价差，在价格区间内设置多个买卖挂单捕捉震荡行情",
            category="量化套利",
            risk_profile="HIGH",
            complexity="ADVANCED",
            required_fields=["symbol", "timeframe", "initial_amount", "martin_multiplier", "max_levels"],
            validation_rules={
                "initial_amount": {"min": 10, "max": 100000, "type": "float"},
                "martin_multiplier": {"min": 1.5, "max": 5.0, "type": "float"},
                "max_levels": {"min": 3, "max": 20, "type": "int"},
                "scalp_profit_pct": {"min": 0.0005, "max": 0.01, "type": "float"},
                "scalp_stop_loss_pct": {"min": 0.001, "max": 0.05, "type": "float"},
                "grid_spacing_pct": {"min": 0.0005, "max": 0.01, "type": "float"},
                "grid_count": {"min": 5, "max": 50, "type": "int"},
                "take_profit_pct": {"min": 0.005, "max": 0.1, "type": "float"},
                "stop_loss_pct": {"min": 0.01, "max": 0.2, "type": "float"},
                "max_position_value": {"min": 100, "max": 1000000, "type": "float"},
                "price_precision": {"min": 2, "max": 8, "type": "int"},
                "amount_precision": {"min": 2, "max": 8, "type": "int"}
            },
            default_config={
                # 基础参数
                "symbol": "BTC-USDT",
                "timeframe": "15m",
                "risk_per_trade": 0.05,
                "max_positions": 1,
                "position_sizing": "fixed",
                
                # 马丁格尔参数
                "initial_amount": 100.0,  # 初始下单金额（USDT）
                "martin_multiplier": 2.0,  # 马丁格尔倍数
                "max_levels": 10,  # 最大持仓层级
                
                # 剥头皮参数
                "scalp_profit_pct": 0.002,  # 剥头皮利润比例（0.2%）
                "scalp_stop_loss_pct": 0.005,  # 剥头皮止损比例（0.5%）
                
                # 网格参数
                "grid_spacing_pct": 0.001,  # 网格间距（0.1%）
                "grid_count": 10,  # 网格数量（上下各5个）
                
                # 止盈止损参数
                "take_profit_pct": 0.01,  # 总持仓止盈比例（1%）
                "stop_loss_pct": 0.05,  # 总持仓止损比例（5%）
                
                # 风控参数
                "max_position_value": 10000.0,  # 最大持仓价值（USDT）
                "min_price_change": 0.0001,  # 最小价格变化（0.01%）
                
                # 精度设置
                "price_precision": 2,
                "amount_precision": 6,
                
                # 风险管理
                "risk_config": {
                    "max_daily_loss": 0.1,
                    "max_position_size": 1.0,
                    "max_drawdown": 0.3,
                    "max_leverage": 1.0,
                    "max_concentration": 1.0
                }
            }
        )
        
        # RSI策略模板
        self.templates["RSI_Strategy"] = StrategyTemplate(
            name="RSI_Strategy",
            display_name="RSI超买超卖策略",
            description="基于相对强弱指数的超买超卖信号进行交易，适合震荡市场",
            category="均值回归",
            risk_profile="MEDIUM",
            complexity="BEGINNER",
            required_fields=["symbol", "timeframe", "rsi_period"],
            validation_rules={
                "rsi_period": {"min": 5, "max": 50, "type": "int"},
                "rsi_oversold": {"min": 10, "max": 40, "type": "int"},
                "rsi_overbought": {"min": 60, "max": 90, "type": "int"}
            },
            default_config={
                # 基础参数
                "symbol": "ETH-USDT",
                "timeframe": "1h",
                "risk_per_trade": 0.02,
                "max_positions": 2,
                "position_sizing": "fixed",
                
                # RSI参数
                "rsi_period": 14,
                "rsi_oversold": 30,
                "rsi_overbought": 70,
                
                # 止损止盈参数
                "stop_loss_pct": 0.03,
                "take_profit_pct": 0.08,
                
                # 风险管理
                "risk_config": {
                    "max_daily_loss": 0.04,
                    "max_position_size": 0.15,
                    "max_drawdown": 0.15,
                    "max_leverage": 1.0,
                    "max_concentration": 0.4
                }
            }
        )
        
        # 布林带策略模板
        self.templates["Bollinger_Strategy"] = StrategyTemplate(
            name="Bollinger_Strategy",
            display_name="布林带策略",
            description="基于布林带突破和回归的交易策略，结合趋势跟踪和均值回归",
            category="技术指标",
            risk_profile="MEDIUM",
            complexity="INTERMEDIATE",
            required_fields=["symbol", "timeframe", "bb_period", "bb_std"],
            validation_rules={
                "bb_period": {"min": 10, "max": 50, "type": "int"},
                "bb_std": {"min": 1.0, "max": 3.0, "type": "float"}
            },
            default_config={
                # 基础参数
                "symbol": "BTC-USDT",
                "timeframe": "1h",
                "risk_per_trade": 0.02,
                "max_positions": 2,
                "position_sizing": "fixed",
                
                # 布林带参数
                "bb_period": 20,
                "bb_std": 2.0,
                
                # 止损止盈参数
                "stop_loss_pct": 0.025,
                "take_profit_pct": 0.075,
                
                # 风险管理
                "risk_config": {
                    "max_daily_loss": 0.04,
                    "max_position_size": 0.12,
                    "max_drawdown": 0.15,
                    "max_leverage": 1.0,
                    "max_concentration": 0.4
                }
            }
        )
        
        # MACD策略模板
        self.templates["MACD_Strategy"] = StrategyTemplate(
            name="MACD_Strategy",
            display_name="MACD策略",
            description="基于MACD指标金叉死叉的经典趋势跟踪策略",
            category="趋势跟踪",
            risk_profile="MEDIUM",
            complexity="INTERMEDIATE",
            required_fields=["symbol", "timeframe", "fast_period", "slow_period", "signal_period"],
            validation_rules={
                "fast_period": {"min": 5, "max": 30, "type": "int"},
                "slow_period": {"min": 15, "max": 60, "type": "int"},
                "signal_period": {"min": 5, "max": 20, "type": "int"}
            },
            default_config={
                # 基础参数
                "symbol": "BTC-USDT",
                "timeframe": "1h",
                "risk_per_trade": 0.02,
                "max_positions": 2,
                "position_sizing": "fixed",
                
                # MACD参数
                "fast_period": 12,
                "slow_period": 26,
                "signal_period": 9,
                
                # 止损止盈参数
                "stop_loss_pct": 0.025,
                "take_profit_pct": 0.075,
                
                # 风险管理
                "risk_config": {
                    "max_daily_loss": 0.04,
                    "max_position_size": 0.12,
                    "max_drawdown": 0.15,
                    "max_leverage": 1.0,
                    "max_concentration": 0.4
                }
            }
        )
        
        logger.info(f"已加载 {len(self.templates)} 个策略模板")
    
    def get_template(self, strategy_type: str) -> Optional[StrategyTemplate]:
        """获取策略模板"""
        return self.templates.get(strategy_type)
    
    def get_all_templates(self) -> Dict[str, StrategyTemplate]:
        """获取所有策略模板"""
        return self.templates.copy()
    
    def get_templates_by_category(self, category: str) -> Dict[str, StrategyTemplate]:
        """按类别获取策略模板"""
        return {
            name: template for name, template in self.templates.items()
            if template.category == category
        }
    
    def get_templates_by_risk_profile(self, risk_profile: str) -> Dict[str, StrategyTemplate]:
        """按风险档次获取策略模板"""
        return {
            name: template for name, template in self.templates.items()
            if template.risk_profile == risk_profile
        }
    
    def validate_config(self, strategy_type: str, config: Dict[str, Any]) -> Tuple[bool, List[str]]:
        """验证策略配置"""
        errors = []
        
        if strategy_type not in self.templates:
            return False, [f"未知策略类型: {strategy_type}"]
        
        template = self.templates[strategy_type]
        logger.info(f"验证策略配置 - 策略类型: {strategy_type}, 模板类型: {type(template)}")
        logger.info(f"模板属性: required_fields={getattr(template, 'required_fields', 'None')}, validation_rules={getattr(template, 'validation_rules', 'None')}")
        
        # 检查必需字段
        for field in template.required_fields:
            if field not in config:
                errors.append(f"缺少必需字段: {field}")
        
        # 验证字段规则
        for field, rules in template.validation_rules.items():
            if field in config:
                value = config[field]
                
                # 类型检查
                if "type" in rules:
                    expected_type = rules["type"]
                    if expected_type == "int" and not isinstance(value, int):
                        errors.append(f"字段 {field} 应为整数类型")
                    elif expected_type == "float" and not isinstance(value, (int, float)):
                        errors.append(f"字段 {field} 应为数值类型")
                    elif expected_type == "str" and not isinstance(value, str):
                        errors.append(f"字段 {field} 应为字符串类型")
                
                # 范围检查
                # 先尝试转换为数值类型进行比较
                numeric_value = None
                if isinstance(value, (int, float)):
                    numeric_value = value
                elif isinstance(value, str):
                    try:
                        # 尝试转换为浮点数
                        numeric_value = float(value)
                        # 如果是整数类型，尝试转换回整数
                        if "type" in rules and rules["type"] == "int":
                            numeric_value = int(numeric_value)
                    except (ValueError, TypeError):
                        pass
                
                if numeric_value is not None:
                    if "min" in rules:
                        try:
                            min_value = float(rules["min"]) if isinstance(rules["min"], str) else rules["min"]
                            if numeric_value < min_value:
                                errors.append(f"字段 {field} 的值 {numeric_value} 小于最小值 {min_value}")
                        except (ValueError, TypeError):
                            pass
                    if "max" in rules:
                        try:
                            max_value = float(rules["max"]) if isinstance(rules["max"], str) else rules["max"]
                            if numeric_value > max_value:
                                errors.append(f"字段 {field} 的值 {numeric_value} 大于最大值 {max_value}")
                        except (ValueError, TypeError):
                            pass
        
        # 特殊验证逻辑
        if strategy_type == "MA_Cross_Strategy":
            if config.get("short_period", 0) >= config.get("long_period", 0):
                errors.append("短期均线周期必须小于长期均线周期")
        
        return len(errors) == 0, errors
    
    def create_config_from_template(self, strategy_type: str, custom_config: Dict[str, Any] = None) -> Optional[Dict[str, Any]]:
        """从模板创建配置"""
        if strategy_type not in self.templates:
            return None
        
        template = self.templates[strategy_type]
        config = template.default_config.copy()
        
        if custom_config:
            # 深度合并配置
            self._deep_merge_config(config, custom_config)
        
        return config
    
    def _deep_merge_config(self, base_config: Dict[str, Any], custom_config: Dict[str, Any]):
        """深度合并配置"""
        for key, value in custom_config.items():
            if key in base_config and isinstance(base_config[key], dict) and isinstance(value, dict):
                self._deep_merge_config(base_config[key], value)
            else:
                base_config[key] = value
    
    def save_config(self, strategy_name: str, config: Dict[str, Any]) -> bool:
        """保存策略配置到文件"""
        try:
            config_file = os.path.join(self.config_dir, f"{strategy_name}.json")
            
            # 添加元数据
            config_with_meta = {
                "metadata": {
                    "created_at": datetime.now().isoformat(),
                    "version": "1.0.0",
                    "strategy_name": strategy_name
                },
                "config": config
            }
            
            with open(config_file, 'w', encoding='utf-8') as f:
                json.dump(config_with_meta, f, indent=2, ensure_ascii=False)
            
            logger.info(f"策略配置已保存: {config_file}")
            return True
            
        except Exception as e:
            logger.error(f"保存策略配置失败: {e}")
            return False
    
    def load_config(self, strategy_name: str) -> Optional[Dict[str, Any]]:
        """从文件加载策略配置"""
        try:
            config_file = os.path.join(self.config_dir, f"{strategy_name}.json")
            
            if not os.path.exists(config_file):
                return None
            
            with open(config_file, 'r', encoding='utf-8') as f:
                config_data = json.load(f)
            
            # 返回配置部分，忽略元数据
            if isinstance(config_data, dict) and "config" in config_data:
                return config_data["config"]
            else:
                # 兼容旧格式
                return config_data
                
        except Exception as e:
            logger.error(f"加载策略配置失败: {e}")
            return None
    
    def get_all_saved_configs(self) -> List[Dict[str, Any]]:
        """获取所有已保存的配置"""
        configs = []
        
        try:
            for filename in os.listdir(self.config_dir):
                if filename.endswith('.json'):
                    strategy_name = filename[:-5]  # 去掉.json后缀
                    config = self.load_config(strategy_name)
                    if config:
                        configs.append({
                            'strategy_name': strategy_name,
                            'config': config
                        })
        except Exception as e:
            logger.error(f"获取已保存配置失败: {e}")
        
        return configs
    
    def delete_config(self, strategy_name: str) -> bool:
        """删除策略配置文件"""
        try:
            config_file = os.path.join(self.config_dir, f"{strategy_name}.json")
            
            if os.path.exists(config_file):
                os.remove(config_file)
                logger.info(f"策略配置已删除: {strategy_name}")
                return True
            else:
                logger.warning(f"配置文件不存在: {strategy_name}")
                return False
                
        except Exception as e:
            logger.error(f"删除策略配置失败: {e}")
            return False
    
    def export_template(self, strategy_type: str) -> Optional[Dict[str, Any]]:
        """导出策略模板为JSON格式"""
        if strategy_type not in self.templates:
            return None
        
        template = self.templates[strategy_type]
        return {
            "name": template.name,
            "display_name": template.display_name,
            "description": template.description,
            "category": template.category,
            "risk_profile": template.risk_profile,
            "complexity": template.complexity,
            "default_config": template.default_config,
            "required_fields": template.required_fields,
            "validation_rules": template.validation_rules
        }
    
    def get_config_schema(self, strategy_type: str) -> Optional[Dict[str, Any]]:
        """获取策略配置的JSON Schema"""
        if strategy_type not in self.templates:
            return None
        
        template = self.templates[strategy_type]
        
        schema = {
            "type": "object",
            "title": template.display_name,
            "description": template.description,
            "properties": {},
            "required": template.required_fields
        }
        
        # 根据默认配置生成schema
        for key, value in template.default_config.items():
            prop_schema = {"description": f"{key}参数"}
            
            if isinstance(value, bool):
                prop_schema["type"] = "boolean"
            elif isinstance(value, int):
                prop_schema["type"] = "integer"
            elif isinstance(value, float):
                prop_schema["type"] = "number"
            elif isinstance(value, str):
                prop_schema["type"] = "string"
            elif isinstance(value, dict):
                prop_schema["type"] = "object"
            elif isinstance(value, list):
                prop_schema["type"] = "array"
            
            # 添加验证规则
            if key in template.validation_rules:
                rules = template.validation_rules[key]
                if "min" in rules:
                    prop_schema["minimum"] = rules["min"]
                if "max" in rules:
                    prop_schema["maximum"] = rules["max"]
            
            schema["properties"][key] = prop_schema
        
        return schema

# 全局配置管理器实例
strategy_config_manager = StrategyConfigManager()

# 便捷函数
def get_strategy_template(strategy_type: str) -> Optional[StrategyTemplate]:
    """获取策略模板"""
    return strategy_config_manager.get_template(strategy_type)

def validate_strategy_config(strategy_type: str, config: Dict[str, Any]) -> Tuple[bool, List[str]]:
    """验证策略配置"""
    return strategy_config_manager.validate_config(strategy_type, config)

def create_strategy_config(strategy_type: str, custom_config: Dict[str, Any] = None) -> Optional[Dict[str, Any]]:
    """创建策略配置"""
    return strategy_config_manager.create_config_from_template(strategy_type, custom_config) 