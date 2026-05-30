"""Tests de seguridad: IDOR / autorización por tenant y escalada de privilegios.

Modelo: vendedor_a está asignado a cliente_a; vendedor_b a cliente_b. Un
vendedor NO debe poder facturar/preparar/ver/editar pedidos ni precios de un
cliente que no tiene asignado, ni editar productos (rol 'vendedor' = solo
lectura en productos).
"""
import os
from decimal import Decimal
from unittest.mock import patch

import pytest

os.environ.setdefault('SECRET_KEY', 'test-secret')
os.environ.setdefault('FLASK_ENV', 'testing')
os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')

from app import app as flask_app, db as _db


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


# IDs estables capturados en el seed
IDS = {}


def _seed():
    from app import (Rol, Territorio, Vendedor, Cliente, Producto,
                     Pedido, DetallePedido, ClienteVendedor)

    rol_admin = Rol(nombre='super_admin', descripcion='Admin')
    rol_vend = Rol(nombre='vendedor', descripcion='Vendedor')
    terr = Territorio(nombre='t1', descripcion='T1')
    _db.session.add_all([rol_admin, rol_vend, terr])
    _db.session.flush()

    def mk_vend(u):
        v = Vendedor(username=u, email=f'{u}@t.com', nombre_completo=u,
                     rol_id=rol_vend.id, territorio_id=terr.id, activo=True)
        v.set_password('pw')
        _db.session.add(v)
        return v

    va, vb = mk_vend('vend_a'), mk_vend('vend_b')

    ca = Cliente(nombre='Cliente A', territorio_id=terr.id, qbo_id='QBO-A', moneda='XCG')
    cb = Cliente(nombre='Cliente B', territorio_id=terr.id, qbo_id='QBO-B', moneda='XCG')
    _db.session.add_all([ca, cb])

    prod = Producto(nombre='Producto X', descripcion='d', temperatura='Seco',
                    se_pesa=False, tax_rate=6.0, qbo_id='QBO-PX')
    _db.session.add(prod)
    _db.session.flush()

    # Asignaciones: va→ca, vb→cb
    _db.session.add_all([
        ClienteVendedor(cliente_id=ca.id, vendedor_id=va.id, activo=True),
        ClienteVendedor(cliente_id=cb.id, vendedor_id=vb.id, activo=True),
    ])

    # Pedido del cliente A (en preparado) con líneas importadas
    pedido = Pedido(cliente_id=ca.id, estado='preparado', tipo_cambio=1.0)
    _db.session.add(pedido)
    _db.session.flush()
    _db.session.add_all([
        DetallePedido(pedido_id=pedido.id, producto_id=prod.id, cajas=5,
                      cajas_pedidas=5, peso=0, precio_unitario=Decimal('5.00'),
                      subtotal=Decimal('25.00'), es_linea_pedido=True),
        DetallePedido(pedido_id=pedido.id, producto_id=prod.id, cajas=5,
                      cajas_pedidas=0, peso=0, precio_unitario=Decimal('5.00'),
                      subtotal=Decimal('25.00'), fecha_expiracion='2026-12-31',
                      es_linea_pedido=False),
    ])
    _db.session.commit()

    IDS.update(cliente_a=ca.id, cliente_b=cb.id, producto=prod.id,
               pedido_a=pedido.id)


def _login(app, username):
    c = app.test_client()
    c.post('/login', data={'username': username, 'password': 'pw'},
           follow_redirects=True)
    return c


# ── Vuln 1: facturar / marcar_preparado IDOR ───────────────────────────────

@patch('app.N8N_WEBHOOK_URL', 'http://test/webhook')
@patch('app.requests.post')
def test_vendedor_ajeno_no_factura_pedido(mock_post, app):
    from app import Pedido
    c = _login(app, 'vend_b')
    resp = c.post(f'/pedidos/{IDS["pedido_a"]}/facturar', follow_redirects=False)
    assert resp.status_code in (302, 403)
    mock_post.assert_not_called()  # NUNCA debe llegar al webhook QBO
    with app.app_context():
        p = _db.session.get(Pedido, IDS['pedido_a'])
        assert p.estado != 'facturado'


def test_vendedor_ajeno_no_marca_preparado(app):
    from app import Pedido
    # dejar el pedido en 'pendiente' para detectar cambio de estado
    with app.app_context():
        p = _db.session.get(Pedido, IDS['pedido_a'])
        p.estado = 'pendiente'
        _db.session.commit()
    c = _login(app, 'vend_b')
    resp = c.post(f'/pedidos/{IDS["pedido_a"]}/marcar_preparado', follow_redirects=False)
    assert resp.status_code in (302, 403)
    with app.app_context():
        p = _db.session.get(Pedido, IDS['pedido_a'])
        assert p.estado == 'pendiente'


