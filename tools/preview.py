"""Renderiza as telas com dados reais em PNGs (sem framebuffer). Uso:

    CRIPTO_FONT_DIR=<dir com fontes> python3 tools/preview.py OUT_DIR [--scale 3]
"""
import os
import sys
import time
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("XDG_CONFIG_HOME", tempfile.mkdtemp())

from criptomonitor.app import App  # noqa: E402
from criptomonitor.market import Market  # noqa: E402


def wait(market, keys, timeout=20):
    end = time.time() + timeout
    while time.time() < end and any(market.busy(k) for k in keys):
        time.sleep(0.1)


def main():
    out = sys.argv[1]
    scale = int(sys.argv[3]) if len(sys.argv) > 3 and sys.argv[2] == "--scale" else 3
    os.makedirs(out, exist_ok=True)
    m = Market()
    app = App(m)

    def settle(rounds=6):
        for _ in range(rounds):
            app.tick()
            time.sleep(0.3)
            wait(m, list(m._inflight))
        app.tick()

    def snap(name):
        im = app.render()
        im.resize((im.width * scale, im.height * scale), 0).save(os.path.join(out, name + ".png"))
        print("salvo", name)

    settle(8)
    snap("1-painel")
    for k in ("x", "x"):
        app.key(k)
    snap("2-painel-sel")
    app.key("ENTER")
    settle(6)
    snap("3-grafico-24h")
    app.key("3")
    settle(5)
    snap("4-grafico-7d")
    for _ in range(40):
        app.key("z")
    snap("5-grafico-cursor")
    app.key("ESC"); app.key("ESC")
    app.key("s")
    settle(2)
    snap("6-busca-vazia")
    for ch in "pepe":
        app.key(ch)
    app.typed_at = 0
    settle(5)
    snap("7-busca-pepe")
    app.key("ENTER")
    settle(6)
    snap("8-pepe-grafico")
    app.key("m")
    settle(4)
    snap("9-pepe-brl")
    app.key("ESC"); app.key("ESC")
    app.key("t")
    settle(2)
    snap("10-painel-claro")
    app.key("?")
    snap("11-ajuda")
    m.shutdown()


if __name__ == "__main__":
    main()
