#!/usr/bin/env python3
"""
Generate alien_icon.ico for Alien AI Trader — the landing-page alien face
clutching a realistic banded wad of cash. Draws 256/48/32/16 and saves a
multi-resolution .ico (+ a PNG for reference).

NOTE: Replace with your own art by naming it installer/alien_icon.ico (256x256).
Requires: Pillow  (auto-installed below if missing)
Built by Troy Walker of T-Dub's Apps — 2026
"""

import os
import math

try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError:
    print("Pillow not found. Installing...")
    import subprocess, sys
    subprocess.check_call([sys.executable, "-m", "pip", "install", "Pillow", "--quiet"])
    from PIL import Image, ImageDraw, ImageFont


def _font(px):
    for name in ("arialbd.ttf", "arial.ttf", "seguisb.ttf", "segoeui.ttf",
                 "DejaVuSans-Bold.ttf", "DejaVuSans.ttf"):
        try:
            return ImageFont.truetype(name, max(6, int(px)))
        except Exception:
            continue
    try:
        return ImageFont.load_default()
    except Exception:
        return None


def _text(d, cx, cy, s, px, fill, anchor="mm"):
    f = _font(px)
    if not f:
        return
    try:
        d.text((cx, cy), s, font=f, fill=fill, anchor=anchor)
    except TypeError:  # older Pillow without anchor=
        d.text((cx - len(s) * px * 0.3, cy - px * 0.55), s, font=f, fill=fill)


def _rot_ellipse(d, cx, cy, rw, rh, angle_deg, fill):
    pts, a = [], math.radians(angle_deg)
    for i in range(40):
        t = 2 * math.pi * i / 40
        x, y = rw * math.cos(t), rh * math.sin(t)
        pts.append((cx + x * math.cos(a) - y * math.sin(a),
                    cy + x * math.sin(a) + y * math.cos(a)))
    d.polygon(pts, fill=fill)


