# tests/test_trazabilidad.py
"""Tests para Story 2.3: Reforzar trazabilidad obligatoria en preparación."""
import os
import pytest
from unittest.mock import patch, MagicMock

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

        # Setup pedido pendiente con detalles
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


def _build_preparar_form(detalles, lote='L001', fab='2026-01-01', exp='2026-06-01'):
    """Helper para construir form data de preparación con trazabilidad."""
    form_data = {}
    for d in detalles:
        form_data[f'entregadas_{d.id}'] = str(d.cajas)
        form_data[f'peso_{d.id}'] = '0'
        form_data[f'lote_{d.id}'] = lote
        form_data[f'fab_{d.id}'] = fab
        form_data[f'exp_{d.id}'] = exp
    return form_data


# === AC #1: Validación obligatoria en preparación ===

def test_preparar_sin_lote_rechazado(logged_client, app):
    """AC #1: POST preparar_pedido SIN lote retorna 200, pedido sigue pendiente."""
    with app.app_context():
        from app import Pedido, DetallePedido
        pedido = Pedido.query.first()
        detalles = DetallePedido.query.filter_by(pedido_id=pedido.id).all()

        form_data = _build_preparar_form(detalles, lote='', fab='2026-01-01', exp='2026-06-01')
        resp = logged_client.post(
            f'/pedidos/{pedido.id}/preparar',
            data=form_data,
        )
        assert resp.status_code == 200
        # Pedido sigue en pendiente
        pedido_updated = Pedido.query.first()
        assert pedido_updated.estado == 'pendiente'


def test_preparar_sin_fecha_fabricacion_rechazado(logged_client, app):
    """AC #1: POST preparar_pedido SIN fecha_fabricacion → error."""
    with app.app_context():
        from app import Pedido, DetallePedido
        pedido = Pedido.query.first()
        detalles = DetallePedido.query.filter_by(pedido_id=pedido.id).all()

        form_data = _build_preparar_form(detalles, lote='L001', fab='', exp='2026-06-01')
        resp = logged_client.post(
            f'/pedidos/{pedido.id}/preparar',
            data=form_data,
        )
        assert resp.status_code == 200
        pedido_updated = Pedido.query.first()
        assert pedido_updated.estado == 'pendiente'


def test_preparar_sin_fecha_expiracion_rechazado(logged_client, app):
    """AC #1: POST preparar_pedido SIN fecha_expiracion → error."""
    with app.app_context():
        from app import Pedido, DetallePedido
        pedido = Pedido.query.first()
        detalles = DetallePedido.query.filter_by(pedido_id=pedido.id).all()

        form_data = _build_preparar_form(detalles, lote='L001', fab='2026-01-01', exp='')
        resp = logged_client.post(
            f'/pedidos/{pedido.id}/preparar',
            data=form_data,
        )
        assert resp.status_code == 200
        pedido_updated = Pedido.query.first()
        assert pedido_updated.estado == 'pendiente'


def test_preparar_pedido_facturado_rechazado(logged_client, app):
    """AC #4: POST preparar_pedido de pedido facturado → rechazado."""
    with app.app_context():
        from app import Pedido, DetallePedido
        pedido = Pedido.query.first()
        pedido.estado = 'facturado'
        _db.session.commit()

        detalles = DetallePedido.query.filter_by(pedido_id=pedido.id).all()
        form_data = _build_preparar_form(detalles)
        resp = logged_client.post(
            f'/pedidos/{pedido.id}/preparar',
            data=form_data,
            follow_redirects=True,
        )
        assert resp.status_code == 200
        pedido_updated = Pedido.query.first()
        assert pedido_updated.estado == 'facturado'


def test_agregar_detalle_pedido_facturado_rechazado(logged_client, app):
    """AC #4: POST detalles_pedido de pedido facturado → rechazado, detalle NO se crea."""
    with app.app_context():
        from app import Pedido, DetallePedido, Producto
        pedido = Pedido.query.first()
        pedido.estado = 'facturado'
        _db.session.commit()

        producto = Producto.query.first()
        count_before = DetallePedido.query.filter_by(pedido_id=pedido.id).count()

        resp = logged_client.post(
            f'/pedidos/{pedido.id}/detalles',
            data={
                'producto_id': str(producto.id),
                'peso': '5.0',
                'cajas': '0',
                'lote': 'L001',
                'fecha_fabricacion': '2026-01-01',
                'fecha_expiracion': '2026-06-01',
            },
            follow_redirects=True,
        )
        assert resp.status_code == 200
        count_after = DetallePedido.query.filter_by(pedido_id=pedido.id).count()
        assert count_after == count_before


def test_preparar_con_trazabilidad_completa_acepta(logged_client, app):
    """AC #1: POST preparar_pedido CON todos los campos → estado 'listo'."""
    with app.app_context():
        from app import Pedido, DetallePedido
        pedido = Pedido.query.first()
        detalles = DetallePedido.query.filter_by(pedido_id=pedido.id).all()

        form_data = _build_preparar_form(detalles)
        resp = logged_client.post(
            f'/pedidos/{pedido.id}/preparar',
            data=form_data,
            follow_redirects=True,
        )
        assert resp.status_code == 200
        pedido_updated = Pedido.query.first()
        assert pedido_updated.estado == 'listo'


