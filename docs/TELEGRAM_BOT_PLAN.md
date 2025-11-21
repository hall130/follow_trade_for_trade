# Telegram 机器人构建计划

## 📋 概述

本文档描述了如何为千里金量化交易系统构建 Telegram 机器人（Bot），用于：
- 接收和管理交易信号
- 管理订阅和转发规则
- 查询系统状态和统计数据
- 执行管理操作

## 🎯 功能需求

### 1. 核心功能

#### 1.1 交易信号接收
- 接收 TradingView webhook 信号
- 接收其他平台的交易信号
- 支持信号格式化和展示

#### 1.2 订阅管理
- 查看订阅状态
- 续订订阅
- 查看订阅历史

#### 1.3 转发规则管理
- 查看转发规则列表
- 启用/禁用转发规则
- 创建/编辑转发规则（简化版）

#### 1.4 系统状态查询
- 查看平台连接状态
- 查看消息转发统计
- 查看系统运行状态

### 2. 命令列表

```
/start - 启动机器人，显示欢迎信息
/help - 显示帮助信息
/status - 查看系统状态
/subscriptions - 查看订阅列表
/renew <subscription_id> - 续订订阅
/rules - 查看转发规则列表
/enable_rule <rule_id> - 启用转发规则
/disable_rule <rule_id> - 禁用转发规则
/stats - 查看统计信息
```

### 3. 交互式菜单

- 使用 Inline Keyboard 提供快捷操作
- 支持分页浏览（订阅列表、转发规则列表）
- 支持确认对话框（续订、启用/禁用规则）

## 🏗️ 架构设计

### 1. 技术选型

#### 1.1 Python Telegram Bot 库
- **推荐**：`python-telegram-bot` (PTB v20+)
- **优势**：
  - 官方推荐，社区活跃
  - 支持异步操作
  - 功能完善，文档齐全
  - 支持 Webhook 和 Polling 两种模式

#### 1.2 备选方案
- `aiogram`：异步框架，性能优秀
- `telegram-python-bot`：轻量级，简单易用

### 2. 项目结构

```
core/
├── message_forward/
│   ├── platforms/
│   │   ├── telegram_bot.py          # Telegram Bot 平台实现
│   │   └── ...
│   └── ...
├── telegram_bot/
│   ├── __init__.py
│   ├── bot.py                       # Bot 主类
│   ├── handlers/
│   │   ├── __init__.py
│   │   ├── start.py                 # /start 命令处理
│   │   ├── help.py                  # /help 命令处理
│   │   ├── status.py                 # /status 命令处理
│   │   ├── subscriptions.py          # 订阅管理
│   │   ├── rules.py                 # 转发规则管理
│   │   └── stats.py                 # 统计信息
│   ├── keyboards.py                  # Inline Keyboard 生成
│   ├── utils.py                     # 工具函数
│   └── config.py                    # Bot 配置
└── ...
```

### 3. 数据库设计

#### 3.1 新增表：`telegram_bot_users`
```sql
CREATE TABLE telegram_bot_users (
    id INT PRIMARY KEY AUTO_INCREMENT,
    user_id BIGINT NOT NULL UNIQUE COMMENT 'Telegram 用户ID',
    username VARCHAR(255) COMMENT 'Telegram 用户名',
    first_name VARCHAR(255) COMMENT '用户名字',
    last_name VARCHAR(255) COMMENT '用户姓氏',
    is_admin BOOLEAN DEFAULT FALSE COMMENT '是否为管理员',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_user_id (user_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='Telegram Bot 用户表';
```

#### 3.2 新增表：`telegram_bot_chats`
```sql
CREATE TABLE telegram_bot_chats (
    id INT PRIMARY KEY AUTO_INCREMENT,
    chat_id BIGINT NOT NULL UNIQUE COMMENT 'Telegram 聊天ID（群组或频道）',
    chat_type ENUM('private', 'group', 'supergroup', 'channel') NOT NULL,
    title VARCHAR(255) COMMENT '群组/频道标题',
    is_active BOOLEAN DEFAULT TRUE COMMENT '是否激活',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_chat_id (chat_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='Telegram Bot 聊天表';
```

