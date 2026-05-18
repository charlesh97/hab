"""DVBS-2 TX Tab — cinematic video transmission controls."""

import os
from datetime import datetime

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QLineEdit, QPlainTextEdit, QMessageBox, QGroupBox,
    QFormLayout, QFileDialog, QSplitter, QCheckBox, QSlider,
)
from hab_engine.widgets import GlassCard, PrimaryButton, MetricTile, Divider

try:
    import pyqtgraph as pg
    import numpy as np
    PYQTGRAPH_AVAILABLE = True
except ImportError:
    PYQTGRAPH_AVAILABLE = False


class DVBS2TXTab(QWidget):
    """DVBS-2 video transmission tab with cinematic styling."""

    debug_message = Signal(str, str)

    def __init__(self, connection_tab, engine=None, parent=None) -> None:
        super().__init__(parent)
        self.connection_tab = connection_tab
        self.engine = engine
        self.selected_file = None
        self.tsfifo_path = "/tmp/tsfifo"
        self._current_spectrum = None

        self.debug_message.connect(self._append_debug)

        if self.engine:
            self.engine.set_spectrum_callback(self._on_engine_spectrum)
            self.engine.set_pipeline_debug_callback(self._on_pipeline_debug)

        self._setup_ui()

    def _on_engine_spectrum(self, frame):
        self._current_spectrum = frame

    def _on_pipeline_debug(self, name: str, msg: str):
        self.debug_message.emit(name, msg)

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(16)

        # Header
        header = QLabel("DVBS-2 Transmitter")
        header.setStyleSheet("""
            font-size: 18px; font-weight: 700;
            color: rgba(255, 255, 255, 0.87); letter-spacing: -0.3px;
        """)
        layout.addWidget(header)

        # ── Input File Row ──
        file_card = GlassCard()
        file_row = QHBoxLayout(file_card)
        file_row.setSpacing(12)

        file_label = QLabel("INPUT FILE")
        file_label.setStyleSheet("""
            font-size: 10px; font-weight: 700;
            color: rgba(255, 255, 255, 0.40); letter-spacing: 1.5px;
        """)
        file_row.addWidget(file_label)

        self.file_path_display = QLineEdit()
        self.file_path_display.setReadOnly(True)
        self.file_path_display.setPlaceholderText("No file selected...")
        file_row.addWidget(self.file_path_display, 1)

        self.btn_browse = QPushButton("Browse")
        file_row.addWidget(self.btn_browse)
        layout.addWidget(file_card)

        # ── Pipeline + TX Controls ──
        controls_layout = QHBoxLayout()
        controls_layout.setSpacing(16)

        # Pipeline section
        pipeline_card = GlassCard()
        pipeline_inner = QVBoxLayout(pipeline_card)
        pipeline_inner.setSpacing(8)

        pipe_header = QLabel("PIPELINE")
        pipe_header.setStyleSheet("""
            font-size: 10px; font-weight: 700;
            color: rgba(255, 255, 255, 0.40); letter-spacing: 1.5px;
        """)
        pipeline_inner.addWidget(pipe_header)

        pipe_buttons = QHBoxLayout()
        self.btn_start_pipe = PrimaryButton("▶ Pipeline")
        self.btn_stop_pipe = QPushButton("■ Stop")
        self.btn_stop_pipe.setEnabled(False)
        pipe_buttons.addWidget(self.btn_start_pipe)
        pipe_buttons.addWidget(self.btn_stop_pipe)
        pipeline_inner.addLayout(pipe_buttons)

        self.pipe_status = QLabel("Status: Stopped")
        self.pipe_status.setStyleSheet("""
            font-size: 11px; color: rgba(255, 255, 255, 0.50);
            font-family: 'JetBrains Mono', 'SF Mono', monospace;
        """)
        pipeline_inner.addWidget(self.pipe_status)
        controls_layout.addWidget(pipeline_card, 1)

        # TX section
        tx_card = GlassCard()
        tx_inner = QVBoxLayout(tx_card)
        tx_inner.setSpacing(8)

        tx_header = QLabel("TRANSMISSION")
        tx_header.setStyleSheet("""
            font-size: 10px; font-weight: 700;
            color: rgba(255, 255, 255, 0.40); letter-spacing: 1.5px;
        """)
        tx_inner.addWidget(tx_header)

        tx_params = QHBoxLayout()
        tx_params.addWidget(QLabel("VGA:"))
        self.tx_gain_slider = QSlider(Qt.Horizontal)
        self.tx_gain_slider.setMinimum(0)
        self.tx_gain_slider.setMaximum(47)
        self.tx_gain_slider.setValue(16)
        self.tx_gain_slider.setTickPosition(QSlider.TicksBelow)
        self.tx_gain_slider.setTickInterval(5)
        self.tx_gain_label = QLabel("16 dB")
        self.tx_gain_slider.valueChanged.connect(
            lambda v: self.tx_gain_label.setText(f"{v} dB")
        )
        tx_params.addWidget(self.tx_gain_slider)
        tx_params.addWidget(self.tx_gain_label)
        self.tx_amp = QCheckBox("AMP")
        tx_params.addWidget(self.tx_amp)
        tx_inner.addLayout(tx_params)

        tx_buttons = QHBoxLayout()
        self.btn_start_tx = PrimaryButton("▶ Start TX")
        self.btn_stop_tx = QPushButton("■ Stop TX")
        self.btn_stop_tx.setEnabled(False)
        tx_buttons.addWidget(self.btn_start_tx)
        tx_buttons.addWidget(self.btn_stop_tx)
        tx_inner.addLayout(tx_buttons)

        self.tx_status = QLabel("Status: Stopped")
        self.tx_status.setStyleSheet("""
            font-size: 11px; color: rgba(255, 255, 255, 0.50);
            font-family: 'JetBrains Mono', 'SF Mono', monospace;
        """)
        tx_inner.addWidget(self.tx_status)
        controls_layout.addWidget(tx_card, 1)

        layout.addLayout(controls_layout)

        # ── Debug Terminals ──
        debug_card = GlassCard()
        debug_inner = QVBoxLayout(debug_card)
        debug_inner.setSpacing(8)

        debug_header = QLabel("PIPELINE OUTPUT")
        debug_header.setStyleSheet("""
            font-size: 10px; font-weight: 700;
            color: rgba(255, 255, 255, 0.40); letter-spacing: 1.5px;
        """)
        debug_inner.addWidget(debug_header)

        debug_split = QHBoxLayout()
        debug_split.setSpacing(12)

        # ffmpeg
        ffmpeg_box = QVBoxLayout()
        ffmpeg_label = QLabel("ffmpeg")
        ffmpeg_label.setStyleSheet("""
            font-size: 11px; font-weight: 600;
            color: rgba(255, 255, 255, 0.60);
        """)
        ffmpeg_box.addWidget(ffmpeg_label)
        self.debug_ffmpeg = QPlainTextEdit()
        self.debug_ffmpeg.setReadOnly(True)
        self.debug_ffmpeg.setPlaceholderText("ffmpeg output...")
        self.debug_ffmpeg.setMaximumBlockCount(200)
        ffmpeg_box.addWidget(self.debug_ffmpeg)
        debug_split.addLayout(ffmpeg_box)

        # tsp
        tsp_box = QVBoxLayout()
        tsp_label = QLabel("tsp")
        tsp_label.setStyleSheet("""
            font-size: 11px; font-weight: 600;
            color: rgba(255, 255, 255, 0.60);
        """)
        tsp_box.addWidget(tsp_label)
        self.debug_tsp = QPlainTextEdit()
        self.debug_tsp.setReadOnly(True)
        self.debug_tsp.setPlaceholderText("tsp output...")
        self.debug_tsp.setMaximumBlockCount(200)
        tsp_box.addWidget(self.debug_tsp)
        debug_split.addLayout(tsp_box)

        debug_inner.addLayout(debug_split)
        layout.addWidget(debug_card)

        # ── Spectrum ──
        if PYQTGRAPH_AVAILABLE:
            pg.setConfigOption('background', (10, 10, 11))
            pg.setConfigOption('foreground', 'w')

            spectrum_card = GlassCard()
            spec_layout = QVBoxLayout(spectrum_card)
            spec_layout.setSpacing(8)

            spec_header = QLabel("SPECTRUM")
            spec_header.setStyleSheet("""
                font-size: 10px; font-weight: 700;
                color: rgba(255, 255, 255, 0.40); letter-spacing: 1.5px;
            """)
            spec_layout.addWidget(spec_header)

            self.spectrum_plot = pg.PlotWidget()
            self.spectrum_plot.setLabel('left', 'Power', units='dB')
            self.spectrum_plot.setLabel('bottom', 'Frequency', units='Hz')
            self.spectrum_plot.showGrid(x=True, y=True, alpha=0.3)
            self.spectrum_plot.setMinimumHeight(180)
            self.spectrum_curve = self.spectrum_plot.plot(
                pen=pg.mkPen(color=(249, 115, 22), width=1.5)
            )
            spec_layout.addWidget(self.spectrum_plot, 1)

            # Waterfall
            self.waterfall = pg.ImageView()
            self.waterfall.setMinimumHeight(180)
            self.waterfall.view.invertY(True)
            spec_layout.addWidget(self.waterfall, 1)

            self.waterfall_data = np.zeros((200, 1024))
            self.waterfall_row = 0
            layout.addWidget(spectrum_card, 1)
        else:
            no_graph = QLabel("PyQtGraph not installed")
            no_graph.setAlignment(Qt.AlignCenter)
            no_graph.setStyleSheet("background: rgba(255,255,255,0.02); border-radius: 16px; padding: 40px; color: rgba(255,255,255,0.4);")
            no_graph.setMinimumHeight(200)
            layout.addWidget(no_graph)

        layout.addStretch()

        # ── Connect signals ──
        self.btn_browse.clicked.connect(self._browse)
        self.btn_start_pipe.clicked.connect(self._start_pipeline)
        self.btn_stop_pipe.clicked.connect(self._stop_pipeline)
        self.btn_start_tx.clicked.connect(self._start_tx)
        self.btn_stop_tx.clicked.connect(self._stop_tx)

        self.spectrum_timer = QTimer()
        self.spectrum_timer.timeout.connect(self._update_spectrum)
        self.spectrum_timer.setInterval(50)

    def _append_debug(self, name: str, msg: str):
        ts = datetime.now().strftime("%H:%M:%S")
        formatted = f"[{ts}] {msg}"
        if name == "ffmpeg":
            self.debug_ffmpeg.appendPlainText(formatted)
        elif name == "tsp":
            self.debug_tsp.appendPlainText(formatted)

    def _log(self, msg: str):
        self._append_debug("ffmpeg", msg)
        self._append_debug("tsp", msg)

    def _browse(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select MP4 File", "", "MP4 Files (*.mp4);;All Files (*)"
        )
        if path:
            self.selected_file = path
            self.file_path_display.setText(path)
            self._log(f"File: {path}")

    def _start_pipeline(self):
        if not self.selected_file:
            QMessageBox.warning(self, "No File", "Select an MP4 file first.")
            return
        if not os.path.exists(self.selected_file):
            QMessageBox.warning(self, "Not Found", "File does not exist.")
            return
        if self.engine and self.engine.start_pipeline(self.selected_file):
            self.btn_start_pipe.setEnabled(False)
            self.btn_stop_pipe.setEnabled(True)
            self.pipe_status.setText("Status: Running • encoding")
            self.pipe_status.setStyleSheet("font-size: 11px; color: #10b981; font-family: 'JetBrains Mono', 'SF Mono', monospace;")
            self._log("Pipeline started")
        else:
            QMessageBox.critical(self, "Error", "Failed to start pipeline.")

    def _stop_pipeline(self):
        if self.engine:
            self.engine.stop_pipeline()
        self.btn_start_pipe.setEnabled(True)
        self.btn_stop_pipe.setEnabled(False)
        self.pipe_status.setText("Status: Stopped")
        self.pipe_status.setStyleSheet("font-size: 11px; color: rgba(255, 255, 255, 0.50); font-family: 'JetBrains Mono', 'SF Mono', monospace;")
        self._log("Pipeline stopped")

    def _start_tx(self):
        if not self.connection_tab.is_device_connected():
            QMessageBox.warning(self, "No Device", "Connect a HackRF first.")
            return
        device = self.connection_tab.get_device_args()
        if not device:
            QMessageBox.warning(self, "No Device", "Could not get device info.")
            return

        params = self.connection_tab.get_connection_params()
        freq = params["frequency"]

        if self.engine:
            self.engine.update_params(frequency=freq, symbol_rate=1e6)
            self.engine.flowgraph.update_config(
                center_freq=freq,
                tx_gain_vga=float(self.tx_gain_slider.value()),
                tx_gain_amp=self.tx_amp.isChecked(),
            )
            dev = self.connection_tab.selected_device()
            args = f"driver=hackrf,serial={dict(dev).get('serial', '')}" if dev else "driver=hackrf"

            if self.engine.start_tx(device_args=args):
                self._log(f"TX: {freq/1e6:.3f} MHz, VGA={self.tx_gain_slider.value()} dB")
                self.btn_start_tx.setEnabled(False)
                self.btn_stop_tx.setEnabled(True)
                self.tx_status.setText("Status: Transmitting")
                self.tx_status.setStyleSheet("font-size: 11px; color: #f97316; font-family: 'JetBrains Mono', 'SF Mono', monospace;")
                self.spectrum_timer.start()
                return
        QMessageBox.critical(self, "TX Error", "Failed to start transmission.")

    def _stop_tx(self):
        if self.engine:
            self.engine.stop_tx()
        self.spectrum_timer.stop()
        self.btn_start_tx.setEnabled(True)
        self.btn_stop_tx.setEnabled(False)
        self.tx_status.setText("Status: Stopped")
        self.tx_status.setStyleSheet("font-size: 11px; color: rgba(255, 255, 255, 0.50); font-family: 'JetBrains Mono', 'SF Mono', monospace;")
        self._log("TX stopped")

    def _update_spectrum(self):
        if not PYQTGRAPH_AVAILABLE:
            return
        frame = self._current_spectrum
        if frame is None:
            return
        try:
            freq = np.array(frame.frequencies)
            power = np.array(frame.power_db)
            self.spectrum_curve.setData(freq, power)
            if self.waterfall_data.shape[1] >= len(power):
                self.waterfall_data[self.waterfall_row, :len(power)] = power[:self.waterfall_data.shape[1]]
                self.waterfall_row = (self.waterfall_row + 1) % 200
                self.waterfall.setImage(self.waterfall_data, autoLevels=True)
        except Exception:
            pass

    def cleanup(self):
        self._stop_tx()
        self._stop_pipeline()
