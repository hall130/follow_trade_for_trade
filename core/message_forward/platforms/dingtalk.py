"""
钉钉消息平台实现
支持钉钉群机器人和钉钉 Stream 模式
"""

from typing import Callable, Dict, List, Optional, Any
import asyncio
import aiohttp
import hmac
import hashlib
import base64
import time
import urllib.parse
import concurrent.futures
import threading

from ..base import MessagePlatform
from ..models import Message, MessageType, PlatformType
from utils.logger import get_logger

logger = get_logger(__name__)

# 全局线程池（用于处理事件循环关闭时的异步发送）
# 所有钉钉平台实例共享此线程池，避免频繁创建和销毁线程
_global_thread_pool = None
_thread_pool_lock = threading.Lock()
_thread_pool_max_workers = 20  # 最大线程数，可根据实际需求调整

def get_global_thread_pool():
    """获取全局线程池（单例模式）"""
    global _global_thread_pool
    if _global_thread_pool is None:
        with _thread_pool_lock:
            if _global_thread_pool is None:
                _global_thread_pool = concurrent.futures.ThreadPoolExecutor(
                    max_workers=_thread_pool_max_workers,
                    thread_name_prefix="dingtalk_sender"
                )
                logger.info(f"✅ 创建全局钉钉消息发送线程池 (最大线程数: {_thread_pool_max_workers})")
    return _global_thread_pool

