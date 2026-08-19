# tests/test_pedido_form_fixes.py
"""Regresiones de la revisión del form de pedidos (2026-08-18).

Cada test reproduce un hallazgo de la revisión end-to-end del flujo de nuevo
pedido: sync de líneas de preparación al editar, tope 9999 en líneas
fusionadas, tipo_cambio resuelto en el servidor, redirects de error que
pierden estado, jerarquía de precios unificada y N+1 del paso 2.
"""
import json
import os
import re
import pytest
from datetime import datetime, timedelta
from decimal import Decimal

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
        _db.session.add(Cliente(nombre='Hotel Dolar', territorio_id=territorio.id,
                                moneda='USD'))

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


def _crear_pedido_por_post(logged_client, cliente_id, producto_id, cajas='2',
                           precio='20.00'):
    resp = logged_client.post('/pedidos/nuevo', data={
        'cliente_id': cliente_id, 'notas': '',
        'productos[0][id]': producto_id,
        'productos[0][cajas]': cajas,
        'productos[0][precio]': precio,
    }, follow_redirects=True)
    assert resp.status_code == 200
    from app import Pedido
    return Pedido.query.order_by(Pedido.id.desc()).first().id


def _editar_por_post(logged_client, pedido_id, cliente_id, producto_id,
                     cajas='2', precio='20.00', follow=True, extra=None):
    data = {
        'cliente_id': cliente_id, 'notas': '',
        'productos[0][id]': producto_id,
        'productos[0][cajas]': cajas,
        'productos[0][precio]': precio,
    }
    if extra:
        data.update(extra)
    return logged_client.post(f'/pedidos/{pedido_id}/editar', data=data,
                              follow_redirects=follow)


def _crear_pedido(cliente_id, lineas, dias_atras=0):
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
    _db.session.commit()
    return pedido


def _seed_lineas(html):
    marca = 'const productos_pedido = '
    inicio = html.index(marca) + len(marca)
    fin = html.index('\n', inicio)
    return json.loads(html[inicio:fin].rstrip().rstrip(';'))


# ── Jerarquía de precios: helper único y versión bulk ──────────────────────

def _armar_escenario_precios():
    """4 productos, uno por cada camino de la jerarquía:
    específico / lista asignada / lista default / sin precio."""
    from app import (Cliente, ListaPrecio, PrecioProducto, ClienteListaPrecio,
                     PrecioClienteProducto)
    cliente_id, prods = _ids()
    chuleta = prods['Chuleta de cerdo ahumada 5 kg']
    salchicha = prods['Salchicha Frankfurter 2.5 kg']
    ham = prods['Ham di Pasku 4 kg']
    # Aceite queda sin precio en ninguna lista.

    _db.session.add(PrecioClienteProducto(
        cliente_id=cliente_id, producto_id=chuleta, precio_base=99.55))

    asignada = ListaPrecio(nombre='Mayorista')
    default = ListaPrecio(nombre='General', es_default=True)
    _db.session.add_all([asignada, default])
    _db.session.flush()
    _db.session.add(PrecioProducto(
        lista_precio_id=asignada.id, producto_id=salchicha, precio_base=55.10))
    _db.session.add(PrecioProducto(
        lista_precio_id=default.id, producto_id=ham, precio_base=12.34))
    # La default también tiene chuleta y salchicha, para probar que las capas
    # de arriba le ganan.
    _db.session.add(PrecioProducto(
        lista_precio_id=default.id, producto_id=chuleta, precio_base=1.11))
    _db.session.add(PrecioProducto(
        lista_precio_id=default.id, producto_id=salchicha, precio_base=2.22))
    _db.session.add(ClienteListaPrecio(
        cliente_id=cliente_id, lista_precio_id=asignada.id))
    _db.session.commit()
    return cliente_id, {'especifico': chuleta, 'lista': salchicha,
                        'default': ham, 'sin_precio': prods['Aceite vegetal 12 x 1 L']}


def test_precio_vigente_coincide_con_el_par_de_resolutores(app):
    from app import (_precio_vigente, obtener_precio_producto_cliente,
                     obtener_precio_default_producto)
    cliente_id, casos = _armar_escenario_precios()

    esperados = {'especifico': 99.55, 'lista': 55.10, 'default': 12.34,
                 'sin_precio': None}
    for caso, producto_id in casos.items():
        par = obtener_precio_producto_cliente(cliente_id, producto_id, 'base')
        if par is None:
            par = obtener_precio_default_producto(producto_id, 'base')
        assert _precio_vigente(cliente_id, producto_id) == par == esperados[caso], caso


