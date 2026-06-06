# receiver-server/config.py
"""Server and receiver configuration dataclasses."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ServerConfig:
    host: str = "0.0.0.0"
    port: int = 8000
    packet_buffer_size: int = 1000
    status_interval_sec: float = 1.0
    spectrum_points: int = 256
    spectrum_chunk_interval: int = 20
    database_path: str = "hab_data.db"


@dataclass
class ReceiverConfig:
    freq_hz: int = 433_500_000
    sample_rate: int = 2_000_000
    symbol_rate: int = 100_000
    sps: int = 20
    gain_lna: int = 32
    gain_vga: int = 30
    gain_amp: int = 0
    serial: str | None = None
