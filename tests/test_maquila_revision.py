"""Revisión del módulo de maquila (2026-09-04): fallos que daban 500 o
elegían en silencio, y las consultas en lote que reemplazan a los N+1."""
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
    flask_app.config.update(TESTING=True, WTF_CSRF_ENABLED=False,
                            SQLALCHEMY_DATABASE_URI='sqlite:///:memory:')
    with flask_app.app_context():
        _db.create_all()
        from app import Rol, Territorio, Vendedor, Cliente, Producto
        from maquila.models import Ingrediente
        ra = Rol(nombre='super_admin', descripcion='Admin')
        terr = Territorio(nombre='t1', descripcion='T1')
        _db.session.add_all([ra, terr])
        _db.session.flush()
        v = Vendedor(username='admin', email='a@t.com', nombre_completo='Admin',
                     rol_id=ra.id, territorio_id=terr.id, activo=True)
        v.set_password('pw')
        cli = Cliente(nombre='Maquila SA')
        prod = Producto(nombre='Chorizo', se_pesa=True, tax_rate=10)
        ing = Ingrediente(nombre='Carne de res')
        tripa = Ingrediente(nombre='Tripa', unidad='ud')
        _db.session.add_all([v, cli, prod, ing, tripa])
        _db.session.commit()
        IDS.update(vendedor=v.id, cliente=cli.id, producto=prod.id,
                   ingrediente=ing.id, tripa=tripa.id)
        yield flask_app
        _db.drop_all()


def _login(app):
    c = app.test_client()
    c.post('/login', data={'username': 'admin', 'password': 'pw'},
           follow_redirects=True)
    return c


def _recibir(peso, ingrediente_id=None, dia=1):
    from maquila import servicios
    return servicios.crear_recepcion(
        cliente_id=IDS['cliente'], recibido_en=date(2026, 9, dia),
        vendedor_id=IDS['vendedor'],
        lineas=[{'ingrediente_id': ingrediente_id or IDS['ingrediente'],
                 'peso_total': Decimal(str(peso))}])


# --- Validaciones que antes reventaban con 500 -----------------------------

def test_crear_recepcion_sin_fecha_avisa_en_vez_de_reventar(app):
    """`recibido_en=None` llegaba hasta `siguiente_codigo(...year)` y daba
    AttributeError: la ruta lo tapaba con «error inesperado»."""
    from maquila import servicios
    with app.app_context():
        with pytest.raises(servicios.RecepcionInvalida):
            servicios.crear_recepcion(
                cliente_id=IDS['cliente'], recibido_en=None,
                vendedor_id=IDS['vendedor'],
                lineas=[{'ingrediente_id': IDS['ingrediente'],
                         'peso_total': Decimal('10')}])


def test_crear_recepcion_con_linea_sin_ingrediente_avisa(app):
    from maquila import servicios
    with app.app_context():
        with pytest.raises(servicios.RecepcionInvalida):
            servicios.crear_recepcion(
                cliente_id=IDS['cliente'], recibido_en=date(2026, 9, 1),
                vendedor_id=IDS['vendedor'],
                lineas=[{'ingrediente_id': None, 'peso_total': Decimal('10')}])


def test_ruta_recepcion_nueva_con_cliente_basura_no_revienta(app):
    """`int(request.form['cliente_id'])` era el único parseo sin red del
    módulo: basura ahí daba 500, no un mensaje."""
    from maquila.models import RecepcionIngrediente
    c = _login(app)
    r = c.post('/maquila/recepciones/nueva', data={
        'cliente_id': 'no-es-un-numero',
        'recibido_en': '2026-09-03',
        'linea_ingrediente_id': [str(IDS['ingrediente'])],
        'linea_peso_total': ['24'],
    }, follow_redirects=True)
    assert r.status_code == 200
    with app.app_context():
        assert RecepcionIngrediente.query.count() == 0


def test_ruta_recepcion_nueva_sin_fecha_no_revienta(app):
    from maquila.models import RecepcionIngrediente
    c = _login(app)
    r = c.post('/maquila/recepciones/nueva', data={
        'cliente_id': str(IDS['cliente']),
        'recibido_en': '',
        'linea_ingrediente_id': [str(IDS['ingrediente'])],
        'linea_peso_total': ['24'],
    }, follow_redirects=True)
    assert r.status_code == 200
    assert 'necesita una fecha' in r.data.decode()
    with app.app_context():
        assert RecepcionIngrediente.query.count() == 0


def test_abrir_corrida_sin_fecha_avisa_en_vez_de_reventar(app):
    from maquila import servicios
    with app.app_context():
        with pytest.raises(servicios.CorridaInvalida):
            servicios.abrir_corrida(
                cliente_id=IDS['cliente'], producto_id=IDS['producto'],
                lote='L-1', fecha_produccion=None, vendedor_id=IDS['vendedor'])


