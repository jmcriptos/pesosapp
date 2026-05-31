"""Tests de las mejoras audit-ready del registro de temperaturas."""
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
    flask_app.config.update(TESTING=True, WTF_CSRF_ENABLED=False,
                            SQLALCHEMY_DATABASE_URI='sqlite:///:memory:')
    with flask_app.app_context():
        _db.create_all()
        from app import Rol, Territorio, Vendedor, Camara
        roles = {}
        for n in ('super_admin', 'supervisor', 'vendedor'):
            r = Rol(nombre=n, descripcion=n)
            _db.session.add(r); roles[n] = r
        terr = Territorio(nombre='t1', descripcion='T1')
        _db.session.add(terr); _db.session.flush()
        for u, rol in (('admin', 'super_admin'), ('super', 'supervisor'), ('vend', 'vendedor')):
            v = Vendedor(username=u, email=f'{u}@t.com', nombre_completo=u.title(),
                         rol_id=roles[rol].id, territorio_id=terr.id, activo=True)
            v.set_password('pw'); _db.session.add(v)
        cam = Camara(nombre='Cava 1', tipo='refrigeracion',
                     temp_min=Decimal('0'), temp_max=Decimal('4'), activa=True)
        _db.session.add(cam); _db.session.commit()
        IDS['camara'] = cam.id
        yield flask_app
        _db.drop_all()


def _login(app, username):
    c = app.test_client()
    c.post('/login', data={'username': username, 'password': 'pw'}, follow_redirects=True)
    return c


def test_get_registro_config_singleton(app):
    from app import _get_registro_config, RegistroConfig
    with app.app_context():
        c1 = _get_registro_config()
        c2 = _get_registro_config()
        assert c1.id == c2.id
        assert RegistroConfig.query.count() == 1
        assert c1.codigo_documento  # tiene un valor por defecto


def test_revision_y_columnas_accion_existen(app):
    from app import RevisionRegistro, LecturaTemperatura
    from datetime import date
    with app.app_context():
        rev = RevisionRegistro(periodo_desde=date(2026, 5, 1), periodo_hasta=date(2026, 5, 31))
        _db.session.add(rev)
        lec = LecturaTemperatura(camara_id=IDS['camara'], temperatura=Decimal('2'),
                                 fuera_de_rango=False, accion_tomada='x', accion_disposicion='y',
                                 accion_causa='c', accion_responsable='r')
        _db.session.add(lec); _db.session.commit()
        assert RevisionRegistro.query.count() == 1
        got = LecturaTemperatura.query.get(lec.id)
        assert got.accion_tomada == 'x' and got.accion_disposicion == 'y'


def test_config_no_admin_bloqueado(app):
    c = _login(app, 'vend')
    resp = c.post('/registros/temperaturas/config',
                  data={'codigo_documento': 'X', 'version': '9', 'frecuencia_texto': 'f'},
                  follow_redirects=False)
    assert resp.status_code in (302, 403)
    from app import RegistroConfig
    with app.app_context():
        cfg = RegistroConfig.query.first()
        assert cfg is None or cfg.codigo_documento != 'X'


def test_config_admin_guarda(app):
    c = _login(app, 'admin')
    resp = c.post('/registros/temperaturas/config',
                  data={'codigo_documento': 'FR-9', 'version': '2',
                        'frecuencia_texto': '3 veces/día', 'termometro': 'TP-1',
                        'termometro_calibrado_en': '2026-01-15'},
                  follow_redirects=True)
    assert resp.status_code == 200
    from app import RegistroConfig
    with app.app_context():
        cfg = RegistroConfig.query.first()
        assert cfg.codigo_documento == 'FR-9'
        assert cfg.termometro == 'TP-1'
        assert cfg.termometro_calibrado_en.isoformat() == '2026-01-15'


def test_fuera_de_rango_sin_obligatorios_rechazado(app):
    from app import LecturaTemperatura
    c = _login(app, 'vend')
    c.post('/registros/temperaturas/registrar',
           data={'camara_id': IDS['camara'], 'temperatura': '9',
                 'accion_tomada': '', 'accion_disposicion': ''}, follow_redirects=True)
    with app.app_context():
        assert LecturaTemperatura.query.filter_by(camara_id=IDS['camara']).count() == 0


def test_fuera_de_rango_con_obligatorios_guarda(app):
    from app import LecturaTemperatura
    c = _login(app, 'vend')
    c.post('/registros/temperaturas/registrar',
           data={'camara_id': IDS['camara'], 'temperatura': '9',
                 'accion_causa': 'puerta abierta', 'accion_tomada': 'se cerró',
                 'accion_responsable': 'Juan', 'accion_disposicion': 'producto OK'},
           follow_redirects=True)
    with app.app_context():
        lec = LecturaTemperatura.query.filter_by(camara_id=IDS['camara']).first()
        assert lec is not None and lec.fuera_de_rango is True
        assert lec.accion_tomada == 'se cerró'
        assert lec.accion_disposicion == 'producto OK'
        assert lec.accion_causa == 'puerta abierta'


def test_en_rango_ignora_accion(app):
    from app import LecturaTemperatura
    c = _login(app, 'vend')
    c.post('/registros/temperaturas/registrar',
           data={'camara_id': IDS['camara'], 'temperatura': '2',
                 'accion_tomada': 'no aplica'}, follow_redirects=True)
    with app.app_context():
        lec = LecturaTemperatura.query.filter_by(camara_id=IDS['camara']).first()
        assert lec is not None and lec.fuera_de_rango is False
        assert lec.accion_tomada is None


def test_revisar_supervisor_crea_revision(app):
    from app import RevisionRegistro
    c = _login(app, 'super')
    resp = c.post('/registros/temperaturas/revisar',
                  data={'fecha_inicio': '2026-05-01', 'fecha_fin': '2026-05-31'},
                  follow_redirects=True)
    assert resp.status_code == 200
    with app.app_context():
        assert RevisionRegistro.query.count() == 1


def test_revisar_vendedor_bloqueado(app):
    from app import RevisionRegistro
    c = _login(app, 'vend')
    resp = c.post('/registros/temperaturas/revisar',
                  data={'fecha_inicio': '2026-05-01', 'fecha_fin': '2026-05-31'},
                  follow_redirects=False)
    assert resp.status_code in (302, 403)
    with app.app_context():
        assert RevisionRegistro.query.count() == 0


def test_export_pdf_audit(app):
    c = _login(app, 'admin')
    c.post('/registros/temperaturas/registrar',
           data={'camara_id': IDS['camara'], 'temperatura': '2'}, follow_redirects=True)
    resp = c.post('/registros/temperaturas/export',
                  data={'fecha_inicio': '2000-01-01', 'fecha_fin': '2100-01-01'},
                  follow_redirects=False)
    assert resp.status_code == 200
    assert 'application/pdf' in resp.headers.get('Content-Type', '')
