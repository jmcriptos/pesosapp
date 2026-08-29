---
target: listado de pedidos (tablero, 3ª pasada)
total_score: 23
max_score: 40
na_heuristics: 
p0_count: 3
p1_count: 2
timestamp: 2026-08-29T07-15-17Z
slug: templates-pedidos-html
---
`Method: dual-agent (A: revisión de diseño · B: detector + evidencia de navegador)`

Tercera crítica. Primera ronda que audita modo oscuro del sistema de forma sistemática, y ahí abajo había una capa entera sin revisar.

## Design Health Score — 23/40 (Aceptable)

Bajó desde 28 y NO por regresión: la puntuación anterior era optimista porque nadie había mirado en oscuro.

| # | Heurística | Score | Hallazgo |
|---|---|---|---|
| 1 | Visibilidad del estado | 2 | Carga = opacity 0.918 durante 0,12s (nada). La caja de error queda DEBAJO de 20 tarjetas. |
| 2 | Correspondencia mundo real | 3 | Vocabulario de reparto real. El confirm de borrar dice «#960», la pantalla dice «PED-960». |
| 3 | Control y libertad | 3 | «Volver al tablero» funciona; Atrás vuelve en un paso; `next` conserva filtro y página. Borrar sin deshacer. |
| 4 | Consistencia | 2 | Tarjeta compartida = logro. En oscuro píldoras y encabezados se pintan de CTA azul. |
| 5 | Prevención de errores | 2 | Facturar confirma con cliente y monto, pero acepta «0.00 XCG (0 líneas)». |
| 6 | Reconocer > recordar | 2 | El encabezado de grupo NO es sticky y el tablero mide 2585px. |
| 7 | Flexibilidad | 2 | 48 páginas sin salto a una página concreta. |
| 8 | Estético y minimalista | 2 | 46% del teléfono es cromo antes de la 1ª tarjeta; 806px muertos a 1920. |
| 9 | Recuperación de errores | 3 | El vacío de búsqueda sigue excelente; el error queda fuera de pantalla. |
| 10 | Ayuda | 2 | La única ayuda aparece cuando ya fallaste. |

Tendencia: 16 → 20 → 28 → 23.

## Tres P0, mismo origen, verificados por el controlador en el navegador

| Hallazgo (modo oscuro del sistema) | Medición | Ratio |
|---|---|---|
| El buscador escribe blanco sobre blanco | rgb(248,249,250) sobre rgb(255,255,255) | **1,05:1** |
| 4 de las 5 píldoras de filtro, invisibles | blanco sobre blanco | **1,00:1** |
| Los 4 encabezados ordenables como CTA azul | blanco sobre #1877ff | 4,10:1 |

El buscador ES la puerta del archivo según el spec: en oscuro, la única vía a 950 pedidos facturados no muestra lo que se teclea. Las píldoras son la única respuesta a «¿qué estoy viendo?» en 960 registros.

NO son regresiones de este trabajo: verificado con `git show 637cca22` que el buscador ya usaba el token antes. Las dos críticas anteriores no los vieron porque ninguna emuló modo oscuro.

## La causa raíz, medida

`:root {` abre en styles.css:2 y NO CIERRA NUNCA. Por anidamiento CSS quedan **342 bloques** adentro, todos con especificidad prestada. Ya se agregó guarda de especificidad dos veces y las dos veces la lista quedó corta.

Cerrar la llave NO es un cambio de un carácter: cambia la cascada de 342 reglas en toda la app. Merece spec y verificación propios.

## Otros hallazgos

- **`.pedidos-empty i` es descendiente sin acotar** y alcanza al `<i class="fa fa-plus">` DENTRO del CTA: el «+» de «Cargar un pedido» se dibuja a 35px, display:block, oscuro sobre verde = **1,65:1** y desalineado. Es el botón del estado por defecto de producción.
- **A 200% de texto la tarjeta se choca consigo misma**: la píldora VENCIDO se superpone con el importe. WCAG 1.4.4.
- **Con búsqueda activa la pantalla se contradice**: «Todos 960» + «Ningún pedido coincide» + «Sin pedidos», las tres a la vez. `status_counts` se calcula antes de aplicar `q`.
- **Facturar y borrar comparten el mismo confirm() del sistema**: en PWA de iOS el botón que factura dice «OK», idéntico al que borra. El borrado cascadea `pedido_evento` y tiene 4 palabras de aviso contra 30 de facturar.
- El encabezado de la tabla declara `position:sticky` pero su contenedor no scrollea: medido tras scrollTo(0,800), `top = -337` (fuera de pantalla).
- Se pierde el foco en cada swap: tras paginar y tras ordenar, `activeElement` es BODY.
- El nombre del cliente se corta a 19 caracteres en el teléfono y el `title` no existe en táctil.
- La fila de filtros esconde el 49% de sus opciones (scrollWidth 698 / clientWidth 358).

## Lo que sigue bien
`_agrupar_tablero` es la mejor pieza del expediente. La tarjeta compartida eliminó la divergencia entre vistas (verificado: `.pc-action-main` idéntico como `<a>` y como `<button>`). El contraste en modo CLARO es sólido: 10 elementos entre 4,76 y 17,9.

## Preguntas
1. Si el 99% de los días el tablero está vacío, ¿por qué el vacío sigue siendo lo menos diseñado? El vacío no es un caso borde: ES la pantalla.
2. La barrita lateral codifica el estado, que ya está en la píldora y en el botón; el grupo no se codifica en ningún lado salvo un título que se va con el scroll. ¿Por qué el dato redundante tiene tres portadores y el único, medio?
3. ¿Cuántas rondas más antes de que salga más barato cerrar la llave de styles.css que seguir listando selectores?
4. El spec afirma que la cola «entra entera en una pantalla». Con 10 pedidos mide 2585px. ¿A qué número deja de ser cierto?
