# QuickBooks por API directa (sin n8n) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Que la app facture y consulte facturas en QuickBooks Online hablando
directo con la API v3 de Intuit, sin pasar por n8n. Fase 1 saca de n8n la
facturación y la consulta de factura (lo que hoy bloquea el negocio). Fase 2
saca las ventas del dashboard. Drive y las alertas HACCP quedan en n8n.

**Por qué:** el plan de n8n Cloud se cobra por ejecución y en septiembre de
2026 se llegó al tope a mitad de mes, con la facturación parada. La API de
QuickBooks no tiene tope práctico (500 llamadas por minuto por empresa) y
devuelve siempre el Id de la factura, cosa que n8n no garantiza (ver la guarda
de duplicados en `facturar_pedido`).

**Architecture:** Un cliente HTTP puro en `utils/qbo_client.py` (OAuth2,
refresco de token, GET/POST con reintento ante 401). Un traductor puro en
`utils/qbo_factura.py` que convierte el payload de `pedido_a_json` en un
`Invoice` de QBO, reemplazando el nodo de código de n8n. Los tokens viven en
una tabla de fila única en Postgres, no en memoria, porque gunicorn corre
varios workers y Heroku recicla los dynos a diario. Cada camino que hoy sale a
n8n gana un *backend* elegible por variable de entorno (`n8n` o `qbo`), así el
corte es reversible con un `heroku config:set` y sin deploy.

```
HOY     app ──POST──▶ n8n ──▶ Code node ──▶ QBO API
FASE 1  app ──▶ utils/qbo_factura (construir Invoice) ──▶ utils/qbo_client ──▶ QBO API
FASE 2  app ──▶ utils/qbo_ventas (query Invoice por rango) ──▶ utils/qbo_client ──▶ QBO API
```

**Tech Stack:** Flask, SQLAlchemy, `requests` (ya instalado), pytest. API v3 de
QuickBooks Online con `minorversion=75`. OAuth 2.0 de Intuit, scope
`com.intuit.quickbooks.accounting`.

**Esfuerzo estimado:** Fase 1, dos a tres días. Fase 2, uno a dos días. Más el
trámite de JM en Intuit (una hora) y la ventana de corte en producción.

## Prerrequisitos (JM, antes de la Task 1)

- [ ] Crear una app en https://developer.intuit.com (tipo QuickBooks Online
      and Payments, scope Accounting). Anotar **Client ID** y **Client Secret**
      de *Development* (sandbox) y de *Production*. Se guardan en Heroku, no
      en el repo ni en este documento.
- [ ] Registrar la Redirect URI en la app de Intuit, exactamente:
      `https://<dominio-de-pesosapp>/admin/quickbooks/callback` (producción) y
      `http://localhost:5000/admin/quickbooks/callback` (desarrollo).
- [ ] Crear (o confirmar) una **empresa sandbox** en el portal de Intuit. Ahí
      se prueba la Fase 1 antes de tocar la empresa real.
- [x] Body real de n8n del 2026-09-11 guardado en `n8n-facturacion-body-2026-09-11.json` (ver Task 4). Sigue faltando el export del workflow para la consulta de DocNumber:
- [ ] Exportar el JSON del workflow de facturación de n8n (`...` → Download) y
      dejarlo en `docs/superpowers/specs/n8n-facturacion-export.json`. El nodo
      `Generar Numero Factura` es la fuente de verdad de: la consulta de
      DocNumber, el agrupado de líneas, los `CustomField` 1–3, `TxnDate`,
      `DueDate`, `PrivateNote`/`CustomerMemo` y cualquier campo que no esté en
      el diseño del 2026-08-28. **Sin este export la Task 4 se hace a ciegas.**
- [ ] Exportar también el workflow de ventas (el que responde a
      `N8N_QB_SALES_WEBHOOK_URL`) para la Fase 2: define qué filas y qué claves
      espera hoy el dashboard (`transactions[]`, `home_amount`, `weight`…).

## Global Constraints

- Python 3.12 (`.python-version`), tests con `python -m pytest tests/ -q`
  **sin** forzar `DATABASE_URL` (conftest usa sqlite en memoria).
- **No agregar dependencias.** `requests` alcanza para OAuth2 y la API v3. No
  usar `python-quickbooks`, `intuit-oauth` ni `cryptography`.
- **No usar Alembic.** Cambios de esquema por `CREATE TABLE`/`ALTER TABLE`
  directo, local y en Heroku, como en los planes anteriores. La tabla nueva se
  crea en producción **antes** del deploy.
