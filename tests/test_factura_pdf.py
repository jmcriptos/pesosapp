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


def _streams_descomprimidos(pdf):
    """Los content streams de reportlab vienen con ASCII85Decode +
    FlateDecode. Los devuelve descomprimidos y en orden, uno por stream,
    para poder leer el texto realmente dibujado en vez de confiar en cómo
    un rasterizador externo (con su propia sustitución de fuentes) decide
    pintarlo."""
    out = []
    for m in re.finditer(rb'stream\r?\n(.*?)endstream', pdf, re.S):
        raw = m.group(1).strip(b'\r\n')
        try:
            out.append(zlib.decompress(base64.a85decode(raw.split(b'~>')[0], adobe=False)))
        except Exception:
            try:
                out.append(zlib.decompress(raw))
            except Exception:
                out.append(raw)
    return out


def _texto_visible(pdf):
    return b''.join(_streams_descomprimidos(pdf))


def _mapa_fuentes(pdf):
    """Nombre de recurso (/F1, /F2...) -> BaseFont (Helvetica,
    Helvetica-Bold...), leído de los objetos /Type /Font del PDF (son
    objetos planos, no vienen comprimidos)."""
    fuentes = {}
    for m in re.finditer(rb'<<([^<>]*?/Type\s*/Font[^<>]*?)>>', pdf, re.S):
        bloque = m.group(1)
        base = re.search(rb'/BaseFont\s*/(\S+)', bloque)
        nombre = re.search(rb'/Name\s*/(\S+)', bloque)
        if base and nombre:
            fuentes[nombre.group(1)] = base.group(1).decode('latin1')
    return fuentes


_TOKEN_RE = re.compile(
    rb'/(F\d+)\s+([\d.]+)\s+Tf'          # cambio de fuente/tamaño
    rb'|\(((?:[^()\\]|\\.)*)\)\s*Tj'      # texto simple
    rb'|\[((?:[^\[\]])*)\]\s*TJ'          # texto con kerning
)
_PAREN_RE = re.compile(rb'\(((?:[^()\\]|\\.)*)\)')


def _unescape(s):
    return s.replace(rb'\(', b'(').replace(rb'\)', b')')


def _runs_de_texto(pdf):
    """Cada fragmento de texto realmente dibujado en el PDF, con la fuente
    (BaseFont) y el tamaño con los que reportlab lo escribió -- construido
    siguiendo los operadores Tf/Tj/TJ del content stream, no adivinado
    desde un screenshot. Devuelve una lista de (fuente, tamaño, texto)."""
    fuentes = _mapa_fuentes(pdf)
    runs = []
    for stream in _streams_descomprimidos(pdf):
        fuente = tamano = None
        for m in _TOKEN_RE.finditer(stream):
            if m.group(1):
                fuente = fuentes.get(m.group(1), m.group(1).decode('latin1'))
                tamano = float(m.group(2))
            elif m.group(3) is not None:
                texto = _unescape(m.group(3)).decode('latin1')
                if texto.strip():
                    runs.append((fuente, tamano, texto))
            elif m.group(4) is not None:
                texto = b''.join(_unescape(p) for p in _PAREN_RE.findall(m.group(4))).decode('latin1')
                if texto.strip():
                    runs.append((fuente, tamano, texto))
    return runs


def _fuente_de(runs, texto_esperado):
    """(fuente, tamaño) del primer run cuyo texto contiene `texto_esperado`."""
    for fuente, tamano, texto in runs:
        if texto_esperado in texto:
            return fuente, tamano
    raise AssertionError(f'no se encontró ningún texto que contenga {texto_esperado!r}')


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


def test_render_negrita_por_elemento():
    """No alcanza con que /BaseFont /Helvetica-Bold aparezca en algún lado
    del PDF (el header de la tabla solo ya lo garantiza) -- hay que probar,
    elemento por elemento, que el texto que la referencia muestra en
    negrita realmente se dibujó con esa fuente. Sigue los operadores
    Tf/Tj/TJ del content stream (vía `_runs_de_texto`), no un screenshot."""
    from utils.factura_pdf import render_factura_pdf

    pdf = render_factura_pdf(cargar('xcg_con_ob'))
    runs = _runs_de_texto(pdf)

    # Nombre del cliente bajo BILL TO, negrita contra las líneas de
    # dirección en peso normal.
    assert _fuente_de(runs, 'Esperamos Supermarket')[0] == 'Helvetica-Bold'
    # Valor del bloque de detalles (el label 'Invoice #:' de al lado es gris
    # y en peso normal).
    assert _fuente_de(runs, '5811')[0] == 'Helvetica-Bold'
    # Una cifra de la columna AMOUNT.
    assert _fuente_de(runs, '293.34')[0] == 'Helvetica-Bold'
    # BALANCE DUE y su importe.
    assert _fuente_de(runs, 'BALANCE DUE')[0] == 'Helvetica-Bold'
    assert _fuente_de(runs, '727.77')[0] == 'Helvetica-Bold'
    # Título del bloque bancario.
    assert _fuente_de(runs, 'Jomar Foods, BV')[0] == 'Helvetica-Bold'
    # Header de la tabla de líneas.
    assert _fuente_de(runs, 'AMOUNT')[0] == 'Helvetica-Bold'
    # Control: una línea que NO debe estar en negrita.
    assert _fuente_de(runs, 'Willemstad')[0] == 'Helvetica'


def test_render_tamanos_de_fuente():
    """El spec de la factura es, ante todo, una lista de tamaños. Un cambio
    que reduzca BALANCE DUE a 10pt o infle PRODUCT a 12pt debe romper la
    suite."""
    from utils.factura_pdf import render_factura_pdf

    pdf = render_factura_pdf(cargar('xcg_con_ob'))
    runs = _runs_de_texto(pdf)

    assert _fuente_de(runs, 'INVOICE')[1] == 26
    assert _fuente_de(runs, 'BALANCE DUE')[1] == 13
    assert _fuente_de(runs, 'Deviled Ham 32/120 gr')[1] == 8.5


def test_render_usd_muestra_la_moneda():
    from utils.factura_pdf import render_factura_pdf

    pdf = render_factura_pdf(cargar('usd'))

    assert b'USD - US Dollar' in _texto_visible(pdf)
