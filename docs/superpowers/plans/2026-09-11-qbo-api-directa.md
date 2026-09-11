# QuickBooks por API directa (sin n8n) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Que la app facture y consulte facturas en QuickBooks Online hablando
directo con la API v3 de Intuit, sin pasar por n8n. Fase 1 saca de n8n la
facturación y la consulta de factura (lo que hoy bloquea el negocio). Fase 2
saca las ventas del dashboard y la fijación diaria de la tasa USD. Drive y
las alertas HACCP quedan en n8n.

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

**Estado (2026-09-11):** Fase 1 codificada y con tests en la rama
`claude/festive-goldberg-ds8ujn`: Tasks 1, 2, 3, 4, 5, 6, 7 y 7b hechas
(`utils/qbo_client.py`, `utils/qbo_factura.py`, `utils/qbo_tasa.py`,
modelo `QboConexion`, rutas `/admin/quickbooks/*`, backend `qbo` en
`facturar_pedido` y en `_obtener_factura_qbo`, comando `flask qbo-fijar-tasa`).
Pendiente: Task 8 (sandbox de punta a punta y corte a producción, necesita
las credenciales en una sesión nueva) y toda la Fase 2.

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
- [x] Tres bodies reales de n8n (XCG pesables, XCG cajas al 6 %, USD export)
      guardados en `docs/superpowers/specs/n8n-facturacion-body-*.json`. Con
      ellos la Task 4 queda definida salvo dos confirmaciones (ver ahí).
- [x] Export del workflow de facturación recibido el 2026-09-11 y guardado
      (sin el path del webhook ni el realm id) en
      `docs/superpowers/specs/n8n-facturacion-export.md` y `n8n-facturacion-nodo-codigo.js`.
- [x] Export del workflow «Fijar USD en 1.78» recibido el 2026-09-11 y
      resumido en `docs/superpowers/specs/n8n-tasa-usd-export.md`.
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
  siendo manual y compartida entre facturas y notas de crédito. La Task 5 la
  conserva y le agrega tres protecciones contra duplicados; pasar a la
  numeración automática de QBO es una decisión aparte de JM.

---

## File Structure

| Archivo | Responsabilidad |
|---|---|
| `utils/qbo_client.py` (crear) | OAuth2 de Intuit y wrapper HTTP de la API v3. Sin Flask, sin DB: recibe config y un *token store* con `cargar()`/`guardar()`. |
| `utils/qbo_factura.py` (crear) | Función pura `construir_invoice(payload, doc_number, hoy)` que arma el body del `Invoice`. Reemplaza al nodo de código de n8n. |
| `utils/qbo_tasa.py` (crear) | `asegurar_tasa_usd(client, fecha, tasa)`: lee la tasa USD→ANG de QBO para esa fecha y la fija si difiere. Reemplaza al workflow diario de n8n. |
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
| `QBO_TASA_USD` | `1.78` | Tasa USD→ANG que se fija en QBO (mismo valor que hoy usa n8n y `DASHBOARD_USD_TO_XCG_FALLBACK_RATE`). |
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
- Fuente: `docs/superpowers/specs/n8n-facturacion-export.md` y `n8n-facturacion-nodo-codigo.js` (prerrequisito)

**Interfaz:**

```python
def construir_invoice(payload: dict, doc_number: str, hoy: date) -> dict
```

Recibe **exactamente** lo que devuelve `pedido_a_json` (no se cambia el
payload: la app ya manda `currency_qbo`, `currency_display`, `exchange_rate`,
`class_ref`, `product_name` y el `tax_rate` como código de QBO). Devuelve el
body para `POST /invoice`.

Reglas, tomadas del **export del workflow de n8n** (2026-09-11, copia con el
path del webhook y el realm id tachados en
`docs/superpowers/specs/n8n-facturacion-export.md` y `n8n-facturacion-nodo-codigo.js`) y de tres bodies reales
(`docs/superpowers/specs/n8n-facturacion-body-*.json`):

