/** Regresiones del nodo que arma la factura de QuickBooks.
 *
 *  1) EL MEDIO CENTAVO
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
 *  2) EL TAXABLE DE CADA LINEA
 *
 *  El nodo mandaba `NON` en las lineas de codigo 13 y 14, y JM
 *  las marcaba TAX a mano en CADA factura: una linea NON se cae
 *  del reporte de ventas gravadas. Los tres codigos de OB
 *  (10, 13, 14) estan marcados `taxable: true` en QuickBooks; el
 *  0% lo define el codigo de la TRANSACCION, no el TAX/NON de la
 *  linea. La linea va TAX siempre.
 *
 *  3) LOS DOS CAMPOS DE MONEDA
 *
 *  `Currency2` (1000000003) es el que se ve en la pantalla de QBO
 *  y nadie lo escribia: se quedaba en XCG. El `Currency` legacy
 *  (DefinitionId 1) que si se llenaba es OTRO campo, que la
 *  pantalla no muestra.
 *
 *  Correr:  node docs/n8n/test-nodo-factura.js
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

const armarBody = (lines, extra = {}) => ({
  order_id: 1334,
  customer_qbo_id: '6',
  currency: 'XCG',
  currency_qbo: 'ANG',
  exchange_rate: 1,
  lines,
  ...extra
});

const fallos = [];
const chequear = (que, real, esperado) => {
  if (real !== esperado) {
    fallos.push(`${que}: da ${real}, se esperaba ${esperado}`);
  }
};

// ---------- el medio centavo (pedido 1334) ----------
const factura = correrNodo(armarBody([
  ...CAJAS_9294.map((p) => linea(p, 14.5, '1359')),
  linea(18.85, 14.3, '1366')
]));

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

// ---------- el taxable de cada linea ----------
// 10 = OB 6%, 13 = Non Tax (exportacion), 14 = Local Prod. Los
// tres son `taxable: true` en QuickBooks: la linea va TAX y la
// tasa la pone el codigo de la transaccion.
for (const codigo of [10, 13, 14]) {
  const f = correrNodo(armarBody([linea(10, 14.5, '1359')].map(
    (l) => ({ ...l, tax_rate: codigo })
  )));
  const det = f.Line[0].SalesItemLineDetail;
  chequear(
    `linea con codigo ${codigo}`,
    det.TaxCodeRef.value,
    'TAX'
  );
  // El codigo de la transaccion va SIEMPRE, tambien al 0%: sin el,
  // la venta queda sin clasificar en el reporte de OB. La 5865
  // salio asi -- `TxnTaxDetail: { TotalTax: 0 }` y nada mas.
  chequear(
    `codigo de transaccion con ${codigo}`,
    ((f.TxnTaxDetail || {}).TxnTaxCodeRef || {}).value,
    String(codigo)
  );
  const tl = ((f.TxnTaxDetail || {}).TaxLine || [{}])[0].TaxLineDetail;
  chequear(
    `tasa de la transaccion con ${codigo}`,
    (tl || {}).TaxPercent,
    codigo === 10 ? 6 : 0
  );
  // La TaxRateRef va SIEMPRE en 25, para cualquier codigo. No es
  // la que corresponde -- la del 6% es la 17 -- y esa es la
  // gracia: QuickBooks no la acepta, recalcula la tasa desde el
  // codigo de la transaccion y guarda la correcta. Mandarle la 17
  // "correcta" le rompe el calculo: la 5867 salio al 0% y hubo que
  // ajustarla a mano (2026-09-08). Ver el README.
  chequear(
    `TaxRateRef con ${codigo}`,
    ((tl || {}).TaxRateRef || {}).value,
    '25'
  );
}

// ---------- Currency2 ----------
// Es una LISTA: guarda el id de la opcion, no el texto. Medido el
// 2026-09-08 sobre la 5864 (XCG -> '1') y la 5856 (USD -> '2').
// Y es OTRO campo que el `Currency` legacy: la 5856 tenia el legacy
// en 'USD - US Dollar' y el Currency2 en '1' (XCG) al mismo tiempo.
const campo = (f, id) =>
  (f.CustomField || []).find((c) => c.DefinitionId === id);

const moneda = [
  ['XCG', 'XCG - Caribbean Guilder', '1'],
  ['USD', 'USD - US Dollar', '2']
];

for (const [cur, display, opcion] of moneda) {
  const f = correrNodo(armarBody(
    [linea(10, 14.5, '1359')],
    { currency: cur, currency_display: display }
  ));
  chequear(
    `Currency2 en ${cur}`,
    (campo(f, '1000000003') || {}).StringValue,
    opcion
  );
  // El legacy sigue yendo: es otro campo, no una vista del mismo.
  chequear(
    `Currency legacy en ${cur}`,
    (campo(f, '1') || {}).StringValue,
    display
  );
}

if (fallos.length) {
  console.error('FALLA:');
  for (const f of fallos) console.error('  - ' + f);
  process.exit(1);
}
console.log('OK: montos, taxable de linea y Currency2');
