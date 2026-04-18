# tests/test_dashboard_kpis.py
"""Tests para Story 1.1: KPIs de nivel de servicio corregidos."""
import os
import re
import pytest
from datetime import datetime, timedelta, date, timezone
from zoneinfo import ZoneInfo

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
        from app import Rol, Territorio, Vendedor
        rol = Rol(nombre='super_admin', descripcion='Admin')
        _db.session.add(rol)
        territorio = Territorio(nombre='test', descripcion='Test')
        _db.session.add(territorio)
        _db.session.flush()
        vendedor = Vendedor(
            username='admin',
            email='admin@test.com',
            nombre_completo='Admin Test',
            rol_id=rol.id,
            territorio_id=territorio.id,
            activo=True,
        )
        vendedor.set_password('testpass')
        _db.session.add(vendedor)
        _db.session.commit()
        yield flask_app
        _db.drop_all()


@pytest.fixture
def logged_client(app):
    client = app.test_client()
    client.post('/login', data={
        'username': 'admin',
        'password': 'testpass',
    }, follow_redirects=True)
    return client


# === Tests de estructura de respuesta ===

def test_dashboard_loads_without_error(logged_client):
    """AC #8: El dashboard carga sin errores."""
    resp = logged_client.get('/dashboard')
    assert resp.status_code == 200


def test_dashboard_no_order_accuracy_in_response(logged_client):
    """AC #3: Order Accuracy eliminado del template."""
    resp = logged_client.get('/dashboard')
    html = resp.data.decode('utf-8')
    # No debe contener la variable antigua normalizada
    assert 'order_accuracy_v' not in html


def test_dashboard_has_order_fill_rate(logged_client):
    """OFR real reemplaza Order Completion Rate en el template."""
    resp = logged_client.get('/dashboard')
    html = resp.data.decode('utf-8')
    assert 'Order Fill Rate' in html


def test_dashboard_has_customer_engagement(logged_client):
    """AC #5: Customer Engagement se muestra en el dashboard."""
    resp = logged_client.get('/dashboard')
    html = resp.data.decode('utf-8')
    assert 'Customer Engagement' in html


# === Tests de cálculo de KPIs (via la función helper interna) ===

def test_kpis_empty_period_returns_defaults(app):
    """calcular_kpis_periodo con lista vacía retorna defaults correctos (sin datos = fallback)."""
    with app.app_context():
        resp = app.test_client()
        resp.post('/login', data={'username': 'admin', 'password': 'testpass'})
        response = resp.get('/dashboard')
        assert response.status_code == 200
        html = response.data.decode('utf-8')
        # Debe contener las claves nuevas en el HTML renderizado
        assert 'order_completion_rate' in html
        assert 'order_accuracy' not in html


def test_kpi_evolution_chart_no_accuracy(logged_client):
    """AC #3: El chart de evolución no tiene dataset de Accuracy."""
    resp = logged_client.get('/dashboard')
    html = resp.data.decode('utf-8')
    assert 'order_accuracy' not in html
    assert "Accuracy (%)" not in html


def test_kpi_evolution_chart_has_ofr(logged_client):
    """El chart de evolución usa OFR."""
    resp = logged_client.get('/dashboard')
    html = resp.data.decode('utf-8')
    assert 'order_completion_rate' in html
    assert "OFR (%)" in html


def test_dashboard_no_palabras_error(app):
    """AC #3: La variable palabras_error ya no se usa en app.py."""
    import inspect
    from app import app as flask_app
    # Leer el source code de la ruta dashboard
    source_file = inspect.getfile(flask_app.__class__)
    with open(os.path.join(os.path.dirname(source_file), 'app.py'), 'r') as f:
        content = f.read()
    # palabras_error ya no debe estar definida
    assert "palabras_error = {" not in content


def test_fallback_data_has_correct_keys(app):
    """AC #7: El fallback_data tiene las claves correctas."""
    with open(os.path.join(os.path.dirname(__file__), '..', 'app.py'), 'r') as f:
        content = f.read()
    # Verificar que fallback_data tiene las nuevas claves
    assert "'order_completion_rate'" in content
    assert "'customer_engagement'" in content
    assert "'perfect_order_rate'" in content
    # Y no tiene las viejas
    assert "'order_accuracy'" not in content.split('fallback_data')[1].split('}')[0]


