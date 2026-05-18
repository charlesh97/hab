"""
HAB Ground Station — Cinematic Dark Theme Stylesheet
Inspired by the stratos dashboard design language.
"""

# ── Color Palette ──
BG_PRIMARY = "#0a0a0b"
BG_CARD = "rgba(255, 255, 255, 0.02)"
BG_CARD_HOVER = "rgba(255, 255, 255, 0.04)"
BG_ACTIVE = "rgba(249, 115, 22, 0.10)"

BORDER_WEAK = "rgba(255, 255, 255, 0.05)"
BORDER_CARD = "rgba(255, 255, 255, 0.10)"
BORDER_ACTIVE = "rgba(249, 115, 22, 0.30)"

TEXT_PRIMARY = "rgba(255, 255, 255, 0.87)"
TEXT_SECONDARY = "rgba(255, 255, 255, 0.60)"
TEXT_TERTIARY = "rgba(255, 255, 255, 0.40)"
TEXT_DIM = "rgba(255, 255, 255, 0.20)"

ACCENT_ORANGE = "#f97316"
ACCENT_SKY = "#0284c7"
ACCENT_EMERALD = "#10b981"
ACCENT_ROSE = "#f43f5e"

# ── Typography ──
FONT_FAMILY = "Inter, -apple-system, sans-serif"
FONT_MONO = "JetBrains Mono, SF Mono, monospace"

# ── Border Radii ──
RADIUS_CARD = "16px"
RADIUS_PILL = "9999px"
RADIUS_WINDOW = "32px"

# ── Shadows ──
SHADOW_CARD = "0 0 50px -15px rgba(14, 165, 233, 0.15)"
SHADOW_INNER = "inset 0 0 20px rgba(249, 115, 22, 0.05)"


