# trade_server.py
import sys
import os
import asyncio
from utils.logger import logger
from core.market_trade.trade_service import set_global_is_demo, get_global_is_demo
from config import get_mysql_config
from database.db import MySQLPool, get_enabled_signal_accounts
from core.market_trade.trade_service import TradeService
from core.market_trade.signal_service import SignalService
from model.models import SignalAccount
import traceback
from utils.dingtalk_bot import init_dingtalk_bot, get_dingtalk_bot
from config.dingtalk_config import get_dingtalk_config
import time
import psutil

class TradeServer:
    """交易服务器类，提供交易接口"""
    
    def __init__(self, db_pool=None):
        self.db_pool = db_pool
        self.trade_service = None
        self.signal_service = None
        self.account_manager = None
        self._running = False
        self._tasks = []
    
    async def initialize(self):
        """初始化交易服务器"""
        if not self.db_pool:
            mysql_conf = get_mysql_config()
            self.db_pool = MySQLPool(**mysql_conf)
        
        self.trade_service = TradeService(self.db_pool)
        self.signal_service = SignalService(self.db_pool, self.trade_service)
        self.account_manager = AccountManager(self.db_pool, self.signal_service)
        
        logger.info("交易服务器初始化完成")
    
    async def start(self):
        """启动交易服务器"""
        if self._running:
            logger.warning("交易服务器已在运行")
            return
        
        await self.initialize()
        
        # 启动动态账号监听管理器
        await self.account_manager.monitor_signal_accounts()
        
        # 启动客户账户监听任务
        customer_task = self.trade_service.listen_customer_accounts()
        
        # 启动定时热重载任务
        await self.trade_service.start_all_monitoring_systems()
        
        # 创建所有任务
        self._tasks = [
            customer_task,
            periodic_reload(self.trade_service),
            periodic_price_check(),
            self.trade_service.start_no_trading_monitor(),
            self.trade_service.start_stop_loss_monitor(),
            self.trade_service.check_websocket_connections(),
            periodic_health_check(self.account_manager),
            memory_monitor(),
            db_pool_monitor(self.account_manager),
            system_health_monitor(self.account_manager),
            auto_restart_monitor(self.account_manager, self.trade_service),
        ]
        
        self._running = True
        logger.info("🚀 交易服务器已启动")
    
    async def stop(self):
        """停止交易服务器"""
        if not self._running:
            return
        
        self._running = False
        
        # 清理所有WebSocket连接
        if self.trade_service:
            await self.trade_service.cleanup_all_clients()
        
        logger.info("交易服务器已停止")
    
    async def get_status(self):
        """获取服务器状态"""
        return {
            "running": self._running,
            "tasks_count": len(self._tasks) if self._tasks else 0,
            "db_pool": "initialized" if self.db_pool else "not_initialized",
            "trade_service": "initialized" if self.trade_service else "not_initialized",
            "signal_service": "initialized" if self.signal_service else "not_initialized"
        }

# 系统资源优化
def optimize_system_resources():
    """优化系统资源设置"""
    try:
        # Windows系统不支持resource模块，跳过文件描述符优化
        if sys.platform.startswith('win'):
            logger.info("Windows系统，跳过文件描述符优化")
            
            # 设置asyncio事件循环策略
            asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
            
            # 设置更高的并发限制
            import threading
            threading.stack_size(2**20)  # 1MB栈大小
            
            logger.info("Windows系统资源优化完成")
        else:
            # Unix/Linux系统
            import resource
            # 获取当前文件描述符限制
            soft, hard = resource.getrlimit(resource.RLIMIT_NOFILE)
            logger.info(f"当前文件描述符限制: soft={soft}, hard={hard}")
            
            # 尝试提高文件描述符限制
            if soft < 65536:
                try:
                    resource.setrlimit(resource.RLIMIT_NOFILE, (65536, hard))
                    new_soft, new_hard = resource.getrlimit(resource.RLIMIT_NOFILE)
                    logger.info(f"已提高文件描述符限制: soft={new_soft}, hard={new_hard}")
                except Exception as e:
                    logger.warning(f"无法提高文件描述符限制: {e}")
            
            # 设置更高的并发限制
            import threading
            threading.stack_size(2**20)  # 1MB栈大小
            
            logger.info("Unix/Linux系统资源优化完成")
        
    except Exception as e:
        logger.warning(f"系统资源优化失败: {e}")

