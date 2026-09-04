"""Tests de acceso y andamiaje del módulo de maquila."""
import os
from datetime import date
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
        from app import Rol, Territorio, Vendedor
        ra = Rol(nombre='super_admin', descripcion='Admin')
        rv = Rol(nombre='vendedor', descripcion='Vendedor')
        terr = Territorio(nombre='t1', descripcion='T1')
        _db.session.add_all([ra, rv, terr])
        _db.session.flush()
        admin = Vendedor(username='admin', email='a@t.com', nombre_completo='Admin',
                         rol_id=ra.id, territorio_id=terr.id, activo=True)
        admin.set_password('pw')
        vend = Vendedor(username='vend', email='v@t.com', nombre_completo='Vend',
                        rol_id=rv.id, territorio_id=terr.id, activo=True)
        vend.set_password('pw')
        _db.session.add_all([admin, vend])
        _db.session.commit()
        IDS['admin'] = admin.id
        yield flask_app
        _db.drop_all()


def _login(app, username):
    c = app.test_client()
    c.post('/login', data={'username': username, 'password': 'pw'}, follow_redirects=True)
    return c


def test_las_tablas_de_maquila_existen(app):
    """create_all() debe ver los modelos: si maquila.models no está importado,
    las tablas no se crean y todo el módulo falla sin explicación visible."""
    with app.app_context():
        nombres = set(_db.inspect(_db.engine).get_table_names())
    esperadas = {
        'ingrediente', 'recepcion_ingrediente', 'recepcion_linea', 'recepcion_bulto',
        'recepcion_foto', 'receta', 'receta_ingrediente', 'corrida_produccion',
        'corrida_caja', 'corrida_consumo', 'corrida_consumo_origen',
        'movimiento_ingrediente',
    }
    assert esperadas <= nombres


def test_admin_entra_al_indice(app):
    c = _login(app, 'admin')
    r = c.get('/maquila')
    assert r.status_code == 200


def test_vendedor_no_entra(app):
    c = _login(app, 'vend')
    r = c.get('/maquila', follow_redirects=False)
    assert r.status_code == 302


def test_anonimo_no_entra(app):
    r = app.test_client().get('/maquila', follow_redirects=False)
    assert r.status_code == 302


def test_alta_de_ingrediente(app):
    from maquila.models import Ingrediente
    c = _login(app, 'admin')
    r = c.post('/maquila/ingredientes', data={'nombre': 'Tripa natural',
                                              'unidad': 'ud'},
               follow_redirects=True)
    assert r.status_code == 200
    with app.app_context():
        assert Ingrediente.query.filter_by(nombre='Tripa natural').count() == 1


def test_alta_de_recepcion_por_la_ruta(app):
    from maquila.models import Ingrediente, RecepcionIngrediente
    with app.app_context():
        from app import Cliente
        cli = Cliente(nombre='Maquila SA')
        ing = Ingrediente(nombre='Carne de res')
        _db.session.add_all([cli, ing])
        _db.session.commit()
        cli_id, ing_id = cli.id, ing.id

    c = _login(app, 'admin')
    r = c.post('/maquila/recepciones/nueva', data={
        'cliente_id': str(cli_id),
        'recibido_en': '2026-09-03',
        'documento_cliente': '',
        'temperatura': '-18.5',
        'linea_ingrediente_id': [str(ing_id)],
        'linea_lote_cliente': [''],
        'linea_fecha_vencimiento': [''],
        'linea_peso_total': [''],
        'linea_bultos': ['12.5,11.5'],
    }, follow_redirects=True)
    assert r.status_code == 200
    with app.app_context():
        rec = RecepcionIngrediente.query.one()
        assert rec.codigo == 'R-2026-0001'
        assert rec.documento_cliente is None
        assert rec.lineas[0].peso_total == Decimal('24.000')
        assert len(rec.lineas[0].bultos) == 2


def test_rechaza_foto_con_mimetype_no_permitido(app):
    """Un SVG con <script> adentro no debe poder colarse como 'foto': si se
    sirviera después con su Content-Type declarado, se ejecutaría como
    documento desde el origen de la app."""
    import io
    from maquila.models import Ingrediente, RecepcionIngrediente
    with app.app_context():
        from app import Cliente
        cli = Cliente(nombre='Maquila SVG SA')
        ing = Ingrediente(nombre='Carne de res SVG')
        _db.session.add_all([cli, ing])
        _db.session.commit()
        cli_id, ing_id = cli.id, ing.id

    c = _login(app, 'admin')
    svg = b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>'
    r = c.post('/maquila/recepciones/nueva', data={
        'cliente_id': str(cli_id),
        'recibido_en': '2026-09-03',
        'linea_ingrediente_id': [str(ing_id)],
        'linea_lote_cliente': [''],
        'linea_fecha_vencimiento': [''],
        'linea_peso_total': ['10'],
        'linea_bultos': [''],
        'fotos': (io.BytesIO(svg), 'evil.svg', 'image/svg+xml'),
    }, content_type='multipart/form-data', follow_redirects=True)
    assert r.status_code == 200
    assert 'no permitido'.encode('utf-8') in r.data
    with app.app_context():
        assert RecepcionIngrediente.query.count() == 0