| Archivo | Factura | Caso |
|---|---|---|
| `...-5879-xcg-pesables.json` | 5879, cliente 1497 | XCG, código 14 (0 %), solo pesables |
| `...-5878-xcg-cajas.json` | 5878, cliente 1497 | XCG, código 10 (6 %), atunes y aceites por cajas |
| `...-5869-usd-export.json` | 5869, cliente 1737 | USD, código 13 (Non Tax), tipo de cambio 1,78 |


El nodo de código de n8n lleva **comentarios con errores medidos en
producción** (6070, 6100, 6240, facturas 5848, 5856, 5863, 5864, 5865). Son
la parte más valiosa del export: cada uno es un test del traductor.

**Cabecera:**
- `CustomerRef.value = payload['customer_qbo_id']`.
- `DocNumber` — ver Task 5.
- `TxnDate = hoy`, `DueDate = hoy + 7`. n8n usa la fecha UTC del servidor;
  la app usa la fecha local de Curaçao, que es lo correcto.
- `SalesTermRef.value = '46'`. Constante `QBO_SALES_TERM_ID` (n8n lo tiene
  fijo; no depende del cliente).
- `GlobalTaxCalculation = 'TaxExcluded'`.
- `CurrencyRef.value = payload['currency_qbo']` y `ExchangeRate =
  payload['exchange_rate']` siempre (también en ANG con 1).
- `CustomerMemo.value` es un **texto fijo** con los datos bancarios de Jomar,
  puesto en el nodo HTTP (no en el de código):
  `"Jomar Foods, BV\nCrib nr.: 102505329\nK.V.K.: 148768\nRBC Account# 8000009000132576"`.
  Constante `QBO_CUSTOMER_MEMO`. **Las `notes` del pedido no llegan a QBO
  hoy**; se replica igual. Si JM las quiere en la factura, es un cambio aparte.
- `PrivateNote = 'PesosApp pedido {order_id}'` (nuevo, no lo manda n8n): no
  se imprime y permite rastrear duplicados desde QBO.

**URL del POST:** `invoice?minorversion=75&include=enhancedAllCustomFields`.
Sin `include=enhancedAllCustomFields` **QBO ignora `Currency2`** (medido por
JM el 2026-09-08). El cliente de la Task 1 lo agrega en `post()` cuando el
body trae `CustomField`.

**`CustomField`** (los cuatro, en este orden, siempre `Type: 'StringType'`):

| DefinitionId | Name | StringValue |
|---|---|---|
| `1` | `Currency` | `payload['currency_display']` |
| `2` | `Sales Rep` | `payload.get('sales_rep') or 'OF'`. La app no manda `sales_rep`; queda la constante. |
| `3` | `Tax ID No.` | `payload.get('tax_id') or ''` |
| `1000000003` | `Currency2` | `{'XCG': '1', 'ANG': '1', 'USD': '2'}[currency]`, por `payload['currency']`. Es una lista: 1 = XCG, 2 = USD, 3 = ANG (nunca se manda el 3). Es el campo que **se ve** en la pantalla de QBO; el `DefinitionId 1` es otro campo, invisible. |

**Líneas — la aritmética va en enteros.** QBO revalida
`Amount == UnitPrice × Qty` con redondeo media-arriba y rechaza con **6070**
si difiere en medio centavo (pedido 1334: 128,350 kg × 14,50 = 1.861,075
exactos; el `double` da 1.861,0749… y salía 1.861,07). En Python:
`Decimal` con `ROUND_HALF_UP`, sin `float` en ningún paso intermedio.
- Agrupar por `(product_qbo_id, unit_price)` en orden de aparición.
- `qty` de cada línea a **milésimas** (`Decimal(str(qty)).quantize('0.001')`),
  `unit_price` a **centavos**. `Qty` de la línea agrupada es la suma de
  milésimas; `Amount = (Qty × UnitPrice)` redondeado media-arriba a
  centavos; `UnitPrice` con dos decimales.
- `Description` = las `qty` individuales con **dos decimales**, unidas por
  tabulador (`"23.15\t23.40"`; un producto por cajas queda `"3.00"`). Es lo
  que leen `utils/factura_pdf._pesos_de_descripcion` y la trazabilidad.
- `DetailType = 'SalesItemLineDetail'`.
- `ItemRef = {value: product_qbo_id, name: descripcion}`. n8n usa
  `descripcion` (con `(Lote X)` si lo trae) como `name`; QBO resuelve el
  ítem por `value` y reescribe `name`, así que es inofensivo. Se replica.
