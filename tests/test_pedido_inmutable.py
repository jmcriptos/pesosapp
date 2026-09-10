"""Un solo dueño para la regla «este pedido ya no se toca».

Hasta ahora esa regla estaba escrita catorce veces como `estado == 'facturado'`
repartida por todo `app.py`. Este test existe para que, cuando aparezca el
estado `entregado`, no haga falta confiar en la memoria de nadie para saber si
las catorce lo cubren: `_pedido_es_inmutable` es el único dueño y este archivo
lo prueba contra las cinco acciones que un pedido facturado ya no admite.
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

    ca = Cliente(nombre='Cliente A', territorio_id=terr.id, qbo_id='QBO-A', moneda='XCG')
    _db.session.add(ca)

    prod = Producto(nombre='Producto X', descripcion='d', temperatura='Seco',
                    se_pesa=False, tax_rate=6.0, qbo_id='QBO-PX')
    _db.session.add(prod)
    _db.session.flush()

    _db.session.add(ClienteVendedor(cliente_id=ca.id, vendedor_id=va.id, activo=True))

    hoy = _hoy()

    def mk_pedido(estado):
        p = Pedido(cliente_id=ca.id, estado=estado, tipo_cambio=1.0,
                   fecha_entrega=hoy)
        _db.session.add(p)
        _db.session.flush()
        _db.session.add(DetallePedido(
            pedido_id=p.id, producto_id=prod.id, cajas=5, cajas_pedidas=5,
            peso=0, precio_unitario=Decimal('5.00'), subtotal=Decimal('25.00'),
            es_linea_pedido=True))
        return p

    pendiente = mk_pedido('pendiente')
    preparado = mk_pedido('preparado')
    facturado = mk_pedido('facturado')
    entregado = mk_pedido('entregado')

    # Línea de preparación del entregado: sin ella, `_validar_preparacion_pedido`
    # ya lo bloquea por trazabilidad incompleta y los tests de `marcar_preparado`/
    # `facturar` pasarían igual con la guarda de inmutabilidad rota — no
    # probarían nada. `pedido_a_json` factura por esta línea (no por la
    # original) para productos que no se pesan, así que necesita el mismo
    # precio que la original: en 0 dispara el guard de `_validar_datos_facturacion`
    # («precio en 0») y el facturar test tampoco pasaría por la guarda que
    # se quiere probar.
    _db.session.add(DetallePedido(
        pedido_id=entregado.id, producto_id=prod.id, cajas=5, peso=0,
        precio_unitario=Decimal('5.00'), subtotal=Decimal('25.00'),
        es_linea_pedido=False))

    _db.session.commit()
    IDS.update(pendiente=pendiente.id, preparado=preparado.id,
               facturado=facturado.id, entregado=entregado.id)


def _login(app, username):
    """Un solo test_client por test: un segundo cliente hereda la sesión del
    primero y los tests de autorización pasarían en vacío."""
    c = app.test_client()
    c.post('/login', data={'username': username, 'password': 'pw'},
           follow_redirects=True)
    return c


def test_un_pedido_entregado_no_se_puede_editar(app):
    """Con POST clásico (sin el header de `fetch`) un form vacío también
    redirige por validación de pasos — 302 no alcanza para saber si fue la
    guarda de inmutabilidad o el form vacío. El camino AJAX de
    `pedido_form.html` sí distingue: 409 es el código que SOLO usa esta
    guarda dentro de `editar_pedido` (los demás branches de error son 400/403)."""
    c = _login(app, 'jefe')
    resp = c.post(f'/pedidos/{IDS["entregado"]}/editar', data={},
                  headers={'X-Requested-With': 'XMLHttpRequest'},
                  follow_redirects=False)
    assert resp.status_code == 409, 'un entregado ya salió: su factura está en QBO'


def test_un_pedido_entregado_no_se_puede_eliminar(app):
    from app import Pedido
    c = _login(app, 'jefe')
    c.post(f'/pedidos/{IDS["entregado"]}/eliminar')
    assert _db.session.get(Pedido, IDS['entregado']) is not None


def test_un_pedido_entregado_no_se_puede_pesar(app):
    c = _login(app, 'jefe')
    resp = c.get(f'/pedidos/{IDS["entregado"]}/pesar', follow_redirects=False)
    assert resp.status_code == 302


def test_un_pedido_entregado_no_vuelve_a_preparado(app):
    from app import Pedido
    c = _login(app, 'jefe')
    c.post(f'/pedidos/{IDS["entregado"]}/marcar_preparado')
    assert _db.session.get(Pedido, IDS['entregado']).estado == 'entregado'


def test_un_pedido_entregado_no_se_vuelve_a_facturar(app):
    """`N8N_WEBHOOK_URL` no está seteada en test: sin parchearla, la ruta ya
    corta antes del `requests.post` por esa razón y el mock quedaría sin
    llamar pase lo que pase con la guarda — el test no probaría nada."""
    from unittest.mock import patch
    c = _login(app, 'jefe')
    with patch('app.requests.post') as mock_post, \
         patch('app.N8N_WEBHOOK_URL', 'https://n8n.example/webhook'):
        c.post(f'/pedidos/{IDS["entregado"]}/facturar')
    mock_post.assert_not_called()


def test_el_facturado_sigue_siendo_inmutable(app):
    """La regla vieja no se pierde al generalizarla."""
    from app import Pedido
    c = _login(app, 'jefe')
    c.post(f'/pedidos/{IDS["facturado"]}/eliminar')
    assert _db.session.get(Pedido, IDS['facturado']) is not None
