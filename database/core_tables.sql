-- =====================================================================
-- 核心业务建表脚本 (从代码内嵌 SQL 反推)
-- DB: MySQL 5.7+/8.0, ENGINE=InnoDB, CHARSET=utf8mb4
--
-- 说明:
--  * 本文件涵盖代码中引用、但原本没有任何建表脚本的所有核心表:
--    认证/权限、会员/支付、核心跟单、限价跟单、做市商、订阅/邀请码等。
--  * strategy_* 系列表见 database/strategy_tables.sql
--  * 系统公告表见 database/announcements_schema.sql
--  * 消息转发平台/规则/历史表见 database/message_forward_schema_mysql.sql
--  * 表已按外键依赖排序: 被引用的表在前。跨模块引用(如 rule_id、
--    target_platform_id)仅建索引不加外键约束, 以避免加载顺序/环境隔离问题。
--
-- 执行: mysql -u<user> -p <db> < database/core_tables.sql
-- =====================================================================

SET NAMES utf8mb4;
SET FOREIGN_KEY_CHECKS = 0;

-- =====================================================================
-- 一、认证与权限 (RBAC)  users 必须最先创建
-- =====================================================================

CREATE TABLE IF NOT EXISTS users (
    id                  BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    username            VARCHAR(100)    NOT NULL COMMENT '登录用户名',
    password_hash       VARCHAR(255)    NOT NULL COMMENT 'bcrypt 密码哈希',
    full_name           VARCHAR(100)    DEFAULT NULL COMMENT '真实姓名',
    email               VARCHAR(255)    DEFAULT NULL COMMENT '邮箱',
    role                VARCHAR(50)     NOT NULL DEFAULT 'user' COMMENT '角色代码, 关联 roles.role_code',
    status              ENUM('active','inactive') NOT NULL DEFAULT 'active' COMMENT '账号状态',
    customer_uid        VARCHAR(64)     DEFAULT NULL COMMENT '关联客户UID',
    is_password_changed TINYINT(1)      NOT NULL DEFAULT 0 COMMENT '是否已修改初始密码',
    password_changed_at DATETIME        DEFAULT NULL COMMENT '密码最后修改时间',
    last_login_at       DATETIME        DEFAULT NULL COMMENT '最后登录时间',
    last_login_ip       VARCHAR(45)     DEFAULT NULL COMMENT '最后登录IP',
    created_at          TIMESTAMP       NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at          TIMESTAMP       NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uk_users_username (username),
    KEY idx_users_role (role),
    KEY idx_users_status (status),
    KEY idx_users_customer_uid (customer_uid)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='系统用户表';

CREATE TABLE IF NOT EXISTS roles (
    id          BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    role_code   VARCHAR(50)  NOT NULL COMMENT '角色代码, 对应 users.role',
    role_name   VARCHAR(100) NOT NULL COMMENT '角色名称',
    description VARCHAR(255) DEFAULT NULL,
    created_at  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uk_roles_code (role_code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='角色定义表';

CREATE TABLE IF NOT EXISTS modules (
    id          BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    module_code VARCHAR(50)  NOT NULL COMMENT '模块代码 signal_sources/customers/strategies等',
    module_name VARCHAR(100) NOT NULL COMMENT '模块名称',
    description VARCHAR(255) DEFAULT NULL,
    created_at  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uk_modules_code (module_code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='系统模块定义表';
CREATE TABLE IF NOT EXISTS permissions (
    id               BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    module_id        BIGINT UNSIGNED NOT NULL COMMENT '关联 modules.id',
    permission_level ENUM('none','read','write','admin') NOT NULL COMMENT '权限级别',
    created_at       TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uk_permissions_module_level (module_id, permission_level),
    CONSTRAINT fk_permissions_module FOREIGN KEY (module_id) REFERENCES modules (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='模块-权限级别原子权限表';

CREATE TABLE IF NOT EXISTS role_permissions (
    id            BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    role_id       BIGINT UNSIGNED NOT NULL COMMENT '关联 roles.id',
    permission_id BIGINT UNSIGNED NOT NULL COMMENT '关联 permissions.id',
    created_at    TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uk_role_perm (role_id, permission_id),
    KEY idx_rp_permission (permission_id),
    CONSTRAINT fk_rp_role FOREIGN KEY (role_id) REFERENCES roles (id) ON DELETE CASCADE,
    CONSTRAINT fk_rp_permission FOREIGN KEY (permission_id) REFERENCES permissions (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='角色-权限关联表';

-- 用户直接权限 (init_permission_system.py 使用; grant 用 ON DUPLICATE KEY UPDATE)
CREATE TABLE IF NOT EXISTS user_permissions (
    id               BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    user_id          BIGINT UNSIGNED NOT NULL COMMENT '关联 users.id',
    module_code      VARCHAR(50)     NOT NULL COMMENT '模块代码',
    permission_level ENUM('none','read','write','admin') NOT NULL COMMENT '权限级别',
    granted_by       BIGINT UNSIGNED DEFAULT NULL COMMENT '授权人 users.id; NULL=会员等级自动同步',
    granted_at       TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '授予时间',
    expires_at       DATETIME  DEFAULT NULL COMMENT '过期时间, NULL=永久',
    PRIMARY KEY (id),
    UNIQUE KEY uk_user_module (user_id, module_code),
    KEY idx_up_module (module_code),
    KEY idx_up_granted_by (granted_by),
    KEY idx_up_expires (expires_at),
    CONSTRAINT fk_up_user FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='用户模块权限表';

-- 会话
CREATE TABLE IF NOT EXISTS sessions (
    id         BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    session_id VARCHAR(64)  NOT NULL COMMENT 'token_urlsafe 生成的会话ID',
    user_id    BIGINT UNSIGNED NOT NULL COMMENT '关联 users.id',
    token      TEXT         NOT NULL COMMENT 'JWT Token',
    created_at DATETIME     NOT NULL,
    expires_at DATETIME     NOT NULL COMMENT '会话过期时间',
    ip_address VARCHAR(45)  DEFAULT NULL,
    is_active  TINYINT(1)   NOT NULL DEFAULT 1,
    PRIMARY KEY (id),
    UNIQUE KEY uk_sessions_session_id (session_id),
    KEY idx_sessions_user (user_id),
    KEY idx_sessions_expires (expires_at),
    CONSTRAINT fk_sessions_user FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='用户会话表';

-- 登录日志
CREATE TABLE IF NOT EXISTS login_logs (
    id           BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    user_id      BIGINT UNSIGNED DEFAULT NULL COMMENT '关联 users.id, 失败时可为空',
    username     VARCHAR(100)    DEFAULT NULL COMMENT '尝试登录的用户名',
    login_ip     VARCHAR(45)     DEFAULT NULL,
    login_status ENUM('success','failed') NOT NULL COMMENT '登录结果',
    fail_reason  VARCHAR(255)    DEFAULT NULL COMMENT '失败原因',
    created_at   TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    KEY idx_login_logs_user (user_id),
    KEY idx_login_logs_username (username),
    KEY idx_login_logs_created (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='登录日志表';
-- =====================================================================
-- 二、会员与支付
-- =====================================================================

CREATE TABLE IF NOT EXISTS membership_levels (
    id                     BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    level_code             VARCHAR(50)  NOT NULL COMMENT '等级代码, 如 free',
    level_name             VARCHAR(100) NOT NULL COMMENT '等级名称',
    level_order            INT          NOT NULL DEFAULT 0 COMMENT '等级排序',
    price_monthly          DECIMAL(10,2) NOT NULL DEFAULT 0.00 COMMENT '月度价格',
    price_yearly           DECIMAL(10,2) NOT NULL DEFAULT 0.00 COMMENT '年度价格',
    max_customers          INT NOT NULL DEFAULT 0 COMMENT '最大客户数, 0=无限制',
    max_strategies         INT NOT NULL DEFAULT 0 COMMENT '最大策略数, 0=无限制',
    max_backtests_per_day  INT NOT NULL DEFAULT 0 COMMENT '每日最大回测次数, 0=无限制',
    max_forward_rules      INT NOT NULL DEFAULT 0 COMMENT '最大转发规则数, 0=无限制',
    is_active              TINYINT(1) NOT NULL DEFAULT 1 COMMENT '是否启用',
    description            VARCHAR(255) DEFAULT NULL,
    created_at             TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at             TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uk_ml_code (level_code),
    KEY idx_ml_order (level_order)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='会员等级表';

CREATE TABLE IF NOT EXISTS membership_level_permissions (
    id               BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    level_id         BIGINT UNSIGNED NOT NULL COMMENT '关联 membership_levels.id',
    module_code      VARCHAR(50)     NOT NULL COMMENT '模块代码',
    permission_level ENUM('none','read','write','admin') NOT NULL COMMENT '该等级对模块的权限级别',
    PRIMARY KEY (id),
    UNIQUE KEY uk_mlp_level_module (level_id, module_code),
    KEY idx_mlp_module (module_code),
    CONSTRAINT fk_mlp_level FOREIGN KEY (level_id) REFERENCES membership_levels (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='会员等级模块权限表';

CREATE TABLE IF NOT EXISTS user_memberships (
    id         BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    user_id    BIGINT UNSIGNED NOT NULL COMMENT '关联 users.id',
    level_id   BIGINT UNSIGNED NOT NULL COMMENT '关联 membership_levels.id',
    started_at DATETIME  NOT NULL COMMENT '会员开始时间',
    expires_at DATETIME  DEFAULT NULL COMMENT '到期时间, NULL=永久(免费会员)',
    status     ENUM('active','cancelled','expired') NOT NULL DEFAULT 'active' COMMENT '会员状态',
    auto_renew TINYINT(1) NOT NULL DEFAULT 0 COMMENT '是否自动续费',
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    KEY idx_um_user_status (user_id, status),
    KEY idx_um_level (level_id),
    KEY idx_um_expires (expires_at),
    CONSTRAINT fk_um_user FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE,
    CONSTRAINT fk_um_level FOREIGN KEY (level_id) REFERENCES membership_levels (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='用户会员关系表';

-- 会员订单 (membership_service, order_no 前缀 MEM)
CREATE TABLE IF NOT EXISTS membership_orders (
    id             BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    order_no       VARCHAR(64)  NOT NULL COMMENT '订单号, 前缀 MEM',
    user_id        BIGINT UNSIGNED NOT NULL COMMENT '关联 users.id',
    level_id       BIGINT UNSIGNED NOT NULL COMMENT '关联 membership_levels.id',
    billing_period ENUM('monthly','yearly') NOT NULL COMMENT '计费周期',
    amount         DECIMAL(10,2) NOT NULL COMMENT '订单金额',
    payment_method VARCHAR(50)  DEFAULT NULL COMMENT '支付方式',
    status         ENUM('pending','paid','cancelled','expired','failed') NOT NULL DEFAULT 'pending' COMMENT '订单状态',
    expires_at     DATETIME     DEFAULT NULL COMMENT '会员到期时间',
    created_at     TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at     TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uk_mo_order_no (order_no),
    KEY idx_mo_user (user_id),
    KEY idx_mo_level (level_id),
    CONSTRAINT fk_mo_user FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE,
    CONSTRAINT fk_mo_level FOREIGN KEY (level_id) REFERENCES membership_levels (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='会员订单表(简单版)';
-- 支付订单 (order_service, order_no 前缀 PAY, 含链上/支付回调字段)
CREATE TABLE IF NOT EXISTS membership_payment_orders (
    id                  BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    order_no            VARCHAR(64)  NOT NULL COMMENT '订单号, 前缀 PAY',
    user_id             BIGINT UNSIGNED NOT NULL COMMENT '关联 users.id',
    membership_level_id BIGINT UNSIGNED NOT NULL COMMENT '关联 membership_levels.id',
    order_type          ENUM('subscribe','renew') NOT NULL COMMENT '订单类型',
    billing_period      ENUM('monthly','yearly') NOT NULL COMMENT '计费周期',
    original_amount     DECIMAL(10,2) NOT NULL COMMENT '原始金额(USD)',
    discount_amount     DECIMAL(10,2) NOT NULL DEFAULT 0.00 COMMENT '优惠金额',
    final_amount        DECIMAL(10,2) NOT NULL COMMENT '最终应付金额',
    payment_method      ENUM('usdt_trc20','alipay','binance') NOT NULL COMMENT '支付方式',
    payment_amount      DECIMAL(18,6) NOT NULL COMMENT '实际支付金额(按币种换算)',
    payment_currency    VARCHAR(10)  NOT NULL COMMENT '支付币种',
    discount_code       VARCHAR(64)  DEFAULT NULL COMMENT '使用的优惠码',
    status              ENUM('pending','paid','expired','cancelled','failed') NOT NULL DEFAULT 'pending' COMMENT '订单状态',
    payment_tx_hash     VARCHAR(128) DEFAULT NULL COMMENT '链上交易哈希',
    payment_tx_id       VARCHAR(128) DEFAULT NULL COMMENT '第三方支付交易ID',
    payment_proof       VARCHAR(512) DEFAULT NULL COMMENT '支付凭证/浏览器链接',
    callback_data       JSON         DEFAULT NULL COMMENT '支付回调原始数据',
    expires_at          DATETIME     DEFAULT NULL COMMENT '订单过期时间',
    paid_at             DATETIME     DEFAULT NULL COMMENT '支付完成时间',
    created_at          TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at          TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uk_mpo_order_no (order_no),
    KEY idx_mpo_user (user_id),
    KEY idx_mpo_level (membership_level_id),
    KEY idx_mpo_status (status),
    KEY idx_mpo_tx_hash (payment_tx_hash),
    CONSTRAINT fk_mpo_user FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE,
    CONSTRAINT fk_mpo_level FOREIGN KEY (membership_level_id) REFERENCES membership_levels (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='会员支付订单表';

CREATE TABLE IF NOT EXISTS payment_listener_logs (
    id            BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    order_no      VARCHAR(64)  NOT NULL COMMENT '关联订单号',
    listener_type VARCHAR(50)  NOT NULL COMMENT '监听器类型',
    action        VARCHAR(64)  NOT NULL COMMENT '动作',
    status        VARCHAR(32)  NOT NULL COMMENT '结果 success/failed',
    message       TEXT         DEFAULT NULL COMMENT '日志信息',
    data          JSON         DEFAULT NULL COMMENT '附加数据',
    created_at    TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    KEY idx_pll_order_no (order_no),
    KEY idx_pll_created (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='支付监听日志表';

-- 交易所API兑换码 (telegram_bot/redemption_code_service)
CREATE TABLE IF NOT EXISTS exchange_api_redemption_codes (
    id          BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    code        VARCHAR(64)  NOT NULL COMMENT '兑换码',
    exchange    VARCHAR(32)  NOT NULL COMMENT '交易所类型 okx/binance',
    description VARCHAR(255) DEFAULT NULL COMMENT '备注',
    user_id     BIGINT UNSIGNED DEFAULT NULL COMMENT '使用者 users.id, NULL=未使用',
    used_at     DATETIME     DEFAULT NULL COMMENT '使用时间',
    is_active   TINYINT(1)   NOT NULL DEFAULT 1 COMMENT '是否启用',
    expires_at  DATETIME     DEFAULT NULL COMMENT '过期时间, NULL=永不过期',
    created_by  BIGINT UNSIGNED DEFAULT NULL COMMENT '创建者 users.id',
    created_at  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uk_earc_code (code),
    KEY idx_earc_exchange (exchange),
    KEY idx_earc_user (user_id),
    KEY idx_earc_created_by (created_by)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='交易所API兑换码表';
-- =====================================================================
-- 三、核心跟单 (市价跟单)
--   所有 *_uid 主键均为 uuid4().hex (32位十六进制), 用 VARCHAR(64)
--   is_demo 用于实盘/模拟盘环境隔离
-- =====================================================================

-- 信号源账户
CREATE TABLE IF NOT EXISTS signal_sources (
    source_uid          VARCHAR(64)   NOT NULL COMMENT '信号源UID',
    name                VARCHAR(255)  NOT NULL COMMENT '信号源名称',
    api_key             VARCHAR(255)  NULL COMMENT '交易所API Key',
    api_secret          VARCHAR(255)  NULL COMMENT '交易所API Secret',
    passphrase          VARCHAR(255)  NULL COMMENT '交易所API Passphrase',
    exchange            VARCHAR(32)   NOT NULL DEFAULT 'OKX' COMMENT '交易所',
    enabled             TINYINT(1)    NOT NULL DEFAULT 1 COMMENT '是否启用',
    init_assets         DECIMAL(20,8) NULL COMMENT '初始资产',
    total_assets        DECIMAL(20,8) NULL COMMENT '当前总资产',
    leverage            INT           NULL DEFAULT 1 COMMENT '当前杠杆倍率',
    is_demo             TINYINT(1)    NULL COMMENT '是否模拟盘',
    unique_name         VARCHAR(255)  NULL COMMENT '唯一名称(关联限价跟单trader)',
    stop_loss_percent   DECIMAL(20,8) NULL COMMENT '止损百分比',
    recently_assets     DECIMAL(20,8) NULL COMMENT '最近资产(止损前)',
    last_stop_loss_time DATETIME      NULL COMMENT '上次止损时间',
    stop_loss_count     INT           NULL DEFAULT 0 COMMENT '止损次数',
    created_at          DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    PRIMARY KEY (source_uid),
    KEY idx_ss_enabled (enabled),
    KEY idx_ss_is_demo (is_demo),
    KEY idx_ss_unique_name (unique_name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='信号源账户';

-- 客户账户
CREATE TABLE IF NOT EXISTS customers (
    customer_uid        VARCHAR(64)   NOT NULL COMMENT '客户UID',
    name                VARCHAR(255)  NOT NULL COMMENT '客户名称',
    api_key             VARCHAR(255)  NULL COMMENT '交易所API Key',
    api_secret          VARCHAR(255)  NULL COMMENT '交易所API Secret',
    passphrase          VARCHAR(255)  NULL COMMENT '交易所API Passphrase',
    exchange            VARCHAR(32)   NOT NULL DEFAULT 'OKX' COMMENT '交易所',
    enabled             TINYINT(1)    NOT NULL DEFAULT 1 COMMENT '是否启用',
    init_asset          DECIMAL(20,8) NOT NULL DEFAULT 0 COMMENT '初始资产',
    trading_asset       DECIMAL(20,8) NULL COMMENT '开仓资产(为空则用init_asset)',
    total_asset         DECIMAL(20,8) NOT NULL DEFAULT 0 COMMENT '当前总资产',
    leverage            INT           NULL DEFAULT 1 COMMENT '当前杠杆倍率',
    is_demo             TINYINT(1)    NULL COMMENT '是否模拟盘',
    owner_user_id       BIGINT UNSIGNED NULL COMMENT '所属用户ID(权限系统)',
    stop_loss_percent   DECIMAL(20,8) NULL COMMENT '止损百分比',
    stop_loss_enabled   TINYINT(1)    NULL DEFAULT 0 COMMENT '是否启用止损',
    recently_assets     DECIMAL(20,8) NULL COMMENT '最近资产(止损前)',
    last_stop_loss_time DATETIME      NULL COMMENT '上次止损时间',
    stop_loss_count     INT           NULL DEFAULT 0 COMMENT '止损次数',
    created_at          DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    PRIMARY KEY (customer_uid),
    KEY idx_c_enabled (enabled),
    KEY idx_c_is_demo (is_demo),
    KEY idx_c_owner (owner_user_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='客户账户';

-- 策略
CREATE TABLE IF NOT EXISTS strategies (
    strategy_uid      VARCHAR(64)  NOT NULL COMMENT '策略UID',
    name              VARCHAR(255) NOT NULL COMMENT '策略名称',
    signal_source_uid VARCHAR(64)  NULL COMMENT '关联信号源UID(遗留; 多对多见 strategy_signal_source)',
    enabled           TINYINT(1)   NOT NULL DEFAULT 1 COMMENT '是否启用',
    created_at        DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    PRIMARY KEY (strategy_uid),
    KEY idx_s_enabled (enabled),
    KEY idx_s_signal_source (signal_source_uid)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='策略';

-- 规则 (rule_uid 常等于 source_uid 用于信号源-规则一一对应)
CREATE TABLE IF NOT EXISTS rules (
    rule_uid       VARCHAR(64)   NOT NULL COMMENT '规则UID(部分场景=source_uid)',
    strategy_uid   VARCHAR(64)   NOT NULL COMMENT '所属策略UID',
    name           VARCHAR(255)  NULL COMMENT '规则名称',
    position_ratio DECIMAL(20,8) NOT NULL DEFAULT 0 COMMENT '仓位比例',
    max_leverage   DECIMAL(20,8) NOT NULL DEFAULT 10 COMMENT '最大杠杆',
    enabled        TINYINT(1)    NOT NULL DEFAULT 1 COMMENT '是否启用',
    PRIMARY KEY (rule_uid),
    KEY idx_r_strategy (strategy_uid),
    KEY idx_r_enabled (enabled)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='规则';

-- 策略-信号源 多对多 (代码中同时用 source_uid 与 signal_source_uid 两列, 均保留)
CREATE TABLE IF NOT EXISTS strategy_signal_source (
    id                BIGINT      NOT NULL AUTO_INCREMENT,
    strategy_uid      VARCHAR(64) NOT NULL COMMENT '策略UID',
    source_uid        VARCHAR(64) NULL COMMENT '信号源UID(主用列)',
    signal_source_uid VARCHAR(64) NULL COMMENT '信号源UID(部分JOIN使用)',
    enabled           TINYINT(1)  NOT NULL DEFAULT 1 COMMENT '是否启用',
    PRIMARY KEY (id),
    KEY idx_sss_strategy (strategy_uid),
    KEY idx_sss_source (source_uid),
    KEY idx_sss_signal_source (signal_source_uid),
    KEY idx_sss_enabled (enabled)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='策略-信号源关联';

-- 客户-策略 多对多
CREATE TABLE IF NOT EXISTS customer_strategy (
    id           BIGINT      NOT NULL AUTO_INCREMENT,
    customer_uid VARCHAR(64) NOT NULL COMMENT '客户UID',
    strategy_uid VARCHAR(64) NOT NULL COMMENT '策略UID',
    enabled      TINYINT(1)  NOT NULL DEFAULT 1 COMMENT '是否启用',
    PRIMARY KEY (id),
    KEY idx_cs_customer (customer_uid),
    KEY idx_cs_strategy (strategy_uid),
    KEY idx_cs_enabled (enabled)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='客户-策略关联';

-- 客户-规则 多对多
CREATE TABLE IF NOT EXISTS customer_rule (
    id           BIGINT      NOT NULL AUTO_INCREMENT,
    customer_uid VARCHAR(64) NOT NULL COMMENT '客户UID',
    rule_uid     VARCHAR(64) NOT NULL COMMENT '规则UID',
    enabled      TINYINT(1)  NOT NULL DEFAULT 1 COMMENT '是否启用',
    PRIMARY KEY (id),
    KEY idx_cr_customer (customer_uid),
    KEY idx_cr_rule (rule_uid),
    KEY idx_cr_enabled (enabled)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='客户-规则关联';
-- 信号源资产快照
CREATE TABLE IF NOT EXISTS signal_account_assets (
    asset_uid         VARCHAR(64)   NOT NULL COMMENT '资产快照UID',
    signal_source_uid VARCHAR(64)   NOT NULL COMMENT '信号源UID',
    asset             DECIMAL(20,8) NOT NULL COMMENT '资产值',
    snapshot_time     DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '快照时间',
    PRIMARY KEY (asset_uid),
    KEY idx_saa_source_time (signal_source_uid, snapshot_time)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='信号源资产快照';

-- 信号源成交记录
CREATE TABLE IF NOT EXISTS signal_account_trades (
    trade_uid             VARCHAR(64)   NOT NULL COMMENT '成交UID',
    signal_source_uid     VARCHAR(64)   NOT NULL COMMENT '信号源UID',
    symbol                VARCHAR(64)   NOT NULL COMMENT '交易对',
    direction             VARCHAR(16)   NULL COMMENT '买卖方向 buy/sell',
    pos_side              VARCHAR(16)   NULL COMMENT '持仓方向 long/short',
    volume                DECIMAL(20,8) NULL COMMENT '名义价值(USDT)',
    volume_contract       DECIMAL(20,8) NULL COMMENT '合约张数',
    close_volume_contract DECIMAL(20,8) NULL COMMENT '已平合约张数',
    order_id              VARCHAR(64)   NULL COMMENT '开仓订单ID',
    close_order_id        VARCHAR(64)   NULL COMMENT '平仓订单ID',
    trade_type            VARCHAR(16)   NULL COMMENT '交易类型 open/manual',
    open_px               DECIMAL(20,8) NULL COMMENT '开仓均价',
    close_px              DECIMAL(20,8) NULL COMMENT '平仓均价',
    profit                DECIMAL(20,8) NULL COMMENT '盈亏',
    status                VARCHAR(16)   NOT NULL DEFAULT 'open' COMMENT '状态 open/closed',
    execution_type        VARCHAR(32)   NULL DEFAULT 'auto' COMMENT '执行类型',
    execution_reason      TEXT          NULL COMMENT '执行原因',
    is_demo               TINYINT(1)    NULL COMMENT '是否模拟盘',
    created_at            DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    closed_at             DATETIME      NULL COMMENT '平仓时间',
    PRIMARY KEY (trade_uid),
    KEY idx_sat_source (signal_source_uid),
    KEY idx_sat_symbol (symbol),
    KEY idx_sat_status (status),
    KEY idx_sat_is_demo (is_demo),
    KEY idx_sat_order (order_id),
    KEY idx_sat_close_order (close_order_id),
    KEY idx_sat_lookup (signal_source_uid, symbol, pos_side, is_demo, status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='信号源成交记录';

-- 客户跟单成交记录
CREATE TABLE IF NOT EXISTS customer_trades (
    trade_uid             VARCHAR(64)   NOT NULL COMMENT '跟单UID',
    customer_uid          VARCHAR(64)   NOT NULL COMMENT '客户UID',
    strategy_uid          VARCHAR(64)   NULL COMMENT '策略UID',
    rule_uid              VARCHAR(64)   NULL COMMENT '规则UID',
    symbol                VARCHAR(64)   NOT NULL COMMENT '交易对',
    volume                DECIMAL(20,8) NULL COMMENT '名义价值(USDT)',
    volume_contract       DECIMAL(20,8) NULL COMMENT '合约张数',
    close_volume_contract DECIMAL(20,8) NULL COMMENT '已平合约张数',
    direction             VARCHAR(16)   NULL COMMENT '买卖方向 buy/sell',
    pos_side              VARCHAR(16)   NULL COMMENT '持仓方向 long/short',
    order_id              VARCHAR(64)   NULL COMMENT '开仓订单ID',
    close_order_id        VARCHAR(64)   NULL COMMENT '平仓订单ID',
    open_px               DECIMAL(20,8) NULL COMMENT '开仓均价',
    close_px              DECIMAL(20,8) NULL COMMENT '平仓均价',
    profit                DECIMAL(20,8) NULL COMMENT '盈亏',
    clOrdId               VARCHAR(64)   NULL COMMENT '客户端订单ID',
    parent_ordId          VARCHAR(64)   NULL COMMENT '父订单ID',
    parent_clOrdId        VARCHAR(64)   NULL COMMENT '父客户端订单ID',
    split_ratio           DECIMAL(20,8) NULL COMMENT '分摊比例',
    status                VARCHAR(16)   NOT NULL DEFAULT 'open' COMMENT '状态 open/closed',
    execution_type        VARCHAR(32)   NULL DEFAULT 'auto' COMMENT '执行类型',
    execution_reason      TEXT          NULL COMMENT '执行原因',
    parent_operation_id   VARCHAR(64)   NULL COMMENT '父操作ID',
    is_demo               TINYINT(1)    NULL COMMENT '是否模拟盘',
    created_at            DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    closed_at             DATETIME      NULL COMMENT '平仓时间',
    PRIMARY KEY (trade_uid),
    KEY idx_ct_customer (customer_uid),
    KEY idx_ct_strategy (strategy_uid),
    KEY idx_ct_rule (rule_uid),
    KEY idx_ct_symbol (symbol),
    KEY idx_ct_status (status),
    KEY idx_ct_is_demo (is_demo),
    KEY idx_ct_close_order (close_order_id),
    KEY idx_ct_parent_ord (parent_ordId),
    KEY idx_ct_lookup (customer_uid, symbol, pos_side, status, is_demo)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='客户跟单成交记录';

-- 跟单失败记录
CREATE TABLE IF NOT EXISTS trade_failures (
    failure_uid        VARCHAR(64) NOT NULL COMMENT '失败记录UID',
    customer_trade_uid VARCHAR(64) NULL COMMENT '关联客户跟单UID',
    reason             TEXT        NULL COMMENT '失败原因',
    created_at         DATETIME    NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    PRIMARY KEY (failure_uid),
    KEY idx_tf_customer_trade (customer_trade_uid)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='跟单失败记录';
-- =====================================================================
-- 四、限价跟单
-- =====================================================================

-- 带单员(信号源/交易员)主表
CREATE TABLE IF NOT EXISTS limit_follow_traders (
    id                 BIGINT       NOT NULL AUTO_INCREMENT,
    unique_name        VARCHAR(64)  NOT NULL COMMENT '带单员唯一标识',
    name               VARCHAR(128) NOT NULL DEFAULT '' COMMENT '带单员显示名称',
    description        VARCHAR(512) DEFAULT NULL COMMENT '描述',
    enabled            TINYINT(1)   NOT NULL DEFAULT 1 COMMENT '是否启用',
    collector_type     VARCHAR(32)  NOT NULL DEFAULT 'okx' COMMENT '采集器类型 okx/binance/hyperliquid/echosync',
    collector_config   JSON         DEFAULT NULL COMMENT '采集器配置',
    is_public          TINYINT(1)   NOT NULL DEFAULT 1 COMMENT '是否公开带单员',
    created_by_user_id BIGINT UNSIGNED DEFAULT NULL COMMENT '创建者用户ID(权限系统)',
    created_at         DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    updated_at         DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    PRIMARY KEY (id),
    UNIQUE KEY uk_unique_name (unique_name),
    KEY idx_lft_enabled (enabled),
    KEY idx_lft_created_by (created_by_user_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='限价跟单带单员';

-- 限价跟单策略
CREATE TABLE IF NOT EXISTS limit_follow_strategies (
    id                          BIGINT        NOT NULL AUTO_INCREMENT,
    strategy_name               VARCHAR(128)  NOT NULL DEFAULT '' COMMENT '策略名称',
    trader_unique_name          VARCHAR(64)   NOT NULL DEFAULT '' COMMENT '带单员唯一标识',
    customer_uid                VARCHAR(64)   DEFAULT NULL COMMENT '客户UID(向后兼容, 多客户见关联表)',
    symbol                      VARCHAR(32)   NOT NULL DEFAULT '' COMMENT '交易对; SPECIFIC 表示用 symbols',
    symbols                     JSON          DEFAULT NULL COMMENT '指定交易对列表',
    pos_side                    VARCHAR(8)    NOT NULL DEFAULT 'both' COMMENT '持仓方向 long/short/both',
    follow_type                 VARCHAR(16)   NOT NULL DEFAULT 'percentage' COMMENT '跟单类型 percentage/fixed',
    follow_mode                 VARCHAR(32)   NOT NULL DEFAULT 'follow_signal_source' COMMENT '跟单模式',
    follow_order_types          VARCHAR(16)   NOT NULL DEFAULT 'limit_only' COMMENT '订单类型 limit_only/market_only/both',
    limit_market_ratio          VARCHAR(16)   NOT NULL DEFAULT '1:1' COMMENT '限价:市价比例',
    follow_value                DECIMAL(20,8) NOT NULL DEFAULT 0 COMMENT '跟单值',
    min_follow_value            DECIMAL(20,8) NOT NULL DEFAULT 0.5 COMMENT '最小跟单值',
    max_follow_value            DECIMAL(20,8) NOT NULL DEFAULT 5.0 COMMENT '最大跟单值',
    max_orders_per_signal       INT           NOT NULL DEFAULT 4 COMMENT '每信号最大挂单数',
    leverage                    INT           NOT NULL DEFAULT 10 COMMENT '杠杆倍数',
    max_net_leverage            DECIMAL(20,8) NOT NULL DEFAULT 1.5 COMMENT '最大净杠杆',
    proportional_position       TINYINT(1)    NOT NULL DEFAULT 0 COMMENT '是否按比例开仓',
    auto_cancel_on_signal_close TINYINT(1)    NOT NULL DEFAULT 1 COMMENT '信号源平仓时自动撤单',
    enabled                     TINYINT(1)    NOT NULL DEFAULT 1 COMMENT '是否启用',
    strategy_group_id           BIGINT        DEFAULT NULL COMMENT '策略分组ID',
    created_by_user_id          BIGINT UNSIGNED DEFAULT NULL COMMENT '创建者用户ID(权限系统)',
    created_at                  DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    updated_at                  DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    PRIMARY KEY (id),
    KEY idx_lfs_trader (trader_unique_name),
    KEY idx_lfs_customer (customer_uid),
    KEY idx_lfs_symbol (symbol),
    KEY idx_lfs_enabled (enabled),
    KEY idx_lfs_follow_mode (follow_mode),
    KEY idx_lfs_created_by (created_by_user_id),
    KEY idx_lfs_signal_lookup (trader_unique_name, symbol, enabled)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='限价跟单策略';

-- 策略-客户 多对多(含自定义杠杆/跟单值)
CREATE TABLE IF NOT EXISTS limit_follow_strategy_customers (
    id                  BIGINT        NOT NULL AUTO_INCREMENT,
    strategy_id         BIGINT        NOT NULL COMMENT '策略ID',
    customer_uid        VARCHAR(64)   NOT NULL COMMENT '客户UID',
    enabled             TINYINT(1)    NOT NULL DEFAULT 1 COMMENT '是否启用',
    custom_leverage     INT           DEFAULT NULL COMMENT '客户自定义杠杆',
    custom_follow_value DECIMAL(20,8) DEFAULT NULL COMMENT '客户自定义跟单值',
    created_at          DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    updated_at          DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    PRIMARY KEY (id),
    UNIQUE KEY uk_lfsc_strategy_customer (strategy_id, customer_uid),
    KEY idx_lfsc_customer (customer_uid),
    KEY idx_lfsc_enabled (enabled),
    CONSTRAINT fk_lfsc_strategy FOREIGN KEY (strategy_id) REFERENCES limit_follow_strategies (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='限价跟单策略-客户关联';

-- 限价跟单订单
CREATE TABLE IF NOT EXISTS limit_follow_orders (
    id                 BIGINT        NOT NULL AUTO_INCREMENT,
    order_uid          VARCHAR(64)   NOT NULL COMMENT '订单唯一标识',
    strategy_id        BIGINT        NOT NULL DEFAULT 0 COMMENT '策略ID',
    trader_unique_name VARCHAR(64)   NOT NULL DEFAULT '' COMMENT '带单员唯一标识',
    customer_uid       VARCHAR(64)   NOT NULL DEFAULT '' COMMENT '客户UID',
    symbol             VARCHAR(32)   NOT NULL DEFAULT '' COMMENT '交易对',
    pos_side           VARCHAR(8)    NOT NULL DEFAULT 'long' COMMENT '持仓方向',
    follow_value       DECIMAL(20,8) NOT NULL DEFAULT 0 COMMENT '跟单值',
    target_price       DECIMAL(20,8) NOT NULL DEFAULT 0 COMMENT '目标挂单价格',
    order_size         DECIMAL(20,8) NOT NULL DEFAULT 0 COMMENT '下单数量',
    order_type         VARCHAR(16)   NOT NULL DEFAULT 'limit' COMMENT '订单类型 limit/market',
    status             VARCHAR(16)   NOT NULL DEFAULT 'pending' COMMENT '状态',
    signal_order_id    VARCHAR(64)   DEFAULT NULL COMMENT '来源信号订单ID',
    order_id           VARCHAR(64)   DEFAULT NULL COMMENT '本地订单ID',
    exchange_order_id  VARCHAR(64)   DEFAULT NULL COMMENT '交易所订单ID',
    close_order_id     VARCHAR(64)   DEFAULT NULL COMMENT '平仓订单ID',
    filled_price       DECIMAL(20,8) DEFAULT NULL COMMENT '成交价格',
    filled_size        DECIMAL(20,8) DEFAULT NULL COMMENT '成交数量',
    limit_close_size   DECIMAL(20,8) NOT NULL DEFAULT 0 COMMENT '累计已平仓数量',
    reduce_only        TINYINT(1)    NOT NULL DEFAULT 0 COMMENT '是否只减仓',
    created_at         DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    updated_at         DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    PRIMARY KEY (id),
    UNIQUE KEY uk_lfo_order_uid (order_uid),
    KEY idx_lfo_strategy (strategy_id),
    KEY idx_lfo_trader (trader_unique_name),
    KEY idx_lfo_customer (customer_uid),
    KEY idx_lfo_symbol (symbol),
    KEY idx_lfo_status (status),
    KEY idx_lfo_exchange_order (exchange_order_id),
    KEY idx_lfo_signal_order (signal_order_id),
    KEY idx_lfo_cust_sym_side (customer_uid, symbol, pos_side)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='限价跟单订单';

-- 限价跟单执行记录
CREATE TABLE IF NOT EXISTS limit_follow_executions (
    id                 BIGINT      NOT NULL AUTO_INCREMENT,
    execution_uid      VARCHAR(64) NOT NULL COMMENT '执行记录唯一标识',
    strategy_id        BIGINT      NOT NULL DEFAULT 0 COMMENT '策略ID',
    order_uid          VARCHAR(64) NOT NULL DEFAULT '' COMMENT '关联订单UID',
    trader_unique_name VARCHAR(64) NOT NULL DEFAULT '' COMMENT '带单员唯一标识',
    customer_uid       VARCHAR(64) NOT NULL DEFAULT '' COMMENT '客户UID',
    symbol             VARCHAR(32) NOT NULL DEFAULT '' COMMENT '交易对',
    pos_side           VARCHAR(8)  NOT NULL DEFAULT 'long' COMMENT '持仓方向',
    execution_type     VARCHAR(32) NOT NULL DEFAULT 'order_placement' COMMENT '执行类型',
    execution_status   VARCHAR(16) NOT NULL DEFAULT 'pending' COMMENT '执行状态',
    execution_data     JSON        DEFAULT NULL COMMENT '执行数据',
    error_message      TEXT        DEFAULT NULL COMMENT '错误信息',
    retry_count        INT         NOT NULL DEFAULT 0 COMMENT '重试次数',
    created_at         DATETIME    NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    updated_at         DATETIME    NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    PRIMARY KEY (id),
    UNIQUE KEY uk_lfe_execution_uid (execution_uid),
    KEY idx_lfe_strategy (strategy_id),
    KEY idx_lfe_order (order_uid),
    KEY idx_lfe_customer (customer_uid),
    KEY idx_lfe_status (execution_status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='限价跟单执行记录';

-- 限价跟单配置
CREATE TABLE IF NOT EXISTS limit_follow_configs (
    id           BIGINT       NOT NULL AUTO_INCREMENT,
    config_key   VARCHAR(128) NOT NULL COMMENT '配置键',
    config_value TEXT         DEFAULT NULL COMMENT '配置值',
    config_type  VARCHAR(16)  NOT NULL DEFAULT 'string' COMMENT '值类型 string/int/float/bool/json',
    description  VARCHAR(255) DEFAULT NULL COMMENT '配置说明',
    customer_uid VARCHAR(64)  DEFAULT NULL COMMENT '客户UID(客户级配置)',
    enabled      TINYINT(1)   NOT NULL DEFAULT 1 COMMENT '是否启用',
    created_at   DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    updated_at   DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    PRIMARY KEY (id),
    UNIQUE KEY uk_lfc_config_key (config_key),
    KEY idx_lfc_customer (customer_uid),
    KEY idx_lfc_enabled (enabled)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='限价跟单配置';

-- 限价跟单日志
CREATE TABLE IF NOT EXISTS limit_follow_logs (
    id                 BIGINT      NOT NULL AUTO_INCREMENT,
    log_level          VARCHAR(16) NOT NULL DEFAULT 'INFO' COMMENT '日志级别',
    message            TEXT        NOT NULL COMMENT '日志消息',
    order_uid          VARCHAR(64) DEFAULT NULL COMMENT '关联订单UID',
    strategy_id        BIGINT      DEFAULT NULL COMMENT '关联策略ID',
    customer_uid       VARCHAR(64) DEFAULT NULL COMMENT '客户UID',
    trader_unique_name VARCHAR(64) DEFAULT NULL COMMENT '带单员唯一标识',
    extra_data         JSON        DEFAULT NULL COMMENT '附加数据',
    created_at         DATETIME    NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    PRIMARY KEY (id),
    KEY idx_lfl_level (log_level),
    KEY idx_lfl_order (order_uid),
    KEY idx_lfl_strategy (strategy_id),
    KEY idx_lfl_created (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='限价跟单日志';

-- 带单员成交记录(采集/跟随交易员模式)
CREATE TABLE IF NOT EXISTS trader_trades (
    id                    BIGINT        NOT NULL AUTO_INCREMENT,
    trade_uid             VARCHAR(64)   NOT NULL COMMENT '成交唯一标识',
    trader_unique_name    VARCHAR(64)   NOT NULL COMMENT '带单员唯一标识',
    symbol                VARCHAR(32)   NOT NULL COMMENT '交易对',
    direction             VARCHAR(8)    DEFAULT NULL COMMENT '买卖方向 buy/sell',
    pos_side              VARCHAR(8)    NOT NULL COMMENT '持仓方向 long/short',
    volume                DECIMAL(20,8) NOT NULL DEFAULT 0 COMMENT '开仓量(USDT)',
    volume_contract       DECIMAL(20,8) NOT NULL DEFAULT 0 COMMENT '开仓量(合约张数)',
    order_id              VARCHAR(64)   DEFAULT NULL COMMENT '开仓订单ID',
    trade_type            VARCHAR(16)   NOT NULL DEFAULT 'open' COMMENT '操作类型 open/close',
    open_px               DECIMAL(20,8) NOT NULL DEFAULT 0 COMMENT '开仓均价',
    status                VARCHAR(16)   NOT NULL DEFAULT 'open' COMMENT '状态 open/closed',
    close_volume_contract DECIMAL(20,8) DEFAULT NULL COMMENT '已平仓量(合约张数)',
    close_px              DECIMAL(20,8) DEFAULT NULL COMMENT '平仓均价',
    close_order_id        VARCHAR(64)   DEFAULT NULL COMMENT '平仓订单ID',
    profit                DECIMAL(20,8) DEFAULT NULL COMMENT '盈亏',
    closed_at             DATETIME      DEFAULT NULL COMMENT '平仓时间',
    created_at            DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    PRIMARY KEY (id),
    UNIQUE KEY uk_tt_trade_uid (trade_uid),
    KEY idx_tt_trader_lookup (trader_unique_name, symbol, pos_side, status),
    KEY idx_tt_order (order_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='带单员成交记录';
-- =====================================================================
-- 五、做市商 (Market Maker)
-- =====================================================================

CREATE TABLE IF NOT EXISTS market_maker_accounts (
    id                 BIGINT       NOT NULL AUTO_INCREMENT,
    account_name       VARCHAR(100) NOT NULL COMMENT '账号名称(全局唯一)',
    user_id            BIGINT UNSIGNED NOT NULL COMMENT '所属用户ID',
    exchange           VARCHAR(50)  NOT NULL DEFAULT 'backpack' COMMENT '交易所',
    market_type        VARCHAR(20)  NOT NULL DEFAULT 'spot' COMMENT '市场类型 spot/perp',
    api_key            VARCHAR(255) DEFAULT '' COMMENT 'API Key',
    api_secret         VARCHAR(255) DEFAULT '' COMMENT 'API Secret',
    base_url           VARCHAR(255) DEFAULT 'https://api.backpack.work' COMMENT 'API基础URL',
    ws_proxy           VARCHAR(255) NULL COMMENT 'WebSocket代理地址',
    symbols            JSON         NULL COMMENT '交易对列表',
    params             JSON         NULL COMMENT '做市参数配置',
    enabled            TINYINT(1)   NOT NULL DEFAULT 1 COMMENT '是否启用',
    created_by_user_id BIGINT UNSIGNED NULL COMMENT '创建者用户ID',
    created_at         DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    updated_at         DATETIME     NULL DEFAULT NULL ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    PRIMARY KEY (id),
    UNIQUE KEY uk_mma_account_name (account_name),
    KEY idx_mma_user (user_id),
    KEY idx_mma_user_enabled (user_id, enabled)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='做市账号表';

CREATE TABLE IF NOT EXISTS market_maker_status (
    id            BIGINT       NOT NULL AUTO_INCREMENT,
    account_name  VARCHAR(100) NOT NULL COMMENT '账号名称',
    symbol        VARCHAR(50)  NOT NULL COMMENT '交易对',
    status        VARCHAR(20)  NOT NULL DEFAULT 'stopped' COMMENT '运行状态 running/stopped/error',
    process_id    INT          NULL COMMENT '进程ID',
    start_time    DATETIME     NULL COMMENT '启动时间',
    stop_time     DATETIME     NULL COMMENT '停止时间',
    error_message TEXT         NULL COMMENT '错误信息',
    last_update   DATETIME     NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '最后更新时间',
    PRIMARY KEY (id),
    UNIQUE KEY uk_mms_account_symbol (account_name, symbol),
    KEY idx_mms_status (status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='做市账号运行状态表';

CREATE TABLE IF NOT EXISTS market_maker_stats (
    id                BIGINT        NOT NULL AUTO_INCREMENT,
    account_name      VARCHAR(100)  NOT NULL COMMENT '账号名称',
    symbol            VARCHAR(50)   NOT NULL COMMENT '交易对',
    date              DATE          NOT NULL COMMENT '统计日期',
    buy_volume        DECIMAL(20,8) NOT NULL DEFAULT 0 COMMENT '买入成交量',
    sell_volume       DECIMAL(20,8) NOT NULL DEFAULT 0 COMMENT '卖出成交量',
    maker_buy_volume  DECIMAL(20,8) NOT NULL DEFAULT 0 COMMENT 'Maker买入量',
    maker_sell_volume DECIMAL(20,8) NOT NULL DEFAULT 0 COMMENT 'Maker卖出量',
    taker_buy_volume  DECIMAL(20,8) NOT NULL DEFAULT 0 COMMENT 'Taker买入量',
    taker_sell_volume DECIMAL(20,8) NOT NULL DEFAULT 0 COMMENT 'Taker卖出量',
    realized_profit   DECIMAL(20,8) NOT NULL DEFAULT 0 COMMENT '已实现利润',
    total_fees        DECIMAL(20,8) NOT NULL DEFAULT 0 COMMENT '总手续费',
    net_profit        DECIMAL(20,8) NOT NULL DEFAULT 0 COMMENT '净利润',
    trade_count       INT           NOT NULL DEFAULT 0 COMMENT '成交笔数',
    created_at        DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    updated_at        DATETIME      NULL DEFAULT NULL ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    PRIMARY KEY (id),
    UNIQUE KEY uk_mmst_account_symbol_date (account_name, symbol, date),
    KEY idx_mmst_date (date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='做市账号每日统计表';

-- =====================================================================
-- 六、订阅 / 邀请码 / Telegram 绑定 (消息转发相关, rule_id 关联 message_forward_rules)
-- =====================================================================

CREATE TABLE IF NOT EXISTS invitation_codes (
    id                 BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    code               VARCHAR(32)  NOT NULL COMMENT '邀请码',
    rule_id            VARCHAR(64)  NOT NULL COMMENT '转发规则ID',
    target_platform_id BIGINT       DEFAULT NULL COMMENT '目标平台ID, NULL=所有目标平台',
    target_chat_id     VARCHAR(128) DEFAULT NULL COMMENT '目标聊天ID, NULL=所有群组',
    duration_days      INT          NOT NULL DEFAULT 30 COMMENT '续订天数',
    max_uses           INT          NOT NULL DEFAULT 1 COMMENT '最大使用次数, 0=无限制',
    used_count         INT          NOT NULL DEFAULT 0 COMMENT '已使用次数',
    is_active          TINYINT(1)   NOT NULL DEFAULT 1 COMMENT '是否启用',
    expires_at         DATETIME     DEFAULT NULL COMMENT '过期时间, NULL=永不过期',
    created_by         BIGINT UNSIGNED DEFAULT NULL COMMENT '创建者 users.id',
    created_at         TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at         TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uk_ic_code (code),
    KEY idx_ic_rule (rule_id),
    KEY idx_ic_target (rule_id, target_platform_id, target_chat_id),
    KEY idx_ic_created_by (created_by)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='转发规则邀请码表';

CREATE TABLE IF NOT EXISTS invitation_code_usage (
    id                 BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    code               VARCHAR(32)  NOT NULL COMMENT '使用的邀请码',
    rule_id            VARCHAR(64)  NOT NULL COMMENT '转发规则ID',
    target_platform_id BIGINT       NOT NULL COMMENT '目标平台ID',
    target_chat_id     VARCHAR(128) NOT NULL COMMENT '目标聊天ID',
    used_by            VARCHAR(128) DEFAULT NULL COMMENT '使用者标识',
    duration_days      INT          NOT NULL DEFAULT 30 COMMENT '本次续订天数',
    used_at            TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '使用时间',
    PRIMARY KEY (id),
    KEY idx_icu_code (code),
    KEY idx_icu_rule (rule_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='邀请码使用记录表';

CREATE TABLE IF NOT EXISTS forward_rule_subscriptions (
    id                   BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    rule_id              VARCHAR(64)  NOT NULL COMMENT '转发规则ID',
    target_platform_id   BIGINT       NOT NULL COMMENT '目标平台ID',
    target_chat_id       VARCHAR(128) NOT NULL COMMENT '目标聊天ID',
    subscription_status  ENUM('active','expired','suspended') NOT NULL DEFAULT 'active' COMMENT '订阅状态',
    start_date           DATETIME     DEFAULT NULL COMMENT '开始时间',
    expire_date          DATETIME     DEFAULT NULL COMMENT '到期时间',
    last_renewed_at      DATETIME     DEFAULT NULL COMMENT '最后续订时间',
    last_renewed_by_code VARCHAR(32)  DEFAULT NULL COMMENT '最后续订使用的邀请码',
    total_renewals       INT          NOT NULL DEFAULT 0 COMMENT '累计续订次数',
    created_at           TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at           TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uk_frs_rule_target (rule_id, target_platform_id, target_chat_id),
    KEY idx_frs_status_expire (subscription_status, expire_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='转发规则订阅表(按目标群组)';

CREATE TABLE IF NOT EXISTS telegram_user_subscriptions (
    id                  BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    user_id             BIGINT       NOT NULL COMMENT 'Telegram用户ID',
    username            VARCHAR(128) DEFAULT NULL COMMENT '用户名',
    rule_id             VARCHAR(64)  NOT NULL COMMENT '转发规则ID',
    source_platform_id  BIGINT       DEFAULT NULL COMMENT '源平台ID, NULL=所有TradingView平台',
    target_platform_id  BIGINT       NOT NULL COMMENT '目标平台ID',
    intervals           JSON         DEFAULT NULL COMMENT '时间周期过滤列表',
    strategies          JSON         DEFAULT NULL COMMENT '策略过滤列表',
    subscription_status ENUM('active','cancelled','expired') NOT NULL DEFAULT 'active' COMMENT '订阅状态',
    start_date          DATETIME     DEFAULT NULL COMMENT '开始时间',
    expire_date         DATETIME     DEFAULT NULL COMMENT '到期时间',
    messages_received   INT          NOT NULL DEFAULT 0 COMMENT '已接收消息数',
    last_message_at     DATETIME     DEFAULT NULL COMMENT '最后接收消息时间',
    created_at          TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at          TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uk_tus_user_rule (user_id, rule_id),
    KEY idx_tus_rule (rule_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='Telegram用户订阅表';

CREATE TABLE IF NOT EXISTS telegram_user_sessions (
    id            BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    user_id       BIGINT      NOT NULL COMMENT 'Telegram用户ID',
    current_state VARCHAR(50) NOT NULL DEFAULT 'main_menu' COMMENT '当前状态',
    context_data  TEXT        NULL COMMENT '上下文数据(JSON, 含导航栈)',
    created_at    TIMESTAMP   NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at    TIMESTAMP   NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uk_tusess_user (user_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='Telegram用户会话状态表';

CREATE TABLE IF NOT EXISTS telegram_bot_user_bindings (
    id                BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    telegram_user_id  BIGINT       NOT NULL COMMENT 'Telegram用户ID',
    telegram_username VARCHAR(128) DEFAULT NULL COMMENT 'Telegram用户名',
    platform_user_id  BIGINT UNSIGNED NOT NULL COMMENT '关联 users.id',
    created_at        TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uk_tbub_telegram_user (telegram_user_id),
    UNIQUE KEY uk_tbub_platform_user (platform_user_id),
    CONSTRAINT fk_tbub_user FOREIGN KEY (platform_user_id) REFERENCES users (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='Telegram账号绑定表';

-- 自动跟单转发配置 (telegram_bot 创建)
CREATE TABLE IF NOT EXISTS forward_trade_configs (
    id                   BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    config_name          VARCHAR(255)  NOT NULL COMMENT '配置名称',
    user_id              BIGINT UNSIGNED NOT NULL COMMENT '所属用户ID',
    source_platform_id   BIGINT        NULL COMMENT '源平台ID',
    source_platform_name VARCHAR(255)  NULL COMMENT '源平台名称',
    customer_uid         VARCHAR(64)   NULL COMMENT '关联 customers.customer_uid',
    customer_name        VARCHAR(255)  NULL COMMENT '客户名称',
    amount_ratio         DECIMAL(10,4) NOT NULL DEFAULT 0.0000 COMMENT '金额比例',
    enabled              TINYINT(1)    NOT NULL DEFAULT 1 COMMENT '是否启用',
    created_by_user_id   BIGINT UNSIGNED NULL COMMENT '创建者用户ID',
    created_at           TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at           TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uk_ftc_config_name (config_name),
    KEY idx_ftc_user (user_id),
    KEY idx_ftc_customer (customer_uid)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='自动跟单转发配置表';

-- =====================================================================
-- 七、微信公众号用户 (wechat_official)
-- =====================================================================

CREATE TABLE IF NOT EXISTS wechat_official_users (
    id                  BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    openid              VARCHAR(64)  NOT NULL COMMENT '微信OpenID',
    nickname            VARCHAR(255) NULL COMMENT '昵称',
    headimgurl          VARCHAR(512) NULL COMMENT '头像URL',
    sex                 TINYINT      NULL COMMENT '性别',
    city                VARCHAR(100) NULL COMMENT '城市',
    province            VARCHAR(100) NULL COMMENT '省份',
    country             VARCHAR(100) NULL COMMENT '国家',
    language            VARCHAR(20)  NULL DEFAULT 'zh_CN' COMMENT '语言',
    subscribe           TINYINT(1)   NOT NULL DEFAULT 0 COMMENT '是否关注',
    subscribe_time      DATETIME     NULL COMMENT '关注时间',
    unsubscribe_time    DATETIME     NULL COMMENT '取消关注时间',
    status              VARCHAR(20)  NOT NULL DEFAULT 'active' COMMENT '状态',
    last_interaction_at DATETIME     NULL COMMENT '最后交互时间',
    created_at          TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at          TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uk_wou_openid (openid),
    KEY idx_wou_subscribe_status (subscribe, status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='微信公众号用户表';

CREATE TABLE IF NOT EXISTS wechat_official_subscriptions (
    id                BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    user_id           BIGINT UNSIGNED NOT NULL COMMENT '关联 wechat_official_users.id',
    openid            VARCHAR(64)  NOT NULL COMMENT '微信OpenID',
    subscription_type VARCHAR(50)  NOT NULL COMMENT '订阅类型 trade/alert/system/signal',
    enabled           TINYINT(1)   NOT NULL DEFAULT 1 COMMENT '是否启用',
    config            TEXT         NULL COMMENT '配置(JSON)',
    created_at        TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at        TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uk_wos_user_subtype (user_id, subscription_type),
    KEY idx_wos_openid (openid),
    KEY idx_wos_type (subscription_type)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='微信公众号订阅表';

CREATE TABLE IF NOT EXISTS wechat_official_message_logs (
    id                BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    user_id           BIGINT UNSIGNED NULL COMMENT '关联用户ID',
    openid            VARCHAR(64)  NULL COMMENT '微信OpenID',
    message_type      VARCHAR(50)  NULL COMMENT '消息类型',
    subscription_type VARCHAR(50)  NULL COMMENT '订阅类型',
    content           TEXT         NULL COMMENT '内容',
    template_id       VARCHAR(100) NULL COMMENT '模板ID',
    status            VARCHAR(20)  NOT NULL DEFAULT 'sent' COMMENT '状态',
    error_message     TEXT         NULL COMMENT '错误信息',
    sent_at           DATETIME     NULL COMMENT '发送时间',
    created_at        TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    KEY idx_woml_user (user_id),
    KEY idx_woml_openid (openid)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='微信公众号消息日志表';

-- =====================================================================
-- 八、止损 / 手动操作 / 仓位异常 / 持仓资产快照
-- =====================================================================

-- 信号源止损设置 (按策略区分)
CREATE TABLE IF NOT EXISTS signal_stop_loss (
    stop_loss_uid       VARCHAR(64)   NOT NULL COMMENT '止损设置唯一标识',
    signal_source_uid   VARCHAR(64)   NOT NULL COMMENT '信号源UID',
    strategy_uid        VARCHAR(64)   NOT NULL COMMENT '策略UID',
    stop_loss_percent   DECIMAL(20,8) NOT NULL COMMENT '止损百分比',
    stop_profit_percent DECIMAL(20,8) NOT NULL COMMENT '止盈百分比',
    enabled             TINYINT(1)    NOT NULL DEFAULT 1 COMMENT '是否启用',
    is_demo             TINYINT(1)    NOT NULL DEFAULT 1 COMMENT '是否模拟盘',
    created_at          DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    updated_at          DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    PRIMARY KEY (stop_loss_uid),
    KEY idx_ssl_source (signal_source_uid),
    KEY idx_ssl_strategy (strategy_uid),
    KEY idx_ssl_is_demo (is_demo),
    KEY idx_ssl_lookup (signal_source_uid, strategy_uid, is_demo)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='信号源止损设置';

-- 客户止损设置 (按策略区分)
CREATE TABLE IF NOT EXISTS customer_stop_loss (
    stop_loss_uid       VARCHAR(64)   NOT NULL COMMENT '止损设置唯一标识',
    customer_uid        VARCHAR(64)   NOT NULL COMMENT '客户UID',
    strategy_uid        VARCHAR(64)   NOT NULL COMMENT '策略UID',
    stop_loss_percent   DECIMAL(20,8) NOT NULL COMMENT '止损百分比',
    stop_profit_percent DECIMAL(20,8) NOT NULL COMMENT '止盈百分比',
    enabled             TINYINT(1)    NOT NULL DEFAULT 1 COMMENT '是否启用',
    is_demo             TINYINT(1)    NOT NULL DEFAULT 1 COMMENT '是否模拟盘',
    created_at          DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    updated_at          DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    PRIMARY KEY (stop_loss_uid),
    KEY idx_csl_customer (customer_uid),
    KEY idx_csl_strategy (strategy_uid),
    KEY idx_csl_is_demo (is_demo),
    KEY idx_csl_lookup (customer_uid, strategy_uid, is_demo)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='客户止损设置';

-- 手动开/平仓操作记录
CREATE TABLE IF NOT EXISTS manual_operations (
    id                BIGINT        NOT NULL AUTO_INCREMENT,
    customer_uid      VARCHAR(64)   NOT NULL COMMENT '账户UID(信号源/客户)',
    symbol            VARCHAR(64)   NOT NULL COMMENT '交易对',
    pos_side          VARCHAR(16)   NOT NULL COMMENT '持仓方向 long/short',
    operation_type    VARCHAR(16)   NOT NULL COMMENT '操作类型 open/close',
    sz                DECIMAL(20,8) DEFAULT NULL COMMENT '操作数量(张)',
    order_id          VARCHAR(64)   DEFAULT NULL COMMENT '交易所订单ID',
    reason            TEXT          DEFAULT NULL COMMENT '操作原因',
    is_demo           TINYINT(1)    NOT NULL DEFAULT 1 COMMENT '是否模拟盘',
    related_trade_uid VARCHAR(64)   DEFAULT NULL COMMENT '关联交易UID',
    execution_status  VARCHAR(32)   DEFAULT NULL COMMENT '执行状态 success/filled/canceled',
    status            VARCHAR(32)   DEFAULT NULL COMMENT '业务状态',
    created_at        DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    updated_at        DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    PRIMARY KEY (id),
    KEY idx_mo_customer (customer_uid),
    KEY idx_mo_order (order_id),
    KEY idx_mo_symbol (symbol),
    KEY idx_mo_op_type (operation_type),
    KEY idx_mo_exec_status (execution_status),
    KEY idx_mo_is_demo (is_demo),
    KEY idx_mo_created (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='手动开平仓操作记录';

-- 仓位异常检测记录
CREATE TABLE IF NOT EXISTS position_anomalies (
    id                BIGINT        NOT NULL AUTO_INCREMENT,
    customer_uid      VARCHAR(64)   NOT NULL COMMENT '客户UID',
    symbol            VARCHAR(64)   NOT NULL COMMENT '交易对',
    pos_side          VARCHAR(16)   NOT NULL COMMENT '持仓方向 long/short',
    expected_sz       DECIMAL(20,8) DEFAULT NULL COMMENT '期望张数',
    actual_sz         DECIMAL(20,8) DEFAULT NULL COMMENT '实际张数',
    difference_sz     DECIMAL(20,8) DEFAULT NULL COMMENT '差异张数',
    anomaly_type      VARCHAR(32)   DEFAULT NULL COMMENT '异常类型 overflow/underflow',
    is_demo           TINYINT(1)    NOT NULL DEFAULT 1 COMMENT '是否模拟盘',
    status            VARCHAR(16)   NOT NULL DEFAULT 'pending' COMMENT '状态 pending/resolved',
    resolution_method VARCHAR(32)   DEFAULT NULL COMMENT '修复方式',
    resolved_at       DATETIME      DEFAULT NULL COMMENT '解决时间',
    created_at        DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    PRIMARY KEY (id),
    KEY idx_pa_customer (customer_uid),
    KEY idx_pa_symbol (symbol),
    KEY idx_pa_status (status),
    KEY idx_pa_is_demo (is_demo),
    KEY idx_pa_created (created_at),
    KEY idx_pa_lookup (customer_uid, symbol, pos_side, status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='仓位异常检测记录';

-- 转发交易执行记录 (config_id 关联 forward_trade_configs.id)
CREATE TABLE IF NOT EXISTS forward_trade_records (
    id                 BIGINT        NOT NULL AUTO_INCREMENT,
    config_id          BIGINT        NOT NULL COMMENT '转发配置ID',
    message_id         VARCHAR(128)  DEFAULT NULL COMMENT '来源消息ID',
    source_platform_id VARCHAR(64)   DEFAULT NULL COMMENT '来源平台ID',
    symbol             VARCHAR(64)   NOT NULL COMMENT '交易对',
    action             VARCHAR(32)   DEFAULT NULL COMMENT '动作 open/close',
    direct             VARCHAR(16)   DEFAULT NULL COMMENT '方向 buy/sell/long/short',
    price              DECIMAL(20,8) DEFAULT NULL COMMENT '价格',
    quantity           DECIMAL(20,8) DEFAULT NULL COMMENT '数量',
    amount             DECIMAL(20,8) DEFAULT NULL COMMENT '交易金额(USDT)',
    amount_ratio       DECIMAL(20,8) DEFAULT NULL COMMENT '金额比例',
    order_id           VARCHAR(128)  DEFAULT NULL COMMENT '交易所订单ID',
    order_status       VARCHAR(32)   DEFAULT NULL COMMENT '订单状态',
    execution_status   VARCHAR(32)   NOT NULL DEFAULT 'pending' COMMENT '执行状态',
    error_message      TEXT          DEFAULT NULL COMMENT '错误信息',
    executed_at        DATETIME      DEFAULT NULL COMMENT '执行时间',
    created_at         DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    PRIMARY KEY (id),
    KEY idx_ftr_config (config_id),
    KEY idx_ftr_symbol (symbol),
    KEY idx_ftr_exec_status (execution_status),
    KEY idx_ftr_created (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='转发交易执行记录';

-- 客户持仓表 (限价跟单持仓计算)
CREATE TABLE IF NOT EXISTS customer_positions (
    id           BIGINT        NOT NULL AUTO_INCREMENT,
    customer_uid VARCHAR(64)   NOT NULL COMMENT '客户UID',
    symbol       VARCHAR(64)   NOT NULL COMMENT '交易对',
    pos          DECIMAL(20,8) NOT NULL DEFAULT 0 COMMENT '持仓张数',
    pos_side     VARCHAR(16)   NOT NULL DEFAULT 'long' COMMENT '持仓方向 long/short',
    avg_px       DECIMAL(20,8) DEFAULT 0 COMMENT '开仓均价',
    upl          DECIMAL(20,8) DEFAULT 0 COMMENT '未实现盈亏',
    margin       DECIMAL(20,8) DEFAULT 0 COMMENT '保证金',
    status       VARCHAR(16)   NOT NULL DEFAULT 'open' COMMENT '状态 open/closed',
    created_at   DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    PRIMARY KEY (id),
    KEY idx_cp_customer (customer_uid),
    KEY idx_cp_symbol (symbol),
    KEY idx_cp_status (status),
    KEY idx_cp_lookup (customer_uid, symbol, status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='客户持仓表';

-- 客户资产表
CREATE TABLE IF NOT EXISTS customer_assets (
    id                BIGINT        NOT NULL AUTO_INCREMENT,
    customer_uid      VARCHAR(64)   NOT NULL COMMENT '客户UID',
    currency          VARCHAR(16)   NOT NULL DEFAULT 'USDT' COMMENT '币种',
    total_balance     DECIMAL(20,8) NOT NULL DEFAULT 0 COMMENT '总余额',
    available_balance DECIMAL(20,8) NOT NULL DEFAULT 0 COMMENT '可用余额',
    created_at        DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    updated_at        DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    PRIMARY KEY (id),
    KEY idx_ca_customer (customer_uid),
    KEY idx_ca_lookup (customer_uid, currency)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='客户资产表';

-- 客户监控配置表 (除 customer_uid 外的列为依据默认配置字典推断)
CREATE TABLE IF NOT EXISTS customer_configs (
    id                        BIGINT        NOT NULL AUTO_INCREMENT,
    customer_uid              VARCHAR(64)   NOT NULL COMMENT '客户UID',
    check_interval            INT           DEFAULT 30 COMMENT '检查间隔(秒)',
    sync_interval             INT           DEFAULT 300 COMMENT '同步间隔(秒)',
    status_sync_interval      INT           DEFAULT 60 COMMENT '状态同步间隔(秒)',
    health_check_interval     INT           DEFAULT 120 COMMENT '健康检查间隔(秒)',
    websocket_enabled         TINYINT(1)    DEFAULT 1 COMMENT '启用WebSocket',
    auto_repair_enabled       TINYINT(1)    DEFAULT 1 COMMENT '启用自动修复',
    auto_repair_max_orders    INT           DEFAULT 3 COMMENT '自动修复最大订单数',
    stale_order_timeout       INT           DEFAULT 3600 COMMENT '过期订单超时(秒)',
    max_concurrent_checks     INT           DEFAULT 5 COMMENT '最大并发检查数',
    batch_size                INT           DEFAULT 50 COMMENT '批处理大小',
    retry_attempts            INT           DEFAULT 3 COMMENT '重试次数',
    timeout                   INT           DEFAULT 30 COMMENT '超时时间(秒)',
    api_rate_limit_delay      DECIMAL(10,3) DEFAULT 0.100 COMMENT 'API速率限制延迟(秒)',
    max_consecutive_failures  INT           DEFAULT 5 COMMENT '最大连续失败次数',
    enable_notifications      TINYINT(1)    DEFAULT 0 COMMENT '启用通知',
    created_at                DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    updated_at                DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    PRIMARY KEY (id),
    UNIQUE KEY uk_cc_customer (customer_uid)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='客户监控配置表(部分列为推断)';

SET FOREIGN_KEY_CHECKS = 1;


