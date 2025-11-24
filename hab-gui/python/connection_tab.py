import os
from datetime import datetime

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QListWidget,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QMessageBox,
    QGroupBox,
    QFormLayout,
    QSlider,
)

try:
    import SoapySDR
    SOAPY_AVAILABLE = True
except ImportError:
    SOAPY_AVAILABLE = False


class ConnectionTab(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)

        self.discovered_devices = []
        self.connected_device = None

        # UI
        main_layout = QVBoxLayout(self)

        # Device discovery section
        device_group = QGroupBox("HackRF Device")
        device_layout = QVBoxLayout()

        controls_layout = QHBoxLayout()
        self.btn_refresh = QPushButton("Refresh Devices")
        self.btn_connect = QPushButton("Connect")
        self.btn_disconnect = QPushButton("Disconnect")
        self.btn_disconnect.setEnabled(False)
        controls_layout.addWidget(self.btn_refresh)
        controls_layout.addWidget(self.btn_connect)
        controls_layout.addWidget(self.btn_disconnect)
        controls_layout.addStretch(1)

        self.device_list = QListWidget()
        self.device_list.setAlternatingRowColors(True)
        self.device_list.setMaximumHeight(100)

        device_layout.addLayout(controls_layout)
        device_layout.addWidget(QLabel("Available Devices:"))
        device_layout.addWidget(self.device_list)
        device_group.setLayout(device_layout)

        # Connection parameters section
        params_group = QGroupBox("Connection Parameters")
        params_form = QFormLayout()

        # Frequency
        self.input_frequency = QLineEdit()
        self.input_frequency.setText("434.000")  # MHz
        self.input_frequency.setPlaceholderText("e.g., 434.000")
        freq_layout = QHBoxLayout()
        freq_layout.addWidget(self.input_frequency)
        freq_layout.addWidget(QLabel("MHz"))
        params_form.addRow("Frequency:", freq_layout)

        # LO ppm
        self.input_lo_ppm = QLineEdit()
        self.input_lo_ppm.setText("0")
        self.input_lo_ppm.setPlaceholderText("e.g., 0")
        lo_layout = QHBoxLayout()
        lo_layout.addWidget(self.input_lo_ppm)
        lo_layout.addWidget(QLabel("ppm"))
        params_form.addRow("LO ppm:", lo_layout)

        # Sample rate
        self.input_sample_rate = QLineEdit()
        self.input_sample_rate.setText("2.0")  # Msps
        self.input_sample_rate.setPlaceholderText("e.g., 2.0")
        sr_layout = QHBoxLayout()
        sr_layout.addWidget(self.input_sample_rate)
        sr_layout.addWidget(QLabel("Msps"))
        params_form.addRow("Sample Rate:", sr_layout)

        # LNA Gain
        lna_layout = QHBoxLayout()
        self.slider_lna_gain = QSlider(Qt.Horizontal)
        self.slider_lna_gain.setMinimum(0)
        self.slider_lna_gain.setMaximum(40)
        self.slider_lna_gain.setValue(16)
        self.slider_lna_gain.setTickPosition(QSlider.TicksBelow)
        self.slider_lna_gain.setTickInterval(8)
        self.label_lna_gain = QLabel("16 dB")
        self.slider_lna_gain.valueChanged.connect(
            lambda v: self.label_lna_gain.setText(f"{v} dB")
        )
        lna_layout.addWidget(self.slider_lna_gain)
        lna_layout.addWidget(self.label_lna_gain)
        params_form.addRow("LNA Gain:", lna_layout)

        # VGA Gain
        vga_layout = QHBoxLayout()
        self.slider_vga_gain = QSlider(Qt.Horizontal)
        self.slider_vga_gain.setMinimum(0)
        self.slider_vga_gain.setMaximum(62)
        self.slider_vga_gain.setValue(20)
        self.slider_vga_gain.setTickPosition(QSlider.TicksBelow)
        self.slider_vga_gain.setTickInterval(10)
        self.label_vga_gain = QLabel("20 dB")
        self.slider_vga_gain.valueChanged.connect(
            lambda v: self.label_vga_gain.setText(f"{v} dB")
        )
        vga_layout.addWidget(self.slider_vga_gain)
        vga_layout.addWidget(self.label_vga_gain)
        params_form.addRow("VGA Gain:", vga_layout)

        # Apply button
        self.btn_apply_params = QPushButton("Apply Parameters")
        self.btn_apply_params.setEnabled(False)
        params_form.addRow(self.btn_apply_params)

        params_group.setLayout(params_form)

        # Log
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setPlaceholderText("Connection logs will appear here…")
        self.log.setMaximumHeight(150)

        main_layout.addWidget(device_group)
        main_layout.addWidget(params_group)
        main_layout.addWidget(QLabel("Log:"))
        main_layout.addWidget(self.log)
        main_layout.addStretch(1)

        # Signals
        self.btn_refresh.clicked.connect(self.refresh_devices_clicked)
        self.btn_connect.clicked.connect(self.connect_clicked)
        self.btn_disconnect.clicked.connect(self.disconnect_clicked)
        self.btn_apply_params.clicked.connect(self.apply_params_clicked)

        # Auto-refresh on init
        self.refresh_devices_clicked()

    def append_log(self, message: str) -> None:
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log.appendPlainText(f"[{timestamp}] {message}")
        print(f"[{timestamp}] {message}")

    def selected_device(self):
        idx = self.device_list.currentRow()
        if 0 <= idx < len(self.discovered_devices):
            return self.discovered_devices[idx]
        return None

    def refresh_devices_clicked(self) -> None:
        """Scan for available HackRF devices"""
        if not SOAPY_AVAILABLE:
            self.append_log("ERROR: SoapySDR not installed. Install with: pip install SoapySDR")
            return
            
        try:
            self.append_log("Scanning for HackRF devices...")
            self.device_list.clear()
            self.discovered_devices = []

            # Enumerate HackRF devices
            results = SoapySDR.Device.enumerate("driver=hackrf")
            
            if not results:
                self.append_log("No HackRF devices found.")
                self.append_log("Make sure HackRF is connected and drivers are installed.")
                return

            for result in results:
                self.discovered_devices.append(result)
                # Convert result to dict and extract fields
                d = dict(result)
                label = d.get("label", "")
                serial = d.get("serial", "unknown")
                device_name = d.get("device", "")
                version = d.get("version", "")
                self.device_list.addItem(f"{label} (Serial: {serial}, Device: {device_name}, Version: {version})")
            
            self.append_log(f"Found {len(self.discovered_devices)} HackRF device(s).")
        except Exception as exc:
            self.append_log(f"Device scan failed: {exc}")

    def connect_clicked(self) -> None:
        """Connect to selected HackRF device"""
        if not SOAPY_AVAILABLE:
            self.append_log("ERROR: SoapySDR not installed.")
            return
            
        device = self.selected_device()
        if device is None:
            QMessageBox.information(
                self, "Connect", "Select a device from the list first."
            )
            return

        try:
            if self.connected_device is not None:
                self.connected_device = None

            self.append_log(f"Connecting to {device}...")
            
            # Create device instance
            self.connected_device = SoapySDR.Device(device)
            
            self.append_log("Connected successfully.")
            self.btn_disconnect.setEnabled(True)
            self.btn_apply_params.setEnabled(True)
            
            # Apply initial parameters
            self.apply_params_clicked()
            
        except Exception as exc:
            self.append_log(f"Connection failed: {exc}")
            self.connected_device = None

    def disconnect_clicked(self) -> None:
        """Disconnect from HackRF device"""
        if self.connected_device:
            try:
                self.connected_device = None
                self.append_log("Disconnected.")
            except Exception as exc:
                self.append_log(f"Disconnect error: {exc}")
        self.connected_device = None
        self.btn_disconnect.setEnabled(False)
        self.btn_apply_params.setEnabled(False)

    def apply_params_clicked(self) -> None:
        """Apply connection parameters to HackRF"""
        if not self.connected_device:
            QMessageBox.warning(self, "Apply", "Not connected to a device.")
            return

        try:
            # Get parameters
            freq_mhz = float(self.input_frequency.text())
            freq_hz = freq_mhz * 1e6
            
            sample_rate_msps = float(self.input_sample_rate.text())
            sample_rate_hz = sample_rate_msps * 1e6
            
            lna_gain = self.slider_lna_gain.value()
            vga_gain = self.slider_vga_gain.value()

            # Apply to device
            self.connected_device.setSampleRate(SoapySDR.SOAPY_SDR_RX, 0, sample_rate_hz)
            self.connected_device.setFrequency(SoapySDR.SOAPY_SDR_RX, 0, freq_hz)
            
            # Set gains
            self.connected_device.setGain(SoapySDR.SOAPY_SDR_RX, 0, "LNA", lna_gain)
            self.connected_device.setGain(SoapySDR.SOAPY_SDR_RX, 0, "VGA", vga_gain)

            self.append_log(f"Parameters applied:")
            self.append_log(f"  Frequency: {freq_mhz} MHz")
            self.append_log(f"  Sample Rate: {sample_rate_msps} Msps")
            self.append_log(f"  LNA Gain: {lna_gain} dB")
            self.append_log(f"  VGA Gain: {vga_gain} dB")

        except ValueError as e:
            QMessageBox.warning(self, "Invalid Input", f"Invalid parameter value: {e}")
        except Exception as exc:
            self.append_log(f"Failed to apply parameters: {exc}")

    def get_connection_params(self) -> dict:
        """Get current connection parameters"""
        return {
            "frequency": float(self.input_frequency.text()) * 1e6,
            "sample_rate": float(self.input_sample_rate.text()) * 1e6,
            "lna_gain": self.slider_lna_gain.value(),
            "vga_gain": self.slider_vga_gain.value(),
            "lo_ppm": int(self.input_lo_ppm.text()),
        }
    
    def is_device_connected(self) -> bool:
        """Check if a device is currently connected"""
        return self.connected_device is not None
    
    def get_connected_device(self):
        """Get the connected device object"""
        return self.connected_device
    
    def get_device_args(self) -> dict:
        """Get SoapySDR device arguments for the connected device"""
        if self.connected_device is None:
            return None
        
        device = self.selected_device()
        if device is None:
            return None
        
        return device

