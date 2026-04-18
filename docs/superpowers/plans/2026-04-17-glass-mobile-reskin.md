# Glass Mobile Reskin Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Apply the iterated prototype design (dark theme, heavy glass, blue hue, minimal KPI) to Dashboard, Pedidos list, PedidoDetail, and the shared `base.html` chrome in the production Flask app — without touching any backend code or existing JS.

**Architecture:** Layered CSS approach. A new `static/css/app-mobile.css` loads last (after `dark-theme.css`) so its rules win by order. Templates get surgical edits (wrapper classes, card markup, new hero/timeline/items). A tiny `static/js/theme-toggle.js` (~25 LOC, new file) handles light/dark persistence in `localStorage`. **Zero changes to existing JS files** — that is the explicit regression guard against the Phase 3 bug.

**Tech Stack:** Flask + Jinja2, vanilla CSS (no preprocessor), vanilla JS, Chart.js (unchanged). No new dependencies.

**Branch:** `feat/glass-mobile-reskin` (already created). Staging: `pesosapp-staging` Heroku app.

**Design reference** (already copied into repo for stable paths):
- `_bmad-output/design-reference/src/tokens.css` — identical to `static/css/tokens.css` (Phase 1)
- `_bmad-output/design-reference/src/primitives.css` — identical to `static/css/primitives.css` (Phase 1)
- `_bmad-output/design-reference/src/app.css` — 1014 LOC, source of truth for screen-level styles
- `_bmad-output/design-reference/src/screens/*.jsx` — markup patterns for each screen
- `_bmad-output/design-reference/prototype-index.html` — prototype shell (reference only, not ported)

**Spec:** `docs/superpowers/specs/2026-04-17-glass-mobile-reskin-design.md`

---

## Part A — Scaffolding

### Task 1: Verify branch and commit design reference

**Files:**
- Modify: none
- Add to index: `_bmad-output/design-reference/**`
- Test: none (docs-only)

- [ ] **Step 1: Verify on the feature branch**

Run: `git branch --show-current`
Expected output: `feat/glass-mobile-reskin`

If not on it, run: `git checkout feat/glass-mobile-reskin`

- [ ] **Step 2: Verify design reference exists**

Run: `ls _bmad-output/design-reference/src/`
Expected output:
```
app.css
components.jsx
data.js
primitives.css
screens
tokens.css
```

If the directory is missing, abort and request manual re-extraction from `/Users/josedasilva/Dropbox/Mi Mac (MacBook-Air-de-Jose.local)/Downloads/pesosapp.zip` — the rest of the plan depends on it.

- [ ] **Step 3: Commit the design reference**

```bash
git add _bmad-output/design-reference/
git commit -m "docs: add Claude Design prototype bundle as reskin reference"
```

Expected: one commit created; no files beyond `_bmad-output/design-reference/` added.

---

### Task 2: Add `[data-hue="blue"]` variant to tokens.css

**Files:**
- Modify: `static/css/tokens.css` (append at the end)
- Test: visual (inspect DevTools after Task 10 lands)

- [ ] **Step 1: Open `static/css/tokens.css` and read the last 10 lines**

Run: `tail -n 10 static/css/tokens.css`

Identify the final `}` of the file so the new block is appended after it.

- [ ] **Step 2: Append the hue variants block**

Append at the end of the file:

```css

/* ─── Hue variants (activated via body[data-hue]) ────────────────────── */
[data-hue="blue"] {
  --indigo-500: #2563eb;
  --violet-500: #0ea5e9;
  --indigo-300: #93c5fd;
  --color-accent-soft: rgba(37, 99, 235, 0.12);
  --color-shadow-accent: rgba(37, 99, 235, 0.3);
}
[data-hue="teal"] {
  --indigo-500: #14b8a6;
  --violet-500: #06b6d4;
  --indigo-300: #5eead4;
  --color-accent-soft: rgba(20, 184, 166, 0.12);
  --color-shadow-accent: rgba(20, 184, 166, 0.25);
}
[data-hue="rose"] {
  --indigo-500: #f43f5e;
  --violet-500: #ec4899;
  --indigo-300: #fda4af;
  --color-accent-soft: rgba(244, 63, 94, 0.12);
  --color-shadow-accent: rgba(244, 63, 94, 0.25);
}
[data-hue="amber"] {
  --indigo-500: #f59e0b;
  --violet-500: #f97316;
  --indigo-300: #fcd34d;
  --color-accent-soft: rgba(245, 158, 11, 0.12);
  --color-shadow-accent: rgba(245, 158, 11, 0.25);
}
```

Note: `[data-hue="indigo"]` is the implicit default — covered by the base `:root` values.

- [ ] **Step 3: Verify no syntax errors**

Run: `python -c "open('static/css/tokens.css').read()"` — just confirms file is readable.

Visual inspection: the last line of `tokens.css` must still end with a closing `}` and the file must not contain unbalanced braces (visually balanced `{` and `}` counts).

- [ ] **Step 4: Commit**

```bash
git add static/css/tokens.css
git commit -m "feat(tokens): add blue/teal/rose/amber hue variants for data-hue switching"
```

---

### Task 3: Create `static/js/theme-toggle.js`

**Files:**
- Create: `static/js/theme-toggle.js`
- Test: manual in Task 9 (button flips theme and persists)

- [ ] **Step 1: Create the file with exact contents**

Write `static/js/theme-toggle.js`:

```js
/*
 * Theme toggle — reads saved theme from localStorage, applies to body.dataset.theme,
 * wires up any [data-theme-toggle] button to flip and persist.
 * Loaded near the top of <body> (not deferred) so the saved theme is applied
 * before the first paint and there is no flash from the default to the saved value.
 */
(function () {
  var KEY = 'pesos_theme';
  var root = document.body;
  if (!root) return;

  try {
    var saved = localStorage.getItem(KEY);
    if (saved === 'light' || saved === 'dark') {
      root.dataset.theme = saved;
    }
  } catch (e) { /* localStorage blocked — silent */ }

  function sync(current) {
    var buttons = document.querySelectorAll('[data-theme-toggle]');
    for (var i = 0; i < buttons.length; i++) {
      buttons[i].setAttribute('aria-pressed', String(current === 'dark'));
    }
  }

  document.addEventListener('click', function (ev) {
    var btn = ev.target.closest && ev.target.closest('[data-theme-toggle]');
    if (!btn) return;
    var next = root.dataset.theme === 'dark' ? 'light' : 'dark';
    root.dataset.theme = next;
    try { localStorage.setItem(KEY, next); } catch (e) {}
    sync(next);
  });

  sync(root.dataset.theme || 'dark');
})();
```

Notes for the implementer:
- `var` (not `let/const`) for compatibility with older iOS Safari, no build step.
- Event delegation on `document` handles theme-toggle buttons added later.
- The outer `try/catch` around `localStorage` is required — private mode in Safari throws.

- [ ] **Step 2: Verify the file is valid JS**

Run: `node -c static/js/theme-toggle.js 2>&1 || echo "syntax error"`
Expected: no output (valid), or if `node` is unavailable, skip this check.

- [ ] **Step 3: Commit**

```bash
git add static/js/theme-toggle.js
git commit -m "feat(js): theme toggle with localStorage persistence"
```

---

## Part B — `app-mobile.css` built incrementally

The prototype's `app.css` (1014 LOC at `_bmad-output/design-reference/src/app.css`) is the source. **Do not copy it wholesale**. It contains sections that are prototype-only chrome (iPhone frames, desktop stage, tweaks panel, density/glass/accent variants) — those are dropped. Only the screen-level styles are ported, in order.

### Task 4: Create `app-mobile.css` — screen shell + nav + glass card

**Files:**
- Create: `static/css/app-mobile.css`
- Reference: `_bmad-output/design-reference/src/app.css:145-320`

- [ ] **Step 1: Create the file with the header and shell section**

Write `static/css/app-mobile.css`:

