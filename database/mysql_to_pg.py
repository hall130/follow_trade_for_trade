#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MySQL DDL -> PostgreSQL DDL 翻译器

把项目里的 MySQL 建表脚本机械翻译成 PostgreSQL 方言，输出到 database/pg_schema.sql。

转换规则：
  * BIGINT [UNSIGNED] NOT NULL AUTO_INCREMENT  -> BIGSERIAL（保留 inline PRIMARY KEY）
  * TINYINT(1)/TINYINT                         -> SMALLINT（保留 0/1 语义，兼容 enabled=1 查询）
  * BOOLEAN                                     -> BOOLEAN（PG 原生，strategy_* 子系统用 true/false）
  * DATETIME                                   -> TIMESTAMP
  * LONGTEXT/MEDIUMTEXT                        -> TEXT
  * JSON                                       -> JSONB
  * ENUM(...)                                  -> VARCHAR(50)
  * `反引号`                                    -> 去除
  * KEY/INDEX 行（表内联索引）                  -> 独立 CREATE INDEX（表名前缀避免重名）
  * UNIQUE KEY name (cols)                     -> 独立 CREATE UNIQUE INDEX（可作 ON CONFLICT 目标）
  * COMMENT '...'                              -> 去除
  * ON UPDATE CURRENT_TIMESTAMP                -> 去除（改用 updated_at 触发器）
  * ) ENGINE=... COMMENT='...'                 -> );
  * SET NAMES / SET FOREIGN_KEY_CHECKS         -> 去除
  * SOURCE ...                                 -> 忽略（本脚本直接合并各文件）
  * 含 updated_at 列的表                        -> 生成 BEFORE UPDATE 触发器自动刷新时间
