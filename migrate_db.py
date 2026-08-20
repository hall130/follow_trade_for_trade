#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
数据库迁移脚本：添加 strategy_instances 表缺失的字段
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

        # 添加 is_demo 字段
        print("\n1. 添加 is_demo 字段（交易模式）...")
        cur.execute("""
            ALTER TABLE strategy_instances
            ADD COLUMN IF NOT EXISTS is_demo BOOLEAN DEFAULT true;
        """)
        print("   ✅ is_demo 字段添加成功")

        # 添加 account_id 字段
        print("\n2. 添加 account_id 字段（关联客户账号）...")
        cur.execute("""
            ALTER TABLE strategy_instances
            ADD COLUMN IF NOT EXISTS account_id VARCHAR(100);
        """)
        print("   ✅ account_id 字段添加成功")

        # 添加 signal_source_uid 字段
        print("\n3. 添加 signal_source_uid 字段（关联信号源）...")
        cur.execute("""
            ALTER TABLE strategy_instances
            ADD COLUMN IF NOT EXISTS signal_source_uid VARCHAR(100);
        """)
        print("   ✅ signal_source_uid 字段添加成功")

        # 添加索引
        print("\n4. 创建索引以提高查询性能...")
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_strategy_instances_is_demo
            ON strategy_instances(is_demo);
        """)
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_strategy_instances_account_id
            ON strategy_instances(account_id);
        """)
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_strategy_instances_signal_source_uid
            ON strategy_instances(signal_source_uid);
        """)
        print("   ✅ 索引创建成功")

        # 提交事务
        conn.commit()

        # 查看表结构
        print("\n5. 验证表结构...")
        cur.execute("""
            SELECT column_name, data_type, is_nullable, column_default
            FROM information_schema.columns
            WHERE table_name = 'strategy_instances'
            ORDER BY ordinal_position;
        """)

        print("\n   strategy_instances 表结构：")
        print("   " + "-" * 70)
        print(f"   {'字段名':<30} {'数据类型':<20} {'可空':<10} {'默认值'}")
        print("   " + "-" * 70)

        for row in cur.fetchall():
            column_name, data_type, is_nullable, column_default = row
            default_str = str(column_default)[:20] if column_default else '-'
            print(f"   {column_name:<30} {data_type:<20} {is_nullable:<10} {default_str}")

        print("   " + "-" * 70)

        cur.close()
        conn.close()

        print("\n" + "=" * 60)
        print("✅ 数据库迁移成功完成！")
        print("=" * 60)
        print("\n请重启应用以使更改生效。")

    except Exception as e:
        print(f"\n❌ 数据库迁移失败: {e}")
        import traceback
        traceback.print_exc()
        return False

    return True

if __name__ == '__main__':
    migrate()
