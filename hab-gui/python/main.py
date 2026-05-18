import sys
import logging
from PySide6.QtCore import Qt
from PySide6.QtGui import QPalette, QColor
from PySide6.QtWidgets import (
    QApplication,
    QMainWindow,
    QTabWidget,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    datefmt="%H:%M:%S",
)

from telemetry_tab import TelemetryTab
from connection_tab import ConnectionTab
from dvbs2_tx_tab import DVBS2TXTab
from dashboard_tab import DashboardTab
from hab_engine import HabEngine


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("HAB Ground Station")
        self.resize(1200, 800)

        # Initialize the engine (singleton)
        self.engine = HabEngine(enable_websocket=True)

        tabs = QTabWidget()
        
        # Create tabs, pass engine reference
        self.dashboard_tab = DashboardTab(self.engine)
        self.connection_tab = ConnectionTab(self.engine)
        self.telemetry_tab = TelemetryTab(self.engine)
        self.dvbs2_tx_tab = DVBS2TXTab(self.connection_tab, self.engine)
        
        tabs.addTab(self.dashboard_tab, "Dashboard")
        tabs.addTab(self.telemetry_tab, "Telemetry")
        tabs.addTab(self.connection_tab, "Connection")
        tabs.addTab(self.dvbs2_tx_tab, "DVBS-2 TX")
        
        self.setCentralWidget(tabs)
        self.setWindowTitle("HAB Ground Station v0.1")

    def closeEvent(self, event):
        """Clean up on close."""
        self.engine.cleanup()
        super().closeEvent(event)


def apply_dark_palette(app: QApplication) -> None:
    app.setStyle("Fusion")
    palette = QPalette()
    palette.setColor(QPalette.Window, QColor(53, 53, 53))
    palette.setColor(QPalette.WindowText, Qt.white)
    palette.setColor(QPalette.Base, QColor(35, 35, 35))
    palette.setColor(QPalette.AlternateBase, QColor(53, 53, 53))
    palette.setColor(QPalette.ToolTipBase, Qt.white)
    palette.setColor(QPalette.ToolTipText, Qt.white)
    palette.setColor(QPalette.Text, Qt.white)
    palette.setColor(QPalette.Button, QColor(53, 53, 53))
    palette.setColor(QPalette.ButtonText, Qt.white)
    palette.setColor(QPalette.BrightText, Qt.red)
    palette.setColor(QPalette.Link, QColor(42, 130, 218))
    palette.setColor(QPalette.Highlight, QColor(42, 130, 218))
    palette.setColor(QPalette.HighlightedText, Qt.black)
    app.setPalette(palette)


def main() -> int:
    app = QApplication(sys.argv)
    apply_dark_palette(app)

    window = MainWindow()
    window.show()

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
