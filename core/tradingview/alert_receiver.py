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
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List
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
        
        # 缓存 TradingView 平台实例（使用 Redis，降级到内存）
        self._tradingview_platforms_cache = None
        self._cache_timestamp = None
        self._cache_ttl = 300  # 缓存有效期（秒，5分钟）
        self._redis_cache_ttl = 600  # Redis 缓存有效期（秒，10分钟）
    
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
            logger.info(f"📢 检查通知配置: enable_notifications={self.config.get('enable_notifications')}, message_manager={self.message_manager is not None}")
            if self.config['enable_notifications']:
                logger.info(f"📢 准备发送交易通知，消息管理器: {self.message_manager is not None}")
                await self._send_trade_notification(trade_info, success)
            else:
                logger.warning("⚠️ 通知功能已禁用，不会转发消息。请检查 alert_receiver 的配置。")
            
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
            interval = data.get('interval', '')  # 交易周期：3m, 5m, 15m, 30m, 1h, 2h, 4h, 1day
            
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
            
            # 保存原始 action 和 direct 用于消息格式化
            original_action = action
            original_direct = direct
            
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
                'action': trade_action,  # 内部使用的交易动作（buy/sell/close）
                'price': float(price),
                'quantity': float(quantity),
                'message': message,
                'alert_name': data.get('alert_name', ''),
                'strategy': data.get('strategy', 'TradingView'),
                'timestamp': datetime.now(timezone.utc),  # 使用 UTC 时间，带时区信息
                'original_data': data,
                'direct': original_direct if original_direct else None,  # 保存原始方向信息（SHORT/LONG）
                'original_action': original_action,  # 保存原始 action（BUY/SELL）
                'interval': interval  # 交易周期：3m, 5m, 15m, 30m, 1h, 2h, 4h, 1day
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
            logger.info(f"🔔 开始发送交易通知，消息管理器状态: {self.message_manager is not None}")
            if not self.message_manager:
                logger.warning("⚠️ 消息管理器未初始化，跳过消息转发。请检查消息转发服务是否已启动。")
                return
            logger.info("✅ 消息管理器已初始化，继续处理...")
            
            # 检查策略过滤器（在转发之前）
            # 获取原始数据（包含 type_ 字段）
            original_data = trade_info.get('original_data', {})
            type_ = original_data.get('type_')
            
            # 获取所有 TradingView 平台实例（使用缓存优化）
            tradingview_platforms = self._get_tradingview_platforms()
            
            # 提取关键信息用于过滤
            strategy = type_ or original_data.get('strategy') or original_data.get('indicator')
            original_symbol = trade_info.get('symbol', '').upper()
            
            # 转换合约名称（提前计算，避免重复）
            contract_name = self._convert_symbol_to_contract_name(original_symbol)
            logger.info(f"📝 合约名称转换: {original_symbol} -> {contract_name}")
            
            # 过滤匹配的平台实例
            matched_platforms = []
            for platform_id, platform in tradingview_platforms:
                if self._check_platform_filters(platform_id, platform, strategy, contract_name):
                    matched_platforms.append((platform_id, platform))
            
            # 如果没有匹配的平台，记录日志并返回
            if not matched_platforms:
                logger.info(f"⚠️ 没有 TradingView 平台实例匹配过滤条件。策略: {strategy}, 合约: {contract_name}")
                return
            
            logger.info(f"✅ 找到 {len(matched_platforms)} 个匹配的 TradingView 平台实例，将分别转发消息")
            
            # 创建消息内容（复用，避免重复格式化）
            message_content = self._create_message_content(trade_info, contract_name)
            
            # 为每个匹配的平台实例创建消息并转发（并行处理，提高效率）
            from core.message_forward.models import PlatformType
            
            forward_tasks = []
            for platform_id, platform in matched_platforms:
                # 创建消息对象（使用 Markdown 格式）
                message = Message(
                    content=message_content,
                    message_type=MessageType.MARKDOWN,
                    formatted_content=message_content,  # 钉钉 Markdown 使用 formatted_content
                    source_platform=PlatformType.TRADINGVIEW,
                    source_platform_id=platform_id,  # 使用匹配的平台实例ID
                    source_chat_id="tradingview_webhook",
                    source_user_id="tradingview",
                    source_username="TradingView",
                    extra_data={
                        'trade_info': trade_info,
                        'source': 'TradingView',
                        'signal_received': True
                    }
                )
                
                # 创建转发任务（异步执行）
                async def forward_to_platform(pid: int, msg: Message):
                    """转发消息到指定平台"""
                    try:
                        logger.info(f"📤 开始转发 TradingView 信号到平台 {pid}")
                        logger.debug(f"   消息内容: {msg.content[:100]}...")
                        logger.debug(f"   源平台ID: {msg.source_platform_id}")
                        await self.message_manager._on_message_received(msg)
                        logger.info(f"✅ TradingView 信号已转发到平台 {pid}（_on_message_received 完成）")
                        return {'platform_id': pid, 'success': True}
                    except Exception as e:
                        logger.error(f"❌ 转发 TradingView 信号到平台 {pid} 失败: {e}")
                        import traceback
                        logger.error(f"完整错误堆栈:\n{traceback.format_exc()}")
                        return {'platform_id': pid, 'success': False, 'error': str(e)}
                
                forward_tasks.append(forward_to_platform(platform_id, message))
            
            # 并行执行所有转发任务
            if forward_tasks:
                results = await asyncio.gather(*forward_tasks, return_exceptions=True)
                success_count = sum(1 for r in results if isinstance(r, dict) and r.get('success', False))
                logger.info(f"📊 转发完成: {success_count}/{len(forward_tasks)} 个平台成功")
            
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
    
    def _get_tradingview_platforms(self) -> List[tuple]:
        """
        获取所有 TradingView 平台实例（使用 Redis 缓存优化）
        
        Returns:
            List[tuple]: (platform_id, platform) 元组列表
        """
        from core.message_forward.models import PlatformType
        from typing import List
        import time
        import json
        
        # 尝试从 Redis 获取平台ID列表和配置
        try:
            from core.redis_manager import get_redis_manager
            redis_manager = get_redis_manager()
            
            cache_key_platform_ids = "tradingview:platforms:ids"
            cache_key_platform_configs = "tradingview:platforms:configs"
            
            # 从 Redis 获取平台ID列表和配置
            cached_platform_ids = redis_manager.get(cache_key_platform_ids)
            cached_configs = redis_manager.get(cache_key_platform_configs)
            
            if cached_platform_ids and cached_configs:
                logger.debug(f"✅ 从 Redis 缓存获取 TradingView 平台配置")
                # 从缓存中恢复平台实例
                tradingview_platforms = []
                for platform_id in cached_platform_ids:
                    if str(platform_id) in cached_configs:
                        # 动态创建平台实例
                        if self.message_manager:
                            platform = self.message_manager._get_or_create_platform_instance(platform_id)
                            if platform:
                                tradingview_platforms.append((platform_id, platform))
                
                if tradingview_platforms:
                    logger.info(f"✅ 从 Redis 缓存恢复 {len(tradingview_platforms)} 个 TradingView 平台实例")
                    # 同时更新内存缓存
                    self._tradingview_platforms_cache = tradingview_platforms
                    self._cache_timestamp = time.time()
                    return tradingview_platforms
        except Exception as e:
            logger.debug(f"从 Redis 获取缓存失败，使用数据库查询: {e}")
        
        # 检查内存缓存是否有效（降级方案）
        current_time = time.time()
        if (self._tradingview_platforms_cache is not None and 
            self._cache_timestamp is not None and 
            current_time - self._cache_timestamp < self._cache_ttl):
            logger.debug(f"✅ 使用内存缓存的 TradingView 平台实例（缓存时间: {current_time - self._cache_timestamp:.1f}秒）")
            return self._tradingview_platforms_cache
        
        # 缓存失效或不存在，从数据库重新获取
        tradingview_platforms = []
        platform_ids_set = set()  # 用于去重
        platform_configs = {}  # 保存配置信息用于缓存
        
        if not self.message_manager:
            logger.warning("⚠️ message_manager 未设置，无法获取 TradingView 平台实例")
            return tradingview_platforms
        
        # 来源1: 从 platforms 字典获取
        if hasattr(self.message_manager, 'platforms'):
            for platform_id, platform in self.message_manager.platforms.items():
                if (hasattr(platform, 'platform_type') and 
                    platform.platform_type == PlatformType.TRADINGVIEW and
                    platform_id not in platform_ids_set):
                    tradingview_platforms.append((platform_id, platform))
                    platform_ids_set.add(platform_id)
                    # 保存配置信息
                    if hasattr(platform, 'config'):
                        platform_configs[platform_id] = platform.config
        
        # 来源2: 从监听服务获取
        if hasattr(self.message_manager, '_listener_service') and self.message_manager._listener_service:
            if hasattr(self.message_manager._listener_service, 'listening_platforms'):
                for platform_id, platform in self.message_manager._listener_service.listening_platforms.items():
                    if (hasattr(platform, 'platform_type') and 
                        platform.platform_type == PlatformType.TRADINGVIEW and
                        platform_id not in platform_ids_set):
                        tradingview_platforms.append((platform_id, platform))
                        platform_ids_set.add(platform_id)
                        # 保存配置信息
                        if hasattr(platform, 'config'):
                            platform_configs[platform_id] = platform.config
        
        # 来源3: 从数据库动态查询所有 TradingView 平台实例
        if hasattr(self.message_manager, '_db') and self.message_manager._db:
            try:
                db_pool = None
                if hasattr(self.message_manager._db, 'db_pool'):
                    db_pool = self.message_manager._db.db_pool
                elif hasattr(self.message_manager._db, '_db_pool'):
                    db_pool = self.message_manager._db._db_pool
                elif hasattr(self.message_manager._db, 'query'):
                    db_pool = self.message_manager._db
                
                if db_pool:
                    sql = "SELECT id, config FROM message_platforms WHERE platform_type = 'tradingview' AND enabled = 1"
                    rows = db_pool.query(sql)
                    for row in rows:
                        platform_id = row['id']
                        if platform_id not in platform_ids_set:
                            # 解析配置
                            config_str = row.get('config', '{}')
                            try:
                                if isinstance(config_str, str):
                                    config = json.loads(config_str)
                                else:
                                    config = config_str
                                platform_configs[platform_id] = config
                            except:
                                platform_configs[platform_id] = {}
                            
                            # 动态创建平台实例
                            platform = self.message_manager._get_or_create_platform_instance(platform_id)
                            if platform:
                                tradingview_platforms.append((platform_id, platform))
                                platform_ids_set.add(platform_id)
            except Exception as e:
                logger.warning(f"从数据库查询 TradingView 平台实例失败: {e}")
        
        # 更新内存缓存
        self._tradingview_platforms_cache = tradingview_platforms
        self._cache_timestamp = current_time
        
        # 更新 Redis 缓存（异步，不阻塞）
        try:
            from core.redis_manager import get_redis_manager
            redis_manager = get_redis_manager()
            
            cache_key_platform_ids = "tradingview:platforms:ids"
            cache_key_platform_configs = "tradingview:platforms:configs"
            
            # 缓存平台ID列表
            platform_ids_list = list(platform_ids_set)
            redis_manager.set(cache_key_platform_ids, platform_ids_list, ttl=self._redis_cache_ttl)
            
            # 缓存平台配置信息（转换为字符串键）
            configs_dict = {str(k): v for k, v in platform_configs.items()}
            redis_manager.set(cache_key_platform_configs, configs_dict, ttl=self._redis_cache_ttl)
            
            logger.debug(f"✅ TradingView 平台配置已缓存到 Redis（{len(platform_ids_list)} 个平台，TTL: {self._redis_cache_ttl}秒）")
        except Exception as e:
            logger.debug(f"更新 Redis 缓存失败（不影响功能）: {e}")
        
        logger.info(f"✅ 获取到 {len(tradingview_platforms)} 个 TradingView 平台实例（已缓存）")
        return tradingview_platforms
    
    def _clear_platforms_cache(self):
        """清除平台实例缓存（当平台配置更新时调用）"""
        # 清除内存缓存
        self._tradingview_platforms_cache = None
        self._cache_timestamp = None
        
        # 清除 Redis 缓存
        try:
            from core.redis_manager import get_redis_manager
            redis_manager = get_redis_manager()
            
            cache_key_platform_ids = "tradingview:platforms:ids"
            cache_key_platform_configs = "tradingview:platforms:configs"
            
            redis_manager.delete(cache_key_platform_ids)
            redis_manager.delete(cache_key_platform_configs)
            
            logger.debug("✅ TradingView 平台实例缓存已清除（内存 + Redis）")
        except Exception as e:
            logger.debug(f"清除 Redis 缓存失败（不影响功能）: {e}")
            logger.debug("✅ TradingView 平台实例内存缓存已清除")
    
    def _convert_symbol_to_contract_name(self, symbol: str) -> str:
        """
        将交易对符号转换为标准合约名称
        
        Args:
            symbol: 原始交易对符号（如 BTCUSDT, BTCUSDT28X2025）
        
        Returns:
            标准合约名称（如 BTC-USDT-SWAP）
        """
        if not symbol:
            return "UNKNOWN-USDT-SWAP"
        
        symbol = symbol.upper()
        logger.debug(f"🔍 转换合约名称: {symbol}")
        
        base_symbol = None
        import re
        
        # 方法1: 处理期货合约格式（如 BTCUSDT28X2025, ETHUSDT241229）
        futures_pattern = r'^([A-Z]{2,5})(USDT|USDC|USD)([0-9A-Z]+)$'
        futures_match = re.match(futures_pattern, symbol)
        if futures_match:
            base_symbol = futures_match.group(1)
            logger.debug(f"✅ 识别为期货合约格式: {symbol} -> {base_symbol}")
        
        # 方法2: 处理标准交易对格式（如 BTCUSDT, ETHUSD）
        if not base_symbol:
            suffixes = ['USDT', 'USDC', 'USD', 'BTC', 'ETH']
            for suffix in suffixes:
                if symbol.endswith(suffix) and len(symbol) > len(suffix):
                    base_symbol = symbol[:-len(suffix)]
                    logger.debug(f"✅ 移除后缀: {symbol} -> {base_symbol} (后缀: {suffix})")
                    break
        
        # 方法3: 提取前3个字符
        if not base_symbol:
            if len(symbol) >= 3:
                base_symbol = symbol[:3]
                logger.debug(f"✅ 提取前3个字符: {symbol} -> {base_symbol}")
            else:
                base_symbol = symbol
                logger.debug(f"⚠️ 保持原样: {symbol}")
        
        # 清理基础币种
        base_symbol = base_symbol.replace('USD', '').replace('USDT', '').replace('USDC', '')
        
        # 如果清理后为空或太短，重新提取
        if not base_symbol or len(base_symbol) < 2:
            if len(symbol) >= 3:
                base_symbol = symbol[:3]
            else:
                base_symbol = symbol
        
        contract_name = f"{base_symbol}-USDT-SWAP"
        logger.debug(f"📝 最终合约名称: {contract_name}")
        return contract_name
    
    def _check_platform_filters(
        self, 
        platform_id: int, 
        platform: Any, 
        strategy: Optional[str], 
        contract_name: str
    ) -> bool:
        """
        检查平台过滤条件是否匹配
        
        Args:
            platform_id: 平台ID
            platform: 平台实例
            strategy: 策略类型（type_ 字段）
            contract_name: 转换后的合约名称
        
        Returns:
            是否匹配
        """
        # 检查策略过滤器
        strategy_filter = getattr(platform, 'strategy_filter', [])
        if strategy_filter:  # 如果配置了策略过滤器
            if not strategy:
                logger.debug(f"❌ 平台 {platform_id}: 配置了策略过滤器 {strategy_filter}，但消息没有策略标识")
                return False
            if strategy not in strategy_filter:
                logger.debug(f"❌ 平台 {platform_id}: 策略 '{strategy}' 不在过滤器 {strategy_filter} 中")
                return False
            logger.debug(f"✅ 平台 {platform_id}: 策略 '{strategy}' 匹配过滤器 {strategy_filter}")
        else:
            logger.debug(f"✅ 平台 {platform_id}: 未配置策略过滤器，允许所有策略")
        
        # 检查交易对过滤器
        symbol_filter = getattr(platform, 'symbol_filter', [])
        if symbol_filter:  # 如果配置了交易对过滤器
            if contract_name not in symbol_filter:
                logger.debug(f"❌ 平台 {platform_id}: 合约 '{contract_name}' 不在过滤器 {symbol_filter} 中")
                return False
            logger.debug(f"✅ 平台 {platform_id}: 合约 '{contract_name}' 匹配过滤器 {symbol_filter}")
        else:
            logger.debug(f"✅ 平台 {platform_id}: 未配置交易对过滤器，允许所有交易对")
        
        return True
    
    def _format_trade_type(self, action: str, direct: str) -> str:
        """
        格式化交易类型显示
        
        Args:
            action: 交易动作（BUY/SELL）
            direct: 方向（LONG/SHORT）
        
        Returns:
            格式化后的交易类型
        """
        action = action.upper() if action else ''
        direct = direct.upper() if direct else ''
        
        if action == 'BUY' and direct == 'SHORT':
            return "平空"
        elif action == 'SELL' and direct == 'LONG':
            return "平多"
        elif action == 'BUY' and direct == 'LONG':
            return "开多"
        elif action == 'SELL' and direct == 'SHORT':
            return "开空"
        elif action == 'BUY':
            return "买入"
        elif action == 'SELL':
            return "卖出"
        elif action == 'CLOSE':
            if direct == 'SHORT':
                return "平空"
            elif direct == 'LONG':
                return "平多"
            else:
                return "平仓"
        else:
            return action or "未知"
    
    def _format_interval_display(self, interval: str) -> str:
        """
        格式化周期显示
        
        Args:
            interval: 周期字符串（如 15M, 1H, 1DAY）
        
        Returns:
            格式化后的周期显示（如 15分钟, 1小时, 1天）
        """
        if not interval:
            return ''
        
        interval_upper = interval.upper()
        
        if interval_upper.endswith('M'):
            minutes = interval_upper.replace('M', '')
            try:
                minutes_int = int(minutes)
                return f"{minutes_int}分钟"
            except ValueError:
                return interval
        elif interval_upper.endswith('H'):
            hours = interval_upper.replace('H', '')
            try:
                hours_int = int(hours)
                return f"{hours_int}小时"
            except ValueError:
                return interval
        elif interval_upper in ['1DAY', '1D', 'DAY', 'D']:
            return "1天"
        else:
            return interval
    
    def _create_message_content(self, trade_info: Dict[str, Any], contract_name: str) -> str:
        """
        创建消息内容
        
        Args:
            trade_info: 交易信息字典
            contract_name: 合约名称
        
        Returns:
            格式化的消息内容
        """
        # 获取交易类型
        original_action = trade_info.get('original_action', '').upper()
        direct = trade_info.get('direct', '').upper()
        trade_type = self._format_trade_type(original_action, direct)
        
        # 格式化价格
        price = trade_info.get('price', 0)
        price_str = f"${price:,.2f}" if price else "$0.00"
        
        # 格式化时间
        from datetime import timezone, timedelta
        china_tz = timezone(timedelta(hours=8))
        timestamp = trade_info.get('timestamp')
        
        if timestamp is None:
            china_time = datetime.now(china_tz)
        else:
            if timestamp.tzinfo is None:
                timestamp = timestamp.replace(tzinfo=timezone.utc)
            china_time = timestamp.astimezone(china_tz)
        
        time_str = china_time.strftime('%Y-%m-%d %H:%M:%S')
        
        # 格式化周期
        interval = trade_info.get('interval', '')
        interval_display = self._format_interval_display(interval)
        
        # 获取消息内容
        message_content_text = trade_info.get('message', '')
        
        # 构建消息
        message_content = f"""🔔 TradingView 交易信号

📊 **交易类型**: {trade_type}

💵 **价格**:     {price_str}

📈 **合约**:     {contract_name}"""
        
        if interval_display:
            message_content += f"""

⏱️ **周期**:     {interval_display}"""
        
        message_content += f"""

🆔 **消息内容**: {message_content_text}

⏰ **时间**:     {time_str}

---

*来自千里金交易平台*"""
        
        return message_content.strip()
    
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
    else:
        # 如果已存在实例，更新 message_manager（因为每次请求可能不同）
        if message_manager is not None:
            alert_receiver.message_manager = message_manager
            logger.debug("✅ 已更新 alert_receiver 的 message_manager")
    return alert_receiver

if __name__ == "__main__":
    # 测试运行
    receiver = TradingViewAlertReceiver()
    receiver.run(debug=True)