- `TaxCodeRef.value = 'TAX'` **siempre**. La empresa está en modo US: el
  código de línea solo acepta `TAX`/`NON` (error **6100** con otro valor), y
  con `NON` la venta se caía del reporte de ventas gravadas y había que
  marcar cada línea a mano (factura 5864). El 0 % lo define el código de la
  transacción.
- `ClassRef.value`: `class_ref` de la línea si viene; si no, **detección por
  palabras clave** sobre el nombre, con la misma tabla de n8n (`classKeywords`
  del export, cinco clases). Se porta tal cual a `utils/qbo_factura.py` como
  red de seguridad: hoy hay productos sin clase en la app que salen
  clasificados gracias a esto, y quitarlo sería una regresión visible en los
  reportes por clase. Sin coincidencia, la línea va sin `ClassRef` y la app ya
  avisa («se facturaron sin clase»).

**Impuesto (`TxnTaxDetail`) — va siempre, calculado, con `TaxRateRef` fija
en `25`.** Del segundo export de JM (2026-09-11, el desplegado): el nodo
HTTP reenvía `GlobalTaxCalculation`, `TxnTaxDetail`, `CurrencyRef` y
`ExchangeRate`, y **la facturación sale correcta así**. Hechos medidos en
producción que fijan el diseño:

- Con solo `TxnTaxCodeRef`, la factura sale al 0 % (5848). Hay que mandar
  `TotalTax` y `TaxLine`.
- Sin `TxnTaxDetail`, la factura sale **sin código** y no entra en el reporte
  de OB (5865). El bloque va también al 0 %.
- `TaxRateRef` va **siempre `'25'`**, para cualquier código. No es la tasa
  que corresponde (las reales son 17 = OB 6 %, 18 = OB 9 %, 19 = Non Tax,
  25 = Local Prod): QBO la rechaza, recalcula desde `TxnTaxCodeRef` y guarda
  la correcta (5863: mandada con 25, guardada con 17 al 6 %). Mandar la
  «correcta» 17 **rompe el cálculo** y la factura sale al 0 % (5867). El
  traductor lleva este comentario al lado de la constante para que nadie lo
  «arregle».

```python
PCT_POR_CODIGO = {'10': 6, '11': 9, '13': 0, '14': 0}
TAX_RATE_REF = '25'   # siempre; ver comentario de la 5867
```

`NetAmountTaxable` = suma de `Amount` en centavos; `TotalTax = round_half_up(
neto × pct / 100)` en centavos; `TaxLine[0] = {Amount: TotalTax, DetailType:
'TaxLineDetail', TaxLineDetail: {TaxPercent, NetAmountTaxable, PercentBased:
True, TaxRateRef: {value: '25'}}}`. Un código fuera de `PCT_POR_CODIGO`
levanta `ValueError`; líneas con códigos distintos, `ValueError`.

**Tipo de cambio y modo de cálculo:** `GlobalTaxCalculation = 'TaxExcluded'`
siempre; `ExchangeRate = exchange_rate` siempre que sea distinto de 0 (n8n lo
manda si es truthy, así que en ANG viaja `1`). Los tres bodies de ejemplo son
la salida del nodo de código y, con este template, también lo que llega a
QBO, salvo el `CustomerMemo` que agrega el nodo HTTP.

**Otro hallazgo, fuera de alcance de este plan:** al leer las facturas en
QBO, la 5878 tiene 5 de 7 líneas con precio corregido a mano y un ítem
reemplazado (1305 → 1430); la 5879, una línea (19,98 → 25,30). Las listas
de precios de la app van por detrás de lo que se factura. La app ya tiene
`_comparar_precios_factura` para detectarlo; conviene que JM lo use tras
cada factura corregida, o que se automatice en un plan aparte.

