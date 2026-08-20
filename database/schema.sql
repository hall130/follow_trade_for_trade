-- =====================================================================
-- 数据库总建表入口
-- 按依赖顺序汇总执行本项目所有建表脚本。
--
-- 用法:
--   mysql -u<user> -p<password> <database> < database/schema.sql
--
-- 或在 MySQL 客户端中:
--   USE <database>;
--   SOURCE database/core_tables.sql;
--   SOURCE database/strategy_tables.sql;
--   SOURCE database/announcements_schema.sql;
--   SOURCE database/message_forward_schema_mysql.sql;
--
-- 说明:
--   * core_tables.sql                    -- 认证/权限/会员/支付/核心跟单/限价跟单/
--                                            做市商/止损/手动操作/仓位异常/订阅邀请码等 (55张表)
--   * strategy_tables.sql                -- 策略交易(strategy_*)系列表与视图 (原有)
--   * announcements_schema.sql           -- 系统公告表 (init_announcements.py 加载)
--   * message_forward_schema_mysql.sql   -- 消息转发平台/规则/历史表 (db_operations_mysql.py 加载)
--
--   所有脚本均使用 CREATE TABLE IF NOT EXISTS, 可重复执行。
-- =====================================================================

SOURCE database/core_tables.sql;
SOURCE database/strategy_tables.sql;
SOURCE database/announcements_schema.sql;
SOURCE database/message_forward_schema_mysql.sql;
