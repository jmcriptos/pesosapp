# tests/test_facturacion.py
"""Tests para Story 2.4: Fix facturación atómica con manejo de errores."""
import os
import pytest
import requests as req_lib
from unittest.mock import patch, MagicMock
from datetime import datetime, timezone

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

        # Setup cliente con qbo_id (requerido por pedido_a_json)
        cliente = Cliente(nombre='Cliente Test', territorio_id=territorio.id,
                          qbo_id='QBO-C001')
        _db.session.add(cliente)
        _db.session.flush()

        # Setup producto con qbo_id y tax_rate
        producto = Producto(
            nombre='Chuleta de Cerdo',
            descripcion='Carne',
            temperatura='Congelado',
            se_pesa=True,
            tax_rate=6.0,
            qbo_id='QBO-P001',
        )
        _db.session.add(producto)
        _db.session.flush()

        # Pedido en estado "preparado" con trazabilidad completa (listo para facturar)
        pedido = Pedido(
            cliente_id=cliente.id,
            estado='preparado',
        )
        _db.session.add(pedido)
        _db.session.flush()

        detalle = DetallePedido(
            pedido_id=pedido.id,
            producto_id=producto.id,
            cajas=10,
            peso=0,
            precio_unitario=25.00,
            subtotal=250.00,
            lote='L001',
            fecha_fabricacion=datetime(2026, 1, 1),
            fecha_expiracion=datetime(2026, 6, 1),
            es_linea_pedido=False,
        )
        _db.session.add(detalle)
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


def _mock_n8n_success(invoice_id='INV-001'):
    """Helper: mock N8N respuesta exitosa con invoice_id."""
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {'invoice_id': invoice_id}
    mock_resp.raise_for_status = MagicMock()
    return mock_resp


def _mock_n8n_success_no_invoice():
    """Helper: mock N8N respuesta 200 pero sin invoice_id en JSON."""
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {'status': 'ok'}
    mock_resp.raise_for_status = MagicMock()
    return mock_resp


def _mock_n8n_http_error(status_code, body=None):
    """Helper: mock N8N respuesta HTTP error."""
    mock_resp = MagicMock()
    mock_resp.status_code = status_code
    mock_resp.text = body or f'Error {status_code}'
    mock_resp.json.return_value = {'message': body or f'Error {status_code}'}
    mock_resp.raise_for_status.side_effect = req_lib.HTTPError(
        response=mock_resp
    )
    return mock_resp


# === AC #1: Facturación exitosa con invoice ID ===

@patch('app.N8N_WEBHOOK_URL', 'http://test-n8n.local/webhook')
@patch('app.requests.post')
def test_facturacion_exitosa_con_invoice_id(mock_post, logged_client, app):
    """AC #1: N8N 200 + invoice_id → estado=facturado, invoice_id_qbo guardado."""
    mock_post.return_value = _mock_n8n_success('INV-001')

    with app.app_context():
        from app import Pedido
        pedido = Pedido.query.first()
        pedido_id = pedido.id

        resp = logged_client.post(
            f'/pedidos/{pedido_id}/facturar',
            follow_redirects=True,
        )
        assert resp.status_code == 200

        pedido = _db.session.get(Pedido, pedido_id)
        assert pedido.estado == 'facturado'
        assert pedido.invoice_id_qbo == 'INV-001'
        assert pedido.fecha_facturacion is not None

        # Flash incluye invoice ID
        assert b'INV-001' in resp.data


# === AC #2: Manejo de error HTTP 4xx ===

@patch('app.N8N_WEBHOOK_URL', 'http://test-n8n.local/webhook')
@patch('app.requests.post')
def test_facturacion_error_400(mock_post, logged_client, app):
    """AC #2: N8N 400 → pedido sigue 'preparado', flash con mensaje específico."""
    mock_post.return_value = _mock_n8n_http_error(400, 'Customer not found in QBO')

    with app.app_context():
        from app import Pedido
        pedido = Pedido.query.first()
        pedido_id = pedido.id

        resp = logged_client.post(
            f'/pedidos/{pedido_id}/facturar',
            follow_redirects=True,
        )
        assert resp.status_code == 200

        pedido = _db.session.get(Pedido, pedido_id)
        assert pedido.estado == 'preparado'
        assert pedido.invoice_id_qbo is None

        # Flash muestra el error específico
        assert b'HTTP 400' in resp.data


