#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Telegram Bot 状态管理器
管理用户会话状态和上下文数据
"""

from typing import Dict, Any, Optional
from datetime import datetime
import json
from utils.logger import get_logger

logger = get_logger(__name__)


class StateManager:
    """状态管理器"""
    
    def __init__(self, db_pool):
        """
        初始化状态管理器
        
        Args:
            db_pool: 数据库连接池
        """
        self.db_pool = db_pool
    
    def get_session(self, user_id: int) -> Dict[str, Any]:
        """
        获取用户会话状态
        
        Args:
            user_id: 用户ID
        
        Returns:
            会话状态字典
        """
        if not self.db_pool:
            logger.error("数据库连接池不可用，无法获取用户会话")
            return {
                'user_id': user_id,
                'current_state': 'main_menu',
                'context_data': {},
                'navigation_stack': []
            }
        
        try:
            sql = """
                SELECT * FROM telegram_user_sessions 
                WHERE user_id = %s
            """
            rows = self.db_pool.query(sql, (user_id,))
            
            if rows:
                session = dict(rows[0])
                # 解析 JSON 字段
                if session.get('context_data'):
                    if isinstance(session['context_data'], str):
                        session['context_data'] = json.loads(session['context_data'])
                else:
                    session['context_data'] = {}
                
                # 初始化导航栈
                if 'navigation_stack' not in session.get('context_data', {}):
                    session['context_data']['navigation_stack'] = []
                
                return session
            else:
                # 创建新会话
                return self.create_session(user_id)
                
        except Exception as e:
            logger.error(f"获取用户会话失败: {e}")
            return {
                'user_id': user_id,
                'current_state': 'main_menu',
                'context_data': {'navigation_stack': []}
            }
    
    def create_session(self, user_id: int, current_state: str = 'main_menu', context_data: Optional[Dict] = None) -> Dict[str, Any]:
        """
        创建新会话
        
        Args:
            user_id: 用户ID
            current_state: 当前状态
            context_data: 上下文数据
        
        Returns:
            创建的会话字典
        """
        if not self.db_pool:
            logger.error("数据库连接池不可用，无法创建用户会话")
            if context_data is None:
                context_data = {'navigation_stack': []}
            return {
                'user_id': user_id,
                'current_state': current_state,
                'context_data': context_data
            }
        
        try:
            if context_data is None:
                context_data = {}
            
            # 确保导航栈存在
            if 'navigation_stack' not in context_data:
                context_data['navigation_stack'] = []
            
            sql = """
                INSERT INTO telegram_user_sessions 
                (user_id, current_state, context_data)
                VALUES (%s, %s, %s)
                ON DUPLICATE KEY UPDATE
                    current_state = VALUES(current_state),
                    context_data = VALUES(context_data),
                    updated_at = CURRENT_TIMESTAMP
            """
            
            context_data_json = json.dumps(context_data, ensure_ascii=False)
            self.db_pool.execute(sql, (user_id, current_state, context_data_json))
            
            return {
                'user_id': user_id,
                'current_state': current_state,
                'context_data': context_data
            }
            
        except Exception as e:
            logger.error(f"创建用户会话失败: {e}")
            if context_data is None:
                context_data = {'navigation_stack': []}
            return {
                'user_id': user_id,
                'current_state': current_state,
                'context_data': context_data
            }
    
    def push_navigation(self, user_id: int, page: str) -> bool:
        """
        推入页面到导航栈
        
        Args:
            user_id: 用户ID
            page: 页面标识（如 'subscription_menu', 'select_intervals' 等）
        
        Returns:
            是否成功
        """
        try:
            session = self.get_session(user_id)
            context_data = session.get('context_data', {})
            navigation_stack = context_data.get('navigation_stack', [])
            
            # 如果当前页面已经在栈顶，不重复添加
            if navigation_stack and navigation_stack[-1] == page:
                return True
            
            # 推入新页面
            navigation_stack.append(page)
            context_data['navigation_stack'] = navigation_stack
            
            return self.update_session(user_id, context_data=context_data)
        except Exception as e:
            logger.error(f"推入导航栈失败: {e}")
            return False
    
    def pop_navigation(self, user_id: int) -> Optional[str]:
        """
        从导航栈弹出上一页
        
        Args:
            user_id: 用户ID
        
        Returns:
            上一页标识，如果没有则返回 None
        """
        try:
            session = self.get_session(user_id)
            context_data = session.get('context_data', {})
            navigation_stack = context_data.get('navigation_stack', [])
            
            # 移除当前页面（栈顶）
            if navigation_stack:
                navigation_stack.pop()
            
            # 获取上一页
            previous_page = navigation_stack[-1] if navigation_stack else None
            
            context_data['navigation_stack'] = navigation_stack
            self.update_session(user_id, context_data=context_data)
            
            return previous_page
        except Exception as e:
            logger.error(f"弹出导航栈失败: {e}")
            return None
    
    def clear_navigation(self, user_id: int) -> bool:
        """
        清空导航栈
        
        Args:
            user_id: 用户ID
        
        Returns:
            是否成功
        """
        try:
            session = self.get_session(user_id)
            context_data = session.get('context_data', {})
            context_data['navigation_stack'] = []
            return self.update_session(user_id, context_data=context_data)
        except Exception as e:
            logger.error(f"清空导航栈失败: {e}")
            return False
    
    def get_previous_page(self, user_id: int) -> Optional[str]:
        """
        获取上一页（不弹出）
        
        Args:
            user_id: 用户ID
        
        Returns:
            上一页标识，如果没有则返回 None
        """
        try:
            session = self.get_session(user_id)
            context_data = session.get('context_data', {})
            navigation_stack = context_data.get('navigation_stack', [])
            
            # 返回倒数第二个页面（上一页）
            if len(navigation_stack) > 1:
                return navigation_stack[-2]
            return None
        except Exception as e:
            logger.error(f"获取上一页失败: {e}")
            return None
    
    def update_session(
        self,
        user_id: int,
        current_state: Optional[str] = None,
        context_data: Optional[Dict] = None
    ) -> bool:
        """
        更新用户会话状态
        
        Args:
            user_id: 用户ID
            current_state: 新状态（可选）
            context_data: 新上下文数据（可选）
        
        Returns:
            是否更新成功
        """
        if not self.db_pool:
            logger.error("数据库连接池不可用，无法更新用户会话")
            return False
        
        try:
            # 获取当前会话
            session = self.get_session(user_id)
            
            # 更新状态
            if current_state is not None:
                session['current_state'] = current_state
            
            # 更新上下文数据
            if context_data is not None:
                session['context_data'] = context_data
            elif context_data is None and current_state is not None:
                # 如果只更新状态，保持现有上下文数据
                pass
            
            # 保存到数据库
            sql = """
                INSERT INTO telegram_user_sessions 
                (user_id, current_state, context_data)
                VALUES (%s, %s, %s)
                ON DUPLICATE KEY UPDATE
                    current_state = VALUES(current_state),
                    context_data = VALUES(context_data),
                    updated_at = CURRENT_TIMESTAMP
            """
            
            context_data_json = json.dumps(session['context_data'], ensure_ascii=False)
            self.db_pool.execute(sql, (user_id, session['current_state'], context_data_json))
            
            return True
            
        except Exception as e:
            logger.error(f"更新用户会话失败: {e}")
            return False
    
    def clear_session(self, user_id: int) -> bool:
        """
        清除用户会话
        
        Args:
            user_id: 用户ID
        
        Returns:
            是否清除成功
        """
        if not self.db_pool:
            logger.error("数据库连接池不可用，无法清除用户会话")
            return False
        
        try:
            sql = """
                DELETE FROM telegram_user_sessions 
                WHERE user_id = %s
            """
            self.db_pool.execute(sql, (user_id,))
            return True
        except Exception as e:
            logger.error(f"清除用户会话失败: {e}")
            return False

