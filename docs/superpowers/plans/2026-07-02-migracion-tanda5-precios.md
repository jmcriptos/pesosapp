# Migración Tanda 5 (Precios) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Migrar las 7 pantallas de `/precios/*` del tema oscuro legacy al design system claro, en un solo push final, arreglando dos bugs reales encontrados en el camino (carga masiva CSV rota, modal de precios de cliente roto) y eliminando un template huérfano.

**Architecture:** Mismo mecanismo que la Tanda 1 (`gestion.css`): un CSS nuevo `static/css/precios.css` scopeado a `body[data-precios-screen]` (seteado por `base.html` para rutas `/precios/*`), reutilizando los tokens claros + neutralización de `<form>` + escudo dark-mode ya verificados en `gestion.css`. Los componentes estructurales son nuevos (`.precios-hub-*`, `.precios-list-*`, `.precios-table`, `.precios-modal`) porque el contenido es distinto al patrón GESTIÓN de lista de filas (hub de tarjetas, tabla editable tipo hoja de cálculo, formularios con cálculo en vivo). Se reutilizan `.mobile-card`/`.mobile-form-*` (globales) donde el patrón coincide exactamente (formularios simples tipo `lista_form.html`).

**Tech Stack:** Flask/Jinja2, CSS vanilla, JS vanilla (se elimina jQuery de `precios/clientes.html`, único remanente en esta tanda), pytest.

**Spec:** `docs/superpowers/specs/2026-07-01-migracion-lote-oscuro-design.md` (Tanda 5, antes numerada 5, ver corrección 2026-07-02 sobre Etiquetas)

---

**Contexto crítico para el implementador (no lo sabes si no has leído el repo):**

- El tema global es OSCURO (`dark-theme.css` con `!important`, y un `@media (prefers-color-scheme: dark)` en `styles.min.css` con especificidad inflada por un `:root` sin cerrar). Las pantallas claras re-aclaran solo su contenido con CSS scopeado a un `data-*` del body, cargado DESPUÉS en la cascada. El mecanismo ya está verificado en producción en `static/css/gestion.css` — **léelo primero** (`/Users/josedasilva/Projects/pesosapp/static/css/gestion.css`) y copia su estructura, incluida la sección 6 (escudo dark-mode) tal cual, adaptando el prefijo de atributo.
- `static/js/base.js` (servido como `base.min.js`) define `window.escapeHtml`, `window.mostrarMensaje(msg, tipo)`, y parchea `window.fetch` para inyectar `X-CSRFToken` en peticiones no-GET same-origin. **`{% block scripts %}` se renderiza ANTES que `<script src=base.min.js>`** en `base.html` — nunca llames a `window.mostrarMensaje` en tiempo de parseo; usa el patrón `aviso()` (ver `templates/clientes.html` líneas 94-98) que además hace fallback a `alert()` si `base.min.js` está en caché vieja.
- Patrón de creación con doble-submit-guard + fail-closed-delete: copia EXACTAMENTE los handlers de `templates/clientes.html` (ya revisado y aprobado en Tanda 1) — deshabilitar el botón submit al entrar al handler, re-habilitarlo en error/catch ANTES de mostrar el aviso, y en deletes tratar como éxito SOLO `res.message` (nunca asumir éxito por ausencia de `res.error`).
- Tras editar `static/js/base.js` SIEMPRE ejecutar `cp static/js/base.js static/js/base.min.js`. En esta tanda no debería hacer falta tocar `base.js` (no hay helpers nuevos que compartir), pero si algún grupo lo requiere, seguir esa convención.
- Los tests se corren `.venv/bin/python -m pytest ... -q` SIN forzar `DATABASE_URL` de archivo (el propio test setea sqlite memory).
- Trabajamos en `main` local; **NO hacer `git push`** durante la ejecución de los grupos — el push final (deploy a Heroku) lo hace el humano tras el cierre de tanda, con OK explícito.
- **Dos bugs reales a corregir como parte de esta tanda** (no son mejoras opcionales, son funcionalidad rota hoy):
  1. **Carga masiva CSV** (`precios/carga_masiva.html`): el form hace submit nativo (`<form method="POST" enctype="multipart/form-data">`) a `/precios/procesar-csv`, que SIEMPRE responde JSON (`jsonify(...)`) — el navegador termina navegando y mostrando JSON crudo. Además el template espera variables (`resultado.total_registros`, `resultado.detalle_errores`, etc.) que la ruta `carga_masiva_precios()` NUNCA pasa al render, y aunque las pasara no coinciden con la forma real de la respuesta de `/precios/procesar-csv` (`{success, mensaje, resultados: {procesados, errores, warnings, detalles}}`). El link "Descargar Log" apunta a `url_for('descargar_log', ...)`, endpoint que no existe (lanzaría `BuildError` si esa rama de código alguna vez se alcanzara). Fix: submit por fetch, renderizar la forma REAL de la respuesta, quitar "Descargar Log", corregir el link de plantilla a la ruta real `/precios/descargar-plantilla/<tipo>`.
  2. **Modal "ver precios de cliente"** (`precios/clientes.html`): el JS hace `precio.precio_jomar.toFixed(2)` y `precio.producto_nombre`, pero `/api/precios/cliente/<id>/productos` devuelve objetos con `nombre` (no `producto_nombre`), `precio_base`, `margen_jomar`, `margen_retail` — **NUNCA** `precio_jomar`/`precio_retail` calculados. Hoy esto lanza `TypeError: undefined is not a function` a mitad del `forEach`, dejando la tabla del modal a medio renderizar. Fix: usar `precio.nombre`, calcular `precio_base * margen_jomar` / `precio_base * margen_retail` en el JS.
- **Código muerto confirmado**: `templates/precios/pedido_form.html` (654 líneas) no lo renderiza ninguna ruta — verificado con `grep -n "pedido_form" app.py`: las únicas dos llamadas (`nuevo_pedido()`, `editar_pedido()`) hacen `render_template('pedido_form.html', ...)` **sin el prefijo `precios/`**, que Jinja resuelve contra `templates/pedido_form.html` (446 líneas, ya migrado, en uso real). El archivo dentro de `precios/` es un duplicado huérfano de una versión antigua. Se borra en el Grupo A.
- Los routes de crear/editar **Lista de Precios** (`nueva_lista_precio`, `editar_lista_precio`) usan `flash('...', 'success')` + `redirect()`, NO JSON — el formulario de `lista_form.html` debe seguir siendo un POST nativo (sin `fetch`/`preventDefault`). El mensaje aparece solo via el stack global `.app-flash-stack` que ya renderiza `base.html` (confirmado: el mismo mecanismo que usan hoy `editar_cliente`/`editar_producto` sin necesitar código extra) — no crear un `#flash-message` local en esa página.
- Modelos usados: `ListaPrecio` (id, nombre, descripcion, es_default, activa, fecha_creacion, `precios_productos` relationship, `clientes` relationship vía `ClienteListaPrecio`), `PrecioProducto` (lista_precio_id, producto_id, precio_base, margen_jomar, margen_retail, precio_jomar, precio_retail — calculados server-side por `calcular_precios()`), `PrecioClienteProducto` (mismos campos + cliente_id), `ClienteListaPrecio` (cliente_id, lista_precio_id, activa, fecha_asignacion). `Producto.proveedor` ya existe (usado en Tanda 1).
- Tom Select: para activarlo en un `<select>` basta agregar la clase `ts-select` (+ opcional `data-ts-placeholder="..."`) — el init global en `base.html` lo detecta solo.

**Files:**

| Acción | Path | Responsabilidad |
|---|---|---|
| Delete | `templates/precios/pedido_form.html` | Código muerto confirmado |
| Create | `static/css/precios.css` | Scope claro + componentes estructurales de Precios (hub, list-card, table, modal) |
| Create | `tests/test_precios_ui.py` | Smoke tests de infraestructura + markup por pantalla (sueltos: ids/data-attrs) |
| Modify | `templates/base.html` | body attr `data-precios-screen` + link condicional a `precios.css` para rutas `/precios` |
| Modify | `templates/precios/index.html` | Hub claro |
| Modify | `templates/precios/listas.html` | Grid de tarjetas claro + fix fail-closed delete |
| Modify | `templates/precios/lista_form.html` | Form claro (`.mobile-card`/`.mobile-form-*`), sin JS de submit |
| Modify | `templates/precios/carga_masiva.html` | CAPTURA claro + **fix bug fetch/JSON** |
| Modify | `templates/precios/lista_productos.html` | Tabla editable clara (mantiene JS vanilla existente, migrado a `aviso()`) |
| Modify | `templates/precios/clientes.html` | Form+tabla+modal claros, jQuery→vanilla, **fix bug modal** |
| Modify | `templates/precios/cliente_producto.html` | Form+tabla claros, `mostrarMensaje` local → `aviso()` |

---

### Task 1: Tests de infraestructura (fallando)

**Files:**
- Create: `tests/test_precios_ui.py`

- [ ] **Step 1: Escribir el archivo de tests con los tests de infraestructura y de cada pantalla**

```python
"""Smoke tests — migración de Precios (Tanda 5) al design system claro.
Spec: docs/superpowers/specs/2026-07-01-migracion-lote-oscuro-design.md

Asserts sobre ids/data-attrs, no markup exacto (evita el test rot documentado
en test_dashboard_kpis/test_etiquetas).
"""

import os
import pytest

os.environ.setdefault("SECRET_KEY", "test-secret")
os.environ.setdefault("FLASK_ENV", "testing")
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

from app import app as flask_app, db as _db


@pytest.fixture
def app():
    flask_app.config.update(
        TESTING=True,
        WTF_CSRF_ENABLED=False,
        SQLALCHEMY_DATABASE_URI="sqlite:///:memory:",
    )
    with flask_app.app_context():
        _db.create_all()
        from app import (
            Rol, Territorio, Vendedor, Cliente, Producto,
            ListaPrecio, PrecioProducto, PrecioClienteProducto, ClienteListaPrecio,
        )

        rol = Rol(nombre="super_admin", descripcion="Admin")
        _db.session.add(rol)
        territorio = Territorio(nombre="test", descripcion="Test")
        _db.session.add(territorio)
        _db.session.flush()

        vendedor = Vendedor(
            username="admin",
            email="admin@test.com",
            nombre_completo="Admin Test",
            rol_id=rol.id,
            territorio_id=territorio.id,
            activo=True,
        )
        vendedor.set_password("testpass")
        _db.session.add(vendedor)

        cliente = Cliente(nombre="Cliente Precios Uno", moneda="XCG")
        producto = Producto(nombre="Producto Precios Uno", proveedor="Prov Test", tax_rate=10)
        _db.session.add(cliente)
        _db.session.add(producto)
        _db.session.flush()

        lista_default = ListaPrecio(nombre="Lista General", descripcion="Default", es_default=True, activa=True)
        lista_custom = ListaPrecio(nombre="Lista Premium", descripcion="Custom", es_default=False, activa=True)
        _db.session.add(lista_default)
        _db.session.add(lista_custom)
        _db.session.flush()

        precio_prod = PrecioProducto(
            lista_precio_id=lista_default.id, producto_id=producto.id,
            precio_base=10.0, margen_jomar=1.0, margen_retail=1.2,
        )
        precio_prod.calcular_precios()
        _db.session.add(precio_prod)

        precio_esp = PrecioClienteProducto(
            cliente_id=cliente.id, producto_id=producto.id,
            precio_base=9.0, margen_jomar=1.0, margen_retail=1.2,
        )
        precio_esp.calcular_precios()
        _db.session.add(precio_esp)

        _db.session.add(ClienteListaPrecio(cliente_id=cliente.id, lista_precio_id=lista_custom.id, activa=True))

        _db.session.commit()

        yield flask_app
        _db.drop_all()


@pytest.fixture
def logged_client(app):
    client = app.test_client()
    client.post(
        "/login",
        data={"username": "admin", "password": "testpass"},
        follow_redirects=True,
    )
    return client


def _lista_default_id(app):
    with app.app_context():
        from app import ListaPrecio
        return ListaPrecio.query.filter_by(es_default=True).first().id


# ---------------------------------------------------------------------------
# Infraestructura compartida (base.html + precios.css)
# ---------------------------------------------------------------------------

PRECIOS_PATHS = [
    "/precios",
    "/precios/listas",
    "/precios/listas/nueva",
    "/precios/clientes",
    "/precios/cliente-producto",
    "/precios/carga-masiva",
]


@pytest.mark.parametrize("path", PRECIOS_PATHS)
def test_precios_route_returns_200(logged_client, path):
    response = logged_client.get(path)
    assert response.status_code == 200, f"{path} returned {response.status_code}"


@pytest.mark.parametrize("path", PRECIOS_PATHS)
def test_precios_css_is_linked(logged_client, path):
    response = logged_client.get(path)
    assert b"css/precios.css" in response.data, f"precios.css link missing from {path}"


@pytest.mark.parametrize("path", PRECIOS_PATHS)
def test_body_has_precios_screen_attr(logged_client, path):
    response = logged_client.get(path)
    assert b'data-precios-screen="1"' in response.data, (
        f"data-precios-screen missing from {path} body"
    )


@pytest.mark.parametrize("path", ["/dashboard", "/pedidos", "/clientes", "/productos"])
def test_non_precios_routes_lack_precios_attrs(logged_client, path):
    response = logged_client.get(path)
    assert b'data-precios-screen="1"' not in response.data
    assert b"css/precios.css" not in response.data


def test_precios_lista_productos_route(logged_client, app):
    lista_id = _lista_default_id(app)
    response = logged_client.get(f"/precios/listas/{lista_id}/productos")
    assert response.status_code == 200
    assert b'data-precios-screen="1"' in response.data
    assert b"css/precios.css" in response.data


# ---------------------------------------------------------------------------
# Hub (precios/index.html)
# ---------------------------------------------------------------------------


def test_hub_patron_claro(logged_client):
    html = logged_client.get("/precios").data
    assert b"precios-hub-grid" in html
    assert b"Lista General" not in html  # el hub no lista nombres, solo cuenta
    assert b"listas" in html  # contador "N listas"


# ---------------------------------------------------------------------------
# Listas (precios/listas.html)
# ---------------------------------------------------------------------------


def test_listas_patron_claro(logged_client):
    html = logged_client.get("/precios/listas").data
    assert b'id="btn-nueva-lista"' in html
    assert b"Lista General" in html
    assert b"Lista Premium" in html
    assert b"precios-list-card" in html


def test_listas_sin_legacy(logged_client):
    html = logged_client.get("/precios/listas").data
    assert b"#141820" not in html, "color legacy oscuro no debe quedar inline"


# ---------------------------------------------------------------------------
# Lista form (precios/lista_form.html)
# ---------------------------------------------------------------------------


def test_lista_form_nueva_patron_claro(logged_client):
    html = logged_client.get("/precios/listas/nueva").data
    assert b"mobile-card" in html
    assert b'name="nombre"' in html
    assert b'name="descripcion"' in html


def test_lista_form_editar_patron_claro(logged_client, app):
    lista_id = _lista_default_id(app)
    html = logged_client.get(f"/precios/listas/{lista_id}/editar").data
    assert b"mobile-card" in html
    assert b"Lista por defecto" in html or b"lista por defecto" in html.lower()


# ---------------------------------------------------------------------------
# Lista productos — tabla editable (precios/lista_productos.html)
# ---------------------------------------------------------------------------


def test_lista_productos_patron_claro(logged_client, app):
    lista_id = _lista_default_id(app)
    html = logged_client.get(f"/precios/listas/{lista_id}/productos").data
    assert b"precios-table" in html
    assert b"Producto Precios Uno" in html
    assert b'id="btn-guardar-todo"' in html
    assert b'id="btn-agregar-producto"' in html


# ---------------------------------------------------------------------------
# Precios por cliente (precios/clientes.html)
# ---------------------------------------------------------------------------


def test_precios_clientes_patron_claro(logged_client):
    html = logged_client.get("/precios/clientes").data
    assert b'id="form-asignar-lista"' in html
    assert b"Cliente Precios Uno" in html
    assert b'id="modal-precios-cliente"' in html


def test_precios_clientes_sin_jquery(logged_client):
    html = logged_client.get("/precios/clientes").data
    assert b"code.jquery.com" not in html, "precios/clientes.html ya no debe cargar jQuery CDN"


# ---------------------------------------------------------------------------
# Cliente-producto (precios/cliente_producto.html)
# ---------------------------------------------------------------------------


def test_cliente_producto_patron_claro(logged_client):
    html = logged_client.get("/precios/cliente-producto").data
    assert b'id="form-precio-especifico"' in html
    assert b"Cliente Precios Uno" in html
    assert b"Producto Precios Uno" in html


# ---------------------------------------------------------------------------
# Carga masiva (precios/carga_masiva.html)
# ---------------------------------------------------------------------------


def test_carga_masiva_patron_claro(logged_client):
    html = logged_client.get("/precios/carga-masiva").data
    assert b'id="form-carga-masiva"' in html
    assert b"Descargar Log" not in html, "link roto (endpoint inexistente) debe eliminarse"


# ---------------------------------------------------------------------------
# Código muerto eliminado
# ---------------------------------------------------------------------------


def test_pedido_form_precios_no_existe():
    import os
    path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
        "templates", "precios", "pedido_form.html",
    )
    assert not os.path.exists(path), "templates/precios/pedido_form.html debía borrarse (código muerto)"
```

