import os
import secrets
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Response

router = APIRouter()

SESSION_CACHE_PREFIX = "auth.sessions."
SESSION_COOKIE_NAME = "ek_session"

_sessions = set()


def _get_webpass() -> Optional[str]:
    return os.environ.get("EK_WEBPASS")


def validate_webpass() -> None:
    if _get_webpass() == "your-password":
        raise ValueError("EK_WEBPASS cannot be the example password 'your-password'; choose a different password.")


def _get_token_from_request(request: Request) -> Optional[str]:
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        return auth.split(" ", 1)[1].strip()
    cookie = request.cookies.get(SESSION_COOKIE_NAME)
    if cookie:
        return cookie
    return None


def require_auth(request: Request):
    webpass = _get_webpass()
    if not webpass:
        return True
    token = _get_token_from_request(request)
    if not token:
        raise HTTPException(status_code=401, detail="Unauthorized")
    if (SESSION_CACHE_PREFIX + token) not in _sessions:
        raise HTTPException(status_code=401, detail="Invalid session")
    return True


async def get_current_user(request: Request):
    return require_auth(request)


@router.post("/auth/login")
async def login(payload: dict, response: Response):
    webpass = _get_webpass()
    if not webpass:
        raise HTTPException(status_code=503, detail="EK_WEBPASS is not set")
    password = str(payload.get("password", ""))
    if password != webpass:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    token = secrets.token_urlsafe(24)
    _sessions.add(SESSION_CACHE_PREFIX + token)
    response.set_cookie(SESSION_COOKIE_NAME, token, httponly=True, samesite="lax")
    return {"token": token}


@router.post("/auth/logout")
async def logout(request: Request, response: Response):
    token = _get_token_from_request(request)
    if token:
        key = SESSION_CACHE_PREFIX + token
        if key in _sessions:
            _sessions.remove(key)
    response.delete_cookie(SESSION_COOKIE_NAME)
    return {"success": True}


@router.get("/auth/me")
async def me(_: bool = Depends(require_auth)):
    return {"authenticated": True}
