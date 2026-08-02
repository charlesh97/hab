from __future__ import annotations

import os
import signal
import subprocess
import time
from unittest import mock

import numpy as np

from ground.rx.combined_rx import (
    BPSK_DECODE_SAMPLES,
    CHANNEL_FILTER_TAPS,
    CHUNK_SAMPLES,
    VIDEO_PORT,
    CompositeReceiver,
    parse_args,
)
from ground.rx.demod import PacketDecoder
from payload.tx.combined_tx import make_packet_waveform, root_raised_cosine_taps
from protocol.telemetry import FrameType, PositionFrame


SAMPLE_RATE = 8_000_000
OFFSET = 700_000
COMMON_CFO_HZ = -10_000


def _receiver() -> CompositeReceiver:
    return CompositeReceiver(parse_args(["--no-dvbs2"]))


def _split_bpsk(receiver: CompositeReceiver, samples: np.ndarray) -> np.ndarray:
    chunks = []
    for start in range(0, len(samples), CHUNK_SAMPLES):
        _, bpsk = receiver._split(samples[start : start + CHUNK_SAMPLES])
        chunks.append(bpsk)
    return np.concatenate(chunks)


def _position_payload() -> bytes:
    return PositionFrame(
        type=FrameType.POSITION,
        seq=42,
        lat=48.1173,
        lon=11.516667,
        alt_m=545.4,
        agl_m=535.4,
        fix=True,
        fix_type="2d",
        sats=8,
        hdop=0.9,
        vdop=0.0,
    ).pack()


def _composite_capture(
    sample_count: int | None = None,
    include_bpsk: bool = True,
) -> tuple[np.ndarray, bytes]:
    """Build DVB-S2-like QPSK plus an optional live-format BPSK burst."""
    rng = np.random.default_rng(20260731)
    if sample_count is None:
        sample_count = int(0.15 * SAMPLE_RATE)

    # A 2 Msym/s RRC-shaped QPSK waveform gives the same occupied plateau
    # width as the live DVB-S2 branch without needing a DVB-S2 encoder here.
    qpsk_count = (sample_count + 3) // 4 + 20
    qpsk = (
        2 * rng.integers(0, 2, qpsk_count) - 1
        + 1j * (2 * rng.integers(0, 2, qpsk_count) - 1)
    ) / np.sqrt(2.0)
    upsampled = np.zeros(qpsk_count * 4, dtype=np.complex64)
    upsampled[::4] = qpsk
    dvbs2 = np.convolve(
        upsampled,
        root_raised_cosine_taps(4),
        mode="same",
    )[:sample_count]
    dvbs2 = np.asarray(dvbs2 / np.max(np.abs(dvbs2)), dtype=np.complex64)

    payload = _position_payload()
    packet = make_packet_waveform(payload, SAMPLE_RATE)
    bpsk = np.zeros(sample_count, dtype=np.complex64)
    packet_start = int(0.05 * SAMPLE_RATE)
    if include_bpsk:
        bpsk[packet_start : packet_start + len(packet)] = packet

    # Match the live frequency plan and measured common HackRF LO error:
    # DVB-S2 at +700 kHz, BPSK at -700 kHz, both shifted -10 kHz.
    # After the RX's +700 kHz mixer, BPSK is at -10 kHz while the
    # DVB-S2 occupied edge begins near +40 kHz and its plateau is farther out.
    indexes = np.arange(sample_count, dtype=np.float64)
    subcarrier = np.exp(2j * np.pi * OFFSET * indexes / SAMPLE_RATE)
    common_cfo = np.exp(2j * np.pi * COMMON_CFO_HZ * indexes / SAMPLE_RATE)
    noise = 0.005 * (
        rng.standard_normal(sample_count)
        + 1j * rng.standard_normal(sample_count)
    )
    composite = (
        (0.65 * dvbs2 * subcarrier + 0.45 * bpsk * subcarrier.conjugate())
        * common_cfo
        + noise
    )
    return np.asarray(composite, dtype=np.complex64), payload


def test_channel_filter_passes_offset_burst_and_rejects_dvbs2_center() -> None:
    sample_count = 8 * CHUNK_SAMPLES
    indexes = np.arange(sample_count, dtype=np.float64)

    # The common -10 kHz LO error remains after the configured -700 kHz
    # BPSK subcarrier is mixed to baseband.
    desired = np.exp(
        2j * np.pi * (-OFFSET + COMMON_CFO_HZ) * indexes / SAMPLE_RATE
    ).astype(np.complex64)
    dvbs2_center = np.exp(
        2j * np.pi * (OFFSET + COMMON_CFO_HZ) * indexes / SAMPLE_RATE
    ).astype(np.complex64)

    desired_out = _split_bpsk(_receiver(), desired)[2_000:]
    plateau_out = _split_bpsk(_receiver(), dvbs2_center)[2_000:]
    desired_rms = float(np.sqrt(np.mean(np.abs(desired_out) ** 2)))
    plateau_rms = float(np.sqrt(np.mean(np.abs(plateau_out) ** 2)))

    assert desired_rms > 0.95
    assert plateau_rms < 0.05 * desired_rms


