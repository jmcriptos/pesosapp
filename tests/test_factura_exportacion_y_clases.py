"""El payload de facturación lleva todo lo que la factura necesita.

Cuatro datos se corregían a mano en cada factura de QuickBooks. Tres salen de
acá (el cuarto, `Currency2`, no se puede escribir por la API v3):

- La CLASE del producto. n8n ya respeta `class_ref` por línea; la app nunca lo
  mandaba, así que ninguna línea salía clasificada.
- La MONEDA del campo personalizado y el TIPO DE CAMBIO. Los clientes de
  exportación son USD en QBO pero estaban cargados como XCG en la app.
- El IMPUESTO de exportación: a un cliente USD se le factura exento (código
  13) sea cual sea el producto. Antes salía el código del producto, así que un
  atún (10 = OB 6%) se le cobraba con 6% a un cliente de Bonaire.
"""
import os
from datetime import date
from decimal import Decimal

import pytest

os.environ.setdefault('SECRET_KEY', 'test-secret')
os.environ.setdefault('FLASK_ENV', 'testing')
os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')

from app import app as flask_app, db as _db

CLASE_COCIDOS = '600000000005541105'
CLASE_ATUN = '600000000005391641'


@pytest.fixture
def app():
    flask_app.config.update(TESTING=True, WTF_CSRF_ENABLED=False,
                            SQLALCHEMY_DATABASE_URI='sqlite:///:memory:')
    with flask_app.app_context():
        _db.create_all()
        from app import Rol, Territorio, Vendedor
        rol = Rol(nombre='super_admin', descripcion='A')
        terr = Territorio(nombre='t', descripcion='T')
        _db.session.add_all([rol, terr])
        _db.session.flush()
        v = Vendedor(username='admin', email='a@t.com', nombre_completo='Admin',
                     rol_id=rol.id, territorio_id=terr.id, activo=True)
        v.set_password('testpass')
        _db.session.add(v)
        _db.session.commit()
        yield flask_app
        _db.drop_all()


@pytest.fixture
def logged_client(app):
    c = app.test_client()
    c.post('/login', data={'username': 'admin', 'password': 'testpass'},
           follow_redirects=True)
    return c


def _pedido(moneda='XCG', tax_rate=10.0, clase=CLASE_ATUN, nombre='Atun en Agua 160g'):
    """Pedido de un producto por caja, con su línea original y la de preparación."""
    from app import Cliente, Producto, Pedido, DetallePedido

    # qbo_id único por cliente: la tabla lo exige y un test puede armar varios.
    n = Cliente.query.count() + 1
    cli = Cliente(nombre=f'Cliente {n}', moneda=moneda, qbo_id=f'C{n}',
                  territorio_id=1)
    prod = Producto(nombre=nombre, se_pesa=False, tax_rate=tax_rate,
                    qbo_id=f'P{n}', temperatura='Seco', clase_qbo=clase)
    _db.session.add_all([cli, prod])
    _db.session.flush()

    tc = 1.78 if (moneda or '').upper() == 'USD' else 1.0
    p = Pedido(cliente_id=cli.id, estado='preparado', tipo_cambio=tc,
               fecha_entrega=date(2026, 8, 29))
    _db.session.add(p)
    _db.session.flush()
    for original in (True, False):
        _db.session.add(DetallePedido(
            pedido_id=p.id, producto_id=prod.id, cajas=Decimal('2'),
            cajas_pedidas=Decimal('2'), peso=0, precio_unitario=Decimal('10'),
            subtotal=Decimal('20'), es_linea_pedido=original,
            lote=None if original else 'L-1',
            fecha_fabricacion=None if original else date(2026, 8, 27),
            fecha_expiracion=None if original else date(2027, 8, 27)))
    _db.session.commit()
    return p


# ------------------------------------------------------ impuesto de exportación


