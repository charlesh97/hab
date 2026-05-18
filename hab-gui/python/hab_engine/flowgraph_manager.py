"""Flowgraph Manager — manages the DVB-S2 TX GNU Radio flowgraph lifecycle."""

import logging
import threading
from typing import Optional, Callable
from .models import SpectrumFrame
import time

logger = logging.getLogger(__name__)


class FlowgraphManager:
    """
    Manages the DVB-S2 transmitter flowgraph lifecycle.
    Handles creation, start, stop, and reconfiguration.
    """

    def __init__(self):
        self._flowgraph = None
        self._lock = threading.Lock()
        self._running = False
        self._spectrum_callback: Optional[Callable[[SpectrumFrame], None]] = None
        self._config = {
            "device_args": "driver=hackrf",
            "center_freq": 915e6,
            "symbol_rate": 1e6,
            "tx_gain_vga": 16.0,
            "tx_gain_amp": False,
            "file_path": "/tmp/tsfifo",
            "rolloff": 0.2,
            "modcod": "QPSK1/2",
            "pilots": True,
        }

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def config(self) -> dict:
        return dict(self._config)

    def set_spectrum_callback(self, callback: Callable[[SpectrumFrame], None]):
        """Set callback for spectrum data."""
        self._spectrum_callback = callback

    def update_config(self, **kwargs):
        """Update configuration parameters."""
        self._config.update(kwargs)
        if self._running and self._flowgraph:
            self._flowgraph.reconfigure(**kwargs)

    def start(self) -> bool:
        """Start the DVB-S2 TX flowgraph."""
        if self._running:
            logger.warning("Flowgraph already running")
            return False

        with self._lock:
            try:
                from dvbs2_flowgraph import Dvbs2Flowgraph

                self._flowgraph = Dvbs2Flowgraph(
                    device_args=self._config["device_args"],
                    center_freq=self._config["center_freq"],
                    symbol_rate=self._config["symbol_rate"],
                    tx_gain_vga=self._config["tx_gain_vga"],
                    tx_gain_amp=self._config["tx_gain_amp"],
                    file_path=self._config["file_path"],
                    rolloff=self._config["rolloff"],
                    modcod=self._config["modcod"],
                    pilots=self._config["pilots"],
                )

                self._running = True

                # Start spectrum polling thread if callback is set
                if self._spectrum_callback:
                    self._flowgraph.start()
                    self._spectrum_poll_thread = threading.Thread(
                        target=self._poll_spectrum, daemon=True
                    )
                    self._spectrum_poll_thread.start()
                else:
                    self._flowgraph.start()

                logger.info("DVBS2 flowgraph started")
                return True

            except Exception as e:
                logger.error(f"Failed to start flowgraph: {e}")
                self._flowgraph = None
                return False

    def _poll_spectrum(self):
        """Poll spectrum data from flowgraph and forward to callback."""
        while self._running and self._flowgraph:
            data = self._flowgraph.get_spectrum_data()
            if data and self._spectrum_callback:
                freq, power = data
                frame = SpectrumFrame(
                    frequencies=list(freq),
                    power_db=list(power),
                    timestamp=time.time(),
                    center_freq=self._config["center_freq"],
                    span_hz=self._config["symbol_rate"] * 2,
                )
                try:
                    self._spectrum_callback(frame)
                except Exception as e:
                    logger.error(f"Spectrum callback error: {e}")
            time.sleep(0.05)

    def stop(self):
        """Stop the DVB-S2 TX flowgraph."""
        if not self._running:
            return

        with self._lock:
            self._running = False
            if self._flowgraph:
                try:
                    self._flowgraph.stop()
                    self._flowgraph.wait()
                except Exception as e:
                    logger.error(f"Error stopping flowgraph: {e}")
                self._flowgraph = None
            logger.info("DVBS2 flowgraph stopped")

    def cleanup(self):
        """Full cleanup."""
        self.stop()
