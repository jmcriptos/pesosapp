"""La caché de ventas de QuickBooks se refresca sin bloquear al usuario.

La llamada a n8n/QuickBooks tarda ~7,6s en producción y agota los 8s de
timeout con frecuencia. Antes, el primero que abría el dashboard después de
vencer el TTL se comía esa espera entera dentro del request.
"""
import time
import threading

import app as app_module


FECHAS = None


def _fechas():
    """Los siete argumentos de fecha que pide la función, en orden."""
    from datetime import date, timedelta
    hoy = date(2026, 8, 30)
    return (
        hoy,                                  # hoy
        date(2026, 8, 1),                     # inicio_mes
        hoy - timedelta(days=hoy.weekday()),  # inicio_semana
        date(2026, 7, 1),                     # inicio_mes_anterior
        date(2026, 7, 31),                    # fin_mes_anterior
        date(2026, 3, 2),                     # inicio_tendencia
        hoy - timedelta(days=6),              # inicio_ultimos_7_dias
    )


def _clave_de_cache(url, args):
    hoy, _, _, _, _, inicio_tendencia, _ = args
    return (url, inicio_tendencia.isoformat(), hoy.isoformat(), str(app_module.DASHBOARD_TIMEZONE))


class _RespuestaFalsa:
    status_code = 200

    def raise_for_status(self):
        return None

    def json(self):
        return {'transactions': [], 'summary': {}}


def _preparar(monkeypatch, url, demora, args, cache):
    llamadas = {'n': 0}

    def fake_post(*_a, **_kw):
        llamadas['n'] += 1
        time.sleep(demora)
        return _RespuestaFalsa()

    monkeypatch.setattr(app_module, 'QB_SALES_SOURCE', 'quickbooks')
    monkeypatch.setattr(app_module, 'N8N_QB_SALES_WEBHOOK_URL', url)
    monkeypatch.setattr(app_module, 'N8N_QB_SALES_TIMEOUT', 20)
    monkeypatch.setattr(app_module, '_qb_sales_cache', cache)
    # raising=False: sin el arreglo el símbolo no existe, y lo que tiene que
    # fallar es la aserción de que no bloquea, no el monkeypatch.
    monkeypatch.setattr(app_module, '_qb_refresh_en_curso', False, raising=False)
    monkeypatch.setattr(app_module.requests, 'post', fake_post)
    return llamadas


def _esperar_hilo_nombre(nombre, limite=5.0):
    """Espera a que no quede ningún hilo con ese nombre (o se rinde)."""
    fin = time.perf_counter() + limite
    while time.perf_counter() < fin:
        if not any(t.name == nombre for t in threading.enumerate()):
            return True
        time.sleep(0.02)
    return False


def _esperar_hilo(limite=5.0):
    return _esperar_hilo_nombre('qb-sales-refresh', limite)


def test_con_cache_stale_devuelve_al_instante_y_refresca_por_detras(monkeypatch):
    """El caso que causaba la página de 8 segundos."""
    url = 'https://n8n.test/qb-sales-bg'
    args = _fechas()
    ahora = time.time()
    valor_viejo = {'ventas_mes': 111.0}
    cache = {
        'key': _clave_de_cache(url, args),
        'value': valor_viejo,
        'expires_at': ahora - 1,          # TTL fresco vencido
        'stale_expires_at': ahora + 900,  # pero todavía servible
        'failure_expires_at': 0.0,
        'last_refresh_attempt': 0.0,      # fuera del throttle
    }
    llamadas = _preparar(monkeypatch, url, demora=1.5, args=args, cache=cache)

    inicio = time.perf_counter()
    resultado = app_module._obtener_metricas_ventas_quickbooks(*args)
    transcurrido = time.perf_counter() - inicio

    # Devuelve lo cacheado sin esperar el 1,5s de la red.
    assert resultado is valor_viejo
    assert transcurrido < 0.5, f'la llamada bloqueó {transcurrido:.2f}s'

    # Y el refresco sí ocurrió, en segundo plano.
    assert _esperar_hilo(), 'el hilo de refresco no terminó'
    assert llamadas['n'] == 1, 'el refresco en segundo plano no llamó a la red'


