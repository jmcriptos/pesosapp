# tests/test_sesion_persistente.py
"""La sesión tiene que sobrevivir a que iOS descarte el WebView de la PWA.

Reportado desde un iPhone: "la sesión se cierra cada vez que voy a otra app".

Causa: `PERMANENT_SESSION_LIFETIME` estaba configurado en 8 h, pero Flask solo
lo aplica cuando la sesión es `permanent`. Como nunca se marcaba, la cookie
salía SIN `Expires` ni `Max-Age`, es decir, una cookie de sesión de navegador.
La app se usa como PWA standalone en iPhone, y cuando iOS descarta el WebView
—lo que pasa de rutina al cambiar de app— esas cookies se pierden.

Verificado contra producción antes del arreglo:
    set-cookie: session=...; Secure; HttpOnly; Path=/; SameSite=Lax
sin Expires ni Max-Age.
"""
import os
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
        from app import Rol, Territorio, Vendedor

        rol = Rol(nombre='super_admin', descripcion='Admin')
        _db.session.add(rol)
        territorio = Territorio(nombre='test', descripcion='Test')
        _db.session.add(territorio)
        _db.session.flush()
        v = Vendedor(username='admin', email='a@t.com', nombre_completo='Admin',
                     rol_id=rol.id, territorio_id=territorio.id, activo=True)
        v.set_password('testpass')
        _db.session.add(v)
        _db.session.commit()
        yield flask_app
        _db.drop_all()


def _cookies_de_login(app, remember=False):
    """Devuelve las cabeceras Set-Cookie del login."""
    client = app.test_client()
    data = {'username': 'admin', 'password': 'testpass'}
    if remember:
        data['remember_me'] = 'on'
    resp = client.post('/login', data=data)
    return resp.headers.getlist('Set-Cookie')


def test_la_cookie_de_sesion_persiste_al_cerrar_el_webview(app):
    """Sin Expires/Max-Age, iOS tira la cookie al descartar la PWA.

    Este es el test que fallaba: la cookie salía sin vencimiento, así que
    cambiar de app deslogueaba al vendedor.
    """
    cookies = _cookies_de_login(app)
    sesion = next((c for c in cookies if c.startswith('session=')), None)

    assert sesion is not None, 'el login debe emitir la cookie de sesión'
    tiene_vencimiento = 'Expires=' in sesion or 'Max-Age=' in sesion
    assert tiene_vencimiento, (
        'La cookie de sesión no lleva vencimiento, así que es de sesión de '
        f'navegador y iOS la descarta al cerrar el WebView: {sesion}'
    )


def test_la_sesion_queda_marcada_como_permanente(app):
    """Es lo que hace que PERMANENT_SESSION_LIFETIME (8 h) se aplique."""
    from flask import session

    client = app.test_client()
    client.post('/login', data={'username': 'admin', 'password': 'testpass'})
    with client.session_transaction() as s:
        assert s.permanent is True


def test_el_vencimiento_respeta_las_8_horas_configuradas(app):
    """No inventar un plazo nuevo: el que ya declaraba la config."""
    from datetime import timedelta
    assert flask_app.config['PERMANENT_SESSION_LIFETIME'] == timedelta(hours=8)


def test_la_cookie_sigue_siendo_segura(app):
    """Persistir no puede costar los atributos de seguridad."""
    sesion = next(c for c in _cookies_de_login(app) if c.startswith('session='))
    assert 'HttpOnly' in sesion
    assert 'SameSite=Lax' in sesion
