from fastapi import APIRouter, HTTPException, Depends
from typing import Dict, List, Optional, Any
from pydantic import BaseModel
from datetime import datetime
import asyncio

from core.strategy_trade.strategy_manager import StrategyManager
from core.strategy_trade.base_strategy import TradingSignal
from config.strategy_config import strategy_config_manager
from database.db import get_db_pool
from utils.logger import get_logger

logger = get_logger(__name__)

# 创建路由器
router = APIRouter(prefix="/api/strategy", tags=["策略交易"])

# 全局策略管理器实例
strategy_manager: Optional[StrategyManager] = None

# 请求模型
class StrategyConfig(BaseModel):
    strategy_type: str
    name: str
    config: Dict[str, Any]

class StrategyUpdate(BaseModel):
    config: Dict[str, Any]

class SignalResponse(BaseModel):
    strategy_name: str
    symbol: str
    action: str
    price: float
    quantity: float
    confidence: float
    timestamp: datetime
    metadata: Optional[Dict[str, Any]] = None

# 依赖注入
async def get_strategy_manager():
    global strategy_manager
    if strategy_manager is None:
        db_pool = await get_db_pool()
        strategy_manager = StrategyManager(db_pool)
    return strategy_manager

@router.post("/create")
async def create_strategy(
    strategy_config: StrategyConfig,
    manager: StrategyManager = Depends(get_strategy_manager)
):
    """创建新策略"""
    try:
        success = await manager.create_strategy(
            strategy_config.strategy_type,
            strategy_config.name,
            strategy_config.config
        )
        
        if success:
            return {
                "success": True,
                "message": f"策略 {strategy_config.name} 创建成功",
                "strategy_name": strategy_config.name
            }
        else:
            raise HTTPException(status_code=400, detail="策略创建失败")
            
    except Exception as e:
        logger.error(f"创建策略失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/start/{strategy_name}")
async def start_strategy(
    strategy_name: str,
    manager: StrategyManager = Depends(get_strategy_manager)
):
    """启动策略"""
    try:
        success = await manager.start_strategy(strategy_name)
        
        if success:
            return {
                "success": True,
                "message": f"策略 {strategy_name} 已启动"
            }
        else:
            raise HTTPException(status_code=404, detail="策略不存在")
            
    except Exception as e:
        logger.error(f"启动策略失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/stop/{strategy_name}")
async def stop_strategy(
    strategy_name: str,
    manager: StrategyManager = Depends(get_strategy_manager)
):
    """停止策略"""
    try:
        success = await manager.stop_strategy(strategy_name)
        
        if success:
            return {
                "success": True,
                "message": f"策略 {strategy_name} 已停止"
            }
        else:
            raise HTTPException(status_code=404, detail="策略不存在")
            
    except Exception as e:
        logger.error(f"停止策略失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/list")
async def list_strategies(
    manager: StrategyManager = Depends(get_strategy_manager)
):
    """获取策略列表"""
    try:
        strategies = await manager.get_strategies_list()
        return {
            "success": True,
            "strategies": strategies
        }
    except Exception as e:
        logger.error(f"获取策略列表失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/status/{strategy_name}")
async def get_strategy_status(
    strategy_name: str,
    manager: StrategyManager = Depends(get_strategy_manager)
):
    """获取策略状态"""
    try:
        status = manager.strategy_engine.get_strategy_performance(strategy_name)
        
        if status:
            return {
                "success": True,
                "status": status
            }
        else:
            raise HTTPException(status_code=404, detail="策略不存在")
            
    except Exception as e:
        logger.error(f"获取策略状态失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.put("/config/{strategy_name}")
async def update_strategy_config(
    strategy_name: str,
    config_update: StrategyUpdate,
    manager: StrategyManager = Depends(get_strategy_manager)
):
    """更新策略配置"""
    try:
        await manager.strategy_engine.update_strategy_config(
            strategy_name, 
            config_update.config
        )
        
        return {
            "success": True,
            "message": f"策略 {strategy_name} 配置已更新"
        }
        
    except Exception as e:
        logger.error(f"更新策略配置失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/engine/start")
async def start_engine(
    manager: StrategyManager = Depends(get_strategy_manager)
):
    """启动策略引擎"""
    try:
        await manager.start_engine()
        return {
            "success": True,
            "message": "策略引擎已启动"
        }
    except Exception as e:
        logger.error(f"启动策略引擎失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/engine/stop")
async def stop_engine(
    manager: StrategyManager = Depends(get_strategy_manager)
):
    """停止策略引擎"""
    try:
        await manager.stop_engine()
        return {
            "success": True,
            "message": "策略引擎已停止"
        }
    except Exception as e:
        logger.error(f"停止策略引擎失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/engine/status")
async def get_engine_status(
    manager: StrategyManager = Depends(get_strategy_manager)
):
    """获取策略引擎状态"""
    try:
        is_running = manager.strategy_engine.is_running
        strategies_count = len(manager.strategy_engine.strategies)
        
        return {
            "success": True,
            "engine_status": {
                "is_running": is_running,
                "strategies_count": strategies_count,
                "update_interval": manager.strategy_engine.update_interval
            }
        }
    except Exception as e:
        logger.error(f"获取引擎状态失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/signals/{strategy_name}")
async def get_strategy_signals(
    strategy_name: str,
    limit: int = 50,
    manager: StrategyManager = Depends(get_strategy_manager)
):
    """获取策略信号历史"""
    try:
        # 这里可以从数据库获取信号历史
        # 暂时返回空列表，实际实现需要查询数据库
        return {
            "success": True,
            "signals": [],
            "message": "信号历史功能待实现"
        }
    except Exception as e:
        logger.error(f"获取策略信号失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/available")
async def get_available_strategies():
    """获取可用的策略类型"""
    try:
        available_strategies = {
            "MA_Cross_Strategy": {
                "name": "移动平均交叉策略",
                "description": "基于短期和长期移动平均线交叉的交易策略",
                "parameters": {
                    "short_period": "短期均线周期（默认10）",
                    "long_period": "长期均线周期（默认20）",
                    "symbol": "交易对符号"
                }
            },
            "RSI_Strategy": {
                "name": "RSI策略",
                "description": "基于相对强弱指数的超买超卖策略",
                "parameters": {
                    "rsi_period": "RSI计算周期（默认14）",
                    "oversold_level": "超卖阈值（默认30）",
                    "overbought_level": "超买阈值（默认70）",
                    "symbol": "交易对符号"
                }
            },
            "Bollinger_Strategy": {
                "name": "布林带策略",
                "description": "基于布林带的价格突破策略",
                "parameters": {
                    "period": "布林带计算周期（默认20）",
                    "std_dev": "标准差倍数（默认2）",
                    "symbol": "交易对符号"
                }
            }
        }
        
        return {
            "success": True,
            "available_strategies": available_strategies
        }
    except Exception as e:
        logger.error(f"获取可用策略失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))