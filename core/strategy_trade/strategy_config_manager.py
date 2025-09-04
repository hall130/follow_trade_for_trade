import json
import os
from typing import Dict, List, Optional, Any
from datetime import datetime
from utils.logger import get_logger

logger = get_logger(__name__)

class StrategyConfigManager:
    """策略配置管理器"""
    
    def __init__(self, config_dir: str = "config/strategies"):
        self.config_dir = config_dir
        self.config_file = os.path.join(config_dir, "strategy_configs.json")
        self.backup_dir = os.path.join(config_dir, "backups")
        
        # 确保目录存在
        os.makedirs(config_dir, exist_ok=True)
        os.makedirs(self.backup_dir, exist_ok=True)
        
        # 加载配置
        self.configs = self._load_configs()
    
    def _load_configs(self) -> Dict[str, Any]:
        """加载配置文件"""
        try:
            if os.path.exists(self.config_file):
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    configs = json.load(f)
                    logger.info(f"成功加载策略配置文件: {self.config_file}")
                    return configs
            else:
                # 创建默认配置文件
                default_configs = self._create_default_configs()
                self._save_configs(default_configs)
                return default_configs
                
        except Exception as e:
            logger.error(f"加载策略配置文件失败: {e}")
            return self._create_default_configs()
    
    def _create_default_configs(self) -> Dict[str, Any]:
        """创建默认配置"""
        return {
            "version": "1.0.0",
            "last_updated": datetime.now().isoformat(),
            "strategies": {},
            "global_settings": {
                "default_risk_per_trade": 0.02,
                "default_max_positions": 3,
                "default_position_sizing": "fixed",
                "enable_risk_management": True,
                "enable_backtesting": True,
                "enable_logging": True,
                "log_level": "INFO"
            },
            "risk_management": {
                "max_daily_loss": 0.05,
                "max_total_exposure": 0.8,
                "max_single_exposure": 0.2,
                "max_drawdown": 0.2,
                "correlation_threshold": 0.7
            },
            "backtesting": {
                "default_initial_capital": 10000,
                "default_commission": 0.001,
                "default_slippage": 0.0005,
                "enable_optimization": False,
                "optimization_method": "grid_search"
            }
        }
    
    def _save_configs(self, configs: Dict[str, Any]):
        """保存配置文件"""
        try:
            # 创建备份
            if os.path.exists(self.config_file):
                backup_file = os.path.join(
                    self.backup_dir, 
                    f"strategy_configs_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
                )
                os.rename(self.config_file, backup_file)
                logger.info(f"配置文件已备份: {backup_file}")
            
            # 保存新配置
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(configs, f, indent=2, ensure_ascii=False)
            
            logger.info(f"策略配置文件已保存: {self.config_file}")
            
        except Exception as e:
            logger.error(f"保存策略配置文件失败: {e}")
    
    def save_strategy_config(self, strategy_name: str, config: Dict[str, Any]) -> bool:
        """保存策略配置"""
        try:
            self.configs["strategies"][strategy_name] = {
                "config": config,
                "created_at": datetime.now().isoformat(),
                "updated_at": datetime.now().isoformat(),
                "version": "1.0.0"
            }
            
            self.configs["last_updated"] = datetime.now().isoformat()
            self._save_configs(self.configs)
            
            logger.info(f"策略配置已保存: {strategy_name}")
            return True
            
        except Exception as e:
            logger.error(f"保存策略配置失败: {e}")
            return False
    
    def get_strategy_config(self, strategy_name: str) -> Optional[Dict[str, Any]]:
        """获取策略配置"""
        try:
            if strategy_name in self.configs["strategies"]:
                return self.configs["strategies"][strategy_name]["config"]
            return None
            
        except Exception as e:
            logger.error(f"获取策略配置失败: {e}")
            return None
    
    def get_all_strategy_configs(self) -> Dict[str, Any]:
        """获取所有策略配置"""
        return self.configs.get("strategies", {})
    
    def update_strategy_config(self, strategy_name: str, new_config: Dict[str, Any]) -> bool:
        """更新策略配置"""
        try:
            if strategy_name in self.configs["strategies"]:
                # 保留创建时间，更新修改时间
                created_at = self.configs["strategies"][strategy_name]["created_at"]
                
                self.configs["strategies"][strategy_name] = {
                    "config": new_config,
                    "created_at": created_at,
                    "updated_at": datetime.now().isoformat(),
                    "version": "1.0.0"
                }
                
                self.configs["last_updated"] = datetime.now().isoformat()
                self._save_configs(self.configs)
                
                logger.info(f"策略配置已更新: {strategy_name}")
                return True
            else:
                logger.warning(f"策略不存在，无法更新: {strategy_name}")
                return False
                
        except Exception as e:
            logger.error(f"更新策略配置失败: {e}")
            return False
    
    def delete_strategy_config(self, strategy_name: str) -> bool:
        """删除策略配置"""
        try:
            if strategy_name in self.configs["strategies"]:
                del self.configs["strategies"][strategy_name]
                self.configs["last_updated"] = datetime.now().isoformat()
                self._save_configs(self.configs)
                
                logger.info(f"策略配置已删除: {strategy_name}")
                return True
            else:
                logger.warning(f"策略不存在，无法删除: {strategy_name}")
                return False
                
        except Exception as e:
            logger.error(f"删除策略配置失败: {e}")
            return False
    
    def get_global_settings(self) -> Dict[str, Any]:
        """获取全局设置"""
        return self.configs.get("global_settings", {})
    
    def update_global_settings(self, new_settings: Dict[str, Any]) -> bool:
        """更新全局设置"""
        try:
            self.configs["global_settings"].update(new_settings)
            self.configs["last_updated"] = datetime.now().isoformat()
            self._save_configs(self.configs)
            
            logger.info("全局设置已更新")
            return True
            
        except Exception as e:
            logger.error(f"更新全局设置失败: {e}")
            return False
    
    def get_risk_management_config(self) -> Dict[str, Any]:
        """获取风险管理配置"""
        return self.configs.get("risk_management", {})
    
    def update_risk_management_config(self, new_config: Dict[str, Any]) -> bool:
        """更新风险管理配置"""
        try:
            self.configs["risk_management"].update(new_config)
            self.configs["last_updated"] = datetime.now().isoformat()
            self._save_configs(self.configs)
            
            logger.info("风险管理配置已更新")
            return True
            
        except Exception as e:
            logger.error(f"更新风险管理配置失败: {e}")
            return False
    
    def get_backtesting_config(self) -> Dict[str, Any]:
        """获取回测配置"""
        return self.configs.get("backtesting", {})
    
    def update_backtesting_config(self, new_config: Dict[str, Any]) -> bool:
        """更新回测配置"""
        try:
            self.configs["backtesting"].update(new_config)
            self.configs["last_updated"] = datetime.now().isoformat()
            self._save_configs(self.configs)
            
            logger.info("回测配置已更新")
            return True
            
        except Exception as e:
            logger.error(f"更新回测配置失败: {e}")
            return False
    
    def export_config(self, export_path: str) -> bool:
        """导出配置文件"""
        try:
            with open(export_path, 'w', encoding='utf-8') as f:
                json.dump(self.configs, f, indent=2, ensure_ascii=False)
            
            logger.info(f"配置文件已导出: {export_path}")
            return True
            
        except Exception as e:
            logger.error(f"导出配置文件失败: {e}")
            return False
    
    def import_config(self, import_path: str) -> bool:
        """导入配置文件"""
        try:
            with open(import_path, 'r', encoding='utf-8') as f:
                imported_configs = json.load(f)
            
            # 验证配置文件格式
            if not self._validate_imported_config(imported_configs):
                logger.error("导入的配置文件格式无效")
                return False
            
            # 备份当前配置
            backup_file = os.path.join(
                self.backup_dir, 
                f"strategy_configs_backup_before_import_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            )
            self._save_configs(self.configs)
            os.rename(self.config_file, backup_file)
            
            # 应用导入的配置
            self.configs = imported_configs
            self.configs["last_updated"] = datetime.now().isoformat()
            self._save_configs(self.configs)
            
            logger.info(f"配置文件已导入: {import_path}")
            return True
            
        except Exception as e:
            logger.error(f"导入配置文件失败: {e}")
            return False
    
    def _validate_imported_config(self, config: Dict[str, Any]) -> bool:
        """验证导入的配置文件"""
        required_keys = ["version", "strategies", "global_settings"]
        
        for key in required_keys:
            if key not in config:
                return False
        
        return True
    
    def get_config_summary(self) -> Dict[str, Any]:
        """获取配置摘要"""
        return {
            "total_strategies": len(self.configs.get("strategies", {})),
            "active_strategies": len([s for s in self.configs.get("strategies", {}).values() 
                                   if s.get("config", {}).get("is_active", False)]),
            "last_updated": self.configs.get("last_updated"),
            "version": self.configs.get("version"),
            "global_settings": self.configs.get("global_settings", {}),
            "risk_management": self.configs.get("risk_management", {}),
            "backtesting": self.configs.get("backtesting", {})
        }
    
    def create_strategy_template(self, strategy_type: str, name: str, 
                               base_config: Dict[str, Any]) -> bool:
        """创建策略模板"""
        try:
            template_key = f"{strategy_type}_{name}"
            
            self.configs["strategies"][template_key] = {
                "config": base_config,
                "created_at": datetime.now().isoformat(),
                "updated_at": datetime.now().isoformat(),
                "version": "1.0.0",
                "is_template": True,
                "strategy_type": strategy_type
            }
            
            self.configs["last_updated"] = datetime.now().isoformat()
            self._save_configs(self.configs)
            
            logger.info(f"策略模板已创建: {template_key}")
            return True
            
        except Exception as e:
            logger.error(f"创建策略模板失败: {e}")
            return False
    
    def get_strategy_templates(self) -> Dict[str, Any]:
        """获取策略模板"""
        templates = {}
        for name, config in self.configs.get("strategies", {}).items():
            if config.get("is_template", False):
                templates[name] = config
        
        return templates
    
    def clone_strategy_config(self, source_name: str, new_name: str) -> bool:
        """克隆策略配置"""
        try:
            if source_name not in self.configs["strategies"]:
                logger.error(f"源策略不存在: {source_name}")
                return False
            
            source_config = self.configs["strategies"][source_name]["config"].copy()
            source_config["name"] = new_name
            
            self.configs["strategies"][new_name] = {
                "config": source_config,
                "created_at": datetime.now().isoformat(),
                "updated_at": datetime.now().isoformat(),
                "version": "1.0.0",
                "is_template": False
            }
            
            self.configs["last_updated"] = datetime.now().isoformat()
            self._save_configs(self.configs)
            
            logger.info(f"策略配置已克隆: {source_name} -> {new_name}")
            return True
            
        except Exception as e:
            logger.error(f"克隆策略配置失败: {e}")
            return False 