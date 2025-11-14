#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Gunicorn 配置文件
用于生产环境部署 Flask API 服务
"""

import multiprocessing
import os

# 服务器配置
bind = "127.0.0.1:5001"
# 如果使用 gevent，建议只用 1 个 worker（单进程多协程）
# 如果使用 sync，可以使用多个 worker（多进程）
worker_class = "gevent"  # gevent: 单进程多协程（避免多进程问题）| sync: 多进程（需要 preload_app=False）
workers = 1  # gevent 模式下使用单进程，通过协程处理并发
worker_connections = 1000
timeout = 120
keepalive = 5

# 日志配置
# 使用项目目录下的 logs 目录，避免权限问题
log_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'logs', 'gunicorn')
os.makedirs(log_dir, exist_ok=True)
accesslog = os.path.join(log_dir, "gunicorn_access.log")
errorlog = os.path.join(log_dir, "gunicorn_error.log")
loglevel = "info"
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s" %(D)s'

# 进程管理
daemon = False
pidfile = "/var/run/follow-trade-api.pid"
umask = 0o007
user = None  # 如果以 root 运行，可以设置为非 root 用户
group = None

# 性能优化
preload_app = False  # 禁用预加载，避免多进程共享状态问题，更安全
max_requests = 1000  # 每个 worker 处理 1000 个请求后重启，防止内存泄漏
max_requests_jitter = 50

# 优雅重启
graceful_timeout = 30

# 进程名称
proc_name = "follow-trade-api"

def when_ready(server):
    """服务器准备就绪时的回调"""
    server.log.info("Follow Trade API 服务器已启动")

def on_exit(server):
    """服务器退出时的回调"""
    server.log.info("Follow Trade API 服务器已停止")