```css
/* =============================================================================
   PesosApp · Glass Mobile Reskin
   Loaded AFTER dark-theme.css so it wins by source order.
   Scope: body-level layout, glass cards, nav-bar, bottom tabbar, hero.
   See docs/superpowers/specs/2026-04-17-glass-mobile-reskin-design.md
   ============================================================================= */

/* Reset and base */
body {
  font-family: var(--font-sans, -apple-system, BlinkMacSystemFont, 'Inter', system-ui, sans-serif);
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
}

/* The mobile shell — centered narrow on desktop, full-width on mobile */
.app-shell {
  min-height: 100vh;
  max-width: 480px;
  margin: 0 auto;
  padding-bottom: calc(72px + env(safe-area-inset-bottom, 0));
  position: relative;
  background:
    radial-gradient(ellipse 80% 60% at 20% 0%, color-mix(in oklab, var(--indigo-500) 10%, transparent), transparent 70%),
    radial-gradient(ellipse 70% 50% at 90% 20%, color-mix(in oklab, var(--violet-500) 8%, transparent), transparent 70%),
    var(--color-bg);
}

/* Glass card — the fundamental surface for panels, KPI tiles, and list groups */
.gcard {
  background: var(--glass-bg);
  backdrop-filter: blur(40px) saturate(2);
  -webkit-backdrop-filter: blur(40px) saturate(2);
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-lg, 16px);
  padding: 14px;
}

/* Hero (page title area) */
.hero {
  padding: 20px 16px 12px;
}
.hero-kicker {
  font-size: 11px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.12em;
  color: var(--color-text-subtle);
  margin-bottom: 4px;
}
.hero-title {
  font-size: 28px;
  font-weight: 800;
  letter-spacing: -0.02em;
  line-height: 1.1;
  margin: 0;
}
.hero-sub {
  font-size: 14px;
  color: var(--color-text-muted);
  margin-top: 6px;
}

/* Top nav bar (glass) */
.nav-bar {
  position: sticky;
  top: 0;
  z-index: 50;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 16px;
  background: var(--glass-bg);
  backdrop-filter: blur(20px) saturate(1.8);
  -webkit-backdrop-filter: blur(20px) saturate(1.8);
  border-bottom: 1px solid var(--color-border-subtle);
}
.nav-title {
  font-size: 17px;
  font-weight: 700;
  letter-spacing: -0.01em;
}
.nav-pill {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 36px;
  height: 36px;
  border-radius: 10px;
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  cursor: pointer;
  color: var(--color-text);
  transition: transform 140ms ease;
}
.nav-pill:hover { transform: translateY(-1px); }
.nav-pill[aria-pressed="true"] {
  background: linear-gradient(135deg, var(--indigo-500), var(--violet-500));
  color: white;
  border-color: transparent;
}

/* Bottom tabbar (sticky) */
.tabbar {
  position: fixed;
  left: 0;
  right: 0;
  bottom: 0;
  z-index: 60;
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 4px;
  padding: 8px 10px calc(8px + env(safe-area-inset-bottom, 0));
  background: var(--glass-bg-strong);
  backdrop-filter: blur(30px) saturate(1.8);
  -webkit-backdrop-filter: blur(30px) saturate(1.8);
  border-top: 1px solid var(--color-border-subtle);
  max-width: 480px;
  margin: 0 auto;
}
.tabbar .tab {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 6px 0;
  font-size: 10px;
  font-weight: 600;
  color: var(--color-text-muted);
  text-decoration: none;
  border-radius: 10px;
  gap: 2px;
}
.tabbar .tab.active {
  color: var(--indigo-500);
}
.tabbar .tab i,
.tabbar .tab svg {
  font-size: 18px;
  width: 20px;
  height: 20px;
}
```

- [ ] **Step 2: Link it from base.html (temporarily just to verify loading)**

Do not edit base.html yet — that happens in Task 9. For this step, only verify the file is syntactically clean:

Run: `python -c "open('static/css/app-mobile.css').read()"` — no output expected.

Also count braces balance:

Run: `python -c "t=open('static/css/app-mobile.css').read(); print('ok' if t.count('{')==t.count('}') else 'UNBALANCED')"`
Expected: `ok`

- [ ] **Step 3: Commit**

```bash
git add static/css/app-mobile.css
git commit -m "feat(css): app-mobile.css — shell, glass card, nav-bar, tabbar, hero"
```

---

### Task 5: Append dashboard-specific styles to `app-mobile.css`

**Files:**
- Modify: `static/css/app-mobile.css` (append)
- Reference: `_bmad-output/design-reference/src/app.css:320-490` (segmented, kpi, ring, sec-head, rank, chart)

- [ ] **Step 1: Append the dashboard block**

Append to `static/css/app-mobile.css`:

```css

/* ============================================================================
   Dashboard
   ============================================================================ */

/* Segmented control (existing carousel nav gets restyled via these classes) */
.segmented {
  display: flex;
  gap: 4px;
  padding: 3px;
  background: var(--color-surface-sunken);
  border-radius: 12px;
  margin: 0 16px 12px;
}
.segmented button {
  flex: 1;
  height: 36px;
  border: none;
  background: transparent;
  border-radius: 9px;
  font-size: 12px;
  font-weight: 600;
  color: var(--color-text-muted);
  cursor: pointer;
  letter-spacing: -0.01em;
  transition: background 140ms ease, color 140ms ease;
}
.segmented button.active {
  background: var(--color-bg-elevated);
  color: var(--color-text);
  box-shadow: var(--shadow-sm);
}

/* KPI grid + tile */
.kpi-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 10px;
  padding: 0 16px;
}
.kpi {
  background: var(--glass-bg);
  backdrop-filter: blur(40px) saturate(2);
  -webkit-backdrop-filter: blur(40px) saturate(2);
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-lg, 16px);
  padding: 14px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.kpi-top {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 10px;
  margin-bottom: 4px;
}
.kpi-label {
  font-size: 11px;
  font-weight: 600;
  color: var(--color-text-muted);
  text-transform: uppercase;
  letter-spacing: 0.06em;
}
.kpi-value {
  font-size: 24px;
  font-weight: 800;
  letter-spacing: -0.02em;
  font-variant-numeric: tabular-nums;
  line-height: 1.05;
}
.kpi-value small {
  font-size: 12px;
  font-weight: 500;
  color: var(--color-text-subtle);
  margin-left: 3px;
}
.kpi-sub {
  font-size: 11px;
  color: var(--color-text-subtle);
}
.kpi-trend {
  font-size: 11px;
  font-weight: 700;
  padding: 2px 8px;
  border-radius: 99px;
  background: var(--color-success-soft);
  color: var(--color-success-soft-fg);
}
.kpi-trend.down {
  background: var(--color-danger-soft);
  color: var(--color-danger-soft-fg);
}

/* Minimal KPI style (applied globally via body[data-kpi-style="minimal"]) */
[data-kpi-style="minimal"] .ring-wrap,
[data-kpi-style="minimal"] .progress-ring {
  display: none;
}

/* Progress ring */
.ring-wrap {
  position: relative;
  width: 44px;
  height: 44px;
  flex-shrink: 0;
}
.ring-wrap svg { display: block; }
.ring-wrap .ring-label {
  position: absolute;
  inset: 0;
  display: grid;
  place-items: center;
  font-size: 11px;
  font-weight: 700;
  font-variant-numeric: tabular-nums;
}

/* Section header */
.sec-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px 16px 8px;
}
.sec-title {
  font-size: 13px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: var(--color-text-subtle);
}
.sec-action {
  font-size: 13px;
  font-weight: 600;
  color: var(--indigo-500);
  text-decoration: none;
}

/* Rank rows (Top productos / clientes) */
.rank-list { padding: 0 16px; }
.rank {
  padding: 12px 14px;
  display: grid;
  grid-template-columns: 28px 1fr auto;
  align-items: center;
  gap: 12px;
  border-bottom: 1px solid var(--color-border-subtle);
}
.rank:last-child { border-bottom: none; }
.rank-pos {
  width: 26px;
  height: 26px;
  border-radius: 8px;
  display: grid;
  place-items: center;
  font-size: 12px;
  font-weight: 800;
  color: white;
  background: linear-gradient(135deg, var(--indigo-500), var(--violet-500));
}
.rank-body { min-width: 0; }
.rank-name {
  font-size: 14px;
  font-weight: 600;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.rank-bar {
  height: 6px;
  border-radius: 99px;
  background: var(--color-accent-soft, rgba(99,102,241,0.12));
  margin-top: 6px;
  overflow: hidden;
}
.rank-bar-fill {
  height: 100%;
  border-radius: 99px;
  background: linear-gradient(90deg, var(--indigo-500), var(--violet-500));
}
.rank-amt {
  text-align: right;
  font-size: 14px;
  font-weight: 700;
  font-variant-numeric: tabular-nums;
}
.rank-amt small {
  display: block;
  font-size: 10px;
  font-weight: 500;
  color: var(--color-text-subtle);
}

/* Sparkline chart card */
.chart-card { padding: 16px; margin: 0 16px; }
.chart-head {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  margin-bottom: 14px;
}
.chart-big {
  font-size: 28px;
  font-weight: 800;
  letter-spacing: -0.02em;
  font-variant-numeric: tabular-nums;
  line-height: 1.05;
}
.chart-big small {
  font-size: 12px;
  font-weight: 500;
  color: var(--color-text-subtle);
  margin-left: 3px;
}
.chart-legend {
  font-size: 11px;
  color: var(--color-text-muted);
  display: flex;
  align-items: center;
  gap: 8px;
}
```

