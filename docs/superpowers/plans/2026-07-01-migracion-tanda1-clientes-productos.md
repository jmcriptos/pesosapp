# Migración Tanda 1 (Clientes + Productos) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Migrar las pantallas Clientes y Productos del tema oscuro legacy al design system claro, creando la base compartida (`gestion.css`, patrón GESTIÓN, `mostrarMensaje` global) que reutilizarán las tandas 2-6.

**Architecture:** Patrón espejo de `registros_light.css`: `base.html` marca las rutas migradas con `body[data-gestion-screen]` y carga `static/css/gestion.css` (scoping de tokens claros + componentes de lista). Los templates se reescriben al patrón GESTIÓN (lista-primero + búsqueda client-side + form de crear colapsado). El JS de productos sale de `scripts.js` a `static/js/productos.js` (vanilla; `base.js` ya parchea `window.fetch` con CSRF). **`static/scripts.js` NO se toca en esta tanda** — sigue sirviendo a facturación/recepciones hasta sus tandas.

**Tech Stack:** Flask/Jinja2, CSS vanilla (tokens + primitives existentes), JS vanilla, pytest.

**Spec:** `docs/superpowers/specs/2026-07-01-migracion-lote-oscuro-design.md`

**Contexto crítico para el implementador (no lo sabes si no has leído el repo):**

- El tema global es OSCURO (`dark-theme.css` con `!important`). Las pantallas claras re-aclaran solo su contenido con CSS scopeado a un `data-*` del body, cargado DESPUÉS en la cascada. Copia el mecanismo de `static/css/registros_light.css`.
- `static/js/base.js` (servido como `base.min.js`) ya define `window.escapeHtml`, parchea `window.fetch` para inyectar `X-CSRFToken`, y delega clicks de `[data-remove-producto]` a `window.eliminarProducto` — **ese nombre global está reservado; no lo definas**.
- Tras editar `static/js/base.js` SIEMPRE ejecutar `cp static/js/base.js static/js/base.min.js` (no hay minificador; `base.html` carga el .min).
- `POST /clientes/nuevo` y `POST /productos` devuelven SIEMPRE JSON (app.py:8205, análogo en productos). Hoy el form de clientes hace POST nativo y el usuario ve JSON crudo — el rediseño lo maneja con `fetch`.
- Los templates de editar (`cliente_form.html`, `editar_producto.html`) YA usan clases `.mobile-*`; con el scoping de tokens quedan claros sin tocarlos.
- Los tests se corren `.venv/bin/python -m pytest ... -q` SIN forzar `DATABASE_URL` de archivo (el propio test setea sqlite memory).
- Trabajamos en `main` local; **NO hacer `git push`** (push = deploy a Heroku; lo gatilla el usuario al final).
- Los deletes de estas pantallas confirman con `confirm()` dentro del handler fetch, NO con el atributo `data-confirm`: esa convención de base.js intercepta submits de `<form>`, y aquí los deletes son llamadas fetch DELETE/POST sin form. No "corregir" esto hacia data-confirm.

**Files:**

| Acción | Path | Responsabilidad |
|---|---|---|
| Create | `tests/test_gestion_ui.py` | Smoke tests de la tanda (sueltos: ids/data-attrs, no markup exacto) |
| Create | `static/css/gestion.css` | Scope claro + componentes del patrón GESTIÓN (compartido tandas 1-5) |
| Create | `static/js/productos.js` | JS de la pantalla Productos (extraído de scripts.js, vanilla) |
| Modify | `templates/base.html` | body attr `data-gestion-screen` + link condicional a gestion.css |
| Modify | `static/js/base.js` (+ regenerar `base.min.js`) | `window.mostrarMensaje` global |
| Modify | `templates/clientes.html` | Reescritura al patrón GESTIÓN |
| Modify | `templates/productos.html` | Reescritura al patrón GESTIÓN |

---

### Task 1: Tests de infraestructura (fallando)

**Files:**
- Create: `tests/test_gestion_ui.py`

- [ ] **Step 1: Escribir el archivo de tests con los tests de infraestructura**

```python
"""Smoke tests — migración del lote oscuro al design system claro (Tanda 1).
Spec: docs/superpowers/specs/2026-07-01-migracion-lote-oscuro-design.md

A propósito se asserta sobre ids y data-attributes (no markup exacto) para
no repetir el "test rot" de test_dashboard_kpis/test_etiquetas.
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
        from app import Rol, Territorio, Vendedor, Cliente, Producto

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
        _db.session.add(Cliente(nombre="Cliente Uno", moneda="USD", qbo_id="QBO-77"))
        _db.session.add(
            Producto(nombre="Producto Uno", proveedor="Prov Test", se_pesa=True, tax_rate=10)
        )
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


# ---------------------------------------------------------------------------
# Infraestructura compartida (base.html + gestion.css)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("path", ["/clientes", "/productos"])
def test_gestion_route_returns_200(logged_client, path):
    response = logged_client.get(path)
    assert response.status_code == 200, f"{path} returned {response.status_code}"


@pytest.mark.parametrize("path", ["/clientes", "/productos"])
def test_gestion_css_is_linked(logged_client, path):
    response = logged_client.get(path)
    assert b"css/gestion.css" in response.data, f"gestion.css link missing from {path}"


@pytest.mark.parametrize("path", ["/clientes", "/productos"])
def test_body_has_gestion_screen_attr(logged_client, path):
    response = logged_client.get(path)
    assert b'data-gestion-screen="1"' in response.data, (
        f"data-gestion-screen missing from {path} body"
    )


@pytest.mark.parametrize("path", ["/dashboard", "/pedidos"])
def test_non_gestion_routes_lack_gestion_attrs(logged_client, path):
    """El scope claro NO debe filtrarse a pantallas que no son de gestión."""
    response = logged_client.get(path)
    assert b'data-gestion-screen="1"' not in response.data
    assert b"css/gestion.css" not in response.data
```