- Todo texto visible al usuario va en español.
- **Nunca loguear tokens ni el client secret.** Los logs pueden citar
  `realm_id`, códigos HTTP y el `Fault` de QBO, nada más.
- Los caminos viejos por n8n **no se borran en la Fase 1**: quedan detrás del
  selector de backend para poder volver atrás sin deploy.
- Toda llamada a QBO respeta el límite del router de Heroku (30 s): timeout
  de 20 s por request, un solo reintento y solo ante 401 por token vencido.
- Decisión vigente de JM (`docnumber-carrera-decision`): la numeración sigue
  siendo manual, últimas 50 facturas más uno. No se cambia en este plan.

---

## File Structure

| Archivo | Responsabilidad |
|---|---|
| `utils/qbo_client.py` (crear) | OAuth2 de Intuit y wrapper HTTP de la API v3. Sin Flask, sin DB: recibe config y un *token store* con `cargar()`/`guardar()`. |
| `utils/qbo_factura.py` (crear) | Función pura `construir_invoice(payload, doc_number, hoy)` que arma el body del `Invoice`. Reemplaza al nodo de código de n8n. |
| `utils/qbo_ventas.py` (crear, Fase 2) | Query paginada de `Invoice` por rango de fechas y aplanado a las filas que ya entiende `_normalizar_metricas_ventas_quickbooks`. |
| `app.py` (modificar) | Modelo `QboConexion`, token store sobre SQLAlchemy, rutas `/admin/quickbooks/*`, selector de backend en `facturar_pedido`, `_obtener_factura_qbo` y `_qb_refrescar_desde_red`. |
| `templates/admin/quickbooks.html` (crear) | Estado de la conexión y botones Conectar/Desconectar. |
| `templates/admin/configuracion.html` (modificar) | Enlace a la página anterior. |
| `tests/test_qbo_client.py`, `tests/test_qbo_factura.py`, `tests/test_qbo_conexion.py`, `tests/test_qbo_ventas.py` (crear) | Tests por módulo, con `requests` mockeado. |
| `tests/fixtures/qbo/*.json` (crear) | Respuestas reales de QBO (sandbox) anonimizadas: token, invoice creada, invoice consultada, query de DocNumber, query de ventas. |
| `.env.example`, `docs/superpowers/specs/2026-08-28-factura-qbo-sin-correcciones-design.md` (modificar) | Variables nuevas y nota de que el nodo de n8n queda reemplazado. |

## Variables de entorno nuevas

| Variable | Valor | Notas |
|---|---|---|
| `QBO_CLIENT_ID` / `QBO_CLIENT_SECRET` | de Intuit | Sandbox en local, producción en Heroku. |
| `QBO_REDIRECT_URI` | URL del callback | Tiene que coincidir letra por letra con la registrada en Intuit. |
| `QBO_ENVIRONMENT` | `sandbox` \| `production` | Elige el host: `sandbox-quickbooks.api.intuit.com` o `quickbooks.api.intuit.com`. |
| `QBO_MINOR_VERSION` | `75` | Intuit exige mínimo 75 desde 2025. |
| `QBO_TIMEOUT` | `20` | Segundos por request. |
| `FACTURACION_BACKEND` | `n8n` (default) \| `qbo` | Fase 1. Selecciona quién crea y consulta facturas. |
| `QB_SALES_BACKEND` | `n8n` (default) \| `qbo` | Fase 2. Selecciona de dónde salen las ventas del dashboard. |

Endpoints de Intuit que usa el cliente (fijos, no configurables):

- Autorización: `https://appcenter.intuit.com/connect/oauth2`
- Tokens: `https://oauth.platform.intuit.com/oauth2/v1/tokens/bearer`
- Revocación: `https://developer.api.intuit.com/v2/oauth2/tokens/revoke`
- API: `https://{host}/v3/company/{realm_id}/...?minorversion=75`

Vida de los tokens: el *access token* dura una hora; el *refresh token* rota
en cada refresco y caduca a los **100 días sin uso**. Con facturación semanal
nunca caduca. Si caduca, la única salida es que un super_admin vuelva a
Conectar; la app tiene que decirlo con claridad, no fallar en silencio.

---

# FASE 1 — Facturación y consulta de factura

### Task 1: Cliente OAuth2 + API v3 (`utils/qbo_client.py`)

**Files:**
- Create: `utils/qbo_client.py`
- Test: `tests/test_qbo_client.py`

**Interfaces:**

