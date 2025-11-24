from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QLabel,
    QPlainTextEdit,
    QGroupBox,
    QFormLayout,
    QLineEdit,
    QCheckBox,
    QSplitter,
)
from datetime import datetime
import numpy as np

try:
    import pyqtgraph as pg
    PYQTGRAPH_AVAILABLE = True
except ImportError:
    PYQTGRAPH_AVAILABLE = False


class TelemetryTab(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)

        # Header
        header = QLabel("Telemetry")
        header.setAlignment(Qt.AlignLeft)
        header.setStyleSheet("font-size: 18px; font-weight: 600;")

        # Control buttons
        btn_row = QHBoxLayout()
        self.btn_start_rx = QPushButton("Start RX")
        self.btn_stop_rx = QPushButton("Stop RX")
        self.btn_export = QPushButton("Export CSV")
        self.btn_stop_rx.setEnabled(False)
        self.btn_export.setEnabled(False)
        
        btn_row.addWidget(self.btn_start_rx)
        btn_row.addWidget(self.btn_stop_rx)
        btn_row.addWidget(self.btn_export)
        btn_row.addStretch(1)

        # Create splitter for spectrum analyzer and terminal
        splitter = QSplitter(Qt.Vertical)

        # Spectrum Analyzer Section
        spectrum_widget = QWidget()
        spectrum_layout = QVBoxLayout(spectrum_widget)
        spectrum_layout.setContentsMargins(0, 0, 0, 0)

        spectrum_header = QLabel("Spectrum Analyzer")
        spectrum_header.setStyleSheet("font-weight: 600;")

        # Spectrum controls
        controls_group = QGroupBox("Spectrum Controls")
        controls_layout = QHBoxLayout()

        # RBW and VBW inputs
        params_form = QFormLayout()
        self.input_rbw = QLineEdit()
        self.input_rbw.setText("10")
        self.input_rbw.setPlaceholderText("kHz")
        self.input_rbw.setMaximumWidth(100)
        rbw_layout = QHBoxLayout()
        rbw_layout.addWidget(self.input_rbw)
        rbw_layout.addWidget(QLabel("kHz"))
        rbw_layout.addStretch()
        params_form.addRow("RBW:", rbw_layout)

        self.input_vbw = QLineEdit()
        self.input_vbw.setText("10")
        self.input_vbw.setPlaceholderText("kHz")
        self.input_vbw.setMaximumWidth(100)
        vbw_layout = QHBoxLayout()
        vbw_layout.addWidget(self.input_vbw)
        vbw_layout.addWidget(QLabel("kHz"))
        vbw_layout.addStretch()
        params_form.addRow("VBW:", vbw_layout)

        controls_layout.addLayout(params_form)

        # Max hold and clear buttons
        spectrum_btn_layout = QVBoxLayout()
        self.chk_max_hold = QCheckBox("Max Hold")
        self.btn_clear_spectrum = QPushButton("Clear")
        self.btn_clear_spectrum.setMaximumWidth(100)
        spectrum_btn_layout.addWidget(self.chk_max_hold)
        spectrum_btn_layout.addWidget(self.btn_clear_spectrum)
        spectrum_btn_layout.addStretch()

        controls_layout.addLayout(spectrum_btn_layout)
        controls_layout.addStretch()
        controls_group.setLayout(controls_layout)

        # Spectrum plot
        if PYQTGRAPH_AVAILABLE:
            pg.setConfigOption('background', (35, 35, 35))
            pg.setConfigOption('foreground', 'w')
            self.spectrum_plot = pg.PlotWidget()
            self.spectrum_plot.setLabel('left', 'Power', units='dB')
            self.spectrum_plot.setLabel('bottom', 'Frequency', units='Hz')
            self.spectrum_plot.showGrid(x=True, y=True, alpha=0.3)
            self.spectrum_plot.setMinimumHeight(300)
            
            # Initialize plot data
            self.spectrum_curve = self.spectrum_plot.plot(pen=pg.mkPen(color=(42, 130, 218), width=1))
            self.spectrum_data = None
            self.max_hold_data = None
        else:
            self.spectrum_plot = QLabel("PyQtGraph not installed. Install with: pip install pyqtgraph")
            self.spectrum_plot.setMinimumHeight(300)
            self.spectrum_plot.setAlignment(Qt.AlignCenter)
            self.spectrum_plot.setStyleSheet("background-color: #232323; color: white;")

        spectrum_layout.addWidget(spectrum_header)
        spectrum_layout.addWidget(controls_group)
        spectrum_layout.addWidget(self.spectrum_plot)

        # Terminal Section
        terminal_widget = QWidget()
        terminal_layout = QVBoxLayout(terminal_widget)
        terminal_layout.setContentsMargins(0, 0, 0, 0)

        terminal_label = QLabel("Telemetry Terminal:")
        self.terminal = QPlainTextEdit()
        self.terminal.setReadOnly(True)
        self.terminal.setPlaceholderText("Received telemetry will appear here...")
        self.terminal.setMinimumHeight(150)

        terminal_layout.addWidget(terminal_label)
        terminal_layout.addWidget(self.terminal)

        # Add widgets to splitter
        splitter.addWidget(spectrum_widget)
        splitter.addWidget(terminal_widget)
        splitter.setStretchFactor(0, 3)  # Spectrum gets more space
        splitter.setStretchFactor(1, 1)  # Terminal gets less space

        # Add everything to main layout
        layout.addWidget(header)
        layout.addLayout(btn_row)
        layout.addWidget(splitter)

        # Connect signals
        self.btn_start_rx.clicked.connect(self.start_rx_clicked)
        self.btn_stop_rx.clicked.connect(self.stop_rx_clicked)
        self.btn_export.clicked.connect(self.export_csv_clicked)
        self.btn_clear_spectrum.clicked.connect(self.clear_spectrum_clicked)

        # Telemetry receiver (will be initialized when needed)
        self.telemetry_rx = None
        
        # Spectrum update timer
        self.spectrum_timer = QTimer()
        self.spectrum_timer.timeout.connect(self.update_spectrum_display)
        self.spectrum_timer.setInterval(50)  # Update at ~20 Hz

    def append_telemetry(self, message: str) -> None:
        """Append telemetry message to terminal with timestamp"""
        timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        self.terminal.appendPlainText(f"[{timestamp}] {message}")

    def start_rx_clicked(self) -> None:
        """Start telemetry reception"""
        try:
            from telemetry_rx import TelemetryReceiverInterface
            
            if self.telemetry_rx is None:
                self.telemetry_rx = TelemetryReceiverInterface(
                    self.on_telemetry_received,
                    self.on_spectrum_data_received
                )
            
            self.telemetry_rx.start()
            self.spectrum_timer.start()
            self.append_telemetry("Telemetry RX started")
            self.btn_start_rx.setEnabled(False)
            self.btn_stop_rx.setEnabled(True)
        except Exception as e:
            self.append_telemetry(f"Error starting RX: {e}")

    def stop_rx_clicked(self) -> None:
        """Stop telemetry reception"""
        try:
            if self.telemetry_rx:
                self.telemetry_rx.stop()
            self.spectrum_timer.stop()
            self.append_telemetry("Telemetry RX stopped")
            self.btn_start_rx.setEnabled(True)
            self.btn_stop_rx.setEnabled(False)
        except Exception as e:
            self.append_telemetry(f"Error stopping RX: {e}")

    def export_csv_clicked(self) -> None:
        """Export telemetry data to CSV"""
        self.append_telemetry("CSV export not yet implemented")

    def on_telemetry_received(self, data: bytes) -> None:
        """Callback when telemetry is received"""
        # Process the packet
        processed = self.packet_processing(data)
        # Display in terminal
        self.append_telemetry(processed)

    def packet_processing(self, data: bytes) -> str:
        """Process received telemetry packet - placeholder for now"""
        # For now, just convert to hex string
        return f"RX: {data.hex()}"

    def on_spectrum_data_received(self, frequencies: np.ndarray, power_db: np.ndarray) -> None:
        """Callback when spectrum FFT data is received"""
        if not PYQTGRAPH_AVAILABLE:
            return

        # Store the latest spectrum data
        self.spectrum_data = (frequencies, power_db)

        # Update max hold if enabled
        if self.chk_max_hold.isChecked():
            if self.max_hold_data is None:
                self.max_hold_data = power_db.copy()
            else:
                # Take maximum of current and previous data
                self.max_hold_data = np.maximum(self.max_hold_data, power_db)

    def update_spectrum_display(self) -> None:
        """Update the spectrum plot display"""
        if not PYQTGRAPH_AVAILABLE or self.spectrum_data is None:
            return

        frequencies, power_db = self.spectrum_data

        # Use max hold data if enabled, otherwise use current data
        if self.chk_max_hold.isChecked() and self.max_hold_data is not None:
            display_data = self.max_hold_data
        else:
            display_data = power_db

        # Update the plot
        self.spectrum_curve.setData(frequencies, display_data)

    def clear_spectrum_clicked(self) -> None:
        """Clear the spectrum display and max hold data"""
        self.max_hold_data = None
        if PYQTGRAPH_AVAILABLE and self.spectrum_data is not None:
            # Clear by showing empty data
            self.spectrum_curve.setData([], [])
            self.spectrum_data = None
        self.append_telemetry("Spectrum cleared")

