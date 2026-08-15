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
@patch('app.requests.post')
def test_obtener_factura_sin_webhook_configurado(mock_post, app):
    from app import _obtener_factura_qbo

    with app.app_context():
        assert _obtener_factura_qbo('47349') is None

    # Sin URL no se debe postear a ningún lado (ni a '').
    assert mock_post.call_count == 0


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


def _factura_fixture(nombre='xcg_sin_ob.json'):
    import json, pathlib
    return json.loads(
        pathlib.Path(f'tests/fixtures/facturas/{nombre}').read_text())


@patch('app.N8N_INVOICE_FETCH_WEBHOOK_URL', 'http://n8n.local/fetch')
@patch('app.N8N_DRIVE_WEBHOOK_URL', '')
@patch('app.requests.post')
def test_ruta_devuelve_pdf(mock_post, app):
    factura = _factura_fixture()
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.return_value = factura
    mock_post.return_value = mock_resp

    with app.app_context():
        pedido_id = _crear_pedido_facturado(invoice_id='47347')
        client = _login(app)

        resp = client.get(f'/pedidos/{pedido_id}/factura.pdf')

    assert resp.status_code == 200
    assert resp.mimetype == 'application/pdf'
    assert resp.data[:5] == b'%PDF-'
    assert 'Factura_5814.pdf' in resp.headers['Content-Disposition']
    # Documento financiero: no debe quedar cacheado tras cerrar sesión.
    assert 'no-store' in resp.headers['Cache-Control']
    assert 'private' in resp.headers['Cache-Control']


@patch('app.N8N_INVOICE_FETCH_WEBHOOK_URL', 'http://n8n.local/fetch')
@patch('app.N8N_DRIVE_WEBHOOK_URL', 'http://n8n.local/drive')
@patch('app.requests.post')
def test_ruta_502_si_qbo_devuelve_otra_factura(mock_post, app):
    """Un payload que no es la factura pedida no se renderiza ni se archiva."""
    otra = _factura_fixture('usd.json')  # Id 47340, no 47347
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.return_value = otra
    mock_post.return_value = mock_resp

    with app.app_context():
        pedido_id = _crear_pedido_facturado(invoice_id='47347')
        client = _login(app)

        resp = client.get(f'/pedidos/{pedido_id}/factura.pdf')

    assert resp.status_code == 502
    # Solo la consulta a QBO: nada se subió a Drive.
    assert mock_post.call_count == 1
    assert mock_post.call_args_list[0].args[0] == 'http://n8n.local/fetch'


@patch('app.N8N_INVOICE_FETCH_WEBHOOK_URL', 'http://n8n.local/fetch')
@patch('app.N8N_DRIVE_WEBHOOK_URL', 'http://n8n.local/drive')
@patch('app.requests.post')
def test_ruta_502_si_qbo_devuelve_payload_vacio(mock_post, app):
    """`{"success": true}` no debe convertirse en una factura en blanco."""
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.return_value = {'success': True}
    mock_post.return_value = mock_resp

    with app.app_context():
        pedido_id = _crear_pedido_facturado(invoice_id='47347')
        client = _login(app)

        resp = client.get(f'/pedidos/{pedido_id}/factura.pdf')

    assert resp.status_code == 502
    assert mock_post.call_count == 1


@patch('app.N8N_INVOICE_FETCH_WEBHOOK_URL', 'http://n8n.local/fetch')
@patch('app.N8N_DRIVE_WEBHOOK_URL', 'http://n8n.local/drive')
@patch('app.requests.post')
def test_ruta_devuelve_pdf_aunque_falle_el_archivado(mock_post, app):
    """Drive configurado pero caído: el usuario igual recibe su PDF."""
    import requests as req_lib

    factura = _factura_fixture()
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.return_value = factura

    # Tanto la consulta a QBO como el archivado pasan por app.requests.post.
    def _post(url, *args, **kwargs):
        if url == 'http://n8n.local/drive':
            raise req_lib.Timeout('drive caído')
        return mock_resp

    mock_post.side_effect = _post

    with app.app_context():
        pedido_id = _crear_pedido_facturado(invoice_id='47347')
        client = _login(app)

        resp = client.get(f'/pedidos/{pedido_id}/factura.pdf')

    assert resp.status_code == 200
    assert resp.mimetype == 'application/pdf'
    assert resp.data[:5] == b'%PDF-'
    # Se intentó archivar de verdad (no se tomó la rama de "sin configurar").
    assert any(c.args[0] == 'http://n8n.local/drive' for c in mock_post.call_args_list)


