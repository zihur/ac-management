import os
import shutil
import sys
import sqlite3
from typing import Callable


def _resolve_db_path() -> str:
    if not getattr(sys, "frozen", False):
        return "air_conditioner.db"

    local_app_data = os.environ.get("LOCALAPPDATA")
    if not local_app_data:
        local_app_data = os.path.join(os.path.expanduser("~"), "AppData", "Local")

    data_dir = os.path.join(local_app_data, "AC_Management")
    os.makedirs(data_dir, exist_ok=True)
    db_path = os.path.join(data_dir, "air_conditioner.db")

    # 從舊版 exe 同目錄自動搬移資料（若存在）
    legacy_path = os.path.join(os.path.dirname(sys.executable), "air_conditioner.db")
    if os.path.isfile(legacy_path) and not os.path.isfile(db_path):
        shutil.copy2(legacy_path, db_path)

    return db_path


DB_NAME = _resolve_db_path()

LATEST_SCHEMA_VERSION = 2


def get_db_connection():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    # 開啟 SQLite 的外鍵約束功能 (Foreign Key Support)
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


def _ensure_migrations_table(cursor: sqlite3.Cursor) -> None:
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version INTEGER PRIMARY KEY,
            applied_at TEXT DEFAULT (datetime('now'))
        )
    """)


def _get_current_version(cursor: sqlite3.Cursor) -> int:
    row = cursor.execute("SELECT MAX(version) FROM schema_migrations").fetchone()
    return row[0] or 0


def _migration_v1_ac_model_yearly(cursor: sqlite3.Cursor) -> None:
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS ac_model_yearly (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ac_model_id INTEGER NOT NULL,
            year INTEGER NOT NULL,
            official_retail_price REAL NOT NULL,
            discount_ratio REAL NOT NULL CHECK (discount_ratio > 0 AND discount_ratio <= 1),
            cadr REAL,
            notes TEXT,
            UNIQUE(ac_model_id, year),
            FOREIGN KEY (ac_model_id) REFERENCES ac_models (id) ON DELETE CASCADE
        )
    """)


def _migration_v2_discount_type(cursor: sqlite3.Cursor) -> None:
    """支援折數與固定扣款兩種優惠方式。"""
    columns = {
        row[1] for row in cursor.execute("PRAGMA table_info(ac_model_yearly)").fetchall()
    }
    if "discount_type" in columns:
        return

    cursor.execute("""
        CREATE TABLE ac_model_yearly_new (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ac_model_id INTEGER NOT NULL,
            year INTEGER NOT NULL,
            official_retail_price REAL NOT NULL,
            discount_type TEXT NOT NULL DEFAULT 'percent'
                CHECK (discount_type IN ('percent', 'fixed')),
            discount_ratio REAL CHECK (
                discount_ratio IS NULL OR (discount_ratio > 0 AND discount_ratio <= 1)
            ),
            discount_amount REAL CHECK (
                discount_amount IS NULL OR discount_amount >= 0
            ),
            cadr REAL,
            notes TEXT,
            UNIQUE(ac_model_id, year),
            FOREIGN KEY (ac_model_id) REFERENCES ac_models (id) ON DELETE CASCADE
        )
    """)
    cursor.execute("""
        INSERT INTO ac_model_yearly_new (
            id, ac_model_id, year, official_retail_price,
            discount_type, discount_ratio, discount_amount, cadr, notes
        )
        SELECT
            id, ac_model_id, year, official_retail_price,
            'percent', discount_ratio, NULL, cadr, notes
        FROM ac_model_yearly
    """)
    cursor.execute("DROP TABLE ac_model_yearly")
    cursor.execute("ALTER TABLE ac_model_yearly_new RENAME TO ac_model_yearly")


_MIGRATIONS: dict[int, Callable[[sqlite3.Cursor], None]] = {
    1: _migration_v1_ac_model_yearly,
    2: _migration_v2_discount_type,
}


def _apply_migrations(cursor: sqlite3.Cursor) -> None:
    current = _get_current_version(cursor)
    for version in sorted(_MIGRATIONS):
        if version > current:
            _MIGRATIONS[version](cursor)
            cursor.execute(
                "INSERT INTO schema_migrations (version) VALUES (?)",
                (version,),
            )


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

    # 4. 執行 schema migration（新增年度資料表等）
    _ensure_migrations_table(cursor)
    _apply_migrations(cursor)

    conn.commit()
    conn.close()
