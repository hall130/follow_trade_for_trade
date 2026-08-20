# 🚀 量化交易系统

[![Python](https://img.shields.io/badge/Python-3.11+-blue.svg)](https://www.python.org/)
[![Flask](https://img.shields.io/badge/Flask-2.0+-green.svg)](https://flask.palletsprojects.com/)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-15+-336791.svg)](https://www.postgresql.org/)
[![TimescaleDB](https://img.shields.io/badge/TimescaleDB-2.x-FDB515.svg)](https://www.timescale.com/)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

> 🏆 **企业级量化交易系统** - 集成多交易所、智能跟单、策略交易、做市刷单的专业交易平台

## ⚠️ 重要风险提示

**🔴 本系统仅供学习和研究使用，请谨慎用于实盘交易**

- 加密货币交易具有极高风险，可能导致重大损失
- 建议优先使用交易所演示账户进行测试
- 使用前请充分了解相关风险并做好资金管理
- 建议在专业人士指导下使用

## 📋 目录

- [项目概述](#-项目概述)
- [核心功能](#-核心功能)
- [系统架构](#-系统架构)
- [快速开始](#-快速开始)
- [项目结构](#-项目结构)
- [配置说明](#-配置说明)
- [数据库](#-数据库postgresql--timescaledb)
- [API接口](#-api接口)
- [前端界面](#-前端界面)
- [部署指南](#-部署指南)
- [常见问题](#-常见问题)

## 🎯 项目概述

量化交易系统是一个**企业级的量化交易平台**，采用现代化微服务架构，专为专业交易机构和量化交易者设计。

### 🎪 核心能力

| 功能模块 | 技术特性 | 商业价值 |
|---------|---------|---------|
| **多交易所支持** | OKX、Binance REST/WebSocket API | 统一多平台交易，提高流动性 |
| **智能跟单系统** | 限价跟单、市价跟单、信号源跟单 | 自动化交易，降低人工成本 |
| **热门带单员** | OKX、Binance热门交易员发现 | 发现优质交易员，提升跟单收益 |
| **巨鲸交易员** | Hyperliquid/Echosync集成 | 追踪巨鲸交易，捕捉市场机会 |
| **策略交易引擎** | 5种核心策略，支持回测和实盘 | 从回测到实盘无缝切换 |
| **做市刷单** | 多种做市策略，自动化刷单 | 提供流动性，获取手续费返佣 |
| **风险控制系统** | 实时风险评估，自动干预 | 保护资金安全，控制回撤 |
| **消息转发系统** | Telegram/钉钉/微信多平台 | 实时消息同步，提升协作效率 |
| **会员系统** | 多等级会员、权限管理、自动续费 | 灵活的会员体系，权限自动同步 |
| **支付系统** | USDT/支付宝/Binance Pay | 多种支付方式，自动监听支付状态 |

### 🔥 技术亮点

- **⚡ 高性能**：支持1000+并发连接，API响应时间<100ms，Redis缓存优化
- **🔄 高可用**：自动重连机制，智能重试，99.5%+系统可用性
- **🧠 智能化**：动态参数配置，自适应策略优化，策略过滤器精确控制
- **🤖 全自动**：从信号生成到订单执行全流程自动化
- **🛡️ 安全性**：多层次安全机制，数据加密存储，权限管理系统
- **📈 可扩展**：微服务架构，支持水平扩展
- **💾 缓存优化**：Redis缓存热门带单员、巨鲸交易员数据，减少API请求
- **🎯 精确过滤**：TradingView策略过滤器双重检查机制，确保消息精确转发

## ✨ 核心功能

### 1. 🤖 智能跟单系统

#### 限价跟单
- **多交易所支持**：OKX、Binance、Hyperliquid
- **实时监控**：WebSocket实时监听交易员操作
- **智能下单**：自动计算跟单比例，限价单执行
- **风险控制**：仓位限制、杠杆控制、止损保护

#### 市价跟单
- **信号源管理**：支持TradingView、Telegram等多种信号源
- **策略过滤器**：支持为每个TradingView平台实例配置独立的策略过滤器（如ASR-VC、ASR-TP、ASR-HD）
- **快速执行**：市价单快速成交
- **批量处理**：支持多客户批量跟单

#### 热门带单员
- **OKX热门交易员**：收益率、收益额、跟单人数、胜率排序
- **Binance热门交易员**：PNL、ROI、跟单人数、夏普比率排序
- **公开/私域检测**：自动检测交易员是否为公开可跟单（基于API数据可访问性）
- **一键添加**：从热门带单员直接添加到限价跟单
- **Redis缓存**：智能缓存机制，每小时自动更新，减少API请求

### 2. 🐋 巨鲸交易员

#### Hyperliquid/Echosync集成
- **排行榜**：PNL排行、胜率排行、最新操作
- **巨鲸订单**：大额交易订单监控（默认>10万USDC）
- **巨鲸转移**：大额资金转移监控（默认>1万USDC）
- **用户详情**：查看巨鲸交易员的详细持仓和收益

#### 数据特性
- **实时更新**：巨鲸订单和转移每分钟自动刷新
- **排行榜缓存**：5分钟缓存，减少API请求
- **一键跟单**：从巨鲸交易员直接创建限价跟单策略

### 3. 🧠 策略交易引擎

#### 支持的策略
- **移动平均交叉** (MA Cross)
- **RSI超买超卖** (RSI Strategy)
- **布林带策略** (Bollinger Bands)
- **MACD策略** (MACD Strategy)
- **网格交易** (Grid Trading)
- **做市商交易** (Market maker)
- **马丁剥头皮网格策略**

#### 功能特性
- **完整回测**：历史数据回测，性能指标分析
- **实盘交易**：WebSocket实时数据，自动信号生成
- **参数优化**：动态参数配置，策略优化
- **风险控制**：实时风险评估，自动干预

### 4. 💰 做市刷单

#### 做市策略
- **标准做市策略**：价差、数量、最大订单数等参数可配置
- **Avellaneda-Stoikov策略**：基于库存风险的最优做市
- **Maker-Taker对冲策略**：做市商和接受者对冲

#### 功能特性
- **多账号管理**：支持多个做市账号，独立配置
- **实时统计**：总成交量、总利润、总手续费、净利润
- **进程管理**：独立进程运行，支持启停控制
- **用户隔离**：每个用户看到自己的做市账号

### 5. 🛡️ 风险控制系统

- **实时风险评估**：每笔交易前进行风险评估
- **动态仓位管理**：根据市场波动调整仓位大小
- **智能止损机制**：固定止损+跟踪止损组合
- **资金管理**：Kelly公式优化仓位分配

### 6. 📨 消息转发系统

- **多平台支持**：Telegram、钉钉、微信、微信公众号、TradingView
- **双向转发**：任意平台之间互相转发
- **智能过滤**：关键词筛选、排除规则、策略过滤器
- **内容转换**：前缀/后缀、Markdown格式
- **策略过滤器**：支持为每个 TradingView 平台实例配置独立的策略过滤器（如 ASR-VC、ASR-TP、ASR-HD）
- **订阅管理**：自动订阅管理、过期提醒、手动续订
- **双重检查机制**：消息转发前和转发规则匹配时双重策略过滤器检查，确保精确转发

### 7. 👥 会员系统

- **多等级会员**：免费会员、基础会员、高级会员、VIP会员
- **权限管理**：会员等级与权限系统完全融合，自动同步权限
- **自动续费**：支持手动续费和自动续费两种方式
- **支付集成**：支持 USDT TRC20、支付宝、Binance Pay 三种支付方式
- **权限优先级**：管理员 > 用户自定义权限 > 会员等级权限 > 角色默认权限

### 8. 💳 支付系统

- **支付方式**：USDT TRC20、支付宝、Binance Pay
- **支付监听**：自动监听支付状态，支付成功后自动激活会员
- **订单管理**：完整的支付订单管理，支持订单查询和状态跟踪
- **汇率转换**：支持 USD 到 CNY 的汇率转换（默认 7.2）
- **支付回调**：支持 Webhook 回调（支付宝、Binance Pay）

## 🏗️ 系统架构

```
┌─────────────────────────────────────────────────────────────┐
│                    🌐 前端展示层                              │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐    │
│  │ 交易控制台 │  │ 策略管理 │  │ 风险监控 │  │ 数据分析 │    │
│  └──────────┘  └──────────┘  └──────────┘  └──────────┘    │
└─────────────────────────────────────────────────────────────┘
                            │
┌─────────────────────────────────────────────────────────────┐
│                  🔌 API服务层 (Flask)                        │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐    │
│  │ 跟单API  │  │ 策略API  │  │ 风险API  │  │ 数据API  │    │
│  └──────────┘  └──────────┘  └──────────┘  └──────────┘    │
└─────────────────────────────────────────────────────────────┘
                            │
┌─────────────────────────────────────────────────────────────┐
│                  🏢 核心业务层                                │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐    │
│  │ 跟单引擎 │  │ 策略引擎 │  │ 风险引擎 │  │ 数据引擎 │    │
│  └──────────┘  └──────────┘  └──────────┘  └──────────┘    │
└─────────────────────────────────────────────────────────────┘
                            │
┌─────────────────────────────────────────────────────────────┐
│                  🗄️ 数据访问层                               │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐                  │
│  │PostgreSQL │  │ Redis缓存 │  │ 文件存储 │                  │
│  │+Timescale │  │           │  │          │                  │
│  └──────────┘  └──────────┘  └──────────┘                  │
└─────────────────────────────────────────────────────────────┘
                            │
┌─────────────────────────────────────────────────────────────┐
│                  🌍 外部服务层                               │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐    │
│  │ OKX交易所 │  │ Binance  │  │ Hyperliquid│ │ Echosync │    │
│  └──────────┘  └──────────┘  └──────────┘  └──────────┘    │
└─────────────────────────────────────────────────────────────┘
```

## 🚀 快速开始

### 🛠️ 环境要求

| 组件 | 版本要求 | 推荐配置 |
|------|---------|---------|
| **Python** | 3.10+ | 3.11+ |
| **PostgreSQL** | 15+ | 16+ |
| **TimescaleDB** | 2.x | 2.x（时序数据可选） |
| **Redis** | 6.0+ | 7.0+ (可选) |
| **内存** | 4GB+ | 16GB+ |
| **CPU** | 2核+ | 8核+ |
| **网络** | 稳定网络 | 低延迟(<100ms) |

### ⚡ 一键启动

```bash
# 1. 克隆项目
git clone https://github.com/your-repo/follow_trade_for_trade.git
cd follow_trade_for_trade

# 2. 安装依赖
pip install -r requirements.txt

# 3. 配置数据库（PostgreSQL）
#    创建数据库（默认库名 trade_db，与 config.py 一致）
psql -U postgres -c "CREATE DATABASE trade_db;"

# 导入完整表结构（69 张表，含触发器/索引）
psql -U postgres -d trade_db -f database/pg_schema.sql

# 4. 配置系统
# 编辑 config/config.py，配置数据库连接与 API 密钥
#（数据库配置项仍名为 MYSQL_CONFIG，仅为兼容旧调用，底层已是 PostgreSQL）

# 5. 启动系统
python main.py
```

### 🎯 快速验证

```bash
# 启动后访问
http://localhost:8080  # 前端界面
http://localhost:5001  # API服务

# 验证系统状态
curl http://localhost:5001/api/v1/health
```

## 📁 项目结构

```
follow_trade_for_trade/
├── 📁 api/                     # API服务层
│   ├── api_server.py          # 主API服务器
│   └── flask_error_handler.py # 错误处理
├── 📁 config/                  # 配置管理
│   ├── config.py              # 主配置文件
│   ├── binance_config.py      # Binance配置
│   └── okx_config.py          # OKX配置
├── 📁 core/                    # 核心业务层
│   ├── 📁 limit_trade/        # 限价跟单模块
│   │   ├── collectors/       # 交易员采集器
│   │   ├── limit_follow_service.py
│   │   └── popular_traders_service.py
│   ├── 📁 market_trade/       # 市场交易模块
│   ├── 📁 market_maker/       # 做市刷单模块
│   ├── 📁 strategy_trade/     # 策略交易模块
│   └── 📁 message_forward/    # 消息转发模块
├── 📁 database/                # 数据访问层
│   ├── db.py                  # 数据库连接池
│   └── *.sql                  # 数据库表结构
├── 📁 exchange/                # 交易所集成
│   ├── 📁 okx/               # OKX交易所
│   ├── 📁 binance/           # Binance交易所
│   └── 📁 hyperliquid/       # Hyperliquid交易所
├── 📁 frontend/                # 前端界面
│   ├── index.html            # 主页面
│   ├── app.js                # 主逻辑
│   └── styles.css            # 样式文件
├── 📁 auth/                    # 认证授权模块
│   ├── auth_service.py       # 认证服务
│   └── permission_service.py # 权限管理
├── main.py                    # 主程序入口
└── requirements.txt           # 依赖列表
```

## 🔧 配置说明

### 📊 数据库配置

> 数据库已迁移至 **PostgreSQL + TimescaleDB**，底层驱动为 `psycopg2`（见 [database/db.py](database/db.py)）。
> 配置变量名仍保留 `MYSQL_CONFIG` / `get_mysql_config()` 以兼容全部现有调用点，**不代表仍在使用 MySQL**。

```python
# config/config.py
MYSQL_CONFIG = {
    'host': 'localhost',   # PostgreSQL 主机
    'port': 5432,          # PostgreSQL 端口（注意不是 3306）
    'user': 'postgres',    # PostgreSQL 用户名
    'password': '******',  # PostgreSQL 密码
    'db': 'trade_db',      # 数据库名
}
```

### 🏪 交易所配置

```python
# OKX配置
OKX_CONFIG = {
    'api_key': 'your_okx_api_key',
    'api_secret': 'your_okx_api_secret',
    'passphrase': 'your_okx_passphrase',
    'is_demo': False
}

# Binance配置
BINANCE_CONFIG = {
    'api_key': 'your_binance_api_key',
    'api_secret': 'your_binance_api_secret'
}
```

### 🔐 Redis配置（可选）

```python
REDIS_CONFIG = {
    'host': 'localhost',
    'port': 6379,
    'db': 0,
    'password': None,  # 如果有密码
    'enabled': True    # 是否启用Redis
}
```

## 📊 API接口

### 🔌 核心API概览

| 接口分类 | 主要功能 | 端点示例 |
|---------|---------|---------|
| **热门带单员** | 获取OKX/Binance热门交易员 | `/api/v1/popular-traders` |
| **限价跟单** | 跟单员管理、跟单执行 | `/api/v1/limit-follow/traders` |
| **巨鲸交易员** | Echosync排行榜、订单、转移 | `/api/v1/echosync/leaderboard` |
| **做市刷单** | 做市账号管理、统计 | `/api/v1/market-maker/accounts` |
| **策略交易** | 策略管理、回测、实盘 | `/api/v1/strategy/strategies` |
| **账户管理** | 客户管理、持仓、交易记录 | `/api/v1/customers` |

### 📖 热门带单员API

```http
GET /api/v1/popular-traders?exchange=okx&sort_by=yield_ratio&limit=20

# 响应示例
{
  "success": true,
  "data": [
    {
      "unique_name": "E334AA83D20BC42C",
      "nick_name": "cococai",
      "yield_ratio": 546.29,
      "win_ratio": 54.55,
      "follower_num": 354,
      "follower_limit": 601,
      "source": "okx"
    }
  ],
  "total": 108
}
```

## 🎨 前端界面

### 🎯 核心页面

- **仪表板**：系统概览、实时统计
- **账户管理**：客户管理、持仓、交易记录
- **跟单交易**：信号源管理、限价跟单
- **信号交易**：信号源交易、信号源管理
- **热门带单员**：OKX/Binance热门交易员发现，公开/私域标识
- **巨鲸交易员**：排行榜、巨鲸订单、巨鲸转移
- **策略交易**：策略管理、策略交易、规则管理
- **刷单做市**：做市管理、做市统计
- **风险管理**：风险控制设置
- **会员服务**：会员等级查看、订阅、续费、自动续费设置
- **我的**：个人资料、会员信息、剩余天数、自动续费状态
- **系统设置**：消息转发、用户管理、权限管理、订阅管理

### 🛠️ 前端技术栈

- **UI框架**：Bootstrap 5 响应式设计（本地化部署，CDN备用）
- **图表库**：LightweightCharts 专业金融图表
- **实时通信**：WebSocket 双向通信
- **数据可视化**：ECharts 多维数据展示
- **图标库**：Bootstrap Icons（本地化部署）

## 🗄️ 数据库（PostgreSQL + TimescaleDB）

### 🔄 从 MySQL 迁移到 PostgreSQL

本项目数据库已由 **MySQL 迁移至 PostgreSQL 15+**（时序类数据可选启用 TimescaleDB）。迁移要点：

| 项目 | 迁移前 (MySQL) | 迁移后 (PostgreSQL) |
|------|---------------|---------------------|
| 驱动 | `pymysql` | `psycopg2` |
| 默认端口 | 3306 | **5432** |
| 连接池 | `MySQLPool` | 仍名为 `MySQLPool`，底层已换 psycopg2（见 [database/db.py](database/db.py)） |
| 自增主键 | `AUTO_INCREMENT` | `BIGSERIAL` |
| 布尔类型 | `TINYINT(1)` | 原生 `BOOLEAN` |
| JSON 字段 | `JSON` | `JSONB` |
| 时间戳自动更新 | `ON UPDATE CURRENT_TIMESTAMP` | 触发器 `set_updated_at()` |
| 时序数据 | 普通表 | TimescaleDB hypertable（可选） |

> **兼容性说明**：配置项、函数名、类名仍沿用 `MYSQL_CONFIG` / `get_mysql_config()` / `MySQLPool` 等旧名称，
> 这是为兼容全部现有调用点而保留的**别名**，**系统运行时使用的是 PostgreSQL**。
> 布尔值写入时注意：`db.py` 注册了全局 bool 适配器，向 `BOOLEAN` 列写入时需在 SQL 中显式 `%s::boolean` 转型。

迁移脚本见 [database/mysql_to_pg.py](database/mysql_to_pg.py)，它由 MySQL 建表脚本自动生成 PostgreSQL 版 [database/pg_schema.sql](database/pg_schema.sql)。

### 🚀 建库与建表

```bash
# 1. 创建数据库（库名 trade_db，需与 config.py 中 MYSQL_CONFIG['db'] 一致）
psql -U postgres -c "CREATE DATABASE trade_db;"

# 2. （可选）启用 TimescaleDB 扩展，用于 K 线/信号等时序数据
psql -U postgres -d trade_db -c "CREATE EXTENSION IF NOT EXISTS timescaledb;"

# 3. 导入完整表结构（69 张表 + 触发器 + 索引）
psql -U postgres -d trade_db -f database/pg_schema.sql
```

### 📋 数据表总览

系统共 **69 张表**，按业务域划分：

| 业务域 | 主要表 |
|--------|--------|
| **用户与权限** | `users`, `roles`, `modules`, `permissions`, `role_permissions`, `user_permissions`, `sessions`, `login_logs` |
| **会员与支付** | `membership_levels`, `user_memberships`, `membership_orders`, `membership_payment_orders`, `payment_listener_logs`, `exchange_api_redemption_codes` |
| **跟单核心** | `signal_sources`, `customers`, `strategies`, `rules`, `customer_strategy`, `customer_rule`, `customer_trades`, `trade_failures` |
| **限价跟单** | `limit_follow_traders`, `limit_follow_strategies`, `limit_follow_strategy_customers`, `limit_follow_orders`, `limit_follow_executions`, `limit_follow_configs`, `limit_follow_logs`, `trader_trades` |
| **做市刷单** | `market_maker_accounts`, `market_maker_status`, `market_maker_stats` |
| **策略引擎** | `strategy_configs`, `strategy_instances`, `strategy_signals`, `strategy_positions`, `strategy_trades`, `strategy_performance`, `strategy_risk_monitor`, `strategy_backtests`, `strategy_market_data`, `strategy_logs` |
| **风控与持仓** | `signal_stop_loss`, `customer_stop_loss`, `manual_operations`, `position_anomalies`, `customer_positions`, `customer_assets`, `customer_configs` |
| **消息转发** | `message_platforms`, `message_forward_rules`, `message_history`, `forward_trade_configs`, `forward_trade_records`, `telegram_*`, `wechat_official_*` |
| **邀请与订阅** | `invitation_codes`, `invitation_code_usage`, `forward_rule_subscriptions` |

### 📜 完整建表 SQL

完整 DDL 见 [database/pg_schema.sql](database/pg_schema.sql)（约 1500 行，69 张表 + 索引 + 触发器）。下方为其中几张核心表的**真实定义**（从 pg_schema.sql 摘录，未改动）：

```sql
-- =====================================================================
-- PostgreSQL + TimescaleDB 建表脚本（节选）
-- 执行完整脚本: psql -U postgres -d trade_db -f database/pg_schema.sql
-- =====================================================================

-- updated_at 自动刷新触发器函数
CREATE OR REPLACE FUNCTION set_updated_at() RETURNS trigger AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- 用户表
CREATE TABLE IF NOT EXISTS users (
    id BIGSERIAL,
    username            VARCHAR(100)    NOT NULL,
    password_hash       VARCHAR(255)    NOT NULL,
    full_name           VARCHAR(100)    DEFAULT NULL,
    email               VARCHAR(255)    DEFAULT NULL,
    role                VARCHAR(50)     NOT NULL DEFAULT 'user',
    status              VARCHAR(50)     NOT NULL DEFAULT 'active',
    customer_uid        VARCHAR(64)     DEFAULT NULL,
    is_password_changed SMALLINT        NOT NULL DEFAULT 0,
    password_changed_at TIMESTAMP       DEFAULT NULL,
    last_login_at       TIMESTAMP       DEFAULT NULL,
    last_login_ip       VARCHAR(45)     DEFAULT NULL,
    created_at          TIMESTAMP       NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at          TIMESTAMP       NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id)
);

-- 客户（跟单账户）表；主键为 customer_uid
CREATE TABLE IF NOT EXISTS customers (
    customer_uid        VARCHAR(64)   NOT NULL,
    name                VARCHAR(255)  NOT NULL,
    api_key             VARCHAR(255)  NULL,
    api_secret          VARCHAR(255)  NULL,
    passphrase          VARCHAR(255)  NULL,
    exchange            VARCHAR(32)   NOT NULL DEFAULT 'OKX',
    enabled             SMALLINT      NOT NULL DEFAULT 1,
    init_asset          DECIMAL(20,8) NOT NULL DEFAULT 0,
    trading_asset       DECIMAL(20,8) NULL,
    total_asset         DECIMAL(20,8) NOT NULL DEFAULT 0,
    leverage            INT           NULL DEFAULT 1,
    is_demo             SMALLINT      NULL,
    owner_user_id       BIGINT        NULL,
    stop_loss_percent   DECIMAL(20,8) NULL,
    stop_loss_enabled   SMALLINT      NULL DEFAULT 0,
    recently_assets     DECIMAL(20,8) NULL,
    last_stop_loss_time TIMESTAMP     NULL,
    stop_loss_count     INT           NULL DEFAULT 0,
    created_at          TIMESTAMP     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (customer_uid)
);

-- 策略实例表（config_json 以 JSONB 存储全部策略参数）
CREATE TABLE IF NOT EXISTS strategy_instances (
    id BIGSERIAL PRIMARY KEY,
    instance_name    VARCHAR(100) NOT NULL UNIQUE,
    strategy_name    VARCHAR(100) NOT NULL,
    account_id       VARCHAR(50)  NOT NULL,
    symbol           VARCHAR(20)  NOT NULL,
    timeframe        VARCHAR(10)  NOT NULL,
    status           VARCHAR(50)  DEFAULT 'STOPPED',
    config_json      JSONB        NOT NULL,
    performance_json JSONB,
    started_at       TIMESTAMP    NULL,
    stopped_at       TIMESTAMP    NULL,
    last_signal_at   TIMESTAMP    NULL,
    created_at       TIMESTAMP    DEFAULT CURRENT_TIMESTAMP,
    updated_at       TIMESTAMP    DEFAULT CURRENT_TIMESTAMP,
    created_by       VARCHAR(50),
    FOREIGN KEY (strategy_name) REFERENCES strategy_configs(strategy_name) ON DELETE CASCADE
);

-- 策略持仓表
CREATE TABLE IF NOT EXISTS strategy_positions (
    id BIGSERIAL PRIMARY KEY,
    instance_id    BIGINT       NOT NULL,
    position_id    VARCHAR(50)  NOT NULL,
    symbol         VARCHAR(20)  NOT NULL,
    side           VARCHAR(50)  NOT NULL,
    quantity       DECIMAL(20,8) NOT NULL,
    entry_price    DECIMAL(20,8) NOT NULL,
    current_price  DECIMAL(20,8),
    unrealized_pnl DECIMAL(20,8) DEFAULT 0,
    stop_loss      DECIMAL(20,8),
    take_profit    DECIMAL(20,8),
    entry_time     TIMESTAMP    NOT NULL,
    exit_time      TIMESTAMP    NULL,
    exit_price     DECIMAL(20,8),
    realized_pnl   DECIMAL(20,8) DEFAULT 0,
    status         VARCHAR(50)  DEFAULT 'OPEN',
    metadata_json  JSONB,
    created_at     TIMESTAMP    DEFAULT CURRENT_TIMESTAMP,
    updated_at     TIMESTAMP    DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (instance_id) REFERENCES strategy_instances(id) ON DELETE CASCADE
);

-- 限价跟单订单表
CREATE TABLE IF NOT EXISTS limit_follow_orders (
    id BIGSERIAL,
    order_uid          VARCHAR(64)   NOT NULL,
    strategy_id        BIGINT        NOT NULL DEFAULT 0,
    trader_unique_name VARCHAR(64)   NOT NULL DEFAULT '',
    customer_uid       VARCHAR(64)   NOT NULL DEFAULT '',
    symbol             VARCHAR(32)   NOT NULL DEFAULT '',
    pos_side           VARCHAR(8)    NOT NULL DEFAULT 'long',
    follow_value       DECIMAL(20,8) NOT NULL DEFAULT 0,
    target_price       DECIMAL(20,8) NOT NULL DEFAULT 0,
    order_size         DECIMAL(20,8) NOT NULL DEFAULT 0,
    order_type         VARCHAR(16)   NOT NULL DEFAULT 'limit',
    status             VARCHAR(16)   NOT NULL DEFAULT 'pending',
    signal_order_id    VARCHAR(64)   DEFAULT NULL,
    order_id           VARCHAR(64)   DEFAULT NULL,
    exchange_order_id  VARCHAR(64)   DEFAULT NULL,
    close_order_id     VARCHAR(64)   DEFAULT NULL,
    filled_price       DECIMAL(20,8) DEFAULT NULL,
    filled_size        DECIMAL(20,8) DEFAULT NULL,
    limit_close_size   DECIMAL(20,8) NOT NULL DEFAULT 0,
    reduce_only        SMALLINT      NOT NULL DEFAULT 0,
    created_at         TIMESTAMP     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at         TIMESTAMP     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id)
);

-- …… 其余 60+ 张表、索引与触发器详见 database/pg_schema.sql
```

> ⚠️ 以上为节选，字段以 [database/pg_schema.sql](database/pg_schema.sql) 实际内容为准。建库请直接执行该文件，不要手动复制节选片段。
>
> 关于 `is_demo`：建表脚本中定义为 `SMALLINT`，但部分运行环境的该列实际为 `BOOLEAN`。因 `db.py` 注册了全局 bool→整数适配器，向 `BOOLEAN` 列写入布尔值时需在 SQL 中显式 `%s::boolean` 转型，否则会报 “类型为 boolean, 但表达式为 integer”。以你目标库的真实列类型为准。

## 📈 部署指南

### 🐳 Docker部署（推荐）

```bash
# 构建镜像
docker build -t follow-trade .

# 运行容器
docker run -d -p 5001:5001 -p 8080:8080 follow-trade
```

### ☁️ 生产环境部署

```bash
# 1. 系统服务化
sudo chmod +x ./scripts/deploy_services.sh
- 按照指令配置服务

# 2. 启动服务
- 服务启动有两种方式
- 首先 sudo chmod +x ./scripts/switch_trade_mode.sh
./scripts/switch_trade_mode.sh demo/real # 执行模拟环境还是实盘环境
```

## ❓ 常见问题

### Q: 如何添加新的交易所支持？
A: 在 `exchange/` 目录下创建新的交易所客户端，实现 `BaseRESTClient` 和 `BaseWebSocketClient` 接口。

### Q: 如何添加新的做市策略？
A: 在 `core/market_maker/strategies/` 目录下创建新策略类，继承 `BaseMarketMaker`。

### Q: 系统支持哪些排序方式？
A: 
- OKX: 收益率(yieldRatio)、收益额(pnl)、跟单人数(traderFollowerLimit)、胜率(winRatio)
- Binance: 收益率(ROI)、总盈亏(PNL)、跟单人数(COPY_COUNT)、夏普比率(SHARP_RATIO)

### Q: 如何配置Redis缓存？
A: 在 `config/config.py` 中配置 `REDIS_CONFIG`，设置 `enabled: True`。

### Q: TradingView策略过滤器如何使用？
A: 
1. 在消息转发平台管理中，创建或编辑TradingView平台实例
2. 在"策略过滤器"字段中输入策略类型，多个策略用逗号分隔（如：`ASR-VC,ASR-TP`）
3. 系统会优先使用消息中的 `type_` 字段进行完整匹配
4. 只有匹配策略过滤器的消息才会被转发

### Q: 如何配置Bootstrap本地化部署？
A: 
1. 运行 `python scripts/download_bootstrap.py` 下载Bootstrap资源到本地
2. 确保 `frontend/lib/` 目录有正确的文件权限
3. 前端会自动优先使用本地文件，CDN作为备用

### Q: 热门带单员的公开/私域是如何检测的？
A: 
- **公开**：通过API可以获取到交易记录的带单员（OKX/Binance API返回数据）
- **私域**：API无法获取交易记录的带单员（只能通过信号源跟单）
- 系统每小时自动检测并更新状态

### Q: 消息转发系统的订阅管理如何工作？
A: 
1. 创建转发规则时，系统会自动为每个目标平台/群组创建订阅
2. 订阅默认有效期为30天（可在配置中修改）
3. 到期前3天开始每天发送提醒
4. 可以通过前端界面手动续订订阅

### Q: 会员系统如何与权限系统融合？
A: 
1. 用户注册时自动分配免费会员权限
2. 用户升级会员时，系统自动同步新会员等级的权限
3. 用户续费会员时，权限保持不变
4. 会员到期时，自动清理会员权限，保留用户自定义权限
5. 权限优先级：管理员 > 用户自定义权限 > 会员等级权限 > 角色默认权限

### Q: 支付系统支持哪些支付方式？
A: 
- **USDT TRC20**：通过 TronGrid API 轮询监控支付状态
- **支付宝**：支持轮询和 Webhook 回调两种方式
- **Binance Pay**：支持轮询和 Webhook 回调两种方式
- 支付成功后自动激活会员，无需手动操作

### Q: 如何配置支付系统？
A: 
1. 在 `config/config.py` 中配置 `PAYMENT_CONFIG`
2. USDT TRC20：配置收款地址和 TronGrid API URL
3. 支付宝：配置 App ID 和回调地址
4. Binance Pay：配置 API Key 和 Secret
5. 配置汇率（USD 到 CNY，默认 7.2）

### Q: 用户如何删除自己添加的客户 API？
A: 
1. 在账户管理页面找到要删除的客户
2. 点击删除按钮
3. 系统会验证权限，确保只能删除自己的客户
4. 删除成功后，客户信息会自动从内存中移除

## 📝 更新日志

查看详细的更新日志和版本历史：[CHANGELOG.md](CHANGELOG.md)

### 最新更新 [v1.2.0] - 2025-11-27
#### 🎯 主要更新
- ✨ **会员系统与权限融合**：权限模块与会员等级完全融合，会员变更时自动同步权限
- ✨ **支付系统**：支持 USDT TRC20、支付宝、Binance Pay 三种支付方式
- ✨ **会员续费**：支持手动续费和自动续费功能
- 🔧 **Telegram Bot API 配置**：配置 API 时自动设置 `is_demo` 字段，确保数据正确显示
- 🔧 **客户管理**：用户可删除自己添加的客户 API 配置
- 🐛 **权限同步**：修复会员续费、升级、降级时权限未同步的问题
- 🐛 **数据过滤**：修复客户数据查询时的权限过滤逻辑

### 上一次版本 [v1.1.5] - 2025-11-19
#### 🎯 主要更新
- ✨ **消息转发**：支持消息转发直接跟单交易
- ✨ **会员服务**：优化会员服务UI, 修复跳转bug
- 🔧 **telegrambot与订阅码**：支持telegrambot实现订阅功能,并且在web端生成对应的订阅码
- 🔧 **hyperliquid接口优化**：现在可以直接执行跟单交易
- 🐛 **热门带单员新增更多带单员**
- 🐛 **限价跟单服务支持多交易所响应**


### 上一次版本 [v1.1.0] - 2025-11-09

#### 🎯 主要更新
- ✨ **TradingView策略过滤器**：支持为每个平台实例配置独立的策略过滤器
- ✨ **双重检查机制**：消息转发前和转发规则匹配时双重策略过滤器检查
- 🔧 **Bootstrap本地化**：支持本地部署Bootstrap资源，提升加载速度
- 🔧 **公开/私域检测**：自动检测热门带单员的公开/私域状态
- 🐛 **修复策略过滤器不生效问题**
- 🐛 **修复Bootstrap Icons字体文件404错误**

## 📞 联系我们

- **项目主页**：[GitHub Repository](https://github.com/your-repo/follow_trade_for_trade)
- **问题反馈**：[GitHub Issues](https://github.com/your-repo/follow_trade_for_trade/issues)
- **更新日志**：[CHANGELOG.md](CHANGELOG.md)
- **Telegram Bot计划**：[docs/TELEGRAM_BOT_PLAN.md](docs/TELEGRAM_BOT_PLAN.md)

---

<div align="center">

**⭐ 如果这个项目对你有帮助，请给我们一个Star！**

Built with ❤️ by the Follow Trade Team

</div>
