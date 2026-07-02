"""Smoke tests — migración del lote oscuro al design system claro (Tanda 1).
Spec: docs/superpowers/specs/2026-07-01-migracion-lote-oscuro-design.md

A propósito se asserta sobre ids y data-attributes (no markup exacto) para
no repetir el "test rot" de test_dashboard_kpis/test_etiquetas.
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
        from app import Rol, Territorio, Vendedor, Cliente, Producto

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
        _db.session.add(Cliente(nombre="Cliente Uno", moneda="USD", qbo_id="QBO-77"))
        _db.session.add(
            Producto(nombre="Producto Uno", proveedor="Prov Test", se_pesa=True, tax_rate=10)
        )
        _db.session.commit()

        yield flask_app
        _db.drop_all()


@pytest.fixture
def logged_client(app):
    client = app.test_client()
    client.post(
        "/login",
        data={"username": "admin", "password": "testpass"},
        follow_redirects=True,
    )
    return client


# ---------------------------------------------------------------------------
# Infraestructura compartida (base.html + gestion.css)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("path", ["/clientes", "/productos"])
def test_gestion_route_returns_200(logged_client, path):
    response = logged_client.get(path)
    assert response.status_code == 200, f"{path} returned {response.status_code}"


@pytest.mark.parametrize("path", ["/clientes", "/productos"])
def test_gestion_css_is_linked(logged_client, path):
    response = logged_client.get(path)
    assert b"css/gestion.css" in response.data, f"gestion.css link missing from {path}"


@pytest.mark.parametrize("path", ["/clientes", "/productos"])
def test_body_has_gestion_screen_attr(logged_client, path):
    response = logged_client.get(path)
    assert b'data-gestion-screen="1"' in response.data, (
        f"data-gestion-screen missing from {path} body"
    )


@pytest.mark.parametrize("path", ["/dashboard", "/pedidos"])
def test_non_gestion_routes_lack_gestion_attrs(logged_client, path):
    """El scope claro NO debe filtrarse a pantallas que no son de gestión."""
    response = logged_client.get(path)
    assert b'data-gestion-screen="1"' not in response.data
    assert b"css/gestion.css" not in response.data
