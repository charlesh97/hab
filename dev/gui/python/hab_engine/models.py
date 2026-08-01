"""Data models and message types for HAB Ground Station."""

from dataclasses import dataclass, field, asdict
from typing import List, Dict, Optional, Any
from enum import Enum
import json
import time


class WSMessageType(str, Enum):
    """WebSocket message type identifiers."""
    STATUS = "status"
    SPECTRUM = "spectrum"
    TELEMETRY = "telemetry"
    PIPELINE = "pipeline"
    DEVICE = "device"
    ERROR = "error"

    # Command types (macOS app → engine)
    CMD_START_PIPELINE = "start_pipeline"
    CMD_STOP_PIPELINE = "stop_pipeline"
    CMD_START_TX = "start_tx"
    CMD_STOP_TX = "stop_tx"
    CMD_SET_FREQ = "set_frequency"
    CMD_SET_GAIN = "set_gain"
    CMD_SET_SYMBOL_RATE = "set_symbol_rate"
    CMD_REFRESH_DEVICES = "refresh_devices"
    CMD_CONNECT_DEVICE = "connect_device"
    CMD_DISCONNECT = "disconnect"


@dataclass
class PipelineStatus:
    """Status of the ffmpeg → tsp pipeline."""
    running: bool = False
    file_path: str = ""
    bitrate: float = 0.0
    packets_sent: int = 0
    errors: int = 0
    duration_sec: float = 0.0


@dataclass
class SpectrumFrame:
    """Single FFT spectrum frame."""
    frequencies: List[float] = field(default_factory=list)
    power_db: List[float] = field(default_factory=list)
    timestamp: float = 0.0
    center_freq: float = 0.0
    span_hz: float = 0.0

    def to_message(self) -> Dict[str, Any]:
        """Convert to WebSocket message dict, downsampled to reduce bandwidth."""
        # Downsample to ~256 points for network efficiency
        step = max(1, len(self.frequencies) // 256)
        return {
            "type": WSMessageType.SPECTRUM.value,
            "data": {
                "f": list(self.frequencies[::step]),
                "p": list(self.power_db[::step]),
                "fc": self.center_freq,
                "span": self.span_hz,
                "ts": self.timestamp,
            }
        }


@dataclass
class TelemetryData:
    """Received telemetry packet."""
    raw: bytes = b""
    parsed: str = ""
    rssi: float = -120.0
    snr: float = 0.0
    frequency_error: float = 0.0
    timestamp: float = 0.0


@dataclass
class DeviceInfo:
    """HackRF device information."""
    serial: str = ""
    label: str = ""
    connected: bool = False
    frequency: float = 434e6
    sample_rate: float = 2e6
    gains: Dict[str, float] = field(default_factory=lambda: {
        "LNA": 16.0,
        "VGA": 20.0,
        "AMP": False,
    })


@dataclass
class EngineStatus:
    """Overall engine status broadcast to all clients."""
    running: bool = False
    pipeline: PipelineStatus = field(default_factory=PipelineStatus)
    tx_active: bool = False
    rx_active: bool = False
    device_connected: bool = False
    device_serial: str = ""
    frequency: float = 915e6
    symbol_rate: float = 1e6
    uptime_sec: float = 0.0
    error_count: int = 0
    last_error: str = ""

    def to_message(self) -> Dict[str, Any]:
        return {
            "type": WSMessageType.STATUS.value,
            "data": {
                "running": self.running,
                "tx_active": self.tx_active,
                "rx_active": self.rx_active,
                "device_connected": self.device_connected,
                "frequency": self.frequency,
                "symbol_rate": self.symbol_rate,
                "uptime_sec": self.uptime_sec,
                "pipeline": asdict(self.pipeline),
                "error_count": self.error_count,
                "last_error": self.last_error,
            }
        }
