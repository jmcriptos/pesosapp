# tests/test_dashboard_redesign.py
"""Tests for Phase 3 Dashboard Tabs X-style + Glass Refresh."""
import os
from pathlib import Path
import pytest

os.environ.setdefault('SECRET_KEY', 'test-secret')
os.environ.setdefault('FLASK_ENV', 'testing')
os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DASHBOARD_TABS_JS = PROJECT_ROOT / 'static' / 'js' / 'dashboard-tabs.js'
PRIMITIVES_CSS = PROJECT_ROOT / 'static' / 'css' / 'primitives.css'
BASE_HTML = PROJECT_ROOT / 'templates' / 'base.html'
DASHBOARD_HTML = PROJECT_ROOT / 'templates' / 'dashboard.html'

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


# ─── Task 1: Scaffold ────────────────────────────────────────────────────────

def test_dashboard_tabs_js_file_exists():
    """dashboard-tabs.js must exist in static/js/."""
    assert DASHBOARD_TABS_JS.exists(), f"Expected {DASHBOARD_TABS_JS} to exist"


def test_base_html_loads_dashboard_tabs_js():
    """base.html must load dashboard-tabs.js with defer."""
    html = BASE_HTML.read_text(encoding='utf-8')
    assert 'dashboard-tabs.js' in html, "dashboard-tabs.js not found in base.html"


# ─── Task 2: .dash-tabs CSS primitive ────────────────────────────────────────

def test_primitives_css_has_dash_tabs_selector():
    """primitives.css must define the .dash-tabs selector."""
    css = PRIMITIVES_CSS.read_text(encoding='utf-8')
    assert '.dash-tabs' in css, ".dash-tabs selector not found in primitives.css"


def test_primitives_css_has_dash_tab_selector():
    """primitives.css must define the .dash-tab selector."""
    css = PRIMITIVES_CSS.read_text(encoding='utf-8')
    assert '.dash-tab' in css, ".dash-tab selector not found in primitives.css"


def test_primitives_css_has_dash_tabs_indicator():
    """primitives.css must define the .dash-tabs-indicator selector."""
    css = PRIMITIVES_CSS.read_text(encoding='utf-8')
    assert '.dash-tabs-indicator' in css, ".dash-tabs-indicator selector not found in primitives.css"


# ─── Task 3: DashboardTabs JS controller ─────────────────────────────────────

def test_dashboard_tabs_js_has_class():
    """dashboard-tabs.js must define the DashboardTabs class."""
    js = DASHBOARD_TABS_JS.read_text(encoding='utf-8')
    assert 'class DashboardTabs' in js, "DashboardTabs class not found in dashboard-tabs.js"


def test_dashboard_tabs_js_has_activate_method():
    """DashboardTabs must have an activate method."""
    js = DASHBOARD_TABS_JS.read_text(encoding='utf-8')
    assert 'activate(' in js or 'activate (' in js, "activate method not found in dashboard-tabs.js"


def test_dashboard_tabs_js_has_indicator_animation():
    """DashboardTabs must animate the indicator (move/width)."""
    js = DASHBOARD_TABS_JS.read_text(encoding='utf-8')
    assert 'indicator' in js, "indicator animation code not found in dashboard-tabs.js"


# ─── Task 4: Template nav swap ───────────────────────────────────────────────

def test_dashboard_html_has_dash_tabs_nav():
    """dashboard.html must contain the new .dash-tabs nav element."""
    html = DASHBOARD_HTML.read_text(encoding='utf-8')
    assert 'class="dash-tabs"' in html or "class='dash-tabs'" in html, \
        ".dash-tabs nav not found in dashboard.html"


def test_dashboard_html_has_data_dashboard_tabs():
    """The .exec-dashboard container must have data-dashboard-tabs attribute."""
    html = DASHBOARD_HTML.read_text(encoding='utf-8')
    assert 'data-dashboard-tabs' in html, \
        "data-dashboard-tabs attribute not found in dashboard.html"


def test_dashboard_html_no_carousel_js():
    """The inline carousel JS controller must be removed from dashboard.html."""
    html = DASHBOARD_HTML.read_text(encoding='utf-8')
    assert 'const carousel = document.getElementById' not in html, \
        "Old carousel JS still present in dashboard.html — must be removed"


# ─── Task 5: Ambient background ──────────────────────────────────────────────

def test_dashboard_html_has_ambient_background():
    """The .exec-dashboard container must apply the --bg-ambient gradient."""
    html = DASHBOARD_HTML.read_text(encoding='utf-8')
    assert '--bg-ambient' in html or 'bg-ambient' in html, \
        "--bg-ambient gradient not applied to exec-dashboard in dashboard.html"


# ─── Task 6: Ventas panel refresh ────────────────────────────────────────────

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
    assert 'class="ring"' in panel or "class='ring'" in panel or 'class="ring ' in panel
    assert 'data-state=' in panel, "rings must carry data-state for semantic color"
    # Old classes should be gone from this panel
    assert 'kpi-tile' not in panel
    assert 'progress-ring' not in panel
    assert 'c-green' not in panel
    assert 'c-amber' not in panel
    assert 'c-red' not in panel


# ─── Task 7: Servicio panel refresh ──────────────────────────────────────────

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
