"""Tras el backfill, ~960 pedidos pasan de `facturado` a `entregado` en
producción. En esta empresa se factura ANTES de entregar, así que un pedido
entregado se facturó igual — entregarlo no lo desfactura. Si el dashboard
siguiera contando solo `estado == 'facturado'`, todas las métricas que miden
"lo facturado" caerían de 964 a 4 sin que nadie hubiera dejado de facturar:
una regresión silenciosa en cifras que JM mira todos los días.

La primera mitad de este archivo prueba el único punto que cubre nueve de
los llamadores de una sola vez: `_pedido_facturado_en_periodo_local`. Pero
un revisor con mutation testing rompió a mano tres de los sitios que SÍ
pasan por rutas HTTP reales (el contador de `dashboard_vendedor`,
`pedidos_facturados_list` y `es_facturado` en `/dashboard`) y la suite
completa siguió en verde: ningún fixture de la suite crea un pedido
`entregado` CON `fecha_facturacion`, así que la rama nueva nunca se
ejercitaba. La prueba de reversión del helper de abajo solo prueba que el
helper se prueba a sí mismo — no que ninguna ruta lo usa bien.

La segunda mitad son tests de INTEGRACIÓN por ruta: siembran un pedido
`entregado` con `fecha_facturacion` dentro del período y piden la ruta real
por HTTP, para que un `== 'facturado'` vuelto a colar ahí haga fallar al
test aunque el helper esté bien. Cubren `/dashboard`, `/api/admin/stats` y
`/api/dashboard/metricas` (esta última ejercita `obtener_metricas_sistema`,
que tiene el MISMO patrón de contador que el `dashboard_vendedor` que el
revisor rompió a mano).

Dos rutas de la lista del brief quedaron afuera, por bugs preexistentes y
sin relación con esta tarea que impiden ejercitarlas de punta a punta
(detalle en el reporte de la Task 6):
  - `/dashboard_vendedor`: el template `dashboard_vendedor.html` referencia
    `porcentaje_meta`, que la ruta nunca pone en el contexto (ni en la rama
    admin ni en la de vendedor) → `UndefinedError` en CUALQUIER request,
    con o sin este fix. La ruta está además huérfana: ningún link ni
    redirect de la app apunta a ella desde que un commit anterior la
    reemplazó por `dashboard`/`home`.
  - `/admin/analytics`: la query de `eficiencia_vendedores` usa
    `db.case([(condición, 1)], else_=0)` — sintaxis de lista, removida en
    SQLAlchemy 2.0 (la app corre con 2.0.32). Explota SIEMPRE, capturada por
    un `except Exception` que hace `flash` + redirect a `/`. El bug ya
    estaba antes de esta rama (verificado contra `e7f3b477`, el commit previo
    a la Task 6).
"""
import os
from datetime import datetime, timezone

import pytest

os.environ.setdefault('SECRET_KEY', 'test-secret')
os.environ.setdefault('FLASK_ENV', 'testing')
os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')

import app as app_module
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
        yield flask_app
        _db.drop_all()


def test_un_pedido_entregado_sigue_contando_como_facturado(app):
    """Tras el backfill, 960 pedidos pasan a `entregado`. Si el dashboard
    sigue contando solo `facturado`, las cifras caen de 964 a 4 sin que nadie
    haya dejado de facturar: una regresión silenciosa en números que JM mira
    todos los días."""
    from app import _pedido_facturado_en_periodo_local, Pedido
    from datetime import date, datetime
    p = Pedido(estado='entregado', fecha_facturacion=datetime(2026, 9, 1, 12, 0))
    assert _pedido_facturado_en_periodo_local(p, date(2026, 9, 1)) is True


def test_un_pendiente_no_cuenta_como_facturado(app):
    from app import _pedido_facturado_en_periodo_local, Pedido
    from datetime import date, datetime
    p = Pedido(estado='pendiente', fecha_facturacion=datetime(2026, 9, 1, 12, 0))
    assert _pedido_facturado_en_periodo_local(p, date(2026, 9, 1)) is False


# ── Tests de integración por ruta ───────────────────────────────────────
# Siembran UN pedido `entregado` con `fecha_facturacion` dentro del mes y
# piden la ruta real por HTTP. `_obtener_metricas_ventas_quickbooks` se
# fuerza a `None` para forzar el camino local (el que de verdad ejercita
# `PEDIDO_INMUTABLE`/`_pedido_facturado_en_periodo_local`) — sin QBO
# configurado en el entorno de test ya cae ahí solo, pero se fuerza igual
# para que el test no dependa de esa casualidad del entorno.

