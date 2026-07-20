#!/opt/homebrew/bin/python3.14
"""Wideband HackRF worker with DVB-S2 and future packet receive paths.

The worker exchanges newline-delimited JSON messages over stdin/stdout:

Manager to worker::

    {"command": "start", "data": {...}}
    {"command": "stop"}
    {"command": "configure", "data": {...}}

Worker to manager::

    {"type": "ready"}
    {"type": "status", "dvbs2": {...}, "hackrf": {...}}
    {"type": "error", "message": "..."}

Diagnostic logging goes to stderr so stdout remains machine-readable.
"""

from __future__ import annotations

import atexit
import json
import logging
import os
import signal
import stat
import sys
import threading
import traceback
from pathlib import Path
from typing import Any

# Homebrew's GNU Radio Python modules are not always on the subprocess path.
sys.path.insert(0, "/opt/homebrew/lib/python3.14/site-packages")

from gnuradio import analog, blocks, dvbs2rx, gr, soapy  # noqa: E402
from gnuradio import filter as gr_filter  # noqa: E402
from gnuradio.fft import window  # noqa: E402
from gnuradio.filter import firdes  # noqa: E402


DEFAULT_TS_PIPE_PATH = "/tmp/dvbs2_ts_pipe"
DEFAULT_PACKET_OFFSET_HZ = 2e6
DEFAULT_PACKET_SAMPLE_RATE = 2e6

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [sdr-worker] %(levelname)s: %(message)s",
)
logger = logging.getLogger("sdr-worker")

_flowgraph: SdrRxFlowgraph | None = None
_flowgraph_lock = threading.RLock()
_stdout_lock = threading.Lock()
_status_stop = threading.Event()
_status_thread: threading.Thread | None = None
_managed_pipe_path: str | None = None
_pipe_hold_fd: int | None = None


def _parse_modcod(modcod: str) -> tuple[str, str, str]:
    """Return normalized MODCOD, constellation, and code rate strings."""
    normalized = modcod.strip().upper()
    code_rate = normalized.replace("8PSK", "").replace("QPSK", "")
    constellation = normalized.replace(code_rate, "")
    if constellation not in {"QPSK", "8PSK"} or not code_rate:
        raise ValueError(f"Invalid DVB-S2 MODCOD: {modcod}")
    return normalized, constellation, code_rate


def _decimation(input_rate: float, output_rate: float, path_name: str) -> int:
    """Calculate an integer decimation and reject inconsistent rate pairs."""
    if input_rate <= 0 or output_rate <= 0:
        raise ValueError(f"{path_name} sample rates must be positive")
    ratio = input_rate / output_rate
    decimation = round(ratio)
    if decimation < 1 or not abs(ratio - decimation) < 1e-9:
        raise ValueError(
            f"HackRF sample_rate ({input_rate:g}) must be an integer multiple "
            f"of {path_name} sample rate ({output_rate:g})"
        )
    return decimation


def _pls_filter(
    constellation: str,
    code_rate: str,
    frame_size: str,
    pilots: str,
) -> tuple[int, int]:
    """Build PL signalling filters using the same policy as ``rx.py``."""
    pilot_values = [False, True] if pilots == "auto" else [pilots == "on"]
    pls_values = [
        dvbs2rx.params.dvbs2_pls(
            constellation, code_rate, frame_size, pilots_enabled
        )
        for pilots_enabled in pilot_values
    ]
    return dvbs2rx.params.pls_filter(*pls_values)


