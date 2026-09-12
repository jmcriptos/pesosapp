# tests/test_seguridad.py
"""Arreglos de seguridad del 2026-09-12: IP real del cliente, límite de
login por cuenta, permisos fail-closed y tokens de QuickBooks cifrados."""
from datetime import datetime
from unittest.mock import patch

import pytest
from cryptography.fernet import Fernet

import app as app_module
from app import app as flask_app, db as _db, QboConexion, _QboStoreDb
from utils.qbo_client import QboNoConectado


@pytest.fixture
def app():
    flask_app.config.update(TESTING=True, WTF_CSRF_ENABLED=False,
                            SQLALCHEMY_DATABASE_URI='sqlite:///:memory:')
    with flask_app.app_context():
        _db.create_all()
        from app import Rol, Territorio, Vendedor
        rol = Rol(nombre='super_admin', descripcion='Admin')
        territorio = Territorio(nombre='test', descripcion='Test')
        _db.session.add_all([rol, territorio])
        _db.session.flush()
        v = Vendedor(username='admin', email='admin@test.com', nombre_completo='Admin',
                     rol_id=rol.id, territorio_id=territorio.id, activo=True)
        v.set_password('testpass')
        _db.session.add(v)
        _db.session.commit()
        yield flask_app
        _db.session.remove()
        _db.drop_all()


# ── IP del cliente ────────────────────────────────────────────────────────

def test_ip_es_la_ultima_de_x_forwarded_for(app, monkeypatch):
    """Heroku agrega la IP real al final; lo anterior lo escribe el cliente."""
    monkeypatch.delenv('TRUST_CF_CONNECTING_IP', raising=False)
    with app.test_request_context(headers={'X-Forwarded-For': '1.1.1.1, 2.2.2.2, 9.9.9.9'}):
        assert app_module._client_ip() == '9.9.9.9'


def test_cf_connecting_ip_se_ignora_sin_la_bandera(app, monkeypatch):
    monkeypatch.delenv('TRUST_CF_CONNECTING_IP', raising=False)
    with app.test_request_context(headers={'CF-Connecting-IP': '1.1.1.1',
                                           'X-Forwarded-For': '9.9.9.9'}):
        assert app_module._client_ip() == '9.9.9.9'


def test_cf_connecting_ip_con_la_bandera(app, monkeypatch):
    monkeypatch.setenv('TRUST_CF_CONNECTING_IP', '1')
    with app.test_request_context(headers={'CF-Connecting-IP': '1.1.1.1',
                                           'X-Forwarded-For': '9.9.9.9'}):
        assert app_module._client_ip() == '1.1.1.1'


def test_sin_cabeceras_usa_remote_addr(app):
    with app.test_request_context(environ_base={'REMOTE_ADDR': '5.5.5.5'}):
        assert app_module._client_ip() == '5.5.5.5'


# ── límite de login por cuenta ────────────────────────────────────────────

def test_clave_por_cuenta_normaliza_el_usuario(app):
    with app.test_request_context(method='POST', data={'username': '  Admin '}):
        assert app_module._login_username_key() == 'user:admin'
    with app.test_request_context(method='POST', data={}, headers={'X-Forwarded-For': '9.9.9.9'}):
        assert app_module._login_username_key() == 'ip:9.9.9.9'


def test_solo_descuenta_intentos_fallidos():
    class R:
        def __init__(self, status):
            self.status_code = status
    assert app_module._login_fallido(R(200)) is True
    assert app_module._login_fallido(R(302)) is False


# El limitador se construye DESACTIVADO cuando FLASK_ENV=testing (no registra
# sus hooks), y Flask no admite registrar hooks después de la primera
# petición. La prueba de punta a punta corre en un subproceso con el
# limitador activo y una base sqlite en memoria.
ESCENARIO_LIMITE = r"""
import os, sys
os.environ.update(FLASK_ENV='development', SECRET_KEY='x',
                  DATABASE_URL='sqlite:///:memory:', RATELIMIT_STORAGE_URI='memory://')
os.environ.pop('TRUST_CF_CONNECTING_IP', None)
import app as m
m.app.config.update(TESTING=True, WTF_CSRF_ENABLED=False)
assert m.limiter is not None and m.limiter.enabled
with m.app.app_context():
    m.db.create_all()
    rol = m.Rol(nombre='super_admin', descripcion='A'); t = m.Territorio(nombre='t', descripcion='T')
    m.db.session.add_all([rol, t]); m.db.session.flush()
    v = m.Vendedor(username='admin', email='a@t.com', nombre_completo='A', rol_id=rol.id,
                   territorio_id=t.id, activo=True)
    v.set_password('testpass'); m.db.session.add(v); m.db.session.commit()
    c = m.app.test_client()
    # Cinco fallos sobre la misma cuenta desde IPs distintas.
    codigos = [c.post('/login', data={'username': 'admin', 'password': 'mala'},
                      headers={'X-Forwarded-For': f'10.0.0.{i}'}).status_code for i in range(5)]
    sexto = c.post('/login', data={'username': 'admin', 'password': 'mala'},
                   headers={'X-Forwarded-For': '10.0.0.99'}).status_code
    otra = c.post('/login', data={'username': 'otro', 'password': 'mala'},
                  headers={'X-Forwarded-For': '10.0.0.100'}).status_code
    # Logins correctos, cada uno desde su IP, no consumen el límite por cuenta.
    m.limiter.reset()
    buenos = [m.app.test_client().post('/login', data={'username': 'admin', 'password': 'testpass'},
              headers={'X-Forwarded-For': f'10.1.0.{i}'}).status_code for i in range(6)]
print(repr((codigos, sexto, otra, buenos)))
"""


@pytest.mark.skipif(app_module.limiter is None, reason='flask_limiter no instalado')
def test_la_cuenta_se_bloquea_aunque_cambie_la_ip_y_los_logins_buenos_no_consumen():
    import subprocess, sys, os, ast
    res = subprocess.run([sys.executable, '-c', ESCENARIO_LIMITE], capture_output=True,
                         text=True, cwd=os.path.join(os.path.dirname(__file__), '..'), timeout=120)
    assert res.returncode == 0, res.stderr[-2000:]
    codigos, sexto, otra, buenos = ast.literal_eval(res.stdout.strip().splitlines()[-1])
    assert all(c != 429 for c in codigos), codigos     # los cinco primeros pasan
    assert sexto == 429                                  # el sexto, bloqueado
    assert otra != 429                                   # otra cuenta no se ve afectada
    assert buenos == [302] * 6                           # los correctos no descuentan


# ── permisos fail-closed ──────────────────────────────────────────────────

class _NoVendedor:
    """Un usuario autenticado que no es Vendedor (el viejo «usuario legacy»)."""
    is_authenticated = True
    is_active = True
    is_anonymous = False


def test_un_no_vendedor_no_tiene_ningun_permiso(app):
    with app.test_request_context():
        with patch.object(app_module, 'current_user', _NoVendedor()):
            perms = app_module.inject_permissions()
            assert perms['puede_crear']('pedidos') is False
            assert perms['puede_editar']('pedidos') is False
            assert perms['puede_eliminar']('pedidos') is False


def test_un_vendedor_conserva_sus_permisos(app):
    from app import Vendedor
    admin = Vendedor.query.filter_by(username='admin').one()
    with app.test_request_context():
        with patch.object(app_module, 'current_user', admin):
            perms = app_module.inject_permissions()
            assert perms['puede_crear']('pedidos') == admin.tiene_permiso('pedidos', 'crear')


# ── tokens cifrados ───────────────────────────────────────────────────────

CLAVE = Fernet.generate_key().decode()


def _tokens():
    return {'realm_id': '123', 'access_token': 'acc-secreto', 'refresh_token': 'ref-secreto',
            'access_expires_at': datetime(2026, 9, 12, 16), 'refresh_expires_at': datetime(2026, 12, 20)}


def test_con_clave_los_tokens_se_guardan_cifrados(app, monkeypatch):
    monkeypatch.setenv('QBO_TOKEN_KEY', CLAVE)
    _QboStoreDb().guardar(_tokens())
    fila = _db.session.get(QboConexion, 1)
    assert fila.access_token.startswith('enc:') and 'acc-secreto' not in fila.access_token
    assert fila.refresh_token.startswith('enc:') and 'ref-secreto' not in fila.refresh_token
    assert fila.realm_id == '123'                      # el realm no es secreto
    assert _QboStoreDb().cargar() == _tokens()


def test_sin_clave_se_guardan_en_texto_plano_y_la_pantalla_avisa(app, monkeypatch):
    monkeypatch.delenv('QBO_TOKEN_KEY', raising=False)
    monkeypatch.setenv('QBO_CLIENT_ID', 'cid')
    monkeypatch.setenv('QBO_CLIENT_SECRET', 'sec')
    _QboStoreDb().guardar(_tokens())
    assert _db.session.get(QboConexion, 1).refresh_token == 'ref-secreto'
    client = app.test_client()
    client.post('/login', data={'username': 'admin', 'password': 'testpass'})
    html = client.get('/admin/quickbooks').data.decode()
    assert 'Tokens cifrados en la base' in html and 'Texto plano' in html


def test_fila_vieja_en_texto_plano_se_lee_con_clave_y_se_recifra_al_guardar(app, monkeypatch):
    monkeypatch.delenv('QBO_TOKEN_KEY', raising=False)
    _QboStoreDb().guardar(_tokens())                  # como quedó antes del cifrado
    monkeypatch.setenv('QBO_TOKEN_KEY', CLAVE)
    tokens = _QboStoreDb().cargar()
    assert tokens['refresh_token'] == 'ref-secreto'
    _QboStoreDb().guardar(tokens)                     # el próximo refresco
    assert _db.session.get(QboConexion, 1).refresh_token.startswith('enc:')


def test_tokens_cifrados_sin_clave_es_no_conectado(app, monkeypatch):
    monkeypatch.setenv('QBO_TOKEN_KEY', CLAVE)
    _QboStoreDb().guardar(_tokens())
    monkeypatch.delenv('QBO_TOKEN_KEY')
    with pytest.raises(QboNoConectado, match='QBO_TOKEN_KEY'):
        _QboStoreDb().cargar()


def test_clave_equivocada_es_no_conectado(app, monkeypatch):
    monkeypatch.setenv('QBO_TOKEN_KEY', CLAVE)
    _QboStoreDb().guardar(_tokens())
    monkeypatch.setenv('QBO_TOKEN_KEY', Fernet.generate_key().decode())
    with pytest.raises(QboNoConectado, match='no corresponde'):
        _QboStoreDb().cargar()


# ── almacén del limitador ─────────────────────────────────────────────────

def test_rediss_agrega_ssl_cert_reqs_solo(monkeypatch):
    monkeypatch.setenv('RATELIMIT_STORAGE_URI', 'rediss://:pw@host:6380')
    assert app_module._ratelimit_storage_uri() == 'rediss://:pw@host:6380?ssl_cert_reqs=none'
    monkeypatch.setenv('RATELIMIT_STORAGE_URI', 'rediss://:pw@host:6380?ssl_cert_reqs=none')
    assert app_module._ratelimit_storage_uri() == 'rediss://:pw@host:6380?ssl_cert_reqs=none'


def test_redis_sin_tls_y_memoria_van_tal_cual(monkeypatch):
    monkeypatch.setenv('RATELIMIT_STORAGE_URI', 'redis://:pw@host:6379')
    assert app_module._ratelimit_storage_uri() == 'redis://:pw@host:6379'
    monkeypatch.delenv('RATELIMIT_STORAGE_URI')
    assert app_module._ratelimit_storage_uri() == 'memory://'


def test_uri_invalida_no_tira_la_app():
    """Reproduce el `<REDIS_URL>?ssl_cert_reqs=none` literal del 2026-09-12:
    la app tiene que arrancar igual, con el límite en memoria."""
    import subprocess, sys, os
    codigo = (
        "import os; os.environ.update(FLASK_ENV='development', SECRET_KEY='x', "
        "DATABASE_URL='sqlite:///:memory:', RATELIMIT_STORAGE_URI='<REDIS_URL>?ssl_cert_reqs=none'); "
        "import app; print('ARRANCO', app.limiter is not None)"
    )
    res = subprocess.run([sys.executable, '-c', codigo], capture_output=True, text=True,
                         cwd=os.path.join(os.path.dirname(__file__), '..'), timeout=120)
    assert res.returncode == 0, res.stderr[-1500:]
    assert 'ARRANCO True' in res.stdout
    assert 'RATELIMIT_STORAGE_URI inválida' in res.stderr
