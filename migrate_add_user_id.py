#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
数据库迁移脚本：添加 strategy_instances 表的 user_id 字段
"""

import psycopg2
import sys

# 设置输出编码
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# 数据库连接配置
DB_CONFIG = {
    'host': 'localhost',
    'port': 5432,
    'user': 'postgres',
    'password': 'Sfplc_2026!',
    'database': 'trade_db'
}

def migrate():
    """执行数据库迁移"""
    try:
        # 连接数据库
        print("正在连接数据库...")
        conn = psycopg2.connect(**DB_CONFIG)
        cur = conn.cursor()

        print("=" * 60)
        print("开始数据库迁移...")
        print("=" * 60)

        # 添加 user_id 字段
        print("\n1. 添加 user_id 字段（用户ID）...")
        cur.execute("""
            ALTER TABLE strategy_instances
            ADD COLUMN IF NOT EXISTS user_id VARCHAR(64);
        """)
        print("   ✅ user_id 字段添加成功")

        # 添加索引
        print("\n2. 添加 user_id 索引...")
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_strategy_instances_user_id
            ON strategy_instances(user_id);
        """)
        print("   ✅ user_id 索引添加成功")

        # 提交事务
        conn.commit()

        print("\n" + "=" * 60)
        print("✅ 数据库迁移完成！")
        print("=" * 60)

        # 关闭连接
        cur.close()
        conn.close()

    except Exception as e:
        print(f"\n❌ 迁移失败: {e}")
        if 'conn' in locals():
            conn.rollback()
        sys.exit(1)

if __name__ == '__main__':
    migrate()
