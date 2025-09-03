-- 资产分析相关数据库表

-- 资产快照表
CREATE TABLE IF NOT EXISTS asset_snapshots (
    id SERIAL PRIMARY KEY,
    customer_uid VARCHAR(100) NOT NULL,
    exchange VARCHAR(50) NOT NULL,
    timestamp TIMESTAMP NOT NULL,
    total_value DECIMAL(20, 8) NOT NULL DEFAULT 0,
    valuation_ccy VARCHAR(10) NOT NULL DEFAULT 'USD',
    balance_data JSONB,
    positions_data JSONB,
    risk_data JSONB,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    
    -- 索引
    INDEX idx_asset_snapshots_customer (customer_uid),
    INDEX idx_asset_snapshots_exchange (exchange),
    INDEX idx_asset_snapshots_timestamp (timestamp),
    INDEX idx_asset_snapshots_customer_exchange (customer_uid, exchange),
    INDEX idx_asset_snapshots_customer_timestamp (customer_uid, timestamp)
);

-- 资产趋势表
CREATE TABLE IF NOT EXISTS asset_trends (
    id SERIAL PRIMARY KEY,
    customer_uid VARCHAR(100) NOT NULL,
    exchange VARCHAR(50) NOT NULL,
    date VARCHAR(10) NOT NULL,
    timestamp BIGINT NOT NULL,
    total_value DECIMAL(20, 8) NOT NULL DEFAULT 0,
    change DECIMAL(20, 8) NOT NULL DEFAULT 0,
    change_percent DECIMAL(10, 4) NOT NULL DEFAULT 0,
    volume_24h DECIMAL(20, 8) DEFAULT 0,
    high_24h DECIMAL(20, 8) DEFAULT 0,
    low_24h DECIMAL(20, 8) DEFAULT 0,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    
    -- 索引
    INDEX idx_asset_trends_customer (customer_uid),
    INDEX idx_asset_trends_exchange (exchange),
    INDEX idx_asset_trends_date (date),
    INDEX idx_asset_trends_timestamp (timestamp),
    INDEX idx_asset_trends_customer_exchange (customer_uid, exchange),
    INDEX idx_asset_trends_customer_date (customer_uid, date)
);

-- 资产分析结果表
CREATE TABLE IF NOT EXISTS asset_analysis (
    id SERIAL PRIMARY KEY,
    customer_uid VARCHAR(100) NOT NULL,
    exchange VARCHAR(50) NOT NULL,
    analysis_time TIMESTAMP NOT NULL,
    total_assets DECIMAL(20, 8) NOT NULL DEFAULT 0,
    total_positions INTEGER NOT NULL DEFAULT 0,
    risk_level VARCHAR(20) NOT NULL DEFAULT 'unknown',
    asset_distribution JSONB,
    position_summary JSONB,
    risk_metrics JSONB,
    trend_analysis JSONB,
    recommendations JSONB,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    
    -- 索引
    INDEX idx_asset_analysis_customer (customer_uid),
    INDEX idx_asset_analysis_exchange (exchange),
    INDEX idx_asset_analysis_time (analysis_time),
    INDEX idx_asset_analysis_risk_level (risk_level),
    INDEX idx_asset_analysis_customer_exchange (customer_uid, exchange),
    INDEX idx_asset_analysis_customer_time (customer_uid, analysis_time)
);

-- 交易所资产汇总表
CREATE TABLE IF NOT EXISTS exchange_asset_summaries (
    id SERIAL PRIMARY KEY,
    exchange VARCHAR(50) NOT NULL UNIQUE,
    total_customers INTEGER NOT NULL DEFAULT 0,
    total_assets DECIMAL(20, 8) NOT NULL DEFAULT 0,
    avg_assets_per_customer DECIMAL(20, 8) NOT NULL DEFAULT 0,
    top_assets JSONB,
    risk_distribution JSONB,
    last_updated TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    
    -- 索引
    INDEX idx_exchange_asset_summaries_exchange (exchange),
    INDEX idx_exchange_asset_summaries_last_updated (last_updated)
);