- [ ] **Step 2: Verify balance**

Run: `python -c "t=open('static/css/app-mobile.css').read(); print('ok' if t.count('{')==t.count('}') else 'UNBALANCED')"`
Expected: `ok`

- [ ] **Step 3: Commit**

```bash
git add static/css/app-mobile.css
git commit -m "feat(css): dashboard styles — segmented, kpi, ring, rank, chart"
```

---

### Task 6: Append Pedidos list styles to `app-mobile.css`

**Files:**
- Modify: `static/css/app-mobile.css` (append)
- Reference: `_bmad-output/design-reference/src/app.css:490-624` (search-pill, chips-row, fchip, pedido-card, status-pill, sla)

- [ ] **Step 1: Append the Pedidos block**

Append to `static/css/app-mobile.css`:

```css

/* ============================================================================
   Pedidos list
   ============================================================================ */

.pedidos-list {
  padding: 0 16px;
}

.search-pill {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 0 14px;
  height: 44px;
  border-radius: 99px;
  background: var(--glass-bg);
  backdrop-filter: blur(20px) saturate(1.6);
  -webkit-backdrop-filter: blur(20px) saturate(1.6);
  border: 1px solid var(--glass-border);
  margin: 0 16px 12px;
  color: var(--color-text-subtle);
  font-size: 15px;
}
.search-pill input {
  border: none;
  background: transparent;
  flex: 1;
  font-size: 16px;
  outline: none;
  color: var(--color-text);
}
.search-pill input::placeholder { color: var(--color-text-subtle); }

.chips-row {
  display: flex;
  gap: 7px;
  margin: 0 16px 14px;
  overflow-x: auto;
  padding-bottom: 2px;
  -ms-overflow-style: none;
  scrollbar-width: none;
}
.chips-row::-webkit-scrollbar { display: none; }
.fchip {
  flex-shrink: 0;
  height: 32px;
  padding: 0 12px;
  border-radius: 99px;
  border: 1px solid var(--color-border);
  background: var(--color-bg-elevated);
  font-size: 12px;
  font-weight: 600;
  color: var(--color-text-muted);
  display: inline-flex;
  align-items: center;
  gap: 5px;
  cursor: pointer;
  white-space: nowrap;
}
.fchip .fcount {
  background: rgba(15, 23, 42, 0.08);
  border-radius: 99px;
  padding: 1px 6px;
  font-size: 10px;
  font-variant-numeric: tabular-nums;
}
.fchip.active {
  background: var(--indigo-500);
  border-color: var(--indigo-500);
  color: white;
}
.fchip.active .fcount {
  background: rgba(255, 255, 255, 0.22);
  color: white;
}

/* Day-group header */
.day-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin: 14px 0 8px;
  padding: 6px 0;
  font-size: 12px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: var(--color-text-subtle);
}
.day-head .day-totals {
  font-variant-numeric: tabular-nums;
  color: var(--color-text-muted);
}

/* Pedido row as card */
.pedido-card {
  padding: 14px 14px 12px;
  border-radius: var(--radius-xl, 20px);
  background: var(--color-bg-elevated);
  border: 1px solid var(--color-border-subtle);
  margin-bottom: 10px;
  box-shadow: var(--shadow-xs);
  cursor: pointer;
  transition: transform 160ms ease, box-shadow 160ms ease;
  text-decoration: none;
  color: inherit;
  display: block;
}
.pedido-card:hover {
  transform: translateY(-1px);
  box-shadow: var(--shadow-sm);
}
.pc-top {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 10px;
  margin-bottom: 6px;
}
.pc-id {
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.05em;
  color: var(--color-text-subtle);
  font-variant-numeric: tabular-nums;
}
.pc-client {
  font-size: 16px;
  font-weight: 700;
  letter-spacing: -0.01em;
  line-height: 1.2;
  margin-top: 2px;
}
.pc-amt {
  font-size: 16px;
  font-weight: 700;
  font-variant-numeric: tabular-nums;
  text-align: right;
  line-height: 1.1;
}
.pc-amt small {
  display: block;
  font-size: 10px;
  font-weight: 500;
  color: var(--color-text-subtle);
  margin-top: 2px;
}
.pc-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  font-size: 12px;
  color: var(--color-text-muted);
  margin-top: 6px;
}
.pc-meta span {
  display: inline-flex;
  align-items: center;
  gap: 4px;
}
.pc-foot {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-top: 10px;
  padding-top: 10px;
  border-top: 1px solid var(--color-border-subtle);
}

.status-pill {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 4px 9px;
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.02em;
  border-radius: 99px;
  text-transform: uppercase;
}
.status-pill.pendiente { background: var(--color-warning-soft); color: var(--color-warning-soft-fg); }
.status-pill.preparado { background: var(--color-success-soft); color: var(--color-success-soft-fg); }
.status-pill.facturado { background: var(--color-info-soft); color: var(--color-info-soft-fg); }
.status-pill.vencido   { background: var(--color-danger-soft);  color: var(--color-danger-soft-fg); }

.sla {
  font-size: 11px;
  font-weight: 600;
  color: var(--color-text-muted);
  display: inline-flex;
  align-items: center;
  gap: 5px;
}
.sla .dot { width: 6px; height: 6px; border-radius: 99px; background: var(--color-success, #10b981); }
.sla.warn .dot { background: var(--color-warning, #f59e0b); }
.sla.danger .dot { background: var(--color-danger, #f43f5e); }
```

- [ ] **Step 2: Verify balance**

Run: `python -c "t=open('static/css/app-mobile.css').read(); print('ok' if t.count('{')==t.count('}') else 'UNBALANCED')"`
Expected: `ok`

- [ ] **Step 3: Commit**

```bash
git add static/css/app-mobile.css
git commit -m "feat(css): pedidos list styles — search-pill, chips, pedido-card, sla"
```

---

### Task 7: Append Pedido detail styles to `app-mobile.css`

**Files:**
- Modify: `static/css/app-mobile.css` (append)
- Reference: `_bmad-output/design-reference/src/app.css:625-816` (detail-hero, line-item, timeline, fab)

- [ ] **Step 1: Append the Pedido detail block**

Append to `static/css/app-mobile.css`:

```css

/* ============================================================================
   Pedido detail
   ============================================================================ */

.detail-hero {
  padding: 20px 16px 18px;
  margin: 0 16px 14px;
  border-radius: var(--radius-xl, 20px);
  background: linear-gradient(135deg, var(--indigo-500) 0%, var(--violet-500) 100%);
  color: white;
  position: relative;
  overflow: hidden;
  box-shadow: 0 20px 40px -20px var(--color-shadow-accent);
}
.detail-hero::before {
  content: "";
  position: absolute;
  inset: 0;
  background: radial-gradient(ellipse 60% 40% at 80% 20%, rgba(255,255,255,0.2), transparent 60%);
  pointer-events: none;
}
.dh-row {
  position: relative;
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
}
.dh-client {
  font-size: 20px;
  font-weight: 800;
  letter-spacing: -0.02em;
  line-height: 1.15;
}
.dh-id {
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.08em;
  opacity: 0.8;
  margin-bottom: 2px;
}
.dh-meta {
  font-size: 13px;
  opacity: 0.85;
  margin-top: 6px;
}
.dh-stats {
  position: relative;
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 10px;
  margin-top: 16px;
}
.dh-stat {
  background: rgba(255, 255, 255, 0.12);
  border: 1px solid rgba(255, 255, 255, 0.18);
  border-radius: 12px;
  padding: 10px;
  backdrop-filter: blur(8px);
  -webkit-backdrop-filter: blur(8px);
}
.dh-stat-label {
  font-size: 10px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  opacity: 0.85;
}
.dh-stat-val {
  font-size: 18px;
  font-weight: 800;
  font-variant-numeric: tabular-nums;
  margin-top: 2px;
}

/* Progress timeline */
.timeline {
  padding: 4px 0;
}
.tl-item {
  position: relative;
  padding: 12px 14px 12px 36px;
  min-height: 44px;
}
.tl-item::before {
  content: "";
  position: absolute;
  left: 19px;
  top: 26px;
  bottom: -12px;
  width: 2px;
  background: var(--color-border);
}
.tl-item:last-child::before { display: none; }
.tl-dot {
  position: absolute;
  left: 12px;
  top: 14px;
  width: 16px;
  height: 16px;
  border-radius: 99px;
  background: var(--color-surface-sunken);
  border: 2px solid var(--color-border);
}
.tl-dot.done {
  background: var(--color-success, #10b981);
  border-color: var(--color-success, #10b981);
}
.tl-dot.active {
  background: var(--indigo-500);
  border-color: var(--indigo-500);
  box-shadow: 0 0 0 4px var(--color-accent-soft);
}
.tl-title { font-size: 13px; font-weight: 600; }
.tl-meta { font-size: 11px; color: var(--color-text-subtle); margin-top: 2px; }
.tl-time {
  position: absolute;
  right: 14px;
  top: 12px;
  font-size: 11px;
  color: var(--color-text-subtle);
  font-variant-numeric: tabular-nums;
}

/* Line items (productos dentro del pedido) */
.line-items { padding: 0; }
.line-item {
  padding: 12px 14px;
  display: grid;
  grid-template-columns: 6px 1fr auto;
  gap: 12px;
  align-items: center;
  border-bottom: 1px solid var(--color-border-subtle);
}
.line-item:last-child { border-bottom: none; }
.li-strip {
  width: 4px;
  height: 32px;
  border-radius: 2px;
  background: var(--li-color, var(--indigo-500));
}
.li-body { min-width: 0; }
.li-name {
  font-size: 14px;
  font-weight: 600;
  letter-spacing: -0.01em;
}
.li-meta {
  font-size: 11px;
  color: var(--color-text-subtle);
  margin-top: 2px;
  font-variant-numeric: tabular-nums;
}
.li-qty {
  text-align: right;
  font-size: 16px;
  font-weight: 700;
  font-variant-numeric: tabular-nums;
}
.li-qty small {
  display: block;
  font-size: 10px;
  color: var(--color-text-subtle);
  font-weight: 500;
  margin-top: 2px;
}

/* Category color hints for the left strip (apply via .line-item[data-cat="..."]) */
.line-item[data-cat="res"]    { --li-color: #dc2626; }
.line-item[data-cat="falda"]  { --li-color: #ea580c; }
.line-item[data-cat="pollo"]  { --li-color: #eab308; }
.line-item[data-cat="cerdo"]  { --li-color: #f472b6; }
.line-item[data-cat="default"],
.line-item:not([data-cat])    { --li-color: var(--indigo-500); }

/* Weigh-status chip inside a line item */
.weigh-strip {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 10px;
  font-weight: 700;
  padding: 2px 7px;
  border-radius: 99px;
  background: var(--color-success-soft);
  color: var(--color-success-soft-fg);
}
.weigh-strip.pending {
  background: var(--color-warning-soft);
  color: var(--color-warning-soft-fg);
}
.weigh-strip b { font-variant-numeric: tabular-nums; }

/* Sticky bottom action bar (for "Marcar preparado" / "Facturar") */
.action-bar {
  position: sticky;
  bottom: 72px;
  z-index: 40;
  display: flex;
  gap: 10px;
  padding: 10px 16px;
  background: var(--glass-bg-strong);
  backdrop-filter: blur(30px) saturate(1.8);
  -webkit-backdrop-filter: blur(30px) saturate(1.8);
  border-top: 1px solid var(--color-border-subtle);
  margin-top: 14px;
}
.action-bar .btn-primary,
.action-bar .btn-secondary {
  flex: 1;
  height: 48px;
  border-radius: 14px;
  font-size: 15px;
  font-weight: 700;
  letter-spacing: -0.01em;
  cursor: pointer;
  border: none;
  font-family: inherit;
}
.action-bar .btn-primary {
  background: linear-gradient(135deg, var(--indigo-500), var(--violet-500));
  color: white;
  box-shadow: 0 10px 22px -8px var(--color-shadow-accent);
}
.action-bar .btn-secondary {
  background: var(--color-surface);
  color: var(--color-text);
  border: 1px solid var(--color-border);
}
```

- [ ] **Step 2: Verify balance**

Run: `python -c "t=open('static/css/app-mobile.css').read(); print('ok' if t.count('{')==t.count('}') else 'UNBALANCED')"`
Expected: `ok`

- [ ] **Step 3: Commit**

```bash
git add static/css/app-mobile.css
git commit -m "feat(css): pedido detail styles — hero, timeline, line-items, action-bar"
```

---

### Task 8: Append dark-mode overrides to `app-mobile.css`

**Files:**
- Modify: `static/css/app-mobile.css` (append)
- Reference: `_bmad-output/design-reference/src/app.css:950-1014` (dark scope)

- [ ] **Step 1: Append dark-mode overrides**

Append to `static/css/app-mobile.css`:

```css

/* ============================================================================
   Dark mode overrides — activated via body[data-theme="dark"]
   Default theme in this app is dark; light is an opt-in toggle.
   ============================================================================ */

[data-theme="dark"] {
  --color-bg: #0a0a0f;
  --color-bg-elevated: #121219;
  --color-surface: rgba(255, 255, 255, 0.04);
  --color-surface-sunken: rgba(255, 255, 255, 0.02);
  --color-text: #f8fafc;
  --color-text-muted: #94a3b8;
  --color-text-subtle: #64748b;
  --color-border: rgba(255, 255, 255, 0.08);
  --color-border-subtle: rgba(255, 255, 255, 0.05);
  --glass-bg: rgba(18, 18, 25, 0.6);
  --glass-bg-strong: rgba(10, 10, 15, 0.8);
  --glass-border: rgba(255, 255, 255, 0.06);
}

[data-theme="dark"] .pedido-card,
[data-theme="dark"] .fchip:not(.active) {
  background: rgba(255, 255, 255, 0.04);
  border-color: rgba(255, 255, 255, 0.08);
}

[data-theme="dark"] .segmented {
  background: rgba(255, 255, 255, 0.06);
}
[data-theme="dark"] .segmented button.active {
  background: rgba(255, 255, 255, 0.1);
  color: #fff;
}

[data-theme="dark"] .search-pill input { color: #fff; }

[data-theme="dark"] .dh-stat {
  background: rgba(255, 255, 255, 0.1);
  border-color: rgba(255, 255, 255, 0.15);
}

[data-theme="dark"] .nav-pill { color: #fff; }

/* Theme transition animation */
body,
.app-shell,
.gcard,
.kpi,
.pedido-card,
.nav-bar,
.tabbar {
  transition: background-color 150ms ease, color 150ms ease, border-color 150ms ease;
}
```

- [ ] **Step 2: Verify balance**

Run: `python -c "t=open('static/css/app-mobile.css').read(); print('ok' if t.count('{')==t.count('}') else 'UNBALANCED')"`
Expected: `ok`

