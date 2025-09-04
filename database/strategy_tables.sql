-- 策略配置表
CREATE TABLE IF NOT EXISTS strategy_configs (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    strategy_name VARCHAR(100) NOT NULL UNIQUE COMMENT '策略名称',
    strategy_type VARCHAR(50) NOT NULL COMMENT '策略类型',
    config_json JSON NOT NULL COMMENT '策略配置JSON',
    is_active BOOLEAN DEFAULT FALSE COMMENT '是否激活',
    is_template BOOLEAN DEFAULT FALSE COMMENT '是否为模板',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    created_by VARCHAR(50) COMMENT '创建者',
    version VARCHAR(20) DEFAULT '1.0.0' COMMENT '版本号',
    INDEX idx_strategy_type (strategy_type),
    INDEX idx_is_active (is_active),
    INDEX idx_created_at (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='策略配置表';

-- 策略实例表
CREATE TABLE IF NOT EXISTS strategy_instances (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    instance_name VARCHAR(100) NOT NULL UNIQUE COMMENT '实例名称',
    strategy_name VARCHAR(100) NOT NULL COMMENT '策略名称',
    account_id VARCHAR(50) NOT NULL COMMENT '关联账号ID',
    symbol VARCHAR(20) NOT NULL COMMENT '交易对',
    timeframe VARCHAR(10) NOT NULL COMMENT '时间框架',
    status ENUM('STOPPED', 'RUNNING', 'PAUSED', 'ERROR') DEFAULT 'STOPPED' COMMENT '运行状态',
    config_json JSON NOT NULL COMMENT '实例配置JSON',
    performance_json JSON COMMENT '性能数据JSON',
    started_at TIMESTAMP NULL COMMENT '启动时间',
    stopped_at TIMESTAMP NULL COMMENT '停止时间',
    last_signal_at TIMESTAMP NULL COMMENT '最后信号时间',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    created_by VARCHAR(50) COMMENT '创建者',
    INDEX idx_strategy_name (strategy_name),
    INDEX idx_account_id (account_id),
    INDEX idx_symbol (symbol),
    INDEX idx_status (status),
    INDEX idx_started_at (started_at),
    FOREIGN KEY (strategy_name) REFERENCES strategy_configs(strategy_name) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='策略实例表';

-- 交易信号表
CREATE TABLE IF NOT EXISTS strategy_signals (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    instance_id BIGINT NOT NULL COMMENT '策略实例ID',
    signal_id VARCHAR(50) NOT NULL COMMENT '信号ID',
    symbol VARCHAR(20) NOT NULL COMMENT '交易对',
    action ENUM('BUY', 'SELL', 'HOLD', 'CLOSE') NOT NULL COMMENT '交易动作',
    price DECIMAL(20,8) NOT NULL COMMENT '信号价格',
    quantity DECIMAL(20,8) NOT NULL COMMENT '数量',
    confidence DECIMAL(5,4) NOT NULL COMMENT '信号置信度',
    signal_strength DECIMAL(5,4) COMMENT '信号强度',
    stop_loss DECIMAL(20,8) COMMENT '止损价格',
    take_profit DECIMAL(20,8) COMMENT '止盈价格',
    metadata_json JSON COMMENT '信号元数据',
    status ENUM('PENDING', 'EXECUTED', 'REJECTED', 'CANCELLED') DEFAULT 'PENDING' COMMENT '信号状态',
    executed_at TIMESTAMP NULL COMMENT '执行时间',
    executed_price DECIMAL(20,8) COMMENT '执行价格',
    executed_quantity DECIMAL(20,8) COMMENT '执行数量',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    INDEX idx_instance_id (instance_id),
    INDEX idx_signal_id (signal_id),
    INDEX idx_symbol (symbol),
    INDEX idx_action (action),
    INDEX idx_status (status),
    INDEX idx_created_at (created_at),
    FOREIGN KEY (instance_id) REFERENCES strategy_instances(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='交易信号表';

-- 策略持仓表
CREATE TABLE IF NOT EXISTS strategy_positions (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    instance_id BIGINT NOT NULL COMMENT '策略实例ID',
    position_id VARCHAR(50) NOT NULL COMMENT '持仓ID',
    symbol VARCHAR(20) NOT NULL COMMENT '交易对',
    side ENUM('LONG', 'SHORT') NOT NULL COMMENT '持仓方向',
    quantity DECIMAL(20,8) NOT NULL COMMENT '持仓数量',
    entry_price DECIMAL(20,8) NOT NULL COMMENT '开仓价格',
    current_price DECIMAL(20,8) COMMENT '当前价格',
    unrealized_pnl DECIMAL(20,8) DEFAULT 0 COMMENT '未实现盈亏',
    stop_loss DECIMAL(20,8) COMMENT '止损价格',
    take_profit DECIMAL(20,8) COMMENT '止盈价格',
    entry_time TIMESTAMP NOT NULL COMMENT '开仓时间',
    exit_time TIMESTAMP NULL COMMENT '平仓时间',
    exit_price DECIMAL(20,8) COMMENT '平仓价格',
    realized_pnl DECIMAL(20,8) DEFAULT 0 COMMENT '已实现盈亏',
    status ENUM('OPEN', 'CLOSED', 'PARTIAL') DEFAULT 'OPEN' COMMENT '持仓状态',
    metadata_json JSON COMMENT '持仓元数据',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    INDEX idx_instance_id (instance_id),
    INDEX idx_position_id (position_id),
    INDEX idx_symbol (symbol),
    INDEX idx_side (side),
    INDEX idx_status (status),
    INDEX idx_entry_time (entry_time),
    FOREIGN KEY (instance_id) REFERENCES strategy_instances(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='策略持仓表';

-- 交易记录表
CREATE TABLE IF NOT EXISTS strategy_trades (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    instance_id BIGINT NOT NULL COMMENT '策略实例ID',
    trade_id VARCHAR(50) NOT NULL COMMENT '交易ID',
    position_id VARCHAR(50) COMMENT '关联持仓ID',
    symbol VARCHAR(20) NOT NULL COMMENT '交易对',
    side ENUM('BUY', 'SELL') NOT NULL COMMENT '交易方向',
    quantity DECIMAL(20,8) NOT NULL COMMENT '交易数量',
    price DECIMAL(20,8) NOT NULL COMMENT '交易价格',
    amount DECIMAL(20,8) NOT NULL COMMENT '交易金额',
    commission DECIMAL(20,8) DEFAULT 0 COMMENT '手续费',
    slippage DECIMAL(20,8) DEFAULT 0 COMMENT '滑点',
    pnl DECIMAL(20,8) DEFAULT 0 COMMENT '盈亏',
    trade_type ENUM('OPEN', 'CLOSE', 'PARTIAL') NOT NULL COMMENT '交易类型',
    reason VARCHAR(100) COMMENT '交易原因',
    metadata_json JSON COMMENT '交易元数据',
    executed_at TIMESTAMP NOT NULL COMMENT '执行时间',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    INDEX idx_instance_id (instance_id),
    INDEX idx_trade_id (trade_id),
    INDEX idx_position_id (position_id),
    INDEX idx_symbol (symbol),
    INDEX idx_side (side),
    INDEX idx_executed_at (executed_at),
    FOREIGN KEY (instance_id) REFERENCES strategy_instances(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='交易记录表';

-- 策略性能表
CREATE TABLE IF NOT EXISTS strategy_performance (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    instance_id BIGINT NOT NULL COMMENT '策略实例ID',
    date DATE NOT NULL COMMENT '统计日期',
    total_trades INT DEFAULT 0 COMMENT '总交易数',
    winning_trades INT DEFAULT 0 COMMENT '盈利交易数',
    losing_trades INT DEFAULT 0 COMMENT '亏损交易数',
    win_rate DECIMAL(5,4) DEFAULT 0 COMMENT '胜率',
    total_pnl DECIMAL(20,8) DEFAULT 0 COMMENT '总盈亏',
    realized_pnl DECIMAL(20,8) DEFAULT 0 COMMENT '已实现盈亏',
    unrealized_pnl DECIMAL(20,8) DEFAULT 0 COMMENT '未实现盈亏',
    max_drawdown DECIMAL(20,8) DEFAULT 0 COMMENT '最大回撤',
    profit_factor DECIMAL(10,4) DEFAULT 0 COMMENT '盈亏因子',
    sharpe_ratio DECIMAL(10,4) DEFAULT 0 COMMENT '夏普比率',
    max_consecutive_losses INT DEFAULT 0 COMMENT '最大连续亏损',
    current_consecutive_losses INT DEFAULT 0 COMMENT '当前连续亏损',
    average_win DECIMAL(20,8) DEFAULT 0 COMMENT '平均盈利',
    average_loss DECIMAL(20,8) DEFAULT 0 COMMENT '平均亏损',
    max_single_win DECIMAL(20,8) DEFAULT 0 COMMENT '最大单笔盈利',
    max_single_loss DECIMAL(20,8) DEFAULT 0 COMMENT '最大单笔亏损',
    daily_return DECIMAL(10,6) DEFAULT 0 COMMENT '日收益率',
    cumulative_return DECIMAL(10,6) DEFAULT 0 COMMENT '累计收益率',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    UNIQUE KEY uk_instance_date (instance_id, date),
    INDEX idx_instance_id (instance_id),
    INDEX idx_date (date),
    FOREIGN KEY (instance_id) REFERENCES strategy_instances(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='策略性能表';

-- 风险监控表
CREATE TABLE IF NOT EXISTS strategy_risk_monitor (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    instance_id BIGINT NOT NULL COMMENT '策略实例ID',
    risk_type VARCHAR(50) NOT NULL COMMENT '风险类型',
    risk_level ENUM('LOW', 'MEDIUM', 'HIGH', 'CRITICAL') NOT NULL COMMENT '风险等级',
    current_value DECIMAL(20,8) NOT NULL COMMENT '当前值',
    threshold_value DECIMAL(20,8) NOT NULL COMMENT '阈值',
    is_triggered BOOLEAN DEFAULT FALSE COMMENT '是否触发',
    triggered_at TIMESTAMP NULL COMMENT '触发时间',
    message TEXT COMMENT '风险信息',
    action_taken VARCHAR(200) COMMENT '采取的行动',
    resolved_at TIMESTAMP NULL COMMENT '解决时间',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    INDEX idx_instance_id (instance_id),
    INDEX idx_risk_type (risk_type),
    INDEX idx_risk_level (risk_level),
    INDEX idx_is_triggered (is_triggered),
    INDEX idx_triggered_at (triggered_at),
    FOREIGN KEY (instance_id) REFERENCES strategy_instances(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='风险监控表';

-- 回测记录表
CREATE TABLE IF NOT EXISTS strategy_backtests (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    strategy_name VARCHAR(100) NOT NULL COMMENT '策略名称',
    backtest_name VARCHAR(100) NOT NULL COMMENT '回测名称',
    start_date DATE NOT NULL COMMENT '开始日期',
    end_date DATE NOT NULL COMMENT '结束日期',
    initial_capital DECIMAL(20,8) NOT NULL COMMENT '初始资金',
    final_capital DECIMAL(20,8) NOT NULL COMMENT '最终资金',
    total_return DECIMAL(10,6) NOT NULL COMMENT '总收益率',
    max_drawdown DECIMAL(10,6) NOT NULL COMMENT '最大回撤',
    sharpe_ratio DECIMAL(10,4) NOT NULL COMMENT '夏普比率',
    total_trades INT NOT NULL COMMENT '总交易数',
    win_rate DECIMAL(5,4) NOT NULL COMMENT '胜率',
    profit_factor DECIMAL(10,4) NOT NULL COMMENT '盈亏因子',
    config_json JSON NOT NULL COMMENT '回测配置',
    results_json JSON COMMENT '详细结果',
    status ENUM('RUNNING', 'COMPLETED', 'FAILED') DEFAULT 'RUNNING' COMMENT '状态',
    started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '开始时间',
    completed_at TIMESTAMP NULL COMMENT '完成时间',
    created_by VARCHAR(50) COMMENT '创建者',
    INDEX idx_strategy_name (strategy_name),
    INDEX idx_backtest_name (backtest_name),
    INDEX idx_start_date (start_date),
    INDEX idx_end_date (end_date),
    INDEX idx_status (status),
    INDEX idx_started_at (started_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='回测记录表';

-- 市场数据缓存表
CREATE TABLE IF NOT EXISTS strategy_market_data (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    symbol VARCHAR(20) NOT NULL COMMENT '交易对',
    timeframe VARCHAR(10) NOT NULL COMMENT '时间框架',
    timestamp TIMESTAMP NOT NULL COMMENT '时间戳',
    open_price DECIMAL(20,8) NOT NULL COMMENT '开盘价',
    high_price DECIMAL(20,8) NOT NULL COMMENT '最高价',
    low_price DECIMAL(20,8) NOT NULL COMMENT '最低价',
    close_price DECIMAL(20,8) NOT NULL COMMENT '收盘价',
    volume DECIMAL(20,8) NOT NULL COMMENT '成交量',
    indicators_json JSON COMMENT '技术指标数据',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    UNIQUE KEY uk_symbol_timeframe_timestamp (symbol, timeframe, timestamp),
    INDEX idx_symbol (symbol),
    INDEX idx_timeframe (timeframe),
    INDEX idx_timestamp (timestamp)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='市场数据缓存表';

-- 策略日志表
CREATE TABLE IF NOT EXISTS strategy_logs (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    instance_id BIGINT COMMENT '策略实例ID',
    log_level ENUM('DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL') NOT NULL COMMENT '日志级别',
    message TEXT NOT NULL COMMENT '日志消息',
    module VARCHAR(50) COMMENT '模块名称',
    function_name VARCHAR(100) COMMENT '函数名称',
    line_number INT COMMENT '行号',
    exception_info TEXT COMMENT '异常信息',
    context_json JSON COMMENT '上下文信息',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    INDEX idx_instance_id (instance_id),
    INDEX idx_log_level (log_level),
    INDEX idx_created_at (created_at),
    FOREIGN KEY (instance_id) REFERENCES strategy_instances(id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='策略日志表';

-- 创建视图：策略实例概览
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

-- 创建视图：策略性能汇总
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

-- 插入默认策略配置
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
}', true, 'system'); 