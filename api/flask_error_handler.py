#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Flask 全局错误处理和健康检查
"""

import traceback
import sys
import threading
import time
from functools import wraps
from utils.logger import logger


def setup_flask_error_handlers(app):
    """设置 Flask 全局错误处理器"""
    from flask import request, jsonify
    
    @app.errorhandler(Exception)
    def handle_exception(e):
        """全局异常处理器"""
        logger.error(f"[Flask全局异常] 未捕获的异常: {e}")
        logger.error(f"[Flask全局异常] 异常类型: {type(e).__name__}")
        logger.error(f"[Flask全局异常] 堆栈跟踪:\n{traceback.format_exc()}")
        
        # 返回友好的错误响应
        return jsonify({
            'success': False,
            'message': f'服务器内部错误: {str(e)}',
            'error_type': type(e).__name__
        }), 500
    
    @app.errorhandler(500)
    def handle_500(e):
        """500 错误处理器"""
        logger.error(f"[Flask 500错误] {e}")
        logger.error(f"[Flask 500错误] 堆栈跟踪:\n{traceback.format_exc()}")
        return jsonify({
            'success': False,
            'message': '服务器内部错误',
            'error': str(e)
        }), 500
    
    @app.errorhandler(404)
    def handle_404(e):
        """404 错误处理器"""
        logger.warning(f"[Flask 404错误] {request.path}")
        return jsonify({
            'success': False,
            'message': '接口不存在',
            'path': request.path
        }), 404
    
    logger.info("[Flask错误处理] 全局错误处理器已设置")


def monitor_flask_health(app):
    """监控 Flask 应用健康状态"""
    def health_check():
        while True:
            try:
                time.sleep(60)  # 每分钟检查一次
                
                # 检查线程状态
                active_threads = threading.active_count()
                logger.debug(f"[Flask健康检查] 活跃线程数: {active_threads}")
                
                # 检查应用上下文
                if not app:
                    logger.error("[Flask健康检查] Flask 应用对象丢失！")
                
            except Exception as e:
                logger.error(f"[Flask健康检查] 健康检查失败: {e}")
                time.sleep(60)
    
    health_thread = threading.Thread(target=health_check, daemon=True, name="FlaskHealthMonitor")
    health_thread.start()
    logger.info("[Flask健康检查] 健康监控线程已启动")


def safe_async_call(func):
    """安全的异步调用装饰器，确保事件循环正确管理"""
    @wraps(func)
    def wrapper(*args, **kwargs):
        import asyncio
        try:
            # 尝试获取当前事件循环
            try:
                loop = asyncio.get_event_loop()
                if loop.is_closed():
                    raise RuntimeError("Event loop is closed")
            except RuntimeError:
                # 如果没有事件循环或已关闭，创建新的
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
            
            # 运行异步函数
            if loop.is_running():
                # 如果循环正在运行，在专用线程中运行
                import concurrent.futures
                future = concurrent.futures.Future()
                def run_in_thread():
                    # 在新线程中创建新的事件循环
                    new_loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(new_loop)
                    try:
                        result = new_loop.run_until_complete(func(*args, **kwargs))
                        future.set_result(result)
                    except Exception as e:
                        future.set_exception(e)
                    finally:
                        new_loop.close()
                
                thread = threading.Thread(target=run_in_thread, daemon=True)
                thread.start()
                thread.join(timeout=30)  # 30秒超时
                
                if thread.is_alive():
                    raise TimeoutError("异步调用超时")
                
                return future.result()
            else:
                # 事件循环存在但未运行
                # 为了安全，也在专用线程中运行（避免 gevent 相关问题）
                import concurrent.futures
                future = concurrent.futures.Future()
                def run_in_thread():
                    new_loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(new_loop)
                    try:
                        result = new_loop.run_until_complete(func(*args, **kwargs))
                        future.set_result(result)
                    except Exception as e:
                        future.set_exception(e)
                    finally:
                        new_loop.close()
                thread = threading.Thread(target=run_in_thread, daemon=True)
                thread.start()
                thread.join(timeout=30)
                if thread.is_alive():
                    raise TimeoutError("异步调用超时")
                return future.result()
                
        except Exception as e:
            logger.error(f"[安全异步调用] 执行失败: {e}")
            logger.error(f"[安全异步调用] 堆栈跟踪:\n{traceback.format_exc()}")
            raise
    
    return wrapper

