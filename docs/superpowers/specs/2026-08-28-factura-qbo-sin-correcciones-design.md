# Facturar sin correcciones manuales en QuickBooks

**Fecha:** 2026-08-28
**Estado:** diseño aprobado, pendiente de plan de implementación

## Problema

Cada factura que sale de la app hay que corregirla a mano en QuickBooks. JM
enumeró cuatro datos:

1. La moneda en el campo personalizado.
2. Las clases de los productos.
3. La tasa de impuesto.
4. El tipo de cambio, cuando aplica.

Los cuatro tienen la misma forma: **n8n infiere o defaultea datos que la app
conoce pero no manda**, o los interpreta con un significado distinto del que
la app les da.

## Arquitectura actual

```
app (pedido_a_json)  ──POST JSON──▶  n8n webhook  ──▶  Code node  ──▶  HTTP POST /invoice  ──▶  QBO
```

El nodo de código (`Generar Numero Factura`) traduce el JSON de la app al
formato de la API v3 de QuickBooks. Ese workflow **no vive en este repo**; lo
edita JM.

Payload actual (`pedido_a_json`, `app.py`):

```json
{
  "order_id": 1305,
  "order_date": "2026-08-28T16:02:43",
  "customer_qbo_id": "24",
  "currency": "XCG",
  "notes": null,
  "lines": [
    {
      "product_qbo_id": "1434",
      "descripcion": "Cooked Shoulder 500 gr",
      "qty": 0.25,
      "unit_price": 270.0,
      "amount": 67.5,
      "tax_rate": 14
    }
  ],
  "total": 507.25
}
```

## Causas raíz

### 1. Las clases nunca se asignan (100% de las facturas)

n8n resuelve el nombre del producto así:

```js
let productName = l.product_name || l.name || l.description || '';
```

El payload manda ese dato como **`descripcion`**, en español. Ninguna de las
tres claves existe, así que `productName` queda vacío. A partir de ahí:

- `detectClassFromProduct('')` sale en su primera línea (`if (!productName) return null`).
- `getProductName(id)` busca datos de `Item` en `$input.all()`, donde solo
  llegan las consultas de DocNumber. Devuelve `''`.
- El último fallback evalúa `''.includes('smoked')` → `false`.

`ClassRef` **no se agrega nunca**. El mismo desajuste deja `ItemRef.name`
vacío (inofensivo: QBO resuelve el ítem por id, pero conviene arreglarlo).

**n8n ya honra `class_ref` por línea con máxima prioridad**, así que este
punto se resuelve mandándolo desde la app sin tocar n8n.

### 2. La app y n8n dan a `tax_rate` significados distintos

`Producto.tax_rate` guarda un **código de QuickBooks** (10 = OB 6%, 14 = OB 0%),
no un porcentaje — está documentado en `app.py:6123`. n8n lo trata como
porcentaje:

```js
const txnTaxCodeMap = { '0': '14', '6': '14', '9': '14' };  // no contempla 10 ni 14
const taxRateMap    = { '0': '25', '6': '25', '9': '25' };
const txnTaxCode = txnTaxCodeMap[firstLineRate.toString()] || '14';
const taxRateRef = taxRateMap[firstLineRate.toString()]   || '25';
const taxAmount  = (subtotal * firstLineRate) / 100;
```

Los dos valores que manda la app caen al **mismo fallback**
(`TxnTaxCodeRef: '14'`, `TaxRateRef: '25'`) y además se calcula un `TotalTax`
sin sentido (10% o 14%). Evidencia en producción:

| Factura | Pedido | `tax_rate` de la app | Impuesto en QBO |
|---|---|---|---|
| 5842 (47949) | 1299 | 10 (= 6%) | 84,38 sobre 1.406,40 = **6% ✓** |
| 5847 (47954) | 1305 | 14 (= 0%) | 0 — probablemente ya corregido a mano |

