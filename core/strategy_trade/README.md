# 策略交易模块 (Strategy Trade Module)

一个完整的量化交易策略执行和管理系统，支持策略开发、回测、实盘交易、风险管理和性能监控。

## 功能特性

### 🚀 核心功能
- **策略引擎**: 高性能异步策略执行引擎
- **多策略支持**: 同时运行多个交易策略
- **回测系统**: 完整的历史数据回测功能
- **风险管理**: 多维度风险控制和监控
- **实时监控**: 策略性能实时监控和告警
- **数据持久化**: 完整的数据库存储方案

### 📊 支持的策略类型
- 移动平均交叉策略 (MA Cross)
- RSI 超买超卖策略
- 布林带策略 (Bollinger Bands)
- MACD 策略
- 网格交易策略 (Grid Trading)
- 自定义策略扩展

### 🛡️ 风险管理
- 最大回撤控制
- 仓位大小限制
- 日亏损限制
- 连续亏损监控
- 实时风险评估

## 模块结构

```
core/strategy_trade/
├── __init__.py                 # 模块初始化
├── api.py                     # RESTful API接口
├── base_strategy.py           # 基础策略框架
├── strategy_engine.py         # 策略执行引擎
├── strategy_manager.py        # 策略管理器
├── strategy_db.py             # 数据库接口层
├── backtest_engine.py         # 回测引擎
├── monitoring.py              # 监控和告警系统
├── config_manager.py          # 配置管理
├── strategy_tables.sql        # 数据库表结构
├── indicators.sql             # 指标表结构
├── utils/
│   ├── __init__.py
│   └── indicators.py          # 技术指标库
└── strategies/                # 具体策略实现
    ├── __init__.py
    ├── ma_cross_strategy.py   # 移动平均交叉策略
    ├── rsi_strategy.py        # RSI策略
    ├── bollinger_strategy.py  # 布林带策略
    ├── macd_strategy.py       # MACD策略
    └── grid_strategy.py       # 网格策略
```

## 快速开始

### 1. 安装依赖

```bash
pip install pandas numpy asyncio aioredis aiomysql
```

### 2. 初始化数据库

```python
# 执行 strategy_tables.sql 创建数据库表
mysql -u username -p database_name < core/strategy_trade/strategy_tables.sql
```

### 3. 基本使用示例

```python
import asyncio
from core.strategy_trade.strategy_manager import StrategyManager
from core.strategy_trade.strategy_engine import StrategyEngine
from database.db import get_db_pool

async def main():
    # 获取数据库连接池
    db_pool = await get_db_pool()
    
    # 创建策略管理器
    strategy_manager = StrategyManager(db_pool)
    
    # 创建移动平均交叉策略
    ma_config = {
        "short_period": 10,
        "long_period": 20,
        "symbol": "BTC-USDT",
        "timeframe": "1h",
        "risk_per_trade": 0.02,
        "stop_loss_pct": 0.02,
        "take_profit_pct": 0.06
    }
    
    # 创建策略
    success = await strategy_manager.create_strategy(
        strategy_type="MA_Cross_Strategy",
        name="BTC_MA_Cross_1",
        config=ma_config
    )
    
    if success:
        # 启动策略引擎
        await strategy_manager.start_engine()
        
        # 启动策略
        await strategy_manager.start_strategy("BTC_MA_Cross_1")
        
        print("策略已启动，开始交易...")
        
        # 运行10分钟后停止
        await asyncio.sleep(600)
        
        # 停止策略
        await strategy_manager.stop_strategy("BTC_MA_Cross_1")
        await strategy_manager.stop_engine()

if __name__ == "__main__":
    asyncio.run(main())
```

## API 接口

### 策略管理 API

#### 1. 创建策略
```http
POST /api/strategy/create
Content-Type: application/json

{
  "strategy_type": "MA_Cross_Strategy",
  "name": "BTC_MA_Cross_1",
  "config": {
    "short_period": 10,
    "long_period": 20,
    "symbol": "BTC-USDT",
    "timeframe": "1h",
    "risk_per_trade": 0.02
  }
}
```

#### 2. 启动策略
```http
POST /api/strategy/start/BTC_MA_Cross_1
```

#### 3. 停止策略
```http
POST /api/strategy/stop/BTC_MA_Cross_1
```

#### 4. 获取策略列表
```http
GET /api/strategy/list
```

#### 5. 获取策略状态
```http
GET /api/strategy/status/BTC_MA_Cross_1
```

