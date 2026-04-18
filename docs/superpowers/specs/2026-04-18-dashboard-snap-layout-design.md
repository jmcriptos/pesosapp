# Dashboard Snap Layout — Design Spec

**Date:** 2026-04-18
**Status:** Approved, ready for implementation plan

## Problem

Dashboard se usa principalmente en móvil. Hoy las pestañas Ventas y Servicio muestran KPIs en grids 2×2 (Ventas) y 2×3 (Servicio) con tipografía pequeña, y un chart de tendencia muy bajo (~140px). El usuario reporta que la legibilidad es pobre — quiere ver una tarjeta a la vez, grande, y un chart de tendencia mucho más prominente. Además, el fondo dark con gradientes radiales indigo/violet baja el contraste.

## Goals

- En móvil/tablet, Ventas y Servicio muestran **una tarjeta a la vez** ocupando ~85vh, con scroll-snap vertical nativo.
- El chart de tendencia (12 meses, Ventas) ocupa ~90vh como su propia tarjeta-snap, con canvas a ~70vh.
- Mejorar el contraste del dashboard: fondo sólido oscuro, glass más opaca, texto más blanco.
- Cero cambios al carrusel horizontal de tabs ni a Chart.js. Solo un `IntersectionObserver` corto (~15 LOC) para el indicador de puntitos.

## Non-goals

- Top y Actividad **no** cambian (son listas, ya funcionan a tamaño legible).
- No tocar el JS del carrusel horizontal entre tabs (`dash-tabs`, `dash-track`). Sí se añade un `IntersectionObserver` corto y aislado solo para el indicador de puntitos del snap.
- No cambiar tokens globales (`tokens.css`) — overrides scoped a `body[data-dashboard-screen]`.
- No tocar consultas del backend ni la lógica de KPIs.
- No reescribir Chart.js ni cambiar las series. Solo crece de tamaño.

## Decisions log

| Decision | Value | Rationale |
|---|---|---|
| Patrón de navegación | Scroll-snap vertical nativo (`scroll-snap-type: y mandatory`) | El gesto "scroll" ya es conocido y no compite con el swipe horizontal de tabs |
| Alcance | Ventas + Servicio | Top/Actividad son listas; no ganan con tarjetas grandes |
| Card size | `min-height: 85vh` por tarjeta-snap | Deja un asomo del siguiente para invitar al scroll |
| Chart size | Tarjeta `min-height: 90vh`; canvas `height: 70vh` | El chart es la métrica más vista; pasa a protagonista |
| Fondo | Sólido `#0a0e1f` (sin gradientes) | Más contraste con tarjetas glass |
| Glass opacity | `--glass-bg-strong: rgba(15,23,42,0.72)` (vs ~0.55 actual en dark) | Tarjetas más definidas sobre el fondo oscuro |
| Tipografía | Valor KPI `--color-text` puro (`#f8fafc`); subs `#cbd5e1` | Mayor legibilidad sin tocar tokens globales |
| Indicador de progreso | Puntitos verticales (4 para Ventas, 6 para Servicio) en el costado derecho | Orientación rápida sin ocupar espacio del KPI |
| Desktop | Snap desactivado en `≥1024px` — vuelve al grid actual | Scroll-snap con mouse es awkward; en desktop hay espacio para la grid |
| JS | Solo un `IntersectionObserver` corto para los puntitos | El resto es CSS puro sobre el HTML existente |

## Architecture

### Modified files

| Path | Cambio |
|---|---|
| `static/css/dashboard_light.css` | Añadir sección "Snap layout" scoped a `body[data-dashboard-screen]` con: contenedores snap, tarjetas snap, escalado tipográfico, fondo sólido, glass opaca, indicador de puntitos. Toda dentro de `@media (max-width: 1023px)`. |
| `templates/dashboard.html` | Cambios mínimos al markup: añadir `data-snap-card="1"` a cada `.kpi`, `.chart-card` y `.week-mini-grid` dentro de los paneles de Ventas y Servicio para tener un selector limpio. Añadir `<div class="snap-dots">` por panel (4 dots Ventas, 6 dots Servicio). Sin cambios a la estructura ni al contenido de los KPIs. |
| `static/js/dashboard-snap-dots.js` (nuevo, ~15 LOC) | `IntersectionObserver` que marca el dot activo según qué `.kpi[data-snap-card]` está más visible en cada panel snap. |

### Untouched

- `static/js/dashboard-tabs.js` y todo el JS del carrusel horizontal de tabs.
- Chart.js, sus series y su configuración (solo crece el contenedor).
- Tokens globales (`tokens.css`).
- Todos los demás templates y CSS.

## Visual structure

### Mobile (`<1024px`)

