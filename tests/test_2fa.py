# tests/test_2fa.py
"""Segundo factor (TOTP): activación, login en dos pasos, códigos de
respaldo, obligación por rol, desactivación, reset por admin y por CLI."""
import re
import json
from unittest.mock import patch

import pyotp
import pytest
from cryptography.fernet import Fernet

import app as app_module
from app import app as flask_app, db as _db, Vendedor


@pytest.fixture
def app(monkeypatch):
    monkeypatch.delenv('TOTP_OBLIGATORIO_ROLES', raising=False)
    monkeypatch.delenv('QBO_TOKEN_KEY', raising=False)
    flask_app.config.update(TESTING=True, WTF_CSRF_ENABLED=False,
                            SQLALCHEMY_DATABASE_URI='sqlite:///:memory:')
    with flask_app.app_context():
        _db.create_all()
        from app import Rol, Territorio
        admin = Rol(nombre='super_admin', descripcion='Admin')
        ventas = Rol(nombre='vendedor', descripcion='Ventas')
        t = Territorio(nombre='t', descripcion='T')
        _db.session.add_all([admin, ventas, t])
        _db.session.flush()
        for username, rol in (('admin', admin), ('ventas', ventas)):
            v = Vendedor(username=username, email=f'{username}@t.com', nombre_completo=username.title(),
                         rol_id=rol.id, territorio_id=t.id, activo=True)
            v.set_password('testpass')
            _db.session.add(v)
        _db.session.commit()
        yield flask_app
        _db.session.remove()
        _db.drop_all()


def _login(client, username='admin', password='testpass', **extra):
    return client.post('/login', data={'username': username, 'password': password, **extra})


def _secreto_pendiente(client):
    with client.session_transaction() as sess:
        return sess.get('2fa_setup_secret')


def _codigo(secreto):
    return pyotp.TOTP(secreto).now()


def _codigos_en(html):
    """Los códigos de respaldo del bloque donde se muestran (y solo de ahí:
    la página tiene clases CSS con el mismo aspecto `xxxx-xxxx`)."""
    m = re.search(r'<pre class="qbo-codigos-respaldo"[^>]*>(.*?)</pre>', html, re.S)
    return re.findall(r'\b[a-z0-9]{4}-[a-z0-9]{4}\b', m.group(1)) if m else []


def _activar(client):
    """Activa el 2FA del usuario logueado y devuelve (secreto, códigos de respaldo)."""
    client.get('/mi-cuenta/2fa')
    secreto = _secreto_pendiente(client)
    resp = client.post('/mi-cuenta/2fa/activar', data={'codigo': _codigo(secreto)}, follow_redirects=True)
    return secreto, _codigos_en(resp.data.decode())


# ── activación ────────────────────────────────────────────────────────────

def test_pantalla_de_activacion_muestra_qr_y_clave_manual(app):
    c = app.test_client()
    _login(c)
    resp = c.get('/mi-cuenta/2fa')
    assert resp.status_code == 200
    html = resp.data.decode()
    assert '<svg' in html and 'Clave manual' in html
    secreto = _secreto_pendiente(c)
    assert secreto and ' '.join(secreto[i:i + 4] for i in range(0, len(secreto), 4)) in html


def test_codigo_incorrecto_no_activa(app):
    c = app.test_client()
    _login(c)
    c.get('/mi-cuenta/2fa')
    resp = c.post('/mi-cuenta/2fa/activar', data={'codigo': '000000'}, follow_redirects=True)
    assert 'no coincide'.encode() in resp.data
    assert not Vendedor.query.filter_by(username='admin').one().totp_activo


def test_activacion_guarda_secreto_y_muestra_ocho_codigos_una_sola_vez(app):
    c = app.test_client()
    _login(c)
    secreto, codigos = _activar(c)
    v = Vendedor.query.filter_by(username='admin').one()
    assert v.totp_activo and v.totp_secret == secreto        # sin clave: texto plano
    assert len(codigos) == 8 and len(set(codigos)) == 8
    assert len(json.loads(v.codigos_respaldo)) == 8
    assert _secreto_pendiente(c) is None
    # Segunda visita: los códigos ya no se muestran.
    html = c.get('/mi-cuenta/2fa').data.decode()
    assert 'Segundo factor activo' in html
    assert not _codigos_en(html)


