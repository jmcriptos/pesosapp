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


def _crear_pedido_por_post(logged_client, cliente_id, producto_id, cajas='2', precio='20.00'):
    resp = logged_client.post('/pedidos/nuevo', data={
        'cliente_id': cliente_id, 'notas': '',
        'productos[0][id]': producto_id,
        'productos[0][cajas]': cajas,
        'productos[0][precio]': precio,
    }, follow_redirects=True)
    assert resp.status_code == 200
    from app import Pedido
    return Pedido.query.order_by(Pedido.id.desc()).first().id


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
    assert 'data-paso="cliente"' in html
    assert 'id="form-nuevo-pedido"' not in html   # el paso 1 no trae el form del pedido


def test_paso2_cliente_con_historial_siembra_lineas(app, logged_client):
    cliente_id, prods = _ids()
    chuleta = prods['Chuleta de cerdo ahumada 5 kg']
    _crear_pedido(cliente_id, [(chuleta, 7)], dias_atras=3)

    resp = logged_client.get(f'/pedidos/nuevo?cliente={cliente_id}&grupo=pesable:10')
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert 'id="form-nuevo-pedido"' in html
    assert 'Chuleta de cerdo ahumada 5 kg' in html
    assert '"habitual": 7' in html or '"habitual":7' in html
    # El cliente ya no se elige acá: viene fijado desde el paso 1 y viaja en un
    # hidden. (Antes de la Task 3 esto era un <option ... selected>.)
    assert f'name="cliente_id" value="{cliente_id}"' in html.replace("'", '"')


def test_paso2_orden_de_secciones(app, logged_client):
    cliente_id, prods = _ids()
    _crear_pedido(cliente_id, [(prods['Chuleta de cerdo ahumada 5 kg'], 7)], dias_atras=3)
    html = logged_client.get(
        f'/pedidos/nuevo?cliente={cliente_id}&grupo=pesable:10').get_data(as_text=True)

    i_head = html.index('id="ph-cliente-head"')
    i_lineas = html.index('id="productos-body"')
    i_add = html.index('id="ph-add-toggle"')
    i_entrega = html.index('id="ph-entrega-chips"')
    i_notas = html.index('id="notas"')
    assert i_head < i_lineas < i_add < i_entrega < i_notas

    assert '<select name="cliente_id"' not in html          # ya no hay select de cliente
    assert f'name="cliente_id" value="{cliente_id}"' in html.replace("'", '"')
    assert '/api/precios/cliente' not in html               # sin fetch de precios
    assert '/api/clientes' not in html                      # sin fetch de habitual
    # OJO: no usar 'pedido-habitual' como token — el body lleva
    # data-pedido-habitual="1" y el CSS pedido_habitual.css, que se quedan.


def test_paso2_sin_historial_abre_panel(app, logged_client):
    from app import Cliente
    nuevo = Cliente.query.filter_by(nombre='Cliente Nuevo').first()
    html = logged_client.get(
        f'/pedidos/nuevo?cliente={nuevo.id}&grupo=pesable:10').get_data(as_text=True)
    assert 'Sin pedidos anteriores' in html
    assert 'id="ph-add-panel"' in html
    # El panel arranca abierto: `hidden` no está en su tag de apertura. Se mira
    # el tag ENTERO (no solo lo que va antes del id) porque el atributo se
    # renderiza después del id y buscarlo a medias no probaría nada.
    panel_tag = re.search(r'<div[^>]*id="ph-add-panel"[^>]*>', html).group(0)
    assert 'hidden' not in panel_tag


def test_paso2_multigrupo_sin_grupo_repregunta(app, logged_client):
    cliente_id, prods = _ids()
    _crear_pedido(cliente_id, [(prods['Chuleta de cerdo ahumada 5 kg'], 3)], dias_atras=7)
    _crear_pedido(cliente_id, [(prods['Ham di Pasku 4 kg'], 2)], dias_atras=3)

    resp = logged_client.get(f'/pedidos/nuevo?cliente={cliente_id}')
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert 'data-paso="cliente"' in html
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

    html = logged_client.get(
        f'/pedidos/nuevo?cliente={cliente_id}&grupo=pesable:10').get_data(as_text=True)
    assert '99.55' in html


