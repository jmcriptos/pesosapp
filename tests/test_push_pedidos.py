"""Notificaciones push de pedidos nuevos.

Modelo: `vend_a` (vendedor, asignado a Cliente A) carga un pedido. Tienen
dispositivo suscrito: el propio vend_a, `admin` (super_admin), `bodega`
(supervisor) y `fuera` (usuario inactivo). El aviso tiene que llegar a admin y
bodega: no a quien cargó el pedido ni a un usuario dado de baja.

El envío real (pywebpush → Apple/Google) se reemplaza por un doble que anota
a quién se llamó; lo que se prueba es la lógica de la app, no la red.
"""
import base64
import json
import os
from decimal import Decimal
from unittest.mock import patch

import pytest

os.environ.setdefault('SECRET_KEY', 'test-secret')
os.environ.setdefault('FLASK_ENV', 'testing')
os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')

from app import app as flask_app, db as _db  # noqa: E402
from utils import push_notificaciones as push  # noqa: E402

CLAVES = {
    'VAPID_PUBLIC_KEY': 'BPUBLICA',
    'VAPID_PRIVATE_KEY': 'PRIVADA',
    'VAPID_CLAIMS_EMAIL': 'ops@jomar.test',
}
IDS = {}


@pytest.fixture
def app(monkeypatch):
    for clave, valor in CLAVES.items():
        monkeypatch.setenv(clave, valor)
    flask_app.config.update(
        TESTING=True,
        WTF_CSRF_ENABLED=False,
        SQLALCHEMY_DATABASE_URI='sqlite:///:memory:',
    )
    with flask_app.app_context():
        _db.create_all()
        _seed()
        yield flask_app
        _db.session.remove()
        _db.drop_all()


def _seed():
    from app import (Cliente, ClienteVendedor, Producto, Rol, SuscripcionPush,
                     Territorio, Vendedor)

    roles = {n: Rol(nombre=n, descripcion=n) for n in ('super_admin', 'supervisor', 'vendedor')}
    terr = Territorio(nombre='t1', descripcion='T1')
    _db.session.add_all(list(roles.values()) + [terr])
    _db.session.flush()

    def mk_vend(usuario, rol, activo=True):
        v = Vendedor(username=usuario, email=f'{usuario}@t.com', nombre_completo=usuario.title(),
                     rol_id=roles[rol].id, territorio_id=terr.id, activo=activo)
        v.set_password('pw')
        _db.session.add(v)
        return v

    vend_a = mk_vend('vend_a', 'vendedor')
    admin = mk_vend('admin', 'super_admin')
    bodega = mk_vend('bodega', 'supervisor')
    fuera = mk_vend('fuera', 'vendedor', activo=False)

    cliente = Cliente(nombre='Cliente A', territorio_id=terr.id, qbo_id='QBO-A', moneda='XCG')
    producto = Producto(nombre='Producto X', descripcion='d', temperatura='Seco',
                        se_pesa=False, tax_rate=6.0, qbo_id='QBO-PX')
    _db.session.add_all([cliente, producto])
    _db.session.flush()
    _db.session.add(ClienteVendedor(cliente_id=cliente.id, vendedor_id=vend_a.id, activo=True))

    def mk_sus(vendedor, nombre):
        s = SuscripcionPush(vendedor_id=vendedor.id,
                            endpoint=f'https://push.test/{nombre}',
                            p256dh='p256dh-' + nombre, auth='auth-' + nombre)
        _db.session.add(s)
        return s

    for vendedor, nombre in ((vend_a, 'vend_a'), (admin, 'admin'), (bodega, 'bodega'), (fuera, 'fuera')):
        mk_sus(vendedor, nombre)
    _db.session.commit()

    IDS.update(cliente=cliente.id, producto=producto.id, vend_a=vend_a.id,
               admin=admin.id, bodega=bodega.id, fuera=fuera.id)


def _login(app, usuario):
    c = app.test_client()
    c.post('/login', data={'username': usuario, 'password': 'pw'}, follow_redirects=True)
    return c