```
┌─────────────────────┐  ← topbar (dark glass)
│ ⚙ Pesos · Hoy 18:53 │
├─────────────────────┤
│ [Ventas][Servicio]… │  ← segmented tabs (sin cambios)
├─────────────────────┤
│                     │
│  ┌───────────────┐  │
│  │   VENTAS      │  │
│  │   DEL MES     │  │  ← KPI Card 1 (snap, 85vh)
│  │   ◯ 67%       │  │     · Indicador de puntitos a la derecha
│  │   42,500 XCG  │  │     · Valor a 64px (vs 24px actual)
│  │   Meta 63K    │  │
│  └───────────────┘  │
│                     │
├─────────────────────┤  ← snap divider (invisible)
│  ┌───────────────┐  │
│  │   PROYECCIÓN  │  │  ← KPI Card 2 (snap)
│  │   ◯ 81%       │  │
│  │   51,200 XCG  │  │
│  └───────────────┘  │
│                     │
│  …                  │
│                     │
│  ┌───────────────┐  │
│  │ TENDENCIA     │  │
│  │ 12 MESES      │  │  ← Chart Card (snap, 90vh)
│  │ ┌──────────┐  │  │     · Canvas 70vh
│  │ │ /\  /\   │  │  │     · Header con valor "esta semana"
│  │ │/  \/  \  │  │  │
│  │ └──────────┘  │  │
│  └───────────────┘  │
│                     │
├─────────────────────┤
│ 🏠 📋 ➕ 👥 ⋯       │  ← tabbar (dark glass)
└─────────────────────┘
```

Servicio sigue el mismo patrón pero con 6 KPI cards (OTD, OFR, POR, CE, LT, PED).

### Desktop (`≥1024px`)

Sin cambios — vuelve al grid 2×2 (Ventas) / 2×3 (Servicio) actual. Snap desactivado.

## Behavior

- **Scroll natural:** dedo arriba/abajo. Cada KPI engancha al centro del viewport (`scroll-snap-align: center; scroll-snap-stop: always`).
- **Cambio de tab horizontal:** sin cambios. El swipe horizontal entre Ventas/Servicio/Top/Actividad sigue funcionando vía el JS existente del carrusel.
- **Indicador de puntitos:** posición fija en el lateral derecho del panel snap. Un `IntersectionObserver` de ~15 LOC marca el dot del KPI más visible. Funciona en todo iOS Safari moderno y es trivial de mantener — más predecible que `:has()` con un selector frágil.
- **Tabs Top y Actividad:** layout actual sin cambios. No son contenedores snap.

## Contraste y fondo

Overrides CSS aplicados solo dentro de `body[data-dashboard-screen]` para no afectar otras pantallas:

```css
body[data-dashboard-screen] .app-shell,
body[data-dashboard-screen] .app-content {
  background: #0a0e1f !important;
  background-image: none !important;
}
body[data-dashboard-screen] .gcard {
  --glass-bg-strong: rgba(15, 23, 42, 0.72);
  border-color: rgba(255, 255, 255, 0.08);
  box-shadow: 0 12px 32px -8px rgba(0, 0, 0, 0.5);
}
body[data-dashboard-screen] .kpi-value { color: #f8fafc; }
body[data-dashboard-screen] .kpi-sub   { color: #cbd5e1; }
```

## Tradeoffs aceptados

- **Más scroll para ver todo:** ver los 4 KPIs de Ventas requiere ~3 scrolls. Aceptado a cambio de tarjetas grandes y legibles a un brazo de distancia.
- **Cambio visual fuerte en dark:** el fondo sólido es marcadamente diferente del actual gradiente. Aceptado por el contraste.

## Riesgos

- **Conflicto con scroll de página:** si el snap container no tiene altura fija bien calculada (`calc(100vh - topbar - tabs - tabbar - safe-area)`), el scroll engancha mal. Mitigación: definir variables CSS para `--topbar-h`, `--tabs-h`, `--tabbar-h` y validar en iPhone real.
- **Chart muy alto en landscape:** 70vh de canvas en landscape se ve plano. Mitigación: limitar `max-height: 480px` para el canvas.
- **Carrusel de tabs y snap interactúan:** el JS de tabs modifica `transform` del track. Verificar que los containers snap no rompen el `transform` del padre. Si lo hacen, encerrar el snap en un wrapper.

## Plan de validación

1. Implementar en una rama feature, probar en iPhone real.
2. Validar que cada KPI card engancha (no se queda a medias).
3. Validar que el swipe horizontal entre tabs sigue funcionando.
4. Validar que Top y Actividad NO snappean.
5. Validar contraste visual en dark mode con luz ambiente típica de bodega.
