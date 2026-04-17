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