# === Tests de Story 1.2: Reorganización dashboard y proyección ===

def test_dashboard_has_objetivos_de_ventas_section(logged_client):
    """AC #1: La sección de Ventas está visible en el dashboard."""
    resp = logged_client.get('/dashboard')
    html = resp.data.decode('utf-8')
    assert 'data-panel-label="Ventas"' in html


def test_dashboard_has_nivel_de_servicio_section(logged_client):
    """AC #2: La sección de Servicio está visible en el dashboard."""
    resp = logged_client.get('/dashboard')
    html = resp.data.decode('utf-8')
    assert 'data-panel-label="Servicio"' in html


def test_dashboard_has_proyeccion(logged_client):
    """AC #3/#5: Proyección de ventas se muestra en el dashboard."""
    resp = logged_client.get('/dashboard')
    html = resp.data.decode('utf-8')
    assert 'Proyección' in html or 'proyeccion_ventas' in html


def test_dashboard_has_perfect_order_rate(logged_client):
    """AC #2: Perfect Order Rate visible en Nivel de Servicio."""
    resp = logged_client.get('/dashboard')
    html = resp.data.decode('utf-8')
    assert 'Perfect Order Rate' in html


def test_meta_configurable_env_var(app):
    """AC #4: Meta mensual leída de env var MONTHLY_SALES_TARGET."""
    with open(os.path.join(os.path.dirname(__file__), '..', 'app.py'), 'r') as f:
        content = f.read()
    assert "os.environ.get('MONTHLY_SALES_TARGET'" in content
    # No debe quedar hardcode 120000.00
    assert 'meta_mensual = 120000.00' not in content


def test_fallback_data_has_proyeccion_keys(app):
    """AC #3: fallback_data incluye claves de proyección."""
    with open(os.path.join(os.path.dirname(__file__), '..', 'app.py'), 'r') as f:
        content = f.read()
    fallback_section = content.split('fallback_data')[1].split('}')[0]
    assert "'proyeccion_ventas'" in fallback_section
    assert "'porcentaje_proyeccion'" in fallback_section
    assert "'dias_total_mes'" in fallback_section


def _ventas_mes_en_html(html):
    match = re.search(
        r'Ventas del Mes</span>.*?<div class="tile-value">([^<]+)<small>XCG</small>',
        html,
        flags=re.S
    )
    assert match is not None
    return int(re.sub(r'[^0-9]', '', match.group(1)) or '0')


def _top_producto_1_en_html(html):
    match = re.search(
        r'Top Productos.*?<span class="rr-name">([^<]+)</span>\s*<span class="rr-amount">([^<]+)<small>XCG</small>',
        html,
        flags=re.S
    )
    assert match is not None
    nombre = match.group(1).strip()
    monto = int(re.sub(r'[^0-9]', '', match.group(2)) or '0')
    return nombre, monto