- [ ] **Step 2: Correr los tests y verificar que fallan los de infraestructura**

Run: `.venv/bin/python -m pytest tests/test_gestion_ui.py -q`
Expected: 4 FAIL (`test_gestion_css_is_linked`, `test_body_has_gestion_screen_attr` × 2 paths), 4 PASS (los 200 y los negativos ya pasan).

---

### Task 2: base.html — body attr + link condicional

**Files:**
- Modify: `templates/base.html` (línea ~106 el link, línea ~109 el body)

- [ ] **Step 1: Agregar el link condicional a gestion.css**

En `templates/base.html`, localizar el link de `registros_light.css` (línea ~106, dentro de su condicional de `/registros`). Inmediatamente DESPUÉS de ese bloque condicional, agregar:

```jinja
{% if request.path.startswith(('/clientes', '/productos')) %}
    <link rel="stylesheet" href="{{ url_for('static', filename='css/gestion.css') }}">
{% endif %}
```

Nota: `startswith` con tupla es Python válido dentro de Jinja. En tandas futuras la tupla crece (`'/facturacion'`, `'/recepciones'`, etc.).

- [ ] **Step 2: Agregar data-gestion-screen al body**

En la línea del `<body>` (~109), el bloque `body_attrs` termina con:

```jinja
{% elif request.path.startswith('/admin/vendedores') %} data-ops-shell="1"{% endif %}
```

Cambiarlo a:

```jinja
{% elif request.path.startswith('/admin/vendedores') %} data-ops-shell="1"{% elif request.path.startswith(('/clientes', '/productos')) %} data-gestion-screen="1"{% endif %}
```

- [ ] **Step 3: Correr los tests de infraestructura**

Run: `.venv/bin/python -m pytest tests/test_gestion_ui.py -q`
Expected: los 4 que fallaban ahora PASS (gestion.css devuelve 404 como estático pero el LINK ya aparece en el HTML; el archivo se crea en Task 3). 8 PASS total.

---

### Task 3: static/css/gestion.css

**Files:**
- Create: `static/css/gestion.css`

- [ ] **Step 1: Crear el archivo completo**

