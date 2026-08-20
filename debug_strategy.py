"""
调试策略启动问题
"""
import asyncio
import sys
import os

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(__file__))

from db.mysql_pool import get_db_pool
from core.strategy_trade.core.manager import StrategyManager
from exchange.exchange_factory import create_exchange_client

async def test_strategy_startup():
    """测试策略启动流程"""

    print("=" * 60)
    print("开始诊断策略启动问题")
    print("=" * 60)

    # 1. 检查数据库连接
    print("\n[1/5] 检查数据库连接...")
    try:
        db_pool = get_db_pool()
        customers = db_pool.query(
            "SELECT customer_uid, api_key, is_demo FROM customers WHERE customer_uid = %s",
            ('cust_b08e700e',)
        )
        if customers:
            customer = customers[0]
            print(f"✅ 找到客户: {customer['customer_uid']}")
            print(f"   API Key: {customer['api_key'][:8]}***")
            print(f"   是否模拟盘: {customer['is_demo']}")
        else:
            print(f"❌ 未找到客户 cust_b08e700e")
            return
    except Exception as e:
        print(f"❌ 数据库连接失败: {e}")
        return

    # 2. 检查策略是否存在
    print("\n[2/5] 检查策略是否存在...")
    try:
        strategy_manager = StrategyManager()
        strategy_info = strategy_manager.get_strategy('template_FMZGrid_Strategy')
        if strategy_info:
            print(f"✅ 找到策略: {strategy_info.name}")
            print(f"   状态: {strategy_info.status}")
            strategy = strategy_info.strategy

            # 检查策略是否有 timeframe 属性
            if hasattr(strategy, 'timeframe'):
                print(f"   Timeframe: {strategy.timeframe}")
            else:
                print(f"   ⚠️  策略没有 timeframe 属性（将跳过历史预热）")
        else:
            print(f"❌ 未找到策略 template_FMZGrid_Strategy")
            return
    except Exception as e:
        print(f"❌ 获取策略失败: {e}")
        import traceback
        traceback.print_exc()
        return

    # 3. 测试OKX API连接
    print("\n[3/5] 测试OKX API连接...")
    try:
        is_demo = customer['is_demo']
        rest_client = create_exchange_client(
            exchange='okx',
            client_type='rest',
            is_demo=is_demo
        )
        print(f"✅ OKX REST客户端创建成功")
        print(f"   API URL: {rest_client.api_url}")
        print(f"   是否模拟盘: {is_demo}")

        # 测试拉取历史K线
        print("\n   测试拉取历史K线...")
        rows = await rest_client.get_historical_klines(
            symbol='BTC-USDT-SWAP',
            interval='1m',
            start_time=None,
            end_time=None,
            limit=5
        )

        if rows:
            print(f"   ✅ 成功拉取 {len(rows)} 根K线")
            print(f"   最新K线时间: {rows[0][0]}")
        else:
            print(f"   ❌ 未获取到K线数据")

    except Exception as e:
        print(f"❌ OKX API测试失败: {e}")
        import traceback
        traceback.print_exc()
        return

    # 4. 检查策略的 market_data 属性
    print("\n[4/5] 检查策略属性...")
    try:
        if hasattr(strategy, 'market_data'):
            print(f"✅ 策略有 market_data 属性 (长度: {len(strategy.market_data)})")
        else:
            print(f"❌ 策略没有 market_data 属性")

        if hasattr(strategy, 'price_data'):
            print(f"✅ 策略有 price_data 属性")
        else:
            print(f"⚠️  策略没有 price_data 属性")
    except Exception as e:
        print(f"❌ 检查策略属性失败: {e}")

    # 5. 总结
    print("\n[5/5] 诊断总结")
    print("=" * 60)
    print("可能的问题：")

    if not hasattr(strategy, 'timeframe'):
        print("❌ 策略没有 timeframe 属性 - 这会导致历史预热被跳过")
        print("   解决方案：在策略类的 __init__ 中添加 self.timeframe = '1m'")

    if not hasattr(strategy, 'market_data'):
        print("❌ 策略没有 market_data 属性 - 这会导致数据无法填充")
        print("   解决方案：确保策略继承自 BaseStrategy")

    print("\n建议：")
    print("1. 检查策略类是否正确继承 BaseStrategy")
    print("2. 确保策略的 __init__ 方法中设置了 self.timeframe")
    print("3. 重启后端服务后重新启动策略")
    print("=" * 60)

if __name__ == '__main__':
    asyncio.run(test_strategy_startup())
