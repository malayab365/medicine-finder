"""Tiny SQLite layer for user accounts.

Kept dependency-free with stdlib `sqlite3`, consistent with the hand-rolled
cache and rate limiter. A connection is opened per operation — simple and safe
across FastAPI's threadpool at v1 scale. Move to a connection pool / real DB if
traffic grows.
"""

import sqlite3
from contextlib import contextmanager

from app.config import settings

_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    username      TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    created_at    TEXT NOT NULL DEFAULT (datetime('now'))
);
"""


@contextmanager
def _connect():
    conn = sqlite3.connect(settings.database_path)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    """Create tables if they don't exist. Idempotent; safe to call on startup."""
    with _connect() as conn:
        conn.executescript(_SCHEMA)


def create_user(username: str, password_hash: str) -> sqlite3.Row:
    """Insert a user. Raises sqlite3.IntegrityError if the username is taken."""
    with _connect() as conn:
        cur = conn.execute(
            "INSERT INTO users (username, password_hash) VALUES (?, ?)",
            (username, password_hash),
        )
        row = conn.execute(
            "SELECT * FROM users WHERE id = ?", (cur.lastrowid,)
        ).fetchone()
    return row


def get_user_by_username(username: str) -> sqlite3.Row | None:
    with _connect() as conn:
        return conn.execute(
            "SELECT * FROM users WHERE username = ?", (username,)
        ).fetchone()


def get_user_by_id(user_id: int) -> sqlite3.Row | None:
    with _connect() as conn:
        return conn.execute(
            "SELECT * FROM users WHERE id = ?", (user_id,)
        ).fetchone()


def reset_users() -> None:
    """Test helper: wipe the users table."""
    with _connect() as conn:
        conn.execute("DELETE FROM users")
