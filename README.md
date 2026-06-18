# PDF Color Check — RGB / Spot Detector

A small macOS app that checks whether a PDF is **print-safe** (pure **CMYK** /
**grayscale**) or contains **RGB** or **spot/Separation** colors (e.g. Pantone).
It produces a **PDF report** with a PASS/FAIL verdict, the list of affected
pages, and a thumbnail of each flagged page with the offending areas **boxed in
red (RGB)** or **orange (spot)**.

It also checks for **white overprint** — a white object set to overprint, which
disappears on press because it knocks nothing out. The report always states the
result explicitly ("No white overprint found." when there is none).

- ✅ **Pass:** DeviceCMYK, DeviceGray, and no white-overprint objects
- 🚫 **Flagged:** DeviceRGB, RGB-based ICC / CalRGB / Lab / Indexed-on-RGB,
  Separation / DeviceN spot colors, and white objects set to overprint

## How it works

The detector parses the PDF's actual content streams with **pikepdf** (libqpdf),
reading the real color operators (`rg`, `k`, `cs`/`scn`, …), the colorspace
resources, and the overprint flags from ExtGState (`/OP`, `/op`). This is more
reliable than rendering-based tools, which normalize every color to sRGB and
lose the CMYK-vs-RGB distinction. A small graphics-state interpreter tracks the
transformation matrix (for bounding boxes), the current color values (to detect
white), and the overprint state. The report is rendered and assembled with
**PyMuPDF**.

## Install

```bash
python3 -m pip install --only-binary=:all: -r requirements.txt
```

## Use

**Standalone Mac app (no Terminal needed):** open `dist/PDF Color Check.app`
(drag it to /Applications if you like), then drop a PDF onto the window. The
report opens automatically and is saved as `<yourfile>_color_report.pdf` next
to the original. The first launch may need a right-click → **Open** to get past
Gatekeeper, since the app is unsigned.

**Drag-and-drop from source:** double-click `run.command` (or run
`./run.command`), then drop a PDF onto the window.

**Command line:**

```bash
python3 -m checkpdf myfile.pdf [more.pdf ...]
```

Prints PASS / FAIL per file and writes a report PDF next to each input. Exit
code is non-zero if any file fails.

## Project layout

```
checkpdf/
  colorspace.py   # classify a PDF colorspace -> rgb/cmyk/gray/spot/...
  detector.py     # content-stream interpreter -> list of findings + verdict
  report.py       # thumbnails + highlight boxes + summary report PDF
  gui.py          # tkinter / tkinterdnd2 drag-and-drop window
  cli.py          # `python -m checkpdf`
tests/
  make_fixtures.py  # build known CMYK / RGB / spot test PDFs
  test_detector.py  # verdict, finding counts, bbox accuracy
```

Run the tests with `python3 -m pytest tests/`.

## Building the standalone app

PyInstaller cannot cross-build: build **on the OS you want to run on**.
`build.py` is the cross-platform driver and picks the right options per OS.

**macOS:**

```bash
python3 -m pip install --only-binary=:all: pyinstaller pyinstaller-hooks-contrib
python3 build.py          # -> dist/PDF Color Check.app
```

**Windows:** copy this whole project folder to a Windows PC that has
**64-bit Python 3.10–3.13** installed (tick *"Add Python to PATH"* in the
installer). Note the PDF libraries ship 64-bit wheels only for 3.10–3.13 —
**Python 3.14+ or 32-bit Python will not work**; if that's all you have, install
the [64-bit Python 3.12](https://www.python.org/downloads/release/python-3129/)
("Windows installer (64-bit)"). Then **double-click `build_windows.bat`** — it
auto-selects a compatible interpreter, installs the dependencies, builds the
app, and zips it:

```
dist\PDF Color Check\PDF Color Check.exe   (the app)
dist\PDF-Color-Check-Windows.zip           (release-ready zip)
```

To run it on yet another Windows PC, copy `dist\PDF-Color-Check-Windows.zip`,
unzip it, and launch `PDF Color Check.exe` inside the folder. Windows
SmartScreen may warn the first time (unsigned app) — click *More info → Run
anyway*.

## Releases (pre-built downloads)

The built apps are **not** committed to the repo (binaries don't belong in
git). To share a ready-to-run app so others don't have to build it, attach the
built artifacts to a [GitHub Release](https://github.com/eddyidno1/PREPRESS-PDF-COLOR-DETECTOR/releases).
On Windows, `build_windows.bat` already produces an upload-ready
`dist\PDF-Color-Check-Windows.zip`; on macOS, zip the app with
`ditto -c -k --sequesterRsrc --keepParent "dist/PDF Color Check.app" dist/PDF-Color-Check-macOS.zip`.
Upload the zip(s) to a release and users download and run them directly — no
Python needed.

## Notes & limitations

- **Text bounding boxes are approximate** (we don't load per-glyph font
  metrics); vector and image boxes are precise. The PASS/FAIL verdict and the
  per-page list are exact regardless.
- Classification is by **declared colorspace**, the standard preflight
  definition of "RGB present". Overprint/ink simulation is out of scope.
- **Rotated pages** (`/Rotate`): highlight box placement assumes unrotated
  pages; detection is unaffected.
- **Password-protected PDFs** are reported as "could not analyze" rather than
  guessed.
