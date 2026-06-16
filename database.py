import os
import sqlite3
from datetime import datetime

# On Railway, mount a volume at /data and set DATA_DIR=/data
_DB_DIR = os.getenv("DATA_DIR", ".")
DB_FILE = os.path.join(_DB_DIR, "fund.db")


def init_db():
    os.makedirs(_DB_DIR, exist_ok=True)
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS transactions (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id    INTEGER NOT NULL,
            username   TEXT,
            full_name  TEXT,
            amount     INTEGER NOT NULL,
            date_str   TEXT NOT NULL,
            month_str  TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()


def save_transaction(user_id: int, username: str, full_name: str, amount: int):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    now = datetime.now()
    c.execute(
        "INSERT INTO transactions (user_id, username, full_name, amount, date_str, month_str) VALUES (?,?,?,?,?,?)",
        (user_id, username, full_name, amount,
         now.strftime("%d/%m/%Y %H:%M"),
         now.strftime("%m/%Y")),
    )
    conn.commit()
    conn.close()


def get_user_history(user_id: int):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    month_str = datetime.now().strftime("%m/%Y")
    c.execute(
        "SELECT full_name, amount, date_str FROM transactions WHERE user_id=? AND month_str=? ORDER BY created_at DESC",
        (user_id, month_str),
    )
    rows = c.fetchall()
    conn.close()
    return rows, sum(r[1] for r in rows)


def clear_user_history(user_id: int):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    month_str = datetime.now().strftime("%m/%Y")
    c.execute("DELETE FROM transactions WHERE user_id=? AND month_str=?", (user_id, month_str))
    deleted = c.rowcount
    conn.commit()
    conn.close()
    return deleted
