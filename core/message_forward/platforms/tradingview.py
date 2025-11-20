"""
TradingView消息平台实现
支持接收TradingView Webhook信号并转发

TradingView Alert Webhook格式:
{
    "symbol": "BTCUSDT",
    "action": "buy" | "sell" | "close",
    "price": 50000.0,
    "time": "2025-11-03 12:00:00",
    "message": "ASR信号：买入",
    "strategy": "ASR",
    "interval": "1h"
}
"""

from typing import Callable, Dict, List, Optional, Any
import asyncio
import aiohttp
import json
import hmac
import hashlib
from datetime import datetime

from ..base import MessagePlatform
from ..models import Message, MessageType, PlatformType
from utils.logger import get_logger

logger = get_logger(__name__)


class TradingViewPlatform(MessagePlatform):
    """TradingView消息平台（Webhook接收）"""
    
    def __init__(self, config: Dict[str, Any]):
        super().__init__(PlatformType.TRADINGVIEW, config)
        
        # Webhook配置
        self.use_webhook = config.get('use_webhook', True)  # 是否使用webhook接收方式
        self.webhook_port = config.get('webhook_port', 8080)  # Webhook监听端口（已弃用，不再使用独立服务器）
        self.webhook_path = config.get('webhook_path', '/tradingview/webhook')  # Webhook接收路径
        self.secret_key = config.get('secret_key', '')  # Webhook签名密钥（可选，用于验证）
        
        # 如果配置的端口是 80 或 443，记录警告（这些端口被 Nginx 占用）
        if self.webhook_port in [80, 443]:
            logger.warning(f"⚠️ 配置的端口 {self.webhook_port} 已被 Nginx 占用")
            logger.warning("   TradingView Webhook 将通过 Flask API 端点接收: /webhook/tradingview")
            logger.warning("   请在 TradingView Alert 中配置: https://your-domain/webhook/tradingview")
        
        # 过滤配置
        self.strategy_filter = config.get('strategy_filter', [])  # 策略过滤器（例如：['ASR']，留空表示接收所有）
        self.symbol_filter = config.get('symbol_filter', [])  # 交易对过滤器（例如：['BTCUSDT']，留空表示接收所有）
        
        # 状态
        self.session = None
        self.listening = False
        self.webhook_server = None
        
        # 调试：消息历史记录
        self.message_history: List[Dict[str, Any]] = []  # 保存收到的所有消息（用于调试）
        self.max_history_size = 1000  # 最大保存数量
        
        logger.info("TradingView平台初始化")
    
    async def connect(self) -> bool:
        """连接到TradingView（使用Flask API端点，不启动独立服务器）"""
        try:
            if self.use_webhook:
                # TradingView Webhook 通过 Flask API 的 /webhook/tradingview 端点接收
                # 不需要启动独立的 Webhook 服务器，避免端口冲突
                # Flask API 已经通过 Nginx 代理对外提供服务
                logger.info("TradingView Webhook 使用 Flask API 端点接收消息")
                logger.info(f"   Webhook URL: https://your-domain/webhook/tradingview")
                logger.info(f"   或: http://your-domain/webhook/tradingview (如果使用HTTP)")
                logger.info("   请在 TradingView Alert 中配置此 URL")
                
                self.connected = True
                return True
            else:
                logger.warning("TradingView仅支持Webhook方式")
                return False
                
        except Exception as e:
            logger.error(f"TradingView连接失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
            self.connected = False
            return False
    
    async def _connect_webhook_legacy(self) -> bool:
        """通过Webhook方式连接（启动独立HTTP服务器接收消息）- 已弃用，保留用于兼容"""
        # 注意：此方法已弃用，因为会与 Nginx 端口冲突
        # 现在使用 Flask API 的 /webhook/tradingview 端点
        # 如果配置的端口是 80 或 443，直接拒绝启动
        if self.webhook_port in [80, 443]:
            logger.error(f"❌ 不能使用端口 {self.webhook_port}，该端口已被 Nginx 占用")
            logger.error("   请使用 Flask API 端点: https://your-domain/webhook/tradingview")
            logger.error("   或配置非 80/443 的端口（如 8080），并通过 Nginx 代理")
            return False
        
        try:
            from aiohttp import web
            import threading
            import socket
            
            logger.info("启动TradingView Webhook接收服务器...")
            
            # 创建aiohttp应用
            app = web.Application()
            
            # 定义webhook处理函数
            async def webhook_handler(request):
                """处理TradingView发送的webhook请求"""
                try:
                    # 获取请求头信息（用于调试）
                    headers = dict(request.headers)
                    
                    # 获取请求数据
                    if request.content_type == 'application/json':
                        data = await request.json()
                    else:
                        # 尝试解析表单数据或文本
                        try:
                            post_data = await request.post()
                            data = dict(post_data)
                        except:
                            text = await request.text()
                            try:
                                data = json.loads(text)
                            except:
                                data = {'raw': text}
                    
                    # 验证签名（如果配置了secret_key）
                    if self.secret_key:
                        signature = headers.get('X-Signature', '')
                        if signature and not self._verify_signature(json.dumps(data, sort_keys=True), signature):
                            logger.warning("TradingView Webhook签名验证失败")
                            return web.json_response({
                                'status': 'error',
                                'message': 'Invalid signature'
                            }, status=401)
                    
                    # 记录原始请求信息（用于调试）
                    request_info = {
                        'timestamp': datetime.now().isoformat(),
                        'method': request.method,
                        'path': str(request.path),
                        'query': dict(request.query),
                        'headers': {k: v for k, v in headers.items() if k.lower() not in ['authorization', 'cookie']},
                        'content_type': request.content_type,
                        'data': data,
                    }
                    
                    # 保存到历史记录
                    self.message_history.append(request_info)
                    if len(self.message_history) > self.max_history_size:
                        self.message_history.pop(0)
                    
                    logger.info(f"📨 收到TradingView webhook消息")
                    logger.info(f"   Path: {request.path}")
                    logger.info(f"   Content-Type: {request.content_type}")
                    logger.info(f"   Data: {json.dumps(data, ensure_ascii=False, indent=2)}")
                    
                    # 解析消息（支持多种TradingView格式）
                    message = self._parse_webhook_message(data)
                    if message:
                        logger.info(f"✅ 解析消息成功: 策略={message.source_username}, 交易对={message.source_chat_id}, 动作={message.content[:50]}...")
                        
                        # 检查过滤条件
                        if self._should_forward(message, data):
                            # 触发消息处理器
                            for handler in self.message_handlers:
                                try:
                                    if asyncio.iscoroutinefunction(handler):
                                        await handler(message)
                                    else:
                                        handler(message)
                                except Exception as e:
                                    logger.error(f"消息处理器执行失败: {e}")
                        else:
                            logger.debug(f"消息被过滤器过滤: {message.content[:50]}...")
                    else:
                        logger.warning(f"⚠️  无法解析消息，原始数据: {data}")
                    
                    # 返回成功响应
                    return web.json_response({
                        'status': 'ok',
                        'message': 'received',
                        'parsed': message is not None,
                        'timestamp': datetime.now().isoformat()
                    })
                    
                except Exception as e:
                    logger.error(f"处理webhook请求失败: {e}")
                    import traceback
                    logger.error(traceback.format_exc())
                    return web.json_response({
                        'status': 'error',
                        'message': str(e),
                        'timestamp': datetime.now().isoformat()
                    }, status=500)
            
            # 定义调试接口：查看收到的消息历史
            async def history_handler(request):
                """查看webhook消息历史（调试用）"""
                try:
                    limit = int(request.query.get('limit', 50))
                    limit = min(limit, 500)
                    
                    history = self.message_history[-limit:]
                    
                    return web.json_response({
                        'status': 'ok',
                        'total': len(self.message_history),
                        'returned': len(history),
                        'history': history
                    })
                except Exception as e:
                    return web.json_response({'status': 'error', 'message': str(e)}, status=500)
            
            # 注册路由
            app.router.add_post(self.webhook_path, webhook_handler)
            app.router.add_get(self.webhook_path + '/status', lambda r: web.json_response({
                'status': 'running',
                'timestamp': datetime.now().isoformat()
            }))
            
            # 调试接口：查看消息历史
            app.router.add_get(self.webhook_path + '/history', history_handler)
            
            # 在后台线程中运行服务器
            def run_server():
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                runner = web.AppRunner(app)
                loop.run_until_complete(runner.setup())
                site = web.TCPSite(runner, '0.0.0.0', self.webhook_port)
                loop.run_until_complete(site.start())
                logger.info(f"✅ TradingView Webhook服务器已启动: http://0.0.0.0:{self.webhook_port}{self.webhook_path}")
                try:
                    loop.run_forever()
                except KeyboardInterrupt:
                    pass
                finally:
                    loop.run_until_complete(runner.cleanup())
                    loop.close()
            
            server_thread = threading.Thread(target=run_server, daemon=True, name="TradingViewWebhookServer")
            server_thread.start()
            
            # 等待服务器启动（使用 time.sleep 而不是 asyncio.sleep，避免事件循环冲突）
            import time
            time.sleep(1)
            
            self.connected = True
            logger.info(f"✅ TradingView Webhook服务器已启动，等待接收消息")
            logger.info(f"   📍 Webhook接收地址: http://your-server-ip:{self.webhook_port}{self.webhook_path}")
            logger.info(f"   🔍 状态检查: http://your-server-ip:{self.webhook_port}{self.webhook_path}/status")
            logger.info(f"   📜 消息历史: http://your-server-ip:{self.webhook_port}{self.webhook_path}/history?limit=50")
            logger.info(f"   请在TradingView Alert中配置此URL作为webhook地址")
            
            return True
            
        except Exception as e:
            logger.error(f"Webhook服务器启动失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return False
    
    def _verify_signature(self, payload: str, signature: str) -> bool:
        """验证Webhook签名"""
        if not self.secret_key:
            return True  # 未配置密钥，跳过验证
        
        try:
            # TradingView可能使用HMAC SHA256签名
            expected_signature = hmac.new(
                self.secret_key.encode('utf-8'),
                payload.encode('utf-8'),
                hashlib.sha256
            ).hexdigest()
            
            return hmac.compare_digest(expected_signature, signature)
        except Exception as e:
            logger.error(f"签名验证失败: {e}")
            return False
    
    async def disconnect(self) -> bool:
        """断开连接"""
        try:
            self.listening = False
            
            if self.session:
                await self.session.close()
                self.session = None
            
            self.connected = False
            logger.info("TradingView连接已断开")
            return True
            
        except Exception as e:
            logger.error(f"断开连接失败: {e}")
            return False
    
    async def send_message(self, chat_id: str, message: Message) -> bool:
        """发送消息到TradingView（TradingView主要用于接收，不支持发送）"""
        logger.warning("TradingView平台主要用于接收信号，不支持发送消息")
        return False
    
    async def listen(self, callback: Callable[[Message], None]) -> None:
        """监听TradingView信号（Webhook方式：消息通过HTTP POST接收，已经在webhook_handler中处理）"""
        if not self.connected:
            logger.error("TradingView未连接，无法监听")
            return
        
        self.listening = True
        logger.info("TradingView Webhook监听已启动，等待TradingView推送信号...")
        logger.info(f"   请在TradingView Alert中配置webhook地址: http://your-server-ip:{self.webhook_port}{self.webhook_path}")
        while self.listening:
            # 使用 loop.call_later 而不是 asyncio.sleep，避免 nest_asyncio 影响
            current_loop = asyncio.get_running_loop()
            future = current_loop.create_future()
            def set_result():
                if not future.done():
                    future.set_result(None)
            current_loop.call_later(1, set_result)
            await future
    
    async def start_listening(self, monitored_chat_ids: Optional[List[str]] = None):
        """
        开始监听消息（兼容接口，TradingView通过Webhook接收，不需要主动监听）
        
        Args:
            monitored_chat_ids: 要监听的群组/频道ID列表（TradingView不需要此参数，但保留以兼容接口）
        """
        # TradingView平台通过Webhook被动接收消息，不需要主动监听
        # 只需要确保连接已建立（Webhook服务器已启动）
        if not self.connected:
            logger.warning("TradingView未连接，尝试连接...")
            await self.connect()
        
        if self.connected:
            self.listening = True
            logger.info("✅ TradingView Webhook监听已就绪，等待接收消息...")
            logger.info(f"   Webhook地址: http://your-server-ip:{self.webhook_port}{self.webhook_path}")
            # 保持运行状态
            while self.listening:
                # 使用 loop.call_later 而不是 asyncio.sleep，避免 nest_asyncio 影响
                current_loop = asyncio.get_running_loop()
                future = current_loop.create_future()
                def set_result():
                    if not future.done():
                        future.set_result(None)
                current_loop.call_later(10, set_result)
                await future
        else:
            logger.error("❌ TradingView连接失败，无法启动监听")
    
    def _parse_webhook_message(self, data: Dict[str, Any]) -> Optional[Message]:
        """
        解析TradingView Webhook消息
        
        支持多种格式：
        1. 标准格式: {"symbol": "BTCUSDT", "action": "buy", "price": 50000, ...}
        2. Alert消息格式: {"message": "ASR信号：买入 BTCUSDT @ 50000", ...}
        3. 自定义格式: 根据实际配置调整
        """
        try:
            # 提取基本信息
            symbol = data.get('symbol') or data.get('ticker') or data.get('pair', '')
            action = data.get('action') or data.get('side') or data.get('signal', '')
            price = data.get('price') or data.get('close') or data.get('close_price', '')
            strategy = data.get('strategy') or data.get('indicator') or data.get('study', 'ASR')
            message_text = data.get('message') or data.get('text') or ''
            time_str = data.get('time') or data.get('timestamp') or data.get('alert_time', '')
            
            # 如果message_text为空，尝试构建
            if not message_text:
                parts = []
                if strategy:
                    parts.append(f"{strategy}信号")
                if action:
                    action_cn = {'buy': '买入', 'sell': '卖出', 'close': '平仓', 'long': '做多', 'short': '做空'}.get(action.lower(), action)
                    parts.append(action_cn)
                if symbol:
                    parts.append(symbol)
                if price:
                    parts.append(f"@ {price}")
                
                message_text = "：".join(parts) if parts else "TradingView信号"
            else:
                # 如果已有消息，添加策略信息
                if strategy and strategy not in message_text:
                    message_text = f"[{strategy}] {message_text}"
            
            # 格式化消息内容
            content = f"📊 TradingView信号提醒\n"
            content += f"策略: {strategy}\n"
            content += f"交易对: {symbol}\n"
            if action:
                action_cn = {'buy': '🟢 买入', 'sell': '🔴 卖出', 'close': '⚪ 平仓', 'long': '🟢 做多', 'short': '🔴 做空'}.get(action.lower(), action)
                content += f"动作: {action_cn}\n"
            if price:
                content += f"价格: ${price}\n"
            if message_text and message_text not in content:
                content += f"备注: {message_text}\n"
            
            # 解析时间戳
            if time_str:
                try:
                    # 尝试多种时间格式
                    if isinstance(time_str, (int, float)):
                        timestamp = datetime.fromtimestamp(time_str)
                    elif isinstance(time_str, str):
                        # 尝试解析ISO格式或常见格式
                        for fmt in ['%Y-%m-%d %H:%M:%S', '%Y-%m-%dT%H:%M:%S', '%Y-%m-%d %H:%M:%S.%f']:
                            try:
                                timestamp = datetime.strptime(time_str, fmt)
                                break
                            except:
                                continue
                        else:
                            timestamp = datetime.now()
                    else:
                        timestamp = datetime.now()
                except:
                    timestamp = datetime.now()
            else:
                timestamp = datetime.now()
            
            message = Message(
                content=content.strip(),
                message_type=MessageType.TEXT,
                timestamp=timestamp,
                source_platform=PlatformType.TRADINGVIEW,
                source_chat_id=symbol or 'unknown',  # 使用交易对作为chat_id
                source_user_id=strategy or 'ASR',  # 使用策略名称作为user_id
                source_username=strategy or 'ASR',  # 使用策略名称作为username
                message_id=f"{strategy}_{symbol}_{timestamp.timestamp()}",
                extra_data=data  # 保存原始数据
            )
            
            return message
            
        except Exception as e:
            logger.error(f"解析TradingView消息失败: {e}")
            logger.error(f"原始数据: {data}")
            import traceback
            logger.debug(traceback.format_exc())
            return None
    
    def _should_forward(self, message: Message, raw_data: Dict[str, Any]) -> bool:
        """判断是否应该转发此消息"""
        # 策略过滤
        if self.strategy_filter:
            # 优先使用 type_ 字段（如 "ASR-VC"、"ASR-TP"、"ASR-HD"）
            # 如果没有 type_，再尝试 strategy、indicator 等字段
            strategy = (
                raw_data.get('type_') or  # 优先使用 type_ 字段
                raw_data.get('strategy') or 
                raw_data.get('indicator') or 
                message.source_username
            )
            
            if strategy:
                # 完整匹配（精确匹配）
                # 例如：type_="ASR-VC" 必须配置 "ASR-VC" 才能匹配
                if strategy not in self.strategy_filter:
                    logger.debug(f"策略过滤器不匹配: 策略 '{strategy}' 不在过滤器列表 {self.strategy_filter} 中")
                    return False
        
        # 交易对过滤
        if self.symbol_filter:
            symbol = raw_data.get('symbol') or raw_data.get('ticker') or message.source_chat_id
            if symbol and symbol not in self.symbol_filter:
                return False
        
        return True
    
    async def get_chat_info(self, chat_id: str) -> Optional[Dict[str, Any]]:
        """获取信息（TradingView不涉及群聊）"""
        return {
            'id': chat_id,
            'name': f'TradingView信号 - {chat_id}',
            'description': f'TradingView交易对: {chat_id}',
            'extra_data': {}
        }

