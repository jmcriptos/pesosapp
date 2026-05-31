# Diseño: Barra de carga superior (reemplazo del overlay con porcentaje)

**Fecha:** 2026-05-30
**Estado:** Aprobado (pendiente revisión final del usuario)

## Problema

El indicador de carga actual es un overlay a pantalla completa con un anillo SVG
y un porcentaje que sube de 0%→90% en 8 segundos mediante una animación RAF
independiente de la carga real. En páginas rápidas el número va "atrasado" y la
navegación se siente lenta y artificial ("fake").

## Objetivo

Reemplazar el overlay + porcentaje por una **barra de progreso superior delgada**
(estilo NProgress / YouTube / GitHub), sin número y sin bloquear la pantalla, que
se sienta rápida y honesta.

## Decisiones tomadas
- **Eliminar por completo** el overlay a pantalla completa (anillo, porcentaje,
  tarjeta, label "Cargando…").
- **Mostrar la barra de inmediato** al navegar (sin delay).
- Sin número de porcentaje visible.

## Comportamiento

### Disparo (se conserva la lógica actual)
Listener en **fase de captura** sobre:
- Clics en `<a href>` internos — con las mismas exclusiones actuales: `target="_blank"`,
  atributo `download`, teclas modificadoras (Cmd/Ctrl/Shift/Alt), anchors (`#…`),
  `javascript:`/`mailto:`/`tel:`, orígenes externos, mismo `href` que la URL actual,
  y elementos controlados por **htmx** (cualquier ancestro con atributo `hx-*`/`data-hx-*`).
- Envíos de `<form>` (mismas exclusiones de `_blank` y htmx).

### Animación (trickle, sin porcentaje)
1. Al dispararse: la barra aparece y avanza rápido hasta ~30%.
2. Luego "gotea": incrementos pequeños decrecientes hacia un **tope de ~90%**
   (nunca llega sola a 100%).
3. La página nueva renderiza con la barra ya en progreso (CSS + markup crítico
   inline en cada página) y reanuda el trickle desde ~30% → sin parpadeo ni reset visible.
4. Al estar lista (`DOMContentLoaded` + 1 frame con `requestAnimationFrame`):
   salta a **100%** y se desvanece rápido (~200ms). Sin "beat" largo.

### Fallbacks (se conservan)
- **Safety timer:** si la navegación nunca completa, forzar el cierre (fade) a los ~10s.
- **bfcache:** en `pageshow` con `event.persisted === true`, ocultar la barra de
  inmediato (la página vuelve ya cargada; no animar).

## Estética
- Barra `position: fixed; top: 0; left: 0;` ancho 100%, alto **3px**, color de marca
  `#2563eb`, con un leve glow/sombra en el extremo derecho (el "peg" de NProgress).
- `z-index` alto (por encima de topbar/drawer/modales).
- Progreso vía `transform: scaleX(...)` con `transform-origin: left` (animación
  compuesta, sin layout thrash) y `transition` suave.

## Accesibilidad
- `prefers-reduced-motion: reduce`: sin trickle continuo; la barra aparece, al
  terminar se llena y desaparece con transición mínima (o sin animación).
- Contenedor con `role="status"` y `aria-label="Cargando"`; sin texto visible.
  La barra en sí es `aria-hidden="true"`.

## Componentes / archivos
| Componente | Archivo | Cambio |
|-----------|---------|--------|
| CSS crítico inline | `templates/base.html` (~líneas 35-92) | Reemplazar las reglas del overlay/anillo/percent por las de la barra trickle |
| Markup | `templates/base.html` (~líneas 143-160) | Quitar `app-loading-screen` (anillo, percent, card, label); dejar solo `app-loading-bar` como barra de progreso |
| Script de disparo | `templates/base.html` (~líneas 161-241) | Mantener la detección de navegación; `showNavOverlay()` → arranca la barra/trickle |
| Script de avance/cierre | `templates/base.html` (~líneas 583-660) | Reemplazar la lógica RAF de porcentaje del anillo por el trickle de la barra y el `finish()` (100% + fade) |

Todo el cambio queda contenido en `templates/base.html`. No se tocan `base.js`
ni archivos minificados (el loader vive inline en `base.html`).

## Casos borde
- Navegación cancelada / red caída → safety timer cierra la barra (~10s).
- Back/forward (bfcache) → sin barra.
- htmx / `_blank` / descargas / externos → no se dispara la barra.
- `prefers-reduced-motion` → animación mínima.

## Pruebas
- **Regresión a nivel de fuente** (`tests/test_loader_barra.py`): `templates/base.html`
  contiene el elemento de barra (`id="appLoadingBar"`) y **ya NO** contiene el markup
  del overlay viejo (`appLoadingScreen`, `appLoadingPercent`, `app-loading-ring`).
- **Humo:** `tests/test_reskin_smoke.py` sigue verde (las páginas renderizan).
- **Verificación visual** al implementar: navegar en el navegador y observar la barra
  (aparece, gotea, completa y desaparece; no hay overlay; no hay parpadeo en back/forward).

Nota: ningún test existente referencia el markup del loader (verificado), así que su
eliminación no rompe la suite.

## Fuera de alcance (YAGNI)
- Progreso "real" vía fetch/SPA.
- Delay anti-parpadeo (se decidió mostrar inmediato).
- Cambios al tema/colores fuera del azul de marca ya usado.