def test_firma_base64_corrupta_no_revienta_la_recepcion(app):
    """base64.b64decode sobre basura no debe tirar un 500: la recepción se
    guarda igual, sin firma."""
    from maquila.models import Ingrediente, RecepcionIngrediente
    with app.app_context():
        from app import Cliente
        cli = Cliente(nombre='Maquila Firma Rota SA')
        ing = Ingrediente(nombre='Carne de res firma')
        _db.session.add_all([cli, ing])
        _db.session.commit()
        cli_id, ing_id = cli.id, ing.id

    c = _login(app, 'admin')
    r = c.post('/maquila/recepciones/nueva', data={
        'cliente_id': str(cli_id),
        'recibido_en': '2026-09-03',
        'linea_ingrediente_id': [str(ing_id)],
        'linea_lote_cliente': [''],
        'linea_fecha_vencimiento': [''],
        'linea_peso_total': ['10'],
        'linea_bultos': [''],
        'firma_png': 'data:image/png;base64,***no-es-base64-valido***',
    }, follow_redirects=True)
    assert r.status_code == 200
    with app.app_context():
        rec = RecepcionIngrediente.query.one()
        assert rec.firma is None


def _cliente_producto_ingrediente(app):
    from app import Cliente, Producto
    from maquila.models import Ingrediente
    with app.app_context():
        cli = Cliente(nombre='Maquila SA')
        prod = Producto(nombre='Chorizo', se_pesa=True, tax_rate=10)
        ing = Ingrediente(nombre='Carne de res')
        _db.session.add_all([cli, prod, ing])
        _db.session.commit()
        return cli.id, prod.id, ing.id


def test_abrir_una_corrida_por_la_ruta(app):
    from maquila.models import CorridaProduccion
    cli_id, prod_id, _ing = _cliente_producto_ingrediente(app)
    c = _login(app, 'admin')
    r = c.post('/maquila/corridas/nueva', data={
        'cliente_id': str(cli_id), 'producto_id': str(prod_id),
        'lote': 'L-0903', 'fecha_produccion': '2026-09-03',
        'fecha_vencimiento': '2026-12-03'}, follow_redirects=True)
    assert r.status_code == 200
    with app.app_context():
        corrida = CorridaProduccion.query.one()
        assert corrida.lote == 'L-0903'
        assert corrida.codigo == 'P-2026-0001'


def test_cerrar_una_corrida_sin_saldo_avisa_y_no_cierra(app):
    """El bloqueo tiene que llegar como mensaje, no como un 500."""
    from maquila import servicios
    from maquila.models import CorridaProduccion
    from decimal import Decimal as D
    cli_id, prod_id, ing_id = _cliente_producto_ingrediente(app)
    with app.app_context():
        corrida = servicios.abrir_corrida(
            cliente_id=cli_id, producto_id=prod_id, lote='L-1',
            fecha_produccion=date(2026, 9, 3), vendedor_id=IDS['admin'])
        servicios.agregar_caja_producida(corrida, D('40'))
        _db.session.commit()
        corrida_id = corrida.id

    c = _login(app, 'admin')
    r = c.post(f'/maquila/corridas/{corrida_id}/cerrar', data={
        'consumo_ingrediente_id': [str(ing_id)],
        'consumo_real': ['50']}, follow_redirects=True)
    assert r.status_code == 200
    assert b'Faltan' in r.data
    with app.app_context():
        assert _db.session.get(CorridaProduccion, corrida_id).estado == 'abierta'


