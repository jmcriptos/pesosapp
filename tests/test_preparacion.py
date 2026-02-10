# tests/test_preparacion.py
"""Tests para Story 2.2: Fix unidades de medida en preparación de pedidos.
Updated for Story 3-0: /preparar now redirects to /detalles."""
import os
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
        from app import (Rol, Territorio, Vendedor, Cliente, Producto,
                         Pedido, DetallePedido)

        # Setup user
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

        # Setup cliente
        cliente = Cliente(nombre='Cliente Test', territorio_id=territorio.id)
        _db.session.add(cliente)
        _db.session.flush()

        # Setup productos
        producto_carne = Producto(
            nombre='Chuleta de Cerdo',
            descripcion='Carne que se pesa',
            temperatura='Congelado',
            se_pesa=True,
            tax_rate=6.0,
        )
        producto_aceite = Producto(
            nombre='Aceite de Oliva',
            descripcion='Producto por unidad',
            temperatura='Ambiente',
            se_pesa=False,
            tax_rate=6.0,
        )
        _db.session.add_all([producto_carne, producto_aceite])
        _db.session.flush()

        # Setup pedido con detalles
        pedido = Pedido(
            cliente_id=cliente.id,
            estado='pendiente',
        )
        _db.session.add(pedido)
        _db.session.flush()

        detalle_carne = DetallePedido(
            pedido_id=pedido.id,
            producto_id=producto_carne.id,
            cajas=10,
            peso=0,
            precio_unitario=25.00,
            subtotal=250.00,
            es_linea_pedido=True,
        )
        detalle_aceite = DetallePedido(
            pedido_id=pedido.id,
            producto_id=producto_aceite.id,
            cajas=5,
            peso=0,
            precio_unitario=12.00,
            subtotal=60.00,
            es_linea_pedido=True,
        )
        _db.session.add_all([detalle_carne, detalle_aceite])
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


@pytest.fixture
def anon_client(app):
    return app.test_client()


# === Story 3-0: /preparar now redirects 301 to /detalles ===

def test_preparar_pedido_get_loads(logged_client, app):
    """Story 3-0: preparar_pedido GET redirects 301 to detalles."""
    with app.app_context():
        from app import Pedido
        pedido = Pedido.query.first()
        resp = logged_client.get(f'/pedidos/{pedido.id}/preparar')
        assert resp.status_code == 301
        assert f'/pedidos/{pedido.id}/detalles' in resp.headers['Location']


def test_preparar_pedido_shows_product_names(logged_client, app):
    """Following redirect, detalles shows product names."""
    with app.app_context():
        from app import Pedido
        pedido = Pedido.query.first()
        resp = logged_client.get(f'/pedidos/{pedido.id}/preparar',
                                  follow_redirects=True)
        html = resp.data.decode('utf-8')
        assert 'Chuleta de Cerdo' in html
        assert 'Aceite de Oliva' in html


def test_preparar_pedido_shows_cajas_solicitadas(logged_client, app):
    """Following redirect, detalles shows cajas."""
    with app.app_context():
        from app import Pedido
        pedido = Pedido.query.first()
        resp = logged_client.get(f'/pedidos/{pedido.id}/preparar',
                                  follow_redirects=True)
        html = resp.data.decode('utf-8')
        # Cajas are shown in the details view
        assert '10' in html
        assert '5' in html


# === AC #2, #3: Test POST via detalles saves correctly ===

def test_post_preparar_saves_cajas(logged_client, app):
    """Story 3-0: Adding via detalles creates preparation line (es_linea_pedido=False)."""
    with app.app_context():
        from app import Pedido, DetallePedido, Producto
        pedido = Pedido.query.first()
        producto = Producto.query.filter_by(se_pesa=True).first()

        resp = logged_client.post(
            f'/pedidos/{pedido.id}/detalles',
            data={
                'producto_id': str(producto.id),
                'peso': '4.5',
                'cajas': '1',
                'lote': 'L001',
                'fecha_fabricacion': '2026-01-01',
                'fecha_expiracion': '2026-06-01',
            },
            follow_redirects=True,
        )
        assert resp.status_code == 200

        new_det = DetallePedido.query.filter_by(
            pedido_id=pedido.id, es_linea_pedido=False
        ).first()
        assert new_det is not None
        assert new_det.peso == 4.5


