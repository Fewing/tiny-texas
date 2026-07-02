from __future__ import annotations

import secrets

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from app.auth.dependencies import load_auth_context, require_csrf
from app.auth.security import create_session, delete_session_by_token, hash_password, verify_password
from app.config import settings
from app.db import get_db
from app.db.models import User
from app.web.templates import templates

router = APIRouter()


def _set_session_cookie(response: RedirectResponse, token: str) -> None:
    response.set_cookie(
        settings.session_cookie_name,
        token,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        max_age=settings.session_days * 24 * 60 * 60,
    )


def _valid_invite_code(invite_code: str) -> bool:
    expected = settings.registration_invite_code
    return bool(expected) and secrets.compare_digest(invite_code.strip(), expected)


@router.get("/login")
def login_page(request: Request, db: DbSession = Depends(get_db)):
    auth = load_auth_context(request, db)
    if auth is not None:
        return RedirectResponse("/lobby", status_code=303)
    return templates.TemplateResponse(request, "auth/login.html", {"current_user": None})


@router.post("/login")
def login(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    db: DbSession = Depends(get_db),
):
    user = db.execute(select(User).where(User.username == username.strip())).scalar_one_or_none()
    if user is None or not verify_password(password, user.password_hash):
        return templates.TemplateResponse(
            request,
            "auth/login.html",
            {"current_user": None, "error": "用户名或密码错误。"},
            status_code=400,
        )
    token, _session = create_session(db, user)
    response = RedirectResponse("/lobby", status_code=303)
    _set_session_cookie(response, token)
    return response


@router.get("/register")
def register_page(request: Request, db: DbSession = Depends(get_db)):
    auth = load_auth_context(request, db)
    if auth is not None:
        return RedirectResponse("/lobby", status_code=303)
    return templates.TemplateResponse(request, "auth/register.html", {"current_user": None})


@router.post("/register")
def register(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    invite_code: str = Form(""),
    db: DbSession = Depends(get_db),
):
    clean_username = username.strip()
    if not _valid_invite_code(invite_code):
        return templates.TemplateResponse(
            request,
            "auth/register.html",
            {"current_user": None, "error": "邀请码无效。"},
            status_code=400,
        )
    if len(clean_username) < 3 or len(clean_username) > 32:
        return templates.TemplateResponse(
            request,
            "auth/register.html",
            {"current_user": None, "error": "用户名长度必须为 3-32 个字符。"},
            status_code=400,
        )
    if len(password) < 8:
        return templates.TemplateResponse(
            request,
            "auth/register.html",
            {"current_user": None, "error": "密码至少需要 8 个字符。"},
            status_code=400,
        )
    existing = db.execute(select(User).where(User.username == clean_username)).scalar_one_or_none()
    if existing is not None:
        return templates.TemplateResponse(
            request,
            "auth/register.html",
            {"current_user": None, "error": "用户名已被占用。"},
            status_code=400,
        )
    user = User(username=clean_username, password_hash=hash_password(password))
    db.add(user)
    db.commit()
    db.refresh(user)
    token, _session = create_session(db, user)
    response = RedirectResponse("/lobby", status_code=303)
    _set_session_cookie(response, token)
    return response


@router.post("/logout")
def logout(
    request: Request,
    csrf_token: str = Form(...),
    db: DbSession = Depends(get_db),
):
    require_csrf(request, db, csrf_token)
    token = request.cookies.get(settings.session_cookie_name)
    delete_session_by_token(db, token)
    response = RedirectResponse("/", status_code=303)
    response.delete_cookie(settings.session_cookie_name)
    return response
