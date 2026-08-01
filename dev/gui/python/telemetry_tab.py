"""Telemetry Tab — spectrum analyzer and packet stream with cinematic styling."""

from datetime import datetime
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QPlainTextEdit, QGroupBox, QFormLayout, QLineEdit,
    QCheckBox, QSplitter,
)
from hab_engine.widgets import GlassCard, PrimaryButton
import numpy as np

try:
    import pyqtgraph as pg
    PYQTGRAPH_AVAILABLE = True
except ImportError:
    PYQTGRAPH_AVAILABLE = False


class TelemetryTab(QWidget):
    def __init__(self, engine=None, parent=None) -> None:
        super().__init__(parent)
        self.engine = engine
        self._engine_spectrum = None
        self.telemetry_rx = None
        self.spectrum_data = None
        self.max_hold_data = None

        if self.engine:
            self.engine.set_spectrum_callback(self._on_engine_spectrum)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(16)

        # Header
        header = QLabel("Telemetry & Spectrum")
        header.setStyleSheet("""
            font-size: 18px; font-weight: 700;
            color: rgba(255, 255, 255, 0.87); letter-spacing: -0.3px;
        """)
        layout.addWidget(header)

        # ── Spectrum Card ──
        spectrum_card = GlassCard()
        spec_layout = QVBoxLayout(spectrum_card)
        spec_layout.setSpacing(8)

        spec_header = QLabel("SPECTRUM ANALYZER")
        spec_header.setStyleSheet("""
            font-size: 10px; font-weight: 700;
            color: rgba(255, 255, 255, 0.40); letter-spacing: 1.5px;
        """)
        spec_layout.addWidget(spec_header)

        # Controls
        ctrl_row = QHBoxLayout()
        ctrl_row.setSpacing(16)

        # RBW
        rbw_layout = QHBoxLayout()
        rbw_layout.addWidget(QLabel("RBW:"))
        self.input_rbw = QLineEdit("10")
        self.input_rbw.setMaximumWidth(80)
        rbw_layout.addWidget(self.input_rbw)
        rbw_layout.addWidget(QLabel("kHz"))
        ctrl_row.addLayout(rbw_layout)

        # VBW
        vbw_layout = QHBoxLayout()
        vbw_layout.addWidget(QLabel("VBW:"))
        self.input_vbw = QLineEdit("10")
        self.input_vbw.setMaximumWidth(80)
        vbw_layout.addWidget(self.input_vbw)
        vbw_layout.addWidget(QLabel("kHz"))
        ctrl_row.addLayout(vbw_layout)

        self.chk_max_hold = QCheckBox("Max Hold")
        ctrl_row.addWidget(self.chk_max_hold)
        self.btn_clear = QPushButton("Clear")
        ctrl_row.addWidget(self.btn_clear)
        ctrl_row.addStretch()

        # RX buttons
        self.btn_start_rx = PrimaryButton("▶ Start RX")
        self.btn_stop_rx = QPushButton("■ Stop RX")
        self.btn_stop_rx.setEnabled(False)
        ctrl_row.addWidget(self.btn_start_rx)
        ctrl_row.addWidget(self.btn_stop_rx)

        spec_layout.addLayout(ctrl_row)

        # Plot
        if PYQTGRAPH_AVAILABLE:
            pg.setConfigOption('background', (10, 10, 11))
            pg.setConfigOption('foreground', 'w')
            self.spectrum_plot = pg.PlotWidget()
            self.spectrum_plot.setLabel('left', 'Power', units='dB')
            self.spectrum_plot.setLabel('bottom', 'Frequency', units='Hz')
            self.spectrum_plot.showGrid(x=True, y=True, alpha=0.3)
            self.spectrum_plot.setMinimumHeight(300)
            self.spectrum_curve = self.spectrum_plot.plot(
                pen=pg.mkPen(color=(2, 132, 199), width=1.5)
            )
            spec_layout.addWidget(self.spectrum_plot)
        else:
            no_graph = QLabel("PyQtGraph not installed")
            no_graph.setAlignment(Qt.AlignCenter)
            no_graph.setStyleSheet("background: rgba(255,255,255,0.02); border-radius: 16px; padding: 40px;")
            no_graph.setMinimumHeight(300)
            spec_layout.addWidget(no_graph)

        layout.addWidget(spectrum_card, 1)

        # ── Telemetry Terminal ──
        terminal_card = GlassCard()
        term_layout = QVBoxLayout(terminal_card)
        term_layout.setSpacing(8)

        term_header = QLabel("TELEMETRY STREAM")
        term_header.setStyleSheet("""
            font-size: 10px; font-weight: 700;
            color: rgba(255, 255, 255, 0.40); letter-spacing: 1.5px;
        """)
        term_layout.addWidget(term_header)

        self.terminal = QPlainTextEdit()
        self.terminal.setReadOnly(True)
        self.terminal.setPlaceholderText("Received telemetry will appear here...")
        self.terminal.setMaximumBlockCount(500)
        self.terminal.setMinimumHeight(120)
        term_layout.addWidget(self.terminal)

        layout.addWidget(terminal_card)

        # ── Signals ──
        self.btn_start_rx.clicked.connect(self._start_rx)
        self.btn_stop_rx.clicked.connect(self._stop_rx)
        self.btn_clear.clicked.connect(self._clear_spectrum)

        self.spectrum_timer = QTimer()
        self.spectrum_timer.timeout.connect(self._update_spectrum)
        self.spectrum_timer.setInterval(50)

    def _on_engine_spectrum(self, frame):
        self._engine_spectrum = (np.array(frame.frequencies), np.array(frame.power_db))

    def log(self, msg: str):
        ts = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        self.terminal.appendPlainText(f"[{ts}] {msg}")

    def _start_rx(self):
        try:
            from telemetry_rx import TelemetryReceiverInterface
            if self.telemetry_rx is None:
                self.telemetry_rx = TelemetryReceiverInterface(
                    self._on_packet, self._on_rx_spectrum
                )
            self.telemetry_rx.start()
            self.spectrum_timer.start()
            self.log("RX started")
            self.btn_start_rx.setEnabled(False)
            self.btn_stop_rx.setEnabled(True)
        except Exception as e:
            self.log(f"Error: {e}")

    def _stop_rx(self):
        if self.telemetry_rx:
            self.telemetry_rx.stop()
        self.spectrum_timer.stop()
        self.log("RX stopped")
        self.btn_start_rx.setEnabled(True)
        self.btn_stop_rx.setEnabled(False)

    def _on_packet(self, data: bytes):
        self.log(f"RX: {data.hex()}")

    def _on_rx_spectrum(self, freq, power):
        if PYQTGRAPH_AVAILABLE:
            self.spectrum_data = (freq, power)
            if self.chk_max_hold.isChecked():
                if self.max_hold_data is None:
                    self.max_hold_data = power.copy()
                else:
                    self.max_hold_data = np.maximum(self.max_hold_data, power)

    def _update_spectrum(self):
        if not PYQTGRAPH_AVAILABLE:
            return
        spectrum = self._engine_spectrum if self._engine_spectrum is not None else self.spectrum_data
        if spectrum is None:
            return
        freq, power = spectrum

        if self.chk_max_hold.isChecked() and self.max_hold_data is not None:
            display = self.max_hold_data
        else:
            display = power
        self.spectrum_curve.setData(freq, display)

    def _clear_spectrum(self):
        self.max_hold_data = None
        if PYQTGRAPH_AVAILABLE:
            self.spectrum_curve.setData([], [])
            self.spectrum_data = None
            self._engine_spectrum = None
        self.log("Spectrum cleared")