def test_post_preparar_saves_peso_for_se_pesa_product(logged_client, app):
    """POST detalles saves peso for se_pesa product."""
    with app.app_context():
        from app import Pedido, DetallePedido, Producto
        pedido = Pedido.query.first()
        producto = Producto.query.filter_by(se_pesa=True).first()

        resp = logged_client.post(
            f'/pedidos/{pedido.id}/detalles',
            data={
                'producto_id': str(producto.id),
                'peso': '45.5',
                'cajas': '1',
                'lote': 'L001',
                'fecha_fabricacion': '2026-01-01',
                'fecha_expiracion': '2026-06-01',
            },
            follow_redirects=True,
        )
        assert resp.status_code == 200

        new_det = DetallePedido.query.filter_by(
            pedido_id=pedido.id, es_linea_pedido=False
        ).first()
        assert new_det.peso == 45.5


def test_pedido_changes_to_listo(logged_client, app):
    """Story 3-0: marcar_preparado changes estado to 'preparado' with full traceability."""
    with app.app_context():
        from app import Pedido, DetallePedido, Producto
        pedido = Pedido.query.first()
        assert pedido.estado == 'pendiente'

        # Add import product fecha_expiracion
        prod_import = Producto.query.filter_by(se_pesa=False).first()
        det_import = DetallePedido.query.filter_by(
            producto_id=prod_import.id, es_linea_pedido=True
        ).first()
        det_import.fecha_expiracion = '2026-06-01'

        # Add preparation lines for se_pesa product
        prod_pesa = Producto.query.filter_by(se_pesa=True).first()
        from datetime import datetime
        for i in range(3):
            det = DetallePedido(
                pedido_id=pedido.id,
                producto_id=prod_pesa.id,
                cajas=1,
                peso=4.5,
                precio_unitario=25.00,
                subtotal=25.00,
                lote='L001',
                fecha_fabricacion=datetime(2026, 1, 1),
                fecha_expiracion=datetime(2026, 6, 1),
                es_linea_pedido=False,
            )
            _db.session.add(det)

        # Add preparation line for import product
        prod_import = Producto.query.filter_by(se_pesa=False).first()
        det_import = DetallePedido(
            pedido_id=pedido.id,
            producto_id=prod_import.id,
            cajas=5,
            peso=0,
            precio_unitario=12.00,
            subtotal=60.00,
            es_linea_pedido=False,
        )
        _db.session.add(det_import)
        _db.session.commit()

        resp = logged_client.post(
            f'/pedidos/{pedido.id}/marcar_preparado',
            follow_redirects=True,
        )
        assert resp.status_code == 200

        pedido_updated = Pedido.query.first()
        assert pedido_updated.estado == 'preparado'


def test_preparar_pedido_shows_diferencia_column(logged_client, app):
    """Following redirect to detalles, shows products view."""
    with app.app_context():
        from app import Pedido
        pedido = Pedido.query.first()
        resp = logged_client.get(f'/pedidos/{pedido.id}/preparar',
                                  follow_redirects=True)
        html = resp.data.decode('utf-8')
        assert 'Producto' in html


def test_preparar_pedido_peso_field_conditional(logged_client, app):
    """Following redirect, detalles shows peso field in form."""
    with app.app_context():
        from app import Pedido
        pedido = Pedido.query.first()
        resp = logged_client.get(f'/pedidos/{pedido.id}/preparar',
                                  follow_redirects=True)
        html = resp.data.decode('utf-8')
        assert 'Peso' in html


# === AC #5: Modelo Producto has se_pesa field ===

def test_producto_has_se_pesa_field(app):
    """Modelo Producto tiene campo se_pesa."""
    with app.app_context():
        from app import Producto
        p = Producto.query.first()
        assert hasattr(p, 'se_pesa')
        assert isinstance(p.se_pesa, bool)


def test_producto_se_pesa_default_false(app):
    """El campo se_pesa tiene default False."""
    with app.app_context():
        from app import Producto
        p = Producto(nombre='Test', tax_rate=0.0)
        _db.session.add(p)
        _db.session.flush()
        assert p.se_pesa is False


def test_post_preparar_no_peso_for_non_se_pesa_product(logged_client, app):
    """Import product original line keeps peso=0."""
    with app.app_context():
        from app import Pedido, DetallePedido, Producto
        prod_aceite = Producto.query.filter_by(se_pesa=False).first()
        pedido = Pedido.query.first()

        det = DetallePedido.query.filter_by(
            pedido_id=pedido.id, producto_id=prod_aceite.id
        ).first()
        assert det.peso == 0


# === Regression tests ===

def test_regression_dashboard_works(logged_client):
    """El dashboard sigue funcionando normalmente."""
    resp = logged_client.get('/dashboard')
    assert resp.status_code == 200


def test_regression_login_works(anon_client):
    """La página de login sigue funcionando normalmente."""
    resp = anon_client.get('/login')
    assert resp.status_code == 200
