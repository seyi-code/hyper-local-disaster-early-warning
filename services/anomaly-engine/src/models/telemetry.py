from __future__ import annotations

from pydantic import BaseModel, Field
from typing import Optional, Literal
from datetime import datetime


class TelemetryEvent(BaseModel):
    sensor_id: str
    cell_id: str
    metric: Literal["water_level_cm", "pm25_ugm3", "temperature_c", "humidity_pct"]
    value: float
    timestamp: datetime
    lat: Optional[float] = None
    lon: Optional[float] = None
    battery_pct: Optional[float] = None
    stream_id: Optional[str] = None


class AlertEvent(BaseModel):
    cell_id: str
    sensor_id: str
    metric: str
    value: float
    direction: str
    score: float
    timestamp: datetime
    message: str
    severity: Literal["warning", "critical"] = "warning"
