# Tiny Texas

A lightweight web-based Texas Hold'em MVP using FastAPI, Jinja2, HTMX, WebSocket, SQLite, and Docker.

## Run locally

```bash
python -m venv .venv
. .venv/bin/activate
pip install -e ".[dev]"
uvicorn app.main:app --reload
```

Open `http://localhost:8000`.

## Run with Docker

```bash
docker compose up --build
```

The app runs on `http://localhost:8000`, and SQLite data is stored in the `tiny_texas_data` volume.

