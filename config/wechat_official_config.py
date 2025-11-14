#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
微信公众号配置
"""

WECHAT_OFFICIAL_CONFIG = {
    "app_id": "wxca0a7ba829d1bd7b",  # 微信公众号 AppID
    "app_secret": "ae91d68b1ea5d8a011651a21a8d82521",  # 微信公众号 AppSecret
    "token": "",  # 用于验证的 token（可选，用于接收消息时验证）
    "enabled": True,  # 是否启用
    
    # 通知配置
    "notifications": {
        "trade": {
            "enabled": True,  # 是否启用交易通知
            "use_template": True,  # 是否使用模板消息（推荐，不受48小时限制）
            "template_id": "",  # 交易通知模板ID（如果 use_template=True 则必须配置）
            # 模板消息格式建议：
            # 标题：交易执行通知
            # 内容：
            #   {{first.DATA}}
            #   交易对：{{keyword1.DATA}}
            #   方向：{{keyword2.DATA}}
            #   金额：{{keyword3.DATA}}
            #   价格：{{keyword4.DATA}}
            #   {{remark.DATA}}
        },
        "alert": {
            "enabled": True,  # 是否启用告警通知
            "use_template": True,  # 是否使用模板消息
            "template_id": "",  # 告警通知模板ID
            "levels": ["error", "warning"],  # 告警级别过滤
        },
        "system": {
            "enabled": True,  # 是否启用系统通知
            "use_template": False,  # 系统通知通常使用客服消息即可
        }
    },
    
    # 用户配置（用户的 openid 列表）
    # openid 是用户在关注公众号后的唯一标识
    # 可以通过以下方式获取：
    # 1. 用户关注公众号后，在消息推送中获取
    # 2. 通过网页授权获取用户 openid
    # 3. 通过用户管理接口获取
    "users": {
        # "user1": "oXXXXXXXXXXXXXX",  # 示例用户
        # "user2": "oYYYYYYYYYYYYYY",  # 示例用户
    }
}


def get_wechat_official_config():
    """获取微信公众号配置"""
    try:
        # 检查配置是否有效
        config = WECHAT_OFFICIAL_CONFIG.copy()
        
        # 如果没有 app_id 或 app_secret，返回 None
        if not config.get("app_id") or not config.get("app_secret"):
            return None
        
        # 如果配置被禁用，返回 None
        if not config.get("enabled", False):
            return None
            
        return config
        
    except Exception as e:
        print(f"获取微信公众号配置失败: {e}")
        return None


def is_wechat_official_enabled():
    """检查微信公众号是否启用"""
    return WECHAT_OFFICIAL_CONFIG.get("enabled", False)


def get_user_openids():
    """获取所有用户的 openid 列表"""
    config = WECHAT_OFFICIAL_CONFIG.get("users", {})
    return list(config.values())


def get_user_openid(user_key: str) -> str:
    """根据用户标识获取 openid"""
    return WECHAT_OFFICIAL_CONFIG.get("users", {}).get(user_key, "")


# ============================================================================
# 配置说明
# ============================================================================

"""
微信公众号配置说明：

1. 获取 AppID 和 AppSecret
   - 登录微信公众平台：https://mp.weixin.qq.com
   - 进入"开发" -> "基本配置"
   - 获取 AppID 和 AppSecret
   - 注意：AppSecret 需要妥善保管，不要泄露

2. 获取用户 openid
   - openid 是用户在关注公众号后的唯一标识
   - 获取方式：
     a) 用户关注公众号后，在消息推送中获取
     b) 通过网页授权获取（需要用户授权）
     c) 通过用户管理接口获取（需要用户已关注）

3. 模板消息配置
   - 登录微信公众平台
   - 进入"功能" -> "模板消息"
   - 申请模板消息（需要审核）
   - 获取模板ID
   - 配置模板数据格式

4. 客服消息 vs 模板消息
   - 客服消息：
     * 优点：配置简单，无需申请模板
     * 缺点：用户必须在48小时内与公众号有过交互
   - 模板消息：
     * 优点：不受48小时限制，可以随时推送
     * 缺点：需要申请模板，格式固定

5. 注意事项
   - 所有推送消息都需要遵守微信公众平台规范
   - 不要发送垃圾消息，避免被微信封禁
   - 建议使用模板消息进行重要通知
   - 客服消息适合临时通知和交互

6. 测试方法
   - 先配置好 AppID 和 AppSecret
   - 获取测试用户的 openid
   - 使用测试代码发送消息验证
"""

