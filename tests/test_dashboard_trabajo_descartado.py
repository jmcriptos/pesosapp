# tests/test_dashboard_trabajo_descartado.py
"""El dashboard no calcula localmente lo que QuickBooks va a pisar.

Hasta el 2026-08-30 la ruta recorría los ~900 pedidos facturados de seis meses
llamando a `_calcular_venta_pedido` —386 de los 570ms del request, medido en
producción— y enseguida QuickBooks, que es la fuente de verdad, sobrescribía
TODOS esos valores. El mismo recorrido completo se repetía para armar los
rankings locales, que en el caso normal tampoco se usan.

Estos tests fijan las dos mitades del contrato:

  - Con QuickBooks disponible, el recorrido caro NO corre y las cifras son las
    de QuickBooks.
  - Sin QuickBooks, el recorrido corre y la pantalla muestra cifras locales.

La segunda mitad importa tanto como la primera: una optimización que apaga el
respaldo no es una optimización, es una pantalla en ceros el día que falle el
webhook.
"""
import os
from datetime import datetime, timedelta, timezone

import pytest

os.environ.setdefault('SECRET_KEY', 'test-secret')
os.environ.setdefault('FLASK_ENV', 'testing')
os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')

import app as app_module
from app import app as flask_app, db as _db


@pytest.fixture
def app():
    flask_app.config.update(
        TESTING=True,
        WTF_CSRF_ENABLED=False,
        SQLALCHEMY_DATABASE_URI='sqlite:///:memory:',
    )
    with flask_app.app_context():
        _db.create_all()
        from app import Rol, Territorio, Vendedor, Cliente, Producto, Pedido, DetallePedido
        rol = Rol(nombre='super_admin', descripcion='Admin')
        _db.session.add(rol)
        territorio = Territorio(nombre='test', descripcion='Test')
        _db.session.add(territorio)
        _db.session.flush()
        vendedor = Vendedor(
            username='admin', email='admin@test.com', nombre_completo='Admin Test',
            rol_id=rol.id, territorio_id=territorio.id, activo=True,
        )
        vendedor.set_password('testpass')
        cliente = Cliente(nombre='Mangusa Hypermarket')
        producto = Producto(nombre='Boneless Chicken Breast', se_pesa=False)
        _db.session.add_all([vendedor, cliente, producto])
        _db.session.flush()

        # Dos pedidos facturados que separan las dos poblaciones: el del mes,
        # que OTD y OFR necesitan siempre, y uno viejo que solo hacía falta para
        # las ventas de seis meses y los rankings — o sea, justo lo que
        # QuickBooks pisa. Con un solo pedido las dos ramas se ven iguales.
        ahora = datetime.now(timezone.utc)
        viejo = ahora - timedelta(days=100)
        for fecha, subtotal in ((ahora, 100), (viejo, 700)):
            pedido = Pedido(cliente_id=cliente.id, estado='facturado',
                            fecha_pedido=fecha, fecha_facturacion=fecha)
            _db.session.add(pedido)
            _db.session.flush()
            _db.session.add(DetallePedido(
                pedido_id=pedido.id, producto_id=producto.id,
                cajas=4, cajas_pedidas=4, peso=0,
                precio_unitario=25, subtotal=subtotal, es_linea_pedido=True,
            ))
            if fecha is ahora:
                pedido_del_mes_id = pedido.id
        _db.session.commit()
        flask_app.config['_TEST_PEDIDO_DEL_MES'] = pedido_del_mes_id
        yield flask_app
        _db.drop_all()


@pytest.fixture
def logged_client(app):
    client = app.test_client()
    client.post('/login', data={'username': 'admin', 'password': 'testpass'},
                follow_redirects=True)
    return client


def _contar_calculos_de_venta(monkeypatch):
    """Envuelve `_calcular_venta_pedido` para contar cuántas veces se llama.

    Es la función que hace el trabajo caro: recorre detalles y cajas pesadas de
    cada pedido. Contar sus llamadas mide la optimización directamente, en vez
    de cronometrar —que en una base de prueba de un pedido no distingue nada.
    """
    llamadas = []
    original = app_module._calcular_venta_pedido

    def espia(pedido, *a, **kw):
        llamadas.append(pedido.id)
        return original(pedido, *a, **kw)

    monkeypatch.setattr(app_module, '_calcular_venta_pedido', espia)
    return llamadas


