"""Render de facturas de QuickBooks a PDF.

Dos responsabilidades separadas a propósito: `extraer_datos_factura` normaliza
el objeto Invoice de QBO a un dict plano (testeable con aserciones ricas), y
`render_factura_pdf` lo dibuja (se verifica estructuralmente).

El módulo es puro: sin Flask, sin base de datos, sin red.
"""
import re


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
