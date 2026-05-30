"""Tests para productos importados (no-pesables) en la pantalla de detalles:

1. Al eliminar un producto importado debe borrarse TANTO la línea original
   (es_linea_pedido=True) COMO la línea de preparación (es_linea_pedido=False),
   de modo que el producto deje de aparecer en la factura (pedido_a_json).
2. pedido_a_json no debe emitir una línea de preparación huérfana (sin línea
   original correspondiente) — defensa en profundidad para datos antiguos.
3. Al editar la cantidad de un producto importado, la línea original y la de
   preparación quedan sincronizadas (cajas/subtotal) y pedido_a_json refleja
   la nueva cantidad.
"""
import os
from decimal import Decimal

import pytest

os.environ.setdefault('SECRET_KEY', 'test-secret')
os.environ.setdefault('FLASK_ENV', 'testing')
os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')

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
        _seed_base()
        yield flask_app
        _db.drop_all()


@pytest.fixture
def logged_client(app):
    client = app.test_client()
    client.post('/login', data={'username': 'admin', 'password': 'testpass'},
                follow_redirects=True)
    return client


def _seed_base():
    from app import Rol, Territorio, Vendedor, Cliente, Producto
    rol = Rol(nombre='super_admin', descripcion='Admin')
    _db.session.add(rol)
    territorio = Territorio(nombre='t1', descripcion='T1')
    _db.session.add(territorio)
    _db.session.flush()

    vendedor = Vendedor(username='admin', email='a@test.com',
                        nombre_completo='Admin', rol_id=rol.id,
                        territorio_id=territorio.id, activo=True)
    vendedor.set_password('testpass')
    _db.session.add(vendedor)

    cliente = Cliente(nombre='Cliente QBO', territorio_id=territorio.id,
                      qbo_id='QBO-C1', moneda='XCG')
    _db.session.add(cliente)

    # Producto importado (no se pesa)
    producto = Producto(nombre='Maíz Enlatado', descripcion='Importado',
                        temperatura='Seco', se_pesa=False, tax_rate=6.0,
                        qbo_id='QBO-IMP1')
    _db.session.add(producto)
    _db.session.flush()


def _build_pedido_importado(cajas=10, precio='5.00'):
    """Crea un pedido importado tal como lo deja editar_pedido:
    una línea original (es_linea_pedido=True) y una línea de preparación
    (es_linea_pedido=False) para el mismo producto. Devuelve
    (pedido_id, original_id, prep_id, producto_id)."""
    from app import Cliente, Producto, Pedido, DetallePedido

    cliente = Cliente.query.first()
    producto = Producto.query.filter_by(se_pesa=False).first()
    precio_dec = Decimal(precio)

    pedido = Pedido(cliente_id=cliente.id, estado='preparado', tipo_cambio=1.0)
    _db.session.add(pedido)
    _db.session.flush()

    original = DetallePedido(
        pedido_id=pedido.id, producto_id=producto.id,
        cajas=cajas, cajas_pedidas=cajas, peso=0,
        precio_unitario=precio_dec, subtotal=precio_dec * cajas,
        es_linea_pedido=True,
    )
    prep = DetallePedido(
        pedido_id=pedido.id, producto_id=producto.id,
        cajas=cajas, cajas_pedidas=0, peso=0,
        precio_unitario=precio_dec, subtotal=precio_dec * cajas,
        fecha_expiracion='2026-12-31',
        es_linea_pedido=False,
    )
    _db.session.add_all([original, prep])
    _db.session.commit()
    return pedido.id, original.id, prep.id, producto.id


# ── 1) Bug: eliminar producto importado lo saca de la factura ──────────────

def test_eliminar_importado_borra_ambas_filas(logged_client, app):
    from app import DetallePedido

    with app.app_context():
        pedido_id, original_id, prep_id, producto_id = _build_pedido_importado()

    # El botón de la tarjeta envía el id de la línea ORIGINAL
    resp = logged_client.post(f'/detalles_pedido/{original_id}/eliminar',
                              follow_redirects=True)
    assert resp.status_code == 200

    with app.app_context():
        restantes = DetallePedido.query.filter_by(
            pedido_id=pedido_id, producto_id=producto_id).all()
        assert restantes == [], (
            f"Tras eliminar deben borrarse ambas filas; quedaron {len(restantes)}"
        )


def test_factura_no_incluye_producto_eliminado(logged_client, app):
    from app import Pedido, pedido_a_json

    with app.app_context():
        pedido_id, original_id, prep_id, producto_id = _build_pedido_importado()

    logged_client.post(f'/detalles_pedido/{original_id}/eliminar',
                       follow_redirects=True)

    with app.app_context():
        pedido = _db.session.get(Pedido, pedido_id)
        payload = pedido_a_json(pedido)
        qbo_ids = [l['product_qbo_id'] for l in payload['lines']]
        assert 'QBO-IMP1' not in qbo_ids, (
            f"El producto eliminado no debe facturarse; payload={payload['lines']}"
        )
        assert payload['lines'] == []
        assert payload['total'] == 0


# ── 2) Defensa: prep huérfana (sin línea original) no se factura ───────────

def test_pedido_a_json_ignora_prep_huerfana(app):
    from app import DetallePedido, Pedido, pedido_a_json

    with app.app_context():
        pedido_id, original_id, prep_id, producto_id = _build_pedido_importado()
        # Simular estado roto previo: existe la prep pero no la línea original
        original = _db.session.get(DetallePedido, original_id)
        _db.session.delete(original)
        _db.session.commit()

        pedido = _db.session.get(Pedido, pedido_id)
        payload = pedido_a_json(pedido)
        assert payload['lines'] == [], (
            f"Una prep sin línea original no debe facturarse; {payload['lines']}"
        )


# ── 3) Editar cantidad de importado sincroniza filas + factura ─────────────

def test_editar_cantidad_importado_sincroniza(logged_client, app):
    from app import DetallePedido, Pedido, pedido_a_json

    with app.app_context():
        pedido_id, original_id, prep_id, producto_id = _build_pedido_importado(
            cajas=10, precio='5.00')

    # El modal "Editar" envía el id de la línea PREP, con cajas en el campo peso
    resp = logged_client.post(
        f'/detalles_pedido/{prep_id}/editar',
        data={'producto_id': producto_id, 'peso': '4',
              'fecha_expiracion': '2026-12-31'},
        follow_redirects=True,
    )
    assert resp.status_code == 200

    with app.app_context():
        prep = _db.session.get(DetallePedido, prep_id)
        original = _db.session.get(DetallePedido, original_id)
        assert prep.cajas == 4
        # La línea original (la que muestra la tarjeta) debe quedar sincronizada
        assert original.cajas == 4, "La tarjeta seguiría mostrando la cantidad vieja"
        assert original.cajas_pedidas == 4

        pedido = _db.session.get(Pedido, pedido_id)
        payload = pedido_a_json(pedido)
        assert len(payload['lines']) == 1
        assert payload['lines'][0]['qty'] == 4
        assert payload['total'] == 20.0
