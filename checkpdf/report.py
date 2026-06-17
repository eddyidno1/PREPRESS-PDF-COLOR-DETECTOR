"""Build a PDF report from a :class:`detector.Report`.

The report has a summary page (PASS / FAIL, counts, affected pages) followed by
one detail page per flagged source page: a thumbnail of the page with the RGB
areas boxed in red and spot-color areas in orange, plus a list of findings.
"""

from __future__ import annotations

import datetime
import os

import fitz  # PyMuPDF

PAGE_W, PAGE_H = 612, 792           # US Letter, points
MARGIN = 50
RGB_COLOR = (0.85, 0.1, 0.1)        # red for RGB findings
SPOT_COLOR = (0.95, 0.55, 0.0)      # orange for spot findings
WHITE_OP_COLOR = (0.0, 0.35, 0.9)   # blue for white-overprint findings
PASS_COLOR = (0.13, 0.55, 0.13)
FAIL_COLOR = (0.80, 0.10, 0.10)
GREY = (0.4, 0.4, 0.4)

_KIND_COLORS = {"rgb": RGB_COLOR, "spot": SPOT_COLOR,
                "white_overprint": WHITE_OP_COLOR}
_KIND_LABELS = {"rgb": "RGB", "spot": "SPOT", "white_overprint": "WHITE-OP"}


def _kind_color(kind):
    return _KIND_COLORS.get(kind, RGB_COLOR)


def build_report(report, src_pdf_path, out_path=None) -> str:
    """Create the report PDF and return its path."""
    if out_path is None:
        base, _ = os.path.splitext(str(src_pdf_path))
        out_path = base + "_color_report.pdf"

    doc = fitz.open()
    src = None
    try:
        src = fitz.open(src_pdf_path)
    except Exception:
        src = None

    _summary_page(doc, report, src_pdf_path)

    if src is not None:
        for pno in report.pages_with_findings:
            try:
                _detail_page(doc, src, report, pno)
            except Exception as exc:
                _note_page(doc, f"Page {pno}: could not render thumbnail ({exc}).")

    doc.save(out_path, garbage=4, deflate=True)
    doc.close()
    if src is not None:
        src.close()
    return out_path


def _summary_page(doc, report, src_pdf_path):
    page = doc.new_page(width=PAGE_W, height=PAGE_H)
    x = MARGIN
    y = 70

    page.insert_text((x, y), "PDF Color Check Report", fontsize=22,
                     fontname="helv", color=(0, 0, 0))
    y += 28
    page.insert_text((x, y), os.path.basename(str(src_pdf_path)),
                     fontsize=11, fontname="helv", color=GREY)
    y += 14
    page.insert_text((x, y), datetime.datetime.now().strftime("Generated %Y-%m-%d %H:%M"),
                     fontsize=9, fontname="helv", color=GREY)
    y += 30

    # Verdict banner
    if report.encrypted or report.errors and report.page_count == 0:
        verdict, color = "COULD NOT ANALYZE", GREY
    elif report.passed:
        verdict, color = "PASS  -  CMYK / grayscale, no overprint issues", PASS_COLOR
    else:
        problems = []
        if report.rgb_count or report.spot_count:
            problems.append("RGB / spot color")
        if report.white_overprint_count:
            problems.append("white overprint")
        verdict = "FAIL  -  " + " and ".join(problems) + " found"
        color = FAIL_COLOR

    banner = fitz.Rect(x, y, PAGE_W - MARGIN, y + 40)
    page.draw_rect(banner, color=color, fill=color, width=0)
    page.insert_textbox(banner + (8, 11, -8, 0), verdict, fontsize=14,
                        fontname="hebo", color=(1, 1, 1))
    y += 60

    if not report.encrypted:
        page.insert_text((x, y), f"Pages in document: {report.page_count}",
                         fontsize=11, fontname="helv")
        y += 24

        # --- Color section ---
        page.insert_text((x, y), "RGB / spot color:", fontsize=11, fontname="hebo")
        y += 18
        if report.color_findings:
            page.insert_text((x + 12, y),
                             f"RGB findings: {report.rgb_count}    "
                             f"Spot findings: {report.spot_count}",
                             fontsize=11, fontname="helv")
            y += 16
            cpages = sorted({f.page for f in report.color_findings})
            page.insert_text((x + 12, y), "On pages: " + ", ".join(map(str, cpages)),
                             fontsize=11, fontname="helv")
        else:
            page.insert_text((x + 12, y), "None - all CMYK / grayscale.",
                             fontsize=11, fontname="helv", color=PASS_COLOR)
        y += 26

        # --- White overprint section (always stated explicitly) ---
        page.insert_text((x, y), "White overprint:", fontsize=11, fontname="hebo")
        y += 18
        if report.white_overprint_count:
            wpages = sorted({f.page for f in report.findings
                             if f.kind == "white_overprint"})
            page.insert_text((x + 12, y),
                             f"{report.white_overprint_count} white-overprint "
                             f"object(s) found on pages: " + ", ".join(map(str, wpages)),
                             fontsize=11, fontname="helv", color=FAIL_COLOR)
        else:
            page.insert_text((x + 12, y), "No white overprint found.",
                             fontsize=11, fontname="helv", color=PASS_COLOR)
        y += 24

    if report.errors:
        y += 10
        page.insert_text((x, y), "Notes:", fontsize=11, fontname="hebo")
        y += 16
        for err in report.errors[:8]:
            page.insert_text((x + 10, y), "• " + err, fontsize=10,
                             fontname="helv", color=GREY)
            y += 14

    # Legend
    if not report.passed and not report.encrypted:
        y += 16
        page.insert_text((x, y), "Legend (box colors on page thumbnails):",
                         fontsize=10, fontname="hebo")
        y += 16
        for col, label in ((RGB_COLOR, "RGB color"),
                           (SPOT_COLOR, "Spot / Separation color (e.g. Pantone)"),
                           (WHITE_OP_COLOR, "White object set to overprint")):
            page.draw_rect(fitz.Rect(x, y - 8, x + 14, y + 4), color=col, fill=col)
            page.insert_text((x + 22, y), label, fontsize=10, fontname="helv")
            y += 18


