"""Tests de permisos configurables (#2)."""
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
        ra = Rol(nombre='super_admin', descripcion='Admin')
        rs = Rol(nombre='supervisor', descripcion='Supervisor')
        rv = Rol(nombre='vendedor', descripcion='Vendedor')
        terr = Territorio(nombre='t1', descripcion='T1')
        _db.session.add_all([ra, rs, rv, terr])
        _db.session.flush()
        admin = Vendedor(username='admin', email='admin@t.com', nombre_completo='Admin',
                         rol_id=ra.id, territorio_id=terr.id, activo=True)
        admin.set_password('pw')
        vend = Vendedor(username='vend', email='vend@t.com', nombre_completo='Vend',
                        rol_id=rv.id, territorio_id=terr.id, activo=True)
        vend.set_password('pw')
        _db.session.add_all([admin, vend])
        _db.session.commit()
        IDS['ra'] = ra.id; IDS['rs'] = rs.id; IDS['rv'] = rv.id
        IDS['admin'] = admin.id; IDS['vend'] = vend.id
        yield flask_app
        _db.drop_all()


def _login(app, username):
    c = app.test_client()
    c.post('/login', data={'username': username, 'password': 'pw'}, follow_redirects=True)
    return c


def test_super_admin_siempre_true(app):
    from app import Vendedor
    with app.app_context():
        a = _db.session.get(Vendedor, IDS['admin'])
        assert a.tiene_permiso('pedidos', 'eliminar') is True
        assert a.tiene_permiso('registros', 'editar') is True


def test_fallback_sin_filas(app):
    from app import Vendedor
    with app.app_context():
        v = _db.session.get(Vendedor, IDS['vend'])
        assert v.tiene_permiso('pedidos', 'editar') is True
        assert v.tiene_permiso('pedidos', 'eliminar') is False
        assert v.tiene_permiso('registros', 'crear') is True
        assert v.tiene_permiso('registros', 'editar') is False


def test_lee_de_rolpermiso(app):
    from app import Vendedor, Permiso, RolPermiso
    with app.app_context():
        p = Permiso(nombre='pedidos', recurso='pedidos', categoria='recurso')
        _db.session.add(p); _db.session.flush()
        rp = RolPermiso(rol_id=IDS['rv'], permiso_id=p.id,
                        puede_leer=True, puede_crear=False, puede_editar=False, puede_eliminar=False)
        _db.session.add(rp); _db.session.commit()
        v = _db.session.get(Vendedor, IDS['vend'])
        assert v.tiene_permiso('pedidos', 'leer') is True
        assert v.tiene_permiso('pedidos', 'crear') is False


def test_sembrar_crea_filas_y_es_idempotente(app):
    from app import Vendedor, Permiso, RolPermiso, _sembrar_permisos
    with app.app_context():
        _sembrar_permisos()
        assert Permiso.query.filter_by(recurso='registros').first() is not None
        assert Permiso.query.count() == 5
        v = _db.session.get(Vendedor, IDS['vend'])
        assert v.tiene_permiso('registros', 'crear') is True
        assert v.tiene_permiso('registros', 'editar') is False
        n_rp = RolPermiso.query.count()
        _sembrar_permisos()
        assert RolPermiso.query.count() == n_rp


def _set_rolpermiso(rec, leer=False, crear=False, editar=False, eliminar=False, rol_id=None):
    from app import Permiso, RolPermiso
    rol_id = rol_id or IDS['rv']
    p = Permiso.query.filter_by(recurso=rec).first()
    if p is None:
        p = Permiso(nombre=rec, recurso=rec, categoria='recurso'); _db.session.add(p); _db.session.flush()
    rp = RolPermiso.query.filter_by(rol_id=rol_id, permiso_id=p.id).first()
    if rp is None:
        rp = RolPermiso(rol_id=rol_id, permiso_id=p.id); _db.session.add(rp)
    rp.puede_leer, rp.puede_crear, rp.puede_editar, rp.puede_eliminar = leer, crear, editar, eliminar
    _db.session.commit()


def test_temp_registrar_sin_crear_bloqueado(app):
    with app.app_context():
        _set_rolpermiso('registros', leer=True, crear=False, editar=False)
    c = _login(app, 'vend')
    resp = c.get('/registros/temperaturas', follow_redirects=False)
    assert resp.status_code == 302


def test_temp_config_requiere_editar(app):
    with app.app_context():
        _set_rolpermiso('registros', leer=True, crear=True, editar=False)
    c = _login(app, 'vend')
    resp = c.get('/registros/temperaturas/camaras', follow_redirects=False)
    assert resp.status_code == 302
