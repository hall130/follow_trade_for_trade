# main.py
import sys
import os
import asyncio
import threading
import time
import webbrowser
from multiprocessing import Process
from utils.logger import logger
from core.market_trade.trade_service import set_global_is_demo, get_global_is_demo

def optimize_system_resources():
    """优化系统资源设置"""
    try:
        # Windows系统不支持resource模块，跳过文件描述符优化
        if sys.platform.startswith('win'):
            logger.info("Windows系统，跳过文件描述符优化")
            
            # 设置asyncio事件循环策略
            asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
            
            # 设置更高的并发限制
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
            threading.stack_size(2**20)  # 1MB栈大小
            
            logger.info("Unix/Linux系统资源优化完成")
        
    except Exception as e:
        logger.warning(f"系统资源优化失败: {e}")

def start_frontend():
    """启动前端Web服务器"""
    try:
        import subprocess
        import socket
        
        # 检查frontend目录是否存在
        frontend_dir = os.path.join(os.path.dirname(__file__), 'frontend')
        if not os.path.exists(frontend_dir):
            logger.warning(f"前端目录不存在: {frontend_dir}")
            return
        
        # 查找可用端口
        port = 8080
        while port < 8090:
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                result = sock.connect_ex(('localhost', port))
                sock.close()
                
                if result != 0:  # 端口可用
                    break
                port += 1
            except:
                port += 1
                continue
        else:
            logger.error("无法找到可用端口启动前端服务器")
            return
        
        logger.info(f"🌐 准备启动前端服务器: http://localhost:{port}")
        logger.info(f"�� 前端目录: {os.path.abspath(frontend_dir)}")
        
        def run_frontend_server():
            try:
                # 切换到前端目录
                os.chdir(frontend_dir)
                
                # 启动HTTP服务器
                cmd = [sys.executable, '-m', 'http.server', str(port)]
                
                # 启动服务器进程
                process = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    cwd=frontend_dir
                )
                
                # 等待服务器启动
                time.sleep(3)
                
                # 检查进程是否还在运行
                if process.poll() is None:
                    logger.info(f"✅ 前端服务器启动成功: http://localhost:{port}")
                    
                    # 自动打开浏览器
                    try:
                        webbrowser.open(f'http://localhost:{port}')
                        logger.info(f"🚀 已自动打开浏览器: http://localhost:{port}")
                    except Exception as e:
                        logger.warning(f"无法自动打开浏览器: {e}")
                        logger.info(f"请手动访问: http://localhost:{port}")
                    
                    # 保持进程运行
                    try:
                        process.wait()
                    except KeyboardInterrupt:
                        logger.info("前端服务器收到中断信号，正在关闭...")
                        process.terminate()
                        process.wait()
                else:
                    # 进程已退出，获取错误信息
                    stdout, stderr = process.communicate()
                    logger.error(f"前端服务器启动失败: {stderr.decode()}")
                    
            except Exception as e:
                logger.error(f"启动前端服务器失败: {e}")
            finally:
                # 恢复原始工作目录
                try:
                    os.chdir(os.path.dirname(__file__))
                except:
                    pass
        
        # 在新线程中启动前端服务器
        frontend_thread = threading.Thread(target=run_frontend_server, daemon=True)
        frontend_thread.start()
        
        # 等待一下确保服务器启动
        time.sleep(1)
            
    except Exception as e:
        logger.error(f"启动前端服务器失败: {e}")
        # 如果subprocess方式失败，尝试使用备用方式
        start_frontend_fallback(port, frontend_dir)

