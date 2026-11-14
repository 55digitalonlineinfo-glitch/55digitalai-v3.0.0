#!/usr/bin/env python3
"""
55DigitalAI — Full Account Audit PDF Generator
=============================================================
Purpose  : Turn a structured full-account-audit JSON (see
           clients/<slug>/reports/full_account_audit_YYYY-MM-DD.json for
           the schema) into a branded, client-ready PDF — a dashboard-style
           opening page (stat cards, prioritized-action preview, findings
           donut, sample findings rows), then the complete report: executive
           summary, full prioritized action plan, section-by-section
           findings tables (every row, every section), What's Working Well,
           Gaps, and a complete All Failed Items list.

           Branding (agency name/colors/logo) pulled from brand_config.json
           via scripts/brand.py — edit that file, not this one, to rebrand.

           This does not run the audit itself — it renders whatever
           findings were already gathered (via the Ads/GA4/Search Console
           APIs and the system-prompts/agents/ppc-audit-agent.md
           checklist) into the PDF. Logs the run to
           clients/<slug>/reports/pdf_generation_log.log.

Usage    : python3 scripts/generate_audit_pdf.py <client_slug> <audit_json_path>
Changelog: 2026-07-23  Initial version
           2026-08-21  Dashboard-style front page (stat cards, action-plan
                       preview, findings-coverage donut, pill status badges)
                       layered on top of the existing full report.
"""

import json
import sys
from datetime import datetime
from pathlib import Path

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    PageBreak, Image, KeepTogether, HRFlowable, Flowable,
)

sys.path.insert(0, str(Path(__file__).resolve().parent))
from client_registry import resolve  # noqa: E402
from pdf_common import COLORS, LOGO_PATH, AGENCY_NAME, FONTS as _FONTS, hexc  # noqa: E402

PAGE_W, PAGE_H = A4
MARGIN = 20 * mm
CONTENT_W = PAGE_W - 2 * MARGIN


# ─── status → color / bucket helpers ───────────────────────────────────────

def status_colors(status):
    """Returns (fg_hex_string, bg_Color) for a status label."""
    s = status.lower()
    if s.startswith("pass") or s.startswith("resolved"):
        return COLORS["pass"], hexc("pass_bg")
    if s.startswith("fail"):
        return COLORS["fail"], hexc("fail_bg")
    if s.startswith("n/a"):
        return COLORS["na"], hexc("na_bg")
    return COLORS["warn"], hexc("warn_bg")  # Manual, Partial, Mixed, Calculated, etc.


def status_bucket(status):
    s = status.lower()
    if s.startswith("pass") or s.startswith("resolved"):
        return "pass"
    if s.startswith("fail"):
        return "fail"
    if s.startswith("n/a"):
        return "na"
    return "manual"  # Manual, Partial, Mixed, Calculated-benchmark-only, etc.


_STATUS_LABEL_PREFIXES = [
    ("pass", "PASS"), ("resolved", "PASS"),
    ("fail", "FAIL"),
    ("n/a", "N/A"),
    ("partial", "PARTIAL"),
    ("manual", "MANUAL"),
    ("calculated", "CALC."),
    ("needs", "REVIEW"),
]


def short_status_label(status):
    """Collapse a verbose status ('Needs a closer look', 'Fail — precise,
    content-verified') to a short, fixed-vocabulary pill label. Falls back to
    the first word (never a mid-word slice) for anything unmatched."""
    s = status.strip().lower()
    for prefix, label in _STATUS_LABEL_PREFIXES:
        if s.startswith(prefix):
            return label
    first_word = status.split()[0].rstrip(",;:—-") if status.split() else status
    return first_word[:8].upper()


# ─── custom drawn flowables (rounded cards, donut, pill badges) ───────────

class RoundedCardBG(Flowable):
    """A rounded-rect background card. Draw first, then overlay content via
    a following flowable positioned by the caller — used as a simple filled
    card when no dynamic content needs to sit inside it."""

    def __init__(self, width, height, bg=None, border=None, radius=7):
        Flowable.__init__(self)
        self.width = width
        self.height = height
        self.bg = bg or hexc("white")
        self.border = border
        self.radius = radius

    def wrap(self, avail_w, avail_h):
        return self.width, self.height

    def draw(self):
        c = self.canv
        c.saveState()
        c.setFillColor(self.bg)
        if self.border:
            c.setStrokeColor(self.border)
            c.roundRect(0, 0, self.width, self.height, self.radius, stroke=1, fill=1)
        else:
            c.roundRect(0, 0, self.width, self.height, self.radius, stroke=0, fill=1)
        c.restoreState()


