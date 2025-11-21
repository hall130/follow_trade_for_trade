# 更新日志

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