Ese es el «a veces sale bien»: cuando corresponde 6% coincide con el fallback;
cuando corresponde 0%, no.

### 3. El tipo de cambio no sale de la app ni se usa en n8n

`Pedido.tipo_cambio` existe (1.0 para XCG, 1.78 para USD) y **no está en el
payload**. El nodo de código dice `/** SIN CurrencyRef **/` y nunca setea
`CurrencyRef` ni `ExchangeRate`; el condicional del nodo HTTP siempre resuelve
a vacío. La moneda y la tasa las decide QBO por la ficha del cliente.

Dato relevante: QBO reporta la moneda base como **`ANG`** (símbolo ƒ), no
`XCG`. El `CurrencyRef` tiene que usar el código de QBO, no el de la app.

### 4. n8n solo carga tres de los cuatro campos personalizados

Escribe `CustomField` con `DefinitionId` 1 (Currency), 2 (Sales Rep) y 3
(Tax ID). Las facturas tienen además **`Currency2`** (`udcf_1000000003`), una
lista con XCG / USD / ANG que **n8n nunca toca**. Por eso a veces está vacío
(factura 5835) y a veces cargado (las ya corregidas).

## Diseño

Principio: **el payload lleva explícito todo lo que la factura necesita; n8n
deja de inferir**.

### Payload nuevo

Se agregan campos; no se quita ni se renombra ninguno, así que un n8n sin
actualizar sigue funcionando igual que hoy.

```json
{
  "order_id": 1305,
  "order_date": "2026-08-28T16:02:43",
  "customer_qbo_id": "24",
  "currency": "XCG",
  "currency_qbo": "ANG",                       // NUEVO: código de moneda de QBO
  "currency_display": "XCG - Caribbean Guilder", // NUEVO: para los CustomField
  "exchange_rate": 1.0,                        // NUEVO: Pedido.tipo_cambio
  "notes": null,
  "lines": [
    {
      "product_qbo_id": "1434",
      "descripcion": "Cooked Shoulder 500 gr",
      "product_name": "Cooked Shoulder 500 gr", // NUEVO: alias que n8n ya busca
      "class_ref": "600000000005541105",        // NUEVO: Producto.clase_qbo
      "qty": 0.25,
      "unit_price": 270.0,
      "amount": 67.5,
      "tax_rate": 14
    }
  ],
  "total": 507.25
}
```

`product_name` se **agrega** en vez de renombrar `descripcion`: el agrupado de
n8n usa `product_qbo_id` + `unit_price`, así que no lo afecta, y evita romper
cualquier otro consumidor.

### Cambios en la app

**Modelo.** `Producto.clase_qbo = db.Column(db.String(30), nullable=True)`:
guarda el Id de Class de QuickBooks. Migración a mano en prod **antes** del
push (no hay release phase — ver `migraciones-prod-alembic-desacoplado`):

```sql
ALTER TABLE producto ADD COLUMN clase_qbo VARCHAR(30);
```

**Catálogo de clases.** Constante en `app.py` con las cinco clases que ya usa
el workflow de n8n:

| Id | Nombre |
|---|---|
| `600000000005541105` | Cocidos y Ahumados |
| `600000000005391641` | Atún Van Camps |
| `529395` | Mantova |
| `600000000005012031` | Tomate |
| `600000000005391660` | Untables Underwood |

Agregar una clase nueva en QBO exige agregar una línea acá. Es aceptable para
cinco valores estables; una tabla propia sería sobreingeniería (YAGNI).

**Pantalla de productos.** Un `<select>` «Clase (QuickBooks)» junto al QBO ID,
en el alta y en la edición. Opcional: un producto sin clase se factura como
hoy (sin `ClassRef`), no se bloquea nada.

**Payload.** `pedido_a_json` agrega los campos de arriba. `class_ref` se omite
de la línea cuando el producto no tiene clase, para no mandar `null`.

