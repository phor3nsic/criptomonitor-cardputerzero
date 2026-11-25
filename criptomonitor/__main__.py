"""Ponto de entrada: laço principal com framebuffer + teclado do CardputerZero."""
import argparse
import os
import select
import signal
import sys
import time

from . import __version__


def main(argv=None):
    ap = argparse.ArgumentParser(prog="criptomonitor", description="Monitor de criptomoedas para o CardputerZero")
    ap.add_argument("--fb", help="framebuffer (padrão: $APPLAUNCH_LINUX_FBDEV_DEVICE ou /dev/fb0)")
    ap.add_argument("--kbd", help="dispositivo evdev do teclado")
    ap.add_argument("--keys-fifo", help="(desenvolvimento) FIFO com teclas simuladas, uma por linha")
    ap.add_argument("--version", action="version", version=__version__)
    args = ap.parse_args(argv)

    from .app import App
    from .hw import Framebuffer, Keyboard
    from .market import Market

    rpipe, wpipe = os.pipe()
    os.set_blocking(rpipe, False)
    os.set_blocking(wpipe, False)

    def wake():
        try:
            os.write(wpipe, b"!")
        except (BlockingIOError, OSError):
            pass

    market = Market(on_change=wake)
    app = App(market, wake=wake)
    fb = kb = None
    fifo = None
    shot = {"want": False}

    def on_term(*_):
        app.exit = True
        wake()

    def on_usr1(*_):
        shot["want"] = True
        wake()

    signal.signal(signal.SIGTERM, on_term)
    signal.signal(signal.SIGINT, on_term)
    signal.signal(signal.SIGHUP, on_term)
    signal.signal(signal.SIGUSR1, on_usr1)

    try:
        fb = Framebuffer(args.fb)
        kb = Keyboard(args.kbd)
        if args.keys_fifo:
            if not os.path.exists(args.keys_fifo):
                os.mkfifo(args.keys_fifo, 0o600)
            fifo = os.open(args.keys_fifo, os.O_RDONLY | os.O_NONBLOCK)
        fb.draw(app.render())
        fifo_buf = b""
        while not app.exit:
            app.tick()
            if app.dirty:
                app.dirty = False
                fb.draw(app.render())
            fds = [kb.fileno(), rpipe] + ([fifo] if fifo is not None else [])
            timeout = 0.05 if kb.esc_down is not None else 0.2
            ready, _, _ = select.select(fds, [], [], timeout)
            if rpipe in ready:
                try:
                    while os.read(rpipe, 64):
                        pass
                except BlockingIOError:
                    pass
                app.dirty = True
            if kb.fileno() in ready:
                for k in kb.read():
                    app.key(k)
            hold = kb.poll_hold()
            if hold:
                app.key(hold)
            if fifo is not None and fifo in ready:
                chunk = os.read(fifo, 256)
                if not chunk:  # escritor fechou; reabre
                    os.close(fifo)
                    fifo = os.open(args.keys_fifo, os.O_RDONLY | os.O_NONBLOCK)
                fifo_buf += chunk
                while b"\n" in fifo_buf:
                    line, fifo_buf = fifo_buf.split(b"\n", 1)
                    k = line.decode(errors="ignore").strip()
                    if k:
                        app.key(" " if k == "SPACE" else k)
            if shot["want"]:
                shot["want"] = False
                path = app.screenshot()
                if path:
                    print(f"captura: {path}", flush=True)
    except OSError as exc:
        print(f"criptomonitor: {exc}", file=sys.stderr)
        return 1
    finally:
        market.shutdown()
        if kb:
            kb.close()
        if fb:
            fb.close()
        if fifo is not None:
            os.close(fifo)
    return 0


if __name__ == "__main__":
    sys.exit(main())