def test_precios_bulk_coincide_con_el_resolutor(app):
    from app import _precio_vigente, _precios_vigentes_para_cliente
    cliente_id, casos = _armar_escenario_precios()
    ids = list(casos.values())

    bulk = _precios_vigentes_para_cliente(cliente_id, ids)
    assert bulk == {pid: _precio_vigente(cliente_id, pid) for pid in ids}


def test_paso2_no_escala_queries_con_el_catalogo(app, logged_client):
    """El render del paso 2 debe hacer un número de queries acotado, no
    proporcional al catálogo (el N+1 hacía 3-5 queries por producto)."""
    from sqlalchemy import event
    from app import Producto
    cliente_id, prods = _ids()
    for n in range(26):
        _db.session.add(Producto(
            nombre=f'Importado bulk {n:02d}', descripcion='x',
            temperatura='Congelado', se_pesa=False, tax_rate=10.0,
        ))
    _db.session.commit()
    _crear_pedido(cliente_id, [(prods['Aceite vegetal 12 x 1 L'], 3)], dias_atras=7)
    _crear_pedido(cliente_id, [(prods['Aceite vegetal 12 x 1 L'], 3)], dias_atras=3)

    consultas = []

    def _contar(conn, cursor, statement, parameters, context, executemany):
        if statement.lstrip().upper().startswith('SELECT'):
            consultas.append(statement)

    engine = _db.session.get_bind()
    event.listen(engine, 'before_cursor_execute', _contar)
    try:
        resp = logged_client.get(
            f'/pedidos/nuevo?cliente={cliente_id}&grupo=importado:10')
        assert resp.status_code == 200
    finally:
        event.remove(engine, 'before_cursor_execute', _contar)

    assert len(consultas) <= 25, (
        f'{len(consultas)} SELECTs para renderizar el paso 2 con 30 productos'
    )


# ── Tope 9999 y producto inexistente ───────────────────────────────────────

def test_lineas_fusionadas_respetan_el_tope_de_cajas(app, logged_client):
    from app import Pedido
    cliente_id, prods = _ids()
    aceite = prods['Aceite vegetal 12 x 1 L']

    resp = logged_client.post('/pedidos/nuevo', data={
        'cliente_id': cliente_id, 'notas': '',
        'productos[0][id]': aceite, 'productos[0][cajas]': '5000',
        'productos[0][precio]': '20.00',
        'productos[1][id]': aceite, 'productos[1][cajas]': '5000',
        'productos[1][precio]': '20.00',
    }, follow_redirects=True)

    assert resp.status_code == 200
    assert '9999' in resp.get_data(as_text=True)
    assert Pedido.query.count() == 0


def test_producto_inexistente_no_deja_pedido_huerfano(app, logged_client):
    from app import Pedido
    cliente_id, _ = _ids()

    resp = logged_client.post('/pedidos/nuevo', data={
        'cliente_id': cliente_id, 'notas': '',
        'productos[0][id]': '99999', 'productos[0][cajas]': '2',
        'productos[0][precio]': '20.00',
    }, follow_redirects=True)

    assert resp.status_code == 200
    assert 'ya no existe' in resp.get_data(as_text=True)
    assert Pedido.query.count() == 0


# ── Líneas de preparación: sync al editar y paridad de subtotal ────────────

def test_editar_resincroniza_cajas_de_prep_no_capturada(app, logged_client):
    from app import DetallePedido
    cliente_id, prods = _ids()
    aceite = prods['Aceite vegetal 12 x 1 L']
    pid = _crear_pedido_por_post(logged_client, cliente_id, aceite, cajas='5')

    resp = _editar_por_post(logged_client, pid, cliente_id, aceite, cajas='8')
    assert resp.status_code == 200

    prep = DetallePedido.query.filter_by(
        pedido_id=pid, producto_id=aceite, es_linea_pedido=False).one()
    orig = DetallePedido.query.filter_by(
        pedido_id=pid, producto_id=aceite, es_linea_pedido=True).one()
    assert orig.cajas == 8
    assert prep.cajas == 8, 'la prep sin capturar debe seguir a la línea original'
    assert prep.subtotal == orig.subtotal


