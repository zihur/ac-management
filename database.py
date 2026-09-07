import sqlite3

DB_NAME = "air_conditioner.db"


def get_db_connection():
    """建立資料庫連線並設定 Row 格式"""
    conn = sqlite3.connect(DB_NAME)
    # 讓查詢結果能像字典一樣用 key 取值 (例如 row["brand"])
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """初始化資料庫與建立資料表"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS ac_models (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            brand TEXT NOT NULL,
            model_number TEXT UNIQUE NOT NULL,
            cooling_capacity REAL NOT NULL,
            notes TEXT
        )
    """)
    conn.commit()
    conn.close()