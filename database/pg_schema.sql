-- =====================================================================
-- PostgreSQL + TimescaleDB 建表脚本（由 mysql_to_pg.py 自动生成）
-- 源: core_tables.sql / strategy_tables.sql / announcements_schema.sql /
--     message_forward_schema_mysql.sql
-- 执行: psql -U postgres -d trade_db -f database/pg_schema.sql
-- =====================================================================

-- updated_at 自动刷新触发器函数
CREATE OR REPLACE FUNCTION set_updated_at() RETURNS trigger AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- ---- 表 ----
CREATE TABLE IF NOT EXISTS users (
    id BIGSERIAL,
    username            VARCHAR(100)    NOT NULL,
    password_hash       VARCHAR(255)    NOT NULL,
    full_name           VARCHAR(100)    DEFAULT NULL,
    email               VARCHAR(255)    DEFAULT NULL,
    role                VARCHAR(50)     NOT NULL DEFAULT 'user',
    status              VARCHAR(50) NOT NULL DEFAULT 'active',
    customer_uid        VARCHAR(64)     DEFAULT NULL,
    is_password_changed SMALLINT      NOT NULL DEFAULT 0,
    password_changed_at TIMESTAMP        DEFAULT NULL,
    last_login_at       TIMESTAMP        DEFAULT NULL,
    last_login_ip       VARCHAR(45)     DEFAULT NULL,
    created_at          TIMESTAMP       NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at          TIMESTAMP       NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id)
);
CREATE TABLE IF NOT EXISTS roles (
    id BIGSERIAL,
    role_code   VARCHAR(50)  NOT NULL,
    role_name   VARCHAR(100) NOT NULL,
    description VARCHAR(255) DEFAULT NULL,
    created_at  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id)
);
CREATE TABLE IF NOT EXISTS modules (
    id BIGSERIAL,
    module_code VARCHAR(50)  NOT NULL,
    module_name VARCHAR(100) NOT NULL,
    description VARCHAR(255) DEFAULT NULL,
    created_at  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id)
);
CREATE TABLE IF NOT EXISTS permissions (
    id BIGSERIAL,
    module_id        BIGINT NOT NULL,
    permission_level VARCHAR(50) NOT NULL,
    created_at       TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    CONSTRAINT fk_permissions_module FOREIGN KEY (module_id) REFERENCES modules (id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS role_permissions (
    id BIGSERIAL,
    role_id       BIGINT NOT NULL,
    permission_id BIGINT NOT NULL,
    created_at    TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    CONSTRAINT fk_rp_role FOREIGN KEY (role_id) REFERENCES roles (id) ON DELETE CASCADE,
    CONSTRAINT fk_rp_permission FOREIGN KEY (permission_id) REFERENCES permissions (id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS user_permissions (
    id BIGSERIAL,
    user_id          BIGINT NOT NULL,
    module_code      VARCHAR(50)     NOT NULL,
    permission_level VARCHAR(50) NOT NULL,
    granted_by       BIGINT DEFAULT NULL,
    granted_at       TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    expires_at       TIMESTAMP  DEFAULT NULL,
    PRIMARY KEY (id),
    CONSTRAINT fk_up_user FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS sessions (
    id BIGSERIAL,
    session_id VARCHAR(64)  NOT NULL,
    user_id    BIGINT NOT NULL,
    token      TEXT         NOT NULL,
    created_at TIMESTAMP     NOT NULL,
    expires_at TIMESTAMP     NOT NULL,
    ip_address VARCHAR(45)  DEFAULT NULL,
    is_active  SMALLINT   NOT NULL DEFAULT 1,
    PRIMARY KEY (id),
    CONSTRAINT fk_sessions_user FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS login_logs (
    id BIGSERIAL,
    user_id      BIGINT DEFAULT NULL,
    username     VARCHAR(100)    DEFAULT NULL,
    login_ip     VARCHAR(45)     DEFAULT NULL,
    login_status VARCHAR(50) NOT NULL,
    fail_reason  VARCHAR(255)    DEFAULT NULL,
    created_at   TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id)
);
CREATE TABLE IF NOT EXISTS membership_levels (
    id BIGSERIAL,
    level_code             VARCHAR(50)  NOT NULL,
    level_name             VARCHAR(100) NOT NULL,
    level_order            INT          NOT NULL DEFAULT 0,
    price_monthly          DECIMAL(10,2) NOT NULL DEFAULT 0.00,
    price_yearly           DECIMAL(10,2) NOT NULL DEFAULT 0.00,
    max_customers          INT NOT NULL DEFAULT 0,
    max_strategies         INT NOT NULL DEFAULT 0,
    max_backtests_per_day  INT NOT NULL DEFAULT 0,
    max_forward_rules      INT NOT NULL DEFAULT 0,
    is_active              SMALLINT NOT NULL DEFAULT 1,
    description            VARCHAR(255) DEFAULT NULL,
    created_at             TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at             TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id)
);
CREATE TABLE IF NOT EXISTS membership_level_permissions (
    id BIGSERIAL,
    level_id         BIGINT NOT NULL,
    module_code      VARCHAR(50)     NOT NULL,
    permission_level VARCHAR(50) NOT NULL,
    PRIMARY KEY (id),
    CONSTRAINT fk_mlp_level FOREIGN KEY (level_id) REFERENCES membership_levels (id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS user_memberships (
    id BIGSERIAL,
    user_id    BIGINT NOT NULL,
    level_id   BIGINT NOT NULL,
    started_at TIMESTAMP  NOT NULL,
    expires_at TIMESTAMP  DEFAULT NULL,
    status     VARCHAR(50) NOT NULL DEFAULT 'active',
    auto_renew SMALLINT NOT NULL DEFAULT 0,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    CONSTRAINT fk_um_user FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE,
    CONSTRAINT fk_um_level FOREIGN KEY (level_id) REFERENCES membership_levels (id)
);
CREATE TABLE IF NOT EXISTS membership_orders (
    id BIGSERIAL,
    order_no       VARCHAR(64)  NOT NULL,
    user_id        BIGINT NOT NULL,
    level_id       BIGINT NOT NULL,
    billing_period VARCHAR(50) NOT NULL,
    amount         DECIMAL(10,2) NOT NULL,
    payment_method VARCHAR(50)  DEFAULT NULL,
    status         VARCHAR(50) NOT NULL DEFAULT 'pending',
    expires_at     TIMESTAMP     DEFAULT NULL,
    created_at     TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at     TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    CONSTRAINT fk_mo_user FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE,
    CONSTRAINT fk_mo_level FOREIGN KEY (level_id) REFERENCES membership_levels (id)
);
CREATE TABLE IF NOT EXISTS membership_payment_orders (
    id BIGSERIAL,
    order_no            VARCHAR(64)  NOT NULL,
    user_id             BIGINT NOT NULL,
    membership_level_id BIGINT NOT NULL,
    order_type          VARCHAR(50) NOT NULL,
    billing_period      VARCHAR(50) NOT NULL,
    original_amount     DECIMAL(10,2) NOT NULL,
    discount_amount     DECIMAL(10,2) NOT NULL DEFAULT 0.00,
    final_amount        DECIMAL(10,2) NOT NULL,
    payment_method      VARCHAR(50) NOT NULL,
    payment_amount      DECIMAL(18,6) NOT NULL,
    payment_currency    VARCHAR(10)  NOT NULL,
    discount_code       VARCHAR(64)  DEFAULT NULL,
    status              VARCHAR(50) NOT NULL DEFAULT 'pending',
    payment_tx_hash     VARCHAR(128) DEFAULT NULL,
    payment_tx_id       VARCHAR(128) DEFAULT NULL,
    payment_proof       VARCHAR(512) DEFAULT NULL,
    callback_data       JSONB         DEFAULT NULL,
    expires_at          TIMESTAMP     DEFAULT NULL,
    paid_at             TIMESTAMP     DEFAULT NULL,
    created_at          TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at          TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    CONSTRAINT fk_mpo_user FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE,
    CONSTRAINT fk_mpo_level FOREIGN KEY (membership_level_id) REFERENCES membership_levels (id)
);
CREATE TABLE IF NOT EXISTS payment_listener_logs (
    id BIGSERIAL,
    order_no      VARCHAR(64)  NOT NULL,
    listener_type VARCHAR(50)  NOT NULL,
    action        VARCHAR(64)  NOT NULL,
    status        VARCHAR(32)  NOT NULL,
    message       TEXT         DEFAULT NULL,
    data          JSONB         DEFAULT NULL,
    created_at    TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id)
);
CREATE TABLE IF NOT EXISTS exchange_api_redemption_codes (
    id BIGSERIAL,
    code        VARCHAR(64)  NOT NULL,
    exchange    VARCHAR(32)  NOT NULL,
    description VARCHAR(255) DEFAULT NULL,
    user_id     BIGINT DEFAULT NULL,
    used_at     TIMESTAMP     DEFAULT NULL,
    is_active   SMALLINT   NOT NULL DEFAULT 1,
    expires_at  TIMESTAMP     DEFAULT NULL,
    created_by  BIGINT DEFAULT NULL,
    created_at  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id)
);
CREATE TABLE IF NOT EXISTS signal_sources (
    source_uid          VARCHAR(64)   NOT NULL,
    name                VARCHAR(255)  NOT NULL,
    api_key             VARCHAR(255)  NULL,
    api_secret          VARCHAR(255)  NULL,
    passphrase          VARCHAR(255)  NULL,
    exchange            VARCHAR(32)   NOT NULL DEFAULT 'OKX',
    enabled             SMALLINT    NOT NULL DEFAULT 1,
    init_assets         DECIMAL(20,8) NULL,
    total_assets        DECIMAL(20,8) NULL,
    leverage            INT           NULL DEFAULT 1,
    is_demo             SMALLINT    NULL,
    unique_name         VARCHAR(255)  NULL,
    stop_loss_percent   DECIMAL(20,8) NULL,
    recently_assets     DECIMAL(20,8) NULL,
    last_stop_loss_time TIMESTAMP      NULL,
    stop_loss_count     INT           NULL DEFAULT 0,
    created_at          TIMESTAMP      NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (source_uid)
);
CREATE TABLE IF NOT EXISTS customers (
    customer_uid        VARCHAR(64)   NOT NULL,
    name                VARCHAR(255)  NOT NULL,
    api_key             VARCHAR(255)  NULL,
    api_secret          VARCHAR(255)  NULL,
    passphrase          VARCHAR(255)  NULL,
    exchange            VARCHAR(32)   NOT NULL DEFAULT 'OKX',
    enabled             SMALLINT    NOT NULL DEFAULT 1,
    init_asset          DECIMAL(20,8) NOT NULL DEFAULT 0,
    trading_asset       DECIMAL(20,8) NULL,
    total_asset         DECIMAL(20,8) NOT NULL DEFAULT 0,
    leverage            INT           NULL DEFAULT 1,
    is_demo             SMALLINT    NULL,
    owner_user_id       BIGINT NULL,
    stop_loss_percent   DECIMAL(20,8) NULL,
    stop_loss_enabled   SMALLINT    NULL DEFAULT 0,
    recently_assets     DECIMAL(20,8) NULL,
    last_stop_loss_time TIMESTAMP      NULL,
    stop_loss_count     INT           NULL DEFAULT 0,
    created_at          TIMESTAMP      NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (customer_uid)
);
CREATE TABLE IF NOT EXISTS strategies (
    strategy_uid      VARCHAR(64)  NOT NULL,
    name              VARCHAR(255) NOT NULL,
    signal_source_uid VARCHAR(64)  NULL,
    enabled           SMALLINT   NOT NULL DEFAULT 1,
    created_at        TIMESTAMP     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (strategy_uid)
);
CREATE TABLE IF NOT EXISTS rules (
    rule_uid       VARCHAR(64)   NOT NULL,
    strategy_uid   VARCHAR(64)   NOT NULL,
    name           VARCHAR(255)  NULL,
    position_ratio DECIMAL(20,8) NOT NULL DEFAULT 0,
    max_leverage   DECIMAL(20,8) NOT NULL DEFAULT 10,
    enabled        SMALLINT    NOT NULL DEFAULT 1,
    PRIMARY KEY (rule_uid)
);
CREATE TABLE IF NOT EXISTS strategy_signal_source (
    id BIGSERIAL,
    strategy_uid      VARCHAR(64) NOT NULL,
    source_uid        VARCHAR(64) NULL,
    signal_source_uid VARCHAR(64) NULL,
    enabled           SMALLINT  NOT NULL DEFAULT 1,
    PRIMARY KEY (id)
);
CREATE TABLE IF NOT EXISTS customer_strategy (
    id BIGSERIAL,
    customer_uid VARCHAR(64) NOT NULL,
    strategy_uid VARCHAR(64) NOT NULL,
    enabled      SMALLINT  NOT NULL DEFAULT 1,
    PRIMARY KEY (id)
);
CREATE TABLE IF NOT EXISTS customer_rule (
    id BIGSERIAL,
    customer_uid VARCHAR(64) NOT NULL,
    rule_uid     VARCHAR(64) NOT NULL,
    enabled      SMALLINT  NOT NULL DEFAULT 1,
    PRIMARY KEY (id)
);
CREATE TABLE IF NOT EXISTS signal_account_assets (
    asset_uid         VARCHAR(64)   NOT NULL,
    signal_source_uid VARCHAR(64)   NOT NULL,
    asset             DECIMAL(20,8) NOT NULL,
    snapshot_time     TIMESTAMP      NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (asset_uid)
);
CREATE TABLE IF NOT EXISTS signal_account_trades (
    trade_uid             VARCHAR(64)   NOT NULL,
    signal_source_uid     VARCHAR(64)   NOT NULL,
    symbol                VARCHAR(64)   NOT NULL,
    direction             VARCHAR(16)   NULL,
    pos_side              VARCHAR(16)   NULL,
    volume                DECIMAL(20,8) NULL,
    volume_contract       DECIMAL(20,8) NULL,
    close_volume_contract DECIMAL(20,8) NULL,
    order_id              VARCHAR(64)   NULL,
    close_order_id        VARCHAR(64)   NULL,
    trade_type            VARCHAR(16)   NULL,
    open_px               DECIMAL(20,8) NULL,
    close_px              DECIMAL(20,8) NULL,
    profit                DECIMAL(20,8) NULL,
    status                VARCHAR(16)   NOT NULL DEFAULT 'open',
    execution_type        VARCHAR(32)   NULL DEFAULT 'auto',
    execution_reason      TEXT          NULL,
    is_demo               SMALLINT    NULL,
    created_at            TIMESTAMP      NOT NULL DEFAULT CURRENT_TIMESTAMP,
    closed_at             TIMESTAMP      NULL,
    PRIMARY KEY (trade_uid)
);
CREATE TABLE IF NOT EXISTS customer_trades (
    trade_uid             VARCHAR(64)   NOT NULL,
    customer_uid          VARCHAR(64)   NOT NULL,
    strategy_uid          VARCHAR(64)   NULL,
    rule_uid              VARCHAR(64)   NULL,
    symbol                VARCHAR(64)   NOT NULL,
    volume                DECIMAL(20,8) NULL,
    volume_contract       DECIMAL(20,8) NULL,
    close_volume_contract DECIMAL(20,8) NULL,
    direction             VARCHAR(16)   NULL,
    pos_side              VARCHAR(16)   NULL,
    order_id              VARCHAR(64)   NULL,
    close_order_id        VARCHAR(64)   NULL,
    open_px               DECIMAL(20,8) NULL,
    close_px              DECIMAL(20,8) NULL,
    profit                DECIMAL(20,8) NULL,
    clOrdId               VARCHAR(64)   NULL,
    parent_ordId          VARCHAR(64)   NULL,
    parent_clOrdId        VARCHAR(64)   NULL,
    split_ratio           DECIMAL(20,8) NULL,
    status                VARCHAR(16)   NOT NULL DEFAULT 'open',
    execution_type        VARCHAR(32)   NULL DEFAULT 'auto',
    execution_reason      TEXT          NULL,
    parent_operation_id   VARCHAR(64)   NULL,
    is_demo               SMALLINT    NULL,
    created_at            TIMESTAMP      NOT NULL DEFAULT CURRENT_TIMESTAMP,
    closed_at             TIMESTAMP      NULL,
    PRIMARY KEY (trade_uid)
);
CREATE TABLE IF NOT EXISTS trade_failures (
    failure_uid        VARCHAR(64) NOT NULL,
    customer_trade_uid VARCHAR(64) NULL,
    reason             TEXT        NULL,
    created_at         TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (failure_uid)
);
CREATE TABLE IF NOT EXISTS limit_follow_traders (
    id BIGSERIAL,
    unique_name        VARCHAR(64)  NOT NULL,
    name               VARCHAR(128) NOT NULL DEFAULT '',
    description        VARCHAR(512) DEFAULT NULL,
    enabled            SMALLINT   NOT NULL DEFAULT 1,
    collector_type     VARCHAR(32)  NOT NULL DEFAULT 'okx',
    collector_config   JSONB         DEFAULT NULL,
    is_public          SMALLINT   NOT NULL DEFAULT 1,
    created_by_user_id BIGINT DEFAULT NULL,
    created_at         TIMESTAMP     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at         TIMESTAMP     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id)
);
CREATE TABLE IF NOT EXISTS limit_follow_strategies (
    id BIGSERIAL,
    strategy_name               VARCHAR(128)  NOT NULL DEFAULT '',
    trader_unique_name          VARCHAR(64)   NOT NULL DEFAULT '',
    customer_uid                VARCHAR(64)   DEFAULT NULL,
    symbol                      VARCHAR(32)   NOT NULL DEFAULT '',
    symbols                     JSONB          DEFAULT NULL,
    pos_side                    VARCHAR(8)    NOT NULL DEFAULT 'both',
    follow_type                 VARCHAR(16)   NOT NULL DEFAULT 'percentage',
    follow_mode                 VARCHAR(32)   NOT NULL DEFAULT 'follow_signal_source',
    follow_order_types          VARCHAR(16)   NOT NULL DEFAULT 'limit_only',
    limit_market_ratio          VARCHAR(16)   NOT NULL DEFAULT '1:1',
    follow_value                DECIMAL(20,8) NOT NULL DEFAULT 0,
    min_follow_value            DECIMAL(20,8) NOT NULL DEFAULT 0.5,
    max_follow_value            DECIMAL(20,8) NOT NULL DEFAULT 5.0,
    max_orders_per_signal       INT           NOT NULL DEFAULT 4,
    leverage                    INT           NOT NULL DEFAULT 10,
    max_net_leverage            DECIMAL(20,8) NOT NULL DEFAULT 1.5,
    proportional_position       SMALLINT    NOT NULL DEFAULT 0,
    auto_cancel_on_signal_close SMALLINT    NOT NULL DEFAULT 1,
    enabled                     SMALLINT    NOT NULL DEFAULT 1,
    strategy_group_id           BIGINT        DEFAULT NULL,
    created_by_user_id          BIGINT DEFAULT NULL,
    created_at                  TIMESTAMP      NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at                  TIMESTAMP      NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id)
);
CREATE TABLE IF NOT EXISTS limit_follow_strategy_customers (
    id BIGSERIAL,
    strategy_id         BIGINT        NOT NULL,
    customer_uid        VARCHAR(64)   NOT NULL,
    enabled             SMALLINT    NOT NULL DEFAULT 1,
    custom_leverage     INT           DEFAULT NULL,
    custom_follow_value DECIMAL(20,8) DEFAULT NULL,
    created_at          TIMESTAMP      NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at          TIMESTAMP      NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    CONSTRAINT fk_lfsc_strategy FOREIGN KEY (strategy_id) REFERENCES limit_follow_strategies (id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS limit_follow_orders (
    id BIGSERIAL,
    order_uid          VARCHAR(64)   NOT NULL,
    strategy_id        BIGINT        NOT NULL DEFAULT 0,
    trader_unique_name VARCHAR(64)   NOT NULL DEFAULT '',
    customer_uid       VARCHAR(64)   NOT NULL DEFAULT '',
    symbol             VARCHAR(32)   NOT NULL DEFAULT '',
    pos_side           VARCHAR(8)    NOT NULL DEFAULT 'long',
    follow_value       DECIMAL(20,8) NOT NULL DEFAULT 0,
    target_price       DECIMAL(20,8) NOT NULL DEFAULT 0,
    order_size         DECIMAL(20,8) NOT NULL DEFAULT 0,
    order_type         VARCHAR(16)   NOT NULL DEFAULT 'limit',
    status             VARCHAR(16)   NOT NULL DEFAULT 'pending',
    signal_order_id    VARCHAR(64)   DEFAULT NULL,
    order_id           VARCHAR(64)   DEFAULT NULL,
    exchange_order_id  VARCHAR(64)   DEFAULT NULL,
    close_order_id     VARCHAR(64)   DEFAULT NULL,
    filled_price       DECIMAL(20,8) DEFAULT NULL,
    filled_size        DECIMAL(20,8) DEFAULT NULL,
    limit_close_size   DECIMAL(20,8) NOT NULL DEFAULT 0,
    reduce_only        SMALLINT    NOT NULL DEFAULT 0,
    created_at         TIMESTAMP      NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at         TIMESTAMP      NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id)
);
CREATE TABLE IF NOT EXISTS limit_follow_executions (
    id BIGSERIAL,
    execution_uid      VARCHAR(64) NOT NULL,
    strategy_id        BIGINT      NOT NULL DEFAULT 0,
    order_uid          VARCHAR(64) NOT NULL DEFAULT '',
    trader_unique_name VARCHAR(64) NOT NULL DEFAULT '',
    customer_uid       VARCHAR(64) NOT NULL DEFAULT '',
    symbol             VARCHAR(32) NOT NULL DEFAULT '',
    pos_side           VARCHAR(8)  NOT NULL DEFAULT 'long',
    execution_type     VARCHAR(32) NOT NULL DEFAULT 'order_placement',
    execution_status   VARCHAR(16) NOT NULL DEFAULT 'pending',
    execution_data     JSONB        DEFAULT NULL,
    error_message      TEXT        DEFAULT NULL,
    retry_count        INT         NOT NULL DEFAULT 0,
    created_at         TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at         TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id)
);
CREATE TABLE IF NOT EXISTS limit_follow_configs (
    id BIGSERIAL,
    config_key   VARCHAR(128) NOT NULL,
    config_value TEXT         DEFAULT NULL,
    config_type  VARCHAR(16)  NOT NULL DEFAULT 'string',
    description  VARCHAR(255) DEFAULT NULL,
    customer_uid VARCHAR(64)  DEFAULT NULL,
    enabled      SMALLINT   NOT NULL DEFAULT 1,
    created_at   TIMESTAMP     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at   TIMESTAMP     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id)
);
CREATE TABLE IF NOT EXISTS limit_follow_logs (
    id BIGSERIAL,
    log_level          VARCHAR(16) NOT NULL DEFAULT 'INFO',
    message            TEXT        NOT NULL,
    order_uid          VARCHAR(64) DEFAULT NULL,
    strategy_id        BIGINT      DEFAULT NULL,
    customer_uid       VARCHAR(64) DEFAULT NULL,
    trader_unique_name VARCHAR(64) DEFAULT NULL,
    extra_data         JSONB        DEFAULT NULL,
    created_at         TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id)
);
CREATE TABLE IF NOT EXISTS trader_trades (
    id BIGSERIAL,
    trade_uid             VARCHAR(64)   NOT NULL,
    trader_unique_name    VARCHAR(64)   NOT NULL,
    symbol                VARCHAR(32)   NOT NULL,
    direction             VARCHAR(8)    DEFAULT NULL,
    pos_side              VARCHAR(8)    NOT NULL,
    volume                DECIMAL(20,8) NOT NULL DEFAULT 0,
    volume_contract       DECIMAL(20,8) NOT NULL DEFAULT 0,
    order_id              VARCHAR(64)   DEFAULT NULL,
    trade_type            VARCHAR(16)   NOT NULL DEFAULT 'open',
    open_px               DECIMAL(20,8) NOT NULL DEFAULT 0,
    status                VARCHAR(16)   NOT NULL DEFAULT 'open',
    close_volume_contract DECIMAL(20,8) DEFAULT NULL,
    close_px              DECIMAL(20,8) DEFAULT NULL,
    close_order_id        VARCHAR(64)   DEFAULT NULL,
    profit                DECIMAL(20,8) DEFAULT NULL,
    closed_at             TIMESTAMP      DEFAULT NULL,
    created_at            TIMESTAMP      NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id)
);
CREATE TABLE IF NOT EXISTS market_maker_accounts (
    id BIGSERIAL,
    account_name       VARCHAR(100) NOT NULL,
    user_id            BIGINT NOT NULL,
    exchange           VARCHAR(50)  NOT NULL DEFAULT 'backpack',
    market_type        VARCHAR(20)  NOT NULL DEFAULT 'spot',
    api_key            VARCHAR(255) DEFAULT '',
    api_secret         VARCHAR(255) DEFAULT '',
    base_url           VARCHAR(255) DEFAULT 'https://api.backpack.work',
    ws_proxy           VARCHAR(255) NULL,
    symbols            JSONB         NULL,
    params             JSONB         NULL,
    enabled            SMALLINT   NOT NULL DEFAULT 1,
    created_by_user_id BIGINT NULL,
    created_at         TIMESTAMP     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at         TIMESTAMP     NULL DEFAULT NULL,
    PRIMARY KEY (id)
);
CREATE TABLE IF NOT EXISTS market_maker_status (
    id BIGSERIAL,
    account_name  VARCHAR(100) NOT NULL,
    symbol        VARCHAR(50)  NOT NULL,
    status        VARCHAR(20)  NOT NULL DEFAULT 'stopped',
    process_id    INT          NULL,
    start_time    TIMESTAMP     NULL,
    stop_time     TIMESTAMP     NULL,
    error_message TEXT         NULL,
    last_update   TIMESTAMP     NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id)
);
CREATE TABLE IF NOT EXISTS market_maker_stats (
    id BIGSERIAL,
    account_name      VARCHAR(100)  NOT NULL,
    symbol            VARCHAR(50)   NOT NULL,
    date              DATE          NOT NULL,
    buy_volume        DECIMAL(20,8) NOT NULL DEFAULT 0,
    sell_volume       DECIMAL(20,8) NOT NULL DEFAULT 0,
    maker_buy_volume  DECIMAL(20,8) NOT NULL DEFAULT 0,
    maker_sell_volume DECIMAL(20,8) NOT NULL DEFAULT 0,
    taker_buy_volume  DECIMAL(20,8) NOT NULL DEFAULT 0,
    taker_sell_volume DECIMAL(20,8) NOT NULL DEFAULT 0,
    realized_profit   DECIMAL(20,8) NOT NULL DEFAULT 0,
    total_fees        DECIMAL(20,8) NOT NULL DEFAULT 0,
    net_profit        DECIMAL(20,8) NOT NULL DEFAULT 0,
    trade_count       INT           NOT NULL DEFAULT 0,
    created_at        TIMESTAMP      NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at        TIMESTAMP      NULL DEFAULT NULL,
    PRIMARY KEY (id)
);
CREATE TABLE IF NOT EXISTS invitation_codes (
    id BIGSERIAL,
    code               VARCHAR(32)  NOT NULL,
    rule_id            VARCHAR(64)  NOT NULL,
    target_platform_id BIGINT       DEFAULT NULL,
    target_chat_id     VARCHAR(128) DEFAULT NULL,
    duration_days      INT          NOT NULL DEFAULT 30,
    max_uses           INT          NOT NULL DEFAULT 1,
    used_count         INT          NOT NULL DEFAULT 0,
    is_active          SMALLINT   NOT NULL DEFAULT 1,
    expires_at         TIMESTAMP     DEFAULT NULL,
    created_by         BIGINT DEFAULT NULL,
    created_at         TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at         TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id)
);
CREATE TABLE IF NOT EXISTS invitation_code_usage (
    id BIGSERIAL,
    code               VARCHAR(32)  NOT NULL,
    rule_id            VARCHAR(64)  NOT NULL,
    target_platform_id BIGINT       NOT NULL,
    target_chat_id     VARCHAR(128) NOT NULL,
    used_by            VARCHAR(128) DEFAULT NULL,
    duration_days      INT          NOT NULL DEFAULT 30,
    used_at            TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id)
);
CREATE TABLE IF NOT EXISTS forward_rule_subscriptions (
    id BIGSERIAL,
    rule_id              VARCHAR(64)  NOT NULL,
    target_platform_id   BIGINT       NOT NULL,
    target_chat_id       VARCHAR(128) NOT NULL,
    subscription_status  VARCHAR(50) NOT NULL DEFAULT 'active',
    start_date           TIMESTAMP     DEFAULT NULL,
    expire_date          TIMESTAMP     DEFAULT NULL,
    last_renewed_at      TIMESTAMP     DEFAULT NULL,
    last_renewed_by_code VARCHAR(32)  DEFAULT NULL,
    total_renewals       INT          NOT NULL DEFAULT 0,
    created_at           TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at           TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id)
);
CREATE TABLE IF NOT EXISTS telegram_user_subscriptions (
    id BIGSERIAL,
    user_id             BIGINT       NOT NULL,
    username            VARCHAR(128) DEFAULT NULL,
    rule_id             VARCHAR(64)  NOT NULL,
    source_platform_id  BIGINT       DEFAULT NULL,
    target_platform_id  BIGINT       NOT NULL,
    intervals           JSONB         DEFAULT NULL,
    strategies          JSONB         DEFAULT NULL,
    subscription_status VARCHAR(50) NOT NULL DEFAULT 'active',
    start_date          TIMESTAMP     DEFAULT NULL,
    expire_date         TIMESTAMP     DEFAULT NULL,
    messages_received   INT          NOT NULL DEFAULT 0,
    last_message_at     TIMESTAMP     DEFAULT NULL,
    created_at          TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at          TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id)
);
CREATE TABLE IF NOT EXISTS telegram_user_sessions (
    id BIGSERIAL,
    user_id       BIGINT      NOT NULL,
    current_state VARCHAR(50) NOT NULL DEFAULT 'main_menu',
    context_data  TEXT        NULL,
    created_at    TIMESTAMP   NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at    TIMESTAMP   NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id)
);
CREATE TABLE IF NOT EXISTS telegram_bot_user_bindings (
    id BIGSERIAL,
    telegram_user_id  BIGINT       NOT NULL,
    telegram_username VARCHAR(128) DEFAULT NULL,
    platform_user_id  BIGINT NOT NULL,
    created_at        TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    CONSTRAINT fk_tbub_user FOREIGN KEY (platform_user_id) REFERENCES users (id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS forward_trade_configs (
    id BIGSERIAL,
    config_name          VARCHAR(255)  NOT NULL,
    user_id              BIGINT NOT NULL,
    source_platform_id   BIGINT        NULL,
    source_platform_name VARCHAR(255)  NULL,
    customer_uid         VARCHAR(64)   NULL,
    customer_name        VARCHAR(255)  NULL,
    amount_ratio         DECIMAL(10,4) NOT NULL DEFAULT 0.0000,
    enabled              SMALLINT    NOT NULL DEFAULT 1,
    created_by_user_id   BIGINT NULL,
    created_at           TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at           TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id)
);
CREATE TABLE IF NOT EXISTS wechat_official_users (
    id BIGSERIAL,
    openid              VARCHAR(64)  NOT NULL,
    nickname            VARCHAR(255) NULL,
    headimgurl          VARCHAR(512) NULL,
    sex                 SMALLINT      NULL,
    city                VARCHAR(100) NULL,
    province            VARCHAR(100) NULL,
    country             VARCHAR(100) NULL,
    language            VARCHAR(20)  NULL DEFAULT 'zh_CN',
    subscribe           SMALLINT   NOT NULL DEFAULT 0,
    subscribe_time      TIMESTAMP     NULL,
    unsubscribe_time    TIMESTAMP     NULL,
    status              VARCHAR(20)  NOT NULL DEFAULT 'active',
    last_interaction_at TIMESTAMP     NULL,
    created_at          TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at          TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id)
);
CREATE TABLE IF NOT EXISTS wechat_official_subscriptions (
    id BIGSERIAL,
    user_id           BIGINT NOT NULL,
    openid            VARCHAR(64)  NOT NULL,
    subscription_type VARCHAR(50)  NOT NULL,
    enabled           SMALLINT   NOT NULL DEFAULT 1,
    config            TEXT         NULL,
    created_at        TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at        TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id)
);
CREATE TABLE IF NOT EXISTS wechat_official_message_logs (
    id BIGSERIAL,
    user_id           BIGINT NULL,
    openid            VARCHAR(64)  NULL,
    message_type      VARCHAR(50)  NULL,
    subscription_type VARCHAR(50)  NULL,
    content           TEXT         NULL,
    template_id       VARCHAR(100) NULL,
    status            VARCHAR(20)  NOT NULL DEFAULT 'sent',
    error_message     TEXT         NULL,
    sent_at           TIMESTAMP     NULL,
    created_at        TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id)
);
CREATE TABLE IF NOT EXISTS signal_stop_loss (
    stop_loss_uid       VARCHAR(64)   NOT NULL,
    signal_source_uid   VARCHAR(64)   NOT NULL,
    strategy_uid        VARCHAR(64)   NOT NULL,
    stop_loss_percent   DECIMAL(20,8) NOT NULL,
    stop_profit_percent DECIMAL(20,8) NOT NULL,
    enabled             SMALLINT    NOT NULL DEFAULT 1,
    is_demo             SMALLINT    NOT NULL DEFAULT 1,
    created_at          TIMESTAMP      NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at          TIMESTAMP      NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (stop_loss_uid)
);
CREATE TABLE IF NOT EXISTS customer_stop_loss (
    stop_loss_uid       VARCHAR(64)   NOT NULL,
    customer_uid        VARCHAR(64)   NOT NULL,
    strategy_uid        VARCHAR(64)   NOT NULL,
    stop_loss_percent   DECIMAL(20,8) NOT NULL,
    stop_profit_percent DECIMAL(20,8) NOT NULL,
    enabled             SMALLINT    NOT NULL DEFAULT 1,
    is_demo             SMALLINT    NOT NULL DEFAULT 1,
    created_at          TIMESTAMP      NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at          TIMESTAMP      NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (stop_loss_uid)
);
CREATE TABLE IF NOT EXISTS manual_operations (
    id BIGSERIAL,
    customer_uid      VARCHAR(64)   NOT NULL,
    symbol            VARCHAR(64)   NOT NULL,
    pos_side          VARCHAR(16)   NOT NULL,
    operation_type    VARCHAR(16)   NOT NULL,
    sz                DECIMAL(20,8) DEFAULT NULL,
    order_id          VARCHAR(64)   DEFAULT NULL,
    reason            TEXT          DEFAULT NULL,
    is_demo           SMALLINT    NOT NULL DEFAULT 1,
    related_trade_uid VARCHAR(64)   DEFAULT NULL,
    execution_status  VARCHAR(32)   DEFAULT NULL,
    status            VARCHAR(32)   DEFAULT NULL,
    created_at        TIMESTAMP      NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at        TIMESTAMP      NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id)
);
CREATE TABLE IF NOT EXISTS position_anomalies (
    id BIGSERIAL,
    customer_uid      VARCHAR(64)   NOT NULL,
    symbol            VARCHAR(64)   NOT NULL,
    pos_side          VARCHAR(16)   NOT NULL,
    expected_sz       DECIMAL(20,8) DEFAULT NULL,
    actual_sz         DECIMAL(20,8) DEFAULT NULL,
    difference_sz     DECIMAL(20,8) DEFAULT NULL,
    anomaly_type      VARCHAR(32)   DEFAULT NULL,
    is_demo           SMALLINT    NOT NULL DEFAULT 1,
    status            VARCHAR(16)   NOT NULL DEFAULT 'pending',
    resolution_method VARCHAR(32)   DEFAULT NULL,
    resolved_at       TIMESTAMP      DEFAULT NULL,
    created_at        TIMESTAMP      NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id)
);
CREATE TABLE IF NOT EXISTS forward_trade_records (
    id BIGSERIAL,
    config_id          BIGINT        NOT NULL,
    message_id         VARCHAR(128)  DEFAULT NULL,
    source_platform_id VARCHAR(64)   DEFAULT NULL,
    symbol             VARCHAR(64)   NOT NULL,
    action             VARCHAR(32)   DEFAULT NULL,
    direct             VARCHAR(16)   DEFAULT NULL,
    price              DECIMAL(20,8) DEFAULT NULL,
    quantity           DECIMAL(20,8) DEFAULT NULL,
    amount             DECIMAL(20,8) DEFAULT NULL,
    amount_ratio       DECIMAL(20,8) DEFAULT NULL,
    order_id           VARCHAR(128)  DEFAULT NULL,
    order_status       VARCHAR(32)   DEFAULT NULL,
    execution_status   VARCHAR(32)   NOT NULL DEFAULT 'pending',
    error_message      TEXT          DEFAULT NULL,
    executed_at        TIMESTAMP      DEFAULT NULL,
    created_at         TIMESTAMP      NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id)
);
CREATE TABLE IF NOT EXISTS customer_positions (
    id BIGSERIAL,
    customer_uid VARCHAR(64)   NOT NULL,
    symbol       VARCHAR(64)   NOT NULL,
    pos          DECIMAL(20,8) NOT NULL DEFAULT 0,
    pos_side     VARCHAR(16)   NOT NULL DEFAULT 'long',
    avg_px       DECIMAL(20,8) DEFAULT 0,
    upl          DECIMAL(20,8) DEFAULT 0,
    margin       DECIMAL(20,8) DEFAULT 0,
    status       VARCHAR(16)   NOT NULL DEFAULT 'open',
    created_at   TIMESTAMP      NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id)
);
CREATE TABLE IF NOT EXISTS customer_assets (
    id BIGSERIAL,
    customer_uid      VARCHAR(64)   NOT NULL,
    currency          VARCHAR(16)   NOT NULL DEFAULT 'USDT',
    total_balance     DECIMAL(20,8) NOT NULL DEFAULT 0,
    available_balance DECIMAL(20,8) NOT NULL DEFAULT 0,
    created_at        TIMESTAMP      NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at        TIMESTAMP      NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id)
);
CREATE TABLE IF NOT EXISTS customer_configs (
    id BIGSERIAL,
    customer_uid              VARCHAR(64)   NOT NULL,
    check_interval            INT           DEFAULT 30,
    sync_interval             INT           DEFAULT 300,
    status_sync_interval      INT           DEFAULT 60,
    health_check_interval     INT           DEFAULT 120,
    websocket_enabled         SMALLINT    DEFAULT 1,
    auto_repair_enabled       SMALLINT    DEFAULT 1,
    auto_repair_max_orders    INT           DEFAULT 3,
    stale_order_timeout       INT           DEFAULT 3600,
    max_concurrent_checks     INT           DEFAULT 5,
    batch_size                INT           DEFAULT 50,
    retry_attempts            INT           DEFAULT 3,
    timeout                   INT           DEFAULT 30,
    api_rate_limit_delay      DECIMAL(10,3) DEFAULT 0.100,
    max_consecutive_failures  INT           DEFAULT 5,
    enable_notifications      SMALLINT    DEFAULT 0,
    created_at                TIMESTAMP      NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at                TIMESTAMP      NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id)
);
CREATE TABLE IF NOT EXISTS strategy_configs (
    id BIGSERIAL PRIMARY KEY,
    strategy_name VARCHAR(100) NOT NULL UNIQUE,
    strategy_type VARCHAR(50) NOT NULL,
    config_json JSONB NOT NULL,
    is_active SMALLINT DEFAULT 0,
    is_template SMALLINT DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_by VARCHAR(50),
    version VARCHAR(20) DEFAULT '1.0.0'
);
CREATE TABLE IF NOT EXISTS strategy_instances (
    id BIGSERIAL PRIMARY KEY,
    instance_name VARCHAR(100) NOT NULL UNIQUE,
    strategy_name VARCHAR(100) NOT NULL,
    account_id VARCHAR(50) NOT NULL,
    symbol VARCHAR(20) NOT NULL,
    timeframe VARCHAR(10) NOT NULL,
    status VARCHAR(50) DEFAULT 'STOPPED',
    config_json JSONB NOT NULL,
    performance_json JSONB,
    started_at TIMESTAMP NULL,
    stopped_at TIMESTAMP NULL,
    last_signal_at TIMESTAMP NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_by VARCHAR(50),
    FOREIGN KEY (strategy_name) REFERENCES strategy_configs(strategy_name) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS strategy_signals (
    id BIGSERIAL PRIMARY KEY,
    instance_id BIGINT NOT NULL,
    signal_id VARCHAR(50) NOT NULL,
    symbol VARCHAR(20) NOT NULL,
    action VARCHAR(50) NOT NULL,
    price DECIMAL(20,8) NOT NULL,
    quantity DECIMAL(20,8) NOT NULL,
    confidence DECIMAL(5,4) NOT NULL,
    signal_strength DECIMAL(5,4),
    stop_loss DECIMAL(20,8),
    take_profit DECIMAL(20,8),
    metadata_json JSONB,
    status VARCHAR(50) DEFAULT 'PENDING',
    executed_at TIMESTAMP NULL,
    executed_price DECIMAL(20,8),
    executed_quantity DECIMAL(20,8),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (instance_id) REFERENCES strategy_instances(id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS strategy_positions (
    id BIGSERIAL PRIMARY KEY,
    instance_id BIGINT NOT NULL,
    position_id VARCHAR(50) NOT NULL,
    symbol VARCHAR(20) NOT NULL,
    side VARCHAR(50) NOT NULL,
    quantity DECIMAL(20,8) NOT NULL,
    entry_price DECIMAL(20,8) NOT NULL,
    current_price DECIMAL(20,8),
    unrealized_pnl DECIMAL(20,8) DEFAULT 0,
    stop_loss DECIMAL(20,8),
    take_profit DECIMAL(20,8),
    entry_time TIMESTAMP NOT NULL,
    exit_time TIMESTAMP NULL,
    exit_price DECIMAL(20,8),
    realized_pnl DECIMAL(20,8) DEFAULT 0,
    status VARCHAR(50) DEFAULT 'OPEN',
    metadata_json JSONB,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (instance_id) REFERENCES strategy_instances(id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS strategy_trades (
    id BIGSERIAL PRIMARY KEY,
    instance_id BIGINT NOT NULL,
    trade_id VARCHAR(50) NOT NULL,
    position_id VARCHAR(50),
    symbol VARCHAR(20) NOT NULL,
    side VARCHAR(50) NOT NULL,
    quantity DECIMAL(20,8) NOT NULL,
    price DECIMAL(20,8) NOT NULL,
    amount DECIMAL(20,8) NOT NULL,
    commission DECIMAL(20,8) DEFAULT 0,
    slippage DECIMAL(20,8) DEFAULT 0,
    pnl DECIMAL(20,8) DEFAULT 0,
    trade_type VARCHAR(50) NOT NULL,
    reason VARCHAR(100),
    metadata_json JSONB,
    executed_at TIMESTAMP NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (instance_id) REFERENCES strategy_instances(id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS strategy_performance (
    id BIGSERIAL PRIMARY KEY,
    instance_id BIGINT NOT NULL,
    date DATE NOT NULL,
    total_trades INT DEFAULT 0,
    winning_trades INT DEFAULT 0,
    losing_trades INT DEFAULT 0,
    win_rate DECIMAL(5,4) DEFAULT 0,
    total_pnl DECIMAL(20,8) DEFAULT 0,
    realized_pnl DECIMAL(20,8) DEFAULT 0,
    unrealized_pnl DECIMAL(20,8) DEFAULT 0,
    max_drawdown DECIMAL(20,8) DEFAULT 0,
    profit_factor DECIMAL(10,4) DEFAULT 0,
    sharpe_ratio DECIMAL(10,4) DEFAULT 0,
    max_consecutive_losses INT DEFAULT 0,
    current_consecutive_losses INT DEFAULT 0,
    average_win DECIMAL(20,8) DEFAULT 0,
    average_loss DECIMAL(20,8) DEFAULT 0,
    max_single_win DECIMAL(20,8) DEFAULT 0,
    max_single_loss DECIMAL(20,8) DEFAULT 0,
    daily_return DECIMAL(10,6) DEFAULT 0,
    cumulative_return DECIMAL(10,6) DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (instance_id) REFERENCES strategy_instances(id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS strategy_risk_monitor (
    id BIGSERIAL PRIMARY KEY,
    instance_id BIGINT NOT NULL,
    risk_type VARCHAR(50) NOT NULL,
    risk_level VARCHAR(50) NOT NULL,
    current_value DECIMAL(20,8) NOT NULL,
    threshold_value DECIMAL(20,8) NOT NULL,
    is_triggered SMALLINT DEFAULT 0,
    triggered_at TIMESTAMP NULL,
    message TEXT,
    action_taken VARCHAR(200),
    resolved_at TIMESTAMP NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (instance_id) REFERENCES strategy_instances(id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS strategy_backtests (
    id BIGSERIAL PRIMARY KEY,
    strategy_name VARCHAR(100) NOT NULL,
    backtest_name VARCHAR(100) NOT NULL,
    start_date DATE NOT NULL,
    end_date DATE NOT NULL,
    initial_capital DECIMAL(20,8) NOT NULL,
    final_capital DECIMAL(20,8) NOT NULL,
    total_return DECIMAL(10,6) NOT NULL,
    max_drawdown DECIMAL(10,6) NOT NULL,
    sharpe_ratio DECIMAL(10,4) NOT NULL,
    total_trades INT NOT NULL,
    win_rate DECIMAL(5,4) NOT NULL,
    profit_factor DECIMAL(10,4) NOT NULL,
    config_json JSONB NOT NULL,
    results_json JSONB,
    status VARCHAR(50) DEFAULT 'RUNNING',
    started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP NULL,
    created_by VARCHAR(50)
);
CREATE TABLE IF NOT EXISTS strategy_market_data (
    id BIGSERIAL PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL,
    timeframe VARCHAR(10) NOT NULL,
    timestamp TIMESTAMP NOT NULL,
    open_price DECIMAL(20,8) NOT NULL,
    high_price DECIMAL(20,8) NOT NULL,
    low_price DECIMAL(20,8) NOT NULL,
    close_price DECIMAL(20,8) NOT NULL,
    volume DECIMAL(20,8) NOT NULL,
    indicators_json JSONB,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS strategy_logs (
    id BIGSERIAL PRIMARY KEY,
    instance_id BIGINT,
    log_level VARCHAR(50) NOT NULL,
    message TEXT NOT NULL,
    module VARCHAR(50),
    function_name VARCHAR(100),
    line_number INT,
    exception_info TEXT,
    context_json JSONB,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (instance_id) REFERENCES strategy_instances(id) ON DELETE SET NULL
);
CREATE TABLE IF NOT EXISTS system_announcements (
    id BIGSERIAL,
    title       VARCHAR(255) NOT NULL,
    content     TEXT         NOT NULL,
    type        VARCHAR(20)  NOT NULL DEFAULT 'info',
    priority    INT          NOT NULL DEFAULT 0,
    is_pinned   SMALLINT   NOT NULL DEFAULT 0,
    is_active   SMALLINT   NOT NULL DEFAULT 1,
    created_by  VARCHAR(100) DEFAULT 'admin',
    expire_at   TIMESTAMP     NULL,
    created_at  TIMESTAMP     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at  TIMESTAMP     NULL DEFAULT NULL,
    PRIMARY KEY (id)
);
CREATE TABLE IF NOT EXISTS message_platforms (
    id BIGSERIAL,
    platform_type     VARCHAR(50)  NOT NULL,
    platform_name     VARCHAR(255) NOT NULL,
    enabled           SMALLINT   NOT NULL DEFAULT 1,
    config            TEXT     NOT NULL,
    monitored_chats   TEXT         NULL,
    status            VARCHAR(50)  NOT NULL DEFAULT 'inactive',
    error_message     TEXT         NULL,
    last_connected_at TIMESTAMP    NULL,
    created_at        TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at        TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id)
);
CREATE TABLE IF NOT EXISTS message_forward_rules (
    id BIGSERIAL,
    rule_id             VARCHAR(64)  NOT NULL,
    rule_name           VARCHAR(255) NOT NULL,
    enabled             SMALLINT   NOT NULL DEFAULT 1,
    source_platform_id  BIGINT       NULL,
    source_platform     VARCHAR(50)  NOT NULL DEFAULT '',
    source_chat_ids     TEXT         NULL,
    target_platform_ids TEXT         NULL,
    target_platforms    TEXT         NOT NULL,
    target_chat_ids     TEXT         NULL,
    keywords            TEXT         NULL,
    exclude_keywords    TEXT         NULL,
    add_prefix          VARCHAR(255) NULL DEFAULT '',
    add_suffix          VARCHAR(255) NULL DEFAULT '',
    enable_markdown     SMALLINT   NOT NULL DEFAULT 0,
    messages_forwarded  INT          NOT NULL DEFAULT 0,
    created_at          TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at          TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id)
);
CREATE TABLE IF NOT EXISTS message_history (
    id BIGSERIAL,
    message_id         VARCHAR(255) NOT NULL,
    source_platform_id BIGINT       NULL,
    source_platform    VARCHAR(50)  NOT NULL,
    source_chat_id     VARCHAR(255) NULL,
    source_chat_title  VARCHAR(255) NULL,
    content            TEXT         NOT NULL,
    forwarded_to       TEXT         NULL,
    is_test            SMALLINT   NOT NULL DEFAULT 0,
    rule_id            VARCHAR(64)  NULL,
    timestamp          TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id)
);

-- ---- 索引 ----
CREATE UNIQUE INDEX IF NOT EXISTS users_uk_users_username ON users (username);
CREATE INDEX IF NOT EXISTS users_idx_users_role ON users (role);
CREATE INDEX IF NOT EXISTS users_idx_users_status ON users (status);
CREATE INDEX IF NOT EXISTS users_idx_users_customer_uid ON users (customer_uid);
CREATE UNIQUE INDEX IF NOT EXISTS roles_uk_roles_code ON roles (role_code);
CREATE UNIQUE INDEX IF NOT EXISTS modules_uk_modules_code ON modules (module_code);
CREATE UNIQUE INDEX IF NOT EXISTS permissions_uk_permissions_module_level ON permissions (module_id, permission_level);
CREATE UNIQUE INDEX IF NOT EXISTS role_permissions_uk_role_perm ON role_permissions (role_id, permission_id);
CREATE INDEX IF NOT EXISTS role_permissions_idx_rp_permission ON role_permissions (permission_id);
CREATE UNIQUE INDEX IF NOT EXISTS user_permissions_uk_user_module ON user_permissions (user_id, module_code);
CREATE INDEX IF NOT EXISTS user_permissions_idx_up_module ON user_permissions (module_code);
CREATE INDEX IF NOT EXISTS user_permissions_idx_up_granted_by ON user_permissions (granted_by);
CREATE INDEX IF NOT EXISTS user_permissions_idx_up_expires ON user_permissions (expires_at);
CREATE UNIQUE INDEX IF NOT EXISTS sessions_uk_sessions_session_id ON sessions (session_id);
CREATE INDEX IF NOT EXISTS sessions_idx_sessions_user ON sessions (user_id);
CREATE INDEX IF NOT EXISTS sessions_idx_sessions_expires ON sessions (expires_at);
CREATE INDEX IF NOT EXISTS login_logs_idx_login_logs_user ON login_logs (user_id);
CREATE INDEX IF NOT EXISTS login_logs_idx_login_logs_username ON login_logs (username);
CREATE INDEX IF NOT EXISTS login_logs_idx_login_logs_created ON login_logs (created_at);
CREATE UNIQUE INDEX IF NOT EXISTS membership_levels_uk_ml_code ON membership_levels (level_code);
CREATE INDEX IF NOT EXISTS membership_levels_idx_ml_order ON membership_levels (level_order);
CREATE UNIQUE INDEX IF NOT EXISTS membership_level_permissions_uk_mlp_level_module ON membership_level_permissions (level_id, module_code);
CREATE INDEX IF NOT EXISTS membership_level_permissions_idx_mlp_module ON membership_level_permissions (module_code);
CREATE INDEX IF NOT EXISTS user_memberships_idx_um_user_status ON user_memberships (user_id, status);
CREATE INDEX IF NOT EXISTS user_memberships_idx_um_level ON user_memberships (level_id);
CREATE INDEX IF NOT EXISTS user_memberships_idx_um_expires ON user_memberships (expires_at);
CREATE UNIQUE INDEX IF NOT EXISTS membership_orders_uk_mo_order_no ON membership_orders (order_no);
CREATE INDEX IF NOT EXISTS membership_orders_idx_mo_user ON membership_orders (user_id);
CREATE INDEX IF NOT EXISTS membership_orders_idx_mo_level ON membership_orders (level_id);
CREATE UNIQUE INDEX IF NOT EXISTS membership_payment_orders_uk_mpo_order_no ON membership_payment_orders (order_no);
CREATE INDEX IF NOT EXISTS membership_payment_orders_idx_mpo_user ON membership_payment_orders (user_id);
CREATE INDEX IF NOT EXISTS membership_payment_orders_idx_mpo_level ON membership_payment_orders (membership_level_id);
CREATE INDEX IF NOT EXISTS membership_payment_orders_idx_mpo_status ON membership_payment_orders (status);
CREATE INDEX IF NOT EXISTS membership_payment_orders_idx_mpo_tx_hash ON membership_payment_orders (payment_tx_hash);
CREATE INDEX IF NOT EXISTS payment_listener_logs_idx_pll_order_no ON payment_listener_logs (order_no);
CREATE INDEX IF NOT EXISTS payment_listener_logs_idx_pll_created ON payment_listener_logs (created_at);
CREATE UNIQUE INDEX IF NOT EXISTS exchange_api_redemption_codes_uk_earc_code ON exchange_api_redemption_codes (code);
CREATE INDEX IF NOT EXISTS exchange_api_redemption_codes_idx_earc_exchange ON exchange_api_redemption_codes (exchange);
CREATE INDEX IF NOT EXISTS exchange_api_redemption_codes_idx_earc_user ON exchange_api_redemption_codes (user_id);
CREATE INDEX IF NOT EXISTS exchange_api_redemption_codes_idx_earc_created_by ON exchange_api_redemption_codes (created_by);
CREATE INDEX IF NOT EXISTS signal_sources_idx_ss_enabled ON signal_sources (enabled);
CREATE INDEX IF NOT EXISTS signal_sources_idx_ss_is_demo ON signal_sources (is_demo);
CREATE INDEX IF NOT EXISTS signal_sources_idx_ss_unique_name ON signal_sources (unique_name);
CREATE INDEX IF NOT EXISTS customers_idx_c_enabled ON customers (enabled);
CREATE INDEX IF NOT EXISTS customers_idx_c_is_demo ON customers (is_demo);
CREATE INDEX IF NOT EXISTS customers_idx_c_owner ON customers (owner_user_id);
CREATE INDEX IF NOT EXISTS strategies_idx_s_enabled ON strategies (enabled);
CREATE INDEX IF NOT EXISTS strategies_idx_s_signal_source ON strategies (signal_source_uid);
CREATE INDEX IF NOT EXISTS rules_idx_r_strategy ON rules (strategy_uid);
CREATE INDEX IF NOT EXISTS rules_idx_r_enabled ON rules (enabled);
CREATE INDEX IF NOT EXISTS strategy_signal_source_idx_sss_strategy ON strategy_signal_source (strategy_uid);
CREATE INDEX IF NOT EXISTS strategy_signal_source_idx_sss_source ON strategy_signal_source (source_uid);
CREATE INDEX IF NOT EXISTS strategy_signal_source_idx_sss_signal_source ON strategy_signal_source (signal_source_uid);
CREATE INDEX IF NOT EXISTS strategy_signal_source_idx_sss_enabled ON strategy_signal_source (enabled);
CREATE INDEX IF NOT EXISTS customer_strategy_idx_cs_customer ON customer_strategy (customer_uid);
CREATE INDEX IF NOT EXISTS customer_strategy_idx_cs_strategy ON customer_strategy (strategy_uid);
CREATE INDEX IF NOT EXISTS customer_strategy_idx_cs_enabled ON customer_strategy (enabled);
CREATE INDEX IF NOT EXISTS customer_rule_idx_cr_customer ON customer_rule (customer_uid);
CREATE INDEX IF NOT EXISTS customer_rule_idx_cr_rule ON customer_rule (rule_uid);
CREATE INDEX IF NOT EXISTS customer_rule_idx_cr_enabled ON customer_rule (enabled);
CREATE INDEX IF NOT EXISTS signal_account_assets_idx_saa_source_time ON signal_account_assets (signal_source_uid, snapshot_time);
CREATE INDEX IF NOT EXISTS signal_account_trades_idx_sat_source ON signal_account_trades (signal_source_uid);
CREATE INDEX IF NOT EXISTS signal_account_trades_idx_sat_symbol ON signal_account_trades (symbol);
CREATE INDEX IF NOT EXISTS signal_account_trades_idx_sat_status ON signal_account_trades (status);
CREATE INDEX IF NOT EXISTS signal_account_trades_idx_sat_is_demo ON signal_account_trades (is_demo);
CREATE INDEX IF NOT EXISTS signal_account_trades_idx_sat_order ON signal_account_trades (order_id);
CREATE INDEX IF NOT EXISTS signal_account_trades_idx_sat_close_order ON signal_account_trades (close_order_id);
CREATE INDEX IF NOT EXISTS signal_account_trades_idx_sat_lookup ON signal_account_trades (signal_source_uid, symbol, pos_side, is_demo, status);
CREATE INDEX IF NOT EXISTS customer_trades_idx_ct_customer ON customer_trades (customer_uid);
CREATE INDEX IF NOT EXISTS customer_trades_idx_ct_strategy ON customer_trades (strategy_uid);
CREATE INDEX IF NOT EXISTS customer_trades_idx_ct_rule ON customer_trades (rule_uid);
CREATE INDEX IF NOT EXISTS customer_trades_idx_ct_symbol ON customer_trades (symbol);
CREATE INDEX IF NOT EXISTS customer_trades_idx_ct_status ON customer_trades (status);
CREATE INDEX IF NOT EXISTS customer_trades_idx_ct_is_demo ON customer_trades (is_demo);
CREATE INDEX IF NOT EXISTS customer_trades_idx_ct_close_order ON customer_trades (close_order_id);
CREATE INDEX IF NOT EXISTS customer_trades_idx_ct_parent_ord ON customer_trades (parent_ordId);
CREATE INDEX IF NOT EXISTS customer_trades_idx_ct_lookup ON customer_trades (customer_uid, symbol, pos_side, status, is_demo);
CREATE INDEX IF NOT EXISTS trade_failures_idx_tf_customer_trade ON trade_failures (customer_trade_uid);
CREATE UNIQUE INDEX IF NOT EXISTS limit_follow_traders_uk_unique_name ON limit_follow_traders (unique_name);
CREATE INDEX IF NOT EXISTS limit_follow_traders_idx_lft_enabled ON limit_follow_traders (enabled);
CREATE INDEX IF NOT EXISTS limit_follow_traders_idx_lft_created_by ON limit_follow_traders (created_by_user_id);
CREATE INDEX IF NOT EXISTS limit_follow_strategies_idx_lfs_trader ON limit_follow_strategies (trader_unique_name);
CREATE INDEX IF NOT EXISTS limit_follow_strategies_idx_lfs_customer ON limit_follow_strategies (customer_uid);
CREATE INDEX IF NOT EXISTS limit_follow_strategies_idx_lfs_symbol ON limit_follow_strategies (symbol);
CREATE INDEX IF NOT EXISTS limit_follow_strategies_idx_lfs_enabled ON limit_follow_strategies (enabled);
CREATE INDEX IF NOT EXISTS limit_follow_strategies_idx_lfs_follow_mode ON limit_follow_strategies (follow_mode);
CREATE INDEX IF NOT EXISTS limit_follow_strategies_idx_lfs_created_by ON limit_follow_strategies (created_by_user_id);
CREATE INDEX IF NOT EXISTS limit_follow_strategies_idx_lfs_signal_lookup ON limit_follow_strategies (trader_unique_name, symbol, enabled);
CREATE UNIQUE INDEX IF NOT EXISTS limit_follow_strategy_customers_uk_lfsc_strategy_customer ON limit_follow_strategy_customers (strategy_id, customer_uid);
CREATE INDEX IF NOT EXISTS limit_follow_strategy_customers_idx_lfsc_customer ON limit_follow_strategy_customers (customer_uid);
CREATE INDEX IF NOT EXISTS limit_follow_strategy_customers_idx_lfsc_enabled ON limit_follow_strategy_customers (enabled);
CREATE UNIQUE INDEX IF NOT EXISTS limit_follow_orders_uk_lfo_order_uid ON limit_follow_orders (order_uid);
CREATE INDEX IF NOT EXISTS limit_follow_orders_idx_lfo_strategy ON limit_follow_orders (strategy_id);
CREATE INDEX IF NOT EXISTS limit_follow_orders_idx_lfo_trader ON limit_follow_orders (trader_unique_name);
CREATE INDEX IF NOT EXISTS limit_follow_orders_idx_lfo_customer ON limit_follow_orders (customer_uid);
CREATE INDEX IF NOT EXISTS limit_follow_orders_idx_lfo_symbol ON limit_follow_orders (symbol);
CREATE INDEX IF NOT EXISTS limit_follow_orders_idx_lfo_status ON limit_follow_orders (status);
CREATE INDEX IF NOT EXISTS limit_follow_orders_idx_lfo_exchange_order ON limit_follow_orders (exchange_order_id);
CREATE INDEX IF NOT EXISTS limit_follow_orders_idx_lfo_signal_order ON limit_follow_orders (signal_order_id);
CREATE INDEX IF NOT EXISTS limit_follow_orders_idx_lfo_cust_sym_side ON limit_follow_orders (customer_uid, symbol, pos_side);
CREATE UNIQUE INDEX IF NOT EXISTS limit_follow_executions_uk_lfe_execution_uid ON limit_follow_executions (execution_uid);
CREATE INDEX IF NOT EXISTS limit_follow_executions_idx_lfe_strategy ON limit_follow_executions (strategy_id);
CREATE INDEX IF NOT EXISTS limit_follow_executions_idx_lfe_order ON limit_follow_executions (order_uid);
CREATE INDEX IF NOT EXISTS limit_follow_executions_idx_lfe_customer ON limit_follow_executions (customer_uid);
CREATE INDEX IF NOT EXISTS limit_follow_executions_idx_lfe_status ON limit_follow_executions (execution_status);
CREATE UNIQUE INDEX IF NOT EXISTS limit_follow_configs_uk_lfc_config_key ON limit_follow_configs (config_key);
CREATE INDEX IF NOT EXISTS limit_follow_configs_idx_lfc_customer ON limit_follow_configs (customer_uid);
CREATE INDEX IF NOT EXISTS limit_follow_configs_idx_lfc_enabled ON limit_follow_configs (enabled);
CREATE INDEX IF NOT EXISTS limit_follow_logs_idx_lfl_level ON limit_follow_logs (log_level);
CREATE INDEX IF NOT EXISTS limit_follow_logs_idx_lfl_order ON limit_follow_logs (order_uid);
CREATE INDEX IF NOT EXISTS limit_follow_logs_idx_lfl_strategy ON limit_follow_logs (strategy_id);
CREATE INDEX IF NOT EXISTS limit_follow_logs_idx_lfl_created ON limit_follow_logs (created_at);
CREATE UNIQUE INDEX IF NOT EXISTS trader_trades_uk_tt_trade_uid ON trader_trades (trade_uid);
CREATE INDEX IF NOT EXISTS trader_trades_idx_tt_trader_lookup ON trader_trades (trader_unique_name, symbol, pos_side, status);
CREATE INDEX IF NOT EXISTS trader_trades_idx_tt_order ON trader_trades (order_id);
CREATE UNIQUE INDEX IF NOT EXISTS market_maker_accounts_uk_mma_account_name ON market_maker_accounts (account_name);
CREATE INDEX IF NOT EXISTS market_maker_accounts_idx_mma_user ON market_maker_accounts (user_id);
CREATE INDEX IF NOT EXISTS market_maker_accounts_idx_mma_user_enabled ON market_maker_accounts (user_id, enabled);
CREATE UNIQUE INDEX IF NOT EXISTS market_maker_status_uk_mms_account_symbol ON market_maker_status (account_name, symbol);
CREATE INDEX IF NOT EXISTS market_maker_status_idx_mms_status ON market_maker_status (status);
CREATE UNIQUE INDEX IF NOT EXISTS market_maker_stats_uk_mmst_account_symbol_date ON market_maker_stats (account_name, symbol, date);
CREATE INDEX IF NOT EXISTS market_maker_stats_idx_mmst_date ON market_maker_stats (date);
CREATE UNIQUE INDEX IF NOT EXISTS invitation_codes_uk_ic_code ON invitation_codes (code);
CREATE INDEX IF NOT EXISTS invitation_codes_idx_ic_rule ON invitation_codes (rule_id);
CREATE INDEX IF NOT EXISTS invitation_codes_idx_ic_target ON invitation_codes (rule_id, target_platform_id, target_chat_id);
CREATE INDEX IF NOT EXISTS invitation_codes_idx_ic_created_by ON invitation_codes (created_by);
CREATE INDEX IF NOT EXISTS invitation_code_usage_idx_icu_code ON invitation_code_usage (code);
CREATE INDEX IF NOT EXISTS invitation_code_usage_idx_icu_rule ON invitation_code_usage (rule_id);
CREATE UNIQUE INDEX IF NOT EXISTS forward_rule_subscriptions_uk_frs_rule_target ON forward_rule_subscriptions (rule_id, target_platform_id, target_chat_id);
CREATE INDEX IF NOT EXISTS forward_rule_subscriptions_idx_frs_status_expire ON forward_rule_subscriptions (subscription_status, expire_date);
CREATE UNIQUE INDEX IF NOT EXISTS telegram_user_subscriptions_uk_tus_user_rule ON telegram_user_subscriptions (user_id, rule_id);
CREATE INDEX IF NOT EXISTS telegram_user_subscriptions_idx_tus_rule ON telegram_user_subscriptions (rule_id);
CREATE UNIQUE INDEX IF NOT EXISTS telegram_user_sessions_uk_tusess_user ON telegram_user_sessions (user_id);
CREATE UNIQUE INDEX IF NOT EXISTS telegram_bot_user_bindings_uk_tbub_telegram_user ON telegram_bot_user_bindings (telegram_user_id);
CREATE UNIQUE INDEX IF NOT EXISTS telegram_bot_user_bindings_uk_tbub_platform_user ON telegram_bot_user_bindings (platform_user_id);
CREATE UNIQUE INDEX IF NOT EXISTS forward_trade_configs_uk_ftc_config_name ON forward_trade_configs (config_name);
CREATE INDEX IF NOT EXISTS forward_trade_configs_idx_ftc_user ON forward_trade_configs (user_id);
CREATE INDEX IF NOT EXISTS forward_trade_configs_idx_ftc_customer ON forward_trade_configs (customer_uid);
CREATE UNIQUE INDEX IF NOT EXISTS wechat_official_users_uk_wou_openid ON wechat_official_users (openid);
CREATE INDEX IF NOT EXISTS wechat_official_users_idx_wou_subscribe_status ON wechat_official_users (subscribe, status);
CREATE UNIQUE INDEX IF NOT EXISTS wechat_official_subscriptions_uk_wos_user_subtype ON wechat_official_subscriptions (user_id, subscription_type);
CREATE INDEX IF NOT EXISTS wechat_official_subscriptions_idx_wos_openid ON wechat_official_subscriptions (openid);
CREATE INDEX IF NOT EXISTS wechat_official_subscriptions_idx_wos_type ON wechat_official_subscriptions (subscription_type);
CREATE INDEX IF NOT EXISTS wechat_official_message_logs_idx_woml_user ON wechat_official_message_logs (user_id);
CREATE INDEX IF NOT EXISTS wechat_official_message_logs_idx_woml_openid ON wechat_official_message_logs (openid);
CREATE INDEX IF NOT EXISTS signal_stop_loss_idx_ssl_source ON signal_stop_loss (signal_source_uid);
CREATE INDEX IF NOT EXISTS signal_stop_loss_idx_ssl_strategy ON signal_stop_loss (strategy_uid);
CREATE INDEX IF NOT EXISTS signal_stop_loss_idx_ssl_is_demo ON signal_stop_loss (is_demo);
CREATE INDEX IF NOT EXISTS signal_stop_loss_idx_ssl_lookup ON signal_stop_loss (signal_source_uid, strategy_uid, is_demo);
CREATE INDEX IF NOT EXISTS customer_stop_loss_idx_csl_customer ON customer_stop_loss (customer_uid);
CREATE INDEX IF NOT EXISTS customer_stop_loss_idx_csl_strategy ON customer_stop_loss (strategy_uid);
CREATE INDEX IF NOT EXISTS customer_stop_loss_idx_csl_is_demo ON customer_stop_loss (is_demo);
CREATE INDEX IF NOT EXISTS customer_stop_loss_idx_csl_lookup ON customer_stop_loss (customer_uid, strategy_uid, is_demo);
CREATE INDEX IF NOT EXISTS manual_operations_idx_mo_customer ON manual_operations (customer_uid);
CREATE INDEX IF NOT EXISTS manual_operations_idx_mo_order ON manual_operations (order_id);
CREATE INDEX IF NOT EXISTS manual_operations_idx_mo_symbol ON manual_operations (symbol);
CREATE INDEX IF NOT EXISTS manual_operations_idx_mo_op_type ON manual_operations (operation_type);
CREATE INDEX IF NOT EXISTS manual_operations_idx_mo_exec_status ON manual_operations (execution_status);
CREATE INDEX IF NOT EXISTS manual_operations_idx_mo_is_demo ON manual_operations (is_demo);
CREATE INDEX IF NOT EXISTS manual_operations_idx_mo_created ON manual_operations (created_at);
CREATE INDEX IF NOT EXISTS position_anomalies_idx_pa_customer ON position_anomalies (customer_uid);
CREATE INDEX IF NOT EXISTS position_anomalies_idx_pa_symbol ON position_anomalies (symbol);
CREATE INDEX IF NOT EXISTS position_anomalies_idx_pa_status ON position_anomalies (status);
CREATE INDEX IF NOT EXISTS position_anomalies_idx_pa_is_demo ON position_anomalies (is_demo);
CREATE INDEX IF NOT EXISTS position_anomalies_idx_pa_created ON position_anomalies (created_at);
CREATE INDEX IF NOT EXISTS position_anomalies_idx_pa_lookup ON position_anomalies (customer_uid, symbol, pos_side, status);
CREATE INDEX IF NOT EXISTS forward_trade_records_idx_ftr_config ON forward_trade_records (config_id);
CREATE INDEX IF NOT EXISTS forward_trade_records_idx_ftr_symbol ON forward_trade_records (symbol);
CREATE INDEX IF NOT EXISTS forward_trade_records_idx_ftr_exec_status ON forward_trade_records (execution_status);
CREATE INDEX IF NOT EXISTS forward_trade_records_idx_ftr_created ON forward_trade_records (created_at);
CREATE INDEX IF NOT EXISTS customer_positions_idx_cp_customer ON customer_positions (customer_uid);
CREATE INDEX IF NOT EXISTS customer_positions_idx_cp_symbol ON customer_positions (symbol);
CREATE INDEX IF NOT EXISTS customer_positions_idx_cp_status ON customer_positions (status);
CREATE INDEX IF NOT EXISTS customer_positions_idx_cp_lookup ON customer_positions (customer_uid, symbol, status);
CREATE INDEX IF NOT EXISTS customer_assets_idx_ca_customer ON customer_assets (customer_uid);
CREATE INDEX IF NOT EXISTS customer_assets_idx_ca_lookup ON customer_assets (customer_uid, currency);
CREATE UNIQUE INDEX IF NOT EXISTS customer_configs_uk_cc_customer ON customer_configs (customer_uid);
CREATE INDEX IF NOT EXISTS strategy_configs_idx_strategy_type ON strategy_configs (strategy_type);
CREATE INDEX IF NOT EXISTS strategy_configs_idx_is_active ON strategy_configs (is_active);
CREATE INDEX IF NOT EXISTS strategy_configs_idx_created_at ON strategy_configs (created_at);
CREATE INDEX IF NOT EXISTS strategy_instances_idx_strategy_name ON strategy_instances (strategy_name);
CREATE INDEX IF NOT EXISTS strategy_instances_idx_account_id ON strategy_instances (account_id);
CREATE INDEX IF NOT EXISTS strategy_instances_idx_symbol ON strategy_instances (symbol);
CREATE INDEX IF NOT EXISTS strategy_instances_idx_status ON strategy_instances (status);
CREATE INDEX IF NOT EXISTS strategy_instances_idx_started_at ON strategy_instances (started_at);
CREATE INDEX IF NOT EXISTS strategy_signals_idx_instance_id ON strategy_signals (instance_id);
CREATE INDEX IF NOT EXISTS strategy_signals_idx_signal_id ON strategy_signals (signal_id);
CREATE INDEX IF NOT EXISTS strategy_signals_idx_symbol ON strategy_signals (symbol);
CREATE INDEX IF NOT EXISTS strategy_signals_idx_action ON strategy_signals (action);
CREATE INDEX IF NOT EXISTS strategy_signals_idx_status ON strategy_signals (status);
CREATE INDEX IF NOT EXISTS strategy_signals_idx_created_at ON strategy_signals (created_at);
CREATE INDEX IF NOT EXISTS strategy_positions_idx_instance_id ON strategy_positions (instance_id);
CREATE INDEX IF NOT EXISTS strategy_positions_idx_position_id ON strategy_positions (position_id);
CREATE INDEX IF NOT EXISTS strategy_positions_idx_symbol ON strategy_positions (symbol);
CREATE INDEX IF NOT EXISTS strategy_positions_idx_side ON strategy_positions (side);
CREATE INDEX IF NOT EXISTS strategy_positions_idx_status ON strategy_positions (status);
CREATE INDEX IF NOT EXISTS strategy_positions_idx_entry_time ON strategy_positions (entry_time);
CREATE INDEX IF NOT EXISTS strategy_trades_idx_instance_id ON strategy_trades (instance_id);
CREATE INDEX IF NOT EXISTS strategy_trades_idx_trade_id ON strategy_trades (trade_id);
CREATE INDEX IF NOT EXISTS strategy_trades_idx_position_id ON strategy_trades (position_id);
CREATE INDEX IF NOT EXISTS strategy_trades_idx_symbol ON strategy_trades (symbol);
CREATE INDEX IF NOT EXISTS strategy_trades_idx_side ON strategy_trades (side);
CREATE INDEX IF NOT EXISTS strategy_trades_idx_executed_at ON strategy_trades (executed_at);
CREATE UNIQUE INDEX IF NOT EXISTS strategy_performance_uk_instance_date ON strategy_performance (instance_id, date);
CREATE INDEX IF NOT EXISTS strategy_performance_idx_instance_id ON strategy_performance (instance_id);
CREATE INDEX IF NOT EXISTS strategy_performance_idx_date ON strategy_performance (date);
CREATE INDEX IF NOT EXISTS strategy_risk_monitor_idx_instance_id ON strategy_risk_monitor (instance_id);
CREATE INDEX IF NOT EXISTS strategy_risk_monitor_idx_risk_type ON strategy_risk_monitor (risk_type);
CREATE INDEX IF NOT EXISTS strategy_risk_monitor_idx_risk_level ON strategy_risk_monitor (risk_level);
CREATE INDEX IF NOT EXISTS strategy_risk_monitor_idx_is_triggered ON strategy_risk_monitor (is_triggered);
CREATE INDEX IF NOT EXISTS strategy_risk_monitor_idx_triggered_at ON strategy_risk_monitor (triggered_at);
CREATE INDEX IF NOT EXISTS strategy_backtests_idx_strategy_name ON strategy_backtests (strategy_name);
CREATE INDEX IF NOT EXISTS strategy_backtests_idx_backtest_name ON strategy_backtests (backtest_name);
CREATE INDEX IF NOT EXISTS strategy_backtests_idx_start_date ON strategy_backtests (start_date);
CREATE INDEX IF NOT EXISTS strategy_backtests_idx_end_date ON strategy_backtests (end_date);
CREATE INDEX IF NOT EXISTS strategy_backtests_idx_status ON strategy_backtests (status);
CREATE INDEX IF NOT EXISTS strategy_backtests_idx_started_at ON strategy_backtests (started_at);
CREATE UNIQUE INDEX IF NOT EXISTS strategy_market_data_uk_symbol_timeframe_timestamp ON strategy_market_data (symbol, timeframe, timestamp);
CREATE INDEX IF NOT EXISTS strategy_market_data_idx_symbol ON strategy_market_data (symbol);
CREATE INDEX IF NOT EXISTS strategy_market_data_idx_timeframe ON strategy_market_data (timeframe);
CREATE INDEX IF NOT EXISTS strategy_market_data_idx_timestamp ON strategy_market_data (timestamp);
CREATE INDEX IF NOT EXISTS strategy_logs_idx_instance_id ON strategy_logs (instance_id);
CREATE INDEX IF NOT EXISTS strategy_logs_idx_log_level ON strategy_logs (log_level);
CREATE INDEX IF NOT EXISTS strategy_logs_idx_created_at ON strategy_logs (created_at);
CREATE INDEX IF NOT EXISTS system_announcements_idx_active_expire ON system_announcements (is_active, expire_at);
CREATE INDEX IF NOT EXISTS system_announcements_idx_pinned_priority ON system_announcements (is_pinned, priority);
CREATE INDEX IF NOT EXISTS system_announcements_idx_created_at ON system_announcements (created_at);
CREATE UNIQUE INDEX IF NOT EXISTS message_platforms_uk_platform_name ON message_platforms (platform_name);
CREATE INDEX IF NOT EXISTS message_platforms_idx_platform_type ON message_platforms (platform_type);
CREATE UNIQUE INDEX IF NOT EXISTS message_forward_rules_uk_rule_id ON message_forward_rules (rule_id);
CREATE INDEX IF NOT EXISTS message_forward_rules_idx_source_platform_id ON message_forward_rules (source_platform_id);
CREATE INDEX IF NOT EXISTS message_history_idx_timestamp ON message_history (timestamp);
CREATE INDEX IF NOT EXISTS message_history_idx_source_platform_id ON message_history (source_platform_id);
CREATE INDEX IF NOT EXISTS message_history_idx_rule_id ON message_history (rule_id);

-- ---- updated_at 触发器 ----
DROP TRIGGER IF EXISTS trg_users_updated_at ON users;
CREATE TRIGGER trg_users_updated_at BEFORE UPDATE ON users FOR EACH ROW EXECUTE FUNCTION set_updated_at();
DROP TRIGGER IF EXISTS trg_membership_levels_updated_at ON membership_levels;
CREATE TRIGGER trg_membership_levels_updated_at BEFORE UPDATE ON membership_levels FOR EACH ROW EXECUTE FUNCTION set_updated_at();
DROP TRIGGER IF EXISTS trg_user_memberships_updated_at ON user_memberships;
CREATE TRIGGER trg_user_memberships_updated_at BEFORE UPDATE ON user_memberships FOR EACH ROW EXECUTE FUNCTION set_updated_at();
DROP TRIGGER IF EXISTS trg_membership_orders_updated_at ON membership_orders;
CREATE TRIGGER trg_membership_orders_updated_at BEFORE UPDATE ON membership_orders FOR EACH ROW EXECUTE FUNCTION set_updated_at();
DROP TRIGGER IF EXISTS trg_membership_payment_orders_updated_at ON membership_payment_orders;
CREATE TRIGGER trg_membership_payment_orders_updated_at BEFORE UPDATE ON membership_payment_orders FOR EACH ROW EXECUTE FUNCTION set_updated_at();
DROP TRIGGER IF EXISTS trg_exchange_api_redemption_codes_updated_at ON exchange_api_redemption_codes;
CREATE TRIGGER trg_exchange_api_redemption_codes_updated_at BEFORE UPDATE ON exchange_api_redemption_codes FOR EACH ROW EXECUTE FUNCTION set_updated_at();
DROP TRIGGER IF EXISTS trg_limit_follow_traders_updated_at ON limit_follow_traders;
CREATE TRIGGER trg_limit_follow_traders_updated_at BEFORE UPDATE ON limit_follow_traders FOR EACH ROW EXECUTE FUNCTION set_updated_at();
DROP TRIGGER IF EXISTS trg_limit_follow_strategies_updated_at ON limit_follow_strategies;
CREATE TRIGGER trg_limit_follow_strategies_updated_at BEFORE UPDATE ON limit_follow_strategies FOR EACH ROW EXECUTE FUNCTION set_updated_at();
DROP TRIGGER IF EXISTS trg_limit_follow_strategy_customers_updated_at ON limit_follow_strategy_customers;
CREATE TRIGGER trg_limit_follow_strategy_customers_updated_at BEFORE UPDATE ON limit_follow_strategy_customers FOR EACH ROW EXECUTE FUNCTION set_updated_at();
DROP TRIGGER IF EXISTS trg_limit_follow_orders_updated_at ON limit_follow_orders;
CREATE TRIGGER trg_limit_follow_orders_updated_at BEFORE UPDATE ON limit_follow_orders FOR EACH ROW EXECUTE FUNCTION set_updated_at();
DROP TRIGGER IF EXISTS trg_limit_follow_executions_updated_at ON limit_follow_executions;
CREATE TRIGGER trg_limit_follow_executions_updated_at BEFORE UPDATE ON limit_follow_executions FOR EACH ROW EXECUTE FUNCTION set_updated_at();
DROP TRIGGER IF EXISTS trg_limit_follow_configs_updated_at ON limit_follow_configs;
CREATE TRIGGER trg_limit_follow_configs_updated_at BEFORE UPDATE ON limit_follow_configs FOR EACH ROW EXECUTE FUNCTION set_updated_at();
DROP TRIGGER IF EXISTS trg_market_maker_accounts_updated_at ON market_maker_accounts;
CREATE TRIGGER trg_market_maker_accounts_updated_at BEFORE UPDATE ON market_maker_accounts FOR EACH ROW EXECUTE FUNCTION set_updated_at();
DROP TRIGGER IF EXISTS trg_market_maker_stats_updated_at ON market_maker_stats;
CREATE TRIGGER trg_market_maker_stats_updated_at BEFORE UPDATE ON market_maker_stats FOR EACH ROW EXECUTE FUNCTION set_updated_at();
DROP TRIGGER IF EXISTS trg_invitation_codes_updated_at ON invitation_codes;
CREATE TRIGGER trg_invitation_codes_updated_at BEFORE UPDATE ON invitation_codes FOR EACH ROW EXECUTE FUNCTION set_updated_at();
DROP TRIGGER IF EXISTS trg_forward_rule_subscriptions_updated_at ON forward_rule_subscriptions;
CREATE TRIGGER trg_forward_rule_subscriptions_updated_at BEFORE UPDATE ON forward_rule_subscriptions FOR EACH ROW EXECUTE FUNCTION set_updated_at();
DROP TRIGGER IF EXISTS trg_telegram_user_subscriptions_updated_at ON telegram_user_subscriptions;
CREATE TRIGGER trg_telegram_user_subscriptions_updated_at BEFORE UPDATE ON telegram_user_subscriptions FOR EACH ROW EXECUTE FUNCTION set_updated_at();
DROP TRIGGER IF EXISTS trg_telegram_user_sessions_updated_at ON telegram_user_sessions;
CREATE TRIGGER trg_telegram_user_sessions_updated_at BEFORE UPDATE ON telegram_user_sessions FOR EACH ROW EXECUTE FUNCTION set_updated_at();
DROP TRIGGER IF EXISTS trg_forward_trade_configs_updated_at ON forward_trade_configs;
CREATE TRIGGER trg_forward_trade_configs_updated_at BEFORE UPDATE ON forward_trade_configs FOR EACH ROW EXECUTE FUNCTION set_updated_at();
DROP TRIGGER IF EXISTS trg_wechat_official_users_updated_at ON wechat_official_users;
CREATE TRIGGER trg_wechat_official_users_updated_at BEFORE UPDATE ON wechat_official_users FOR EACH ROW EXECUTE FUNCTION set_updated_at();
DROP TRIGGER IF EXISTS trg_wechat_official_subscriptions_updated_at ON wechat_official_subscriptions;
CREATE TRIGGER trg_wechat_official_subscriptions_updated_at BEFORE UPDATE ON wechat_official_subscriptions FOR EACH ROW EXECUTE FUNCTION set_updated_at();
DROP TRIGGER IF EXISTS trg_signal_stop_loss_updated_at ON signal_stop_loss;
CREATE TRIGGER trg_signal_stop_loss_updated_at BEFORE UPDATE ON signal_stop_loss FOR EACH ROW EXECUTE FUNCTION set_updated_at();
DROP TRIGGER IF EXISTS trg_customer_stop_loss_updated_at ON customer_stop_loss;
CREATE TRIGGER trg_customer_stop_loss_updated_at BEFORE UPDATE ON customer_stop_loss FOR EACH ROW EXECUTE FUNCTION set_updated_at();
DROP TRIGGER IF EXISTS trg_manual_operations_updated_at ON manual_operations;
CREATE TRIGGER trg_manual_operations_updated_at BEFORE UPDATE ON manual_operations FOR EACH ROW EXECUTE FUNCTION set_updated_at();
DROP TRIGGER IF EXISTS trg_customer_assets_updated_at ON customer_assets;
CREATE TRIGGER trg_customer_assets_updated_at BEFORE UPDATE ON customer_assets FOR EACH ROW EXECUTE FUNCTION set_updated_at();
DROP TRIGGER IF EXISTS trg_customer_configs_updated_at ON customer_configs;
CREATE TRIGGER trg_customer_configs_updated_at BEFORE UPDATE ON customer_configs FOR EACH ROW EXECUTE FUNCTION set_updated_at();
DROP TRIGGER IF EXISTS trg_strategy_configs_updated_at ON strategy_configs;
CREATE TRIGGER trg_strategy_configs_updated_at BEFORE UPDATE ON strategy_configs FOR EACH ROW EXECUTE FUNCTION set_updated_at();
DROP TRIGGER IF EXISTS trg_strategy_instances_updated_at ON strategy_instances;
CREATE TRIGGER trg_strategy_instances_updated_at BEFORE UPDATE ON strategy_instances FOR EACH ROW EXECUTE FUNCTION set_updated_at();
DROP TRIGGER IF EXISTS trg_strategy_signals_updated_at ON strategy_signals;
CREATE TRIGGER trg_strategy_signals_updated_at BEFORE UPDATE ON strategy_signals FOR EACH ROW EXECUTE FUNCTION set_updated_at();
DROP TRIGGER IF EXISTS trg_strategy_positions_updated_at ON strategy_positions;
CREATE TRIGGER trg_strategy_positions_updated_at BEFORE UPDATE ON strategy_positions FOR EACH ROW EXECUTE FUNCTION set_updated_at();
DROP TRIGGER IF EXISTS trg_strategy_performance_updated_at ON strategy_performance;
CREATE TRIGGER trg_strategy_performance_updated_at BEFORE UPDATE ON strategy_performance FOR EACH ROW EXECUTE FUNCTION set_updated_at();
DROP TRIGGER IF EXISTS trg_strategy_risk_monitor_updated_at ON strategy_risk_monitor;
CREATE TRIGGER trg_strategy_risk_monitor_updated_at BEFORE UPDATE ON strategy_risk_monitor FOR EACH ROW EXECUTE FUNCTION set_updated_at();
DROP TRIGGER IF EXISTS trg_system_announcements_updated_at ON system_announcements;
CREATE TRIGGER trg_system_announcements_updated_at BEFORE UPDATE ON system_announcements FOR EACH ROW EXECUTE FUNCTION set_updated_at();
DROP TRIGGER IF EXISTS trg_message_platforms_updated_at ON message_platforms;
CREATE TRIGGER trg_message_platforms_updated_at BEFORE UPDATE ON message_platforms FOR EACH ROW EXECUTE FUNCTION set_updated_at();
DROP TRIGGER IF EXISTS trg_message_forward_rules_updated_at ON message_forward_rules;
CREATE TRIGGER trg_message_forward_rules_updated_at BEFORE UPDATE ON message_forward_rules FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- ---- 视图 ----
CREATE OR REPLACE VIEW v_strategy_instances_overview AS
SELECT 
    si.id,
    si.instance_name,
    si.strategy_name,
    si.account_id,
    si.symbol,
    si.timeframe,
    si.status,
    si.started_at,
    si.stopped_at,
    si.last_signal_at,
    si.created_at,
    si.updated_at,
    sc.strategy_type,
    sc.is_template,
    COALESCE(sp.total_trades, 0) as total_trades,
    COALESCE(sp.win_rate, 0) as win_rate,
    COALESCE(sp.total_pnl, 0) as total_pnl,
    COALESCE(sp.max_drawdown, 0) as max_drawdown,
    COALESCE(sp.sharpe_ratio, 0) as sharpe_ratio
FROM strategy_instances si
LEFT JOIN strategy_configs sc ON si.strategy_name = sc.strategy_name
LEFT JOIN (
    SELECT 
        instance_id,
        SUM(total_trades) as total_trades,
        AVG(win_rate) as win_rate,
        SUM(total_pnl) as total_pnl,
        MIN(max_drawdown) as max_drawdown,
        AVG(sharpe_ratio) as sharpe_ratio
    FROM strategy_performance 
    GROUP BY instance_id
) sp ON si.id = sp.instance_id;
CREATE OR REPLACE VIEW v_strategy_performance_summary AS
SELECT 
    si.instance_name,
    si.strategy_name,
    si.symbol,
    si.status,
    COUNT(DISTINCT st.id) as total_trades,
    COUNT(DISTINCT CASE WHEN st.pnl > 0 THEN st.id END) as winning_trades,
    COUNT(DISTINCT CASE WHEN st.pnl < 0 THEN st.id END) as losing_trades,
    ROUND(COUNT(DISTINCT CASE WHEN st.pnl > 0 THEN st.id END) * 100.0 / COUNT(DISTINCT st.id), 2) as win_rate,
    COALESCE(SUM(st.pnl), 0) as total_pnl,
    COALESCE(SUM(st.commission), 0) as total_commission,
    COALESCE(AVG(st.pnl), 0) as avg_pnl,
    COALESCE(MAX(st.pnl), 0) as max_win,
    COALESCE(MIN(st.pnl), 0) as max_loss,
    si.started_at,
    si.last_signal_at
FROM strategy_instances si
LEFT JOIN strategy_trades st ON si.id = st.instance_id
GROUP BY si.id, si.instance_name, si.strategy_name, si.symbol, si.status, si.started_at, si.last_signal_at;

-- ---- 默认数据 ----
INSERT INTO strategy_configs (strategy_name, strategy_type, config_json, is_template, created_by) VALUES
('MA_Cross_Template', 'MA_Cross_Strategy', '{
    "short_period": 10,
    "long_period": 20,
    "ema_period": 12,
    "rsi_period": 14,
    "rsi_oversold": 30,
    "rsi_overbought": 70,
    "stop_loss_pct": 0.02,
    "take_profit_pct": 0.06,
    "trailing_stop": true,
    "trailing_stop_pct": 0.01,
    "min_volume_ratio": 1.2,
    "min_price_change": 0.005,
    "adx_threshold": 25,
    "volatility_threshold": 0.02,
    "symbol": "BTC-USDT",
    "timeframe": "1h",
    "risk_per_trade": 0.02,
    "max_positions": 3,
    "position_sizing": "fixed"
}', true, 'system'),

('Grid_Template', 'Grid_Strategy', '{
    "grid_levels": 10,
    "grid_spacing": 0.02,
    "base_price": 50000,
    "investment_per_grid": 1000,
    "dynamic_grid": true,
    "grid_adjustment_threshold": 0.1,
    "max_grid_adjustments": 3,
    "max_grid_positions": 5,
    "stop_loss_pct": 0.05,
    "take_profit_pct": 0.15,
    "enable_trend_following": false,
    "symbol": "BTC-USDT",
    "timeframe": "1h",
    "risk_per_trade": 0.02,
    "max_positions": 5,
    "position_sizing": "fixed"
}', true, 'system'),

('RSI_Template', 'RSI_Strategy', '{
    "rsi_period": 14,
    "rsi_oversold": 30,
    "rsi_overbought": 70,
    "stop_loss_pct": 0.03,
    "take_profit_pct": 0.08,
    "symbol": "BTC-USDT",
    "timeframe": "1h",
    "risk_per_trade": 0.02,
    "max_positions": 2,
    "position_sizing": "fixed"
}', true, 'system')
ON CONFLICT (strategy_name) DO NOTHING;
