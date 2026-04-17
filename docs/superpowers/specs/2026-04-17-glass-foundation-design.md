# Design Spec · Phase 1 · Glass Foundation (Tokens + Primitives)

**Status:** Draft — awaiting user review
**Date:** 2026-04-17
**Author:** Jose (owner) with Claude
**Phase:** 1 of 5 (systemic redesign)

---

## 1 · Context

PesosApp currently uses a legacy CSS system (`styles.css`, `dashboard_pro.css`) built with hardcoded values, no dark mode support, and increasingly divergent patterns across pages. The user has approved a systemic redesign aimed at a **Premium Glass** aesthetic (Apple/iOS-like), with **Premium Indigo** as the primary palette, optimized for mobile (iPhone) as the primary usage device.

The redesign is decomposed into 5 independent phases:

| Phase | Name | Description |
|---|---|---|
| **1** | **Foundation** ← *this spec* | Design tokens + primitive components |
| 2 | Shell & Navigation | Redesign `base.html`, topbar, tabbar, nav |
| 3 | Dashboard | Rebuild `dashboard.html` with new system |
| 4 | Pedidos (operational tray) | Lists, filters, row actions |
| 5 | Secondary pages | Clientes, productos, facturación, login |

Each phase ships independently. Phase 1 establishes the vocabulary; Phases 2-5 speak it.

## 2 · Scope

### In scope (Phase 1)

- `static/css/tokens.css` — all CSS custom properties (color, typography, spacing, radii, shadows, motion, z-index, blur).
- `static/css/primitives.css` — primitive components: `.btn`, `.input`, `.field`, `.card` (+ variants), `.chip`, `.badge`, surface helpers, layout utilities (`.stack`, `.cluster`, `.grid-auto`), skeleton loaders.
- Loading strategy: both files loaded in `base.html` **before** existing `styles.css` / `dashboard_pro.css`. No changes to existing CSS files.
- Light + Dark mode via `prefers-color-scheme` (automatic, respects iOS setting). `:root[data-theme="light|dark"]` overrides reserved for future manual toggle.
- Visual verification on mobile (iPhone) and desktop browsers.

### Out of scope (future phases)

- Any changes to `base.html` structure beyond the two `<link>` additions.
- Any changes to existing templates (dashboard, pedidos, etc.).
- Modals, dialogs, toasts, toggle switches, tabs, dropdowns (added on demand in Phase 2+).
- Dark mode manual toggle UI (tokens support it, UI deferred).
- Removing or rewriting existing `styles.css` / `dashboard_pro.css` (happens at end of Phase 5).

## 3 · Key decisions

| Decision | Value | Rationale |
|---|---|---|
| Aesthetic | **Premium Glass** (Apple/iOS) | User selection (brainstorming step 1) |
| Primary palette | **Premium Indigo** `#6366F1` | User selection; premium fintech feel; pairs with accent `#8B5CF6` |
| Primary device | **Mobile (iPhone)** | User selection; mobile-first scale and touch targets |
| Dark mode | **Auto via `prefers-color-scheme`** | Respects iOS system setting; premium without toggle UX load |
| Implementation | **Approach C · Hybrid** | New files coexist with legacy; zero regression risk |
| Font stack | **System-native** (SF Pro / Inter fallback) | Zero downloads, no FOUT, feels native |
| Base type size | **15 px body, 16 px inputs** (+2 px on desktop via MQ) | 15 px body feels iOS-native; inputs must be ≥16 px to avoid iOS Safari zoom on focus |
| Ring tier thresholds | **≥85% success / 70–84% warning / <70% danger** | Semantic color feedback per KPI |

## 4 · File structure

```
static/
  css/
    tokens.css        ← NEW — all CSS custom properties
    primitives.css    ← NEW — primitive components
  styles.css          ← UNTOUCHED
  styles.min.css      ← UNTOUCHED
  dashboard_pro.css   ← UNTOUCHED
  dashboard_pro.min.css ← UNTOUCHED
```

