"""Framebuffer RGB565 e teclado evdev do CardputerZero (sem root, sem servidor gráfico).

O APPLaunch exporta APPLAUNCH_LINUX_FBDEV_DEVICE e APPLAUNCH_LINUX_KEYBOARD_DEVICE;
usamos esses caminhos quando presentes. O teclado é compartilhado (sem grab), como
recomenda o guia.
"""
import mmap
import os
import re
import time
from pathlib import Path

from PIL import Image, ImageChops

W, H = 320, 170

_G_LO = [(v & 0x1C) << 3 for v in range(256)]
_B_LO = [v >> 3 for v in range(256)]
_R_HI = [v & 0xF8 for v in range(256)]
_G_HI = [v >> 5 for v in range(256)]


def rgb565(im):
    """Empacota RGB888 -> RGB565 little-endian usando laços nativos do Pillow."""
    r, g, b = im.convert("RGB").split()
    lo = ImageChops.add(g.point(_G_LO), b.point(_B_LO))
    hi = ImageChops.add(r.point(_R_HI), g.point(_G_HI))
    return Image.merge("LA", (lo, hi)).tobytes()


class Framebuffer:
    def __init__(self, path=None):
        path = path or os.environ.get("APPLAUNCH_LINUX_FBDEV_DEVICE") or "/dev/fb0"
        real = Path(path).resolve()
        sysfs = Path("/sys/class/graphics") / real.name
        size = (sysfs / "virtual_size").read_text().strip()
        bpp = (sysfs / "bits_per_pixel").read_text().strip()
        if size != f"{W},{H}" or bpp != "16":
            raise OSError(f"framebuffer inesperado {size}@{bpp}bpp; esperado {W}x{H} RGB565")
        self.stride = int((sysfs / "stride").read_text())
        self.fd = os.open(real, os.O_RDWR)
        self.mem = mmap.mmap(self.fd, self.stride * H)
        self._last = None

    def draw(self, im):
        packed = rgb565(im)
        if packed == self._last:
            return
        self._last = packed
        row = W * 2
        if self.stride == row:
            self.mem[:] = packed
        else:
            for y in range(H):
                self.mem[y * self.stride:y * self.stride + row] = packed[y * row:(y + 1) * row]

    def close(self, clear=True):
        if clear:
            self.mem[:] = bytes(self.stride * H)
        self.mem.close()
        os.close(self.fd)


# --- teclado -----------------------------------------------------------------
LETTERS = {c: ch for codes, chars in [(range(2, 12), "1234567890"), (range(16, 26), "qwertyuiop"),
                                      (range(30, 39), "asdfghjkl"), (range(44, 51), "zxcvbnm")]
           for c, ch in zip(codes, chars)}
NAMED = {
    14: "BACK", 15: "TAB", 28: "ENTER", 57: " ", 96: "ENTER",
    103: "UP", 108: "DOWN", 105: "LEFT", 106: "RIGHT",
    102: "HOME", 107: "END", 104: "PGUP", 109: "PGDN", 111: "DEL",
    138: "HELP", 59: "HELP", 99: "SHOT", 210: "SHOT",
}
# Mapa oficial de símbolos do tca8418 (capítulo 5 do guia); lido do arquivo do sistema.
KEYMAP_FILE = "/usr/share/keymaps/tca8418_keypad_m5stack_keymap.map"
_SYM_NAMES = dict(zip(
    ("exclam at numbersign dollar percent asciicircum ampersand asterisk parenleft parenright "
     "asciitilde grave underscore minus plus equal bracketleft bracketright braceleft braceright "
     "semicolon colon apostrophe quotedbl less greater backslash bar comma period slash question").split(),
    "!@#$%^&*()~`_-+=[]{};:'\"<>\\|,./?"))
ESC_HOLD = 0.8


def load_symbols(path=KEYMAP_FILE):
    out = {}
    try:
        for line in Path(path).read_text().splitlines():
            m = re.match(r"\s*keycode\s+(\d+)\s*=\s*(\w+)", line)
            if m and m[2] in _SYM_NAMES:
                out[int(m[1])] = _SYM_NAMES[m[2]]
    except OSError:
        pass
    return out


class Keyboard:
    def __init__(self, path=None):
        import evdev
        self._evdev = evdev
        path = path or os.environ.get("APPLAUNCH_LINUX_KEYBOARD_DEVICE")
        if not path:
            for name in sorted(Path("/sys/class/input").glob("event*/device/name")):
                if "tca8418" in name.read_text().lower():
                    path = "/dev/input/" + name.parent.parent.name
                    break
        if not path:
            raise OSError("teclado tca8418 não encontrado")
        self.dev = evdev.InputDevice(path)
        self.builtin = "tca8418" in (self.dev.name or "").lower()
        self.symbols = load_symbols() if self.builtin else {}
        self.shift = set()
        self.esc_down = None
        self.esc_fired = False

    def fileno(self):
        return self.dev.fd

    def read(self):
        """Lê eventos pendentes (não bloqueante) e devolve tokens de tecla."""
        out = []
        try:
            for ev in self.dev.read():
                tok = self._translate(ev)
                if tok:
                    out.append(tok)
        except BlockingIOError:
            pass
        return out

    def poll_hold(self):
        if self.esc_down is not None and not self.esc_fired and time.monotonic() - self.esc_down >= ESC_HOLD:
            self.esc_fired = True
            return "QUIT"
        return None

    def _translate(self, ev):
        if ev.type != self._evdev.ecodes.EV_KEY:
            return None
        code, val = ev.code, ev.value
        if code in (42, 54):
            (self.shift.add if val else self.shift.discard)(code)
            return None
        if code == 1:  # Esc: toque = voltar, segurar = sair
            if val == 1:
                self.esc_down, self.esc_fired = time.monotonic(), False
            elif val == 0:
                fired, self.esc_down = self.esc_fired, None
                return None if fired else "ESC"
            return None
        if val not in (1, 2):
            return None
        if code in NAMED:
            tok = NAMED[code]
            # Enter segurado nunca repete ações.
            if val == 2 and tok not in ("UP", "DOWN", "LEFT", "RIGHT", "BACK"):
                return None
            return tok
        if code in self.symbols:  # camada Sym já selecionada pelo driver
            return self.symbols[code]
        ch = LETTERS.get(code)
        if ch and self.shift:
            ch = ch.upper()
        return ch

    def close(self):
        try:
            self.dev.close()
        except OSError:
            pass
