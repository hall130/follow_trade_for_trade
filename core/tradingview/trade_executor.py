#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
TradingView交易执行器
执行TradingView Alert交易指令
"""

import asyncio
from datetime import datetime
from typing import Dict, Any, Optional, List
from dataclasses import dataclass

from .alert_parser import TradeInstruction, TradeAction
from core.market_trade.trade_service import TradeService
from core.message_forward.manager import MessageForwardManager
from core.message_forward.models import Message, MessageType, PlatformType
from utils.logger import get_logger

logger = get_logger(__name__)

@dataclass
class ExecutionResult:
    """执行结果"""
    success: bool
    order_id: Optional[str] = None
    error_message: Optional[str] = None
    execution_time: Optional[datetime] = None
    metadata: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}

class TradingViewTradeExecutor:
    """TradingView交易执行器"""
    
    def __init__(self, trade_service: TradeService = None, message_manager: MessageForwardManager = None):
        self.trade_service = trade_service
        self.message_manager = message_manager
        
        # 执行配置
        self.config = {
            'max_position_size': 10000,  # 最大仓位大小(USDT)
            'min_confidence': 0.7,        # 最小置信度
            'enable_notifications': True,  # 启用通知
            'enable_risk_management': True, # 启用风险管理
            'default_exchange': 'okx',    # 默认交易所
            'default_account_type': 'futures', # 默认账户类型
            'max_daily_trades': 50,       # 每日最大交易次数
            'enable_stop_loss': True,     # 启用止损
            'stop_loss_percentage': 0.02, # 止损百分比(2%)
            'enable_take_profit': True,   # 启用止盈
            'take_profit_percentage': 0.05 # 止盈百分比(5%)
        }
        
        # 执行历史
        self.execution_history: List[ExecutionResult] = []
        
        # 风险管理
        self.risk_manager = TradingViewRiskManager(self.config)
        
        logger.info("TradingView交易执行器初始化完成")
    
    async def execute_instruction(self, instruction: TradeInstruction) -> ExecutionResult:
        """执行交易指令"""
        try:
            logger.info(f"🎯 开始执行交易指令: {instruction}")
            
            # 1. 指令验证
            is_valid, error_msg = self._validate_instruction(instruction)
            if not is_valid:
                logger.warning(f"交易指令验证失败: {error_msg}")
                return ExecutionResult(
                    success=False,
                    error_message=error_msg,
                    execution_time=datetime.now()
                )
            
            # 2. 风险管理检查
            if not await self.risk_manager.check_instruction(instruction):
                logger.warning(f"风险管理检查失败: {instruction}")
                return ExecutionResult(
                    success=False,
                    error_message="风险管理检查失败",
                    execution_time=datetime.now()
                )
            
            # 3. 执行交易
            execution_result = await self._execute_trade(instruction)
            
            # 4. 记录执行结果
            self.execution_history.append(execution_result)
            
            # 5. 发送通知
            if self.config['enable_notifications']:
                await self._send_execution_notification(instruction, execution_result)
            
            # 6. 更新风险管理状态
            await self.risk_manager.update_after_execution(instruction, execution_result)
            
            logger.info(f"✅ 交易指令执行完成: {execution_result.success}")
            return execution_result
            
        except Exception as e:
            logger.error(f"执行交易指令失败: {e}")
            result = ExecutionResult(
                success=False,
                error_message=str(e),
                execution_time=datetime.now()
            )
            self.execution_history.append(result)
            return result
    
    def _validate_instruction(self, instruction: TradeInstruction) -> tuple[bool, str]:
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
            if instruction.confidence < self.config['min_confidence']:
                return False, f"置信度过低: {instruction.confidence} < {self.config['min_confidence']}"
            
            # 检查仓位大小
            position_value = instruction.price * instruction.quantity
            if position_value > self.config['max_position_size']:
                return False, f"仓位价值超过限制: {position_value} > {self.config['max_position_size']}"
            
            return True, "验证通过"
            
        except Exception as e:
            logger.error(f"验证交易指令失败: {e}")
            return False, f"验证异常: {e}"
    
    async def _execute_trade(self, instruction: TradeInstruction) -> ExecutionResult:
        """执行交易"""
        try:
            start_time = datetime.now()
            
            if not self.trade_service:
                return ExecutionResult(
                    success=False,
                    error_message="交易服务未初始化",
                    execution_time=start_time
                )
            
            # 根据交易动作执行不同的交易逻辑
            if instruction.action == TradeAction.BUY:
                result = await self._execute_buy_order(instruction)
            elif instruction.action == TradeAction.SELL:
                result = await self._execute_sell_order(instruction)
            elif instruction.action == TradeAction.CLOSE_LONG:
                result = await self._execute_close_long_order(instruction)
            elif instruction.action == TradeAction.CLOSE_SHORT:
                result = await self._execute_close_short_order(instruction)
            elif instruction.action == TradeAction.STOP_LOSS:
                result = await self._execute_stop_loss_order(instruction)
            elif instruction.action == TradeAction.TAKE_PROFIT:
                result = await self._execute_take_profit_order(instruction)
            else:
                result = ExecutionResult(
                    success=False,
                    error_message=f"不支持的交易动作: {instruction.action}",
                    execution_time=start_time
                )
            
            result.execution_time = start_time
            return result
            
        except Exception as e:
            logger.error(f"执行交易异常: {e}")
            return ExecutionResult(
                success=False,
                error_message=str(e),
                execution_time=datetime.now()
            )
    
    async def _execute_buy_order(self, instruction: TradeInstruction) -> ExecutionResult:
        """执行买入订单"""
        try:
            logger.info(f"📈 执行买入订单: {instruction.symbol} @ {instruction.price}")
            
            # 构建订单参数
            order_params = {
                'symbol': instruction.symbol,
                'side': 'buy',
                'order_type': instruction.order_type,
                'quantity': instruction.quantity,
                'price': instruction.price,
                'metadata': {
                    'source': 'TradingView',
                    'instruction_id': f"tv_{int(datetime.now().timestamp())}",
                    'confidence': instruction.confidence,
                    'reason': instruction.reason,
                    **instruction.metadata
                }
            }
            
            # 执行订单
            order_result = await self.trade_service.place_order(**order_params)
            
            if order_result and order_result.get('success'):
                # 设置止损止盈
                if self.config['enable_stop_loss'] or self.config['enable_take_profit']:
                    await self._set_stop_loss_take_profit(instruction, order_result)
                
                return ExecutionResult(
                    success=True,
                    order_id=order_result.get('order_id'),
                    metadata=order_result
                )
            else:
                return ExecutionResult(
                    success=False,
                    error_message=order_result.get('error', '买入订单执行失败')
                )
                
        except Exception as e:
            logger.error(f"执行买入订单失败: {e}")
            return ExecutionResult(
                success=False,
                error_message=str(e)
            )
    
    async def _execute_sell_order(self, instruction: TradeInstruction) -> ExecutionResult:
        """执行卖出订单"""
        try:
            logger.info(f"📉 执行卖出订单: {instruction.symbol} @ {instruction.price}")
            
            # 构建订单参数
            order_params = {
                'symbol': instruction.symbol,
                'side': 'sell',
                'order_type': instruction.order_type,
                'quantity': instruction.quantity,
                'price': instruction.price,
                'metadata': {
                    'source': 'TradingView',
                    'instruction_id': f"tv_{int(datetime.now().timestamp())}",
                    'confidence': instruction.confidence,
                    'reason': instruction.reason,
                    **instruction.metadata
                }
            }
            
            # 执行订单
            order_result = await self.trade_service.place_order(**order_params)
            
            if order_result and order_result.get('success'):
                return ExecutionResult(
                    success=True,
                    order_id=order_result.get('order_id'),
                    metadata=order_result
                )
            else:
                return ExecutionResult(
                    success=False,
                    error_message=order_result.get('error', '卖出订单执行失败')
                )
                
        except Exception as e:
            logger.error(f"执行卖出订单失败: {e}")
            return ExecutionResult(
                success=False,
                error_message=str(e)
            )
    
    async def _execute_close_long_order(self, instruction: TradeInstruction) -> ExecutionResult:
        """执行平多订单"""
        try:
            logger.info(f"🔒 执行平多订单: {instruction.symbol}")
            
            # 获取当前多头仓位
            positions = await self.trade_service.get_positions(instruction.symbol)
            long_position = None
            
            for pos in positions:
                if pos.get('side') == 'long' and float(pos.get('size', 0)) > 0:
                    long_position = pos
                    break
            
            if not long_position:
                return ExecutionResult(
                    success=False,
                    error_message="没有多头仓位可平"
                )
            
            # 执行平仓
            close_params = {
                'symbol': instruction.symbol,
                'side': 'sell',
                'order_type': 'market',
                'quantity': float(long_position['size']),
                'metadata': {
                    'source': 'TradingView',
                    'action': 'close_long',
                    'original_position': long_position,
                    **instruction.metadata
                }
            }
            
            order_result = await self.trade_service.place_order(**close_params)
            
            if order_result and order_result.get('success'):
                return ExecutionResult(
                    success=True,
                    order_id=order_result.get('order_id'),
                    metadata=order_result
                )
            else:
                return ExecutionResult(
                    success=False,
                    error_message=order_result.get('error', '平多订单执行失败')
                )
                
        except Exception as e:
            logger.error(f"执行平多订单失败: {e}")
            return ExecutionResult(
                success=False,
                error_message=str(e)
            )
    
    async def _execute_close_short_order(self, instruction: TradeInstruction) -> ExecutionResult:
        """执行平空订单"""
        try:
            logger.info(f"🔓 执行平空订单: {instruction.symbol}")
            
            # 获取当前空头仓位
            positions = await self.trade_service.get_positions(instruction.symbol)
            short_position = None
            
            for pos in positions:
                if pos.get('side') == 'short' and float(pos.get('size', 0)) > 0:
                    short_position = pos
                    break
            
            if not short_position:
                return ExecutionResult(
                    success=False,
                    error_message="没有空头仓位可平"
                )
            
            # 执行平仓
            close_params = {
                'symbol': instruction.symbol,
                'side': 'buy',
                'order_type': 'market',
                'quantity': float(short_position['size']),
                'metadata': {
                    'source': 'TradingView',
                    'action': 'close_short',
                    'original_position': short_position,
                    **instruction.metadata
                }
            }
            
            order_result = await self.trade_service.place_order(**close_params)
            
            if order_result and order_result.get('success'):
                return ExecutionResult(
                    success=True,
                    order_id=order_result.get('order_id'),
                    metadata=order_result
                )
            else:
                return ExecutionResult(
                    success=False,
                    error_message=order_result.get('error', '平空订单执行失败')
                )
                
        except Exception as e:
            logger.error(f"执行平空订单失败: {e}")
            return ExecutionResult(
                success=False,
                error_message=str(e)
            )
    
    async def _execute_stop_loss_order(self, instruction: TradeInstruction) -> ExecutionResult:
        """执行止损订单"""
        try:
            logger.info(f"🛑 执行止损订单: {instruction.symbol} @ {instruction.price}")
            
            # 获取当前仓位
            positions = await self.trade_service.get_positions(instruction.symbol)
            
            if not positions:
                return ExecutionResult(
                    success=False,
                    error_message="没有仓位可设置止损"
                )
            
            # 为每个仓位设置止损
            results = []
            for position in positions:
                if float(position.get('size', 0)) > 0:
                    stop_params = {
                        'symbol': instruction.symbol,
                        'side': 'sell' if position.get('side') == 'long' else 'buy',
                        'order_type': 'stop_market',
                        'quantity': float(position['size']),
                        'stop_price': instruction.price,
                        'metadata': {
                            'source': 'TradingView',
                            'action': 'stop_loss',
                            'original_position': position,
                            **instruction.metadata
                        }
                    }
                    
                    order_result = await self.trade_service.place_order(**stop_params)
                    results.append(order_result)
            
            # 检查结果
            success_count = sum(1 for r in results if r and r.get('success'))
            
            if success_count > 0:
                return ExecutionResult(
                    success=True,
                    metadata={'stop_loss_results': results}
                )
            else:
                return ExecutionResult(
                    success=False,
                    error_message="所有止损订单执行失败"
                )
                
        except Exception as e:
            logger.error(f"执行止损订单失败: {e}")
            return ExecutionResult(
                success=False,
                error_message=str(e)
            )
    
    async def _execute_take_profit_order(self, instruction: TradeInstruction) -> ExecutionResult:
        """执行止盈订单"""
        try:
            logger.info(f"💰 执行止盈订单: {instruction.symbol} @ {instruction.price}")
            
            # 获取当前仓位
            positions = await self.trade_service.get_positions(instruction.symbol)
            
            if not positions:
                return ExecutionResult(
                    success=False,
                    error_message="没有仓位可设置止盈"
                )
            
            # 为每个仓位设置止盈
            results = []
            for position in positions:
                if float(position.get('size', 0)) > 0:
                    tp_params = {
                        'symbol': instruction.symbol,
                        'side': 'sell' if position.get('side') == 'long' else 'buy',
                        'order_type': 'limit',
                        'quantity': float(position['size']),
                        'price': instruction.price,
                        'metadata': {
                            'source': 'TradingView',
                            'action': 'take_profit',
                            'original_position': position,
                            **instruction.metadata
                        }
                    }
                    
                    order_result = await self.trade_service.place_order(**tp_params)
                    results.append(order_result)
            
            # 检查结果
            success_count = sum(1 for r in results if r and r.get('success'))
            
            if success_count > 0:
                return ExecutionResult(
                    success=True,
                    metadata={'take_profit_results': results}
                )
            else:
                return ExecutionResult(
                    success=False,
                    error_message="所有止盈订单执行失败"
                )
                
        except Exception as e:
            logger.error(f"执行止盈订单失败: {e}")
            return ExecutionResult(
                success=False,
                error_message=str(e)
            )
    
    async def _set_stop_loss_take_profit(self, instruction: TradeInstruction, order_result: Dict[str, Any]):
        """设置止损止盈"""
        try:
            if not self.config['enable_stop_loss'] and not self.config['enable_take_profit']:
                return
            
            symbol = instruction.symbol
            price = instruction.price
            quantity = instruction.quantity
            
            # 设置止损
            if self.config['enable_stop_loss']:
                stop_loss_price = price * (1 - self.config['stop_loss_percentage'])
                stop_params = {
                    'symbol': symbol,
                    'side': 'sell',
                    'order_type': 'stop_market',
                    'quantity': quantity,
                    'stop_price': stop_loss_price,
                    'metadata': {
                        'source': 'TradingView',
                        'action': 'auto_stop_loss',
                        'original_order_id': order_result.get('order_id')
                    }
                }
                
                await self.trade_service.place_order(**stop_params)
                logger.info(f"✅ 自动止损已设置: {stop_loss_price}")
            
            # 设置止盈
            if self.config['enable_take_profit']:
                take_profit_price = price * (1 + self.config['take_profit_percentage'])
                tp_params = {
                    'symbol': symbol,
                    'side': 'sell',
                    'order_type': 'limit',
                    'quantity': quantity,
                    'price': take_profit_price,
                    'metadata': {
                        'source': 'TradingView',
                        'action': 'auto_take_profit',
                        'original_order_id': order_result.get('order_id')
                    }
                }
                
                await self.trade_service.place_order(**tp_params)
                logger.info(f"✅ 自动止盈已设置: {take_profit_price}")
                
        except Exception as e:
            logger.error(f"设置止损止盈失败: {e}")
    
    async def _send_execution_notification(self, instruction: TradeInstruction, result: ExecutionResult):
        """发送执行通知"""
        try:
            if not self.message_manager:
                return
            
            # 构建通知消息
            status_emoji = "✅" if result.success else "❌"
            status_text = "成功" if result.success else "失败"
            
            message_content = f"""
{status_emoji} TradingView交易{status_text}

