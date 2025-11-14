"""
刷单进程管理器
管理多个刷单进程的启动、停止和监控
"""
import sys
import os
import random
import signal
import subprocess
import time
from pathlib import Path
from typing import Dict, List, Any, Set, Optional
from multiprocessing import Process
from utils.logger import logger

try:
    import psutil
    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False
    logger.warning("psutil未安装，将使用备用进程管理方法")


class MarketMakerProcessManager:
    """刷单进程管理器"""
    
    def __init__(self, config_file: Optional[str] = None):
        """
        初始化进程管理器
        
        Args:
            config_file: 配置文件路径
        """
        from .config_manager import MarketMakerConfigManager
        
        self.config_manager = MarketMakerConfigManager(config_file)
        self.processes: Dict[str, subprocess.Popen] = {}  # key: account_name_symbol
        self.should_stop = False
        
        # 获取项目根目录
        self.root_dir = Path(__file__).parent.parent.parent.resolve()
        
        # 日志目录
        self.log_dir = self.root_dir / "logs" / "market_maker"
        self.log_dir.mkdir(parents=True, exist_ok=True)
    
    def get_account_key(self, name: str, symbol: str) -> str:
        """生成账号唯一标识"""
        return f"{name}_{symbol}"
    
    def _build_command(self, account: Dict[str, Any], symbol: str) -> List[str]:
        """
        构建启动命令
        
        Args:
            account: 账号配置
            symbol: 交易对
            
        Returns:
            命令列表
        """
        # 使用Python运行刷单脚本
        script_path = self.root_dir / "core" / "market_maker" / "run_market_maker.py"
        
        cmd = [sys.executable, str(script_path)]
        
        # 添加参数
        cmd.extend(["--account-name", account.get("name", "unknown")])
        cmd.extend(["--symbol", symbol])
        cmd.extend(["--exchange", account.get("exchange", "backpack")])
        cmd.extend(["--market-type", account.get("market_type", "spot")])
        
        # 添加策略参数
        params = account.get("params", {})
        if "spread" in params:
            cmd.extend(["--spread", str(params["spread"])])
        if "quantity" in params:
            cmd.extend(["--quantity", str(params["quantity"])])
        if "max_orders" in params:
            cmd.extend(["--max-orders", str(params["max_orders"])])
        if "interval" in params:
            cmd.extend(["--interval", str(params["interval"])])
        if "duration" in params:
            cmd.extend(["--duration", str(params["duration"])])
        if "strategy" in params:
            cmd.extend(["--strategy", str(params["strategy"])])
        
        # 标准策略的仓位管理参数
        if "target_position" in params:
            cmd.extend(["--target-position", str(params["target_position"])])
        if "max_position" in params:
            cmd.extend(["--max-position", str(params["max_position"])])
        if "position_threshold" in params:
            cmd.extend(["--position-threshold", str(params["position_threshold"])])
        if "inventory_skew" in params:
            cmd.extend(["--inventory-skew", str(params["inventory_skew"])])
        if "stop_loss" in params:
            cmd.extend(["--stop-loss", str(params["stop_loss"])])
        if "take_profit" in params:
            cmd.extend(["--take-profit", str(params["take_profit"])])
        
        # Avellaneda-Stoikov策略参数
        if "risk_factor" in params:
            cmd.extend(["--risk-factor", str(params["risk_factor"])])
        if "inventory_target" in params:
            cmd.extend(["--inventory-target", str(params["inventory_target"])])
        if "order_amount_shape_factor" in params:
            cmd.extend(["--order-amount-shape-factor", str(params["order_amount_shape_factor"])])
        if "min_spread" in params:
            cmd.extend(["--min-spread", str(params["min_spread"])])
        if "maker_fee" in params:
            cmd.extend(["--maker-fee", str(params["maker_fee"])])
        if "taker_fee" in params:
            cmd.extend(["--taker-fee", str(params["taker_fee"])])
        if "add_transaction_costs" in params and params["add_transaction_costs"]:
            cmd.append("--add-transaction-costs")
        
        # 重平设置
        if "enable_rebalance" in params and params["enable_rebalance"]:
            cmd.append("--enable-rebalance")
        if "base_asset_target" in params:
            cmd.extend(["--base-asset-target", str(params["base_asset_target"])])
        if "rebalance_threshold" in params:
            cmd.extend(["--rebalance-threshold", str(params["rebalance_threshold"])])
        
        return cmd
    
    def _spawn_process(self, account: Dict[str, Any], symbol: str, index: int) -> subprocess.Popen:
        """
        启动单个刷单进程
        
        Args:
            account: 账号配置
            symbol: 交易对
            index: 账号索引
            
        Returns:
            进程对象
        """
        name = account.get("name", f"acc{index}")
        
        # 构建命令
        cmd = self._build_command(account, symbol)
        
        # 设置环境变量
        env = os.environ.copy()
        
        # 从账号配置中获取环境变量
        account_env = account.get("env", {})
        for k, v in account_env.items():
            if v is not None:
                env[str(k)] = str(v)
        
        # 设置日志相关环境变量
        env["ACCOUNT_NAME"] = name
        env["SYMBOL"] = symbol
        
        # 日志文件路径
        log_path = self.log_dir / f"{name}_{symbol}.log"
        
        # 打开日志文件
        stdout = open(log_path, "a", buffering=1, encoding="utf-8")
        stderr = subprocess.STDOUT
        
        # 启动子进程
        try:
            proc = subprocess.Popen(
                cmd,
                stdout=stdout,
                stderr=stderr,
                env=env,
                cwd=str(self.root_dir)
            )
            logger.info(f"[进程管理器] 已启动进程: pid={proc.pid}, name={name}, symbol={symbol}, log={log_path}")
            return proc
        except Exception as e:
            logger.error(f"[进程管理器] 启动进程失败: {name}_{symbol}, 错误: {e}")
            stdout.close()
            raise
    
    def start_account(self, account: Dict[str, Any], symbol: str, index: int = 1) -> bool:
        """
        启动单个账号进程
        
        Args:
            account: 账号配置
            symbol: 交易对
            index: 账号索引（默认1）
            
        Returns:
            是否启动成功
        """
        name = account.get("name", f"acc{index}")
        key = self.get_account_key(name, symbol)
        
        # 检查是否已经在运行
        if key in self.processes:
            proc = self.processes[key]
            if proc.poll() is None:  # 进程还在运行
                logger.info(f"[进程管理器] 账号 {name}_{symbol} (pid={proc.pid}) 已在运行，跳过")
                return True
        
        # 启动前随机抖动 0-2 秒，降低并发高峰
        time.sleep(random.random() * 2.0)
        
        try:
            proc = self._spawn_process(account, symbol, index)
            self.processes[key] = proc
            logger.info(f"[进程管理器] 已启动账号: {name}_{symbol} (pid={proc.pid})")
            return True
        except Exception as e:
            logger.error(f"[进程管理器] 启动账号失败: {name}_{symbol}, 错误: {e}")
            return False
    
    def stop_account(self, key: str):
        """
        停止单个账号进程
        
        Args:
            key: 账号唯一标识
        """
        if key not in self.processes:
            return
        
        proc = self.processes[key]
        pid = proc.pid
        
        if proc.poll() is None:  # 进程还在运行
            logger.info(f"[进程管理器] 正在停止账号进程: {key} (pid={pid})")
            try:
                if HAS_PSUTIL:
                    try:
                        psutil_proc = psutil.Process(pid)
                        psutil_proc.terminate()
                        try:
                            psutil_proc.wait(timeout=3)
                            logger.info(f"[进程管理器] 进程 {pid} 已正常退出")
                        except psutil.TimeoutExpired:
                            logger.warning(f"[进程管理器] 进程 {pid} 未响应，强制终止...")
                            psutil_proc.kill()
                            try:
                                psutil_proc.wait(timeout=2)
                                logger.info(f"[进程管理器] 进程 {pid} 已强制终止")
                            except psutil.TimeoutExpired:
                                logger.warning(f"[进程管理器] 警告: 进程 {pid} 仍未能终止")
                    except psutil.NoSuchProcess:
                        logger.info(f"[进程管理器] 进程 {pid} 已不存在")
                else:
                    # 备用方法
                    proc.terminate()
                    deadline = time.time() + 3
                    while proc.poll() is None and time.time() < deadline:
                        time.sleep(0.1)
                    if proc.poll() is None:
                        proc.kill()
                        logger.info(f"[进程管理器] 进程 {pid} 已强制终止")
            except Exception as e:
                logger.error(f"[进程管理器] 停止进程失败: {key}, 错误: {e}")
                try:
                    if proc.poll() is None:
                        proc.kill()
                except:
                    pass
        
        # 从字典中移除
        if key in self.processes:
            del self.processes[key]
    
    def start_all(self) -> bool:
        """
        启动所有账号
        
        Returns:
            是否启动成功
        """
        accounts = self.config_manager.load_accounts()
        if not accounts:
            logger.warning("没有找到任何账号配置")
            return False
        
        logger.info(f"[进程管理器] 准备启动 {len(accounts)} 个账号...")
        
        for i, account in enumerate(accounts, 1):
            symbols = account.get("symbols", [])
            if not symbols:
                name = account.get("name", f"acc{i}")
                logger.warning(f"[进程管理器] 账号 {name} 未配置 symbols，跳过")
                continue
            
            for symbol in symbols:
                self.start_account(account, symbol, i)
        
        return True
    
    def stop_all(self):
        """停止所有进程"""
        logger.info("[进程管理器] 正在停止所有进程...")
        self.should_stop = True
        
        # 优雅终止所有进程
        for key, proc in list(self.processes.items()):
            if proc.poll() is None:  # 进程还在运行
                try:
                    proc.terminate()
                except Exception:
                    pass
        
        # 最多等待5秒钟
        deadline = time.time() + 5
        for proc in list(self.processes.values()):
            if proc.poll() is None:
                try:
                    timeout = max(0, deadline - time.time())
                    proc.wait(timeout=timeout)
                except Exception:
                    pass
        
        # 仍未退出则强杀
        for proc in list(self.processes.values()):
            if proc.poll() is None:
                try:
                    proc.kill()
                except Exception:
                    pass
        
        self.processes.clear()
        logger.info("[进程管理器] 所有进程已停止")
    
    def monitor(self):
        """监控进程状态"""
        while not self.should_stop:
            # 清理已退出的进程
            dead_processes = []
            for key, proc in list(self.processes.items()):
                ret = proc.poll()
                if ret is not None:  # 进程已退出
                    dead_processes.append((key, proc.pid, ret))
            
            # 移除已退出的进程
            for key, pid, ret in dead_processes:
                logger.warning(f"[进程管理器] 进程已退出: {key} (pid={pid}, code={ret})")
                del self.processes[key]
            
            time.sleep(2)
    
    def get_status(self) -> Dict[str, Any]:
        """
        获取所有进程状态
        
        Returns:
            进程状态字典
        """
        status = {
            "total": len(self.processes),
            "running": 0,
            "stopped": 0,
            "processes": []
        }
        
        for key, proc in self.processes.items():
            is_running = proc.poll() is None
            if is_running:
                status["running"] += 1
            else:
                status["stopped"] += 1
            
            status["processes"].append({
                "key": key,
                "pid": proc.pid,
                "running": is_running,
                "return_code": proc.poll() if not is_running else None
            })
        
        return status

