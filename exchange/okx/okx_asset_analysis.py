"""
OKX资产分析模块
用于获取和分析账户资产波动数据
"""

import asyncio
import json
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
import aiohttp
from utils.logger import logger


class OKXAssetAnalysis:
    """OKX资产分析器"""
    
    def __init__(self, api_key: str, api_secret: str, passphrase: str, is_demo: bool = True):
        self.api_key = api_key
        self.api_secret = api_secret
        self.passphrase = passphrase
        self.is_demo = is_demo
        
        # 根据是否为演示账户选择不同的URL
        if is_demo:
            self.base_url = "https://www.okx.com"
            self.api_url = "https://www.okx.com/api/v5"
        else:
            self.base_url = "https://www.okx.com"
            self.api_url = "https://www.okx.com/api/v5"
        
        # 资产历史数据缓存
        self.asset_history_cache = {}
        self.cache_expiry = 300  # 5分钟缓存过期
        
    def _get_timestamp(self) -> str:
        """获取ISO格式的时间戳"""
        return datetime.utcnow().isoformat()[:-3] + 'Z'
    
    def _sign(self, timestamp: str, method: str, request_path: str, body: str = '') -> str:
        """生成API签名"""
        import hmac
        import hashlib
        
        message = timestamp + method + request_path + body
        mac = hmac.new(
            bytes(self.api_secret, encoding='utf8'),
            bytes(message, encoding='utf-8'),
            digestmod='sha256'
        )
        return mac.hexdigest()
    
    def _get_headers(self, method: str, request_path: str, body: str = '') -> Dict[str, str]:
        """获取请求头"""
        timestamp = self._get_timestamp()
        signature = self._sign(timestamp, method, request_path, body)
        
        return {
            'OK-ACCESS-KEY': self.api_key,
            'OK-ACCESS-SIGN': signature,
            'OK-ACCESS-TIMESTAMP': timestamp,
            'OK-ACCESS-PASSPHRASE': self.passphrase,
            'Content-Type': 'application/json'
        }
    
    async def get_account_balance(self, ccy: str = None) -> Dict[str, Any]:
        """获取账户余额
        
        Args:
            ccy: 币种，如BTC、ETH等，不传则获取所有币种
            
        Returns:
            账户余额数据
        """
        try:
            url = f"{self.api_url}/account/balance"
            params = {}
            if ccy:
                params['ccy'] = ccy
            
            async with aiohttp.ClientSession() as session:
                headers = self._get_headers('GET', f'/api/v5/account/balance?{self._build_query_string(params)}')
                async with session.get(url, params=params, headers=headers) as response:
                    if response.status == 200:
                        data = await response.json()
                        return data
                    else:
                        logger.error(f"获取账户余额失败: {response.status}")
                        return None
                        
        except Exception as e:
            logger.error(f"获取账户余额异常: {e}")
            return None
    
    async def get_account_positions(self, inst_type: str = 'SWAP') -> Dict[str, Any]:
        """获取账户持仓信息
        
        Args:
            inst_type: 产品类型，SWAP-永续合约，MARGIN-杠杆，SPOT-现货
            
        Returns:
            持仓信息数据
        """
        try:
            url = f"{self.api_url}/account/positions"
            params = {'instType': inst_type}
            
            async with aiohttp.ClientSession() as session:
                headers = self._get_headers('GET', f'/api/v5/account/positions?{self._build_query_string(params)}')
                async with session.get(url, params=params, headers=headers) as response:
                    if response.status == 200:
                        data = await response.json()
                        return data
                    else:
                        logger.error(f"获取持仓信息失败: {response.status}")
                        return None
                        
        except Exception as e:
            logger.error(f"获取持仓信息异常: {e}")
            return None
    
    async def get_account_risk(self) -> Dict[str, Any]:
        """获取账户风险信息
        
        Returns:
            账户风险数据
        """
        try:
            url = f"{self.api_url}/account/account-position-risk"
            
            async with aiohttp.ClientSession() as session:
                headers = self._get_headers('GET', '/api/v5/account/account-position-risk')
                async with session.get(url, headers=headers) as response:
                    if response.status == 200:
                        data = await response.json()
                        return data
                    else:
                        logger.error(f"获取账户风险信息失败: {response.status}")
                        return None
                        
        except Exception as e:
            logger.error(f"获取账户风险信息异常: {e}")
            return None
    
    async def get_asset_valuation(self, ccy: str = 'USD') -> Dict[str, Any]:
        """获取资产估值
        
        Args:
            ccy: 计价币种，默认USD
            
        Returns:
            资产估值数据
        """
        try:
            url = f"{self.api_url}/account/balance"
            
            async with aiohttp.ClientSession() as session:
                headers = self._get_headers('GET', '/api/v5/account/balance')
                async with session.get(url, headers=headers) as response:
                    if response.status == 200:
                        data = await response.json()
                        
                        # 计算总资产估值
                        total_valuation = 0
                        asset_details = []
                        
                        if data.get('data'):
                            for balance in data['data']:
                                if float(balance.get('bal', 0)) > 0:
                                    # 这里需要获取实时汇率来计算USD估值
                                    # 简化处理，假设所有币种都按1:1计算
                                    usd_value = float(balance.get('bal', 0))
                                    total_valuation += usd_value
                                    
                                    asset_details.append({
                                        'ccy': balance.get('ccy'),
                                        'balance': balance.get('bal'),
                                        'frozen': balance.get('frozen'),
                                        'available': balance.get('availBal'),
                                        'usd_value': usd_value
                                    })
                        
                        return {
                            'total_valuation': total_valuation,
                            'valuation_ccy': ccy,
                            'assets': asset_details,
                            'timestamp': datetime.now().isoformat()
                        }
                    else:
                        logger.error(f"获取资产估值失败: {response.status}")
                        return None
                        
        except Exception as e:
            logger.error(f"获取资产估值异常: {e}")
            return None
    
    async def get_asset_trend_data(self, days: int = 30, ccy: str = 'USD') -> List[Dict[str, Any]]:
        """获取资产趋势数据（模拟数据，实际需要定期记录）
        
        Args:
            days: 天数范围
            ccy: 计价币种
            
        Returns:
            资产趋势数据列表
        """
        try:
            # 这里返回模拟数据，实际应用中需要定期记录资产数据
            trend_data = []
            base_value = 10000  # 基础资产值
            
            for i in range(days):
                date = datetime.now() - timedelta(days=days-i-1)
                
                # 模拟资产波动（实际应该从数据库获取历史记录）
                import random
                variation = random.uniform(-0.05, 0.05)  # ±5%波动
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
            logger.error(f"获取资产趋势数据异常: {e}")
            return []
    
    def _build_query_string(self, params: Dict[str, Any]) -> str:
        """构建查询字符串"""
        if not params:
            return ''
        return '&'.join([f"{k}={v}" for k, v in params.items()])
    
    async def get_comprehensive_asset_analysis(self) -> Dict[str, Any]:
        """获取综合资产分析
        
        Returns:
            包含余额、持仓、风险、趋势的完整分析
        """
        try:
            # 并行获取各种数据
            tasks = [
                self.get_account_balance(),
                self.get_account_positions(),
                self.get_account_risk(),
                self.get_asset_valuation(),
                self.get_asset_trend_data()
            ]
            
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # 处理结果
            balance_data = results[0] if not isinstance(results[0], Exception) else None
            positions_data = results[1] if not isinstance(results[1], Exception) else None
            risk_data = results[2] if not isinstance(results[2], Exception) else None
            valuation_data = results[3] if not isinstance(results[3], Exception) else None
            trend_data = results[4] if not isinstance(results[4], Exception) else []
            
            return {
                'balance': balance_data,
                'positions': positions_data,
                'risk': risk_data,
                'valuation': valuation_data,
                'trend': trend_data,
                'analysis_time': datetime.now().isoformat(),
                'summary': {
                    'total_assets': valuation_data.get('total_valuation', 0) if valuation_data else 0,
                    'total_positions': len(positions_data.get('data', [])) if positions_data else 0,
                    'risk_level': self._calculate_risk_level(risk_data) if risk_data else 'unknown'
                }
            }
            
        except Exception as e:
            logger.error(f"获取综合资产分析异常: {e}")
            return None
    
    def _calculate_risk_level(self, risk_data: Dict[str, Any]) -> str:
        """计算风险等级"""
        try:
            if not risk_data or 'data' not in risk_data:
                return 'unknown'
            
            # 根据风险数据计算风险等级
            # 这里需要根据OKX的具体风险指标来实现
            return 'low'  # 简化处理
            
        except Exception as e:
            logger.error(f"计算风险等级异常: {e}")
            return 'unknown'


# 全局资产分析器管理器
_global_asset_analyzers = {}

async def get_okx_asset_analyzer(client_key: str, api_key: str, api_secret: str, 
                                passphrase: str, is_demo: bool = True) -> OKXAssetAnalysis:
    """获取全局OKX资产分析器"""
    if client_key not in _global_asset_analyzers:
        analyzer = OKXAssetAnalysis(api_key, api_secret, passphrase, is_demo)
        _global_asset_analyzers[client_key] = analyzer
    
    return _global_asset_analyzers[client_key]

def get_global_asset_analyzer_manager():
    """获取全局资产分析器管理器"""
    return _global_asset_analyzers 