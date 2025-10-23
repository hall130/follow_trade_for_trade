# 📚 文档索引

> 快速找到你需要的文档

---

## 🎯 我应该看哪个文档？

### 🆕 新用户（第一次使用）

**推荐阅读顺序**：

1. **[用户使用手册](USER_MANUAL.md)** ⭐ 最重要
   - 涵盖所有模块的使用方法
   - 包含完整的操作示例
   - 5分钟快速上手

2. **[策略实盘快速启动](QUICK_START_LIVE_TRADING.md)**
   - 如果你想使用策略自动交易
   - 5分钟启动指南

3. **主 [README.md](../README.md)**
   - 项目整体介绍
   - 系统架构说明

---

## 📖 按功能模块查找

### 1️⃣ 信号源跟单

**使用文档**：
- [用户使用手册 - 信号源跟单](USER_MANUAL.md#2-信号源跟单)
- [用户使用手册 - 限价跟单](USER_MANUAL.md#3-限价跟单)

**你能做什么**：
- 监听专业交易员的交易
- 自动按比例跟单
- 设置触发条件跟单

---

### 2️⃣ 策略回测

**使用文档**：
- [用户使用手册 - 策略回测](USER_MANUAL.md#4-策略回测)
- [回测系统优化文档](BACKTEST_OPTIMIZATION.md)

**你能做什么**：
- 使用历史数据测试策略
- 查看策略表现指标
- 优化策略参数

---

### 3️⃣ 策略实盘交易

**使用文档**：
- [策略实盘快速启动](QUICK_START_LIVE_TRADING.md) ⭐ 推荐
- [用户使用手册 - 策略实盘](USER_MANUAL.md#5-策略实盘)
- [策略实盘集成文档](STRATEGY_LIVE_TRADING_INTEGRATION.md)（技术细节）

**你能做什么**：
- 策略自动交易（从数据到订单全自动）
- 实时监控策略表现
- 支持演示账户安全测试

---

### 4️⃣ 风险管理

**使用文档**：
- [用户使用手册 - 风险管理](USER_MANUAL.md#6-风险管理)

**你能做什么**：
- 设置止损止盈
- 控制杠杆和仓位
- 紧急停止交易

---

### 5️⃣ 前端界面

**使用文档**：
- [用户使用手册 - 前端界面](USER_MANUAL.md#7-前端界面)
- [前端文档](FRONTEND.md)

**你能做什么**：
- 可视化管理所有功能
- 查看图表和报告
- 实时监控系统状态

---

## 🔧 按技术主题查找

### API 开发

- [API 文档](API_DOCS.md)
- [用户使用手册 - API速查](USER_MANUAL.md#13-快速参考)

### OKX 交易所集成

- [OKX API 优化文档](OKX_API_OPTIMIZATION.md)
- 解决了历史数据加载、超时、参数错误等问题

### 前端图表

- [前端图表修复文档](FRONTEND_CHART_FIX.md)
- 解决了 LightweightCharts "Value is null" 错误

### 回测系统

- [回测优化文档](BACKTEST_OPTIMIZATION.md)
- 循环分页加载、无限历史数据支持

### 策略开发

- [策略实盘集成文档](STRATEGY_LIVE_TRADING_INTEGRATION.md)
- 如何开发和部署新策略

---

## 🆘 遇到问题？

### 常见问题

查看 [用户使用手册 - 故障排查](USER_MANUAL.md#10-故障排查)

包括：
- 系统无法启动
- 跟单不执行
- 策略不产生交易
- 网络连接问题

### 日志查看

查看 [用户使用手册 - 日志查看](USER_MANUAL.md#9-日志查看)

### 性能优化

查看 [用户使用手册 - 性能优化](USER_MANUAL.md#11-性能优化建议)

---

## 📊 文档地图

```
docs/
│
├── 📘 INDEX.md (本文件)
│   └── 文档索引和导航
│
├── 📕 USER_MANUAL.md ⭐ 重点
│   ├── 所有模块使用方法
│   ├── 完整操作示例
│   ├── 故障排查
│   └── 最佳实践
│
├── 📗 QUICK_START_LIVE_TRADING.md
│   └── 5分钟启动策略实盘
│
├── 📙 STRATEGY_LIVE_TRADING_INTEGRATION.md
│   ├── 策略实盘技术架构
│   ├── 集成步骤详解
│   └── API 接口文档
│
├── 📔 BACKTEST_OPTIMIZATION.md
│   └── 回测系统优化详解
│
├── 📓 OKX_API_OPTIMIZATION.md
│   └── OKX API 使用和优化
│
├── 📒 FRONTEND_CHART_FIX.md
│   └── 前端图表问题修复
│
├── 📖 API_DOCS.md
│   └── API 接口文档
│
└── 📄 FRONTEND.md
    └── 前端开发文档
```

---

## 🚀 快速链接

### 最常用文档

| 文档 | 适用场景 | 阅读时间 |
|------|----------|----------|
| [用户使用手册](USER_MANUAL.md) | 日常使用、查询命令 | 10-15分钟 |
| [策略实盘快速启动](QUICK_START_LIVE_TRADING.md) | 启动策略交易 | 5分钟 |
| [主 README](../README.md) | 了解项目全貌 | 15-20分钟 |

### 专题文档

| 专题 | 文档 | 阅读时间 |
|------|------|----------|
| 信号源跟单 | [用户手册 - 第2节](USER_MANUAL.md#2-信号源跟单) | 5分钟 |
| 限价跟单 | [用户手册 - 第3节](USER_MANUAL.md#3-限价跟单) | 5分钟 |
| 策略回测 | [用户手册 - 第4节](USER_MANUAL.md#4-策略回测) | 5分钟 |
| 策略实盘 | [用户手册 - 第5节](USER_MANUAL.md#5-策略实盘) | 5分钟 |
| 风险管理 | [用户手册 - 第6节](USER_MANUAL.md#6-风险管理) | 5分钟 |

### 技术文档

| 主题 | 文档 | 适用人群 |
|------|------|----------|
| API 开发 | [API_DOCS.md](API_DOCS.md) | 开发者 |
| 策略开发 | [策略集成文档](STRATEGY_LIVE_TRADING_INTEGRATION.md) | 策略开发者 |
| 前端开发 | [FRONTEND.md](FRONTEND.md) | 前端开发者 |
| 系统集成 | [策略集成文档](STRATEGY_LIVE_TRADING_INTEGRATION.md) | 系统管理员 |

---

## 💡 使用建议

### 🆕 第一次使用

```
Step 1: 阅读主 README.md (了解项目)
   ↓
Step 2: 阅读用户使用手册 (学会操作)
   ↓
Step 3: 根据需求查看专题文档
   ↓
Step 4: 开始使用！
```

### 🔍 遇到具体问题

```
Step 1: 查看用户使用手册 - 故障排查
   ↓
Step 2: 查看日志 (tail -f trades.log)
   ↓
Step 3: 查看相关专题文档
   ↓
Step 4: 搜索文档关键词
```

### 🛠️ 开发和定制

```
Step 1: 阅读系统架构 (README.md)
   ↓
Step 2: 阅读 API 文档
   ↓
Step 3: 查看具体模块的技术文档
   ↓
Step 4: 开始开发！
```

---

## 🔖 快捷搜索

按 `Ctrl+F` 搜索关键词：

- **信号源** → [用户手册 #2](USER_MANUAL.md#2-信号源跟单)
- **跟单** → [用户手册 #2](USER_MANUAL.md#2-信号源跟单), [#3](USER_MANUAL.md#3-限价跟单)
- **回测** → [用户手册 #4](USER_MANUAL.md#4-策略回测)
- **实盘** → [快速启动](QUICK_START_LIVE_TRADING.md), [用户手册 #5](USER_MANUAL.md#5-策略实盘)
- **风险** → [用户手册 #6](USER_MANUAL.md#6-风险管理)
- **API** → [API文档](API_DOCS.md), [用户手册 #13](USER_MANUAL.md#13-快速参考)
- **前端** → [用户手册 #7](USER_MANUAL.md#7-前端界面), [前端文档](FRONTEND.md)
- **故障** → [用户手册 #10](USER_MANUAL.md#10-故障排查)
- **日志** → [用户手册 #9](USER_MANUAL.md#9-日志查看)
- **配置** → [用户手册 - 附录](USER_MANUAL.md#附录-配置文件参考)

---

## ⚡ 一句话指南

| 我想... | 看这个 | 时间 |
|---------|--------|------|
| 快速上手 | [用户使用手册](USER_MANUAL.md) | 10分钟 |
| 启动策略实盘 | [快速启动](QUICK_START_LIVE_TRADING.md) | 5分钟 |
| 配置信号源跟单 | [用户手册 #2](USER_MANUAL.md#2-信号源跟单) | 5分钟 |
| 运行策略回测 | [用户手册 #4](USER_MANUAL.md#4-策略回测) | 5分钟 |
| 设置风险参数 | [用户手册 #6](USER_MANUAL.md#6-风险管理) | 3分钟 |
| 解决问题 | [用户手册 #10](USER_MANUAL.md#10-故障排查) | 按需 |
| 开发API | [API文档](API_DOCS.md) | 20分钟 |
| 开发策略 | [策略集成文档](STRATEGY_LIVE_TRADING_INTEGRATION.md) | 30分钟 |

---

**提示**: 建议将本页加入书签，方便快速查找文档！ 📌

**版本**: v1.0  
**最后更新**: 2025年10月23日

