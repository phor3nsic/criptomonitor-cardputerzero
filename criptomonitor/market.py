"""Dados de mercado: Binance (REST público, principal) com CoinGecko como reserva.

Nenhuma chave de API. Toda rede roda em threads de trabalho limitadas; a UI só lê
os dicionários publicados aqui (atribuições atômicas sob o GIL) e é acordada via
callback `on_change`.
"""
import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import requests

from . import __version__

BINANCE = "https://api.binance.com/api/v3"
COINGECKO = "https://api.coingecko.com/api/v3"
HEADERS = {"User-Agent": f"CriptoMonitor/{__version__} (CardputerZero)", "Accept": "application/json"}
TIMEOUT = (6, 12)

# key, binance interval, limit, coingecko days, seconds covered
PERIODS = [
    ("1H", "1m", 60, 1, 3600),
    ("24H", "15m", 96, 1, 86400),
    ("7D", "1h", 168, 7, 7 * 86400),
    ("30D", "4h", 180, 30, 30 * 86400),
    ("1A", "1d", 365, 365, 365 * 86400),
]
PERIOD_KEYS = [p[0] for p in PERIODS]

NAMES = {
    "BTC": "Bitcoin", "ETH": "Ethereum", "SOL": "Solana", "BNB": "BNB", "XRP": "XRP",
    "ADA": "Cardano", "DOGE": "Dogecoin", "TRX": "TRON", "TON": "Toncoin", "AVAX": "Avalanche",
    "DOT": "Polkadot", "LINK": "Chainlink", "MATIC": "Polygon", "POL": "Polygon", "SHIB": "Shiba Inu",
    "LTC": "Litecoin", "BCH": "Bitcoin Cash", "UNI": "Uniswap", "NEAR": "NEAR Protocol",
    "XLM": "Stellar", "ATOM": "Cosmos", "APT": "Aptos", "ARB": "Arbitrum", "OP": "Optimism",
    "SUI": "Sui", "PEPE": "Pepe", "FIL": "Filecoin", "ETC": "Ethereum Classic", "HBAR": "Hedera",
    "ICP": "Internet Computer", "INJ": "Injective", "RENDER": "Render", "AAVE": "Aave",
    "TAO": "Bittensor", "WIF": "dogwifhat", "BONK": "Bonk", "FET": "Artificial Superintelligence",
    "SEI": "Sei", "TIA": "Celestia", "ALGO": "Algorand", "VET": "VeChain", "XMR": "Monero",
    "MKR": "Maker", "RUNE": "THORChain", "SAND": "The Sandbox", "MANA": "Decentraland",
    "AXS": "Axie Infinity", "GALA": "Gala", "FLOKI": "Floki", "JUP": "Jupiter", "ENA": "Ethena",
    "TRUMP": "Official Trump", "HYPE": "Hyperliquid", "USDT": "Tether", "USDC": "USD Coin",
    "CRV": "Curve", "LDO": "Lido DAO", "STX": "Stacks", "IMX": "Immutable", "KAS": "Kaspa",
    "WLD": "Worldcoin", "ONDO": "Ondo", "PENGU": "Pudgy Penguins", "S": "Sonic", "EOS": "EOS",
}
POPULAR = ["BTC", "ETH", "SOL", "XRP", "DOGE", "ADA", "PEPE", "LINK", "AVAX", "SUI"]
_EXCLUDE_SUFFIX = ("UP", "DOWN", "BULL", "BEAR")