"""
import re
import os

BASE = os.path.dirname(os.path.abspath(__file__))

# 按依赖顺序合并
FILES = [
    'core_tables.sql',
    'strategy_tables.sql',
    'announcements_schema.sql',
    'message_forward_schema_mysql.sql',
]

OUTPUT = os.path.join(BASE, 'pg_schema.sql')


def strip_comment(line: str) -> str:
    """去除列/表定义里的 COMMENT '...'"""
    return re.sub(r"\s+COMMENT\s+'[^']*'", '', line, flags=re.IGNORECASE)


def convert_type(col_line: str) -> str:
    """转换单个列定义的数据类型"""
    line = col_line

    # AUTO_INCREMENT 列 -> BIGSERIAL
    if re.search(r'AUTO_INCREMENT', line, re.IGNORECASE):
        colname = line.split()[0]
        if re.search(r'PRIMARY\s+KEY', line, re.IGNORECASE):
            return f'{colname} BIGSERIAL PRIMARY KEY'
        return f'{colname} BIGSERIAL'

    # UNSIGNED 去除
    line = re.sub(r'\s+UNSIGNED', '', line, flags=re.IGNORECASE)
    # ON UPDATE CURRENT_TIMESTAMP 去除（触发器处理）
    line = re.sub(r'\s+ON\s+UPDATE\s+CURRENT_TIMESTAMP', '', line, flags=re.IGNORECASE)
    # ENUM(...) -> VARCHAR(50)
    line = re.sub(r'ENUM\s*\([^)]*\)', 'VARCHAR(50)', line, flags=re.IGNORECASE)
    # 类型替换（保守，作用于类型位置的独立单词）
    line = re.sub(r'\bTINYINT\s*\(\s*1\s*\)', 'SMALLINT', line, flags=re.IGNORECASE)
    line = re.sub(r'\bTINYINT\b(?!\s*\()', 'SMALLINT', line, flags=re.IGNORECASE)
    line = re.sub(r'\bTINYINT\s*\(\s*\d+\s*\)', 'SMALLINT', line, flags=re.IGNORECASE)
    # BOOL/BOOLEAN -> SMALLINT（代码里以 1/0 语义使用，配合 db.py 的全局 bool 适配器）
    line = re.sub(r'\bBOOLEAN\b', 'SMALLINT', line, flags=re.IGNORECASE)
    line = re.sub(r'\bBOOL\b', 'SMALLINT', line, flags=re.IGNORECASE)
    # SMALLINT 列上的 DEFAULT TRUE/FALSE -> 1/0
    line = re.sub(r'(SMALLINT[^,]*DEFAULT\s+)TRUE\b', r'\g<1>1', line, flags=re.IGNORECASE)
    line = re.sub(r'(SMALLINT[^,]*DEFAULT\s+)FALSE\b', r'\g<1>0', line, flags=re.IGNORECASE)
    line = re.sub(r'\bLONGTEXT\b', 'TEXT', line, flags=re.IGNORECASE)
    line = re.sub(r'\bMEDIUMTEXT\b', 'TEXT', line, flags=re.IGNORECASE)
    line = re.sub(r'\bDATETIME\b', 'TIMESTAMP', line, flags=re.IGNORECASE)
    # JSON -> JSONB（大写类型；列名里的 _json 是小写，不受影响）
    line = re.sub(r'\bJSON\b', 'JSONB', line)
    return line


def parse_create_table(block: str):
    """
    解析单个 CREATE TABLE 语句，返回 (create_sql, [index_sql...], table_name, has_updated_at)
    """
    m = re.search(r'CREATE\s+TABLE\s+(IF\s+NOT\s+EXISTS\s+)?`?(\w+)`?\s*\((.*)\)\s*ENGINE',
                  block, re.IGNORECASE | re.DOTALL)
    if not m:
        # 没有 ENGINE 结尾（少见），退化处理
        m = re.search(r'CREATE\s+TABLE\s+(IF\s+NOT\s+EXISTS\s+)?`?(\w+)`?\s*\((.*)\)\s*;',
                      block, re.IGNORECASE | re.DOTALL)
        if not m:
            return None
    table = m.group(2)
    body = m.group(3)

    # 按行拆分表体，逐条处理（每列/约束一行，以逗号结尾）
    raw_lines = [l.strip() for l in body.split('\n') if l.strip()]

    col_defs = []
    constraints = []
    indexes = []
    has_updated_at = False

    for line in raw_lines:
        line = line.rstrip(',').strip()
        if not line:
            continue
        line = line.replace('`', '')
        line = strip_comment(line)
        upper = line.upper()

        # UNIQUE KEY name (cols) -> 独立唯一索引
        mu = re.match(r'UNIQUE\s+KEY\s+(\w+)\s*\(([^)]*)\)', line, re.IGNORECASE)
        if mu:
            idx_name, cols = mu.group(1), mu.group(2)
            indexes.append(
                f'CREATE UNIQUE INDEX IF NOT EXISTS {table}_{idx_name} ON {table} ({cols});')
            continue

        # KEY/INDEX name (cols) -> 独立索引
        mk = re.match(r'(?:KEY|INDEX)\s+(\w+)\s*\(([^)]*)\)', line, re.IGNORECASE)
        if mk:
            idx_name, cols = mk.group(1), mk.group(2)
            indexes.append(
                f'CREATE INDEX IF NOT EXISTS {table}_{idx_name} ON {table} ({cols});')
            continue

        # 表级约束保留
        if upper.startswith('PRIMARY KEY') or upper.startswith('CONSTRAINT') \
                or upper.startswith('FOREIGN KEY') or upper.startswith('UNIQUE ('):
            constraints.append(line)
            continue

        # 普通列定义
        if re.search(r'\bupdated_at\b', line, re.IGNORECASE):
            has_updated_at = True
        col_defs.append(convert_type(line))

    all_defs = col_defs + constraints
    create_sql = (f'CREATE TABLE IF NOT EXISTS {table} (\n    '
                  + ',\n    '.join(all_defs) + '\n);')
    return create_sql, indexes, table, has_updated_at


def main():
    all_create = []
    all_index = []
    all_views = []
    all_inserts = []
    updated_at_tables = []

    for fname in FILES:
        path = os.path.join(BASE, fname)
        with open(path, 'r', encoding='utf-8') as f:
            content = f.read()

        # 去除 SET 语句
        content = re.sub(r'SET\s+NAMES[^;]*;', '', content, flags=re.IGNORECASE)
        content = re.sub(r'SET\s+FOREIGN_KEY_CHECKS[^;]*;', '', content, flags=re.IGNORECASE)

        # 提取 CREATE TABLE 块
        for tbl_m in re.finditer(
                r'CREATE\s+TABLE\s+IF\s+NOT\s+EXISTS.*?\)\s*ENGINE[^;]*;',
                content, re.IGNORECASE | re.DOTALL):
            parsed = parse_create_table(tbl_m.group(0))
            if parsed:
                create_sql, indexes, table, has_upd = parsed
                all_create.append(create_sql)
                all_index.extend(indexes)
                if has_upd:
                    updated_at_tables.append(table)

        # 提取 VIEW（PG 兼容，去反引号即可）
        for view_m in re.finditer(
                r'CREATE\s+OR\s+REPLACE\s+VIEW.*?;',
                content, re.IGNORECASE | re.DOTALL):
            all_views.append(view_m.group(0).replace('`', ''))

        # 提取 INSERT（默认数据）
        for ins_m in re.finditer(
                r'INSERT\s+INTO.*?;',
                content, re.IGNORECASE | re.DOTALL):
            all_inserts.append(ins_m.group(0).replace('`', ''))

    # 组装输出
    out = []
    out.append('-- =====================================================================')
    out.append('-- PostgreSQL + TimescaleDB 建表脚本（由 mysql_to_pg.py 自动生成）')
    out.append('-- 源: core_tables.sql / strategy_tables.sql / announcements_schema.sql /')
    out.append('--     message_forward_schema_mysql.sql')
    out.append('-- 执行: psql -U postgres -d trade_db -f database/pg_schema.sql')
    out.append('-- =====================================================================')
    out.append('')
    out.append('-- updated_at 自动刷新触发器函数')
    out.append("""CREATE OR REPLACE FUNCTION set_updated_at() RETURNS trigger AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;""")
    out.append('')

    out.append('-- ---- 表 ----')
    out.extend(all_create)
    out.append('')

    out.append('-- ---- 索引 ----')
    out.extend(all_index)
    out.append('')

    out.append('-- ---- updated_at 触发器 ----')
    for t in updated_at_tables:
        out.append(f'DROP TRIGGER IF EXISTS trg_{t}_updated_at ON {t};')
        out.append(f'CREATE TRIGGER trg_{t}_updated_at BEFORE UPDATE ON {t} '
                   f'FOR EACH ROW EXECUTE FUNCTION set_updated_at();')
    out.append('')

    out.append('-- ---- 视图 ----')
    out.extend(all_views)
    out.append('')

    out.append('-- ---- 默认数据 ----')
    for ins in all_inserts:
        # ON CONFLICT 保护：默认策略配置按 strategy_name 唯一
        if 'strategy_configs' in ins.lower():
            ins = ins.rstrip(';') + '\nON CONFLICT (strategy_name) DO NOTHING;'
        out.append(ins)
    out.append('')

    with open(OUTPUT, 'w', encoding='utf-8') as f:
        f.write('\n'.join(out))

    print(f'[OK] 生成 {OUTPUT}')
    print(f'  表: {len(all_create)}  索引: {len(all_index)}  '
          f'视图: {len(all_views)}  INSERT: {len(all_inserts)}  '
          f'updated_at触发器: {len(updated_at_tables)}')


if __name__ == '__main__':
    main()
