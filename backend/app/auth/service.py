"""Account use-cases: input validation, registration, and authentication.

Sits between the router and the storage/security layers. Returns plain user
rows from the repository; the router maps those to response schemas.
"""

import sqlite3

from app.auth import repository
from app.auth.security import hash_password, verify_password

MIN_USERNAME_LEN = 3
MAX_USERNAME_LEN = 32
MIN_PASSWORD_LEN = 8
MAX_PASSWORD_LEN = 128


def validate_credentials(username: str, password: str) -> str | None:
    """Return an error message for invalid input, or None if acceptable."""
    username = username.strip()
    if not (MIN_USERNAME_LEN <= len(username) <= MAX_USERNAME_LEN):
        return f"Username must be {MIN_USERNAME_LEN}–{MAX_USERNAME_LEN} characters."
    if not (MIN_PASSWORD_LEN <= len(password) <= MAX_PASSWORD_LEN):
        return f"Password must be at least {MIN_PASSWORD_LEN} characters."
    return None


def register_user(username: str, password: str) -> sqlite3.Row:
    """Create a user. Raises ValueError if the username is already taken."""
    try:
        return repository.create_user(username.strip(), hash_password(password))
    except sqlite3.IntegrityError as exc:
        raise ValueError("That username is already taken.") from exc


def authenticate(username: str, password: str) -> sqlite3.Row | None:
    """Return the user row if credentials are valid, else None."""
    user = repository.get_user_by_username(username.strip())
    if user is None or not verify_password(password, user["password_hash"]):
        return None
    return user
