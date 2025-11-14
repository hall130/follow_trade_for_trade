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
    from auth.decorators import admin_required
    AUTH_AVAILABLE = True
except ImportError:
    logger.warning("认证模块不可用，公告管理将不受权限限制")
    AUTH_AVAILABLE = False
    # 创建空装饰器
    def admin_required(f):
        return f

def get_db():
    """获取数据库连接"""
    return get_db_pool()

@announcements_bp.route('/announcements', methods=['GET'])
def get_announcements():
    """获取公告列表"""
    try:
        db_pool = get_db()
        
        # 只获取激活的、未过期的公告
        sql = """
            SELECT * FROM system_announcements 
            WHERE is_active = 1 
            AND (expire_at IS NULL OR expire_at > NOW())
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
        created_by = data.get('created_by', 'admin')
        
        db_pool = get_db()
        
        sql = """
            INSERT INTO system_announcements 
            (title, content, type, priority, is_pinned, created_by) 
            VALUES (%s, %s, %s, %s, %s, %s)
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
                priority = %s, is_pinned = %s, updated_at = NOW()
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

