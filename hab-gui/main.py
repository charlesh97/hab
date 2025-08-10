import sys
import asyncio
import os
from datetime import datetime

from PySide6.QtCore import Qt
from PySide6.QtGui import QPalette, QColor
from PySide6.QtWidgets import (
    QApplication,
    QMainWindow,
    QWidget,
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

from qasync import QEventLoop, asyncSlot
from bleak import BleakScanner, BleakClient, BleakError


class TelemetryTab(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)

        header = QLabel("Telemetry (Coming Soon)")
        header.setAlignment(Qt.AlignLeft)
        header.setStyleSheet("font-size: 18px; font-weight: 600;")

        hint = QLabel(
            "This tab will display live telemetry, graphs, and controls.\n"
            "For now, use the Bluetooth tab to scan and connect to your payload."
        )
        hint.setWordWrap(True)

        btn_row = QHBoxLayout()
        btn_refresh = QPushButton("Refresh")
        btn_export = QPushButton("Export CSV")
        btn_refresh.setEnabled(False)
        btn_export.setEnabled(False)
        btn_row.addWidget(btn_refresh)
        btn_row.addWidget(btn_export)
        btn_row.addStretch(1)

        layout.addWidget(header)
        layout.addWidget(hint)
        layout.addLayout(btn_row)
        layout.addStretch(1)


class BleTab(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)

        self.discovered = []  # list[bleak.backends.device.BLEDevice]
        self.client: BleakClient | None = None
        self.is_connecting = False
        self.default_download_dir = os.path.expanduser("~/Downloads")

        # UI
        main_layout = QVBoxLayout(self)

        controls_layout = QHBoxLayout()
        self.btn_scan = QPushButton("Scan")
        self.btn_connect = QPushButton("Connect")
        self.btn_disconnect = QPushButton("Disconnect")
        self.btn_disconnect.setEnabled(False)
        controls_layout.addWidget(self.btn_scan)
        controls_layout.addWidget(self.btn_connect)
        controls_layout.addWidget(self.btn_disconnect)
        controls_layout.addStretch(1)

        self.device_list = QListWidget()
        self.device_list.setAlternatingRowColors(True)

        # Download group
        download_group = QGroupBox("Download / Read Data")
        form = QFormLayout()
        self.input_char_uuid = QLineEdit()
        self.input_char_uuid.setPlaceholderText(
            "Characteristic UUID to read from (e.g. 0000xxxx-0000-1000-8000-00805f9b34fb)"
        )
        self.input_save_path = QLineEdit()
        self.input_save_path.setPlaceholderText("Save file path (optional)")
        self.btn_browse = QPushButton("Browse…")
        browse_row = QHBoxLayout()
        browse_row.addWidget(self.input_save_path)
        browse_row.addWidget(self.btn_browse)

        self.btn_download_once = QPushButton("Read Once → Save")
        self.btn_start_notifications = QPushButton("Start Notifications → Append")
        self.btn_stop_notifications = QPushButton("Stop Notifications")
        self.btn_start_notifications.setEnabled(False)
        self.btn_stop_notifications.setEnabled(False)

        form.addRow("Characteristic UUID", self.input_char_uuid)
        form.addRow("Save To", QWidget())
        form.itemAt(form.rowCount() - 1, QFormLayout.FieldRole).widget().setLayout(browse_row)
        form.addRow(self.btn_download_once)
        form.addRow(self.btn_start_notifications)
        form.addRow(self.btn_stop_notifications)
        download_group.setLayout(form)

        # Log
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setPlaceholderText("Logs will appear here…")

        main_layout.addLayout(controls_layout)
        main_layout.addWidget(QLabel("Discovered Devices:"))
        main_layout.addWidget(self.device_list)
        main_layout.addWidget(download_group)
        main_layout.addWidget(QLabel("Log:"))
        main_layout.addWidget(self.log)

        # Signals
        self.btn_scan.clicked.connect(self.scan_clicked)
        self.btn_connect.clicked.connect(self.connect_clicked)
        self.btn_disconnect.clicked.connect(self.disconnect_clicked)
        self.btn_browse.clicked.connect(self.browse_save_path)
        self.btn_download_once.clicked.connect(self.download_once_clicked)
        self.btn_start_notifications.clicked.connect(self.start_notifications_clicked)
        self.btn_stop_notifications.clicked.connect(self.stop_notifications_clicked)

        self.notification_task: asyncio.Task | None = None

    def append_log(self, message: str) -> None:
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log.appendPlainText(f"[{timestamp}] {message}")

    # ----- UI helpers -----
    def selected_device(self):
        idx = self.device_list.currentRow()
        if 0 <= idx < len(self.discovered):
            return self.discovered[idx]
        return None

    def browse_save_path(self) -> None:
        default_dir = self.default_download_dir
        os.makedirs(default_dir, exist_ok=True)
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Save Data As",
            os.path.join(default_dir, "ble_data.bin"),
            "All Files (*.*)",
        )
        if path:
            self.input_save_path.setText(path)

    # ----- BLE actions -----
    @asyncSlot()
    async def scan_clicked(self) -> None:
        try:
            self.append_log("Scanning for BLE devices (5s)…")
            self.device_list.clear()
            self.discovered = await BleakScanner.discover(timeout=5.0)
            if not self.discovered:
                self.append_log("No devices found.")
                return
            for dev in self.discovered:
                name = dev.name or "(unknown)"
                address = getattr(dev, "address", getattr(dev, "details", "?"))
                self.device_list.addItem(f"{name} — {address}")
            self.append_log(f"Found {len(self.discovered)} devices.")
        except Exception as exc:
            self.append_log(f"Scan failed: {exc}")

    @asyncSlot()
    async def connect_clicked(self) -> None:
        if self.is_connecting:
            return
        device = self.selected_device()
        if device is None:
            QMessageBox.information(self, "Connect", "Select a device from the list first.")
            return
        self.is_connecting = True
        self.btn_connect.setEnabled(False)
        try:
            if self.client and self.client.is_connected:
                await self.client.disconnect()
                self.client = None

            self.append_log(f"Connecting to {device.name or device.address}…")
            self.client = BleakClient(device)
            await self.client.connect(timeout=10.0)
            if await self.client.is_connected():
                self.append_log("Connected.")
                self.btn_disconnect.setEnabled(True)
                self.btn_start_notifications.setEnabled(True)
            else:
                self.append_log("Connection did not establish.")
                self.client = None
        except BleakError as exc:
            self.append_log(f"BLE error: {exc}")
            self.client = None
        except Exception as exc:
            self.append_log(f"Connect failed: {exc}")
            self.client = None
        finally:
            self.is_connecting = False
            self.btn_connect.setEnabled(True)

    @asyncSlot()
    async def disconnect_clicked(self) -> None:
        await self._stop_notifications_if_running()
        if self.client:
            try:
                await self.client.disconnect()
                self.append_log("Disconnected.")
            except Exception as exc:
                self.append_log(f"Disconnect error: {exc}")
        self.client = None
        self.btn_disconnect.setEnabled(False)
        self.btn_start_notifications.setEnabled(False)
        self.btn_stop_notifications.setEnabled(False)

    def _resolve_save_path(self) -> str:
        path = self.input_save_path.text().strip()
        if not path:
            os.makedirs(self.default_download_dir, exist_ok=True)
            filename = datetime.now().strftime("ble_data_%Y%m%d_%H%M%S.bin")
            path = os.path.join(self.default_download_dir, filename)
        return path

    @asyncSlot()
    async def download_once_clicked(self) -> None:
        if not self.client or not await self.client.is_connected():
            QMessageBox.warning(self, "Read", "Not connected to a device.")
            return
        char_uuid = self.input_char_uuid.text().strip()
        if not char_uuid:
            QMessageBox.information(
                self,
                "Characteristic UUID",
                "Enter a characteristic UUID to read from.",
            )
            return
        try:
            self.append_log(f"Reading from {char_uuid}…")
            data = await self.client.read_gatt_char(char_uuid)
            save_path = self._resolve_save_path()
            with open(save_path, "wb") as f:
                f.write(data)
            self.append_log(f"Saved {len(data)} bytes to {save_path}")
        except Exception as exc:
            self.append_log(f"Read failed: {exc}")

    async def _notification_callback(self, sender: int, data: bytearray, file_path: str):
        try:
            with open(file_path, "ab") as f:
                f.write(data)
            self.append_log(f"Notification {sender}: +{len(data)} bytes (→ {file_path})")
        except Exception as exc:
            self.append_log(f"Write error: {exc}")

    @asyncSlot()
    async def start_notifications_clicked(self) -> None:
        if not self.client or not await self.client.is_connected():
            QMessageBox.warning(self, "Notifications", "Not connected to a device.")
            return
        char_uuid = self.input_char_uuid.text().strip()
        if not char_uuid:
            QMessageBox.information(
                self,
                "Characteristic UUID",
                "Enter a characteristic UUID to subscribe to.",
            )
            return
        file_path = self._resolve_save_path()
        try:
            # Start notifications
            self.append_log(f"Subscribing to notifications on {char_uuid}…")
            await self.client.start_notify(
                char_uuid,
                lambda sender, data: asyncio.create_task(
                    self._notification_callback(sender, data, file_path)
                ),
            )
            self.btn_start_notifications.setEnabled(False)
            self.btn_stop_notifications.setEnabled(True)
            self.append_log("Receiving notifications. Click Stop to end.")
        except Exception as exc:
            self.append_log(f"Start notifications failed: {exc}")

    async def _stop_notifications_if_running(self) -> None:
        if self.client and await self.client.is_connected():
            char_uuid = self.input_char_uuid.text().strip()
            if char_uuid:
                try:
                    await self.client.stop_notify(char_uuid)
                except Exception:
                    pass
        self.btn_stop_notifications.setEnabled(False)
        self.btn_start_notifications.setEnabled(True)

    @asyncSlot()
    async def stop_notifications_clicked(self) -> None:
        await self._stop_notifications_if_running()
        self.append_log("Notifications stopped.")


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("HAB Ground Station")
        self.resize(1000, 700)

        tabs = QTabWidget()
        tabs.addTab(TelemetryTab(), "Telemetry")
        tabs.addTab(BleTab(), "Bluetooth")
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

    loop = QEventLoop(app)
    asyncio.set_event_loop(loop)

    window = MainWindow()
    window.show()

    with loop:
        return loop.run_forever()


if __name__ == "__main__":
    sys.exit(main())
