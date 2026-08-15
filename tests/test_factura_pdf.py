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


_TOKEN_RE_POS = re.compile(
    rb'(?P<q>q)(?=[\s])'
    rb'|(?P<Q>Q)(?=[\s])'
    rb'|1 0 0 1 (?P<cmx>-?[\d.]+) -?[\d.]+ cm'          # traslación (q/cm/Q anidados de las tablas)
    rb'|/(?P<fname>F\d+) (?P<fsize>[\d.]+) Tf'
    rb'|1 0 0 1 (?P<tmx>-?[\d.]+) -?[\d.]+ Tm'          # fija el origen de la línea de texto
    rb'|(?P<tdx>-?[\d.]+) -?[\d.]+ Td'                  # mueve dentro de esa línea (así alinea reportlab)
    rb'|\((?P<tj>(?:[^()\\]|\\.)*)\)\s*Tj'
    rb'|\[(?P<TJ>(?:[^\[\]])*)\]\s*TJ'
)


def _runs_con_posicion(pdf):
    """Como `_runs_de_texto`, pero además de fuente/tamaño devuelve la
    posición x0 (en pt, en el sistema de coordenadas de la página) donde
    reportlab empezó a dibujar cada fragmento de texto.

    reportlab no alinea a la derecha/centro moviendo la celda -- calcula el
    ancho de la línea con `stringWidth` y la corre con un operador `Td`
    relativo *dentro* del mismo bloque BT/ET (el `Tm` sólo fija el punto de
    partida de la línea). Sumar cm (traslación acumulada de las tablas
    anidadas) + Tm + Td da la x real donde arranca el glyph; sumarle
    `pdfmetrics.stringWidth(texto, fuente, tamaño)` da dónde termina -- ese
    borde derecho es lo que hay que comparar entre columnas/bloques.
    Devuelve una lista de (x0, fuente, tamaño, texto)."""
    fuentes = _mapa_fuentes(pdf)
    runs = []
    for stream in _streams_descomprimidos(pdf):
        stack = [0.0]
        cum = 0.0
        fuente = tamano = None
        tm_tx = 0.0
        td_acc = 0.0
        for m in _TOKEN_RE_POS.finditer(stream):
            if m.group('q') is not None:
                stack.append(cum)
            elif m.group('Q') is not None:
                if stack:
                    cum = stack.pop()
            elif m.group('cmx') is not None:
                cum += float(m.group('cmx'))
            elif m.group('fname') is not None:
                fuente = fuentes.get(m.group('fname'), m.group('fname').decode('latin1'))
                tamano = float(m.group('fsize'))
            elif m.group('tmx') is not None:
                tm_tx = float(m.group('tmx'))
                td_acc = 0.0
            elif m.group('tdx') is not None:
                td_acc += float(m.group('tdx'))
            elif m.group('tj') is not None:
                texto = _unescape(m.group('tj')).decode('latin1')
                if texto.strip():
                    runs.append((cum + tm_tx + td_acc, fuente, tamano, texto))
            elif m.group('TJ') is not None:
                texto = b''.join(_unescape(p) for p in _PAREN_RE.findall(m.group('TJ'))).decode('latin1')
                if texto.strip():
                    runs.append((cum + tm_tx + td_acc, fuente, tamano, texto))
    return runs


def _bordes_derechos(runs, texto_esperado):
    """x del borde derecho (x0 + ancho real del glyph run) de CADA run cuyo
    texto es exactamente `texto_esperado` (dos importes iguales -- p.ej.
    TOTAL y BALANCE DUE en la misma factura -- son runs distintos con la
    misma cadena)."""
    from reportlab.pdfbase.pdfmetrics import stringWidth

    bordes = [x0 + stringWidth(texto, fuente, tamano)
              for x0, fuente, tamano, texto in runs if texto.strip() == texto_esperado]
    if not bordes:
        raise AssertionError(f'no se encontró ningún texto igual a {texto_esperado!r}')
    return bordes


def _borde_derecho(runs, texto_esperado):
    """x del borde derecho (x0 + ancho real del glyph run) del primer run
    cuyo texto contiene `texto_esperado`."""
    from reportlab.pdfbase.pdfmetrics import stringWidth

    for x0, fuente, tamano, texto in runs:
        if texto_esperado in texto:
            return x0 + stringWidth(texto, fuente, tamano)
    raise AssertionError(f'no se encontró ningún texto que contenga {texto_esperado!r}')