class DingTalkPlatform(MessagePlatform):
    """钉钉消息平台"""
    
    def __init__(self, config: Dict[str, Any]):
        super().__init__(PlatformType.DINGTALK, config)
        
        # 群机器人配置
        self.webhook_url = config.get('webhook_url')
        self.secret = config.get('secret')  # 加签密钥
        
        # Stream 模式配置（用于接收消息）
        self.client_id = config.get('client_id')
        self.client_secret = config.get('client_secret')
        
        # 运行时状态
        self.session = None
        self.stream_task = None
        
        if not self.webhook_url:
            logger.warning("钉钉 webhook_url 未配置")
            self.enabled = False
    
    async def connect(self) -> bool:
        """连接到钉钉"""
        if not self.enabled:
            logger.warning("钉钉平台未启用")
            return False
        
        try:
            logger.info("正在连接钉钉...")
            
            # 创建 HTTP 会话
            self.session = aiohttp.ClientSession()
            
            # 先设置连接状态（必须在测试之前，因为测试会调用 send_message）
            self.connected = True
            
            # 验证配置（不发送实际消息，避免打扰用户）
            if self.webhook_url:
                logger.info("✅ 钉钉 Webhook 配置有效")
            else:
                logger.warning("⚠️ 钉钉 Webhook URL 未配置")
            
            logger.info("✅ 钉钉连接成功")
            
            # 如果配置了 Stream 模式，启动消息监听
            if self.client_id and self.client_secret:
                asyncio.create_task(self._start_stream_listener())
            
            return True
            
        except Exception as e:
            logger.error(f"钉钉连接失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
            self.connected = False
            return False
    
    async def disconnect(self) -> bool:
        """断开钉钉连接"""
        try:
            if self.stream_task:
                self.stream_task.cancel()
            
            if self.session:
                try:
                    await self.session.close()
                except Exception as e:
                    logger.warning(f"关闭钉钉 session 时出错: {e}")
                finally:
                    self.session = None
            
            logger.info("钉钉连接已断开")
            self.connected = False
            return True
        except Exception as e:
            logger.error(f"钉钉断开连接失败: {e}")
            return False
    
    def __del__(self):
        """析构函数，确保 session 被清理"""
        if self.session:
            try:
                # 尝试关闭 session（如果事件循环仍然可用）
                import asyncio
                try:
                    loop = asyncio.get_event_loop()
                    if loop.is_running():
                        # 如果事件循环正在运行，创建任务来关闭
                        loop.create_task(self.session.close())
                    else:
                        # 如果事件循环未运行，尝试运行直到完成
                        loop.run_until_complete(self.session.close())
                except:
                    # 如果无法关闭，至少设置为 None
                    self.session = None
            except:
                pass
    
    def _generate_sign(self) -> tuple:
        """生成钉钉签名"""
        if not self.secret:
            return None, None
        
        timestamp = str(round(time.time() * 1000))
        secret_enc = self.secret.encode('utf-8')
        string_to_sign = f'{timestamp}\n{self.secret}'
        string_to_sign_enc = string_to_sign.encode('utf-8')
        hmac_code = hmac.new(secret_enc, string_to_sign_enc, digestmod=hashlib.sha256).digest()
        sign = urllib.parse.quote_plus(base64.b64encode(hmac_code))
        return timestamp, sign
    
    async def send_message(self, chat_id: str, message: Message) -> bool:
        """发送消息到钉钉"""
        if not self.connected:
            logger.error("钉钉未连接")
            return False
        
        # 确保 session 存在且有效，如果不存在或事件循环已关闭则重新创建
        try:
            # 检查当前事件循环状态
            try:
                current_loop = asyncio.get_running_loop()
                if current_loop.is_closed():
                    raise RuntimeError("Event loop is closed")
                # 有运行的事件循环，检查 session 是否需要重新创建
                if not self.session:
                    # 创建 session 时显式指定 timeout，避免 "Timeout context manager should be used inside a task" 错误
                    timeout = aiohttp.ClientTimeout(total=30, connect=10)
                    self.session = aiohttp.ClientSession(timeout=timeout, loop=current_loop)
                else:
                    # 检查 session 是否仍然有效（通过检查其内部连接器）
                    try:
                        # 尝试访问 session 的内部属性来检查是否有效
                        if hasattr(self.session, '_connector') and self.session._connector is None:
                            # Session 已关闭，重新创建
                            timeout = aiohttp.ClientTimeout(total=30, connect=10)
                            self.session = aiohttp.ClientSession(timeout=timeout, loop=current_loop)
                    except:
                        # 如果检查失败，重新创建 session
                        try:
                            await self.session.close()
                        except:
                            pass
                        timeout = aiohttp.ClientTimeout(total=30, connect=10)
                        self.session = aiohttp.ClientSession(timeout=timeout, loop=current_loop)
            except RuntimeError:
                # 没有运行的事件循环或已关闭，直接使用线程池发送，不创建 session
                # 因为在这种情况下创建 session 会导致 "Timeout context manager should be used inside a task" 错误
                if self.session:
                    try:
                        await self.session.close()
                    except:
                        pass
                    self.session = None
                # 直接跳到线程池发送逻辑
                pass
        except Exception as e:
            logger.error(f"创建钉钉会话失败: {e}")
            # 如果创建失败，清空 session，后续使用线程池发送
            if self.session:
                try:
                    await self.session.close()
                except:
                    pass
                self.session = None
        
        try:
            # 构造请求 URL（添加签名）
            url = self.webhook_url
            if self.secret:
                timestamp, sign = self._generate_sign()
                url = f"{self.webhook_url}&timestamp={timestamp}&sign={sign}"
            
            # 从消息中提取交易类型（用于钉钉消息标题）
            # 优先从 extra_data 中获取 trade_info，然后提取 trade_type
            title = "消息转发"  # 默认标题
            if message.extra_data:
                trade_info = message.extra_data.get('trade_info')
                if trade_info:
                    # 从 trade_info 中提取交易类型
                    original_action = trade_info.get('original_action', '').upper()
                    direct = trade_info.get('direct', '').upper()
                    
                    # 判断交易类型（与 alert_receiver.py 中的逻辑保持一致）
                    if original_action == 'BUY' and direct == 'SHORT':
                        title = "平空"
                    elif original_action == 'SELL' and direct == 'LONG':
                        title = "平多"
                    elif original_action == 'BUY' and direct == 'LONG':
                        title = "开多"
                    elif original_action == 'SELL' and direct == 'SHORT':
                        title = "开空"
                    elif original_action == 'BUY':
                        title = "买入"
                    elif original_action == 'SELL':
                        title = "卖出"
                    elif original_action == 'CLOSE' or trade_info.get('action') == 'close':
                        if direct == 'SHORT':
                            title = "平空"
                        elif direct == 'LONG':
                            title = "平多"
                        else:
                            title = "平仓"
            
            # 如果从 extra_data 中没有获取到，尝试从消息内容中解析
            if title == "消息转发" and message.content:
                import re
                # 方法1：尝试从消息内容中提取交易类型（格式：📊 **交易类型**: 平空）
                match = re.search(r'\*\*交易类型\*\*:\s*(\S+)', message.content)
                if match:
                    title = match.group(1)
                else:
                    # 方法2：尝试从消息第一行提取标题（格式：🔔 TradingView 交易信号 或 🔔 平空）
                    first_line = message.content.split('\n')[0].strip()
                    # 移除 emoji 和多余空格
                    first_line_clean = re.sub(r'^[🔔📊💵📈🆔⏰]+', '', first_line).strip()
                    if first_line_clean and first_line_clean != "TradingView 交易信号":
                        # 如果第一行不是默认标题，使用它作为 title
                        title = first_line_clean
            
            # 构造消息体
            if message.message_type == MessageType.MARKDOWN:
                payload = {
                    "msgtype": "markdown",
                    "markdown": {
                        "title": title,
                        "text": message.formatted_content or message.content
                    }
                }
            elif message.message_type == MessageType.LINK:
                payload = {
                    "msgtype": "link",
                    "link": {
                        "title": title,
                        "text": message.content,
                        "messageUrl": message.extra_data.get('url', ''),
                        "picUrl": message.extra_data.get('pic_url', '')
                    }
                }
            else:
                # 普通文本消息
                payload = {
                    "msgtype": "text",
                    "text": {
                        "content": message.content
                    }
                }
            
            # 发送消息（确保在正确的事件循环上下文中）
            # 如果没有 session（事件循环不可用），直接使用线程池发送
            if not self.session:
                # 直接跳到线程池发送逻辑
                raise RuntimeError("Event loop is closed")
            
            # 尝试使用 session 发送，如果失败则使用线程池
            use_thread_pool = False
            try:
                async with self.session.post(url, json=payload) as response:
                    result = await response.json()
                    
                    if result.get('errcode') == 0:
                        logger.info(f"✅ 钉钉消息发送成功: chat_id={chat_id}")
                        return True
                    else:
                        error_msg = result.get('errmsg', '未知错误')
                        logger.error(f"❌ 钉钉消息发送失败: chat_id={chat_id}, errcode={result.get('errcode')}, errmsg={error_msg}")
                        logger.error(f"   请求URL: {url[:100]}...")
                        return False
            except (RuntimeError, Exception) as e:
                error_msg = str(e).lower()
                # 检查是否是 timeout context manager 错误或其他需要线程池的错误
                if ("timeout context manager should be used inside a task" in error_msg or
                    "event loop is closed" in error_msg or 
                    "no running event loop" in error_msg):
                    use_thread_pool = True
                else:
                    # 其他错误，重新抛出
                    raise
            
            # 如果需要使用线程池，执行线程池发送逻辑
            if use_thread_pool:
                logger.warning(f"⚠️ 检测到事件循环问题，使用全局线程池发送消息到钉钉: chat_id={chat_id}")
                logger.info(f"📤 线程池发送详情: webhook_url={self.webhook_url[:50] if self.webhook_url else None}..., payload长度={len(str(payload))}")
                # 清空 session，避免后续再次使用
                if self.session:
                    try:
                        await self.session.close()
                    except:
                        pass
                    self.session = None
                
                try:
                    # 在新线程中运行异步发送
                    def run_in_thread():
                        """在新线程中创建新的事件循环并发送消息"""
                        new_loop = None
                        try:
                            import threading
                            thread_id = threading.current_thread().ident
                            thread_name = threading.current_thread().name
                            logger.info(f"🔄 [线程 {thread_id}:{thread_name}] 线程池任务开始: chat_id={chat_id}, url={url[:80]}...")
                            # 创建新的事件循环（不使用 nest_asyncio）
                            new_loop = asyncio.new_event_loop()
                            asyncio.set_event_loop(new_loop)
                            logger.info(f"✅ [线程 {thread_id}] 事件循环创建成功")
                            
                            # 发送消息（在新的事件循环中）
                            async def send():
                                """在新的事件循环中发送消息"""
                                try:
                                    logger.info(f"🔄 [线程 {thread_id}] 异步发送函数开始: 创建 session...")
                                    # 在新的事件循环中创建 session（确保使用正确的事件循环和 timeout）
                                    timeout = aiohttp.ClientTimeout(total=30, connect=10)
                                    session = aiohttp.ClientSession(timeout=timeout, loop=new_loop)
                                    logger.info(f"✅ [线程 {thread_id}] Session 创建成功")
                                    try:
                                        logger.info(f"🔄 [线程 {thread_id}] 发送 HTTP POST 请求: url={url[:80]}...")
                                        async with session.post(url, json=payload) as response:
                                            logger.info(f"✅ [线程 {thread_id}] 收到 HTTP 响应: status={response.status}")
                                            result = await response.json()
                                            logger.info(f"✅ [线程 {thread_id}] JSON 解析成功: errcode={result.get('errcode')}, errmsg={result.get('errmsg', 'N/A')}")
                                            return result
                                    finally:
                                        logger.info(f"🔄 [线程 {thread_id}] 关闭 session...")
                                        await session.close()
                                        logger.info(f"✅ [线程 {thread_id}] Session 已关闭")
                                except Exception as send_error:
                                    logger.error(f"❌ [线程 {thread_id}] 异步发送函数内部错误: {send_error}")
                                    import traceback
                                    logger.error(f"[线程 {thread_id}] 错误堆栈:\n{traceback.format_exc()}")
                                    raise
                            
                            # 直接运行，不使用 nest_asyncio
                            logger.info(f"🔄 [线程 {thread_id}] 运行异步函数...")
                            result = new_loop.run_until_complete(send())
                            logger.info(f"✅ [线程 {thread_id}] 异步函数执行完成，结果: {result}")
                            
                            if result.get('errcode') == 0:
                                logger.info(f"✅ 钉钉消息发送成功（线程池）: chat_id={chat_id}")
                                return True
                            else:
                                error_msg = result.get('errmsg', '未知错误')
                                logger.error(f"❌ 钉钉消息发送失败（线程池）: chat_id={chat_id}, errcode={result.get('errcode')}, errmsg={error_msg}")
                                logger.error(f"   完整响应: {result}")
                                return False
                        except Exception as thread_error:
                            import threading
                            thread_id = threading.current_thread().ident
                            logger.error(f"❌ [线程 {thread_id}] 在全局线程池中发送钉钉消息失败: {thread_error}")
                            import traceback
                            logger.error(f"[线程 {thread_id}] 完整错误堆栈:\n{traceback.format_exc()}")
                            return False
                        finally:
                            # 清理事件循环
                            import threading
                            thread_id = threading.current_thread().ident
                            logger.info(f"🔄 [线程 {thread_id}] 开始清理事件循环...")
                            if new_loop:
                                try:
                                    # 取消所有待处理的任务
                                    try:
                                        pending = asyncio.all_tasks(new_loop)
                                        if pending:
                                            logger.debug(f"   取消 {len(pending)} 个待处理任务")
                                            for task in pending:
                                                task.cancel()
                                            # 等待任务取消完成
                                            new_loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
                                    except Exception as cleanup_error:
                                        logger.warning(f"清理待处理任务时出错: {cleanup_error}")
                                finally:
                                    try:
                                        new_loop.close()
                                        logger.debug(f"✅ 事件循环已关闭")
                                    except Exception as close_error:
                                        logger.warning(f"关闭事件循环时出错: {close_error}")
                                    finally:
                                        try:
                                            asyncio.set_event_loop(None)
                                        except:
                                            pass
                    
                    # 使用全局线程池执行（复用线程，避免频繁创建和销毁）
                    logger.info(f"🔄 提交任务到全局线程池: chat_id={chat_id}")
                    thread_pool = get_global_thread_pool()
                    future = thread_pool.submit(run_in_thread)
                    logger.info(f"⏳ 等待线程池任务完成（最多30秒）...")
                    try:
                        result = future.result(timeout=30)  # 30秒超时
                        logger.info(f"✅ 线程池任务完成，结果: {result}")
                        return result
                    except Exception as timeout_error:
                        logger.error(f"❌ 线程池任务超时或异常: {timeout_error}")
                        import traceback
                        logger.error(f"完整错误堆栈:\n{traceback.format_exc()}")
                        # 尝试取消任务
                        try:
                            future.cancel()
                            logger.warning(f"⚠️ 已尝试取消超时的线程池任务")
                        except:
                            pass
                        return False
                        
                except Exception as retry_error:
                    logger.error(f"❌ 线程池重试发送钉钉消息失败: {retry_error}")
                    import traceback
                    logger.error(f"完整错误堆栈:\n{traceback.format_exc()}")
                    return False
                    
        except Exception as e:
            logger.error(f"钉钉发送消息失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return False
    
    async def listen(self, callback: Callable[[Message], None]) -> None:
        """监听钉钉消息"""
        self.add_message_handler(callback)
        logger.info("钉钉消息监听已启动")
    
    async def _test_webhook(self) -> bool:
        """测试 Webhook 连接"""
        try:
            # 发送测试消息
            test_message = Message(
                content="[测试] 钉钉消息转发系统连接测试",
                message_type=MessageType.TEXT
            )
            return await self.send_message("", test_message)
        except Exception as e:
            logger.error(f"钉钉 Webhook 测试失败: {e}")
            return False
    
    async def _start_stream_listener(self):
        """
        启动 Stream 模式消息监听
        注意：这需要钉钉企业内部应用的权限
        """
        try:
            logger.info("启动钉钉 Stream 模式监听...")
            # TODO: 实现钉钉 Stream 模式
            # 这需要使用钉钉开放平台的 Stream SDK
            # https://open.dingtalk.com/document/isvapp/stream-overview
            
            logger.warning("钉钉 Stream 模式暂未实现，仅支持发送消息")
            
        except Exception as e:
            logger.error(f"钉钉 Stream 监听失败: {e}")
    
    async def get_chat_info(self, chat_id: str) -> Optional[Dict[str, Any]]:
        """获取钉钉聊天信息"""
        # 钉钉群机器人模式无法获取群信息
        # 如果需要，可以通过 OpenAPI 实现
        return {
            'id': chat_id,
            'platform': 'dingtalk',
            'type': 'group'
        }

