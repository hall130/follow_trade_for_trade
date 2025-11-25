#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Telegram Bot 键盘构建器
用于构建主菜单、订阅管理等界面的键盘
"""

from typing import List, Optional
from telegram import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton


class KeyboardBuilder:
    """键盘构建器"""
    
    @staticmethod
    def build_main_menu() -> ReplyKeyboardMarkup:
        """
        构建主菜单键盘（固定按钮）
        
        Returns:
            ReplyKeyboardMarkup 对象
        """
        keyboard = [
            [KeyboardButton("📊 订阅管理"), KeyboardButton("👤 我的"), KeyboardButton("💬 联系客服")],
        ]
        return ReplyKeyboardMarkup(keyboard, resize_keyboard=True, is_persistent=True)
    
    @staticmethod
    def build_subscription_menu() -> InlineKeyboardMarkup:
        """
        构建订阅管理菜单（Inline 按钮）
        
        Returns:
            InlineKeyboardMarkup 对象
        """
        keyboard = [
            [InlineKeyboardButton("⏱️ 选择时间周期", callback_data="select_intervals")],
            [InlineKeyboardButton("📈 选择策略", callback_data="select_strategies")],
            [
                InlineKeyboardButton("📋 查看当前订阅", callback_data="view_subscription"),
                InlineKeyboardButton("🔙 返回主菜单", callback_data="back_to_main")
            ]
        ]
        return InlineKeyboardMarkup(keyboard)
    
    @staticmethod
    def build_interval_selection(selected: Optional[List[str]] = None, show_back: bool = True, back_to: str = "back_to_subscription_menu") -> InlineKeyboardMarkup:
        """
        构建时间周期选择键盘
        
        Args:
            selected: 已选择的时间周期列表
            show_back: 是否显示返回按钮
            back_to: 返回目标（back_to_subscription_menu 或 back_to_main）
        
        Returns:
            InlineKeyboardMarkup 对象
        """
        if selected is None:
            selected = []
        
        # 时间周期配置（显示名称和值）
        intervals = [
            ("3m", "3分钟"),
            ("5m", "5分钟"),
            ("15m", "15分钟"),
            ("30m", "30分钟"),
            ("1h", "1小时"),
            ("2h", "2小时"),
            ("4h", "4小时"),
            ("1day", "1天")
        ]
        
        buttons = []
        for interval, label in intervals:
            prefix = "✅" if interval in selected else "⚪"
            buttons.append(
                InlineKeyboardButton(
                    f"{prefix} {label}",
                    callback_data=f"toggle_interval:{interval}"
                )
            )
        
        # 每行3个按钮
        keyboard = [buttons[i:i+3] for i in range(0, len(buttons), 3)]
        
        # 添加操作按钮
        action_buttons = [InlineKeyboardButton("✅ 确认选择", callback_data="confirm_intervals")]
        if show_back:
            if back_to == "back_to_subscription_menu":
                action_buttons.append(InlineKeyboardButton("🔙 返回", callback_data="back_to_subscription_menu"))
            else:
                action_buttons.append(InlineKeyboardButton("🏠 主菜单", callback_data="back_to_main"))
        keyboard.append(action_buttons)
        
        return InlineKeyboardMarkup(keyboard)
    
    @staticmethod
    def build_strategy_selection(selected: Optional[List[str]] = None, available_strategies: Optional[List[str]] = None, show_back: bool = True, back_to: str = "back_to_subscription_menu") -> InlineKeyboardMarkup:
        """
        构建策略选择键盘
        
        Args:
            selected: 已选择的策略列表
            available_strategies: 可用的策略列表（如果为 None，使用默认列表）
            show_back: 是否显示返回按钮
            back_to: 返回目标（back_to_subscription_menu 或 back_to_main）
        
        Returns:
            InlineKeyboardMarkup 对象
        """
        if selected is None:
            selected = []
        
        # 默认策略列表（可以从配置中获取）
        if available_strategies is None:
            strategies = [
                ("ASR-VC", "ASR-VC"),
                ("ASR-SC", "ASR-SC"),
                # 可以添加更多策略
            ]
        else:
            strategies = [(s, s) for s in available_strategies]
        
        buttons = []
        for strategy_id, strategy_name in strategies:
            prefix = "✅" if strategy_id in selected else "⚪"
            buttons.append(
                InlineKeyboardButton(
                    f"{prefix} {strategy_name}",
                    callback_data=f"toggle_strategy:{strategy_id}"
                )
            )
        
        # 每行2个按钮
        keyboard = [buttons[i:i+2] for i in range(0, len(buttons), 2)]
        
        # 添加操作按钮
        action_buttons = [InlineKeyboardButton("✅ 确认选择", callback_data="confirm_strategies")]
        if show_back:
            if back_to == "back_to_subscription_menu":
                action_buttons.append(InlineKeyboardButton("🔙 返回", callback_data="back_to_subscription_menu"))
            else:
                action_buttons.append(InlineKeyboardButton("🏠 主菜单", callback_data="back_to_main"))
        keyboard.append(action_buttons)
        
        return InlineKeyboardMarkup(keyboard)
    
    @staticmethod
    def build_save_confirmation(show_back: bool = True) -> InlineKeyboardMarkup:
        """
        构建保存确认键盘
        
        Args:
            show_back: 是否显示返回按钮
        
        Returns:
            InlineKeyboardMarkup 对象
        """
        keyboard = [
            [InlineKeyboardButton("✅ 保存订阅", callback_data="save_subscription")]
        ]
        if show_back:
            keyboard.append([InlineKeyboardButton("🔙 返回修改", callback_data="back_to_previous")])
        return InlineKeyboardMarkup(keyboard)
    
    @staticmethod
    def build_back_button(back_to: str = "back_to_subscription_menu") -> List[InlineKeyboardButton]:
        """
        构建统一的返回按钮
        
        Args:
            back_to: 返回目标
                - back_to_main: 返回主菜单
                - back_to_subscription_menu: 返回订阅管理菜单
                - back_to_previous: 返回上一页
        
        Returns:
            返回按钮列表
        """
        if back_to == "back_to_main":
            return [InlineKeyboardButton("🏠 返回主菜单", callback_data="back_to_main")]
        elif back_to == "back_to_subscription_menu":
            return [InlineKeyboardButton("🔙 返回", callback_data="back_to_subscription_menu")]
        else:
            return [InlineKeyboardButton("🔙 返回", callback_data="back_to_previous")]
    
    @staticmethod
    def build_subscription_status(subscription: dict) -> InlineKeyboardMarkup:
        """
        构建订阅状态显示键盘
        
        Args:
            subscription: 订阅信息字典
        
        Returns:
            InlineKeyboardMarkup 对象
        """
        keyboard = [
            [InlineKeyboardButton("✏️ 修改订阅", callback_data="select_intervals")],
            [InlineKeyboardButton("❌ 取消订阅", callback_data="cancel_subscription")],
            [InlineKeyboardButton("🔙 返回主菜单", callback_data="back_to_main")]
        ]
        return InlineKeyboardMarkup(keyboard)
    
    @staticmethod
    def build_registration_menu() -> InlineKeyboardMarkup:
        """
        构建注册菜单键盘
        
        Returns:
            InlineKeyboardMarkup 对象
        """
        keyboard = [
            [InlineKeyboardButton("1️⃣ 自动注册", callback_data="auto_register")],
            [InlineKeyboardButton("2️⃣ 绑定现有账号", callback_data="bind_existing_account")],
        ]
        return InlineKeyboardMarkup(keyboard)
    
    @staticmethod
    def build_my_account_menu() -> InlineKeyboardMarkup:
        """
        构建我的账号菜单键盘
        
        Returns:
            InlineKeyboardMarkup 对象
        """
        keyboard = [
            [InlineKeyboardButton("⚙️ 配置账号", callback_data="configure_account")],
            [InlineKeyboardButton("🔑 配置 OKX API", callback_data="configure_okx_api")],
            [InlineKeyboardButton("🔑 配置 Binance API", callback_data="configure_binance_api")],
            [InlineKeyboardButton("📈 转发交易配置", callback_data="forward_trade_config")],
            [InlineKeyboardButton("🔙 返回主菜单", callback_data="back_to_main")]
        ]
        return InlineKeyboardMarkup(keyboard)
    
    @staticmethod
    def build_configure_account_menu() -> InlineKeyboardMarkup:
        """
        构建配置账号菜单键盘
        
        Returns:
            InlineKeyboardMarkup 对象
        """
        keyboard = [
            [InlineKeyboardButton("📝 修改用户名", callback_data="input_username")],
            [InlineKeyboardButton("🔒 修改密码", callback_data="input_password")],
            [InlineKeyboardButton("🔙 返回", callback_data="my_account_menu")]
        ]
        return InlineKeyboardMarkup(keyboard)
    
    @staticmethod
    def build_redemption_code_menu(exchange: str) -> InlineKeyboardMarkup:
        """
        构建兑换码菜单键盘
        
        Args:
            exchange: 交易所类型
        
        Returns:
            InlineKeyboardMarkup 对象
        """
        keyboard = [
            [InlineKeyboardButton("📝 输入兑换码", callback_data=f"input_redemption_code:{exchange}")],
            [InlineKeyboardButton("🔙 返回", callback_data="my_account_menu")]
        ]
        return InlineKeyboardMarkup(keyboard)
    
    @staticmethod
    def build_configure_api_menu(exchange: str, has_config: bool = False) -> InlineKeyboardMarkup:
        """
        构建配置 API 菜单键盘
        
        Args:
            exchange: 交易所类型
            has_config: 是否已有配置
        
        Returns:
            InlineKeyboardMarkup 对象
        """
        keyboard = []
        if not has_config:
            keyboard.append([InlineKeyboardButton("📝 输入 API Key", callback_data=f"input_api_key:{exchange}")])
        else:
            keyboard.append([InlineKeyboardButton("🔄 重新配置", callback_data=f"input_api_key:{exchange}")])
        keyboard.append([InlineKeyboardButton("🔙 返回", callback_data="my_account_menu")])
        return InlineKeyboardMarkup(keyboard)

