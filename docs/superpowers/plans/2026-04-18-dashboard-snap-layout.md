# Dashboard Snap Layout Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Convert the Ventas y Servicio panels of the mobile dashboard to a vertical scroll-snap layout (one KPI per ~85vh, chart per ~90vh), and switch the dashboard content area to a high-contrast dark scheme with opaque glass cards.

**Architecture:** Add a NEW CSS file (`dashboard_snap.css`) loaded after the existing `dashboard_light.css`, so its dark + snap rules win by source order without removing the light theme. Add a tiny ~25-LOC JS module (`dashboard-snap-dots.js`) using `IntersectionObserver` to drive a vertical pagination indicator. Touch `dashboard.html` minimally — only inject `data-snap-card="1"` hooks on existing KPIs/cards and add empty `<div class="snap-dots">` slots that the JS populates.

**Tech Stack:** Flask/Jinja2, vanilla CSS (no preprocessor — minified files are committed in repo, but the project edits the source files directly per CLAUDE.md memory), vanilla JS (no framework), Chart.js (untouched), pytest for smoke tests.

**Spec:** `docs/superpowers/specs/2026-04-18-dashboard-snap-layout-design.md`

**Pre-flight knowledge:**
- The dashboard is currently in LIGHT mode in production: `dashboard_light.css` overrides the dark theme to white cards on slate background. This plan **adds dark + snap on top** of it; we do NOT delete the light file in this iteration so the change is purely additive and easy to revert.
- `body[data-theme="dark"]` is set on `<body>` but currently neutralized for the dashboard content by `dashboard_light.css`. The new file restores dark for content area only (topbar/tabbar already inherit dark).
- The horizontal carousel between tabs (Ventas/Servicio/Top/Actividad) is driven by JS that translates `.panels-track` via `transform`. Snap containers must NOT be ancestors of the track or the transform will fight the snap. The track sits inside `#dash-viewport`; each `.dash-panel` is a sibling within `.panels-track`. We add `overflow-y: auto; scroll-snap-type: y mandatory` to the **panel itself** (`.dash-panel[data-dash-panel="ventas"]`), so the snap is scoped to one tab's content and doesn't fight the horizontal transform.
- Top y Actividad panels are EXPLICITLY excluded from snap behavior.
- Tests live in `tests/`. Smoke tests follow the pattern in `tests/test_reskin_smoke.py` (logged-in client, assert route 200, assert asset links present).
- The Heroku auto-deploys on `git push` to `main`. We commit per task; a single combined push at the end is fine.

---

### Task 1: Add markup hooks to `dashboard.html` (no visual change yet)

**Files:**
- Modify: `templates/dashboard.html` (Ventas panel ~lines 598-693, Servicio panel ~lines 698-729)

This task only adds attributes and empty divs. The page renders identically until Task 3 wires the CSS.

- [ ] **Step 1: Add `data-snap-card="1"` to each KPI/card in the Ventas panel**

In `templates/dashboard.html`, inside `<div class="dash-panel" data-dash-panel="ventas">`, add `data-snap-card="1"` to each of the 4 `.kpi` divs, the `.gcard.chart-card`, and the `.week-mini-grid`.

Example for the first KPI (around line 604):

```jinja
<div class="kpi" data-snap-card="1">
  <div class="kpi-top">
    <div class="kpi-label">Ventas del Mes</div>
```

Repeat for: Proyección (line ~614), On-Time Delivery (~628), Pendientes (~638), `<div class="gcard chart-card" data-snap-card="1">` (~656), `<div class="week-mini-grid" data-snap-card="1">` (~678).

- [ ] **Step 2: Add `data-snap-card="1"` to each KPI in the Servicio panel**

Inside `<div class="dash-panel" data-dash-panel="servicio">`, the loop generating 6 KPIs (~lines 712-726) renders `<div class="kpi">`. Update to `<div class="kpi" data-snap-card="1">`.

- [ ] **Step 3: Add empty `snap-dots` slots before each panel**

