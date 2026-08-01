from __future__ import annotations

import struct
import time
import unittest
from unittest import mock

import numpy as np

from payload.telemetry.nmea import GPSState, parse_gga, parse_rmc
from payload.tx.combined_tx import (
    BPSK_SYMBOL_RATE,
    CHUNK_SECONDS,
    CompositeTransmitter,
    Dvbs2Pipeline,
    FfmpegProcess,
    RateLimitedLogger,
    build_bpsk_cycle,
    crc16,
    compute_tsrate,
    frequency_interleave,
    make_packet_waveform,
    packet_bits,
    parse_args,
    root_raised_cosine_taps,
)
from protocol.telemetry import FrameType, PositionFrame


GGA = "$GPGGA,123519,4807.038,N,01131.000,E,1,08,0.9,545.4,M,46.9,M,,*47"
RMC = "$GPRMC,123519,A,4807.038,N,01131.000,E,022.4,084.4,230394,003.1,W*6A"


class NMEATests(unittest.TestCase):
    def test_gga_and_rmc_update_position_state(self) -> None:
        gga = parse_gga(GGA)
        rmc = parse_rmc(RMC)
        self.assertIsNotNone(gga)
        self.assertIsNotNone(rmc)
        self.assertAlmostEqual(float(gga["lat"]), 48.1173)
        self.assertAlmostEqual(float(gga["lon"]), 11.516667)
        self.assertAlmostEqual(float(rmc["speed_mps"]), 11.5235456)

        state = GPSState()
        self.assertTrue(state.update(GGA))
        self.assertTrue(state.update(RMC))
        self.assertTrue(state.fix)
        self.assertEqual(state.fix_type, "2d")
        self.assertEqual(state.satellites, 8)
        self.assertAlmostEqual(state.altitude_m, 545.4)
        self.assertAlmostEqual(state.heading_deg, 84.4)

    def test_bad_checksum_is_rejected(self) -> None:
        self.assertIsNone(parse_gga(GGA[:-2] + "00"))
        self.assertIsNone(parse_rmc(RMC[:-2] + "00"))


class BPSKTests(unittest.TestCase):
    def setUp(self) -> None:
        self.frame = PositionFrame(
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
        )
        self.payload = self.frame.pack()

    def test_crc16_xmodem_check_vector(self) -> None:
        self.assertEqual(crc16(b"123456789"), 0x31C3)

    def test_packet_layout_and_waveform_length(self) -> None:
        bits = packet_bits(self.payload)
        self.assertEqual(bits[:8], [1, 0, 1, 0, 1, 0, 1, 0])
        sync = int("".join(str(bit) for bit in bits[256:288]), 2)
        self.assertEqual(sync, 0xE38FC0FC)
        length = int("".join(str(bit) for bit in bits[288:304]), 2)
        self.assertEqual(length, 38)
        expected_crc = struct.pack(">H", crc16(self.payload))
        self.assertEqual(
            bits[-16:],
            [
                (byte >> shift) & 1
                for byte in expected_crc
                for shift in range(7, -1, -1)
            ],
        )

        sample_rate = 4_000_000
        waveform = make_packet_waveform(self.payload, sample_rate)
        expected_symbols = 256 + 32 + 16 + 38 * 8 + 16
        expected_sps = sample_rate // BPSK_SYMBOL_RATE
        self.assertEqual(len(waveform), expected_symbols * expected_sps)
        self.assertEqual(waveform.dtype, np.complex64)
        self.assertAlmostEqual(float(np.max(np.abs(waveform))), 0.7, places=5)

        mapped = 1.0 - 2.0 * np.asarray(bits, dtype=np.float64)
        upsampled = np.zeros(len(mapped) * expected_sps, dtype=np.float64)
        upsampled[::expected_sps] = mapped
        reference = np.convolve(
            upsampled,
            root_raised_cosine_taps(expected_sps),
            mode="same",
        )
        reference *= 0.7 / np.max(np.abs(reference))
        np.testing.assert_allclose(
            waveform, reference.astype(np.complex64), atol=1e-6
        )

    def test_one_second_cycle_contains_packet(self) -> None:
        cycle = build_bpsk_cycle(self.payload, 2_000_000)
        self.assertEqual(len(cycle), 2_000_000)
        self.assertTrue(np.all(cycle[:100_000] == 0))
        self.assertGreater(np.count_nonzero(cycle), 0)


