import os
import sys
import sqlite3

if getattr(sys, "frozen", False):
    DB_NAME = os.path.join(os.path.dirname(sys.executable), "air_conditioner.db")
else:
    DB_NAME = "air_conditioner.db"

def get_db_connection():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    # 開啟 SQLite 的外鍵約束功能 (Foreign Key Support)
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn

def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # 1. 建立品牌主表 (Lookup Table)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS brands (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL
        )
    """)

    # 2. 建立冷氣型號表 (使用 brand_id 作為外鍵)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS ac_models (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            brand_id INTEGER NOT NULL,
            model_number TEXT UNIQUE NOT NULL,
            cooling_capacity REAL NOT NULL,
            notes TEXT,
            FOREIGN KEY (brand_id) REFERENCES brands (id)
        )
    """)

    # 3. 預設植入基本品牌 (Seeds)
    default_brands = ["日立", "國際牌", "大金", "三菱", "禾聯", "奇美"]
    for brand_name in default_brands:
        cursor.execute("INSERT OR IGNORE INTO brands (name) VALUES (?)", (brand_name,))

    conn.commit()
    conn.close()