- [ ] **Step 2: Correr los tests y verificar que fallan los que dependen de código aún no escrito**

Run: `.venv/bin/python -m pytest tests/test_precios_ui.py -q`
Expected: los tests de rutas/200 y los negativos de `/dashboard`/`/pedidos`/`/clientes`/`/productos` PASAN; todos los demás (css linked, body attr, markup por pantalla, sin-jquery, pedido_form no existe) FALLAN. Anota el conteo exacto para comparar en el siguiente checkpoint.

---

### Task 2: Eliminar código muerto + fundación de `base.html`

**Files:**
- Delete: `templates/precios/pedido_form.html`
- Modify: `templates/base.html`

- [ ] **Step 1: Borrar el template huérfano**

```bash
git rm templates/precios/pedido_form.html
```

- [ ] **Step 2: Agregar el link condicional a precios.css**

En `templates/base.html`, localizar el bloque condicional de `gestion.css` (agregado en la Tanda 1, cerca de la línea 110). Inmediatamente DESPUÉS de ese bloque, agregar:

```jinja
{% if request.path.startswith('/precios') %}
    <link rel="stylesheet" href="{{ url_for('static', filename='css/precios.css') }}">
{% endif %}
```

- [ ] **Step 3: Agregar data-precios-screen al body**

En el `body_attrs` (la misma línea larga con la cadena de `{% elif %}`), agregar un nuevo `elif` al final, antes del `{% endif %}` de cierre:

```jinja
{% elif request.path.startswith('/precios') %} data-precios-screen="1"{% endif %}
```

(Debe quedar encadenado después del `elif` de `data-gestion-screen` de la Tanda 1, mismo patrón.)

- [ ] **Step 4: Correr los tests de infraestructura**

Run: `.venv/bin/python -m pytest tests/test_precios_ui.py -q`
Expected: pasan `test_precios_route_returns_200` (ya pasaba), `test_precios_css_is_linked` (ahora SÍ, aunque el archivo `precios.css` todavía no existe — el link en el HTML es lo que se testea, no el 200 del estático), `test_body_has_precios_screen_attr`, `test_non_precios_routes_lack_precios_attrs`, `test_precios_lista_productos_route`, y `test_pedido_form_precios_no_existe`. Los tests de markup específico por pantalla siguen fallando (se resuelven en los grupos siguientes).

- [ ] **Step 5: Commit**

```bash
git add tests/test_precios_ui.py templates/base.html
git commit -m "feat(precios): fundación tanda 5 — scope claro data-precios-screen + borra pedido_form.html huérfano"
```

---

### Task 3: `static/css/precios.css`

**Files:**
- Create: `static/css/precios.css`

- [ ] **Step 1: Crear el archivo completo**

```css
/* =============================================================================
   PesosApp · precios.css — pantallas de Precios migradas al design system claro
   Spec: docs/superpowers/specs/2026-07-01-migracion-lote-oscuro-design.md

   Mismo mecanismo que gestion.css (Tanda 1): el tema global sigue siendo
   oscuro (dark-theme.css, overrides con !important) mientras duren las
   tandas. Aquí re-aclaramos SOLO el contenido de las pantallas marcadas por
   base.html con body[data-precios-screen]. Carga después de dark-theme.css
   en la cascada. Servido directo (sin minificar), como gestion.css.
   Convención: reglas con prefijo body[data-precios-screen] = pelean
   especificidad contra dark-theme.css; sin prefijo = layout puro sin conflicto.
   ============================================================================= */

/* ── 1 · Fondo del área de contenido ─────────────────────────────────────── */
body[data-precios-screen] .app-content,
body[data-precios-screen] .mobile-form-container {
  background: #f8fafc !important;
  background-image: none !important;
}

/* ── 2 · Tokens claros scopeados al wrapper de contenido.
      NUNCA al body (lección de la firma/canvas en pantallas ops). ────────── */
body[data-precios-screen] .precios-wrap,
body[data-precios-screen] .mobile-form-container {
  --color-bg: #ffffff;
  --color-bg-elevated: #ffffff;
  --color-bg-subtle: #f8fafc;
  --color-surface: #ffffff;
  --color-surface-muted: #f1f5f9;
  --color-text: #0f172a;
  --color-text-muted: #475569;
  --color-text-subtle: #94a3b8;
  --color-border: #e2e8f0;
  --color-border-subtle: #eef2f7;
  --color-success-soft: #dcfce7; --color-success-soft-fg: #166534;
  --color-warning-soft: #fef9c3; --color-warning-soft-fg: #854d0e;
  --color-danger-soft:  #fee2e2; --color-danger-soft-fg:  #991b1b;
  --color-info-soft:    #e0f2fe; --color-info-soft-fg:    #075985;
  --color-primary-soft: #e0e7ff; --color-primary-soft-fg: #3730a3;
  color: #0f172a;
}

/* ── 3 · Neutralizar el "recuadro" genérico de <form> ────────────────────── */
body[data-precios-screen] .precios-wrap form,
body[data-precios-screen] .mobile-form-container form {
  background: transparent !important;
  box-shadow: none !important;
  padding: 0 !important;
  border: 0 !important;
  border-radius: 0 !important;
}

/* ── 4 · Reverts de dark-theme para .mobile-* dentro del scope (idéntico a
      gestion.css sección 4 — lista_form.html reutiliza estos componentes) ── */
body[data-precios-screen] .mobile-card {
  background: #ffffff !important;
  box-shadow: 0 10px 32px -12px rgba(15, 23, 42, 0.08) !important;
  border: 1px solid #e2e8f0 !important;
}
body[data-precios-screen] .mobile-card-body { color: #0f172a !important; }
body[data-precios-screen] .mobile-card-header {
  background: #f8fafc !important;
  color: #0f172a !important;
  border-bottom: 1px solid #e2e8f0 !important;
}
body[data-precios-screen] .mobile-form-label,
body[data-precios-screen] .mobile-checkbox-label { color: #475569 !important; }
body[data-precios-screen] .mobile-form-control,
body[data-precios-screen] .precios-wrap input,
body[data-precios-screen] .precios-wrap select,
body[data-precios-screen] .precios-wrap textarea,
body[data-precios-screen] .mobile-form-container input,
body[data-precios-screen] .mobile-form-container select,
body[data-precios-screen] .mobile-form-container textarea {
  background: #ffffff !important;
  border-color: #e2e8f0 !important;
  color: #0f172a !important;
}
body[data-precios-screen] .precios-wrap input::placeholder,
body[data-precios-screen] .mobile-form-container input::placeholder {
  color: #94a3b8 !important;
}
body[data-precios-screen] .mobile-btn-secondary {
  background: #ffffff !important;
  color: #0f172a !important;
  border: 1px solid #e2e8f0 !important;
}

/* dark-theme.css además fija color en TAGS genéricos sin scope y SIN
   !important (`strong{color:#f1f5f9}`, `p{color:#94a3b8}`,
   `a{color:#60a5fa}`, `small{color:#94a3b8}`). Como esas reglas matchean
   directo al elemento hijo (ej. <strong> dentro de un <td>), ganan sobre el
   `color` heredado del padre aunque el padre tenga !important — la herencia
   no hereda el !important, solo el valor. Se revierten explícitamente los 4
   tags dentro de las tres raíces de contenido claro (.precios-wrap,
   .mobile-form-container, .precios-modal — el modal vive FUERA de
   .precios-wrap en el DOM). No se tocan los que ya tienen su propio color
   vía clase (.precios-sub, .precios-list-meta, .precios-chip-*, etc. —
   esos ganan por especificidad de clase, sin necesidad de !important aquí). */
body[data-precios-screen] .precios-wrap strong,
body[data-precios-screen] .mobile-form-container strong,
body[data-precios-screen] .precios-modal strong {
  color: inherit !important;
}
body[data-precios-screen] .precios-wrap p,
body[data-precios-screen] .mobile-form-container p,
body[data-precios-screen] .precios-modal p {
  color: inherit !important;
}
body[data-precios-screen] .precios-wrap small,
body[data-precios-screen] .mobile-form-container small,
body[data-precios-screen] .precios-modal small {
  color: #64748b !important;
}
body[data-precios-screen] .precios-wrap a:not([class]),
body[data-precios-screen] .mobile-form-container a:not([class]),
body[data-precios-screen] .precios-modal a:not([class]) {
  color: #2563eb !important;
}

/* Tom Select: dark-theme.css lo estila sin scope y con !important (pinta
   el control y el dropdown de negro). El dropdown se monta con
   dropdownParent:'body' (base.html) — sigue siendo descendiente de
   body[data-precios-screen], así que el scope alcanza igual. Mismo patrón
   ya usado en etiquetas_form.css. */
body[data-precios-screen] .ts-wrapper .ts-control,
body[data-precios-screen] .ts-wrapper.single .ts-control,
body[data-precios-screen] .ts-wrapper.multi .ts-control {
  background: #ffffff !important;
  color: #0f172a !important;
  border: 1px solid #e2e8f0 !important;
  border-radius: 10px !important;
}
body[data-precios-screen] .ts-wrapper.focus .ts-control,
body[data-precios-screen] .ts-wrapper.single.focus .ts-control,
body[data-precios-screen] .ts-wrapper.multi.focus .ts-control {
  background: #ffffff !important;
  border-color: #2563eb !important;
  box-shadow: 0 0 0 3px rgba(37, 99, 235, 0.16) !important;
}
body[data-precios-screen] .ts-control input,
body[data-precios-screen] .ts-wrapper.single .ts-control input {
  color: #0f172a !important;
}
body[data-precios-screen] .ts-control input::placeholder,
body[data-precios-screen] .ts-wrapper .ts-control > input::placeholder,
body[data-precios-screen] .ts-wrapper.single .ts-control input::placeholder {
  color: #94a3b8 !important;
}
body[data-precios-screen] .ts-control .item,
body[data-precios-screen] .ts-wrapper.single .ts-control .item {
  color: #0f172a !important;
}
body[data-precios-screen] .ts-dropdown,
body[data-precios-screen] .ts-dropdown.single,
body[data-precios-screen] .ts-dropdown.multi {
  background: #ffffff !important;
  color: #0f172a !important;
  border: 1px solid #e2e8f0 !important;
  box-shadow: 0 20px 48px -16px rgba(15, 23, 42, 0.18) !important;
}
body[data-precios-screen] .ts-dropdown .option,
body[data-precios-screen] .ts-dropdown .ts-dropdown-content .option {
  background: #ffffff !important;
  color: #0f172a !important;
  border-bottom-color: #f1f5f9 !important;
}
body[data-precios-screen] .ts-dropdown .option:hover,
body[data-precios-screen] .ts-dropdown .option.active,
body[data-precios-screen] .ts-dropdown .ts-dropdown-content .option:hover,
body[data-precios-screen] .ts-dropdown .ts-dropdown-content .option.active {
  background: #eef4ff !important;
  color: #2563eb !important;
}