class CompositeDSPTests(unittest.TestCase):
    def test_tsrate_calculation(self) -> None:
        self.assertEqual(compute_tsrate(1e6), 965_327)
        self.assertEqual(compute_tsrate(2e6), 1_930_653)
        self.assertEqual(compute_tsrate(3e6), 2_895_980)
        self.assertEqual(compute_tsrate(4e6), 3_861_306)
        self.assertEqual(
            parse_args(["--sym-rate", "3e6"]).tsrate,
            2_895_980,
        )
        self.assertEqual(
            parse_args(["--tsrate", "1900000"]).tsrate,
            1_900_000,
        )

    def test_frequency_plan_and_phase_continuity(self) -> None:
        sample_rate = 6_000_000
        offset = 1_500_000
        count = 4096
        ones = np.ones(count, dtype=np.complex64)
        first, phase = frequency_interleave(
            ones[:2048], ones[:2048], offset, sample_rate
        )
        second, _ = frequency_interleave(
            ones[2048:], ones[2048:], offset, sample_rate, phase
        )
        split_result = np.concatenate((first, second))
        whole_result, _ = frequency_interleave(
            ones, ones, offset, sample_rate
        )
        np.testing.assert_allclose(split_result, whole_result, atol=1e-6)

        spectrum = np.fft.fftshift(np.fft.fft(whole_result))
        frequencies = np.fft.fftshift(
            np.fft.fftfreq(count, d=1.0 / sample_rate)
        )
        strongest = np.argsort(np.abs(spectrum))[-2:]
        self.assertEqual(
            set(np.rint(frequencies[strongest]).astype(int)),
            {-1_500_000, 1_500_000},
        )
        positive = np.argmin(np.abs(frequencies - offset))
        negative = np.argmin(np.abs(frequencies + offset))
        self.assertGreater(
            np.abs(spectrum[positive]),
            np.abs(spectrum[negative]),
        )

    def test_default_cli_and_dvbs2_command(self) -> None:
        args = parse_args([])
        self.assertEqual(args.center_freq, 914e6)
        self.assertEqual(args.offset, 700e3)
        self.assertEqual(args.sample_rate, 8e6)
        self.assertEqual(args.sym_rate, 2e6)
        self.assertEqual(args.tsrate, 1_930_653)
        self.assertTrue(args.pilots)

        pipeline = Dvbs2Pipeline(args, RateLimitedLogger())
        command = pipeline._tx_command()
        self.assertIn("--source", command)
        self.assertIn("fd", command)
        self.assertEqual(command[command.index("--in-fd") + 1], "0")
        self.assertEqual(command[command.index("--out-fd") + 1], "1")
        self.assertNotIn("--out-real-time", command)
        self.assertEqual(
            command[command.index("--samp-rate") + 1],
            "8000000",
        )
        self.assertEqual(
            command[command.index("--tsrate") + 1],
            "1930653",
        )
        # TX tunes to center + offset (DVB-S2 sits above center)
        self.assertEqual(
            command[command.index("--freq") + 1],
            "914700000",
        )
        self.assertIn("--pilots", command)

        composite_ffmpeg_command = pipeline._ffmpeg_command()
        self.assertEqual(
            composite_ffmpeg_command[
                composite_ffmpeg_command.index("-an") + 1
            ],
            "-vf",
        )
        self.assertEqual(
            composite_ffmpeg_command[
                composite_ffmpeg_command.index("-vf") + 2
            ],
            "-c:v",
        )

        video_bitrate = int(args.tsrate * 0.78)
        video_bitrate = (video_bitrate // 1000) * 1000
        ffmpeg = FfmpegProcess(
            udp_port=args.video_udp,
            errors=RateLimitedLogger(),
            tsrate=args.tsrate,
            video_bitrate=video_bitrate,
        )
        ffmpeg_command = ffmpeg.command()
        self.assertEqual(
            ffmpeg_command[ffmpeg_command.index("-video_size") + 1],
            "1280x720",
        )
        for option, expected in {
            "-b:v": "1505000",
            "-maxrate": "1505000",
            "-bufsize": "1505000",
            "-g": "15",
            "-keyint_min": "15",
            "-muxrate": "1930653",
        }.items():
            self.assertEqual(
                ffmpeg_command[ffmpeg_command.index(option) + 1],
                expected,
            )

    def test_dvbs2_read_fills_chunk_from_fragmented_pipe(self) -> None:
        class FragmentedReader:
            def __init__(self, data: bytes, fragment_size: int) -> None:
                self.data = data
                self.fragment_size = fragment_size
                self.position = 0
                self.read_count = 0

            def readinto(self, buffer: memoryview) -> int:
                self.read_count += 1
                amount = min(
                    len(buffer),
                    self.fragment_size,
                    len(self.data) - self.position,
                )
                if amount == 0:
                    return 0
                buffer[:amount] = self.data[
                    self.position : self.position + amount
                ]
                self.position += amount
                return amount

        expected = np.arange(4096, dtype=np.float32).astype(np.complex64)
        stdout = FragmentedReader(expected.tobytes(), fragment_size=997)
        pipeline = Dvbs2Pipeline(parse_args([]), RateLimitedLogger())
        pipeline.tx_proc = mock.Mock(stdout=stdout)

        actual = pipeline.read_samples(len(expected))

        np.testing.assert_array_equal(actual, expected)
        self.assertGreater(stdout.read_count, 1)

    def test_frequency_interleave_fits_realtime_chunk_budget(self) -> None:
        sample_rate = 8_000_000
        count = int(sample_rate * CHUNK_SECONDS)
        dvbs2 = np.ones(count, dtype=np.complex64)
        bpsk = np.zeros(count, dtype=np.complex64)

        durations = []
        phase = 0.0
        for _ in range(6):
            start = time.perf_counter()
            _, phase = frequency_interleave(
                dvbs2, bpsk, 700e3, sample_rate, phase
            )
            durations.append(time.perf_counter() - start)

        median_duration = float(np.median(durations[1:]))
        self.assertLess(
            median_duration,
            CHUNK_SECONDS,
            f"interleaver took {median_duration * 1000:.1f} ms for a "
            f"{CHUNK_SECONDS * 1000:.0f} ms chunk",
        )

    def test_gr_mode_command_uses_default_modcod(self) -> None:
        args = parse_args(["--use-gr", "--no-bpsk"])
        tx_process = mock.Mock()
        tx_process.poll.return_value = 0
        ffmpeg_process = mock.Mock()

        with mock.patch(
            "payload.tx.combined_tx.subprocess.Popen",
            side_effect=[tx_process, ffmpeg_process],
        ) as popen:
            CompositeTransmitter(args)._run_gr_mode()

        tx_command = popen.call_args_list[0].args[0]
        modcod_index = tx_command.index("--modcod")
        self.assertEqual(
            tx_command[modcod_index : modcod_index + 2],
            ["--modcod", "QPSK1/2"],
        )

    def test_video_bitrate_scales_with_symbol_rate(self) -> None:
        transmitter = CompositeTransmitter(
            parse_args(["--sym-rate", "1e6"])
        )
        self.assertEqual(transmitter.ffmpeg.tsrate, 965_327)
        self.assertEqual(transmitter.ffmpeg.video_bitrate, 752_000)
        command = transmitter.ffmpeg.command()
        for option in ("-b:v", "-maxrate", "-bufsize"):
            self.assertEqual(
                command[command.index(option) + 1],
                "752000",
            )


if __name__ == "__main__":
    unittest.main()
