# Legacy CSS `!important` Sweep — Implementation Plan

> **Status:** Queued — deferred from the v697-v698 review round (commit `9f8a7d77`).
> **Risk:** High. Requires visual regression testing per screen.
> **Estimated effort:** 1-3 days, sub-divided by file.

## Context

The full-app code review at HEAD `5cd41635` flagged that the project has
**~1,087 `!important` declarations** across 6 legacy stylesheets. The
overlay pattern (`legacy.css → *_redesign.css`) means most legacy
`!important` are now redundant — the redesign sheet would win by source
order alone. But a blind sweep would also remove `!important` that are
load-bearing for non-redesign reasons:

- Defeating Bootstrap / Tom Select / FontAwesome defaults
- Beating inline `style="..."` attributes from Jinja templates
- Working around iOS Safari quirks

## Inventory

| File | `!important` count | Has redesign sheet? |
|---|---|---|
| `dark-theme.css` | 503 | No (global) |
| `pedidos_list.css` | 225 | No (carries the redesign itself) |
| `detalles_pedido.css` | 217 | Yes — `detail_redesign.css` |
| `dashboard_light.css` | 75 | Yes — `dashboard_snap.css` |
| `forms.css` | 43 | No (global) |
| `pesar.css` | 24 | Yes — `pesar_redesign.css` |
| **Total** | **1,087** | |

## Methodology

For each file with a redesign counterpart, run this loop:

1. **Cross-reference selectors.** For every selector in the legacy file,
   grep the redesign file. If the redesign defines the same selector
   with `!important`, the legacy `!important` is structurally redundant
   and safe to remove.

2. **Strip in a feature branch.** Never on `main` directly. Push to a
   throw-away branch and visually verify in a Heroku review app or local
   `flask run`.

3. **Per-screen visual regression checklist** (run in iPhone Safari +
   desktop Chrome):
   - Dashboard tab Ventas, Servicio, Top, Actividad
   - Pedidos list — pendiente, preparado, facturado filters
   - Detalles pedido — pendiente, preparado, facturado states; with and
     without weighed boxes
   - Pesar screen — chips, lote card, keypad, summary, edit modal
   - Pedido form — nuevo and editar paths
   - Etiquetas card (collapse + expanded) at desktop and mobile

4. **Commit per file.** A failure in one file should be revertible
   without touching the others.

5. **Don't touch `dark-theme.css` and `forms.css`.** Both are global;
   no redesign sheet supersedes them. The `!important` there is
   intentional or load-bearing for browser-default defeat.

## Suggested order (lowest risk → highest)

### 1. `pesar.css` (24 !important) — start here

The pesar redesign is the youngest and most aggressive overlay. Most
of pesar.css's `!important` is from the original spec when there was
no redesign overlay. Now `pesar_redesign.css` covers virtually every
visible selector with its own `!important`.

Specific selectors to grep against `pesar_redesign.css`:
- `.pesar-nav`, `.pesar-nav-pill`, `.pesar-nav-client`, `.pesar-nav-meta`
- `.pesar-chip`, `.pesar-chip-status`, `.pesar-chip-name`
- `.pesar-lote-card`, `.pesar-lote-head`, `.pesar-lote-new`
- `.pesar-field input`, `.pesar-date-trigger`
- `.pesar-keypad-card`, `.pesar-readout`, `.pesar-key`, `.pesar-key.is-submit`
- `.pesar-group-card`, `.pesar-group-header`
- `.pesar-modal-overlay`, `.pesar-modal`, `.pesar-edit-readout`,
  `.pesar-edit-key`, `.pesar-modal-actions`, `.pesar-delete-btn`,
  `.pesar-save-btn`
- `.pesar-date-sheet-panel`, `.pesar-date-cell`, `.pesar-date-sheet-primary`,
  `.pesar-date-sheet-secondary`

For each match in both files, remove `!important` from the legacy
declaration only.

### 2. `dashboard_light.css` (75 !important)

Same procedure against `dashboard_snap.css`. Selectors to expect overlap on:
- `.app-content`, `.app-shell`, `.app-shell.dash-body`
- `.dash-seg`, `.dash-seg button`, `.dash-seg button.active`
- `.kpi`, `.kpi-grid`, `.kpi-top`, `.kpi-label`, `.kpi-value`,
  `.kpi-value small`, `.kpi-sub`
- `.gcard`, `.chart-card`, `.chart-big`, `.chart-legend`
- `.week-mini-grid`, `.week-mini-card`, `.week-mini-label`, `.week-mini-val`
- `.svc-kpi-grid`, `.dash-panel .kpi`
- `.sec-head`, `.sec-title`, `.sec-action`
- `.ring-wrap circle`, `.ring-label`

### 3. `detalles_pedido.css` (217 !important)

Highest density. Cross-reference against `detail_redesign.css` AND the
extracted `detalles_pedido_inline.css`. Selectors to expect overlap on:
- `.app-content`, `.app-shell`, `.mobile-form-container`
- `.mobile-card`, `.mobile-card-header`, `.mobile-card-body`
- `.detail-tabs`, `.detail-tab`, `.detail-tab.is-active`
- `.action-bar`, `.action-bar .btn-primary`, `.action-bar .btn-secondary`
- `.producto-item-mobile`, `.producto-item-name`, `.producto-detail-label`,
  `.producto-detail-value`
- `.badge-pedido`, `.badge-pedido.badge-pesable`, `.badge-pedido.badge-import`
- `.mobile-edit-btn`, `.mobile-delete-btn`
- `.edit-modal-overlay`, `.edit-modal`

This file is the largest and the riskiest. Consider splitting into 2-3
sub-PRs (cards / action bar / modal) so each can be reverted
independently.

### 4. `pedidos_list.css` (225 !important)

This file IS itself a redesign of the pedidos list — there's no
`pedidos_list_redesign.css` to cross-reference against. The 225
`!important` here mostly fight `dark-theme.css` and the inline-extracted
`pedidos_inline.css`.

Strategy:
- Group by selector family (cards / pagination / hero / search-pill /
  status-pill).
- For each family, identify the competing `dark-theme.css` rule and
  decide whether to (a) keep the `!important`, (b) bump specificity on
  the legacy selector to win without `!important`, or (c) move the
  competing `dark-theme.css` rule to be more specific.

This is the longest and most architectural of the four files. Consider
deferring until the pedidos list gets its own redesign overlay.

## Out of scope

- `dark-theme.css` (503) — global theme, broad blast radius
- `forms.css` (43) — global form reset, fights browser defaults
- The minified bundles (`*.min.css`) — regenerated from sources

## Sign-off checklist per per-file PR

- [ ] `pytest tests/` passes (no smoke regressions)
- [ ] Visual diff captured for every screen in the per-screen checklist
- [ ] iPhone Safari standalone PWA mode tested
- [ ] Heroku review app verified before merging to `main`
- [ ] Commit message documents the count removed and the file scope

## Done when

All four files in scope have `!important` density reduced by ≥40% and
no visual regression reports come from the user during a 7-day soak.
