---
target: dashboard
total_score: 12
max_score: 40
na_heuristics: 
p0_count: 1
p1_count: 3
timestamp: 2026-08-30T15-02-48Z
slug: templates-dashboard-html
---
**Method: dual-agent** (A: design review, isolated · B: detector + browser evidence, isolated). Deviation: B returned before A, so detector evidence entered the parent context before the design judgment. A's review was itself isolated.

## Design Health Score

| # | Heuristic | Score | Key issue |
|---|---|---|---|
| 1 | Visibility of system status | 1 | No freshness or degradation marker. The `except` at `app.py:6074` re-renders this template with zeros. |
| 2 | Match with the real world | 1 | "Tendencia · últimos 12 meses" (`dashboard.html:189`) charts 26 weeks (`app.py:5769`). Six English acronyms in a Spanish UI. |
| 3 | User control and freedom | 2 | Tabs and swipe work both ways with no traps, but no period control and no drill-down. |
| 4 | Consistency and standards | 1 | Active tab blue at 1440px, white at 390px; `524` here vs `524.32` in /pedidos; "Pendientes" carries two values. |
| 5 | Error prevention | 2 | Nothing destructive lives here, but `preventDefault()` at `:531` hijacks diagonal drags. |
| 6 | Recognition over recall | 1 | OTD/OFR/POR/CE/LT/PED demand recall; "OFR 100%" appears on Ventas before OFR is defined on Servicio. |
| 7 | Flexibility and efficiency | 1 | Zero accelerators: no drill-down, filters, period switch, or keyboard tab navigation. |
| 8 | Aesthetic and minimalist design | 2 | The fold is genuinely good; undercut by a one-slice donut and six rings repeating the number beside them. |
| 9 | Error recognition / recovery | 0 | No error state exists. The catastrophic path is pixel-identical to a quiet Monday. |
| 10 | Help and documentation | 1 | The only help is a 9px English gloss at 2.56:1. No threshold is explained. |
| **Total** | | **12/40** | **Poor — major UX overhaul required** |

The score measures whether the surface does its job, not taste. Three measured facts: the body has zero interactive targets, it cannot signal its own failure, and it prints two different numbers for the same word in one session.

## Design Specificity Verdict

**Category-interchangeable.** Swap "XCG" for "USD" and four tab labels and this ships unchanged as a CRM or a gym dashboard. Generic 2021 dashboard kit: segmented pills, 44px progress rings, 2x2 KPI grid, trend line, status donut, top-N lists with coloured rank bars. The business's actual texture — cajas vs kg, the pendiente→preparado→facturado warehouse pipeline, the OB/exportación split, the XCG/USD divide, the ≤2-day SLA that defines "vencido" — is absent or reduced to a decimal. Cajas and kg appear once, buried in `rank-meta` (`:295-297`).

The damning evidence is internal: sibling screens ARE specific. `/clientes` says "63 días sin comprar · su ritmo: 16 d" with an action on the row; `/pedidos` says "PED-31 · PENDIENTE · entrega 31/08 · 524.32 XCG" with a state rail and a Preparar button. The dashboard shares none of their language — and it is the home tab.

**Deterministic scan.** Template: exit 0, zero findings (it carries almost no inline styling). Stylesheets: 7 findings.
- **4 slop findings are FALSE POSITIVES — `static/dashboard_pro.css` is never served.** Verified: `grep -rn "dashboard_pro" templates/ static/js/ app.py` returns nothing. 614 lines no user has seen. Delete, don't redesign.
- **3 true positives**, all `layout-transition`: `transition: height` on `.panels-viewport` (`dashboard_inline.css:27`), `transition: width 600ms` on `.rank-bar-fill` (`:365`) and `.estado-bar-fill` (`:469`). Fix with `transform: scaleX()` + `transform-origin:left`.
- `dashboard_light.css` and `dashboard_snap.css`: zero findings.

**Overlay.** Injection succeeded locally — itself a finding: Talisman mounts only when `FLASK_ENV == "production"` (`app.py:371`), so the dev server has no CSP and executed an inline script plus a cross-origin one. **This run does not verify production CSP.** The Impeccable script draws no visible overlay; it only installs a JS API — there is nothing to look at in the browser. Its 390px scan: 60 findings, 38 unique — `low-contrast` x24, `undersized-ui-text` x20, `bounce-easing` x5, `layout-transition` x3.

## Overall Impression

A beautifully executed mockup that was never wired to the product. The fold is good; everything below is a poster — ~30 numbers with no baseline, none tappable, across four panels discoverable only by an unsignposted swipe. The biggest opportunity is not aesthetic: `dashboard()` already computes what is needed and throws it away. `pedidos_operativos` (`app.py:5895`) carries per-order "Vencido 3d" / "Límite hoy" / "En tiempo" and is never referenced. Twelve context variables are computed per load with zero template hits.

## What's Working