`base.html` additions (in `<head>`, before any existing stylesheet):

```html
<link rel="stylesheet" href="{{ url_for('static', filename='css/tokens.css') }}">
<link rel="stylesheet" href="{{ url_for('static', filename='css/primitives.css') }}">
```

Minified versions (`tokens.min.css`, `primitives.min.css`) are **not** required for Phase 1. Add in Phase 5 cleanup.

## 5 · Token architecture

### Two-layer system

**Layer 1 — Primitive tokens** (absolute values). Never referenced by components directly.

```css
--indigo-500: #6366f1;
--gray-900: #0f172a;
```

**Layer 2 — Semantic tokens** (intent + role). Always used by components.

```css
--color-primary: var(--indigo-500);
--color-text: var(--gray-900);
```

**Rule:** Components reference Layer 2 only. Dark mode reassigns Layer 2; Layer 1 never changes.

### Light/Dark strategy

```css
:root {
  /* Light defaults */
  --color-bg: var(--gray-50);
  /* ... */
}
@media (prefers-color-scheme: dark) {
  :root {
    --color-bg: var(--gray-950);
    /* ... */
  }
}
:root[data-theme="light"] { /* force light — reserved */ }
:root[data-theme="dark"]  { /* force dark — reserved */ }
```

### Component tokens (local overrides)

```css
.card {
  --card-bg: var(--color-surface);
  --card-radius: var(--radius-lg);
  background: var(--card-bg);
  border-radius: var(--card-radius);
}
```

Allows per-instance override: `<div class="card" style="--card-radius: var(--radius-xl);">`.

## 6 · Color system (concrete values)

### Layer 1 — Primitives

```css
/* Neutrals (warm slate) */
--gray-50:  #f8fafc;
--gray-100: #f1f5f9;
--gray-200: #e2e8f0;
--gray-300: #cbd5e1;
--gray-400: #94a3b8;
--gray-500: #64748b;
--gray-600: #475569;
--gray-700: #334155;
--gray-800: #1e293b;
--gray-900: #0f172a;
--gray-950: #020617;

/* Indigo (primary) */
--indigo-50:  #eef2ff;
--indigo-100: #e0e7ff;
--indigo-200: #c7d2fe;
--indigo-300: #a5b4fc;
--indigo-400: #818cf8;
--indigo-500: #6366f1;   /* ★ brand primary */
--indigo-600: #4f46e5;
--indigo-700: #4338ca;
--indigo-800: #3730a3;
--indigo-900: #312e81;

/* Violet (accent for gradients/hero) */
--violet-400: #a78bfa;
--violet-500: #8b5cf6;
--violet-600: #7c3aed;

/* Semantic primitives */
--emerald-400: #34d399;  --emerald-500: #10b981;  --emerald-600: #059669;
--amber-400:   #fbbf24;  --amber-500:   #f59e0b;  --amber-600:   #d97706;
--rose-400:    #fb7185;  --rose-500:    #f43f5e;  --rose-600:    #e11d48;
--sky-400:     #38bdf8;  --sky-500:     #0ea5e9;  --sky-600:     #0284c7;
```

### Layer 2 — Semantic tokens (Light)

