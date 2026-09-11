# tests/test_qbo_facturar.py
"""Facturación directa en QuickBooks (`FACTURACION_BACKEND=qbo`) y consulta
de factura por API. El cliente de QBO se reemplaza por un MagicMock: sin red.
El camino por n8n lo cubren test_facturacion*.py, que siguen igual."""
from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock, patch, call

import pytest

import app as app_module
from app import app as flask_app, db as _db
from utils.qbo_client import QboError, QboNoConectado
from tests.test_facturacion_validacion import _crear_pedido_preparado


@pytest.fixture
def app():
    flask_app.config.update(TESTING=True, WTF_CSRF_ENABLED=False,
                            SQLALCHEMY_DATABASE_URI='sqlite:///:memory:')
    with flask_app.app_context():
        _db.create_all()
        from app import Rol, Territorio, Vendedor
        rol = Rol(nombre='super_admin', descripcion='Admin')
        _db.session.add(rol)
        territorio = Territorio(nombre='test', descripcion='Test')
        _db.session.add(territorio)
        _db.session.flush()
        vendedor = Vendedor(username='admin', email='admin@test.com',
                            nombre_completo='Admin Test', rol_id=rol.id,
                            territorio_id=territorio.id, activo=True)
        vendedor.set_password('testpass')
        _db.session.add(vendedor)
        _db.session.commit()
        yield flask_app
        _db.session.remove()
        _db.drop_all()


@pytest.fixture
def logged_client(app):
    client = app.test_client()
    client.post('/login', data={'username': 'admin', 'password': 'testpass'},
                follow_redirects=True)
    return client


@pytest.fixture
def backend_qbo(monkeypatch):
    monkeypatch.setenv('FACTURACION_BACKEND', 'qbo')
    monkeypatch.setenv('QBO_CLIENT_ID', 'cid')
    monkeypatch.setenv('QBO_CLIENT_SECRET', 'sec')
    monkeypatch.setenv('QBO_TASA_USD', '1.78')


def _cliente_qbo(facturas=('5879',), notas=(), respuesta_post=None):
    cliente = MagicMock()

    def query(sql):
        if 'FROM Invoice' in sql:
            return {'Invoice': [{'DocNumber': n} for n in facturas]} if facturas else {}
        return {'CreditMemo': [{'DocNumber': n} for n in notas]} if notas else {}

    cliente.query.side_effect = query
    cliente.post.return_value = respuesta_post or {
        'Invoice': {'Id': '48001', 'DocNumber': '5880'}}
    return cliente


HOY = date(2026, 9, 11)


def _facturar(logged_client, pedido_id, cliente):
    with patch.object(app_module, '_qbo_client', return_value=cliente), \
            patch.object(app_module, '_hoy_local', return_value=HOY):
        return logged_client.post(f'/pedidos/{pedido_id}/facturar', follow_redirects=True)


# ── camino feliz ──────────────────────────────────────────────────────────

def test_factura_directo_en_qbo_y_guarda_id_y_numero(logged_client, app, backend_qbo):
    from app import Pedido
    pedido_id = _crear_pedido_preparado()
    cliente = _cliente_qbo()

    resp = _facturar(logged_client, pedido_id, cliente)

    assert resp.status_code == 200
    assert 'Factura 5880 generada (QBO 48001)'.encode() in resp.data
    pedido = _db.session.get(Pedido, pedido_id)
    assert pedido.estado == 'facturado'
    assert pedido.invoice_id_qbo == '48001'
    assert pedido.doc_number_qbo == '5880'
    assert pedido.fecha_facturacion is not None

    cliente.asegurar_token.assert_called_once()
    cliente.post.assert_called_once()
    path, body = cliente.post.call_args.args
    assert path == 'invoice'
    assert cliente.post.call_args.kwargs['params'] == {'include': 'enhancedAllCustomFields'}
    assert body['DocNumber'] == '5880'
    assert body['CustomerRef'] == {'value': 'QBO-C001'}
    assert body['TxnDate'] == '2026-09-11' and body['DueDate'] == '2026-09-18'
    linea = body['Line'][0]
    assert linea['Description'] == '19.60\t19.50'
    assert linea['SalesItemLineDetail']['Qty'] == 39.1
    assert linea['SalesItemLineDetail']['UnitPrice'] == 25
    assert linea['Amount'] == 977.5
    assert body['TxnTaxDetail']['TxnTaxCodeRef'] == {'value': '14'}
    assert body['PrivateNote'] == f'PesosApp pedido {pedido_id}'


