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
```

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
| `lines[].tax_rate` | **Id de TaxCode de QBO**, no un porcentaje: `TaxCodeRef` de la línea y `TxnTaxCodeRef` de la transacción |
| `lines[].qty` / `unit_price` | `Qty` / `UnitPrice`; se agrupa por `(product_qbo_id, unit_price)` |

Diseño completo:
`docs/superpowers/specs/2026-08-28-factura-qbo-sin-correcciones-design.md`
