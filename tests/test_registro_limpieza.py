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


def test_productos_admin_crea(app):
    from app import ProductoLimpieza
    c = _login(app, 'admin')
    c.post('/registros/limpieza/productos/nuevo',
           data={'nombre': 'Detergente alcalino', 'dilucion': '20 ml / 1 L',
                 'procedimiento': 'Fregar y enjuagar'}, follow_redirects=True)
    with app.app_context():
        p = ProductoLimpieza.query.filter_by(nombre='Detergente alcalino').first()
        assert p is not None
        assert p.dilucion == '20 ml / 1 L'


def test_productos_sin_dilucion_rechazado(app):
    from app import ProductoLimpieza
    c = _login(app, 'admin')
    c.post('/registros/limpieza/productos/nuevo',
           data={'nombre': 'Sin dilucion', 'dilucion': ''}, follow_redirects=True)
    with app.app_context():
        assert ProductoLimpieza.query.filter_by(nombre='Sin dilucion').first() is None


def test_productos_consulta_visible_para_todos(app):
    c = _login(app, 'vend')
    resp = c.get('/registros/limpieza/productos')
    assert resp.status_code == 200
    assert 'Sanitizante clorado' in resp.data.decode('utf-8')


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


def test_areas_no_admin_bloqueado(app):
    from app import AreaLimpieza
    c = _login(app, 'vend')
    resp = c.post('/registros/limpieza/areas/nueva',
                  data={'nombre': 'X', 'tipo': 'equipo'}, follow_redirects=False)
    assert resp.status_code in (302, 403)
    with app.app_context():
        assert AreaLimpieza.query.filter_by(nombre='X').first() is None


def test_areas_admin_crea(app):
    from app import AreaLimpieza
    c = _login(app, 'admin')
    resp = c.post('/registros/limpieza/areas/nueva',
                  data={'nombre': 'Mesa de empaque', 'tipo': 'espacio',
                        'producto_id': IDS['producto'], 'frecuencia_texto': 'Por turno'},
                  follow_redirects=True)
    assert resp.status_code == 200
    with app.app_context():
        a = AreaLimpieza.query.filter_by(nombre='Mesa de empaque').first()
        assert a is not None
        assert a.tipo == 'espacio'
        assert a.producto_id == IDS['producto']


def test_areas_tipo_invalido_rechazado(app):
    from app import AreaLimpieza
    c = _login(app, 'admin')
    c.post('/registros/limpieza/areas/nueva',
           data={'nombre': 'Mala', 'tipo': 'xxx'}, follow_redirects=True)
    with app.app_context():
        assert AreaLimpieza.query.filter_by(nombre='Mala').first() is None


def test_areas_admin_edita(app):
    from app import AreaLimpieza
    c = _login(app, 'admin')
    c.post(f'/registros/limpieza/areas/{IDS["area"]}/editar',
           data={'nombre': 'Sierra (editada)', 'tipo': 'equipo',
                 'producto_id': '', 'frecuencia_texto': 'Semanal'}, follow_redirects=True)
    with app.app_context():
        a = _db.session.get(AreaLimpieza, IDS['area'])
        assert a.nombre == 'Sierra (editada)'
        assert a.producto_id is None


def test_areas_toggle(app):
    from app import AreaLimpieza
    c = _login(app, 'admin')
    c.post(f'/registros/limpieza/areas/{IDS["area"]}/toggle', follow_redirects=True)
    with app.app_context():
        assert _db.session.get(AreaLimpieza, IDS['area']).activa is False


def test_registrar_requiere_login(app):
    client = app.test_client()
    resp = client.post('/registros/limpieza/registrar',
                       data={'area_id': IDS['area'], 'conforme': 'si'},
                       follow_redirects=False)
    assert resp.status_code == 302
    assert '/login' in resp.headers.get('Location', '')


def test_registrar_conforme(app):
    from app import RegistroLimpieza
    c = _login(app, 'vend')
    resp = c.post('/registros/limpieza/registrar',
                  data={'area_id': IDS['area'], 'conforme': 'si',
                        'verificado_por': IDS['admin']}, follow_redirects=True)
    assert resp.status_code == 200
    with app.app_context():
        r = RegistroLimpieza.query.filter_by(area_id=IDS['area']).first()
        assert r is not None
        assert r.conforme is True
        assert r.registrado_por == IDS['vend']


