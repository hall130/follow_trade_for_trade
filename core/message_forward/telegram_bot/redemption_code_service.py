#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
交易所 API 兑换码管理服务
用于 Web 页面管理兑换码
"""

from typing import Dict, List, Optional, Any
import secrets
import string
from datetime import datetime, timedelta
from utils.logger import get_logger

logger = get_logger(__name__)


class RedemptionCodeService:
    """兑换码管理服务"""
    
    def __init__(self, db_pool):
        """
        初始化服务
        
        Args:
            db_pool: 数据库连接池
        """
        self.db_pool = db_pool
    
    def generate_code(self, length: int = 16) -> str:
        """
        生成兑换码
        
        Args:
            length: 码长度（默认16）
        
        Returns:
            格式化的兑换码（如：ABCD-EFGH-IJKL-MNOP）
        """
        # 生成随机码（只使用大写字母和数字）
        alphabet = string.ascii_uppercase + string.digits
        code = ''.join(secrets.choice(alphabet) for _ in range(length))
        
        # 格式化为 4-4-4-4 格式
        formatted_code = '-'.join([code[i:i+4] for i in range(0, len(code), 4)])
        return formatted_code
    
    def create_redemption_code(
        self,
        exchange: str,
        description: Optional[str] = None,
        expires_at: Optional[datetime] = None,
        created_by: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        创建兑换码
        
        Args:
            exchange: 交易所类型 ('okx' 或 'binance')
            description: 兑换码描述/备注
            expires_at: 过期时间（可选，NULL表示永不过期）
            created_by: 创建者用户ID
        
        Returns:
            创建的兑换码信息
        """
        if not self.db_pool:
            return {
                'success': False,
                'message': '数据库连接不可用'
            }
        
        try:
            # 生成唯一兑换码
            code = self.generate_code()
            
            # 确保兑换码唯一
            while self.get_code_by_code(code):
                code = self.generate_code()
            
            # 插入数据库
            sql = """
                INSERT INTO exchange_api_redemption_codes
                (code, exchange, description, is_active, expires_at, created_by, created_at)
                VALUES (%s, %s, %s, 1, %s, %s, NOW())
            """
            code_id = self.db_pool.execute(sql, (
                code, exchange, description, expires_at, created_by
            ))
            
            logger.info(f"✅ 创建兑换码成功: {code} ({exchange})")
            
            return {
                'success': True,
                'id': code_id,
                'code': code,
                'exchange': exchange,
                'description': description,
                'expires_at': expires_at.isoformat() if expires_at else None,
                'message': '兑换码创建成功'
            }
            
        except Exception as e:
            logger.error(f"创建兑换码失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return {
                'success': False,
                'message': f'创建失败: {str(e)}'
            }
    
    def get_code_by_code(self, code: str) -> Optional[Dict[str, Any]]:
        """
        根据兑换码获取信息
        
        Args:
            code: 兑换码
        
        Returns:
            兑换码信息，如果不存在返回None
        """
        if not self.db_pool:
            return None
        
        try:
            sql = """
                SELECT * FROM exchange_api_redemption_codes
                WHERE code = %s
            """
            rows = self.db_pool.query(sql, (code,))
            if rows:
                return dict(rows[0])
            return None
        except Exception as e:
            logger.error(f"查询兑换码失败: {e}")
            return None
    
    def get_redemption_codes(
        self,
        exchange: Optional[str] = None,
        is_active: Optional[int] = None,
        page: int = 1,
        page_size: int = 20,
        search: Optional[str] = None,
        user_only: bool = False,
        current_user_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        获取兑换码列表（支持分页和筛选）
        
        Args:
            exchange: 交易所类型筛选（可选）
            is_active: 是否激活筛选（可选，1=激活，0=禁用）
            page: 页码（从1开始）
            page_size: 每页数量
            search: 搜索关键词（搜索兑换码或描述）
            user_only: 如果为True，只返回未使用的兑换码或当前用户已使用的兑换码
            current_user_id: 当前用户ID（用于 user_only 模式，显示用户自己的兑换码）
        
        Returns:
            兑换码列表和分页信息
        """
        if not self.db_pool:
            return {
                'success': False,
                'data': [],
                'total': 0,
                'page': page,
                'page_size': page_size,
                'message': '数据库连接不可用'
            }
        
        try:
            # 构建查询条件
            conditions = []
            params = []
            
            if exchange:
                conditions.append("r.exchange = %s")
                params.append(exchange)
            
            # 注意：is_active 条件在 user_only 模式下需要特殊处理
            # 如果 user_only=True，我们需要分别处理未使用和已使用的情况
            # 所以先不在这里添加 is_active 条件，在 user_only 逻辑中处理
            
            # 普通用户只能查看：未使用的兑换码 或 自己已使用的兑换码
            if user_only:
                if current_user_id:
                    # 显示未使用的（user_id IS NULL，激活且未过期）或自己已使用的（user_id = current_user_id，显示所有）
                    # 使用复杂的条件：未使用的需要激活且未过期，已使用的显示所有（不过滤过期和激活状态）
                    conditions.append("(" +
                        "(r.user_id IS NULL AND r.is_active = 1 AND (r.expires_at IS NULL OR r.expires_at > NOW())) OR " +
                        "(r.user_id = %s)" +
                    ")")
                    params.append(current_user_id)
                else:
                    # 如果没有用户ID，只显示未使用的（激活且未过期）
                    conditions.append("r.user_id IS NULL")
                    conditions.append("r.is_active = 1")
                    conditions.append("(r.expires_at IS NULL OR r.expires_at > NOW())")
            else:
                # 管理员模式：如果指定了 is_active，添加条件
                if is_active is not None:
                    conditions.append("r.is_active = %s")
                    params.append(is_active)
            
            if search:
                conditions.append("(r.code LIKE %s OR r.description LIKE %s)")
                search_pattern = f"%{search}%"
                params.extend([search_pattern, search_pattern])
            
            where_clause = "WHERE " + " AND ".join(conditions) if conditions else ""
            
            # 获取总数（使用别名）
            count_sql = f"SELECT COUNT(*) as total FROM exchange_api_redemption_codes r {where_clause}"
            count_rows = self.db_pool.query(count_sql, tuple(params))
            total = count_rows[0]['total'] if count_rows else 0
            
            # 获取分页数据
            offset = (page - 1) * page_size
            sql = f"""
                SELECT 
                    r.id,
                    r.code,
                    r.exchange,
                    r.description,
                    r.user_id,
                    r.used_at,
                    r.is_active,
                    r.expires_at,
                    r.created_by,
                    r.created_at,
                    r.updated_at,
                    u.username as created_by_username,
                    u2.username as used_by_username
                FROM exchange_api_redemption_codes r
                LEFT JOIN users u ON r.created_by = u.id
                LEFT JOIN users u2 ON r.user_id = u2.id
                {where_clause}
                ORDER BY r.created_at DESC
                LIMIT %s OFFSET %s
            """
            params.extend([page_size, offset])
            rows = self.db_pool.query(sql, tuple(params))
            
            # 格式化数据
            codes = []
            for row in rows:
                code_data = dict(row)
                # 格式化日期
                if code_data.get('expires_at'):
                    if isinstance(code_data['expires_at'], str):
                        code_data['expires_at'] = code_data['expires_at']
                    else:
                        code_data['expires_at'] = code_data['expires_at'].isoformat() if hasattr(code_data['expires_at'], 'isoformat') else str(code_data['expires_at'])
                if code_data.get('used_at'):
                    if isinstance(code_data['used_at'], str):
                        code_data['used_at'] = code_data['used_at']
                    else:
                        code_data['used_at'] = code_data['used_at'].isoformat() if hasattr(code_data['used_at'], 'isoformat') else str(code_data['used_at'])
                if code_data.get('created_at'):
                    if isinstance(code_data['created_at'], str):
                        code_data['created_at'] = code_data['created_at']
                    else:
                        code_data['created_at'] = code_data['created_at'].isoformat() if hasattr(code_data['created_at'], 'isoformat') else str(code_data['created_at'])
                
                # 判断状态
                status = '未使用'
                if code_data.get('user_id'):
                    status = '已使用'
                elif code_data.get('expires_at'):
                    try:
                        expires_at = datetime.fromisoformat(code_data['expires_at'].replace('Z', '+00:00'))
                        if datetime.now() > expires_at:
                            status = '已过期'
                    except:
                        pass
                elif not code_data.get('is_active', 1):
                    status = '已禁用'
                
                code_data['status'] = status
                codes.append(code_data)
            
            return {
                'success': True,
                'data': codes,
                'total': total,
                'page': page,
                'page_size': page_size,
                'total_pages': (total + page_size - 1) // page_size if page_size > 0 else 1
            }
            
        except Exception as e:
            logger.error(f"获取兑换码列表失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return {
                'success': False,
                'data': [],
                'total': 0,
                'page': page,
                'page_size': page_size,
                'message': f'获取失败: {str(e)}'
            }
    
    def update_redemption_code(
        self,
        code_id: int,
        description: Optional[str] = None,
        is_active: Optional[int] = None,
        expires_at: Optional[datetime] = None
    ) -> Dict[str, Any]:
        """
        更新兑换码
        
        Args:
            code_id: 兑换码ID
            description: 新描述（可选）
            is_active: 是否激活（可选）
            expires_at: 新过期时间（可选）
        
        Returns:
            更新结果
        """
        if not self.db_pool:
            return {
                'success': False,
                'message': '数据库连接不可用'
            }
        
        try:
            updates = []
            params = []
            
            if description is not None:
                updates.append("description = %s")
                params.append(description)
            
            if is_active is not None:
                updates.append("is_active = %s")
                params.append(is_active)
            
            if expires_at is not None:
                updates.append("expires_at = %s")
                params.append(expires_at)
            
            if not updates:
                return {
                    'success': False,
                    'message': '没有需要更新的内容'
                }
            
            params.append(code_id)
            update_sql = f"""
                UPDATE exchange_api_redemption_codes
                SET {', '.join(updates)}, updated_at = NOW()
                WHERE id = %s
            """
            self.db_pool.execute(update_sql, tuple(params))
            
            logger.info(f"✅ 更新兑换码成功: ID={code_id}")
            
            return {
                'success': True,
                'message': '更新成功'
            }
            
        except Exception as e:
            logger.error(f"更新兑换码失败: {e}")
            return {
                'success': False,
                'message': f'更新失败: {str(e)}'
            }
    
    def delete_redemption_code(self, code_id: int) -> Dict[str, Any]:
        """
        删除兑换码
        
        Args:
            code_id: 兑换码ID
        
        Returns:
            删除结果
        """
        if not self.db_pool:
            return {
                'success': False,
                'message': '数据库连接不可用'
            }
        
        try:
            # 检查是否已被使用
            check_sql = "SELECT user_id FROM exchange_api_redemption_codes WHERE id = %s"
            rows = self.db_pool.query(check_sql, (code_id,))
            if rows and rows[0].get('user_id'):
                return {
                    'success': False,
                    'message': '该兑换码已被使用，无法删除'
                }
            
            # 删除兑换码
            delete_sql = "DELETE FROM exchange_api_redemption_codes WHERE id = %s"
            self.db_pool.execute(delete_sql, (code_id,))
            
            logger.info(f"✅ 删除兑换码成功: ID={code_id}")
            
            return {
                'success': True,
                'message': '删除成功'
            }
            
        except Exception as e:
            logger.error(f"删除兑换码失败: {e}")
            return {
                'success': False,
                'message': f'删除失败: {str(e)}'
            }
    
    def batch_create_redemption_codes(
        self,
        exchange: str,
        count: int,
        description: Optional[str] = None,
        expires_at: Optional[datetime] = None,
        created_by: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        批量创建兑换码
        
        Args:
            exchange: 交易所类型
            count: 创建数量
            description: 描述（可选）
            expires_at: 过期时间（可选）
            created_by: 创建者用户ID
        
        Returns:
            创建结果
        """
        if not self.db_pool:
            return {
                'success': False,
                'message': '数据库连接不可用'
            }
        
        try:
            created_codes = []
            failed_count = 0
            
            for i in range(count):
                result = self.create_redemption_code(
                    exchange=exchange,
                    description=description,
                    expires_at=expires_at,
                    created_by=created_by
                )
                
                if result.get('success'):
                    created_codes.append(result)
                else:
                    failed_count += 1
            
            logger.info(f"✅ 批量创建兑换码完成: 成功 {len(created_codes)} 个，失败 {failed_count} 个")
            
            return {
                'success': True,
                'created_count': len(created_codes),
                'failed_count': failed_count,
                'codes': created_codes,
                'message': f'成功创建 {len(created_codes)} 个兑换码'
            }
            
        except Exception as e:
            logger.error(f"批量创建兑换码失败: {e}")
            return {
                'success': False,
                'message': f'批量创建失败: {str(e)}'
            }
    
    def get_statistics(self, admin_only: bool = True) -> Dict[str, Any]:
        """
        获取兑换码统计信息
        
        Args:
            admin_only: 如果为True，返回完整统计；如果为False，只返回未使用的兑换码统计
        
        Returns:
            统计信息
        """
        if not self.db_pool:
            return {
                'success': False,
                'message': '数据库连接不可用'
            }
        
        try:
            if admin_only:
                # 管理员：完整统计
                # 总数量
                total_sql = "SELECT COUNT(*) as total FROM exchange_api_redemption_codes"
                total_rows = self.db_pool.query(total_sql)
                total = total_rows[0]['total'] if total_rows else 0
                
                # 已使用数量
                used_sql = "SELECT COUNT(*) as used FROM exchange_api_redemption_codes WHERE user_id IS NOT NULL"
                used_rows = self.db_pool.query(used_sql)
                used = used_rows[0]['used'] if used_rows else 0
                
                # 未使用数量
                unused = total - used
                
                # 按交易所统计
                exchange_sql = """
                    SELECT exchange, COUNT(*) as count,
                           SUM(CASE WHEN user_id IS NOT NULL THEN 1 ELSE 0 END) as used_count
                    FROM exchange_api_redemption_codes
                    GROUP BY exchange
                """
                exchange_rows = self.db_pool.query(exchange_sql)
                exchange_stats = {}
                for row in exchange_rows:
                    exchange_stats[row['exchange']] = {
                        'total': row['count'],
                        'used': row['used_count'],
                        'unused': row['count'] - row['used_count']
                    }
                
                return {
                    'success': True,
                    'total': total,
                    'used': used,
                    'unused': unused,
                    'exchange_stats': exchange_stats
                }
            else:
                # 普通用户：只统计未使用的兑换码
                unused_sql = """
                    SELECT COUNT(*) as unused 
                    FROM exchange_api_redemption_codes 
                    WHERE user_id IS NULL 
                    AND is_active = 1 
                    AND (expires_at IS NULL OR expires_at > NOW())
                """
                unused_rows = self.db_pool.query(unused_sql)
                unused = unused_rows[0]['unused'] if unused_rows else 0
                
                # 按交易所统计未使用的
                exchange_sql = """
                    SELECT exchange, COUNT(*) as unused_count
                    FROM exchange_api_redemption_codes
                    WHERE user_id IS NULL 
                    AND is_active = 1 
                    AND (expires_at IS NULL OR expires_at > NOW())
                    GROUP BY exchange
                """
                exchange_rows = self.db_pool.query(exchange_sql)
                exchange_stats = {}
                for row in exchange_rows:
                    exchange_stats[row['exchange']] = {
                        'unused': row['unused_count']
                    }
                
                return {
                    'success': True,
                    'total': unused,
                    'used': 0,
                    'unused': unused,
                    'exchange_stats': exchange_stats
                }
            
        except Exception as e:
            logger.error(f"获取统计信息失败: {e}")
            return {
                'success': False,
                'message': f'获取失败: {str(e)}'
            }