```python
class QboConfig(NamedTuple):
    client_id: str
    client_secret: str
    redirect_uri: str
    environment: str        # 'sandbox' | 'production'
    minor_version: int = 75
    timeout: float = 20.0

class TokenStore(Protocol):
    def cargar(self) -> dict | None: ...      # {'realm_id', 'access_token', 'refresh_token', 'access_expires_at', 'refresh_expires_at'}
    def guardar(self, tokens: dict) -> None: ...

class QboError(Exception):            # base; .status, .fault (dict de QBO), .es_auth (bool)
class QboNoConectado(QboError):       # no hay tokens o el refresh token venció

class QboClient:
    def __init__(self, config: QboConfig, store: TokenStore, session=None): ...
    def url_autorizacion(self, state: str) -> str
    def canjear_codigo(self, code: str, realm_id: str) -> None     # guarda tokens
    def refrescar(self) -> None                                    # guarda tokens
    def revocar(self) -> None
    def get(self, path: str, params: dict | None = None) -> dict
    def post(self, path: str, body: dict, params: dict | None = None) -> dict
    def query(self, sql: str) -> dict                               # GET /query?query=...
```

Reglas del wrapper:
- Antes de cada request, si `access_expires_at` está a menos de 60 s, refresca.
- Ante `401`, refresca **una vez** y reintenta la misma request. Un segundo
  401 levanta `QboError(es_auth=True)`.
- Ante `4xx` con body `Fault`, levanta `QboError` con el `Fault` completo
  (`Fault.Error[0].Message` y `.Detail` son lo que se muestra al usuario).
- Ante timeout o error de conexión, deja pasar las excepciones de `requests`
  para que `facturar_pedido` conserve sus mensajes actuales.
- Header `Accept: application/json` en todo; `Content-Type: application/json`
  en POST. Autenticación del endpoint de tokens con Basic `client_id:secret`.

- [ ] **Step 1: Tests que fallan** (`requests.Session` mockeado con `MagicMock`,
      como en `tests/test_facturacion.py`): `url_autorizacion` incluye
      `client_id`, `redirect_uri`, `scope`, `state` y `response_type=code`;
      `canjear_codigo` guarda `realm_id` y calcula `access_expires_at` /
      `refresh_expires_at` desde `expires_in` / `x_refresh_token_expires_in`;
      `get` refresca cuando el token está por vencer; `get` refresca y
      reintenta ante 401 y falla al segundo 401; `post` traduce un `Fault` a
      `QboError` con el mensaje; `query` codifica el SQL en la URL;
      `QboNoConectado` cuando el store devuelve `None`.
- [ ] **Step 2: Implementar** hasta que pasen. Sin estado global: una
      instancia por request se construye en `app.py` (Task 2).
- [ ] **Step 3:** `python -m pytest tests/test_qbo_client.py -q` en verde.

### Task 2: Persistir la conexión (`QboConexion`) y token store

**Files:**
- Modify: `app.py` (modelos, junto a `VentasQbCache` ~línea 3316; helpers junto a `N8N_WEBHOOK_URL` ~línea 9207)
- Test: `tests/test_qbo_conexion.py`

**Modelo (fila única, id=1):**

```python
class QboConexion(db.Model):
    __tablename__ = 'qbo_conexion'
    id = db.Column(db.Integer, primary_key=True)
    realm_id = db.Column(db.String(30), nullable=True)
    access_token = db.Column(db.Text, nullable=True)
    refresh_token = db.Column(db.Text, nullable=True)
    access_expires_at = db.Column(db.DateTime, nullable=True)
    refresh_expires_at = db.Column(db.DateTime, nullable=True)
    conectado_por = db.Column(db.Integer, db.ForeignKey('vendedor.id'), nullable=True)
    conectado_en = db.Column(db.DateTime, nullable=True)
    ultimo_error = db.Column(db.String(255), nullable=True)
    ultimo_error_en = db.Column(db.DateTime, nullable=True)
```

SQL para producción (correr en Heroku **antes** del deploy):

```sql
CREATE TABLE IF NOT EXISTS qbo_conexion (
  id INTEGER PRIMARY KEY,
  realm_id VARCHAR(30), access_token TEXT, refresh_token TEXT,
  access_expires_at TIMESTAMP, refresh_expires_at TIMESTAMP,
  conectado_por INTEGER REFERENCES vendedor(id), conectado_en TIMESTAMP,
  ultimo_error VARCHAR(255), ultimo_error_en TIMESTAMP
);
```

**Decisión sobre cifrado:** los tokens van en texto plano en Postgres, igual
que n8n los guarda en su propia base. La base ya es la frontera de confianza
de la app (credenciales de usuarios, precios, clientes). Cifrar exigiría una
dependencia nueva y una clave más en Heroku, y no cambia el modelo de amenaza
(quien lee la base lee la clave). Se anota como riesgo aceptado; si JM quiere
cifrado, va en un plan aparte.

