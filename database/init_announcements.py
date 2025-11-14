#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
初始化系统公告表
"""

from database.db import get_db_pool
from utils.logger import get_logger

logger = get_logger(__name__)

def init_announcements_table():
    """初始化公告表"""
    try:
        db_pool = get_db_pool()
        
        # 读取SQL文件
        with open('database/announcements_schema.sql', 'r', encoding='utf-8') as f:
            sql_content = f.read()
        
        # 分割SQL语句
        statements = [s.strip() for s in sql_content.split(';') if s.strip() and not s.strip().startswith('--')]
        
        # 执行每条SQL
        for statement in statements:
            if statement:
                try:
                    db_pool.execute(statement)
                    logger.info(f"执行SQL成功: {statement[:50]}...")
                except Exception as e:
                    logger.warning(f"执行SQL失败 (可能已存在): {e}")
        
        logger.info("✅ 系统公告表初始化完成")
        return True
        
    except Exception as e:
        logger.error(f"❌ 初始化公告表失败: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return False

if __name__ == '__main__':
    print("开始初始化系统公告表...")
    if init_announcements_table():
        print("初始化成功！")
    else:
        print("初始化失败，请检查日志")

