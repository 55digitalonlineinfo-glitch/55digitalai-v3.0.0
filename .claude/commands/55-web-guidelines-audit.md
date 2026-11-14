---
description: Website guidelines audit - 61 design / mobile / accessibility / anti-AI-look points measured on the real page, annotated before/after screenshots, fix summary, client PDF and /55-web-animation ideas
---

Run the website guidelines audit for **$1** (a URL, a local .html path, or a client slug whose domain you look up in `clients.json`). Read-only - never changes the page.

Always use the script, never a shortened list or a manual check:

`.venv/bin/python3 scripts/guidelines_audit.py <url|path> [--client slug] [--name name] [--exceptions 11,20] [--title "..."] [--logo path] [--primary "#hex"] [--before <baseline>/audit.json] [--no-pdf]`

- Measures all 61 points on the rendered page (desktop 1440px, phone points in iPhone 390px emulation), draws annotated screenshots and writes `clients/<slug>/reports/guidelines/<name>/` with `--client <slug>` (always pass it for a client page; your own pages or a prospect without a client folder go to `guidelines/<name>/`): PDF, report.md, audit.json, img/.
- Needs Playwright's Chromium once: `.venv/bin/python3 -m playwright install chromium`.
- Rules behind the points: `system-prompts/frameworks/web-design-rules.md` (Impeccable rules, anti-AI-look craft checks and official guidelines). Every point has a one-line **Why** (why we check it, why it is best practice) on its PDF card and in report.md, and a source link (Apple HIG, Material 3, IBM Carbon, WCAG / W3C, web.dev, NN/g, Impeccable).
- Report branding defaults to `brand_config.json` (agency name, logo, accent colour); `--logo` / `--primary` override it per report.

## The 61 points (number as shown | priority H/M/L | phone = measured at 390px)

| # | Point | Pri | | # | Point | Pri |
|---|---|---|---|---|---|---|
| 1 | Section spacing | M | | 32 | Heading rhythm (more space above than below) | L |
| 2 | Phone side margins (phone) | H | | 33 | No one-word last lines | L |
| 3 | Content width | M | | 34 | Text selection colour (::selection) | L |
| 4 | Borders 1px | L | | 35 | No hero-metric numbers (64px+) | L |
| 5 | Nested corner radius | M | | 36 | Line height >= 1.3 | M |
| 6 | Radius scale (max 4) | M | | 37 | Text setting (justify, long caps, wide tracking) | L |
| 7 | Spacing grid 4/8px | M | | 38 | Heading order (one h1, no skipped levels) | M |
| 8 | Type scale (max 5, min 11px) | M | | 39 | No grey text on colour | M |
| 9 | Line length <= 80 | M | | 40 | Inner padding (text not glued to box edge) | L |
| 10 | Tap target 44px (phone) | H | | 41 | All text visible (failed scroll-reveal) | H |
| 11 | Accent colour (1-3 hues; none fails too) | L | | 42 | Text not covered | H |
| 12 | No labels above headings (capsules too) | M | | 43 | First-screen columns balanced | M |
| 13 | No glow (dots, coloured shadows) | M | | 44 | Sideways rows + clipped pop-ups (phone) | M |
| 14 | Balanced headings (phone) | L | | 45 | Calm motion (no bounce easing, no pulsing dots) | L |
| 15 | Equal-width digits | L | | 46 | No decorative grid background | L |
| 16 | Bottom bar and iPhone safe area (phone) | H | | 47 | Palette without AI cliches | L |
| 17 | Visible focus | H | | 48 | No numbered sections (01/02/03) | L |
| 18 | Labels on icon buttons + alt (phone) | H | | 49 | Main headline size | L |
| 19 | Reduced motion: selective, no global switch-off (phone) | M | | 50 | Copy without AI cliches (UA/RU/PL/EN) | M |
| 20 | Animation without layout change | M | | 51 | Interface states + error messages | M |
| 21 | Button feedback <= 300ms | M | | 52 | Browser details (scrollbar, caret) | L |
| 22 | Text contrast WCAG AA | H | | 53 | One motion moment | L |
| 23 | No decorative glass | M | | 54 | No random italic words | L |
| 24 | Font not overused (Inter, Roboto, Geist...) | L | | 55 | Monospace only for code | L |
| 25 | Letter-spacing >= -0.04em | L | | 56 | One button system | M |
| 26 | No icon tiles above headings | M | | 57 | Real product / photo on the first screen | M |
| 27 | No grid of identical cards | M | | 58 | Spacing rhythm (not one gap everywhere) | L |
| 28 | No card inside a card | L | | 59 | One primary CTA per group | M |
| 29 | No auto-scrolling | M | | 60 | Consistent icons (one stroke/style) | L |
| 30 | No gradient text | L | | 61 | Play icon optically centred | L |
| 31 | No coloured background haze | M | | | | |

