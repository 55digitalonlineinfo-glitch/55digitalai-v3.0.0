#!/usr/bin/env python3
"""
guidelines_audit.py - the 61-point website design / mobile / accessibility guidelines audit for ANY page,
as a client-ready PDF with an annotated screenshot and a source link for every point.

Purpose
    Works on any public page or local .html file. Opens the page in Playwright
    (desktop 1440px + iPhone 390px emulation), measures all 61 points from the real rendered DOM and
    CSS, draws measurement boxes over the offending (or representative) elements, and builds the
    dark A4 glass PDF (same look as scripts/feed_report_pdf.py). Every point gets a verdict:
    PASS / FAIL / EXCEPTION (a conscious design choice, set with --exceptions) / N/A (element not on the page).
    FAIL points carry a concrete "what to fix"; a High / Medium / Low fix summary opens the report.

    The 35 points (shown numbers): 1 section spacing, 2 phone side margins, 3 content width, 4 borders 1px, 5 nested radius,
    6 radius scale, 7 spacing grid 4/8px, 8 type scale, 9 line length, 10 tap targets 44px, 11 accent colours,
    12 no labels above headings, 13 no glow (dots, buttons, cards), 14 balanced headings, 15 tabular numbers, 16 safe area
    (iPhone home bar), 17 visible focus, 18 labels on icon buttons + alt, 19 reduced motion (selective, no global switch-off),
    20 no layout animation, 21 button feedback <=300ms, 22 text contrast (WCAG AA),
    adopted from Impeccable (pbakaus/impeccable) on 2026-11-13: 23 no decorative glass, 24 font not overused (Inter, Roboto...),
    25 letter-spacing >= -0.04em, 26 no icon tiles above headings, 27 no grid of identical cards, 28 no card inside a card,
    29 no auto-scrolling marquee, 30 no gradient text, 31 no coloured radial/conic background haze, 32 heading rhythm
    (more space above than below), 33 no one-word last lines in body text, 34 themed ::selection, 35 no hero-metric numbers (64px+).
    More Impeccable detector + craft-floor checks (2026-11-13): 36 line height >= 1.3, 37 text setting (justify / long caps /
    wide tracking), 38 heading order, 39 no grey on colour, 40 inner padding, 41 all text visible (failed reveals), 42 text not
    covered, 43 balanced first-screen columns, 44 sideways rows + clipped pop-ups (phone), 45 calm motion (no bounce, no pulsing
    dots), 46 no decorative grid background, 47 palette without AI cliches, 48 no numbered sections, 49 main headline size,
    50 copy without AI cliches (UA/RU/PL/EN buzzwords, "Not X. Just Y.", "X, meet Y."), 51 interface states + error messages,
    52 browser details (scrollbar, caret), 53 one motion moment.
    Anti-AI-look craft checks (2026-11-13): 54 no random italic words, 55 monospace only for code, 56 one
    button system, 57 real product/photo on the first screen, 58 spacing rhythm, 59 one primary CTA, 60 consistent icons,
    61 play icon optically centred. Every point also carries a one-line "Why" (WHY dict) shown on its PDF card and in report.md.

Setup / usage
    .venv/bin/python scripts/guidelines_audit.py <url | path/to/page.html> [options]
      --client SLUG        client slug: output goes to clients/<SLUG>/reports/guidelines/<NAME>/
                           (without it: guidelines/<NAME>/, for your own pages or a prospect)
      --name NAME          output folder name (default: from the URL)
      --exceptions 11,20   point numbers (as shown, 1-61) that are conscious design exceptions (shown amber instead of red)
      --title TEXT         page title shown in the report (default: host + path)
      --logo PATH          logo for the header (default: logo_path from brand_config.json)
      --primary "#hex"     accent colour of the report (default: accent colour from brand_config.json)
      --no-pdf             measure + shots + audit.json/report.md only
      --no-qa              skip the page-by-page PNG render used for checking the PDF
      --before PATH        earlier audit.json (guidelines/<SLUG>/audit.prev.json) for 'Before: X' notes
    Output folder (see --client): "<NAME> - guidelines.pdf" + .html, audit.json, report.md, img/, qa/
    The console prints the High / Medium / Low fix summary first, then the full 61-row table.

Notes
    - Rules and numbers come from system-prompts/frameworks/web-design-rules.md and the sources listed
      per point in the PDF (Apple HIG, Material 3, IBM Carbon, WCAG 2.2, W3C, web.dev, NN/g).
    - Third-party cookie banners are ignored. Pages behind a login/403 cannot be audited.
    - Heuristics are conservative but not perfect (e.g. point 5 only sees parent/child pairs); read the
      screenshot of each FAIL before sending the report to a client.

Changelog
    2026-11-13  v3.1 - comparable before/after: every screenshot stores its crop relative to the page section it sits in
                     (audit.json "crop": section id / tag+class+order, offset, size; viewport frame for the bottom bar). With
                     --before the after shot cuts exactly the same part of the same section, same pixel size, even when the
                     flagged element was removed or the page got shorter. Crops are whole pixels and never run past the page end.
    2026-11-13  v3 - 61 points: 18 more Impeccable checks (36-53) and 8 anti-AI-look craft checks (54-61); point 11 now also fails
                     with NO accent colour; WHY line on every card; cover list in 3 columns; with --before the cover shows the
                     before score and a "What we changed and why" section lists every fixed point.
    2026-11-13  v2 - 13 new points from the Impeccable design rules (35 points): glass, overused font, crushed tracking,
                     icon tiles, identical card grids, nested cards, marquee, gradient text, colour haze, heading rhythm,
                     one-word last lines, ::selection, hero-metric numbers. Point 12 (label above heading) now fails for ANY
                     label (capsules too), point 13 covers every coloured glow (not only dots), point 19 fails a global
                     *{animation:none;transition:none} reduced-motion switch-off. Internal ids 25-37; --before still matches by id.
    2026-11-11  v1 - generalised from a manual one-page audit into a script for any page.
    2026-11-11  v1.5 - point 10 skips links inside <footer> / role=contentinfo (dense text link lists, same as apple.com's footer).
    2026-11-11  v1.4 - before/after shots frame the SAME element: audit.json stores a CSS path (anchor) of each point's first mark and the
                     re-scan crops around it instead of around its own first mark.
    2026-11-11  v1.3 - --before also puts the earlier screenshot of each point next to the new one ("Before" / "After"); previous
                     screenshots are kept in img.prev/.
    2026-11-11  v1.2 - removed the glow and macOS-window checks (22 points, numbered 1-22; --before still matches by internal id).
    2026-11-11  v1.1 - --client: output into clients/<slug>/reports/guidelines/, the script stays generic in scripts/.
    2026-11-11  --before <audit.json>: 'Before: <value>' on points whose value changed; the previous
                     run's audit.json is kept as audit.prev.json automatically.
"""
import argparse, datetime, json, os, pathlib, re, shutil, subprocess, sys, tempfile, urllib.parse
from PIL import Image

WS = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(WS / "scripts"))
from feed_report_pdf import CSS as BASE_CSS, SWIFT_QA, hex_rgb  # noqa: E402
from brand import AGENCY_NAME, COLORS, LOGO_PATH  # noqa: E402  (brand_config.json)

