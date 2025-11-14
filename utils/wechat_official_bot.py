#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
微信公众号推送工具
提供简单的API用于发送各种类型的消息到微信公众号
"""

import asyncio
import aiohttp
import time
import json
from typing import Optional, Dict, Any, List
from utils.logger import logger


class WeChatOfficialBot:
    """微信公众号推送客户端"""
    
    def __init__(self, app_id: str, app_secret: str):
        """
        初始化微信公众号推送客户端
        
        Args:
            app_id: 微信公众号 AppID
            app_secret: 微信公众号 AppSecret
        """
        self.app_id = app_id
        self.app_secret = app_secret
        self.api_base_url = 'https://api.weixin.qq.com'
        
        # Access Token 管理
        self.access_token = None
        self.access_token_expires_at = 0
        self._token_lock = asyncio.Lock()
    
    async def _get_access_token(self) -> bool:
        """获取 Access Token（线程安全）"""
        async with self._token_lock:
            # 检查 token 是否还有效
            if self.access_token and time.time() < self.access_token_expires_at:
                return True
            
            try:
                url = f"{self.api_base_url}/cgi-bin/token"
                params = {
                    'grant_type': 'client_credential',
                    'appid': self.app_id,
                    'secret': self.app_secret
                }
                
                async with aiohttp.ClientSession() as session:
                    async with session.get(url, params=params) as response:
                        if response.status != 200:
                            logger.error(f"获取 Access Token 失败，HTTP状态码: {response.status}")
                            return False
                        
                        result = await response.json()
                        
                        if 'access_token' in result:
                            self.access_token = result['access_token']
                            # Access Token 有效期通常是 7200 秒，提前 5 分钟刷新
                            expires_in = result.get('expires_in', 7200)
                            self.access_token_expires_at = time.time() + expires_in - 300
                            logger.info("✅ 获取微信公众号 Access Token 成功")
                            return True
                        else:
                            error_code = result.get('errcode', 'unknown')
                            error_msg = result.get('errmsg', 'unknown error')
                            logger.error(f"获取 Access Token 失败: [{error_code}] {error_msg}")
                            return False
                            
            except Exception as e:
                logger.error(f"获取 Access Token 异常: {e}")
                return False
    
    async def send_text(self, openid: str, content: str) -> bool:
        """
        发送文本消息（客服消息）
        
        Args:
            openid: 用户的 openid（微信公众号用户的唯一标识）
            content: 消息内容
            
        Returns:
            是否发送成功
            
        注意：
            - 用户必须在48小时内与公众号有过交互才能接收客服消息
            - 如果用户超过48小时未交互，需要使用模板消息
        """
        try:
            if not await self._get_access_token():
                return False
            
            url = f"{self.api_base_url}/cgi-bin/message/custom/send"
            params = {'access_token': self.access_token}
            
            payload = {
                'touser': openid,
                'msgtype': 'text',
                'text': {
                    'content': content
                }
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.post(url, params=params, json=payload) as response:
                    if response.status != 200:
                        logger.error(f"发送文本消息失败，HTTP状态码: {response.status}")
                        return False
                    
                    result = await response.json()
                    
                    if result.get('errcode') == 0:
                        logger.info(f"✅ 文本消息已发送到用户: {openid[:8]}...")
                        return True
                    else:
                        error_code = result.get('errcode', 'unknown')
                        error_msg = result.get('errmsg', 'unknown error')
                        
                        # 处理常见错误
                        if error_code == 45015:
                            logger.warning(f"用户 {openid[:8]}... 超过48小时未交互，无法发送客服消息")
                        elif error_code == 40001:
                            logger.warning("Access Token 无效，尝试重新获取")
                            self.access_token = None
                            return await self.send_text(openid, content)  # 重试
                        else:
                            logger.error(f"发送文本消息失败: [{error_code}] {error_msg}")
                        
                        return False
                        
        except Exception as e:
            logger.error(f"发送文本消息异常: {e}")
            return False
    
    async def send_template_message(self, openid: str, template_id: str, 
                                   data: Dict[str, Any], url: Optional[str] = None,
                                   miniprogram: Optional[Dict[str, Any]] = None) -> bool:
        """
        发送模板消息
        
        Args:
            openid: 用户的 openid
            template_id: 模板ID（需要在微信公众平台配置）
            data: 模板数据（格式：{"first": {"value": "..."}, "keyword1": {"value": "..."}, ...}）
            url: 跳转链接（可选）
            miniprogram: 小程序跳转配置（可选，格式：{"appid": "...", "pagepath": "..."}）
            
        Returns:
            是否发送成功
            
        注意：
            - 需要先在微信公众平台申请模板消息
            - 模板数据格式参考：https://developers.weixin.qq.com/doc/offiaccount/Message_Management/Template_Message_Interface.html
        """
        try:
            if not await self._get_access_token():
                return False
            
            api_url = f"{self.api_base_url}/cgi-bin/message/template/send"
            params = {'access_token': self.access_token}
            
            payload = {
                'touser': openid,
                'template_id': template_id,
                'data': data
            }
            
            if url:
                payload['url'] = url
            
            if miniprogram:
                payload['miniprogram'] = miniprogram
            
            async with aiohttp.ClientSession() as session:
                async with session.post(api_url, params=params, json=payload) as response:
                    if response.status != 200:
                        logger.error(f"发送模板消息失败，HTTP状态码: {response.status}")
                        return False
                    
                    result = await response.json()
                    
                    if result.get('errcode') == 0:
                        logger.info(f"✅ 模板消息已发送到用户: {openid[:8]}...")
                        return True
                    else:
                        error_code = result.get('errcode', 'unknown')
                        error_msg = result.get('errmsg', 'unknown error')
                        logger.error(f"发送模板消息失败: [{error_code}] {error_msg}")
                        return False
                        
        except Exception as e:
            logger.error(f"发送模板消息异常: {e}")
            return False
    
    async def send_trade_notification(self, openid: str, trade_info: Dict[str, Any], 
                                     use_template: bool = False, template_id: Optional[str] = None) -> bool:
        """
        发送交易通知
        
        Args:
            openid: 用户的 openid
            trade_info: 交易信息字典
            use_template: 是否使用模板消息（推荐，不受48小时限制）
            template_id: 模板消息ID（如果 use_template=True 则必须提供）
            
        Returns:
            是否发送成功
        """
        # 构建消息内容
        content = f"""
