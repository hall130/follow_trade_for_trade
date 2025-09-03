"""
资产分析API接口
提供资产波动数据查询和分析功能
"""

from flask import Blueprint, request, jsonify
from datetime import datetime, timedelta
from typing import Dict, Any
import asyncio
from core.asset_analysis_service import get_asset_analysis_service
from utils.logger import logger

# 创建蓝图
asset_analysis_bp = Blueprint('asset_analysis', __name__, url_prefix='/api/v1/asset-analysis')


@asset_analysis_bp.route('/customer/<customer_uid>/overview', methods=['GET'])
async def get_customer_asset_overview(customer_uid: str):
    """获取客户资产概览
    
    Args:
        customer_uid: 客户UID
        
    Returns:
        客户资产概览数据
    """
    try:
        service = await get_asset_analysis_service()
        
        # 获取客户资产分析
        analysis = await service.analyze_customer_assets(customer_uid, None)
        
        if not analysis:
            return jsonify({
                'success': False,
                'message': '客户资产分析失败'
            }), 400
        
        # 获取资产趋势数据
        trend_data = await service.get_asset_trend_data(customer_uid, None, 30)
        
        # 构建响应数据
        response_data = {
            'customer_uid': customer_uid,
            'analysis_time': analysis.analysis_time.isoformat() if analysis.analysis_time else None,
            'total_assets': analysis.total_assets,
            'total_positions': analysis.total_positions,
            'risk_level': analysis.risk_level,
            'asset_distribution': analysis.asset_distribution,
            'position_summary': analysis.position_summary,
            'risk_metrics': analysis.risk_metrics,
            'trend_analysis': analysis.trend_analysis,
            'recommendations': analysis.recommendations,
            'trend_data': trend_data
        }
        
        return jsonify({
            'success': True,
            'data': response_data
        })
        
    except Exception as e:
        logger.error(f"获取客户资产概览失败: {e}")
        return jsonify({
            'success': False,
            'message': f'获取客户资产概览失败: {str(e)}'
        }), 500


@asset_analysis_bp.route('/customer/<customer_uid>/exchange/<exchange>/analysis', methods=['GET'])
async def get_customer_exchange_analysis(customer_uid: str, exchange: str):
    """获取客户在特定交易所的资产分析
    
    Args:
        customer_uid: 客户UID
        exchange: 交易所
        
    Returns:
        交易所资产分析数据
    """
    try:
        service = await get_asset_analysis_service()
        
        # 获取客户在特定交易所的资产分析
        analysis = await service.analyze_customer_assets(customer_uid, exchange)
        
        if not analysis:
            return jsonify({
                'success': False,
                'message': f'获取客户在{exchange}的资产分析失败'
            }), 400
        
        # 获取资产趋势数据
        trend_data = await service.get_asset_trend_data(customer_uid, exchange, 30)
        
        # 获取资产快照历史
        snapshots = await service.get_asset_snapshots(customer_uid, exchange, 7)
        
        response_data = {
            'customer_uid': customer_uid,
            'exchange': exchange,
            'analysis': analysis.to_dict(),
            'trend_data': trend_data,
            'recent_snapshots': [snapshot.to_dict() for snapshot in snapshots[:10]]
        }
        
        return jsonify({
            'success': True,
            'data': response_data
        })
        
    except Exception as e:
        logger.error(f"获取客户交易所资产分析失败: {e}")
        return jsonify({
            'success': False,
            'message': f'获取客户交易所资产分析失败: {str(e)}'
        }), 500


@asset_analysis_bp.route('/customer/<customer_uid>/trend', methods=['GET'])
async def get_customer_asset_trend(customer_uid: str):
    """获取客户资产趋势数据
    
    Args:
        customer_uid: 客户UID
        
    Query Parameters:
        days: 天数范围（默认30天）
        exchange: 交易所（可选）
        
    Returns:
        资产趋势数据
    """
    try:
        days = int(request.args.get('days', 30))
        exchange = request.args.get('exchange')
        
        if days <= 0 or days > 365:
            return jsonify({
                'success': False,
                'message': '天数范围必须在1-365之间'
            }), 400
        
        service = await get_asset_analysis_service()
        
        # 获取趋势数据
        trend_data = await service.get_asset_trend_data(customer_uid, exchange, days)
        
        return jsonify({
            'success': True,
            'data': {
                'customer_uid': customer_uid,
                'exchange': exchange,
                'days': days,
                'trend_data': trend_data,
                'summary': {
                    'total_points': len(trend_data),
                    'start_date': trend_data[0]['date'] if trend_data else None,
                    'end_date': trend_data[-1]['date'] if trend_data else None,
                    'initial_value': trend_data[0]['total_value'] if trend_data else 0,
                    'final_value': trend_data[-1]['total_value'] if trend_data else 0
                }
            }
        })
        
    except Exception as e:
        logger.error(f"获取客户资产趋势失败: {e}")
        return jsonify({
            'success': False,
            'message': f'获取客户资产趋势失败: {str(e)}'
        }), 500


