# receiver-server/tests/test_models.py
import pytest
from pydantic import ValidationError
from models import (
    EnvironmentPayload, MotionPayload, PositionPayload, PowerPayload,
    AccelData, GyroData, AttData,
    ReceiverStatus, ReceiverState, SpectrumFrame, ErrorInfo, ErrorCode,
)


class TestTelemetryPayloads:
    def test_environment_payload_valid(self):
        pkt = EnvironmentPayload(
            type="environment", temp_ext_c=-42.6, temp_int_c=12.4,
            pressure_hpa=72.8, humidity_pct=4.2, baro_alt_m=18190.5,
        )
        assert pkt.type == "environment"
        assert pkt.temp_ext_c == -42.6

    def test_environment_payload_wrong_type_rejected(self):
        with pytest.raises(ValidationError):
            EnvironmentPayload(
                type="motion", temp_ext_c=-42.6, temp_int_c=12.4,
                pressure_hpa=72.8, humidity_pct=4.2, baro_alt_m=18190.5,
            )

    def test_environment_payload_missing_field(self):
        with pytest.raises(ValidationError):
            EnvironmentPayload(type="environment", temp_ext_c=-42.6)

    def test_motion_payload_valid(self):
        pkt = MotionPayload(
            type="motion", gs_mps=13.8, vs_mps=5.4,
            heading_deg=72.6, cog_deg=74.1,
            accel={"x": 0.03, "y": -0.08, "z": 9.71},
            gyro_dps={"r": 0.4, "p": -0.2, "y": 1.1},
            att_deg={"roll": 2.8, "pitch": -4.1, "yaw": 71.9},
        )
        assert pkt.accel.x == 0.03

    def test_motion_payload_nested_validation(self):
        with pytest.raises(ValidationError):
            MotionPayload(
                type="motion", gs_mps=13.8, vs_mps=5.4,
                heading_deg=72.6, cog_deg=74.1,
                accel={"x": "bad"}, gyro_dps={"r": 0},
                att_deg={"roll": 0, "pitch": 0, "yaw": 0},
            )

    def test_position_payload_valid(self):
        pkt = PositionPayload(
            type="position", lat=39.318742, lon=-120.328915,
            alt_m=18342.7, agl_m=17210.3,
            fix=True, fix_type="3d", sats=14, hdop=0.82, vdop=1.34,
        )
        assert pkt.fix is True

    def test_power_payload_valid(self):
        pkt = PowerPayload(
            type="power", bat_v=7.62, bat_a=0.84, bat_w=6.4,
            bat_pct=68, bat_temp_c=8.1,
        )
        assert pkt.bat_pct == 68


class TestSubModels:
    def test_accel_data_from_dict(self):
        a = AccelData(x=0.03, y=-0.08, z=9.71)
        assert a.z == 9.71


class TestReceiverStatus:
    def test_defaults(self):
        s = ReceiverStatus(running=False, state=ReceiverState.IDLE)
        assert s.freq_hz == 0
        assert s.packets_total == 0

    def test_serialization(self):
        s = ReceiverStatus(
            running=True, state=ReceiverState.RUNNING,
            freq_hz=433500000, sample_rate=2000000,
            gain_lna=32, gain_vga=30, gain_amp=0,
            packets_total=42, packets_valid=40,
            symbol_rate=100000, sps=20,
        )
        d = s.model_dump()
        assert d["running"] is True
        assert d["state"] == "running"
        assert d["freq_hz"] == 433500000


class TestSpectrumFrame:
    def test_valid(self):
        sf = SpectrumFrame(fc_hz=433500000, span_hz=2000000, points=[-80.0, -75.0, -70.0], ts=12345.0)
        assert sf.fc_hz == 433500000
        assert len(sf.points) == 3

    def test_serialization(self):
        sf = SpectrumFrame(fc_hz=433500000, span_hz=2000000, points=[-80.0], ts=12345.0)
        d = sf.model_dump()
        assert d["fc_hz"] == 433500000
        assert d["span_hz"] == 2000000


class TestErrorModels:
    def test_error_info_valid(self):
        err = ErrorInfo(code=ErrorCode.HARDWARE_ERR, message="SDR not found")
        assert err.code == ErrorCode.HARDWARE_ERR
        assert err.message == "SDR not found"

    def test_error_code_values(self):
        assert ErrorCode.DEVICE_LOST.value == "DEVICE_LOST"
        assert ErrorCode.SIGNAL_LOST.value == "SIGNAL_LOST"
        assert ErrorCode.HARDWARE_ERR.value == "HARDWARE_ERR"
