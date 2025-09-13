#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
数据库初始化脚本
用于创建策略交易系统所需的所有数据库表和视图
"""

import asyncio
import os
from database.db import get_db_pool
from utils.logger import get_logger

logger = get_logger(__name__)

async def execute_sql_file(pool, sql_file_path: str):
    """执行SQL文件"""
    try:
        if not os.path.exists(sql_file_path):
            logger.error(f"SQL文件不存在: {sql_file_path}")
            return False
        
        with open(sql_file_path, 'r', encoding='utf-8') as f:
            sql_content = f.read()
        
        # 按分号分割SQL语句
        sql_statements = [stmt.strip() for stmt in sql_content.split(';') if stmt.strip()]
        
        async with pool.acquire() as conn:
            for sql in sql_statements:
                if sql:
                    try:
                        await conn.execute(sql)
                        logger.debug(f"执行SQL语句成功: {sql[:50]}...")
                    except Exception as e:
                        logger.error(f"执行SQL语句失败: {sql[:50]}... 错误: {e}")
                        raise
        
        logger.info(f"SQL文件执行成功: {sql_file_path}")
        return True
        
    except Exception as e:
        logger.error(f"执行SQL文件失败: {sql_file_path} 错误: {e}")
        return False

async def create_database_schema():
    """创建数据库模式"""
    try:
        pool = await get_db_pool()
        
        # SQL文件路径
        sql_file = os.path.join(os.path.dirname(__file__), 'strategy_tables.sql')
        
        # 执行SQL文件
        success = await execute_sql_file(pool, sql_file)
        
        if success:
            logger.info("数据库初始化完成")
            return True
        else:
            logger.error("数据库初始化失败")
            return False
            
    except Exception as e:
        logger.error(f"数据库初始化异常: {e}")
        return False

async def check_database_status():
    """检查数据库状态"""
    try:
        pool = await get_db_pool()
        
        # 检查表是否存在
        tables_to_check = [
            'strategy_configs',
            'strategy_instances', 
            'strategy_signals',
            'strategy_positions',
            'strategy_trades',
            'strategy_performance',
            'strategy_risk_monitor',
            'strategy_backtests',
            'strategy_market_data',
            'strategy_logs'
        ]
        
        async with pool.acquire() as conn:
            for table in tables_to_check:
                result = await conn.fetchone(
                    "SELECT COUNT(*) as count FROM information_schema.tables WHERE table_name = %s",
                    table
                )
                if result and result['count'] > 0:
                    logger.info(f"表 {table} 存在")
                else:
                    logger.warning(f"表 {table} 不存在")
        
        # 检查视图
        views_to_check = [
            'v_strategy_instances_overview',
            'v_strategy_performance_summary'
        ]
        
        async with pool.acquire() as conn:
            for view in views_to_check:
                result = await conn.fetchone(
                    "SELECT COUNT(*) as count FROM information_schema.views WHERE table_name = %s",
                    view
                )
                if result and result['count'] > 0:
                    logger.info(f"视图 {view} 存在")
                else:
                    logger.warning(f"视图 {view} 不存在")
        
        logger.info("数据库状态检查完成")
        return True
        
    except Exception as e:
        logger.error(f"检查数据库状态失败: {e}")
        return False

async def clean_database():
    """清理数据库（删除所有表）"""
    try:
        pool = await get_db_pool()
        
        # 删除顺序很重要，要先删除有外键约束的表
        drop_order = [
            'strategy_logs',
            'strategy_risk_monitor',
            'strategy_performance',
            'strategy_trades',
            'strategy_positions',
            'strategy_signals',
            'strategy_instances',
            'strategy_configs',
            'strategy_backtests',
            'strategy_market_data',
            'v_strategy_instances_overview',
            'v_strategy_performance_summary'
        ]
        
        async with pool.acquire() as conn:
            # 禁用外键检查
            await conn.execute("SET FOREIGN_KEY_CHECKS = 0")
            
            for table in drop_order:
                try:
                    await conn.execute(f"DROP TABLE IF EXISTS {table}")
                    logger.info(f"已删除表: {table}")
                except:
                    try:
                        await conn.execute(f"DROP VIEW IF EXISTS {table}")
                        logger.info(f"已删除视图: {table}")
                    except:
                        logger.warning(f"删除 {table} 失败")
            
            # 重新启用外键检查
            await conn.execute("SET FOREIGN_KEY_CHECKS = 1")
        
        logger.info("数据库清理完成")
        return True
        
    except Exception as e:
        logger.error(f"清理数据库失败: {e}")
        return False

async def reset_database():
    """重置数据库（清理后重新创建）"""
    logger.info("开始重置数据库...")
    
    # 清理数据库
    clean_success = await clean_database()
    if not clean_success:
        logger.error("数据库清理失败")
        return False
    
    # 重新创建
    create_success = await create_database_schema()
    if not create_success:
        logger.error("数据库重建失败")
        return False
    
    logger.info("数据库重置完成")
    return True

async def main():
    """主函数"""
    print("=" * 60)
    print("策略交易系统 - 数据库初始化工具")
    print("=" * 60)
    
    while True:
        print("\n请选择操作:")
        print("1. 初始化数据库")
        print("2. 检查数据库状态")
        print("3. 清理数据库")
        print("4. 重置数据库")
        print("5. 退出")
        
        choice = input("\n请输入选项 (1-5): ").strip()
        
        if choice == '1':
            print("\n正在初始化数据库...")
            success = await create_database_schema()
            if success:
                print("✅ 数据库初始化成功")
            else:
                print("❌ 数据库初始化失败")
                
        elif choice == '2':
            print("\n正在检查数据库状态...")
            await check_database_status()
            
        elif choice == '3':
            confirm = input("\n⚠️  确定要清理所有数据库表吗？(输入 'yes' 确认): ").strip()
            if confirm.lower() == 'yes':
                print("正在清理数据库...")
                success = await clean_database()
                if success:
                    print("✅ 数据库清理成功")
                else:
                    print("❌ 数据库清理失败")
            else:
                print("操作已取消")
                
        elif choice == '4':
            confirm = input("\n⚠️  确定要重置数据库吗？这将删除所有数据！(输入 'yes' 确认): ").strip()
            if confirm.lower() == 'yes':
                print("正在重置数据库...")
                success = await reset_database()
                if success:
                    print("✅ 数据库重置成功")
                else:
                    print("❌ 数据库重置失败")
            else:
                print("操作已取消")
                
        elif choice == '5':
            print("再见！")
            break
            
        else:
            print("无效选项，请重新选择")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n操作被用户中断")
    except Exception as e:
        print(f"\n运行出错: {e}")
        logger.error(f"数据库初始化工具运行出错: {e}") 