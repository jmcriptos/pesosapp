"""Varios productos pueden compartir el mismo `qbo_id`.

Hay productos que se pesan y etiquetan por separado (cada uno con su lote y su
peso) pero que en QuickBooks se facturan contra un único ítem de servicio. El
`qbo_id` dejó de ser único para permitirlo; estos tests fijan lo que eso
implica en las tres rutas que cruzaban código QBO → producto.
"""
import os
from datetime import date, datetime
from decimal import Decimal

import pytest

os.environ.setdefault('SECRET_KEY', 'test-secret')
os.environ.setdefault('FLASK_ENV', 'testing')
os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')

from app import app as flask_app, db as _db

CODIGO_SERVICIO = 'QBO-SERV'


@pytest.fixture
def app():
    flask_app.config.update(
        TESTING=True,
        WTF_CSRF_ENABLED=False,
        SQLALCHEMY_DATABASE_URI='sqlite:///:memory:',
    )
    with flask_app.app_context():
        _db.create_all()
        yield flask_app
        _db.drop_all()


def _base(qbo_cliente='QBO-C1'):
    """Rol + territorio + vendedor + cliente. Devuelve (vendedor, cliente)."""
    from app import Rol, Territorio, Vendedor, Cliente

    rol = Rol(nombre='super_admin', descripcion='Admin')
    territorio = Territorio(nombre='t1', descripcion='T1')
    _db.session.add_all([rol, territorio])
    _db.session.flush()

    vendedor = Vendedor(
        username='tester', email='t@test.com', nombre_completo='Tester',
        rol_id=rol.id, territorio_id=territorio.id, activo=True,
    )
    vendedor.set_password('x')
    cliente = Cliente(nombre='Cliente QBO', territorio_id=territorio.id,
                      qbo_id=qbo_cliente)
    _db.session.add_all([vendedor, cliente])
    _db.session.flush()
    return vendedor, cliente


def _producto(nombre, qbo_id=CODIGO_SERVICIO, se_pesa=True, tax_rate=6.0):
    from app import Producto

    p = Producto(nombre=nombre, descripcion=nombre, temperatura='Refrigerado',
                 se_pesa=se_pesa, tax_rate=tax_rate, qbo_id=qbo_id)
    _db.session.add(p)
    _db.session.flush()
    return p


# ---------------------------------------------------------------- modelo


def test_dos_productos_pueden_compartir_el_mismo_qbo_id(app):
    """El `qbo_id` ya no es único: dos productos distintos que se facturan
    contra el mismo ítem de servicio deben poder guardarse."""
    from app import Producto

    with app.app_context():
        _base()
        _producto('Pechuga deshuesada')
        _producto('Muslo deshuesado')
        _db.session.commit()

        compartidos = Producto.query.filter_by(qbo_id=CODIGO_SERVICIO).all()
        assert len(compartidos) == 2, (
            f'Esperaba 2 productos con el código {CODIGO_SERVICIO}, '
            f'encontré {len(compartidos)}'
        )


# ------------------------------------------------------------ facturación


def _pedido_dos_productos_mismo_codigo(precio_a='10.00', precio_b='10.00'):
    """Pedido con dos productos pesables distintos que comparten `qbo_id`,
    cada uno con una caja pesada. Devuelve (pedido, prod_a, prod_b)."""
    from app import Pedido, DetallePedido, CajaPesada

    vendedor, cliente = _base()
    prod_a = _producto('Pechuga deshuesada')
    prod_b = _producto('Muslo deshuesado')

    pedido = Pedido(cliente_id=cliente.id, estado='preparado', tipo_cambio=1.0)
    _db.session.add(pedido)
    _db.session.flush()

    for prod, precio, peso in ((prod_a, precio_a, '2.50'), (prod_b, precio_b, '3.10')):
        detalle = DetallePedido(
            pedido_id=pedido.id, producto_id=prod.id, cajas=1, cajas_pedidas=1,
            peso=0, precio_unitario=Decimal(precio), subtotal=Decimal('0'),
            es_linea_pedido=True,
        )
        _db.session.add(detalle)
        _db.session.flush()
        _db.session.add(CajaPesada(
            detalle_pedido_id=detalle.id, numero=1, peso=Decimal(peso),
            lote=f'L-{prod.id}', fecha_elaboracion=date(2026, 1, 1),
            fecha_vencimiento=date(2026, 6, 1), pesado_por=vendedor.id,
            pesado_en=datetime(2026, 4, 22, 12, 0, 0),
        ))
    _db.session.commit()
    return pedido, prod_a, prod_b


