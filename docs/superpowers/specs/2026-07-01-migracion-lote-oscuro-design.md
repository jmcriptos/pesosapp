# Migración del lote oscuro al design system claro

**Fecha:** 2026-07-01
**Estado:** Aprobado — en ejecución (Tanda 1 deployada 2026-07-02)
**Origen:** Revisión UI/UX 2026-07-01 (preview local + viewport móvil 375px)

**Corrección 2026-07-02:** Etiquetas (`templates/form_generar_etiquetas.html`)
**ya estaba migrada** antes de esta revisión (commits `8ec94000`/`6d329b60`,
`static/css/etiquetas_form.css` "desktop-first light redesign") — la
evaluación original confundió la topbar oscura global (compartida por todas
las pantallas, incluidas las ya claras) con la pantalla en sí. Se retira del
alcance de la Tanda 4; esa tanda queda disponible para consumir en una futura
pantalla si aparece, o se elimina del plan de tandas.

## Problema

La app tiene dos generaciones de UI conviviendo. Pedidos, Dashboard, Detalle,
Pesar, Registros HACCP y Etiquetas usan el design system claro (tokens +
primitives + `.mobile-*`, o su propio CSS scopeado tipo `etiquetas_form.css`);
Clientes y Productos (migrados, Tanda 1) también. Facturación, Recepciones,
Importación y Precios (hub + 5 subpantallas) siguen en el tema oscuro legacy
(`dark-theme.css` + ~520 líneas de `<style>` inline). Al navegar, la app salta
de claro a oscuro. Además:

- **Importación está rota**: `scripts.js` llama `agregarProducto()` (líneas
  ~587 y ~601) pero la función se perdió en la "limpieza masiva" (`4cb84336`);
  existía en el primer commit (`f56a63ca`, scripts.js:491). El botón "Agregar
  Producto" no hace nada y la excepción aborta el resto del init.
- `scripts.js` es compartido por 4 pantallas y lanza errores cruzados en
  consola (p. ej. `#form-crear-producto` null en Facturación, scripts.js:197).
- El toggle de tema del header no hace nada visible: las pantallas nuevas son
  light-only (hardcodeado en `*_light.css` / `pedidos_list.css`).
- `formulario_importacion.html` referencia `importaciones.css` e
  `importaciones.js` que no existen.

## Decisiones (respuestas del usuario)

| Decisión | Valor |
|---|---|
| Alcance | Todo el lote oscuro: las 5 pantallas core + Precios (hub y subpantallas). Etiquetas retirada 2026-07-02 (ya estaba migrada) |
| Nivel UX | Re-skin + mejoras estándar (lista-primero, búsqueda, sin columna ID, Tom Select) — misma funcionalidad de fondo |
| Tema oscuro | Quitar el toggle; la app queda light-only. Dark mode real = proyecto futuro aparte |
| Bugs scripts.js | Incluidos: restaurar `agregarProducto`, split por pantalla con guardas |
| Enfoque | C — capa compartida `gestion.css` + migración en 6 tandas deployables + retirada final del tema oscuro |

## No-alcance

- Cero cambios de backend: no se tocan rutas, modelos, queries ni migraciones.
- No se rediseñan flujos de fondo (los AJAX/endpoints actuales se conservan).
- No se implementa variante oscura de ninguna pantalla.
- No se migran Login ni Admin (Admin/Usuarios ya usa ops-*; Login es un caso
  aparte y queda como está).
- No se reescribe lógica jQuery a vanilla; jQuery se mantiene donde ya funciona.

## Arquitectura

### 1. CSS: un archivo compartido

**Nuevo:** `static/css/gestion.css` (servido directo, sin minificar, como
`registros.css`). Cada template migrado lo carga en su bloque `extra_css`.