```css
/* =============================================================================
   PesosApp · gestion.css — pantallas de gestión migradas al design system claro
   Spec: docs/superpowers/specs/2026-07-01-migracion-lote-oscuro-design.md

   Espejo de registros_light.css: el tema global sigue siendo oscuro
   (dark-theme.css, overrides con !important) mientras duren las tandas.
   Aquí re-aclaramos SOLO el contenido de las pantallas marcadas por base.html
   con body[data-gestion-screen]. Carga después de dark-theme.css en la cascada.
   Servido directo (sin minificar), como registros.css.
   ============================================================================= */

/* ── 1 · Fondo del área de contenido ─────────────────────────────────────── */
body[data-gestion-screen] .app-content,
body[data-gestion-screen] .mobile-form-container {
  background: #f8fafc !important;
  background-image: none !important;
}

/* ── 2 · Tokens claros scopeados al wrapper de contenido.
      NUNCA al body: hay JS que lee getComputedStyle(document.body) y vería
      los tokens oscuros (lección de la firma/canvas en pantallas ops).
      .mobile-form-container cubre las páginas de editar (cliente_form.html,
      editar_producto.html) sin tocar sus templates. ─────────────────────── */
body[data-gestion-screen] .gestion-wrap,
body[data-gestion-screen] .mobile-form-container {
  --color-bg: #ffffff;
  --color-bg-elevated: #ffffff;
  --color-bg-subtle: #f8fafc;
  --color-surface: #ffffff;
  --color-surface-muted: #f1f5f9;
  --color-surface-strong: rgba(255, 255, 255, 0.92);
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

/* ── 3 · Neutralizar el "recuadro" genérico de <form> (dark-theme.css /
      forms.css / styles.min.css le ponen fondo+sombra+padding a todo form) ── */
body[data-gestion-screen] .gestion-wrap form,
body[data-gestion-screen] .mobile-form-container form {
  background: transparent !important;
  box-shadow: none !important;
  padding: 0 !important;
  border: 0 !important;
  border-radius: 0 !important;
}

/* ── 4 · Reverts de dark-theme para los componentes .mobile-* dentro del
      scope (mismos valores que registros_light.css) ───────────────────── */
body[data-gestion-screen] .mobile-card {
  background: #ffffff !important;
  box-shadow: 0 10px 32px -12px rgba(15, 23, 42, 0.08) !important;
  border: 1px solid #e2e8f0 !important;
}
body[data-gestion-screen] .mobile-card-body { color: #0f172a !important; }
body[data-gestion-screen] .mobile-card-header {
  background: #f8fafc !important;
  color: #0f172a !important;
  border-bottom: 1px solid #e2e8f0 !important;
}
body[data-gestion-screen] .mobile-form-label { color: #475569 !important; }
body[data-gestion-screen] .mobile-form-control,
body[data-gestion-screen] .gestion-wrap input,
body[data-gestion-screen] .gestion-wrap select,
body[data-gestion-screen] .gestion-wrap textarea,
body[data-gestion-screen] .mobile-form-container input,
body[data-gestion-screen] .mobile-form-container select,
body[data-gestion-screen] .mobile-form-container textarea {
  background: #ffffff !important;
  border-color: #e2e8f0 !important;
  color: #0f172a !important;
}
body[data-gestion-screen] .gestion-wrap input::placeholder,
body[data-gestion-screen] .mobile-form-container input::placeholder {
  color: #94a3b8 !important;
}
body[data-gestion-screen] .mobile-btn-secondary {
  background: #ffffff !important;
  color: #0f172a !important;
  border: 1px solid #e2e8f0 !important;
}

/* ── 5 · Layout del patrón GESTIÓN ───────────────────────────────────────── */
.gestion-wrap {
  display: flex;
  flex-direction: column;
  gap: 14px;
  padding: 8px 14px 90px; /* laterales: .app-content no aporta padding aquí; bottom: respiro sobre la tabbar fija */
}

.gestion-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}
body[data-gestion-screen] .gestion-title {
  margin: 0;
  font-size: 1.6rem;
  font-weight: 800;
  letter-spacing: -0.02em;
  color: #0f172a;
}
.gestion-new-btn { flex: 0 0 auto; }

/* Búsqueda */
body[data-gestion-screen] .gestion-search {
  width: 100%;
  min-height: 46px;
  padding: 10px 16px;
  font-size: 16px; /* evita zoom de iOS */
  border-radius: 14px;
  border: 1px solid #e2e8f0 !important;
  background: #ffffff !important;
  color: #0f172a !important;
  box-shadow: 0 4px 14px -8px rgba(15, 23, 42, 0.08);
}
body[data-gestion-screen] .gestion-search:focus {
  outline: none;
  border-color: #2563eb !important;
  box-shadow: 0 0 0 3px rgba(37, 99, 235, 0.18);
}

/* Form de crear colapsable */
.gestion-create[hidden] { display: none !important; }

/* Lista de filas */
.gestion-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 10px;
}
body[data-gestion-screen] .gestion-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  background: #ffffff;
  border: 1px solid #eef2f7;
  border-radius: var(--radius-xl, 20px);
  padding: 14px 16px;
  box-shadow: 0 10px 32px -12px rgba(15, 23, 42, 0.08);
}
.gestion-row[hidden] { display: none !important; }

.gestion-row-main {
  display: flex;
  flex-direction: column;
  gap: 6px;
  min-width: 0; /* permite ellipsis interno sin romper el flex */
}
body[data-gestion-screen] .gestion-row-name {
  font-weight: 700;
  font-size: 1.02rem;
  color: #0f172a;
  overflow-wrap: anywhere; /* nombre completo visible: se parte, no se trunca */
}
body[data-gestion-screen] .gestion-row-sub {
  font-size: 0.85rem;
  color: #64748b;
}
.gestion-row-badges {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

/* Acciones por fila (touch targets 40px, aria-label en el template) */
.gestion-row-actions {
  display: flex;
  gap: 8px;
  flex: 0 0 auto;
}
body[data-gestion-screen] .gestion-icon-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 40px;
  height: 40px;
  border-radius: 12px;
  border: 1px solid transparent;
  cursor: pointer;
  font-size: 0.95rem;
  text-decoration: none;
  transition: background 0.15s ease, color 0.15s ease;
}
body[data-gestion-screen] .gestion-icon-edit {
  background: #eef4ff !important;
  color: #2b7cff !important;
}
body[data-gestion-screen] .gestion-icon-edit:hover { background: #d9e8ff !important; }
body[data-gestion-screen] .gestion-icon-delete {
  background: #ffecec !important;
  color: #dc3545 !important;
}
body[data-gestion-screen] .gestion-icon-delete:hover { background: #ffd3d3 !important; }
.gestion-icon-btn i { pointer-events: none; }

/* Estado vacío */
body[data-gestion-screen] .gestion-empty {
  list-style: none;
  text-align: center;
  padding: 32px 16px;
  color: #94a3b8;
  background: #ffffff;
  border: 1px dashed #e2e8f0;
  border-radius: var(--radius-xl, 20px);
}

/* Chips (primitives.css) — asegurar contraste claro dentro del scope */
body[data-gestion-screen] .chip {
  background: var(--color-surface-muted);
  color: var(--color-text-muted);
}
body[data-gestion-screen] .chip-success { background: var(--color-success-soft); color: var(--color-success-soft-fg); }
body[data-gestion-screen] .chip-warning { background: var(--color-warning-soft); color: var(--color-warning-soft-fg); }
body[data-gestion-screen] .chip-info    { background: var(--color-info-soft);    color: var(--color-info-soft-fg); }
body[data-gestion-screen] .chip-primary { background: var(--color-primary-soft); color: var(--color-primary-soft-fg); }
```

- [ ] **Step 2: Verificar que el estático se sirve**

Run: `curl -s -o /dev/null -w "%{http_code}" http://localhost:5002/static/css/gestion.css` (con el server de preview corriendo; si no, `ls -la static/css/gestion.css`)
Expected: `200` (o el archivo listado).