def test_no_llama_a_n8n_con_backend_qbo(logged_client, app, backend_qbo):
    pedido_id = _crear_pedido_preparado()
    with patch.object(app_module, 'requests') as req:
        _facturar(logged_client, pedido_id, _cliente_qbo())
    req.post.assert_not_called()


def test_usa_el_ultimo_numero_local_si_qbo_va_atrasado(logged_client, app, backend_qbo):
    from app import Pedido
    pedido_id = _crear_pedido_preparado()
    # La app ya emitió la 5881 pero QBO todavía devuelve 5879 como máxima.
    otro = Pedido(cliente_id=_db.session.get(Pedido, pedido_id).cliente_id,
                  estado='facturado', doc_number_qbo='5881')
    _db.session.add(otro)
    _db.session.commit()
    cliente = _cliente_qbo(facturas=('5879',))
    _facturar(logged_client, pedido_id, cliente)
    assert cliente.post.call_args.args[1]['DocNumber'] == '5882'


def test_cliente_usd_fija_la_tasa_del_dia_y_factura_exento(logged_client, app, backend_qbo):
    from app import Pedido
    pedido_id = _crear_pedido_preparado()
    pedido = _db.session.get(Pedido, pedido_id)
    pedido.cliente.moneda = 'USD'
    _db.session.commit()
    cliente = _cliente_qbo()
    with patch('utils.qbo_tasa.asegurar_tasa_usd') as tasa:
        _facturar(logged_client, pedido_id, cliente)
    tasa.assert_called_once_with(cliente, HOY, Decimal('1.78'))
    body = cliente.post.call_args.args[1]
    assert body['CurrencyRef'] == {'value': 'USD'}
    assert body['TxnTaxDetail']['TxnTaxCodeRef'] == {'value': '13'}
    assert body['CustomField'][3]['StringValue'] == '2'


def test_cliente_xcg_no_toca_la_tasa(logged_client, app, backend_qbo):
    pedido_id = _crear_pedido_preparado()
    with patch('utils.qbo_tasa.asegurar_tasa_usd') as tasa:
        _facturar(logged_client, pedido_id, _cliente_qbo())
    tasa.assert_not_called()


def test_fallo_al_fijar_la_tasa_no_frena_la_factura(logged_client, app, backend_qbo):
    from app import Pedido
    pedido_id = _crear_pedido_preparado()
    _db.session.get(Pedido, pedido_id).cliente.moneda = 'USD'
    _db.session.commit()
    cliente = _cliente_qbo()
    with patch('utils.qbo_tasa.asegurar_tasa_usd', side_effect=QboError('caído')):
        _facturar(logged_client, pedido_id, cliente)
    assert _db.session.get(Pedido, pedido_id).estado == 'facturado'


# ── errores ───────────────────────────────────────────────────────────────

def _fault(codigo, mensaje, detalle=''):
    return QboError(mensaje, status=400, fault={'Error': [
        {'Message': mensaje, 'Detail': detalle, 'code': codigo}]})


def test_numero_duplicado_reintenta_una_vez_con_el_siguiente(logged_client, app, backend_qbo):
    from app import Pedido
    pedido_id = _crear_pedido_preparado()
    cliente = _cliente_qbo()
    cliente.post.side_effect = [
        _fault('6240', 'Duplicate Document Number Error'),
        {'Invoice': {'Id': '48002', 'DocNumber': '5881'}},
    ]
    resp = _facturar(logged_client, pedido_id, cliente)
    numeros = [c.args[1]['DocNumber'] for c in cliente.post.call_args_list]
    assert numeros == ['5880', '5881']
    assert _db.session.get(Pedido, pedido_id).doc_number_qbo == '5881'
    assert b'Factura 5881 generada' in resp.data


def test_segundo_duplicado_no_reintenta_mas(logged_client, app, backend_qbo):
    from app import Pedido
    pedido_id = _crear_pedido_preparado()
    cliente = _cliente_qbo()
    cliente.post.side_effect = _fault('6240', 'Duplicate Document Number Error')
    resp = _facturar(logged_client, pedido_id, cliente)
    assert cliente.post.call_count == 2
    assert _db.session.get(Pedido, pedido_id).estado == 'preparado'
    assert 'QuickBooks rechazó la factura'.encode() in resp.data