def draw_alien(size):
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    s = size / 256.0
    def S(v):
        return v * s
    cx = size / 2.0

    GREEN = (34, 197, 94, 255)     # #22c55e
    STROKE = (22, 163, 74, 255)    # #16a34a
    LITE = (74, 222, 128, 255)     # #4ade80
    BILL = (122, 220, 150, 255)
    BILLDK = (20, 83, 45, 255)

    def rrect(box, fill, outline=None, r=6, w=2):
        try:
            d.rounded_rectangle(box, radius=S(r), fill=fill, outline=outline,
                                width=max(1, int(S(w))))
        except Exception:
            d.rectangle(box, fill=fill, outline=outline)

    # Background squircle + glow ring
    rrect([S(8), S(8), S(248), S(248)], (9, 15, 28, 255), r=54)
    d.ellipse([cx - S(94), S(108) - S(94), cx + S(94), S(108) + S(94)],
              outline=(34, 197, 94, 52), width=max(1, int(S(6))))

    # Flying banknotes
    if size >= 48:
        for (bx, by, bw, bh, fp) in [(S(202), S(50), S(34), S(22), S(7)),
                                     (S(52), S(56), S(30), S(20), S(6))]:
            rrect([bx - bw / 2, by - bh / 2, bx + bw / 2, by + bh / 2], BILL,
                  outline=BILLDK, r=3, w=1)
            d.ellipse([bx - S(6), by - S(5), bx + S(6), by + S(5)], fill=(236, 253, 245, 255))
            if size >= 128:
                _text(d, bx, by, "$", fp, BILLDK)

    # Antenna
    d.line([(cx, S(34)), (cx, S(12))], fill=GREEN, width=max(1, int(S(4.5))))
    br = max(2, int(S(8)))
    d.ellipse([cx - br, S(9) - br, cx + br, S(9) + br], fill=LITE)

    # Arms (behind head; hands hold the wad)
    aw = max(2, int(S(13)))
    d.line([(cx - S(32), S(152)), (cx - S(10), S(202))], fill=GREEN, width=aw)
    d.line([(cx + S(32), S(152)), (cx + S(10), S(202))], fill=GREEN, width=aw)

    # Head (matches landing-page alien face)
    d.ellipse([cx - S(60), S(108) - S(78), cx + S(60), S(108) + S(78)],
              fill=GREEN, outline=STROKE, width=max(1, int(S(3))))

    # Eyes: black, tilted, with shine
    _rot_ellipse(d, cx - S(29), S(97), S(22), S(15), -18, (0, 0, 0, 255))
    _rot_ellipse(d, cx + S(29), S(97), S(22), S(15), 18, (0, 0, 0, 255))
    for ex, ey in [(cx - S(38), S(90)), (cx + S(20), S(90))]:
        d.ellipse([ex - S(6.5), ey - S(4.5), ex + S(6.5), ey + S(4.5)], fill=(255, 255, 255, 205))

    # Nostrils + wide smile
    nr = max(1, int(S(5)))
    for nx in [cx - S(13), cx + S(13)]:
        d.ellipse([nx - nr, S(140) - nr, nx + nr, S(140) + nr], fill=STROKE)
    d.arc([cx - S(27), S(152) - S(20), cx + S(27), S(152) + S(24)],
          start=20, end=160, fill=STROKE, width=max(1, int(S(4))))

    # Realistic banded wad of cash (lighter green + white $100 strap)
    rrect([S(76), S(188), S(180), S(236)], (56, 189, 120, 255), r=4)   # deepest
    rrect([S(76), S(184), S(180), S(232)], (79, 209, 138, 255), r=4)
    rrect([S(76), S(180), S(180), S(228)], BILL, outline=BILLDK, r=4, w=1.5)  # front bill
    if size >= 48:
        rrect([S(82), S(186), S(174), S(222)], None, outline=(34, 197, 94, 140), r=3, w=1.3)
        d.ellipse([cx - S(16), S(202) - S(13), cx + S(16), S(202) + S(13)],
                  fill=(236, 253, 245, 255), outline=BILLDK, width=max(1, int(S(1))))
        pr = max(2, int(S(5.5)))
        d.ellipse([cx - pr, S(199) - pr, cx + pr, S(199) + pr], fill=(95, 214, 143, 255))
        if size >= 128:
            _text(d, S(92), S(192), "$", S(9), BILLDK)
            _text(d, S(164), S(216), "$", S(9), BILLDK)
            _text(d, S(160), S(192), "100", S(7), BILLDK)
            _text(d, S(96), S(216), "100", S(7), BILLDK)
    # White currency strap with black edge lines + $100
    rrect([S(114), S(176), S(142), S(232)], (255, 255, 255, 255), outline=(203, 213, 225, 255), r=1, w=1)
    d.rectangle([S(114), S(182), S(142), S(184)], fill=(0, 0, 0, 255))
    d.rectangle([S(114), S(224), S(142), S(226)], fill=(0, 0, 0, 255))
    if size >= 48:
        _text(d, cx, S(197), "$100", S(8), (0, 0, 0, 255))
    if size >= 32:
        _text(d, cx, S(216), "$", S(15), (0, 0, 0, 255))

    return img


def main():
    out_dir = os.path.join(os.path.dirname(__file__), "installer")
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, "alien_icon.ico")

    print(f"Generating alien-with-cash icon -> {out_path}")
    sizes = [256, 48, 32, 16]
    images = [draw_alien(s) for s in sizes]

    images[0].save(out_path, format="ICO", sizes=[(s, s) for s in sizes],
                   append_images=images[1:])
    print(f"  OK  Icon saved: {out_path}")

    png_path = os.path.join(out_dir, "alien_icon.png")
    images[0].save(png_path, format="PNG")
    print(f"  OK  PNG saved:  {png_path}")
    print("\n  TIP: replace installer/alien_icon.ico with your own 256x256 ICO to customize.")


if __name__ == "__main__":
    main()
