import sqlite3
import os
from contextlib import contextmanager

def get_db_connection():
    db_path = "/tmp/media.db" if os.environ.get('VERCEL') else "media.db"
    conn = sqlite3.connect(db_path, timeout=10, check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.row_factory = sqlite3.Row
    return conn

@contextmanager
def get_db():
    conn = get_db_connection()
    try:
        yield conn
    finally:
        conn.close()

def init_db():
    if os.environ.get('VERCEL'):
        os.makedirs("/tmp", exist_ok=True)
    with get_db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS medias (
                id TEXT PRIMARY KEY,
                product_id TEXT NOT NULL,
                file_name TEXT NOT NULL,
                file_url TEXT NOT NULL,
                file_type TEXT CHECK(file_type IN ('image', 'video')),
                is_thumbnail INTEGER DEFAULT 0 CHECK(
                    (file_type = 'image' AND is_thumbnail IN (0, 1)) OR
                    (file_type = 'video' AND is_thumbnail = 0)
                ),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)