# ── Edición: cambiar de cliente por round-trip re-cotizado ─────────────────

def test_editar_muestra_cambiar_y_sin_select(app, logged_client):
    cliente_id, prods = _ids()
    pid = _crear_pedido_por_post(logged_client, cliente_id, prods['Aceite vegetal 12 x 1 L'])
    html = logged_client.get(f'/pedidos/{pid}/editar').get_data(as_text=True)
    assert 'id="ph-cambiar-cliente"' in html
    assert '<select name="cliente_id"' not in html
    assert 'cambiar=1' in html


def test_editar_cambiar_muestra_paso1(app, logged_client):
    cliente_id, prods = _ids()
    pid = _crear_pedido_por_post(logged_client, cliente_id, prods['Aceite vegetal 12 x 1 L'])
    html = logged_client.get(f'/pedidos/{pid}/editar?cambiar=1').get_data(as_text=True)
    assert 'data-paso="cliente"' in html
    assert f'/pedidos/{pid}/editar' in html   # destino apunta de vuelta a la edición


def test_editar_con_cliente_recotiza(app, logged_client):
    from app import Cliente, PrecioClienteProducto
    cliente_id, prods = _ids()
    otro = Cliente.query.filter_by(nombre='Cliente Nuevo').first()
    pid_prod = prods['Aceite vegetal 12 x 1 L']
    _db.session.add(PrecioClienteProducto(
        cliente_id=otro.id, producto_id=pid_prod, precio_base=33.44))
    _db.session.commit()

    pid = _crear_pedido_por_post(logged_client, cliente_id, pid_prod)
    html = logged_client.get(f'/pedidos/{pid}/editar?cliente={otro.id}').get_data(as_text=True)
    assert f'name="cliente_id" value="{otro.id}"' in html.replace("'", '"')
    assert '33.44' in html                       # línea re-cotizada para el cliente nuevo
    # El catálogo entero también trae 33.44, así que el assert de arriba no
    # prueba que la LÍNEA se re-cotizó: eso se mira en las líneas sembradas.
    assert [l['precio'] for l in _seed_lineas(html)] == [33.44]
    # Nada se guardó: el cambio de cliente recién viaja con «Actualizar pedido».
    from app import Pedido
    assert _db.session.get(Pedido, pid).cliente_id == cliente_id
    assert 'Precios re-cotizados para este cliente' in html


def test_editar_sin_cliente_muestra_jerarquia_no_avisa(app, logged_client):
    """Sin `?cliente` no hay aviso, pero el precio ya sale de la jerarquía.

    Al guardar, `_resolver_precio_unitario_pedido` resuelve por jerarquía sí o
    sí: mostrar el precio viejo haría que el pedido se guardara por un número
    distinto del que el vendedor vio. Sin precio en ninguna lista, cae al
    guardado (mismo último recurso que el POST).
    """
    from app import PrecioClienteProducto
    cliente_id, prods = _ids()
    pid_prod = prods['Aceite vegetal 12 x 1 L']
    pid = _crear_pedido_por_post(logged_client, cliente_id, pid_prod, precio='20.00')

    # Sin precio configurado: el guardado es el que se ve.
    html = logged_client.get(f'/pedidos/{pid}/editar').get_data(as_text=True)
    assert [l['precio'] for l in _seed_lineas(html)] == [20.0]
    assert 'Precios re-cotizados para este cliente' not in html

    _db.session.add(PrecioClienteProducto(
        cliente_id=cliente_id, producto_id=pid_prod, precio_base=77.77))
    _db.session.commit()

    html = logged_client.get(f'/pedidos/{pid}/editar').get_data(as_text=True)
    assert [l['precio'] for l in _seed_lineas(html)] == [77.77]
    assert 'Precios re-cotizados para este cliente' not in html   # mismo cliente


