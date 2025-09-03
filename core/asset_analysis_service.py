"""
资产分析服务
用于管理资产波动数据的获取、存储和分析
"""

import asyncio
import json
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from database.db import get_db_pool
from model.asset_analysis_models import (
    AssetSnapshot, AssetTrend, AssetAnalysis, ExchangeAssetSummary, AssetAnalysisUtils
)
from exchange.okx.okx_asset_analysis import get_okx_asset_analyzer
from utils.logger import logger


class AssetAnalysisService:
    """资产分析服务"""
    
    def __init__(self):
        self.db_pool = None
        self.analysis_cache = {}
        self.cache_expiry = 300  # 5分钟缓存过期
    
    async def get_db_pool(self):
        """获取数据库连接池"""
        if not self.db_pool:
            self.db_pool = await get_db_pool()
        return self.db_pool
    
    async def create_asset_snapshot(self, customer_uid: str, exchange: str, 
                                  balance_data: Dict[str, Any], positions_data: Dict[str, Any],
                                  risk_data: Dict[str, Any]) -> Optional[AssetSnapshot]:
        """创建资产快照
        
        Args:
            customer_uid: 客户UID
            exchange: 交易所
            balance_data: 余额数据
            positions_data: 持仓数据
            risk_data: 风险数据
            
        Returns:
            资产快照对象
        """
        try:
            # 计算总资产价值
            total_value = self._calculate_total_asset_value(balance_data, positions_data)
            
            # 创建快照
            snapshot = AssetSnapshot(
                customer_uid=customer_uid,
                exchange=exchange,
                total_value=total_value,
                balance_data=balance_data,
                positions_data=positions_data,
                risk_data=risk_data
            )
            
            # 保存到数据库
            await self._save_asset_snapshot(snapshot)
            
            logger.info(f"已创建资产快照: {customer_uid} - {exchange}")
            return snapshot
            
        except Exception as e:
            logger.error(f"创建资产快照失败: {e}")
            return None
    
    async def get_asset_snapshots(self, customer_uid: str, exchange: str = None, 
                                 days: int = 30) -> List[AssetSnapshot]:
        """获取资产快照历史
        
        Args:
            customer_uid: 客户UID
            exchange: 交易所（可选）
            days: 天数范围
            
        Returns:
            资产快照列表
        """
        try:
            db_pool = await self.get_db_pool()
            
            # 构建查询条件
            where_conditions = ["customer_uid = %s"]
            params = [customer_uid]
            
            if exchange:
                where_conditions.append("exchange = %s")
                params.append(exchange)
            
            # 添加时间范围
            start_date = datetime.now() - timedelta(days=days)
            where_conditions.append("timestamp >= %s")
            params.append(start_date)
            
            where_clause = " AND ".join(where_conditions)
            
            query = f"""
                SELECT * FROM asset_snapshots 
                WHERE {where_clause}
                ORDER BY timestamp DESC
                LIMIT %s
            """
            params.append(days)
            
            async with db_pool.acquire() as conn:
                async with conn.cursor() as cursor:
                    await cursor.execute(query, params)
                    rows = await cursor.fetchall()
                    
                    snapshots = []
                    for row in rows:
                        snapshot_data = self._row_to_dict(row, cursor.description)
                        snapshot = AssetSnapshot.from_dict(snapshot_data)
                        snapshots.append(snapshot)
                    
                    return snapshots
                    
        except Exception as e:
            logger.error(f"获取资产快照失败: {e}")
            return []
    
    async def analyze_customer_assets(self, customer_uid: str, exchange: str) -> Optional[AssetAnalysis]:
        """分析客户资产
        
        Args:
            customer_uid: 客户UID
            exchange: 交易所
            
        Returns:
            资产分析结果
        """
        try:
            # 检查缓存
            cache_key = f"{customer_uid}_{exchange}"
            if cache_key in self.analysis_cache:
                cache_data = self.analysis_cache[cache_key]
                if datetime.now().timestamp() - cache_data['timestamp'] < self.cache_expiry:
                    return cache_data['data']
            
            # 获取客户信息
            customer = await self._get_customer_info(customer_uid)
            if not customer:
                logger.error(f"客户不存在: {customer_uid}")
                return None
            
            # 根据交易所获取资产数据
            if exchange.lower() == 'okx':
                analysis_data = await self._analyze_okx_assets(customer)
            else:
                # 其他交易所的分析逻辑
                analysis_data = await self._analyze_generic_assets(customer, exchange)
            
            if not analysis_data:
                return None
            
            # 创建分析结果
            analysis = AssetAnalysis(
                customer_uid=customer_uid,
                exchange=exchange,
                total_assets=analysis_data.get('total_assets', 0),
                total_positions=analysis_data.get('total_positions', 0),
                risk_level=analysis_data.get('risk_level', 'unknown'),
                asset_distribution=analysis_data.get('asset_distribution', {}),
                position_summary=analysis_data.get('position_summary', {}),
                risk_metrics=analysis_data.get('risk_metrics', {}),
                trend_analysis=analysis_data.get('trend_analysis', {}),
                recommendations=analysis_data.get('recommendations', [])
            )
            
            # 缓存结果
            self.analysis_cache[cache_key] = {
                'data': analysis,
                'timestamp': datetime.now().timestamp()
            }
            
            return analysis
            
        except Exception as e:
            logger.error(f"分析客户资产失败: {e}")
            return None
    
    async def get_asset_trend_data(self, customer_uid: str, exchange: str, 
                                  days: int = 30) -> List[Dict[str, Any]]:
        """获取资产趋势数据
        
        Args:
            customer_uid: 客户UID
            exchange: 交易所
            days: 天数范围
            
        Returns:
            趋势数据列表
        """
        try:
            # 获取历史快照
            snapshots = await self.get_asset_snapshots(customer_uid, exchange, days)
            
            if not snapshots:
                # 如果没有历史数据，返回模拟数据
                return self._generate_mock_trend_data(days)
            
            # 转换为趋势数据
            trend_data = []
            for i, snapshot in enumerate(snapshots):
                if i == 0:
                    change = 0
                    change_percent = 0
                else:
                    prev_value = snapshots[i-1].total_value
                    change = snapshot.total_value - prev_value
                    change_percent = (change / prev_value * 100) if prev_value > 0 else 0
                
                trend_data.append({
                    'date': snapshot.timestamp.strftime('%Y-%m-%d'),
                    'timestamp': int(snapshot.timestamp.timestamp() * 1000),
                    'total_value': round(snapshot.total_value, 2),
                    'change': round(change, 2),
                    'change_percent': round(change_percent, 2)
                })
            
            return trend_data
            
        except Exception as e:
            logger.error(f"获取资产趋势数据失败: {e}")
            return []
    
    async def get_exchange_asset_summary(self, exchange: str) -> Optional[ExchangeAssetSummary]:
        """获取交易所资产汇总
        
        Args:
            exchange: 交易所
            
        Returns:
            交易所资产汇总
        """
        try:
            db_pool = await self.get_db_pool()
            
            # 获取该交易所的所有客户资产统计
            query = """
                SELECT 
                    COUNT(DISTINCT customer_uid) as total_customers,
                    SUM(total_value) as total_assets,
                    AVG(total_value) as avg_assets
                FROM asset_snapshots 
                WHERE exchange = %s 
                AND timestamp >= %s
            """
            
            # 获取最近7天的数据
            start_date = datetime.now() - timedelta(days=7)
            
            async with db_pool.acquire() as conn:
                async with conn.cursor() as cursor:
                    await cursor.execute(query, (exchange, start_date))
                    row = await cursor.fetchone()
                    
                    if row:
                        summary = ExchangeAssetSummary(
                            exchange=exchange,
                            total_customers=row[0] or 0,
                            total_assets=row[1] or 0.0,
                            avg_assets_per_customer=row[2] or 0.0
                        )
                        
                        # 获取风险分布
                        summary.risk_distribution = await self._get_risk_distribution(exchange)
                        
                        return summary
            
            return None
            
        except Exception as e:
            logger.error(f"获取交易所资产汇总失败: {e}")
            return None
    
    async def schedule_asset_snapshots(self):
        """定时创建资产快照"""
        try:
            logger.info("开始定时创建资产快照...")
            
            # 获取所有客户
            customers = await self._get_all_customers()
            
            for customer in customers:
                try:
                    # 为每个客户创建资产快照
                    await self._create_customer_snapshot(customer)
                    await asyncio.sleep(1)  # 避免请求过于频繁
                    
                except Exception as e:
                    logger.error(f"为客户 {customer.get('customer_uid')} 创建快照失败: {e}")
                    continue
            
            logger.info("定时创建资产快照完成")
            
        except Exception as e:
            logger.error(f"定时创建资产快照失败: {e}")
    
    # 私有方法
    async def _save_asset_snapshot(self, snapshot: AssetSnapshot):
        """保存资产快照到数据库"""
        try:
            db_pool = await self.get_db_pool()
            
            query = """
                INSERT INTO asset_snapshots 
                (customer_uid, exchange, timestamp, total_value, valuation_ccy, 
                 balance_data, positions_data, risk_data, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """
            
            params = (
                snapshot.customer_uid,
                snapshot.exchange,
                snapshot.timestamp,
                snapshot.total_value,
                snapshot.valuation_ccy,
                json.dumps(snapshot.balance_data),
                json.dumps(snapshot.positions_data),
                json.dumps(snapshot.risk_data),
                snapshot.created_at
            )
            
            async with db_pool.acquire() as conn:
                async with conn.cursor() as cursor:
                    await cursor.execute(query, params)
                    await conn.commit()
                    
        except Exception as e:
            logger.error(f"保存资产快照失败: {e}")
    
    async def _analyze_okx_assets(self, customer: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """分析OKX资产"""
        try:
            # 创建OKX资产分析器
            analyzer = await get_okx_asset_analyzer(
                customer['customer_uid'],
                customer['api_key'],
                customer['api_secret'],
                customer['passphrase'],
                customer.get('is_demo', True)
            )
            
            # 获取综合资产分析
            analysis = await analyzer.get_comprehensive_asset_analysis()
            
            if not analysis:
                return None
            
            # 处理分析结果
            return {
                'total_assets': analysis.get('summary', {}).get('total_assets', 0),
                'total_positions': analysis.get('summary', {}).get('total_positions', 0),
                'risk_level': analysis.get('summary', {}).get('risk_level', 'unknown'),
                'asset_distribution': self._extract_asset_distribution(analysis.get('valuation', {})),
                'position_summary': analysis.get('positions', {}),
                'risk_metrics': analysis.get('risk', {}),
                'trend_analysis': self._analyze_trend_data(analysis.get('trend', [])),
                'recommendations': []
            }
            
        except Exception as e:
            logger.error(f"分析OKX资产失败: {e}")
            return None
    
    async def _analyze_generic_assets(self, customer: Dict[str, Any], exchange: str) -> Optional[Dict[str, Any]]:
        """分析通用资产（其他交易所）"""
        try:
            # 这里可以实现其他交易所的分析逻辑
            # 目前返回基础信息
            return {
                'total_assets': customer.get('current_asset', 0),
                'total_positions': 0,
                'risk_level': 'unknown',
                'asset_distribution': {},
                'position_summary': {},
                'risk_metrics': {},
                'trend_analysis': {},
                'recommendations': []
            }
            
        except Exception as e:
            logger.error(f"分析通用资产失败: {e}")
            return None
    
    def _calculate_total_asset_value(self, balance_data: Dict[str, Any], 
                                   positions_data: Dict[str, Any]) -> float:
        """计算总资产价值"""
        try:
            total_value = 0.0
            
            # 计算余额价值
            if balance_data and 'data' in balance_data:
                for balance in balance_data['data']:
                    bal = float(balance.get('bal', 0))
                    if bal > 0:
                        # 这里需要获取实时汇率，简化处理
                        total_value += bal
            
            # 计算持仓价值
            if positions_data and 'data' in positions_data:
                for position in positions_data['data']:
                    pos_value = float(position.get('notionalUsd', 0))
                    total_value += pos_value
            
            return round(total_value, 2)
            
        except Exception as e:
            logger.error(f"计算总资产价值失败: {e}")
            return 0.0
    
    def _extract_asset_distribution(self, valuation_data: Dict[str, Any]) -> Dict[str, float]:
        """提取资产分布"""
        try:
            distribution = {}
            
            if valuation_data and 'assets' in valuation_data:
                total_value = valuation_data.get('total_valuation', 0)
                if total_value > 0:
                    for asset in valuation_data['assets']:
                        asset_value = asset.get('usd_value', 0)
                        if asset_value > 0:
                            ratio = asset_value / total_value
                            distribution[asset.get('ccy', 'unknown')] = round(ratio * 100, 2)
            
            return distribution
            
        except Exception as e:
            logger.error(f"提取资产分布失败: {e}")
            return {}
    
    def _analyze_trend_data(self, trend_data: List[Dict[str, Any]]) -> Dict[str, Any]:
        """分析趋势数据"""
        try:
            if not trend_data or len(trend_data) < 2:
                return {'trend': 'stable', 'volatility': 0, 'growth_rate': 0}
            
            values = [item.get('total_value', 0) for item in trend_data]
            
            # 计算趋势
            first_value = values[0]
            last_value = values[-1]
            
            if last_value > first_value * 1.05:  # 增长超过5%
                trend = 'rising'
            elif last_value < first_value * 0.95:  # 下降超过5%
                trend = 'declining'
            else:
                trend = 'stable'
            
            # 计算波动率
            volatility = AssetAnalysisUtils.calculate_volatility(values)
            
            # 计算增长率
            growth_rate = AssetAnalysisUtils.calculate_asset_growth_rate(
                first_value, last_value, len(trend_data)
            )
            
            return {
                'trend': trend,
                'volatility': volatility,
                'growth_rate': growth_rate,
                'max_drawdown': AssetAnalysisUtils.calculate_max_drawdown(values)
            }
            
        except Exception as e:
            logger.error(f"分析趋势数据失败: {e}")
            return {'trend': 'unknown', 'volatility': 0, 'growth_rate': 0}
    
    def _generate_mock_trend_data(self, days: int) -> List[Dict[str, Any]]:
        """生成模拟趋势数据"""
        try:
            import random
            
            trend_data = []
            base_value = 10000
            
            for i in range(days):
                date = datetime.now() - timedelta(days=days-i-1)
                variation = random.uniform(-0.03, 0.03)  # ±3%波动
                current_value = base_value * (1 + variation)
                
                trend_data.append({
                    'date': date.strftime('%Y-%m-%d'),
                    'timestamp': int(date.timestamp() * 1000),
                    'total_value': round(current_value, 2),
                    'change': round(variation * 100, 2),
                    'change_percent': round(variation * 100, 2)
                })
                
                base_value = current_value
            
            return trend_data
            
        except Exception as e:
            logger.error(f"生成模拟趋势数据失败: {e}")
            return []
    
    async def _get_customer_info(self, customer_uid: str) -> Optional[Dict[str, Any]]:
        """获取客户信息"""
        try:
            db_pool = await self.get_db_pool()
            
            query = "SELECT * FROM customers WHERE customer_uid = %s"
            
            async with db_pool.acquire() as conn:
                async with conn.cursor() as cursor:
                    await cursor.execute(query, (customer_uid,))
                    row = await cursor.fetchone()
                    
                    if row:
                        return self._row_to_dict(row, cursor.description)
            
            return None
            
        except Exception as e:
            logger.error(f"获取客户信息失败: {e}")
            return None
    
    async def _get_all_customers(self) -> List[Dict[str, Any]]:
        """获取所有客户"""
        try:
            db_pool = await self.get_db_pool()
            
            query = "SELECT * FROM customers WHERE enabled = true"
            
            async with db_pool.acquire() as conn:
                async with conn.cursor() as cursor:
                    await cursor.execute(query)
                    rows = await cursor.fetchall()
                    
                    customers = []
                    for row in rows:
                        customer_data = self._row_to_dict(row, cursor.description)
                        customers.append(customer_data)
                    
                    return customers
                    
        except Exception as e:
            logger.error(f"获取所有客户失败: {e}")
            return []
    
    async def _create_customer_snapshot(self, customer: Dict[str, Any]):
        """为客户创建资产快照"""
        try:
            exchange = customer.get('exchange')
            if not exchange:
                return
            
            # 根据交易所类型获取资产数据
            if exchange.lower() == 'okx':
                await self._create_okx_snapshot(customer)
            else:
                # 其他交易所的处理逻辑
                await self._create_generic_snapshot(customer)
                
        except Exception as e:
            logger.error(f"为客户创建快照失败: {e}")
    
    async def _create_okx_snapshot(self, customer: Dict[str, Any]):
        """创建OKX快照"""
        try:
            analyzer = await get_okx_asset_analyzer(
                customer['customer_uid'],
                customer['api_key'],
                customer['api_secret'],
                customer['passphrase'],
                customer.get('is_demo', True)
            )
            
            # 获取账户数据
            balance_data = await analyzer.get_account_balance()
            positions_data = await analyzer.get_account_positions()
            risk_data = await analyzer.get_account_risk()
            
            # 创建快照
            await self.create_asset_snapshot(
                customer['customer_uid'],
                customer['exchange'],
                balance_data,
                positions_data,
                risk_data
            )
            
        except Exception as e:
            logger.error(f"创建OKX快照失败: {e}")
    
    async def _create_generic_snapshot(self, customer: Dict[str, Any]):
        """创建通用快照"""
        try:
            # 创建基础快照数据
            balance_data = {
                'data': [{
                    'ccy': 'USD',
                    'bal': str(customer.get('current_asset', 0)),
                    'frozen': '0',
                    'availBal': str(customer.get('trading_asset', 0))
                }]
            }
            
            await self.create_asset_snapshot(
                customer['customer_uid'],
                customer['exchange'],
                balance_data,
                {},
                {}
            )
            
        except Exception as e:
            logger.error(f"创建通用快照失败: {e}")
    
    async def _get_risk_distribution(self, exchange: str) -> Dict[str, int]:
        """获取风险分布"""
        try:
            db_pool = await self.get_db_pool()
            
            query = """
                SELECT risk_level, COUNT(*) as count
                FROM asset_analysis 
                WHERE exchange = %s 
                AND analysis_time >= %s
                GROUP BY risk_level
            """
            
            start_date = datetime.now() - timedelta(days=7)
            
            async with db_pool.acquire() as conn:
                async with conn.cursor() as cursor:
                    await cursor.execute(query, (exchange, start_date))
                    rows = await cursor.fetchall()
                    
                    risk_distribution = {}
                    for row in rows:
                        risk_distribution[row[0]] = row[1]
                    
                    return risk_distribution
                    
        except Exception as e:
            logger.error(f"获取风险分布失败: {e}")
            return {}
    
    def _row_to_dict(self, row, description) -> Dict[str, Any]:
        """将数据库行转换为字典"""
        return {desc[0]: value for desc, value in zip(description, row)}


# 全局资产分析服务实例
_global_asset_analysis_service = None

async def get_asset_analysis_service() -> AssetAnalysisService:
    """获取全局资产分析服务"""
    global _global_asset_analysis_service
    if not _global_asset_analysis_service:
        _global_asset_analysis_service = AssetAnalysisService()
    return _global_asset_analysis_service 