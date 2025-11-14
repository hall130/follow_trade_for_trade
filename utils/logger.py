import logging
import os
import sys
from logging.handlers import RotatingFileHandler

class SafeRotatingFileHandler(RotatingFileHandler):
    """
    安全的日志轮转处理器
    在 Windows 上处理多进程同时写入同一日志文件时的权限错误
    """
    def doRollover(self):
        """
        执行日志轮转，捕获权限错误
        """
        try:
            super().doRollover()
        except (PermissionError, OSError) as e:
            # Windows 上多进程同时写入时，轮转可能失败
            # 记录错误但不抛出异常，继续使用当前文件
            if hasattr(self, 'stream') and self.stream:
                try:
                    self.stream.write(f"[日志轮转失败: {e}，继续使用当前日志文件]\n")
                    self.stream.flush()
                except:
                    pass
            # 不抛出异常，让日志继续写入当前文件

# 尝试导入日志配置
try:
    from config.logger_config import *
except ImportError:
    # 如果配置文件不存在，使用默认配置
    ENABLE_HEALTH_CHECK_LOGGING = False
    HEALTH_CHECK_LOG_LEVEL = "WARNING"
    LOG_HEALTH_CHECK_SUCCESS = False
    LOG_HEALTH_CHECK_FAILURE = True
    DEFAULT_LOG_LEVEL = "INFO"
    LOG_FORMAT = "[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s"
    DATE_FORMAT = "%Y-%m-%d %H:%M:%S"
    ENABLE_LOG_ROTATION = True
    MAX_LOG_FILE_SIZE = 10 * 1024 * 1024  # 10MB
    MAX_LOG_FILES = 5

def setup_logger(name="follow_trade", level=None):
    """设置日志记录器"""
    if level is None:
        level = getattr(logging, DEFAULT_LOG_LEVEL.upper(), logging.INFO)
    
    logger = logging.getLogger(name)
    logger.setLevel(level)
    
    # 清除现有的处理器
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)
    
    # 创建格式化器
    formatter = logging.Formatter(LOG_FORMAT, datefmt=DATE_FORMAT)
    
    # 控制台处理器
    ch = logging.StreamHandler()
    ch.setFormatter(formatter)
    ch.setLevel(level)
    logger.addHandler(ch)
    
    # 文件处理器（带轮转）
    if ENABLE_LOG_ROTATION:
        try:
            # 使用自定义的 SafeRotatingFileHandler 处理多进程冲突
            # 在 Windows 上，多个进程同时写入同一文件时，轮转可能会失败
            # SafeRotatingFileHandler 会捕获权限错误，继续使用当前文件
            fh = SafeRotatingFileHandler(
                "trades.log",
                maxBytes=MAX_LOG_FILE_SIZE,
                backupCount=MAX_LOG_FILES,
                encoding='utf-8',
                delay=True  # 延迟打开文件，减少多进程冲突
            )
            fh.setFormatter(formatter)
            fh.setLevel(level)
            logger.addHandler(fh)
        except (PermissionError, OSError) as e:
            # Windows 上多进程同时写入日志文件时可能出现权限错误
            # 忽略此错误，继续使用控制台输出
            print(f"无法创建日志文件处理器（可能是多进程冲突）: {e}")
            print("将仅使用控制台输出日志")
        except Exception as e:
            print(f"无法创建日志文件处理器: {e}")
    
    return logger

def get_logger(name="follow_trade"):
    """获取日志记录器"""
    return logging.getLogger(name)

# 创建主日志记录器
logger = setup_logger("follow_trade")

# 创建专门的健康检查日志记录器
if ENABLE_HEALTH_CHECK_LOGGING:
    health_check_logger = setup_logger("health_check", getattr(logging, HEALTH_CHECK_LOG_LEVEL.upper(), logging.WARNING))
else:
    health_check_logger = None

def log_health_check(message, level="INFO", force=False):
    """记录健康检查日志"""
    if not ENABLE_HEALTH_CHECK_LOGGING and not force:
        return
    
    if health_check_logger:
        log_level = getattr(logging, level.upper(), logging.INFO)
        health_check_logger.log(log_level, message)
    else:
        # 如果没有专门的健康检查日志记录器，使用主日志记录器
        log_level = getattr(logging, level.upper(), logging.INFO)
        logger.log(log_level, f"[健康检查] {message}")

def should_log_health_check_success():
    """是否应该记录健康检查成功日志"""
    return LOG_HEALTH_CHECK_SUCCESS

def should_log_health_check_failure():
    """是否应该记录健康检查失败日志"""
    return LOG_HEALTH_CHECK_FAILURE 