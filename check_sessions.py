#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from database.db import get_db_pool

def check_sessions_table():
    try:
        db = get_db_pool()
        columns = db.query('DESCRIBE sessions')
        print('Sessions table structure:')
        for col in columns:
            print(f"{col['Field']}: {col['Type']}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    check_sessions_table()
