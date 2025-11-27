# 更新日志

## [🚀已发布] - 2025-11-27

### 🎯 新增功能

#### 1. 会员系统与权限完全融合
- **功能描述**：权限模块与会员等级系统完全融合，会员变更时自动同步用户权限
- **实现位置**：
  - `core/membership/membership_service.py`：会员激活、续费、升级时自动同步权限
  - `auth/permission_service.py`：权限检查逻辑融合会员等级权限
  - `database/membership_system_schema.sql`：数据库触发器自动同步权限
- **使用场景**：
  - 用户注册时自动分配免费会员权限
  - 用户升级会员时自动更新权限
  - 用户续费会员时保持权限一致
  - 会员到期时自动清理权限
- **权限优先级**：
  1. 管理员角色（拥有所有权限）
  2. 用户自定义权限（手动授予）
  3. 会员等级权限（自动同步）
  4. 角色默认权限（基础权限）

#### 2. 支付系统集成
- **功能描述**：支持 USDT TRC20、支付宝、Binance Pay 三种支付方式
- **实现位置**：
  - `core/payment/`：支付订单管理和监听服务
  - `core/payment/listeners/`：USDT、支付宝、Binance Pay 支付监听器
  - `api/api_server.py`：支付相关 API 接口
- **支付流程**：
  1. 用户选择会员等级和计费周期
  2. 创建支付订单
  3. 选择支付方式（USDT/支付宝/Binance Pay）
  4. 支付监听器监控支付状态
  5. 支付成功后自动激活会员
- **支付监听**：
  - USDT TRC20：通过 TronGrid API 轮询监控
  - 支付宝：支持轮询和 Webhook 回调
  - Binance Pay：支持轮询和 Webhook 回调

#### 3. 会员续费功能
- **功能描述**：支持手动续费和自动续费两种方式
- **实现位置**：
  - `core/membership/membership_service.py`：续费和自动续费逻辑
  - `api/api_server.py`：续费 API 接口
  - `frontend/app.js`：续费 UI 界面
- **功能特性**：
  - 手动续费：用户可选择月付或年付续费
  - 自动续费：开启后到期自动续费
  - 续费后自动同步权限

### 🔧 功能优化

#### 1. Telegram Bot API 配置优化
- **改进前**：配置 API 时未设置 `is_demo` 字段，导致客户数据无法正确显示
- **改进后**：
  - 自动从环境变量 `IS_DEMO` 获取模拟盘设置
  - 创建和更新客户记录时自动设置 `is_demo` 字段
  - 确保客户数据与系统设置一致
- **实现位置**：`core/message_forward/telegram_bot/exchange_api_service.py`

#### 2. 客户管理功能增强
- **新增功能**：用户可删除自己添加的客户 API 配置
- **权限控制**：
  - 使用 `@filter_customers` 装饰器确保只能删除自己的客户
  - 删除前验证客户是否存在和权限
  - 删除后自动重新加载客户信息
- **实现位置**：`api/api_server.py` 的 `delete_customer` 函数

#### 3. 权限检查逻辑优化
- **改进**：优化客户数据查询时的权限过滤逻辑
- **修复**：使用正则表达式正确解析 `g.customer_filter`，支持 `" AND owner_user_id = 6"` 格式
- **实现位置**：`api/api_server.py` 的 `get_customers` 和 `get_customer` 函数

### 🐛 问题修复

#### 1. 会员续费后权限未同步
- **问题**：用户续费会员后，权限未自动同步更新
- **修复**：在 `renew_membership` 方法中添加权限同步逻辑
- **实现位置**：`core/membership/membership_service.py`

#### 2. 会员到期时权限未清理
- **问题**：会员到期后，自动授予的权限未清理
- **修复**：新增 `cleanup_expired_membership_permissions` 方法，清理过期会员权限
- **实现位置**：`core/membership/membership_service.py`

#### 3. 客户数据查询权限过滤失败
- **问题**：`g.customer_filter` 格式为 `" AND owner_user_id = 6"`，但解析逻辑不正确
- **修复**：使用正则表达式 `r'owner_user_id\s*=\s*(\d+)'` 正确提取用户ID
- **实现位置**：`api/api_server.py`