def test_registrar_no_conforme_sin_accion_rechazado(app):
    from app import RegistroLimpieza
    c = _login(app, 'vend')
    c.post('/registros/limpieza/registrar',
           data={'area_id': IDS['area'], 'conforme': 'no'}, follow_redirects=True)
    with app.app_context():
        assert RegistroLimpieza.query.filter_by(area_id=IDS['area']).count() == 0


def test_registrar_no_conforme_con_accion(app):
    from app import RegistroLimpieza
    c = _login(app, 'vend')
    c.post('/registros/limpieza/registrar',
           data={'area_id': IDS['area'], 'conforme': 'no',
                 'accion_tomada': 'Se volvio a limpiar',
                 'accion_disposicion': 'Quedo conforme',
                 'verificado_por': IDS['admin']}, follow_redirects=True)
    with app.app_context():
        r = RegistroLimpieza.query.filter_by(area_id=IDS['area']).first()
        assert r is not None
        assert r.conforme is False
        assert 'volvio a limpiar' in r.accion_tomada


def test_principal_muestra_area(app):
    c = _login(app, 'vend')
    resp = c.get('/registros/limpieza')
    assert resp.status_code == 200
    body = resp.data.decode('utf-8')
    assert 'Sierra de cortar' in body
    assert 'Sanitizante clorado' in body


def test_historial_lista_registros(app):
    c = _login(app, 'vend')
    c.post('/registros/limpieza/registrar',
           data={'area_id': IDS['area'], 'conforme': 'si',
                 'verificado_por': IDS['admin']}, follow_redirects=True)
    resp = c.get('/registros/limpieza/historial')
    assert resp.status_code == 200
    assert 'Sierra de cortar' in resp.data.decode('utf-8')


def test_revisar_no_admin_bloqueado(app):
    from app import RevisionLimpieza
    c = _login(app, 'vend')
    resp = c.post('/registros/limpieza/revisar',
                  data={'fecha_inicio': '2026-05-01', 'fecha_fin': '2026-05-31'},
                  follow_redirects=False)
    assert resp.status_code in (302, 403)
    with app.app_context():
        assert RevisionLimpieza.query.count() == 0


def test_revisar_marca_periodo(app):
    from app import RevisionLimpieza
    from datetime import date
    c = _login(app, 'admin')
    c.post('/registros/limpieza/revisar',
           data={'fecha_inicio': '2026-05-01', 'fecha_fin': '2026-05-31'},
           follow_redirects=True)
    with app.app_context():
        rev = RevisionLimpieza.query.first()
        assert rev is not None
        assert rev.revisado_por == IDS['admin']
        assert rev.periodo_desde == date(2026, 5, 1)
        assert rev.periodo_hasta == date(2026, 5, 31)


def test_export_devuelve_pdf(app):
    c = _login(app, 'vend')
    c.post('/registros/limpieza/registrar',
           data={'area_id': IDS['area'], 'conforme': 'si',
                 'verificado_por': IDS['admin']}, follow_redirects=True)
    resp = c.post('/registros/limpieza/export',
                  data={'fecha_inicio': '2000-01-01', 'fecha_fin': '2100-01-01'},
                  follow_redirects=False)
    assert resp.status_code == 200
    assert 'application/pdf' in resp.headers.get('Content-Type', '')


def test_config_no_admin_bloqueado(app):
    c = _login(app, 'vend')
    resp = c.get('/registros/limpieza/config', follow_redirects=False)
    assert resp.status_code in (302, 403)


def test_config_admin_guarda(app):
    from app import LimpiezaConfig
    c = _login(app, 'admin')
    c.post('/registros/limpieza/config',
           data={'codigo_documento': 'FR-HACCP-LIMP-02', 'version': '2',
                 'frecuencia_texto': 'Diaria', 'responsable_verificacion': 'Jefe de calidad'},
           follow_redirects=True)
    with app.app_context():
        cfg = LimpiezaConfig.query.first()
        assert cfg.codigo_documento == 'FR-HACCP-LIMP-02'
        assert cfg.responsable_verificacion == 'Jefe de calidad'


