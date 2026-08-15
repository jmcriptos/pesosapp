"""Actualización de la lista de precios desde la factura corregida en QBO.

Cuando la lista está desactualizada el precio se corrige a mano en QuickBooks y
esa corrección no vuelve nunca a la app, así que hay que volver a corregirla en
la factura siguiente. Estos tests cubren el camino de vuelta.
"""
import os
from unittest.mock import MagicMock, patch

import pytest

os.environ.setdefault('SECRET_KEY', 'test-secret')
os.environ.setdefault('FLASK_ENV', 'testing')
os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')

from app import app as flask_app, db as _db

INVOICE_ID = '47346'
QBO_ITEM_ID = '806'
QBO_ITEM_ID_2 = '807'


@pytest.fixture
def app():
    flask_app.config.update(
        TESTING=True, WTF_CSRF_ENABLED=False,
        SQLALCHEMY_DATABASE_URI='sqlite:///:memory:',
    )
    with flask_app.app_context():
        _db.create_all()
        yield flask_app
        _db.drop_all()


def _factura(lineas=None):
    """Estructura real de una Invoice de QBO (verificada contra agosto 2026)."""
    if lineas is None:
        lineas = [{'item': QBO_ITEM_ID, 'nombre': 'Smoked Turkey Breast', 'qty': 10, 'precio': 34.00}]
    return {
        'Invoice': {
            'Id': INVOICE_ID,
            'DocNumber': '5813',
            'TxnDate': '2026-08-14',
            'CustomerRef': {'name': 'Centrum'},
            'Line': [
                {
                    'DetailType': 'SalesItemLineDetail',
                    'Amount': l['qty'] * l['precio'],
                    'SalesItemLineDetail': {
                        'ItemRef': {'value': l['item'], 'name': l['nombre']},
                        'Qty': l['qty'],
                        'UnitPrice': l['precio'],
                    },
                }
                for l in lineas
            ],
        }
    }


def _armar(precio_app=24.80, precio_facturado=24.80, con_linea_preparacion=True,
           qbo_id_producto=QBO_ITEM_ID):
    """Crea el escenario base y devuelve (pedido_id, producto_id, cliente_id)."""
    from app import (Rol, Territorio, Vendedor, Cliente, Producto, Pedido,
                     DetallePedido, PrecioClienteProducto)

    rol = Rol(nombre='super_admin', descripcion='Admin')
    _db.session.add(rol)
    territorio = Territorio(nombre='t', descripcion='T')
    _db.session.add(territorio)
    _db.session.flush()

    vendedor = Vendedor(username='admin', email='a@t.com', nombre_completo='Admin',
                        rol_id=rol.id, territorio_id=territorio.id, activo=True)
    vendedor.set_password('testpass')
    _db.session.add(vendedor)

    cliente = Cliente(nombre='Centrum', territorio_id=territorio.id, qbo_id='1570')
    producto = Producto(nombre='Smoked Turkey Breast', qbo_id=qbo_id_producto, tax_rate=0.06)
    _db.session.add_all([cliente, producto])
    _db.session.flush()

    if precio_app is not None:
        precio = PrecioClienteProducto(
            cliente_id=cliente.id, producto_id=producto.id,
            precio_base=precio_app, margen_jomar=1.0, margen_retail=1.2, activo=True,
        )
        precio.calcular_precios()
        _db.session.add(precio)

    pedido = Pedido(cliente_id=cliente.id, estado='facturado',
                    invoice_id_qbo=INVOICE_ID, doc_number_qbo='5813')
    _db.session.add(pedido)
    _db.session.flush()

    _db.session.add(DetallePedido(
        pedido_id=pedido.id, producto_id=producto.id, cajas=10, peso=0,
        precio_unitario=precio_facturado, subtotal=precio_facturado * 10,
        es_linea_pedido=True, cajas_pedidas=10,
    ))
    if con_linea_preparacion:
        _db.session.add(DetallePedido(
            pedido_id=pedido.id, producto_id=producto.id, cajas=10, peso=0,
            precio_unitario=precio_facturado, subtotal=precio_facturado * 10,
            es_linea_pedido=False, cajas_pedidas=10,
        ))

    _db.session.commit()
    return pedido.id, producto.id, cliente.id


def _login(app, username='admin', password='testpass'):
    client = app.test_client()
    client.post('/login', data={'username': username, 'password': password},
                follow_redirects=True)
    return client