```css
:root {
  /* Surfaces & text */
  --color-bg:            var(--gray-50);
  --color-bg-elevated:   #ffffff;
  --color-surface:       #ffffff;
  --color-surface-muted: var(--gray-100);
  --color-surface-sunken:var(--gray-100);

  --color-text:          var(--gray-900);
  --color-text-muted:    var(--gray-600);
  --color-text-subtle:   var(--gray-500);
  --color-text-inverse:  #ffffff;

  --color-border:        var(--gray-200);
  --color-border-strong: var(--gray-300);
  --color-border-subtle: rgba(15, 23, 42, 0.06);

  /* Glass */
  --glass-bg:        rgba(255, 255, 255, 0.72);
  --glass-bg-strong: rgba(255, 255, 255, 0.85);
  --glass-border:    rgba(255, 255, 255, 0.9);
  --glass-blur:      blur(18px) saturate(1.2);

  /* Ambient background */
  --bg-ambient: linear-gradient(135deg, #eef2ff 0%, #ffffff 45%, #fdf2f8 100%);

  /* Primary */
  --color-primary:        var(--indigo-500);
  --color-primary-hover:  var(--indigo-600);
  --color-primary-active: var(--indigo-700);
  --color-primary-fg:     #ffffff;
  --color-primary-soft:   var(--indigo-50);
  --color-primary-soft-fg:var(--indigo-700);

  /* Accent */
  --color-accent:       var(--violet-500);
  --color-accent-soft:  #f3e8ff;

  /* Semantic roles (solid + soft-bg + soft-fg) */
  --color-success:         var(--emerald-500);
  --color-success-fg:      #ffffff;
  --color-success-soft:    #d1fae5;
  --color-success-soft-fg: var(--emerald-600);

  --color-warning:         var(--amber-500);
  --color-warning-fg:      var(--gray-900);
  --color-warning-soft:    #fef3c7;
  --color-warning-soft-fg: var(--amber-600);

  --color-danger:          var(--rose-500);
  --color-danger-fg:       #ffffff;
  --color-danger-soft:     #ffe4e6;
  --color-danger-soft-fg:  var(--rose-600);

  --color-info:            var(--sky-500);
  --color-info-fg:         #ffffff;
  --color-info-soft:       #e0f2fe;
  --color-info-soft-fg:    var(--sky-600);

  /* Focus ring */
  --focus-ring: 0 0 0 3px rgba(99, 102, 241, 0.35);
}
```

### Layer 2 — Semantic tokens (Dark override)

```css
@media (prefers-color-scheme: dark) {
  :root {
    --color-bg:            var(--gray-950);
    --color-bg-elevated:   var(--gray-900);
    --color-surface:       #1a1f37;
    --color-surface-muted: var(--gray-800);
    --color-surface-sunken:var(--gray-950);

    --color-text:          var(--gray-50);
    --color-text-muted:    var(--gray-400);
    --color-text-subtle:   var(--gray-500);
    --color-text-inverse:  var(--gray-900);

    --color-border:        rgba(255, 255, 255, 0.08);
    --color-border-strong: rgba(255, 255, 255, 0.15);
    --color-border-subtle: rgba(255, 255, 255, 0.04);

    --glass-bg:        rgba(30, 41, 59, 0.55);
    --glass-bg-strong: rgba(30, 41, 59, 0.75);
    --glass-border:    rgba(255, 255, 255, 0.08);
    --glass-blur:      blur(20px) saturate(1.3);

    --bg-ambient: linear-gradient(135deg, #0a0e1f 0%, #0f172a 50%, #1a1033 100%);

    --color-primary:        var(--indigo-400);
    --color-primary-hover:  var(--indigo-300);
    --color-primary-active: var(--indigo-200);
    --color-primary-fg:     var(--gray-900);
    --color-primary-soft:   rgba(99, 102, 241, 0.15);
    --color-primary-soft-fg:var(--indigo-300);

    --color-accent:       var(--violet-400);
    --color-accent-soft:  rgba(139, 92, 246, 0.15);

    --color-success-soft:    rgba(16, 185, 129, 0.15);
    --color-success-soft-fg: var(--emerald-400);
    --color-warning-soft:    rgba(245, 158, 11, 0.15);
    --color-warning-soft-fg: var(--amber-400);
    --color-danger-soft:     rgba(244, 63, 94, 0.15);
    --color-danger-soft-fg:  var(--rose-400);
    --color-info-soft:       rgba(14, 165, 233, 0.15);
    --color-info-soft-fg:    var(--sky-400);

    --focus-ring: 0 0 0 3px rgba(129, 140, 248, 0.45);
  }
}
```

### Contrast requirements (WCAG)

- Body text on surface: ≥ 12:1 (AAA).
- Muted text on surface: ≥ 4.7:1 (AA).
- Primary fg on primary bg: ≥ 4.6:1 (AA).
- Chip soft combinations: ≥ 4.5:1 (AA).