def test_dashboard_ventas_mes_usa_fecha_facturacion_local_y_solo_facturados(app, logged_client):
    """Ventas del mes: solo facturados y clasificados por fecha_facturacion local."""
    from app import db, Cliente, Producto, Pedido, DetallePedido

    tz_cur = ZoneInfo('America/Curacao')
    now_local = datetime.now(tz_cur)
    inicio_mes = now_local.date().replace(day=1)
    ultimo_dia_mes_anterior = inicio_mes - timedelta(days=1)

    # 23:30 del último día del mes anterior en Curazao (UTC cae al día siguiente)
    fecha_fact_prev_local = datetime(
        ultimo_dia_mes_anterior.year, ultimo_dia_mes_anterior.month, ultimo_dia_mes_anterior.day,
        23, 30, tzinfo=tz_cur
    )
    fecha_fact_prev_utc = fecha_fact_prev_local.astimezone(timezone.utc)

    # Facturación válida en mes actual
    fecha_fact_mes_local = datetime(
        inicio_mes.year, inicio_mes.month, inicio_mes.day, 9, 0, tzinfo=tz_cur
    )
    fecha_fact_mes_utc = fecha_fact_mes_local.astimezone(timezone.utc)

    with app.app_context():
        cliente = Cliente(nombre='Cliente Dashboard Ventas')
        producto = Producto(nombre='Producto Dashboard Ventas', tax_rate=0.0, se_pesa=False)
        db.session.add_all([cliente, producto])
        db.session.flush()

        # NO debe contar en ventas del mes (facturado local mes anterior)
        pedido_prev = Pedido(
            cliente_id=cliente.id,
            estado='facturado',
            fecha_pedido=fecha_fact_mes_utc,
            fecha_facturacion=fecha_fact_prev_utc,
            tipo_cambio=1.0
        )
        db.session.add(pedido_prev)
        db.session.flush()
        db.session.add(DetallePedido(
            pedido_id=pedido_prev.id,
            producto_id=producto.id,
            cajas=1,
            cajas_pedidas=1,
            precio_unitario=111,
            subtotal=111,
            es_linea_pedido=True
        ))

        # Debe contar en ventas del mes
        pedido_mes = Pedido(
            cliente_id=cliente.id,
            estado='facturado',
            fecha_pedido=fecha_fact_mes_utc,
            fecha_facturacion=fecha_fact_mes_utc,
            tipo_cambio=1.0
        )
        db.session.add(pedido_mes)
        db.session.flush()
        db.session.add(DetallePedido(
            pedido_id=pedido_mes.id,
            producto_id=producto.id,
            cajas=1,
            cajas_pedidas=1,
            precio_unitario=222,
            subtotal=222,
            es_linea_pedido=True
        ))

        # No facturado: nunca debe entrar a ventas
        pedido_pendiente = Pedido(
            cliente_id=cliente.id,
            estado='pendiente',
            fecha_pedido=fecha_fact_mes_utc,
            tipo_cambio=1.0
        )
        db.session.add(pedido_pendiente)
        db.session.flush()
        db.session.add(DetallePedido(
            pedido_id=pedido_pendiente.id,
            producto_id=producto.id,
            cajas=1,
            cajas_pedidas=1,
            precio_unitario=900,
            subtotal=900,
            es_linea_pedido=True
        ))

        db.session.commit()

    resp = logged_client.get('/dashboard')
    assert resp.status_code == 200
    html = resp.data.decode('utf-8')
    assert _ventas_mes_en_html(html) == 222


def test_dashboard_ventas_mes_cuenta_pedido_creado_antes_si_facturo_este_mes(app, logged_client):
    """Si se facturó este mes, debe contar aunque se creó el mes pasado."""
    from app import db, Cliente, Producto, Pedido, DetallePedido

    tz_cur = ZoneInfo('America/Curacao')
    now_local = datetime.now(tz_cur)
    inicio_mes = now_local.date().replace(day=1)
    dia_mes_pasado = inicio_mes - timedelta(days=5)

    fecha_pedido_utc = datetime(
        dia_mes_pasado.year, dia_mes_pasado.month, dia_mes_pasado.day,
        10, 0, tzinfo=tz_cur
    ).astimezone(timezone.utc)
    fecha_fact_utc = datetime(
        inicio_mes.year, inicio_mes.month, inicio_mes.day,
        11, 0, tzinfo=tz_cur
    ).astimezone(timezone.utc)

    with app.app_context():
        cliente = Cliente(nombre='Cliente Facturado Mes Actual')
        producto = Producto(nombre='Producto Facturado Mes Actual', tax_rate=0.0, se_pesa=False)
        db.session.add_all([cliente, producto])
        db.session.flush()

        pedido = Pedido(
            cliente_id=cliente.id,
            estado='facturado',
            fecha_pedido=fecha_pedido_utc,
            fecha_facturacion=fecha_fact_utc,
            tipo_cambio=1.0
        )
        db.session.add(pedido)
        db.session.flush()
        db.session.add(DetallePedido(
            pedido_id=pedido.id,
            producto_id=producto.id,
            cajas=1,
            cajas_pedidas=1,
            precio_unitario=333,
            subtotal=333,
            es_linea_pedido=True
        ))
        db.session.commit()

    resp = logged_client.get('/dashboard')
    assert resp.status_code == 200
    html = resp.data.decode('utf-8')
    assert _ventas_mes_en_html(html) == 333


