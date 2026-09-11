# Workflow de n8n — facturación a QuickBooks

Dos nodos del workflow viven acá, versionados junto al payload que los
alimenta (`pedido_a_json` en `app.py`) y, sobre todo, para poder copiarlos
desde un editor:

| Archivo | Nodo de n8n |
|---|---|
| `generar-numero-factura.js` | **Code** `Generar Numero Factura` |
| `http-facturar-qbo-body.txt` | body del **HTTP Request** `HTTP Facturar QBO` |

> **No lo copies desde el chat ni desde markdown renderizado.** El 2026-08-28
> se pegó desde un terminal y **todas las líneas de más de ~78 caracteres
> llegaron cortadas** — el bloque se renderizó con ancho fijo y el copiado se
> llevó solo lo visible. n8n respondió `Invalid or unexpected token`, y como
> el nodo tiene su salida de error desconectada, el síntoma que llegó a la app
> fue un genérico «Error temporal en QuickBooks».
>
> Por eso `generar-numero-factura.js` **no pasa de 72 columnas**: aunque se
> copie mal, sobrevive. El body del HTTP no puede: cuatro de sus líneas son
> expresiones `{{ }}` que van enteras o no van, y la más larga llega a 98
> caracteres. Ese archivo **solo** se copia desde un editor.

## Cómo actualizarlo

1. Abrir el archivo en un editor y copiar todo.
2. En n8n, reemplazar el contenido del nodo que le corresponde —el Code, o
   el campo **Body** del HTTP Request.
3. Guardar y activar.

Nada se despliega solo: este repo es la fuente de verdad, pero el que factura
es lo que esté pegado en n8n. Si los dos archivos no están en n8n tal cual
están acá, el workflow corre otra cosa.

## Cómo verificarlo antes de pegar

```sh
node --check docs/n8n/generar-numero-factura.js
node docs/n8n/test-nodo-factura.js
```

El segundo corre el nodo entero contra el pedido 1334 y comprueba las cosas
que ya salieron mal: que los montos de línea sean los que QuickBooks vuelve a
calcular, que cada línea vaya como gravable, que el `Currency2` lleve el id de
la opción, y que el body del HTTP nombre todos los campos que el Code node
emite.

## Trampa del workflow

`Get Invoice Number`, `Get Credit Memo Number` y `Generar Numero Factura`
tienen `onError: continueErrorOutput` y **esa segunda salida no está conectada
a nada**. Cualquier error intermedio se traga: el workflow termina sin ítems y
el webhook responde `HTTP 500 — "No item to return was found"`, sin decir qué
falló. Conviene conectar esas salidas a un nodo que devuelva el error, o
quitarles el `onError` para que n8n falle con el mensaje real.

## La trampa del body del HTTP

El nodo `HTTP Facturar QBO` **no manda el ítem entero**: su body es un JSON
escrito campo por campo, y solo viaja lo que esté nombrado ahí. Todo lo que el
Code node calcule y el body no liste, se pierde en silencio.

Así se rompió el impuesto: el body listaba nueve campos y `TxnTaxDetail` no
era uno de ellos. Las líneas llegaban marcadas `TAX` y **sin código de
transacción**, así que la tasa la resolvía QuickBooks por su cuenta — el
default del cliente— y daba igual qué código mandara la app. Faltaban también
`GlobalTaxCalculation` y `ExchangeRate`.

> **Ojo con lo que esto implica hacia atrás.** Mientras el body fue ese, las
> facturas no llevaron `TxnTaxDetail`. Cualquier conclusión sacada comparando
> facturas de ese período —incluida la de la `5863` contra la `5867` que
> justificó el `TaxRateRef` fijo— se sacó sobre payloads a los que el bloque
> de impuesto nunca les llegó.

`node docs/n8n/test-nodo-factura.js` lo comprueba: recorre los campos que el
Code node emite y falla si el body no nombra alguno. Al agregar un campo
nuevo al Code node hay que agregarlo también al body, o el test avisa.

## Contrato con la app

El payload lo arma `pedido_a_json`. Campos que el nodo consume:

| Campo | Uso |
|---|---|
| `customer_qbo_id` | `CustomerRef` |
| `currency_qbo` | `CurrencyRef` (QBO llama **ANG** a la moneda local) |
| `currency_display` | CustomField «Currency» (legacy, `DefinitionId 1`) |
| `currency` | CustomField «Currency2» (`DefinitionId 1000000003`) — ver abajo |
| `exchange_rate` | `ExchangeRate` |
| `lines[].product_qbo_id` | `ItemRef.value` |
| `lines[].descripcion` | `ItemRef.name` (n8n también acepta `product_name`) |
| `lines[].class_ref` | `ClassRef` — gana sobre la detección por palabras clave |
| `lines[].tax_rate` | **Id de TaxCode de QBO**, no un porcentaje. Va a `TxnTaxDetail.TxnTaxCodeRef` (transacción). En la **línea** se traduce a `TAX`/`NON` — ver abajo |
| `lines[].qty` / `unit_price` | `Qty` / `UnitPrice`; se agrupa por `(product_qbo_id, unit_price)` |