🔄 交易执行通知

交易详情:
- 交易ID: {trade_info.get('trade_uid', 'N/A')}
- 交易对: {trade_info.get('symbol', 'N/A')}
- 方向: {trade_info.get('direction', 'N/A')}
- 持仓方向: {trade_info.get('pos_side', 'N/A')}
- USDT金额: {trade_info.get('volume', 'N/A')} USDT
- 价格: {trade_info.get('price', 'N/A')}
- 客户: {trade_info.get('customer_uid', 'N/A')}
- 策略: {trade_info.get('strategy_uid', 'N/A')}
- 规则: {trade_info.get('rule_uid', 'N/A')}
- 时间: {trade_info.get('time', 'N/A')}

状态: {'✅ 成功' if trade_info.get('success') else '❌ 失败'}
"""
        
        if not trade_info.get('success'):
            content += f"\n错误信息: {trade_info.get('error', 'N/A')}"
        
        if use_template and template_id:
            # 使用模板消息
            template_data = {
                'first': {
                    'value': '交易执行通知',
                    'color': '#173177'
                },
                'keyword1': {
                    'value': trade_info.get('symbol', 'N/A'),
                    'color': '#173177'
                },
                'keyword2': {
                    'value': trade_info.get('direction', 'N/A'),
                    'color': '#173177'
                },
                'keyword3': {
                    'value': f"{trade_info.get('volume', 'N/A')} USDT",
                    'color': '#173177'
                },
                'keyword4': {
                    'value': trade_info.get('price', 'N/A'),
                    'color': '#173177'
                },
                'remark': {
                    'value': '✅ 成功' if trade_info.get('success') else '❌ 失败',
                    'color': '#173177'
                }
            }
            return await self.send_template_message(openid, template_id, template_data)
        else:
            # 使用客服消息
            return await self.send_text(openid, content)
    
    async def send_alert_notification(self, openid: str, alert_type: str, 
                                      alert_info: Dict[str, Any],
                                      use_template: bool = False, 
                                      template_id: Optional[str] = None) -> bool:
        """
        发送告警通知
        
        Args:
            openid: 用户的 openid
            alert_type: 告警类型 (error, warning, info)
            alert_info: 告警信息字典
            use_template: 是否使用模板消息
            template_id: 模板消息ID
            
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
        
        # 构建消息内容
        content = f"""
{icon} {alert_info.get('title', '系统告警')}

告警级别: {alert_info.get('level', alert_type).upper()}
告警时间: {alert_info.get('time', 'N/A')}
告警消息: {alert_info.get('message', 'N/A')}

详细信息:
- 账户: {alert_info.get('account', 'N/A')}
- 策略: {alert_info.get('strategy', 'N/A')}
- 交易对: {alert_info.get('symbol', 'N/A')}

建议操作: {alert_info.get('suggestion', '请及时处理')}
"""
        
        if use_template and template_id:
            # 使用模板消息
            template_data = {
                'first': {
                    'value': f"{icon} {alert_info.get('title', '系统告警')}",
                    'color': '#173177'
                },
                'keyword1': {
                    'value': alert_info.get('level', alert_type).upper(),
                    'color': '#173177'
                },
                'keyword2': {
                    'value': alert_info.get('message', 'N/A'),
                    'color': '#173177'
                },
                'keyword3': {
                    'value': alert_info.get('account', 'N/A'),
                    'color': '#173177'
                },
                'remark': {
                    'value': alert_info.get('suggestion', '请及时处理'),
                    'color': '#173177'
                }
            }
            return await self.send_template_message(openid, template_id, template_data)
        else:
            # 使用客服消息
            return await self.send_text(openid, content)
    
    async def send_to_multiple_users(self, openids: List[str], content: str) -> Dict[str, bool]:
        """
        批量发送消息到多个用户
        
        Args:
            openids: 用户 openid 列表
            content: 消息内容
            
        Returns:
            每个用户的发送结果字典 {openid: success}
        """
        results = {}
        for openid in openids:
            results[openid] = await self.send_text(openid, content)
            # 避免频率限制，稍微延迟
            await asyncio.sleep(0.1)
        return results


