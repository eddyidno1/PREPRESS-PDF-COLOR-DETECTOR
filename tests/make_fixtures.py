"""Generate PDFs with known color content for testing the detector.

We build content streams by hand with pikepdf so the exact color operators
and colorspaces are known:

    cmyk_only.pdf  — only `k` (CMYK) and `g` (gray) fills        -> PASS
    has_rgb.pdf    — page 1 CMYK, page 2 an RGB rect + RGB image  -> FAIL
    has_spot.pdf   — a Separation (PANTONE-style) fill            -> FAIL
"""

import os

import pikepdf
from pikepdf import Array, Dictionary, Name


def _add_page(pdf, content, resources=None, size=(400, 400)):
    page = pdf.add_blank_page(page_size=size)
    page.Contents = pdf.make_stream(content)
    page.Resources = resources if resources is not None else Dictionary()
    return page


def make_cmyk_only(path):
    pdf = pikepdf.Pdf.new()
    _add_page(pdf, b"0 0 0 1 k 50 50 300 300 re f 0.5 g 100 100 60 60 re f")
    pdf.save(path)


def make_has_rgb(path):
    pdf = pikepdf.Pdf.new()
    # Page 1: clean CMYK
    _add_page(pdf, b"0 0 0 1 k 50 50 300 300 re f")

    # Page 2: an RGB rectangle and a tiny RGB image
    img = pdf.make_stream(bytes([255, 0, 0]) * 4)  # 2x2 red, DeviceRGB
    img.Type = Name.XObject
    img.Subtype = Name.Image
    img.Width = 2
    img.Height = 2
    img.ColorSpace = Name.DeviceRGB
    img.BitsPerComponent = 8
    res = Dictionary(XObject=Dictionary(Im0=img))
    content = (b"q 1 0 0 rg 50 250 200 100 re f Q "
               b"q 100 0 0 100 150 40 cm /Im0 Do Q")
    _add_page(pdf, content, resources=res)
    pdf.save(path)


def make_has_spot(path):
    pdf = pikepdf.Pdf.new()
    tint = pdf.make_indirect(Dictionary(
        FunctionType=2, Domain=Array([0, 1]),
        C0=Array([0, 0, 0, 0]), C1=Array([0, 1, 1, 0]), N=1,
    ))
    sep = Array([Name.Separation, Name("/PANTONE_Red"), Name.DeviceCMYK, tint])
    res = Dictionary(ColorSpace=Dictionary(CS0=sep))
    content = b"/CS0 cs 1 scn 50 50 200 200 re f"
    _add_page(pdf, content, resources=res)
    pdf.save(path)


def make_white_overprint(path):
    """Three CMYK rectangles exercising the white-overprint logic:
      1. white (0 0 0 0) with overprint ON   -> FLAGGED
      2. black (0 0 0 1) with overprint ON    -> not white, ok
      3. white (0 0 0 0) with overprint OFF   -> not overprinting, ok
    """
    pdf = pikepdf.Pdf.new()
    on = Dictionary(Type=Name.ExtGState, OP=True, op=True)
    off = Dictionary(Type=Name.ExtGState, OP=False, op=False)
    res = Dictionary(ExtGState=Dictionary(GSon=on, GSoff=off))
    content = (
        b"/GSon gs 0 0 0 0 k 40 40 150 150 re f "      # white + overprint -> FLAG
        b"0 0 0 1 k 40 230 150 120 re f "               # black + overprint -> ok
        b"/GSoff gs 0 0 0 0 k 230 40 120 120 re f"      # white, overprint off -> ok
    )
    _add_page(pdf, content, resources=res)
    pdf.save(path)


def build_all(outdir):
    os.makedirs(outdir, exist_ok=True)
    paths = {
        "cmyk_only": os.path.join(outdir, "cmyk_only.pdf"),
        "has_rgb": os.path.join(outdir, "has_rgb.pdf"),
        "has_spot": os.path.join(outdir, "has_spot.pdf"),
        "white_overprint": os.path.join(outdir, "white_overprint.pdf"),
    }
    make_cmyk_only(paths["cmyk_only"])
    make_has_rgb(paths["has_rgb"])
    make_has_spot(paths["has_spot"])
    make_white_overprint(paths["white_overprint"])
    return paths


if __name__ == "__main__":
    here = os.path.join(os.path.dirname(__file__), "fixtures")
    for name, p in build_all(here).items():
        print(f"{name}: {p}")
