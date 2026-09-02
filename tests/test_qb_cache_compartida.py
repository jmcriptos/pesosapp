"""La caché de ventas de QuickBooks vive en Postgres, compartida, y nadie la espera.

Diagnóstico del 2026-09-02 en producción: la llamada a n8n/QuickBooks tarda
7,5–7,7 s contra un timeout bloqueante de 8 s; la caché era un dict por
worker (dos workers, dos horas distintas); su clave incluía `hoy`, así que a
medianoche todo lo guardado dejaba de servir y el primero que entraba
esperaba 8 s para, casi siempre, caer a la cifra local —que es otra métrica:
un tercio de las ventas— con sello «Ventas al ahora».

Contrato nuevo:
  - una fila en `ventas_qb_cache` con la respuesta CRUDA de n8n; las ventanas
    de mes y semana se calculan al leer, con la fecha de hoy;
  - al abrir el dashboard nunca se espera a la red: fresca → se usa; vieja
    (< 24 h) → se usa y se refresca por detrás; nada → None y refresco;
  - el throttle entre workers es `last_refresh_attempt` de la fila;
  - sin dato de QuickBooks la pantalla dice «Sin datos de QuickBooks», no
    muestra la cifra local ni el sello.
"""
import json
import os
import re
import threading
import time
from datetime import date, datetime, timedelta, timezone

import pytest

os.environ.setdefault('SECRET_KEY', 'test-secret')
os.environ.setdefault('FLASK_ENV', 'testing')
os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')

import app as app_module
from app import app as flask_app, db as _db


HOY = datetime.now(app_module.DASHBOARD_TIMEZONE).date()
INICIO_MES = HOY.replace(day=1)
MES_PASADO = (INICIO_MES - timedelta(days=1)).replace(day=15)

PAYLOAD = {
    'transactions': [
        {'date': HOY.isoformat(), 'invoice_number': '9001', 'customer': 'Cliente QB',
         'product': 'Producto QB', 'quantity': 4, 'amount': 500,
         'currency_origin': 'ANG', 'fx_applied': 1, 'transaction_type': 'Invoice'},
        {'date': MES_PASADO.isoformat(), 'invoice_number': '9000', 'customer': 'Cliente QB',
         'product': 'Producto QB', 'quantity': 2, 'amount': 300,
         'currency_origin': 'ANG', 'fx_applied': 1, 'transaction_type': 'Invoice'},
    ],
    'summary': {'total_amount': 800, 'total_invoices': 2, 'total_lines': 2},
}


@pytest.fixture
def app():
    flask_app.config.update(
        TESTING=True, WTF_CSRF_ENABLED=False,
        SQLALCHEMY_DATABASE_URI='sqlite:///:memory:',
    )
    with flask_app.app_context():
        _db.create_all()
        from app import Rol, Territorio, Vendedor, Cliente, Producto, Pedido, DetallePedido
        rol = Rol(nombre='super_admin', descripcion='Admin')
        terr = Territorio(nombre='t', descripcion='T')
        _db.session.add_all([rol, terr])
        _db.session.flush()
        v = Vendedor(username='admin', email='a@t.com', nombre_completo='Admin',
                     rol_id=rol.id, territorio_id=terr.id, activo=True)
        v.set_password('testpass')
        cliente = Cliente(nombre='Mangusa Hypermarket')
        producto = Producto(nombre='Boneless Chicken Breast', se_pesa=False, tax_rate=10.0)
        _db.session.add_all([v, cliente, producto])
        _db.session.flush()
        # Un pedido facturado este mes de 100 XCG: la cifra LOCAL que no debe
        # colarse como si fuera de QuickBooks.
        ahora = datetime.now(timezone.utc)
        pedido = Pedido(cliente_id=cliente.id, estado='facturado',
                        fecha_pedido=ahora, fecha_facturacion=ahora)
        _db.session.add(pedido)
        _db.session.flush()
        _db.session.add(DetallePedido(
            pedido_id=pedido.id, producto_id=producto.id, cajas=4, cajas_pedidas=4,
            peso=0, precio_unitario=25, subtotal=100, es_linea_pedido=True,
        ))
        _db.session.commit()
        yield flask_app
        _db.session.remove()
        _db.drop_all()


@pytest.fixture
def logged_client(app):
    c = app.test_client()
    c.post('/login', data={'username': 'admin', 'password': 'testpass'},
           follow_redirects=True)
    return c


def _fechas():
    return app_module._fechas_ventas_quickbooks()


def _args():
    f = _fechas()
    return (f['hoy'], f['inicio_mes'], f['inicio_semana'], f['inicio_mes_anterior'],
            f['fin_mes_anterior'], f['inicio_tendencia'], f['inicio_ultimos_7_dias'])


class _Respuesta:
    status_code = 200

    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