Diseño completo:
`docs/superpowers/specs/2026-08-28-factura-qbo-sin-correcciones-design.md`


## Los DOS campos de moneda

La factura tiene dos, y no son dos vistas del mismo:

| Campo | `DefinitionId` | Qué guarda | Se ve en QBO |
|---|---|---|---|
| `Currency` | `1` (legacy) | el texto: `USD - US Dollar` | **no** |
| `Currency2` | `1000000003` | el **id de la opción**: `1`/`2`/`3` | sí |

`Currency2` es una **lista**, así que guarda el id, no el texto:
`1` = XCG, `2` = USD, `3` = ANG (medido el 2026-09-08 sobre las facturas
5864 y 5856). Nunca se manda el `3`: QuickBooks llama ANG a la moneda local,
pero el desplegable dice XCG, que es como la llama la empresa.

Que sean dos campos se comprobó viéndolos en desacuerdo: la 5856 tenía el
legacy en `USD - US Dollar` y el `Currency2` en `1` (XCG) **al mismo
tiempo**, y salió por email al cliente así. Desde el 2026-08-28 se llenaba
bien el legacy —el que la pantalla no muestra— y por eso la moneda se seguía
viendo mal.

> **La URL importa.** Los campos personalizados nuevos (`udcf_*`) sólo
> viajan si el nodo HTTP que crea la factura lleva
> `?minorversion=75&include=enhancedAllCustomFields`. Sin eso QuickBooks
> ignora el `CustomField` con `DefinitionId 1000000003` sin avisar.
>
> Con ese parámetro, **la respuesta también cambia de forma**: devuelve
> `Currency2` y `Sales Rep` con ids nuevos, y no devuelve `Currency` ni
> `Tax ID No.`. La app sólo lee `Invoice.Id` y `DocNumber` de esa respuesta
> (`_extraer_invoice_id`), así que no la afecta.

## La trampa del medio centavo

QuickBooks **revalida** cada línea: `Amount` tiene que ser
`UnitPrice * Qty` redondeado a centavos **media-arriba**. Si no
coincide devuelve:

```
6070 — Amount is not equal to UnitPrice * Qty.
       Supplied value: 1,861.07
```

Los pesos traen 3 decimales y los precios 2, así que el producto
cae bastante seguido justo en el medio centavo: 128.350 kg a
14.50 son **1861.075 exactos**. En coma flotante 128.35 se guarda
como 128.34999999999999432, el producto da 1861.0749999999998 y
el redondeo lo baja a 1861.07 — QBO esperaba 1861.08. Le pasó al
pedido 1334 el 2026-09-08. `Number.EPSILON` no salva: es 25 veces
más chico que el error que ya trae la suma de ocho pesos.

Por eso el nodo hace la cuenta **en enteros** —el peso en
milésimas, el precio en centavos— y manda `Qty` y `UnitPrice` con
esos mismos decimales, para que QBO rehaga exactamente la misma
cuenta. El `amount` que manda la app no se usa: n8n agrupa las
líneas por `(product_qbo_id, unit_price)` y el monto tiene que
salir de la cantidad ya sumada.

## La trampa del impuesto (modo US)

Esta empresa está configurada en QuickBooks en **modo US**. Eso significa que
`Line.SalesItemLineDetail.TaxCodeRef` **solo acepta `TAX` o `NON`**. Mandarle
el código real devuelve:

```
6100 — Invalid Line TaxCode in the request
Valid line TaxCodes for US should be TAX or NON. Supplied value: 10
```

El código real (10 / 13 / 14) va **únicamente** en
`TxnTaxDetail.TxnTaxCodeRef`. La línea va **`TAX` siempre**:

| `tax_rate` de la app | Línea | Transacción | Resultado |
|---|---|---|---|
| `10` — OB 6% | `TAX` | `10` | 6% |
| `13` — Non Tax (exportación) | `TAX` | `13` | 0% |
| `14` — OB Non Tax Local Prod | `TAX` | `14` | 0% |

**No confundir «exento» con «no gravable».** Los tres códigos de OB de esta
empresa están marcados `taxable: true` en QuickBooks; el único no gravable de
verdad es el `NON` genérico del sistema, que la app nunca manda. El 0% lo
define el código de la **transacción**, no el `TAX`/`NON` de la línea — la
factura 5864 salió al 0% con todas sus líneas en `TAX`.

Entre el 2026-08-28 y el 2026-09-08 el nodo mandó `NON` en las líneas de
código 13 y 14, con el razonamiento —falso— de que si no, «un producto exento
no tiene forma de salir al 0%». Una línea `NON` se cae del reporte de ventas
gravadas, así que hubo que marcarlas a mano en **cada** factura de Mr Raucher
y de exportación.