def test_dashboard_ventas_mes_no_reconvierte_tipo_cambio(app, logged_client):
    """Ventas del mes debe reflejar subtotal facturado, sin multiplicar por tipo_cambio."""
    from app import db, Cliente, Producto, Pedido, DetallePedido

    tz_cur = ZoneInfo('America/Curacao')
    fecha_fact_utc = datetime.now(tz_cur).astimezone(timezone.utc)

    with app.app_context():
        cliente = Cliente(nombre='Cliente USD Dashboard', moneda='USD')
        producto = Producto(nombre='Producto USD Dashboard', tax_rate=0.0, se_pesa=False)
        db.session.add_all([cliente, producto])
        db.session.flush()

        pedido = Pedido(
            cliente_id=cliente.id,
            estado='facturado',
            fecha_pedido=fecha_fact_utc,
            fecha_facturacion=fecha_fact_utc,
            tipo_cambio=1.78
        )
        db.session.add(pedido)
        db.session.flush()
        db.session.add(DetallePedido(
            pedido_id=pedido.id,
            producto_id=producto.id,
            cajas=1,
            cajas_pedidas=1,
            precio_unitario=100,
            subtotal=100,
            es_linea_pedido=True
        ))
        db.session.commit()

    resp = logged_client.get('/dashboard')
    assert resp.status_code == 200
    html = resp.data.decode('utf-8')
    assert _ventas_mes_en_html(html) == 100


def test_dashboard_ventas_desde_quickbooks_si_fuente_habilitada(app, logged_client, monkeypatch):
    """Si QuickBooks está habilitado, ventas del dashboard deben salir del endpoint N8N/QB."""
    import app as app_module

    tz_cur = ZoneInfo('America/Curacao')
    hoy_local = datetime.now(tz_cur).date()
    called = {}

    class DummyResponse:
        def __init__(self, payload):
            self._payload = payload

        def raise_for_status(self):
            return None

        def json(self):
            return self._payload

    def fake_post(url, json, timeout):
        called['url'] = url
        called['json'] = json
        called['timeout'] = timeout
        return DummyResponse({
            'transactions': [
                {
                    'date': hoy_local.isoformat(),
                    'invoice_number': 'QB-1001',
                    'customer': 'Cliente QB',
                    'product': 'Producto QB',
                    'quantity': 4,
                    'amount': 500
                }
            ]
        })

    monkeypatch.setattr(app_module, 'QB_SALES_SOURCE', 'quickbooks')
    monkeypatch.setattr(app_module, 'N8N_QB_SALES_WEBHOOK_URL', 'https://n8n.test/qb-sales')
    monkeypatch.setattr(app_module, 'N8N_QB_SALES_TIMEOUT', 7)
    monkeypatch.setattr(app_module.requests, 'post', fake_post)

    resp = logged_client.get('/dashboard')
    assert resp.status_code == 200
    html = resp.data.decode('utf-8')

    assert _ventas_mes_en_html(html) == 500
    assert 'Cliente QB' in html
    assert 'Producto QB' in html
    assert called['url'] == 'https://n8n.test/qb-sales'
    expected_timeout = (
        min(7, app_module.N8N_QB_BLOCKING_TIMEOUT_MS / 1000.0)
        if app_module.N8N_QB_BLOCKING_TIMEOUT_MS > 0
        else 7
    )
    assert called['timeout'] == expected_timeout
    assert called['json']['group_by'] == ['day', 'week', 'customer', 'product']


def test_dashboard_ventas_qbo_usd_convierte_a_xcg(app, logged_client, monkeypatch):
    """QBO/USD debe convertirse a XCG cuando incluye exchange_rate válido."""
    import app as app_module

    tz_cur = ZoneInfo('America/Curacao')
    hoy_local = datetime.now(tz_cur).date()

    class DummyResponse:
        def __init__(self, payload):
            self._payload = payload

        def raise_for_status(self):
            return None

        def json(self):
            return self._payload

    def fake_post(url, json, timeout):
        return DummyResponse({
            'transactions': [
                {
                    'date': hoy_local.isoformat(),
                    'invoice_number': 'QB-USD-1001',
                    'customer': 'Cliente Bonaire',
                    'product': 'Producto USD',
                    'currency': 'USD',
                    'exchange_rate': 1.78,
                    'amount': 100
                }
            ]
        })

    monkeypatch.setattr(app_module, 'QB_SALES_SOURCE', 'quickbooks')
    monkeypatch.setattr(app_module, 'N8N_QB_SALES_WEBHOOK_URL', 'https://n8n.test/qb-sales-usd')
    monkeypatch.setattr(app_module, 'N8N_QB_SALES_TIMEOUT', 7)
    monkeypatch.setattr(app_module, '_qb_sales_cache', {
        'key': None,
        'value': None,
        'expires_at': 0.0,
        'stale_expires_at': 0.0,
        'failure_expires_at': 0.0,
        'last_refresh_attempt': 0.0,
    })
    monkeypatch.setattr(app_module.requests, 'post', fake_post)

    resp = logged_client.get('/dashboard')
    assert resp.status_code == 200
    html = resp.data.decode('utf-8')
    assert _ventas_mes_en_html(html) == 178