class AccountManager:
    def __init__(self, db_pool, signal_service):
        self.db_pool = db_pool
        self.signal_service = signal_service
        self.signal_tasks = {}  # {source_uid: asyncio.Task}
        self._last_signal_uids = set()

    async def _safe_listen_signal_account(self, acc, uid):
        try:
            await self.signal_service.listen_signal_account(SignalAccount(**acc))
        except asyncio.CancelledError:
            logger.info(f'信号源监听任务被取消: {uid}')
            # 清理任务引用
            if uid in self.signal_tasks:
                del self.signal_tasks[uid]
        except Exception as e:
            logger.error(f'信号源监听任务异常退出: {uid}, error={e}\n{traceback.format_exc()}，即将自动重启')
            # 清理任务引用
            if uid in self.signal_tasks:
                del self.signal_tasks[uid]
            # 自动重启
            await asyncio.sleep(2)
            logger.info(f'重启信号源监听: {uid}')
            # 检查是否已经有新任务在运行
            if uid not in self.signal_tasks:
                task = asyncio.create_task(self._safe_listen_signal_account(acc, uid))
                self.signal_tasks[uid] = task

    async def check_tasks_health(self):
        """检查所有信号源监听任务健康状态"""
        try:
            current_time = time.time()
            logger.info(f"🔍 开始检查信号源监听任务健康状态...")
            
            # 获取当前启用的信号源
            signal_accounts = get_enabled_signal_accounts(self.db_pool, get_global_is_demo())
            current_uids = set(acc['source_uid'] for acc in signal_accounts)
            
            # 检查任务状态
            for uid in current_uids:
                task = self.signal_tasks.get(uid)
                if not task:
                    logger.warning(f"⚠️ 信号源 {uid} 没有监听任务，立即创建")
                    acc = next((acc for acc in signal_accounts if acc['source_uid'] == uid), None)
                    if acc:
                        new_task = asyncio.create_task(self._safe_listen_signal_account(acc, uid))
                        self.signal_tasks[uid] = new_task
                        logger.info(f"✅ 信号源 {uid} 监听任务已创建")
                elif task.done():
                    logger.warning(f"⚠️ 信号源 {uid} 监听任务已完成，重新创建")
                    acc = next((acc for acc in signal_accounts if acc['source_uid'] == uid), None)
                    if acc:
                        # 取消旧任务
                        if not task.done():
                            task.cancel()
                            try:
                                await asyncio.wait_for(task, timeout=2.0)
                            except:
                                pass
                        
                        # 创建新任务
                        new_task = asyncio.create_task(self._safe_listen_signal_account(acc, uid))
                        self.signal_tasks[uid] = new_task
                        logger.info(f"✅ 信号源 {uid} 监听任务已重新创建")
                else:
                    logger.info(f"✅ 信号源 {uid} 监听任务运行正常")
            
            # 输出统计信息
            active_tasks = [uid for uid, task in self.signal_tasks.items() if task and not task.done()]
            logger.info(f"📊 任务健康检查完成: 总计 {len(current_uids)} 个信号源，活跃任务 {len(active_tasks)} 个")
            
        except Exception as e:
            logger.error(f"❌ 任务健康检查失败: {e}")
            logger.error(f"任务健康检查异常详情: {traceback.format_exc()}")

    async def monitor_signal_accounts(self):
        first_run = True
        while True:
            try:
                signal_accounts = get_enabled_signal_accounts(self.db_pool, get_global_is_demo())
                current_uids = set(acc['source_uid'] for acc in signal_accounts)
                
                # 新增的信号源
                new_uids = current_uids - self._last_signal_uids
                # 被移除的信号源
                removed_uids = self._last_signal_uids - current_uids
                
                # 启动新增信号源监听
                for acc in signal_accounts:
                    uid = acc['source_uid']
                    task = self.signal_tasks.get(uid)
                    
                    if uid in new_uids:
                        logger.info(f'新增信号源监听: {uid}')
                        # 安全检查，避免重复创建任务
                        if uid not in self.signal_tasks:
                            new_task = asyncio.create_task(self._safe_listen_signal_account(acc, uid))
                            self.signal_tasks[uid] = new_task
                    elif first_run and uid not in self.signal_tasks:
                        logger.info(f'首次启动信号源监听: {uid}')
                        new_task = asyncio.create_task(self._safe_listen_signal_account(acc, uid))
                        self.signal_tasks[uid] = new_task
                    elif task and task.done():
                        # 任务异常退出但未被清理，自动重启
                        logger.warning(f'监听任务异常退出，自动重启: {uid}')
                        # 先取消旧任务（如果还在运行）
                        if not task.done():
                            task.cancel()
                            try:
                                # 等待任务完全取消，最多等待5秒
                                await asyncio.wait_for(task, timeout=5.0)
                            except asyncio.TimeoutError:
                                logger.warning(f'任务取消超时: {uid}')
                            except Exception as e:
                                logger.error(f'取消任务时异常: {uid}, error={e}')
                        
                        # 等待一小段时间确保任务完全清理
                        await asyncio.sleep(1)
                        # 安全检查，避免重复创建任务
                        if uid not in self.signal_tasks:
                            new_task = asyncio.create_task(self._safe_listen_signal_account(acc, uid))
                            self.signal_tasks[uid] = new_task
                    elif uid not in self.signal_tasks:
                        # 新增：检查是否有信号源没有对应的监听任务（可能是重连后丢失的）
                        logger.warning(f'发现信号源 {uid} 没有监听任务，立即创建: {uid}')
                        new_task = asyncio.create_task(self._safe_listen_signal_account(acc, uid))
                        self.signal_tasks[uid] = new_task
                
                # 取消被移除的信号源监听
                for uid in removed_uids:
                    logger.info(f'移除信号源监听: {uid}')
                    task = self.signal_tasks.get(uid)
                    if task:
                        task.cancel()
                        try:
                            # 等待任务完全取消，最多等待5秒
                            await asyncio.wait_for(task, timeout=5.0)
                        except asyncio.TimeoutError:
                            logger.warning(f'移除任务取消超时: {uid}')
                        except Exception as e:
                            logger.error(f'移除任务时异常: {uid}, error={e}')
                        finally:
                            # 安全删除，避免KeyError
                            if uid in self.signal_tasks:
                                del self.signal_tasks[uid]
                
                # 清理已完成的任务引用
                completed_tasks = [uid for uid, task in self.signal_tasks.items() if task.done()]
                for uid in completed_tasks:
                    logger.info(f'清理已完成的任务: {uid}')
                    # 安全删除，避免KeyError
                    if uid in self.signal_tasks:
                        del self.signal_tasks[uid]
                
                # 新增：检查所有信号源监听任务状态
                for uid in current_uids:
                    task = self.signal_tasks.get(uid)
                    if not task or task.done():
                        logger.warning(f'信号源 {uid} 监听任务状态异常，重新创建')
                        # 查找对应的账户信息
                        acc = next((acc for acc in signal_accounts if acc['source_uid'] == uid), None)
                        if acc:
                            # 取消旧任务
                            if task and not task.done():
                                task.cancel()
                                try:
                                    await asyncio.wait_for(task, timeout=2.0)
                                except:
                                    pass
                            
                            # 创建新任务
                            new_task = asyncio.create_task(self._safe_listen_signal_account(acc, uid))
                            self.signal_tasks[uid] = new_task
                            logger.info(f'信号源 {uid} 监听任务已重新创建')
                
                self._last_signal_uids = current_uids
                first_run = False
                
                # 输出当前任务状态
                active_tasks = [uid for uid, task in self.signal_tasks.items() if task and not task.done()]
                logger.info(f'当前活跃的信号源监听任务: {active_tasks}')
                
                # 缩短检查间隔从30秒改为10秒，提高响应速度
                await asyncio.sleep(10)
                
            except Exception as e:
                logger.error(f'监控信号源账户时异常: {e}\n{traceback.format_exc()}')
                # 异常后等待时间也缩短，从30秒改为10秒
                await asyncio.sleep(10)

