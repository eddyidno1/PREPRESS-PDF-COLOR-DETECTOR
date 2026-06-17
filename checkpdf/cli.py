"""Command-line entry point: ``python -m checkpdf file.pdf [more.pdf ...]``."""

import sys

from .detector import analyze
from .report import build_report


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv:
        print("Usage: python -m checkpdf <file.pdf> [file2.pdf ...]")
        return 2

    exit_code = 0
    for path in argv:
        report = analyze(path)
        out = build_report(report, path)
        status = "PASS" if report.passed else (
            "ENCRYPTED" if report.encrypted else "FAIL")
        print(f"{status:9}  {path}")
        if not report.passed and not report.encrypted:
            print(f"           RGB: {report.rgb_count}  Spot: {report.spot_count}  "
                  f"White-overprint: {report.white_overprint_count}  "
                  f"Pages: {report.pages_with_findings}")
            exit_code = 1
        for err in report.errors:
            print(f"           ! {err}")
        print(f"           report -> {out}")
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
