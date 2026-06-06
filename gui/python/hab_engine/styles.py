"""
HAB Ground Station — Glassmorphism Cinematic Dark Theme
Matched to the STRATOS reference design language.
"""

# ── Color Palette (Reference-Matched) ──
BG_PRIMARY = "#0a0a0b"
BG_CARD = "rgba(18, 20, 22, 0.82)"       # Dark frosted glass base
BG_CARD_HOVER = "rgba(30, 32, 35, 0.85)" 
BG_ACTIVE = "rgba(249, 115, 22, 0.12)"   # Orange glow for active states

BORDER_CARD = "rgba(255, 255, 255, 0.06)"    # Very subtle
BORDER_CARD_HOVER = "rgba(255, 255, 255, 0.12)"
BORDER_ACTIVE = "rgba(249, 115, 22, 0.30)"

TEXT_PRIMARY = "rgba(255, 255, 255, 0.92)"
TEXT_SECONDARY = "rgba(255, 255, 255, 0.65)"
TEXT_TERTIARY = "rgba(255, 255, 255, 0.40)"
TEXT_DIM = "rgba(255, 255, 255, 0.20)"

ACCENT_ORANGE = "#f97316"
ACCENT_ORANGE_GLOW = "rgba(249, 115, 22, 0.15)"
ACCENT_SKY = "#0284c7"
ACCENT_EMERALD = "#10b981"
ACCENT_ROSE = "#f43f5e"

# ── Typography ──
FONT_SANS = "Inter, -apple-system, BlinkMacSystemFont, sans-serif"
FONT_MONO = "JetBrains Mono, SF Mono, Menlo, monospace"

# ── Border Radii ──
RADIUS_XL = "24px"   # Hero card
RADIUS_LG = "16px"   # Standard card
RADIUS_MD = "12px"   # Smaller cards / tiles
RADIUS_PILL = "9999px"


def main_stylesheet() -> str:
    """Full application stylesheet — glassmorphism cinematic dark."""
    return f"""
        QMainWindow, QWidget {{
            background-color: transparent;
            font-family: {FONT_SANS};
            color: {TEXT_PRIMARY};
        }}
        QTabWidget::pane {{
            background: transparent;
            border: none;
        }}
        QTabBar::tab {{
            background: transparent;
            color: {TEXT_TERTIARY};
            padding: 8px 20px;
            margin: 2px;
            border-radius: {RADIUS_PILL};
            font-size: 11px;
            font-weight: 500;
            letter-spacing: 0.3px;
        }}
        QTabBar::tab:selected {{
            background: {BG_CARD};
            color: {TEXT_PRIMARY};
            border: 1px solid {BORDER_CARD};
        }}
        QTabBar::tab:hover {{
            background: {BG_CARD_HOVER};
            color: {TEXT_PRIMARY};
        }}
        QPushButton {{
            background-color: {BG_CARD};
            border: 1px solid {BORDER_CARD};
            border-radius: {RADIUS_PILL};
            padding: 8px 20px;
            color: {TEXT_PRIMARY};
            font-size: 11px;
            font-weight: 600;
            letter-spacing: 0.3px;
        }}
        QPushButton:hover {{
            background-color: {BG_CARD_HOVER};
            border: 1px solid {BORDER_CARD_HOVER};
        }}
        QPushButton:disabled {{
            background-color: rgba(255, 255, 255, 0.02);
            color: {TEXT_DIM};
            border: 1px solid rgba(255, 255, 255, 0.03);
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
        QGroupBox {{
            background-color: {BG_CARD};
            border: 1px solid {BORDER_CARD};
            border-radius: {RADIUS_LG};
            margin-top: 0;
            padding: 14px;
            font-size: 12px;
            font-weight: 600;
            color: {TEXT_TERTIARY};
        }}
        QLineEdit, QPlainTextEdit {{
            background-color: rgba(255, 255, 255, 0.03);
            border: 1px solid {BORDER_CARD};
            border-radius: {RADIUS_MD};
            padding: 8px 12px;
            color: {TEXT_PRIMARY};
            font-family: {FONT_MONO};
            font-size: 11px;
            selection-background-color: {ACCENT_ORANGE_GLOW};
        }}
        QLineEdit:focus, QPlainTextEdit:focus {{
            border: 1px solid {ACCENT_SKY};
        }}
        QPlainTextEdit {{
            background-color: rgba(0, 0, 0, 0.4);
        }}
        QSlider::groove:horizontal {{
            background: rgba(255, 255, 255, 0.06);
            height: 3px;
            border-radius: 2px;
        }}
        QSlider::handle:horizontal {{
            background: {ACCENT_SKY};
            width: 12px;
            height: 12px;
            margin: -5px 0;
            border-radius: 6px;
        }}
        QSlider::sub-page:horizontal {{
            background: {ACCENT_SKY};
            height: 3px;
            border-radius: 2px;
        }}
        QCheckBox {{
            spacing: 6px;
            color: {TEXT_SECONDARY};
            font-size: 11px;
        }}
        QCheckBox::indicator {{
            width: 14px;
            height: 14px;
            border-radius: 4px;
            border: 1px solid {BORDER_CARD};
        }}
        QCheckBox::indicator:checked {{
            background: {ACCENT_ORANGE};
            border-color: {ACCENT_ORANGE};
        }}
        QScrollBar:vertical {{
            background: transparent;
            width: 3px;
        }}
        QScrollBar::handle:vertical {{
            background: rgba(255, 255, 255, 0.08);
            border-radius: 2px;
            min-height: 20px;
        }}
        QScrollBar::handle:vertical:hover {{
            background: rgba(255, 255, 255, 0.15);
        }}
        QScrollBar:horizontal {{
            background: transparent;
            height: 3px;
        }}
        QScrollBar::handle:horizontal {{
            background: rgba(255, 255, 255, 0.08);
            border-radius: 2px;
        }}
        QListWidget {{
            background-color: rgba(0, 0, 0, 0.4);
            border: 1px solid {BORDER_CARD};
            border-radius: {RADIUS_MD};
            padding: 4px;
        }}
        QListWidget::item {{
            padding: 6px 10px;
            border-radius: 6px;
            color: {TEXT_SECONDARY};
            font-size: 11px;
        }}
        QListWidget::item:selected {{
            background-color: {ACCENT_ORANGE_GLOW};
            color: {TEXT_PRIMARY};
        }}
        QListWidget::item:hover {{
            background-color: {BG_CARD_HOVER};
        }}
    """