Right BEFORE `<div class="dash-panel" data-dash-panel="ventas">` (~line 598), insert:

```jinja
<div class="snap-dots" data-snap-dots-for="ventas" aria-hidden="true"></div>
```

Right BEFORE `<div class="dash-panel" data-dash-panel="servicio">` (~line 698), insert:

```jinja
<div class="snap-dots" data-snap-dots-for="servicio" aria-hidden="true"></div>
```

The JS in Task 4 fills these with one `<span>` per snap card.

- [ ] **Step 4: Verify the page still loads and tests pass**

Run:
```bash
.venv311/bin/python -m pytest tests/test_reskin_smoke.py -v
```
Expected: all tests pass (no behavior changed, only attributes added).

- [ ] **Step 5: Commit**

```bash
git add templates/dashboard.html
git commit -m "feat(dashboard): mark snap targets in Ventas/Servicio panels"
```

---

### Task 2: Add smoke test for snap markup (will fail; pins requirements)

**Files:**
- Modify: `tests/test_reskin_smoke.py`

- [ ] **Step 1: Add the failing test**

Append to `tests/test_reskin_smoke.py`:

```python
# ---------------------------------------------------------------------------
# Dashboard snap layout
# Spec: docs/superpowers/specs/2026-04-18-dashboard-snap-layout-design.md
# ---------------------------------------------------------------------------


def test_dashboard_snap_css_is_linked(logged_client):
    response = logged_client.get("/dashboard")
    assert b"css/dashboard_snap.css" in response.data, (
        "dashboard_snap.css link missing from /dashboard"
    )


def test_dashboard_snap_dots_js_is_linked(logged_client):
    response = logged_client.get("/dashboard")
    assert b"js/dashboard-snap-dots.js" in response.data, (
        "dashboard-snap-dots.js link missing from /dashboard"
    )


def test_dashboard_ventas_panel_has_snap_cards(logged_client):
    """Spec: 4 snap targets in Ventas (4 KPIs + chart + week mini = 6 total)."""
    response = logged_client.get("/dashboard")
    html = response.data
    # Coarse but reliable: count occurrences of the marker inside the rendered HTML.
    # Ventas panel has 4 KPIs + 1 chart + 1 week-mini = 6 snap cards minimum.
    # Servicio adds 6 more = 12 total.
    assert html.count(b'data-snap-card="1"') >= 12, (
        "Expected at least 12 snap-card markers (Ventas 6 + Servicio 6); "
        f"found {html.count(b'data-snap-card=\"1\"')}"
    )


def test_dashboard_snap_dots_slots_present(logged_client):
    response = logged_client.get("/dashboard")
    html = response.data
    assert b'data-snap-dots-for="ventas"' in html, "snap-dots slot for Ventas missing"
    assert b'data-snap-dots-for="servicio"' in html, "snap-dots slot for Servicio missing"
```

- [ ] **Step 2: Run the test, confirm the markup-already-present ones pass**

```bash
.venv311/bin/python -m pytest tests/test_reskin_smoke.py::test_dashboard_ventas_panel_has_snap_cards tests/test_reskin_smoke.py::test_dashboard_snap_dots_slots_present -v
```
Expected: both PASS (Task 1 added the markup).

- [ ] **Step 3: Run the asset-link tests, confirm they fail**

```bash
.venv311/bin/python -m pytest tests/test_reskin_smoke.py::test_dashboard_snap_css_is_linked tests/test_reskin_smoke.py::test_dashboard_snap_dots_js_is_linked -v
```
Expected: both FAIL — the CSS and JS files are not yet linked.

- [ ] **Step 4: Commit**

```bash
git add tests/test_reskin_smoke.py
git commit -m "test(dashboard): smoke tests for snap layout assets and markup"
```

---

### Task 3: Create `dashboard_snap.css` with snap layout + dark scheme

**Files:**
- Create: `static/css/dashboard_snap.css`