def test_con_clave_el_secreto_se_guarda_cifrado(app, monkeypatch):
    monkeypatch.setenv('QBO_TOKEN_KEY', Fernet.generate_key().decode())
    c = app.test_client()
    _login(c)
    secreto, _ = _activar(c)
    v = Vendedor.query.filter_by(username='admin').one()
    assert v.totp_secret.startswith('enc:') and secreto not in v.totp_secret
    assert app_module._secreto_totp(v) == secreto


# ── login en dos pasos ────────────────────────────────────────────────────

def test_login_con_2fa_pide_el_codigo_y_no_inicia_sesion_todavia(app):
    c = app.test_client()
    _login(c)
    secreto, _ = _activar(c)
    c.post('/logout')

    resp = _login(c, next='/productos')
    assert resp.status_code == 302 and resp.headers['Location'].endswith('/login/2fa')
    assert c.get('/pedidos').status_code == 302          # sigue sin sesión
    assert b'Verificaci' in c.get('/login/2fa').data

    resp = c.post('/login/2fa', data={'codigo': '000000'})
    assert resp.status_code == 200 and b'incorrecto' in resp.data
    assert c.get('/pedidos').status_code == 302

    resp = c.post('/login/2fa', data={'codigo': _codigo(secreto)})
    assert resp.status_code == 302 and resp.headers['Location'].endswith('/productos')
    assert c.get('/pedidos').status_code == 200


def test_sin_2fa_el_login_sigue_siendo_de_un_paso(app):
    c = app.test_client()
    resp = _login(c)
    assert resp.status_code == 302 and '/login/2fa' not in resp.headers['Location']
    assert c.get('/pedidos').status_code == 200


def test_codigo_de_respaldo_entra_una_sola_vez(app):
    c = app.test_client()
    _login(c)
    _, codigos = _activar(c)
    c.post('/logout')

    _login(c)
    resp = c.post('/login/2fa', data={'codigo': codigos[0].upper()})
    assert resp.status_code == 302
    assert len(json.loads(Vendedor.query.filter_by(username='admin').one().codigos_respaldo)) == 7
    c.post('/logout')

    _login(c)
    resp = c.post('/login/2fa', data={'codigo': codigos[0]})
    assert resp.status_code == 200 and b'incorrecto' in resp.data


def test_la_verificacion_pendiente_caduca(app):
    c = app.test_client()
    _login(c)
    secreto, _ = _activar(c)
    c.post('/logout')
    _login(c)
    with patch.object(app_module.time, 'time', return_value=app_module.time.time() + 600):
        resp = c.post('/login/2fa', data={'codigo': _codigo(secreto)})
    assert resp.status_code == 302 and resp.headers['Location'].endswith('/login')
    assert c.get('/pedidos').status_code == 302


def test_login_2fa_sin_pendiente_vuelve_al_login(app):
    c = app.test_client()
    resp = c.get('/login/2fa')
    assert resp.status_code == 302 and resp.headers['Location'].endswith('/login')


# ── obligación por rol ────────────────────────────────────────────────────

def test_rol_obligado_sin_2fa_solo_puede_activarlo(app, monkeypatch):
    monkeypatch.setenv('TOTP_OBLIGATORIO_ROLES', 'super_admin')
    c = app.test_client()
    _login(c)
    resp = c.get('/pedidos')
    assert resp.status_code == 302 and resp.headers['Location'].endswith('/mi-cuenta/2fa')
    assert c.get('/mi-cuenta/2fa').status_code == 200
    _activar(c)
    assert c.get('/pedidos').status_code == 200


def test_rol_no_obligado_no_se_bloquea(app, monkeypatch):
    monkeypatch.setenv('TOTP_OBLIGATORIO_ROLES', 'super_admin')
    c = app.test_client()
    _login(c, 'ventas')
    resp = c.get('/mi-cuenta/cambiar-contrasena')
    assert resp.status_code == 200


def test_por_defecto_nadie_esta_obligado(app):
    c = app.test_client()
    _login(c)
    assert c.get('/pedidos').status_code == 200


# ── desactivar y regenerar ────────────────────────────────────────────────

def test_rol_obligado_no_puede_desactivar(app, monkeypatch):
    monkeypatch.setenv('TOTP_OBLIGATORIO_ROLES', 'super_admin')
    c = app.test_client()
    _login(c)
    secreto, _ = _activar(c)
    resp = c.post('/mi-cuenta/2fa/desactivar', data={'codigo': _codigo(secreto)}, follow_redirects=True)
    assert 'no se puede desactivar'.encode() in resp.data
    assert Vendedor.query.filter_by(username='admin').one().totp_activo