def test_editar_preserva_prep_ya_capturada(app, logged_client):
    """Una prep que almacén ya tocó (peso/lote/fechas) conserva su cantidad:
    lo preparado es lo que se factura. Solo se re-precia."""
    from app import DetallePedido
    cliente_id, prods = _ids()
    aceite = prods['Aceite vegetal 12 x 1 L']
    pid = _crear_pedido_por_post(logged_client, cliente_id, aceite, cajas='5')

    prep = DetallePedido.query.filter_by(
        pedido_id=pid, producto_id=aceite, es_linea_pedido=False).one()
    prep.lote = 'LOTE-77'
    prep.peso = 12.5
    _db.session.commit()

    resp = _editar_por_post(logged_client, pid, cliente_id, aceite, cajas='8')
    assert resp.status_code == 200

    prep = DetallePedido.query.filter_by(
        pedido_id=pid, producto_id=aceite, es_linea_pedido=False).one()
    assert prep.cajas == 5
    assert prep.lote == 'LOTE-77'
    # subtotal = precio × peso capturado (12.5), no × cajas.
    assert prep.subtotal == Decimal('20.00') * Decimal('12.5')


def test_sincronizar_prep_copia_el_subtotal_decimal_exacto(app):
    """La prep debe COPIAR el subtotal Decimal de la línea, no recomputarlo
    con float redondeado (el alta usaba round(float(...), 2) y divergía en
    centavos de la copia Decimal de la edición; en Postgres, Numeric(10,2)
    cuantiza distinto cada camino: 13.35 × 0.5 → 6.67 vs 6.68)."""
    from app import _sincronizar_lineas_prep, DetallePedido, Producto
    cliente_id, prods = _ids()
    aceite = prods['Aceite vegetal 12 x 1 L']
    pedido = _crear_pedido(cliente_id, [(aceite, 0.5)])

    linea = {
        'producto_id': aceite, 'cajas': 0.5,
        'precio_unitario': Decimal('13.35'),
        'subtotal': Decimal('13.35') * Decimal('0.5'),   # 6.675 exacto
    }
    _sincronizar_lineas_prep(
        pedido, [linea], {aceite: _db.session.get(Producto, aceite)})

    prep = [obj for obj in _db.session.new
            if isinstance(obj, DetallePedido) and not obj.es_linea_pedido]
    assert len(prep) == 1
    assert prep[0].subtotal == Decimal('6.675')   # el Decimal exacto, sin round float
    assert prep[0].cajas == 0.5


# ── tipo_cambio server-side ────────────────────────────────────────────────

def test_nuevo_pedido_usd_fija_tipo_cambio_en_el_servidor(app, logged_client):
    from app import Cliente, Pedido
    usd = Cliente.query.filter_by(nombre='Hotel Dolar').first()
    _, prods = _ids()

    resp = logged_client.post('/pedidos/nuevo', data={
        'cliente_id': usd.id, 'notas': '',
        'productos[0][id]': prods['Aceite vegetal 12 x 1 L'],
        'productos[0][cajas]': '2',
        'productos[0][precio]': '20.00',
        # Sin campo tipo_cambio: el servidor lo resuelve por la moneda.
    }, follow_redirects=True)
    assert resp.status_code == 200
    assert Pedido.query.one().tipo_cambio == 1.78


def test_nuevo_pedido_ignora_tipo_cambio_del_form(app, logged_client):
    from app import Cliente, Pedido
    usd = Cliente.query.filter_by(nombre='Hotel Dolar').first()
    _, prods = _ids()

    logged_client.post('/pedidos/nuevo', data={
        'cliente_id': usd.id, 'notas': '',
        'productos[0][id]': prods['Aceite vegetal 12 x 1 L'],
        'productos[0][cajas]': '2',
        'productos[0][precio]': '20.00',
        'tipo_cambio': '5.0',   # manipulado: no debe ganarle a la moneda
    }, follow_redirects=True)
    assert Pedido.query.one().tipo_cambio == 1.78