def test_dashboard_ventas_qbo_usd_tasa_uno_usa_fallback(app, logged_client, monkeypatch):
    """Si QBO/USD retorna exchange_rate=1, dashboard usa fallback configurable."""
    import app as app_module

    tz_cur = ZoneInfo('America/Curacao')
    hoy_local = datetime.now(tz_cur).date()

    class DummyResponse:
        def __init__(self, payload):
            self._payload = payload

        def raise_for_status(self):
            return None

        def json(self):
            return self._payload

    def fake_post(url, json, timeout):
        return DummyResponse({
            'transactions': [
                {
                    'date': hoy_local.isoformat(),
                    'invoice_number': 'QB-USD-1002',
                    'customer': 'Cliente Bonaire',
                    'product': 'Producto USD',
                    'currency': 'USD',
                    'exchange_rate': 1.0,
                    'amount': 100
                }
            ]
        })

    monkeypatch.setattr(app_module, 'QB_SALES_SOURCE', 'quickbooks')
    monkeypatch.setattr(app_module, 'N8N_QB_SALES_WEBHOOK_URL', 'https://n8n.test/qb-sales-usd-fallback')
    monkeypatch.setattr(app_module, 'N8N_QB_SALES_TIMEOUT', 7)
    monkeypatch.setattr(app_module, 'DASHBOARD_USD_TO_XCG_FALLBACK_RATE', 1.78)
    monkeypatch.setattr(app_module, '_qb_sales_cache', {
        'key': None,
        'value': None,
        'expires_at': 0.0,
        'stale_expires_at': 0.0,
        'failure_expires_at': 0.0,
        'last_refresh_attempt': 0.0,
    })
    monkeypatch.setattr(app_module.requests, 'post', fake_post)

    resp = logged_client.get('/dashboard')
    assert resp.status_code == 200
    html = resp.data.decode('utf-8')
    assert _ventas_mes_en_html(html) == 178


def test_dashboard_ventas_qbo_no_sobrescribe_con_summary_sin_convertir(app, logged_client, monkeypatch):
    """Si hay transactions procesables, summary no debe pisar el total convertido."""
    import app as app_module

    tz_cur = ZoneInfo('America/Curacao')
    hoy_local = datetime.now(tz_cur).date()

    class DummyResponse:
        def __init__(self, payload):
            self._payload = payload

        def raise_for_status(self):
            return None

        def json(self):
            return self._payload

    def fake_post(url, json, timeout):
        return DummyResponse({
            'transactions': [
                {
                    'date': hoy_local.isoformat(),
                    'invoice_number': 'QB-USD-2001',
                    'customer': 'Cliente Bonaire',
                    'product': 'Producto USD',
                    'currency': 'USD',
                    'exchange_rate': 1.78,
                    'amount': 100
                }
            ],
            'summary': {
                # Simula summary en USD sin conversión
                'ventas_mes': 100,
                'currency': 'USD',
                'exchange_rate': 1.0
            }
        })

    monkeypatch.setattr(app_module, 'QB_SALES_SOURCE', 'quickbooks')
    monkeypatch.setattr(app_module, 'N8N_QB_SALES_WEBHOOK_URL', 'https://n8n.test/qb-sales-summary')
    monkeypatch.setattr(app_module, 'N8N_QB_SALES_TIMEOUT', 7)
    monkeypatch.setattr(app_module, '_qb_sales_cache', {
        'key': None,
        'value': None,
        'expires_at': 0.0,
        'stale_expires_at': 0.0,
        'failure_expires_at': 0.0,
        'last_refresh_attempt': 0.0,
    })
    monkeypatch.setattr(app_module.requests, 'post', fake_post)

    resp = logged_client.get('/dashboard')
    assert resp.status_code == 200
    html = resp.data.decode('utf-8')
    assert _ventas_mes_en_html(html) == 178