def test_fault_de_validacion_deja_el_pedido_como_estaba(logged_client, app, backend_qbo):
    from app import Pedido
    pedido_id = _crear_pedido_preparado()
    cliente = _cliente_qbo()
    cliente.post.side_effect = _fault('6070', 'Amount is not equal to UnitPrice * Qty',
                                      'Line 1: 977.50 vs 977.49')
    resp = _facturar(logged_client, pedido_id, cliente)
    pedido = _db.session.get(Pedido, pedido_id)
    assert pedido.estado == 'preparado' and pedido.invoice_id_qbo is None
    assert 'Amount is not equal to UnitPrice'.encode() in resp.data
    assert b'977.49' in resp.data


def test_sin_conexion_pide_conectar_y_registra_el_error(logged_client, app, backend_qbo):
    from app import Pedido, QboConexion
    pedido_id = _crear_pedido_preparado()
    cliente = _cliente_qbo()
    cliente.asegurar_token.side_effect = QboNoConectado()
    resp = _facturar(logged_client, pedido_id, cliente)
    assert 'QuickBooks no está conectado'.encode() in resp.data
    assert _db.session.get(Pedido, pedido_id).estado == 'preparado'
    assert 'no está conectado' in _db.session.get(QboConexion, 1).ultimo_error
    cliente.post.assert_not_called()


def test_sin_credenciales_con_backend_qbo_cae_a_n8n(logged_client, app, monkeypatch):
    """`FACTURACION_BACKEND=qbo` sin QBO_CLIENT_ID no rompe: sigue por n8n."""
    monkeypatch.setenv('FACTURACION_BACKEND', 'qbo')
    monkeypatch.delenv('QBO_CLIENT_ID', raising=False)
    pedido_id = _crear_pedido_preparado()
    with patch.object(app_module, 'N8N_WEBHOOK_URL', 'http://n8n.local/hook'), \
            patch.object(app_module.requests, 'post') as post:
        post.return_value.status_code = 200
        post.return_value.json.return_value = {'Invoice': {'Id': '1', 'DocNumber': '2'}}
        logged_client.post(f'/pedidos/{pedido_id}/facturar', follow_redirects=True)
    post.assert_called_once()


def test_timeout_de_qbo_muestra_mensaje_y_no_marca(logged_client, app, backend_qbo):
    import requests as req_lib
    from app import Pedido
    pedido_id = _crear_pedido_preparado()
    cliente = _cliente_qbo()
    cliente.post.side_effect = req_lib.Timeout('lento')
    resp = _facturar(logged_client, pedido_id, cliente)
    assert b'Timeout' in resp.data and b'QuickBooks' in resp.data
    assert _db.session.get(Pedido, pedido_id).estado == 'preparado'


# ── lock entre workers ────────────────────────────────────────────────────

def test_lock_solo_en_postgres(app):
    with patch.object(app_module.db.session, 'execute') as execute:
        app_module._qbo_bloquear_facturacion()          # sqlite: nada
        execute.assert_not_called()
        with patch.object(app_module.db.engine.dialect, 'name', 'postgresql'):
            app_module._qbo_bloquear_facturacion()
        execute.assert_called_once()
        sql, params = execute.call_args.args
        assert 'pg_advisory_xact_lock' in str(sql)
        assert params == {'clave': app_module.QBO_LOCK_FACTURACION}


# ── consulta de factura ───────────────────────────────────────────────────

def test_obtener_factura_por_api_devuelve_el_invoice(app, backend_qbo):
    cliente = MagicMock()
    cliente.get.return_value = {'Invoice': {'Id': '47997', 'DocNumber': '5879'}}
    with patch.object(app_module, '_qbo_client', return_value=cliente), \
            patch.object(app_module.requests, 'post') as post:
        datos = app_module._obtener_factura_qbo('47997')
    assert datos == {'Invoice': {'Id': '47997', 'DocNumber': '5879'}}
    cliente.get.assert_called_once_with('invoice/47997')
    post.assert_not_called()


def test_obtener_factura_por_api_devuelve_none_si_falla(app, backend_qbo):
    cliente = MagicMock()
    cliente.get.side_effect = QboError('no existe', status=400)
    with patch.object(app_module, '_qbo_client', return_value=cliente):
        assert app_module._obtener_factura_qbo('1') is None


def test_obtener_factura_con_backend_n8n_sigue_usando_el_webhook(app, monkeypatch):
    monkeypatch.setenv('FACTURACION_BACKEND', 'n8n')
    with patch.object(app_module, 'N8N_INVOICE_FETCH_WEBHOOK_URL', 'http://n8n.local/fetch'), \
            patch.object(app_module.requests, 'post') as post:
        post.return_value.json.return_value = {'Invoice': {'Id': '1'}}
        assert app_module._obtener_factura_qbo('1') == {'Invoice': {'Id': '1'}}
    post.assert_called_once()