- [ ] **Step 3: Verify final file size is in the expected range**

Run: `wc -l static/css/app-mobile.css`
Expected: 600–750 lines (roughly).

- [ ] **Step 4: Commit**

```bash
git add static/css/app-mobile.css
git commit -m "feat(css): dark mode overrides + theme transition"
```

---

## Part C — Templates

### Task 9: Update `templates/base.html`

**Files:**
- Modify: `templates/base.html`

- [ ] **Step 1: Link `app-mobile.css` after `dark-theme.css`**

In `templates/base.html`, find this line:
```html
    <link rel="stylesheet" href="{{ url_for('static', filename='css/dark-theme.css') }}">
```

Immediately after it, add:
```html

    <!-- Glass Mobile Reskin — loaded LAST so its rules win by order -->
    <link rel="stylesheet" href="{{ url_for('static', filename='css/app-mobile.css') }}">
```

- [ ] **Step 2: Set body data attributes**

In `templates/base.html`, locate the `<body>` tag. Replace it with:

```html
<body data-theme="dark" data-hue="blue" data-glass="heavy" data-kpi-style="minimal">
```

Note: if the existing `<body>` tag already has classes or other attributes, preserve them and merge. For example if it reads `<body class="has-sidebar">`, change to:
```html
<body class="has-sidebar" data-theme="dark" data-hue="blue" data-glass="heavy" data-kpi-style="minimal">
```

- [ ] **Step 3: Add the theme-toggle script early in `<body>`**

Immediately after the opening `<body ...>` tag, add:

```html
<script src="{{ url_for('static', filename='js/theme-toggle.js') }}"></script>
```

Important: not `defer`, not at the bottom — it must run before the page paints so the saved theme is applied without a flash.

- [ ] **Step 4: Add the theme-toggle button to the header**

Find the existing navigation/header area in `base.html`. Locate a logical place near the user menu or branding (the mobile-first header). Add:

```html
<button type="button"
        data-theme-toggle
        aria-pressed="true"
        class="nav-pill"
        title="Alternar tema claro/oscuro"
        aria-label="Alternar tema claro/oscuro">
  <i class="fas fa-moon theme-icon-dark" aria-hidden="true"></i>
  <i class="fas fa-sun theme-icon-light" aria-hidden="true"></i>
</button>
```

Then, in the `<style>` block inside `<head>`, add these lines (or append to the existing one):

```css
/* Theme-toggle icon swap */
[data-theme="dark"] .theme-icon-light { display: none; }
[data-theme="light"] .theme-icon-dark { display: none; }
```

- [ ] **Step 5: Add the bottom tabbar**

Find the end of the template's main content area, just before `{% block scripts %}` or `</body>` (whichever comes first). Add the tabbar:

```html
<nav class="tabbar" aria-label="Navegación principal">
  <a href="{{ url_for('dashboard') }}" class="tab {% if request.endpoint == 'dashboard' %}active{% endif %}">
    <i class="fas fa-chart-pie" aria-hidden="true"></i>
    Dashboard
  </a>
  <a href="{{ url_for('pedidos') }}" class="tab {% if request.endpoint in ['pedidos', 'detalles_pedido'] %}active{% endif %}">
    <i class="fas fa-receipt" aria-hidden="true"></i>
    Pedidos
  </a>
  <a href="{{ url_for('productos') }}" class="tab {% if request.endpoint == 'productos' %}active{% endif %}">
    <i class="fas fa-box" aria-hidden="true"></i>
    Productos
  </a>
  <a href="#" class="tab" onclick="event.preventDefault(); document.getElementById('mobile-menu-toggle')?.click();">
    <i class="fas fa-bars" aria-hidden="true"></i>
    Más
  </a>
</nav>
```

Note: the Jinja route names `dashboard`, `pedidos`, `productos`, `detalles_pedido` match the existing Flask routes in `app.py`. If any `url_for()` fails (unknown endpoint), fall back to hardcoded `/dashboard`, `/pedidos`, `/productos`.

- [ ] **Step 6: Smoke test the home page locally**

Start the dev server (in a separate terminal):

```bash
flask --app app run --port 5001
```

Visit `http://localhost:5001/dashboard` (or whatever requires login; log in first). Verify:
- Page renders without 500 errors.
- Browser DevTools shows `app-mobile.css` loaded (network tab).
- `<body>` has `data-theme="dark" data-hue="blue" data-glass="heavy" data-kpi-style="minimal"`.
- Theme toggle button appears and alternates icon on click.
- Reload the page — theme persists.

Stop the server (Ctrl+C).

- [ ] **Step 7: Commit**

```bash
git add templates/base.html
git commit -m "feat(base): link app-mobile.css, add theme toggle + bottom tabbar"
```

---

### Task 10: Restyle `templates/dashboard.html`

**Files:**
- Modify: `templates/dashboard.html`
- Reference: `_bmad-output/design-reference/src/screens/Dashboard.jsx` (markup patterns)

- [ ] **Step 1: Wrap the page in `.app-shell`**

In `templates/dashboard.html`, find the outermost container inside `{% block content %}`. Wrap it:

```jinja
{% block content %}
<div class="app-shell">
  <!-- existing dashboard content goes here unchanged -->
</div>
{% endblock %}
```

- [ ] **Step 2: Add the hero section above the panels**

Immediately inside `.app-shell`, before any existing panel markup, add:

```jinja
<header class="hero">
  <div class="hero-kicker">Hoy · {{ hoy.strftime('%A %d de %B') if hoy is defined else '' }}</div>
  <h1 class="hero-title">Hola, {{ current_user.nombre if current_user.is_authenticated else '' }}</h1>
  <p class="hero-sub">Panel de ventas y servicio — en vivo.</p>
</header>
```

Note: if `current_user.nombre` does not exist on your User model, use `current_user.username`. If `hoy` is not passed to the template context, drop the kicker or add `hoy = datetime.now()` in the corresponding `app.py` view (a docs-only context change — allowed by this spec only if the view already computes dates; otherwise drop the kicker line).

- [ ] **Step 3: Wrap each panel (Ventas, Servicio, Top, Pedidos) in `.gcard`**

For each existing panel `<section>` or `<div class="panel-*">`, add the `.gcard` class (or wrap in `<div class="gcard">`).

Example pattern (apply to each panel):
```html
<!-- Before -->
<section class="panel-ventas">
  ...existing KPI tiles...
</section>

<!-- After -->
<section class="panel-ventas gcard">
  ...existing KPI tiles...
</section>
```

Note: the existing panel markup includes JS hooks (classes, data- attributes). **Do not change** any data- attributes or IDs — the carousel controller and chart-mount code rely on them.

- [ ] **Step 4: Restyle KPI tiles to use `.kpi-grid` + `.kpi`**

For each block of 2+ KPI boxes inside a panel, wrap them in `.kpi-grid` and add `.kpi` to each tile:

```html
<!-- Before -->
<div class="ventas-kpis">
  <div class="kpi-box">
    <span class="label">Meta</span>
    <span class="value">120k</span>
  </div>
  <div class="kpi-box">
    <span class="label">Alcanzado</span>
    <span class="value">78k</span>
  </div>
</div>

<!-- After -->
<div class="kpi-grid">
  <div class="kpi">
    <div class="kpi-top">
      <div class="kpi-label">Meta</div>
    </div>
    <div class="kpi-value">120<small>k</small></div>
  </div>
  <div class="kpi">
    <div class="kpi-top">
      <div class="kpi-label">Alcanzado</div>
    </div>
    <div class="kpi-value">78<small>k</small></div>
  </div>
</div>
```

Preserve existing IDs and `data-` attributes on the tiles so any existing Chart.js mount points keep working.

- [ ] **Step 5: Chart.js color adaptation (inline template script only)**

If `dashboard.html` contains an inline `<script>` block that initializes a Chart.js chart, locate the dataset config and change any hardcoded hex colors to:

```js
borderColor: getComputedStyle(document.body).getPropertyValue('--indigo-500').trim() || '#2563eb',
backgroundColor: 'rgba(37, 99, 235, 0.12)',
```