def test_hub_registros_ok(app):
    c = _login(app, 'vend')
    resp = c.get('/registros')
    assert resp.status_code == 200
    body = resp.data.decode('utf-8')
    assert 'Temperaturas' in body
    assert 'Limpieza' in body


def test_registro_campos_haccp(app):
    from app import RegistroLimpieza
    with app.app_context():
        r = RegistroLimpieza(area_id=IDS['area'], registrado_por=IDS['vend'],
                             verificado_por=IDS['admin'], conforme=True,
                             concentracion_ppm=250, metodo_verificacion='visual')
        _db.session.add(r)
        _db.session.commit()
        got = _db.session.get(RegistroLimpieza, r.id)
        assert got.concentracion_ppm == 250
        assert got.metodo_verificacion == 'visual'
        assert got.verificado_por_vendedor.nombre_completo == 'Admin'
        assert got.registrado_por_vendedor.nombre_completo == 'Vend'


def _crear_area_con_sani(app):
    from app import AreaLimpieza, ProductoLimpieza
    with app.app_context():
        sani = ProductoLimpieza(nombre='Sani-T-10 Plus', dilucion='Según ficha técnica', activo=True)
        _db.session.add(sani)
        _db.session.flush()
        a = AreaLimpieza(nombre='Mesa con sani', tipo='equipo',
                         sanitizante_id=sani.id, activa=True)
        _db.session.add(a)
        _db.session.commit()
        return a.id


def test_registrar_verifico_obligatorio(app):
    from app import RegistroLimpieza
    c = _login(app, 'vend')
    c.post('/registros/limpieza/registrar',
           data={'area_id': IDS['area'], 'conforme': 'si'}, follow_redirects=True)
    with app.app_context():
        assert RegistroLimpieza.query.filter_by(area_id=IDS['area']).count() == 0


def test_registrar_verifico_distinto_operador(app):
    from app import RegistroLimpieza
    c = _login(app, 'vend')  # operador = vend
    c.post('/registros/limpieza/registrar',
           data={'area_id': IDS['area'], 'conforme': 'si',
                 'verificado_por': IDS['vend']}, follow_redirects=True)
    with app.app_context():
        assert RegistroLimpieza.query.filter_by(area_id=IDS['area']).count() == 0


def test_registrar_ppm_obligatorio_con_sanitizante(app):
    from app import RegistroLimpieza
    area_id = _crear_area_con_sani(app)
    c = _login(app, 'vend')
    c.post('/registros/limpieza/registrar',
           data={'area_id': area_id, 'conforme': 'si',
                 'verificado_por': IDS['admin']}, follow_redirects=True)
    with app.app_context():
        assert RegistroLimpieza.query.filter_by(area_id=area_id).count() == 0


def test_registrar_ppm_fuera_rango_bloquea_conforme(app):
    from app import RegistroLimpieza
    area_id = _crear_area_con_sani(app)
    c = _login(app, 'vend')
    c.post('/registros/limpieza/registrar',
           data={'area_id': area_id, 'conforme': 'si', 'concentracion_ppm': '120',
                 'verificado_por': IDS['admin']}, follow_redirects=True)
    with app.app_context():
        assert RegistroLimpieza.query.filter_by(area_id=area_id).count() == 0


def test_registrar_ppm_en_rango_conforme_ok(app):
    from app import RegistroLimpieza
    area_id = _crear_area_con_sani(app)
    c = _login(app, 'vend')
    c.post('/registros/limpieza/registrar',
           data={'area_id': area_id, 'conforme': 'si', 'concentracion_ppm': '250',
                 'verificado_por': IDS['admin'], 'metodo_verificacion': 'visual'},
           follow_redirects=True)
    with app.app_context():
        r = RegistroLimpieza.query.filter_by(area_id=area_id).first()
        assert r is not None
        assert r.concentracion_ppm == 250
        assert r.verificado_por == IDS['admin']
        assert r.metodo_verificacion == 'visual'