#### 4. Telegram Bot 配置 API 缺少 is_demo 字段
- **问题**：通过 Telegram Bot 配置 API 时，未设置 `is_demo` 字段，导致客户数据无法显示
- **修复**：在 `save_exchange_api_config` 方法中自动获取并设置 `is_demo` 字段
- **实现位置**：`core/message_forward/telegram_bot/exchange_api_service.py`

#### 5. 客户删除功能缺失
- **问题**：用户无法删除自己添加的客户 API 配置，返回 405 Method Not Allowed
- **修复**：添加 `DELETE /api/v1/customers/<customer_uid>` 路由，支持删除客户
- **实现位置**：`api/api_server.py`

#### 6. 异步函数调用错误
- **问题**：在同步代码中使用 `asyncio.create_task()` 导致 `no running event loop` 错误
- **修复**：使用 `run_async_safe()` 函数安全调用异步函数
- **实现位置**：`api/api_server.py` 的转发交易配置缓存刷新逻辑

### 📝 代码改进

#### 1. 权限同步机制
- **数据库触发器**：会员变更时自动调用 `sync_user_membership_permissions` 存储过程
- **手动同步**：在 `activate_membership` 和 `renew_membership` 中显式调用权限同步
- **权限清理**：会员到期时自动清理 `granted_by IS NULL` 的权限

#### 2. 支付系统架构
- **订单管理**：`core/payment/order_service.py` 管理支付订单
- **监听服务**：`core/payment/payment_listener_service.py` 统一管理所有支付监听器
- **监听器实现**：
  - `usdt_listener.py`：USDT TRC20 监听器
  - `alipay_listener.py`：支付宝监听器
  - `binance_listener.py`：Binance Pay 监听器

### 📚 文档更新

#### 新增文档
- `docs/PAYMENT_SYSTEM_DESIGN.md`：支付系统设计文档
- `database/membership_payment_schema.sql`：支付订单和监听日志表结构

#### 更新文档
- `README.md`：添加最新版本更新说明
- `CHANGELOG.md`：添加 v1.2.0 版本更新日志

### ⚠️ 注意事项

1. **权限同步**：
   - 会员变更时权限会自动同步，无需手动操作
   - 如果存储过程失败，系统会回退到手动同步
   - 建议定期检查权限同步日志，确保没有异常

2. **支付配置**：
   - USDT TRC20 需要配置收款地址和 TronGrid API
   - 支付宝需要配置 App ID 和回调地址
   - Binance Pay 需要配置 API Key 和 Secret
   - 汇率配置：默认 USD 到 CNY 汇率为 7.2

3. **客户数据过滤**：
   - 普通用户只能看到和操作自己的客户数据
   - 管理员可以看到所有客户数据
   - 删除客户前会验证权限，确保安全

4. **Telegram Bot API 配置**：
   - 配置 API 时会自动设置 `is_demo` 字段
   - 确保环境变量 `IS_DEMO` 正确设置
   - 客户数据会根据 `is_demo` 字段过滤显示

### 🚀 下一步计划

- [ ] 实现支付监听器的 Webhook 回调支持
- [ ] 添加支付订单的统计和报表功能
- [ ] 优化权限同步性能，支持批量同步
- [ ] 添加会员等级变更的审计日志

---

## [🚀已发布] - 2025-11-25

### 🎯 新增功能

#### 1. 限价跟单多交易所支持
- **功能描述**：限价跟单系统现在支持 OKX、Binance 和 Hyperliquid 三个交易所
- **实现位置**：
  - `core/limit_trade/limit_follow_executor.py`：统一执行器，自动识别交易所类型
  - `core/limit_trade/limit_follow_service.py`：支持多交易所的订单状态同步
  - `core/limit_trade/collectors/`：各交易所数据采集器
- **使用场景**：
  - 可以同时监控不同交易所的带单员
  - 自动根据带单员配置选择对应的采集器和交易所客户端
  - 统一的订单处理逻辑，支持多交易所
- **配置方式**：在数据库 `customers` 和 `signal_sources` 表中配置 `exchange` 字段（'okx', 'binance', 'hyperliquid'）

#### 2. 智能交易回溯机制
- **功能描述**：当系统重启或检测到订单ID跳跃时，自动回溯查找中间被跳过的交易
- **实现位置**：`core/limit_trade/limit_follow_executor.py` 的 `check_trader_async` 方法
- **工作原理**：
  1. 检测到订单ID变化时，获取更多记录（默认100条）进行回溯查找
  2. 从最新记录开始，倒序查找上次处理的订单ID
  3. 找到连续点后，提取所有中间被跳过的交易
  4. 按时间正序处理所有新交易，确保不遗漏