**Helpers en `app.py`:**
- `_qbo_config()` lee las variables de entorno; devuelve `None` si faltan
  `QBO_CLIENT_ID`/`QBO_CLIENT_SECRET`.
- `_QboStoreDb` implementa `TokenStore` sobre `QboConexion` con commit
  inmediato en `guardar` (dos workers no pueden refrescar a la vez con tokens
  distintos: Intuit invalida el refresh token anterior al rotar; el commit
  inmediato reduce la ventana, y el reintento ante 401 de la Task 1 cubre al
  worker que perdió la carrera).
- `_qbo_client()` construye `QboClient(_qbo_config(), _QboStoreDb())`.
- `_facturacion_backend()` devuelve `'qbo'` solo si `FACTURACION_BACKEND=qbo`
  **y** `_qbo_config()` no es `None`; si no, `'n8n'`. Loguea un warning
  cuando piden `qbo` sin credenciales.

- [ ] **Step 1: Tests:** `guardar` persiste y `cargar` relee; `cargar`
      devuelve `None` sin fila o sin `refresh_token`; `_facturacion_backend`
      cae a `n8n` sin credenciales.
- [ ] **Step 2: Implementar.**
- [ ] **Step 3:** correr `tests/test_qbo_conexion.py` y la suite completa.

### Task 3: Pantalla Conectar QuickBooks (`/admin/quickbooks`)

**Files:**
- Modify: `app.py` (rutas junto a `admin_configuracion` ~línea 5286)
- Create: `templates/admin/quickbooks.html`
- Modify: `templates/admin/configuracion.html` (enlace)
- Test: `tests/test_qbo_conexion.py`

Rutas, todas con `@login_required` y `@requiere_rol(['super_admin'])`:

| Ruta | Método | Hace |
|---|---|---|
| `/admin/quickbooks` | GET | Muestra estado: conectado o no, `realm_id`, entorno, vencimiento del refresh token, último error, backend activo de facturación y de ventas. |
| `/admin/quickbooks/conectar` | POST | Genera `state` aleatorio, lo guarda en `session['qbo_oauth_state']`, redirige a `url_autorizacion(state)`. |
| `/admin/quickbooks/callback` | GET | Valida `state` contra la sesión (si no coincide: 400 y flash). Lee `code` y `realmId`, llama `canjear_codigo`, guarda `conectado_por`/`conectado_en`, flash de éxito, redirige a `/admin/quickbooks`. |
| `/admin/quickbooks/desconectar` | POST | `revocar()` (best-effort) y vacía la fila. |
| `/admin/quickbooks/probar` | POST | `GET companyinfo/{realm_id}` y muestra el nombre de la empresa. Es la prueba de humo tras conectar. |

El template sigue las convenciones de `base.js` (sin manejadores inline; los
botones son `<form method="post">` con el token CSRF de Flask-WTF).

- [ ] **Step 1: Tests:** un usuario no super_admin recibe 403; `conectar`
      guarda `state` y redirige a `appcenter.intuit.com`; `callback` con
      `state` incorrecto no guarda nada; `callback` correcto persiste
      `realm_id` (cliente mockeado); `probar` muestra `CompanyName`.
- [ ] **Step 2: Implementar rutas y template.**
- [ ] **Step 3:** prueba manual en local contra sandbox: conectar, probar,
      desconectar. Anotar en este documento cualquier sorpresa del flujo.

### Task 4: Traductor de payload a `Invoice` (`utils/qbo_factura.py`)

**Files:**
- Create: `utils/qbo_factura.py`
- Create: `tests/fixtures/qbo/invoice_creada.json` (respuesta real del sandbox)
- Test: `tests/test_qbo_factura.py`
- Fuente: `docs/superpowers/specs/n8n-facturacion-export.json` (prerrequisito)

**Interfaz:**

```python
def construir_invoice(payload: dict, doc_number: str, hoy: date) -> dict
```

Recibe **exactamente** lo que devuelve `pedido_a_json` (no se cambia el
payload: la app ya manda `currency_qbo`, `currency_display`, `exchange_rate`,
`class_ref`, `product_name` y el `tax_rate` como código de QBO). Devuelve el
body para `POST /invoice`.

Reglas, tomadas del **body real que n8n mandó a QBO el 2026-09-11** (factura
5879, cliente 1497, pegado por JM en el chat; copia en
`docs/superpowers/specs/n8n-facturacion-body-2026-09-11.json`). Ese body es
más nuevo que el diseño del 2026-08-28: ya manda `CurrencyRef`,
`ExchangeRate` y `Currency2`. Donde el body y el diseño difieren, manda el
body.

