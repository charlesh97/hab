import sys
from PySide6.QtCore import Qt
from PySide6.QtGui import QPalette, QColor
from PySide6.QtWidgets import (
    QApplication,
    QMainWindow,
    QTabWidget,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QListWidget,
    QLabel,
    QLineEdit,
    QFileDialog,
    QPlainTextEdit,
    QMessageBox,
    QGroupBox,
    QFormLayout,
)

from telemetry_tab import TelemetryTab
from connection_tab import ConnectionTab
from dvbs2_tx_tab import DVBS2TXTab


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("HAB Ground Station")
        self.resize(1000, 700)

        tabs = QTabWidget()
        
        # Create tabs in order: Telemetry, Connection, DVBS-2 TX
        # Connection tab must be created before DVBS-2 TX tab
        telemetry_tab = TelemetryTab()
        connection_tab = ConnectionTab()
        dvbs2_tx_tab = DVBS2TXTab(connection_tab)
        
        tabs.addTab(telemetry_tab, "Telemetry")
        tabs.addTab(connection_tab, "Connection")
        tabs.addTab(dvbs2_tx_tab, "DVBS-2 TX")
        
        self.setCentralWidget(tabs)


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