1. **The data-derived headline (`:101-108`).** A small state machine — no sales / overdue / pending / all clear. The source comment records that it replaced a static "Tu semana va bien" that lied. Authored judgment: an interface willing to lead with bad news.
2. **The `meses_es` array (`:96-97`).** Hardcoded because the dyno locale rendered "16 de August, 2026". The precise, unglamorous detail that separates a real product from a template.
3. **The first-second read of the fold.** 27px/800 near-black with a small blue kicker; at 390px the headline reads in well under a second. Sound typographic instinct.

## Priority Issues

### [P0] The screen cannot say it is broken — and the hero puts invoicing ahead of urgency
`app.py:6074` catches any exception and re-renders this template with `fallback_data` (all zeros). The hero then prints "Todavía no hay ventas este mes." — a confident factual claim. Worse, `:104-108` orders `not ventas_mes_v` BEFORE `pedidos_vencidos_v`, and `ventas_mes` is fed from QuickBooks (`app.py:1370`+), not local orders. Verified locally: 12 August orders worth XCG 2,953 exist while the screen says there were no sales.
**Why:** a salesperson cannot distinguish "the DB is down" from "nobody bought", and will act on the second. A QBO outage erases the overdue headline. No banner, no timestamp, no retry; and `otd_rate: 0` draws a zero-length arc so even the state colour is invisible.
**Fix:** pass `degradado=True` in `fallback_data`, render an amber bar above the hero, suppress the derived headline when degraded, reorder `:104-108` so vencidos beats absent sales, and add `datos al {{hh:mm}}` under `.hero-sub`.
**Command:** `/impeccable harden templates/dashboard.html`

### [P1] Nothing in the body is clickable: a poster, not an Operate surface
Measured live: 10 `.kpi` cards, 5 `.act-row` rows and every `.rank` entry are plain `<div>`s (`href: null`, `cursor: auto`). The whole body offers two links and four tabs.
**Why:** the job is "check state, then act on orders". The user reads "19 pendientes", taps it, nothing happens, then has to re-find it in `/pedidos`. On iPhone, all day, that is one tap vs a five-step re-orientation. `app.py:6083`'s own comment calls `/pedidos?estado=pendiente` "el aviso del dashboard".
**Fix:** wrap `.act-row` (`:363-378`) in `<a href="{{ url_for('detalles_pedido', pedido_id=pedido.id) }}">`; Pendientes card (`:176-184`) → `/pedidos?estado=pendiente`; vencidos sub-line its own link; each `.rank` client row → that client. Add `cursor:pointer`, hover/active, chevron.
**Command:** `/impeccable shape templates/dashboard.html`

### [P1] The same word carries two numbers, and the chart mislabels its own range
"Pendientes" = 19 on the KPI card (`:181`, ~6-month window at `app.py:5528`) and 12 in the donut legend (`:401`, 30-day window at `app.py:5865`), both visible one tab apart. "Tendencia · últimos 12 meses" (`:189`) plots 26 weekly buckets — `app.py:5769`'s own comment says "26 semanas (6 meses)". All three verified in source.
**Why:** the two cheapest ways to lose trust in every other number. "19 pendientes · 0 vencidos" actively reassures about 19 orders structurally incapable of counting as vencido.
**Fix:** compute `pedidos_pendientes` over the same window as `pedidos_vencidos`, or label both explicitly. Change `:189` to "últimos 6 meses".
**Command:** `/impeccable clarify templates/dashboard.html`

### [P1] On the warehouse phone, the operational text is below the legibility floor
33 text/background pairs measured; **9 fail AA**. One token is responsible: `#94a3b8` on white = **2.56:1**, carrying every secondary label — including the order number and date (`.act-meta`, 11px), the XCG unit (9.9px), the 9px acronym glosses, and `Chart.defaults.color` (`:449`) for every axis. Tap targets: **27 of 33 interactive elements under 44x44** at 390px — carousel arrows at 11x20 and 15x20, "Ver más ›" at 68x17, the four tabs at 39.5px tall. The bottom tabbar passes (70.8x52.5).
**Why:** the order number is what a person reads aloud across a warehouse floor, on a phone, in daylight. Everything needed to transact is in the lightest weight on the page while decorative rings get weight 800.
**Fix:** `#94a3b8` → `#64748b` (4.76:1) for those classes; `.act-meta` to 12px; the 9px gloss to 11px or delete it and rename the acronyms to Spanish. Tabs to 44px minimum; 44px hit areas on the carousel arrows via pseudo-elements.
**Command:** `/impeccable audit templates/dashboard.html`

### [P2] The rings overflow, and their colour vanishes exactly when it matters
`.ring-label` "100.0%" measures **51.9px inside a 44px ring — 7.9px of overflow**, crossing the coloured stroke on OTD and OFR at both breakpoints. State colour lives only in the arc, so a `danger` ring at 0% (POR, and PED whenever ≥7 orders are pending via `pend_pct` at `:80`) is indistinguishable from an inert neutral ring. And `pend_pct` = `[0, 100 - pedidos_pendientes_v * 15]|max` is an invented scale where 7 orders = 0% — not a rate or ratio of anything, yet it drives a ring users read as a measurement.
**Why:** broken text over a stroke reads as a bug on the exact card being read. A severity system that goes invisible at maximum severity teaches that grey means "fine".
**Fix:** drop the value from the ring (already printed 8px below) and let it carry the threshold — a target tick at 95%. Give the ring track the state colour at low alpha. Replace `pend_pct` with a real ratio or remove that ring.
**Command:** `/impeccable polish templates/dashboard.html`

