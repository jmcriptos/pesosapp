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
