#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Telegram监听服务进程管理器
管理TelegramListenerService的启动、停止和状态监控
"""

import os
import sys
import json
import subprocess
import signal
import time
import threading
from typing import Dict, Optional, Any
from pathlib import Path
from datetime import datetime

# 添加项目根目录到Python路径
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from utils.logger import get_logger

logger = get_logger(__name__)

class TelegramListenerProcessManager:
    """Telegram监听服务进程管理器"""
    
    def __init__(self):
        """初始化管理器"""
        self.process: Optional[subprocess.Popen] = None
        
        # 获取项目根目录（相对于当前文件）
        project_root = Path(__file__).parent.parent.parent
        
        self.status_file = project_root / "telegram_listener_status.json"
        self.pid_file = project_root / "telegram_listener.pid"
        self.config_file = project_root / "config" / "telegram_listener_config.json"
        self.script_file = project_root / "start_telegram_listener.py"
        
        # 状态监控线程
        self.monitor_thread: Optional[threading.Thread] = None
        self.monitoring = False
        
        logger.info("Telegram监听服务进程管理器初始化完成")
    
    def is_running(self) -> bool:
        """检查服务是否正在运行"""
        logger.debug(f"检查服务是否运行，PID文件: {self.pid_file}, 状态文件: {self.status_file}")
        
        # 检查PID文件
        if self.pid_file.exists():
            try:
                with open(self.pid_file, 'r') as f:
                    pid = int(f.read().strip())
                
                logger.debug(f"从PID文件读取PID: {pid}")
                
                # 检查进程是否存在
                try:
                    if sys.platform == 'win32':
                        # Windows上使用不同的方法检查进程
                        try:
                            import psutil
                            try:
                                process = psutil.Process(pid)
                                # 检查进程是否还在运行
                                if process.is_running():
                                    logger.debug(f"进程 {pid} 正在运行")
                                    return True
                            except (psutil.NoSuchProcess, psutil.AccessDenied):
                                # 进程不存在或无权限访问
                                logger.debug(f"进程 {pid} 不存在或无权限访问")
                                self.pid_file.unlink(missing_ok=True)
                                return False
                        except ImportError:
                            # psutil不可用，使用os.kill
                            logger.debug("psutil不可用，使用os.kill检查进程")
                            try:
                                os.kill(pid, 0)
                                logger.debug(f"进程 {pid} 存在（通过os.kill）")
                                return True
                            except OSError:
                                logger.debug(f"进程 {pid} 不存在（通过os.kill）")
                                self.pid_file.unlink(missing_ok=True)
                                return False
                    else:
                        # Unix/Linux系统
                        os.kill(pid, 0)  # 发送信号0，不杀死进程，只检查是否存在
                        logger.debug(f"进程 {pid} 存在")
                        return True
                except OSError:
                    # 进程不存在，删除PID文件
                    logger.debug(f"进程 {pid} 不存在，删除PID文件")
                    self.pid_file.unlink(missing_ok=True)
                    return False
            except (ValueError, FileNotFoundError) as e:
                logger.debug(f"读取PID文件失败: {e}")
                return False
        
        # 如果PID文件不存在，但状态文件显示运行中，也认为服务在运行
        # 因为状态文件是服务自己更新的，更可靠
        if self.status_file.exists():
            try:
                with open(self.status_file, 'r', encoding='utf-8') as f:
                    status = json.load(f)
                if status.get('running', False):
                    # 状态文件显示运行中，即使没有PID文件也认为在运行
                    # 可能是PID文件被意外删除，但服务还在运行
                    logger.debug("PID文件不存在，但状态文件显示运行中，认为服务在运行")
                    return True
            except Exception as e:
                logger.debug(f"读取状态文件失败: {e}")
        
        logger.debug("服务未运行")
        return False
    
    def get_status(self) -> Dict[str, Any]:
        """获取服务状态"""
        try:
            logger.info(f"获取服务状态，状态文件路径: {self.status_file}")
            logger.info(f"状态文件是否存在: {self.status_file.exists()}")
            logger.info(f"状态文件绝对路径: {self.status_file.absolute()}")
            
            # 优先从状态文件读取（状态文件是服务自己更新的，更准确）
            if self.status_file.exists():
                try:
                    logger.info(f"开始读取状态文件: {self.status_file}")
                    with open(self.status_file, 'r', encoding='utf-8') as f:
                        status = json.load(f)
                    
                    logger.info(f"从状态文件读取的状态: running={status.get('running', False)}, running类型={type(status.get('running'))}, telegram_connected={status.get('telegram_connected', False)}")
                    logger.info(f"状态文件完整内容: {json.dumps(status, ensure_ascii=False, indent=2, default=str)}")
                    
                    # 如果状态文件显示运行中，信任状态文件
                    # 因为状态文件是服务自己更新的，比PID文件更可靠
                    running_value = status.get('running', False)
                    # 确保 running 是布尔值
                    if isinstance(running_value, bool) and running_value:
                        # 状态文件显示运行中，直接返回
                        # 不检查进程，因为PID文件可能被意外删除，但服务还在运行
                        # 如果服务真的退出了，状态文件会在下次更新时自动更新为未运行
                        logger.info(f"状态文件显示运行中，返回状态: running=True")
                        return status
                    elif isinstance(running_value, str) and running_value.lower() in ('true', '1', 'yes'):
                        # 处理字符串类型的 true
                        logger.info(f"状态文件中running是字符串'true'，转换为布尔值")
                        status['running'] = True
                        return status
                    else:
                        # 状态文件显示未运行，但检查一下进程是否真的不存在
                        # 如果进程存在但状态文件显示未运行，可能是状态文件更新延迟
                        logger.info(f"状态文件显示未运行 (running={running_value}, 类型={type(running_value)})，检查进程状态")
                        is_running = self.is_running()
                        logger.info(f"进程检查结果: is_running={is_running}")
                        if is_running:
                            # 进程存在，更新状态为运行中
                            status['running'] = True
                            try:
                                with open(self.status_file, 'w', encoding='utf-8') as f:
                                    json.dump(status, f, ensure_ascii=False, indent=2, default=str)
                                logger.info("进程存在但状态文件显示未运行，已更新状态文件")
                            except Exception as e:
                                logger.warning(f"更新状态文件失败: {e}")
                    
                    logger.info(f"返回状态: running={status.get('running', False)}")
                    return status
                except (json.JSONDecodeError, FileNotFoundError) as e:
                    logger.error(f"读取状态文件失败: {e}")
                    import traceback
                    logger.error(traceback.format_exc())
                    # 读取失败，继续执行下面的逻辑
                except Exception as e:
                    logger.error(f"读取状态文件时发生未知错误: {e}")
                    import traceback
                    logger.error(traceback.format_exc())
                    # 发生未知错误，继续执行下面的逻辑
            
            # 如果状态文件不存在或读取失败，检查进程是否在运行
            if not self.is_running():
                return {
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
                    'target_platforms_count': 0
                }
            
            # 进程在运行但状态文件不存在，返回基本状态
            return {
                'running': True,
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
                'target_platforms_count': 0
            }
            
        except Exception as e:
            logger.error(f"获取服务状态失败: {e}")
            return {
                'running': False,
                'error': str(e)
            }
    
    def start(self) -> Dict[str, Any]:
        """启动服务"""
        try:
            # 检查是否已经在运行
            # 优先检查状态文件，因为状态文件更可靠
            if self.status_file.exists():
                try:
                    with open(self.status_file, 'r', encoding='utf-8') as f:
                        status = json.load(f)
                    if status.get('running', False):
                        logger.warning("状态文件显示服务已在运行中")
                        return {
                            'success': False,
                            'message': '服务已经在运行中（状态文件显示）'
                        }
                except:
                    pass
            
            # 也检查进程
            if self.is_running():
                logger.warning("检测到服务进程正在运行")
                return {
                    'success': False,
                    'message': '服务已经在运行中（检测到进程）'
                }
            
            # 检查配置文件是否存在（尝试多种路径）
            if not self.config_file.exists():
                # 尝试使用相对路径
                relative_config = Path("config/telegram_listener_config.json")
                if relative_config.exists():
                    self.config_file = relative_config.resolve()
                    logger.info(f"使用相对路径找到配置文件: {self.config_file}")
                else:
                    # 尝试从当前工作目录查找
                    cwd_config = Path.cwd() / "config" / "telegram_listener_config.json"
                    if cwd_config.exists():
                        self.config_file = cwd_config.resolve()
                        logger.info(f"从工作目录找到配置文件: {self.config_file}")
                    else:
                        abs_config = self.config_file.resolve()
                        return {
                            'success': False,
                            'message': f'配置文件不存在: {self.config_file}',
                            'details': {
                                'config_file': str(self.config_file),
                                'absolute_path': str(abs_config),
                                'relative_path': str(relative_config),
                                'relative_exists': relative_config.exists(),
                                'cwd_path': str(cwd_config),
                                'cwd_exists': cwd_config.exists(),
                                'current_dir': str(Path.cwd()),
                                'project_root': str(Path(__file__).parent.parent.parent),
                                'exists': False,
                                'hint': '请从 config/telegram_listener_config_example.json 复制并创建配置文件'
                            }
                        }
            
            # 检查启动脚本是否存在
            if not self.script_file.exists():
                abs_script = self.script_file.resolve()
                return {
                    'success': False,
                    'message': f'启动脚本不存在: {self.script_file}',
                    'details': {
                        'script_file': str(self.script_file),
                        'absolute_path': str(abs_script),
                        'exists': False
                    }
                }
            
            # 启动进程
            try:
                # 使用subprocess启动独立进程
                # 使用项目根目录作为工作目录
                project_root = self.script_file.parent
                
                # 在 Windows 上，使用 CREATE_NEW_PROCESS_GROUP 避免信号传播
                # 注意：不使用 DETACHED_PROCESS，因为会导致无法捕获输出
                creation_flags = 0
                if sys.platform == 'win32':
                    import subprocess as sp
                    # 只使用 CREATE_NEW_PROCESS_GROUP，不使用 DETACHED_PROCESS
                    # 这样可以捕获子进程的输出，同时避免信号传播
                    creation_flags = sp.CREATE_NEW_PROCESS_GROUP
                
                # 将输出重定向到文件，方便调试
                log_dir = project_root / "logs"
                log_dir.mkdir(exist_ok=True)
                stdout_file = log_dir / "telegram_listener_stdout.log"
                stderr_file = log_dir / "telegram_listener_stderr.log"
                
                process = subprocess.Popen(
                    [sys.executable, str(self.script_file)],
                    stdout=open(stdout_file, 'w', encoding='utf-8'),
                    stderr=open(stderr_file, 'w', encoding='utf-8'),
                    cwd=str(project_root),
                    env=os.environ.copy(),
                    creationflags=creation_flags if sys.platform == 'win32' else 0,
                    start_new_session=True if sys.platform != 'win32' else False
                )
                
                # 保存PID
                with open(self.pid_file, 'w') as f:
                    f.write(str(process.pid))
                
                self.process = process
                
                # 等待一下，检查进程是否成功启动
                # 先等待2秒，让进程有时间初始化
                time.sleep(2)
                
                # 如果进程已退出，说明启动失败
                if process.poll() is not None:
                    # 进程已退出，从日志文件读取错误信息
                    stdout_msg = ''
                    stderr_msg = ''
                    try:
                        if stdout_file.exists():
                            with open(stdout_file, 'r', encoding='utf-8') as f:
                                stdout_msg = f.read()
                        if stderr_file.exists():
                            with open(stderr_file, 'r', encoding='utf-8') as f:
                                stderr_msg = f.read()
                    except Exception as e:
                        logger.warning(f"读取日志文件失败: {e}")
                    
                    # 如果日志文件为空，尝试从进程读取（虽然可能已经关闭）
                    if not stdout_msg and not stderr_msg:
                        try:
                            stdout, stderr = process.communicate(timeout=1)
                            stdout_msg = stdout.decode('utf-8', errors='ignore') if stdout else ''
                            stderr_msg = stderr.decode('utf-8', errors='ignore') if stderr else ''
                        except:
                            pass
                    
                    error_msg = stderr_msg or stdout_msg or '进程启动后立即退出'
                    logger.error(f"服务启动失败，进程已退出。stdout: {stdout_msg[:500]}, stderr: {stderr_msg[:500]}")
                    
                    # 清理PID文件
                    if self.pid_file.exists():
                        self.pid_file.unlink(missing_ok=True)
                    
                    return {
                        'success': False,
                        'message': f'服务启动失败: {error_msg[:500]}',  # 限制错误消息长度
                        'details': {
                            'stdout': stdout_msg[:500],
                            'stderr': stderr_msg[:500],
                            'exit_code': process.returncode,
                            'log_files': {
                                'stdout': str(stdout_file),
                                'stderr': str(stderr_file)
                            }
                        }
                    }
                
                # 再等待3秒，检查进程是否还在运行（给初始化更多时间）
                time.sleep(3)
                if process.poll() is not None:
                    # 进程在初始化阶段退出，从日志文件读取错误信息
                    stdout_msg = ''
                    stderr_msg = ''
                    try:
                        if stdout_file.exists():
                            with open(stdout_file, 'r', encoding='utf-8') as f:
                                stdout_msg = f.read()
                        if stderr_file.exists():
                            with open(stderr_file, 'r', encoding='utf-8') as f:
                                stderr_msg = f.read()
                    except Exception as e:
                        logger.warning(f"读取日志文件失败: {e}")
                    
                    # 如果日志文件为空，尝试从进程读取
                    if not stdout_msg and not stderr_msg:
                        try:
                            stdout, stderr = process.communicate(timeout=1)
                            stdout_msg = stdout.decode('utf-8', errors='ignore') if stdout else ''
                            stderr_msg = stderr.decode('utf-8', errors='ignore') if stderr else ''
                        except:
                            pass
                    
                    error_msg = stderr_msg or stdout_msg or '服务初始化失败，进程已退出'
                    logger.error(f"服务初始化失败，进程已退出。stdout: {stdout_msg[:500]}, stderr: {stderr_msg[:500]}")
                    
                    # 清理PID文件
                    if self.pid_file.exists():
                        self.pid_file.unlink(missing_ok=True)
                    
                    # 检查是否是认证失败
                    hint = '请检查日志文件或运行 python telegram_login_helper.py 进行登录'
                    if '未认证' in error_msg or '未登录' in error_msg or 'session_string' in error_msg.lower():
                        hint = 'Telegram 未认证，请运行: python telegram_login_helper.py 进行登录'
                    
                    return {
                        'success': False,
                        'message': f'服务初始化失败: {error_msg[:500]}',
                        'details': {
                            'stdout': stdout_msg[:500],
                            'stderr': stderr_msg[:500],
                            'exit_code': process.returncode,
                            'hint': hint,
                            'log_files': {
                                'stdout': str(stdout_file),
                                'stderr': str(stderr_file)
                            }
                        }
                    }
                
                logger.info(f"Telegram监听服务已启动 (PID: {process.pid})")
                
                # 等待状态文件创建，确保服务真正启动
                max_wait = 10  # 最多等待10秒
                wait_interval = 0.5  # 每0.5秒检查一次
                waited = 0
                status_file_created = False
                
                while waited < max_wait:
                    if self.status_file.exists():
                        try:
                            # 尝试读取状态文件，确保它是有效的JSON
                            with open(self.status_file, 'r', encoding='utf-8') as f:
                                status = json.load(f)
                            status_file_created = True
                            logger.info(f"状态文件已创建，服务正在运行")
                            break
                        except (json.JSONDecodeError, FileNotFoundError):
                            # 文件存在但内容无效，继续等待
                            pass
                    
                    time.sleep(wait_interval)
                    waited += wait_interval
                    
                    # 检查进程是否还在运行
                    if process.poll() is not None:
                        # 进程已退出
                        logger.error(f"服务进程在启动后退出 (等待了 {waited:.1f} 秒)")
                        # 清理PID文件
                        if self.pid_file.exists():
                            self.pid_file.unlink(missing_ok=True)
                        return {
                            'success': False,
                            'message': '服务启动后进程退出，请检查日志文件',
                            'details': {
                                'exit_code': process.returncode,
                                'log_files': {
                                    'stdout': str(stdout_file),
                                    'stderr': str(stderr_file)
                                }
                            }
                        }
                
                if not status_file_created:
                    logger.warning(f"等待 {max_wait} 秒后状态文件仍未创建，但进程仍在运行")
                    # 即使状态文件未创建，如果进程还在运行，也认为启动成功
                    # 状态文件可能稍后才会创建
                
                # 启动状态监控
                self._start_monitoring()
                
                return {
                    'success': True,
                    'message': '服务启动成功',
                    'pid': process.pid,
                    'status_file_created': status_file_created
                }
                
            except Exception as e:
                logger.error(f"启动服务失败: {e}")
                import traceback
                error_trace = traceback.format_exc()
                logger.error(error_trace)
                return {
                    'success': False,
                    'message': f'启动服务失败: {str(e)}',
                    'details': {
                        'error_type': type(e).__name__,
                        'python_executable': sys.executable,
                        'script_path': str(self.script_file),
                        'config_path': str(self.config_file),
                        'traceback': error_trace
                    }
                }
                
        except Exception as e:
            logger.error(f"启动服务异常: {e}")
            import traceback
            error_trace = traceback.format_exc()
            logger.error(error_trace)
            return {
                'success': False,
                'message': f'启动服务异常: {str(e)}',
                'details': {
                    'error_type': type(e).__name__,
                    'config_file': str(self.config_file),
                    'config_exists': self.config_file.exists(),
                    'script_file': str(self.script_file),
                    'script_exists': self.script_file.exists(),
                    'traceback': error_trace
                }
            }
    
    def stop(self) -> Dict[str, Any]:
        """停止服务"""
        try:
            logger.info("开始停止Telegram监听服务...")
            
            # 检查服务是否在运行
            is_running = self.is_running()
            logger.info(f"服务运行状态检查: is_running={is_running}")
            
            if not is_running:
                # 即使进程不在运行，也尝试清理状态文件和PID文件
                if self.status_file.exists():
                    try:
                        # 更新状态文件为未运行
                        with open(self.status_file, 'r', encoding='utf-8') as f:
                            status = json.load(f)
                        status['running'] = False
                        with open(self.status_file, 'w', encoding='utf-8') as f:
                            json.dump(status, f, ensure_ascii=False, indent=2, default=str)
                        logger.info("已更新状态文件为未运行")
                    except Exception as e:
                        logger.warning(f"更新状态文件失败: {e}")
                
                # 清理PID文件
                if self.pid_file.exists():
                    self.pid_file.unlink(missing_ok=True)
                
                return {
                    'success': True,
                    'message': '服务未运行，已清理状态'
                }
            
            # 读取PID
            pid = None
            if self.pid_file.exists():
                try:
                    with open(self.pid_file, 'r') as f:
                        pid = int(f.read().strip())
                    logger.info(f"从PID文件读取PID: {pid}")
                except (ValueError, FileNotFoundError) as e:
                    logger.warning(f"读取PID文件失败: {e}")
                    pid = None
            
            # 如果没有PID文件，尝试通过状态文件找到进程
            if pid is None:
                # 无法通过PID停止，但可以更新状态文件
                logger.warning("PID文件不存在，无法通过PID停止进程")
                if self.status_file.exists():
                    try:
                        with open(self.status_file, 'r', encoding='utf-8') as f:
                            status = json.load(f)
                        status['running'] = False
                        with open(self.status_file, 'w', encoding='utf-8') as f:
                            json.dump(status, f, ensure_ascii=False, indent=2, default=str)
                        logger.info("已更新状态文件为未运行（无法通过PID停止进程）")
                    except Exception as e:
                        logger.warning(f"更新状态文件失败: {e}")
                
                return {
                    'success': False,
                    'message': 'PID文件不存在，无法停止进程。请手动停止或重启服务。'
                }
            
            # 停止进程
            try:
                if sys.platform == 'win32':
                    # Windows系统
                    try:
                        import psutil
                        try:
                            process = psutil.Process(pid)
                            # 尝试优雅停止
                            process.terminate()
                            logger.info(f"已发送终止信号到进程 {pid}")
                        except (psutil.NoSuchProcess, psutil.AccessDenied) as e:
                            logger.warning(f"无法终止进程 {pid}: {e}")
                            # 进程可能已经退出
                            self.pid_file.unlink(missing_ok=True)
                            return {
                                'success': True,
                                'message': '进程不存在或已退出'
                            }
                    except ImportError:
                        # psutil不可用，使用taskkill命令
                        logger.info("psutil不可用，使用taskkill命令停止进程")
                        import subprocess
                        try:
                            subprocess.run(['taskkill', '/F', '/PID', str(pid)], 
                                          check=True, capture_output=True, timeout=10)
                            logger.info(f"已使用taskkill停止进程 {pid}")
                        except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError) as e:
                            logger.warning(f"taskkill失败: {e}")
                            # 尝试使用os.kill
                            try:
                                os.kill(pid, signal.SIGTERM if hasattr(signal, 'SIGTERM') else signal.CTRL_C_EVENT)
                            except (OSError, AttributeError):
                                pass
                else:
                    # Unix/Linux系统
                    # 尝试优雅停止（SIGTERM）
                    os.kill(pid, signal.SIGTERM)
                    logger.info(f"已发送SIGTERM信号到进程 {pid}")
                
                # 等待进程退出（最多10秒）
                for i in range(10):
                    time.sleep(1)
                    try:
                        if sys.platform == 'win32':
                            try:
                                import psutil
                                process = psutil.Process(pid)
                                if not process.is_running():
                                    break
                            except (psutil.NoSuchProcess, psutil.AccessDenied, ImportError):
                                # 进程已退出
                                break
                        else:
                            os.kill(pid, 0)  # 检查进程是否还存在
                    except OSError:
                        # 进程已退出
                        break
                else:
                    # 如果进程还在运行，强制杀死
                    logger.warning(f"进程 {pid} 在10秒后仍未退出，尝试强制停止")
                    try:
                        if sys.platform == 'win32':
                            try:
                                import psutil
                                process = psutil.Process(pid)
                                process.kill()
                                logger.warning(f"已强制停止进程 {pid}")
                            except (psutil.NoSuchProcess, psutil.AccessDenied, ImportError):
                                pass
                        else:
                            os.kill(pid, signal.SIGKILL)
                            logger.warning(f"已发送SIGKILL信号到进程 {pid}")
                    except (OSError, AttributeError) as e:
                        logger.warning(f"强制停止失败: {e}")
                
                # 删除PID文件
                self.pid_file.unlink(missing_ok=True)
                
                # 更新状态文件
                if self.status_file.exists():
                    try:
                        with open(self.status_file, 'r', encoding='utf-8') as f:
                            status = json.load(f)
                        status['running'] = False
                        with open(self.status_file, 'w', encoding='utf-8') as f:
                            json.dump(status, f, ensure_ascii=False, indent=2, default=str)
                        logger.info("已更新状态文件为未运行")
                    except Exception as e:
                        logger.warning(f"更新状态文件失败: {e}")
                
                # 停止监控
                self._stop_monitoring()
                
                logger.info(f"Telegram监听服务已停止 (PID: {pid})")
                
                return {
                    'success': True,
                    'message': '服务已停止'
                }
                    
            except ProcessLookupError:
                # 进程不存在
                logger.info(f"进程 {pid} 不存在")
                self.pid_file.unlink(missing_ok=True)
                # 更新状态文件
                if self.status_file.exists():
                    try:
                        with open(self.status_file, 'r', encoding='utf-8') as f:
                            status = json.load(f)
                        status['running'] = False
                        with open(self.status_file, 'w', encoding='utf-8') as f:
                            json.dump(status, f, ensure_ascii=False, indent=2, default=str)
                    except Exception:
                        pass
                return {
                    'success': True,
                    'message': '进程不存在，已清理状态'
                }
            except PermissionError as e:
                logger.error(f"没有权限停止服务: {e}")
                return {
                    'success': False,
                    'message': f'没有权限停止服务: {str(e)}'
                }
                
        except Exception as e:
            logger.error(f"停止服务失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return {
                'success': False,
                'message': f'停止服务失败: {str(e)}'
            }
    
    def _start_monitoring(self):
        """启动状态监控"""
        if self.monitoring:
            return
        
        self.monitoring = True
        self.monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self.monitor_thread.start()
        logger.info("状态监控已启动")
    
    def _stop_monitoring(self):
        """停止状态监控"""
        self.monitoring = False
        if self.monitor_thread:
            self.monitor_thread.join(timeout=2)
        logger.info("状态监控已停止")
    
    def _monitor_loop(self):
        """监控循环"""
        while self.monitoring:
            try:
                if not self.is_running():
                    self.monitoring = False
                    logger.warning("服务进程已退出，停止监控")
                    break
                
                # 每30秒检查一次
                time.sleep(30)
                
            except Exception as e:
                logger.error(f"监控循环异常: {e}")
                time.sleep(30)
    
    def restart(self) -> Dict[str, Any]:
        """重启服务"""
        stop_result = self.stop()
        if not stop_result.get('success'):
            return {
                'success': False,
                'message': f'停止服务失败: {stop_result.get("message")}'
            }
        
        # 等待一下
        time.sleep(2)
        
        return self.start()

# 全局管理器实例
_global_manager: Optional[TelegramListenerProcessManager] = None

def get_telegram_listener_manager() -> TelegramListenerProcessManager:
    """获取全局管理器实例"""
    global _global_manager
    if _global_manager is None:
        _global_manager = TelegramListenerProcessManager()
    return _global_manager

