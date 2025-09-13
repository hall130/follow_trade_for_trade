"""
策略交易监控和报告系统
提供实时监控、告警、性能分析和报告生成功能
"""

import asyncio
import json
import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Any, Callable
from datetime import datetime, timedelta, date
from dataclasses import dataclass, asdict
from enum import Enum
import smtplib
from email.mime import text
from email.mime import multipart

from .strategy_db import StrategyDB
from .base_strategy import BaseStrategy
from utils.logger import get_logger

logger = get_logger(__name__)

class AlertLevel(Enum):
    """告警级别"""
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"

@dataclass
class Alert:
    """告警信息"""
    id: str
    level: AlertLevel
    title: str
    message: str
    strategy_name: Optional[str] = None
    timestamp: datetime = None
    is_resolved: bool = False
    resolved_at: Optional[datetime] = None
    metadata: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now()
        if self.metadata is None:
            self.metadata = {}

class StrategyMonitor:
    """策略监控器"""
    
    def __init__(self, db: StrategyDB = None):
        self.db = db or StrategyDB()
        self.strategies: Dict[str, BaseStrategy] = {}
        self.alerts: List[Alert] = []
        self.metrics_history: Dict[str, List[Dict]] = {}
        self.alert_handlers: List[Callable] = []
        
        # 监控配置
        self.monitoring_interval = 30  # 秒
        self.is_monitoring = False
        self._monitor_task = None
        
        # 告警规则
        self.alert_rules = {
            'max_drawdown': 0.15,        # 最大回撤15%
            'consecutive_losses': 5,      # 连续亏损5次
            'daily_loss_pct': 0.05,      # 日亏损5%
            'win_rate_threshold': 0.3,    # 胜率低于30%
            'profit_factor_threshold': 0.8,  # 盈亏比低于0.8
            'position_size_warning': 0.5,   # 单个持仓超过50%
            'trade_frequency_warning': 100   # 日交易次数超过100
        }
        
        # 性能基准
        self.performance_benchmarks = {
            'good_win_rate': 0.6,
            'good_profit_factor': 1.5,
            'good_sharpe_ratio': 1.0,
            'acceptable_drawdown': 0.1
        }
    
    def add_strategy(self, strategy: BaseStrategy):
        """添加监控策略"""
        self.strategies[strategy.name] = strategy
        self.metrics_history[strategy.name] = []
        logger.info(f"开始监控策略: {strategy.name}")
    
    def remove_strategy(self, strategy_name: str):
        """移除监控策略"""
        if strategy_name in self.strategies:
            del self.strategies[strategy_name]
            if strategy_name in self.metrics_history:
                del self.metrics_history[strategy_name]
            logger.info(f"停止监控策略: {strategy_name}")
    
    async def start_monitoring(self):
        """开始监控"""
        if self.is_monitoring:
            logger.warning("监控已在运行")
            return
        
        self.is_monitoring = True
        self._monitor_task = asyncio.create_task(self._monitoring_loop())
        logger.info("策略监控已启动")
    
    async def stop_monitoring(self):
        """停止监控"""
        if not self.is_monitoring:
            return
        
        self.is_monitoring = False
        if self._monitor_task:
            self._monitor_task.cancel()
            try:
                await self._monitor_task
            except asyncio.CancelledError:
                pass
        
        logger.info("策略监控已停止")
    
    async def _monitoring_loop(self):
        """监控主循环"""
        while self.is_monitoring:
            try:
                await self._collect_metrics()
                await self._check_alerts()
                await self._update_performance_analytics()
                await asyncio.sleep(self.monitoring_interval)
            except Exception as e:
                logger.error(f"监控循环错误: {e}")
                await asyncio.sleep(5)
    
    async def _collect_metrics(self):
        """收集策略指标"""
        current_time = datetime.now()
        
        for strategy_name, strategy in self.strategies.items():
            try:
                # 获取策略性能数据
                performance = strategy.get_performance_summary()
                
                # 添加时间戳和额外指标
                metrics = {
                    'timestamp': current_time.isoformat(),
                    'strategy_name': strategy_name,
                    'is_active': strategy.is_active,
                    **performance,
                    'positions_count': len(strategy.positions),
                    'current_positions': strategy.get_current_positions(),
                    'risk_metrics': self._calculate_risk_metrics(strategy)
                }
                
                # 保存到历史记录
                self.metrics_history[strategy_name].append(metrics)
                
                # 保持最近1000条记录
                if len(self.metrics_history[strategy_name]) > 1000:
                    self.metrics_history[strategy_name] = self.metrics_history[strategy_name][-1000:]
                
            except Exception as e:
                logger.error(f"收集策略指标失败 {strategy_name}: {e}")
    
    def _calculate_risk_metrics(self, strategy: BaseStrategy) -> Dict[str, Any]:
        """计算风险指标"""
        try:
            risk_metrics = {}
            
            # 持仓集中度
            if strategy.positions:
                total_value = sum(pos.quantity * pos.current_price for pos in strategy.positions.values())
                max_position = max(pos.quantity * pos.current_price for pos in strategy.positions.values())
                risk_metrics['position_concentration'] = max_position / total_value if total_value > 0 else 0
            else:
                risk_metrics['position_concentration'] = 0
            
            # 计算VaR (简化版)
            if len(strategy.trade_history) >= 10:
                pnl_list = [trade.get('pnl', 0) for trade in strategy.trade_history[-30:]]
                if pnl_list:
                    risk_metrics['var_95'] = np.percentile(pnl_list, 5)
                    risk_metrics['var_99'] = np.percentile(pnl_list, 1)
            
            # 波动率
            if strategy_name := strategy.name in self.metrics_history:
                recent_pnl = [m.get('total_pnl', 0) for m in self.metrics_history[strategy.name][-20:]]
                if len(recent_pnl) > 1:
                    returns = np.diff(recent_pnl)
                    risk_metrics['volatility'] = np.std(returns) if len(returns) > 0 else 0
            
            return risk_metrics
            
        except Exception as e:
            logger.error(f"计算风险指标失败: {e}")
            return {}
    
    async def _check_alerts(self):
        """检查告警条件"""
        for strategy_name, strategy in self.strategies.items():
            try:
                await self._check_strategy_alerts(strategy)
            except Exception as e:
                logger.error(f"检查策略告警失败 {strategy_name}: {e}")
    
    async def _check_strategy_alerts(self, strategy: BaseStrategy):
        """检查单个策略的告警"""
        performance = strategy.get_performance_summary()
        
        # 检查最大回撤
        if performance['max_drawdown'] < -self.alert_rules['max_drawdown']:
            await self._create_alert(
                AlertLevel.ERROR,
                f"策略 {strategy.name} 最大回撤过大",
                f"当前回撤: {performance['max_drawdown']:.2%}, 阈值: {self.alert_rules['max_drawdown']:.2%}",
                strategy.name
            )
        
        # 检查连续亏损
        if performance['current_consecutive_losses'] >= self.alert_rules['consecutive_losses']:
            await self._create_alert(
                AlertLevel.WARNING,
                f"策略 {strategy.name} 连续亏损",
                f"连续亏损次数: {performance['current_consecutive_losses']}, 阈值: {self.alert_rules['consecutive_losses']}",
                strategy.name
            )
        
        # 检查胜率
        if (performance['total_trades'] > 10 and 
            performance['win_rate'] < self.alert_rules['win_rate_threshold']):
            await self._create_alert(
                AlertLevel.WARNING,
                f"策略 {strategy.name} 胜率过低",
                f"当前胜率: {performance['win_rate']:.2%}, 阈值: {self.alert_rules['win_rate_threshold']:.2%}",
                strategy.name
            )
        
        # 检查盈亏比
        if (performance['total_trades'] > 10 and 
            performance['profit_factor'] < self.alert_rules['profit_factor_threshold']):
            await self._create_alert(
                AlertLevel.WARNING,
                f"策略 {strategy.name} 盈亏比过低",
                f"当前盈亏比: {performance['profit_factor']:.2f}, 阈值: {self.alert_rules['profit_factor_threshold']:.2f}",
                strategy.name
            )
        
        # 检查持仓风险
        for symbol, position in strategy.positions.items():
            position_risk = abs(position.unrealized_pnl) / (position.entry_price * position.quantity)
            if position_risk > self.alert_rules['position_size_warning']:
                await self._create_alert(
                    AlertLevel.INFO,
                    f"策略 {strategy.name} 持仓风险较高",
                    f"持仓 {symbol} 风险: {position_risk:.2%}",
                    strategy.name
                )
    
    async def _create_alert(self, level: AlertLevel, title: str, message: str, 
                          strategy_name: str = None, metadata: Dict[str, Any] = None):
        """创建告警"""
        alert_id = f"{datetime.now().timestamp()}_{level.value}_{strategy_name or 'system'}"
        
        alert = Alert(
            id=alert_id,
            level=level,
            title=title,
            message=message,
            strategy_name=strategy_name,
            metadata=metadata or {}
        )
        
        self.alerts.append(alert)
        
        # 保持最近500个告警
        if len(self.alerts) > 500:
            self.alerts = self.alerts[-500:]
        
        logger.warning(f"[{level.value}] {title}: {message}")
        
        # 通知告警处理器
        await self._notify_alert_handlers(alert)
    
    async def _notify_alert_handlers(self, alert: Alert):
        """通知告警处理器"""
        for handler in self.alert_handlers:
            try:
                if asyncio.iscoroutinefunction(handler):
                    await handler(alert)
                else:
                    handler(alert)
            except Exception as e:
                logger.error(f"告警处理器错误: {e}")
    
    def add_alert_handler(self, handler: Callable):
        """添加告警处理器"""
        self.alert_handlers.append(handler)
    
    async def _update_performance_analytics(self):
        """更新性能分析"""
        try:
            # 计算系统级性能指标
            system_metrics = await self._calculate_system_metrics()
            
            # 保存到数据库（如果需要）
            # await self.db.save_system_metrics(system_metrics)
            
        except Exception as e:
            logger.error(f"更新性能分析失败: {e}")
    
    async def _calculate_system_metrics(self) -> Dict[str, Any]:
        """计算系统级指标"""
        active_strategies = [s for s in self.strategies.values() if s.is_active]
        total_strategies = len(self.strategies)
        
        if not active_strategies:
            return {
                'active_strategies': 0,
                'total_strategies': total_strategies,
                'system_pnl': 0,
                'system_trades': 0,
                'average_win_rate': 0
            }
        
        # 聚合所有策略的性能
        total_pnl = sum(s.performance.get('total_pnl', 0) for s in active_strategies)
        total_trades = sum(s.performance.get('total_trades', 0) for s in active_strategies)
        total_wins = sum(s.performance.get('winning_trades', 0) for s in active_strategies)
        
        system_win_rate = total_wins / total_trades if total_trades > 0 else 0
        
        return {
            'active_strategies': len(active_strategies),
            'total_strategies': total_strategies,
            'system_pnl': total_pnl,
            'system_trades': total_trades,
            'system_win_rate': system_win_rate,
            'timestamp': datetime.now().isoformat()
        }
    
    def get_alerts(self, level: AlertLevel = None, strategy_name: str = None, 
                   hours: int = 24) -> List[Alert]:
        """获取告警列表"""
        filtered_alerts = self.alerts
        
        # 按时间过滤
        cutoff_time = datetime.now() - timedelta(hours=hours)
        filtered_alerts = [a for a in filtered_alerts if a.timestamp >= cutoff_time]
        
        # 按级别过滤
        if level:
            filtered_alerts = [a for a in filtered_alerts if a.level == level]
        
        # 按策略过滤
        if strategy_name:
            filtered_alerts = [a for a in filtered_alerts if a.strategy_name == strategy_name]
        
        return sorted(filtered_alerts, key=lambda x: x.timestamp, reverse=True)
    
    def get_strategy_metrics(self, strategy_name: str, hours: int = 24) -> List[Dict[str, Any]]:
        """获取策略指标历史"""
        if strategy_name not in self.metrics_history:
            return []
        
        cutoff_time = datetime.now() - timedelta(hours=hours)
        
        return [
            m for m in self.metrics_history[strategy_name]
            if datetime.fromisoformat(m['timestamp']) >= cutoff_time
        ]
    
    def get_performance_summary(self) -> Dict[str, Any]:
        """获取性能摘要"""
        active_strategies = len([s for s in self.strategies.values() if s.is_active])
        total_alerts = len(self.get_alerts(hours=24))
        critical_alerts = len(self.get_alerts(AlertLevel.CRITICAL, hours=24))
        
        # 计算平均性能
        if self.strategies:
            performances = [s.get_performance_summary() for s in self.strategies.values()]
            avg_win_rate = np.mean([p['win_rate'] for p in performances])
            avg_pnl = np.mean([p['total_pnl'] for p in performances])
            avg_trades = np.mean([p['total_trades'] for p in performances])
        else:
            avg_win_rate = avg_pnl = avg_trades = 0
        
        return {
            'active_strategies': active_strategies,
            'total_strategies': len(self.strategies),
            'total_alerts_24h': total_alerts,
            'critical_alerts_24h': critical_alerts,
            'average_win_rate': avg_win_rate,
            'average_pnl': avg_pnl,
            'average_trades': avg_trades,
            'monitoring_status': 'active' if self.is_monitoring else 'stopped',
            'last_update': datetime.now().isoformat()
        }