class StatCard(Flowable):
    """One dashboard stat card: label, big value, small sublabel."""

    def __init__(self, width, height, label, value, sublabel):
        Flowable.__init__(self)
        self.width = width
        self.height = height
        self.label = label
        self.value = value
        self.sublabel = sublabel

    def wrap(self, avail_w, avail_h):
        return self.width, self.height

    def draw(self):
        from reportlab.pdfbase.pdfmetrics import stringWidth

        c = self.canv
        c.saveState()
        c.setFillColor(hexc("white"))
        c.setStrokeColor(hexc("na_bg"))
        c.roundRect(0, 0, self.width, self.height, 6, stroke=1, fill=1)

        pad = 9
        avail_w = self.width - 2 * pad

        def fit(text, font, size):
            """Shrink text with an ellipsis until it fits avail_w at this font/size."""
            if stringWidth(text, font, size) <= avail_w:
                return text
            while text and stringWidth(text + "…", font, size) > avail_w:
                text = text[:-1]
            return f"{text.rstrip()}…" if text else text

        c.setFillColor(hexc("text"))
        c.setFont(_FONTS["regular"], 8)
        c.drawString(pad, self.height - 16, fit(self.label, _FONTS["regular"], 8))

        c.setFillColor(hexc("primary"))
        c.setFont(_FONTS["bold"], 17)
        c.drawString(pad, self.height - 36, fit(self.value, _FONTS["bold"], 17))

        # Sublabel: wrap across up to 2 lines (word-wrapped), each fit to width.
        c.setFillColor(hexc("text"))
        sub_font, sub_size = _FONTS["regular"], 6.8
        words = self.sublabel.split(" ")
        lines, cur = [], ""
        for w in words:
            trial = f"{cur} {w}".strip()
            if stringWidth(trial, sub_font, sub_size) <= avail_w:
                cur = trial
            else:
                if cur:
                    lines.append(cur)
                cur = w
            if len(lines) == 2:
                break
        if cur and len(lines) < 2:
            lines.append(cur)
        lines = lines[:2]
        if lines:
            lines[-1] = fit(lines[-1], sub_font, sub_size)
        c.setFont(sub_font, sub_size)
        y = 9 if len(lines) == 1 else 16
        for line in lines:
            c.drawString(pad, y, line)
            y -= 8
        c.restoreState()


class Donut(Flowable):
    """Simple donut chart: segments = [(value, color_hex), ...]."""

    def __init__(self, size, segments, center_value, center_label):
        Flowable.__init__(self)
        self.size = size
        self.segments = segments
        self.center_value = center_value
        self.center_label = center_label

    def wrap(self, avail_w, avail_h):
        return self.size, self.size

    def draw(self):
        c = self.canv
        c.saveState()
        total = sum(v for v, _ in self.segments) or 1
        cx = cy = self.size / 2
        r_out = self.size / 2 - 3
        r_in = r_out * 0.58
        start = 90.0
        for v, color in self.segments:
            extent = -360.0 * (v / total)
            if v > 0:
                c.setFillColor(color)
                c.wedge(cx - r_out, cy - r_out, cx + r_out, cy + r_out, start, extent, stroke=0, fill=1)
            start += extent
        c.setFillColor(hexc("white"))
        c.circle(cx, cy, r_in, stroke=0, fill=1)
        c.setFillColor(hexc("primary"))
        c.setFont(_FONTS["bold"], 18)
        c.drawCentredString(cx, cy - 3, self.center_value)
        c.setFillColor(hexc("text"))
        c.setFont(_FONTS["regular"], 6.5)
        c.drawCentredString(cx, cy - 15, self.center_label)
        c.restoreState()


class StatusPill(Flowable):
    """Small rounded status badge used inside findings-table cells."""

    def __init__(self, text, fg_hex, bg_color, width=50, height=12.5):
        Flowable.__init__(self)
        self.text = text
        self.fg_hex = fg_hex
        self.bg_color = bg_color
        self.width = width
        self.height = height

    def wrap(self, avail_w, avail_h):
        return self.width, self.height

    def draw(self):
        c = self.canv
        c.saveState()
        from reportlab.lib import colors as _colors
        c.setFillColor(self.bg_color)
        c.roundRect(0, 0, self.width, self.height, self.height / 2, stroke=0, fill=1)
        c.setFillColor(_colors.HexColor(self.fg_hex))
        c.setFont(_FONTS["bold"], 6.6)
        c.drawCentredString(self.width / 2, self.height / 2 - 2.3, self.text)
        c.restoreState()


