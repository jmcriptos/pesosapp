"""La transición `facturado → entregado`, y su vuelta atrás.

Acá se factura ANTES de que salga el camión —a veces el día anterior—, así que
`facturado` no significa «llegó al cliente». Sin este estado no hay forma de
contestar «¿qué está facturado pero todavía no llegó?». El chofer marca la
entrega desde el teléfono al dejar la mercadería, y por eso la ruta necesita
su propia guarda: no puede reusar `_pedido_es_inmutable` porque es justamente
la que mueve un pedido FUERA de esa regla, de forma controlada.
"""
import json
import os
from datetime import timedelta
from decimal import Decimal

import pytest

os.environ.setdefault('SECRET_KEY', 'test-secret')
os.environ.setdefault('FLASK_ENV', 'testing')
os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')

from app import app as flask_app, db as _db, DASHBOARD_TIMEZONE


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
        _seed()
        yield flask_app
        _db.drop_all()


def _hoy():
    from datetime import datetime
    return datetime.now(DASHBOARD_TIMEZONE).date()


def _seed():
    from app import (Rol, Territorio, Vendedor, Cliente, Producto,
                     Pedido, DetallePedido, ClienteVendedor)

    rol_admin = Rol(nombre='super_admin', descripcion='Admin')
    rol_vend = Rol(nombre='vendedor', descripcion='Vendedor')
    terr = Territorio(nombre='t1', descripcion='T1')
    _db.session.add_all([rol_admin, rol_vend, terr])
    _db.session.flush()

    def mk_vend(u, rol):
        v = Vendedor(username=u, email=f'{u}@t.com', nombre_completo=u,
                     rol_id=rol.id, territorio_id=terr.id, activo=True)
        v.set_password('pw')
        _db.session.add(v)
        return v

    jefe = mk_vend('jefe', rol_admin)
    va = mk_vend('vend_a', rol_vend)
    # No se le asigna el Cliente A: es el vendedor ajeno del test de IDOR.
    vb = mk_vend('vend_b', rol_vend)

    ca = Cliente(nombre='Cliente A', territorio_id=terr.id, qbo_id='QBO-A', moneda='XCG')
    _db.session.add(ca)

    prod = Producto(nombre='Producto X', descripcion='d', temperatura='Seco',
                    se_pesa=False, tax_rate=6.0, qbo_id='QBO-PX')
    prod_pesable = Producto(nombre='Producto Pesable', descripcion='d', temperatura='Frio',
                            se_pesa=True, tax_rate=6.0, qbo_id='QBO-PW')
    _db.session.add_all([prod, prod_pesable])
    _db.session.flush()

    _db.session.add(ClienteVendedor(cliente_id=ca.id, vendedor_id=va.id, activo=True))

    hoy = _hoy()

    def mk_pedido(estado, entrega):
        p = Pedido(cliente_id=ca.id, estado=estado, tipo_cambio=1.0,
                   fecha_entrega=entrega)
        _db.session.add(p)
        _db.session.flush()
        _db.session.add(DetallePedido(
            pedido_id=p.id, producto_id=prod.id, cajas=5, cajas_pedidas=5,
            peso=0, precio_unitario=Decimal('5.00'), subtotal=Decimal('25.00'),
            es_linea_pedido=True))
        _db.session.add(DetallePedido(
            pedido_id=p.id, producto_id=prod_pesable.id, cajas=3, cajas_pedidas=3,
            peso=0, precio_unitario=Decimal('7.00'), subtotal=Decimal('21.00'),
            es_linea_pedido=True))
        return p

    pendiente = mk_pedido('pendiente', hoy)
    preparado = mk_pedido('preparado', hoy)
    facturado = mk_pedido('facturado', hoy)
    entregado_hoy = mk_pedido('entregado', hoy)
    entregado_viejo = mk_pedido('entregado', hoy - timedelta(days=30))
    # Facturado con la entrega VENCIDA (no `hoy`, no `entregado`): es la
    # combinación que agujereaba la pintura de la tarjeta. `_agrupar_tablero`
    # (Task 3) ya lo manda a «Atrasados», pero la tarjeta decidía con su
    # propio `estado == 'facturado'` si iba atenuada como «hecho» y si
    # llevaba la franja roja — las dos veces con la exclusión equivocada.
    facturado_vencido = mk_pedido('facturado', hoy - timedelta(days=5))

    _db.session.commit()
    IDS.update(pendiente=pendiente.id, preparado=preparado.id,
               facturado=facturado.id, entregado_hoy=entregado_hoy.id,
               entregado_viejo=entregado_viejo.id,
               facturado_vencido=facturado_vencido.id)


