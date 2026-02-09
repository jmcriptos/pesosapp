# tests/test_etiquetas.py
"""Tests para Story 2.5: Verificar etiquetas y vista de pedidos con nuevo modelo."""
import os
import pytest
from unittest.mock import patch, call

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

        # Cliente
        cliente = Cliente(nombre='Cliente Test', territorio_id=territorio.id,
                          qbo_id='QBO-C001')
        _db.session.add(cliente)
        _db.session.flush()

        # Producto que se pesa (kg)
        prod_peso = Producto(
            nombre='Chuleta de Cerdo',
            descripcion='Carne',
            temperatura='-18°C',
            se_pesa=True,
            tax_rate=6.0,
            qbo_id='QBO-P001',
        )
        _db.session.add(prod_peso)

        # Producto que NO se pesa (unidades)
        prod_uds = Producto(
            nombre='Salchicha Paquete',
            descripcion='Embutido',
            temperatura='4°C',
            se_pesa=False,
            tax_rate=6.0,
            qbo_id='QBO-P002',
        )
        _db.session.add(prod_uds)
        _db.session.flush()

        # Pedido listo con trazabilidad completa
        pedido = Pedido(
            cliente_id=cliente.id,
            estado='preparado',
        )
        _db.session.add(pedido)
        _db.session.flush()

        # Detalle 1: producto que se pesa (línea de preparación)
        det1 = DetallePedido(
            pedido_id=pedido.id,
            producto_id=prod_peso.id,
            cajas=5,
            peso=12.50,
            precio_unitario=25.00,
            subtotal=312.50,
            lote='L001',
            fecha_fabricacion='2026-01-15',
            fecha_expiracion='2026-06-15',
            es_linea_pedido=False,
        )
        _db.session.add(det1)

        # Detalle 2: producto que NO se pesa (línea de preparación)
        det2 = DetallePedido(
            pedido_id=pedido.id,
            producto_id=prod_uds.id,
            cajas=10,
            peso=0,
            precio_unitario=15.00,
            subtotal=150.00,
            lote='L002',
            fecha_fabricacion='2026-01-15',
            fecha_expiracion='2026-07-15',
            es_linea_pedido=False,
        )
        _db.session.add(det2)
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


# === AC #1: Etiquetas 4x2 con datos completos ===

def test_etiquetas_4x2_genera_pdf(logged_client, app):
    """AC #1: Etiquetas 4x2 para pedido con trazabilidad → HTTP 200, PDF."""
    with app.app_context():
        from app import Pedido
        pedido = Pedido.query.first()
        resp = logged_client.get(
            f'/generar_etiqueta_detalle/{pedido.id}'
            '?fecha_inicio=2026-01-01&fecha_fin=2026-12-31'
        )
        assert resp.status_code == 200
        assert resp.content_type == 'application/pdf'
        assert len(resp.data) > 100  # PDF no vacío


# === AC #2: Etiquetas A4 con datos completos ===

def test_etiquetas_a4_genera_pdf(logged_client, app):
    """AC #2: Etiquetas A4 para pedido con trazabilidad → HTTP 200, PDF."""
    with app.app_context():
        from app import Pedido
        pedido = Pedido.query.first()
        resp = logged_client.get(
            f'/generar_etiqueta_detalle_a4/{pedido.id}'
            '?fecha_inicio=2026-01-01&fecha_fin=2026-12-31'
        )
        assert resp.status_code == 200
        assert resp.content_type == 'application/pdf'
        assert len(resp.data) > 100


# === AC #3: Peso con unidad correcta — spy verifica contenido real ===

@patch('app.draw_order_label', wraps=__import__('app').draw_order_label)
def test_etiquetas_4x2_peso_kg_verificado(mock_draw, logged_client, app):
    """AC #3: se_pesa=True → draw_order_label recibe weight con 'kg'."""
    with app.app_context():
        from app import Pedido, DetallePedido, Producto
        pedido = Pedido.query.first()

        # Solo dejar el detalle del producto que se pesa
        prod_uds = Producto.query.filter_by(se_pesa=False).first()
        DetallePedido.query.filter_by(
            pedido_id=pedido.id, producto_id=prod_uds.id
        ).delete()
        _db.session.commit()

        resp = logged_client.get(
            f'/generar_etiqueta_detalle/{pedido.id}'
            '?fecha_inicio=2026-01-01&fecha_fin=2026-12-31'
        )
        assert resp.status_code == 200
        assert mock_draw.call_count == 1
        _, kwargs = mock_draw.call_args
        assert 'kg' in kwargs['weight']
        assert '12.50' in kwargs['weight']


