"""
邀请码管理服务
用于管理转发规则的邀请码和订阅
"""

import uuid
import secrets
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
from utils.logger import get_logger

logger = get_logger(__name__)


class InvitationCodeService:
    """邀请码服务"""
    
    def __init__(self, db):
        """
        初始化邀请码服务
        
        Args:
            db: 数据库操作实例（MessageForwardDB）或数据库连接池
        """
        self.db = db
        # 获取数据库连接池
        if hasattr(db, 'db_pool'):
            self.db_pool = db.db_pool
        elif hasattr(db, '_db_pool'):
            self.db_pool = db._db_pool
        else:
            # 如果传入的就是连接池
            self.db_pool = db
    
    def generate_code(self, length: int = 12) -> str:
        """
        生成邀请码
        
        Args:
            length: 邀请码长度（默认12位）
        
        Returns:
            邀请码字符串（格式：XXXX-XXXX-XXXX）
        """
        # 生成随机字符串（使用大写字母和数字）
        chars = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789'  # 排除容易混淆的字符
        code = ''.join(secrets.choice(chars) for _ in range(length))
        
        # 格式化为 XXXX-XXXX-XXXX
        formatted_code = '-'.join([code[i:i+4] for i in range(0, len(code), 4)])
        return formatted_code
    
    def create_invitation_code(
        self,
        rule_id: str,
        duration_days: int = 30,
        max_uses: int = 1,
        target_platform_id: Optional[int] = None,
        target_chat_id: Optional[str] = None,
        expires_at: Optional[datetime] = None,
        created_by: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        创建邀请码
        
        Args:
            rule_id: 转发规则ID
            duration_days: 有效期天数（续订时延长的时间）
            max_uses: 最大使用次数（0表示无限制）
            target_platform_id: 目标平台ID（可选，NULL表示适用于规则的所有目标平台）
            target_chat_id: 目标聊天ID（可选，NULL表示适用于所有群组）
            expires_at: 邀请码过期时间（可选，NULL表示永不过期）
            created_by: 创建者用户ID（可选）
        
        Returns:
            创建的邀请码信息
        """
        try:
            # 生成唯一邀请码
            code = self.generate_code()
            
            # 确保邀请码唯一
            while self.get_code_by_code(code):
                code = self.generate_code()
            
            # 插入数据库
            sql = """
                INSERT INTO invitation_codes 
                (code, rule_id, target_platform_id, target_chat_id, duration_days, 
                 max_uses, is_active, expires_at, created_by)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """
            code_id = self.db_pool.execute(sql, (
                code, rule_id, target_platform_id, target_chat_id,
                duration_days, max_uses, 1, expires_at, created_by
            ))
            
            logger.info(f"✅ 创建邀请码成功: {code} (规则ID: {rule_id}, 有效期: {duration_days}天)")
            
            return {
                'id': code_id,
                'code': code,
                'rule_id': rule_id,
                'duration_days': duration_days,
                'max_uses': max_uses
            }
        except Exception as e:
            logger.error(f"❌ 创建邀请码失败: {e}")
            raise
    
    def get_code_by_code(self, code: str) -> Optional[Dict[str, Any]]:
        """
        根据邀请码获取信息
        
        Args:
            code: 邀请码
        
        Returns:
            邀请码信息，如果不存在返回None
        """
        try:
            sql = """
                SELECT * FROM invitation_codes 
                WHERE code = %s
            """
            rows = self.db_pool.query(sql, (code,))
            result = dict(rows[0]) if rows else None
            return result
        except Exception as e:
            logger.error(f"查询邀请码失败: {e}")
            return None
    
    def validate_code(
        self,
        code: str,
        rule_id: Optional[str] = None,
        target_platform_id: Optional[int] = None,
        target_chat_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        验证邀请码是否有效
        
        Args:
            code: 邀请码
            rule_id: 转发规则ID（可选，用于验证是否匹配）
            target_platform_id: 目标平台ID（可选，用于验证是否匹配）
            target_chat_id: 目标聊天ID（可选，用于验证是否匹配）
        
        Returns:
            验证结果: {'valid': bool, 'message': str, 'code_info': dict}
        """
        code_info = self.get_code_by_code(code)
        
        if not code_info:
            return {
                'valid': False,
                'message': '邀请码不存在',
                'code_info': None
            }
        
        # 检查是否激活
        if not code_info.get('is_active', 0):
            return {
                'valid': False,
                'message': '邀请码已被禁用',
                'code_info': code_info
            }
        
        # 检查是否过期
        expires_at = code_info.get('expires_at')
        if expires_at:
            expires_at = datetime.fromisoformat(str(expires_at)) if isinstance(expires_at, str) else expires_at
            if datetime.now() > expires_at:
                return {
                    'valid': False,
                    'message': '邀请码已过期',
                    'code_info': code_info
                }
        
        # 检查使用次数
        max_uses = code_info.get('max_uses', 1)
        used_count = code_info.get('used_count', 0)
        if max_uses > 0 and used_count >= max_uses:
            return {
                'valid': False,
                'message': '邀请码已达到最大使用次数',
                'code_info': code_info
            }
        
        # 检查规则ID是否匹配
        if rule_id and code_info.get('rule_id') != rule_id:
            return {
                'valid': False,
                'message': '邀请码不适用于此转发规则',
                'code_info': code_info
            }
        
        # 检查目标平台ID是否匹配
        code_target_platform_id = code_info.get('target_platform_id')
        if code_target_platform_id and target_platform_id:
            if code_target_platform_id != target_platform_id:
                return {
                    'valid': False,
                    'message': '邀请码不适用于此目标平台',
                    'code_info': code_info
                }
        
        # 检查目标聊天ID是否匹配
        code_target_chat_id = code_info.get('target_chat_id')
        if code_target_chat_id and target_chat_id:
            if code_target_chat_id != target_chat_id:
                return {
                    'valid': False,
                    'message': '邀请码不适用于此群组',
                    'code_info': code_info
                }
        
        return {
            'valid': True,
            'message': '邀请码有效',
            'code_info': code_info
        }
    
    def use_code(
        self,
        code: str,
        rule_id: str,
        target_platform_id: int,
        target_chat_id: str,
        used_by: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        使用邀请码（增加使用次数）
        
        Args:
            code: 邀请码
            rule_id: 转发规则ID
            target_platform_id: 目标平台ID
            target_chat_id: 目标聊天ID
            used_by: 使用者标识（可选）
        
        Returns:
            使用结果: {'success': bool, 'message': str, 'duration_days': int}
        """
        try:
            # 验证邀请码
            validation = self.validate_code(code, rule_id, target_platform_id, target_chat_id)
            if not validation['valid']:
                return {
                    'success': False,
                    'message': validation['message'],
                    'duration_days': 0
                }
            
            code_info = validation['code_info']
            duration_days = code_info.get('duration_days', 30)
            
            # 增加使用次数
            sql = """
                UPDATE invitation_codes 
                SET used_count = used_count + 1
                WHERE code = %s
            """
            self.db_pool.execute(sql, (code,))
            
            # 记录使用历史
            usage_sql = """
                INSERT INTO invitation_code_usage 
                (code, rule_id, target_platform_id, target_chat_id, used_by, duration_days)
                VALUES (%s, %s, %s, %s, %s, %s)
            """
            usage_id = self.db_pool.execute(usage_sql, (
                code, rule_id, target_platform_id, target_chat_id, used_by, duration_days
            ))
            
            logger.info(f"✅ 邀请码使用成功: {code} (规则ID: {rule_id}, 平台ID: {target_platform_id}, 群组: {target_chat_id})")
            
            return {
                'success': True,
                'message': '邀请码使用成功',
                'duration_days': duration_days,
                'usage_id': usage_id
            }
        except Exception as e:
            logger.error(f"❌ 使用邀请码失败: {e}")
            return {
                'success': False,
                'message': f'使用邀请码失败: {str(e)}',
                'duration_days': 0
            }
    
    def get_codes_by_rule(self, rule_id: str) -> List[Dict[str, Any]]:
        """
        获取规则的所有邀请码
        
        Args:
            rule_id: 转发规则ID
        
        Returns:
            邀请码列表
        """
        try:
            sql = """
                SELECT * FROM invitation_codes 
                WHERE rule_id = %s
                ORDER BY created_at DESC
            """
            rows = self.db_pool.query(sql, (rule_id,))
            return [dict(row) for row in rows] if rows else []
        except Exception as e:
            logger.error(f"查询规则邀请码失败: {e}")
            return []
    
    def create_unique_code_for_subscription(
        self,
        rule_id: str,
        target_platform_id: int,
        target_chat_id: str,
        duration_days: int = 30,
        max_uses: int = 1,
        expires_at: Optional[datetime] = None,
        created_by: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        为特定订阅创建唯一邀请码（每个订阅一个邀请码）
        
        Args:
            rule_id: 转发规则ID
            target_platform_id: 目标平台ID
            target_chat_id: 目标聊天ID
            duration_days: 有效期天数（续订时延长的时间）
            max_uses: 最大使用次数（默认1，表示只能使用一次）
            expires_at: 邀请码过期时间（可选，NULL表示永不过期）
            created_by: 创建者用户ID（可选）
        
        Returns:
            创建的邀请码信息
        """
        try:
            # 检查是否已存在该订阅的邀请码
            existing_code = self.get_code_for_subscription(
                rule_id, target_platform_id, target_chat_id
            )
            if existing_code:
                logger.info(f"订阅已存在邀请码: {existing_code['code']}，返回现有邀请码")
                return {
                    'id': existing_code['id'],
                    'code': existing_code['code'],
                    'rule_id': rule_id,
                    'duration_days': duration_days,
                    'max_uses': max_uses,
                    'is_existing': True
                }
            
            # 创建新的唯一邀请码
            return self.create_invitation_code(
                rule_id=rule_id,
                duration_days=duration_days,
                max_uses=max_uses,
                target_platform_id=target_platform_id,
                target_chat_id=target_chat_id,
                expires_at=expires_at,
                created_by=created_by
            )
        except Exception as e:
            logger.error(f"❌ 为订阅创建邀请码失败: {e}")
            raise
    
    def get_code_for_subscription(
        self,
        rule_id: str,
        target_platform_id: int,
        target_chat_id: str
    ) -> Optional[Dict[str, Any]]:
        """
        获取特定订阅的邀请码
        
        Args:
            rule_id: 转发规则ID
            target_platform_id: 目标平台ID
            target_chat_id: 目标聊天ID
        
        Returns:
            邀请码信息，如果不存在返回None
        """
        try:
            sql = """
                SELECT * FROM invitation_codes 
                WHERE rule_id = %s 
                AND target_platform_id = %s 
                AND target_chat_id = %s
                AND is_active = 1
                ORDER BY created_at DESC
                LIMIT 1
            """
            rows = self.db_pool.query(sql, (rule_id, target_platform_id, target_chat_id))
            if rows:
                return dict(rows[0])
            return None
        except Exception as e:
            logger.error(f"查询订阅邀请码失败: {e}")
            return None
    
    def create_codes_for_all_targets(
        self,
        rule_id: str,
        target_platform_ids: List[int],
        target_chat_ids: Dict[int, List[str]],
        duration_days: int = 30,
        max_uses: int = 1,
        expires_at: Optional[datetime] = None,
        created_by: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        为规则的所有目标平台和群组批量创建唯一邀请码
        
        Args:
            rule_id: 转发规则ID
            target_platform_ids: 目标平台ID列表
            target_chat_ids: 目标聊天ID映射 {platform_id: [chat_ids]}
            duration_days: 有效期天数
            max_uses: 最大使用次数
            expires_at: 邀请码过期时间（可选）
            created_by: 创建者用户ID（可选）
        
        Returns:
            创建的邀请码列表
        """
        created_codes = []
        for platform_id in target_platform_ids:
            chat_ids = target_chat_ids.get(platform_id, ['default'])
            for chat_id in chat_ids:
                try:
                    code_info = self.create_unique_code_for_subscription(
                        rule_id=rule_id,
                        target_platform_id=platform_id,
                        target_chat_id=chat_id,
                        duration_days=duration_days,
                        max_uses=max_uses,
                        expires_at=expires_at,
                        created_by=created_by
                    )
                    created_codes.append(code_info)
                except Exception as e:
                    logger.error(f"为平台 {platform_id} 群组 {chat_id} 创建邀请码失败: {e}")
        
        logger.info(f"✅ 批量创建邀请码完成: 规则ID={rule_id}, 共创建 {len(created_codes)} 个邀请码")
        return created_codes
    
    def deactivate_code(self, code: str) -> bool:
        """
        禁用邀请码
        
        Args:
            code: 邀请码
        
        Returns:
            是否成功
        """
        try:
            sql = """
                UPDATE invitation_codes 
                SET is_active = 0
                WHERE code = %s
            """
            self.db_pool.execute(sql, (code,))
            logger.info(f"✅ 邀请码已禁用: {code}")
            return True
        except Exception as e:
            logger.error(f"❌ 禁用邀请码失败: {e}")
            return False


class SubscriptionService:
    """订阅管理服务"""
    
    def __init__(self, db):
        """
        初始化订阅服务
        
        Args:
            db: 数据库操作实例（MessageForwardDB）或数据库连接池
        """
        self.db = db
        # 获取数据库连接池
        if hasattr(db, 'db_pool'):
            self.db_pool = db.db_pool
        elif hasattr(db, '_db_pool'):
            self.db_pool = db._db_pool
        else:
            # 如果传入的就是连接池
            self.db_pool = db
        self.invitation_service = InvitationCodeService(db)
    
    def create_subscription(
        self,
        rule_id: str,
        target_platform_id: int,
        target_chat_id: str,
        duration_days: int = 30,
        start_date: Optional[datetime] = None
    ) -> Dict[str, Any]:
        """
        创建订阅
        
        Args:
            rule_id: 转发规则ID
            target_platform_id: 目标平台ID
            target_chat_id: 目标聊天ID
            duration_days: 有效期天数
            start_date: 开始时间（可选，默认当前时间）
        
        Returns:
            创建的订阅信息
        """
        try:
            if start_date is None:
                start_date = datetime.now()
            
            expire_date = start_date + timedelta(days=duration_days)
            
            # 检查是否已存在订阅
            existing = self.get_subscription(rule_id, target_platform_id, target_chat_id)
            if existing:
                # 更新现有订阅
                return self.renew_subscription(
                    rule_id, target_platform_id, target_chat_id, duration_days, None
                )
            
            # 创建新订阅
            sql = """
                INSERT INTO forward_rule_subscriptions 
                (rule_id, target_platform_id, target_chat_id, subscription_status, 
                 start_date, expire_date)
                VALUES (%s, %s, %s, %s, %s, %s)
            """
            sub_id = self.db_pool.execute(sql, (
                rule_id, target_platform_id, target_chat_id, 'active',
                start_date, expire_date
            ))
            
            logger.info(f"✅ 创建订阅成功: 规则ID={rule_id}, 平台ID={target_platform_id}, 群组={target_chat_id}, 有效期={duration_days}天")
            
            return {
                'id': sub_id,
                'rule_id': rule_id,
                'target_platform_id': target_platform_id,
                'target_chat_id': target_chat_id,
                'start_date': start_date,
                'expire_date': expire_date,
                'subscription_status': 'active'
            }
        except Exception as e:
            logger.error(f"❌ 创建订阅失败: {e}")
            raise
    
    def get_subscription(
        self,
        rule_id: str,
        target_platform_id: int,
        target_chat_id: str
    ) -> Optional[Dict[str, Any]]:
        """
        获取订阅信息
        
        Args:
            rule_id: 转发规则ID
            target_platform_id: 目标平台ID
            target_chat_id: 目标聊天ID
        
        Returns:
            订阅信息，如果不存在返回None
        """
        try:
            sql = """
                SELECT * FROM forward_rule_subscriptions 
                WHERE rule_id = %s AND target_platform_id = %s AND target_chat_id = %s
            """
            rows = self.db_pool.query(sql, (rule_id, target_platform_id, target_chat_id))
            if rows:
                return dict(rows[0])
            return None
        except Exception as e:
            logger.error(f"查询订阅失败: {e}")
            return None
    
    def renew_subscription(
        self,
        rule_id: str,
        target_platform_id: int,
        target_chat_id: str,
        duration_days: int,
        code: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        续订订阅
        
        Args:
            rule_id: 转发规则ID
            target_platform_id: 目标平台ID
            target_chat_id: 目标聊天ID
            duration_days: 续订天数
            code: 使用的邀请码（可选）
        
        Returns:
            续订结果
        """
        try:
            subscription = self.get_subscription(rule_id, target_platform_id, target_chat_id)
            
            if not subscription:
                # 如果订阅不存在，创建新订阅
                return self.create_subscription(rule_id, target_platform_id, target_chat_id, duration_days)
            
            # 计算新的过期时间
            current_expire = subscription.get('expire_date')
            if isinstance(current_expire, str):
                current_expire = datetime.fromisoformat(current_expire.replace('Z', '+00:00'))
            elif current_expire is None:
                current_expire = datetime.now()
            
            # 如果已过期，从当前时间开始续订；否则从过期时间开始续订
            if current_expire < datetime.now():
                new_expire = datetime.now() + timedelta(days=duration_days)
            else:
                new_expire = current_expire + timedelta(days=duration_days)
            
            # 更新订阅
            sql = """
                UPDATE forward_rule_subscriptions 
                SET subscription_status = 'active',
                    expire_date = %s,
                    last_renewed_at = %s,
                    last_renewed_by_code = %s,
                    total_renewals = total_renewals + 1
                WHERE rule_id = %s AND target_platform_id = %s AND target_chat_id = %s
            """
            self.db_pool.execute(sql, (
                new_expire, datetime.now(), code,
                rule_id, target_platform_id, target_chat_id
            ))
            
            logger.info(f"✅ 订阅续订成功: 规则ID={rule_id}, 平台ID={target_platform_id}, 群组={target_chat_id}, 新过期时间={new_expire}")
            
            return {
                'success': True,
                'message': '订阅续订成功',
                'expire_date': new_expire,
                'duration_days': duration_days
            }
        except Exception as e:
            logger.error(f"❌ 续订订阅失败: {e}")
            return {
                'success': False,
                'message': f'续订订阅失败: {str(e)}'
            }
    
    def check_subscription_valid(
        self,
        rule_id: str,
        target_platform_id: int,
        target_chat_id: str
    ) -> bool:
        """
        检查订阅是否有效
        
        Args:
            rule_id: 转发规则ID
            target_platform_id: 目标平台ID
            target_chat_id: 目标聊天ID
        
        Returns:
            是否有效
        """
        subscription = self.get_subscription(rule_id, target_platform_id, target_chat_id)
        
        if not subscription:
            logger.warning(f"⚠️ 订阅不存在: 规则ID={rule_id}, 平台ID={target_platform_id}, 群组={target_chat_id}")
            return False
        
        if subscription.get('subscription_status') != 'active':
            logger.warning(f"⚠️ 订阅状态不是 active: 规则ID={rule_id}, 平台ID={target_platform_id}, 群组={target_chat_id}, 状态={subscription.get('subscription_status')}")
            return False
        
        expire_date = subscription.get('expire_date')
        if expire_date:
            # 处理不同类型的日期格式
            try:
                original_expire_date = expire_date  # 保存原始值用于日志
                
                if isinstance(expire_date, str):
                    # 字符串格式，尝试多种解析方式
                    try:
                        # 方法1: 尝试解析 ISO 格式（带时间）
                        if 'T' in expire_date or ' ' in expire_date:
                            # 处理时区信息
                            if expire_date.endswith('Z'):
                                expire_date = expire_date.replace('Z', '+00:00')
                            elif '+' not in expire_date and expire_date.count(':') >= 2:
                                # 没有时区信息，假设是本地时间
                                expire_date = expire_date
                            expire_date = datetime.fromisoformat(expire_date.replace('Z', '+00:00'))
                        else:
                            # 方法2: 纯日期格式 YYYY-MM-DD
                            expire_date = datetime.strptime(expire_date, '%Y-%m-%d')
                    except ValueError:
                        # 方法3: 尝试其他常见格式
                        try:
                            # MySQL DATETIME 格式: YYYY-MM-DD HH:MM:SS
                            expire_date = datetime.strptime(expire_date, '%Y-%m-%d %H:%M:%S')
                        except ValueError:
                            try:
                                # 带微秒的格式: YYYY-MM-DD HH:MM:SS.ffffff
                                expire_date = datetime.strptime(expire_date, '%Y-%m-%d %H:%M:%S.%f')
                            except ValueError as parse_error:
                                logger.error(f"❌ 解析过期日期失败: 原始值={original_expire_date}, 类型={type(original_expire_date)}, 错误: {parse_error}")
                                # 尝试使用 dateutil 解析（如果可用）
                                try:
                                    from dateutil import parser
                                    expire_date = parser.parse(str(expire_date))
                                    logger.info(f"✅ 使用 dateutil 解析成功: {expire_date}")
                                except ImportError:
                                    logger.error("dateutil 未安装，无法使用备用解析方法")
                                    return False
                                except Exception as e:
                                    logger.error(f"❌ dateutil 解析也失败: {e}")
                                    return False
                elif isinstance(expire_date, datetime):
                    # 已经是 datetime 对象，确保是 naive datetime（无时区）
                    if expire_date.tzinfo is not None:
                        # 转换为本地时区的 naive datetime
                        expire_date = expire_date.astimezone().replace(tzinfo=None)
                else:
                    # 其他类型（可能是 date 对象或 MySQL 的 datetime 对象）
                    if hasattr(expire_date, 'date') and hasattr(expire_date, 'time'):
                        # 如果是 date 对象，转换为 datetime
                        if not hasattr(expire_date, 'hour'):  # 是 date 对象，不是 datetime
                            expire_date = datetime.combine(expire_date, datetime.min.time())
                        # 否则已经是 datetime 对象，但可能来自 MySQL
                        elif not isinstance(expire_date, datetime):
                            # MySQL 返回的 datetime 对象，转换为标准 datetime
                            expire_date = datetime(
                                expire_date.year, expire_date.month, expire_date.day,
                                expire_date.hour, expire_date.minute, expire_date.second,
                                expire_date.microsecond if hasattr(expire_date, 'microsecond') else 0
                            )
                    else:
                        logger.error(f"❌ 未知的过期日期类型: {type(expire_date)}, 值: {expire_date}")
                        return False
                
                # 确保 expire_date 是 naive datetime（无时区）
                if expire_date.tzinfo is not None:
                    expire_date = expire_date.astimezone().replace(tzinfo=None)
                
                # 获取当前时间（naive datetime，与数据库时间一致）
                now = datetime.now()
                
                # 详细日志（只在 DEBUG 级别记录，避免日志过多）
                logger.debug(f"🔍 检查订阅有效性: 规则ID={rule_id}, 平台ID={target_platform_id}, 群组={target_chat_id}")
                logger.debug(f"   过期时间: {expire_date} (类型: {type(expire_date).__name__})")
                logger.debug(f"   当前时间: {now}")
                days_left = (expire_date - now).total_seconds() / 86400
                logger.debug(f"   剩余天数: {days_left:.2f} 天")
                
                if expire_date < now:
                    # 自动更新为过期状态
                    logger.warning(f"⚠️ 订阅已过期: 规则ID={rule_id}, 平台ID={target_platform_id}, 群组={target_chat_id}, 过期时间={expire_date}, 当前时间={now}")
                    self.update_subscription_status(rule_id, target_platform_id, target_chat_id, 'expired')
                    return False
                else:
                    logger.info(f"✅ 订阅有效: 规则ID={rule_id}, 平台ID={target_platform_id}, 群组={target_chat_id}, 过期时间={expire_date}, 剩余 {days_left:.2f} 天")
            except Exception as e:
                logger.error(f"❌ 检查订阅有效性时发生错误: {e}")
                import traceback
                logger.error(traceback.format_exc())
                # 发生错误时，为了安全起见，返回 False
                return False
        
        return True
    
    def update_subscription_status(
        self,
        rule_id: str,
        target_platform_id: int,
        target_chat_id: str,
        status: str
    ) -> bool:
        """
        更新订阅状态
        
        Args:
            rule_id: 转发规则ID
            target_platform_id: 目标平台ID
            target_chat_id: 目标聊天ID
            status: 新状态（active, expired, suspended）
        
        Returns:
            是否成功
        """
        try:
            sql = """
                UPDATE forward_rule_subscriptions 
                SET subscription_status = %s
                WHERE rule_id = %s AND target_platform_id = %s AND target_chat_id = %s
            """
            self.db_pool.execute(sql, (status, rule_id, target_platform_id, target_chat_id))
            return True
        except Exception as e:
            logger.error(f"更新订阅状态失败: {e}")
            return False
    
    def process_invitation_code(
        self,
        code: str,
        rule_id: str,
        target_platform_id: int,
        target_chat_id: str,
        used_by: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        处理邀请码（验证并使用，然后续订订阅）
        
        Args:
            code: 邀请码
            rule_id: 转发规则ID
            target_platform_id: 目标平台ID
            target_chat_id: 目标聊天ID
            used_by: 使用者标识（可选）
        
        Returns:
            处理结果
        """
        try:
            # 验证邀请码
            validation = self.invitation_service.validate_code(code, rule_id, target_platform_id, target_chat_id)
            if not validation['valid']:
                return {
                    'success': False,
                    'message': validation['message']
                }
            
            code_info = validation['code_info']
            duration_days = code_info.get('duration_days', 30)
            
            # 使用邀请码
            use_result = self.invitation_service.use_code(
                code, rule_id, target_platform_id, target_chat_id, used_by
            )
            if not use_result['success']:
                return use_result
            
            # 续订订阅
            renew_result = self.renew_subscription(
                rule_id, target_platform_id, target_chat_id, duration_days, code
            )
            
            if renew_result.get('success', False):
                return {
                    'success': True,
                    'message': f'邀请码使用成功，订阅已续订 {duration_days} 天',
                    'expire_date': renew_result.get('expire_date'),
                    'duration_days': duration_days
                }
            else:
                return {
                    'success': False,
                    'message': f'邀请码使用成功，但续订失败: {renew_result.get("message", "未知错误")}'
                }
        except Exception as e:
            logger.error(f"❌ 处理邀请码失败: {e}")
            return {
                'success': False,
                'message': f'处理邀请码失败: {str(e)}'
            }
    
    def get_subscriptions_by_rule(self, rule_id: str) -> List[Dict[str, Any]]:
        """
        获取规则的所有订阅
        
        Args:
            rule_id: 转发规则ID
        
        Returns:
            订阅列表
        """
        try:
            sql = """
                SELECT * FROM forward_rule_subscriptions 
                WHERE rule_id = %s
                ORDER BY expire_date DESC
            """
            rows = self.db_pool.query(sql, (rule_id,))
            return [dict(row) for row in rows] if rows else []
        except Exception as e:
            logger.error(f"查询规则订阅失败: {e}")
            return []

