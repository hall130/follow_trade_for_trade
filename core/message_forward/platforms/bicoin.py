"""
币coin消息平台实现
支持获取币coin群内消息并转发

注意：币coin可能有多种实现方式：
1. 官方API（如果有）
2. 网页爬虫
3. WebSocket连接
4. 模拟客户端（需要逆向分析）
"""

from typing import Callable, Dict, List, Optional, Any
import asyncio
import aiohttp
import json
from datetime import datetime

from ..base import MessagePlatform
from ..models import Message, MessageType, PlatformType
from utils.logger import get_logger

logger = get_logger(__name__)


class BicoinPlatform(MessagePlatform):
    """币coin消息平台"""
    
    def __init__(self, config: Dict[str, Any]):
        super().__init__(PlatformType.BICOIN, config)
        
        # 配置参数
        self.api_base_url = config.get('api_base_url', 'https://api.bicoin.com')  # API基础地址
        self.api_token = config.get('api_token', '')  # API Token
        self.api_secret = config.get('api_secret', '')  # API Secret
        self.group_ids = config.get('group_ids', [])  # 要监听的群ID列表
        self.polling_interval = config.get('polling_interval', 5)  # 轮询间隔（秒）
        
        # WebSocket配置
        self.use_websocket = config.get('use_websocket', False)  # 是否使用WebSocket
        self.ws_url = config.get('ws_url', 'wss://ws.bicoin.com')  # WebSocket地址
        
        # 爬虫配置（如果API不可用）
        self.use_crawler = config.get('use_crawler', False)  # 是否使用爬虫
        self.cookies = config.get('cookies', {})  # 登录cookies
        self.headers = config.get('headers', {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
        
        # Webhook接收方式（推荐）- 币coin客户端发送webhook到这个服务器
        self.use_webhook = config.get('use_webhook', True)  # 是否使用webhook接收方式
        self.webhook_port = config.get('webhook_port', 8080)  # Webhook监听端口
        self.webhook_path = config.get('webhook_path', '/bicoin/webhook')  # Webhook接收路径
        
        # 状态
        self.session = None
        self.ws = None
        self.listening = False
        self.last_message_id = {}  # 记录每个群最后的消息ID
        self.webhook_server = None  # Webhook HTTP服务器
        
        # 调试：消息历史记录
        self.message_history: List[Dict[str, Any]] = []  # 保存收到的所有消息（用于调试）
        self.max_history_size = 1000  # 最大保存数量
        
        logger.info("币coin平台初始化")
    
    async def connect(self) -> bool:
        """
        连接到币coin
        
        注意：由于币coin可能不再支持webhook和API，推荐使用以下方式：
        1. 通过Telegram/微信等中间层转发（推荐）
           - 在"平台管理"中添加Telegram平台，监听币coin的Telegram群组
           - 或使用微信机器人转发币coin消息
        2. WebSocket方式（如果币coin还支持）
        3. 爬虫方式（需要登录cookie）
        """
        try:
            logger.info("正在连接币coin...")
            logger.warning("⚠️  注意：币coin可能不再支持webhook和API方式")
            logger.info("💡 推荐方案：通过Telegram或微信等中间层转发币coin消息")
            
            # 尝试连接方式（按优先级）
            connection_methods = []
            
            # 1. WebSocket方式（如果配置）
            if self.use_websocket:
                connection_methods.append(('WebSocket', self._connect_websocket))
            
            # 2. 爬虫方式（如果配置）
            if self.use_crawler:
                connection_methods.append(('爬虫', self._connect_crawler))
            
            # 3. Webhook方式（虽然可能不可用，但保留用于测试）
            if self.use_webhook:
                connection_methods.append(('Webhook', self._connect_webhook))
            
            # 4. API方式（最后尝试）
            connection_methods.append(('API', self._connect_api))
            
            # 依次尝试各种连接方式
            for method_name, connect_func in connection_methods:
                try:
                    logger.info(f"尝试使用 {method_name} 方式连接...")
                    if await connect_func():
                        logger.info(f"✅ 使用 {method_name} 方式连接成功")
                        return True
                    else:
                        logger.warning(f"⚠️  {method_name} 方式连接失败，尝试下一种方式")
                except Exception as e:
                    logger.warning(f"⚠️  {method_name} 方式连接异常: {e}，尝试下一种方式")
                    continue
            
            # 所有方式都失败
            logger.error("❌ 所有连接方式都失败")
            logger.info("""
💡 推荐解决方案：

方案1：通过Telegram转发（推荐）
  1. 在"平台管理"中添加Telegram平台
  2. 监听币coin的Telegram群组
  3. 配置转发规则：Telegram -> 其他平台

方案2：通过微信机器人转发
  1. 使用微信机器人工具（如WxAuto）转发币coin消息
  2. 在"平台管理"中添加微信平台
  3. 监听微信机器人接收到的币coin消息

方案3：使用爬虫方式
  1. 获取币coin登录cookie
  2. 配置 use_crawler: true
  3. 配置 cookies: {...}
            """)
            
            self.connected = False
            return False
                
        except Exception as e:
            logger.error(f"币coin连接失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
            self.connected = False
            return False
    
    async def _connect_webhook(self) -> bool:
        """通过Webhook方式连接（启动HTTP服务器接收消息）"""
        try:
            from aiohttp import web
            import threading
            
            logger.info("启动币coin Webhook接收服务器...")
            
            # 创建aiohttp应用
            app = web.Application()
            
            # 定义webhook处理函数
            async def webhook_handler(request):
                """处理币coin发送的webhook请求"""
                try:
                    # 获取请求头信息（用于调试）
                    headers = dict(request.headers)
                    
                    # 获取请求数据
                    if request.content_type == 'application/json':
                        data = await request.json()
                    else:
                        post_data = await request.post()
                        data = dict(post_data)
                    
                    # 记录原始请求信息（用于调试）
                    request_info = {
                        'timestamp': datetime.now().isoformat(),
                        'method': request.method,
                        'path': str(request.path),
                        'query': dict(request.query),
                        'headers': {k: v for k, v in headers.items() if k.lower() not in ['authorization', 'cookie']},  # 排除敏感信息
                        'content_type': request.content_type,
                        'data': data,  # 原始数据
                        'raw_body': None  # 可以保存原始body（如果需要）
                    }
                    
                    # 保存到历史记录
                    self.message_history.append(request_info)
                    if len(self.message_history) > self.max_history_size:
                        self.message_history.pop(0)  # 移除最旧的记录
                    
                    logger.info(f"📨 收到币coin webhook消息")
                    logger.info(f"   Path: {request.path}")
                    logger.info(f"   Content-Type: {request.content_type}")
                    logger.info(f"   Data: {json.dumps(data, ensure_ascii=False, indent=2)}")
                    logger.info(f"   Headers: {json.dumps(request_info['headers'], ensure_ascii=False)}")
                    
                    # 解析消息（根据币coin的实际格式调整）
                    message = self._parse_webhook_message(data)
                    if message:
                        logger.info(f"✅ 解析消息成功: 群={message.source_chat_id}, 用户={message.source_username}, 内容={message.content[:100]}...")
                        
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
                    limit = min(limit, 500)  # 最多返回500条
                    
                    history = self.message_history[-limit:]
                    
                    return web.json_response({
                        'status': 'ok',
                        'total': len(self.message_history),
                        'returned': len(history),
                        'history': history
                    })
                except Exception as e:
                    return web.json_response({'status': 'error', 'message': str(e)}, status=500)
            
            # 定义测试接口：模拟币coin推送消息（用于测试）
            async def test_handler(request):
                """测试接口：模拟币coin推送消息"""
                try:
                    if request.method == 'GET':
                        # 返回测试表单
                        html = """
                        <html>
                        <head><title>币coin Webhook测试</title></head>
                        <body>
                            <h2>币coin Webhook测试工具</h2>
                            <form method="POST">
                                <p>
                                    <label>消息格式:</label><br>
                                    <select name="format" id="format">
                                        <option value="wechat">微信机器人格式</option>
                                        <option value="trade">交易数据格式</option>
                                        <option value="custom">自定义JSON</option>
                                    </select>
                                </p>
                                <p>
                                    <label>消息内容 (JSON):</label><br>
                                    <textarea name="data" id="data" rows="10" cols="60">{
  "wxid": "wxid_test",
  "msg": "测试消息内容",
  "room": "测试群"
}</textarea>
                                </p>
                                <button type="button" onclick="loadTemplate()">加载模板</button>
                                <button type="submit">发送测试</button>
                            </form>
                            <script>
                            function loadTemplate() {
                                var format = document.getElementById('format').value;
                                var templates = {
                                    'wechat': '{"wxid": "wxid_test", "msg": "测试消息内容", "room": "测试群"}',
                                    'trade': '{"data": {"pair": "BTC/USDT", "price": 50000, "side": "buy", "amount": 0.1}, "group_id": "test_group"}',
                                    'custom': '{"content": "自定义消息", "group_id": "test", "user": "test_user"}'
                                };
                                document.getElementById('data').value = templates[format] || templates['wechat'];
                            }
                            </script>
                        </body>
                        </html>
                        """
                        return web.Response(text=html, content_type='text/html')
                    else:
                        # POST请求：处理测试消息
                        post_data = await request.post()
                        data_str = post_data.get('data', '{}')
                        
                        try:
                            data = json.loads(data_str)
                        except:
                            return web.json_response({'status': 'error', 'message': '无效的JSON格式'}, status=400)
                        
                        # 直接调用webhook_handler处理
                        from aiohttp.web import Request
                        # 创建一个模拟请求对象
                        test_request = type('MockRequest', (), {
                            'method': 'POST',
                            'path': self.webhook_path,
                            'content_type': 'application/json',
                            'headers': {},
                            'query': {}
                        })()
                        test_request.json = lambda: data
                        test_request.post = lambda: {}
                        
                        # 解析消息
                        message = self._parse_webhook_message(data)
                        
                        return web.json_response({
                            'status': 'ok',
                            'message': '测试消息已处理',
                            'original_data': data,
                            'parsed_message': message.to_dict() if message else None,
                            'parsed': message is not None
                        })
                except Exception as e:
                    return web.json_response({'status': 'error', 'message': str(e)}, status=500)
            
            # 注册路由
            app.router.add_post(self.webhook_path, webhook_handler)
            app.router.add_get(self.webhook_path + '/status', lambda r: web.json_response({'status': 'running', 'timestamp': datetime.now().isoformat()}))
            
            # 调试接口：查看消息历史
            app.router.add_get(self.webhook_path + '/history', history_handler)
            
            # 测试接口：模拟币coin推送消息
            app.router.add_get(self.webhook_path + '/test', test_handler)
            app.router.add_post(self.webhook_path + '/test', test_handler)
            
            # 在后台线程中运行服务器
            def run_server():
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                runner = web.AppRunner(app)
                loop.run_until_complete(runner.setup())
                site = web.TCPSite(runner, '0.0.0.0', self.webhook_port)
                loop.run_until_complete(site.start())
                logger.info(f"✅ 币coin Webhook服务器已启动: http://0.0.0.0:{self.webhook_port}{self.webhook_path}")
                try:
                    loop.run_forever()
                except KeyboardInterrupt:
                    pass
                finally:
                    loop.run_until_complete(runner.cleanup())
                    loop.close()
            
            server_thread = threading.Thread(target=run_server, daemon=True)
            server_thread.start()
            
            # 等待服务器启动
            await asyncio.sleep(1)
            
            self.connected = True
            logger.info(f"✅ 币coin Webhook服务器已启动，等待接收消息")
            logger.info(f"   📍 Webhook接收地址: http://your-server-ip:{self.webhook_port}{self.webhook_path}")
            logger.info(f"   🔍 状态检查: http://your-server-ip:{self.webhook_port}{self.webhook_path}/status")
            logger.info(f"   📜 消息历史: http://your-server-ip:{self.webhook_port}{self.webhook_path}/history?limit=50")
            logger.info(f"   🧪 测试工具: http://your-server-ip:{self.webhook_port}{self.webhook_path}/test")
            logger.info(f"   请在币coin客户端配置此URL作为webhook地址")
            
            return True
            
        except Exception as e:
            logger.error(f"Webhook服务器启动失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return False
    
    async def _connect_api(self) -> bool:
        """通过API连接"""
        try:
            # 创建HTTP会话
            self.session = aiohttp.ClientSession()
            
            # 测试连接（调用认证接口）
            if self.api_token and self.api_secret:
                # 这里需要根据币coin的实际API文档实现认证
                # 示例：
                headers = {
                    'Authorization': f'Bearer {self.api_token}',
                    'Content-Type': 'application/json'
                }
                async with self.session.get(
                    f'{self.api_base_url}/api/v1/auth/verify',
                    headers=headers
                ) as response:
                    if response.status == 200:
                        self.connected = True
                        logger.info("✅ 币coin API连接成功")
                        return True
                    else:
                        logger.error(f"币coin API认证失败: {response.status}")
                        return False
            else:
                # 如果没有配置API token，使用匿名方式
                logger.warning("⚠️  未配置API Token，使用匿名模式")
                self.connected = True
                return True
                
        except Exception as e:
            logger.error(f"API连接失败: {e}")
            return False
    
    async def _connect_websocket(self) -> bool:
        """通过WebSocket连接"""
        try:
            logger.info("正在连接币coin WebSocket...")
            
            # 构建WebSocket URL（需要根据实际协议调整）
            ws_url = f"{self.ws_url}?token={self.api_token}" if self.api_token else self.ws_url
            
            self.session = aiohttp.ClientSession()
            self.ws = await self.session.ws_connect(ws_url)
            
            self.connected = True
            logger.info("✅ 币coin WebSocket连接成功")
            
            # 订阅群消息
            if self.group_ids:
                subscribe_msg = {
                    'action': 'subscribe',
                    'groups': self.group_ids
                }
                await self.ws.send_json(subscribe_msg)
                logger.info(f"已订阅群: {self.group_ids}")
            
            return True
            
        except Exception as e:
            logger.error(f"WebSocket连接失败: {e}")
            return False
    
    async def _connect_crawler(self) -> bool:
        """通过爬虫方式连接"""
        try:
            logger.info("使用爬虫方式连接币coin...")
            
            self.session = aiohttp.ClientSession(
                cookies=self.cookies,
                headers=self.headers
            )
            
            # 测试是否可以访问页面
            test_url = self.config.get('crawler_url', 'https://www.bicoin.com')
            async with self.session.get(test_url) as response:
                if response.status == 200:
                    self.connected = True
                    logger.info("✅ 币coin爬虫连接成功")
                    return True
                else:
                    logger.error(f"无法访问币coin页面: {response.status}")
                    return False
                    
        except Exception as e:
            logger.error(f"爬虫连接失败: {e}")
            return False
    
    async def disconnect(self) -> bool:
        """断开连接"""
        try:
            if self.ws:
                await self.ws.close()
                self.ws = None
            
            if self.session:
                await self.session.close()
                self.session = None
            
            self.connected = False
            self.listening = False
            logger.info("币coin连接已断开")
            return True
            
        except Exception as e:
            logger.error(f"断开连接失败: {e}")
            return False
    
    async def send_message(self, chat_id: str, message: Message) -> bool:
        """发送消息到币coin群"""
        try:
            if not self.connected:
                logger.warning("币coin未连接，无法发送消息")
                return False
            
            # 构建消息内容
            content = message.content
            if message.formatted_content:
                content = message.formatted_content
            
            # 调用API发送消息
            if self.session and self.api_token:
                url = f'{self.api_base_url}/api/v1/groups/{chat_id}/messages'
                headers = {
                    'Authorization': f'Bearer {self.api_token}',
                    'Content-Type': 'application/json'
                }
                data = {
                    'content': content,
                    'type': message.message_type.value
                }
                
                async with self.session.post(url, headers=headers, json=data) as response:
                    if response.status == 200:
                        logger.info(f"✅ 消息已发送到币coin群: {chat_id}")
                        return True
                    else:
                        logger.error(f"发送消息失败: {response.status}")
                        return False
            
            logger.warning("无法发送消息：未配置API或连接")
            return False
            
        except Exception as e:
            logger.error(f"发送消息失败: {e}")
            return False
    
    async def listen(self, callback: Callable[[Message], None]) -> None:
        """监听币coin群消息"""
        if not self.connected:
            logger.error("币coin未连接，无法监听消息")
            return
        
        self.listening = True
        
        if self.use_webhook:
            # Webhook方式：消息通过HTTP POST接收，已经在webhook_handler中处理
            # 这里只需要保持监听状态，等待webhook请求
            logger.info("币coin Webhook监听已启动，等待币coin客户端推送消息...")
            logger.info(f"   请在币coin客户端配置webhook地址: http://your-server-ip:{self.webhook_port}{self.webhook_path}")
            while self.listening:
                await asyncio.sleep(1)
        elif self.use_websocket and self.ws:
            # WebSocket方式监听
            await self._listen_websocket(callback)
        elif self.use_crawler:
            # 爬虫方式监听
            await self._listen_crawler(callback)
        else:
            # API轮询方式监听
            await self._listen_api(callback)
    
    async def _listen_websocket(self, callback: Callable[[Message], None]) -> None:
        """WebSocket方式监听"""
        try:
            logger.info("开始WebSocket监听...")
            
            while self.listening and self.ws:
                try:
                    msg = await self.ws.receive()
                    
                    if msg.type == aiohttp.WSMsgType.TEXT:
                        data = json.loads(msg.data)
                        message = self._parse_websocket_message(data)
                        if message:
                            await callback(message)
                    elif msg.type == aiohttp.WSMsgType.ERROR:
                        logger.error(f"WebSocket错误: {self.ws.exception()}")
                        break
                    elif msg.type == aiohttp.WSMsgType.CLOSE:
                        logger.info("WebSocket连接已关闭")
                        break
                        
                except Exception as e:
                    logger.error(f"处理WebSocket消息失败: {e}")
                    await asyncio.sleep(1)
                    
        except Exception as e:
            logger.error(f"WebSocket监听失败: {e}")
        finally:
            self.listening = False
    
    async def _listen_api(self, callback: Callable[[Message], None]) -> None:
        """API轮询方式监听"""
        try:
            logger.info("开始API轮询监听...")
            
            while self.listening:
                for group_id in self.group_ids:
                    try:
                        # 调用API获取群消息
                        url = f'{self.api_base_url}/api/v1/groups/{group_id}/messages'
                        headers = {
                            'Authorization': f'Bearer {self.api_token}',
                        }
                        params = {
                            'since': self.last_message_id.get(group_id, 0),
                            'limit': 50
                        }
                        
                        async with self.session.get(url, headers=headers, params=params) as response:
                            if response.status == 200:
                                data = await response.json()
                                messages = data.get('messages', [])
                                
                                for msg_data in messages:
                                    message = self._parse_api_message(msg_data, group_id)
                                    if message:
                                        await callback(message)
                                        
                                        # 更新最后消息ID
                                        msg_id = msg_data.get('id')
                                        if msg_id:
                                            self.last_message_id[group_id] = msg_id
                                            
                    except Exception as e:
                        logger.error(f"获取群 {group_id} 消息失败: {e}")
                
                # 等待下次轮询
                await asyncio.sleep(self.polling_interval)
                
        except Exception as e:
            logger.error(f"API监听失败: {e}")
        finally:
            self.listening = False
    
    async def _listen_crawler(self, callback: Callable[[Message], None]) -> None:
        """
        爬虫方式监听
        
        需要配置：
        - cookies: 币coin登录后的cookie（从浏览器开发者工具获取）
        - crawler_url: 币coin群组页面URL
        - group_ids: 要监听的群ID列表
        
        获取cookie方法：
        1. 打开浏览器，登录币coin
        2. 打开开发者工具（F12）
        3. 在Network标签中找到币coin的请求
        4. 复制Cookie请求头的值
        """
        try:
            logger.info("开始爬虫监听...")
            logger.warning("⚠️  爬虫方式需要根据币coin的实际网页结构实现")
            logger.info("💡 提示：需要配置cookies和crawler_url")
            
            if not self.cookies:
                logger.error("❌ 未配置cookies，无法使用爬虫方式")
                logger.info("""
📝 配置方法：
1. 在浏览器中登录币coin
2. 打开开发者工具（F12）-> Network标签
3. 刷新页面，找到币coin的请求
4. 复制Cookie请求头的值
5. 在配置中添加：
   cookies: {
     "session_id": "your_session_id",
     "token": "your_token",
     ...
   }
                """)
                return
            
            while self.listening:
                try:
                    for group_id in self.group_ids:
                        # 构建群组消息页面URL
                        # 注意：需要根据币coin的实际URL结构调整
                        group_url = self.config.get('crawler_url', 'https://www.bicoin.com')
                        if '{group_id}' in group_url:
                            group_url = group_url.format(group_id=group_id)
                        else:
                            group_url = f"{group_url}/group/{group_id}/messages"
                        
                        try:
                            # 访问群组消息页面
                            async with self.session.get(group_url) as response:
                                if response.status == 200:
                                    html = await response.text()
                                    
                                    # 解析HTML获取消息
                                    # TODO: 根据币coin的实际HTML结构实现解析
                                    # 可以使用BeautifulSoup或正则表达式
                                    messages = self._parse_html_messages(html, group_id)
                                    
                                    for msg_data in messages:
                                        message = self._parse_crawler_message(msg_data, group_id)
                                        if message:
                                            # 检查是否是新消息（避免重复）
                                            msg_id = message.message_id
                                            if msg_id and msg_id not in self.last_message_id.values():
                                                await callback(message)
                                                self.last_message_id[group_id] = msg_id
                                else:
                                    logger.warning(f"访问群组 {group_id} 失败: {response.status}")
                                    
                        except Exception as e:
                            logger.error(f"获取群 {group_id} 消息失败: {e}")
                    
                    # 等待下次轮询
                    await asyncio.sleep(self.polling_interval)
                    
                except Exception as e:
                    logger.error(f"爬虫监听循环错误: {e}")
                    await asyncio.sleep(self.polling_interval)
                
        except Exception as e:
            logger.error(f"爬虫监听失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
        finally:
            self.listening = False
    
    def _parse_html_messages(self, html: str, group_id: str) -> List[Dict[str, Any]]:
        """
        解析HTML获取消息列表
        
        需要根据币coin的实际HTML结构实现
        可以使用BeautifulSoup或正则表达式
        """
        try:
            # 这里提供基础框架，需要根据实际HTML结构调整
            messages = []
            
            # 示例：使用正则表达式提取消息（需要根据实际结构调整）
            import re
            # 假设消息格式：<div class="message" data-id="123">...</div>
            message_pattern = r'<div[^>]*class="message"[^>]*data-id="(\d+)"[^>]*>(.*?)</div>'
            matches = re.finditer(message_pattern, html, re.DOTALL)
            
            for match in matches:
                msg_id = match.group(1)
                msg_html = match.group(2)
                
                # 提取消息内容（需要根据实际结构调整）
                content_match = re.search(r'<div[^>]*class="content"[^>]*>(.*?)</div>', msg_html, re.DOTALL)
                content = content_match.group(1) if content_match else ''
                # 清理HTML标签
                content = re.sub(r'<[^>]+>', '', content).strip()
                
                # 提取用户信息（需要根据实际结构调整）
                user_match = re.search(r'<div[^>]*class="user"[^>]*>(.*?)</div>', msg_html, re.DOTALL)
                username = re.sub(r'<[^>]+>', '', user_match.group(1)).strip() if user_match else ''
                
                messages.append({
                    'id': msg_id,
                    'content': content,
                    'username': username,
                    'group_id': group_id,
                    'timestamp': datetime.now().isoformat()
                })
            
            return messages
            
        except Exception as e:
            logger.error(f"解析HTML消息失败: {e}")
            return []
    
    def _parse_crawler_message(self, data: Dict[str, Any], group_id: str) -> Optional[Message]:
        """解析爬虫获取的消息"""
        try:
            message = Message(
                content=data.get('content', ''),
                message_type=MessageType.TEXT,
                timestamp=datetime.fromisoformat(data.get('timestamp', datetime.now().isoformat())) 
                         if isinstance(data.get('timestamp'), str) else datetime.now(),
                source_platform=PlatformType.BICOIN,
                source_chat_id=str(group_id),
                source_user_id=data.get('user_id', ''),
                source_username=data.get('username', ''),
                message_id=str(data.get('id', '')),
                extra_data=data
            )
            return message
            
        except Exception as e:
            logger.error(f"解析爬虫消息失败: {e}")
            return None
    
    def _parse_websocket_message(self, data: Dict[str, Any]) -> Optional[Message]:
        """解析WebSocket消息"""
        try:
            # 根据币coin的WebSocket消息格式解析
            # 示例格式：
            content = data.get('content', '')
            group_id = data.get('group_id', '')
            user_id = data.get('user_id', '')
            username = data.get('username', '')
            timestamp = data.get('timestamp', datetime.now().isoformat())
            
            message = Message(
                content=content,
                message_type=MessageType.TEXT,
                timestamp=datetime.fromisoformat(timestamp) if isinstance(timestamp, str) else datetime.now(),
                source_platform=PlatformType.BICOIN,
                source_chat_id=group_id,
                source_user_id=user_id,
                source_username=username,
                message_id=data.get('id'),
                extra_data=data
            )
            
            return message
            
        except Exception as e:
            logger.error(f"解析WebSocket消息失败: {e}")
            return None
    
    def _parse_api_message(self, data: Dict[str, Any], group_id: str) -> Optional[Message]:
        """解析API消息"""
        try:
            content = data.get('content', '')
            user_id = data.get('user_id', '')
            username = data.get('username', '')
            timestamp = data.get('created_at', datetime.now().isoformat())
            
            message = Message(
                content=content,
                message_type=MessageType.TEXT,
                timestamp=datetime.fromisoformat(timestamp) if isinstance(timestamp, str) else datetime.now(),
                source_platform=PlatformType.BICOIN,
                source_chat_id=group_id,
                source_user_id=user_id,
                source_username=username,
                message_id=str(data.get('id', '')),
                extra_data=data
            )
            
            return message
            
        except Exception as e:
            logger.error(f"解析API消息失败: {e}")
            return None
    
    def _parse_webhook_message(self, data: Dict[str, Any]) -> Optional[Message]:
        """
        解析Webhook消息
        
        支持多种消息格式：
        1. 微信机器人格式: {"wxid": "...", "msg": "...", "room": "..."}
        2. 交易数据格式: {"data": {...}, "group_id": "..."}
        3. 自定义JSON格式: {"content": "...", "group_id": "...", "user": "..."}
        """
        try:
            # 格式1: 微信机器人格式（币coin可能通过微信机器人转发）
            if 'wxid' in data and 'msg' in data:
                content = data.get('msg', '')
                group_id = data.get('room', data.get('group_id', 'unknown'))
                user_id = data.get('wxid', '')
                username = data.get('nickname', data.get('user', ''))
                
                message = Message(
                    content=content,
                    message_type=MessageType.TEXT,
                    timestamp=datetime.now(),
                    source_platform=PlatformType.BICOIN,
                    source_chat_id=str(group_id),
                    source_user_id=str(user_id),
                    source_username=username,
                    message_id=data.get('id', ''),
                    extra_data=data
                )
                return message
            
            # 格式2: 交易数据格式
            elif 'data' in data and 'group_id' in data:
                trade_data = data.get('data', {})
                group_id = data.get('group_id', '')
                
                # 构建交易消息内容
                content_parts = []
                if 'pair' in trade_data:
                    content_parts.append(f"交易对: {trade_data['pair']}")
                if 'side' in trade_data:
                    content_parts.append(f"方向: {trade_data['side']}")
                if 'price' in trade_data:
                    content_parts.append(f"价格: {trade_data['price']}")
                if 'amount' in trade_data:
                    content_parts.append(f"数量: {trade_data['amount']}")
                
                content = '\n'.join(content_parts) if content_parts else json.dumps(trade_data, ensure_ascii=False)
                
                message = Message(
                    content=content,
                    message_type=MessageType.TEXT,
                    timestamp=datetime.now(),
                    source_platform=PlatformType.BICOIN,
                    source_chat_id=str(group_id),
                    source_user_id=data.get('user_id', ''),
                    source_username=data.get('username', ''),
                    message_id=data.get('id', ''),
                    extra_data=data
                )
                return message
            
            # 格式3: 自定义JSON格式
            elif 'content' in data or 'message' in data:
                content = data.get('content', data.get('message', ''))
                group_id = data.get('group_id', data.get('chat_id', 'unknown'))
                user_id = data.get('user_id', data.get('user', ''))
                username = data.get('username', data.get('user_name', ''))
                
                message = Message(
                    content=content,
                    message_type=MessageType.TEXT,
                    timestamp=datetime.fromisoformat(data.get('timestamp', datetime.now().isoformat())) 
                             if isinstance(data.get('timestamp'), str) else datetime.now(),
                    source_platform=PlatformType.BICOIN,
                    source_chat_id=str(group_id),
                    source_user_id=str(user_id),
                    source_username=username,
                    message_id=str(data.get('id', data.get('message_id', ''))),
                    extra_data=data
                )
                return message
            
            # 无法识别的格式，尝试通用解析
            else:
                logger.warning(f"无法识别的webhook消息格式: {data}")
                # 尝试提取可能的字段
                content = json.dumps(data, ensure_ascii=False)
                group_id = data.get('group_id', data.get('chat_id', data.get('room', 'unknown')))
                
                message = Message(
                    content=content,
                    message_type=MessageType.TEXT,
                    timestamp=datetime.now(),
                    source_platform=PlatformType.BICOIN,
                    source_chat_id=str(group_id),
                    source_user_id='',
                    source_username='',
                    message_id='',
                    extra_data=data
                )
                return message
                
        except Exception as e:
            logger.error(f"解析Webhook消息失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return None
    
    async def get_chat_info(self, chat_id: str) -> Optional[Dict[str, Any]]:
        """获取群信息"""
        try:
            if not self.connected or not self.session:
                return None
            
            url = f'{self.api_base_url}/api/v1/groups/{chat_id}'
            headers = {
                'Authorization': f'Bearer {self.api_token}',
            }
            
            async with self.session.get(url, headers=headers) as response:
                if response.status == 200:
                    data = await response.json()
                    return {
                        'id': chat_id,
                        'name': data.get('name', ''),
                        'description': data.get('description', ''),
                        'member_count': data.get('member_count', 0),
                        'extra_data': data
                    }
                else:
                    return None
                    
        except Exception as e:
            logger.error(f"获取群信息失败: {e}")
            return None

