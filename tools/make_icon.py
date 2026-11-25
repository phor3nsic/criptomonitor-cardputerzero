"""Generates the app icon. Usage: make_icon.py OUT.png [SIZE] (100 = launcher, 256 = Store)."""
import sys

from PIL import Image, ImageDraw

S = 4
N = 100 * S


def main(out, size=100):
    im = Image.new("RGBA", (N, N), (0, 0, 0, 0))
    grad = Image.linear_gradient("L").resize((N, N))
    top = Image.new("RGBA", (N, N), (28, 36, 58, 255))
    bot = Image.new("RGBA", (N, N), (10, 13, 22, 255))
    bg = Image.composite(bot, top, grad)
    mask = Image.new("L", (N, N), 0)
    ImageDraw.Draw(mask).rounded_rectangle((4 * S, 4 * S, N - 4 * S, N - 4 * S), 22 * S, fill=255)
    im.paste(bg, (0, 0), mask)
    d = ImageDraw.Draw(im)
    # barras (candles) ao fundo
    for i, (h, col) in enumerate([(26, (255, 92, 108)), (40, (46, 214, 128)), (32, (255, 92, 108)), (54, (46, 214, 128))]):
        x = (22 + i * 16) * S
        d.rounded_rectangle((x, (80 - h) * S, x + 9 * S, 80 * S), 3 * S, fill=col + (70,))
    # linha ascendente dourada
    pts = [(16, 70), (32, 58), (46, 64), (62, 42), (72, 48), (86, 24)]
    pts = [(x * S, y * S) for x, y in pts]
    d.line(pts, fill=(255, 184, 64, 255), width=7 * S, joint="curve")
    x, y = pts[-1]
    d.ellipse((x - 7 * S, y - 7 * S, x + 7 * S, y + 7 * S), fill=(255, 184, 64, 255))
    d.ellipse((x - 3 * S, y - 3 * S, x + 3 * S, y + 3 * S), fill=(255, 245, 220, 255))
    im.resize((size, size), Image.LANCZOS).save(out)


if __name__ == "__main__":
    main(sys.argv[1], int(sys.argv[2]) if len(sys.argv) > 2 else 100)