Contenido:
- Wrapper `.gestion-wrap` que fija los tokens claros **scopeados al wrapper**
  (patrón `.reg-wrap`). Nunca al `body`: `getComputedStyle(document.body)`
  devuelve tokens oscuros (lección aprendida — ver memoria "operaciones CSS
  bleed").
- Neutralización del estilado global de `<form>` dentro del scope
  (`.gestion-wrap form { background: transparent !important; box-shadow: none;
  padding: 0; border: 0; }`), replicando lo que hizo Registros contra
  `dark-theme.css`/`forms.css`/`styles.min.css`.
- Solo componentes faltantes: fila de lista con badges (`.gestion-row`),
  header de página con búsqueda (`.gestion-header`, `.gestion-search`),
  sección colapsable de crear (`.gestion-create`), tabla→tarjetas responsive
  (`.gestion-table`).

**Se reutiliza, no se duplica:** `.mobile-card`, `.mobile-btn`,
`.mobile-btn-primary`, `.mobile-form-control`, `.mobile-form-label` (globales
vía `app-mobile.css`) + utilidades de `primitives.css` (`.chip-*`, `.field`,
`.stack-*`, `.label`).

**Se elimina:** los bloques `<style>` inline de los templates legacy
(clientes 166 líneas, facturacion 170, recepciones 138, productos 50) y el
Font Awesome 6.4.2 duplicado que carga `clientes.html` (el global es 6.7.2).

### 2. Dos patrones de pantalla

**Patrón GESTIÓN** — Clientes, Productos, Precios (listas/asignaciones):
- Header: título + botón `＋ Nuevo` (`.mobile-btn-primary`).
- Búsqueda client-side que filtra la lista (input tipo `pedidos`).
- Lista de tarjetas server-rendered: nombre prominente, badges
  (`.chip-*`: moneda, QBO vinculado, se-pesa), **sin columna ID**.
- Acciones editar/eliminar por fila; eliminar usa `data-confirm` (convención
  `base.js`) conservando el AJAX actual.
- Crear: el form actual queda colapsado en `.gestion-create`; `＋ Nuevo` lo
  expande y enfoca el primer campo. Mismo POST/AJAX de hoy.
- Editar: sigue siendo página aparte (`cliente_form.html`,
  `editar_producto.html`, `lista_form.html`) restilada con los mismos
  componentes de form.

**Patrón CAPTURA** — Facturación, Recepciones, Importación, Etiquetas:
- El formulario es la tarea primaria: queda arriba, restilado
  (`.mobile-card` + `.field`/`.mobile-form-*`).
- Selects de cliente/producto → **Tom Select**: basta agregar la clase
  `ts-select` (+ `data-ts-placeholder="Buscar…"`) — `base.html` ya trae un
  auto-init para `select.ts-select` con dropdown montado en `<body>` y fix
  de fondo para iOS.
- Registros del día / tablas AJAX debajo del form, restiladas.
- Facturación: los forms secundarios (Reporte de pesos, Generar etiquetas)
  pasan a secciones colapsables debajo de la tabla.
- Importación: la tabla de cálculo se conserva como tabla con scroll
  horizontal dentro de una tarjeta (UX de hoja de cálculo; no se fuerza a
  tarjetas).

### 3. JavaScript

`static/scripts.js` se parte en un archivo por pantalla:

| Nuevo archivo | Origen (scripts.js) | Template |
|---|---|---|
| `static/js/productos.js` | líneas ~194–264 + `agregarProductoATabla` (~490) | productos.html |
| `static/js/recepciones.js` | líneas ~59–192 | recepciones.html |
| `static/js/facturacion.js` | líneas ~342–478 | facturacion.html |
| `static/js/importaciones.js` | líneas ~487–609 + `agregarProducto()` restaurada de `f56a63ca:static/scripts.js` (línea 491) | formulario_importacion.html |

- Cada archivo abre con guarda: `if (!document.getElementById('<root>')) return;`
- Cada template carga **solo** su archivo. `scripts.js` se borra al final
  (tanda 6) cuando ningún template lo referencie.
- Helpers compartidos: `escapeHtml` ya vive en `base.js`; `mostrarMensaje`
  se mueve a `base.js` como helper global (una sola fuente) y se regenera
  `base.min.js`.
- Clientes conserva su `<script>` inline (ya está aislado); solo se ajustan
  selectores si cambia el markup.
- Al editar `base.js`, regenerar `base.min.js` (`cp static/js/base.js
  static/js/base.min.js`).

### 4. Tandas (cada una deployable e independiente)

| Tanda | Pantallas | Contenido clave |
|---|---|---|
| 1 | ✅ Clientes + Productos | Deployada 2026-07-02. Valida patrón GESTIÓN; crea `gestion.css`; split `productos.js`; quita FA 6.4.2 duplicado |
| 2 | Recepciones + Facturación | Patrón CAPTURA; Tom Select; tablas AJAX restiladas; split `recepciones.js`/`facturacion.js`; colapsables de reportes |
| 3 | Importación | Restaurar `agregarProducto`; crear `importaciones.js` real; corregir refs muertas a `importaciones.css`/`js`; tabla scroll-h |
| ~~4~~ | ~~Etiquetas~~ | **Retirada del alcance 2026-07-02** — ya estaba migrada (ver corrección arriba). Renumeración: la limpieza final pasa a llamarse Tanda 5 |
| 5 (antes 5) | Precios | `precios/index.html` (hub → tarjetas claras), `listas.html`, `lista_form.html`, `lista_productos.html`, `clientes.html`, `cliente_producto.html`, `carga_masiva.html`. Patrón GESTIÓN. La tanda grande (~3,300 líneas de template con estilos y scripts inline propios) |
| 6 | Limpieza final | Ver siguiente sección. Precondición: Tandas 2, 3 y 5 completas (Etiquetas ya no bloquea) |

### 5. Limpieza final (tanda 6)

Precondición: ninguna página renderiza oscuro.

1. Quitar `<link dark-theme.css>` de `base.html` (línea ~73) y borrar
   `static/css/dark-theme.css`.
2. Quitar el botón de tema del header, borrar `static/js/theme-toggle.js` y
   su `<script>` en `base.html`; fijar `data-theme="light"` en `body_attrs`.
3. `styles.css`: cerrar el `:root` sin cerrar (bug conocido: 245 reglas
   anidadas) y eliminar el bloque `@media (prefers-color-scheme: dark)` que
   pinta botones azules; regenerar `styles.min.css`.
4. Borrar template muerto `templates/precios/pedido_form.html` (ninguna ruta
   lo renderiza).
5. Borrar `static/scripts.js` (ya sin referencias).
6. Smoke visual de TODAS las pantallas (nuevas y migradas) tras retirar la
   cascada oscura — es el paso con mayor radio de impacto del proyecto.

### 6. Verificación (por tanda) y despliegue

- Suite completa: `.venv/bin/python -m pytest tests/ -q` (venv, sin forzar
  `DATABASE_URL`). Tests acoplados a markup (`test_etiquetas`, y verificar
  `test_dashboard_kpis`/`test_consolidar_flujo` en tanda 6) se ajustan cuando
  el markup cambie de verdad, no se borran.
- Visual: preview local (launch.json puerto 5002, `admin`/`Preview123!` en
  `local.db`), viewport 375px, captura por pantalla migrada; consola sin
  errores (criterio: cero `jQuery.Deferred exception`).
- Interacción mínima por pantalla: crear + eliminar (con confirm) + búsqueda
  en GESTIÓN; submit + carga de tabla AJAX en CAPTURA; en Importación,
  "Agregar Producto" agrega fila y `calcularTotales` recalcula.
- Deploy por tanda: `git push` a main (auto-deploy Heroku) **con OK del
  usuario por tanda**. Verificar contra `app.jomarfoods.com` en navegador de
  escritorio (Cloudflare cachea estáticos; el origen Heroku no reproduce
  problemas de CDN) y refrescar la PWA en iPhone.

## Riesgos

- **Tanda 6 (retirar dark-theme.css)** es el cambio de mayor alcance: páginas
  no contempladas (login, admin, errores) podrían depender de esa cascada.
  Mitigación: smoke de todas las rutas del drawer antes del push.
- Tests acoplados a markup exacto ("test rot") — presupuestar ajuste de
  selectores en tandas 4 y 6.
- PWA cachea estáticos: tras cada deploy, refrescar y validar en el iPhone
  real.
- `gestion.css` compite con la cascada oscura mientras existan tandas
  pendientes: todos los overrides van scopeados a `.gestion-wrap` con
  especificidad suficiente (patrón probado por `registros_light.css`).