**Cabecera:**
- `CustomerRef.value = payload['customer_qbo_id']`.
- `DocNumber = doc_number`.
- `TxnDate = hoy`, `DueDate = hoy + 7`. Confirmado (11 → 18 de septiembre).
- `SalesTermRef.value = '46'`. **Nuevo, no estaba en el diseño.** Es el
  término de pago de QBO (presumiblemente Net 7). Constante `QBO_SALES_TERM_ID`
  en `utils/qbo_factura.py`, con comentario. *Abierto: ¿es fijo para todos los
  clientes o n8n lo lee del cliente?*
- `GlobalTaxCalculation = 'TaxExcluded'`.
- `CurrencyRef.value = payload['currency_qbo']` y `ExchangeRate =
  payload['exchange_rate']` **siempre**, también en ANG con tipo de cambio 1.
  Así lo manda n8n hoy; se replica igual.

**`CustomField`** (los cuatro, en este orden, siempre `Type: 'StringType'`):

| DefinitionId | Name | StringValue |
|---|---|---|
| `1` | `Currency` | `payload['currency_display']` |
| `2` | `Sales Rep` | `'OF'` en la factura de ejemplo. *Abierto: ¿fijo, o sale del vendedor del pedido?* |
| `3` | `Tax ID No.` | `''` |
| `1000000003` | `Currency2` | `'1'` para XCG. *Abierto: qué valor lleva USD (y ANG si difiere). Es el índice de la lista, no el texto.* |

`Currency2` **sí** se escribe por API con `DefinitionId '1000000003'`: el
pendiente 1 del diseño del 2026-08-28 queda resuelto por la evidencia.

**Líneas:**
- Se agrupa por `(product_qbo_id, unit_price)`. `Qty` es la suma de `qty`,
  `Amount` es `round(sum(amount), 2)` (verificado: 46,55 × 13,20 = 614,46).
- `Description` = los pesos de cada caja, con **dos decimales y separados por
  tabulador** (`"23.15\t23.40"`). Es lo que leen
  `utils/factura_pdf._pesos_de_descripcion` y la trazabilidad por caja; el
  separador tiene que ser exactamente `\t`. *Abierto: qué pone n8n en
  `Description` de un producto no pesable (cajas enteras, con o sin lote). La
  factura de ejemplo solo tiene pesables.*
- `DetailType = 'SalesItemLineDetail'`.
- `SalesItemLineDetail.ItemRef = {value: product_qbo_id, name: product_name}`.
  El `name` va **sin** la categoría (`"Cooked Chicken Ham"`, no
  `"Smoked and Cooked:Cooked Chicken Ham"`); QBO resuelve por `value`.
- `UnitPrice`, `Qty`, `TaxCodeRef.value = 'TAX'`, `ClassRef.value = class_ref`
  solo si viene (sin `name`).
- Orden de las líneas: el del payload (que ya sale ordenado por clase y
  producto desde `pedido_a_json`).

**Impuesto (`TxnTaxDetail`):** n8n manda hoy el bloque completo calculado a
mano: `TotalTax`, `TxnTaxCodeRef` y un `TaxLine` con `TaxRateRef`,
`TaxPercent`, `NetAmountTaxable` y `PercentBased: true`. Para el código `14`
usa `TaxRateRef '25'` con 0 %. Dos caminos, se decide en sandbox:

1. **Preferido:** mandar solo `TxnTaxDetail: {TxnTaxCodeRef: {value: código}}`
   y dejar que QBO calcule `TotalTax` y `TaxLine` a partir de
   `GlobalTaxCalculation: 'TaxExcluded'`. Es lo que recomendaba el diseño del
   2026-08-28 y elimina el mapa de tasas. Se prueba en sandbox con `10` (6 %),
   `14` (0 %) y `13` (Non Tax); si QBO devuelve el impuesto correcto, listo.
2. **Si QBO no calcula solo:** replicar el bloque de n8n. Hace falta el mapa
   código → `TaxRateRef` y porcentaje: `14 → 25, 0 %` está confirmado;
   *abierto: `10 → ?, 6 %` y `13 → ?, 0 %`* (se leen con
   `SELECT * FROM TaxCode` en la empresa real). `NetAmountTaxable` es la suma
   de `Amount` de las líneas; `TotalTax = round(net × pct / 100, 2)`.

**Notas:** la factura de ejemplo no trae `PrivateNote` ni `CustomerMemo`, así
que no se sabe si n8n los manda cuando `notes` tiene valor. El traductor manda
`CustomerMemo.value = payload['notes']` si hay notas, y **siempre**
`PrivateNote = 'PesosApp pedido {order_id}'`: es la única forma de rastrear un
duplicado desde QBO y no se imprime en la factura del cliente.