async def memory_monitor():
    """内存监控任务 - 每分钟检查一次内存使用情况"""
    while True:
        try:
            
            if psutil:
                process = psutil.Process()
                memory_info = process.memory_info()
                memory_mb = memory_info.rss / 1024 / 1024
            
                if memory_mb > 800:  # 超过800MB严重警告
                    logger.error(f"🚨 内存使用严重过高: {memory_mb:.2f} MB，建议立即重启")
                    # 发送钉钉告警
                    try:
                        from utils.dingtalk_bot import get_dingtalk_bot
                        bot = get_dingtalk_bot()
                        if bot:
                            alert_info = {
                                "title": "内存使用严重过高告警",
                                "level": "ERROR",
                                "message": f"系统内存使用已达到 {memory_mb:.2f} MB",
                                "account": "系统级别",
                                "strategy": "内存监控",
                                "symbol": "系统资源",
                                "suggestion": "建议立即重启系统或检查内存泄漏"
                            }
                            asyncio.create_task(bot.send_alert_notification_async("error", alert_info))
                    except Exception as e:
                        logger.error(f"发送钉钉告警失败: {e}")
                elif memory_mb > 500:  # 超过500MB警告
                    logger.warning(f"⚠️ 内存使用过高: {memory_mb:.2f} MB")
                else:
                    logger.info(f"📊 内存使用正常: {memory_mb:.2f} MB")
            else:
                logger.debug("psutil不可用，跳过内存监控")
            
            await asyncio.sleep(60)  # 每分钟检查一次
        except Exception as e:
            logger.error(f"内存监控异常: {e}")
            await asyncio.sleep(60)