def _preparar(monkeypatch, demora=0.0, payload=None, falla=None):
    """QuickBooks habilitado y `requests.post` falso que cuenta llamadas."""
    llamadas = {'n': 0, 'timeouts': []}

    def fake_post(*_a, **kw):
        llamadas['n'] += 1
        llamadas['timeouts'].append(kw.get('timeout'))
        if demora:
            time.sleep(demora)
        if falla:
            raise falla
        return _Respuesta(payload if payload is not None else PAYLOAD)

    monkeypatch.setattr(app_module, 'QB_SALES_SOURCE', 'quickbooks')
    monkeypatch.setattr(app_module, 'N8N_QB_SALES_WEBHOOK_URL', 'https://n8n.test/qb-compartida')
    monkeypatch.setattr(app_module, 'N8N_QB_SALES_TIMEOUT', 20)
    monkeypatch.setattr(app_module, '_qb_refresh_en_curso', False, raising=False)
    monkeypatch.setattr(app_module.requests, 'post', fake_post)
    return llamadas


def _esperar_hilo(nombre='qb-sales-refresh', limite=5.0):
    fin = time.perf_counter() + limite
    while time.perf_counter() < fin:
        if not any(t.name == nombre for t in threading.enumerate()):
            return True
        time.sleep(0.02)
    return False


def _sembrar_fila(hace=timedelta(0), payload=None, intento_hace=None, raw=True):
    """Deja en la base la fila de caché con la respuesta cruda de n8n."""
    from app import VentasQbCache
    ahora = datetime.now(timezone.utc).replace(tzinfo=None)
    fila = VentasQbCache(
        id=1,
        raw_json=json.dumps(payload if payload is not None else PAYLOAD) if raw else None,
        fetched_at=(ahora - hace) if raw else None,
        last_refresh_attempt=(ahora - intento_hace) if intento_hace is not None else None,
    )
    _db.session.merge(fila)
    _db.session.commit()
    return fila


def _fila():
    from app import VentasQbCache
    _db.session.expire_all()
    return _db.session.get(VentasQbCache, 1)


# ─────────────────────────────────────────── la lectura nunca espera a la red


def test_sin_fila_devuelve_none_al_instante_y_refresca_por_detras(app, monkeypatch):
    """El arranque en frío ya no bloquea: antes era «el único caso» que esperaba."""
    llamadas = _preparar(monkeypatch, demora=1.0)

    inicio = time.perf_counter()
    resultado = app_module._obtener_metricas_ventas_quickbooks(*_args())
    transcurrido = time.perf_counter() - inicio

    assert resultado is None
    assert transcurrido < 0.5, f'bloqueó {transcurrido:.2f}s'
    assert _esperar_hilo(), 'el refresco no terminó'
    assert llamadas['n'] == 1

    fila = _fila()
    assert fila is not None and fila.fetched_at is not None
    assert json.loads(fila.raw_json)['summary']['total_invoices'] == 2

    # La segunda lectura ya sirve el dato, sin red.
    de_nuevo = app_module._obtener_metricas_ventas_quickbooks(*_args())
    assert de_nuevo['ventas_mes'] == 500.0
    assert llamadas['n'] == 1


def test_fila_fresca_se_sirve_sin_tocar_la_red(app, monkeypatch):
    llamadas = _preparar(monkeypatch)
    _sembrar_fila(hace=timedelta(seconds=30))

    resultado = app_module._obtener_metricas_ventas_quickbooks(*_args())

    assert resultado['ventas_mes'] == 500.0
    assert resultado['ventas_mes_anterior'] == 300.0
    _esperar_hilo(limite=0.3)
    assert llamadas['n'] == 0


def test_fila_vieja_se_sirve_y_se_refresca_por_detras(app, monkeypatch):
    llamadas = _preparar(monkeypatch, demora=0.3)
    _sembrar_fila(hace=timedelta(minutes=10))
    antes = _fila().fetched_at

    inicio = time.perf_counter()
    resultado = app_module._obtener_metricas_ventas_quickbooks(*_args())
    assert time.perf_counter() - inicio < 0.2

    assert resultado['ventas_mes'] == 500.0
    assert _esperar_hilo()
    assert llamadas['n'] == 1
    assert _fila().fetched_at > antes


def test_fila_vencida_no_se_sirve_pero_dispara_refresco(app, monkeypatch):
    """Más de 24 h: mejor «sin datos» que una cifra de anteayer."""
    llamadas = _preparar(monkeypatch, demora=0.05)
    _sembrar_fila(hace=timedelta(hours=25))

    resultado = app_module._obtener_metricas_ventas_quickbooks(*_args())

    assert resultado is None
    assert _esperar_hilo()
    assert llamadas['n'] == 1


def test_dentro_del_throttle_de_la_fila_no_refresca(app, monkeypatch):
    """El throttle es la fila, no el proceso: así los dos workers se coordinan."""
    llamadas = _preparar(monkeypatch)
    _sembrar_fila(hace=timedelta(minutes=10), intento_hace=timedelta(seconds=5))

    resultado = app_module._obtener_metricas_ventas_quickbooks(*_args())

    assert resultado['ventas_mes'] == 500.0
    _esperar_hilo(limite=0.3)
    assert llamadas['n'] == 0