## 7 · Typography

```css
--font-sans: -apple-system, BlinkMacSystemFont, 'SF Pro Display',
             'SF Pro Text', 'Inter', 'Segoe UI', Roboto, system-ui, sans-serif;
--font-mono: ui-monospace, 'SF Mono', 'Menlo', 'Consolas', monospace;
--font-numeric: var(--font-sans);

/* Size scale (mobile base 15px) */
--text-2xs:  10px;
--text-xs:   11px;
--text-sm:   13px;
--text-base: 15px;  /* ★ body default */
--text-input:16px;  /* inputs only — ≥16px prevents iOS Safari zoom on focus */
--text-md:   17px;
--text-lg:   20px;
--text-xl:   24px;
--text-2xl:  32px;
--text-3xl:  40px;
--text-4xl:  52px;

/* Weights */
--weight-regular:  400;
--weight-medium:   500;
--weight-semibold: 600;
--weight-bold:     700;
--weight-heavy:    800;

/* Line height */
--leading-tight:   1.1;
--leading-snug:    1.25;
--leading-normal:  1.4;
--leading-relaxed: 1.6;

/* Letter spacing */
--tracking-tight:   -0.02em;
--tracking-normal:   0;
--tracking-wide:     0.04em;
--tracking-widest:   0.1em;
```

### Tabular numerals (data rendering)

```css
.num, .kpi-value, .metric-value, .tabular {
  font-variant-numeric: tabular-nums lining-nums;
  font-feature-settings: "tnum", "lnum";
}
```

### Label pattern (dashboard KPI labels)

```css
.label {
  font-size: var(--text-xs);
  font-weight: var(--weight-semibold);
  letter-spacing: var(--tracking-widest);
  text-transform: uppercase;
  color: var(--color-text-muted);
}
```

### Utility classes

- Sizes: `.text-2xs`, `.text-xs`, `.text-sm`, `.text-base`, `.text-md`, `.text-lg`, `.text-xl`, `.text-2xl`, `.text-3xl`, `.text-4xl`.
- Weights: `.font-medium`, `.font-semibold`, `.font-bold`.
- Colors: `.text-muted`, `.text-subtle`, `.text-primary`.

## 8 · Spacing, Radii, Shadows, Motion, Z-index, Blur

### Spacing (4-based)

```css
--space-0: 0;    --space-1: 4px;   --space-2: 8px;   --space-3: 12px;
--space-4: 16px; --space-5: 20px;  --space-6: 24px;  --space-8: 32px;
--space-10:40px; --space-12:48px;  --space-16:64px;  --space-20:80px;
```

### Radii

```css
--radius-xs: 4px;   --radius-sm: 8px;   --radius-md: 12px;
--radius-lg: 16px;  --radius-xl: 20px;  --radius-2xl: 24px;
--radius-full: 9999px;
```

### Shadows (solid + glass)

```css
/* Solid */
--shadow-xs: 0 1px 2px rgba(15,23,42,0.05);
--shadow-sm: 0 1px 3px rgba(15,23,42,0.08), 0 1px 2px rgba(15,23,42,0.04);
--shadow-md: 0 4px 12px -2px rgba(15,23,42,0.10), 0 2px 4px rgba(15,23,42,0.04);
--shadow-lg: 0 10px 20px -5px rgba(15,23,42,0.10), 0 4px 8px rgba(15,23,42,0.04);
--shadow-xl: 0 20px 40px -12px rgba(15,23,42,0.14), 0 8px 16px rgba(15,23,42,0.04);

/* Glass (indigo-tinted) */
--shadow-glass-sm: 0 4px 14px -4px rgba(99,102,241,0.18);
--shadow-glass-md: 0 20px 40px -12px rgba(99,102,241,0.22), 0 2px 6px rgba(15,23,42,0.04);
--shadow-glass-lg: 0 30px 60px -15px rgba(99,102,241,0.28), 0 4px 10px rgba(15,23,42,0.05);
```