#### 6. 更新策略配置
```http
PUT /api/strategy/config/BTC_MA_Cross_1
Content-Type: application/json

{
  "config": {
    "stop_loss_pct": 0.03,
    "take_profit_pct": 0.08
  }
}
```

### 引擎管理 API

#### 1. 启动引擎
```http
POST /api/strategy/engine/start
```

#### 2. 停止引擎
```http
POST /api/strategy/engine/stop
```

#### 3. 获取引擎状态
```http
GET /api/strategy/engine/status
```

### 回测 API

#### 1. 运行回测
```http
POST /api/strategy/backtest
Content-Type: application/json

{
  "strategy_name": "BTC_MA_Cross_1",
  "start_date": "2023-01-01",
  "end_date": "2023-12-31",
  "initial_capital": 100000
}
```

## 自定义策略开发

### 1. 创建策略类

```python
from core.strategy_trade.base_strategy import BaseStrategy, TradingSignal
from core.strategy_trade.utils.indicators import TechnicalIndicators
import pandas as pd
from datetime import datetime

class MyCustomStrategy(BaseStrategy):
    """自定义策略示例"""
    
    def __init__(self, config):
        super().__init__("My_Custom_Strategy", config)
        
        # 策略参数
        self.rsi_period = config.get('rsi_period', 14)
        self.rsi_oversold = config.get('rsi_oversold', 30)
        self.rsi_overbought = config.get('rsi_overbought', 70)
        self.ma_period = config.get('ma_period', 20)
    
    def generate_signals(self, data: pd.DataFrame) -> List[TradingSignal]:
        """生成交易信号"""
        signals = []
        
        if len(data) < max(self.rsi_period, self.ma_period):
            return signals
        
        # 计算技术指标
        rsi = TechnicalIndicators.rsi(data['close'], self.rsi_period)
        ma = TechnicalIndicators.sma(data['close'], self.ma_period)
        
        current_price = data['close'].iloc[-1]
        current_rsi = rsi.iloc[-1]
        current_ma = ma.iloc[-1]
        
        # 生成买入信号
        if (current_rsi < self.rsi_oversold and 
            current_price > current_ma):
            signal = TradingSignal(
                symbol=self.symbol,
                action='BUY',
                price=current_price,
                quantity=1.0,
                timestamp=datetime.now(),
                confidence=0.8,
                strategy_name=self.name,
                stop_loss=current_price * 0.98,
                take_profit=current_price * 1.06
            )
            signals.append(signal)
        
        # 生成卖出信号
        elif current_rsi > self.rsi_overbought:
            signal = TradingSignal(
                symbol=self.symbol,
                action='SELL',
                price=current_price,
                quantity=1.0,
                timestamp=datetime.now(),
                confidence=0.8,
                strategy_name=self.name
            )
            signals.append(signal)
        
        return signals
    
    def should_exit_position(self, position, current_data: pd.DataFrame) -> bool:
        """判断是否应该退出持仓"""
        current_price = current_data['close'].iloc[-1]
        
        # 止损检查
        if position.stop_loss and current_price <= position.stop_loss:
            return True
        
        # 止盈检查
        if position.take_profit and current_price >= position.take_profit:
            return True
        
        return False
```

### 2. 注册策略

```python
# 在 strategy_manager.py 中添加新策略
self.available_strategies["My_Custom_Strategy"] = "path.to.my_custom_strategy.MyCustomStrategy"
```

## 监控和告警

### 1. 启动监控系统

```python
from core.strategy_trade.monitoring import StrategyMonitor, AlertNotifier

# 创建监控器
monitor = StrategyMonitor()

# 添加策略到监控
for strategy in strategies:
    monitor.add_strategy(strategy)

# 启动监控
await monitor.start_monitoring()

# 设置邮件告警
email_config = {
    'smtp_server': 'smtp.gmail.com',
    'smtp_port': 587,
    'username': 'your-email@gmail.com',
    'password': 'your-password',
    'to_emails': ['admin@company.com']
}

notifier = AlertNotifier(email_config)
monitor.add_alert_handler(notifier.handle_alert)
```

### 2. 生成报告

```python
from core.strategy_trade.monitoring import ReportGenerator

# 创建报告生成器
report_gen = ReportGenerator(monitor)

# 生成日报
daily_report = await report_gen.generate_daily_report()

# 导出为HTML
html_file = await report_gen.export_report_to_html(daily_report)
print(f"报告已保存到: {html_file}")
```

## 配置说明

### 策略配置参数