def _login(app, username):
    """Un solo test_client por test: un segundo cliente hereda la sesión del
    primero y los tests de autorización pasarían en vacío."""
    c = app.test_client()
    c.post('/login', data={'username': username, 'password': 'pw'},
           follow_redirects=True)
    return c


# ── Marcar entregado ────────────────────────────────────────────────────────

def test_un_facturado_se_marca_entregado(app):
    from app import Pedido
    c = _login(app, 'jefe')
    resp = c.post(f'/pedidos/{IDS["facturado"]}/entregar')
    assert resp.status_code == 302
    assert _db.session.get(Pedido, IDS['facturado']).estado == 'entregado'


def test_un_pendiente_no_se_marca_entregado(app):
    """El guarda que protege la factura: si se pudiera, el pedido saldría de la
    cola sin factura y no la generaría nunca."""
    from app import Pedido
    c = _login(app, 'jefe')
    c.post(f'/pedidos/{IDS["pendiente"]}/entregar')
    assert _db.session.get(Pedido, IDS['pendiente']).estado == 'pendiente'


def test_un_preparado_no_se_marca_entregado(app):
    from app import Pedido
    c = _login(app, 'jefe')
    c.post(f'/pedidos/{IDS["preparado"]}/entregar')
    assert _db.session.get(Pedido, IDS['preparado']).estado == 'preparado'


def test_marcar_entregado_deja_rastro_con_la_hora(app):
    from app import PedidoEvento
    c = _login(app, 'jefe')
    c.post(f'/pedidos/{IDS["facturado"]}/entregar')
    ev = PedidoEvento.query.filter_by(
        pedido_id=IDS['facturado'], tipo='entregado').one()
    assert json.loads(ev.meta) == {'anterior': 'facturado', 'nueva': 'entregado'}
    assert ev.created_at is not None


# ── Deshacer ─────────────────────────────────────────────────────────────

def test_deshacer_devuelve_a_facturado(app):
    from app import Pedido
    c = _login(app, 'jefe')
    c.post(f'/pedidos/{IDS["entregado_hoy"]}/entrega/deshacer')
    assert _db.session.get(Pedido, IDS['entregado_hoy']).estado == 'facturado'


def test_deshacer_deja_su_propio_rastro(app):
    from app import PedidoEvento
    c = _login(app, 'jefe')
    c.post(f'/pedidos/{IDS["entregado_hoy"]}/entrega/deshacer')
    assert PedidoEvento.query.filter_by(
        pedido_id=IDS['entregado_hoy'], tipo='entrega_deshecha').count() == 1


def test_deshacer_no_toca_un_facturado(app):
    """No alcanza con que el estado final coincida: la ruta fija
    `estado = 'facturado'` de todas formas, así que sobre un pedido que YA
    está facturado el estado queda igual con o sin guarda. Lo que distingue
    el no-op correcto de la guarda rota es que, sin guarda, además se escribe
    un PedidoEvento `entrega_deshecha` con `meta={'anterior': 'entregado'}`
    que sería FALSO (el estado anterior real era 'facturado') — un evento de
    auditoría que miente es peor que no tenerlo."""
    from app import Pedido, PedidoEvento
    c = _login(app, 'jefe')
    c.post(f'/pedidos/{IDS["facturado"]}/entrega/deshacer')
    assert _db.session.get(Pedido, IDS['facturado']).estado == 'facturado'
    assert PedidoEvento.query.filter_by(
        pedido_id=IDS['facturado'], tipo='entrega_deshecha').count() == 0


# ── Permisos y next ──────────────────────────────────────────────────────

def test_vendedor_ajeno_no_marca_entregado(app):
    from app import Pedido
    c = _login(app, 'vend_b')          # vend_b no ve al Cliente A
    resp = c.post(f'/pedidos/{IDS["facturado"]}/entregar')
    assert resp.status_code in (302, 403)
    assert _db.session.get(Pedido, IDS['facturado']).estado == 'facturado'


def test_vendedor_ajeno_no_deshace_entrega(app):
    """Equivalente de IDOR para /entrega/deshacer: `entregar_pedido` ya tenía
    su guarda cubierta por `test_vendedor_ajeno_no_marca_entregado`, pero
    `deshacer_entrega_pedido` usa la misma guarda de permisos sin ningún test
    que la ejerza — un solo test_client por test, porque un segundo cliente
    hereda la sesión del primero y el test pasaría en vacío."""
    from app import Pedido
    c = _login(app, 'vend_b')          # vend_b no ve al Cliente A
    resp = c.post(f'/pedidos/{IDS["entregado_hoy"]}/entrega/deshacer')
    assert resp.status_code in (302, 403)
    assert _db.session.get(Pedido, IDS['entregado_hoy']).estado == 'entregado'


