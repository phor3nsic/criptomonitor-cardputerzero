"""Paletas (cores semânticas) e fontes. Todas as cores do app vêm daqui."""
import hashlib
import colorsys
import os
from pathlib import Path

from PIL import ImageFont

DARK = {
    "bg_top": (12, 16, 26), "bg_bot": (8, 10, 17),
    "surface": (20, 26, 39), "surface2": (30, 38, 56), "line": (40, 49, 68),
    "text": (236, 241, 248), "muted": (132, 145, 168), "faint": (78, 90, 112),
    "accent": (255, 184, 64), "accent_text": (20, 16, 8),
    "up": (46, 214, 128), "down": (255, 92, 108), "flat": (150, 160, 180),
    "ok": (46, 214, 128), "warn": (255, 184, 64), "err": (255, 92, 108),
    "overlay": (6, 8, 14),
}
LIGHT = {
    "bg_top": (246, 248, 252), "bg_bot": (234, 238, 245),
    "surface": (255, 255, 255), "surface2": (226, 232, 242), "line": (210, 217, 229),
    "text": (16, 22, 34), "muted": (88, 99, 120), "faint": (160, 170, 188),
    "accent": (214, 132, 0), "accent_text": (255, 255, 255),
    "up": (8, 150, 82), "down": (214, 44, 66), "flat": (100, 110, 130),
    "ok": (8, 150, 82), "warn": (214, 132, 0), "err": (214, 44, 66),
    "overlay": (20, 24, 34),
}
THEMES = {"dark": DARK, "light": LIGHT}

COIN_COLORS = {
    "BTC": (247, 147, 26), "ETH": (98, 126, 234), "SOL": (153, 69, 255), "BNB": (243, 186, 47),
    "XRP": (35, 140, 210), "ADA": (0, 90, 220), "DOGE": (194, 166, 51), "TRX": (235, 0, 41),
    "TON": (0, 136, 204), "AVAX": (232, 65, 66), "DOT": (230, 0, 122), "LINK": (42, 90, 218),
    "SHIB": (255, 161, 0), "LTC": (52, 93, 157), "BCH": (10, 193, 142), "UNI": (255, 0, 122),
    "PEPE": (60, 150, 60), "SUI": (77, 162, 255), "XLM": (20, 20, 20), "ATOM": (46, 49, 72),
    "NEAR": (0, 200, 150), "USDT": (38, 161, 123), "USDC": (39, 117, 202), "XMR": (255, 102, 0),
    "ARB": (40, 160, 240), "OP": (255, 4, 32), "APT": (40, 40, 40), "HBAR": (60, 60, 60),
}


def coin_color(sym):
    if sym in COIN_COLORS:
        return COIN_COLORS[sym]
    h = int(hashlib.md5(sym.encode()).hexdigest()[:4], 16) / 0xFFFF
    r, g, b = colorsys.hls_to_rgb(h, 0.52, 0.62)
    return int(r * 255), int(g * 255), int(b * 255)


def mix(a, b, t):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


# --- fontes ------------------------------------------------------------------
_FONT_DIRS = [os.environ.get("CRIPTO_FONT_DIR", ""), "/usr/share/fonts/truetype/nunito-sans",
              "/usr/share/fonts/truetype/dejavu"]
NUNITO = "NunitoSans-VariableFont_YTLC,opsz,wdth,wght.ttf"
DEJAVU, DEJAVU_BOLD = "DejaVuSans.ttf", "DejaVuSans-Bold.ttf"


def _find(name):
    for d in _FONT_DIRS:
        if d and (Path(d) / name).exists():
            return str(Path(d) / name)
    return None


def _nunito(size, weight, width=100):
    path = _find(NUNITO)
    if path:
        try:
            f = ImageFont.truetype(path, size)
            axes = {a["name"]: a for a in f.get_variation_axes()}
            values = []
            for a in f.get_variation_axes():
                n = a["name"]
                if n == b"Weight":
                    values.append(weight)
                elif n == b"Width":
                    values.append(width)
                elif n == b"Optical size":
                    values.append(min(a["maximum"], max(a["minimum"], size)))
                else:
                    values.append(a["default"])
            f.set_variation_by_axes(values)
            return f
        except (OSError, ValueError):
            pass
    return _dejavu(size, weight >= 600)


def _dejavu(size, bold=False):
    path = _find(DEJAVU_BOLD if bold else DEJAVU)
    if path:
        return ImageFont.truetype(path, size)
    return ImageFont.load_default(size)


class Fonts:
    def __init__(self):
        self.title = _nunito(14, 800)
        self.sym = _nunito(13, 800)
        self.name = _nunito(10, 500)
        self.price = _nunito(13, 750, 96)
        self.pill = _nunito(10, 800)
        self.small = _nunito(10, 650)
        self.tiny = _nunito(9, 700)
        self.big = _nunito(25, 850, 94)
        self.mid = _nunito(15, 800)
        self.avatar = _nunito(9, 900)
        self.avatar_s = _nunito(7, 900)
        self.input = _nunito(16, 800)
        self.key = _dejavu(8, True)
