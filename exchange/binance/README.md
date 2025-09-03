# 币安交易所集成

## 概述

本模块提供了币安交易所的完整集成，包括REST API客户端和WebSocket客户端，支持现货交易和测试网环境。

## 功能特性

### REST API客户端 (BinanceRESTClient)
- ✅ 账户管理（获取账户信息、余额）
- ✅ 交易操作（下单、取消订单、查询订单状态）
- ✅ 市场数据（价格、K线、交易所信息）
- ✅ 完整的鉴权类型支持（NONE, TRADE, USER_DATA, USER_STREAM）
- ✅ 自动签名和认证
- ✅ 支持测试网和主网
- ✅ 时间同步安全（timestamp + recvWindow）
- ✅ 用户数据流管理（listenKey）

### WebSocket客户端 (BinanceWebSocketClient)
- ✅ 实时价格行情订阅
- ✅ K线数据订阅
- ✅ 交易数据订阅
- ✅ 深度数据订阅
- ✅ 用户数据订阅（需要API密钥）
- ✅ 组合流订阅
- ✅ 自动重连和错误处理
- ✅ 会话身份验证（session.logon/logout/status）
- ✅ 临时请求授权（支持不同API密钥）
- ✅ 自动listenKey管理

## 快速开始

### 1. 配置API密钥

编辑 `config/binance_config.py` 文件：

```python
BINANCE_CONFIG = {
    'api_key': 'your_actual_api_key_here',
    'api_secret': 'your_actual_api_secret_here',
    'is_demo': True,  # 设置为False使用主网
    # ... 其他配置
}
```

**重要提示**: 根据币安API要求，不同的操作需要不同的API密钥权限：
- **NONE**: 公开市场数据（无需API密钥）
- **TRADE**: 交易操作（下单、取消订单）
- **USER_DATA**: 私人账户信息（订单状态、交易历史）
- **USER_STREAM**: 管理用户数据流订阅

请确保在币安账户的API管理页面中启用了相应的权限。

### 2. 使用REST客户端

```python
from exchange import create_exchange_client

# 创建REST客户端
client = create_exchange_client(
    exchange='binance',
    client_type='rest',
    api_key='your_api_key',
    api_secret='your_api_secret',
    is_demo=True
)

# 获取账户信息
account_info = await client.get_account_info()

# 下单
order = await client.place_order(
    symbol='BTCUSDT',
    side='BUY',
    order_type='LIMIT',
    quantity=0.001,
    price=50000.0
)
```

### 3. 使用WebSocket客户端

```python
from exchange import create_exchange_client

# 创建WebSocket客户端
client = create_exchange_client(
    exchange='binance',
    client_type='ws',
    api_key='your_api_key',  # 可选
    api_secret='your_api_secret',  # 可选
    is_demo=True
)

# 订阅价格行情
async def price_callback(data):
    print(f"BTC价格: {data}")

await client.subscribe_ticker('BTCUSDT', price_callback)

# 订阅K线数据
async def kline_callback(data):
    print(f"K线数据: {data}")

await client.subscribe_kline('BTCUSDT', '1m', kline_callback)
```

### 4. 使用交易所工厂

```python
from exchange import get_exchange_factory

factory = get_exchange_factory()

# 从配置创建客户端
client = factory.create_client_from_config('binance', is_demo=True)

# 获取支持的交易所
supported = factory.get_supported_exchanges()
print(f"支持的交易所: {supported}")  # ['okx', 'binance']
```

## API参考

### BinanceRESTClient

#### 账户相关
- `get_account_info()` - 获取账户信息 (USER_DATA)
- `get_balance()` - 获取账户余额 (USER_DATA)

#### 交易相关
- `place_order(symbol, side, order_type, quantity, price, time_in_force, recv_window)` - 下单 (TRADE)
- `cancel_order(symbol, order_id, recv_window)` - 取消订单 (TRADE)
- `get_order_status(symbol, order_id, recv_window)` - 获取订单状态 (USER_DATA)
- `get_open_orders(symbol, recv_window)` - 获取未成交订单 (USER_DATA)

#### 市场数据
- `get_ticker_price(symbol)` - 获取价格信息 (NONE)
- `get_klines(symbol, interval, start_time, end_time, limit)` - 获取K线数据 (NONE)
- `get_exchange_info()` - 获取交易所信息 (NONE)

#### 用户数据流管理
- `create_listen_key()` - 创建listenKey (USER_STREAM)
- `extend_listen_key(listen_key)` - 延长listenKey有效期 (USER_STREAM)
- `close_listen_key(listen_key)` - 关闭listenKey (USER_STREAM)

#### 交易历史
- `get_trade_history(symbol, limit, from_id, recv_window)` - 获取交易历史 (USER_DATA)
- `get_account_trades(symbol, order_id, recv_window)` - 获取账户交易统计 (USER_DATA)

### BinanceWebSocketClient

