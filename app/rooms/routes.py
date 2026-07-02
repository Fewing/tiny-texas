from __future__ import annotations

import secrets
import string
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Form, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from sqlalchemy import delete, select
from sqlalchemy.orm import Session as DbSession

from app.auth.dependencies import load_auth_context, require_csrf
from app.db import get_db
from app.db.models import Room, RoomPlayer
from app.game.runtime import GameError
from app.web.templates import templates

router = APIRouter()

ROOM_CODE_ALPHABET = string.ascii_uppercase + string.digits


@router.get("/lobby")
def lobby(request: Request, db: DbSession = Depends(get_db)):
    auth = load_auth_context(request, db)
    if auth is None:
        return RedirectResponse("/login", status_code=303)
    rooms = db.execute(select(Room).order_by(Room.created_at.desc())).scalars().all()
    return templates.TemplateResponse(
        request,
        "rooms/lobby.html",
        {"current_user": auth.user, "csrf_token": auth.session.csrf_token, "rooms": rooms},
    )


@router.post("/rooms")
def create_room(
    request: Request,
    name: str = Form(...),
    seat_count: int = Form(6),
    small_blind: int = Form(5),
    big_blind: int = Form(10),
    buy_in: int = Form(1000),
    csrf_token: str = Form(...),
    db: DbSession = Depends(get_db),
):
    auth = require_csrf(request, db, csrf_token)
    if not 2 <= seat_count <= 9:
        raise HTTPException(status_code=400, detail="座位数必须在 2 到 9 之间。")
    if small_blind <= 0 or big_blind <= small_blind or buy_in < big_blind * 20:
        raise HTTPException(status_code=400, detail="盲注或买入筹码配置无效。")

    room = Room(
        code=_new_room_code(db),
        name=name.strip()[:80] or "小牌桌",
        creator_id=auth.user.id,
        seat_count=seat_count,
        small_blind=small_blind,
        big_blind=big_blind,
        buy_in=buy_in,
    )
    db.add(room)
    db.flush()
    db.add(RoomPlayer(room_id=room.id, user_id=auth.user.id, player_type="human"))
    db.commit()
    return RedirectResponse(f"/rooms/{room.code}", status_code=303)


@router.get("/rooms/{code}")
async def room_detail(request: Request, code: str, db: DbSession = Depends(get_db)):
    auth = load_auth_context(request, db)
    if auth is None:
        return RedirectResponse("/login", status_code=303)
    room = _get_room_or_404(db, code)
    service = request.app.state.game_service
    runtime = await service.sync_room(db, room)
    room_player = _get_room_player(db, room.id, auth.user.id)
    return templates.TemplateResponse(
        request,
        "rooms/detail.html",
        {
            "current_user": auth.user,
            "csrf_token": auth.session.csrf_token,
            "room": room,
            "room_player": room_player,
            "initial_state": runtime.public_state(auth.user.id),
            "error": request.query_params.get("error"),
        },
    )


@router.post("/rooms/{code}/join")
async def join_room(
    request: Request,
    code: str,
    csrf_token: str = Form(...),
    db: DbSession = Depends(get_db),
):
    auth = require_csrf(request, db, csrf_token)
    room = _get_room_or_404(db, code)
    room_player = _get_room_player(db, room.id, auth.user.id)
    if room_player is None:
        db.add(RoomPlayer(room_id=room.id, user_id=auth.user.id, player_type="human"))
    else:
        room_player.left_at = None
    db.commit()
    await request.app.state.game_service.sync_room(db, room)
    return RedirectResponse(f"/rooms/{room.code}", status_code=303)


@router.post("/rooms/{code}/delete")
async def delete_room(
    request: Request,
    code: str,
    csrf_token: str = Form(...),
    db: DbSession = Depends(get_db),
):
    auth = require_csrf(request, db, csrf_token)
    room = _get_room_or_404(db, code)
    if room.creator_id != auth.user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="只有房间创建者可以删除房间。")

    room_code = room.code
    db.execute(delete(RoomPlayer).where(RoomPlayer.room_id == room.id))
    db.delete(room)
    db.commit()

    request.app.state.room_manager.remove(room_code)
    await request.app.state.connection_manager.close_room(room_code)
    return RedirectResponse("/lobby", status_code=303)


@router.post("/rooms/{code}/seat")
async def take_seat(
    request: Request,
    code: str,
    seat_index: int = Form(...),
    csrf_token: str = Form(...),
    db: DbSession = Depends(get_db),
):
    auth = require_csrf(request, db, csrf_token)
    room = _get_room_or_404(db, code)
    try:
        await request.app.state.game_service.take_seat(db, room, auth.user, seat_index)
    except GameError as exc:
        return _redirect_room(room.code, str(exc))
    return RedirectResponse(f"/rooms/{room.code}", status_code=303)


@router.post("/rooms/{code}/stand")
async def stand(
    request: Request,
    code: str,
    csrf_token: str = Form(...),
    db: DbSession = Depends(get_db),
):
    auth = require_csrf(request, db, csrf_token)
    room = _get_room_or_404(db, code)
    try:
        await request.app.state.game_service.stand(db, room, auth.user)
    except GameError as exc:
        return _redirect_room(room.code, str(exc))
    return RedirectResponse(f"/rooms/{room.code}", status_code=303)


@router.post("/rooms/{code}/ready")
async def ready(
    request: Request,
    code: str,
    csrf_token: str = Form(...),
    db: DbSession = Depends(get_db),
):
    auth = require_csrf(request, db, csrf_token)
    room = _get_room_or_404(db, code)
    try:
        await request.app.state.game_service.set_ready(room, auth.user, True)
    except GameError as exc:
        return _redirect_room(room.code, str(exc))
    return RedirectResponse(f"/rooms/{room.code}", status_code=303)


def _new_room_code(db: DbSession) -> str:
    while True:
        code = "".join(secrets.choice(ROOM_CODE_ALPHABET) for _ in range(6))
        exists = db.execute(select(Room.id).where(Room.code == code)).scalar_one_or_none()
        if exists is None:
            return code


def _get_room_or_404(db: DbSession, code: str) -> Room:
    room = db.execute(select(Room).where(Room.code == code.upper())).scalar_one_or_none()
    if room is None:
        raise HTTPException(status_code=404, detail="房间不存在。")
    return room


def _get_room_player(db: DbSession, room_id: int, user_id: int) -> RoomPlayer | None:
    return db.execute(
        select(RoomPlayer).where(RoomPlayer.room_id == room_id, RoomPlayer.user_id == user_id)
    ).scalar_one_or_none()


def _redirect_room(code: str, error: str) -> RedirectResponse:
    return RedirectResponse(f"/rooms/{code}?{urlencode({'error': error})}", status_code=303)
