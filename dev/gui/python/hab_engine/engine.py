"""HabEngine — Core orchestrator for the HAB Ground Station."""

import logging
import time
import threading
from typing import Optional, Dict, Any, Callable, Coroutine
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

        # Status — mark as running immediately on init
        self._status = EngineStatus()
        self._status.running = True
        self._status_lock = threading.Lock()
        self._error_count = 0
        self._last_error = ""

        # Device state (populated by Connection Tab or auto-detect)
        self._device_info = DeviceInfo()

        # Auto-detect HackRF devices on startup
        self._detect_hackrf_devices()

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

    def _detect_hackrf_devices(self):
        """Scan for HackRF devices using hackrf_info and update status."""
        try:
            import subprocess
            result = subprocess.run(["hackrf_info"], capture_output=True, text=True, timeout=5)
            serials = []
            for line in result.stdout.split("\n"):
                if "Serial number:" in line:
                    serial = line.split(":")[1].strip()
                    if serial:
                        serials.append(serial)
            if serials:
                self._device_info.serial = serials[0]
                self._device_info.connected = True
                self._device_info.label = f"HackRF ({serials[0][:16]}...)"
                with self._status_lock:
                    self._status.device_connected = True
                    self._status.device_serial = serials[0]
                logger.info(f"HackRF detected: {len(serials)} device(s), primary: {serials[0][:16]}...")
            else:
                logger.warning("No HackRF devices found")
        except FileNotFoundError:
            logger.warning("hackrf_info not installed — cannot auto-detect HackRF")
        except Exception as e:
            logger.warning(f"HackRF detection failed: {e}")

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
            self.start_tx()

        elif cmd == WSMessageType.CMD_STOP_TX.value:
            self.stop_tx()

        elif cmd == WSMessageType.CMD_SET_FREQ.value:
            freq = float(data.get("frequency", 915e6))
            self.flowgraph.update_config(center_freq=freq)

        elif cmd == WSMessageType.CMD_SET_GAIN.value:
            gain = float(data.get("vga", 16))
            amp = bool(data.get("amp", False))
            self.flowgraph.update_config(tx_gain_vga=gain, tx_gain_amp=amp)

        elif cmd == WSMessageType.CMD_SET_SYMBOL_RATE.value:
            sr = float(data.get("symbol_rate", 1e6))
            self.flowgraph.update_config(symbol_rate=sr)

        elif cmd == WSMessageType.CMD_REFRESH_DEVICES.value:
            # Trigger device refresh (GUI will handle via Connection Tab)
            pass

        # ── DVB-S2 config commands (from SettingsPage DVB-S2 tab) ──
        elif cmd in ('set_modcod', 'set_pilots', 'set_rolloff', 'set_fec_frame',
                     'set_sps', 'set_rrc_delay', 'set_gold_code',
                     'set_fullscale', 'set_sink_type', 'set_device_args'):
            # These parameters require a stop/start of TX to take effect.
            # Store them in the flowgraph config for next start.
            param_map = {
                'set_modcod': 'modcod',
                'set_pilots': 'pilots',
                'set_rolloff': 'rolloff',
                'set_fec_frame': 'fec_frame',
                'set_sps': 'sps',
                'set_rrc_delay': 'rrc_delay',
                'set_gold_code': 'gold_code',
                'set_fullscale': 'fullscale',
                'set_sink_type': 'sink_type',
                'set_device_args': 'device_args',
            }
            key = param_map.get(cmd, cmd)
            if key == 'pilots':
                # Convert string to bool
                val = data.get(key, data.get('pilots', 'ON')).upper() == 'ON'
            elif key == 'rolloff':
                val = float(data.get(key, data.get('rolloff', 0.35)))
            elif key == 'modcod':
                val = str(data.get(key, data.get('modcod', 'QPSK 1/4')))
            elif key in ('sps',):
                val = int(data.get(key, data.get('sps', 2)))
            else:
                val = data.get(key, data.get(cmd.replace('set_', ''), ''))
            self.flowgraph.update_config(**{key: val})

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
        """Start DVB-S2 transmission.
        The flowgraph runs in a subprocess so this is truly non-blocking.
        Returns True if start was initiated, False if already running.
        """
        if self.flowgraph.is_running:
            logger.warning("TX already running")
            return False
        
        self.flowgraph.update_config(device_args=device_args)
        logger.info("Starting DVB-S2 TX...")
        
        # Fire-and-forget to subprocess worker
        self.flowgraph.start()
        with self._status_lock:
            self._status.tx_active = True
        logger.info("DVB-S2 TX initiated")
        return True

    def stop_tx(self):
        """Stop DVB-S2 transmission."""
        logger.info("Stopping DVB-S2 TX...")
        self.flowgraph.stop()
        with self._status_lock:
            self._status.tx_active = False
        logger.info("DVB-S2 TX stopped")

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