Dark mode reduces solid opacity and boosts glass saturation (see §6).

### Motion

```css
--duration-fast:   120ms;
--duration-base:   200ms;
--duration-slow:   320ms;
--duration-slower: 480ms;

--ease-linear:       linear;
--ease-out-quart:    cubic-bezier(0.25, 1, 0.5, 1);
--ease-in-out-quart: cubic-bezier(0.76, 0, 0.24, 1);
--ease-spring:       cubic-bezier(0.34, 1.56, 0.64, 1);
--ease-overshoot:    cubic-bezier(0.68, -0.55, 0.265, 1.55);
```

### Reduced motion

```css
@media (prefers-reduced-motion: reduce) {
  :root {
    --duration-fast: 0ms; --duration-base: 0ms; --duration-slow: 0ms;
  }
  *, *::before, *::after {
    animation-duration: 0.01ms !important;
    animation-iteration-count: 1 !important;
    transition-duration: 0.01ms !important;
  }
}
```

### Z-index (named layers)

```css
--z-base:    0;     --z-raised:  10;    --z-sticky:  100;
--z-overlay: 500;   --z-modal:   1000;
--z-toast:   1500;  --z-tooltip: 2000;
```

### Blur

```css
--blur-sm: 8px;   --blur-md: 18px;  --blur-lg: 28px;  --blur-xl: 40px;
```

## 9 · Primitives

### `.btn`

Variants: `primary`, `secondary` (default), `ghost`, `danger`.
Sizes: `sm` (36 px), default (44 px ★ iOS touch), `lg` (52 px).
Modifiers: `btn-block` (100% width), `btn-icon` (square, icon-only).
States: hover, active (scale 0.98), `:focus-visible` (focus ring), `[disabled]` (50% opacity).

Full CSS in §10 of primitives.css implementation (see writing-plans next).

### `.input` + `.field`

- `.input` 44 px min-height, **16 px font-size** (`--text-input`) — prevents iOS Safari zoom on focus.
- States: default, `:hover`, `:focus` (primary border + ring), `[aria-invalid="true"]`, `[disabled]`.
- `.field` wrapper with `.field-label` (uppercase widest tracking), `.field-help`, `.field-error`.

### `.card` + `.card-header` + `.card-body` + `.card-footer`

- Base: solid surface, `--radius-lg`, `--shadow-sm`.
- Variants:
  - `.card-glass` — glass-bg + backdrop-blur + `--radius-xl` + `--shadow-glass-md`.
  - `.card-interactive` — hover elevates with transform + shadow-md.
  - `[data-state="success|warning|danger"]` — tinted shadow that picks up semantic color.
- Component tokens: `--card-bg`, `--card-border`, `--card-shadow`, `--card-radius`.

### `.chip`

Pill with semantic variants: default (neutral), `primary`, `success`, `warning`, `danger`, `info`. Size `--text-xs`, `--weight-semibold`, soft-bg + soft-fg.

### `.badge`

Small count indicator. `min-width: 18px`, danger-red by default. `.badge-dot` (8×8 px, no content) for status indicators.

### Surfaces

- `.surface-solid` — surface + border + radius-lg.
- `.surface-glass` — glass-bg + blur + radius-xl.
- `.surface-sunken` — surface-sunken + radius-lg.

### Layout utilities

```css
.stack          { display: flex; flex-direction: column; }
.stack-1 > * + * { margin-top: var(--space-1); }
/* ... stack-2, stack-3, stack-4, stack-6 */

.cluster        { display: flex; flex-wrap: wrap; }
.cluster-1/2/3/4 { gap: var(--space-N); }

.grid-auto {
  display: grid;
  gap: var(--space-4);
  grid-template-columns: repeat(auto-fit, minmax(var(--grid-min, 240px), 1fr));
}
```

### Skeleton loaders

```css
.skeleton { animated shimmer gradient; }
.skeleton-text  { height: 1em; }
.skeleton-title { height: 1.5em; width: 60%; }
.skeleton-tile  { min-height: 130px; border-radius: var(--radius-xl); }
```

