"""Tests de la obtención de facturas desde QBO vía n8n y de la ruta del PDF."""
import os
from unittest.mock import MagicMock, patch

import pytest

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
        yield flask_app
        _db.drop_all()


def _crear_pedido_facturado(invoice_id='47349', doc_number='5816'):
    from app import Rol, Territorio, Vendedor, Cliente, Pedido

    rol = Rol(nombre='super_admin', descripcion='Admin')
    _db.session.add(rol)
    territorio = Territorio(nombre='t', descripcion='T')
    _db.session.add(territorio)
    _db.session.flush()

    vendedor = Vendedor(username='admin', email='a@t.com', nombre_completo='Admin',
                        rol_id=rol.id, territorio_id=territorio.id, activo=True)
    vendedor.set_password('testpass')
    _db.session.add(vendedor)

    cliente = Cliente(nombre='Centrum', territorio_id=territorio.id, qbo_id='1570')
    _db.session.add(cliente)
    _db.session.flush()

    pedido = Pedido(cliente_id=cliente.id, estado='facturado',
                    invoice_id_qbo=invoice_id, doc_number_qbo=doc_number)
    _db.session.add(pedido)
    _db.session.commit()
    return pedido.id


def _login(app):
    client = app.test_client()
    client.post('/login', data={'username': 'admin', 'password': 'testpass'},
                follow_redirects=True)
    return client


@patch('app.N8N_INVOICE_FETCH_WEBHOOK_URL', 'http://n8n.local/fetch')
@patch('app.requests.post')
def test_obtener_factura_devuelve_el_invoice(mock_post, app):
    from app import _obtener_factura_qbo

    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.return_value = {'Invoice': {'Id': '47349', 'DocNumber': '5816'}}
    mock_post.return_value = mock_resp

    with app.app_context():
        factura = _obtener_factura_qbo('47349')

    assert factura['Invoice']['DocNumber'] == '5816'
    assert mock_post.call_args.kwargs['json'] == {'invoice_id': '47349'}


@patch('app.N8N_INVOICE_FETCH_WEBHOOK_URL', '')
def test_obtener_factura_sin_webhook_configurado(app):
    from app import _obtener_factura_qbo

    with app.app_context():
        assert _obtener_factura_qbo('47349') is None


@patch('app.N8N_INVOICE_FETCH_WEBHOOK_URL', 'http://n8n.local/fetch')
@patch('app.requests.post')
def test_obtener_factura_traga_errores_de_red(mock_post, app):
    import requests as req_lib
    from app import _obtener_factura_qbo

    mock_post.side_effect = req_lib.ConnectionError('n8n caído')

    with app.app_context():
        assert _obtener_factura_qbo('47349') is None


@patch('app.N8N_DRIVE_WEBHOOK_URL', 'http://n8n.local/drive')
@patch('app.requests.post')
def test_archivar_manda_el_pdf_en_base64(mock_post, app):
    import base64
    from app import _archivar_factura_drive

    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_post.return_value = mock_resp

    with app.app_context():
        ok = _archivar_factura_drive(b'%PDF-fake', 'Factura_5816.pdf')

    assert ok is True
    enviado = mock_post.call_args.kwargs['json']
    assert enviado['filename'] == 'Factura_5816.pdf'
    assert base64.b64decode(enviado['pdf_base64']) == b'%PDF-fake'


@patch('app.N8N_DRIVE_WEBHOOK_URL', 'http://n8n.local/drive')
@patch('app.requests.post')
def test_archivar_no_propaga_fallos(mock_post, app):
    import requests as req_lib
    from app import _archivar_factura_drive

    mock_post.side_effect = req_lib.Timeout('drive lento')

    with app.app_context():
        assert _archivar_factura_drive(b'%PDF-fake', 'x.pdf') is False


@patch('app.N8N_INVOICE_FETCH_WEBHOOK_URL', 'http://n8n.local/fetch')
@patch('app.N8N_DRIVE_WEBHOOK_URL', '')
@patch('app.requests.post')
def test_ruta_devuelve_pdf(mock_post, app):
    import json, pathlib

    factura = json.loads(
        pathlib.Path('tests/fixtures/facturas/xcg_sin_ob.json').read_text())
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.return_value = factura
    mock_post.return_value = mock_resp

    with app.app_context():
        pedido_id = _crear_pedido_facturado()
        client = _login(app)

        resp = client.get(f'/pedidos/{pedido_id}/factura.pdf')

    assert resp.status_code == 200
    assert resp.mimetype == 'application/pdf'
    assert resp.data[:5] == b'%PDF-'
    assert 'Factura_5814.pdf' in resp.headers['Content-Disposition']


def test_ruta_404_sin_invoice_id(app):
    with app.app_context():
        pedido_id = _crear_pedido_facturado(invoice_id=None, doc_number=None)
        client = _login(app)

        resp = client.get(f'/pedidos/{pedido_id}/factura.pdf')

    assert resp.status_code == 404


@patch('app.N8N_INVOICE_FETCH_WEBHOOK_URL', 'http://n8n.local/fetch')
@patch('app.requests.post')
def test_ruta_502_si_n8n_falla(mock_post, app):
    import requests as req_lib
    mock_post.side_effect = req_lib.ConnectionError('n8n caído')

    with app.app_context():
        pedido_id = _crear_pedido_facturado()
        client = _login(app)

        resp = client.get(f'/pedidos/{pedido_id}/factura.pdf')

    assert resp.status_code == 502
