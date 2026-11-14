# Web design rules (premium, Apple-style) - source for /55-web-guidelines-audit

Apple publishes no web guidelines (its HIG covers apps). Everything here is **convention in the
style of apple.com plus widely shared "anti AI-look" rules**, except the 44px tap target (an actual
HIG rule). `scripts/guidelines_audit.py` measures these rules on the rendered page (61 points);
this file is for designing a page so the audit passes the first time.

Sources the rules come from:
- **Impeccable** (github.com/pbakaus/impeccable) - its detector and "craft floor" rules (labels above
  headings, glass, overused fonts, glow, background haze, identical card grids, ...).
- Anti-AI-look craft checks (points 54-61: italics, monospace, buttons, real product photo,
  spacing rhythm, one primary CTA, consistent icons, play icon).
- Official guidelines cited per point in the PDF: Apple HIG, Material Design 3, IBM Carbon, WCAG 2.2,
  W3C CSS specs, WebKit, web.dev, NN/g.

Edit this file to match your own house style; keep `guidelines_audit.py` in sync if you change a number.

## Measurements

| Thing | Value |
|---|---|
| Spacing | multiples of 8px, 4px for fine steps. Applies to padding, gap AND margin. Allowed exceptions: 1-2px optical icon nudges and hairline rings; negative margins that only enlarge a tap area |
| Section padding | **96px desktop, 80px phone** (160px desktop only for a deliberately airy page). See "Spacing between sections" below |
| Side gutter / content width | 16-24px on phones; content max ~980-1200px |
| Borders | always 1px hairline; on dark backgrounds white at ~8-15% alpha |
| Radius | 4 values max, e.g. 12 (inputs, small controls), 20 (tiles, medium cards), 28 (large cards), capsule (buttons). Values = Material Design 3 shape tokens (0/4/8/12/16/20/28/32/48dp + full). Nested radius = outer radius - padding (28 with 1px ring -> 27): Apple WWDC25 "Get to know the new design system". The "max 4" limit is an in-house rule |
| Type | 4-5 text sizes max, e.g. 13 (small), 15 (UI), 17 (body), 19 (lead), plus headings; nothing under 11px. Body copy lines max ~70-80 characters |
| Font | per project, matched to the brand, with the glyphs the language needs (Cyrillic, Polish, ...). Avoid the overused set: Inter, Roboto, Fraunces, Geist, Plus Jakarta Sans, Space Grotesk |
| Letter-spacing | never tighter than -0.04em (headings -0.02 to -0.035em) |
| Line height | at least 1.3 for any text block |
| Heading rhythm | more space above a heading than below it (e.g. 32px above, 8-12px below) |
| Colour | one accent colour + neutrals (a brand pair is fine when both colours are in the logo); no glow of any kind: no coloured blurred shadows, no radial/conic colour haze in backgrounds |
| Shadows | neutral and offset only (`0 2px 6px rgba(0,0,0,.4)`, `0 16px 32px -16px rgba(0,0,0,.8)`); never a coloured shadow |
| Surfaces | solid. No decorative glass (`backdrop-filter: blur`), also not on the sticky header or the mobile bar |
| Tap targets | at least 44x44px for every link, button, tab and icon (HIG). Inline text links inside a sentence are exempt; a standalone phone link is not |
| Contrast | text meets WCAG AA (4.5:1 body, 3:1 large text); no grey text on a coloured background |

## Spacing between sections: what the official guidelines say

No official source gives one number for the gap between page sections. What they do say:

- **IBM Carbon** (carbondesignsystem.com/elements/spacing/overview): spacing scale
  2, 4, 8, 12, 16, 24, 32, 40, 48, 64, 80, 96, 160px. Larger spacing marks higher levels of
  hierarchy (so sections take the top of the scale); avoid values outside the scale; at smaller
  breakpoints move one or more steps down the scale.
- **Apple HIG, Layout**: group related items with negative space, container shapes or separator
  lines; respect system margins and safe areas. No numbers for web sections.

Applied rule: desktop sections 96px (a Carbon token), phones one step down to 80px.

## Craft rules

