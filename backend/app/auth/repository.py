"""User storage behind a small repository interface.

The rest of the auth layer depends only on the `UserRepository` Protocol and the
typed `User` dataclass — never on `sqlite3` or its `Row` type. Swapping to a real
database later (Postgres, etc.) is a new `UserRepository` implementation plus one
line at the bottom of this module; the service, deps, and router don't change.

The default implementation is `SqliteUserRepository`: stdlib `sqlite3`, kept
dependency-free and consistent with the hand-rolled cache and rate limiter. A
connection is opened per operation — simple and safe across FastAPI's threadpool
at v1 scale. Move to a connection pool / real DB if traffic grows.
"""

import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Protocol

from app.core.config import settings


@dataclass(frozen=True)
class User:
    """A user account, decoupled from the storage engine."""

    id: int
    username: str
    password_hash: str
    created_at: str


class UsernameTakenError(Exception):
    """Raised by a repository when a username already exists."""


class UserRepository(Protocol):
    """Storage contract the auth layer depends on."""

    def create_user(self, username: str, password_hash: str) -> User: ...
    def get_user_by_username(self, username: str) -> User | None: ...
    def get_user_by_id(self, user_id: int) -> User | None: ...


_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    username      TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    created_at    TEXT NOT NULL DEFAULT (datetime('now'))
);
"""


def _to_user(row: sqlite3.Row) -> User:
    return User(
        id=row["id"],
        username=row["username"],
        password_hash=row["password_hash"],
        created_at=row["created_at"],
    )


class SqliteUserRepository:
    """`UserRepository` backed by a local SQLite file.

    `database_path` is resolved lazily from settings on each connection (rather
    than captured at construction) so tests can repoint `settings.database_path`
    after the module is imported.
    """

    def __init__(self, database_path: str | None = None) -> None:
        self._database_path = database_path

    @contextmanager
    def _connect(self):
        conn = sqlite3.connect(self._database_path or settings.database_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def init_db(self) -> None:
        """Create tables if they don't exist. Idempotent; safe on startup."""
        with self._connect() as conn:
            conn.executescript(_SCHEMA)

    def create_user(self, username: str, password_hash: str) -> User:
        """Insert a user. Raises `UsernameTakenError` if the username is taken."""
        try:
            with self._connect() as conn:
                cur = conn.execute(
                    "INSERT INTO users (username, password_hash) VALUES (?, ?)",
                    (username, password_hash),
                )
                row = conn.execute(
                    "SELECT * FROM users WHERE id = ?", (cur.lastrowid,)
                ).fetchone()
        except sqlite3.IntegrityError as exc:
            raise UsernameTakenError(username) from exc
        return _to_user(row)

    def get_user_by_username(self, username: str) -> User | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM users WHERE username = ?", (username,)
            ).fetchone()
        return _to_user(row) if row else None

    def get_user_by_id(self, user_id: int) -> User | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM users WHERE id = ?", (user_id,)
            ).fetchone()
        return _to_user(row) if row else None

    def reset_users(self) -> None:
        """Test helper: wipe the users table."""
        with self._connect() as conn:
            conn.execute("DELETE FROM users")


# The single repository the app wires through. Swap these two lines to change the
# storage engine; nothing else in the auth layer references the engine. The
# concrete instance is also kept for lifecycle/test calls (`init_db`/`reset_users`)
# that aren't part of the storage contract.
_sqlite = SqliteUserRepository()
users: UserRepository = _sqlite


def init_db() -> None:
    """Create the schema on startup (delegates to the default repository)."""
    _sqlite.init_db()


def reset_users() -> None:
    """Test helper: wipe the users table."""
    _sqlite.reset_users()
