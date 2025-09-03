import logging
import os
from logging.handlers import RotatingFileHandler

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
            fh = RotatingFileHandler(
                "trades.log",
                maxBytes=MAX_LOG_FILE_SIZE,
                backupCount=MAX_LOG_FILES,
                encoding='utf-8'
            )
            fh.setFormatter(formatter)
            fh.setLevel(level)
            logger.addHandler(fh)
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