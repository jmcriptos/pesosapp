# Estandarizar UI de Registros al estilo Detalle de Pedidos

**Fecha:** 2026-05-31
**Estado:** Aprobado — implementación directa (cambio acotado de CSS + swaps de botones)

## Objetivo

Unificar la apariencia de las pantallas de **Registros HACCP** (temperaturas,
limpieza, áreas, productos, cámaras, configuraciones, historiales y el hub) con
la de **Detalle de Pedidos**, que el usuario toma como referencia. Se conserva
la **barra de color de estado** a la izquierda de cada tarjeta (verde/ámbar/rojo)
porque comunica el estado de un vistazo (registrado hoy / falta / fuera de rango),
algo valioso en HACCP.

## Diagnóstico (de dónde diverge)

Ambas áreas comparten tokens y los campos de formulario (`.mobile-form-control`,
`.mobile-form-label`). Los formularios de "crear" de Registros ya usan
`.mobile-card` + `.mobile-btn` (idénticos a Pedidos). La divergencia visible está en:

1. **Tarjetas de lista `.reg-card` / filas `.reg-row`**: usan `var(--shadow-sm)`
   (plano) y radio 16px, mientras Pedidos usa una sombra elevada
   (`--shadow-card: 0 10px 32px -12px rgba(15,23,42,0.08)`) y radio mayor.
2. **Botones de acción inline** (Registrar lectura, Registrar limpieza, Marcar
   período como revisado): usan `.reg-btn-primary` **compacto**, mientras Pedidos
   y los formularios de "crear" usan `.mobile-btn-primary` **grande con gradiente**.
3. **Barra de navegación superior** (`.reg-toolbar` con `.reg-btn`): estilo propio,
   se armoniza con el look "secundario" de Pedidos.

## Cambios

### A. `static/css/registros.css`
- `.reg-card`, `.reg-row`: `box-shadow` → sombra elevada
  `0 10px 32px -12px rgba(15, 23, 42, 0.08)` (vía `var(--shadow-card, …)` con
  fallback literal, porque `--shadow-card` se define por página y no es global);
  `border-radius` → `var(--radius-xl, 20px)`. **Se mantiene** `.reg-card::before`
  (barra de estado) y su `overflow: hidden`.
- `.reg-btn` (navegación): restilar al look secundario de Pedidos — fondo elevado
  (`var(--color-bg-elevated)`), borde sutil (`var(--color-border)`), sombra suave;
  se mantiene compacto para la fila de navegación.
- `.reg-pill` y títulos `.reg-name`: ajustes finos de armonización (sin cambios
  estructurales).

### B. Plantillas — botones de acción principal a `mobile-btn` (reutilizar, una sola fuente)
Cambiar el botón primario compacto por el grande de Pedidos (misma clase global,
sin duplicar estilos):
- `templates/registros/temperaturas.html`: "Registrar lectura"
  `reg-btn reg-btn-primary` → `mobile-btn mobile-btn-primary`.
- `templates/registros/limpieza.html`: "Registrar limpieza" → idem.
- `templates/registros/temperaturas_historial.html`: "Marcar período como revisado"
  → `mobile-btn mobile-btn-primary`.
- `templates/registros/limpieza_historial.html`: idem.

Los formularios de crear/guardar (cámaras, áreas, productos, configs) y los botones
Filtrar/Exportar de los historiales **ya** usan `.mobile-btn*` → no se tocan.

## Alcance y no-alcance

- **Sí**: estética de tarjetas (elevación/radio), botones primarios prominentes,
  navegación armonizada, conservando la barra de estado. Aplica a las 10 pantallas
  vía CSS compartido.
- **No** (YAGNI): NO se copian elementos específicos de Pedidos que no aplican a
  Registros (hero, timeline, tabs segmentados, summary strip, action bar fija). NO
  se reestructura el HTML de las tarjetas ni se cambian los formularios de campos.

## Verificación

- Render local con login + capturas (playwright) de al menos: hub `/registros`,
  registro de temperaturas, registro de limpieza, e historial — comparando contra
  el look de un Detalle de Pedido. Confirmar en claro y oscuro si es viable.
- Sin cambios de backend; los tests existentes deben seguir verdes (las plantillas
  deben renderizar 200).

## Despliegue

`registros.css` se sirve directo (sin minificar) y las plantillas son server-side,
así que basta `git push` a main (auto-deploy Heroku). Recordar refrescar la PWA.
