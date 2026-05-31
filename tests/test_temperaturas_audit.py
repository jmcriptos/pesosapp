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