- [ ] **Step 1: Tests** con los tres bodies reales como fixtures esperados
      (reconstruyendo el payload de la app que los produjo) y además los
      casos medidos en producción: 128,350 × 14,50 = 1.861,08 (6070);
      0,1 × 3 = 0,30; `TaxCodeRef` de línea siempre `TAX` (6100); bloque de
      impuesto presente al 0 % (5865) y `TaxRateRef` siempre `25` (5867);
      2.666,98 × 6 % = 160,02; `Currency2` 1/2; `CustomerMemo` fijo; clase
      por palabra clave cuando falta `class_ref`; `ValueError` si se mezclan
      impuestos o el código no está en la tabla.
- [ ] **Step 2: Implementar** como función pura. Sin Flask, sin DB, sin red.
- [ ] **Step 3:** en verde. Guardar en `tests/fixtures/qbo/` la primera
      respuesta real del sandbox para la Task 6.

### Task 5: Número de factura (`siguiente_doc_number`)

**Files:**
- Modify: `utils/qbo_factura.py`
- Modify: `app.py` (`_crear_factura_qbo`, Task 6)
- Create: `tests/fixtures/qbo/query_docnumber_invoice.json`, `..._creditmemo.json`
- Test: `tests/test_qbo_factura.py`, `tests/test_facturacion.py`

**Cómo lo hace n8n hoy** (export): dos consultas en paralelo,
`SELECT DocNumber FROM Invoice ORDER BY MetaData.CreateTime DESC MAXRESULTS 50`
y la misma sobre `CreditMemo`; toma el **mayor numérico de las dos listas**
y suma uno; si no encuentra ninguno, arranca en 5320. **Facturas y notas de
crédito comparten la secuencia**: es un dato de negocio que el diseño de
agosto no tenía y que el correlativo del reporte de OB depende de él.

**Por qué se puede duplicar** (la «carrera» que JM decidió tolerar): dos
usuarios facturan con segundos de diferencia y los dos leen el mismo máximo.
Y hay una segunda causa que el `ORDER BY CreateTime` no cubre: **el índice
de consulta de QBO tarda unos segundos en reflejar una factura recién
creada**, así que incluso en serie, dos facturas seguidas pueden leer el
mismo máximo.

**Diseño nuevo: tres capas, cada una cubre lo que la anterior no.**

```python
def siguiente_doc_number(client, ultimo_local: int | None) -> str
```

1. **QBO sigue siendo la fuente de verdad** (las notas de crédito se hacen a
   mano en QBO y consumen números que la app no ve): las dos consultas de
   n8n, tal cual, mayor numérico de ambas. Sin resultados → `QboError`;
   nunca un número inventado como el 5320.
2. **La app aporta su propio último número:** `ultimo_local` es
   `max(Pedido.doc_number_qbo)` numérico en la base de la app. Cubre el
   retraso del índice de QBO: si la app acaba de emitir la 5880 y QBO
   todavía devuelve 5879 como máxima, el siguiente es 5881 igual.
   El resultado es `max(qbo_invoice, qbo_creditmemo, ultimo_local) + 1`.
3. **Serialización entre workers:** `_crear_factura_qbo` toma un
   `pg_advisory_xact_lock(<constante>)` de Postgres al inicio de la
   transacción y lo suelta con el commit, así que dos facturaciones
   simultáneas se ponen en fila (la segunda espera uno o dos segundos y lee
   el número ya actualizado en la capa 2). En sqlite (tests) el lock es un
   no-op. A la escala de Jomar, facturar en serie no se nota.
4. **Red final:** si QBO igual responde **6240** (Duplicate Document
   Number), se recalcula y se reintenta **una vez**.

Con las capas 2 y 3 el duplicado solo puede venir de una nota de crédito
creada a mano en QBO en los mismos segundos, y para eso está la 4.

**Alternativa que queda en manos de JM:** apagar «Custom transaction
numbers» en QBO y dejar que QuickBooks numere solo. Elimina las consultas y
la carrera de raíz, y la app lee el `DocNumber` de la respuesta como ya hace.
Hay que verificar en sandbox que las notas de crédito sigan compartiendo la
secuencia con las facturas como hoy; si lo hacen, es la opción más simple y
el plan se reduce a la capa 4. Cambia una decisión tomada
(`docnumber-carrera-decision`), así que la toma JM, no este plan.

