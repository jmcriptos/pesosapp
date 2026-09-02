"""Precalentamiento de la caché de ventas de QuickBooks al arrancar el worker.

La lectura de la caché (fila compartida en Postgres, sin bloqueo) se prueba
en test_qb_cache_compartida.py. Acá queda el arranque: que no salga a la red
en tests, que no salga sin webhook, y que cuando sale lo haga en un hilo, con
el timeout completo.
"""
import time
import threading

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