# ── Vuln 3: etiquetas PDF IDOR ─────────────────────────────────────────────

def test_vendedor_ajeno_no_descarga_etiqueta(app):
    c = _login(app, 'vend_b')
    resp = c.get(f'/generar_etiqueta_detalle/{IDS["pedido_a"]}'
                 '?fecha_inicio=2000-01-01&fecha_fin=2100-01-01',
                 follow_redirects=False)
    assert resp.status_code in (302, 403)
    assert 'application/pdf' not in resp.headers.get('Content-Type', '')


def test_vendedor_ajeno_no_descarga_etiqueta_a4(app):
    c = _login(app, 'vend_b')
    resp = c.get(f'/generar_etiqueta_detalle_a4/{IDS["pedido_a"]}'
                 '?fecha_inicio=2000-01-01&fecha_fin=2100-01-01',
                 follow_redirects=False)
    assert resp.status_code in (302, 403)
    assert 'application/pdf' not in resp.headers.get('Content-Type', '')


# ── Vuln 6: editar_pedido GET IDOR ─────────────────────────────────────────

def test_vendedor_ajeno_no_abre_editar_pedido(app):
    c = _login(app, 'vend_b')
    resp = c.get(f'/pedidos/{IDS["pedido_a"]}/editar', follow_redirects=False)
    assert resp.status_code in (302, 403), (
        "GET editar_pedido debe bloquear pedidos de otro tenant antes de renderizar"
    )


# ── Vuln 2: APIs de precios por cliente (IDOR) ─────────────────────────────

@pytest.mark.parametrize('url_tpl', [
    '/api/precios/cliente/{c}/productos',
    '/api/precios/cliente/{c}',
    '/api/precios/cliente/{c}/debug',
    '/api/precios/cliente/{c}/producto/{p}',
])
def test_vendedor_ajeno_no_ve_precios_cliente(app, url_tpl):
    c = _login(app, 'vend_b')
    url = url_tpl.format(c=IDS['cliente_a'], p=IDS['producto'])
    resp = c.get(url, follow_redirects=False)
    assert resp.status_code == 403, f"{url} debe devolver 403 para vendedor ajeno"


def test_vendedor_propio_si_ve_precios_cliente(app):
    # Regresión: el vendedor asignado SÍ puede ver los precios de su cliente
    c = _login(app, 'vend_a')
    resp = c.get(f'/api/precios/cliente/{IDS["cliente_a"]}/productos')
    assert resp.status_code == 200


# ── Vuln 5: editar_producto requiere permiso de rol ────────────────────────

def test_vendedor_no_edita_producto(app):
    from app import Producto
    c = _login(app, 'vend_a')
    resp = c.post(f'/productos/{IDS["producto"]}/editar',
                  data={'nombre': 'HACKEADO', 'tax_rate': '0', 'qbo_id': 'X'},
                  follow_redirects=False)
    assert resp.status_code in (302, 403)
    with app.app_context():
        p = _db.session.get(Producto, IDS['producto'])
        assert p.nombre == 'Producto X', "El vendedor no debe poder editar productos"


# ── Vuln 4: XSS — los campos de usuario se escapan en scripts.js ───────────

def test_scripts_js_escapa_campos_usuario():
    import re
    path = os.path.join(os.path.dirname(__file__), '..', 'static', 'scripts.js')
    with open(path, encoding='utf-8') as fh:
        js = fh.read()

    assert 'function escapeHtml' in js, "Falta el helper escapeHtml"

    # Campos de texto controlados por el usuario que NUNCA deben interpolarse
    # crudos dentro de plantillas HTML.
    campos_peligrosos = [
        r'\$\{recepcion\.producto\}',
        r'\$\{recepcion\.proveedor\}',
        r'\$\{recepcion\.numero_factura\}',
        r'\$\{cliente\.nombre\}',
        r'\$\{facturacion\.producto\}',
        r'\$\{facturacion\.cliente\}',
        r'\$\{facturacion\.lote\}',
        r'\$\{producto\.nombre\}',
        r'\$\{producto\.descripcion\}',
    ]
    for patron in campos_peligrosos:
        assert not re.search(patron, js), (
            f"Interpolación cruda sin escapar encontrada: {patron}"
        )
