# 跟单交易系统 - 用户使用手册

> 📖 简洁版使用手册 - 涵盖所有核心模块  
> 🎯 目标：5分钟快速上手，轻松使用所有功能

---

## 📑 目录

1. [系统启动](#1-系统启动)
2. [信号源跟单](#2-信号源跟单)
3. [限价跟单](#3-限价跟单)
4. [策略回测](#4-策略回测)
5. [策略实盘](#5-策略实盘)
6. [风险管理](#6-风险管理)
7. [前端界面](#7-前端界面)

---

## 1. 系统启动

### 启动命令

```bash
# 启动所有模块（推荐）
python main.py

# 仅启动API服务器
python main.py api

# 使用演示账户
python main.py --demo

# 使用实盘账户（⚠️ 谨慎）
python main.py --real
```

### 访问地址

- **前端界面**: http://localhost:8080
- **API 服务**: http://localhost:5000
- **健康检查**: http://localhost:5000/health

### 验证启动

```bash
# 检查系统状态
curl http://localhost:5000/health

# 预期响应
{
  "status": "healthy",
  "timestamp": "2025-10-23T10:00:00Z"
}
```

---

## 2. 信号源跟单

### 功能说明

监听指定信号源账户的交易，自动跟单到你的客户账户。

### 2.1 添加信号源

**方法1: 通过前端界面**

1. 访问 http://localhost:8080
2. 进入"信号源管理"
3. 点击"添加信号源"
4. 填写信号源信息

**方法2: 通过API**

```bash
curl -X POST http://localhost:5000/api/v1/signal-sources \
  -H "Content-Type: application/json" \
  -d '{
    "unique_code": "BFF0B05FDCC878AA",
    "name": "专业交易员A",
    "exchange": "okx",
    "is_enabled": true
  }'
```

### 2.2 配置跟单策略

```bash
curl -X POST http://localhost:5000/api/v1/strategies \
  -H "Content-Type: application/json" \
  -d '{
    "name": "跟单策略1",
    "signal_source_id": "BFF0B05FDCC878AA",
    "follow_ratio": 0.5,
    "max_leverage": 3.0,
    "symbols": ["BTC-USDT-SWAP", "ETH-USDT-SWAP"]
  }'
```

### 2.3 绑定客户账户

```bash
curl -X POST http://localhost:5000/api/v1/customers \
  -H "Content-Type: application/json" \
  -d '{
    "unique_code": "YOUR_ACCOUNT_ID",
    "api_key": "YOUR_API_KEY",
    "api_secret": "YOUR_API_SECRET",
    "passphrase": "YOUR_PASSPHRASE",
    "strategy_id": "strategy_123"
  }'
```

### 2.4 查看跟单记录

```bash
# 查看所有跟单记录
curl http://localhost:5000/api/v1/follow-trades

# 查看特定策略的跟单记录
curl http://localhost:5000/api/v1/follow-trades?strategy_id=strategy_123
```

---

## 3. 限价跟单

### 功能说明

当信号源账户达到指定条件时（如仓位、盈亏），自动执行跟单。

### 3.1 创建限价跟单规则

```bash
curl -X POST http://localhost:5000/api/v1/limit-follow/rules \
  -H "Content-Type: application/json" \
  -d '{
    "name": "BTC达到100手时跟单",
    "signal_source": "BFF0B05FDCC878AA",
    "symbol": "BTC-USDT-SWAP",
    "trigger_condition": {
      "type": "position",
      "threshold": 100,
      "operator": ">=",
      "direction": "LONG"
    },
    "follow_action": {
      "ratio": 0.3,
      "max_position": 30
    },
    "is_enabled": true
  }'
```

### 3.2 条件类型

| 类型 | 说明 | 示例 |
|------|------|------|
| `position` | 仓位数量 | 持仓 ≥ 100 手 |
| `pnl` | 盈亏金额 | 盈利 ≥ 1000 USDT |
| `price` | 价格触发 | BTC 价格 ≥ 70000 |
| `time` | 时间触发 | 每天 09:00 |

### 3.3 查看限价跟单状态

```bash
# 查看所有规则
curl http://localhost:5000/api/v1/limit-follow/rules

# 查看规则执行历史
curl http://localhost:5000/api/v1/limit-follow/executions?rule_id=rule_123
```

### 3.4 启动/停止规则

```bash
# 启动规则
curl -X POST http://localhost:5000/api/v1/limit-follow/rules/rule_123/enable

# 停止规则
curl -X POST http://localhost:5000/api/v1/limit-follow/rules/rule_123/disable

# 删除规则
curl -X DELETE http://localhost:5000/api/v1/limit-follow/rules/rule_123
```

---

## 4. 策略回测

### 功能说明

使用历史数据测试策略表现，无需实盘资金。

### 4.1 运行回测

```bash
curl -X POST http://localhost:5000/api/v1/strategy/backtests \
  -H "Content-Type: application/json" \
  -d '{
    "strategy_name": "template_RSI_Strategy",
    "symbol": "BTC-USDT-SWAP",
    "timeframe": "1h",
    "start_date": "2025-07-23",
    "end_date": "2025-10-22",
    "initial_capital": 10000,
    "config": {
      "rsi_period": 14,
      "rsi_oversold": 30,
      "rsi_overbought": 70,
      "stop_loss_pct": 0.03,
      "take_profit_pct": 0.06
    }
  }'
```

### 4.2 支持的策略

| 策略类型 | strategy_name | 适用场景 |
|---------|---------------|---------|
| RSI策略 | `template_RSI_Strategy` | 震荡行情 |
| 均线交叉 | `template_MA_Cross_Strategy` | 趋势行情 |
| 布林带 | `template_Bollinger_Strategy` | 波动行情 |
| MACD | `template_MACD_Strategy` | 趋势确认 |

### 4.3 查看回测结果

```bash
# 查看所有回测
curl http://localhost:5000/api/v1/strategy/backtests

# 查看特定回测详情
curl http://localhost:5000/api/v1/strategy/backtests/{backtest_id}
```

### 4.4 回测结果指标

```json
{
  "total_return": 0.15,        // 总收益率 15%
  "annual_return": 0.45,       // 年化收益率 45%
  "max_drawdown": -0.12,       // 最大回撤 12%
  "sharpe_ratio": 1.8,         // 夏普比率
  "win_rate": 0.65,            // 胜率 65%
  "total_trades": 50,          // 总交易次数
  "equity_curve": [...],       // 资金曲线
  "trade_history": [...]       // 交易记录
}
```

---

## 5. 策略实盘

### 功能说明

将策略自动化运行在实盘，从数据接收到订单执行全自动。

### 5.1 创建策略实例

```bash
curl -X POST http://localhost:5000/api/v1/strategy-live/strategies \
  -H "Content-Type: application/json" \
  -d '{
    "strategy_type": "RSI_Strategy",
    "name": "my_rsi_btc",
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
```

### 5.2 启动策略实盘

```bash
curl -X POST http://localhost:5000/api/v1/strategy-live/strategies/{strategy_id}/start \
  -H "Content-Type: application/json" \
  -d '{
    "symbol": "BTC-USDT-SWAP",
    "exchange": "okx",
    "is_demo": true,              // ⭐ 首次使用演示账户
    "initial_capital": 1000.0,
    "max_position_value": 500.0,
    "stop_loss_pct": 0.03,
    "take_profit_pct": 0.06
  }'
```

### 5.3 监控策略状态

```bash
# 查看策略状态
curl http://localhost:5000/api/v1/strategy-live/strategies/{strategy_id}/status

# 响应示例
{
  "status": "RUNNING",
  "symbol": "BTC-USDT-SWAP",
  "is_demo": true,
  "running_time": "01:30:45",
  "has_ws_connection": true,
  "current_positions": 1,
  "today_pnl": 25.50,
  "total_trades": 3
}
```

### 5.4 停止策略

```bash
# 停止策略并平仓
curl -X POST http://localhost:5000/api/v1/strategy-live/strategies/{strategy_id}/stop \
  -H "Content-Type: application/json" \
  -d '{
    "close_positions": true
  }'

# 停止策略但保留持仓
curl -X POST http://localhost:5000/api/v1/strategy-live/strategies/{strategy_id}/stop \
  -d '{"close_positions": false}'
```

### 5.5 查看实盘交易记录

```bash
# 查看所有运行中的策略
curl http://localhost:5000/api/v1/strategy-live/strategies

# 查看策略交易历史
curl http://localhost:5000/api/v1/strategy-live/strategies/{strategy_id}/trades
```

---

## 6. 风险管理

### 6.1 设置全局风险参数

```bash
curl -X PUT http://localhost:5000/api/v1/risk/global \
  -H "Content-Type: application/json" \
  -d '{
    "max_daily_loss": 0.05,        // 最大日亏损 5%
    "max_total_loss": 0.20,        // 最大总亏损 20%
    "max_leverage": 3.0,           // 最大杠杆 3倍
    "max_position_value": 10000,   // 单仓最大价值
    "emergency_stop": false        // 紧急停止开关
  }'
```

### 6.2 设置策略级风险参数

```bash
curl -X PUT http://localhost:5000/api/v1/strategies/{strategy_id}/risk \
  -H "Content-Type: application/json" \
  -d '{
    "max_positions": 3,
    "position_sizing": "fixed",
    "stop_loss_pct": 0.03,
    "take_profit_pct": 0.06,
    "trailing_stop": true,
    "trailing_stop_pct": 0.02
  }'
```

### 6.3 查看风险指标

```bash
# 查看当前风险状态
curl http://localhost:5000/api/v1/risk/status

# 响应示例
{
  "total_exposure": 5000.0,      // 总敞口
  "leverage_ratio": 2.5,         // 当前杠杆
  "daily_pnl": -150.0,          // 今日盈亏
  "daily_loss_pct": -0.015,     // 日亏损率 1.5%
  "total_pnl": 1200.0,          // 总盈亏
  "risk_level": "MEDIUM",        // 风险等级
  "warnings": []                 // 风险警告
}
```

### 6.4 紧急止损

```bash
# 立即平掉所有仓位
curl -X POST http://localhost:5000/api/v1/risk/emergency-stop

# 恢复交易
curl -X POST http://localhost:5000/api/v1/risk/resume
```

---

## 7. 前端界面

### 7.1 访问前端

浏览器访问: http://localhost:8080

### 7.2 主要页面

| 页面 | 路径 | 功能 |
|------|------|------|
| 仪表盘 | `/` | 总览、实时数据 |
| 信号源管理 | `/signal-sources` | 管理信号源 |
| 策略管理 | `/strategies` | 管理跟单策略 |
| 回测系统 | `/backtest` | 策略回测 |
| 限价跟单 | `/limit-follow` | 限价跟单配置 |
| 风险控制 | `/risk` | 风险参数设置 |
| 交易记录 | `/trades` | 查看历史交易 |

### 7.3 使用流程

#### 信号源跟单流程
```
1. 添加信号源
   ↓
2. 创建跟单策略
   ↓
3. 配置跟单比例、杠杆等参数
   ↓
4. 绑定客户账户
   ↓
5. 启动监听
   ↓
6. 系统自动跟单
```

#### 策略回测流程
```
1. 选择策略类型
   ↓
2. 配置策略参数
   ↓
3. 设置回测时间范围
   ↓
4. 运行回测
   ↓
5. 查看回测结果（图表、指标）
   ↓
6. 优化参数（可选）
   ↓
7. 满意后启动实盘
```

#### 策略实盘流程
```
1. 创建策略实例
   ↓
2. 配置实盘参数（演示/实盘）
   ↓
3. 启动策略
   ↓
4. 监控运行状态
   ↓
5. 查看交易记录
   ↓
6. 根据表现调整参数或停止
```

---

## 8. 常用操作示例

### 8.1 完整的跟单设置

```bash
# 1. 添加信号源
SIGNAL_ID="BFF0B05FDCC878AA"
curl -X POST http://localhost:5000/api/v1/signal-sources \
  -d "{\"unique_code\": \"$SIGNAL_ID\", \"name\": \"专业交易员\", \"is_enabled\": true}"

# 2. 创建跟单策略
STRATEGY_RESPONSE=$(curl -X POST http://localhost:5000/api/v1/strategies \
  -d "{\"name\": \"跟单策略A\", \"signal_source_id\": \"$SIGNAL_ID\", \"follow_ratio\": 0.5}")
STRATEGY_ID=$(echo $STRATEGY_RESPONSE | jq -r '.id')

# 3. 添加客户账户
curl -X POST http://localhost:5000/api/v1/customers \
  -d "{\"api_key\": \"YOUR_KEY\", \"strategy_id\": \"$STRATEGY_ID\"}"

# 4. 查看跟单状态
curl http://localhost:5000/api/v1/follow-trades?strategy_id=$STRATEGY_ID
```

### 8.2 完整的策略交易流程

```bash
# 1. 先回测验证策略
BACKTEST_RESPONSE=$(curl -X POST http://localhost:5000/api/v1/strategy/backtests \
  -d '{
    "strategy_name": "template_RSI_Strategy",
    "symbol": "BTC-USDT-SWAP",
    "timeframe": "1h",
    "start_date": "2025-09-01",
    "end_date": "2025-10-22",
    "initial_capital": 10000
  }')

# 2. 查看回测结果
BACKTEST_ID=$(echo $BACKTEST_RESPONSE | jq -r '.backtest_id')
curl http://localhost:5000/api/v1/strategy/backtests/$BACKTEST_ID

# 3. 如果回测满意，创建实盘策略
STRATEGY_RESPONSE=$(curl -X POST http://localhost:5000/api/v1/strategy-live/strategies \
  -d '{
    "strategy_type": "RSI_Strategy",
    "name": "live_rsi_btc",
    "config": {"symbol": "BTC-USDT-SWAP", "timeframe": "1h"}
  }')
STRATEGY_ID=$(echo $STRATEGY_RESPONSE | jq -r '.strategy_id')

# 4. 启动策略（演示账户）
curl -X POST http://localhost:5000/api/v1/strategy-live/strategies/$STRATEGY_ID/start \
  -d '{"is_demo": true, "initial_capital": 1000}'

# 5. 监控策略
curl http://localhost:5000/api/v1/strategy-live/strategies/$STRATEGY_ID/status
```

---

## 9. 日志查看

### 9.1 查看系统日志

```bash
# 实时查看主日志
tail -f trades.log

# 查看最近100行
tail -n 100 trades.log

# 搜索错误日志
grep "ERROR" trades.log

# 搜索特定策略的日志
grep "strategy_abc123" trades.log
```

### 9.2 日志级别

| 级别 | 说明 | 示例 |
|------|------|------|
| `INFO` | 正常信息 | 策略启动、交易执行 |
| `WARNING` | 警告信息 | 接近风险限制 |
| `ERROR` | 错误信息 | API调用失败 |
| `DEBUG` | 调试信息 | 详细执行流程 |

---

## 10. 故障排查

### 10.1 系统无法启动

```bash
# 检查端口占用
netstat -ano | findstr :5000
netstat -ano | findstr :8080

# 检查数据库连接
python -c "from database.db import get_db_pool; pool = get_db_pool(); print('数据库连接成功')"

# 查看详细错误
python main.py 2>&1 | tee startup.log
```

### 10.2 跟单不执行

**检查清单**：
```bash
# 1. 信号源是否启用
curl http://localhost:5000/api/v1/signal-sources/{signal_id}

# 2. 策略是否启用
curl http://localhost:5000/api/v1/strategies/{strategy_id}

# 3. 客户账户API是否有效
curl http://localhost:5000/api/v1/customers/test-connection

# 4. 查看跟单监控日志
grep "跟单" trades.log | tail -20
```

### 10.3 策略不产生交易

**检查清单**：
```bash
# 1. 策略是否在运行
curl http://localhost:5000/api/v1/strategy-live/strategies/{id}/status

# 2. WebSocket连接是否正常
grep "WebSocket" trades.log | tail -10

# 3. 是否收到市场数据
grep "市场数据" trades.log | tail -10

# 4. 策略参数是否合理（如RSI阈值不要太极端）
# RSI 超卖 < 35, 超买 > 65 较合理
```

### 10.4 网络连接问题

```bash
# 测试OKX连接
curl https://www.okx.com/api/v5/public/time

# 运行连接测试脚本
python test_okx_connection.py

# 检查代理设置
echo $HTTP_PROXY
echo $HTTPS_PROXY
```

---

## 11. 性能优化建议

### 11.1 数据库优化

```sql
-- 定期清理旧数据（保留3个月）
DELETE FROM trades WHERE timestamp < DATE_SUB(NOW(), INTERVAL 3 MONTH);

-- 添加索引
CREATE INDEX idx_timestamp ON trades(timestamp);
CREATE INDEX idx_strategy ON trades(strategy_id);
```

### 11.2 系统资源

```bash
# 监控系统资源
python -c "import psutil; print(f'CPU: {psutil.cpu_percent()}%, 内存: {psutil.virtual_memory().percent}%')"

# 如果内存占用过高，重启系统
python main.py api  # 轻量级启动
```

---

## 12. 安全建议

### 12.1 API密钥管理

```bash
# ❌ 不要在代码中硬编码密钥
api_key = "hardcoded_key"

# ✅ 使用环境变量
export OKX_API_KEY="your_key"
export OKX_API_SECRET="your_secret"
export OKX_PASSPHRASE="your_passphrase"
```

### 12.2 风险控制

```
✅ 推荐设置：
- 日最大亏损: 2-5%
- 总最大亏损: 10-20%
- 最大杠杆: 1-3倍
- 单仓最大: 总资金的20-30%

❌ 避免：
- 日亏损 > 10%
- 杠杆 > 5倍
- 单仓 > 50%
```

### 12.3 实盘交易流程

```
1. 演示账户测试 (1-2周)
   ↓
2. 小额实盘 (≤1000 USDT, 1-2周)
   ↓
3. 逐步增加资金 (根据表现)
   ↓
4. 多策略组合 (分散风险)
```

---

## 13. 快速参考

### API端点速查

```bash
# 系统状态
GET  /health

# 信号源
POST /api/v1/signal-sources          # 添加信号源
GET  /api/v1/signal-sources          # 列出信号源
PUT  /api/v1/signal-sources/{id}     # 更新信号源

# 跟单策略
POST /api/v1/strategies              # 创建策略
GET  /api/v1/strategies              # 列出策略
PUT  /api/v1/strategies/{id}         # 更新策略

# 策略回测
POST /api/v1/strategy/backtests      # 运行回测
GET  /api/v1/strategy/backtests      # 查看回测列表
GET  /api/v1/strategy/backtests/{id} # 查看回测详情

# 策略实盘
POST /api/v1/strategy-live/strategies            # 创建策略
POST /api/v1/strategy-live/strategies/{id}/start # 启动
POST /api/v1/strategy-live/strategies/{id}/stop  # 停止
GET  /api/v1/strategy-live/strategies/{id}/status # 状态

# 限价跟单
POST /api/v1/limit-follow/rules      # 创建规则
GET  /api/v1/limit-follow/rules      # 列出规则
PUT  /api/v1/limit-follow/rules/{id} # 更新规则

# 风险管理
GET  /api/v1/risk/status             # 风险状态
PUT  /api/v1/risk/global             # 全局风险参数
POST /api/v1/risk/emergency-stop     # 紧急停止
```

---

## 14. 获取帮助

### 文档资源

- 📖 [快速启动指南](QUICK_START_LIVE_TRADING.md)
- 📚 [策略实盘集成文档](STRATEGY_LIVE_TRADING_INTEGRATION.md)
- 🔧 [回测系统文档](BACKTEST_OPTIMIZATION.md)
- 🌐 [OKX API文档](OKX_API_OPTIMIZATION.md)

### 常见问题

访问项目 Issues 或查看日志文件 `trades.log`

### 技术支持

如遇到问题：
1. 查看日志: `tail -f trades.log`
2. 检查系统状态: `curl http://localhost:5000/health`
3. 参考文档中的"故障排查"章节

---

## 附录: 配置文件参考

### A. 交易所配置

```python
# config/okx_config.py
OKX_CONFIG = {
    'api_key': 'YOUR_API_KEY',
    'api_secret': 'YOUR_API_SECRET',
    'passphrase': 'YOUR_PASSPHRASE',
    'is_demo': True,  # 演示账户
    'timeout': 60,
    'retry_times': 3
}
```

### B. 风险配置

```python
# config/risk_config.py
RISK_CONFIG = {
    'max_daily_loss': 0.05,      # 5%
    'max_total_loss': 0.20,      # 20%
    'max_leverage': 3.0,         # 3倍
    'stop_loss_pct': 0.03,       # 3%
    'take_profit_pct': 0.06      # 6%
}
```

---

**版本**: v1.0  
**最后更新**: 2025年10月23日  
**维护者**: Follow Trade Team

🎉 祝您使用愉快！记住：**风险控制永远第一！** 🛡️

