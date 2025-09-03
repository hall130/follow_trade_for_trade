"""
资产分析数据模型
用于存储和分析资产波动数据
"""

from datetime import datetime
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict
import json


@dataclass
class AssetSnapshot:
    """资产快照"""
    id: Optional[int] = None
    customer_uid: str = ""
    exchange: str = ""
    timestamp: datetime = None
    total_value: float = 0.0
    valuation_ccy: str = "USD"
    balance_data: Dict[str, Any] = None
    positions_data: Dict[str, Any] = None
    risk_data: Dict[str, Any] = None
    created_at: datetime = None
    
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now()
        if self.created_at is None:
            self.created_at = datetime.now()
        if self.balance_data is None:
            self.balance_data = {}
        if self.positions_data is None:
            self.positions_data = {}
        if self.risk_data is None:
            self.risk_data = {}
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        data = asdict(self)
        data['timestamp'] = self.timestamp.isoformat() if self.timestamp else None
        data['created_at'] = self.created_at.isoformat() if self.created_at else None
        return data
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'AssetSnapshot':
        """从字典创建实例"""
        if 'timestamp' in data and data['timestamp']:
            if isinstance(data['timestamp'], str):
                data['timestamp'] = datetime.fromisoformat(data['timestamp'].replace('Z', '+00:00'))
            elif isinstance(data['timestamp'], (int, float)):
                data['timestamp'] = datetime.fromtimestamp(data['timestamp'] / 1000)
        
        if 'created_at' in data and data['created_at']:
            if isinstance(data['created_at'], str):
                data['created_at'] = datetime.fromisoformat(data['created_at'].replace('Z', '+00:00'))
            elif isinstance(data['created_at'], (int, float)):
                data['created_at'] = datetime.fromtimestamp(data['created_at'] / 1000)
        
        return cls(**data)


@dataclass
class AssetTrend:
    """资产趋势数据"""
    id: Optional[int] = None
    customer_uid: str = ""
    exchange: str = ""
    date: str = ""
    timestamp: int = 0
    total_value: float = 0.0
    change: float = 0.0
    change_percent: float = 0.0
    volume_24h: float = 0.0
    high_24h: float = 0.0
    low_24h: float = 0.0
    created_at: datetime = None
    
    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.now()
        if not self.date and self.timestamp:
            self.date = datetime.fromtimestamp(self.timestamp / 1000).strftime('%Y-%m-%d')
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        data = asdict(self)
        data['created_at'] = self.created_at.isoformat() if self.created_at else None
        return data
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'AssetTrend':
        """从字典创建实例"""
        if 'created_at' in data and data['created_at']:
            if isinstance(data['created_at'], str):
                data['created_at'] = datetime.fromisoformat(data['created_at'].replace('Z', '+00:00'))
            elif isinstance(data['created_at'], (int, float)):
                data['created_at'] = datetime.fromtimestamp(data['created_at'] / 1000)
        
        return cls(**data)


@dataclass
class AssetAnalysis:
    """资产分析结果"""
    customer_uid: str = ""
    exchange: str = ""
    analysis_time: datetime = None
    total_assets: float = 0.0
    total_positions: int = 0
    risk_level: str = "unknown"
    asset_distribution: Dict[str, float] = None
    position_summary: Dict[str, Any] = None
    risk_metrics: Dict[str, Any] = None
    trend_analysis: Dict[str, Any] = None
    recommendations: List[str] = None
    
    def __post_init__(self):
        if self.analysis_time is None:
            self.analysis_time = datetime.now()
        if self.asset_distribution is None:
            self.asset_distribution = {}
        if self.position_summary is None:
            self.position_summary = {}
        if self.risk_metrics is None:
            self.risk_metrics = {}
        if self.trend_analysis is None:
            self.trend_analysis = {}
        if self.recommendations is None:
            self.recommendations = []
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        data = asdict(self)
        data['analysis_time'] = self.analysis_time.isoformat() if self.analysis_time else None
        return data
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'AssetAnalysis':
        """从字典创建实例"""
        if 'analysis_time' in data and data['analysis_time']:
            if isinstance(data['analysis_time'], str):
                data['analysis_time'] = datetime.fromisoformat(data['analysis_time'].replace('Z', '+00:00'))
            elif isinstance(data['analysis_time'], (int, float)):
                data['analysis_time'] = datetime.fromtimestamp(data['analysis_time'] / 1000)
        
        return cls(**data)