class SdrRxFlowgraph(gr.top_block):
    """HackRF capture, DVB-S2 decode, and a stub packet downconverter."""

    def __init__(
        self,
        freq_hz: float = 915e6,
        sample_rate: float = 10e6,
        dvbs2_offset_hz: float = -2e6,
        symbol_rate: float = 1e6,
        modcod: str = "QPSK1/2",
        rolloff: float = 0.2,
        pilots: str | bool = "auto",
        frame_size: str = "normal",
        lna: int = 8,
        vga: int = 20,
        amp: bool = False,
        serial: str | None = None,
        ts_pipe_path: str = DEFAULT_TS_PIPE_PATH,
        packet_offset_hz: float = DEFAULT_PACKET_OFFSET_HZ,
        packet_sample_rate: float = DEFAULT_PACKET_SAMPLE_RATE,
    ) -> None:
        super().__init__("SDR RX Worker", catch_exceptions=True)

        self.freq_hz = float(freq_hz)
        self.sample_rate = float(sample_rate)
        self.dvbs2_offset_hz = float(dvbs2_offset_hz)
        self.symbol_rate = float(symbol_rate)
        self.modcod, self.constellation, self.code_rate = _parse_modcod(modcod)
        self.rolloff = float(rolloff)
        self.pilots = self._normalize_pilots(pilots)
        self.frame_size = frame_size.lower()
        self.lna = self._clamp_lna(lna)
        self.vga = self._clamp_vga(vga)
        self.amp = bool(amp)
        self.serial = serial
        self.ts_pipe_path = ts_pipe_path
        self.packet_offset_hz = float(packet_offset_hz)
        self.packet_sample_rate = float(packet_sample_rate)
        self.running = False

        self._dvbs2_sample_rate = 2.0 * self.symbol_rate
        self._dvbs2_sps = self._dvbs2_sample_rate / self.symbol_rate
        dvbs2_decimation = _decimation(
            self.sample_rate, self._dvbs2_sample_rate, "DVB-S2"
        )
        packet_decimation = _decimation(
            self.sample_rate, self.packet_sample_rate, "packet"
        )

        self._build_hackrf_source()
        self._build_dvbs2_downconverter(dvbs2_decimation)
        self._build_dvbs2_receiver()
        self._build_packet_stub(packet_decimation)
        self._connect_flowgraph()

        logger.info(
            "Flowgraph configured: freq=%.3f MHz, sample_rate=%.3f Msps, "
            "DVB-S2 offset=%.3f MHz, symbol_rate=%.3f Msym/s, modcod=%s",
            self.freq_hz / 1e6,
            self.sample_rate / 1e6,
            self.dvbs2_offset_hz / 1e6,
            self.symbol_rate / 1e6,
            self.modcod,
        )

    @staticmethod
    def _normalize_pilots(pilots: str | bool) -> str:
        if isinstance(pilots, bool):
            return "on" if pilots else "off"
        normalized = str(pilots).lower()
        if normalized not in {"on", "off", "auto"}:
            raise ValueError("pilots must be 'on', 'off', 'auto', or a boolean")
        return normalized

    @staticmethod
    def _clamp_lna(value: int | float) -> int:
        return max(0, min(int(value), 40))

    @staticmethod
    def _clamp_vga(value: int | float) -> int:
        return max(0, min(int(value), 62))

    def _build_hackrf_source(self) -> None:
        device_args = f"serial={self.serial}" if self.serial else ""
        self._hackrf_source = soapy.source(
            "driver=hackrf", "fc32", 1, device_args, "", [""], [""]
        )
        self._hackrf_source.set_sample_rate(0, self.sample_rate)
        self._hackrf_source.set_bandwidth(0, 0)
        self._hackrf_source.set_frequency(0, self.freq_hz)
        self._hackrf_source.set_gain(0, "AMP", self.amp)
        self._hackrf_source.set_gain(0, "LNA", self.lna)
        self._hackrf_source.set_gain(0, "VGA", self.vga)

    def _build_dvbs2_downconverter(self, decimation: int) -> None:
        taps = firdes.low_pass(
            1.0,
            self.sample_rate,
            self._dvbs2_sample_rate / 2.0,
            self._dvbs2_sample_rate / 4.0,
            window.WIN_HAMMING,
            6.76,
        )
        self._dvbs2_xlating_fir = gr_filter.freq_xlating_fir_filter_ccc(
            decimation,
            taps,
            self.dvbs2_offset_hz,
            self.sample_rate,
        )

    def _build_dvbs2_receiver(self) -> None:
        """Construct the complete receive chain from ``rx.py``."""
        standard, frame_size, code_rate, constellation = dvbs2rx.params.translate(
            "DVB-S2", self.frame_size, self.code_rate, self.constellation
        )

        # Upper layer: de-mapping/FEC output -> MPEG transport stream bytes.
        self._dvbs2_ldpc = dvbs2rx.ldpc_decoder_bb(
            standard,
            frame_size,
            code_rate,
            constellation,
            dvbs2rx.OM_MESSAGE,
            dvbs2rx.INFO_OFF,
            25,
            0,
        )
        self._dvbs2_bch = dvbs2rx.bch_decoder_bb(
            standard, frame_size, code_rate, dvbs2rx.OM_MESSAGE, 0
        )
        self._dvbs2_descrambler = dvbs2rx.bbdescrambler_bb(
            standard, frame_size, code_rate
        )
        self._dvbs2_bbheader = dvbs2rx.bbdeheader_bb(
            standard, frame_size, code_rate, -1
        )

        # Lower layer: AGC -> carrier correction -> timing/PL sync -> demapper.
        self._dvbs2_agc = analog.agc_cc(1e-5, 1.0, 1.0)
        self._dvbs2_agc.set_max_gain(65536)
        self._dvbs2_rotator = dvbs2rx.rotator_cc(0, True)
        self._dvbs2_symbol_sync = dvbs2rx.symbol_sync_cc(
            self._dvbs2_sps,
            1e-3,
            1.0,
            self.rolloff,
            5,
            128,
            0,
        )
        pls_filter_lo, pls_filter_hi = _pls_filter(
            self.constellation,
            self.code_rate,
            self.frame_size,
            self.pilots,
        )
        self._dvbs2_physical = dvbs2rx.plsync_cc(
            0,
            30,
            self._dvbs2_sps,
            0,
            False,
            False,
            pls_filter_lo,
            pls_filter_hi,
        )
        self._dvbs2_demodulator = dvbs2rx.xfecframe_demapper_cb(
            frame_size, code_rate, constellation
        )

        # blocks.file_sink is intentionally used here: ffmpeg reads the FIFO.
        self._ts_file_sink = blocks.file_sink(
            gr.sizeof_char, self.ts_pipe_path, False
        )
        self._ts_file_sink.set_unbuffered(False)

    def _build_packet_stub(self, decimation: int) -> None:
        taps = firdes.low_pass(
            1.0,
            self.sample_rate,
            self.packet_sample_rate / 2.0,
            self.packet_sample_rate / 4.0,
            window.WIN_HAMMING,
            6.76,
        )
        self._packet_xlating_fir = gr_filter.freq_xlating_fir_filter_ccc(
            decimation,
            taps,
            self.packet_offset_hz,
            self.sample_rate,
        )
        self._packet_null_sink = blocks.null_sink(gr.sizeof_gr_complex)

    def _connect_flowgraph(self) -> None:
        # Shared wideband capture feeding the two sub-carrier DDC paths.
        self.connect((self._hackrf_source, 0), (self._dvbs2_xlating_fir, 0))
        self.connect((self._hackrf_source, 0), (self._packet_xlating_fir, 0))
        self.connect((self._packet_xlating_fir, 0), (self._packet_null_sink, 0))

        # Full DVB-S2 receive chain from rf/dvbs2/rx.py::connect_dvbs2rx.
        self.connect(
            (self._dvbs2_xlating_fir, 0),
            (self._dvbs2_agc, 0),
            (self._dvbs2_rotator, 0),
            (self._dvbs2_symbol_sync, 0),
            (self._dvbs2_physical, 0),
            (self._dvbs2_demodulator, 0),
            (self._dvbs2_ldpc, 0),
            (self._dvbs2_bch, 0),
            (self._dvbs2_descrambler, 0),
            (self._dvbs2_bbheader, 0),
            (self._ts_file_sink, 0),
        )
        self.msg_connect(
            (self._dvbs2_physical, "rotator_phase_inc"),
            (self._dvbs2_rotator, "cmd"),
        )
        self.msg_connect(
            (self._dvbs2_ldpc, "llr_pdu"),
            (self._dvbs2_demodulator, "llr_pdu"),
        )

    def start(self, max_noutput_items: int = 10_000_000) -> None:
        super().start(max_noutput_items)
        self.running = True

    def stop(self) -> None:
        self.running = False
        super().stop()
        super().wait()

    def reconfigure(self, **kwargs: Any) -> None:
        """Apply parameters that GNU Radio and the HackRF can change live."""
        unsupported = {
            "sample_rate",
            "symbol_rate",
            "modcod",
            "rolloff",
            "pilots",
            "frame_size",
            "serial",
            "ts_pipe_path",
            "packet_sample_rate",
        }.intersection(kwargs)
        if unsupported:
            names = ", ".join(sorted(unsupported))
            raise ValueError(f"Stop and restart to change: {names}")

        live_fields = {
            "freq_hz",
            "dvbs2_offset_hz",
            "packet_offset_hz",
            "lna",
            "vga",
            "amp",
        }
        unknown = set(kwargs).difference(live_fields)
        if unknown:
            names = ", ".join(sorted(unknown))
            raise ValueError(f"Unknown configuration field(s): {names}")

        if "freq_hz" in kwargs:
            self.freq_hz = float(kwargs["freq_hz"])
            self._hackrf_source.set_frequency(0, self.freq_hz)
        if "dvbs2_offset_hz" in kwargs:
            self.dvbs2_offset_hz = float(kwargs["dvbs2_offset_hz"])
            self._dvbs2_xlating_fir.set_center_freq(self.dvbs2_offset_hz)
        if "packet_offset_hz" in kwargs:
            self.packet_offset_hz = float(kwargs["packet_offset_hz"])
            self._packet_xlating_fir.set_center_freq(self.packet_offset_hz)
        if "lna" in kwargs:
            self.lna = self._clamp_lna(kwargs["lna"])
            self._hackrf_source.set_gain(0, "LNA", self.lna)
        if "vga" in kwargs:
            self.vga = self._clamp_vga(kwargs["vga"])
            self._hackrf_source.set_gain(0, "VGA", self.vga)
        if "amp" in kwargs:
            self.amp = bool(kwargs["amp"])
            self._hackrf_source.set_gain(0, "AMP", self.amp)

        logger.info("Reconfigured flowgraph: %s", kwargs)

    def get_status(self) -> dict[str, Any]:
        """Return current receiver and HackRF status."""
        locked = bool(self._dvbs2_physical.get_locked())
        fec_frames = self._dvbs2_bch.get_frame_count()
        snr_db = float(self._dvbs2_demodulator.get_snr()) if fec_frames else 0.0
        frequency_offset_hz = (
            float(self._dvbs2_physical.get_freq_offset()) * self.symbol_rate
        )
        return {
            "dvbs2": {
                "locked": locked,
                "snr_db": snr_db,
                "fo_hz": frequency_offset_hz,
                "modcod": self.modcod,
                "offset_hz": self.dvbs2_offset_hz,
                "symbol_rate": self.symbol_rate,
            },
            "hackrf": {
                "freq_hz": self.freq_hz,
                "sample_rate": self.sample_rate,
                "lna": self.lna,
                "vga": self.vga,
                "amp": self.amp,
                "serial": self.serial or "unknown",
            },
        }