def _mock_qbo(mock_post, payload=None):
    resp = MagicMock()
    resp.raise_for_status.return_value = None
    resp.json.return_value = payload if payload is not None else _factura()
    mock_post.return_value = resp
    return resp


# ─────────────────────────── Extracción (unitario) ───────────────────────────

def test_extraer_datos_factura_expone_item_qbo_id():
    """AC 1 (base): sin el id del ítem no hay forma de cruzar contra Producto."""
    from utils.factura_pdf import extraer_datos_factura

    datos = extraer_datos_factura(_factura())
    assert datos['lineas'][0]['item_qbo_id'] == QBO_ITEM_ID
    assert datos['lineas'][0]['rate'] == 34.00


def test_extraer_datos_factura_sin_item_ref_no_revienta():
    from utils.factura_pdf import extraer_datos_factura

    payload = {'Invoice': {'Id': INVOICE_ID, 'Line': [{
        'DetailType': 'SalesItemLineDetail',
        'Amount': 10.0,
        'SalesItemLineDetail': {'Qty': 1, 'UnitPrice': 10.0},
    }]}}
    assert extraer_datos_factura(payload)['lineas'][0]['item_qbo_id'] is None


# ─────────────────────────────── Comparación ─────────────────────────────────

@patch('app.N8N_INVOICE_FETCH_WEBHOOK_URL', 'http://n8n.local/fetch')
@patch('app.requests.post')
def test_muestra_la_diferencia_de_precio(mock_post, app):
    """AC 1: el precio corregido en QBO aparece contra el vigente en la app."""
    _mock_qbo(mock_post)
    pedido_id, _, _ = _armar(precio_app=24.80)

    resp = _login(app).get(f'/pedidos/{pedido_id}/precios-factura')

    assert resp.status_code == 200
    html = resp.data.decode()
    assert 'Smoked Turkey Breast' in html
    assert '34.00' in html
    assert '24.80' in html


@patch('app.N8N_INVOICE_FETCH_WEBHOOK_URL', 'http://n8n.local/fetch')
@patch('app.requests.post')
def test_precio_igual_no_se_lista(mock_post, app):
    """AC 2: sin umbral, el redondeo llenaría la pantalla de ruido."""
    _mock_qbo(mock_post, _factura([
        {'item': QBO_ITEM_ID, 'nombre': 'Smoked Turkey Breast', 'qty': 10, 'precio': 24.80},
    ]))
    pedido_id, _, _ = _armar(precio_app=24.80)

    html = _login(app).get(f'/pedidos/{pedido_id}/precios-factura').data.decode()

    assert 'coinciden con los de la app' in html
    assert 'Actualizar precios seleccionados' not in html


@patch('app.N8N_INVOICE_FETCH_WEBHOOK_URL', 'http://n8n.local/fetch')
@patch('app.requests.post')
def test_producto_sin_qbo_id_se_muestra_como_no_reconocido(mock_post, app):
    """AC 9: nunca descartar una línea en silencio."""
    _mock_qbo(mock_post)
    pedido_id, _, _ = _armar(qbo_id_producto='999')

    html = _login(app).get(f'/pedidos/{pedido_id}/precios-factura').data.decode()

    assert 'no se pueden actualizar' in html
    assert 'No corresponde a ningún producto' in html


@patch('app.N8N_INVOICE_FETCH_WEBHOOK_URL', 'http://n8n.local/fetch')
@patch('app.requests.post')
def test_avisa_si_la_factura_no_cubre_las_lineas_del_pedido(mock_post, app):
    """AC 10: un pedido puede tener más de una factura en QBO."""
    from app import Producto, DetallePedido, Pedido

    _mock_qbo(mock_post)
    pedido_id, _, _ = _armar()

    otro = Producto(nombre='Smoked Turkey Ham', qbo_id=QBO_ITEM_ID_2, tax_rate=0.06)
    _db.session.add(otro)
    _db.session.flush()
    _db.session.add(DetallePedido(
        pedido_id=pedido_id, producto_id=otro.id, cajas=5, peso=0,
        precio_unitario=18.65, subtotal=93.25, es_linea_pedido=False, cajas_pedidas=5,
    ))
    _db.session.commit()

    html = _login(app).get(f'/pedidos/{pedido_id}/precios-factura').data.decode()

    assert 'no cubre todas las líneas del pedido' in html
    assert 'Smoked Turkey Ham' in html


