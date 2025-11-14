"""
Backpack API认证和签名模块
"""
import base64
import nacl.signing
from typing import Optional
from utils.logger import logger


def create_signature(secret_key: str, message: str) -> Optional[str]:
    """
    创建API签名
    
    Args:
        secret_key: API密钥（base64编码）
        message: 要签名的消息
        
    Returns:
        签名字符串或None（如果签名失败）
    """
    try:
        # 解码密钥并签名
        decoded_key = base64.b64decode(secret_key)
        signing_key = nacl.signing.SigningKey(decoded_key)
        signature = signing_key.sign(message.encode('utf-8')).signature
        return base64.b64encode(signature).decode('utf-8')
    except Exception as e:
        logger.error(f"签名创建失败: {e}")
        return None