def test_next_a_otro_host_no_redirige_afuera(app):
    c = _login(app, 'jefe')
    resp = c.post(f'/pedidos/{IDS["facturado"]}/entregar',
                  data={'next': 'https://evil.com/x'})
    assert 'evil.com' not in resp.headers.get('Location', '')


# ── El botón en la tarjeta ───────────────────────────────────────────────
# Copiado (no importado) de tests/test_pedido_mover_entrega.py: recorta el
# bloque de UNA tarjeta buscando `data-href="/pedidos/<id>/detalles"`, porque
# `PED-<id>` aparece varias veces dentro de la misma tarjeta (el id, el
# `sr-only`, cada `aria-label`) y un recorte por ese texto da falsos rojos.
def _tarjeta(html, pedido_id):
    for bloque in html.split('<div class="pedido-card'):
        if f'data-href="/pedidos/{pedido_id}/detalles"' in bloque:
            return bloque
    raise AssertionError(f'no se dibujó la tarjeta de PED-{pedido_id}')


def test_la_tarjeta_de_un_facturado_ofrece_entregar(app):
    c = _login(app, 'jefe')
    tarjeta = _tarjeta(c.get('/pedidos').get_data(as_text=True), IDS['facturado'])
    assert f'/pedidos/{IDS["facturado"]}/entregar' in tarjeta


def test_la_tarjeta_de_un_pendiente_no_ofrece_entregar(app):
    """Todavía no está facturado: la ruta lo rechaza, así que el botón solo
    serviría para hacer rebotar al chofer."""
    c = _login(app, 'jefe')
    tarjeta = _tarjeta(c.get('/pedidos').get_data(as_text=True), IDS['pendiente'])
    assert '/entregar' not in tarjeta


def test_el_entregado_de_hoy_ofrece_deshacer(app):
    c = _login(app, 'jefe')
    tarjeta = _tarjeta(c.get('/pedidos').get_data(as_text=True), IDS['entregado_hoy'])
    assert f'/pedidos/{IDS["entregado_hoy"]}/entrega/deshacer' in tarjeta


def test_el_entregado_del_archivo_no_ofrece_deshacer(app):
    """En el archivo el botón es solo un toque equivocado esperando."""
    c = _login(app, 'jefe')
    html = c.get('/pedidos?estado=entregado').get_data(as_text=True)
    tarjeta = _tarjeta(html, IDS['entregado_viejo'])
    assert '/entrega/deshacer' not in tarjeta


# ── La pintura de la tarjeta (agujero del plan, sumado a esta tarea) ───────
# `_pedidos_tablero.html` y `_pedidos_resultados.html` decidían con su PROPIO
# `estado == 'facturado'` si la tarjeta iba atenuada como "hecho" y si
# llevaba la franja roja de vencido. Con `entregado` como el nuevo terminal,
# un facturado atrasado caía bien en «Atrasados» (Task 3) pero se seguía
# pintando gris, como terminado, y sin la alerta: exactamente la señal falsa
# que todo este trabajo vino a borrar.
def test_el_facturado_atrasado_lleva_la_alerta_de_vencido(app):
    c = _login(app, 'jefe')
    tarjeta = _tarjeta(c.get('/pedidos').get_data(as_text=True), IDS['facturado_vencido'])
    assert 'data-vencido="1"' in tarjeta


def test_el_facturado_atrasado_no_se_pinta_como_hecho(app):
    """`tablero-hecho` atenúa la tarjeta como "esto ya está". Un facturado sin
    entregar NO está: solo lo pinta gris `entregado`."""
    c = _login(app, 'jefe')
    tarjeta = _tarjeta(c.get('/pedidos').get_data(as_text=True), IDS['facturado_vencido'])
    assert 'tablero-hecho' not in tarjeta


def test_el_entregado_de_hoy_se_pinta_como_hecho(app):
    c = _login(app, 'jefe')
    tarjeta = _tarjeta(c.get('/pedidos').get_data(as_text=True), IDS['entregado_hoy'])
    assert 'tablero-hecho' in tarjeta


# ── El detalle deja de mentir ────────────────────────────────────────────
def test_el_detalle_de_un_entregado_llega_al_ultimo_paso(app):
    """Los 973 pedidos se veían como 3 de 4 para siempre porque el 4º paso era
    inalcanzable. `active_map` ya contemplaba `entregado`; faltaba que algún
    pedido llegara ahí."""
    c = _login(app, 'jefe')
    html = c.get(f'/pedidos/{IDS["entregado_hoy"]}/detalles').get_data(as_text=True)
    # El 4º paso es el ACTUAL, y por lo tanto ninguno queda pendiente.
    assert 'detail-stepper-item is-current' in html
    assert 'detail-stepper-item is-pending' not in html, \
        'con el pedido entregado ningún paso del progreso queda gris'