- **优势**：避免因系统停止运行或网络延迟导致的漏单问题

#### 3. 动态时间范围查询
- **功能描述**：根据最后处理的交易时间动态计算查询时间范围，减少API调用
- **实现位置**：各交易所数据采集器的 `get_trade_records_async` 方法
- **工作原理**：
  - 如果存在上次处理的交易时间，从该时间往前推1小时查询
  - 如果没有，使用默认的7天时间范围
  - 确保时间范围不超过默认天数，避免查询过多历史数据
- **优势**：提高查询效率，减少不必要的API调用

### 🔧 功能优化

#### 1. 多维度新订单判断
- **改进前**：仅依赖订单ID判断是否为新订单
- **改进后**：
  - 订单ID不同 → 新订单
  - 订单ID相同但时间更新（时间差>1秒）→ 新订单
  - 同时记录订单ID和时间戳，提高判断准确性
- **实现位置**：`core/limit_trade/limit_follow_executor.py`

#### 2. 数据采集器字段映射优化
- **Binance**：
  - 支持没有 `orderId` 的情况，自动生成唯一标识符
  - 优先使用 `orderTime` 和 `orderUpdateTime` 作为时间戳
  - 优先使用 `executedQty` 和 `avgPrice` 字段
  - 添加数据排序逻辑，确保按时间倒序
- **Hyperliquid**：
  - 修复时间字段处理（支持毫秒时间戳，不是ISO字符串）
  - 修复持仓方向判断（使用 `dir` 和 `startPosition` 字段，而不是 `side_info`）
  - 优化排序逻辑，确保类型安全
- **OKX**：保持接口一致性，支持动态时间范围参数

#### 3. 并发监控优化
- **改进**：所有带单员并发检查，不串行执行
- **监控频率**：
  - 带单员交易监控：每5秒检查一次
  - 订单状态监控：每30秒检查一次
  - 状态同步：每60秒执行一次
- **实现位置**：`core/limit_trade/limit_follow_executor.py` 和 `core/limit_trade/limit_follow_service.py`

### 🐛 问题修复

#### 1. Binance 订单ID缺失问题
- **问题**：Binance API 返回的历史交易数据没有 `orderId` 字段
- **修复**：自动生成唯一标识符，格式：`BINANCE_{时间戳}_{交易对}_{方向}_{持仓方向}_{数量}_{价格}`
- **实现位置**：`core/limit_trade/collectors/binance_collector.py`

#### 2. Hyperliquid 时间字段解析错误
- **问题**：代码假设 `time` 字段是 ISO 字符串格式，但实际返回的是毫秒时间戳（整数）
- **修复**：添加类型检查，支持毫秒时间戳、ISO 字符串等多种格式
- **实现位置**：`core/limit_trade/collectors/hyperliquid_trader_collector.py`

#### 3. Hyperliquid 持仓方向判断错误
- **问题**：代码使用 `side_info` 数组判断持仓方向，但实际数据中没有该字段
- **修复**：优先使用 `dir` 字段（如 "Close Long"），其次使用 `startPosition` 字段
- **实现位置**：`core/limit_trade/collectors/hyperliquid_trader_collector.py`

#### 4. 交易记录排序缺失
- **问题**：Binance 和 Hyperliquid 返回的数据可能不是按时间排序
- **修复**：添加排序逻辑，确保所有采集器返回的数据按时间倒序（最新的在前）
- **实现位置**：各交易所数据采集器的 `get_trade_records_async` 方法

#### 5. 系统重启后漏单问题
- **问题**：使用 `limit=1` 时，如果系统停止运行一段时间，重启后可能跳过中间的交易
- **修复**：实现智能回溯机制，检测到订单ID变化时自动回溯查找中间交易
- **实现位置**：`core/limit_trade/limit_follow_executor.py`

### 📝 代码改进

#### 1. 新增配置参数
- `gap_detection_limit`：检测到订单ID变化时，获取更多记录用于回溯查找（默认100条）
- `last_trade_times`：记录每个跟单员的最后处理交易时间戳

#### 2. 代码优化
- 改进了时间字段处理，支持多种格式（毫秒时间戳、ISO字符串）
- 优化了数据排序逻辑，确保类型安全
- 增强了错误处理和日志记录