Single file containing all of: snap container/cards, KPI scaling, bigger chart, dark background, opaque glass, snap dots styling, desktop fallback.

- [ ] **Step 1: Create `static/css/dashboard_snap.css` with the full content below**

```css
/* =============================================================================
   Dashboard · Snap Layout + High-Contrast Dark
   Spec: docs/superpowers/specs/2026-04-18-dashboard-snap-layout-design.md

   Loaded AFTER dashboard_light.css so its rules win by source order.
   Scope: body[data-dashboard-screen] only — does not affect other pages.
   Mobile/tablet only (<1024px). Desktop falls back to existing grid layout.
   ============================================================================= */

@media (max-width: 1023px) {

  /* ── 1. Dark background + opaque glass ───────────────────────────────── */

  body[data-dashboard-screen] .app-content,
  body[data-dashboard-screen] .app-shell,
  body[data-dashboard-screen] .app-shell.dash-body,
  body[data-dashboard-screen] .screen-body {
    background: #0a0e1f !important;
    background-image: none !important;
    color: #f8fafc;
  }

  /* Re-scope content tokens to dark so descendants pick the right colors. */
  body[data-dashboard-screen] .app-content,
  body[data-dashboard-screen] .app-shell.dash-body,
  body[data-dashboard-screen] .screen-body {
    --color-bg: #0a0e1f;
    --color-bg-elevated: #131a30;
    --color-bg-subtle: #0f1428;
    --color-surface: #131a30;
    --color-surface-strong: rgba(15, 23, 42, 0.72);
    --color-text: #f8fafc;
    --color-text-muted: #cbd5e1;
    --color-text-subtle: #94a3b8;
    --color-border: rgba(255, 255, 255, 0.08);
    --color-border-subtle: rgba(255, 255, 255, 0.04);
    --shadow-card: 0 12px 32px -8px rgba(0, 0, 0, 0.5);
  }

  /* Hero text on dark */
  body[data-dashboard-screen] .hero-title { color: #f8fafc !important; }
  body[data-dashboard-screen] .hero-kicker,
  body[data-dashboard-screen] .hero-sub   { color: #cbd5e1 !important; }

  /* Segmented tabs container on dark */
  body[data-dashboard-screen] .dash-seg {
    background: rgba(255, 255, 255, 0.04) !important;
    border-color: rgba(255, 255, 255, 0.08) !important;
  }
  body[data-dashboard-screen] .dash-seg button {
    color: #cbd5e1 !important;
  }
  body[data-dashboard-screen] .dash-seg button:not(.active):hover {
    color: #f8fafc !important;
    background: rgba(255, 255, 255, 0.06) !important;
  }

  /* Glass cards: KPI, chart, week-mini, generic gcard */
  body[data-dashboard-screen] .kpi,
  body[data-dashboard-screen] .gcard,
  body[data-dashboard-screen] .chart-card,
  body[data-dashboard-screen] .week-mini-card,
  body[data-dashboard-screen] .svc-kpi-grid .kpi,
  body[data-dashboard-screen] .dash-panel .gcard,
  body[data-dashboard-screen] .dash-panel .kpi {
    background: rgba(15, 23, 42, 0.72) !important;
    background-image: none !important;
    border: 1px solid rgba(255, 255, 255, 0.08) !important;
    color: #f8fafc !important;
    box-shadow: 0 12px 32px -8px rgba(0, 0, 0, 0.5) !important;
    backdrop-filter: blur(12px) saturate(1.4) !important;
    -webkit-backdrop-filter: blur(12px) saturate(1.4) !important;
  }

  /* Text inside cards */
  body[data-dashboard-screen] .kpi-label,
  body[data-dashboard-screen] .week-mini-label,
  body[data-dashboard-screen] .sec-title {
    color: #94a3b8 !important;
  }
  body[data-dashboard-screen] .kpi-value,
  body[data-dashboard-screen] .week-mini-val,
  body[data-dashboard-screen] .chart-big {
    color: #f8fafc !important;
  }
  body[data-dashboard-screen] .kpi-sub,
  body[data-dashboard-screen] .chart-big small,
  body[data-dashboard-screen] .chart-legend {
    color: #cbd5e1 !important;
  }
  body[data-dashboard-screen] .ring-label {
    color: #f8fafc !important;
  }
  body[data-dashboard-screen] .kpi .ring-wrap circle:first-child {
    stroke: rgba(255, 255, 255, 0.12) !important;
  }
  body[data-dashboard-screen] .kpi-value small,
  body[data-dashboard-screen] .week-mini-val small {
    color: #94a3b8 !important;
  }

  /* Top/Activity rows borders on dark */
  body[data-dashboard-screen] .rank-row,
  body[data-dashboard-screen] .ranking-item,
  body[data-dashboard-screen] .list-row,
  body[data-dashboard-screen] .activity-item,
  body[data-dashboard-screen] .feed-item {
    color: #f8fafc !important;
    border-bottom-color: rgba(255, 255, 255, 0.06) !important;
  }

  /* ── 2. Snap layout — Ventas + Servicio panels only ──────────────────── */

  body[data-dashboard-screen] .dash-panel[data-dash-panel="ventas"],
  body[data-dashboard-screen] .dash-panel[data-dash-panel="servicio"] {
    /* Snap container: viewport minus topbar (~64px), tabs (~52px), tabbar (~63px) and safe area. */
    height: calc(100vh - 64px - 52px - 63px - env(safe-area-inset-bottom, 0px));
    overflow-y: auto;
    overflow-x: hidden;
    scroll-snap-type: y mandatory;
    -webkit-overflow-scrolling: touch;
    scrollbar-width: none;
  }
  body[data-dashboard-screen] .dash-panel[data-dash-panel="ventas"]::-webkit-scrollbar,
  body[data-dashboard-screen] .dash-panel[data-dash-panel="servicio"]::-webkit-scrollbar {
    display: none;
  }

  /* Inside snap panels: kill the grid; stack cards vertically */
  body[data-dashboard-screen] .dash-panel[data-dash-panel="ventas"] .kpi-grid,
  body[data-dashboard-screen] .dash-panel[data-dash-panel="servicio"] .svc-kpi-grid {
    display: flex;
    flex-direction: column;
    gap: 0;
    margin-bottom: 0;
  }

  /* Snap targets — one per card */
  body[data-dashboard-screen] .dash-panel[data-dash-panel="ventas"] [data-snap-card],
  body[data-dashboard-screen] .dash-panel[data-dash-panel="servicio"] [data-snap-card] {
    scroll-snap-align: center;
    scroll-snap-stop: always;
    min-height: 85vh;
    display: flex;
    flex-direction: column;
    justify-content: center;
    margin: 0 0 12px;
  }

  /* Chart gets a taller snap target and bigger canvas */
  body[data-dashboard-screen] .dash-panel[data-dash-panel="ventas"] .chart-card[data-snap-card] {
    min-height: 90vh;
  }
  body[data-dashboard-screen] .trend-chart-wrap {
    height: 70vh;
    max-height: 480px; /* landscape sanity */
    min-height: 320px;
  }
  body[data-dashboard-screen] .trend-chart-wrap canvas {
    width: 100% !important;
    height: 100% !important;
  }

  /* Scale up KPI typography inside snap cards (~1.8×) */
  body[data-dashboard-screen] .dash-panel[data-dash-panel="ventas"] .kpi[data-snap-card] .kpi-value,
  body[data-dashboard-screen] .dash-panel[data-dash-panel="servicio"] .kpi[data-snap-card] .kpi-value {
    font-size: clamp(48px, 14vw, 72px) !important;
    line-height: 1.05;
  }
  body[data-dashboard-screen] .dash-panel[data-dash-panel="ventas"] .kpi[data-snap-card] .kpi-label,
  body[data-dashboard-screen] .dash-panel[data-dash-panel="servicio"] .kpi[data-snap-card] .kpi-label {
    font-size: 0.95rem !important;
    letter-spacing: 0.06em;
  }
  body[data-dashboard-screen] .dash-panel[data-dash-panel="ventas"] .kpi[data-snap-card] .kpi-sub,
  body[data-dashboard-screen] .dash-panel[data-dash-panel="servicio"] .kpi[data-snap-card] .kpi-sub {
    font-size: 1rem !important;
    margin-top: 8px;
  }
  /* Bigger progress ring inside snap KPI */
  body[data-dashboard-screen] .dash-panel[data-dash-panel="ventas"] .kpi[data-snap-card] .ring-wrap,
  body[data-dashboard-screen] .dash-panel[data-dash-panel="servicio"] .kpi[data-snap-card] .ring-wrap {
    transform: scale(1.6);
    transform-origin: top right;
    margin-bottom: 18px;
  }

  /* Week-mini grid stays a 3-col grid inside its snap card, just centered */
  body[data-dashboard-screen] .dash-panel[data-dash-panel="ventas"] .week-mini-grid[data-snap-card] {
    display: grid;
    grid-template-columns: repeat(3, minmax(0, 1fr));
    gap: 12px;
    align-content: center;
  }
  body[data-dashboard-screen] .dash-panel[data-dash-panel="ventas"] .week-mini-grid[data-snap-card] .week-mini-val {
    font-size: 1.6rem !important;
  }

  /* ── 3. Snap dots indicator (right edge of viewport) ─────────────────── */

  body[data-dashboard-screen] .snap-dots {
    position: fixed;
    right: 8px;
    top: 50%;
    transform: translateY(-50%);
    display: none; /* shown by JS only when its panel is the active tab */
    flex-direction: column;
    gap: 8px;
    z-index: 25;
    pointer-events: none;
  }
  body[data-dashboard-screen] .snap-dots.is-active {
    display: flex;
  }
  body[data-dashboard-screen] .snap-dots span {
    width: 6px;
    height: 6px;
    border-radius: 50%;
    background: rgba(255, 255, 255, 0.25);
    transition: background 160ms ease, transform 160ms ease;
  }
  body[data-dashboard-screen] .snap-dots span.is-current {
    background: #f8fafc;
    transform: scale(1.4);
  }
}

/* Desktop (≥1024px): no snap, no dots — fall back to existing grid layout */
@media (min-width: 1024px) {
  body[data-dashboard-screen] .snap-dots { display: none !important; }
}
```