def test_ruta_corrida_nueva_sin_fecha_no_revienta(app):
    """Antes: `fecha_produccion.year` sobre None → AttributeError → 500,
    porque la ruta solo atrapaba CorridaInvalida."""
    from maquila.models import CorridaProduccion
    c = _login(app)
    r = c.post('/maquila/corridas/nueva', data={
        'cliente_id': str(IDS['cliente']), 'producto_id': str(IDS['producto']),
        'lote': 'L-SIN-FECHA', 'fecha_produccion': ''}, follow_redirects=True)
    assert r.status_code == 200
    assert 'necesita una fecha' in r.data.decode()
    with app.app_context():
        assert CorridaProduccion.query.count() == 0


# --- Recetas -----------------------------------------------------------------

def test_receta_con_ingrediente_repetido_se_rechaza_sin_500(app):
    """Dos filas del form con el mismo ingrediente chocaban contra
    `uq_receta_ingrediente` y daban IntegrityError → 500."""
    from maquila.models import Receta
    c = _login(app)
    r = c.post('/maquila/recetas/nueva', data={
        'nombre': 'Chorizo', 'producto_id': str(IDS['producto']),
        'cliente_id': '', 'base_kg': '100', 'activa': '1',
        'item_ingrediente_id': [str(IDS['ingrediente']), str(IDS['ingrediente'])],
        'item_cantidad': ['80', '20'],
    }, follow_redirects=True)
    assert r.status_code == 200
    assert b'repetido' in r.data
    with app.app_context():
        assert Receta.query.count() == 0


def test_receta_con_producto_inexistente_se_rechaza_sin_500(app):
    from maquila.models import Receta
    c = _login(app)
    r = c.post('/maquila/recetas/nueva', data={
        'nombre': 'Chorizo', 'producto_id': '999999',
        'cliente_id': '', 'base_kg': '100', 'activa': '1',
        'item_ingrediente_id': [str(IDS['ingrediente'])],
        'item_cantidad': ['80'],
    }, follow_redirects=True)
    assert r.status_code == 200
    with app.app_context():
        assert Receta.query.count() == 0


# --- Trazabilidad: DocNumber duplicado ---------------------------------------

def test_trazar_docnumber_repetido_en_dos_pedidos_es_ambiguo(app):
    """La numeración manual en n8n admite la carrera (decisión de JM): dos
    pedidos pueden compartir DocNumber. `trazar` no puede quedarse con el
    primero en silencio."""
    from app import Pedido
    from maquila import reportes
    with app.app_context():
        p1 = Pedido(cliente_id=IDS['cliente'], estado='facturado',
                    doc_number_qbo='4321')
        p2 = Pedido(cliente_id=IDS['cliente'], estado='facturado',
                    doc_number_qbo='4321')
        _db.session.add_all([p1, p2])
        _db.session.commit()
        resultado = reportes.trazar('4321')
        assert resultado['encontrado'] is True
        assert resultado['ambiguo'] is True
        assert {f['pedido_id'] for f in resultado['hacia_adelante']} == {p1.id, p2.id}


# --- Saldos en lote ------------------------------------------------------------

def test_saldos_por_linea_coincide_con_saldo_de_linea(app):
    from maquila import servicios
    with app.app_context():
        r1 = _recibir(100, dia=1)
        r2 = _recibir(50, dia=2)
        l1, l2 = r1.lineas[0], r2.lineas[0]
        servicios.registrar_movimiento(
            cliente_id=IDS['cliente'], ingrediente_id=IDS['ingrediente'],
            tipo='salida', cantidad=Decimal('30'), origen_tipo='corrida',
            origen_id=1, vendedor_id=IDS['vendedor'], recepcion_linea_id=l1.id)
        _db.session.commit()

        lote = servicios.saldos_por_linea([l1.id, l2.id, 999999])
        assert lote[l1.id] == servicios.saldo_de_linea(l1.id) == Decimal('70')
        assert lote[l2.id] == servicios.saldo_de_linea(l2.id) == Decimal('50')
        assert lote[999999] == Decimal('0')
        assert servicios.saldos_por_linea([]) == {}


def test_saldos_de_cliente_en_una_consulta_mantiene_el_desglose(app):
    """recibido = solo entradas; consumido = |salidas|; ajustes = ajuste +
    devolución; y cada ingrediente sale con su unidad."""
    from maquila import servicios
    with app.app_context():
        _recibir(100)
        _recibir(20, ingrediente_id=IDS['tripa'])
        servicios.registrar_movimiento(
            cliente_id=IDS['cliente'], ingrediente_id=IDS['ingrediente'],
            tipo='salida', cantidad=Decimal('40'), origen_tipo='corrida',
            origen_id=1, vendedor_id=IDS['vendedor'])
        servicios.registrar_movimiento(
            cliente_id=IDS['cliente'], ingrediente_id=IDS['ingrediente'],
            tipo='ajuste', cantidad=Decimal('-5'), origen_tipo='manual',
            vendedor_id=IDS['vendedor'], motivo='merma en cámara')
        servicios.registrar_movimiento(
            cliente_id=IDS['cliente'], ingrediente_id=IDS['ingrediente'],
            tipo='devolucion', cantidad=Decimal('2'), origen_tipo='manual',
            vendedor_id=IDS['vendedor'], motivo='volvió un bulto')
        _db.session.commit()

        filas = {f['ingrediente']: f for f in servicios.saldos_de_cliente(IDS['cliente'])}
        carne = filas['Carne de res']
        assert carne['recibido'] == Decimal('100')
        assert carne['consumido'] == Decimal('40')
        assert carne['ajustes'] == Decimal('-3')
        assert carne['saldo'] == Decimal('57')
        assert carne['unidad'] == 'kg'
        tripa = filas['Tripa']
        assert tripa['recibido'] == tripa['saldo'] == Decimal('20')
        assert tripa['consumido'] == Decimal('0')
        assert tripa['ajustes'] == Decimal('0')
        assert tripa['unidad'] == 'ud'