def test_default_frequency_plan_filter_and_decode_queue() -> None:
    receiver = _receiver()

    assert receiver.args.offset == OFFSET
    assert CHANNEL_FILTER_TAPS == 129
    assert len(receiver.channel_taps) == 129
    assert receiver._decode_queue.maxsize == 8


def test_filter_and_mixer_state_are_phase_continuous_across_chunks() -> None:
    rng = np.random.default_rng(9)
    samples = (
        rng.standard_normal(100_003) + 1j * rng.standard_normal(100_003)
    ).astype(np.complex64)

    _, whole = _receiver()._split(samples)
    chunked_receiver = _receiver()
    chunked_parts = []
    starts = (0, 12_345, 45_678, 80_001, len(samples))
    for start, end in zip(starts, starts[1:]):
        _, part = chunked_receiver._split(samples[start:end])
        chunked_parts.append(part)

    np.testing.assert_allclose(
        np.concatenate(chunked_parts),
        whole,
        rtol=1e-5,
        atol=1e-5,
    )


def test_filter_tracks_configured_offset() -> None:
    configured_offset = 230_000
    receiver = CompositeReceiver(
        parse_args(["--no-dvbs2", "--offset", str(configured_offset)])
    )
    indexes = np.arange(4 * CHUNK_SAMPLES, dtype=np.float64)
    bpsk_subcarrier = np.exp(
        -2j * np.pi * configured_offset * indexes / SAMPLE_RATE
    ).astype(np.complex64)

    baseband = _split_bpsk(receiver, bpsk_subcarrier)[2_000:]
    phase_step = float(np.angle(np.vdot(baseband[:-1], baseband[1:])))

    assert float(np.mean(np.abs(baseband))) > 0.95
    assert abs(phase_step) < 1e-4


def test_synthetic_composite_decodes_valid_frame_with_measured_cfo() -> None:
    composite, payload = _composite_capture()
    bpsk = _split_bpsk(_receiver(), composite)

    results = PacketDecoder(bursts_only=True).decode(bpsk)
    matching = [result for result in results if result[0] == payload]

    assert matching
    assert abs(matching[0][2] - COMMON_CFO_HZ) < 1_000