class Pill(Flowable):
    """Small rounded label chip (e.g. the '55DIGITALAI' badge, tier tags)."""

    def __init__(self, text, fg_color, bg_color, font_size=8, pad_x=8, height=15):
        Flowable.__init__(self)
        self.text = text
        self.fg_color = fg_color
        self.bg_color = bg_color
        self.font_size = font_size
        self.pad_x = pad_x
        self.height = height
        from reportlab.pdfbase.pdfmetrics import stringWidth
        self.width = stringWidth(text, _FONTS["bold"], font_size) + 2 * pad_x

    def wrap(self, avail_w, avail_h):
        return self.width, self.height

    def draw(self):
        c = self.canv
        c.saveState()
        c.setFillColor(self.bg_color)
        c.roundRect(0, 0, self.width, self.height, self.height / 2, stroke=0, fill=1)
        c.setFillColor(self.fg_color)
        c.setFont(_FONTS["bold"], self.font_size)
        c.drawCentredString(self.width / 2, self.height / 2 - self.font_size * 0.34, self.text)
        c.restoreState()


# ─── styles ─────────────────────────────────────────────────────────────

def build_styles():
    return {
        "dash_badge": ParagraphStyle("dash_badge", fontName=_FONTS["bold"], fontSize=8,
                                      textColor=hexc("accent")),
        "dash_title": ParagraphStyle("dash_title", fontName=_FONTS["bold"], fontSize=25,
                                      textColor=hexc("primary"), leading=29, spaceBefore=4),
        "dash_sub": ParagraphStyle("dash_sub", fontName=_FONTS["regular"], fontSize=10.5,
                                    textColor=hexc("text"), leading=14),
        "dash_card_h": ParagraphStyle("dash_card_h", fontName=_FONTS["bold"], fontSize=12,
                                       textColor=hexc("primary"), leading=15, spaceAfter=4),
        "cover_title": ParagraphStyle("cover_title", fontName=_FONTS["bold"], fontSize=28,
                                       textColor=hexc("white"), leading=34, spaceBefore=0),
        "cover_sub": ParagraphStyle("cover_sub", fontName=_FONTS["regular"], fontSize=13,
                                     textColor=hexc("bg_light"), leading=18),
        "cover_meta": ParagraphStyle("cover_meta", fontName=_FONTS["regular"], fontSize=10,
                                      textColor=hexc("bg_light"), leading=14),
        "h1": ParagraphStyle("h1", fontName=_FONTS["bold"], fontSize=18, leading=22,
                              textColor=hexc("primary"), spaceBefore=0, spaceAfter=8),
        "h2": ParagraphStyle("h2", fontName=_FONTS["bold"], fontSize=13, leading=16,
                              textColor=hexc("primary"), spaceBefore=14, spaceAfter=6),
        "section_note": ParagraphStyle("section_note", fontName=_FONTS["italic"], fontSize=8.5, leading=11,
                                        textColor=hexc("text"), spaceAfter=6),
        "score_label": ParagraphStyle("score_label", fontName=_FONTS["bold"], fontSize=12, leading=15,
                                       textColor=hexc("bg_light"), spaceAfter=2),
        "score_number": ParagraphStyle("score_number", fontName=_FONTS["bold"], fontSize=40, leading=46,
                                        textColor=hexc("accent")),
        "body": ParagraphStyle("body", fontName=_FONTS["regular"], fontSize=10,
                                textColor=hexc("secondary"), leading=14),
        "cell": ParagraphStyle("cell", fontName=_FONTS["regular"], fontSize=8.5,
                                textColor=hexc("secondary"), leading=11),
        "cell_bold": ParagraphStyle("cell_bold", fontName=_FONTS["bold"], fontSize=8.5,
                                     textColor=hexc("primary"), leading=11),
        "cell_header": ParagraphStyle("cell_header", fontName=_FONTS["bold"], fontSize=8.5,
                                       textColor=hexc("white"), leading=11),
        "list_item": ParagraphStyle("list_item", fontName=_FONTS["regular"], fontSize=9.5,
                                     textColor=hexc("secondary"), leading=13.5, spaceAfter=6,
                                     leftIndent=4),
        "action_title": ParagraphStyle("action_title", fontName=_FONTS["bold"], fontSize=9.5,
                                        textColor=hexc("primary"), leading=12),
        "action_body": ParagraphStyle("action_body", fontName=_FONTS["regular"], fontSize=8.5,
                                       textColor=hexc("text"), leading=11.5),
        "failed_item": ParagraphStyle("failed_item", fontName=_FONTS["regular"], fontSize=8.5,
                                       textColor=hexc("secondary"), leading=12, spaceAfter=3),
        "footer": ParagraphStyle("footer", fontName=_FONTS["regular"], fontSize=7.5, leading=9,
                                  textColor=hexc("text")),
    }