def test_recalcular_reparto_muestra_el_declarado_no_el_teorico(app):
    """El reparto que se ve tiene que ser el que se va a ejecutar: si el
    operario edita el consumo real, hay que recalcular contra eso, no seguir
    mostrando el estimado de la receta (Ronda de arreglo 1, punto 1)."""
    from maquila import servicios
    from maquila.models import CorridaConsumo, CorridaProduccion, Receta, RecetaIngrediente
    from decimal import Decimal as D
    cli_id, prod_id, ing_id = _cliente_producto_ingrediente(app)
    with app.app_context():
        receta = Receta(producto_id=prod_id, cliente_id=None, nombre='Receta test',
                        base_kg=D('100'), activa=True, creada_por=IDS['admin'])
        _db.session.add(receta)
        _db.session.flush()
        _db.session.add(RecetaIngrediente(receta_id=receta.id, ingrediente_id=ing_id,
                                          cantidad=D('50')))
        _db.session.commit()

        servicios.crear_recepcion(
            cliente_id=cli_id, recibido_en=date(2026, 9, 1), vendedor_id=IDS['admin'],
            lineas=[{'ingrediente_id': ing_id, 'peso_total': D('100')}])

        corrida = servicios.abrir_corrida(
            cliente_id=cli_id, producto_id=prod_id, lote='L-RECALC',
            fecha_produccion=date(2026, 9, 3), vendedor_id=IDS['admin'])
        servicios.agregar_caja_producida(corrida, D('20'))
        _db.session.commit()
        corrida_id = corrida.id

    c = _login(app, 'admin')

    # El teórico para 20kg producidos con esa receta es 10.000: se ve como
    # estimado hasta que alguien lo recalcule contra lo declarado.
    r = c.get(f'/maquila/corridas/{corrida_id}')
    assert r.status_code == 200
    assert b'10.000' in r.data
    assert 'estimado según la receta'.encode('utf-8') in r.data

    r = c.post(f'/maquila/corridas/{corrida_id}/recalcular', data={
        'consumo_ingrediente_id': [str(ing_id)],
        'consumo_real': ['37.5']}, follow_redirects=True)
    assert r.status_code == 200
    assert b'37.5' in r.data
    assert b'consumo declarado' in r.data

    with app.app_context():
        assert _db.session.get(CorridaProduccion, corrida_id).estado == 'abierta'
        assert CorridaConsumo.query.count() == 0


def test_producto_id_no_numerico_no_revienta(app):
    """Basura en `producto_id` tiene que dar un mensaje, no un 500
    (Ronda de arreglo 1, punto 3)."""
    from maquila.models import CorridaProduccion
    cli_id, _prod_id, _ing_id = _cliente_producto_ingrediente(app)
    c = _login(app, 'admin')
    r = c.post('/maquila/corridas/nueva', data={
        'cliente_id': str(cli_id), 'producto_id': 'no-es-un-numero',
        'lote': 'L-BASURA', 'fecha_produccion': '2026-09-03'}, follow_redirects=True)
    assert r.status_code == 200
    assert b'cliente y un producto' in r.data
    with app.app_context():
        assert CorridaProduccion.query.count() == 0


def test_el_indice_lista_los_clientes_con_recepciones(app):
    from maquila.models import Ingrediente
    from maquila import servicios
    with app.app_context():
        from app import Cliente
        cli = Cliente(nombre='Maquila SA')
        ing = Ingrediente(nombre='Carne de res')
        _db.session.add_all([cli, ing])
        _db.session.commit()
        servicios.crear_recepcion(
            cliente_id=cli.id, recibido_en=date(2026, 9, 1),
            vendedor_id=IDS['admin'],
            lineas=[{'ingrediente_id': ing.id, 'peso_total': Decimal('50')}])
    c = _login(app, 'admin')
    r = c.get('/maquila')
    assert r.status_code == 200
    assert b'Maquila SA' in r.data


# ---------------------------------------------------------------------------
# Task 12: reportes de auditoría, export y navegación
# ---------------------------------------------------------------------------


def test_el_kardex_responde_y_exporta(app):
    from maquila import servicios
    from maquila.models import Ingrediente
    cli_id, _prod_id, ing_id = _cliente_producto_ingrediente(app)
    with app.app_context():
        servicios.crear_recepcion(
            cliente_id=cli_id, recibido_en=date(2026, 9, 1),
            vendedor_id=IDS['admin'],
            lineas=[{'ingrediente_id': ing_id, 'peso_total': Decimal('50')}])
    c = _login(app, 'admin')
    r = c.get(f'/maquila/reportes/kardex?cliente_id={cli_id}')
    assert r.status_code == 200
    assert b'Carne de res' in r.data

    x = c.get(f'/maquila/reportes/kardex/export?cliente_id={cli_id}')
    assert x.status_code == 200
    assert x.headers['Content-Type'].startswith(
        'application/vnd.openxmlformats')


def test_trazabilidad_sin_resultado_no_revienta(app):
    c = _login(app, 'admin')
    r = c.get('/maquila/reportes/trazabilidad?q=NO-EXISTE')
    assert r.status_code == 200
    assert 'Sin resultados'.encode() in r.data