# ---------------------------------------------------------------------------------------------
# Browser-side measurement. One call per viewport (desktop / phone); Python picks the right one per point.
# Every mark is {c: color key, r: [x, y, w, h] in page coordinates, v: short value, f: filled band}.
# ---------------------------------------------------------------------------------------------
COLLECT_JS = r"""
async (opt) => {
const out = {};
const $$ = s => [...document.querySelectorAll(s)];
const px = v => parseFloat(v) || 0;
const SKIP = '[class*="cky"],[id*="cky"],[class*="cookie"],[id*="cookie"],[class*="consent"],[id*="consent"],[id*="onetrust"],[id*="CookieBanner"],[id*="usercentrics"],[class*="CookieConsent"]';
const clipCache = new Map();
const clipped = e => { let n = e.parentElement, i = 0;
  while (n && n !== document.body && i++ < 8) {
    if (clipCache.has(n)) { if (clipCache.get(n)) return true; n = n.parentElement; continue; }
    const s = getComputedStyle(n), r = n.getBoundingClientRect();
    const c = (s.overflow !== 'visible' || s.overflowY !== 'visible') && r.height < 2;
    clipCache.set(n, c); if (c) return true; n = n.parentElement; }
  return false; };
const vis = e => { const r = e.getBoundingClientRect(); if (r.width < 1 || r.height < 1) return false;
  const s = getComputedStyle(e); if (s.visibility === 'hidden' || s.display === 'none' || +s.opacity < 0.05) return false;
  if (e.closest(SKIP) || e.closest('[aria-hidden="true"]') && !e.closest('a,button')) return false;
  if (r.right < 0 || r.left > innerWidth + 50) return false; return !clipped(e); };
const selOf = e => { const p = []; while (e && e !== document.body && e.parentElement) { p.unshift(e.tagName.toLowerCase() + ':nth-child(' + ([...e.parentElement.children].indexOf(e) + 1) + ')'); e = e.parentElement; } return 'body > ' + p.join(' > '); };
const rect = e => { const r = e.getBoundingClientRect(), a = [Math.round(r.left + scrollX), Math.round(r.top + scrollY), Math.round(r.width), Math.round(r.height)]; a.sel = selOf(e); return a; };
const els = $$('body *').filter(e => e instanceof HTMLElement && !/^(SCRIPT|STYLE|NOSCRIPT|LINK|META|BR|TEMPLATE)$/.test(e.tagName) && vis(e));
const cs = new Map(els.map(e => [e, getComputedStyle(e)]));
const col = s => { const m = (s || '').match(/rgba?\(([^)]+)\)/); if (!m) return [0, 0, 0, 0];
  const p = m[1].split(/[ ,\/]+/).filter(Boolean).map(parseFloat); return [p[0], p[1], p[2], p.length > 3 ? p[3] : 1]; };
const hsl = ([r, g, b]) => { r /= 255; g /= 255; b /= 255; const mx = Math.max(r, g, b), mn = Math.min(r, g, b), l = (mx + mn) / 2; let h = 0, s = 0;
  if (mx !== mn) { const d = mx - mn; s = l > .5 ? d / (2 - mx - mn) : d / (mx + mn);
    h = mx === r ? ((g - b) / d + (g < b ? 6 : 0)) : mx === g ? ((b - r) / d + 2) : ((r - g) / d + 4); h *= 60; } return [h, s, l]; };
const hex = ([r, g, b]) => '#' + [r, g, b].map(x => Math.round(x).toString(16).padStart(2, '0')).join('');
const text = e => [...e.childNodes].filter(n => n.nodeType === 3).map(n => n.textContent).join('').replace(/\s+/g, ' ').trim();
const mk = (c, r, v, f) => ({ c, r: [...r], sel: r.sel, v: String(v === undefined ? '' : v), f: !!f });
const lab = e => e.tagName.toLowerCase() + (typeof e.className === 'string' && e.className.trim() ? '.' + e.className.trim().split(/\s+/)[0] : '');
const num = v => Math.round(v * 10) / 10;
const lh = s => { const fs = px(s.fontSize); return s.lineHeight === 'normal' ? fs * 1.2 : px(s.lineHeight); };
const trect = e => { const rg = document.createRange(); rg.selectNodeContents(e); return rg.getBoundingClientRect(); };
const inScroller = e => { let n = e.parentElement; while (n && n !== document.body) { const s = getComputedStyle(n);
  if (/(auto|scroll)/.test(s.overflowX) && n.scrollWidth > n.clientWidth + 4) return true; n = n.parentElement; } return false; };
const pct = (a, p) => { const s = [...a].sort((x, y) => x - y); return s[Math.min(s.length - 1, Math.max(0, Math.floor(p * (s.length - 1))))]; };
const run = (n, f) => { try { out[n] = f(); } catch (e) { out[n] = { err: String(e) }; } };
const firstHead = $$('h1,h2').filter(vis)[0];

// 1 section spacing
run(1, () => {
  let secs = $$('section').filter(s => !s.parentElement.closest('section') && vis(s) && s.getBoundingClientRect().height > 120);
  if (secs.length < 2) secs = $$('main > *, body > div > *').filter(s => vis(s) && s.getBoundingClientRect().height > 120 && !/^(HEADER|FOOTER|NAV)$/.test(s.tagName));
  const gaps = [];
  for (let i = 0; i < secs.length - 1; i++) { const a = secs[i], b = secs[i + 1], sa = getComputedStyle(a), sb = getComputedStyle(b), ra = a.getBoundingClientRect(), rb = b.getBoundingClientRect();
    const extra = Math.max(0, rb.top - ra.bottom), sA = px(sa.paddingBottom) + px(sa.marginBottom), sB = px(sb.paddingTop) + px(sb.marginTop);
    gaps.push({ g: sA + sB + extra, sides: [sA, sB].filter(x => x > 0), pa: px(sa.paddingBottom), pb: px(sb.paddingTop), ra: rect(a), rb: rect(b) }); }
  const sorted = [...gaps].sort((x, y) => x.g - y.g), med = sorted[Math.floor(sorted.length / 2)];
  return { gaps: gaps.map(x => num(x.g)), sides: gaps.flatMap(x => x.sides.map(num)), marks: med ? [
    mk('b', [med.ra[0], med.ra[1] + med.ra[3] - Math.max(med.pa, 4), med.ra[2], Math.max(med.pa, 4)], num(med.pa) + 'px', true),
    mk('a', [med.rb[0], med.rb[1], med.rb[2], Math.max(med.pb, 4)], num(med.pb) + 'px', true)] : [] }; });

// 2 phone side margins
run(2, () => {
  const L = [], R = [], modes = {};
  els.forEach(e => { const t = text(e); if (t.length < 2 || cs.get(e).position === 'fixed' || inScroller(e)) return;
    const rg = document.createRange(); rg.selectNodeContents(e); const r = rg.getClientRects()[0]; if (!r || r.width < 4) return;
    const l = Math.round(r.left * 2) / 2; L.push({ l, e }); modes[l] = (modes[l] || 0) + 1;
    const br = e.getBoundingClientRect(); if (/^(P|H1|H2|H3|LI)$/.test(e.tagName) && br.width > innerWidth * .5) R.push(innerWidth - br.right); });
  if (!L.length) return { err: 'no text' };
  const minL = L.reduce((a, b) => b.l < a.l ? b : a), minR = R.length ? Math.min(...R) : 999;
  const mode = +Object.entries(modes).filter(([k]) => +k >= 4).sort((a, b) => b[1] - a[1])[0][0];
  const y = firstHead ? rect(firstHead)[1] : 0, vw = innerWidth;
  return { min: num(Math.min(minL.l, minR)), mode, vw, marks: [mk('r', rect(minL.e), num(minL.l) + 'px'),
    mk('b', [0, y, mode, 260], mode + 'px', true), mk('b', [vw - mode, y, mode, 260], mode + 'px', true)] }; });

// 3 content width
run(3, () => {
  const T = els.filter(e => /^(P|H1|H2|H3|LI|A|BUTTON|SPAN|DIV)$/.test(e.tagName) && text(e).length > 3 && !e.closest('header,footer,nav') && cs.get(e).position !== 'fixed' && !inScroller(e));
  if (T.length < 3) return { err: 'few text elements' };
  const lefts = [], rights = [];
  T.forEach(e => { const rg = document.createRange(); rg.selectNodeContents(e); const r = rg.getBoundingClientRect(); lefts.push(r.left); rights.push(r.right); });
  const l = pct(lefts, .03), r = pct(rights, .97), y = firstHead ? rect(firstHead)[1] : 0, vw = innerWidth;
  return { l: Math.round(l), r: Math.round(r), vw, marks: [mk('b', [l, y, r - l, 300], Math.round(r - l) + 'px'),
    mk('a', [0, y, l, 300], Math.round(l) + 'px', true), mk('a', [r, y, vw - r, 300], Math.round(vw - r) + 'px', true)] }; });

// 4 borders
run(4, () => {
  const widths = {}, heavy = new Set(); let sample = null, wmax = 0;
  els.forEach(e => { const s = cs.get(e); const r = e.getBoundingClientRect();
    ['Top', 'Right', 'Bottom', 'Left'].forEach(sd => { const w = px(s['border' + sd + 'Width']);
      if (w > 0 && s['border' + sd + 'Style'] !== 'none' && col(s['border' + sd + 'Color'])[3] > 0.05) {
        widths[w] = (widths[w] || 0) + 1;
        if (w >= 1.5 && r.height > 6 && r.width > 6) { heavy.add(e); wmax = Math.max(wmax, w); } else if (!sample && r.height > 40 && r.width > 80) sample = e; } }); });
  const H = [...heavy];
  return { widths, heavy: H.length, wmax, marks: H.length ? H.slice(0, 4).map(e => mk('r', rect(e), num(px(cs.get(e).borderTopWidth) || wmax) + 'px')) : (sample ? [mk('g', rect(sample), '1px')] : []) }; });

// 5 nested radius
run(5, () => {
  const pairs = [];
  els.forEach(p => { const sp = cs.get(p), R = px(sp.borderTopLeftRadius); if (R < 4) return; const r = p.getBoundingClientRect(); if (R >= Math.min(r.width, r.height) / 2 - 1) return;
    [...p.children].forEach(c => { if (!cs.has(c)) return; const Rc = px(cs.get(c).borderTopLeftRadius); if (Rc < 2) return; const rc = c.getBoundingClientRect();
      if (Rc >= Math.min(rc.width, rc.height) / 2 - 1) return;
      const inset = Math.min(rc.left - r.left, rc.top - r.top, r.right - rc.right, r.bottom - rc.bottom); if (inset > 16 || inset < 0) return;
      const exp = Math.max(0, R - inset); pairs.push({ ok: Math.abs(Rc - exp) <= 2, R, Rc, inset: num(inset), exp: num(exp), p, c }); }); });
  const bad = pairs.filter(x => !x.ok), pick = bad[0] || pairs[0];
  return { pairs: pairs.length, bad: bad.length, R: pick ? num(pick.R) : 0, Rc: pick ? num(pick.Rc) : 0, inset: pick ? pick.inset : 0, exp: pick ? pick.exp : 0,
    marks: pick ? [mk(pick.ok ? 'g' : 'r', rect(pick.p), num(pick.R) + 'px'), mk(pick.ok ? 'b' : 'a', rect(pick.c), num(pick.Rc) + 'px')] : [] }; });

// 6 radius scale
run(6, () => {
  const rad = {};
  els.forEach(e => { const t = cs.get(e).borderTopLeftRadius; if (t.includes('%')) return; const R = Math.round(px(t)); const r = e.getBoundingClientRect();
    if (R < 3 || R >= Math.min(r.width, r.height) / 2 - 1 || r.height < 16) return; (rad[R] = rad[R] || { n: 0, e }).n++; });
  const list = Object.entries(rad).map(([R, o]) => ({ R: +R, n: o.n, e: o.e })).sort((a, b) => a.R - b.R);
  return { radii: list.map(x => ({ R: x.R, n: x.n })), marks: list.slice(0, 6).map(x => mk('b', rect(x.e), x.R + 'px')) }; });

// 7 spacing grid
run(7, () => {
  let tot = 0, off = 0; const offv = {};
  els.forEach(e => { const s = cs.get(e); if (s.display === 'inline') return;
    ['paddingTop', 'paddingRight', 'paddingBottom', 'paddingLeft', 'marginTop', 'marginBottom', 'rowGap', 'columnGap'].forEach(k => {
      if (s[k] === 'normal') return; const v = px(s[k]); if (v <= 0 || v > 200) return; tot++;
      const m = v % 4; if (m > 0.05 && 4 - m > 0.05) { off++; (offv[num(v)] = offv[num(v)] || { n: 0, e }).n++; } }); });
  const top = Object.entries(offv).map(([v, o]) => ({ v: +v, n: o.n, e: o.e })).sort((a, b) => b.n - a.n).slice(0, 3);
  return { tot, off, top: top.map(x => ({ v: x.v, n: x.n })), marks: top.map(x => mk('r', rect(x.e), x.v + 'px')) }; });

// 8 type scale
run(8, () => {
  const sz = {}, small = [];
  els.forEach(e => { if (!text(e)) return; const f = Math.round(px(cs.get(e).fontSize) * 2) / 2; if (f < 24) { (sz[f] = sz[f] || { n: 0, e }).n++; } if (f < 11) small.push(e); });
  const list = Object.entries(sz).map(([f, o]) => ({ f: +f, n: o.n, e: o.e })).sort((a, b) => a.f - b.f).filter(x => x.n >= 2);
  return { sizes: list.map(x => ({ f: x.f, n: x.n })), small: small.length,
    marks: small.slice(0, 2).map(e => mk('r', rect(e), px(cs.get(e).fontSize) + 'px')).concat(list.slice(0, 6).map(x => mk('b', rect(x.e), x.f + 'px'))) }; });

// 9 line length
run(9, () => {
  let best = null;
  els.filter(e => /^(P|LI|BLOCKQUOTE|DD|H1|H2|H3|DIV|SPAN)$/.test(e.tagName)).forEach(e => {
    const leafBox = /^(DIV|SPAN)$/.test(e.tagName); if (leafBox && /flex|grid/.test(cs.get(e).display)) return;
    const t = (leafBox ? text(e) : (e.innerText || '').replace(/\s+/g, ' ').trim()); if (t.length < 50 || t.length > 1200) return;
    if ([...e.children].some(c => cs.get(c) && cs.get(c).display !== 'inline' && (c.innerText || '').trim().length > 20)) return;
    const s = cs.get(e), h = e.getBoundingClientRect().height - px(s.paddingTop) - px(s.paddingBottom), lines = Math.max(1, Math.round(h / lh(s)));
    if (lines < 2 && e.tagName !== 'P') return;   // one-line row labels are UI, not running text
    const cpl = Math.min(t.length, Math.round(t.length / lines)); if (!best || cpl > best.cpl) best = { cpl, e }; });
  return best ? { cpl: best.cpl, marks: [mk(best.cpl > 80 ? 'r' : 'b', rect(best.e), best.cpl)] } : { err: 'no paragraphs' }; });

// 10 tap targets
run(10, () => {
  const seen = new Set(), items = [];
  $$('a[href],button,input:not([type=hidden]),select,textarea,summary,[role=button],[role=tab]').forEach(e => {
    if (!vis(e) || e.closest('footer,[role=contentinfo]')) return; let t = e; const type = (e.getAttribute('type') || '').toLowerCase();   // footer link lists are exempt (apple.com: all 75 footer links are 14px text rows, under 44px)
    if (type === 'checkbox' || type === 'radio') { const l = e.closest('label') || (e.id && document.querySelector('label[for="' + e.id + '"]')); if (l) t = l; }
    if (e.tagName === 'A' && getComputedStyle(e).display === 'inline') { const p = e.parentElement; if (p && p.innerText && p.innerText.trim().length > (e.innerText || '').trim().length + 12) return; }
    if (seen.has(t)) return; seen.add(t); const r = t.getBoundingClientRect(); let w = r.width, h = r.height;
    ['::before', '::after'].forEach(ps => { const q = getComputedStyle(t, ps);   // an invisible absolutely positioned pseudo-element can enlarge the hit area
      if (q.content !== 'none' && q.position === 'absolute') { w = Math.max(w, px(q.width)); h = Math.max(h, px(q.height)); } });
    items.push({ w: Math.round(w), h: Math.round(h), e: t }); });
  const bad = items.filter(x => Math.min(x.w, x.h) < 44).sort((a, b) => Math.min(a.w, a.h) - Math.min(b.w, b.h));
  const mn = bad[0];
  return { total: items.length, bad: bad.length, minw: mn ? mn.w : 0, minh: mn ? mn.h : 0,
    marks: bad.length ? bad.slice(0, 10).map(x => mk('r', rect(x.e), x.w + '×' + x.h)) : items.slice(0, 6).map(x => mk('g', rect(x.e), x.w + '×' + x.h)) }; });

// 11 accent colours
run(11, () => {
  const bk = {};
  const add = (c, e) => { const [r, g, b, a] = c; if (a < 0.5) return; const [h, s, l] = hsl([r, g, b]); if (s < 0.35 || l < 0.18 || l > 0.85) return;
    const k = Math.floor(((h + 20) % 360) / 40); (bk[k] = bk[k] || { n: 0, e, c: hex([r, g, b]) }).n++; };
  const grad = (e, s) => { const bi = s.backgroundImage; if (!bi || !/gradient/.test(bi)) return [];
    if (!(e.matches('a,button,[class*=btn],[class*=button]') || /text/.test(s.webkitBackgroundClip || s.backgroundClip))) return [];
    return (bi.match(/rgba?\([^)]+\)/g) || []).map(col); };
  els.forEach(e => { const s = cs.get(e); if (text(e)) add(col(s.color), e); add(col(s.backgroundColor), e); grad(e, s).forEach(c => add(c, e));
    if (px(s.borderTopWidth) > 0) add(col(s.borderTopColor), e); });
  const list = Object.values(bk).filter(x => x.n >= 3).sort((a, b) => b.n - a.n);
  return { buckets: list.map(x => ({ c: x.c, n: x.n })), marks: list.slice(0, 4).map(x => mk('b', rect(x.e), x.c)) }; });

// 14 eyebrow labels
run(14, () => {
  const eb = [];
  $$('h1,h2').filter(vis).forEach(h => { let p = h.previousElementSibling;
    while (p && !text(p) && p.children.length === 1) p = p.children[0];
    if (p && cs.get(p) && vis(p) && text(p).length && text(p).length <= 50 && px(cs.get(p).fontSize) <= 15 && !eb.includes(p)) eb.push(p); });
  // 2026-11-13 (Impeccable kicker ban): every label above a heading fails, capsule or not
  return { n: eb.length, bad: eb.length, marks: eb.slice(0, 3).map(e => mk('r', rect(e), '')) }; });

// 15 glowing dots
run(15, () => {
  const d = new Set();
  els.forEach(e => { const s = cs.get(e), r = e.getBoundingClientRect();
    if (r.width <= 14 && r.height <= 14 && r.width >= 4 && Math.abs(r.width - r.height) < 2 && px(s.borderTopLeftRadius) >= r.width / 2 - 1 && col(s.backgroundColor)[3] > 0.3 && (s.boxShadow !== 'none' || s.animationName !== 'none')) d.add(e);
    ['::before', '::after'].forEach(ps => { const p = getComputedStyle(e, ps);
      if (p.content && p.content !== 'none' && p.content !== 'normal') { const w = px(p.width), h = px(p.height);
        if (w >= 4 && w <= 14 && Math.abs(w - h) < 2 && px(p.borderTopLeftRadius) >= w / 2 - 1 && p.boxShadow !== 'none' && col(p.backgroundColor)[3] > .3) d.add(e); } }); });
  // 2026-11-13 (Impeccable dark-glow): any coloured, blurred box- or text-shadow is a glow, not only on dots
  const glowSh = sh => !!sh && sh !== 'none' && sh.split(/,(?![^(]*\))/).some(part => { if (/inset/.test(part)) return false;
    const c = col(part); if (c[3] < .15 || hsl(c)[1] < .25) return false;
    const n = (part.replace(/rgba?\([^)]+\)/, '').match(/-?[\d.]+px/g) || []).map(parseFloat); return (n[2] || 0) >= 12; });
  const g = els.filter(e => !d.has(e) && (glowSh(cs.get(e).boxShadow) || glowSh(cs.get(e).textShadow)));
  const D = [...d];
  return { n: D.length + g.length, dots: D.length, glow: g.length, list: [...new Set(g.map(lab))].slice(0, 4).join(', '),
    marks: D.concat(g).slice(0, 4).map(e => mk('r', rect(e), '')) }; });

// 16 balanced headings
run(16, () => {
  const hs = $$('h1,h2,h3').filter(vis).map(h => { const s = cs.get(h) || getComputedStyle(h); const lines = Math.round(h.getBoundingClientRect().height / lh(s));
    const tw = s.textWrapStyle || s.textWrap || ''; return { h, lines, bal: /balance|pretty/.test(tw) }; });
  const multi = hs.filter(x => x.lines >= 2), bad = multi.filter(x => !x.bal);
  return { multi: multi.length, bad: bad.length, marks: bad.length ? bad.slice(0, 3).map(x => mk('r', rect(x.h), '')) : multi.slice(0, 2).map(x => mk('g', rect(x.h), '')) }; });

// 17 tabular numbers
run(17, () => {
  const nums = els.filter(e => { const t = text(e); if (!t || t.length > 22 || e.closest('a[href^="tel:"]')) return false;
    const d = (t.match(/\d/g) || []).length; return d >= 3 && d / t.replace(/\s/g, '').length >= .5; });
  const bad = nums.filter(e => { const s = cs.get(e); return !(/tabular-nums/.test(s.fontVariantNumeric) || /tnum/.test(s.fontFeatureSettings)); });
  return { total: nums.length, bad: bad.length, marks: bad.length ? bad.slice(0, 4).map(e => mk('r', rect(e), text(e))) : nums.slice(0, 3).map(e => mk('g', rect(e), text(e))) }; });

// 20 labels on icon-only controls + image alt
run(20, () => {
  const named = e => { if (e.getAttribute('aria-label') || e.getAttribute('aria-labelledby') || e.getAttribute('title')) return true;
    if ((e.innerText || '').trim() || (e.textContent || '').trim()) return true; if (e.tagName === 'INPUT' && e.value) return true;
    return !!e.querySelector('img[alt]:not([alt=""]),svg title'); };
  const ctl = $$('a[href],button,[role=button],input[type=submit],input[type=button],summary').filter(vis);
  const icon = ctl.filter(e => !(e.innerText || '').trim() && !(e.tagName === 'INPUT' && e.value));
  const bad = icon.filter(e => !named(e));
  const imgs = $$('img').filter(vis).filter(i => !i.hasAttribute('alt') && i.getAttribute('role') !== 'presentation');
  const all = bad.concat(imgs);
  return { icon: icon.length, bad: bad.length, noalt: imgs.length,
    marks: all.length ? all.slice(0, 5).map(e => mk('r', rect(e), '')) : icon.slice(0, 3).map(e => mk('g', rect(e), '')) }; });

// 21 reduced motion (CSS part is checked in Python)
run(21, () => {
  const animated = els.filter(e => { const s = cs.get(e); return (s.animationName !== 'none' && px(s.animationDuration) > 0) || s.transitionDuration.split(',').some(x => parseFloat(x) > 0); }).length;
  return { animated, marks: firstHead ? [mk('g', rect(firstHead), '')] : [] }; });

// 22 layout animation
run(22, () => {
  const L = /^(height|width|max-height|max-width|min-height|top|left|right|bottom|margin.*|padding.*)$/, bad = [];
  els.forEach(e => { const s = cs.get(e); if (!s.transitionDuration.split(',').some(x => parseFloat(x) > 0)) return;
    if (s.transitionProperty.split(',').map(x => x.trim()).some(x => L.test(x))) bad.push(e); });
  return { n: bad.length, marks: bad.slice(0, 4).map(e => mk('a', rect(e), '')) }; });

// 23 button feedback
run(23, () => {
  const seen = new Set(), btns = $$('button,input[type=submit],[role=button],a[class*=btn],a[class*=button],a[class*=cta],.btn,.button').filter(vis).filter(e => e.getBoundingClientRect().height >= 28 && !seen.has(e) && seen.add(e));
  const dur = e => Math.max(0, ...getComputedStyle(e).transitionDuration.split(',').map(x => /ms/.test(x) ? parseFloat(x) : parseFloat(x) * 1000));
  const rows = btns.map(e => ({ e, d: Math.round(dur(e)) })), good = rows.filter(x => x.d > 0 && x.d <= 300), bad = rows.filter(x => !(x.d > 0 && x.d <= 300));
  const typ = good.length ? pct(good.map(x => x.d), .5) : 0;
  return { total: rows.length, ok: good.length, bad: bad.length, typ,
    marks: bad.slice(0, 3).map(x => mk('r', rect(x.e), x.d + 'ms')).concat(good.slice(0, 2).map(x => mk('g', rect(x.e), x.d + 'ms'))) }; });

// 24 contrast
run(24, () => {
  const lum = ([r, g, b]) => { const f = v => { v /= 255; return v <= .03928 ? v / 12.92 : Math.pow((v + .055) / 1.055, 2.4); }; return .2126 * f(r) + .7152 * f(g) + .0722 * f(b); };
  const cr = (a, b) => { const x = lum(a), y = lum(b); return (Math.max(x, y) + .05) / (Math.min(x, y) + .05); };
  const bgOf = e => { const layers = []; let n = e;
    while (n && n.nodeType === 1) { const s = getComputedStyle(n); if (s.backgroundImage && s.backgroundImage !== 'none') return null;
      const c = col(s.backgroundColor); if (c[3] > 0) { layers.push(c); if (c[3] >= .99) break; } n = n.parentElement; }
    let base = [255, 255, 255]; for (let i = layers.length - 1; i >= 0; i--) { const [r, g, b, a] = layers[i]; base = [r * a + base[0] * (1 - a), g * a + base[1] * (1 - a), b * a + base[2] * (1 - a)]; } return base; };
  const rows = [];
  els.forEach(e => { if (!text(e) || e.matches(':disabled')) return; const r = e.getBoundingClientRect(); if (r.width <= 2 || r.height <= 2) return;
    const s = cs.get(e), bg = bgOf(e); if (!bg) return; const c = col(s.color), a = c[3];
    const fg = [c[0] * a + bg[0] * (1 - a), c[1] * a + bg[1] * (1 - a), c[2] * a + bg[2] * (1 - a)];
    const fs = px(s.fontSize), large = fs >= 24 || (fs >= 18.66 && +s.fontWeight >= 700); rows.push({ e, ratio: cr(fg, bg), thr: large ? 3 : 4.5 }); });
  if (!rows.length) return { err: 'no text' };
  // the background can be a sibling under the text (e.g. an absolutely positioned pill): re-measure the low ones from what is really behind them
  const refine = x => { const e = x.e; e.scrollIntoView({ block: 'center' }); const rg = document.createRange(); rg.selectNodeContents(e); const rr = rg.getBoundingClientRect();
    const cx = rr.left + rr.width / 2, cy = rr.top + rr.height / 2; if (cx < 0 || cy < 0 || cx > innerWidth || cy > innerHeight) return null;
    const layers = []; for (const n of document.elementsFromPoint(cx, cy)) { if (n === e || e.contains(n)) continue; const s = getComputedStyle(n);
      if (s.backgroundImage && s.backgroundImage !== 'none') return null; const c = col(s.backgroundColor); if (c[3] > 0) { layers.push(c); if (c[3] >= .99) break; } }
    let base = [255, 255, 255]; for (let i = layers.length - 1; i >= 0; i--) { const [r, g, b, a] = layers[i]; base = [r * a + base[0] * (1 - a), g * a + base[1] * (1 - a), b * a + base[2] * (1 - a)]; }
    const c = col(getComputedStyle(e).color), a = c[3]; return cr([c[0] * a + base[0] * (1 - a), c[1] * a + base[1] * (1 - a), c[2] * a + base[2] * (1 - a)], base); };
  rows.filter(x => x.ratio < x.thr).slice(0, 60).forEach(x => { const nr = refine(x); if (nr !== null) x.ratio = nr; });
  window.scrollTo(0, 0);
  const bad = rows.filter(x => x.ratio < x.thr).sort((a, b) => a.ratio - b.ratio), low = [...rows].sort((a, b) => a.ratio - b.ratio);
  return { rows: rows.length, bad: bad.length, min: num(low[0].ratio),
    marks: bad.length ? bad.slice(0, 3).map(x => mk('r', rect(x.e), num(x.ratio) + ':1')) : low.slice(0, 2).map(x => mk('g', rect(x.e), num(x.ratio) + ':1')) }; });

// ---- 25-37: rules adopted from Impeccable (pbakaus/impeccable detector + craft floor), 2026-11-13 ----
const shown = e => { const r = e.getBoundingClientRect(), s = getComputedStyle(e); return r.width > 0 && r.height > 0 && s.display !== 'none' && s.visibility !== 'hidden' && !e.closest(SKIP); };
// a "card": a visible surface (fill, gradient, border or shadow) with a rounded corner, big enough to hold content
const isCard = e => { if (!cs.has(e) || e.matches('button,input,select,textarea,img,svg,video,picture,iframe,canvas')) return false;
  const s = cs.get(e), r = e.getBoundingClientRect(); if (r.width < 120 || r.height < 80 || r.width > innerWidth * .9) return false;
  const surf = col(s.backgroundColor)[3] > .02 || (s.backgroundImage !== 'none' && !/url\(/.test(s.backgroundImage)) || px(s.borderTopWidth) > 0 || s.boxShadow !== 'none';
  return surf && px(s.borderTopLeftRadius) >= 8; };

// 25 decorative glass (backdrop-filter blur)
run(25, () => {
  const g = $$('body *').filter(e => { const s = getComputedStyle(e); const b = s.backdropFilter || s.webkitBackdropFilter || 'none'; return /blur/.test(b) && shown(e); });
  return { n: g.length, list: [...new Set(g.map(lab))].slice(0, 4).join(', '), marks: g.slice(0, 4).map(e => mk('r', rect(e), '')) }; });

// 26 overused font (Impeccable: Inter, Roboto, Fraunces, Geist, Plus Jakarta Sans, Space Grotesk)
run(26, () => {
  const OVER = ['inter', 'roboto', 'fraunces', 'geist', 'plus jakarta sans', 'space grotesk'];
  const first = f => (f || '').split(',')[0].replace(/["']/g, '').trim();
  const fams = {}; els.forEach(e => { const t = text(e); if (t) { const f = first(cs.get(e).fontFamily); fams[f] = (fams[f] || 0) + t.length; } });
  const top = Object.entries(fams).sort((a, b) => b[1] - a[1]).slice(0, 3).map(x => x[0]);
  const bad = top.filter(f => OVER.includes(f.toLowerCase()));
  const pick = $$('h1,h2').filter(vis).find(h => bad.includes(first(getComputedStyle(h).fontFamily))) || firstHead;
  return { fonts: top.join(', '), bad: bad.join(', '), marks: pick ? [mk(bad.length ? 'r' : 'g', rect(pick), first(getComputedStyle(pick).fontFamily))] : [] }; });

// 27 crushed letter-spacing (floor -0.04em)
run(27, () => {
  const em = e => { const s = cs.get(e); return px(s.letterSpacing) / Math.max(1, px(s.fontSize)); };
  const bad = els.filter(e => text(e) && px(cs.get(e).fontSize) >= 12 && em(e) < -0.0405).sort((a, b) => em(a) - em(b));
  return { n: bad.length, worst: bad.length ? Math.round(em(bad[0]) * 1000) / 1000 : 0,
    marks: bad.slice(0, 3).map(e => mk('r', rect(e), (Math.round(em(e) * 1000) / 1000) + 'em')) }; });

// 28 icon tile stacked above a heading (the generic AI feature card)
run(28, () => {
  const t = els.filter(e => { const s = cs.get(e), r = e.getBoundingClientRect();
    if (e.matches('a,button') || r.width < 28 || r.width > 80 || Math.abs(r.width - r.height) > 4 || text(e) || !e.querySelector('svg,img,i')) return false;
    const filled = col(s.backgroundColor)[3] > .05 || s.backgroundImage !== 'none' || px(s.borderTopWidth) > 0;
    if (!filled || px(s.borderTopLeftRadius) >= r.width / 2 - 1) return false;
    const h = e.parentElement && e.parentElement.querySelector('h2,h3,h4'); return !!h && h.getBoundingClientRect().top >= r.bottom - 2; });
  return { n: t.length, marks: t.slice(0, 4).map(e => mk('r', rect(e), '')) }; });

// 29 identical card grid (3+ same-size cards in a row as the page structure)
run(29, () => {
  const grids = [];
  els.forEach(g => { const kids = [...g.children].filter(k => cs.has(k)); if (kids.length < 3 || !kids.every(isCard)) return;
    const R = kids.map(k => k.getBoundingClientRect()), ws = R.map(r => r.width), hs = R.map(r => r.height);
    if (Math.max(...ws) - Math.min(...ws) > 4 || Math.max(...hs) - Math.min(...hs) > 8) return;
    if (new Set(R.map(r => Math.round(r.top))).size === kids.length) return;   // a vertical stack (e.g. a photo column), not a row of cards
    grids.push({ g, n: kids.length }); });
  return { n: grids.length, cards: grids.reduce((a, x) => a + x.n, 0), marks: grids.slice(0, 3).map(x => mk('r', rect(x.g), x.n + ' x')) }; });

// 30 card inside a card (a 1-2px "ring" wrapper around an inner card is not nesting)
run(30, () => {
  const cards = els.filter(isCard), set = new Set(cards);
  const nested = cards.filter(c => { const cr = c.getBoundingClientRect(); let p = c.parentElement;
    while (p && p !== document.body) { if (set.has(p)) { const pr = p.getBoundingClientRect(); return !(cr.width >= pr.width - 6 && cr.height >= pr.height - 6); } p = p.parentElement; }
    return false; });
  return { n: nested.length, marks: nested.slice(0, 3).map(e => mk('r', rect(e), '')) }; });

// 31 auto-scrolling marquee (infinite animation on a strip of 3+ items); aria-hidden strips count too
run(31, () => {
  const m = $$('body *').filter(e => { if (!shown(e)) return false; const s = getComputedStyle(e);
    if (s.animationName === 'none' || !/infinite/.test(s.animationIterationCount)) return false;
    const r = e.getBoundingClientRect(); return e.children.length >= 3 && (r.width > 200 || r.height > 200); });
  return { n: m.length, marks: m.slice(0, 3).map(e => mk('r', rect(e.parentElement || e), '')) }; });

// 32 gradient text (background-clip: text)
run(32, () => {
  const g = $$('body *').filter(e => { const s = getComputedStyle(e); return /text/.test(s.webkitBackgroundClip || s.backgroundClip || '') && s.backgroundImage !== 'none' && (e.textContent || '').trim() && shown(e); });
  return { n: g.length, list: g.slice(0, 3).map(e => (e.textContent || '').trim().replace(/\s+/g, ' ').slice(0, 24)).join(', '), marks: g.slice(0, 3).map(e => mk('r', rect(e), '')) }; });

// 33 coloured radial / conic background haze (on the element or its ::before / ::after)
run(33, () => {
  const coloured = b => (b.match(/rgba?\([^)]+\)/g) || []).map(col).some(c => c[3] > .04 && hsl(c)[1] > .15);
  const hits = [];
  $$('body *').forEach(e => { const r = e.getBoundingClientRect(); if (r.width < 120 || r.height < 80 || !shown(e)) return;
    for (const ps of [null, '::before', '::after']) { const s = getComputedStyle(e, ps); if (ps && (!s.content || s.content === 'none' || s.display === 'none')) continue;
      const b = s.backgroundImage || ''; if (/(radial|conic)-gradient/.test(b) && !/url\(/.test(b) && coloured(b)) { hits.push(e); break; } } });
  return { n: hits.length, marks: hits.slice(0, 3).map(e => mk('r', rect(e), '')) }; });

// 34 heading rhythm: more space above a heading than below it
run(34, () => {
  const rows = [];
  $$('h2,h3').filter(vis).forEach(h => { const p = h.previousElementSibling, n = h.nextElementSibling; if (!p || !n || !vis(p) || !vis(n)) return;
    const r = h.getBoundingClientRect(), a = r.top - p.getBoundingClientRect().bottom, b = n.getBoundingClientRect().top - r.bottom;
    if (a < 0 || b < 0 || a > 240) return; rows.push({ h, a: Math.round(a), b: Math.round(b) }); });
  const bad = rows.filter(x => x.a <= x.b), show = bad.length ? bad : rows;
  return { total: rows.length, bad: bad.length, ex: bad[0] ? bad[0].a + '/' + bad[0].b : '',
    marks: show.slice(0, 3).map(x => mk(bad.length ? 'r' : 'g', rect(x.h), x.a + 'px / ' + x.b + 'px')) }; });

// 35 one word alone on the last line of body text (straggler)
run(35, () => {
  const bad = []; let total = 0;
  $$('p,li').filter(vis).forEach(p => { const t = (p.innerText || '').trim(); if (t.split(/\s+/).length < 6) return;
    const tw = document.createTreeWalker(p, NodeFilter.SHOW_TEXT); let last = null; while (tw.nextNode()) if (tw.currentNode.textContent.trim()) last = tw.currentNode;
    if (!last) return; const s = last.textContent.replace(/\s+$/, ''); const i = s.lastIndexOf(' ') + 1; if (i <= 1) return;
    const j = s.lastIndexOf(' ', i - 2) + 1; total++;
    if (/\u00a0/.test(s.slice(i))) return;   // last two words already tied with a non-breaking space: never a one-word line
    const w = document.createRange(); w.setStart(last, i); w.setEnd(last, s.length);
    const pw = document.createRange(); pw.setStart(last, j); pw.setEnd(last, i - 1);
    if (Math.round(pw.getBoundingClientRect().top) < Math.round(w.getBoundingClientRect().top) - 2) bad.push(p); });
  return { total, n: bad.length, marks: bad.slice(0, 3).map(e => mk('r', rect(e), '')) }; });

// 36 themed text selection: the CSS part (::selection) is checked in Python
run(36, () => ({ marks: firstHead ? [mk('b', rect(firstHead), '')] : [] }));

// 37 hero-metric number: a bare number set at display size (64px+)
run(37, () => {
  const big = els.filter(e => { const t = (e.innerText || '').trim(); return t && /\d/.test(t) && /^[\d\s.,+%×x\/:$€₴-]{1,10}$/.test(t) && px(cs.get(e).fontSize) >= 64; });
  return { n: big.length, ex: big[0] ? (big[0].innerText || '').trim() + ' (' + Math.round(px(cs.get(big[0]).fontSize)) + 'px)' : '',
    marks: big.slice(0, 3).map(e => mk('r', rect(e), Math.round(px(cs.get(e).fontSize)) + 'px')) }; });

// ---- 38-55: more Impeccable detector rules + craft-floor checks (groups 1 and 2), 2026-11-13 ----
const effOpacity = e => { let o = 1, n = e; while (n && n.nodeType === 1) { o *= +getComputedStyle(n).opacity; n = n.parentElement; } return o; };
const bgBehind = e => { let n = e; while (n && n.nodeType === 1) { const b = col(getComputedStyle(n).backgroundColor); if (b[3] > .5) return b; n = n.parentElement; } return null; };

// 38 line height of body text >= 1.3
run(38, () => {
  const bad = els.filter(e => { const t = text(e), s = cs.get(e); if (t.length < 40 || px(s.fontSize) >= 24) return false;
    const L = lh(s); return e.getBoundingClientRect().height >= L * 1.8 && L / px(s.fontSize) < 1.3; });
  const ratio = e => Math.round(lh(cs.get(e)) / px(cs.get(e).fontSize) * 100) / 100;
  return { n: bad.length, worst: bad.length ? Math.min(...bad.map(ratio)) : 0, marks: bad.slice(0, 3).map(e => mk('r', rect(e), ratio(e))) }; });

// 39 text setting: no justified text, no long ALL-CAPS passages, no wide tracking on body text
run(39, () => {
  const just = [], caps = [], wide = [];
  els.forEach(e => { const t = text(e); if (t.length <= 40) return; const s = cs.get(e);
    if (s.textAlign === 'justify') just.push(e);
    if ((s.textTransform === 'uppercase' || (t === t.toUpperCase() && /[A-ZА-ЯІЇЄҐĄĆĘŁŃÓŚŹŻ]{5}/.test(t)))) caps.push(e);
    else if (px(s.letterSpacing) / Math.max(1, px(s.fontSize)) > 0.05) wide.push(e); });
  const all = just.concat(caps, wide);
  return { n: all.length, just: just.length, caps: caps.length, wide: wide.length, marks: all.slice(0, 3).map(e => mk('r', rect(e), '')) }; });

// 40 heading levels in order (one h1, no jumps like h2 -> h4)
run(40, () => {
  const hs = $$('h1,h2,h3,h4,h5,h6').filter(shown); let prev = 0; const skips = [];
  hs.forEach(h => { const l = +h.tagName[1]; if (prev && l > prev + 1) skips.push({ h, t: 'h' + prev + ' > h' + l }); prev = l; });
  const h1 = hs.filter(h => h.tagName === 'H1').length;
  return { total: hs.length, h1, n: skips.length, ex: skips[0] ? skips[0].t : '',
    marks: skips.length ? skips.slice(0, 3).map(x => mk('r', rect(x.h), x.t)) : hs.slice(0, 1).map(h => mk('g', rect(h), h.tagName.toLowerCase())) }; });

// 41 grey text on a coloured background
run(41, () => {
  const bad = els.filter(e => { if (!text(e)) return false; const [, s, l] = hsl(col(cs.get(e).color)); if (s > .12 || l < .25 || l > .85) return false;
    const bg = bgBehind(e); if (!bg) return false; const [, bs, bl] = hsl(bg); return bs > .35 && bl > .15 && bl < .85; });
  return { n: bad.length, marks: bad.slice(0, 3).map(e => mk('r', rect(e), '')) }; });

// 42 cramped padding: text too close to the edge of its own visible box
run(42, () => {
  const bad = els.filter(e => { if (!text(e) || e.matches('input,select,textarea') || /^inline$/.test(cs.get(e).display)) return false; const s = cs.get(e);
    if (!(col(s.backgroundColor)[3] > .1 || px(s.borderTopWidth) > 0 || px(s.borderLeftWidth) > 0)) return false;
    const r = e.getBoundingClientRect(); if (r.height > 200 || r.width < 24) return false; const t = trect(e); if (!t.width) return false;
    const hz = Math.min(t.left - r.left, r.right - t.right), vt = Math.min(t.top - r.top, r.bottom - t.bottom); return hz < 8 || vt < 3; });
  return { n: bad.length, marks: bad.slice(0, 3).map(e => mk('r', rect(e), '')) }; });

// 43 content still invisible after every reveal had its chance (failed scroll-reveal)
run(43, () => {
  let total = 0, hidden = 0; const hid = new Set();
  const tw = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  while (tw.nextNode()) { const n = tw.currentNode, t = n.textContent.trim(); if (t.length < 2) continue; const e = n.parentElement;
    if (!e || /^(SCRIPT|STYLE|NOSCRIPT|TEMPLATE|OPTION)$/.test(e.tagName) || e.closest(SKIP) || e.closest('[aria-hidden="true"],[hidden],details:not([open])')) continue;
    const r = e.getBoundingClientRect(); if (r.width < 1 || r.height < 1) continue; total += t.length;
    if (effOpacity(e) < .05 || getComputedStyle(e).visibility === 'hidden') { hidden += t.length; hid.add(e); } }
  const H = [...hid].filter(e => !e.parentElement || !hid.has(e.parentElement));
  return { pct: total ? Math.round(hidden / total * 1000) / 10 : 0, marks: H.slice(0, 3).map(e => mk('r', rect(e), '')) }; });

// 45 hero columns: one opening column must not run far past the fold while its sibling fits
run(45, () => {
  const cand = els.filter(e => { const r = e.getBoundingClientRect(); return r.top + scrollY < innerHeight * .6 && [...e.children].filter(k => cs.has(k)).length >= 2; });
  for (const g of cand) { const kids = [...g.children].filter(k => cs.has(k) && k.getBoundingClientRect().width > innerWidth * .25);
    if (kids.length < 2) continue; const R = kids.map(k => k.getBoundingClientRect()); if (Math.abs(R[0].top - R[1].top) > 60) continue;
    const fold = innerHeight - scrollY, b = R.map(r => r.bottom + scrollY);
    const long = b.findIndex(x => x > innerHeight * 1.25), short = b.findIndex(x => x <= innerHeight);
    if (long >= 0 && short >= 0) return { bad: 1, ex: Math.round(b[long]) + 'px', marks: [mk('r', rect(kids[long]), Math.round(b[long]) + 'px'), mk('g', rect(kids[short]), '')] };
    return { bad: 0, ex: '', marks: [mk('g', rect(g), '')] }; }
  return { bad: 0, na: 1, ex: '', marks: [] }; });

// 46 sideways scroll rows: first card not glued to the edge; pop-ups not cut by an overflow container (phone)
run(46, () => {
  const flush = [];
  $$('body *').filter(shown).forEach(s => { const st = getComputedStyle(s); if (!/(auto|scroll)/.test(st.overflowX) || s.scrollWidth <= s.clientWidth + 4) return;
    const k = [...s.children].find(c => c.getBoundingClientRect().width > 40); if (!k) return; const kr = k.getBoundingClientRect(), sr = s.getBoundingClientRect();
    if (px(getComputedStyle(k).borderTopLeftRadius) >= 8 && kr.left - sr.left < 2 && px(st.paddingLeft) < 2 && px(st.scrollPaddingLeft || 0) < 2) flush.push(s); });
  const clipped = $$('[role=tooltip],[role=menu],[role=listbox],.tooltip,.dropdown,.popover').filter(shown).filter(p => { const pr = p.getBoundingClientRect(); let n = p.parentElement;
    while (n && n !== document.body) { const s = getComputedStyle(n); if (/(hidden|clip)/.test(s.overflow + s.overflowX + s.overflowY)) { const r = n.getBoundingClientRect();
      return pr.left < r.left - 1 || pr.right > r.right + 1 || pr.top < r.top - 1 || pr.bottom > r.bottom + 1; } n = n.parentElement; } return false; });
  const all = flush.concat(clipped);
  return { n: all.length, flush: flush.length, clipped: clipped.length, marks: all.slice(0, 3).map(e => mk('r', rect(e), '')) }; });

// 47 calm motion: no bounce / elastic easing, no pulsing status dots
run(47, () => {
  const over = f => (f.match(/cubic-bezier\(([^)]+)\)/g) || []).some(c => { const v = c.slice(13, -1).split(',').map(parseFloat); return v[1] < -0.05 || v[1] > 1.05 || v[3] < -0.05 || v[3] > 1.05; });
  const bounce = $$('body *').filter(shown).filter(e => { const s = getComputedStyle(e); return over(s.transitionTimingFunction + s.animationTimingFunction) || /bounce|elastic|wobble|jello|rubber/i.test(s.animationName); });
  const pulse = $$('body *').filter(shown).filter(e => { const s = getComputedStyle(e), r = e.getBoundingClientRect();
    return r.width <= 16 && r.width >= 4 && Math.abs(r.width - r.height) < 2 && s.animationName !== 'none' && /infinite/.test(s.animationIterationCount); });
  const all = bounce.concat(pulse);
  return { n: all.length, bounce: bounce.length, pulse: pulse.length, marks: all.slice(0, 3).map(e => mk('r', rect(e), '')) }; });

// 48 decorative grid-line / stripe backgrounds
run(48, () => {
  const hits = [];
  $$('body *').forEach(e => { const r = e.getBoundingClientRect(); if (r.width < 120 || r.height < 80 || !shown(e)) return;
    for (const ps of [null, '::before', '::after']) { const s = getComputedStyle(e, ps); if (ps && (!s.content || s.content === 'none' || s.display === 'none')) continue;
      const b = s.backgroundImage || '', sizes = (s.backgroundSize.match(/[\d.]+px/g) || []).map(parseFloat);
      if (/repeating-(linear|radial)-gradient/.test(b) || ((b.match(/linear-gradient/g) || []).length >= 2 && sizes.length && Math.max(...sizes) <= 120)) { hits.push(e); break; } } });
  return { n: hits.length, marks: hits.slice(0, 3).map(e => mk('r', rect(e), '')) }; });

// 49 palette is not the AI default: purple/violet gradients, cyan text on dark, cream/beige page background
run(49, () => {
  const purple = $$('body *').filter(shown).filter(e => { const b = getComputedStyle(e).backgroundImage || ''; return /gradient/.test(b) && (b.match(/rgba?\([^)]+\)/g) || []).map(col).some(c => { const [h, s, l] = hsl(c); return c[3] > .3 && h >= 255 && h <= 300 && s > .4 && l > .2 && l < .8; }); });
  const cyan = els.filter(e => { if (!text(e)) return false; const [h, s, l] = hsl(col(cs.get(e).color)); if (!(h >= 170 && h <= 200 && s > .5 && l > .45)) return false; const bg = bgBehind(e); return bg && hsl(bg)[2] < .2; });
  const pb = col(getComputedStyle(document.body).backgroundColor)[3] > .5 ? col(getComputedStyle(document.body).backgroundColor) : col(getComputedStyle(document.documentElement).backgroundColor);
  const [ph, ps, pl] = hsl(pb), cream = pb[3] > .5 && ph >= 28 && ph <= 60 && ps >= .2 && pl >= .86 && pl <= .97;
  const all = purple.concat(cyan);
  return { n: purple.length + cyan.length + (cream ? 1 : 0), purple: purple.length, cyan: cyan.length, cream: cream ? hex(pb) : '',
    marks: all.length ? all.slice(0, 3).map(e => mk('r', rect(e), '')) : (cream && firstHead ? [mk('r', rect(firstHead), hex(pb))] : []) }; });

// 50 no small numbered section labels (01 / 02 / 03 next to section headings)
run(50, () => {
  const lab = [];
  $$('h2,h3').filter(vis).forEach(h => { const near = [h.previousElementSibling, h.parentElement && h.parentElement.previousElementSibling, h.firstElementChild].filter(Boolean);
    const hit = near.find(n => { const t = (n.innerText || '').trim(); return /^(0?\d{1,2}|[IVX]{1,4})(\s*[.\/)\-]\s*(0?\d{1,2})?)?$/.test(t) && px(getComputedStyle(n).fontSize) <= 20; });
    if (hit) lab.push(hit); });
  return { n: lab.length >= 2 ? lab.length : 0, marks: lab.length >= 2 ? lab.slice(0, 3).map(e => mk('r', rect(e), (e.innerText || '').trim())) : [] }; });

// 51 headline not oversized: a full-sentence h1 at display size that eats the first screen
run(51, () => {
  const h = $$('h1').filter(vis)[0]; if (!h) return { na: 1, marks: [] }; const s = getComputedStyle(h), r = h.getBoundingClientRect();
  const words = (h.innerText || '').trim().split(/\s+/).length, fs = px(s.fontSize), share = r.height / innerHeight;
  const bad = (words >= 5 && fs >= 72) || share > .5;
  return { bad: bad ? 1 : 0, fs: Math.round(fs), words, share: Math.round(share * 100), marks: [mk(bad ? 'r' : 'g', rect(h), Math.round(fs) + 'px')] }; });

// 52 copy without AI cliches (UA / RU / PL / EN): buzzwords, "Not X. Just Y." cadence, "theatre" framing
run(52, () => {
  const BUZZ = [/\bstreamlin\w*/gi, /\bempower\w*/gi, /\bsupercharg\w*/gi, /\bworld[- ]class\b/gi, /\benterprise[- ]grade\b/gi, /\bnext[- ]gen(eration)?\b/gi, /\bcutting[- ]edge\b/gi,
    /\bseamless(ly)?\b/gi, /\brevolutionar\w*/gi, /\bgame[- ]chang\w*/gi, /\bunleash\w*/gi, /\bbest[- ]in[- ]class\b/gi, /\bstate[- ]of[- ]the[- ]art\b/gi, /\bsynerg\w*/gi,
    /інноваційн\S*/gi, /революційн\S*/gi, /світового рівня/gi, /нового покоління/gi, /новітнього покоління/gi, /передов\S* технолог\S*/gi, /безшовн\S*/gi, /на новий рівень/gi, /неперевершен\S*/gi,
    /инновационн\S*/gi, /революционн\S*/gi, /мирового уровня/gi, /нового поколения/gi, /на новый уровень/gi, /бесшовн\S*/gi,
    /innowacyjn\S*/gi, /rewolucyjn\S*/gi, /światowej klasy/gi, /nowej generacji/gi, /najnowszej generacji/gi, /przełomow\S*/gi, /na wyższy poziom/gi, /najwyższej jakości/gi];
  const APH = [/(^|[.!?]\s)(Not|Не|Nie)\s[^.!?\n]{1,30}[.!?]\s+(Just|Only|A|An|А|Лише|Тільки|Просто|Tylko|Po prostu)?\s?[^.!?\n]{1,30}[.!?]/g,
               /[.!?]\s+(No|Без|Bez)\s[^.!?\n]{1,25}[.!?]/g,
               /(^|[.!?\n]\s*)[A-ZА-ЯІЇЄҐ][^,.!?\n]{2,24},\s+(meet|знайомтесь|познакомьтесь|poznaj)\s[^.!?\n]{2,24}[.!?]/g];
  const THEA = [/\btheat(er|re)\b/gi, /\bтеатр\S*/gi, /\bteatr\S*/gi];
  const body = document.body.innerText || '', hits = [];
  BUZZ.forEach(r => (body.match(r) || []).forEach(m => hits.push(m.toLowerCase())));
  const aph = APH.reduce((a, r) => a + (body.match(r) || []).length, 0), thea = THEA.reduce((a, r) => a + (body.match(r) || []).length, 0);
  const words = [...new Set(hits)];
  const find = w => { const tw = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT); while (tw.nextNode()) if (tw.currentNode.textContent.toLowerCase().includes(w) && tw.currentNode.parentElement && vis(tw.currentNode.parentElement)) return tw.currentNode.parentElement; return null; };
  const marks = words.slice(0, 3).map(w => [w, find(w)]).filter(x => x[1]).map(([w, e]) => mk('r', rect(e), w));
  return { buzz: hits.length, words: words.slice(0, 5).join(', '), aph, thea, marks }; });

// 53 interface states + error messages (forms facts; the CSS part is checked in Python)
run(53, () => {
  const forms = $$('form').filter(shown), fields = $$('input:not([type=hidden]):not([type=submit]):not([type=button]),select,textarea').filter(shown);
  const req = fields.filter(f => f.required || f.getAttribute('aria-required') === 'true');
  const explained = req.filter(f => f.getAttribute('aria-describedby') || f.getAttribute('aria-errormessage') ||
    (f.closest('label,.field,.form-group,.form-field,div') || f.parentElement).querySelector('[class*=err],[class*=invalid],[class*=hint],[role=alert]'));
  return { forms: forms.length, req: req.length, explained: explained.length,
    marks: forms.length ? [mk(req.length && explained.length < req.length ? 'r' : 'b', rect(forms[0]), '')] : (firstHead ? [mk('b', rect(firstHead), '')] : []) }; });

// 54 browser parts styled: scrollbar (CSS, checked in Python) and the text caret in inputs
run(54, () => {
  const inputs = $$('input:not([type=hidden]):not([type=checkbox]):not([type=radio]):not([type=submit]),textarea').filter(shown);
  const caret = inputs.filter(i => !/auto/.test(getComputedStyle(i).caretColor || 'auto'));
  const box = inputs.length ? (inputs[0].closest('form') || inputs[0].parentElement || inputs[0]) : null;   // the whole form crops reliably
  return { inputs: inputs.length, caret: caret.length, marks: box ? [mk(caret.length ? 'g' : 'r', rect(box), '')] : [] }; });

// 55 one authored motion moment: the same scroll-reveal entrance repeated on many sections
run(55, () => {
  const RE = /^(rv|rise|reveal|fade|fade-?up|fade-?in|aos|animate|animated|wow|sr|in-?view|js-reveal|scroll-reveal)$/i;
  const secs = $$('section').filter(s => !s.parentElement.closest('section') && shown(s)); const per = {};
  secs.forEach(s => { const toks = new Set(); s.querySelectorAll('[class],[data-aos],[data-animate],[data-reveal],[data-sr]').forEach(e => {
      if (e.hasAttribute('data-aos')) toks.add('data-aos'); if (e.hasAttribute('data-reveal') || e.hasAttribute('data-sr') || e.hasAttribute('data-animate')) toks.add('data-reveal');
      (typeof e.className === 'string' ? e.className.split(/\s+/) : []).forEach(c => { if (RE.test(c)) toks.add(c); }); });
    toks.forEach(t => (per[t] = per[t] || []).push(s)); });
  const top = Object.entries(per).sort((a, b) => b[1].length - a[1].length)[0];
  return { sections: secs.length, tok: top ? top[0] : '', n: top ? top[1].length : 0, marks: top && top[1].length >= 4 ? top[1].slice(0, 3).map(s => mk('r', rect(s), '.' + top[0])) : [] }; });

// ---- 56-63: anti-AI-look craft checks (2026-11-13) ----
// 56 no random italic words inside headings (the italic-serif emphasis tell)
run(56, () => {
  const it = $$('h1,h2,h3').filter(vis).flatMap(h => [...h.querySelectorAll('em,i,span')].filter(s => getComputedStyle(s).fontStyle === 'italic' && getComputedStyle(h).fontStyle !== 'italic'));
  return { n: it.length, marks: it.slice(0, 3).map(e => mk('r', rect(e), '')) }; });

// 57 monospace only for code / data, not as a 'technical' costume in headings and copy
run(57, () => {
  const mono = els.filter(e => { const t = text(e); if (!t || e.closest('code,pre,kbd,samp,table,input,textarea')) return false;
    return /mono|courier|consolas|menlo|monaco|sf mono|jetbrains|fira code|ibm plex mono|space mono/i.test(cs.get(e).fontFamily.split(',')[0]) && !/^[\d\s.,:$€₴%+-]+$/.test(t); });
  return { n: mono.length, marks: mono.slice(0, 3).map(e => mk('r', rect(e), '')) }; });

// 58 one design system for buttons: a few consistent variants, not many ad-hoc styles
run(58, () => {
  const btns = $$('button,input[type=submit],a[class*=btn],a[class*=button],.btn,.button').filter(vis).filter(e => e.getBoundingClientRect().height >= 28);
  const sig = e => { const s = getComputedStyle(e); return [Math.round(px(s.borderTopLeftRadius) >= e.getBoundingClientRect().height / 2 - 1 ? 999 : px(s.borderTopLeftRadius)), s.fontWeight, Math.round(px(s.fontSize)), px(s.borderTopWidth) > 0 ? 'b' : '-'].join('|'); };
  const groups = {}; btns.forEach(e => { const k = sig(e); (groups[k] = groups[k] || []).push(e); });
  const keys = Object.keys(groups);
  return { total: btns.length, k: keys.length, marks: keys.slice(0, 5).map(k => mk(keys.length > 4 ? 'r' : 'g', rect(groups[k][0]), '')) }; });

// 59 show the actual product / place: a real photo, screenshot or video on the first screen
run(59, () => {
  const media = $$('img,video,picture,canvas').filter(shown).filter(e => { const r = e.getBoundingClientRect(); return r.top + scrollY < innerHeight && r.width >= 200 && r.height >= 120; });
  const bgimg = $$('body *').filter(e => { const r = e.getBoundingClientRect(); return r.top + scrollY < innerHeight && r.width >= 300 && r.height >= 200 && /url\(/.test(getComputedStyle(e).backgroundImage); });
  const any = media.concat(bgimg);
  return { n: any.length, marks: any.length ? [mk('g', rect(any[0]), '')] : (firstHead ? [mk('r', rect(firstHead), '')] : []) }; });

// 60 spacing rhythm: not one gap value everywhere (group related things tight, separate groups wide)
run(60, () => {
  const vals = {}; let tot = 0;
  els.forEach(e => { const s = cs.get(e); [s.rowGap, s.columnGap, s.marginTop, s.marginBottom].forEach(v => { const x = Math.round(px(v)); if (x >= 4 && x <= 200) { vals[x] = (vals[x] || 0) + 1; tot++; } }); });
  const top = Object.entries(vals).sort((a, b) => b[1] - a[1]); const share = tot ? top[0][1] / tot : 0;
  return { tot, top: top[0] ? top[0][0] : 0, share: Math.round(share * 100), distinct: top.length, marks: firstHead ? [mk(share > .6 ? 'r' : 'g', rect(firstHead), '')] : [] }; });

// 61 one clear primary CTA per group: two neighbouring filled buttons with the same weight compete
run(61, () => {
  const filled = e => { const s = getComputedStyle(e), c = col(s.backgroundColor); return c[3] > .6 && hsl(c)[1] > .25 || /gradient/.test(s.backgroundImage); };
  const btns = $$('button,input[type=submit],a[class*=btn],a[class*=button],.btn,.button').filter(vis).filter(e => e.getBoundingClientRect().height >= 36);
  const bad = [];
  btns.forEach((a, i) => btns.slice(i + 1).forEach(b => { if (a.parentElement !== b.parentElement || !filled(a) || !filled(b)) return;
    const sa = getComputedStyle(a), sb = getComputedStyle(b); if (sa.backgroundColor === sb.backgroundColor && sa.backgroundImage === sb.backgroundImage) bad.push(a.parentElement); }));
  const B = [...new Set(bad)];
  return { n: B.length, marks: B.slice(0, 3).map(e => mk('r', rect(e), '')) }; });

// 62 consistent icon style: one stroke width and line-vs-filled style for inline SVG icons
run(62, () => {
  const svgs = $$('svg').filter(shown).filter(s => { const r = s.getBoundingClientRect(); return r.width >= 12 && r.width <= 48; });
  const style = s => { const st = s.getAttribute('stroke') || getComputedStyle(s).stroke, f = s.getAttribute('fill') || '';
    return (st && st !== 'none' && f === 'none') ? 'line' + (s.getAttribute('stroke-width') || getComputedStyle(s).strokeWidth || '') : 'fill'; };
  const kinds = {}; svgs.forEach(s => { const k = style(s); (kinds[k] = kinds[k] || []).push(s); });
  const keys = Object.keys(kinds), lineW = keys.filter(k => k.startsWith('line'));
  const mixed = keys.includes('fill') && lineW.length && kinds.fill.length >= 2;
  return { total: svgs.length, kinds: keys.map(k => k.replace('line', 'line ') + ' x' + kinds[k].length).join(', '), bad: (lineW.length > 2 || mixed) ? 1 : 0,
    marks: keys.slice(0, 4).map(k => mk((lineW.length > 2 || mixed) ? 'r' : 'g', rect(kinds[k][0]), k.replace('line', 'line '))) }; });

// 63 play icons optically centred (a triangle needs a small shift to the right inside its circle)
run(63, () => {
  const plays = $$('button,a,[role=button],div,span').filter(vis).filter(e => /play/i.test((e.getAttribute('aria-label') || '') + ' ' + (typeof e.className === 'string' ? e.className : '')) && e.querySelector('svg'));
  const rows = plays.map(e => { const g = e.querySelector('svg path,svg polygon') || e.querySelector('svg'); const br = e.getBoundingClientRect(), gr = g.getBoundingClientRect();
    return { e, dx: Math.round(((gr.left + gr.width / 2) - (br.left + br.width / 2)) * 10) / 10, w: gr.width }; }).filter(x => x.w > 0);
  const bad = rows.filter(x => x.dx < x.w * .04);
  return { total: rows.length, n: bad.length, marks: (bad.length ? bad : rows).slice(0, 2).map(x => mk(bad.length ? 'r' : 'g', rect(x.e), x.dx + 'px')) }; });

// 44 text hidden under another element (async: scrolls the page and asks the browser what is on top)
try {
  const items = els.filter(e => text(e).length >= 2 && !e.closest('header,nav,[class*=hdr],[class*=header]')).slice(0, 600), bad = [];
  const H = document.documentElement.scrollHeight;
  for (let y = 0; y < H; y += Math.round(innerHeight * .8)) {
    window.scrollTo(0, y); await new Promise(r => setTimeout(r, 40));
    items.forEach(e => { if (bad.includes(e)) return; const t = trect(e); const cx = t.left + t.width / 2, cy = t.top + t.height / 2;
      if (!t.width || cx < 0 || cy < 80 || cx > innerWidth || cy > innerHeight - 4) return;
      // text scrolled or clipped out of its own overflow box is not "covered" (marquees, carousels, collapsed panels)
      let q = e.parentElement; while (q && q !== document.body) { const qs = getComputedStyle(q); if (/(hidden|clip|auto|scroll)/.test(qs.overflow + qs.overflowX + qs.overflowY)) {
        const qr = q.getBoundingClientRect(); if (cx < qr.left || cx > qr.right || cy < qr.top || cy > qr.bottom) return; }
        if (getComputedStyle(q).animationName !== 'none') return; q = q.parentElement; }
      const top = document.elementFromPoint(cx, cy); if (!top || top === e || e.contains(top) || top.contains(e)) return;
      let n = top; while (n && n !== document.body) { const s = getComputedStyle(n); if (s.position === 'fixed' || s.position === 'sticky') return; n = n.parentElement; }
      const s = getComputedStyle(top); if (col(s.backgroundColor)[3] < .5 && !/^(IMG|VIDEO|CANVAS|IFRAME)$/.test(top.tagName)) return;
      bad.push(e); }); }
  window.scrollTo(0, 0);
  out[44] = { n: bad.length, marks: bad.slice(0, 3).map(e => mk('r', rect(e), '')) };
} catch (e) { out[44] = { err: String(e) }; }

// context shot for points that pass with nothing to mark, so every card shows the page (2026-11-13: "never skip a point")
const CONTEXT = { 14: 'h2,h1', 25: 'h1', 27: 'h1,h2', 33: 'section', 38: 'p', 39: 'p', 40: 'h1,h2', 41: 'p', 42: '.btn,button,a[class*=btn]', 43: 'h1',
  44: 'h1', 45: '.btn,button', 46: 'section', 47: '.btn,button', 48: 'h2', 49: 'h1', 50: 'h2,h1', 52: 'h1', 53: 'section', 54: 'form,input,h1',
  56: 'h1', 57: 'p', 58: '.btn,button', 59: 'h1,img', 60: 'h2', 61: '.btn,button', 62: 'svg', 21: 'section', 22: 'h1', 23: '.btn,button' };
Object.entries(CONTEXT).forEach(([n, sel]) => { const o = out[n]; if (!o || o.err || (o.marks && o.marks.length)) return;
  const e = $$(sel).find(x => shown(x) && x.getBoundingClientRect().width > 20); if (e) o.marks = [mk('g', rect(e), '')]; });

// page-level facts for the CSS-driven points
const metaVp = (document.querySelector('meta[name=viewport]') || {}).content || '';
const sheets = $$('link[rel=stylesheet]').map(l => l.href);
const inline = $$('style').map(s => s.textContent).join('\n');
return { out, metaVp, sheets, inline };
}
"""