def test_un_cliente_usd_factura_todo_como_exportacion(app):
    """La exportación manda sobre el producto: un atún al 6% se factura exento."""
    from app import pedido_a_json

    with app.app_context():
        payload = pedido_a_json(_pedido(moneda='USD', tax_rate=10.0))

    assert [l['tax_rate'] for l in payload['lines']] == ['13'], (
        'Un cliente USD es exportación: todas sus líneas van con el código 13'
    )


def test_un_cliente_xcg_conserva_el_impuesto_del_producto(app):
    """Regresión: el caso normal no cambia."""
    from app import pedido_a_json

    with app.app_context():
        payload = pedido_a_json(_pedido(moneda='XCG', tax_rate=10.0))

    assert [l['tax_rate'] for l in payload['lines']] == [10.0]


# ------------------------------------------------------------ moneda y cambio


def test_el_payload_lleva_la_moneda_de_qbo_y_el_tipo_de_cambio(app):
    """QBO llama ANG a la moneda local, no XCG; y el tipo de cambio nunca salía."""
    from app import pedido_a_json

    with app.app_context():
        xcg = pedido_a_json(_pedido(moneda='XCG'))
        usd = pedido_a_json(_pedido(moneda='USD'))

    assert xcg['currency_qbo'] == 'ANG'
    assert xcg['currency_display'] == 'XCG - Caribbean Guilder'
    assert xcg['exchange_rate'] == 1.0

    assert usd['currency_qbo'] == 'USD'
    assert usd['currency_display'] == 'USD - US Dollar'
    assert usd['exchange_rate'] == 1.78


# ------------------------------------------------------------------- clases


def test_cada_linea_lleva_la_clase_de_su_producto(app):
    from app import pedido_a_json

    with app.app_context():
        payload = pedido_a_json(_pedido(clase=CLASE_ATUN))

    assert [l['class_ref'] for l in payload['lines']] == [CLASE_ATUN]


def test_un_producto_sin_clase_no_manda_class_ref(app):
    """Mandar null haría que n8n lo tome como clase válida y la pise."""
    from app import pedido_a_json

    with app.app_context():
        payload = pedido_a_json(_pedido(clase=None))

    assert 'class_ref' not in payload['lines'][0]


def test_cada_linea_lleva_el_nombre_del_producto(app):
    """n8n busca `product_name`; la app solo mandaba `descripcion`, así que
    ItemRef.name salía vacío y la detección por keywords nunca corría."""
    from app import pedido_a_json

    with app.app_context():
        payload = pedido_a_json(_pedido(nombre='Atun en Agua 160g'))

    assert payload['lines'][0]['product_name'] == 'Atun en Agua 160g'


# ------------------------------------------------------ pantalla de productos


def test_la_pantalla_de_productos_guarda_la_clase(app, logged_client):
    from app import Producto

    logged_client.post('/productos', data={
        'nombre': 'Smoked Bacon', 'descripcion': 'x', 'temperatura': 'Refrigerado',
        'qbo_id': 'P9', 'tax_rate': '14.0', 'clase_qbo': CLASE_COCIDOS,
    }, follow_redirects=True)

    with app.app_context():
        prod = Producto.query.filter_by(nombre='Smoked Bacon').first()
        assert prod is not None
        assert prod.clase_qbo == CLASE_COCIDOS


# ----------------------------------------------- el aviso de clase no bloquea


def test_avisar_sin_clase_no_bloquea_la_facturacion(app):
    """`_validar_datos_facturacion` bloquea con cualquier string que devuelva,
    así que el aviso de clase NO puede vivir ahí."""
    from app import pedido_a_json, _validar_datos_facturacion, _productos_sin_clase

    with app.app_context():
        payload = pedido_a_json(_pedido(clase=None))

    assert _validar_datos_facturacion(payload) == [], (
        'Faltar la clase no puede impedir facturar'
    )
    assert _productos_sin_clase(payload) == ['Atun en Agua 160g']


def test_no_avisa_cuando_todas_las_lineas_tienen_clase(app):
    from app import pedido_a_json, _productos_sin_clase

    with app.app_context():
        payload = pedido_a_json(_pedido(clase=CLASE_ATUN))

    assert _productos_sin_clase(payload) == []
