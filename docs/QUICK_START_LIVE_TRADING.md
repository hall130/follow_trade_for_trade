# 策略交易实盘快速启动指南

> 🚀 5分钟快速启动策略交易实盘

## 🎯 系统架构说明

策略交易系统**已经集成到主系统**中，启动 `main.py` 时自动加载：

```
python main.py  # 自动启动所有模块，包括策略交易
```

系统启动时会自动：
1. ✅ 初始化数据库连接
2. ✅ 启动 API 服务器 (端口 5000)
3. ✅ 启动跟单交易服务
4. ✅ **启动策略交易服务**  ← 新增！
5. ✅ 启动前端界面 (端口 8080)

---

##  ⚡ 快速启动

### 1. 启动系统

```bash
# 方式1: 启动所有服务（推荐）
python main.py

# 方式2: 仅启动API服务器（包含策略交易）
python main.py api

# 方式3: 使用演示账户
python main.py --demo
```

### 2. 验证策略交易服务

```bash
# 检查策略交易服务状态
curl http://localhost:5000/api/v1/strategy-trade/health

# 预期响应：
# {
#   "success": true,
#   "data": {
#     "module_available": true,
#     "status": "healthy"
#   }
# }
```

---

## 📝 使用示例

### 示例1：创建并启动RSI策略（演示账户）

```bash
# Step 1: 创建策略
curl -X POST http://localhost:5000/api/v1/strategy-live/strategies \
  -H "Content-Type: application/json" \
  -d '{
    "strategy_type": "RSI_Strategy",
    "name": "demo_rsi_btc",
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

# 响应示例：
# {
#   "success": true,
#   "strategy_id": "550e8400-e29b-41d4-a716-446655440000",
#   "message": "策略创建成功"
# }

# Step 2: 启动策略（使用演示账户）
curl -X POST http://localhost:5000/api/v1/strategy-live/strategies/{strategy_id}/start \
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

# 响应示例：
# {
#   "success": true,
#   "message": "策略已启动"
# }

# Step 3: 查看策略状态
curl http://localhost:5000/api/v1/strategy-live/strategies/{strategy_id}/status

# 响应示例：
# {
#   "success": true,
#   "data": {
#     "status": "RUNNING",
#     "strategy_id": "550e8400-e29b-41d4-a716-446655440000",
#     "symbol": "BTC-USDT-SWAP",
#     "exchange": "okx",
#     "is_demo": true,
#     "running_time": "00:15:30",
#     "has_ws_connection": true
#   }
# }

# Step 4: 停止策略
curl -X POST http://localhost:5000/api/v1/strategy-live/strategies/{strategy_id}/stop \
  -H "Content-Type: application/json" \
  -d '{
    "close_positions": true
  }'
```

### 示例2：Python 客户端

```python
import requests

BASE_URL = 'http://localhost:5000'

# 1. 创建策略
response = requests.post(
    f'{BASE_URL}/api/v1/strategy-live/strategies',
    json={
        'strategy_type': 'RSI_Strategy',
        'name': 'my_rsi_strategy',
        'config': {
            'symbol': 'BTC-USDT-SWAP',
            'timeframe': '1h',
            'rsi_period': 14,
            'rsi_oversold': 30,
            'rsi_overbought': 70
        }
    }
)
result = response.json()
strategy_id = result['strategy_id']
print(f"策略已创建: {strategy_id}")

# 2. 启动策略（演示账户）
response = requests.post(
    f'{BASE_URL}/api/v1/strategy-live/strategies/{strategy_id}/start',
    json={
        'symbol': 'BTC-USDT-SWAP',
        'exchange': 'okx',
        'is_demo': True,  # 演示账户
        'initial_capital': 1000.0
    }
)
print(f"策略启动结果: {response.json()}")

# 3. 查看状态
response = requests.get(
    f'{BASE_URL}/api/v1/strategy-live/strategies/{strategy_id}/status'
)
print(f"策略状态: {response.json()}")

# 4. 停止策略
response = requests.post(
    f'{BASE_URL}/api/v1/strategy-live/strategies/{strategy_id}/stop',
    json={'close_positions': True}
)
print(f"策略停止结果: {response.json()}")
```

---

## 🔍 监控和日志

### 查看实时日志

```bash
# 查看主日志
tail -f trades.log

# 查看策略专用日志（如果有）
tail -f logs/strategy_*.log
```

### 日志内容示例

