# Workflow de n8n — facturación a QuickBooks

`generar-numero-factura.js` es el contenido del nodo **Code** llamado
`Generar Numero Factura`. Vive acá para que quede versionado junto al payload
que lo alimenta (`pedido_a_json` en `app.py`) y, sobre todo, para poder
copiarlo desde un editor.

> **No lo copies desde el chat ni desde markdown renderizado.** El 2026-08-28
> se pegó desde un terminal y **todas las líneas de más de ~78 caracteres
> llegaron cortadas** — el bloque se renderizó con ancho fijo y el copiado se
> llevó solo lo visible. n8n respondió `Invalid or unexpected token`, y como
> el nodo tiene su salida de error desconectada, el síntoma que llegó a la app
> fue un genérico «Error temporal en QuickBooks».
>
> Por eso el archivo **no pasa de 72 columnas**: aunque se copie mal, sobrevive.

## Cómo actualizarlo

1. Abrir `generar-numero-factura.js` en un editor y copiar todo.
2. En n8n, nodo `Generar Numero Factura`, reemplazar el contenido.
3. Guardar y activar.

## Cómo verificarlo antes de pegar

```sh
node --check docs/n8n/generar-numero-factura.js
node docs/n8n/test-nodo-factura.js
```

El segundo corre el nodo entero contra el pedido 1334 y comprueba las
dos cosas que ya salieron mal: que los montos de línea sean los que
QuickBooks vuelve a calcular, y que cada línea vaya como gravable.

## Trampa del workflow

`Get Invoice Number`, `Get Credit Memo Number` y `Generar Numero Factura`
tienen `onError: continueErrorOutput` y **esa segunda salida no está conectada
a nada**. Cualquier error intermedio se traga: el workflow termina sin ítems y
el webhook responde `HTTP 500 — "No item to return was found"`, sin decir qué
falló. Conviene conectar esas salidas a un nodo que devuelva el error, o
quitarles el `onError` para que n8n falle con el mensaje real.

## Contrato con la app

El payload lo arma `pedido_a_json`. Campos que el nodo consume:

| Campo | Uso |
|---|---|
| `customer_qbo_id` | `CustomerRef` |
| `currency_qbo` | `CurrencyRef` (QBO llama **ANG** a la moneda local) |
| `currency_display` | CustomField «Currency» |
| `exchange_rate` | `ExchangeRate` |
| `lines[].product_qbo_id` | `ItemRef.value` |
| `lines[].descripcion` | `ItemRef.name` (n8n también acepta `product_name`) |
| `lines[].class_ref` | `ClassRef` — gana sobre la detección por palabras clave |
| `lines[].tax_rate` | **Id de TaxCode de QBO**, no un porcentaje. Va a `TxnTaxDetail.TxnTaxCodeRef` (transacción). En la **línea** se traduce a `TAX`/`NON` — ver abajo |
| `lines[].qty` / `unit_price` | `Qty` / `UnitPrice`; se agrupa por `(product_qbo_id, unit_price)` |

Diseño completo:
`docs/superpowers/specs/2026-08-28-factura-qbo-sin-correcciones-design.md`


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

Con 0% **no se manda `TxnTaxDetail`** en absoluto: comprobado en la 5848, una
factura sin ese bloque sale exenta.

> **Resuelto (2026-09-08):** el `TaxRateRef` fijo en `'25'` está mal —el 25 es
> la tasa del 0% local, no la del 6%— pero **QuickBooks lo ignora** y pone la
> que corresponde al `TaxCode`. Medido sobre facturas que nadie tocó a mano:
> la 5863 se mandó con `25` y quedó guardada con `17`. Las tasas reales son
> `17` = OB 6%, `18` = OB 9%, `19` = Non Tax, `25` = OB Non Tax Local Prod.
> Se deja como está: cambiarlo no cambia nada en la factura.
