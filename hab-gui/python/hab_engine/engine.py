"""HabEngine — Core orchestrator for the HAB Ground Station."""

import logging
import time
import threading
from typing import Optional, Dict, Any, Callable
from .models import (
    EngineStatus, PipelineStatus, SpectrumFrame,
    DeviceInfo, WSMessageType
)
from .pipeline_manager import PipelineManager
from .flowgraph_manager import FlowgraphManager
from .websocket_server import WebSocketServer

logger = logging.getLogger(__name__)


class HabEngine:
    """
    Singleton orchestrator for all HAB Ground Station operations.

    Manages:
    - DVBS2 TX flowgraph lifecycle
    - ffmpeg → tsp encoding pipeline
    - Telemetry RX (future)
    - Spectrum data collection
    - WebSocket broadcasting to macOS dashboard
    """

    _instance: Optional['HabEngine'] = None

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self, enable_websocket: bool = True):
        if hasattr(self, '_initialized') and self._initialized:
            return
        self._initialized = True

        self._start_time = time.time()

        # Managers
        self.pipeline = PipelineManager()
        self.flowgraph = FlowgraphManager()

        # WebSocket server
        self.ws_server = WebSocketServer() if enable_websocket else None
        if self.ws_server:
            self.ws_server.set_command_handler(self._handle_ws_command)

        # Status
        self._status = EngineStatus()
        self._status_lock = threading.Lock()
        self._error_count = 0
        self._last_error = ""

        # Device state (populated by Connection Tab)
        self._device_info = DeviceInfo()

        # Status broadcast thread
        self._broadcast_thread = None
        self._broadcast_running = False

        # Callbacks
        self._spectrum_callback: Optional[Callable] = None

        # Connect flowgraph spectrum to our handler
        self.flowgraph.set_spectrum_callback(self._on_spectrum_data)

        # Connect pipeline debug to log
        self.pipeline.set_debug_callback(
            lambda name, msg: logger.debug(f"[{name}] {msg}")
        )

        # Start WebSocket
        if self.ws_server:
            self.ws_server.start()

        # Start status broadcast loop
        self._start_broadcast()

        logger.info("HabEngine initialized")

    def _start_broadcast(self):
        """Start periodic status broadcast."""
        self._broadcast_running = True
        self._broadcast_thread = threading.Thread(
            target=self._broadcast_loop, daemon=True
        )
        self._broadcast_thread.start()

    def _broadcast_loop(self):
        """Broadcast engine status at 2 Hz."""
        while self._broadcast_running:
            self._broadcast_status()
            time.sleep(0.5)

    def _broadcast_status(self):
        """Send current status to all WebSocket clients."""
        if not self.ws_server:
            return
        with self._status_lock:
            self._status.uptime_sec = time.time() - self._start_time
            self._status.error_count = self._error_count
            self._status.last_error = self._last_error
        self.ws_server.broadcast(self._status.to_message())

    def _on_spectrum_data(self, frame: SpectrumFrame):
        """Handle spectrum data from flowgraph."""
        # Forward to GUI callback if set
        if self._spectrum_callback:
            try:
                self._spectrum_callback(frame)
            except Exception as e:
                logger.error(f"Spectrum GUI callback error: {e}")

        # Broadcast to WebSocket clients
        if self.ws_server:
            self.ws_server.broadcast(frame.to_message())

    def set_spectrum_callback(self, callback: Callable[[SpectrumFrame], None]):
        """Set callback for spectrum data (used by GUI tab)."""
        self._spectrum_callback = callback

    async def _handle_ws_command(self, msg: Dict[str, Any]):
        """Handle commands from WebSocket clients (macOS app)."""
        cmd = msg.get("command", msg.get("type", ""))
        data = msg.get("data", {})

        logger.info(f"WS command: {cmd} {data}")

        if cmd == WSMessageType.CMD_START_PIPELINE.value:
            file_path = data.get("file_path", self._device_info.serial)
            await self.start_pipeline(file_path)

        elif cmd == WSMessageType.CMD_STOP_PIPELINE.value:
            await self.stop_pipeline()

        elif cmd == WSMessageType.CMD_START_TX.value:
            await self.start_tx()

        elif cmd == WSMessageType.CMD_STOP_TX.value:
            await self.stop_tx()

        elif cmd == WSMessageType.CMD_SET_FREQ.value:
            freq = float(data.get("frequency", 915e6))
            self.flowgraph.update_config(center_freq=freq)

        elif cmd == WSMessageType.CMD_SET_GAIN.value:
            gain = float(data.get("vga", 16))
            amp = bool(data.get("amp", False))
            self.flowgraph.update_config(tx_gain_vga=gain, tx_gain_amp=amp)

        elif cmd == WSMessageType.CMD_REFRESH_DEVICES.value:
            # Trigger device refresh (GUI will handle via Connection Tab)
            pass

    # ── Public API ──

    def update_device_state(self, device_info: DeviceInfo):
        """Update device state from Connection Tab."""
        self._device_info = device_info
        with self._status_lock:
            self._status.device_connected = device_info.connected
            self._status.device_serial = device_info.serial

    def update_params(self, frequency: float = None, symbol_rate: float = None):
        """Update radio parameters."""
        if frequency:
            self._device_info.frequency = frequency
            with self._status_lock:
                self._status.frequency = frequency
        if symbol_rate:
            self._device_info.sample_rate = symbol_rate * 2
            with self._status_lock:
                self._status.symbol_rate = symbol_rate

    def start_pipeline(self, input_file: str) -> bool:
        """Start the ffmpeg → tsp encoding pipeline."""
        success = self.pipeline.start(input_file)
        if success:
            with self._status_lock:
                self._status.pipeline = self.pipeline.status
        return success

    def stop_pipeline(self):
        """Stop the encoding pipeline."""
        self.pipeline.stop()
        with self._status_lock:
            self._status.pipeline = PipelineStatus()

    def start_tx(self, device_args: str = "driver=hackrf") -> bool:
        """Start DVB-S2 transmission."""
        self.flowgraph.update_config(device_args=device_args)
        success = self.flowgraph.start()
        if success:
            with self._status_lock:
                self._status.tx_active = True
        return success

    def stop_tx(self):
        """Stop DVB-S2 transmission."""
        self.flowgraph.stop()
        with self._status_lock:
            self._status.tx_active = False

    def set_pipeline_debug_callback(self, callback: Callable[[str, str], None]):
        """Set callback for pipeline debug output."""
        self.pipeline.set_debug_callback(callback)

    @property
    def status(self) -> EngineStatus:
        return self._status

    def cleanup(self):
        """Full cleanup — stop all operations."""
        logger.info("HabEngine cleanup")
        self._broadcast_running = False
        self.stop_tx()
        self.stop_pipeline()
        if self.ws_server:
            self.ws_server.stop()
        self._initialized = False
        self._instance = None
        type(self)._instance = None
