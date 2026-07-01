# Repository Guidelines

## Project Structure & Module Organization

This repository is a lightweight FastAPI Texas Hold'em app. Source code lives in `app/`, split by responsibility:

- `app/main.py`: FastAPI app setup, routers, startup state.
- `app/auth/`: registration, login, session cookies, CSRF checks.
- `app/db/`: SQLAlchemy models and SQLite session setup.
- `app/rooms/`: lobby, room creation, seating, ready flow.
- `app/game/`: poker runtime, evaluator, service layer, shared game models.
- `app/realtime/`: WebSocket routes and connection manager.
- `app/bots/`: bot strategy protocol and placeholder strategies.
- `app/templates/` and `app/static/`: Jinja templates, CSS, browser JS.
- `tests/`: pytest tests for game logic and HTTP flows.
- `migrations/`: Alembic migration entrypoint.

## Build, Test, and Development Commands

Use the local virtual environment when available:

```powershell
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe -m compileall app migrations tests
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

`pytest` runs unit and integration tests. `compileall` catches syntax/import-time issues. `uvicorn` starts the app at `http://127.0.0.1:8000`.

Docker deployment is defined in `Dockerfile` and `docker-compose.yml`:

```powershell
docker compose up --build
```

## Coding Style & Naming Conventions

Use Python 3.11+ syntax and 4-space indentation. Prefer typed functions, dataclasses for runtime state, and SQLAlchemy ORM models for persisted data. Keep module names lowercase and descriptive, such as `runtime.py`, `routes.py`, or `manager.py`.

Route handlers should stay thin; put poker behavior in `app/game/` and persistence/broadcast orchestration in service classes. Avoid leaking hidden cards in public state responses.

## Testing Guidelines

Tests use `pytest`, `pytest-asyncio`, and FastAPI `TestClient`. Name test files `test_*.py` and test functions `test_*`. Add tests for any change to betting rules, room lifecycle, authentication, WebSocket payloads, or state redaction.

Prefer focused tests in `tests/test_runtime.py` for poker mechanics and HTTP flow tests in `tests/test_http_flow.py` for rendered pages and session behavior.

## Commit & Pull Request Guidelines

There is no git history in this workspace, so use clear, conventional commit messages such as `feat: add room ready flow` or `fix: hide opponent hole cards`.

Pull requests should include a short summary, test results, and screenshots or screen recordings for visible UI changes. Link related issues when available, and call out database model or migration changes explicitly.

## Security & Configuration Tips

Configuration is environment-driven in `app/config.py`. Keep `COOKIE_SECURE=true` in HTTPS deployments. Do not introduce real-money handling without a separate accounting, audit, and compliance design. SQLite is intended for single-instance deployment only.