def test_editar_reasignando_cliente_actualiza_tipo_cambio(app, logged_client):
    from app import Cliente, Pedido
    cliente_id, prods = _ids()
    usd = Cliente.query.filter_by(nombre='Hotel Dolar').first()
    aceite = prods['Aceite vegetal 12 x 1 L']
    pid = _crear_pedido_por_post(logged_client, cliente_id, aceite)
    assert _db.session.get(Pedido, pid).tipo_cambio == 1.0

    _editar_por_post(logged_client, pid, usd.id, aceite)
    assert _db.session.get(Pedido, pid).tipo_cambio == 1.78


def test_editar_sin_cambiar_cliente_no_toca_tipo_cambio(app, logged_client):
    """Los pedidos históricos con rates raros (expediente XCG a 1.78) no se
    reescriben por una edición cualquiera: el rate solo cambia con el cliente."""
    from app import Pedido
    cliente_id, prods = _ids()
    aceite = prods['Aceite vegetal 12 x 1 L']
    pid = _crear_pedido_por_post(logged_client, cliente_id, aceite)
    pedido = _db.session.get(Pedido, pid)
    pedido.tipo_cambio = 1.78   # rate histórico anómalo en un cliente XCG
    _db.session.commit()

    _editar_por_post(logged_client, pid, cliente_id, aceite, cajas='3')
    assert _db.session.get(Pedido, pid).tipo_cambio == 1.78


# ── Redirects de error que preservan estado ────────────────────────────────

def test_error_al_editar_conserva_el_cliente_destino(app, logged_client):
    from app import Cliente
    cliente_id, prods = _ids()
    otro = Cliente.query.filter_by(nombre='Cliente Nuevo').first()
    aceite = prods['Aceite vegetal 12 x 1 L']
    pid = _crear_pedido_por_post(logged_client, cliente_id, aceite)

    resp = _editar_por_post(logged_client, pid, otro.id, aceite,
                            cajas='no-es-numero', follow=False)
    assert resp.status_code in (302, 303)
    assert f'cliente={otro.id}' in resp.headers['Location']


def test_error_en_nuevo_conserva_el_grupo(app, logged_client):
    cliente_id, prods = _ids()

    resp = logged_client.post('/pedidos/nuevo', data={
        'cliente_id': cliente_id, 'notas': '',
        'grupo': 'pesable:10',
        'productos[0][id]': prods['Chuleta de cerdo ahumada 5 kg'],
        'productos[0][cajas]': 'no-es-numero',
        'productos[0][precio]': '20.00',
    }, follow_redirects=False)
    assert resp.status_code in (302, 303)
    location = resp.headers['Location']
    assert f'cliente={cliente_id}' in location
    assert 'grupo=pesable' in location.replace('%3A', ':')


def test_paso2_lleva_el_grupo_en_un_hidden(app, logged_client):
    cliente_id, prods = _ids()
    for dias in (14, 7):
        _crear_pedido(cliente_id, [(prods['Chuleta de cerdo ahumada 5 kg'], 3)],
                      dias_atras=dias)
        _crear_pedido(cliente_id, [(prods['Ham di Pasku 4 kg'], 2)],
                      dias_atras=dias - 1)

    html = logged_client.get(
        f'/pedidos/nuevo?cliente={cliente_id}&grupo=pesable:10'
    ).get_data(as_text=True)
    assert re.search(r'name="grupo"[^>]*value="pesable:10"', html.replace("'", '"'))


# ── Auditoría ──────────────────────────────────────────────────────────────

def test_editar_pedido_registra_evento(app, logged_client):
    from app import PedidoEvento
    cliente_id, prods = _ids()
    aceite = prods['Aceite vegetal 12 x 1 L']
    pid = _crear_pedido_por_post(logged_client, cliente_id, aceite)

    resp = _editar_por_post(logged_client, pid, cliente_id, aceite, cajas='3')
    assert resp.status_code == 200
    eventos = PedidoEvento.query.filter_by(pedido_id=pid, tipo='editado').all()
    assert len(eventos) == 1


# ── Grupo nuevo fuera del historial ────────────────────────────────────────

def _cliente_multigrupo(cliente_id, prods):
    for dias in (14, 7):
        _crear_pedido(cliente_id, [(prods['Chuleta de cerdo ahumada 5 kg'], 3)],
                      dias_atras=dias)
        _crear_pedido(cliente_id, [(prods['Ham di Pasku 4 kg'], 2)],
                      dias_atras=dias - 1)