Allowed only if the Chart.js config is **inside a template `<script>` tag**. If it lives in a separate `.js` file under `static/js/`, skip this step to honor the "zero existing JS changes" guard.

- [ ] **Step 6: Smoke test locally**

Start the dev server:

```bash
flask --app app run --port 5001
```

Visit `/dashboard`. Verify:
- Hero title renders with the user's name.
- All 4 panels show with the glass card look.
- Carousel nav still switches panels (the existing JS controller must work — if it does not, revert Step 3 for the broken panel and report; do not attempt to fix the JS).
- KPI numbers match the values rendered before the reskin (compare against a screenshot taken at the start of the session if available).
- Chart/sparkline still renders (the dataset values are unchanged; only colors differ if Step 5 applied).

Stop the server.

- [ ] **Step 7: Run tests**

Run: `pytest tests/ -x -q 2>&1 | tail -40`

Expected: all existing dashboard-related tests pass. If a selector-based test fails because the markup now has `.gcard` wrapping, update the selector in the test — the business logic has not changed.

- [ ] **Step 8: Commit**

```bash
git add templates/dashboard.html
git commit -m "feat(dashboard): apply glass card + kpi grid, add hero section"
```

---

### Task 11: Restyle `templates/pedidos.html` — table to cards

**Files:**
- Modify: `templates/pedidos.html`
- Reference: `_bmad-output/design-reference/src/screens/PedidosList.jsx`

- [ ] **Step 1: Read the current template to identify the existing table**

Run: `grep -n "<table\|<tr\|<td\|for .* in .*pedidos" templates/pedidos.html | head -20`

Locate the `{% for pedido in pedidos %}` loop that generates the rows. Note the Jinja variable names used on each `pedido` (e.g., `pedido.id`, `pedido.cliente.nombre`, `pedido.total`, `pedido.fecha_entrega`, `pedido.estado`).

- [ ] **Step 2: Wrap content in `.app-shell` with hero + search + chips**

Find `{% block content %}`. Restructure as:

```jinja
{% block content %}
<div class="app-shell">
  <header class="hero">
    <div class="hero-kicker">Pedidos</div>
    <h1 class="hero-title">Lista</h1>
  </header>

  <div class="search-pill">
    <i class="fas fa-search" aria-hidden="true"></i>
    <input type="search" placeholder="Buscar pedido, cliente o PED-" id="pedidos-search" autocomplete="off">
  </div>

  <div class="chips-row" role="tablist" aria-label="Filtrar pedidos">
    <button type="button" class="fchip active" data-filter="todos">
      Todos <span class="fcount">{{ pedidos|length }}</span>
    </button>
    <button type="button" class="fchip" data-filter="pendiente">Pendientes</button>
    <button type="button" class="fchip" data-filter="preparado">Preparados</button>
    <button type="button" class="fchip" data-filter="facturado">Facturados</button>
  </div>

  <div class="pedidos-list">
    {# existing pedidos loop replaced below #}
  </div>
</div>
{% endblock %}
```

- [ ] **Step 3: Replace the table `<tr>` loop with card markup**

Inside `.pedidos-list`, replace the old `<table>` + `<tr>` loop with:

```jinja
{% for pedido in pedidos %}
<a href="{{ url_for('detalles_pedido', pedido_id=pedido.id) }}"
   class="pedido-card"
   data-estado="{{ pedido.estado|lower }}"
   data-search="{{ (pedido.numero ~ ' ' ~ pedido.cliente.nombre)|lower }}">
  <div class="pc-top">
    <div>
      <div class="pc-id">PED-{{ pedido.numero or pedido.id }}</div>
      <div class="pc-client">{{ pedido.cliente.nombre }}</div>
    </div>
    <div class="pc-amt">
      {{ '{:,.0f}'.format(pedido.total or 0) }}
      <small>{{ pedido.cliente.moneda or 'XCG' }}</small>
    </div>
  </div>

  <div class="pc-meta">
    <span><i class="fas fa-boxes" aria-hidden="true"></i> {{ pedido.detalles|length }} líneas</span>
    {% if pedido.fecha_entrega %}
    <span><i class="fas fa-calendar" aria-hidden="true"></i> {{ pedido.fecha_entrega.strftime('%d/%m') }}</span>
    {% endif %}
  </div>

  <div class="pc-foot">
    <span class="status-pill {{ pedido.estado|lower }}">{{ pedido.estado }}</span>
    {% if pedido.fecha_entrega %}
    {% set delta = (pedido.fecha_entrega - hoy).days if hoy is defined else 0 %}
    <span class="sla {% if delta < 0 %}danger{% elif delta <= 1 %}warn{% endif %}">
      <span class="dot"></span>
      {% if delta < 0 %}Vencido {{ -delta }}d{% elif delta == 0 %}Hoy{% else %}{{ delta }}d{% endif %}
    </span>
    {% endif %}
  </div>
</a>
{% else %}
<p style="text-align: center; color: var(--color-text-muted); padding: 40px 0;">
  No hay pedidos para mostrar.
</p>
{% endfor %}
```

Important adjustments:
- If the production `Pedido` model uses different attribute names (e.g., `pedido.numero_pedido` instead of `pedido.numero`), update the Jinja expressions to match. Check `app.py` for the `Pedido` model definition.
- If `hoy` is not available in the template context, drop the SLA `<span>` block rather than passing a new variable (backend changes are out of scope per the spec).

- [ ] **Step 4: Add client-side filter JS (inline in the template, not a new file)**

Below the closing `</div>` of `.app-shell`, before `{% endblock %}`, add:

```html
<script>
(function () {
  var searchInput = document.getElementById('pedidos-search');
  var chips = document.querySelectorAll('.chips-row .fchip');
  var cards = document.querySelectorAll('.pedido-card');
  var activeFilter = 'todos';
  var activeSearch = '';

  function apply() {
    var total = 0;
    cards.forEach(function (card) {
      var matchesFilter = activeFilter === 'todos' || card.dataset.estado === activeFilter;
      var matchesSearch = !activeSearch || (card.dataset.search || '').indexOf(activeSearch) !== -1;
      var show = matchesFilter && matchesSearch;
      card.style.display = show ? '' : 'none';
      if (show) total++;
    });
    var allChip = document.querySelector('.fchip[data-filter="todos"] .fcount');
    if (allChip) allChip.textContent = total;
  }

  chips.forEach(function (chip) {
    chip.addEventListener('click', function () {
      chips.forEach(function (c) { c.classList.remove('active'); });
      chip.classList.add('active');
      activeFilter = chip.dataset.filter;
      apply();
    });
  });

  if (searchInput) {
    searchInput.addEventListener('input', function () {
      activeSearch = searchInput.value.trim().toLowerCase();
      apply();
    });
  }
})();
</script>
```

This script is **new code inside the template** — it does not count as modifying an existing JS file.

- [ ] **Step 5: Smoke test locally**

Start the dev server and visit `/pedidos`. Verify:
- All pedidos appear as cards (no table).
- Search filters the list as you type.
- Chips filter by estado.
- Clicking a card opens the detail page (existing `/pedidos/<id>/detalles` route).
- Count on the "Todos" chip updates as filters are applied.

- [ ] **Step 6: Run tests**

Run: `pytest tests/ -x -q -k "pedido" 2>&1 | tail -40`

If any test asserts on `<table>` markup, update the selector to match the new `.pedido-card` structure. Do not change what the test asserts about data — only the DOM selector.

- [ ] **Step 7: Commit**

```bash
git add templates/pedidos.html
git commit -m "feat(pedidos): replace table with card list, add search + filter chips"
```

---

### Task 12: Restyle `templates/detalles_pedido.html`

**Files:**
- Modify: `templates/detalles_pedido.html`
- Reference: `_bmad-output/design-reference/src/screens/PedidoDetail.jsx`

- [ ] **Step 1: Read the current template structure**

Run: `head -80 templates/detalles_pedido.html`

Identify:
- The outer `{% block content %}` wrapper.
- Where the pedido header (cliente, numero, total) is rendered.
- Where the `detalles` (line items) loop is.
- Where action buttons live (Marcar preparado, Facturar).

