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


def test_toggle_no_admin_bloqueado(app):
    from app import Vendedor
    c = _login(app, 'vend')
    resp = c.post(f'/admin/vendedores/{IDS["admin"]}/toggle', follow_redirects=False)
    assert resp.status_code in (302, 403)
    with app.app_context():
        assert _db.session.get(Vendedor, IDS['admin']).activo is True


def test_toggle_activa_desactiva(app):
    from app import Vendedor
    c = _login(app, 'admin')
    c.post(f'/admin/vendedores/{IDS["vend"]}/toggle', follow_redirects=True)
    with app.app_context():
        assert _db.session.get(Vendedor, IDS['vend']).activo is False
    c.post(f'/admin/vendedores/{IDS["vend"]}/toggle', follow_redirects=True)
    with app.app_context():
        assert _db.session.get(Vendedor, IDS['vend']).activo is True


def test_toggle_no_auto_desactivar(app):
    from app import Vendedor
    c = _login(app, 'admin')
    c.post(f'/admin/vendedores/{IDS["admin"]}/toggle', follow_redirects=True)
    with app.app_context():
        assert _db.session.get(Vendedor, IDS['admin']).activo is True


def test_toggle_no_desactivar_ultimo_superadmin(app):
    from app import Vendedor
    with app.app_context():
        a2 = Vendedor(username='admin2', email='a2@t.com', nombre_completo='Admin2',
                      rol_id=IDS['rol_admin'], territorio_id=IDS['terr'], activo=True)
        a2.set_password('pw'); _db.session.add(a2); _db.session.commit()
        IDS['admin2'] = a2.id
    c = _login(app, 'admin')
    c.post(f'/admin/vendedores/{IDS["admin2"]}/toggle', follow_redirects=True)
    with app.app_context():
        assert _db.session.get(Vendedor, IDS['admin2']).activo is False


def test_editar_no_admin_bloqueado(app):
    from app import Vendedor
    c = _login(app, 'vend')
    resp = c.post(f'/admin/vendedores/{IDS["vend"]}/editar',
                  data={'nombre_completo': 'X', 'email': 'x@t.com', 'rol_id': IDS['rol_vend']},
                  follow_redirects=False)
    assert resp.status_code in (302, 403)
    with app.app_context():
        assert _db.session.get(Vendedor, IDS['vend']).nombre_completo == 'Vend'


def test_editar_cambia_rol_y_email(app):
    from app import Vendedor
    c = _login(app, 'admin')
    c.post(f'/admin/vendedores/{IDS["vend"]}/editar', data={
        'nombre_completo': 'Vend Editado', 'email': 'nuevo_vend@t.com',
        'telefono': '123', 'rol_id': IDS['rol_super'], 'territorio_id': IDS['terr'],
    }, follow_redirects=True)
    with app.app_context():
        v = _db.session.get(Vendedor, IDS['vend'])
        assert v.nombre_completo == 'Vend Editado'
        assert v.email == 'nuevo_vend@t.com'
        assert v.rol.nombre == 'supervisor'


def test_editar_email_duplicado_rechazado(app):
    from app import Vendedor
    c = _login(app, 'admin')
    c.post(f'/admin/vendedores/{IDS["vend"]}/editar', data={
        'nombre_completo': 'Vend', 'email': 'admin@t.com', 'rol_id': IDS['rol_vend'],
    }, follow_redirects=True)
    with app.app_context():
        assert _db.session.get(Vendedor, IDS['vend']).email == 'vend@t.com'


def test_editar_ultimo_superadmin_no_pierde_rol(app):
    from app import Vendedor
    c = _login(app, 'admin')
    c.post(f'/admin/vendedores/{IDS["admin"]}/editar', data={
        'nombre_completo': 'Admin', 'email': 'admin@t.com', 'rol_id': IDS['rol_vend'],
    }, follow_redirects=True)
    with app.app_context():
        assert _db.session.get(Vendedor, IDS['admin']).rol.nombre == 'super_admin'


def test_reset_no_admin_bloqueado(app):
    c = _login(app, 'vend')
    resp = c.post(f'/admin/vendedores/{IDS["vend"]}/reset-password',
                  data={'password_temporal': 'Temporal9'}, follow_redirects=False)
    assert resp.status_code in (302, 403)


def test_reset_con_temporal(app):
    from app import Vendedor
    c = _login(app, 'admin')
    c.post(f'/admin/vendedores/{IDS["vend"]}/reset-password',
           data={'password_temporal': 'Temporal9'}, follow_redirects=True)
    with app.app_context():
        v = _db.session.get(Vendedor, IDS['vend'])
        assert v.debe_cambiar_password is True
        assert v.check_password('Temporal9') is True


def test_reset_genera_si_blanco(app):
    from app import Vendedor
    c = _login(app, 'admin')
    c.post(f'/admin/vendedores/{IDS["vend"]}/reset-password',
           data={'password_temporal': ''}, follow_redirects=True)
    with app.app_context():
        v = _db.session.get(Vendedor, IDS['vend'])
        assert v.debe_cambiar_password is True
        assert v.check_password('pw') is False  # la contraseña vieja ya no sirve
