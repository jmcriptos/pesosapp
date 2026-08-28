# tests/test_pedido_habitual.py
"""Tests del "pedido habitual" que precarga /pedidos/nuevo.

La pantalla "Repetir y ajustar" trae el pedido ya escrito con lo que el cliente
suele comprar. Lo que se prueba acá es la receta: qué líneas entran, con qué
cantidad, y que las líneas de preparación no dupliquen las cantidades.
"""
import os
import pytest
from datetime import datetime, timedelta

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
            username='admin', email='admin@test.com',
            nombre_completo='Admin Test',
            rol_id=rol.id, territorio_id=territorio.id, activo=True,
        )
        vendedor.set_password('testpass')
        _db.session.add(vendedor)

        _db.session.add(Cliente(nombre='Van den Tweel', territorio_id=territorio.id))
        _db.session.add(Cliente(nombre='Cliente Nuevo', territorio_id=territorio.id))

        # Los dos grupos de facturación de producción son los dos impuestos.
        # `se_pesa` no los parte: un pesable y un importado con el mismo
        # impuesto van en el mismo pedido.
        for nombre, se_pesa, tax in [
            ('Chuleta de cerdo ahumada 5 kg', True, 10.0),   # imp:10, pesable
            ('Salchicha Frankfurter 2.5 kg', True, 10.0),    # imp:10, pesable
            ('Ham di Pasku 4 kg', True, 14.0),               # imp:14, pesable
            ('Aceite vegetal 12 x 1 L', False, 10.0),        # imp:10, importado
        ]:
            _db.session.add(Producto(
                nombre=nombre, descripcion='x', temperatura='Congelado',
                se_pesa=se_pesa, tax_rate=tax,
            ))
        _db.session.commit()

        yield flask_app
        _db.drop_all()


@pytest.fixture
def logged_client(app):
    client = app.test_client()
    client.post('/login', data={
        'username': 'admin', 'password': 'testpass',
    }, follow_redirects=True)
    return client


def _ids():
    from app import Cliente, Producto
    cliente = Cliente.query.filter_by(nombre='Van den Tweel').first()
    productos = {p.nombre: p.id for p in Producto.query.all()}
    return cliente.id, productos


def _crear_pedido(cliente_id, lineas, dias_atras=0, con_prep=False):
    """Crea un pedido con sus líneas originales.

    `lineas` es [(producto_id, cajas)]. Con `con_prep` agrega además la línea
    de preparación que la app genera para productos de importación.
    """
    from app import Pedido, DetallePedido

    pedido = Pedido(
        cliente_id=cliente_id,
        fecha_pedido=datetime.utcnow() - timedelta(days=dias_atras),
    )
    _db.session.add(pedido)
    _db.session.flush()

    for producto_id, cajas in lineas:
        _db.session.add(DetallePedido(
            pedido_id=pedido.id, producto_id=producto_id,
            cajas=cajas, cajas_pedidas=cajas,
            precio_unitario=10, subtotal=10 * cajas,
            es_linea_pedido=True,
        ))
        if con_prep:
            _db.session.add(DetallePedido(
                pedido_id=pedido.id, producto_id=producto_id,
                cajas=cajas, cajas_pedidas=0,
                precio_unitario=10, subtotal=10 * cajas,
                es_linea_pedido=False,
            ))

    _db.session.commit()
    return pedido


def test_cliente_sin_historial_no_devuelve_lineas(app, logged_client):
    from app import Cliente

    nuevo = Cliente.query.filter_by(nombre='Cliente Nuevo').first()
    resp = logged_client.get(f'/api/clientes/{nuevo.id}/pedido-habitual')

    assert resp.status_code == 200
    datos = resp.get_json()
    assert datos['lineas'] == []
    assert datos['visitas'] == 0
    assert datos['ultima_fecha'] is None


