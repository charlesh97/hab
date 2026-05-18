import sys
import logging
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QTabWidget, QVBoxLayout, QWidget,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    datefmt="%H:%M:%S",
)

from telemetry_tab import TelemetryTab
from connection_tab import ConnectionTab
from dvbs2_tx_tab import DVBS2TXTab
from dashboard_tab import CinematicDashboardTab as DashboardTab
from hab_engine import HabEngine
from hab_engine.styles import main_stylesheet, BG_PRIMARY
from hab_engine.widgets import TopBar


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("HAB Ground Station")
        self.resize(1400, 900)

        # Initialize the engine (singleton)
        self.engine = HabEngine(enable_websocket=True)

        # Root widget
        root = QWidget()
        root.setStyleSheet(f"""
            background-color: {BG_PRIMARY};
            border-radius: 32px;
        """)
        root_layout = QVBoxLayout(root)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        # Cinematic Top Bar
        self.top_bar = TopBar("HAB-1 STRATOS", "ID: #521514")
        root_layout.addWidget(self.top_bar)

        # Tabs
        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)

        self.dashboard_tab = DashboardTab(self.engine)
        self.connection_tab = ConnectionTab(self.engine)
        self.telemetry_tab = TelemetryTab(self.engine)
        self.dvbs2_tx_tab = DVBS2TXTab(self.connection_tab, self.engine)

        self.tabs.addTab(self.dashboard_tab, "Dashboard")
        self.tabs.addTab(self.telemetry_tab, "Telemetry")
        self.tabs.addTab(self.connection_tab, "Connection")
        self.tabs.addTab(self.dvbs2_tx_tab, "DVBS-2 TX")
        # Default to first tab; switch by passing --tab N on command line
        import sys
        if "--tab" in sys.argv:
            idx = int(sys.argv[sys.argv.index("--tab") + 1])
            self.tabs.setCurrentIndex(idx)

        root_layout.addWidget(self.tabs)
        self.setCentralWidget(root)

    def closeEvent(self, event):
        """Clean up on close."""
        self.engine.cleanup()
        super().closeEvent(event)


def main() -> int:
    app = QApplication(sys.argv)
    app.setStyle("Fusion")

    # Apply cinematic dark stylesheet
    app.setStyleSheet(main_stylesheet())

    window = MainWindow()
    window.show()

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
