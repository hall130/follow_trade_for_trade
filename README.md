# 🚀 跟单交易系统 (Follow Trade System)

[![Python](https://img.shields.io/badge/Python-3.8+-blue.svg)](https://www.python.org/)
[![Flask](https://img.shields.io/badge/Flask-2.0+-green.svg)](https://flask.palletsprojects.com/)
[![MySQL](https://img.shields.io/badge/MySQL-8.0+-orange.svg)](https://www.mysql.com/)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

> 一个专业的加密货币跟单交易系统，支持多交易所、多客户管理、风险控制和自动化交易

## ⚠️ 重要风险提示

**🔴 本系统仅供学习和研究使用，请谨慎用于实盘交易**

- 加密货币交易具有极高风险，可能导致重大损失
- 建议优先使用交易所演示账户进行测试
- 使用前请充分了解相关风险并做好资金管理
- 建议在专业人士指导下使用

## 📋 目录

- [🎯 项目概述](#-项目概述)
- [🏗️ 系统架构](#️-系统架构)
- [📊 项目进度](#-项目进度)
- [✨ 核心功能](#-核心功能)
- [🚀 快速开始](#-快速开始)
- [📁 项目结构](#-项目结构)
- [🔧 配置说明](#-配置说明)
- [📊 API接口](#-api接口)
- [🎨 前端界面](#-前端界面)
- [🧪 测试说明](#-测试说明)
- [📈 部署指南](#-部署指南)
- [🤝 贡献指南](#-贡献指南)
- [📄 许可证](#-许可证)

## 🎯 项目概述

跟单交易系统是一个**企业级的分布式金融交易系统**，主要功能包括：

- **多交易所支持**: 支持OKX、Binance等主流交易所
- **客户管理**: 完整的客户账户管理和配置
- **信号源管理**: 专业的交易信号源监控和跟单
- **限价跟单**: 智能的限价跟单策略和执行
- **风险控制**: 多层次的风险管理和控制
- **实时监控**: WebSocket实时数据推送和状态监控

## 🏗️ 系统架构

### 完整系统架构图

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                                🌐 前端层 (Frontend Layer)                        │
├─────────────────────────────────────────────────────────────────────────────────┤
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐            │
│  │   主控制台   │  │  客户管理   │  │  信号监控   │  │  限价跟单   │            │
│  │  Dashboard  │  │  Customer   │  │   Signal    │  │ Limit Order │            │
│  │             │  │ Management │  │ Monitoring  │  │ Management  │            │
│  └─────────────┘  └─────────────┘  └─────────────┘  └─────────────┘            │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐            │
│  │  风险控制   │  │  数据分析   │  │  系统设置   │  │  资产分析   │            │
│  │ Risk Control│  │Data Analysis│  │   Settings  │  │Asset Analysis│           │
│  └─────────────┘  └─────────────┘  └─────────────┘  └─────────────┘            │
└─────────────────────────────────────────────────────────────────────────────────┘
                                        │
                                        ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│                              🔌 API服务层 (API Layer)                           │
├─────────────────────────────────────────────────────────────────────────────────┤
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐            │
│  │  客户API    │  │  信号源API  │  │  限价单API  │  │  资产API    │            │
│  │ Customer    │  │ Signal      │  │ Limit Order │  │ Asset       │            │
│  │ API         │  │ Source API  │  │ API         │  │ Analysis API│            │
│  └─────────────┘  └─────────────┘  └─────────────┘  └─────────────┘            │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐            │
│  │  风险API    │  │  监控API    │  │  配置API    │  │  通知API    │            │
│  │ Risk API    │  │ Monitor API │  │ Config API  │  │Notify API   │            │
│  └─────────────┘  └─────────────┘  └─────────────┘  └─────────────┘            │
└─────────────────────────────────────────────────────────────────────────────────┘
                                        │
                                        ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│                            🏢 核心业务层 (Core Business Layer)                   │
├─────────────────────────────────────────────────────────────────────────────────┤
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐            │
│  │  交易服务   │  │  信号服务   │  │  限价跟单   │  │  资产分析   │            │
│  │ Trade       │  │ Signal      │  │ Limit Follow│  │ Asset       │            │
│  │ Service     │  │ Service     │  │ Service     │  │ Analysis    │            │
│  └─────────────┘  └─────────────┘  └─────────────┘  └─────────────┘            │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐            │
│  │  风险控制   │  │  连接管理   │  │  模块管理   │  │  配置管理   │            │
│  │ Risk        │  │ Connection  │  │ Module      │  │ Config      │            │
│  │ Control     │  │ Manager     │  │ Manager     │  │ Manager     │            │
│  └─────────────┘  └─────────────┘  └─────────────┘  └─────────────┘            │
└─────────────────────────────────────────────────────────────────────────────────┘
                                        │
                                        ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│                            🔗 数据访问层 (Data Access Layer)                     │
├─────────────────────────────────────────────────────────────────────────────────┤
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐            │
│  │  数据库     │  │  连接池     │  │  缓存层     │  │  日志系统   │            │
│  │ Database    │  │ Connection  │  │ Cache       │  │ Logging     │            │
│  │ (MySQL)     │  │ Pool        │  │ Layer       │  │ System      │            │
│  └─────────────┘  └─────────────┘  └─────────────┘  └─────────────┘            │
└─────────────────────────────────────────────────────────────────────────────────┘
                                        │
                                        ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│                          🌍 外部服务层 (External Services Layer)                 │
├─────────────────────────────────────────────────────────────────────────────────┤
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐            │
│  │  OKX交易所  │  │ Binance     │  │  钉钉机器人 │  │  其他服务   │            │
│  │ Exchange    │  │ Exchange    │  │ DingTalk    │  │ Other       │            │
│  │ (REST/WS)   │  │ (REST/WS)   │  │ Bot         │  │ Services    │            │
│  └─────────────┘  └─────────────┘  └─────────────┘  └─────────────┘            │
│                                                                                 │
│  🔴 风险提示: 交易所API需要谨慎使用，建议优先使用模拟账户测试                      │
└─────────────────────────────────────────────────────────────────────────────────┘
```

### 技术栈与特性

#### 核心技术
- **后端**: Python 3.8+, Flask, asyncio, WebSocket
- **数据库**: MySQL 8.0, 连接池管理
- **交易所**: OKX + Binance REST/WebSocket API
- **实时通信**: WebSocket长连接，自动重连机制
- **监控**: 系统健康检查，性能监控，错误追踪
- **通知**: 钉钉机器人，多渠道消息推送

#### 系统特性
- **高并发**: 异步处理，连接池管理
- **高可用**: 自动重连，错误恢复，模块化设计
- **实时性**: WebSocket双向通信，毫秒级响应
- **安全性**: API签名，访问控制，数据加密
- **扩展性**: 模块化架构，插件式交易所支持

## 📊 项目进度

### ✅ 已完成功能 (约85%)

| 模块 | 完成度 | 状态 | 说明 |
|------|--------|------|------|
| **基础架构** | 100% | ✅ 完成 | 模块化设计，依赖管理 |
| **数据库层** | 95% | ✅ 完成 | MySQL连接池，数据模型 |
| **API服务器** | 90% | ✅ 完成 | RESTful API，错误处理 |
| **客户管理** | 95% | ✅ 完成 | CRUD操作，配置管理 |
| **信号源管理** | 90% | ✅ 完成 | 信号监听，处理逻辑 |
| **交易服务** | 85% | ✅ 完成 | 异步交易，订单管理 |
| **限价跟单** | 90% | ✅ 完成 | 策略管理，风险控制 |
| **风险控制** | 80% | ✅ 完成 | 杠杆控制，预警机制 |
| **OKX集成** | 95% | ✅ 完成 | REST + WebSocket |
| **Binance集成** | 95% | ✅ 完成 | REST + WebSocket |
| **前端界面** | 75% | ✅ 完成 | 基础UI，数据展示 |
| **配置管理** | 90% | ✅ 完成 | 多环境配置，验证 |
| **日志系统** | 85% | ✅ 完成 | 结构化日志，轮转 |
| **钉钉通知** | 95% | ✅ 完成 | 消息推送，告警 |

### 🚧 进行中功能 (约10%)

| 模块 | 完成度 | 状态 | 说明 |
|------|--------|------|------|
| **资产分析** | 70% | 🚧 开发中 | 趋势分析，风险评估 |
| **性能优化** | 60% | 🚧 开发中 | 缓存层，查询优化 |
| **前端优化** | 80% | 🚧 开发中 | 实时图表，用户体验 |
| **监控告警** | 75% | 🚧 开发中 | 系统监控，自动恢复 |

### 📝 待开发功能 (约5%)

| 模块 | 优先级 | 状态 | 说明 |
|------|--------|------|------|
| **回测系统** | 中 | 📝 规划中 | 策略回测，历史分析 |
| **移动端** | 低 | 📝 规划中 | 移动应用，推送通知 |
| **多语言** | 低 | 📝 规划中 | 国际化支持 |
| **高级策略** | 中 | 📝 规划中 | AI辅助，机器学习 |

### 🎯 里程碑

#### ✅ 已完成里程碑
- **v0.1.0** (2025-04): 基础架构搭建
- **v0.2.0** (2025-05): 核心交易功能
- **v0.3.0** (2025-06): 限价跟单系统
- **v0.4.0** (2025-07): 多交易所支持
- **v0.5.0** (2025-08): 风险控制系统

#### 🚧 进行中里程碑
- **v0.6.0** (2025-09): 系统优化和稳定性提升

#### 📅 计划中里程碑
- **v0.7.0** (2025-10): 高级数据分析
- **v1.0.0** (2026-01): 正式版本发布

## ✨ 核心功能

### 🔄 跟单交易
- 实时信号监控
- 智能跟单策略
- 多级风险控制
- 自动化订单执行

### 👥 客户管理
- 多交易所账户管理
- 个性化配置设置
- 实时资产监控
- 交易历史记录

### 📊 风险控制
- 杠杆限制管理
- 持仓集中度控制
- 实时风险预警
- 自动风险干预

### 📈 数据分析
- 交易性能统计
- 风险分析报告
- 趋势分析图表
- 实时监控面板

## 🚀 未来规划

### 🎯 长期发展目标 (2026-2027)

#### 🤖 AI智能交易系统
- **机器学习策略**: 集成TensorFlow/PyTorch，开发基于深度学习的交易策略
- **自然语言处理**: 支持新闻情感分析，社交媒体情绪监控
- **强化学习**: 实现自适应交易策略，动态优化参数
- **预测模型**: 价格预测、波动率预测、市场趋势分析
- **智能风控**: AI驱动的实时风险评估和预警系统

#### 📊 高级策略交易
- **多因子模型**: 技术指标、基本面数据、宏观经济因子综合分析
- **套利策略**: 跨交易所套利、期现套利、统计套利
- **高频交易**: 微秒级订单执行，低延迟交易系统
- **算法交易**: TWAP、VWAP、冰山订单等专业算法
- **组合管理**: 多策略组合优化，动态资产配置

## 🚀 快速开始

### ⚠️ 使用前必读

**强烈建议在开始使用前：**
1. 优先使用交易所的**演示账户**进行测试
2. 仔细阅读风险提示和使用说明
3. 从小额资金开始测试系统功能
4. 确保充分理解系统的运行机制

### 环境要求

- Python 3.8+
- MySQL 8.0+
- Redis (可选，用于缓存)

### 安装步骤

1. **克隆项目**
```bash
git clone https://github.com/hall130/follow_trade_for_trade.git
cd follow_trade_for_trade
```

2. **安装依赖**
```bash
pip install -r requirements.txt
```

3. **配置数据库**
```bash
# 创建数据库
mysql -u root -p
CREATE DATABASE follow_trade CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

# 导入表结构
mysql -u root -p follow_trade < database/*.sql
```

4. **配置环境变量**
```bash
cp config/config_example.py config/config.py
# 编辑 config.py 文件，填入你的配置信息
# 强烈建议先使用演示账户配置
```

5. **启动系统**
```bash
python main.py
```

### 快速测试

访问 `http://localhost:5000` 查看系统状态

## 📁 项目结构

```
follow_trade_for_trade/
├── api/                    # API服务器模块
│   ├── __init__.py
│   ├── api_server.py      # 主API服务器
│   └── asset_analysis_api.py
├── config/                 # 配置管理
│   ├── __init__.py
│   ├── config.py          # 主配置
│   ├── mysql_config.py    # 数据库配置
│   ├── okx_config.py      # OKX配置
│   ├── binance_config.py  # Binance配置
│   └── limit_follow_config.py # 限价单配置
├── core/                   # 核心业务逻辑
│   ├── __init__.py
│   ├── module_manager.py  # 模块管理器
│   ├── market_trade/      # 市场交易
│   ├── limit_trade/       # 限价跟单
│   └── asset_analysis_service.py
├── database/               # 数据库相关
│   ├── __init__.py
│   ├── db.py              # 数据库连接池
│   └── *.sql              # 数据库表结构
├── exchange/               # 交易所集成
│   ├── __init__.py
│   ├── okx/               # OKX交易所
│   └── binance/           # Binance交易所
├── frontend/               # 前端界面
│   ├── index.html         # 主页面
│   ├── app.js             # 主逻辑
│   ├── styles.css         # 样式文件
│   └── limit_follow.html  # 限价单页面
├── model/                  # 数据模型
│   ├── __init__.py
│   ├── models.py          # 基础模型
│   ├── limit_follow_models.py
│   └── asset_analysis_models.py
├── utils/                  # 工具模块
│   ├── __init__.py
│   ├── logger.py          # 日志工具
│   └── dingtalk_bot.py    # 钉钉机器人
├── main.py                 # 主程序入口
├── start_system.py         # 系统启动脚本
└── requirements.txt        # 依赖包列表
```

## 🔧 配置说明

### 数据库配置

在 `config/config.py` 中配置MySQL连接：

```python
MYSQL_CONFIG = {
    'host': 'localhost',
    'port': 3306,
    'user': 'your_username',
    'password': 'your_password',
    'database': 'follow_trade',
    'charset': 'utf8mb4'
}
```

### 交易所配置

配置OKX和Binance的API密钥：

```python
# OKX配置
OKX_CONFIG = {
    'api_key': 'your_okx_api_key',
    'api_secret': 'your_okx_api_secret',
    'passphrase': 'your_okx_passphrase',
    'is_demo': True  # 是否使用演示账户
}

# Binance配置
BINANCE_CONFIG = {
    'api_key': 'your_binance_api_key',
    'api_secret': 'your_binance_api_secret',
    'is_demo': True
}
```

### 限价单配置

在 `config/limit_follow_config.py` 中配置跟单参数：

```python
DEFAULT_LIMIT_FOLLOW_CONFIG = {
    'max_orders_per_signal': 4,        # 每个信号最大跟单数
    'default_follow_percentages': [1.0, 2.0, 3.0, 4.0],  # 跟单百分比
    'max_net_leverage': 10.0,          # 最大净杠杆
    'risk_control_enabled': True       # 启用风险控制
}
```

## 📊 API接口

### 核心接口

| 接口 | 方法 | 描述 |
|------|------|------|
| `/api/v1/customers` | GET/POST | 客户管理 |
| `/api/v1/signal-sources` | GET/POST | 信号源管理 |
| `/api/v1/limit-follow/strategies` | GET/POST | 限价单策略 |
| `/api/v1/limit-follow/orders` | GET | 限价单订单 |
| `/api/v1/limit-follow/status` | GET | 系统状态 |

### 限价单专用接口

| 接口 | 方法 | 描述 |
|------|------|------|
| `/api/v1/limit-follow/risk/assessment` | POST | 风险评估 |
| `/api/v1/limit-follow/analytics/performance` | GET | 性能分析 |
| `/api/v1/limit-follow/batch/update-strategies` | POST | 批量更新策略 |

详细API文档请参考 [API_DOCS.md](docs/API_DOCS.md)

## 🎨 前端界面

系统提供了完整的前端界面，包括：

- **主控制台**: 系统概览和快速操作
- **客户管理**: 客户账户管理界面
- **信号源监控**: 实时信号监控面板
- **限价单管理**: 专业的限价单操作界面
- **风险控制**: 风险监控和预警面板
- **数据分析**: 交易数据分析和图表

**📖 [查看前端详细文档 →](docs/FRONTEND.md)**

## 🧪 测试说明

### 单元测试

```bash
# 运行所有测试
python -m pytest tests/

# 运行特定模块测试
python -m pytest tests/test_limit_follow.py
```

### 集成测试

```bash
# 启动测试环境
python test_integration.py

# 测试API接口
python test_api_endpoints.py
```

### 性能测试

```bash
# 压力测试
python performance_test.py

# 数据库性能测试
python test_database_performance.py
```

## 📈 部署指南

### 生产环境部署

1. **服务器准备**
```bash
# 安装系统依赖
sudo apt update
sudo apt install python3 python3-pip mysql-server nginx
```

2. **应用部署**
```bash
# 使用Gunicorn部署
pip install gunicorn
gunicorn -w 4 -b 0.0.0.0:5000 main:app
```

3. **Nginx配置**
```nginx
server {
    listen 80;
    server_name your-domain.com;
    
    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

4. **系统服务**
```bash
# 创建systemd服务
sudo nano /etc/systemd/system/follow-trade.service

# 启动服务
sudo systemctl enable follow-trade
sudo systemctl start follow-trade
```

### Docker部署

```bash
# 构建镜像
docker build -t follow-trade .

# 运行容器
docker run -d -p 5000:5000 --name follow-trade follow-trade
```

## 🤝 贡献指南

我们欢迎所有形式的贡献！

### 贡献方式

1. **报告Bug**: 在GitHub Issues中报告问题
2. **功能建议**: 提出新功能建议
3. **代码贡献**: 提交Pull Request
4. **文档改进**: 帮助完善文档

### 开发流程

1. Fork项目到你的GitHub账户
2. 创建功能分支: `git checkout -b feature/amazing-feature`
3. 提交更改: `git commit -m 'Add amazing feature'`
4. 推送到分支: `git push origin feature/amazing-feature`
5. 创建Pull Request

### 代码规范

- 遵循PEP 8 Python代码规范
- 添加适当的注释和文档字符串
- 编写单元测试覆盖新功能
- 确保所有测试通过

## 📄 许可证

本项目采用 [MIT许可证](LICENSE) - 查看LICENSE文件了解详情

## 📞 联系我们

- **项目主页**: [GitHub Repository](https://github.com/hall130/follow_trade_for_trade)
- **问题反馈**: [GitHub Issues](https://github.com/hall130/follow_trade_for_trade/issues)
- **讨论交流**: [GitHub Discussions](https://github.com/hall130/follow_trade_for_trade/discussions)

---

**⭐ 如果这个项目对你有帮助，请给我们一个Star！**

**📖 [继续阅读前端文档 →](docs/FRONTEND.md)** 
**🚀 [继续阅读API文档 →](docs/API_DOCS.md)** 