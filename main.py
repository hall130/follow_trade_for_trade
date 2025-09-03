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

def start_frontend():
    """启动前端Web服务器"""
    try:
        import subprocess
        import os
        import sys
        
        # 检查frontend目录是否存在
        frontend_dir = os.path.join(os.path.dirname(__file__), 'frontend')
        if not os.path.exists(frontend_dir):
            logger.warning(f"前端目录不存在: {frontend_dir}")
            return
        
        # 查找可用端口
        port = 8080
        while port < 8090:
            try:
                # 检查端口是否可用
                import socket
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
        logger.info(f"📁 前端目录: {os.path.abspath(frontend_dir)}")
        
        # 使用subprocess启动前端服务器
        def run_frontend_server():
            try:
                # 切换到前端目录
                os.chdir(frontend_dir)
                
                # 启动HTTP服务器
                if sys.platform.startswith('win'):
                    # Windows系统
                    cmd = [sys.executable, '-m', 'http.server', str(port)]
                else:
                    # Unix/Linux系统
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
        
        # 使用更简单的方式启动
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
    from api.api_server import app, init_db
    from config import get_api_server_config
    
    init_db()
    logger.info("启动Flask API服务器...")
    api_config = get_api_server_config()
    
    app.run(
        host=api_config['host'],
        port=api_config['port'],
        debug=api_config['debug'],
        use_reloader=False,
        threaded=api_config['threaded'],
        processes=api_config['processes']
    )

def start_trade():
    """启动交易服务"""
    from core.market_trade.trade_server import start_trade as trade_start
    trade_start()

def start_unified_api_server():
    """启动统一的API服务器（包含所有功能）"""
    try:
        logger.info("启动统一API服务器...")
        
        # 启动API服务器
        api_thread = threading.Thread(target=start_flask, daemon=True)
        api_thread.start()
        logger.info("统一API服务器启动成功")
        
        # 等待API服务器启动
        time.sleep(2)
        
        # 启动跟单监控器
        monitor_thread = threading.Thread(target=start_follow_monitor, daemon=True)
        monitor_thread.start()
        logger.info("跟单监控器启动成功")
        
        # 保持服务运行
        while True:
            time.sleep(5)
            
    except KeyboardInterrupt:
        logger.info("统一API服务器收到中断信号，正在停止...")
    except Exception as e:
        logger.error(f"统一API服务器启动失败: {e}")

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
        from database.db import MySQLPool
        from config import get_mysql_config
        # 初始化数据库连接
        db_pool = MySQLPool(
            **get_mysql_config()
        )
        
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
        from config import get_mysql_config
        # 初始化数据库连接
        db_pool = MySQLPool(
            **get_mysql_config()
        )
        
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
    trade                    - 仅启动交易模块
    api                      - 启动统一API服务器（包含所有功能）
    limit-follow             - 仅启动限价跟单监控器
    all                      - 同时启动交易模块、统一API服务器和前端界面 (默认)
    frontend                 - 仅启动前端界面
    help                     - 显示此帮助信息

选项:
    --demo                   - 使用模拟盘环境
    --real                   - 使用实盘环境
    --no-frontend            - 不启动前端界面

示例:
    python main.py trade --demo                    # 仅启动交易模块(模拟盘)
    python main.py api                             # 启动统一API服务器
    python main.py limit-follow                    # 仅启动跟单监控器
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
        logger.info("🚀 启动交易模块...")
        start_trade()
    elif mode == 'api':
        logger.info("🚀 启动统一API服务器...")
        start_unified_api_server()
    elif mode == 'limit-follow':
        logger.info("🚀 启动限价跟单监控器...")
        start_limit_follow()
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
        logger.info("🚀 同时启动交易模块、统一API服务器和前端界面...")
        
        # 启动前端（如果启用）
        if start_frontend_flag:
            logger.info("🌐 启动前端界面...")
            start_frontend()
        
        # 启动两个后端进程
        p1 = Process(target=start_flask)  # 统一API服务器
        p2 = Process(target=start_trade)  # 交易模块
        
        p1.start()
        p2.start()
        
        try:
            p1.join()
            p2.join()
        except KeyboardInterrupt:
            logger.info("收到中断信号，正在关闭...")
            for p in (p1, p2):
                try:
                    p.terminate()
                except Exception:
                    pass
            for p in (p1, p2):
                try:
                    p.join()
                except Exception:
                    pass
        finally:
            logger.info("程序退出，资源清理完成")
    else:
        print(f"错误: 未知模式 '{mode}'")
        print_usage()
        sys.exit(1)

if __name__ == '__main__':
    main()