def test_dentro_del_throttle_no_dispara_refresco(monkeypatch):
    url = 'https://n8n.test/qb-sales-throttle'
    args = _fechas()
    ahora = time.time()
    valor_viejo = {'ventas_mes': 222.0}
    cache = {
        'key': _clave_de_cache(url, args),
        'value': valor_viejo,
        'expires_at': ahora - 1,
        'stale_expires_at': ahora + 900,
        'failure_expires_at': 0.0,
        'last_refresh_attempt': ahora,  # recién intentado
    }
    llamadas = _preparar(monkeypatch, url, demora=0.05, args=args, cache=cache)

    resultado = app_module._obtener_metricas_ventas_quickbooks(*args)

    assert resultado is valor_viejo
    _esperar_hilo(limite=0.5)
    assert llamadas['n'] == 0, 'no debía tocar la red dentro del throttle'


def test_arranque_en_frio_si_espera(monkeypatch):
    """Sin nada que mostrar, la primera llamada sí bloquea: es el único caso."""
    url = 'https://n8n.test/qb-sales-frio'
    args = _fechas()
    cache = {
        'key': None,
        'value': None,
        'expires_at': 0.0,
        'stale_expires_at': 0.0,
        'failure_expires_at': 0.0,
        'last_refresh_attempt': 0.0,
    }
    llamadas = _preparar(monkeypatch, url, demora=0.05, args=args, cache=cache)

    resultado = app_module._obtener_metricas_ventas_quickbooks(*args)

    assert llamadas['n'] == 1
    assert resultado is not None
    assert app_module._qb_sales_cache['value'] is resultado


def test_un_solo_hilo_de_refresco_a_la_vez(monkeypatch):
    url = 'https://n8n.test/qb-sales-unico'
    args = _fechas()
    ahora = time.time()
    cache = {
        'key': _clave_de_cache(url, args),
        'value': {'ventas_mes': 333.0},
        'expires_at': ahora - 1,
        'stale_expires_at': ahora + 900,
        'failure_expires_at': 0.0,
        'last_refresh_attempt': 0.0,
    }
    llamadas = _preparar(monkeypatch, url, demora=0.4, args=args, cache=cache)

    for _ in range(5):
        app_module._obtener_metricas_ventas_quickbooks(*args)

    assert _esperar_hilo(), 'el hilo de refresco no terminó'
    assert llamadas['n'] == 1, f'se dispararon {llamadas["n"]} refrescos en paralelo'


# ── Precalentamiento al arrancar el worker ──────────────────────────────────

def test_precalentamiento_no_corre_en_tests(monkeypatch):
    """El guard de testing evita que el import salga a la red en la suite."""
    monkeypatch.setenv('FLASK_ENV', 'testing')
    monkeypatch.setattr(app_module, 'N8N_QB_SALES_WEBHOOK_URL', 'https://n8n.test/no-tocar')
    llamado = {'n': 0}
    monkeypatch.setattr(app_module, '_obtener_metricas_ventas_quickbooks',
                        lambda **_kw: llamado.__setitem__('n', llamado['n'] + 1))

    app_module._precalentar_cache_qb()

    _esperar_hilo_nombre('qb-sales-warmup', limite=0.5)
    assert llamado['n'] == 0


def test_precalentamiento_no_corre_sin_webhook(monkeypatch):
    monkeypatch.delenv('FLASK_ENV', raising=False)
    monkeypatch.delenv('PYTEST_CURRENT_TEST', raising=False)
    monkeypatch.setattr(app_module, 'N8N_QB_SALES_WEBHOOK_URL', '')
    llamado = {'n': 0}
    monkeypatch.setattr(app_module, '_obtener_metricas_ventas_quickbooks',
                        lambda **_kw: llamado.__setitem__('n', llamado['n'] + 1))

    app_module._precalentar_cache_qb()

    _esperar_hilo_nombre('qb-sales-warmup', limite=0.5)
    assert llamado['n'] == 0


