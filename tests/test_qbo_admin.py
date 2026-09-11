# tests/test_qbo_admin.py
"""Pantalla /admin/quickbooks: estado, conectar (OAuth2), callback,
probar y desconectar. Solo super_admin. Cliente de QBO mockeado."""
from unittest.mock import MagicMock, patch

import pytest

import app as app_module
from app import app as flask_app, db as _db, QboConexion, _QboStoreDb
from utils.qbo_client import QboError


@pytest.fixture
def app():
    flask_app.config.update(TESTING=True, WTF_CSRF_ENABLED=False,
                            SQLALCHEMY_DATABASE_URI='sqlite:///:memory:')
    with flask_app.app_context():
        _db.create_all()
        from app import Rol, Territorio, Vendedor
        admin = Rol(nombre='super_admin', descripcion='Admin')
        ventas = Rol(nombre='vendedor', descripcion='Ventas')
        territorio = Territorio(nombre='test', descripcion='Test')
        _db.session.add_all([admin, ventas, territorio])
        _db.session.flush()
        for username, rol in (('admin', admin), ('ventas', ventas)):
            v = Vendedor(username=username, email=f'{username}@test.com',
                         nombre_completo=username.title(), rol_id=rol.id,
                         territorio_id=territorio.id, activo=True)
            v.set_password('testpass')
            _db.session.add(v)
        _db.session.commit()
        yield flask_app
        _db.session.remove()
        _db.drop_all()


def _login(app, username):
    client = app.test_client()
    client.post('/login', data={'username': username, 'password': 'testpass'},
                follow_redirects=True)
    return client


@pytest.fixture
def admin(app):
    return _login(app, 'admin')


@pytest.fixture
def credenciales(monkeypatch):
    monkeypatch.setenv('QBO_CLIENT_ID', 'cid')
    monkeypatch.setenv('QBO_CLIENT_SECRET', 'sec')
    monkeypatch.setenv('QBO_ENVIRONMENT', 'sandbox')
    monkeypatch.setenv('QBO_REDIRECT_URI', 'http://localhost:5000/admin/quickbooks/callback')


def _tokens():
    from datetime import datetime
    return {'realm_id': '123', 'access_token': 'a', 'refresh_token': 'r',
            'access_expires_at': datetime(2026, 9, 11, 16), 'refresh_expires_at': datetime(2026, 12, 20)}


# ── acceso ────────────────────────────────────────────────────────────────

def test_solo_super_admin(app):
    resp = _login(app, 'ventas').get('/admin/quickbooks')
    assert resp.status_code == 302
    assert '/admin/quickbooks' not in resp.headers['Location']


def test_anonimo_va_al_login(app):
    resp = app.test_client().get('/admin/quickbooks')
    assert resp.status_code == 302 and '/login' in resp.headers['Location']


# ── estado ────────────────────────────────────────────────────────────────

def test_estado_sin_credenciales_ni_conexion(admin, monkeypatch):
    monkeypatch.delenv('QBO_CLIENT_ID', raising=False)
    resp = admin.get('/admin/quickbooks')
    assert resp.status_code == 200
    assert b'Faltan QBO_CLIENT_ID' in resp.data
    assert b'No conectado' in resp.data
    assert b'disabled' in resp.data      # el botón Conectar no sirve sin credenciales


def test_estado_conectado_muestra_empresa_y_backends(admin, credenciales, monkeypatch):
    monkeypatch.setenv('FACTURACION_BACKEND', 'qbo')
    _QboStoreDb().guardar(_tokens())
    resp = admin.get('/admin/quickbooks')
    assert b'Conectado' in resp.data and b'123' in resp.data
    assert b'sandbox' in resp.data
    assert b'<code>qbo</code>' in resp.data      # facturación
    assert b'<code>n8n</code>' in resp.data      # ventas
    assert b'Probar conexi' in resp.data and b'Desconectar' in resp.data


def test_estado_muestra_el_ultimo_error(admin, credenciales):
    app_module._qbo_registrar_error('refresh token vencido')
    resp = admin.get('/admin/quickbooks')
    assert b'refresh token vencido' in resp.data


# ── conectar ──────────────────────────────────────────────────────────────

def test_conectar_redirige_a_intuit_con_state_en_sesion(admin, credenciales):
    resp = admin.post('/admin/quickbooks/conectar')
    assert resp.status_code == 302
    destino = resp.headers['Location']
    assert destino.startswith('https://appcenter.intuit.com/connect/oauth2?')
    assert 'client_id=cid' in destino
    with admin.session_transaction() as sess:
        state = sess['qbo_oauth_state']
    assert state and f'state={state}' in destino


def test_conectar_sin_credenciales_avisa(admin, monkeypatch):
    monkeypatch.delenv('QBO_CLIENT_ID', raising=False)
    resp = admin.post('/admin/quickbooks/conectar', follow_redirects=True)
    assert b'Faltan QBO_CLIENT_ID' in resp.data


# ── callback ──────────────────────────────────────────────────────────────

def test_callback_con_state_incorrecto_es_400(admin, credenciales):
    with admin.session_transaction() as sess:
        sess['qbo_oauth_state'] = 'esperado'
    with patch.object(app_module, '_qbo_client') as factory:
        resp = admin.get('/admin/quickbooks/callback?code=abc&realmId=123&state=otro')
    assert resp.status_code == 400
    factory.assert_not_called()


def test_callback_sin_state_en_sesion_es_400(admin, credenciales):
    resp = admin.get('/admin/quickbooks/callback?code=abc&realmId=123&state=x')
    assert resp.status_code == 400


def test_callback_correcto_canjea_y_guarda_quien_conecto(admin, credenciales):
    from app import Vendedor
    with admin.session_transaction() as sess:
        sess['qbo_oauth_state'] = 'estado-ok'
    cliente = MagicMock()
    cliente.canjear_codigo.side_effect = lambda code, realm_id: _QboStoreDb().guardar(
        dict(_tokens(), realm_id=realm_id))
    with patch.object(app_module, '_qbo_client', return_value=cliente):
        resp = admin.get('/admin/quickbooks/callback?code=abc&realmId=999&state=estado-ok',
                         follow_redirects=True)
    cliente.canjear_codigo.assert_called_once_with('abc', '999')
    fila = _db.session.get(QboConexion, 1)
    assert fila.realm_id == '999'
    assert fila.conectado_por == Vendedor.query.filter_by(username='admin').one().id
    assert fila.conectado_en is not None
    assert b'QuickBooks conectado' in resp.data
    with admin.session_transaction() as sess:
        assert 'qbo_oauth_state' not in sess      # el state es de un solo uso


def test_callback_con_error_de_intuit_avisa(admin, credenciales):
    with admin.session_transaction() as sess:
        sess['qbo_oauth_state'] = 's'
    resp = admin.get('/admin/quickbooks/callback?error=access_denied&state=s',
                     follow_redirects=True)
    assert b'access_denied' in resp.data
    assert _db.session.get(QboConexion, 1) is None


def test_callback_canje_rechazado_registra_error(admin, credenciales):
    with admin.session_transaction() as sess:
        sess['qbo_oauth_state'] = 's'
    cliente = MagicMock()
    cliente.canjear_codigo.side_effect = QboError('Intuit rechazó (HTTP 400): invalid_grant',
                                                  status=400, es_auth=True)
    with patch.object(app_module, '_qbo_client', return_value=cliente):
        resp = admin.get('/admin/quickbooks/callback?code=abc&realmId=1&state=s',
                         follow_redirects=True)
    assert b'invalid_grant' in resp.data
    assert 'invalid_grant' in _db.session.get(QboConexion, 1).ultimo_error


# ── probar y desconectar ──────────────────────────────────────────────────

def test_probar_muestra_el_nombre_de_la_empresa(admin, credenciales):
    _QboStoreDb().guardar(_tokens())
    cliente = MagicMock()
    cliente.realm_id = '123'
    cliente.get.return_value = {'CompanyInfo': {'CompanyName': 'Jomar Foods BV'}}
    with patch.object(app_module, '_qbo_client', return_value=cliente):
        resp = admin.post('/admin/quickbooks/probar', follow_redirects=True)
    cliente.get.assert_called_once_with('companyinfo/123')
    assert 'Conexión OK: Jomar Foods BV'.encode() in resp.data


def test_probar_con_error_de_auth_lo_registra(admin, credenciales):
    _QboStoreDb().guardar(_tokens())
    cliente = MagicMock()
    cliente.get.side_effect = QboError('rechazó las credenciales', status=401, es_auth=True)
    with patch.object(app_module, '_qbo_client', return_value=cliente):
        resp = admin.post('/admin/quickbooks/probar', follow_redirects=True)
    assert b'QuickBooks respondi' in resp.data
    assert 'rechazó' in _db.session.get(QboConexion, 1).ultimo_error


def test_desconectar_revoca_y_borra_la_fila(admin, credenciales):
    _QboStoreDb().guardar(_tokens())
    cliente = MagicMock()
    with patch.object(app_module, '_qbo_client', return_value=cliente):
        resp = admin.post('/admin/quickbooks/desconectar', follow_redirects=True)
    cliente.revocar.assert_called_once()
    assert _db.session.get(QboConexion, 1) is None
    assert b'QuickBooks desconectado' in resp.data


def test_desconectar_aunque_revocar_falle(admin, credenciales):
    _QboStoreDb().guardar(_tokens())
    cliente = MagicMock()
    cliente.revocar.side_effect = QboError('Intuit caído')
    with patch.object(app_module, '_qbo_client', return_value=cliente):
        admin.post('/admin/quickbooks/desconectar', follow_redirects=True)
    assert _db.session.get(QboConexion, 1) is None


def test_el_menu_muestra_quickbooks_al_super_admin(app, credenciales):
    assert b'/admin/quickbooks' in _login(app, 'admin').get('/pedidos').data


def test_el_menu_no_muestra_quickbooks_a_un_vendedor(app, credenciales):
    # Un usuario por test: con el app_context del fixture abierto, Flask-Login
    # cachea el usuario cargado en `g` y el segundo login del mismo test lo
    # heredaría.
    assert b'/admin/quickbooks' not in _login(app, 'ventas').get('/pedidos').data
