from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.db import init_db
from app.game.service import GameService
from app.realtime.manager import ConnectionManager
from app.realtime.routes import router as websocket_router
from app.rooms.manager import RoomManager
from app.rooms.routes import router as rooms_router
from app.web.routes import router as web_router
from app.auth.routes import router as auth_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    app.state.room_manager = RoomManager()
    app.state.connection_manager = ConnectionManager()
    app.state.game_service = GameService(app.state.room_manager, app.state.connection_manager)
    yield


app = FastAPI(title="Tiny Texas", lifespan=lifespan)
app.mount("/static", StaticFiles(directory="app/static"), name="static")
app.include_router(web_router)
app.include_router(auth_router)
app.include_router(rooms_router)
app.include_router(websocket_router)


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}