# 全局微信公众号推送实例
_wechat_official_bot = None


def get_wechat_official_bot() -> Optional[WeChatOfficialBot]:
    """获取全局微信公众号推送实例"""
    global _wechat_official_bot
    return _wechat_official_bot


def init_wechat_official_bot(app_id: str, app_secret: str):
    """初始化微信公众号推送客户端"""
    global _wechat_official_bot
    
    try:
        if not app_id or not app_secret:
            logger.warning("微信公众号 app_id 或 app_secret 为空，跳过初始化")
            return False
        
        _wechat_official_bot = WeChatOfficialBot(app_id, app_secret)
        logger.info("微信公众号推送客户端初始化完成")
        return True
        
    except Exception as e:
        logger.error(f"微信公众号推送客户端初始化失败: {e}")
        return False


async def send_text(openid: str, content: str) -> bool:
    """发送文本消息"""
    bot = get_wechat_official_bot()
    if bot:
        return await bot.send_text(openid, content)
    else:
        logger.warning("微信公众号推送客户端未初始化，跳过文本消息发送")
        return False


async def send_template_message(openid: str, template_id: str, 
                               data: Dict[str, Any], url: Optional[str] = None,
                               miniprogram: Optional[Dict[str, Any]] = None) -> bool:
    """发送模板消息"""
    bot = get_wechat_official_bot()
    if bot:
        return await bot.send_template_message(openid, template_id, data, url, miniprogram)
    else:
        logger.warning("微信公众号推送客户端未初始化，跳过模板消息发送")
        return False


async def send_trade_notification(openid: str, trade_info: Dict[str, Any], 
                                 use_template: bool = False, 
                                 template_id: Optional[str] = None) -> bool:
    """发送交易通知"""
    bot = get_wechat_official_bot()
    if bot:
        return await bot.send_trade_notification(openid, trade_info, use_template, template_id)
    else:
        logger.warning("微信公众号推送客户端未初始化，跳过交易通知")
        return False


async def send_alert_notification(openid: str, alert_type: str, 
                                 alert_info: Dict[str, Any],
                                 use_template: bool = False, 
                                 template_id: Optional[str] = None) -> bool:
    """发送告警通知"""
    bot = get_wechat_official_bot()
    if bot:
        return await bot.send_alert_notification(openid, alert_type, alert_info, 
                                                use_template, template_id)
    else:
        logger.warning("微信公众号推送客户端未初始化，跳过告警通知")
        return False