BARS_JS = r"""
() => {
const SKIP = '[class*="cky"],[id*="cky"],[class*="cookie"],[id*="cookie"],[class*="consent"],[id*="consent"],[id*="onetrust"],[id*="CookieBanner"],[id*="usercentrics"]';
const px = v => parseFloat(v) || 0;
// fixed to the bottom edge; NOT required to be visible now (such bars are often slid off-screen with a transform until the user scrolls)
const bars = [...document.querySelectorAll('body *')].filter(e => { const s = getComputedStyle(e);
  if (s.position !== 'fixed' || s.bottom !== '0px' || s.display === 'none') return false; const r = e.getBoundingClientRect();
  return r.width >= innerWidth * .8 && r.height > 20 && r.height < 220 && !e.closest(SKIP); });
return bars.map(e => { const r = e.getBoundingClientRect(); return { r: [0, Math.round(innerHeight + scrollY - r.height), Math.round(r.width), Math.round(r.height)], pb: px(getComputedStyle(e).paddingBottom) }; });
}
"""

FOCUS_ASSIGN_JS = r"""
() => {
const SKIP = '[class*="cky"],[id*="cky"],[class*="cookie"],[id*="cookie"],[class*="consent"],[id*="consent"],[id*="onetrust"],[id*="usercentrics"]';
const sig = e => { const s = getComputedStyle(e); return [s.outlineStyle, s.outlineWidth, s.outlineColor, s.boxShadow, s.borderTopColor, s.backgroundColor, s.textDecorationLine, s.color].join('|'); };
const out = []; let i = 0;
document.querySelectorAll('a[href],button,input:not([type=hidden]),select,textarea,summary,[tabindex]:not([tabindex="-1"])').forEach(e => {
  const r = e.getBoundingClientRect(), s = getComputedStyle(e);
  if (r.width < 4 || r.height < 4 || s.visibility === 'hidden' || s.display === 'none' || e.closest(SKIP) || r.right < 0 || r.left > innerWidth) return;
  e.setAttribute('data-glid', i); out.push({ id: i, base: sig(e) }); i++; });
window.__sig = sig; return out;
}
"""