def _crear_pedido(client, cajas='3'):
    return client.post('/pedidos/nuevo', data={
        'cliente_id': IDS['cliente'],
        'notas': '',
        'productos[0][id]': IDS['producto'],
        'productos[0][cajas]': cajas,
        'productos[0][precio]': '13.00',
    }, follow_redirects=True)


class _Doble:
    """Reemplaza `push_notificaciones.enviar`: anota cada llamada y responde
    según el endpoint (por defecto 'ok')."""

    def __init__(self, respuestas=None):
        self.llamadas = []
        self.respuestas = respuestas or {}

    def __call__(self, suscripcion, payload, claves=None):
        self.llamadas.append((suscripcion, payload))
        return self.respuestas.get(suscripcion['endpoint'], ('ok', None))

    @property
    def endpoints(self):
        return sorted(s['endpoint'] for s, _ in self.llamadas)


# ── Service worker y pantalla ───────────────────────────────────────────────

def test_sw_js_se_sirve_sin_login(app):
    r = app.test_client().get('/sw.js')
    assert r.status_code == 200
    assert 'javascript' in r.headers['Content-Type']
    assert r.headers['Cache-Control'] == 'no-cache'
    assert b"addEventListener('push'" in r.data


def test_pantalla_notificaciones(app):
    c = _login(app, 'admin')
    r = c.get('/mi-cuenta/notificaciones')
    assert r.status_code == 200
    assert 'Activar en este dispositivo' in r.get_data(as_text=True)
    assert 'data-push-configurado="1"' in r.get_data(as_text=True)


def test_pantalla_avisa_cuando_faltan_claves(app, monkeypatch):
    monkeypatch.delenv('VAPID_PRIVATE_KEY')
    c = _login(app, 'admin')
    r = c.get('/mi-cuenta/notificaciones')
    assert r.status_code == 200
    assert 'Sin configurar en el servidor' in r.get_data(as_text=True)


# ── Suscripción ─────────────────────────────────────────────────────────────

def test_clave_publica(app):
    c = _login(app, 'admin')
    r = c.get('/api/push/clave-publica')
    assert r.status_code == 200
    assert r.get_json() == {'ok': True, 'clave': 'BPUBLICA'}


def test_sin_claves_responde_503(app, monkeypatch):
    monkeypatch.delenv('VAPID_PUBLIC_KEY')
    c = _login(app, 'admin')
    assert c.get('/api/push/clave-publica').status_code == 503
    r = c.post('/api/push/suscribir', json={
        'endpoint': 'https://push.test/x', 'keys': {'p256dh': 'a', 'auth': 'b'}})
    assert r.status_code == 503
    assert r.get_json()['ok'] is False


def test_suscribir_guarda_actualiza_y_reasigna(app):
    from app import SuscripcionPush

    c = _login(app, 'vend_a')
    cuerpo = {'endpoint': 'https://push.test/nuevo', 'keys': {'p256dh': 'k1', 'auth': 'a1'}}
    r = c.post('/api/push/suscribir', json=cuerpo)
    assert r.status_code == 200
    assert r.get_json() == {'ok': True, 'dispositivos': 2}

    # Mismo endpoint otra vez (re-sincronización): no duplica, actualiza claves.
    cuerpo['keys']['auth'] = 'a2'
    r = c.post('/api/push/suscribir', json=cuerpo)
    assert r.get_json()['dispositivos'] == 2
    with app.app_context():
        fila = SuscripcionPush.query.filter_by(endpoint='https://push.test/nuevo').one()
        assert fila.auth == 'a2'
        assert fila.vendedor_id == IDS['vend_a']

    # Teléfono compartido: entra otro usuario y el aviso pasa a ser suyo.
    # En un app context NUEVO a propósito: Flask-Login cachea el usuario
    # cargado en `g`, y dentro del fixture las requests del test client
    # reutilizan el mismo context, así que un segundo cliente en el mismo
    # bloque seguiría viéndose como vend_a (en el servidor real cada request
    # trae su propio context y esto no pasa).
    with app.app_context():
        c2 = _login(app, 'bodega')
        r = c2.post('/api/push/suscribir', json=cuerpo)
        assert r.get_json()['dispositivos'] == 2
    with app.app_context():
        fila = SuscripcionPush.query.filter_by(endpoint='https://push.test/nuevo').one()
        assert fila.vendedor_id == IDS['bodega']
        assert SuscripcionPush.query.filter_by(vendedor_id=IDS['vend_a']).count() == 1


