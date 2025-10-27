import os
import subprocess
import threading
import time
from queue import Queue
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
)

try:
    import pyqtgraph as pg
    import numpy as np
    PYQTGRAPH_AVAILABLE = True
except ImportError:
    PYQTGRAPH_AVAILABLE = False


class DVBS2TXTab(QWidget):
    # Signal for thread-safe debug output (process_name, message)
    debug_message = Signal(str, str)
    
    def __init__(self, connection_tab, parent=None) -> None:
        super().__init__(parent)
        
        self.connection_tab = connection_tab
        self.ffmpeg_process = None
        self.tsp_process = None
        self.gnuradio_flowgraph = None
        self.selected_file = None
        self.tsfifo_path = "/tmp/tsfifo"
        self.gnuradio_available = False
        
        # Connect signal to slot - the ffmpeg and tsp processes will emit messages via this signal
        self.debug_message.connect(self.append_debug_to_terminal)
        
        # Check if GNU Radio is available (but don't import yet)
        try:
            import gnuradio
            self.gnuradio_available = True
        except ImportError:
            self.gnuradio_available = False
            print("Warning: GNU Radio not available")
        
        # Setup UI
        main_layout = QVBoxLayout(self)
        
        # Header
        header = QLabel("DVBS-2 Transmitter")
        header.setAlignment(Qt.AlignLeft)
        header.setStyleSheet("font-size: 18px; font-weight: 600;")
        main_layout.addWidget(header)
        
        # File Input Section
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
        
        # Pipeline Control Section
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
        
        # ffmpeg terminal
        ffmpeg_widget = QWidget()
        ffmpeg_layout = QVBoxLayout(ffmpeg_widget)
        ffmpeg_layout.setContentsMargins(5, 5, 5, 5)
        ffmpeg_label = QLabel("ffmpeg Output:")
        ffmpeg_label.setStyleSheet("font-weight: 600;")
        self.debug_terminal_ffmpeg = QPlainTextEdit()
        self.debug_terminal_ffmpeg.setReadOnly(True)
        self.debug_terminal_ffmpeg.setPlaceholderText("ffmpeg output will appear here...")
        ffmpeg_layout.addWidget(ffmpeg_label)
        ffmpeg_layout.addWidget(self.debug_terminal_ffmpeg)
        
        # tsp terminal
        tsp_widget = QWidget()
        tsp_layout = QVBoxLayout(tsp_widget)
        tsp_layout.setContentsMargins(5, 5, 5, 5)
        tsp_label = QLabel("tsp Output:")
        tsp_label.setStyleSheet("font-weight: 600;")
        self.debug_terminal_tsp = QPlainTextEdit()
        self.debug_terminal_tsp.setReadOnly(True)
        self.debug_terminal_tsp.setPlaceholderText("tsp output will appear here...")
        tsp_layout.addWidget(tsp_label)
        tsp_layout.addWidget(self.debug_terminal_tsp)
        
        debug_terminals_layout.addWidget(ffmpeg_widget)
        debug_terminals_layout.addWidget(tsp_widget)
        
        pipeline_layout.addLayout(debug_terminals_layout)
        pipeline_group.setLayout(pipeline_layout)
        main_layout.addWidget(pipeline_group)
        
        # Transmission Control Section
        tx_group = QGroupBox("Transmission Control")
        tx_layout = QVBoxLayout()
        
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
        
        # Create splitter for spectrum visualization
        splitter = QSplitter(Qt.Vertical)
        
        # Spectrum visualization
        spectrum_widget = QWidget()
        spectrum_layout = QVBoxLayout(spectrum_widget)
        spectrum_layout.setContentsMargins(0, 0, 0, 0)
        
        spectrum_header = QLabel("Spectrum Visualization")
        spectrum_header.setStyleSheet("font-weight: 600;")
        spectrum_layout.addWidget(spectrum_header)
        
        if PYQTGRAPH_AVAILABLE:
            pg.setConfigOption('background', (35, 35, 35))
            pg.setConfigOption('foreground', 'w')
            
            # Frequency spectrum plot
            self.spectrum_plot = pg.PlotWidget()
            self.spectrum_plot.setLabel('left', 'Power', units='dB')
            self.spectrum_plot.setLabel('bottom', 'Frequency', units='Hz')
            self.spectrum_plot.showGrid(x=True, y=True, alpha=0.3)
            self.spectrum_plot.setMinimumHeight(150)
            self.spectrum_curve = self.spectrum_plot.plot(pen=pg.mkPen(color=(42, 130, 218), width=1))
            
            # Waterfall plot
            self.waterfall_plot = pg.ImageView()
            self.waterfall_plot.setMinimumHeight(200)
            self.waterfall_plot.view.invertY(True)
            
            spectrum_layout.addWidget(self.spectrum_plot)
            spectrum_layout.addWidget(self.waterfall_plot)
            
            # Initialize waterfall data
            self.waterfall_data = np.zeros((200, 1024))  # 200 rows of 1024 FFT points
            self.waterfall_row_index = 0
        else:
            no_graph_msg = QLabel("PyQtGraph not installed. Install with: pip install pyqtgraph")
            no_graph_msg.setMinimumHeight(300)
            no_graph_msg.setAlignment(Qt.AlignCenter)
            no_graph_msg.setStyleSheet("background-color: #232323; color: white;")
            spectrum_layout.addWidget(no_graph_msg)
        
        splitter.addWidget(spectrum_widget)
        splitter.setStretchFactor(0, 1)
        
        main_layout.addWidget(splitter)
        
        # Connect signals
        self.btn_browse_file.clicked.connect(self.browse_file_clicked)
        self.btn_start_pipeline.clicked.connect(self.start_pipeline_clicked)
        self.btn_stop_pipeline.clicked.connect(self.stop_pipeline_clicked)
        self.btn_start_tx.clicked.connect(self.start_tx_clicked)
        self.btn_stop_tx.clicked.connect(self.stop_tx_clicked)
        
        # Setup spectrum update timer
        self.spectrum_timer = QTimer()
        self.spectrum_timer.timeout.connect(self.update_spectrum_display)
        self.spectrum_timer.setInterval(50)  # ~20 Hz update rate
        
    def append_debug_to_terminal(self, process_name: str, message: str) -> None:
        """Append message to appropriate debug terminal with timestamp (called from signal)"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        formatted_message = f"[{timestamp}] {message}"
        
        if process_name == "ffmpeg":
            self.debug_terminal_ffmpeg.appendPlainText(formatted_message)
        elif process_name == "tsp":
            self.debug_terminal_tsp.appendPlainText(formatted_message)
        
        # Also print to console
        print(formatted_message)
    
    def append_debug(self, message: str) -> None:
        """Append message to both terminals with timestamp (for status messages)"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        formatted_message = f"[{timestamp}] {message}"
        self.debug_terminal_ffmpeg.appendPlainText(formatted_message)
        self.debug_terminal_tsp.appendPlainText(formatted_message)
        print(formatted_message)
        
    def browse_file_clicked(self) -> None:
        """Open file dialog to select MP4 file"""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select MP4 File",
            "",
            "MP4 Files (*.mp4);;All Files (*)"
        )
        
        if file_path:
            self.selected_file = file_path
            self.file_path_display.setText(file_path)
            self.append_debug(f"Selected file: {file_path}")
    
    def start_pipeline_clicked(self) -> None:
        """Start ffmpeg and tsp pipeline"""
        if not self.selected_file:
            QMessageBox.warning(self, "No File", "Please select an MP4 file first.")
            return
        
        if not os.path.exists(self.selected_file):
            QMessageBox.warning(self, "File Not Found", "Selected file does not exist.")
            return
        
        try:
            # Create named pipe if it doesn't exist
            if os.path.exists(self.tsfifo_path):
                os.remove(self.tsfifo_path)
            os.mkfifo(self.tsfifo_path)
            self.append_debug(f"Created named pipe: {self.tsfifo_path}")
            
            # Start ffmpeg
            ffmpeg_cmd = [
                "ffmpeg", "-re", "-fflags", "+genpts",
                "-i", self.selected_file,
                "-vf", "scale=1920:1080,format=yuv420p", "-r", "30",
                "-c:v", "libx264", "-preset", "veryfast", "-tune", "zerolatency",
                "-g", "30", "-keyint_min", "30",
                "-b:v", "700k", "-maxrate", "700k", "-bufsize", "500k",
                "-c:a", "mp2", "-b:a", "128k",
                "-f", "mpegts", "-muxrate", "965326", "-mpegts_flags", "+resend_headers",
                "udp://239.1.1.1:5001?pkt_size=1316"
            ]
            
            self.append_debug(f"Starting ffmpeg: {ffmpeg_cmd}")
            self.ffmpeg_process = subprocess.Popen(
                ffmpeg_cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1  # Line buffered
            )
            
            # Start thread to read ffmpeg output
            threading.Thread(target=self._read_process_output, args=(self.ffmpeg_process, "ffmpeg"), daemon=True).start()
            
            # Start tsp
            tsp_cmd = [
                "tsp", "-I", "ip", "239.1.1.1:5001",
                "-P", "regulate", "--bitrate", "965326",
                "-O", "file", self.tsfifo_path
            ]
            
            self.append_debug(f"Starting tsp: {' '.join(tsp_cmd)}")
            self.tsp_process = subprocess.Popen(
                tsp_cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1  # Line buffered
            )
            
            # Start thread to read tsp output
            threading.Thread(target=self._read_process_output, args=(self.tsp_process, "tsp"), daemon=True).start()
            
            self.pipeline_status_label.setText("Status: Running")
            self.pipeline_status_label.setStyleSheet("color: green; font-weight: 600;")
            self.btn_start_pipeline.setEnabled(False)
            self.btn_stop_pipeline.setEnabled(True)
            
        except Exception as e:
            self.append_debug(f"Error starting pipeline: {e}")
            QMessageBox.critical(self, "Pipeline Error", f"Failed to start pipeline: {e}")
    
    def stop_pipeline_clicked(self) -> None:
        """Stop ffmpeg and tsp pipeline"""
        try:
            if self.ffmpeg_process:
                self.ffmpeg_process.terminate()
                self.ffmpeg_process.wait(timeout=5)
                self.append_debug("ffmpeg terminated")
            
            if self.tsp_process:
                self.tsp_process.terminate()
                self.tsp_process.wait(timeout=5)
                self.append_debug("tsp terminated")
            
            # Cleanup named pipe
            if os.path.exists(self.tsfifo_path):
                os.remove(self.tsfifo_path)
                self.append_debug(f"Removed named pipe: {self.tsfifo_path}")
            
            self.pipeline_status_label.setText("Status: Stopped")
            self.pipeline_status_label.setStyleSheet("color: red; font-weight: 600;")
            self.btn_start_pipeline.setEnabled(True)
            self.btn_stop_pipeline.setEnabled(False)
            
        except Exception as e:
            self.append_debug(f"Error stopping pipeline: {e}")
    
    def _read_process_output(self, process, name):
        """Read process output and append to debug terminal (runs in background thread)"""
        while process.poll() is None:
            try:
                line = process.stdout.readline()
                if line:
                    stripped = line.strip()
                    if stripped:  # Only print non-empty lines
                        # Emit signal for thread-safe GUI update
                        self.debug_message.emit(name, stripped)
            except:
                break
        self.debug_message.emit(name, "Process ended")
    
    def start_tx_clicked(self) -> None:
        """Start GNURadio transmission"""
        # Check device connection
        if not self.connection_tab.is_device_connected():
            QMessageBox.warning(
                self, 
                "No Device", 
                "Please connect to a HackRF device in the Connection tab first."
            )
            return
        
        # Check if pipeline is running
        if not self.btn_stop_pipeline.isEnabled():
            QMessageBox.warning(
                self,
                "Pipeline Not Running",
                "Please start the pipeline first."
            )
            return
        
        try:
            self.append_debug("Importing GNURadio modules...")
            from dvbs2_flowgraph import Dvbs2Flowgraph
            self.append_debug("GNURadio modules imported successfully")
            
            # Get device info from connection tab
            device_args = self.connection_tab.get_device_args()
            if device_args is None:
                QMessageBox.warning(self, "Device Error", "Could not get device arguments.")
                return
            
            params = self.connection_tab.get_connection_params()
            
            self.append_debug(f"Creating flowgraph with center_freq={params['frequency']/1e6:.3f} MHz")
            
            # Create flowgraph
            self.gnuradio_flowgraph = Dvbs2Flowgraph(
                device_args=device_args,
                center_freq=params["frequency"],
                symbol_rate=1000000,  # 1 Msps
                tx_gain=50,  # Default TX gain
                file_path=self.tsfifo_path,
                callback=None
            )
            
            self.append_debug("Flowgraph created, starting...")
            self.gnuradio_flowgraph.start()
            self.append_debug("Flowgraph started successfully")
            
            # Start spectrum update timer
            self.spectrum_timer.start()
            
            self.tx_status_label.setText("Status: Running")
            self.tx_status_label.setStyleSheet("color: green; font-weight: 600;")
            self.btn_start_tx.setEnabled(False)
            self.btn_stop_tx.setEnabled(True)
            
        except ImportError as e:
            error_msg = f"Failed to import GNURadio: {e}"
            self.append_debug(error_msg)
            QMessageBox.critical(self, "Import Error", f"{error_msg}\n\nMake sure GNU Radio is installed via Homebrew.")
        except Exception as e:
            error_msg = f"Error starting TX: {e}"
            self.append_debug(error_msg)
            import traceback
            self.append_debug(traceback.format_exc())
            QMessageBox.critical(self, "TX Error", error_msg)
    
    def stop_tx_clicked(self) -> None:
        """Stop GNURadio transmission"""
        try:
            if self.gnuradio_flowgraph:
                self.spectrum_timer.stop()
                self.gnuradio_flowgraph.stop()
                self.gnuradio_flowgraph.wait()
                self.append_debug("GNURadio flowgraph stopped")
            
            self.tx_status_label.setText("Status: Stopped")
            self.tx_status_label.setStyleSheet("color: red; font-weight: 600;")
            self.btn_start_tx.setEnabled(True)
            self.btn_stop_tx.setEnabled(False)
            
        except Exception as e:
            self.append_debug(f"Error stopping TX: {e}")
    
    def update_spectrum_display(self) -> None:
        """Update spectrum plots from GNURadio flowgraph data"""
        if not PYQTGRAPH_AVAILABLE or not self.gnuradio_flowgraph:
            return
        
        try:
            # Get spectrum data from flowgraph
            spectrum_data = self.gnuradio_flowgraph.get_spectrum_data()
            
            if spectrum_data is None:
                return
            
            frequencies, power_db = spectrum_data
            
            # Update frequency plot
            self.spectrum_curve.setData(frequencies, power_db)
            
            # Update waterfall
            self.waterfall_data[self.waterfall_row_index, :] = power_db
            self.waterfall_row_index = (self.waterfall_row_index + 1) % 200
            self.waterfall_plot.setImage(self.waterfall_data, autoLevels=True)
            
        except Exception as e:
            print(f"Error updating spectrum: {e}")
    
    def cleanup(self):
        """Cleanup resources when tab is closed"""
        self.stop_tx_clicked()
        self.stop_pipeline_clicked()