def test_una_sola_visita_se_precarga_tal_cual(app, logged_client):
    """Con un solo pedido no hay nada que promediar: se repite esa visita."""
    cliente_id, prods = _ids()
    chuleta = prods['Chuleta de cerdo ahumada 5 kg']
    _crear_pedido(cliente_id, [(chuleta, 7)], dias_atras=3)

    datos = logged_client.get(f'/api/clientes/{cliente_id}/pedido-habitual').get_json()

    assert datos['visitas'] == 1
    assert len(datos['lineas']) == 1
    assert datos['lineas'][0]['id'] == chuleta
    assert datos['lineas'][0]['cajas'] == 7
    assert datos['lineas'][0]['cajas_habitual'] == 7


def test_producto_de_una_sola_visita_queda_fuera(app, logged_client):
    """Una compra puntual no debe volverse parte del pedido base.

    Con 3 visitas, la chuleta aparece en las 3 y la salchicha en una sola: la
    salchicha fue un antojo, no un hábito.

    Los dos productos son del MISMO grupo (pesable:10) a propósito: un pedido
    no puede mezclar grupos, así que la compra puntual tiene que entrar por un
    producto que sí podía viajar en ese mismo pedido.
    """
    cliente_id, prods = _ids()
    chuleta = prods['Chuleta de cerdo ahumada 5 kg']
    salchicha = prods['Salchicha Frankfurter 2.5 kg']

    _crear_pedido(cliente_id, [(chuleta, 8)], dias_atras=21)
    _crear_pedido(cliente_id, [(chuleta, 8)], dias_atras=14)
    _crear_pedido(cliente_id, [(chuleta, 8), (salchicha, 2)], dias_atras=7)

    datos = logged_client.get(f'/api/clientes/{cliente_id}/pedido-habitual').get_json()

    ids = [l['id'] for l in datos['lineas']]
    assert chuleta in ids
    assert salchicha not in ids


def test_cantidad_es_la_mediana_no_el_promedio(app, logged_client):
    """Un pedido atípico no debe arrastrar la cantidad propuesta.

    Cantidades 5, 5, 5 y 40: el promedio da 14 (una cantidad que el cliente
    nunca pidió), la mediana da 5, que es lo que realmente compra.
    """
    cliente_id, prods = _ids()
    chuleta = prods['Chuleta de cerdo ahumada 5 kg']

    for dias, cajas in [(28, 5), (21, 5), (14, 5), (7, 40)]:
        _crear_pedido(cliente_id, [(chuleta, cajas)], dias_atras=dias)

    datos = logged_client.get(f'/api/clientes/{cliente_id}/pedido-habitual').get_json()

    linea = next(l for l in datos['lineas'] if l['id'] == chuleta)
    assert linea['cajas'] == 5, 'la mediana debe resistir el pedido atípico'


def test_solo_mira_las_ultimas_cuatro_visitas(app, logged_client):
    """Un producto que dejó de comprarse hace meses no debe reaparecer."""
    cliente_id, prods = _ids()
    chuleta = prods['Chuleta de cerdo ahumada 5 kg']
    salchicha = prods['Salchicha Frankfurter 2.5 kg']

    # Dos visitas viejas con salchicha, cuatro recientes sin ella.
    _crear_pedido(cliente_id, [(chuleta, 8), (salchicha, 6)], dias_atras=60)
    _crear_pedido(cliente_id, [(chuleta, 8), (salchicha, 6)], dias_atras=53)
    for dias in (28, 21, 14, 7):
        _crear_pedido(cliente_id, [(chuleta, 8)], dias_atras=dias)

    datos = logged_client.get(f'/api/clientes/{cliente_id}/pedido-habitual').get_json()

    assert datos['visitas'] == 4
    ids = [l['id'] for l in datos['lineas']]
    assert salchicha not in ids