@pytest.mark.parametrize('cuerpo', [
    {},
    {'endpoint': 'http://inseguro.test/x', 'keys': {'p256dh': 'a', 'auth': 'b'}},
    {'endpoint': 'https://push.test/x', 'keys': {'p256dh': '', 'auth': 'b'}},
    {'endpoint': 'https://push.test/x'},
])
def test_suscribir_rechaza_cuerpos_invalidos(app, cuerpo):
    c = _login(app, 'admin')
    r = c.post('/api/push/suscribir', json=cuerpo)
    assert r.status_code == 400


def test_suscribir_exige_login(app):
    r = app.test_client().post('/api/push/suscribir', json={
        'endpoint': 'https://push.test/x', 'keys': {'p256dh': 'a', 'auth': 'b'}})
    assert r.status_code == 302


def test_desuscribir_solo_lo_propio(app):
    from app import SuscripcionPush

    c = _login(app, 'vend_a')
    # El endpoint de otro usuario no se toca aunque se mande.
    r = c.post('/api/push/desuscribir', json={'endpoint': 'https://push.test/admin'})
    assert r.get_json() == {'ok': True, 'dispositivos': 1}
    r = c.post('/api/push/desuscribir', json={'endpoint': 'https://push.test/vend_a'})
    assert r.get_json() == {'ok': True, 'dispositivos': 0}
    with app.app_context():
        assert SuscripcionPush.query.filter_by(endpoint='https://push.test/admin').count() == 1
        assert SuscripcionPush.query.filter_by(endpoint='https://push.test/vend_a').count() == 0


# ── El aviso al crear un pedido ─────────────────────────────────────────────

def test_pedido_nuevo_avisa_a_los_demas_no_al_autor_ni_a_inactivos(app):
    from app import Pedido, SuscripcionPush

    doble = _Doble()
    with patch.object(push, 'enviar', doble):
        c = _login(app, 'vend_a')
        r = _crear_pedido(c)
    assert r.status_code == 200

    assert doble.endpoints == ['https://push.test/admin', 'https://push.test/bodega']

    with app.app_context():
        pedido = Pedido.query.one()
        _, payload = doble.llamadas[0]
        assert payload['title'] == f'Nuevo pedido #{pedido.id}'
        assert 'Cliente A' in payload['body']
        assert '3 cajas' in payload['body']
        assert '39.00 XCG' in payload['body']
        assert 'Vend_A' in payload['body']
        assert payload['url'] == f'/pedidos/{pedido.id}/detalles'
        assert payload['tag'] == f'pedido-{pedido.id}'

        # Queda registrado que a esos dispositivos sí se les mandó algo.
        for nombre in ('admin', 'bodega'):
            fila = SuscripcionPush.query.filter_by(endpoint=f'https://push.test/{nombre}').one()
            assert fila.ultimo_envio_en is not None
        assert SuscripcionPush.query.filter_by(endpoint='https://push.test/vend_a').one().ultimo_envio_en is None


def test_suscripcion_dada_de_baja_se_borra(app):
    from app import SuscripcionPush

    doble = _Doble(respuestas={'https://push.test/bodega': ('baja', 'HTTP 410')})
    with patch.object(push, 'enviar', doble):
        c = _login(app, 'vend_a')
        _crear_pedido(c)

    with app.app_context():
        assert SuscripcionPush.query.filter_by(endpoint='https://push.test/bodega').count() == 0
        assert SuscripcionPush.query.filter_by(endpoint='https://push.test/admin').count() == 1


def test_un_error_de_envio_no_borra_ni_rompe(app):
    from app import Pedido, SuscripcionPush

    doble = _Doble(respuestas={'https://push.test/admin': ('error', 'HTTP 500')})
    with patch.object(push, 'enviar', doble):
        c = _login(app, 'vend_a')
        r = _crear_pedido(c)
    assert r.status_code == 200
    with app.app_context():
        assert Pedido.query.count() == 1
        assert SuscripcionPush.query.filter_by(endpoint='https://push.test/admin').count() == 1


