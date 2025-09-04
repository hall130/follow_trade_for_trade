# 策略交易模块文件重构指南

## 重构概述

为了更好地组织项目结构，我们对策略交易模块的文件进行了重新组织，将相关文件移动到更合适的目录中。

## 重构变更

### 1. SQL文件迁移

**原位置**: `core/strategy_trade/strategy_tables.sql` 和 `core/strategy_trade/indicators.sql`  
**新位置**: `database/strategy_tables.sql`

- 将所有数据库表结构定义合并到 `database/strategy_tables.sql`
- 删除了重复的 `indicators.sql` 文件
- 所有策略相关的数据库表、视图、索引和初始数据都在一个文件中

### 2. 配置文件重构

**原位置**: `core/strategy_trade/config_manager.py`  
**新位置**: `config/strategy_config.py`

- 创建了统一的策略配置管理器 `StrategyConfigManager`
- 包含所有策略模板的定义和验证规则
- 支持配置文件的保存、加载和验证
- 提供JSON Schema生成功能

### 3. 数据库工具

**新增**: `database/init_database.py`

- 数据库初始化和管理工具
- 支持创建、检查、清理和重置数据库
- 交互式命令行界面

## 新的文件结构

```
follow_trade_for_trade/
├── config/
│   ├── strategy_config.py          # 统一的策略配置管理
│   └── strategy_configs/           # 策略配置文件存储目录
│       ├── strategy1.json
│       └── strategy2.json
├── database/
│   ├── strategy_tables.sql         # 所有策略相关数据库表
│   └── init_database.py           # 数据库初始化工具
└── core/
    └── strategy_trade/
        ├── base_strategy.py
        ├── strategy_engine.py
        ├── strategy_manager.py
        ├── strategy_db.py
        ├── backtest_engine.py
        ├── monitoring.py
        ├── api.py
        ├── utils/
        │   └── indicators.py
        └── strategies/
            ├── ma_cross_strategy.py
            ├── rsi_strategy.py
            ├── grid_strategy.py
            ├── bollinger_strategy.py
            └── macd_strategy.py
```

## 导入路径更新

### 配置管理相关

**之前**:
```python
from core.strategy_trade.config_manager import ConfigManager
```

**现在**:
```python
from config.strategy_config import (
    strategy_config_manager, 
    get_strategy_template, 
    validate_strategy_config,
    create_strategy_config
)
```

### 数据库相关

**之前**:
```python
# SQL文件在 core/strategy_trade/ 目录下
```

**现在**:
```python
# SQL文件在 database/ 目录下
# 使用 database/init_database.py 进行数据库初始化
```

## 配置管理增强

### 策略模板

新的配置管理器提供了更强大的模板功能：

1. **策略模板定义**: 包含完整的策略配置模板，包括默认值、验证规则、风险档次等
2. **配置验证**: 自动验证配置参数的类型、范围和逻辑关系
3. **配置持久化**: 支持将配置保存到JSON文件
4. **模板分类**: 按类别、风险档次、复杂度分类管理模板

### 策略模板示例

```python
# 获取移动平均策略模板
template = get_strategy_template("MA_Cross_Strategy")

# 验证配置
is_valid, errors = validate_strategy_config("MA_Cross_Strategy", my_config)

# 创建配置
config = create_strategy_config("MA_Cross_Strategy", custom_params)
```

## 数据库管理

### 初始化数据库

```bash
# 运行数据库初始化工具
python database/init_database.py
```

该工具提供以下功能：
1. 初始化数据库（创建所有表和视图）
2. 检查数据库状态
3. 清理数据库
4. 重置数据库

### 新的数据库表

所有策略相关的表都在 `database/strategy_tables.sql` 中定义：

- `strategy_configs`: 策略配置模板
- `strategy_instances`: 策略实例
- `strategy_signals`: 交易信号
- `strategy_positions`: 持仓记录
- `strategy_trades`: 交易记录
- `strategy_performance`: 性能统计
- `strategy_risk_monitor`: 风险监控
- `strategy_backtests`: 回测记录
- `strategy_market_data`: 市场数据
- `strategy_logs`: 日志记录

## 兼容性说明

### 现有代码迁移

1. **更新导入语句**: 按照上述路径更新所有相关的import语句
2. **配置管理**: 使用新的配置管理器替换旧的ConfigManager
3. **数据库初始化**: 使用新的初始化工具创建数据库表

### 配置文件迁移

旧的配置文件可以通过以下方式迁移：

```python
from config.strategy_config import strategy_config_manager

# 保存旧配置到新格式
strategy_config_manager.save_config("strategy_name", old_config)

# 加载配置
new_config = strategy_config_manager.load_config("strategy_name")
```

## 优势

1. **更清晰的结构**: 配置文件在config目录，数据库文件在database目录
2. **统一管理**: 所有策略配置通过一个管理器处理
3. **更强验证**: 完整的配置验证和类型检查
4. **易于维护**: 模块化的设计便于扩展和维护
5. **工具支持**: 专门的数据库管理工具

## 注意事项

1. 确保更新所有相关的导入路径
2. 运行数据库初始化工具创建新的表结构
3. 迁移现有的配置文件到新格式
4. 测试所有功能确保兼容性

## 下一步

1. 运行 `python database/init_database.py` 初始化数据库
2. 更新现有代码中的导入路径
3. 测试所有功能
4. 迁移现有配置数据 