#!/usr/bin/env python
"""
刷单策略运行脚本
作为子进程运行，执行单个账号的刷单策略
"""
import argparse
import sys
import os
from pathlib import Path

# 添加项目根目录到路径
root_dir = Path(__file__).parent.parent.parent.resolve()
sys.path.insert(0, str(root_dir))

from utils.logger import logger


def parse_arguments():
    """解析命令行参数"""
    parser = argparse.ArgumentParser(description='刷单策略运行脚本')
    
    # 基本参数
    parser.add_argument('--account-name', type=str, required=True, help='账号名称')
    parser.add_argument('--symbol', type=str, required=True, help='交易对')
    parser.add_argument('--exchange', type=str, default='backpack', help='交易所')
    parser.add_argument('--market-type', type=str, choices=['spot', 'perp'], default='spot', help='市场类型')
    
    # 策略参数
    parser.add_argument('--spread', type=float, help='价差百分比')
    parser.add_argument('--quantity', type=float, help='订单数量')
    parser.add_argument('--max-orders', type=int, default=3, help='每侧最大订单数量')
    parser.add_argument('--interval', type=int, default=60, help='更新间隔（秒）')
    parser.add_argument('--duration', type=int, default=3600, help='运行时间（秒）')
    parser.add_argument('--strategy', type=str, default='standard', help='策略类型')
    
    # 标准策略的仓位管理参数
    parser.add_argument('--target-position', type=float, default=0.0, help='目标持仓量（绝对値）')
    parser.add_argument('--max-position', type=float, default=0.5, help='最大持仓量（绝对値）')
    parser.add_argument('--position-threshold', type=float, default=0.4, help='触发仓位调整的阈值')
    parser.add_argument('--inventory-skew', type=float, default=0.0, help='库存偏移（0-1）')
    parser.add_argument('--stop-loss', type=float, help='止损金额（负数）')
    parser.add_argument('--take-profit', type=float, help='止盈金额（正数）')
    
    # Avellaneda-Stoikov策略参数
    parser.add_argument('--risk-factor', type=float, default=5.0, help='风险因子 (gamma)')
    parser.add_argument('--inventory-target', type=float, default=0.0, help='目标库存')
    parser.add_argument('--order-amount-shape-factor', type=float, default=1.0, help='订单大小调整因子 (eta)')
    parser.add_argument('--min-spread', type=float, default=0.01, help='最小价差(%)')
    parser.add_argument('--maker-fee', type=float, default=0.1, help='Maker手续费率(%)')
    parser.add_argument('--taker-fee', type=float, default=0.1, help='Taker手续费率(%)')
    parser.add_argument('--add-transaction-costs', action='store_true', help='将交易费计入价差')
    
    # 环境变量参数（从进程管理器传递）
    parser.add_argument('--api-key', type=str, help='API密钥（从环境变量或参数）')
    parser.add_argument('--api-secret', type=str, help='API密钥（从环境变量或参数）')
    parser.add_argument('--ws-proxy', type=str, help='WebSocket代理')
    parser.add_argument('--base-url', type=str, help='API基础URL')
    
    # 重平设置
    parser.add_argument('--enable-rebalance', action='store_true', help='开启重平功能')
    parser.add_argument('--base-asset-target', type=float, help='基础资产目标比例 (0-100)')
    parser.add_argument('--rebalance-threshold', type=float, help='重平触发阈值')
    
    # 数据库选项
    parser.add_argument('--enable-db', action='store_true', help='启用数据库')
    
    return parser.parse_args()


