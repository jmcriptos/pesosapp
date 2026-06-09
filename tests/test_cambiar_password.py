"""Tests para autoservicio de cambio de contraseña."""
import os
import pytest

os.environ.setdefault('SECRET_KEY', 'test-secret')
os.environ.setdefault('FLASK_ENV', 'testing')
os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')

from app import app as flask_app, db as _db

OLD = 'OldPass123'
IDS = {}


@pytest.fixture
def app():
    flask_app.config.update(
        TESTING=True,
        WTF_CSRF_ENABLED=False,
        SQLALCHEMY_DATABASE_URI='sqlite:///:memory:',
    )
    with flask_app.app_context():
        _db.create_all()
        from app import Rol, Territorio, Vendedor
        rol = Rol(nombre='vendedor', descripcion='Vendedor')
        terr = Territorio(nombre='t1', descripcion='T1')
        _db.session.add_all([rol, terr])
        _db.session.flush()
        v = Vendedor(username='user1', email='u1@t.com', nombre_completo='User Uno',
                     rol_id=rol.id, territorio_id=terr.id, activo=True)
        v.set_password(OLD)
        _db.session.add(v)
        _db.session.commit()
        IDS['user'] = v.id
        yield flask_app
        _db.drop_all()


def _login(app):
    c = app.test_client()
    c.post('/login', data={'username': 'user1', 'password': OLD},
           follow_redirects=True)
    return c


URL = '/mi-cuenta/cambiar-contrasena'


def _sigue_con_old(app):
    from app import Vendedor
    with app.app_context():
        v = _db.session.get(Vendedor, IDS['user'])
        assert v.check_password(OLD), "La contraseña NO debió cambiar"


def test_no_autenticado_redirige(app):
    c = app.test_client()
    resp = c.post(URL, data={'actual': OLD, 'nueva': 'NuevaPass1', 'confirmar': 'NuevaPass1'},
                  follow_redirects=False)
    assert resp.status_code == 302
    assert '/login' in resp.headers.get('Location', '')
    _sigue_con_old(app)


def test_actual_incorrecta(app):
    c = _login(app)
    resp = c.post(URL, data={'actual': 'malaclave', 'nueva': 'NuevaPass1', 'confirmar': 'NuevaPass1'})
    assert resp.status_code == 200
    _sigue_con_old(app)


def test_confirmacion_no_coincide(app):
    c = _login(app)
    resp = c.post(URL, data={'actual': OLD, 'nueva': 'NuevaPass1', 'confirmar': 'OtraCosa1'})
    assert resp.status_code == 200
    _sigue_con_old(app)


def test_nueva_muy_corta(app):
    c = _login(app)
    resp = c.post(URL, data={'actual': OLD, 'nueva': 'corta', 'confirmar': 'corta'})
    assert resp.status_code == 200
    _sigue_con_old(app)


def test_nueva_igual_a_actual(app):
    c = _login(app)
    resp = c.post(URL, data={'actual': OLD, 'nueva': OLD, 'confirmar': OLD})
    assert resp.status_code == 200
    _sigue_con_old(app)


# Nota: el usuario legacy (DefaultUser) fue eliminado por seguridad; ya no existe
# un fallback de credenciales por variables de entorno. El test correspondiente
# se retiró junto con esa funcionalidad.


def test_exito_cambia_y_desloguea(app):
    from app import Vendedor
    c = _login(app)
    nueva = 'NuevaPass1'
    resp = c.post(URL, data={'actual': OLD, 'nueva': nueva, 'confirmar': nueva},
                  follow_redirects=False)
    assert resp.status_code == 302
    assert '/login' in resp.headers.get('Location', '')
    with app.app_context():
        v = _db.session.get(Vendedor, IDS['user'])
        assert v.check_password(nueva)
        assert not v.check_password(OLD)
    r2 = c.get('/dashboard', follow_redirects=False)
    assert r2.status_code == 302
    assert '/login' in r2.headers.get('Location', '')
