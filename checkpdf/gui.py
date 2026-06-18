"""Drag-and-drop GUI: drop a PDF, get a color report.

Uses tkinterdnd2 for file drop when available, and always offers a
"Choose PDF…" button as a fallback.
"""

import os
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import filedialog

from .detector import analyze
from .report import build_report

try:
    from tkinterdnd2 import DND_FILES, TkinterDnD
    _HAS_DND = True
except Exception:  # pragma: no cover - depends on platform install
    _HAS_DND = False


BG = "#1e1f24"
DROP_BG = "#2a2c33"
ACCENT = "#4a90d9"
PASS_BG = "#1f7a33"
FAIL_BG = "#b21f1f"


def _resource(*parts):
    """Locate a bundled data file, both when frozen and from source."""
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.dirname(__file__)))
    return os.path.join(base, *parts)


def _set_window_icon(root):
    png = _resource("assets", "icon.png")
    if os.path.exists(png):
        try:
            img = tk.PhotoImage(file=png)
            root.iconphoto(True, img)
            root._icon_ref = img  # keep a reference so it isn't garbage-collected
        except Exception:
            pass


def _open_file(path):
    try:
        if sys.platform == "darwin":
            subprocess.run(["open", path], check=False)
        elif os.name == "nt":
            os.startfile(path)  # type: ignore[attr-defined]
        else:
            subprocess.run(["xdg-open", path], check=False)
    except Exception:
        pass


class App:
    def __init__(self, root):
        self.root = root
        root.title("PDF Color Check — RGB / Spot Detector")
        root.geometry("560x460")
        root.configure(bg=BG)

        tk.Label(root, text="PDF Color Check", bg=BG, fg="white",
                 font=("Helvetica", 20, "bold")).pack(pady=(22, 2))
        tk.Label(root, text="Flags RGB and spot colors · CMYK and grayscale pass",
                 bg=BG, fg="#9aa0aa", font=("Helvetica", 11)).pack()

        self.drop = tk.Label(
            root,
            text=("⬇  Drag a PDF here\n\n" if _HAS_DND else "")
                 + "or click to choose a file",
            bg=DROP_BG, fg="#c7ccd6", font=("Helvetica", 13),
            width=46, height=8, relief="ridge", bd=2,
        )
        self.drop.pack(pady=20, padx=24, fill="both", expand=False)
        self.drop.bind("<Button-1>", lambda e: self.choose())

        self.status = tk.Label(root, text="Ready.", bg=BG, fg="#9aa0aa",
                               font=("Helvetica", 11), wraplength=500, justify="center")
        self.status.pack(pady=4)

        self.banner = tk.Label(root, text="", bg=BG, fg="white",
                               font=("Helvetica", 15, "bold"))
        self.banner.pack(pady=6, fill="x", padx=24)

        btns = tk.Frame(root, bg=BG)
        btns.pack(pady=6)
        tk.Button(btns, text="Choose PDF…", command=self.choose,
                  font=("Helvetica", 12)).pack()

        if _HAS_DND:
            self.drop.drop_target_register(DND_FILES)
            self.drop.dnd_bind("<<Drop>>", self.on_drop)

    # ------------------------------------------------------------------ #
    def choose(self):
        path = filedialog.askopenfilename(
            title="Choose a PDF",
            filetypes=[("PDF files", "*.pdf"), ("All files", "*.*")],
        )
        if path:
            self.process(path)

    def on_drop(self, event):
        path = self._parse_drop(event.data)
        if path:
            self.process(path)

    @staticmethod
    def _parse_drop(data):
        data = data.strip()
        if data.startswith("{") and data.endswith("}"):
            data = data[1:-1]
        # take the first path if several were dropped
        return data.split("} {")[0].strip("{}").strip()

    # ------------------------------------------------------------------ #
    def process(self, path):
        self.banner.config(text="", bg=BG)
        self.status.config(text=f"Analyzing {os.path.basename(path)} …",
                           fg="#c7ccd6")
        self.root.update_idletasks()
        threading.Thread(target=self._work, args=(path,), daemon=True).start()

    def _work(self, path):
        try:
            report = analyze(path)
            out = build_report(report, path)
        except Exception as exc:
            self.root.after(0, self._show_error, str(exc))
            return
        self.root.after(0, self._show_result, report, out)

    def _show_error(self, msg):
        self.banner.config(text="ERROR", bg=FAIL_BG)
        self.status.config(text=msg, fg="#e7a0a0")

    def _show_result(self, report, out):
        if report.encrypted:
            self.banner.config(text="COULD NOT ANALYZE", bg="#555")
            self.status.config(text="PDF is password-protected.", fg="#e7c08a")
            return
        if report.passed:
            self.banner.config(text="✓  PASS — CMYK / grayscale only", bg=PASS_BG)
            self.status.config(
                text=f"No RGB or spot colors found across {report.page_count} page(s).\n"
                     f"Report saved and opened.", fg="#bfe6c4")
        else:
            self.banner.config(text="✗  FAIL — RGB or spot color found", bg=FAIL_BG)
            self.status.config(
                text=f"RGB: {report.rgb_count}   Spot: {report.spot_count}   "
                     f"Pages: {', '.join(map(str, report.pages_with_findings))}\n"
                     f"Report saved and opened.", fg="#f0bcbc")
        _open_file(out)


def main():
    root = TkinterDnD.Tk() if _HAS_DND else tk.Tk()
    _set_window_icon(root)
    App(root)
    # Smoke-test hook: launch, then quit, so packaging can be verified
    # headlessly. If the env var is a PDF path, run a real analyze->report
    # cycle first to confirm the native libraries work when frozen.
    selftest = os.environ.get("CHECKPDF_SELFTEST")
    if selftest:
        if os.path.isfile(selftest):
            rep = analyze(selftest)
            out = build_report(rep, selftest)
            print(f"SELFTEST passed={rep.passed} rgb={rep.rgb_count} "
                  f"spot={rep.spot_count} report={out}")
        root.after(600, root.destroy)
    root.mainloop()


if __name__ == "__main__":
    main()
