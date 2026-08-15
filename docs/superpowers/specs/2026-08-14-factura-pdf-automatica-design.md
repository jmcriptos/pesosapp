# Factura PDF bajo demanda — diseño

Fecha: 2026-08-14

## Problema

Al facturar un pedido, la factura se crea en QuickBooks pero no queda ningún
documento para el cliente. Hoy hay que correr a mano un workflow de n8n que
genera un HTML y lo sube a Google Drive. El cliente necesita un PDF: se lo
mandan por WhatsApp y también se lo entregan impreso con la mercancía.

La generación de PDF que había en n8n usaba PDF Generator API, un servicio de
pago. El objetivo es automatizar el proceso sin costos nuevos.

## La restricción que define el diseño

**La lista de precios de la app a veces está desactualizada, y entonces la
factura se corrige a mano en QuickBooks antes de entregarla.** Pasó el
2026-08-14 con los pedidos 1264 y 1267 (Smoked Turkey Breast 24,80 → 34;
Smoked Turkey Ham 0 → 18,65).

Eso descarta guardar un snapshot de la factura al momento de facturar: sería
anterior a la corrección y el PDF saldría con los precios viejos. También
descarta generar el PDF automáticamente al facturar, por la misma razón.

El PDF se genera **cuando el usuario lo pide**, consultando la factura vigente
en QuickBooks. Así refleja lo que hay en QBO, se haya corregido o no.

## Contexto que habilita la solución

1. **La app ya genera PDFs con reportlab** (etiquetas y reportes de
   importación, `app.py`). No hay dependencia nueva.
2. **La app ya guarda `invoice_id_qbo`** desde el 2026-08-14 (release v838),
   que es lo que permite volver a pedirle la factura a QuickBooks.
3. **n8n ya tiene credenciales de QuickBooks y de Google Drive.** La app no
   necesita ninguna de las dos: habla con n8n, como ya hace para facturar.

`Cliente` no tiene dirección ni CRIB; esos datos solo existen en QBO y llegan
en el objeto `Invoice` (`BillAddr`, con el CRIB en `CountrySubDivisionCode`).

## Decisiones

**Redibujar la factura en reportlab, no replicar el HTML.** El HTML actual usa
CSS Grid y flexbox, que solo un navegador real renderiza bien. Los
renderizadores gratuitos rompen el grid de pesos por caja, que es justo lo que
da trazabilidad a la factura. Un navegador headless daría fidelidad perfecta
pero exige infraestructura nueva, o sea costo. El resultado en reportlab será
muy parecido pero no idéntico píxel a píxel, y a cambio es gratis,
determinista y testeable.

**Datos frescos de QBO en cada generación, sin snapshot.** Es lo único que
sobrevive a las correcciones manuales.

**Dos webhooks nuevos de n8n, y no se toca el de facturación.** Extender el
workflow de facturación rompería la respuesta: en modo `Last Node`, n8n
responde con la salida del último nodo, así que la app dejaría de recibir
`Invoice.Id`. Los dos nuevos son de dos nodos cada uno.

## Componentes

### `utils/factura_pdf.py` (nuevo)

```python
render_factura_pdf(invoice_json: dict) -> bytes
```

Función pura: recibe el objeto `Invoice` de QBO, devuelve los bytes del PDF.
Sin Flask, sin base de datos, sin red. Se testea sola.

`app.py` ya pasa de 10.000 líneas; el renderizador no va ahí.

Contenido, A4, replicando la estructura del HTML actual: encabezado con datos
de Jomar Foods y logo, bloque *Bill To* con CRIB, detalles de la factura
(número, fechas, términos, moneda), tabla de líneas con el grid de pesos por
caja, datos bancarios y totales con OB.

La moneda se detecta como en el HTML: `CurrencyRef` con `USD`/`DOLLAR` → USD;
en cualquier otro caso, XCG.

### Modelo `Pedido` — una columna nueva

| Columna | Tipo | Contenido |
|---|---|---|
| `doc_number_qbo` | `String(20)` | Número visible de la factura (ej. `5816`) |

Se llena al facturar, junto a `invoice_id_qbo`. Permite mostrar el número en
la lista de pedidos y nombrar el archivo sin consultar QBO.

Migración Alembic, **que hay que correr también en Heroku** (`heroku pg:psql`);
si no, producción rompe al desplegar.

### Webhooks de n8n (a crear)

**1. Obtener factura** — `N8N_INVOICE_FETCH_WEBHOOK_URL`

`Webhook (POST)` → `QuickBooks: get invoice` → responde en modo `Last Node`.
Recibe `{"invoice_id": "47349"}` y devuelve el objeto `Invoice`. Es el nodo
`Obtener Factura` que ya existe en el workflow manual.

