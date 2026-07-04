#!/usr/bin/env python3
"""Generate PUSU PWA icons from the reticle mark (mirrors public/pusu.svg).

Redraws the mark natively with Pillow (no SVG rasteriser needed) so we control
the maskable safe-zone padding and the opaque apple-touch background. Outputs to
public/icons/. Re-run whenever the brand mark changes.

  icon-192.png          192  rounded-rect bg + full mark   (manifest, purpose any)
  icon-512.png          512  rounded-rect bg + full mark   (manifest, purpose any)
  icon-maskable-512.png 512  full-bleed bg + mark @66%      (manifest, purpose maskable)
  apple-touch-icon.png  180  full-bleed opaque bg + mark    (iOS home screen)
"""
import math
import os

from PIL import Image, ImageDraw

BG = (11, 14, 17)          # #0B0E11
GOLD = (245, 185, 66)      # #F5B942
MID = (116, 91, 39)        # gold @0.45 over bg (mid ring)
SS = 4                     # supersample factor for antialiasing
OUT = os.path.join(os.path.dirname(__file__), "..", "public", "icons")


def _line_polar(draw, cx, cy, unit, ang_deg, r0, r1, width, fill):
    a = math.radians(ang_deg)
    x0, y0 = cx + math.cos(a) * r0 * unit, cy + math.sin(a) * r0 * unit
    x1, y1 = cx + math.cos(a) * r1 * unit, cy + math.sin(a) * r1 * unit
    draw.line([(x0, y0), (x1, y1)], fill=fill, width=max(1, round(width * unit)))


def draw_mark(draw, cx, cy, unit):
    """Draw the reticle centred at (cx,cy); `unit` = pixels per SVG unit."""
    def circ(r, w, fill):
        bb = [cx - r * unit, cy - r * unit, cx + r * unit, cy + r * unit]
        draw.ellipse(bb, outline=fill, width=max(1, round(w * unit)))

    # outer scanning (dashed) ring r=19.5 sw=2.2, dash 3.5 gap 5 => ~25deg period
    r, w = 19.5, 2.2
    bb = [cx - r * unit, cy - r * unit, cx + r * unit, cy + r * unit]
    period = 25.0
    dash = 10.3  # 3.5/8.5 of the period, in degrees
    a = 0.0
    while a < 360:
        draw.arc(bb, a, a + dash, fill=GOLD, width=max(1, round(w * unit)))
        a += period

    # mid ring r=12.5 sw=1.4 (dimmed)
    circ(12.5, 1.4, MID)

    # crosshair ticks sw=2.2 (top/bottom/left/right, radial r=13.5..19)
    for ang in (270, 90, 180, 0):  # up, down, left, right
        _line_polar(draw, cx, cy, unit, ang, 13.5, 19.0, 2.2, GOLD)

    # lock-on strike triangle (24,14)(29.5,24.5)(18.5,24.5) -> center-relative
    tri = [(0, -10), (5.5, 0.5), (-5.5, 0.5)]
    draw.polygon([(cx + dx * unit, cy + dy * unit) for dx, dy in tri], fill=GOLD)

    # center core r=2.6
    draw.ellipse([cx - 2.6 * unit, cy - 2.6 * unit, cx + 2.6 * unit, cy + 2.6 * unit], fill=GOLD)


def render(size, mark_scale=1.0, rounded=True):
    S = size * SS
    img = Image.new("RGB", (S, S), BG)
    d = ImageDraw.Draw(img)
    if rounded:
        # rounded-rect bg like the favicon (rx=11 of 48). Corners outside stay BG
        # too, so this is purely cosmetic on the opaque field.
        rad = round(11 / 48 * S)
        mask = Image.new("L", (S, S), 0)
        ImageDraw.Draw(mask).rounded_rectangle([0, 0, S - 1, S - 1], radius=rad, fill=255)
        bg = Image.new("RGB", (S, S), BG)
        img = Image.composite(bg, Image.new("RGB", (S, S), (0, 0, 0)), mask)
        d = ImageDraw.Draw(img)
    unit = (S / 48.0) * mark_scale
    draw_mark(d, S / 2, S / 2, unit)
    return img.resize((size, size), Image.LANCZOS)


def main():
    os.makedirs(OUT, exist_ok=True)
    render(192, rounded=True).save(os.path.join(OUT, "icon-192.png"))
    render(512, rounded=True).save(os.path.join(OUT, "icon-512.png"))
    # maskable: full-bleed square (OS applies its own mask), mark in the safe zone
    render(512, mark_scale=0.66, rounded=False).save(os.path.join(OUT, "icon-maskable-512.png"))
    # apple-touch: opaque, full-bleed (iOS rounds corners itself)
    render(180, rounded=False).save(os.path.join(OUT, "apple-touch-icon.png"))
    for f in sorted(os.listdir(OUT)):
        print("wrote", os.path.join("public/icons", f))


if __name__ == "__main__":
    main()
