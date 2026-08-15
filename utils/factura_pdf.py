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
from reportlab.lib.enums import TA_RIGHT
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


def _logo():
    """El logo es opcional a propósito: los tests corren sin el asset y una
    factura sin logo es preferible a una factura que no se genera."""
    ruta = Path(__file__).resolve().parent.parent / 'static' / 'logo_factura.png'
    if not ruta.exists():
        return ''
    try:
        # lazy=0 fuerza a leer imageWidth/imageHeight ya: Image es "lazy" por
        # defecto y setea drawWidth/drawHeight recién al primer acceso a esos
        # atributos, lo que pisaba el drawWidth que fijamos abajo.
        img = Image(str(ruta), lazy=0)
        ancho = 62 * mm
        img.drawWidth = ancho
        img.drawHeight = ancho * (img.imageHeight / img.imageWidth)
        img.hAlign = 'RIGHT'
        return img
    except Exception:
        return ''


def _grid_pesos(pesos, estilo):
    """Los pesos de cada caja en 5 columnas, como el HTML."""
    filas = [pesos[i:i + 5] for i in range(0, len(pesos), 5)]
    filas = [f + [''] * (5 - len(f)) for f in filas]
    tabla = Table(
        [[Paragraph(_xe(c), estilo) for c in fila] for fila in filas],
        colWidths=[12 * mm] * 5,
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
    d = extraer_datos_factura(invoice_json)

    base = getSampleStyleSheet()
    st_normal = ParagraphStyle('n', parent=base['Normal'], fontName='Helvetica',
                               fontSize=8, leading=10)
    st_bold = ParagraphStyle('b', parent=st_normal, fontName='Helvetica-Bold')
    st_small = ParagraphStyle('s', parent=st_normal, fontSize=7, leading=9)
    st_titulo = ParagraphStyle('t', parent=st_normal, fontName='Helvetica-Bold',
                               fontSize=22, alignment=TA_RIGHT)
    st_empresa = ParagraphStyle('e', parent=st_normal, fontName='Helvetica-Bold',
                                fontSize=11)

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
    empresa += [Paragraph(_xe(l), st_normal) for l in EMPRESA[1:]]
    flow.append(Table(
        [[empresa, _logo()]],
        colWidths=[110 * mm, 76 * mm],
        style=TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('ALIGN', (1, 0), (1, 0), 'RIGHT'),
            ('LEFTPADDING', (0, 0), (-1, -1), 0),
            ('RIGHTPADDING', (0, 0), (-1, -1), 0),
        ]),
    ))
    flow.append(Spacer(1, 4 * mm))
    flow.append(Paragraph('INVOICE', st_titulo))
    flow.append(Spacer(1, 6 * mm))

    # Bill To + detalles de la factura
    bill = [Paragraph('BILL TO', st_small), Paragraph(_xe(d['cliente']), st_bold)]
    for linea in d['direccion']:
        if linea != d['cliente']:
            bill.append(Paragraph(_xe(linea), st_normal))
    if d['crib']:
        bill.append(Paragraph(f'CRIB: {_xe(d["crib"])}', st_small))

    detalles = [
        ('Invoice #:', d['numero']),
        ('Date:', _fecha(d['fecha'])),
        ('Terms:', d['terminos']),
        ('Due Date:', _fecha(d['vence'])),
        ('Currency:', d['moneda_label']),
    ]
    tabla_detalles = Table(
        [[Paragraph(_xe(k), st_small), Paragraph(_xe(v), st_bold)] for k, v in detalles],
        colWidths=[22 * mm, 44 * mm],
        style=TableStyle([
            ('ALIGN', (0, 0), (0, -1), 'RIGHT'),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
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
    flow.append(Spacer(1, 6 * mm))

    # Tabla de líneas
    cab = ['PRODUCT', 'DETAILS', 'QUANTITY', 'RATE', 'AMOUNT']
    filas = [[Paragraph(f'<b>{_xe(c)}</b>', st_small) for c in cab]]
    for l in d['lineas']:
        detalle = (_grid_pesos(l['pesos'], st_small) if l['pesos']
                   else Paragraph(_xe(l['detalle_texto']), st_small))
        filas.append([
            Paragraph(_xe(l['producto']), st_normal),
            detalle,
            Paragraph(f'{l["qty"]:,.2f}', st_small),
            Paragraph(_money(l['rate']), st_small),
            Paragraph(f'<b>{_money(l["amount"])}</b>', st_small),
        ])

    tabla = Table(filas, colWidths=[52 * mm, 66 * mm, 20 * mm, 20 * mm, 28 * mm],
                  repeatRows=1)
    tabla.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('ALIGN', (2, 0), (-1, -1), 'RIGHT'),
        ('LINEABOVE', (0, 0), (-1, 0), 1.2, colors.black),
        ('LINEBELOW', (0, 0), (-1, 0), 1.2, colors.black),
        ('LINEBELOW', (0, 1), (-1, -2), 0.25, colors.HexColor('#dddddd')),
        ('LINEBELOW', (0, -1), (-1, -1), 1.2, colors.black),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
    ]))
    flow.append(tabla)
    flow.append(Spacer(1, 6 * mm))

    # Datos bancarios + totales
    banco = [Paragraph(_xe(BANCO[0]), st_bold)]
    banco += [Paragraph(_xe(l), st_small) for l in BANCO[1:]]

    totales_datos = [
        ('SUBTOTAL', _money(d['subtotal'])),
        (f'OB ({_pct(d["ob_pct"])}%)', _money(d['ob'])),
        ('TOTAL', _money(d['total'])),
        ('BALANCE DUE', _money(d['balance'])),
    ]
    totales = Table(
        [[Paragraph(_xe(k), st_normal), Paragraph(f'<b>{v}</b>', st_normal)]
         for k, v in totales_datos],
        colWidths=[40 * mm, 34 * mm],
        style=TableStyle([
            ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
            ('LINEABOVE', (0, -1), (-1, -1), 1.2, colors.black),
            ('TOPPADDING', (0, 0), (-1, -1), 3),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ]),
    )
    flow.append(KeepTogether(Table(
        [[banco, totales]],
        colWidths=[112 * mm, 74 * mm],
        style=TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('LEFTPADDING', (0, 0), (-1, -1), 0),
            ('RIGHTPADDING', (0, 0), (-1, -1), 0),
        ]),
    )))

    doc.build(flow)
    return buf.getvalue()