def test_precalentamiento_llena_la_cache_en_segundo_plano(monkeypatch):
    """Con QuickBooks habilitado, el arranque calienta la caché sin bloquear."""
    monkeypatch.delenv('FLASK_ENV', raising=False)
    monkeypatch.delenv('PYTEST_CURRENT_TEST', raising=False)
    monkeypatch.setattr(app_module, 'QB_SALES_SOURCE', 'quickbooks')
    monkeypatch.setattr(app_module, 'N8N_QB_SALES_WEBHOOK_URL', 'https://n8n.test/warmup')
    llamado = {'n': 0}

    def falso(**kw):
        llamado['n'] += 1
        llamado['kw'] = kw

    monkeypatch.setattr(app_module, '_obtener_metricas_ventas_quickbooks', falso)

    inicio = time.perf_counter()
    app_module._precalentar_cache_qb()
    transcurrido = time.perf_counter() - inicio

    assert transcurrido < 0.2, 'el precalentamiento no debe bloquear el import'
    assert _esperar_hilo_nombre('qb-sales-warmup'), 'el hilo no terminó'
    assert llamado['n'] == 1
    # Nadie espera en ese hilo: tiene que usar el timeout completo, no el
    # presupuesto de 8s pensado para una petición de usuario.
    assert llamado['kw'].get('_refrescando') is True


def test_las_fechas_del_helper_son_las_que_usa_la_clave_de_cache():
    """El dashboard y el precalentamiento tienen que compartir clave."""
    f = app_module._fechas_ventas_quickbooks()
    assert set(f) == {
        'hoy', 'inicio_mes', 'inicio_semana', 'inicio_mes_anterior',
        'fin_mes_anterior', 'inicio_tendencia', 'inicio_ultimos_7_dias',
    }
    assert f['inicio_semana'].weekday() == 0
    assert f['inicio_mes'].day == 1
    assert (f['inicio_semana'] - f['inicio_tendencia']).days == 25 * 7
    assert f['fin_mes_anterior'] < f['inicio_mes']
    assert f['inicio_mes_anterior'].day == 1


# ── Sello de frescura ───────────────────────────────────────────────────────

def test_sin_datos_traidos_no_hay_sello(monkeypatch):
    monkeypatch.setattr(app_module, '_qb_sales_cache', {
        'key': None, 'value': None, 'expires_at': 0.0, 'stale_expires_at': 0.0,
        'failure_expires_at': 0.0, 'last_refresh_attempt': 0.0,
    })
    assert app_module._qb_datos_traidos_en() is None


def test_el_sello_es_la_hora_del_dato_no_la_del_render(monkeypatch):
    """El caso que motivó el arreglo.

    Con la ventana stale en 24h un valor servido puede tener horas encima. El
    sello tiene que decir cuándo se trajo, no cuándo se dibujó la pantalla.
    """
    url = 'https://n8n.test/qb-sello'
    args = _fechas()
    ahora = time.time()
    hace_20_horas = ahora - 20 * 3600
    valor = {'ventas_mes': 999.0}
    cache = {
        'key': _clave_de_cache(url, args),
        'value': valor,
        'expires_at': ahora - 1,             # ya no está fresco
        'stale_expires_at': ahora + 4 * 3600,  # pero sigue servible (24h)
        'failure_expires_at': 0.0,
        'last_refresh_attempt': ahora,       # dentro del throttle: sin refresco
        'fetched_at': hace_20_horas,
    }
    llamadas = _preparar(monkeypatch, url, demora=0.05, args=args, cache=cache)

    resultado = app_module._obtener_metricas_ventas_quickbooks(*args)
    assert resultado is valor
    assert llamadas['n'] == 0

    sello = app_module._qb_datos_traidos_en()
    assert sello is not None
    edad_horas = (time.time() - sello.timestamp()) / 3600
    assert 19.5 < edad_horas < 20.5, f'el sello dice {edad_horas:.1f}h, debía decir ~20h'


def test_una_consulta_exitosa_deja_su_marca(monkeypatch):
    url = 'https://n8n.test/qb-sello-nuevo'
    args = _fechas()
    cache = {
        'key': None, 'value': None, 'expires_at': 0.0, 'stale_expires_at': 0.0,
        'failure_expires_at': 0.0, 'last_refresh_attempt': 0.0,
    }
    _preparar(monkeypatch, url, demora=0.02, args=args, cache=cache)

    app_module._obtener_metricas_ventas_quickbooks(*args)

    sello = app_module._qb_datos_traidos_en()
    assert sello is not None
    assert abs(time.time() - sello.timestamp()) < 10