@patch('app.N8N_INVOICE_FETCH_WEBHOOK_URL', 'http://n8n.local/fetch')
@patch('app.requests.post')
def test_pedido_sin_lineas_de_preparacion_no_avisa_de_mas(mock_post, app):
    """AC 11: los productos pesables se facturan desde la línea ORIGINAL vía sus
    CajaPesada, así que 'sin líneas de preparación' es normal, no un problema.
    Verificado en producción: pasa en la mitad de los pedidos de agosto."""
    from app import CajaPesada, DetallePedido, Producto
    from datetime import date

    _mock_qbo(mock_post)
    pedido_id, producto_id, _ = _armar(precio_app=24.80, con_linea_preparacion=False)

    Producto.query.get(producto_id).se_pesa = True
    original = DetallePedido.query.filter_by(
        pedido_id=pedido_id, es_linea_pedido=True).first()
    _db.session.add(CajaPesada(
        detalle_pedido_id=original.id, numero=1, peso=10.0, lote='L1',
        fecha_elaboracion=date(2026, 8, 1), fecha_vencimiento=date(2026, 12, 1),
    ))
    _db.session.commit()

    resp = _login(app).get(f'/pedidos/{pedido_id}/precios-factura')
    html = resp.data.decode()

    assert resp.status_code == 200
    assert 'no se pudo determinar' not in html.lower()
    # El precio que se facturó sale de la línea original, no de una de preparación
    assert 'Se facturó desde la app a 24.80' in html


@patch('app.N8N_INVOICE_FETCH_WEBHOOK_URL', 'http://n8n.local/fetch')
@patch('app.requests.post')
def test_pedido_sin_ninguna_linea_facturable_degrada(mock_post, app):
    """AC 11 (caso real): sin líneas de preparación ni cajas pesadas no se puede
    saber qué mandó la app, pero la vista responde igual."""
    _mock_qbo(mock_post)
    pedido_id, _, _ = _armar(con_linea_preparacion=False)

    resp = _login(app).get(f'/pedidos/{pedido_id}/precios-factura')

    assert resp.status_code == 200
    assert 'No se pudo determinar' in resp.data.decode()


def test_template_no_ofrece_aplicar_todas(app):
    """AC 6: la fricción por línea es la defensa contra el descuento puntual."""
    with patch('app.N8N_INVOICE_FETCH_WEBHOOK_URL', 'http://n8n.local/fetch'), \
         patch('app.requests.post') as mock_post:
        _mock_qbo(mock_post)
        pedido_id, _, _ = _armar()
        html = _login(app).get(f'/pedidos/{pedido_id}/precios-factura').data.decode()

    assert 'name="aplicar"' in html
    assert 'checked' not in html.split('name="aplicar"')[1].split('>')[0]
    assert 'seleccionar tod' not in html.lower()
    assert 'aplicar tod' not in html.lower()


# ────────────────── Regresiones de la revisión adversarial ───────────────────

@patch('app.N8N_INVOICE_FETCH_WEBHOOK_URL', 'http://n8n.local/fetch')
@patch('app.requests.post')
def test_reactiva_precio_desactivado_en_vez_de_duplicarlo(mock_post, app):
    """F1: la unique constraint es (cliente_id, producto_id) SIN incluir `activo`,
    así que crear una fila nueva sobre una desactivada revienta con IntegrityError."""
    from app import PrecioClienteProducto

    _mock_qbo(mock_post)
    pedido_id, producto_id, cliente_id = _armar(precio_app=24.80)

    viejo = PrecioClienteProducto.query.filter_by(
        cliente_id=cliente_id, producto_id=producto_id).first()
    viejo.activo = False
    _db.session.commit()

    resp = _login(app).post(f'/pedidos/{pedido_id}/precios-factura/aplicar',
                            data={'aplicar': str(producto_id)}, follow_redirects=True)

    assert resp.status_code == 200
    filas = PrecioClienteProducto.query.filter_by(
        cliente_id=cliente_id, producto_id=producto_id).all()
    assert len(filas) == 1
    assert filas[0].activo is True
    assert float(filas[0].precio_base) == 34.00


