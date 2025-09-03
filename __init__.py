"""
Follow Trade For Trade - 跟单交易系统

这是一个专业的加密货币跟单交易系统，支持多交易所、多策略、风险控制等功能。

主要功能:
- 信号源管理和监控
- 客户账户管理
- 策略配置和执行
- 风险控制和止损管理
- 限价跟单交易
- 实时市场数据
- Web管理界面

作者: sylas
版本: 1.0.0
"""

__version__ = "1.0.0"
__author__ = "sylas"
__description__ = "专业的加密货币跟单交易系统"

# 导出主要模块
from .main import main
from .api.api_server import app as api_app

__all__ = [
    "main",
    "api_app",
    "__version__",
    "__author__",
    "__description__"
] 