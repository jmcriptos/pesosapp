# Corte a QuickBooks por API directa en Heroku — paso a paso

Runbook de la Task 8 del plan `2026-09-11-qbo-api-directa.md`. Se salta el
sandbox a propósito: el sandbox no tiene los códigos de impuesto, las clases
ni los campos personalizados de la empresa real, así que la prueba que de
verdad importa es la primera factura real, revisada campo por campo.

Todo es reversible en cada paso con `heroku config:set FACTURACION_BACKEND=n8n`.
n8n no se toca hasta el paso 10.

Datos fijos:

| Qué | Valor |
|---|---|
| App de Heroku | `pesosapp` |
| Dominio | `https://app.jomarfoods.com` (el de `herokuapp.com` no se usa para la Redirect URI) |
| Redirect URI de producción | `https://app.jomarfoods.com/admin/quickbooks/callback` |
| Rama con el código | `claude/festive-goldberg-ds8ujn` |
| Rama que despliega Heroku | `main` |

Los comandos `heroku …` se corren desde tu terminal, con el CLI de Heroku
logueado. **Las claves nunca se pegan en el chat.**

---

## 0. Prerrequisitos (portal de Intuit, 10 minutos)

- [ ] En https://developer.intuit.com → Dashboard → la app que usa n8n →
      **Keys & credentials** → pestaña **Production**: anotá el Client ID y
      el Client Secret. Son los mismos que usa n8n; una app de Intuit admite
      varias conexiones a la vez, cada una con su propio refresh token, así
      que n8n sigue funcionando.
- [ ] En esa misma pestaña, **Redirect URIs** → Add URI:
      `https://app.jomarfoods.com/admin/quickbooks/callback`.
      Tiene que quedar letra por letra igual; Intuit rechaza cualquier
      diferencia (barra final, http, mayúsculas).
- [ ] Tener a mano un usuario **super_admin** de PesosApp: es el único rol
      que ve Configuración → QuickBooks.

## 1. Llevar el código a `main` y desplegar

Desde tu clon local, con la rama actualizada:

```bash
git fetch origin
git checkout main
git pull origin main
git merge --no-ff origin/claude/festive-goldberg-ds8ujn
git push origin main
```

Todavía **no** hagas `git push heroku main`: primero la tabla y las
variables (pasos 2 y 3), para que el primer arranque ya tenga todo.

## 2. Crear la tabla en Postgres (antes del deploy)

```bash
heroku pg:psql --app pesosapp
```

Dentro de psql:

```sql
CREATE TABLE IF NOT EXISTS qbo_conexion (
  id INTEGER PRIMARY KEY,
  realm_id VARCHAR(30),
  access_token TEXT,
  refresh_token TEXT,
  access_expires_at TIMESTAMP,
  refresh_expires_at TIMESTAMP,
  conectado_por INTEGER REFERENCES vendedor(id),
  conectado_en TIMESTAMP,
  ultimo_error VARCHAR(255),
  ultimo_error_en TIMESTAMP
);
\d qbo_conexion
\q
```

Es la única migración. No usa Alembic (ver Global Constraints del plan).

## 3. Variables de entorno (con el backend todavía en n8n)

```bash
heroku config:set --app pesosapp \
  QBO_CLIENT_ID='<client id de producción>' \
  QBO_CLIENT_SECRET='<client secret de producción>' \
  QBO_ENVIRONMENT=production \
  QBO_REDIRECT_URI=https://app.jomarfoods.com/admin/quickbooks/callback \
  QBO_MINOR_VERSION=75 \
  QBO_TIMEOUT=20 \
  QBO_TASA_USD=1.78 \
  FACTURACION_BACKEND=n8n \
  QB_SALES_BACKEND=n8n
```

Con `FACTURACION_BACKEND=n8n` la app sigue facturando por n8n exactamente
como hoy. Los pasos 4 a 6 solo preparan la conexión.

## 4. Deploy

```bash
git push heroku main
heroku logs --tail --app pesosapp
```

Esperar a que aparezca el arranque de gunicorn sin errores. Comprobación
rápida: entrar a la app, ir a Pedidos, y ver que carga.

## 5. Conectar QuickBooks desde la app

1. Entrar con el usuario super_admin.
2. Menú → **QuickBooks** (está debajo de Usuarios).
3. La pantalla tiene que decir «Credenciales en el entorno: Configuradas
   (production)» y «No conectado».
4. **Conectar QuickBooks** → te lleva a Intuit. Iniciá sesión con la cuenta
   que administra Jomar Foods BV en QuickBooks, elegí la empresa
   **Jomar Foods BV** y aceptá.
5. Volvés a la app con «QuickBooks conectado (empresa <realm id>)».
6. **Probar conexión** → tiene que decir «Conexión OK: Jomar Foods BV».

Si algo falla acá:
- `400` al volver de Intuit: la sesión se perdió en el viaje. Volvé a
  entrar a la app y repetí Conectar (no abras Intuit en otra pestaña).