# === AC #2: Validación obligatoria en agregar detalle ===

def test_agregar_detalle_sin_lote_rechazado(logged_client, app):
    """AC #2: POST detalles_pedido SIN lote → error flash, detalle NO se crea."""
    with app.app_context():
        from app import Pedido, DetallePedido, Producto
        pedido = Pedido.query.first()
        producto = Producto.query.first()
        count_before = DetallePedido.query.filter_by(pedido_id=pedido.id).count()

        resp = logged_client.post(
            f'/pedidos/{pedido.id}/detalles',
            data={
                'producto_id': str(producto.id),
                'peso': '5.0',
                'cajas': '0',
                'lote': '',
                'fecha_fabricacion': '2026-01-01',
                'fecha_expiracion': '2026-06-01',
            },
            follow_redirects=True,
        )
        assert resp.status_code == 200
        count_after = DetallePedido.query.filter_by(pedido_id=pedido.id).count()
        assert count_after == count_before  # No se creó nuevo detalle


# === AC #3: Bloqueo facturación sin trazabilidad ===

def test_facturar_sin_trazabilidad_bloqueado(logged_client, app):
    """AC #3: POST facturar con trazabilidad incompleta → flash error, estado sigue 'listo'."""
    with app.app_context():
        from app import Pedido
        pedido = Pedido.query.first()
        pedido.estado = 'listo'
        _db.session.commit()

        resp = logged_client.post(
            f'/pedidos/{pedido.id}/facturar',
            follow_redirects=True,
        )
        assert resp.status_code == 200
        pedido_updated = Pedido.query.first()
        assert pedido_updated.estado == 'listo'


def test_facturar_con_trazabilidad_completa_procede(logged_client, app):
    """AC #3: POST facturar con trazabilidad completa → procede (mock N8N)."""
    with app.app_context():
        from app import Pedido, DetallePedido
        pedido = Pedido.query.first()
        pedido.estado = 'listo'

        # Rellenar trazabilidad en todos los detalles
        for d in DetallePedido.query.filter_by(pedido_id=pedido.id).all():
            d.lote = 'L001'
            d.fecha_fabricacion = '2026-01-01'
            d.fecha_expiracion = '2026-06-01'
        _db.session.commit()

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {'invoice_id': 'INV-TEST'}

        with patch('app.N8N_WEBHOOK_URL', 'http://test-n8n.local/webhook'), \
             patch('app.requests.post', return_value=mock_resp):
            resp = logged_client.post(
                f'/pedidos/{pedido.id}/facturar',
                follow_redirects=True,
            )
        assert resp.status_code == 200
        pedido_updated = Pedido.query.first()
        assert pedido_updated.estado == 'facturado'


# === AC #4: Inmutabilidad post-facturación ===

def test_editar_detalle_facturado_rechazado(logged_client, app):
    """AC #4: POST editar_detalle de pedido facturado → rechazado."""
    with app.app_context():
        from app import Pedido, DetallePedido, Producto
        pedido = Pedido.query.first()
        pedido.estado = 'facturado'
        _db.session.commit()

        detalle = DetallePedido.query.filter_by(pedido_id=pedido.id).first()
        producto = Producto.query.first()

        resp = logged_client.post(
            f'/detalles_pedido/{detalle.id}/editar',
            data={
                'producto_id': str(producto.id),
                'peso': '10.0',
                'lote': 'NUEVO',
                'fecha_fabricacion': '2026-02-01',
                'fecha_expiracion': '2026-07-01',
            },
            follow_redirects=True,
        )
        assert resp.status_code == 200
        # Verificar que lote NO cambió
        detalle_updated = DetallePedido.query.get(detalle.id)
        assert detalle_updated.lote != 'NUEVO'


def test_eliminar_detalle_facturado_rechazado(logged_client, app):
    """AC #4: POST eliminar_detalle de pedido facturado → rechazado."""
    with app.app_context():
        from app import Pedido, DetallePedido
        pedido = Pedido.query.first()
        pedido.estado = 'facturado'
        _db.session.commit()

        detalle = DetallePedido.query.filter_by(pedido_id=pedido.id).first()
        count_before = DetallePedido.query.filter_by(pedido_id=pedido.id).count()

        resp = logged_client.post(
            f'/detalles_pedido/{detalle.id}/eliminar',
            follow_redirects=True,
        )
        assert resp.status_code == 200
        count_after = DetallePedido.query.filter_by(pedido_id=pedido.id).count()
        assert count_after == count_before  # No se eliminó


# === AC #6: Regresión ===

def test_preparar_pedido_get_sigue_cargando(logged_client, app):
    """AC #6: preparar_pedido GET sigue funcionando."""
    with app.app_context():
        from app import Pedido
        pedido = Pedido.query.first()
        resp = logged_client.get(f'/pedidos/{pedido.id}/preparar')
        assert resp.status_code == 200


def test_regression_dashboard_works(logged_client):
    """AC #6: El dashboard sigue funcionando."""
    resp = logged_client.get('/dashboard')
    assert resp.status_code == 200


def test_regression_login_works(anon_client):
    """AC #6: La página de login sigue funcionando."""
    resp = anon_client.get('/login')
    assert resp.status_code == 200