@patch('app.N8N_INVOICE_FETCH_WEBHOOK_URL', 'http://n8n.local/fetch')
@patch('app.requests.post')
def test_precio_cero_en_la_factura_no_se_puede_aplicar(mock_post, app):
    """F2: escribir un precio 0 en la lista es justo lo que la guarda de
    facturación impide del otro lado."""
    from app import PrecioClienteProducto

    _mock_qbo(mock_post, _factura([
        {'item': QBO_ITEM_ID, 'nombre': 'Smoked Turkey Breast', 'qty': 10, 'precio': 0},
    ]))
    pedido_id, producto_id, cliente_id = _armar(precio_app=24.80)
    client = _login(app)

    html = client.get(f'/pedidos/{pedido_id}/precios-factura').data.decode()
    assert 'precio 0' in html
    assert 'name="aplicar"' not in html

    client.post(f'/pedidos/{pedido_id}/precios-factura/aplicar',
                data={'aplicar': str(producto_id)}, follow_redirects=True)
    precio = PrecioClienteProducto.query.filter_by(
        cliente_id=cliente_id, producto_id=producto_id).first()
    assert float(precio.precio_base) == 24.80


@patch('app.N8N_INVOICE_FETCH_WEBHOOK_URL', 'http://n8n.local/fetch')
@patch('app.requests.post')
def test_producto_con_dos_precios_en_la_factura_no_se_aplica(mock_post, app):
    """F3: el payload emite una línea por caja pesada, así que un producto puede
    venir repetido. Con precios distintos no hay un precio nuevo único."""
    from app import PrecioClienteProducto

    _mock_qbo(mock_post, _factura([
        {'item': QBO_ITEM_ID, 'nombre': 'Smoked Turkey Breast', 'qty': 5, 'precio': 34.00},
        {'item': QBO_ITEM_ID, 'nombre': 'Smoked Turkey Breast', 'qty': 5, 'precio': 31.00},
    ]))
    pedido_id, producto_id, cliente_id = _armar(precio_app=24.80)
    client = _login(app)

    html = client.get(f'/pedidos/{pedido_id}/precios-factura').data.decode()
    assert 'más de un precio' in html
    assert 'name="aplicar"' not in html

    client.post(f'/pedidos/{pedido_id}/precios-factura/aplicar',
                data={'aplicar': str(producto_id)}, follow_redirects=True)
    precio = PrecioClienteProducto.query.filter_by(
        cliente_id=cliente_id, producto_id=producto_id).first()
    assert float(precio.precio_base) == 24.80


@patch('app.N8N_INVOICE_FETCH_WEBHOOK_URL', 'http://n8n.local/fetch')
@patch('app.requests.post')
def test_producto_repetido_con_mismo_precio_suma_cantidades(mock_post, app):
    """F3 (caso normal): varias cajas del mismo producto al mismo precio son
    una sola diferencia, no una fila duplicada por caja."""
    _mock_qbo(mock_post, _factura([
        {'item': QBO_ITEM_ID, 'nombre': 'Smoked Turkey Breast', 'qty': 6, 'precio': 34.00},
        {'item': QBO_ITEM_ID, 'nombre': 'Smoked Turkey Breast', 'qty': 4, 'precio': 34.00},
    ]))
    pedido_id, _, _ = _armar(precio_app=24.80)

    html = _login(app).get(f'/pedidos/{pedido_id}/precios-factura').data.decode()

    assert html.count('name="aplicar"') == 1
    assert '10.00' in html


@patch('app.N8N_INVOICE_FETCH_WEBHOOK_URL', 'http://n8n.local/fetch')
@patch('app.requests.post')
def test_avisa_cuando_el_precio_se_hereda_de_la_lista(mock_post, app):
    """F4: aplicar acá desengancha al cliente de la lista general para siempre."""
    from app import ListaPrecio, PrecioProducto

    _mock_qbo(mock_post)
    pedido_id, producto_id, _ = _armar(precio_app=None)

    lista = ListaPrecio(nombre='General', es_default=True, activa=True)
    _db.session.add(lista)
    _db.session.flush()
    en_lista = PrecioProducto(lista_precio_id=lista.id, producto_id=producto_id,
                              precio_base=24.80, margen_jomar=1.0, margen_retail=1.2,
                              activo=True)
    en_lista.calcular_precios()
    _db.session.add(en_lista)
    _db.session.commit()

    html = _login(app).get(f'/pedidos/{pedido_id}/precios-factura').data.decode()

    assert 'hereda el precio de la lista general' in html