@pytest.fixture
def app_con_entregado(app):
    """Como `app`, pero con un admin logueable y un pedido `entregado` con
    `fecha_facturacion` de HOY y un subtotal reconocible (987), para poder
    afirmar que la cifra mostrada lo INCLUYE."""
    from app import Rol, Territorio, Vendedor, Cliente, Producto, Pedido, DetallePedido

    rol = Rol(nombre='super_admin', descripcion='Admin')
    territorio = Territorio(nombre='t-entregado', descripcion='T')
    _db.session.add_all([rol, territorio])
    _db.session.flush()
    vendedor = Vendedor(
        username='jefe_entregado', email='jefe_entregado@test.com',
        nombre_completo='Jefe Entregado', rol_id=rol.id,
        territorio_id=territorio.id, activo=True,
    )
    vendedor.set_password('testpass')
    cliente = Cliente(nombre='Cliente Entregado Dashboard')
    producto = Producto(nombre='Producto Entregado Dashboard', se_pesa=False)
    _db.session.add_all([vendedor, cliente, producto])
    _db.session.flush()

    ahora = datetime.now(timezone.utc)
    pedido = Pedido(cliente_id=cliente.id, estado='entregado',
                     fecha_pedido=ahora, fecha_facturacion=ahora)
    _db.session.add(pedido)
    _db.session.flush()
    # `cajas` (2, lo entregado) distinto de `cajas_pedidas` (4, lo pedido):
    # a proposito, para que el OFR ("Cajas entregadas") de un 50% detectable
    # en vez de un 100% que seria igual con o sin el pedido incluido (ver
    # `test_dashboard_ofr_incluye_al_entregado` mas abajo).
    _db.session.add(DetallePedido(
        pedido_id=pedido.id, producto_id=producto.id,
        cajas=2, cajas_pedidas=4, peso=0,
        precio_unitario=25, subtotal=987, es_linea_pedido=True,
    ))
    _db.session.commit()
    return app


@pytest.fixture
def logged_client_entregado(app_con_entregado):
    """Un solo test_client, logueado como el admin sembrado arriba."""
    client = app_con_entregado.test_client()
    client.post('/login', data={'username': 'jefe_entregado', 'password': 'testpass'},
                follow_redirects=True)
    return client


@pytest.fixture(autouse=False)
def sin_quickbooks(monkeypatch):
    """Fuerza el camino local: sin esto el test seguiría pasando por
    casualidad del entorno (sin webhook configurado), no por diseño."""
    monkeypatch.setattr(app_module, '_obtener_metricas_ventas_quickbooks', lambda *a, **kw: None)


def test_dashboard_incluye_al_entregado_en_ventas_del_mes(logged_client_entregado, sin_quickbooks):
    """Sitio roto a mano por el revisor: `pedidos_facturados_list` (~app.py
    :5924) y `es_facturado` (~app.py:5960) dentro de `/dashboard`. Si
    volvieran a comparar solo contra `'facturado'`, el entregado sembrado
    arriba desaparecería de la suma y este test lo detecta por el número
    exacto que faltaría (987), no por una cifra en cero que podría deberse a
    cualquier otra cosa."""
    html = logged_client_entregado.get('/dashboard').get_data(as_text=True)
    assert '<div class="kpi-value">987<small>XCG</small></div>' in html


def test_dashboard_ofr_incluye_al_entregado(logged_client_entregado, sin_quickbooks):
    """Distinto sitio, mismo bug potencial: `es_facturado` (~app.py:5960)
    adentro de `obtener_metricas_pedido` decide si el pedido entra al cálculo
    de OFR ("Cajas entregadas"). El fixture pide 4 cajas y entrega 2 a
    propósito: si `es_facturado` volviera a mirar solo `'facturado'`, este
    pedido se cae del cálculo y el mes queda SIN pedidos facturados, que cae
    al 100% por defecto (ver `calcular_kpis_periodo`) — un 100% que se vería
    igual de sano que el 50% real, así que no alcanzaba con leer ventas_mes
    para cubrir este sitio."""
    html = logged_client_entregado.get('/dashboard').get_data(as_text=True)
    assert '<div class="kpi-value">50.0%</div>' in html


def test_api_admin_stats_incluye_al_entregado(logged_client_entregado, sin_quickbooks):
    """`/api/admin/stats`: fallback local de `ventas_mes` (app.py ~5484-5492)."""
    resp = logged_client_entregado.get('/api/admin/stats')
    assert resp.status_code == 200
    assert resp.get_json()['ventas_mes'] == 987.0


def test_api_dashboard_metricas_incluye_al_entregado(logged_client_entregado, sin_quickbooks):
    """`/api/dashboard/metricas` (super_admin) llama a `obtener_metricas_sistema()`,
    que tiene EXACTAMENTE el mismo patrón de contador que el revisor rompió a
    mano en `dashboard_vendedor` (~app.py:2269: `Pedido.estado.in_(PEDIDO_INMUTABLE)).count()`).
    `dashboard_vendedor` no se puede ejercitar de punta a punta (ver el
    docstring del módulo), así que esta ruta cubre el mismo patrón de
    contador con una ruta que sí sirve datos reales."""
    resp = logged_client_entregado.get('/api/dashboard/metricas')
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['pedidos_facturados'] == 1
    assert data['ventas_mes'] == 987.0
