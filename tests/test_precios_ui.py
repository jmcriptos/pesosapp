"""Smoke tests — migración de Precios (Tanda 5) al design system claro.
Spec: docs/superpowers/specs/2026-07-01-migracion-lote-oscuro-design.md

Asserts sobre ids/data-attrs, no markup exacto (evita el test rot documentado
en test_dashboard_kpis/test_etiquetas).
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
        from app import (
            Rol, Territorio, Vendedor, Cliente, Producto,
            ListaPrecio, PrecioProducto, PrecioClienteProducto, ClienteListaPrecio,
        )

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

        cliente = Cliente(nombre="Cliente Precios Uno", moneda="XCG")
        producto = Producto(nombre="Producto Precios Uno", proveedor="Prov Test", tax_rate=10)
        _db.session.add(cliente)
        _db.session.add(producto)
        _db.session.flush()

        lista_default = ListaPrecio(nombre="Lista General", descripcion="Default", es_default=True, activa=True)
        lista_custom = ListaPrecio(nombre="Lista Premium", descripcion="Custom", es_default=False, activa=True)
        _db.session.add(lista_default)
        _db.session.add(lista_custom)
        _db.session.flush()

        precio_prod = PrecioProducto(
            lista_precio_id=lista_default.id, producto_id=producto.id,
            precio_base=10.0, margen_jomar=1.0, margen_retail=1.2,
        )
        precio_prod.calcular_precios()
        _db.session.add(precio_prod)

        precio_esp = PrecioClienteProducto(
            cliente_id=cliente.id, producto_id=producto.id,
            precio_base=9.0, margen_jomar=1.0, margen_retail=1.2,
        )
        precio_esp.calcular_precios()
        _db.session.add(precio_esp)

        _db.session.add(ClienteListaPrecio(cliente_id=cliente.id, lista_precio_id=lista_custom.id, activa=True))

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


def _lista_default_id(app):
    with app.app_context():
        from app import ListaPrecio
        return ListaPrecio.query.filter_by(es_default=True).first().id


# ---------------------------------------------------------------------------
# Infraestructura compartida (base.html + precios.css)
# ---------------------------------------------------------------------------

PRECIOS_PATHS = [
    "/precios",
    "/precios/listas",
    "/precios/listas/nueva",
    "/precios/clientes",
    "/precios/cliente-producto",
    "/precios/carga-masiva",
]


@pytest.mark.parametrize("path", PRECIOS_PATHS)
def test_precios_route_returns_200(logged_client, path):
    response = logged_client.get(path)
    assert response.status_code == 200, f"{path} returned {response.status_code}"


@pytest.mark.parametrize("path", PRECIOS_PATHS)
def test_precios_css_is_linked(logged_client, path):
    response = logged_client.get(path)
    assert b"css/precios.css" in response.data, f"precios.css link missing from {path}"


@pytest.mark.parametrize("path", PRECIOS_PATHS)
def test_body_has_precios_screen_attr(logged_client, path):
    response = logged_client.get(path)
    assert b'data-precios-screen="1"' in response.data, (
        f"data-precios-screen missing from {path} body"
    )


@pytest.mark.parametrize("path", ["/dashboard", "/pedidos", "/clientes", "/productos"])
def test_non_precios_routes_lack_precios_attrs(logged_client, path):
    response = logged_client.get(path)
    assert b'data-precios-screen="1"' not in response.data
    assert b"css/precios.css" not in response.data


def test_precios_lista_productos_route(logged_client, app):
    lista_id = _lista_default_id(app)
    response = logged_client.get(f"/precios/listas/{lista_id}/productos")
    assert response.status_code == 200
    assert b'data-precios-screen="1"' in response.data
    assert b"css/precios.css" in response.data


# ---------------------------------------------------------------------------
# Hub (precios/index.html)
# ---------------------------------------------------------------------------


def test_hub_patron_claro(logged_client):
    html = logged_client.get("/precios").data
    assert b"precios-hub-grid" in html
    assert b"Lista General" not in html  # el hub no lista nombres, solo cuenta
    assert b"listas" in html  # contador "N listas"


# ---------------------------------------------------------------------------
# Listas (precios/listas.html)
# ---------------------------------------------------------------------------


def test_listas_patron_claro(logged_client):
    html = logged_client.get("/precios/listas").data
    assert b'id="btn-nueva-lista"' in html
    assert b"Lista General" in html
    assert b"Lista Premium" in html
    assert b"precios-list-card" in html


def test_listas_sin_legacy(logged_client):
    html = logged_client.get("/precios/listas").data
    assert b"#141820" not in html, "color legacy oscuro no debe quedar inline"


# ---------------------------------------------------------------------------
# Lista form (precios/lista_form.html)
# ---------------------------------------------------------------------------


def test_lista_form_nueva_patron_claro(logged_client):
    html = logged_client.get("/precios/listas/nueva").data
    assert b"mobile-card" in html
    assert b'name="nombre"' in html
    assert b'name="descripcion"' in html


def test_lista_form_editar_patron_claro(logged_client, app):
    lista_id = _lista_default_id(app)
    html = logged_client.get(f"/precios/listas/{lista_id}/editar").data
    assert b"mobile-card" in html
    assert b"Lista por defecto" in html or b"lista por defecto" in html.lower()


# ---------------------------------------------------------------------------
# Lista productos — tabla editable (precios/lista_productos.html)
# ---------------------------------------------------------------------------


def test_lista_productos_patron_claro(logged_client, app):
    lista_id = _lista_default_id(app)
    html = logged_client.get(f"/precios/listas/{lista_id}/productos").data
    assert b"precios-table" in html
    assert b"Producto Precios Uno" in html
    assert b'id="btn-guardar-todo"' in html
    assert b'id="btn-agregar-producto"' in html


# ---------------------------------------------------------------------------
# Precios por cliente (precios/clientes.html)
# ---------------------------------------------------------------------------


def test_precios_clientes_patron_claro(logged_client):
    html = logged_client.get("/precios/clientes").data
    assert b'id="form-asignar-lista"' in html
    assert b"Cliente Precios Uno" in html
    assert b'id="modal-precios-cliente"' in html


def test_precios_clientes_sin_jquery(logged_client):
    html = logged_client.get("/precios/clientes").data
    assert b"code.jquery.com" not in html, "precios/clientes.html ya no debe cargar jQuery CDN"


# ---------------------------------------------------------------------------
# Cliente-producto (precios/cliente_producto.html)
# ---------------------------------------------------------------------------


def test_cliente_producto_patron_claro(logged_client):
    html = logged_client.get("/precios/cliente-producto").data
    assert b'id="form-precio-especifico"' in html
    assert b"Cliente Precios Uno" in html
    assert b"Producto Precios Uno" in html


# ---------------------------------------------------------------------------
# Carga masiva (precios/carga_masiva.html)
# ---------------------------------------------------------------------------


def test_carga_masiva_patron_claro(logged_client):
    html = logged_client.get("/precios/carga-masiva").data
    assert b'id="form-carga-masiva"' in html
    assert b"Descargar Log" not in html, "link roto (endpoint inexistente) debe eliminarse"


# ---------------------------------------------------------------------------
# Código muerto eliminado
# ---------------------------------------------------------------------------


def test_pedido_form_precios_no_existe():
    import os
    path = os.path.join(
        os.path.dirname(os.path.dirname(__file__)),
        "templates", "precios", "pedido_form.html",
    )
    assert not os.path.exists(path), "templates/precios/pedido_form.html debía borrarse (código muerto)"
