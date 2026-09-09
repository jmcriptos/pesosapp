/** Nodo Code "Generar Numero Factura": arma la factura de QBO.
 *
 *  OJO AL COPIAR: no lo copies desde el chat ni desde markdown
 *  renderizado. El 2026-08-28 se pego desde un terminal y TODAS
 *  las lineas de mas de ~78 caracteres llegaron cortadas; n8n
 *  respondio "Invalid or unexpected token". Por eso este archivo
 *  no pasa de 72 columnas: copialo desde un editor.
 *
 *  CAMBIOS 2026-08-28
 *  1. IMPUESTO: `tax_rate` NO es un porcentaje, es el Id del
 *     TaxCode de QBO. OJO: esta empresa esta en modo US, asi que
 *     el TaxCodeRef DE LINEA solo acepta 'TAX' o 'NON' (error
 *     6100 si se manda otra cosa). El codigo real va solo en
 *     TxnTaxDetail.TxnTaxCodeRef.
 *     Codigos: 10 = OB 6%, 13 = Non Tax (exportacion),
 *     14 = OB Non Tax Local Prod.
 *     Las tablas viejas solo tenian 0/6/9, asi que 10 y 14 caian
 *     las dos al mismo fallback y ademas se calculaba un
 *     TotalTax inventado. Ahora el codigo viaja tal cual y QBO
 *     calcula la tasa.
 *  2. NOMBRE DEL PRODUCTO: la app lo manda como `descripcion`
 *     y aca se buscaba `product_name || name || description`.
 *     Quedaba vacio SIEMPRE: ItemRef.name salia vacio y no se
 *     detectaba ninguna clase.
 *  3. MONEDA / TIPO DE CAMBIO: se setean CurrencyRef y
 *     ExchangeRate, pero solo si la app manda los campos nuevos.
 *  4. Amount redondeado a 2 decimales (0.1*3 daba
 *     0.30000000000000004).
 *  5. Se elimino getProductName(): buscaba datos de Item en
 *     $input, donde solo llegan las consultas de DocNumber.
 *
 *  CAMBIOS 2026-09-08
 *  1. TAXABLE DE LINEA: se mandaba 'NON' en los codigos 13 y
 *     14, y habia que marcar cada linea como taxable a mano o
 *     la venta se caia del reporte de ventas gravadas. Va TAX
 *     siempre; el 0% lo pone el codigo de la transaccion.
 *  2. MONTO DE LINEA: el redondeo en coma flotante bajaba el
 *     medio centavo en vez de subirlo y QBO rechazaba la
 *     factura con 6070 "Amount is not equal to UnitPrice *
 *     Qty". Ahora la cuenta va en enteros (peso en milesimas,
 *     precio en centavos) con redondeo media-arriba, el mismo
 *     de QuickBooks. Ver docs/n8n/test-nodo-factura.js.
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

  console.log(`Numeros encontrados: ${allNumbers.length}`);
  const maxNumber = allNumbers.length > 0
    ? Math.max(...allNumbers)
    : 5320;
  console.log(`Max DocNumber: ${maxNumber}`);
  return (maxNumber + 1).toString();
};

const today = (d = 0) =>
  new Date(Date.now() + d * 864e5).toISOString().slice(0, 10);

const formatDecimal = (num) => Number(num).toFixed(2);

// ---------- dinero en enteros ----------
// QuickBooks revalida Amount == UnitPrice * Qty con decimales
// exactos y redondeo media-arriba. Calcularlo en coma flotante
// falla justo en el medio centavo: 128.350 kg a 14.50 son
// 1861.075 exactos, pero el double da 1861.0749999999998 y el
// monto salia 1861.07 -> error 6070 (pedido 1334, 2026-09-08).
// Number.EPSILON no alcanzaba: es 25 veces mas chico que el
// error que ya traia la suma de ocho pesos. Por eso el peso
// viaja en milesimas y el precio en centavos, como enteros.
const MIL = 1000;   // el peso trae 3 decimales
const CENT = 100;   // el precio trae 2

const enEnteros = (num, escala) =>
  Math.round(Number(num) * escala);

// Division de enteros con redondeo media-arriba, como QBO.
const divMediaArriba = (num, den) => {
  const signo = num < 0 ? -1 : 1;
  const n = Math.abs(num);
  const resto = n % den;
  const entero = (n - resto) / den;
  return signo * (resto * 2 >= den ? entero + 1 : entero);
};

// ---------- clases (red de seguridad) ----------
// Solo se usa cuando la linea NO trae class_ref. Desde que el
// nombre del producto llega de verdad, esto por fin corre.
const classNames = {
  '600000000005541105': 'Cocidos y Ahumados',
  '600000000005391641': 'Atun Van Camps',
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
  '600000000005391641': [
    'atun', 'atún', 'tuna',
    'van camps', 'vancamps', 'van camp'
  ],
  '529395': [
    'mantova', 'oil', 'aceite', 'olive', 'oliva',
    'vinegar', 'vinagre', 'balsamic', 'balsamico',
    'extra virgin', 'virgen extra'
  ],
  '600000000005012031': [
    'tomat', 'tomato', 'ketchup', 'catsup',
    'salsa', 'sauce', 'pasta', 'puree', 'pure',
    'puré', 'marinara', 'pomodoro'
  ],
  '600000000005391660': [
    'underwood', 'spread', 'untable', 'pate',
    'paté', 'pâté', 'deviled', 'meat spread'
  ]
};

function detectClassFromProduct(productName) {
  if (!productName) return null;
  const nameLower = productName.toLowerCase();
  const pares = Object.entries(classKeywords);
  for (const [classId, keywords] of pares) {
    for (const keyword of keywords) {
      if (nameLower.includes(keyword)) {
        console.log(
          `Keyword "${keyword}" -> ${classNames[classId]}`
        );
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

// ---------- impuesto ----------
// `tax_rate` es el Id del TaxCode de QBO, no un porcentaje. Un
// pedido nunca mezcla impuestos (el grupo de facturacion ES el
// tax_rate), asi que la primera linea representa a todas.
const taxCodeDe = (l) => {
  const v = l?.tax_rate;
  if (v === null || v === undefined || v === '') return '';
  return String(Number(v));
};

// QBO tiene esta empresa en modo US: el TaxCodeRef DE LINEA solo
// acepta 'TAX' o 'NON'. Mandar el codigo real ahi devuelve
// "Valid line TaxCodes for US should be TAX or NON" (error 6100,
// visto el 2026-08-28). El codigo real va SOLO a nivel de
// transaccion, en TxnTaxDetail.TxnTaxCodeRef.
//
// Y va TAX SIEMPRE. Los tres codigos de OB de esta empresa
// -10 (6%), 13 (Non Tax) y 14 (Local Prod)- estan marcados
// `taxable: true` en QuickBooks; el unico no gravable de verdad
// es el 'NON' generico del sistema, que la app nunca manda. El
// 0% lo define el codigo de la TRANSACCION, no el TAX/NON de la
// linea: la factura 5864 salio al 0% con todas sus lineas TAX.
// Mandar NON sacaba esas ventas del reporte de ventas gravadas
// y habia que marcarlas a mano en CADA factura.
const LINEA_GRAVABLE = 'TAX';

// Porcentaje que corresponde a cada TaxCode. QBO NO calcula el
// impuesto solo con TxnTaxCodeRef: la factura 5848 salio con 0%
// mandando unicamente el codigo. Hay que mandarle TotalTax y
// TaxLine, como hacia el codigo viejo.
const PCT_POR_CODIGO = {
  '10': 6,   // OB 6%
  '11': 9,   // OB 9%
  '13': 0,   // Non Tax (exportacion)
  '14': 0    // OB Non Tax Local Prod
};

// TaxRate de QBO usado para el calculo. RESUELTO 2026-09-08: el
// '25' es en realidad la tasa del 0% local, no la del 6% -- pero
// QuickBooks lo IGNORA y pone la que corresponde al TaxCode. Se
// midio sobre facturas que nadie corrigio a mano: la 5863 salio
// con la tasa 17 (OB 6%) mandandole 25. Las tasas reales son
// 17 = OB 6%, 18 = OB 9%, 19 = Non Tax, 25 = Local Prod.
// Se deja como esta: cambiarlo no cambia nada en la factura.
const TAX_RATE_REF = '25';

const taxCodeFactura = taxCodeDe(body.lines?.[0]);
console.log(`TaxCode de QBO: ${taxCodeFactura || '(ninguno)'}`);

// ---------- moneda ----------
const currencyInput = body.currency || 'XCG';
const currencyDisplayMap = {
  'XCG': 'XCG - Caribbean Guilder',
  'ANG': 'XCG - Caribbean Guilder',
  'USD': 'USD - US Dollar'
};
const currencyDisplay =
  body.currency_display ||
  currencyDisplayMap[currencyInput] ||
  'XCG - Caribbean Guilder';

console.log(`Currency display: ${currencyDisplay}`);

const defaultClass = body.default_class || body.class_ref || null;

// ---------- factura base ----------
const factura = {
  CustomerRef: { value: body.customer_qbo_id },
  DocNumber: nextInvoiceNumber(),
  TxnDate: today(),
  DueDate: today(7),
  SalesTermRef: { value: '46' },
  GlobalTaxCalculation: 'TaxExcluded',

  CustomField: [
    {
      DefinitionId: '1',
      Name: 'Currency',
      Type: 'StringType',
      StringValue: currencyDisplay
    },
    {
      DefinitionId: '2',
      Name: 'Sales Rep',
      Type: 'StringType',
      StringValue: body.sales_rep || 'OF'
    },
    {
      DefinitionId: '3',
      Name: 'Tax ID No.',
      Type: 'StringType',
      StringValue: body.tax_id || ''
    }
  ],

  Line: []
};

// Moneda y tipo de cambio: SOLO si la app los manda. Mientras no
// lo haga, la factura sale como hoy (QBO usa la moneda del
// cliente) y este nodo no cambia nada.
if (body.currency_qbo) {
  factura.CurrencyRef = { value: body.currency_qbo };
  console.log(`CurrencyRef: ${body.currency_qbo}`);
  if (body.exchange_rate) {
    factura.ExchangeRate = Number(body.exchange_rate);
    console.log(`ExchangeRate: ${factura.ExchangeRate}`);
  }
}

console.log(`DocNumber generado: ${factura.DocNumber}`);

// ---------- agrupar lineas ----------
let subtotalCent = 0;
const map = new Map();
for (const l of body.lines ?? []) {
  const key = `${l.product_qbo_id}_${l.unit_price}`;
  const e = map.get(key) ?? { ...l, qtyMil: 0, descriptions: [] };
  e.qtyMil += enEnteros(l.qty, MIL);
  e.descriptions.push(formatDecimal(l.qty));
  map.set(key, e);
}

// ---------- lineas ----------
for (const l of map.values()) {
  // `descripcion` es como la manda la app; el resto son alias.
  const fullProductName =
    l.descripcion ||
    l.product_name ||
    l.name ||
    l.description ||
    '';

  if (!fullProductName) {
    console.log(`Linea sin nombre: ${l.product_qbo_id}`);
  }

  const precioCent = enEnteros(l.unit_price, CENT);
  const montoCent = divMediaArriba(l.qtyMil * precioCent, MIL);

  const lineItem = {
    DetailType: 'SalesItemLineDetail',
    Description: l.descriptions.join('\t'),
    Amount: montoCent / CENT,
    SalesItemLineDetail: {
      ItemRef: {
        value: l.product_qbo_id,
        name: fullProductName
      },
      // Qty y UnitPrice son los que QBO usa para rehacer la
      // cuenta: van con los mismos decimales que el monto.
      Qty: l.qtyMil / MIL,
      UnitPrice: precioCent / CENT
    }
  };

  lineItem.SalesItemLineDetail.TaxCodeRef = {
    value: LINEA_GRAVABLE
  };

  // ---- clase ----
  let lineClass = null;
  if (l.class_ref) {
    lineClass = l.class_ref;
    console.log(`class_ref de la app: ${lineClass}`);
  } else if (l.class_key && classMap[l.class_key]) {
    lineClass = classMap[l.class_key];
  } else {
    lineClass =
      detectClassFromProduct(fullProductName) || defaultClass;
  }

  if (lineClass) {
    lineItem.SalesItemLineDetail.ClassRef = { value: lineClass };
    console.log(`ClassRef ${lineClass} -> ${fullProductName}`);
  } else {
    console.log(`Sin clase: ${fullProductName}`);
  }

  subtotalCent += montoCent;
  factura.Line.push(lineItem);
}

// ---------- impuesto de la transaccion ----------
// Con 0% NO se manda TxnTaxDetail: comprobado en la factura 5848,
// una factura sin TxnTaxDetail sale exenta. Con tasa > 0 hay que
// mandar TotalTax y TaxLine o QBO no calcula nada.
const pct = PCT_POR_CODIGO[taxCodeFactura] ?? 0;

if (pct > 0) {
  const impuesto = divMediaArriba(subtotalCent * pct, 100) / CENT;
  const neto = subtotalCent / CENT;
  factura.TxnTaxDetail = {
    TotalTax: impuesto,
    TxnTaxCodeRef: { value: taxCodeFactura },
    TaxLine: [{
      Amount: impuesto,
      DetailType: 'TaxLineDetail',
      TaxLineDetail: {
        TaxPercent: pct,
        NetAmountTaxable: neto,
        PercentBased: true,
        TaxRateRef: { value: TAX_RATE_REF }
      }
    }]
  };
  console.log(`Impuesto ${pct}% = ${impuesto} sobre ${neto}`);
} else {
  console.log(`Sin impuesto (codigo ${taxCodeFactura})`);
}

console.log('Factura lista:', JSON.stringify(factura));

return [{ json: factura }];
