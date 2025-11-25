#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Telegram Bot 消息格式化工具
将 TradingView 消息格式化为 Telegram Markdown 格式
"""

from typing import Dict, Any, Optional
from datetime import datetime, timezone, timedelta
from utils.logger import get_logger

logger = get_logger(__name__)


def format_tradingview_message_for_telegram(message: 'Message') -> str:
    """
    格式化 TradingView 消息为 Telegram Markdown 格式
    
    使用与钉钉相同的格式，但适配 Telegram 的 Markdown 语法：
    - Telegram 使用 *粗体* 而不是 **粗体**
    - Telegram 使用 _斜体_ 而不是 *斜体*
    
    Args:
        message: Message 对象，包含 TradingView 交易信号信息
    
    Returns:
        格式化后的 Markdown 消息文本
    """
    try:
        # 从消息的 extra_data 中提取交易信息
        trade_info = message.extra_data.get('trade_info', {})
        original_data = trade_info.get('original_data', {})
        
        # 提取交易类型
        original_action = trade_info.get('original_action', '').upper()
        direct = trade_info.get('direct', '').upper()
        
        # 判断交易类型
        trade_type = ""
        if original_action == 'BUY' and direct == 'SHORT':
            trade_type = "平空"
        elif original_action == 'SELL' and direct == 'LONG':
            trade_type = "平多"
        elif original_action == 'BUY' and direct == 'LONG':
            trade_type = "开多"
        elif original_action == 'SELL' and direct == 'SHORT':
            trade_type = "开空"
        elif original_action == 'BUY':
            trade_type = "买入"
        elif original_action == 'SELL':
            trade_type = "卖出"
        elif original_action == 'CLOSE' or trade_info.get('action') == 'close':
            if direct == 'SHORT':
                trade_type = "平空"
            elif direct == 'LONG':
                trade_type = "平多"
            else:
                trade_type = "平仓"
        else:
            trade_type = f"{original_action or trade_info.get('action', '')}"
        
        # 格式化价格
        price = trade_info.get('price', 0)
        price_str = f"${price:,.2f}" if price else "$0.00"
        
        # 提取合约名称（从消息内容或 trade_info 中）
        contract_name = "未知合约"
        symbol = trade_info.get('symbol', '')
        if symbol:
            # 提取基础币种（简化版，实际应该使用 alert_receiver.py 中的逻辑）
            base_symbol = symbol
            for suffix in ['USDT', 'USDC', 'USD', 'BTC', 'ETH']:
                if symbol.endswith(suffix) and len(symbol) > len(suffix):
                    base_symbol = symbol[:-len(suffix)]
                    break
            if not base_symbol or len(base_symbol) < 2:
                base_symbol = symbol[:3] if len(symbol) >= 3 else symbol
            contract_name = f"{base_symbol.replace('USD', '').replace('USDT', '').replace('USDC', '')}-USDT-SWAP"
        
        # 格式化周期显示
        interval = trade_info.get('interval', '')
        interval_display = ''
        if interval:
            interval_upper = interval.upper()
            if interval_upper.endswith('M'):
                minutes = interval_upper.replace('M', '')
                try:
                    minutes_int = int(minutes)
                    interval_display = f"{minutes_int}分钟"
                except ValueError:
                    interval_display = interval
            elif interval_upper.endswith('H'):
                hours = interval_upper.replace('H', '')
                try:
                    hours_int = int(hours)
                    interval_display = f"{hours_int}小时"
                except ValueError:
                    interval_display = interval
            elif interval_upper in ['1DAY', '1D', 'DAY', 'D']:
                interval_display = "1天"
            else:
                interval_display = interval
        
        # 获取消息内容
        message_content_text = trade_info.get('message', '')
        
        # 格式化时间（使用中国时区）
        china_tz = timezone(timedelta(hours=8))
        timestamp = trade_info.get('timestamp')
        
        if timestamp is None:
            china_time = datetime.now(china_tz)
        else:
            if timestamp.tzinfo is None:
                timestamp = timestamp.replace(tzinfo=timezone.utc)
            china_time = timestamp.astimezone(china_tz)
        
        time_str = china_time.strftime('%Y-%m-%d %H:%M:%S')
        
        # 构建 Telegram Markdown 消息
        # Telegram 使用 *粗体* 而不是 **粗体**
        # Telegram 使用 _斜体_ 而不是 *斜体*
        message_text = f"""🔔 TradingView 交易信号

📊 *交易类型*: {trade_type}

💵 *价格*:     {price_str}

📈 *合约*:     {contract_name}"""
        
        # 如果有周期信息，添加到消息中
        if interval_display:
            message_text += f"""

⏱️ *周期*:     {interval_display}"""
        
        message_text += f"""

🆔 *消息内容*: {message_content_text}

⏰ *时间*:     {time_str}

---

_来自千里金交易平台_"""
        
        return message_text
        
    except Exception as e:
        logger.error(f"格式化 TradingView 消息失败: {e}")
        import traceback
        logger.error(traceback.format_exc())
        # 返回简化版本
        return f"🔔 TradingView 交易信号\n\n{message.content}"


def escape_markdown_v2(text: str) -> str:
    """
    转义 Telegram MarkdownV2 特殊字符
    
    如果使用 MarkdownV2 模式，需要转义以下字符：
    '_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!'
    
    Args:
        text: 需要转义的文本
    
    Returns:
        转义后的文本
    """
    special_chars = ['_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!']
    for char in special_chars:
        text = text.replace(char, f'\\{char}')
    return text


def format_message_for_telegram_markdown_v2(message: 'Message') -> str:
    """
    格式化消息为 Telegram MarkdownV2 格式
    
    注意：MarkdownV2 需要转义所有特殊字符，使用更复杂
    建议使用 format_tradingview_message_for_telegram 和 Markdown 模式
    
    Args:
        message: Message 对象
    
    Returns:
        格式化后的 MarkdownV2 消息文本
    """
    try:
        trade_info = message.extra_data.get('trade_info', {})
        original_action = trade_info.get('original_action', '').upper()
        direct = trade_info.get('direct', '').upper()
        
        # 判断交易类型
        trade_type = ""
        if original_action == 'BUY' and direct == 'SHORT':
            trade_type = "平空"
        elif original_action == 'SELL' and direct == 'LONG':
            trade_type = "平多"
        elif original_action == 'BUY' and direct == 'LONG':
            trade_type = "开多"
        elif original_action == 'SELL' and direct == 'SHORT':
            trade_type = "开空"
        else:
            trade_type = original_action or "未知"
        
        # 转义所有特殊字符
        trade_type = escape_markdown_v2(trade_type)
        price_str = escape_markdown_v2(f"${trade_info.get('price', 0):,.2f}")
        contract_name = escape_markdown_v2(trade_info.get('contract_name', '未知合约'))
        message_content = escape_markdown_v2(trade_info.get('message', ''))
        time_str = escape_markdown_v2(datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
        
        # 构建 MarkdownV2 消息（使用 *粗体*）
        message_text = f"""🔔 TradingView 交易信号

📊 *交易类型*: {trade_type}

💵 *价格*:     {price_str}

📈 *合约*:     {contract_name}

🆔 *消息内容*: {message_content}

⏰ *时间*:     {time_str}

\\-\\-\\-

_来自千里金交易平台_"""
        
        return message_text
        
    except Exception as e:
        logger.error(f"格式化 MarkdownV2 消息失败: {e}")
        return escape_markdown_v2(message.content)