def start_frontend_fallback(port, frontend_dir):
    """备用前端启动方式"""
    try:
        logger.info("尝试使用备用方式启动前端服务器...")
        
        def run_simple_server():
            try:
                import http.server
                import socketserver
                
                # 创建简单的HTTP服务器
                handler = http.server.SimpleHTTPRequestHandler
                
                # 设置工作目录
                original_dir = os.getcwd()
                os.chdir(frontend_dir)
                
                try:
                    with socketserver.TCPServer(("", port), handler) as httpd:
                        httpd.allow_reuse_address = True
                        logger.info(f"✅ 前端服务器启动成功 (备用方式): http://localhost:{port}")
                        
                        # 自动打开浏览器
                        try:
                            webbrowser.open(f'http://localhost:{port}')
                            logger.info(f"🚀 已自动打开浏览器: http://localhost:{port}")
                        except Exception as e:
                            logger.warning(f"无法自动打开浏览器: {e}")
                            logger.info(f"请手动访问: http://localhost:{port}")
                        
                        # 启动服务器
                        httpd.serve_forever()
                        
                except Exception as e:
                    logger.error(f"备用服务器启动失败: {e}")
                finally:
                    # 恢复工作目录
                    try:
                        os.chdir(original_dir)
                    except:
                        pass
                        
            except Exception as e:
                logger.error(f"备用前端启动失败: {e}")
        
        # 在新线程中启动
        fallback_thread = threading.Thread(target=run_simple_server, daemon=True)
        fallback_thread.start()
        
    except Exception as e:
        logger.error(f"备用前端启动方式也失败了: {e}")
        logger.info("请手动启动前端服务器:")
        logger.info(f"cd {frontend_dir}")
        logger.info(f"python -m http.server {port}")