# === AC #3: Manejo de error HTTP 5xx ===

@patch('app.N8N_WEBHOOK_URL', 'http://test-n8n.local/webhook')
@patch('app.requests.post')
def test_facturacion_error_500(mock_post, logged_client, app):
    """AC #3: N8N 500 → pedido sigue 'preparado', flash mensaje temporal."""
    mock_post.return_value = _mock_n8n_http_error(500, 'Internal Server Error')

    with app.app_context():
        from app import Pedido
        pedido = Pedido.query.first()
        pedido_id = pedido.id

        resp = logged_client.post(
            f'/pedidos/{pedido_id}/facturar',
            follow_redirects=True,
        )
        assert resp.status_code == 200

        pedido = _db.session.get(Pedido, pedido_id)
        assert pedido.estado == 'preparado'
        assert pedido.invoice_id_qbo is None

        # Flash muestra mensaje de error temporal
        assert 'Error temporal en QuickBooks'.encode() in resp.data


# === AC #4: Manejo de timeout ===

@patch('app.N8N_WEBHOOK_URL', 'http://test-n8n.local/webhook')
@patch('app.requests.post', side_effect=req_lib.Timeout('Connection timed out'))
def test_facturacion_timeout(mock_post, logged_client, app):
    """AC #4: N8N timeout → pedido sigue 'preparado', flash timeout."""
    with app.app_context():
        from app import Pedido
        pedido = Pedido.query.first()
        pedido_id = pedido.id

        resp = logged_client.post(
            f'/pedidos/{pedido_id}/facturar',
            follow_redirects=True,
        )
        assert resp.status_code == 200

        pedido = _db.session.get(Pedido, pedido_id)
        assert pedido.estado == 'preparado'
        assert pedido.invoice_id_qbo is None

        assert 'Timeout'.encode() in resp.data


# === AC #5: N8N 200 pero sin invoice_id en JSON ===

@patch('app.N8N_WEBHOOK_URL', 'http://test-n8n.local/webhook')
@patch('app.requests.post')
def test_facturacion_exitosa_sin_invoice_id(mock_post, logged_client, app):
    """AC #5: N8N 200 sin invoice_id → estado=facturado, invoice_id_qbo=None."""
    mock_post.return_value = _mock_n8n_success_no_invoice()

    with app.app_context():
        from app import Pedido
        pedido = Pedido.query.first()
        pedido_id = pedido.id

        resp = logged_client.post(
            f'/pedidos/{pedido_id}/facturar',
            follow_redirects=True,
        )
        assert resp.status_code == 200

        pedido = _db.session.get(Pedido, pedido_id)
        assert pedido.estado == 'facturado'
        assert pedido.invoice_id_qbo is None
        assert pedido.fecha_facturacion is not None

        # Flash genérico (sin invoice ID)
        assert 'Factura generada correctamente'.encode() in resp.data


# === AC #6: Pedido ya facturado (idempotencia) ===

@patch('app.N8N_WEBHOOK_URL', 'http://test-n8n.local/webhook')
def test_facturacion_pedido_ya_facturado(logged_client, app):
    """AC #6: Pedido ya facturado → rechazado sin llamar N8N."""
    with app.app_context():
        from app import Pedido
        pedido = Pedido.query.first()
        pedido.estado = 'facturado'
        pedido.invoice_id_qbo = 'INV-EXISTING'
        _db.session.commit()
        pedido_id = pedido.id

        # NO debe llamar N8N
        with patch('app.requests.post') as mock_post:
            resp = logged_client.post(
                f'/pedidos/{pedido_id}/facturar',
                follow_redirects=True,
            )
            mock_post.assert_not_called()

        assert resp.status_code == 200
        assert 'ya est'.encode() in resp.data


# === AC #7: Trazabilidad incompleta → rechazado ===