FOCUS_READ_JS = r"""
() => { const e = document.activeElement; if (!e || e.dataset.glid === undefined) return null;
  const s = getComputedStyle(e), r = e.getBoundingClientRect();
  return { id: +e.dataset.glid, sig: window.__sig(e), os: s.outlineStyle, ow: parseFloat(s.outlineWidth) || 0,
    r: [Math.round(r.left + scrollX), Math.round(r.top + scrollY), Math.round(r.width), Math.round(r.height)] }; }
"""

OVERLAY_JS = r"""
(opt) => {
const C = { g: '#1fbf6b', r: '#ff2d87', b: '#2e8bff', a: '#f0b44c' };
opt.marks.forEach(m => { const c = C[m.c] || C.b, d = document.createElement('div'), [x, y, w, h] = m.r;
  Object.assign(d.style, { position: 'absolute', left: x + 'px', top: y + 'px', width: w + 'px', height: h + 'px',
    border: m.f ? 'none' : '2px solid ' + c, background: m.f ? c + '66' : 'transparent', zIndex: 2147483000, pointerEvents: 'none', boxSizing: 'border-box', borderRadius: '4px' });
  if (m.label) { const t = document.createElement('span'); t.textContent = m.label;
    Object.assign(t.style, { position: 'absolute', whiteSpace: 'nowrap', background: c, color: '#fff', padding: '5px 8px', borderRadius: '6px',
      font: '600 ' + opt.fs + 'px/1 -apple-system,Segoe UI,Arial,sans-serif', left: '0', top: -(opt.fs + 14) + 'px' });
    if (m.f || h < 8) Object.assign(t.style, { left: '50%', top: '50%', transform: 'translate(-50%,-50%)' });
    d.appendChild(t); }
  document.body.appendChild(d); });
}
"""

