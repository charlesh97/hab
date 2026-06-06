# receiver-server/models.py
"""Pydantic v2 models for telemetry payloads, receiver status, and spectrum data."""

from __future__ import annotations
from enum import Enum
from typing import Literal
from pydantic import BaseModel


class AccelData(BaseModel):
    x: float
    y: float
    z: float


class GyroData(BaseModel):
    r: float
    p: float
    y: float


class AttData(BaseModel):
    roll: float
    pitch: float
    yaw: float



class EnvironmentPayload(BaseModel):
    type: Literal["environment"]
    temp_ext_c: float
    temp_int_c: float
    pressure_hpa: float
    humidity_pct: float
    baro_alt_m: float


class MotionPayload(BaseModel):
    type: Literal["motion"]
    gs_mps: float
    vs_mps: float
    heading_deg: float
    cog_deg: float
    accel: AccelData
    gyro_dps: GyroData
    att_deg: AttData


class PositionPayload(BaseModel):
    type: Literal["position"]
    lat: float
    lon: float
    alt_m: float
    agl_m: float
    fix: bool
    fix_type: str
    sats: int
    hdop: float
    vdop: float


class PowerPayload(BaseModel):
    type: Literal["power"]
    bat_v: float
    bat_a: float
    bat_w: float
    bat_pct: int
    bat_temp_c: float


class ReceiverState(str, Enum):
    IDLE = "idle"
    STARTING = "starting"
    RUNNING = "running"
    STOPPING = "stopping"
    ERROR = "error"


class ReceiverStatus(BaseModel):
    running: bool = False
    state: ReceiverState = ReceiverState.IDLE
    freq_hz: int = 0
    sample_rate: int = 0
    gain_lna: int = 0
    gain_vga: int = 0
    gain_amp: int = 0
    packets_total: int = 0
    packets_valid: int = 0
    symbol_rate: int = 100_000
    sps: int = 20
    signal_strength_db: float = 0.0
    lock: bool = False
    fo_hz: float = 0.0
    last_error: str = ""


class SpectrumFrame(BaseModel):
    """Spectrum frame — frequencies and power values."""
    fc_hz: int
    span_hz: int
    points: list[float]
    ts: float


class ErrorCode(str, Enum):
    DEVICE_LOST = "DEVICE_LOST"
    SIGNAL_LOST = "SIGNAL_LOST"
    HARDWARE_ERR = "HARDWARE_ERR"


class ErrorInfo(BaseModel):
    code: ErrorCode
    message: str
