"""
消息转发配置
配置 Telegram、钉钉、微信等平台的连接信息和转发规则
"""

# ============================================================================
# 平台配置
# ============================================================================

MESSAGE_FORWARD_CONFIG = {
    # 平台配置
    'platforms': {
        # Telegram 配置
        'telegram': {
            'enabled': False,  # 是否启用
            'bot_token': '',   # Bot Token（从 @BotFather 获取）
            # 获取方式：https://t.me/BotFather
        },
        
        # 钉钉配置
        'dingtalk': {
            'enabled': False,  # 是否启用
            'webhook_url': '',  # 群机器人 Webhook 地址
            'secret': '',       # 加签密钥（可选，用于安全性验证）
            # 获取方式：钉钉群设置 -> 智能群助手 -> 添加机器人 -> 自定义机器人
            
            # Stream 模式配置（用于接收消息，需要企业内部应用）
            'client_id': '',
            'client_secret': '',
        },
        
        # 微信配置
        'wechat': {
            'enabled': False,  # 是否启用
            'hot_reload': True,  # 是否启用热登录（避免每次都扫码）
            # 注意：微信需要扫码登录，无法完全自动化
        },
    },
    
    # 转发规则
    'forward_rules': [
        # 示例规则 1：Telegram -> 钉钉
        {
            'rule_id': 'rule_tg_to_dt',
            'name': 'Telegram消息转发到钉钉',
            'enabled': False,  # 是否启用此规则
            
            # 源配置
            'source_platform': 'telegram',  # 源平台
            'source_chat_ids': [],  # 源聊天ID列表（留空表示所有聊天）
            
            # 目标配置
            'target_platforms': ['dingtalk'],  # 目标平台列表
            'target_chat_ids': {
                'dingtalk': []  # 钉钉目标群（使用 webhook，可以留空）
            },
            
            # 过滤条件
            'keywords': [],  # 关键词过滤（包含任一关键词才转发）
            'exclude_keywords': [],  # 排除关键词（包含任一关键词则不转发）
            
            # 转换配置
            'add_prefix': '[TG转发] ',  # 添加前缀
            'add_suffix': '',  # 添加后缀
            'enable_markdown': False,  # 是否启用 Markdown
        },
        
        # 示例规则 2：钉钉 -> Telegram
        {
            'rule_id': 'rule_dt_to_tg',
            'name': '钉钉消息转发到Telegram',
            'enabled': False,
            
            'source_platform': 'dingtalk',
            'source_chat_ids': [],
            
            'target_platforms': ['telegram'],
            'target_chat_ids': {
                'telegram': []  # Telegram chat_id 列表
            },
            
            'keywords': [],
            'exclude_keywords': [],
            
            'add_prefix': '[钉钉转发] ',
            'add_suffix': '',
            'enable_markdown': True,
        },
        
        # 示例规则 3：微信 -> 钉钉 + Telegram
        {
            'rule_id': 'rule_wx_to_all',
            'name': '微信消息转发到钉钉和Telegram',
            'enabled': False,
            
            'source_platform': 'wechat',
            'source_chat_ids': [],
            
            'target_platforms': ['dingtalk', 'telegram'],
            'target_chat_ids': {
                'dingtalk': [],
                'telegram': []
            },
            
            'keywords': ['交易', '信号', '订单'],  # 只转发包含这些关键词的消息
            'exclude_keywords': ['测试'],  # 不转发包含"测试"的消息
            
            'add_prefix': '[微信转发] ',
            'add_suffix': '',
            'enable_markdown': False,
        },
    ]
}

# ============================================================================
# 配置说明
# ============================================================================

"""
1. Telegram 配置
   - bot_token: 从 @BotFather 获取
   - 获取步骤:
     1. 打开 Telegram，搜索 @BotFather
     2. 发送 /newbot 创建新机器人
     3. 按提示设置名称
     4. 获取 bot_token

   - 获取 chat_id:
     1. 将机器人添加到群组
     2. 在群组发送任意消息
     3. 访问: https://api.telegram.org/bot<YOUR_BOT_TOKEN>/getUpdates
     4. 从返回的 JSON 中找到 chat.id

2. 钉钉配置
   - webhook_url: 群机器人 Webhook 地址
   - 获取步骤:
     1. 打开钉钉群聊
     2. 群设置 -> 智能群助手 -> 添加机器人 -> 自定义机器人
     3. 设置机器人名称和权限
     4. 复制 Webhook 地址
     5. (可选) 启用加签，复制密钥

3. 微信配置
   - 使用 itchat 库，需要扫码登录
   - hot_reload: 启用后会保存登录状态，避免频繁扫码
   - 首次使用会在终端显示二维码
   
   - 获取 chat_id:
     - 好友: 用户的 UserName
     - 群聊: 群的 UserName
     - 可以通过 itchat.search_friends() 或 itchat.search_chatrooms() 搜索

4. 转发规则配置
   - rule_id: 规则唯一标识
   - source_platform: 源平台 (telegram/dingtalk/wechat)
   - source_chat_ids: 源聊天ID列表，留空表示所有聊天
   - target_platforms: 目标平台列表
   - target_chat_ids: 目标聊天ID，按平台分组
   - keywords: 关键词过滤，包含任一关键词才转发
   - exclude_keywords: 排除关键词，包含任一关键词则不转发
   - add_prefix/add_suffix: 添加前缀/后缀
   - enable_markdown: 是否启用 Markdown 格式

5. 注意事项
   - 所有平台默认都是禁用的 (enabled: False)
   - 使用前需要配置相应的 token/webhook/secret
   - 转发规则也默认禁用，配置完成后设置 enabled: True
   - 微信登录需要人工扫码，无法完全自动化
   - 确保有网络访问对应平台的权限
"""

def get_message_forward_config():
    """获取消息转发配置"""
    return MESSAGE_FORWARD_CONFIG.copy()