def _send(message: dict[str, Any]) -> None:
    """Write one atomic JSON protocol message to stdout."""
    with _stdout_lock:
        print(json.dumps(message, separators=(",", ":")), flush=True)


def _ensure_pipe(path: str) -> bool:
    """Ensure *path* is a FIFO; return whether this worker created it."""
    pipe = Path(path)
    try:
        mode = pipe.stat().st_mode
    except FileNotFoundError:
        os.mkfifo(pipe)
        logger.info("Created named pipe: %s", pipe)
        return True
    if not stat.S_ISFIFO(mode):
        raise ValueError(f"TS output path exists but is not a named pipe: {pipe}")
    return False


def _cleanup_pipe(path: str | None) -> None:
    """Remove a managed FIFO without deleting any other kind of file."""
    if not path:
        return
    pipe = Path(path)
    try:
        if stat.S_ISFIFO(pipe.stat().st_mode):
            pipe.unlink()
            logger.info("Removed named pipe: %s", pipe)
    except FileNotFoundError:
        pass
    except OSError as exc:
        logger.warning("Could not remove named pipe %s: %s", pipe, exc)


def _close_pipe_hold() -> None:
    """Close the read end that lets ``file_sink`` open before ffmpeg does."""
    global _pipe_hold_fd
    if _pipe_hold_fd is None:
        return
    try:
        os.close(_pipe_hold_fd)
    except OSError:
        pass
    _pipe_hold_fd = None


