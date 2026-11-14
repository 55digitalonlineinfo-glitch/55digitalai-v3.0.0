#!/usr/bin/env python3
"""
55DigitalAI — Generic Text Report -> PDF
=============================================================
Purpose  : Turn the plain-text stdout of any read-only report script
           (daily_check.py, campaign_analyst.py, merchant_review.py,
           seasonality.py, ga4_reports.py) into a branded, client-ready PDF
           — without needing a bespoke JSON schema per report type the way
           generate_audit_pdf.py does for the full account audit.

           Recognizes a few conventions already used by these scripts'
           printed output: lines starting with "##" become section headings,
           "===" separator lines are dropped, and "[FLAG]"/"[OK]" markers
           get colored inline so problems still stand out on paper.

Usage    : from text_report_pdf import render_text_report
           render_text_report(client_meta, "Daily Pulse-Check", captured_text, output_path)
"""

import io
import re
import sys
import html
import contextlib
from datetime import datetime
from pathlib import Path

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pdf_common import COLORS, LOGO_PATH, AGENCY_NAME, FONTS, hexc  # noqa: E402

PAGE_W, PAGE_H = A4
MARGIN = 20 * mm

_MARKER_COLOR = {"[FLAG]": "fail", "[OK]": "pass", "[NEGATE]": "fail", "[KEEP]": "pass",
                 "[WARN]": "warn", "[DRY RUN]": "warn"}
_SEPARATOR_RE = re.compile(r"^[=\-─━]{4,}$")


def _styles():
    return {
        "title": ParagraphStyle("title", fontName=FONTS["bold"], fontSize=20, leading=25,
                                 textColor=hexc("primary"), spaceAfter=2),
        "meta": ParagraphStyle("meta", fontName=FONTS["regular"], fontSize=10, leading=14,
                                textColor=hexc("text"), spaceAfter=10),
        "h2": ParagraphStyle("h2", fontName=FONTS["bold"], fontSize=12.5, leading=16,
                              textColor=hexc("primary"), spaceBefore=10, spaceAfter=4),
        "body": ParagraphStyle("body", fontName="Courier", fontSize=8.5, leading=12,
                                textColor=hexc("secondary"), spaceAfter=1),
        "footer": ParagraphStyle("footer", fontName=FONTS["regular"], fontSize=7.5, leading=9,
                                  textColor=hexc("text")),
    }


def _colorize_line(line: str) -> str:
    """Wrap known [MARKER] prefixes in a color span; escape everything else for Paragraph markup."""
    escaped = html.escape(line)
    for marker, color_key in _MARKER_COLOR.items():
        esc_marker = html.escape(marker)
        if escaped.lstrip().startswith(esc_marker):
            return escaped.replace(esc_marker, f'<font color="{COLORS[color_key]}"><b>{esc_marker}</b></font>', 1)
    return escaped


def _draw_footer(canvas, doc, title, client_name):
    canvas.saveState()
    canvas.setFont(FONTS["regular"], 7.5)
    canvas.setFillColor(hexc("text"))
    canvas.drawString(MARGIN, 12 * mm, f"{title} — {client_name}")
    canvas.drawRightString(PAGE_W - MARGIN, 12 * mm, f"Page {doc.page}")
    canvas.setStrokeColor(hexc("na"))
    canvas.line(MARGIN, 16 * mm, PAGE_W - MARGIN, 16 * mm)
    canvas.restoreState()


class _Tee:
    """Writes to real stdout AND a buffer — for scripts that print() directly
    instead of building a string first, so wiring in --pdf doesn't need
    restructuring their internals."""
    def __init__(self, *streams):
        self.streams = streams

    def write(self, data):
        for s in self.streams:
            s.write(data)

    def flush(self):
        for s in self.streams:
            s.flush()


def capture_stdout(func, *args, **kwargs) -> str:
    """Calls func(*args, **kwargs), printing normally to the terminal exactly as
    before, while also capturing everything printed. Returns the captured text."""
    buf = io.StringIO()
    tee = _Tee(sys.stdout, buf)
    with contextlib.redirect_stdout(tee):
        func(*args, **kwargs)
    return buf.getvalue()


def render_text_report(client_meta: dict, title: str, text: str, output_path) -> Path:
    """client_meta: dict with at least 'name' (and optionally 'domain'). text: the
    captured stdout of a report script. output_path: where to write the PDF."""
    styles = _styles()
    doc = SimpleDocTemplate(
        str(output_path), pagesize=A4,
        leftMargin=MARGIN, rightMargin=MARGIN, topMargin=MARGIN, bottomMargin=MARGIN,
    )
    story = []

    if LOGO_PATH.exists():
        from reportlab.platypus import Image
        story.append(Image(str(LOGO_PATH), width=30 * mm, height=30 * mm, kind="proportional"))
        story.append(Spacer(1, 4 * mm))

    story.append(Paragraph(html.escape(title), styles["title"]))
    meta_bits = [client_meta.get("name", "")]
    if client_meta.get("domain"):
        meta_bits.append(client_meta["domain"])
    meta_bits.append(datetime.now().strftime("%Y-%m-%d %H:%M"))
    story.append(Paragraph(html.escape("  ·  ".join(b for b in meta_bits if b)), styles["meta"]))
    story.append(Paragraph(html.escape(f"Prepared by {AGENCY_NAME}"), styles["footer"]))
    story.append(Spacer(1, 6 * mm))

    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        if _SEPARATOR_RE.match(line.strip()):
            continue
        if not line.strip():
            story.append(Spacer(1, 2))
            continue
        if line.lstrip().startswith("##"):
            story.append(Paragraph(html.escape(line.lstrip("#").strip()), styles["h2"]))
            continue
        story.append(Paragraph(_colorize_line(line), styles["body"]))

    def on_page(canvas, doc_):
        _draw_footer(canvas, doc_, title, client_meta.get("name", ""))

    doc.build(story, onFirstPage=on_page, onLaterPages=on_page)
    return Path(output_path)
