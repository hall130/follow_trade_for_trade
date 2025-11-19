#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
限价跟单执行器
监控跟单员交易，自动执行跟单策略
"""

import json
import time
import asyncio
import aiohttp
from typing import Dict, List, Optional
from utils.logger import logger
from database.db import MySQLPool
from core.limit_trade.limit_follow_models import LimitFollowStrategy, LimitFollowOrder, AccountRelation, FollowMode
from core.limit_trade.limit_follow_db import LimitFollowDB
from config.contract_config import get_contract_min_sz
import requests
from exchange.exchange_factory import create_exchange_client
from core.limit_trade.collectors.collector_factory import TraderCollectorFactory
from core.limit_trade.collectors.base_collector import BaseTraderCollector


class LimitFollowExecutor:
    def __init__(self, db_pool: MySQLPool, default_collector_type: str = 'okx'):
        """
        初始化限价跟单执行器
        
        Args:
            db_pool: 数据库连接池
            default_collector_type: 默认采集器类型 ('okx', 'binance' 等)
        """
        if db_pool is None:
            # 尝试从全局管理器获取
            from database.global_db_manager import get_global_db_pool
            db_pool = get_global_db_pool()
            if db_pool is None:
                raise ValueError("数据库连接池不可用，无法初始化限价跟单执行器")
        
        self.db_pool = db_pool
        self.limit_follow_db = LimitFollowDB(db_pool)
        
        # 去重机制：记录每个跟单员的最后处理订单ID
        self.last_ord_ids = {}
        
        # 从数据库加载最新的订单ID
        self._load_latest_ord_ids()
        
        # 配置
        self.config = {
            'polling_interval': 5,  # 轮询间隔（秒）
            'trade_limit': 1,  # 每次获取的交易记录数量
            'max_retry_attempts': 3,  # 最大重试次数
            'retry_delay': 5,  # 重试延迟（秒）
            'request_timeout': 10,  # 请求超时时间（秒）
            'enable_logging': True,  # 启用日志记录
            'log_level': 'INFO',  # 日志级别
            'default_collector_type': default_collector_type  # 默认采集器类型
        }
        
        # 采集器缓存：{trader_unique_name: collector_instance}
        self.collectors_cache: Dict[str, BaseTraderCollector] = {}
    
    def _parse_ratio(self, ratio_str: str) -> tuple:
        """解析比例配置字符串，如 '3:1' -> (0.75, 0.25)"""
        try:
            if ':' not in ratio_str:
                return 1.0, 0.0  # 默认全限价
            
            limit_part, market_part = ratio_str.split(':')
            limit_ratio = int(limit_part)
            market_ratio = int(market_part)
            total = limit_ratio + market_ratio
            
            return limit_ratio / total, market_ratio / total
        except Exception as e:
            logger.error(f"解析比例配置失败: {ratio_str}, 错误: {e}")
            return 1.0, 0.0  # 默认全限价
        
    def _load_latest_ord_ids(self):
        """从数据库加载最新的订单ID"""
        try:
            # 使用子查询获取每个跟单员的最新记录
            query = """
                SELECT l1.trader_unique_name, l1.extra_data
                FROM limit_follow_logs l1
                INNER JOIN (
                    SELECT trader_unique_name, MAX(created_at) as max_created_at
                    FROM limit_follow_logs 
                    WHERE log_level = 'INFO' 
                    AND message LIKE %s
                    GROUP BY trader_unique_name
                ) l2 ON l1.trader_unique_name = l2.trader_unique_name 
                    AND l1.created_at = l2.max_created_at
                WHERE l1.log_level = 'INFO' 
                AND l1.message LIKE %s
            """
            # 使用参数化查询避免格式化字符串问题，查询两种类型的记录
            records = self.db_pool.query(query, ('%发现新交易%', '%发现新交易%'))
            
            # 构建最新订单ID字典
            latest_by_trader = {}
            for record in records:
                trader_unique_name = record['trader_unique_name']
                extra_data = json.loads(record['extra_data']) if record['extra_data'] else {}
                ord_id = extra_data.get('ord_id', '')
                if ord_id:
                    latest_by_trader[trader_unique_name] = ord_id
            
            self.last_ord_ids = latest_by_trader
            logger.info(f"从数据库加载了 {len(self.last_ord_ids)} 个跟单员的最新订单ID: {self.last_ord_ids}")
            
        except Exception as e:
            logger.error(f"加载最新订单ID失败: {e}")
    
    def _save_processed_order_id(self, trader_unique_name: str, ord_id: str):
        """保存已处理的订单ID到数据库"""
        try:
            # 记录处理日志，包含订单ID信息
            from limit_follow_models import LimitFollowLog
            from datetime import datetime
            log = LimitFollowLog(
                log_level='INFO',
                message=f'处理跟单员交易: {trader_unique_name} - {ord_id}',
                order_uid=f'PROCESSED_{ord_id}',
                strategy_id=None,
                customer_uid=None,
                trader_unique_name=trader_unique_name,
                extra_data={'ord_id': ord_id, 'processed_at': datetime.now().isoformat()}
            )
            
            self.limit_follow_db.add_log(log)
            logger.info(f"已保存处理记录: {trader_unique_name} - {ord_id}")
            
        except Exception as e:
            logger.error(f"保存处理记录失败: {e}")
    def _get_collector_for_trader(self, trader_unique_name: str) -> Optional[BaseTraderCollector]:
        """
        获取带单员对应的采集器实例（带缓存）
        
        Args:
            trader_unique_name: 带单员唯一标识
            
        Returns:
            采集器实例
        """
        # 检查缓存
        if trader_unique_name in self.collectors_cache:
            return self.collectors_cache[trader_unique_name]
        
        # 从数据库获取带单员的采集器配置
        try:
            query = """
                SELECT collector_type, collector_config 
                FROM limit_follow_traders 
                WHERE unique_name = %s
            """
            result = self.db_pool.query(query, (trader_unique_name,))
            
            if result and result[0]:
                collector_type = result[0].get('collector_type') or self.config['default_collector_type']
                collector_config_str = result[0].get('collector_config')
                
                # 解析配置（如果是JSON字符串）
                collector_config = {}
                if collector_config_str:
                    try:
                        collector_config = json.loads(collector_config_str) if isinstance(collector_config_str, str) else collector_config_str
                    except:
                        logger.warning(f"解析采集器配置失败: {collector_config_str}")
            else:
                # 使用默认配置
                collector_type = self.config['default_collector_type']
                collector_config = {}
            
            # 创建采集器
            collector = TraderCollectorFactory.create_collector(collector_type, collector_config)
            
            if collector:
                # 缓存采集器
                self.collectors_cache[trader_unique_name] = collector
                logger.info(f"为带单员 {trader_unique_name} 创建{collector_type}采集器")
                return collector
            else:
                logger.error(f"无法为带单员 {trader_unique_name} 创建采集器")
                return None
                
        except Exception as e:
            logger.error(f"获取带单员采集器失败: {e}")
            # 回退到默认采集器
            collector = TraderCollectorFactory.create_collector(
                self.config['default_collector_type'],
                {}
            )
            if collector:
                self.collectors_cache[trader_unique_name] = collector
            return collector
    
    async def get_trade_records_async(
        self, 
        session: aiohttp.ClientSession, 
        trader_unique_name: str, 
        limit: int = 1
    ) -> List[Dict]:
        """
        异步获取交易记录（统一接口）
        
        Args:
            session: aiohttp会话对象
            trader_unique_name: 带单员唯一标识
            limit: 获取的记录数量限制
            
        Returns:
            标准化的交易记录列表
        """
        try:
            # 获取对应的采集器
            collector = self._get_collector_for_trader(trader_unique_name)
            
            if not collector:
                logger.error(f"无法获取带单员 {trader_unique_name} 的采集器")
                return []
            
            # 获取原始交易记录
            raw_records = await collector.get_trade_records_async(
                session, 
                trader_unique_name, 
                limit
            )
            
            # 标准化所有记录
            normalized_records = []
            for raw_record in raw_records:
                normalized = collector.normalize_trade_record(raw_record)
                if normalized:
                    normalized_records.append(normalized)
            
            return normalized_records
                    
        except Exception as e:
            logger.error(f"获取交易记录失败: {e}")
            return []
    
    def _log_new_trade(self, trader_unique_name: str, trade: Dict):
        """记录新交易到日志"""
        try:
            log_data = {
                'trader_unique_name': trader_unique_name,
                'ord_id': trade.get('ordId', ''),
                'side': trade.get('side', ''),
                'sz': trade.get('sz', ''),
                'avgPx': trade.get('avgPx', ''),
                'instId': trade.get('instId', ''),
                'cTime': trade.get('cTime', '')
            }
            
                    # 创建LimitFollowLog对象
            from model.limit_follow_models import LimitFollowLog
            log_entry = LimitFollowLog(
                log_level='INFO',
                message=f'发现新交易: {trader_unique_name} - {trade.get("ordId", "")}',
                trader_unique_name=trader_unique_name,
                extra_data=log_data
            )
            
            self.limit_follow_db.add_log(log_entry)
            
        except Exception as e:
            logger.error(f"记录新交易日志失败: {e}")
    
    def get_follow_strategies(self, trader_unique_name: str, symbol: str, pos_side: str) -> List[LimitFollowStrategy]:
        """获取跟单策略"""
        try:
            # 使用数据库查询来获取匹配的策略，支持SPECIFIC模式
            strategies = self.db_pool.query(
                """SELECT * FROM limit_follow_strategies 
                WHERE trader_unique_name=%s AND enabled=1 
                AND (
                    symbol='ALL' 
                    OR symbol=%s 
                    OR (symbol='SPECIFIC' AND JSON_CONTAINS(symbols, %s))
                )
                AND (pos_side='both' OR pos_side=%s)""",
                (trader_unique_name, symbol, f'"{symbol}"', pos_side)
            )
            
            # 转换为LimitFollowStrategy对象
            matching_strategies = []
            for strategy_data in strategies:
                try:
                    # 解析symbols字段
                    symbols_list = []
                    if strategy_data.get('symbols'):
                        import json
                        symbols_list = json.loads(strategy_data['symbols'])
                    
                    strategy = LimitFollowStrategy(
                        id=strategy_data['id'],
                        strategy_name=strategy_data['strategy_name'],
                        trader_unique_name=strategy_data['trader_unique_name'],
                        customer_uid=strategy_data['customer_uid'],
                        symbol=strategy_data['symbol'],
                        symbols=symbols_list,
                        pos_side=strategy_data['pos_side'],
                        follow_type=strategy_data['follow_type'],
                        follow_mode=strategy_data['follow_mode'],
                        follow_order_types=strategy_data.get('follow_order_types', 'limit_only'),
                        limit_market_ratio=strategy_data.get('limit_market_ratio', '1:1'),
                        follow_value=float(strategy_data['follow_value']) if strategy_data.get('follow_value') is not None else 0.0,
                        min_follow_value=float(strategy_data.get('min_follow_value', 0.5)) if strategy_data.get('min_follow_value') is not None else 0.5,
                        max_follow_value=float(strategy_data.get('max_follow_value', 5.0)) if strategy_data.get('max_follow_value') is not None else 5.0,
                        max_orders_per_signal=strategy_data.get('max_orders_per_signal', 4),
                        leverage=float(strategy_data.get('leverage', 10)) if strategy_data.get('leverage') is not None else 10.0,
                        max_net_leverage=float(strategy_data.get('max_net_leverage', 1.5)) if strategy_data.get('max_net_leverage') is not None else 1.5,
                        proportional_position=bool(strategy_data.get('proportional_position', False)),
                        auto_cancel_on_signal_close=bool(strategy_data.get('auto_cancel_on_signal_close', True)),
                        enabled=bool(strategy_data.get('enabled', True)),
                        created_at=strategy_data.get('created_at'),
                        updated_at=strategy_data.get('updated_at')
                    )
                    matching_strategies.append(strategy)
                except Exception as e:
                    logger.error(f"转换策略对象失败: {e}")
                    continue
            
            logger.info(f"找到 {len(matching_strategies)} 个匹配的跟单策略")
            return matching_strategies
            
        except Exception as e:
            logger.error(f"获取跟单策略失败: {e}")
            return []
    
    async def calculate_follow_order_size(self, strategy: LimitFollowStrategy, signal_price: float, signal_size: float, signal_symbol: str = None) -> float:
        """计算跟单订单数量，根据跟单模式调整逻辑"""
        try:
            # 根据跟单模式获取账户关系
            account_relation = await self._get_account_relation(strategy)
            
            # 获取实际可用于跟单的客户资产
            available_balance = await self._get_available_balance_for_follow(account_relation)
            
            if strategy.follow_type == 'percentage':
                # 百分比跟单
                follow_percentage = strategy.follow_value / 100.0
                base_size = signal_size * follow_percentage
                
                # 根据跟单模式调整计算逻辑
                if strategy.is_follow_signal_source():
                    # 跟信号源模式：直接使用计算出的数量
                    follow_size = base_size
                else:
                    # 跟交易员模式：需要考虑信号源账户在客户总资产中的占比
                    follow_size = await self._adjust_size_for_trader_mode(strategy, base_size, available_balance, signal_price)
            else:
                # 固定数量跟单
                follow_size = strategy.follow_value
            
            # 应用最小/最大限制
            min_size = strategy.min_follow_value
            max_size = strategy.max_follow_value
            
            if strategy.follow_type == 'percentage':
                min_size = signal_size * (min_size / 100.0)
                max_size = signal_size * (max_size / 100.0)
            
            follow_size = max(min_size, min(follow_size, max_size))
            
            # 如果启用按比例开仓，根据净杠杆控制调整数量
            if strategy.proportional_position:
                follow_size = await self._adjust_size_by_leverage(strategy, follow_size, signal_price)
            
            # 确保数量符合合约要求（这里需要根据具体合约调整）
            # 对于SPECIFIC策略，使用信号中的实际币种；其他情况使用策略符号
            contract_symbol = signal_symbol if strategy.symbol == 'SPECIFIC' else strategy.symbol
            min_lot_size = get_contract_min_sz(contract_symbol)
            follow_size = round(follow_size / min_lot_size) * min_lot_size
            
            logger.info(f"跟单数量计算: 跟单模式={strategy.follow_mode}, 信号数量={signal_size}, 跟单比例={strategy.follow_value}%, 计算结果={follow_size}")
            return follow_size
            
        except Exception as e:
            logger.error(f"计算跟单数量失败: {e}")
            return 0.0
    
    async def _get_account_relation(self, strategy: LimitFollowStrategy) -> AccountRelation:
        """获取账户关系信息"""
        try:
            # 通过trader_unique_name获取信号源UID
            # 这里假设trader_unique_name就是信号源的source_uid，或者通过数据库查询获取
            signal_source_uid = strategy.trader_unique_name
            
            return AccountRelation(
                strategy=strategy,
                signal_source_uid=signal_source_uid,
                customer_uid=strategy.customer_uid
            )
        except Exception as e:
            logger.error(f"获取账户关系失败: {e}")
            raise
    
    async def _get_available_balance_for_follow(self, account_relation: AccountRelation) -> float:
        """获取可用于跟单的客户账户余额"""
        try:
            # 获取客户账户总资产
            customer_total_balance = await self._get_customer_balance(account_relation.customer_uid)
            
            if account_relation.should_exclude_signal_account():
                # 跟信号源模式：客户账户不包含信号源账户，直接返回客户账户余额
                logger.info(f"跟信号源模式：客户资产={customer_total_balance:.2f}")
                return customer_total_balance
            else:
                # 跟交易员模式：客户账户和带单员账户是独立的，直接返回客户账户余额
                # 资产比例已经在 _adjust_size_for_trader_mode 中处理
                logger.info(f"跟交易员模式：客户资产={customer_total_balance:.2f}，直接使用客户资产作为可用余额")
                return customer_total_balance
        except Exception as e:
            logger.error(f"获取可用跟单余额失败: {e}")
            return 0.0
    
    async def _adjust_size_for_trader_mode(self, strategy: LimitFollowStrategy, base_size: float, 
                                         available_balance: float, signal_price: float) -> float:
        """为跟交易员模式调整订单数量"""
        try:
            # 1) 先按资产比例缩放（客户资产/带单员资产）
            try:
                customer_asset = await self._get_customer_balance(strategy.customer_uid)
                trader_uid = strategy.trader_unique_name
                trader_asset = await self._get_signal_source_balance(trader_uid)
                
                # 确保所有数值都是 float 类型
                customer_asset_float = float(customer_asset) if customer_asset is not None else 0.0
                trader_asset_float = float(trader_asset) if trader_asset is not None else 0.0
                
                if trader_asset_float > 0:
                    asset_ratio = customer_asset_float / trader_asset_float
                else:
                    logger.warning(f"带单员 {trader_uid} 资产为0，使用默认比例1.0")
                    asset_ratio = 1.0
                    
                logger.info(f"资产比例计算: 客户资产={customer_asset_float:.2f}, 带单员资产={trader_asset_float:.2f}, 比例={asset_ratio:.4f}")
            except Exception as e:
                logger.error(f"计算资产比例失败: {e}")
                asset_ratio = 1.0
            scaled_size = base_size * asset_ratio

            # 2) 再按可用余额进行保证金约束（假设10倍杠杆）
            required_margin = scaled_size * signal_price / 10.0
            
            if required_margin > available_balance and required_margin > 0:
                # 如果所需保证金超过可用余额，按比例缩减
                adjustment_ratio = available_balance / required_margin
                adjusted_size = scaled_size * adjustment_ratio
                logger.info(f"跟交易员模式：按资产比例缩放 {scaled_size}，再按保证金约束调整为 {adjusted_size}，调整比例 {adjustment_ratio:.2%}")
                return adjusted_size
            else:
                return scaled_size
        except Exception as e:
            logger.error(f"跟交易员模式订单数量调整失败: {e}")
            return base_size
    
    async def _get_customer_balance(self, customer_uid: str) -> float:
        """获取客户账户余额"""
        try:
            query = """
                SELECT total_asset 
                FROM customers 
                WHERE customer_uid = %s 
            """
            results = self.db_pool.query(query, (customer_uid,))
            
            if results and results[0]['total_asset'] is not None:
                # 确保转换为 float 类型，处理 Decimal 类型
                total_asset_raw = results[0]['total_asset']
                return float(total_asset_raw) if total_asset_raw is not None else 0.0
            else:
                logger.warning(f"客户 {customer_uid} 没有资产信息")
                return 0.0
        except Exception as e:
            logger.error(f"获取客户账户余额失败: {e}")
            return 0.0
    
    async def _get_signal_source_balance(self, signal_source_uid: str) -> float:
        """获取信号源账户余额"""
        try:
            # 从signal_account_assets表获取信号源账户资产
            query = """
                SELECT asset 
                FROM signal_account_assets 
                WHERE signal_source_uid = %s 
                ORDER BY snapshot_time DESC 
                LIMIT 1
            """
            results = self.db_pool.query(query, (signal_source_uid,))
            
            if results and results[0]['asset'] is not None:
                asset_raw = results[0]['asset']
                return float(asset_raw) if asset_raw is not None else 0.0
            else:
                # 回退：尝试从 OKX 公开带单员页面抓取资产
                logger.info(f"信号源 {signal_source_uid} 在数据库中无资产记录，尝试从 OKX API 获取")
                scraped = await self._scrape_okx_trader_public_asset(signal_source_uid)
                if scraped is not None:
                    logger.info(f"从 OKX API 获取到带单员 {signal_source_uid} 资产: {scraped}")
                    return float(scraped)
                logger.warning(f"未找到信号源/带单员 {signal_source_uid} 的资产信息")
                return 0.0
        except Exception as e:
            logger.error(f"获取信号源账户余额失败: {e}")
            return 0.0

    async def _scrape_okx_trader_public_asset(self, trader_unique_name: str) -> Optional[float]:
        """从 OKX 带单员公开 API 获取资产（单位：USDT），失败返回 None。
        使用官方 API: /priapi/v5/ecotrade/public/community/user/asset
        """
        try:
            import requests
            import time
            
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36',
                'Accept': 'application/json, text/plain, */*',
                'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
                'Referer': 'https://www.okx.com/',
                'Origin': 'https://www.okx.com'
            }
            
            # 使用官方 API 接口
            url = "https://www.okx.com/priapi/v5/ecotrade/public/community/user/asset"
            params = {
                'uniqueName': trader_unique_name,
                't': int(time.time() * 1000)  # 添加时间戳
            }
            
            resp = requests.get(url, params=params, headers=headers, timeout=10)
            logger.info(f"OKX API 请求状态: {resp.status_code}")
            
            if resp.status_code != 200:
                logger.warning(f"OKX API 请求失败: {resp.status_code}")
                return None
                
            data = resp.json()
            logger.info(f"OKX API 响应: {data}")
            
            if data.get('code') != '0':
                logger.warning(f"OKX API 返回错误: {data.get('msg', '未知错误')}")
                return None
                
            # 提取 USDT 资产
            assets = data.get('data', [])
            logger.info(f"找到 {len(assets)} 个资产记录")
            
            for asset in assets:
                if asset.get('currency') == 'USDT':
                    amount = float(asset.get('amount', 0))
                    logger.info(f"成功获取 USDT 资产: {amount}")
                    return amount
                    
            logger.warning("未找到 USDT 资产")
            return None
        except Exception:
            return None
    
    async def _adjust_size_by_leverage(self, strategy: LimitFollowStrategy, base_size: float, signal_price: float, signal_symbol: str = None) -> float:
        """根据净杠杆控制调整开仓数量"""
        try:
            customer_uid = strategy.customer_uid
            symbol = strategy.symbol
            
            logger.info(f"按比例开仓: 策略={strategy.strategy_name}, 基础数量={base_size}, 最大净杠杆={strategy.max_net_leverage}")
            
            # 对于ALL或SPECIFIC策略，使用信号中的实际币种；其他情况使用策略配置的币种
            if strategy.symbol in ['ALL', 'SPECIFIC'] and signal_symbol:
                contract_symbol = signal_symbol
            else:
                contract_symbol = strategy.symbol

            # 1. 获取客户当前持仓信息
            # 如果symbol为ALL或SPECIFIC，则不查询特定持仓，使用空列表
            if symbol in ['ALL', 'SPECIFIC']:
                logger.info(f"策略跟随全部交易对或自定义币种，跳过特定持仓查询")
                current_positions = []
            else:
                current_positions = await self._get_customer_positions(customer_uid, symbol)
            
            # 2. 获取客户账户余额和保证金信息
            account_info = await self._get_customer_account_info(customer_uid, symbol)
            
            if not account_info:
                logger.warning(f"无法获取客户账户信息: {customer_uid}")
                return base_size
            
            # 3. 计算当前净杠杆
            current_leverage = self._calculate_current_leverage(current_positions, account_info, signal_price)
            
            # 4. 根据最大净杠杆限制调整数量
            adjusted_size = self._adjust_size_by_leverage_limit(
                base_size, current_leverage, strategy.max_net_leverage, 
                account_info, signal_price, contract_symbol
            )
            
            logger.info(f"净杠杆调整: 当前杠杆={current_leverage:.2f}, 最大杠杆={strategy.max_net_leverage}, 调整后数量={adjusted_size}")
            
            return adjusted_size
            
        except Exception as e:
            logger.error(f"根据净杠杆调整数量失败: {e}")
            return base_size
    
    async def _get_trader_position_info(self, trader_unique_name: str, symbol: str, pos_side: str) -> Dict:
        """获取带单员在指定交易对上的持仓信息"""
        try:
            # 从数据库查询带单员的持仓（使用 trader_trades 表）
            sql = """
                SELECT SUM(volume_contract) as total_volume, 
                       SUM(IFNULL(close_volume_contract, 0)) as closed_volume
                FROM trader_trades 
                WHERE trader_unique_name = %s AND symbol = %s AND pos_side = %s AND status = 'open'
            """
            result = self.db_pool.query(sql, (trader_unique_name, symbol, pos_side))
            
            if not result:
                return {
                    'total_volume': 0.0,
                    'closed_volume': 0.0,
                    'remaining_volume': 0.0,
                    'close_ratio': 0.0
                }
            
            row = result[0]
            total_volume = float(row.get('total_volume', 0))
            closed_volume = float(row.get('closed_volume', 0))
            remaining_volume = max(0.0, total_volume - closed_volume)
            
            # 计算累计平仓比例
            close_ratio = closed_volume / total_volume if total_volume > 0 else 0.0
            
            logger.info(f"带单员 {trader_unique_name} 在 {symbol} {pos_side} 持仓: 总开仓={total_volume}, 已平仓={closed_volume}, 剩余={remaining_volume}, 累计平仓比例={close_ratio:.2%}")
            
            return {
                'total_volume': total_volume,
                'closed_volume': closed_volume,
                'remaining_volume': remaining_volume,
                'close_ratio': close_ratio
            }
            
        except Exception as e:
            logger.error(f"获取带单员持仓失败: {e}")
            return {
                'total_volume': 0.0,
                'closed_volume': 0.0,
                'remaining_volume': 0.0,
                'close_ratio': 0.0
            }

    async def _handle_limit_follow_close(self, strategy: LimitFollowStrategy, symbol: str, pos_side: str, close_ratio: float, signal_order_id: str):
        """处理限价跟单平仓：检查已成交订单并决定撤单还是平仓"""
        try:
            # 查询该策略下该交易对的所有待成交限价单
            sql = """
                SELECT order_uid, order_id, order_size, filled_size, status, target_price
                FROM limit_follow_orders 
                WHERE strategy_id = %s AND symbol = %s AND pos_side = %s 
                AND status IN ('pending', 'live', 'partially_filled')
                ORDER BY created_at ASC
            """
            result = self.db_pool.query(sql, (strategy.id, symbol, pos_side))
            
            if not result:
                logger.info(f"策略 {strategy.strategy_name} 在 {symbol} {pos_side} 上没有待成交的限价单")
                return
            
            logger.info(f"找到 {len(result)} 个待成交的限价单，开始处理平仓")
            
            for order_row in result:
                order_uid = order_row['order_uid']
                exchange_order_id = order_row['order_id']
                order_size = float(order_row['order_size'])
                filled_size = float(order_row['filled_size'] or 0)
                status = order_row['status']
                target_price = float(order_row['target_price'])
                
                logger.info(f"处理订单 {order_uid}: 总数量={order_size}, 已成交={filled_size}, 状态={status}")
                
                if filled_size <= 0:
                    # 完全未成交：直接撤单
                    logger.info(f"订单 {order_uid} 完全未成交，执行撤单")
                    await self._cancel_limit_order(strategy, order_uid, exchange_order_id)
                elif filled_size >= order_size:
                    # 完全成交：直接平仓
                    logger.info(f"订单 {order_uid} 完全成交，执行平仓")
                    await self._close_filled_order(strategy, order_uid, order_size, symbol, pos_side)
                else:
                    # 部分成交：按比例处理
                    remaining_size = order_size - filled_size
                    close_size = remaining_size * close_ratio
                    
                    logger.info(f"订单 {order_uid} 部分成交，剩余={remaining_size}, 按比例{close_ratio:.2%}平仓={close_size}")
                    
                    if close_ratio >= 0.95:
                        # 比例大于95%：先撤单，再平仓已成交部分
                        logger.info(f"平仓比例{close_ratio:.2%}大于95%，先撤单再平仓")
                        await self._cancel_limit_order(strategy, order_uid, exchange_order_id)
                        await self._close_filled_order(strategy, order_uid, filled_size, symbol, pos_side)
                    else:
                        # 比例小于95%：只平仓部分
                        await self._close_partial_order(strategy, order_uid, close_size, symbol, pos_side)
                        
        except Exception as e:
            logger.error(f"处理限价跟单平仓失败: {e}")

    async def _cancel_limit_order(self, strategy: LimitFollowStrategy, order_uid: str, exchange_order_id: str):
        """撤销限价单"""
        max_retries = 3
        retry_delay = 1  # 秒
        
        for attempt in range(max_retries):
            try:
                if not exchange_order_id:
                    logger.warning(f"订单 {order_uid} 没有交易所订单ID，无法撤单")
                    return
                
                # 获取订单信息
                order_info = self.db_pool.query(
                    "SELECT symbol FROM limit_follow_orders WHERE order_uid = %s",
                    (order_uid,)
                )
                
                if not order_info:
                    logger.warning(f"订单 {order_uid} 不存在")
                    return
                
                symbol = order_info[0]['symbol']
                
                # 获取客户账户信息
                customer_info = self.db_pool.query(
                    "SELECT api_key, api_secret, passphrase, is_demo FROM customers WHERE customer_uid = %s",
                    (strategy.customer_uid,)
                )
                
                if not customer_info:
                    logger.error(f"客户 {strategy.customer_uid} 不存在")
                    return
                
                customer_data = customer_info[0]
                
                # 创建REST客户端
                rest_client = create_exchange_client(
                    exchange='okx',
                    client_type='rest',
                    api_key=customer_data['api_key'],
                    api_secret=customer_data['api_secret'],
                    passphrase=customer_data['passphrase'],
                    is_demo=customer_data['is_demo']
                )
                
                # 调用交易所API撤销订单
                logger.info(f"[撤单] 调用REST API撤单: instId={symbol}, ordId={exchange_order_id} (尝试 {attempt + 1}/{max_retries})")
                cancel_result = await rest_client.cancel_order(symbol, ordId=exchange_order_id)
                
                if cancel_result and cancel_result.get('code') == '0':
                    # 更新数据库状态
                    self.db_pool.execute("""
                        UPDATE limit_follow_orders 
                        SET status = 'canceled', updated_at = NOW()
                        WHERE order_uid = %s
                    """, (order_uid,))
                    
                    logger.info(f"订单 {order_uid} 撤单成功")
                    return  # 成功，退出重试循环
                else:
                    error_msg = cancel_result.get('msg', '未知错误') if cancel_result else '请求失败'
                    logger.warning(f"订单 {order_uid} 撤单失败: {error_msg} (尝试 {attempt + 1}/{max_retries})")
                    
                    # 如果是最后一次尝试，记录最终失败
                    if attempt == max_retries - 1:
                        logger.error(f"订单 {order_uid} 撤单最终失败，已重试 {max_retries} 次")
                        return
                    
                    # 等待后重试
                    await asyncio.sleep(retry_delay)
                    
            except Exception as e:
                logger.error(f"撤销订单 {order_uid} 失败 (尝试 {attempt + 1}/{max_retries}): {e}")
                
                # 如果是最后一次尝试，记录最终失败
                if attempt == max_retries - 1:
                    logger.error(f"订单 {order_uid} 撤单最终失败，已重试 {max_retries} 次")
                    return
                
                # 等待后重试
                await asyncio.sleep(retry_delay)

    async def _close_filled_order(self, strategy: LimitFollowStrategy, order_uid: str, filled_size: float, symbol: str, pos_side: str):
        """平仓已成交的订单"""
        try:
            # 创建平仓市价单
            close_order = LimitFollowOrder(
                order_uid=f"CLOSE_{order_uid}",
                strategy_id=strategy.id,
                trader_unique_name=strategy.trader_unique_name,
                customer_uid=strategy.customer_uid,
                symbol=symbol,
                pos_side=pos_side,
                follow_value=0,
                target_price=0,
                order_size=filled_size,
                order_type='market',
                status='pending',
                reduce_only=True
            )
            
            # 保存平仓订单
            if self.limit_follow_db.create_order(close_order):
                logger.info(f"创建平仓订单成功: {close_order.order_uid}")
                # 这里需要调用交易所API执行平仓
                # await self._execute_close_order(close_order)
            else:
                logger.error(f"创建平仓订单失败: {close_order.order_uid}")
                
        except Exception as e:
            logger.error(f"平仓已成交订单 {order_uid} 失败: {e}")

    async def _close_partial_order(self, strategy: LimitFollowStrategy, order_uid: str, close_size: float, symbol: str, pos_side: str):
        """部分平仓订单"""
        try:
            # 创建部分平仓市价单
            close_order = LimitFollowOrder(
                order_uid=f"PARTIAL_CLOSE_{order_uid}",
                strategy_id=strategy.id,
                trader_unique_name=strategy.trader_unique_name,
                customer_uid=strategy.customer_uid,
                symbol=symbol,
                pos_side=pos_side,
                follow_value=0,
                target_price=0,
                order_size=close_size,
                order_type='market',
                status='pending',
                reduce_only=True
            )
            
            # 保存平仓订单
            if self.limit_follow_db.create_order(close_order):
                logger.info(f"创建部分平仓订单成功: {close_order.order_uid}")
                # 这里需要调用交易所API执行平仓
                # await self._execute_close_order(close_order)
            else:
                logger.error(f"创建部分平仓订单失败: {close_order.order_uid}")
                
        except Exception as e:
            logger.error(f"部分平仓订单 {order_uid} 失败: {e}")

    async def _create_limit_orders(self, strategy: LimitFollowStrategy, trade: Dict, follow_side: str, follow_size: float, avg_px: float, ord_id: str) -> List[LimitFollowOrder]:
        """创建限价单"""
        orders = []
        max_orders = strategy.max_orders_per_signal
        size_per_order = follow_size / max_orders
        
        for i in range(max_orders):
            # 计算价格偏移百分比 (1%, 2%, 3%, 4%)
            price_offset_percent = (i + 1) * strategy.min_follow_value / 100.0
            
            # 计算目标价格
            if follow_side == 'long':
                # 多仓跟单：比带单员便宜
                target_price = avg_px * (1 - price_offset_percent)
            else:
                # 空仓跟单：比带单员贵
                target_price = avg_px * (1 + price_offset_percent)
            
            # 创建限价单
            order = LimitFollowOrder(
                order_uid=f"LIMIT_{ord_id}_{strategy.id}_{strategy.customer_uid}_{i+1}",
                strategy_id=strategy.id,
                trader_unique_name=strategy.trader_unique_name,
                customer_uid=strategy.customer_uid,
                symbol=trade.get('instId', ''),
                pos_side=follow_side,
                follow_value=price_offset_percent * 100,
                target_price=target_price,
                order_size=size_per_order,
                order_type='limit',
                status='pending'
            )
            orders.append(order)
        
        return orders

    async def _create_market_orders(self, strategy: LimitFollowStrategy, trade: Dict, follow_side: str, follow_size: float, ord_id: str) -> List[LimitFollowOrder]:
        """创建市价单"""
        order = LimitFollowOrder(
            order_uid=f"MARKET_{ord_id}_{strategy.id}_{strategy.customer_uid}",
            strategy_id=strategy.id,
            trader_unique_name=strategy.trader_unique_name,
            customer_uid=strategy.customer_uid,
            symbol=trade.get('instId', ''),
            pos_side=follow_side,
            follow_value=0,
            target_price=0,
            order_size=follow_size,
            order_type='market',
            status='pending'
        )
        return [order]

    async def _create_mixed_orders(self, strategy: LimitFollowStrategy, trade: Dict, follow_side: str, follow_size: float, avg_px: float, ord_id: str) -> List[LimitFollowOrder]:
        """创建混合订单（限价+市价）"""
        orders = []
        
        # 解析比例配置
        limit_ratio, market_ratio = self._parse_ratio(strategy.limit_market_ratio)
        
        # 计算限价单和市价单的数量
        limit_orders_count = int(strategy.max_orders_per_signal * limit_ratio)
        market_size = follow_size * market_ratio
        limit_size = follow_size * limit_ratio
        
        logger.info(f"混合模式: 限价比例={limit_ratio:.2%}, 市价比例={market_ratio:.2%}")
        logger.info(f"限价单数量={limit_orders_count}, 限价单大小={limit_size}, 市价单大小={market_size}")
        
        # 创建限价单
        if limit_orders_count > 0:
            limit_size_per_order = limit_size / limit_orders_count

            for i in range(limit_orders_count):
                price_offset_percent = (i + 1) * strategy.min_follow_value / 100.0
                
                if follow_side == 'long':
                    target_price = avg_px * (1 - price_offset_percent)
                else:
                    target_price = avg_px * (1 + price_offset_percent)
                
                order = LimitFollowOrder(
                    order_uid=f"MIXED_LIMIT_{ord_id}_{strategy.id}_{strategy.customer_uid}_{i+1}",
                    strategy_id=strategy.id,
                    trader_unique_name=strategy.trader_unique_name,
                    customer_uid=strategy.customer_uid,
                    symbol=trade.get('instId', ''),
                    pos_side=follow_side,
                    follow_value=price_offset_percent * 100,
                    target_price=target_price,
                    order_size=limit_size_per_order,
                    order_type='limit',
                    status='pending'
                )
                orders.append(order)
        
        # 创建市价单
        if market_size > 0:
            order = LimitFollowOrder(
                order_uid=f"MIXED_MARKET_{ord_id}_{strategy.id}_{strategy.customer_uid}",
                strategy_id=strategy.id,
                trader_unique_name=strategy.trader_unique_name,
                customer_uid=strategy.customer_uid,
                symbol=trade.get('instId', ''),
                pos_side=follow_side,
                follow_value=0,
                target_price=0,
                order_size=market_size,
                order_type='market',
                status='pending'
            )
            orders.append(order)
        
        return orders

    async def _handle_market_follow_close(self, strategy: LimitFollowStrategy, symbol: str, pos_side: str, close_ratio: float, signal_order_id: str):
        """按比例处理市价跟单减仓

        规则:
        - 对每一笔已成交的市价跟单订单，按照 filled_size 的 close_ratio 计算应减数量
        - 考虑历史已减数量（limit_close_size），避免重复减仓
        - 创建 reduceOnly 的市价平仓单，并在成功后更新原订单的 limit_close_size 字段
        - 不修改原订单的 status 状态（保持为 filled），只有在完全平仓后才可考虑标记为 closed
        - 跳过小于最小下单单位的碎量，累积到最后一单处理
        """
        try:
            # 查询该策略下该交易对的所有市价单
            sql = """
                SELECT order_uid, exchange_order_id, order_size, filled_size, 
                       IFNULL(limit_close_size, 0) AS limit_close_size,
                       status
                FROM limit_follow_orders 
                WHERE strategy_id = %s AND symbol = %s AND pos_side = %s 
                AND order_type = 'market' AND status IN ('pending', 'live', 'filled')
                ORDER BY created_at ASC
            """
            result = self.db_pool.query(sql, (strategy.id, symbol, pos_side))
            
            if not result:
                logger.info(f"策略 {strategy.strategy_name} 在 {symbol} {pos_side} 上没有市价单")
                return
            
            logger.info(f"找到 {len(result)} 个市价单，开始按比例减仓: ratio={close_ratio}")

            # 获取交易对精度与最小下单单位
            try:
                from config.contract_config import get_min_order_size, get_size_precision
                min_step = get_min_order_size(symbol)
                size_precision = get_size_precision(symbol)
            except Exception:
                min_step = 0
                size_precision = 8

            remainder = 0.0
            
            for idx, order_row in enumerate(result):
                order_uid = order_row['order_uid']
                filled_size = float(order_row['filled_size'] or 0)
                order_size = float(order_row['order_size'])
                already_reduced = float(order_row.get('limit_close_size', 0) or 0)
                
                if filled_size > 0:
                    # 可减剩余 = 已成交 - 已减
                    reducible = max(0.0, filled_size - already_reduced)
                    if reducible <= 0:
                        logger.info(f"订单 {order_uid} 无可减数量(已减={already_reduced}, 成交={filled_size})，跳过")
                        continue

                    # 计算本单应减数量
                    raw_close = reducible * close_ratio + remainder

                    # 四舍五入到交易对精度，并确保不小于最小步进
                    close_size = raw_close
                    if size_precision is not None:
                        close_size = float(f"{close_size:.{size_precision}f}")

                    # 按最小下单单位截断
                    if min_step and min_step > 0:
                        steps = int(close_size / min_step)
                        close_size = steps * min_step
                        remainder = raw_close - close_size
                    else:
                        remainder = 0.0

                    # 最后一单吃掉余数
                    if idx == len(result) - 1 and remainder > 0:
                        close_size += remainder
                        remainder = 0.0

                    # 安全边界：不可超过可减剩余
                    close_size = max(0.0, min(close_size, reducible))

                    if close_size <= 0:
                        logger.info(f"订单 {order_uid} 计算得到的减仓量过小，跳过")
                        continue

                    await self._close_market_order(strategy, order_uid, close_size, symbol, pos_side)
                else:
                    # 未成交，跳过（市价单通常立即成交）
                    logger.info(f"市价单 {order_uid} 未成交，跳过平仓")
                        
        except Exception as e:
            logger.error(f"处理市价跟单平仓失败: {e}")

    async def _close_market_order(self, strategy: LimitFollowStrategy, order_uid: str, close_size: float, symbol: str, pos_side: str):
        """平仓市价单"""
        try:
            # 创建平仓市价单
            close_order = LimitFollowOrder(
                order_uid=f"CLOSE_MARKET_{order_uid}",
                strategy_id=strategy.id,
                trader_unique_name=strategy.trader_unique_name,
                customer_uid=strategy.customer_uid,
                symbol=symbol,
                pos_side=pos_side,
                follow_value=0,
                target_price=0,
                order_size=close_size,
                order_type='market',
                status='pending',
                reduce_only=True
            )
            
            # 保存平仓订单
            if self.limit_follow_db.create_order(close_order):
                logger.info(f"创建市价平仓订单成功: {close_order.order_uid}")
                
                # 获取或创建 limit_follow_service 实例
                if not hasattr(self, 'limit_follow_service'):
                    from limit_follow_service import LimitFollowService
                    self.limit_follow_service = LimitFollowService(self.db_pool)
                
                limit_follow_service = self.limit_follow_service
                
                # 调用交易所API执行平仓
                try:
                    result = await limit_follow_service._submit_order_to_exchange(close_order)
                    if result:
                        logger.info(f"市价平仓订单执行成功: {close_order.order_uid}, 数量={close_size}")
                        
                        # 更新原订单的 limit_close_size 字段（累加），避免重复减仓
                        try:
                            # 使用原子累加操作确保并发安全
                            self.db_pool.execute(
                                "UPDATE limit_follow_orders SET limit_close_size = IFNULL(limit_close_size, 0) + %s, updated_at = NOW() WHERE order_uid = %s",
                                (close_size, order_uid)
                            )
                            
                            # 查询更新后的值用于日志
                            updated_order = self.db_pool.query(
                                "SELECT limit_close_size, filled_size FROM limit_follow_orders WHERE order_uid = %s",
                                (order_uid,)
                            )
                            
                            if updated_order:
                                new_closed = float(updated_order[0].get('limit_close_size', 0) or 0)
                                filled_size = float(updated_order[0].get('filled_size', 0) or 0)
                                
                                logger.info(f"已累加更新原市价订单 {order_uid} 的 limit_close_size: +{close_size}, 累计={new_closed} (filled_size={filled_size})")
                                
                                # 如果完全平仓，可以标记为 closed（但建议通过确认机制）
                                if new_closed >= filled_size:
                                    logger.info(f"订单 {order_uid} 已完全平仓，可考虑标记为 closed")
                        except Exception as e:
                            logger.error(f"更新原市价订单 limit_close_size 失败: {order_uid} - {e}")
                    else:
                        logger.error(f"市价平仓订单执行失败: {close_order.order_uid}")
                except Exception as e:
                    logger.error(f"执行市价平仓订单异常: {close_order.order_uid} - {e}")
            else:
                logger.error(f"创建市价平仓订单失败: {close_order.order_uid}")
                
        except Exception as e:
            logger.error(f"平仓市价单 {order_uid} 失败: {e}")

    async def _record_trader_trade(self, trader_unique_name: str, trade: Dict, trade_direction: str, operation_type: str):
        """记录带单员交易到数据库"""
        try:
            from config.contract_config import get_contract_multiplier
            from database.db import close_trader_trade
            
            symbol = trade.get('instId', '')
            side = trade.get('side', '')
            pos_side = trade.get('posSide', '')
            sz = float(trade.get('sz', '0'))
            avg_px = float(trade.get('avgPx', '0'))
            ord_id = trade.get('ordId', '')
            
            # 计算合约数量
            
            volume_contract = sz
            
            if operation_type == 'open':
                # 开仓时插入新记录
                # 生成交易UID - 缩短长度避免数据库字段超限
                # 使用更短的格式：TRADER_前8位_币种_订单ID前10位_时间戳后6位
                trader_short = trader_unique_name[:8] if len(trader_unique_name) > 8 else trader_unique_name
                symbol_short = symbol.replace('-USDT-SWAP', '').replace('-USDT', '')  # 去掉后缀
                ord_id_short = ord_id[:10] if len(ord_id) > 10 else ord_id
                timestamp_short = int(time.time()) % 1000000  # 取后6位
                trade_uid = f"TRADER_{trader_short}_{symbol_short}_{ord_id_short}_{timestamp_short}"
                
                # 确保trade_uid不超过64个字符
                if len(trade_uid) > 64:
                    # 进一步缩短
                    trade_uid = f"TRADER_{trader_short[:6]}_{symbol_short[:6]}_{ord_id_short[:8]}_{timestamp_short}"
                    if len(trade_uid) > 64:
                        # 最后保险：使用哈希
                        import hashlib
                        hash_suffix = hashlib.md5(f"{trader_unique_name}_{ord_id}_{int(time.time())}".encode()).hexdigest()[:8]
                        trade_uid = f"TRADER_{hash_suffix}"
                
                # 插入开仓记录
                sql = """
                    INSERT INTO trader_trades 
                    (trade_uid, trader_unique_name, symbol, direction, pos_side, volume, volume_contract, 
                     order_id, trade_type, open_px, status, created_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
                """
                
                # 计算USDT数量
                volume_usdt = sz * avg_px * get_contract_multiplier(symbol)
                
                self.db_pool.execute(sql, (
                    trade_uid,
                    trader_unique_name,
                    symbol,
                    side,
                    pos_side,
                    volume_usdt,
                    volume_contract,
                    ord_id,
                    operation_type,
                    avg_px,
                    'open'
                ))
                
                logger.info(f"记录带单员开仓: {trader_unique_name} {sz}张 {symbol} @ {avg_px}")
                
            elif operation_type == 'close':
                # 平仓时先记录交易信息，但不立即更新状态
                # 等跟单操作完成后再更新状态
                logger.info(f"检测到带单员平仓: {trader_unique_name} {sz}张 {symbol} @ {avg_px}")
                logger.info(f"平仓信息已记录，将在跟单完成后更新数据库状态")
            
        except Exception as e:
            logger.error(f"记录带单员交易失败: {e}")

    async def _update_trader_close_status(self, trader_unique_name: str, trade: Dict, trade_direction: str):
        """在跟单完成后更新带单员平仓状态"""
        try:
            from database.db import close_trader_trade
            
            symbol = trade.get('instId', '')
            pos_side = trade.get('posSide', '')
            sz = float(trade.get('sz', '0'))
            avg_px = float(trade.get('avgPx', '0'))
            ord_id = trade.get('ordId', '')
            
            # 查找对应的开仓记录进行更新
            open_trades = self.db_pool.query("""
                SELECT trade_uid FROM trader_trades 
                WHERE trader_unique_name = %s AND symbol = %s AND pos_side = %s 
                AND trade_type = 'open' AND status = 'open'
                ORDER BY created_at ASC
                LIMIT 1
            """, (trader_unique_name, symbol, pos_side))
            
            if open_trades:
                trade_uid = open_trades[0]['trade_uid']
                # 计算盈亏（简化计算）
                profit = 0  # 暂时设为0，后续可以根据开仓价格计算
                close_trader_trade(self.db_pool, trade_uid, ord_id, avg_px, profit)
                logger.info(f"[跟单完成后] 更新带单员平仓状态: {trader_unique_name} {sz}张 {symbol} @ {avg_px}")
            else:
                logger.warning(f"[跟单完成后] 未找到带单员开仓记录: {trader_unique_name} {symbol} {pos_side}")
                
        except Exception as e:
            logger.error(f"更新带单员平仓状态失败: {e}")

    async def _get_customer_positions(self, customer_uid: str, symbol: str) -> List[Dict]:
        """获取客户当前持仓"""
        try:
            # 直接从OKX API获取实时持仓信息
            if not hasattr(self, 'limit_follow_service'):
                from limit_follow_service import LimitFollowService
                self.limit_follow_service = LimitFollowService(self.db_pool)
            
            # 获取客户持仓
            positions = await self.limit_follow_service._get_customer_positions(customer_uid, symbol)
            
            if not positions:
                logger.info(f"客户 {customer_uid} 在 {symbol} 上没有持仓")
                return []
            
            logger.info(f"获取到客户 {customer_uid} 在 {symbol} 上的 {len(positions)} 个持仓")
            return positions
            
        except Exception as e:
            logger.error(f"获取客户持仓失败: {e}")
            return []
    
    async def _get_customer_account_info(self, customer_uid, symbol: str) -> Optional[Dict]:
        """获取客户账户信息（从数据库获取）"""
        try:
            # 从数据库获取客户账户信息
            query = """
                SELECT total_asset, leverage, is_demo
                FROM customers 
                WHERE customer_uid = %s AND enabled = 1
            """
            results = self.db_pool.query(query, (customer_uid,))
            
            if not results:
                logger.warning(f"客户 {customer_uid} 不存在或已禁用")
                return None
            
            customer_data = results[0]
            
            # 构建账户信息
            account_info = {
                'total_balance': float(customer_data.get('total_asset', 0)) if customer_data.get('total_asset') is not None else 0.0,
                'available_balance': float(customer_data.get('total_asset', 0)) if customer_data.get('total_asset') is not None else 0.0,
                'leverage': customer_data.get('leverage', 1),
                'is_demo': bool(customer_data.get('is_demo', False)),
                'customer_uid': customer_uid,
                'currency': 'USDT'
            }
            
            logger.info(f"客户账户信息: {account_info}")
            return account_info
            
        except Exception as e:
            logger.error(f"获取客户账户信息失败: {e}")
            return None
    
    def _calculate_current_leverage(self, positions: List[Dict], account_info: Dict, current_price: float) -> float:
        """计算当前净杠杆"""
        try:
            if not positions or not account_info:
                return 0.0
            
            # 计算总持仓价值
            total_position_value = 0.0
            for position in positions:
                # 确保pos_size是float类型
                pos_size_raw = position.get('pos', 0)
                pos_size = float(pos_size_raw) if pos_size_raw is not None else 0.0
                pos_side = position.get('pos_side', 'long')
                
                # 根据持仓方向计算价值
                if pos_side == 'long':
                    position_value = pos_size * current_price
                else:  # short
                    position_value = pos_size * current_price
                
                total_position_value += position_value
            
            # 获取可用保证金，确保是float类型
            available_margin_raw = account_info.get('available_balance', 0)
            available_margin = float(available_margin_raw) if available_margin_raw is not None else 0.0
            
            if available_margin <= 0:
                logger.warning("可用保证金为0，无法计算杠杆")
                return float('inf')  # 返回无穷大表示风险极高
            
            # 计算净杠杆 = 总持仓价值 / 可用保证金
            current_leverage = total_position_value / available_margin
            
            logger.info(f"杠杆计算: 总持仓价值={total_position_value:.2f}, 可用保证金={available_margin:.2f}, 当前杠杆={current_leverage:.2f}")
            
            return current_leverage
            
        except Exception as e:
            logger.error(f"计算当前杠杆失败: {e}")
            return 0.0
    
    def _adjust_size_by_leverage_limit(self, base_size: float, current_leverage: float, 
                                     max_leverage: float, account_info: Dict, signal_price: float, symbol: str = 'BTC-USDT-SWAP') -> float:
        """根据最大杠杆限制调整开仓数量"""
        try:
            if current_leverage >= max_leverage:
                logger.warning(f"当前杠杆 {current_leverage:.2f} 已达到最大限制 {max_leverage}, 不允许开新仓")
                return 0.0
            
            # 计算剩余可用杠杆
            remaining_leverage = max_leverage - current_leverage
            
            # 获取可用保证金，确保是float类型
            available_margin_raw = account_info.get('available_balance', 0)
            available_margin = float(available_margin_raw) if available_margin_raw is not None else 0.0
            
            logger.info(f"杠杆调整调试: 账户信息={account_info}, 可用保证金={available_margin}")
            
            # 计算基于剩余杠杆的最大可开仓价值
            max_position_value = available_margin * remaining_leverage
            
            # 计算基于剩余杠杆的最大可开仓数量（币数）
            max_position_size_in_currency = max_position_value / signal_price
            
            # 转换为张数（需要合约乘数）
            from config.contract_config import get_contract_multiplier
            multiplier = get_contract_multiplier(symbol)
            max_position_size = max_position_size_in_currency / multiplier
            
            # 取较小值作为最终开仓数量
            adjusted_size = min(base_size, max_position_size)
            
            # 确保数量不为负数
            adjusted_size = max(0, adjusted_size)
            
            logger.info(f"杠杆限制调整: 剩余杠杆={remaining_leverage:.2f}, 最大可开仓价值={max_position_value:.2f}, 最大可开仓币数={max_position_size_in_currency:.6f}, 最大可开仓张数={max_position_size:.2f}, 调整后数量={adjusted_size}")
            
            return adjusted_size
            
        except Exception as e:
            logger.error(f"根据杠杆限制调整数量失败: {e}")
            return base_size
    
    async def create_follow_orders(self, strategy: LimitFollowStrategy, trade: Dict, trade_direction: str, operation_type: str = 'open') -> List[LimitFollowOrder]:
        """创建跟单订单 - 按价格偏移策略"""
        try:
            side = trade.get('side', '')
            sz = float(trade.get('sz', '0'))
            avg_px = float(trade.get('avgPx', '0'))
            inst_id = trade.get('instId', '')
            ord_id = trade.get('ordId', '')
            
            # 使用传入的trade_direction
            follow_side = trade_direction
            
            # 🆕 反向跟单逻辑：如果启用了反向跟单，反转开仓方向
            if strategy.reverse_direction:
                if follow_side == 'long':
                    follow_side = 'short'
                    logger.info(f"🔄 反向跟单已启用：信号源做多 → 跟单做空")
                elif follow_side == 'short':
                    follow_side = 'long'
                    logger.info(f"🔄 反向跟单已启用：信号源做空 → 跟单做多")
                else:
                    logger.warning(f"⚠️ 未知的跟单方向: {follow_side}，无法反转")
            
            # 检查是否应该跟单这个币种
            should_follow = False
            if strategy.symbol == 'SPECIFIC':
                # SPECIFIC模式：检查信号币种是否在策略的symbols列表中
                if strategy.symbols and inst_id in strategy.symbols:
                    should_follow = True
                    logger.info(f"SPECIFIC策略匹配: 信号币种 {inst_id} 在策略币种列表 {strategy.symbols} 中")
                else:
                    logger.info(f"SPECIFIC策略不匹配: 信号币种 {inst_id} 不在策略币种列表 {strategy.symbols} 中")
            elif strategy.symbol == 'ALL':
                # ALL模式：跟单所有币种
                should_follow = True
                logger.info(f"ALL策略: 跟单所有币种 {inst_id}")
            else:
                # 特定币种模式：检查是否匹配
                if strategy.symbol == inst_id:
                    should_follow = True
                    logger.info(f"特定币种策略匹配: {inst_id}")
                else:
                    logger.info(f"特定币种策略不匹配: 策略币种 {strategy.symbol} != 信号币种 {inst_id}")
            
            if not should_follow:
                logger.info(f"策略 {strategy.strategy_name} 不匹配信号币种 {inst_id}，跳过创建订单")
                return []
            
            # 如果是平仓操作，检查带单员是否有对应持仓
            if operation_type == 'close':
                # 获取带单员持仓信息（包含累计平仓比例）
                position_info = await self._get_trader_position_info(strategy.trader_unique_name, inst_id, trade_direction)
                trader_position_size = position_info['remaining_volume']
                total_volume = position_info['total_volume']
                current_close_ratio = position_info['close_ratio']
                
                if trader_position_size <= 0:
                    logger.info(f"带单员 {strategy.trader_unique_name} 在 {inst_id} 上没有 {trade_direction} 持仓，跳过平仓跟单")
                    return []
                
                # 计算本次平仓比例
                current_close_ratio = sz / trader_position_size if trader_position_size > 0 else 0
                logger.info(f"带单员 {strategy.trader_unique_name} 在 {inst_id} 上有 {trader_position_size} 张 {trade_direction} 持仓，本次平仓 {sz} 张，本次平仓比例: {current_close_ratio:.2%}")
                
                # 如果本次平仓比例小于5%，认为是减仓操作
                if current_close_ratio < 0.05:
                    logger.info(f"本次平仓比例 {current_close_ratio:.2%} 小于5%，视为减仓操作，跳过跟单")
                    return []
                
                # 计算平仓后的累计比例
                future_close_ratio = (position_info['closed_volume'] + sz) / total_volume if total_volume > 0 else 0
                logger.info(f"平仓后累计比例: {future_close_ratio:.2%}")
                
                # 如果平仓后累计比例大于95%，视为全平仓
                if future_close_ratio >= 0.95:
                    logger.info(f"平仓后累计比例 {future_close_ratio:.2%} 超过95%，视为全平仓操作")
                    close_ratio = 1.0  # 强制设为100%
                else:
                    close_ratio = current_close_ratio
            
            # 计算跟单数量
            if operation_type == 'close':
                # 平仓操作：按平仓比例计算跟单数量
                # 先计算基础跟单数量
                base_follow_size = await self.calculate_follow_order_size(strategy, avg_px, sz, inst_id)
                # 再按平仓比例调整
                follow_size = base_follow_size * close_ratio
                logger.info(f"平仓跟单数量计算: 基础数量={base_follow_size}, 平仓比例={close_ratio:.2%}, 最终数量={follow_size}")
            else:
                # 开仓操作：按策略配置的百分比计算
                follow_size = await self.calculate_follow_order_size(strategy, avg_px, sz, inst_id)
            
            if follow_size <= 0:
                logger.warning(f"跟单数量为0，跳过创建订单")
                return []
            
            # 创建跟单订单
            orders = []
            max_orders = strategy.max_orders_per_signal
            
            # 根据操作类型创建订单
            if operation_type == 'close':
                # 平仓操作：根据订单类型分别处理
                if strategy.follow_order_types == 'limit_only':
                    await self._handle_limit_follow_close(strategy, inst_id, follow_side, close_ratio, ord_id)
                elif strategy.follow_order_types == 'market_only':
                    await self._handle_market_follow_close(strategy, inst_id, follow_side, close_ratio, ord_id)
                elif strategy.follow_order_types == 'both':
                    # 混合模式：分别处理限价单和市价单
                    await self._handle_limit_follow_close(strategy, inst_id, follow_side, close_ratio, ord_id)
                    await self._handle_market_follow_close(strategy, inst_id, follow_side, close_ratio, ord_id)
                return []  # 平仓操作不创建新订单，而是处理现有订单
            else:
                # 开仓操作：根据 follow_order_types 创建订单
                if strategy.follow_order_types == 'limit_only':
                    # 限价模式：创建多个限价单
                    orders = await self._create_limit_orders(strategy, trade, follow_side, follow_size, avg_px, ord_id)
                elif strategy.follow_order_types == 'market_only':
                    # 市价模式：创建市价单
                    orders = await self._create_market_orders(strategy, trade, follow_side, follow_size, ord_id)
                elif strategy.follow_order_types == 'both':
                    # 混合模式：创建限价单+市价单
                    orders = await self._create_mixed_orders(strategy, trade, follow_side, follow_size, avg_px, ord_id)
                else:
                    # 默认限价模式（向后兼容）
                    logger.warning(f"未知的跟单类型: {strategy.follow_order_types}，使用默认限价模式")
                    orders = await self._create_limit_orders(strategy, trade, follow_side, follow_size, avg_px, ord_id)
                    
                # 如果已经通过特定方法创建了订单，跳过通用创建逻辑
                if orders:
                    return orders
                for i in range(max_orders):
                    # 计算价格偏移百分比 (1%, 2%, 3%, 4%)
                    price_offset_percent = (i + 1) * strategy.min_follow_value / 100.0
                    
                    # 计算目标价格
                    if follow_side == 'long':
                        # 多仓跟单：比跟单员便宜
                        target_price = avg_px * (1 - price_offset_percent)
                    else:
                        # 空仓跟单：比跟单员贵
                        target_price = avg_px * (1 + price_offset_percent)
                    
                    # 订单数量就是计算出的 follow_size（所有订单数量相同）
                    order_size = follow_size
                    
                    # 创建订单对象
                    order = LimitFollowOrder(
                        order_uid=f"FOLLOW_{ord_id}_{strategy.id}_{strategy.customer_uid}_{i+1}",
                        strategy_id=strategy.id,
                        trader_unique_name=strategy.trader_unique_name,
                        customer_uid=strategy.customer_uid,
                        symbol=inst_id,
                        pos_side=follow_side,
                        follow_value=price_offset_percent * 100,  # 记录实际使用的偏移百分比
                        target_price=target_price,
                        order_size=order_size,
                        order_type='limit',
                        status='pending'
                    )
                    orders.append(order)
            
            return orders
            
        except Exception as e:
            logger.error(f"创建跟单订单失败: {e}")
            return []
    
    async def _check_margin_before_order(self, order: LimitFollowOrder, signal_price: float) -> bool:
        """在下单前检查保证金是否充足"""
        try:
            # 获取客户实时余额
            customer_balance = await self._get_customer_balance(order.customer_uid)
            
            # 获取策略杠杆设置
            if not hasattr(self, 'limit_follow_service'):
                from limit_follow_service import LimitFollowService
                self.limit_follow_service = LimitFollowService(self.db_pool)
            
            leverage = await self.limit_follow_service._get_strategy_leverage(order.strategy_id, order.customer_uid)
            
            # 计算所需保证金
            from config.contract_config import get_contract_multiplier
            multiplier = get_contract_multiplier(order.symbol)
            required_margin = order.order_size * multiplier * signal_price / leverage
            
            # 添加安全缓冲
            safety_buffer = 1.15  # 15%安全缓冲
            required_margin_with_buffer = required_margin * safety_buffer
            
            logger.info(f"下单前保证金检查: 订单={order.order_uid}, 数量={order.order_size}, 价格={signal_price}")
            logger.info(f"保证金需求: 基础={required_margin:.2f} USDT, 含缓冲={required_margin_with_buffer:.2f} USDT, 客户余额={customer_balance:.2f} USDT")
            
            if required_margin_with_buffer > customer_balance:
                logger.error(f"保证金不足，取消订单: {order.order_uid}, 需要={required_margin_with_buffer:.2f} USDT, 可用={customer_balance:.2f} USDT")
                return False
            
            logger.info(f"保证金充足，可以下单: {order.order_uid}")
            return True
            
        except Exception as e:
            logger.error(f"保证金检查失败: {e}")
            return False

    async def execute_follow_orders(self, orders: List[LimitFollowOrder]) -> bool:
        """执行跟单订单"""
        try:
            success_count = 0
            
            # 使用已初始化的限价跟单服务
            if not hasattr(self, 'limit_follow_service'):
                from core.limit_trade.limit_follow_service import LimitFollowService
                self.limit_follow_service = LimitFollowService(self.db_pool)
            
            limit_follow_service = self.limit_follow_service
            
            for i, order in enumerate(orders):
                logger.info(f"执行第 {i+1}/{len(orders)} 个订单: {order.order_uid}")
                
                # 在下单前检查保证金
                signal_price = order.target_price if order.target_price > 0 else 180.74  # 使用目标价格或默认价格
                if not await self._check_margin_before_order(order, signal_price):
                    logger.warning(f"保证金不足，跳过订单: {order.order_uid}")
                    continue
                # 保存订单到数据库
                if self.limit_follow_db.create_order(order):
                    logger.info(f"跟单订单创建成功: {order.order_uid}")
                    
                    # 向交易所发送实际订单
                    import asyncio
                    try:
                        # 尝试获取现有事件循环
                        loop = asyncio.get_event_loop()
                        if loop.is_running():
                            # 如果事件循环正在运行，创建任务
                            task = loop.create_task(limit_follow_service._submit_order_to_exchange(order))
                            # 等待任务完成
                            result = await task
                        else:
                            # 如果事件循环没有运行，运行到完成
                            result = asyncio.run(limit_follow_service._submit_order_to_exchange(order))
                    except RuntimeError:
                        # 如果没有事件循环，创建一个新的
                        result = asyncio.run(limit_follow_service._submit_order_to_exchange(order))
                    
                    if result:
                        success_count += 1
                        logger.success(f"跟单订单发送到交易所成功: {order.order_uid}")
                        
                        # 记录成功日志
                        from model.limit_follow_models import LimitFollowLog
                        log_entry = LimitFollowLog(
                            log_level='INFO',
                            message=f'跟单订单发送到交易所成功: {order.order_uid}',
                            order_uid=order.order_uid,
                            strategy_id=order.strategy_id,
                            customer_uid=order.customer_uid,
                            trader_unique_name=order.trader_unique_name,
                            extra_data={
                                'target_price': order.target_price,
                                'order_size': order.order_size,
                                'follow_value': order.follow_value,
                                'status': 'sent_to_exchange'
                            }
                        )
                        self.limit_follow_db.add_log(log_entry)
                    else:
                        logger.error(f"跟单订单发送到交易所失败: {order.order_uid}")
                        
                        # 记录失败日志
                        from model.limit_follow_models import LimitFollowLog
                        log_entry = LimitFollowLog(
                            log_level='ERROR',
                            message=f'跟单订单发送到交易所失败: {order.order_uid}',
                            order_uid=order.order_uid,
                            strategy_id=order.strategy_id,
                            customer_uid=order.customer_uid,
                            trader_unique_name=order.trader_unique_name,
                            extra_data={
                                'target_price': order.target_price,
                                'order_size': order.order_size,
                                'follow_value': order.follow_value,
                                'status': 'exchange_failed'
                            }
                        )
                        self.limit_follow_db.add_log(log_entry)
                else:
                    logger.error(f"跟单订单创建失败: {order.order_uid}")
            
            logger.info(f"跟单订单执行完成: {success_count}/{len(orders)} 成功")
            return success_count > 0
            
        except Exception as e:
            logger.error(f"执行跟单订单失败: {e}")
            return False
    
    async def process_new_trade(self, trader_unique_name: str, trade: Dict):
        """处理新交易"""
        try:
            side = trade.get('side', '')
            pos_side = trade.get('posSide', '')
            sz = float(trade.get('sz', '0'))
            avg_px = float(trade.get('avgPx', '0'))
            inst_id = trade.get('instId', '')
            ord_id = trade.get('ordId', '')
            
            logger.info(f"处理新交易: {trader_unique_name} {side} {sz} {inst_id} @ {avg_px}, posSide: {pos_side}")
            
            # 只处理posSide为long或short的情况，其他情况跳过
            if pos_side not in ['long', 'short']:
                logger.info(f"跳过非双向开仓模式: posSide={pos_side}")
                return
            
            # 确定持仓方向和操作类型
            trade_direction, operation_type = self._analyze_trade_direction(side, pos_side)
            
            if not trade_direction:
                logger.error(f"无法确定交易方向: side={side}, posSide={pos_side}")
                return
            
            # 处理开仓和平仓操作
            logger.info(f"交易解析结果: 方向={trade_direction}, 操作类型={operation_type}")
            
            # 记录带单员交易到数据库
            await self._record_trader_trade(trader_unique_name, trade, trade_direction, operation_type)
            
            # 获取跟单策略
            strategies = self.get_follow_strategies(trader_unique_name, inst_id, trade_direction)
            
            if not strategies:
                logger.info(f"没有找到匹配的跟单策略: {trader_unique_name} {inst_id} {trade_direction}")
                return
            
            # 为每个策略创建跟单订单
            for strategy in strategies:
                logger.info(f"执行跟单策略: {strategy.strategy_name} (客户: {strategy.customer_uid})")
                
                # 创建跟单订单
                orders = await self.create_follow_orders(strategy, trade, trade_direction, operation_type)
                
                if orders:
                    logger.info(f"创建了 {len(orders)} 个跟单订单")
                    
                    # 执行跟单订单
                    try:
                        result = await self.execute_follow_orders(orders)
                        if result:
                            logger.info(f"跟单策略执行成功: {strategy.strategy_name}")  # 修复：改为 info
                        else:
                            logger.error(f"跟单策略执行失败: {strategy.strategy_name}")
                    except Exception as e:
                        logger.error(f"执行跟单策略失败: {strategy.strategy_name} - {e}")
                        # 继续执行下一个策略，不要中断
                        continue
                else:
                    logger.warning(f"没有创建任何跟单订单: {strategy.strategy_name}")
            
            # 如果是平仓操作，在跟单完成后更新带单员状态
            if operation_type == 'close':
                await self._update_trader_close_status(trader_unique_name, trade, trade_direction)
            
        except Exception as e:
            logger.error(f"处理新交易失败: {e}")
    def _analyze_trade_direction(self, side: str, pos_side: str) -> tuple:
        """
        分析交易方向和操作类型（只处理双向开仓模式）
        
        Args:
            side: 交易方向 ('buy' 或 'sell')
            pos_side: 持仓方向 ('long' 或 'short')
        
        Returns:
            tuple: (trade_direction, operation_type)
            - trade_direction: 'long' 或 'short' 或 None
            - operation_type: 'open' 或 'close'
        """
        try:
            # 只处理双向开仓模式
            if pos_side == 'long':
                if side == 'buy':
                    return 'long', 'open'  # 开多仓
                elif side == 'sell':
                    return 'long', 'close'  # 平多仓
                else:
                    return None, None
            
            elif pos_side == 'short':
                if side == 'sell':
                    return 'short', 'open'  # 开空仓（卖出开空）
                elif side == 'buy':
                    return 'short', 'close'  # 平空仓（买入平空）
                else:
                    return None, None
            
            else:
                # 这里不应该到达，因为外层已经过滤了
                logger.warning(f"意外的posSide: {pos_side}")
                return None, None
                
        except Exception as e:
            logger.error(f"分析交易方向失败: {e}")
            return None, None

    # 同步检查方法已删除，使用异步方法替代
    
    async def check_trader_async(self, session: aiohttp.ClientSession, trader_unique_name: str):
        """异步检查单个跟单员"""
        try:
            logger.info(f"检查跟单员: {trader_unique_name}")
            
            # 获取对应的采集器
            collector = self._get_collector_for_trader(trader_unique_name)
            if not collector:
                logger.warning(f"无法获取带单员 {trader_unique_name} 的采集器，跳过检查")
                return
            
            # 异步获取交易记录（已标准化）
            trades = await self.get_trade_records_async(session, trader_unique_name, self.config['trade_limit'])
            new_trades = []
            
            if trades:
                # 获取最新一条交易（已经是标准化格式）
                latest_trade = trades[0]
                ord_id = latest_trade.get('ordId', '')
                
                if ord_id:
                    # 检查是否是新的订单ID
                    last_ord_id = self.last_ord_ids.get(trader_unique_name, '')
                    
                    if ord_id != last_ord_id:
                        # 新的订单ID，添加到新交易列表
                        new_trades.append(latest_trade)
                        # 更新最后处理的订单ID
                        self.last_ord_ids[trader_unique_name] = ord_id
                        
                        # 记录到日志
                        self._log_new_trade(trader_unique_name, latest_trade)
                        
                        logger.info(f"[{collector.get_collector_type()}] 发现新交易: {trader_unique_name} - {ord_id}")
                    else:
                        logger.debug(f"订单已处理: {trader_unique_name} - {ord_id}")
            
            if new_trades:
                logger.info(f"发现 {len(new_trades)} 笔新交易")
                for trade in new_trades:
                    await self.process_new_trade(trader_unique_name, trade)
            else:
                logger.debug(f"没有新交易")
                
        except Exception as e:
            logger.error(f"检查跟单员失败: {e}")
    
    def get_monitored_traders(self) -> List[str]:
        """获取所有被监控的跟单员"""
        try:
            # 检查数据库连接池是否可用
            if self.db_pool is None:
                logger.error("数据库连接池不可用，无法获取被监控的跟单员")
                return []
            
            # 从数据库获取所有启用的策略中的跟单员
            query = """
                SELECT DISTINCT trader_unique_name 
                FROM limit_follow_strategies 
                WHERE enabled = 1 
                AND follow_mode = 'follow_trader'
            """
            # 修复：传递空元组作为参数，因为查询没有占位符
            records = self.db_pool.query(query, ())
            
            traders = [record['trader_unique_name'] for record in records]
            logger.info(f"获取到 {len(traders)} 个被监控的跟单员")
            
            return traders
            
        except Exception as e:
            logger.error(f"获取被监控跟单员失败: {e}")
            return []
    
    def clear_collector_cache(self, trader_unique_name: Optional[str] = None):
        """
        清除采集器缓存
        
        Args:
            trader_unique_name: 如果提供，只清除该带单员的缓存；否则清除所有缓存
        """
        if trader_unique_name:
            if trader_unique_name in self.collectors_cache:
                del self.collectors_cache[trader_unique_name]
                logger.info(f"已清除带单员 {trader_unique_name} 的采集器缓存")
        else:
            self.collectors_cache.clear()
            logger.info("已清除所有采集器缓存")
    
    # 同步监控方法已删除，使用异步方法替代
    
    async def run_monitoring_async(self):
        """运行并发监控"""
        logger.info("开始并发限价跟单监控...")
        
        # 确保使用当前事件循环（在 Gunicorn/gevent 环境中可能需要 nest_asyncio）
        try:
            loop = asyncio.get_running_loop()
            logger.debug(f"使用运行中的事件循环: {loop}")
        except RuntimeError:
            # 如果没有运行的事件循环，获取或创建新的
            try:
                loop = asyncio.get_event_loop()
                if loop.is_closed():
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                logger.debug(f"获取或创建事件循环: {loop}")
            except RuntimeError:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                logger.debug(f"创建新事件循环: {loop}")
        
        # 创建HTTP会话（使用当前事件循环）
        async with aiohttp.ClientSession() as session:
            while True:
                try:
                    # 获取被监控的跟单员
                    traders = self.get_monitored_traders()
                    
                    if not traders:
                        logger.info("没有需要监控的跟单员")
                        # 使用当前事件循环的 sleep
                        await asyncio.sleep(self.config['polling_interval'])
                        continue
                    
                    logger.info(f"开始并发检查 {len(traders)} 个跟单员...")
                    
                    # 创建所有跟单员的检查任务
                    tasks = []
                    for trader in traders:
                        task = self.check_trader_async(session, trader)
                        tasks.append(task)
                    
                    # 并发执行所有任务
                    start_time = time.time()
                    await asyncio.gather(*tasks, return_exceptions=True)
                    end_time = time.time()
                    
                    execution_time = end_time - start_time
                    logger.info(f"并发检查完成，耗时: {execution_time:.2f} 秒")
                    
                    # 等待下次轮询
                    interval = self.config['polling_interval']
                    logger.info(f"等待 {interval} 秒后进行下次检查...")
                    await asyncio.sleep(interval)
                    
                except KeyboardInterrupt:
                    logger.info("监控已停止")
                    break
                except RuntimeError as e:
                    # 检查是否是事件循环关闭错误
                    error_msg = str(e).lower()
                    if "attached to a different loop" in error_msg:
                        # 事件循环不匹配，尝试恢复
                        logger.warning(f"⚠️ 事件循环不匹配，尝试恢复: {e}")
                        try:
                            # 等待一小段时间，让事件循环稳定
                            import time
                            time.sleep(0.5)
                            # 尝试重新获取事件循环
                            try:
                                current_loop = asyncio.get_running_loop()
                                logger.debug(f"当前事件循环: {current_loop}")
                            except RuntimeError:
                                # 如果没有运行中的循环，获取或创建新的
                                try:
                                    current_loop = asyncio.get_event_loop()
                                    if current_loop.is_closed():
                                        current_loop = asyncio.new_event_loop()
                                        asyncio.set_event_loop(current_loop)
                                except RuntimeError:
                                    current_loop = asyncio.new_event_loop()
                                    asyncio.set_event_loop(current_loop)
                                logger.debug(f"获取或创建事件循环: {current_loop}")
                            
                            # 继续监控循环
                            logger.info("✅ 事件循环已恢复，继续监控")
                            continue
                        except Exception as recover_error:
                            logger.error(f"❌ 无法恢复事件循环: {recover_error}")
                            import traceback
                            logger.error(traceback.format_exc())
                            break
                    elif "closed" in error_msg or "no running event loop" in error_msg:
                        logger.error(f"事件循环错误，监控将停止: {e}")
                        # 尝试重新获取事件循环
                        try:
                            loop = asyncio.get_running_loop()
                            if loop.is_closed():
                                logger.error("事件循环已关闭，无法继续监控")
                                break
                        except RuntimeError:
                            logger.error("无法获取事件循环，监控将停止")
                            break
                    else:
                        # 其他 RuntimeError，记录并继续
                        logger.error(f"监控异常: {e}")
                        import traceback
                        logger.error(traceback.format_exc())
                        try:
                            # 确保事件循环仍然有效
                            loop = asyncio.get_running_loop()
                            if loop.is_closed():
                                logger.error("事件循环已关闭，无法继续监控")
                                break
                            await asyncio.sleep(10)  # 异常后等待10秒再继续
                        except RuntimeError as sleep_e:
                            logger.error(f"无法继续等待，监控将停止: {sleep_e}")
                            break
                except Exception as e:
                    logger.error(f"监控异常: {e}")
                    import traceback
                    logger.error(traceback.format_exc())
                    # 异常后等待，但需要检查事件循环是否仍然有效
                    try:
                        loop = asyncio.get_running_loop()
                        if loop.is_closed():
                            logger.error("事件循环已关闭，无法继续监控")
                            break
                        await asyncio.sleep(10)  # 异常后等待10秒再继续
                    except RuntimeError:
                        logger.error("无法获取事件循环，监控将停止")
                        break


async def main():
    """主函数"""
    # 初始化数据库连接
    from config import get_mysql_config
    db_pool = MySQLPool(
        **get_mysql_config()
    )
    
    # 创建跟单执行器
    executor = LimitFollowExecutor(db_pool)
    
    # 开始监控
    await executor.run_monitoring_async()

def main_sync():
    """同步主函数"""
    asyncio.run(main())

if __name__ == "__main__":
    main_sync() 