Point notes: 10 skips links inside `<footer>` / `role=contentinfo` (dense footer link lists, like apple.com's). 33 treats two words tied with a non-breaking space as one unit (that IS the fix). 42 ignores text clipped by its own overflow box (marquees, collapsed panels). Points that pass with nothing to mark still get a context screenshot (green box); only N/A points have no screenshot.

## Output rules

- **ALL 61 points, always** - chat reply, report.md and PDF. Never only the failures, never "the rest pass", never merged rows. N/A and EXCEPTION points are listed with the reason. If the script outputs fewer than 61 points, that is a bug: fix the script and re-run.
- **Chat reply format:** first the High / Medium / Low fix summary (what + how), then one table of all 61 rows in point order with columns
  `# | Result (PASS/FAIL/EXCEPTION/N/A) | Point | Measured finding | Why we need it | Proposed fix`
  - Measured finding = the script's text with the real values (not just the title).
  - Why we need it = the point's Why line (report.md, last column).
  - Proposed fix = the script's fix text for FAIL rows (exact selector / CSS change when known); "-" for PASS / N/A.
  - Count the rows before sending: exactly 61, numbered 1-61.
- **Check every FAIL screenshot** before calling it done (downscale it first, e.g. `sips -Z 700` on macOS or PIL elsewhere) - heuristics can misfire (e.g. 5 only sees parent/child pairs, 60 counts SVG stroke attributes). Fix the script, not the report, when a finding is wrong.
- `--exceptions` takes point numbers as shown (1-61) for points the site owner keeps on purpose (amber instead of red).

## Flow (every run)

1. **Scan** with `--no-pdf` and save the result as the baseline right away:
   copy `<folder>/audit.json` and `<folder>/img/` to `<folder>-baseline/` (a later run rotates `audit.json`/`img/` into `audit.prev.json`/`img.prev/` only ONCE, so a second re-scan or the PDF run would lose the before shots). Show the fix summary + the 61-row table.
2. **Animation ideas** (see below) after the table, when applicable.
3. **Propose concrete fixes** for every FAIL (exact selector / CSS / HTML change, file to edit) and **apply them only after the user approves the exact list**. Approval of the approach is not approval of the list. Never edit or deploy a live page without it. Follow `system-prompts/frameworks/web-design-rules.md` and check the page on a phone-width viewport after the change.
4. **Re-scan** the fixed page (deployed URL, or a local fixed copy before deploy) with `--before <folder>-baseline/audit.json`. Every card then shows BEFORE and AFTER screenshots side by side **of the same part of the same section** (the before run stores each crop relative to its section in audit.json `crop`; the after run cuts that exact region at the same pixel size, even if the flagged element was removed). Before sending, verify every pair is the same size (`img/pNN_before.jpg` vs `img/pNN.jpg`). Changed values get "Before: X", fixed points that still FAIL are reported, never hidden. A report after fixes is never after-only. If the baseline was lost, rebuild it by auditing a saved copy of the old HTML first.
5. **ALWAYS ask "PDF for the client?"** (AskUserQuestion: yes / no). The report and PDF are in English only. Client branding: `--logo clients/<slug>/logo.png --primary "<brand hex>"`. Then run again without `--no-pdf`, with `--before <folder>-baseline/audit.json` when fixes were made.
6. **QA the PDF** before handing it over: the script renders `qa/pageN.png` (macOS only; skip with `--no-qa` elsewhere); look at the cover and 2-3 card pages downscaled, and fix any "content touching the footer" warning.

## What the PDF contains

- Cover: score (with `--before`: "Before: X / 61 ... After: Y / 61"), the 61-point list in 3 columns, KPI tiles.
- "What to fix" page(s) by priority when anything fails.
- With `--before`: "What we changed and why" pages - every point that went FAIL -> PASS with its fix and its Why.
- One card per point: result chip, measured finding, **Why**, fix (when failing), BEFORE / AFTER screenshots, source link.

## Animation ideas (after every scan)

After the 61-row table, if any motion point fails (13 glow, 19 reduced motion, 20 layout animation, 21 button feedback, 29 auto-scroll, 41 hidden text, 45 calm motion, 51 interface states, 53 one motion moment), or the page has no designed motion at all, add a short "Animation ideas (/55-web-animation)" list: 2-5 candidates from `.claude/commands/55-web-animation.md` (20 UX & animation principles), each as `principle -> element -> why`. Examples: 21 fail -> "Snappy timing + squash on the CTA press"; 51 fail -> "Pose to pose: idle / loading / done states on the submit button (Doherty < 400ms)"; 53 fail -> "Staging: one first-screen sequence, other sections static"; 29 fail -> "replace the marquee with a static row; motion only on user scroll". Only offer; build nothing until the user runs `/55-web-animation` or approves the exact list. Any animation added must still pass points 13, 19, 20, 21, 29, 41, 45, 51 and 53.

Reply in the user's language; no em dash.