def test_dashboard_ventas_qbo_summary_usd_convierte_cuando_no_hay_filas(app, logged_client, monkeypatch):
    """Si solo hay summary USD (sin transactions), debe convertir a XCG."""
    import app as app_module

    class DummyResponse:
        def __init__(self, payload):
            self._payload = payload

        def raise_for_status(self):
            return None

        def json(self):
            return self._payload

    def fake_post(url, json, timeout):
        return DummyResponse({
            'summary': {
                'ventas_mes': 100,
                'currency': 'USD',
                'exchange_rate': 1.78
            }
        })

    monkeypatch.setattr(app_module, 'QB_SALES_SOURCE', 'quickbooks')
    monkeypatch.setattr(app_module, 'N8N_QB_SALES_WEBHOOK_URL', 'https://n8n.test/qb-sales-summary-only')
    monkeypatch.setattr(app_module, 'N8N_QB_SALES_TIMEOUT', 7)
    monkeypatch.setattr(app_module, '_qb_sales_cache', {
        'key': None,
        'value': None,
        'expires_at': 0.0,
        'stale_expires_at': 0.0,
        'failure_expires_at': 0.0,
        'last_refresh_attempt': 0.0,
    })
    monkeypatch.setattr(app_module.requests, 'post', fake_post)

    resp = logged_client.get('/dashboard')
    assert resp.status_code == 200
    html = resp.data.decode('utf-8')
    assert _ventas_mes_en_html(html) == 178


def test_dashboard_top_productos_prioriza_lineas_preparacion_facturadas(app, logged_client):
    """Top productos debe usar líneas facturadas (preparación), no línea original."""
    from app import db, Cliente, Producto, Pedido, DetallePedido

    tz_cur = ZoneInfo('America/Curacao')
    now_local = datetime.now(tz_cur)
    fecha_fact_utc = now_local.astimezone(timezone.utc)

    with app.app_context():
        cliente = Cliente(nombre='Cliente Top Productos')
        prod_a = Producto(nombre='Producto A', tax_rate=0.0, se_pesa=False)
        prod_b = Producto(nombre='Producto B', tax_rate=0.0, se_pesa=False)
        db.session.add_all([cliente, prod_a, prod_b])
        db.session.flush()

        # Producto A:
        # Línea original alta (1000), línea de preparación real menor (300)
        pedido_a = Pedido(
            cliente_id=cliente.id,
            estado='facturado',
            fecha_pedido=fecha_fact_utc,
            fecha_facturacion=fecha_fact_utc,
            tipo_cambio=1.0
        )
        db.session.add(pedido_a)
        db.session.flush()
        db.session.add_all([
            DetallePedido(
                pedido_id=pedido_a.id,
                producto_id=prod_a.id,
                cajas=10,
                cajas_pedidas=10,
                precio_unitario=100,
                subtotal=1000,
                es_linea_pedido=True
            ),
            DetallePedido(
                pedido_id=pedido_a.id,
                producto_id=prod_a.id,
                cajas=3,
                cajas_pedidas=0,
                precio_unitario=100,
                subtotal=300,
                es_linea_pedido=False
            ),
        ])

        # Producto B:
        # Línea original menor (400), línea de preparación real mayor (500)
        pedido_b = Pedido(
            cliente_id=cliente.id,
            estado='facturado',
            fecha_pedido=fecha_fact_utc,
            fecha_facturacion=fecha_fact_utc,
            tipo_cambio=1.0
        )
        db.session.add(pedido_b)
        db.session.flush()
        db.session.add_all([
            DetallePedido(
                pedido_id=pedido_b.id,
                producto_id=prod_b.id,
                cajas=4,
                cajas_pedidas=4,
                precio_unitario=100,
                subtotal=400,
                es_linea_pedido=True
            ),
            DetallePedido(
                pedido_id=pedido_b.id,
                producto_id=prod_b.id,
                cajas=5,
                cajas_pedidas=0,
                precio_unitario=100,
                subtotal=500,
                es_linea_pedido=False
            ),
        ])
        db.session.commit()

    resp = logged_client.get('/dashboard')
    assert resp.status_code == 200
    html = resp.data.decode('utf-8')
    nombre_top, monto_top = _top_producto_1_en_html(html)

    assert nombre_top == 'Producto B'
    assert monto_top == 500


