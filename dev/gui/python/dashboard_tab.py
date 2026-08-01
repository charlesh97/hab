"""
Live Mission Dashboard — telemetry summary, camera feed, map, event log.
Glassmorphism design matching the STRATOS reference.
"""

import os
from datetime import datetime
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QPixmap, QPainter, QLinearGradient, QColor, QBrush
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QPushButton, QLabel, QFrame, QPlainTextEdit, QSplitter,
)
from hab_engine.widgets import GlassCard, PrimaryButton
from hab_engine.styles import (
    ACCENT_ORANGE, ACCENT_SKY, ACCENT_EMERALD,
    TEXT_PRIMARY, TEXT_SECONDARY, TEXT_TERTIARY, TEXT_DIM,
    BORDER_CARD, BG_CARD,
)

# ── Background Earth Image ──
EARTH_IMAGE = os.path.expanduser(
    "~/.openclaw/agents/main/workspace/earth_from_space.jpg"
)


class EarthBackground(QWidget):
    """Full-size Earth from space background with dark vignette."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.pixmap = QPixmap(EARTH_IMAGE)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)

    def paintEvent(self, event):
        if self.pixmap.isNull():
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)
        scaled = self.pixmap.scaled(
            self.size(), Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation
        )
        x = (scaled.width() - self.width()) // 2
        y = (scaled.height() - self.height()) // 2
        painter.drawPixmap(0, 0, scaled, x, y, self.width(), self.height())

        # Dark vignette overlay
        overlay = QLinearGradient(0, 0, 0, self.height())
        overlay.setColorAt(0.0, QColor(10, 10, 11, 220))
        overlay.setColorAt(0.15, QColor(10, 10, 11, 40))
        overlay.setColorAt(0.85, QColor(10, 10, 11, 40))
        overlay.setColorAt(1.0, QColor(10, 10, 11, 220))
        painter.fillRect(self.rect(), QBrush(overlay))
        painter.end()


class DashboardTopBar(QFrame):
    """Status bar showing mission name, link status, packet count, time."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(f"""
            DashboardTopBar {{
                background-color: {BG_CARD};
                border: 1px solid {BORDER_CARD};
                border-radius: 14px;
            }}
        """)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(20, 10, 20, 10)

        # Mission name
        name = QLabel("STRATOS HAB-1")
        name.setStyleSheet(f"font-size: 13px; font-weight: 700; color: {TEXT_PRIMARY}; letter-spacing: 1px;")
        layout.addWidget(name)

        # Status pills
        for label, status, color in [
            ("TELEMETRY", "NOMINAL", ACCENT_EMERALD),
            ("VIDEO LINK", "NOMINAL", ACCENT_EMERALD),
            ("GPS", "SEARCHING", "#f59e0b"),
        ]:
            pill = QLabel(f"● {label}: {status}")
            pill.setStyleSheet(f"""
                font-size: 9px; font-weight: 700; letter-spacing: 0.5px;
                color: {color};
                background-color: rgba(255,255,255,0.03);
                border: 1px solid rgba(255,255,255,0.06);
                border-radius: 9999px; padding: 4px 12px;
            """)
            layout.addWidget(pill)

        layout.addStretch()

        # Packet counter
        pkt = QLabel("PKT: 0")
        pkt.setStyleSheet(f"font-size: 11px; font-family: 'JetBrains Mono', monospace; color: {TEXT_TERTIARY};")
        layout.addWidget(pkt)

        # Time
        self.time_label = QLabel()
        self.time_label.setStyleSheet(f"font-size: 11px; font-family: 'JetBrains Mono', monospace; color: {TEXT_SECONDARY};")
        layout.addWidget(self.time_label)
        self._update_time()

    def _update_time(self):
        self.time_label.setText(datetime.now().strftime("%H:%M:%S UTC"))
        QTimer.singleShot(1000, self._update_time)


class TelemetryCard(QFrame):
    """Right panel — all telemetry readouts in a compact glass card."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(f"""
            TelemetryCard {{
                background-color: {BG_CARD};
                border: 1px solid {BORDER_CARD};
                border-radius: 16px;
            }}
        """)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(4)

        header = QLabel("TELEMETRY")
        header.setStyleSheet(f"font-size: 10px; font-weight: 700; color: {TEXT_TERTIARY}; letter-spacing: 1.5px;")
        layout.addWidget(header)

        self._rows = {}
        metrics = [
            ("ALTITUDE", "24,348", "m", ACCENT_SKY),
            ("CLIMB", "+9.4", "m/s", ACCENT_EMERALD),
            ("GROUND SPEED", "22.5", "m/s", TEXT_PRIMARY),
            ("HEADING", "085", "°", TEXT_PRIMARY),
            ("EXT TEMP", "-52.3", "°C", "#f59e0b"),
            ("INT TEMP", "+15.2", "°C", TEXT_PRIMARY),
            ("PRESSURE", "68.5", "hPa", TEXT_PRIMARY),
            ("BATTERY", "88.5", "%", ACCENT_EMERALD),
            ("GPS SATS", "11", "", TEXT_PRIMARY),
            ("ALTITUDE", "24,348", "m", ACCENT_SKY),
        ]
        for label, value, unit, color in metrics[:8]:
            row, val_widget = self._add_metric(layout, label, value, unit, color)
            self._rows[label] = val_widget

    def _add_metric(self, layout, label, value, unit, color):
        row = QHBoxLayout()
        row.setContentsMargins(0, 6, 0, 6)

        lbl = QLabel(label)
        lbl.setStyleSheet(f"font-size: 9px; font-weight: 600; color: {TEXT_TERTIARY}; letter-spacing: 0.8px;")
        row.addWidget(lbl)
        row.addStretch()

        val = QLabel(value)
        val.setStyleSheet(f"""
            font-size: 14px; font-weight: 700;
            font-family: 'JetBrains Mono', monospace;
            color: {color};
        """)
        row.addWidget(val)

        if unit:
            u = QLabel(unit)
            u.setStyleSheet(f"font-size: 9px; font-family: 'JetBrains Mono', monospace; color: {TEXT_DIM}; padding-top: 2px;")
            row.addWidget(u)

        layout.addLayout(row)
        # Thin divider
        div = QFrame()
        div.setFixedHeight(1)
        div.setStyleSheet("background-color: rgba(255,255,255,0.04);")
        layout.addWidget(div)
        return row, val


class CameraFeed(QFrame):
    """Camera feed placeholder with gradient and LIVE badge."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(f"""
            CameraFeed {{
                background-color: {BG_CARD};
                border: 1px solid {BORDER_CARD};
                border-radius: 16px;
            }}
        """)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # Video area
        video = QFrame()
        video.setMinimumHeight(240)
        video.setStyleSheet("""
            background-color: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                stop:0 #0a1628, stop:0.5 #111827, stop:1 #0a0a0b);
            border-radius: 16px 16px 0 0;
        """)
        video_layout = QVBoxLayout(video)
        video_layout.setContentsMargins(12, 12, 12, 12)

        # Top overlay: LIVE badge
        live_row = QHBoxLayout()
        live = QLabel("● LIVE")
        live.setStyleSheet(f"font-size: 9px; font-weight: 700; color: {ACCENT_ROSE}; letter-spacing: 1px; background: rgba(0,0,0,0.5); border-radius: 4px; padding: 2px 8px;")
        live_row.addWidget(live)
        live_row.addWidget(QLabel("ONBOARD CAM"))
        live_row.addStretch()

        # Bottom overlay: bitrate + signal info
        bl = QLabel("2.4 Mbps  ·  98%")
        bl.setStyleSheet(f"font-size: 9px; font-family: 'JetBrains Mono', monospace; color: {TEXT_TERTIARY}; background: rgba(0,0,0,0.5); border-radius: 4px; padding: 2px 8px;")
        live_row.addWidget(bl)
        video_layout.addLayout(live_row)
        video_layout.addStretch()

        # Stream URL bar
        url_bar = QFrame()
        url_bar.setStyleSheet(f"background-color: rgba(0,0,0,0.3); border-radius: 0 0 16px 16px; padding: 8px;")
        url_layout = QHBoxLayout(url_bar)
        url_layout.setContentsMargins(12, 6, 12, 6)
        url = QLabel("rtsp://hab-1.local/stream1")
        url.setStyleSheet(f"font-size: 9px; font-family: 'JetBrains Mono', monospace; color: {TEXT_DIM};")
        url_layout.addWidget(url, 1)
        reconnect = QPushButton("Reconnect")
        reconnect.setFixedHeight(24)
        reconnect.setStyleSheet(f"font-size: 9px; padding: 2px 12px; background: rgba(255,255,255,0.05); border-radius: 9999px; color: {TEXT_TERTIARY};")
        url_layout.addWidget(reconnect)

        layout.addWidget(video, 1)
        layout.addWidget(url_bar)


class LiveMap(QFrame):
    """Live map with balloon position, flight path, launch/recovery markers."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(f"""
            LiveMap {{
                background-color: {BG_CARD};
                border: 1px solid {BORDER_CARD};
                border-radius: 16px;
            }}
        """)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(4)

        header = QLabel("MAP VIEW")
        header.setStyleSheet(f"font-size: 10px; font-weight: 700; color: {TEXT_TERTIARY}; letter-spacing: 1.5px;")
        layout.addWidget(header)

        map_area = QLabel()
        map_area.setMinimumHeight(180)
        map_area.setAlignment(Qt.AlignCenter)
        map_area.setStyleSheet(f"""
            font-size: 8px; font-family: 'JetBrains Mono', monospace;
            color: {TEXT_DIM}; line-height: 1.3;
        """)
        map_area.setText(
            "  ┌──────────────────────────┐\n"
            "  │     ╭─────────────────╮   │\n"
            "  │    ╱                   ╲  │\n"
            "  │   │      ○ balloon      │ │\n"
            "  │   │     ╱ ╲             │ │\n"
            "  │   │    ╱   ╲ path       │ │\n"
            "  │   │   ╱     ╲           │ │\n"
            "  │   │  ╱       ╲          │ │\n"
            "  │   │ ○launch   ○recov    │ │\n"
            "  │    ╲                   ╱  │\n"
            "  │     ╰─────────────────╯   │\n"
            "  └──────────────────────────┘"
        )
        layout.addWidget(map_area, 1)

        # Lat/Lon readout
        coord = QLabel("39.0500°N  105.5000°W  |  Alt: 24,348m")
        coord.setStyleSheet(f"font-size: 9px; font-family: 'JetBrains Mono', monospace; color: {TEXT_TERTIARY};")
        layout.addWidget(coord)


class EventLog(QPlainTextEdit):
    """Live packet stream / event log with monospace formatting."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setReadOnly(True)
        self.setPlaceholderText("Waiting for telemetry...")
        self.setMaximumBlockCount(200)
        self.setMinimumHeight(120)
        self.setStyleSheet(f"""
            QPlainTextEdit {{
                background-color: rgba(0, 0, 0, 0.5);
                border: 1px solid {BORDER_CARD};
                border-radius: 12px;
                padding: 10px;
                color: {TEXT_SECONDARY};
                font-family: 'JetBrains Mono', monospace;
                font-size: 10px;
                line-height: 1.4;
            }}
        """)