- Headings `text-wrap:balance`, paragraphs and list items `text-wrap:pretty` (no one-word last lines).
- `::selection{background:<brand colour>;color:#fff}` on every page; theme focus rings and scrollbars too.
- Prices, counters, table numbers: `font-variant-numeric:tabular-nums`.
- Fixed bottom bars: `padding-bottom:calc(8px + env(safe-area-inset-bottom))`.
- Never remove focus without a replacement: `outline:none` only with a visible `:focus-visible` ring.
- Icon-only buttons get an `aria-label`, images get `alt`. Never block paste in inputs. Inputs at least 16px (iOS zoom).
- One `h1` per page, no skipped heading levels.
- Motion: prefer `transform`/`opacity`; hover/press feedback ~200ms (max 300ms); ease-out entrances; no
  bounce/elastic easing, no pulsing dots; avoid animating large `blur()`/`backdrop-filter`/`box-shadow` surfaces.
- `prefers-reduced-motion`: remove the MOVEMENT (slides, scale, parallax, smooth scroll), keep short colour and
  opacity fades so state changes stay visible. Never one global `*{animation:none;transition:none}` switch-off.
- Content is visible by default: a scroll-reveal that fails must never leave text invisible.
- No auto-scrolling content (marquee rails, self-scrolling photo columns). Static rows or user-driven scrolling.
- Designing motion: use `/55-web-animation` (20 UX & animation principles with recipes that pass the audit):
  one designed motion moment per page, frequent actions animate least, feedback within 400ms.
- Forms and buttons have designed states: idle, hover, press, loading, done, error, with a readable error message.
- Disabled controls: `opacity:.5; cursor:not-allowed`.

## Patterns that read as "AI-looking" (avoid)

| Pattern | Use instead |
|---|---|
| macOS window frame: red/yellow/green "traffic light" dots, fake title bar around a form, map, screenshot or card | plain card, content starts at the top |
| ANY small label above a heading: kicker, eyebrow, tinted pill, neutral capsule | nothing: the heading carries itself; put the info in the heading or the text below |
| Glowing dots as bullets in chips, eyebrows, marquee pills, list tiles (`box-shadow:0 0 10px <colour>` on a dot) | no dot, or a thin checkmark icon for list items |
| Emoji as icons | inline SVG line icons |
| Coloured glow: blurred coloured shadow under buttons, around forms, on icon tiles | neutral offset shadow or none |
| Radial / conic colour haze or spotlight behind sections, cards, forms | plain background or a photo |
| Decorative grid / dot pattern as a background | plain background |
| Decorative glass (`backdrop-filter: blur`) on header, bars, buttons, chips | solid surface in the page colour |
| Gradient text (`background-clip:text`) on headings or prices | solid colour; emphasis by weight or size |
| Rounded icon tile stacked above a card heading | icon beside the heading, a thin line icon without a tile, or no icon |
| Row of 3+ identical cards (icon + heading + text) as the page structure | columns under one hairline, a list, or one lead item |
| Card inside a card (e.g. a tinted "bonus" box inside an offer card) | a hairline divider and spacing |
| Numbered sections ("01 / 02 / 03") as decoration | real headings |
| Big bare number as a "hero metric" (64px+, e.g. a price at 88px) | the number inside the heading or text, 40-48px |
| Crushed headline tracking (< -0.04em) | -0.02 to -0.035em |
| Random word in italics inside a heading ("Wide-*open* thinking") | one style for the whole heading |
| Monospace / blinking cursor as a "technical" look | main font; monospace only for code, IDs, measurements |
| Buttons in many ad-hoc styles | 2-3 variants: primary (filled), secondary (outline), text |
| Abstract illustration instead of the real product, place or team | a real photo, product shot or video on the first screen |
| Same gap everywhere | tight inside groups (8-12), wider between groups (24-48), widest between sections (80-96) |
| Two neighbouring CTAs with the same filled style | one filled primary per group, the other outline/text |
| Mixed icon styles (filled + outline, several stroke widths) | one icon set, one stroke width |
| Play triangle centred by its box | shift it ~5-8% right (optical centre) |
| Vague slogan headline ("Curiosity, meet clarity.", "Not X. Just Y.") | a specific one ("Cited answers from papers", "Diagnostics in 30 min") |
| Buzzword copy ("seamless", "unlock", "elevate", "game-changer") | plain, concrete wording |
| Long dash (em dash) in any text | short hyphen " - " |

## Lessons from real pages

- Hard edges where a section background meets the next section: fade it in/out with a vertical mask
  (`mask-image:linear-gradient(180deg,transparent,#000 220px,#000 calc(100% - 220px),transparent)`).
- Hidden-by-default content (price lists, FAQs) must look expandable: a strong button with a
  chevron, plus a faded preview of the first rows.
- Rows that scroll sideways on phones need visible affordance: arrow buttons, edge fades, a
  one-time peek scroll; pop-ups must not be clipped on a 390px screen.