# ──────────────────────────────── Escritura ──────────────────────────────────

@patch('app.N8N_INVOICE_FETCH_WEBHOOK_URL', 'http://n8n.local/fetch')
@patch('app.requests.post')
def test_aplicar_actualiza_el_precio_del_cliente(mock_post, app):
    """AC 4: el objetivo — que la próxima factura salga con el precio nuevo."""
    from app import PrecioClienteProducto, PedidoEvento
    import json

    _mock_qbo(mock_post)
    pedido_id, producto_id, cliente_id = _armar(precio_app=24.80)

    resp = _login(app).post(
        f'/pedidos/{pedido_id}/precios-factura/aplicar',
        data={'aplicar': str(producto_id)}, follow_redirects=True,
    )

    assert resp.status_code == 200
    precio = PrecioClienteProducto.query.filter_by(
        cliente_id=cliente_id, producto_id=producto_id).first()
    assert float(precio.precio_base) == 34.00
    # margen 1.0 → lo que se factura es exactamente el precio_base
    assert float(precio.precio_jomar) == 34.00

    evento = PedidoEvento.query.filter_by(tipo='precio_actualizado').first()
    assert evento is not None
    meta = json.loads(evento.meta)
    assert meta['precio_anterior'] == 24.80
    assert meta['precio_nuevo'] == 34.00
    assert meta['invoice_id_qbo'] == INVOICE_ID


@patch('app.N8N_INVOICE_FETCH_WEBHOOK_URL', 'http://n8n.local/fetch')
@patch('app.requests.post')
def test_aplicar_crea_el_precio_si_no_existia(mock_post, app):
    """AC 3: el caso del producto nuevo, que fue el origen del incidente."""
    from app import PrecioClienteProducto

    _mock_qbo(mock_post)
    pedido_id, producto_id, cliente_id = _armar(precio_app=None)

    _login(app).post(f'/pedidos/{pedido_id}/precios-factura/aplicar',
                     data={'aplicar': str(producto_id)}, follow_redirects=True)

    precio = PrecioClienteProducto.query.filter_by(
        cliente_id=cliente_id, producto_id=producto_id).first()
    assert precio is not None
    assert float(precio.precio_base) == 34.00
    assert float(precio.margen_jomar) == 1.0


@patch('app.N8N_INVOICE_FETCH_WEBHOOK_URL', 'http://n8n.local/fetch')
@patch('app.requests.post')
def test_sin_seleccion_no_escribe_nada(mock_post, app):
    """AC 5: el default es no aplicar."""
    from app import PrecioClienteProducto, PedidoEvento

    _mock_qbo(mock_post)
    pedido_id, producto_id, cliente_id = _armar(precio_app=24.80)

    _login(app).post(f'/pedidos/{pedido_id}/precios-factura/aplicar',
                     data={}, follow_redirects=True)

    precio = PrecioClienteProducto.query.filter_by(
        cliente_id=cliente_id, producto_id=producto_id).first()
    assert float(precio.precio_base) == 24.80
    assert PedidoEvento.query.filter_by(tipo='precio_actualizado').count() == 0


@patch('app.N8N_INVOICE_FETCH_WEBHOOK_URL', 'http://n8n.local/fetch')
@patch('app.requests.post')
def test_ignora_producto_que_no_difiere_en_la_factura(mock_post, app):
    """AC 8: el precio se relee de QBO; del form solo se toma qué producto."""
    from app import PrecioClienteProducto, PedidoEvento

    # En QBO el precio coincide con el de la app: no hay nada que aplicar.
    _mock_qbo(mock_post, _factura([
        {'item': QBO_ITEM_ID, 'nombre': 'Smoked Turkey Breast', 'qty': 10, 'precio': 24.80},
    ]))
    pedido_id, producto_id, cliente_id = _armar(precio_app=24.80)

    _login(app).post(f'/pedidos/{pedido_id}/precios-factura/aplicar',
                     data={'aplicar': str(producto_id)}, follow_redirects=True)

    precio = PrecioClienteProducto.query.filter_by(
        cliente_id=cliente_id, producto_id=producto_id).first()
    assert float(precio.precio_base) == 24.80
    assert PedidoEvento.query.filter_by(tipo='precio_actualizado').count() == 0


