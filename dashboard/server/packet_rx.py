# receiver-server/packet_rx.py
"""Packet receiver — wraps rf/packet/src/ as an async bridge.

ReceiverWorker: synchronous SDR manager + signal processing pipeline.
AsyncPacketReceiver: async bridge using run_in_executor for SDR I/O.

The packet_codec import is lazy (function-level) so tests can import
without the rf/packet/src/ directory on PYTHONPATH.
"""

from __future__ import annotations

import time
import asyncio
from concurrent.futures import ThreadPoolExecutor
from typing import Callable, Awaitable

import numpy as np

from models import SpectrumFrame
from config import ReceiverConfig


class ReceiverWorker:
    """Synchronous SDR manager + signal processing pipeline.

    Uses packet_codec and fec_cc from rf/packet/src/ for FEC/CRC.
    Wraps SoapySDR for HackRF control.
    """

    def __init__(self, config: ReceiverConfig):
        self.config = config
        self._sdr = None
        self._rx_stream = None
        self._fo_est: float = 0.0
        self._chunk_size: int = 524_288
        self._rrc_taps: np.ndarray | None = None
        self._raw_iq: np.ndarray | None = None

    def open(self) -> None:
        """Open the HackRF via SoapySDR and configure the stream."""
        import SoapySDR
        from SoapySDR import SOAPY_SDR_RX, SOAPY_SDR_CF32

        args = dict(driver="hackrf")
        if self.config.serial:
            args["serial"] = self.config.serial

        self._sdr = SoapySDR.Device(args)
        self._sdr.setSampleRate(SOAPY_SDR_RX, 0, self.config.sample_rate)
        self._sdr.setFrequency(SOAPY_SDR_RX, 0, self.config.freq_hz)

        try:
            self._sdr.setGain(SOAPY_SDR_RX, 0, "LNA", self.config.gain_lna)
            self._sdr.setGain(SOAPY_SDR_RX, 0, "VGA", self.config.gain_vga)
            self._sdr.setGain(SOAPY_SDR_RX, 0, "AMP", self.config.gain_amp)
        except Exception:
            pass

        self._rx_stream = self._sdr.setupStream(SOAPY_SDR_RX, SOAPY_SDR_CF32)
        self._sdr.activateStream(self._rx_stream)

        self._init_rrc_filter()

    def _init_rrc_filter(self) -> None:
        """Initialize the RRC matched filter taps."""
        sps = self.config.sps
        span = 10
        t = np.arange(-span, span + 1e-9, 1 / sps)
        beta = 0.35
        denom = 1.0 - (2.0 * beta * t) ** 2
        with np.errstate(divide="ignore", invalid="ignore"):
            taps = (
                np.sin(np.pi * t * (1 - beta))
                + 4 * beta * t * np.cos(np.pi * t * (1 + beta))
            ) / (np.pi * t * denom + 1e-30)
        taps[np.abs(t) < 1e-9] = 1.0 + beta * (4 / np.pi - 1)
        taps = taps / np.sqrt(np.sum(taps**2))
        self._rrc_taps = taps.astype(np.float32)

    def read_one(self) -> dict | None:
        """Read one chunk from the SDR and attempt to decode a packet."""
        import SoapySDR
        from SoapySDR import SOAPY_SDR_RX

        buf = np.zeros(self._chunk_size, dtype=np.complex64)
        try:
            sr = self._sdr.readStream(
                self._rx_stream, [buf], self._chunk_size, timeoutUs=5_000_000
            )
        except Exception:
            return None

        if sr.ret <= 0:
            return None

        samples = buf[: sr.ret]
        self._raw_iq = samples
        return self._decode(samples)

    def _decode(self, samples: np.ndarray) -> dict | None:
        """Decode IQ samples into a packet dict (or None if no valid packet)."""
        # Lazy import — test isolation when rf/packet/src/ is not on path
        from packet_codec import packet_decode

        samples = samples - np.mean(samples)
        max_val: float = float(np.max(np.abs(samples)))
        if max_val < 0.1:
            return None

        t = np.arange(len(samples)) / self.config.sample_rate
        lo = np.exp(-2j * np.pi * self._fo_est * t)
        samples = (samples * lo).astype(np.complex64)
        filtered = np.convolve(samples, self._rrc_taps, mode="same")
        denom_value: float = float(np.sqrt(np.mean(np.abs(filtered) ** 2) + 1e-30))
        filtered = filtered / denom_value

        sps = self.config.sps
        sync_word_bits = [
            1, 0, 1, 0, 1, 1, 0, 0,
            1, 1, 0, 1, 1, 1, 0, 1,
            1, 0, 1, 0, 0, 1, 0, 0,
            1, 1, 1, 0, 0, 0, 1, 0,
        ]
        sync_symbols = np.array([1 if b else -1 for b in sync_word_bits], dtype=np.float32)
        corr = np.abs(np.correlate(np.real(filtered), sync_symbols, mode="valid"))
        threshold: float = float(np.mean(corr) + 2.5 * np.std(corr))
        peaks = np.where(corr > threshold)[0]

        if len(peaks) == 0:
            return None

        peak = int(peaks[0])
        symbols = np.real(filtered[peak::sps])
        bits = np.where(symbols > 0, 1, 0).astype(np.uint8).tolist()
        bits.extend([0] * 8)
        byte_list: list[int] = []
        for i in range(0, len(bits) - 7, 8):
            b = 0
            for j in range(8):
                b = (b << 1) | bits[i + j]
            byte_list.append(b)
        payload = packet_decode(bytes(byte_list))
        if payload is None:
            return None
        import json
        return json.loads(payload.decode("utf-8"))

    def compute_spectrum(self, points: int = 256) -> list[float] | None:
        """Compute power spectrum from latest raw IQ samples."""
        if self._raw_iq is None or len(self._raw_iq) == 0:
            return None
        fft = np.fft.fft(self._raw_iq * np.hanning(len(self._raw_iq)))
        mag = np.abs(np.fft.fftshift(fft))
        mag_db = 20 * np.log10(mag + 1e-30)
        indices = np.linspace(0, len(mag_db) - 1, points, dtype=int)
        return mag_db[indices].tolist()

    def close(self) -> None:
        """Clean up SoapySDR resources."""
        import SoapySDR
        from SoapySDR import SOAPY_SDR_RX

        if self._rx_stream is not None:
            try:
                self._sdr.deactivateStream(self._rx_stream)
                self._sdr.closeStream(self._rx_stream)
            except Exception:
                pass
            self._rx_stream = None
        self._sdr = None


