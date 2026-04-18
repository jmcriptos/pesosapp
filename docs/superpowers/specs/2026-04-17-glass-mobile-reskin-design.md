# Glass Mobile Reskin — Design Spec

**Date:** 2026-04-17
**Branch target:** `feat/glass-mobile-reskin`
**Status:** Approved, ready for implementation plan

## Problem

Pesosapp is used primarily on mobile by sales reps. Phase 1 of the Glass Foundation system (tokens + primitives) is merged but not applied to any UI. Phase 3 (dashboard tabs X-style + glass refresh, PR #24) was merged and reverted because of a functional bug and visual dislike. The user has since iterated a new mobile-first design in Claude Design (prototype bundle), chose its final look (dark theme, heavy glass, blue hue, minimal KPI style), and wants that applied to production.

## Goals

- Visually port Dashboard, Pedidos list, and Pedido detail from the prototype to the production Flask/Jinja app.
- Apply the same glass aesthetic to the shared chrome (`base.html`) so navigation feels consistent across pages.
- Mobile-first — desktop renders the same mobile layout centered in a narrow container.
- Expose a single user-facing setting: dark/light theme toggle, persisted in `localStorage`.

## Non-goals

- No new Pesar screen (the biggest iteration from the chat) — deferred to a future phase.
- No backend changes: no new routes, models, migrations, or queries.
- No changes to dashboard charts, filters, date nav, carousel JS, N8N invoicing, or any business logic.
- No tweaks panel (density, glass intensity, hue, KPI style) — hardcoded to the prototype's chosen values.
- Secondary pages (Productos, Clientes, Facturación, Admin, Login, Recepciones) out of scope. They inherit the updated `base.html` chrome but their page bodies keep current styles.

## Decisions log

| Decision | Value | Rationale |
|---|---|---|
| Scope | Dashboard + Pedidos + PedidoDetail + `base.html` | Covers the 3 prototype screens plus shared chrome for consistency |
| Priority | Mobile-first | User confirmed the app is used primarily on mobile |
| User settings | Theme toggle only (dark/light) | Other dimensions are design-time choices, not user preferences |
| Fixed config | `data-theme="dark" data-hue="blue" data-glass="heavy" data-kpi-style="minimal"` | Matches the prototype's final iterated state |
| Approach | Layered CSS on top of existing templates (surgical edits) | Avoids repeating the Phase 3 bug (which was in new JS controller) |
| Breakpoint strategy | Single mobile layout, `max-width: 480px` centered on desktop | Simplifies the port, mobile is primary use |
| Anti-flash theme | `data-theme` applied before first paint via inline script block | Prevents dark→light flash on page load |

## Architecture

### New files

| Path | Purpose | Approx size |
|---|---|---|
| `static/css/app-mobile.css` | Port of `src/app.css` from the prototype bundle, adapted to Jinja selectors | ~27 KB |
| `static/js/theme-toggle.js` | Vanilla JS theme persistence + toggle | ~25 LOC |

### Modified files

| Path | Change |
|---|---|
| `static/css/tokens.css` | Add `[data-hue="blue"]` variant matching the prototype (indigo-500 → `#2563eb`, violet-500 → `#0ea5e9`). No changes to Phase 1 tokens already in use. |
| `templates/base.html` | Link `app-mobile.css` and `theme-toggle.js`. Set `<body data-theme="dark" data-hue="blue" data-glass="heavy" data-kpi-style="minimal">`. Add sun/moon toggle button in header. Add glass bottom nav with 4 tabs (Dashboard / Pedidos / Productos / Más). |
| `templates/dashboard.html` | Wrap panels in `.gcard`. Replace KPI tiles with `.kpi` minimal style. Restyle existing carousel nav (classes only, no JS changes). Keep Chart.js sparkline; recolor line/fill to `--accent`. |
| `templates/pedidos.html` | Replace `<table>` with a `<ul>` of `.card` rows. Add sticky glass search bar, horizontal filter chips, day-group headers with daily totals. |
| `templates/detalles_pedido.html` | Add gradient hero with client + PED number + KPI totals (cajas / peso / total XCG). Add 4-step progress timeline. Restyle internal tabs. Rewrite product line items with color strip + weight-hero layout. Add sticky bottom action bar. |

### Untouched

- All dashboard JS (charts, filters, date nav, carousel controller).
- `dark-theme.css`, `forms.css`, `main.css` — remain loaded as fallback; `app-mobile.css` is loaded last and wins by load order.
- `app.py`, models, routes, queries, migrations.
- All other templates.

## CSS strategy

**Load order in `base.html`:**
```
tokens.css → primitives.css → main.css → forms.css → dark-theme.css → app-mobile.css
```

**Global variables pinned** in `:root` of `app-mobile.css`:
```css
--accent: var(--indigo-500);    /* = #2563eb by data-hue="blue" */
--accent-2: var(--violet-500);  /* = #0ea5e9 by data-hue="blue" */
--glass-blur: 40px;
--glass-saturation: 2;
```

**Theme values:**
- `[data-theme="dark"]` (default): bg `#0a0a0f`, text `#f8fafc`, surfaces `rgba(255,255,255,0.04)`
- `[data-theme="light"]`: bg `#f8fafc`, text `#020617`, surfaces `rgba(0,0,0,0.03)`
- Transitions 150ms ease on `background-color`, `color`, `border-color` for the toggle animation.

**Breakpoints:**
- Default (mobile): single column, cards full width, 16px gutters, bottom nav fixed.
- `@media (min-width: 769px)`: `.app-shell { max-width: 480px; margin: 0 auto; }` — mobile layout centered.

## Component mapping

### Dashboard
- Greeting hero (`h1` with user name + localized date subtitle).
- Existing carousel nav preserved; panel containers wrapped in `.gcard`.
- KPI tiles become `.kpi` cards. Because `data-kpi-style="minimal"` is the fixed default, `.progress-ring` is hidden and tiles render as tabular numbers with labels.
- Sparkline Chart.js container wrapped in `.gcard`; dataset unchanged; line/fill use `--accent`.
- Rank lists (Top productos/clientes) use `.card` rows with 1px separators, tabular numerals, and variation chips.

### Pedidos list
- Sticky glass search bar with placeholder `Buscar pedido…`.
- Horizontal scrollable filter chips: Todos / Pendientes / Preparados / Facturados. Active chip filled with `--accent`.
- Day-group headers (sticky inside scroll): `Hoy · 12 pedidos · XCG 45.2k`.
- Row card per pedido: client name + PED number + hour + total + SLA pill (green/amber/red based on `pedido.estado` and delivery date).
- Tap routes to `/pedidos/<id>/detalles` (existing route, unchanged).

### Pedido detail
- Gradient hero (indigo→cyan blue): client, PED number, status chip, and 3 KPI numbers (cajas / peso total / total XCG).
- 4-step progress timeline: Creado → Preparado → Facturado → Entregado. Active step uses `--accent` gradient; completed steps show a check icon.
- Internal tabs: Productos (default) · Detalles · Historial. Only the Productos list gets new markup; Detalles and Historial keep existing markup with only glass restyling.
- Line items: 4px color strip per category on the left, name + meta (`cajas · precio/kg`), weight `42.8 kg` hero on the right, status chip (`● Pesado` green or `◌ Por pesar` amber).
- Sticky bottom action bar with primary buttons (`Marcar preparado` / `Facturar`) rendered conditionally based on current `pedido.estado`. Form actions and endpoints unchanged.

## Theme toggle JS

**File:** `static/js/theme-toggle.js`

```js
(function () {
  const KEY = 'pesos_theme';
  const root = document.body;

  const saved = localStorage.getItem(KEY);
  if (saved === 'light' || saved === 'dark') {
    root.dataset.theme = saved;
  }

  document.querySelectorAll('[data-theme-toggle]').forEach(btn => {
    btn.addEventListener('click', () => {
      const next = root.dataset.theme === 'dark' ? 'light' : 'dark';
      root.dataset.theme = next;
      try { localStorage.setItem(KEY, next); } catch {}
      document.querySelectorAll('[data-theme-toggle]').forEach(b => {
        b.setAttribute('aria-pressed', String(next === 'dark'));
      });
    });
  });
})();
```

Loaded at the top of `<body>` (not deferred) so the saved theme is applied before the page renders.

**Markup in `base.html`:**
```html
<button data-theme-toggle aria-pressed="true" class="hbtn" title="Alternar tema">
  <svg class="sun-icon" aria-hidden="true">…</svg>
  <svg class="moon-icon" aria-hidden="true">…</svg>
</button>
```

The two SVGs are toggled by CSS rules keyed on `[data-theme]` — one is `display: none` depending on the current theme.

**Fallbacks:**
- No JS: body stays at default `dark`, rest of app works.
- No localStorage (private mode / locked down browser): toggle still works session-by-session, `try/catch` swallows the exception.

## Testing

### Automated
- Existing pytest suite must stay green (163 Phase 1 tests, 30 KPI tests, dashboard tests). Update selectors only if markup changes force it.
- Add one smoke test that requests `/dashboard`, `/pedidos`, `/pedidos/<id>/detalles` and asserts 200 + `app-mobile.css` is linked in the response HTML.
- No new visual tests.

### Manual QA checklist (run on `pesosapp-staging`)
Viewport: mobile 375×812 in Chrome DevTools, plus a real iPhone once possible.

- [ ] Dashboard renders; charts display; carousel nav switches panels.
- [ ] KPI numbers match production (side-by-side compare).
- [ ] Date nav (arrows, specific day) works on dashboard.
- [ ] Pedidos list: search filters rows, chip filters switch subsets, tap opens detail.
- [ ] Pedido detail: internal tabs switch content, bottom action bar executes `Marcar preparado` and `Facturar` against the real endpoints.
- [ ] Theme toggle alternates dark/light and persists across reload.
- [ ] No console errors on any of the three pages.

### Phase 3 regression guard
Before pushing to staging, run `git diff main -- static/js/` and confirm **zero changes to existing JS files**. The Phase 3 bug most likely lived in the new `dashboard-tabs.js` controller; leaving existing JS untouched neutralizes that risk vector.

## Deploy

**Branch:** `feat/glass-mobile-reskin` off `main`.

**Staging (one-time setup):**
```bash
heroku create pesosapp-staging
# Staging shares the production database (reskin only, no data changes).
# Optional: fork a copy with `heroku addons:create heroku-postgresql:...` for full isolation.
```

**Iterative push during development:**
```bash
git push https://git.heroku.com/pesosapp-staging.git feat/glass-mobile-reskin:main
```

**Path to production** after staging passes the checklist:
1. Open PR to `main`.
2. Merge.
3. Heroku main app auto-deploys via the existing `main` push hook.

## Risks and mitigations

| Risk | Mitigation |
|---|---|
| Phase 3 bug reappears | Do not touch any existing JS file. Run the `git diff main -- static/js/` guard before staging push. |
| Visual regression on secondary pages | Scope `app-mobile.css` selectors tightly (via `.app-shell` wrapper or page-specific parent classes) so they do not leak into Productos/Clientes/Facturación. |
| Pedidos table → cards breaks tests asserting on `<table>` | Update only the selectors that genuinely need to change; a selector-level test change is cheaper than re-engineering the markup. |
| Chart.js sparkline looks wrong against glass bg | If colors are hard to read against dark glass, fall back to the existing sparkline styling — the spec allows keeping it untouched. |
| Bottom nav overlaps content on short screens | Add `padding-bottom: calc(64px + safe-area-inset-bottom)` to `.app-shell`. |
| Full-bleed layout on desktop looks bad at 1920px | The `max-width: 480px` container mimics a mobile emulator in the browser; acceptable for this phase since the app is primarily mobile. |

## Out of scope (future phases)

- New Pesar screen (box weight registration with lote + fecha elaboración + vencimiento). Requires backend model, migration, routes, and UI. Entire separate spec.
- Reskin of Productos, Clientes, Facturación, Admin, Login pages.
- Desktop-optimized wide layouts (tables, sidebars) for power users.
- Tweaks panel exposing density / glass intensity / hue / KPI style.
