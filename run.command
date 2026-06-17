#!/bin/bash
# Double-click this file (or run it) to launch the PDF Color Check app.
cd "$(dirname "$0")"
exec python3 -m checkpdf.gui
