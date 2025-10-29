#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
TradingView消息提醒接收器
接收TradingView Alert并执行交易
"""

import asyncio
import json
import hmac
import hashlib
from datetime import datetime
from typing import Dict, Any, Optional
from flask import Flask, request, jsonify
from flask_cors import CORS

from core.market_trade.trade_service import TradeService
from core.message_forward.manager import MessageForwardManager
from core.message_forward.models import Message, MessageType, PlatformType
from utils.logger import get_logger

logger = get_logger(__name__)

class TradingViewAlertReceiver:
    """TradingView消息提醒接收器"""
    
    def __init__(self, trade_service: TradeService = None, message_manager: MessageForwardManager = None):
        self.trade_service = trade_service
        self.message_manager = message_manager
        self.app = Flask(__name__)
        CORS(self.app)
        self._setup_routes()
        
        # 交易统计
        self.trade_stats = {
            'total_alerts': 0,
            'successful_trades': 0,
            'failed_trades': 0,
            'last_alert_time': None
        }
        
        # 配置
        self.config = {
            'secret_key': None,
            'enable_notifications': True,
            'max_position_size': 10000,  # 最大仓位大小(USDT)
            'min_confidence': 0.7,      # 最小置信度
            'default_exchange': 'okx',   # 默认交易所
            'default_account_type': 'futures'  # 默认账户类型
        }
    
    def _setup_routes(self):
        """设置路由"""
        
        @self.app.route('/webhook/tradingview', methods=['POST'])
        def receive_tradingview_alert():
            """接收TradingView Alert"""
            return self._handle_tradingview_alert()
        
        @self.app.route('/webhook/status', methods=['GET'])
        def get_status():
            """获取Webhook状态"""
            return jsonify({
                'status': 'active',
                'stats': self.trade_stats,
                'config': self.config,
                'timestamp': datetime.now().isoformat()
            })
    
    def _verify_signature(self, payload: str, signature: str) -> bool:
        """验证Webhook签名"""
        if not self.config['secret_key']:
            return True  # 如果没有设置密钥，跳过验证
        
        try:
            expected_signature = hmac.new(
                self.config['secret_key'].encode('utf-8'),
                payload.encode('utf-8'),
                hashlib.sha256
            ).hexdigest()
            
            return hmac.compare_digest(signature, expected_signature)
        except Exception as e:
            logger.error(f"签名验证失败: {e}")
            return False
    
    def _handle_tradingview_alert(self):
        """处理TradingView Alert"""
        try:
            # 获取原始数据
            payload = request.get_data(as_text=True)
            signature = request.headers.get('X-Signature', '')
            
            # 验证签名
            if not self._verify_signature(payload, signature):
                logger.warning("TradingView Webhook签名验证失败")
                return jsonify({'error': 'Invalid signature'}), 401
            
            # 解析JSON
            data = json.loads(payload)
            logger.info(f"收到TradingView Alert: {data}")
            
            # 更新统计
            self.trade_stats['total_alerts'] += 1
            self.trade_stats['last_alert_time'] = datetime.now().isoformat()
            
            # 异步处理交易
            asyncio.create_task(self._process_tradingview_alert(data))
            
            return jsonify({'status': 'received', 'timestamp': datetime.now().isoformat()})
            
        except Exception as e:
            logger.error(f"处理TradingView Alert失败: {e}")
            return jsonify({'error': str(e)}), 500
    
    async def _process_tradingview_alert(self, data: Dict[str, Any]):
        """处理TradingView Alert并执行交易"""
        try:
            # 解析Alert数据
            trade_info = self._parse_alert_data(data)
            
            if not trade_info:
                logger.warning("Alert数据解析失败")
                self.trade_stats['failed_trades'] += 1
                return
            
            # 执行交易
            success = await self._execute_trade(trade_info)
            
            if success:
                self.trade_stats['successful_trades'] += 1
                logger.info(f"✅ TradingView交易执行成功: {trade_info}")
            else:
                self.trade_stats['failed_trades'] += 1
                logger.error(f"❌ TradingView交易执行失败: {trade_info}")
            
            # 发送通知
            if self.config['enable_notifications']:
                await self._send_trade_notification(trade_info, success)
            
        except Exception as e:
            logger.error(f"处理TradingView Alert异常: {e}")
            self.trade_stats['failed_trades'] += 1
    
    def _parse_alert_data(self, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """解析Alert数据"""
        try:
            # 提取基本信息
            symbol = data.get('symbol', '').upper()
            action = data.get('action', '').upper()
            price = data.get('price', 0)
            quantity = data.get('quantity', 0)
            message = data.get('message', '')
            
            # 验证必要字段
            if not symbol or not action or not price:
                logger.warning(f"Alert缺少必要字段: symbol={symbol}, action={action}, price={price}")
                return None
            
            # 标准化交易对格式
            if not symbol.endswith('USDT') and not symbol.endswith('BTC') and not symbol.endswith('ETH'):
                symbol = f"{symbol}USDT"
            
            # 解析交易动作
            if action in ['BUY', 'LONG', '开多', '做多', '买入']:
                trade_action = 'buy'
            elif action in ['SELL', 'SHORT', '开空', '做空', '卖出']:
                trade_action = 'sell'
            elif action in ['CLOSE', '平仓', '关闭']:
                trade_action = 'close'
            else:
                logger.warning(f"未知的交易动作: {action}")
                return None
            
            # 解析数量
            if not quantity or quantity <= 0:
                # 尝试从消息中提取数量
                quantity = self._extract_quantity_from_message(message)
                if not quantity:
                    quantity = 0.01  # 默认数量
            
            trade_info = {
                'symbol': symbol,
                'action': trade_action,
                'price': float(price),
                'quantity': float(quantity),
                'message': message,
                'alert_name': data.get('alert_name', ''),
                'strategy': data.get('strategy', 'TradingView'),
                'timestamp': datetime.now(),
                'original_data': data
            }
            
            logger.info(f"Alert解析成功: {trade_info}")
            return trade_info
            
        except Exception as e:
            logger.error(f"解析Alert数据失败: {e}")
            return None
    
    def _extract_quantity_from_message(self, message: str) -> Optional[float]:
        """从消息中提取数量"""
        try:
            import re
            
            # 查找数量模式
            patterns = [
                r'(\d+\.?\d*)\s*btc',  # 0.1 btc
                r'(\d+\.?\d*)\s*eth',  # 1.5 eth
                r'(\d+\.?\d*)\s*usdt',  # 1000 usdt
                r'数量[:\s]*(\d+\.?\d*)',  # 数量: 0.1
                r'amount[:\s]*(\d+\.?\d*)',  # amount: 1000
                r'(\d+\.?\d*)\s*个',  # 0.1个
            ]
            
            for pattern in patterns:
                match = re.search(pattern, message.lower())
                if match:
                    return float(match.group(1))
            
            return None
            
        except Exception as e:
            logger.error(f"提取数量失败: {e}")
            return None
    
    async def _execute_trade(self, trade_info: Dict[str, Any]) -> bool:
        """执行交易"""
        try:
            if not self.trade_service:
                logger.error("交易服务未初始化")
                return False
            
            symbol = trade_info['symbol']
            action = trade_info['action']
            price = trade_info['price']
            quantity = trade_info['quantity']
            
            logger.info(f"执行交易: {symbol} {action} @ {price} 数量: {quantity}")
            
            # 构建订单参数
            order_params = {
                'symbol': symbol,
                'side': action,
                'order_type': 'market',  # 市价单
                'quantity': quantity,
                'price': price,
                'metadata': {
                    'source': 'TradingView',
                    'alert_name': trade_info['alert_name'],
                    'strategy': trade_info['strategy'],
                    'message': trade_info['message']
                }
            }
            
            # 执行订单
            order_result = await self.trade_service.place_order(**order_params)
            
            if order_result and order_result.get('success'):
                logger.info(f"✅ 交易执行成功: {order_result}")
                return True
            else:
                logger.error(f"❌ 交易执行失败: {order_result}")
                return False
                
        except Exception as e:
            logger.error(f"执行交易异常: {e}")
            return False
    
    async def _send_trade_notification(self, trade_info: Dict[str, Any], success: bool):
        """发送交易通知"""
        try:
            if not self.message_manager:
                return
            
            # 构建通知消息
            status_emoji = "✅" if success else "❌"
            status_text = "成功" if success else "失败"
            
            message_content = f"""
{status_emoji} TradingView交易{status_text}

