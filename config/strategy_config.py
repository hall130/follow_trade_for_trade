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
                "rsi_oversold": 30,
                "rsi_overbought": 70,
                
                # 成交量确认参数
                "volume_threshold": 1.5,
                "price_change_threshold": 0.01,
                
                # 交易频率控制
                "min_trade_interval": 5,  # 最小交易间隔5分钟
                "max_trades_per_day": 50,  # 每日最大交易次数
                
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
                if isinstance(value, (int, float)):
                    if "min" in rules and value < rules["min"]:
                        errors.append(f"字段 {field} 的值 {value} 小于最小值 {rules['min']}")
                    if "max" in rules and value > rules["max"]:
                        errors.append(f"字段 {field} 的值 {value} 大于最大值 {rules['max']}")
        
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