def test_un_fallo_no_borra_la_marca_del_valor_que_sigue_sirviendo(monkeypatch):
    """Si la consulta falla pero se sigue mostrando el valor viejo, el sello
    tiene que seguir siendo el de ese valor viejo."""
    import requests as _rq
    url = 'https://n8n.test/qb-sello-fallo'
    args = _fechas()
    ahora = time.time()
    hace_3_horas = ahora - 3 * 3600
    valor = {'ventas_mes': 777.0}
    cache = {
        'key': _clave_de_cache(url, args),
        'value': valor,
        'expires_at': ahora - 1,
        'stale_expires_at': ahora + 3600,
        'failure_expires_at': 0.0,
        'last_refresh_attempt': 0.0,
        'fetched_at': hace_3_horas,
    }
    _preparar(monkeypatch, url, demora=0.01, args=args, cache=cache)

    def revienta(*_a, **_kw):
        raise _rq.RequestException('n8n caído')

    monkeypatch.setattr(app_module.requests, 'post', revienta)

    # `_refrescando=True` recorre el camino de red directo, como el hilo.
    app_module._obtener_metricas_ventas_quickbooks(*args, _refrescando=True)

    sello = app_module._qb_datos_traidos_en()
    assert sello is not None
    edad_horas = (time.time() - sello.timestamp()) / 3600
    assert 2.5 < edad_horas < 3.5, f'el sello dice {edad_horas:.1f}h, debía conservar ~3h'


# ── Kilos y cajas ───────────────────────────────────────────────────────────

def test_kilos_usa_la_bascula_cuando_hay_cajas_pesadas():
    """La báscula manda sobre el peso declarado en la línea.

    Verificado además contra los 185 pedidos con cajas pesadas de producción
    el 2026-08-30, comparando cada uno contra un SUM directo sobre
    caja_pesada: cero discrepancias.
    """
    class Producto:
        def __init__(self, se_pesa): self.se_pesa = se_pesa

    class Detalle:
        def __init__(self, original, producto_id, producto, peso=0, cajas=0,
                     peso_real=0, n_cajas=0):
            self.es_linea_pedido = original
            self.producto_id = producto_id
            self.producto = producto
            self.peso = peso
            self.cajas = cajas
            self.peso_real = peso_real
            self.cajas_pesadas_count = n_cajas

    class Pedido:
        def __init__(self, detalles): self.detalles = detalles

    pesable = Producto(True)
    por_caja = Producto(False)

    # La línea original declara 20 kg pero la báscula midió 18,4: manda la báscula.
    ped = Pedido([
        Detalle(True, 1, pesable, peso=20, cajas=2, peso_real=18.4, n_cajas=2),
        Detalle(True, 2, por_caja, peso=0, cajas=3),
    ])
    kg, cajas = app_module._kilos_y_cajas_pedido(ped)
    assert abs(kg - 18.4) < 0.001, f'debía tomar el peso de báscula, tomó {kg}'
    assert abs(cajas - 5) < 0.001, f'2 pesadas + 3 por caja = 5, dio {cajas}'


def test_kilos_no_cuenta_dos_veces_la_linea_de_preparacion():
    class Producto:
        def __init__(self, se_pesa): self.se_pesa = se_pesa

    class Detalle:
        def __init__(self, original, producto_id, producto, peso=0, cajas=0,
                     peso_real=0, n_cajas=0):
            self.es_linea_pedido = original
            self.producto_id = producto_id
            self.producto = producto
            self.peso = peso
            self.cajas = cajas
            self.peso_real = peso_real
            self.cajas_pesadas_count = n_cajas

    class Pedido:
        def __init__(self, detalles): self.detalles = detalles

    pesable = Producto(True)
    # Producto pesable con báscula Y con línea de preparación: la prep no suma.
    ped = Pedido([
        Detalle(True, 1, pesable, peso=20, peso_real=18.4, n_cajas=2),
        Detalle(False, 1, pesable, peso=18.4, cajas=2),
    ])
    kg, cajas = app_module._kilos_y_cajas_pedido(ped)
    assert abs(kg - 18.4) < 0.001, f'no debía sumar la prep encima, dio {kg}'
    assert abs(cajas - 2) < 0.001, f'dio {cajas} cajas'
