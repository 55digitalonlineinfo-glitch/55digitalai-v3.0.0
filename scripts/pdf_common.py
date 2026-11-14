#!/usr/bin/env python3
"""
55DigitalAI — Shared PDF Setup (fonts + colors)
=============================================================
Purpose  : Font registration + brand color helpers shared by every PDF
           renderer (generate_audit_pdf.py, text_report_pdf.py) so the
           cross-platform font fallback logic and brand loading only
           exist in one place.

Usage    : from pdf_common import COLORS, hexc, FONTS, AGENCY_NAME, LOGO_PATH
"""

from pathlib import Path

from reportlab.lib import colors
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
from brand import COLORS, LOGO_PATH, AGENCY_NAME  # noqa: E402

# reportlab's built-in Helvetica only supports WinAnsi encoding, which drops
# Polish characters like Ł/ł — register a real Unicode TTF (also covers
# Cyrillic-script client names) so every client's text renders
# correctly. Falls back to built-in Helvetica (ASCII-only, never crashes) if
# none of these common font locations exist.
_FONT_CANDIDATES = [
    (Path("/System/Library/Fonts/Supplemental"), "Arial.ttf", "Arial Bold.ttf", "Arial Italic.ttf", "Arial Bold Italic.ttf"),  # macOS
    (Path("C:/Windows/Fonts"), "arial.ttf", "arialbd.ttf", "ariali.ttf", "arialbi.ttf"),  # Windows
    (Path("/usr/share/fonts/truetype/liberation"), "LiberationSans-Regular.ttf", "LiberationSans-Bold.ttf",
     "LiberationSans-Italic.ttf", "LiberationSans-BoldItalic.ttf"),  # common Linux distros
]
_FONT_NAME = "Helvetica"
for _dir, _reg, _bold, _italic, _bolditalic in _FONT_CANDIDATES:
    if (_dir / _reg).exists():
        try:
            pdfmetrics.registerFont(TTFont("Arial", str(_dir / _reg)))
            pdfmetrics.registerFont(TTFont("Arial-Bold", str(_dir / _bold)))
            pdfmetrics.registerFont(TTFont("Arial-Italic", str(_dir / _italic)))
            pdfmetrics.registerFont(TTFont("Arial-BoldItalic", str(_dir / _bolditalic)))
            pdfmetrics.registerFontFamily("Arial", normal="Arial", bold="Arial-Bold",
                                           italic="Arial-Italic", boldItalic="Arial-BoldItalic")
            _FONT_NAME = "Arial"
            break
        except Exception:
            continue

FONTS = {"regular": "Arial", "bold": "Arial-Bold", "italic": "Arial-Italic", "bolditalic": "Arial-BoldItalic"} \
    if _FONT_NAME == "Arial" else \
    {"regular": "Helvetica", "bold": "Helvetica-Bold", "italic": "Helvetica-Oblique", "bolditalic": "Helvetica-BoldOblique"}


def hexc(key):
    return colors.HexColor(COLORS[key])