TIER_COLOR = {"critical": "fail", "high": "warn", "medium": "accent"}
TIER_LABEL = {"critical": "CRITICAL", "high": "HIGH", "medium": "MEDIUM"}


def draw_header_footer(canvas, doc, client_name, brand_pdf_title):
    canvas.saveState()
    canvas.setFont(_FONTS["regular"], 7.5)
    canvas.setFillColor(hexc("text"))
    canvas.drawString(MARGIN, 12 * mm, f"{AGENCY_NAME} — {brand_pdf_title} — {client_name}")
    canvas.drawRightString(PAGE_W - MARGIN, 12 * mm, f"Page {doc.page}")
    canvas.setStrokeColor(hexc("na"))
    canvas.line(MARGIN, 16 * mm, PAGE_W - MARGIN, 16 * mm)
    canvas.restoreState()


def dashboard_page_background(canvas, doc):
    canvas.saveState()
    canvas.setFillColor(hexc("bg_light"))
    canvas.rect(0, 0, PAGE_W, PAGE_H, stroke=0, fill=1)
    canvas.restoreState()


def _split_action(text):
    """First sentence -> title, rest -> body (for the compact action-plan preview)."""
    if ". " in text:
        head, rest = text.split(". ", 1)
        return head.strip(), rest.strip()
    return text.strip(), ""


