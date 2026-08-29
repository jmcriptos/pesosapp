"""El radar de clientes: ritmo propio, agrupación y contrato de la pantalla.

Spec: docs/superpowers/specs/2026-08-29-radar-clientes-design.md
"""
import os
from datetime import date, datetime, timedelta, timezone

import pytest

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


def test_el_ritmo_nunca_es_menor_a_un_dia():
    ritmo, _ = _ritmo_cliente(_fechas(0, 1, 2, 3))
    assert ritmo >= 1
