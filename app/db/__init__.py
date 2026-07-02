from app.db.models import Base

__all__ = ["Base", "SessionLocal", "get_db", "init_db"]


def __getattr__(name: str):
    if name in {"SessionLocal", "get_db", "init_db"}:
        from app.db import session

        return getattr(session, name)
    raise AttributeError(f"module 'app.db' has no attribute {name!r}")

