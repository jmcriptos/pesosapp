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