### Ring state pattern (shared primitive)

Used by KPI tiles and any component with semantic state indication:

```css
.ring[data-state="success"] { --ring-color: var(--color-success); }
.ring[data-state="warning"] { --ring-color: var(--color-warning); }
.ring[data-state="danger"]  { --ring-color: var(--color-danger); }
.ring[data-state="neutral"] { --ring-color: var(--color-primary); }

.ring-fg { stroke: var(--ring-color); transition: stroke 0.3s var(--ease-out-quart); }
```

Threshold tokens (used by Jinja to derive `data-state`):

```css
--threshold-success: 85;
--threshold-warning: 70;
```

## 10 · Primitive inventory (Phase 1 final list)

| Primitive | CSS class(es) | Variants |
|---|---|---|
| Button | `.btn` | primary, secondary, ghost, danger · sm/md/lg · block, icon |
| Input | `.input`, `.field`, `.field-label`, `.field-help`, `.field-error` | default, focused, invalid, disabled |
| Card | `.card`, `.card-header`, `.card-body`, `.card-footer` | solid, glass, state-tinted (success/warning/danger), interactive |
| Chip | `.chip` | neutral, primary, success, warning, danger, info |
| Badge | `.badge`, `.badge-dot` | numeric, dot |
| Surfaces | `.surface-solid`, `.surface-glass`, `.surface-sunken` | — |
| Layout utilities | `.stack`, `.stack-1/2/3/4/6`, `.cluster`, `.cluster-1/2/3/4`, `.grid-auto` | — |
| Skeleton | `.skeleton`, `.skeleton-text`, `.skeleton-title`, `.skeleton-tile` | — |
| Ring state | `.ring`, `.ring-bg`, `.ring-fg`, `.ring-text` | `data-state="success/warning/danger/neutral"` |

## 11 · Success criteria (how we know Phase 1 is done)

1. `static/css/tokens.css` and `static/css/primitives.css` exist with all tokens and primitives defined above.
2. `base.html` loads both files before any legacy stylesheet.
3. Existing pages render identically to before (no visual regression on dashboard, pedidos, login, etc.).
4. Light/dark mode switches automatically with `prefers-color-scheme` — verified on macOS browser with simulated dark mode and on iPhone with system dark mode enabled.
5. A demo page (`/dev/primitives` or similar, admin-only) renders all primitives from the showcase in both themes. This page stays in the codebase as a living reference for future phases.
6. Test suite passes (133/133 tests). No new runtime behavior is changed.
7. WCAG AA contrast verified for all token pairings (automated via a script or manual spot-check).
8. Bundle size impact: `tokens.css + primitives.css` combined ≤ 20 KB uncompressed.

## 12 · Out-of-scope reminder

Phase 1 does **not** touch any existing template or visual — users will see no visible change after Phase 1 ships (except the new `/dev/primitives` demo page). The payoff is in Phases 2-5, which build on top of this foundation.

## 13 · Migration path (post-Phase 1)

- Phase 2 (Shell): `base.html` topbar/tabbar rewritten using primitives.
- Phase 3 (Dashboard): `dashboard.html` rewritten using primitives. `dashboard_pro.css` can start to be retired.
- Phases 4-5: each page migrates. Legacy CSS shrinks.
- End of Phase 5: legacy files deleted, minified bundles regenerated.

## 14 · Open questions / future considerations

- **Manual theme toggle**: tokens already support `[data-theme="light|dark"]`. A user-facing toggle (UI + persistence) can be added as a post-Phase-5 enhancement.
- **Icon system**: current app uses Font Awesome. Glass aesthetic might benefit from SF Symbols-inspired icons, but migrating is out of scope for this phase.
- **Typography refinement**: if after Phase 3 a display font (e.g. SF Pro Rounded) is desired for hero KPIs, it can be added as `--font-display` without breaking the current stack.

---

**Next step:** invoke `writing-plans` skill to produce an implementation plan for this spec.