@dataclass
class ExchangeAssetSummary:
    """交易所资产汇总"""
    exchange: str = ""
    total_customers: int = 0
    total_assets: float = 0.0
    avg_assets_per_customer: float = 0.0
    top_assets: List[str] = None
    risk_distribution: Dict[str, int] = None
    last_updated: datetime = None
    
    def __post_init__(self):
        if self.last_updated is None:
            self.last_updated = datetime.now()
        if self.top_assets is None:
            self.top_assets = []
        if self.risk_distribution is None:
            self.risk_distribution = {}
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        data = asdict(self)
        data['last_updated'] = self.last_updated.isoformat() if self.last_updated else None
        return data
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ExchangeAssetSummary':
        """从字典创建实例"""
        if 'last_updated' in data and data['last_updated']:
            if isinstance(data['last_updated'], str):
                data['last_updated'] = datetime.fromisoformat(data['last_updated'].replace('Z', '+00:00'))
            elif isinstance(data['last_updated'], (int, float)):
                data['last_updated'] = datetime.fromtimestamp(data['last_updated'] / 1000)
        
        return cls(**data)


# 资产分析工具函数
class AssetAnalysisUtils:
    """资产分析工具类"""
    
    @staticmethod
    def calculate_asset_growth_rate(initial_value: float, current_value: float, days: int) -> float:
        """计算资产增长率"""
        if initial_value <= 0 or days <= 0:
            return 0.0
        
        growth_rate = (current_value - initial_value) / initial_value
        annualized_rate = ((1 + growth_rate) ** (365 / days)) - 1
        return round(annualized_rate * 100, 2)
    
    @staticmethod
    def calculate_volatility(values: List[float]) -> float:
        """计算波动率"""
        if len(values) < 2:
            return 0.0
        
        import statistics
        mean = statistics.mean(values)
        variance = statistics.variance(values, mean)
        volatility = variance ** 0.5
        return round(volatility, 4)
    
    @staticmethod
    def calculate_sharpe_ratio(returns: List[float], risk_free_rate: float = 0.02) -> float:
        """计算夏普比率"""
        if len(returns) < 2:
            return 0.0
        
        import statistics
        avg_return = statistics.mean(returns)
        std_return = statistics.stdev(returns)
        
        if std_return == 0:
            return 0.0
        
        sharpe_ratio = (avg_return - risk_free_rate) / std_return
        return round(sharpe_ratio, 4)
    
    @staticmethod
    def calculate_max_drawdown(values: List[float]) -> float:
        """计算最大回撤"""
        if len(values) < 2:
            return 0.0
        
        max_drawdown = 0.0
        peak = values[0]
        
        for value in values:
            if value > peak:
                peak = value
            drawdown = (peak - value) / peak
            max_drawdown = max(max_drawdown, drawdown)
        
        return round(max_drawdown * 100, 2)
    
    @staticmethod
    def generate_asset_recommendations(analysis: AssetAnalysis) -> List[str]:
        """生成资产建议"""
        recommendations = []
        
        # 基于风险等级的建议
        if analysis.risk_level == "high":
            recommendations.append("建议降低杠杆，控制风险敞口")
            recommendations.append("考虑设置更严格的止损")
        
        # 基于资产分布的建议
        if analysis.asset_distribution:
            # 检查是否过度集中在某个资产
            max_asset_ratio = max(analysis.asset_distribution.values())
            if max_asset_ratio > 0.5:  # 超过50%
                recommendations.append("建议分散投资，避免过度集中")
        
        # 基于趋势的建议
        if analysis.trend_analysis:
            trend = analysis.trend_analysis.get('trend', '')
            if trend == 'declining':
                recommendations.append("资产呈下降趋势，建议谨慎操作")
            elif trend == 'rising':
                recommendations.append("资产呈上升趋势，可考虑适度加仓")
        
        # 默认建议
        if not recommendations:
            recommendations.append("资产状况良好，建议保持当前策略")
        
        return recommendations 