```
[2025-10-23 10:00:00] [INFO] 🤖 正在初始化策略交易服务...
[2025-10-23 10:00:01] [INFO] ✅ 策略交易服务已初始化并启动
[2025-10-23 10:01:00] [INFO] 📡 策略 abc-123 订阅市场数据: BTC-USDT-SWAP candle1H
[2025-10-23 10:01:05] [INFO] 🔄 策略 abc-123 开始接收实时数据...
[2025-10-23 10:15:00] [INFO] 📊 策略 abc-123 接收数据: 价格=67850.5
[2025-10-23 10:30:00] [INFO] 🎯 策略 abc-123 产生 1 个信号
[2025-10-23 10:30:01] [INFO] ✅ 策略 abc-123 买入订单已提交: order_id=123456789
```

---

## 🛠️ API 接口总览

| 接口 | 方法 | 路径 | 说明 |
|------|------|------|------|
| 创建策略 | POST | `/api/v1/strategy-live/strategies` | 创建新策略 |
| 启动策略 | POST | `/api/v1/strategy-live/strategies/{id}/start` | 启动实盘交易 |
| 停止策略 | POST | `/api/v1/strategy-live/strategies/{id}/stop` | 停止实盘交易 |
| 查看状态 | GET | `/api/v1/strategy-live/strategies/{id}/status` | 获取运行状态 |
| 列出策略 | GET | `/api/v1/strategy-live/strategies` | 列出所有策略 |
| 健康检查 | GET | `/api/v1/strategy-trade/health` | 服务健康状态 |

---

## ⚙️ 配置说明

### 实盘配置参数

```json
{
  "symbol": "BTC-USDT-SWAP",      // 交易对
  "exchange": "okx",               // 交易所
  "is_demo": true,                 // true=演示账户, false=实盘
  "initial_capital": 1000.0,       // 初始资金
  "max_position_value": 500.0,     // 单仓最大价值
  "stop_loss_pct": 0.03,           // 止损 3%
  "take_profit_pct": 0.06          // 止盈 6%
}
```

### 风险提示

⚠️ **首次使用务必设置 `"is_demo": true`**

只有在演示账户运行稳定后，再考虑切换到实盘：
```json
{
  "is_demo": false  // 实盘模式
}
```

---

## 🎯 支持的策略类型

| 策略类型 | strategy_type | 说明 |
|---------|---------------|------|
| RSI策略 | `RSI_Strategy` | 基于RSI指标的超买超卖策略 |
| 均线交叉 | `MA_Cross_Strategy` | 双均线交叉策略 |
| 布林带 | `Bollinger_Strategy` | 布林带突破策略 |
| MACD | `MACD_Strategy` | MACD指标策略 |
| 网格交易 | `Grid_Strategy` | 网格交易策略（开发中） |

---

## ❓ 常见问题

### Q1: 如何确认策略交易服务已启动？

**A**: 检查启动日志，应该看到：
```
[INFO] 🤖 正在初始化策略交易服务...
[INFO] ✅ 策略交易服务已初始化并启动
```

或者访问健康检查接口：
```bash
curl http://localhost:5000/api/v1/strategy-trade/health
```

### Q2: 策略没有产生交易怎么办？

**A**: 检查以下几点：
1. 策略状态是否为 `RUNNING`
2. WebSocket 连接是否正常
3. 查看日志是否有接收到市场数据
4. 策略参数是否合理（RSI阈值不要设置太极端）

### Q3: 如何从演示账户切换到实盘？

**A**: 停止策略后重新启动，修改配置：
```json
{
  "is_demo": false  // 切换到实盘
}
```

⚠️ **务必先在演示账户充分测试！**

### Q4: 系统重启后策略会自动运行吗？

**A**: 目前需要手动重新启动策略。后续版本会支持自动恢复。

---

## 📚 相关文档

- [完整集成文档](STRATEGY_LIVE_TRADING_INTEGRATION.md) - 详细的技术架构和API说明
- [回测系统文档](BACKTEST_OPTIMIZATION.md) - 回测相关功能
- [OKX API文档](OKX_API_OPTIMIZATION.md) - API使用说明

---

## 🆘 获取帮助

如果遇到问题：

1. 查看日志：`tail -f trades.log`
2. 检查服务状态：`curl http://localhost:5000/api/v1/strategy-trade/health`
3. 参考详细文档：`docs/STRATEGY_LIVE_TRADING_INTEGRATION.md`

---

**祝您交易顺利！记住：风险控制永远是第一位的！** 🛡️

