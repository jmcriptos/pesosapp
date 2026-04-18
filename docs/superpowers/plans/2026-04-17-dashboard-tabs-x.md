# Dashboard Tabs X-style + Glass Refresh — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the dashboard's carousel (dots + arrow buttons) with Twitter/X-style horizontal tabs featuring an animated underline indicator, and apply Phase 1 glass tokens + primitives to every element in the 4 existing panels.

**Architecture:** Add a new `.dash-tabs` primitive to `static/css/primitives.css` and a vanilla JS controller `static/js/dashboard-tabs.js` (~80 LOC). Replace the `dashboard-subnav-wrap` block in `templates/dashboard.html` with the new nav. Swap per-panel classes in the same template from `.kpi-tile` / `.progress-ring` / `.c-green` etc. to `.card.card-glass` / `.ring[data-state]` / `.chip-success`. Every color and sizing value resolves through the Phase 1 tokens so dark mode is automatic.

**Tech Stack:** Plain CSS (tokens-driven), vanilla JavaScript, Flask + Jinja2 template, pytest + Flask test client for integration tests.

**Branch strategy:** Work on `feat/dashboard-tabs-x`, branching **from `feat/glass-foundation`** (Phase 1 PR #23). When Phase 1 merges to main, rebase Phase 3 onto main. Every task's commit leaves the dashboard in a working state; merge happens after Task 11.

---

## File Structure

### Created

| File | Responsibility |
|---|---|
| `static/js/dashboard-tabs.js` | `DashboardTabs` class: activate panel, animate indicator, handle swipe gesture, handle keyboard ←/→. Self-initializes on pages that have `[data-dashboard-tabs]` in DOM. |
| `tests/test_dashboard_redesign.py` | Flask integration tests that fetch `/dashboard` and assert the new nav markup, the new primitive classes in each panel, the ambient background, and the inline carousel JS has been removed. |

### Modified

| File | Change |
|---|---|
| `templates/dashboard.html` | (a) Replace lines 60-91 (`.dashboard-subnav-wrap`) with the new `<nav class="dash-tabs">`. (b) Add `data-dashboard-tabs` attribute on the panel container. (c) Apply `style="background: var(--bg-ambient);"` to the outer `.exec-dashboard` div. (d) Swap panel-internal classes (`.kpi-tile` → `.card.card-glass`, `.tile-label` → `.label`, etc.) per §5 of the spec. (e) Remove the inline carousel JS block near line 1598. |
| `templates/base.html` | Add a single `<script defer src="{{ url_for('static', filename='js/dashboard-tabs.js') }}"></script>` tag near the existing JS loads. |
| `static/css/primitives.css` | Append `.dash-tabs`, `.dash-tab`, `.dash-tabs-indicator` blocks. |

### Untouched

- `app.py` (no route or backend change)
- `static/styles.css`, `static/dashboard_pro.css` (carousel rules become orphaned — cleanup deferred to Phase 5)
- All other templates
- Any test file other than the new `tests/test_dashboard_redesign.py`

---

## Task 1: Scaffolding — branch, empty JS file, script tag, test scaffold

**Files:**
- Create: `static/js/dashboard-tabs.js` (empty shell, header comment only)
- Modify: `templates/base.html` (add `<script defer>` tag)
- Create: `tests/test_dashboard_redesign.py` (Flask fixtures + scaffold test)

- [ ] **Step 1: Create feature branch from feat/glass-foundation**

```bash
git checkout feat/glass-foundation
git checkout -b feat/dashboard-tabs-x
```

- [ ] **Step 2: Write the failing test (scaffold)**

Create `tests/test_dashboard_redesign.py`:

```python
# tests/test_dashboard_redesign.py
"""Tests for Phase 3: Dashboard tabs X-style + glass refresh."""
import os
from pathlib import Path
import pytest

os.environ.setdefault('SECRET_KEY', 'test-secret')
os.environ.setdefault('FLASK_ENV', 'testing')
os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')

from app import app as flask_app, db as _db

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DASHBOARD_TABS_JS = PROJECT_ROOT / 'static' / 'js' / 'dashboard-tabs.js'
PRIMITIVES_CSS = PROJECT_ROOT / 'static' / 'css' / 'primitives.css'
DASHBOARD_HTML = PROJECT_ROOT / 'templates' / 'dashboard.html'
BASE_HTML = PROJECT_ROOT / 'templates' / 'base.html'


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


# ─── Scaffolding ────────────────────────────────────────────────────────

def test_dashboard_tabs_js_exists():
    assert DASHBOARD_TABS_JS.exists(), f"Expected {DASHBOARD_TABS_JS} to exist"


def test_base_html_loads_dashboard_tabs_js():
    html = BASE_HTML.read_text(encoding='utf-8')
    assert 'js/dashboard-tabs.js' in html, "dashboard-tabs.js <script> not found in base.html"
```

- [ ] **Step 3: Run the tests to verify they fail**

```bash
source .venv311/bin/activate && python -m pytest -p no:postgresql tests/test_dashboard_redesign.py -v
```

Expected: 2 tests FAIL (file doesn't exist, script tag missing).

- [ ] **Step 4: Create `static/js/dashboard-tabs.js` (empty shell)**

```javascript
/* =============================================================================
   PesosApp · Dashboard Tabs X-style controller · Phase 3
   See docs/superpowers/specs/2026-04-17-dashboard-tabs-x-design.md
   ============================================================================= */
```

- [ ] **Step 5: Add `<script>` tag to `templates/base.html`**

Search for the existing `<script>` tags (e.g., the one that loads `scripts.min.js`). Insert the new tag right after the last stylesheet link and before any existing script tags. Using the Edit tool, find a unique anchor near the end of the `<head>` section (e.g., the CSRF token meta). Add after the closing `</style>` block that exists after the flash stacks, or immediately before the closing `</head>` tag, the following:

```html
<script defer src="{{ url_for('static', filename='js/dashboard-tabs.js') }}"></script>
```

To find the exact insertion point reliably, grep first:

```bash
grep -n "scripts.min.js\|</head>" templates/base.html | head -5
```

If `scripts.min.js` is loaded in `<head>`, add the new `<script defer>` right after its line. If `scripts.min.js` is near `</body>`, add the new `<script defer>` right after its line. `defer` makes the order safe either way.

- [ ] **Step 6: Run tests to verify they pass**

```bash
python -m pytest -p no:postgresql tests/test_dashboard_redesign.py -v
```

Expected: 2 PASS.

- [ ] **Step 7: Run full test suite — no regressions**

```bash
python -m pytest -p no:postgresql tests/ 2>&1 | tail -3
```

Expected: 163 + 2 = 165 passed.

- [ ] **Step 8: Commit**

```bash
git add static/js/dashboard-tabs.js templates/base.html tests/test_dashboard_redesign.py
git commit -m "$(cat <<'EOF'
feat(dashboard): scaffold Phase 3 — empty JS controller + script tag + test

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: `.dash-tabs` primitive in primitives.css

**Files:**
- Modify: `static/css/primitives.css` (append `.dash-tabs` block)
- Modify: `tests/test_dashboard_redesign.py` (CSS presence test)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_dashboard_redesign.py`:

```python
def test_dash_tabs_primitive_defined():
    css = PRIMITIVES_CSS.read_text(encoding='utf-8')
    assert '.dash-tabs' in css
    assert '.dash-tab' in css
    assert '.dash-tabs-indicator' in css
    # Uses semantic tokens
    assert 'var(--color-primary)' in css
    assert 'var(--glass-bg-strong)' in css or 'var(--glass-bg)' in css
    # Sticky positioning
    assert 'position: sticky' in css or 'position:sticky' in css
    # Indicator animation uses spring easing
    assert 'var(--ease-spring)' in css
```

- [ ] **Step 2: Run test to verify failure**

```bash
python -m pytest -p no:postgresql tests/test_dashboard_redesign.py::test_dash_tabs_primitive_defined -v
```

Expected: FAIL.

- [ ] **Step 3: Append to `static/css/primitives.css`**

```css

/* ─── .dash-tabs — X/Twitter-style horizontal tab bar ─────────────────── */
.dash-tabs {
  position: sticky;
  top: 0;
  z-index: var(--z-sticky);
  display: flex;
  gap: var(--space-4);
  padding: var(--space-3) var(--space-4);
  background: var(--glass-bg-strong);
  backdrop-filter: var(--glass-blur);
  -webkit-backdrop-filter: var(--glass-blur);
  border-bottom: 1px solid var(--color-border-subtle);
  overflow-x: auto;
  overflow-y: hidden;
  scrollbar-width: none;
  scroll-snap-type: x mandatory;
  -webkit-overflow-scrolling: touch;
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
  flex: 0 0 auto;
}
.dash-tab:hover { color: var(--color-text); }
.dash-tab.is-active { color: var(--color-primary); }
.dash-tab:focus-visible {
  outline: none;
  box-shadow: var(--focus-ring);
  border-radius: var(--radius-sm);
}

.dash-tabs-indicator {
  position: absolute;
  bottom: 0;
  left: 0;
  height: 2px;
  width: 0;
  background: var(--color-primary);
  border-radius: var(--radius-full) var(--radius-full) 0 0;
  transition:
    transform var(--duration-base) var(--ease-spring),
    width var(--duration-base) var(--ease-spring);
  pointer-events: none;
  will-change: transform, width;
}
```

- [ ] **Step 4: Run test to verify pass**

```bash
python -m pytest -p no:postgresql tests/test_dashboard_redesign.py::test_dash_tabs_primitive_defined -v
```

- [ ] **Step 5: Commit**

```bash
git add static/css/primitives.css tests/test_dashboard_redesign.py
git commit -m "feat(dashboard): add .dash-tabs primitive (X-style horizontal tabs)"
```

---

## Task 3: `DashboardTabs` JS controller — core (activate + indicator)

**Files:**
- Modify: `static/js/dashboard-tabs.js` (implement core class)
- Modify: `tests/test_dashboard_redesign.py` (presence test for class)

- [ ] **Step 1: Write the failing test**

Append:

```python
def test_dashboard_tabs_js_has_class_and_init():
    js = DASHBOARD_TABS_JS.read_text(encoding='utf-8')
    assert 'class DashboardTabs' in js
    assert 'activate' in js
    # Must look for the root selector
    assert 'data-dashboard-tabs' in js
    # Must update the indicator
    assert 'dash-tabs-indicator' in js
    # Self-init on DOMContentLoaded
    assert 'DOMContentLoaded' in js
```

- [ ] **Step 2: Run test to verify failure**

```bash
python -m pytest -p no:postgresql tests/test_dashboard_redesign.py::test_dashboard_tabs_js_has_class_and_init -v
```

- [ ] **Step 3: Replace contents of `static/js/dashboard-tabs.js`**

```javascript
/* =============================================================================
   PesosApp · Dashboard Tabs X-style controller · Phase 3
   See docs/superpowers/specs/2026-04-17-dashboard-tabs-x-design.md
   ============================================================================= */
(function () {
  'use strict';

  class DashboardTabs {
    constructor(root) {
      this.root = root;
      this.tabBar = root.querySelector('.dash-tabs');
      this.indicator = root.querySelector('.dash-tabs-indicator');
      this.tabs = Array.from(root.querySelectorAll('.dash-tab'));
      this.panels = Array.from(root.querySelectorAll('.tab-panel'));

      if (!this.tabBar || !this.indicator || this.tabs.length === 0) return;

      this.activeIndex = Math.max(0, this.tabs.findIndex(t => t.classList.contains('is-active')));
      this._bindClicks();
      window.addEventListener('resize', () => this._updateIndicator(), { passive: true });

      // Defer initial indicator position to next frame so fonts/layout have settled.
      requestAnimationFrame(() => this._updateIndicator());
    }

    activate(index) {
      if (index < 0 || index >= this.tabs.length || index === this.activeIndex) return this;
      this.activeIndex = index;

      this.tabs.forEach((t, i) => {
        const active = i === index;
        t.classList.toggle('is-active', active);
        t.setAttribute('aria-selected', active ? 'true' : 'false');
      });

      this.panels.forEach((p, i) => {
        const active = i === index;
        p.classList.toggle('active', active);
        p.setAttribute('aria-hidden', active ? 'false' : 'true');
      });

      this._updateIndicator();
      return this;
    }

    _bindClicks() {
      this.tabs.forEach((tab, i) => {
        tab.addEventListener('click', (e) => {
          e.preventDefault();
          this.activate(i);
        });
      });
    }

    _updateIndicator() {
      const tab = this.tabs[this.activeIndex];
      if (!tab || !this.indicator) return;
      const barRect = this.tabBar.getBoundingClientRect();
      const tabRect = tab.getBoundingClientRect();
      const left = tabRect.left - barRect.left + this.tabBar.scrollLeft;
      this.indicator.style.width = tabRect.width + 'px';
      this.indicator.style.transform = 'translateX(' + left + 'px)';
    }
  }

  document.addEventListener('DOMContentLoaded', () => {
    const root = document.querySelector('[data-dashboard-tabs]');
    if (!root) return;
    window.__dashboardTabs = new DashboardTabs(root);
  });
})();
```

- [ ] **Step 4: Run test to verify pass**

```bash
python -m pytest -p no:postgresql tests/test_dashboard_redesign.py::test_dashboard_tabs_js_has_class_and_init -v
```

- [ ] **Step 5: Commit**

```bash
git add static/js/dashboard-tabs.js tests/test_dashboard_redesign.py
git commit -m "feat(dashboard): DashboardTabs JS controller with indicator animation"
```

---

## Task 4: Template nav swap — carousel → X-tabs + remove inline carousel JS

**Files:**
- Modify: `templates/dashboard.html` (replace `.dashboard-subnav-wrap` block + remove inline carousel JS)
- Modify: `tests/test_dashboard_redesign.py` (integration tests)

- [ ] **Step 1: Write the failing tests**

Append:

```python
def test_dashboard_renders_new_tab_bar(logged_client):
    resp = logged_client.get('/dashboard')
    assert resp.status_code == 200
    html = resp.data.decode('utf-8')
    # New nav markup present
    assert 'class="dash-tabs"' in html or "class='dash-tabs'" in html
    assert 'data-dashboard-tabs' in html
    assert 'class="dash-tabs-indicator"' in html or "class='dash-tabs-indicator'" in html
    # 4 tabs with expected labels
    for label in ['Ventas', 'Servicio', 'Top', 'Pedidos']:
        assert '>' + label + '<' in html, f"Tab label {label!r} not found"


def test_dashboard_no_longer_has_carousel_markup(logged_client):
    resp = logged_client.get('/dashboard')
    html = resp.data.decode('utf-8')
    # Old carousel controls are gone
    assert 'dashboard-carousel-dot' not in html
    assert 'dashboardPrev' not in html
    assert 'dashboardNext' not in html
    assert 'dashboardCarouselDots' not in html
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
python -m pytest -p no:postgresql tests/test_dashboard_redesign.py -v -k "tab_bar or carousel_markup"
```

Expected: 2 FAIL.

- [ ] **Step 3: Replace the carousel nav block in `templates/dashboard.html`**

Using the Edit tool, replace **lines 60-91** (the entire `<div class="exec-dashboard">` opening through the closing `</div>` of `dashboard-subnav-wrap`) with the new tabs markup. Since editing by line numbers is fragile, use Edit with this exact old/new string pair:

**old_string:**

```html
<div class="exec-dashboard">
    <div class="dashboard-subnav-wrap">
        <div class="dashboard-subnav">
            <div class="dashboard-carousel-head">
                <div class="dashboard-carousel-copy">
                    <span class="dashboard-carousel-kicker">Dashboard</span>
                    <div class="dashboard-carousel-title-row">
                        <span class="dashboard-carousel-title" id="dashboardSectionLabel">Ventas</span>
                        <span class="dashboard-carousel-counter" id="dashboardSectionCounter">1 / 4</span>
                    </div>
                </div>

                <div class="dashboard-carousel-controls">
                    <div class="dashboard-carousel-dots" id="dashboardCarouselDots" aria-label="Páginas del dashboard">
                        <button class="dashboard-carousel-dot active" type="button" data-panel-target="tendencia" aria-label="Ir a Ventas" aria-pressed="true"></button>
                        <button class="dashboard-carousel-dot" type="button" data-panel-target="servicio" aria-label="Ir a Servicio" aria-pressed="false"></button>
                        <button class="dashboard-carousel-dot" type="button" data-panel-target="rankings" aria-label="Ir a Top" aria-pressed="false"></button>
                        <button class="dashboard-carousel-dot" type="button" data-panel-target="actividad" aria-label="Ir a Pedidos" aria-pressed="false"></button>
                    </div>

                    <div class="dashboard-carousel-nav">
                        <button class="dashboard-carousel-btn" id="dashboardPrev" type="button" aria-label="Ir a la sección anterior" disabled>
                            <i class="fas fa-arrow-left"></i>
                        </button>
                        <button class="dashboard-carousel-btn" id="dashboardNext" type="button" aria-label="Ir a la siguiente sección">
                            <i class="fas fa-arrow-right"></i>
                        </button>
                    </div>
                </div>
            </div>
        </div>
    </div>
```

**new_string:**

```html
<div class="exec-dashboard" data-dashboard-tabs>
    <nav class="dash-tabs" role="tablist" aria-label="Secciones del dashboard">
        <button class="dash-tab is-active" type="button" role="tab" aria-selected="true"  aria-controls="panel-tendencia" data-panel="tendencia">Ventas</button>
        <button class="dash-tab"           type="button" role="tab" aria-selected="false" aria-controls="panel-servicio"  data-panel="servicio">Servicio</button>
        <button class="dash-tab"           type="button" role="tab" aria-selected="false" aria-controls="panel-rankings"  data-panel="rankings">Top</button>
        <button class="dash-tab"           type="button" role="tab" aria-selected="false" aria-controls="panel-actividad" data-panel="actividad">Pedidos</button>
        <span class="dash-tabs-indicator" aria-hidden="true"></span>
    </nav>
```

- [ ] **Step 4: Remove the inline carousel JS block**

Locate the inline carousel controller script in `templates/dashboard.html`. From the earlier grep, it starts near line 1598 with `const carousel = document.getElementById('dashboardCarousel');`. Find the surrounding `<script>` block (it's likely wrapped in an IIFE or DOMContentLoaded handler).

Use grep to find the exact bounds:

```bash
grep -n "dashboardCarousel\|dashboardPrev\|dashboardNext\|dashboardSectionLabel\|</script>" templates/dashboard.html | head -40
```

Identify the opening `<script>` and closing `</script>` that enclose the carousel logic and delete the entire block (including the tags). If the carousel code is mixed with other dashboard JS inside the same `<script>`, delete only the carousel-specific portion — in practice it's a self-contained IIFE or event handler, so a clean cut is usually possible.

**If uncertain, stop and escalate BLOCKED** with the grep output. Do not guess at boundaries — the dashboard page has other scripts that must keep working.

- [ ] **Step 5: Run tests to verify pass**

```bash
python -m pytest -p no:postgresql tests/test_dashboard_redesign.py -v -k "tab_bar or carousel_markup"
```

Expected: 2 PASS.

- [ ] **Step 6: Run the full dashboard KPI tests — must still pass**

```bash
python -m pytest -p no:postgresql tests/test_dashboard_kpis.py -v 2>&1 | tail -5
```

Expected: 30 passed (baseline intact).

- [ ] **Step 7: Commit**

```bash
git add templates/dashboard.html tests/test_dashboard_redesign.py
git commit -m "feat(dashboard): replace carousel nav with X-style tab bar"
```

---

## Task 5: Ambient background on `.exec-dashboard`

**Files:**
- Modify: `templates/dashboard.html`
- Modify: `tests/test_dashboard_redesign.py`

- [ ] **Step 1: Write the failing test**

Append:

```python
def test_dashboard_uses_ambient_background(logged_client):
    resp = logged_client.get('/dashboard')
    html = resp.data.decode('utf-8')
    # The outer .exec-dashboard div has the ambient gradient applied
    assert 'var(--bg-ambient)' in html
```

- [ ] **Step 2: Run test to verify failure**

```bash
python -m pytest -p no:postgresql tests/test_dashboard_redesign.py::test_dashboard_uses_ambient_background -v
```

- [ ] **Step 3: Modify `templates/dashboard.html`**

Replace the opening tag of the dashboard container added in Task 4:

**old_string:**

```html
<div class="exec-dashboard" data-dashboard-tabs>
```

**new_string:**

```html
<div class="exec-dashboard" data-dashboard-tabs style="background: var(--bg-ambient); min-height: 100vh;">
```

- [ ] **Step 4: Run test to verify pass**

```bash
python -m pytest -p no:postgresql tests/test_dashboard_redesign.py::test_dashboard_uses_ambient_background -v
```

- [ ] **Step 5: Commit**

```bash
git add templates/dashboard.html tests/test_dashboard_redesign.py
git commit -m "feat(dashboard): apply --bg-ambient gradient to dashboard container"
```

---

## Task 6: Refresh Ventas panel (KPI tiles → glass cards with ring states)

**Files:**
- Modify: `templates/dashboard.html` (panel-tendencia block, approximately lines 97-213)
- Modify: `tests/test_dashboard_redesign.py`

- [ ] **Step 1: Write the failing test**

Append:

```python
def test_ventas_panel_uses_glass_cards_and_ring_primitive(logged_client):
    resp = logged_client.get('/dashboard')
    html = resp.data.decode('utf-8')
    # Extract just the Ventas panel for scoped assertions
    start = html.find('id="panel-tendencia"')
    end = html.find('id="panel-servicio"')
    assert start != -1 and end != -1, "Panel boundaries not found"
    panel = html[start:end]
    # New primitive classes replace old .kpi-tile / .progress-ring patterns
    assert 'card card-glass' in panel, "expected .card.card-glass in Ventas panel"
    assert 'class="ring"' in panel or 'class=\'ring\'' in panel or 'class="ring ' in panel
    assert 'data-state=' in panel, "rings must carry data-state for semantic color"
    # Old classes should be gone from this panel
    assert 'kpi-tile' not in panel
    assert 'progress-ring' not in panel
    assert 'c-green' not in panel
    assert 'c-amber' not in panel
    assert 'c-red' not in panel
```

- [ ] **Step 2: Run test to verify failure**

```bash
python -m pytest -p no:postgresql tests/test_dashboard_redesign.py::test_ventas_panel_uses_glass_cards_and_ring_primitive -v
```

- [ ] **Step 3: Modify `templates/dashboard.html` — Ventas panel content**

Refactor the Ventas panel (`<div class="tab-panel active" id="panel-tendencia" …>`). The 4 KPI tiles inside `<div class="kpi-grid">` need updating.

**Tile 1 — Ventas del Mes.**

Replace:

```html
                <div class="kpi-tile">
                    <div class="tile-top">
                        <span class="tile-label">Ventas del Mes</span>
                        <svg class="progress-ring" width="48" height="48" viewBox="0 0 48 48">
                            <circle class="ring-bg" cx="24" cy="24" r="{{ ring_r }}" />
                            <circle class="ring-fg
                                {%- if porcentaje_meta_v >= 80 %} c-green
                                {%- elif porcentaje_meta_v >= 50 %} c-amber
                                {%- else %} c-red{% endif %}"
                                cx="24" cy="24" r="{{ ring_r }}"
                                style="stroke-dasharray:{{ ring_circ }};stroke-dashoffset:{{ ring1_offset }}" />
                            <text x="24" y="26" class="ring-text">{{ '%.0f' % porcentaje_meta_v }}%</text>
                        </svg>
                    </div>
                    <div class="tile-value">{{ '{:,.0f}'.format(ventas_mes_v) }} <small>XCG</small></div>
                    <div class="tile-sub">Meta: {{ '{:,.0f}'.format(meta_mensual_v) }} · {{ pedidos_mes_v }} ped</div>
                </div>
```

with:

```html
                <div class="card card-glass" data-state="{% if porcentaje_meta_v >= 85 %}success{% elif porcentaje_meta_v >= 70 %}warning{% else %}danger{% endif %}">
                    <div class="card-body">
                        <div class="cluster cluster-2" style="justify-content: space-between; align-items: center;">
                            <span class="label">Ventas del Mes</span>
                            <svg class="ring" data-state="{% if porcentaje_meta_v >= 85 %}success{% elif porcentaje_meta_v >= 70 %}warning{% else %}danger{% endif %}" width="48" height="48" viewBox="0 0 48 48">
                                <circle class="ring-bg" cx="24" cy="24" r="{{ ring_r }}"/>
                                <circle class="ring-fg" cx="24" cy="24" r="{{ ring_r }}" style="stroke-dasharray:{{ ring_circ }};stroke-dashoffset:{{ ring1_offset }}"/>
                                <text class="ring-text" x="24" y="26">{{ '%.0f' % porcentaje_meta_v }}%</text>
                            </svg>
                        </div>
                        <div class="text-2xl font-bold tabular tracking-tight" style="margin-top: var(--space-2);">{{ '{:,.0f}'.format(ventas_mes_v) }} <span class="text-sm text-subtle font-medium">XCG</span></div>
                        <div class="text-sm text-muted" style="margin-top: var(--space-1);">Meta: {{ '{:,.0f}'.format(meta_mensual_v) }} · {{ pedidos_mes_v }} ped</div>
                    </div>
                </div>
```

**Tile 2 — Proyección.**

Replace:

```html
                <div class="kpi-tile">
                    <div class="tile-top">
                        <span class="tile-label">Proyección</span>
                        <svg class="progress-ring" width="48" height="48" viewBox="0 0 48 48">
                            <circle class="ring-bg" cx="24" cy="24" r="{{ ring_r }}" />
                            <circle class="ring-fg
                                {%- if porcentaje_proyeccion_v >= 100 %} c-green
                                {%- elif porcentaje_proyeccion_v >= 80 %} c-amber
                                {%- else %} c-red{% endif %}"
                                cx="24" cy="24" r="{{ ring_r }}"
                                style="stroke-dasharray:{{ ring_circ }};stroke-dashoffset:{{ ring2_offset }}" />
                            <text x="24" y="26" class="ring-text">{{ '%.0f' % porcentaje_proyeccion_v }}%</text>
                        </svg>
                    </div>
                    {% if proyeccion_ventas_v > 0 %}
                    <div class="tile-value">{{ '{:,.0f}'.format(proyeccion_ventas_v) }} <small>XCG</small></div>
                    {% else %}
                    <div class="tile-value tile-muted">Sin datos</div>
                    {% endif %}
                    <div class="tile-sub">{{ '%.0f' % porcentaje_proyeccion_v }}% de meta</div>
                </div>
```

with:

```html
                <div class="card card-glass" data-state="{% if porcentaje_proyeccion_v >= 100 %}success{% elif porcentaje_proyeccion_v >= 80 %}warning{% else %}danger{% endif %}">
                    <div class="card-body">
                        <div class="cluster cluster-2" style="justify-content: space-between; align-items: center;">
                            <span class="label">Proyección</span>
                            <svg class="ring" data-state="{% if porcentaje_proyeccion_v >= 100 %}success{% elif porcentaje_proyeccion_v >= 80 %}warning{% else %}danger{% endif %}" width="48" height="48" viewBox="0 0 48 48">
                                <circle class="ring-bg" cx="24" cy="24" r="{{ ring_r }}"/>
                                <circle class="ring-fg" cx="24" cy="24" r="{{ ring_r }}" style="stroke-dasharray:{{ ring_circ }};stroke-dashoffset:{{ ring2_offset }}"/>
                                <text class="ring-text" x="24" y="26">{{ '%.0f' % porcentaje_proyeccion_v }}%</text>
                            </svg>
                        </div>
                        {% if proyeccion_ventas_v > 0 %}
                        <div class="text-2xl font-bold tabular tracking-tight" style="margin-top: var(--space-2);">{{ '{:,.0f}'.format(proyeccion_ventas_v) }} <span class="text-sm text-subtle font-medium">XCG</span></div>
                        {% else %}
                        <div class="text-2xl font-bold text-subtle" style="margin-top: var(--space-2);">Sin datos</div>
                        {% endif %}
                        <div class="text-sm text-muted" style="margin-top: var(--space-1);">{{ '%.0f' % porcentaje_proyeccion_v }}% de meta</div>
                    </div>
                </div>
```

**Tile 3 — On Time Delivery.**

Replace:

```html
                <div class="kpi-tile">
                    <div class="tile-top">
                        <span class="tile-label">On Time Delivery</span>
                        <svg class="progress-ring" width="48" height="48" viewBox="0 0 48 48">
                            <circle class="ring-bg" cx="24" cy="24" r="{{ ring_r }}" />
                            <circle class="ring-fg
                                {%- if otd_rate_v >= 95 %} c-green
                                {%- elif otd_rate_v >= 85 %} c-amber
                                {%- else %} c-red{% endif %}"
                                cx="24" cy="24" r="{{ ring_r }}"
                                style="stroke-dasharray:{{ ring_circ }};stroke-dashoffset:{{ ring3_offset }}" />
                            <text x="24" y="26" class="ring-text">{{ '%.0f' % otd_rate_v }}%</text>
                        </svg>
                    </div>
                    <div class="tile-value">{{ '%.1f' % otd_rate_v }}%</div>
                    <div class="tile-sub">OFR: {{ '%.0f' % order_completion_rate_v }}% · ≤2 días</div>
                </div>
```

with:

```html
                <div class="card card-glass" data-state="{% if otd_rate_v >= 95 %}success{% elif otd_rate_v >= 85 %}warning{% else %}danger{% endif %}">
                    <div class="card-body">
                        <div class="cluster cluster-2" style="justify-content: space-between; align-items: center;">
                            <span class="label">On Time Delivery</span>
                            <svg class="ring" data-state="{% if otd_rate_v >= 95 %}success{% elif otd_rate_v >= 85 %}warning{% else %}danger{% endif %}" width="48" height="48" viewBox="0 0 48 48">
                                <circle class="ring-bg" cx="24" cy="24" r="{{ ring_r }}"/>
                                <circle class="ring-fg" cx="24" cy="24" r="{{ ring_r }}" style="stroke-dasharray:{{ ring_circ }};stroke-dashoffset:{{ ring3_offset }}"/>
                                <text class="ring-text" x="24" y="26">{{ '%.0f' % otd_rate_v }}%</text>
                            </svg>
                        </div>
                        <div class="text-2xl font-bold tabular tracking-tight" style="margin-top: var(--space-2);">{{ '%.1f' % otd_rate_v }}%</div>
                        <div class="text-sm text-muted" style="margin-top: var(--space-1);">OFR: {{ '%.0f' % order_completion_rate_v }}% · ≤2 días</div>
                    </div>
                </div>
```

**Tile 4 — Pendientes** (inverse state: fewer is better).

Use Edit to find the 4th `<div class="kpi-tile">` inside the Ventas panel. It should contain `<span class="tile-label">Pendientes</span>` and `{{ pedidos_pendientes_v }}`. The original block looks like:

```html
                <div class="kpi-tile">
                    <div class="tile-top">
                        <span class="tile-label">Pendientes</span>
                        <svg class="progress-ring" width="48" height="48" viewBox="0 0 48 48">
                            <circle class="ring-bg" cx="24" cy="24" r="{{ ring_r }}" />
                            <circle class="ring-fg
                                {%- if pedidos_pendientes_v == 0 %} c-green
                                {%- elif pedidos_pendientes_v <= 3 %} c-amber
                                {%- else %} c-red{% endif %}"
                                cx="24" cy="24" r="{{ ring_r }}"
                                style="stroke-dasharray:{{ ring_circ }};stroke-dashoffset:{{ ring4_offset }}" />
                            <text x="24" y="26" class="ring-text">{{ pedidos_pendientes_v }}</text>
                        </svg>
                    </div>
                    <div class="tile-value tile-value-big">{{ pedidos_pendientes_v }}</div>
                    <div class="tile-sub">pedidos en cola</div>
                </div>
```

Replace with:

```html
                <div class="card card-glass" data-state="{% if pedidos_pendientes_v == 0 %}success{% elif pedidos_pendientes_v <= 3 %}warning{% else %}danger{% endif %}">
                    <div class="card-body">
                        <div class="cluster cluster-2" style="justify-content: space-between; align-items: center;">
                            <span class="label">Pendientes</span>
                            <svg class="ring" data-state="{% if pedidos_pendientes_v == 0 %}success{% elif pedidos_pendientes_v <= 3 %}warning{% else %}danger{% endif %}" width="48" height="48" viewBox="0 0 48 48">
                                <circle class="ring-bg" cx="24" cy="24" r="{{ ring_r }}"/>
                                <circle class="ring-fg" cx="24" cy="24" r="{{ ring_r }}" style="stroke-dasharray:{{ ring_circ }};stroke-dashoffset:{{ ring4_offset }}"/>
                                <text class="ring-text" x="24" y="26">{{ pedidos_pendientes_v }}</text>
                            </svg>
                        </div>
                        <div class="text-2xl font-bold tabular tracking-tight" style="margin-top: var(--space-2);">{{ pedidos_pendientes_v }}</div>
                        <div class="text-sm text-muted" style="margin-top: var(--space-1);">pedidos en cola</div>
                    </div>
                </div>
```

**If the Ventas panel has additional child blocks (e.g., the meta progress bar, the weekly trend chart wrapper):** leave them as-is for this task. Only the 4 KPI tiles above are in scope for Task 6. The meta-progress / chart containers will be addressed by Phase 3.1 if the user wants to go deeper later.

- [ ] **Step 4: Run the Ventas-panel test**

```bash
python -m pytest -p no:postgresql tests/test_dashboard_redesign.py::test_ventas_panel_uses_glass_cards_and_ring_primitive -v
```

- [ ] **Step 5: Run full dashboard KPI tests**

```bash
python -m pytest -p no:postgresql tests/test_dashboard_kpis.py 2>&1 | tail -3
```

Expected: 30 passed (data output unchanged — only classes moved).

- [ ] **Step 6: Commit**

```bash
git add templates/dashboard.html tests/test_dashboard_redesign.py
git commit -m "feat(dashboard): refresh Ventas panel with glass cards + ring primitive"
```

---

## Task 7: Refresh Servicio panel

**Files:**
- Modify: `templates/dashboard.html` (panel-servicio block)
- Modify: `tests/test_dashboard_redesign.py`

- [ ] **Step 1: Write the failing test**

Append:

```python
def test_servicio_panel_uses_glass_cards_and_rings(logged_client):
    resp = logged_client.get('/dashboard')
    html = resp.data.decode('utf-8')
    start = html.find('id="panel-servicio"')
    end = html.find('id="panel-rankings"')
    assert start != -1 and end != -1
    panel = html[start:end]
    # OTD, Order Completion, Perfect Order, Customer Engagement — all as ring primitives
    assert panel.count('class="ring"') + panel.count("class='ring'") >= 3, (
        "Expected at least 3 ring primitives in Servicio panel"
    )
    assert 'card card-glass' in panel
    # Old patterns removed from this panel
    assert 'kpi-tile' not in panel
    assert 'progress-ring' not in panel
    assert 'c-green' not in panel and 'c-amber' not in panel and 'c-red' not in panel
```

- [ ] **Step 2: Run test to verify failure**

```bash
python -m pytest -p no:postgresql tests/test_dashboard_redesign.py::test_servicio_panel_uses_glass_cards_and_rings -v
```

- [ ] **Step 3: Inspect the Servicio panel block and apply the same refactor**

The Servicio panel starts at `<div class="tab-panel" id="panel-servicio" …>` and ends at `<div class="tab-panel" id="panel-rankings" …>`. Inside, every `<div class="kpi-tile">` with an SVG `progress-ring` follows the same shape as the Ventas tiles. For each tile you find:

1. Change outer `<div class="kpi-tile">` to `<div class="card card-glass" data-state="<state-expr>">` and insert a `<div class="card-body">` wrapper.
2. Change the inner `<div class="tile-top">` to `<div class="cluster cluster-2" style="justify-content: space-between; align-items: center;">`.
3. Change `<span class="tile-label">` to `<span class="label">`.
4. Change `<svg class="progress-ring" …>` to `<svg class="ring" data-state="<state-expr>" …>` and drop the `c-green`/`c-amber`/`c-red` class from the `<circle class="ring-fg …">` — leave it as just `class="ring-fg"`.
5. Change `<div class="tile-value">` to `<div class="text-2xl font-bold tabular tracking-tight" style="margin-top: var(--space-2);">`.
6. Change `<div class="tile-sub">` to `<div class="text-sm text-muted" style="margin-top: var(--space-1);">`.

The `<state-expr>` Jinja expression per KPI (thresholds match spec §5):

- `otd_rate_v`: `{% if otd_rate_v >= 95 %}success{% elif otd_rate_v >= 85 %}warning{% else %}danger{% endif %}`
- `order_completion_rate_v`: `{% if order_completion_rate_v >= 95 %}success{% elif order_completion_rate_v >= 85 %}warning{% else %}danger{% endif %}`
- `perfect_order_rate_v`: same threshold template as `order_completion_rate_v`.
- `customer_engagement_v`: `{% if customer_engagement_v >= 60 %}success{% elif customer_engagement_v >= 40 %}warning{% else %}danger{% endif %}` (Customer Engagement uses a different natural range — these are reasonable defaults).

**Work tile-by-tile.** After each edit, re-render the page (or re-run the test) to confirm the Jinja still compiles.

- [ ] **Step 4: Run the Servicio test**

```bash
python -m pytest -p no:postgresql tests/test_dashboard_redesign.py::test_servicio_panel_uses_glass_cards_and_rings -v
```

- [ ] **Step 5: Run full dashboard KPI tests**

```bash
python -m pytest -p no:postgresql tests/test_dashboard_kpis.py 2>&1 | tail -3
```

- [ ] **Step 6: Commit**

```bash
git add templates/dashboard.html tests/test_dashboard_redesign.py
git commit -m "feat(dashboard): refresh Servicio panel with glass cards + ring primitive"
```

---

## Task 8: Refresh Top panel (rankings + filter chips)

**Files:**
- Modify: `templates/dashboard.html` (panel-rankings block)
- Modify: `tests/test_dashboard_redesign.py`

- [ ] **Step 1: Write the failing test**

Append:

```python
def test_top_panel_uses_cards_and_chips(logged_client):
    resp = logged_client.get('/dashboard')
    html = resp.data.decode('utf-8')
    start = html.find('id="panel-rankings"')
    end = html.find('id="panel-actividad"')
    assert start != -1 and end != -1
    panel = html[start:end]
    # Rankings become cards
    assert 'class="card' in panel, "expected at least one .card in Top panel"
    # Period filter pills become chips
    assert 'class="chip' in panel or "class='chip" in panel
```

- [ ] **Step 2: Run test to verify failure**

```bash
python -m pytest -p no:postgresql tests/test_dashboard_redesign.py::test_top_panel_uses_cards_and_chips -v
```

- [ ] **Step 3: Inspect the Top panel**

The Top panel starts at `<div class="tab-panel" id="panel-rankings" …>` and ends at `<div class="tab-panel" id="panel-actividad" …>`. It contains:

- A period filter group (buttons or tabs labeled Mes / 3M / 6M / 4W).
- A Top Clientes list (up to 5 entries with name, orders, total).
- A Top Productos list (up to 5 entries with name, cajas, ingresos).

**Refactor 3.1 — Period filter.** Find the period filter buttons. They typically look like `<button class="period-pill">Mes</button>` or `<button class="filter-tab active">Mes</button>`. Replace each with:

```html
<button class="chip {% if is_active %}chip-primary{% endif %}" type="button" data-period="month">Mes</button>
```

Apply the same pattern for the other periods (3m, 6m, 4w). The `{% if is_active %}` expression depends on the existing template's active-state variable — preserve it.

If you can't identify the exact filter markup, **grep first**:

```bash
grep -n "data-period\|periodo\|Mes\|3M\|6M\|4W" templates/dashboard.html | head -20
```

**Refactor 3.2 — Top Clientes & Top Productos lists.**

Each list item typically sits inside a parent container with `<div class="ranking-item">` or similar. Wrap each row (or the whole list) in a `.card` with `.card-interactive` so hover lifts it:

For a **list item** pattern like:

```html
<div class="ranking-item">
  <div class="ranking-rank">1</div>
  <div class="ranking-info">
    <div class="ranking-name">Cliente X</div>
    <div class="ranking-meta">12 pedidos</div>
  </div>
  <div class="ranking-total">45,000 XCG</div>
</div>
```

transform to:

```html
<div class="card card-interactive" style="margin-bottom: var(--space-2);">
  <div class="card-body">
    <div class="cluster cluster-3" style="align-items: center; justify-content: space-between;">
      <div class="cluster cluster-3" style="align-items: center;">
        <span class="chip chip-primary">1</span>
        <div>
          <div class="text-md font-semibold">Cliente X</div>
          <div class="text-xs text-muted">12 pedidos</div>
        </div>
      </div>
      <div class="text-lg font-bold tabular">45,000 <span class="text-xs text-subtle">XCG</span></div>
    </div>
  </div>
</div>
```

**Exact markup depends on the current template.** Adapt the transformation using the same primitives. Keep the Jinja loop and variable references intact.

If the existing markup is substantially different from the example, **escalate NEEDS_CONTEXT** with the exact block and ask for guidance.

- [ ] **Step 4: Run the Top test**

```bash
python -m pytest -p no:postgresql tests/test_dashboard_redesign.py::test_top_panel_uses_cards_and_chips -v
```

- [ ] **Step 5: Run full dashboard KPI tests**

```bash
python -m pytest -p no:postgresql tests/test_dashboard_kpis.py 2>&1 | tail -3
```

- [ ] **Step 6: Commit**

```bash
git add templates/dashboard.html tests/test_dashboard_redesign.py
git commit -m "feat(dashboard): refresh Top panel with card rows + chip filters"
```

---

## Task 9: Refresh Pedidos panel (counts + badges + status chips)

**Files:**
- Modify: `templates/dashboard.html` (panel-actividad block)
- Modify: `tests/test_dashboard_redesign.py`

- [ ] **Step 1: Write the failing test**

Append:

```python
def test_pedidos_panel_uses_cards_and_semantic_chips(logged_client):
    resp = logged_client.get('/dashboard')
    html = resp.data.decode('utf-8')
    start = html.find('id="panel-actividad"')
    # Panel is the last one — take the remainder of the tab-panels container
    end = html.find('</div>\n    </div>', start) if start != -1 else -1
    assert start != -1
    panel = html[start:]  # tolerate if we can't find the exact end
    assert 'class="card' in panel
    # Overdue orders (vencidos) should use semantic danger styling
    assert 'chip-danger' in panel or 'badge' in panel
```

- [ ] **Step 2: Run test to verify failure**

```bash
python -m pytest -p no:postgresql tests/test_dashboard_redesign.py::test_pedidos_panel_uses_cards_and_semantic_chips -v
```

- [ ] **Step 3: Inspect the Pedidos panel**

The Pedidos panel starts at `<div class="tab-panel" id="panel-actividad" …>`. Typically it contains:

- Pending orders count (prominent).
- Overdue orders count (semantic-danger).
- Facturados today count.
- Prep activity.

For each counter block like:

```html
<div class="kpi-tile">
  <div class="tile-label">Vencidos</div>
  <div class="tile-value-big">{{ pedidos_vencidos_v }}</div>
  <div class="tile-sub">Requieren atención</div>
</div>
```

replace with:

```html
<div class="card{% if pedidos_vencidos_v > 0 %} card-interactive{% endif %}">
  <div class="card-body">
    <div class="cluster cluster-2" style="align-items: center; justify-content: space-between;">
      <span class="label">Vencidos</span>
      {% if pedidos_vencidos_v > 0 %}<span class="badge">{{ pedidos_vencidos_v }}</span>{% endif %}
    </div>
    <div class="text-2xl font-bold tabular" style="margin-top: var(--space-2); {% if pedidos_vencidos_v > 0 %}color: var(--color-danger);{% endif %}">{{ pedidos_vencidos_v }}</div>
    <div class="text-sm text-muted">Requieren atención</div>
  </div>
</div>
```

Apply equivalent transforms to the other counters, changing only the classes — never the Jinja variable names or backend logic. For status-text strings ("Pendiente", "Facturado", "Listo"), wrap them in `<span class="chip chip-{warning|success|primary}">…</span>` as appropriate.

- [ ] **Step 4: Run the Pedidos test**

```bash
python -m pytest -p no:postgresql tests/test_dashboard_redesign.py::test_pedidos_panel_uses_cards_and_semantic_chips -v
```

- [ ] **Step 5: Run full dashboard KPI tests**

```bash
python -m pytest -p no:postgresql tests/test_dashboard_kpis.py 2>&1 | tail -3
```

- [ ] **Step 6: Commit**

```bash
git add templates/dashboard.html tests/test_dashboard_redesign.py
git commit -m "feat(dashboard): refresh Pedidos panel with cards + badges + semantic chips"
```

---

## Task 10: Swipe gesture + keyboard nav in JS

**Files:**
- Modify: `static/js/dashboard-tabs.js`
- Modify: `tests/test_dashboard_redesign.py`

- [ ] **Step 1: Write the failing test**

Append:

```python
def test_dashboard_tabs_js_has_swipe_and_keyboard_nav():
    js = DASHBOARD_TABS_JS.read_text(encoding='utf-8')
    # Touch-based swipe detection
    assert 'touchstart' in js
    assert 'touchend' in js or 'touchmove' in js
    # Keyboard nav — arrow keys
    assert "'ArrowLeft'" in js or '"ArrowLeft"' in js
    assert "'ArrowRight'" in js or '"ArrowRight"' in js
```

- [ ] **Step 2: Run test to verify failure**

```bash
python -m pytest -p no:postgresql tests/test_dashboard_redesign.py::test_dashboard_tabs_js_has_swipe_and_keyboard_nav -v
```

- [ ] **Step 3: Extend `static/js/dashboard-tabs.js`**

Append two new private methods to the `DashboardTabs` class and call them from the constructor. Replace the existing constructor body to include the new initializations, and add methods after `_updateIndicator`:

```javascript
    // Replace the existing constructor body with this version:
    constructor(root) {
      this.root = root;
      this.tabBar = root.querySelector('.dash-tabs');
      this.indicator = root.querySelector('.dash-tabs-indicator');
      this.tabs = Array.from(root.querySelectorAll('.dash-tab'));
      this.panels = Array.from(root.querySelectorAll('.tab-panel'));
      this.panelsContainer = root.querySelector('.tab-panels') || root;

      if (!this.tabBar || !this.indicator || this.tabs.length === 0) return;

      this.activeIndex = Math.max(0, this.tabs.findIndex(t => t.classList.contains('is-active')));
      this._bindClicks();
      this._bindKeyboard();
      this._bindSwipe();
      window.addEventListener('resize', () => this._updateIndicator(), { passive: true });

      requestAnimationFrame(() => this._updateIndicator());
    }

    // Append after _updateIndicator():

    _bindKeyboard() {
      this.tabs.forEach((tab, i) => {
        tab.addEventListener('keydown', (e) => {
          if (e.key === 'ArrowRight') {
            e.preventDefault();
            const next = Math.min(this.tabs.length - 1, i + 1);
            this.activate(next);
            this.tabs[next].focus();
          } else if (e.key === 'ArrowLeft') {
            e.preventDefault();
            const prev = Math.max(0, i - 1);
            this.activate(prev);
            this.tabs[prev].focus();
          }
        });
      });
    }

    _bindSwipe() {
      let startX = 0;
      let startY = 0;
      let tracking = false;
      const THRESHOLD = 50;

      this.panelsContainer.addEventListener('touchstart', (e) => {
        if (e.touches.length !== 1) return;
        startX = e.touches[0].clientX;
        startY = e.touches[0].clientY;
        tracking = true;
      }, { passive: true });

      this.panelsContainer.addEventListener('touchend', (e) => {
        if (!tracking) return;
        tracking = false;
        const t = e.changedTouches[0];
        const dx = t.clientX - startX;
        const dy = t.clientY - startY;
        // Ignore if mostly vertical (user was scrolling)
        if (Math.abs(dy) > Math.abs(dx)) return;
        if (dx <= -THRESHOLD) {
          this.activate(Math.min(this.tabs.length - 1, this.activeIndex + 1));
        } else if (dx >= THRESHOLD) {
          this.activate(Math.max(0, this.activeIndex - 1));
        }
      }, { passive: true });
    }
```

Use Edit to replace the constructor body, then append the two new methods just before the closing `}` of the `DashboardTabs` class (before `document.addEventListener('DOMContentLoaded', …)`).

- [ ] **Step 4: Run the swipe/keyboard test**

```bash
python -m pytest -p no:postgresql tests/test_dashboard_redesign.py::test_dashboard_tabs_js_has_swipe_and_keyboard_nav -v
```

- [ ] **Step 5: Commit**

```bash
git add static/js/dashboard-tabs.js tests/test_dashboard_redesign.py
git commit -m "feat(dashboard): add swipe gesture + keyboard ←/→ navigation"
```

---

## Task 11: Final verification + push + PR

- [ ] **Step 1: Run full pytest suite — everything must pass**

```bash
source .venv311/bin/activate && python -m pytest -p no:postgresql tests/ 2>&1 | tail -5
```

Expected: 163 (Phase 1 baseline) + ~10 new Phase 3 tests = ~173 passed.

- [ ] **Step 2: Manual smoke test in browser**

Start the dev server (on port 8000 to avoid macOS AirPlay on 5000):

```bash
FLASK_ENV=development PORT=8000 python app.py
```

Log in as super_admin (locally: `admin` / `admin`). Visit `http://localhost:8000/dashboard` and verify:

- [ ] Tab bar renders with 4 labels (Ventas, Servicio, Top, Pedidos).
- [ ] Clicking a tab moves the underline indicator with a spring animation.
- [ ] The correct panel becomes visible and the others are hidden.
- [ ] Keyboard ← / → with focus on tabs cycles them.
- [ ] On touch devices / Chrome responsive mode, horizontal swipe on the panel body advances to the adjacent tab.
- [ ] KPI tiles render as glass cards with ring primitives.
- [ ] Ring color matches threshold (set a KPI low to force danger / mid for warning / high for success).
- [ ] Toggle macOS Appearance (Light ↔ Dark) and confirm the entire dashboard switches: ambient gradient, tab bar blur, cards, rings, text all update.
- [ ] No JS errors in DevTools console.

- [ ] **Step 3: Verify other pages are untouched**

In the same session, browse to `/pedidos`, `/login`, `/clientes`. Each should look **identical** to before Phase 3. If anything changed visually outside the dashboard, investigate — something leaked.

- [ ] **Step 4: Push branch**

```bash
git push -u origin feat/dashboard-tabs-x
```

- [ ] **Step 5: Open PR**

```bash
gh pr create --title "Phase 3: Dashboard tabs X-style + glass refresh" --body "$(cat <<'EOF'
## Summary

- Replaces the dashboard carousel (dots + arrow buttons + inline carousel JS) with an X/Twitter-style horizontal tab bar. Animated underline indicator, sticky header, identical on mobile and desktop.
- Applies Phase 1 glass tokens + primitives to every element in the 4 existing panels (Ventas, Servicio, Top, Pedidos). KPI tiles become glass cards; progress rings use the new `.ring[data-state]` primitive; filter pills become chips; ranking rows become `.card-interactive`; overdue counters get semantic `.badge` and `chip-danger`.
- New `static/js/dashboard-tabs.js` (~100 LOC vanilla JS) handles tab activation, indicator animation, horizontal swipe, and keyboard ←/→ nav.
- Dark mode activates automatically via `prefers-color-scheme` thanks to the semantic token system.

## Scope

Phase 3 of 5 in the systemic visual redesign. Panel content and backend logic unchanged. Global app shell (Phase 2), Pedidos page (Phase 4), and secondary pages (Phase 5) still pending.

## Dependencies

Built on top of `feat/glass-foundation` (Phase 1 PR #23). Rebase on `main` after Phase 1 merges.

## Test plan

- [x] Phase 1 tests (163) unchanged.
- [x] 10 new Phase 3 integration tests pass (nav markup, panel refresh, JS controller).
- [x] Existing dashboard KPI math tests (30) still pass — data unchanged.
- [ ] Manual: all 4 tabs render, indicator animates, swipe/keyboard/click all work.
- [ ] Manual: dark mode via macOS Appearance toggle affects entire dashboard.
- [ ] Manual: `/pedidos`, `/login`, `/clientes` visually unchanged (regression check).

## References

- Spec: `docs/superpowers/specs/2026-04-17-dashboard-tabs-x-design.md`
- Plan: `docs/superpowers/plans/2026-04-17-dashboard-tabs-x.md`

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

- [ ] **Step 6: Report PR URL**

Print the PR URL and mark the work complete. The user merges after visual check.

---

## Dependency map

```
T1 scaffolding (branch + empty JS + script tag + tests)
 ├─ T2 .dash-tabs CSS primitive
 ├─ T3 DashboardTabs JS core
 │   └─ T10 swipe + keyboard extensions (after T3)
 └─ T4 template nav swap + remove inline carousel JS
     ├─ T5 ambient background
     ├─ T6 Ventas panel refresh
     ├─ T7 Servicio panel refresh
     ├─ T8 Top panel refresh
     └─ T9 Pedidos panel refresh
         └─ T11 final verification + PR
```

T6-T9 are independent of each other after T4 completes; they can be parallelized or sequenced.

---

## Spec-to-plan coverage

| Spec section | Implementing task(s) |
|---|---|
| §2 In scope — replace nav | T4 |
| §2 In scope — .dash-tabs primitive | T2 |
| §2 In scope — JS controller | T3 + T10 |
| §2 In scope — panel refresh | T6, T7, T8, T9 |
| §2 In scope — ambient background | T5 |
| §2 In scope — script tag in base.html | T1 |
| §4 Tab bar markup + styling | T2, T4 |
| §4 JS controller (activate + indicator) | T3 |
| §4 Swipe + keyboard | T10 |
| §5 Panel content refresh | T6-T9 |
| §6 File changes | T1-T10 |
| §7 Success criterion 1 (tab bar renders) | T4 (test) |
| §7 Success criterion 2 (indicator animates) | T3, T11 manual |
| §7 Success criterion 3 (swipe works) | T10, T11 manual |
| §7 Success criterion 4 (keyboard works) | T10, T11 manual |
| §7 Success criterion 5 (primitives in panels) | T6-T9 (tests) |
| §7 Success criterion 6 (ring thresholds) | T6, T7, T11 manual |
| §7 Success criterion 7 (dark mode auto) | T5 + T11 manual |
| §7 Success criterion 8 (KPI tests still pass) | T6-T9 (test step) |
| §7 Success criterion 9 (/dev/primitives unaffected) | T11 |
| §7 Success criterion 10 (smoke test) | T11 |