- [ ] **Step 3: Commit de la fundación**

```bash
git add tests/test_gestion_ui.py templates/base.html static/css/gestion.css
git commit -m "feat(gestion): fundación tanda 1 — scope claro data-gestion-screen + gestion.css + smoke tests"
```

---

### Task 4: window.mostrarMensaje en base.js

**Files:**
- Modify: `static/js/base.js` (insertar tras `window.escapeHtml`, línea ~10)
- Regenerar: `static/js/base.min.js`

- [ ] **Step 1: Agregar el helper global**

En `static/js/base.js`, inmediatamente después del cierre de la función `window.escapeHtml` (línea ~10), insertar:

```javascript
// Flash message global (una sola fuente; antes vivía duplicado en scripts.js
// con jQuery). Requiere un <div id="flash-message" class="flash-message"> en
// el template. tipo: 'success' | cualquier otro valor → estilo error.
window.mostrarMensaje = function (mensaje, tipo) {
    var el = document.getElementById('flash-message');
    if (!el) { alert(mensaje); return; }
    el.className = 'flash-message ' + (tipo === 'success' ? 'success' : 'error');
    el.textContent = mensaje; // textContent evita XSS con datos del servidor
    el.style.display = 'block';
    clearTimeout(el._flashTimer);
    el._flashTimer = setTimeout(function () { el.style.display = 'none'; }, 3000);
};
```

- [ ] **Step 2: Regenerar base.min.js**

```bash
cp static/js/base.js static/js/base.min.js
```

- [ ] **Step 3: Verificación rápida en consola del preview**

Con el server corriendo, en cualquier página: `preview_eval` → `typeof window.mostrarMensaje` debe devolver `"function"` (tras recargar).

- [ ] **Step 4: Commit**

```bash
git add static/js/base.js static/js/base.min.js
git commit -m "feat(base.js): window.mostrarMensaje global (única fuente para flash de gestión)"
```

---

### Task 5: Tests de markup de Clientes (fallando)

**Files:**
- Modify: `tests/test_gestion_ui.py` (agregar al final)

- [ ] **Step 1: Agregar los tests**

```python
# ---------------------------------------------------------------------------
# Clientes — patrón GESTIÓN
# ---------------------------------------------------------------------------


def test_clientes_patron_gestion(logged_client):
    html = logged_client.get("/clientes").data
    assert b'id="buscar-cliente"' in html, "input de búsqueda missing"
    assert b'id="crear-cliente-card"' in html, "card de crear missing"
    assert b'id="btn-nuevo-cliente"' in html, "botón + Nuevo missing"
    assert b'id="form-cliente"' in html, "form de crear missing (el POST AJAX depende de este id)"
    assert b"Cliente Uno" in html, "fila del cliente seed missing"
    assert b"gestion-row" in html, "filas .gestion-row missing"


def test_clientes_sin_legacy(logged_client):
    html = logged_client.get("/clientes").data
    assert b"font-awesome/6.4.2" not in html, "FA 6.4.2 duplicado debe eliminarse (global es 6.7.2)"
    assert b"tabla-clientes" not in html, "la tabla legacy debe reemplazarse por .gestion-list"
    assert b"code.jquery.com" not in html, "clientes ya no necesita jQuery CDN"
```

- [ ] **Step 2: Correr y verificar que fallan**

Run: `.venv/bin/python -m pytest tests/test_gestion_ui.py -q`
Expected: 2 FAIL (los nuevos), el resto PASS.

---

### Task 6: Reescribir templates/clientes.html

**Files:**
- Modify: `templates/clientes.html` (reemplazo completo del archivo)

- [ ] **Step 1: Reemplazar el contenido completo del archivo por:**

