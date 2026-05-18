"""
Reusable styled widgets for the HAB Ground Station.
Inspired by the stratos cinematic dashboard design.
"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame, QLabel, QVBoxLayout, QHBoxLayout,
    QPushButton, QWidget,
)


class GlassCard(QFrame):
    """A glassmorphism-styled card with rounded corners and subtle border."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(f"""
            GlassCard {{
                background-color: rgba(255, 255, 255, 0.02);
                border: 1px solid rgba(255, 255, 255, 0.10);
                border-radius: 16px;
                padding: 16px;
            }}
        """)
        # Don't create a layout here - let callers manage it
    
    def vlayout(self, margins=16):
        """Get or create a vertical layout for this card."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(margins, margins, margins, margins)
        layout.setSpacing(8)
        return layout

    def hlayout(self, margins=16):
        """Get or create a horizontal layout for this card."""
        layout = QHBoxLayout(self)
        layout.setContentsMargins(margins, margins, margins, margins)
        layout.setSpacing(8)
        return layout


class MetricTile(QFrame):
    """A single metric display: label, value, unit. Like StatTile in the reference."""

    def __init__(self, label: str, value: str = "---", unit: str = "",
                 accent_color: str = None, parent=None):
        super().__init__(parent)
        self.setStyleSheet(f"""
            MetricTile {{
                background-color: rgba(255, 255, 255, 0.02);
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 12px;
                padding: 12px;
            }}
        """)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(4)

        self.label_widget = QLabel(label)
        self.label_widget.setStyleSheet("""
            font-size: 10px;
            font-weight: 700;
            letter-spacing: 1px;
            text-transform: uppercase;
            color: rgba(255, 255, 255, 0.40);
        """)
        layout.addWidget(self.label_widget)

        value_row = QHBoxLayout()
        value_row.setSpacing(4)

        self.value_widget = QLabel(value)
        color = accent_color or "rgba(255, 255, 255, 0.87)"
        self.value_widget.setStyleSheet(f"""
            font-size: 22px;
            font-weight: 700;
            font-family: 'JetBrains Mono', 'SF Mono', monospace;
            color: {color};
        """)
        value_row.addWidget(self.value_widget)

        if unit:
            self.unit_widget = QLabel(unit)
            self.unit_widget.setStyleSheet("""
                font-size: 11px;
                font-family: 'JetBrains Mono', 'SF Mono', monospace;
                color: rgba(255, 255, 255, 0.35);
                padding-top: 4px;
            """)
            value_row.addWidget(self.unit_widget)

        value_row.addStretch()
        layout.addLayout(value_row)

    def set_value(self, value: str):
        self.value_widget.setText(value)


class StatusPill(QFrame):
    """Small pill-shaped status indicator with label."""

    def __init__(self, label: str = "", status: str = "NOMINAL", parent=None):
        super().__init__(parent)
        colors = {
            "NOMINAL": ("#10b981", "rgba(16, 185, 129, 0.1)", "rgba(16, 185, 129, 0.2)"),
            "DEGRADED": ("#f59e0b", "rgba(245, 158, 11, 0.1)", "rgba(245, 158, 11, 0.2)"),
            "OFFLINE": ("#f43f5e", "rgba(244, 63, 94, 0.1)", "rgba(244, 63, 94, 0.2)"),
            "ACTIVE": ("#0284c7", "rgba(2, 132, 199, 0.1)", "rgba(2, 132, 199, 0.2)"),
            "IDLE": ("rgba(255,255,255,0.4)", "rgba(255,255,255,0.02)", "rgba(255,255,255,0.05)"),
        }
        fg, bg, border = colors.get(status, colors["NOMINAL"])

        self.setStyleSheet(f"""
            StatusPill {{
                background-color: {bg};
                border: 1px solid {border};
                border-radius: 9999px;
                padding: 4px 12px;
            }}
        """)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 4, 10, 4)
        layout.setSpacing(6)

        dot = QLabel("●")
        dot.setStyleSheet(f"color: {fg}; font-size: 8px;")
        layout.addWidget(dot)

        if label:
            lbl = QLabel(label)
            lbl.setStyleSheet(f"""
                font-size: 10px;
                font-weight: 600;
                color: {fg};
                letter-spacing: 0.5px;
            """)
            layout.addWidget(lbl)


