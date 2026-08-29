---
target: listado de pedidos (4ª pasada)
total_score: 26
max_score: 40
na_heuristics: 
p0_count: 0
p1_count: 3
timestamp: 2026-08-29T08-32-48Z
slug: templates-pedidos-html
---
`Method: dual-agent (A: revisión de diseño · B: detector + evidencia de navegador)`

Cuarta pasada, con consigna distinta: se le dio a la evaluación A la lista de lo ya arreglado en las tres rondas anteriores y se la mandó a terreno nuevo (recorrido completo, densidad por pixel, voz de los textos, escala a 3.000).

## Design Health Score — 26/40

Tendencia: 16 → 20 → 28 → 23 → 26. Detector CLI limpio (exit 0). 0 errores de consola, 0 requests fallidos.

| # | Heurística | Score |
|---|---|---|
| 1 Visibilidad | 3 | 2 Mundo real | 3 | 3 Control y libertad | 2 | 4 Consistencia | 2 | 5 Prevención de errores | **4** |
| 6 Reconocer > recordar | 2 | 7 Flexibilidad | 2 | 8 Minimalismo | 2 | 9 Recuperación | 3 | 10 Ayuda | 3 |

Carga cognitiva: 3 fallos de 8 (moderada).

## P1 — Todo `position: sticky` de esta pantalla es decorativo (regresión propia)

Verificado por el controlador: `.tablero-titulo` declara `position:sticky; top:0` pero con `scrollY=900` su `getBoundingClientRect().top` es **−656px**. El scrollport es `main.app-content` (`overflow-y:auto`) que NO scrollea (scrollHeight 2593 == clientHeight 2593); quien scrollea es el documento. Lo mismo con el `<thead>` de la tabla, cuyo ancestro `.tabla-pedidos-scroll` tampoco scrollea.

Se agregó en la ronda anterior y se «verificó» comprobando que la regla estaba en el CSS servido, NO midiendo el render. Tercera vez en este expediente que se cae en esa trampa.

Consecuencia: ~1.800px de recorrido sin rótulo de grupo en móvil; en escritorio se pierden los encabezados Y los botones de ordenar a partir de la fila 8 de 20.

Arreglo: el sticky solo revive si el ancestro con overflow deja de serlo (`.app-content { overflow: visible }` acotado a esta pantalla). Para la tabla, sacar el scroll horizontal del ancestro del thead. **Si no se arregla, borrar las dos declaraciones**: hoy prometen algo que no hacen y la próxima crítica las va a leer como resueltas.

## P1 — El recorrido se rompe al entrar al pedido
`fecha_entrega` NO aparece en ninguna parte de `detalles_pedido.html` (grep: 0). El eje sobre el que la pantalla anterior agrupa, ordena y colorea desaparece al abrir el pedido. Y no hay vuelta: la única salida es la pestaña «Pedidos», que se renderiza `active` mientras estás en el detalle, y siempre va a `/pedidos` pelado (pierde la búsqueda). Es el MISMO error ya arreglado para tablero↔lista: se arregló una pata y quedó la otra. El patrón del `next` ya existe en el repo.

## P1 — Un breakpoint por encima de todos los iPhone
`.pc-foot` pasa a `flex-direction: row` recién en `min-width: 480px`; los iPhone van de 390 a 440. El comentario del código afirma «dos filas por tarjeta en vez de cuatro»: cierto en escritorio, falso en el aparato primario. Cuesta ~40px por tarjeta: 196 → ~156px, tablero 2704 → ~2300px, 3 tarjetas sobre el pliegue en vez de 2.

## P2 — En «Atrasados» se borra el estado real
Un vencido `pendiente` y uno `preparado` se ven idénticos: misma barra rosa, misma píldora VENCIDO. Lo único que los distingue es la etiqueta del botón. Mientras tanto el atraso se afirma tres veces (encabezado, barra, píldora, más «· N d tarde»). Arreglo: conservar la píldora de estado real y dejar que el atraso lo digan la barra y el «· N d tarde». Cuesta cero píxeles.

## P2 — El vacío afirma algo que no puede saber
«El día está cerrado» a las 7 de la mañana, cuando lo que pasa es que todavía no se cargó nada. Y el reparto está invertido: la acción con más peso visual duplica el «+ Nuevo» del hero, mientras la única puerta a los 960 pedidos es un enlace de texto de 14,4px.

## Otros
- Un concepto, tres nombres: Atrasados / Vencidos / VENCIDO. Una acción, tres: Nuevo / Cargar un pedido / Crear primer pedido. Un identificador, tres: PED-958 / #958 / Pedido #958 (los `aria-label` usan el que no se ve).
- Las 5 píldoras son mutuamente excluyentes pero se exponen como 5 `aria-pressed` independientes: debería ser `radiogroup` o `tablist`.
- En oscuro el `caret-color` del buscador es blanco sobre blanco: `-webkit-text-fill-color` rescata el texto pero no el cursor. Se arregla con `caret-color`.
- El tab activo de la tabbar mide ~2,3:1 en oscuro; el «P» del logo, 2,8:1 en el extremo cian de su degradado.
- A 1440px las capturas en claro y oscuro son BYTE-IDÉNTICAS: en escritorio el tema no cambia absolutamente nada.
- Un Vendedor sin clientes asignados recibe «No hay pedidos cargados / Crear primer pedido»: la app le afirma que el negocio no tiene pedidos.
- Escritorio: `.pedidos-tablero` clavado en 1100px sin `margin-inline:auto` → 330px muertos a 1440, 820px a 1920. Y la tabla usa 1372px: pasar de tablero a lista ensancha 272px de golpe.
- Peso: tablero 69KB/497 nodos, lista 136KB/1097, vacío 45KB/253. Load 162/408/291ms.

## La escala: qué se rompe primero a 3.000
NO es el rendimiento. Es que **el tablero solo se vacía facturando**: `entregado` no se alcanza desde ninguna pantalla y borrar no deja rastro. Con 2% de pedidos abandonados sobre 3.000, el tope de la pantalla pasa a ser la basura más vieja del negocio, ordenada de más vieja a menos, empujando el trabajo de hoy abajo. Es un agujero de producto, no de diseño.

## ¿Ya está suficientemente bien?
Respuesta de la evaluación A, textual: «Sí, casi. Y lo digo con todas las letras: el próximo esfuerzo rinde más en otro lado.»

Quedan 4 cosas baratas que sí valen esta pantalla (sticky, breakpoint 480, estado en Atrasados, texto del vacío) — una tarde. Después es rendimiento decreciente.

Dónde rinde más, en orden:
1. **La pantalla de detalle del pedido**: destino de cada toque desde acá, cero rondas de crítica, sin vuelta, sin fecha de entrega, tercer estilo de botón primario. Es donde el recorrido termina, o sea lo que el usuario recuerda.
2. **Cómo se cierra un pedido que no se va a facturar**: el agujero que degrada el tablero con el tiempo.
3. **La navegabilidad del archivo**: filtro por fecha y por cliente. Hoy duele poco; en dos años es la queja principal.
