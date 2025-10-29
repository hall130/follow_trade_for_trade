#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
权限管理系统初始化脚本
用于快速设置权限系统的基础数据和配置
"""

import os
import sys
import hashlib
import bcrypt
from datetime import datetime, timedelta

# 添加项目根目录到Python路径
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database.db import get_db_connection

def hash_password(password: str) -> str:
    """使用bcrypt加密密码"""
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(password.encode('utf-8'), salt).decode('utf-8')

def verify_password(password: str, hashed: str) -> bool:
    """验证密码"""
    return bcrypt.checkpw(password.encode('utf-8'), hashed.encode('utf-8'))

def init_permission_system():
    """初始化权限系统"""
    print("🚀 开始初始化权限管理系统...")
    
    try:
        # 连接数据库
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # 1. 检查是否已经初始化
        cursor.execute("SELECT COUNT(*) FROM users WHERE role = 'admin'")
        admin_count = cursor.fetchone()[0]
        
        if admin_count > 0:
            print("⚠️  权限系统已经初始化，跳过初始化步骤")
            return
        
        # 2. 创建默认管理员账户
        print("📝 创建默认管理员账户...")
        admin_password = "admin123"
        admin_hash = hash_password(admin_password)
        
        cursor.execute("""
            INSERT INTO users (username, password_hash, full_name, email, role, status)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, ("admin", admin_hash, "系统管理员", "admin@example.com", "admin", "active"))
        
        admin_id = cursor.lastrowid
        print(f"✅ 管理员账户创建成功，ID: {admin_id}")
        
        # 3. 为管理员授予所有权限
        print("🔐 为管理员授予所有权限...")
        modules = [
            'signal_sources', 'customers', 'strategies', 'market_follow',
            'limit_follow', 'backtest', 'strategy_live', 'message_forward', 'system_settings'
        ]
        
        for module in modules:
            cursor.execute("""
                INSERT INTO user_permissions (user_id, module_code, permission_level, granted_by)
                VALUES (%s, %s, %s, %s)
            """, (admin_id, module, 'admin', admin_id))
        
        print(f"✅ 已为管理员授予 {len(modules)} 个模块的权限")
        
        # 4. 创建测试普通用户
        print("👤 创建测试普通用户...")
        user_password = "user123"
        user_hash = hash_password(user_password)
        
        cursor.execute("""
            INSERT INTO users (username, password_hash, full_name, email, role, status)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, ("user1", user_hash, "测试用户1", "user1@example.com", "user", "active"))
        
        user_id = cursor.lastrowid
        print(f"✅ 普通用户创建成功，ID: {user_id}")
        
        # 5. 为普通用户授予基本权限
        print("🔑 为普通用户授予基本权限...")
        basic_modules = ['customers', 'strategies', 'backtest', 'strategy_live']
        
        for module in basic_modules:
            cursor.execute("""
                INSERT INTO user_permissions (user_id, module_code, permission_level, granted_by)
                VALUES (%s, %s, %s, %s)
            """, (user_id, module, 'write', admin_id))
        
        print(f"✅ 已为普通用户授予 {len(basic_modules)} 个模块的权限")
        
        # 6. 处理现有数据的所有权
        print("📊 处理现有数据的所有权...")
        
        # 将现有客户分配给管理员
        cursor.execute("UPDATE customers SET owner_user_id = %s WHERE owner_user_id IS NULL", (admin_id,))
        customer_count = cursor.rowcount
        print(f"✅ 已处理 {customer_count} 个客户账户")
        
        # 将现有限价跟单策略分配给管理员
        cursor.execute("UPDATE limit_follow_strategies SET created_by_user_id = %s WHERE created_by_user_id IS NULL", (admin_id,))
        strategy_count = cursor.rowcount
        print(f"✅ 已处理 {strategy_count} 个限价跟单策略")
        
        # 将现有策略实例分配给管理员
        cursor.execute("UPDATE strategy_instances SET created_by_user_id = %s WHERE created_by_user_id IS NULL", (admin_id,))
        instance_count = cursor.rowcount
        print(f"✅ 已处理 {instance_count} 个策略实例")
        
        # 将现有回测记录分配给管理员
        cursor.execute("UPDATE strategy_backtests SET created_by_user_id = %s WHERE created_by_user_id IS NULL", (admin_id,))
        backtest_count = cursor.rowcount
        print(f"✅ 已处理 {backtest_count} 个回测记录")
        
        # 处理带单员数据
        cursor.execute("""
            UPDATE limit_follow_traders 
            SET is_public = 1, created_by_user_id = %s 
            WHERE created_by_user_id IS NULL
        """, (admin_id,))
        trader_count = cursor.rowcount
        print(f"✅ 已处理 {trader_count} 个带单员")
        
        # 7. 提交事务
        conn.commit()
        
        print("\n🎉 权限管理系统初始化完成！")
        print("\n📋 默认账户信息：")
        print("   管理员账户：admin / admin123")
        print("   普通用户：user1 / user123")
        print("\n🔐 权限说明：")
        print("   - 管理员：拥有所有模块的完全权限")
        print("   - 普通用户：拥有客户管理、策略管理、回测、实盘的基本权限")
        print("\n📊 数据统计：")
        print(f"   - 用户数量：2")
        print(f"   - 权限记录：{len(modules) + len(basic_modules)}")
        print(f"   - 客户账户：{customer_count}")
        print(f"   - 限价跟单策略：{strategy_count}")
        print(f"   - 策略实例：{instance_count}")
        print(f"   - 回测记录：{backtest_count}")
        print(f"   - 带单员：{trader_count}")
        
    except Exception as e:
        print(f"❌ 初始化失败：{e}")
        if 'conn' in locals():
            conn.rollback()
        raise
    finally:
        if 'conn' in locals():
            conn.close()

def create_test_users():
    """创建更多测试用户"""
    print("\n👥 创建更多测试用户...")
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # 获取管理员ID
        cursor.execute("SELECT id FROM users WHERE role = 'admin' LIMIT 1")
        admin_id = cursor.fetchone()[0]
        
        # 创建测试用户
        test_users = [
            ("trader1", "交易员1", "trader1@example.com"),
            ("trader2", "交易员2", "trader2@example.com"),
            ("analyst1", "分析师1", "analyst1@example.com"),
        ]
        
        for username, full_name, email in test_users:
            password = "123456"
            password_hash = hash_password(password)
            
            cursor.execute("""
                INSERT INTO users (username, password_hash, full_name, email, role, status)
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (username, password_hash, full_name, email, "user", "active"))
            
            user_id = cursor.lastrowid
            
            # 授予基本权限
            basic_modules = ['customers', 'strategies', 'backtest', 'strategy_live']
            for module in basic_modules:
                cursor.execute("""
                    INSERT INTO user_permissions (user_id, module_code, permission_level, granted_by)
                    VALUES (%s, %s, %s, %s)
                """, (user_id, module, 'write', admin_id))
            
            print(f"✅ 创建用户：{username} / {password}")
        
        conn.commit()
        print(f"✅ 已创建 {len(test_users)} 个测试用户")
        
    except Exception as e:
        print(f"❌ 创建测试用户失败：{e}")
        if 'conn' in locals():
            conn.rollback()
        raise
    finally:
        if 'conn' in locals():
            conn.close()

