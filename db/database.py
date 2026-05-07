"""SQLite connection helper for MSM Quote System."""
import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "msm.sqlite")
SCHEMA_PATH = os.path.join(os.path.dirname(__file__), "schema.sql")


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = get_connection()
    with open(SCHEMA_PATH) as f:
        conn.executescript(f.read())
    conn.close()


if __name__ == "__main__":
    init_db()
    print(f"Database initialized at {os.path.abspath(DB_PATH)}")
