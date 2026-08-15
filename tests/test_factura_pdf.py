"""Tests del renderizador de facturas PDF.

Los fixtures son objetos Invoice de QuickBooks con datos reales de facturas
emitidas el 2026-08-12 y 2026-08-14.
"""
import json
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / 'fixtures' / 'facturas'


def cargar(nombre):
    return json.loads((FIXTURES / f'{nombre}.json').read_text())


def test_extrae_cabecera_y_cliente():
    from utils.factura_pdf import extraer_datos_factura

    datos = extraer_datos_factura(cargar('xcg_con_ob'))

    assert datos['numero'] == '5811'
    assert datos['cliente'] == 'Esperamos Supermarket'
    assert datos['crib'] == '104123456'
    assert datos['moneda'] == 'XCG'
    assert datos['terminos'] == 'Net 7'


def test_extrae_pesos_por_caja_de_la_descripcion():
    from utils.factura_pdf import extraer_datos_factura

    datos = extraer_datos_factura(cargar('xcg_sin_ob'))
    linea = datos['lineas'][0]

    assert linea['producto'] == 'Smoked Turkey Breast'
    assert linea['pesos'] == ['13.50', '12.05']
    assert linea['qty'] == 25.55
    assert linea['rate'] == 34


def test_ignora_lineas_que_no_son_de_producto():
    """QBO mete líneas SubTotalLineDetail que no deben aparecer en la tabla."""
    from utils.factura_pdf import extraer_datos_factura

    datos = extraer_datos_factura(cargar('xcg_con_ob'))

    assert len(datos['lineas']) == 2


def test_detecta_usd():
    from utils.factura_pdf import extraer_datos_factura

    datos = extraer_datos_factura(cargar('usd'))

    assert datos['moneda'] == 'USD'
    assert datos['moneda_label'] == 'USD - US Dollar'


def test_ob_cero_cuando_no_hay_impuesto():
    from utils.factura_pdf import extraer_datos_factura

    datos = extraer_datos_factura(cargar('xcg_sin_ob'))

    assert datos['ob'] == 0
    assert datos['ob_pct'] == 0
    assert datos['total'] == 1600.71


def test_tolera_factura_sin_direccion():
    from utils.factura_pdf import extraer_datos_factura

    datos = extraer_datos_factura({'Invoice': {'Id': '1', 'DocNumber': '9999'}})

    assert datos['numero'] == '9999'
    assert datos['direccion'] == []
    assert datos['crib'] == ''
    assert datos['lineas'] == []
