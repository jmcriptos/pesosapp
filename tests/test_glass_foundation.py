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


def test_reduced_motion_override_present():
    css = _read_tokens()
    assert '@media (prefers-reduced-motion: reduce)' in css
    # Must disable animations globally
    rm_start = css.find('@media (prefers-reduced-motion: reduce)')
    rm_block = css[rm_start:rm_start + 1000]
    assert 'animation-duration: 0.01ms' in rm_block
    assert 'transition-duration: 0.01ms' in rm_block


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


def test_surface_helpers_defined():
    css = _read_primitives()
    for sel in ['.surface-solid', '.surface-glass', '.surface-sunken']:
        assert sel in css


def test_dev_primitives_renders_surfaces(logged_client):
    resp = logged_client.get('/dev/primitives')
    html = resp.data.decode('utf-8')
    for cls in ['surface-solid', 'surface-glass', 'surface-sunken']:
        assert cls in html


def test_layout_utilities_defined():
    css = _read_primitives()
    for sel in ['.stack', '.stack-1', '.stack-4', '.cluster',
                '.cluster-2', '.grid-auto']:
        assert sel in css


def test_skeleton_primitive_defined():
    css = _read_primitives()
    assert '.skeleton' in css
    assert '.skeleton-text' in css
    assert '.skeleton-title' in css
    assert '.skeleton-tile' in css
    assert '@keyframes' in css and 'skeleton' in css  # shimmer keyframe


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
