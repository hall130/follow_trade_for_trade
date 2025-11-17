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
        """解析Alert数据（支持多种格式）"""
        try:
            # 方法1：尝试从标准字段提取
            symbol = data.get('symbol') or data.get('ticker', '').upper()
            action = data.get('action', '').upper()
            direct = data.get('direct', '').upper()  # 方向：LONG/SHORT
            price = data.get('price') or data.get('close', 0)
            quantity = data.get('quantity') or data.get('size') or data.get('amount', 0)
            message = data.get('message', '')
            
            # 方法2：如果标准字段为空，尝试从 Pine Script 变量提取
            if not symbol and 'ticker' in data:
                symbol = str(data['ticker']).upper()
            if not price and 'close' in data:
                try:
                    price = float(data['close'])
                except (ValueError, TypeError):
                    price = 0
            if not action:
                # 尝试从 strategy.order.action 提取
                action = data.get('strategy.order.action', '').upper()
                if not action:
                    # 尝试从消息中提取
                    action = self._extract_action_from_message(message)
            
            # 方法3：如果仍然没有，尝试从消息中解析（支持分隔符格式）
            if not symbol or not action or not price:
                parsed = self._parse_message_format(message)
                if parsed:
                    symbol = parsed.get('symbol') or symbol
                    action = parsed.get('action') or action
                    price = parsed.get('price') or price
                    quantity = parsed.get('quantity') or quantity
            
            # 验证必要字段
            if not symbol:
                logger.warning(f"Alert缺少交易对: data={data}")
                return None
            if not action:
                logger.warning(f"Alert缺少交易动作: data={data}")
                return None
            if not price or price <= 0:
                logger.warning(f"Alert价格无效: price={price}, data={data}")
                return None
            
            # 标准化交易对格式
            if not symbol.endswith('USDT') and not symbol.endswith('BTC') and not symbol.endswith('ETH'):
                symbol = f"{symbol}USDT"
            
            # 解析交易动作（考虑 direct 字段）
            # 如果提供了 direct 字段，结合 action 和 direct 来判断实际交易动作
            # 例如：action=SELL + direct=LONG = 平多仓（close long）
            #      action=BUY + direct=LONG = 开多仓（buy/long）
            #      action=SELL + direct=SHORT = 开空仓（sell/short）
            #      action=BUY + direct=SHORT = 平空仓（close short）
            
            if direct:
                # 有 direct 字段，需要结合 action 和 direct 判断
                if direct in ['LONG', '多', '做多']:
                    if action in ['BUY', '买入']:
                        trade_action = 'buy'  # 开多
                    elif action in ['SELL', '卖出']:
                        trade_action = 'close'  # 平多
                    else:
                        trade_action = 'buy'  # 默认开多
                elif direct in ['SHORT', '空', '做空']:
                    if action in ['SELL', '卖出']:
                        trade_action = 'sell'  # 开空
                    elif action in ['BUY', '买入']:
                        trade_action = 'close'  # 平空
                    else:
                        trade_action = 'sell'  # 默认开空
                else:
                    # direct 字段值未知，回退到只根据 action 判断
                    if action in ['BUY', 'LONG', '开多', '做多', '买入']:
                        trade_action = 'buy'
                    elif action in ['SELL', 'SHORT', '开空', '做空', '卖出']:
                        trade_action = 'sell'
                    elif action in ['CLOSE', '平仓', '关闭']:
                        trade_action = 'close'
                    else:
                        logger.warning(f"未知的交易动作: action={action}, direct={direct}")
                        return None
            else:
                # 没有 direct 字段，只根据 action 判断
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
                'original_data': data,
                'direct': direct if direct else None  # 保存原始方向信息
            }
            
            logger.info(f"Alert解析成功: {trade_info}")
            return trade_info
            
        except Exception as e:
            logger.error(f"解析Alert数据失败: {e}")
            return None
    
    def _extract_action_from_message(self, message: str) -> str:
        """从消息中提取交易动作"""
        try:
            import re
            message_upper = message.upper()
            
            # 买入动作
            if any(keyword in message_upper for keyword in ['BUY', 'LONG', '开多', '做多', '买入', '买']):
                return 'BUY'
            # 卖出动作
            elif any(keyword in message_upper for keyword in ['SELL', 'SHORT', '开空', '做空', '卖出', '卖']):
                return 'SELL'
            # 平仓动作
            elif any(keyword in message_upper for keyword in ['CLOSE', '平仓', '关闭', '平']):
                return 'CLOSE'
            
            return ''
            
        except Exception as e:
            logger.error(f"提取交易动作失败: {e}")
            return ''
    
    def _parse_message_format(self, message: str) -> Optional[Dict[str, Any]]:
        """解析分隔符格式的消息（如：BTCUSDT|50000|BUY|0.1|ASR信号）"""
        try:
            import re
            
            if not message:
                return None
            
            # 尝试分隔符格式：symbol|price|action|quantity|message
            parts = message.split('|')
            if len(parts) >= 3:
                parsed = {}
                if len(parts) > 0:
                    parsed['symbol'] = parts[0].strip().upper()
                if len(parts) > 1:
                    try:
                        parsed['price'] = float(parts[1].strip())
                    except (ValueError, TypeError):
                        pass
                if len(parts) > 2:
                    parsed['action'] = parts[2].strip().upper()
                if len(parts) > 3:
                    try:
                        parsed['quantity'] = float(parts[3].strip())
                    except (ValueError, TypeError):
                        pass
                return parsed
            
            # 尝试其他格式：symbol price action quantity
            pattern = r'([A-Z0-9]+(?:USDT|BTC|ETH)?)\s+([\d.]+)\s+(BUY|SELL|LONG|SHORT|CLOSE|买|卖|开多|开空|平仓)'
            match = re.search(pattern, message.upper())
            if match:
                return {
                    'symbol': match.group(1),
                    'price': float(match.group(2)),
                    'action': match.group(3)
                }
            
            return None
            
        except Exception as e:
            logger.error(f"解析消息格式失败: {e}")
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
            symbol = trade_info['symbol']
            action = trade_info['action']
            price = trade_info['price']
            quantity = trade_info['quantity']
            
            logger.info(f"收到 TradingView 交易信号: {symbol} {action} @ {price} 数量: {quantity}")
            
            # 注意：TradingView webhook 目前只记录警报，不直接执行交易
            # 如果需要执行交易，需要：
            # 1. 配置默认交易账户（API 密钥等）
            # 2. 或者通过消息转发系统触发跟单交易
            
            # 记录交易信号到日志
            logger.info(f"📊 TradingView 交易信号详情:")
            logger.info(f"   - 交易对: {symbol}")
            logger.info(f"   - 动作: {action}")
            logger.info(f"   - 价格: {price}")
            logger.info(f"   - 数量: {quantity}")
            logger.info(f"   - 策略: {trade_info.get('strategy', 'TradingView')}")
            logger.info(f"   - 警报名称: {trade_info.get('alert_name', '')}")
            logger.info(f"   - 消息: {trade_info.get('message', '')}")
            
            # TODO: 如果需要直接执行交易，可以在这里添加逻辑
            # 例如：使用配置的默认账户通过交易所客户端下单
            
            # 目前返回 True 表示信号已接收（但不执行实际交易）
            logger.warning("⚠️ TradingView webhook 目前只记录信号，不执行实际交易。如需执行交易，请配置交易账户或使用消息转发系统。")
            return True
                
        except Exception as e:
            logger.error(f"处理 TradingView 交易信号异常: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return False
    
    async def _send_trade_notification(self, trade_info: Dict[str, Any], success: bool):
        """发送交易信号通知（消息转发）"""
        try:
            if not self.message_manager:
                logger.debug("消息管理器未初始化，跳过消息转发")
                return
            
            # 构建通知消息（当前只转发信号，不执行交易）
            # 格式化动作显示（包含方向信息）
            action_display = trade_info['action'].upper()
            if trade_info.get('direct'):
                direct_display = trade_info['direct']
                if trade_info['action'] == 'close':
                    action_display = f"平仓 ({direct_display})"
                elif trade_info['action'] == 'buy' and direct_display == 'LONG':
                    action_display = f"开多 ({direct_display})"
                elif trade_info['action'] == 'sell' and direct_display == 'SHORT':
                    action_display = f"开空 ({direct_display})"
                else:
                    action_display = f"{action_display} ({direct_display})"
            
            message_content = f"""
📊 TradingView 交易信号

• 交易对: {trade_info['symbol']}
• 动作: {action_display}
• 价格: {trade_info['price']}
• 数量: {trade_info['quantity']}
• 策略: {trade_info.get('strategy', 'TradingView')}
• 警报名称: {trade_info.get('alert_name', '未命名')}

💬 消息: {trade_info.get('message', '无')}
⏰ 时间: {trade_info['timestamp'].strftime('%Y-%m-%d %H:%M:%S')}
            """
            
            # 创建消息对象
            message = Message(
                content=message_content.strip(),
                message_type=MessageType.TEXT,
                source_platform=PlatformType.TRADINGVIEW,  # 使用 TradingView 平台类型
                source_chat_id="tradingview_webhook",
                source_user_id="tradingview",
                source_username="TradingView",
                extra_data={
                    'trade_info': trade_info,
                    'source': 'TradingView',
                    'signal_received': True
                }
            )
            
            # 发送通知（转发消息）
            # 使用 _on_message_received 方法，它会自动应用转发规则
            await self.message_manager._on_message_received(message)
            logger.info("✅ TradingView 信号已转发到消息转发系统")
            
        except Exception as e:
            logger.error(f"发送 TradingView 信号通知失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
    
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