def _status_loop(flowgraph: SdrRxFlowgraph) -> None:
    while not _status_stop.wait(0.5):
        with _flowgraph_lock:
            if _flowgraph is not flowgraph or not flowgraph.running:
                return
            status = flowgraph.get_status()
        _send({"type": "status", **status})


def _stop_flowgraph(*, respond: bool) -> None:
    global _flowgraph, _managed_pipe_path, _status_thread

    _status_stop.set()
    with _flowgraph_lock:
        flowgraph = _flowgraph
        _flowgraph = None

    error: Exception | None = None
    if flowgraph is not None:
        try:
            flowgraph.stop()
        except Exception as exc:  # pragma: no cover - hardware/runtime failure
            error = exc
            logger.error("Error stopping flowgraph: %s", exc)

    thread = _status_thread
    if thread is not None and thread is not threading.current_thread():
        thread.join(timeout=1.0)
    _status_thread = None

    _close_pipe_hold()
    _cleanup_pipe(_managed_pipe_path)
    _managed_pipe_path = None

    if respond:
        if error is None:
            _send({"type": "ready"})
        else:
            _send({"type": "error", "message": str(error)})


def cmd_start(config: dict[str, Any]) -> None:
    """Build and start the flowgraph."""
    global _flowgraph, _managed_pipe_path, _pipe_hold_fd, _status_thread

    with _flowgraph_lock:
        if _flowgraph is not None:
            _send({"type": "error", "message": "Flowgraph already running"})
            return

    pipe_path = str(config.get("ts_pipe_path", DEFAULT_TS_PIPE_PATH))
    flowgraph: SdrRxFlowgraph | None = None
    try:
        _ensure_pipe(pipe_path)
        _managed_pipe_path = pipe_path
        # A write-only FIFO open blocks until a reader appears. Keep one
        # non-consuming read descriptor open so the worker can answer ``start``
        # before the manager launches ffmpeg.
        _pipe_hold_fd = os.open(pipe_path, os.O_RDONLY | os.O_NONBLOCK)
        flowgraph = SdrRxFlowgraph(
            freq_hz=float(config.get("freq_hz", 915e6)),
            sample_rate=float(config.get("sample_rate", 10e6)),
            dvbs2_offset_hz=float(config.get("dvbs2_offset_hz", -2e6)),
            symbol_rate=float(config.get("symbol_rate", 1e6)),
            modcod=str(config.get("modcod", "QPSK1/2")),
            rolloff=float(config.get("rolloff", 0.2)),
            pilots=config.get("pilots", "auto"),
            frame_size=str(config.get("frame_size", "normal")),
            lna=int(config.get("lna", 8)),
            vga=int(config.get("vga", 20)),
            amp=bool(config.get("amp", False)),
            serial=config.get("serial"),
            ts_pipe_path=pipe_path,
            packet_offset_hz=float(
                config.get("packet_offset_hz", DEFAULT_PACKET_OFFSET_HZ)
            ),
            packet_sample_rate=float(
                config.get("packet_sample_rate", DEFAULT_PACKET_SAMPLE_RATE)
            ),
        )
        flowgraph.start()
        with _flowgraph_lock:
            _flowgraph = flowgraph
        _status_stop.clear()
        _status_thread = threading.Thread(
            target=_status_loop,
            args=(flowgraph,),
            name="sdr-status",
            daemon=True,
        )
        _status_thread.start()
        _send({"type": "ready"})
    except Exception as exc:
        logger.error("Failed to start: %s", exc)
        logger.debug("Start traceback:\n%s", traceback.format_exc())
        if flowgraph is not None and flowgraph.running:
            try:
                flowgraph.stop()
            except Exception:
                logger.debug("Cleanup after failed start failed", exc_info=True)
        _close_pipe_hold()
        _cleanup_pipe(_managed_pipe_path or pipe_path)
        _managed_pipe_path = None
        with _flowgraph_lock:
            _flowgraph = None
        _send({"type": "error", "message": str(exc)})