def test_si_el_aviso_revienta_el_pedido_igual_se_crea(app):
    from app import Pedido

    def explota(*_args, **_kwargs):
        raise RuntimeError('sin red')

    with patch.object(push, 'enviar', explota):
        c = _login(app, 'vend_a')
        r = _crear_pedido(c)
    assert r.status_code == 200
    with app.app_context():
        assert Pedido.query.count() == 1


def test_sin_claves_no_se_intenta_nada(app, monkeypatch):
    from app import Pedido

    monkeypatch.delenv('VAPID_PRIVATE_KEY')
    doble = _Doble()
    with patch.object(push, 'enviar', doble):
        c = _login(app, 'vend_a')
        r = _crear_pedido(c)
    assert r.status_code == 200
    assert doble.llamadas == []
    with app.app_context():
        assert Pedido.query.count() == 1


def test_probar_manda_solo_a_los_dispositivos_propios(app):
    doble = _Doble()
    with patch.object(push, 'enviar', doble):
        c = _login(app, 'admin')
        r = c.post('/api/push/probar', json={})
    assert r.status_code == 200
    assert r.get_json() == {'ok': True, 'enviados': 1, 'bajas': 0, 'errores': 0}
    assert doble.endpoints == ['https://push.test/admin']
    assert doble.llamadas[0][1]['title'].startswith('PesosApp')


def test_probar_sin_dispositivos(app):
    from app import SuscripcionPush

    with app.app_context():
        SuscripcionPush.query.filter_by(vendedor_id=IDS['admin']).delete()
        _db.session.commit()
    c = _login(app, 'admin')
    r = c.post('/api/push/probar', json={})
    assert r.status_code == 404


# ── utils/push_notificaciones: lo puro ──────────────────────────────────────

def test_claves_vapid_normaliza_mailto(monkeypatch):
    for clave, valor in CLAVES.items():
        monkeypatch.setenv(clave, valor)
    assert push.claves_vapid() == ('BPUBLICA', 'PRIVADA', 'mailto:ops@jomar.test')
    monkeypatch.setenv('VAPID_CLAIMS_EMAIL', 'mailto:ya@jomar.test')
    assert push.claves_vapid()[2] == 'mailto:ya@jomar.test'
    monkeypatch.setenv('VAPID_PUBLIC_KEY', '')
    assert push.claves_vapid() is None
    assert push.push_configurado() is False


def test_armar_payload():
    from datetime import date

    p = push.armar_payload_nuevo_pedido(
        pedido_id=5890, cliente='Luna Park', cajas=Decimal('12.5'),
        total=Decimal('1234.5'), moneda='XCG', vendedor='Carlos',
        fecha_entrega=date(2026, 10, 15), url='/pedidos/5890/detalles')
    assert p['title'] == 'Nuevo pedido #5890'
    assert p['body'] == 'Luna Park · 12.5 cajas · 1,234.50 XCG · entrega 15/10\nTomado por Carlos'
    assert p['tag'] == 'pedido-5890'
    assert p['url'] == '/pedidos/5890/detalles'

    # Sin total ni cajas ni vendedor: solo el cliente, sin separadores sueltos.
    p = push.armar_payload_nuevo_pedido(pedido_id=1, cliente='X', cajas=0, total=0, moneda='USD')
    assert p['body'] == 'X'


def test_enviar_mapea_respuestas_de_pywebpush(monkeypatch):
    import pywebpush

    class _Resp:
        def __init__(self, status):
            self.status_code = status

    sus = {'endpoint': 'https://push.test/a', 'p256dh': 'k', 'auth': 'a'}
    claves = ('pub', 'priv', 'mailto:x@y.z')
    capturado = {}

    def falso_webpush(**kwargs):
        capturado.update(kwargs)
        if capturado.get('_falla'):
            raise pywebpush.WebPushException('fallo', response=_Resp(capturado['_falla']))
        return 'ok'

    monkeypatch.setattr(pywebpush, 'webpush', falso_webpush)
    assert push.enviar(sus, {'title': 'T'}, claves) == ('ok', None)
    assert capturado['subscription_info'] == {'endpoint': 'https://push.test/a',
                                              'keys': {'p256dh': 'k', 'auth': 'a'}}
    assert json.loads(capturado['data']) == {'title': 'T'}
    assert capturado['vapid_private_key'] == 'priv'
    assert capturado['vapid_claims'] == {'sub': 'mailto:x@y.z'}
    assert capturado['ttl'] == push.TTL_SEGUNDOS

    capturado['_falla'] = 410
    assert push.enviar(sus, {}, claves) == ('baja', 'HTTP 410')
    capturado['_falla'] = 404
    assert push.enviar(sus, {}, claves)[0] == 'baja'
    capturado['_falla'] = 500
    assert push.enviar(sus, {}, claves)[0] == 'error'