## Persona Red Flags

**Casey (distracted mobile, PWA in the warehouse).** Tabs 39.5px tall, under the 44pt iOS minimum. The "Actividad" tab overflows its own container: right edge x=378.2 vs track end x=359.2 — hanging 19px outside the pill. No swipe affordance exists: `dashboard_snap.css:323` sets `.snap-dots{display:none}` while `:127-128` still emits the containers and `dashboard-snap-dots.js` still builds 12 hidden spans — yet the touch handlers at `:508-548` are live. The gesture is greedy: `preventDefault()` (`:531`) fires on any >10px drag where `|dx| ≥ |dy|`, so a diagonal thumb scroll flips her mid-read. She taps the 19: nothing. She cannot read the order number she is matching against a box: 11px at 2.56:1.

**Alex (impatient salesperson, 20 checks/day).** His one question is "which orders are late?" The path: hero → Actividad tab → five rows that are not links → leave for `/pedidos` → re-find them. The route already built it and discarded it (`pedidos_operativos`, `app.py:5895`). He pays for 12 unused context variables per load. No keyboard path: bare `<button>`s, no `role="tablist"`, no `aria-selected`, no arrow keys. The page jumps under his cursor: panels measure 899 / 555 / 297 / 735px, so Ventas→Top collapses the viewport 600px mid-animation.

**Sam (accessibility-dependent).** Nine text pairs fail AA; two that "pass" do so by 0.05 (`hero-kicker`, `hero-sub` at 4.55:1) and the overlay, sampling painted pixels, measured `hero-sub` at 4.4:1 against the real `#f4f6fa` — a fail. Twenty elements below the size floor, including six 9px acronym glosses. The tab carousel exposes no ARIA, so a screen reader announces four stateless buttons unrelated to the panels. Heading skip: `<h1>` straight to `<h3>` (`:189`). The four hidden panels remain in the accessibility tree (`overflow:hidden` does not remove them), so linear reading traverses ~30 offscreen numbers before finishing.

## Minor Observations

- "Buenos días ☀" is unconditional (`:100`) — greets a 7pm shift with sunshine, 8px above "Todavía no hay ventas este mes."
- Dark chart config bleeding onto light cards: `Chart.defaults.borderColor` `rgba(31,41,55,0.8)` (`:450`), grid `rgba(31,41,55,0.6)` (`:654`), donut `rgba(10,10,15,0.8)` (`:683`) — visible as a black hairline at 12 o'clock.
- The status donut is single-category in practice (12/0/0/0): a solid orange ring ~250x250 on a 390px phone, while the legend below carries all four values more informatively in a fifth of the space.
- Desktop wastes the viewport: one panel plus ~370-380px of dead white at 1440x900. A phone idiom applied unchanged to a monitor.
- Dead code: `static/dashboard_pro.css` (614 lines, never served), `dashboard-snap-dots.js` (71 lines, `display:none`), `data-snap-card="1"` on 8 elements with no consumer.
- The green `↑ +0%` chip still shows with zero sales (`:200-205`).
- The "¡Bienvenido, Admin Local!" flash takes the slot above the hero on first load.
- `{% block header_title %}Dashboard{% endblock %}` (`:12`) is set but the mobile topbar renders "Pesos".
- Console clean: 0 errors, 0 warnings; only a `favicon.ico` 404. Six self-congratulatory `console.log` lines ship to every user on every load.
- Top's empty state shows two identical "Sin datos este mes" cards and ~380px of dead space, offering no other period — while the route computed 6m/3m/4w rankings and shipped them unused.

## Questions to Consider

1. If you deleted every progress ring, what would a salesperson actually lose? Each repeats the number beside it.
2. `/clientes` says "63 días sin comprar · su ritmo: 16 d" — every number welded to its own baseline. Why does the dashboard say "100.0%" with no ritmo? The technique is already in this codebase.
3. The route computes `pedidos_operativos` with "Vencido 3d" per order and discards it. Why show a donut of four numbers instead of the five orders that are late, with a Preparar button?
4. If each panel needs its own tab and its own height, is this one screen or four wearing a carousel costume? What would you cut if it had to be one scroll with no tabs?
5. "19 pendientes · 0 vencidos" is the calmest sentence on the page and describes the most dangerous state. What would this look like if designed to make you uncomfortable until the queue was empty?
6. Salespeople live in `/pedidos`, a better Operate surface than this. Should `/dashboard` be the home tab at all, or should the headline and pendientes count become a strip on top of `/pedidos`?

## Caveats

- The local DB is in a near-empty state for the current month (12 pending August orders, zero QuickBooks-sourced sales), so browser screenshots show empty states. Populated paths were read in source.
- Production CSP was not exercised: Talisman mounts only under `FLASK_ENV == "production"`.
