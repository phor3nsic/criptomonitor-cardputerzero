"""UI state, key handling and rendering (Pillow, 320x170)."""
import math
import os
import time

from PIL import Image, ImageChops, ImageDraw

from . import fmt
from .i18n import period_label, tr
from .market import PERIOD_KEYS, merged_results
from .settings import Settings
from .theme import THEMES, Fonts, coin_color, mix

W, H = 320, 170
HEADER_H = 20
FOOTER_Y = 156
LIST_Y = 23
ROW_H = 26
VISIBLE = 5
S_ROW_H = 21
S_LIST_Y = 49

TICKER_EVERY = 15
SPARK_TTL = 300
RATE_TTL = 300
CHART_TTL = {"1H": 30, "24H": 60, "7D": 300, "30D": 900, "1A": 1800}
SEARCH_DEBOUNCE = 0.45
CHART_PAD = 11


def _tw(font, text):
    return font.getlength(text)


def ellipsize(font, text, max_w):
    if _tw(font, text) <= max_w:
        return text
    while text and _tw(font, text + "…") > max_w:
        text = text[:-1]
    return text + "…"


class App:
    def __init__(self, market, settings=None, fonts=None, wake=lambda: None):
        self.market = market
        self.settings = settings or Settings.load()
        self.f = fonts or Fonts()
        self.wake = wake
        self.screen = "dash"
        self.help = False
        self.exit = False
        self.dirty = True
        self.sel = 0
        self.scroll = 0
        self.query = ""
        self.typed_at = 0.0
        self.searched = None
        self.s_sel = 0
        self.s_scroll = 0
        self.coin = None
        self.coin_list = []
        self.came_from = "dash"
        self.period = "24H"
        self.cursor = None
        self.toast_text = None
        self.toast_until = 0.0
        self.shot_dir = os.environ.get("CRIPTO_SHOT_DIR") or os.path.join(
            os.path.expanduser("~"), "Pictures", "CriptoMonitor")
        self._last_tick = 0.0
        self._last_rate = 0.0
        self._last_sym_try = -999.0
        self._last_minute = None
        self._blink = 0
        self._cache = {}
        self._bg = {}
        self._seen_error = None
        if self.settings.error:
            self.toast(self.t(self.settings.error))

    # ------------------------------------------------------------ helpers
    @property
    def c(self):
        return THEMES[self.settings.theme]

    def t(self, key, **kw):
        return tr(self.settings.lang, key, **kw)

    def toast(self, text, secs=2.2):
        self.toast_text, self.toast_until = text, time.time() + secs
        self.dirty = True

    def currency(self):
        if self.settings.currency == "BRL" and self.market.usd_brl:
            return "BRL"
        return "USD"

    def conv(self, v):
        if v is None:
            return None
        return v * self.market.usd_brl if self.currency() == "BRL" else v

    def watched_coins(self):
        return self.settings.watch

    def search_results(self):
        return merged_results(self.market, self.query)

    # ------------------------------------------------------------ teclado
    def key(self, k):
        self.dirty = True
        if k == "QUIT":
            self.exit = True
            return
        if k == "SHOT":
            self.screenshot()
            return
        if self.help:
            self.help = False
            return
        if k in ("HELP", "?"):
            self.help = True
            return
        getattr(self, f"_key_{self.screen}")(k)

    def _global(self, k):
        if k == "m":
            self.settings.currency = "BRL" if self.settings.currency == "USD" else "USD"
            if self.settings.currency == "BRL" and not self.market.usd_brl:
                self.market.submit("rate", self.market.refresh_rate)
                self._last_rate = time.time()
            self._save()
            self.toast(self.t("currency_brl" if self.settings.currency == "BRL" else "currency_usd"))
            return True
        if k == "l":
            self.settings.lang = "pt" if self.settings.lang == "en" else "en"
            fmt.STYLE = self.settings.lang
            self._cache.clear()
            self._save()
            self.toast(self.t("language"))
            return True
        if k == "t":
            self.settings.theme = "light" if self.settings.theme == "dark" else "dark"
            self._cache.clear()
            self._save()
            return True
        if k == "r":
            self._last_tick = 0
            self.market.sparks.clear()
            if self.coin:
                self.market.charts.pop((self.coin["sym"], self.period), None)
            self.toast(self.t("refreshing"), 1.2)
            return True
        return False

    def _save(self):
        if not self.settings.save():
            self.toast(self.t("save_failed"))

    def _key_dash(self, k):
        n = len(self.watched_coins())
        if k in ("UP", "f") and n:
            self.sel = (self.sel - 1) % n
        elif k in ("DOWN", "x") and n:
            self.sel = (self.sel + 1) % n
        elif k == "HOME":
            self.sel = 0
        elif k == "END" and n:
            self.sel = n - 1
        elif k in ("ENTER", "RIGHT", "c") and n:
            self.open_detail(self.watched_coins(), self.sel, "dash")
        elif k in ("s", "/", " ", "TAB"):
            self.screen = "search"
            self.s_sel = 0
        elif k == "ESC":
            self.exit = True
        else:
            self._global(k)
        self._fix_scroll()

    def _fix_scroll(self):
        n = len(self.watched_coins())
        self.sel = max(0, min(self.sel, n - 1)) if n else 0
        if self.sel < self.scroll:
            self.scroll = self.sel
        elif self.sel >= self.scroll + VISIBLE:
            self.scroll = self.sel - VISIBLE + 1
        self.scroll = max(0, min(self.scroll, max(0, n - VISIBLE)))

    def _key_search(self, k):
        results = self.search_results()
        n = len(results)
        if k == "ESC":
            self.screen = "dash"
        elif k == "UP" and n:
            self.s_sel = (self.s_sel - 1) % n
        elif k == "DOWN" and n:
            self.s_sel = (self.s_sel + 1) % n
        elif k == "ENTER" and n:
            self.open_detail(results, min(self.s_sel, n - 1), "search")
        elif k == "BACK":
            self.query = self.query[:-1]
            self._typed()
        elif k == "DEL":
            self.query = ""
            self._typed()
        elif len(k) == 1 and k.isalnum() and len(self.query) < 12:
            self.query += k.upper()
            self._typed()
        n = len(self.search_results())
        self.s_sel = max(0, min(self.s_sel, n - 1)) if n else 0
        if self.s_sel < self.s_scroll:
            self.s_scroll = self.s_sel
        elif self.s_sel >= self.s_scroll + VISIBLE:
            self.s_scroll = self.s_sel - VISIBLE + 1

    def _typed(self):
        self.typed_at = time.time()
        self.s_sel = self.s_scroll = 0

    def open_detail(self, coins, idx, origin):
        self.coin_list = [dict(c) for c in coins]
        self.coin = self.coin_list[idx]
        self.came_from = origin
        self.screen = "detail"
        self.cursor = None
        self._last_tick = 0  # busca o ticker da moeda nova já

    def _series(self):
        if not self.coin:
            return None
        return self.market.charts.get((self.coin["sym"], self.period))

    def _key_detail(self, k):
        series = self._series()
        n = len(series["closes"]) if series else 0
        step = max(1, n // 80)
        if k == "ESC":
            if self.cursor is not None:
                self.cursor = None
            else:
                self.screen = self.came_from
        elif k in ("LEFT", "z") and n:
            self.cursor = n - 1 if self.cursor is None else max(0, self.cursor - step)
        elif k in ("RIGHT", "c") and n:
            self.cursor = n - 1 if self.cursor is None else min(n - 1, self.cursor + step)
        elif k == "HOME" and n:
            self.cursor = 0
        elif k == "END" and n:
            self.cursor = n - 1
        elif len(k) == 1 and k in "12345":
            self._set_period(PERIOD_KEYS[int(k) - 1])
        elif k == "TAB":
            i = PERIOD_KEYS.index(self.period)
            self._set_period(PERIOD_KEYS[(i + 1) % len(PERIOD_KEYS)])
        elif k in ("UP", "f", "DOWN", "x") and len(self.coin_list) > 1:
            i = next((j for j, c in enumerate(self.coin_list) if c is self.coin), 0)
            i = (i + (-1 if k in ("UP", "f") else 1)) % len(self.coin_list)
            self.coin, self.cursor, self._last_tick = self.coin_list[i], None, 0
            if self.came_from == "dash":
                self.sel = i
                self._fix_scroll()
        elif k == "p":
            result = self.settings.toggle(self.coin)
            if result == "full":
                self.toast(self.t("board_full"))
            else:
                self._save()
                self.toast(self.t("pinned" if result == "added" else "unpinned", s=self.coin["sym"]))
                self._fix_scroll()
        else:
            self._global(k)

    def _set_period(self, p):
        if p != self.period:
            self.period, self.cursor = p, None

    def screenshot(self):
        try:
            os.makedirs(self.shot_dir, exist_ok=True)
            path = os.path.join(self.shot_dir, time.strftime("cm-%Y%m%d-%H%M%S.png"))
            self.render(toast=False).save(path)
            self.toast(self.t("shot_saved"))
            return path
        except OSError:
            self.toast(self.t("shot_failed"))
            return None

    # ------------------------------------------------------------ agenda
    def tick(self):
        now = time.time()
        m = self.market
        if not m.binance and now - self._last_sym_try > 30:
            self._last_sym_try = now
            m.submit("symbols", m.load_symbols)
        coins = list(self.watched_coins())
        if self.coin and not self.settings.is_watched(self.coin):
            coins.append(self.coin)
        if coins and now - self._last_tick >= TICKER_EVERY:
            if m.submit("tickers", m.refresh_tickers, coins):
                self._last_tick = now
        if self.settings.currency == "BRL" and now - self._last_rate >= RATE_TTL:
            if m.submit("rate", m.refresh_rate):
                self._last_rate = now
        if self.screen == "dash":
            started = 0
            vis = self.watched_coins()[self.scroll:self.scroll + VISIBLE]
            for c in vis:
                sp = m.sparks.get(c["sym"])
                if (not sp or now - sp[0] > SPARK_TTL) and started < 2:
                    if m.submit(("spark", c["sym"]), m.refresh_spark, c):
                        started += 1
        if self.screen == "detail" and self.coin:
            s = self._series()
            if not s or now - s["ts"] > CHART_TTL[self.period]:
                m.submit(("chart", self.coin["sym"], self.period), m.refresh_chart, self.coin, self.period)
        if self.screen == "search" and self.query and self.query != self.searched \
                and now - self.typed_at >= SEARCH_DEBOUNCE:
            q = self.query.lower()
            if q in m.searches or m.submit(("search", q), m.search, q):
                self.searched = self.query
        # Redesenhos periódicos: relógio, cursor piscante, spinner, toast.
        minute = int(now // 60)
        if minute != self._last_minute:
            self._last_minute, self.dirty = minute, True
        if self.toast_text and now > self.toast_until:
            self.toast_text, self.dirty = None, True
        blink = int(now * 2.5)
        if blink != self._blink and (self.screen in ("search", "detail") or self._loading()):
            self._blink, self.dirty = blink, True
        if m.last_error and m.last_error != self._seen_error:
            self._seen_error = m.last_error
            self.toast(self.t(m.last_error), 3)
        elif not m.last_error:
            self._seen_error = None

    def _loading(self):
        if self.screen == "detail":
            return self._series() is None
        if self.screen == "search":
            return self.market.busy(("search", self.query.lower()))
        return any(c["sym"] not in self.market.tickers for c in self.watched_coins()[:VISIBLE])

    # ------------------------------------------------------------ render
    def render(self, toast=True):
        fmt.STYLE = self.settings.lang
        c = self.c
        im = self._background().copy()
        d = ImageDraw.Draw(im)
        getattr(self, f"_draw_{self.screen}")(im, d)
        if toast and self.toast_text:
            self._draw_toast(d)
        if self.help:
            im = self._draw_help(im)
        return im

    def _background(self):
        key = self.settings.theme
        if key not in self._bg:
            c = self.c
            grad = Image.linear_gradient("L").resize((W, H))
            top = Image.new("RGB", (W, H), c["bg_top"])
            bot = Image.new("RGB", (W, H), c["bg_bot"])
            self._bg[key] = Image.composite(bot, top, grad)
        return self._bg[key]

    # ---- peças comuns
    def _header(self, d, title, sub=None, coin=None):
        c, f = self.c, self.f
        x = 6
        if coin:
            self._avatar(d, 13, 10, 8, coin["sym"])
            x = 25
        else:
            for i, hgt in enumerate((5, 8, 12)):
                d.rounded_rectangle((x + i * 4, 15 - hgt, x + i * 4 + 2, 15), 1, fill=c["accent"])
            x = 21
        d.text((x, 2), title, font=f.title, fill=c["text"])
        x += _tw(f.title, title) + 5
        right = self._status(d)
        if sub:
            d.text((x, 5), ellipsize(f.name, sub, right - x - 6), font=f.name, fill=c["muted"])
            x += min(_tw(f.name, sub), right - x - 6) + 4
        if coin and self.settings.is_watched(coin) and x < right - 12:
            self._star(d, x + 4, 10, 4, c["accent"])

    def _status(self, d):
        """Moeda, indicador de conexão e relógio no canto direito. Retorna x livre."""
        c, f, m = self.c, self.f, self.market
        x = W - 6
        t = fmt.clock()
        x -= _tw(f.small, t)
        d.text((x, 4), t, font=f.small, fill=c["muted"])
        now = time.time()
        if m.last_error and (now - m.last_ok > 60):
            dot = c["err"]
        elif m.last_ok and now - m.last_ok < 60:
            dot = c["ok"]
        else:
            dot = c["warn"]
        x -= 9
        d.ellipse((x, 7, x + 5, 12), fill=dot)
        cur = self.currency()
        label = "R$" if cur == "BRL" else "US$"
        tw = _tw(f.tiny, label)
        x -= tw + 12
        d.rounded_rectangle((x, 3, x + tw + 8, 15), 4, outline=c["accent"], width=1)
        d.text((x + 4, 4), label, font=f.tiny, fill=c["accent"])
        return x

    def _footer(self, d, hints):
        c, f = self.c, self.f
        d.rectangle((0, FOOTER_Y, W, H), fill=mix(c["bg_bot"], c["surface"], 0.6))
        d.line((0, FOOTER_Y, W, FOOTER_Y), fill=c["line"])
        x = 5
        for key, label in hints:
            kw = max(_tw(f.key, key) + 6, 11)
            lw = _tw(f.tiny, label)
            if x + kw + 3 + lw > W - 4:
                break
            d.rounded_rectangle((x, FOOTER_Y + 2, x + kw, FOOTER_Y + 12), 3, fill=c["surface2"])
            d.text((x + kw / 2, FOOTER_Y + 7), key, font=f.key, fill=c["text"], anchor="mm")
            d.text((x + kw + 3, FOOTER_Y + 2), label, font=f.tiny, fill=c["muted"])
            x += kw + 3 + lw + 8

    def _avatar(self, d, cx, cy, r, sym):
        col = coin_color(sym)
        d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=col)
        lum = 0.299 * col[0] + 0.587 * col[1] + 0.114 * col[2]
        fg = (20, 20, 24) if lum > 170 else (255, 255, 255)
        for label, font in ((sym[:3], self.f.avatar), (sym[:3], self.f.avatar_s), (sym[:1], self.f.avatar)):
            if _tw(font, label) <= 2 * r - 3:
                break
        d.text((cx, cy), label, font=font, fill=fg, anchor="mm")

    def _star(self, d, cx, cy, r, fill):
        pts = []
        for i in range(10):
            a = -math.pi / 2 + i * math.pi / 5
            rr = r if i % 2 == 0 else r * 0.45
            pts.append((cx + rr * math.cos(a), cy + rr * math.sin(a)))
        d.polygon(pts, fill=fill)

    def _pill(self, d, box, change):
        c, f = self.c, self.f
        x0, y0, x1, y1 = box
        if change is None:
            d.rounded_rectangle(box, 5, fill=c["surface2"])
            d.text(((x0 + x1) / 2, (y0 + y1) / 2), "—", font=f.pill, fill=c["muted"], anchor="mm")
            return
        col = c["up"] if change > 0.005 else c["down"] if change < -0.005 else c["flat"]
        d.rounded_rectangle(box, 5, fill=mix(c["surface"], col, 0.22))
        text = fmt.pct(abs(change)).lstrip("+")
        if abs(change) >= 100:
            text = fmt.number(abs(change), 0) + "%"
        tw = _tw(f.pill, text)
        tx = (x0 + x1) / 2 - (tw + 7) / 2
        cy = (y0 + y1) / 2
        if change > 0.005:
            d.polygon([(tx, cy + 2), (tx + 5, cy + 2), (tx + 2.5, cy - 2.5)], fill=col)
        elif change < -0.005:
            d.polygon([(tx, cy - 2), (tx + 5, cy - 2), (tx + 2.5, cy + 2.5)], fill=col)
        else:
            d.rectangle((tx, cy - 0.5, tx + 5, cy + 0.5), fill=col)
        d.text((tx + 7, cy), text, font=f.pill, fill=col, anchor="lm")

    def _scrollbar(self, d, top, height, first, visible, total):
        if total <= visible:
            return
        c = self.c
        d.rounded_rectangle((W - 4, top, W - 2, top + height), 1, fill=c["surface2"])
        h = max(10, height * visible / total)
        y = top + (height - h) * first / max(1, total - visible)
        d.rounded_rectangle((W - 4, y, W - 2, y + h), 1, fill=c["accent"])

    def _spinner(self, d, cx, cy, r, col):
        a = (time.time() * 360) % 360
        d.arc((cx - r, cy - r, cx + r, cy + r), a, a + 270, fill=col, width=2)

    def _draw_toast(self, d):
        c, f = self.c, self.f
        tw = _tw(f.small, self.toast_text)
        w = min(W - 20, tw + 20)
        x0 = (W - w) / 2
        y0 = FOOTER_Y - 21
        d.rounded_rectangle((x0, y0, x0 + w, y0 + 17), 8, fill=c["surface2"], outline=c["accent"])
        d.text((W / 2, y0 + 8.5), ellipsize(f.small, self.toast_text, w - 14), font=f.small,
               fill=c["text"], anchor="mm")

    # ---- gráficos (supersampling para linhas suaves)
    def _series_img(self, w, h, values, col, fill_alpha=110, line_w=1.6, ss=3, pad=3):
        key = ("series", w, h, hash(tuple(values)), col, fill_alpha, line_w, pad)
        img = self._cache.get(key)
        if img is not None:
            return img
        if len(self._cache) > 64:
            self._cache.clear()
        W2, H2 = w * ss, h * ss
        lo, hi = min(values), max(values)
        rng = (hi - lo) or abs(hi) * 0.01 or 1
        n = len(values)
        pts = [(i * (W2 - 1) / max(1, n - 1), pad * ss + (H2 - 2 * pad * ss) * (1 - (v - lo) / rng))
               for i, v in enumerate(values)]
        layer = Image.new("RGBA", (W2, H2), col + (0,))
        if fill_alpha:
            mask = Image.new("L", (W2, H2), 0)
            ImageDraw.Draw(mask).polygon(pts + [(W2 - 1, H2), (0, H2)], fill=255)
            grad = Image.linear_gradient("L").rotate(180).resize((W2, H2))
            grad = grad.point(lambda v: v * fill_alpha // 255)
            layer.putalpha(ImageChops.multiply(mask, grad))
        ImageDraw.Draw(layer).line(pts, fill=col + (255,), width=max(1, round(line_w * ss)), joint="curve")
        img = layer.resize((w, h), Image.LANCZOS)
        self._cache[key] = img
        return img

    def _point_y(self, h, values, i, pad=3):
        lo, hi = min(values), max(values)
        rng = (hi - lo) or abs(hi) * 0.01 or 1
        return pad + (h - 2 * pad) * (1 - (values[i] - lo) / rng)

    # ---- tela: painel
    def _draw_dash(self, im, d):
        c, f, m = self.c, self.f, self.market
        coins = self.watched_coins()
        self._header(d, self.t("market"), None)
        if not coins:
            d.text((W / 2, 70), self.t("empty_title"), font=f.mid, fill=c["text"], anchor="mm")
            d.text((W / 2, 92), self.t("empty_hint"), font=f.small, fill=c["muted"], anchor="mm")
        overflow = len(coins) > VISIBLE
        right = W - 7 if overflow else W - 4
        for row, coin in enumerate(coins[self.scroll:self.scroll + VISIBLE]):
            i = self.scroll + row
            y = LIST_Y + row * ROW_H
            sym = coin["sym"]
            t = m.tickers.get(sym)
            if i == self.sel:
                d.rounded_rectangle((3, y, right, y + ROW_H - 2), 6, fill=c["surface2"])
                d.rounded_rectangle((3, y + 5, 5, y + ROW_H - 7), 1, fill=c["accent"])
            self._avatar(d, 18, y + 12, 10, sym)
            d.text((33, y), sym, font=f.sym, fill=c["text"])
            d.text((33, y + 14), ellipsize(f.name, coin.get("name") or sym, 68), font=f.name, fill=c["muted"])
            # sparkline 24h
            sp = m.sparks.get(sym)
            sx, sy, sw, sh = 108, y + 4, 58, 16
            if sp and len(sp[1]) > 1:
                ch = t["change"] if t else (sp[1][-1] - sp[1][0])
                col = c["up"] if ch >= 0 else c["down"]
                img = self._series_img(sw, sh, sp[1], col, fill_alpha=70, line_w=1.3, pad=1)
                im.paste(img, (sx, sy), img)
            else:
                d.line((sx, sy + sh / 2, sx + sw, sy + sh / 2), fill=c["line"], width=1)
            pill = (right - 49, y + 4, right - 2, y + 20)
            if t:
                p = fmt.price(self.conv(t["price"]), self.currency())
                pf = f.price if _tw(f.price, p) <= pill[0] - 5 - (sx + sw + 6) else f.pill
                d.text((pill[0] - 5, y + 12), p, font=pf, fill=c["text"], anchor="rm")
                self._pill(d, pill, t["change"])
            else:
                pw = 56
                d.rounded_rectangle((pill[0] - 5 - pw, y + 7, pill[0] - 5, y + 17), 4,
                                    fill=mix(c["surface"], c["surface2"], 0.5 + 0.5 * math.sin(time.time() * 4 + row)))
                self._pill(d, pill, None)
        self._scrollbar(d, LIST_Y, ROW_H * VISIBLE - 2, self.scroll, VISIBLE, len(coins))
        self._footer(d, [("↵", self.t("chart")), ("S", self.t("search")),
                         ("M", "R$" if self.settings.currency == "USD" else "US$"),
                         ("T", self.t("theme")), ("?", self.t("help"))])

    # ---- tela: busca
    def _draw_search(self, im, d):
        c, f, m = self.c, self.f, self.market
        self._header(d, self.t("search"), self.t("by_symbol"))
        box = (6, 23, W - 6, 45)
        d.rounded_rectangle(box, 8, fill=c["surface"], outline=c["accent"], width=1)
        d.ellipse((13, 28, 22, 37), outline=c["muted"], width=2)
        d.line((21, 36, 25, 40), fill=c["muted"], width=2)
        tx = 31
        if self.query:
            d.text((tx, 34), self.query, font=f.input, fill=c["text"], anchor="lm")
            cx = tx + _tw(f.input, self.query) + 2
        else:
            d.text((tx, 34), self.t("type_symbol"), font=f.small, fill=c["faint"], anchor="lm")
            cx = tx
        if int(time.time() * 2.5) % 2 == 0:
            d.rectangle((cx, 27, cx + 1, 41), fill=c["accent"])
        busy = m.busy(("search", self.query.lower())) or (self.query and self.query != self.searched)
        if self.query and busy:
            self._spinner(d, W - 18, 34, 5, c["accent"])

        results = self.search_results()
        if not self.query:
            d.text((W - 12, 34), self.t("popular"), font=f.tiny, fill=c["muted"], anchor="rm")
        if not results:
            msg = self.t("loading_list") if not m.binance and not self.query else (
                self.t("searching") if busy else self.t("not_found", q=self.query))
            d.text((W / 2, 95), msg, font=f.small, fill=c["muted"], anchor="mm")
        overflow = len(results) > VISIBLE
        right = W - 7 if overflow else W - 4
        for row, coin in enumerate(results[self.s_scroll:self.s_scroll + VISIBLE]):
            i = self.s_scroll + row
            y = S_LIST_Y + row * S_ROW_H
            if i == self.s_sel:
                d.rounded_rectangle((3, y, right, y + S_ROW_H - 2), 6, fill=c["surface2"])
                d.rounded_rectangle((3, y + 4, 5, y + S_ROW_H - 6), 1, fill=c["accent"])
                d.text((right - 4, y + 9), "›", font=f.mid, fill=c["accent"], anchor="rm")
            self._avatar(d, 17, y + 9, 8, coin["sym"])
            d.text((30, y + 9), coin["sym"], font=f.sym, fill=c["text"], anchor="lm")
            nx = 30 + _tw(f.sym, coin["sym"]) + 6
            meta = []
            if coin.get("rank"):
                meta.append(f"#{coin['rank']}")
            meta.append("Binance" if coin["src"] == "binance" else "CoinGecko")
            meta_txt = " · ".join(meta)
            mx = right - 14 - _tw(f.tiny, meta_txt)
            d.text((mx, y + 9), meta_txt, font=f.tiny, fill=c["faint"], anchor="lm")
            name = coin.get("name") or ""
            if name and name.upper() != coin["sym"]:
                d.text((nx, y + 9), ellipsize(f.name, name, mx - nx - 6), font=f.name, fill=c["muted"], anchor="lm")
            if self.settings.is_watched(coin):
                self._star(d, mx - 8, y + 9, 3.5, c["accent"])
        self._scrollbar(d, S_LIST_Y, S_ROW_H * VISIBLE - 2, self.s_scroll, VISIBLE, len(results))
        self._footer(d, [("↵", self.t("open")), ("Fn↑↓", self.t("move")), ("⌫", self.t("delete")), ("Esc", self.t("back"))])

    # ---- tela: detalhe/gráfico
    def _draw_detail(self, im, d):
        c, f, m = self.c, self.f, self.market
        coin = self.coin
        sym = coin["sym"]
        self._header(d, sym, coin.get("name") if coin.get("name") != sym else None, coin=coin)
        t = m.tickers.get(sym)
        s = self._series()
        vals = s["closes"] if s and len(s["closes"]) > 1 else None
        cur = self.currency()

        # preço grande (ou valor sob o cursor)
        if vals and self.cursor is not None:
            ci = min(self.cursor, len(vals) - 1)
            price, change = vals[ci], (vals[ci] / vals[0] - 1) * 100 if vals[0] else None
            when = fmt.stamp(s["times"][ci], self.period)
        else:
            price = t["price"] if t else (vals[-1] if vals else None)
            change = ((price / vals[0] - 1) * 100) if vals and price and vals[0] else (
                t["change"] if t and self.period == "24H" else None)
            when = None
        ptxt = fmt.price(self.conv(price), cur)
        d.text((8, 19), ptxt, font=f.big, fill=c["text"])
        self._pill(d, (W - 66, 25, W - 6, 41), change)
        if price and vals and change is not None:
            diff = self.conv(price) - self.conv(vals[0])
            col = c["up"] if diff > 0 else c["down"] if diff < 0 else c["flat"]
            dtxt = ("+" if diff > 0 else "") + fmt.price(diff, cur, fmt.decimals_for(self.conv(price)))
            if _tw(f.big, ptxt) + _tw(f.tiny, dtxt) + 24 < W - 70:
                d.text((W - 72, 33), dtxt, font=f.tiny, fill=col, anchor="rm")

        # abas de período
        x = 8
        for i, key in enumerate(PERIOD_KEYS):
            label = period_label(self.settings.lang, key)
            tw = _tw(f.tiny, label)
            w = max(26, tw + 12)
            box = (x, 50, x + w, 63)
            if key == self.period:
                d.rounded_rectangle(box, 6, fill=c["accent"])
                d.text((x + w / 2, 56.5), label, font=f.tiny, fill=c["accent_text"], anchor="mm")
            else:
                d.rounded_rectangle(box, 6, outline=c["line"], width=1)
                d.text((x + w / 2, 56.5), label, font=f.tiny, fill=c["muted"], anchor="mm")
            x += w + 4
        if when:
            d.text((W - 7, 56.5), when, font=f.small, fill=c["accent"], anchor="rm")
        elif s:
            d.text((W - 7, 56.5), self.t("updated", t=fmt.clock(s["ts"])), font=f.tiny, fill=c["faint"], anchor="rm")

        # gráfico
        cx0, cy0, cw, chh = 6, 67, W - 12, 72
        for k in range(4):
            gy = cy0 + 3 + k * (chh - 6) / 3
            for gx in range(cx0, cx0 + cw, 6):
                d.point((gx, gy), fill=c["line"])
        if vals:
            up = vals[-1] >= vals[0]
            col = c["up"] if up else c["down"]
            img = self._series_img(cw, chh, vals, col, pad=CHART_PAD)
            im.paste(img, (cx0, cy0), img)
            n = len(vals)
            hi_i = max(range(n), key=vals.__getitem__)
            lo_i = min(range(n), key=vals.__getitem__)
            for idx, above in ((hi_i, True), (lo_i, False)):
                px = cx0 + idx * (cw - 1) / max(1, n - 1)
                py = cy0 + self._point_y(chh, vals, idx, CHART_PAD)
                label = fmt.price(self.conv(vals[idx]), cur)
                lw = _tw(f.tiny, label)
                lx = min(max(px - lw / 2, cx0), cx0 + cw - lw)
                ly = py - 12 if above else py + 1
                d.text((lx, ly), label, font=f.tiny, fill=c["muted"])
            # ponto final pulsante
            ex = cx0 + cw - 1
            ey = cy0 + self._point_y(chh, vals, n - 1, CHART_PAD)
            pr = 4 + 1.5 * math.sin(time.time() * 3)
            d.ellipse((ex - pr, ey - pr, ex + pr, ey + pr), outline=mix(c["bg_top"], col, 0.5), width=1)
            d.ellipse((ex - 2, ey - 2, ex + 2, ey + 2), fill=col)
            if self.cursor is not None:
                ci = min(self.cursor, n - 1)
                px = cx0 + ci * (cw - 1) / max(1, n - 1)
                py = cy0 + self._point_y(chh, vals, ci, CHART_PAD)
                for yy in range(cy0, cy0 + chh, 3):
                    d.line((px, yy, px, yy + 1), fill=c["text"])
                d.ellipse((px - 4, py - 4, px + 4, py + 4), fill=c["bg_top"], outline=c["accent"], width=2)
        else:
            if m.busy(("chart", sym, self.period)) or not m.last_error:
                self._spinner(d, W / 2 - 50, cy0 + chh / 2, 6, c["accent"])
                d.text((W / 2 - 38, cy0 + chh / 2), self.t("loading_chart"), font=f.small, fill=c["muted"], anchor="lm")
            else:
                d.text((W / 2, cy0 + chh / 2 - 7), self.t("chart_failed"), font=f.small, fill=c["text"], anchor="mm")
                d.text((W / 2, cy0 + chh / 2 + 8), self.t("press_r"), font=f.tiny, fill=c["muted"], anchor="mm")

        # estatísticas
        stats = []
        if vals:
            stats.append((self.t("high"), fmt.price(self.conv(max(vals)), cur)))
            stats.append((self.t("low"), fmt.price(self.conv(min(vals)), cur)))
        if t and t.get("volume"):
            stats.append((self.t("vol24"), fmt.compact(self.conv(t["volume"]), cur)))
        x = 8
        limit = W - 8 - (_tw(f.tiny, "CoinGecko") + 8 if coin.get("src") == "coingecko" else 0)
        for label, val in stats:
            if x + _tw(f.tiny, label) + 3 + _tw(f.tiny, val) > limit:
                break
            d.text((x, 141), label, font=f.tiny, fill=c["faint"])
            x += _tw(f.tiny, label) + 3
            d.text((x, 141), val, font=f.tiny, fill=c["text"])
            x += _tw(f.tiny, val) + 10
        if coin.get("src") == "coingecko":
            d.text((W - 7, 141), "CoinGecko", font=f.tiny, fill=c["faint"], anchor="ra")

        pin = self.t("unpin") if self.settings.is_watched(coin) else self.t("pin")
        hints = [("1-5", self.t("period")), ("Z/C", self.t("cursor"))]
        if len(self.coin_list) > 1:
            hints.append(("F/X", self.t("coin")))
        hints += [("P", pin), ("Esc", self.t("back"))]
        self._footer(d, hints)

    # ---- ajuda
    def _draw_help(self, im):
        c, f = self.c, self.f
        shade = Image.new("RGB", (W, H), c["overlay"])
        im = Image.blend(im, shade, 0.72)
        d = ImageDraw.Draw(im)
        d.rounded_rectangle((8, 6, W - 8, H - 6), 10, fill=c["surface"], outline=c["line"])
        d.text((18, 11), self.t("shortcuts"), font=f.title, fill=c["accent"])
        d.text((W - 18, 15), self.t("any_key"), font=f.tiny, fill=c["faint"], anchor="ra")
        rows = [
            ("F / X", self.t("h_move")),
            ("Enter", self.t("h_enter")),
            ("S", self.t("h_search")),
            ("1-5 · Tab", self.t("h_period")),
            ("Z / C", self.t("h_cursor")),
            ("P", self.t("h_pin")),
            ("M·T·L·R", self.t("h_mtr")),
            ("Esc", self.t("h_esc")),
        ]
        y = 32
        for k, desc in rows:
            kw = _tw(f.tiny, k) + 8
            d.rounded_rectangle((18, y, 18 + kw, y + 12), 3, fill=c["surface2"])
            d.text((18 + kw / 2, y + 6), k, font=f.tiny, fill=c["text"], anchor="mm")
            d.text((84, y + 6), desc, font=f.small, fill=c["text"], anchor="lm")
            y += 15
        return im
