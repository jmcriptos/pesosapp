/** Estructura compatible con QuickBooks
 *
 *  CAMBIOS 2026-08-28
 *  1. IMPUESTO: `tax_rate` que manda la app NO es un porcentaje, es el Id del
 *     TaxCode de QBO (10 = OB 6%, 14 = OB Non Tax Local Prod). Las tablas
 *     viejas solo contemplaban 0/6/9, así que 10 y 14 caían las dos al mismo
 *     fallback y encima se calculaba un TotalTax inventado. Ahora el código
 *     viaja tal cual y QBO calcula la tasa.
 *  2. NOMBRE DEL PRODUCTO: la app manda `descripcion` (en español) y acá se
 *     buscaba `product_name || name || description`. Quedaba vacío SIEMPRE, y
 *     por eso ItemRef.name salía vacío y no se detectaba ninguna clase.
 *  3. MONEDA / TIPO DE CAMBIO: se setean CurrencyRef y ExchangeRate, pero solo
 *     cuando la app manda los campos nuevos. Mientras no los mande, se comporta
 *     igual que hoy — así este nodo se puede desplegar solo, sin esperar la app.
 *  4. Amount redondeado a 2 decimales (0.1*3 daba 0.30000000000000004).
 *  5. Se eliminó getProductName(): buscaba datos de Item en $input, donde solo
 *     llegan las consultas de DocNumber. Nunca tuvo con qué responder.
 */

// ---------- helpers ----------
const nextInvoiceNumber = () => {
  const allItems = $input.all();
  let allNumbers = [];

  for (const item of allItems) {
    if (item.json?.QueryResponse?.Invoice) {
      for (const inv of item.json.QueryResponse.Invoice) {
        const num = parseInt(inv.DocNumber, 10);
        if (!isNaN(num)) allNumbers.push(num);
      }
    }
    if (item.json?.QueryResponse?.CreditMemo) {
      for (const cm of item.json.QueryResponse.CreditMemo) {
        const num = parseInt(cm.DocNumber, 10);
        if (!isNaN(num)) allNumbers.push(num);
      }
    }
  }

  console.log(`📊 Números encontrados: ${allNumbers.length}`);
  if (allNumbers.length > 0) {
    const sorted = [...allNumbers].sort((a, b) => b - a);
    console.log(`📊 Top 5 números: ${sorted.slice(0, 5).join(', ')}`);
  }

  const maxNumber = allNumbers.length > 0 ? Math.max(...allNumbers) : 5320;
  console.log(`📊 Max DocNumber: ${maxNumber}, nuevo: ${maxNumber + 1}`);
  return (maxNumber + 1).toString();
};

const today = (d = 0) => new Date(Date.now() + d * 864e5).toISOString().slice(0, 10);
const formatDecimal = (num) => Number(num).toFixed(2);
const round2 = (num) => Math.round((Number(num) + Number.EPSILON) * 100) / 100;

// ---------- MAPEO DE PALABRAS CLAVE A CLASES ----------
const classNames = {
  '600000000005541105': 'Cocidos y Ahumados',
  '600000000005391641': 'Atún Van Camps',
  '529395': 'Mantova',
  '600000000005012031': 'Tomate',
  '600000000005391660': 'Untables Underwood'
};

const classKeywords = {
  '600000000005541105': [
    'smoked', 'ahumad', 'cooked', 'cocid',
    'pork', 'cerdo', 'chop', 'chuleta',
    'bacon', 'tocino', 'ham', 'jamon', 'jamón',
    'chorizo', 'salami', 'sausage', 'salchicha',
    'shoulder', 'picnic', 'ribs', 'costilla'
  ],
  '600000000005391641': ['atun', 'atún', 'tuna', 'van camps', 'vancamps', 'van camp'],
  '529395': [
    'mantova', 'oil', 'aceite', 'olive', 'oliva',
    'vinegar', 'vinagre', 'balsamic', 'balsamico',
    'extra virgin', 'virgen extra'
  ],
  '600000000005012031': [
    'tomat', 'tomato', 'ketchup', 'catsup', 'salsa', 'sauce',
    'pasta', 'puree', 'pure', 'puré', 'marinara', 'pomodoro'
  ],
  '600000000005391660': [
    'underwood', 'spread', 'untable', 'pate', 'paté', 'pâté',
    'deviled', 'meat spread'
  ]
};

function detectClassFromProduct(productName) {
  if (!productName) return null;
  const nameLower = productName.toLowerCase();
  for (const [classId, keywords] of Object.entries(classKeywords)) {
    for (const keyword of keywords) {
      if (nameLower.includes(keyword)) {
        console.log(`   🎯 Keyword "${keyword}" → ${classNames[classId]} (${classId})`);
        return classId;
      }
    }
  }
  return null;
}

