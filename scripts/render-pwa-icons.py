#!/usr/bin/env python3
"""Regenerate the checked-in PWA PNGs. Optional development dependency: Pillow."""
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
DESTINATION = ROOT / 'root/usr/share/weharbor/pwa/pwa-icons'


def render(size):
    scale = 4
    image = Image.new('RGB', (512 * scale, 512 * scale), '#101c2d')
    draw = ImageDraw.Draw(image)

    def polygon(points, color):
        draw.polygon([(x * scale, y * scale) for x, y in points], fill=color)

    def line(points, color, width):
        draw.line([(x * scale, y * scale) for x, y in points], fill=color, width=width * scale)
        radius = width * scale / 2
        for x, y in [points[0], points[-1]]:
            x, y = x * scale, y * scale
            draw.ellipse((x - radius, y - radius, x + radius, y + radius), fill=color)

    polygon([(156, 148), (356, 148), (356, 272), (250, 272),
             (208, 306), (208, 272), (156, 272)], '#56dfbb')
    line([(184, 183), (328, 183)], '#101c2d', 14)
    line([(184, 215), (272, 215)], '#101c2d', 14)
    polygon([(156, 320), (356, 320), (324, 352), (188, 352)], '#edf5fc')
    wave = []
    for part in range(4):
        for step in range(33):
            t = step / 32
            wave.append((152 + 52 * (part + t), 374 + (-20 if part % 2 == 0 else 20) * 2 * t * (1 - t)))
    line(wave, '#56dfbb', 12)
    return image.resize((size, size), Image.Resampling.LANCZOS)


if __name__ == '__main__':
    DESTINATION.mkdir(parents=True, exist_ok=True)
    for name, size in [('icon-192.png', 192), ('icon-512.png', 512),
                       ('maskable-512.png', 512), ('apple-touch-icon.png', 180)]:
        render(size).save(DESTINATION / name, optimize=True)
