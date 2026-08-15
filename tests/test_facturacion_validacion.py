"""Tests de validación de datos de facturación.

Origen: el 2026-08-14 los pedidos 1264 y 1267 se facturaron con el producto
"Smoked Turkey Ham" (id 199) recién creado sin precio en ninguna lista
(precio_unitario = 0.00) y con un qbo_id que no correspondía al item real
de QuickBooks. La app no validaba nada de eso: armó el payload, N8N lo
aceptó y las facturas hubo que corregirlas a mano en QBO.

Estos tests fijan el contrato: si una línea va a salir hacia QuickBooks sin
precio o sin item, la facturación se bloquea ANTES de llamar a N8N.
"""
import os
from datetime import datetime
from unittest.mock import patch

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
        from app import Rol, Territorio, Vendedor

        rol = Rol(nombre='super_admin', descripcion='Admin')
        _db.session.add(rol)
        territorio = Territorio(nombre='test', descripcion='Test')
        _db.session.add(territorio)
        _db.session.flush()

        vendedor = Vendedor(
            username='admin', email='admin@test.com',
            nombre_completo='Admin Test', rol_id=rol.id,
            territorio_id=territorio.id, activo=True,
        )
        vendedor.set_password('testpass')
        _db.session.add(vendedor)
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


def _crear_pedido_preparado(precio_unitario=25.00, producto_qbo_id='QBO-P001',
                            cliente_qbo_id='QBO-C001'):
    """Pedido 'preparado' con trazabilidad completa, listo para facturar.

    Reproduce la forma real de los pedidos 1264/1267: producto pesable con
    línea original (es_linea_pedido=True) y sus CajaPesada. Es el camino que
    recorre el primer bucle de pedido_a_json.
    """
    from app import (Cliente, Producto, Pedido, DetallePedido, Territorio,
                     CajaPesada)

    territorio = Territorio.query.first()
    cliente = Cliente(nombre='Cliente Test', territorio_id=territorio.id,
                      qbo_id=cliente_qbo_id)
    _db.session.add(cliente)

    producto = Producto(
        nombre='Smoked Turkey Ham', descripcion='Pavo', temperatura='Congelado',
        se_pesa=True, tax_rate=14.0, qbo_id=producto_qbo_id,
    )
    _db.session.add(producto)
    _db.session.flush()

    pedido = Pedido(cliente_id=cliente.id, estado='preparado')
    _db.session.add(pedido)
    _db.session.flush()

    detalle = DetallePedido(
        pedido_id=pedido.id, producto_id=producto.id,
        cajas=2, peso=0, cajas_pedidas=2,
        precio_unitario=precio_unitario,
        subtotal=precio_unitario * 2,
        es_linea_pedido=True,
    )
    _db.session.add(detalle)
    _db.session.flush()

    for numero, peso in ((1, 19.60), (2, 19.50)):
        _db.session.add(CajaPesada(
            detalle_pedido_id=detalle.id, numero=numero, peso=peso,
            lote='L-1208202601',
            fecha_elaboracion=datetime(2026, 8, 12).date(),
            fecha_vencimiento=datetime(2027, 8, 12).date(),
        ))
    _db.session.commit()
    return pedido.id


@patch('app.N8N_WEBHOOK_URL', 'http://test-n8n.local/webhook')
@patch('app.requests.post')
def test_no_factura_producto_sin_precio(mock_post, logged_client, app):
    """Línea con precio 0 → no se llama a N8N y el pedido sigue 'preparado'."""
    with app.app_context():
        from app import Pedido
        pedido_id = _crear_pedido_preparado(precio_unitario=0.00)

        resp = logged_client.post(f'/pedidos/{pedido_id}/facturar',
                                  follow_redirects=True)

        assert resp.status_code == 200
        mock_post.assert_not_called()

        pedido = _db.session.get(Pedido, pedido_id)
        assert pedido.estado == 'preparado'
        assert pedido.fecha_facturacion is None
        assert b'Smoked Turkey Ham' in resp.data


@patch('app.N8N_WEBHOOK_URL', 'http://test-n8n.local/webhook')
@patch('app.requests.post')
def test_no_factura_producto_sin_qbo_id(mock_post, logged_client, app):
    """Producto sin qbo_id → no se llama a N8N y el pedido sigue 'preparado'."""
    with app.app_context():
        from app import Pedido
        pedido_id = _crear_pedido_preparado(producto_qbo_id=None)

        resp = logged_client.post(f'/pedidos/{pedido_id}/facturar',
                                  follow_redirects=True)

        assert resp.status_code == 200
        mock_post.assert_not_called()

        pedido = _db.session.get(Pedido, pedido_id)
        assert pedido.estado == 'preparado'
        assert pedido.fecha_facturacion is None
        assert b'Smoked Turkey Ham' in resp.data


@patch('app.N8N_WEBHOOK_URL', 'http://test-n8n.local/webhook')
@patch('app.requests.post')
def test_no_factura_cliente_sin_qbo_id(mock_post, logged_client, app):
    """Cliente sin qbo_id → no se llama a N8N y el pedido sigue 'preparado'."""
    with app.app_context():
        from app import Pedido
        pedido_id = _crear_pedido_preparado(cliente_qbo_id=None)

        resp = logged_client.post(f'/pedidos/{pedido_id}/facturar',
                                  follow_redirects=True)

        assert resp.status_code == 200
        mock_post.assert_not_called()

        pedido = _db.session.get(Pedido, pedido_id)
        assert pedido.estado == 'preparado'
        assert pedido.fecha_facturacion is None


def _mock_n8n(invoice_id=None):
    from unittest.mock import MagicMock
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = (
        {'invoice_id': invoice_id} if invoice_id else {'status': 'ok'}
    )
    mock_resp.raise_for_status = MagicMock()
    return mock_resp