### 📚 文档更新

#### 更新文档
- `CHANGELOG.md`：添加限价跟单多交易所支持相关更新
- `docs/TELEGRAM_BOT_PLAN.md`：添加限价跟单功能说明

### ⚠️ 注意事项

1. **交易所配置**：
   - 确保在数据库 `customers` 和 `signal_sources` 表中正确配置 `exchange` 字段
   - 支持的交易所：'okx', 'binance', 'hyperliquid'
   - 如果未配置，默认使用 'okx'

2. **订单ID生成**：
   - Binance 订单如果没有 `orderId`，会自动生成唯一标识符
   - 生成的标识符包含时间戳、交易对、方向等信息，确保唯一性

3. **时间范围限制**：
   - 默认查询最近7天的交易记录
   - 如果系统长时间停止运行，可能无法获取超过7天的历史交易
   - 建议保持系统持续运行，避免长时间中断

4. **回溯查找**：
   - 当检测到订单ID跳跃时，会自动获取更多记录进行回溯
   - 如果回溯查找的记录数超过 `gap_detection_limit`，可能仍会遗漏部分交易
   - 建议定期检查系统日志，确保没有异常

### 🚀 下一步计划

- [ ] 支持更多交易所（如 Bybit、Gate.io 等）
- [ ] 实现 WebSocket 实时监听（替代轮询）
- [ ] 优化回溯查找算法，支持分页查询
- [ ] 添加交易记录缓存机制，减少API调用

---

## [🚀已发布] - 2025-11-19

### 🎯 新增功能

#### 1. TradingView 策略过滤器优化
- **功能描述**：支持为每个 TradingView 平台实例配置独立的策略过滤器
- **实现位置**：
  - `core/tradingview/alert_receiver.py`：在消息转发前检查策略过滤器
  - `core/message_forward/manager.py`：在转发规则匹配时再次检查策略过滤器
- **使用场景**：
  - 多个 TradingView 平台实例，每个实例配置不同的策略类型（如 ASR-VC、ASR-TP、ASR-HD）
  - 通过策略过滤器精确控制哪些消息被转发
- **配置方式**：在平台配置中设置 `strategy_filter` 字段，支持逗号分隔的多个策略（如：`ASR-VC,ASR-TP`）
- **匹配逻辑**：
  - 优先使用 `type_` 字段进行完整匹配
  - 如果没有 `type_` 字段，回退到 `strategy` 或 `indicator` 字段
  - 如果所有平台实例的策略过滤器都不匹配，消息将被过滤

#### 2. 消息转发策略过滤器双重检查机制
- **第一层检查**：在 `alert_receiver._send_trade_notification` 中，检查所有 TradingView 平台实例的策略过滤器
- **第二层检查**：在 `MessageForwardManager._on_message_received` 中，如果转发规则指定了源平台ID，会再次检查该平台实例的策略过滤器
- **优势**：确保只有匹配策略过滤器的消息才会被转发到对应的转发规则

### 🔧 功能优化

#### 1. Bootstrap 本地化部署
- **问题**：Bootstrap CSS/JS 和 Bootstrap Icons 字体文件从 CDN 加载失败
- **解决方案**：
  - 创建了 `scripts/download_bootstrap.py` 和 `scripts/download_bootstrap.sh` 脚本，用于下载 Bootstrap 资源到本地
  - 修改了 `frontend/index.html`，优先使用本地文件，CDN 作为备用
  - 修复了 Bootstrap Icons 字体文件路径问题（`./fonts/` → `../font/`）
- **文档**：新增 `docs/BOOTSTRAP_LOCAL_SETUP.md` 说明文档

#### 2. 策略过滤器日志优化
- 添加了详细的日志输出，包括：
  - 策略过滤器匹配/不匹配的详细信息
  - 源平台实例的策略过滤器检查结果
  - 转发规则匹配时的策略过滤器验证

### 🐛 问题修复

#### 1. TradingView 策略过滤器不生效
- **问题**：配置了策略过滤器（如 `ASR-VC`），但其他策略类型（如 `ASR-TP`）的消息仍然被转发
- **原因**：策略过滤器检查逻辑在 `TradingViewPlatform._should_forward` 中，但 webhook 消息通过 Flask API 直接接收，绕过了平台实例的过滤逻辑
- **修复**：
  - 在 `alert_receiver._send_trade_notification` 中添加策略过滤器检查
  - 在 `MessageForwardManager._on_message_received` 中添加转发规则级别的策略过滤器检查
  - 确保只有匹配策略过滤器的消息才会被转发

