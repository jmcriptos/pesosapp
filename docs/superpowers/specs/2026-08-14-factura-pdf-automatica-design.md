# Factura PDF automática — diseño

Fecha: 2026-08-14

## Problema

Al facturar un pedido, la factura se crea en QuickBooks pero no queda ningún
documento para el cliente. Hoy hay que correr a mano un workflow de n8n que
genera un HTML y lo sube a Google Drive. El cliente necesita un PDF: se lo
mandan por WhatsApp y también se lo entregan impreso con la mercancía.

La generación de PDF que había en n8n usaba PDF Generator API, un servicio de
pago. El objetivo es automatizar todo el proceso sin costos nuevos.

## Contexto que habilita la solución

Dos hechos, ambos verificados el 2026-08-14:

1. **La app ya genera PDFs con reportlab** (etiquetas y reportes de
   importación, `app.py:8042`). No hay dependencia nueva que instalar.
2. **El webhook de n8n está en modo `Last Node`**, así que la respuesta de
   facturación es el objeto `Invoice` crudo de QuickBooks: incluye `BillAddr`
   (con el CRIB en `CountrySubDivisionCode`), `DocNumber`, `DueDate`,
   `SalesTermRef`, `TxnTaxDetail` y las líneas con los pesos por caja en
   `Description`.

El punto 2 es lo que hace innecesario darle credenciales de QuickBooks a la
app: todo lo que la factura necesita llega ya en la respuesta. `Cliente` no
tiene dirección ni CRIB — esos datos solo existen en QBO.

## Decisiones

**Redibujar la factura en reportlab, no replicar el HTML.** El HTML actual usa
CSS Grid y flexbox, que solo un navegador real renderiza bien. Los
renderizadores gratuitos (conversión de Google Drive, Apps Script) rompen el
grid de pesos por caja, que es justo lo que da trazabilidad a la factura. Un
navegador headless daría fidelidad perfecta pero exige infraestructura nueva,
o sea costo. El resultado en reportlab será muy parecido pero no idéntico
píxel a píxel, y a cambio es gratis, determinista y testeable.

**La app empuja el PDF a un webhook nuevo de n8n; no se toca el workflow de
facturación.** Extender el workflow existente con un nodo de Drive rompería la
facturación: en modo `Last Node`, n8n responde con la salida del último nodo,
así que la app pasaría a recibir la respuesta de Drive en vez de `Invoice.Id`.
Un webhook separado (Webhook → Google Drive → responder, 2 nodos) reusa la
credencial de Drive existente y mantiene separadas las dos
responsabilidades: facturar y archivar.

**Snapshot en vez de archivo almacenado.** Se guarda el JSON del Invoice y el
PDF se regenera bajo demanda. Los pedidos facturados ya son inmutables en la
app, así que el render es determinista. El snapshot además es un registro fiel
de lo que se facturó.

## Componentes

### `utils/factura_pdf.py` (nuevo)

```python
render_factura_pdf(invoice_json: dict) -> bytes
```

Función pura: recibe el objeto `Invoice` de QBO, devuelve los bytes del PDF.
Sin Flask, sin base de datos, sin red. Se testea sola.

`app.py` ya pasa de 10.000 líneas; el renderizador no va ahí.

Contenido del PDF, A4, replicando la estructura del HTML actual:
encabezado con datos de Jomar Foods y logo, bloque *Bill To* con CRIB,
detalles de la factura (número, fechas, términos, moneda), tabla de líneas
con el grid de pesos por caja, datos bancarios y totales con OB.

La moneda se detecta como en el HTML: `CurrencyRef` con `USD`/`DOLLAR` → USD,
en cualquier otro caso XCG.

### Modelo `Pedido` — dos columnas nuevas

| Columna | Tipo | Contenido |
|---|---|---|
| `doc_number_qbo` | `String(20)` | Número visible de la factura (ej. `5816`) |
| `factura_qbo_json` | `Text` | Snapshot del objeto `Invoice` de QBO |

