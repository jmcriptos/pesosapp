---
target: listado de pedidos
total_score: 16
max_score: 40
na_heuristics: 
p0_count: 2
p1_count: 2
timestamp: 2026-08-28T08-22-35Z
slug: templates-pedidos-html
---
# Critique — Listado de pedidos

Método: dual-agent (A: revisión de diseño · B: detector + evidencia de navegador), aislados.

## Design Health Score — 16/40 (necesita trabajo)

| # | Heurística | Score | Hallazgo clave |
|---|---|---|---|
| 1 | Visibilidad del estado | 2 | Filtrar por Vencidos/Por preparar no resalta ninguna pill |
| 2 | Correspondencia mundo real | 2 | «Por preparar (16)» incluye los 5 con badge PREPARADO (app.py:5790) |
| 3 | Control y libertad | 2 | Eliminar confirma; Facturar (QuickBooks real) no |
| 4 | Consistencia | 1 | Móvil/escritorio difieren en moneda, atraso y orden de acciones |
| 5 | Prevención de errores | 1 | Un toque a 8px del tacho emite factura irreversible |
| 6 | Reconocer > recordar | 2 | 321/685px de filtros ocultos; 2 pills fuera de pantalla sin señal |
| 7 | Flexibilidad | 2 | Búsqueda sin producto ni monto; sin orden por urgencia |
| 8 | Estética/minimalismo | 2 | «Sin notas» x15; pill de estado repetida en lista ya filtrada |
| 9 | Recuperación de errores | 1 | Estado vacío afirma 0 pedidos habiendo 26; salida a 1.62:1 |
| 10 | Ayuda | 1 | Vocabulario sin explicar; ayuda en title=, inexistente al tacto |

Las 10 aplican (modo Operate). Tres deducciones son de consecuencia, no de gusto.

## Especificidad
Intercambiable de categoría. Idea propia: el ancla temporal es la fecha de ENTREGA.
Todo lo demás es Tailwind por defecto. Detector sobre el template crudo = falso
negativo (exit 0) porque no resuelve url_for de Jinja; sobre la página renderizada:
ai-color-palette (índigo real), side-tab (falso positivo de ubicación; la franja real
es .pedido-card::before), dark-glow (débil). Sin overlays inyectados.

Tema: body declara dark, pedidos_list.css lo revierte a claro con !important.
Computado: texto rgb(241,245,249) sobre rgb(248,250,252) = 1.06:1. Sobrevive solo
porque cada elemento redeclara color. 445 !important aplican a esta página.

## Funciona
1. Búsqueda server-side con contador monotónico anti-carrera y fallback; no cierra el teclado iOS.
2. fecha_entrega con degradación honesta (cambia ícono y rótulo cuando cae a fecha de pedido).
3. Totales en mono + tabular-nums + peso 800.

## Prioridades
- [P0] Moneda contradictoria: móvil «450.00 USD», escritorio «450.00» bajo header fijo
  «Total (XCG)» (_pedidos_resultados.html:36-39 vs :229). Ordena por número crudo.
  VERIFICADO. Fix: moneda por fila en ambos anchos, ordenar por total*tipo_cambio,
  subir el código de moneda (hoy 2.56:1 / 10.56px).
- [P0] Facturar sin confirmación: form submit pelado (:107-113 móvil, :319-325 escritorio)
  hacia facturar_pedido -> N8N -> QuickBooks. Eliminar SÍ tiene data-confirm (:129, :329).
  VERIFICADO. Fix: confirmación con cliente/total+moneda/líneas/impuesto/entrega; separar
  del tacho >=24px.
- [P1] Estado vacío miente: con 26 pedidos dice «no hay», CTA dominante «Crear primer
  pedido», salida «Limpiar filtros» a 1.62:1. Fix: ramificar el botón, no solo el texto.
- [P1] Orden por id DESC: los vencidos quedan desparramados; el móvil nunca dice cuántos
  días de atraso. Fix: ordenar por urgencia dentro de cada grupo.
- [P2] Móvil y escritorio divergen; las acciones derivan 100px entre filas adyacentes;
  3 familias tipográficas por tarjeta (--font-sans nunca aplicado al body);
  Font Awesome cargado dos veces (6.7.2 + 6.4.2).

## Personas
- Vendedor al sol: moneda 2.56:1/10.56px y VENCIDO 3.91:1/11.2px son los tokens más
  débiles y los que más importan; ~1.8 tarjetas por pantalla (49% chrome).
- Empleado nuevo: «Por preparar» muestra tarjetas PREPARADO; «Hoy» incluye facturados.
- Baja visión: 8 estilos fallan AA en móvil, incluido el CTA «+ Nuevo» a 2.54:1;
  sin aria-live; 5 div role="link" envolviendo <a>/<button>.

## Menores
«1 líneas» sin pluralizar; 4 formatos de fecha en una columna; estado 'entregado' oculto
de un filtro llamado «Todos»; carga = opacity .5 sin spinner; 6 controles para 1 parámetro;
«+ Nuevo» 95x42 y paginación 42x42 bajo el piso de 44px; 0 errores de consola.