```jinja
{% extends "base.html" %}

{% block title %}Clientes{% endblock %}

{% block header_title %}
  <i class="fas fa-users color-purple mr-8"></i>Clientes
{% endblock %}

{% block content %}
<div class="gestion-wrap">
  <div id="flash-message" class="flash-message hidden"></div>

  <div class="gestion-header">
    <h1 class="gestion-title">Clientes</h1>
    <button type="button" id="btn-nuevo-cliente" class="mobile-btn mobile-btn-primary gestion-new-btn">
      <i class="fas fa-plus"></i> Nuevo
    </button>
  </div>

  <section id="crear-cliente-card" class="mobile-card gestion-create" hidden>
    <div class="mobile-card-header">
      <i class="fas fa-user-plus"></i> Registrar Nuevo Cliente
    </div>
    <div class="mobile-card-body">
      <form id="form-cliente" method="POST" action="{{ url_for('nuevo_cliente') }}">
        <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
        <div class="mobile-form-group">
          <label for="nombre-cliente" class="mobile-form-label">Nombre:</label>
          <input id="nombre-cliente" name="nombre" class="mobile-form-control" required>
        </div>
        <div class="mobile-form-group">
          <label for="qbo-cliente" class="mobile-form-label">QBO ID <small>(opcional)</small>:</label>
          <input id="qbo-cliente" name="qbo_id" class="mobile-form-control">
        </div>
        <div class="mobile-form-group">
          <label for="moneda-cliente" class="mobile-form-label">Moneda:</label>
          <select id="moneda-cliente" name="moneda" class="mobile-form-control">
            <option value="XCG">XCG (Guilder)</option>
            <option value="USD">USD (Dólar)</option>
          </select>
        </div>
        <div class="mobile-form-actions">
          <button type="button" id="btn-cancelar-cliente" class="mobile-btn mobile-btn-secondary">
            <i class="fas fa-times"></i> Cancelar
          </button>
          <button type="submit" class="mobile-btn mobile-btn-primary">
            <i class="fas fa-plus"></i> Registrar
          </button>
        </div>
      </form>
    </div>
  </section>

  <input type="search" id="buscar-cliente" class="gestion-search"
         placeholder="Buscar cliente…" autocomplete="off"
         aria-label="Buscar cliente">

  <ul id="lista-clientes" class="gestion-list">
    {% for c in clientes %}
    <li class="gestion-row" id="cliente-{{ c.id }}" data-buscar="{{ c.nombre|lower }}">
      <div class="gestion-row-main">
        <span class="gestion-row-name">{{ c.nombre }}</span>
        <span class="gestion-row-badges">
          <span class="chip {{ 'chip-warning' if c.moneda == 'USD' else '' }}">{{ c.moneda or 'XCG' }}</span>
          {% if c.qbo_id %}
          <span class="chip chip-success" title="Integrado a QuickBooks">QBO {{ c.qbo_id }}</span>
          {% else %}
          <span class="chip" title="Sin QBO ID">Sin QBO</span>
          {% endif %}
        </span>
      </div>
      <div class="gestion-row-actions">
        <a href="{{ url_for('editar_cliente', cliente_id=c.id) }}"
           class="gestion-icon-btn gestion-icon-edit" title="Editar"
           aria-label="Editar {{ c.nombre }}"><i class="fas fa-pen"></i></a>
        <button type="button"
                class="gestion-icon-btn gestion-icon-delete eliminar-cliente"
                data-id="{{ c.id }}" title="Eliminar"
                aria-label="Eliminar {{ c.nombre }}"><i class="fas fa-trash"></i></button>
      </div>
    </li>
    {% else %}
    <li class="gestion-empty">No hay clientes registrados todavía.</li>
    {% endfor %}
  </ul>
</div>
{% endblock %}

{% block scripts %}
<script nonce="{{ csp_nonce() }}">
(function () {
  'use strict';

  // Flash diferido (tras crear + reload). OJO: este block scripts se renderiza
  // ANTES de base.min.js en base.html, así que window.mostrarMensaje aún no
  // existe en parse-time — diferir a DOMContentLoaded (base.min.js es script
  // síncrono y ya habrá cargado para entonces).
  var flash = sessionStorage.getItem('gestionFlash');
  if (flash) {
    sessionStorage.removeItem('gestionFlash');
    document.addEventListener('DOMContentLoaded', function () {
      if (window.mostrarMensaje) window.mostrarMensaje(flash, 'success');
    });
  }

  // Abrir/cerrar el form de crear
  var createCard = document.getElementById('crear-cliente-card');
  document.getElementById('btn-nuevo-cliente').addEventListener('click', function () {
    var abrir = createCard.hidden;
    createCard.hidden = !abrir;
    if (abrir) document.getElementById('nombre-cliente').focus();
  });
  document.getElementById('btn-cancelar-cliente').addEventListener('click', function () {
    createCard.hidden = true;
  });

  // Búsqueda client-side
  document.getElementById('buscar-cliente').addEventListener('input', function () {
    var q = this.value.trim().toLowerCase();
    document.querySelectorAll('#lista-clientes .gestion-row').forEach(function (row) {
      row.hidden = !!q && row.dataset.buscar.indexOf(q) === -1;
    });
  });

  // Crear cliente — el endpoint SIEMPRE responde JSON (app.py nuevo_cliente),
  // así que el submit nativo mostraría JSON crudo; se maneja con fetch.
  // base.js ya inyecta X-CSRFToken en fetch; el token de form va en FormData.
  var form = document.getElementById('form-cliente');
  form.addEventListener('submit', function (e) {
    e.preventDefault();
    var submitBtn = form.querySelector('button[type="submit"]');
    submitBtn.disabled = true; // evita doble submit (doble tap en móvil)
    fetch(form.action, {
      method: 'POST',
      body: new FormData(form),
      headers: { 'X-Requested-With': 'XMLHttpRequest' }
    })
      .then(function (r) {
        return r.json().catch(function () { return { error: 'Error al registrar el cliente' }; });
      })
      .then(function (res) {
        if (res.error) {
          window.mostrarMensaje(res.error, 'error');
          submitBtn.disabled = false;
          return;
        }
        // Reload: la fila la renderiza el servidor (una sola fuente de markup)
        sessionStorage.setItem('gestionFlash', res.message || 'Cliente registrado');
        window.location.reload();
      })
      .catch(function () {
        window.mostrarMensaje('Error al registrar el cliente', 'error');
        submitBtn.disabled = false;
      });
  });

  // Eliminar cliente (delegación scoped a la lista)
  document.getElementById('lista-clientes').addEventListener('click', function (e) {
    var btn = e.target.closest('.eliminar-cliente');
    if (!btn) return;
    if (!confirm('¿Eliminar este cliente?')) return;
    fetch('/clientes/' + btn.dataset.id, {
      method: 'DELETE',
      headers: { 'X-Requested-With': 'XMLHttpRequest' }
    })
      .then(function (r) { return r.json().catch(function () { return {}; }); })
      .then(function (res) {
        if (res.message) {
          var row = document.getElementById('cliente-' + btn.dataset.id);
          if (row) row.remove();
          window.mostrarMensaje(res.message, 'success');
        } else {
          window.mostrarMensaje(res.error || 'Error al eliminar', 'error');
        }
      })
      .catch(function () { window.mostrarMensaje('Error al eliminar', 'error'); });
  });
})();
</script>
{% endblock %}
```

