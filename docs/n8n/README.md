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
node docs/n8n/test-monto-linea.js
```

El segundo corre el nodo entero contra el pedido 1334 y comprueba
que los montos de línea son los que QuickBooks vuelve a calcular.

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
`TxnTaxDetail.TxnTaxCodeRef`. La línea se marca:

| `tax_rate` de la app | Línea | Transacción |
|---|---|---|
| `10` — OB 6% | `TAX` | `10` |
| `13` — Non Tax (exportación) | `NON` | `13` |
| `14` — OB Non Tax Local Prod | `NON` | `14` |

El código viejo mandaba siempre `TAX` en la línea, así que un producto exento
no tenía forma de salir al 0% y había que corregir la factura a mano.

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

> **Pendiente de confirmar:** el `TaxRateRef` está fijo en `'25'`, que es el
> que traía el código viejo y con el que la factura 5842 salió al 6%. No está
> verificado contra la lista de TaxRate de QuickBooks (que es una entidad
> distinta de los TaxCode). Si algún día se factura al 9%, casi seguro
> necesita otro `TaxRateRef`.
