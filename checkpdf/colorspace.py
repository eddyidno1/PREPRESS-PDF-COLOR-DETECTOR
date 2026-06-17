"""Resolve a PDF colorspace object into a simple color category.

Categories returned by :func:`classify`:
    'rgb'   — DeviceRGB, CalRGB, RGB ICC profile, or Indexed on an RGB base
    'lab'   — Lab colorspace (treated as RGB-class / non-CMYK)
    'cmyk'  — DeviceCMYK or CMYK ICC profile
    'gray'  — DeviceGray, CalGray, or Gray ICC profile
    'spot'  — Separation or DeviceN (named spot colors, e.g. Pantone)
    'pattern' / 'unknown' — anything we cannot map to the above

Only 'rgb', 'lab' and 'spot' are flagged as print problems (see FLAGGED).
"""

from pikepdf import ObjectType

# Categories that fail a print-safe check, mapped to the report's "kind".
FLAGGED = {"rgb": "rgb", "lab": "rgb", "spot": "spot"}

_DEVICE = {"/DeviceGray": "gray", "/DeviceRGB": "rgb", "/DeviceCMYK": "cmyk"}
# Abbreviated names used inside inline images (BI ... ID ... EI).
_ABBREV = {"/G": "gray", "/RGB": "rgb", "/CMYK": "cmyk"}
_ICC_N = {1: "gray", 3: "rgb", 4: "cmyk"}


def _is(obj, code):
    return getattr(obj, "_type_code", None) == code


def is_name(obj):
    return _is(obj, ObjectType.name_)


def is_array(obj):
    return _is(obj, ObjectType.array)


def is_stream(obj):
    return _is(obj, ObjectType.stream)


def flagged_kind(category):
    """Return 'rgb' or 'spot' if the category is a print problem, else None."""
    return FLAGGED.get(category)


def classify(cs, _depth=0):
    """Return ``(category, detail)`` for a pikepdf colorspace object.

    ``detail`` is a human-readable note (e.g. a spot colorant name) and may be
    an empty string.
    """
    if cs is None or _depth > 12:
        return ("unknown", "")

    if is_name(cs):
        s = str(cs)
        if s in _DEVICE:
            return (_DEVICE[s], "")
        if s in _ABBREV:
            return (_ABBREV[s], "")
        if s == "/Pattern":
            return ("pattern", "")
        return ("unknown", s.lstrip("/"))

    if is_array(cs) and len(cs) > 0:
        family = str(cs[0])

        if family == "/ICCBased":
            return _classify_icc(cs)
        if family in ("/Indexed", "/I"):
            base = cs[1] if len(cs) > 1 else None
            cat, det = classify(base, _depth + 1)
            return (cat, ("indexed " + det).strip())
        if family == "/Separation":
            name = str(cs[1]).lstrip("/") if len(cs) > 1 else "?"
            return ("spot", name)
        if family == "/DeviceN":
            names = []
            if len(cs) > 1 and is_array(cs[1]):
                names = [str(n).lstrip("/") for n in cs[1]]
            return ("spot", "+".join(names) if names else "DeviceN")
        if family == "/CalRGB":
            return ("rgb", "CalRGB")
        if family == "/CalGray":
            return ("gray", "CalGray")
        if family == "/Lab":
            return ("lab", "Lab")
        if family == "/Pattern":
            # Uncolored pattern carries an underlying colorspace as cs[1].
            if len(cs) > 1:
                return classify(cs[1], _depth + 1)
            return ("pattern", "")
        if family in _DEVICE:
            return (_DEVICE[family], "")

    if is_stream(cs):
        return _classify_icc_stream(cs)

    return ("unknown", "")


def _classify_icc(cs):
    stream = cs[1] if len(cs) > 1 else None
    if stream is None:
        return ("unknown", "ICC")
    return _classify_icc_stream(stream)


def _classify_icc_stream(stream):
    n = None
    try:
        if "/N" in stream:
            n = int(stream.get("/N"))
    except Exception:
        n = None
    if n in _ICC_N:
        return (_ICC_N[n], "ICC%d" % n)
    # Fall back to the /Alternate colorspace if /N is missing/odd.
    try:
        alt = stream.get("/Alternate") if "/Alternate" in stream else None
    except Exception:
        alt = None
    if alt is not None:
        return classify(alt)
    return ("unknown", "ICC")