@patch('app.N8N_INVOICE_FETCH_WEBHOOK_URL', 'http://n8n.local/fetch')
@patch('app.requests.post')
def test_no_toca_la_lista_general_ni_otros_clientes(mock_post, app):
    """AC 7: en precio_producto hay filas con margen 1.2 — escribir ahí infla 20%."""
    from app import Cliente, ListaPrecio, PrecioProducto, PrecioClienteProducto

    _mock_qbo(mock_post)
    pedido_id, producto_id, _ = _armar(precio_app=24.80)

    lista = ListaPrecio(nombre='General', es_default=True, activa=True)
    _db.session.add(lista)
    _db.session.flush()
    en_lista = PrecioProducto(lista_precio_id=lista.id, producto_id=producto_id,
                              precio_base=24.80, margen_jomar=1.2, margen_retail=1.2,
                              activo=True)
    en_lista.calcular_precios()
    otro_cliente = Cliente(nombre='Otro', territorio_id=1, qbo_id='9999')
    _db.session.add_all([en_lista, otro_cliente])
    _db.session.flush()
    precio_otro = PrecioClienteProducto(cliente_id=otro_cliente.id, producto_id=producto_id,
                                        precio_base=24.80, margen_jomar=1.0,
                                        margen_retail=1.2, activo=True)
    precio_otro.calcular_precios()
    _db.session.add(precio_otro)
    _db.session.commit()

    _login(app).post(f'/pedidos/{pedido_id}/precios-factura/aplicar',
                     data={'aplicar': str(producto_id)}, follow_redirects=True)

    assert float(PrecioProducto.query.get(en_lista.id).precio_base) == 24.80
    assert float(PrecioClienteProducto.query.get(precio_otro.id).precio_base) == 24.80


# ──────────────────────────── Guardas y errores ──────────────────────────────

def test_404_sin_invoice_id(app):
    """AC 12."""
    from app import Pedido

    pedido_id, _, _ = _armar()
    Pedido.query.get(pedido_id).invoice_id_qbo = None
    _db.session.commit()

    assert _login(app).get(f'/pedidos/{pedido_id}/precios-factura').status_code == 404


@patch('app.N8N_INVOICE_FETCH_WEBHOOK_URL', 'http://n8n.local/fetch')
@patch('app.requests.post')
def test_502_si_qbo_devuelve_otra_factura(mock_post, app):
    """AC 13: sin esta guarda se compararían precios de otra factura."""
    payload = _factura()
    payload['Invoice']['Id'] = '99999'
    _mock_qbo(mock_post, payload)
    pedido_id, _, _ = _armar()

    assert _login(app).get(f'/pedidos/{pedido_id}/precios-factura').status_code == 502


@patch('app.N8N_INVOICE_FETCH_WEBHOOK_URL', 'http://n8n.local/fetch')
@patch('app.requests.post')
def test_502_si_n8n_falla(mock_post, app):
    """AC 14."""
    mock_post.side_effect = Exception('n8n caído')
    pedido_id, _, _ = _armar()

    assert _login(app).get(f'/pedidos/{pedido_id}/precios-factura').status_code == 502


@patch('app.N8N_INVOICE_FETCH_WEBHOOK_URL', 'http://n8n.local/fetch')
@patch('app.requests.post')
def test_vendedor_ajeno_no_puede_ver_ni_aplicar(mock_post, app):
    """AC 15: escribir precios de un cliente ajeno es peor que solo verlos."""
    from app import Rol, Vendedor

    _mock_qbo(mock_post)
    pedido_id, producto_id, _ = _armar()

    rol_vend = Rol(nombre='vendedor', descripcion='Vendedor')
    _db.session.add(rol_vend)
    _db.session.flush()
    ajeno = Vendedor(username='ajeno', email='x@t.com', nombre_completo='Ajeno',
                     rol_id=rol_vend.id, territorio_id=1, activo=True)
    ajeno.set_password('pw')
    _db.session.add(ajeno)
    _db.session.commit()

    client = _login(app, 'ajeno', 'pw')

    ver = client.get(f'/pedidos/{pedido_id}/precios-factura', follow_redirects=False)
    aplicar = client.post(f'/pedidos/{pedido_id}/precios-factura/aplicar',
                          data={'aplicar': str(producto_id)}, follow_redirects=False)

    assert ver.status_code in (302, 403)
    assert aplicar.status_code in (302, 403)