📊 交易信息:
• 交易对: {instruction.symbol}
• 动作: {instruction.action.value}
• 价格: {instruction.price}
• 数量: {instruction.quantity}
• 订单类型: {instruction.order_type}
• 置信度: {instruction.confidence:.2%}

💬 原因: {instruction.reason}
⏰ 执行时间: {result.execution_time.strftime('%Y-%m-%d %H:%M:%S')}
🆔 订单ID: {result.order_id or 'N/A'}
            """
            
            if not result.success:
                message_content += f"\n❌ 错误: {result.error_message}"
            
            # 创建消息对象
            message = Message(
                content=message_content.strip(),
                message_type=MessageType.TEXT,
                source_platform=PlatformType.SYSTEM,
                source_chat_id="tradingview_executor",
                source_user_id="system",
                source_username="TradingView Executor",
                extra_data={
                    'instruction': {
                        'symbol': instruction.symbol,
                        'action': instruction.action.value,
                        'price': instruction.price,
                        'quantity': instruction.quantity
                    },
                    'result': {
                        'success': result.success,
                        'order_id': result.order_id,
                        'error_message': result.error_message
                    }
                }
            )
            
            # 发送通知
            await self.message_manager.forward_message(message)
            
        except Exception as e:
            logger.error(f"发送执行通知失败: {e}")
    
    def get_execution_history(self, limit: int = 100) -> List[ExecutionResult]:
        """获取执行历史"""
        return self.execution_history[-limit:]
    
    def get_execution_statistics(self) -> Dict[str, Any]:
        """获取执行统计"""
        total_executions = len(self.execution_history)
        successful_executions = sum(1 for r in self.execution_history if r.success)
        
        return {
            'total_executions': total_executions,
            'successful_executions': successful_executions,
            'failed_executions': total_executions - successful_executions,
            'success_rate': successful_executions / total_executions if total_executions > 0 else 0,
            'last_execution': self.execution_history[-1].execution_time if self.execution_history else None,
            'config': self.config
        }
    
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

class TradingViewRiskManager:
    """TradingView风险管理器"""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.daily_trades = {}  # 每日交易统计
        self.position_limits = {}  # 仓位限制
    
    async def check_instruction(self, instruction: TradeInstruction) -> bool:
        """检查交易指令风险"""
        try:
            # 1. 检查最大仓位限制
            if not await self._check_position_limit(instruction):
                return False
            
            # 2. 检查每日交易限制
            if not await self._check_daily_limit(instruction):
                return False
            
            # 3. 检查市场时间
            if not await self._check_market_hours(instruction):
                return False
            
            # 4. 检查价格异常
            if not await self._check_price_anomaly(instruction):
                return False
            
            return True
            
        except Exception as e:
            logger.error(f"风险管理检查异常: {e}")
            return False
    
    async def _check_position_limit(self, instruction: TradeInstruction) -> bool:
        """检查仓位限制"""
        try:
            # 计算仓位价值
            position_value = instruction.price * instruction.quantity
            
            if position_value > self.config['max_position_size']:
                logger.warning(f"仓位价值超过限制: {position_value} > {self.config['max_position_size']}")
                return False
            
            return True
            
        except Exception as e:
            logger.error(f"检查仓位限制失败: {e}")
            return False
    
    async def _check_daily_limit(self, instruction: TradeInstruction) -> bool:
        """检查每日交易限制"""
        try:
            today = datetime.now().date()
            symbol = instruction.symbol
            
            if today not in self.daily_trades:
                self.daily_trades[today] = {}
            
            if symbol not in self.daily_trades[today]:
                self.daily_trades[today][symbol] = 0
            
            # 检查每日交易次数限制
            max_daily_trades = self.config.get('max_daily_trades', 50)
            if self.daily_trades[today][symbol] >= max_daily_trades:
                logger.warning(f"每日交易次数超限: {symbol} -> {self.daily_trades[today][symbol]}")
                return False
            
            # 增加计数
            self.daily_trades[today][symbol] += 1
            
            return True
            
        except Exception as e:
            logger.error(f"检查每日限制失败: {e}")
            return False
    
    async def _check_market_hours(self, instruction: TradeInstruction) -> bool:
        """检查市场时间"""
        try:
            # 加密货币市场24小时开放，这里可以添加其他检查
            return True
            
        except Exception as e:
            logger.error(f"检查市场时间失败: {e}")
            return False
    
    async def _check_price_anomaly(self, instruction: TradeInstruction) -> bool:
        """检查价格异常"""
        try:
            # 这里可以添加价格异常检测逻辑
            # 比如检查价格是否在合理范围内
            return True
            
        except Exception as e:
            logger.error(f"检查价格异常失败: {e}")
            return False
    
    async def update_after_execution(self, instruction: TradeInstruction, result: ExecutionResult):
        """执行后更新风险管理状态"""
        try:
            # 这里可以更新风险管理状态
            # 比如更新仓位信息、风险指标等
            logger.debug(f"更新风险管理状态: {instruction.symbol} -> {result.success}")
            
        except Exception as e:
            logger.error(f"更新风险管理状态失败: {e}")