def show_system_status():
    """显示系统状态"""
    print("\n📊 权限管理系统状态：")
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # 用户统计
        cursor.execute("SELECT role, COUNT(*) FROM users GROUP BY role")
        user_stats = cursor.fetchall()
        print("\n👥 用户统计：")
        for role, count in user_stats:
            print(f"   {role}: {count} 人")
        
        # 权限统计
        cursor.execute("SELECT module_code, COUNT(*) FROM user_permissions GROUP BY module_code")
        permission_stats = cursor.fetchall()
        print("\n🔐 权限统计：")
        for module, count in permission_stats:
            print(f"   {module}: {count} 个权限")
        
        # 数据统计
        tables = ['customers', 'limit_follow_strategies', 'strategy_instances', 'strategy_backtests']
        print("\n📊 数据统计：")
        for table in tables:
            try:
                cursor.execute(f"SELECT COUNT(*) FROM {table}")
                count = cursor.fetchone()[0]
                print(f"   {table}: {count} 条记录")
            except:
                print(f"   {table}: 表不存在")
        
    except Exception as e:
        print(f"❌ 获取系统状态失败：{e}")
    finally:
        if 'conn' in locals():
            conn.close()

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="权限管理系统初始化脚本")
    parser.add_argument("--init", action="store_true", help="初始化权限系统")
    parser.add_argument("--create-users", action="store_true", help="创建测试用户")
    parser.add_argument("--status", action="store_true", help="显示系统状态")
    
    args = parser.parse_args()
    
    if args.init:
        init_permission_system()
    elif args.create_users:
        create_test_users()
    elif args.status:
        show_system_status()
    else:
        print("请指定操作：--init, --create-users, 或 --status")
        print("\n使用示例：")
        print("  python init_permission_system.py --init        # 初始化权限系统")
        print("  python init_permission_system.py --create-users # 创建测试用户")
        print("  python init_permission_system.py --status      # 显示系统状态")

