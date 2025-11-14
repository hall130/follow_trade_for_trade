#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
服务监控和自动恢复模块
提供高可用性保障：自动检测服务健康状态、自动重启、资源监控
"""

import time
import threading
import psutil
import os
import sys
import signal
import subprocess
from typing import Dict, Optional, Callable
from utils.logger import logger
from datetime import datetime


class ServiceMonitor:
    """服务监控器 - 提供高可用性保障"""
    
    def __init__(self, check_interval: int = 30, max_restart_attempts: int = 5):
        """
        初始化服务监控器
        
        Args:
            check_interval: 健康检查间隔（秒）
            max_restart_attempts: 最大重启尝试次数（24小时内）
        """
        self.check_interval = check_interval
        self.max_restart_attempts = max_restart_attempts
        self.monitored_services: Dict[str, Dict] = {}
        self.restart_history: Dict[str, list] = {}
        self.is_running = False
        self.monitor_thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()
        
        # 资源阈值配置
        self.memory_warning_threshold = 1024 * 1024 * 1024  # 1GB
        self.memory_critical_threshold = 2 * 1024 * 1024 * 1024  # 2GB
        self.cpu_warning_threshold = 80.0  # 80%
        self.cpu_critical_threshold = 95.0  # 95%
        
    def register_service(
        self, 
        name: str, 
        health_check: Callable[[], bool],
        restart_func: Optional[Callable[[], None]] = None,
        critical: bool = True
    ):
        """
        注册需要监控的服务
        
        Args:
            name: 服务名称
            health_check: 健康检查函数，返回 True 表示健康
            restart_func: 重启函数（可选）
            critical: 是否为关键服务（关键服务失败会触发重启）
        """
        with self._lock:
            self.monitored_services[name] = {
                'health_check': health_check,
                'restart_func': restart_func,
                'critical': critical,
                'last_check': None,
                'last_status': None,
                'failure_count': 0,
                'last_failure_time': None
            }
            self.restart_history[name] = []
            logger.info(f"[服务监控] 已注册服务: {name} (关键服务: {critical})")
    
    def start(self):
        """启动监控"""
        if self.is_running:
            logger.warning("[服务监控] 监控已在运行")
            return
        
        self.is_running = True
        self.monitor_thread = threading.Thread(
            target=self._monitor_loop,
            daemon=True,
            name="ServiceMonitor"
        )
        self.monitor_thread.start()
        logger.info("[服务监控] 服务监控器已启动")
    
    def stop(self):
        """停止监控"""
        self.is_running = False
        if self.monitor_thread:
            self.monitor_thread.join(timeout=5)
        logger.info("[服务监控] 服务监控器已停止")
    
    def _monitor_loop(self):
        """监控循环"""
        while self.is_running:
            try:
                # 检查系统资源
                self._check_system_resources()
                
                # 检查所有注册的服务
                with self._lock:
                    for name, service_info in self.monitored_services.items():
                        self._check_service(name, service_info)
                
                # 等待下次检查
                time.sleep(self.check_interval)
                
            except Exception as e:
                logger.error(f"[服务监控] 监控循环异常: {e}")
                time.sleep(self.check_interval)
    
    def _check_system_resources(self):
        """检查系统资源使用情况"""
        try:
            process = psutil.Process(os.getpid())
            
            # 检查内存使用
            memory_info = process.memory_info()
            memory_mb = memory_info.rss / 1024 / 1024
            
            if memory_mb > self.memory_critical_threshold / 1024 / 1024:
                logger.critical(f"[服务监控] 内存使用严重警告: {memory_mb:.2f} MB")
                # 可以触发GC或清理操作
                import gc
                gc.collect()
            elif memory_mb > self.memory_warning_threshold / 1024 / 1024:
                logger.warning(f"[服务监控] 内存使用警告: {memory_mb:.2f} MB")
            
            # 检查CPU使用
            cpu_percent = process.cpu_percent(interval=1)
            if cpu_percent > self.cpu_critical_threshold:
                logger.critical(f"[服务监控] CPU使用严重警告: {cpu_percent:.2f}%")
            elif cpu_percent > self.cpu_warning_threshold:
                logger.warning(f"[服务监控] CPU使用警告: {cpu_percent:.2f}%")
                
        except Exception as e:
            logger.error(f"[服务监控] 资源检查失败: {e}")
    
    def _check_service(self, name: str, service_info: Dict):
        """检查单个服务"""
        try:
            health_check = service_info['health_check']
            is_healthy = health_check()
            
            service_info['last_check'] = datetime.now()
            service_info['last_status'] = is_healthy
            
            if not is_healthy:
                service_info['failure_count'] += 1
                service_info['last_failure_time'] = datetime.now()
                
                logger.warning(f"[服务监控] 服务 {name} 健康检查失败 (失败次数: {service_info['failure_count']})")
                
                # 如果是关键服务且失败次数达到阈值，尝试重启
                if service_info['critical'] and service_info['failure_count'] >= 3:
                    self._attempt_restart(name, service_info)
            else:
                # 健康时重置失败计数
                if service_info['failure_count'] > 0:
                    logger.info(f"[服务监控] 服务 {name} 已恢复健康")
                    service_info['failure_count'] = 0
                    
        except Exception as e:
            logger.error(f"[服务监控] 检查服务 {name} 时异常: {e}")
    
    def _attempt_restart(self, name: str, service_info: Dict):
        """尝试重启服务"""
        # 检查24小时内的重启次数
        now = datetime.now()
        recent_restarts = [
            restart_time for restart_time in self.restart_history[name]
            if (now - restart_time).total_seconds() < 86400  # 24小时
        ]
        
        if len(recent_restarts) >= self.max_restart_attempts:
            logger.critical(
                f"[服务监控] 服务 {name} 在24小时内已重启 {len(recent_restarts)} 次，"
                f"达到最大限制 {self.max_restart_attempts}，停止自动重启"
            )
            return
        
        logger.warning(f"[服务监控] 尝试重启服务: {name}")
        
        try:
            restart_func = service_info.get('restart_func')
            if restart_func:
                restart_func()
                self.restart_history[name].append(now)
                service_info['failure_count'] = 0
                logger.info(f"[服务监控] 服务 {name} 重启成功")
            else:
                logger.warning(f"[服务监控] 服务 {name} 没有配置重启函数")
        except Exception as e:
            logger.error(f"[服务监控] 重启服务 {name} 失败: {e}")
    
    def get_service_status(self) -> Dict:
        """获取所有服务的状态"""
        with self._lock:
            status = {}
            for name, service_info in self.monitored_services.items():
                status[name] = {
                    'healthy': service_info['last_status'],
                    'last_check': service_info['last_check'].isoformat() if service_info['last_check'] else None,
                    'failure_count': service_info['failure_count'],
                    'last_failure': service_info['last_failure_time'].isoformat() if service_info['last_failure_time'] else None,
                    'restart_count_24h': len([
                        t for t in self.restart_history[name]
                        if (datetime.now() - t).total_seconds() < 86400
                    ])
                }
            return status


# 全局监控器实例
_global_monitor: Optional[ServiceMonitor] = None


def get_service_monitor() -> ServiceMonitor:
    """获取全局服务监控器（单例）"""
    global _global_monitor
    if _global_monitor is None:
        _global_monitor = ServiceMonitor()
    return _global_monitor


def start_service_monitoring():
    """启动服务监控"""
    monitor = get_service_monitor()
    monitor.start()
    return monitor