async def db_pool_monitor(account_manager):
    """数据库连接池监控 - 每5分钟检查一次"""
    while True:
        try:
            # 检查数据库连接池状态
            if hasattr(account_manager, 'db_pool') and hasattr(account_manager.db_pool, '_pool'):
                pool_size = len(account_manager.db_pool._pool)
                if pool_size > 50:  # 连接数过多
                    logger.warning(f"⚠️ 数据库连接池过大: {pool_size} 个连接")
                elif pool_size > 30:  # 连接数较多
                    logger.info(f"📊 数据库连接池状态: {pool_size} 个连接")
                else:
                    logger.debug(f"📊 数据库连接池状态: {pool_size} 个连接")
            else:
                logger.debug("数据库连接池监控: 无法获取连接池信息")
            
            await asyncio.sleep(300)  # 每5分钟检查一次
        except Exception as e:
            logger.error(f"数据库连接池监控异常: {e}")
            await asyncio.sleep(300)

async def system_health_monitor(account_manager):
    """系统健康监控 - 综合监控系统状态"""
    while True:
        try:
            # 检查关键任务状态
            active_tasks = len([task for task in asyncio.all_tasks() if not task.done()])
            logger.info(f"📊 系统健康状态: 活跃任务 {active_tasks} 个")
            
            # 检查信号队列大小
            if hasattr(account_manager.signal_service, 'signal_queue'):
                queue_size = account_manager.signal_service.signal_queue.qsize()
                if queue_size > 100:  # 队列过大警告
                    logger.warning(f"⚠️ 信号队列过大: {queue_size} 条消息")
                elif queue_size > 50:  # 队列较大
                    logger.info(f"📊 信号队列状态: {queue_size} 条消息")
                else:
                    logger.debug(f"📊 信号队列状态: {queue_size} 条消息")
            
            await asyncio.sleep(120)  # 每2分钟检查一次
        except Exception as e:
            logger.error(f"系统健康监控异常: {e}")
            await asyncio.sleep(120)

async def auto_restart_monitor(account_manager, trade_service):
    """自动重启监控任务 - 每10分钟检查一次内存并在必要时重启关键任务"""
    while True:
        try:
            await trade_service.check_memory_and_restart()
            await asyncio.sleep(600)  # 每10分钟检查一次
        except Exception as e:
            logger.error(f"自动重启监控异常: {e}")
            logger.error(f"异常详情: {traceback.format_exc()}")
            await asyncio.sleep(600)