def cmd_stop(config: dict[str, Any] | None = None) -> None:
    """Stop the flowgraph and clean up its named pipe."""
    del config
    _stop_flowgraph(respond=True)


def cmd_configure(config: dict[str, Any]) -> None:
    """Apply a partial live configuration update."""
    with _flowgraph_lock:
        if _flowgraph is None:
            _send({"type": "error", "message": "Flowgraph not running"})
            return
        try:
            _flowgraph.reconfigure(**config)
        except Exception as exc:
            logger.error("Reconfigure failed: %s", exc)
            _send({"type": "error", "message": str(exc)})
            return
    _send({"type": "ready"})


_COMMANDS = {
    "start": cmd_start,
    "stop": cmd_stop,
    "configure": cmd_configure,
}


def _atexit_cleanup() -> None:
    _stop_flowgraph(respond=False)


atexit.register(_atexit_cleanup)


def main() -> int:
    """Read commands from stdin until EOF, emitting JSON responses."""
    signal.signal(signal.SIGINT, signal.SIG_IGN)
    signal.signal(signal.SIGTERM, signal.SIG_IGN)
    _send({"type": "ready"})

    try:
        for line in sys.stdin:
            line = line.strip()
            if not line:
                continue
            try:
                message = json.loads(line)
                if not isinstance(message, dict):
                    raise ValueError("Command must be a JSON object")
                command = message.get("command", "")
                data = message.get("data", {})
                if not isinstance(data, dict):
                    raise ValueError("Command data must be a JSON object")
                handler = _COMMANDS.get(command)
                if handler is None:
                    _send(
                        {
                            "type": "error",
                            "message": f"Unknown command: {command}",
                        }
                    )
                else:
                    handler(data)
            except json.JSONDecodeError:
                _send({"type": "error", "message": "Invalid JSON"})
            except Exception as exc:
                logger.error("Command handler error: %s", exc)
                _send({"type": "error", "message": str(exc)})
    finally:
        _stop_flowgraph(respond=False)
    return 0


if __name__ == "__main__":
    sys.exit(main())