# ---------------------------------------------------------------------------------------------
# Static data: sources, priorities, contexts, texts
# ---------------------------------------------------------------------------------------------
SRC = {
    "carbon": ("IBM Carbon Design System, Spacing", "https://carbondesignsystem.com/elements/spacing/overview/"),
    "hig_layout": ("Apple Human Interface Guidelines, Layout", "https://developer.apple.com/design/human-interface-guidelines/layout"),
    "m3_divider": ("Material Design 3, Divider specs", "https://m3.material.io/components/divider/specs"),
    "wwdc_356": ("Apple WWDC25, Get to know the new design system", "https://developer.apple.com/videos/play/wwdc2025/356/"),
    "m3_shape": ("Material Design 3, Corner radius scale", "https://m3.material.io/styles/shape/corner-radius-scale"),
    "hig_type": ("Apple Human Interface Guidelines, Typography", "https://developer.apple.com/design/human-interface-guidelines/typography"),
    "wcag_148": ("WCAG 2.2, 1.4.8 Visual Presentation", "https://www.w3.org/WAI/WCAG22/Understanding/visual-presentation.html"),
    "hig_a11y": ("Apple Human Interface Guidelines, Accessibility", "https://developer.apple.com/design/human-interface-guidelines/accessibility"),
    "hig_color": ("Apple Human Interface Guidelines, Color", "https://developer.apple.com/design/human-interface-guidelines/color"),
    "own": ("In-house design standard", ""),
    "css_text": ("W3C CSS Text Level 4, text-wrap", "https://www.w3.org/TR/css-text-4/"),
    "css_fonts": ("W3C CSS Fonts Level 4, font-variant-numeric", "https://www.w3.org/TR/css-fonts-4/"),
    "webkit_safe": ("WebKit, Designing Websites for iPhone X (safe area)", "https://webkit.org/blog/7929/designing-websites-for-iphone-x/"),
    "wcag_247": ("WCAG 2.2, 2.4.7 Focus Visible", "https://www.w3.org/WAI/WCAG22/Understanding/focus-visible.html"),
    "wcag_412": ("WCAG 2.2, 4.1.2 Name, Role, Value", "https://www.w3.org/WAI/WCAG22/Understanding/name-role-value.html"),
    "wcag_233": ("WCAG 2.2, 2.3.3 Animation from Interactions", "https://www.w3.org/WAI/WCAG22/Understanding/animation-from-interactions.html"),
    "webdev_anim": ("web.dev (Google), High-performance CSS animations", "https://web.dev/articles/animations-guide"),
    "nng": ("Nielsen Norman Group, Response Times: The 3 Important Limits", "https://www.nngroup.com/articles/response-times-3-important-limits/"),
    "wcag_143": ("WCAG 2.2, 1.4.3 Contrast (Minimum)", "https://www.w3.org/WAI/WCAG22/Understanding/contrast-minimum.html"),
    "wcag_222": ("WCAG 2.2, 2.2.2 Pause, Stop, Hide", "https://www.w3.org/WAI/WCAG22/Understanding/pause-stop-hide.html"),
    "css_pseudo": ("W3C CSS Pseudo-Elements Level 4, ::selection", "https://www.w3.org/TR/css-pseudo-4/#highlight-pseudos"),
    "impeccable": ("Impeccable design rules (pbakaus/impeccable)", "https://github.com/pbakaus/impeccable"),
    "w3c_headings": ("W3C WAI Tutorials, Headings", "https://www.w3.org/WAI/tutorials/page-structure/headings/"),
    "wcag_331": ("WCAG 2.2, 3.3.1 Error Identification", "https://www.w3.org/WAI/WCAG22/Understanding/error-identification.html"),
    "css_scrollbars": ("W3C CSS Scrollbars Styling Level 1", "https://www.w3.org/TR/css-scrollbars-1/"),
    "craft": ("Impeccable design rules", "https://github.com/pbakaus/impeccable"),
}
SOURCES = {1: "carbon", 2: "hig_layout", 3: "hig_layout", 4: "m3_divider", 5: "wwdc_356", 6: "m3_shape", 7: "carbon", 8: "hig_type",
           9: "wcag_148", 10: "hig_a11y", 11: "hig_color", 14: "own", 15: "own", 16: "css_text", 17: "css_fonts",
           18: "webkit_safe", 19: "wcag_247", 20: "wcag_412", 21: "wcag_233", 22: "webdev_anim", 23: "nng", 24: "wcag_143",
           25: "impeccable", 26: "impeccable", 27: "impeccable", 28: "impeccable", 29: "impeccable", 30: "impeccable", 31: "wcag_222",
           32: "impeccable", 33: "impeccable", 34: "impeccable", 35: "css_text", 36: "css_pseudo", 37: "impeccable",
           38: "wcag_148", 39: "wcag_148", 40: "w3c_headings", 41: "impeccable", 42: "impeccable", 43: "impeccable", 44: "impeccable",
           45: "impeccable", 46: "impeccable", 47: "impeccable", 48: "impeccable", 49: "impeccable", 50: "impeccable", 51: "impeccable",
           52: "impeccable", 53: "wcag_331", 54: "css_scrollbars", 55: "impeccable",
           56: "craft", 57: "craft", 58: "craft", 59: "craft", 60: "craft", 61: "craft", 62: "craft", 63: "craft"}
PRIORITY = {2: "high", 10: "high", 18: "high", 19: "high", 20: "high", 24: "high",
            1: "med", 3: "med", 5: "med", 6: "med", 7: "med", 8: "med", 9: "med", 21: "med", 22: "med", 23: "med",
            43: "high", 44: "high",
            14: "med", 15: "med", 25: "med", 28: "med", 29: "med", 31: "med", 33: "med", 38: "med", 40: "med", 41: "med", 45: "med", 46: "med", 52: "med", 53: "med",
            58: "med", 59: "med", 61: "med",
            56: "low", 57: "low", 60: "low", 62: "low", 63: "low",
            39: "low", 42: "low", 47: "low", 48: "low", 49: "low", 50: "low", 51: "low", 54: "low", 55: "low",
            4: "low", 11: "low", 16: "low", 17: "low", 26: "low", 27: "low", 30: "low", 32: "low", 34: "low", 35: "low", 36: "low", 37: "low"}
REMOVED = {12, 13}   # glow and macOS window bar are not part of the audit; internal ids stay, the numbers shown are sequential
ACTIVE = [n for n in range(1, 64) if n not in REMOVED]   # 25-55 Impeccable rules, 56-63 craft checks (2026-11-13)
N_POINTS = len(ACTIVE)
DISP = {n: i + 1 for i, n in enumerate(ACTIVE)}
MOBILE_POINTS = {2, 10, 16, 18, 20, 21, 46}   # measured in the iPhone 390px emulation, the rest on desktop 1440px
COLORS = {"g": "#1fbf6b", "r": "#ff2d87", "b": "#2e8bff", "a": "#f0b44c"}

# label drawn on the screenshot; "{v}" is the measured value from the page
MARK = {14: "label above heading",
        15: "glow", 25: "glass (blur)", 28: "icon tile", 30: "card in a card",
        31: "auto-scroll", 32: "gradient text", 33: "colour haze",
        35: "one-word line", 36: "text selection",
        39: "text setting", 41: "grey on colour", 42: "cramped",
        43: "invisible text", 44: "text covered", 46: "flush / clipped",
        47: "motion", 48: "grid background", 49: "palette", 53: "states / errors",
        54: "caret / scrollbar", 56: "italic", 57: "monospace",
        59: "photo / product", 61: "two equal CTAs", 16: "not balanced", 20: "no label",
        21: "animations off", 22: "animates size"}

UI = {
    "en": dict(chip=dict(ok="Pass", fail="Fail", exc="Conscious exception", na="Not applicable"), short=dict(ok="Pass", fail="Fix", exc="Exception", na="N/A"),
               eyebrow="Design · Mobile · Accessibility", head="Design guidelines audit", fix="What to fix:", why="Why:", changed="What we changed and why", source="Source", was="Before", now="After",
               h_all="meets premium design standards", h_some="{ok} of {total} checks meet the standards",
               lead="{total} checks: spacing, type, corner radius, phone usability and accessibility. Each point below has a screenshot of the page and a link to the Apple, Google, IBM, W3C or Impeccable standard.",
               k_ok="checks pass", k_fail="need fixing", k_exc="conscious design exceptions", k_na="not applicable to this page",
               fixes="What to fix", pri=dict(high="High priority", med="Medium priority", low="Low priority"), nofix="Nothing to fix."),
}

# title / ok / bad (/ fix) text per point, per language. Keys in {} come from the verdict dict.
TXT = {
    "en": {
        1: ("Section spacing: {med}px", "Sections are separated by {lo}-{hi}px (typically {med}px), all within the 48-160px scale and a multiple of 4.",
            "Section spacing is {lo}-{hi}px, typically {med}px. Outside the 48-160px scale or not a multiple of 4: {badlist}.",
            "Move vertical section spacing to one scale: 64 / 80 / 96 / 120px (48-80px on phones)."),
        2: ("Phone side margins: {min}px", "Text stays {min}px from the screen edge (main margin {mode}px).",
            "Text comes within {min}px of the screen edge. The minimum is 16px; the main margin is {mode}px.",
            "Set side margins of at least 16px (padding-inline: 16px) on every block with text."),
        3: ("Content width: {w}px", "Content takes {w}px of {vw}px with {gl}px margins on each side.",
            "Content stretches to {w}px of the {vw}px screen: long lines and extra eye travel on wide monitors.",
            "Cap the container: max-width 1184-1240px and centre it (margin-inline: auto)."),
        4: ("Borders: {wtxt}", "All borders on the page are thin: {wtxt}.", "{heavy} elements have a border thicker than 1px (up to {wmax}px).",
            "Replace thick borders with 1px or with a background / soft shadow."),
        5: ("Nested corner radius", "{pairs} nested pairs: the inner radius equals the outer radius minus the gap.",
            "{bad} of {pairs} nested pairs have the wrong inner radius (e.g. {R}px outside, {Rc}px inside with a {inset}px gap, should be {exp}px).",
            "Inner radius = outer radius minus the gap between the blocks (28px outside and 8px gap - 20px inside)."),
        6: ("Radius scale: {k} values", "{lst}. No more than 4 values, the rest are capsules and circles.", "{k} different corner radii: {lst}. The scale should have at most 4 values.",
            "Reduce to a 12 / 20 / 28px scale (capsule for buttons)."),
        7: ("Spacing grid: {pct}% off-grid", "{pct}% of spacing values are off the 4px grid ({off} of {tot}).",
            "{off} of {tot} spacing values ({pct}%) are not multiples of 4px, most often {top}.", "Move padding, margin and gap to multiples of 4 (ideally 8): 8, 16, 24, 32, 48px."),
        8: ("Type scale: {k} sizes", "{lst}. No more than 5 sizes, minimum {min}px.", "{k} text sizes under 24px: {lst}. {note}",
            "Reduce to 4-5 sizes (for example 13 / 15 / 17 / 19px), minimum 11px, ideally 13px."),
        9: ("Line length: up to {cpl} characters", "The longest text line is about {cpl} characters (WCAG: up to 80).",
            "The longest line is about {cpl} characters; WCAG recommends up to 80.", "Limit text width: max-width 60-70ch."),
        10: ("Tap target: at least 44px", "All {total} buttons and links on the phone are 44px or larger.",
             "{bad} of {total} buttons and links on the phone are smaller than 44x44px, the smallest is {minw}x{minh}px.",
             "Enlarge the tap area to 44x44px (padding or min-height: 44px; for tiny icons use an invisible pseudo-element)."),
        11: ("Accent colour: {k} hues", "Accent colours: {k} ({lst}). The rest of the palette is neutral.", "{k} accent hues ({lst}): use 1-3 - none looks unfinished, more than 3 is too colourful.",
             "Keep 1-2 accent colours (main for buttons, second for highlights); everything else neutral."),
        14: ("No labels above headings", "No small labels above headings: each heading carries itself.",
             "{bad} small labels above headings (capsules, kickers), the generic AI-design template.",
             "Delete the label. If the information matters, move it into the heading or the text below it."),
        15: ("No glow", "No coloured glow: not on dots, buttons or cards.",
             "{n} elements have a coloured glow ({list}): a blurred coloured shadow reads as a template AI effect.",
             "Replace the coloured shadow with a neutral one (0 2px 6px rgba(0,0,0,.4)) or remove it; dots become a thin check mark."),
        16: ("Balanced headings", "All {multi} multi-line headings use text-wrap: balance or pretty.",
             "{bad} of {multi} multi-line headings are not balanced: the last line may be a single word.", "Add h1, h2, h3 { text-wrap: balance }."),
        17: ("Equal-width digits", "All {total} numeric elements use font-variant-numeric: tabular-nums.",
             "{bad} of {total} numeric elements (prices, counters) lack tabular-nums, so the digits jump.", "Add font-variant-numeric: tabular-nums to prices, counters and tables."),
        18: ("Bottom bar and iPhone", "The bottom bar respects the iPhone home indicator (safe-area-inset-bottom).",
             "There is a bottom bar, but {why}.", "Add padding-bottom: calc(8px + env(safe-area-inset-bottom))."),
        19: ("Visible focus", "All {tested} tested elements show a visible focus when tabbing.", "{bad} of {tested} tested elements show no visible focus when tabbing.",
             "Add :focus-visible { outline: 2px solid accent; outline-offset: 2px } and never set outline: none without a replacement."),
        20: ("Labels on icon buttons and images", "Icon buttons ({icon}) have a screen-reader label and every image has alt.",
             "{bad} of {icon} icon buttons have no aria-label, {noalt} images have no alt.", "Add aria-label to icon buttons and alt to images (decorative ones - alt=\"\")."),
        21: ("Reduced motion", "{why}", "{why}",
             "In @media (prefers-reduced-motion: reduce) remove movement (slides, scale, auto-scroll, smooth scrolling) but keep short colour and opacity fades, instead of switching everything off with *{animation:none;transition:none}."),
        22: ("Animation without layout change", "Transitions do not change height, width or position (only transform and opacity).",
             "{n} elements animate size or position (height, width, max-height, top, margin...){kf}. Can stutter on slow phones.",
             "Animate transform and opacity (or grid-template-rows) instead of height."),
        23: ("Button feedback: up to 300 ms", "{ok} of {total} buttons have a 100-300 ms transition (typically {typ} ms).",
             "{bad} of {total} buttons have no transition or one slower than 300 ms.", "Add transition: 0.2s for colour and transform on buttons."),
        24: ("Text contrast: from {min}:1", "The weakest text has {min}:1 contrast (WCAG AA: 4.5:1, large text 3:1).",
             "{bad} text elements are below WCAG AA, the worst is {min}:1.", "Darken or lighten the text colour to 4.5:1 contrast (large text 3:1)."),
        25: ("No decorative glass", "No background blur (backdrop-filter) is used.",
             "{n} elements use blurred glass ({list}): a decorative effect instead of a solid surface.",
             "Solid surfaces instead of glass: header and bottom bar in the page background colour, no backdrop-filter."),
        26: ("Font: {fonts}", "The main font ({fonts}) is not on the overused list.",
             "The main font {bad} is one of the most overused (Inter, Roboto, Geist...), so the page looks like thousands of others.",
             "Pick a less common font that fits the client's brand and covers every language on the site."),
        27: ("Letter-spacing: from -0.04em", "No text is tighter than -0.04em.",
             "{n} text elements are tighter than -0.04em (tightest {worst}em): letters start to merge.",
             "Keep heading letter-spacing at -0.04em or looser (e.g. -0.03em)."),
        28: ("No icon tiles above headings", "No square icon tiles stacked above card headings.",
             "{n} icon tiles above card headings - the most common AI feature-card template.",
             "Icon beside the heading, or a thin line icon without a tile, or no icon at all."),
        29: ("No grid of identical cards", "No rows of 3+ identical cards as the page structure.",
             "{n} grids of identical cards ({cards} cards): the lazy icon + heading + text structure.",
             "Columns without cards under one thin line, a list, or one lead item with the rest lighter."),
        30: ("No card inside a card", "No cards nested inside other cards.",
             "{n} cards sit inside other cards: extra depth and visual noise.",
             "Drop the inner border and background: separate it with spacing, a heading or a thin divider."),
        31: ("No auto-scrolling", "No strips or columns that scroll by themselves.",
             "{n} blocks scroll by themselves forever: distracting, and half the content is always hidden.",
             "A static row, or scrolling only on user action; if motion is needed, a pause button (WCAG 2.2.2)."),
        32: ("No gradient text", "Text uses solid colours.",
             "{n} elements use gradient text ({list}): a decorative AI trick.",
             "Solid colour; emphasis comes from weight or size."),
        33: ("No coloured background haze", "No coloured radial/conic glow in the backgrounds.",
             "{n} blocks have a coloured radial/conic haze in the background: the typical 'space glow' AI backdrop.",
             "A plain background or a photo; depth from an offset shadow, not a coloured cloud."),
        34: ("Heading rhythm", "All {total} headings have more space above than below.",
             "{bad} of {total} headings have no more space above than below (e.g. {ex}px), so they don't bind to their own text.",
             "More space above a heading than below it (e.g. 32px above, 8-12px below)."),
        35: ("No one-word last lines", "None of the {total} paragraphs ends with a single word on its last line.",
             "{n} of {total} paragraphs end with one word alone on the last line, leaving a hole under the text.",
             "Add p, li { text-wrap: pretty }."),
        36: ("Text selection colour", "Selected text uses the brand colours (::selection).",
             "Selected text uses the browser's default blue: a detail that shows the page was assembled, not designed.",
             "Add ::selection { background: brand colour; color: #fff }."),
        37: ("No hero-metric numbers", "No bare numbers set at 64px or larger.",
             "{n} numbers are set as a 'hero metric' ({ex}): the big-number-plus-small-label template.",
             "Make the price or number part of the heading or text (e.g. 40-48px), without a gradient."),
        38: ("Line height: from 1.3", "Body text has a line height of 1.3 or more (ideally 1.5-1.7).",
             "{n} text blocks have a line height under 1.3 (lowest {worst}): the lines run together.",
             "line-height 1.5-1.7 for body text."),
        39: ("Text setting", "No justified text, no long ALL-CAPS passages, no spaced-out body text.",
             "Text setting problems: justified - {just}, long ALL-CAPS - {caps}, spaced-out body text - {wide}.",
             "text-align: left; capitals only for short labels; body letter-spacing at most 0.05em."),
        40: ("Heading order", "{total} headings are in order, {h1} h1.",
             "Heading levels jump ({n} times, e.g. {ex}) or there is not exactly one h1 ({h1}): the outline breaks for screen readers.",
             "One h1, then h2 > h3 without skipping levels (set the size with a CSS class, not the level)."),
        41: ("No grey text on colour", "No grey text on saturated coloured backgrounds.",
             "{n} elements have grey text on a coloured background: it looks washed out.",
             "On colour use white/near-white text or a darker shade of the background colour, not grey."),
        42: ("Inner padding", "Text never sits tight against the edges of its own box.",
             "{n} boxes have text closer than 8px to the side (or 3px top/bottom): it looks cramped.",
             "At least 8px inner padding at the sides of a text box (buttons and chips 12-16px)."),
        43: ("All text visible", "After loading and scrolling all text is visible ({pct}% invisible).",
             "{pct}% of the page text stays invisible (opacity 0) even after scrolling: a failed reveal animation.",
             "Show content by default and animate only from a visible state; provide a no-JS and reduced-motion fallback."),
        44: ("Text not covered", "No text is covered by another element.",
             "{n} text elements sit partly under another opaque element and cannot be read.",
             "Remove the overlap: z-index, spacing or the position of the decorative box."),
        45: ("First-screen columns", "The first-screen columns are balanced.",
             "One first-screen column runs to {ex} while its neighbour fits the screen: dead space beside a long column.",
             "Shorten the long column, move part of it lower, or balance the column heights."),
        46: ("Sideways rows and pop-ups", "Cards in sideways rows don't stick to the edge; pop-ups are not clipped.",
             "Rows with cards flush against the edge: {flush}; clipped menus/tooltips: {clipped}.",
             "Give the row inner padding (padding-inline and scroll-padding 16px); the menu's parent gets overflow: visible."),
        47: ("Calm motion", "No bounce / elastic easing and no pulsing dots.",
             "Bounce easing: {bounce}, pulsing dots: {pulse}: looks cheap and 'alive' for no reason.",
             "Smooth ease-out without overshoot; a static indicator with a label instead of a pulse."),
        48: ("No decorative grid background", "No grid-line or striped decorative backgrounds.",
             "{n} blocks have a decorative grid or stripes in the background: the template AI backdrop.",
             "A plain background, a photo or a real brand texture."),
        49: ("Palette without AI clichés", "No purple gradients, cyan text on dark or cream page background.",
             "Palette clichés: purple gradients - {purple}, cyan text on dark - {cyan}, cream background - {cream}.",
             "Colours from the client's brand; the page background is a deliberate choice, not a default beige."),
        50: ("No numbered sections", "Sections are not numbered with small digits (01 / 02 / 03).",
             "{n} small numbers next to section headings: the page numbers its own chapters instead of earning attention.",
             "Remove the numbers unless the sequence matters to the reader."),
        51: ("Main headline size", "Main headline: {fs}px, {words} words, {share}% of the screen height.",
             "The main headline is oversized: {fs}px, {words} words, {share}% of the screen height - nothing else fits on the first screen.",
             "A full sentence at 40-56px; display size only for 1-2 words."),
        52: ("Copy without AI clichés", "The copy has no marketing buzzwords or aphoristic slogans.",
             "Buzzwords: {buzz} ({words}); 'Not X. Just Y.' lines: {aph}; 'theatre': {thea}. This is how text generators write.",
             "Replace each buzzword with a specific: what exactly, how much, how fast (e.g. 'diagnostics in 30 min')."),
        53: ("Interface states and errors", "Hover, disabled, error and loading states exist; form errors are explained.",
             "Missing: {missing}.",
             "Add :hover, :disabled, error (aria-invalid / .is-invalid) and loading (aria-busy) styles; next to every required field a message saying what is wrong and how to fix it."),
        54: ("Browser details", "The scrollbar and the input caret use the site's colours.",
             "Not styled: {missing}.",
             "Add scrollbar-color: thumb-colour track-colour; and caret-color: accent for inputs."),
        55: ("One motion moment", "The reveal animation is not repeated identically on every section.",
             "The same reveal animation '{tok}' on {n} of {sections} sections: motion becomes a template, not an accent.",
             "Keep one designed motion moment (e.g. the first screen); show the other sections without the identical animation."),
        56: ("No random italic words", "Headings have no single words set in italics.",
             "{n} italic words inside headings: the italic-serif trick that screams AI template.",
             "Set the heading in one style; emphasis comes from the words, not italics."),
        57: ("Monospace only for code", "Monospace is not used as decoration.",
             "{n} text elements use monospace outside code and data: a 'technical' costume.",
             "Monospace only for code, IDs and measurements; headings and copy in the main font."),
        58: ("One button system", "{total} buttons in {k} style variants - a consistent system.",
             "{total} buttons in {k} different styles (radius, weight, size, border): no single design system.",
             "Reduce to 2-3 variants: primary, secondary (outline), text; same sizes and radius."),
        59: ("Real product on the first screen", "The first screen shows a real photo, product shot or video.",
             "The first screen has no photo or product shot at all: only text and decoration.",
             "Show the real service, car, team or interface - not an abstract illustration."),
        60: ("Spacing rhythm", "Spacing varies: tight inside groups, wider between them (most common {top}px - {share}%).",
             "One gap of {top}px is {share}% of all spacing: everything is equally far apart, groups don't read.",
             "Tight inside a group (8-12px), wider between groups (24-48px), widest between sections (80-96px)."),
        61: ("One primary CTA", "Each button group has one primary button; the rest are secondary.",
             "{n} groups have two neighbouring buttons with the same filled colour: the main action is unclear.",
             "One filled button per group; the second is outline or text."),
        62: ("Consistent icons", "Icons share one style ({kinds}).",
             "Icons mix styles ({kinds}): different stroke widths, filled next to outline.",
             "One icon set: one stroke width (e.g. 1.8-2px), no mixing with filled icons."),
        63: ("Play icon optically centred", "Play icons are shifted to look centred in their circle.",
             "{n} play icons are centred geometrically, so the triangle looks off to the left.",
             "Shift the triangle right by ~5-8% of its width (transform: translateX(2px)) - align by eye, not by pixels."),
    },
}
# one-line 'why we check it / why it is best practice' per point (internal ids), shown on every card
WHY = {
    "en": {
        1: 'Equal, generous gaps between sections tell the reader where one topic ends; IBM Carbon spaces higher levels further apart.',
        2: 'Text touching the screen edge is hard to read and looks broken; Apple asks for system margins on every screen.',
        3: 'Very wide content forces long eye travel on big monitors; a capped, centred column keeps the page calm.',
        4: 'Thick borders make a page heavy and dated; 1px hairlines separate without shouting (Material divider spec).',
        5: 'A mismatched inner radius makes nested shapes look unequal; concentric radii are how Apple builds its UI.',
        6: 'A few corner radii make a page feel designed; many random ones look assembled from different kits.',
        7: 'A 4/8px grid keeps spacing consistent and fast to build; off-grid values look accidental.',
        8: 'Few text sizes give a clear hierarchy; many sizes and tiny text make the page noisy and hard to read.',
        9: 'Lines over ~80 characters make the eye lose its place when jumping to the next line (WCAG 1.4.8).',
        10: 'Fingers need about 44x44px; smaller targets cause mis-taps and lost leads on phones (Apple HIG).',
        11: 'One to three accents guide the eye to actions; none looks unfinished, many look like a template.',
        14: 'Small kickers above headings are the most recognisable AI-template mark; a strong heading needs no label.',
        15: "Coloured glows are the default 'cool' effect of generated pages; neutral offset shadows read as real depth.",
        16: 'Balanced headings avoid a single orphan word on the last line, which looks careless.',
        17: 'Tabular digits keep prices and counters from jumping as numbers change.',
        18: 'Without safe-area padding the bottom bar sits under the iPhone home indicator and is hard to tap.',
        19: 'Keyboard users need to see where focus is; it is a WCAG AA requirement (2.4.7).',
        20: 'Screen readers announce icon buttons and images only if they have a label or alt text (WCAG 4.1.2).',
        21: 'Reduced motion should remove movement, not all feedback; a global switch-off hides state changes too.',
        22: 'Animating size or position forces layout work and stutters on slow phones; transform and opacity stay smooth.',
        23: 'Button feedback within ~100-300ms feels instant; slower or missing feedback feels broken (NN/g).',
        24: 'Low-contrast text is unreadable for many visitors and in sunlight; WCAG AA needs 4.5:1.',
        25: 'Decorative glass is a template effect, costs performance and lowers contrast; solid surfaces are clearer.',
        26: 'Inter, Roboto and Geist are on most generated pages; a brand-fitting font makes the client look distinct.',
        27: 'Tracking tighter than -0.04em makes letters touch and lowers legibility, especially in Cyrillic.',
        28: 'A rounded icon tile above every card heading is the default AI feature card; it adds noise, not meaning.',
        29: 'Rows of identical cards give every point the same weight; real hierarchy helps visitors decide.',
        30: 'A card inside a card adds depth without meaning; spacing and dividers group content more cleanly.',
        31: 'Auto-scrolling content distracts and hides half its items; WCAG 2.2.2 requires a way to stop it.',
        32: 'Gradient text is decoration that hurts legibility; emphasis should come from weight or size.',
        33: "Coloured background haze is the 'space glow' backdrop of generated pages; it muddies contrast.",
        34: 'More space above a heading than below binds it to its own text, so sections read as units.',
        35: 'A single word on the last line leaves a hole and looks unedited; text-wrap: pretty fixes it for free.',
        36: 'The default blue selection is a small sign the page was not finished; brand colours show care.',
        37: 'A huge bare number with a small label is a SaaS template; a price inside the heading reads as information.',
        38: 'Line height under 1.3 makes lines run together; WCAG suggests about 1.5 for body text.',
        39: 'Justified text makes rivers, long capitals hide word shapes, wide tracking slows reading (WCAG 1.4.8).',
        40: 'Ordered heading levels let screen-reader users jump through the page (W3C headings tutorial).',
        41: 'Grey on colour looks washed out; a tint of the background or white keeps text crisp.',
        42: 'Text glued to its box edge looks cramped and cheap; inner padding gives it room.',
        43: 'Text left invisible by a failed reveal animation is content the visitor never sees.',
        44: 'Text covered by another element cannot be read; it is usually a layout bug.',
        45: 'A first-screen column that runs far past the fold leaves dead space beside it and hides the CTA.',
        46: "Cards glued to a scroller's edge look cut off; clipped menus and tooltips cannot be used.",
        47: 'Bounce easing and pulsing dots feel dated and restless; real objects decelerate smoothly.',
        48: 'Decorative grid-line and stripe backgrounds are a recurring generated-page signature.',
        49: "Purple gradients, cyan-on-dark and default cream are the AI palette; brand colours are the client's own.",
        50: 'Section numbers 01/02/03 are editorial scaffolding; they add nothing unless order matters.',
        51: 'A full-sentence headline at display size eats the first screen and pushes the offer below the fold.',
        52: "Buzzwords and 'Not X. Just Y.' slogans read as machine-written; specifics build trust.",
        53: 'Visible hover, disabled, loading and error states tell people what is happening (WCAG 3.3.1).',
        54: 'Default scrollbars and carets belong to no design system; themed ones show the page was built with care.',
        55: 'The same reveal on every section turns motion into wallpaper; one designed moment is remembered.',
        56: 'A random italic word in a heading is the italic-serif AI trick; it adds style without meaning.',
        57: "Monospace as a 'technical' look is costume; it should mark code or data only.",
        58: 'Buttons in many ad-hoc styles look assembled; 2-3 consistent variants form a design system.',
        59: 'A real photo or product shot builds trust faster than abstract illustration.',
        60: 'Identical gaps everywhere hide grouping; tight groups and wider separations make structure visible.',
        61: 'Two equally loud buttons make visitors hesitate; one primary action converts better.',
        62: 'Mixed icon styles look collected from different kits; one stroke and style looks intentional.',
        63: 'A geometrically centred triangle looks off-centre; optical alignment looks right to the eye.',
    },
}
NA_TEXT = {"en": "Not applicable: the page has no such element."}