async def periodic_health_check(account_manager):
    """定期检查信号源监听任务健康状态"""
    while True:
        try:
            await account_manager.check_tasks_health()
            logger.info("[定时任务] 信号源监听任务健康检查完成")
        except Exception as e:
            logger.error(f"[定时任务] 信号源监听任务健康检查失败: {e}")
            logger.error(f"[定时任务] 信号源监听任务健康检查异常详情: {traceback.format_exc()}")
        await asyncio.sleep(300)  # 每5分钟检查一次

def init_dingtalk_early():
    """早期初始化钉钉机器人"""
    try:
        dingtalk_config = get_dingtalk_config()
        if dingtalk_config and dingtalk_config.get("enabled", False):
            webhook_url = dingtalk_config.get("webhook_url")
            secret = dingtalk_config.get("secret")
            if webhook_url and webhook_url != "YOUR_ACCESS_TOKEN" and secret and secret != "YOUR_SECRET_KEY":
                if init_dingtalk_bot(webhook_url, secret):
                    logger.info("✅ 钉钉机器人早期初始化成功")
                    return True
                else:
                    logger.warning("⚠️ 钉钉机器人早期初始化失败")
                    return False
            else:
                logger.warning("⚠️ 钉钉机器人配置未完成，跳过早期初始化")
                return False
        else:
            logger.info("ℹ️ 钉钉通知已禁用，跳过早期初始化")
            return False
    except Exception as e:
        logger.error(f"❌ 钉钉机器人早期初始化失败: {e}")
        return False

async def periodic_reload(trade_service):
    """保留定时重新加载作为备用机制，但频率降低"""
    while True:
        try:
            # 只在必要时重新加载，减少资源占用
            await asyncio.sleep(300)  # 每5分钟检查一次，作为备用机制
        except Exception as e:
            logger.error(f"[定时任务] 配置重新加载失败: {e}")
            await asyncio.sleep(300)

async def periodic_position_check(trade_service):
    """定时检查仓位异常，周期由 config 的 reconcile.interval_seconds 决定"""
    from config import get_reconcile_config
    while True:
        try:
            interval = int(get_reconcile_config().get('interval_seconds', 300))
        except Exception:
            interval = 300
        try:
            await trade_service.check_position_anomalies()
            logger.info("[定时任务] 仓位异常检查完成")
        except Exception as e:
            logger.error(f"[定时任务] 仓位异常检查失败: {e}")
        await asyncio.sleep(max(30, interval))  # 下限 30s，防误配成 0 空转

async def periodic_price_check():
    """定期检查价格缓存状态"""
    while True:
        try:
            logger.info(f"[定时任务] 开始价格缓存检查...")
            # 这里可以添加价格缓存的具体逻辑
            logger.info(f"[定时任务] 价格缓存检查完成")
            await asyncio.sleep(300)  # 每5分钟检查一次
        except Exception as e:
            logger.error(f"[定时任务] 价格缓存检查失败: {e}")
            logger.error(f"[定时任务] 价格缓存检查异常详情: {traceback.format_exc()}")
            # 异常后等待较短时间再重试，避免长时间停止
            await asyncio.sleep(60)  # 异常后1分钟重试

async def refresh_contract_specs():
    """启动时从交易所拉取真实合约规格，覆盖静态表。失败保留静态表兜底。

    OKX 用公共 instruments 接口（无需密钥）。Binance fapi 规格刷新在
    fapi 客户端就绪后接入（阶段 3），此处 try/except 保证任一失败不影响启动。
    """
    from config import contract_spec_manager
    try:
        from exchange.base_client import ExchangeClientFactory, ExchangeType
        okx_public = ExchangeClientFactory.create_rest_client(
            ExchangeType.OKX, api_key="", api_secret="",
            passphrase="", is_demo=get_global_is_demo())
        await contract_spec_manager.refresh_from_okx(okx_public)
    except Exception as e:
        logger.error(f"[合约规格] OKX 规格刷新失败，保留静态表: {e}")
    try:
        from exchange.binance.binance_fapi_rest_client import BinanceFapiRESTClient
        fapi_public = BinanceFapiRESTClient(api_key="", api_secret="",
                                            is_demo=get_global_is_demo())
        await contract_spec_manager.refresh_from_binance(fapi_public)
    except ImportError:
        logger.info("[合约规格] Binance fapi 客户端尚未就绪，跳过 Binance 规格刷新")
    except Exception as e:
        logger.error(f"[合约规格] Binance 规格刷新失败，保留静态表: {e}")
    logger.info(f"[合约规格] 动态规格缓存共 {contract_spec_manager.spec_count()} 个合约")


