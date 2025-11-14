#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
TradingView集成管理器
整合TradingView Alert接收、解析和执行功能
"""

import asyncio
import json
import sys
import os
from datetime import datetime
from typing import Dict, Any, Optional, List

# 添加项目根目录到Python路径
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.tradingview.alert_receiver import TradingViewAlertReceiver, get_alert_receiver
from core.tradingview.alert_parser import TradingViewAlertParser, TradeInstruction
from core.tradingview.trade_executor import TradingViewTradeExecutor, ExecutionResult
from core.market_trade.trade_service import TradeService
from core.message_forward.manager import MessageForwardManager
from utils.logger import get_logger

logger = get_logger(__name__)

class TradingViewManager:
    """TradingView集成管理器"""
    
    def __init__(self):
        self.alert_receiver = None
        self.alert_parser = TradingViewAlertParser()
        self.trade_executor = None
        self.trade_service = None
        self.message_manager = None
        
        # 配置
        self.config = {
            'webhook_secret_key': None,
            'webhook_port': 5001,
            'webhook_host': '0.0.0.0',
            'enable_notifications': True,
            'enable_auto_trading': True,
            'enable_risk_management': True,
            'max_position_size': 10000,
            'min_confidence': 0.7,
            'default_exchange': 'okx',
            'default_account_type': 'futures',
            'max_daily_trades': 50,
            'enable_stop_loss': True,
            'stop_loss_percentage': 0.02,
            'enable_take_profit': True,
            'take_profit_percentage': 0.05
        }
        
        # 统计信息
        self.stats = {
            'total_alerts_received': 0,
            'successful_trades': 0,
            'failed_trades': 0,
            'last_alert_time': None,
            'system_start_time': datetime.now()
        }
        
        logger.info("TradingView集成管理器初始化完成")
    
    async def initialize(self, trade_service: TradeService = None, message_manager: MessageForwardManager = None):
        """初始化系统"""
        try:
            logger.info("🚀 初始化TradingView集成系统...")
            
            # 初始化交易服务
            self.trade_service = trade_service
            if not self.trade_service:
                logger.warning("交易服务未提供，将使用模拟模式")
            
            # 初始化消息管理器
            self.message_manager = message_manager
            if not self.message_manager:
                logger.warning("消息管理器未提供，将禁用通知")
            
            # 初始化交易执行器
            self.trade_executor = TradingViewTradeExecutor(self.trade_service, self.message_manager)
            
            # 初始化Alert接收器
            self.alert_receiver = get_alert_receiver(self.trade_service, self.message_manager)
            
            # 更新配置
            self._update_executor_config()
            
            logger.info("✅ TradingView集成系统初始化完成")
            return True
            
        except Exception as e:
            logger.error(f"初始化失败: {e}")
            return False
    
    def _update_executor_config(self):
        """更新执行器配置"""
        try:
            if self.trade_executor:
                for key, value in self.config.items():
                    if key in self.trade_executor.config:
                        self.trade_executor.update_config(key, value)
            
            if self.alert_receiver:
                for key, value in self.config.items():
                    if key in self.alert_receiver.config:
                        self.alert_receiver.update_config(key, value)
                        
        except Exception as e:
            logger.error(f"更新执行器配置失败: {e}")
    
    async def start_webhook_server(self):
        """启动Webhook服务器"""
        try:
            if not self.alert_receiver:
                logger.error("Alert接收器未初始化")
                return False
            
            logger.info(f"🌐 启动TradingView Webhook服务器: {self.config['webhook_host']}:{self.config['webhook_port']}")
            
            # 在后台启动Webhook服务器
            asyncio.create_task(self._run_webhook_server())
            
            return True
            
        except Exception as e:
            logger.error(f"启动Webhook服务器失败: {e}")
            return False
    
    async def _run_webhook_server(self):
        """运行Webhook服务器"""
        try:
            # 这里需要修改为异步运行Flask应用
            # 由于Flask不是原生异步，这里使用线程池
            import threading
            
            def run_flask():
                self.alert_receiver.run(
                    host=self.config['webhook_host'],
                    port=self.config['webhook_port'],
                    debug=False
                )
            
            flask_thread = threading.Thread(target=run_flask, daemon=True)
            flask_thread.start()
            
            logger.info("✅ TradingView Webhook服务器已启动")
            
        except Exception as e:
            logger.error(f"运行Webhook服务器失败: {e}")
    
    async def process_tradingview_alert(self, alert_data: Dict[str, Any]) -> bool:
        """处理TradingView Alert"""
        try:
            logger.info(f"📨 处理TradingView Alert: {alert_data}")
            
            # 更新统计
            self.stats['total_alerts_received'] += 1
            self.stats['last_alert_time'] = datetime.now()
            
            # 解析Alert
            instruction = self.alert_parser.parse_alert(alert_data)
            if not instruction:
                logger.warning("TradingView Alert解析失败")
                self.stats['failed_trades'] += 1
                return False
            
            # 执行交易
            if self.config['enable_auto_trading']:
                execution_result = await self.trade_executor.execute_instruction(instruction)
                
                if execution_result.success:
                    self.stats['successful_trades'] += 1
                    logger.info(f"✅ TradingView交易执行成功: {instruction}")
                else:
                    self.stats['failed_trades'] += 1
                    logger.error(f"❌ TradingView交易执行失败: {instruction}")
                
                return execution_result.success
            else:
                logger.info("自动交易已禁用，仅记录Alert")
                return True
            
        except Exception as e:
            logger.error(f"处理TradingView Alert失败: {e}")
            self.stats['failed_trades'] += 1
            return False
    
    async def process_text_message(self, text: str) -> bool:
        """处理文本消息"""
        try:
            logger.info(f"📝 处理文本消息: {text}")
            
            # 解析文本消息
            instruction = self.alert_parser.parse_text_message(text)
            if not instruction:
                logger.warning("文本消息解析失败")
                return False
            
            # 执行交易
            if self.config['enable_auto_trading']:
                execution_result = await self.trade_executor.execute_instruction(instruction)
                
                if execution_result.success:
                    self.stats['successful_trades'] += 1
                    logger.info(f"✅ 文本消息交易执行成功: {instruction}")
                else:
                    self.stats['failed_trades'] += 1
                    logger.error(f"❌ 文本消息交易执行失败: {instruction}")
                
                return execution_result.success
            else:
                logger.info("自动交易已禁用，仅记录文本消息")
                return True
            
        except Exception as e:
            logger.error(f"处理文本消息失败: {e}")
            return False
    
    def get_system_status(self) -> Dict[str, Any]:
        """获取系统状态"""
        uptime = datetime.now() - self.stats['system_start_time']
        
        return {
            'system_status': 'running',
            'uptime_seconds': uptime.total_seconds(),
            'uptime_human': str(uptime).split('.')[0],
            'webhook_endpoints': {
                'tradingview': f"http://{self.config['webhook_host']}:{self.config['webhook_port']}/webhook/tradingview",
                'status': f"http://{self.config['webhook_host']}:{self.config['webhook_port']}/webhook/status"
            },
            'statistics': self.stats,
            'configuration': self.config,
            'last_update': datetime.now().isoformat()
        }
    
    def get_execution_statistics(self) -> Dict[str, Any]:
        """获取执行统计"""
        if self.trade_executor:
            return self.trade_executor.get_execution_statistics()
        else:
            return {
                'total_executions': 0,
                'successful_executions': 0,
                'failed_executions': 0,
                'success_rate': 0,
                'last_execution': None
            }
    
    def get_execution_history(self, limit: int = 100) -> List[ExecutionResult]:
        """获取执行历史"""
        if self.trade_executor:
            return self.trade_executor.get_execution_history(limit)
        else:
            return []
    
    def update_config(self, key: str, value: Any) -> bool:
        """更新配置"""
        try:
            if key in self.config:
                self.config[key] = value
                
                # 更新执行器配置
                self._update_executor_config()
                
                logger.info(f"✅ 配置已更新: {key} = {value}")
                return True
            else:
                logger.warning(f"配置项不存在: {key}")
                return False
        except Exception as e:
            logger.error(f"更新配置失败: {e}")
            return False
    
    def save_config(self, filename: str = "tradingview_config.json") -> bool:
        """保存配置"""
        try:
            config_data = {
                'config': self.config,
                'stats': self.stats,
                'last_save': datetime.now().isoformat()
            }
            
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(config_data, f, ensure_ascii=False, indent=2)
            
            logger.info(f"✅ 配置已保存到: {filename}")
            return True
            
        except Exception as e:
            logger.error(f"保存配置失败: {e}")
            return False
    
    def load_config(self, filename: str = "tradingview_config.json") -> bool:
        """加载配置"""
        try:
            with open(filename, 'r', encoding='utf-8') as f:
                config_data = json.load(f)
            
            if 'config' in config_data:
                self.config.update(config_data['config'])
            
            # 更新执行器配置
            self._update_executor_config()
            
            logger.info(f"✅ 配置已从文件加载: {filename}")
            return True
            
        except FileNotFoundError:
            logger.info("配置文件不存在，使用默认配置")
            return True
        except Exception as e:
            logger.error(f"加载配置失败: {e}")
            return False
    
    def get_supported_symbols(self) -> List[str]:
        """获取支持的交易对"""
        return self.alert_parser.get_supported_symbols()
    
    def get_supported_actions(self) -> List[str]:
        """获取支持的交易动作"""
        return self.alert_parser.get_supported_actions()
    
    async def test_alert_parsing(self, test_data: Dict[str, Any]) -> Optional[TradeInstruction]:
        """测试Alert解析"""
        try:
            return self.alert_parser.parse_alert(test_data)
        except Exception as e:
            logger.error(f"测试Alert解析失败: {e}")
            return None
    
    async def test_text_parsing(self, text: str) -> Optional[TradeInstruction]:
        """测试文本解析"""
        try:
            return self.alert_parser.parse_text_message(text)
        except Exception as e:
            logger.error(f"测试文本解析失败: {e}")
            return None
    
    async def test_trade_execution(self, instruction: TradeInstruction) -> ExecutionResult:
        """测试交易执行"""
        try:
            if not self.trade_executor:
                return ExecutionResult(
                    success=False,
                    error_message="交易执行器未初始化"
                )
            
            return await self.trade_executor.execute_instruction(instruction)
        except Exception as e:
            logger.error(f"测试交易执行失败: {e}")
            return ExecutionResult(
                success=False,
                error_message=str(e)
            )

# 全局实例
tradingview_manager = None

def get_tradingview_manager() -> TradingViewManager:
    """获取TradingView管理器实例"""
    global tradingview_manager
    if tradingview_manager is None:
        tradingview_manager = TradingViewManager()
    return tradingview_manager

async def main():
    """主函数"""
    print("=" * 60)
    print("🤖 TradingView集成管理器")
    print("=" * 60)
    
    manager = get_tradingview_manager()
    
    try:
        # 初始化
        if not await manager.initialize():
            print("❌ 初始化失败")
            return
        
        # 启动Webhook服务器
        if not await manager.start_webhook_server():
            print("❌ 启动Webhook服务器失败")
            return
        
        print("✅ 系统启动成功!")
        print(f"🌐 Webhook地址: http://{manager.config['webhook_host']}:{manager.config['webhook_port']}")
        print("🛑 按 Ctrl+C 停止服务")
        
        # 保持运行
        while True:
            await asyncio.sleep(1)
            
    except KeyboardInterrupt:
        print("\n⏹️  用户停止服务")
    except Exception as e:
        logger.error(f"服务运行异常: {e}")
    finally:
        print("👋 服务已停止")

if __name__ == "__main__":
    asyncio.run(main())