### 4. 集成方案

#### 4.1 作为消息转发平台
- 将 Telegram Bot 作为目标平台，接收转发消息
- 支持发送到私聊、群组、频道

#### 4.2 作为命令处理平台
- 处理用户命令和交互
- 查询系统状态和统计数据
- 管理订阅和转发规则

#### 4.3 与现有系统集成
- 复用 `MessageForwardManager` 和 `SubscriptionService`
- 使用现有的数据库连接和配置管理
- 集成到 `UnifiedListenerService`（如果需要）

## 🔧 实现步骤

### 阶段 1：基础框架搭建（1-2天）

#### 1.1 安装依赖
```bash
pip install python-telegram-bot==20.7
```

#### 1.2 创建 Bot 实例
- 通过 @BotFather 创建 Bot，获取 Token
- 创建 `TelegramBotPlatform` 类，继承 `MessagePlatform`
- 实现基础的连接、发送消息功能

#### 1.3 数据库表创建
- 创建 `telegram_bot_users` 和 `telegram_bot_chats` 表
- 添加数据库操作方法

### 阶段 2：命令处理（2-3天）

#### 2.1 基础命令
- `/start`：欢迎信息和基本介绍
- `/help`：帮助信息和使用说明
- `/status`：系统状态查询

#### 2.2 订阅管理命令
- `/subscriptions`：查看订阅列表（支持分页）
- `/renew <subscription_id>`：续订订阅
- 使用 Inline Keyboard 提供快捷操作

#### 2.3 转发规则管理命令
- `/rules`：查看转发规则列表（支持分页）
- `/enable_rule <rule_id>`：启用转发规则
- `/disable_rule <rule_id>`：禁用转发规则

### 阶段 3：消息转发集成（2-3天）

#### 3.1 作为目标平台
- 实现 `send_message` 方法
- 支持发送到私聊、群组、频道
- 支持 Markdown 格式消息

#### 3.2 消息格式化
- 格式化 TradingView 信号
- 格式化订阅提醒
- 格式化系统通知

### 阶段 4：高级功能（3-5天）

#### 4.1 交互式菜单
- Inline Keyboard 实现
- 分页浏览
- 确认对话框

#### 4.2 权限管理
- 管理员权限检查
- 用户权限验证
- 操作日志记录

#### 4.3 统计信息
- `/stats`：查看系统统计
- 消息转发统计
- 订阅统计
- 平台状态统计

### 阶段 5：测试和优化（2-3天）

#### 5.1 功能测试
- 命令处理测试
- 消息转发测试
- 权限验证测试

#### 5.2 性能优化
- 异步操作优化
- 数据库查询优化
- 消息发送优化

#### 5.3 错误处理
- 异常捕获和处理
- 用户友好的错误提示
- 日志记录

## 📝 代码示例

### 1. Bot 初始化

```python
# core/telegram_bot/bot.py
from telegram import Update
from telegram.ext import Application, CommandHandler, CallbackQueryHandler
from core.message_forward.manager import MessageForwardManager
from core.message_forward.invitation_service import SubscriptionService

class TelegramBot:
    def __init__(self, token: str, manager: MessageForwardManager, subscription_service: SubscriptionService):
        self.token = token
        self.manager = manager
        self.subscription_service = subscription_service
        self.application = Application.builder().token(token).build()
        
        # 注册命令处理器
        self._register_handlers()
    
    def _register_handlers(self):
        """注册命令处理器"""
        self.application.add_handler(CommandHandler("start", self.start_command))
        self.application.add_handler(CommandHandler("help", self.help_command))
        self.application.add_handler(CommandHandler("status", self.status_command))
        self.application.add_handler(CommandHandler("subscriptions", self.subscriptions_command))
        self.application.add_handler(CallbackQueryHandler(self.callback_handler))
    
    async def start_command(self, update: Update, context):
        """处理 /start 命令"""
        await update.message.reply_text(
            "欢迎使用千里金量化交易系统 Bot！\n\n"
            "使用 /help 查看可用命令。"
        )
    
    async def run(self):
        """启动 Bot"""
        await self.application.initialize()
        await self.application.start()
        await self.application.updater.start_polling()
```