**Preguntas abiertas para JM antes de cerrar la Task 4** (cuatro, todas
chicas): `SalesTermRef` fijo o por cliente; `Sales Rep` fijo o por vendedor;
valor de `Currency2` para USD; `Description` de un producto no pesable. Se
responden con una factura USD de ejemplo y una con un producto por cajas.

- [ ] **Step 1: Tests** con un payload de cliente XCG (dos productos, uno
      pesable con tres cajas) y otro USD: agrupado y descripciones, `ClassRef`
      presente/ausente, `TxnTaxCodeRef` 10/14/13, `CurrencyRef`+`ExchangeRate`
      solo en USD, `ValueError` si se mezclan impuestos, `CustomField` 1–3,
      `DocNumber` y fechas. Comparar el body completo contra un fixture
      escrito a mano a partir del export de n8n.
- [ ] **Step 2: Implementar** como función pura. Sin Flask, sin DB, sin red.
- [ ] **Step 3:** en verde. Guardar en `tests/fixtures/qbo/` la primera
      respuesta real del sandbox para la Task 6.

### Task 5: Número de factura (`siguiente_doc_number`)

**Files:**
- Modify: `utils/qbo_factura.py`
- Create: `tests/fixtures/qbo/query_docnumber.json`
- Test: `tests/test_qbo_factura.py`

```python
def siguiente_doc_number(client) -> str
```

Ejecuta `SELECT DocNumber FROM Invoice ORDERBY MetaData.CreateTime DESC
MAXRESULTS 50`, toma el mayor **numérico** (ignorando DocNumbers no numéricos)
y suma uno. Es la misma regla del nodo de n8n; la carrera entre dos
facturaciones simultáneas es la decisión vigente de JM y no se cambia acá.
Si QBO devuelve `6240` (Duplicate Document Number) al crear, `facturar_pedido`
reintenta **una sola vez** con el número siguiente: cubre la carrera sin
cambiar la decisión.

- [ ] **Step 1: Tests:** mayor numérico entre mezclados, lista vacía levanta
      `QboError` claro (no inventar "1"), ignora strings.
- [ ] **Step 2: Implementar.**

### Task 6: `facturar_pedido` con backend `qbo`

**Files:**
- Modify: `app.py` (`facturar_pedido` ~línea 9481, `_extraer_invoice_id` ~línea 4689)
- Test: `tests/test_facturacion.py` (nuevo bloque), `tests/test_pedido_inmutable.py`

Cambio mínimo y aditivo: entre la validación del payload y la llamada a n8n se
inserta la bifurcación:

```python
if _facturacion_backend() == 'qbo':
    resp_data, error = _crear_factura_qbo(pedido_id, payload)   # nuevo helper
    if error:
        flash(error, 'danger'); return _volver_a('lista_pedidos')
else:
    ... (bloque actual de requests.post a n8n, intacto) ...
    resp_data = resp.json()
invoice_id, doc_number = _extraer_invoice_id(resp_data)
```

`_crear_factura_qbo(pedido_id, payload)`:
1. `client = _qbo_client()`; sin conexión → mensaje «QuickBooks no está
   conectado. Un administrador tiene que conectarlo en Configuración →
   QuickBooks.»
2. `doc = siguiente_doc_number(client)`.
3. `body = construir_invoice(payload, doc, hoy_curazao)`.
4. `client.post('invoice', body)`; ante `Fault` con código `6240`, repetir el
   paso 2 y 3 una vez.
5. Devuelve el JSON crudo: `{"Invoice": {...}}`, la misma forma que ya
   entiende `_extraer_invoice_id`. **Todo lo que sigue en `facturar_pedido`
   (commit atómico, evento de auditoría, flashes) no cambia.**

Mapeo de errores a los mensajes existentes: timeout y conexión conservan los
textos de hoy con «QuickBooks» en vez de «N8N»; `QboError` con `Fault` muestra
`Fault.Error[0].Message` y `Detail` recortado a 200 caracteres;
`QboError(es_auth=True)` guarda `ultimo_error` en `QboConexion` y pide
reconectar.

- [ ] **Step 1: Tests** con `FACTURACION_BACKEND=qbo` y `_qbo_client`
      parcheado: factura creada marca el pedido `facturado` con `invoice_id_qbo`
      y `doc_number_qbo`; `6240` reintenta una vez con el número siguiente;
      `Fault` de validación deja el pedido sin tocar y muestra el mensaje; sin
      conexión no llama a nada; con backend `n8n` los tests existentes siguen
      pasando sin cambios.