Notas de lo eliminado deliberadamente: el bloque `extra_css` entero (166 líneas inline + Font Awesome 6.4.2 duplicado), el jQuery CDN, y la columna ID.

- [ ] **Step 2: Correr los tests de clientes**

Run: `.venv/bin/python -m pytest tests/test_gestion_ui.py -q`
Expected: todos PASS.

- [ ] **Step 3: Verificación visual e interactiva en el preview**

Con el server de preview (launch.json `pesosapp`, puerto 5002; login `admin` / `Preview123!`):
1. Viewport móvil 375px → `/clientes`: fondo claro, header "Clientes" + botón Nuevo, búsqueda, filas con chips. Captura.
2. Tocar "＋ Nuevo" → se expande el form con foco en Nombre; "Cancelar" lo colapsa.
3. Crear un cliente de prueba ("Test Preview") → recarga + flash "Cliente registrado" + aparece en la lista.
4. Buscar "test" → filtra; borrar búsqueda → vuelven todas.
5. Eliminar el cliente de prueba → confirm + fila desaparece + flash.
6. Abrir `/clientes/1/editar` → la página de editar se ve CLARA (hereda por `.mobile-form-container` en el scope) sin tocar su template.
7. Consola sin errores (`preview_console_logs` level=error → vacío en esta página).

- [ ] **Step 4: Commit**

```bash
git add templates/clientes.html tests/test_gestion_ui.py
git commit -m "feat(clientes): migra al design system claro con patrón GESTIÓN (lista+búsqueda, crear colapsado)"
```

---

### Task 7: Tests de markup de Productos (fallando)

**Files:**
- Modify: `tests/test_gestion_ui.py` (agregar al final)

- [ ] **Step 1: Agregar los tests**

```python
# ---------------------------------------------------------------------------
# Productos — patrón GESTIÓN
# ---------------------------------------------------------------------------


def test_productos_patron_gestion(logged_client):
    html = logged_client.get("/productos").data
    assert b'id="buscar-producto"' in html, "input de búsqueda missing"
    assert b'id="crear-producto-card"' in html, "card de crear missing"
    assert b'id="btn-nuevo-producto"' in html, "botón + Nuevo missing"
    assert b'id="form-crear-producto"' in html, "form de crear missing (id usado por productos.js)"
    assert b"Producto Uno" in html, "fila del producto seed missing"
    assert b"js/productos.js" in html, "productos.js debe estar linkeado"


def test_productos_sin_legacy(logged_client):
    html = logged_client.get("/productos").data
    assert b"static/scripts.js" not in html, (
        "productos.html ya no debe cargar el scripts.js compartido"
    )
    assert b"code.jquery.com" not in html, "productos ya no necesita jQuery CDN"
    assert b"Se pesa" in html, "el chip 'Se pesa' del producto seed debe renderizarse"
```

- [ ] **Step 2: Correr y verificar que fallan**

Run: `.venv/bin/python -m pytest tests/test_gestion_ui.py -q`
Expected: 2 FAIL (los nuevos), el resto PASS.

---

### Task 8: static/js/productos.js

**Files:**
- Create: `static/js/productos.js`

- [ ] **Step 1: Crear el archivo completo**

