-- =====================================================================
-- 系统公告表 (由 database/init_announcements.py 按此固定路径加载)
-- 来源: api/announcements_api.py 中的读写 SQL 反推
-- =====================================================================
CREATE TABLE IF NOT EXISTS system_announcements (
    id          BIGINT       NOT NULL AUTO_INCREMENT COMMENT '公告ID',
    title       VARCHAR(255) NOT NULL COMMENT '公告标题',
    content     TEXT         NOT NULL COMMENT '公告内容',
    type        VARCHAR(20)  NOT NULL DEFAULT 'info' COMMENT '公告类型 info/warning/success/error',
    priority    INT          NOT NULL DEFAULT 0 COMMENT '优先级, 数值越大越靠前',
    is_pinned   TINYINT(1)   NOT NULL DEFAULT 0 COMMENT '是否置顶',
    is_active   TINYINT(1)   NOT NULL DEFAULT 1 COMMENT '是否激活(软删除标记, 0=已删除)',
    created_by  VARCHAR(100) DEFAULT 'admin' COMMENT '发布人',
    expire_at   DATETIME     NULL COMMENT '过期时间(UTC, NULL=永不过期)',
    created_at  DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    updated_at  DATETIME     NULL DEFAULT NULL ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    PRIMARY KEY (id),
    INDEX idx_active_expire (is_active, expire_at),
    INDEX idx_pinned_priority (is_pinned, priority),
    INDEX idx_created_at (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='系统公告表';