class NavPill(QPushButton):
    """Pill-shaped navigation button like the reference TopBar."""

    def __init__(self, label: str, is_active: bool = False, parent=None):
        super().__init__(label, parent)
        self._active = is_active
        self.setCursor(Qt.PointingHandCursor)
        self._update_style()

    def set_active(self, active: bool):
        self._active = active
        self._update_style()

    def _update_style(self):
        if self._active:
            self.setStyleSheet(f"""
                QPushButton {{
                    background-color: rgba(255, 255, 255, 0.08);
                    color: white;
                    border: 1px solid rgba(255, 255, 255, 0.10);
                    border-radius: 9999px;
                    padding: 8px 24px;
                    font-size: 11px;
                    font-weight: 400;
                    letter-spacing: 0.8px;
                }}
            """)
        else:
            self.setStyleSheet(f"""
                QPushButton {{
                    background-color: transparent;
                    color: rgba(255, 255, 255, 0.50);
                    border: 1px solid transparent;
                    border-radius: 9999px;
                    padding: 8px 24px;
                    font-size: 11px;
                    font-weight: 400;
                    letter-spacing: 0.8px;
                }}
                QPushButton:hover {{
                    background-color: rgba(255, 255, 255, 0.04);
                    color: rgba(255, 255, 255, 0.80);
                }}
            """)


class PrimaryButton(QPushButton):
    """Orange accent primary action button."""

    def __init__(self, label: str, parent=None):
        super().__init__(label, parent)
        self.setCursor(Qt.PointingHandCursor)
        self.setStyleSheet(f"""
            QPushButton {{
                background-color: #f97316;
                border: none;
                border-radius: 9999px;
                padding: 10px 24px;
                color: white;
                font-size: 12px;
                font-weight: 600;
                letter-spacing: 0.3px;
            }}
            QPushButton:hover {{
                background-color: #ea580c;
            }}
            QPushButton:pressed {{
                background-color: #d97706;
            }}
            QPushButton:disabled {{
                background-color: rgba(249, 115, 22, 0.3);
                color: rgba(255, 255, 255, 0.4);
            }}
        """)


class TopBar(QWidget):
    """Cinematic top navigation bar matching the reference design."""

    def __init__(self, title: str = "HAB-1 Stratos", subtitle: str = "ID: #521514",
                 parent=None):
        super().__init__(parent)
        self.setFixedHeight(72)
        self.setStyleSheet("background-color: transparent;")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(32, 0, 32, 0)

        # Left: Logo & Brand
        left = QHBoxLayout()
        logo = QLabel("⦿")
        logo.setStyleSheet(f"""
            font-size: 20px;
            color: white;
            background-color: rgba(255,255,255,0.08);
            border: 1px solid rgba(255,255,255,0.10);
            border-radius: 9999px;
            padding: 6px 10px;
        """)
        left.addWidget(logo)
        left.addSpacing(12)

        brand = QLabel(title)
        brand.setStyleSheet("""
            font-size: 13px;
            font-weight: 300;
            color: white;
            letter-spacing: 2px;
        """)
        left.addWidget(brand)
        left.addStretch()
        layout.addLayout(left, 1)

        # Center: Nav pills (filled by main window)
        self.nav_layout = QHBoxLayout()
        self.nav_layout.setSpacing(4)
        layout.addLayout(self.nav_layout, 2)

        # Right: Status
        right = QHBoxLayout()
        right.addStretch()
        self.phase_label = StatusPill("ASCENT", "ACTIVE")
        right.addWidget(self.phase_label)
        layout.addLayout(right, 1)

    def set_nav_pills(self, pills: list):
        """Replace navigation pills."""
        for i in reversed(range(self.nav_layout.count())):
            item = self.nav_layout.itemAt(i)
            if item and item.widget():
                item.widget().deleteLater()
        for label, active in pills:
            self.nav_layout.addWidget(NavPill(label, active))


class Divider(QFrame):
    """Thin horizontal divider."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(1)
        self.setStyleSheet("background-color: rgba(255, 255, 255, 0.06);")