def main_stylesheet() -> str:
    """Full application stylesheet."""
    return f"""
        QMainWindow {{
            background-color: {BG_PRIMARY};
            border-radius: {RADIUS_WINDOW};
        }}
        QWidget {{
            background-color: transparent;
            font-family: {FONT_FAMILY};
            color: {TEXT_PRIMARY};
        }}
        QTabWidget::pane {{
            background-color: {BG_PRIMARY};
            border: none;
            border-radius: {RADIUS_CARD};
        }}
        QTabBar::tab {{
            background-color: transparent;
            color: {TEXT_TERTIARY};
            padding: 10px 24px;
            margin: 4px 2px;
            border-radius: {RADIUS_PILL};
            font-size: 12px;
            font-weight: 500;
            letter-spacing: 0.5px;
            border: 1px solid transparent;
        }}
        QTabBar::tab:selected {{
            background-color: {BG_CARD};
            color: {TEXT_PRIMARY};
            border: 1px solid {BORDER_CARD};
        }}
        QTabBar::tab:hover {{
            background-color: {BG_CARD_HOVER};
            color: {TEXT_PRIMARY};
        }}
        QPushButton {{
            background-color: {BG_CARD};
            border: 1px solid {BORDER_CARD};
            border-radius: {RADIUS_PILL};
            padding: 8px 20px;
            color: {TEXT_PRIMARY};
            font-size: 12px;
            font-weight: 600;
            letter-spacing: 0.3px;
        }}
        QPushButton:hover {{
            background-color: {BG_CARD_HOVER};
            border: 1px solid rgba(255, 255, 255, 0.20);
        }}
        QPushButton:pressed {{
            background-color: rgba(255, 255, 255, 0.08);
        }}
        QPushButton:disabled {{
            background-color: rgba(255, 255, 255, 0.02);
            color: {TEXT_DIM};
            border: 1px solid {BORDER_WEAK};
        }}
        QPushButton#primary {{
            background-color: {ACCENT_ORANGE};
            border: none;
            color: white;
        }}
        QPushButton#primary:hover {{
            background-color: #ea580c;
        }}
        QPushButton#primary:disabled {{
            background-color: rgba(249, 115, 22, 0.3);
        }}
        QPushButton#danger {{
            background-color: rgba(244, 63, 94, 0.15);
            border: 1px solid rgba(244, 63, 94, 0.3);
            color: {ACCENT_ROSE};
        }}
        QPushButton#danger:hover {{
            background-color: rgba(244, 63, 94, 0.25);
        }}
        QLabel {{
            color: {TEXT_SECONDARY};
            font-size: 13px;
        }}
        QLabel#heading {{
            font-size: 18px;
            font-weight: 700;
            color: {TEXT_PRIMARY};
            letter-spacing: -0.3px;
        }}
        QLabel#subheading {{
            font-size: 11px;
            font-weight: 500;
            color: {TEXT_TERTIARY};
            letter-spacing: 1px;
            text-transform: uppercase;
        }}
        QLabel#value {{
            font-size: 24px;
            font-weight: 700;
            font-family: {FONT_MONO};
            color: {TEXT_PRIMARY};
        }}
        QLabel#unit {{
            font-size: 12px;
            font-family: {FONT_MONO};
            color: {TEXT_TERTIARY};
        }}
        QGroupBox {{
            background-color: {BG_CARD};
            border: 1px solid {BORDER_CARD};
            border-radius: {RADIUS_CARD};
            margin-top: 0px;
            padding: 16px;
            font-size: 12px;
            font-weight: 600;
            color: {TEXT_TERTIARY};
            letter-spacing: 0.5px;
        }}
        QGroupBox::title {{
            subcontrol-origin: margin;
            padding: 0 8px;
        }}
        QLineEdit, QPlainTextEdit {{
            background-color: rgba(255, 255, 255, 0.03);
            border: 1px solid {BORDER_CARD};
            border-radius: 8px;
            padding: 8px 12px;
            color: {TEXT_PRIMARY};
            font-family: {FONT_MONO};
            font-size: 12px;
            selection-background-color: rgba(249, 115, 22, 0.3);
        }}
        QLineEdit:focus, QPlainTextEdit:focus {{
            border: 1px solid {ACCENT_SKY};
        }}
        QPlainTextEdit {{
            background-color: rgba(0, 0, 0, 0.3);
            border: 1px solid {BORDER_WEAK};
        }}
        QSlider::groove:horizontal {{
            background: rgba(255, 255, 255, 0.08);
            height: 4px;
            border-radius: 2px;
        }}
        QSlider::handle:horizontal {{
            background: {ACCENT_SKY};
            width: 14px;
            height: 14px;
            margin: -5px 0;
            border-radius: 7px;
        }}
        QSlider::sub-page:horizontal {{
            background: {ACCENT_SKY};
            height: 4px;
            border-radius: 2px;
        }}
        QCheckBox {{
            spacing: 8px;
            color: {TEXT_SECONDARY};
            font-size: 12px;
        }}
        QCheckBox::indicator {{
            width: 16px;
            height: 16px;
            border-radius: 4px;
            border: 1px solid {BORDER_CARD};
            background: transparent;
        }}
        QCheckBox::indicator:checked {{
            background: {ACCENT_ORANGE};
            border-color: {ACCENT_ORANGE};
        }}
        QScrollBar:vertical {{
            background: transparent;
            width: 4px;
            margin: 0;
        }}
        QScrollBar::handle:vertical {{
            background: rgba(255, 255, 255, 0.1);
            border-radius: 2px;
            min-height: 20px;
        }}
        QScrollBar::handle:vertical:hover {{
            background: rgba(255, 255, 255, 0.2);
        }}
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
            height: 0;
        }}
        QScrollBar:horizontal {{
            background: transparent;
            height: 4px;
        }}
        QScrollBar::handle:horizontal {{
            background: rgba(255, 255, 255, 0.1);
            border-radius: 2px;
        }}
        QSplitter::handle {{
            background: rgba(255, 255, 255, 0.05);
            height: 1px;
        }}
        QListWidget {{
            background-color: rgba(0, 0, 0, 0.3);
            border: 1px solid {BORDER_WEAK};
            border-radius: 8px;
            padding: 4px;
            outline: none;
        }}
        QListWidget::item {{
            padding: 8px 12px;
            border-radius: 6px;
            color: {TEXT_SECONDARY};
        }}
        QListWidget::item:selected {{
            background-color: rgba(249, 115, 22, 0.15);
            color: {TEXT_PRIMARY};
        }}
        QListWidget::item:hover {{
            background-color: rgba(255, 255, 255, 0.03);
        }}
    """
