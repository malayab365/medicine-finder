"""FastAPI dependencies for resolving the logged-in user from the session.

Only `user_id` is stashed in the signed session cookie; the user is reloaded
from storage per request.
"""

from fastapi import HTTPException, Request

from app.auth.repository import User, users


def current_user(request: Request) -> User | None:
    """The logged-in user, or None."""
    user_id = request.session.get("user_id")
    if user_id is None:
        return None
    return users.get_user_by_id(user_id)


def require_user(request: Request) -> User:
    """The logged-in user, or 401."""
    user = current_user(request)
    if user is None:
        raise HTTPException(status_code=401, detail="Login required.")
    return user
