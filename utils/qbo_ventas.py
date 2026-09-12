"""Ventas del dashboard leídas directo de QuickBooks (Fase 2).

Reemplaza al workflow de n8n «qb-sales-dashboard»
(docs/superpowers/specs/n8n-ventas-export.md). Devuelve EXACTAMENTE la
misma forma, para que `_normalizar_metricas_ventas_quickbooks` no cambie:

    {"transactions": [fila, ...], "summary": {...}}

con una fila por línea de producto y los montos ya en florines.

Única diferencia deliberada: n8n pedía `MAXRESULTS 1000` sin paginar y
truncaba en silencio; acá se pagina. Todo lo demás se replica tal cual,
incluida la tasa USD fija, para que la comparación en paralelo dé cero.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal, ROUND_HALF_UP

TASA_USD_POR_DEFECTO = Decimal('1.78')
PAGINA = 1000
CENTAVO = Decimal('0.01')


def _num(valor) -> Decimal:
    """`n()` de n8n: número o 0."""
    try:
        d = Decimal(str(valor))
    except Exception:
        return Decimal('0')
    return d if d.is_finite() else Decimal('0')


def _r2(d: Decimal):
    """`r2()` de n8n: dos decimales, media-arriba. Entero si no tiene decimales."""
    q = d.quantize(CENTAVO, rounding=ROUND_HALF_UP)
    return int(q) if q == q.to_integral_value() else float(q)


def aplanar_facturas(facturas: list, tasa_usd=TASA_USD_POR_DEFECTO) -> dict:
    """El nodo «Process Transactions1» de n8n, línea por línea."""
    tasa_usd = Decimal(str(tasa_usd))
    filas = []
    for inv in facturas or []:
        cliente = (inv.get('CustomerRef') or {}).get('name') or 'Sin cliente'
        moneda = (inv.get('CurrencyRef') or {}).get('value') or 'ANG'
        fx = tasa_usd if moneda == 'USD' else Decimal('1')
        numero = str(inv.get('DocNumber') or inv.get('Id') or '')
        fecha = inv.get('TxnDate') or ''

        lineas = [l for l in (inv.get('Line') or [])
                  if isinstance(l, dict) and l.get('DetailType') == 'SalesItemLineDetail']
        if lineas:
            for linea in lineas:
                detalle = linea.get('SalesItemLineDetail') or {}
                monto = _num(linea.get('Amount')) * fx
                if monto.quantize(CENTAVO, rounding=ROUND_HALF_UP) <= 0:
                    continue
                filas.append({
                    'date': fecha,
                    'invoice_number': numero,
                    'customer': cliente,
                    'product': (detalle.get('ItemRef') or {}).get('name') or 'Sin producto',
                    'quantity': _r2(_num(detalle.get('Qty'))),
                    'unit_price': _r2(_num(detalle.get('UnitPrice')) * fx),
                    'amount': _r2(monto),
                    'currency_origin': moneda,
                    'fx_applied': _r2(fx),
                    'transaction_type': 'Invoice',
                })
        else:
            bruto = _num(inv.get('TotalAmt'))
            impuesto = _num((inv.get('TxnTaxDetail') or {}).get('TotalTax'))
            neto = (bruto - impuesto) * fx
            if neto.quantize(CENTAVO, rounding=ROUND_HALF_UP) <= 0:
                continue
            filas.append({
                'date': fecha,
                'invoice_number': numero,
                'customer': cliente,
                'product': '(sin detalle)',
                'quantity': 0,
                'unit_price': 0,
                'amount': _r2(neto),
                'currency_origin': moneda,
                'fx_applied': _r2(fx),
                'transaction_type': 'Invoice',
            })

    total = sum((Decimal(str(f['amount'])) for f in filas), Decimal('0'))
    return {
        'transactions': filas,
        'summary': {
            'total_amount': _r2(total),
            'total_invoices': len({f['invoice_number'] for f in filas}),
            'total_lines': len(filas),
        },
    }


def _query_facturas(desde: date, hasta: date, inicio: int) -> str:
    return (
        "SELECT * FROM Invoice "
        f"WHERE TxnDate >= '{desde.isoformat()}' AND TxnDate <= '{hasta.isoformat()}' "
        f"ORDERBY TxnDate STARTPOSITION {inicio} MAXRESULTS {PAGINA}"
    )


def facturas_del_rango(client, desde: date, hasta: date) -> list:
    """Todas las facturas del rango, paginando de a 1000."""
    facturas = []
    inicio = 1
    while True:
        respuesta = client.query(_query_facturas(desde, hasta, inicio))
        pagina = respuesta.get('Invoice') or []
        facturas.extend(pagina)
        if len(pagina) < PAGINA:
            return facturas
        inicio += PAGINA


def consultar_ventas(client, desde: date, hasta: date, tasa_usd=TASA_USD_POR_DEFECTO) -> dict:
    """Lo que hoy devuelve el webhook de ventas de n8n, leído directo de QBO."""
    return aplanar_facturas(facturas_del_rango(client, desde, hasta), tasa_usd)
