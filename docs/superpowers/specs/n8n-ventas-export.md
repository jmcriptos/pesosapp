# Workflow de ventas del dashboard en n8n — export del 2026-09-12

Responde al webhook de `N8N_QB_SALES_WEBHOOK_URL`. Path del webhook y realm
id omitidos. Fuente de verdad de la Fase 2 del plan
`2026-09-11-qbo-api-directa.md`.

```
Webhook (POST, responde con nodo Respond)
  └─▶ Code «Parse Dates1»: from_date / to_date del body (default: 1 de enero → hoy)
        └─▶ GET /query?query=SELECT * FROM Invoice WHERE TxnDate >= 'from' AND TxnDate <= 'to' MAXRESULTS 1000&minorversion=73
              └─▶ Code «Process Transactions1» (abajo)
                    └─▶ Respond to Webhook
```

Lo que devuelve, tal cual lo consume `_normalizar_metricas_ventas_quickbooks`:

```json
{
  "transactions": [
    {
      "date": "2026-09-11",
      "invoice_number": "5882",
      "customer": "Roberto da Silva",
      "product": "Smoked and Cooked:Smoked Pork Chop",
      "quantity": 6,
      "unit_price": 13,
      "amount": 78,
      "currency_origin": "ANG",
      "fx_applied": 1,
      "transaction_type": "Invoice"
    }
  ],
  "summary": {"total_amount": 78, "total_invoices": 1, "total_lines": 1}
}
```

Reglas del nodo de código:

- Una fila por línea `SalesItemLineDetail` de cada factura. Se omiten las
  líneas con monto ≤ 0.
- `amount` y `unit_price` ya vienen **en florines**: si `CurrencyRef` es
  `USD` se multiplican por **1,78 fijo** (no por el `ExchangeRate` de la
  factura). El conjunto `USD_CUSTOMERS` del código no se usa.
- Factura sin líneas de detalle: una fila con `product: '(sin detalle)'`,
  `quantity: 0` y `amount = (TotalAmt − TotalTax) × fx`.
- **No** hay peso, **no** se restan notas de crédito, **no** hay paginación
  (`MAXRESULTS 1000`: más de mil facturas en el rango se truncan en silencio).
- `date` es `TxnDate`; `invoice_number` es `DocNumber` (o `Id` si falta).

## Nodo «Process Transactions1»

```js
// Extraer facturas del response QBO
const body = $json.QueryResponse ?? {};
const invoices = Array.isArray(body.Invoice) ? body.Invoice : [];

// Clientes facturados en USD que pagan en ANG
const USD_CUSTOMERS = new Set([
  'Caribe Nobo', 'Famoso Supermarket', 'Latinova', 'Deli Nova'
]);
const USD_TO_ANG = 1.78;

const n  = (v) => Number.isFinite(Number(v)) ? Number(v) : 0;
const r2 = (x) => Math.round((x + Number.EPSILON) * 100) / 100;

const out = [];

for (const inv of invoices) {
  const customerName = inv.CustomerRef?.name || 'Sin cliente';
  const currency     = inv.CurrencyRef?.value || 'ANG';
  const fxRate       = currency === 'USD' ? USD_TO_ANG : 1;

  const lines = Array.isArray(inv.Line) ? inv.Line : [];
  const detailLines = lines.filter(l => l.DetailType === 'SalesItemLineDetail');

  if (detailLines.length > 0) {
    for (const line of detailLines) {
      const detail  = line.SalesItemLineDetail || {};
      const qty     = n(detail.Qty);
      const lineAmt = r2(n(line.Amount) * fxRate);
      if (lineAmt <= 0) continue;

      out.push({
        date:             inv.TxnDate || '',
        invoice_number:   String(inv.DocNumber || inv.Id || ''),
        customer:         customerName,
        product:          detail.ItemRef?.name || 'Sin producto',
        quantity:         qty,
        unit_price:       r2(n(detail.UnitPrice) * fxRate),
        amount:           lineAmt,
        currency_origin:  currency,
        fx_applied:       fxRate,
        transaction_type: 'Invoice',
      });
    }
  } else {
    // Fallback: sin líneas de detalle, usar total neto
    const gross = n(inv.TotalAmt);
    const tax   = n(inv.TxnTaxDetail?.TotalTax);
    const net   = r2((gross - tax) * fxRate);
    if (net <= 0) continue;

    out.push({
      date:             inv.TxnDate || '',
      invoice_number:   String(inv.DocNumber || inv.Id || ''),
      customer:         customerName,
      product:          '(sin detalle)',
      quantity:         0,
      unit_price:       0,
      amount:           net,
      currency_origin:  currency,
      fx_applied:       fxRate,
      transaction_type: 'Invoice',
    });
  }
}

const totalAmount   = r2(out.reduce((s, t) => s + t.amount, 0));
const totalInvoices = new Set(out.map(t => t.invoice_number)).size;

return [{
  json: {
    transactions: out,
    summary: {
      total_amount:   totalAmount,
      total_invoices: totalInvoices,
      total_lines:    out.length,
    }
  }
}];
```