/* ── 5 · Layout base ──────────────────────────────────────────────────────── */
.precios-wrap {
  display: flex;
  flex-direction: column;
  gap: 16px;
  max-width: 1200px;
  margin: 0 auto;
  padding: 16px 14px 90px;
}
body[data-precios-screen] .precios-title {
  margin: 0;
  font-size: 1.4rem;
  font-weight: 800;
  letter-spacing: -0.02em;
  color: #0f172a;
}
body[data-precios-screen] .precios-sub {
  color: #64748b;
  font-size: 0.9rem;
  margin: 4px 0 0;
}
.precios-page-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 16px;
  flex-wrap: wrap;
}

/* ── 6 · Hub (precios/index.html) ────────────────────────────────────────── */
.precios-hub-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 14px;
}
body[data-precios-screen] .precios-hub-card {
  background: #ffffff;
  border: 1px solid #e2e8f0;
  border-radius: 18px;
  padding: 24px 20px;
  text-align: center;
  text-decoration: none;
  color: #0f172a;
  box-shadow: 0 10px 32px -12px rgba(15, 23, 42, 0.08);
  transition: transform 0.15s ease, box-shadow 0.15s ease;
}
body[data-precios-screen] .precios-hub-card:hover {
  transform: translateY(-2px);
  box-shadow: 0 16px 40px -14px rgba(15, 23, 42, 0.14);
  color: #0f172a;
}
body[data-precios-screen] .precios-hub-icon {
  font-size: 2rem;
  color: #2563eb;
  margin-bottom: 12px;
}
body[data-precios-screen] .precios-hub-card h3 {
  margin: 0 0 6px;
  font-size: 1.05rem;
  color: #0f172a;
}
body[data-precios-screen] .precios-hub-card p {
  margin: 0 0 10px;
  color: #64748b;
  font-size: 0.85rem;
  line-height: 1.4;
}
@media (max-width: 640px) {
  .precios-hub-grid { grid-template-columns: 1fr; }
}

