-- =====================================================================
-- 消息转发模块表 (由 core/message_forward/db_operations_mysql.py 按此固定路径加载)
-- 来源: db_operations.py (sqlite DDL) + db_operations_mysql.py 实际读写字段, 转 MySQL
-- =====================================================================

-- 平台配置表
CREATE TABLE IF NOT EXISTS message_platforms (
    id                BIGINT       NOT NULL AUTO_INCREMENT COMMENT '平台ID',
    platform_type     VARCHAR(50)  NOT NULL COMMENT '平台类型 telegram/dingtalk/wechat/tradingview',
    platform_name     VARCHAR(255) NOT NULL COMMENT '平台名称',
    enabled           TINYINT(1)   NOT NULL DEFAULT 1 COMMENT '是否启用',
    config            LONGTEXT     NOT NULL COMMENT '平台配置(JSON字符串)',
    monitored_chats   TEXT         NULL COMMENT '监听的聊天列表(JSON数组)',
    status            VARCHAR(50)  NOT NULL DEFAULT 'inactive' COMMENT '连接状态',
    error_message     TEXT         NULL COMMENT '错误信息',
    last_connected_at TIMESTAMP    NULL COMMENT '最后连接时间',
    created_at        TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    updated_at        TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    PRIMARY KEY (id),
    UNIQUE KEY uk_platform_name (platform_name),
    KEY idx_platform_type (platform_type)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='消息转发-平台配置';

-- 转发规则表
CREATE TABLE IF NOT EXISTS message_forward_rules (
    id                  BIGINT       NOT NULL AUTO_INCREMENT COMMENT '规则ID',
    rule_id             VARCHAR(64)  NOT NULL COMMENT '规则唯一标识',
    rule_name           VARCHAR(255) NOT NULL COMMENT '规则名称',
    enabled             TINYINT(1)   NOT NULL DEFAULT 1 COMMENT '是否启用',
    source_platform_id  BIGINT       NULL COMMENT '源平台ID(关联 message_platforms.id)',
    source_platform     VARCHAR(50)  NOT NULL DEFAULT '' COMMENT '源平台类型',
    source_chat_ids     TEXT         NULL COMMENT '源聊天ID列表(JSON数组)',
    target_platform_ids TEXT         NULL COMMENT '目标平台ID列表(JSON数组)',
    target_platforms    TEXT         NOT NULL COMMENT '目标平台类型列表(JSON数组)',
    target_chat_ids     TEXT         NULL COMMENT '目标聊天ID(JSON对象)',
    keywords            TEXT         NULL COMMENT '关键词过滤(JSON数组)',
    exclude_keywords    TEXT         NULL COMMENT '排除关键词(JSON数组)',
    add_prefix          VARCHAR(255) NULL DEFAULT '' COMMENT '添加前缀',
    add_suffix          VARCHAR(255) NULL DEFAULT '' COMMENT '添加后缀',
    enable_markdown     TINYINT(1)   NOT NULL DEFAULT 0 COMMENT '是否启用Markdown',
    messages_forwarded  INT          NOT NULL DEFAULT 0 COMMENT '已转发消息数',
    created_at          TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    updated_at          TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    PRIMARY KEY (id),
    UNIQUE KEY uk_rule_id (rule_id),
    KEY idx_source_platform_id (source_platform_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='消息转发-转发规则';

-- 消息历史表
CREATE TABLE IF NOT EXISTS message_history (
    id                 BIGINT       NOT NULL AUTO_INCREMENT COMMENT '记录ID',
    message_id         VARCHAR(255) NOT NULL COMMENT '消息ID',
    source_platform_id BIGINT       NULL COMMENT '源平台ID',
    source_platform    VARCHAR(50)  NOT NULL COMMENT '源平台类型',
    source_chat_id     VARCHAR(255) NULL COMMENT '源聊天ID',
    source_chat_title  VARCHAR(255) NULL COMMENT '源聊天标题',
    content            TEXT         NOT NULL COMMENT '消息内容',
    forwarded_to       TEXT         NULL COMMENT '转发目标(JSON数组)',
    is_test            TINYINT(1)   NOT NULL DEFAULT 0 COMMENT '是否测试消息',
    rule_id            VARCHAR(64)  NULL COMMENT '关联规则ID',
    timestamp          TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '消息时间',
    PRIMARY KEY (id),
    KEY idx_timestamp (timestamp),
    KEY idx_source_platform_id (source_platform_id),
    KEY idx_rule_id (rule_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='消息转发-消息历史';
