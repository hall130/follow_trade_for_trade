#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Telegram 7x24小时消息监听与转发服务启动脚本
"""

import asyncio
import sys
import os
import json
import signal
from pathlib import Path
import time

# 添加项目根目录到Python路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from core.message_forward.telegram_listener_service import TelegramListenerService
from utils.logger import get_logger

logger = get_logger(__name__)

# 全局服务实例
service: TelegramListenerService = None

def signal_handler(signum, frame):
    """信号处理函数"""
    logger.info(f"收到信号 {signum}，正在停止服务...")
    if service:
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                loop.create_task(service.stop())
            else:
                asyncio.run(service.stop())
        except Exception as e:
            logger.error(f"停止服务失败: {e}")

async def main():
    """主函数"""
    global service
    
    # 配置文件路径（使用绝对路径）
    config_file = project_root / 'config' / 'telegram_listener_config.json'
    
    # 如果配置文件不存在，尝试使用相对路径
    if not config_file.exists():
        config_file = Path('config') / 'telegram_listener_config.json'
    
    # 如果配置文件不存在，使用示例配置
    if not config_file.exists():
        example_config = project_root / 'config' / 'telegram_listener_config_example.json'
        if example_config.exists():
            logger.warning(f"配置文件不存在，请复制示例配置: {example_config} -> {config_file}")
            logger.warning("并修改其中的配置项")
            return
        else:
            logger.error("配置文件不存在，且示例配置文件也不存在")
            return
    
    # 加载配置
    try:
        with open(config_file, 'r', encoding='utf-8') as f:
            config = json.load(f)
        logger.info(f"✅ 配置文件加载成功: {config_file}")
    except Exception as e:
        logger.error(f"❌ 加载配置文件失败: {e}")
        return
    
    # 创建服务实例
    service = TelegramListenerService(config)
    
    # 设置信号处理（优雅退出）
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # 初始化服务
    logger.info("🚀 正在初始化服务...")
    try:
        if not await service.initialize():
            logger.error("❌ 服务初始化失败")
            # 保存失败状态到文件，方便前端查看
            # 使用项目根目录的绝对路径
            status_file = project_root / "telegram_listener_status.json"
            try:
                status = {
                    'running': False,
                    'stats': {
                        'total_messages': 0,
                        'filtered_messages': 0,
                        'forwarded_messages': 0,
                        'failed_forwards': 0,
                        'start_time': None,
                        'last_message_time': None
                    },
                    'telegram_connected': False,
                    'telegram_authenticated': False,
                    'forward_rules_count': 0,
                    'active_rules_count': 0,
                    'target_platforms_count': 0,
                    'error': '服务初始化失败，请检查日志'
                }
                with open(status_file, 'w', encoding='utf-8') as f:
                    json.dump(status, f, ensure_ascii=False, indent=2, default=str)
            except Exception as e:
                logger.warning(f"保存状态文件失败: {e}")
            return
    except Exception as e:
        logger.error(f"❌ 服务初始化异常: {e}")
        import traceback
        logger.error(traceback.format_exc())
        # 保存异常状态
        # 使用项目根目录的绝对路径
        status_file = project_root / "telegram_listener_status.json"
        try:
            status = {
                'running': False,
                'stats': {
                    'total_messages': 0,
                    'filtered_messages': 0,
                    'forwarded_messages': 0,
                    'failed_forwards': 0,
                    'start_time': None,
                    'last_message_time': None
                },
                'telegram_connected': False,
                'telegram_authenticated': False,
                'forward_rules_count': 0,
                'active_rules_count': 0,
                'target_platforms_count': 0,
                'error': f'服务初始化异常: {str(e)}'
            }
            with open(status_file, 'w', encoding='utf-8') as f:
                json.dump(status, f, ensure_ascii=False, indent=2, default=str)
        except:
            pass
        return
    
    # 保存PID文件
    # 使用项目根目录的绝对路径，确保与管理器使用相同的路径
    pid_file = project_root / "telegram_listener.pid"
    try:
        with open(pid_file, 'w') as f:
            f.write(str(os.getpid()))
        logger.info(f"PID文件已保存: {pid_file} (PID: {os.getpid()})")
    except Exception as e:
        logger.warning(f"保存PID文件失败: {e}")
    
    # 立即创建一个初始状态文件，表示服务正在启动
    # 使用项目根目录的绝对路径，确保与管理器使用相同的路径
    status_file = project_root / "telegram_listener_status.json"
    try:
        initial_status = service.get_status()
        initial_status['running'] = False  # 还未真正运行
        initial_status['starting'] = True  # 标记为正在启动
        with open(status_file, 'w', encoding='utf-8') as f:
            json.dump(initial_status, f, ensure_ascii=False, indent=2, default=str)
        logger.info(f"初始状态文件已创建: {status_file}")
    except Exception as e:
        logger.warning(f"创建初始状态文件失败: {e}")
    
    # 启动服务（7x24小时运行）
    logger.info("✅ 服务初始化成功，开始7x24小时监听...")
    try:
        await service.start()
    except KeyboardInterrupt:
        logger.info("收到中断信号，正在停止服务...")
    except Exception as e:
        logger.error(f"服务运行出错: {e}")
        import traceback
        logger.error(traceback.format_exc())
    finally:
        await service.stop()
        # 删除PID文件
        # 使用项目根目录的绝对路径
        pid_file = project_root / "telegram_listener.pid"
        if pid_file.exists():
            try:
                pid_file.unlink()
                logger.info("PID文件已删除")
            except Exception as e:
                logger.warning(f"删除PID文件失败: {e}")
        logger.info("👋 服务已停止")

if __name__ == "__main__":
    try:
        # 注意：在 Windows 上，不要忽略信号，让程序能正常响应中断
        # 父进程已经使用了 CREATE_NEW_PROCESS_GROUP，子进程可以独立运行
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("用户中断，退出")
    except Exception as e:
        logger.error(f"程序异常退出: {e}")
        import traceback
        logger.error(traceback.format_exc())
        # 确保在异常退出时也清理 PID 文件
        # 使用项目根目录的绝对路径
        pid_file = project_root / "telegram_listener.pid"
        if pid_file.exists():
            try:
                pid_file.unlink()
            except:
                pass

