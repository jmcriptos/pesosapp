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

### 3 y 4. La moneda del cliente está mal en la app — una sola causa

Los clientes de exportación **son USD en QuickBooks**. Verificado en facturas
reales: la 5838 (Caribe Nobo) y la 5821 (Famoso) salen con
`currency_info: { symbol: "$", currency: "USD" }`.

En la app, en cambio, están cargados como **XCG**. De ahí salen dos de las
cuatro correcciones manuales:

- **El campo personalizado «Currency»** dice «XCG - Caribbean Guilder» sobre
  una factura en dólares. n8n lo deriva de `body.currency`, que la app manda
  como `XCG` porque `Cliente.moneda` lo dice.
- **El tipo de cambio** nunca aparece: con `moneda = XCG`,
  `Pedido.tipo_cambio` queda en 1.0 y la app cree que no aplica.

Además, `pedido_a_json` no manda `tipo_cambio` y el nodo de código de n8n dice
`/** SIN CurrencyRef **/` y nunca setea `CurrencyRef` ni `ExchangeRate`.

Dato relevante: QBO reporta la moneda base como **`ANG`** (símbolo ƒ), no
`XCG`. El `CurrencyRef` tiene que usar el código de QBO, no el de la app.

**Consecuencia que nadie había mirado:** como esos pedidos quedan con
`tipo_cambio = 1.0`, el dashboard cuenta las ventas de exportación 1:1 en vez
de multiplicarlas por 1.78. Las está subestimando un 44%.

### 5. `Currency2` no lo escribe nadie

n8n escribe `CustomField` con `DefinitionId` 1 (Currency), 2 (Sales Rep) y 3
(Tax ID). Las facturas tienen además **`Currency2`** (`udcf_1000000003`), una
lista con XCG / USD / ANG que **n8n nunca toca**.

## Exportación

Regla de negocio confirmada por JM (2026-08-28): **moneda USD ⇒ es
exportación ⇒ TaxCode `13` (Non Tax)**, cualquiera sea el producto.

Clientes de exportación (todos de Bonaire):

| Id | Cliente | `moneda` en la app | Acción |
|---|---|---|---|
| 20 | Caribe Nobo | XCG | corregir a USD |
| 21 | Carniceria Latino | XCG | corregir a USD |
| 25 | Famoso | XCG | corregir a USD |
| 133 | Caribe Sup | XCG | corregir a USD |
| 529 | Liza Convenience Store | USD | ya está bien |

Hasta hoy esas facturas salieron con el código del **producto**: `14` para los
cárnicos y `10` (¡6%!) para atunes y aceites. Hay pedidos históricos de Caribe
Nobo y Caribe Sup con productos al 10 desde agosto de 2025 — cada una de esas
facturas se corrigió a mano.

**La corrección de moneda no cambia lo que se le cobra al cliente**: el cliente
en QBO ya es USD, así que la factura ya salía en dólares con esos mismos
números. Lo que cambia es del lado de la app (tipo de cambio y dashboard) y el
campo personalizado.

**Fuera de alcance, en manos de JM:** revisar si las listas de precios de esos
clientes están cargadas en USD o en XCG. Varios productos tienen el mismo
precio que para un cliente local (Aglio Oil 51,00 en ambos), lo que bajo un
cliente USD significa cobrar un 78% de más. Eso condiciona si la corrección del
dashboard queda bien, no si la factura sale bien.

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

**Impuesto de exportación.** El `tax_rate` de cada línea deja de salir
directamente del producto: si el cliente es USD, todas las líneas llevan `13`.
Un solo helper con la regla, para que no se copie en dos lados:

```python
TAX_CODE_EXPORTACION = '13'  # Non Tax — ver tabla de TaxCodes

def _tax_code_de_linea(pedido, producto):
    """Código de impuesto de QBO para una línea.

    La exportación manda sobre el producto: a un cliente en USD se le factura
    exento sea cual sea la mercadería. Sin esto, un atún (código 10, OB 6%)
    se le cobraba con 6% a un cliente de Bonaire.
    """
    if (pedido.cliente.moneda or 'XCG').upper() == 'USD':
        return TAX_CODE_EXPORTACION
    return producto.tax_rate
```

**Corrección de datos en producción.** Los cuatro clientes de exportación
cargados como XCG pasan a USD:

```sql
UPDATE cliente SET moneda = 'USD' WHERE id IN (20, 21, 25, 133);
```

No toca pedidos históricos: `Pedido.tipo_cambio` ya está guardado en cada uno y
se conserva — misma decisión que en `tipo-cambio-expediente` («olvida los
pedidos viejos»). Solo los pedidos nuevos toman 1.78.

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

## Ids de TaxCode (confirmados por JM, 2026-08-28)