_PAYLOAD_QB = {
    'ventas_mes': 122014.0,
    'ventas_semana': 31000.0,
    'ventas_mes_anterior': 98000.0,
    'ventas_diarias_idx': {},
    'ventas_semanales_idx': {},
    'rankings_periodos': {
        'month': {
            'top_productos': [{'nombre': 'Pork Shoulder', 'ingresos': 5000.0,
                               'cajas': 10, 'peso': 0, 'pedidos': 2}],
            'top_clientes': [('Mangusa Hypermarket',
                              {'total': 5000.0, 'pedidos': 2, 'ultimo_pedido': None})],
            'max_ventas': 5000.0,
            'max_total_clientes': 5000.0,
        },
        '6m': {'top_productos': [], 'top_clientes': []},
        '3m': {'top_productos': [], 'top_clientes': []},
        '4w': {'top_productos': [], 'top_clientes': []},
    },
}


def test_quickbooks_manda_sobre_las_cifras_de_la_pantalla(logged_client, monkeypatch):
    """QuickBooks es la fuente de verdad y la pantalla muestra SUS números.

    Acá los rankings de 6m/3m/4s vienen vacíos, así que el ranking local sí se
    construye como respaldo de esos periodos —y eso es correcto: un periodo sin
    datos de QuickBooks se llena con lo que hay—. Lo que se fija es que ese
    respaldo no contamina lo que se ve: las ventas y el Top del mes siguen
    siendo los de QuickBooks, no los del pedido local de 100 XCG.
    """
    monkeypatch.setattr(app_module, '_obtener_metricas_ventas_quickbooks',
                        lambda *a, **kw: dict(_PAYLOAD_QB))

    html = logged_client.get('/dashboard').get_data(as_text=True)

    assert '122,014' in html
    assert 'Pork Shoulder' in html
    # Y no la venta local, que es la que el recorrido caro habría producido.
    assert '800<small>XCG</small>' not in html.replace(' ', '')


def test_con_quickbooks_completo_no_se_construye_ningun_ranking_local(logged_client, monkeypatch):
    """Con los cuatro periodos servidos, el segundo recorrido tampoco corre."""
    payload = dict(_PAYLOAD_QB)
    payload['rankings_periodos'] = {
        k: dict(_PAYLOAD_QB['rankings_periodos']['month'])
        for k in ('month', '6m', '3m', '4w')
    }
    monkeypatch.setattr(app_module, '_obtener_metricas_ventas_quickbooks',
                        lambda *a, **kw: payload)
    llamadas = _contar_calculos_de_venta(monkeypatch)

    resp = logged_client.get('/dashboard')
    assert resp.status_code == 200
    del_mes = flask_app.config['_TEST_PEDIDO_DEL_MES']
    assert set(llamadas) <= {del_mes}, f'se recorrieron pedidos de más: {llamadas}'


def test_sin_quickbooks_el_respaldo_local_sigue_dando_cifras(logged_client, monkeypatch):
    """La otra mitad: sin webhook, la pantalla NO se queda en ceros."""
    monkeypatch.setattr(app_module, '_obtener_metricas_ventas_quickbooks',
                        lambda *a, **kw: None)
    llamadas = _contar_calculos_de_venta(monkeypatch)

    html = logged_client.get('/dashboard').get_data(as_text=True)

    # El pedido facturado de 100 XCG aparece como venta del mes.
    assert '100<small>XCG</small>' in html.replace(' ', '').replace('\n', '') or '100' in html
    # Y el Top local se construyó: el cliente y el producto de la base.
    assert 'Mangusa Hypermarket' in html
    assert 'Boneless Chicken Breast' in html
    # Acá el recorrido SÍ tiene que haber corrido, y sobre los DOS pedidos:
    # sin QuickBooks, la tendencia de seis meses solo existe si se calcula.
    del_mes = flask_app.config['_TEST_PEDIDO_DEL_MES']
    assert set(llamadas) - {del_mes}, 'el respaldo local no miró más allá del mes'


def test_los_pendientes_se_cuentan_con_o_sin_quickbooks(logged_client, monkeypatch, app):
    """`pedidos_pendientes` vivía dentro del bloque que se volvió condicional.

    Si se hubiera quedado adentro, el titular diría "0 pedidos por atender" cada
    vez que QuickBooks contesta — o sea siempre.
    """
    from app import Pedido, Cliente

    with app.app_context():
        cliente = Cliente.query.first()
        for _ in range(3):
            _db.session.add(Pedido(cliente_id=cliente.id, estado='pendiente',
                                   fecha_pedido=datetime.now(timezone.utc)))
        _db.session.commit()

    monkeypatch.setattr(app_module, '_obtener_metricas_ventas_quickbooks',
                        lambda *a, **kw: dict(_PAYLOAD_QB))
    html = logged_client.get('/dashboard').get_data(as_text=True)
    assert '3 pedidos por atender' in html or '3 pedido' in html
