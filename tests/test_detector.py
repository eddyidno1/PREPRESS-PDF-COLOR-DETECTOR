import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from checkpdf.detector import analyze       # noqa: E402
from checkpdf.report import build_report     # noqa: E402
from tests.make_fixtures import build_all     # noqa: E402


@pytest.fixture(scope="module")
def fixtures(tmp_path_factory):
    outdir = tmp_path_factory.mktemp("fixtures")
    return build_all(str(outdir))


def test_cmyk_only_passes(fixtures):
    rep = analyze(fixtures["cmyk_only"])
    assert rep.passed
    assert rep.findings == []
    assert rep.white_overprint_count == 0
    assert rep.page_count == 1


def test_white_overprint_detected(fixtures):
    rep = analyze(fixtures["white_overprint"])
    assert not rep.passed
    # Exactly one of the two white rectangles overprints.
    assert rep.white_overprint_count == 1
    assert rep.rgb_count == 0 and rep.spot_count == 0
    wf = [f for f in rep.findings if f.kind == "white_overprint"][0]
    assert wf.page == 1
    assert "overprint" in wf.detail


def test_has_rgb_fails(fixtures):
    rep = analyze(fixtures["has_rgb"])
    assert not rep.passed
    assert rep.pages_with_findings == [2]          # only page 2
    assert rep.rgb_count >= 2                       # rect + image
    kinds = {f.element for f in rep.findings}
    assert "vector" in kinds and "image" in kinds
    assert all(f.kind == "rgb" for f in rep.findings)


def test_has_spot_fails(fixtures):
    rep = analyze(fixtures["has_spot"])
    assert not rep.passed
    assert rep.spot_count >= 1
    assert any("PANTONE" in f.detail for f in rep.findings)


def test_report_is_generated(fixtures, tmp_path):
    rep = analyze(fixtures["has_rgb"])
    out = build_report(rep, fixtures["has_rgb"], str(tmp_path / "report.pdf"))
    assert os.path.exists(out)
    assert os.path.getsize(out) > 0


def test_bbox_location_is_reasonable(fixtures):
    """The RGB rectangle was drawn at 50,250 size 200x100 on a 400pt page."""
    rep = analyze(fixtures["has_rgb"])
    rects = [f for f in rep.findings if f.element == "vector"]
    assert rects
    x0, y0, x1, y1 = rects[0].bbox
    assert abs(x0 - 50) < 2 and abs(x1 - 250) < 2
    assert abs(y0 - 250) < 2 and abs(y1 - 350) < 2
