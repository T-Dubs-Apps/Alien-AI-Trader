#!/usr/bin/env python3
"""
Generate alien_icon.ico for Alien AI Trader.
Draws a procedural alien face at 256x256, 48x48, 32x32, 16x16
and saves as a multi-resolution .ico file.

NOTE: Replace this with your own custom image by naming it
      installer/alien_icon.ico  (256x256 recommended).

Requires: Pillow  (pip install Pillow)
Built by Troy Walker of T-Dub's Apps — 2026
"""

import os
import math

try:
    from PIL import Image, ImageDraw
except ImportError:
    print("Pillow not found. Installing...")
    import subprocess, sys
    subprocess.check_call([sys.executable, "-m", "pip", "install", "Pillow", "--quiet"])
    from PIL import Image, ImageDraw


def draw_alien_face(size: int) -> Image.Image:
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    cx, cy = size // 2, size // 2
    scale = size / 256.0

    # ── Background circle (dark space) ────────────────────────
    r_bg = int(120 * scale)
    d.ellipse(
        [cx - r_bg, cy - r_bg, cx + r_bg, cy + r_bg],
        fill=(8, 14, 26, 255)
    )

    # ── Alien head (green oval) ────────────────────────────────
    hw = int(70 * scale)   # half-width
    hh = int(88 * scale)   # half-height  (taller than wide = classic alien)
    head_top = cy - int(20 * scale)  # shift head slightly up
    d.ellipse(
        [cx - hw, head_top - hh, cx + hw, head_top + hh],
        fill=(34, 197, 94, 255),    # #22c55e — green
        outline=(22, 163, 74, 255), # #16a34a — darker green
    )

    # ── Forehead shine ────────────────────────────────────────
    shine_r = int(22 * scale)
    d.ellipse(
        [cx - int(30 * scale) - shine_r,
         head_top - hh + int(15 * scale),
         cx - int(30 * scale) + shine_r,
         head_top - hh + int(15 * scale) + shine_r * 2],
        fill=(74, 222, 128, 130),   # semi-transparent light green
    )

    # ── Eyes (large, black, oval — tilted slightly) ───────────
    eye_spread = int(28 * scale)
    eye_cy = head_top - int(12 * scale)
    eye_rw = int(24 * scale)
    eye_rh = int(16 * scale)

    # Draw a simple rotated ellipse by using a polygon approximation
    def rotated_ellipse(draw, cx_, cy_, rw, rh, angle_deg, fill):
        pts = []
        angle_rad = math.radians(angle_deg)
        steps = 32
        for i in range(steps):
            t = 2 * math.pi * i / steps
            x = rw * math.cos(t)
            y = rh * math.sin(t)
            rx = x * math.cos(angle_rad) - y * math.sin(angle_rad)
            ry = x * math.sin(angle_rad) + y * math.cos(angle_rad)
            pts.append((cx_ + rx, cy_ + ry))
        draw.polygon(pts, fill=fill)

    rotated_ellipse(d, cx - eye_spread, eye_cy, eye_rw, eye_rh, -18, (0, 0, 0, 255))
    rotated_ellipse(d, cx + eye_spread, eye_cy, eye_rw, eye_rh,  18, (0, 0, 0, 255))

    # Eye shine (small white dots)
    shine_dot = max(2, int(7 * scale))
    for ex in [cx - eye_spread - int(8 * scale), cx + eye_spread - int(8 * scale)]:
        ey = eye_cy - int(4 * scale)
        d.ellipse([ex - shine_dot, ey - shine_dot, ex + shine_dot, ey + shine_dot],
                  fill=(255, 255, 255, 200))

    # ── Nostrils (two small dots) ────────────────────────────
    nose_y = head_top + int(20 * scale)
    nr = max(2, int(4 * scale))
    d.ellipse([cx - int(10*scale)-nr, nose_y-nr, cx - int(10*scale)+nr, nose_y+nr],
              fill=(22, 163, 74, 255))
    d.ellipse([cx + int(10*scale)-nr, nose_y-nr, cx + int(10*scale)+nr, nose_y+nr],
              fill=(22, 163, 74, 255))

    # ── Mouth (thin smile arc) ───────────────────────────────
    mouth_y = head_top + int(45 * scale)
    mouth_r = int(22 * scale)
    mouth_lw = max(1, int(3 * scale))
    d.arc(
        [cx - mouth_r, mouth_y - mouth_r // 2,
         cx + mouth_r, mouth_y + mouth_r // 2],
        start=10, end=170,
        fill=(22, 163, 74, 255),
        width=mouth_lw,
    )

    # ── Antenna ──────────────────────────────────────────────
    ant_base_y = head_top - hh + int(5 * scale)
    ant_tip_y  = head_top - hh - int(40 * scale)
    ant_lw = max(1, int(3 * scale))
    d.line([(cx, ant_base_y), (cx, ant_tip_y)],
           fill=(34, 197, 94, 255), width=ant_lw)
    ball_r = max(3, int(8 * scale))
    d.ellipse([cx - ball_r, ant_tip_y - ball_r,
               cx + ball_r, ant_tip_y + ball_r],
              fill=(74, 222, 128, 255))

    # ── Outer glow ring ──────────────────────────────────────
    glow_r = int(122 * scale)
    for i in range(3, 0, -1):
        alpha = 40 - i * 10
        d.ellipse(
            [cx - glow_r - i * 3, cy - glow_r - i * 3,
             cx + glow_r + i * 3, cy + glow_r + i * 3],
            outline=(34, 197, 94, alpha),
            width=1
        )

    return img


def main():
    out_dir = os.path.join(os.path.dirname(__file__), "installer")
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, "alien_icon.ico")

    print(f"Generating alien icon → {out_path}")

    sizes = [256, 48, 32, 16]
    images = [draw_alien_face(s) for s in sizes]

    # Save multi-resolution .ico
    images[0].save(
        out_path,
        format="ICO",
        sizes=[(s, s) for s in sizes],
        append_images=images[1:],
    )
    print(f"  ✔  Icon saved: {out_path}")

    # Also save a 256x256 PNG for reference / the splash screen
    png_path = os.path.join(out_dir, "alien_icon.png")
    images[0].save(png_path, format="PNG")
    print(f"  ✔  PNG saved:  {png_path}")
    print()
    print("  TIP: To use your own image, replace installer/alien_icon.ico")
    print("       with a 256x256 ICO file (any Windows icon editor can convert a PNG).")


if __name__ == "__main__":
    main()
