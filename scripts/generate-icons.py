#!/usr/bin/env python3
"""Generate PWA icons from the ⚔ (U+2694) brand glyph."""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
STATIC = ROOT / "static"
FONT = "/usr/share/fonts/google-noto-emoji-fonts/NotoEmoji-Regular.ttf"
GLYPH = "\u2694"
BG = (0x1A, 0x1D, 0x27, 255)
FG = (0xE8, 0xEA, 0xF0, 255)


def _draw(size: int, *, transparent: bool = False) -> Image.Image:
    bg = (0, 0, 0, 0) if transparent else BG
    img = Image.new("RGBA", (size, size), bg)
    draw = ImageDraw.Draw(img)
    font_size = int(size * 0.63)
    font = ImageFont.truetype(FONT, font_size)
    bbox = draw.textbbox((0, 0), GLYPH, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    x = (size - tw) // 2 - bbox[0]
    y = (size - th) // 2 - bbox[1]
    color = (255, 255, 255, 255) if transparent else FG
    draw.text((x, y), GLYPH, font=font, fill=color)
    return img


def main() -> None:
    _draw(512).save(STATIC / "icon-512.png")
    _draw(192).save(STATIC / "icon-192.png")
    _draw(512, transparent=True).save(STATIC / "icon-monochrome.png")
    print("Wrote icon-192.png, icon-512.png, icon-monochrome.png")


if __name__ == "__main__":
    main()
