"""Generate the app icon (icon.png / icon.ico / icon.icns).

The motif: a rounded card holding the classic overlapping CMYK process-color
circles (cyan/magenta/yellow, multiplying to secondary colors and black where
all three meet) with a magnifier on top — "checking the colors in a document".

Run:  python assets/make_icon.py
Requires Pillow. On macOS, iconutil is used to build the .icns.
"""

import os
import subprocess
import sys

from PIL import Image, ImageChops, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
SS = 4  # supersampling factor for smooth edges
SIZE = 1024
BG = (30, 31, 36, 255)          # dark card (matches the GUI background)
CARD_INSET = 70
CYAN = (0, 174, 239)
MAGENTA = (236, 0, 140)
YELLOW = (255, 222, 23)


def _rounded(draw, box, radius, fill):
    draw.rounded_rectangle(box, radius=radius, fill=fill)


def _circle_layer(canvas, center, r, color):
    """A white RGB layer with one filled color circle (for multiply blending)."""
    layer = Image.new("RGB", canvas, (255, 255, 255))
    d = ImageDraw.Draw(layer)
    cx, cy = center
    d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=color)
    return layer


def build_master():
    w = SIZE * SS
    img = Image.new("RGBA", (w, w), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Card background
    inset = CARD_INSET * SS
    _rounded(draw, (inset, inset, w - inset, w - inset),
             radius=180 * SS, fill=BG)

    # Inner white "page"
    pad = 150 * SS
    _rounded(draw, (pad, pad, w - pad, w - pad),
             radius=90 * SS, fill=(248, 248, 248, 255))

    # Overlapping CMYK circles, multiplied together for true process-color look.
    r = 200 * SS
    cx, cy = w // 2, int(w * 0.46)
    off = 120 * SS
    centers = [(cx, cy - off), (cx - off, cy + off // 1), (cx + off, cy + off)]
    # arrange as a triangle: top, bottom-left, bottom-right
    centers = [
        (cx, cy - int(off * 0.9)),
        (cx - int(off * 0.95), cy + int(off * 0.7)),
        (cx + int(off * 0.95), cy + int(off * 0.7)),
    ]
    blend = Image.new("RGB", (w, w), (255, 255, 255))
    for ctr, col in zip(centers, (CYAN, MAGENTA, YELLOW)):
        blend = ImageChops.multiply(blend, _circle_layer((w, w), ctr, r, col))

    # Mask the blended circles so only the union of the three disks shows.
    mask = Image.new("L", (w, w), 0)
    md = ImageDraw.Draw(mask)
    for (mx, my) in centers:
        md.ellipse((mx - r, my - r, mx + r, my + r), fill=255)
    img.paste(blend, (0, 0), mask)

    # Magnifier: ring + handle over the lower-right.
    ring_c = (60, 64, 74, 255)
    lx, ly, lr = int(w * 0.66), int(w * 0.66), 150 * SS
    lw = 34 * SS
    draw.ellipse((lx - lr, ly - lr, lx + lr, ly + lr), outline=ring_c, width=lw)
    # handle
    import math
    ang = math.radians(45)
    hx0 = lx + int((lr + lw / 2) * math.cos(ang))
    hy0 = ly + int((lr + lw / 2) * math.sin(ang))
    hx1 = hx0 + int(150 * SS * math.cos(ang))
    hy1 = hy0 + int(150 * SS * math.sin(ang))
    draw.line((hx0, hy0, hx1, hy1), fill=ring_c, width=46 * SS)
    draw.ellipse((hx1 - 24 * SS, hy1 - 24 * SS, hx1 + 24 * SS, hy1 + 24 * SS),
                 fill=ring_c)

    return img.resize((SIZE, SIZE), Image.LANCZOS)


def main():
    master = build_master()
    png = os.path.join(HERE, "icon.png")
    master.save(png)
    print("wrote", png)

    # Windows .ico
    ico = os.path.join(HERE, "icon.ico")
    master.save(ico, sizes=[(16, 16), (24, 24), (32, 32), (48, 48),
                            (64, 64), (128, 128), (256, 256)])
    print("wrote", ico)

    # macOS .icns via iconutil (falls back to Pillow if unavailable)
    icns = os.path.join(HERE, "icon.icns")
    iconset = os.path.join(HERE, "icon.iconset")
    if sys.platform == "darwin":
        os.makedirs(iconset, exist_ok=True)
        spec = [(16, ""), (16, "@2x"), (32, ""), (32, "@2x"),
                (128, ""), (128, "@2x"), (256, ""), (256, "@2x"),
                (512, ""), (512, "@2x")]
        for base, suffix in spec:
            px = base * (2 if suffix else 1)
            name = f"icon_{base}x{base}{suffix}.png"
            master.resize((px, px), Image.LANCZOS).save(os.path.join(iconset, name))
        subprocess.run(["iconutil", "-c", "icns", iconset, "-o", icns], check=True)
        print("wrote", icns)
    else:
        try:
            master.save(icns)
            print("wrote", icns, "(Pillow)")
        except Exception as exc:
            print("skipped .icns:", exc)


if __name__ == "__main__":
    main()
