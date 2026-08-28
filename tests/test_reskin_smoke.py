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


def test_theme_toggle_is_gone(logged_client):
    """La app no lleva modo oscuro: el toggle se eliminó el 2026-08-28.

    Era además un control muerto en la práctica —el contenido de todas las
    pantallas está clavado en claro con `!important`, así que alternar
    `data-theme` solo cambiaba topbar y tabbar—, y un control visible que no
    hace nada le enseña al usuario a desconfiar de los otros.

    Ojo: esto NO es lo mismo que quitar `data-theme="dark"` del <body>, que
    sigue y debe seguir (ver test_body_has_reskin_data_attributes). Ese
    atributo es el marco fijo de la app, no una preferencia del usuario.
    """
    response = logged_client.get("/dashboard")
    assert b"js/theme-toggle.js" not in response.data, (
        "volvió a linkearse theme-toggle.js"
    )
    assert b"data-theme-toggle" not in response.data, (
        "volvió el botón de alternar tema"
    )
    assert b"Alternar tema" not in response.data


# ---------------------------------------------------------------------------
# Dashboard snap layout
# Spec: docs/superpowers/specs/2026-04-18-dashboard-snap-layout-design.md
# ---------------------------------------------------------------------------


def test_dashboard_snap_css_is_linked(logged_client):
    response = logged_client.get("/dashboard")
    assert b"css/dashboard_snap.css" in response.data, (
        "dashboard_snap.css link missing from /dashboard"
    )


def test_dashboard_snap_dots_js_is_linked(logged_client):
    response = logged_client.get("/dashboard")
    assert b"js/dashboard-snap-dots.js" in response.data, (
        "dashboard-snap-dots.js link missing from /dashboard"
    )


def test_dashboard_ventas_panel_has_snap_cards(logged_client):
    """Spec: 4 snap targets in Ventas (4 KPIs + chart + week mini = 6 total)."""
    response = logged_client.get("/dashboard")
    html = response.data
    # Coarse but reliable: count occurrences of the marker inside the rendered HTML.
    # Ventas panel has 4 KPIs + 1 chart + 1 week-mini = 6 snap cards minimum.
    # Servicio adds 6 more = 12 total.
    snap_card_count = html.count(b'data-snap-card="1"')
    assert snap_card_count >= 12, (
        "Expected at least 12 snap-card markers (Ventas 6 + Servicio 6); "
        f"found {snap_card_count}"
    )


def test_dashboard_snap_dots_slots_present(logged_client):
    response = logged_client.get("/dashboard")
    html = response.data
    assert b'data-snap-dots-for="ventas"' in html, "snap-dots slot for Ventas missing"
    assert b'data-snap-dots-for="servicio"' in html, "snap-dots slot for Servicio missing"
