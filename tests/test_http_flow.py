from __future__ import annotations

import re

from fastapi.testclient import TestClient


def _csrf_token(html: str) -> str:
    csrf_match = re.search(r'name="csrf_token" value="([^"]+)"', html)
    assert csrf_match is not None
    return csrf_match.group(1)


def _room_code(html: str) -> str:
    code_match = re.search(r'data-room-code="([^"]+)"', html)
    assert code_match is not None
    return code_match.group(1)


def test_register_create_delete_room_flow(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'tiny_texas_test.db'}")
    monkeypatch.setenv("REGISTRATION_INVITE_CODE", "test-invite")

    from app.main import app

    with TestClient(app) as client:
        blocked = client.post(
            "/register",
            data={"username": "blocked", "password": "password123", "invite_code": "wrong"},
            follow_redirects=True,
        )
        assert blocked.status_code == 400
        assert "邀请码无效。" in blocked.text
        assert "大厅" not in blocked.text

        register = client.post(
            "/register",
            data={"username": "smokeuser", "password": "password123", "invite_code": "test-invite"},
            follow_redirects=True,
        )
        assert register.status_code == 200
        assert "大厅" in register.text
        assert "我们不生产米，我们只是慈善家的搬运工。" in register.text

        room = client.post(
            "/rooms",
            data={
                "csrf_token": _csrf_token(register.text),
                "name": "测试牌桌",
                "seat_count": "2",
                "small_blind": "5",
                "big_blind": "10",
                "buy_in": "1000",
            },
            follow_redirects=True,
        )

        assert room.status_code == 200
        assert 'id="room-app"' in room.text
        assert 'id="result-modal"' in room.text
        assert 'id="bot-modal"' in room.text
        assert 'id="bot-options"' in room.text
        assert 'data-is-owner="true"' in room.text
        assert "测试牌桌" in room.text
        assert "我们不生产米，我们只是慈善家的搬运工。" in room.text

        room_code = _room_code(room.text)
        lobby = client.get("/lobby")
        assert lobby.status_code == 200
        assert f'action="/rooms/{room_code}/delete"' in lobby.text

        client.post("/logout", data={"csrf_token": _csrf_token(lobby.text)}, follow_redirects=True)
        intruder = client.post(
            "/register",
            data={"username": "intruder", "password": "password123", "invite_code": "test-invite"},
            follow_redirects=True,
        )
        assert intruder.status_code == 200
        assert f'action="/rooms/{room_code}/delete"' not in intruder.text

        forbidden = client.post(
            f"/rooms/{room_code}/delete",
            data={"csrf_token": _csrf_token(intruder.text)},
            follow_redirects=False,
        )
        assert forbidden.status_code == 403

        client.post("/logout", data={"csrf_token": _csrf_token(intruder.text)}, follow_redirects=True)
        owner = client.post(
            "/login",
            data={"username": "smokeuser", "password": "password123"},
            follow_redirects=True,
        )
        assert owner.status_code == 200

        deleted = client.post(
            f"/rooms/{room_code}/delete",
            data={"csrf_token": _csrf_token(owner.text)},
            follow_redirects=True,
        )
        assert deleted.status_code == 200
        assert room_code not in deleted.text
        assert f'action="/rooms/{room_code}/delete"' not in deleted.text

        missing = client.get(f"/rooms/{room_code}", follow_redirects=False)
        assert missing.status_code == 404
