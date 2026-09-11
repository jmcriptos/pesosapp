# tests/test_qbo_factura.py
"""Traductor payload → Invoice (utils/qbo_factura.py).

Los tres fixtures `body_*.json` son la salida real del nodo de código de
n8n para facturas de producción (2026-09-09/11). El traductor tiene que
producir exactamente eso, más el `CustomerMemo` que agregaba el nodo HTTP y
el `PrivateNote` nuevo.
"""
import json
from datetime import date
from pathlib import Path

import pytest

from utils.qbo_factura import (
    construir_invoice, detectar_clase, codigo_impuesto_del_payload,
    QBO_CUSTOMER_MEMO, TAX_RATE_REF,
)

FIXTURES = Path(__file__).parent / 'fixtures' / 'qbo'
COCIDOS = '600000000005541105'
ATUN = '600000000005391641'
MANTOVA = '529395'


def _fixture(nombre):
    with open(FIXTURES / nombre, encoding='utf-8') as f:
        return json.load(f)[0]


def _linea(qbo_id, nombre, qty, precio, tax, clase=None):
    linea = {
        'product_qbo_id': qbo_id, 'descripcion': nombre, 'product_name': nombre,
        'qty': qty, 'unit_price': precio,
        'amount': round(qty * precio, 2), 'tax_rate': tax,
    }
    if clase:
        linea['class_ref'] = clase
    return linea


def _payload(customer, moneda, tipo_cambio, lineas, order_id=1305):
    return {
        'order_id': order_id,
        'order_date': '2026-09-11T14:02:43',
        'customer_qbo_id': customer,
        'currency': moneda,
        'currency_qbo': 'USD' if moneda == 'USD' else 'ANG',
        'currency_display': ('USD - US Dollar' if moneda == 'USD'
                             else 'XCG - Caribbean Guilder'),
        'exchange_rate': tipo_cambio,
        'notes': None,
        'lines': lineas,
        'total': round(sum(l['amount'] for l in lineas), 2),
    }


def _esperado(nombre, doc_number, order_id):
    esperado = _fixture(nombre)
    esperado['DocNumber'] = doc_number
    esperado['CustomerMemo'] = {'value': QBO_CUSTOMER_MEMO}
    esperado['PrivateNote'] = f'PesosApp pedido {order_id}'
    # El nodo desplegado manda TaxRateRef 25 siempre (ver comentario de la
    # 5867). El body de la 5869 es de una versión anterior que mandaba 19.
    esperado['TxnTaxDetail']['TaxLine'][0]['TaxLineDetail']['TaxRateRef'] = {
        'value': TAX_RATE_REF}
    return esperado


def _pesables(qbo_id, nombre, pesos, precio, tax, clase):
    return [_linea(qbo_id, nombre, p, precio, tax, clase) for p in pesos]


# ── los tres bodies reales ────────────────────────────────────────────────

def test_factura_5879_xcg_pesables_codigo_14():
    lineas = (
        _pesables('1365', 'Cooked Chicken Ham', [23.15, 23.40], 13.2, 14, COCIDOS)
        + _pesables('1370', 'Cooked Shoulder', [23.30, 23.20, 23.35, 23.45, 23.45], 14.25, 14, COCIDOS)
        + _pesables('1354', 'Ham di Pasku di Turkey', [12.20], 19.98, 14, COCIDOS)
        + _pesables('1351', 'Porchop Huma Ku Wesu',
                    [10.40, 13.20, 12.50, 14.60, 12.40, 14.90, 14.25, 13.45, 15.10, 15.30,
                     13.80, 12.50, 14.50, 12.45, 13.45, 13.90, 13.20, 17.00, 13.15, 12.60],
                    14, 14, COCIDOS)
        + _pesables('1366', 'Smoked Chicken Ham', [18.85], 14.3, 14, COCIDOS)
        + _pesables('1352', 'Smoked Turkey Ham', [19.50], 18.65, 14, COCIDOS)
    )
    payload = _payload('1497', 'XCG', 1.0, lineas, order_id=1340)
    body = construir_invoice(payload, '5879', date(2026, 9, 11))
    assert body == _esperado('body_5879_xcg_pesables.json', '5879', 1340)