class LiveDashboardTab(QWidget):
    """Full live mission dashboard — camera, map, telemetry, event log, actions."""

    def __init__(self, engine=None, parent=None) -> None:
        super().__init__(parent)
        self.engine = engine
        self.packets = []

        # Earth background
        self.earth_bg = EarthBackground(self)

        # Outer layout (overlaid on background)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 16, 24, 16)
        outer.setSpacing(12)

        # ── Top Bar ──
        self.top_bar = DashboardTopBar()
        outer.addWidget(self.top_bar)

        # ── Main Content Grid ──
        middle = QHBoxLayout()
        middle.setSpacing(12)

        # Left: Camera feed
        left_col = QVBoxLayout()
        left_col.setSpacing(12)
        self.camera = CameraFeed()
        left_col.addWidget(self.camera, 3)

        # Quick status row below camera
        status_row = QHBoxLayout()
        status_row.setSpacing(8)
        for label, val, color in [
            ("ALT", "24,348m", ACCENT_SKY),
            ("TEMP", "-52.3°C", "#f59e0b"),
            ("BATT", "88.5%", ACCENT_EMERALD),
        ]:
            pill = QLabel(f"{label}: {val}")
            pill.setStyleSheet(f"""
                font-size: 10px; font-weight: 700; font-family: 'JetBrains Mono', monospace;
                color: {color}; background: rgba(0,0,0,0.3);
                border: 1px solid {BORDER_CARD}; border-radius: 9999px;
                padding: 4px 12px;
            """)
            status_row.addWidget(pill)
        status_row.addStretch()
        left_col.addLayout(status_row)
        middle.addLayout(left_col, 3)

        # Center: Map
        self.map_widget = LiveMap()
        middle.addWidget(self.map_widget, 4)

        # Right: Telemetry
        self.telemetry = TelemetryCard()
        middle.addWidget(self.telemetry, 3)

        outer.addLayout(middle, 1)

        # ── Event Log ──
        log_header = QHBoxLayout()
        log_header.addWidget(QLabel("EVENT LOG"))
        log_header.addStretch()
        pause_btn = QPushButton("⏸")
        pause_btn.setFixedSize(28, 22)
        pause_btn.setStyleSheet(f"font-size: 11px; padding: 0; background: rgba(255,255,255,0.03); border: 1px solid {BORDER_CARD}; border-radius: 6px; color: {TEXT_TERTIARY};")
        log_header.addWidget(pause_btn)
        clear_btn = QPushButton("✕")
        clear_btn.setFixedSize(28, 22)
        clear_btn.setStyleSheet(f"font-size: 11px; padding: 0; background: rgba(255,255,255,0.03); border: 1px solid {BORDER_CARD}; border-radius: 6px; color: {TEXT_TERTIARY};")
        log_header.addWidget(clear_btn)
        self.event_log = EventLog()

        log_card = GlassCard()
        log_inner = QVBoxLayout(log_card)
        log_inner.setContentsMargins(0, 0, 0, 0)
        log_inner.setSpacing(0)

        # Add header with padding
        hdr_widget = QWidget()
        hdr_widget.setStyleSheet("background: transparent;")
        hdr = QHBoxLayout(hdr_widget)
        hdr.setContentsMargins(16, 10, 16, 4)
        hdr_lbl = QLabel("PACKET STREAM")
        hdr_lbl.setStyleSheet(f"font-size: 10px; font-weight: 700; color: {TEXT_TERTIARY}; letter-spacing: 1.5px;")
        hdr.addWidget(hdr_lbl)
        hdr.addStretch()
        rx_rate = QLabel("RX: 1.0 pkt/s")
        rx_rate.setStyleSheet(f"font-size: 9px; color: {ACCENT_EMERALD}; font-family: 'JetBrains Mono', monospace;")
        hdr.addWidget(rx_rate)
        log_inner.addWidget(hdr_widget)
        log_inner.addWidget(self.event_log)
        outer.addWidget(log_card)

        # ── Quick Actions Row ──
        actions = QHBoxLayout()
        actions.setSpacing(8)
        for btn_def in [
            ("▶ START TX", ACCENT_ORANGE),
            ("■ STOP TX", TEXT_PRIMARY),
            ("▶ PIPELINE", ACCENT_SKY),
            ("■ STOP PIPELINE", TEXT_PRIMARY),
            ("SET FREQ", TEXT_SECONDARY),
            ("CONFIG", TEXT_SECONDARY),
        ]:
            label, color = btn_def
            btn = QPushButton(label)
            if color == ACCENT_ORANGE:
                btn = PrimaryButton(label)
            else:
                btn.setStyleSheet(f"""
                    QPushButton {{
                        background-color: rgba(255,255,255,0.03);
                        border: 1px solid {BORDER_CARD};
                        border-radius: 9999px;
                        padding: 8px 18px;
                        color: {color};
                        font-size: 10px;
                        font-weight: 600;
                        letter-spacing: 0.3px;
                    }}
                    QPushButton:hover {{
                        background-color: rgba(255,255,255,0.06);
                    }}
                """)
            actions.addWidget(btn)
        actions.addStretch()
        outer.addLayout(actions)

        # ── Simulate live data ──
        self._demo_timer = QTimer()
        self._demo_timer.timeout.connect(self._simulate_packet)
        self._demo_timer.start(2000)

    def resizeEvent(self, event):
        self.earth_bg.setGeometry(self.rect())
        super().resizeEvent(event)

    def _simulate_packet(self):
        """Simulate a telemetry packet for demo."""
        ts = datetime.now().strftime("%H:%M:%S")
        alt = 24348 + (hash(str(len(self.packets))) % 20 - 10)
        vs = 9.4 + (hash(str(len(self.packets))) % 10 - 5) / 10
        temp = -52.3 + (hash(str(len(self.packets) + 1)) % 10 - 5) / 10

        pkt_type = "TLM" if len(self.packets) % 5 != 0 else "EVT"
        if pkt_type == "TLM":
            msg = f"[{ts}] [TLM] A:{alt}m V:{vs:.1f}m/s T:{temp:.1f}°C"
        else:
            msg = f"[{ts}] [EVT] STATUS_UPDATE_NOMINAL SATS:11"

        self.event_log.appendPlainText(msg)
        self.packets.append(msg)
