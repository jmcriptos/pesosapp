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


def test_camaras_no_admin_bloqueado(app):
    from app import Camara
    c = _login(app, 'vend')
    resp = c.post('/registros/temperaturas/camaras/nueva',
                  data={'nombre': 'X', 'tipo': 'refrigeracion', 'temp_min': '0', 'temp_max': '4'},
                  follow_redirects=False)
    assert resp.status_code in (302, 403)
    with app.app_context():
        assert Camara.query.filter_by(nombre='X').first() is None


def test_camaras_admin_crea(app):
    from app import Camara
    c = _login(app, 'admin')
    resp = c.post('/registros/temperaturas/camaras/nueva',
                  data={'nombre': 'Refri 2', 'tipo': 'refrigeracion', 'temp_min': '0', 'temp_max': '4'},
                  follow_redirects=True)
    assert resp.status_code == 200
    with app.app_context():
        assert Camara.query.filter_by(nombre='Refri 2').first() is not None


def test_camaras_rango_invalido_rechazado(app):
    from app import Camara
    c = _login(app, 'admin')
    c.post('/registros/temperaturas/camaras/nueva',
           data={'nombre': 'Mala', 'tipo': 'refrigeracion', 'temp_min': '5', 'temp_max': '1'},
           follow_redirects=True)
    with app.app_context():
        assert Camara.query.filter_by(nombre='Mala').first() is None


def test_camaras_toggle(app):
    from app import Camara
    c = _login(app, 'admin')
    c.post(f'/registros/temperaturas/camaras/{IDS["camara"]}/toggle', follow_redirects=True)
    with app.app_context():
        assert _db.session.get(Camara, IDS['camara']).activa is False


def test_registrar_requiere_login(app):
    client = app.test_client()
    resp = client.post('/registros/temperaturas/registrar',
                        data={'camara_id': IDS['camara'], 'temperatura': '-20'},
                        follow_redirects=False)
    assert resp.status_code == 302
    assert '/login' in resp.headers.get('Location', '')


def test_registrar_en_rango(app):
    from app import LecturaTemperatura
    c = _login(app, 'vend')
    resp = c.post('/registros/temperaturas/registrar',
                  data={'camara_id': IDS['camara'], 'temperatura': '-20'},
                  follow_redirects=True)
    assert resp.status_code == 200
    with app.app_context():
        lec = LecturaTemperatura.query.filter_by(camara_id=IDS['camara']).first()
        assert lec is not None
        assert lec.fuera_de_rango is False
        assert lec.registrado_por == IDS['vend']


def test_registrar_fuera_de_rango_sin_accion_rechazado(app):
    from app import LecturaTemperatura
    c = _login(app, 'vend')
    c.post('/registros/temperaturas/registrar',
           data={'camara_id': IDS['camara'], 'temperatura': '-5', 'accion_correctiva': ''},
           follow_redirects=True)
    with app.app_context():
        assert LecturaTemperatura.query.filter_by(camara_id=IDS['camara']).count() == 0


def test_registrar_fuera_de_rango_con_accion(app):
    from app import LecturaTemperatura
    c = _login(app, 'vend')
    c.post('/registros/temperaturas/registrar',
           data={'camara_id': IDS['camara'], 'temperatura': '-5',
                 'accion_tomada': 'Se movió el producto a otra cámara',
                 'accion_disposicion': 'producto OK'},
           follow_redirects=True)
    with app.app_context():
        lec = LecturaTemperatura.query.filter_by(camara_id=IDS['camara']).first()
        assert lec is not None
        assert lec.fuera_de_rango is True
        assert 'otra cámara' in lec.accion_tomada


def test_principal_muestra_estado(app):
    c = _login(app, 'vend')
    resp = c.get('/registros/temperaturas')
    assert resp.status_code == 200
    assert 'Congelación 1' in resp.data.decode('utf-8')


def test_historial_lista_lecturas(app):
    c = _login(app, 'vend')
    c.post('/registros/temperaturas/registrar',
           data={'camara_id': IDS['camara'], 'temperatura': '-20'}, follow_redirects=True)
    resp = c.get('/registros/temperaturas/historial')
    assert resp.status_code == 200
    body = resp.data.decode('utf-8')
    assert 'Congelación 1' in body
    assert '-20' in body


def test_export_devuelve_pdf(app):
    c = _login(app, 'vend')
    c.post('/registros/temperaturas/registrar',
           data={'camara_id': IDS['camara'], 'temperatura': '-20'}, follow_redirects=True)
    resp = c.post('/registros/temperaturas/export',
                  data={'fecha_inicio': '2000-01-01', 'fecha_fin': '2100-01-01'},
                  follow_redirects=False)
    assert resp.status_code == 200
    assert 'application/pdf' in resp.headers.get('Content-Type', '')


def test_camaras_admin_edita(app):
    from app import Camara
    from decimal import Decimal
    c = _login(app, 'admin')
    c.post(f'/registros/temperaturas/camaras/{IDS["camara"]}/editar',
           data={'nombre': 'Congelación 1 (editada)', 'tipo': 'congelacion',
                 'temp_min': '-30', 'temp_max': '-20'}, follow_redirects=True)
    with app.app_context():
        cam = _db.session.get(Camara, IDS['camara'])
        assert cam.nombre == 'Congelación 1 (editada)'
        assert cam.temp_max == Decimal('-20')


def test_camaras_congelacion_debe_ser_bajo_cero(app):
    from app import Camara
    c = _login(app, 'admin')
    # Congelación con rango positivo (15 a 18) debe rechazarse.
    c.post('/registros/temperaturas/camaras/nueva',
           data={'nombre': 'Congel Positiva', 'tipo': 'congelacion',
                 'temp_min': '15', 'temp_max': '18'}, follow_redirects=True)
    with app.app_context():
        assert Camara.query.filter_by(nombre='Congel Positiva').first() is None
    # Con rango bajo cero sí se crea.
    c.post('/registros/temperaturas/camaras/nueva',
           data={'nombre': 'Congel Buena', 'tipo': 'congelacion',
                 'temp_min': '-25', 'temp_max': '-18'}, follow_redirects=True)
    with app.app_context():
        assert Camara.query.filter_by(nombre='Congel Buena').first() is not None
