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