def test_el_refresco_usa_el_timeout_completo(app, monkeypatch):
    """Nadie espera en el hilo: 20 s, no el presupuesto de usuario."""
    llamadas = _preparar(monkeypatch)
    monkeypatch.setattr(app_module, 'N8N_QB_SALES_TIMEOUT', 20)

    app_module._obtener_metricas_ventas_quickbooks(*_args())

    assert _esperar_hilo()
    assert llamadas['timeouts'] == [20.0]


def test_un_fallo_deja_rastro_y_conserva_la_fila(app, monkeypatch):
    import requests as _rq
    llamadas = _preparar(monkeypatch, falla=_rq.RequestException('n8n caído'))
    _sembrar_fila(hace=timedelta(minutes=10))
    antes = _fila().fetched_at

    resultado = app_module._obtener_metricas_ventas_quickbooks(*_args())

    assert resultado['ventas_mes'] == 500.0
    assert _esperar_hilo()
    assert llamadas['n'] == 1
    fila = _fila()
    assert fila.fetched_at == antes
    assert 'n8n caído' in (fila.last_error or '')
    assert fila.last_refresh_attempt is not None


# ──────────────────────────────────── el dato crudo se interpreta al leer


def test_las_ventanas_se_calculan_al_leer_no_al_guardar(app, monkeypatch):
    """Por eso la fila no caduca a medianoche: la misma respuesta cruda
    responde a «este mes» con la fecha del día que la lee."""
    _preparar(monkeypatch)
    _sembrar_fila(hace=timedelta(hours=1))
    hoy, inicio_mes, inicio_semana, imant, fmant, tendencia, u7 = _args()

    de_este_mes = app_module._obtener_metricas_ventas_quickbooks(
        hoy, inicio_mes, inicio_semana, imant, fmant, tendencia, u7)
    # Si «el mes» empezara el día 16 del mes pasado, la fila del 15 no cuenta
    # y la de hoy sí: mismo crudo, otra ventana.
    inicio_alterno = MES_PASADO + timedelta(days=1)
    alterno = app_module._obtener_metricas_ventas_quickbooks(
        hoy, inicio_alterno, inicio_semana, imant, fmant, tendencia, u7)

    assert de_este_mes['ventas_mes'] == 500.0
    assert alterno['ventas_mes'] == 500.0
    assert de_este_mes['ventas_mes_anterior'] == 300.0


def test_el_sello_es_la_hora_de_la_fila(app, monkeypatch):
    _preparar(monkeypatch)
    _sembrar_fila(hace=timedelta(hours=3))

    sello = app_module._qb_datos_traidos_en()

    assert sello is not None
    edad_horas = (time.time() - sello.timestamp()) / 3600
    assert 2.9 < edad_horas < 3.1, f'el sello dice {edad_horas:.2f}h'


def test_sin_fila_no_hay_sello(app, monkeypatch):
    _preparar(monkeypatch)
    assert app_module._qb_datos_traidos_en() is None


# ─────────────────────────────────────────── la pantalla no disfraza la fuente


def _ventas_del_mes(html):
    m = re.search(r'Ventas del Mes</div>\s*<div class="kpi-value[^"]*">([^<]*)', html, flags=re.S)
    assert m is not None, 'no encontré la tarjeta Ventas del Mes'
    return m.group(1).strip()


def test_dashboard_sin_datos_de_quickbooks_no_muestra_la_cifra_local(app, logged_client, monkeypatch):
    """El caso de producción: sin dato de QuickBooks la pantalla mostraba los
    100 XCG del pedido local con sello «Ventas al ahora»."""
    _preparar(monkeypatch, demora=0.5)

    html = logged_client.get('/dashboard').get_data(as_text=True)

    assert 'Sin datos de QuickBooks' in html
    assert 'Ventas al ' not in html
    assert _ventas_del_mes(html) == 'Sin datos'
    # Ni la semana: el 100 del pedido local no se cuela en la tarjeta de ventas.
    assert re.search(r'class="chart-big[^"]*">100<small>', html) is None
    _esperar_hilo()


def test_dashboard_con_fila_muestra_quickbooks_y_su_sello(app, logged_client, monkeypatch):
    _preparar(monkeypatch)
    _sembrar_fila(hace=timedelta(minutes=2))

    html = logged_client.get('/dashboard').get_data(as_text=True)

    assert 'Sin datos de QuickBooks' not in html
    assert 'Ventas al ' in html
    assert _ventas_del_mes(html) == '500'


def test_dashboard_con_fuente_local_explicita_lo_dice(app, logged_client, monkeypatch):
    """Solo cuando la configuración pide la app como fuente se muestra la cifra
    local, y entonces se llama por su nombre."""
    monkeypatch.setattr(app_module, 'QB_SALES_SOURCE', 'local')
    monkeypatch.setattr(app_module, 'N8N_QB_SALES_WEBHOOK_URL', '')

    html = logged_client.get('/dashboard').get_data(as_text=True)

    assert 'registradas en la app' in html
    assert 'Sin datos de QuickBooks' not in html
    assert _ventas_del_mes(html) == '100'
