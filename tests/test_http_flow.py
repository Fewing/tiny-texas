from __future__ import annotations

import re

from fastapi.testclient import TestClient


def test_register_create_room_flow(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'tiny_texas_test.db'}")

    from app.main import app

    with TestClient(app) as client:
        register = client.post(
            "/register",
            data={"username": "smokeuser", "password": "password123"},
            follow_redirects=True,
        )
        assert register.status_code == 200
        assert "Lobby" in register.text

        csrf_match = re.search(r'name="csrf_token" value="([^"]+)"', register.text)
        assert csrf_match is not None

        room = client.post(
            "/rooms",
            data={
                "csrf_token": csrf_match.group(1),
                "name": "Smoke Table",
                "seat_count": "2",
                "small_blind": "5",
                "big_blind": "10",
                "buy_in": "1000",
            },
            follow_redirects=True,
        )

        assert room.status_code == 200
        assert 'id="room-app"' in room.text
        assert "Smoke Table" in room.text

