"""ORM models: stored log entries and detected anomaly windows."""
from datetime import datetime, timezone

from sqlalchemy import JSON, DateTime, Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class LogEntry(Base):
    __tablename__ = "log_entries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime, index=True)
    level: Mapped[str] = mapped_column(String(16), default="INFO")
    source: Mapped[str] = mapped_column(String(64), default="app")
    message: Mapped[str] = mapped_column(Text, default="")
    status_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    response_time_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
    log_format: Mapped[str] = mapped_column(String(16), default="unknown")
    upload_id: Mapped[str] = mapped_column(String(36), index=True, default="")


class Anomaly(Base):
    __tablename__ = "anomalies"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    window_start: Mapped[datetime] = mapped_column(DateTime, index=True)
    window_end: Mapped[datetime] = mapped_column(DateTime)
    iforest_score: Mapped[float] = mapped_column(Float, default=0.0)
    max_abs_z: Mapped[float] = mapped_column(Float, default=0.0)
    agreement: Mapped[str] = mapped_column(String(32), default="none")
    detectors: Mapped[list] = mapped_column(JSON, default=list)
    triggered_metrics: Mapped[list] = mapped_column(JSON, default=list)
    abnormal_features: Mapped[list] = mapped_column(JSON, default=list)
    metrics: Mapped[dict] = mapped_column(JSON, default=dict)
    label: Mapped[str | None] = mapped_column(String(20), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
