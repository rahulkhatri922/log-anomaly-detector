"""SQLAlchemy engine/session setup (SQLite by default) and shared paths."""
import os
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

DATA_DIR = Path(os.environ.get("DATA_DIR", "data"))
DATA_DIR.mkdir(parents=True, exist_ok=True)
MODEL_PATH = DATA_DIR / "model.joblib"

DATABASE_URL = os.environ.get("DATABASE_URL", f"sqlite:///{DATA_DIR / 'app.db'}")

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {},
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def to_naive_utc(dt: datetime) -> datetime:
    """Normalize any datetime to naive UTC so SQLite comparisons are consistent."""
    if dt.tzinfo is not None:
        return dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt
