# tests/test_qbo_conexion.py
"""Conexión con QuickBooks en app.py: modelo `QboConexion`, token store,
configuración desde el entorno, selector de backend, último número local y
el comando `qbo-fijar-tasa`. Sin red."""
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest

import app as app_module
from app import app as flask_app, db as _db, QboConexion, _QboStoreDb


@pytest.fixture
def app():
    """Propio y no el de conftest: aquel usa `engine.table_names()`, que
    SQLAlchemy 2 ya no tiene (mismo motivo por el que cada test del repo
    define el suyo)."""
    flask_app.config.update(TESTING=True, WTF_CSRF_ENABLED=False,
                            SQLALCHEMY_DATABASE_URI='sqlite:///:memory:')
    with flask_app.app_context():
        _db.create_all()
        from app import Rol, Territorio
        _db.session.add(Rol(nombre='super_admin', descripcion='Admin'))
        _db.session.add(Territorio(nombre='test', descripcion='Test'))
        _db.session.commit()
        yield flask_app
        _db.session.remove()
        _db.drop_all()


def _tokens():
    return {
        'realm_id': '123', 'access_token': 'acc', 'refresh_token': 'ref',
        'access_expires_at': datetime(2026, 9, 11, 16, 0),
        'refresh_expires_at': datetime(2026, 12, 20, 15, 0),
    }


# ── token store ───────────────────────────────────────────────────────────

def test_store_vacio_devuelve_none(app):
    assert _QboStoreDb().cargar() is None


def test_store_guarda_en_la_fila_1_y_relee(app):
    store = _QboStoreDb()
    store.guardar(_tokens())
    fila = _db.session.get(QboConexion, 1)
    assert fila.realm_id == '123'
    assert fila.refresh_token == 'ref'
    assert store.cargar() == _tokens()


def test_store_sobrescribe_la_misma_fila_al_rotar(app):
    store = _QboStoreDb()
    store.guardar(_tokens())
    store.guardar(dict(_tokens(), access_token='acc2', refresh_token='ref2'))
    assert QboConexion.query.count() == 1
    assert store.cargar()['refresh_token'] == 'ref2'


def test_fila_sin_refresh_token_cuenta_como_no_conectada(app):
    _db.session.add(QboConexion(id=1, realm_id='123', ultimo_error='algo'))
    _db.session.commit()
    assert _QboStoreDb().cargar() is None


def test_guardar_limpia_el_ultimo_error(app):
    app_module._qbo_registrar_error('token vencido')
    assert _db.session.get(QboConexion, 1).ultimo_error == 'token vencido'
    _QboStoreDb().guardar(_tokens())
    fila = _db.session.get(QboConexion, 1)
    assert fila.ultimo_error is None and fila.ultimo_error_en is None


# ── configuración y backend ───────────────────────────────────────────────

def test_config_none_sin_credenciales(monkeypatch):
    monkeypatch.delenv('QBO_CLIENT_ID', raising=False)
    monkeypatch.delenv('QBO_CLIENT_SECRET', raising=False)
    assert app_module._qbo_config() is None
    assert app_module._qbo_client() is None


def test_config_lee_el_entorno(monkeypatch):
    monkeypatch.setenv('QBO_CLIENT_ID', 'cid')
    monkeypatch.setenv('QBO_CLIENT_SECRET', 'sec')
    monkeypatch.setenv('QBO_ENVIRONMENT', 'Production')
    monkeypatch.setenv('QBO_REDIRECT_URI', 'https://app/cb')
    monkeypatch.setenv('QBO_MINOR_VERSION', '75')
    monkeypatch.setenv('QBO_TIMEOUT', '12')
    cfg = app_module._qbo_config()
    assert cfg.client_id == 'cid' and cfg.client_secret == 'sec'
    assert cfg.environment == 'production'
    assert cfg.redirect_uri == 'https://app/cb'
    assert cfg.minor_version == 75 and cfg.timeout == 12.0
    assert app_module._qbo_client() is not None


def test_backend_por_defecto_es_n8n(monkeypatch):
    monkeypatch.delenv('FACTURACION_BACKEND', raising=False)
    monkeypatch.delenv('QB_SALES_BACKEND', raising=False)
    assert app_module._facturacion_backend() == 'n8n'
    assert app_module._qb_sales_backend() == 'n8n'


def test_backend_qbo_sin_credenciales_cae_a_n8n(monkeypatch):
    monkeypatch.setenv('FACTURACION_BACKEND', 'qbo')
    monkeypatch.delenv('QBO_CLIENT_ID', raising=False)
    monkeypatch.delenv('QBO_CLIENT_SECRET', raising=False)
    assert app_module._facturacion_backend() == 'n8n'


def test_backend_qbo_con_credenciales(monkeypatch):
    monkeypatch.setenv('FACTURACION_BACKEND', 'QBO')
    monkeypatch.setenv('QB_SALES_BACKEND', 'qbo')
    monkeypatch.setenv('QBO_CLIENT_ID', 'cid')
    monkeypatch.setenv('QBO_CLIENT_SECRET', 'sec')
    assert app_module._facturacion_backend() == 'qbo'
    assert app_module._qb_sales_backend() == 'qbo'


def test_tasa_usd_desde_entorno_con_fallback(monkeypatch):
    monkeypatch.setenv('QBO_TASA_USD', '1.79')
    assert str(app_module._qbo_tasa_usd()) == '1.79'
    monkeypatch.setenv('QBO_TASA_USD', 'no-es-numero')
    assert str(app_module._qbo_tasa_usd()) == '1.78'
    monkeypatch.delenv('QBO_TASA_USD')
    assert str(app_module._qbo_tasa_usd()) == '1.78'


# ── último número local ───────────────────────────────────────────────────

def _pedido(doc_number, cliente_id):
    from app import Pedido
    return Pedido(cliente_id=cliente_id, estado='facturado', doc_number_qbo=doc_number)


@pytest.fixture
def cliente_id(app):
    from app import Cliente, Territorio
    territorio = Territorio.query.first()
    cliente = Cliente(nombre='Cliente', territorio_id=territorio.id, qbo_id='1')
    _db.session.add(cliente)
    _db.session.commit()
    return cliente.id


def test_ultimo_doc_number_local_none_sin_facturas(app):
    assert app_module._ultimo_doc_number_local() is None


def test_ultimo_doc_number_local_es_el_mayor_numerico(app, cliente_id):
    _db.session.add_all([
        _pedido('5879', cliente_id), _pedido('5881', cliente_id),
        _pedido(None, cliente_id), _pedido('N/A', cliente_id), _pedido('5880', cliente_id),
    ])
    _db.session.commit()
    assert app_module._ultimo_doc_number_local() == 5881


# ── comando qbo-fijar-tasa ────────────────────────────────────────────────

def test_cli_fija_hoy_y_manana(app, monkeypatch):
    monkeypatch.setenv('QBO_TASA_USD', '1.78')
    cliente = MagicMock()
    cliente.get.return_value = {'ExchangeRate': {'Rate': 1.79, 'AsOfDate': '2026-09-11', 'SyncToken': '0'}}
    with patch.object(app_module, '_qbo_client', return_value=cliente), \
            patch.object(app_module, '_hoy_local', return_value=datetime(2026, 9, 11).date()):
        resultado = app.test_cli_runner().invoke(args=['qbo-fijar-tasa'])
    assert resultado.exit_code == 0, resultado.output
    assert '2026-09-11: fijada en 1.78' in resultado.output
    assert '2026-09-12: fijada en 1.78' in resultado.output
    fechas = [c.kwargs['params']['asofdate'] for c in cliente.get.call_args_list]
    assert fechas == ['2026-09-11', '2026-09-12']
    assert cliente.post.call_count == 2


def test_cli_sin_credenciales_falla_con_mensaje(app):
    with patch.object(app_module, '_qbo_client', return_value=None):
        resultado = app.test_cli_runner().invoke(args=['qbo-fijar-tasa'])
    assert resultado.exit_code != 0
    assert 'QBO_CLIENT_ID' in resultado.output
