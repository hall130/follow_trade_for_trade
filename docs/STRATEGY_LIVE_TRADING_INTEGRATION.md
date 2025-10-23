# 策略交易实盘集成指南

> 📅 创建日期：2025年10月23日  
> 📝 版本：v1.0  
> 🎯 目标：将策略交易模块接入现有实盘交易框架

## 📋 目录

1. [系统架构](#系统架构)
2. [快速开始](#快速开始)
3. [详细集成步骤](#详细集成步骤)
4. [API 接口](#api-接口)
5. [示例代码](#示例代码)
6. [常见问题](#常见问题)

---

## 🏗️ 系统架构

### 现有系统结构

```
follow_trade_for_trade/
├── core/
│   ├── market_trade/          # 现有实盘交易系统
│   │   ├── trade_server.py    # 交易服务器
│   │   ├── trade_service.py   # 交易执行服务
│   │   └── signal_service.py  # 信号处理服务
│   │
│   ├── limit_trade/           # 限价跟单系统
│   │
│   └── strategy_trade/        # 策略交易系统 (NEW!)
│       ├── core/
│       │   ├── strategy.py          # 策略基类
│       │   ├── manager.py           # 策略管理器
│       │   └── backtest.py          # 回测引擎
│       ├── strategies/              # 策略实现
│       │   └── technical/
│       │       ├── rsi.py
│       │       ├── ma_cross.py
│       │       └── macd.py
│       ├── strategy_trade_service.py  # 策略交易服务 (NEW!)
│       └── integration.py             # 集成模块 (NEW!)
│
└── api/
    └── api_server.py          # Flask API 服务器
```

### 集成架构图

```
┌─────────────────────────────────────────────────────┐
│                   API Server                        │
│              (Flask REST API)                       │
└────────────────┬────────────────────────────────────┘
                 │
                 ├───────────────┬───────────────────┐
                 │               │                   │
         ┌───────▼──────┐  ┌────▼────────┐  ┌──────▼──────┐
         │ TradeServer  │  │ LimitFollow │  │  Strategy   │
         │              │  │   Service   │  │ Integration │ ◄── NEW!
         └───────┬──────┘  └─────────────┘  └──────┬──────┘
                 │                                  │
         ┌───────▼──────────────────┐      ┌───────▼──────────┐
         │    TradeService          │      │  StrategyTrade   │
         │  (订单执行)              │      │    Service       │
         └──────────────────────────┘      └───────┬──────────┘
                                                    │
                                            ┌───────▼──────────┐
                                            │ StrategyManager  │
                                            │ (策略管理)       │
                                            └───────┬──────────┘
                                                    │
                                            ┌───────▼──────────┐
                                            │  Strategy        │
                                            │  Instances       │
                                            │  (RSI/MA/MACD)   │
                                            └──────────────────┘

                           ┌──────────────────┐
                           │   OKX WebSocket  │
                           │  (实时市场数据)   │
                           └──────────────────┘
```

---

## 🚀 快速开始

### 步骤1：修改 `api_server.py`

在 `api_server.py` 中添加策略交易集成：

```python
# api/api_server.py

from core.strategy_trade.integration import StrategyTradeIntegration

# 全局变量
strategy_trade_integration: Optional[StrategyTradeIntegration] = None

# 在 initialize_app() 函数中添加
async def initialize_app():
    global trade_server, strategy_trade_integration
    
    # ... 现有初始化代码 ...
    
    # 初始化策略交易集成
    if trade_server and trade_server.trade_service:
        strategy_trade_integration = StrategyTradeIntegration(
            db_pool=trade_server.db_pool,
            trade_service=trade_server.trade_service
        )
        await strategy_trade_integration.start()
        logger.info("✅ 策略交易系统已集成")

# 添加策略交易 API 端点

@app.route('/api/v1/strategy-trade/strategies', methods=['POST'])
async def create_strategy_trade():
    """创建策略交易实例"""
    data = await request.get_json()
    result = await strategy_trade_integration.api_create_strategy(
        strategy_type=data['strategy_type'],
        name=data['name'],
        config=data['config']
    )
    return jsonify(result)

@app.route('/api/v1/strategy-trade/strategies/<strategy_id>/start', methods=['POST'])
async def start_strategy_trade(strategy_id):
    """启动策略实盘交易"""
    data = await request.get_json()
    result = await strategy_trade_integration.api_start_strategy(
        strategy_id=strategy_id,
        config=data
    )
    return jsonify(result)

@app.route('/api/v1/strategy-trade/strategies/<strategy_id>/stop', methods=['POST'])
async def stop_strategy_trade(strategy_id):
    """停止策略实盘交易"""
    data = await request.get_json()
    close_positions = data.get('close_positions', True)
    result = await strategy_trade_integration.api_stop_strategy(
        strategy_id=strategy_id,
        close_positions=close_positions
    )
    return jsonify(result)

@app.route('/api/v1/strategy-trade/strategies/<strategy_id>/status', methods=['GET'])
async def get_strategy_trade_status(strategy_id):
    """获取策略状态"""
    result = await strategy_trade_integration.api_get_strategy_status(strategy_id)
    return jsonify(result)

@app.route('/api/v1/strategy-trade/strategies', methods=['GET'])
async def list_strategy_trades():
    """列出所有策略"""
    result = await strategy_trade_integration.api_list_strategies()
    return jsonify(result)
```

### 步骤2：修改 `main.py`

确保在主程序中启动策略交易系统：

```python
# main.py

import asyncio
from api.api_server import app, initialize_app

async def main():
    # 初始化应用（包括策略交易系统）
    await initialize_app()
    
    # 启动 Flask 服务器
    app.run(host='0.0.0.0', port=5000)

if __name__ == '__main__':
    asyncio.run(main())
```

### 步骤3：测试策略交易

#### 3.1 创建策略

```bash
curl -X POST http://localhost:5000/api/v1/strategy-trade/strategies \
  -H "Content-Type: application/json" \
  -d '{
    "strategy_type": "RSI_Strategy",
    "name": "live_rsi_btc",
    "config": {
      "symbol": "BTC-USDT-SWAP",
      "timeframe": "1h",
      "rsi_period": 14,
      "rsi_oversold": 30,
      "rsi_overbought": 70,
      "stop_loss_pct": 0.03,
      "take_profit_pct": 0.06
    }
  }'

# 响应
{
  "success": true,
  "strategy_id": "abc-123-def",
  "message": "策略创建成功"
}
```

#### 3.2 启动策略实盘交易

```bash
curl -X POST http://localhost:5000/api/v1/strategy-trade/strategies/abc-123-def/start \
  -H "Content-Type: application/json" \
  -d '{
    "symbol": "BTC-USDT-SWAP",
    "exchange": "okx",
    "is_demo": true,
    "initial_capital": 1000.0,
    "max_position_value": 500.0,
    "stop_loss_pct": 0.03,
    "take_profit_pct": 0.06
  }'

# 响应
{
  "success": true,
  "message": "策略已启动"
}
```

#### 3.3 查看策略状态

```bash
curl http://localhost:5000/api/v1/strategy-trade/strategies/abc-123-def/status

# 响应
{
  "success": true,
  "data": {
    "status": "RUNNING",
    "strategy_id": "abc-123-def",
    "symbol": "BTC-USDT-SWAP",
    "exchange": "okx",
    "is_demo": true,
    "running_time": "01:23:45",
    "has_ws_connection": true
  }
}
```

#### 3.4 停止策略

```bash
curl -X POST http://localhost:5000/api/v1/strategy-trade/strategies/abc-123-def/stop \
  -H "Content-Type: application/json" \
  -d '{
    "close_positions": true
  }'

# 响应
{
  "success": true,
  "message": "策略已停止"
}
```

---

## 📝 详细集成步骤

### 1. 数据库表设计

创建策略交易相关表（如果还没有）：

```sql
-- database/strategy_tables.sql

-- 策略实例表
CREATE TABLE IF NOT EXISTS strategy_instances (
    id VARCHAR(50) PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    strategy_type VARCHAR(50) NOT NULL,
    config JSON NOT NULL,
    status VARCHAR(20) DEFAULT 'STOPPED',
    is_active TINYINT DEFAULT 1,
    auto_start TINYINT DEFAULT 0,
    created_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_status (status),
    INDEX idx_type (strategy_type)
);

-- 策略交易记录表
CREATE TABLE IF NOT EXISTS strategy_trades (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    strategy_id VARCHAR(50) NOT NULL,
    order_id VARCHAR(100) NOT NULL,
    symbol VARCHAR(50) NOT NULL,
    side VARCHAR(10) NOT NULL,
    price DECIMAL(20, 8) NOT NULL,
    quantity DECIMAL(20, 8) NOT NULL,
    order_value DECIMAL(20, 8) NOT NULL,
    commission DECIMAL(20, 8) DEFAULT 0,
    pnl DECIMAL(20, 8) DEFAULT 0,
    status VARCHAR(20) DEFAULT 'PENDING',
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_strategy (strategy_id),
    INDEX idx_order (order_id),
    INDEX idx_time (timestamp)
);

-- 策略性能指标表
CREATE TABLE IF NOT EXISTS strategy_performance (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    strategy_id VARCHAR(50) NOT NULL,
    total_return DECIMAL(10, 4) DEFAULT 0,
    sharpe_ratio DECIMAL(10, 4) DEFAULT 0,
    max_drawdown DECIMAL(10, 4) DEFAULT 0,
    win_rate DECIMAL(10, 4) DEFAULT 0,
    total_trades INT DEFAULT 0,
    current_equity DECIMAL(20, 8) DEFAULT 0,
    updated_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY unique_strategy (strategy_id)
);
```

运行数据库初始化：

```bash
python database/init_database.py
```

### 2. WebSocket 数据订阅

`StrategyTradeService` 自动处理 WebSocket 订阅：

```python
# 在 strategy_trade_service.py 中

async def _run_strategy_loop(self, strategy_id, strategy, config):
    # 1. 连接 WebSocket
    client = await client_manager.get_client(...)
    
    # 2. 订阅K线数据
    await client.subscribe_public(
        channel=f"candle{interval}",
        inst_id=symbol,
        callback=self._handle_market_data
    )
    
    # 3. 保持连接，接收实时数据
    while True:
        await asyncio.sleep(1)
```

### 3. 策略信号处理流程

```
实时市场数据 (WebSocket)
    │
    ▼
MarketData 对象
    │
    ▼
strategy.on_data(market_data)
    │
    ├──> strategy.price_data.append()
    ├──> strategy.volume_data.append()
    └──> strategy.on_market_data()  # 策略逻辑
              │
              ▼
         计算技术指标 (RSI, MA, etc.)
              │
              ▼
         判断买卖信号
              │
              ▼
         strategy.pending_signals.append(Signal)
              │
              ▼
    strategy.get_signals()  # 返回信号列表
              │
              ▼
    _execute_signal()  # 执行信号
              │
              ├──> _risk_check()  # 风险检查
              │
              ├──> _execute_buy_order()  # 买入
              │      │
              │      └──> REST API place_order()
              │
              └──> _execute_sell_order()  # 卖出
                     │
                     └──> REST API place_order()
```

### 4. 风险控制集成

在 `strategy_trade_service.py` 中实现风险检查：

```python
async def _risk_check(self, strategy_id, signal, config):
    """
    风险检查
    
    1. 检查订单价值是否超限
    2. 检查总持仓价值是否超限
    3. 检查日交易次数是否超限
    4. 检查是否达到最大亏损
    """
    
    # 1. 订单价值检查
    order_value = signal.price * signal.quantity
    if order_value > config.max_position_value:
        logger.warning(f"订单价值超限: {order_value} > {config.max_position_value}")
        return False
    
    # 2. 查询当前持仓
    positions = await self._get_current_positions(strategy_id)
    total_position_value = sum(p['value'] for p in positions)
    
    if total_position_value + order_value > config.initial_capital * 0.8:
        logger.warning(f"总持仓超限: {total_position_value}")
        return False
    
    # 3. 查询今日交易次数
    today_trades = await self._get_today_trades_count(strategy_id)
    if today_trades >= 10:  # 每日最多10笔
        logger.warning(f"今日交易次数超限: {today_trades}")
        return False
    
    # 4. 检查当日亏损
    today_pnl = await self._get_today_pnl(strategy_id)
    if today_pnl < -config.initial_capital * 0.05:  # 日亏损5%
        logger.warning(f"今日亏损超限: {today_pnl}")
        return False
    
    return True
```

---

## 🔌 API 接口

### 完整 API 列表

| 方法 | 路径 | 功能 | 参数 |
|------|------|------|------|
| POST | `/api/v1/strategy-trade/strategies` | 创建策略 | strategy_type, name, config |
| GET | `/api/v1/strategy-trade/strategies` | 列出所有策略 | - |
| GET | `/api/v1/strategy-trade/strategies/<id>` | 获取策略详情 | - |
| POST | `/api/v1/strategy-trade/strategies/<id>/start` | 启动策略 | symbol, exchange, is_demo, etc. |
| POST | `/api/v1/strategy-trade/strategies/<id>/stop` | 停止策略 | close_positions |
| POST | `/api/v1/strategy-trade/strategies/<id>/pause` | 暂停策略 | - |
| POST | `/api/v1/strategy-trade/strategies/<id>/resume` | 恢复策略 | - |
| GET | `/api/v1/strategy-trade/strategies/<id>/status` | 获取状态 | - |
| GET | `/api/v1/strategy-trade/strategies/<id>/performance` | 获取性能指标 | - |
| GET | `/api/v1/strategy-trade/strategies/<id>/trades` | 获取交易记录 | start_date, end_date |
| PUT | `/api/v1/strategy-trade/strategies/<id>/config` | 更新配置 | config |
| DELETE | `/api/v1/strategy-trade/strategies/<id>` | 删除策略 | - |

### API 详细说明

#### 1. 创建策略

**请求**:
```http
POST /api/v1/strategy-trade/strategies
Content-Type: application/json

{
  "strategy_type": "RSI_Strategy",
  "name": "live_rsi_btc",
  "config": {
    "symbol": "BTC-USDT-SWAP",
    "timeframe": "1h",
    "rsi_period": 14,
    "rsi_oversold": 30,
    "rsi_overbought": 70,
    "stop_loss_pct": 0.03,
    "take_profit_pct": 0.06
  }
}
```

**响应**:
```json
{
  "success": true,
  "strategy_id": "abc-123-def",
  "message": "策略创建成功"
}
```

#### 2. 启动策略

**请求**:
```http
POST /api/v1/strategy-trade/strategies/abc-123-def/start
Content-Type: application/json

{
  "symbol": "BTC-USDT-SWAP",
  "exchange": "okx",
  "is_demo": true,
  "initial_capital": 1000.0,
  "max_position_value": 500.0,
  "stop_loss_pct": 0.03,
  "take_profit_pct": 0.06
}
```

**响应**:
```json
{
  "success": true,
  "message": "策略已启动"
}
```

---

## 💻 示例代码

### Python 客户端示例

```python
import requests
import json

class StrategyTradeClient:
    def __init__(self, base_url='http://localhost:5000'):
        self.base_url = base_url
    
    def create_strategy(self, strategy_type, name, config):
        """创建策略"""
        response = requests.post(
            f'{self.base_url}/api/v1/strategy-trade/strategies',
            json={
                'strategy_type': strategy_type,
                'name': name,
                'config': config
            }
        )
        return response.json()
    
    def start_strategy(self, strategy_id, config):
        """启动策略"""
        response = requests.post(
            f'{self.base_url}/api/v1/strategy-trade/strategies/{strategy_id}/start',
            json=config
        )
        return response.json()
    
    def stop_strategy(self, strategy_id, close_positions=True):
        """停止策略"""
        response = requests.post(
            f'{self.base_url}/api/v1/strategy-trade/strategies/{strategy_id}/stop',
            json={'close_positions': close_positions}
        )
        return response.json()
    
    def get_status(self, strategy_id):
        """获取状态"""
        response = requests.get(
            f'{self.base_url}/api/v1/strategy-trade/strategies/{strategy_id}/status'
        )
        return response.json()

# 使用示例
client = StrategyTradeClient()

# 1. 创建策略
result = client.create_strategy(
    strategy_type='RSI_Strategy',
    name='my_rsi_strategy',
    config={
        'symbol': 'BTC-USDT-SWAP',
        'timeframe': '1h',
        'rsi_period': 14,
        'rsi_oversold': 30,
        'rsi_overbought': 70
    }
)
strategy_id = result['strategy_id']

# 2. 启动策略（演示账户）
client.start_strategy(
    strategy_id=strategy_id,
    config={
        'symbol': 'BTC-USDT-SWAP',
        'exchange': 'okx',
        'is_demo': True,  # 演示账户
        'initial_capital': 1000.0
    }
)

# 3. 查看状态
status = client.get_status(strategy_id)
print(status)

# 4. 停止策略
client.stop_strategy(strategy_id, close_positions=True)
```

---

## ❓ 常见问题

### Q1: 如何查看策略实盘日志？

**A**: 日志位于 `logs/strategy_{strategy_id}.log`

```bash
tail -f logs/strategy_abc-123-def.log
```

### Q2: 策略信号为什么没有执行？

**A**: 检查以下几点：
1. 风险检查是否通过（查看日志）
2. WebSocket 连接是否正常
3. 资金是否充足
4. 策略是否处于运行状态

### Q3: 如何从演示账户切换到实盘？

**A**: 修改启动配置中的 `is_demo` 参数：

```json
{
  "is_demo": false  // 改为 false
}
```

**⚠️ 警告**：切换到实盘前请确保策略经过充分测试！

### Q4: 如何同时运行多个策略？

**A**: 创建多个策略实例并分别启动：

```python
# 策略1: RSI
strategy1_id = client.create_strategy('RSI_Strategy', 'rsi_btc', {...})
client.start_strategy(strategy1_id, {...})

# 策略2: MA Cross
strategy2_id = client.create_strategy('MA_Cross_Strategy', 'ma_eth', {...})
client.start_strategy(strategy2_id, {...})
```

### Q5: 如何自定义新策略？

**A**: 参考 [策略开发指南](STRATEGY_DEVELOPMENT.md)

---

## 🔧 故障排除

### 问题1: WebSocket 连接失败

**症状**：日志显示 "WebSocket连接失败"

**解决**：
1. 检查网络连接
2. 确认 OKX API 可访问
3. 检查防火墙设置

### 问题2: 订单执行失败

**症状**：产生信号但订单未提交

**解决**：
1. 检查 API 密钥配置
2. 确认账户余额充足
3. 查看风险检查日志

### 问题3: 策略状态异常

**症状**：策略显示 ERROR 状态

**解决**：
```bash
# 查看详细日志
tail -n 100 logs/strategy_{strategy_id}.log

# 重启策略
curl -X POST http://localhost:5000/api/v1/strategy-trade/strategies/{id}/stop
curl -X POST http://localhost:5000/api/v1/strategy-trade/strategies/{id}/start -d '...'
```

---

## 📚 相关文档

- [回测系统文档](BACKTEST_OPTIMIZATION.md)
- [策略开发指南](STRATEGY_DEVELOPMENT.md)
- [风险控制文档](RISK_CONTROL.md)
- [OKX API 文档](OKX_API_OPTIMIZATION.md)

---

**文档维护者**：Follow Trade Team  
**最后更新**：2025年10月23日  
**下一步**：完善数据库表结构和性能监控 🚀