Note the variable names used (e.g., `pedido.cliente.nombre`, `detalle.producto.nombre`, `detalle.cantidad`, `detalle.peso`, `detalle.pesado`).

- [ ] **Step 2: Wrap in `.app-shell` and add the gradient hero**

Find `{% block content %}`. Restructure as:

```jinja
{% block content %}
<div class="app-shell">
  <header class="detail-hero">
    <div class="dh-row">
      <div>
        <div class="dh-id">PED-{{ pedido.numero or pedido.id }}</div>
        <div class="dh-client">{{ pedido.cliente.nombre }}</div>
        <div class="dh-meta">
          {% if pedido.fecha_entrega %}
            Entrega: {{ pedido.fecha_entrega.strftime('%A %d de %B') }}
          {% endif %}
        </div>
      </div>
      <span class="status-pill {{ pedido.estado|lower }}"
            style="background: rgba(255,255,255,0.18); color: white;">
        {{ pedido.estado }}
      </span>
    </div>
    <div class="dh-stats">
      <div class="dh-stat">
        <div class="dh-stat-label">Cajas</div>
        <div class="dh-stat-val">{{ pedido.detalles|sum(attribute='cantidad')|int or 0 }}</div>
      </div>
      <div class="dh-stat">
        <div class="dh-stat-label">Peso total</div>
        <div class="dh-stat-val">{{ '{:.1f}'.format(pedido.detalles|sum(attribute='peso') or 0) }} <small>kg</small></div>
      </div>
      <div class="dh-stat">
        <div class="dh-stat-label">Total</div>
        <div class="dh-stat-val">{{ '{:,.0f}'.format(pedido.total or 0) }}</div>
      </div>
    </div>
  </header>

  {# existing tabs and content below #}
</div>
{% endblock %}
```

Note: `pedido.detalles|sum(attribute='peso')` assumes the `DetallePedido` model has a `peso` attribute. If it does not, drop the Peso stat or compute from cantidad × peso_unitario. Verify against the model before shipping.

- [ ] **Step 3: Add the 4-step timeline**

Immediately after `.detail-hero`, add:

```jinja
{% set estado = (pedido.estado or '')|lower %}
{% set steps = [
  ('creado',     'Pedido creado',     'fa-plus-circle'),
  ('preparado',  'Preparado',         'fa-box'),
  ('facturado',  'Facturado',         'fa-file-invoice'),
  ('entregado',  'Entregado',         'fa-truck'),
] %}
{% set active_idx = {'pendiente': 0, 'preparado': 1, 'facturado': 2, 'entregado': 3}.get(estado, 0) %}
<div class="gcard timeline" style="margin: 0 16px 14px;">
  {% for key, label, icon in steps %}
    {% set idx = loop.index0 %}
    <div class="tl-item">
      <span class="tl-dot {% if idx < active_idx %}done{% elif idx == active_idx %}active{% endif %}"></span>
      <div class="tl-title">{{ label }}</div>
      <div class="tl-meta">
        {% if idx < active_idx %}Completado
        {% elif idx == active_idx %}En curso
        {% else %}Pendiente{% endif %}
      </div>
    </div>
  {% endfor %}
</div>
```

- [ ] **Step 4: Replace the detalles (line items) loop**

Find the existing `{% for detalle in pedido.detalles %}` block. Replace the markup inside the loop (not the loop itself) with:

```jinja
<div class="gcard" style="margin: 0 16px 14px; padding: 0;">
  <div class="line-items">
    {% for detalle in pedido.detalles %}
      <div class="line-item" data-cat="{{ (detalle.producto.categoria or 'default')|lower }}">
        <div class="li-strip"></div>
        <div class="li-body">
          <div class="li-name">{{ detalle.producto.nombre }}</div>
          <div class="li-meta">
            {{ detalle.cantidad }} cajas ·
            {% if detalle.precio_unitario %}{{ '{:.2f}'.format(detalle.precio_unitario) }} / kg{% endif %}
          </div>
        </div>
        <div class="li-qty">
          {% if detalle.peso %}{{ '{:.1f}'.format(detalle.peso) }}<small>kg</small>{% else %}—{% endif %}
        </div>
      </div>
    {% endfor %}
  </div>
</div>
```

Adjust attribute names to match the production `DetallePedido` model. If `detalle.producto.categoria` does not exist, drop the `data-cat` attribute — the item will default to the indigo strip via CSS.

- [ ] **Step 5: Add the sticky action bar at the bottom of content**

Before `{% endblock %}`, add:

```jinja
{% if pedido.estado|lower in ['pendiente', 'preparado'] %}
<div class="action-bar">
  {% if pedido.estado|lower == 'pendiente' %}
    <form method="post" action="{{ url_for('marcar_preparado', pedido_id=pedido.id) }}" style="flex:1;">
      {{ csrf_token_input() if csrf_token_input is defined else '' }}
      <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
      <button type="submit" class="btn-primary" style="width: 100%;">Marcar preparado</button>
    </form>
  {% elif pedido.estado|lower == 'preparado' %}
    <form method="post" action="{{ url_for('facturar', pedido_id=pedido.id) }}" style="flex:1;">
      <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
      <button type="submit" class="btn-primary" style="width: 100%;">Facturar</button>
    </form>
  {% endif %}
  <a href="{{ url_for('pedidos') }}" class="btn-secondary" style="display:grid;place-items:center;text-decoration:none;">Volver</a>
</div>
{% endif %}
```

Adjust the `url_for()` endpoint names to match actual Flask route names in `app.py`. If the buttons currently work via a different mechanism (AJAX, JS handler), preserve that handler by copying its `onclick`/data attributes onto the new button.

- [ ] **Step 6: Smoke test locally**

Start the dev server and visit `/pedidos`, click a pedido card. Verify:
- Gradient hero renders with client name + KPIs (cajas, peso, total).
- Timeline shows 4 steps with the correct one active.
- Line items show with colored strip on the left, weight on the right.
- Action bar appears at the bottom with context-appropriate buttons.
- Clicking `Marcar preparado` / `Facturar` still triggers the existing backend endpoint (no JS changes — forms post as before).

- [ ] **Step 7: Run tests**

Run: `pytest tests/ -x -q -k "detalle or pedido" 2>&1 | tail -40`

- [ ] **Step 8: Commit**

```bash
git add templates/detalles_pedido.html
git commit -m "feat(detalle): gradient hero, timeline, line-items, sticky action bar"
```

---

## Part D — Verification

### Task 13: Add a smoke test for the reskinned routes

**Files:**
- Create or extend: `tests/test_reskin_smoke.py`

- [ ] **Step 1: Check if tests require login**

Run: `grep -l "client.post.*login\|login_user" tests/*.py | head -3`

Note the pattern used for authenticated test clients. Reuse the fixture/helper in the new test.

- [ ] **Step 2: Create the smoke test**

Write `tests/test_reskin_smoke.py`:

```python
"""Smoke tests for the Glass Mobile Reskin — spec 2026-04-17-glass-mobile-reskin-design.md."""

import pytest


@pytest.fixture
def authed_client(client, app):
    """Placeholder fixture — Step 3 of this task wires it to the real auth helper.

    If `tests/conftest.py` already exposes an authenticated-client fixture
    (common names: `authed_client`, `logged_in_client`, `admin_client`),
    delete this fixture entirely and rename the test parameter to match.
    """
    return client


@pytest.mark.parametrize("path", [
    "/dashboard",
    "/pedidos",
])
def test_reskin_routes_return_200(authed_client, path):
    response = authed_client.get(path)
    assert response.status_code == 200, f"{path} returned {response.status_code}"


def test_app_mobile_css_is_linked(authed_client):
    response = authed_client.get("/dashboard")
    assert b"css/app-mobile.css" in response.data, \
        "app-mobile.css link missing from /dashboard"


def test_body_has_reskin_data_attributes(authed_client):
    response = authed_client.get("/dashboard")
    html = response.data
    assert b'data-theme="dark"' in html
    assert b'data-hue="blue"' in html
    assert b'data-glass="heavy"' in html
    assert b'data-kpi-style="minimal"' in html


def test_theme_toggle_script_is_linked(authed_client):
    response = authed_client.get("/dashboard")
    assert b"js/theme-toggle.js" in response.data
```

