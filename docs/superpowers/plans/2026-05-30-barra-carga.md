# Barra de carga superior — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reemplazar el overlay de carga a pantalla completa (anillo + porcentaje) por una barra de progreso superior delgada (estilo NProgress), sin número y sin bloquear la pantalla.

**Architecture:** Todo el loader vive inline en `templates/base.html` (CSS crítico + markup + script) más una copia de respaldo de las reglas CSS en `static/css/base_inline.css`. Se elimina el overlay (`app-loading-screen`, anillo SVG, `appLoadingPercent`, label) en ambos archivos y se consolida la lógica JS en un único script que muestra/gotea/completa la barra `#appLoadingBar`.

**Tech Stack:** HTML/CSS/JS vanilla inline, Jinja2 (Flask), pytest (test de regresión a nivel de fuente).

**Nota de verificación:** correr pytest con `.venv311/bin/python -m pytest` desde `/Users/josedasilva/Projects/pesosapp`.

---

### Task 1: Test de regresión (source-level, TDD)

**Files:**
- Create: `tests/test_loader_barra.py`

- [ ] **Step 1: Escribir el test que falla**

Crear `tests/test_loader_barra.py`:

```python
"""Regresión: el loader es una barra superior (NProgress), sin overlay/anillo/%.

Verifica a nivel de fuente que base.html y base_inline.css ya no contienen el
markup/estilos del overlay viejo y sí la barra de progreso.
"""
import os

ROOT = os.path.join(os.path.dirname(__file__), '..')


def _read(rel):
    with open(os.path.join(ROOT, rel), encoding='utf-8') as fh:
        return fh.read()


def test_base_html_usa_barra_sin_overlay():
    html = _read('templates/base.html')
    # La barra existe
    assert 'id="appLoadingBar"' in html
    # El overlay viejo fue eliminado
    assert 'appLoadingScreen' not in html, "Quedó el overlay app-loading-screen"
    assert 'appLoadingPercent' not in html, "Quedó el porcentaje"
    assert 'app-loading-ring' not in html, "Quedó el anillo"
    assert 'app-loading-screen' not in html, "Quedó la clase del overlay"
    assert 'app-loading-label' not in html, "Quedó el label Cargando…"


def test_base_inline_css_sin_overlay():
    css = _read('static/css/base_inline.css')
    assert '.app-loading-bar' in css, "Debe conservar la barra"
    assert 'app-loading-screen' not in css, "Quedó CSS del overlay"
    assert 'app-loading-ring' not in css, "Quedó CSS del anillo"
    assert 'app-loading-percent' not in css, "Quedó CSS del porcentaje"
    assert 'app-loading-label' not in css, "Quedó CSS del label"
    assert 'app-loading-shimmer' not in css, "Quedó el keyframe shimmer viejo"
```

- [ ] **Step 2: Correr el test para verificar que falla**

Run: `.venv311/bin/python -m pytest tests/test_loader_barra.py -q`
Expected: FAIL (ambos: `appLoadingScreen`/anillo aún presentes en base.html; overlay aún en base_inline.css).

- [ ] **Step 3: Commit del test**

```bash
git add tests/test_loader_barra.py
git commit -m "test(loader): regresión barra superior sin overlay (rojo)"
```

---

### Task 2: Reescribir el loader en `templates/base.html`

**Files:**
- Modify: `templates/base.html` (CSS crítico inline, markup, y scripts del loader)

Esta tarea tiene 4 ediciones. Hazlas todas y luego corre el test de Task 1.

- [ ] **Step 1: Reemplazar el CSS crítico inline del loader**

En el `<style>` del `<head>`, reemplazar EXACTAMENTE este bloque:

