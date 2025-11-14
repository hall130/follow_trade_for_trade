#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
加密中间件
处理前端加密请求的解密
"""

import os
import sys
import base64
import json
import secrets
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from flask import request, g

# 添加项目根目录到Python路径
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from utils.logger import get_logger

logger = get_logger(__name__)

class CryptoMiddleware:
    """加密中间件类"""
    
    def __init__(self):
        # 从环境变量获取加密密钥，如果没有则使用默认密钥（生产环境必须设置）
        self.encryption_key = os.getenv('ENCRYPTION_KEY', 'default-encryption-key-32-bytes!!').encode('utf-8')
        
        # 确保密钥长度为32字节（AES-256）
        if len(self.encryption_key) < 32:
            self.encryption_key = self.encryption_key.ljust(32, b'0')[:32]
        elif len(self.encryption_key) > 32:
            self.encryption_key = self.encryption_key[:32]
        
        # 临时密钥存储（用于密钥交换）
        self.temp_keys: Dict[str, Dict[str, Any]] = {}
        self.temp_key_expire_minutes = 5  # 临时密钥5分钟过期
    
    def generate_temp_key(self) -> Dict[str, str]:
        """生成临时加密密钥（用于密钥交换）"""
        try:
            # 生成随机密钥
            temp_key = secrets.token_bytes(32)
            key_id = secrets.token_urlsafe(16)
            
            # 存储临时密钥
            self.temp_keys[key_id] = {
                'key': temp_key,
                'created_at': datetime.utcnow(),
                'expires_at': datetime.utcnow() + timedelta(minutes=self.temp_key_expire_minutes)
            }
            
            # 清理过期密钥
            self._cleanup_expired_keys()
            
            return {
                'key_id': key_id,
                'key': base64.b64encode(temp_key).decode('utf-8'),
                'salt': base64.b64encode(secrets.token_bytes(16)).decode('utf-8'),
                'expires_in': self.temp_key_expire_minutes * 60
            }
        except Exception as e:
            logger.error(f"生成临时密钥失败: {e}")
            raise
    
    def get_temp_key(self, key_id: str) -> Optional[bytes]:
        """获取临时密钥"""
        try:
            if key_id not in self.temp_keys:
                return None
            
            key_data = self.temp_keys[key_id]
            
            # 检查是否过期
            if datetime.utcnow() > key_data['expires_at']:
                del self.temp_keys[key_id]
                return None
            
            return key_data['key']
        except Exception as e:
            logger.error(f"获取临时密钥失败: {e}")
            return None
    
    def _cleanup_expired_keys(self):
        """清理过期的临时密钥"""
        try:
            now = datetime.utcnow()
            expired_keys = [
                key_id for key_id, key_data in self.temp_keys.items()
                if now > key_data['expires_at']
            ]
            for key_id in expired_keys:
                del self.temp_keys[key_id]
        except Exception as e:
            logger.error(f"清理过期密钥失败: {e}")
    
    def decrypt_request(self, encrypted_data: str, use_temp_key: bool = False, key_id: str = None) -> Optional[Dict[str, Any]]:
        """
        解密请求数据
        
        Args:
            encrypted_data: Base64编码的加密数据
            use_temp_key: 是否使用临时密钥
            key_id: 临时密钥ID（如果使用临时密钥）
        
        Returns:
            解密后的数据字典，如果解密失败返回None
        """
        try:
            # 选择使用的密钥
            if use_temp_key and key_id:
                key = self.get_temp_key(key_id)
                if not key:
                    logger.warning(f"临时密钥不存在或已过期: {key_id}")
                    return None
            else:
                key = self.encryption_key
            
            # Base64解码
            combined = base64.b64decode(encrypted_data)
            
            # 提取IV（前12字节）和加密数据
            iv = combined[:12]
            ciphertext = combined[12:]
            
            # 解密
            aesgcm = AESGCM(key)
            decrypted_data = aesgcm.decrypt(iv, ciphertext, None)
            
            # 解析JSON
            data = json.loads(decrypted_data.decode('utf-8'))
            return data
            
        except Exception as e:
            logger.error(f"解密请求数据失败: {e}")
            return None
    
    def should_decrypt(self) -> bool:
        """判断当前请求是否需要解密"""
        # 检查请求头中是否有加密标记
        return request.headers.get('X-Encrypted', '').lower() == 'true'
    
    def decrypt_request_body(self) -> Optional[Dict[str, Any]]:
        """解密请求体"""
        try:
            if not self.should_decrypt():
                return None
            
            # 获取加密数据
            data = request.get_json(silent=True)
            if not data or 'encrypted_data' not in data:
                logger.warning("请求标记为加密，但未找到encrypted_data字段")
                return None
            
            encrypted_data = data['encrypted_data']
            key_id = data.get('key_id')  # 可选：临时密钥ID
            
            # 解密
            decrypted = self.decrypt_request(
                encrypted_data,
                use_temp_key=bool(key_id),
                key_id=key_id
            )
            
            if decrypted:
                # 将解密后的数据存储到g对象，供后续使用
                g.decrypted_data = decrypted
                return decrypted
            else:
                logger.error("请求解密失败")
                return None
                
        except Exception as e:
            logger.error(f"解密请求体失败: {e}")
            return None

# 全局实例
crypto_middleware = CryptoMiddleware()