@patch('app.N8N_INVOICE_FETCH_WEBHOOK_URL', 'http://n8n.local/fetch')
@patch('app.requests.post')
def test_botones_solo_con_factura(mock_post, app):
    """AC 16."""
    from app import Pedido

    _mock_qbo(mock_post)
    pedido_id, _, _ = _armar()
    client = _login(app)

    assert 'Revisar precios' in client.get(f'/pedidos/{pedido_id}/detalles').data.decode()

    Pedido.query.get(pedido_id).invoice_id_qbo = None
    _db.session.commit()
    assert 'Revisar precios' not in client.get(f'/pedidos/{pedido_id}/detalles').data.decode()


# ─────────── El pedido cobrado distinto de la lista (caso pedido 1270) ────────

@patch('app.N8N_INVOICE_FETCH_WEBHOOK_URL', 'http://n8n.local/fetch')
@patch('app.requests.post')
def test_avisa_cuando_el_pedido_se_cobro_distinto_de_la_lista(mock_post, app):
    """Caso real del pedido 1270: la lista tenía 13,00, QBO facturó 13,00, pero
    el pedido se cargó a 14,00 (precio de la lista default). No hay nada que
    actualizar, pero decir 'coinciden' tapaba que la factura sí difería."""
    _mock_qbo(mock_post, _factura([
        {'item': QBO_ITEM_ID, 'nombre': 'Smoked Turkey Breast', 'qty': 2, 'precio': 13.00},
    ]))
    pedido_id, _, _ = _armar(precio_app=13.00, precio_facturado=14.00)

    html = _login(app).get(f'/pedidos/{pedido_id}/precios-factura').data.decode()

    assert 'El pedido se cobró distinto' in html
    assert 'se facturó a 14.00' in html
    assert 'coinciden con los de la app' not in html
    # No es algo que se actualice: la lista ya está bien
    assert 'name="aplicar"' not in html


# ──────────── El precio del formulario no le gana a la jerarquía ─────────────

def test_precio_del_form_no_pisa_el_precio_del_cliente(app):
    """Origen del pedido 1270: el form se siembra con el precio de la lista
    default y solo lo corrige el JS al elegir cliente. Si ese JS no corre, el
    pedido salía cobrado con el precio equivocado."""
    from app import _resolver_precio_unitario_pedido
    from decimal import Decimal

    _, producto_id, cliente_id = _armar(precio_app=13.00)

    # El formulario manda 14.00 (el de la lista default); gana el del cliente.
    assert _resolver_precio_unitario_pedido(cliente_id, producto_id, '14.00') == Decimal('13')
    assert _resolver_precio_unitario_pedido(cliente_id, producto_id, None) == Decimal('13')
    assert _resolver_precio_unitario_pedido(cliente_id, producto_id, '') == Decimal('13')


def test_precio_cae_a_la_lista_default_si_el_cliente_no_tiene_propio(app):
    from app import _resolver_precio_unitario_pedido, ListaPrecio, PrecioProducto
    from decimal import Decimal

    _, producto_id, cliente_id = _armar(precio_app=None)

    lista = ListaPrecio(nombre='General', es_default=True, activa=True)
    _db.session.add(lista)
    _db.session.flush()
    fila = PrecioProducto(lista_precio_id=lista.id, producto_id=producto_id,
                          precio_base=14.00, margen_jomar=1.0, margen_retail=1.2,
                          activo=True)
    fila.calcular_precios()
    _db.session.add(fila)
    _db.session.commit()

    assert _resolver_precio_unitario_pedido(cliente_id, producto_id, '99.00') == Decimal('14')


def test_el_form_es_el_ultimo_recurso_no_un_override(app):
    """Sin precio en ninguna lista, el del formulario es mejor que un 0 — que
    además borraría el precio de un pedido que ya lo tenía al editarlo."""
    from app import _resolver_precio_unitario_pedido
    from decimal import Decimal

    _, producto_id, cliente_id = _armar(precio_app=None)

    assert _resolver_precio_unitario_pedido(cliente_id, producto_id, '25.00') == Decimal('25.00')
    assert _resolver_precio_unitario_pedido(cliente_id, producto_id, None) == Decimal('0')