@patch('app.N8N_WEBHOOK_URL', 'http://test-n8n.local/webhook')
@patch('app.requests.post')
def test_no_refactura_pedido_facturado_sin_invoice_id(mock_post, logged_client, app):
    """Bug real: invoice_id_qbo es NULL en los 909 pedidos de producción, así que
    el guard de idempotencia nunca disparaba y cualquier pedido se podía facturar
    dos veces (le pasó al 1264 el 2026-08-14). Sin confirmación explícita, no se
    reenvía."""
    with app.app_context():
        from app import Pedido
        pedido_id = _crear_pedido_preparado()
        pedido = _db.session.get(Pedido, pedido_id)
        pedido.estado = 'facturado'
        pedido.invoice_id_qbo = None
        _db.session.commit()

        resp = logged_client.post(f'/pedidos/{pedido_id}/facturar',
                                  follow_redirects=True)

        assert resp.status_code == 200
        mock_post.assert_not_called()
        assert 'duplicada'.encode() in resp.data


@patch('app.N8N_WEBHOOK_URL', 'http://test-n8n.local/webhook')
@patch('app.requests.post')
def test_reintento_explicito_si_reenvia(mock_post, logged_client, app):
    """El reintento sigue siendo posible, pero solo con confirmación explícita."""
    mock_post.return_value = _mock_n8n()

    with app.app_context():
        from app import Pedido
        pedido_id = _crear_pedido_preparado()
        pedido = _db.session.get(Pedido, pedido_id)
        pedido.estado = 'facturado'
        pedido.invoice_id_qbo = None
        _db.session.commit()

        resp = logged_client.post(f'/pedidos/{pedido_id}/facturar',
                                  data={'reintentar': '1'},
                                  follow_redirects=True)

        assert resp.status_code == 200
        mock_post.assert_called_once()


@patch('app.N8N_WEBHOOK_URL', 'http://test-n8n.local/webhook')
@patch('app.requests.post')
def test_sin_invoice_id_avisa_en_vez_de_declarar_exito(mock_post, logged_client, app):
    """N8N 200 sin invoice_id no prueba que QBO creara nada: el 2026-08-14 la app
    mostró 'Factura generada correctamente' y en QuickBooks no había factura."""
    mock_post.return_value = _mock_n8n()

    with app.app_context():
        pedido_id = _crear_pedido_preparado()

        resp = logged_client.post(f'/pedidos/{pedido_id}/facturar',
                                  follow_redirects=True)

        assert resp.status_code == 200
        assert 'Factura generada correctamente'.encode() not in resp.data
        assert 'no confirm'.encode() in resp.data


@patch('app.N8N_WEBHOOK_URL', 'http://test-n8n.local/webhook')
@patch('app.requests.post')
def test_lee_invoice_id_del_objeto_invoice_de_qbo(mock_post, logged_client, app):
    """El webhook N8N quedó en modo 'Last Node': responde con el objeto crudo de
    QuickBooks, donde el ID viene en Invoice.Id (no en una clave 'invoice_id').
    Sin esto, invoice_id_qbo sigue NULL y el guard anti-duplicados nunca sirve."""
    from unittest.mock import MagicMock

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        'Invoice': {'Id': '47349', 'DocNumber': '5816', 'TotalAmt': 1234.5},
        'time': '2026-08-15T00:40:00.000-04:00',
    }
    mock_resp.raise_for_status = MagicMock()
    mock_post.return_value = mock_resp

    with app.app_context():
        from app import Pedido
        pedido_id = _crear_pedido_preparado()

        resp = logged_client.post(f'/pedidos/{pedido_id}/facturar',
                                  follow_redirects=True)

        assert resp.status_code == 200
        pedido = _db.session.get(Pedido, pedido_id)
        assert pedido.estado == 'facturado'
        assert pedido.invoice_id_qbo == '47349'
        assert '5816'.encode() in resp.data


@patch('app.N8N_WEBHOOK_URL', 'http://test-n8n.local/webhook')
@patch('app.requests.post')
def test_guard_duplicados_usa_invoice_id_real(mock_post, logged_client, app):
    """Con invoice_id_qbo poblado, el pedido ya facturado se rechaza sin pedir
    confirmación: hay prueba de que la factura existe en QuickBooks."""
    with app.app_context():
        from app import Pedido
        pedido_id = _crear_pedido_preparado()
        pedido = _db.session.get(Pedido, pedido_id)
        pedido.estado = 'facturado'
        pedido.invoice_id_qbo = '47349'
        _db.session.commit()

        resp = logged_client.post(f'/pedidos/{pedido_id}/facturar',
                                  data={'reintentar': '1'},
                                  follow_redirects=True)

        assert resp.status_code == 200
        mock_post.assert_not_called()


@patch('app.N8N_WEBHOOK_URL', 'http://test-n8n.local/webhook')
@patch('app.requests.post')
def test_factura_normal_sigue_funcionando(mock_post, logged_client, app):
    """Datos completos → la facturación sigue llamando a N8N como siempre."""
    from unittest.mock import MagicMock

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {'invoice_id': 'INV-001'}
    mock_resp.raise_for_status = MagicMock()
    mock_post.return_value = mock_resp

    with app.app_context():
        from app import Pedido
        pedido_id = _crear_pedido_preparado()

        resp = logged_client.post(f'/pedidos/{pedido_id}/facturar',
                                  follow_redirects=True)

        assert resp.status_code == 200
        mock_post.assert_called_once()

        pedido = _db.session.get(Pedido, pedido_id)
        assert pedido.estado == 'facturado'
