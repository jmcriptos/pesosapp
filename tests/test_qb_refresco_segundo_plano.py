"""Precalentamiento de la caché de ventas de QuickBooks al arrancar el worker.

La lectura de la caché (fila compartida en Postgres, sin bloqueo) se prueba
en test_qb_cache_compartida.py. Acá queda el arranque: que no salga a la red
en tests, que no salga sin webhook, y que cuando sale lo haga en un hilo, con
el timeout completo.
"""
import time
import threading
from datetime import datetime

import app as app_module


def _esperar_hilo_nombre(nombre, limite=5.0):
    """Espera a que no quede ningún hilo con ese nombre (o se rinde)."""
    fin = time.perf_counter() + limite
    while time.perf_counter() < fin:
        if not any(t.name == nombre for t in threading.enumerate()):
            return True
        time.sleep(0.02)
    return False


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
    """Con QuickBooks habilitado y el warmup pedido, calienta sin bloquear."""
    monkeypatch.delenv('FLASK_ENV', raising=False)
    monkeypatch.delenv('PYTEST_CURRENT_TEST', raising=False)
    monkeypatch.setenv('QB_WARMUP_ON_BOOT', 'true')
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


# ── Ventana de refresco: el plan de n8n se cobra por ejecución ──────────────
#
# El 2026-09-11 la instancia de n8n llegó al 100% de su cuota mensual. El bucle
# periódico corría cada 300 s las 24 h: 288 ejecuciones/día (~8.600/mes) que
# nadie pidió. Estos tests fijan que el bucle no salga a la red de madrugada ni
# en domingo, y que el default del intervalo no vuelva a 300 s por descuido.

def _momento(dia, hora):
    """Un datetime en hora de Curaçao. `dia` es weekday(): lunes=0."""
    # 2026-09-07 fue lunes, así que sumar `dia` da el weekday buscado.
    return datetime(2026, 9, 7 + dia, hora, 0, tzinfo=app_module.DASHBOARD_TIMEZONE)


def test_ventana_abierta_en_horario_laboral(monkeypatch):
    monkeypatch.setattr(app_module, 'N8N_QB_REFRESH_HORA_INICIO', 6)
    monkeypatch.setattr(app_module, 'N8N_QB_REFRESH_HORA_FIN', 19)
    monkeypatch.setattr(app_module, 'N8N_QB_REFRESH_DIAS', frozenset(range(0, 6)))

    assert app_module._dentro_de_ventana_refresco(_momento(0, 6)) is True   # lunes al abrir
    assert app_module._dentro_de_ventana_refresco(_momento(2, 13)) is True  # miércoles mediodía
    assert app_module._dentro_de_ventana_refresco(_momento(5, 18)) is True  # sábado, último tramo


def test_ventana_cerrada_de_madrugada_y_en_domingo(monkeypatch):
    monkeypatch.setattr(app_module, 'N8N_QB_REFRESH_HORA_INICIO', 6)
    monkeypatch.setattr(app_module, 'N8N_QB_REFRESH_HORA_FIN', 19)
    monkeypatch.setattr(app_module, 'N8N_QB_REFRESH_DIAS', frozenset(range(0, 6)))

    assert app_module._dentro_de_ventana_refresco(_momento(1, 3)) is False   # martes 3 a.m.
    assert app_module._dentro_de_ventana_refresco(_momento(1, 19)) is False  # fin exclusivo
    assert app_module._dentro_de_ventana_refresco(_momento(6, 12)) is False  # domingo


def test_ventana_de_24h_cuando_inicio_y_fin_coinciden(monkeypatch):
    """Escape hatch: quien quiera el comportamiento viejo lo pide explícito."""
    monkeypatch.setattr(app_module, 'N8N_QB_REFRESH_HORA_INICIO', 0)
    monkeypatch.setattr(app_module, 'N8N_QB_REFRESH_HORA_FIN', 0)
    monkeypatch.setattr(app_module, 'N8N_QB_REFRESH_DIAS', frozenset(range(0, 7)))

    assert app_module._dentro_de_ventana_refresco(_momento(1, 3)) is True
    assert app_module._dentro_de_ventana_refresco(_momento(6, 23)) is True


def test_ventana_que_cruza_la_medianoche(monkeypatch):
    monkeypatch.setattr(app_module, 'N8N_QB_REFRESH_HORA_INICIO', 22)
    monkeypatch.setattr(app_module, 'N8N_QB_REFRESH_HORA_FIN', 6)
    monkeypatch.setattr(app_module, 'N8N_QB_REFRESH_DIAS', frozenset(range(0, 7)))

    assert app_module._dentro_de_ventana_refresco(_momento(1, 23)) is True
    assert app_module._dentro_de_ventana_refresco(_momento(1, 2)) is True
    assert app_module._dentro_de_ventana_refresco(_momento(1, 12)) is False


def test_refresco_periodico_viene_apagado_de_fabrica():
    """JM lo pidió apagado: las ejecuciones son para la facturación."""
    assert app_module.N8N_QB_REFRESH_INTERVAL_SEC == 0


def test_precalentamiento_de_arranque_viene_apagado_de_fabrica(monkeypatch):
    """Heroku recicla dynos a diario; cada arranque gastaba una ejecución."""
    monkeypatch.delenv('QB_WARMUP_ON_BOOT', raising=False)
    monkeypatch.delenv('FLASK_ENV', raising=False)
    monkeypatch.delenv('PYTEST_CURRENT_TEST', raising=False)
    monkeypatch.setattr(app_module, 'QB_SALES_SOURCE', 'quickbooks')
    monkeypatch.setattr(app_module, 'N8N_QB_SALES_WEBHOOK_URL', 'https://n8n.test/no-tocar')
    llamado = {'n': 0}
    monkeypatch.setattr(app_module, '_obtener_metricas_ventas_quickbooks',
                        lambda **_kw: llamado.__setitem__('n', llamado['n'] + 1))

    app_module._precalentar_cache_qb()

    _esperar_hilo_nombre('qb-sales-warmup', limite=0.5)
    assert llamado['n'] == 0, 'el arranque no debe salir a n8n sin que se lo pidan'


def test_intervalo_en_cero_no_levanta_el_hilo_periodico(monkeypatch):
    """Con 0 no hay bucle: ni un solo hilo tocando n8n por su cuenta."""
    monkeypatch.setattr(app_module, 'N8N_QB_REFRESH_INTERVAL_SEC', 0)
    monkeypatch.setattr(app_module, '_qb_periodico_iniciado', False)

    app_module._iniciar_refresco_periodico_qb()

    assert not any(t.name == 'qb-sales-periodico' for t in threading.enumerate())
    assert app_module._qb_periodico_iniciado is False, 'no debe marcarse iniciado'


def test_dias_de_refresco_se_parsean_desde_rango_o_lista():
    parsear = app_module._parsear_dias_refresco
    assert parsear('0-5') == set(range(0, 6))
    assert parsear('0,2,4') == {0, 2, 4}
    assert parsear(' 1 - 3 ') == {1, 2, 3}
    assert parsear('0-99') == set(range(0, 7)), 'recorta a días válidos'


def test_dias_de_refresco_invalidos_caen_al_default():
    parsear = app_module._parsear_dias_refresco
    default = frozenset(range(0, 6))
    assert parsear(None) == default
    assert parsear('') == default
    assert parsear('lunes') == default
    assert parsear('5-1') == default, 'rango invertido no vacía la semana'
    assert parsear('9') == default, 'solo días fuera de rango no vacía la semana'