- [ ] **Step 1: Tests:** mayor numérico entre facturas y notas de crédito
      mezcladas; `ultimo_local` mayor que QBO gana; ignora DocNumbers no
      numéricos; sin resultados en ninguna de las dos → `QboError`; el
      reintento por 6240 pide un número nuevo (Task 6).
- [ ] **Step 2: Implementar** `siguiente_doc_number` (pura, recibe el
      cliente) y el helper `_ultimo_doc_number_local()` en `app.py`.
- [ ] **Step 3:** el advisory lock va en `_crear_factura_qbo` (Task 6), con
      un test que verifica que en Postgres se emite `pg_advisory_xact_lock` y
      en sqlite no se emite nada.

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
2. `doc = siguiente_doc_number(client, _ultimo_doc_number_local())`, dentro
   del advisory lock (Task 5).
3. `body = construir_invoice(payload, doc, hoy_curazao)`.
4. `client.post('invoice', body, params={'include': 'enhancedAllCustomFields'})`;
   ante `Fault` con código `6240`, repetir los pasos 2 y 3 una vez.
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

### Task 7b: Tasa USD→ANG fija en QBO (`utils/qbo_tasa.py`)

**Files:**
- Create: `utils/qbo_tasa.py`
- Modify: `app.py` (`_crear_factura_qbo`, comando CLI)
- Create: `tests/fixtures/qbo/exchangerate.json`
- Test: `tests/test_qbo_tasa.py`

**Qué hace n8n hoy** (`n8n-tasa-usd-export.md`): todos los días a las 05:00
lee la tasa USD→ANG de QBO para hoy y mañana (UTC) y la fija en 1,78 con el
`SyncToken` leído. Existe para que las facturas en USD, y cualquier
transacción hecha a mano en QBO ese día, se contabilicen a 1,78 y no a la
tasa del día de Intuit.

**Diseño:**

```python
def asegurar_tasa_usd(client, fecha: date, tasa: Decimal) -> bool
```

`GET exchangerate?sourcecurrencycode=USD&asofdate={fecha}`; si `Rate` ya es
`tasa`, no hace nada y devuelve `False`; si no, `POST exchangerate` con
`{SourceCurrencyCode: 'USD', TargetCurrencyCode: 'ANG', Rate, AsOfDate}` y el
`SyncToken` si vino, y devuelve `True`. Idempotente: se puede llamar mil
veces.

Se usa en dos lugares:
1. **Antes de crear una factura USD** en `_crear_factura_qbo`, con el
   `TxnDate` de la factura (fecha local de Curaçao, así que la doble fecha
   «hoy y mañana» de n8n ya no hace falta). Best-effort: si falla, se loguea
   y se factura igual, porque la factura lleva su propio `ExchangeRate`.
2. **Comando `flask qbo-fijar-tasa`** que fija hoy y mañana, para correrlo a
   diario desde el add-on **Heroku Scheduler** (gratis, un dyno de un
   minuto). Cubre las transacciones hechas a mano en QBO, que es lo que la
   llamada 1 no cubre. Se activa en la Task 8 y ahí se apaga el workflow de
   n8n.

- [ ] **Step 1: Tests:** tasa ya correcta → no hace POST; tasa distinta →
      POST con `SyncToken`; sin tasa previa → POST sin `SyncToken`; en la
      factura USD se llama con el `TxnDate` y un fallo no impide facturar;
      en una factura ANG no se llama.
- [ ] **Step 2: Implementar** módulo, llamada y comando.

### Task 8: Config, documentación y corte a producción

**Files:**
- Modify: `.env.example`, `docs/superpowers/specs/2026-08-28-factura-qbo-sin-correcciones-design.md`, `HEROKU_DEBUG.md`

- [ ] **Step 1:** variables nuevas en `.env.example` con comentarios; nota en
      el spec del 2026-08-28: «el nodo de código de n8n queda reemplazado por
      `utils/qbo_factura.py`; el export vive en `n8n-facturacion-export.md` y `n8n-facturacion-nodo-codigo.js`».
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
- [ ] **Step 5:** instalar Heroku Scheduler, programar `flask qbo-fijar-tasa`
      a diario a las 05:00 y, tras verificar un día que la tasa quedó en
      1,78, desactivar el workflow «Fijar USD en 1.78» en n8n.

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
