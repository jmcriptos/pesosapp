"""Mover la fecha de entrega de un pedido desde la tarjeta, sin editarlo entero.

El tablero de `/pedidos` agrupa por `fecha_entrega`, pero hasta ahora la única
forma de cambiarla era el formulario de edición de 4 pasos (que además vuelve a
cotizar precios). Como en el día a día los pedidos se corren de fecha varias
veces, las fechas envejecían y el tablero dejaba de decir la verdad.
"""
import json
import os
from datetime import date, timedelta
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
    va, vb = mk_vend('vend_a', rol_vend), mk_vend('vend_b', rol_vend)

    ca = Cliente(nombre='Cliente A', territorio_id=terr.id, qbo_id='QBO-A', moneda='XCG')
    cb = Cliente(nombre='Cliente B', territorio_id=terr.id, qbo_id='QBO-B', moneda='XCG')
    _db.session.add_all([ca, cb])

    prod = Producto(nombre='Producto X', descripcion='d', temperatura='Seco',
                    se_pesa=False, tax_rate=6.0, qbo_id='QBO-PX')
    _db.session.add(prod)
    _db.session.flush()

    _db.session.add_all([
        ClienteVendedor(cliente_id=ca.id, vendedor_id=va.id, activo=True),
        ClienteVendedor(cliente_id=cb.id, vendedor_id=vb.id, activo=True),
    ])

    hoy = _hoy()

    def mk_pedido(cliente, estado, entrega):
        p = Pedido(cliente_id=cliente.id, estado=estado, tipo_cambio=1.0,
                   fecha_entrega=entrega)
        _db.session.add(p)
        _db.session.flush()
        _db.session.add(DetallePedido(
            pedido_id=p.id, producto_id=prod.id, cajas=5, cajas_pedidas=5,
            peso=0, precio_unitario=Decimal('5.00'), subtotal=Decimal('25.00'),
            es_linea_pedido=True))
        return p

    # Atrasado tres días: el caso que se arrastra al día de hoy.
    atrasado = mk_pedido(ca, 'pendiente', hoy - timedelta(days=3))
    # Ya es de hoy: no debe ofrecer el botón «Hoy».
    de_hoy = mk_pedido(ca, 'pendiente', hoy)
    # Facturado: el trabajo cerró, no se le mueve el día.
    facturado = mk_pedido(ca, 'facturado', hoy - timedelta(days=2))
    # De otro cliente, para el test de IDOR.
    ajeno = mk_pedido(cb, 'pendiente', hoy + timedelta(days=4))

    _db.session.commit()
    IDS.update(atrasado=atrasado.id, de_hoy=de_hoy.id,
               facturado=facturado.id, ajeno=ajeno.id)


def _login(app, username):
    """Un solo test_client por test: un segundo cliente hereda la sesión del
    primero y los tests de autorización pasarían en vacío."""
    c = app.test_client()
    c.post('/login', data={'username': username, 'password': 'pw'},
           follow_redirects=True)
    return c


def _tarjeta(html, pedido_id):
    """El bloque HTML de UNA tarjeta.

    Recortar por `PED-{id}` no sirve: ese texto aparece varias veces dentro de
    la misma tarjeta (el id, el `sr-only`, cada `aria-label`), así que el corte
    caía a mitad de camino y el test daba un falso rojo.
    """
    for bloque in html.split('<div class="pedido-card'):
        if f'data-href="/pedidos/{pedido_id}/detalles"' in bloque:
            return bloque
    raise AssertionError(f'no se dibujó la tarjeta de PED-{pedido_id}')


def _entrega_de(pedido_id):
    from app import Pedido
    return _db.session.get(Pedido, pedido_id).fecha_entrega


# ── Mover la fecha ─────────────────────────────────────────────────────────

def test_mover_a_hoy_trae_el_pedido_atrasado_al_dia(app):
    c = _login(app, 'jefe')
    resp = c.post(f'/pedidos/{IDS["atrasado"]}/entrega', data={'fecha': 'hoy'})
    assert resp.status_code == 302
    assert _entrega_de(IDS['atrasado']) == _hoy()


def test_mover_a_manana_saca_del_dia_lo_que_no_se_alcanzo(app):
    c = _login(app, 'jefe')
    c.post(f'/pedidos/{IDS["de_hoy"]}/entrega', data={'fecha': 'manana'})
    assert _entrega_de(IDS['de_hoy']) == _hoy() + timedelta(days=1)


def test_mover_a_una_fecha_explicita(app):
    c = _login(app, 'jefe')
    c.post(f'/pedidos/{IDS["atrasado"]}/entrega', data={'fecha': '2026-12-24'})
    assert _entrega_de(IDS['atrasado']) == date(2026, 12, 24)


def test_una_fecha_ilegible_no_borra_la_que_ya_tenia(app):
    """`_parsear_fecha_entrega` convierte la basura en None, y un pedido sin
    fecha cae en «Sin fecha de entrega»: mover mal escondería el trabajo."""
    c = _login(app, 'jefe')
    antes = _entrega_de(IDS['atrasado'])
    c.post(f'/pedidos/{IDS["atrasado"]}/entrega', data={'fecha': 'el jueves'})
    assert _entrega_de(IDS['atrasado']) == antes


def test_sin_fecha_no_cambia_nada(app):
    c = _login(app, 'jefe')
    antes = _entrega_de(IDS['atrasado'])
    c.post(f'/pedidos/{IDS["atrasado"]}/entrega', data={})
    assert _entrega_de(IDS['atrasado']) == antes