@asset_analysis_bp.route('/exchange/<exchange>/summary', methods=['GET'])
async def get_exchange_asset_summary(exchange: str):
    """获取交易所资产汇总
    
    Args:
        exchange: 交易所
        
    Returns:
        交易所资产汇总数据
    """
    try:
        service = await get_asset_analysis_service()
        
        # 获取交易所资产汇总
        summary = await service.get_exchange_asset_summary(exchange)
        
        if not summary:
            return jsonify({
                'success': False,
                'message': f'获取交易所{exchange}资产汇总失败'
            }), 400
        
        return jsonify({
            'success': True,
            'data': summary.to_dict()
        })
        
    except Exception as e:
        logger.error(f"获取交易所资产汇总失败: {e}")
        return jsonify({
            'success': False,
            'message': f'获取交易所资产汇总失败: {str(e)}'
        }), 500


@asset_analysis_bp.route('/customer/<customer_uid>/snapshot', methods=['POST'])
async def create_asset_snapshot(customer_uid: str):
    """手动创建资产快照
    
    Args:
        customer_uid: 客户UID
        
    Returns:
        创建结果
    """
    try:
        service = await get_asset_analysis_service()
        
        # 获取客户信息
        customer = await service._get_customer_info(customer_uid)
        if not customer:
            return jsonify({
                'success': False,
                'message': '客户不存在'
            }), 404
        
        exchange = customer.get('exchange')
        if not exchange:
            return jsonify({
                'success': False,
                'message': '客户未配置交易所'
            }), 400
        
        # 创建资产快照
        snapshot = await service._create_customer_snapshot(customer)
        
        if snapshot:
            return jsonify({
                'success': True,
                'message': '资产快照创建成功',
                'data': {
                    'customer_uid': customer_uid,
                    'exchange': exchange,
                    'timestamp': datetime.now().isoformat()
                }
            })
        else:
            return jsonify({
                'success': False,
                'message': '资产快照创建失败'
            }), 500
        
    except Exception as e:
        logger.error(f"创建资产快照失败: {e}")
        return jsonify({
            'success': False,
            'message': f'创建资产快照失败: {str(e)}'
        }), 500


@asset_analysis_bp.route('/customer/<customer_uid>/snapshots', methods=['GET'])
async def get_customer_snapshots(customer_uid: str):
    """获取客户资产快照历史
    
    Args:
        customer_uid: 客户UID
        
    Query Parameters:
        exchange: 交易所（可选）
        days: 天数范围（默认7天）
        limit: 返回数量限制（默认50）
        
    Returns:
        资产快照历史数据
    """
    try:
        exchange = request.args.get('exchange')
        days = int(request.args.get('days', 7))
        limit = int(request.args.get('limit', 50))
        
        if days <= 0 or days > 365:
            return jsonify({
                'success': False,
                'message': '天数范围必须在1-365之间'
            }), 400
        
        if limit <= 0 or limit > 1000:
            return jsonify({
                'success': False,
                'message': '数量限制必须在1-1000之间'
            }), 400
        
        service = await get_asset_analysis_service()
        
        # 获取资产快照
        snapshots = await service.get_asset_snapshots(customer_uid, exchange, days)
        
        # 限制返回数量
        snapshots = snapshots[:limit]
        
        return jsonify({
            'success': True,
            'data': {
                'customer_uid': customer_uid,
                'exchange': exchange,
                'days': days,
                'total_snapshots': len(snapshots),
                'snapshots': [snapshot.to_dict() for snapshot in snapshots]
            }
        })
        
    except Exception as e:
        logger.error(f"获取客户资产快照失败: {e}")
        return jsonify({
            'success': False,
            'message': f'获取客户资产快照失败: {str(e)}'
        }), 500


