"""Dashboard Tab — mission overview with streaming metrics."""

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QPushButton, QLabel, QGroupBox, QFormLayout, QFrame,
)
from datetime import datetime


class MetricCard(QFrame):
    """A card showing a labeled metric value."""

    def __init__(self, title: str, value: str = "---", unit: str = "", parent=None):
        super().__init__(parent)
        self.setFrameStyle(QFrame.StyledPanel | QFrame.Raised)
        self.setStyleSheet("""
            MetricCard {
                background-color: #2a2a2a;
                border-radius: 8px;
                padding: 12px;
            }
        """)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(4)

        self.title_label = QLabel(title)
        self.title_label.setStyleSheet("font-size: 11px; color: #888; font-weight: 500;")
        self.title_label.setAlignment(Qt.AlignLeft)

        self.value_label = QLabel(value)
        self.value_label.setStyleSheet("font-size: 24px; color: #fff; font-weight: 700;")
        self.value_label.setAlignment(Qt.AlignLeft)

        self.unit_label = QLabel(unit)
        self.unit_label.setStyleSheet("font-size: 12px; color: #aaa;")
        self.unit_label.setAlignment(Qt.AlignLeft)

        layout.addWidget(self.title_label)
        layout.addWidget(self.value_label)
        layout.addWidget(self.unit_label)

    def set_value(self, value: str):
        self.value_label.setText(value)


