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
