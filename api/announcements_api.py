"""
系统公告API
提供公告的CRUD接口
"""

from flask import Blueprint, request, jsonify
from database.db import get_db_pool
from utils.logger import get_logger

logger = get_logger(__name__)

# 创建Blueprint
announcements_bp = Blueprint('announcements', __name__)

# 导入权限装饰器
try:
    from auth.decorators import admin_required, get_current_user
    AUTH_AVAILABLE = True
except ImportError:
    logger.warning("认证模块不可用，公告管理将不受权限限制")
    AUTH_AVAILABLE = False
    # 创建空装饰器
    def admin_required(f):
        return f
    def get_current_user():
        return None

def get_db():
    """获取数据库连接"""
    return get_db_pool()

@announcements_bp.route('/announcements', methods=['GET'])
def get_announcements():
    """获取公告列表"""
    try:
        db_pool = get_db()
        
        # 只获取激活的、未过期的公告
        # 注意：使用 UTC 时间进行比较，确保时区正确
        sql = """
            SELECT * FROM system_announcements 
            WHERE is_active = 1 
            AND (expire_at IS NULL OR expire_at > UTC_TIMESTAMP())
            ORDER BY is_pinned DESC, priority DESC, created_at DESC
            LIMIT 50
        """
        
        announcements = db_pool.query(sql)
        
        return jsonify({
            'success': True,
            'data': announcements
        })
        
    except Exception as e:
        logger.error(f"获取公告列表失败: {e}")
        return jsonify({
            'success': False,
            'message': str(e)
        }), 500


@announcements_bp.route('/announcements/<int:announcement_id>', methods=['GET'])
def get_announcement(announcement_id):
    """获取单个公告"""
    try:
        db_pool = get_db()
        
        sql = "SELECT * FROM system_announcements WHERE id = %s"
        result = db_pool.query(sql, (announcement_id,))
        
        if not result:
            return jsonify({
                'success': False,
                'message': '公告不存在'
            }), 404
        
        return jsonify({
            'success': True,
            'data': result[0]
        })
        
    except Exception as e:
        logger.error(f"获取公告失败: {e}")
        return jsonify({
            'success': False,
            'message': str(e)
        }), 500


@announcements_bp.route('/announcements', methods=['POST'])
@admin_required
def create_announcement():
    """创建公告（仅管理员）"""
    try:
        data = request.json
        
        title = data.get('title', '').strip()
        content = data.get('content', '').strip()
        
        if not title or not content:
            return jsonify({
                'success': False,
                'message': '标题和内容不能为空'
            }), 400
        
        ann_type = data.get('type', 'info')
        priority = data.get('priority', 0)
        is_pinned = data.get('is_pinned', 0)
        
        # 获取当前登录用户信息，使用管理员姓名作为发布人
        # 注意：不依赖前端传值，后端自动获取当前登录用户
        created_by = 'admin'  # 默认值
        
        if AUTH_AVAILABLE:
            try:
                current_user = get_current_user()
                if current_user:
                    # 优先使用 full_name，如果没有则使用 username
                    created_by = current_user.get('full_name') or current_user.get('username', 'admin')
                    logger.info(f"[公告] 发布人: {created_by} (用户ID: {current_user.get('id')}, 用户名: {current_user.get('username')})")
                else:
                    logger.warning("[公告] 无法获取当前用户信息，使用默认值 'admin'")
            except Exception as e:
                logger.warning(f"[公告] 获取当前用户信息失败: {e}，使用默认值 'admin'")
                import traceback
                logger.debug(traceback.format_exc())
        else:
            logger.warning("[公告] 认证模块不可用，使用默认值 'admin'")
        
        # 如果前端传了 created_by，记录日志但不使用（安全考虑）
        if data.get('created_by'):
            logger.info(f"[公告] 前端传递了 created_by: {data.get('created_by')}，但使用后端获取的值: {created_by}")
        
        db_pool = get_db()
        
        # 使用 UTC 时间确保时区正确
        sql = """
            INSERT INTO system_announcements 
            (title, content, type, priority, is_pinned, created_by, created_at) 
            VALUES (%s, %s, %s, %s, %s, %s, UTC_TIMESTAMP())
        """
        
        announcement_id = db_pool.execute(sql, (
            title, content, ann_type, priority, is_pinned, created_by
        ))
        
        logger.info(f"创建公告成功: {title}")
        
        return jsonify({
            'success': True,
            'message': '公告创建成功',
            'data': {'id': announcement_id}
        })
        
    except Exception as e:
        logger.error(f"创建公告失败: {e}")
        return jsonify({
            'success': False,
            'message': str(e)
        }), 500


@announcements_bp.route('/announcements/<int:announcement_id>', methods=['PUT'])
@admin_required
def update_announcement(announcement_id):
    """更新公告（仅管理员）"""
    try:
        data = request.json
        
        title = data.get('title', '').strip()
        content = data.get('content', '').strip()
        
        if not title or not content:
            return jsonify({
                'success': False,
                'message': '标题和内容不能为空'
            }), 400
        
        ann_type = data.get('type', 'info')
        priority = data.get('priority', 0)
        is_pinned = data.get('is_pinned', 0)
        
        db_pool = get_db()
        
        sql = """
            UPDATE system_announcements 
            SET title = %s, content = %s, type = %s, 
                priority = %s, is_pinned = %s, updated_at = UTC_TIMESTAMP()
            WHERE id = %s
        """
        
        db_pool.execute(sql, (
            title, content, ann_type, priority, is_pinned, announcement_id
        ))
        
        logger.info(f"更新公告成功: {announcement_id}")
        
        return jsonify({
            'success': True,
            'message': '公告更新成功'
        })
        
    except Exception as e:
        logger.error(f"更新公告失败: {e}")
        return jsonify({
            'success': False,
            'message': str(e)
        }), 500


@announcements_bp.route('/announcements/<int:announcement_id>', methods=['DELETE'])
@admin_required
def delete_announcement(announcement_id):
    """删除公告（软删除，仅管理员）"""
    try:
        db_pool = get_db()
        
        # 软删除：设置为不激活
        sql = "UPDATE system_announcements SET is_active = 0 WHERE id = %s"
        db_pool.execute(sql, (announcement_id,))
        
        logger.info(f"删除公告成功: {announcement_id}")
        
        return jsonify({
            'success': True,
            'message': '公告删除成功'
        })
        
    except Exception as e:
        logger.error(f"删除公告失败: {e}")
        return jsonify({
            'success': False,
            'message': str(e)
        }), 500

