---
description: Web animation - propose and build purposeful motion for a landing page from the 20 principles of UX & animation (Disney's 12 + UX laws), within the /55-web-guidelines-audit motion rules
---

Propose (and, after approval, build) animations for **$ARGUMENTS** - a URL, a local .html path, or a client slug (domain from `clients.json`), optionally followed by a goal or element ("CTA button", "price list", "form submit").

Based on the "20 Principles of UX & Animation" (Disney's 12 principles of animation plus UX laws). Motion must also pass `/55-web-guidelines-audit` (points 13, 19, 20, 21, 29, 41, 45, 51, 53); the recipes below are written to pass it.

## Hard rules (from /55-web-guidelines-audit, never break)

- Animate `transform` and `opacity` (plus colour, `filter`, `clip-path` when smooth). Never `width/height/top/left/margin` (point 20).
- UI feedback 100-300 ms; an action's result visible within 400 ms (Doherty). Entrances up to ~500 ms.
- Easing: ease-out for entering, ease-in-out for moving, ease-in for leaving. **No overshoot curves** (`cubic-bezier` with y < 0 or > 1) and no keyframes named bounce/elastic/wobble (point 45). "Wind-up" and "squash" are done with small keyframe steps, not bouncy curves.
- ONE designed motion moment per page (usually the first screen or the main CTA). Never the same reveal on every section (point 53). Content is visible by default; animate from a visible state (point 41).
- No auto-scrolling marquees or self-scrolling columns (point 29). No pulsing dots (45). No coloured glow as an effect (13).
- `prefers-reduced-motion: reduce`: remove movement (slides, scale, parallax, smooth scroll) but keep short colour/opacity fades - never one global `*{animation:none;transition:none}` (point 19).
- Frequent actions (menus, tabs, filters, repeated buttons) animate little or not at all; rare, important moments (submit success, first screen) may animate more.

## The 20 principles: when to use them on a landing page, and the recipe

| # | Principle | Use on landing pages for | Recipe (CSS / JS) |
|---|---|---|---|
| 1 | Squash & stretch - "things squish on impact to show weight" | CTA press, add-to-cart, toggle | `:active{transform:scale(.97)}` 100ms; on success a 160ms keyframe `0%{scale:1}40%{scale:1.04 .96}100%{scale:1}` ease-out |
| 2 | Anticipation wind-up - "a small wind-up before the big move" | send button arrow, "next" chevron, menu open | keyframe `0%{translate:0}25%{translate:-3px 0}100%{translate:12px 0}` 300ms ease-out on the icon only |
| 3 | Staging the focus - "direct the eye to one thing at a time" | first screen: headline -> sub -> CTA; modal open | dim the rest (`opacity:.5`), stagger 3 items max 60-80ms apart, total under 500ms |
| 4 | Pose to pose - "set the key poses, let the rest fill in" | multi-step morphs (button -> spinner -> check) | define states as classes (`.is-loading`, `.is-done`) and let `transition` interpolate; no hand-built frame-by-frame |
| 5 | Follow through - "parts keep moving after the main body stops" | toast/card entering, accordion contents | container ends at 240ms, its contents fade/slide in 60-80ms later |
| 6 | Slow in & slow out - "speed up and slow down, never constant" | every transition | `--ease-out:cubic-bezier(.22,1,.36,1)`, `--ease-in-out:cubic-bezier(.65,0,.35,1)`; never `linear` except progress/spinners |
| 7 | Moving in arcs - "move along curves, not straight lines" | fly-to-cart, item moving to a new spot | animate `translate` X and Y on separate tracks with different easings (X ease-out, Y ease-in) or `offset-path` |
| 8 | Secondary action - "a small flourish that backs up the main one" | "Saved" / "Sent" confirmation | check icon draws (`stroke-dashoffset`) 200ms after the label changes; one flourish, no confetti |
| 9 | Snappy timing - "duration sets the feel; keep UI under 300ms" | hovers, tooltips, dropdowns | 150-200ms hover, 200-250ms menus, tooltips 150ms; respect point 21 |
| 10 | Exaggerated feedback - "push it past real so the moment lands" | form error, wrong password | 3-step horizontal shake keyframe (`translate:-6px/6px/-3px/0`, 240ms) + red border + message (point 51) |
| 11 | Solid drawing in 3D - "give flat things depth and volume" | product/card/price-card hover | `perspective:700px` on parent, `rotateX/rotateY` up to 6deg following the pointer; off on touch and reduced motion |
| 12 | Overall appeal - "the sum of every detail, done with care" | download/submit button states | design idle, hover, press, loading, done, error for the main CTA; audit point 51 checks them |
| 13 | Fitts's law - "bigger, closer targets are faster to hit" | CTA placement, close buttons | primary CTA large and near the thumb/eye path; sticky phone bar; never a tiny far "x" |
| 14 | Bigger hit areas - "the clickable zone can be bigger than it looks" | icon buttons, small links | invisible `::after{inset:-10px}` to reach 44x44 (point 10) without changing the look |
| 15 | Hick's law - "fewer choices, faster decisions" | menus, pricing, forms | one primary CTA (point 59), progressive disclosure, max ~5 nav items |
| 16 | Miller's law - "we hold about 7 things at once, so chunk it" | phone/card numbers, long lists, steps | format phone numbers in groups (`+1 555 123 4567`), group lists in 3-7, steps 1-2-3 |
| 17 | Doherty threshold - "respond within 400ms or it feels slow" | form submit, price list open, tabs | show pressed/loading state instantly (<100ms), optimistic "Sent" when safe, skeleton for slow data |
| 18 | Postel's law - "accept messy input, give back clean output" | phone, date, name fields | accept any phone format, normalise on blur to the local format; never reject spaces/dashes |
| 19 | Jakob's law - "people expect your app to work like the others" | header, cart, forms | logo left, menu/CTA right, cart top-right, standard form order; animation never moves these |
| 20 | Frequency of use - "the more it's used, the less it should animate" | nav, tabs, filters, repeated actions | instant or <=150ms fade for frequent actions; save bigger motion for one rare moment |

## Flow

1. **Read the page** (local file, or render the URL with Playwright): sections, main CTA, forms, existing transitions/keyframes, reduced-motion block. If a `/55-web-guidelines-audit` result exists for the page (`clients/<slug>/reports/guidelines/<name>/audit.json` or `guidelines/<name>/audit.json`), read its motion points first.
2. **Propose** a table: `# | Principle | Element (selector, section) | What the visitor sees | Recipe | Why it helps (conversion / clarity)`. Max 5-7 candidates, ranked by impact; mark the ONE designed motion moment. Point out existing motion that breaks the hard rules (and which audit point it fails) as "remove/replace".
3. **Wait for approval of the exact list** (approval of the idea is not approval of the list). Never edit or deploy a live page without it.
4. **Build** in the page's own CSS/JS (inline, no new libraries unless asked), with a reduced-motion alternative for each item. Reuse the page's own easing/duration variables when it has them and keep the page's look.
5. **Check**: open the page at phone width (390px) and desktop, then re-run `/55-web-guidelines-audit` with `--before` (motion points must still pass).
6. **Deploy only after approval**, with the page's own deploy process.

Reply in the user's language; no em dash; no emoji icons in the page.
