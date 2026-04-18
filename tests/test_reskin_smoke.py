"""Smoke tests for the Glass Mobile Reskin.
Spec: docs/superpowers/specs/2026-04-17-glass-mobile-reskin-design.md

Verifies that reskinned routes return 200 and include the expected
CSS/JS asset links and body data-attributes injected by the reskin.
"""

import os
import pytest

os.environ.setdefault("SECRET_KEY", "test-secret")
os.environ.setdefault("FLASK_ENV", "testing")
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

from app import app as flask_app, db as _db


@pytest.fixture
def app():
    flask_app.config.update(
        TESTING=True,
        WTF_CSRF_ENABLED=False,
        SQLALCHEMY_DATABASE_URI="sqlite:///:memory:",
    )
    with flask_app.app_context():
        _db.create_all()
        from app import Rol, Territorio, Vendedor

        rol = Rol(nombre="super_admin", descripcion="Admin")
        _db.session.add(rol)
        territorio = Territorio(nombre="test", descripcion="Test")
        _db.session.add(territorio)
        _db.session.flush()

        vendedor = Vendedor(
            username="admin",
            email="admin@test.com",
            nombre_completo="Admin Test",
            rol_id=rol.id,
            territorio_id=territorio.id,
            activo=True,
        )
        vendedor.set_password("testpass")
        _db.session.add(vendedor)
        _db.session.commit()

        yield flask_app
        _db.drop_all()


@pytest.fixture
def logged_client(app):
    """Authenticated test client — mirrors the pattern used in test_dashboard_kpis.py."""
    client = app.test_client()
    client.post(
        "/login",
        data={"username": "admin", "password": "testpass"},
        follow_redirects=True,
    )
    return client


# ---------------------------------------------------------------------------
# Route availability
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("path", ["/dashboard", "/pedidos"])
def test_reskin_routes_return_200(logged_client, path):
    response = logged_client.get(path)
    assert response.status_code == 200, f"{path} returned {response.status_code}"


# ---------------------------------------------------------------------------
# CSS asset link
# ---------------------------------------------------------------------------


def test_app_mobile_css_is_linked(logged_client):
    response = logged_client.get("/dashboard")
    assert b"css/app-mobile.css" in response.data, (
        "app-mobile.css link missing from /dashboard"
    )


# ---------------------------------------------------------------------------
# Body data-attributes injected by the reskin
# ---------------------------------------------------------------------------


def test_body_has_reskin_data_attributes(logged_client):
    response = logged_client.get("/dashboard")
    html = response.data
    assert b'data-theme="dark"' in html, "data-theme=\"dark\" missing from /dashboard body"
    assert b'data-hue="blue"' in html, "data-hue=\"blue\" missing from /dashboard body"
    assert b'data-glass="heavy"' in html, "data-glass=\"heavy\" missing from /dashboard body"
    assert b'data-kpi-style="minimal"' in html, (
        "data-kpi-style=\"minimal\" missing from /dashboard body"
    )


# ---------------------------------------------------------------------------
# JS asset link
# ---------------------------------------------------------------------------


def test_theme_toggle_script_is_linked(logged_client):
    response = logged_client.get("/dashboard")
    assert b"js/theme-toggle.js" in response.data, (
        "theme-toggle.js link missing from /dashboard"
    )