def test_kardex_incluye_movimientos_de_la_ultima_hora_local_del_dia_hasta(app):
    """`registrado_en` se guarda en UTC naive y DASHBOARD_TIMEZONE es
    America/Curacao (UTC-4): un movimiento de las 22:00 hora local del 3 de
    septiembre queda en la base como 2026-09-04 02:00 UTC. Filtrar
    `hasta=2026-09-03` comparando esa fecha cruda contra el UTC guardado lo
    dejaría afuera aunque la columna lo muestre como del día 3 — la ventana
    tiene que convertirse a UTC antes de filtrar."""
    from datetime import datetime as dt
    from maquila import servicios
    from maquila.models import MovimientoIngrediente
    cli_id, _prod_id, ing_id = _cliente_producto_ingrediente(app)
    with app.app_context():
        servicios.crear_recepcion(
            cliente_id=cli_id, recibido_en=date(2026, 9, 3),
            vendedor_id=IDS['admin'],
            lineas=[{'ingrediente_id': ing_id, 'peso_total': Decimal('50')}])
        mov = MovimientoIngrediente.query.filter_by(cliente_id=cli_id).one()
        mov.registrado_en = dt(2026, 9, 4, 2, 0)  # = 2026-09-03 22:00 local
        _db.session.commit()

    c = _login(app, 'admin')
    r = c.get(f'/maquila/reportes/kardex?cliente_id={cli_id}'
              '&desde=2026-09-03&hasta=2026-09-03')
    assert r.status_code == 200
    assert b'Carne de res' in r.data
    assert b'2026-09-03 22:00' in r.data


def test_trazabilidad_ambigua_muestra_los_candidatos_por_cliente(app):
    """Dos clientes distintos pueden compartir el mismo lote (es único por
    `(cliente_id, lote)`, no globalmente): `trazar` ya no elige uno en
    silencio, así que la plantilla tiene que mostrar ambos, distinguibles
    por cliente."""
    from maquila import servicios
    from app import Cliente, Producto
    with app.app_context():
        cli1 = Cliente(nombre='Cliente Ambar')
        cli2 = Cliente(nombre='Cliente Bravo')
        prod = Producto(nombre='Chorizo', se_pesa=True, tax_rate=10)
        _db.session.add_all([cli1, cli2, prod])
        _db.session.commit()
        servicios.abrir_corrida(
            cliente_id=cli1.id, producto_id=prod.id, lote='L-AMBIGUO',
            fecha_produccion=date(2026, 9, 1), vendedor_id=IDS['admin'])
        servicios.abrir_corrida(
            cliente_id=cli2.id, producto_id=prod.id, lote='L-AMBIGUO',
            fecha_produccion=date(2026, 9, 1), vendedor_id=IDS['admin'])
        _db.session.commit()

    c = _login(app, 'admin')
    r = c.get('/maquila/reportes/trazabilidad?q=L-AMBIGUO')
    assert r.status_code == 200
    assert b'ambigu' in r.data.lower()
    assert b'Cliente Ambar' in r.data
    assert b'Cliente Bravo' in r.data


def test_reporte_saldos_y_rendimiento_responden(app):
    from maquila import servicios
    cli_id, _prod_id, ing_id = _cliente_producto_ingrediente(app)
    with app.app_context():
        servicios.crear_recepcion(
            cliente_id=cli_id, recibido_en=date(2026, 9, 1),
            vendedor_id=IDS['admin'],
            lineas=[{'ingrediente_id': ing_id, 'peso_total': Decimal('50')}])
    c = _login(app, 'admin')
    r = c.get(f'/maquila/reportes/saldos?cliente_id={cli_id}')
    assert r.status_code == 200
    assert b'Carne de res' in r.data

    r = c.get('/maquila/reportes/rendimiento')
    assert r.status_code == 200


def test_vendedor_no_entra_a_los_reportes(app):
    c = _login(app, 'vend')
    for ruta in ('/maquila/reportes/saldos', '/maquila/reportes/kardex',
                 '/maquila/reportes/kardex/export',
                 '/maquila/reportes/rendimiento',
                 '/maquila/reportes/trazabilidad'):
        r = c.get(ruta, follow_redirects=False)
        assert r.status_code == 302, ruta


def test_el_link_a_maquila_se_ve_para_super_admin(app):
    c = _login(app, 'admin')
    r = c.get('/dashboard')
    assert r.status_code == 200
    assert '/maquila"'.encode() in r.data


def test_el_link_a_maquila_no_se_ve_para_vendedor(app):
    """base.html se renderiza para toda la app: el enlace nuevo no puede
    reventar el render para un vendedor sin rol super_admin, y no debe
    verlo."""
    c = _login(app, 'vend')
    r = c.get('/dashboard')
    assert r.status_code == 200
    assert '/maquila"'.encode() not in r.data