def test_lineas_de_preparacion_no_duplican_la_cantidad(app, logged_client):
    """`es_linea_pedido=False` repite el producto: contarla daría el doble."""
    cliente_id, prods = _ids()
    aceite = prods['Aceite vegetal 12 x 1 L']

    _crear_pedido(cliente_id, [(aceite, 4)], dias_atras=14, con_prep=True)
    _crear_pedido(cliente_id, [(aceite, 4)], dias_atras=7, con_prep=True)

    datos = logged_client.get(f'/api/clientes/{cliente_id}/pedido-habitual').get_json()

    linea = next(l for l in datos['lineas'] if l['id'] == aceite)
    assert linea['cajas'] == 4, 'la línea de preparación no debe sumarse'
    assert linea['visitas'] == 2


def test_cadencia_y_ultima_fecha(app, logged_client):
    """El encabezado dice «Compra cada N días · última vez el D mmm»."""
    cliente_id, prods = _ids()
    chuleta = prods['Chuleta de cerdo ahumada 5 kg']

    for dias in (21, 14, 7):
        _crear_pedido(cliente_id, [(chuleta, 8)], dias_atras=dias)

    datos = logged_client.get(f'/api/clientes/{cliente_id}/pedido-habitual').get_json()

    assert datos['cadencia_dias'] == 7
    esperada = (datetime.utcnow() - timedelta(days=7)).date().isoformat()
    assert datos['ultima_fecha'] == esperada


def test_endpoint_exige_login(app):
    """El historial de compra de un cliente no es público."""
    cliente_id, _ = _ids()
    resp = app.test_client().get(f'/api/clientes/{cliente_id}/pedido-habitual')
    assert resp.status_code in (301, 302, 401), resp.status_code


# ───────────────────────────────────────────────────────────────────────────
# Grupos de facturación: un pedido nunca mezcla productos con impuestos
# distintos, porque QuickBooks no los factura en un mismo documento.
# ───────────────────────────────────────────────────────────────────────────

def test_grupo_no_es_solo_se_pesa(app, logged_client):
    """Dos pesables con impuestos distintos son grupos distintos.

    Es el caso que se escapa si uno particiona por `se_pesa` a secas: ambos
    son pesables, así que "no mezclar pesables con importados" se cumple, pero
    la factura llevaría tax 10 y tax 14 juntos.
    """
    from app import _grupo_facturable, Producto

    chuleta = Producto.query.filter_by(nombre='Chuleta de cerdo ahumada 5 kg').first()
    ham = Producto.query.filter_by(nombre='Ham di Pasku 4 kg').first()

    assert chuleta.se_pesa and ham.se_pesa
    assert _grupo_facturable(chuleta) != _grupo_facturable(ham)


def test_servidor_rechaza_pedido_mezclado(app, logged_client):
    """El guard no vive solo en la pantalla: un POST directo también se corta."""
    from app import Pedido

    cliente_id, prods = _ids()
    antes = Pedido.query.count()

    resp = logged_client.post('/pedidos/nuevo', data={
        'cliente_id': str(cliente_id),
        'tipo_cambio': '1.0',
        'productos[0][id]': str(prods['Aceite vegetal 12 x 1 L']),
        'productos[0][cajas]': '3',
        'productos[0][precio]': '10.00',
        'productos[1][id]': str(prods['Ham di Pasku 4 kg']),
        'productos[1][cajas]': '2',
        'productos[1][precio]': '5.00',
    }, follow_redirects=True)

    assert resp.status_code == 200
    assert Pedido.query.count() == antes, 'no debe crearse un pedido mezclado'
    assert 'impuestos distintos' in resp.get_data(as_text=True)


def test_servidor_acepta_pesable_e_importado_del_mismo_impuesto(app, logged_client):
    """La contracara: mezclar TIPOS con un mismo impuesto sí se factura.

    Producción tiene 7 pedidos así (agosto 2026) y QuickBooks los facturó sin
    quejarse; el guard es por impuesto, no por `se_pesa`.
    """
    from app import Pedido

    cliente_id, prods = _ids()
    antes = Pedido.query.count()

    resp = logged_client.post('/pedidos/nuevo', data={
        'cliente_id': str(cliente_id),
        'tipo_cambio': '1.0',
        'productos[0][id]': str(prods['Chuleta de cerdo ahumada 5 kg']),  # pesable, imp 10
        'productos[0][cajas]': '3',
        'productos[0][precio]': '10.00',
        'productos[1][id]': str(prods['Aceite vegetal 12 x 1 L']),        # importado, imp 10
        'productos[1][cajas]': '2',
        'productos[1][precio]': '5.00',
    }, follow_redirects=True)

    assert resp.status_code == 200
    assert Pedido.query.count() == antes + 1, 'el pedido debía crearse'
    assert 'impuestos distintos' not in resp.get_data(as_text=True)