- [ ] **Step 2: Verify the file exists**

Run:
```bash
ls -la static/css/dashboard_snap.css
```
Expected: file present, size > 4 KB.

- [ ] **Step 3: Commit**

```bash
git add static/css/dashboard_snap.css
git commit -m "feat(dashboard): dashboard_snap.css — vertical snap + dark contrast"
```

---

### Task 4: Create `dashboard-snap-dots.js` for the pagination indicator

**Files:**
- Create: `static/js/dashboard-snap-dots.js`

- [ ] **Step 1: Create `static/js/dashboard-snap-dots.js` with the full content below**

```javascript
/* Dashboard snap-dots indicator.
   Spec: docs/superpowers/specs/2026-04-18-dashboard-snap-layout-design.md

   For each .snap-dots[data-snap-dots-for="<panel>"] container:
   - Find the matching .dash-panel[data-dash-panel="<panel>"]
   - Create one <span> per [data-snap-card] inside that panel
   - Use IntersectionObserver on the cards to mark the most-visible one as
     .is-current
   - Show the dot column only when the panel is the active tab (the existing
     dashboard tab JS toggles a class — we reuse aria-hidden on .dash-panel
     or fall back to checking which panel is currently translated into view).
*/
(function () {
  'use strict';

  function initSnapDots(container) {
    var panelKey = container.dataset.snapDotsFor;
    if (!panelKey) return;
    var panel = document.querySelector(
      '.dash-panel[data-dash-panel="' + panelKey + '"]'
    );
    if (!panel) return;
    var cards = panel.querySelectorAll('[data-snap-card]');
    if (!cards.length) return;

    container.innerHTML = '';
    var dots = [];
    cards.forEach(function () {
      var dot = document.createElement('span');
      container.appendChild(dot);
      dots.push(dot);
    });

    var observer = new IntersectionObserver(
      function (entries) {
        entries.forEach(function (entry) {
          if (!entry.isIntersecting) return;
          var idx = Array.prototype.indexOf.call(cards, entry.target);
          if (idx < 0) return;
          dots.forEach(function (d, i) {
            d.classList.toggle('is-current', i === idx);
          });
        });
      },
      { root: panel, threshold: 0.6 }
    );
    cards.forEach(function (card) { observer.observe(card); });
  }

  function updateActiveDots() {
    document.querySelectorAll('.snap-dots').forEach(function (container) {
      var panelKey = container.dataset.snapDotsFor;
      var activeBtn = document.querySelector(
        '#dash-tabs button.active[data-panel="' + panelKey + '"]'
      );
      container.classList.toggle('is-active', !!activeBtn);
    });
  }

  document.addEventListener('DOMContentLoaded', function () {
    document.querySelectorAll('.snap-dots').forEach(initSnapDots);
    updateActiveDots();

    // The existing tab JS toggles .active on #dash-tabs button. Listen for
    // clicks to refresh which dot column is shown.
    var tabs = document.getElementById('dash-tabs');
    if (tabs) tabs.addEventListener('click', function () {
      // Defer one frame so the existing tab JS finishes updating .active.
      window.requestAnimationFrame(updateActiveDots);
    });
  });
})();
```

