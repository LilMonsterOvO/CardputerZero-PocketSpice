"""CardputerZero 320x170 layout constants and cp0-keys nav geometry."""
from __future__ import annotations

SCREEN_W = 320
SCREEN_H = 170

# Reserved regions
HEADER_H = 18
NAVBAR_H = 26
CONTENT_TOP = HEADER_H
CONTENT_BOTTOM = SCREEN_H - NAVBAR_H
CONTENT_H = CONTENT_BOTTOM - CONTENT_TOP  # 126 px

# cp0-keys spec: bottom 5 key-aligned actions mapped to keys 4..8
# Recommended icon centers: X = 49, 105, 161, 217, 273; Y = 153; size 22x22
NAV_CENTERS_X = (49, 105, 161, 217, 273)
NAV_ICON_Y = 153
NAV_ICON_SIZE = 22
NAV_KEYS_LABELS = ("4", "5", "6", "7", "8")

# High-contrast dark oscilloscope palette
BG_COLOR = (14, 18, 24)
HEADER_BG = (24, 31, 42)
PANEL_BG = (20, 26, 35)
NAV_BG = (18, 23, 31)
GRID_COLOR = (40, 50, 66)
BORDER_COLOR = (62, 78, 102)
TEXT_PRIMARY = (235, 242, 250)
TEXT_MUTED = (148, 165, 188)
ACCENT_BLUE = (80, 178, 255)
ACCENT_GREEN = (74, 222, 128)
ACCENT_AMBER = (251, 191, 36)
ACCENT_RED = (248, 113, 113)
ACCENT_CYAN = (34, 211, 238)

CH_COLORS = (ACCENT_GREEN, ACCENT_AMBER, ACCENT_CYAN)