| Id | Nombre | Activo |
|---|---|---|
| `10` | OB 6% | Sí |
| `11` | OB 9% | Sí |
| `13` | Non Tax | Sí |
| `14` | OB Non Tax Local Prod | Sí |
| `12` | OB 6 - Inactive | **No** |
| `TAX` / `NON` / `CustomSalesTax` | genéricos del sistema | Sí |

`Producto.tax_rate` guarda exactamente uno de estos Ids, así que **la app ya
manda el valor correcto** y no hace falta ningún campo nuevo para el impuesto:
alcanza con que n8n lo use como código en vez de como porcentaje.

Propiedad útil que sale de esto: como el código viaja tal cual, dar de alta un
producto al **9% (`11`)** o exento (`13`) no requiere tocar código en ningún
lado — solo cargar ese valor en el producto. Hoy solo se usan `10` y `14`.

El `TaxCodeRef: 'TAX'` que n8n pone en cada línea se conserva: marca la línea
como gravable, y la tasa la define el `TxnTaxCodeRef` de la transacción junto
con `GlobalTaxCalculation: 'TaxExcluded'`.

## Pendiente

1. **`Currency2` por API.** Los campos personalizados nuevos de QBO (`udcf_*`)
   no siempre son escribibles por el array `CustomField` de la API v3, que
   históricamente solo admite los tres legacy (DefinitionId 1–3). Si no se
   puede, ese campo sigue cargándose a mano y hay que decirlo, no simularlo.
   Es el único de los cuatro que puede quedar sin resolver.

2. **El paso de «grupo de facturación» para clientes de exportación.** Pregunta
   abierta, no decidida: el grupo se deriva del `tax_rate` del **producto** y
   existe para impedir que un pedido mezcle impuestos. Para un cliente USD todo
   va al `13`, así que la restricción deja de tener sentido — hoy Caribe Nobo
   no puede pedir atún (10) y jamón (14) en el mismo pedido aunque los dos se
   facturen exentos.

   **No se toca en esta implementación.** Es una limitación que ya existe, no
   una regresión, y el paso 2 se hizo obligatorio a propósito hace poco
   («el grupo de facturación se elige siempre»). Deshacerlo de costado sería
   peor que dejarlo. Queda anotado para decidir aparte.

## Fuera de alcance

- La carrera del `DocNumber` (n8n consulta las últimas 50 facturas y suma 1).
  Decisión ya tomada por JM: se conserva — ver `docnumber-carrera-decision`.
- `TxnDate` usa `today()` en vez de la fecha del pedido, y `DueDate` es
  `today+7` fijo. No está en la lista de correcciones de JM.
- Clasificar los 64 productos existentes. Es carga de datos, no código.

## Verificación

- Tests de `pedido_a_json`: los campos nuevos con sus valores, y que
  `class_ref` se omita cuando el producto no tiene clase.
- Test del impuesto de exportación: un cliente USD factura **todas** sus líneas
  con `13`, incluso las de un producto con `tax_rate = 10`; un cliente XCG
  conserva el código del producto.
- Test de la pantalla de productos: la clase se guarda y se relee.
- Test de `_validar_datos_facturacion`: avisa por producto sin clase y **no**
  bloquea la facturación.
- Prueba de punta a punta: un pedido de un cliente XCG y otro de un cliente
  USD, verificando en QBO la clase por línea, la tasa, la moneda y el tipo de
  cambio **sin tocar nada a mano**.

## Orden de despliegue

1. **n8n** (JM, ya entregado): arregla el impuesto por sí solo. Los campos de
   moneda quedan dormidos hasta que la app los mande.
2. **App**: columna, pantalla, payload y el helper de impuesto de exportación.
   Es aditivo: con el n8n viejo no empeora nada.
3. **Datos**: el `UPDATE cliente` de moneda. Es el que activa el impuesto de
   exportación, el tipo de cambio y el campo «Currency».
4. **Clasificar los 64 productos** (JM), con las clases presugeridas por las
   palabras clave del workflow.

## Riesgos

- **El cambio de n8n y el de la app tienen que ir juntos.** El payload nuevo es
  retrocompatible (solo agrega), así que se puede desplegar la app primero; el
  impuesto y el tipo de cambio no mejoran hasta que n8n se actualice.
- **El impuesto se arregla solo del lado de n8n.** Es el único de los cuatro
  que no necesita nada de la app: si se actualiza n8n y nada más, la tasa ya
  sale bien. Conviene hacerlo primero por ser el de mayor impacto y menor
  riesgo.
- Los 64 productos arrancan sin clase. Hasta que se carguen, las facturas
  salen igual que hoy en ese aspecto (sin `ClassRef`), no peor.