# ═══════════════════════════════════════════════════════════════
# Bloque 2: Tests de exactitud ventas QBO / fallback
# ═══════════════════════════════════════════════════════════════

def test_dashboard_ventas_qbo_agregados_usd_sin_moneda_usa_monto_directo(app, logged_client, monkeypatch):
    """Agregados diarios sin campo moneda asumen XCG (monto directo sin conversión)."""
    import app as app_module
    from datetime import date

    class DummyResponse:
        def raise_for_status(self): pass
        def json(self):
            hoy = date.today()
            return {
                'daily': [
                    {'date': hoy.isoformat(), 'amount': 200.0}
                ]
            }

    monkeypatch.setattr(app_module, 'QB_SALES_SOURCE', 'quickbooks')
    monkeypatch.setattr(app_module, 'N8N_QB_SALES_WEBHOOK_URL', 'https://n8n.test/qb-agg-no-currency')
    monkeypatch.setattr(app_module, 'N8N_QB_SALES_TIMEOUT', 7)
    monkeypatch.setattr(app_module, '_qb_sales_cache', {
        'key': None, 'value': None, 'expires_at': 0.0,
        'stale_expires_at': 0.0, 'failure_expires_at': 0.0, 'last_refresh_attempt': 0.0,
    })
    monkeypatch.setattr(app_module.requests, 'post', lambda url, json, timeout: DummyResponse())

    resp = logged_client.get('/dashboard')
    assert resp.status_code == 200
    html = resp.data.decode('utf-8')
    # Sin campo moneda → se asume XCG → monto = 200, no se multiplica
    assert _ventas_mes_en_html(html) == 200


def test_dashboard_ventas_qbo_agregados_usd_con_moneda_convierte(app, logged_client, monkeypatch):
    """Agregados diarios con currency=USD deben convertir a XCG."""
    import app as app_module
    from datetime import date

    class DummyResponse:
        def raise_for_status(self): pass
        def json(self):
            hoy = date.today()
            return {
                'daily': [
                    {'date': hoy.isoformat(), 'amount': 100.0,
                     'currency': 'USD', 'exchange_rate': 1.78}
                ]
            }

    monkeypatch.setattr(app_module, 'QB_SALES_SOURCE', 'quickbooks')
    monkeypatch.setattr(app_module, 'N8N_QB_SALES_WEBHOOK_URL', 'https://n8n.test/qb-agg-usd')
    monkeypatch.setattr(app_module, 'N8N_QB_SALES_TIMEOUT', 7)
    monkeypatch.setattr(app_module, '_qb_sales_cache', {
        'key': None, 'value': None, 'expires_at': 0.0,
        'stale_expires_at': 0.0, 'failure_expires_at': 0.0, 'last_refresh_attempt': 0.0,
    })
    monkeypatch.setattr(app_module.requests, 'post', lambda url, json, timeout: DummyResponse())

    resp = logged_client.get('/dashboard')
    assert resp.status_code == 200
    html = resp.data.decode('utf-8')
    assert _ventas_mes_en_html(html) == 178


def test_dashboard_ventas_qbo_agregados_usd_sin_tasa_usa_fallback(app, logged_client, monkeypatch):
    """Agregados USD sin exchange_rate deben usar tasa fallback."""
    import app as app_module
    from datetime import date

    class DummyResponse:
        def raise_for_status(self): pass
        def json(self):
            hoy = date.today()
            return {
                'daily': [
                    {'date': hoy.isoformat(), 'amount': 100.0, 'currency': 'USD'}
                ]
            }

    monkeypatch.setattr(app_module, 'QB_SALES_SOURCE', 'quickbooks')
    monkeypatch.setattr(app_module, 'N8N_QB_SALES_WEBHOOK_URL', 'https://n8n.test/qb-agg-usd-no-rate')
    monkeypatch.setattr(app_module, 'N8N_QB_SALES_TIMEOUT', 7)
    monkeypatch.setattr(app_module, 'DASHBOARD_USD_TO_XCG_FALLBACK_RATE', 1.78)
    monkeypatch.setattr(app_module, '_qb_sales_cache', {
        'key': None, 'value': None, 'expires_at': 0.0,
        'stale_expires_at': 0.0, 'failure_expires_at': 0.0, 'last_refresh_attempt': 0.0,
    })
    monkeypatch.setattr(app_module.requests, 'post', lambda url, json, timeout: DummyResponse())

    resp = logged_client.get('/dashboard')
    assert resp.status_code == 200
    html = resp.data.decode('utf-8')
    # 100 USD × 1.78 fallback = 178 XCG
    assert _ventas_mes_en_html(html) == 178


