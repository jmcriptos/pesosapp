# tests/test_ofr.py
"""Tests para OFR (Order Fill Rate) real por cajas."""
import os
import pytest
from datetime import datetime, timezone

os.environ.setdefault('SECRET_KEY', 'test-secret')
os.environ.setdefault('FLASK_ENV', 'testing')
os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')

from app import app as flask_app, db as _db


@pytest.fixture
def app():
    flask_app.config.update(
        TESTING=True, WTF_CSRF_ENABLED=False,
        SQLALCHEMY_DATABASE_URI='sqlite:///:memory:',
    )
    with flask_app.app_context():
        _db.create_all()
        from app import (Rol, Territorio, Vendedor, Cliente, Producto)

        rol = Rol(nombre='super_admin', descripcion='Admin')
        _db.session.add(rol)
        territorio = Territorio(nombre='test', descripcion='Test')
        _db.session.add(territorio)
        _db.session.flush()

        vendedor = Vendedor(
            username='admin', email='admin@test.com',
            nombre_completo='Admin Test',
            rol_id=rol.id, territorio_id=territorio.id, activo=True,
        )
        vendedor.set_password('testpass')
        _db.session.add(vendedor)

        cliente = Cliente(nombre='Cliente Test', territorio_id=territorio.id,
                          qbo_id='QBO-C001')
        _db.session.add(cliente)
        _db.session.flush()

        prod_manuf = Producto(
            nombre='Smoked Chicken Ham', descripcion='Carne',
            temperatura='Congelado', se_pesa=True, tax_rate=6.0, qbo_id='QBO-P001',
        )
        _db.session.add(prod_manuf)

        prod_import = Producto(
            nombre='Aceite Oliva', descripcion='Aceite',
            temperatura='Ambiente', se_pesa=False, tax_rate=0.0, qbo_id='QBO-P002',
        )
        _db.session.add(prod_import)
        _db.session.commit()

        yield flask_app
        _db.drop_all()


@pytest.fixture
def logged_client(app):
    client = app.test_client()
    client.post('/login', data={
        'username': 'admin', 'password': 'testpass',
    }, follow_redirects=True)
    return client


def _get_ids(session):
    """Helper to get entity IDs after fixture setup."""
    from app import Cliente, Producto
    cliente = Cliente.query.first()
    prod_manuf = Producto.query.filter_by(se_pesa=True).first()
    prod_import = Producto.query.filter_by(se_pesa=False).first()
    return cliente, prod_manuf, prod_import


def test_ofr_100_percent_manufactura(logged_client, app):
    """OFR = 100% cuando todas las cajas de manufactura tienen líneas de prep."""
    with app.app_context():
        from app import Pedido, DetallePedido
        cliente, prod_manuf, _ = _get_ids(_db.session)

        pedido = Pedido(cliente_id=cliente.id, estado='facturado',
                        fecha_facturacion=datetime.now(timezone.utc))
        _db.session.add(pedido)
        _db.session.flush()

        _db.session.add(DetallePedido(
            pedido_id=pedido.id, producto_id=prod_manuf.id,
            cajas=3, cajas_pedidas=3, peso=0,
            precio_unitario=25, subtotal=75, es_linea_pedido=True,
        ))
        for i in range(3):
            _db.session.add(DetallePedido(
                pedido_id=pedido.id, producto_id=prod_manuf.id,
                cajas=1, cajas_pedidas=0, peso=2.5,
                precio_unitario=25, subtotal=25, es_linea_pedido=False,
                lote='L001', fecha_fabricacion='2026-01-01',
                fecha_expiracion='2026-06-01',
            ))
        _db.session.commit()

        resp = logged_client.get('/dashboard')
        assert resp.status_code == 200
        html = resp.data.decode('utf-8')
        assert 'Order Fill Rate' in html
        assert '100.0%' in html


def test_ofr_partial_manufactura(logged_client, app):
    """OFR parcial cuando faltan líneas de prep para manufactura."""
    with app.app_context():
        from app import Pedido, DetallePedido
        cliente, prod_manuf, _ = _get_ids(_db.session)

        pedido = Pedido(cliente_id=cliente.id, estado='facturado',
                        fecha_facturacion=datetime.now(timezone.utc))
        _db.session.add(pedido)
        _db.session.flush()

        _db.session.add(DetallePedido(
            pedido_id=pedido.id, producto_id=prod_manuf.id,
            cajas=5, cajas_pedidas=5, peso=0,
            precio_unitario=25, subtotal=125, es_linea_pedido=True,
        ))
        for i in range(3):
            _db.session.add(DetallePedido(
                pedido_id=pedido.id, producto_id=prod_manuf.id,
                cajas=1, cajas_pedidas=0, peso=2.5,
                precio_unitario=25, subtotal=25, es_linea_pedido=False,
                lote='L001', fecha_fabricacion='2026-01-01',
                fecha_expiracion='2026-06-01',
            ))
        _db.session.commit()

        resp = logged_client.get('/dashboard')
        html = resp.data.decode('utf-8')
        assert '60.0%' in html