def test_candado_provisional_se_suelta_al_quedarse_sin_lineas(app, logged_client):
    """El candado que NO puso el servidor no puede sobrevivir al pedido vacío.

    Desde que el grupo se elige siempre, el único camino que llega al form sin
    grupo del servidor es la EDICIÓN: ahí lo fija la primera línea del pedido.
    Si se quitan todas, el buscador tiene que volver a ofrecer el catálogo
    entero; antes quedaba acotado al grupo de la línea borrada, sin aviso que
    lo explicara y sin más salida que recargar la página.

    Es lógica de la pantalla: el comportamiento se verificó en el navegador
    (quitar todas las líneas → el catálogo vuelve a estar completo). Acá se
    ancla que las dos piezas sigan en el template.
    """
    cliente_id, prods = _ids()
    pid = _crear_pedido_por_post(logged_client, cliente_id,
                                 prods['Aceite vegetal 12 x 1 L'])
    html = logged_client.get(f'/pedidos/{pid}/editar').get_data(as_text=True)

    # Editando, el servidor no fija grupo: lo deduce la pantalla de las líneas.
    assert 'const grupoDelServidor = "" || null' in html
    assert 'function sincronizarCandadoProvisional' in html
    # Y se recalcula en cada render de las líneas, que es donde se quitan.
    cuerpo = html.split('function actualizarTablaProductos()')[1][:200]
    assert 'sincronizarCandadoProvisional()' in cuerpo


def test_selector_de_grupos_muestra_ultima_vez(app, logged_client):
    cliente_id, prods = _ids()
    _cliente_multigrupo(cliente_id, prods)

    html = logged_client.get(f'/pedidos/nuevo?cliente={cliente_id}').get_data(as_text=True)
    assert 'ltima vez' in html   # «última vez <fecha>» en cada card de grupo


# ── Template: limpieza y precio unitario visible ───────────────────────────

def test_css_de_la_pantalla_hace_valer_hidden(app, logged_client):
    """`hidden` tiene que ocultar de verdad en esta pantalla.

    El atributo solo trae `display:none` de la hoja del navegador, con
    especificidad cero: las reglas propias que fijan `display` (filas de
    cliente en flex, panel de añadir en grid) lo anulaban y nada desaparecía
    — el buscador de clientes marcaba las filas y seguían todas a la vista.
    """
    import re as _re
    from pathlib import Path
    css = Path('static/css/pedido_nuevo.css').read_text()
    assert _re.search(r'\[hidden\]\s*\{[^}]*display:\s*none\s*!important', css), (
        'falta la regla que hace valer [hidden] sobre los display propios'
    )


def test_paso2_sin_hidden_nombre_muerto(app, logged_client):
    cliente_id, prods = _ids()
    _crear_pedido(cliente_id, [(prods['Aceite vegetal 12 x 1 L'], 3)], dias_atras=3)
    html = logged_client.get(
        f'/pedidos/nuevo?cliente={cliente_id}&grupo=importado:10').get_data(as_text=True)
    assert '[nombre]' not in html


def test_editar_linea_sin_precio_no_se_muestra_como_cero(app, logged_client):
    """Un 0 guardado (línea vieja sin precio) viaja como null, no como 0.

    La pantalla dice «sin precio» ante null; con un 0 mostraría «0.00», que se
    lee como gratis — el número que nadie quiere ver junto a un producto.
    """
    from app import DetallePedido
    cliente_id, prods = _ids()
    aceite = prods['Aceite vegetal 12 x 1 L']
    pid = _crear_pedido_por_post(logged_client, cliente_id, aceite, precio='')
    linea = DetallePedido.query.filter_by(
        pedido_id=pid, es_linea_pedido=True).one()
    assert linea.precio_unitario == 0     # sin precio en ninguna lista

    html = logged_client.get(f'/pedidos/{pid}/editar').get_data(as_text=True)
    assert [l['precio'] for l in _seed_lineas(html)] == [None]


def test_paso2_muestra_precio_unitario_en_las_lineas(app, logged_client):
    cliente_id, prods = _ids()
    _crear_pedido(cliente_id, [(prods['Aceite vegetal 12 x 1 L'], 3)], dias_atras=3)
    html = logged_client.get(
        f'/pedidos/nuevo?cliente={cliente_id}&grupo=importado:10').get_data(as_text=True)
    assert 'c/u' in html
