"""Connection Tab — HackRF device discovery and configuration."""

import os
from datetime import datetime

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QListWidget,
    QLabel, QLineEdit, QPlainTextEdit, QMessageBox, QGroupBox,
    QFormLayout, QSlider,
)
from hab_engine.widgets import GlassCard, PrimaryButton, StatusPill

try:
    import SoapySDR
    SOAPY_AVAILABLE = True
except ImportError:
    SOAPY_AVAILABLE = False


class ConnectionTab(QWidget):
    def __init__(self, engine=None, parent=None) -> None:
        super().__init__(parent)
        self.engine = engine
        self.discovered_devices = []
        self.connected_device = None

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(24, 20, 24, 20)
        main_layout.setSpacing(16)

        # Header
        header = QLabel("Device Connection")
        header.setStyleSheet("""
            font-size: 18px; font-weight: 700;
            color: rgba(255, 255, 255, 0.87); letter-spacing: -0.3px;
        """)
        main_layout.addWidget(header)

        # ── Device Discovery Card ──
        device_card = GlassCard()
        device_layout = QVBoxLayout(device_card)
        device_layout.setSpacing(12)

        device_header = QLabel("HACKRF DEVICE")
        device_header.setStyleSheet("""
            font-size: 10px; font-weight: 700;
            color: rgba(255, 255, 255, 0.40); letter-spacing: 1.5px;
        """)
        device_layout.addWidget(device_header)

        controls = QHBoxLayout()
        self.btn_refresh = QPushButton("Refresh")
        self.btn_connect = PrimaryButton("Connect")
        self.btn_disconnect = QPushButton("Disconnect")
        self.btn_disconnect.setEnabled(False)
        controls.addWidget(self.btn_refresh)
        controls.addWidget(self.btn_connect)
        controls.addWidget(self.btn_disconnect)
        controls.addStretch()
        device_layout.addLayout(controls)

        self.device_list = QListWidget()
        self.device_list.setMinimumHeight(80)
        self.device_list.setMaximumHeight(120)
        device_layout.addWidget(QLabel("Available Devices:"))
        device_layout.addWidget(self.device_list)
        main_layout.addWidget(device_card)

        # ── Connection Parameters Card ──
        params_card = GlassCard()
        params_layout = QVBoxLayout(params_card)
        params_layout.setSpacing(12)

        params_header = QLabel("RF PARAMETERS")
        params_header.setStyleSheet("""
            font-size: 10px; font-weight: 700;
            color: rgba(255, 255, 255, 0.40); letter-spacing: 1.5px;
        """)
        params_layout.addWidget(params_header)

        params_form = QFormLayout()
        params_form.setSpacing(12)

        # Frequency
        self.input_frequency = QLineEdit("434.000")
        freq_row = QHBoxLayout()
        freq_row.addWidget(self.input_frequency)
        freq_row.addWidget(QLabel("MHz"))
        params_form.addRow("Frequency:", freq_row)

        # LO ppm
        self.input_lo_ppm = QLineEdit("0")
        lo_row = QHBoxLayout()
        lo_row.addWidget(self.input_lo_ppm)
        lo_row.addWidget(QLabel("ppm"))
        params_form.addRow("LO ppm:", lo_row)

        # Sample rate
        self.input_sample_rate = QLineEdit("2.0")
        sr_row = QHBoxLayout()
        sr_row.addWidget(self.input_sample_rate)
        sr_row.addWidget(QLabel("Msps"))
        params_form.addRow("Sample Rate:", sr_row)

        # LNA Gain
        lna_row = QHBoxLayout()
        self.slider_lna = QSlider(Qt.Horizontal)
        self.slider_lna.setMinimum(0)
        self.slider_lna.setMaximum(40)
        self.slider_lna.setValue(16)
        self.slider_lna.setTickPosition(QSlider.TicksBelow)
        self.slider_lna.setTickInterval(8)
        self.label_lna = QLabel("16 dB")
        self.slider_lna.valueChanged.connect(
            lambda v: self.label_lna.setText(f"{v} dB")
        )
        lna_row.addWidget(self.slider_lna)
        lna_row.addWidget(self.label_lna)
        params_form.addRow("LNA Gain:", lna_row)

        # VGA Gain
        vga_row = QHBoxLayout()
        self.slider_vga = QSlider(Qt.Horizontal)
        self.slider_vga.setMinimum(0)
        self.slider_vga.setMaximum(62)
        self.slider_vga.setValue(20)
        self.slider_vga.setTickPosition(QSlider.TicksBelow)
        self.slider_vga.setTickInterval(10)
        self.label_vga = QLabel("20 dB")
        self.slider_vga.valueChanged.connect(
            lambda v: self.label_vga.setText(f"{v} dB")
        )
        vga_row.addWidget(self.slider_vga)
        vga_row.addWidget(self.label_vga)
        params_form.addRow("VGA Gain:", vga_row)

        self.btn_apply = QPushButton("Apply Parameters")
        self.btn_apply.setEnabled(False)
        params_form.addRow(self.btn_apply)
        params_layout.addLayout(params_form)
        main_layout.addWidget(params_card)

        # ── Log ──
        log_card = GlassCard()
        log_layout = QVBoxLayout(log_card)
        log_layout.setSpacing(8)

        log_header = QLabel("CONNECTION LOG")
        log_header.setStyleSheet("""
            font-size: 10px; font-weight: 700;
            color: rgba(255, 255, 255, 0.40); letter-spacing: 1.5px;
        """)
        log_layout.addWidget(log_header)

        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setPlaceholderText("Connection logs will appear here...")
        self.log.setMaximumHeight(150)
        log_layout.addWidget(self.log)
        main_layout.addWidget(log_card)

        # ── Signals ──
        self.btn_refresh.clicked.connect(self.refresh_devices)
        self.btn_connect.clicked.connect(self.connect_device)
        self.btn_disconnect.clicked.connect(self.disconnect_device)
        self.btn_apply.clicked.connect(self.apply_params)

        # Auto-refresh
        self.refresh_devices()

    def log_msg(self, msg: str):
        ts = datetime.now().strftime("%H:%M:%S")
        self.log.appendPlainText(f"[{ts}] {msg}")

    def selected_device(self):
        idx = self.device_list.currentRow()
        if 0 <= idx < len(self.discovered_devices):
            return self.discovered_devices[idx]
        return None

    def refresh_devices(self):
        if not SOAPY_AVAILABLE:
            self.log_msg("SoapySDR not installed")
            return
        try:
            self.log_msg("Scanning for HackRF devices...")
            self.device_list.clear()
            self.discovered_devices = []
            results = SoapySDR.Device.enumerate("driver=hackrf")
            if not results:
                self.log_msg("No HackRF devices found")
                return
            for r in results:
                self.discovered_devices.append(r)
                d = dict(r)
                label = d.get("label", "HackRF")
                serial = d.get("serial", "unknown")
                self.device_list.addItem(f"{label}  ·  {serial}")
            self.log_msg(f"Found {len(results)} device(s)")
        except Exception as e:
            self.log_msg(f"Scan failed: {e}")

    def connect_device(self):
        if not SOAPY_AVAILABLE:
            return
        device = self.selected_device()
        if not device:
            QMessageBox.information(self, "Connect", "Select a device first.")
            return
        try:
            if self.connected_device:
                self.connected_device = None
            self.log_msg("Connecting...")
            self.connected_device = SoapySDR.Device(device)
            self.log_msg("Connected")
            self.btn_disconnect.setEnabled(True)
            self.btn_apply.setEnabled(True)
            self.apply_params()

            if self.engine:
                from hab_engine.models import DeviceInfo
                info = DeviceInfo(
                    serial=dict(device).get("serial", "unknown"),
                    connected=True,
                    frequency=float(self.input_frequency.text()) * 1e6,
                    sample_rate=float(self.input_sample_rate.text()) * 1e6,
                )
                self.engine.update_device_state(info)
        except Exception as e:
            self.log_msg(f"Connection failed: {e}")

    def disconnect_device(self):
        self.connected_device = None
        self.btn_disconnect.setEnabled(False)
        self.btn_apply.setEnabled(False)
        self.log_msg("Disconnected")
        if self.engine:
            from hab_engine.models import DeviceInfo
            self.engine.update_device_state(DeviceInfo())

    def apply_params(self):
        if not self.connected_device:
            return
        try:
            freq = float(self.input_frequency.text()) * 1e6
            sr = float(self.input_sample_rate.text()) * 1e6
            lna = self.slider_lna.value()
            vga = self.slider_vga.value()

            self.connected_device.setSampleRate(SoapySDR.SOAPY_SDR_RX, 0, sr)
            self.connected_device.setFrequency(SoapySDR.SOAPY_SDR_RX, 0, freq)
            self.connected_device.setGain(SoapySDR.SOAPY_SDR_RX, 0, "LNA", lna)
            self.connected_device.setGain(SoapySDR.SOAPY_SDR_RX, 0, "VGA", vga)

            self.log_msg(f"Applied: {freq/1e6} MHz, {sr/1e6} Msps, LNA={lna}, VGA={vga}")
        except Exception as e:
            self.log_msg(f"Apply failed: {e}")

    def get_connection_params(self) -> dict:
        return {
            "frequency": float(self.input_frequency.text()) * 1e6,
            "sample_rate": float(self.input_sample_rate.text()) * 1e6,
            "lna_gain": self.slider_lna.value(),
            "vga_gain": self.slider_vga.value(),
            "lo_ppm": int(self.input_lo_ppm.text()),
        }

    def is_device_connected(self) -> bool:
        return self.connected_device is not None

    def get_connected_device(self):
        return self.connected_device

    def get_device_args(self) -> dict:
        if self.connected_device is None:
            return None
        return self.selected_device()