@asset_analysis_bp.route('/dashboard/overview', methods=['GET'])
async def get_dashboard_asset_overview():
    """获取仪表板资产概览
    
    Returns:
        所有客户的资产概览数据
    """
    try:
        service = await get_asset_analysis_service()
        
        # 获取所有客户
        customers = await service._get_all_customers()
        
        overview_data = []
        for customer in customers:
            try:
                # 获取客户资产分析
                analysis = await service.analyze_customer_assets(
                    customer['customer_uid'], 
                    customer.get('exchange')
                )
                
                if analysis:
                    overview_data.append({
                        'customer_uid': customer['customer_uid'],
                        'name': customer.get('name', ''),
                        'exchange': customer.get('exchange', ''),
                        'is_demo': customer.get('is_demo', False),
                        'enabled': customer.get('enabled', False),
                        'total_assets': analysis.total_assets,
                        'total_positions': analysis.total_positions,
                        'risk_level': analysis.risk_level,
                        'last_analysis': analysis.analysis_time.isoformat() if analysis.analysis_time else None
                    })
                else:
                    # 如果没有分析数据，使用基础信息
                    overview_data.append({
                        'customer_uid': customer['customer_uid'],
                        'name': customer.get('name', ''),
                        'exchange': customer.get('exchange', ''),
                        'is_demo': customer.get('is_demo', False),
                        'enabled': customer.get('enabled', False),
                        'total_assets': customer.get('current_asset', 0),
                        'total_positions': 0,
                        'risk_level': 'unknown',
                        'last_analysis': None
                    })
                    
            except Exception as e:
                logger.error(f"获取客户 {customer['customer_uid']} 资产概览失败: {e}")
                continue
        
        # 计算汇总统计
        total_customers = len(overview_data)
        total_assets = sum(item['total_assets'] for item in overview_data)
        avg_assets = total_assets / total_customers if total_customers > 0 else 0
        
        # 按交易所分组统计
        exchange_stats = {}
        for item in overview_data:
            exchange = item['exchange']
            if exchange not in exchange_stats:
                exchange_stats[exchange] = {
                    'customers': 0,
                    'total_assets': 0,
                    'avg_assets': 0
                }
            
            exchange_stats[exchange]['customers'] += 1
            exchange_stats[exchange]['total_assets'] += item['total_assets']
        
        # 计算每个交易所的平均资产
        for exchange in exchange_stats:
            customers_count = exchange_stats[exchange]['customers']
            if customers_count > 0:
                exchange_stats[exchange]['avg_assets'] = exchange_stats[exchange]['total_assets'] / customers_count
        
        return jsonify({
            'success': True,
            'data': {
                'summary': {
                    'total_customers': total_customers,
                    'total_assets': round(total_assets, 2),
                    'avg_assets_per_customer': round(avg_assets, 2)
                },
                'exchange_stats': exchange_stats,
                'customers': overview_data
            }
        })
        
    except Exception as e:
        logger.error(f"获取仪表板资产概览失败: {e}")
        return jsonify({
            'success': False,
            'message': f'获取仪表板资产概览失败: {str(e)}'
        }), 500


@asset_analysis_bp.route('/health', methods=['GET'])
async def get_asset_analysis_health():
    """获取资产分析服务健康状态
    
    Returns:
        服务健康状态
    """
    try:
        service = await get_asset_analysis_service()
        
        # 检查数据库连接
        db_pool = await service.get_db_pool()
        if not db_pool:
            return jsonify({
                'success': False,
                'message': '数据库连接失败',
                'status': 'unhealthy'
            }), 500
        
        return jsonify({
            'success': True,
            'message': '资产分析服务运行正常',
            'status': 'healthy',
            'timestamp': datetime.now().isoformat()
        })
        
    except Exception as e:
        logger.error(f"获取资产分析服务健康状态失败: {e}")
        return jsonify({
            'success': False,
            'message': f'获取服务健康状态失败: {str(e)}',
            'status': 'unhealthy'
        }), 500


# 注册蓝图到主应用
def register_asset_analysis_blueprint(app):
    """注册资产分析蓝图到Flask应用"""
    app.register_blueprint(asset_analysis_bp)
    logger.info("资产分析API蓝图已注册") 