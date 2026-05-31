"""Tests de administración de usuarios (#1)."""
import os

import pytest

os.environ.setdefault('SECRET_KEY', 'test-secret')
os.environ.setdefault('FLASK_ENV', 'testing')
os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')

from app import app as flask_app, db as _db

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
        rol_admin = Rol(nombre='super_admin', descripcion='Admin')
        rol_super = Rol(nombre='supervisor', descripcion='Supervisor')
        rol_vend = Rol(nombre='vendedor', descripcion='Vendedor')
        terr = Territorio(nombre='t1', descripcion='T1')
        _db.session.add_all([rol_admin, rol_super, rol_vend, terr])
        _db.session.flush()
        admin = Vendedor(username='admin', email='admin@t.com', nombre_completo='Admin',
                         rol_id=rol_admin.id, territorio_id=terr.id, activo=True)
        admin.set_password('pw')
        vend = Vendedor(username='vend', email='vend@t.com', nombre_completo='Vend',
                        rol_id=rol_vend.id, territorio_id=terr.id, activo=True)
        vend.set_password('pw')
        _db.session.add_all([admin, vend])
        _db.session.commit()
        IDS['rol_admin'] = rol_admin.id
        IDS['rol_super'] = rol_super.id
        IDS['rol_vend'] = rol_vend.id
        IDS['terr'] = terr.id
        IDS['admin'] = admin.id
        IDS['vend'] = vend.id
        yield flask_app
        _db.drop_all()


def _login(app, username):
    c = app.test_client()
    c.post('/login', data={'username': username, 'password': 'pw'}, follow_redirects=True)
    return c


def test_columna_debe_cambiar_password(app):
    from app import Vendedor
    with app.app_context():
        v = _db.session.get(Vendedor, IDS['vend'])
        assert v.debe_cambiar_password is False


def test_nuevo_usuario_nace_con_flag(app):
    from app import Vendedor
    c = _login(app, 'admin')
    c.post('/admin/vendedores/nuevo', data={
        'username': 'nuevo', 'email': 'nuevo@t.com', 'nombre_completo': 'Nuevo',
        'password': 'inicial9', 'rol_id': IDS['rol_vend'],
    }, follow_redirects=True)
    with app.app_context():
        v = Vendedor.query.filter_by(username='nuevo').first()
        assert v is not None
        assert v.debe_cambiar_password is True


def test_flag_fuerza_cambio(app):
    from app import Vendedor
    with app.app_context():
        v = _db.session.get(Vendedor, IDS['vend'])
        v.debe_cambiar_password = True
        _db.session.commit()
    c = _login(app, 'vend')
    resp = c.get('/registros', follow_redirects=False)
    assert resp.status_code == 302
    assert 'cambiar-contrasena' in resp.headers.get('Location', '')


def test_cambiar_password_limpia_flag(app):
    from app import Vendedor
    with app.app_context():
        v = _db.session.get(Vendedor, IDS['vend'])
        v.debe_cambiar_password = True
        _db.session.commit()
    c = _login(app, 'vend')
    c.post('/mi-cuenta/cambiar-contrasena',
           data={'actual': 'pw', 'nueva': 'NuevaClave9', 'confirmar': 'NuevaClave9'},
           follow_redirects=True)
    with app.app_context():
        v = _db.session.get(Vendedor, IDS['vend'])
        assert v.debe_cambiar_password is False
        assert v.check_password('NuevaClave9') is True