Ambas se llenan en `facturar_pedido` cuando la respuesta trae un `Invoice`.
Migración Alembic, **que hay que correr también en Heroku** (`heroku pg:psql`);
si no, producción rompe al desplegar.

### Ruta `GET /pedidos/<int:pedido_id>/factura.pdf`

`@login_required` + el mismo guard de autorización que usa facturar
(`_user_can_manage_pedido`). Devuelve el PDF con nombre
`Factura_<doc_number>.pdf`. Si el pedido no tiene `factura_qbo_json`
(pedidos anteriores a este cambio), 404 con mensaje explicando que solo hay
PDF para facturas emitidas desde esta versión.

### Push a Drive

Variable de entorno `N8N_DRIVE_WEBHOOK_URL`. Tras commitear la facturación,
la app renderiza el PDF y lo manda al webhook con `_webhook_headers()`.

Es **best-effort y no transaccional**: se envuelve en `try/except`, con
timeout de 15s (configurable vía `N8N_DRIVE_TIMEOUT`, mismo patrón que
`N8N_WEBHOOK_TIMEOUT`). Un fallo de Drive registra un warning y muestra un aviso,
pero nunca revierte ni ensucia la facturación. Un fallo del render tampoco:
la factura en QuickBooks ya existe y el PDF se puede regenerar después desde
la ruta.

### Botón de compartir

En `detalles_pedido.html`, visible solo si el pedido tiene snapshot. Usa
**Web Share API** con el PDF como `File`: es la única forma que funciona en el
PWA standalone de iPhone, donde una descarga normal o abrir pestaña no sirven.
En escritorio cae a un enlace de descarga.

## Manejo de errores

| Situación | Comportamiento |
|---|---|
| Pedido sin `factura_qbo_json` | Botón oculto; ruta 404 con mensaje claro |
| Falla el push a Drive | Warning en pantalla y en log; la factura no se toca |
| Falla el render al facturar | Se captura y se loguea; nunca tumba una facturación |
| `N8N_DRIVE_WEBHOOK_URL` sin configurar | Se omite el push, se loguea; no es error |
| Otro vendedor pide el PDF | 403 |

## Tests

**`render_factura_pdf`**, contra JSONs de factura reales. Los fixtures se
obtienen consultando la API de QuickBooks por `Id` de factura y se guardan en
`tests/fixtures/facturas/` como archivos JSON, para que los tests no dependan
de la red. Casos a cubrir:

- XCG con OB al 6% (factura 5811, productos importados)
- XCG con OB al 0% (factura 5814, producción local)
- USD (factura 5807)
- Sin `BillAddr` ni CRIB
- 20 cajas pesadas, que fuerza segunda página (factura 5806)

Se verifica que devuelve un PDF válido, que el número de factura y el total
aparecen en el texto extraído, y que ningún caso lanza excepción.

**Ruta:** 404 sin snapshot, 200 con `content-type: application/pdf`, 403 desde
otro vendedor.

**Facturación:** que `factura_qbo_json` y `doc_number_qbo` se persisten al
facturar bien, y que un fallo del push a Drive no impide que el pedido quede
facturado.

## Fuera de alcance

- Reenvío por correo desde la app
- Plantillas de factura configurables
- Regenerar PDFs de las 909 facturas anteriores (no tienen snapshot)
- Tocar el workflow de facturación de n8n

## Pendiente aparte

La carrera del `DocNumber` en el workflow de facturación sigue sin resolver:
`nextInvoiceNumber()` lee el máximo y suma 1 sin bloqueo, que fue lo que
perdió la factura del pedido 1264. Ya no es silenciosa (devuelve 500), pero
sigue fallando al facturar dos pedidos con pocos segundos de diferencia.
Se resuelve dejando que QuickBooks asigne el número; es una decisión contable
pendiente y no forma parte de este diseño.