```javascript
/* Productos — lógica de la pantalla /productos.
   Extraída de static/scripts.js (sección "Manejo de Productos") en la tanda 1
   de la migración del lote oscuro, reescrita en vanilla: base.js ya parchea
   window.fetch con X-CSRFToken y expone window.escapeHtml/window.mostrarMensaje.

   OJO: NO definir window.eliminarProducto — ese nombre global está reservado
   por la convención [data-remove-producto] de base.js (form de pedidos). */
(function () {
    'use strict';

    var form = document.getElementById('form-crear-producto');
    var lista = document.getElementById('lista-productos');
    if (!form || !lista) return; // guarda: solo corre en /productos

    // Flash diferido (tras crear + reload). OJO: base.html incluye este script
    // ANTES de base.min.js, así que window.mostrarMensaje aún no existe en
    // parse-time — diferir a DOMContentLoaded (base.min.js es script síncrono
    // y ya habrá cargado para entonces).
    var flash = sessionStorage.getItem('gestionFlash');
    if (flash) {
        sessionStorage.removeItem('gestionFlash');
        document.addEventListener('DOMContentLoaded', function () {
            if (window.mostrarMensaje) window.mostrarMensaje(flash, 'success');
        });
    }

    // Abrir/cerrar el form de crear
    var createCard = document.getElementById('crear-producto-card');
    document.getElementById('btn-nuevo-producto').addEventListener('click', function () {
        var abrir = createCard.hidden;
        createCard.hidden = !abrir;
        if (abrir) document.getElementById('nombre').focus();
    });
    document.getElementById('btn-cancelar-producto').addEventListener('click', function () {
        createCard.hidden = true;
    });

    // Búsqueda client-side (nombre + proveedor, ver data-buscar en el template)
    document.getElementById('buscar-producto').addEventListener('input', function () {
        var q = this.value.trim().toLowerCase();
        lista.querySelectorAll('.gestion-row').forEach(function (row) {
            row.hidden = !!q && row.dataset.buscar.indexOf(q) === -1;
        });
    });

    // Crear producto — el endpoint responde JSON; reload para que la fila la
    // renderice el servidor (única fuente de markup; reemplaza al viejo
    // agregarProductoATabla que insertaba filas desalineadas por JS).
    form.addEventListener('submit', function (e) {
        e.preventDefault();
        var submitBtn = form.querySelector('button[type="submit"]');
        submitBtn.disabled = true; // evita doble submit (doble tap en móvil)
        fetch(form.action, {
            method: 'POST',
            body: new FormData(form),
            headers: { 'X-Requested-With': 'XMLHttpRequest' }
        })
            .then(function (r) {
                return r.json().catch(function () { return { error: 'Error al crear el producto' }; });
            })
            .then(function (res) {
                if (res.error) {
                    window.mostrarMensaje(res.error, 'error');
                    submitBtn.disabled = false;
                    return;
                }
                sessionStorage.setItem('gestionFlash', res.message || 'Producto creado');
                window.location.reload();
            })
            .catch(function () {
                window.mostrarMensaje('Error al crear el producto', 'error');
                submitBtn.disabled = false;
            });
    });

    // Eliminar producto (delegación scoped a la lista)
    lista.addEventListener('click', function (e) {
        var btn = e.target.closest('.eliminar-producto');
        if (!btn) return;
        if (!confirm('¿Eliminar este producto?')) return;
        var body = new URLSearchParams();
        body.set('accion', 'eliminar');
        fetch('/productos/' + btn.dataset.id + '/eliminar', {
            method: 'POST',
            headers: {
                'X-Requested-With': 'XMLHttpRequest',
                'Content-Type': 'application/x-www-form-urlencoded'
            },
            body: body.toString()
        })
            .then(function (r) { return r.json().catch(function () { return {}; }); })
            .then(function (res) {
                if (res.error) { window.mostrarMensaje(res.error, 'error'); return; }
                var row = document.getElementById('producto-' + btn.dataset.id);
                if (row) row.remove();
                window.mostrarMensaje(res.message || 'Producto eliminado', 'success');
            })
            .catch(function () { window.mostrarMensaje('Error al eliminar el producto.', 'error'); });
    });
})();
```

- [ ] **Step 2: Sanity check de sintaxis**

Run: `node --check static/js/productos.js`
Expected: sin output (exit 0).

---

### Task 9: Reescribir templates/productos.html

**Files:**
- Modify: `templates/productos.html` (reemplazo completo del archivo)

- [ ] **Step 1: Reemplazar el contenido completo del archivo por:**