#### 2. Bootstrap Icons 字体文件 404 错误
- **问题**：`bootstrap-icons.woff2` 和 `bootstrap-icons.woff` 文件返回 404
- **原因**：CSS 文件中的字体路径不正确（`./fonts/` 应该是 `../font/`）
- **修复**：修改了 `frontend/lib/bootstrap-icons/css/bootstrap-icons.css` 中的字体路径

### 📝 代码改进

#### 1. 新增方法
- `MessageForwardManager._get_platform_instance_by_id()`：根据平台ID获取平台实例，优先从监听服务获取，如果不存在则动态创建

#### 2. 代码优化
- 改进了策略过滤器的检查逻辑，支持多个 TradingView 平台实例的独立过滤
- 优化了日志输出，提供更详细的调试信息

### 📚 文档更新

#### 新增文档
- `docs/BOOTSTRAP_LOCAL_SETUP.md`：Bootstrap 本地化部署指南
- `docs/TRADINGVIEW_WEBHOOK_TEST.md`：TradingView Webhook 测试指南（已删除，内容合并到其他文档）

#### 更新文档
- `docs/TELEGRAM_LISTENER_SERVICE.md`：更新了 Telegram 监听服务说明

### 🔄 架构说明

#### TradingView Webhook 处理流程
1. **Webhook 接收**：所有 TradingView webhook 消息通过 Flask API 端点 `/webhook/tradingview` 接收
2. **策略过滤器检查（第一层）**：在 `alert_receiver._send_trade_notification` 中，检查所有 TradingView 平台实例的策略过滤器
3. **消息创建**：如果通过第一层检查，创建 `Message` 对象
4. **转发规则匹配（第二层）**：在 `MessageForwardManager._on_message_received` 中，检查转发规则，如果规则指定了源平台ID，再次检查该平台实例的策略过滤器
5. **消息转发**：只有匹配的转发规则才会被转发

#### 多平台实例支持
- **单一监控**：只有一个 Flask API 端点接收所有 TradingView webhook 消息
- **多实例过滤**：每个 TradingView 平台实例可以配置独立的策略过滤器
- **精确转发**：通过转发规则的源平台ID，确保消息只转发到匹配的平台实例

### ⚠️ 注意事项

1. **策略过滤器配置**：
   - 策略过滤器使用完整匹配（精确匹配）
   - 例如：`type_="ASR-VC"` 必须配置 `"ASR-VC"` 才能匹配
   - 支持多个策略，使用逗号分隔（如：`ASR-VC,ASR-TP`）

2. **转发规则配置**：
   - 建议为每个 TradingView 平台实例创建独立的转发规则
   - 转发规则的 `source_platform_id` 应该对应具体的平台实例ID
   - 这样可以确保策略过滤器在转发规则级别也能正确工作

3. **Bootstrap 本地化**：
   - 如果使用本地 Bootstrap 文件，需要运行 `scripts/download_bootstrap.py` 下载资源
   - 确保 `frontend/lib/` 目录有正确的文件权限

### 🚀 下一步计划

- [ ] 构建 Telegram 机器人（Bot API）
- [ ] 支持 Telegram Bot 命令处理
- [ ] 集成 Telegram Bot 到消息转发系统
- [ ] 支持通过 Telegram Bot 管理订阅和转发规则

---

## 历史版本

### [v1.0.0] - 2025-10-10

#### 主要功能
- 多交易所支持（OKX、Binance）
- 智能跟单系统
- 策略交易引擎
- 消息转发系统
- 热门带单员和巨鲸交易员数据采集
- Redis 缓存优化
- 公开/私域交易员检测

#### 技术特性
- Flask RESTful API
- WebSocket 实时通信
- 异步任务处理
- 数据库连接池
- Redis 缓存层
- 多平台消息转发

---

## 版本说明

- **格式**：`[版本号] - 发布日期`
- **分类**：
  - 🎯 新增功能
  - 🔧 功能优化
  - 🐛 问题修复
  - 📝 代码改进
  - 📚 文档更新
  - ⚠️ 注意事项
  - 🚀 下一步计划

