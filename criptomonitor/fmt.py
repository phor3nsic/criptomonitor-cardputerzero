"""Number/date formatting. STYLE "en" = 1,234.56 ; "pt" = 1.234,56."""
import math
import time

CURRENCY_PREFIX = {"USD": "$", "BRL": "R$"}
STYLE = "en"


def _ptbr(text):
    if STYLE != "pt":
        return text
    return text.replace(",", "\0").replace(".", ",").replace("\0", ".")


def decimals_for(value):
    a = abs(value)
    if a >= 10000:
        return 0
    if a >= 1:
        return 2
    if a >= 0.01:
        return 4
    if a == 0:
        return 2
    return min(10, -int(math.floor(math.log10(a))) + 3)


def number(value, dec=None):
    if value is None or not math.isfinite(value):
        return "—"
    if dec is None:
        dec = decimals_for(value)
        text = f"{value:,.{dec}f}"
        if abs(value) < 0.01 and "." in text:
            text = text.rstrip("0")  # 0,000003240 -> 0,00000324
        return _ptbr(text)
    return _ptbr(f"{value:,.{dec}f}")


def price(value, currency="USD", dec=None):
    if value is None or not math.isfinite(value):
        return "—"
    prefix = CURRENCY_PREFIX.get(currency, "")
    sign = "-" if value < 0 else ""
    sep = " " if len(prefix) > 1 else ""
    return f"{sign}{prefix}{sep}{number(abs(value), dec)}"


def pct(value):
    if value is None or not math.isfinite(value):
        return "—"
    sign = "+" if value > 0 else ("-" if value < 0 else "")
    return f"{sign}{_ptbr(f'{abs(value):.2f}')}%"


def compact(value, currency=None):
    if value is None or not math.isfinite(value):
        return "—"
    a = abs(value)
    suffixes = ((1e12, " tri"), (1e9, " bi"), (1e6, " mi"), (1e3, " mil")) if STYLE == "pt" else \
        ((1e12, "T"), (1e9, "B"), (1e6, "M"), (1e3, "K"))
    for limit, suffix in suffixes:
        if a >= limit:
            text = _ptbr(f"{value / limit:.1f}") + suffix
            break
    else:
        text = number(value, 0 if a >= 100 else 2)
    if currency:
        prefix = CURRENCY_PREFIX.get(currency, "")
        sep = " " if len(prefix) > 1 else ""
        text = f"{prefix}{sep}{text}"
    return text


def clock(ts=None):
    return time.strftime("%H:%M", time.localtime(ts))


def stamp(ts, period_key):
    lt = time.localtime(ts)
    pt = STYLE == "pt"
    if period_key in ("1H", "24H"):
        return time.strftime("%d/%m %H:%M" if pt else "%b %d %H:%M", lt)
    if period_key in ("7D", "30D"):
        return time.strftime("%d/%m %Hh" if pt else "%b %d %H:00", lt)
    return time.strftime("%d/%m/%Y" if pt else "%b %d, %Y", lt)