class Market:
    def __init__(self, on_change=lambda: None):
        self.on_change = on_change
        self._pool = ThreadPoolExecutor(max_workers=3, thread_name_prefix="net")
        self._local = threading.local()
        self._inflight = set()
        self._lock = threading.Lock()
        self.tickers = {}        # sym -> dict(price, change, high, low, volume, ts)
        self.sparks = {}         # sym -> (ts, [closes])
        self.charts = {}         # (sym, period) -> dict(ts, times, closes)
        self.usd_brl = None
        self.binance = set()     # símbolos base com par USDT
        self.all_prices = {}     # sym -> preço USD (lista completa Binance)
        self.searches = {}       # query -> list[coin]
        self.last_ok = 0.0
        self.last_error = None
        self.closed = False

    # -- infraestrutura -------------------------------------------------
    def _session(self):
        s = getattr(self._local, "session", None)
        if s is None:
            s = requests.Session()
            s.headers.update(HEADERS)
            self._local.session = s
        return s

    def _get(self, url, **params):
        r = self._session().get(url, params=params or None, timeout=TIMEOUT)
        r.raise_for_status()
        return r.json()

    def submit(self, key, fn, *args):
        """Agenda um job, ignorando duplicatas já em andamento. Retorna True se agendou."""
        with self._lock:
            if self.closed or key in self._inflight:
                return False
            self._inflight.add(key)

        def run():
            try:
                fn(*args)
                self.last_ok = time.time()
                self.last_error = None
            except requests.RequestException as exc:
                self.last_error = _friendly(exc)
            except (ValueError, KeyError, TypeError, IndexError):
                self.last_error = "err_bad_reply"
            finally:
                with self._lock:
                    self._inflight.discard(key)
                if not self.closed:
                    self.on_change()

        self._pool.submit(run)
        return True

    def busy(self, key):
        with self._lock:
            return key in self._inflight

    def shutdown(self):
        self.closed = True
        self._pool.shutdown(wait=False, cancel_futures=True)

    # -- jobs -----------------------------------------------------------
    def load_symbols(self):
        data = self._get(f"{BINANCE}/ticker/price")
        prices, syms = {}, set()
        for item in data:
            s = item.get("symbol", "")
            if not s.endswith("USDT"):
                continue
            base = s[:-4]
            if not base or base.endswith(_EXCLUDE_SUFFIX) and len(base) > 4:
                continue
            try:
                p = float(item["price"])
            except (KeyError, ValueError):
                continue
            if p <= 0:
                continue  # par deslistado
            syms.add(base)
            prices[base] = p
        self.binance, self.all_prices = syms, prices

    def refresh_rate(self):
        data = self._get(f"{BINANCE}/ticker/price", symbol="USDTBRL")
        self.usd_brl = float(data["price"])

    def refresh_tickers(self, coins):
        now = time.time()
        bn = [c["sym"] for c in coins if c.get("src", "binance") == "binance"]
        cg = [c for c in coins if c.get("src") == "coingecko" and c.get("cg_id")]
        if bn:
            symbols = json.dumps([s + "USDT" for s in bn], separators=(",", ":"))
            data = self._get(f"{BINANCE}/ticker/24hr", symbols=symbols)
            for t in data:
                sym = t["symbol"][:-4]
                self.tickers[sym] = {
                    "price": float(t["lastPrice"]), "change": float(t["priceChangePercent"]),
                    "high": float(t["highPrice"]), "low": float(t["lowPrice"]),
                    "volume": float(t["quoteVolume"]), "ts": now,
                }
        if cg:
            ids = ",".join(c["cg_id"] for c in cg)
            data = self._get(f"{COINGECKO}/simple/price", ids=ids, vs_currencies="usd",
                             include_24hr_change="true", include_24hr_vol="true")
            for c in cg:
                d = data.get(c["cg_id"])
                if not d or d.get("usd") is None:
                    continue
                prev = self.tickers.get(c["sym"], {})
                self.tickers[c["sym"]] = {
                    "price": float(d["usd"]), "change": float(d.get("usd_24h_change") or 0.0),
                    "high": prev.get("high"), "low": prev.get("low"),
                    "volume": d.get("usd_24h_vol"), "ts": now,
                }

    def refresh_spark(self, coin):
        times, closes = self._series(coin, "24H", spark=True)
        self.sparks[coin["sym"]] = (time.time(), closes)

    def refresh_chart(self, coin, period):
        times, closes = self._series(coin, period)
        self.charts[(coin["sym"], period)] = {"ts": time.time(), "times": times, "closes": closes}
        # Um gráfico de 24h também serve de sparkline.
        if period == "24H":
            self.sparks[coin["sym"]] = (time.time(), closes)

    def _series(self, coin, period, spark=False):
        key, interval, limit, days, span = next(p for p in PERIODS if p[0] == period)
        if spark:
            interval, limit = "1h", 24
        if coin.get("src", "binance") == "binance":
            rows = self._get(f"{BINANCE}/klines", symbol=coin["sym"] + "USDT", interval=interval, limit=limit)
            return [r[6] / 1000 for r in rows], [float(r[4]) for r in rows]
        data = self._get(f"{COINGECKO}/coins/{coin['cg_id']}/market_chart", vs_currency="usd", days=days)
        pts = data.get("prices") or []
        cutoff = time.time() - span
        pts = [p for p in pts if p[0] / 1000 >= cutoff] or pts
        if spark and len(pts) > 48:
            step = len(pts) / 48
            pts = [pts[int(i * step)] for i in range(48)] + [pts[-1]]
        return [p[0] / 1000 for p in pts], [float(p[1]) for p in pts]

    def search(self, query):
        data = self._get(f"{COINGECKO}/search", query=query)
        out, seen_bn = [], set()
        for c in (data.get("coins") or [])[:12]:
            sym = (c.get("symbol") or "").upper()
            if not sym:
                continue
            on_bn = sym in self.binance and sym not in seen_bn
            if on_bn:
                seen_bn.add(sym)
            out.append({"sym": sym, "name": c.get("name") or sym, "rank": c.get("market_cap_rank"),
                        "src": "binance" if on_bn else "coingecko", "cg_id": c.get("id")})
        self.searches[query] = out


def coin_for(sym, name=None):
    return {"sym": sym, "name": name or NAMES.get(sym, sym), "src": "binance"}


def local_matches(market, query, limit=12):
    q = query.upper()
    if not q:
        return [coin_for(s) for s in POPULAR if not market.binance or s in market.binance][:limit]
    hits = [s for s in market.binance if s.startswith(q)]
    hits.sort(key=lambda s: (s != q, s not in NAMES, len(s), s))
    return [coin_for(s) for s in hits[:limit]]


def merged_results(market, query, limit=12):
    """Resultados da CoinGecko (com nome/rank) + prefixos locais da Binance."""
    q = query.upper()
    remote = market.searches.get(q.lower(), [])
    out, seen = [], set()
    # Correspondência exata primeiro: é o que quem digita uma abreviação espera.
    exact = [c for c in remote if c["sym"] == q]
    for c in exact + [c for c in remote if c["sym"] != q]:
        k = (c["sym"], c["src"], c.get("cg_id") if c["src"] == "coingecko" else None)
        if k in seen:
            continue
        seen.add(k)
        out.append(c)
    have_bn = {c["sym"] for c in out if c["src"] == "binance"}
    local = local_matches(market, q, limit)
    if not remote:
        local.sort(key=lambda c: c["sym"] != q)
        return local[:limit]
    for c in local:
        if c["sym"] not in have_bn:
            out.append(c)
    return out[:limit]


def _friendly(exc):
    if isinstance(exc, requests.HTTPError) and exc.response is not None:
        code = exc.response.status_code
        if code in (429, 451, 403):
            return f"err_{code}"
        return f"err_http:{code}"
    if isinstance(exc, requests.Timeout):
        return "err_timeout"
    if isinstance(exc, requests.ConnectionError):
        return "err_offline"
    return "err_network"
