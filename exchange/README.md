# 交易所统一接口层

## 概述

本模块提供了一套统一的交易所接口层，解决了原有架构中直接调用具体交易所客户端导致的耦合问题。

## 问题背景

在原有架构中，core和api模块直接调用具体的交易所客户端（如`okx_rest_client`、`binance_rest_client`等），导致：

- **代码耦合度高**：业务逻辑与具体交易所实现绑定
- **扩展性差**：添加新交易所需要修改多处代码  
- **维护困难**：不同交易所的接口差异需要分别处理
- **测试复杂**：需要为每个交易所单独编写测试

## 解决方案

### 架构设计

```
exchange/
├── base_client.py              # 抽象基类定义
├── unified_rest_client.py     # 统一REST客户端
├── unified_ws_client.py       # 统一WebSocket客户端
├── exchange_factory.py         # 工厂类
├── usage_example.py           # 使用示例
├── MIGRATION_GUIDE.md         # 迁移指南
├── README.md                  # 本文档
└── [具体交易所实现]/
    ├── okx/
    │   ├── okx_rest_client.py
    │   └── okx_ws_client.py
    ├── binance/
    │   ├── binance_rest_client.py
    │   └── binance_ws_client.py
    └── bybit/ (未来支持)
```

### 核心组件

#### 1. 抽象基类 (`base_client.py`)

定义了统一的接口规范：

- `BaseRESTClient`: REST客户端抽象基类
- `BaseWebSocketClient`: WebSocket客户端抽象基类
- 数据类：`OrderRequest`, `OrderResponse`, `Position`, `Balance`, `Ticker`
- 枚举类：`ExchangeType`, `OrderSide`, `OrderType`, `OrderStatus`

#### 2. 统一客户端

- `UnifiedRESTClient`: 统一REST客户端，提供标准化的API接口
- `UnifiedWebSocketClient`: 统一WebSocket客户端，提供标准化的订阅接口

#### 3. 工厂类 (`exchange_factory.py`)

- `ExchangeFactory`: 管理客户端实例的创建和获取
- 支持客户端缓存和复用
- 提供便捷的创建函数

## 使用方法

### 基本使用

```python
from exchange.exchange_factory import create_exchange_client

# 创建REST客户端
rest_client = create_exchange_client(
    exchange='okx',
    client_type='rest',
    api_key='your_api_key',
    api_secret='your_api_secret',
    passphrase='your_passphrase',
    is_demo=True
)

# 创建WebSocket客户端
ws_client = create_exchange_client(
    exchange='okx',
    client_type='ws',
    api_key='your_api_key',
    api_secret='your_api_secret',
    passphrase='your_passphrase',
    is_demo=True
)
```

### REST API使用

```python
# 下单
order_result = await rest_client.place_order(
    symbol='BTC-USDT-SWAP',
    side='buy',
    order_type='market',
    quantity=0.01
)

# 获取持仓
positions = await rest_client.get_positions()

# 获取余额
balance = await rest_client.get_balance()

# 获取行情
ticker = await rest_client.get_ticker('BTC-USDT-SWAP')
```

### WebSocket使用

```python
# 连接
await ws_client.connect()

# 订阅行情
def on_ticker(data):
    print(f"行情更新: {data}")

await ws_client.subscribe_ticker('BTC-USDT-SWAP', on_ticker)

# 订阅订单更新
def on_order(data):
    print(f"订单更新: {data}")

await ws_client.subscribe_orders(on_order)
```

## 支持的交易所

| 交易所 | REST支持 | WebSocket支持 | 状态 |
|--------|----------|---------------|------|
| OKX    | ✅        | ✅            | 完成 |
| Binance| ✅        | ✅            | 完成 |
| Bybit  | 🔄        | 🔄            | 开发中 |

## 迁移指南

### 从直接调用迁移

**原来的方式：**
```python
from exchange.okx.okx_rest_client import OKXRESTClient

client = OKXRESTClient(api_key, api_secret, passphrase, is_demo)
result = await client.place_order(instId='BTC-USDT-SWAP', ...)
```

**新的方式：**
```python
from exchange.exchange_factory import create_exchange_client

client = create_exchange_client('okx', 'rest', api_key, api_secret, passphrase, is_demo)
result = await client.place_order(symbol='BTC-USDT-SWAP', side='buy', order_type='market', quantity=0.01)
```

### 核心优势

1. **统一接口**：所有交易所使用相同的API调用方式
2. **易于扩展**：添加新交易所只需实现抽象基类
3. **降低耦合**：业务逻辑与具体交易所实现解耦
4. **简化测试**：统一的测试接口
5. **支持多交易所**：可以同时使用多个交易所

## 配置示例

### 数据库配置

```sql
-- 添加交易所字段
ALTER TABLE customers ADD COLUMN exchange VARCHAR(20) DEFAULT 'okx';
ALTER TABLE signal_sources ADD COLUMN exchange VARCHAR(20) DEFAULT 'okx';
```

### 配置文件

```python
# config/exchange_config.py
EXCHANGE_CONFIGS = {
    'okx': {
        'rest_url': 'https://www.okx.com/api/v5',
        'ws_url': 'wss://ws.okx.com:8443/ws/v5/public',
        'requires_passphrase': True
    },
    'binance': {
        'rest_url': 'https://api.binance.com/api',
        'ws_url': 'wss://stream.binance.com:9443/ws',
        'requires_passphrase': False
    }
}
```

## 测试

### 运行示例

```bash
cd exchange
python usage_example.py
```

### 单元测试

```python
import pytest
from exchange.exchange_factory import create_exchange_client

@pytest.mark.asyncio
async def test_unified_client():
    client = create_exchange_client('okx', 'rest', 'test_key', 'test_secret', 'test_pass', True)
    result = await client.get_ticker('BTC-USDT-SWAP')
    assert result.get('success') is True
```

## 开发计划

- [x] 抽象基类定义
- [x] 统一REST客户端
- [x] 统一WebSocket客户端
- [x] 工厂类实现
- [x] 迁移指南
- [ ] 重构core模块
- [ ] 重构api模块
- [ ] 添加Bybit支持
- [ ] 完善测试覆盖
- [ ] 性能优化

## 贡献指南

1. 新交易所支持：实现`BaseRESTClient`和`BaseWebSocketClient`抽象基类
2. 功能扩展：在统一客户端中添加新的API方法
3. 测试：为新功能编写单元测试和集成测试
4. 文档：更新相关文档和示例

## 许可证

本项目采用MIT许可证。