- [ ] **Step 2: Implementar.**
- [ ] **Step 3:** suite completa en verde.

### Task 7: `_obtener_factura_qbo` con backend `qbo`

**Files:**
- Modify: `app.py` (`_obtener_factura_qbo` ~línea 9220)
- Create: `tests/fixtures/qbo/invoice_consultada.json`
- Test: `tests/test_factura_ruta.py`

Con backend `qbo`: `client.get(f'invoice/{invoice_id}')` devuelve
`{"Invoice": {...}}`, que `utils/factura_pdf._pick_invoice` ya acepta. El PDF,
la comparación de precios (`_comparar_precios_factura`) y el archivado en
Drive no cambian una línea. Sigue devolviendo `None` ante cualquier fallo,
como hoy.

- [ ] **Step 1: Test:** con backend `qbo` el PDF se genera desde la respuesta
      directa (fixture); con `n8n` sigue usando el webhook.
- [ ] **Step 2: Implementar.**

### Task 8: Config, documentación y corte a producción

**Files:**
- Modify: `.env.example`, `docs/superpowers/specs/2026-08-28-factura-qbo-sin-correcciones-design.md`, `HEROKU_DEBUG.md`

- [ ] **Step 1:** variables nuevas en `.env.example` con comentarios; nota en
      el spec del 2026-08-28: «el nodo de código de n8n queda reemplazado por
      `utils/qbo_factura.py`; el export vive en `n8n-facturacion-export.json`».
- [ ] **Step 2: Sandbox de punta a punta** (local, `QBO_ENVIRONMENT=sandbox`):
      un pedido XCG con pesable y no pesable, uno USD. Verificar en la empresa
      sandbox clase por línea, tasa, moneda, tipo de cambio, DocNumber
      correlativo, descripciones con los pesos, y abrir el PDF desde la app.
- [ ] **Step 3: Producción, en este orden:**
      1. `CREATE TABLE qbo_conexion` en Heroku Postgres.
      2. `heroku config:set` de `QBO_*` de producción con
         `FACTURACION_BACKEND=n8n` (todavía).
      3. Deploy. Conectar desde `/admin/quickbooks` con el usuario de JM y
         pulsar Probar: tiene que mostrar «Jomar Foods BV».
      4. `heroku config:set FACTURACION_BACKEND=qbo`.
      5. Facturar **un** pedido real, revisarlo en QBO campo por campo con JM.
      6. Si algo sale mal: `heroku config:set FACTURACION_BACKEND=n8n` y se
         sigue por n8n (o por el plan superior) mientras se corrige. Sin
         deploy, sin pérdida de datos.
      7. Tras tres facturas limpias, se da por cerrada la Fase 1.
- [ ] **Step 4:** vaciar `N8N_INVOICE_FETCH_WEBHOOK_URL`. Desactivar el
      workflow de facturación en n8n (no borrarlo hasta cerrar la Fase 2).

**Criterio de salida de la Fase 1:** una semana de facturas sin corrección
manual y sin tocar n8n para facturar ni para ver PDFs.

---

# FASE 2 — Ventas del dashboard

### Task 9: Query de ventas (`utils/qbo_ventas.py`)

**Files:**
- Create: `utils/qbo_ventas.py`
- Create: `tests/fixtures/qbo/query_ventas.json`
- Test: `tests/test_qbo_ventas.py`
- Fuente: export del workflow de ventas de n8n (prerrequisito)

```python
def consultar_ventas(client, desde: date, hasta: date) -> dict
```

Devuelve **la misma forma que hoy devuelve n8n**, para que
`_normalizar_metricas_ventas_quickbooks` (`app.py` ~línea 1620) no cambie:
`{'transactions': [fila, ...]}` con una fila por **línea** de factura y las
claves que el normalizador ya lee: `date`, `invoice_number`, `customer`,
`product`, `quantity`, `weight`, `amount`, `currency`, `exchange_rate`,
`home_amount`.

Cómo se arma:
- `SELECT * FROM Invoice WHERE TxnDate >= '{desde}' AND TxnDate <= '{hasta}'
  ORDERBY TxnDate STARTPOSITION {n} MAXRESULTS 1000`, paginando hasta que
  vuelvan menos de 1000. Con el volumen de Jomar (decenas de facturas por
  mes) son una o dos páginas para el rango del dashboard.
- Notas de crédito: si el workflow de n8n las restaba (ver export), agregar la
  misma query sobre `CreditMemo` con `amount` negativo. Si no las restaba, no
  agregarlas ahora: primero igualar, después mejorar.