@patch('app.draw_order_label', wraps=__import__('app').draw_order_label)
def test_etiquetas_4x2_peso_uds_verificado(mock_draw, logged_client, app):
    """AC #3: se_pesa=False → draw_order_label recibe weight con 'uds'."""
    with app.app_context():
        from app import Pedido, DetallePedido, Producto
        pedido = Pedido.query.first()

        # Solo dejar el detalle del producto que NO se pesa
        prod_peso = Producto.query.filter_by(se_pesa=True).first()
        DetallePedido.query.filter_by(
            pedido_id=pedido.id, producto_id=prod_peso.id
        ).delete()
        _db.session.commit()

        resp = logged_client.get(
            f'/generar_etiqueta_detalle/{pedido.id}'
            '?fecha_inicio=2026-01-01&fecha_fin=2026-12-31'
        )
        assert resp.status_code == 200
        assert mock_draw.call_count == 1
        _, kwargs = mock_draw.call_args
        assert 'uds' in kwargs['weight']
        assert '10' in kwargs['weight']


# === AC #3: Validación de fechas ===

def test_etiquetas_4x2_sin_fechas_retorna_400(logged_client, app):
    """Ruta sin fechas válidas → error 400."""
    with app.app_context():
        from app import Pedido
        pedido = Pedido.query.first()
        resp = logged_client.get(
            f'/generar_etiqueta_detalle/{pedido.id}'
        )
        assert resp.status_code == 400


def test_etiquetas_a4_sin_fechas_retorna_400(logged_client, app):
    """Ruta A4 sin fechas → error 400."""
    with app.app_context():
        from app import Pedido
        pedido = Pedido.query.first()
        resp = logged_client.get(
            f'/generar_etiqueta_detalle_a4/{pedido.id}'
        )
        assert resp.status_code == 400


# === AC #4: Vista pedidos pendientes ===

def test_vista_pedidos_carga_correctamente(logged_client, app):
    """AC #4: /pedidos carga con estados y datos correctos."""
    resp = logged_client.get('/pedidos')
    assert resp.status_code == 200
    assert b'Cliente Test' in resp.data


# === AC #5: Sin regresiones ===

def test_regresion_login_funciona(app):
    """Regresión: login sigue funcionando."""
    client = app.test_client()
    resp = client.post('/login', data={
        'username': 'admin',
        'password': 'testpass',
    }, follow_redirects=True)
    assert resp.status_code == 200


def test_regresion_dashboard_accesible(logged_client, app):
    """Regresión: dashboard accesible."""
    resp = logged_client.get('/dashboard', follow_redirects=True)
    assert resp.status_code == 200


# === Trazabilidad parcial (null safety) — 4x2 ===

def test_etiquetas_4x2_trazabilidad_parcial_no_crashea(logged_client, app):
    """Trazabilidad parcial (sin lote) → etiqueta 4x2 se genera sin crash."""
    with app.app_context():
        from app import Pedido, DetallePedido
        pedido = Pedido.query.first()
        det = DetallePedido.query.filter_by(pedido_id=pedido.id).first()
        det.lote = None
        det.fecha_expiracion = None
        _db.session.commit()

        resp = logged_client.get(
            f'/generar_etiqueta_detalle/{pedido.id}'
            '?fecha_inicio=2026-01-01&fecha_fin=2026-12-31'
        )
        assert resp.status_code == 200
        assert resp.content_type == 'application/pdf'


# === M1 Fix: Trazabilidad parcial A4 ===

def test_etiquetas_a4_trazabilidad_parcial_no_crashea(logged_client, app):
    """Trazabilidad parcial (sin lote) → etiqueta A4 se genera sin crash."""
    with app.app_context():
        from app import Pedido, DetallePedido
        pedido = Pedido.query.first()
        det = DetallePedido.query.filter_by(pedido_id=pedido.id).first()
        det.lote = None
        det.fecha_expiracion = None
        _db.session.commit()

        resp = logged_client.get(
            f'/generar_etiqueta_detalle_a4/{pedido.id}'
            '?fecha_inicio=2026-01-01&fecha_fin=2026-12-31'
        )
        assert resp.status_code == 200
        assert resp.content_type == 'application/pdf'


# === M2 Fix: Test via POST ===

def test_etiquetas_4x2_via_post(logged_client, app):
    """Ruta 4x2 funciona via POST (compatibilidad iOS)."""
    with app.app_context():
        from app import Pedido
        pedido = Pedido.query.first()
        resp = logged_client.post(
            f'/generar_etiqueta_detalle/{pedido.id}',
            data={
                'fecha_inicio': '2026-01-01',
                'fecha_fin': '2026-12-31',
            },
        )
        assert resp.status_code == 200
        assert resp.content_type == 'application/pdf'
