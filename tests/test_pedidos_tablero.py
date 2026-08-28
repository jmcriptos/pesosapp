# tests/test_pedidos_tablero.py
"""El tablero de entregas: reparto en grupos y contrato de modos.

Spec: docs/superpowers/specs/2026-08-28-pedidos-tablero-design.md
"""
import os
from datetime import date, timedelta

import pytest

os.environ.setdefault('SECRET_KEY', 'test-secret')
os.environ.setdefault('FLASK_ENV', 'testing')
os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')

from app import _agrupar_tablero, Pedido


HOY = date(2026, 8, 28)


def _p(estado, dias=None, id=1):
    """Pedido suelto, sin sesión: `_agrupar_tablero` es pura."""
    return Pedido(
        id=id,
        estado=estado,
        fecha_entrega=None if dias is None else HOY + timedelta(days=dias),
    )


def _claves(grupos):
    return [clave for clave, _etiqueta, _pedidos in grupos]


def _pedidos_de(grupos, clave):
    for c, _etiqueta, pedidos in grupos:
        if c == clave:
            return pedidos
    return []


def test_atrasado_sin_facturar_va_a_atrasados():
    grupos = _agrupar_tablero([_p('pendiente', dias=-3)], HOY)
    assert _claves(grupos) == ['atrasados']


def test_entrega_hoy_va_a_hoy_en_cualquier_estado():
    grupos = _agrupar_tablero(
        [_p('pendiente', dias=0, id=1),
         _p('preparado', dias=0, id=2),
         _p('facturado', dias=0, id=3)],
        HOY,
    )
    assert _claves(grupos) == ['hoy']
    assert len(_pedidos_de(grupos, 'hoy')) == 3


def test_el_facturado_de_hoy_no_se_cuela_en_otro_grupo():
    """Decisión del spec: se queda en «Hoy», marcado hecho. En ningún otro."""
    grupos = _agrupar_tablero([_p('facturado', dias=0)], HOY)
    assert _claves(grupos) == ['hoy']


def test_entrega_futura_sin_facturar_va_a_proximos():
    grupos = _agrupar_tablero([_p('preparado', dias=5)], HOY)
    assert _claves(grupos) == ['proximos']


def test_sin_facturar_y_sin_fecha_nunca_es_invisible():
    """El test que más importa: si falla, la pantalla esconde trabajo."""
    grupos = _agrupar_tablero([_p('pendiente', dias=None)], HOY)
    assert _claves(grupos) == ['sin_fecha']
    assert len(_pedidos_de(grupos, 'sin_fecha')) == 1


def test_el_archivo_no_entra_al_tablero():
    """Facturado que no se entrega hoy: ni atrasados, ni próximos, ni sin fecha."""
    grupos = _agrupar_tablero(
        [_p('facturado', dias=-30, id=1),
         _p('facturado', dias=None, id=2),
         _p('facturado', dias=9, id=3)],
        HOY,
    )
    assert grupos == []


def test_los_grupos_vacios_no_se_dibujan():
    grupos = _agrupar_tablero([_p('pendiente', dias=0)], HOY)
    assert _claves(grupos) == ['hoy'], 'no debe aparecer ningún grupo vacío'


def test_los_grupos_van_en_orden_de_urgencia():
    grupos = _agrupar_tablero(
        [_p('pendiente', dias=4, id=1),
         _p('pendiente', dias=None, id=2),
         _p('pendiente', dias=0, id=3),
         _p('pendiente', dias=-2, id=4)],
        HOY,
    )
    assert _claves(grupos) == ['atrasados', 'hoy', 'proximos', 'sin_fecha']


def test_ningun_pedido_aparece_dos_veces():
    pedidos = [_p('pendiente', dias=-1, id=1), _p('facturado', dias=0, id=2),
               _p('preparado', dias=3, id=3), _p('pendiente', dias=None, id=4)]
    grupos = _agrupar_tablero(pedidos, HOY)
    vistos = [p.id for _c, _e, ps in grupos for p in ps]
    assert sorted(vistos) == [1, 2, 3, 4]
    assert len(vistos) == len(set(vistos)), 'un pedido cayó en dos grupos'