def test_servidor_rechaza_mezcla_entre_dos_pesables(app, logged_client):
    """Mismo bloqueo cuando los dos productos son pesables pero difieren en tax."""
    from app import Pedido

    cliente_id, prods = _ids()
    antes = Pedido.query.count()

    resp = logged_client.post('/pedidos/nuevo', data={
        'cliente_id': str(cliente_id),
        'tipo_cambio': '1.0',
        'productos[0][id]': str(prods['Chuleta de cerdo ahumada 5 kg']),
        'productos[0][cajas]': '3',
        'productos[0][precio]': '10.00',
        'productos[1][id]': str(prods['Ham di Pasku 4 kg']),
        'productos[1][cajas]': '2',
        'productos[1][precio]': '13.00',
    }, follow_redirects=True)

    assert Pedido.query.count() == antes
    assert 'impuestos distintos' in resp.get_data(as_text=True)


def test_pedido_de_un_solo_grupo_se_guarda(app, logged_client):
    """El guard no puede estorbar el caso normal."""
    from app import Pedido

    cliente_id, prods = _ids()
    antes = Pedido.query.count()

    logged_client.post('/pedidos/nuevo', data={
        'cliente_id': str(cliente_id),
        'tipo_cambio': '1.0',
        'productos[0][id]': str(prods['Chuleta de cerdo ahumada 5 kg']),
        'productos[0][cajas]': '3',
        'productos[0][precio]': '10.00',
        'productos[1][id]': str(prods['Salchicha Frankfurter 2.5 kg']),
        'productos[1][cajas]': '2',
        'productos[1][precio]': '8.00',
    }, follow_redirects=True)

    assert Pedido.query.count() == antes + 1


def test_cliente_multigrupo_no_precarga_sin_elegir(app, logged_client):
    """Precargar mezclado sería armar un pedido imposible de facturar."""
    cliente_id, prods = _ids()
    chuleta = prods['Chuleta de cerdo ahumada 5 kg']
    ham = prods['Ham di Pasku 4 kg']

    # Dos visitas de cada grupo, en pedidos separados (como en producción).
    _crear_pedido(cliente_id, [(chuleta, 8)], dias_atras=28)
    _crear_pedido(cliente_id, [(chuleta, 8)], dias_atras=21)
    _crear_pedido(cliente_id, [(ham, 3)], dias_atras=14)
    _crear_pedido(cliente_id, [(ham, 3)], dias_atras=7)

    datos = logged_client.get(f'/api/clientes/{cliente_id}/pedido-habitual').get_json()

    assert datos['lineas'] == [], 'sin grupo elegido no se precarga nada'
    assert datos['grupo'] is None
    assert len(datos['grupos']) == 2
    # El grupo del pedido más reciente va primero en la lista.
    assert datos['grupos'][0]['clave'] == 'imp:14'


def test_elegir_grupo_precarga_solo_ese_grupo(app, logged_client):
    cliente_id, prods = _ids()
    chuleta = prods['Chuleta de cerdo ahumada 5 kg']
    ham = prods['Ham di Pasku 4 kg']

    _crear_pedido(cliente_id, [(chuleta, 8)], dias_atras=28)
    _crear_pedido(cliente_id, [(chuleta, 8)], dias_atras=21)
    _crear_pedido(cliente_id, [(ham, 3)], dias_atras=14)
    _crear_pedido(cliente_id, [(ham, 3)], dias_atras=7)

    datos = logged_client.get(
        f'/api/clientes/{cliente_id}/pedido-habitual?grupo=imp:10'
    ).get_json()

    assert datos['grupo'] == 'imp:10'
    ids = [l['id'] for l in datos['lineas']]
    assert ids == [chuleta]
    assert ham not in ids