#### 订阅方法
- `subscribe_ticker(symbol, callback)` - 订阅价格行情 (NONE)
- `subscribe_kline(symbol, interval, callback)` - 订阅K线数据 (NONE)
- `subscribe_trade(symbol, callback)` - 订阅交易数据 (NONE)
- `subscribe_depth(symbol, callback)` - 订阅深度数据 (NONE)
- `subscribe_user_data(listen_key, callback)` - 订阅用户数据流 (USER_STREAM)
- `subscribe_user_data_with_rest_client(rest_client, callback)` - 自动管理listenKey并订阅用户数据
- `subscribe_multiple_streams(streams, callback)` - 订阅多个流 (NONE)

#### 会话身份验证
- `session_logon(connection_id, api_key, api_secret)` - 进行会话身份验证 (USER_STREAM)
- `session_status(connection_id)` - 检查会话状态 (USER_STREAM)
- `session_logout(connection_id)` - 登出会话 (USER_STREAM)
- `is_session_authenticated(connection_id)` - 检查会话是否已认证
- `get_session_api_key(connection_id)` - 获取会话的API密钥
- `send_signed_request(connection_id, method, params, api_key, api_secret, recv_window)` - 发送签名请求（支持临时授权）

#### 管理方法
- `unsubscribe(stream_name)` - 取消订阅
- `ping(stream_name)` - 发送ping消息
- `close_all()` - 关闭所有连接
- `get_status()` - 获取连接状态

## 鉴权类型说明

币安API根据不同的操作类型需要不同的鉴权权限：

| 鉴权类型 | 描述 | 需要API密钥 | 示例操作 |
|---------|------|-------------|----------|
| **NONE** | 公开市场数据 | ❌ 否 | 获取价格、K线、交易所信息 |
| **TRADE** | 交易操作 | ✅ 是 | 下单、取消订单 |
| **USER_DATA** | 私人账户信息 | ✅ 是 | 订单状态、交易历史、账户余额 |
| **USER_STREAM** | 用户数据流管理 | ✅ 是 | 创建/管理listenKey |

### 时间同步安全
- 所有需要签名的请求都包含 `timestamp` 参数（毫秒时间戳）
- `recvWindow` 参数指定请求有效期（默认5000ms，最大60000ms）
- 服务器会验证请求时间，确保请求在有效期内

## 配置选项

### 环境配置
- `is_demo`: 是否使用测试网（默认True）
- `timeout`: 请求超时时间（默认30秒）
- `max_retries`: 最大重试次数（默认3次）

### 速率限制
- `requests_per_minute`: 每分钟请求限制（默认1200）
- `orders_per_second`: 每秒订单限制（默认10）
- `orders_per_day`: 每日订单限制（默认200000）

## 测试

运行测试脚本验证集成：

```bash
    python test_binance_integration.py
    ```

## 高级功能：会话身份验证

### 1. 会话身份验证

币安WebSocket支持会话身份验证，一次认证后整个会话有效：

```python
from exchange import create_exchange_client

# 创建WebSocket客户端
ws_client = create_exchange_client(
    exchange='binance',
    client_type='ws',
    is_demo=True
)

# 进行会话身份验证
success = await ws_client.session_logon('connection_1', 'your_api_key', 'your_api_secret')
if success:
    print("会话认证成功")
    
    # 检查会话状态
    status = await ws_client.session_status('connection_1')
    print(f"会话状态: {status}")
    
    # 发送需要签名的请求（使用会话密钥）
    response = await ws_client.send_signed_request(
        'connection_1',
        'order.place',
        {'symbol': 'BTCUSDT', 'side': 'BUY', 'quantity': 0.001}
    )
    
    # 登出会话
    await ws_client.session_logout('connection_1')
```

### 2. 临时请求授权

支持为单个请求使用不同的API密钥：

```python
# 使用临时密钥发送请求
response = await ws_client.send_signed_request(
    'connection_1',
    'order.place',
    {'symbol': 'BTCUSDT', 'side': 'BUY', 'quantity': 0.001},
    api_key='trade_api_key',      # 临时TRADE密钥
    api_secret='trade_api_secret', # 临时TRADE密钥
    recv_window=10000             # 10秒有效期
)
```

### 3. 会话管理

```python
# 获取所有已认证的会话
sessions = ws_client.get_authenticated_sessions()
print(f"已认证会话: {sessions}")

# 检查特定连接是否已认证
if ws_client.is_session_authenticated('connection_1'):
    print("连接已认证")
    
# 清除所有会话认证
ws_client.clear_authenticated_sessions()
```

## 注意事项

1. **API密钥安全**: 请妥善保管API密钥，不要提交到版本控制系统
2. **测试网**: 建议先在测试网环境测试，确认无误后再使用主网
3. **速率限制**: 注意遵守币安的API速率限制
4. **网络连接**: 确保网络连接稳定，特别是WebSocket连接

## 错误处理

客户端包含完善的错误处理机制：
- 自动重试机制
- 详细的错误日志
- 连接状态监控
- 异常恢复能力

## 扩展性

该模块设计为可扩展架构，可以轻松添加：
- 新的交易所支持
- 新的API接口
- 自定义错误处理
- 监控和统计功能

## 支持

如有问题，请检查：
1. API密钥配置是否正确
2. 网络连接是否正常
3. 日志输出中的错误信息
4. 币安API文档和状态页面 