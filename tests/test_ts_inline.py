"""Todo `select.ts-select` del auto-init de base.html cuelga su lista del
propio campo (`data-ts-inline`), no de <body>.

Montada en <body>, Tom Select posiciona la lista con `rect.top +
window.scrollY`; en iPhone, al subir el teclado, esas cifras dejan de ser
coherentes y la lista queda descolgada o fuera de pantalla (medido con un
panel ?tsdebug el 2026-10-14 en Nuevo lote; mismo auto-init en todas estas
pantallas). Si una pantalla nueva necesita quedarse en <body> (tarjeta con
overflow hidden), que lo diga en el template y se excluya acá con motivo.
"""
import os
import re

import pytest

os.environ.setdefault("SECRET_KEY", "test-secret")
os.environ.setdefault("FLASK_ENV", "testing")
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

from app import app as flask_app, db as _db

IDS = {}


@pytest.fixture
def client():
    flask_app.config.update(TESTING=True, WTF_CSRF_ENABLED=False,
                            SQLALCHEMY_DATABASE_URI="sqlite:///:memory:")
    with flask_app.app_context():
        _db.create_all()
        from app import (Rol, Territorio, Vendedor, Cliente, Producto,
                         ListaPrecio, Pedido, DetallePedido)
        rol = Rol(nombre="super_admin", descripcion="Admin")
        terr = Territorio(nombre="t", descripcion="T")
        _db.session.add_all([rol, terr])
        _db.session.flush()
        admin = Vendedor(username="admin", email="a@t.com", nombre_completo="Admin",
                         rol_id=rol.id, territorio_id=terr.id, activo=True)
        admin.set_password("pw")
        cliente = Cliente(nombre="Cliente Uno", moneda="XCG")
        producto = Producto(nombre="Producto Uno", tax_rate=10)
        lista = ListaPrecio(nombre="General", descripcion="Default", es_default=True, activa=True)
        _db.session.add_all([admin, cliente, producto, lista])
        _db.session.flush()
        pedido = Pedido(cliente_id=cliente.id, estado="pendiente")
        _db.session.add(pedido)
        _db.session.flush()
        _db.session.add(DetallePedido(pedido_id=pedido.id, producto_id=producto.id,
                                      cajas=1, peso=0, precio_unitario=1, subtotal=1))
        _db.session.commit()
        IDS.update(producto=producto.id, lista=lista.id, pedido=pedido.id)
        c = flask_app.test_client()
        c.post("/login", data={"username": "admin", "password": "pw"}, follow_redirects=True)
        yield c
        _db.drop_all()


SELECT_RE = re.compile(r'<select\b[^>]*\bclass="[^"]*\bts-select\b[^"]*"[^>]*>')


def _paths():
    return [
        "/precios/clientes",
        "/precios/cliente-producto",
        "/precios/carga-masiva",
        f"/precios/listas/{IDS['lista']}/productos",
        "/etiquetas_vencimiento",
        f"/productos/{IDS['producto']}/editar",
        f"/pedidos/{IDS['pedido']}/detalles",   # modal de edición de línea
    ]


def test_todo_ts_select_cuelga_del_campo(client):
    sin_inline = []
    vistos = 0
    for path in _paths():
        r = client.get(path)
        assert r.status_code == 200, (path, r.status_code)
        tags = SELECT_RE.findall(r.get_data(as_text=True))
        assert tags, f"{path}: no se encontró ningún select.ts-select"
        for tag in tags:
            vistos += 1
            if "data-ts-inline" not in tag and "data-no-auto-ts" not in tag:
                sin_inline.append((path, tag[:80]))
    assert vistos >= 8
    assert not sin_inline, sin_inline
