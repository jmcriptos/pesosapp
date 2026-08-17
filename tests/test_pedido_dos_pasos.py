# tests/test_pedido_dos_pasos.py
"""El form de pedidos en dos pasos: primero el cliente, después el pedido.

Antes /pedidos/nuevo abría el form entero con el cliente vacío y el JS iba a
buscar precios e historial por AJAX. Ahora el paso 1 solo pregunta el cliente y
el paso 2 (`?cliente=<id>`) llega ya sembrado desde el servidor: catálogo con
los precios de ESE cliente y las líneas de su pedido habitual.
"""
import json
import os
import re
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

        # Los tres grupos de facturación que existen en producción. Ojo con el
        # tercero: `se_pesa` NO determina el impuesto — hay pesables con
        # tax_rate 10 y con 14, así que el grupo es el par (se_pesa, tax_rate).
        for nombre, se_pesa, tax in [
            ('Chuleta de cerdo ahumada 5 kg', True, 10.0),   # pesable:10
            ('Salchicha Frankfurter 2.5 kg', True, 10.0),    # pesable:10
            ('Ham di Pasku 4 kg', True, 14.0),               # pesable:14
            ('Aceite vegetal 12 x 1 L', False, 10.0),        # importado:10
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


def _seed_lineas(html):
    """Las líneas que el servidor sembró en el paso 2, ya parseadas.

    Buscar un nombre de producto en el HTML entero no prueba nada: el catálogo
    completo viaja en la misma página. Lo que importa es qué trae el pedido.
    """
    marca = 'const productos_pedido = '
    inicio = html.index(marca) + len(marca)
    fin = html.index('\n', inicio)
    return json.loads(html[inicio:fin].rstrip().rstrip(';'))


def test_paso1_sin_cliente_muestra_selector(app, logged_client):
    resp = logged_client.get('/pedidos/nuevo')
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert 'id="paso-cliente"' in html
    assert 'id="form-nuevo-pedido"' not in html   # el paso 1 no trae el form del pedido


def test_paso2_cliente_con_historial_siembra_lineas(app, logged_client):
    cliente_id, prods = _ids()
    chuleta = prods['Chuleta de cerdo ahumada 5 kg']
    _crear_pedido(cliente_id, [(chuleta, 7)], dias_atras=3)

    resp = logged_client.get(f'/pedidos/nuevo?cliente={cliente_id}')
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert 'id="form-nuevo-pedido"' in html
    assert 'Chuleta de cerdo ahumada 5 kg' in html
    assert '"habitual": 7' in html or '"habitual":7' in html
    # (el hidden cliente_id llega con la Task 3; aquí el select transicional
    # debe traer al cliente preseleccionado)
    assert 'selected' in html
    # `selected` a secas también casa con el `selectedIndex` del JS viejo; lo
    # que se está probando es que el <option> de ESTE cliente venga marcado.
    assert re.search(rf'<option value="{cliente_id}"[^>]*selected', html)


def test_paso2_multigrupo_sin_grupo_repregunta(app, logged_client):
    cliente_id, prods = _ids()
    _crear_pedido(cliente_id, [(prods['Chuleta de cerdo ahumada 5 kg'], 3)], dias_atras=7)
    _crear_pedido(cliente_id, [(prods['Ham di Pasku 4 kg'], 2)], dias_atras=3)

    resp = logged_client.get(f'/pedidos/nuevo?cliente={cliente_id}')
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert 'id="paso-cliente"' in html
    assert 'Qué pedido vas a tomar' in html
    assert f'cliente={cliente_id}&amp;grupo=pesable:10' in html or f'cliente={cliente_id}&grupo=pesable:10' in html


def test_paso2_multigrupo_con_grupo_precarga_solo_ese(app, logged_client):
    cliente_id, prods = _ids()
    for dias in (14, 7):
        _crear_pedido(cliente_id, [(prods['Chuleta de cerdo ahumada 5 kg'], 3)], dias_atras=dias)
        _crear_pedido(cliente_id, [(prods['Ham di Pasku 4 kg'], 2)], dias_atras=dias - 1)

    resp = logged_client.get(f'/pedidos/nuevo?cliente={cliente_id}&grupo=pesable:10')
    html = resp.get_data(as_text=True)
    assert 'id="form-nuevo-pedido"' in html
    assert 'Chuleta de cerdo ahumada 5 kg' in html
    assert 'Ham di Pasku 4 kg' not in html.split('const productos =')[0]  # no en líneas sembradas
    # El grupo elegido manda: la línea del otro grupo no se siembra.
    nombres = [l['nombre'] for l in _seed_lineas(html)]
    assert nombres == ['Chuleta de cerdo ahumada 5 kg']


def test_paso2_cliente_inexistente_redirige_paso1(app, logged_client):
    resp = logged_client.get('/pedidos/nuevo?cliente=99999', follow_redirects=False)
    assert resp.status_code in (302, 303)


def test_catalogo_paso2_trae_precio_del_cliente(app, logged_client):
    from app import PrecioClienteProducto
    cliente_id, prods = _ids()
    pid = prods['Chuleta de cerdo ahumada 5 kg']
    _db.session.add(PrecioClienteProducto(
        cliente_id=cliente_id, producto_id=pid, precio_base=99.55))
    _db.session.commit()
    _crear_pedido(cliente_id, [(pid, 3)], dias_atras=3)

    html = logged_client.get(f'/pedidos/nuevo?cliente={cliente_id}').get_data(as_text=True)
    assert '99.55' in html