def start_flask():
    """启动Flask API服务器"""
    import sys
    import traceback
    
    try:
        from api.api_server import app, init_db
        from config import get_api_server_config
        
        init_db()
        logger.info("启动Flask API服务器...")
        
        # 初始化并自动启动消息转发服务（如果可用）
        logger.info("=" * 60)
        logger.info("开始初始化消息转发服务...")
        logger.info("=" * 60)
        
        try:
            # 检查消息转发模块是否可用
            try:
                from core.message_forward.api_service import MessageForwardAPIService
                from database.db import get_db_pool
                import asyncio
                import threading
                MESSAGE_FORWARD_AVAILABLE = True
                logger.info("✓ 消息转发模块导入成功")
            except ImportError as import_error:
                logger.error(f"✗ 消息转发模块导入失败: {import_error}")
                MESSAGE_FORWARD_AVAILABLE = False
            
            if MESSAGE_FORWARD_AVAILABLE:
                # 获取数据库连接池
                logger.info("正在获取数据库连接池...")
                db_pool = get_db_pool()
                if db_pool:
                    logger.info("✓ 数据库连接池获取成功")
                    
                    # 创建消息转发服务实例
                    logger.info("正在创建消息转发服务实例...")
                    service = MessageForwardAPIService(db_pool)
                    logger.info("✓ 消息转发服务实例创建成功")
                    
                    # 创建后台事件循环用于消息转发服务
                    logger.info("正在创建后台事件循环...")
                    loop = asyncio.new_event_loop()
                    
                    def run_event_loop_in_thread(loop):
                        """在后台线程中持续运行事件循环"""
                        asyncio.set_event_loop(loop)
                        loop.run_forever()
                    
                    # 启动后台线程
                    event_loop_thread = threading.Thread(
                        target=run_event_loop_in_thread, 
                        args=(loop,), 
                        daemon=True,
                        name="MessageForwardEventLoop"
                    )
                    event_loop_thread.start()
                    logger.info("✓ 后台事件循环线程已启动")
                    
                    # 在后台事件循环中启动服务
                    logger.info("正在启动消息转发服务...")
                    try:
                        future = asyncio.run_coroutine_threadsafe(service.start_service(), loop)
                        # 增加超时时间到60秒，因为平台连接（如Telegram）可能需要较长时间
                        result = future.result(timeout=60)  # 等待最多60秒
                        
                        if result.get('success'):
                            logger.info("✓ 消息转发服务启动成功")
                            
                            # 将服务实例和事件循环注册到全局，供 api_server.py 使用
                            logger.info("正在注册服务到全局变量...")
                            import api.api_server as api_server_module
                            api_server_module._message_forward_service = service
                            api_server_module._message_forward_loop = loop
                            
                            # 验证注册成功
                            if api_server_module._message_forward_service is not None:
                                logger.info("✓ 服务注册成功，全局变量已设置")
                            else:
                                logger.error("✗ 服务注册失败，全局变量为 None")
                        else:
                            logger.error(f"✗ 消息转发服务启动失败: {result.get('message')}")
                    except TimeoutError:
                        logger.warning("⚠️ 消息转发服务启动超时（60秒），但服务可能在后台继续启动中...")
                        logger.warning("⚠️ 建议通过API接口检查服务状态，或查看日志了解详细启动进度")
                        # 即使超时，也尝试注册服务，因为服务可能在后台继续启动
                        try:
                            import api.api_server as api_server_module
                            api_server_module._message_forward_service = service
                            api_server_module._message_forward_loop = loop
                            logger.info("✓ 已注册服务到全局变量（尽管启动可能仍在进行中）")
                        except Exception as reg_error:
                            logger.error(f"✗ 注册服务失败: {reg_error}")
                    except Exception as start_error:
                        logger.error(f"✗ 消息转发服务启动异常: {start_error}")
                        import traceback
                        logger.error(traceback.format_exc())
                else:
                    logger.error("✗ 数据库连接池不可用，消息转发服务将无法使用")
            else:
                logger.warning("消息转发模块不可用，相关功能将被禁用")
                
        except Exception as e:
            logger.error(f"✗ 消息转发服务初始化失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
        
        logger.info("=" * 60)
        logger.info("消息转发服务初始化流程结束")
        logger.info("=" * 60)
        
        api_config = get_api_server_config()
        
        # 设置未捕获异常处理器
        def handle_exception(exc_type, exc_value, exc_traceback):
            """处理未捕获的异常"""
            if issubclass(exc_type, KeyboardInterrupt):
                sys.__excepthook__(exc_type, exc_value, exc_traceback)
                return
            
            logger.critical(
                f"[Flask未捕获异常] {exc_type.__name__}: {exc_value}\n"
                f"{''.join(traceback.format_exception(exc_type, exc_value, exc_traceback))}"
            )
        
        sys.excepthook = handle_exception
        
        # 启动 Flask（不使用 daemon 模式，确保服务稳定）
        logger.info(f"Flask 服务器启动在 {api_config['host']}:{api_config['port']}")
        app.run(
            host=api_config['host'],
            port=api_config['port'],
            debug=api_config['debug'],
            use_reloader=False,
            threaded=api_config['threaded'],
            processes=1,  # 不使用多进程，避免问题
            passthrough_errors=False  # 让 Flask 处理所有错误
        )
    except KeyboardInterrupt:
        # 静默处理 Ctrl+C，避免打印大量错误堆栈
        logger.info("Flask API服务器收到停止信号")
        sys.exit(0)
    except Exception as e:
        logger.critical(f"[Flask启动失败] {e}\n{traceback.format_exc()}")
        sys.exit(1)

def start_trade():
    """启动交易服务（包含限价跟单监控）"""
    try:
        logger.info("🚀 启动交易服务和限价跟单监控...")
        
        # 在后台线程启动限价跟单监控
        limit_follow_thread = threading.Thread(target=start_limit_follow_background, daemon=True)
        limit_follow_thread.start()
        logger.info("✅ 限价跟单监控已在后台启动")
        
        # 等待一下确保监控启动
        time.sleep(2)
        
        # 启动主要交易服务
        from core.market_trade.trade_server import start_trade as trade_start
        trade_start()
        
    except KeyboardInterrupt:
        # 静默处理 Ctrl+C，避免打印大量错误堆栈
        logger.info("交易服务收到停止信号")
        sys.exit(0)
    except Exception as e:
        logger.error(f"启动交易服务失败: {e}")
        sys.exit(1)

def start_limit_follow_background():
    """后台启动限价跟单监控"""
    try:
        logger.info("🔄 初始化限价跟单监控服务...")
        time.sleep(5)  # 等待主服务启动
        
        from core.limit_trade.limit_follow_service import get_limit_follow_service
        service = get_limit_follow_service()
        
        # 启动监控
        import asyncio
        asyncio.run(service.start_monitoring())
        
    except Exception as e:
        logger.error(f"限价跟单监控启动失败: {e}")
        # 如果监控启动失败，尝试重新启动
        try:
            logger.info("🔄 尝试重新启动限价跟单监控...")
            time.sleep(15)  # 增加等待时间
            from core.limit_trade.limit_follow_service import get_limit_follow_service
            service = get_limit_follow_service()
            import asyncio
            asyncio.run(service.start_monitoring())
        except Exception as retry_error:
            logger.error(f"重新启动限价跟单监控失败: {retry_error}")

def start_strategy_trade():
    """启动策略交易模块（仅回测，不含实盘）"""
    logger.info("正在启动策略交易模块...")
    try:
        import asyncio
        from core.strategy_trade.core.manager import StrategyManager
        from database.db import get_db_pool
        
        def run_strategy_trade():
            try:
                # 导入策略类
                from core.strategy_trade.strategies.technical.ma_cross import MACrossStrategy
                from core.strategy_trade.strategies.technical.rsi import RSIStrategy
                from core.strategy_trade.strategies.technical.macd import MACDStrategy
                from core.strategy_trade.strategies.technical.bollinger import BollingerStrategy
                from core.strategy_trade.strategies.advanced.grid import GridStrategy
                from core.strategy_trade.strategies.advanced.high_frequency import HighFrequencyStrategy
                
                # 创建策略管理器
                strategy_manager = StrategyManager()
                
                # 注册策略类型
                strategy_manager.register_strategy_type('MA_Cross_Strategy', MACrossStrategy)
                strategy_manager.register_strategy_type('RSI_Strategy', RSIStrategy)
                strategy_manager.register_strategy_type('MACD_Strategy', MACDStrategy)
                strategy_manager.register_strategy_type('Bollinger_Strategy', BollingerStrategy)
                strategy_manager.register_strategy_type('Grid_Strategy', GridStrategy)
                strategy_manager.register_strategy_type('High_Frequency_Strategy', HighFrequencyStrategy)
                
                logger.info("策略交易模块启动成功")
                
                # 保持运行
                try:
                    while True:
                        import time
                        time.sleep(1)
                except KeyboardInterrupt:
                    logger.info("策略交易模块接收到停止信号")
                    
            except Exception as e:
                logger.error(f"策略交易模块运行失败: {e}")
                raise
        
        # 运行策略交易模块
        run_strategy_trade()
        
    except KeyboardInterrupt:
        # 静默处理 Ctrl+C，避免打印大量错误堆栈
        logger.info("策略交易模块收到停止信号")
        sys.exit(0)
    except Exception as e:
        logger.error(f"策略交易模块启动失败: {e}")
        sys.exit(1)

def start_unified_api_server():
    """启动统一的API服务器（包含所有功能）"""
    try:
        logger.info("启动统一API服务器...")
        
        # 启动服务监控
        try:
            from core.service_monitor import start_service_monitoring, get_service_monitor
            monitor = start_service_monitoring()
            
            # 注册 Flask API 服务健康检查
            def check_flask_health():
                try:
                    import urllib.request
                    response = urllib.request.urlopen('http://127.0.0.1:5001/health', timeout=2)
                    return response.getcode() == 200
                except:
                    return False
            
            monitor.register_service(
                name='flask_api',
                health_check=check_flask_health,
                restart_func=lambda: logger.warning("[服务监控] Flask API 需要手动重启"),
                critical=True
            )
            logger.info("[服务监控] Flask API 服务已注册到监控器")
        except Exception as e:
            logger.warning(f"[服务监控] 服务监控模块不可用: {e}")
        
        # 启动API服务器（使用 daemon=True，确保主进程退出时线程也会终止）
        api_thread = threading.Thread(target=start_flask, daemon=True, name="FlaskAPIServer")
        api_thread.start()
        logger.info("统一API服务器启动成功")
        
        # 监控 API 线程状态
        def monitor_api_thread():
            while True:
                time.sleep(10)
                if not api_thread.is_alive():
                    logger.critical("[Flask监控] API 服务器线程已停止！尝试重启...")
                    try:
                        new_thread = threading.Thread(target=start_flask, daemon=False, name="FlaskAPIServer")
                        new_thread.start()
                        logger.info("[Flask监控] API 服务器已重启")
                    except Exception as e:
                        logger.critical(f"[Flask监控] 重启失败: {e}")
        
        monitor_thread = threading.Thread(target=monitor_api_thread, daemon=True, name="FlaskMonitor")
        monitor_thread.start()
        logger.info("[Flask监控] API 服务器监控线程已启动")
        
        # 等待API服务器启动
        time.sleep(2)
        
        # 启动限价跟单监控器
        limit_follow_thread = threading.Thread(target=start_limit_follow_background, daemon=True)
        limit_follow_thread.start()
        logger.info("✅ 限价跟单监控已在后台启动")
        
        # 保持服务运行
        while True:
            time.sleep(5)
            
    except KeyboardInterrupt:
        logger.info("统一API服务器收到中断信号，正在停止...")
        sys.exit(0)
    except Exception as e:
        logger.error(f"统一API服务器启动失败: {e}")
        sys.exit(1)

def start_market_maker():
    """启动刷单/做市模块"""
    from core.market_maker.process_manager import MarketMakerProcessManager
    import signal
    
    logger.info("🚀 启动刷单/做市模块...")
    
    # 创建进程管理器
    manager = MarketMakerProcessManager()
    
    # 注册信号处理
    def signal_handler(sig, frame):
        logger.info("\n[刷单模块] 收到停止信号，正在关闭...")
        manager.stop_all()
        sys.exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    if hasattr(signal, 'SIGTERM'):
        signal.signal(signal.SIGTERM, signal_handler)
    
    # 启动所有账号
    if not manager.start_all():
        logger.error("启动刷单模块失败：没有找到账号配置")
        logger.info("请创建配置文件: market_maker_accounts.json")
        return
    
    logger.info("[刷单模块] 所有账号已启动，按 Ctrl+C 停止")
    
    try:
        # 监控进程状态
        manager.monitor()
    except KeyboardInterrupt:
        logger.info("\n[刷单模块] 收到键盘中断，正在关闭...")
        manager.stop_all()

def start_limit_follow():
    """启动限价跟单服务（仅监控，不启动API）"""
    try:
        logger.info("启动限价跟单监控器...")
        
        # 启动跟单监控器
        monitor_thread = threading.Thread(target=start_follow_monitor, daemon=True)
        monitor_thread.start()
        logger.info("跟单监控器启动成功")
        
        # 保持服务运行
        while True:
            time.sleep(5)
            
    except KeyboardInterrupt:
        logger.info("限价跟单服务收到中断信号，正在停止...")
    except Exception as e:
        logger.error(f"限价跟单服务启动失败: {e}")

def start_follow_monitor():
    """启动跟单监控器"""
    try:
        from core.limit_trade.limit_follow_executor import LimitFollowExecutor
        from database.global_db_manager import get_global_db_pool
        
        # 使用全局数据库连接池
        db_pool = get_global_db_pool()
        logger.info("🎯 跟单监控器使用全局数据库连接池")
        
        # 创建跟单执行器
        executor = LimitFollowExecutor(db_pool)
        
        # 开始监控
        import asyncio
        asyncio.run(executor.run_monitoring_async())
        
    except Exception as e:
        logger.error(f"跟单监控器启动失败: {e}")

def start_limit_follow_monitor_only():
    """仅启动限价跟单监控器（不启动API服务器）"""
    try:
        logger.info("启动限价跟单监控器...")
        
        from core.limit_trade.limit_follow_executor import LimitFollowExecutor
        from database.global_db_manager import get_global_db_pool
        
        # 使用全局数据库连接池
        db_pool = get_global_db_pool()
        logger.info("🎯 限价跟单监控器使用全局数据库连接池")
        
        # 创建跟单执行器
        executor = LimitFollowExecutor(db_pool)
        
        # 开始监控
        import asyncio
        asyncio.run(executor.run_monitoring_async())
        
    except KeyboardInterrupt:
        logger.info("跟单监控器收到中断信号，正在停止...")
    except Exception as e:
        logger.error(f"跟单监控器启动失败: {e}")

def print_usage():
    """打印使用说明"""
    print("""
OKX交易所自动跟单系统启动器

使用方法:
    python main.py [模式] [选项]

模式:
    trade                    - 仅启动交易模块（包含限价跟单监控）
    strategy                 - 仅启动策略交易模块（回测）
    api                      - 启动统一API服务器（包含策略实盘服务）🆕
    limit-follow             - 仅启动限价跟单监控器
    all                      - 同时启动所有模块和前端界面 (默认)
    frontend                 - 仅启动前端界面
    help                     - 显示此帮助信息

选项:
    --demo                   - 使用模拟盘环境
    --real                   - 使用实盘环境
    --no-frontend            - 不启动前端界面

示例:
    python main.py trade --demo                    # 仅启动交易模块(模拟盘)
    python main.py strategy --demo                 # 仅启动策略交易模块(回测)
    python main.py api --demo                      # 启动API服务器(包含策略实盘) 🆕
    python main.py limit-follow                    # 仅启动跟单监控器
    python main.py market-maker                    # 仅启动刷单/做市模块
    python main.py all --real                      # 同时启动所有模块(实盘)
    python main.py all --demo --no-frontend        # 启动后端，不启动前端
    python main.py frontend                        # 仅启动前端界面
    python main.py                                 # 同时启动所有模块(默认模式)
    """)

def main():
    # 优化系统资源
    optimize_system_resources()
    
    # 解析命令行参数
    args = sys.argv[1:] if len(sys.argv) > 1 else ['all']
    mode = args[0].lower() if args else 'all'
    
    # 检查是否为帮助模式
    if mode in ['help', '-h', '--help']:
        print_usage()
        return
    
    # 解析交易模式
    trade_mode = None
    start_frontend_flag = True
    
    if '--demo' in args:
        trade_mode = 'demo'
    elif '--real' in args:
        trade_mode = 'real'
    
    if '--no-frontend' in args:
        start_frontend_flag = False
    
    # 设置交易模式
    if trade_mode:
        if trade_mode == 'real':
            set_global_is_demo(0)
            os.environ['IS_DEMO'] = '0'
            print("当前使用实盘交易环境，请关注资金安全！")
        elif trade_mode == 'demo':
            set_global_is_demo(1)
            os.environ['IS_DEMO'] = '1'
            print("当前使用模拟盘交易环境。")
    else:
        # 默认检查环境变量
        if os.environ.get('TRADE_MODE'):
            mode_env = os.environ['TRADE_MODE'].strip().lower()
            if mode_env == 'real':
                set_global_is_demo(0)
                os.environ['IS_DEMO'] = '0'
            elif mode_env == 'demo':
                set_global_is_demo(1)
                os.environ['IS_DEMO'] = '1'
        
        if get_global_is_demo():
            print("当前使用模拟盘交易环境。")
        else:
            print("当前使用实盘交易环境，请关注资金安全！")
    
    # 根据模式启动相应服务
    if mode == 'trade':
        logger.info("�� 启动交易模块...")
        start_trade()
    elif mode == 'strategy':
        logger.info("🚀 启动策略交易模块（回测）...")
        start_strategy_trade()
    elif mode == 'api':
        logger.info("🚀 启动统一API服务器...")
        start_unified_api_server()
    elif mode == 'limit-follow':
        logger.info("�� 启动限价跟单监控器...")
        start_limit_follow()
    elif mode == 'market-maker':
        logger.info("🚀 启动刷单/做市模块...")
        start_market_maker()
    elif mode == 'frontend':
        logger.info("🚀 启动前端界面...")
        start_frontend()
        # 保持程序运行
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            logger.info("收到中断信号，正在关闭...")
    elif mode == 'all':
        logger.info("🚀 同时启动所有模块和前端界面...")
        
        # 启动前端（如果启用）
        if start_frontend_flag:
            logger.info("启动前端界面...")
            start_frontend()
        
        # 启动三个后端进程（恢复多进程架构）
        p1 = Process(target=start_flask)  # API服务器（包含消息转发服务）
        p2 = Process(target=start_trade)  # 交易模块（包含限价跟单监控）
        p3 = Process(target=start_strategy_trade)  # 策略交易模块
        
        p1.start()
        p2.start()
        p3.start()
        
        try:
            # 等待所有子进程
            p1.join()
            p2.join()
            p3.join()
        except KeyboardInterrupt:
            logger.info("收到中断信号，正在关闭...")
            for p in (p1, p2, p3):
                try:
                    p.terminate()
                except Exception:
                    pass
            for p in (p1, p2, p3):
                try:
                    p.join(timeout=5)
                except Exception:
                    pass
        finally:
            logger.info("程序退出，资源清理完成")
            # 强制退出，确保所有线程和进程都被终止
            sys.exit(0)
    else:
        print(f"错误: 未知模式 '{mode}'")
        print_usage()
        sys.exit(1)

if __name__ == '__main__':
    main()