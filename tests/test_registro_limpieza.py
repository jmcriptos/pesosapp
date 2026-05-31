"""Tests del registro de limpieza (HACCP)."""
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
        from app import Rol, Territorio, Vendedor, ProductoLimpieza, AreaLimpieza
        rol_admin = Rol(nombre='super_admin', descripcion='Admin')
        rol_vend = Rol(nombre='vendedor', descripcion='Vendedor')
        terr = Territorio(nombre='t1', descripcion='T1')
        _db.session.add_all([rol_admin, rol_vend, terr])
        _db.session.flush()
        admin = Vendedor(username='admin', email='a@t.com', nombre_completo='Admin',
                         rol_id=rol_admin.id, territorio_id=terr.id, activo=True)
        admin.set_password('pw')
        vend = Vendedor(username='vend', email='v@t.com', nombre_completo='Vend',
                        rol_id=rol_vend.id, territorio_id=terr.id, activo=True)
        vend.set_password('pw')
        _db.session.add_all([admin, vend])
        prod = ProductoLimpieza(nombre='Sanitizante clorado', dilucion='10 ml / 1 L', activo=True)
        _db.session.add(prod)
        _db.session.flush()
        area = AreaLimpieza(nombre='Sierra de cortar', tipo='equipo',
                            producto_id=prod.id, frecuencia_texto='Diaria', activa=True)
        _db.session.add(area)
        _db.session.commit()
        IDS['producto'] = prod.id
        IDS['area'] = area.id
        IDS['admin'] = admin.id
        IDS['vend'] = vend.id
        yield flask_app
        _db.drop_all()


def _login(app, username):
    c = app.test_client()
    c.post('/login', data={'username': username, 'password': 'pw'}, follow_redirects=True)
    return c


def test_registro_persiste(app):
    from app import RegistroLimpieza
    with app.app_context():
        r = RegistroLimpieza(area_id=IDS['area'], registrado_por=IDS['admin'], conforme=True)
        _db.session.add(r)
        _db.session.commit()
        got = _db.session.get(RegistroLimpieza, r.id)
        assert got is not None
        assert got.area.nombre == 'Sierra de cortar'
        assert got.area.producto.nombre == 'Sanitizante clorado'
        assert got.registrado_en is not None