@patch('app.N8N_INVOICE_FETCH_WEBHOOK_URL', 'http://n8n.local/fetch')
@patch('app.N8N_DRIVE_WEBHOOK_URL', '')
@patch('app.requests.post')
def test_ruta_500_si_los_datos_de_la_factura_son_ilegibles(mock_post, app):
    """extraer_datos_factura también va dentro del try: nada de 500 sin manejar.

    render_factura_pdf ya llama a extraer_datos_factura internamente, así que
    para aislar la llamada de la ruta se deja pasar la primera y se rompe la
    segunda.
    """
    import utils.factura_pdf as fpdf

    factura = _factura_fixture()
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.return_value = factura
    mock_post.return_value = mock_resp

    real = fpdf.extraer_datos_factura
    llamadas = {'n': 0}

    def _extraer(payload):
        llamadas['n'] += 1
        if llamadas['n'] > 1:  # la de la ruta, después de renderizar
            raise ValueError('payload raro')
        return real(payload)

    with app.app_context():
        pedido_id = _crear_pedido_facturado(invoice_id='47347')
        client = _login(app)

        with patch('utils.factura_pdf.extraer_datos_factura', side_effect=_extraer):
            resp = client.get(f'/pedidos/{pedido_id}/factura.pdf')

    assert llamadas['n'] >= 2, 'la ruta ya no llama a extraer_datos_factura'
    assert resp.status_code == 500
    # 500 manejado (abort con mensaje), no una excepción suelta.
    assert b'No se pudo generar el PDF de la factura.' in resp.data


def test_timeouts_caben_en_el_limite_de_heroku():
    """QBO + Drive corren en serie dentro del request: 30s de router (H12)."""
    import app as app_mod

    assert app_mod.N8N_DRIVE_TIMEOUT <= 8
    assert app_mod.N8N_INVOICE_FETCH_TIMEOUT + app_mod.N8N_DRIVE_TIMEOUT < 30


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


def test_detalles_muestra_boton_factura_si_hay_invoice_id(app):
    with app.app_context():
        pedido_id = _crear_pedido_facturado()
        client = _login(app)

        resp = client.get(f'/pedidos/{pedido_id}/detalles')

    assert b'data-factura-share' in resp.data


def test_detalles_oculta_boton_sin_invoice_id(app):
    with app.app_context():
        pedido_id = _crear_pedido_facturado(invoice_id=None, doc_number=None)
        client = _login(app)

        resp = client.get(f'/pedidos/{pedido_id}/detalles')

    # Sin el 200 el assert de abajo pasaría igual ante un redirect o un 500.
    assert resp.status_code == 200
    assert b'data-factura-share' not in resp.data


# --- Cableado del botón en el cliente (base.js) -----------------------------
# El comportamiento real de la hoja de compartir solo se prueba en dispositivo;
# aquí se verifica la estructura del handler a nivel de fuente.

ROOT = os.path.join(os.path.dirname(__file__), '..')


def _leer_js(rel):
    with open(os.path.join(ROOT, rel), encoding='utf-8') as fh:
        return fh.read()


def _bloque_factura(js):
    inicio = js.index("data-factura-share")
    return js[inicio:inicio + 3000]


def test_share_fallido_cae_en_la_descarga():
    """share() pierde la activación transitoria (~5s) si el PDF tardó: el
    NotAllowedError de iOS tiene que terminar en descarga, no en un alert."""
    bloque = _bloque_factura(_leer_js('static/js/base.js'))

    # La ruta de descarga está factorizada y la usan ambas ramas.
    assert 'function descargar(blob)' in bloque
    assert bloque.count('descargar(blob)') >= 2
    # navigator.share tiene su propio try/catch.
    assert 'catch (shareErr)' in bloque
    assert "shareErr.name === 'AbortError'" in bloque
    # El AbortError del fetch ya no se traga en silencio: solo el de share.
    assert "err.name === 'AbortError'" not in bloque


def test_mensajes_de_error_distintos_por_status():
    bloque = _bloque_factura(_leer_js('static/js/base.js'))

    assert 'resp.status === 403' in bloque
    assert 'resp.status === 404' in bloque
    assert 'resp.status === 502' in bloque
    assert "throw new Error('HTTP '" not in bloque
    assert 'No tiene permiso' in bloque
    assert 'QuickBooks' in bloque


def test_base_min_js_esta_regenerado():
    """base.html carga el .min: si queda viejo, el fix no llega a producción."""
    assert _leer_js('static/js/base.js') == _leer_js('static/js/base.min.js')