```python
{
    # 基础参数
    "symbol": "BTC-USDT",           # 交易对
    "timeframe": "1h",              # 时间框架
    "risk_per_trade": 0.02,         # 每笔交易风险比例
    "max_positions": 3,             # 最大持仓数量
    
    # 止损止盈
    "stop_loss_pct": 0.02,          # 止损百分比
    "take_profit_pct": 0.06,        # 止盈百分比
    "trailing_stop": True,          # 是否启用跟踪止损
    
    # 风险管理
    "max_daily_loss": 0.05,         # 最大日亏损
    "max_drawdown": 0.2,            # 最大回撤
    "position_sizing": "fixed",     # 仓位计算方法
    
    # 策略特定参数
    "short_period": 10,             # 短期均线周期
    "long_period": 20,              # 长期均线周期
    "rsi_period": 14,               # RSI周期
    "rsi_oversold": 30,             # RSI超卖阈值
    "rsi_overbought": 70            # RSI超买阈值
}
```

### 风险配置参数

```python
{
    "max_daily_loss": 0.05,         # 最大日亏损5%
    "max_position_size": 0.1,       # 最大单笔仓位10%
    "max_correlation": 0.7,         # 最大相关性
    "max_drawdown": 0.2,            # 最大回撤20%
    "max_leverage": 1.0,            # 最大杠杆倍数
    "max_concentration": 0.3        # 最大持仓集中度
}
```

## 性能优化

### 1. 数据库优化
- 使用连接池管理数据库连接
- 合理设置索引提高查询效率
- 定期清理历史数据

### 2. 内存优化
- 限制历史数据缓存大小
- 及时清理无用对象
- 使用数据流处理大量数据

### 3. 并发优化
- 使用异步编程提高并发性能
- 合理设置线程池大小
- 避免阻塞操作

## 故障排除

### 常见问题

1. **策略无法启动**
   - 检查配置参数是否正确
   - 确认数据库连接正常
   - 查看日志错误信息

2. **信号不生成**
   - 检查市场数据是否正常更新
   - 确认策略逻辑是否正确
   - 查看策略状态和参数

3. **性能问题**
   - 监控CPU和内存使用情况
   - 检查数据库查询效率
   - 优化策略计算逻辑

### 日志查看

```python
# 设置日志级别
import logging
logging.getLogger('core.strategy_trade').setLevel(logging.DEBUG)

# 查看具体策略日志
logger = get_logger('core.strategy_trade.strategies.ma_cross_strategy')
```

## 部署指南

### 1. 生产环境部署

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 配置数据库
mysql -u username -p database_name < strategy_tables.sql

# 3. 配置环境变量
export DB_HOST=localhost
export DB_USER=username
export DB_PASSWORD=password
export DB_NAME=trading_db

# 4. 启动服务
python -m uvicorn api.api_server:app --host 0.0.0.0 --port 8000
```

### 2. Docker 部署

```dockerfile
FROM python:3.9-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .
EXPOSE 8000

CMD ["python", "-m", "uvicorn", "api.api_server:app", "--host", "0.0.0.0", "--port", "8000"]
```

### 3. 监控配置

```yaml
# prometheus.yml
scrape_configs:
  - job_name: 'strategy-trade'
    static_configs:
      - targets: ['localhost:8000']
    metrics_path: '/metrics'
```

## 扩展开发

### 1. 添加新的技术指标

```python
# 在 utils/indicators.py 中添加
@staticmethod
def my_custom_indicator(data: pd.Series, period: int = 14) -> pd.Series:
    """自定义技术指标"""
    # 实现指标计算逻辑
    return result
```

### 2. 扩展风险管理

```python
# 继承 RiskManager 类
class CustomRiskManager(RiskManager):
    def validate_signal(self, signal, portfolio_value):
        # 添加自定义风险检查逻辑
        return super().validate_signal(signal, portfolio_value)
```

### 3. 自定义数据源

```python
# 实现数据接口
class CustomDataProvider:
    async def get_market_data(self, symbol: str, timeframe: str) -> pd.DataFrame:
        # 从自定义数据源获取数据
        pass
```

## 版本历史

- **v1.0.0** - 初始版本，基础策略引擎
- **v1.1.0** - 添加回测功能和风险管理
- **v1.2.0** - 完善监控系统和告警功能
- **v1.3.0** - 优化性能和添加更多策略类型
- **v2.0.0** - 重构架构，支持分布式部署

## 贡献指南

1. Fork 项目
2. 创建特性分支
3. 提交更改
4. 推送到分支
5. 创建 Pull Request

## 许可证

MIT License

## 联系方式

- 技术支持: support@example.com
- 文档: https://docs.example.com
- Issues: https://github.com/example/strategy-trade/issues 