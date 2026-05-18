import os
import threading
import time
from datetime import datetime

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QMessageBox,
    QGroupBox,
    QFormLayout,
    QFileDialog,
    QSplitter,
    QCheckBox,
    QSlider,
)

try:
    import pyqtgraph as pg
    import numpy as np
    PYQTGRAPH_AVAILABLE = True
except ImportError:
    PYQTGRAPH_AVAILABLE = False


class DVBS2TXTab(QWidget):
    """DVBS-2 video transmission tab with HabEngine integration."""

    # Signal for thread-safe debug output
    debug_message = Signal(str, str)

    def __init__(self, connection_tab, engine=None, parent=None) -> None:
        super().__init__(parent)
        self.connection_tab = connection_tab
        self.engine = engine
        self.selected_file = None
        self.tsfifo_path = "/tmp/tsfifo"

        # Debug output signal connection
        self.debug_message.connect(self._append_debug_to_terminal)

        # Setup spectrum callback from engine
        if self.engine:
            self.engine.set_spectrum_callback(self._on_engine_spectrum)
            self.engine.set_pipeline_debug_callback(self._on_pipeline_debug)

        # Spectrum display state
        self._current_spectrum = None

        self._setup_ui()

    def _on_engine_spectrum(self, frame):
        """Receive spectrum data from engine (called from background thread)."""
        self._current_spectrum = frame

    def _on_pipeline_debug(self, process_name: str, message: str):
        """Receive pipeline debug output from engine."""
        self.debug_message.emit(process_name, message)

    def _setup_ui(self):
        """Build the UI."""
        main_layout = QVBoxLayout(self)

        # Header
        header = QLabel("DVBS-2 Transmitter")
        header.setAlignment(Qt.AlignLeft)
        header.setStyleSheet("font-size: 18px; font-weight: 600;")
        main_layout.addWidget(header)

        # ── Input File Section ──
        file_group = QGroupBox("Input File")
        file_layout = QFormLayout()
        file_input_layout = QHBoxLayout()
        self.file_path_display = QLineEdit()
        self.file_path_display.setReadOnly(True)
        self.file_path_display.setPlaceholderText("No file selected")
        self.btn_browse_file = QPushButton("Browse...")
        file_input_layout.addWidget(self.file_path_display)
        file_input_layout.addWidget(self.btn_browse_file)
        file_layout.addRow("MP4 File:", file_input_layout)
        file_group.setLayout(file_layout)
        main_layout.addWidget(file_group)

        # ── Pipeline Control Section ──
        pipeline_group = QGroupBox("Pipeline Control")
        pipeline_layout = QVBoxLayout()
        pipeline_btn_layout = QHBoxLayout()
        self.btn_start_pipeline = QPushButton("Start Pipeline")
        self.btn_stop_pipeline = QPushButton("Stop Pipeline")
        self.btn_stop_pipeline.setEnabled(False)
        self.pipeline_status_label = QLabel("Status: Stopped")
        self.pipeline_status_label.setStyleSheet("color: red; font-weight: 600;")
        pipeline_btn_layout.addWidget(self.btn_start_pipeline)
        pipeline_btn_layout.addWidget(self.btn_stop_pipeline)
        pipeline_btn_layout.addStretch()
        pipeline_btn_layout.addWidget(self.pipeline_status_label)
        pipeline_layout.addLayout(pipeline_btn_layout)

        # Debug terminals (side by side)
        debug_terminals_layout = QHBoxLayout()
        ffmpeg_widget = QWidget()
        ffmpeg_layout = QVBoxLayout(ffmpeg_widget)
        ffmpeg_layout.setContentsMargins(5, 5, 5, 5)
        ffmpeg_label = QLabel("ffmpeg Output:")
        ffmpeg_label.setStyleSheet("font-weight: 600;")
        self.debug_terminal_ffmpeg = QPlainTextEdit()
        self.debug_terminal_ffmpeg.setReadOnly(True)
        self.debug_terminal_ffmpeg.setPlaceholderText("ffmpeg output will appear here...")
        self.debug_terminal_ffmpeg.setMaximumBlockCount(500)
        ffmpeg_layout.addWidget(ffmpeg_label)
        ffmpeg_layout.addWidget(self.debug_terminal_ffmpeg)

        tsp_widget = QWidget()
        tsp_layout = QVBoxLayout(tsp_widget)
        tsp_layout.setContentsMargins(5, 5, 5, 5)
        tsp_label = QLabel("tsp Output:")
        tsp_label.setStyleSheet("font-weight: 600;")
        self.debug_terminal_tsp = QPlainTextEdit()
        self.debug_terminal_tsp.setReadOnly(True)
        self.debug_terminal_tsp.setPlaceholderText("tsp output will appear here...")
        self.debug_terminal_tsp.setMaximumBlockCount(500)
        tsp_layout.addWidget(tsp_label)
        tsp_layout.addWidget(self.debug_terminal_tsp)

        debug_terminals_layout.addWidget(ffmpeg_widget)
        debug_terminals_layout.addWidget(tsp_widget)
        pipeline_layout.addLayout(debug_terminals_layout)
        pipeline_group.setLayout(pipeline_layout)
        main_layout.addWidget(pipeline_group)

        # ── Transmission Control Section ──
        tx_group = QGroupBox("Transmission Control")
        tx_layout = QVBoxLayout()

        # TX params row
        tx_params_layout = QHBoxLayout()
        tx_params_layout.addWidget(QLabel("VGA Gain:"))
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
        tx_params_layout.addWidget(self.tx_gain_slider)
        tx_params_layout.addWidget(self.tx_gain_label)

        self.tx_amp_check = QCheckBox("AMP (14dB)")
        self.tx_amp_check.setChecked(False)
        tx_params_layout.addWidget(self.tx_amp_check)
        tx_params_layout.addStretch()
        tx_layout.addLayout(tx_params_layout)

        tx_btn_layout = QHBoxLayout()
        self.btn_start_tx = QPushButton("Start TX")
        self.btn_stop_tx = QPushButton("Stop TX")
        self.btn_stop_tx.setEnabled(False)
        self.tx_status_label = QLabel("Status: Stopped")
        self.tx_status_label.setStyleSheet("color: red; font-weight: 600;")
        tx_btn_layout.addWidget(self.btn_start_tx)
        tx_btn_layout.addWidget(self.btn_stop_tx)
        tx_btn_layout.addStretch()
        tx_btn_layout.addWidget(self.tx_status_label)
        tx_layout.addLayout(tx_btn_layout)
        tx_group.setLayout(tx_layout)
        main_layout.addWidget(tx_group)

        # ── Spectrum Visualization ──
        splitter = QSplitter(Qt.Vertical)
        spectrum_widget = QWidget()
        spectrum_layout = QVBoxLayout(spectrum_widget)
        spectrum_layout.setContentsMargins(0, 0, 0, 0)
        spectrum_header = QLabel("Spectrum Visualization")
        spectrum_header.setStyleSheet("font-weight: 600;")
        spectrum_layout.addWidget(spectrum_header)

        if PYQTGRAPH_AVAILABLE:
            pg.setConfigOption('background', (35, 35, 35))
            pg.setConfigOption('foreground', 'w')
            self.spectrum_plot = pg.PlotWidget()
            self.spectrum_plot.setLabel('left', 'Power', units='dB')
            self.spectrum_plot.setLabel('bottom', 'Frequency', units='Hz')
            self.spectrum_plot.showGrid(x=True, y=True, alpha=0.3)
            self.spectrum_plot.setMinimumHeight(150)
            self.spectrum_curve = self.spectrum_plot.plot(
                pen=pg.mkPen(color=(42, 130, 218), width=1)
            )
            spectrum_layout.addWidget(self.spectrum_plot)

            # Waterfall
            self.waterfall_plot = pg.ImageView()
            self.waterfall_plot.setMinimumHeight(200)
            self.waterfall_plot.view.invertY(True)
            spectrum_layout.addWidget(self.waterfall_plot)
            self.waterfall_data = np.zeros((200, 1024))
            self.waterfall_row_index = 0
        else:
            no_graph = QLabel("PyQtGraph not installed. pip install pyqtgraph")
            no_graph.setMinimumHeight(300)
            no_graph.setAlignment(Qt.AlignCenter)
            no_graph.setStyleSheet("background-color: #232323; color: white;")
            spectrum_layout.addWidget(no_graph)

        splitter.addWidget(spectrum_widget)
        splitter.setStretchFactor(0, 1)
        main_layout.addWidget(splitter)

        # ── Connect signals ──
        self.btn_browse_file.clicked.connect(self._browse_file)
        self.btn_start_pipeline.clicked.connect(self._start_pipeline)
        self.btn_stop_pipeline.clicked.connect(self._stop_pipeline)
        self.btn_start_tx.clicked.connect(self._start_tx)
        self.btn_stop_tx.clicked.connect(self._stop_tx)

        # Spectrum update timer (20 Hz)
        self.spectrum_timer = QTimer()
        self.spectrum_timer.timeout.connect(self._update_spectrum)
        self.spectrum_timer.setInterval(50)

    # ── Debug Output ──

    def _append_debug_to_terminal(self, process_name: str, message: str):
        """Append message to the appropriate debug terminal."""
        timestamp = datetime.now().strftime("%H:%M:%S")
        formatted = f"[{timestamp}] {message}"
        if process_name == "ffmpeg":
            self.debug_terminal_ffmpeg.appendPlainText(formatted)
        elif process_name == "tsp":
            self.debug_terminal_tsp.appendPlainText(formatted)
        print(formatted)

    def _log(self, message: str):
        """Log to both terminals."""
        self._append_debug_to_terminal("ffmpeg", message)
        self._append_debug_to_terminal("tsp", message)

    # ── File Selection ──

    def _browse_file(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Select MP4 File", "", "MP4 Files (*.mp4);;All Files (*)"
        )
        if file_path:
            self.selected_file = file_path
            self.file_path_display.setText(file_path)
            self._log(f"Selected file: {file_path}")

    # ── Pipeline Control ──

    def _start_pipeline(self):
        if not self.selected_file:
            QMessageBox.warning(self, "No File", "Select an MP4 file first.")
            return
        if not os.path.exists(self.selected_file):
            QMessageBox.warning(self, "Not Found", "File does not exist.")
            return

        if self.engine:
            success = self.engine.start_pipeline(self.selected_file)
            if success:
                self.btn_start_pipeline.setEnabled(False)
                self.btn_stop_pipeline.setEnabled(True)
                self.pipeline_status_label.setText("Status: Running")
                self.pipeline_status_label.setStyleSheet("color: green; font-weight: 600;")
                self._log("Pipeline started via HabEngine")
            else:
                QMessageBox.critical(self, "Error", "Failed to start pipeline.")
        else:
            QMessageBox.warning(self, "No Engine", "Engine not initialized.")

    def _stop_pipeline(self):
        if self.engine:
            self.engine.stop_pipeline()
        self.btn_start_pipeline.setEnabled(True)
        self.btn_stop_pipeline.setEnabled(False)
        self.pipeline_status_label.setText("Status: Stopped")
        self.pipeline_status_label.setStyleSheet("color: red; font-weight: 600;")
        self._log("Pipeline stopped")

    # ── TX Control ──

    def _start_tx(self):
        if not self.connection_tab.is_device_connected():
            QMessageBox.warning(self, "No Device", "Connect a HackRF first.")
            return

        device = self.connection_tab.get_device_args()
        if device is None:
            QMessageBox.warning(self, "No Device", "Could not get device info.")
            return

        params = self.connection_tab.get_connection_params()
        freq = params["frequency"]

        # Update engine params
        if self.engine:
            self.engine.update_params(
                frequency=freq,
                symbol_rate=1e6,
            )
            self.engine.flowgraph.update_config(
                center_freq=freq,
                tx_gain_vga=float(self.tx_gain_slider.value()),
                tx_gain_amp=self.tx_amp_check.isChecked(),
            )

            # Build device args string from selected device
            dev = self.connection_tab.selected_device()
            device_args = f"driver=hackrf,serial={dict(dev).get('serial', '')}" if dev else "driver=hackrf"

            success = self.engine.start_tx(device_args=device_args)
            if success:
                self._log(f"TX started: {freq/1e6:.3f} MHz, VGA={self.tx_gain_slider.value()} dB, AMP={self.tx_amp_check.isChecked()}")
                self.btn_start_tx.setEnabled(False)
                self.btn_stop_tx.setEnabled(True)
                self.tx_status_label.setText("Status: Transmitting")
                self.tx_status_label.setStyleSheet("color: green; font-weight: 600;")
                self.spectrum_timer.start()
            else:
                QMessageBox.critical(self, "TX Error", "Failed to start transmission.")
        else:
            QMessageBox.warning(self, "No Engine", "Engine not initialized.")

    def _stop_tx(self):
        if self.engine:
            self.engine.stop_tx()
        self.spectrum_timer.stop()
        self.btn_start_tx.setEnabled(True)
        self.btn_stop_tx.setEnabled(False)
        self.tx_status_label.setText("Status: Stopped")
        self.tx_status_label.setStyleSheet("color: red; font-weight: 600;")
        self._log("TX stopped")

    # ── Spectrum Display ──

    def _update_spectrum(self):
        """Update spectrum plots from engine data."""
        if not PYQTGRAPH_AVAILABLE:
            return
        frame = self._current_spectrum
        if frame is None:
            return

        try:
            freq = np.array(frame.frequencies)
            power = np.array(frame.power_db)

            # Frequency plot
            self.spectrum_curve.setData(freq, power)

            # Waterfall
            if self.waterfall_data.shape[1] >= len(power):
                self.waterfall_data[self.waterfall_row_index, :len(power)] = power[:self.waterfall_data.shape[1]]
                self.waterfall_row_index = (self.waterfall_row_index + 1) % 200
                self.waterfall_plot.setImage(self.waterfall_data, autoLevels=True)
        except Exception as e:
            print(f"Spectrum update error: {e}")

    def cleanup(self):
        """Clean up when tab is closed."""
        self._stop_tx()
        self._stop_pipeline()