### QBO no calcula el impuesto solo

Mandar únicamente `TxnTaxCodeRef` **no alcanza**: la factura 5848 salió con 0%
llevando el código 10. Hay que mandarle `TotalTax` y `TaxLine` calculados,
como hacía el código viejo — pero con el porcentaje que de verdad corresponde
al código, no interpretando el código como porcentaje:

| TaxCode | Porcentaje |
|---|---|
| `10` | 6% |
| `11` | 9% |
| `13` | 0% |
| `14` | 0% |

**El bloque va SIEMPRE, también al 0%.** Omitirlo no deja la factura «exenta
y limpia»: la deja **sin código**. La 5865 salió con `TxnTaxDetail:
{ TotalTax: 0 }` y nada más — una venta sin clasificar en el reporte de OB.
Hasta el 2026-09-08 no se notaba porque al marcar las líneas como gravables a
mano, QuickBooks recalculaba y le estampaba el código; sin esa edición, la
factura queda como la mandamos.

### El `TaxRateRef` va siempre en `25`, y está mal a propósito

El `TaxRateRef` es otra entidad que el `TaxCode`. Las tasas reales de esta
empresa son `17` = OB 6%, `18` = OB 9%, `19` = Non Tax, `25` = OB Non Tax
Local Prod. El nodo manda **`25` siempre**, sea cual sea el código.

Suena a bug y no lo es: QuickBooks **no acepta** la tasa que le mandamos,
recalcula la que corresponde al `TxnTaxCodeRef` y guarda esa. La 5863 se
mandó con `25` y quedó guardada con `17`, al 6% correcto.

> **No lo "arregles".** El 2026-09-08 se cambió a la tasa que corresponde a
> cada código, razonando que QBO la reescribe igual y que así el payload
> queda idéntico a lo guardado. La primera factura al 6% emitida con ese
> cambio —la **5867**— salió al **0%** y hubo que ajustarla a mano.
> Mandarle la `17` no le confirma el 6%: le rompe el cálculo. El `25`
> funciona *porque* obliga a QuickBooks a resolver la tasa desde el código.

> **Resuelto (2026-09-08):** el `TaxRateRef` fijo en `'25'` está mal —el 25 es
> la tasa del 0% local, no la del 6%— pero **QuickBooks lo ignora** y pone la
> que corresponde al `TaxCode`. Medido sobre facturas que nadie tocó a mano:
> la 5863 se mandó con `25` y quedó guardada con `17`. Las tasas reales son
> `17` = OB 6%, `18` = OB 9%, `19` = Non Tax, `25` = OB Non Tax Local Prod.
> Se deja como está: cambiarlo no cambia nada en la factura.


# Workflow aparte: tipo de cambio USD diario

`tipo-cambio-diario.json` es un workflow completo, listo para importar
(**Import from File**, o pegarlo en el canvas). No toca el de facturación.

## Por qué existe

La factura manda `ExchangeRate: 1.78` y **QuickBooks lo descarta**: usa la
tasa que se descarga sola cada madrugada. El 2026-09-09 tenía `1.802075`
(actualizada 01:11) y la factura 5868 salió con esa. Las cinco facturas en
USD que existían hasta ese día estaban las cinco corregidas a mano.

La tasa se fija con otra API: `POST /v3/company/<realm>/exchangerate`.

## Qué hace

| Nodo | Qué hace |
|---|---|
| `Todos los dias 05:00` | Dispara una vez por día |
| `Fechas UTC a fijar` | Emite **dos** fechas: hoy y mañana (UTC) |
| `Leer tasa actual` | `GET` de la tasa de esa fecha — trae el `SyncToken` |
| `Fijar USD en 1.78` | `POST` con `Rate: 1.78` y el `SyncToken` si lo hay |

**Hoy y mañana, no sólo hoy.** El `TxnDate` de la factura sale de
`new Date().toISOString()`, o sea la fecha **UTC**. Facturando de tarde en
Curaçao (UTC−4) ya es el día siguiente en UTC: la 5865 se emitió a las 21:45
del 8 de septiembre y salió con `TxnDate 2026-09-09`. Fijando sólo la de hoy,
las facturas de la tarde saldrían con la tasa de QuickBooks.

**El `SyncToken` sale del GET.** Una fecha nueva no lo trae y el `POST` va sin
él; una que ya se fijó sí, y entonces hace falta o QBO rechaza la escritura
por objeto desactualizado. Cada fecha se escribe dos veces (como «mañana» un
día y como «hoy» al siguiente), así que el caso se da todos los días.

## Por qué va aparte y no dentro de la facturación

El flujo de facturación funciona, y meter un nodo en el medio cambia lo que le
llega a `HTTP Facturar QBO`. La tasa no depende del pedido: es política de la
empresa, 1,78 todos los días. Si el job falla, la factura sale con la tasa de
QuickBooks y se corrige a mano — que es el peor caso de siempre, no uno nuevo.
