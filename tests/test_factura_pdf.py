"""Tests del renderizador de facturas PDF.

Los fixtures son objetos Invoice de QuickBooks con datos reales de facturas
emitidas el 2026-08-12 y 2026-08-14.
"""
import base64
import json
import re
import zlib
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / 'fixtures' / 'facturas'


def cargar(nombre):
    return json.loads((FIXTURES / f'{nombre}.json').read_text())


def _texto_visible(pdf):
    """Descomprime los content streams del PDF (reportlab los guarda con
    ASCII85Decode + FlateDecode) para poder buscar texto literal dentro de
    los operadores Tj, en vez de confiar en cómo un rasterizador externo
    (con su propia sustitución de fuentes) decide dibujarlos."""
    out = b''
    for m in re.finditer(rb'stream\r?\n(.*?)endstream', pdf, re.S):
        raw = m.group(1).strip(b'\r\n')
        try:
            out += zlib.decompress(base64.a85decode(raw.split(b'~>')[0], adobe=False))
        except Exception:
            try:
                out += zlib.decompress(raw)
            except Exception:
                out += raw
    return out


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


def test_extrae_impuesto_y_totales_con_ob():
    """Verifica que el porcentaje de impuesto (OB) se extrae correctamente de TaxLineDetail."""
    from utils.factura_pdf import extraer_datos_factura

    datos = extraer_datos_factura(cargar('xcg_con_ob'))

    assert datos['subtotal'] == 686.58
    assert datos['ob_pct'] == 6
    assert datos['ob'] == 41.19
    assert datos['total'] == 727.77


def test_subtotal_fallback_sin_subtotal_en_invoice():
    """Cuando SubTotal no está presente, calcula el subtotal sumando los montos de las líneas."""
    from utils.factura_pdf import extraer_datos_factura

    invoice = {
        'Invoice': {
            'DocNumber': '9999',
            'Line': [
                {
                    'Amount': 100.00,
                    'DetailType': 'SalesItemLineDetail',
                    'SalesItemLineDetail': {
                        'ItemRef': {'name': 'Category:Product A'},
                        'Qty': 10,
                        'UnitPrice': 10,
                    }
                },
                {
                    'Amount': 250.50,
                    'DetailType': 'SalesItemLineDetail',
                    'SalesItemLineDetail': {
                        'ItemRef': {'name': 'Category:Product B'},
                        'Qty': 5,
                        'UnitPrice': 50.1,
                    }
                }
            ],
            'TxnTaxDetail': {'TotalTax': 0}
        }
    }

    datos = extraer_datos_factura(invoice)

    assert datos['subtotal'] == 350.50
    assert datos['total'] == 350.50
    assert len(datos['lineas']) == 2


@pytest.mark.parametrize('fixture', ['xcg_con_ob', 'xcg_sin_ob', 'usd'])
def test_render_produce_pdf_valido(fixture):
    from utils.factura_pdf import render_factura_pdf

    pdf = render_factura_pdf(cargar(fixture))

    assert pdf[:5] == b'%PDF-'
    assert pdf.rstrip()[-5:] == b'%%EOF'
    assert len(pdf) > 2000


def test_render_tolera_factura_minima():
    """Una factura sin líneas ni dirección no debe reventar el render."""
    from utils.factura_pdf import render_factura_pdf

    pdf = render_factura_pdf({'Invoice': {'Id': '1', 'DocNumber': '9999'}})

    assert pdf[:5] == b'%PDF-'


def test_render_con_muchas_cajas_no_revienta_y_crece():
    """Caso real de la factura 5806: 6 productos de 20 cajas cada uno. El grid
    de pesos tiene que fluir sin romper el render, y el PDF resultante pesa
    claramente más que uno de dos líneas."""
    from utils.factura_pdf import render_factura_pdf

    pesos = '\t'.join(f'{12 + i * 0.15:.2f}' for i in range(20))
    linea = {
        'DetailType': 'SalesItemLineDetail',
        'Description': pesos,
        'Amount': 3339.70,
        'SalesItemLineDetail': {
            'ItemRef': {'name': 'Smoked and Cooked:Smoked Pork Chop'},
            'Qty': 256.9, 'UnitPrice': 13,
        },
    }
    factura = {'Invoice': {
        'Id': '47339', 'DocNumber': '5806', 'TxnDate': '2026-08-11',
        'CustomerRef': {'name': 'Mangusa Supermarket na Rio Canario, BV'},
        'Line': [dict(linea) for _ in range(6)],
        'SubTotal': 20038.2, 'TotalAmt': 20038.2,
    }}

    grande = render_factura_pdf(factura)
    chico = render_factura_pdf(cargar('xcg_sin_ob'))

    assert grande[:5] == b'%PDF-'
    assert len(grande) > len(chico)


def test_render_incrusta_la_fuente_bold():
    """Verificación real de negrita, no visual: reportlab declara la fuente
    en los recursos del PDF como /BaseFont /Helvetica-Bold cuando algún
    ParagraphStyle la usa. Buscar el string en los bytes crudos alcanza
    porque esa declaración vive en el diccionario de recursos (un objeto
    plano), no dentro de un content stream comprimido.

    (Un rasterizador externo puede sustituir Helvetica-Bold por la misma
    cara que Helvetica si el sistema no tiene una fuente bold real mapeada
    -verificado en este entorno con `fc-match Helvetica-Bold` -> Regular-,
    así que un screenshot con esa herramienta no es evidencia confiable de
    si el PDF pide negrita o no; esto sí lo es.)"""
    from utils.factura_pdf import render_factura_pdf

    pdf = render_factura_pdf(cargar('xcg_con_ob'))

    assert b'/BaseFont /Helvetica-Bold' in pdf


def test_render_usd_muestra_la_moneda():
    from utils.factura_pdf import render_factura_pdf

    pdf = render_factura_pdf(cargar('usd'))

    assert b'USD - US Dollar' in _texto_visible(pdf)