**Validación.** `_validar_datos_facturacion` suma un aviso —no un error— por
cada producto sin clase: «X: sin clase de QuickBooks; la línea saldrá sin
clasificar». Se muestra igual que los errores actuales pero no impide
facturar, porque hoy ninguna línea tiene clase y bloquear dejaría la app
inservible hasta clasificar los 64 productos.

### Cambios en n8n

**Clases: ninguno.** El código ya usa `l.class_ref` con máxima prioridad. La
detección por keywords queda como red de seguridad y ahora además funciona,
porque `product_name` llega con valor.

**Impuesto.** Borrar `txnTaxCodeMap`, `taxRateMap` y el cálculo de `taxAmount`.
Usar el código que manda la app y dejar que QBO calcule:

```js
const taxCode = String(body.lines?.[0]?.tax_rate ?? '');
factura.TxnTaxDetail = { TxnTaxCodeRef: { value: taxCode } };
```

Tomar la primera línea es correcto y no una simplificación: **un pedido nunca
mezcla impuestos** — el grupo de facturación ES el `tax_rate`, y el paso 2 del
formulario impide armar un pedido con dos grupos (ver
`grupos-facturacion-pedido`). Todas las líneas traen el mismo valor.

Sin `TotalTax` ni `TaxLine` calculados a mano: con
`GlobalTaxCalculation: 'TaxExcluded'` y el código correcto, QBO aplica la tasa.

**Tipo de cambio.** En el nodo de código:

```js
if (body.currency_qbo) {
  factura.CurrencyRef = { value: body.currency_qbo };
  if (body.exchange_rate) factura.ExchangeRate = Number(body.exchange_rate);
}
```

El nodo HTTP ya tiene el condicional de `CurrencyRef`; hay que agregarle
`ExchangeRate`.

**Moneda del campo personalizado.** Usar `body.currency_display` en el
`CustomField` de `DefinitionId: '1'` en vez del mapa local, y agregar el
`Currency2` — **sujeto a la verificación de abajo**.

## Pendiente de confirmar antes de implementar

1. **Ids de TaxCode.** Hay que confirmar en QuickBooks que `10` y `14` son los
   Ids reales de los TaxCode de 6% y 0%. El diseño del impuesto depende de
   esto; si no lo son, la app tiene que mandar un campo `tax_code_qbo` aparte.
2. **`Currency2` por API.** Los campos personalizados nuevos de QBO (`udcf_*`)
   no siempre son escribibles por el array `CustomField` de la API v3, que
   históricamente solo admite los tres legacy (DefinitionId 1–3). Si no se
   puede, ese campo sigue cargándose a mano y hay que decirlo, no simularlo.

## Fuera de alcance

- La carrera del `DocNumber` (n8n consulta las últimas 50 facturas y suma 1).
  Decisión ya tomada por JM: se conserva — ver `docnumber-carrera-decision`.
- `TxnDate` usa `today()` en vez de la fecha del pedido, y `DueDate` es
  `today+7` fijo. No está en la lista de correcciones de JM.
- Clasificar los 64 productos existentes. Es carga de datos, no código.

## Verificación

- Tests de `pedido_a_json`: los campos nuevos con sus valores, y que
  `class_ref` se omita cuando el producto no tiene clase.
- Test de la pantalla de productos: la clase se guarda y se relee.
- Test de `_validar_datos_facturacion`: avisa por producto sin clase y **no**
  bloquea la facturación.
- Prueba de punta a punta: un pedido de un cliente XCG y otro de un cliente
  USD, verificando en QBO la clase por línea, la tasa, la moneda y el tipo de
  cambio **sin tocar nada a mano**.

## Riesgos

- **El cambio de n8n y el de la app tienen que ir juntos.** El payload nuevo es
  retrocompatible (solo agrega), así que se puede desplegar la app primero; el
  impuesto y el tipo de cambio no mejoran hasta que n8n se actualice.
- Si los ids de TaxCode no son 10/14, el arreglo del impuesto queda a medias y
  hay que rediseñar esa parte.
