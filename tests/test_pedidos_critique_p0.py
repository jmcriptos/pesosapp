"""Los P0/P1 del critique del listado de pedidos.

1. La moneda no puede ser ambigua: móvil mostraba «450.00 USD» y escritorio
   «450.00» bajo un encabezado fijo «Total (XCG)». ƒ450 y $450 difieren ~78%.
2. Facturar crea una factura real en QuickBooks y no pedía confirmación,
   mientras que eliminar —recuperable— sí la pedía.
3. El estado vacío afirmaba «no hay pedidos» habiendo 26, y su salida real
   estaba a 1.62:1 contra un CTA verde a pantalla completa.

Critique: .impeccable/critique/2026-08-28T08-22-35Z__templates-pedidos-html.md
"""
import os
import re
from datetime import datetime, timedelta
from decimal import Decimal

import pytest

os.environ.setdefault('SECRET_KEY', 'test-secret')
os.environ.setdefault('FLASK_ENV', 'testing')
os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')

from app import app as flask_app, db as _db


@pytest.fixture
def app():
    flask_app.config.update(
        TESTING=True, WTF_CSRF_ENABLED=False,
        SQLALCHEMY_DATABASE_URI='sqlite:///:memory:',
    )
    with flask_app.app_context():
        _db.create_all()
        from app import Rol, Territorio, Vendedor, Cliente, Producto

        rol = Rol(nombre='super_admin', descripcion='Admin')
        _db.session.add(rol)
        territorio = Territorio(nombre='test', descripcion='Test')
        _db.session.add(territorio)
        _db.session.flush()
        vendedor = Vendedor(
            username='admin', email='admin@test.com', nombre_completo='Admin',
            rol_id=rol.id, territorio_id=territorio.id, activo=True,
        )
        vendedor.set_password('testpass')
        _db.session.add(vendedor)
        _db.session.add(Cliente(nombre='Distribuidora Norte', territorio_id=territorio.id,
                                moneda='XCG', qbo_id='C-XCG'))
        _db.session.add(Cliente(nombre='Almacen Sur', territorio_id=territorio.id,
                                moneda='USD', qbo_id='C-USD'))
        _db.session.add(Producto(nombre='Producto', temperatura='4°C', se_pesa=False,
                                 tax_rate=10.0, qbo_id='P1'))
        _db.session.commit()
        yield flask_app
        _db.drop_all()


@pytest.fixture
def logged_client(app):
    client = app.test_client()
    client.post('/login', data={'username': 'admin', 'password': 'testpass'},
                follow_redirects=True)
    return client


def _hoy_local():
    from app import DASHBOARD_TIMEZONE
    return datetime.now(DASHBOARD_TIMEZONE).date()


def _pedido(cliente_nombre, estado='pendiente', total=450.00, dias=1):
    from app import Pedido, Cliente, Producto, DetallePedido
    cliente = Cliente.query.filter_by(nombre=cliente_nombre).first()
    p = Pedido(cliente_id=cliente.id, estado=estado,
               tipo_cambio=1.78 if cliente.moneda == 'USD' else 1.0)
    p.fecha_entrega = _hoy_local() + timedelta(days=dias)
    _db.session.add(p)
    _db.session.flush()
    _db.session.add(DetallePedido(
        pedido_id=p.id, producto_id=Producto.query.first().id,
        cajas=1, cajas_pedidas=1, peso=0,
        precio_unitario=Decimal(str(total)), subtotal=Decimal(str(total)),
        es_linea_pedido=True,
    ))
    _db.session.commit()
    return p


def _fila_escritorio(html, pedido_id):
    """El <tr> de ese pedido en la tabla de escritorio."""
    for tr in re.findall(r'<tr[^>]*>.*?</tr>', html, re.S):
        if f'PED-{pedido_id}<' in tr or f'>PED-{pedido_id}' in tr:
            return tr
    return ''


# === P0-1: la moneda no puede ser ambigua ===

def test_el_encabezado_no_afirma_una_moneda_fija(app, logged_client):
    """«Total (XCG)» mentía sobre las filas de clientes en USD."""
    with app.app_context():
        _pedido('Almacen Sur')

        # `/pedidos` sin parámetros es el TABLERO desde el 2026-08-28; el
        # encabezado que este test verifica vive en `?estado=todos`.
        html = logged_client.get('/pedidos?estado=todos').get_data(as_text=True)

        assert 'Total (XCG)' not in html


def test_la_fila_de_escritorio_dice_su_moneda(app, logged_client):
    """Escritorio mostraba el número pelado; móvil sí decía USD."""
    with app.app_context():
        usd = _pedido('Almacen Sur', total=450.00)
        xcg = _pedido('Distribuidora Norte', total=450.00)

        # `/pedidos` sin parámetros es el TABLERO desde el 2026-08-28; el
        # markup de fila que este archivo verifica vive en `?estado=todos`.
        html = logged_client.get('/pedidos?estado=todos').get_data(as_text=True)

        assert 'USD' in _fila_escritorio(html, usd.id)
        assert 'XCG' in _fila_escritorio(html, xcg.id)