📊 交易信息:
• 交易对: {trade_info['symbol']}
• 动作: {trade_info['action']}
• 价格: {trade_info['price']}
• 数量: {trade_info['quantity']}
• 策略: {trade_info['strategy']}
• Alert: {trade_info['alert_name']}

💬 消息: {trade_info['message']}
⏰ 时间: {trade_info['timestamp'].strftime('%Y-%m-%d %H:%M:%S')}
            """
            
            # 创建消息对象
            message = Message(
                content=message_content.strip(),
                message_type=MessageType.TEXT,
                source_platform=PlatformType.SYSTEM,
                source_chat_id="tradingview_alert",
                source_user_id="system",
                source_username="TradingView Alert",
                extra_data={
                    'trade_info': trade_info,
                    'success': success,
                    'source': 'TradingView'
                }
            )
            
            # 发送通知
            await self.message_manager.forward_message(message)
            
        except Exception as e:
            logger.error(f"发送交易通知失败: {e}")
    
    def update_config(self, key: str, value: Any) -> bool:
        """更新配置"""
        try:
            if key in self.config:
                self.config[key] = value
                logger.info(f"✅ 配置已更新: {key} = {value}")
                return True
            else:
                logger.warning(f"配置项不存在: {key}")
                return False
        except Exception as e:
            logger.error(f"更新配置失败: {e}")
            return False
    
    def get_status(self) -> Dict[str, Any]:
        """获取状态"""
        return {
            'status': 'active',
            'stats': self.trade_stats,
            'config': self.config,
            'timestamp': datetime.now().isoformat()
        }
    
    def run(self, host: str = '0.0.0.0', port: int = 5001, debug: bool = False):
        """启动Webhook服务器"""
        logger.info(f"🚀 TradingView Alert接收器启动: {host}:{port}")
        self.app.run(host=host, port=port, debug=debug)

# 全局实例
alert_receiver = None

def get_alert_receiver(trade_service: TradeService = None, message_manager: MessageForwardManager = None) -> TradingViewAlertReceiver:
    """获取Alert接收器实例"""
    global alert_receiver
    if alert_receiver is None:
        alert_receiver = TradingViewAlertReceiver(trade_service, message_manager)
    return alert_receiver

if __name__ == "__main__":
    # 测试运行
    receiver = TradingViewAlertReceiver()
    receiver.run(debug=True)