/* ── 7 · Grid de tarjetas (precios/listas.html) ──────────────────────────── */
.precios-list-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
  gap: 14px;
}
body[data-precios-screen] .precios-list-card {
  background: #ffffff;
  border: 1px solid #eef2f7;
  border-left: 4px solid #2563eb;
  border-radius: var(--radius-xl, 20px);
  padding: 18px 20px;
  box-shadow: 0 10px 32px -12px rgba(15, 23, 42, 0.08);
}
.precios-list-card-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 8px;
  margin-bottom: 10px;
}
body[data-precios-screen] .precios-list-card-header h3 {
  margin: 0;
  font-size: 1.05rem;
  color: #0f172a;
  flex: 1;
}
body[data-precios-screen] .precios-list-desc {
  color: #64748b;
  font-size: 0.88rem;
  margin: 0 0 4px;
}
body[data-precios-screen] .precios-list-meta {
  color: #94a3b8;
  font-size: 0.78rem;
}
.precios-list-stats {
  display: flex;
  gap: 16px;
  margin: 12px 0;
  padding: 10px 12px;
  background: #f8fafc;
  border-radius: 10px;
  border: 1px solid #eef2f7;
}
body[data-precios-screen] .precios-stat-item {
  display: flex;
  align-items: center;
  gap: 6px;
  color: #64748b;
  font-size: 0.82rem;
}
body[data-precios-screen] .precios-stat-item i { color: #2563eb; }
body[data-precios-screen] .precios-stat-value { color: #0f172a; font-weight: 700; }
.precios-list-actions {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}
body[data-precios-screen] .precios-chip-action {
  padding: 6px 12px;
  border-radius: 8px;
  font-size: 0.78rem;
  font-weight: 600;
  text-decoration: none;
  display: inline-flex;
  align-items: center;
  gap: 5px;
  border: 1px solid transparent;
  cursor: pointer;
}
body[data-precios-screen] .precios-chip-primary { background: #e0e7ff; color: #3730a3; }
body[data-precios-screen] .precios-chip-edit { background: #fef9c3; color: #854d0e; }
body[data-precios-screen] .precios-chip-danger { background: #fee2e2; color: #991b1b; }

/* Botones de icono en filas de tabla (equivalente propio de .gestion-icon-btn:
   ese componente vive en gestion.css scopeado a body[data-gestion-screen], que
   NO aplica en estas pantallas — se define aquí para no depender de otro CSS). */
body[data-precios-screen] .precios-icon-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 36px;
  height: 36px;
  border-radius: 10px;
  border: 1px solid transparent;
  cursor: pointer;
  font-size: 0.88rem;
  transition: background 0.15s ease, color 0.15s ease;
}
body[data-precios-screen] .precios-icon-edit { background: #eef4ff !important; color: #2b7cff !important; }
body[data-precios-screen] .precios-icon-edit:hover { background: #d9e8ff !important; }
body[data-precios-screen] .precios-icon-delete { background: #ffecec !important; color: #dc3545 !important; }
body[data-precios-screen] .precios-icon-delete:hover { background: #ffd3d3 !important; }
.precios-icon-btn i { pointer-events: none; }

/* ── 8 · Tabla editable (precios/lista_productos.html) ───────────────────── */
body[data-precios-screen] .precios-table-card {
  background: #ffffff;
  border-radius: var(--radius-xl, 20px);
  border: 1px solid #eef2f7;
  overflow: hidden;
  box-shadow: 0 10px 32px -12px rgba(15, 23, 42, 0.08);
}
.precios-table-responsive { overflow-x: auto; }
.precios-table { width: 100%; border-collapse: collapse; }
/* dark-theme.css define `td { color:#f1f5f9 !important }`,
   `tr:nth-child(even) td { background:#161c26 !important }` y
   `tr:hover td { background:#1a1f2b !important }` SIN scope — pelea contra
   cualquier tabla de la app. Los reverts de abajo deben llevar !important en
   background/color para ganarle (mismo patrón que la sección 4). */
body[data-precios-screen] .precios-table th {
  background: #f8fafc !important;
  color: #475569 !important;
  padding: 12px 10px;
  text-align: left;
  font-weight: 700;
  font-size: 0.78rem;
  text-transform: uppercase;
  letter-spacing: 0.03em;
  white-space: nowrap;
  border-bottom: 1px solid #eef2f7;
}
body[data-precios-screen] .precios-table td {
  padding: 10px;
  border-bottom: 1px solid #f1f5f9;
  background: #ffffff !important;
  color: #0f172a !important;
  font-size: 0.9rem;
}
body[data-precios-screen] .precios-table tr:nth-child(even) td { background: #f8fafc !important; }
body[data-precios-screen] .precios-table tr:hover td { background: #f1f5f9 !important; }
.precios-th-precio, .precios-th-margen { width: 110px; text-align: center; }
.precios-th-proveedor { width: 140px; }
.precios-th-acciones { width: 60px; text-align: center; }
body[data-precios-screen] .precios-input {
  width: 90px;
  padding: 6px 8px;
  background: #ffffff !important;
  color: #0f172a !important;
  border: 1px solid #e2e8f0 !important;
  border-radius: 8px;
  font-size: 0.88rem;
  font-family: 'SF Mono', 'Fira Code', monospace;
  text-align: right;
}
body[data-precios-screen] .precios-input:focus {
  outline: none;
  border-color: #2563eb !important;
  box-shadow: 0 0 0 3px rgba(37, 99, 235, 0.16);
}
body[data-precios-screen] .precios-input.is-modified {
  border-color: #f59e0b !important;
  background: #fffbeb !important;
}
.precios-td-input { text-align: center; }
.precios-td-calculado {
  font-family: 'SF Mono', 'Fira Code', monospace;
  font-weight: 700;
  text-align: center;
}
body[data-precios-screen] .precios-precio-jomar { color: #0284c7; }
body[data-precios-screen] .precios-precio-retail { color: #ea580c; }
@keyframes precios-row-saved {
  0% { background: rgba(5, 150, 105, 0.15); }
  100% { background: transparent; }
}
.precios-row-saved td { animation: precios-row-saved 1.4s ease-out; }

/* ── 9 · Toolbar / acciones de página ────────────────────────────────────── */
.precios-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}
.precios-toolbar-left, .precios-toolbar-right {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}
body[data-precios-screen] .precios-select {
  padding: 9px 12px;
  background: #ffffff !important;
  color: #0f172a !important;
  border: 1px solid #e2e8f0 !important;
  border-radius: 10px;
  font-size: 0.88rem;
}
body[data-precios-screen] .precios-count { color: #64748b; font-size: 0.85rem; }

/* ── 10 · Tabla genérica (asignaciones / precios específicos) ────────────── */
/* Mismo problema que .precios-table (sección 8): dark-theme.css pelea sin
   scope contra cualquier <td>/fila par/hover — reverts con !important. */
body[data-precios-screen] .precios-generic-table th {
  background: linear-gradient(135deg, #2563eb 0%, #4f46e5 100%) !important;
  color: #ffffff !important;
  padding: 12px 10px;
  text-align: left;
  font-weight: 700;
  font-size: 0.82rem;
}
body[data-precios-screen] .precios-generic-table td {
  padding: 12px 10px;
  border-bottom: 1px solid #f1f5f9;
  background: #ffffff !important;
  color: #0f172a !important;
}
body[data-precios-screen] .precios-generic-table tbody tr:nth-of-type(odd) td { background: #f8fafc !important; }
body[data-precios-screen] .precios-generic-table tbody tr:hover td { background: #f1f5f9 !important; }

/* ── 11 · Empty state ─────────────────────────────────────────────────────── */
body[data-precios-screen] .precios-empty {
  text-align: center;
  padding: 40px 16px;
  color: #94a3b8;
  background: #ffffff;
  border: 1px dashed #e2e8f0;
  border-radius: var(--radius-xl, 20px);
}
body[data-precios-screen] .precios-empty i { font-size: 2.2rem; color: #cbd5e1; margin-bottom: 10px; display: block; }

/* ── 12 · Modal (precios/clientes.html) ──────────────────────────────────── */
.precios-modal {
  position: fixed;
  inset: 0;
  z-index: 1000;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(15, 23, 42, 0.5);
  padding: 16px;
}
.precios-modal[hidden] { display: none; }
body[data-precios-screen] .precios-modal-content {
  background: #ffffff;
  border-radius: 18px;
  width: 100%;
  max-width: 720px;
  max-height: 82vh;
  overflow: hidden;
  display: flex;
  flex-direction: column;
  border: 1px solid #e2e8f0;
}
body[data-precios-screen] .precios-modal-header {
  padding: 16px 20px;
  border-bottom: 1px solid #eef2f7;
  display: flex;
  justify-content: space-between;
  align-items: center;
}
body[data-precios-screen] .precios-modal-header h3 { margin: 0; color: #0f172a; font-size: 1.05rem; }
body[data-precios-screen] .precios-modal-close {
  background: none;
  border: none;
  font-size: 22px;
  cursor: pointer;
  color: #64748b;
  line-height: 1;
}
body[data-precios-screen] .precios-modal-body {
  padding: 18px 20px;
  overflow-y: auto;
  color: #0f172a;
}

/* ── 13 · Badges/chips propios de Precios (fuera de scope de .chip global) ── */
body[data-precios-screen] .precios-badge {
  display: inline-block;
  padding: 3px 10px;
  border-radius: 12px;
  font-size: 0.72rem;
  font-weight: 700;
  text-transform: uppercase;
}
body[data-precios-screen] .precios-badge-default { background: #fef9c3; color: #854d0e; }
body[data-precios-screen] .precios-badge-inactive { background: #f1f5f9; color: #64748b; }
body[data-precios-screen] .precios-badge-success { background: #dcfce7; color: #166534; }
body[data-precios-screen] .precios-badge-info { background: #e0f2fe; color: #075985; }
body[data-precios-screen] .precios-badge-primary { background: #e0e7ff; color: #3730a3; }

/* ── 14 · Escudo dark-mode del sistema (idéntico mecanismo verificado en
      gestion.css sección 6 — mismos ofensores, mismo truco de especificidad,
      adaptado al prefijo data-precios-screen). ─────────────────────────── */
@media (prefers-color-scheme: dark) {
  html body[data-precios-screen] .precios-wrap input:not([type="checkbox"]):not([type="radio"]):not([type="submit"]):not([type="button"]),
  html body[data-precios-screen] .precios-wrap select,
  html body[data-precios-screen] .precios-wrap textarea,
  html body[data-precios-screen] .mobile-form-container input:not([type="checkbox"]):not([type="radio"]):not([type="submit"]):not([type="button"]),
  html body[data-precios-screen] .mobile-form-container select,
  html body[data-precios-screen] .mobile-form-container textarea {
    background: #ffffff !important;
    background-image: none !important;
    border: 1px solid #e2e8f0 !important;
    color: #0f172a !important;
    box-shadow: none !important;
  }
  html body[data-precios-screen] .precios-wrap input:not([type="checkbox"]):not([type="radio"]):not([type="submit"]):not([type="button"]):focus,
  html body[data-precios-screen] .precios-wrap select:focus,
  html body[data-precios-screen] .precios-wrap textarea:focus,
  html body[data-precios-screen] .mobile-form-container input:not([type="checkbox"]):not([type="radio"]):not([type="submit"]):not([type="button"]):focus,
  html body[data-precios-screen] .mobile-form-container select:focus,
  html body[data-precios-screen] .mobile-form-container textarea:focus {
    background: #ffffff !important;
    border-color: #2563eb !important;
  }
  html body[data-precios-screen] .precios-wrap input::placeholder,
  html body[data-precios-screen] .mobile-form-container input::placeholder {
    color: #94a3b8 !important;
  }
  html body[data-precios-screen] .precios-wrap label,
  html body[data-precios-screen] .mobile-form-container label {
    color: #475569 !important;
  }
  html body[data-precios-screen] .precios-wrap form,
  html body[data-precios-screen] .mobile-form-container form {
    background: transparent !important;
  }
  html body[data-precios-screen] .mobile-card {
    background: #ffffff !important;
    color: #0f172a !important;
  }
  html body[data-precios-screen] .mobile-card-header {
    background: #f8fafc !important;
    color: #0f172a !important;
  }
  html body[data-precios-screen] .mobile-btn-secondary:not(.btn-chip):not(.cam-edit) {
    background: #ffffff !important;
    color: #0f172a !important;
    border: 1px solid #e2e8f0 !important;
  }
  html body[data-precios-screen] .precios-input:not(.btn-chip):not(.cam-edit) {
    background: #ffffff !important;
    color: #0f172a !important;
  }
  html body[data-precios-screen] .precios-icon-edit:not(.btn-chip):not(.cam-edit) {
    background: #eef4ff !important;
    color: #2b7cff !important;
  }
  html body[data-precios-screen] .precios-icon-delete:not(.btn-chip):not(.cam-edit) {
    background: #ffecec !important;
    color: #dc3545 !important;
  }
}
```

- [ ] **Step 2: Verificar que el estático se sirve**

Run: `ls -la static/css/precios.css` (confirmar que existe; con el server de preview corriendo, `curl -s -o /dev/null -w "%{http_code}" http://localhost:5002/static/css/precios.css` debe dar `200`).

- [ ] **Step 3: Commit**

```bash
git add static/css/precios.css
git commit -m "feat(precios): crea precios.css — scope claro + componentes hub/list/table/modal"
```

---

### Task 4: Hub claro (`precios/index.html`)

**Files:**
- Modify: `templates/precios/index.html` (reemplazo completo del archivo)

- [ ] **Step 1: Reemplazar el contenido completo del archivo por:**

```jinja
<!-- templates/precios/index.html -->
{% extends "base.html" %}

{% block title %}Sistema de Precios{% endblock %}

{% block header_title %}
    <i class="fas fa-dollar-sign color-blue mr-10"></i>Sistema de Precios
{% endblock %}

{% block content %}
<div class="precios-wrap">
    <div class="precios-hub-grid">
        <a href="{{ url_for('listas_precios') }}" class="precios-hub-card">
            <div class="precios-hub-icon"><i class="fas fa-list-alt"></i></div>
            <h3>Listas de Precios</h3>
            <p>Gestionar listas de precios por defecto y personalizadas</p>
            <span class="precios-badge precios-badge-info">{{ listas_precio|length }} listas</span>
        </a>

        <a href="{{ url_for('precios_clientes') }}" class="precios-hub-card">
            <div class="precios-hub-icon"><i class="fas fa-users"></i></div>
            <h3>Precios por Cliente</h3>
            <p>Asignar listas de precios específicas a clientes</p>
        </a>

        <a href="{{ url_for('precios_cliente_producto') }}" class="precios-hub-card">
            <div class="precios-hub-icon"><i class="fas fa-tags"></i></div>
            <h3>Precios Específicos</h3>
            <p>Definir precios individuales por cliente-producto</p>
        </a>

        <a href="{{ url_for('carga_masiva_precios') }}" class="precios-hub-card">
            <div class="precios-hub-icon"><i class="fas fa-upload"></i></div>
            <h3>Carga Masiva CSV</h3>
            <p>Actualizar precios en lote desde archivo CSV</p>
        </a>
    </div>
</div>
{% endblock %}
```

Nota: se elimina el bloque `extra_css` completo (71 líneas inline) — todo el estilo vive ahora en `precios.css`.

- [ ] **Step 2: Correr los tests del hub**

Run: `.venv/bin/python -m pytest tests/test_precios_ui.py -k hub -q`
Expected: `test_hub_patron_claro` PASA.

- [ ] **Step 3: Commit**

```bash
git add templates/precios/index.html
git commit -m "feat(precios): hub claro con .precios-hub-grid"
```

---

### Task 5: Listas claro (`precios/listas.html`)

**Files:**
- Modify: `templates/precios/listas.html` (reemplazo completo del archivo)

- [ ] **Step 1: Reemplazar el contenido completo del archivo por:**

```jinja
<!-- templates/precios/listas.html -->
{% extends "base.html" %}

{% block title %}Listas de Precios{% endblock %}

{% block header_title %}
    <i class="fas fa-list-alt color-blue mr-10"></i>Listas de Precios
{% endblock %}

{% block content %}
<div class="precios-wrap">
  <div id="flash-message" class="flash-message hidden"></div>

  <div class="precios-page-header">
    <h1 class="precios-title">Listas de Precios</h1>
    <a href="{{ url_for('nueva_lista_precio') }}" id="btn-nueva-lista" class="mobile-btn mobile-btn-primary">
      <i class="fas fa-plus"></i> Nueva Lista
    </a>
  </div>

  <div class="precios-list-grid">
    {% for lista in listas %}
    <div class="precios-list-card" data-lista-id="{{ lista.id }}">
      <div class="precios-list-card-header">
        <h3>{{ lista.nombre }}</h3>
        <div>
          {% if lista.es_default %}<span class="precios-badge precios-badge-default">Por Defecto</span>{% endif %}
          {% if not lista.activa %}<span class="precios-badge precios-badge-inactive">Inactiva</span>{% endif %}
        </div>
      </div>

      <p class="precios-list-desc">{{ lista.descripcion or 'Sin descripción' }}</p>
      <span class="precios-list-meta">Creada: {{ lista.fecha_creacion.strftime('%d/%m/%Y') if lista.fecha_creacion else '—' }}</span>

      <div class="precios-list-stats">
        <div class="precios-stat-item">
          <i class="fas fa-box"></i>
          <span class="precios-stat-value">{{ lista.precios_productos|length }}</span> productos
        </div>
        <div class="precios-stat-item">
          <i class="fas fa-users"></i>
          <span class="precios-stat-value">{{ lista.clientes|length }}</span> clientes
        </div>
      </div>

      <div class="precios-list-actions">
        <a href="{{ url_for('precios_lista_productos', lista_id=lista.id) }}"
           class="precios-chip-action precios-chip-primary">
          <i class="fas fa-dollar-sign"></i> Precios
        </a>
        {% if not lista.es_default %}
        <a href="{{ url_for('editar_lista_precio', lista_id=lista.id) }}"
           class="precios-chip-action precios-chip-edit">
          <i class="fas fa-edit"></i> Editar
        </a>
        <button type="button" class="precios-chip-action precios-chip-danger eliminar-lista"
                data-id="{{ lista.id }}" aria-label="Eliminar {{ lista.nombre }}">
          <i class="fas fa-trash"></i> Eliminar
        </button>
        {% endif %}
      </div>
    </div>
    {% else %}
    <div class="precios-empty">
      <i class="fas fa-list-alt"></i>
      <p>No hay listas de precios. Crea la primera para comenzar.</p>
      <a href="{{ url_for('nueva_lista_precio') }}" class="mobile-btn mobile-btn-primary">
        <i class="fas fa-plus"></i> Crear Lista
      </a>
    </div>
    {% endfor %}
  </div>
</div>
{% endblock %}

{% block scripts %}
<script nonce="{{ csp_nonce() }}">
(function () {
  'use strict';

  function aviso(msg, tipo) {
    if (window.mostrarMensaje) { window.mostrarMensaje(msg, tipo); }
    else { alert(msg); }
  }

  document.querySelectorAll('.eliminar-lista').forEach(function (btn) {
    btn.addEventListener('click', function () {
      var listaId = btn.dataset.id;
      var card = btn.closest('.precios-list-card');
      if (!confirm('¿Eliminar esta lista de precios?')) return;

      fetch('/precios/listas/' + listaId + '/eliminar', { method: 'POST' })
        .then(function (r) { return r.json().catch(function () { return {}; }); })
        .then(function (data) {
          // Fail-closed: solo message cuenta como éxito.
          if (data.message) {
            card.style.transition = 'opacity 0.25s';
            card.style.opacity = '0';
            setTimeout(function () {
              card.remove();
              if (!document.querySelector('.precios-list-card')) window.location.reload();
            }, 250);
          } else {
            aviso(data.error || 'Error al eliminar', 'error');
          }
        })
        .catch(function () { aviso('Error de conexión', 'error'); });
    });
  });
})();
</script>
{% endblock %}
```

Cambios funcionales respecto al original: el handler de delete ahora es fail-closed (antes: cualquier respuesta sin `data.message` explícito ya mostraba error correctamente — este comportamiento se conserva, pero se documenta y se usa `aviso()` en vez de `alert()` directo, con fallback si `base.min.js` está en caché vieja).

- [ ] **Step 2: Correr los tests de listas**

Run: `.venv/bin/python -m pytest tests/test_precios_ui.py -k listas -q`
Expected: `test_listas_patron_claro`, `test_listas_sin_legacy` PASAN.

- [ ] **Step 3: Commit**

```bash
git add templates/precios/listas.html
git commit -m "feat(precios): listas claro con .precios-list-grid + aviso() fail-closed"
```

---

### Task 6: Form de lista claro (`precios/lista_form.html`)

**Files:**
- Modify: `templates/precios/lista_form.html` (reemplazo completo del archivo)

- [ ] **Step 1: Reemplazar el contenido completo del archivo por:**

```jinja
<!-- templates/precios/lista_form.html -->
{% extends "base.html" %}

{% block title %}
    {% if lista %}Editar Lista de Precios{% else %}Nueva Lista de Precios{% endif %}
{% endblock %}

{% block header_title %}
    <i class="fas fa-list-alt color-blue mr-10"></i>
    {% if lista %}Editar Lista{% else %}Nueva Lista{% endif %}
{% endblock %}

{% block content %}
<div class="mobile-form-container">
  <form method="POST" id="lista-form" autocomplete="off">
    <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">

    <div class="mobile-card">
      <div class="mobile-card-header">
        <i class="fas fa-tag"></i>
        {% if lista %}Editar Lista de Precios{% else %}Crear Nueva Lista de Precios{% endif %}
      </div>
      <div class="mobile-card-body">
        <div class="mobile-form-group">
          <label class="mobile-form-label" for="nombre">Nombre de la Lista:</label>
          <input type="text" id="nombre" name="nombre" class="mobile-form-control"
                 value="{{ lista.nombre if lista else '' }}"
                 placeholder="Ej: Lista Clientes Premium" required>
        </div>

        <div class="mobile-form-group">
          <label class="mobile-form-label" for="descripcion">Descripción:</label>
          <textarea id="descripcion" name="descripcion" rows="3" class="mobile-form-control"
                    placeholder="Descripción opcional">{{ lista.descripcion if lista else '' }}</textarea>
        </div>

        {% if lista and lista.es_default %}
        <p class="precios-list-meta">
          <i class="fas fa-info-circle"></i>
          Lista por defecto: esta es la lista de precios principal del sistema.
        </p>
        {% endif %}
      </div>
    </div>

    <div class="mobile-form-actions">
      <a href="{{ url_for('listas_precios') }}" class="mobile-btn mobile-btn-secondary">
        <i class="fas fa-arrow-left"></i> Cancelar
      </a>
      <button type="submit" class="mobile-btn mobile-btn-primary">
        <i class="fas fa-save"></i>
        {% if lista %}Actualizar Lista{% else %}Crear Lista{% endif %}
      </button>
    </div>
  </form>

  {% if lista %}
  <div class="mobile-card">
    <div class="mobile-card-header"><i class="fas fa-info-circle"></i> Información de la Lista</div>
    <div class="mobile-card-body">
      <p class="precios-list-meta">Creada: {{ lista.fecha_creacion.strftime('%d/%m/%Y %H:%M') if lista.fecha_creacion else 'No disponible' }}</p>
      <p class="precios-list-meta">
        Estado:
        <span class="precios-badge {{ 'precios-badge-success' if lista.activa else 'precios-badge-inactive' }}">
          {{ 'Activa' if lista.activa else 'Inactiva' }}
        </span>
      </p>
      <p class="precios-list-meta">{{ lista.precios_productos|length }} productos configurados · {{ lista.clientes|length }} clientes asignados</p>
      {% if lista.precios_productos|length > 0 %}
      <a href="{{ url_for('precios_lista_productos', lista_id=lista.id) }}" class="mobile-btn mobile-btn-secondary">
        <i class="fas fa-dollar-sign"></i> Gestionar Precios
      </a>
      {% endif %}
    </div>
  </div>
  {% endif %}
</div>
{% endblock %}

{% block scripts %}
<script nonce="{{ csp_nonce() }}">
document.addEventListener('DOMContentLoaded', function () {
  var nombre = document.getElementById('nombre');
  nombre.focus();
  nombre.addEventListener('input', function () {
    this.style.borderColor = this.value.trim().length < 3 ? '#ef4444' : '';
  });
  document.getElementById('lista-form').addEventListener('submit', function (e) {
    if (nombre.value.trim().length < 3) {
      e.preventDefault();
      alert('El nombre debe tener al menos 3 caracteres');
      nombre.focus();
    }
  });
});
</script>
{% endblock %}
```

Este formulario sigue siendo un **POST nativo** (los routes `nueva_lista_precio`/`editar_lista_precio` usan `flash()`+`redirect()`, no JSON) — el mensaje de éxito/error lo pinta el stack global `.app-flash-stack` de `base.html`, sin necesitar `#flash-message` local ni `fetch`.

- [ ] **Step 2: Correr los tests del form**

Run: `.venv/bin/python -m pytest tests/test_precios_ui.py -k lista_form -q`
Expected: `test_lista_form_nueva_patron_claro`, `test_lista_form_editar_patron_claro` PASAN.

- [ ] **Step 3: Commit**

```bash
git add templates/precios/lista_form.html
git commit -m "feat(precios): lista_form claro reutilizando .mobile-card/.mobile-form-*"
```

---

### Task 7: Carga masiva claro + fix del bug fetch/JSON (`precios/carga_masiva.html`)

**Files:**
- Modify: `templates/precios/carga_masiva.html` (reemplazo completo del archivo)

- [ ] **Step 1: Reemplazar el contenido completo del archivo por:**

```jinja
<!-- templates/precios/carga_masiva.html -->
{% extends "base.html" %}

{% block title %}Carga Masiva de Precios{% endblock %}

{% block header_title %}<i class="fas fa-upload color-blue mr-10"></i>Carga Masiva de Precios{% endblock %}

{% block content %}
<div class="precios-wrap">
  <div id="flash-message" class="flash-message hidden"></div>

  <div class="mobile-card">
    <div class="mobile-card-header"><i class="fas fa-file-csv"></i> Archivo CSV</div>
    <div class="mobile-card-body">
      <form id="form-carga-masiva" enctype="multipart/form-data" autocomplete="off">
        <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">

        <div class="mobile-form-group">
          <label class="mobile-form-label" for="archivo">Archivo CSV:</label>
          <input type="file" name="archivo_csv" id="archivo" class="mobile-form-control" accept=".csv" required>
          <small>Formato soportado: CSV (.csv) codificado en UTF-8</small>
        </div>

        <div class="mobile-form-group">
          <label class="mobile-form-label" for="tipo_carga">Tipo de Carga:</label>
          <select name="tipo_carga" id="tipo_carga" class="mobile-form-control" required>
            <option value="">Seleccione el tipo de carga</option>
            <option value="lista_precios">Actualizar Precios de Lista</option>
            <option value="asignacion_clientes">Asignar Listas a Clientes</option>
            <option value="precios_especificos">Precios Específicos por Cliente</option>
          </select>
        </div>

        <div class="mobile-form-group" id="grupo-lista-precios">
          <label class="mobile-form-label" for="lista_precios">Lista de Precios:</label>
          <select name="lista_precio_id" id="lista_precios" class="mobile-form-control ts-select"
                  data-ts-placeholder="Buscar lista…">
            <option value="">Seleccione una lista de precios</option>
            {% for lista in listas %}
            <option value="{{ lista.id }}">{{ lista.nombre }}</option>
            {% endfor %}
          </select>
        </div>

        <div class="mobile-form-group">
          <label class="mobile-checkbox-label">
            <input type="checkbox" name="validar_antes" id="validar_antes" class="mobile-checkbox" checked>
            Validar antes de procesar (recomendado para archivos grandes)
          </label>
        </div>

        <div class="mobile-form-actions">
          <a href="{{ url_for('mostrar_precios') }}" class="mobile-btn mobile-btn-secondary">Cancelar</a>
          <button type="submit" class="mobile-btn mobile-btn-primary">
            <i class="fas fa-upload"></i> Procesar Archivo
          </button>
        </div>
      </form>
    </div>
  </div>

  <div class="mobile-card" id="resultado-card" hidden>
    <div class="mobile-card-header"><i class="fas fa-clipboard-check"></i> Resultado del Procesamiento</div>
    <div class="mobile-card-body">
      <p id="resultado-resumen" class="precios-list-meta"></p>
      <div id="resultado-detalles" class="precios-empty" style="text-align:left; display:none;"></div>
      <div class="mobile-form-actions">
        <a id="link-ver-lista" href="{{ url_for('listas_precios') }}" class="mobile-btn mobile-btn-secondary">
          <i class="fas fa-list"></i> Ver Lista de Precios
        </a>
      </div>
    </div>
  </div>

  <div class="mobile-card">
    <div class="mobile-card-header"><i class="fas fa-file-excel"></i> Plantilla de Carga</div>
    <div class="mobile-card-body">
      <p class="precios-list-meta">Descarga la plantilla del tipo de carga seleccionado para asegurar el formato correcto.</p>
      <a id="link-plantilla" href="{{ url_for('descargar_plantilla_csv', tipo='lista_precios') }}"
         class="mobile-btn mobile-btn-secondary">
        <i class="fas fa-download"></i> Descargar Plantilla
      </a>
    </div>
  </div>
</div>
{% endblock %}

{% block scripts %}
<script nonce="{{ csp_nonce() }}">
(function () {
  'use strict';

  function aviso(msg, tipo) {
    if (window.mostrarMensaje) { window.mostrarMensaje(msg, tipo); }
    else { alert(msg); }
  }

  var tipoCargaSelect = document.getElementById('tipo_carga');
  var grupoLista = document.getElementById('grupo-lista-precios');
  var listaPreciosSelect = document.getElementById('lista_precios');
  var linkPlantilla = document.getElementById('link-plantilla');

  var PLANTILLA_URLS = {
    lista_precios: "{{ url_for('descargar_plantilla_csv', tipo='lista_precios') }}",
    asignacion_clientes: "{{ url_for('descargar_plantilla_csv', tipo='asignacion_clientes') }}",
    precios_especificos: "{{ url_for('descargar_plantilla_csv', tipo='precios_especificos') }}"
  };

  tipoCargaSelect.addEventListener('change', function () {
    var tipo = this.value;
    grupoLista.style.display = (tipo === 'asignacion_clientes') ? 'none' : '';
    if (PLANTILLA_URLS[tipo]) linkPlantilla.href = PLANTILLA_URLS[tipo];
  });

  var archivoInput = document.getElementById('archivo');
  archivoInput.addEventListener('change', function () {
    var file = this.files[0];
    if (!file) return;
    var maxSize = 10 * 1024 * 1024;
    if (file.size > maxSize) {
      aviso('El archivo es demasiado grande. El tamaño máximo es 10MB.', 'error');
      this.value = '';
      return;
    }
    var allowedTypes = ['text/csv', 'text/plain', 'application/csv', 'application/vnd.ms-excel'];
    if (file.type && allowedTypes.indexOf(file.type) === -1) {
      aviso('Tipo de archivo no soportado. Use CSV (.csv)', 'error');
      this.value = '';
    }
  });

  var form = document.getElementById('form-carga-masiva');
  var resultadoCard = document.getElementById('resultado-card');
  var resultadoResumen = document.getElementById('resultado-resumen');
  var resultadoDetalles = document.getElementById('resultado-detalles');

  // Fix: el submit nativo iba a un endpoint que SIEMPRE responde JSON (el
  // navegador terminaba mostrando JSON crudo); además el template esperaba
  // variables (resultado.total_registros, resultado.detalle_errores...) que
  // la ruta nunca pasaba. Se reemplaza por fetch, renderizando la forma REAL
  // de /precios/procesar-csv: {success, mensaje, resultados: {procesados,
  // errores, warnings, detalles}}.
  form.addEventListener('submit', function (e) {
    e.preventDefault();

    if (!archivoInput.files[0]) { aviso('Por favor seleccione un archivo', 'error'); archivoInput.focus(); return; }
    if (!tipoCargaSelect.value) { aviso('Por favor seleccione el tipo de carga', 'error'); tipoCargaSelect.focus(); return; }
    if (tipoCargaSelect.value !== 'asignacion_clientes' && !listaPreciosSelect.value) {
      aviso('Por favor seleccione una lista de precios', 'error');
      listaPreciosSelect.focus();
      return;
    }

    var submitBtn = form.querySelector('button[type="submit"]');
    submitBtn.disabled = true;

    fetch("{{ url_for('procesar_csv_precios') }}", {
      method: 'POST',
      body: new FormData(form)
    })
      .then(function (r) { return r.json().catch(function () { return { error: 'Error al procesar el archivo' }; }); })
      .then(function (data) {
        submitBtn.disabled = false;
        if (data.error) { aviso(data.error, 'error'); return; }

        var r = data.resultados || {};
        resultadoResumen.textContent =
          (r.procesados || 0) + ' procesados · ' + (r.errores || 0) + ' con errores' +
          ((r.warnings && r.warnings.length) ? ' · ' + r.warnings.length + ' advertencias' : '');

        if (r.detalles && r.detalles.length) {
          resultadoDetalles.style.display = '';
          resultadoDetalles.innerHTML = '';
          r.detalles.forEach(function (linea) {
            var p = document.createElement('p');
            p.className = 'precios-list-meta';
            p.textContent = linea; // textContent: los detalles vienen del servidor, evita XSS
            resultadoDetalles.appendChild(p);
          });
        } else {
          resultadoDetalles.style.display = 'none';
        }

        resultadoCard.hidden = false;
        resultadoCard.scrollIntoView({ behavior: 'smooth', block: 'start' });
        aviso(data.mensaje || 'Procesamiento completado', (r.errores || 0) > 0 ? 'error' : 'success');
      })
      .catch(function () {
        submitBtn.disabled = false;
        aviso('Error al procesar el archivo', 'error');
      });
  });
})();
</script>
{% endblock %}
```

Cambios funcionales respecto al original (fix del bug documentado en el contexto): submit por `fetch` en vez de POST nativo; los resultados se renderizan con la forma REAL de la respuesta (`resultados.procesados/errores/warnings/detalles`); se elimina "Descargar Log" (el endpoint `descargar_log` no existe); "Descargar Plantilla" ahora apunta a la ruta real `descargar_plantilla_csv(tipo)` con el `tipo` sincronizado al select.

- [ ] **Step 2: Correr los tests de carga masiva**

Run: `.venv/bin/python -m pytest tests/test_precios_ui.py -k carga_masiva -q`
Expected: `test_carga_masiva_patron_claro` PASA.

- [ ] **Step 3: Commit**

```bash
git add templates/precios/carga_masiva.html
git commit -m "fix(precios): carga masiva CSV — submit por fetch, resultado real, plantilla correcta (bug encontrado en revisión)"
```

---

### Task 8: Tabla editable clara (`precios/lista_productos.html`)

**Files:**
- Modify: `templates/precios/lista_productos.html` (reemplazo completo del archivo)

- [ ] **Step 1: Reemplazar el contenido completo del archivo por:**

```jinja
<!-- templates/precios/lista_productos.html -->
{% extends "base.html" %}

{% block title %}Precios - {{ lista.nombre }}{% endblock %}

{% block header_title %}
    <i class="fas fa-list-alt color-blue mr-10"></i>{{ lista.nombre }}
{% endblock %}

{% block content %}
<div class="precios-wrap">
  <div id="flash-message" class="flash-message hidden"></div>

  <div class="precios-page-header">
    <div>
      <h1 class="precios-title">{{ lista.nombre }}</h1>
      <p class="precios-sub">{{ lista.descripcion or 'Sin descripción' }}</p>
      {% if lista.es_default %}<span class="precios-badge precios-badge-default">Lista por Defecto</span>{% endif %}
    </div>
    <a href="{{ url_for('listas_precios') }}" class="mobile-btn mobile-btn-secondary">
      <i class="fas fa-arrow-left"></i> Volver
    </a>
  </div>

  <div class="precios-toolbar">
    <div class="precios-toolbar-left">
      <select id="filtro-proveedor" class="precios-select" aria-label="Filtrar por proveedor">
        <option value="">Todos los proveedores</option>
        {% for prov in proveedores %}
        <option value="{{ prov }}">{{ prov }}</option>
        {% endfor %}
      </select>
      <span class="precios-count" id="productos-count">{{ precios_existentes|length }} productos</span>
    </div>
    <div class="precios-toolbar-right">
      <button type="button" class="mobile-btn mobile-btn-secondary" id="btn-agregar-producto">
        <i class="fas fa-plus"></i> Agregar Producto
      </button>
      <button type="button" class="mobile-btn mobile-btn-primary" id="btn-guardar-todo" disabled>
        <i class="fas fa-save"></i> Guardar Cambios
      </button>
    </div>
  </div>

  <div class="precios-table-card">
    <div class="precios-table-responsive">
      <table class="precios-table" id="tabla-precios">
        <thead>
          <tr>
            <th>Producto</th>
            <th class="precios-th-proveedor">Proveedor</th>
            <th class="precios-th-precio">Precio Base ($)</th>
            <th class="precios-th-margen">Margen Jomar</th>
            <th class="precios-th-precio">P. Jomar</th>
            <th class="precios-th-margen">Margen Retail</th>
            <th class="precios-th-precio">P. Retail</th>
            <th class="precios-th-acciones">Acciones</th>
          </tr>
        </thead>
        <tbody id="tbody-precios">
          {% for precio, producto in precios_existentes %}
          <tr data-precio-id="{{ precio.id }}"
              data-producto-id="{{ producto.id }}"
              data-proveedor="{{ producto.proveedor or '' }}">
            <td><strong>{{ producto.nombre }}</strong></td>
            <td class="precios-td-proveedor">{{ producto.proveedor or '—' }}</td>
            <td class="precios-td-input">
              <input type="number" class="precios-input input-base"
                     value="{{ '%.2f'|format(precio.precio_base) }}"
                     step="0.01" min="0" data-original="{{ '%.2f'|format(precio.precio_base) }}"
                     aria-label="Precio base de {{ producto.nombre }}">
            </td>
            <td class="precios-td-input">
              <input type="number" class="precios-input input-margen"
                     value="{{ '%.2f'|format(precio.margen_jomar or 1.0) }}"
                     step="0.01" min="0" data-field="margen_jomar"
                     data-original="{{ '%.2f'|format(precio.margen_jomar or 1.0) }}"
                     aria-label="Margen Jomar de {{ producto.nombre }}">
            </td>
            <td class="precios-td-calculado precios-precio-jomar">
              ${{ "%.2f"|format((precio.precio_base * (precio.margen_jomar or 1.0))) }}
            </td>
            <td class="precios-td-input">
              <input type="number" class="precios-input input-margen"
                     value="{{ '%.2f'|format(precio.margen_retail or 1.2) }}"
                     step="0.01" min="0" data-field="margen_retail"
                     data-original="{{ '%.2f'|format(precio.margen_retail or 1.2) }}"
                     aria-label="Margen Retail de {{ producto.nombre }}">
            </td>
            <td class="precios-td-calculado precios-precio-retail">
              ${{ "%.2f"|format((precio.precio_base * (precio.margen_retail or 1.2))) }}
            </td>
            <td style="text-align:center">
              <button type="button" class="precios-icon-btn precios-icon-delete btn-eliminar"
                      title="Eliminar" aria-label="Eliminar precio de {{ producto.nombre }}">
                <i class="fas fa-trash"></i>
              </button>
            </td>
          </tr>
          {% endfor %}
        </tbody>
      </table>
    </div>

    {% if not precios_existentes %}
    <div class="precios-empty" id="empty-state">
      <i class="fas fa-box-open"></i>
      <p>No hay precios configurados. Agrega productos usando el botón de arriba.</p>
    </div>
    {% endif %}
  </div>

  <div class="mobile-card" id="agregar-form" hidden>
    <div class="mobile-card-header"><i class="fas fa-plus-circle"></i> Agregar Producto a la Lista</div>
    <div class="mobile-card-body">
      <form id="form-nuevo-precio">
        <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
        <div class="mobile-form-group">
          <label class="mobile-form-label" for="nuevo_producto_id">Producto:</label>
          <select id="nuevo_producto_id" name="producto_id" class="mobile-form-control ts-select"
                  data-ts-placeholder="Buscar producto…" required>
            <option value=""></option>
            {% for producto in productos_disponibles %}
            <option value="{{ producto.id }}">{{ producto.nombre }}</option>
            {% endfor %}
          </select>
        </div>
        <div class="mobile-form-group">
          <label class="mobile-form-label" for="nuevo_precio_base">Precio Base ($):</label>
          <input type="number" id="nuevo_precio_base" name="precio_base" class="mobile-form-control" step="0.01" min="0" required>
        </div>
        <div class="mobile-form-group">
          <label class="mobile-form-label" for="nuevo_margen_jomar">Margen Jomar:</label>
          <input type="number" id="nuevo_margen_jomar" name="margen_jomar" class="mobile-form-control" step="0.01" min="0" value="1.0">
        </div>
        <div class="mobile-form-group">
          <label class="mobile-form-label" for="nuevo_margen_retail">Margen Retail:</label>
          <input type="number" id="nuevo_margen_retail" name="margen_retail" class="mobile-form-control" step="0.01" min="0" value="1.2">
        </div>
        <div class="mobile-form-actions">
          <button type="button" class="mobile-btn mobile-btn-secondary" id="btn-cancelar-agregar">Cancelar</button>
          <button type="submit" class="mobile-btn mobile-btn-primary">
            <i class="fas fa-plus"></i> Agregar
          </button>
        </div>
      </form>
    </div>
  </div>
</div>
{% endblock %}

{% block scripts %}
<script nonce="{{ csp_nonce() }}">
(function () {
  'use strict';

  var LISTA_ID = {{ lista.id }};
  var cambiosPendientes = false;

  // base.min.js stale (caché CDN/PWA) puede no traer mostrarMensaje aún.
  // Reemplaza al mostrarMensaje() local que tenía este archivo antes.
  function aviso(msg, tipo) {
    if (window.mostrarMensaje) { window.mostrarMensaje(msg, tipo); }
    else { alert(msg); }
  }

  function actualizarContador() {
    var filas = document.querySelectorAll('#tbody-precios tr');
    var visibles = Array.prototype.filter.call(filas, function (r) { return r.style.display !== 'none'; }).length;
    var total = filas.length;
    var filtro = document.getElementById('filtro-proveedor').value;
    document.getElementById('productos-count').textContent =
      filtro ? (visibles + ' de ' + total + ' productos') : (total + ' productos');
  }

  function marcarCambios() {
    cambiosPendientes = true;
    document.getElementById('btn-guardar-todo').disabled = false;
  }

  function calcularFila(fila) {
    var base = parseFloat(fila.querySelector('.input-base').value) || 0;
    var margenJ = parseFloat(fila.querySelector('[data-field="margen_jomar"]').value) || 1.0;
    var margenR = parseFloat(fila.querySelector('[data-field="margen_retail"]').value) || 1.2;
    fila.querySelector('.precios-precio-jomar').textContent = '$' + (base * margenJ).toFixed(2);
    fila.querySelector('.precios-precio-retail').textContent = '$' + (base * margenR).toFixed(2);
  }

  function marcarModificado(input) {
    input.classList.toggle('is-modified', input.value !== input.dataset.original);
  }

  document.getElementById('filtro-proveedor').addEventListener('change', function () {
    var filtro = this.value.toLowerCase();
    document.querySelectorAll('#tbody-precios tr').forEach(function (fila) {
      var match = !filtro || (fila.dataset.proveedor || '').toLowerCase() === filtro;
      fila.style.display = match ? '' : 'none';
    });
    actualizarContador();
  });

  document.getElementById('tbody-precios').addEventListener('input', function (e) {
    if (!e.target.classList.contains('precios-input')) return;
    var fila = e.target.closest('tr');
    calcularFila(fila);
    marcarModificado(e.target);
    marcarCambios();
  });

  document.getElementById('tbody-precios').addEventListener('click', function (e) {
    var btn = e.target.closest('.btn-eliminar');
    if (!btn) return;
    var fila = btn.closest('tr');
    var precioId = fila.dataset.precioId;
    if (!confirm('¿Eliminar este precio de la lista?')) return;

    fetch('/precios/productos/' + precioId + '/eliminar', { method: 'DELETE' })
      .then(function (r) { return r.json().catch(function () { return {}; }); })
      .then(function (data) {
        if (data.message) {
          fila.remove();
          aviso('Precio eliminado', 'success');
          actualizarContador();
          if (!document.querySelectorAll('#tbody-precios tr').length) {
            var empty = document.getElementById('empty-state');
            if (empty) empty.style.display = '';
          }
        } else {
          aviso(data.error || 'Error al eliminar', 'error');
        }
      })
      .catch(function () { aviso('Error de conexión', 'error'); });
  });

  document.getElementById('btn-guardar-todo').addEventListener('click', function () {
    var btnGuardar = this;
    var filas = document.querySelectorAll('#tbody-precios tr');
    var precios = [];
    filas.forEach(function (fila) {
      var base = parseFloat(fila.querySelector('.input-base').value);
      var margenJ = parseFloat(fila.querySelector('[data-field="margen_jomar"]').value);
      var margenR = parseFloat(fila.querySelector('[data-field="margen_retail"]').value);
      if (!isNaN(base) && base >= 0) {
        precios.push({
          producto_id: parseInt(fila.dataset.productoId, 10),
          precio_base: base,
          margen_jomar: isNaN(margenJ) ? 1.0 : margenJ,
          margen_retail: isNaN(margenR) ? 1.2 : margenR
        });
      }
    });

    btnGuardar.disabled = true;
    btnGuardar.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Guardando...';

    fetch('/precios/listas/' + LISTA_ID + '/productos/masivo', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ precios: precios })
    })
      .then(function (r) { return r.json().catch(function () { return {}; }); })
      .then(function (data) {
        if (data.actualizados !== undefined) {
          aviso(data.message, 'success');
          cambiosPendientes = false;
          filas.forEach(function (fila) {
            fila.querySelectorAll('.precios-input').forEach(function (input) {
              input.dataset.original = input.value;
              input.classList.remove('is-modified');
            });
            fila.classList.add('precios-row-saved');
            setTimeout(function () { fila.classList.remove('precios-row-saved'); }, 1400);
          });
        } else {
          aviso(data.error || 'Error al guardar', 'error');
        }
      })
      .catch(function () { aviso('Error de conexión', 'error'); })
      .finally(function () {
        btnGuardar.innerHTML = '<i class="fas fa-save"></i> Guardar Cambios';
        btnGuardar.disabled = !cambiosPendientes;
      });
  });

  var agregarForm = document.getElementById('agregar-form');
  document.getElementById('btn-agregar-producto').addEventListener('click', function () {
    var abrir = agregarForm.hidden;
    agregarForm.hidden = !abrir;
    if (abrir) agregarForm.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  });
  document.getElementById('btn-cancelar-agregar').addEventListener('click', function () {
    agregarForm.hidden = true;
    document.getElementById('form-nuevo-precio').reset();
  });

  var formNuevo = document.getElementById('form-nuevo-precio');
  formNuevo.addEventListener('submit', function (e) {
    e.preventDefault();
    var submitBtn = formNuevo.querySelector('button[type="submit"]');
    submitBtn.disabled = true;

    fetch('/precios/listas/' + LISTA_ID + '/productos', {
      method: 'POST',
      body: new FormData(formNuevo)
    })
      .then(function (r) { return r.json().catch(function () { return {}; }); })
      .then(function (data) {
        if (data.message) {
          sessionStorage.setItem('gestionFlash', data.message);
          window.location.reload();
        } else {
          submitBtn.disabled = false;
          aviso(data.error || 'Error al agregar', 'error');
        }
      })
      .catch(function () {
        submitBtn.disabled = false;
        aviso('Error de conexión', 'error');
      });
  });

  var flash = sessionStorage.getItem('gestionFlash');
  if (flash) {
    sessionStorage.removeItem('gestionFlash');
    document.addEventListener('DOMContentLoaded', function () { aviso(flash, 'success'); });
  }

  window.addEventListener('beforeunload', function (e) {
    if (cambiosPendientes) {
      e.preventDefault();
      e.returnValue = '';
    }
  });
})();
</script>
{% endblock %}
```

Notas sobre lo conservado vs. lo cambiado: la lógica de negocio (filtro, cálculo en vivo, guardado batch, advertencia `beforeunload`) se mantiene intacta — es sólida y ya estaba en vanilla JS. Cambios: clases CSS a la nomenclatura `precios-*`; `mostrarMensaje()` local reemplazado por `aviso()` (patrón compartido); el guardado batch YA NO manda `X-CSRFToken` manual en el header (el patch global de `base.js` lo inyecta automáticamente en todo `fetch` no-GET, así que se retira el `CSRF` hardcodeado del script y el header explícito); "Agregar producto" ahora usa `sessionStorage` + reload con flash diferido en vez de `setTimeout(location.reload, 800)` (evita el parpadeo del mensaje que desaparecía antes del reload); el botón eliminar usa `.precios-icon-btn`/`.precios-icon-delete` (definidos en `precios.css` — **no** `.gestion-icon-btn`: ese componente vive en `gestion.css` scopeado a `body[data-gestion-screen]`, atributo que las páginas de Precios no tienen).

- [ ] **Step 2: Correr los tests de la tabla**

Run: `.venv/bin/python -m pytest tests/test_precios_ui.py -k lista_productos -q`
Expected: `test_lista_productos_patron_claro` PASA.

- [ ] **Step 3: Commit**

```bash
git add templates/precios/lista_productos.html
git commit -m "feat(precios): tabla editable clara — conserva lógica JS, migra a aviso() y CSRF automático"
```

---

### Task 9: Precios por cliente claro + fix del bug del modal (`precios/clientes.html`)

**Files:**
- Modify: `templates/precios/clientes.html` (reemplazo completo del archivo)

- [ ] **Step 1: Reemplazar el contenido completo del archivo por:**

```jinja
<!-- templates/precios/clientes.html -->
{% extends "base.html" %}

{% block title %}Precios por Cliente{% endblock %}

{% block header_title %}
    <i class="fas fa-users color-blue mr-10"></i>Precios por Cliente
{% endblock %}

{% block content %}
<div class="precios-wrap">
  <div id="flash-message" class="flash-message hidden"></div>

  <div class="precios-page-header">
    <p class="precios-sub" style="max-width:560px">Si un cliente no tiene lista asignada, usará la lista por defecto.</p>
    <a href="{{ url_for('mostrar_precios') }}" class="mobile-btn mobile-btn-secondary">
      <i class="fas fa-arrow-left"></i> Volver a Precios
    </a>
  </div>

  <div class="mobile-card">
    <div class="mobile-card-header"><i class="fas fa-link"></i> Asignar Lista de Precios</div>
    <div class="mobile-card-body">
      <form id="form-asignar-lista">
        <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
        <div class="mobile-form-group">
          <label class="mobile-form-label" for="cliente_id">Cliente:</label>
          <select id="cliente_id" name="cliente_id" class="mobile-form-control ts-select"
                  data-ts-placeholder="Buscar cliente…" required>
            <option value=""></option>
            {% for cliente in clientes %}
            <option value="{{ cliente.id }}">{{ cliente.nombre }}</option>
            {% endfor %}
          </select>
        </div>
        <div class="mobile-form-group">
          <label class="mobile-form-label" for="lista_precio_id">Lista de Precios:</label>
          <select id="lista_precio_id" name="lista_precio_id" class="mobile-form-control ts-select"
                  data-ts-placeholder="Buscar lista…" required>
            <option value=""></option>
            {% for lista in listas %}
            <option value="{{ lista.id }}">{{ lista.nombre }}{% if lista.es_default %} (Por Defecto){% endif %}</option>
            {% endfor %}
          </select>
        </div>
        <div class="mobile-form-actions">
          <button type="submit" class="mobile-btn mobile-btn-primary">
            <i class="fas fa-link"></i> Asignar Lista
          </button>
        </div>
      </form>
    </div>
  </div>

  <div class="mobile-card">
    <div class="mobile-card-header"><i class="fas fa-list"></i> Asignaciones Actuales</div>
    <div class="mobile-card-body">
      {% if asignaciones %}
      <div class="precios-table-responsive">
        <table class="precios-generic-table" id="tabla-asignaciones">
          <thead>
            <tr>
              <th>Cliente</th><th>Lista de Precios</th><th>Tipo</th>
              <th>Fecha Asignación</th><th>Estado</th><th>Acciones</th>
            </tr>
          </thead>
          <tbody>
            {% for asignacion, cliente, lista in asignaciones %}
            <tr data-asignacion-id="{{ asignacion.id }}">
              <td><strong>{{ cliente.nombre }}</strong></td>
              <td>{{ lista.nombre }}{% if lista.es_default %} <span class="precios-badge precios-badge-default">Defecto</span>{% endif %}</td>
              <td>
                {% if lista.es_default %}
                <span class="precios-badge precios-badge-inactive">Sistema</span>
                {% else %}
                <span class="precios-badge precios-badge-success">Personalizada</span>
                {% endif %}
              </td>
              <td>{{ asignacion.fecha_asignacion.strftime('%d/%m/%Y') if asignacion.fecha_asignacion else '-' }}</td>
              <td>
                {% if asignacion.activa %}
                <span class="precios-badge precios-badge-success">Activo</span>
                {% else %}
                <span class="precios-badge precios-badge-inactive">Inactivo</span>
                {% endif %}
              </td>
              <td>
                <button type="button" class="precios-icon-btn precios-icon-edit btn-ver"
                        data-cliente-id="{{ cliente.id }}" data-cliente-nombre="{{ cliente.nombre }}"
                        title="Ver precios" aria-label="Ver precios de {{ cliente.nombre }}">
                  <i class="fas fa-eye"></i>
                </button>
                {% if not lista.es_default %}
                <button type="button" class="precios-icon-btn precios-icon-delete btn-desasignar"
                        data-asignacion-id="{{ asignacion.id }}"
                        title="Desasignar" aria-label="Desasignar lista de {{ cliente.nombre }}">
                  <i class="fas fa-unlink"></i>
                </button>
                {% endif %}
              </td>
            </tr>
            {% endfor %}
          </tbody>
        </table>
      </div>
      {% else %}
      <div class="precios-empty">
        <i class="fas fa-users-slash"></i>
        <p>No hay asignaciones específicas. Todos los clientes usan la lista por defecto.</p>
      </div>
      {% endif %}
    </div>
  </div>

  <div class="precios-hub-grid">
    <div class="precios-hub-card" style="cursor:default">
      <div class="precios-hub-icon"><i class="fas fa-info-circle"></i></div>
      <h3>¿Cómo funciona?</h3>
      <p style="text-align:left">
        Cada cliente puede tener una lista de precios específica. Si no tiene lista
        asignada, usa la lista por defecto. Los precios específicos cliente-producto
        tienen prioridad sobre las listas.
      </p>
    </div>
    <div class="precios-hub-card" style="cursor:default">
      <div class="precios-hub-icon"><i class="fas fa-chart-line"></i></div>
      <h3>Estadísticas</h3>
      <p>{{ clientes|length }} clientes totales · {{ asignaciones|length }} con listas específicas · {{ listas|length }} listas disponibles</p>
    </div>
  </div>
</div>

<div id="modal-precios-cliente" class="precios-modal" hidden>
  <div class="precios-modal-content">
    <div class="precios-modal-header">
      <h3 id="modal-cliente-nombre">Precios del Cliente</h3>
      <button type="button" class="precios-modal-close" aria-label="Cerrar">&times;</button>
    </div>
    <div class="precios-modal-body">
      <div id="precios-cliente-contenido"><p>Cargando precios...</p></div>
    </div>
  </div>
</div>
{% endblock %}

{% block scripts %}
<script nonce="{{ csp_nonce() }}">
(function () {
  'use strict';

  function aviso(msg, tipo) {
    if (window.mostrarMensaje) { window.mostrarMensaje(msg, tipo); }
    else { alert(msg); }
  }

  function escapeHtml(value) {
    if (window.escapeHtml) return window.escapeHtml(value);
    return String(value == null ? '' : value)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
  }

  // ---- Asignar lista (fail-closed) ----
  var form = document.getElementById('form-asignar-lista');
  form.addEventListener('submit', function (e) {
    e.preventDefault();
    var submitBtn = form.querySelector('button[type="submit"]');
    submitBtn.disabled = true;

    fetch("{{ url_for('asignar_lista_cliente') }}", {
      method: 'POST',
      body: new FormData(form)
    })
      .then(function (r) { return r.json().catch(function () { return {}; }); })
      .then(function (data) {
        if (data.message) {
          sessionStorage.setItem('gestionFlash', data.message);
          window.location.reload();
        } else {
          submitBtn.disabled = false;
          aviso(data.error || 'Error al asignar lista', 'error');
        }
      })
      .catch(function () {
        submitBtn.disabled = false;
        aviso('Error de conexión', 'error');
      });
  });

  // ---- Desasignar (fail-closed, delegado a la tabla) ----
  var tabla = document.getElementById('tabla-asignaciones');
  if (tabla) {
    tabla.addEventListener('click', function (e) {
      var btnDel = e.target.closest('.btn-desasignar');
      if (btnDel) {
        var asignacionId = btnDel.dataset.asignacionId;
        if (!confirm('¿Desasignar esta lista de precios del cliente?')) return;
        fetch('/precios/clientes/' + asignacionId + '/eliminar', { method: 'DELETE' })
          .then(function (r) { return r.json().catch(function () { return {}; }); })
          .then(function (data) {
            if (data.message) {
              aviso(data.message, 'success');
              var row = tabla.querySelector('[data-asignacion-id="' + asignacionId + '"]');
              if (row) row.remove();
            } else {
              aviso(data.error || 'Error al eliminar asignación', 'error');
            }
          })
          .catch(function () { aviso('Error de conexión', 'error'); });
        return;
      }

      // ---- Ver precios del cliente (modal) ----
      var btnVer = e.target.closest('.btn-ver');
      if (!btnVer) return;
      var clienteId = btnVer.dataset.clienteId;
      var clienteNombre = btnVer.dataset.clienteNombre;
      var modal = document.getElementById('modal-precios-cliente');
      var contenido = document.getElementById('precios-cliente-contenido');

      document.getElementById('modal-cliente-nombre').textContent = 'Precios de ' + clienteNombre;
      modal.hidden = false;
      contenido.innerHTML = '<p>Cargando información del cliente...</p>';

      fetch('/api/precios/cliente/' + clienteId + '/debug')
        .then(function (r) { return r.json(); })
        .then(function (debugInfo) {
          var infoHtml = '<div class="cliente-info">';
          if (debugInfo.lista_asignada) {
            infoHtml += '<p class="precios-badge precios-badge-info">Lista asignada: ' +
              escapeHtml(debugInfo.lista_asignada.nombre) + ' (' + debugInfo.lista_asignada.productos_count + ' productos)</p>';
          } else {
            infoHtml += '<p class="precios-badge precios-badge-inactive">Sin lista asignada — usando lista por defecto' +
              (debugInfo.lista_default ? ' (' + debugInfo.lista_default.productos_count + ' productos)' : '') + '</p>';
          }
          if (debugInfo.precios_especificos_count > 0) {
            infoHtml += '<p class="precios-badge precios-badge-success">' + debugInfo.precios_especificos_count + ' precios específicos configurados</p>';
          }
          infoHtml += '</div>';
          contenido.innerHTML = infoHtml + '<p>Cargando precios...</p>';

          return fetch('/api/precios/cliente/' + clienteId + '/productos');
        })
        .then(function (r) { return r.json(); })
        .then(function (data) {
          // Fix: la API devuelve {id, nombre, precio, tipo_precio, precio_base,
          // margen_jomar, margen_retail, lista_nombre} — NUNCA precio_jomar/
          // precio_retail ni producto_nombre. El código anterior llamaba
          // precio.precio_jomar.toFixed(2) (undefined) y lanzaba TypeError a
          // mitad del forEach, dejando la tabla a medio renderizar.
          var infoExistente = contenido.querySelector('.cliente-info');
          var html = infoExistente ? infoExistente.outerHTML : '';

          if (data.length > 0) {
            html += '<p class="precios-list-meta">Total de productos con precio: ' + data.length + '</p>';
            html += '<div class="precios-table-responsive"><table class="precios-generic-table"><thead><tr>' +
              '<th>Producto</th><th>Precio Base</th><th>Precio Jomar</th><th>Precio Retail</th><th>Tipo</th>' +
              '</tr></thead><tbody>';

            data.forEach(function (precio) {
              var margenJomar = precio.margen_jomar || 1.0;
              var margenRetail = precio.margen_retail || 1.2;
              var precioJomar = precio.precio_base * margenJomar;
              var precioRetail = precio.precio_base * margenRetail;
              var tipoBadge = precio.tipo_precio === 'específico' ? 'precios-badge-primary'
                : (precio.tipo_precio === 'lista_asignada' ? 'precios-badge-success' : 'precios-badge-inactive');
              var tipoTexto = precio.tipo_precio === 'específico' ? 'Específico'
                : (precio.tipo_precio === 'lista_asignada' ? 'Lista' : 'Default');

              html += '<tr>' +
                '<td><strong>' + escapeHtml(precio.nombre) + '</strong></td>' +
                '<td>$' + precio.precio_base.toFixed(2) + '</td>' +
                '<td>$' + precioJomar.toFixed(2) + '</td>' +
                '<td>$' + precioRetail.toFixed(2) + '</td>' +
                '<td><span class="precios-badge ' + tipoBadge + '">' + tipoTexto + '</span></td>' +
                '</tr>';
            });
            html += '</tbody></table></div>';
          } else {
            html += '<p class="precios-badge precios-badge-inactive">Este cliente no tiene productos con precios configurados.</p>';
          }
          contenido.innerHTML = html;
        })
        .catch(function () {
          contenido.innerHTML = '<p class="precios-badge precios-badge-inactive">Error al cargar los precios.</p>';
        });
    });
  }

  // ---- Cerrar modal ----
  var modalEl = document.getElementById('modal-precios-cliente');
  modalEl.querySelector('.precios-modal-close').addEventListener('click', function () { modalEl.hidden = true; });
  modalEl.addEventListener('click', function (e) { if (e.target === modalEl) modalEl.hidden = true; });

  // ---- Flash diferido ----
  var flash = sessionStorage.getItem('gestionFlash');
  if (flash) {
    sessionStorage.removeItem('gestionFlash');
    document.addEventListener('DOMContentLoaded', function () { aviso(flash, 'success'); });
  }
})();
</script>
{% endblock %}
```

Cambios respecto al original: **jQuery eliminado completamente** (CDN retirado, todo vanilla — patrón `closest`/`dataset`); handlers de crear/eliminar ahora fail-closed y con doble-submit-guard (patrón de Tanda 1); **el bug del modal está corregido** (usa `precio.nombre`, calcula `precio_base * margen_jomar`/`precio_base * margen_retail` en el cliente en vez de leer campos inexistentes); `escapeHtml` reutiliza `window.escapeHtml` de `base.js` con fallback local.

- [ ] **Step 2: Correr los tests de precios por cliente**

Run: `.venv/bin/python -m pytest tests/test_precios_ui.py -k "precios_clientes" -q`
Expected: `test_precios_clientes_patron_claro`, `test_precios_clientes_sin_jquery` PASAN.

- [ ] **Step 3: Commit**

```bash
git add templates/precios/clientes.html
git commit -m "fix(precios): precios por cliente — jQuery a vanilla, fail-closed, corrige TypeError del modal (bug encontrado en revisión)"
```

---

### Task 10: Precios específicos cliente-producto claro (`precios/cliente_producto.html`)

**Files:**
- Modify: `templates/precios/cliente_producto.html` (reemplazo completo del archivo)

- [ ] **Step 1: Reemplazar el contenido completo del archivo por:**

```jinja
<!-- templates/precios/cliente_producto.html -->
{% extends "base.html" %}

{% block title %}Precios Específicos{% endblock %}

{% block header_title %}
    <i class="fas fa-tags color-blue mr-10"></i>Precios Específicos
{% endblock %}

{% block content %}
<div class="precios-wrap">
  <div id="flash-message" class="flash-message hidden"></div>

  <div class="precios-page-header">
    <div>
      <h1 class="precios-title">Precios Específicos Cliente-Producto</h1>
      <p class="precios-sub" style="max-width:560px">
        Define precios individuales para combinaciones específicas de cliente y
        producto. Estos precios tienen la máxima prioridad.
      </p>
    </div>
    <a href="{{ url_for('mostrar_precios') }}" class="mobile-btn mobile-btn-secondary">
      <i class="fas fa-arrow-left"></i> Volver
    </a>
  </div>

  <div class="mobile-card">
    <div class="mobile-card-header"><i class="fas fa-bullseye"></i> Crear Precio Específico</div>
    <div class="mobile-card-body">
      <form id="form-precio-especifico">
        <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">

        <div class="mobile-form-group">
          <label class="mobile-form-label" for="cliente_id">Cliente:</label>
          <select id="cliente_id" name="cliente_id" class="mobile-form-control ts-select"
                  data-ts-placeholder="Buscar cliente…" required>
            <option value=""></option>
            {% for cliente in clientes %}
            <option value="{{ cliente.id }}">{{ cliente.nombre }}</option>
            {% endfor %}
          </select>
        </div>

        <div class="mobile-form-group">
          <label class="mobile-form-label" for="producto_id">Producto:</label>
          <select id="producto_id" name="producto_id" class="mobile-form-control ts-select"
                  data-ts-placeholder="Buscar producto…" required>
            <option value=""></option>
            {% for producto in productos %}
            <option value="{{ producto.id }}">{{ producto.nombre }}</option>
            {% endfor %}
          </select>
        </div>

        <div class="mobile-form-group">
          <label class="mobile-form-label" for="precio_base">Precio Base ($):</label>
          <input type="number" id="precio_base" name="precio_base" class="mobile-form-control" step="0.01" min="0" required>
        </div>

        <div class="mobile-form-group">
          <label class="mobile-form-label" for="margen_jomar">Margen Jomar:</label>
          <input type="number" id="margen_jomar" name="margen_jomar" class="mobile-form-control" step="0.01" min="0" value="1.0">
        </div>

        <div class="mobile-form-group">
          <label class="mobile-form-label" for="margen_retail">Margen Retail:</label>
          <input type="number" id="margen_retail" name="margen_retail" class="mobile-form-control" step="0.01" min="0" value="1.2">
        </div>

        <div class="precios-list-stats">
          <div class="precios-stat-item">Precio Jomar: <span class="precios-stat-value" id="precio_jomar_calc">$0.00</span></div>
          <div class="precios-stat-item">Precio Retail: <span class="precios-stat-value" id="precio_retail_calc">$0.00</span></div>
        </div>

        <div class="mobile-form-actions">
          <button type="button" id="limpiar-form" class="mobile-btn mobile-btn-secondary">
            <i class="fas fa-broom"></i> Limpiar
          </button>
          <button type="submit" class="mobile-btn mobile-btn-primary">
            <i class="fas fa-save"></i> Guardar Precio
          </button>
        </div>
      </form>
    </div>
  </div>

  <div class="mobile-card">
    <div class="mobile-card-header">
      <i class="fas fa-table"></i> Precios Específicos Configurados
      <span class="precios-badge precios-badge-info">{{ precios_especificos|length }}</span>
    </div>
    <div class="mobile-card-body">
      {% if precios_especificos %}
      <div class="precios-table-responsive">
        <table class="precios-generic-table" id="tabla-especificos">
          <thead>
            <tr>
              <th>Cliente</th><th>Producto</th><th>Base</th><th>Jomar</th>
              <th>Retail</th><th>Actualizado</th><th>Acciones</th>
            </tr>
          </thead>
          <tbody>
            {% for precio, cliente, producto in precios_especificos %}
            <tr data-precio-id="{{ precio.id }}"
                data-cliente-id="{{ cliente.id }}"
                data-producto-id="{{ producto.id }}"
                data-precio-base="{{ precio.precio_base }}"
                data-margen-jomar="{{ precio.margen_jomar or 1.0 }}"
                data-margen-retail="{{ precio.margen_retail or 1.2 }}">
              <td><strong>{{ cliente.nombre }}</strong></td>
              <td><strong>{{ producto.nombre }}</strong></td>
              <td>${{ "%.2f"|format(precio.precio_base) }}</td>
              <td class="precios-precio-jomar">${{ "%.2f"|format(precio.precio_jomar or 0) }}</td>
              <td class="precios-precio-retail">${{ "%.2f"|format(precio.precio_retail or 0) }}</td>
              <td>{{ precio.fecha_actualizacion.strftime('%d/%m') if precio.fecha_actualizacion else '-' }}</td>
              <td>
                <button type="button" class="precios-icon-btn precios-icon-edit btn-editar"
                        title="Editar" aria-label="Editar precio de {{ cliente.nombre }} / {{ producto.nombre }}">
                  <i class="fas fa-edit"></i>
                </button>
                <button type="button" class="precios-icon-btn precios-icon-delete btn-eliminar"
                        title="Eliminar" aria-label="Eliminar precio de {{ cliente.nombre }} / {{ producto.nombre }}">
                  <i class="fas fa-trash"></i>
                </button>
              </td>
            </tr>
            {% endfor %}
          </tbody>
        </table>
      </div>
      {% else %}
      <div class="precios-empty">
        <i class="fas fa-tags"></i>
        <p>No hay precios específicos. Los precios específicos tienen máxima prioridad; crea el primero con el formulario.</p>
      </div>
      {% endif %}
    </div>
  </div>

  <div class="mobile-card">
    <div class="mobile-card-header"><i class="fas fa-info-circle"></i> Jerarquía de Precios</div>
    <div class="mobile-card-body">
      <p class="precios-list-meta"><strong>1.</strong> Precios Específicos Cliente-Producto — máxima prioridad (esta página)</p>
      <p class="precios-list-meta"><strong>2.</strong> Lista de Precios del Cliente — si el cliente tiene lista asignada</p>
      <p class="precios-list-meta"><strong>3.</strong> Lista de Precios por Defecto — respaldo del sistema</p>
    </div>
  </div>
</div>
{% endblock %}

{% block scripts %}
<script nonce="{{ csp_nonce() }}">
(function () {
  'use strict';

  function aviso(msg, tipo) {
    if (window.mostrarMensaje) { window.mostrarMensaje(msg, tipo); }
    else { alert(msg); }
  }

  var form = document.getElementById('form-precio-especifico');
  var precioBase = document.getElementById('precio_base');
  var margenJomar = document.getElementById('margen_jomar');
  var margenRetail = document.getElementById('margen_retail');

  function calcularPrecios() {
    var base = parseFloat(precioBase.value) || 0;
    var mj = parseFloat(margenJomar.value) || 1.0;
    var mr = parseFloat(margenRetail.value) || 1.2;
    document.getElementById('precio_jomar_calc').textContent = '$' + (base * mj).toFixed(2);
    document.getElementById('precio_retail_calc').textContent = '$' + (base * mr).toFixed(2);
  }

  [precioBase, margenJomar, margenRetail].forEach(function (el) {
    el.addEventListener('input', calcularPrecios);
  });

  function limpiarFormulario() {
    form.reset();
    calcularPrecios();
  }
  document.getElementById('limpiar-form').addEventListener('click', limpiarFormulario);

  form.addEventListener('submit', function (e) {
    e.preventDefault();
    var submitBtn = form.querySelector('button[type="submit"]');
    submitBtn.disabled = true;

    fetch("{{ url_for('crear_precio_cliente_producto') }}", {
      method: 'POST',
      body: new FormData(form)
    })
      .then(function (r) { return r.json().catch(function () { return {}; }); })
      .then(function (data) {
        if (data.message) {
          sessionStorage.setItem('gestionFlash', data.message);
          window.location.reload();
        } else {
          submitBtn.disabled = false;
          aviso(data.error || 'Error al guardar', 'error');
        }
      })
      .catch(function () {
        submitBtn.disabled = false;
        aviso('Error de conexión', 'error');
      });
  });

  var tabla = document.getElementById('tabla-especificos');
  if (tabla) {
    tabla.addEventListener('click', function (e) {
      var btnEditar = e.target.closest('.btn-editar');
      if (btnEditar) {
        var fila = btnEditar.closest('tr');
        var clienteSelect = document.getElementById('cliente_id');
        var productoSelect = document.getElementById('producto_id');
        if (clienteSelect.tomselect) clienteSelect.tomselect.setValue(fila.dataset.clienteId);
        else clienteSelect.value = fila.dataset.clienteId;
        if (productoSelect.tomselect) productoSelect.tomselect.setValue(fila.dataset.productoId);
        else productoSelect.value = fila.dataset.productoId;
        precioBase.value = fila.dataset.precioBase;
        margenJomar.value = fila.dataset.margenJomar;
        margenRetail.value = fila.dataset.margenRetail;
        calcularPrecios();
        document.querySelector('.mobile-card').scrollIntoView({ behavior: 'smooth' });
        return;
      }

      var btnEliminar = e.target.closest('.btn-eliminar');
      if (!btnEliminar) return;
      var filaDel = btnEliminar.closest('tr');
      var precioId = filaDel.dataset.precioId;
      if (!confirm('¿Eliminar este precio específico?')) return;

      fetch('/precios/cliente-producto/' + precioId + '/eliminar', { method: 'DELETE' })
        .then(function (r) { return r.json().catch(function () { return {}; }); })
        .then(function (data) {
          if (data.message) {
            aviso(data.message, 'success');
            filaDel.remove();
          } else {
            aviso(data.error || 'Error al eliminar', 'error');
          }
        })
        .catch(function () { aviso('Error de conexión', 'error'); });
    });
  }

  var flash = sessionStorage.getItem('gestionFlash');
  if (flash) {
    sessionStorage.removeItem('gestionFlash');
    document.addEventListener('DOMContentLoaded', function () { aviso(flash, 'success'); });
  }

  calcularPrecios();
})();
</script>
{% endblock %}
```

Cambios respecto al original: `mostrarMensaje()` local eliminado, reemplazado por `aviso()`; el submit ahora es fail-closed con doble-submit-guard (antes: `if (data.message)` ya era correcto, se mantiene esa parte, se agrega el guard del botón); el "editar" precarga el form y hace scroll (igual que antes); el delete es fail-closed (ya lo era). No había bugs funcionales en este archivo — es un re-skin + armonización con el patrón compartido.

- [ ] **Step 2: Correr los tests de precios específicos**

Run: `.venv/bin/python -m pytest tests/test_precios_ui.py -k cliente_producto -q`
Expected: `test_cliente_producto_patron_claro` PASA.

- [ ] **Step 3: Correr toda la suite de la tanda**

Run: `.venv/bin/python -m pytest tests/test_precios_ui.py -q`
Expected: todos PASAN.

- [ ] **Step 4: Commit**

```bash
git add templates/precios/cliente_producto.html
git commit -m "feat(precios): precios cliente-producto claro con aviso() y doble-submit-guard"
```

---

### Task 11: Verificación visual e interactiva completa (controller, no subagente)

Este task lo ejecuta el coordinador directamente en el preview (launch.json `pesosapp`, puerto 5002; login `admin`/`Preview123!`), NO un subagente — requiere ver la pantalla.

- [ ] **Step 1: Suite completa de regresión**

Run: `.venv/bin/python -m pytest tests/ -q`
Expected: todo verde (314 + 12 nuevos de Tanda 1 + los de esta tanda passed, sin regresiones en pantallas no tocadas).

- [ ] **Step 2: Recorrido visual en viewport móvil 375px, las 7 pantallas**

Para cada una: `/precios`, `/precios/listas`, `/precios/listas/nueva`, `/precios/listas/<id>/editar`, `/precios/listas/<id>/productos`, `/precios/clientes`, `/precios/cliente-producto`, `/precios/carga-masiva`. Confirmar: fondo claro, sin restos de colores hex oscuros (`#141820`, `#1a1f2b`, `#3b4a5c`), sin errores en consola.

- [ ] **Step 3: Interacción — Listas**

Crear una lista de prueba, confirmar aparece en `/precios/listas` con el flash global. Editarla (cambiar descripción). Eliminarla (no será la default) y confirmar que desaparece con fade.

- [ ] **Step 4: Interacción — Lista de productos (tabla editable)**

Abrir `/precios/listas/<id>/productos` de la lista default (tiene productos del seed). Editar un precio base → confirmar cálculo en vivo de P. Jomar/P. Retail y que el input se marca `is-modified` (borde ámbar). Click "Guardar Cambios" → confirmar animación verde de fila guardada y que el botón vuelve a deshabilitarse. Agregar un producto nuevo vía el mini-form → confirmar reload + flash + fila nueva. Eliminar un precio → confirmar fila desaparece.

- [ ] **Step 5: Interacción — Precios por cliente (el bug del modal)**

En `/precios/clientes`, asignar una lista a un cliente → confirmar aparece en la tabla. Click en el ícono de ojo (Ver) de un cliente que tenga precios (el del seed, con `PrecioClienteProducto`) → **confirmar que el modal renderiza la tabla completa SIN error de consola** (este es el bug fijado; verificar explícitamente con `preview_console_logs` nivel error que está vacío tras abrir el modal). Cerrar el modal con la X y clickeando fuera. Desasignar una lista no-default → confirmar fila desaparece.

- [ ] **Step 6: Interacción — Precios específicos cliente-producto**

Llenar el form (cliente, producto, precio base) → confirmar cálculo en vivo de Jomar/Retail mientras se escribe. Guardar → confirmar aparece en la tabla. Click "Editar" en una fila → confirmar el form se precarga y hace scroll. Eliminar un precio específico → confirmar desaparece.

- [ ] **Step 7: Interacción — Carga masiva CSV (el bug del fetch)**

Seleccionar tipo "Actualizar Precios de Lista", una lista, y un archivo CSV pequeño de prueba con 1-2 filas válidas (usar el botón "Descargar Plantilla" primero para tener un CSV de formato correcto, editarlo con un producto real del seed). Procesar → **confirmar que la página NO navega a JSON crudo**, que aparece la card de resultado con el resumen correcto (N procesados, N errores) y el detalle por fila, sin recargar la página. Cambiar el tipo a "Asignar Listas a Clientes" → confirmar que el select de lista se oculta y el link de plantilla cambia de URL.

- [ ] **Step 8: Dark mode del sistema (escudo)**

`preview_resize` con `colorScheme: dark`, recargar cada pantalla con inputs/formularios (`/precios/listas/nueva`, `/precios/listas/<id>/productos`, `/precios/clientes`, `/precios/cliente-producto`, `/precios/carga-masiva`) y usar `preview_inspect`/`preview_eval` con nodos frescos (recarga completa, no reusar referencias DOM viejas — lección de la Tanda 1) para confirmar que inputs/selects/botones siguen blancos, no azules ni grises oscuros.

- [ ] **Step 9: Si cualquier verificación falla**

Diagnosticar leyendo el código fuente, corregir con Edit, volver a los pasos 2-8 relevantes. No avanzar al cierre con hallazgos sin resolver.

---

### Task 12: Cierre de tanda

- [ ] **Step 1: Revisión final del diff completo**

Run: `git log --oneline main -12` (ajustar el número al total real de commits de la tanda) y `git diff <SHA-antes-de-task-1>..HEAD --stat`
Expected: solo los archivos listados en la tabla de Files, sin sorpresas.

- [ ] **Step 2: Actualizar el spec**

En `docs/superpowers/specs/2026-07-01-migracion-lote-oscuro-design.md`, marcar la Tanda 5 (Precios) como ✅ completada en la tabla de tandas, igual que se hizo con la Tanda 1.

- [ ] **Step 3: Reportar al usuario**

Capturas antes/después de al menos: hub, listas, tabla editable, y el modal de precios de cliente (evidencia del fix del bug). Resultado de la suite completa. Resumen de los 2 bugs corregidos. Pedir OK explícito para `git push` (deploy a Heroku).

**NO hacer `git push` sin el OK explícito del usuario.** Tras el push, recordar: verificar contra `app.jomarfoods.com` (no el origen Heroku directo) y refrescar la PWA en el iPhone.