def test_full_synthetic_decode_batch_meets_realtime_budget() -> None:
    composite, payload = _composite_capture(
        sample_count=BPSK_DECODE_SAMPLES * (SAMPLE_RATE // 2_000_000),
    )
    bpsk = _split_bpsk(_receiver(), composite)
    assert len(bpsk) == BPSK_DECODE_SAMPLES

    decoder = PacketDecoder(bursts_only=True)
    with mock.patch.object(
        decoder,
        "_costas_correct",
        wraps=decoder._costas_correct,
    ) as costas_correct:
        start = time.perf_counter()
        results = decoder.decode(bpsk)
        duration = time.perf_counter() - start

    assert any(result[0] == payload for result in results)
    assert costas_correct.call_count == 1
    assert duration < 0.25, f"full decode batch took {duration:.3f} s"


def test_synthetic_plateau_only_input_decodes_nothing() -> None:
    composite, _ = _composite_capture(include_bpsk=False)
    bpsk = _split_bpsk(_receiver(), composite)

    assert PacketDecoder(bursts_only=True).decode(bpsk) == []


def test_burst_only_decoder_skips_plateau_without_demodulating_it() -> None:
    rng = np.random.default_rng(17)
    plateau = (
        rng.standard_normal(1_048_576) + 1j * rng.standard_normal(1_048_576)
    ).astype(np.complex64)
    decoder = PacketDecoder(bursts_only=True)

    with mock.patch.object(decoder, "_decode_segment") as decode_segment:
        assert decoder.decode(plateau) == []

    decode_segment.assert_not_called()


def test_no_bpsk_mode_does_not_initialize_channel_filter() -> None:
    receiver = CompositeReceiver(parse_args(["--no-bpsk"]))

    assert receiver.args.offset == 0.0
    assert not hasattr(receiver, "channel_taps")


def test_video_bridge_spawn_retries_once_when_listener_does_not_bind() -> None:
    receiver = CompositeReceiver(parse_args(["--no-bpsk"]))
    first_bridge = mock.Mock()
    second_bridge = mock.Mock()

    with (
        mock.patch(
            "ground.rx.combined_rx.subprocess.Popen",
            side_effect=[first_bridge, second_bridge],
        ) as popen,
        mock.patch(
            "ground.rx.combined_rx._wait_listener",
            side_effect=[False, True],
        ) as wait_listener,
    ):
        bridge = receiver._spawn_video_bridge()

    assert bridge is second_bridge
    assert popen.call_count == 2
    assert wait_listener.call_args_list == [
        mock.call(VIDEO_PORT, timeout=14.0),
        mock.call(VIDEO_PORT, timeout=14.0),
    ]
    first_bridge.kill.assert_called_once_with()


def test_video_bridge_supervisor_replaces_exited_bridge() -> None:
    receiver = CompositeReceiver(parse_args(["--no-bpsk"]))
    exited_bridge = mock.Mock()
    exited_bridge.poll.return_value = 0
    replacement = mock.Mock()
    receiver.video_bridge = exited_bridge
    listener = subprocess.CompletedProcess(
        args=[],
        returncode=0,
        stdout="ffmpeg 123 user 4u IPv4 TCP *:8001 (LISTEN)\n",
    )

    def stop_after_check(_seconds: float) -> None:
        receiver.stop_requested = True

    with (
        mock.patch.object(receiver, "_kill_stale_video_bridges") as kill_stale,
        mock.patch(
            "ground.rx.combined_rx.subprocess.Popen",
            return_value=replacement,
        ) as popen,
        mock.patch(
            "ground.rx.combined_rx.subprocess.run",
            return_value=listener,
        ) as run,
        mock.patch(
            "ground.rx.combined_rx.time.sleep",
            side_effect=stop_after_check,
        ),
    ):
        receiver._video_bridge_supervisor()

    kill_stale.assert_called_once_with()
    assert receiver.video_bridge is replacement
    popen.assert_called_once_with(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "warning",
            "-i",
            f"udp://127.0.0.1:{receiver.args.udp_port}",
            "-c:v",
            "mjpeg",
            "-q:v",
            "5",
            "-f",
            "mpjpeg",
            "-listen",
            "1",
            f"http://0.0.0.0:{VIDEO_PORT}/video",
        ],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    run.assert_called_once_with(
        ["lsof", "-nP", f"-iTCP:{VIDEO_PORT}", "-sTCP:LISTEN"],
        capture_output=True,
        text=True,
        timeout=5,
    )


def test_video_bridge_supervisor_does_not_respawn_after_stop() -> None:
    receiver = CompositeReceiver(parse_args(["--no-bpsk"]))
    live_bridge = mock.Mock()
    live_bridge.poll.return_value = None
    receiver.video_bridge = live_bridge

    def request_stop(_seconds: float) -> None:
        receiver.stop_requested = True
        live_bridge.poll.return_value = 0

    with (
        mock.patch.object(receiver, "_kill_stale_video_bridges"),
        mock.patch.object(receiver, "_spawn_video_bridge") as spawn_bridge,
        mock.patch(
            "ground.rx.combined_rx.time.sleep",
            side_effect=request_stop,
        ),
    ):
        receiver._video_bridge_supervisor()

    spawn_bridge.assert_not_called()


def test_video_bridge_stale_cleanup_skips_current_process() -> None:
    receiver = CompositeReceiver(parse_args(["--no-bpsk"]))
    stale_pid = os.getpid() + 1000
    result = subprocess.CompletedProcess(
        args=[],
        returncode=0,
        stdout=f"{os.getpid()}\n{stale_pid}\n",
    )

    with (
        mock.patch(
            "ground.rx.combined_rx.subprocess.run",
            return_value=result,
        ) as run,
        mock.patch("ground.rx.combined_rx.os.kill") as kill,
    ):
        receiver._kill_stale_video_bridges()

    run.assert_called_once_with(
        ["pgrep", "-f", f"udp://127.0.0.1:{receiver.args.udp_port}"],
        capture_output=True,
        text=True,
        timeout=10,
    )
    kill.assert_called_once_with(stale_pid, signal.SIGKILL)


def test_no_dvbs2_does_not_start_video_bridge_supervisor() -> None:
    receiver = CompositeReceiver(
        parse_args(["--no-bpsk", "--no-dvbs2"])
    )
    hackrf = mock.Mock()
    hackrf.stdout.read.return_value = b""
    hackrf.poll.return_value = 1
    receiver.hackrf_proc = hackrf

    with (
        mock.patch("ground.rx.combined_rx.Thread") as thread,
        mock.patch.object(receiver, "_open_hackrf_transfer"),
        mock.patch.object(receiver, "_spawn_video_bridge") as spawn_bridge,
        mock.patch.object(receiver.dvbs2, "start") as start_dvbs2,
        mock.patch.object(receiver.dvbs2, "close"),
    ):
        receiver.run()

    spawn_bridge.assert_not_called()
    start_dvbs2.assert_not_called()
    assert receiver._video_bridge_worker is None
    assert all(
        call.kwargs["target"] != receiver._video_bridge_supervisor
        for call in thread.call_args_list
    )


def test_shutdown_terminates_live_video_bridge() -> None:
    receiver = CompositeReceiver(parse_args(["--no-bpsk"]))
    bridge = mock.Mock()
    bridge.poll.return_value = None
    receiver.video_bridge = bridge
    hackrf = mock.Mock()
    hackrf.stdout.read.return_value = b""
    hackrf.poll.return_value = 1
    receiver.hackrf_proc = hackrf

    with (
        mock.patch("ground.rx.combined_rx.Thread"),
        mock.patch.object(receiver, "_open_hackrf_transfer"),
        mock.patch.object(receiver.dvbs2, "start"),
        mock.patch.object(receiver.dvbs2, "close"),
    ):
        receiver.run()

    bridge.terminate.assert_called_once_with()
    bridge.wait.assert_called_once_with(timeout=5)