-- 资产监控配置表
CREATE TABLE IF NOT EXISTS asset_monitor_config (
    id SERIAL PRIMARY KEY,
    customer_uid VARCHAR(100) NOT NULL,
    exchange VARCHAR(50) NOT NULL,
    enabled BOOLEAN NOT NULL DEFAULT true,
    snapshot_interval INTEGER NOT NULL DEFAULT 3600, -- 快照间隔（秒）
    trend_analysis_enabled BOOLEAN NOT NULL DEFAULT true,
    risk_alert_enabled BOOLEAN NOT NULL DEFAULT true,
    risk_threshold DECIMAL(10, 4) DEFAULT 0.1, -- 风险阈值（10%）
    alert_channels JSONB, -- 告警渠道配置
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    
    -- 索引
    INDEX idx_asset_monitor_config_customer (customer_uid),
    INDEX idx_asset_monitor_config_exchange (exchange),
    INDEX idx_asset_monitor_config_enabled (enabled),
    UNIQUE KEY uk_customer_exchange (customer_uid, exchange)
);

-- 资产告警记录表
CREATE TABLE IF NOT EXISTS asset_alerts (
    id SERIAL PRIMARY KEY,
    customer_uid VARCHAR(100) NOT NULL,
    exchange VARCHAR(50) NOT NULL,
    alert_type VARCHAR(50) NOT NULL, -- 告警类型：risk, trend, balance
    alert_level VARCHAR(20) NOT NULL, -- 告警级别：info, warning, danger
    title VARCHAR(200) NOT NULL,
    message TEXT,
    data JSONB, -- 告警相关数据
    is_read BOOLEAN NOT NULL DEFAULT false,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    
    -- 索引
    INDEX idx_asset_alerts_customer (customer_uid),
    INDEX idx_asset_alerts_exchange (exchange),
    INDEX idx_asset_alerts_type (alert_type),
    INDEX idx_asset_alerts_level (alert_level),
    INDEX idx_asset_alerts_read (is_read),
    INDEX idx_asset_alerts_created (created_at)
);

-- 创建视图：客户资产概览
CREATE OR REPLACE VIEW customer_asset_overview AS
SELECT 
    c.customer_uid,
    c.name,
    c.exchange,
    c.is_demo,
    c.enabled,
    COALESCE(s.total_value, 0) as current_total_value,
    COALESCE(s.total_value - c.init_asset, 0) as total_profit_loss,
    CASE 
        WHEN c.init_asset > 0 THEN 
            ROUND(((s.total_value - c.init_asset) / c.init_asset * 100), 2)
        ELSE 0 
    END as profit_loss_percent,
    s.timestamp as last_snapshot_time,
    a.risk_level,
    a.total_positions
FROM customers c
LEFT JOIN (
    SELECT DISTINCT ON (customer_uid) 
        customer_uid, 
        total_value, 
        timestamp
    FROM asset_snapshots 
    ORDER BY customer_uid, timestamp DESC
) s ON c.customer_uid = s.customer_uid
LEFT JOIN (
    SELECT DISTINCT ON (customer_uid) 
        customer_uid, 
        risk_level, 
        total_positions
    FROM asset_analysis 
    ORDER BY customer_uid, analysis_time DESC
) a ON c.customer_uid = a.customer_uid;

-- 创建视图：交易所资产统计
CREATE OR REPLACE VIEW exchange_asset_stats AS
SELECT 
    exchange,
    COUNT(DISTINCT customer_uid) as total_customers,
    SUM(total_value) as total_assets,
    AVG(total_value) as avg_assets_per_customer,
    MIN(total_value) as min_assets,
    MAX(total_value) as max_assets,
    COUNT(*) as total_snapshots,
    MAX(timestamp) as last_update
FROM asset_snapshots
GROUP BY exchange;

-- 创建视图：客户资产趋势
CREATE OR REPLACE VIEW customer_asset_trend AS
SELECT 
    customer_uid,
    exchange,
    date,
    total_value,
    change,
    change_percent,
    LAG(total_value) OVER (PARTITION BY customer_uid ORDER BY date) as prev_value,
    LAG(total_value, 7) OVER (PARTITION BY customer_uid ORDER BY date) as week_ago_value,
    LAG(total_value, 30) OVER (PARTITION BY customer_uid ORDER BY date) as month_ago_value
FROM asset_trends
ORDER BY customer_uid, date;

-- 插入示例数据（可选）
-- INSERT INTO asset_monitor_config (customer_uid, exchange, snapshot_interval) 
-- VALUES ('customer001', 'okx', 3600), ('customer002', 'binance', 1800); 