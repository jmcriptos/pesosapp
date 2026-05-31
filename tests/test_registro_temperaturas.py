"""Tests del registro de temperaturas de cámaras (HACCP)."""
import os
from decimal import Decimal

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
        from app import Rol, Territorio, Vendedor, Camara
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
        cam = Camara(nombre='Congelación 1', tipo='congelacion',
                     temp_min=Decimal('-25'), temp_max=Decimal('-18'), activa=True)
        _db.session.add(cam)
        _db.session.commit()
        IDS['camara'] = cam.id
        IDS['admin'] = admin.id
        IDS['vend'] = vend.id
        yield flask_app
        _db.drop_all()


def _login(app, username):
    c = app.test_client()
    c.post('/login', data={'username': username, 'password': 'pw'}, follow_redirects=True)
    return c


def test_camara_fuera_de_rango():
    from app import Camara
    from decimal import Decimal
    cam = Camara(nombre='C', tipo='refrigeracion', temp_min=Decimal('0'), temp_max=Decimal('4'))
    assert cam.fuera_de_rango(2) is False
    assert cam.fuera_de_rango(0) is False      # límite inferior incluido
    assert cam.fuera_de_rango(4) is False      # límite superior incluido
    assert cam.fuera_de_rango(5) is True
    assert cam.fuera_de_rango(-1) is True


def test_lectura_persiste(app):
    from app import Camara, LecturaTemperatura
    from decimal import Decimal
    with app.app_context():
        lec = LecturaTemperatura(
            camara_id=IDS['camara'], temperatura=Decimal('-20'),
            registrado_por=IDS['admin'], fuera_de_rango=False,
        )
        _db.session.add(lec)
        _db.session.commit()
        got = _db.session.get(LecturaTemperatura, lec.id)
        assert got is not None
        assert got.camara.nombre == 'Congelación 1'
        assert got.registrado_en is not None