def test_factura_5878_xcg_cajas_codigo_10_con_6_por_ciento():
    lineas = [
        _linea('1297', 'Atun en Agua 160g', 3, 131.08, 10, ATUN),
        _linea('1402', 'Avocado Oil Botella 250ml', 5, 56.6, 10, MANTOVA),
        _linea('1404', 'Avocado Oil Botella 1Lt', 3, 170, 10, MANTOVA),
        _linea('1403', 'Avocado Oil Botella 500ml', 5, 94.75, 10, MANTOVA),
        _linea('1398', 'EV Olive Oil Botella 1Lt', 2, 276.68, 10, MANTOVA),
        _linea('1395', 'EV Olive Oil Botella 250ml', 3, 70.65, 10, MANTOVA),
        _linea('1305', 'Atun en Oliva 3x80g', 3, 80.56, 10, ATUN),
    ]
    payload = _payload('1497', 'XCG', 1.0, lineas, order_id=1339)
    body = construir_invoice(payload, '5878', date(2026, 9, 11))
    esperado = _esperado('body_5878_xcg_cajas.json', '5878', 1339)
    assert body == esperado
    assert body['TxnTaxDetail']['TotalTax'] == 160.02
    assert body['TxnTaxDetail']['TaxLine'][0]['TaxLineDetail']['NetAmountTaxable'] == 2666.98


def test_factura_5869_usd_exportacion_codigo_13():
    lineas = _pesables('1351', 'Porchop Huma Ku Wesu',
                       [19.95, 18.60, 19.95, 18.20, 19.70], 8, 13, COCIDOS)
    payload = _payload('1737', 'USD', 1.78, lineas, order_id=1333)
    body = construir_invoice(payload, '5869', date(2026, 9, 9))
    assert body == _esperado('body_5869_usd_export.json', '5869', 1333)
    assert body['CurrencyRef'] == {'value': 'USD'}
    assert body['ExchangeRate'] == 1.78
    assert body['CustomField'][3]['StringValue'] == '2'


# ── casos medidos en producción ───────────────────────────────────────────

def test_medio_centavo_redondea_hacia_arriba_como_qbo():
    """Pedido 1334 (2026-09-08): 128,350 × 14,50 = 1.861,075 exactos. En
    float da 1.861,0749… y salía 1.861,07 → error 6070 de QBO."""
    pesos = [16.05, 16.05, 16.05, 16.05, 16.05, 16.05, 16.05, 16.00]
    assert round(sum(pesos), 3) == 128.35
    payload = _payload('1', 'XCG', 1.0, _pesables('1351', 'Porchop', pesos, 14.50, 14, COCIDOS))
    linea = construir_invoice(payload, '1', date(2026, 9, 8))['Line'][0]
    assert linea['Amount'] == 1861.08
    assert linea['SalesItemLineDetail']['Qty'] == 128.35


def test_tres_cajas_de_cien_gramos_suman_trescientos():
    """0.1 × 3 daba 0.30000000000000004 en coma flotante."""
    payload = _payload('1', 'XCG', 1.0, _pesables('9', 'Bacon', [0.1, 0.1, 0.1], 10, 14, COCIDOS))
    linea = construir_invoice(payload, '1', date(2026, 9, 8))['Line'][0]
    assert linea['SalesItemLineDetail']['Qty'] == 0.3
    assert linea['Amount'] == 3
    assert linea['Description'] == '0.10\t0.10\t0.10'


def test_tax_code_de_linea_siempre_TAX_y_bloque_de_impuesto_al_cero():
    """Modo US: la línea solo acepta TAX/NON (6100). Con NON la venta se caía
    del reporte (5864). Y sin TxnTaxDetail la factura queda sin código (5865)."""
    payload = _payload('1', 'XCG', 1.0, [_linea('9', 'Jamón', 2, 10, 14, COCIDOS)])
    body = construir_invoice(payload, '1', date(2026, 9, 8))
    assert body['Line'][0]['SalesItemLineDetail']['TaxCodeRef'] == {'value': 'TAX'}
    assert body['TxnTaxDetail'] == {
        'TotalTax': 0,
        'TxnTaxCodeRef': {'value': '14'},
        'TaxLine': [{
            'Amount': 0, 'DetailType': 'TaxLineDetail',
            'TaxLineDetail': {'TaxPercent': 0, 'NetAmountTaxable': 20,
                              'PercentBased': True, 'TaxRateRef': {'value': '25'}},
        }],
    }


def test_tax_rate_ref_es_25_tambien_al_6_por_ciento():
    """5867: mandar la tasa «correcta» 17 hace que QBO facture al 0 %."""
    payload = _payload('1', 'XCG', 1.0, [_linea('9', 'Atún', 1, 100, 10, ATUN)])
    body = construir_invoice(payload, '1', date(2026, 9, 8))
    assert body['TxnTaxDetail']['TaxLine'][0]['TaxLineDetail']['TaxRateRef'] == {'value': '25'}
    assert body['TxnTaxDetail']['TotalTax'] == 6


def test_nueve_por_ciento_sale_de_la_tabla_sin_codigo_nuevo():
    payload = _payload('1', 'XCG', 1.0, [_linea('9', 'X', 1, 100, 11, MANTOVA)])
    body = construir_invoice(payload, '1', date(2026, 9, 8))
    assert body['TxnTaxDetail']['TxnTaxCodeRef'] == {'value': '11'}
    assert body['TxnTaxDetail']['TotalTax'] == 9


