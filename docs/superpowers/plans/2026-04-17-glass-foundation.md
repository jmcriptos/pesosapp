# Glass Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship Phase 1 of the visual redesign — design tokens + primitive components — as two new CSS files that coexist with the existing stylesheets and introduce zero visual regression on current pages.

**Architecture:** Two new files under `static/css/` (`tokens.css` and `primitives.css`) loaded **before** the existing stylesheets in `base.html`. All styling uses CSS custom properties organized in a two-layer token system (primitive values → semantic aliases). Dark mode is automatic via `prefers-color-scheme`. A new admin-only Flask route `/dev/primitives` renders a showcase template used as a living reference and as the target for integration tests.

**Tech Stack:** Plain CSS (no preprocessors), Flask route + Jinja2 template, pytest for verification.

**Branch strategy:** Work on a feature branch `feat/glass-foundation`. Every commit leaves the app in a shippable state, but the final merge to `main` happens after Task 18 (final verification) to avoid partial-Phase-1 deploys to Heroku.

---

## File Structure

### Created

| File | Responsibility |
|---|---|
| `static/css/tokens.css` | All CSS custom properties: color (L1 + L2 light + L2 dark), typography, spacing, radii, shadows, motion, z-index, blur, reduced-motion override. |
| `static/css/primitives.css` | Primitive components: `.btn`, `.input`, `.field`, `.card`, `.chip`, `.badge`, surfaces, layout utilities, skeleton loaders, ring state pattern, typography utility classes. |
| `templates/dev_primitives.html` | Admin-only showcase page rendering every primitive in light + dark conditions. |
| `tests/test_glass_foundation.py` | File-structure tests (tokens present, selectors present) + Flask integration tests for the showcase route. |

### Modified

| File | Change |
|---|---|
| `templates/base.html` | Add two `<link>` tags for `tokens.css` and `primitives.css` immediately after `<meta name="theme-color">` and before `styles.min.css`. |
| `app.py` | Add `/dev/primitives` route (super_admin-only) that renders the showcase template. |

### Untouched

- `static/styles.css`, `static/styles.min.css`
- `static/dashboard_pro.css`, `static/dashboard_pro.min.css`
- `static/css/main.css`, `static/css/main.min.css`
- `static/css/forms.css`, `static/css/dark-theme.css`
- Any other template

---

## Task 1: Scaffolding — empty files + base.html wiring

**Files:**
- Create: `static/css/tokens.css` (empty shell)
- Create: `static/css/primitives.css` (empty shell)
- Create: `tests/test_glass_foundation.py`
- Modify: `templates/base.html` (add two `<link>` tags)

- [ ] **Step 1: Create feature branch**

```bash
git checkout -b feat/glass-foundation
```

- [ ] **Step 2: Write the failing tests**

Create `tests/test_glass_foundation.py`:

```python
# tests/test_glass_foundation.py
"""Tests for Phase 1 Glass Foundation — design tokens + primitives."""
import os
from pathlib import Path
import pytest

os.environ.setdefault('SECRET_KEY', 'test-secret')
os.environ.setdefault('FLASK_ENV', 'testing')
os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')

PROJECT_ROOT = Path(__file__).resolve().parent.parent
TOKENS_CSS = PROJECT_ROOT / 'static' / 'css' / 'tokens.css'
PRIMITIVES_CSS = PROJECT_ROOT / 'static' / 'css' / 'primitives.css'
BASE_HTML = PROJECT_ROOT / 'templates' / 'base.html'


# ─── Scaffolding ────────────────────────────────────────────────────────

def test_tokens_css_file_exists():
    assert TOKENS_CSS.exists(), f"Expected {TOKENS_CSS} to exist"


def test_primitives_css_file_exists():
    assert PRIMITIVES_CSS.exists(), f"Expected {PRIMITIVES_CSS} to exist"


def test_base_html_loads_tokens_before_primitives_before_legacy_css():
    html = BASE_HTML.read_text(encoding='utf-8')
    tokens_idx = html.find("css/tokens.css")
    primitives_idx = html.find("css/primitives.css")
    legacy_idx = html.find("styles.min.css")
    assert tokens_idx != -1, "tokens.css <link> not found in base.html"
    assert primitives_idx != -1, "primitives.css <link> not found in base.html"
    assert legacy_idx != -1, "legacy styles.min.css <link> not found — did base.html change?"
    assert tokens_idx < primitives_idx < legacy_idx, (
        f"Expected order: tokens.css ({tokens_idx}) < primitives.css ({primitives_idx}) "
        f"< styles.min.css ({legacy_idx})"
    )
```

- [ ] **Step 3: Run the tests to verify they fail**

```bash
source .venv311/bin/activate && python -m pytest -p no:postgresql tests/test_glass_foundation.py -v
```

