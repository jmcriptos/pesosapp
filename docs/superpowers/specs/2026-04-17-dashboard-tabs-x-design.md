# Design Spec · Phase 3 · Dashboard Tabs X-style + Glass Refresh

**Status:** Approved — ready for writing-plans
**Date:** 2026-04-17
**Author:** Jose (owner) with Claude
**Phase:** 3 of 5 (systemic redesign)
**Depends on:** Phase 1 (Glass Foundation — PR #23)

---

## 1 · Context

Phase 3 replaces the dashboard's current carousel navigation (dots + arrow buttons + swipe) with a **Twitter/X-style horizontal tab bar** featuring labeled tabs and an animated underline indicator, and applies the glass visual system introduced in Phase 1 (`static/css/tokens.css` + `static/css/primitives.css`) to every element on the page.

The dashboard is the screen users interact with most often. The current carousel has two problems:

1. **Navigation friction** — dots are tiny and unlabeled; users don't know what panel they're jumping to.
2. **No visible payoff from Phase 1** — the foundation shipped, but the user-facing dashboard still uses the legacy styles.

Phase 3 resolves both in one ship.

## 2 · Scope

### In scope

- Replace `dashboard-subnav-wrap` (carousel nav markup) in `templates/dashboard.html` with a new X-style tab bar:
  - 4 labeled tabs: **Ventas · Servicio · Top · Pedidos** (same panels as today).
  - Sticky under the app header.
  - Animated underline indicator (position + width interpolated on tab change).
  - Tap / click to jump; horizontal swipe between adjacent tabs preserved.
  - Keyboard ← → navigation (accessibility).
  - Identical behavior on mobile and desktop.
- Apply Phase 1 tokens and primitives to all existing elements in the 4 panels:
  - KPI tiles → `.card-glass` + ring with `data-state` (thresholds 85/70 from Phase 1 spec).
  - Rankings/tables → `.card` + `.card-interactive` for clickable rows.
  - Chips for filter state, semantic tags, status indicators.
  - Badge for pending/overdue counts.
  - Replace hardcoded colors in inline styles and `dashboard_pro.css` with `var(--color-*)` where used by panel content.
  - Main dashboard container gets `background: var(--bg-ambient)`.
- New JS controller (vanilla, ~50 LOC) in `static/js/dashboard-tabs.js` for tab state, indicator animation, swipe handling. Replaces the carousel controller.
- Template and CSS updates isolated to the dashboard page only.
- Dark mode works automatically via Phase 1 tokens (no extra code).

### Out of scope

- Reorganizing *what* data/KPIs show in each tab (same content, same panels).
- Backend changes: `calcular_kpis_periodo()`, QBO integration, queries, etc.
- Global app shell / base.html topbar / other pages — that is Phase 2 territory.
- Auth, roles, navigation menu.
- Introducing new KPIs or removing existing ones.
- Server-side rendering changes beyond CSS class swaps in the template.

## 3 · Key decisions

| Decision | Value | Rationale |
|---|---|---|
| Nav pattern | **Twitter/X tabs** with labels + animated underline | User explicitly requested; familiar mobile-first pattern |
| Tabs | **4 existing** — Ventas, Servicio, Top, Pedidos | User approved; no content restructuring this phase |
| Device behavior | **Identical mobile & desktop** | User approved default; keeps one mental model |
| Scope | **B — nav + glass refresh**, not full rebuild | User approved; maximum visible impact with minimal risk |
| Dependencies | **Phase 1 merged first** (PR #23) | Phase 3 consumes tokens + primitives; order matters |
| JS approach | **Vanilla JS, no library** | Consistent with existing codebase (`base.min.js` is vanilla) |
| JS file | **New `static/js/dashboard-tabs.js`** | Isolated from `base.min.js`; easy to replace/remove |

## 4 · Tab bar specification

### Markup

```html
<nav class="dash-tabs" role="tablist" aria-label="Secciones del dashboard">
  <button class="dash-tab is-active" role="tab" aria-selected="true"  aria-controls="panel-ventas"   data-panel="ventas">Ventas</button>
  <button class="dash-tab"           role="tab" aria-selected="false" aria-controls="panel-servicio" data-panel="servicio">Servicio</button>
  <button class="dash-tab"           role="tab" aria-selected="false" aria-controls="panel-top"      data-panel="top">Top</button>
  <button class="dash-tab"           role="tab" aria-selected="false" aria-controls="panel-pedidos"  data-panel="pedidos">Pedidos</button>
  <span class="dash-tabs-indicator" aria-hidden="true"></span>
</nav>
```

The indicator is a single absolutely-positioned span that JS moves and resizes on tab change.

### Styling (token-driven)

The tab bar gets a new primitive block in `static/css/primitives.css` named `.dash-tabs` (+ `.dash-tab`, `.dash-tabs-indicator`). Because it is used on exactly one page today but is a reusable tab pattern, it is promoted to a primitive rather than kept in `dashboard_pro.css`.

```css
.dash-tabs {
  position: sticky;
  top: 0;
  z-index: var(--z-sticky);
  display: flex;
  gap: var(--space-4);
  padding: var(--space-3) var(--space-4);
  background: var(--glass-bg-strong);
  backdrop-filter: var(--glass-blur);
  border-bottom: 1px solid var(--color-border-subtle);
  overflow-x: auto;
  overflow-y: hidden;
  scrollbar-width: none;           /* Firefox */
  scroll-snap-type: x mandatory;   /* keeps tab aligned after swipe */
  -webkit-overflow-scrolling: touch;
  position: relative;              /* for indicator */
}
.dash-tabs::-webkit-scrollbar { display: none; }

.dash-tab {
  position: relative;
  padding: var(--space-3) var(--space-2);
  font-family: var(--font-sans);
  font-size: var(--text-md);
  font-weight: var(--weight-semibold);
  color: var(--color-text-muted);
  background: transparent;
  border: 0;
  cursor: pointer;
  white-space: nowrap;
  transition: color var(--duration-base) var(--ease-out-quart);
  scroll-snap-align: start;
}
.dash-tab:hover { color: var(--color-text); }
.dash-tab.is-active { color: var(--color-primary); }
.dash-tab:focus-visible { outline: none; box-shadow: var(--focus-ring); border-radius: var(--radius-sm); }

.dash-tabs-indicator {
  position: absolute;
  bottom: 0;
  left: 0;
  height: 2px;
  background: var(--color-primary);
  border-radius: var(--radius-full) var(--radius-full) 0 0;
  transition:
    transform var(--duration-base) var(--ease-spring),
    width var(--duration-base) var(--ease-spring);
  pointer-events: none;
}
```

Dark mode works automatically — all colors reference semantic tokens that have dark overrides.

### JS controller (`static/js/dashboard-tabs.js`)

Responsibilities:

1. On load: position the indicator under the currently active tab.
2. On tab click or keyboard ← →: toggle `is-active` + `aria-selected` on tabs, show the matching `<section data-panel="…">` (hide the others via the existing `.tab-panel.active` class), reposition the indicator.
3. On horizontal swipe on the panel container (reuse existing swipe detection if present, otherwise a small touchstart/touchmove/touchend handler): advance to the adjacent tab.
4. On window resize: recompute indicator position (tab widths can change if viewport grows).

API (roughly):

```js
class DashboardTabs {
  constructor(rootEl) { /* find tabs, indicator, panels */ }
  activate(panelKey)  { /* updates classes, indicator, panels, URL hash */ }
  enableSwipe()       { /* touch handlers on panel container */ }
  enableKeyboard()    { /* Arrow keys on focused tab */ }
}

document.addEventListener('DOMContentLoaded', () => {
  const root = document.querySelector('[data-dashboard-tabs]');
  if (root) new DashboardTabs(root).activate('ventas').enableSwipe().enableKeyboard();
});
```

URL hash sync (`#servicio`, `#top`, etc.) is a nice-to-have — include it if it fits within the ~50-line budget.

## 5 · Panel content refresh (cosmetic only)

All four panels keep their existing Jinja logic. The refresh is a surgical CSS-class swap. A representative mapping:

### KPI tiles (`Ventas` panel — lines ~97-200 of current `dashboard.html`)

**Current pattern:**
```html
<div class="kpi-tile">
  <div class="tile-top">
    <span class="tile-label">Ventas del Mes</span>
    <svg class="progress-ring" ...>...</svg>
  </div>
  <div class="tile-value">{{ ... }}</div>
  <div class="tile-sub">{{ ... }}</div>
</div>
```

**After refresh:**
```html
<div class="card card-glass" data-state="{{ 'success' if porcentaje_meta_v >= 85 else 'warning' if porcentaje_meta_v >= 70 else 'danger' }}">
  <div class="card-body">
    <div class="cluster cluster-2" style="justify-content: space-between;">
      <span class="label">Ventas del Mes</span>
      <svg class="ring" data-state="{{ … }}">...</svg>
    </div>
    <div class="text-2xl font-bold tabular tracking-tight">{{ '{:,.0f}'.format(ventas_mes_v) }}
      <span class="text-sm text-subtle font-medium">XCG</span>
    </div>
    <div class="text-sm text-muted">Meta: {{ '{:,.0f}'.format(meta_mensual_v) }} · {{ pedidos_mes_v }} ped</div>
  </div>
</div>
```

### Service gauges (`Servicio` panel)

Same pattern — existing SVG rings get `class="ring"` + `data-state` computed from their respective thresholds. Tiles become `.card`. No logic changes.

### Top clientes / productos (`Top` panel)

- Ranking rows → `.card .card-interactive` (clickable hover).
- Filter pills (Mes / 3M / 6M / 4W) → `.chip` (active gets `.chip-primary`, others stay neutral).

### Operational counters (`Pedidos` panel)

- Counts (pendientes, facturados hoy, etc.) → `.card` with `.badge` for non-zero alerts.
- Status pills → `.chip-success` / `.chip-warning` / `.chip-danger` depending on the state.

### Global container

```html
<div class="exec-dashboard" style="background: var(--bg-ambient);">
```

Picks up the indigo→pink gradient in light and indigo→purple in dark automatically.

## 6 · File changes (summary)

### Created

| File | Responsibility |
|---|---|
| `static/js/dashboard-tabs.js` | Tab activation, indicator animation, swipe + keyboard nav, optional URL hash sync. ~50-80 lines. |

### Modified

| File | Change |
|---|---|
| `templates/dashboard.html` | Replace `dashboard-subnav-wrap` block with `<nav class="dash-tabs">`. Swap KPI/card/chip classes inside the 4 panels per §5. Add `data-dashboard-tabs` attribute on the panel container for the JS controller to hook onto. |
| `templates/base.html` | Add `<script src="{{ url_for('static', filename='js/dashboard-tabs.js') }}" defer></script>` — loaded globally but only activates on pages that have `[data-dashboard-tabs]` in DOM. |
| `static/css/primitives.css` | Append `.dash-tabs`, `.dash-tab`, `.dash-tabs-indicator` blocks. |
| `static/dashboard_pro.css` | Optional: remove now-unused carousel rules (`.dashboard-carousel-*`). Can defer to Phase 5 cleanup if risky. |

### Untouched

- `app.py` — no backend changes.
- All other templates and static files.
- Tests for data / KPI math (already passing from Phase 1).

## 7 · Success criteria

1. Tab bar renders at the top of `/dashboard` with 4 labeled tabs, animated indicator, glass background.
2. Clicking / tapping a tab transitions smoothly to the corresponding panel; indicator slides under the active tab.
3. Horizontal swipe on the panel body advances to the adjacent tab (same UX as current carousel).
4. Keyboard ← / → with focus on tabs cycles through them.
5. Every KPI tile, card, chip, ring, and badge in the 4 panels uses Phase 1 primitives/tokens — no hardcoded colors remaining in panel-level inline styles.
6. Ring color reflects threshold state (green ≥85, amber 70-84, red <70) for KPIs where "higher is better"; inverse for "lower is better" counts.
7. Dark mode activates automatically with `prefers-color-scheme: dark` and affects the entire dashboard (no pockets of stale light-mode color).
8. Existing dashboard tests still pass (QBO numbers, KPI math, data unchanged).
9. `/dev/primitives` remains unaffected.
10. Manual smoke test: all 4 tabs render, all data displays correctly, no console errors.

## 8 · Open questions / future considerations

- **Tab icons**: current design is label-only. If later we want Font Awesome icons before each label, the `.dash-tab` markup supports it trivially — defer until requested.
- **URL hash sync**: reasonable to include in JS if it fits; otherwise Phase 3.1.
- **Panel transition animation**: the spec leaves this at "existing" behavior (instant swap or fade). If Phase 3 reveals the swap is jarring, a `translateX` panel transition can be added as a follow-up.
- **Carousel CSS cleanup**: removing `.dashboard-carousel-*` rules from `dashboard_pro.css` is low-value work deferred to Phase 5.
- **Swipe gesture on desktop**: mouse-drag-swipe is not implemented; desktop users rely on tap and keyboard. Fine per "identical mobile & desktop" decision.

---

**Next step:** invoke `writing-plans` skill to produce an implementation plan for this spec.
