# tests/test_pedidos_lista_entrega.py
"""Cifras y filtros del listado de pedidos que dependen de `fecha_entrega`.

La guía "Sistema UI" pone dos cifras arriba de la lista (por preparar /
vencidos) y una píldora "Hoy". Las tres se derivan de `fecha_entrega`, que es
una columna nueva: los pedidos históricos la tienen en NULL y no deben contarse
como vencidos ni como de hoy.
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
        from app import Rol, Territorio, Vendedor, Cliente

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
        _db.session.add(Cliente(nombre='Cliente Uno', territorio_id=territorio.id))
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


def _pedido(estado, dias_entrega=None):
    """Crea un pedido. `dias_entrega=None` deja fecha_entrega en NULL, que es
    como están los 910 pedidos anteriores a la columna."""
    from app import Pedido, Cliente
    cliente = Cliente.query.first()
    p = Pedido(cliente_id=cliente.id, estado=estado)
    if dias_entrega is not None:
        p.fecha_entrega = _hoy_local() + timedelta(days=dias_entrega)
    _db.session.add(p)
    _db.session.commit()
    return p


def _counts(logged_client):
    """Lee las cifras del HTML sin acoplarse al markup exacto.

    Las dos «cifras» de 75px que había arriba de la lista se eliminaron el
    2026-08-28: eran un tercer widget escribiendo el mismo `estado` que las
    píldoras, y «Por preparar» era literalmente Pendientes + Preparados
    repetido más abajo. Los CONTEOS no cambiaron —los sigue calculando
    `lista_pedidos` igual—, solo viven ahora en la píldora. Lo que se rompió
    fue este lector, no la app.
    """
    import re
    html = logged_client.get('/pedidos?estado=todos').get_data(as_text=True)
    out = {}
    for clave in ('por_preparar', 'vencido'):
        m = re.search(
            r'data-estado="%s".*?<span class="filter-pill-count">(\d+)</span>' % clave,
            html, re.S)
        out[clave] = int(m.group(1)) if m else None
    return out


def test_pedido_sin_fecha_entrega_no_cuenta_como_vencido(app, logged_client):
    """Los 910 históricos tienen fecha_entrega NULL: no son vencidos."""
    _pedido('pendiente')      # sin fecha
    _pedido('preparado')      # sin fecha

    cifras = _counts(logged_client)
    assert cifras['vencido'] == 0
    assert cifras['por_preparar'] == 2


def test_vencido_es_entrega_pasada_y_sin_facturar(app, logged_client):
    _pedido('pendiente', dias_entrega=-3)   # vencido
    _pedido('preparado', dias_entrega=-1)   # vencido
    _pedido('pendiente', dias_entrega=0)    # hoy, no vencido
    _pedido('pendiente', dias_entrega=2)    # futuro
    _pedido('facturado', dias_entrega=-9)   # ya facturado: no es un pendiente

    cifras = _counts(logged_client)
    assert cifras['vencido'] == 2, 'facturado no cuenta aunque su entrega pasó'


def test_por_preparar_suma_pendientes_y_preparados(app, logged_client):
    _pedido('pendiente')
    _pedido('pendiente')
    _pedido('preparado')
    _pedido('facturado')

    assert _counts(logged_client)['por_preparar'] == 3


def test_la_cifra_y_su_filtro_coinciden(app, logged_client):
    """Si la cifra dice 3, tocarla tiene que mostrar 3.

    El filtro arrancó apuntando solo a 'pendiente' mientras la cifra sumaba
    pendientes + preparados, así que el número de arriba y la lista de abajo
    no coincidían.
    """
    _pedido('pendiente')
    _pedido('pendiente')
    _pedido('preparado')
    _pedido('facturado')

    cifra = _counts(logged_client)['por_preparar']
    html = logged_client.get('/pedidos?estado=por_preparar').get_data(as_text=True)
    assert cifra == html.count('class="pedido-card"')


def test_filtro_hoy_solo_trae_entregas_de_hoy(app, logged_client):
    _pedido('pendiente', dias_entrega=0)
    _pedido('preparado', dias_entrega=0)
    _pedido('pendiente', dias_entrega=1)
    _pedido('pendiente', dias_entrega=-1)
    _pedido('pendiente')  # sin fecha

    html = logged_client.get('/pedidos?estado=hoy').get_data(as_text=True)
    assert html.count('class="pedido-card"') == 2


def test_filtro_vencido_excluye_facturados(app, logged_client):
    _pedido('pendiente', dias_entrega=-5)
    _pedido('facturado', dias_entrega=-5)

    html = logged_client.get('/pedidos?estado=vencido').get_data(as_text=True)
    assert html.count('class="pedido-card"') == 1


def test_estado_desconocido_cae_a_todos(app, logged_client):
    """Un valor arbitrario en la URL no debe filtrar ni reventar."""
    _pedido('pendiente')
    _pedido('facturado')

    resp = logged_client.get('/pedidos?estado=inventado')
    assert resp.status_code == 200
    assert resp.get_data(as_text=True).count('class="pedido-card"') == 2


def test_pendiente_ofrece_pesar_y_preparado_facturar(app, logged_client):
    """La acción principal de la tarjeta, con palabra, según el estado.

    El pendiente lleva una línea de un producto que SE PESA: la lista ya no
    ofrece «Pesar» cuando no hay nada que pesar, porque la ruta rechaza ese
    caso y devuelve al detalle con un flash.
    """
    from app import Producto, DetallePedido
    from decimal import Decimal

    p_pend = _pedido('pendiente')
    prod = Producto(nombre='Pesable', temperatura='-18°C', se_pesa=True,
                    tax_rate=10.0, qbo_id='Q-PESA')
    _db.session.add(prod)
    _db.session.flush()
    _db.session.add(DetallePedido(
        pedido_id=p_pend.id, producto_id=prod.id, cajas=1, cajas_pedidas=1,
        peso=0, precio_unitario=Decimal('10'), subtotal=Decimal('10'),
        es_linea_pedido=True,
    ))
    _db.session.commit()

    p_prep = _pedido('preparado')

    html = logged_client.get('/pedidos?estado=todos').get_data(as_text=True)
    assert f'/pedidos/{p_pend.id}/pesar' in html
    assert '> Pesar' in html
    assert f'/pedidos/{p_prep.id}/facturar' in html
    assert '> Facturar' in html
