-- 添加策略实例表缺失的字段
-- 执行前请备份数据库！

-- 添加 is_demo 字段（交易模式：true=模拟盘，false=实盘）
ALTER TABLE strategy_instances
ADD COLUMN IF NOT EXISTS is_demo BOOLEAN DEFAULT true;

-- 添加 account_id 字段（关联客户账号）
ALTER TABLE strategy_instances
ADD COLUMN IF NOT EXISTS account_id VARCHAR(100);

-- 添加 signal_source_uid 字段（关联信号源）
ALTER TABLE strategy_instances
ADD COLUMN IF NOT EXISTS signal_source_uid VARCHAR(100);

-- 添加索引以提高查询性能
CREATE INDEX IF NOT EXISTS idx_strategy_instances_is_demo ON strategy_instances(is_demo);
CREATE INDEX IF NOT EXISTS idx_strategy_instances_account_id ON strategy_instances(account_id);
CREATE INDEX IF NOT EXISTS idx_strategy_instances_signal_source_uid ON strategy_instances(signal_source_uid);

-- 查看表结构确认
SELECT column_name, data_type, is_nullable, column_default
FROM information_schema.columns
WHERE table_name = 'strategy_instances'
ORDER BY ordinal_position;