# ── agrupado y descripciones ──────────────────────────────────────────────

def test_agrupa_por_producto_y_precio_conservando_el_orden():
    lineas = [
        _linea('A', 'Jamón', 1.5, 10, 14, COCIDOS),
        _linea('B', 'Bacon', 2, 20, 14, COCIDOS),
        _linea('A', 'Jamón', 2.5, 10, 14, COCIDOS),
        _linea('A', 'Jamón', 1, 12, 14, COCIDOS),   # otro precio: otra línea
    ]
    body = construir_invoice(_payload('1', 'XCG', 1.0, lineas), '1', date(2026, 9, 8))
    assert [(l['SalesItemLineDetail']['ItemRef']['value'], l['SalesItemLineDetail']['UnitPrice'])
            for l in body['Line']] == [('A', 10), ('B', 20), ('A', 12)]
    assert body['Line'][0]['SalesItemLineDetail']['Qty'] == 4
    assert body['Line'][0]['Description'] == '1.50\t2.50'
    assert body['Line'][0]['Amount'] == 40


def test_descripcion_usa_el_nombre_de_la_app_con_lote_incluido():
    """n8n usa `descripcion` como ItemRef.name; QBO lo reescribe por el id."""
    linea = _linea('A', 'Atun en Agua 160g (Lote L23)', 3, 10, 10, ATUN)
    body = construir_invoice(_payload('1', 'XCG', 1.0, [linea]), '1', date(2026, 9, 8))
    assert body['Line'][0]['SalesItemLineDetail']['ItemRef']['name'] == 'Atun en Agua 160g (Lote L23)'
    assert body['Line'][0]['Description'] == '3.00'


# ── clases ────────────────────────────────────────────────────────────────

def test_class_ref_de_la_app_manda_sobre_las_palabras_clave():
    linea = _linea('A', 'Smoked Pork Chop', 1, 10, 14, MANTOVA)
    body = construir_invoice(_payload('1', 'XCG', 1.0, [linea]), '1', date(2026, 9, 8))
    assert body['Line'][0]['SalesItemLineDetail']['ClassRef'] == {'value': MANTOVA}


def test_sin_class_ref_detecta_por_palabra_clave():
    lineas = [
        _linea('A', 'Smoked Pork Chop', 1, 10, 14),
        _linea('B', 'VCamps Atun en Oliva 32x3x80g', 1, 10, 14),   # atún antes que oliva
        _linea('C', 'Galletas de agua', 1, 10, 14),
    ]
    body = construir_invoice(_payload('1', 'XCG', 1.0, lineas), '1', date(2026, 9, 8))
    detalles = [l['SalesItemLineDetail'] for l in body['Line']]
    assert detalles[0]['ClassRef'] == {'value': COCIDOS}
    assert detalles[1]['ClassRef'] == {'value': ATUN}
    assert 'ClassRef' not in detalles[2]


@pytest.mark.parametrize('nombre, clase', [
    ('Ham di Pasku di Turkey', COCIDOS),
    ('EV Olive Oil Botella 1Lt', MANTOVA),
    ('Tomate Triturado', '600000000005012031'),
    ('Underwood Deviled Ham', COCIDOS),   # 'ham' gana: cocidos va primero
    ('', None), (None, None), ('Servilletas', None),
])
def test_detectar_clase(nombre, clase):
    assert detectar_clase(nombre) == clase


# ── cabecera y moneda ─────────────────────────────────────────────────────

def test_cabecera_fechas_termino_y_memo():
    body = construir_invoice(
        _payload('77', 'XCG', 1.0, [_linea('A', 'X', 1, 1, 14)], order_id=1400),
        '6001', date(2026, 12, 30))
    assert body['CustomerRef'] == {'value': '77'}
    assert body['DocNumber'] == '6001'
    assert body['TxnDate'] == '2026-12-30'
    assert body['DueDate'] == '2027-01-06'
    assert body['SalesTermRef'] == {'value': '46'}
    assert body['GlobalTaxCalculation'] == 'TaxExcluded'
    assert body['CustomerMemo'] == {'value': QBO_CUSTOMER_MEMO}
    assert body['PrivateNote'] == 'PesosApp pedido 1400'
    assert 'notes' not in json.dumps(body)


def test_ang_manda_currency_ref_y_tipo_de_cambio_1():
    body = construir_invoice(_payload('1', 'XCG', 1.0, [_linea('A', 'X', 1, 1, 14)]),
                             '1', date(2026, 9, 8))
    assert body['CurrencyRef'] == {'value': 'ANG'}
    assert body['ExchangeRate'] == 1
    assert body['CustomField'][0]['StringValue'] == 'XCG - Caribbean Guilder'
    assert body['CustomField'][3]['StringValue'] == '1'