def test_ofr_zero_manufactura(logged_client, app):
    """OFR = 0% cuando no se prepara nada de manufactura."""
    with app.app_context():
        from app import Pedido, DetallePedido
        cliente, prod_manuf, _ = _get_ids(_db.session)

        pedido = Pedido(cliente_id=cliente.id, estado='facturado',
                        fecha_facturacion=datetime.now(timezone.utc))
        _db.session.add(pedido)
        _db.session.flush()

        _db.session.add(DetallePedido(
            pedido_id=pedido.id, producto_id=prod_manuf.id,
            cajas=4, cajas_pedidas=4, peso=0,
            precio_unitario=25, subtotal=100, es_linea_pedido=True,
        ))
        _db.session.commit()

        resp = logged_client.get('/dashboard')
        html = resp.data.decode('utf-8')
        assert '0.0%' in html


def test_ofr_importacion_partial(logged_client, app):
    """OFR parcial para importación: prep lines cajas < cajas_pedidas."""
    with app.app_context():
        from app import Pedido, DetallePedido
        cliente, _, prod_import = _get_ids(_db.session)

        pedido = Pedido(cliente_id=cliente.id, estado='facturado',
                        fecha_facturacion=datetime.now(timezone.utc))
        _db.session.add(pedido)
        _db.session.flush()

        # Original order line: 10 cajas pedidas
        _db.session.add(DetallePedido(
            pedido_id=pedido.id, producto_id=prod_import.id,
            cajas=10, cajas_pedidas=10, peso=0,
            precio_unitario=15, subtotal=150, es_linea_pedido=True,
        ))
        # Prep line: only 7 cajas delivered
        _db.session.add(DetallePedido(
            pedido_id=pedido.id, producto_id=prod_import.id,
            cajas=7, cajas_pedidas=0, peso=0,
            precio_unitario=15, subtotal=105, es_linea_pedido=False,
        ))
        _db.session.commit()

        resp = logged_client.get('/dashboard')
        html = resp.data.decode('utf-8')
        assert '70.0%' in html


def test_ofr_mixed_products(logged_client, app):
    """OFR con mezcla de manufactura e importación."""
    with app.app_context():
        from app import Pedido, DetallePedido
        cliente, prod_manuf, prod_import = _get_ids(_db.session)

        pedido = Pedido(cliente_id=cliente.id, estado='facturado',
                        fecha_facturacion=datetime.now(timezone.utc))
        _db.session.add(pedido)
        _db.session.flush()

        # Manufactura: 4 pedidas, 2 entregadas
        _db.session.add(DetallePedido(
            pedido_id=pedido.id, producto_id=prod_manuf.id,
            cajas=4, cajas_pedidas=4, peso=0,
            precio_unitario=25, subtotal=100, es_linea_pedido=True,
        ))
        for i in range(2):
            _db.session.add(DetallePedido(
                pedido_id=pedido.id, producto_id=prod_manuf.id,
                cajas=1, cajas_pedidas=0, peso=2.5,
                precio_unitario=25, subtotal=25, es_linea_pedido=False,
                lote='L001', fecha_fabricacion='2026-01-01',
                fecha_expiracion='2026-06-01',
            ))

        # Importación: 6 pedidas, 6 entregadas (100%)
        _db.session.add(DetallePedido(
            pedido_id=pedido.id, producto_id=prod_import.id,
            cajas=6, cajas_pedidas=6, peso=0,
            precio_unitario=15, subtotal=90, es_linea_pedido=True,
        ))
        # Import prep line: 6 cajas
        _db.session.add(DetallePedido(
            pedido_id=pedido.id, producto_id=prod_import.id,
            cajas=6, cajas_pedidas=0, peso=0,
            precio_unitario=15, subtotal=90, es_linea_pedido=False,
        ))
        _db.session.commit()

        resp = logged_client.get('/dashboard')
        html = resp.data.decode('utf-8')
        # Manufactura: 2/4, Importación: 6/6 → total: 8/10 = 80%
        assert '80.0%' in html


def test_cajas_pedidas_set_on_creation(logged_client, app):
    """cajas_pedidas se fija al crear un pedido nuevo."""
    with app.app_context():
        from app import DetallePedido, Producto
        prod_manuf = Producto.query.filter_by(se_pesa=True).first()
        from app import Cliente
        cliente = Cliente.query.first()

        resp = logged_client.post('/pedidos/nuevo', data={
            'cliente_id': cliente.id,
            'productos[0][id]': prod_manuf.id,
            'productos[0][cajas]': '5',
        }, follow_redirects=True)
        assert resp.status_code == 200

        detalle = DetallePedido.query.filter_by(
            producto_id=prod_manuf.id, es_linea_pedido=True
        ).first()
        assert detalle is not None
        assert detalle.cajas_pedidas == 5
        assert detalle.cajas == 5


def test_import_prep_lines_auto_generated(logged_client, app):
    """Import products auto-generate a prep line (es_linea_pedido=False) on order creation."""
    with app.app_context():
        from app import DetallePedido, Producto, Cliente
        prod_import = Producto.query.filter_by(se_pesa=False).first()
        cliente = Cliente.query.first()

        resp = logged_client.post('/pedidos/nuevo', data={
            'cliente_id': cliente.id,
            'productos[0][id]': prod_import.id,
            'productos[0][cajas]': '8',
        }, follow_redirects=True)
        assert resp.status_code == 200

        # Original line
        orig = DetallePedido.query.filter_by(
            producto_id=prod_import.id, es_linea_pedido=True
        ).first()
        assert orig is not None
        assert orig.cajas == 8
        assert orig.cajas_pedidas == 8

        # Auto-generated prep line
        prep = DetallePedido.query.filter_by(
            producto_id=prod_import.id, es_linea_pedido=False
        ).first()
        assert prep is not None
        assert prep.cajas == 8