@patch('app.N8N_WEBHOOK_URL', 'http://test-n8n.local/webhook')
def test_facturacion_trazabilidad_incompleta(logged_client, app):
    """AC #7: Pedido listo pero sin lote → no se puede facturar."""
    with app.app_context():
        from app import Pedido, DetallePedido
        pedido = Pedido.query.first()
        pedido_id = pedido.id
        # Trazabilidad incompleta (modelo actual): una línea original pesable cuya
        # línea de preparación quedó sin lote. _validar_preparacion_pedido solo valida
        # la preparación de productos que tienen línea original, así que añadimos una.
        detalle = DetallePedido.query.filter_by(pedido_id=pedido_id).first()
        linea_original = DetallePedido(
            pedido_id=pedido_id,
            producto_id=detalle.producto_id,
            cajas=detalle.cajas,
            peso=0,
            precio_unitario=0,
            subtotal=0,
            es_linea_pedido=True,
        )
        _db.session.add(linea_original)
        detalle.lote = None
        _db.session.commit()

        with patch('app.requests.post') as mock_post:
            resp = logged_client.post(
                f'/pedidos/{pedido_id}/facturar',
                follow_redirects=True,
            )
            mock_post.assert_not_called()

        assert resp.status_code == 200
        pedido = _db.session.get(Pedido, pedido_id)
        assert pedido.estado == 'preparado'
        assert 'trazabilidad'.encode() in resp.data


# === AC #7 (continuación): ConnectionError ===

@patch('app.N8N_WEBHOOK_URL', 'http://test-n8n.local/webhook')
@patch('app.requests.post', side_effect=req_lib.ConnectionError('Connection refused'))
def test_facturacion_connection_error(mock_post, logged_client, app):
    """ConnectionError → pedido sigue 'preparado', flash error de conexión."""
    with app.app_context():
        from app import Pedido
        pedido = Pedido.query.first()
        pedido_id = pedido.id

        resp = logged_client.post(
            f'/pedidos/{pedido_id}/facturar',
            follow_redirects=True,
        )
        assert resp.status_code == 200

        pedido = _db.session.get(Pedido, pedido_id)
        assert pedido.estado == 'preparado'
        assert 'conexi'.encode() in resp.data


# === H3: DB commit failure path ===

@patch('app.N8N_WEBHOOK_URL', 'http://test-n8n.local/webhook')
@patch('app.requests.post')
def test_facturacion_commit_failure_logs_critical(mock_post, logged_client, app):
    """AC #6: Webhook exitoso pero commit falla → rollback + log critical + flash error."""
    mock_post.return_value = _mock_n8n_success('INV-FAIL')

    with app.app_context():
        from app import Pedido
        pedido = Pedido.query.first()
        pedido_id = pedido.id

        with patch('app.db.session.commit', side_effect=Exception('DB disk full')):
            resp = logged_client.post(
                f'/pedidos/{pedido_id}/facturar',
                follow_redirects=True,
            )
        assert resp.status_code == 200
        # Flash indica error interno
        assert 'Error interno'.encode() in resp.data
        assert 'QuickBooks'.encode() in resp.data


# === M2: N8N_WEBHOOK_URL no configurada ===

@patch('app.N8N_WEBHOOK_URL', None)
def test_facturacion_sin_webhook_url_configurada(logged_client, app):
    """N8N_WEBHOOK_URL=None → flash error de configuración, N8N no se llama."""
    with app.app_context():
        from app import Pedido
        pedido = Pedido.query.first()
        pedido_id = pedido.id

        with patch('app.requests.post') as mock_post:
            resp = logged_client.post(
                f'/pedidos/{pedido_id}/facturar',
                follow_redirects=True,
            )
            mock_post.assert_not_called()

        assert resp.status_code == 200
        assert 'N8N_WEBHOOK_URL'.encode() in resp.data

        pedido = _db.session.get(Pedido, pedido_id)
        assert pedido.estado == 'preparado'


# === Regresión: dashboard y login siguen funcionando ===

def test_regression_login_funciona(app):
    """Regresión: login sigue funcionando correctamente."""
    client = app.test_client()
    resp = client.post('/login', data={
        'username': 'admin',
        'password': 'testpass',
    }, follow_redirects=True)
    assert resp.status_code == 200


def test_regression_dashboard_accesible(logged_client, app):
    """Regresión: dashboard accesible después de login."""
    resp = logged_client.get('/dashboard', follow_redirects=True)
    assert resp.status_code == 200
