"""Analyze a PDF's content streams and report RGB / spot color usage.

The analysis walks each page's content stream with a small graphics-state
interpreter that tracks the current transformation matrix (CTM) and the active
fill/stroke colorspaces. Whenever a painting operator runs while a flagged
colorspace (RGB-class or spot) is active, a :class:`Finding` is recorded with
the painted object's bounding box in PDF user space.

Detection of *whether* a color category is present is exact. Bounding boxes for
vector fills/strokes and images are precise; text boxes are approximate (we do
not load per-glyph font metrics).
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field

import pikepdf

from .colorspace import classify, flagged_kind, is_array, is_name

IDENTITY = (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)

FILL_PAINT = {"f", "F", "f*", "b", "b*", "B", "B*"}
STROKE_PAINT = {"S", "s", "b", "b*", "B", "B*"}
PATH_CLEAR = {"n", "f", "F", "f*", "s", "S", "b", "b*", "B", "B*"}


# --------------------------------------------------------------------------- #
# Matrix helpers (row-vector convention: [x y 1] * M)
# --------------------------------------------------------------------------- #
def mat_mul(m, n):
    a1, b1, c1, d1, e1, f1 = m
    a2, b2, c2, d2, e2, f2 = n
    return (
        a1 * a2 + b1 * c2,
        a1 * b2 + b1 * d2,
        c1 * a2 + d1 * c2,
        c1 * b2 + d1 * d2,
        e1 * a2 + f1 * c2 + e2,
        e1 * b2 + f1 * d2 + f2,
    )


def apply_pt(m, x, y):
    a, b, c, d, e, f = m
    return (a * x + c * y + e, b * x + d * y + f)


# --------------------------------------------------------------------------- #
# Data model
# --------------------------------------------------------------------------- #
@dataclass
class Finding:
    page: int            # 1-based page number
    kind: str            # 'rgb' or 'spot'
    element: str         # 'text' | 'vector' | 'image' | 'shading'
    category: str        # underlying category ('rgb', 'lab', 'spot')
    detail: str          # colorspace note / spot colorant name
    bbox: tuple | None   # (x0, y0, x1, y1) in PDF user space, or None


@dataclass
class Report:
    path: str
    page_count: int = 0
    findings: list = field(default_factory=list)
    errors: list = field(default_factory=list)
    encrypted: bool = False

    @property
    def passed(self) -> bool:
        return not self.findings and not self.errors

    @property
    def pages_with_findings(self):
        return sorted({f.page for f in self.findings})

    @property
    def rgb_count(self):
        return sum(1 for f in self.findings if f.kind == "rgb")

    @property
    def spot_count(self):
        return sum(1 for f in self.findings if f.kind == "spot")

    @property
    def white_overprint_count(self):
        return sum(1 for f in self.findings if f.kind == "white_overprint")

    @property
    def color_findings(self):
        """RGB / spot findings only (excludes white-overprint)."""
        return [f for f in self.findings if f.kind in ("rgb", "spot")]

    def findings_for_page(self, page):
        return [f for f in self.findings if f.page == page]


# --------------------------------------------------------------------------- #
# Graphics state
# --------------------------------------------------------------------------- #
class _GState:
    __slots__ = ("ctm", "fill", "stroke", "fill_detail", "stroke_detail",
                 "fill_val", "stroke_val", "fill_op", "stroke_op")

    def __init__(self, ctm):
        self.ctm = ctm
        self.fill = "gray"          # PDF default fill colorspace is DeviceGray
        self.stroke = "gray"
        self.fill_detail = ""
        self.stroke_detail = ""
        self.fill_val = (0.0,)      # current fill color components (default black)
        self.stroke_val = (0.0,)
        self.fill_op = False        # fill overprint (ExtGState /op)
        self.stroke_op = False      # stroke overprint (ExtGState /OP)

    def clone(self):
        g = _GState(self.ctm)
        g.fill, g.stroke = self.fill, self.stroke
        g.fill_detail, g.stroke_detail = self.fill_detail, self.stroke_detail
        g.fill_val, g.stroke_val = self.fill_val, self.stroke_val
        g.fill_op, g.stroke_op = self.fill_op, self.stroke_op
        return g


def _resolve_classify(cs_obj, resources):
    """Classify a colorspace, resolving named entries via /Resources/ColorSpace."""
    if is_name(cs_obj):
        s = str(cs_obj)
        if s not in ("/DeviceRGB", "/DeviceGray", "/DeviceCMYK", "/Pattern",
                     "/G", "/RGB", "/CMYK"):
            csd = resources.get("/ColorSpace") if resources is not None else None
            if csd is not None:
                try:
                    if s in csd:
                        return classify(csd[s])
                except Exception:
                    pass
    return classify(cs_obj)


# --------------------------------------------------------------------------- #
# Public entry point
# --------------------------------------------------------------------------- #
def analyze(pdf_path) -> Report:
    report = Report(path=str(pdf_path))
    try:
        pdf = pikepdf.open(pdf_path)
    except pikepdf.PasswordError:
        report.encrypted = True
        report.errors.append("PDF is password-protected and cannot be analyzed.")
        return report
    except Exception as exc:  # corrupt / not a PDF
        report.errors.append(f"Could not open PDF: {exc}")
        return report

    with pdf:
        report.page_count = len(pdf.pages)
        for i, page in enumerate(pdf.pages):
            try:
                resources = page.get("/Resources")
                instructions = pikepdf.parse_content_stream(page)
                _run(instructions, IDENTITY, resources, i + 1,
                     report.findings, depth=0, seen=set())
            except Exception as exc:
                report.errors.append(f"Page {i + 1}: could not parse ({exc}).")
    return report


# --------------------------------------------------------------------------- #
# Content-stream interpreter
# --------------------------------------------------------------------------- #
def _run(instructions, ctm, resources, page_no, findings, depth, seen):
    if depth > 12:
        return

    gs = _GState(ctm)
    stack = []

    # current path bbox in user space, accumulated across path-construction ops
    path_bbox = [None]

    # text state
    tm = [IDENTITY]
    tlm = [IDENTITY]
    font_size = [0.0]
    leading = [0.0]

    def expand_path(x, y):
        px, py = apply_pt(gs.ctm, x, y)
        b = path_bbox[0]
        if b is None:
            path_bbox[0] = [px, py, px, py]
        else:
            b[0] = min(b[0], px); b[1] = min(b[1], py)
            b[2] = max(b[2], px); b[3] = max(b[3], py)

    for ins in instructions:
        is_image = type(ins).__name__ == "ContentStreamInlineImage"
        if is_image:
            _handle_inline_image(ins, gs, page_no, findings)
            continue

        op = str(ins.operator)
        ops = ins.operands

        # ---- graphics state stack ----
        if op == "q":
            stack.append(gs.clone())
            continue
        if op == "Q":
            if stack:
                gs = stack.pop()
            continue
        if op == "cm" and len(ops) == 6:
            gs.ctm = mat_mul(tuple(_f(o) for o in ops), gs.ctm)
            continue

        # ---- overprint (ExtGState) ----
        if op == "gs" and ops:
            _apply_extgstate(ops[0], resources, gs)
            continue

        # ---- fill color ----
        if op == "rg":
            gs.fill, gs.fill_detail = "rgb", "DeviceRGB"
            gs.fill_val = tuple(_f(o) for o in ops[:3]); continue
        if op == "g":
            gs.fill, gs.fill_detail = "gray", "DeviceGray"
            gs.fill_val = (_f(ops[0]),) if ops else (0.0,); continue
        if op == "k":
            gs.fill, gs.fill_detail = "cmyk", "DeviceCMYK"
            gs.fill_val = tuple(_f(o) for o in ops[:4]); continue
        if op == "cs":
            if ops:
                gs.fill, gs.fill_detail = _resolve_classify(ops[0], resources)
            gs.fill_val = None; continue
        if op in ("sc", "scn"):
            gs.fill_val = _numeric_operands(ops); continue
        # ---- stroke color ----
        if op == "RG":
            gs.stroke, gs.stroke_detail = "rgb", "DeviceRGB"
            gs.stroke_val = tuple(_f(o) for o in ops[:3]); continue
        if op == "G":
            gs.stroke, gs.stroke_detail = "gray", "DeviceGray"
            gs.stroke_val = (_f(ops[0]),) if ops else (0.0,); continue
        if op == "K":
            gs.stroke, gs.stroke_detail = "cmyk", "DeviceCMYK"
            gs.stroke_val = tuple(_f(o) for o in ops[:4]); continue
        if op == "CS":
            if ops:
                gs.stroke, gs.stroke_detail = _resolve_classify(ops[0], resources)
            gs.stroke_val = None; continue
        if op in ("SC", "SCN"):
            gs.stroke_val = _numeric_operands(ops); continue

        # ---- path construction ----
        if op == "m" and len(ops) >= 2:
            expand_path(_f(ops[0]), _f(ops[1])); continue
        if op == "l" and len(ops) >= 2:
            expand_path(_f(ops[0]), _f(ops[1])); continue
        if op == "c" and len(ops) >= 6:
            for j in range(0, 6, 2):
                expand_path(_f(ops[j]), _f(ops[j + 1]))
            continue
        if op in ("v", "y") and len(ops) >= 4:
            for j in range(0, 4, 2):
                expand_path(_f(ops[j]), _f(ops[j + 1]))
            continue
        if op == "re" and len(ops) >= 4:
            x, y, w, h = (_f(o) for o in ops[:4])
            for cx, cy in ((x, y), (x + w, y), (x + w, y + h), (x, y + h)):
                expand_path(cx, cy)
            continue

        # ---- painting ----
        if op in PATH_CLEAR:
            bbox = path_bbox[0]
            if bbox is not None:
                rect = tuple(bbox)
                if op in FILL_PAINT:
                    _maybe_record(findings, page_no, "vector", gs.fill,
                                  gs.fill_detail, rect)
                    _maybe_white_overprint(findings, page_no, "vector", gs.fill,
                                           gs.fill_val, gs.fill_op, rect)
                if op in STROKE_PAINT:
                    _maybe_record(findings, page_no, "vector", gs.stroke,
                                  gs.stroke_detail, rect)
                    _maybe_white_overprint(findings, page_no, "vector", gs.stroke,
                                           gs.stroke_val, gs.stroke_op, rect)
            path_bbox[0] = None
            continue

        # ---- text ----
        if op == "BT":
            tm[0] = tlm[0] = IDENTITY; continue
        if op == "ET":
            continue
        if op == "Tf" and len(ops) >= 2:
            font_size[0] = _f(ops[1]); continue
        if op == "TL" and ops:
            leading[0] = _f(ops[0]); continue
        if op == "Td" and len(ops) >= 2:
            tlm[0] = mat_mul((1, 0, 0, 1, _f(ops[0]), _f(ops[1])), tlm[0])
            tm[0] = tlm[0]; continue
        if op == "TD" and len(ops) >= 2:
            leading[0] = -_f(ops[1])
            tlm[0] = mat_mul((1, 0, 0, 1, _f(ops[0]), _f(ops[1])), tlm[0])
            tm[0] = tlm[0]; continue
        if op == "Tm" and len(ops) == 6:
            tm[0] = tlm[0] = tuple(_f(o) for o in ops); continue
        if op == "T*":
            tlm[0] = mat_mul((1, 0, 0, 1, 0, -leading[0]), tlm[0])
            tm[0] = tlm[0]; continue
        if op in ("Tj", "'", '"'):
            if op != "Tj":  # ' and " move to next line first
                tlm[0] = mat_mul((1, 0, 0, 1, 0, -leading[0]), tlm[0])
                tm[0] = tlm[0]
            text = ops[-1] if ops else None
            _show_text(_char_count(text), gs, tm, font_size[0], page_no, findings)
            continue
        if op == "TJ" and ops:
            _show_text(_tj_count(ops[0]), gs, tm, font_size[0], page_no, findings)
            continue

        # ---- XObjects & shadings ----
        if op == "Do" and ops:
            _handle_xobject(ops[0], gs, resources, page_no, findings, depth, seen)
            continue
        if op == "sh" and ops:
            _handle_shading(ops[0], resources, page_no, findings)
            continue


def _show_text(nchars, gs, tm, font_size, page_no, findings):
    kind = flagged_kind(gs.fill)
    if font_size <= 0:
        font_size = 1.0
    width = max(nchars, 1) * font_size * 0.5
    # text space -> user space is tm, then the current CTM
    m = mat_mul(tm[0], gs.ctm)
    # text-space corners: descender to ascender
    xs = []
    ys = []
    for cx, cy in ((0, -0.2 * font_size), (width, -0.2 * font_size),
                   (width, 0.8 * font_size), (0, 0.8 * font_size)):
        px, py = apply_pt(m, cx, cy)
        xs.append(px); ys.append(py)
    bbox = (min(xs), min(ys), max(xs), max(ys))
    if kind:
        _maybe_record(findings, page_no, "text", gs.fill, gs.fill_detail, bbox)
    _maybe_white_overprint(findings, page_no, "text", gs.fill,
                           gs.fill_val, gs.fill_op, bbox)
    # advance the text matrix so subsequent runs are positioned roughly right
    tm[0] = mat_mul((1, 0, 0, 1, width, 0), tm[0])


def _handle_inline_image(ins, gs, page_no, findings):
    try:
        ii = ins.iimage
    except Exception:
        return
    detail = "inline image"
    try:
        if getattr(ii, "is_separation", False) or getattr(ii, "is_device_n", False):
            cat = "spot"
        else:
            cat, d = classify(ii.colorspace)
            detail = "inline image " + (d or "")
    except Exception:
        return
    if flagged_kind(cat):
        bbox = _unit_square_bbox(gs.ctm)
        _maybe_record(findings, page_no, "image", cat, detail.strip(), bbox)


def _handle_xobject(name_obj, gs, resources, page_no, findings, depth, seen):
    if resources is None:
        return
    try:
        xdict = resources.get("/XObject")
        if xdict is None:
            return
        name = str(name_obj)
        if name not in xdict:
            return
        xobj = xdict[name]
    except Exception:
        return

    subtype = str(xobj.get("/Subtype")) if xobj.get("/Subtype") is not None else ""

    if subtype == "/Image":
        try:
            if bool(xobj.get("/ImageMask")):
                # Stencil mask painted with the current fill color.
                if flagged_kind(gs.fill):
                    _maybe_record(findings, page_no, "image", gs.fill,
                                  "image mask / " + gs.fill_detail,
                                  _unit_square_bbox(gs.ctm))
                return
            cs = xobj.get("/ColorSpace")
            cat, detail = _resolve_classify(cs, resources) if cs is not None else ("unknown", "")
        except Exception:
            return
        if flagged_kind(cat):
            _maybe_record(findings, page_no, "image", cat, detail,
                          _unit_square_bbox(gs.ctm))
        return

    if subtype == "/Form":
        try:
            oid = (xobj.objgen if hasattr(xobj, "objgen") else id(xobj))
        except Exception:
            oid = id(xobj)
        if oid in seen:
            return
        seen = seen | {oid}
        form_matrix = IDENTITY
        try:
            fm = xobj.get("/Matrix")
            if fm is not None and len(fm) == 6:
                form_matrix = tuple(float(v) for v in fm)
        except Exception:
            pass
        form_res = xobj.get("/Resources") or resources
        try:
            instructions = pikepdf.parse_content_stream(xobj)
        except Exception:
            return
        _run(instructions, mat_mul(form_matrix, gs.ctm), form_res,
             page_no, findings, depth + 1, seen)


def _handle_shading(name_obj, resources, page_no, findings):
    if resources is None:
        return
    try:
        shd = resources.get("/Shading")
        if shd is None:
            return
        name = str(name_obj)
        if name not in shd:
            return
        cs = shd[name].get("/ColorSpace")
        cat, detail = _resolve_classify(cs, resources) if cs is not None else ("unknown", "")
    except Exception:
        return
    if flagged_kind(cat):
        # Shadings fill the current clip; we don't track clip geometry, so the
        # finding is page-level (bbox=None -> report marks the whole page).
        _maybe_record(findings, page_no, "shading", cat, "shading " + detail, None)


# --------------------------------------------------------------------------- #
# Small helpers
# --------------------------------------------------------------------------- #
def _maybe_record(findings, page_no, element, category, detail, bbox):
    kind = flagged_kind(category)
    if kind:
        findings.append(Finding(page=page_no, kind=kind, element=element,
                                category=category, detail=detail or "", bbox=bbox))


def _maybe_white_overprint(findings, page_no, element, category, val, overprint,
                           bbox):
    """Record a finding when a white object is set to overprint.

    Overprinting white is almost always a defect: the white object knocks
    nothing out, so on press it disappears and the background shows through.
    """
    if overprint and is_white(category, val):
        findings.append(Finding(
            page=page_no, kind="white_overprint", element=element,
            category=category,
            detail=f"white {category} set to overprint", bbox=bbox))


def is_white(category, val):
    """True if the color components represent white (no ink / paper)."""
    if not val:
        return False
    try:
        if category == "gray":
            return val[0] >= 0.999
        if category in ("rgb", "lab"):
            return len(val) >= 3 and all(c >= 0.999 for c in val[:3])
        if category == "cmyk":
            return len(val) >= 4 and all(c <= 0.001 for c in val[:4])
        if category == "spot":
            # Separation/DeviceN with a zero tint lays down no ink.
            return all(c <= 0.001 for c in val)
    except Exception:
        return False
    return False


def _numeric_operands(ops):
    vals = []
    for o in ops:
        if is_name(o):
            continue  # e.g. trailing pattern name in scn
        try:
            vals.append(float(o))
        except Exception:
            pass
    return tuple(vals) if vals else None


def _apply_extgstate(name_obj, resources, gs):
    """Apply an ExtGState's overprint settings (/OP stroke, /op fill)."""
    if resources is None:
        return
    try:
        egs = resources.get("/ExtGState")
        if egs is None:
            return
        name = str(name_obj)
        if name not in egs:
            return
        d = egs[name]
        has_op = "/OP" in d
        has_op_lower = "/op" in d
        if has_op:
            gs.stroke_op = bool(d.get("/OP"))
        if has_op_lower:
            gs.fill_op = bool(d.get("/op"))
        elif has_op:
            # Per spec, fill overprint defaults to the /OP value when /op absent.
            gs.fill_op = bool(d.get("/OP"))
    except Exception:
        return


def _unit_square_bbox(ctm):
    xs = []
    ys = []
    for cx, cy in ((0, 0), (1, 0), (1, 1), (0, 1)):
        px, py = apply_pt(ctm, cx, cy)
        xs.append(px); ys.append(py)
    return (min(xs), min(ys), max(xs), max(ys))


def _f(o):
    try:
        return float(o)
    except Exception:
        return 0.0


def _char_count(s):
    if s is None:
        return 0
    try:
        return len(bytes(s))
    except Exception:
        return len(str(s))


def _tj_count(arr):
    n = 0
    try:
        for el in arr:
            if is_name(el):
                continue
            try:
                n += len(bytes(el))
            except Exception:
                pass
    except Exception:
        pass
    return n
