#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
微信公众号缓存管理
提供 Access Token、用户信息、订阅信息等缓存功能
"""

import time
import hashlib
from typing import Optional, Dict, Any, List
from core.redis_manager import get_redis_manager
from utils.logger import get_logger

logger = get_logger(__name__)


class WeChatOfficialCache:
    """微信公众号缓存管理器"""
    
    # 缓存键前缀
    PREFIX_ACCESS_TOKEN = "wechat:access_token"
    PREFIX_USER = "wechat:user"
    PREFIX_SUBSCRIPTIONS = "wechat:subscriptions"
    PREFIX_SUBSCRIBED_USERS = "wechat:subscribed_users"
    
    # 默认 TTL（秒）
    TTL_ACCESS_TOKEN = 7000  # 微信 token 有效期 7200 秒，提前 200 秒刷新
    TTL_USER = 3600  # 1小时
    TTL_SUBSCRIPTIONS = 1800  # 30分钟
    TTL_SUBSCRIBED_USERS = 600  # 10分钟
    
    def __init__(self):
        self.redis = get_redis_manager()
    
    # ==================== Access Token 缓存 ====================
    
    def get_access_token(self, app_id: str) -> Optional[str]:
        """
        获取缓存的 Access Token
        
        Args:
            app_id: 微信公众号 AppID
        
        Returns:
            Access Token，如果不存在或已过期返回 None
        """
        key = f"{self.PREFIX_ACCESS_TOKEN}:{app_id}"
        token_data = self.redis.get(key)
        
        if token_data and isinstance(token_data, dict):
            token = token_data.get('access_token')
            expires_at = token_data.get('expires_at', 0)
            
            # 检查是否过期（提前 200 秒刷新）
            if time.time() < expires_at - 200:
                logger.debug(f"[缓存] Access Token 命中: {app_id}")
                return token
        
        logger.debug(f"[缓存] Access Token 未命中: {app_id}")
        return None
    
    def set_access_token(self, app_id: str, access_token: str, expires_in: int = 7200) -> bool:
        """
        缓存 Access Token
        
        Args:
            app_id: 微信公众号 AppID
            access_token: Access Token
            expires_in: 有效期（秒）
        
        Returns:
            成功返回 True
        """
        key = f"{self.PREFIX_ACCESS_TOKEN}:{app_id}"
        token_data = {
            'access_token': access_token,
            'expires_at': time.time() + expires_in,
            'created_at': time.time()
        }
        
        # TTL 设置为 expires_in + 100 秒（缓冲时间）
        ttl = expires_in + 100
        
        success = self.redis.set(key, token_data, ttl=ttl)
        if success:
            logger.debug(f"[缓存] Access Token 已缓存: {app_id}, TTL={ttl}秒")
        return success
    
    def delete_access_token(self, app_id: str) -> bool:
        """删除 Access Token 缓存"""
        key = f"{self.PREFIX_ACCESS_TOKEN}:{app_id}"
        return self.redis.delete(key)
    
    # ==================== 用户信息缓存 ====================
    
    def get_user(self, openid: str) -> Optional[Dict[str, Any]]:
        """
        获取缓存的用户信息
        
        Args:
            openid: 用户 openid
        
        Returns:
            用户信息字典，如果不存在返回 None
        """
        key = f"{self.PREFIX_USER}:{openid}"
        user = self.redis.get(key)
        
        if user:
            logger.debug(f"[缓存] 用户信息命中: {openid}")
        else:
            logger.debug(f"[缓存] 用户信息未命中: {openid}")
        
        return user
    
    def set_user(self, openid: str, user_info: Dict[str, Any], ttl: Optional[int] = None) -> bool:
        """
        缓存用户信息
        
        Args:
            openid: 用户 openid
            user_info: 用户信息字典
            ttl: 过期时间（秒），默认使用 TTL_USER
        """
        key = f"{self.PREFIX_USER}:{openid}"
        ttl = ttl or self.TTL_USER
        
        success = self.redis.set(key, user_info, ttl=ttl)
        if success:
            logger.debug(f"[缓存] 用户信息已缓存: {openid}, TTL={ttl}秒")
        return success
    
    def delete_user(self, openid: str) -> bool:
        """删除用户信息缓存"""
        key = f"{self.PREFIX_USER}:{openid}"
        return self.redis.delete(key)
    
    def delete_user_pattern(self, pattern: str = "*") -> int:
        """
        批量删除用户缓存（使用模式匹配）
        
        Args:
            pattern: 匹配模式，例如 "o*" 匹配所有以 o 开头的 openid
        
        Returns:
            删除的键数量
        """
        # 注意：Redis 的 keys 命令在生产环境可能阻塞，建议使用 scan
        # 这里简化处理，实际应该使用 scan_iter
        count = 0
        try:
            if self.redis.is_connected():
                # 使用 scan 迭代，避免阻塞
                cursor = 0
                while True:
                    cursor, keys = self.redis.client.scan(
                        cursor=cursor,
                        match=f"{self.PREFIX_USER}:{pattern}",
                        count=100
                    )
                    if keys:
                        self.redis.client.delete(*keys)
                        count += len(keys)
                    if cursor == 0:
                        break
        except Exception as e:
            logger.warning(f"批量删除用户缓存失败: {e}")
        
        return count
    
    # ==================== 订阅信息缓存 ====================
    
    def get_subscriptions(self, openid: str) -> Optional[List[Dict[str, Any]]]:
        """
        获取缓存的用户订阅信息
        
        Args:
            openid: 用户 openid
        
        Returns:
            订阅信息列表，如果不存在返回 None
        """
        key = f"{self.PREFIX_SUBSCRIPTIONS}:{openid}"
        subscriptions = self.redis.get(key)
        
        if subscriptions:
            logger.debug(f"[缓存] 订阅信息命中: {openid}")
        else:
            logger.debug(f"[缓存] 订阅信息未命中: {openid}")
        
        return subscriptions
    
    def set_subscriptions(self, openid: str, subscriptions: List[Dict[str, Any]], 
                         ttl: Optional[int] = None) -> bool:
        """
        缓存用户订阅信息
        
        Args:
            openid: 用户 openid
            subscriptions: 订阅信息列表
            ttl: 过期时间（秒），默认使用 TTL_SUBSCRIPTIONS
        """
        key = f"{self.PREFIX_SUBSCRIPTIONS}:{openid}"
        ttl = ttl or self.TTL_SUBSCRIPTIONS
        
        success = self.redis.set(key, subscriptions, ttl=ttl)
        if success:
            logger.debug(f"[缓存] 订阅信息已缓存: {openid}, TTL={ttl}秒")
        return success
    
    def delete_subscriptions(self, openid: str) -> bool:
        """删除用户订阅信息缓存"""
        key = f"{self.PREFIX_SUBSCRIPTIONS}:{openid}"
        return self.redis.delete(key)
    
    # ==================== 订阅用户列表缓存 ====================
    
    def get_subscribed_users(self, subscription_type: str) -> Optional[List[Dict[str, Any]]]:
        """
        获取订阅了指定类型消息的用户列表
        
        Args:
            subscription_type: 订阅类型（trade/alert/system/signal等）
        
        Returns:
            用户列表，如果不存在返回 None
        """
        key = f"{self.PREFIX_SUBSCRIBED_USERS}:{subscription_type}"
        users = self.redis.get(key)
        
        if users:
            logger.debug(f"[缓存] 订阅用户列表命中: {subscription_type}")
        else:
            logger.debug(f"[缓存] 订阅用户列表未命中: {subscription_type}")
        
        return users
    
    def set_subscribed_users(self, subscription_type: str, users: List[Dict[str, Any]], 
                            ttl: Optional[int] = None) -> bool:
        """
        缓存订阅用户列表
        
        Args:
            subscription_type: 订阅类型
            users: 用户列表
            ttl: 过期时间（秒），默认使用 TTL_SUBSCRIBED_USERS
        """
        key = f"{self.PREFIX_SUBSCRIBED_USERS}:{subscription_type}"
        ttl = ttl or self.TTL_SUBSCRIBED_USERS
        
        success = self.redis.set(key, users, ttl=ttl)
        if success:
            logger.debug(f"[缓存] 订阅用户列表已缓存: {subscription_type}, 用户数={len(users)}, TTL={ttl}秒")
        return success
    
    def delete_subscribed_users(self, subscription_type: Optional[str] = None) -> bool:
        """
        删除订阅用户列表缓存
        
        Args:
            subscription_type: 订阅类型，如果为 None 则删除所有类型的缓存
        """
        if subscription_type:
            key = f"{self.PREFIX_SUBSCRIBED_USERS}:{subscription_type}"
            return self.redis.delete(key)
        else:
            # 删除所有订阅用户列表缓存
            count = 0
            try:
                if self.redis.is_connected():
                    cursor = 0
                    while True:
                        cursor, keys = self.redis.client.scan(
                            cursor=cursor,
                            match=f"{self.PREFIX_SUBSCRIBED_USERS}:*",
                            count=100
                        )
                        if keys:
                            self.redis.client.delete(*keys)
                            count += len(keys)
                        if cursor == 0:
                            break
            except Exception as e:
                logger.warning(f"批量删除订阅用户列表缓存失败: {e}")
            
            return count > 0
    
    # ==================== 缓存统计 ====================
    
    def get_cache_stats(self) -> Dict[str, Any]:
        """获取缓存统计信息"""
        stats = {
            'redis_connected': self.redis.is_connected(),
            'cache_keys': {}
        }
        
        if self.redis.is_connected():
            try:
                # 统计各类缓存的键数量
                for prefix in [self.PREFIX_ACCESS_TOKEN, self.PREFIX_USER, 
                              self.PREFIX_SUBSCRIPTIONS, self.PREFIX_SUBSCRIBED_USERS]:
                    cursor = 0
                    count = 0
                    while True:
                        cursor, keys = self.redis.client.scan(
                            cursor=cursor,
                            match=f"{prefix}:*",
                            count=100
                        )
                        count += len(keys)
                        if cursor == 0:
                            break
                    stats['cache_keys'][prefix] = count
            except Exception as e:
                logger.warning(f"获取缓存统计失败: {e}")
        
        return stats


# 全局实例
_wechat_official_cache = None

def get_wechat_official_cache() -> WeChatOfficialCache:
    """获取微信公众号缓存管理器实例（单例）"""
    global _wechat_official_cache
    if _wechat_official_cache is None:
        _wechat_official_cache = WeChatOfficialCache()
    return _wechat_official_cache

