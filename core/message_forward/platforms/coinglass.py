"""
CoinGlass消息平台实现
支持获取CoinGlass巨鲸提醒并转发

API文档: https://docs.coinglass.com/v4.0-zh/reference/hyperliquid-whale-alert
"""

from typing import Callable, Dict, List, Optional, Any
import asyncio
import aiohttp
import hmac
import hashlib
import base64
import time
from datetime import datetime

from ..base import MessagePlatform
from ..models import Message, MessageType, PlatformType
from utils.logger import get_logger

logger = get_logger(__name__)


class CoinGlassPlatform(MessagePlatform):
    """CoinGlass消息平台（巨鲸提醒）"""
    
    def __init__(self, config: Dict[str, Any]):
        super().__init__(PlatformType.COINGLASS, config)
        
        # API配置
        self.api_key = config.get('api_key', '')  # CoinGlass API Key
        self.api_secret = config.get('api_secret', '')  # CoinGlass API Secret
        self.api_base_url = config.get('api_base_url', 'https://open-api-v4.coinglass.com')
        
        # 监听配置
        self.enable_whale_alert = config.get('enable_whale_alert', True)  # 是否启用巨鲸提醒
        self.polling_interval = config.get('polling_interval', 10)  # 轮询间隔（秒）
        self.min_position_value = config.get('min_position_value', 1000000)  # 最小持仓价值（美元，默认100万）
        
        # 状态
        self.session = None
        self.listening = False
        self.last_check_time = 0  # 最后检查时间戳
        self.last_alert_ids = set()  # 已处理提醒ID集合（防止重复）
        self.max_history_size = 1000  # 最大历史记录数
        
        if not self.api_key:
            logger.warning("CoinGlass API Key 未配置")
            self.enabled = False
    
    async def connect(self) -> bool:
        """连接到CoinGlass"""
        if not self.enabled:
            logger.warning("CoinGlass平台未启用")
            return False
        
        try:
            logger.info("正在连接CoinGlass...")
            
            # 创建HTTP会话
            self.session = aiohttp.ClientSession()
            
            # 测试API连接（获取巨鲸提醒）
            if await self._test_api_connection():
                self.connected = True
                logger.info("✅ CoinGlass连接成功")
                return True
            else:
                logger.error("CoinGlass API测试失败")
                self.connected = False
                return False
                
        except Exception as e:
            logger.error(f"CoinGlass连接失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
            self.connected = False
            return False
    
    async def _test_api_connection(self) -> bool:
        """测试API连接"""
        try:
            url = f'{self.api_base_url}/api/hyperliquid/whale-alert'
            headers = self._build_headers()
            
            async with self.session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=10)) as response:
                if response.status == 200:
                    data = await response.json()
                    if data.get('code') == '0':
                        logger.info(f"✅ CoinGlass API连接成功，获取到 {len(data.get('data', []))} 条巨鲸提醒")
                        return True
                    else:
                        logger.error(f"CoinGlass API返回错误: {data.get('msg', 'Unknown error')}")
                        return False
                elif response.status == 401:
                    logger.error("CoinGlass API认证失败，请检查API Key和Secret")
                    return False
                else:
                    logger.error(f"CoinGlass API请求失败: {response.status}")
                    text = await response.text()
                    logger.error(f"响应内容: {text}")
                    return False
                    
        except Exception as e:
            logger.error(f"测试CoinGlass API连接失败: {e}")
            return False
    
    def _build_headers(self) -> Dict[str, str]:
        """构建请求头（包含身份验证）"""
        headers = {
            'Content-Type': 'application/json',
            'Accept': 'application/json'
        }
        
        # CoinGlass API v4.0 身份验证
        # 根据CoinGlass API文档，通常使用Header传递API Key
        # 常见方式：'CG-API-KEY' 或 'Authorization' 或 'X-API-KEY'
        if self.api_key:
            # 尝试多种常见的Header格式
            headers['CG-API-KEY'] = self.api_key
            headers['X-API-KEY'] = self.api_key
            headers['Authorization'] = f'Bearer {self.api_key}'
            
            # 如果配置了Secret，使用签名认证（如果API支持）
            if self.api_secret:
                timestamp = str(int(time.time() * 1000))
                # 构建签名字符串（根据实际API文档调整格式）
                sign_string = f'{self.api_key}{timestamp}{self.api_secret}'
                signature = hmac.new(
                    self.api_secret.encode('utf-8'),
                    sign_string.encode('utf-8'),
                    hashlib.sha256
                ).hexdigest()
                
                headers['CG-TIMESTAMP'] = timestamp
                headers['CG-SIGN'] = signature
        
        return headers
    
    async def disconnect(self) -> bool:
        """断开连接"""
        try:
            self.listening = False
            
            if self.session:
                await self.session.close()
                self.session = None
            
            self.connected = False
            logger.info("CoinGlass连接已断开")
            return True
            
        except Exception as e:
            logger.error(f"断开连接失败: {e}")
            return False
    
    async def send_message(self, chat_id: str, message: Message) -> bool:
        """发送消息到CoinGlass（CoinGlass主要是接收数据，不支持发送）"""
        logger.warning("CoinGlass平台主要用于接收巨鲸提醒，不支持发送消息")
        return False
    
    async def listen(self, callback: Callable[[Message], None]) -> None:
        """监听CoinGlass巨鲸提醒"""
        if not self.connected:
            logger.error("CoinGlass未连接，无法监听")
            return
        
        if not self.enable_whale_alert:
            logger.info("巨鲸提醒未启用，跳过监听")
            return
        
        self.listening = True
        logger.info("开始监听CoinGlass巨鲸提醒...")
        
        while self.listening:
            try:
                # 获取巨鲸提醒
                alerts = await self._get_whale_alerts()
                
                for alert in alerts:
                    # 检查是否已处理过（防止重复）
                    alert_id = self._get_alert_id(alert)
                    if alert_id in self.last_alert_ids:
                        continue
                    
                    # 检查持仓价值是否达到最小阈值
                    position_value = alert.get('position_value_usd', 0)
                    if position_value < self.min_position_value:
                        continue
                    
                    # 转换为Message对象
                    message = self._parse_whale_alert(alert)
                    if message:
                        # 标记为已处理
                        self.last_alert_ids.add(alert_id)
                        
                        # 限制历史记录大小
                        if len(self.last_alert_ids) > self.max_history_size:
                            # 清理旧的ID（简单策略：清空一半）
                            self.last_alert_ids = set(list(self.last_alert_ids)[self.max_history_size // 2:])
                        
                        # 触发回调
                        await callback(message)
                        
                        logger.info(f"✅ 处理巨鲸提醒: {message.content[:100]}...")
                
                # 等待下次轮询
                await asyncio.sleep(self.polling_interval)
                
            except Exception as e:
                logger.error(f"监听巨鲸提醒失败: {e}")
                import traceback
                logger.error(traceback.format_exc())
                await asyncio.sleep(self.polling_interval)
    
    async def _get_whale_alerts(self) -> List[Dict[str, Any]]:
        """获取巨鲸提醒数据"""
        try:
            url = f'{self.api_base_url}/api/hyperliquid/whale-alert'
            headers = self._build_headers()
            
            async with self.session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=30)) as response:
                if response.status == 200:
                    data = await response.json()
                    if data.get('code') == '0':
                        alerts = data.get('data', [])
                        logger.debug(f"获取到 {len(alerts)} 条巨鲸提醒")
                        return alerts
                    else:
                        logger.error(f"CoinGlass API返回错误: {data.get('msg', 'Unknown error')}")
                        return []
                else:
                    logger.error(f"获取巨鲸提醒失败: {response.status}")
                    text = await response.text()
                    logger.error(f"响应内容: {text}")
                    return []
                    
        except Exception as e:
            logger.error(f"获取巨鲸提醒异常: {e}")
            return []
    
    def _get_alert_id(self, alert: Dict[str, Any]) -> str:
        """生成提醒的唯一ID"""
        # 使用用户地址+币种+时间戳+操作类型作为唯一标识
        user = alert.get('user', '')
        symbol = alert.get('symbol', '')
        create_time = alert.get('create_time', 0)
        action = alert.get('position_action', 0)
        return f"{user}_{symbol}_{create_time}_{action}"
    
    def _parse_whale_alert(self, alert: Dict[str, Any]) -> Optional[Message]:
        """解析巨鲸提醒为Message对象"""
        try:
            user = alert.get('user', '')
            symbol = alert.get('symbol', '')
            position_size = alert.get('position_size', 0)
            entry_price = alert.get('entry_price', 0)
            liq_price = alert.get('liq_price', 0)
            position_value_usd = alert.get('position_value_usd', 0)
            position_action = alert.get('position_action', 0)  # 1: 开仓，2: 平仓
            create_time = alert.get('create_time', 0)
            
            # 转换操作类型
            action_text = '开仓' if position_action == 1 else '平仓' if position_action == 2 else '未知'
            direction_text = '多头' if position_size > 0 else '空头' if position_size < 0 else '未知'
            
            # 格式化消息内容
            content = f"🐋 巨鲸提醒 - Hyperliquid\n"
            content += f"币种: {symbol}\n"
            content += f"操作: {action_text} {direction_text}\n"
            content += f"持仓: {abs(position_size):,.2f} {symbol}\n"
            content += f"开仓价: ${entry_price:,.2f}\n"
            content += f"强平价: ${liq_price:,.2f}\n"
            content += f"持仓价值: ${position_value_usd:,.2f}\n"
            content += f"用户地址: {user[:10]}...{user[-6:]}"
            
            # 转换为时间戳
            if create_time:
                try:
                    timestamp = datetime.fromtimestamp(create_time / 1000)  # 毫秒转秒
                except:
                    timestamp = datetime.now()
            else:
                timestamp = datetime.now()
            
            message = Message(
                content=content,
                message_type=MessageType.TEXT,
                timestamp=timestamp,
                source_platform=PlatformType.COINGLASS,
                source_chat_id='hyperliquid',  # 标识来源平台
                source_user_id=user,
                source_username=None,
                message_id=self._get_alert_id(alert),
                extra_data=alert  # 保存原始数据
            )
            
            return message
            
        except Exception as e:
            logger.error(f"解析巨鲸提醒失败: {e}")
            logger.error(f"原始数据: {alert}")
            return None
    
    async def get_chat_info(self, chat_id: str) -> Optional[Dict[str, Any]]:
        """获取信息（CoinGlass不涉及群聊）"""
        return {
            'id': 'hyperliquid',
            'name': 'Hyperliquid 巨鲸提醒',
            'description': 'CoinGlass提供的Hyperliquid平台巨鲸交易提醒',
            'extra_data': {}
        }