```css
      .app-loading-bar {
        position: fixed; top: 0; left: 0;
        width: 100%; height: 3px;
        background: linear-gradient(90deg, transparent 0%, #2563eb 30%, #6366f1 60%, transparent 100%);
        background-size: 220% 100%;
        animation: app-loading-shimmer 1.1s linear infinite;
        z-index: 9999;
        pointer-events: none;
        transition: opacity 220ms ease, transform 220ms ease;
      }
      .app-loading-bar.is-loaded { opacity: 0; transform: translateY(-3px); }
      @keyframes app-loading-shimmer {
        0%   { background-position: 200% 0; }
        100% { background-position: -200% 0; }
      }
      .app-loading-screen {
        position: fixed; inset: 0;
        z-index: 9998;
        display: flex; align-items: center; justify-content: center;
        background: rgba(244, 246, 250, 0.96);
        backdrop-filter: blur(6px); -webkit-backdrop-filter: blur(6px);
        transition: opacity 280ms ease;
      }
      .app-loading-screen.is-loaded { opacity: 0; pointer-events: none; }
      /* Snap-show during in-app navigation: instant opacity 1, no fade. */
      .app-loading-screen.is-navigating {
        opacity: 1 !important;
        pointer-events: auto !important;
        transition: none !important;
      }
      .app-loading-card { display: flex; flex-direction: column; align-items: center; gap: 16px; }
      .app-loading-ring { position: relative; width: 104px; height: 104px; }
      .app-loading-ring svg { width: 100%; height: 100%; transform: rotate(-90deg); }
      .app-loading-ring-track { fill: none; stroke: rgba(15, 23, 42, 0.10); stroke-width: 8; }
      .app-loading-ring-bar {
        fill: none; stroke: #2563eb; stroke-width: 8; stroke-linecap: round;
        stroke-dasharray: 263.89; stroke-dashoffset: 263.89;
        /* Animación conducida por JS para que el porcentaje y el
           relleno del círculo queden siempre sincronizados. */
      }
      .app-loading-screen.is-loaded .app-loading-ring-bar { stroke-dashoffset: 0; transition: stroke-dashoffset 220ms ease-out; }
      .app-loading-percent {
        position: absolute; inset: 0;
        display: flex; align-items: center; justify-content: center;
        font-size: 1.15rem; font-weight: 800; color: #0f172a;
        font-variant-numeric: tabular-nums; letter-spacing: -0.02em;
      }
      .app-loading-label {
        font-size: 0.85rem; font-weight: 700; color: #64748b;
        letter-spacing: 0.08em; text-transform: uppercase;
      }
      @media (prefers-reduced-motion: reduce) {
        .app-loading-bar { animation: none; background: #2563eb; }
        .app-loading-ring-bar { animation: none; stroke-dashoffset: 132; }
      }
```

con este bloque nuevo:

```css
      /* Barra de progreso superior (estilo NProgress). Sin overlay. El
         ancho lo conduce un script inline; se desvanece al completar. */
      .app-loading-bar {
        position: fixed; top: 0; left: 0;
        height: 3px; width: 0;
        background: #2563eb;
        box-shadow: 0 0 8px rgba(37, 99, 235, 0.7), 0 0 4px rgba(37, 99, 235, 0.5);
        z-index: 9999;
        pointer-events: none;
        opacity: 1;
        transition: width 200ms ease-out, opacity 300ms ease;
      }
      .app-loading-bar.is-loaded { opacity: 0; }
      @media (prefers-reduced-motion: reduce) {
        .app-loading-bar { transition: opacity 200ms ease; box-shadow: none; }
      }
```

- [ ] **Step 2: Reemplazar el markup del loader**

Reemplazar EXACTAMENTE este bloque (justo después de `<body ...>`):

```html
<div class="app-loading-bar" id="appLoadingBar" aria-hidden="true"></div>
<div class="app-loading-screen" id="appLoadingScreen" role="status" aria-live="polite" aria-label="Cargando">
  <div class="app-loading-card">
    <div class="app-loading-ring">
      <svg viewBox="0 0 100 100" aria-hidden="true">
        <circle cx="50" cy="50" r="42" class="app-loading-ring-track"></circle>
        <!-- stroke-dasharray + stroke-dashoffset como atributos SVG (no
             solo CSS) para que el estado inicial vacío se respete antes
             de que cualquier CSS externa cargue. Evita el flash de
             "círculo lleno" en mobile. -->
        <circle cx="50" cy="50" r="42" class="app-loading-ring-bar"
                stroke-dasharray="263.89" stroke-dashoffset="263.89"></circle>
      </svg>
      <div class="app-loading-percent" id="appLoadingPercent">0%</div>
    </div>
    <div class="app-loading-label">Cargando…</div>
  </div>
</div>
```

con esto (solo la barra):

```html
<div class="app-loading-bar" id="appLoadingBar" role="status" aria-label="Cargando" aria-hidden="true"></div>
```

- [ ] **Step 3: Reemplazar el script de disparo por el controlador consolidado**

Reemplazar EXACTAMENTE el `<script>` que empieza con el comentario `/* Mostrar el overlay AL INSTANTE...` y contiene `function showNavOverlay()` (incluye los listeners de `click` y `submit` en fase de captura, y termina en `})();` seguido de `</script>`). Es decir, desde:

```html
<script>
  /* Mostrar el overlay AL INSTANTE cuando el usuario toca un link de
```

hasta el `</script>` que cierra ese bloque (el que está justo antes de `<script src="{{ url_for('static', filename='js/theme-toggle.js') }}"></script>`).

Reemplazarlo COMPLETO por:

```html
<script>
  /* Barra de progreso de navegación (estilo NProgress). Inline para pintar
     en el primer frame. Sin overlay a pantalla completa.
     - Arranca al cargar la página y "gotea" hasta ~90%.
     - Al estar el DOM listo, salta a 100% y se desvanece.
     - Se re-muestra al hacer clic en enlaces internos / enviar forms. */
  (function () {
    var bar = document.getElementById('appLoadingBar');
    if (!bar) return;

    var progress = 0;
    var trickleTimer = null;
    var done = false;

    function render() { bar.style.width = (progress * 100).toFixed(1) + '%'; }
    function set(p) {
      progress = Math.max(progress, Math.min(p, 0.994));
      bar.classList.remove('is-loaded');
      render();
    }
    function trickle() {
      var remaining = 0.9 - progress;
      if (remaining > 0) set(progress + remaining * 0.12);
      trickleTimer = setTimeout(trickle, 350);
    }
    function start() {
      if (done) return;
      if (trickleTimer) return;
      if (progress === 0) set(0.3);
      trickle();
    }
    function finish() {
      if (trickleTimer) { clearTimeout(trickleTimer); trickleTimer = null; }
      done = true;
      progress = 1;
      render();
      setTimeout(function () { bar.classList.add('is-loaded'); }, 120);
    }

    // 1) Arrancar para la carga de ESTA página.
    start();

    // 2) Completar cuando el DOM esté listo (+1 frame).
    function finishWhenReady() {
      requestAnimationFrame(function () { setTimeout(finish, 40); });
    }
    if (document.readyState === 'loading') {
      document.addEventListener('DOMContentLoaded', finishWhenReady);
    } else {
      finishWhenReady();
    }
    window.addEventListener('load', finish);  // fallback
    setTimeout(finish, 10000);                 // safety

    // 3) bfcache (back/forward): la página vuelve ya cargada → ocultar ya.
    window.addEventListener('pageshow', function (e) { if (e.persisted) finish(); });

    // 4) Re-mostrar al navegar a otra página (antes de descargar la actual).
    function isHtmxControlled(el) {
      while (el && el !== document) {
        if (el.attributes) {
          for (var i = 0; i < el.attributes.length; i++) {
            var name = el.attributes[i].name;
            if (name.indexOf('hx-') === 0 || name.indexOf('data-hx-') === 0) return true;
          }
        }
        el = el.parentNode;
      }
      return false;
    }
    function restartForNav() {
      done = false;
      progress = 0;
      start();
      setTimeout(finish, 10000); // safety si la navegación se cancela
    }
    document.addEventListener('click', function (e) {
      var link = e.target.closest('a[href]');
      if (!link) return;
      if (link.target === '_blank') return;
      if (link.hasAttribute('download')) return;
      if (e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
      var href = link.getAttribute('href');
      if (!href) return;
      if (href.charAt(0) === '#') return;
      if (href.indexOf('javascript:') === 0) return;
      if (href.indexOf('mailto:') === 0 || href.indexOf('tel:') === 0) return;
      if (link.origin && link.origin !== location.origin) return;
      if (link.href === location.href) return;
      if (isHtmxControlled(link)) return;
      restartForNav();
    }, true);
    document.addEventListener('submit', function (e) {
      var form = e.target;
      if (!form || form.tagName !== 'FORM') return;
      if (form.target === '_blank') return;
      if (isHtmxControlled(form)) return;
      restartForNav();
    }, true);
  })();
</script>
```

- [ ] **Step 4: Eliminar el script viejo de porcentaje/anillo**

Más abajo en `base.html` hay OTRO `<script>` grande que contiene varias IIFE. Una de ellas maneja el overlay viejo: empieza con un comentario que menciona `stroke-dashoffset` / Safari y abre con `(function () {` declarando `var screen = document.getElementById('appLoadingScreen');`, define `EMPTY`, `tick`, `finish`, y termina con un `})();` (justo después del listener `pageshow` que hace `screen.classList.add('is-loaded')`).

ELIMINAR ÚNICAMENTE esa IIFE — desde su comentario inicial hasta su `})();` inclusive — dejando intacto TODO lo demás del mismo `<script>` (el código de tabbar haptics `touchstart/touchend/touchcancel`, el `flashStack`, los `console.log` y el `window.addEventListener('load', ...)` del tiempo de carga). El bloque a borrar es el que referencia `appLoadingScreen`, `appLoadingPercent` y `.app-loading-ring-bar`.

Verificar tras borrar: `grep -c "appLoadingScreen" templates/base.html` debe devolver `0`.

- [ ] **Step 5: Correr el test de Task 1 (la parte de base.html)**

Run: `.venv311/bin/python -m pytest tests/test_loader_barra.py::test_base_html_usa_barra_sin_overlay -q`
Expected: PASS.

- [ ] **Step 6: Smoke + commit**

Run: `.venv311/bin/python -m pytest tests/test_reskin_smoke.py -q`
Expected: PASS (las páginas renderizan sin error).

```bash
git add templates/base.html
git commit -m "feat(loader): barra de progreso superior en reemplazo del overlay con %"
```