- [ ] **Step 2: Verify the file exists**

```bash
ls -la static/js/dashboard-snap-dots.js
```
Expected: file present, size > 1.5 KB.

- [ ] **Step 3: Commit**

```bash
git add static/js/dashboard-snap-dots.js
git commit -m "feat(dashboard): IntersectionObserver-driven snap-dots indicator"
```

---

### Task 5: Wire the new CSS and JS into `dashboard.html`

**Files:**
- Modify: `templates/dashboard.html` (~line 522 for CSS, scripts block for JS)

- [ ] **Step 1: Add the CSS link AFTER `dashboard_light.css`**

In `templates/dashboard.html`, find this line (~522):
```jinja
<link rel="stylesheet" href="{{ url_for('static', filename='css/dashboard_light.css') }}">
```

Add the snap CSS link RIGHT BELOW it, on a new line:
```jinja
<link rel="stylesheet" href="{{ url_for('static', filename='css/dashboard_light.css') }}">
<link rel="stylesheet" href="{{ url_for('static', filename='css/dashboard_snap.css') }}">
```

- [ ] **Step 2: Add the JS script tag inside the `{% block scripts %}` block**

Locate the `{% block scripts %}` opening in `templates/dashboard.html`. Add this script tag near the top of that block (before any existing dashboard JS):