def test_payload_factura_manda_ambos_productos_con_el_mismo_item_qbo(app):
    """El payload conserva una línea por producto (cada una con su nombre y su
    peso) pero todas apuntan al mismo ítem de QBO, que es lo que permite que
    N8N las agrupe en una sola línea de la factura."""
    from app import pedido_a_json

    with app.app_context():
        pedido, prod_a, prod_b = _pedido_dos_productos_mismo_codigo()

        payload = pedido_a_json(pedido)

        assert len(payload['lines']) == 2
        assert {l['product_qbo_id'] for l in payload['lines']} == {CODIGO_SERVICIO}
        assert {l['descripcion'] for l in payload['lines']} == {
            prod_a.nombre, prod_b.nombre
        }


def test_validacion_de_facturacion_acepta_codigo_compartido(app):
    """Compartir el código no es un error de facturación: la validación previa
    al envío a QBO no debe reportar nada."""
    from app import pedido_a_json, _validar_datos_facturacion

    with app.app_context():
        pedido, _a, _b = _pedido_dos_productos_mismo_codigo()

        errores = _validar_datos_facturacion(pedido_a_json(pedido))

        assert errores == [], f'No esperaba errores, recibí: {errores}'


# ------------------------------------------- precios desde la factura de QBO


def _factura_json(item_qbo_id, rate, qty=1.0, nombre='Servicio'):
    return {
        'Invoice': {
            'Id': '999', 'DocNumber': '1001', 'TxnDate': '2026-08-28',
            'Line': [{
                'DetailType': 'SalesItemLineDetail',
                'Amount': rate * qty,
                'Description': '',
                'SalesItemLineDetail': {
                    'ItemRef': {'value': item_qbo_id, 'name': nombre},
                    'Qty': qty, 'UnitPrice': rate,
                },
            }],
        }
    }


def test_precios_no_se_actualizan_cuando_el_codigo_es_compartido(app):
    """Una línea de la factura cuyo código pertenece a varios productos no
    puede resolverse a uno solo: se muestra, pero no se ofrece actualizar."""
    from app import _comparar_precios_factura

    with app.app_context():
        pedido, _a, _b = _pedido_dos_productos_mismo_codigo()

        filas, _avisos = _comparar_precios_factura(
            pedido, _factura_json(CODIGO_SERVICIO, 12.50)
        )

        assert len(filas) == 1
        assert filas[0]['estado'] == 'codigo_compartido', (
            f"Esperaba estado 'codigo_compartido', recibí {filas[0]['estado']!r}"
        )
        assert filas[0]['motivo']
        assert filas[0]['producto_id'] is None, (
            'No se puede elegir un producto: el código pertenece a varios'
        )


def test_precios_se_siguen_actualizando_con_codigo_propio(app):
    """El caso normal (un código = un producto) no cambia: la diferencia de
    precio se sigue detectando y ofreciendo."""
    from app import _comparar_precios_factura

    with app.app_context():
        vendedor, cliente = _base()
        prod = _producto('Lomo entero', qbo_id='QBO-SOLO')
        _pedido_una_linea(vendedor, cliente, prod, precio='10.00')

        from app import Pedido
        pedido = Pedido.query.first()
        filas, _avisos = _comparar_precios_factura(
            pedido, _factura_json('QBO-SOLO', 12.50)
        )

        assert len(filas) == 1
        assert filas[0]['estado'] == 'difiere'
        assert filas[0]['producto_id'] == prod.id


def _pedido_una_linea(vendedor, cliente, prod, precio='10.00'):
    from app import Pedido, DetallePedido, CajaPesada

    pedido = Pedido(cliente_id=cliente.id, estado='preparado', tipo_cambio=1.0)
    _db.session.add(pedido)
    _db.session.flush()
    detalle = DetallePedido(
        pedido_id=pedido.id, producto_id=prod.id, cajas=1, cajas_pedidas=1,
        peso=0, precio_unitario=Decimal(precio), subtotal=Decimal('0'),
        es_linea_pedido=True,
    )
    _db.session.add(detalle)
    _db.session.flush()
    _db.session.add(CajaPesada(
        detalle_pedido_id=detalle.id, numero=1, peso=Decimal('2.00'),
        lote='L1', fecha_elaboracion=date(2026, 1, 1),
        fecha_vencimiento=date(2026, 6, 1), pesado_por=vendedor.id,
        pesado_en=datetime(2026, 4, 22, 12, 0, 0),
    ))
    _db.session.commit()
    return pedido


