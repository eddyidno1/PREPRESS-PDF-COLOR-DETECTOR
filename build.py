"""Cross-platform build driver for the PDF Color Check app.

Runs PyInstaller with the right options for the current OS. Used both locally
and by the GitHub Actions workflow (.github/workflows/build.yml).

    python build.py

Output:
    macOS    -> dist/PDF Color Check.app
    Windows  -> dist/PDF Color Check/PDF Color Check.exe  (one-folder)
    Linux    -> dist/PDF Color Check/PDF Color Check
"""

import sys

import PyInstaller.__main__

APP_NAME = "PDF Color Check"


def main():
    args = [
        "app_main.py",
        "--noconfirm",
        "--windowed",
        "--name", APP_NAME,
        "--collect-all", "tkinterdnd2",
        "--collect-submodules", "pikepdf",
    ]
    if sys.platform == "darwin":
        args += ["--osx-bundle-identifier", "com.eddyzhou.pdfcolorcheck"]

    PyInstaller.__main__.run(args)


if __name__ == "__main__":
    main()