---

### Task 3: Limpiar `static/css/base_inline.css`

**Files:**
- Modify: `static/css/base_inline.css` (bloque del loader, ~líneas 71-184)

- [ ] **Step 1: Reemplazar el bloque CSS del loader**

Reemplazar EXACTAMENTE desde el comentario `/* Top loading bar shown while the page is fetching/parsing. ... */` y todas las reglas siguientes (`.app-loading-bar`, `@keyframes app-loading-shimmer`, su `@media`, `.app-loading-screen`, `.app-loading-card`, `.app-loading-ring`, `.app-loading-ring svg`, `.app-loading-ring-track`, `.app-loading-ring-bar`, `.app-loading-screen.is-loaded .app-loading-ring-bar`, `.app-loading-percent`, `.app-loading-label`, y el `@media (prefers-reduced-motion: reduce) { .app-loading-ring-bar { ... } }`) — todo el rango que va desde ese comentario hasta la línea `}` que cierra `@media (prefers-reduced-motion: reduce) { .app-loading-ring-bar { stroke-dashoffset: 132; } }` — por:

```css
    /* Barra de carga superior (estilo NProgress). El ancho lo conduce un
       script inline en base.html; se desvanece al completar. Sin overlay. */
    .app-loading-bar {
        position: fixed;
        top: 0; left: 0;
        height: 3px;
        width: 0;
        background: #2563eb;
        box-shadow: 0 0 8px rgba(37, 99, 235, 0.7), 0 0 4px rgba(37, 99, 235, 0.5);
        z-index: 9999;
        pointer-events: none;
        opacity: 1;
        transition: width 200ms ease-out, opacity 300ms ease;
    }
    .app-loading-bar.is-loaded {
        opacity: 0;
    }
    @media (prefers-reduced-motion: reduce) {
        .app-loading-bar { transition: opacity 200ms ease; box-shadow: none; }
    }
```

NO tocar las reglas que vienen después (`.app-topbar` con safe-area, etc.).

- [ ] **Step 2: Correr el test de Task 1 (parte base_inline.css) + completo**

Run: `.venv311/bin/python -m pytest tests/test_loader_barra.py -q`
Expected: PASS (las 2 funciones).

- [ ] **Step 3: Commit**

```bash
git add static/css/base_inline.css
git commit -m "style(loader): limpiar CSS del overlay viejo en base_inline.css"
```

---

### Task 4: Verificación final

**Files:** ninguno (verificación)

- [ ] **Step 1: Suite completa**

Run: `.venv311/bin/python -m pytest tests/ -q`
Expected: los 2 tests nuevos pasan; el conteo de fallas pre-existentes (22, no relacionadas: dashboard_kpis, etiquetas, consolidar_flujo, una de facturacion) NO aumenta. `passed` sube en 2 respecto al baseline previo.

- [ ] **Step 2: Verificación visual (manual, si hay app/preview)**

Navegar entre páginas y confirmar: aparece una barra azul delgada arriba que avanza y desaparece al cargar; NO hay overlay a pantalla completa ni anillo ni porcentaje; al usar back/forward no parpadea; en formularios (submit) también aparece. Si `prefers-reduced-motion` está activo, la barra no "gotea" de forma molesta.

---

## Self-Review

**Spec coverage:**
- Barra superior 3px azul con glow → Task 2 Step 1 + Task 3 Step 1 (CSS).
- Markup solo barra, sin overlay → Task 2 Step 2.
- Disparo en captura con exclusiones (htmx/_blank/download/modificadores/externos/anchor) → Task 2 Step 3 (listeners click/submit).
- Trickle a ~30%→90%, finish a 100% + fade, mostrar inmediato → Task 2 Step 3 (start/trickle/finish).
- Fallbacks: window.load, safety 10s, bfcache pageshow → Task 2 Step 3.
- prefers-reduced-motion → Task 2 Step 1 + Task 3 Step 1 (media query).
- Eliminar overlay/anillo/percent/label en AMBOS archivos → Task 2 (base.html) + Task 3 (base_inline.css), verificado por Task 1.
- Sin tests rotos (ninguno referenciaba el loader) → Task 4.

**Placeholder scan:** Sin TBD/TODO; todo el código (CSS, markup, JS, tests) está completo y literal.

**Type/identifier consistency:** El id `appLoadingBar` se usa en el markup (Task 2 Step 2), el CSS `.app-loading-bar` (Task 2 Step 1 + Task 3) y el script (`getElementById('appLoadingBar')`, Task 2 Step 3). La clase `is-loaded` se aplica en JS y está definida en ambos CSS. El test (Task 1) verifica exactamente esos identificadores y la ausencia de `appLoadingScreen`/`appLoadingPercent`/`app-loading-ring`/`app-loading-label`/`app-loading-shimmer`.
