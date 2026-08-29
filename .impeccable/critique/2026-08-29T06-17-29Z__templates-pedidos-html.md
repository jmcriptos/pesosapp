---
target: listado de pedidos (tablero)
total_score: 28
max_score: 40
na_heuristics: 
p0_count: 1
p1_count: 3
timestamp: 2026-08-29T06-17-29Z
slug: templates-pedidos-html
---
`Method: dual-agent (A: revisión de diseño · B: detector + evidencia de navegador)`

Segunda crítica tras el rediseño: /pedidos pasó de lista paginada de 942 a tablero de entregas (4 grupos por fecha_entrega) con la lista plana bajo parámetros de URL.

## Design Health Score — 28/40 (Bueno)

| # | Heurística | Score | Hallazgo |
|---|---|---|---|
| 1 | Visibilidad del estado | 3 | Grupos con cuenta, «3 d tarde», aria-live, error con reintento. Pero «Todos 960» convive con «1–20 de 129». |
| 2 | Correspondencia mundo real | 4 | Lo mejor: los 4 grupos son las preguntas de un repartidor, no estados de tabla. |
| 3 | Control y libertad | 2 | Del archivo no hay vuelta al tablero salvo una pestaña que ya se ve activa. |
| 4 | Consistencia | 2 | 8 tamaños de fuente, varios a <1px de distancia. En oscuro `<button>` y `<a>` de la misma clase se pintan distinto. |
| 5 | Prevención de errores | 3 | Confirm de Facturar excelente; lo contradice que en oscuro sea el botón más gritón. |
| 6 | Reconocer > recordar | 3 | El nombre de cliente se trunca SIN title (verificado). |
| 7 | Flexibilidad | 3 | Orden y paginación en servidor, URLs compartibles. Sin atajos; archivo a 2410px de scroll. |
| 8 | Estética y minimalismo | 2 | Escritorio: 1340px de vacío entre cliente e importe de la MISMA tarjeta. |
| 9 | Recuperación de errores | 4 | El vacío de búsqueda sigue siendo lo mejor del código base. |
| 10 | Ayuda | 2 | Nada explica los grupos ni por qué un pedido cae en «Sin fecha». |

Tendencia: 16 → 20 → 28.

## Veredicto de especificidad
Específico de este producto, con una recaída. Los 4 grupos son preguntas de reparto; «Sin fecha» existe solo para que un pedido no sea trabajo invisible. La recaída: la tarjeta sigue siendo fila de CRUD y el importe es el dato de mayor peso visual, que es lo menos accionable para quien carga una camioneta.

**Detector CLI:** `[]`, exit 0. **Overlay:** 33 hallazgos.
**Falsos positivos descartados:** `side-tab` sobre `.pedido-card::before` (riel de estado deliberado), `overused-font arial` (stack de sistema), un `low-contrast #141820/#0ea5e9` inatribuible, y —verificado por el controlador— «el buscador no muestra foco»: el agente midió `outline-style` en el `<input>` pero el anillo vive en `.search-pill:focus-within` (box-shadow 3px + borde, confirmado al enfocar).

## Problemas prioritarios

### [P0] En oscuro, «Facturar» es el botón más gritón de la pantalla
`button.pc-action-main` pasa de #4338ca/#e0e7ff (6,41:1) a blanco/#1877ff (**4,10:1 — FALLA AA**, umbral 4,5 para 13px). «Preparar» no cambia porque es `<a>`. Regla ganadora: `:root button:not(.btn-chip)` con !important dentro del `:root` sin cerrar de styles.css (confirmado: 371 llaves abiertas vs 370 cerradas).
Lo grave es la jerarquía de seguridad invertida: la única acción irreversible se vuelve el CTA más brillante y la segura queda suave.
Fix: specificity guard en pedidos_list.css, patrón de las pantallas .ops-*.

### [P1] La atenuación de «hecho» rompe AA — regresión introducida en la Tarea 3
Verificado componiendo la opacidad heredada: `.pc-id` 3,00:1, `.pc-meta span` 3,00:1, `.status-pill` 3,15:1. El arreglo de T3 corrigió el subárbol (los botones ya no se atenúan) pero nadie midió el contraste resultante: 0.62 sobre gris medio hunde bajo AA.
Fix: color explícito (#64748b = 5,0:1) en vez de opacity; píldora a opacidad plena.

### [P1] El tablero no tiene diseño de escritorio
Medido a 1440: tarjeta de 1406px, cliente en x=47, importe en x=1387. `.pedidos-tablero` no está en ninguna de las dos reglas de `@media (min-width:900px)` de pedidos_list.css, así que hereda la tarjeta móvil a sangre completa. 3 tarjetas visibles en 900px. El supervisor trabaja en escritorio.

### [P1] Del archivo no hay puerta de vuelta al tablero
Los únicos enlaces a `/pedidos` sin parámetros son los de navegación rotulados «Pedidos», que ya se ven activos. Borrar la búsqueda vuelve, pero solo si llegaste buscando.

### [P2] El estado vacío del lunes no está resuelto
Borde punteado = vocabulario de «acá falta algo», lo contrario del «día bien cerrado» del spec. No ofrece la acción que describe (el hint dice «cuando cargues un pedido» sin dar el botón, y el patrón ya existe en el vacío de búsqueda). Con `grupos` vacío el estado real es más fuerte que la frase.

## Banderas rojas
**Sam:** `aria-sort` está en el `<button>` y no en el `<th>` — se ignora, no se anuncia la columna ordenada (bug introducido en T2). Más los 3 fallos AA de «hecho». Todo lo que vive en `title` es inalcanzable en táctil.
**Alex:** la tarjeta del tablero no es focuseable, así que el handler de Enter/Espacio es código muerto. Archivo a 2410px o 450ms de debounce + recarga.
**Casey:** el tablero mide 2558px con 10 pedidos — la premisa del spec («entra entera en una pantalla») ya no se cumple. En iOS un `.focus()` sin gesto no reabre el teclado: la restauración de foco probablemente no funcione en el aparato real (razonado, no observado).

## Observaciones menores
- 8 tamaños de fuente, varios a <1px: deriva, no escala.
- Lozenge «Sin pedidos» en el vacío de búsqueda: se lee como afirmación global y parece tocable.
- Cuentas de píldoras globales, no filtradas: «Todos 960» junto a «1–20 de 129».
- La tarjeta del grupo «Sin fecha de entrega» MUESTRA una fecha (cae a fecha_pedido): el grupo dice una cosa y la tarjeta otra.
- Debounce asimétrico: 450ms tablero vs 350ms lista.
- Comentario obsoleto en pedidos_list.css:1284 respecto de la regla que documenta.

## Preguntas
1. Si el estado normal es el tablero vacío, ¿por qué el 95% del esfuerzo fue al 5% del tiempo?
2. ¿El importe merece ser lo más pesado de una tarjeta de entrega? ¿Y si fuera la cantidad de cajas o la ventana horaria?
3. ¿Hace falta una tarjeta de 138px por cada facturado de hoy, o alcanza una línea de cierre («3 entregadas hoy · ƒ12.400»)?
4. El archivo son 952 tarjetas sin ninguna acción en 48 páginas. ¿El enlace del pie no debería llevar a un selector de cliente?
5. El tablero renunció a filtros porque la cola es diminuta. Con 10 pedidos mide 2558px. ¿A partir de cuántos esa decisión se vuelve falsa?
