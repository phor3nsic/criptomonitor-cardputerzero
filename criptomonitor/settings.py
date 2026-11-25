"""Persistent settings (language, currency, theme, dashboard coins), written atomically."""
import json
import os
from pathlib import Path

DEFAULT_WATCH = [
    {"sym": "BTC", "name": "Bitcoin", "src": "binance"},
    {"sym": "ETH", "name": "Ethereum", "src": "binance"},
    {"sym": "SOL", "name": "Solana", "src": "binance"},
    {"sym": "BNB", "name": "BNB", "src": "binance"},
    {"sym": "XRP", "name": "XRP", "src": "binance"},
]
MAX_WATCH = 12


def _path():
    base = os.environ.get("XDG_CONFIG_HOME") or os.path.join(os.path.expanduser("~"), ".config")
    return Path(base) / "criptomonitor" / "settings.json"


def _valid_coin(c):
    return (isinstance(c, dict) and isinstance(c.get("sym"), str) and 0 < len(c["sym"]) <= 16
            and c.get("src") in ("binance", "coingecko")
            and (c["src"] == "binance" or isinstance(c.get("cg_id"), str)))


class Settings:
    def __init__(self):
        self.currency = "USD"
        self.theme = "dark"
        self.lang = "en"
        self.watch = [dict(c) for c in DEFAULT_WATCH]
        self.error = None

    @classmethod
    def load(cls):
        s = cls()
        try:
            data = json.loads(_path().read_text())
        except FileNotFoundError:
            return s
        except (OSError, ValueError):
            s.error = "settings_corrupt"
            return s
        if data.get("currency") in ("USD", "BRL"):
            s.currency = data["currency"]
        if data.get("lang") in ("en", "pt"):
            s.lang = data["lang"]
        if data.get("theme") in ("dark", "light"):
            s.theme = data["theme"]
        watch = data.get("watch")
        if isinstance(watch, list):
            s.watch = [{k: c[k] for k in ("sym", "name", "src", "cg_id") if k in c}
                       for c in watch if _valid_coin(c)][:MAX_WATCH]
        return s

    def save(self):
        p = _path()
        try:
            p.parent.mkdir(parents=True, exist_ok=True)
            tmp = p.with_suffix(".tmp")
            tmp.write_text(json.dumps({"lang": self.lang, "currency": self.currency, "theme": self.theme,
                                       "watch": self.watch}, ensure_ascii=False, indent=1))
            os.replace(tmp, p)
            return True
        except OSError:
            return False

    def is_watched(self, coin):
        return any(_same(c, coin) for c in self.watch)

    def toggle(self, coin):
        """Fixa/desafixa no painel. Retorna 'added', 'removed' ou 'full'."""
        for i, c in enumerate(self.watch):
            if _same(c, coin):
                del self.watch[i]
                return "removed"
        if len(self.watch) >= MAX_WATCH:
            return "full"
        self.watch.append({k: coin[k] for k in ("sym", "name", "src", "cg_id") if k in coin})
        return "added"


def _same(a, b):
    if a["src"] != b.get("src"):
        return False
    if a["src"] == "coingecko":
        return a.get("cg_id") == b.get("cg_id")
    return a["sym"] == b["sym"]