### 2. 订阅管理命令

```python
# core/telegram_bot/handlers/subscriptions.py
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

async def subscriptions_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """处理 /subscriptions 命令"""
    user_id = update.effective_user.id
    
    # 获取订阅列表
    subscriptions = await get_subscriptions_for_user(user_id)
    
    if not subscriptions:
        await update.message.reply_text("您当前没有订阅。")
        return
    
    # 生成分页键盘
    keyboard = []
    for sub in subscriptions[:10]:  # 每页显示10个
        keyboard.append([
            InlineKeyboardButton(
                f"{sub['target_platform_name']} - {sub['status']}",
                callback_data=f"sub_detail_{sub['id']}"
            )
        ])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        "您的订阅列表：",
        reply_markup=reply_markup
    )
```

### 3. 消息转发集成

```python
# core/message_forward/platforms/telegram_bot.py
from .base import MessagePlatform
from ..models import Message, MessageType, PlatformType

class TelegramBotPlatform(MessagePlatform):
    """Telegram Bot 平台实现"""
    
    def __init__(self, config: Dict[str, Any]):
        super().__init__(PlatformType.TELEGRAM_BOT, config)
        self.bot_token = config.get('bot_token')
        self.bot = None
    
    async def connect(self) -> bool:
        """连接 Telegram Bot"""
        from telegram import Bot
        self.bot = Bot(token=self.bot_token)
        self.connected = True
        return True
    
    async def send_message(self, chat_id: str, message: Message) -> bool:
        """发送消息"""
        try:
            if message.message_type == MessageType.MARKDOWN:
                await self.bot.send_message(
                    chat_id=int(chat_id),
                    text=message.content,
                    parse_mode='Markdown'
                )
            else:
                await self.bot.send_message(
                    chat_id=int(chat_id),
                    text=message.content
                )
            return True
        except Exception as e:
            logger.error(f"发送 Telegram Bot 消息失败: {e}")
            return False
```

## 🔐 安全考虑

### 1. Token 安全
- Bot Token 存储在配置文件中，不要提交到版本控制
- 使用环境变量或加密配置文件

### 2. 权限控制
- 实现管理员权限检查
- 限制敏感操作的访问

### 3. 输入验证
- 验证用户输入
- 防止 SQL 注入和命令注入

### 4. 速率限制
- 实现命令调用频率限制
- 防止滥用和攻击

## 📊 监控和日志

### 1. 日志记录
- 记录所有命令调用
- 记录消息发送成功/失败
- 记录错误和异常

### 2. 统计信息
- 命令使用统计
- 消息发送统计
- 用户活跃度统计

## 🚀 部署方案

### 1. Webhook 模式（推荐）
- 使用 Webhook 接收更新
- 需要 HTTPS 和公网 IP
- 性能更好，适合生产环境

### 2. Polling 模式
- 使用长轮询获取更新
- 不需要公网 IP
- 适合开发和测试

### 3. 服务管理
- 使用 systemd 管理 Bot 服务
- 支持自动重启和日志管理

## 📚 参考资源

- [python-telegram-bot 文档](https://docs.python-telegram-bot.org/)
- [Telegram Bot API 文档](https://core.telegram.org/bots/api)
- [Telegram Bot 最佳实践](https://core.telegram.org/bots/faq)

## ✅ 验收标准

1. ✅ Bot 可以正常启动和运行
2. ✅ 所有命令都能正常响应
3. ✅ 消息转发功能正常
4. ✅ 订阅管理功能正常
5. ✅ 权限控制正常工作
6. ✅ 错误处理完善
7. ✅ 日志记录完整
8. ✅ 性能满足要求

## 🎯 后续扩展

- [ ] 支持多语言（i18n）
- [ ] 支持自定义命令
- [ ] 支持定时任务
- [ ] 支持消息模板
- [ ] 支持数据分析报告
- [ ] 支持 Webhook 模式部署