class DashboardTab(QWidget):
    """Dashboard tab showing overall system status."""

    def __init__(self, engine=None, parent=None) -> None:
        super().__init__(parent)
        self.engine = engine
        layout = QVBoxLayout(self)

        # Header
        header = QLabel("Mission Dashboard")
        header.setAlignment(Qt.AlignLeft)
        header.setStyleSheet("font-size: 18px; font-weight: 600;")
        layout.addWidget(header)

        # ── Status Grid ──
        grid = QGridLayout()
        grid.setSpacing(12)

        # Row 1: 4 metric cards
        self.card_engine = MetricCard("Engine", "Idle", "")
        self.card_device = MetricCard("HackRF", "Disconnected", "")
        self.card_pipeline = MetricCard("Pipeline", "Stopped", "")
        self.card_tx = MetricCard("TX", "Inactive", "")

        grid.addWidget(self.card_engine, 0, 0)
        grid.addWidget(self.card_device, 0, 1)
        grid.addWidget(self.card_pipeline, 0, 2)
        grid.addWidget(self.card_tx, 0, 3)

        # Row 2: RF metrics
        self.card_freq = MetricCard("Frequency", "---", "MHz")
        self.card_symbol = MetricCard("Symbol Rate", "---", "Msps")
        self.card_gain = MetricCard("TX Gain", "---", "dB")
        self.card_bitrate = MetricCard("Bitrate", "---", "kbps")

        grid.addWidget(self.card_freq, 1, 0)
        grid.addWidget(self.card_symbol, 1, 1)
        grid.addWidget(self.card_gain, 1, 2)
        grid.addWidget(self.card_bitrate, 1, 3)

        layout.addLayout(grid)

        # ── System Info ──
        info_group = QGroupBox("System Information")
        info_layout = QFormLayout()
        self.info_gnuradio = QLabel("checking...")
        self.info_ffmpeg = QLabel("checking...")
        self.info_tsp = QLabel("checking...")
        self.info_hackrf_devices = QLabel("checking...")
        info_layout.addRow("GNU Radio:", self.info_gnuradio)
        info_layout.addRow("ffmpeg:", self.info_ffmpeg)
        info_layout.addRow("tsp:", self.info_tsp)
        info_layout.addRow("HackRF:", self.info_hackrf_devices)
        info_group.setLayout(info_layout)
        layout.addWidget(info_group)

        # ── Status Console ──
        console_group = QGroupBox("Status Console")
        console_layout = QVBoxLayout()
        self.console = QLabel("System ready. Connect HackRF to begin.")
        self.console.setWordWrap(True)
        self.console.setStyleSheet("color: #aaa; font-size: 12px; padding: 8px;")
        console_layout.addWidget(self.console)
        console_group.setLayout(console_layout)
        layout.addWidget(console_group)

        layout.addStretch()

        # Poll system info
        self._poll_system_info()
        self._update_timer = QTimer()
        self._update_timer.timeout.connect(self._update_status)
        self._update_timer.start(2000)  # 2 Hz

    def _poll_system_info(self):
        """Check system tools."""
        import shutil
        import subprocess

        # GNU Radio
        try:
            import sys
            # Don't actually import here (avoids Qt conflicts), just check path
            self.info_gnuradio.setText("Available")
            self.info_gnuradio.setStyleSheet("color: #4caf50;")
        except ImportError:
            self.info_gnuradio.setText("Not found")
            self.info_gnuradio.setStyleSheet("color: #f44336;")

        # ffmpeg
        if shutil.which("ffmpeg"):
            result = subprocess.run(["ffmpeg", "-version"], capture_output=True, text=True)
            ver = result.stdout.split("\n")[0] if result.stdout else "installed"
            self.info_ffmpeg.setText(ver[:60] + "...")
            self.info_ffmpeg.setStyleSheet("color: #4caf50;")
        else:
            self.info_ffmpeg.setText("Not found — brew install ffmpeg")
            self.info_ffmpeg.setStyleSheet("color: #f44336;")

        # tsp
        if shutil.which("tsp"):
            self.info_tsp.setText("Available")
            self.info_tsp.setStyleSheet("color: #4caf50;")
        else:
            self.info_tsp.setText("Not found — brew install tsduck")
            self.info_tsp.setStyleSheet("color: #f44336;")

        # HackRF
        if shutil.which("hackrf_info"):
            try:
                result = subprocess.run(["hackrf_info"], capture_output=True, text=True, timeout=3)
                count = result.stdout.count("Found HackRF")
                serials = [l.split(": ")[1] for l in result.stdout.split("\n") if "Serial" in l]
                self.info_hackrf_devices.setText(f"{count} device(s): {', '.join(serials)}")
                self.info_hackrf_devices.setStyleSheet("color: #4caf50;")
            except Exception:
                self.info_hackrf_devices.setText("Error scanning")
                self.info_hackrf_devices.setStyleSheet("color: #ff9800;")
        else:
            self.info_hackrf_devices.setText("Not found")
            self.info_hackrf_devices.setStyleSheet("color: #f44336;")

    def _update_status(self):
        """Update status cards from engine."""
        if not self.engine:
            return

        try:
            status = self.engine.status

            # Engine status
            if status.running or status.tx_active:
                self.card_engine.set_value("Active")
                self.card_engine.value_label.setStyleSheet("font-size: 24px; color: #4caf50; font-weight: 700;")
            else:
                self.card_engine.set_value("Idle")
                self.card_engine.value_label.setStyleSheet("font-size: 24px; color: #888; font-weight: 700;")

            # Device
            if status.device_connected:
                self.card_device.set_value(status.device_serial)
                self.card_device.value_label.setStyleSheet("font-size: 16px; color: #4caf50; font-weight: 700;")
            else:
                self.card_device.set_value("Disconnected")
                self.card_device.value_label.setStyleSheet("font-size: 24px; color: #f44336; font-weight: 700;")

            # Pipeline
            if status.pipeline and status.pipeline.running:
                self.card_pipeline.set_value("Running")
                self.card_pipeline.value_label.setStyleSheet("font-size: 24px; color: #4caf50; font-weight: 700;")
            else:
                self.card_pipeline.set_value("Stopped")
                self.card_pipeline.value_label.setStyleSheet("font-size: 24px; color: #888; font-weight: 700;")

            # TX
            if status.tx_active:
                self.card_tx.set_value("Transmitting")
                self.card_tx.value_label.setStyleSheet("font-size: 24px; color: #4caf50; font-weight: 700;")
            else:
                self.card_tx.set_value("Inactive")
                self.card_tx.value_label.setStyleSheet("font-size: 24px; color: #888; font-weight: 700;")

            # RF metrics
            self.card_freq.set_value(f"{status.frequency/1e6:.3f}")
            self.card_symbol.set_value(f"{status.symbol_rate/1e6:.2f}")
            self.card_bitrate.set_value(f"{status.pipeline.bitrate/1000:.0f}" if status.pipeline else "---")

            # Gain — read from flowgraph config
            config = self.engine.flowgraph.config
            gain = config.get("tx_gain_vga", 0)
            amp = config.get("tx_gain_amp", False)
            amp_str = "+14dB AMP" if amp else ""
            self.card_gain.set_value(f"{gain:.0f} dB {amp_str}")

            # Uptime in console
            uptime = status.uptime_sec
            if uptime > 0:
                mins = int(uptime // 60)
                secs = int(uptime % 60)
                self.console.setText(
                    f"System running for {mins}m {secs}s. "
                    f"{'TX active' if status.tx_active else 'TX idle'}. "
                    f"{'Pipeline active' if status.pipeline and status.pipeline.running else 'Pipeline stopped'}. "
                    f"Errors: {status.error_count}"
                )

        except Exception as e:
            pass  # Silently handle disconnected state
