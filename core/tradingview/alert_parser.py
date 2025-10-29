#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
TradingView消息解析器
解析TradingView Alert消息并转换为交易指令
"""

import re
import json
from datetime import datetime
from typing import Dict, Any, Optional, List, Tuple
from dataclasses import dataclass
from enum import Enum

from utils.logger import get_logger

logger = get_logger(__name__)

class TradeAction(Enum):
    """交易动作"""
    BUY = "buy"
    SELL = "sell"
    CLOSE_LONG = "close_long"
    CLOSE_SHORT = "close_short"
    STOP_LOSS = "stop_loss"
    TAKE_PROFIT = "take_profit"

@dataclass
class TradeInstruction:
    """交易指令"""
    symbol: str
    action: TradeAction
    price: float
    quantity: float
    order_type: str = "market"
    stop_price: Optional[float] = None
    reason: str = ""
    confidence: float = 1.0
    metadata: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}

class TradingViewAlertParser:
    """TradingView Alert解析器"""
    
    def __init__(self):
        # 交易对模式
        self.symbol_patterns = {
            'BTC': r'(?i)(btc|bitcoin)',
            'ETH': r'(?i)(eth|ethereum)',
            'USDT': r'(?i)(usdt|tether)',
            'BNB': r'(?i)(bnb|binance)',
            'ADA': r'(?i)(ada|cardano)',
            'SOL': r'(?i)(sol|solana)',
            'MATIC': r'(?i)(matic|polygon)',
            'DOT': r'(?i)(dot|polkadot)',
            'AVAX': r'(?i)(avax|avalanche)',
            'LINK': r'(?i)(link|chainlink)',
            'XRP': r'(?i)(xrp|ripple)',
            'DOGE': r'(?i)(doge|dogecoin)',
            'LTC': r'(?i)(ltc|litecoin)',
            'ATOM': r'(?i)(atom|cosmos)',
            'NEAR': r'(?i)(near)',
            'FTM': r'(?i)(ftm|fantom)',
            'ALGO': r'(?i)(algo|algorand)',
            'VET': r'(?i)(vet|vechain)',
            'THETA': r'(?i)(theta)',
            'FIL': r'(?i)(fil|filecoin)'
        }
        
        # 交易动作模式
        self.action_patterns = {
            TradeAction.BUY: r'(?i)(buy|long|开多|做多|买入|开仓|建仓)',
            TradeAction.SELL: r'(?i)(sell|short|开空|做空|卖出)',
            TradeAction.CLOSE_LONG: r'(?i)(close\s*long|平多|关闭多头|平仓多头)',
            TradeAction.CLOSE_SHORT: r'(?i)(close\s*short|平空|关闭空头|平仓空头)',
            TradeAction.STOP_LOSS: r'(?i)(stop\s*loss|止损|sl|止损单)',
            TradeAction.TAKE_PROFIT: r'(?i)(take\s*profit|止盈|tp|止盈单)'
        }
        
        # 价格模式
        self.price_patterns = [
            r'(\d+\.?\d*)\s*\$',  # 123.45$
            r'\$\s*(\d+\.?\d*)',  # $123.45
            r'price[:\s]*(\d+\.?\d*)',  # price: 123.45
            r'@\s*(\d+\.?\d*)',  # @123.45
            r'(\d+\.?\d*)\s*usdt',  # 123.45 usdt
            r'价格[:\s]*(\d+\.?\d*)',  # 价格: 123.45
            r'(\d+\.?\d*)\s*元',  # 123.45元
        ]
        
        # 数量模式
        self.quantity_patterns = [
            r'(\d+\.?\d*)\s*btc',  # 0.1 btc
            r'(\d+\.?\d*)\s*eth',  # 1.5 eth
            r'(\d+\.?\d*)\s*usdt',  # 1000 usdt
            r'size[:\s]*(\d+\.?\d*)',  # size: 0.1
            r'amount[:\s]*(\d+\.?\d*)',  # amount: 1000
            r'数量[:\s]*(\d+\.?\d*)',  # 数量: 0.1
            r'(\d+\.?\d*)\s*个',  # 0.1个
            r'(\d+\.?\d*)\s*枚',  # 0.1枚
        ]
        
        logger.info("TradingView Alert解析器初始化完成")
    
    def parse_alert(self, alert_data: Dict[str, Any]) -> Optional[TradeInstruction]:
        """解析TradingView Alert"""
        try:
            logger.info(f"解析TradingView Alert: {alert_data}")
            
            # 提取基本信息
            symbol = self._extract_symbol(alert_data)
            action = self._extract_action(alert_data)
            price = self._extract_price(alert_data)
            quantity = self._extract_quantity(alert_data)
            
            # 验证必要字段
            if not symbol:
                logger.warning("未找到交易对")
                return None
            
            if not action:
                logger.warning("未找到交易动作")
                return None
            
            if not price or price <= 0:
                logger.warning(f"价格无效: {price}")
                return None
            
            # 默认数量
            if not quantity or quantity <= 0:
                quantity = self._get_default_quantity(symbol, price)
            
            # 创建交易指令
            instruction = TradeInstruction(
                symbol=symbol,
                action=action,
                price=price,
                quantity=quantity,
                reason=alert_data.get('message', ''),
                confidence=self._calculate_confidence(alert_data),
                metadata={
                    'alert_name': alert_data.get('alert_name', ''),
                    'strategy': alert_data.get('strategy', 'TradingView'),
                    'timeframe': alert_data.get('timeframe', ''),
                    'exchange': alert_data.get('exchange', ''),
                    'original_data': alert_data
                }
            )
            
            logger.info(f"✅ Alert解析成功: {instruction}")
            return instruction
            
        except Exception as e:
            logger.error(f"解析Alert失败: {e}")
            return None
    
    def parse_text_message(self, text: str) -> Optional[TradeInstruction]:
        """解析文本消息"""
        try:
            logger.info(f"解析文本消息: {text}")
            
            # 提取交易对
            symbol = self._extract_symbol_from_text(text)
            if not symbol:
                logger.warning("文本中未找到交易对")
                return None
            
            # 提取动作
            action = self._extract_action_from_text(text)
            if not action:
                logger.warning("文本中未找到交易动作")
                return None
            
            # 提取价格
            price = self._extract_price_from_text(text)
            if not price:
                logger.warning("文本中未找到价格")
                return None
            
            # 提取数量
            quantity = self._extract_quantity_from_text(text)
            if not quantity:
                quantity = self._get_default_quantity(symbol, price)
            
            # 创建交易指令
            instruction = TradeInstruction(
                symbol=symbol,
                action=action,
                price=price,
                quantity=quantity,
                reason=f"从文本解析: {text[:50]}...",
                confidence=0.7,  # 文本解析默认置信度较低
                metadata={'original_text': text}
            )
            
            logger.info(f"✅ 文本消息解析成功: {instruction}")
            return instruction
            
        except Exception as e:
            logger.error(f"解析文本消息失败: {e}")
            return None
    
    def _extract_symbol(self, alert_data: Dict[str, Any]) -> Optional[str]:
        """从Alert数据中提取交易对"""
        # 尝试多个字段
        symbol_fields = ['symbol', 'ticker', 'instrument', 'pair']
        
        for field in symbol_fields:
            if field in alert_data and alert_data[field]:
                symbol = str(alert_data[field]).upper()
                return self._normalize_symbol(symbol)
        
        # 从消息中提取
        message = alert_data.get('message', '')
        return self._extract_symbol_from_text(message)
    
    def _extract_symbol_from_text(self, text: str) -> Optional[str]:
        """从文本中提取交易对"""
        text_upper = text.upper()
        
        # 查找已知交易对模式
        for symbol, pattern in self.symbol_patterns.items():
            if re.search(pattern, text_upper):
                # 查找配对货币
                if 'USDT' in text_upper:
                    return f"{symbol}USDT"
                elif 'BTC' in text_upper:
                    return f"{symbol}BTC"
                elif 'ETH' in text_upper:
                    return f"{symbol}ETH"
                else:
                    return f"{symbol}USDT"  # 默认USDT
        
        # 查找标准格式 (如 BTCUSDT, ETH-USDT)
        pattern = r'([A-Z]{2,10})[-_]?([A-Z]{2,10})'
        match = re.search(pattern, text_upper)
        if match:
            base = match.group(1)
            quote = match.group(2)
            return f"{base}{quote}"
        
        return None
    
    def _normalize_symbol(self, symbol: str) -> str:
        """标准化交易对格式"""
        # 移除分隔符
        symbol = symbol.replace('-', '').replace('_', '').replace('/', '')
        
        # 确保格式正确
        if len(symbol) >= 6:  # 最少6个字符
            return symbol
        
        return symbol
    
    def _extract_action(self, alert_data: Dict[str, Any]) -> Optional[TradeAction]:
        """从Alert数据中提取动作"""
        # 检查action字段
        if 'action' in alert_data:
            action_str = str(alert_data['action']).upper()
            try:
                return TradeAction(action_str.lower())
            except ValueError:
                pass
        
        # 从消息中提取
        message = alert_data.get('message', '')
        return self._extract_action_from_text(message)
    
    def _extract_action_from_text(self, text: str) -> Optional[TradeAction]:
        """从文本中提取动作"""
        text_lower = text.lower()
        
        for action, pattern in self.action_patterns.items():
            if re.search(pattern, text_lower):
                return action
        
        return None
    
    def _extract_price(self, alert_data: Dict[str, Any]) -> Optional[float]:
        """从Alert数据中提取价格"""
        # 尝试多个字段
        price_fields = ['price', 'close', 'value', 'entry']
        
        for field in price_fields:
            if field in alert_data and alert_data[field]:
                try:
                    return float(alert_data[field])
                except (ValueError, TypeError):
                    continue
        
        # 从消息中提取
        message = alert_data.get('message', '')
        return self._extract_price_from_text(message)
    
    def _extract_price_from_text(self, text: str) -> Optional[float]:
        """从文本中提取价格"""
        for pattern in self.price_patterns:
            match = re.search(pattern, text.lower())
            if match:
                try:
                    return float(match.group(1))
                except ValueError:
                    continue
        
        return None
    
    def _extract_quantity(self, alert_data: Dict[str, Any]) -> Optional[float]:
        """从Alert数据中提取数量"""
        # 尝试多个字段
        quantity_fields = ['quantity', 'size', 'amount', 'volume']
        
        for field in quantity_fields:
            if field in alert_data and alert_data[field]:
                try:
                    return float(alert_data[field])
                except (ValueError, TypeError):
                    continue
        
        # 从消息中提取
        message = alert_data.get('message', '')
        return self._extract_quantity_from_text(message)
    
    def _extract_quantity_from_text(self, text: str) -> Optional[float]:
        """从文本中提取数量"""
        for pattern in self.quantity_patterns:
            match = re.search(pattern, text.lower())
            if match:
                try:
                    return float(match.group(1))
                except ValueError:
                    continue
        
        return None
    
    def _get_default_quantity(self, symbol: str, price: float) -> float:
        """获取默认数量"""
        try:
            # 根据交易对和价格计算默认数量
            if 'BTC' in symbol:
                return 0.01  # 默认0.01 BTC
            elif 'ETH' in symbol:
                return 0.1   # 默认0.1 ETH
            elif 'USDT' in symbol:
                return 100   # 默认100 USDT
            else:
                return 0.01  # 默认0.01
                
        except Exception as e:
            logger.error(f"获取默认数量失败: {e}")
            return 0.01
    
    def _calculate_confidence(self, alert_data: Dict[str, Any]) -> float:
        """计算置信度"""
        try:
            confidence = 1.0
            
            # 检查必要字段
            required_fields = ['symbol', 'action', 'price']
            for field in required_fields:
                if field not in alert_data or not alert_data[field]:
                    confidence -= 0.2
            
            # 检查价格合理性
            price = alert_data.get('price', 0)
            if price <= 0:
                confidence -= 0.3
            
            # 检查数量合理性
            quantity = alert_data.get('quantity', 0)
            if quantity <= 0:
                confidence -= 0.1
            
            # 检查消息内容
            message = alert_data.get('message', '')
            if len(message) < 10:
                confidence -= 0.1
            
            return max(0.1, confidence)  # 最低0.1
            
        except Exception as e:
            logger.error(f"计算置信度失败: {e}")
            return 0.5
    
    def validate_instruction(self, instruction: TradeInstruction) -> Tuple[bool, str]:
        """验证交易指令"""
        try:
            # 检查交易对
            if not instruction.symbol or len(instruction.symbol) < 6:
                return False, "交易对格式无效"
            
            # 检查价格
            if instruction.price <= 0:
                return False, "价格必须大于0"
            
            # 检查数量
            if instruction.quantity <= 0:
                return False, "数量必须大于0"
            
            # 检查动作
            if not instruction.action:
                return False, "交易动作无效"
            
            # 检查置信度
            if instruction.confidence < 0.1:
                return False, "置信度过低"
            
            return True, "验证通过"
            
        except Exception as e:
            logger.error(f"验证交易指令失败: {e}")
            return False, f"验证异常: {e}"
    
    def get_supported_symbols(self) -> List[str]:
        """获取支持的交易对列表"""
        return list(self.symbol_patterns.keys())
    
    def get_supported_actions(self) -> List[str]:
        """获取支持的交易动作列表"""
        return [action.value for action in TradeAction]