- «Intuit rechazó la solicitud de tokens»: casi siempre es la Redirect URI
  que no coincide con la registrada en el paso 0.
- «Faltan QBO_CLIENT_ID»: el paso 3 no llegó al dyno; `heroku config --app
  pesosapp` para verificar.

## 6. Prueba de humo por línea de comando (opcional, 1 minuto)

```bash
heroku run --app pesosapp flask --app app qbo-fijar-tasa
```

Tiene que imprimir dos líneas como `2026-09-12: ya estaba en 1.78` (n8n ya
fija la tasa cada mañana, así que lo normal es «ya estaba»). Confirma que la
app habla con QuickBooks con sus propios tokens, lee y escribe.

## 7. Cambiar el backend y facturar UN pedido real

Elegir un pedido chico, de un cliente **XCG**, ya preparado y con
trazabilidad completa. Mejor a una hora tranquila: el cambio de variable
reinicia los dynos.

```bash
heroku config:set FACTURACION_BACKEND=qbo --app pesosapp
```

Facturar el pedido desde la app como siempre. El mensaje tiene que ser
«Factura NNNN generada (QBO nnnnn)». Después, **revisar la factura en
QuickBooks** contra esta lista:

| Campo | Esperado |
|---|---|
| Número (DocNumber) | el siguiente al último de facturas y notas de crédito |
| Cliente | el del pedido |
| Fecha / Vencimiento | hoy (Curaçao) / hoy + 7 |
| Términos | el mismo que las facturas de n8n (id 46) |
| Líneas | un renglón por producto y precio; cantidad = suma de pesos o cajas; precio y monto exactos |
| Descripción de cada línea | los pesos de cada caja con dos decimales, separados por tabulador (`23.15  23.40`); productos por cajas `3.00` |
| Clase por línea | la del producto en la app (o la detectada por nombre si no tiene) |
| Código de impuesto y total | el del grupo de facturación: 14 → 0 %, 10 → 6 % sobre el neto |
| Campo Currency | «XCG - Caribbean Guilder» |
| Campo Currency2 (el que se ve en pantalla) | XCG |
| Sales Rep | OF |
| Memo del cliente | los datos bancarios de Jomar, como siempre |

En la app: abrir el PDF de la factura desde el pedido. Se genera leyendo la
factura por API; tiene que verse igual que antes.

## 8. Segunda y tercera factura

- [ ] Un pedido de un cliente **USD** (Bonaire). Revisar además: moneda USD,
      tipo de cambio 1,78, código 13 (Non Tax), Currency «USD - US Dollar»,
      Currency2 USD.
- [ ] Un pedido con productos **por cajas** (atún, aceites) al 6 %. Revisar
      el 6 % sobre el neto y las descripciones `N.00`.

Tras tres facturas limpias, sin tocar nada a mano, la Fase 1 queda cerrada.

## 9. Si algo sale mal

```bash
heroku config:set FACTURACION_BACKEND=n8n --app pesosapp
```

Sin deploy, sin pérdida de datos: la app vuelve a facturar por n8n en el
siguiente pedido. Si la factura ya se creó en QBO con algo mal, se corrige
a mano en QBO como hasta ahora y me pasás qué salió distinto; el traductor
se ajusta con un test y se vuelve a intentar.

Un pedido que quedó «enviado a facturar» sin número se maneja igual que
hoy: verificar en QBO antes de reenviar (la guarda de duplicados sigue).

## 10. Cerrar n8n para facturación (solo tras el paso 8)

1. Heroku Scheduler para la tasa diaria:

   ```bash
   heroku addons:create scheduler:standard --app pesosapp
   heroku addons:open scheduler --app pesosapp
   ```

   Agregar un job **Every day at 09:00 UTC** (05:00 en Curaçao) con el
   comando `flask --app app qbo-fijar-tasa`. Al día siguiente, comprobar en
   QuickBooks (Configuración → Monedas) que la tasa USD del día es 1,78.

2. En n8n, **desactivar** (no borrar) los workflows de facturación, de
   consulta de factura y «Fijar USD en 1.78». Quedan activos Drive, HACCP y
   ventas del dashboard hasta la Fase 2.

3. En Heroku, vaciar las variables que ya no se usan:

   ```bash
   heroku config:unset N8N_WEBHOOK_URL N8N_INVOICE_FETCH_WEBHOOK_URL --app pesosapp
   ```

   (`_facturacion_backend()` ya no las lee con `qbo`, pero así nadie las
   confunde con algo vigente.)

4. Bajar el plan de n8n al mínimo cuando cierre la Fase 2.

---

## Qué NO hacer

- No borrar los workflows de n8n hasta cerrar la Fase 2.
- No cambiar `TAX_RATE_REF` ni el bloque de impuesto en `utils/qbo_factura.py`
  aunque QBO guarde otra tasa: es a propósito (facturas 5863 y 5867).
- No facturar dos pedidos a la vez en la primera prueba: el lock los pone
  en fila, pero la revisión es más fácil de a uno.