def _cliente_vendedor_logueado(app, username='vend'):
    """Vendedor (rol no super_admin) que solo ve 'Van den Tweel', ya logueado.

    OJO: no combinar con `logged_client`. Flask-Login cachea el usuario en `g`,
    y el `app_context` del fixture es UNO solo para todo el test: si otro
    cliente ya se logueó, el `/login` de este devuelve el redirect de «ya
    estás autenticado» y las peticiones siguen corriendo como el primero.
    """
    from app import Rol, Territorio, Vendedor, ClienteVendedor
    cliente_id, _ = _ids()

    rol_vend = Rol.query.filter_by(nombre='vendedor').first()
    if rol_vend is None:
        rol_vend = Rol(nombre='vendedor', descripcion='Vendedor')
        _db.session.add(rol_vend)
        _db.session.flush()
    vend = Vendedor(
        username=username, email=f'{username}@test.com',
        nombre_completo='Vendedor Test',
        rol_id=rol_vend.id, territorio_id=Territorio.query.first().id, activo=True,
    )
    vend.set_password('pw')
    _db.session.add(vend)
    _db.session.flush()
    # Solo tiene asignado el cliente del pedido; «Cliente Nuevo» le es ajeno.
    _db.session.add(ClienteVendedor(
        cliente_id=cliente_id, vendedor_id=vend.id, activo=True))
    _db.session.commit()

    c = app.test_client()
    resp = c.post('/login', data={'username': username, 'password': 'pw'},
                  follow_redirects=True)
    assert resp.status_code == 200
    return c


def test_editar_con_cliente_prohibido_mantiene_original(app):
    """Paridad con el POST: si el vendedor no puede crear pedidos para ese
    cliente, tampoco puede re-cotizar contra él desde la barra de direcciones."""
    from app import Cliente
    cliente_id, prods = _ids()
    otro = Cliente.query.filter_by(nombre='Cliente Nuevo').first()
    pedido = _crear_pedido(cliente_id, [(prods['Aceite vegetal 12 x 1 L'], 2)])

    c = _cliente_vendedor_logueado(app)
    html = c.get(f'/pedidos/{pedido.id}/editar?cliente={otro.id}').get_data(as_text=True)
    assert 'id="form-nuevo-pedido"' in html          # no lo echó de la pantalla
    assert f'name="cliente_id" value="{cliente_id}"' in html.replace("'", '"')
    assert f'name="cliente_id" value="{otro.id}"' not in html.replace("'", '"')
    assert 'se mantiene el original' in html


def test_editar_cambiar_solo_ofrece_clientes_visibles(app):
    """El paso 1 de la edición respeta la visibilidad del vendedor."""
    from app import Cliente
    cliente_id, prods = _ids()
    otro = Cliente.query.filter_by(nombre='Cliente Nuevo').first()
    pedido = _crear_pedido(cliente_id, [(prods['Aceite vegetal 12 x 1 L'], 2)])

    c = _cliente_vendedor_logueado(app, username='vend2')
    html = c.get(f'/pedidos/{pedido.id}/editar?cambiar=1').get_data(as_text=True)
    assert 'data-paso="cliente"' in html
    # El paso 1 lista los clientes como filas enlazadas al destino.
    assert f'?cliente={cliente_id}"' in html
    assert f'?cliente={otro.id}"' not in html
    assert otro.nombre not in html


def test_paso2_vendedor_regular_no_ve_catalogo_de_cliente_ajeno(app):
    """IDOR: un vendedor regular no debe poder leer el catálogo/precios de un
    cliente que no tiene asignado pidiendo el paso 2 directo por la URL."""
    from app import Cliente
    otro = Cliente.query.filter_by(nombre='Cliente Nuevo').first()

    c = _cliente_vendedor_logueado(app)
    resp = c.get(f'/pedidos/nuevo?cliente={otro.id}', follow_redirects=True)
    assert resp.status_code == 200
    assert resp.history and resp.history[0].status_code in (302, 303)

    html = resp.get_data(as_text=True)
    assert 'id="form-nuevo-pedido"' not in html    # no lo dejó entrar al paso 2
    assert 'Cliente no válido para este vendedor' in html
    assert otro.nombre not in html                 # ni el nombre del cliente ajeno se filtra


def test_html_autenticado_no_se_cachea(app, logged_client):
    """El HTML de páginas autenticadas embebe precios por cliente: no debe
    quedar en el cache HTTP del navegador/PWA (iOS lo reutiliza incluso tras
    cerrar la app, sirviendo formularios viejos)."""
    resp = logged_client.get('/pedidos/nuevo')
    assert 'no-store' in resp.headers.get('Cache-Control', '')