def test_visitas_se_cuentan_dentro_del_grupo(app, logged_client):
    """Las 4 visitas son las del grupo, no las 4 últimas filtradas después.

    Un cliente que alterna grupos tiene, en sus últimos 8 pedidos, solo 4 de
    cada uno. Si se tomaran las últimas 4 en general y recién ahí se filtrara,
    quedarían 2 visitas útiles y el producto no llegaría al mínimo de 2.
    """
    cliente_id, prods = _ids()
    chuleta = prods['Chuleta de cerdo ahumada 5 kg']
    ham = prods['Ham di Pasku 4 kg']

    for dias in (8, 6, 4, 2):
        _crear_pedido(cliente_id, [(chuleta, 8)], dias_atras=dias)
    for dias in (7, 5, 3, 1):
        _crear_pedido(cliente_id, [(ham, 3)], dias_atras=dias)

    datos = logged_client.get(
        f'/api/clientes/{cliente_id}/pedido-habitual?grupo=imp:10'
    ).get_json()

    assert datos['visitas'] == 4
    assert [l['id'] for l in datos['lineas']] == [chuleta]
    assert datos['lineas'][0]['cajas'] == 8


def test_cliente_de_un_solo_grupo_precarga_directo(app, logged_client):
    """Sin ambigüedad no se pregunta nada: 27 de 49 clientes están en este caso."""
    cliente_id, prods = _ids()
    chuleta = prods['Chuleta de cerdo ahumada 5 kg']

    _crear_pedido(cliente_id, [(chuleta, 8)], dias_atras=14)
    _crear_pedido(cliente_id, [(chuleta, 8)], dias_atras=7)

    datos = logged_client.get(f'/api/clientes/{cliente_id}/pedido-habitual').get_json()

    assert datos['grupo'] == 'imp:10'
    assert len(datos['grupos']) == 1
    assert [l['id'] for l in datos['lineas']] == [chuleta]


def test_fecha_entrega_se_guarda_al_crear_pedido(app, logged_client):
    """Las chips de entrega tienen que aterrizar en una columna consultable."""
    from app import Pedido

    cliente_id, prods = _ids()
    chuleta = prods['Chuleta de cerdo ahumada 5 kg']
    entrega = (datetime.utcnow() + timedelta(days=1)).date()

    resp = logged_client.post('/pedidos/nuevo', data={
        'cliente_id': str(cliente_id),
        'fecha_entrega': entrega.isoformat(),
        'notas': '',
        'tipo_cambio': '1.0',
        'productos[0][id]': str(chuleta),
        'productos[0][cajas]': '3',
        'productos[0][precio]': '10.00',
    }, follow_redirects=True)

    assert resp.status_code == 200
    pedido = Pedido.query.order_by(Pedido.id.desc()).first()
    assert pedido.fecha_entrega == entrega


def test_fecha_entrega_invalida_no_tumba_el_pedido(app, logged_client):
    """Perder el día de entrega es recuperable; perder las líneas no."""
    from app import Pedido

    cliente_id, prods = _ids()
    chuleta = prods['Chuleta de cerdo ahumada 5 kg']

    resp = logged_client.post('/pedidos/nuevo', data={
        'cliente_id': str(cliente_id),
        'fecha_entrega': 'mañana',
        'notas': '',
        'tipo_cambio': '1.0',
        'productos[0][id]': str(chuleta),
        'productos[0][cajas]': '3',
        'productos[0][precio]': '10.00',
    }, follow_redirects=True)

    assert resp.status_code == 200
    pedido = Pedido.query.order_by(Pedido.id.desc()).first()
    assert pedido is not None
    assert pedido.fecha_entrega is None
    assert len(pedido.detalles) >= 1
