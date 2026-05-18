"""Dashboard Tab — cinematic mission overview with streaming metrics."""

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QPushButton, QLabel, QGroupBox, QFormLayout, QFrame,
)
from hab_engine.widgets import MetricTile, StatusPill, Divider, GlassCard


class DashboardTab(QWidget):
    """Dashboard tab showing overall system status — cinematic design."""

    def __init__(self, engine=None, parent=None) -> None:
        super().__init__(parent)
        self.engine = engine
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(16)

        # Header
        header = QLabel("Mission Dashboard")
        header.setStyleSheet("""
            font-size: 18px;
            font-weight: 700;
            color: rgba(255, 255, 255, 0.87);
            letter-spacing: -0.3px;
        """)
        layout.addWidget(header)

        # ── Status Cards Grid ──
        grid = QGridLayout()
        grid.setSpacing(12)

        self.card_engine = MetricTile("Engine", "Idle", "", accent_color="rgba(255,255,255,0.6)")
        self.card_device = MetricTile("HackRF", "Disconnected", "", accent_color="#f43f5e")
        self.card_pipeline = MetricTile("Pipeline", "Stopped", "", accent_color="rgba(255,255,255,0.6)")
        self.card_tx = MetricTile("TX", "Inactive", "", accent_color="rgba(255,255,255,0.6)")
        grid.addWidget(self.card_engine, 0, 0)
        grid.addWidget(self.card_device, 0, 1)
        grid.addWidget(self.card_pipeline, 0, 2)
        grid.addWidget(self.card_tx, 0, 3)

        # Row 2: RF metrics
        self.card_freq = MetricTile("Frequency", "---", "MHz", accent_color="#0284c7")
        self.card_symbol = MetricTile("Symbol Rate", "---", "Msps", accent_color="#0284c7")
        self.card_gain = MetricTile("TX Gain", "---", "dB", accent_color="#0284c7")
        self.card_bitrate = MetricTile("Bitrate", "---", "kbps", accent_color="#0284c7")
        grid.addWidget(self.card_freq, 1, 0)
        grid.addWidget(self.card_symbol, 1, 1)
        grid.addWidget(self.card_gain, 1, 2)
        grid.addWidget(self.card_bitrate, 1, 3)

        layout.addLayout(grid)
        layout.addWidget(Divider())

        # ── System Info ──
        info_card = GlassCard()
        info_layout = QVBoxLayout(info_card)
        info_layout.setSpacing(8)

        info_header = QLabel("SYSTEM")
        info_header.setStyleSheet("""
            font-size: 10px;
            font-weight: 700;
            color: rgba(255, 255, 255, 0.40);
            letter-spacing: 1.5px;
        """)
        info_layout.addWidget(info_header)

        self.info_gnuradio = QLabel("GNU Radio: checking...")
        self.info_ffmpeg = QLabel("ffmpeg: checking...")
        self.info_tsp = QLabel("tsp: checking...")
        self.info_hackrf = QLabel("HackRF: checking...")
        for lbl in [self.info_gnuradio, self.info_ffmpeg, self.info_tsp, self.info_hackrf]:
            lbl.setStyleSheet("""
                font-size: 12px;
                font-family: 'JetBrains Mono', 'SF Mono', monospace;
                color: rgba(255, 255, 255, 0.60);
                padding: 2px 0;
            """)
            info_layout.addWidget(lbl)

        layout.addWidget(info_card)

        # ── Status Console ──
        console_card = GlassCard()
        console_layout = QVBoxLayout(console_card)
        console_layout.setSpacing(8)

        console_header = QLabel("STATUS")
        console_header.setStyleSheet("""
            font-size: 10px;
            font-weight: 700;
            color: rgba(255, 255, 255, 0.40);
            letter-spacing: 1.5px;
        """)
        console_layout.addWidget(console_header)

        self.console = QLabel("System ready. Connect HackRF to begin.")
        self.console.setWordWrap(True)
        self.console.setStyleSheet("""
            font-size: 12px;
            color: rgba(255, 255, 255, 0.50);
            padding: 4px 0;
        """)
        console_layout.addWidget(self.console)

        layout.addWidget(console_card)
        layout.addStretch()

        # Poll system info
        self._poll_system_info()
        self._update_timer = QTimer()
        self._update_timer.timeout.connect(self._update_status)
        self._update_timer.start(2000)

    def _poll_system_info(self):
        """Check system tools."""
        import shutil
        import subprocess

        def set_info(lbl, ok: bool, text: str):
            color = "#10b981" if ok else "#f43f5e"
            lbl.setText(f"<span style='color: {color}'>●</span> {text}")
            lbl.setTextFormat(Qt.RichText)

        set_info(self.info_gnuradio, True, "GNU Radio 3.10.12")
        set_info(self.info_ffmpeg, bool(shutil.which("ffmpeg")),
                 "ffmpeg" if shutil.which("ffmpeg") else "ffmpeg — not found")
        set_info(self.info_tsp, bool(shutil.which("tsp")),
                 "tsp (tsduck)" if shutil.which("tsp") else "tsp — not found")

        if shutil.which("hackrf_info"):
            try:
                result = subprocess.run(["hackrf_info"], capture_output=True, text=True, timeout=3)
                count = result.stdout.count("Found HackRF")
                set_info(self.info_hackrf, count > 0, f"{count} HackRF device(s)")
            except Exception:
                set_info(self.info_hackrf, False, "Error scanning")
        else:
            set_info(self.info_hackrf, False, "hackrf_info not found")

    def _update_status(self):
        """Update status cards from engine."""
        if not self.engine:
            return
        try:
            status = self.engine.status

            # Engine
            if status.running or status.tx_active:
                self.card_engine.set_value("Active")
                self.card_engine.value_widget.setStyleSheet("font-size: 22px; font-weight: 700; font-family: 'JetBrains Mono', 'SF Mono', monospace; color: #10b981;")
            else:
                self.card_engine.set_value("Idle")
                self.card_engine.value_widget.setStyleSheet("font-size: 22px; font-weight: 700; font-family: 'JetBrains Mono', 'SF Mono', monospace; color: rgba(255,255,255,0.6);")

            # Device
            if status.device_connected:
                short_serial = status.device_serial[-8:] if len(status.device_serial) > 8 else status.device_serial
                self.card_device.set_value(short_serial)
                self.card_device.value_widget.setStyleSheet("font-size: 18px; font-weight: 700; font-family: 'JetBrains Mono', 'SF Mono', monospace; color: #10b981;")
            else:
                self.card_device.set_value("Disconnected")
                self.card_device.value_widget.setStyleSheet("font-size: 22px; font-weight: 700; font-family: 'JetBrains Mono', 'SF Mono', monospace; color: #f43f5e;")

            # Pipeline
            if status.pipeline and status.pipeline.running:
                self.card_pipeline.set_value("Running")
                self.card_pipeline.value_widget.setStyleSheet("font-size: 22px; font-weight: 700; font-family: 'JetBrains Mono', 'SF Mono', monospace; color: #10b981;")
            else:
                self.card_pipeline.set_value("Stopped")
                self.card_pipeline.value_widget.setStyleSheet("font-size: 22px; font-weight: 700; font-family: 'JetBrains Mono', 'SF Mono', monospace; color: rgba(255,255,255,0.6);")

            # TX
            if status.tx_active:
                self.card_tx.set_value("Transmitting")
                self.card_tx.value_widget.setStyleSheet("font-size: 22px; font-weight: 700; font-family: 'JetBrains Mono', 'SF Mono', monospace; color: #f97316;")
            else:
                self.card_tx.set_value("Inactive")
                self.card_tx.value_widget.setStyleSheet("font-size: 22px; font-weight: 700; font-family: 'JetBrains Mono', 'SF Mono', monospace; color: rgba(255,255,255,0.6);")

            # RF metrics
            self.card_freq.set_value(f"{status.frequency/1e6:.3f}")
            self.card_symbol.set_value(f"{status.symbol_rate/1e6:.2f}")
            self.card_bitrate.set_value(f"{status.pipeline.bitrate/1000:.0f}" if status.pipeline else "---")

            config = self.engine.flowgraph.config
            gain = config.get("tx_gain_vga", 0)
            amp = config.get("tx_gain_amp", False)
            self.card_gain.set_value(f"{gain:.0f}{' +AMP' if amp else ''}")

            # Console
            uptime = status.uptime_sec
            if uptime > 0:
                mins = int(uptime // 60)
                secs = int(uptime % 60)
                self.console.setText(
                    f"System running for {mins}m {secs}s · "
                    f"{'TX active' if status.tx_active else 'TX idle'} · "
                    f"{'Pipeline active' if status.pipeline and status.pipeline.running else 'Pipeline stopped'}"
                )
        except Exception:
            pass