def test_un_pedido_facturado_no_se_mueve(app):
    """Ese trabajo ya cerró y la factura salió: cambiarle el día no significa
    nada y desalinearía el tablero de lo que pasó de verdad."""
    c = _login(app, 'jefe')
    antes = _entrega_de(IDS['facturado'])
    c.post(f'/pedidos/{IDS["facturado"]}/entrega', data={'fecha': 'hoy'})
    assert _entrega_de(IDS['facturado']) == antes


def test_mover_no_toca_las_lineas_ni_el_tipo_de_cambio(app):
    """La ruta existe justamente para NO pasar por el formulario, que recotiza."""
    from app import Pedido
    c = _login(app, 'jefe')
    p = _db.session.get(Pedido, IDS['atrasado'])
    lineas_antes = [(d.id, float(d.precio_unitario), float(d.subtotal))
                    for d in p.detalles]
    c.post(f'/pedidos/{IDS["atrasado"]}/entrega', data={'fecha': 'hoy'})
    _db.session.expire_all()
    p = _db.session.get(Pedido, IDS['atrasado'])
    assert [(d.id, float(d.precio_unitario), float(d.subtotal))
            for d in p.detalles] == lineas_antes
    assert p.tipo_cambio == 1.0
    assert p.estado == 'pendiente'


def test_mover_deja_rastro(app):
    """Cuántas veces se le corrió la entrega a un cliente es una pregunta que
    va a aparecer sola; el evento es gratis y sin él no hay forma de contestarla."""
    from app import PedidoEvento
    c = _login(app, 'jefe')
    c.post(f'/pedidos/{IDS["atrasado"]}/entrega', data={'fecha': 'hoy'})
    eventos = PedidoEvento.query.filter_by(
        pedido_id=IDS['atrasado'], tipo='entrega_movida').all()
    assert len(eventos) == 1
    assert _hoy().strftime('%d/%m') in eventos[0].descripcion
    # Y los dos días en `meta`, para que «cuántas veces se corrió» se pueda
    # contestar con una consulta y no leyendo descripciones a ojo.
    meta = json.loads(eventos[0].meta)
    assert meta == {
        'anterior': (_hoy() - timedelta(days=3)).isoformat(),
        'nueva': _hoy().isoformat(),
    }


# ── Autorización ───────────────────────────────────────────────────────────

def test_vendedor_ajeno_no_mueve_la_entrega(app):
    c = _login(app, 'vend_a')
    antes = _entrega_de(IDS['ajeno'])
    resp = c.post(f'/pedidos/{IDS["ajeno"]}/entrega', data={'fecha': 'hoy'})
    assert resp.status_code in (302, 403)
    assert _entrega_de(IDS['ajeno']) == antes


def test_el_vendedor_mueve_los_pedidos_de_sus_clientes(app):
    c = _login(app, 'vend_a')
    c.post(f'/pedidos/{IDS["atrasado"]}/entrega', data={'fecha': 'hoy'})
    assert _entrega_de(IDS['atrasado']) == _hoy()


def test_next_a_otro_host_no_redirige_afuera(app):
    c = _login(app, 'jefe')
    resp = c.post(f'/pedidos/{IDS["atrasado"]}/entrega',
                  data={'fecha': 'hoy', 'next': 'https://evil.com/x'})
    assert 'evil.com' not in resp.headers.get('Location', '')


# ── Lo que se ve ───────────────────────────────────────────────────────────

def test_el_pedido_movido_a_hoy_aparece_bajo_Hoy_en_el_tablero(app):
    """El test que importa: no que la columna cambie, sino que el tablero lo
    muestre donde el vendedor lo va a buscar."""
    c = _login(app, 'jefe')
    c.post(f'/pedidos/{IDS["atrasado"]}/entrega', data={'fecha': 'hoy'})
    html = c.get('/pedidos').get_data(as_text=True)
    grupo_hoy = html.split('tablero-grupo-hoy')[1].split('tablero-grupo-')[0]
    assert f'PED-{IDS["atrasado"]}' in grupo_hoy


def test_la_tarjeta_ofrece_mover_la_entrega(app):
    c = _login(app, 'jefe')
    html = c.get('/pedidos').get_data(as_text=True)
    assert f'/pedidos/{IDS["atrasado"]}/entrega' in html


def test_un_pedido_que_ya_es_de_hoy_no_ofrece_el_boton_Hoy(app):
    c = _login(app, 'jefe')
    tarjeta = _tarjeta(c.get('/pedidos').get_data(as_text=True), IDS['de_hoy'])
    assert 'value="manana"' in tarjeta, 'debe seguir ofreciendo mover a mañana'
    assert 'value="hoy"' not in tarjeta


def test_un_pedido_de_manana_no_ofrece_el_boton_Manana(app):
    c = _login(app, 'jefe')
    c.post(f'/pedidos/{IDS["atrasado"]}/entrega', data={'fecha': 'manana'})
    tarjeta = _tarjeta(c.get('/pedidos').get_data(as_text=True), IDS['atrasado'])
    assert 'value="hoy"' in tarjeta, 'debe seguir ofreciendo traerlo a hoy'
    assert 'value="manana"' not in tarjeta


def test_la_tarjeta_de_un_facturado_no_ofrece_mover_la_entrega(app):
    c = _login(app, 'jefe')
    html = c.get('/pedidos').get_data(as_text=True)
    assert f'/pedidos/{IDS["facturado"]}/entrega' not in html