```jinja
{% block scripts %}
<script src="{{ url_for('static', filename='js/dashboard-snap-dots.js') }}" defer></script>
```

If the block already has content, just insert the new `<script>` line — do not remove or reorder existing tags.

- [ ] **Step 3: Run all smoke tests, expect everything to pass**

```bash
.venv311/bin/python -m pytest tests/test_reskin_smoke.py -v
```
Expected: ALL tests pass — including `test_dashboard_snap_css_is_linked` and `test_dashboard_snap_dots_js_is_linked` from Task 2.

- [ ] **Step 4: Commit**

```bash
git add templates/dashboard.html
git commit -m "feat(dashboard): wire snap CSS + dots JS into dashboard.html"
```

---

### Task 6: Visual sanity check on iPhone (manual)

**Files:** none modified.

- [ ] **Step 1: Push to deploy and wait for Heroku**

```bash
git push origin main
```

Then poll for the deploy:
```bash
until heroku releases --app pesosapp -n 1 2>&1 | grep -q "$(git rev-parse --short HEAD)"; do sleep 10; done
heroku releases --app pesosapp -n 2
```
Expected: latest release matches the local HEAD short SHA within ~60s.

- [ ] **Step 2: Manual checks on the iPhone**

User opens `https://app.jomarfoods.com/dashboard` in Safari and verifies:

  1. **Background is solid dark `#0a0e1f`** — no gradient, no light slate.
  2. **Tab "Ventas":** scroll vertically — the first KPI ("Ventas del Mes") fills the viewport, snaps when released. Continue scrolling — Proyección, OTD, Pendientes, Chart (large), Esta Semana grid each snap one at a time.
  3. **Chart card:** canvas is visibly larger than before (~70vh tall, ≥320px). No clipping, no overlap with tabbar.
  4. **Snap-dots:** 6 dots appear on the right edge while on Ventas. The current dot is white + larger; others are dim. Switching to Servicio shows 6 dots for that tab.
  5. **Tab "Servicio":** 6 KPIs snap one at a time, big.
  6. **Tabs Top y Actividad:** layout looks the same as before — NO snap, NO dots. Just the existing list.
  7. **Horizontal swipe between tabs (Ventas → Servicio → Top → Actividad):** still works as before.
  8. **No content hidden under the tabbar** at the bottom of any panel.

