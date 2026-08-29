"""El radar de clientes: ritmo propio, agrupación y contrato de la pantalla.

Spec: docs/superpowers/specs/2026-08-29-radar-clientes-design.md
"""
import os
from datetime import date, datetime, timedelta, timezone

os.environ.setdefault('SECRET_KEY', 'test-secret')
os.environ.setdefault('FLASK_ENV', 'testing')
os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')

from app import _ritmo_cliente, _RADAR_RITMO_NEGOCIO


HOY = date(2026, 8, 29)


def _fechas(*dias_atras):
    return [HOY - timedelta(days=d) for d in dias_atras]


def test_ritmo_propio_con_tres_fechas_o_mas():
    # Compra cada 7 días: 0, 7, 14, 21 atrás → intervalos [7,7,7]
    ritmo, propio = _ritmo_cliente(_fechas(0, 7, 14, 21))
    assert (ritmo, propio) == (7, True)


def test_ritmo_es_la_mediana_no_el_promedio():
    """Un intervalo raro no debe mover el ritmo: por eso mediana."""
    # intervalos [5, 5, 100] → mediana 5, promedio 36,7
    ritmo, propio = _ritmo_cliente(_fechas(0, 5, 10, 110))
    assert (ritmo, propio) == (5, True)


def test_con_menos_de_tres_fechas_usa_el_ritmo_del_negocio():
    for fechas in ([], _fechas(3), _fechas(3, 10)):
        ritmo, propio = _ritmo_cliente(fechas)
        assert ritmo == _RADAR_RITMO_NEGOCIO
        assert propio is False


def test_varios_pedidos_el_mismo_dia_no_dan_ritmo_cero():
    """LA regresión que motivó medir entre fechas y no entre pedidos.

    Best Buy carga varios pedidos la misma fecha. Midiendo entre PEDIDOS su
    mediana daba 0 días, lo que lo marcaba atrasado contra una división por
    cero y encima imprimía «ritmo 0d» en la fila. Midiendo entre fechas
    distintas, su ritmo es real.
    """
    fechas = _fechas(0, 0, 0, 14, 14, 28)     # tres fechas, no seis
    ritmo, propio = _ritmo_cliente(fechas)
    assert ritmo == 14
    assert propio is True
    assert ritmo > 0, 'un ritmo de 0 días divide por cero al calcular el atraso'


def test_datetimes_del_mismo_dia_cuentan_como_una_sola_fecha():
    """El contrato que impide que vuelva el bug de Best Buy.

    Si `_ritmo_cliente` no normaliza a día calendario, estos tres `datetime`
    del mismo día sobreviven como fechas distintas, los intervalos dan 0 y el
    ritmo sale 0 — que es división por cero al calcular el atraso.
    """
    base = datetime(2026, 8, 15, 9, 0)
    fechas = [
        base, base.replace(hour=11), base.replace(hour=16),   # un solo día
        datetime(2026, 8, 29, 10, 0),
        datetime(2026, 9, 12, 10, 0),
    ]
    ritmo, propio = _ritmo_cliente(fechas)
    assert ritmo == 14, 'los tres del 15/08 tienen que colapsar en una sola fecha'
    assert propio is True


from app import _agrupar_radar


def _fila(nombre, dias_desde_ultimo=None, ritmo=10, n_pedidos=5, propio=True):
    return {
        'id': abs(hash(nombre)) % 10000,
        'nombre': nombre,
        'ultimo': None if dias_desde_ultimo is None else HOY - timedelta(days=dias_desde_ultimo),
        'n_pedidos': n_pedidos,
        'ritmo': ritmo,
        'ritmo_propio': propio,
    }


def _grupo(grupos, clave):
    for c, _etiqueta, filas in grupos:
        if c == clave:
            return filas
    raise AssertionError(f'falta el grupo {clave}')


def test_las_cuatro_claves_siempre_estan_y_en_orden():
    grupos = _agrupar_radar([], HOY)
    assert [c for c, _e, _f in grupos] == ['atrasados', 'al_dia', 'dormidos', 'sin_pedidos']


def test_pasado_de_su_ritmo_va_a_atrasados():
    # ritmo 10, lleva 30 días → 3× su ritmo
    grupos = _agrupar_radar([_fila('Arco Iris', 30, ritmo=10)], HOY)
    assert [f['nombre'] for f in _grupo(grupos, 'atrasados')] == ['Arco Iris']
    assert _grupo(grupos, 'al_dia') == []


def test_dentro_de_su_ritmo_va_a_al_dia():
    grupos = _agrupar_radar([_fila('Mangusa', 6, ritmo=7)], HOY)
    assert [f['nombre'] for f in _grupo(grupos, 'al_dia')] == ['Mangusa']
    assert _grupo(grupos, 'atrasados') == []


def test_el_umbral_es_una_vez_y_media():
    """Justo en el límite NO está atrasado; apenas encima, sí."""
    assert _grupo(_agrupar_radar([_fila('Justo', 15, ritmo=10)], HOY), 'atrasados') == []
    assert len(_grupo(_agrupar_radar([_fila('Pasado', 16, ritmo=10)], HOY), 'atrasados')) == 1


def test_mas_de_noventa_dias_es_dormido_y_no_atrasado():
    """Disjuntos: un dormido está pasadísimo de su ritmo, pero va en un grupo solo."""
    grupos = _agrupar_radar([_fila('Everyday', 173, ritmo=10)], HOY)
    assert [f['nombre'] for f in _grupo(grupos, 'dormidos')] == ['Everyday']
    assert _grupo(grupos, 'atrasados') == []


def test_sin_ningun_pedido_va_a_su_propio_grupo():
    grupos = _agrupar_radar([_fila('Alta Nueva', None, n_pedidos=0)], HOY)
    assert [f['nombre'] for f in _grupo(grupos, 'sin_pedidos')] == ['Alta Nueva']
    assert _grupo(grupos, 'dormidos') == [], 'no compró nunca, no está dormido'


def test_atrasados_ordena_por_veces_su_ritmo():
    grupos = _agrupar_radar([
        _fila('poco', 20, ritmo=10),    # 2,0×
        _fila('mucho', 60, ritmo=10),   # 6,0×
        _fila('medio', 40, ritmo=10),   # 4,0×
    ], HOY)
    assert [f['nombre'] for f in _grupo(grupos, 'atrasados')] == ['mucho', 'medio', 'poco']


def test_dormidos_ordena_por_cantidad_de_pedidos():
    """En un dormido importa cuánto se perdió, no cuánto hace."""
    grupos = _agrupar_radar([
        _fila('chico', 120, n_pedidos=2),
        _fila('grande', 100, n_pedidos=40),
    ], HOY)
    assert [f['nombre'] for f in _grupo(grupos, 'dormidos')] == ['grande', 'chico']


def test_sin_pedidos_ordena_alfabetico():
    grupos = _agrupar_radar([
        _fila('Zeta', None, n_pedidos=0),
        _fila('alfa', None, n_pedidos=0),
    ], HOY)
    assert [f['nombre'] for f in _grupo(grupos, 'sin_pedidos')] == ['alfa', 'Zeta']


def test_cada_cliente_cae_en_un_solo_grupo():
    filas = [_fila('a', 30, ritmo=10), _fila('b', 5, ritmo=10),
             _fila('c', 200, ritmo=10), _fila('d', None, n_pedidos=0)]
    grupos = _agrupar_radar(filas, HOY)
    vistos = [f['nombre'] for _c, _e, fs in grupos for f in fs]
    assert sorted(vistos) == ['a', 'b', 'c', 'd']
    assert len(vistos) == len(set(vistos))