def test_custom_fields_en_orden_con_sales_rep_y_tax_id_por_defecto():
    body = construir_invoice(_payload('1', 'XCG', 1.0, [_linea('A', 'X', 1, 1, 14)]),
                             '1', date(2026, 9, 8))
    assert [(c['DefinitionId'], c['Name'], c['StringValue']) for c in body['CustomField']] == [
        ('1', 'Currency', 'XCG - Caribbean Guilder'),
        ('2', 'Sales Rep', 'OF'),
        ('3', 'Tax ID No.', ''),
        ('1000000003', 'Currency2', '1'),
    ]
    assert all(c['Type'] == 'StringType' for c in body['CustomField'])


def test_payload_sin_moneda_qbo_no_manda_currency_ref():
    payload = _payload('1', 'XCG', 1.0, [_linea('A', 'X', 1, 1, 14)])
    del payload['currency_qbo']
    body = construir_invoice(payload, '1', date(2026, 9, 8))
    assert 'CurrencyRef' not in body and 'ExchangeRate' not in body


# ── validaciones ──────────────────────────────────────────────────────────

def test_mezcla_de_impuestos_es_error():
    lineas = [_linea('A', 'X', 1, 1, 10), _linea('B', 'Y', 1, 1, 14)]
    with pytest.raises(ValueError, match='mezcla'):
        construir_invoice(_payload('1', 'XCG', 1.0, lineas), '1', date(2026, 9, 8))


def test_codigo_desconocido_es_error():
    with pytest.raises(ValueError, match='desconocido'):
        construir_invoice(_payload('1', 'XCG', 1.0, [_linea('A', 'X', 1, 1, 99)]),
                          '1', date(2026, 9, 8))


def test_sin_codigo_es_error():
    with pytest.raises(ValueError, match='no traen código'):
        construir_invoice(_payload('1', 'XCG', 1.0, [_linea('A', 'X', 1, 1, None)]),
                          '1', date(2026, 9, 8))


def test_sin_lineas_es_error():
    with pytest.raises(ValueError, match='no tiene líneas'):
        codigo_impuesto_del_payload({'lines': []})


def test_codigo_como_string_o_float_se_normaliza():
    assert codigo_impuesto_del_payload({'lines': [{'tax_rate': '10'}, {'tax_rate': 10.0}]}) == '10'


# ── número de factura ─────────────────────────────────────────────────────

from unittest.mock import MagicMock
from utils.qbo_factura import siguiente_doc_number, QUERY_DOCNUMBER
from utils.qbo_client import QboError


def _cliente_docnumber(facturas, notas):
    cliente = MagicMock()

    def query(sql):
        if 'FROM Invoice' in sql:
            return {'Invoice': [{'DocNumber': n} for n in facturas]} if facturas else {}
        if 'FROM CreditMemo' in sql:
            return {'CreditMemo': [{'DocNumber': n} for n in notas]} if notas else {}
        raise AssertionError(sql)

    cliente.query.side_effect = query
    return cliente


def test_siguiente_es_el_mayor_entre_facturas_y_notas_mas_uno():
    cliente = _cliente_docnumber(['5879', '5878', '5877'], ['5880', '5850'])
    assert siguiente_doc_number(cliente) == '5881'


def test_consulta_las_dos_entidades_con_la_query_de_n8n():
    cliente = _cliente_docnumber(['5879'], [])
    siguiente_doc_number(cliente)
    consultas = [c.args[0] for c in cliente.query.call_args_list]
    assert consultas == [
        'SELECT DocNumber FROM Invoice ORDER BY MetaData.CreateTime DESC MAXRESULTS 50',
        'SELECT DocNumber FROM CreditMemo ORDER BY MetaData.CreateTime DESC MAXRESULTS 50',
    ]


def test_ultimo_local_gana_si_qbo_todavia_no_indexo_la_anterior():
    """La app acaba de emitir la 5880 pero QBO aún devuelve 5879 como máxima."""
    cliente = _cliente_docnumber(['5879'], ['5850'])
    assert siguiente_doc_number(cliente, ultimo_local=5880) == '5881'


def test_ultimo_local_menor_no_retrocede():
    cliente = _cliente_docnumber(['5879'], [])
    assert siguiente_doc_number(cliente, ultimo_local=5000) == '5880'


def test_ignora_docnumbers_no_numericos():
    cliente = _cliente_docnumber(['5879', 'NC-12', '', None, ' 5900 '], ['abc'])
    assert siguiente_doc_number(cliente) == '5901'


def test_sin_numeros_en_qbo_es_error_no_un_arranque_inventado():
    cliente = _cliente_docnumber([], [])
    with pytest.raises(QboError, match='no devolvió ningún número'):
        siguiente_doc_number(cliente, ultimo_local=5880)