def test_enviar_sin_claves_es_error_y_no_llama_a_la_red(monkeypatch):
    import pywebpush

    def no_debe_llamarse(**_kwargs):
        raise AssertionError('no debía salir a la red')

    monkeypatch.setattr(pywebpush, 'webpush', no_debe_llamarse)
    for clave in CLAVES:
        monkeypatch.delenv(clave, raising=False)
    assert push.enviar({'endpoint': 'https://x', 'p256dh': 'k', 'auth': 'a'}, {}) == \
        ('error', 'VAPID sin configurar')


def test_enviar_real_cifra_y_firma_con_claves_generadas(monkeypatch):
    """Sin dobles de pywebpush: las claves que salen de `generar_claves` tienen
    que servirle tal cual (cifrado aes128gcm + cabecera VAPID). Solo se
    captura el POST final para no salir a la red."""
    import requests
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import ec

    publica, privada = push.generar_claves()
    monkeypatch.setenv('VAPID_PUBLIC_KEY', publica)
    monkeypatch.setenv('VAPID_PRIVATE_KEY', privada)
    monkeypatch.setenv('VAPID_CLAIMS_EMAIL', 'ops@jomar.test')

    # Claves del "navegador", como las genera PushManager.subscribe().
    navegador = ec.generate_private_key(ec.SECP256R1())
    p256dh = base64.urlsafe_b64encode(navegador.public_key().public_bytes(
        serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)).decode().rstrip('=')
    auth = base64.urlsafe_b64encode(os.urandom(16)).decode().rstrip('=')

    capturado = {}

    class _Resp:
        status_code = 201
        text = 'Created'
        headers = {}

    def falso_post(url, data=None, headers=None, timeout=None, **_kw):
        capturado.update(url=url, data=data, headers=headers, timeout=timeout)
        return _Resp()

    monkeypatch.setattr(requests, 'post', falso_post)
    sus = {'endpoint': 'https://web.push.apple.com/QAbc', 'p256dh': p256dh, 'auth': auth}
    assert push.enviar(sus, {'title': 'Nuevo pedido #1', 'body': 'x'}) == ('ok', None)

    assert capturado['url'] == sus['endpoint']
    assert capturado['timeout'] == push.TIMEOUT_ENVIO
    cab = capturado['headers']
    assert cab['Authorization'].startswith('vapid t=')
    assert ('k=' + publica) in cab['Authorization']
    assert cab['Content-Encoding'] == 'aes128gcm'
    assert str(cab['TTL']) == str(push.TTL_SEGUNDOS)
    assert isinstance(capturado['data'], (bytes, bytearray)) and len(capturado['data']) > 0


def test_generar_claves_en_base64url():
    publica, privada = push.generar_claves()

    def decodificar(texto):
        return base64.urlsafe_b64decode(texto + '=' * (-len(texto) % 4))

    # Punto EC sin comprimir (0x04 + 32 + 32) y escalar privado de 32 bytes:
    # exactamente lo que esperan `applicationServerKey` y pywebpush.
    assert len(decodificar(publica)) == 65 and decodificar(publica)[0] == 4
    assert len(decodificar(privada)) == 32
    assert '=' not in publica + privada and '+' not in publica + privada


def test_comando_generar_claves(app):
    r = app.test_cli_runner().invoke(args=['push-generar-claves'])
    assert r.exit_code == 0, r.output
    assert 'VAPID_PUBLIC_KEY=' in r.output
    assert 'VAPID_PRIVATE_KEY=' in r.output