def main():
    """主函数"""
    args = parse_arguments()
    
    account_name = os.getenv('ACCOUNT_NAME', args.account_name)
    symbol = os.getenv('SYMBOL', args.symbol)
    
    # 从环境变量或参数获取API密钥
    api_key = args.api_key or os.getenv('API_KEY') or os.getenv('BACKPACK_KEY')
    api_secret = args.api_secret or os.getenv('API_SECRET') or os.getenv('BACKPACK_SECRET')
    ws_proxy = args.ws_proxy or os.getenv('WS_PROXY') or os.getenv('BACKPACK_PROXY_WEBSOCKET')
    base_url = args.base_url or os.getenv('BASE_URL', 'https://api.backpack.work')
    
    if not api_key or not api_secret:
        logger.error("缺少API密钥，请通过环境变量或参数提供")
        sys.exit(1)
    
    logger.info(f"启动刷单策略: account={account_name}, symbol={symbol}")
    logger.info(f"参数: exchange={args.exchange}, market_type={args.market_type}")
    logger.info(f"策略参数: spread={args.spread}, quantity={args.quantity}, strategy={args.strategy}")
    
    try:
        # 构建交易所配置
        exchange_config = {
            'api_key': api_key,
            'secret_key': api_secret,
            'base_url': base_url,
            'api_version': 'v1',
            'default_window': '5000'
        }
        
        # 根据策略类型和市场类型初始化不同的策略
        try:
            # 添加参考代码路径
            reference_path = Path(r"D:\backpack\Backpack-MM-Simple")
            if not reference_path.exists():
                logger.error("参考代码路径不存在，无法导入策略")
                logger.warning("请确保参考代码路径正确，或实现自定义策略")
                sys.exit(1)
            
            sys.path.insert(0, str(reference_path))
            
            # 根据市场类型选择基础策略类
            if args.market_type == 'perp':
                # 永续合约：使用PerpetualMarketMaker
                from strategies.perp_market_maker import PerpetualMarketMaker
                
                if args.strategy == 'avellaneda_stoikov':
                    # Avellaneda-Stoikov策略
                    from strategies.avellaneda_stoikov import AvellanedaStoikovStrategy
                    
                    logger.info(f"初始化Avellaneda-Stoikov策略: symbol={symbol}")
                    logger.info(f"参数: risk_factor={args.risk_factor}, inventory_target={args.inventory_target}")
                    
                    market_maker = AvellanedaStoikovStrategy(
                        api_key=api_key,
                        secret_key=api_secret,
                        symbol=symbol,
                        risk_factor=args.risk_factor,
                        inventory_target=args.inventory_target,
                        order_amount_shape_factor=args.order_amount_shape_factor,
                        min_spread=args.min_spread / 100.0 if args.min_spread else 0.0001,  # 转换为小数
                        maker_fee=args.maker_fee / 100.0 if args.maker_fee else 0.001,  # 转换为小数
                        taker_fee=args.taker_fee / 100.0 if args.taker_fee else 0.001,  # 转换为小数
                        add_transaction_costs=args.add_transaction_costs,
                        target_position=args.target_position,
                        max_position=args.max_position,
                        position_threshold=args.position_threshold,
                        inventory_skew=args.inventory_skew,
                        stop_loss=args.stop_loss,
                        take_profit=args.take_profit,
                        ws_proxy=ws_proxy,
                        exchange=args.exchange,
                        exchange_config=exchange_config,
                        enable_database=args.enable_db
                    )
                elif args.strategy == 'maker_hedge':
                    # Maker-Taker对冲策略
                    from strategies.maker_taker_hedge import MakerTakerHedgeStrategy
                    
                    logger.info(f"初始化Maker-Taker对冲策略: symbol={symbol}")
                    
                    market_maker = MakerTakerHedgeStrategy(
                        api_key=api_key,
                        secret_key=api_secret,
                        symbol=symbol,
                        base_spread_percentage=args.spread or 0.5,
                        order_quantity=args.quantity,
                        max_orders=args.max_orders,
                        target_position=args.target_position,
                        max_position=args.max_position,
                        position_threshold=args.position_threshold,
                        inventory_skew=args.inventory_skew,
                        stop_loss=args.stop_loss,
                        take_profit=args.take_profit,
                        ws_proxy=ws_proxy,
                        exchange=args.exchange,
                        exchange_config=exchange_config,
                        enable_database=args.enable_db
                    )
                else:
                    # 标准永续合约做市策略
                    logger.info(f"初始化标准永续合约做市策略: symbol={symbol}")
                    logger.info(f"参数: target_position={args.target_position}, max_position={args.max_position}, stop_loss={args.stop_loss}, take_profit={args.take_profit}")
                    
                    market_maker = PerpetualMarketMaker(
                        api_key=api_key,
                        secret_key=api_secret,
                        symbol=symbol,
                        base_spread_percentage=args.spread or 0.5,
                        order_quantity=args.quantity,
                        max_orders=args.max_orders,
                        target_position=args.target_position,
                        max_position=args.max_position,
                        position_threshold=args.position_threshold,
                        inventory_skew=args.inventory_skew,
                        stop_loss=args.stop_loss,
                        take_profit=args.take_profit,
                        ws_proxy=ws_proxy,
                        exchange=args.exchange,
                        exchange_config=exchange_config,
                        enable_database=args.enable_db
                    )
            else:
                # 现货：使用MarketMaker
                from strategies.market_maker import MarketMaker
                
                # 重平设置
                enable_rebalance = args.enable_rebalance if args.enable_rebalance else True
                base_asset_target = args.base_asset_target if args.base_asset_target else 30.0
                rebalance_threshold = args.rebalance_threshold if args.rebalance_threshold else 15.0
                
                logger.info(f"初始化现货做市策略: symbol={symbol}")
                logger.info(f"重平设置: 开启={enable_rebalance}, 目标比例={base_asset_target}%, 触发阈值={rebalance_threshold}%")
                
                market_maker = MarketMaker(
                    api_key=api_key,
                    secret_key=api_secret,
                    symbol=symbol,
                    base_spread_percentage=args.spread or 0.5,
                    order_quantity=args.quantity,
                    max_orders=args.max_orders,
                    enable_rebalance=enable_rebalance,
                    base_asset_target_percentage=base_asset_target,
                    rebalance_threshold=rebalance_threshold,
                    ws_proxy=ws_proxy,
                    exchange=args.exchange,
                    exchange_config=exchange_config,
                    enable_database=args.enable_db
                )
            
            # 运行策略
            market_maker.run(
                duration_seconds=args.duration or 3600,
                interval_seconds=args.interval or 60
            )
            
        except ImportError as e:
            logger.error(f"导入策略失败: {e}")
            import traceback
            traceback.print_exc()
            logger.warning("请确保参考代码已正确配置")
            sys.exit(1)
        except Exception as e:
            logger.error(f"策略初始化失败: {e}")
            import traceback
            traceback.print_exc()
            sys.exit(1)
        
        logger.info("刷单策略运行完成")
        
    except KeyboardInterrupt:
        logger.info("收到中断信号，正在退出...")
    except Exception as e:
        logger.error(f"刷单过程中发生错误: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()