def test_lineas_con_saldo_ignora_las_lineas_quitadas(app):
    from maquila import servicios
    with app.app_context():
        rec = _recibir(100)
        linea = rec.lineas[0]
        servicios.editar_recepcion(
            rec, vendedor_id=IDS['vendedor'], cabecera={},
            lineas=[{'id': linea.id, 'quitar': True}],
            motivo='llegó otra cosa')
        assert servicios.lineas_con_saldo(IDS['cliente'], IDS['ingrediente']) == []


def test_el_indice_con_varios_clientes_muestra_conteos_correctos(app):
    """Después de agrupar en una sola consulta, cada tarjeta sigue mostrando
    SUS corridas abiertas y SU última recepción, no las del vecino."""
    from app import Cliente
    from maquila import servicios
    with app.app_context():
        otro = Cliente(nombre='Otro SA')
        _db.session.add(otro)
        _db.session.commit()
        _recibir(100, dia=1)
        _recibir(30, dia=5)
        servicios.crear_recepcion(
            cliente_id=otro.id, recibido_en=date(2026, 9, 3),
            vendedor_id=IDS['vendedor'],
            lineas=[{'ingrediente_id': IDS['ingrediente'], 'peso_total': Decimal('7')}])
        servicios.abrir_corrida(
            cliente_id=IDS['cliente'], producto_id=IDS['producto'], lote='A',
            fecha_produccion=date(2026, 9, 4), vendedor_id=IDS['vendedor'])
        servicios.abrir_corrida(
            cliente_id=IDS['cliente'], producto_id=IDS['producto'], lote='B',
            fecha_produccion=date(2026, 9, 4), vendedor_id=IDS['vendedor'])

    c = _login(app)
    r = c.get('/maquila')
    assert r.status_code == 200
    html = r.data.decode()
    assert '2 corridas abiertas' in html
    assert '0 corridas abiertas' in html
    assert 'R-2026-0002 (05/09/2026)' in html
    assert 'R-2026-0003 (03/09/2026)' in html


def test_recepcion_rechazada_devuelve_el_formulario_con_lo_tecleado(app):
    """Un rechazo del servidor no puede borrar cuatro líneas tecleadas con
    guantes: se re-pinta el formulario con lo enviado (no un redirect al
    alta vacía). Fotos y firma no se pueden reponer; el flash lo dice."""
    from maquila.models import RecepcionIngrediente
    c = _login(app)
    r = c.post('/maquila/recepciones/nueva', data={
        'cliente_id': str(IDS['cliente']),
        'recibido_en': '2026-09-03',
        'documento_cliente': 'GUIA-ROJA-77',
        'transportista': 'Camión de Toño',
        'linea_ingrediente_id': [str(IDS['ingrediente']), str(IDS['tripa'])],
        'linea_lote_cliente': ['BR-2291', ''],
        'linea_cantidad_bultos': ['3', ''],
        'linea_peso_total': ['24', ''],   # la segunda línea sin peso → rechazo
    })
    assert r.status_code == 200          # re-render, no 302
    html = r.data.decode()
    assert 'GUIA-ROJA-77' in html
    assert 'Camión de Toño' in html
    assert 'BR-2291' in html
    assert 'value="24"' in html
    assert 'Lo tecleado se conserva' in html
    with app.app_context():
        assert RecepcionIngrediente.query.count() == 0


def test_saldos_de_cliente_separa_correcciones_de_ajustes_manuales(app):
    """Una corrección de recepción es tipo 'ajuste' con origen 'recepcion';
    para quien lee el saldo no es un ajuste de inventario."""
    from maquila import servicios
    with app.app_context():
        rec = _recibir(100)
        servicios.registrar_movimiento(
            cliente_id=IDS['cliente'], ingrediente_id=IDS['ingrediente'],
            tipo='ajuste', cantidad=Decimal('2'), origen_tipo='recepcion',
            origen_id=rec.id, vendedor_id=IDS['vendedor'], motivo='se repesó')
        servicios.registrar_movimiento(
            cliente_id=IDS['cliente'], ingrediente_id=IDS['ingrediente'],
            tipo='ajuste', cantidad=Decimal('-5'), origen_tipo='manual',
            vendedor_id=IDS['vendedor'], motivo='merma en cámara')
        _db.session.commit()
        fila = servicios.saldos_de_cliente(IDS['cliente'])[0]
        assert fila['correcciones'] == Decimal('2')
        assert fila['ajustes'] == Decimal('-5')
        assert fila['saldo'] == Decimal('97')