```jinja
{% extends "base.html" %}

{% block title %}Productos{% endblock %}

{% block header_title %}
<i class="fas fa-box color-salmon mr-10"></i>Productos
{% endblock %}

{% block content %}
<div class="gestion-wrap">
  <div id="flash-message" class="flash-message hidden"></div>

  <div class="gestion-header">
    <h1 class="gestion-title">Productos</h1>
    <button type="button" id="btn-nuevo-producto" class="mobile-btn mobile-btn-primary gestion-new-btn">
      <i class="fas fa-plus"></i> Nuevo
    </button>
  </div>

  <section id="crear-producto-card" class="mobile-card gestion-create" hidden>
    <div class="mobile-card-header">
      <i class="fas fa-box-open"></i> Registrar Producto
    </div>
    <div class="mobile-card-body">
      <form id="form-crear-producto" method="POST" action="{{ url_for('productos') }}">
        <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
        <div class="mobile-form-group">
          <label for="nombre" class="mobile-form-label">Nombre del Producto:</label>
          <input type="text" id="nombre" name="nombre" required class="mobile-form-control">
        </div>
        <div class="mobile-form-group">
          <label for="descripcion" class="mobile-form-label">Descripción:</label>
          <input type="text" id="descripcion" name="descripcion" class="mobile-form-control">
        </div>
        <div class="mobile-form-group">
          <label for="temperatura" class="mobile-form-label">Temperatura:</label>
          <input type="text" id="temperatura" name="temperatura" class="mobile-form-control">
        </div>
        <div class="mobile-form-group">
          <label for="proveedor" class="mobile-form-label">Proveedor:</label>
          <input type="text" id="proveedor" name="proveedor" class="mobile-form-control"
                 placeholder="Ej: Distribuidora ABC">
        </div>
        <div class="mobile-form-group">
          <label for="qbo-producto" class="mobile-form-label">QBO ID (opcional):</label>
          <input type="text" id="qbo-producto" name="qbo_id" class="mobile-form-control">
        </div>
        <div class="mobile-form-group">
          <label for="tax_rate" class="mobile-form-label">TaxCode ID:</label>
          <select id="tax_rate" name="tax_rate" class="mobile-form-control">
            <option value="10">OB 6%</option>
            <option value="14">OB Non Tax Local Prod (0%)</option>
          </select>
        </div>
        <div class="mobile-form-group">
          <label class="mobile-checkbox-label">
            <input type="checkbox" name="se_pesa" value="1" class="mobile-checkbox">
            Se pesa (producto de manufactura que se pesa por caja)
          </label>
        </div>
        <div class="mobile-form-actions">
          <button type="button" id="btn-cancelar-producto" class="mobile-btn mobile-btn-secondary">
            <i class="fas fa-times"></i> Cancelar
          </button>
          <button type="submit" class="mobile-btn mobile-btn-primary">
            <i class="fas fa-plus"></i> Crear Producto
          </button>
        </div>
      </form>
    </div>
  </section>

  <input type="search" id="buscar-producto" class="gestion-search"
         placeholder="Buscar producto o proveedor…" autocomplete="off"
         aria-label="Buscar producto">

  <ul id="lista-productos" class="gestion-list">
    {% for producto in productos %}
    <li class="gestion-row" id="producto-{{ producto.id }}"
        data-buscar="{{ producto.nombre|lower }} {{ (producto.proveedor or '')|lower }}">
      <div class="gestion-row-main">
        <span class="gestion-row-name">{{ producto.nombre }}</span>
        <span class="gestion-row-sub">
          {{ producto.proveedor or 'Sin proveedor' }}{% if producto.descripcion %} · {{ producto.descripcion }}{% endif %}
        </span>
        <span class="gestion-row-badges">
          {% if producto.se_pesa %}<span class="chip chip-info"><i class="fas fa-weight-hanging"></i> Se pesa</span>{% endif %}
          <span class="chip">{{ 'OB 6%' if producto.tax_rate|int == 10 else ('OB 0%' if producto.tax_rate|int == 14 else 'Tax ' ~ producto.tax_rate|int) }}</span>
          {% if producto.qbo_id %}
          <span class="chip chip-success" title="Integrado a QuickBooks">QBO {{ producto.qbo_id }}</span>
          {% else %}
          <span class="chip" title="Sin QBO ID">Sin QBO</span>
          {% endif %}
          {% if producto.temperatura %}<span class="chip">{{ producto.temperatura }}</span>{% endif %}
        </span>
      </div>
      <div class="gestion-row-actions">
        <a href="{{ url_for('editar_producto', producto_id=producto.id) }}"
           class="gestion-icon-btn gestion-icon-edit" title="Editar"
           aria-label="Editar {{ producto.nombre }}"><i class="fas fa-pen"></i></a>
        <button type="button"
                class="gestion-icon-btn gestion-icon-delete eliminar-producto"
                data-id="{{ producto.id }}" title="Eliminar"
                aria-label="Eliminar {{ producto.nombre }}"><i class="fas fa-trash"></i></button>
      </div>
    </li>
    {% else %}
    <li class="gestion-empty">No hay productos registrados todavía.</li>
    {% endfor %}
  </ul>
</div>
{% endblock %}

{% block scripts %}
<script nonce="{{ csp_nonce() }}" src="{{ url_for('static', filename='js/productos.js') }}"></script>
{% endblock %}
```

Notas de lo eliminado deliberadamente: bloque `extra_css` (50 líneas inline), jQuery CDN, `scripts.js` compartido (su sección de productos queda muerta ahí hasta que las tandas 2-3 la vacíen del todo), el script inline de padding del footer (el padding ya lo da `.gestion-wrap`), y la columna ID.

- [ ] **Step 2: Correr toda la suite de la tanda**

Run: `.venv/bin/python -m pytest tests/test_gestion_ui.py -q`
Expected: todos PASS.

- [ ] **Step 3: Correr la suite completa (regresiones)**

Run: `.venv/bin/python -m pytest tests/ -q`
Expected: todo verde (mismo resultado que antes de la tanda; ningún test existente asserta sobre el markup viejo de clientes/productos).

- [ ] **Step 4: Verificación visual e interactiva en el preview**

Igual que en Task 6 pero para `/productos` (viewport 375px):
1. Lista clara con chips (Se pesa / OB / QBO / temperatura). Captura.
2. "＋ Nuevo" expande, crear producto de prueba → reload + flash + fila nueva.
3. Búsqueda filtra por nombre Y proveedor.
4. Eliminar el producto de prueba → confirm + desaparece.
5. `/productos/1/editar` se ve clara.
6. Consola sin errores — específicamente sin `agregarProducto is not defined` ni `Cannot read properties of null` (esta página ya no carga scripts.js).
7. Regresión rápida: `/recepciones` y `/facturacion` (aún oscuras) siguen renderizando igual que antes — scripts.js no se tocó.

- [ ] **Step 5: Commit**

```bash
git add templates/productos.html static/js/productos.js tests/test_gestion_ui.py
git commit -m "feat(productos): migra al design system claro con patrón GESTIÓN + productos.js propio"
```

---

### Task 10: Cierre de tanda

- [ ] **Step 1: Revisión final del diff completo**

Run: `git log --oneline main -6` y `git diff HEAD~4 --stat`
Expected: 4 commits de la tanda; ningún archivo fuera de los listados en la tabla de Files.

- [ ] **Step 2: Reportar al usuario**

Presentar capturas de `/clientes` y `/productos` (antes/después si es posible), resultado de la suite, y pedir OK para `git push` (deploy a Heroku). Recordar: tras el deploy, verificar en `app.jomarfoods.com` (Cloudflare cachea estáticos) y refrescar la PWA del iPhone.

**NO hacer `git push` sin el OK explícito del usuario.**