def _detail_page(doc, src, report, pno):
    findings = report.findings_for_page(pno)
    page = doc.new_page(width=PAGE_W, height=PAGE_H)
    x = MARGIN
    y = 56

    page.insert_text((x, y), f"Page {pno}", fontsize=18, fontname="hebo")
    rgb_n = sum(1 for f in findings if f.kind == "rgb")
    spot_n = sum(1 for f in findings if f.kind == "spot")
    wop_n = sum(1 for f in findings if f.kind == "white_overprint")
    page.insert_text((x, y + 18),
                     f"{rgb_n} RGB, {spot_n} spot, {wop_n} white-overprint finding(s)",
                     fontsize=10, fontname="helv", color=GREY)
    y += 36

    # Render the source page with highlight boxes drawn on it.
    spage = src[pno - 1]
    page_h = spage.rect.height
    for f in findings:
        color = _kind_color(f.kind)
        if f.bbox is None:
            # page-level finding (e.g. shading): outline the whole page
            r = spage.rect + (1, 1, -1, -1)
        else:
            r = _to_fitz_rect(f.bbox, page_h)
            # inflate so the marker sits just outside the object and stays
            # visible even when the object itself is the same color.
            r = r + (-3, -3, 3, 3)
        if r.width < 3:
            r.x1 = r.x0 + 3
        if r.height < 3:
            r.y1 = r.y0 + 3
        try:
            spage.draw_rect(r, color=color, width=1.8)
        except Exception:
            pass

    pix = spage.get_pixmap(dpi=150)

    # Fit the thumbnail into the available region preserving aspect ratio.
    region_top = y
    region_bottom = PAGE_H - 230
    region = fitz.Rect(x, region_top, PAGE_W - MARGIN, region_bottom)
    img_rect = _fit_rect(pix.width, pix.height, region)
    page.insert_image(img_rect, pixmap=pix)
    page.draw_rect(img_rect, color=GREY, width=0.5)

    # Findings list at the bottom.
    ly = region_bottom + 24
    page.insert_text((x, ly), "Findings on this page:", fontsize=11, fontname="hebo")
    ly += 18
    shown = findings[:9]
    for f in shown:
        loc = _format_loc(f.bbox, page_h)
        label = _KIND_LABELS.get(f.kind, f.kind.upper())
        text = f"[{label}] {f.element} - {f.detail or f.category}  @ {loc}"
        page.draw_rect(fitz.Rect(x + 6, ly - 7, x + 14, ly + 1),
                       color=_kind_color(f.kind), fill=_kind_color(f.kind))
        page.insert_text((x + 20, ly), text, fontsize=9, fontname="helv")
        ly += 15
    if len(findings) > len(shown):
        page.insert_text((x + 8, ly), f"…and {len(findings) - len(shown)} more.",
                         fontsize=9, fontname="helv", color=GREY)


def _note_page(doc, message):
    page = doc.new_page(width=PAGE_W, height=PAGE_H)
    page.insert_textbox(fitz.Rect(MARGIN, 80, PAGE_W - MARGIN, 200),
                        message, fontsize=11, fontname="helv", color=GREY)


def _to_fitz_rect(bbox, page_height):
    x0, y0, x1, y1 = bbox
    # PDF user space has a bottom-left origin; fitz uses top-left.
    r = fitz.Rect(x0, page_height - y1, x1, page_height - y0)
    r.normalize()
    return r


def _fit_rect(pw, ph, region):
    rw, rh = region.width, region.height
    if pw <= 0 or ph <= 0:
        return region
    scale = min(rw / pw, rh / ph)
    w, h = pw * scale, ph * scale
    cx = region.x0 + (rw - w) / 2
    cy = region.y0
    return fitz.Rect(cx, cy, cx + w, cy + h)


def _format_loc(bbox, page_height):
    if bbox is None:
        return "page-level"
    x0, y0, x1, y1 = bbox
    return f"x{x0:.0f}-{x1:.0f}, y{y0:.0f}-{y1:.0f} pt"