def dashboard_page(story, styles, data, findings_summary):
    story.append(Spacer(1, 4 * mm))

    badge = Pill("55DIGITALAI", hexc("white"), hexc("accent"), font_size=8, height=15)
    hs = data.get("health_score", "—")
    try:
        hs_num = float(hs.split("/")[0])
    except Exception:
        hs_num = None
    if hs_num is not None and hs_num >= 7:
        hs_fg, hs_bg = COLORS["pass"], hexc("pass_bg")
    elif hs_num is not None and hs_num >= 4:
        hs_fg, hs_bg = COLORS["warn"], hexc("warn_bg")
    else:
        hs_fg, hs_bg = COLORS["fail"], hexc("fail_bg")
    from reportlab.lib import colors as _colors
    score_pill = Pill(f"Health Score {hs}", _colors.HexColor(hs_fg), hs_bg, font_size=9, height=17)

    top_row = Table([[badge, "", score_pill]], colWidths=[CONTENT_W * 0.3, CONTENT_W * 0.4, CONTENT_W * 0.3])
    top_row.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN", (2, 0), (2, 0), "RIGHT"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
    ]))
    story.append(top_row)
    story.append(Spacer(1, 4 * mm))
    story.append(Paragraph("Full Account Audit", styles["dash_title"]))
    lookback = data.get("lookback", "90-day lookback")
    story.append(Paragraph(
        f"{data['client_name']} · {data.get('domain', '—')} · {data['date']} · {lookback}",
        styles["dash_sub"]))
    story.append(Spacer(1, 6 * mm))

    # stat cards row
    stats = data.get("stats") or []
    if stats:
        card_w = (CONTENT_W - 3 * 4) / 4
        cards = [StatCard(card_w, 30 * mm, s["label"], s["value"], s.get("sublabel", "")) for s in stats[:4]]
        row = [cards]
        tbl = Table(row, colWidths=[card_w] * len(cards))
        tbl.setStyle(TableStyle([
            ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 4),
            ("TOPPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
        ]))
        story.append(tbl)
        story.append(Spacer(1, 5 * mm))

    # two-column: action plan preview | findings coverage donut
    action_items = []
    for tier in ("critical", "high"):
        for txt in data.get(tier, []):
            action_items.append((tier, txt))
    action_items = action_items[:3]

    action_cell = [Paragraph("Prioritized Action Plan", styles["dash_card_h"]),
                   HRFlowable(width="100%", thickness=0.75, color=hexc("na_bg"), spaceAfter=6)]
    for tier, txt in action_items:
        title, body = _split_action(txt)
        fg, bg = status_colors("Fail" if tier == "critical" else "Manual")
        pill = Pill(TIER_LABEL[tier], _colors.HexColor(fg), bg, font_size=6.5, height=11, pad_x=6)
        row = Table([[pill, Paragraph(f"<b>{title}</b><br/>{body}", styles["action_body"])]],
                    colWidths=[16 * mm, None])
        row.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 4),
            ("TOPPADDING", (0, 0), (-1, -1), 2), ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ]))
        action_cell.append(row)

    pass_n, fail_n, manual_n, na_n = (findings_summary["pass"], findings_summary["fail"],
                                       findings_summary["manual"], findings_summary["na"])
    scoreable = pass_n + fail_n
    pass_rate = round(100 * pass_n / scoreable) if scoreable else 0
    donut = Donut(34 * mm, [
        (pass_n, hexc("pass")), (fail_n, hexc("fail")),
        (manual_n, hexc("na")), (na_n, hexc("na_bg")),
    ], f"{pass_rate}%", "Pass rate*")
    # Legend swatches: the dot's *fill* is what's visible (text is empty), so
    # the solid color must be passed as bg_color, not the pale "_bg" tint.
    legend_rows = [
        [Pill("", hexc("white"), hexc("pass"), font_size=1, height=6, pad_x=3),
         Paragraph(f"Pass ({pass_n})", styles["action_body"])],
        [Pill("", hexc("white"), hexc("fail"), font_size=1, height=6, pad_x=3),
         Paragraph(f"Fail ({fail_n})", styles["action_body"])],
        [Pill("", hexc("white"), hexc("na"), font_size=1, height=6, pad_x=3),
         Paragraph(f"Manual ({manual_n})", styles["action_body"])],
    ]
    legend_tbl = Table(legend_rows, colWidths=[8 * mm, None])
    legend_tbl.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0), ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
    ]))
    donut_cell = [Paragraph("Findings Coverage", styles["dash_card_h"]),
                  HRFlowable(width="100%", thickness=0.75, color=hexc("na_bg"), spaceAfter=6),
                  Spacer(1, 2 * mm), donut, Spacer(1, 3 * mm), legend_tbl,
                  Spacer(1, 2 * mm),
                  Paragraph(f"*of {scoreable} scoreable items ({na_n} N/A excluded)", styles["section_note"])]

    two_col = Table([[action_cell, donut_cell]], colWidths=[CONTENT_W * 0.62, CONTENT_W * 0.34])
    two_col.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("BACKGROUND", (0, 0), (-1, -1), hexc("white")),
        ("BOX", (0, 0), (0, 0), 0.75, hexc("na_bg")),
        ("BOX", (1, 0), (1, 0), 0.75, hexc("na_bg")),
        ("LEFTPADDING", (0, 0), (0, 0), 10), ("RIGHTPADDING", (0, 0), (0, 0), 10),
        ("LEFTPADDING", (1, 0), (1, 0), 10), ("RIGHTPADDING", (1, 0), (1, 0), 10),
        ("TOPPADDING", (0, 0), (-1, -1), 10), ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
    ]))
    two_col._colWidths = [CONTENT_W * 0.62 - 4, CONTENT_W * 0.34 - 4]
    story.append(two_col)
    story.append(Spacer(1, 5 * mm))

    # sample findings rows
    sample = findings_summary["sample_rows"][:3]
    header_row = [Paragraph("Category", styles["cell_header"]), Paragraph("Item", styles["cell_header"]),
                  Paragraph("Status", styles["cell_header"]), Paragraph("Evidence", styles["cell_header"])]
    rows = [header_row]
    for cat, item, status, evidence in sample:
        fg, bg = status_colors(status)
        pill = StatusPill(short_status_label(status), fg, bg, width=44, height=12)
        rows.append([Paragraph(cat, styles["cell"]), Paragraph(item, styles["cell"]),
                     pill, Paragraph(evidence, styles["cell"])])
    tbl = Table(rows, colWidths=[20 * mm, 55 * mm, 18 * mm, CONTENT_W - 93 * mm], repeatRows=1)
    style = [
        ("BACKGROUND", (0, 0), (-1, 0), hexc("primary")),
        ("TEXTCOLOR", (0, 0), (-1, 0), hexc("white")),
        ("BACKGROUND", (0, 1), (-1, -1), hexc("white")),
        ("LINEBELOW", (0, 0), (-1, -2), 0.4, hexc("na_bg")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 6), ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]
    tbl.setStyle(TableStyle(style))
    story.append(Paragraph("Findings Table — sample rows", styles["dash_card_h"]))
    story.append(Paragraph(
        "A preview only. Every row actually scored in this audit is listed in full under "
        "“Detailed Findings by Section” later in this report — nothing shown here is the complete table.",
        styles["section_note"]))
    story.append(Spacer(1, 2 * mm))
    story.append(tbl)
    story.append(PageBreak())