class ReportGenerator:
    """报告生成器"""
    
    def __init__(self, monitor: StrategyMonitor, db: StrategyDB = None):
        self.monitor = monitor
        self.db = db or StrategyDB()
    
    async def generate_daily_report(self, target_date: date = None) -> Dict[str, Any]:
        """生成日报"""
        if target_date is None:
            target_date = date.today()
        
        report = {
            'date': target_date.isoformat(),
            'summary': await self._generate_summary(target_date),
            'strategy_performance': await self._generate_strategy_performance(target_date),
            'alerts': await self._generate_alerts_summary(target_date),
            'risk_analysis': await self._generate_risk_analysis(target_date),
            'recommendations': await self._generate_recommendations(target_date)
        }
        
        return report
    
    async def _generate_summary(self, target_date: date) -> Dict[str, Any]:
        """生成总览"""
        try:
            # 从数据库获取当日数据
            daily_stats = {}
            
            for strategy_name in self.monitor.strategies.keys():
                # 获取策略实例ID
                strategy_instances = await self.db.get_strategy_instances(strategy_name=strategy_name)
                if strategy_instances:
                    instance_id = strategy_instances[0]['id']
                    
                    # 获取当日性能数据
                    performance_data = await self.db.get_performance_history(instance_id, days=1)
                    if performance_data:
                        daily_stats[strategy_name] = performance_data[0]
            
            # 计算总体统计
            total_pnl = sum(stats.get('total_pnl', 0) for stats in daily_stats.values())
            total_trades = sum(stats.get('total_trades', 0) for stats in daily_stats.values())
            
            return {
                'total_strategies': len(self.monitor.strategies),
                'active_strategies': len([s for s in self.monitor.strategies.values() if s.is_active]),
                'total_pnl': float(total_pnl),
                'total_trades': total_trades,
                'strategy_details': daily_stats
            }
            
        except Exception as e:
            logger.error(f"生成总览失败: {e}")
            return {}
    
    async def _generate_strategy_performance(self, target_date: date) -> Dict[str, Any]:
        """生成策略性能分析"""
        performance_data = {}
        
        for strategy_name, strategy in self.monitor.strategies.items():
            try:
                # 获取策略性能数据
                metrics = self.monitor.get_strategy_metrics(strategy_name, hours=24)
                
                if metrics:
                    latest_metrics = metrics[-1]
                    performance_data[strategy_name] = {
                        'win_rate': latest_metrics.get('win_rate', 0),
                        'total_pnl': latest_metrics.get('total_pnl', 0),
                        'total_trades': latest_metrics.get('total_trades', 0),
                        'max_drawdown': latest_metrics.get('max_drawdown', 0),
                        'sharpe_ratio': latest_metrics.get('sharpe_ratio', 0),
                        'profit_factor': latest_metrics.get('profit_factor', 0),
                        'status': 'active' if strategy.is_active else 'inactive',
                        'positions_count': len(strategy.positions),
                        'risk_score': self._calculate_risk_score(latest_metrics)
                    }
            except Exception as e:
                logger.error(f"生成策略性能分析失败 {strategy_name}: {e}")
        
        return performance_data
    
    def _calculate_risk_score(self, metrics: Dict[str, Any]) -> float:
        """计算风险评分 (0-100, 数值越高风险越大)"""
        try:
            score = 0
            
            # 回撤风险 (0-30分)
            max_drawdown = abs(metrics.get('max_drawdown', 0))
            if max_drawdown > 0.2:
                score += 30
            elif max_drawdown > 0.1:
                score += 20
            elif max_drawdown > 0.05:
                score += 10
            
            # 连续亏损风险 (0-25分)
            consecutive_losses = metrics.get('current_consecutive_losses', 0)
            if consecutive_losses >= 5:
                score += 25
            elif consecutive_losses >= 3:
                score += 15
            elif consecutive_losses >= 2:
                score += 5
            
            # 胜率风险 (0-20分)
            win_rate = metrics.get('win_rate', 0)
            if win_rate < 0.3:
                score += 20
            elif win_rate < 0.4:
                score += 10
            elif win_rate < 0.5:
                score += 5
            
            # 盈亏比风险 (0-25分)
            profit_factor = metrics.get('profit_factor', 0)
            if profit_factor < 0.8:
                score += 25
            elif profit_factor < 1.0:
                score += 15
            elif profit_factor < 1.2:
                score += 5
            
            return min(score, 100)
            
        except Exception as e:
            logger.error(f"计算风险评分失败: {e}")
            return 50  # 默认中等风险
    
    async def _generate_alerts_summary(self, target_date: date) -> Dict[str, Any]:
        """生成告警汇总"""
        try:
            # 获取当日告警
            start_time = datetime.combine(target_date, datetime.min.time())
            end_time = start_time + timedelta(days=1)
            
            daily_alerts = [
                alert for alert in self.monitor.alerts
                if start_time <= alert.timestamp < end_time
            ]
            
            # 按级别统计
            alert_counts = {level.value: 0 for level in AlertLevel}
            for alert in daily_alerts:
                alert_counts[alert.level.value] += 1
            
            # 按策略统计
            strategy_alerts = {}
            for alert in daily_alerts:
                if alert.strategy_name:
                    if alert.strategy_name not in strategy_alerts:
                        strategy_alerts[alert.strategy_name] = 0
                    strategy_alerts[alert.strategy_name] += 1
            
            return {
                'total_alerts': len(daily_alerts),
                'by_level': alert_counts,
                'by_strategy': strategy_alerts,
                'recent_alerts': [
                    {
                        'level': alert.level.value,
                        'title': alert.title,
                        'message': alert.message,
                        'strategy': alert.strategy_name,
                        'timestamp': alert.timestamp.isoformat()
                    }
                    for alert in daily_alerts[-10:]  # 最近10个告警
                ]
            }
            
        except Exception as e:
            logger.error(f"生成告警汇总失败: {e}")
            return {}
    
    async def _generate_risk_analysis(self, target_date: date) -> Dict[str, Any]:
        """生成风险分析"""
        try:
            risk_analysis = {
                'overall_risk_level': 'LOW',
                'risk_factors': [],
                'recommendations': []
            }
            
            # 分析各策略风险
            high_risk_strategies = []
            total_risk_score = 0
            
            for strategy_name, strategy in self.monitor.strategies.items():
                metrics = self.monitor.get_strategy_metrics(strategy_name, hours=24)
                if metrics:
                    latest_metrics = metrics[-1]
                    risk_score = self._calculate_risk_score(latest_metrics)
                    total_risk_score += risk_score
                    
                    if risk_score > 70:
                        high_risk_strategies.append({
                            'strategy': strategy_name,
                            'risk_score': risk_score,
                            'issues': self._identify_risk_issues(latest_metrics)
                        })
            
            # 确定总体风险等级
            avg_risk_score = total_risk_score / len(self.monitor.strategies) if self.monitor.strategies else 0
            
            if avg_risk_score > 70:
                risk_analysis['overall_risk_level'] = 'HIGH'
            elif avg_risk_score > 40:
                risk_analysis['overall_risk_level'] = 'MEDIUM'
            else:
                risk_analysis['overall_risk_level'] = 'LOW'
            
            risk_analysis['average_risk_score'] = avg_risk_score
            risk_analysis['high_risk_strategies'] = high_risk_strategies
            
            return risk_analysis
            
        except Exception as e:
            logger.error(f"生成风险分析失败: {e}")
            return {}
    
    def _identify_risk_issues(self, metrics: Dict[str, Any]) -> List[str]:
        """识别风险问题"""
        issues = []
        
        if metrics.get('max_drawdown', 0) < -0.15:
            issues.append("最大回撤过大")
        
        if metrics.get('current_consecutive_losses', 0) >= 5:
            issues.append("连续亏损过多")
        
        if metrics.get('win_rate', 0) < 0.3:
            issues.append("胜率过低")
        
        if metrics.get('profit_factor', 0) < 0.8:
            issues.append("盈亏比过低")
        
        return issues
    
    async def _generate_recommendations(self, target_date: date) -> List[str]:
        """生成建议"""
        recommendations = []
        
        try:
            # 基于告警生成建议
            critical_alerts = self.monitor.get_alerts(AlertLevel.CRITICAL, hours=24)
            if critical_alerts:
                recommendations.append("发现严重告警，建议立即检查策略运行状态")
            
            # 基于性能生成建议
            for strategy_name, strategy in self.monitor.strategies.items():
                performance = strategy.get_performance_summary()
                
                if performance['win_rate'] < 0.4 and performance['total_trades'] > 10:
                    recommendations.append(f"策略 {strategy_name} 胜率较低，建议优化信号质量")
                
                if performance['max_drawdown'] < -0.1:
                    recommendations.append(f"策略 {strategy_name} 回撤较大，建议加强风险控制")
                
                if performance['current_consecutive_losses'] >= 3:
                    recommendations.append(f"策略 {strategy_name} 连续亏损，建议暂停或调整参数")
            
            if not recommendations:
                recommendations.append("当前系统运行正常，继续保持监控")
            
            return recommendations
            
        except Exception as e:
            logger.error(f"生成建议失败: {e}")
            return ["报告生成过程中出现错误，请检查系统状态"]
    
    async def export_report_to_json(self, report: Dict[str, Any], filename: str = None) -> str:
        """导出报告为JSON文件"""
        if filename is None:
            filename = f"strategy_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        
        try:
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(report, f, ensure_ascii=False, indent=2, default=str)
            
            logger.info(f"报告已导出到: {filename}")
            return filename
            
        except Exception as e:
            logger.error(f"导出报告失败: {e}")
            raise
    
    async def export_report_to_html(self, report: Dict[str, Any], filename: str = None) -> str:
        """导出报告为HTML文件"""
        if filename is None:
            filename = f"strategy_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
        
        try:
            html_content = self._generate_html_report(report)
            
            with open(filename, 'w', encoding='utf-8') as f:
                f.write(html_content)
            
            logger.info(f"HTML报告已导出到: {filename}")
            return filename
            
        except Exception as e:
            logger.error(f"导出HTML报告失败: {e}")
            raise
    
    def _generate_html_report(self, report: Dict[str, Any]) -> str:
        """生成HTML报告内容"""
        return f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>策略交易日报 - {report['date']}</title>
            <meta charset="utf-8">
            <style>
                body {{ font-family: Arial, sans-serif; margin: 20px; }}
                .header {{ background-color: #f4f4f4; padding: 20px; border-radius: 5px; }}
                .section {{ margin: 20px 0; padding: 15px; border: 1px solid #ddd; border-radius: 5px; }}
                .alert-critical {{ color: red; }}
                .alert-error {{ color: orange; }}
                .alert-warning {{ color: gold; }}
                .alert-info {{ color: blue; }}
                table {{ width: 100%; border-collapse: collapse; }}
                th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; }}
                th {{ background-color: #f2f2f2; }}
            </style>
        </head>
        <body>
            <div class="header">
                <h1>策略交易日报</h1>
                <p>日期: {report['date']}</p>
                <p>生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
            </div>
            
            <div class="section">
                <h2>概览</h2>
                <p>总策略数: {report['summary'].get('total_strategies', 0)}</p>
                <p>活跃策略数: {report['summary'].get('active_strategies', 0)}</p>
                <p>总盈亏: {report['summary'].get('total_pnl', 0):.2f}</p>
                <p>总交易数: {report['summary'].get('total_trades', 0)}</p>
            </div>
            
            <div class="section">
                <h2>告警汇总</h2>
                <p>总告警数: {report['alerts'].get('total_alerts', 0)}</p>
                <p>严重告警: {report['alerts'].get('by_level', {}).get('CRITICAL', 0)}</p>
                <p>错误告警: {report['alerts'].get('by_level', {}).get('ERROR', 0)}</p>
                <p>警告告警: {report['alerts'].get('by_level', {}).get('WARNING', 0)}</p>
            </div>
            
            <div class="section">
                <h2>风险分析</h2>
                <p>整体风险等级: {report['risk_analysis'].get('overall_risk_level', 'UNKNOWN')}</p>
                <p>平均风险评分: {report['risk_analysis'].get('average_risk_score', 0):.1f}</p>
            </div>
            
            <div class="section">
                <h2>建议</h2>
                <ul>
                {
                    ''.join(f'<li>{rec}</li>' for rec in report['recommendations'])
                }
                </ul>
            </div>
        </body>
        </html>
        """

class AlertNotifier:
    """告警通知器"""
    
    def __init__(self, email_config: Dict[str, str] = None):
        self.email_config = email_config or {}
        self.notification_rules = {
            AlertLevel.CRITICAL: True,   # 严重告警总是通知
            AlertLevel.ERROR: True,      # 错误告警总是通知
            AlertLevel.WARNING: False,   # 警告告警可选通知
            AlertLevel.INFO: False       # 信息告警默认不通知
        }
    
    async def send_email_alert(self, alert: Alert):
        """发送邮件告警"""
        if not self.email_config:
            logger.warning("邮件配置未设置，无法发送告警邮件")
            return
        
        try:
            smtp_server = self.email_config.get('smtp_server')
            smtp_port = self.email_config.get('smtp_port', 587)
            username = self.email_config.get('username')
            password = self.email_config.get('password')
            to_emails = self.email_config.get('to_emails', [])
            
            if not all([smtp_server, username, password, to_emails]):
                logger.warning("邮件配置不完整，无法发送告警邮件")
                return
            
            # 创建邮件内容
            msg = multipart.MIMEMultipart()
            msg['From'] = username
            msg['To'] = ', '.join(to_emails)
            msg['Subject'] = f"[{alert.level.value}] {alert.title}"
            
            body = f"""
            告警时间: {alert.timestamp.strftime('%Y-%m-%d %H:%M:%S')}
            告警级别: {alert.level.value}
            策略名称: {alert.strategy_name or '系统'}
            告警标题: {alert.title}
            告警内容: {alert.message}
            
            请及时处理相关问题。
            
            ---
            策略交易监控系统
            """
            
            msg.attach(text.MIMEText(body, 'plain', 'utf-8'))
            
            # 发送邮件
            server = smtplib.SMTP(smtp_server, smtp_port)
            server.starttls()
            server.login(username, password)
            text = msg.as_string()
            server.sendmail(username, to_emails, text)
            server.quit()
            
            logger.info(f"告警邮件已发送: {alert.title}")
            
        except Exception as e:
            logger.error(f"发送告警邮件失败: {e}")
    
    async def handle_alert(self, alert: Alert):
        """处理告警"""
        # 检查是否需要通知
        if self.notification_rules.get(alert.level, False):
            await self.send_email_alert(alert)
        
        # 这里可以添加其他通知方式，如钉钉、微信等
        # await self.send_dingtalk_alert(alert)
        # await self.send_wechat_alert(alert) 