Expected: 3 tests FAIL (files don't exist yet, link tags missing).

- [ ] **Step 4: Create the empty CSS files**

Create `static/css/tokens.css` with only a header comment:

```css
/* =============================================================================
   PesosApp · Design Tokens · Phase 1 Glass Foundation
   See docs/superpowers/specs/2026-04-17-glass-foundation-design.md
   ============================================================================= */
```

Create `static/css/primitives.css` with only a header comment:

```css
/* =============================================================================
   PesosApp · Primitive Components · Phase 1 Glass Foundation
   See docs/superpowers/specs/2026-04-17-glass-foundation-design.md
   ============================================================================= */
```

- [ ] **Step 5: Add `<link>` tags to `templates/base.html`**

Using the Edit tool, replace the block:

```html
    <!-- CSS Files - FORZAR MINIFICADOS PARA TESTING -->
    <link rel="stylesheet" href="{{ url_for('static', filename='styles.min.css') }}">
```

with:

```html
    <!-- Phase 1 Glass Foundation — design tokens + primitives (loaded FIRST) -->
    <link rel="stylesheet" href="{{ url_for('static', filename='css/tokens.css') }}">
    <link rel="stylesheet" href="{{ url_for('static', filename='css/primitives.css') }}">

    <!-- CSS Files - FORZAR MINIFICADOS PARA TESTING -->
    <link rel="stylesheet" href="{{ url_for('static', filename='styles.min.css') }}">
```

- [ ] **Step 6: Run the tests to verify they pass**

```bash
python -m pytest -p no:postgresql tests/test_glass_foundation.py -v
```

Expected: 3 tests PASS.

- [ ] **Step 7: Run full test suite — no regressions**

```bash
python -m pytest -p no:postgresql tests/ -v 2>&1 | tail -5
```

Expected: 136 passed (133 existing + 3 new).

- [ ] **Step 8: Commit**

```bash
git add static/css/tokens.css static/css/primitives.css templates/base.html tests/test_glass_foundation.py
git commit -m "$(cat <<'EOF'
feat(css): scaffold Phase 1 glass foundation

Add empty tokens.css and primitives.css under static/css/, wire both
into base.html before the legacy stylesheets, and add file-structure
tests that lock the load order.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: Color tokens — Layer 1 primitives + Layer 2 light + dark override

**Files:**
- Modify: `static/css/tokens.css` (append color blocks)
- Modify: `tests/test_glass_foundation.py` (add color token tests)

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_glass_foundation.py`:

```python
# ─── Color tokens ───────────────────────────────────────────────────────

def _read_tokens():
    return TOKENS_CSS.read_text(encoding='utf-8')


def test_color_primitives_layer1_present():
    css = _read_tokens()
    # Representative primitives — if these are here the rest of the scale is too
    assert '--gray-50: #f8fafc' in css
    assert '--gray-900: #0f172a' in css
    assert '--gray-950: #020617' in css
    assert '--indigo-500: #6366f1' in css  # brand primary
    assert '--indigo-700: #4338ca' in css
    assert '--violet-500: #8b5cf6' in css
    assert '--emerald-500: #10b981' in css
    assert '--amber-500: #f59e0b' in css
    assert '--rose-500: #f43f5e' in css
    assert '--sky-500: #0ea5e9' in css


def test_color_semantic_light_references_primitives():
    css = _read_tokens()
    assert '--color-primary: var(--indigo-500)' in css
    assert '--color-text: var(--gray-900)' in css
    assert '--color-success: var(--emerald-500)' in css
    assert '--color-danger: var(--rose-500)' in css
    # Glass tokens
    assert '--glass-bg: rgba(255, 255, 255, 0.72)' in css
    assert '--glass-blur:' in css
    # Ambient gradient
    assert '--bg-ambient:' in css and 'linear-gradient' in css
    # Focus ring
    assert '--focus-ring:' in css


def test_dark_mode_media_query_overrides_semantic_tokens():
    css = _read_tokens()
    # The dark block must be present
    assert '@media (prefers-color-scheme: dark)' in css
    # Find the dark block content
    dark_start = css.find('@media (prefers-color-scheme: dark)')
    dark_end = css.find('@media', dark_start + 1)
    if dark_end == -1:
        dark_end = len(css)
    dark_block = css[dark_start:dark_end]
    # Key dark overrides
    assert '--color-bg:' in dark_block
    assert '--color-text:' in dark_block
    assert '--color-surface:' in dark_block
    assert '--glass-bg:' in dark_block
    assert '--color-primary:' in dark_block
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
python -m pytest -p no:postgresql tests/test_glass_foundation.py -v -k "color or dark"
```

Expected: 3 tests FAIL.

- [ ] **Step 3: Implement — append the color section to `static/css/tokens.css`**

```css

/* ─── Layer 1: Color primitives ──────────────────────────────────────── */
:root {
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
  --indigo-500: #6366f1;   /* brand primary */
  --indigo-600: #4f46e5;
  --indigo-700: #4338ca;
  --indigo-800: #3730a3;
  --indigo-900: #312e81;

  /* Violet (accent) */
  --violet-400: #a78bfa;
  --violet-500: #8b5cf6;
  --violet-600: #7c3aed;

  /* Emerald (success) */
  --emerald-400: #34d399;
  --emerald-500: #10b981;
  --emerald-600: #059669;

  /* Amber (warning) */
  --amber-400: #fbbf24;
  --amber-500: #f59e0b;
  --amber-600: #d97706;

  /* Rose (danger) */
  --rose-400: #fb7185;
  --rose-500: #f43f5e;
  --rose-600: #e11d48;

  /* Sky (info) */
  --sky-400: #38bdf8;
  --sky-500: #0ea5e9;
  --sky-600: #0284c7;
}

/* ─── Layer 2: Semantic tokens (LIGHT) ───────────────────────────────── */
:root {
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

  /* Glass surfaces */
  --glass-bg:        rgba(255, 255, 255, 0.72);
  --glass-bg-strong: rgba(255, 255, 255, 0.85);
  --glass-border:    rgba(255, 255, 255, 0.9);
  --glass-blur:      blur(18px) saturate(1.2);

  /* Ambient page background */
  --bg-ambient: linear-gradient(135deg, #eef2ff 0%, #ffffff 45%, #fdf2f8 100%);

  /* Primary */
  --color-primary:         var(--indigo-500);
  --color-primary-hover:   var(--indigo-600);
  --color-primary-active:  var(--indigo-700);
  --color-primary-fg:      #ffffff;
  --color-primary-soft:    var(--indigo-50);
  --color-primary-soft-fg: var(--indigo-700);

  /* Accent */
  --color-accent:      var(--violet-500);
  --color-accent-soft: #f3e8ff;

  /* Semantic roles */
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

/* ─── Layer 2: Semantic tokens (DARK) ────────────────────────────────── */
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

    --color-primary:         var(--indigo-400);
    --color-primary-hover:   var(--indigo-300);
    --color-primary-active:  var(--indigo-200);
    --color-primary-fg:      var(--gray-900);
    --color-primary-soft:    rgba(99, 102, 241, 0.15);
    --color-primary-soft-fg: var(--indigo-300);

    --color-accent:      var(--violet-400);
    --color-accent-soft: rgba(139, 92, 246, 0.15);

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

- [ ] **Step 4: Run color tests to verify they pass**

```bash
python -m pytest -p no:postgresql tests/test_glass_foundation.py -v -k "color or dark"
```

Expected: 3 tests PASS.

- [ ] **Step 5: Run full test suite**

```bash
python -m pytest -p no:postgresql tests/ 2>&1 | tail -3
```

Expected: 139 passed.

- [ ] **Step 6: Commit**

```bash
git add static/css/tokens.css tests/test_glass_foundation.py
git commit -m "feat(css): add color tokens (L1 primitives + L2 light + dark override)"
```

---

## Task 3: Typography tokens

**Files:**
- Modify: `static/css/tokens.css` (append typography block)
- Modify: `tests/test_glass_foundation.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_glass_foundation.py`:

```python
# ─── Typography ─────────────────────────────────────────────────────────

def test_typography_tokens_present():
    css = _read_tokens()
    assert '--font-sans:' in css
    assert 'SF Pro Display' in css  # iOS-native stack
    assert '--font-mono:' in css
    # Size scale
    for token in ['--text-2xs', '--text-xs', '--text-sm', '--text-base',
                  '--text-input', '--text-md', '--text-lg', '--text-xl',
                  '--text-2xl', '--text-3xl', '--text-4xl']:
        assert f'{token}:' in css, f"missing {token}"
    # Input must be 16px to prevent iOS zoom
    assert '--text-input: 16px' in css
    # Weights
    for token in ['--weight-regular', '--weight-medium',
                  '--weight-semibold', '--weight-bold', '--weight-heavy']:
        assert f'{token}:' in css
    # Line height
    assert '--leading-tight:' in css
    assert '--leading-normal:' in css
    # Tracking
    assert '--tracking-tight:' in css
    assert '--tracking-widest:' in css
```

- [ ] **Step 2: Run test to verify failure**

```bash
python -m pytest -p no:postgresql tests/test_glass_foundation.py::test_typography_tokens_present -v
```

Expected: FAIL.

- [ ] **Step 3: Implement — append to `static/css/tokens.css`**

```css

/* ─── Typography ─────────────────────────────────────────────────────── */
:root {
  --font-sans: -apple-system, BlinkMacSystemFont, 'SF Pro Display',
               'SF Pro Text', 'Inter', 'Segoe UI', Roboto, system-ui, sans-serif;
  --font-mono: ui-monospace, 'SF Mono', 'Menlo', 'Consolas', monospace;
  --font-numeric: var(--font-sans);

  /* Size scale (mobile base 15px) */
  --text-2xs:   10px;
  --text-xs:    11px;
  --text-sm:    13px;
  --text-base:  15px;   /* body default */
  --text-input: 16px;   /* inputs only — prevents iOS Safari zoom on focus */
  --text-md:    17px;
  --text-lg:    20px;
  --text-xl:    24px;
  --text-2xl:   32px;
  --text-3xl:   40px;
  --text-4xl:   52px;

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
}
```

- [ ] **Step 4: Run test to verify pass**

```bash
python -m pytest -p no:postgresql tests/test_glass_foundation.py::test_typography_tokens_present -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add static/css/tokens.css tests/test_glass_foundation.py
git commit -m "feat(css): add typography tokens"
```

---

## Task 4: Spacing, radii, shadows, motion, z-index, blur

**Files:**
- Modify: `static/css/tokens.css`
- Modify: `tests/test_glass_foundation.py`

- [ ] **Step 1: Write the failing tests**

Append:

```python
# ─── Spacing / radii / shadows / motion / z-index / blur ────────────────

def test_structural_tokens_present():
    css = _read_tokens()
    # Spacing
    for t in ['--space-0', '--space-1', '--space-2', '--space-3', '--space-4',
              '--space-5', '--space-6', '--space-8', '--space-10',
              '--space-12', '--space-16', '--space-20']:
        assert f'{t}:' in css
    assert '--space-4: 16px' in css  # base
    # Radii
    for t in ['--radius-xs', '--radius-sm', '--radius-md', '--radius-lg',
              '--radius-xl', '--radius-2xl', '--radius-full']:
        assert f'{t}:' in css
    # Shadows
    for t in ['--shadow-xs', '--shadow-sm', '--shadow-md', '--shadow-lg',
              '--shadow-xl', '--shadow-glass-sm', '--shadow-glass-md',
              '--shadow-glass-lg']:
        assert f'{t}:' in css
    # Motion
    assert '--duration-fast: 120ms' in css
    assert '--duration-base: 200ms' in css
    assert '--ease-out-quart:' in css
    assert '--ease-spring:' in css
    # Z-index
    for t in ['--z-base', '--z-raised', '--z-sticky',
              '--z-overlay', '--z-modal', '--z-toast', '--z-tooltip']:
        assert f'{t}:' in css
    # Blur
    for t in ['--blur-sm', '--blur-md', '--blur-lg', '--blur-xl']:
        assert f'{t}:' in css


def test_dark_mode_shadow_overrides_present():
    css = _read_tokens()
    dark_start = css.find('@media (prefers-color-scheme: dark)')
    dark_end_candidates = [css.find('@media', dark_start + 1)]
    dark_end = min(i for i in dark_end_candidates if i != -1) if any(
        i != -1 for i in dark_end_candidates) else len(css)
    dark_block = css[dark_start:dark_end]
    # Dark mode should reduce solid shadows (black-on-black loses them)
    assert '--shadow-sm:' in dark_block
    assert '--shadow-md:' in dark_block
```

- [ ] **Step 2: Run tests to verify failure**

```bash
python -m pytest -p no:postgresql tests/test_glass_foundation.py -v -k "structural or shadow"
```

Expected: 2 tests FAIL.

- [ ] **Step 3: Implement — append to `static/css/tokens.css`**

```css

/* ─── Spacing (4-based scale) ─────────────────────────────────────────── */
:root {
  --space-0:   0;
  --space-1:   4px;
  --space-2:   8px;
  --space-3:   12px;
  --space-4:   16px;   /* base */
  --space-5:   20px;
  --space-6:   24px;
  --space-8:   32px;
  --space-10:  40px;
  --space-12:  48px;
  --space-16:  64px;
  --space-20:  80px;
}

/* ─── Radii ───────────────────────────────────────────────────────────── */
:root {
  --radius-xs:   4px;
  --radius-sm:   8px;
  --radius-md:   12px;
  --radius-lg:   16px;
  --radius-xl:   20px;
  --radius-2xl:  24px;
  --radius-full: 9999px;
}

/* ─── Shadows (solid + glass — LIGHT defaults) ────────────────────────── */
:root {
  --shadow-xs: 0 1px 2px rgba(15,23,42,0.05);
  --shadow-sm: 0 1px 3px rgba(15,23,42,0.08), 0 1px 2px rgba(15,23,42,0.04);
  --shadow-md: 0 4px 12px -2px rgba(15,23,42,0.10), 0 2px 4px rgba(15,23,42,0.04);
  --shadow-lg: 0 10px 20px -5px rgba(15,23,42,0.10), 0 4px 8px rgba(15,23,42,0.04);
  --shadow-xl: 0 20px 40px -12px rgba(15,23,42,0.14), 0 8px 16px rgba(15,23,42,0.04);

  --shadow-glass-sm: 0 4px 14px -4px rgba(99,102,241,0.18);
  --shadow-glass-md: 0 20px 40px -12px rgba(99,102,241,0.22), 0 2px 6px rgba(15,23,42,0.04);
  --shadow-glass-lg: 0 30px 60px -15px rgba(99,102,241,0.28), 0 4px 10px rgba(15,23,42,0.05);
}

/* Dark mode shadow overrides (append to existing dark block) */
@media (prefers-color-scheme: dark) {
  :root {
    --shadow-xs: 0 1px 2px rgba(0,0,0,0.3);
    --shadow-sm: 0 1px 3px rgba(0,0,0,0.35);
    --shadow-md: 0 4px 12px -2px rgba(0,0,0,0.4);
    --shadow-lg: 0 10px 20px -5px rgba(0,0,0,0.5);
    --shadow-xl: 0 20px 40px -12px rgba(0,0,0,0.6);
    --shadow-glass-sm: 0 4px 14px -4px rgba(129,140,248,0.25);
    --shadow-glass-md: 0 20px 40px -12px rgba(129,140,248,0.3), 0 2px 6px rgba(0,0,0,0.3);
    --shadow-glass-lg: 0 30px 60px -15px rgba(129,140,248,0.4);
  }
}

/* ─── Motion ─────────────────────────────────────────────────────────── */
:root {
  --duration-fast:   120ms;
  --duration-base:   200ms;
  --duration-slow:   320ms;
  --duration-slower: 480ms;

  --ease-linear:       linear;
  --ease-out-quart:    cubic-bezier(0.25, 1, 0.5, 1);
  --ease-in-out-quart: cubic-bezier(0.76, 0, 0.24, 1);
  --ease-spring:       cubic-bezier(0.34, 1.56, 0.64, 1);
  --ease-overshoot:    cubic-bezier(0.68, -0.55, 0.265, 1.55);
}

/* ─── Z-index (named layers) ─────────────────────────────────────────── */
:root {
  --z-base:    0;
  --z-raised:  10;
  --z-sticky:  100;
  --z-overlay: 500;
  --z-modal:   1000;
  --z-toast:   1500;
  --z-tooltip: 2000;
}

/* ─── Blur ───────────────────────────────────────────────────────────── */
:root {
  --blur-sm: 8px;
  --blur-md: 18px;  /* default glass */
  --blur-lg: 28px;
  --blur-xl: 40px;
}
```

- [ ] **Step 4: Run tests to verify pass**

```bash
python -m pytest -p no:postgresql tests/test_glass_foundation.py -v -k "structural or shadow"
```

Expected: 2 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add static/css/tokens.css tests/test_glass_foundation.py
git commit -m "feat(css): add spacing, radii, shadows, motion, z-index, blur tokens"
```

---

## Task 5: Reduced motion override

**Files:**
- Modify: `static/css/tokens.css`
- Modify: `tests/test_glass_foundation.py`

- [ ] **Step 1: Write the failing test**

Append:

```python
def test_reduced_motion_override_present():
    css = _read_tokens()
    assert '@media (prefers-reduced-motion: reduce)' in css
    # Must disable animations globally
    rm_start = css.find('@media (prefers-reduced-motion: reduce)')
    rm_block = css[rm_start:rm_start + 1000]
    assert 'animation-duration: 0.01ms' in rm_block
    assert 'transition-duration: 0.01ms' in rm_block
```

- [ ] **Step 2: Verify failure**

```bash
python -m pytest -p no:postgresql tests/test_glass_foundation.py::test_reduced_motion_override_present -v
```

Expected: FAIL.

- [ ] **Step 3: Append to `static/css/tokens.css`**

```css

/* ─── Reduced motion override ────────────────────────────────────────── */
@media (prefers-reduced-motion: reduce) {
  :root {
    --duration-fast:   0ms;
    --duration-base:   0ms;
    --duration-slow:   0ms;
    --duration-slower: 0ms;
  }
  *, *::before, *::after {
    animation-duration: 0.01ms !important;
    animation-iteration-count: 1 !important;
    transition-duration: 0.01ms !important;
    scroll-behavior: auto !important;
  }
}
```

- [ ] **Step 4: Verify pass**

```bash
python -m pytest -p no:postgresql tests/test_glass_foundation.py::test_reduced_motion_override_present -v
```

- [ ] **Step 5: Commit**

```bash
git add static/css/tokens.css tests/test_glass_foundation.py
git commit -m "feat(css): honor prefers-reduced-motion"
```

---

## Task 6: Demo route `/dev/primitives` + template scaffolding

**Files:**
- Modify: `app.py` (add new route)
- Create: `templates/dev_primitives.html`
- Modify: `tests/test_glass_foundation.py` (add Flask integration tests)

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_glass_foundation.py`:

```python
# ─── Demo route /dev/primitives ─────────────────────────────────────────

from datetime import datetime
from zoneinfo import ZoneInfo

from app import app as flask_app, db as _db


@pytest.fixture
def app():
    flask_app.config.update(
        TESTING=True,
        WTF_CSRF_ENABLED=False,
        SQLALCHEMY_DATABASE_URI='sqlite:///:memory:',
    )
    with flask_app.app_context():
        _db.create_all()
        from app import Rol, Territorio, Vendedor
        rol = Rol(nombre='super_admin', descripcion='Admin')
        _db.session.add(rol)
        territorio = Territorio(nombre='test', descripcion='Test')
        _db.session.add(territorio)
        _db.session.flush()
        vendedor = Vendedor(
            username='admin',
            email='admin@test.com',
            nombre_completo='Admin Test',
            rol_id=rol.id,
            territorio_id=territorio.id,
            activo=True,
        )
        vendedor.set_password('testpass')
        _db.session.add(vendedor)
        _db.session.commit()
        yield flask_app
        _db.drop_all()


@pytest.fixture
def logged_client(app):
    client = app.test_client()
    client.post('/login', data={
        'username': 'admin',
        'password': 'testpass',
    }, follow_redirects=True)
    return client


def test_dev_primitives_requires_login(app):
    client = app.test_client()
    resp = client.get('/dev/primitives', follow_redirects=False)
    # Should redirect to login (302) or deny (401/403)
    assert resp.status_code in (302, 401, 403), (
        f"Expected redirect/deny for anonymous access, got {resp.status_code}"
    )


def test_dev_primitives_renders_for_admin(logged_client):
    resp = logged_client.get('/dev/primitives')
    assert resp.status_code == 200
    html = resp.data.decode('utf-8')
    # Scaffold marker — we'll expand this test as primitives land
    assert 'glass-foundation-demo' in html
    # The new CSS files must be loaded via base.html
    assert 'css/tokens.css' in html
    assert 'css/primitives.css' in html
```

- [ ] **Step 2: Verify failure**

```bash
python -m pytest -p no:postgresql tests/test_glass_foundation.py -v -k "dev_primitives"
```

Expected: 2 tests FAIL (route missing → 404).

- [ ] **Step 3: Create `templates/dev_primitives.html`**

```html
{% extends "base.html" %}

{% block title %}Glass Foundation · Primitives Showcase{% endblock %}

{% block header_title %}Primitives{% endblock %}

{% block content %}
<main class="glass-foundation-demo" style="padding: var(--space-5, 20px); max-width: 960px; margin: 0 auto;">
  <h1 style="font-size: var(--text-xl, 24px); font-weight: var(--weight-bold, 700);">
    Glass Foundation · Primitives
  </h1>
  <p style="color: var(--color-text-muted, #475569); font-size: var(--text-sm, 13px); margin-top: 4px;">
    Living reference for every primitive defined in Phase 1. Switch macOS/iOS between light and dark mode to verify both themes.
  </p>

  {# Primitive sections will be appended here in subsequent tasks. #}
  <section data-section="placeholder" style="margin-top: var(--space-8, 32px); color: var(--color-text-subtle, #64748b);">
    Primitives will be added here in Tasks 7-16.
  </section>
</main>
{% endblock %}
```

- [ ] **Step 4: Add the Flask route in `app.py`**

Locate the end of the dashboard-related routes (after `@app.route('/dashboard')`'s function body closes, look for a logical spot with `@app.route` siblings). Add:

```python
@app.route('/dev/primitives')
@login_required
def dev_primitives():
    """Admin-only showcase for Phase 1 glass foundation primitives.

    Living reference used by Phases 2-5. Renders every primitive in
    both light and dark themes (theme comes from the user's system
    setting via prefers-color-scheme)."""
    if not isinstance(current_user, Vendedor) or current_user.rol.nombre != 'super_admin':
        abort(403)
    return render_template('dev_primitives.html')
```

If `abort` is not imported, ensure `from flask import abort` is present (already is, likely; verify via search).

- [ ] **Step 5: Verify `abort` is importable**

```bash
grep -n "^from flask import" app.py | head -3
```

If `abort` is missing from the Flask imports line, edit it to add `abort`. Example replacement:

```python
from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify, abort
```

- [ ] **Step 6: Run tests to verify pass**

```bash
python -m pytest -p no:postgresql tests/test_glass_foundation.py -v -k "dev_primitives"
```

Expected: 2 tests PASS.

- [ ] **Step 7: Manually open the demo in a browser (optional but recommended)**

```bash
# In another shell
source .venv311/bin/activate && FLASK_ENV=development python app.py
# Visit http://localhost:5000/dev/primitives after logging in
```

- [ ] **Step 8: Commit**

```bash
git add app.py templates/dev_primitives.html tests/test_glass_foundation.py
git commit -m "feat(css): add /dev/primitives showcase route (scaffolding)"
```

---

## Task 7: `.btn` primitive + showcase block

**Files:**
- Modify: `static/css/primitives.css` (add `.btn`)
- Modify: `templates/dev_primitives.html` (showcase block)
- Modify: `tests/test_glass_foundation.py`

- [ ] **Step 1: Write the failing tests**

Append:

```python
# ─── Primitives ─────────────────────────────────────────────────────────

def _read_primitives():
    return PRIMITIVES_CSS.read_text(encoding='utf-8')


def test_btn_primitive_defined():
    css = _read_primitives()
    # Base
    assert '.btn {' in css or '.btn{' in css
    # Variants
    assert '.btn-primary' in css
    assert '.btn-ghost' in css
    assert '.btn-danger' in css
    # Sizes
    assert '.btn-sm' in css
    assert '.btn-lg' in css
    # Modifiers
    assert '.btn-block' in css
    assert '.btn-icon' in css
    # Must use tokens (not hardcoded color)
    assert 'var(--color-primary)' in css
    # iOS touch target
    assert 'min-height: 44px' in css or 'min-height:44px' in css


def test_dev_primitives_renders_btn_variants(logged_client):
    resp = logged_client.get('/dev/primitives')
    html = resp.data.decode('utf-8')
    # At minimum the showcase has examples of each variant
    for cls in ['btn-primary', 'btn-ghost', 'btn-danger',
                'btn-sm', 'btn-lg', 'btn-block']:
        assert cls in html, f"missing {cls} in /dev/primitives"
```

- [ ] **Step 2: Verify failure**

```bash
python -m pytest -p no:postgresql tests/test_glass_foundation.py -v -k "btn"
```

Expected: 2 FAIL.

- [ ] **Step 3: Append `.btn` block to `static/css/primitives.css`**

```css

/* ─── .btn ───────────────────────────────────────────────────────────── */
.btn {
  --btn-bg: var(--color-surface);
  --btn-fg: var(--color-text);
  --btn-border: var(--color-border);
  --btn-shadow: var(--shadow-xs);

  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: var(--space-2);
  padding: var(--space-2) var(--space-4);
  font-family: var(--font-sans);
  font-size: var(--text-sm);
  font-weight: var(--weight-semibold);
  line-height: 1;
  border-radius: var(--radius-md);
  border: 1px solid var(--btn-border);
  background: var(--btn-bg);
  color: var(--btn-fg);
  box-shadow: var(--btn-shadow);
  cursor: pointer;
  user-select: none;
  min-height: 44px;           /* iOS touch target */
  text-decoration: none;
  transition:
    background var(--duration-fast) var(--ease-out-quart),
    transform var(--duration-fast) var(--ease-spring),
    box-shadow var(--duration-base) var(--ease-out-quart);
}
.btn:hover  { transform: translateY(-1px); box-shadow: var(--shadow-sm); }
.btn:active { transform: translateY(0) scale(0.98); }
.btn:focus-visible { outline: none; box-shadow: var(--focus-ring); }
.btn[disabled] { opacity: 0.5; cursor: not-allowed; transform: none; }

/* Variants */
.btn-primary {
  --btn-bg: var(--color-primary);
  --btn-fg: var(--color-primary-fg);
  --btn-border: transparent;
  --btn-shadow: var(--shadow-glass-sm);
}
.btn-primary:hover { --btn-bg: var(--color-primary-hover); }

.btn-ghost {
  --btn-bg: transparent;
  --btn-fg: var(--color-primary-soft-fg);
  --btn-border: transparent;
  --btn-shadow: none;
}
.btn-ghost:hover { --btn-bg: var(--color-primary-soft); }

.btn-danger {
  --btn-bg: var(--color-danger);
  --btn-fg: var(--color-danger-fg);
  --btn-border: transparent;
}

/* Sizes */
.btn-sm { padding: var(--space-1) var(--space-3); min-height: 36px; font-size: var(--text-xs); }
.btn-lg { padding: var(--space-3) var(--space-6); min-height: 52px; font-size: var(--text-md); }

/* Modifiers */
.btn-block { width: 100%; }
.btn-icon  { width: 44px; padding: 0; aspect-ratio: 1; }
```

- [ ] **Step 4: Replace the placeholder in `templates/dev_primitives.html`**

Replace:
```html
  <section data-section="placeholder" style="margin-top: var(--space-8, 32px); color: var(--color-text-subtle, #64748b);">
    Primitives will be added here in Tasks 7-16.
  </section>
```

with:
```html
  <section data-section="btn" style="margin-top: var(--space-8, 32px);">
    <h2 style="font-size: var(--text-lg); font-weight: var(--weight-bold);">.btn — Button</h2>
    <div style="display:flex; flex-wrap:wrap; gap: var(--space-2); margin-top: var(--space-3);">
      <button class="btn btn-primary">Primary</button>
      <button class="btn">Secondary</button>
      <button class="btn btn-ghost">Ghost</button>
      <button class="btn btn-danger">Danger</button>
    </div>
    <div style="display:flex; flex-wrap:wrap; gap: var(--space-2); margin-top: var(--space-3);">
      <button class="btn btn-primary btn-sm">Small</button>
      <button class="btn btn-primary">Medium</button>
      <button class="btn btn-primary btn-lg">Large</button>
      <button class="btn btn-primary btn-icon" aria-label="Confirm">✓</button>
      <button class="btn btn-primary" disabled>Disabled</button>
    </div>
    <button class="btn btn-primary btn-block btn-lg" style="margin-top: var(--space-3);">Block button (mobile)</button>
  </section>
```

- [ ] **Step 5: Verify pass**

```bash
python -m pytest -p no:postgresql tests/test_glass_foundation.py -v -k "btn"
```

Expected: 2 PASS.

- [ ] **Step 6: Commit**

```bash
git add static/css/primitives.css templates/dev_primitives.html tests/test_glass_foundation.py
git commit -m "feat(css): add .btn primitive (4 variants × 3 sizes + block/icon)"
```

---

## Task 8: `.input` + `.field` primitives

**Files:**
- Modify: `static/css/primitives.css`
- Modify: `templates/dev_primitives.html`
- Modify: `tests/test_glass_foundation.py`

- [ ] **Step 1: Write the failing tests**

Append:

```python
def test_input_primitive_defined():
    css = _read_primitives()
    assert '.input {' in css or '.input{' in css
    assert '.field' in css
    assert '.field-label' in css
    assert '.field-help' in css
    assert '.field-error' in css
    # Must use --text-input (16px) to avoid iOS zoom
    assert 'var(--text-input)' in css
    # Invalid state binding
    assert '[aria-invalid="true"]' in css


def test_dev_primitives_renders_input_examples(logged_client):
    resp = logged_client.get('/dev/primitives')
    html = resp.data.decode('utf-8')
    assert 'class="input"' in html or "class='input'" in html
    assert 'field-label' in html
    assert 'field-error' in html
```

- [ ] **Step 2: Verify failure**

```bash
python -m pytest -p no:postgresql tests/test_glass_foundation.py -v -k "input"
```

- [ ] **Step 3: Append `.input` block to `static/css/primitives.css`**

```css

/* ─── .input + .field ─────────────────────────────────────────────────── */
.input {
  display: block;
  width: 100%;
  padding: var(--space-3) var(--space-4);
  font-family: var(--font-sans);
  font-size: var(--text-input);    /* 16px — prevents iOS zoom */
  font-weight: var(--weight-regular);
  line-height: var(--leading-normal);
  color: var(--color-text);
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  min-height: 44px;
  transition:
    border-color var(--duration-fast) var(--ease-out-quart),
    box-shadow var(--duration-base) var(--ease-out-quart);
}
.input::placeholder { color: var(--color-text-subtle); }
.input:hover { border-color: var(--color-border-strong); }
.input:focus {
  outline: none;
  border-color: var(--color-primary);
  box-shadow: var(--focus-ring);
}
.input[aria-invalid="true"] { border-color: var(--color-danger); }
.input[aria-invalid="true"]:focus {
  box-shadow: 0 0 0 3px rgba(244,63,94,0.25);
}
.input[disabled] { background: var(--color-surface-muted); opacity: 0.7; cursor: not-allowed; }

.field { display: flex; flex-direction: column; gap: var(--space-2); }
.field-label {
  font-size: var(--text-xs);
  font-weight: var(--weight-semibold);
  color: var(--color-text-muted);
  letter-spacing: var(--tracking-widest);
  text-transform: uppercase;
}
.field-help  { font-size: var(--text-xs); color: var(--color-text-subtle); }
.field-error { font-size: var(--text-xs); color: var(--color-danger); }
```

- [ ] **Step 4: Append to `templates/dev_primitives.html`** (inside the `<main>`, after the `.btn` section)

```html

  <section data-section="input" style="margin-top: var(--space-8);">
    <h2 style="font-size: var(--text-lg); font-weight: var(--weight-bold);">.input — Input + .field</h2>
    <div style="display: grid; gap: var(--space-3); margin-top: var(--space-3);">
      <div class="field">
        <label class="field-label" for="demo-cliente">Cliente</label>
        <input class="input" id="demo-cliente" placeholder="Buscar cliente…">
        <span class="field-help">Nombre o QBO ID</span>
      </div>
      <div class="field">
        <label class="field-label" for="demo-email">Correo</label>
        <input class="input" id="demo-email" value="jose@jomarfoods.com">
      </div>
      <div class="field">
        <label class="field-label" for="demo-monto">Monto XCG</label>
        <input class="input" id="demo-monto" value="-450" aria-invalid="true">
        <span class="field-error">El monto debe ser positivo</span>
      </div>
      <div class="field">
        <label class="field-label" for="demo-disabled">Solo lectura</label>
        <input class="input" id="demo-disabled" value="Bloqueado" disabled>
      </div>
    </div>
  </section>
```

- [ ] **Step 5: Verify pass**

```bash
python -m pytest -p no:postgresql tests/test_glass_foundation.py -v -k "input"
```

- [ ] **Step 6: Commit**

```bash
git add static/css/primitives.css templates/dev_primitives.html tests/test_glass_foundation.py
git commit -m "feat(css): add .input + .field primitives (incl. invalid state)"
```

---

## Task 9: `.card` + variants (solid, glass, state-tinted, interactive)

**Files:**
- Modify: `static/css/primitives.css`
- Modify: `templates/dev_primitives.html`
- Modify: `tests/test_glass_foundation.py`

- [ ] **Step 1: Write the failing tests**

Append:

```python
def test_card_primitive_defined():
    css = _read_primitives()
    for sel in ['.card', '.card-header', '.card-body', '.card-footer',
                '.card-glass', '.card-interactive']:
        assert sel in css, f"missing selector: {sel}"
    # State-tinted
    assert '[data-state="success"]' in css
    assert '[data-state="warning"]' in css
    assert '[data-state="danger"]' in css


def test_dev_primitives_renders_card_variants(logged_client):
    resp = logged_client.get('/dev/primitives')
    html = resp.data.decode('utf-8')
    assert 'card-glass' in html
    assert 'data-state="success"' in html
    assert 'data-state="danger"' in html
```

- [ ] **Step 2: Verify failure**

```bash
python -m pytest -p no:postgresql tests/test_glass_foundation.py -v -k "card"
```

- [ ] **Step 3: Append to `static/css/primitives.css`**

```css

/* ─── .card (+header, body, footer) + variants ────────────────────────── */
.card {
  --card-bg: var(--color-surface);
  --card-border: var(--color-border);
  --card-shadow: var(--shadow-sm);
  --card-radius: var(--radius-lg);

  background: var(--card-bg);
  border: 1px solid var(--card-border);
  border-radius: var(--card-radius);
  box-shadow: var(--card-shadow);
  overflow: hidden;
  transition:
    box-shadow var(--duration-base) var(--ease-out-quart),
    transform var(--duration-base) var(--ease-spring);
}
.card-interactive { cursor: pointer; }
.card-interactive:hover {
  box-shadow: var(--shadow-md);
  transform: translateY(-2px);
}

.card-header {
  padding: var(--space-4) var(--space-5);
  border-bottom: 1px solid var(--color-border-subtle);
  display: flex; align-items: center; justify-content: space-between;
  gap: var(--space-3);
}
.card-body   { padding: var(--space-5); }
.card-footer {
  padding: var(--space-4) var(--space-5);
  border-top: 1px solid var(--color-border-subtle);
  background: var(--color-surface-muted);
}

/* Glass variant */
.card-glass {
  --card-bg: var(--glass-bg);
  --card-border: var(--glass-border);
  --card-shadow: var(--shadow-glass-md);
  --card-radius: var(--radius-xl);
  backdrop-filter: var(--glass-blur);
  -webkit-backdrop-filter: var(--glass-blur);
}

/* State-tinted shadows (used by KPI tiles per §9 of spec) */
.card[data-state="success"] { box-shadow: 0 20px 40px -12px rgba(16,185,129,0.22), var(--shadow-sm); }
.card[data-state="warning"] { box-shadow: 0 20px 40px -12px rgba(245,158,11,0.22), var(--shadow-sm); }
.card[data-state="danger"]  { box-shadow: 0 20px 40px -12px rgba(244,63,94,0.22), var(--shadow-sm); }
```

- [ ] **Step 4: Append showcase to `templates/dev_primitives.html`**

```html

  <section data-section="card" style="margin-top: var(--space-8);">
    <h2 style="font-size: var(--text-lg); font-weight: var(--weight-bold);">.card — Card + variants</h2>
    <div style="display: grid; grid-template-columns: 1fr 1fr; gap: var(--space-3); margin-top: var(--space-3);">
      <div class="card">
        <div class="card-header"><strong>Solid</strong></div>
        <div class="card-body" style="color: var(--color-text-muted); font-size: var(--text-sm);">Card base con header + body. Shadow-sm.</div>
      </div>
      <div class="card-glass">
        <div class="card-header"><strong>Glass</strong></div>
        <div class="card-body" style="color: var(--color-text-muted); font-size: var(--text-sm);">Backdrop-filter blur.</div>
      </div>
      <div class="card" data-state="success">
        <div class="card-body" style="font-size: var(--text-sm); color: var(--color-text-muted);">State: success</div>
      </div>
      <div class="card" data-state="danger">
        <div class="card-body" style="font-size: var(--text-sm); color: var(--color-text-muted);">State: danger</div>
      </div>
    </div>
  </section>
```

- [ ] **Step 5: Verify pass and commit**

```bash
python -m pytest -p no:postgresql tests/test_glass_foundation.py -v -k "card"
git add static/css/primitives.css templates/dev_primitives.html tests/test_glass_foundation.py
git commit -m "feat(css): add .card + variants (solid/glass/state-tinted/interactive)"
```

---

## Task 10: `.chip`

**Files:**
- Modify: `static/css/primitives.css`
- Modify: `templates/dev_primitives.html`
- Modify: `tests/test_glass_foundation.py`

- [ ] **Step 1: Write the failing tests**

Append:

```python
def test_chip_primitive_defined():
    css = _read_primitives()
    for sel in ['.chip', '.chip-primary', '.chip-success',
                '.chip-warning', '.chip-danger', '.chip-info']:
        assert sel in css, f"missing {sel}"


def test_dev_primitives_renders_all_chip_variants(logged_client):
    resp = logged_client.get('/dev/primitives')
    html = resp.data.decode('utf-8')
    for cls in ['chip', 'chip-primary', 'chip-success',
                'chip-warning', 'chip-danger', 'chip-info']:
        assert cls in html
```

- [ ] **Step 2: Verify failure**

```bash
python -m pytest -p no:postgresql tests/test_glass_foundation.py -v -k "chip"
```

- [ ] **Step 3: Append to `static/css/primitives.css`**

```css

/* ─── .chip ──────────────────────────────────────────────────────────── */
.chip {
  display: inline-flex;
  align-items: center;
  gap: var(--space-1);
  padding: var(--space-1) var(--space-3);
  font-size: var(--text-xs);
  font-weight: var(--weight-semibold);
  letter-spacing: 0.01em;
  border-radius: var(--radius-full);
  background: var(--color-surface-muted);
  color: var(--color-text-muted);
}
.chip-primary { background: var(--color-primary-soft); color: var(--color-primary-soft-fg); }
.chip-success { background: var(--color-success-soft); color: var(--color-success-soft-fg); }
.chip-warning { background: var(--color-warning-soft); color: var(--color-warning-soft-fg); }
.chip-danger  { background: var(--color-danger-soft);  color: var(--color-danger-soft-fg); }
.chip-info    { background: var(--color-info-soft);    color: var(--color-info-soft-fg); }
```

- [ ] **Step 4: Append showcase to `templates/dev_primitives.html`**

```html

  <section data-section="chip" style="margin-top: var(--space-8);">
    <h2 style="font-size: var(--text-lg); font-weight: var(--weight-bold);">.chip — Semantic chips</h2>
    <div style="display:flex; flex-wrap: wrap; gap: var(--space-2); margin-top: var(--space-3);">
      <span class="chip">Neutral</span>
      <span class="chip chip-primary">Primary</span>
      <span class="chip chip-success">Success</span>
      <span class="chip chip-warning">Warning</span>
      <span class="chip chip-danger">Danger</span>
      <span class="chip chip-info">Info</span>
    </div>
  </section>
```

- [ ] **Step 5: Verify pass and commit**

```bash
python -m pytest -p no:postgresql tests/test_glass_foundation.py -v -k "chip"
git add static/css/primitives.css templates/dev_primitives.html tests/test_glass_foundation.py
git commit -m "feat(css): add .chip primitive (6 semantic variants)"
```

---

## Task 11: `.badge`

**Files:**
- Modify: `static/css/primitives.css`
- Modify: `templates/dev_primitives.html`
- Modify: `tests/test_glass_foundation.py`

- [ ] **Step 1: Write the failing tests**

Append:

```python
def test_badge_primitive_defined():
    css = _read_primitives()
    assert '.badge' in css
    assert '.badge-dot' in css
    # Tabular nums for counts
    assert 'tabular-nums' in css


def test_dev_primitives_renders_badge_examples(logged_client):
    resp = logged_client.get('/dev/primitives')
    html = resp.data.decode('utf-8')
    assert 'class="badge"' in html
    assert 'badge-dot' in html
```

- [ ] **Step 2: Verify failure**

```bash
python -m pytest -p no:postgresql tests/test_glass_foundation.py -v -k "badge"
```

- [ ] **Step 3: Append to `static/css/primitives.css`**

```css

/* ─── .badge ─────────────────────────────────────────────────────────── */
.badge {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 18px;
  height: 18px;
  padding: 0 var(--space-1);
  font-size: var(--text-2xs);
  font-weight: var(--weight-bold);
  font-variant-numeric: tabular-nums;
  background: var(--color-danger);
  color: var(--color-danger-fg);
  border-radius: var(--radius-full);
  line-height: 1;
}
.badge-dot {
  min-width: 8px;
  width: 8px;
  height: 8px;
  padding: 0;
}
```

- [ ] **Step 4: Append showcase to `templates/dev_primitives.html`**

```html

  <section data-section="badge" style="margin-top: var(--space-8);">
    <h2 style="font-size: var(--text-lg); font-weight: var(--weight-bold);">.badge — Counters &amp; dots</h2>
    <div style="display:flex; flex-wrap: wrap; gap: var(--space-3); margin-top: var(--space-3); align-items: center;">
      <button class="btn">Pedidos <span class="badge" style="margin-left: 6px;">12</span></button>
      <button class="btn">Mensajes <span class="badge" style="margin-left: 6px;">99+</span></button>
      <span class="chip chip-success">
        <span class="badge badge-dot" style="background: var(--color-success);"></span>
        Online
      </span>
    </div>
  </section>
```

- [ ] **Step 5: Verify pass and commit**

```bash
python -m pytest -p no:postgresql tests/test_glass_foundation.py -v -k "badge"
git add static/css/primitives.css templates/dev_primitives.html tests/test_glass_foundation.py
git commit -m "feat(css): add .badge primitive (counter + dot)"
```

---

## Task 12: Surface helpers

**Files:**
- Modify: `static/css/primitives.css`
- Modify: `templates/dev_primitives.html`
- Modify: `tests/test_glass_foundation.py`

- [ ] **Step 1: Write the failing tests**

Append:

```python
def test_surface_helpers_defined():
    css = _read_primitives()
    for sel in ['.surface-solid', '.surface-glass', '.surface-sunken']:
        assert sel in css


def test_dev_primitives_renders_surfaces(logged_client):
    resp = logged_client.get('/dev/primitives')
    html = resp.data.decode('utf-8')
    for cls in ['surface-solid', 'surface-glass', 'surface-sunken']:
        assert cls in html
```

- [ ] **Step 2: Verify failure**

```bash
python -m pytest -p no:postgresql tests/test_glass_foundation.py -v -k "surface"
```

- [ ] **Step 3: Append to `static/css/primitives.css`**

```css

/* ─── Surfaces (reusable backgrounds) ────────────────────────────────── */
.surface-solid {
  background: var(--color-surface);
  border-radius: var(--radius-lg);
  border: 1px solid var(--color-border);
}
.surface-glass {
  background: var(--glass-bg);
  border-radius: var(--radius-xl);
  border: 1px solid var(--glass-border);
  backdrop-filter: var(--glass-blur);
  -webkit-backdrop-filter: var(--glass-blur);
}
.surface-sunken {
  background: var(--color-surface-sunken);
  border-radius: var(--radius-lg);
}
```

- [ ] **Step 4: Append showcase**

```html

  <section data-section="surface" style="margin-top: var(--space-8);">
    <h2 style="font-size: var(--text-lg); font-weight: var(--weight-bold);">Surfaces</h2>
    <div style="display: grid; grid-template-columns: 1fr 1fr 1fr; gap: var(--space-3); margin-top: var(--space-3);">
      <div class="surface-solid" style="padding: var(--space-4); text-align:center; font-size: var(--text-sm);">solid</div>
      <div class="surface-glass" style="padding: var(--space-4); text-align:center; font-size: var(--text-sm);">glass</div>
      <div class="surface-sunken" style="padding: var(--space-4); text-align:center; font-size: var(--text-sm);">sunken</div>
    </div>
  </section>
```

- [ ] **Step 5: Verify pass and commit**

```bash
python -m pytest -p no:postgresql tests/test_glass_foundation.py -v -k "surface"
git add static/css/primitives.css templates/dev_primitives.html tests/test_glass_foundation.py
git commit -m "feat(css): add surface helpers (solid/glass/sunken)"
```

---

## Task 13: Layout utilities (`.stack`, `.cluster`, `.grid-auto`)

**Files:**
- Modify: `static/css/primitives.css`
- Modify: `templates/dev_primitives.html`
- Modify: `tests/test_glass_foundation.py`

- [ ] **Step 1: Write the failing test**

Append:

```python
def test_layout_utilities_defined():
    css = _read_primitives()
    for sel in ['.stack', '.stack-1', '.stack-4', '.cluster',
                '.cluster-2', '.grid-auto']:
        assert sel in css
```

- [ ] **Step 2: Verify failure**

```bash
python -m pytest -p no:postgresql tests/test_glass_foundation.py -v -k "layout_utilities"
```

- [ ] **Step 3: Append to `static/css/primitives.css`**

```css

/* ─── Layout utilities ────────────────────────────────────────────────── */
.stack { display: flex; flex-direction: column; }
.stack-1 > * + * { margin-top: var(--space-1); }
.stack-2 > * + * { margin-top: var(--space-2); }
.stack-3 > * + * { margin-top: var(--space-3); }
.stack-4 > * + * { margin-top: var(--space-4); }
.stack-6 > * + * { margin-top: var(--space-6); }

.cluster { display: flex; flex-wrap: wrap; }
.cluster-1 { gap: var(--space-1); }
.cluster-2 { gap: var(--space-2); }
.cluster-3 { gap: var(--space-3); }
.cluster-4 { gap: var(--space-4); }

.grid-auto {
  display: grid;
  gap: var(--space-4);
  grid-template-columns: repeat(auto-fit, minmax(var(--grid-min, 240px), 1fr));
}
```

- [ ] **Step 4: Append showcase**

```html

  <section data-section="layout" style="margin-top: var(--space-8);">
    <h2 style="font-size: var(--text-lg); font-weight: var(--weight-bold);">Layout utilities</h2>
    <h3 style="font-size: var(--text-sm); color: var(--color-text-muted); margin-top: var(--space-3);">.stack-3 (vertical gap 12px)</h3>
    <div class="stack stack-3" style="margin-top: var(--space-2);">
      <div class="surface-solid" style="padding: var(--space-3); font-size: var(--text-sm);">Row 1</div>
      <div class="surface-solid" style="padding: var(--space-3); font-size: var(--text-sm);">Row 2</div>
      <div class="surface-solid" style="padding: var(--space-3); font-size: var(--text-sm);">Row 3</div>
    </div>
    <h3 style="font-size: var(--text-sm); color: var(--color-text-muted); margin-top: var(--space-4);">.cluster-2 (wrap chips)</h3>
    <div class="cluster cluster-2" style="margin-top: var(--space-2);">
      <span class="chip chip-primary">A</span><span class="chip chip-success">B</span>
      <span class="chip chip-warning">C</span><span class="chip chip-danger">D</span>
      <span class="chip chip-info">E</span><span class="chip">F</span>
    </div>
    <h3 style="font-size: var(--text-sm); color: var(--color-text-muted); margin-top: var(--space-4);">.grid-auto (responsive)</h3>
    <div class="grid-auto" style="--grid-min: 140px; margin-top: var(--space-2);">
      <div class="surface-solid" style="padding: var(--space-4); text-align:center;">1</div>
      <div class="surface-solid" style="padding: var(--space-4); text-align:center;">2</div>
      <div class="surface-solid" style="padding: var(--space-4); text-align:center;">3</div>
      <div class="surface-solid" style="padding: var(--space-4); text-align:center;">4</div>
    </div>
  </section>
```

- [ ] **Step 5: Verify pass and commit**

```bash
python -m pytest -p no:postgresql tests/test_glass_foundation.py -v -k "layout_utilities"
git add static/css/primitives.css templates/dev_primitives.html tests/test_glass_foundation.py
git commit -m "feat(css): add layout utilities (.stack, .cluster, .grid-auto)"
```

---

## Task 14: Skeleton loaders

**Files:**
- Modify: `static/css/primitives.css`
- Modify: `templates/dev_primitives.html`
- Modify: `tests/test_glass_foundation.py`

- [ ] **Step 1: Write the failing test**

Append:

```python
def test_skeleton_primitive_defined():
    css = _read_primitives()
    assert '.skeleton' in css
    assert '.skeleton-text' in css
    assert '.skeleton-title' in css
    assert '.skeleton-tile' in css
    assert '@keyframes' in css and 'skeleton' in css  # shimmer keyframe
```

- [ ] **Step 2: Verify failure**

```bash
python -m pytest -p no:postgresql tests/test_glass_foundation.py -v -k "skeleton"
```

- [ ] **Step 3: Append to `static/css/primitives.css`**

```css

/* ─── Skeleton loaders ────────────────────────────────────────────────── */
.skeleton {
  background: linear-gradient(
    90deg,
    var(--color-surface-muted) 0%,
    var(--color-surface)       50%,
    var(--color-surface-muted) 100%
  );
  background-size: 200% 100%;
  animation: skeleton-shimmer 1.6s var(--ease-in-out-quart) infinite;
  border-radius: var(--radius-sm);
  color: transparent;
  pointer-events: none;
  user-select: none;
}
@keyframes skeleton-shimmer {
  0%   { background-position: 200% 0; }
  100% { background-position: -200% 0; }
}
.skeleton-text  { height: 1em; margin-bottom: 6px; }
.skeleton-title { height: 1.5em; width: 60%; margin-bottom: 10px; }
.skeleton-tile  { min-height: 130px; border-radius: var(--radius-xl); }
```

- [ ] **Step 4: Append showcase**

```html

  <section data-section="skeleton" style="margin-top: var(--space-8);">
    <h2 style="font-size: var(--text-lg); font-weight: var(--weight-bold);">Skeleton loaders</h2>
    <div class="card" style="margin-top: var(--space-3);">
      <div class="card-body">
        <div class="skeleton skeleton-title"></div>
        <div class="skeleton skeleton-text"></div>
        <div class="skeleton skeleton-text" style="width: 85%;"></div>
        <div class="skeleton skeleton-text" style="width: 50%;"></div>
      </div>
    </div>
    <div class="skeleton skeleton-tile" style="margin-top: var(--space-3);"></div>
  </section>
```

- [ ] **Step 5: Verify pass and commit**

```bash
python -m pytest -p no:postgresql tests/test_glass_foundation.py -v -k "skeleton"
git add static/css/primitives.css templates/dev_primitives.html tests/test_glass_foundation.py
git commit -m "feat(css): add .skeleton loaders (text/title/tile)"
```

---

## Task 15: Ring state primitive

**Files:**
- Modify: `static/css/primitives.css`
- Modify: `templates/dev_primitives.html`
- Modify: `tests/test_glass_foundation.py`

- [ ] **Step 1: Write the failing test**

Append:

```python
def test_ring_primitive_defined():
    css = _read_primitives()
    assert '.ring' in css
    assert '.ring-bg' in css
    assert '.ring-fg' in css
    assert '.ring[data-state="success"]' in css
    assert '.ring[data-state="warning"]' in css
    assert '.ring[data-state="danger"]' in css
    # Uses --ring-color variable internally
    assert 'var(--ring-color)' in css


def test_dev_primitives_renders_ring_states(logged_client):
    resp = logged_client.get('/dev/primitives')
    html = resp.data.decode('utf-8')
    assert 'class="ring"' in html
    # At least one of each state shown
    assert 'data-state="success"' in html or 'data-state=\'success\'' in html
```

- [ ] **Step 2: Verify failure**

```bash
python -m pytest -p no:postgresql tests/test_glass_foundation.py -v -k "ring"
```

- [ ] **Step 3: Append to `static/css/primitives.css`**

```css

/* ─── Ring state primitive (KPI progress rings) ──────────────────────── */
.ring {
  --ring-color: var(--color-primary);
  display: inline-block;
  width: 36px;
  height: 36px;
}
.ring-bg {
  fill: none;
  stroke: var(--glass-border);
  stroke-width: 4;
  opacity: 0.5;
}
.ring-fg {
  fill: none;
  stroke: var(--ring-color);
  stroke-width: 4;
  stroke-linecap: round;
  transform: rotate(-90deg);
  transform-origin: 50% 50%;
  transition:
    stroke var(--duration-slow) var(--ease-out-quart),
    stroke-dashoffset var(--duration-slower) var(--ease-out-quart);
}
.ring-text {
  fill: var(--ring-color);
  font-size: var(--text-2xs);
  font-weight: var(--weight-bold);
  text-anchor: middle;
  font-variant-numeric: tabular-nums;
}

.ring[data-state="success"] { --ring-color: var(--color-success); }
.ring[data-state="warning"] { --ring-color: var(--color-warning); }
.ring[data-state="danger"]  { --ring-color: var(--color-danger); }
.ring[data-state="neutral"] { --ring-color: var(--color-primary); }
```

- [ ] **Step 4: Append showcase (SVG rings at 90/78/55%)**

```html

  <section data-section="ring" style="margin-top: var(--space-8);">
    <h2 style="font-size: var(--text-lg); font-weight: var(--weight-bold);">Ring state (KPI progress)</h2>
    <div style="display:flex; gap: var(--space-4); margin-top: var(--space-3); align-items: center;">
      <!-- 90% success -->
      <svg class="ring" data-state="success" viewBox="0 0 36 36">
        <circle class="ring-bg" cx="18" cy="18" r="15"></circle>
        <circle class="ring-fg" cx="18" cy="18" r="15"
                style="stroke-dasharray: 94.25; stroke-dashoffset: 9.4;"></circle>
        <text class="ring-text" x="18" y="22">90%</text>
      </svg>
      <!-- 78% warning -->
      <svg class="ring" data-state="warning" viewBox="0 0 36 36">
        <circle class="ring-bg" cx="18" cy="18" r="15"></circle>
        <circle class="ring-fg" cx="18" cy="18" r="15"
                style="stroke-dasharray: 94.25; stroke-dashoffset: 20.7;"></circle>
        <text class="ring-text" x="18" y="22">78%</text>
      </svg>
      <!-- 55% danger -->
      <svg class="ring" data-state="danger" viewBox="0 0 36 36">
        <circle class="ring-bg" cx="18" cy="18" r="15"></circle>
        <circle class="ring-fg" cx="18" cy="18" r="15"
                style="stroke-dasharray: 94.25; stroke-dashoffset: 42.4;"></circle>
        <text class="ring-text" x="18" y="22">55%</text>
      </svg>
      <!-- 100% neutral (default primary) -->
      <svg class="ring" data-state="neutral" viewBox="0 0 36 36">
        <circle class="ring-bg" cx="18" cy="18" r="15"></circle>
        <circle class="ring-fg" cx="18" cy="18" r="15"
                style="stroke-dasharray: 94.25; stroke-dashoffset: 0;"></circle>
        <text class="ring-text" x="18" y="22">100</text>
      </svg>
    </div>
  </section>
```

- [ ] **Step 5: Verify pass and commit**

```bash
python -m pytest -p no:postgresql tests/test_glass_foundation.py -v -k "ring"
git add static/css/primitives.css templates/dev_primitives.html tests/test_glass_foundation.py
git commit -m "feat(css): add ring state primitive (progress + semantic color)"
```

---

## Task 16: Typography utility classes

**Files:**
- Modify: `static/css/primitives.css`
- Modify: `templates/dev_primitives.html`
- Modify: `tests/test_glass_foundation.py`

- [ ] **Step 1: Write the failing test**

Append:

```python
def test_typography_utilities_defined():
    css = _read_primitives()
    for sel in ['.text-xs', '.text-sm', '.text-base', '.text-lg', '.text-xl',
                '.font-medium', '.font-semibold', '.font-bold',
                '.text-muted', '.text-subtle', '.text-primary',
                '.label', '.tabular']:
        assert sel in css, f"missing {sel}"
```

- [ ] **Step 2: Verify failure**

```bash
python -m pytest -p no:postgresql tests/test_glass_foundation.py -v -k "typography_utilities"
```

- [ ] **Step 3: Append to `static/css/primitives.css`**

```css

/* ─── Typography utilities ───────────────────────────────────────────── */
.text-2xs { font-size: var(--text-2xs); }
.text-xs  { font-size: var(--text-xs); }
.text-sm  { font-size: var(--text-sm); }
.text-base{ font-size: var(--text-base); }
.text-md  { font-size: var(--text-md); }
.text-lg  { font-size: var(--text-lg); }
.text-xl  { font-size: var(--text-xl); }
.text-2xl { font-size: var(--text-2xl); }

.font-regular  { font-weight: var(--weight-regular); }
.font-medium   { font-weight: var(--weight-medium); }
.font-semibold { font-weight: var(--weight-semibold); }
.font-bold     { font-weight: var(--weight-bold); }

.text-muted   { color: var(--color-text-muted); }
.text-subtle  { color: var(--color-text-subtle); }
.text-primary { color: var(--color-primary); }
.text-danger  { color: var(--color-danger); }
.text-success { color: var(--color-success); }

.tracking-tight  { letter-spacing: var(--tracking-tight); }
.tracking-widest { letter-spacing: var(--tracking-widest); }

/* Common combined patterns */
.label {
  font-size: var(--text-xs);
  font-weight: var(--weight-semibold);
  letter-spacing: var(--tracking-widest);
  text-transform: uppercase;
  color: var(--color-text-muted);
}
.tabular,
.num,
.kpi-value {
  font-variant-numeric: tabular-nums lining-nums;
  font-feature-settings: "tnum", "lnum";
}
```

- [ ] **Step 4: Append showcase**

```html

  <section data-section="typography" style="margin-top: var(--space-8);">
    <h2 style="font-size: var(--text-lg); font-weight: var(--weight-bold);">Typography utilities</h2>
    <div class="surface-solid" style="padding: var(--space-5); margin-top: var(--space-3);">
      <div class="label">Label uppercase</div>
      <div class="text-xl font-bold tracking-tight">Título 24 px bold tight</div>
      <div class="text-sm text-muted" style="margin-top: 6px;">Body muted 13 px</div>
      <div class="text-xs text-subtle" style="margin-top: 4px;">Subtle 11 px</div>
      <div class="text-2xl font-bold tabular tracking-tight" style="margin-top: var(--space-3);">62,483.02</div>
      <div class="text-xs text-subtle">(tabular-nums aligned)</div>
    </div>
  </section>
```

- [ ] **Step 5: Verify pass and commit**

```bash
python -m pytest -p no:postgresql tests/test_glass_foundation.py -v -k "typography_utilities"
git add static/css/primitives.css templates/dev_primitives.html tests/test_glass_foundation.py
git commit -m "feat(css): add typography utility classes (.text-*, .font-*, .label, .tabular)"
```

---

## Task 17: Bundle size assertion + final file verification

**Files:**
- Modify: `tests/test_glass_foundation.py`

- [ ] **Step 1: Write the failing test**

Append:

```python
def test_bundle_size_under_budget():
    """tokens.css + primitives.css combined must be under 20 KB uncompressed
    (spec §11 success criterion 8)."""
    tokens_size = TOKENS_CSS.stat().st_size
    primitives_size = PRIMITIVES_CSS.stat().st_size
    combined_kb = (tokens_size + primitives_size) / 1024
    assert combined_kb <= 20, (
        f"Bundle exceeds 20 KB: tokens={tokens_size/1024:.1f} KB + "
        f"primitives={primitives_size/1024:.1f} KB = {combined_kb:.1f} KB"
    )
```

- [ ] **Step 2: Run it**

```bash
python -m pytest -p no:postgresql tests/test_glass_foundation.py::test_bundle_size_under_budget -v
```

Expected: PASS (should be ~8-12 KB combined). If it fails, investigate — likely means something duplicated or excessive comments.

- [ ] **Step 3: Commit**

```bash
git add tests/test_glass_foundation.py
git commit -m "test(css): assert combined bundle stays under 20 KB budget"
```

---

## Task 18: Final verification + merge to main

**Files:**
- No code changes. Verification + manual checks + merge.

- [ ] **Step 1: Run the full test suite on the feature branch**

```bash
source .venv311/bin/activate && python -m pytest -p no:postgresql tests/ 2>&1 | tail -3
```

Expected: All tests pass. Baseline was 133; the exact final count depends on how many test functions the executor actually produced (one per primitive added) — expect roughly 133 + 20+.

- [ ] **Step 2: Manually verify the demo page renders without errors**

Start the dev server, log in as super_admin, visit `/dev/primitives`:

```bash
FLASK_ENV=development python app.py
```

In browser, visit `http://localhost:5000/dev/primitives` and confirm:
- [ ] Page renders without Jinja/CSS errors.
- [ ] All 10 sections visible (btn, input, card, chip, badge, surface, layout, skeleton, ring, typography).
- [ ] Every button/input/card looks correct.

- [ ] **Step 3: Manually verify dark mode works**

With the dev server still running, toggle macOS between Light and Dark (System Settings → Appearance). The `/dev/primitives` page should update immediately. Verify:
- [ ] Background ambient gradient shifts from light-indigo to dark-indigo.
- [ ] Text becomes light on dark surface.
- [ ] Glass surfaces become translucent dark.
- [ ] Chips and focus rings still have sufficient contrast.

- [ ] **Step 4: Manually verify no visual regression on existing pages**

With the dev server running, visit each of:
- `/dashboard` — dashboard layout identical to before Phase 1.
- `/pedidos` (or the operational page) — identical to before.
- `/login` — identical.

Nothing should look different. The new tokens/primitives are loaded but no existing class uses them yet.

- [ ] **Step 5: Verify on iPhone (optional but spec-requested)**

- Get the Mac's LAN IP (e.g., `ipconfig getifaddr en0`).
- On iPhone (same Wi-Fi): `http://<mac-ip>:5000/dev/primitives`.
- Verify glass blur renders, touch targets feel right, no iOS zoom on inputs when focused.
- Toggle iPhone between Light and Dark mode in Control Center and confirm the page follows.

- [ ] **Step 6: Push feature branch and open PR**

```bash
git push -u origin feat/glass-foundation
gh pr create --title "Phase 1: Glass Foundation — design tokens + primitives" --body "$(cat <<'EOF'
## Summary
- New `static/css/tokens.css`: design tokens (color L1+L2 light+dark, typography, spacing, radii, shadows, motion, z-index, blur, reduced-motion).
- New `static/css/primitives.css`: primitive components (.btn, .input, .card, .chip, .badge, surfaces, layout utilities, skeleton, ring states, typography utilities).
- New `/dev/primitives` admin-only showcase route (living reference for future phases).
- Both CSS files loaded before the legacy stylesheets in `base.html`. Zero regression on existing pages.

Spec: `docs/superpowers/specs/2026-04-17-glass-foundation-design.md`
Plan: `docs/superpowers/plans/2026-04-17-glass-foundation.md`

## Test plan
- [x] All existing tests pass (baseline 133).
- [x] New foundation tests pass.
- [x] Bundle size ≤ 20 KB combined.
- [x] `/dev/primitives` renders in both light and dark mode (verified on macOS).
- [x] No visual regression on `/dashboard`, `/pedidos`, `/login`.
- [ ] iPhone verification: glass blur, no input zoom, dark mode auto-switch.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

- [ ] **Step 7: After PR review, merge to main (auto-deploys to Heroku)**

The user will merge via GitHub UI or CLI. Deploy will be verified with:

```bash
heroku releases --app pesosapp -n 1
# Then visit the live /dev/primitives page
```

---

## Dependency map (task ordering)

```
T1 scaffolding
 └─ T2 color tokens
     └─ T3 typography tokens
         └─ T4 structural tokens (spacing/radii/shadows/motion/z/blur)
             └─ T5 reduced-motion
                 └─ T6 /dev/primitives route
                     ├─ T7 .btn
                     ├─ T8 .input
                     ├─ T9 .card
                     ├─ T10 .chip
                     ├─ T11 .badge
                     ├─ T12 surfaces
                     ├─ T13 layout utilities
                     ├─ T14 skeleton
                     ├─ T15 ring states
                     └─ T16 typography utilities
                         └─ T17 bundle size assertion
                             └─ T18 final verification + merge
```

T7-T16 are **independent of each other** — each only depends on T1-T6. They can be executed in any order, sequentially or in parallel (via `subagent-driven-development`).

---

## Spec-to-plan coverage table

| Spec section | Implementing task(s) |
|---|---|
| §2 In scope — tokens.css | T1, T2, T3, T4, T5 |
| §2 In scope — primitives.css | T1, T7-T16 |
| §2 In scope — base.html wiring | T1 |
| §2 In scope — light/dark auto | T2 (+ dark overrides in T4) |
| §5 Token architecture (two-layer) | T2 (enforces via `var(--indigo-*)` references) |
| §6 Color system (full values) | T2 |
| §7 Typography | T3 (tokens) + T16 (utilities) |
| §8 Spacing/radii/shadows/motion/z/blur | T4 |
| §8 Reduced motion | T5 |
| §9 .btn | T7 |
| §9 .input + .field | T8 |
| §9 .card (+ variants) | T9 |
| §9 .chip | T10 |
| §9 .badge | T11 |
| §9 Surfaces | T12 |
| §9 Layout utilities | T13 |
| §9 Skeleton | T14 |
| §9 Ring state pattern | T15 |
| §11 Success criterion 1 (files exist) | T1 (verified by test) |
| §11 Success criterion 2 (load order) | T1 (verified by test) |
| §11 Success criterion 3 (no regression) | T18 manual |
| §11 Success criterion 4 (dark mode auto) | T2 + T18 manual |
| §11 Success criterion 5 (/dev/primitives) | T6-T16 |
| §11 Success criterion 6 (test suite passes) | T18 |
| §11 Success criterion 7 (WCAG contrast) | T18 manual (token values pre-verified in spec §6) |
| §11 Success criterion 8 (bundle ≤ 20 KB) | T17 |
