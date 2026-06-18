"""Cross-platform build driver for the PDF Color Check app.

Runs PyInstaller with the right options for the current OS. Used both locally
and by the GitHub Actions workflow (.github/workflows/build.yml).

    python build.py

Output:
    macOS    -> dist/PDF Color Check.app
    Windows  -> dist/PDF Color Check/PDF Color Check.exe  (one-folder)
    Linux    -> dist/PDF Color Check/PDF Color Check
"""

import os
import sys

import PyInstaller.__main__

APP_NAME = "PDF Color Check"
HERE = os.path.dirname(os.path.abspath(__file__))


def main():
    sep = ";" if os.name == "nt" else ":"
    png = os.path.join("assets", "icon.png")
    args = [
        "app_main.py",
        "--noconfirm",
        "--windowed",
        "--name", APP_NAME,
        "--collect-all", "tkinterdnd2",
        "--collect-submodules", "pikepdf",
        # bundle the PNG so the running window/taskbar can use it
        "--add-data", f"{png}{sep}assets",
    ]
    # Platform-specific app icon (embedded in the .app / .exe).
    icon = os.path.join(HERE, "assets",
                        "icon.icns" if sys.platform == "darwin" else "icon.ico")
    if os.path.exists(icon):
        args += ["--icon", icon]
    if sys.platform == "darwin":
        args += ["--osx-bundle-identifier", "com.eddyzhou.pdfcolorcheck"]

    PyInstaller.__main__.run(args)


if __name__ == "__main__":
    main()