- [ ] **Step 3: Wire the `authed_client` fixture to the real helper**

Run: `cat tests/conftest.py 2>/dev/null | head -60`

If there is already a fixture that returns an authenticated client (look for names like `authed_client`, `logged_in_client`, `admin_client`), remove the placeholder fixture from `test_reskin_smoke.py` and rename the parameter to match.

If no such fixture exists, inline one that posts to the login route used by the existing tests (look for `client.post('/login', ...)` in other tests and mimic the pattern).

- [ ] **Step 4: Run the smoke tests**

Run: `pytest tests/test_reskin_smoke.py -v 2>&1 | tail -30`

Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add tests/test_reskin_smoke.py
git commit -m "test(reskin): smoke tests for mobile reskin routes + asset links"
```

---

### Task 14: Full test suite + regression guards

**Files:**
- none (verification only)

- [ ] **Step 1: Run the full pytest suite**

Run: `pytest tests/ -q 2>&1 | tail -30`

Expected: all existing tests pass plus the new smoke tests. If any test fails due to markup changes (selectors), update the selector — do not relax assertions on business logic.

- [ ] **Step 2: Regression guard — no existing JS files modified**

Run: `git diff main -- static/js/ | head -80`

Expected output:
```
diff --git a/static/js/theme-toggle.js b/static/js/theme-toggle.js
new file mode 100644
...
```

There must be no `modified:` lines for any other `static/js/*.js` file. If there are, revert those changes — they violate the regression guard that mitigates the Phase 3 bug.

Also verify `base.min.js` is untouched:

Run: `git diff main -- static/js/base.min.js static/js/base.js`
Expected: empty output.

- [ ] **Step 3: Regression guard — no app.py or model changes**

Run: `git diff main -- app.py models.py extensions.py 2>&1 | head -20`

Expected: empty output.

If any of these were modified, abort and roll back — the spec is explicit that backend is out of scope.

- [ ] **Step 4: Commit (if tests needed selector updates)**

If Step 1 required updating test selectors, stage and commit them:

```bash
git add tests/
git commit -m "test: update selectors to match reskin markup"
```

If no test changes were needed, skip this commit.

---

### Task 15: Deploy to Heroku staging and run manual QA

**Files:**
- none (deployment)

- [ ] **Step 1: Ensure the Heroku staging app exists**

Run: `heroku apps | grep pesosapp-staging`

If missing, create it (requires user confirmation — do not run unattended):

```bash
heroku create pesosapp-staging
```

Then point its DATABASE_URL at the production database (or provision a fresh one — user's choice; the spec notes this is a reskin-only change with no data impact, so sharing production DB is acceptable for a short test window).

- [ ] **Step 2: Push the feature branch to staging**

Run:

```bash
git push https://git.heroku.com/pesosapp-staging.git feat/glass-mobile-reskin:main
```

Expected: build succeeds, new release deployed.

- [ ] **Step 3: Run the manual QA checklist**

Open `pesosapp-staging.herokuapp.com` on:
1. Mobile viewport in Chrome DevTools (iPhone 13 Pro — 390×844).
2. A real iPhone if available.

Verify on each device:

- [ ] Dashboard renders; Chart.js sparkline displays; carousel still switches panels.
- [ ] KPI numbers on the dashboard match production (open prod in another window and compare one-by-one — there must be no data difference, only visual).
- [ ] Date navigation on dashboard (arrows, picker) works.
- [ ] `/pedidos` list shows cards, search filters as you type, chip filters switch subsets.
- [ ] Tapping a pedido card opens the detail page.
- [ ] Detail page: gradient hero shows, timeline shows with correct active step, line items show with color strip + weight.
- [ ] `Marcar preparado` / `Facturar` buttons trigger the backend and update the pedido (test with a safe pedido — or create a dummy one on staging).
- [ ] Theme toggle alternates dark/light; value persists across page reloads.
- [ ] No console errors on any of the 3 pages.
- [ ] Bottom tabbar appears and navigates between Dashboard, Pedidos, Productos, Más.

- [ ] **Step 4: Record results**

In `_bmad-output/implementation-artifacts/glass-mobile-reskin-qa.md`, record:
- Date and device(s) tested.
- Checklist state (pass/fail per item, with notes for any fail).
- Screenshots if any issue surfaces.

Commit the artifact:

```bash
git add _bmad-output/implementation-artifacts/glass-mobile-reskin-qa.md
git commit -m "docs: glass mobile reskin QA results"
```

---

### Task 16: Open pull request to main

**Files:**
- none (git + GitHub)

- [ ] **Step 1: Push the branch to origin**

Run: `git push -u origin feat/glass-mobile-reskin`

- [ ] **Step 2: Open the PR**

Run:

```bash
gh pr create --base main --title "Glass mobile reskin — Dashboard + Pedidos + Detalle (#23 continuation, Phase 3 redo)" --body "$(cat <<'EOF'
## Summary

Apply the iterated Claude Design prototype to the 3 main screens and the shared chrome in mobile-first form. Dark theme, heavy glass, blue hue, minimal KPI. Zero backend changes.

This is the spiritual successor to PR #24 (Phase 3, reverted). The reskin this time:
- Uses the user-approved iterated design (not the original Phase 3 attempt).
- Does not touch any existing JS file — the Phase 3 bug is believed to have lived in the new `dashboard-tabs.js` controller.
- Adds only one new JS file (`theme-toggle.js`, ~25 LOC, self-contained).
- Layered CSS: `app-mobile.css` loads last and wins by order — fully revertible by removing the link.

## Scope

- New: `static/css/app-mobile.css`, `static/js/theme-toggle.js`
- Modified: `static/css/tokens.css` (hue variants), `templates/base.html`, `templates/dashboard.html`, `templates/pedidos.html`, `templates/detalles_pedido.html`
- Out of scope: Pesar screen (new feature), secondary pages, all backend changes

## Testing

- [x] All existing pytest tests pass (updated selectors where markup changed).
- [x] New smoke tests in `tests/test_reskin_smoke.py` cover route 200s + asset links.
- [x] Manual QA checklist on `pesosapp-staging` — see `_bmad-output/implementation-artifacts/glass-mobile-reskin-qa.md`.
- [x] Regression guard passed: no changes to any `static/js/*.js` except the new `theme-toggle.js`.

## References

- Spec: `docs/superpowers/specs/2026-04-17-glass-mobile-reskin-design.md`
- Plan: `docs/superpowers/plans/2026-04-17-glass-mobile-reskin.md`
- Design reference (Claude Design bundle): `_bmad-output/design-reference/`

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

- [ ] **Step 3: Return the PR URL to the user**

Paste the URL produced by `gh pr create` so the user can review before merging. Do not merge unattended.

---

## Appendix A — Rollback plan

If anything breaks in production after merge:

```bash
# From main:
git revert <merge-commit-sha>
git push origin main
```

All reskin changes are additive — removing them restores the prior UI.

Single-file kill switch (no revert needed, for immediate emergencies):
1. Edit `templates/base.html`, comment out the `app-mobile.css` link and the `theme-toggle.js` script tag.
2. Commit + push: Heroku redeploys in ~60s.

## Appendix B — Files reference

**Source prototype (in repo for stable paths):**
- `_bmad-output/design-reference/src/app.css` — full prototype stylesheet (1014 LOC)
- `_bmad-output/design-reference/src/screens/Dashboard.jsx` — dashboard markup (292 LOC)
- `_bmad-output/design-reference/src/screens/PedidosList.jsx` — list markup (158 LOC)
- `_bmad-output/design-reference/src/screens/PedidoDetail.jsx` — detail markup (363 LOC)
- `_bmad-output/design-reference/prototype-index.html` — prototype shell (reference only)

**Memory notes (from MEMORY.md):**
- If migrations are ever needed, apply to Heroku too via `heroku pg:psql`. This plan does not modify the schema, so skip.
- After schema changes, restart the dyno. This plan does not modify the schema, so skip.
- Minified files (`base.min.js`, `styles.min.css`, `css/main.min.css`) are regenerated from source — this plan does not edit them.