def test_registrar_ppm_fuera_rango_permitido_si_no_conforme(app):
    from app import RegistroLimpieza
    area_id = _crear_area_con_sani(app)
    c = _login(app, 'vend')
    c.post('/registros/limpieza/registrar',
           data={'area_id': area_id, 'conforme': 'no', 'concentracion_ppm': '120',
                 'verificado_por': IDS['admin'],
                 'accion_tomada': 'Se reajustó la dilución',
                 'accion_disposicion': 'Se volvió a medir'}, follow_redirects=True)
    with app.app_context():
        r = RegistroLimpieza.query.filter_by(area_id=area_id).first()
        assert r is not None
        assert r.conforme is False
        assert r.concentracion_ppm == 120


def test_index_sheet_tiene_campos_nuevos(app):
    c = _login(app, 'vend')
    body = c.get('/registros/limpieza').data.decode('utf-8')
    assert 'name="verificado_por"' in body
    assert 'name="concentracion_ppm"' in body
    assert 'name="metodo_verificacion"' in body


def test_dilucion_es_texto_sin_limite(app):
    """dilucion debe ser Text (sin límite) para no romper con textos largos en Postgres."""
    from app import ProductoLimpieza
    from sqlalchemy import Text
    col = ProductoLimpieza.__table__.columns['dilucion']
    assert isinstance(col.type, Text)


def test_crear_producto_dilucion_larga(app):
    from app import ProductoLimpieza
    c = _login(app, 'admin')
    larga = 'x' * 400
    c.post('/registros/limpieza/productos/nuevo',
           data={'nombre': 'Prod largo', 'dilucion': larga}, follow_redirects=True)
    with app.app_context():
        p = ProductoLimpieza.query.filter_by(nombre='Prod largo').first()
        assert p is not None
        assert len(p.dilucion) == 400


def test_registrar_ppm_negativo_rechazado(app):
    from app import RegistroLimpieza
    area_id = _crear_area_con_sani(app)
    c = _login(app, 'vend')
    c.post('/registros/limpieza/registrar',
           data={'area_id': area_id, 'conforme': 'no', 'concentracion_ppm': '-5',
                 'verificado_por': IDS['admin'],
                 'accion_tomada': 'x', 'accion_disposicion': 'y'}, follow_redirects=True)
    with app.app_context():
        assert RegistroLimpieza.query.filter_by(area_id=area_id).count() == 0


def test_registrar_no_conforme_sin_ppm_rechazado_con_sanitizante(app):
    from app import RegistroLimpieza
    area_id = _crear_area_con_sani(app)
    c = _login(app, 'vend')
    c.post('/registros/limpieza/registrar',
           data={'area_id': area_id, 'conforme': 'no',
                 'verificado_por': IDS['admin'],
                 'accion_tomada': 'x', 'accion_disposicion': 'y'}, follow_redirects=True)
    with app.app_context():
        assert RegistroLimpieza.query.filter_by(area_id=area_id).count() == 0


def test_historial_muestra_ppm_y_verifico(app):
    area_id = _crear_area_con_sani(app)
    c = _login(app, 'vend')
    c.post('/registros/limpieza/registrar',
           data={'area_id': area_id, 'conforme': 'si', 'concentracion_ppm': '250',
                 'verificado_por': IDS['admin']}, follow_redirects=True)
    body = c.get('/registros/limpieza/historial').data.decode('utf-8')
    assert '250' in body                       # ppm value in row
    assert 'Verificó' in body                  # column header
    assert '<div class="ops-cell-muted">Admin' in body   # verificador in row cell


def test_area_eliminar_sin_registros(app):
    from app import AreaLimpieza
    c = _login(app, 'admin')
    with app.app_context():
        a = AreaLimpieza(nombre='Duplicado seed', tipo='equipo', activa=True)
        _db.session.add(a)
        _db.session.commit()
        aid = a.id
    c.post(f'/registros/limpieza/areas/{aid}/eliminar', follow_redirects=True)
    with app.app_context():
        assert _db.session.get(AreaLimpieza, aid) is None


