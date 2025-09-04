"""
策略扫描器 - 动态发现和验证策略
"""

import os
import ast
import importlib
import inspect
from typing import Dict, List, Any, Optional, Tuple
from utils.logger import get_logger

logger = get_logger(__name__)

class StrategyScanner:
    """策略扫描器 - 动态发现策略参数和验证策略完整性"""
    
    def __init__(self, strategies_dir: str = "core.strategy_trade.strategies"):
        self.strategies_dir = strategies_dir
        self.strategies_path = strategies_dir.replace('.', '/')
        self.discovered_strategies = {}
        
    def scan_all_strategies(self) -> Dict[str, Dict[str, Any]]:
        """扫描所有策略"""
        logger.info("开始扫描策略文件夹...")
        
        # 获取策略文件夹路径
        import core.strategy_trade.strategies
        strategies_folder = os.path.dirname(core.strategy_trade.strategies.__file__)
        
        strategy_files = []
        for file in os.listdir(strategies_folder):
            if file.endswith('_strategy.py') and not file.startswith('__'):
                strategy_files.append(file)
        
        logger.info(f"发现策略文件: {strategy_files}")
        
        for strategy_file in strategy_files:
            try:
                strategy_info = self._analyze_strategy_file(strategy_file)
                if strategy_info:
                    self.discovered_strategies[strategy_info['class_name']] = strategy_info
                    logger.info(f"✅ 成功分析策略: {strategy_info['class_name']}")
            except Exception as e:
                logger.error(f"❌ 分析策略文件失败 {strategy_file}: {e}")
        
        return self.discovered_strategies
    
    def _analyze_strategy_file(self, strategy_file: str) -> Optional[Dict[str, Any]]:
        """分析单个策略文件"""
        try:
            # 构造模块名
            module_name = strategy_file[:-3]  # 去掉.py
            full_module_name = f"{self.strategies_dir}.{module_name}"
            
            # 动态导入模块
            module = importlib.import_module(full_module_name)
            
            # 查找策略类
            strategy_class = None
            for name, obj in inspect.getmembers(module, inspect.isclass):
                if (name.endswith('Strategy') and 
                    obj.__module__ == full_module_name and
                    name != 'BaseStrategy'):
                    strategy_class = obj
                    break
            
            if not strategy_class:
                logger.warning(f"在 {strategy_file} 中未找到策略类")
                return None
            
            # 分析策略类
            return self._analyze_strategy_class(strategy_class, module_name)
            
        except Exception as e:
            logger.error(f"分析策略文件 {strategy_file} 失败: {e}")
            return None
    
    def _analyze_strategy_class(self, strategy_class, module_name: str) -> Dict[str, Any]:
        """分析策略类"""
        class_name = strategy_class.__name__
        
        # 检查必需方法
        required_methods = ['generate_signals', 'should_exit_position']
        missing_methods = []
        
        for method in required_methods:
            if not hasattr(strategy_class, method):
                missing_methods.append(method)
            else:
                # 检查是否是抽象方法（未实现）
                method_obj = getattr(strategy_class, method)
                if hasattr(method_obj, '__isabstractmethod__') and method_obj.__isabstractmethod__:
                    missing_methods.append(method)
        
        # 分析构造函数参数
        init_method = strategy_class.__init__
        parameters = self._extract_config_parameters(init_method, strategy_class)
        
        # 获取策略元信息
        docstring = strategy_class.__doc__ or f"{class_name}策略"
        
        strategy_info = {
            'class_name': class_name,
            'module_name': module_name,
            'full_module_path': f"{self.strategies_dir}.{module_name}",
            'display_name': self._generate_display_name(class_name),
            'description': docstring.strip(),
            'parameters': parameters,
            'missing_methods': missing_methods,
            'is_complete': len(missing_methods) == 0,
            'category': self._determine_category(class_name.lower()),
            'risk_profile': 'MEDIUM',
            'complexity': 'INTERMEDIATE'
        }
        
        return strategy_info
    
    def _extract_config_parameters(self, init_method, strategy_class) -> Dict[str, Any]:
        """从构造函数中提取配置参数"""
        parameters = {}
        
        try:
            # 获取源代码
            source = inspect.getsource(init_method)
            
            # 修复缩进问题 - 删除公共前导空格
            lines = source.split('\n')
            if lines:
                # 找到第一个非空行的缩进
                first_line_indent = 0
                for line in lines:
                    if line.strip():
                        first_line_indent = len(line) - len(line.lstrip())
                        break
                
                # 移除公共缩进
                cleaned_lines = []
                for line in lines:
                    if line.strip():  # 非空行
                        if len(line) >= first_line_indent:
                            cleaned_lines.append(line[first_line_indent:])
                        else:
                            cleaned_lines.append(line.lstrip())
                    else:
                        cleaned_lines.append('')
                
                source = '\n'.join(cleaned_lines)
            
            # 解析AST
            tree = ast.parse(source)
            
            # 查找config.get()调用
            for node in ast.walk(tree):
                if (isinstance(node, ast.Call) and
                    isinstance(node.func, ast.Attribute) and
                    node.func.attr == 'get' and
                    isinstance(node.func.value, ast.Name) and
                    node.func.value.id == 'config'):
                    
                    if len(node.args) >= 1:
                        param_name = None
                        default_value = None
                        
                        # 提取参数名
                        if isinstance(node.args[0], ast.Constant):
                            param_name = node.args[0].value
                        elif isinstance(node.args[0], ast.Str):  # Python < 3.8
                            param_name = node.args[0].s
                        
                        # 提取默认值
                        if len(node.args) >= 2:
                            if isinstance(node.args[1], ast.Constant):
                                default_value = node.args[1].value
                            elif isinstance(node.args[1], ast.Num):  # Python < 3.8
                                default_value = node.args[1].n
                            elif isinstance(node.args[1], ast.Str):  # Python < 3.8
                                default_value = node.args[1].s
                            elif isinstance(node.args[1], ast.NameConstant):  # Python < 3.8
                                default_value = node.args[1].value
                        
                        if param_name:
                            # 推断参数类型和验证规则
                            param_info = self._infer_parameter_info(param_name, default_value)
                            parameters[param_name] = param_info
        
        except Exception as e:
            logger.warning(f"提取参数失败: {e}")
            # 备用方案：通过正则表达式提取
            parameters = self._extract_config_parameters_regex(init_method)
        
        return parameters
    
    def _extract_config_parameters_regex(self, init_method) -> Dict[str, Any]:
        """备用方案：通过正则表达式提取配置参数"""
        import re
        parameters = {}
        
        try:
            source = inspect.getsource(init_method)
            
            # 正则表达式匹配 config.get('param_name', default_value)
            pattern = r"config\.get\(\s*['\"]([^'\"]+)['\"]\s*,\s*([^)]+)\s*\)"
            matches = re.findall(pattern, source)
            
            for param_name, default_str in matches:
                # 尝试解析默认值
                default_value = self._parse_default_value(default_str.strip())
                param_info = self._infer_parameter_info(param_name, default_value)
                parameters[param_name] = param_info
                
        except Exception as e:
            logger.warning(f"正则表达式提取参数失败: {e}")
        
        return parameters
    
    def _parse_default_value(self, value_str: str):
        """解析默认值字符串"""
        try:
            # 移除注释
            value_str = value_str.split('#')[0].strip()
            
            # 尝试直接评估
            if value_str in ['True', 'False']:
                return value_str == 'True'
            elif value_str == 'None':
                return None
            elif value_str.startswith('"') or value_str.startswith("'"):
                return value_str.strip('"\'')
            else:
                # 尝试解析为数字
                if '.' in value_str:
                    return float(value_str)
                else:
                    return int(value_str)
        except:
            return value_str
    
    def _infer_parameter_info(self, param_name: str, default_value: Any) -> Dict[str, Any]:
        """推断参数信息"""
        param_info = {
            'name': param_name,
            'default': default_value,
            'label': self._generate_param_label(param_name),
            'description': self._generate_param_description(param_name),
            'required': False
        }
        
        # 根据参数名和默认值推断类型和验证规则
        if isinstance(default_value, int):
            param_info['type'] = 'int'
            param_info['input_type'] = 'number'
            param_info['step'] = 1
            
            # 推断合理范围
            if 'period' in param_name.lower():
                param_info['min'] = 5
                param_info['max'] = 100
            elif 'level' in param_name.lower():
                param_info['min'] = 3
                param_info['max'] = 50
            elif 'threshold' in param_name.lower():
                param_info['min'] = 10
                param_info['max'] = 90
            else:
                param_info['min'] = 1
                param_info['max'] = 1000
                
        elif isinstance(default_value, float):
            param_info['type'] = 'float'
            param_info['input_type'] = 'number'
            
            if 'pct' in param_name.lower() or 'ratio' in param_name.lower():
                param_info['step'] = 0.001
                param_info['min'] = 0.001
                param_info['max'] = 1.0
            elif 'spacing' in param_name.lower():
                param_info['step'] = 0.001
                param_info['min'] = 0.005
                param_info['max'] = 0.1
            elif 'price' in param_name.lower():
                param_info['step'] = 0.01
                param_info['min'] = 0.01
                param_info['max'] = 1000000
            else:
                param_info['step'] = 0.1
                param_info['min'] = 0.1
                param_info['max'] = 100.0
                
        elif isinstance(default_value, str):
            param_info['type'] = 'string'
            param_info['input_type'] = 'text'
            
        elif isinstance(default_value, bool):
            param_info['type'] = 'boolean'
            param_info['input_type'] = 'checkbox'
        else:
            # 默认处理：根据参数名推断类型
            param_info['type'] = 'string'
            param_info['input_type'] = 'text'
            
            # 根据参数名尝试推断更合适的类型
            param_lower = param_name.lower()
            if any(word in param_lower for word in ['period', 'level', 'threshold', 'count', 'num', 'max']):
                param_info['type'] = 'int'
                param_info['input_type'] = 'number'
                param_info['step'] = 1
                param_info['min'] = 1
                param_info['max'] = 100
            elif any(word in param_lower for word in ['pct', 'ratio', 'rate', 'spacing', 'factor']):
                param_info['type'] = 'float'
                param_info['input_type'] = 'number'
                param_info['step'] = 0.001
                param_info['min'] = 0.001
                param_info['max'] = 1.0
            elif any(word in param_lower for word in ['enable', 'disable', 'use', 'allow']):
                param_info['type'] = 'boolean'
                param_info['input_type'] = 'checkbox'
                param_info['default'] = False  # 如果原值是None，设为False
        
        return param_info
    
    def _generate_display_name(self, class_name: str) -> str:
        """生成显示名称"""
        name_mapping = {
            'GridStrategy': '网格交易策略',
            'RSIStrategy': 'RSI超买超卖策略',
            'BollingerStrategy': '布林带策略',
            'MACDStrategy': 'MACD策略',
            'MACrossStrategy': '移动平均交叉策略'
        }
        return name_mapping.get(class_name, class_name)
    
    def _generate_param_label(self, param_name: str) -> str:
        """生成参数标签"""
        label_mapping = {
            'grid_levels': '网格层数',
            'grid_spacing': '网格间距',
            'base_price': '基准价格',
            'investment_per_grid': '每格投资金额',
            'max_grid_positions': '最大网格仓位',
            'period': '周期',
            'bb_period': '布林带周期',
            'std_dev': '标准差倍数',
            'rsi_period': 'RSI周期',
            'rsi_oversold': 'RSI超卖线',
            'rsi_overbought': 'RSI超买线',
            'short_period': '短期均线周期',
            'long_period': '长期均线周期',
            'fast_period': 'MACD快线周期',
            'slow_period': 'MACD慢线周期',
            'signal_period': 'MACD信号线周期',
            'stop_loss_pct': '止损比例',
            'take_profit_pct': '止盈比例'
        }
        return label_mapping.get(param_name, param_name.replace('_', ' ').title())
    
    def _generate_param_description(self, param_name: str) -> str:
        """生成参数描述"""
        desc_mapping = {
            'grid_levels': '网格总层数，建议3-20',
            'grid_spacing': '网格间距百分比，如0.02表示2%',
            'base_price': '网格中心价格',
            'investment_per_grid': '每个网格投资金额',
            'period': '计算周期',
            'bb_period': '布林带计算周期',
            'std_dev': '标准差倍数',
            'rsi_period': 'RSI计算周期',
            'rsi_oversold': '超卖阈值 (通常20-40)',
            'rsi_overbought': '超买阈值 (通常60-80)',
            'short_period': '短期移动平均线周期',
            'long_period': '长期移动平均线周期',
            'stop_loss_pct': '止损百分比，如0.02表示2%',
            'take_profit_pct': '止盈百分比，如0.06表示6%'
        }
        return desc_mapping.get(param_name, '')
    
    def _determine_category(self, class_name: str) -> str:
        """确定策略类别"""
        if 'grid' in class_name:
            return '量化套利'
        elif 'rsi' in class_name:
            return '均值回归'
        elif 'bollinger' in class_name:
            return '技术指标'
        elif 'macd' in class_name:
            return '趋势跟踪'
        elif 'ma' in class_name or 'cross' in class_name:
            return '趋势跟踪'
        else:
            return '其他'
    
    def get_complete_strategies(self) -> Dict[str, Dict[str, Any]]:
        """获取完整的策略（所有必需方法都已实现）"""
        return {name: info for name, info in self.discovered_strategies.items() 
                if info['is_complete']}
    
    def get_incomplete_strategies(self) -> Dict[str, Dict[str, Any]]:
        """获取不完整的策略（缺少必需方法）"""
        return {name: info for name, info in self.discovered_strategies.items() 
                if not info['is_complete']}

# 全局策略扫描器实例
strategy_scanner = StrategyScanner() 