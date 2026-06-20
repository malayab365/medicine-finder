"""Auth endpoints: register / login / logout / me (JSON API)."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response

from app.auth import service
from app.auth.deps import require_user
from app.auth.repository import User
from app.auth.schemas import AuthRequest, UserResponse

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=UserResponse, status_code=201)
async def register(req: AuthRequest, request: Request) -> UserResponse:
    error = service.validate_credentials(req.username, req.password)
    if error:
        raise HTTPException(status_code=400, detail=error)
    try:
        user = service.register_user(req.username, req.password)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    request.session["user_id"] = user.id
    return UserResponse(id=user.id, username=user.username)


@router.post("/login", response_model=UserResponse)
async def login(req: AuthRequest, request: Request) -> UserResponse:
    user = service.authenticate(req.username, req.password)
    if user is None:
        raise HTTPException(status_code=401, detail="Invalid username or password.")
    request.session["user_id"] = user.id
    return UserResponse(id=user.id, username=user.username)


@router.post("/logout", status_code=204)
async def logout(request: Request) -> Response:
    request.session.clear()
    return Response(status_code=204)


@router.get("/me", response_model=UserResponse)
async def me(user: Annotated[User, Depends(require_user)]) -> UserResponse:
    return UserResponse(id=user.id, username=user.username)
