"""Normalización de facturas de QuickBooks.

`extraer_datos_factura` normaliza el objeto Invoice de QBO a un dict plano
(testeable con aserciones ricas) que contiene todos los datos necesarios para
el renderizado de PDF.

El módulo es puro: sin Flask, sin base de datos, sin red.
"""
import re
from datetime import datetime
from io import BytesIO
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    Image, KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle,
)


def _pick_invoice(src):
    """QBO puede venir envuelto de varias formas según el nodo de n8n."""
    if not src:
        return {}
    if isinstance(src, list):
        src = src[0] if src else {}
    if not isinstance(src, dict):
        return {}
    if isinstance(src.get('Invoice'), dict):
        return src['Invoice']
    query = src.get('QueryResponse') or {}
    if isinstance(query.get('Invoice'), list) and query['Invoice']:
        return query['Invoice'][0]
    return src


def _es_usd(inv):
    ref = inv.get('CurrencyRef') or {}
    texto = f"{ref.get('value') or ''} {ref.get('name') or ''}".upper()
    return 'USD' in texto or 'DOLLAR' in texto


def _pesos_de_descripcion(desc):
    """La descripción de QBO trae los pesos de cada caja separados por
    tabulaciones o espacios. Si tiene letras es una nota, no pesos."""
    if not desc or re.search(r'[A-Za-zÁÉÍÓÚÑáéíóúñ]', desc):
        return []
    pesos = []
    for token in re.split(r'\s+', desc.strip()):
        try:
            valor = float(token)
        except ValueError:
            continue
        if valor > 0:
            pesos.append(f'{valor:.2f}')
    return pesos


def extraer_datos_factura(invoice_json):
    inv = _pick_invoice(invoice_json)
    bill = inv.get('BillAddr') or {}

    lineas = []
    for l in inv.get('Line') or []:
        if l.get('DetailType') != 'SalesItemLineDetail':
            continue
        det = l.get('SalesItemLineDetail') or {}
        nombre = (det.get('ItemRef') or {}).get('name') or ''
        producto = nombre.split(':')[1].strip() if ':' in nombre else nombre
        desc = l.get('Description') or ''
        pesos = _pesos_de_descripcion(desc)
        lineas.append({
            'producto': producto,
            'pesos': pesos,
            'detalle_texto': '' if pesos else desc,
            'qty': float(det.get('Qty') or 0),
            'rate': float(det.get('UnitPrice') or 0),
            'amount': float(l.get('Amount') or 0),
        })

    subtotal = float(inv.get('SubTotal') or 0)
    if not subtotal:
        subtotal = sum(l['amount'] for l in lineas)

    tax = inv.get('TxnTaxDetail') or {}
    ob = float(tax.get('TotalTax') or 0)
    tax_lines = tax.get('TaxLine') or []
    if tax_lines and (tax_lines[0].get('TaxLineDetail') or {}).get('TaxPercent') is not None:
        ob_pct = float(tax_lines[0]['TaxLineDetail']['TaxPercent'])
    elif ob and subtotal:
        ob_pct = (ob / subtotal) * 100
    else:
        ob_pct = 0.0

    total = float(inv.get('TotalAmt') if inv.get('TotalAmt') is not None else subtotal + ob)
    usd = _es_usd(inv)

    direccion = [v for v in (bill.get('Line1'), bill.get('Line2'), bill.get('City')) if v]
    crib = re.sub(r'^CRIB:\s*', '', bill.get('CountrySubDivisionCode') or '', flags=re.I).strip()

    return {
        'numero': str(inv.get('DocNumber') or inv.get('Id') or ''),
        'fecha': inv.get('TxnDate') or '',
        'vence': inv.get('DueDate') or '',
        'terminos': (inv.get('SalesTermRef') or {}).get('name') or '',
        'cliente': (inv.get('CustomerRef') or {}).get('name') or '',
        'direccion': direccion,
        'crib': crib,
        'moneda': 'USD' if usd else 'XCG',
        'moneda_label': 'USD - US Dollar' if usd else 'XCG - Caribbean Guilder',
        'lineas': lineas,
        'subtotal': round(subtotal, 2),
        'ob_pct': ob_pct,
        'ob': round(ob, 2),
        'total': round(total, 2),
        'balance': round(float(inv.get('Balance') if inv.get('Balance') is not None else total), 2),
    }


GRIS = colors.HexColor('#666666')

EMPRESA = [
    'JOMAR FOODS, BV',
    'Industriepark Brievengat, Unit H.I.1.',
    'Willemstad, Curacao',
    'WhatsApp: +5999 6905484',
    'sales@jomarfoods.com',
    'www.jomarfoods.com',
]

BANCO = [
    'Jomar Foods, BV',
    'Crib nr.: 102505329',
    'K.V.K.: 148768',
    'RBC Account#: 8000009000132576',
]


def _xe(s):
    """Escapa para Paragraph de reportlab, que interpreta markup tipo XML."""
    return (str(s or '')
            .replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;'))


def _money(n):
    return f'{float(n or 0):,.2f}'


def _pct(p):
    return str(round(p)) if abs(p - round(p)) < 0.05 else f'{p:.1f}'


def _fecha(iso):
    """QBO entrega 2026-08-11; la factura se ve como 08/11/2026."""
    if not iso:
        return ''
    try:
        return datetime.strptime(str(iso)[:10], '%Y-%m-%d').strftime('%m/%d/%Y')
    except ValueError:
        return str(iso)


def _px(n):
    """CSS px -> pt (96dpi vs 72dpi, el factor estándar es 0.75)."""
    return n * 0.75


def _logo():
    """El logo es opcional a propósito: los tests corren sin el asset y una
    factura sin logo es preferible a una factura que no se genera.

    CSS de referencia: max-height 154px, max-width 420px, aspect ratio
    preservado. Con el asset de 850x480 el alto es lo que manda (~40.7mm),
    dando un ancho de ~72mm."""
    ruta = Path(__file__).resolve().parent.parent / 'static' / 'logo_factura.png'
    if not ruta.exists():
        return ''
    try:
        # lazy=0 fuerza a leer imageWidth/imageHeight ya: Image es "lazy" por
        # defecto y setea drawWidth/drawHeight recién al primer acceso a esos
        # atributos, lo que pisaba el drawWidth que fijamos abajo.
        img = Image(str(ruta), lazy=0)
        max_h, max_w = _px(154), _px(420)
        escala = min(max_h / img.imageHeight, max_w / img.imageWidth)
        img.drawWidth = img.imageWidth * escala
        img.drawHeight = img.imageHeight * escala
        img.hAlign = 'RIGHT'
        return img
    except Exception:
        return ''


def _grid_pesos(pesos, estilo, ancho_col):
    """Los pesos de cada caja en 5 columnas iguales, como el HTML
    (line-height 1.6, cada peso alineado a la derecha)."""
    filas = [pesos[i:i + 5] for i in range(0, len(pesos), 5)]
    filas = [f + [''] * (5 - len(f)) for f in filas]
    tabla = Table(
        [[Paragraph(_xe(c), estilo) for c in fila] for fila in filas],
        colWidths=[ancho_col / 5] * 5,
    )
    tabla.setStyle(TableStyle([
        ('ALIGN', (0, 0), (-1, -1), 'RIGHT'),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 2),
        ('TOPPADDING', (0, 0), (-1, -1), 0),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 1),
    ]))
    return tabla


def render_factura_pdf(invoice_json):
    """Genera el PDF de una factura A4. Los tamaños, colores y espaciados de
    abajo están tomados 1:1 del CSS del generador HTML que produce las
    facturas de referencia (5802-5805); las conversiones px->pt usan el
    factor estándar 0.75 (96dpi CSS vs 72dpi PDF). Excepción conocida: el
    tracking/letter-spacing del CSS no tiene equivalente en reportlab
    Paragraph y se omite (no afecta la jerarquía visual: tamaño/peso/color
    sí se respetan)."""
    d = extraer_datos_factura(invoice_json)

    ancho_contenido = 186 * mm  # A4 (210mm) - 12mm de margen a cada lado

    # NOTA: `leading` (interlineado) es fontSize * line-height del CSS, y
    # ambos ya están en puntos/sin unidad -> NO pasa por _px(). _px() es solo
    # para paddings/márgenes/anchos que el CSS da en px (8px, 20px, etc).
    base = getSampleStyleSheet()
    st_normal = ParagraphStyle('n', parent=base['Normal'], fontName='Helvetica',
                               fontSize=9, leading=9 * 1.2)
    st_bold = ParagraphStyle('b', parent=st_normal, fontName='Helvetica-Bold')
    st_gris = ParagraphStyle('g', parent=st_normal, textColor=GRIS)

    st_titulo = ParagraphStyle('t', parent=st_normal, fontName='Helvetica-Bold',
                               fontSize=26, leading=26 * 1.15, alignment=TA_RIGHT)

    st_empresa = ParagraphStyle('e', parent=st_normal, fontName='Helvetica-Bold',
                                fontSize=14, leading=14 * 1.2, spaceAfter=_px(5))
    st_empresa_linea = ParagraphStyle('el', parent=st_normal, fontSize=9,
                                      leading=9 * 1.2, spaceBefore=_px(1))

    st_bill_label = ParagraphStyle('bt', parent=st_normal, fontName='Helvetica-Bold',
                                   fontSize=8.5, leading=8.5 * 1.2, textColor=GRIS,
                                   spaceAfter=_px(5))
    st_crib = ParagraphStyle('cr', parent=st_normal, fontSize=8.5, leading=8.5 * 1.2,
                             textColor=GRIS, spaceBefore=_px(4))
    # NOTA sobre alineación: TableStyle('ALIGN', ...) NO reposiciona un
    # Paragraph -- Paragraph.wrap() siempre reclama el ancho completo de la
    # celda (necesita saber dónde hacer word-wrap), así que para reportlab
    # ya "usa todo el espacio" y el ALIGN de la tabla no tiene nada que
    # mover. La alineación real de un Paragraph sale de su propio
    # ParagraphStyle.alignment. Por eso todo lo que el CSS pide alineado a
    # la derecha o centrado lleva su propio estilo con `alignment=` acá
    # abajo, y los ('ALIGN', ...) que quedan en los TableStyle son sólo
    # documentación de intención (no rompen nada, pero tampoco alinean).
    st_detalle_label = ParagraphStyle('dl', parent=st_normal, fontSize=9, textColor=GRIS,
                                      alignment=TA_RIGHT)
    st_detalle_val = ParagraphStyle('dv', parent=st_bold, fontSize=9)

    st_th = ParagraphStyle('th', parent=st_normal, fontName='Helvetica-Bold',
                           fontSize=8.5, leading=8.5 * 1.2)
    st_th_center = ParagraphStyle('thc', parent=st_th, alignment=TA_CENTER)
    st_th_right = ParagraphStyle('thr', parent=st_th, alignment=TA_RIGHT)
    st_product = ParagraphStyle('pr', parent=st_normal, fontSize=8.5, leading=8.5 * 1.2)
    st_details = ParagraphStyle('de', parent=st_normal, fontSize=8.5, leading=8.5 * 1.2)
    st_grid = ParagraphStyle('gr', parent=st_normal, fontSize=8.5, leading=8.5 * 1.6)
    st_qty = ParagraphStyle('qt', parent=st_normal, fontSize=8, leading=8 * 1.2,
                            alignment=TA_CENTER)
    st_rate = ParagraphStyle('ra', parent=st_normal, fontSize=8.5, leading=8.5 * 1.2,
                             alignment=TA_RIGHT)
    st_amount = ParagraphStyle('am', parent=st_bold, fontSize=9, alignment=TA_RIGHT)

    st_banco_titulo = ParagraphStyle('bkt', parent=st_normal, fontName='Helvetica-Bold',
                                     fontSize=11, leading=11 * 1.2, textColor=GRIS)
    st_banco_linea = ParagraphStyle('bkl', parent=st_normal, fontSize=9, textColor=GRIS,
                                    leading=9 * 1.3)
    st_total_label = ParagraphStyle('tl', parent=st_normal, fontSize=10, leading=10 * 1.2)
    st_total_val = ParagraphStyle('tv', parent=st_total_label, fontName='Helvetica-Bold',
                                  alignment=TA_RIGHT)
    st_balance_label = ParagraphStyle('bl', parent=st_normal, fontName='Helvetica-Bold',
                                      fontSize=13, leading=13 * 1.2)
    st_balance_val = ParagraphStyle('bv', parent=st_balance_label, alignment=TA_RIGHT)

    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=12 * mm, rightMargin=12 * mm,
        topMargin=12 * mm, bottomMargin=12 * mm,
        title=f'Invoice {d["numero"]}',
    )

    flow = []

    # Encabezado: empresa a la izquierda, logo a la derecha
    empresa = [Paragraph(_xe(EMPRESA[0]), st_empresa)]
    empresa += [Paragraph(_xe(l), st_empresa_linea) for l in EMPRESA[1:]]
    flow.append(Table(
        [[empresa, _logo()]],
        colWidths=[114 * mm, 72 * mm],
        style=TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('ALIGN', (1, 0), (1, 0), 'RIGHT'),
            ('LEFTPADDING', (0, 0), (-1, -1), 0),
            ('RIGHTPADDING', (0, 0), (-1, -1), 0),
        ]),
    ))
    flow.append(Spacer(1, _px(20)))
    flow.append(Paragraph('INVOICE', st_titulo))
    flow.append(Spacer(1, _px(15)))

    # Bill To + detalles de la factura
    bill = [Paragraph('BILL TO', st_bill_label), Paragraph(_xe(d['cliente']), st_bold)]
    for linea in d['direccion']:
        if linea != d['cliente']:
            bill.append(Paragraph(_xe(linea), st_normal))
    if d['crib']:
        bill.append(Paragraph(f'CRIB: {_xe(d["crib"])}', st_crib))

    detalles = [
        ('Invoice #:', d['numero']),
        ('Date:', _fecha(d['fecha'])),
        ('Terms:', d['terminos']),
        ('Due Date:', _fecha(d['vence'])),
        ('Currency:', d['moneda_label']),
    ]
    tabla_detalles = Table(
        [[Paragraph(_xe(k), st_detalle_label), Paragraph(_xe(v), st_detalle_val)]
         for k, v in detalles],
        colWidths=[22 * mm, 44 * mm],
        style=TableStyle([
            ('ALIGN', (0, 0), (0, -1), 'RIGHT'),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('RIGHTPADDING', (0, 0), (0, -1), _px(8)),
            ('TOPPADDING', (0, 0), (-1, -1), 0),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
        ]),
    )
    flow.append(Table(
        [[bill, tabla_detalles]],
        colWidths=[120 * mm, 66 * mm],
        style=TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('LEFTPADDING', (0, 0), (-1, -1), 0),
            ('RIGHTPADDING', (0, 0), (-1, -1), 0),
        ]),
    ))
    flow.append(Spacer(1, _px(20)))

    # Tabla de líneas: PRODUCT 34% / DETAILS 33% / QUANTITY 10% / RATE 10% / AMOUNT 13%
    col_product = ancho_contenido * 0.34
    col_details = ancho_contenido * 0.33
    col_qty = ancho_contenido * 0.10
    col_rate = ancho_contenido * 0.10
    col_amount = ancho_contenido * 0.13

    cab = ['PRODUCT', 'DETAILS', 'QUANTITY', 'RATE', 'AMOUNT']
    cab_estilos = [st_th, st_th, st_th_center, st_th_right, st_th_right]
    filas = [[Paragraph(_xe(c), est) for c, est in zip(cab, cab_estilos)]]
    for l in d['lineas']:
        detalle = (_grid_pesos(l['pesos'], st_grid, col_details) if l['pesos']
                   else Paragraph(_xe(l['detalle_texto']), st_details))
        filas.append([
            Paragraph(_xe(l['producto']), st_product),
            detalle,
            Paragraph(f'{l["qty"]:,.2f}', st_qty),
            Paragraph(_money(l['rate']), st_rate),
            Paragraph(_money(l['amount']), st_amount),
        ])

    tabla = Table(filas, colWidths=[col_product, col_details, col_qty, col_rate, col_amount],
                  repeatRows=1)
    tabla.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('ALIGN', (0, 0), (1, -1), 'LEFT'),
        ('ALIGN', (2, 0), (2, -1), 'CENTER'),
        ('ALIGN', (3, 0), (4, -1), 'RIGHT'),
        ('LINEABOVE', (0, 0), (-1, 0), _px(2), colors.black),
        ('LINEBELOW', (0, 0), (-1, 0), _px(2), colors.black),
        ('LINEBELOW', (0, 1), (-1, -2), _px(1), colors.HexColor('#dddddd')),
        ('LINEBELOW', (0, -1), (-1, -1), _px(2), colors.black),
        ('TOPPADDING', (0, 0), (-1, -1), _px(8)),
        ('BOTTOMPADDING', (0, 0), (-1, -1), _px(8)),
        ('LEFTPADDING', (0, 0), (-1, -1), _px(6)),
        ('RIGHTPADDING', (0, 0), (-1, -1), _px(6)),
        ('RIGHTPADDING', (0, 1), (0, -1), _px(25)),
    ]))
    flow.append(tabla)
    flow.append(Spacer(1, 6 * mm))

    # Datos bancarios + totales
    banco = [Paragraph(_xe(BANCO[0]), st_banco_titulo)]
    banco += [Paragraph(_xe(l), st_banco_linea) for l in BANCO[1:]]

    totales_datos = [
        (st_total_label, st_total_val, 'SUBTOTAL', _money(d['subtotal'])),
        (st_total_label, st_total_val, f'OB ({_pct(d["ob_pct"])}%)', _money(d['ob'])),
        (st_total_label, st_total_val, 'TOTAL', _money(d['total'])),
        (st_balance_label, st_balance_val, 'BALANCE DUE', _money(d['balance'])),
    ]
    totales = Table(
        [[Paragraph(_xe(k), st_l), Paragraph(_xe(v), st_v)] for st_l, st_v, k, v in totales_datos],
        colWidths=[45 * mm, 40 * mm],
        style=TableStyle([
            ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
            # Sin este RIGHTPADDING explícito, la celda de valor cae en el
            # padding por defecto de reportlab (6pt planos, no derivado de
            # ningún px del CSS) en vez del mismo _px(6) que usa la columna
            # AMOUNT de la tabla de líneas -- por eso los importes quedaban
            # ~1.5pt más adentro que AMOUNT y no coincidían con su borde
            # derecho pese a estar ambos "pegados" a la misma margen.
            ('LEFTPADDING', (0, 0), (-1, -1), _px(6)),
            ('RIGHTPADDING', (0, 0), (-1, -1), _px(6)),
            # Regla doble (no sólida) sobre BALANCE DUE, como el CSS de referencia.
            ('LINEABOVE', (0, -1), (-1, -1), _px(1), colors.black, None, None, None, 2, _px(3)),
            ('TOPPADDING', (0, 0), (-1, -2), _px(8)),
            ('BOTTOMPADDING', (0, 0), (-1, -1), _px(8)),
            ('TOPPADDING', (0, -1), (-1, -1), _px(12) + _px(6)),
        ]),
    )
    flow.append(KeepTogether(Table(
        [[banco, totales]],
        colWidths=[101 * mm, 85 * mm],
        style=TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('LEFTPADDING', (0, 0), (-1, -1), 0),
            ('RIGHTPADDING', (0, 0), (-1, -1), 0),
        ]),
    )))

    doc.build(flow)
    return buf.getvalue()
