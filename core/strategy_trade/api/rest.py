"""
策略交易REST API
提供策略管理的RESTful接口
"""

from typing import Dict, List, Any, Optional
from datetime import datetime
import json
from flask import Flask, request, jsonify
from flask_cors import CORS

from ..core.manager import StrategyManager
from ..core.backtest import BacktestConfig, BacktestResult
from ..strategies import *
from utils.logger import get_logger

logger = get_logger(__name__)

class StrategyTradeAPI:
    """策略交易REST API"""
    
    def __init__(self, strategy_manager: Optional[StrategyManager] = None):
        self.app = Flask(__name__)
        CORS(self.app)
        
        self.strategy_manager = strategy_manager or StrategyManager()
        self._register_routes()
        
        logger.info("策略交易REST API初始化完成")
    
    def _register_routes(self) -> None:
        """注册路由"""
        
        @self.app.route('/api/v1/strategies', methods=['GET'])
        def get_strategies():
            """获取所有策略"""
            try:
                strategies = self.strategy_manager.get_all_strategies()
                return jsonify({
                    'success': True,
                    'data': [strategy.to_dict() for strategy in strategies],
                    'message': f'成功获取 {len(strategies)} 个策略'
                })
            except Exception as e:
                logger.error(f"获取策略列表失败: {e}")
                return jsonify({
                    'success': False,
                    'message': f'获取策略列表失败: {str(e)}'
                }), 500
        
        @self.app.route('/api/v1/strategies', methods=['POST'])
        def create_strategy():
            """创建策略"""
            try:
                data = request.get_json()
                strategy_type = data.get('strategy_type')
                name = data.get('name')
                symbol = data.get('symbol')
                config = data.get('config', {})
                
                if not all([strategy_type, name, symbol]):
                    return jsonify({
                        'success': False,
                        'message': '缺少必需参数'
                    }), 400
                
                strategy_id = self.strategy_manager.create_strategy(
                    strategy_type, name, symbol, config
                )
                
                if strategy_id:
                    return jsonify({
                        'success': True,
                        'data': {'strategy_id': strategy_id},
                        'message': '策略创建成功'
                    })
                else:
                    return jsonify({
                        'success': False,
                        'message': '策略创建失败'
                    }), 500
                    
            except Exception as e:
                logger.error(f"创建策略失败: {e}")
                return jsonify({
                    'success': False,
                    'message': f'创建策略失败: {str(e)}'
                }), 500
        
        @self.app.route('/api/v1/strategies/<strategy_id>', methods=['GET'])
        def get_strategy(strategy_id: str):
            """获取策略信息"""
            try:
                strategy = self.strategy_manager.get_strategy(strategy_id)
                if strategy:
                    return jsonify({
                        'success': True,
                        'data': strategy.to_dict(),
                        'message': '获取策略信息成功'
                    })
                else:
                    return jsonify({
                        'success': False,
                        'message': '策略不存在'
                    }), 404
                    
            except Exception as e:
                logger.error(f"获取策略信息失败: {e}")
                return jsonify({
                    'success': False,
                    'message': f'获取策略信息失败: {str(e)}'
                }), 500
        
        @self.app.route('/api/v1/strategies/<strategy_id>/start', methods=['POST'])
        def start_strategy(strategy_id: str):
            """启动策略"""
            try:
                success = self.strategy_manager.start_strategy(strategy_id)
                if success:
                    return jsonify({
                        'success': True,
                        'message': '策略启动成功'
                    })
                else:
                    return jsonify({
                        'success': False,
                        'message': '策略启动失败'
                    }), 500
                    
            except Exception as e:
                logger.error(f"启动策略失败: {e}")
                return jsonify({
                    'success': False,
                    'message': f'启动策略失败: {str(e)}'
                }), 500
        
        @self.app.route('/api/v1/strategies/<strategy_id>/stop', methods=['POST'])
        def stop_strategy(strategy_id: str):
            """停止策略"""
            try:
                success = self.strategy_manager.stop_strategy(strategy_id)
                if success:
                    return jsonify({
                        'success': True,
                        'message': '策略停止成功'
                    })
                else:
                    return jsonify({
                        'success': False,
                        'message': '策略停止失败'
                    }), 500
                    
            except Exception as e:
                logger.error(f"停止策略失败: {e}")
                return jsonify({
                    'success': False,
                    'message': f'停止策略失败: {str(e)}'
                }), 500
        
        @self.app.route('/api/v1/strategies/<strategy_id>', methods=['DELETE'])
        def delete_strategy(strategy_id: str):
            """删除策略"""
            try:
                success = self.strategy_manager.remove_strategy(strategy_id)
                if success:
                    return jsonify({
                        'success': True,
                        'message': '策略删除成功'
                    })
                else:
                    return jsonify({
                        'success': False,
                        'message': '策略删除失败'
                    }), 500
                    
            except Exception as e:
                logger.error(f"删除策略失败: {e}")
                return jsonify({
                    'success': False,
                    'message': f'删除策略失败: {str(e)}'
                }), 500
        
        @self.app.route('/api/v1/strategies/<strategy_id>/backtest', methods=['POST'])
        def run_backtest(strategy_id: str):
            """运行回测"""
            try:
                data = request.get_json()
                
                # 创建回测配置
                config = BacktestConfig(
                    initial_capital=data.get('initial_capital', 100000.0),
                    commission_rate=data.get('commission_rate', 0.0003),
                    slippage_rate=data.get('slippage_rate', 0.001),
                    start_date=datetime.fromisoformat(data.get('start_date', '2023-01-01')),
                    end_date=datetime.fromisoformat(data.get('end_date', '2023-12-31'))
                )
                
                # 这里需要传入历史数据，实际实现中应该从数据库或文件加载
                # 为了演示，这里使用空数据
                import pandas as pd
                data_df = pd.DataFrame()
                
                result = self.strategy_manager.run_backtest(strategy_id, data_df, config)
                
                if result:
                    return jsonify({
                        'success': True,
                        'data': result.to_dict(),
                        'message': '回测完成'
                    })
                else:
                    return jsonify({
                        'success': False,
                        'message': '回测失败'
                    }), 500
                    
            except Exception as e:
                logger.error(f"运行回测失败: {e}")
                return jsonify({
                    'success': False,
                    'message': f'运行回测失败: {str(e)}'
                }), 500
        
        @self.app.route('/api/v1/strategy-types', methods=['GET'])
        def get_strategy_types():
            """获取策略类型列表"""
            try:
                strategy_types = self.strategy_manager.get_strategy_types()
                return jsonify({
                    'success': True,
                    'data': strategy_types,
                    'message': f'成功获取 {len(strategy_types)} 个策略类型'
                })
            except Exception as e:
                logger.error(f"获取策略类型失败: {e}")
                return jsonify({
                    'success': False,
                    'message': f'获取策略类型失败: {str(e)}'
                }), 500
        
        @self.app.route('/api/v1/health', methods=['GET'])
        def health_check():
            """健康检查"""
            return jsonify({
                'success': True,
                'message': '策略交易API运行正常',
                'timestamp': datetime.now().isoformat()
            })
    
    def run(self, host: str = '0.0.0.0', port: int = 5000, debug: bool = False) -> None:
        """运行API服务器"""
        logger.info(f"启动策略交易API服务器: {host}:{port}")
        self.app.run(host=host, port=port, debug=debug)