**2. Archivar en Drive** — `N8N_DRIVE_WEBHOOK_URL`

`Webhook (POST)` → `Google Drive: upload` → responde. Recibe el PDF y el
nombre de archivo, y lo sube a *Facturacion Jomar Foods*.

Ambos en modo `Last Node`, igual que el de facturación: un 2xx significa que
el nodo terminó bien, un fallo devuelve 500.

### Ruta `GET /pedidos/<int:pedido_id>/factura.pdf`

`@login_required` más el mismo guard de autorización que usa facturar
(`_user_can_manage_pedido`). Flujo:

1. Si el pedido no tiene `invoice_id_qbo` → 404 con mensaje claro
2. Pide la factura a QBO vía el webhook de n8n
3. Renderiza el PDF con `render_factura_pdf`
4. Lo archiva en Drive (best-effort, ver abajo)
5. Devuelve el PDF como `Factura_<doc_number>.pdf`

### Archivado en Drive

Ocurre en cada generación, con timeout de 15s
(`N8N_DRIVE_TIMEOUT`, mismo patrón que `N8N_WEBHOOK_TIMEOUT`). Es
**best-effort**: envuelto en `try/except`, un fallo se loguea pero no impide
que el usuario reciba su PDF.

Si se regenera una factura, Drive queda con dos archivos del mismo nombre; el
más reciente es el válido. Se acepta a propósito: no se borra nada, y lo
normal es generar una sola vez, después de corregir.

### Botón de compartir

En `detalles_pedido.html`, visible solo si el pedido tiene `invoice_id_qbo`.
Usa **Web Share API** con el PDF como `File`: es la única forma que funciona en
el PWA standalone de iPhone, donde una descarga normal o abrir pestaña no
sirven. En escritorio cae a un enlace de descarga.

## Manejo de errores

| Situación | Comportamiento |
|---|---|
| Pedido sin `invoice_id_qbo` (los 909 anteriores a v838) | Botón oculto; ruta 404 con mensaje claro |
| n8n no devuelve la factura | 502 con mensaje; no se genera PDF |
| Falla el archivado en Drive | Se loguea; el usuario igual recibe su PDF |
| `N8N_DRIVE_WEBHOOK_URL` sin configurar | Se omite el archivado, se loguea; no es error |
| Otro vendedor pide el PDF | 403 |

## Tests

**`render_factura_pdf`**, contra JSONs de factura reales. Los fixtures se
obtienen consultando la API de QuickBooks por `Id` y se guardan en
`tests/fixtures/facturas/` como archivos JSON, para que los tests no dependan
de la red. Casos a cubrir:

- XCG con OB al 6% (factura 5811, productos importados)
- XCG con OB al 0% (factura 5814, producción local)
- USD (factura 5807)
- Sin `BillAddr` ni CRIB
- 20 cajas pesadas, que fuerza segunda página (factura 5806)

Se verifica que devuelve un PDF válido, que el número de factura y el total
aparecen en el texto extraído, y que ningún caso lanza excepción.

**Ruta:** 404 sin `invoice_id_qbo`, 200 con `content-type: application/pdf`,
403 desde otro vendedor, 502 si n8n falla.

**Archivado:** que un fallo de Drive no impide que la ruta devuelva el PDF.

## Fuera de alcance

- Reenvío por correo desde la app
- Plantillas de factura configurables
- PDFs de las 909 facturas anteriores a v838 (no tienen `invoice_id_qbo`)
- Tocar el workflow de facturación de n8n

## Pendientes aparte

**Los precios corregidos en QBO no vuelven a la app.** El dashboard y los
reportes leen el `subtotal` de la base local, así que cada corrección manual
deja las ventas reportadas por debajo de las reales. Las facturas 5812 y 5814
valen en QuickBooks 6.212,30 y 5.067,81; en la app siguen con los precios
viejos. Este diseño no lo resuelve — solo evita que el PDF herede el error.
Al traer la factura fresca de QBO queda la puerta abierta para reconciliar,
pero es una decisión de datos financieros que merece su propio diseño.

**El webhook `/webhook/actualizacion-precios` no sirve para esto**: actualiza
`precio_jomar`, no `precio_base` (que es el campo que usa la facturación), y
solo si el producto ya tiene fila de precio — no puede crear precios para
productos nuevos, que fue el origen del incidente del Turkey Ham.

**La carrera del `DocNumber`** en el workflow de facturación sigue sin
resolver: `nextInvoiceNumber()` lee el máximo y suma 1 sin bloqueo, que fue lo
que perdió la factura del pedido 1264. Ya no es silenciosa (devuelve 500),
pero sigue fallando al facturar dos pedidos con pocos segundos de diferencia.
Se resuelve dejando que QuickBooks asigne el número; es una decisión contable
pendiente.