async def main():
    mysql_conf = get_mysql_config()
    db_pool = MySQLPool(**mysql_conf)
    trade_service = TradeService(db_pool)
    signal_service = SignalService(db_pool, trade_service)
    # 启动动态账号监听管理器
    account_manager = AccountManager(db_pool, signal_service)
    # 启动客户账户监听任务
    customer_task = trade_service.listen_customer_accounts()
    
    try:
        # 启动时刷新动态合约规格（覆盖静态表，失败兜底）
        await refresh_contract_specs()

        # 启动定时热重载任务
        # 先启动监控系统
        await trade_service.start_all_monitoring_systems()
        
        # 创建所有任务
        tasks = [
            account_manager.monitor_signal_accounts(),
            customer_task,
            periodic_reload(trade_service),
            periodic_position_check(trade_service),
            periodic_price_check(), # 添加价格缓存检查任务
            trade_service.start_no_trading_monitor(),  # 启动长时间无开仓监控
            trade_service.start_stop_loss_monitor(),  # 启动止损监控
            trade_service.check_websocket_connections(),  # 添加WebSocket连接监控
            # 新增：定期健康检查任务
            periodic_health_check(account_manager),  # 定期检查任务健康状态
            memory_monitor(), # 添加内存监控任务
            db_pool_monitor(account_manager), # 添加数据库连接池监控任务
            system_health_monitor(account_manager), # 添加系统健康监控任务
            auto_restart_monitor(account_manager, trade_service), # 添加自动重启监控任务
        ]
        
        # 启动所有任务并监控
        logger.info("🚀 所有任务已启动，开始监控...")
        
        # 使用asyncio.gather启动所有任务，并添加异常处理
        await asyncio.gather(*tasks, return_exceptions=True)
        
    except KeyboardInterrupt:
        logger.info("收到中断信号，开始清理资源...")
    except Exception as e:
        logger.error(f"主程序异常: {e}")
        logger.error(f"主程序异常详情: {traceback.format_exc()}")
    finally:
        # 清理所有WebSocket连接
        await trade_service.cleanup_all_clients()
        logger.info("主程序退出，所有资源已清理")

def start_trade():
    logger.info("启动交易服务...")
    
    # 在交易服务进程中初始化钉钉机器人
    logger.info("🔧 交易服务进程初始化钉钉机器人...")
    dingtalk_initialized = init_dingtalk_early()
    if dingtalk_initialized:
        logger.info("✅ 交易服务进程钉钉机器人已就绪")
    else:
        logger.warning("⚠️ 交易服务进程钉钉机器人初始化失败")
    
    asyncio.run(main())

if __name__ == '__main__':
    # 优化系统资源
    optimize_system_resources()
    
    # 早期初始化钉钉机器人
    logger.info("🔧 开始早期初始化钉钉机器人...")
    dingtalk_initialized = init_dingtalk_early()
    if dingtalk_initialized:
        logger.info("✅ 钉钉机器人已就绪，可以接收交易通知")
    else:
        logger.warning("⚠️ 钉钉机器人初始化失败，交易通知功能不可用")
    
    # 支持通过命令行参数或环境变量切换实盘/模拟盘
    mode = None
    if len(sys.argv) > 1:
        mode = sys.argv[1].strip().lower()
    elif os.environ.get('TRADE_MODE'):
        mode = os.environ['TRADE_MODE'].strip().lower()
    if mode == 'real':
        set_global_is_demo(0)
        os.environ['IS_DEMO'] = '0'
    elif mode == 'demo':
        set_global_is_demo(1)
        os.environ['IS_DEMO'] = '1'
    if get_global_is_demo():
        print("当前使用模拟盘交易环境。")
    else:
        print("当前使用实盘交易环境，请关注资金安全！")

    start_trade() 