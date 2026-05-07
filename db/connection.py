"""
Unified DB connection layer for MSM Valve Management System.

If SUPABASE_URL + SUPABASE_SERVICE_KEY env vars are set → uses Supabase REST API.
Otherwise → falls back to local SQLite files.
"""
import os
import sqlite3
import traceback

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # dotenv not required in production (env vars set by Railway)

SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_KEY", "")
_USE_SUPABASE = bool(SUPABASE_URL and SUPABASE_KEY)

_sb_client = None
_sb_error = None

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")


def get_supabase():
    """Get or create the Supabase client singleton."""
    global _sb_client, _sb_error
    if _sb_client is None and _sb_error is None:
        try:
            from supabase import create_client
            _sb_client = create_client(SUPABASE_URL, SUPABASE_KEY)
        except Exception as e:
            _sb_error = traceback.format_exc()
            raise
    if _sb_error:
        raise RuntimeError(f"Supabase init failed: {_sb_error}")
    return _sb_client


def is_supabase():
    return _USE_SUPABASE


def get_init_error():
    return _sb_error


def get_sqlite(db_name="msm.sqlite"):
    """Get a local SQLite connection (fallback)."""
    db_path = os.path.join(DATA_DIR, db_name)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn
