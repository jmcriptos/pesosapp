/** Regresion: el monto de linea que QuickBooks acepta.
 *
 *  El 2026-09-08 el pedido 1334 no se pudo facturar:
 *
 *    6070 - Amount is not equal to UnitPrice * Qty.
 *           Supplied value: 1,861.07
 *
 *  Ocho cajas de Porchop Huma Sin Wesu suman 128.350 kg a 14.50,
 *  o sea 1861.075 exactos: MEDIO CENTAVO. QuickBooks redondea
 *  media-arriba y espera 1861.08. El nodo sumaba los pesos en
 *  coma flotante (128.35 se guarda como 128.34999999999999432),
 *  el producto daba 1861.0749999999998 y round2 lo bajaba a
 *  1861.07. Number.EPSILON (2.2e-16) es 25 veces mas chico que
 *  el error que ya traia la suma de ocho pesos (5.7e-15).
 *
 *  Correr:  node docs/n8n/test-monto-linea.js
 */

const fs = require('fs');
const path = require('path');

const fuente = fs.readFileSync(
  path.join(__dirname, 'generar-numero-factura.js'),
  'utf8'
);

// El Code node de n8n corre envuelto en una funcion con $input y
// $ inyectados, por eso el archivo termina en `return`.
const correrNodo = (body) => {
  const $input = {
    all: () => [{
      json: { QueryResponse: { Invoice: [{ DocNumber: '5863' }] } }
    }]
  };
  const $ = () => ({ first: () => ({ json: { body } }) });
  const silencio = { log: () => {} };
  const nodo = new Function('$input', '$', 'console', fuente);
  return nodo($input, $, silencio)[0].json;
};

// Pedido 1334 tal cual quedo en la base: una linea por caja.
const CAJAS_9294 = [
  13.65, 17.15, 17.40, 13.70, 19.10, 15.50, 14.20, 17.65
];

const linea = (qty, unit_price, qbo_id) => ({
  product_qbo_id: qbo_id,
  descripcion: 'Porchop Huma Sin Wesu',
  product_name: 'Porchop Huma Sin Wesu',
  qty,
  unit_price,
  amount: qty * unit_price,
  tax_rate: 10
});

const body = {
  order_id: 1334,
  customer_qbo_id: '6',
  currency: 'XCG',
  currency_qbo: 'ANG',
  exchange_rate: 1,
  lines: [
    ...CAJAS_9294.map((p) => linea(p, 14.5, '1359')),
    linea(18.85, 14.3, '1366')
  ]
};

const fallos = [];
const chequear = (que, real, esperado) => {
  if (real !== esperado) {
    fallos.push(`${que}: da ${real}, se esperaba ${esperado}`);
  }
};

const factura = correrNodo(body);
const porItem = {};
for (const l of factura.Line) {
  porItem[l.SalesItemLineDetail.ItemRef.value] = l;
}

const sinWesu = porItem['1359'];
chequear('Qty de las ocho cajas', sinWesu.SalesItemLineDetail.Qty, 128.35);
chequear('Amount 128.35 x 14.50', sinWesu.Amount, 1861.08);

const ham = porItem['1366'];
chequear('Amount 18.85 x 14.30', ham.Amount, 269.56);

// El impuesto sale del subtotal ya redondeado, no de los floats.
chequear(
  'TotalTax 6% sobre 2130.64',
  factura.TxnTaxDetail.TotalTax,
  127.84
);

if (fallos.length) {
  console.error('FALLA:');
  for (const f of fallos) console.error('  - ' + f);
  process.exit(1);
}
console.log('OK: los montos coinciden con lo que calcula QuickBooks');
