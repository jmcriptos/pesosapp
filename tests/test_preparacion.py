# tests/test_preparacion.py
"""Tests para Story 2.2: Fix unidades de medida en preparación de pedidos."""
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
        )
        detalle_aceite = DetallePedido(
            pedido_id=pedido.id,
            producto_id=producto_aceite.id,
            cajas=5,
            peso=0,
            precio_unitario=12.00,
            subtotal=60.00,
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


# === AC #1, #2: Test preparar_pedido GET loads correctly ===

def test_preparar_pedido_get_loads(logged_client, app):
    """AC #1: preparar_pedido carga para pedido válido (200)."""
    with app.app_context():
        from app import Pedido
        pedido = Pedido.query.first()
        resp = logged_client.get(f'/pedidos/{pedido.id}/preparar')
        assert resp.status_code == 200


def test_preparar_pedido_shows_product_names(logged_client, app):
    """AC #1: La vista muestra nombres de productos."""
    with app.app_context():
        from app import Pedido
        pedido = Pedido.query.first()
        resp = logged_client.get(f'/pedidos/{pedido.id}/preparar')
        html = resp.data.decode('utf-8')
        assert 'Chuleta de Cerdo' in html
        assert 'Aceite de Oliva' in html


def test_preparar_pedido_shows_cajas_solicitadas(logged_client, app):
    """AC #1: La vista muestra cantidad pedida con unidad original."""
    with app.app_context():
        from app import Pedido
        pedido = Pedido.query.first()
        resp = logged_client.get(f'/pedidos/{pedido.id}/preparar')
        html = resp.data.decode('utf-8')
        assert '10 cajas' in html
        assert '5 cajas' in html


# === AC #2, #3: Test POST saves cajas and peso correctly ===

def test_post_preparar_saves_cajas(logged_client, app):
    """AC #3: POST preparar_pedido guarda cajas entregadas correctamente."""
    with app.app_context():
        from app import Pedido, DetallePedido
        pedido = Pedido.query.first()
        detalles = DetallePedido.query.filter_by(pedido_id=pedido.id).all()

        form_data = {}
        for d in detalles:
            form_data[f'entregadas_{d.id}'] = '8'
            form_data[f'peso_{d.id}'] = '0'
            form_data[f'lote_{d.id}'] = 'L001'
            form_data[f'fab_{d.id}'] = '2026-01-01'
            form_data[f'exp_{d.id}'] = '2026-06-01'

        resp = logged_client.post(
            f'/pedidos/{pedido.id}/preparar',
            data=form_data,
            follow_redirects=True,
        )
        assert resp.status_code == 200

        # Verify cajas were saved
        for d in DetallePedido.query.filter_by(pedido_id=pedido.id).all():
            assert d.cajas == 8


def test_post_preparar_saves_peso_for_se_pesa_product(logged_client, app):
    """AC #2, #3: POST guarda peso real para producto con se_pesa=True."""
    with app.app_context():
        from app import Pedido, DetallePedido, Producto
        pedido = Pedido.query.first()
        detalles = DetallePedido.query.filter_by(pedido_id=pedido.id).all()

        form_data = {}
        for d in detalles:
            form_data[f'entregadas_{d.id}'] = '7'
            form_data[f'lote_{d.id}'] = 'L001'
            form_data[f'fab_{d.id}'] = '2026-01-01'
            form_data[f'exp_{d.id}'] = '2026-06-01'
            if d.producto.se_pesa:
                form_data[f'peso_{d.id}'] = '45.5'
            else:
                form_data[f'peso_{d.id}'] = '0'

        resp = logged_client.post(
            f'/pedidos/{pedido.id}/preparar',
            data=form_data,
            follow_redirects=True,
        )
        assert resp.status_code == 200

        # Verify peso saved for se_pesa product
        for d in DetallePedido.query.filter_by(pedido_id=pedido.id).all():
            if d.producto.se_pesa:
                assert d.peso == 45.5


def test_post_preparar_no_peso_for_non_se_pesa_product(logged_client, app):
    """AC #4: POST no requiere peso para producto con se_pesa=False."""
    with app.app_context():
        from app import Pedido, DetallePedido
        pedido = Pedido.query.first()
        detalles = DetallePedido.query.filter_by(pedido_id=pedido.id).all()

        form_data = {}
        for d in detalles:
            form_data[f'entregadas_{d.id}'] = '5'
            form_data[f'lote_{d.id}'] = ''
            form_data[f'fab_{d.id}'] = ''
            form_data[f'exp_{d.id}'] = ''
            # No peso submitted for non-se_pesa products

        resp = logged_client.post(
            f'/pedidos/{pedido.id}/preparar',
            data=form_data,
            follow_redirects=True,
        )
        assert resp.status_code == 200

        # Non-se_pesa products should keep original peso (0)
        for d in DetallePedido.query.filter_by(pedido_id=pedido.id).all():
            if not d.producto.se_pesa:
                assert d.peso == 0


# === AC #5: Test modelo Producto has se_pesa field ===

def test_producto_has_se_pesa_field(app):
    """AC #2, #4: Modelo Producto tiene campo se_pesa."""
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


# === AC #3: Test pedido changes to 'listo' after preparation ===

def test_pedido_changes_to_listo(logged_client, app):
    """AC #3: Pedido cambia a estado 'listo' después de preparación."""
    with app.app_context():
        from app import Pedido, DetallePedido
        pedido = Pedido.query.first()
        assert pedido.estado == 'pendiente'

        detalles = DetallePedido.query.filter_by(pedido_id=pedido.id).all()
        form_data = {}
        for d in detalles:
            form_data[f'entregadas_{d.id}'] = str(d.cajas)
            form_data[f'peso_{d.id}'] = '0'
            form_data[f'lote_{d.id}'] = 'L001'
            form_data[f'fab_{d.id}'] = '2026-01-01'
            form_data[f'exp_{d.id}'] = '2026-06-01'

        logged_client.post(
            f'/pedidos/{pedido.id}/preparar',
            data=form_data,
            follow_redirects=True,
        )

        pedido_updated = Pedido.query.first()
        assert pedido_updated.estado == 'listo'


# === AC #5: Template shows difference column ===

def test_preparar_pedido_shows_diferencia_column(logged_client, app):
    """AC #5: La preparación muestra columna de diferencia."""
    with app.app_context():
        from app import Pedido
        pedido = Pedido.query.first()
        resp = logged_client.get(f'/pedidos/{pedido.id}/preparar')
        html = resp.data.decode('utf-8')
        assert 'Diferencia' in html
        assert 'diferencia' in html


# === AC #4: Template conditionally shows peso field ===

def test_preparar_pedido_peso_field_conditional(logged_client, app):
    """AC #2, #4: Campo peso solo para productos que se pesan."""
    with app.app_context():
        from app import Pedido
        pedido = Pedido.query.first()
        resp = logged_client.get(f'/pedidos/{pedido.id}/preparar')
        html = resp.data.decode('utf-8')
        # Should have at least one enabled peso input (for se_pesa=True)
        # and at least one disabled (for se_pesa=False)
        assert 'disabled' in html
        assert 'placeholder="N/A"' in html


# === AC #6: Regression tests ===

def test_regression_dashboard_works(logged_client):
    """AC #6: El dashboard sigue funcionando normalmente."""
    resp = logged_client.get('/dashboard')
    assert resp.status_code == 200


def test_regression_login_works(anon_client):
    """AC #6: La página de login sigue funcionando normalmente."""
    resp = anon_client.get('/login')
    assert resp.status_code == 200