If any of these fail, file the failure as a follow-up issue (do not abandon the deploy — the asset links and tests already passed in Task 5).

---

### Task 7: Update CLAUDE.md memory note about the new files

**Files:**
- Modify: `/Users/josedasilva/.claude/projects/-Users-josedasilva-Projects-pesosapp/memory/MEMORY.md` (or the appropriate memory file under `memory/`)

This is short — just a one-liner so future sessions know where the snap layout lives.

- [ ] **Step 1: Append to the existing dashboard-related memory**

Find the existing memory file that documents the dashboard. If none exists, append to `MEMORY.md`:

```markdown
## Dashboard layout
- Snap layout (one KPI per ~85vh, chart 90vh, dark sólido) lives in `static/css/dashboard_snap.css` + `static/js/dashboard-snap-dots.js`. Loaded after `dashboard_light.css`. Mobile only (<1024px). Spec: `docs/superpowers/specs/2026-04-18-dashboard-snap-layout-design.md`.
```

No commit needed — memory files are local, not tracked in repo git.

---

## Self-Review

**Spec coverage:**
- One KPI at a time on Ventas + Servicio → Task 1 (markup) + Task 3 (CSS snap container).
- Bigger chart (~70vh canvas, 90vh card) → Task 3, `.chart-card[data-snap-card]` rule.
- Dark sólido background `#0a0e1f` → Task 3, opening rule block.
- Glass cards more opaque → Task 3, `rgba(15,23,42,0.72)` with bordes definidos.
- Top/Actividad untouched → Task 3 selectors only target `[data-dash-panel="ventas"]` and `="servicio"`.
- Desktop fallback → Task 3, snap rules wrapped in `@media (max-width: 1023px)`; dots hidden in `≥1024px`.
- IntersectionObserver dot indicator (~15-25 LOC) → Task 4.
- Sin cambios al carrusel horizontal de tabs → only listening to clicks on `#dash-tabs`, no hijack.
- Smoke tests → Task 2, asset links + markup hooks verified.

**Placeholder scan:** No "TBD"/"TODO". Code blocks complete. File paths exact.

**Type/name consistency:**
- `data-snap-card="1"` — used in markup (Task 1) and CSS selectors (Task 3) and JS query (Task 4). ✓
- `data-snap-dots-for="ventas"|"servicio"` — markup (Task 1), JS lookup (Task 4). ✓
- `.snap-dots span.is-current` — CSS (Task 3) + JS toggle (Task 4). ✓
- `.snap-dots.is-active` — CSS show rule (Task 3) + JS toggle (Task 4). ✓
- File names: `dashboard_snap.css` and `dashboard-snap-dots.js` — consistent across tests, wiring, and spec.

No issues found.
