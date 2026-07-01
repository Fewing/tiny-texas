from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session as DbSession

from app.auth.dependencies import load_auth_context
from app.db import get_db
from app.web.templates import templates

router = APIRouter()


@router.get("/")
def index(request: Request, db: DbSession = Depends(get_db)):
    auth = load_auth_context(request, db)
    if auth is not None:
        return RedirectResponse("/lobby", status_code=303)
    return templates.TemplateResponse(request, "index.html", {"current_user": None})