def _centro(runs, texto_esperado):
    """x del centro horizontal del primer run cuyo texto contiene
    `texto_esperado` (para verificar centrado, no alineación a la
    derecha)."""
    from reportlab.pdfbase.pdfmetrics import stringWidth

    for x0, fuente, tamano, texto in runs:
        if texto_esperado in texto:
            return x0 + stringWidth(texto, fuente, tamano) / 2
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


def test_render_alinea_totales_detalles_y_amount_a_la_derecha():
    """Regresión de un bug real: TableStyle('ALIGN', ..., 'RIGHT') no
    reposiciona un Paragraph (que siempre reclama el ancho completo de la
    celda) -- sin `alignment=TA_RIGHT`/`TA_CENTER` en el propio
    ParagraphStyle, todo lo que el CSS pide alineado queda pegado a la
    izquierda. Verificado con un PDF de control aislado (un Paragraph con
    ALIGN RIGHT de tabla y sin alignment propio sale a la izquierda).

    Estas aserciones comparan bordes derechos reales (x0 + stringWidth),
    no estilos declarados, así que también detectan una regresión de
    columna/padding aunque el `alignment` del estilo siga puesto."""
    from utils.factura_pdf import render_factura_pdf

    pdf = render_factura_pdf(cargar('xcg_con_ob'))
    runs = _runs_con_posicion(pdf)

    # 1) Los cuatro valores del bloque de totales terminan en la misma x.
    #    TOTAL y BALANCE DUE comparten importe (727.77) en esta fixture --
    #    son dos runs distintos con la misma cadena, así que se piden los
    #    dos bordes de una y se verifican ambos.
    borde_subtotal = _borde_derecho(runs, '686.58')
    borde_ob = _borde_derecho(runs, '41.19')
    borde_total, borde_balance = _bordes_derechos(runs, '727.77')

    assert borde_subtotal == pytest.approx(borde_ob, abs=0.5)
    assert borde_subtotal == pytest.approx(borde_total, abs=0.5)
    assert borde_subtotal == pytest.approx(borde_balance, abs=0.5)

    # 2) Ese borde común coincide con el borde derecho de la columna AMOUNT
    #    de la tabla de líneas (header y valores) -- el bloque de totales
    #    llega hasta el mismo margen derecho que la tabla de productos.
    borde_amount_header = _borde_derecho(runs, 'AMOUNT')
    borde_amount_293 = _borde_derecho(runs, '293.34')
    borde_amount_393 = _borde_derecho(runs, '393.24')
    assert borde_amount_header == pytest.approx(borde_amount_293, abs=0.5)
    assert borde_amount_393 == pytest.approx(borde_amount_293, abs=0.5)
    assert borde_subtotal == pytest.approx(borde_amount_header, abs=0.5)

    # 3) Las etiquetas del bloque de detalles ('Invoice #:', 'Date:'...)
    #    terminan todas en la misma x, justo antes de sus valores.
    etiquetas = ['Invoice #:', 'Date:', 'Terms:', 'Due Date:', 'Currency:']
    bordes_etiquetas = [_borde_derecho(runs, e) for e in etiquetas]
    for b in bordes_etiquetas[1:]:
        assert b == pytest.approx(bordes_etiquetas[0], abs=0.5)

    # 4) QUANTITY: los valores quedan centrados bajo su header (no
    #    pegados a la izquierda de la columna). '2.00' también aparece en
    #    DETAILS (mismo valor que QUANTITY para un producto sin pesar,
    #    por diseño), pero a 8.5pt -- QUANTITY es la única columna a 8pt
    #    (`st_qty`), así que ese tamaño desambigua cuál run es cuál.
    centro_header_qty = _centro(runs, 'QUANTITY')
    runs_qty_8pt = [r for r in runs if r[2] == 8 and r[3].strip() == '2.00']
    assert runs_qty_8pt, 'no se encontró el valor de QUANTITY a 8pt'
    x0, fuente, tamano, texto = runs_qty_8pt[0]
    from reportlab.pdfbase.pdfmetrics import stringWidth
    centro_valor_qty = x0 + stringWidth(texto, fuente, tamano) / 2
    assert centro_valor_qty == pytest.approx(centro_header_qty, abs=1.5)