def priority_block(story, styles, title, items, color_key):
    if not items:
        return
    story.append(Paragraph(title, styles["h2"]))
    story.append(HRFlowable(width="100%", thickness=1.2, color=hexc(color_key), spaceAfter=6))
    for i, item in enumerate(items, 1):
        story.append(Paragraph(f"<b>{i}.</b> {item}", styles["list_item"]))
    story.append(Spacer(1, 4 * mm))


def section_table(story, styles, section):
    header_row = [Paragraph("Item", styles["cell_header"]), Paragraph("Status", styles["cell_header"]),
                  Paragraph("Evidence", styles["cell_header"])]
    rows = [header_row]
    for item in section["items"]:
        fg, bg = status_colors(item["status"])
        pill = StatusPill(short_status_label(item["status"]), fg, bg, width=48, height=12.5)
        rows.append([
            Paragraph(item["item"], styles["cell"]),
            pill,
            Paragraph(item["evidence"], styles["cell"]),
        ])

    tbl = Table(rows, colWidths=[46 * mm, 22 * mm, CONTENT_W - 68 * mm], repeatRows=1)
    style = [
        ("BACKGROUND", (0, 0), (-1, 0), hexc("primary")),
        ("TEXTCOLOR", (0, 0), (-1, 0), hexc("white")),
        ("LINEBELOW", (0, 0), (-1, -2), 0.4, hexc("na_bg")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]
    tbl.setStyle(TableStyle(style))

    title = f"§{section['id']} {section['title']}"
    heading = Paragraph(title, styles["h2"])
    if section.get("note"):
        note = Paragraph(section["note"], styles["section_note"])
        story.append(KeepTogether([heading, note]))
    else:
        story.append(heading)

    if not section["items"]:
        story.append(Paragraph("N/A for this account.", styles["body"]))
        story.append(Spacer(1, 3 * mm))
        return
    story.append(tbl)
    story.append(Spacer(1, 3 * mm))


def _truncate(text, limit):
    """Truncate at the last word boundary within limit and mark it with an
    ellipsis, so a shortened sample-table cell reads as intentionally
    abbreviated rather than cut off mid-sentence. Falls back to a hard cut
    at `limit` when the word-boundary rewind would lose too much text (e.g.
    a long unbroken token like a URL with no spaces early in the string
    would otherwise collapse the cut back to almost nothing)."""
    if len(text) <= limit:
        return text
    cut = text[:limit].rsplit(" ", 1)[0]
    if len(cut) < limit * 0.6:
        cut = text[:limit]
    return f"{cut.rstrip()}…"


def compute_findings_summary(data):
    pass_n = fail_n = manual_n = na_n = 0
    sample_rows = []
    for section in data["sections"]:
        for item in section["items"]:
            b = status_bucket(item["status"])
            if b == "pass":
                pass_n += 1
            elif b == "fail":
                fail_n += 1
            elif b == "na":
                na_n += 1
            else:
                manual_n += 1
            if b == "fail" and len(sample_rows) < 3:
                sample_rows.append((f"§{section['id']} {_truncate(section['title'], 16)}", item["item"],
                                     item["status"], _truncate(item["evidence"], 100)))
    for section in data["sections"]:
        if len(sample_rows) >= 5:
            break
        for item in section["items"]:
            if status_bucket(item["status"]) == "pass" and len(sample_rows) < 5:
                sample_rows.append((f"§{section['id']} {_truncate(section['title'], 16)}", item["item"],
                                     item["status"], _truncate(item["evidence"], 100)))
    return {"pass": pass_n, "fail": fail_n, "manual": manual_n, "na": na_n, "sample_rows": sample_rows}


def all_failed_items(data):
    out = []
    for section in data["sections"]:
        for item in section["items"]:
            if status_bucket(item["status"]) == "fail":
                out.append(f"[§{section['id']}] {item['item']} — {item['evidence']}")
    return out


def build_pdf(data, output_path):
    styles = build_styles()
    doc = SimpleDocTemplate(
        str(output_path), pagesize=A4,
        leftMargin=MARGIN, rightMargin=MARGIN, topMargin=MARGIN, bottomMargin=MARGIN,
    )
    story = []

    findings_summary = compute_findings_summary(data)
    dashboard_page(story, styles, data, findings_summary)

    story.append(Paragraph("Executive Summary", styles["h1"]))
    story.append(Paragraph(data["health_summary"], styles["body"]))
    story.append(Spacer(1, 3 * mm))
    story.append(Paragraph(data.get("scope_note", ""), styles["section_note"]))
    story.append(Spacer(1, 6 * mm))

    priority_block(story, styles, f"Critical — Fix Immediately ({len(data.get('critical', []))})",
                    data.get("critical", []), "fail")
    priority_block(story, styles, f"High Priority ({len(data.get('high', []))})",
                    data.get("high", []), "warn")
    priority_block(story, styles, f"Medium Priority ({len(data.get('medium', []))})",
                    data.get("medium", []), "accent")
    story.append(PageBreak())

    story.append(Paragraph("Detailed Findings by Section", styles["h1"]))
    story.append(Spacer(1, 2 * mm))
    for section in data["sections"]:
        section_table(story, styles, section)
    story.append(PageBreak())

    story.append(Paragraph("What's Working Well", styles["h1"]))
    for item in data.get("working_well", []):
        story.append(Paragraph(f"• {item}", styles["list_item"]))
    story.append(Spacer(1, 6 * mm))

    if data.get("gaps"):
        story.append(Paragraph("Gaps in This Audit Pass", styles["h2"]))
        story.append(Paragraph(
            "Items needing a follow-up query or manual client-side check — not assumed Pass/Fail.",
            styles["section_note"]))
        for item in data["gaps"]:
            story.append(Paragraph(f"• {item}", styles["list_item"]))
    story.append(PageBreak())

    failed = all_failed_items(data)
    story.append(Paragraph(f"All Failed Items — Complete ({len(failed)})", styles["h1"]))
    story.append(Paragraph(
        "Every row marked Fail in the findings tables above, in table order — the completeness "
        "backstop so nothing silently disappears during prioritization.", styles["section_note"]))
    story.append(Spacer(1, 3 * mm))
    for i, line in enumerate(failed, 1):
        story.append(Paragraph(f"{i}. {line}", styles["failed_item"]))

    def on_first_page(canvas, doc_):
        dashboard_page_background(canvas, doc_)
        canvas.saveState()
        canvas.setFont(_FONTS["regular"], 7)
        canvas.setFillColor(hexc("text"))
        canvas.drawCentredString(PAGE_W / 2, 10 * mm,
                                  f"{AGENCY_NAME} — Full Account Audit — {data['client_name']}")
        canvas.drawRightString(PAGE_W - MARGIN, 10 * mm, "Page 1")
        canvas.restoreState()

    def on_later_pages(canvas, doc_):
        draw_header_footer(canvas, doc_, data["client_name"], "Full Account Audit")

    doc.build(story, onFirstPage=on_first_page, onLaterPages=on_later_pages)


def log_run(client_slug, json_path, pdf_path, log_dir):
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / "pdf_generation_log.log"
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(f"{datetime.now().isoformat(timespec='seconds')}  client={client_slug}  "
                f"source={json_path.name}  output={pdf_path.name}\n")


def main():
    if len(sys.argv) != 3:
        print("Usage: python3 scripts/generate_audit_pdf.py <client_slug> <audit_json_path>")
        sys.exit(2)

    client_slug, json_path = sys.argv[1], Path(sys.argv[2])
    client_meta = resolve(client_slug)  # validates slug, raises KeyError if unknown

    data = json.loads(json_path.read_text(encoding="utf-8"))
    pdf_path = json_path.with_suffix(".pdf")

    build_pdf(data, pdf_path)
    log_run(client_slug, json_path, pdf_path, json_path.parent)

    print(f"PDF generated: {pdf_path}")
    print(f"Logged to: {json_path.parent / 'pdf_generation_log.log'}")


if __name__ == "__main__":
    main()