class AsyncPacketReceiver:
    """Async bridge that runs ReceiverWorker in a thread pool executor.

    on_packet / on_spectrum / on_error are async callbacks invoked on the event loop.
    """

    def __init__(
        self,
        on_packet: Callable[[dict], Awaitable[None]],
        on_spectrum: Callable[[SpectrumFrame], Awaitable[None]],
        on_error: Callable[[str, str], Awaitable[None]],
        spectrum_points: int = 256,
        spectrum_interval: int = 20,
    ):
        self._on_packet = on_packet
        self._on_spectrum = on_spectrum
        self._on_error = on_error
        self._spectrum_points = spectrum_points
        self._spectrum_interval = spectrum_interval
        self._executor = ThreadPoolExecutor(max_workers=1)
        self._running = False
        self._task: asyncio.Task | None = None
        self._worker: ReceiverWorker | None = None

    async def start(self, worker: ReceiverWorker) -> None:
        """Open the SDR in the executor, then begin the read loop."""
        self._running = True
        self._worker = worker
        loop = asyncio.get_event_loop()

        try:
            await loop.run_in_executor(self._executor, worker.open)
        except Exception as e:
            await self._on_error("HARDWARE_ERR", str(e))
            raise

        self._task = asyncio.create_task(self._run_loop())

    async def _run_loop(self) -> None:
        """Main read loop: read chunks, decode, publish spectrum periodically."""
        loop = asyncio.get_event_loop()
        chunk_count = 0
        while self._running:
            try:
                result = await loop.run_in_executor(
                    self._executor, self._worker.read_one
                )
                if result is not None:
                    await self._on_packet(result)

                chunk_count += 1
                if chunk_count % self._spectrum_interval == 0:
                    spectrum = await loop.run_in_executor(
                        self._executor,
                        self._worker.compute_spectrum,
                        self._spectrum_points,
                    )
                    if spectrum is not None:
                        frame = self._build_spectrum_frame(spectrum)
                        await self._on_spectrum(frame)
            except Exception as e:
                await self._on_error("HARDWARE_ERR", str(e))
                break

    def _build_spectrum_frame(self, points: list[float]) -> SpectrumFrame:
        """Build a SpectrumFrame from computed power values."""
        w = self._worker
        return SpectrumFrame(
            fc_hz=w.config.freq_hz if w else 0,
            span_hz=w.config.sample_rate if w else 0,
            points=points,
            ts=time.time(),
        )

    async def stop(self) -> None:
        """Cancel the read loop and shut down the executor."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        if self._worker is not None:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(self._executor, self._worker.close)
        self._executor.shutdown(wait=True)