- `home_amount = Line.Amount * ExchangeRate` cuando `CurrencyRef != 'ANG'`;
  `_monto_qb_a_xcg` ya prioriza `home_amount` y cae al fallback si falta.
- `weight`: suma de los pesos de `Line.Description` con
  `utils.factura_pdf._pesos_de_descripcion` (misma regla que el PDF). Confirmar
  contra el export cómo lo calculaba n8n.
- Se omiten líneas sin `SalesItemLineDetail` (subtotales, descuentos).

- [ ] **Step 1: Tests:** una factura ANG y una USD del fixture producen las
      filas esperadas; paginación con dos páginas; líneas de subtotal
      ignoradas; `home_amount` correcto.
- [ ] **Step 2: Implementar.**

### Task 10: `_qb_refrescar_desde_red` con backend `qbo`

**Files:**
- Modify: `app.py` (`_qb_refrescar_desde_red` ~línea 2019, `_quickbooks_sales_enabled` ~línea 1438, `_obtener_metricas_ventas_quickbooks` ~línea 2091)
- Test: `tests/test_qb_cache_compartida.py`, `tests/test_qb_refresco_segundo_plano.py`

Con `QB_SALES_BACKEND=qbo`: en vez de `requests.post` a n8n, llama
`consultar_ventas(_qbo_client(), desde, hasta)` y guarda el crudo en
`VentasQbCache.raw_json` como hoy. Caché, throttle entre workers, ventana
laboral e hilo de refresco **no cambian**: siguen protegiendo contra latencia,
no contra costo. `_quickbooks_sales_enabled()` acepta el backend `qbo` sin
exigir `N8N_QB_SALES_WEBHOOK_URL`.

- [ ] **Step 1: Tests:** con backend `qbo` el refresco escribe la fila desde
      el cliente mockeado; un `QboError` deja `last_error` y conserva el crudo
      anterior; con backend `n8n` nada cambia.
- [ ] **Step 2: Implementar.**

### Task 11: Comparación en paralelo y corte

**Files:**
- Create: `scripts/comparar_ventas_qbo.py`

Script de una sola vez: trae el rango del dashboard por n8n y por API,
normaliza ambos con `_normalizar_metricas_ventas_quickbooks` y lista las
diferencias en ventas del mes, de la semana, por cliente y por producto.

- [ ] **Step 1:** correr el script en local contra producción (solo lectura)
      hasta que las diferencias sean cero o estén explicadas (por ejemplo,
      notas de crédito).
- [ ] **Step 2:** `heroku config:set QB_SALES_BACKEND=qbo`. Vigilar el
      dashboard dos días.
- [ ] **Step 3:** vaciar `N8N_QB_SALES_WEBHOOK_URL`; desactivar el workflow de
      ventas en n8n.

### Task 12: Limpieza

- [ ] Quitar de `.env.example` las variables de n8n de facturación y ventas;
      dejar solo Drive y HACCP con una nota de que son las únicas que quedan.
- [ ] Actualizar el comentario de `N8N_QB_REFRESH_INTERVAL_SEC` en `app.py`:
      el bucle ya no cuesta ejecuciones, pero sigue apagado por defecto por
      latencia.
- [ ] Bajar el plan de n8n al mínimo (JM). Drive y HACCP consumen decenas de
      ejecuciones al mes, no miles.

**Criterio de salida de la Fase 2:** el dashboard muestra las mismas cifras que
antes con n8n de ventas apagado, y n8n queda solo para Drive y HACCP.

---

## Riesgos y cómo los cubre el plan

| Riesgo | Cobertura |
|---|---|
| Refresh token caduca (100 días sin uso) o Intuit lo revoca | `QboNoConectado` con mensaje claro; `ultimo_error` visible en `/admin/quickbooks`; reconectar es un botón. |
| Dos workers refrescan a la vez y uno se queda con un token inválido | Commit inmediato en `guardar` más el reintento ante 401 de la Task 1. |
| El body del `Invoice` no coincide con lo que hacía n8n | Task 4 se escribe contra el export del workflow y se verifica en sandbox y con una sola factura real antes de abrir el grifo. |
| Duplicado de DocNumber por carrera | Reintento único ante `6240`. La decisión de numeración manual se conserva. |
| Algo falla en producción | `FACTURACION_BACKEND=n8n` y `QB_SALES_BACKEND=n8n` devuelven al camino anterior sin deploy. |
| `Currency2` no se puede escribir por API | Se prueba una vez en sandbox; si no toma, se documenta como carga manual. Ya era el caso con n8n. |
| Tokens en texto plano en la base | Riesgo aceptado (misma postura que n8n). Nunca se loguean. |
