"""Pydantic request/response schemas."""
from datetime import datetime

from pydantic import BaseModel, Field


class TrainRequest(BaseModel):
    normal_start: datetime | None = None
    normal_end: datetime | None = None
    window_seconds: int = Field(default=60, ge=5, le=3600)
    contamination: float = Field(default=0.05, gt=0, le=0.5)


class DetectRequest(BaseModel):
    start: datetime | None = None
    end: datetime | None = None
    z_threshold: float = Field(default=3.0, ge=1.0, le=6.0)


class LabelRequest(BaseModel):
    label: str = Field(pattern="^(true_positive|false_positive)$")


class TimeseriesQuery(BaseModel):
    start: datetime | None = None
    end: datetime | None = None
