"""Account auth: password hashing, registration/login, and session dependencies.

Passwords are hashed with stdlib `hashlib.scrypt` (per-user random salt), so no
native build or extra crypto dependency is needed. Sessions are signed cookies
handled by Starlette's `SessionMiddleware`; we only stash the user id in
`request.session` and reload the user from SQLite per request.
"""

import hashlib
import hmac
import os
import sqlite3

from fastapi import HTTPException, Request

from app import db

# scrypt cost parameters. n=2**14, r=8, p=1 uses ~16 MB, under the default
# 32 MB limit, so no `maxmem` override is needed.
_N = 2**14
_R = 8
_P = 1
_DKLEN = 32

MIN_USERNAME_LEN = 3
MAX_USERNAME_LEN = 32
MIN_PASSWORD_LEN = 8
MAX_PASSWORD_LEN = 128


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    dk = hashlib.scrypt(password.encode(), salt=salt, n=_N, r=_R, p=_P, dklen=_DKLEN)
    return f"scrypt${salt.hex()}${dk.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, salt_hex, hash_hex = stored.split("$")
    except ValueError:
        return False
    if algo != "scrypt":
        return False
    salt = bytes.fromhex(salt_hex)
    dk = hashlib.scrypt(password.encode(), salt=salt, n=_N, r=_R, p=_P, dklen=_DKLEN)
    return hmac.compare_digest(dk.hex(), hash_hex)


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
        return db.create_user(username.strip(), hash_password(password))
    except sqlite3.IntegrityError as exc:
        raise ValueError("That username is already taken.") from exc


def authenticate(username: str, password: str) -> sqlite3.Row | None:
    """Return the user row if credentials are valid, else None."""
    user = db.get_user_by_username(username.strip())
    if user is None or not verify_password(password, user["password_hash"]):
        return None
    return user


def current_user(request: Request) -> sqlite3.Row | None:
    """FastAPI dependency: the logged-in user, or None."""
    user_id = request.session.get("user_id")
    if user_id is None:
        return None
    return db.get_user_by_id(user_id)


def require_user(request: Request) -> sqlite3.Row:
    """FastAPI dependency: the logged-in user, or 401."""
    user = current_user(request)
    if user is None:
        raise HTTPException(status_code=401, detail="Login required.")
    return user