const classMap = {
  'atun_van_camps': '600000000005391641',
  'cocidos_ahumados': '600000000005541105',
  'mantova': '529395',
  'tomate': '600000000005012031',
  'untables_underwood': '600000000005391660'
};

// ---------- entrada ----------
const body = $('Webhook').first().json?.body;
if (!body) throw new Error('Webhook sin body');

const taxCodeDe = (l) => {
  const v = l?.tax_rate;
  return (v === null || v === undefined || v === '') ? '' : String(Number(v));
};

const taxCodeFactura = taxCodeDe(body.lines?.[0]);
console.log(`🧾 TaxCode de QBO: ${taxCodeFactura || '(ninguno)'}`);

const currencyInput = body.currency || 'XCG';
const currencyDisplayMap = {
  'XCG': 'XCG - Caribbean Guilder',
  'ANG': 'XCG - Caribbean Guilder',
  'USD': 'USD - US Dollar'
};
const currencyDisplay =
  body.currency_display || currencyDisplayMap[currencyInput] || 'XCG - Caribbean Guilder';

console.log(`💰 Currency display: "${currencyDisplay}" (input: "${currencyInput}")`);

const defaultClass = body.default_class || body.class_ref || null;

const factura = {
  CustomerRef: { value: body.customer_qbo_id },
  DocNumber: nextInvoiceNumber(),
  TxnDate: today(),
  DueDate: today(7),
  SalesTermRef: { value: '46' },
  GlobalTaxCalculation: 'TaxExcluded',

  CustomField: [
    { DefinitionId: '1', Name: 'Currency',    Type: 'StringType', StringValue: currencyDisplay },
    { DefinitionId: '2', Name: 'Sales Rep',   Type: 'StringType', StringValue: body.sales_rep || 'OF' },
    { DefinitionId: '3', Name: 'Tax ID No.',  Type: 'StringType', StringValue: body.tax_id || '' }
  ],

  Line: []
};

if (body.currency_qbo) {
  factura.CurrencyRef = { value: body.currency_qbo };
  console.log(`💱 CurrencyRef: ${body.currency_qbo}`);
  if (body.exchange_rate) {
    factura.ExchangeRate = Number(body.exchange_rate);
    console.log(`💱 ExchangeRate: ${factura.ExchangeRate}`);
  }
}

console.log(`📄 Generated DocNumber: ${factura.DocNumber}`);

const map = new Map();
for (const l of body.lines ?? []) {
  const key = `${l.product_qbo_id}_${l.unit_price}`;
  const e = map.get(key) ?? { ...l, qty: 0, descriptions: [] };
  e.qty += Number(l.qty);
  e.descriptions.push(formatDecimal(l.qty));
  map.set(key, e);
}

for (const l of map.values()) {
  const fullProductName =
    l.descripcion || l.product_name || l.name || l.description || '';

  if (!fullProductName) {
    console.log(`⚠️ Línea sin nombre de producto (ID ${l.product_qbo_id})`);
  }

  const lineTaxCode = taxCodeDe(l) || taxCodeFactura;

  const lineItem = {
    DetailType: 'SalesItemLineDetail',
    Description: l.descriptions.join('\t'),
    Amount: round2(l.qty * l.unit_price),
    SalesItemLineDetail: {
      ItemRef: { value: l.product_qbo_id, name: fullProductName },
      Qty: l.qty,
      UnitPrice: l.unit_price
    }
  };

  if (lineTaxCode) {
    lineItem.SalesItemLineDetail.TaxCodeRef = { value: lineTaxCode };
  }

  let lineClass = null;
  if (l.class_ref) {
    lineClass = l.class_ref;
    console.log(`📦 class_ref de la app: ${lineClass}`);
  } else if (l.class_key && classMap[l.class_key]) {
    lineClass = classMap[l.class_key];
  } else {
    lineClass = detectClassFromProduct(fullProductName) || defaultClass;
  }

  if (lineClass) {
    lineItem.SalesItemLineDetail.ClassRef = { value: lineClass };
    console.log(`✅ ClassRef ${lineClass} → ${fullProductName}`);
  } else {
    console.log(`⚠️ Sin clase: '${fullProductName}' (ID ${l.product_qbo_id})`);
  }

  factura.Line.push(lineItem);
}

if (taxCodeFactura) {
  factura.TxnTaxDetail = { TxnTaxCodeRef: { value: taxCodeFactura } };
}

console.log('✅ Factura completa:', JSON.stringify(factura, null, 2));

return [{ json: factura }];