def test_dashboard_ventas_qbo_transacciones_con_home_amount_prioriza(app, logged_client, monkeypatch):
    """Si el payload trae home_amount (ya en XCG), debe usarlo en vez de convertir."""
    import app as app_module
    from datetime import date

    class DummyResponse:
        def raise_for_status(self): pass
        def json(self):
            hoy = date.today()
            return {
                'transactions': [{
                    'date': hoy.isoformat(),
                    'amount': 100.0,
                    'home_amount': 180.0,
                    'currency': 'USD',
                    'exchange_rate': 1.78,
                    'customer': 'Test',
                }]
            }

    monkeypatch.setattr(app_module, 'QB_SALES_SOURCE', 'quickbooks')
    monkeypatch.setattr(app_module, 'N8N_QB_SALES_WEBHOOK_URL', 'https://n8n.test/qb-home-amount')
    monkeypatch.setattr(app_module, 'N8N_QB_SALES_TIMEOUT', 7)
    monkeypatch.setattr(app_module, '_qb_sales_cache', {
        'key': None, 'value': None, 'expires_at': 0.0,
        'stale_expires_at': 0.0, 'failure_expires_at': 0.0, 'last_refresh_attempt': 0.0,
    })
    monkeypatch.setattr(app_module.requests, 'post', lambda url, json, timeout: DummyResponse())

    resp = logged_client.get('/dashboard')
    assert resp.status_code == 200
    html = resp.data.decode('utf-8')
    # home_amount=180 tiene prioridad sobre amount=100 × 1.78=178
    assert _ventas_mes_en_html(html) == 180


def test_dashboard_ventas_qbo_fallback_timeout_usa_datos_locales(app, logged_client, monkeypatch):
    """Cuando QBO hace timeout sin cache, debe usar datos locales (0 sin pedidos)."""
    import app as app_module
    import requests as req_lib

    monkeypatch.setattr(app_module, 'QB_SALES_SOURCE', 'quickbooks')
    monkeypatch.setattr(app_module, 'N8N_QB_SALES_WEBHOOK_URL', 'https://n8n.test/qb-timeout')
    monkeypatch.setattr(app_module, 'N8N_QB_SALES_TIMEOUT', 1)
    monkeypatch.setattr(app_module, '_qb_sales_cache', {
        'key': None, 'value': None, 'expires_at': 0.0,
        'stale_expires_at': 0.0, 'failure_expires_at': 0.0, 'last_refresh_attempt': 0.0,
    })

    def fake_post_timeout(url, json, timeout):
        raise req_lib.Timeout('Simulated timeout')

    monkeypatch.setattr(app_module.requests, 'post', fake_post_timeout)

    resp = logged_client.get('/dashboard')
    assert resp.status_code == 200
    # Dashboard debe cargar sin error, usando datos locales
    html = resp.data.decode('utf-8')
    assert 'Ventas del Mes' in html


# === Regresión: parseo de fechas de QBO no debe shiftear por timezone ===

def test_parse_dashboard_date_value_pure_date_no_timezone_shift():
    """Un string de solo-fecha (ej. '2026-04-01') debe mantenerse como esa fecha
    local, sin ser tratado como UTC y corrido a '2026-03-31' al convertir a
    America/Curacao. Esto causaba que las ventas del día 1 del mes quedaran
    excluidas del filtro `fecha >= inicio_mes`."""
    from app import _parse_dashboard_date_value

    assert _parse_dashboard_date_value('2026-04-01') == date(2026, 4, 1)
    assert _parse_dashboard_date_value('2026-04-17') == date(2026, 4, 17)
    assert _parse_dashboard_date_value('04/01/2026') == date(2026, 4, 1)
    # Datetime con hora explícita sí debe pasar por conversión de timezone
    assert _parse_dashboard_date_value('2026-04-17T10:30:00Z') == date(2026, 4, 17)