def test_el_orden_por_total_compara_en_la_misma_moneda(app, logged_client):
    """`data-total` alimenta el sort de la tabla: si lleva el número nativo,
    un pedido de $450 ordena debajo de uno de ƒ487 valiendo casi el doble."""
    with app.app_context():
        usd = _pedido('Almacen Sur', total=450.00)   # 450 * 1.78 = 801 XCG
        xcg = _pedido('Distribuidora Norte', total=487.00)

        html = logged_client.get('/pedidos?estado=todos').get_data(as_text=True)

        def total_dato(pid):
            m = re.search(r'data-total="([0-9.]+)"', _fila_escritorio(html, pid))
            assert m, f'sin data-total en PED-{pid}'
            return float(m.group(1))

        assert total_dato(usd.id) > total_dato(xcg.id), (
            'el pedido en USD vale más en XCG y debe ordenar por encima'
        )
        assert total_dato(usd.id) == pytest.approx(801.0, abs=0.5)


# === P0-2: facturar es irreversible y debe avisarlo ===

def test_facturar_pide_confirmacion(app, logged_client):
    """Crea una factura real en QuickBooks; eliminar —recuperable— ya confirmaba."""
    with app.app_context():
        _pedido('Almacen Sur', estado='preparado')

        html = logged_client.get('/pedidos?estado=todos').get_data(as_text=True)

        formularios = re.findall(r'<form[^>]*facturar[^>]*>.*?</form>', html, re.S)
        assert formularios, 'no encontré el formulario de facturar'
        for form in formularios:
            assert 'data-confirm' in form, 'facturar debe confirmar antes de emitir'


def test_la_confirmacion_dice_que_no_se_puede_deshacer(app, logged_client):
    """El aviso tiene que nombrar la consecuencia, no solo preguntar «¿seguro?»."""
    with app.app_context():
        _pedido('Almacen Sur', estado='preparado', total=450.00)

        html = logged_client.get('/pedidos?estado=todos').get_data(as_text=True)
        form = re.search(r'<form[^>]*facturar[^>]*>.*?</form>', html, re.S).group(0)
        mensaje = re.search(r'data-confirm="([^"]*)"', form).group(1)

        assert 'QuickBooks' in mensaje
        assert 'deshacer' in mensaje.lower()
        assert 'Almacen Sur' in mensaje, 'debe nombrar al cliente'
        assert '450' in mensaje and 'USD' in mensaje, 'debe decir el importe con su moneda'


# === P1-3: el estado vacío no puede mentir ===

def test_sin_resultados_no_dice_que_no_hay_pedidos(app, logged_client):
    """Con pedidos cargados pero filtrados, «Crear primer pedido» es falso."""
    with app.app_context():
        _pedido('Distribuidora Norte')

        html = logged_client.get('/pedidos?q=zzzznoexiste').get_data(as_text=True)

        assert 'Crear primer pedido' not in html
        assert 'zzzznoexiste' in html, 'debe repetir el término buscado'


def test_sin_resultados_la_salida_es_la_accion_principal(app, logged_client):
    """«Limpiar filtros» era un enlace a 1.62:1 bajo un CTA verde gigante."""
    with app.app_context():
        _pedido('Distribuidora Norte')

        html = logged_client.get('/pedidos?q=zzzznoexiste').get_data(as_text=True)

        assert re.search(r'class="[^"]*btn-limpiar-filtros', html), (
            'limpiar filtros debe ser el botón primario, no un enlace tenue'
        )


def test_sin_ningun_pedido_si_ofrece_crear_el_primero(app, logged_client):
    """El caso de cero datos real conserva su CTA."""
    with app.app_context():
        html = logged_client.get('/pedidos?estado=todos').get_data(as_text=True)

        assert 'Crear primer pedido' in html


def test_el_equivalente_ignora_un_tipo_de_cambio_corrupto(app, logged_client):
    """XCG es la moneda base: vale 1 por definición, diga lo que diga la columna.

    Producción tiene 381 pedidos en XCG estampados con `tipo_cambio` 1.78 (el
    expediente que se decidió no remediar). Normalizar con el rate guardado los
    inflaría un 78% y los mandaría al tope de un orden por monto.
    """
    from app import Pedido

    with app.app_context():
        pedido = _pedido('Distribuidora Norte', total=100.00)
        Pedido.query.filter_by(id=pedido.id).update({'tipo_cambio': 1.78})
        _db.session.commit()

        html = logged_client.get('/pedidos?estado=todos').get_data(as_text=True)
        m = re.search(r'data-total="([0-9.]+)"', _fila_escritorio(html, pedido.id))

        assert m, 'sin data-total'
        assert float(m.group(1)) == pytest.approx(100.0, abs=0.5), (
            'un pedido en XCG no se convierte, aunque la fila diga 1.78'
        )