def fmt(x):
    return str(int(round(x))) if abs(x - round(x)) < 0.05 else f"{x:.1f}"


# ---------------------------------------------------------------------------------------------
# Verdicts: (status, dict for the text templates). D is the browser data of the point, css the page CSS.
# ---------------------------------------------------------------------------------------------
def v1(D, c):
    """Each section's OWN vertical spacing is judged against the 48-160px scale (a pair sums two of them, up to 2x160)."""
    g, sides = D["gaps"], D.get("sides") or D["gaps"]
    if not g: return "na", {}
    s = sorted(sides); med = s[len(s) // 2]
    bad = [x for x in g if x < 48 or x > 320] + [x for x in sides if x > 160 or abs(x / 4 - round(x / 4)) > 0.01]
    return ("fail" if bad else "ok"), dict(med=fmt(med), lo=fmt(min(g)), hi=fmt(max(g)), badlist=", ".join(fmt(x) + "px" for x in sorted(set(bad))[:5]))


def v2(D, c):
    return ("ok" if D["min"] >= 16 else "fail"), dict(min=fmt(D["min"]), mode=fmt(D["mode"]))


def v3(D, c):
    w = D["r"] - D["l"]
    return ("ok" if w <= 1280 else "fail"), dict(w=w, vw=D["vw"], gl=round(D["l"]))


def v4(D, c):
    ws = sorted(float(k) for k in D["widths"])
    return ("fail" if D["heavy"] else "ok"), dict(heavy=D["heavy"], wmax=fmt(D["wmax"]), wtxt=" / ".join(fmt(w) + "px" for w in ws[:4]) or "-")


def v5(D, c):
    if not D["pairs"]: return "na", {}
    return ("fail" if D["bad"] else "ok"), dict(pairs=D["pairs"], bad=D["bad"], R=fmt(D["R"]), Rc=fmt(D["Rc"]), inset=fmt(D["inset"]), exp=fmt(D["exp"]))


def v6(D, c):
    merged = []
    for r in D["radii"]:
        if merged and r["R"] - merged[-1][0] <= 1: merged[-1][1] += r["n"]; merged[-1][0] = max(merged[-1][0], r["R"])
        else: merged.append([r["R"], r["n"]])
    if not merged: return "na", {}
    return ("ok" if len(merged) <= 4 else "fail"), dict(k=len(merged), lst=" / ".join(f"{m[0]}px" for m in merged))


def v7(D, c):
    if not D["tot"]: return "na", {}
    p = 100.0 * D["off"] / D["tot"]
    return ("ok" if p <= 5 else "fail"), dict(pct=fmt(p), off=D["off"], tot=D["tot"], top=", ".join(f"{fmt(t['v'])}px" for t in D["top"]) or "-")


def v8(D, c, lang):
    s = D["sizes"]; k = len(s)
    if not k: return "na", {}
    note = ""
    if D["small"]:
        note = ((f"{D['small']} elements are under 11px."))
    return ("ok" if k <= 5 and not D["small"] else "fail"), dict(k=k, lst=" / ".join(f"{fmt(x['f'])}px" for x in s), min=fmt(s[0]["f"]), note=note)


def v9(D, c):
    return ("ok" if D["cpl"] <= 80 else "fail"), dict(cpl=D["cpl"])


def v10(D, c):
    if not D["total"]: return "na", {}
    return ("fail" if D["bad"] else "ok"), dict(total=D["total"], bad=D["bad"], minw=D["minw"], minh=D["minh"])


def v11(D, c):
    k = len(D["buckets"])
    return ("ok" if 1 <= k <= 3 else "fail"), dict(k=k, lst=", ".join(b["c"] for b in D["buckets"][:5]) or "-")




def v14(D, c):
    return ("fail" if D["bad"] else "ok"), dict(n=D["n"], bad=D["bad"])


def v15(D, c): return ("fail" if D["n"] else "ok"), dict(n=D["n"], list=D.get("list") or "-")


def v16(D, c):
    if not D["multi"]: return "na", {}
    return ("fail" if D["bad"] else "ok"), dict(multi=D["multi"], bad=D["bad"])


def v17(D, c):
    if not D["total"]: return "na", {}
    return ("fail" if D["bad"] else "ok"), dict(total=D["total"], bad=D["bad"])


def v20(D, c):
    return ("fail" if D["bad"] + D["noalt"] else "ok"), dict(icon=D["icon"], bad=D["bad"], noalt=D["noalt"])


def v22(D, c, lang):
    kf = c["kf_layout"]
    kft = ""
    if kf: kft = ((f"; @keyframes: {', '.join(kf[:3])}"))
    return ("fail" if D["n"] or kf else "ok"), dict(n=D["n"], kf=kft)


def v23(D, c):
    if not D["total"]: return "na", {}
    good = D["ok"] / D["total"] >= 0.8
    return ("ok" if good else "fail"), dict(total=D["total"], ok=D["ok"], bad=D["bad"], typ=D["typ"])


def v24(D, c):
    return ("fail" if D["bad"] else "ok"), dict(min=fmt(D["min"]), bad=D["bad"], rows=D["rows"])


# ---- 25-37: Impeccable rules (2026-11-13) ----
def v25(D, c): return ("fail" if D["n"] else "ok"), dict(n=D["n"], list=D["list"] or "-")


def v26(D, c):
    if not D["fonts"]: return "na", {}
    return ("fail" if D["bad"] else "ok"), dict(fonts=D["fonts"], bad=D["bad"])


def v27(D, c): return ("fail" if D["n"] else "ok"), dict(n=D["n"], worst=D["worst"])
def v28(D, c): return ("fail" if D["n"] else "ok"), dict(n=D["n"])
def v29(D, c): return ("fail" if D["n"] else "ok"), dict(n=D["n"], cards=D["cards"])
def v30(D, c): return ("fail" if D["n"] else "ok"), dict(n=D["n"])
def v31(D, c): return ("fail" if D["n"] else "ok"), dict(n=D["n"])
def v32(D, c): return ("fail" if D["n"] else "ok"), dict(n=D["n"], list=D["list"] or "-")
def v33(D, c): return ("fail" if D["n"] else "ok"), dict(n=D["n"])


def v34(D, c):
    """Fails when 30%+ of the measurable headings have no more space above than below."""
    if not D["total"]: return "na", {}
    return ("fail" if D["bad"] / D["total"] >= 0.3 else "ok"), dict(total=D["total"], bad=D["bad"], ex=D["ex"] or "-")


def v35(D, c):
    if not D["total"]: return "na", {}
    return ("fail" if D["n"] else "ok"), dict(total=D["total"], n=D["n"])


def v36(D, c): return ("ok" if c["selection"] else "fail"), {}


# ---- 38-55: groups 1 + 2 (2026-11-13) ----
def v38(D, c): return ("fail" if D["n"] else "ok"), dict(n=D["n"], worst=D["worst"])
def v39(D, c): return ("fail" if D["n"] else "ok"), dict(just=D["just"], caps=D["caps"], wide=D["wide"])


def v40(D, c):
    if not D["total"]: return "na", {}
    return ("fail" if D["n"] or D["h1"] != 1 else "ok"), dict(total=D["total"], h1=D["h1"], n=D["n"], ex=D["ex"] or "-")


def v41(D, c): return ("fail" if D["n"] else "ok"), dict(n=D["n"])
def v42(D, c): return ("fail" if D["n"] else "ok"), dict(n=D["n"])
def v43(D, c): return ("fail" if D["pct"] >= 10 else "ok"), dict(pct=fmt(D["pct"]))
def v44(D, c): return ("fail" if D["n"] else "ok"), dict(n=D["n"])


def v45(D, c):
    if D.get("na"): return "na", {}
    return ("fail" if D["bad"] else "ok"), dict(ex=D["ex"] or "-")


def v46(D, c): return ("fail" if D["n"] else "ok"), dict(flush=D["flush"], clipped=D["clipped"])
def v47(D, c): return ("fail" if D["n"] else "ok"), dict(bounce=D["bounce"], pulse=D["pulse"])
def v48(D, c): return ("fail" if D["n"] else "ok"), dict(n=D["n"])
def v49(D, c): return ("fail" if D["n"] else "ok"), dict(purple=D["purple"], cyan=D["cyan"], cream=D["cream"] or "-")
def v50(D, c): return ("fail" if D["n"] else "ok"), dict(n=D["n"])


def v51(D, c):
    if D.get("na"): return "na", {}
    return ("fail" if D["bad"] else "ok"), dict(fs=D["fs"], words=D["words"], share=D["share"])


def v52(D, c):
    bad = D["buzz"] >= 2 or D["aph"] >= 3 or D["thea"] >= 1
    return ("fail" if bad else "ok"), dict(buzz=D["buzz"], words=D["words"] or "-", aph=D["aph"], thea=D["thea"])


def v53(D, c, lang):
    css = c["css"]
    miss = []
    if ":hover" not in css: miss.append("hover")
    if D["forms"]:
        if not re.search(r":disabled|\[disabled\]|is-disabled", css): miss.append("disabled")
        if not re.search(r":invalid|aria-invalid|is-invalid|\.error|has-error|\.invalid", css): miss.append(("error state"))
        if not re.search(r"is-loading|aria-busy|\.loading|is-sending|spinner|\[disabled\]", css): miss.append(("loading"))
        if D["req"] and D["explained"] < D["req"]:
            miss.append((f"error messages for {D['req'] - D['explained']} of {D['req']} required fields"))
    return ("fail" if miss else "ok"), dict(missing=", ".join(miss) or "-")


def v54(D, c, lang):
    miss = []
    if not re.search(r"scrollbar-color|::-webkit-scrollbar", c["css"]): miss.append("scrollbar")
    if D["inputs"] and not D["caret"]: miss.append(("input caret"))
    return ("fail" if miss else "ok"), dict(missing=", ".join(miss) or "-")


def v56(D, c): return ("fail" if D["n"] else "ok"), dict(n=D["n"])
def v57(D, c): return ("fail" if D["n"] else "ok"), dict(n=D["n"])


def v58(D, c):
    if not D["total"]: return "na", {}
    return ("fail" if D["k"] > 4 else "ok"), dict(total=D["total"], k=D["k"])


def v59(D, c): return ("ok" if D["n"] else "fail"), {}


def v60(D, c):
    if not D["tot"]: return "na", {}
    return ("fail" if D["share"] > 60 else "ok"), dict(top=D["top"], share=D["share"])


def v61(D, c): return ("fail" if D["n"] else "ok"), dict(n=D["n"])


def v62(D, c):
    if D["total"] < 3: return "na", {}
    return ("fail" if D["bad"] else "ok"), dict(kinds=D["kinds"])


def v63(D, c):
    if not D["total"]: return "na", {}
    return ("fail" if D["n"] else "ok"), dict(n=D["n"])


def v55(D, c):
    if not D["sections"]: return "na", {}
    return ("fail" if D["n"] >= 4 else "ok"), dict(tok=D["tok"] or "-", n=D["n"], sections=D["sections"])
def v37(D, c): return ("fail" if D["n"] else "ok"), dict(n=D["n"], ex=D["ex"] or "-")


# ---------------------------------------------------------------------------------------------
# CSS helpers
# ---------------------------------------------------------------------------------------------
def keyframes_layout(css):
    """Names of @keyframes that animate layout properties (height/width/top/left/margin/padding)."""
    names, i = [], 0
    while True:
        m = re.compile(r"@(?:-webkit-)?keyframes\s+([\w-]+)\s*\{").search(css, i)
        if not m: break
        depth, j = 1, m.end()
        while j < len(css) and depth:
            depth += {"{": 1, "}": -1}.get(css[j], 0); j += 1
        body = css[m.end():j]
        if re.search(r"(?:^|[;{\s])(height|width|max-height|top|left|right|bottom|margin[\w-]*|padding[\w-]*)\s*:", body) and m.group(1) not in names:
            names.append(m.group(1))
        i = j
    return names


def reduced_motion_kill(css):
    """True when a prefers-reduced-motion block switches off ALL animation/transition with a universal
    selector (*, html, body) instead of removing only the movement (Impeccable audit rule, 2026-11-13)."""
    for m in re.finditer(r"@media[^{]*prefers-reduced-motion\s*:\s*reduce[^{]*\{", css):
        depth, j = 1, m.end()
        while j < len(css) and depth:
            depth += {"{": 1, "}": -1}.get(css[j], 0); j += 1
        for sel, body in re.findall(r"([^{}]+)\{([^{}]*)\}", css[m.end():j]):
            if re.search(r"(^|,)\s*(\*|html|body)(\s*,|\s*$|::?before|::?after|\s+\*)", sel.strip()) and \
               re.search(r"(animation|transition)[\w-]*\s*:\s*(none|0s|0\.0*1m?s|1ms)", body):
                return True
    return False


def fetch_css(ctx, page_url, sheets, inline):
    css = inline
    for href in sheets:
        try:
            if href.startswith("file://"):
                css += "\n" + pathlib.Path(urllib.parse.unquote(urllib.parse.urlparse(href).path)).read_text(errors="ignore")
            else:
                r = ctx.request.get(href, timeout=15000)
                if r.ok: css += "\n" + r.text()
        except Exception:
            pass
    return css


# ---------------------------------------------------------------------------------------------
# Measuring + screenshots
# ---------------------------------------------------------------------------------------------
def host_args(url):
    """Extra Chromium args per host. Empty by default; add a --host-resolver-rules entry here if a site
    only resolves correctly through a specific DNS server on your machine."""
    return []


def new_ctx(browser, mobile, reduce=False):
    kw = dict(ignore_https_errors=True)
    if reduce: kw["reduced_motion"] = "reduce"
    if mobile: kw.update(viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True, device_scale_factor=2)
    else: kw.update(viewport={"width": 1440, "height": 900}, device_scale_factor=1)
    return browser.new_context(**kw)


def prep(page, url, hide_banners=True):
    page.goto(url, wait_until="load", timeout=45000)
    try: page.wait_for_load_state("networkidle", timeout=8000)
    except Exception: pass
    page.add_style_tag(content="html{scroll-behavior:auto !important}" + (
        "[class*=cky],[id*=cky],[class*=cookie],[id*=cookie],[class*=consent],[id*=onetrust]{display:none !important}" if hide_banners else ""))
    h = page.evaluate("document.documentElement.scrollHeight")
    for y in range(0, h, 500):                      # trigger scroll-reveal observers
        page.evaluate(f"window.scrollTo(0,{y})"); page.wait_for_timeout(60)
    page.evaluate("window.scrollTo(0,0)"); page.wait_for_timeout(1500)


def focus_test(page):
    tops = page.evaluate(FOCUS_ASSIGN_JS)
    base = {t["id"]: t["base"] for t in tops}
    tested, seen = [], set()
    page.evaluate("document.activeElement && document.activeElement.blur(); window.scrollTo(0,0)")
    for k in range(1, 40):
        page.keyboard.press("Tab")
        r = page.evaluate(FOCUS_READ_JS)
        if not r or r["id"] in seen: continue
        seen.add(r["id"])
        visible = r["sig"] != base[r["id"]] or (r["os"] != "none" and r["ow"] > 0)
        tested.append(dict(id=r["id"], ok=visible, r=r["r"], tabs=k))
        if len(tested) >= 12: break
    return tested


def measure(browser, url, lang):
    """Run the in-page measurements. Returns results {n: dict(status, d, marks, ctx, extra)}."""
    res, raw, css = {}, {}, ""
    for mobile in (False, True):
        ctx = new_ctx(browser, mobile); pg = ctx.new_page(); prep(pg, url)
        r = pg.evaluate(COLLECT_JS, {"mobile": mobile})
        raw[mobile] = r["out"]
        if not mobile:
            css = fetch_css(ctx, url, r["sheets"], r["inline"]); meta_vp = r["metaVp"]
            ftest = focus_test(pg)
        else:
            pg.evaluate("window.scrollTo(0,1200)"); pg.wait_for_timeout(800)
            bars = pg.evaluate(BARS_JS)
        ctx.close()
    cdata = dict(kf_layout=keyframes_layout(css), selection="::selection" in css, css=css)
    for n in ACTIVE:
        mobile = n in MOBILE_POINTS
        D = raw[mobile].get(str(n)) if n not in (18, 19) else {}
        res[n] = dict(n=n, mobile=mobile, status="na", d={}, marks=[], special=None)
        if n == 18:
            if bars:
                has_safe = "safe-area-inset-bottom" in css; has_cover = "viewport-fit=cover" in meta_vp.replace(" ", "")
                why = []   # without viewport-fit=cover Safari keeps the bar above the home indicator itself; with cover the padding is required
                if has_cover and not has_safe: why.append(("viewport-fit=cover is set but there is no safe-area-inset-bottom padding"))
                b = bars[0]["r"]
                res[n].update(status="ok" if not why else "fail", d=dict(why=((" and ")).join(why)),
                              marks=[dict(c="g" if not why else "r", r=b, v="", f=False), dict(c="b", r=[0, b[1] + b[3] - 34, b[2], 34], v="home", f=True)], special="scroll1200")
            continue
        if n == 19:
            if ftest:
                bad = [t for t in ftest if not t["ok"]]; pick = bad[0] if bad else ftest[0]
                res[n].update(status="fail" if bad else "ok", d=dict(tested=len(ftest), bad=len(bad)), marks=[dict(c="r" if bad else "g", r=pick["r"], v="", f=False)],
                              special=("focus", pick["id"]))
            continue
        if not D or "err" in D:
            res[n]["d"] = dict(err=(D or {}).get("err", "no data")); continue
        if n == 21:
            reduced = "prefers-reduced-motion" in css
            kill = reduced_motion_kill(css)
            if reduced and kill:
                why = (("The prefers-reduced-motion rule switches EVERYTHING off (*{animation:none; transition:none}), so useful state feedback disappears too."))
            elif reduced: why = ("The reduced-motion setting is handled selectively (prefers-reduced-motion).")
            elif D["animated"]: why = ((f"The page has {D['animated']} animated elements but no prefers-reduced-motion rule."))
            else: why = ("The page has no animations.")
            st = "ok" if ((reduced and not kill) or D["animated"] == 0) else "fail"
            res[n].update(status=st, d=dict(animated=D["animated"], why=why), marks=D["marks"], special=None); continue
        fn = globals()[f"v{n}"]
        try:
            st, d = (fn(D, cdata, lang) if n in (8, 22, 53, 54) else fn(D, cdata))
        except Exception as e:
            st, d = "na", dict(err=str(e))
        res[n].update(status=st, d=d, marks=D.get("marks", []), special=("hover" if n == 23 else None))
    return res


# Page sections used to pin a screenshot crop (2026-11-13): the BEFORE crop is stored relative to the section it sits in,
# and the AFTER run cuts exactly the same part of the same section, so the two screenshots are comparable.
SECTIONS_JS = r"""
() => { const top = e => e.getBoundingClientRect().top + scrollY;
  const secs = [...document.querySelectorAll('header, section, footer')].filter(s => !s.parentElement.closest('section') && s.getBoundingClientRect().height > 20)
    .sort((a, b) => top(a) - top(b));
  return secs.map((s, i) => ({ i, id: s.id || '', tag: s.tagName.toLowerCase(), cls: (typeof s.className === 'string' ? s.className.trim().split(/\s+/)[0] : '') || '',
    top: Math.round(top(s)), h: Math.round(s.getBoundingClientRect().height) })); }
"""


def section_at(secs, y):
    """The page section that holds y (page coordinates); in a gap between sections the nearest one above;
    None only above the first section (the crop is then pinned to the page top)."""
    hit = [s for s in secs if s["top"] <= y < s["top"] + s["h"]] or [s for s in secs if s["top"] <= y]
    return hit[-1] if hit else None


def find_section(secs, key):
    """Same section in another render: by id, then tag + first class + order among equals, then plain order."""
    if not key: return None
    if key.get("id"):
        for s in secs:
            if s["id"] == key["id"]: return s
    same = [s for s in secs if s["tag"] == key.get("tag") and s["cls"] == key.get("cls")]
    if 0 <= key.get("k", -1) < len(same): return same[key["k"]]
    return secs[key["i"]] if 0 <= key.get("i", -1) < len(secs) else None


def shoot(browser, url, r, lang, outdir):
    """One annotated screenshot for point r; returns (image file name or None, crop dict for the next comparison)."""
    marks = list(r["marks"] or [])
    crop_prev = r.get("crop")   # BEFORE crop: cut the same part of the same section
    if not marks and not r.get("ref_sels") and not crop_prev: return None, None   # nothing to frame now, nothing before
    n, mobile = r["n"], r["mobile"]
    ctx = new_ctx(browser, mobile, reduce=(n == 21)); pg = ctx.new_page(); prep(pg, url)
    sp = r["special"]; vp = pg.viewport_size; vw, vh = vp["width"], vp["height"]
    anchor = marks[0]["r"] if marks else None
    refs = []
    if r.get("ref_sels"):   # before/after: frame the same elements the earlier screenshot was built around
        try: refs = pg.evaluate("""ss => ss.map(s => { const e = document.querySelector(s); if (!e) return null; const b = e.getBoundingClientRect();
            return { sel: s, r: [Math.round(b.left + scrollX), Math.round(b.top + scrollY), Math.round(b.width), Math.round(b.height)] }; }).filter(Boolean)""", r["ref_sels"])
        except Exception: refs = []
    if refs:
        ref = refs[0]["r"]; anchor = ref
        have = {m.get("sel") for m in marks}
        marks = sorted(marks, key=lambda m: abs(m["r"][1] - ref[1]))
        for q in refs:   # elements flagged before and fixed (or no longer flagged) now: same box in green
            if q["sel"] not in have: marks.append(dict(c="g", r=q["r"], v="", f=False, sel=q["sel"]))
        marks.sort(key=lambda m: (m["r"][1] != ref[1], abs(m["r"][1] - ref[1])))
    if not marks and not crop_prev:   # fixed element no longer on the page, nothing to mark, no earlier crop: no after shot
        ctx.close(); return None, None
    fs = 13 if mobile else 18
    pad = 24; top = fs + 22
    docH = pg.evaluate("document.documentElement.scrollHeight")
    if marks:
        # window of marks near the first one so the crop stays readable
        if anchor is None: anchor = marks[0]["r"]
        inc = [m for m in marks if anchor[1] - 150 <= m["r"][1] <= anchor[1] + 520] or marks[:1]
        x0 = min(m["r"][0] for m in inc); y0 = min(m["r"][1] for m in inc)
        x1 = max(m["r"][0] + m["r"][2] for m in inc); y1 = max(m["r"][1] + m["r"][3] for m in inc)
        if mobile: x0, x1 = 0, vw
        else:
            x0, x1 = max(0, x0 - pad), min(vw, x1 + pad)
            if x1 - x0 < 560:
                c = (x0 + x1) / 2; x0, x1 = max(0, c - 280), min(vw, c + 280)
        y0 = max(0, y0 - top - 6); y1 = y1 + pad
        cap = 760 if mobile else 640
        if y1 - y0 > cap: y1 = y0 + cap
        if y1 - y0 < 110: y1 = y0 + 110
    secs = pg.evaluate(SECTIONS_JS)
    if crop_prev and sp != "scroll1200":   # AFTER: the same part of the same section as the BEFORE screenshot
        s = find_section(secs, crop_prev.get("sec"))
        base = s["top"] if s else 0
        x0 = max(0, min(crop_prev["dx"], vw - 50)); x1 = min(vw, x0 + crop_prev["w"])
        h = min(crop_prev["h"], docH)
        y0 = max(0, min(base + crop_prev["dy"], docH - h)); y1 = y0 + h   # page got shorter: shift up, keep the same size
        if not marks: anchor = [x0, y0, x1 - x0, y1 - y0]
    x0, y0 = int(round(x0)), int(round(y0)); x1, y1 = x0 + int(round(x1 - x0)), y0 + int(round(y1 - y0))   # whole pixels: before/after cut identically
    if y1 > docH:   # never store a crop the browser would silently cut at the page end: shift it up, keep the size
        hh = min(y1 - y0, docH); y0 = max(0, docH - hh); y1 = y0 + hh
    scroll = 0
    if sp == "scroll1200": scroll = 1200
    elif sp == "hover" or (sp and sp[0] == "focus"): scroll = max(0, int(y0 - 40))
    if scroll:
        pg.evaluate(f"window.scrollTo(0,{scroll})"); pg.wait_for_timeout(500)
    if sp == "scroll1200":   # show a bar that is slid off-screen until the page scrolls
        pg.evaluate("""() => document.querySelectorAll('body *').forEach(e => { const s = getComputedStyle(e);
            if (s.position === 'fixed' && s.bottom === '0px' && s.display !== 'none' && e.getBoundingClientRect().width >= innerWidth * .8)
              { e.style.transition = 'none'; e.style.transform = 'none'; e.style.opacity = '1'; e.style.visibility = 'visible'; } })""")
        pg.wait_for_timeout(200)
    if sp == "hover":
        pg.mouse.move(anchor[0] + anchor[2] / 2, anchor[1] - scroll + anchor[3] / 2); pg.wait_for_timeout(700)
    if sp and sp[0] == "focus":
        pg.evaluate(FOCUS_ASSIGN_JS)
        for _ in range(40):
            pg.keyboard.press("Tab")
            cur = pg.evaluate("document.activeElement && document.activeElement.dataset.glid")
            if cur is not None and int(cur) == sp[1]: break
        pg.wait_for_timeout(300)
    fmtm = MARK.get(n)
    labeled = []
    for m in marks:
        v = m.get("v", "")
        t = (fmtm if fmtm else v)
        labeled.append(dict(m, label=t))
    pg.evaluate(OVERLAY_JS, {"marks": labeled, "fs": fs})
    png = outdir / "img" / f"p{n:02d}.png"
    if sp:   # viewport screenshot (fixed bars, hover and focus state need the real viewport)
        clip = dict(x=x0, y=max(0, y0 - scroll), width=x1 - x0, height=min(vh - max(0, y0 - scroll), y1 - y0))
        if sp == "scroll1200" and crop_prev and crop_prev.get("vclip"): clip = dict(crop_prev["vclip"])   # same viewport frame
        pg.screenshot(path=str(png), clip=clip)
    else:
        clip = None
        pg.screenshot(path=str(png), clip=dict(x=x0, y=y0, width=x1 - x0, height=y1 - y0), full_page=True)
    # remember where this crop sits inside its page section, so the next (after-fix) run cuts the same part
    s = section_at(secs, y0)
    crop = dict(sec=(dict(id=s["id"], tag=s["tag"], cls=s["cls"], i=s["i"],
                          k=[q["i"] for q in secs if q["tag"] == s["tag"] and q["cls"] == s["cls"]].index(s["i"])) if s else None),
                dx=round(x0), dy=round(y0 - (s["top"] if s else 0)), w=round(x1 - x0), h=round(y1 - y0), vclip=clip)
    ctx.close()
    jpg = png.with_suffix(".jpg")
    Image.open(png).convert("RGB").save(jpg, quality=82)
    png.unlink()
    return jpg.name, crop


# ---------------------------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------------------------
EXTRA_CSS = """
h1{font-size:23pt}
.cover-in{margin-top:6mm;gap:5mm}
.kpis4{display:grid;grid-template-columns:repeat(4,1fr);gap:3mm}
.k{padding:4mm}.k b{display:block;font-size:17pt;font-weight:700;color:#fff;margin-bottom:1mm}.k b em{font-style:normal;color:#4ade80}.k b em.r{color:#ff6b9a}.k b em.a{color:#f5c26b}.k b em.n{color:#a7abb8}
.k span{font-size:7.8pt;line-height:1.4;color:#d0d3db}
.list{display:grid;grid-template-columns:1fr 1fr;gap:1.6mm 6mm;padding:5mm}
.li{display:flex;align-items:center;gap:2.5mm;font-size:8.6pt;color:#e6e8ec}
.li i{flex:0 0 auto;width:6mm;font-style:normal;color:var(--muted);font-variant-numeric:tabular-nums}
.li span{flex:1}
.chip2{flex:0 0 auto;padding:.8mm 2.4mm;border-radius:99px;font-size:7pt;font-weight:700;white-space:nowrap}
.chip2.ok{background:rgba(34,197,94,.18);color:#86efac}.chip2.exc{background:rgba(240,180,76,.18);color:#f5c26b}
.chip2.fail{background:rgba(255,45,135,.2);color:#ff8fb8}.chip2.na{background:rgba(255,255,255,.1);color:#a7abb8}
.pt{padding:4.5mm 5mm;display:flex;flex-direction:column;gap:2.4mm}
.pt-h{display:flex;justify-content:space-between;align-items:baseline;gap:4mm}
.pt-h h3{font-size:12pt;color:#fff}
.pt p{font-size:9pt;line-height:1.45;color:#d6d9e0}
.pt p em.was{font-style:normal;color:#ff8d93}
.fixb{font-size:8.6pt;line-height:1.45;color:#ffd0e2;background:rgba(255,45,135,.12);border-left:1.2mm solid #ff2d87;border-radius:1.5mm;padding:2mm 3mm}
.fixb b{color:#fff}
.shots{display:flex;gap:3mm;justify-content:center;align-items:flex-start}
.sh{display:flex;flex-direction:column;gap:1.2mm;align-items:center;min-width:0}
.sh span{font-size:7.4pt;font-weight:700;letter-spacing:.06em;text-transform:uppercase;color:var(--muted)}
.sh img{display:block;max-width:100%;height:auto;border-radius:2.5mm;border:1px solid rgba(255,255,255,.18)}
.src{font-size:7.6pt;line-height:1.4;color:var(--muted)}
.pt p.why{font-size:8.4pt;line-height:1.45;color:#b9c3d6}.pt p.why b{color:#fff}
.list.dense{grid-template-columns:1fr 1fr 1fr;gap:1.1mm 4mm;padding:4mm}
.list.dense .li{font-size:7.2pt;gap:1.6mm}.list.dense .li i{width:5mm}.list.dense .chip2{font-size:6.2pt;padding:.5mm 1.8mm}
em.whyfx{font-style:normal;color:#b9c3d6;font-size:8pt}
.src a{color:#9fc5ff;text-decoration:none}
.fixes{padding:5mm;display:flex;flex-direction:column;gap:3mm}
.fixes h3{font-size:11pt;color:#fff;margin-top:1mm}
.fx{display:flex;gap:3mm;font-size:8.6pt;line-height:1.45;color:#e6e8ec}
.fx i{flex:0 0 7mm;font-style:normal;color:var(--muted);font-variant-numeric:tabular-nums}
.fx b{color:#fff;font-weight:600}
"""
INNER_W = 170.0
PAGE_BUDGET = 256.0


def img_size(imgdir, name):
    with Image.open(imgdir / name) as im: return im.size


def shots_html(imgdir, name, maxh):
    w, h = img_size(imgdir, name)
    dh = min(maxh, INNER_W * h / w); dw = dh * w / h
    return f'<div class="shots"><div class="sh"><img src="file://{imgdir / name}" style="width:{dw:.1f}mm;height:{dh:.1f}mm" alt=""></div></div>', dh


def pair_html(imgdir, before, after, maxh, ui):
    """Before and after screenshots side by side, each with a caption."""
    share = (INNER_W - 3.0) / 2
    parts, hmax = [], 0
    for cap, name in ((ui["was"], before), (ui["now"], after)):
        w, h = img_size(imgdir, name)
        dh = min(maxh, share * h / w); dw = dh * w / h
        hmax = max(hmax, dh + 4)
        parts.append(f'<div class="sh"><span>{cap}</span><img src="file://{imgdir / name}" style="width:{dw:.1f}mm;height:{dh:.1f}mm" alt=""></div>')
    return f'<div class="shots">{"".join(parts)}</div>', hmax


def src_html(n, lang):
    name, url = SRC[SOURCES[n]]
    return f'{name}: <a href="{url}">{url}</a>' if url else name


def point_html(p, imgdir, ui, lang):
    chip = f'<b class="chip2 {p["status"]}">{ui["chip"][p["status"]]}</b>'
    body, hi = ("", 0)
    if p.get("img") and p.get("img_before"): body, hi = pair_html(imgdir, p["img_before"], p["img"], 62 if p["mobile"] else 42, ui)
    elif p.get("img"): body, hi = shots_html(imgdir, p["img"], 62 if p["mobile"] else 50)
    fixb = f'<div class="fixb"><b>{ui["fix"]}</b> {p["fix"]}</div>' if p["status"] == "fail" else ""
    was = f' <em class="was">{ui["was"]}: {p["was"]}.</em>' if p.get("was") else ""
    why = WHY[lang].get(p["id"], "")
    whyb = f'<p class="why"><b>{ui["why"]}</b> {why}</p>' if why else ""
    html = (f'<div class="glass pt"><div class="pt-h"><h3>{p["n"]}. {p["title"]}</h3>{chip}</div><p>{p["text"]}{was}</p>{whyb}{fixb}{body}'
            f'<div class="src">{ui["source"]}: {src_html(p["id"], lang)}</div></div>')
    lines = max(1, round(len(p["text"]) / 105 + .4)); fl = max(1, round(len(p["fix"]) / 100 + .4)) if fixb else 0
    wl = max(1, round(len(why) / 110 + .4)) if why else 0
    return html, 9 + 7 + lines * 4.6 + wl * 4.2 + 1.5 + (fl * 4.4 + 5 if fixb else 0) + hi + 5 + 3 * 2.4


def build_css(brand):
    pl = "#" + "".join(f"{round(int(brand['primary'][i:i+2], 16) * .65 + 255 * .35):02x}" for i in (1, 3, 5))
    return (BASE_CSS + EXTRA_CSS).replace("__P__", brand["primary"]).replace("__PL__", pl).replace("__BG__", brand["bg"]).replace("__BG2__", brand["bg2"]) \
        .replace("__S__", brand["secondary"]).replace("__PRGB__", hex_rgb(brand["primary"])).replace("__SRGB__", hex_rgb(brand["secondary"])).replace("__FONT__", "Inter")


def doc_html(body, title, brand, lang):
    return (f'<!doctype html><html lang="{lang}"><head><meta charset="utf-8"><title>{title}</title>'
            '<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap&subset=cyrillic" rel="stylesheet">'
            f'<style>{build_css(brand)}</style></head><body>{body}</body></html>')


def build_pdf(points, outdir, lang, title, brand, logo, pdf_path):
    ui = UI[lang]; imgdir = outdir / "img"
    count = {s: sum(1 for p in points if p["status"] == s) for s in ("ok", "fail", "exc", "na")}
    logo_html = f'<img class="logo" src="file://{logo}" alt="">' if logo and pathlib.Path(logo).exists() else f'<b>{AGENCY_NAME}</b>'
    foot = datetime.date.today().isoformat()
    pages = []

    def page(inner):
        pages.append(f'<section class="page"><div class="head">{logo_html}<span>{ui["head"]}</span></div>{inner}'
                     f'<div class="foot"><span>{foot}</span><span>{len(pages) + 1}</span></div></section>')

    items = "".join(f'<div class="li"><i>{p["n"]}.</i><span>{p["title"]}</span><b class="chip2 {p["status"]}">{ui["short"][p["status"]]}</b></div>' for p in points)
    dense = len(points) > 30   # 2026-11-13: 61 points no longer fit two columns on the cover
    had_before = any(p.get("before_status") for p in points)
    b_ok = sum(1 for p in points if p.get("before_status") in ("ok", "exc")); b_fail = sum(1 for p in points if p.get("before_status") == "fail")
    before_line = (f'<p class="lead" style="font-size:10pt;margin-top:-2mm"><b>{ui["was"]}:</b> {b_ok} / {N_POINTS} {ui["k_ok"]}, {b_fail} {ui["k_fail"]}. '
                   f'<b>{ui["now"]}:</b> {count["ok"] + count["exc"]} / {N_POINTS} {ui["k_ok"]}, {count["fail"]} {ui["k_fail"]}.</p>') if had_before else ""
    head1 = (f'<span class="accent">{title}</span><br>{ui["h_all"]}' if not count["fail"] else f'<span class="accent">{title}</span><br>{ui["h_some"].format(ok=count["ok"] + count["exc"], total=N_POINTS)}')
    page(f'''<div class="cover-in" style="display:flex;flex-direction:column">
<div class="eyebrow">{ui["eyebrow"]}</div><h1>{head1}</h1>
<p class="lead" style="font-size:10pt">{ui["lead"].format(total=N_POINTS)}</p>{before_line}
<div class="kpis4">
<div class="glass k"><b><em>{count["ok"]}</em> / {N_POINTS}</b><span>{ui["k_ok"]}</span></div>
<div class="glass k"><b><em class="r">{count["fail"]}</em></b><span>{ui["k_fail"]}</span></div>
<div class="glass k"><b><em class="a">{count["exc"]}</em></b><span>{ui["k_exc"]}</span></div>
<div class="glass k"><b><em class="n">{count["na"]}</em></b><span>{ui["k_na"]}</span></div>
</div><div class="glass list{' dense' if dense else ''}">{items}</div></div>''')

    fails = [p for p in points if p["status"] == "fail"]
    if fails:
        blocks = ""
        for pr in ("high", "med", "low"):
            rows = [p for p in fails if PRIORITY[p["id"]] == pr]
            if rows:
                blocks += f'<h3>{ui["pri"][pr]}</h3>' + "".join(f'<div class="fx"><i>{p["n"]}.</i><span><b>{p["title"]}.</b> {p["fix"]}</span></div>' for p in rows)
        page(f'<h2>{ui["fixes"]}</h2><div class="glass fixes">{blocks}</div>')
    fixed = [p for p in points if p.get("before_status") == "fail" and p["status"] in ("ok", "exc")]
    if fixed:   # before/after report: what was changed and why it is best practice
        for k in range(0, len(fixed), 8):
            rows = "".join(f'<div class="fx"><i>{p["n"]}.</i><span><b>{p["title"]}.</b> {p.get("before_fix") or ""}'
                           f'<br><em class="whyfx">{ui["why"]} {WHY[lang].get(p["id"], "")}</em></span></div>' for p in fixed[k:k + 8])
            page(f'<h2>{ui["changed"]}{" (" + str(k // 8 + 1) + ")" if len(fixed) > 8 else ""}</h2><div class="glass fixes">{rows}</div>')

    cards = [(p, *point_html(p, imgdir, ui, lang)) for p in points]
    return cards, page, pages, doc_html, ui


def render(cards_fn, outdir, lang, title, brand, logo, pdf_path, points, qa):
    from playwright.sync_api import sync_playwright
    ui = UI[lang]; imgdir = outdir / "img"
    cards, page, pages, _doc, _ui = build_pdf(points, outdir, lang, title, brand, logo, pdf_path)
    html_path = pdf_path.with_suffix(".html")

    def make_doc(heights=None):
        base = len(pages)
        cur, used = [], 0.0
        for p, html, h in cards:
            if heights: h = heights[p["n"]]
            gap = 5 if cur else 0
            if cur and used + gap + h > PAGE_BUDGET:
                page("".join(cur)); cur, used, gap = [], 0.0, 0
            cur.append(html); used += gap + h
        if cur: page("".join(cur))
        doc = doc_html("".join(pages), title, brand, lang)
        del pages[base:]
        return doc.replace("—", "-").replace("–", "-")

    with sync_playwright() as pw:
        br = pw.chromium.launch(); pg = br.new_page()
        mpath = outdir / "_measure.html"
        mpath.write_text(doc_html('<div style="width:180mm;display:flex;flex-direction:column;gap:5mm">' + "".join(h for _, h, _ in cards) + "</div>", title, brand, lang), encoding="utf-8")
        pg.goto("file://" + str(mpath), wait_until="networkidle"); pg.evaluate("document.fonts.ready")
        hs = pg.evaluate("[...document.querySelectorAll('.pt')].map(e=>e.getBoundingClientRect().height/3.7795)")
        mpath.unlink()
        heights = {p["n"]: h for (p, _, _), h in zip(cards, hs)}
        html_path.write_text(make_doc(heights), encoding="utf-8")
        pg.goto("file://" + str(html_path), wait_until="networkidle"); pg.evaluate("document.fonts.ready")
        over = pg.evaluate("""[...document.querySelectorAll('.page')].map((p,i)=>{const r=p.getBoundingClientRect();
          const m=Math.max(...[...p.children].filter(c=>!c.classList.contains('foot')).map(c=>c.getBoundingClientRect().bottom));
          return [i+1, Math.round(r.bottom-m)]}).filter(x=>x[1]<30)""")
        broken = pg.evaluate("[...document.images].filter(i=>!i.naturalWidth).map(i=>i.src)")
        pg.pdf(path=str(pdf_path), format="A4", print_background=True, prefer_css_page_size=True)
        br.close()
    if broken: print("WARNING broken images:", broken)
    if over: print("WARNING pages with content touching the footer (page, px left):", over)
    print("PDF:", pdf_path, f"({pdf_path.stat().st_size / 1e6:.1f} MB)")
    if qa:
        qd = outdir / "qa"; qd.mkdir(exist_ok=True)
        with tempfile.NamedTemporaryFile("w", suffix=".swift", delete=False) as f: f.write(SWIFT_QA)
        r = subprocess.run(["swift", f.name, str(pdf_path), str(qd)], capture_output=True, text=True)
        print(f"QA: {r.stdout.strip()} pages rendered to {qd}/pageN.png" if r.returncode == 0 else "QA render failed: " + r.stderr[-300:])


def console_report(points, lang):
    ui = UI[lang]
    fails = [p for p in points if p["status"] == "fail"]
    print("\n=== " + ui["fixes"].upper() + " ===")
    if not fails: print(ui["nofix"])
    for pr in ("high", "med", "low"):
        rows = [p for p in fails if PRIORITY[p["id"]] == pr]
        if rows:
            print(f"\n{ui['pri'][pr]}")
            for p in rows: print(f"  {p['n']:>2}. {p['title']}\n      {p['text']}\n      -> {p['fix']}")
    print(f"\n=== {N_POINTS} / {N_POINTS} ===")
    mark = dict(ok="PASS", fail="FAIL", exc="EXCEPTION", na="N/A")
    assert len(points) == N_POINTS, f"expected {N_POINTS} points, got {len(points)}"
    for p in points: print(f"{p['n']:>2}. {mark[p['status']]:<9} {p['title']}\n    {p['text']}")
    c = {s: sum(1 for p in points if p["status"] == s) for s in mark}
    print(f"\nPASS {c['ok']} | FAIL {c['fail']} | EXCEPTION {c['exc']} | N/A {c['na']}")


def write_md(points, path, lang, title, url):
    ui = UI[lang]; mark = dict(ok="PASS", fail="FAIL", exc="EXCEPTION", na="N/A")
    L = [f"# {ui['head']}: {title}", "", url, ""]
    fails = [p for p in points if p["status"] == "fail"]
    L.append(f"## {ui['fixes']}")
    for pr in ("high", "med", "low"):
        rows = [p for p in fails if PRIORITY[p["id"]] == pr]
        if rows:
            L += ["", f"**{ui['pri'][pr]}**"] + [f"- {p['n']}. {p['title']}: {p['fix']}" for p in rows]
    if not fails: L.append(ui["nofix"])
    L += ["", f"## {N_POINTS} / {N_POINTS}", "", "| # | Result | Point | Finding | Why |", "|---|---|---|---|---|"]
    L += [f"| {p['n']} | {mark[p['status']]} | {p['title']} | {p['text']} | {WHY[lang].get(p['id'], '')} |" for p in points]
    path.write_text("\n".join(L).replace("—", "-").replace("–", "-") + "\n", encoding="utf-8")


def slugify(url):
    u = urllib.parse.urlparse(url)
    s = (u.hostname or "") + u.path if u.scheme != "file" else pathlib.Path(u.path).parent.name + "-" + pathlib.Path(u.path).stem
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-") or "page"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("target", help="https://... URL or a local .html path")
    ap.add_argument("--client"); ap.add_argument("--name")
    ap.add_argument("--exceptions", default=""); ap.add_argument("--title"); ap.add_argument("--logo")
    ap.add_argument("--primary", default=COLORS.get("accent", "#3E5CE7")); ap.add_argument("--no-pdf", action="store_true"); ap.add_argument("--no-qa", action="store_true")
    ap.add_argument("--before", help="audit.json of an earlier run (e.g. guidelines/<name>/audit.prev.json): adds 'Before: <value>' to points whose value changed")
    a = ap.parse_args()

    url = a.target if re.match(r"^(https?|file)://", a.target) else pathlib.Path(a.target).resolve().as_uri()
    name = a.name or slugify(url)
    if a.client:
        if not (WS / "clients" / a.client).is_dir(): sys.exit(f"ERROR: no folder clients/{a.client}")
        outdir = WS / "clients" / a.client / "reports" / "guidelines" / name
    else:
        outdir = WS / "guidelines" / name
    (outdir / "img").mkdir(parents=True, exist_ok=True)
    # keep the previous result for a before/after comparison (--before .../audit.prev.json)
    if (outdir / "audit.json").exists() and not (a.before and pathlib.Path(a.before).resolve() == (outdir / "audit.json").resolve()):
        (outdir / "audit.json").replace(outdir / "audit.prev.json")
    before = {p.get("id", p["n"]): p for p in json.loads(pathlib.Path(a.before).read_text(encoding="utf-8"))["points"]} if a.before else {}
    # keep the previous screenshots for the before/after pairs (img.prev), then clear the folder
    prev_img = outdir / "img.prev"
    cur = list((outdir / "img").glob("p[0-9][0-9].jpg"))
    if cur:
        shutil.rmtree(prev_img, ignore_errors=True); prev_img.mkdir()
        for f in cur: f.replace(prev_img / f.name)
    for old in (outdir / "img").glob("p*.jpg"): old.unlink()
    bj = pathlib.Path(a.before).resolve() if a.before else None
    before_img = (prev_img if bj.parent == outdir.resolve() else bj.parent / "img") if bj else None
    exceptions = {ACTIVE[int(x) - 1] for x in a.exceptions.split(",") if x.strip().isdigit() and 1 <= int(x) <= N_POINTS}   # numbers as shown in the report
    u = urllib.parse.urlparse(url)
    title = a.title or ((u.hostname or name) + (u.path.rstrip("/") if u.path not in ("", "/") and u.scheme != "file" else ""))
    lang = "en"   # report is English only
    brand = dict(primary=a.primary, secondary="#2e8bff", bg="#0b1020", bg2="#141a2e")
    logo = str(pathlib.Path(a.logo).resolve()) if a.logo else str(LOGO_PATH)   # 2026-11-13: relative --logo rendered as a broken image

    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        br = pw.chromium.launch(args=host_args(url))
        print("Measuring", url)
        res = measure(br, url, lang)
        points = []
        for n in ACTIVE:
            r = res[n]; st = r["status"]
            if st == "fail" and n in exceptions: st = "exc"
            t = TXT[lang][n]; d = r["d"]
            try:
                if st == "na" or "err" in d:
                    title_n = t[0].format(**{k: "-" for k in re.findall(r"{(\w+)}", t[0])})
                    text, fixt = NA_TEXT[lang] + (f" ({d['err']})" if "err" in d else ""), ""
                    st = "na"
                else:
                    title_n = t[0].format(**d)
                    text = (t[1] if st in ("ok", "exc") and r["status"] == "ok" else t[2]).format(**d)
                    fixt = t[3]
            except KeyError as e:
                title_n, text, fixt = t[0], f"(format error {e})", t[3]
            b = before.get(n); was = None
            if b and b["status"] != "na" and st != "na" and b["title"] != title_n:
                was = b["title"].split(":", 1)[1].strip() if ":" in b["title"] else None
            points.append(dict(id=n, n=DISP[n], title=title_n, status=st, text=text, fix=fixt, mobile=r["mobile"], d=d, marks=r["marks"], img=None, was=was,
                               before_status=(before.get(n) or {}).get("status"), before_fix=(before.get(n) or {}).get("fix")))
        print("Screenshots...")
        for p in points:
            if p["status"] == "na": continue
            ref_sels = (before.get(p["id"]) or {}).get("anchors")
            crop_prev = (before.get(p["id"]) or {}).get("crop")   # same section + same part as the BEFORE screenshot
            try: p["img"], p["crop"] = shoot(br, url, dict(n=p["id"], mobile=p["mobile"], marks=res[p["id"]]["marks"], special=res[p["id"]]["special"],
                                                         ref_sels=ref_sels, crop=crop_prev), lang, outdir)
            except Exception as e: print(f"  point {p['n']}: screenshot failed ({e})")
        br.close()
        if before_img:   # the earlier screenshot of the same point goes next to the new one
            for p in points:
                src = before_img / f"p{p['id']:02d}.jpg"
                if p["img"] and p["id"] in before and before[p["id"]]["status"] != "na" and src.exists():
                    shutil.copy(src, outdir / "img" / f"p{p['id']:02d}_before.jpg"); p["img_before"] = f"p{p['id']:02d}_before.jpg"

    (outdir / "audit.json").write_text(json.dumps(dict(url=url, date=datetime.date.today().isoformat(), points=[
        dict(id=p["id"], n=p["n"], status=p["status"], title=p["title"], text=p["text"], fix=p["fix"], data=p["d"], was=p.get("was"),
        anchors=[m["sel"] for m in p["marks"] if m.get("sel")][:10], crop=p.get("crop")) for p in points]), ensure_ascii=False, indent=1), encoding="utf-8")
    write_md(points, outdir / "report.md", lang, title, url)
    console_report(points, lang)
    if not a.no_pdf:
        render(None, outdir, lang, title, brand, logo, outdir / f"{name} - guidelines.pdf", points, not a.no_qa)
    print("Folder:", outdir)


if __name__ == "__main__":
    main()