# ------------------------------------------------- importación de precios CSV


def test_import_csv_rechaza_codigo_qbo_ambiguo(app):
    """El CSV puede traer el código QBO en vez del ID. Si ese código lo usan
    varios productos, hay que decirlo — no elegir uno al azar."""
    from app import procesar_precios_por_lista, ListaPrecio

    with app.app_context():
        _base()
        _producto('Pechuga deshuesada')
        _producto('Muslo deshuesado')
        lista = ListaPrecio(nombre='General', descripcion='Default')
        _db.session.add(lista)
        _db.session.commit()

        resultados = {'procesados': 0, 'errores': 0, 'warnings': [], 'detalles': []}
        filas = [{'codigo_producto': CODIGO_SERVICIO, 'precio_base': '10.00'}]

        resultados = procesar_precios_por_lista(iter(filas), lista.id, resultados)

        assert resultados['errores'] == 1
        assert resultados['procesados'] == 0
        assert any('varios productos' in d for d in resultados['detalles']), (
            f"Esperaba un detalle explicando la ambigüedad, recibí: "
            f"{resultados['detalles']}"
        )


# ------------------------------------------------------- pantalla de productos


@pytest.fixture
def logged_client(app):
    with app.app_context():
        _base()
        _db.session.commit()
    client = app.test_client()
    client.post('/login', data={'username': 'tester', 'password': 'x'},
                follow_redirects=True)
    return client


def _crear_producto_por_form(client, nombre, qbo_id):
    return client.post('/productos', data={
        'nombre': nombre, 'descripcion': nombre, 'temperatura': 'Refrigerado',
        'qbo_id': qbo_id, 'tax_rate': '6.0', 'se_pesa': 'on',
    }, follow_redirects=True)


def test_el_form_de_productos_acepta_un_codigo_qbo_ya_usado(app, logged_client):
    """Cargar un segundo producto con un código que ya existe tiene que
    funcionar: es justo lo que se necesita para el ítem de servicio."""
    from app import Producto

    _crear_producto_por_form(logged_client, 'Pechuga deshuesada', CODIGO_SERVICIO)
    respuesta = _crear_producto_por_form(logged_client, 'Muslo deshuesado', CODIGO_SERVICIO)

    assert respuesta.status_code == 200
    with app.app_context():
        nombres = {p.nombre for p in Producto.query.filter_by(qbo_id=CODIGO_SERVICIO)}
        assert nombres == {'Pechuga deshuesada', 'Muslo deshuesado'}, (
            f'El segundo producto no se guardó; hay: {nombres}'
        )


def test_avisa_cuando_el_codigo_qbo_queda_compartido(app, logged_client):
    """No bloquea, pero sí avisa: un código repetido por error de tipeo tiene
    que notarse en el momento de guardar."""
    _crear_producto_por_form(logged_client, 'Pechuga deshuesada', CODIGO_SERVICIO)
    respuesta = _crear_producto_por_form(logged_client, 'Muslo deshuesado', CODIGO_SERVICIO)

    cuerpo = respuesta.get_data(as_text=True)
    marca = f'El código QBO {CODIGO_SERVICIO} lo comparten 2 productos'
    assert marca in cuerpo, 'Falta el aviso de código compartido al guardar'
    # El aviso tiene que nombrar con quién lo comparte, no solo decir que pasa.
    aviso = cuerpo.split(marca, 1)[1][:200]
    assert 'Pechuga deshuesada' in aviso and 'Muslo deshuesado' in aviso, (
        f'Aviso sin los nombres: {aviso!r}'
    )


def test_el_listado_marca_los_codigos_compartidos(app, logged_client):
    """En /productos, un código usado por varios productos se marca con
    `data-qbo-compartido` = cuántos lo comparten."""
    _crear_producto_por_form(logged_client, 'Pechuga deshuesada', CODIGO_SERVICIO)
    _crear_producto_por_form(logged_client, 'Muslo deshuesado', CODIGO_SERVICIO)
    _crear_producto_por_form(logged_client, 'Lomo entero', 'QBO-SOLO')

    cuerpo = logged_client.get('/productos').get_data(as_text=True)

    assert cuerpo.count('data-qbo-compartido="2"') == 2, (
        'Los dos productos del código compartido deben marcarse'
    )
    assert 'data-qbo-compartido="1"' not in cuerpo, (
        'Un código propio no es compartido y no debe marcarse'
    )
