"""
刷单配置管理器
管理刷单账号配置，支持从JSON文件或数据库加载
"""
import json
import os
from pathlib import Path
from typing import Dict, List, Any, Optional
from utils.logger import logger


class MarketMakerConfigManager:
    """刷单配置管理器"""
    
    def __init__(self, config_file: Optional[str] = None):
        """
        初始化配置管理器
        
        Args:
            config_file: 配置文件路径，默认为项目根目录下的 market_maker_accounts.json
        """
        if config_file:
            self.config_file = Path(config_file)
        else:
            # 默认配置文件路径
            self.config_file = Path(__file__).parent.parent.parent / "market_maker_accounts.json"
        
        self.config_file = self.config_file.resolve()
        self._ensure_config_file()
    
    def _ensure_config_file(self):
        """确保配置文件存在，如果不存在则创建示例配置"""
        if not self.config_file.exists():
            logger.warning(f"配置文件不存在: {self.config_file}，创建示例配置...")
            self._create_example_config()
    
    def _create_example_config(self):
        """创建示例配置文件"""
        example_config = {
            "accounts": [
                {
                    "name": "account1",
                    "exchange": "backpack",
                    "market_type": "spot",
                    "symbols": ["SOL_USDC", "BTC_USDC"],
                    "env": {
                        "BACKPACK_KEY": "your_api_key_here",
                        "BACKPACK_SECRET": "your_secret_key_here",
                        "BASE_URL": "https://api.backpack.work"
                    },
                    "params": {
                        "spread": 0.5,
                        "quantity": 0.1,
                        "max_orders": 3,
                        "interval": 60,
                        "duration": 3600,
                        "strategy": "standard"
                    }
                }
            ]
        }
        
        try:
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(example_config, f, indent=2, ensure_ascii=False)
            logger.info(f"已创建示例配置文件: {self.config_file}")
        except Exception as e:
            logger.error(f"创建配置文件失败: {e}")
    
    def load_accounts(self) -> List[Dict[str, Any]]:
        """
        加载账号配置
        
        Returns:
            账号配置列表
        """
        if not self.config_file.exists():
            logger.warning(f"配置文件不存在: {self.config_file}")
            return []
        
        try:
            with open(self.config_file, 'r', encoding='utf-8') as f:
                config = json.load(f)
            
            accounts = config.get("accounts", [])
            logger.info(f"从配置文件加载了 {len(accounts)} 个账号配置")
            return accounts
        except json.JSONDecodeError as e:
            logger.error(f"配置文件JSON格式错误: {e}")
            return []
        except Exception as e:
            logger.error(f"加载配置文件失败: {e}")
            return []
    
    def save_accounts(self, accounts: List[Dict[str, Any]]):
        """
        保存账号配置到文件
        
        Args:
            accounts: 账号配置列表
        """
        config = {"accounts": accounts}
        try:
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(config, f, indent=2, ensure_ascii=False)
            logger.info(f"已保存 {len(accounts)} 个账号配置到: {self.config_file}")
        except Exception as e:
            logger.error(f"保存配置文件失败: {e}")
            raise
    
    def add_account(self, account: Dict[str, Any]) -> bool:
        """
        添加账号配置
        
        Args:
            account: 账号配置字典
            
        Returns:
            是否添加成功
        """
        accounts = self.load_accounts()
        
        # 检查是否已存在同名账号
        name = account.get("name")
        if name:
            for existing in accounts:
                if existing.get("name") == name:
                    logger.warning(f"账号 {name} 已存在，将更新配置")
                    accounts.remove(existing)
                    break
        
        accounts.append(account)
        self.save_accounts(accounts)
        return True
    
    def remove_account(self, account_name: str) -> bool:
        """
        删除账号配置
        
        Args:
            account_name: 账号名称
            
        Returns:
            是否删除成功
        """
        accounts = self.load_accounts()
        original_count = len(accounts)
        
        accounts = [acc for acc in accounts if acc.get("name") != account_name]
        
        if len(accounts) < original_count:
            self.save_accounts(accounts)
            logger.info(f"已删除账号配置: {account_name}")
            return True
        else:
            logger.warning(f"未找到账号配置: {account_name}")
            return False
    
    def get_account(self, account_name: str) -> Optional[Dict[str, Any]]:
        """
        获取指定账号配置
        
        Args:
            account_name: 账号名称
            
        Returns:
            账号配置字典，如果不存在返回None
        """
        accounts = self.load_accounts()
        for account in accounts:
            if account.get("name") == account_name:
                return account
        return None

