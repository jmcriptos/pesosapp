# tests/test_pedidos_lista_entregado.py
"""`entregado` deja de esconder el pedido de la pantalla.

`base_query` filtraba `Pedido.estado != 'entregado'` ANTES de los conteos:
un pedido entregado desaparecía del tablero, de la lista, de `?estado=todos`
y hasta del total «Ver los N pedidos». El estado que significa «esto salió
bien» era el que borraba el pedido de la vista.

Además `entregado` pasa a ser lo que se hunde al fondo del listado (antes era
`facturado`) y deja de contar como vencido, mientras que un facturado con la
entrega pasada ahora SÍ cuenta: se factura ANTES de que salga el camión, así
que un facturado sin entregar sigue siendo trabajo activo.
"""
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
    from app import Rol, Territorio, Vendedor, Cliente, Producto, Pedido, DetallePedido

    rol = Rol(nombre='super_admin', descripcion='Admin')
    terr = Territorio(nombre='t1', descripcion='T1')
    _db.session.add_all([rol, terr])
    _db.session.flush()

    jefe = Vendedor(username='jefe', email='jefe@t.com', nombre_completo='Jefe',
                     rol_id=rol.id, territorio_id=terr.id, activo=True)
    jefe.set_password('pw')
    _db.session.add(jefe)

    cliente = Cliente(nombre='Cliente A', territorio_id=terr.id, moneda='XCG')
    _db.session.add(cliente)

    prod = Producto(nombre='Producto X', descripcion='d', temperatura='Seco',
                     se_pesa=False, tax_rate=6.0, qbo_id='QBO-PX')
    _db.session.add(prod)
    _db.session.flush()

    hoy = _hoy()

    def mk_pedido(estado, entrega):
        p = Pedido(cliente_id=cliente.id, estado=estado, tipo_cambio=1.0,
                   fecha_entrega=entrega)
        _db.session.add(p)
        _db.session.flush()
        _db.session.add(DetallePedido(
            pedido_id=p.id, producto_id=prod.id, cajas=1, cajas_pedidas=1,
            peso=0, precio_unitario=Decimal('10.00'), subtotal=Decimal('10.00'),
            es_linea_pedido=True))
        return p

    # Cuatro pedidos sembrados: el total «de N» de los tests de abajo asume 4.
    pendiente = mk_pedido('pendiente', hoy)
    entregado = mk_pedido('entregado', hoy)
    facturado = mk_pedido('facturado', hoy)
    facturado_vencido = mk_pedido('facturado', hoy - timedelta(days=3))

    _db.session.commit()
    IDS.update(pendiente=pendiente.id, entregado=entregado.id,
               facturado=facturado.id, facturado_vencido=facturado_vencido.id)


def _login(app, username):
    """Un solo test_client por test: un segundo cliente hereda la sesión del
    primero y los tests de autorización pasarían en vacío."""
    c = app.test_client()
    c.post('/login', data={'username': username, 'password': 'pw'},
           follow_redirects=True)
    return c


def test_el_entregado_no_desaparece_de_la_lista(app):
    """`base_query` filtraba `estado != 'entregado'`, antes de los conteos: el
    pedido desaparecía del tablero, de la lista, de ?estado=todos y hasta del
    total. El estado que significa «salió bien» era el que borraba el pedido
    de la vista."""
    c = _login(app, 'jefe')
    html = c.get('/pedidos?estado=todos').get_data(as_text=True)
    assert f'PED-{IDS["entregado"]}' in html


def test_hay_filtro_por_entregado(app):
    c = _login(app, 'jefe')
    html = c.get('/pedidos?estado=entregado').get_data(as_text=True)
    assert f'PED-{IDS["entregado"]}' in html
    assert f'PED-{IDS["pendiente"]}' not in html


def test_el_entregado_cuenta_en_el_total(app):
    c = _login(app, 'jefe')
    html = c.get('/pedidos?estado=todos').get_data(as_text=True)
    # El pie dice «1–N de TOTAL»; con 4 pedidos sembrados el total es 4.
    assert 'de 4' in html or '1–4' in html


def test_un_entregado_no_esta_vencido(app):
    """Se entregó: no hay nada atrasado que hacer con él."""
    c = _login(app, 'jefe')
    html = c.get('/pedidos?estado=vencido').get_data(as_text=True)
    assert f'PED-{IDS["entregado"]}' not in html


def test_un_facturado_con_entrega_pasada_SI_esta_vencido(app):
    """El contrapunto: facturado ya no significa terminado."""
    c = _login(app, 'jefe')
    html = c.get('/pedidos?estado=vencido').get_data(as_text=True)
    assert f'PED-{IDS["facturado_vencido"]}' in html