def test_rol_libre_desactiva_con_codigo(app):
    c = app.test_client()
    _login(c, 'ventas')
    secreto, _ = _activar(c)
    resp = c.post('/mi-cuenta/2fa/desactivar', data={'codigo': '000000'}, follow_redirects=True)
    assert Vendedor.query.filter_by(username='ventas').one().totp_activo
    resp = c.post('/mi-cuenta/2fa/desactivar', data={'codigo': _codigo(secreto)}, follow_redirects=True)
    assert b'desactivado' in resp.data
    v = Vendedor.query.filter_by(username='ventas').one()
    assert not v.totp_activo and v.totp_secret is None and v.codigos_respaldo is None


def test_regenerar_codigos_exige_codigo_y_los_reemplaza(app):
    c = app.test_client()
    _login(c)
    secreto, viejos = _activar(c)
    c.post('/mi-cuenta/2fa/codigos', data={'codigo': '000000'})
    assert len(json.loads(Vendedor.query.filter_by(username='admin').one().codigos_respaldo)) == 8
    resp = c.post('/mi-cuenta/2fa/codigos', data={'codigo': _codigo(secreto)}, follow_redirects=True)
    nuevos = _codigos_en(resp.data.decode())
    assert len(nuevos) == 8 and not set(nuevos) & set(viejos)


# ── reset por admin y por CLI ─────────────────────────────────────────────

def test_admin_restablece_el_2fa_de_otro_usuario(app):
    from utils.totp import nuevo_secreto
    v = Vendedor.query.filter_by(username='ventas').one()
    v.totp_secret = nuevo_secreto()
    v.totp_confirmado_en = app_module._utcnow_naive()
    _db.session.commit()
    c = app.test_client()
    _login(c)
    resp = c.post(f'/admin/vendedores/{v.id}/2fa/reset', follow_redirects=True)
    assert b'restablecido' in resp.data
    assert not Vendedor.query.filter_by(username='ventas').one().totp_activo
    assert b'Restablecer segundo factor' in c.get('/admin/vendedores').data


def test_un_vendedor_no_puede_restablecer_2fa_ajeno(app):
    admin = Vendedor.query.filter_by(username='admin').one()
    c = app.test_client()
    _login(c, 'ventas')
    resp = c.post(f'/admin/vendedores/{admin.id}/2fa/reset')
    assert resp.status_code == 302 and '/admin/vendedores' not in resp.headers['Location']


def test_cli_2fa_reset(app):
    from utils.totp import nuevo_secreto
    v = Vendedor.query.filter_by(username='admin').one()
    v.totp_secret = nuevo_secreto()
    v.totp_confirmado_en = app_module._utcnow_naive()
    _db.session.commit()
    res = app.test_cli_runner().invoke(args=['2fa-reset', 'admin'])
    assert res.exit_code == 0, res.output
    assert not Vendedor.query.filter_by(username='admin').one().totp_activo
    res = app.test_cli_runner().invoke(args=['2fa-reset', 'nadie'])
    assert res.exit_code != 0 and 'No existe' in res.output


def test_menu_tiene_el_enlace(app):
    c = app.test_client()
    _login(c)
    assert b'/mi-cuenta/2fa' in c.get('/pedidos').data


def test_clave_del_limite_2fa_usa_el_usuario_pendiente(app):
    with app.test_request_context():
        from flask import session
        session['2fa'] = {'id': 7}
        assert app_module._login_2fa_key() == '2fa:7'


def test_el_qr_tiene_fondo_blanco_trazado_negro_y_tamano_legible():
    """Sobre el tema oscuro el QR salía negro sobre negro y de 2,5 cm."""
    from utils.totp import qr_svg, nuevo_secreto, uri_provision, TAMANO_QR_PX
    svg = qr_svg(uri_provision(nuevo_secreto(), 'admin'))
    assert f'width="{TAMANO_QR_PX}" height="{TAMANO_QR_PX}"' in svg
    assert '<rect width="100%" height="100%" fill="#fff"/>' in svg
    assert '<path fill="#000"' in svg
    assert 'mm' not in svg.split('viewBox')[0]
