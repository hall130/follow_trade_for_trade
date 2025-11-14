#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
热门带单员排序类型枚举
"""

from enum import Enum


class OKXSortType(Enum):
    """OKX 排序类型枚举（type 参数，严格区分大小写，使用驼峰命名）"""
    COMPREHENSIVE = ''  # 综合排序（type 为空字符串）
    YIELD_RATIO = 'yieldRatio'  # 收益率
    PNL = 'pnl'  # 收益额/总盈亏
    FOLLOWER_LIMIT = 'traderFollowerLimit'  # 跟单人数
    WIN_RATIO = 'winRatio'  # 胜率
    
    @classmethod
    def from_string(cls, value: str) -> 'OKXSortType':
        """从字符串转换为枚举"""
        if not value:
            return cls.COMPREHENSIVE
        for sort_type in cls:
            if sort_type.value == value:
                return sort_type
        return cls.COMPREHENSIVE  # 默认返回综合排序
    
    def __str__(self):
        return self.value


class BinanceSortType(Enum):
    """Binance 排序类型枚举（data_type 参数，严格区分大小写，使用大写）"""
    COMPREHENSIVE = ''  # 综合排序（使用 AUM，因为 Binance 没有综合排序选项）
    PNL = 'PNL'  # 总盈亏
    ROI = 'ROI'  # 收益率
    COPY_COUNT = 'COPY_COUNT'  # 跟单人数
    SHARP_RATIO = 'SHARP_RATIO'  # 夏普比率（可当作胜率使用，但要注明）
    
    @classmethod
    def from_string(cls, value: str) -> 'BinanceSortType':
        """从字符串转换为枚举"""
        if not value:
            return cls.COMPREHENSIVE
        value_upper = value.upper()
        for sort_type in cls:
            if sort_type.value.upper() == value_upper:
                return sort_type
        return cls.COMPREHENSIVE  # 默认返回综合排序（使用 AUM）
    
    def __str__(self):
        return self.value

