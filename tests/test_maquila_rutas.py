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
