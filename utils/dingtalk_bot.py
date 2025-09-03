#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import requests
import json
import time
import hmac
import hashlib
import base64
import urllib.parse
import asyncio
import aiohttp
from typing import Optional, Dict, Any
from utils.logger import logger

class DingTalkBot:
    """钉钉机器人客户端"""
    
    def __init__(self, webhook_url: str, secret: str = None):
        """
        初始化钉钉机器人
        
        Args:
            webhook_url: 钉钉机器人webhook地址
            secret: 钉钉机器人签名密钥
        """
        self.webhook_url = webhook_url
        self.secret = secret
    
    def _get_sign(self, timestamp: int) -> str:
        """
        生成钉钉机器人签名
        
        加签计算步骤：
        1. 将时间戳 timestamp 和密钥 secret 当做签名字符串
        2. 使用HmacSHA256算法计算签名
        3. 进行Base64 encode
        4. 最后再把签名参数再进行urlEncode
        
        Args:
            timestamp: 时间戳（毫秒）
            
        Returns:
            签名字符串
        """
        if not self.secret:
            return ""
        
        # 1. 构造签名字符串：timestamp + '\n' + secret
        string_to_sign = f"{timestamp}\n{self.secret}"
        
        # 2. 使用HmacSHA256算法计算签名
        hmac_code = hmac.new(
            self.secret.encode('utf-8'),
            string_to_sign.encode('utf-8'),
            digestmod=hashlib.sha256
        ).digest()
        
        # 3. Base64 encode
        base64_sign = base64.b64encode(hmac_code)
        
        # 4. URL encode
        sign = urllib.parse.quote_plus(base64_sign)
        
        return sign
    
    def _get_webhook_url(self) -> str:
        """
        获取带签名的webhook URL
        
        Returns:
            完整的webhook URL
        """
        timestamp = int(time.time() * 1000)
        sign = self._get_sign(timestamp)
        
        if sign:
            return f"{self.webhook_url}&timestamp={timestamp}&sign={sign}"
        return self.webhook_url
    
    def send_text(self, content: str, at_mobiles: list = None, at_all: bool = False) -> bool:
        """
        发送文本消息（同步方式）
        
        Args:
            content: 消息内容
            at_mobiles: 要@的手机号列表
            at_all: 是否@所有人
            
        Returns:
            是否发送成功
        """
        # 添加关键词"推送"以通过钉钉安全设置
        content_with_keyword = f"推送：{content}"
        
        data = {
            "msgtype": "text",
            "text": {
                "content": content_with_keyword
            },
            "at": {
                "atMobiles": at_mobiles or [],
                "isAtAll": at_all
            }
        }
        
        return self._send_message(data)
    
    async def send_text_async(self, content: str, at_mobiles: list = None, at_all: bool = False) -> bool:
        """
        异步发送文本消息
        
        Args:
            content: 消息内容
            at_mobiles: 要@的手机号列表
            at_all: 是否@所有人
            
        Returns:
            是否发送成功
        """

        data = {
            "msgtype": "text",
            "text": {
                "content": content
            },
            "at": {
                "atMobiles": at_mobiles or [],
                "isAtAll": at_all
            }
        }
        
        return await self._send_message_async(data)
    
    def send_markdown(self, title: str, text: str, at_mobiles: list = None, at_all: bool = False) -> bool:
        """
        发送markdown消息（同步方式）
        
        Args:
            title: 消息标题
            text: markdown格式的消息内容
            at_mobiles: 要@的手机号列表
            at_all: 是否@所有人
            
        Returns:
            是否发送成功
        """
        # 添加关键词"推送"以通过钉钉安全设置
        text_with_keyword = f"推送\n\n{text}"
        
        data = {
            "msgtype": "markdown",
            "markdown": {
                "title": title,
                "text": text_with_keyword
            },
            "at": {
                "atMobiles": at_mobiles or [],
                "isAtAll": at_all
            }
        }
        
        return self._send_message(data)
    
    async def send_markdown_async(self, title: str, text: str, at_mobiles: list = None, at_all: bool = False) -> bool:
        """
        异步发送markdown消息
        
        Args:
            title: 消息标题
            text: markdown格式的消息内容
            at_mobiles: 要@的手机号列表
            at_all: 是否@所有人
            
        Returns:
            是否发送成功
        """
        # 添加关键词"推送"以通过钉钉安全设置
        text_with_keyword = f"推送\n\n{text}"
        
        data = {
            "msgtype": "markdown",
            "markdown": {
                "title": title,
                "text": text_with_keyword
            },
            "at": {
                "atMobiles": at_mobiles or [],
                "isAtAll": at_all
            }
        }
        
        return await self._send_message_async(data)
    
    def send_trade_notification(self, trade_info: Dict[str, Any]) -> bool:
        """
        发送交易通知（同步方式）
        
        Args:
            trade_info: 交易信息字典
            
        Returns:
            是否发送成功
        """
        title = "🔄 交易执行通知"
        
        # 构建markdown内容
        text = f"""
### {title}

**交易详情:**
- **交易ID**: `{trade_info.get('trade_uid', 'N/A')}`
- **交易对**: `{trade_info.get('symbol', 'N/A')}`
- **方向**: `{trade_info.get('direction', 'N/A')}`
- **持仓方向**: `{trade_info.get('pos_side', 'N/A')}`
- **USDT金额**: `{trade_info.get('volume', 'N/A')} USDT`
- **价格**: `{trade_info.get('price', 'N/A')}`
- **客户**: `{trade_info.get('customer_uid', 'N/A')}`
- **策略**: `{trade_info.get('strategy_uid', 'N/A')}`
- **规则**: `{trade_info.get('rule_uid', 'N/A')}`
- **时间**: `{trade_info.get('time', 'N/A')}`

**状态**: {'✅ 成功' if trade_info.get('success') else '❌ 失败'}
"""
        
        if not trade_info.get('success'):
            text += f"\n**错误信息**: {trade_info.get('error', 'N/A')}"
        
        return self.send_markdown(title, text)
    
    async def send_trade_notification_async(self, trade_info: Dict[str, Any]) -> bool:
        """
        异步发送交易通知
        
        Args:
            trade_info: 交易信息字典
            
        Returns:
            是否发送成功
        """
        title = "🔄 交易执行通知"
        
        # 构建markdown内容
        text = f"""
### {title}

**交易详情:**
- **交易ID**: `{trade_info.get('trade_uid', 'N/A')}`
- **交易对**: `{trade_info.get('symbol', 'N/A')}`
- **方向**: `{trade_info.get('direction', 'N/A')}`
- **持仓方向**: `{trade_info.get('pos_side', 'N/A')}`
- **USDT金额**: `{trade_info.get('volume_usdt', 'N/A')} USDT`
- **价格**: `{trade_info.get('price', 'N/A')}`
- **客户**: `{trade_info.get('customer_uid', 'N/A')}`
- **策略**: `{trade_info.get('strategy_uid', 'N/A')}`
- **规则**: `{trade_info.get('rule_uid', 'N/A')}`
- **时间**: `{trade_info.get('time', 'N/A')}`

**状态**: {'✅ 成功' if trade_info.get('success') else '❌ 失败'}
"""
        
        if not trade_info.get('success'):
            text += f"\n**错误信息**: {trade_info.get('error', 'N/A')}"
        
        return await self.send_markdown_async(title, text)
    
    def send_alert_notification(self, alert_type: str, alert_info: Dict[str, Any]) -> bool:
        """
        发送告警通知
        
        Args:
            alert_type: 告警类型 (error, warning, info)
            alert_info: 告警信息字典
            
        Returns:
            是否发送成功
        """
        # 根据告警类型选择图标
        icons = {
            "error": "🚨",
            "warning": "⚠️",
            "info": "ℹ️"
        }
        icon = icons.get(alert_type, "ℹ️")
        
        title = f"{icon} {alert_info.get('title', '系统告警')}"
        
        # 构建markdown内容
        text = f"""
### {title}

**告警级别**: `{alert_info.get('level', alert_type).upper()}`
**告警时间**: `{alert_info.get('time', 'N/A')}`
**告警消息**: {alert_info.get('message', 'N/A')}

**详细信息:**
- **账户**: `{alert_info.get('account', 'N/A')}`
- **策略**: `{alert_info.get('strategy', 'N/A')}`
- **交易对**: `{alert_info.get('symbol', 'N/A')}`

**建议操作**: {alert_info.get('suggestion', '请及时处理')}
"""
        
        return self.send_markdown(title, text)
    
    async def send_alert_notification_async(self, alert_type: str, alert_info: Dict[str, Any]) -> bool:
        """
        异步发送告警通知
        
        Args:
            alert_type: 告警类型 (error, warning, info)
            alert_info: 告警信息字典
            
        Returns:
            是否发送成功
        """
        # 根据告警类型选择图标
        icons = {
            "error": "🚨",
            "warning": "⚠️",
            "info": "ℹ️"
        }
        icon = icons.get(alert_type, "ℹ️")
        
        title = f"{icon} {alert_info.get('title', '系统告警')}"
        
        # 构建markdown内容
        text = f"""
### {title}

**告警级别**: `{alert_info.get('level', alert_type).upper()}`
**告警时间**: `{alert_info.get('time', 'N/A')}`
**告警消息**: {alert_info.get('message', 'N/A')}

**详细信息:**
- **账户**: `{alert_info.get('account', 'N/A')}`
- **策略**: `{alert_info.get('strategy', 'N/A')}`
- **交易对**: `{alert_info.get('symbol', 'N/A')}`
- **检查时间**: `{alert_info.get('last_check', 'N/A')}`
- **异常信号源**: `{', '.join(alert_info.get('account', [])) if alert_info.get('signal_sources') else 'N/A'}`

**建议操作**: {alert_info.get('suggestion', '请及时处理')}
"""
        
        return await self.send_markdown_async(title, text)
    
    def _send_message(self, data: Dict[str, Any]) -> bool:
        """
        发送消息到钉钉机器人（同步方式）
        
        Args:
            data: 消息数据
            
        Returns:
            是否发送成功
        """
        try:
            webhook_url = self._get_webhook_url()
            headers = {
                'Content-Type': 'application/json; charset=utf-8'
            }
            
            response = requests.post(
                webhook_url,
                headers=headers,
                data=json.dumps(data),
                timeout=10
            )
            
            if response.status_code == 200:
                result = response.json()
                if result.get('errcode') == 0:
                    logger.info(f"钉钉消息发送成功: {data.get('msgtype', 'unknown')}")
                    return True
                else:
                    logger.error(f"钉钉消息发送失败: {result}")
                    return False
            else:
                logger.error(f"钉钉消息发送失败，HTTP状态码: {response.status_code}")
                return False
                
        except Exception as e:
            logger.error(f"钉钉消息发送异常: {e}")
            return False
    
    async def _send_message_async(self, data: Dict[str, Any]) -> bool:
        """
        异步发送消息到钉钉机器人
        
        Args:
            data: 消息数据
            
        Returns:
            是否发送成功
        """
        try:
            webhook_url = self._get_webhook_url()
            headers = {
                'Content-Type': 'application/json; charset=utf-8'
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    webhook_url,
                    headers=headers,
                    data=json.dumps(data),
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as response:
                    if response.status == 200:
                        result = await response.json()
                        if result.get('errcode') == 0:
                            logger.info(f"钉钉消息异步发送成功: {data.get('msgtype', 'unknown')}")
                            return True
                        else:
                            logger.error(f"钉钉消息异步发送失败: {result}")
                            return False
                    else:
                        logger.error(f"钉钉消息异步发送失败，HTTP状态码: {response.status}")
                        return False
                        
        except Exception as e:
            logger.error(f"钉钉消息异步发送异常: {e}")
            return False


# 全局钉钉机器人实例
_dingtalk_bot = None

def get_dingtalk_bot() -> Optional[DingTalkBot]:
    """获取全局钉钉机器人实例"""
    global _dingtalk_bot
    return _dingtalk_bot

def init_dingtalk_bot(webhook_url: str, secret: str = None):
    """初始化钉钉机器人"""
    global _dingtalk_bot
    
    try:
        if not webhook_url:
            logger.warning("钉钉机器人webhook地址为空，跳过初始化")
            return False
        
        _dingtalk_bot = DingTalkBot(webhook_url, secret)
        logger.info("钉钉机器人初始化完成")
        return True
        
    except Exception as e:
        logger.error(f"钉钉机器人初始化失败: {e}")
        return False

def send_text(content: str, at_mobiles: list = None, at_all: bool = False) -> bool:
    """发送文本消息（同步方式）"""
    bot = get_dingtalk_bot()
    if bot:
        return bot.send_text(content, at_mobiles, at_all)
    else:
        logger.warning("钉钉机器人未初始化，跳过文本消息发送")
        return False

def send_trade_notification(trade_info: Dict[str, Any]) -> bool:
    """发送交易通知（同步方式）"""
    bot = get_dingtalk_bot()
    if bot:
        return bot.send_trade_notification(trade_info)
    else:
        logger.warning("钉钉机器人未初始化，跳过交易通知")
        return False

async def send_text_async(content: str, at_mobiles: list = None, at_all: bool = False) -> bool:
    """异步发送文本消息"""
    bot = get_dingtalk_bot()
    if bot:
        return await bot.send_text_async(content, at_mobiles, at_all)
    else:
        logger.warning("钉钉机器人未初始化，跳过文本消息发送")
        return False

async def send_trade_notification_async(trade_info: Dict[str, Any]) -> bool:
    """异步发送交易通知"""
    bot = get_dingtalk_bot()
    if bot:
        return await bot.send_trade_notification_async(trade_info)
    else:
        logger.warning("钉钉机器人未初始化，跳过交易通知")
        return False

def send_alert_notification(alert_type: str, alert_info: Dict[str, Any]) -> bool:
    """发送告警通知（同步方式）"""
    bot = get_dingtalk_bot()
    if bot:
        return bot.send_alert_notification(alert_type, alert_info)
    else:
        logger.warning("钉钉机器人未初始化，跳过告警通知")
        return False

async def send_alert_notification_async(alert_type: str, alert_info: Dict[str, Any]) -> bool:
    """异步发送告警通知"""
    bot = get_dingtalk_bot()
    if bot:
        return await bot.send_alert_notification_async(alert_type, alert_info)
    else:
        logger.warning("钉钉机器人未初始化，跳过告警通知")
        return False 