def test_area_eliminar_con_registros_bloqueado(app):
    from app import AreaLimpieza, RegistroLimpieza
    c = _login(app, 'admin')
    with app.app_context():
        r = RegistroLimpieza(area_id=IDS['area'], registrado_por=IDS['admin'], conforme=True)
        _db.session.add(r)
        _db.session.commit()
    c.post(f'/registros/limpieza/areas/{IDS["area"]}/eliminar', follow_redirects=True)
    with app.app_context():
        assert _db.session.get(AreaLimpieza, IDS['area']) is not None


def test_area_eliminar_no_admin_bloqueado(app):
    from app import AreaLimpieza
    c = _login(app, 'vend')
    resp = c.post(f'/registros/limpieza/areas/{IDS["area"]}/eliminar', follow_redirects=False)
    assert resp.status_code in (302, 403)
    with app.app_context():
        assert _db.session.get(AreaLimpieza, IDS['area']) is not None


def test_areas_list_muestra_boton_eliminar(app):
    c = _login(app, 'admin')
    body = c.get('/registros/limpieza/areas').data.decode('utf-8')
    assert '/eliminar' in body


def test_registro_historial_eliminar_admin(app):
    from app import RegistroLimpieza
    c = _login(app, 'admin')
    with app.app_context():
        r = RegistroLimpieza(area_id=IDS['area'], registrado_por=IDS['admin'], conforme=True)
        _db.session.add(r)
        _db.session.commit()
        rid = r.id
    c.post(f'/registros/limpieza/registro/{rid}/eliminar', follow_redirects=True)
    with app.app_context():
        assert _db.session.get(RegistroLimpieza, rid) is None


def test_registro_historial_eliminar_no_admin_bloqueado(app):
    from app import RegistroLimpieza
    c = _login(app, 'vend')
    with app.app_context():
        r = RegistroLimpieza(area_id=IDS['area'], registrado_por=IDS['vend'], conforme=True)
        _db.session.add(r)
        _db.session.commit()
        rid = r.id
    resp = c.post(f'/registros/limpieza/registro/{rid}/eliminar', follow_redirects=False)
    assert resp.status_code == 302
    with app.app_context():
        assert _db.session.get(RegistroLimpieza, rid) is not None


def test_historial_boton_eliminar_solo_admin(app):
    from app import RegistroLimpieza
    with app.app_context():
        r = RegistroLimpieza(area_id=IDS['area'], registrado_por=IDS['admin'], conforme=True)
        _db.session.add(r)
        _db.session.commit()
    # Use a single client with explicit logout between users to avoid Flask-Login g cache bleed
    c = app.test_client()
    c.post('/login', data={'username': 'admin', 'password': 'pw'}, follow_redirects=False)
    admin_body = c.get('/registros/limpieza/historial').data.decode('utf-8')
    c.get('/logout', follow_redirects=False)
    c.post('/login', data={'username': 'vend', 'password': 'pw'}, follow_redirects=False)
    vend_body = c.get('/registros/limpieza/historial').data.decode('utf-8')
    assert 'Eliminar registro' in admin_body
    assert 'Eliminar registro' not in vend_body


def test_seed_catalogo_idempotente(app):
    from app import _seed_catalogo_limpieza, ProductoLimpieza, AreaLimpieza
    with app.app_context():
        _seed_catalogo_limpieza()
        _seed_catalogo_limpieza()  # segunda corrida no duplica
        assert ProductoLimpieza.query.filter_by(nombre='Sani-T-10 Plus').count() == 1
        assert ProductoLimpieza.query.filter_by(nombre='Big Punch').count() == 1
        eq = AreaLimpieza.query.filter_by(nombre='Embutidora Vemag').first()
        assert eq is not None and eq.tipo == 'equipo'
        assert eq.sanitizante.nombre == 'Sani-T-10 Plus'
        esp = AreaLimpieza.query.filter_by(nombre='Almacenes').first()
        assert esp is not None and esp.tipo == 'espacio'
        assert esp.sanitizante_id is None
