---
target: listado de pedidos
total_score: 20
max_score: 40
na_heuristics: 
p0_count: 1
p1_count: 4
timestamp: 2026-08-28T21-35-30Z
slug: templates-pedidos-html
---
`Method: dual-agent (A: revisión de diseño · B: detector + evidencia de navegador)`

## Design Health Score

| # | Heurística | Score | Hallazgo clave |
|---|---|---|---|
| 1 | Visibilidad del estado del sistema | 2 | `Facturar` dispara un webhook síncrono a QuickBooks sin spinner, sin estado deshabilitado y sin candado anti-doble-tap. Contadores de píldoras calculados antes de la búsqueda (`app.py:5901-5920`). |
| 2 | Correspondencia con el mundo real | 3 | Verbos correctos. Pero «Todos» no es todos: `app.py:5844` filtra `estado != 'entregado'`. «Contexto» es palabra de sistema. |
| 3 | Control y libertad del usuario | 1 | La única acción irreversible no confirma (P0). Todos los redirects vuelven a `/pedidos` pelado. La tarjeta es `div role="link"`: sin Cmd+click. |
| 4 | Consistencia y estándares | 2 | Dos widgets para una variable. Tres formatos de fecha. La nota es texto en escritorio e icono mudo en móvil. Toggle de tema inerte. |
| 5 | Prevención de errores | 1 | Eliminar confirma y escala el mensaje si está preparado; facturar no confirma. Las protecciones están en la acción equivocada. |
| 6 | Reconocer antes que recordar | 2 | 2 de 5 píldoras fuera de pantalla a 390px (`scrollWidth 665`/`clientWidth 358`). Nombres de cliente truncados. Nota tras icono mudo. |
| 7 | Flexibilidad y eficiencia | 2 | Búsqueda en vivo excelente. Sin facturación por lote; orden de columna sobre 20 de 910; paginación móvil solo prev/next sobre 46 páginas. |
| 8 | Diseño estético y minimalista | 2 | 417 de 774 px útiles móviles (54%) son cromo. Escritorio: fila 1 en y=531, 5 de 20 filas visibles. `1 / 1` con una sola página. «+ Nuevo» duplicado. |
| 9 | Recuperación de errores | 3 | Estado vacío excelente. Lo socava el `form.submit()` silencioso ante fallo de red (`pedidos.html:161`). |
| 10 | Ayuda y documentación | 2 | Un buen hint en la búsqueda. Nada explica «Por preparar» = Pendientes+Preparados ni que «Todos» no es todos. `title=` en producto táctil. |
| **Total** | | **20/40** | **Aceptable** |

Run anterior: 16/40 (2026-08-28T08-22-35Z). +4 tras 7 commits.

## Veredicto de especificidad

Ingeniería específica del dominio vestida con un diseño genérico. La lógica es inconfundiblemente de este negocio (`tiene_pesables` → Pesar/Preparar, `· 3 d tarde`, `fecha_entrega` sobre `fecha_pedido`, XCG/USD nativos, «Vencidos» rojo solo si hay). La composición y el lenguaje visual son SaaS admin de stock: renombrando strings se envía a una startup de facturación B2B sin tocar un pixel. La señal: el estado del pedido (lo que decide la acción) va a 11,2px con 2,11:1; el monto (que nadie usa para decidir acá) a 20px/800 con 17,85:1.

**Detector CLI:** `[]`, exit 0 (limpio; validado contra archivo de control que sí dio 4 hallazgos). Todo lo real aparece renderizado.
**Overlay inyectado:** `[impeccable] 40 anti-patrones` / 47 hallazgos — 19 `undersized-ui-text` (10,6px XCG/USD; 10,88px badges; 10px tabs), 3 `low-contrast` (3,9:1 `#e11d48`/`#ffe4e6`), 5 `bounce-easing`, 3 `ai-color-palette`, 3 `dark-glow`, 2 `gpt-thin-border-wide-shadow`.
**Falsos positivos descartados:** `nested-cards` sobre `table.tabla-pedidos`, `overused-font` (stack de sistema), `dark-glow`/`layout-transition` en `body` (duplicados de `#appLoadingBar` por herencia), `bounce-easing` (decisión deliberada del tabbar).

## Lo que funciona

1. **Estado vacío** (`_pedidos_resultados.html:184-209`): distingue «tu búsqueda no encontró nada» de «no tenés pedidos», cita la consulta, dice qué campos se buscan, y ofrece «Ver todos» en vez de «Crear primero».
2. **Búsqueda en vivo** (`pedidos.html:98-171`): consulta al servidor no al DOM, debounce 350ms, guarda contra respuestas fuera de orden, atenúa sin blanquear, `replaceState`, fallback a submit real. Existe porque un submit cierra el teclado de iOS.
3. **Nunca ofrece una acción que el backend va a rechazar**: `tiene_pesables` y `tiene_factura` condicionan los botones.

## Problemas prioritarios

### [P0] `Facturar` dispara sin confirmar — el guard está cableado al elemento equivocado
`_pedidos_resultados.html:132` y `:365` ponen `data-confirm` sobre el `<button>`; `base.js:314` escucha `e.target.closest('form[data-confirm]')` y en un `submit` `e.target` ES el form, así que nunca lo ve. El form de eliminar sí lo lleva en el `<form>` (`:149`) y por eso sí confirma. Verificado en vivo: `confirmCalled: false, submitFired: true`. Crea una factura real en QuickBooks, a 8px del tacho, sin estado pendiente ni candado de doble envío (encima de la carrera de DocNumber ya asumida). El comentario en `:128-130` afirma lo contrario de lo que se envía.
**Fix:** mover `data-confirm` al `<form class="pc-action-form">` de `:125` y `:362`; extender `base.js:313-322` para deshabilitar el submitter y poner «Facturando…»; regenerar `base.min.js`. → `/impeccable harden`

### [P1] El estado del pedido es lo menos legible de la tarjeta
`.status-pill.preparado` 2,11:1 (`pedidos_list.css:648-651`), `.pendiente` 2,95:1 (`:643-646`), `.vencido` 3,91:1 (`:506-509`), todas a 11,2px. Causa: `color-mix(in srgb, <hue> 18%, transparent)` sobre blanco. El detector lo confirmó independientemente en la variante escritorio (`.estado-badge.estado-vencido` 3,9:1 a 10,88px). El monto en la misma tarjeta: 20px/800 a 17,85:1. Jerarquía invertida.
**Fix:** tinte a 28-32% + tinta un paso más oscura (`#78350f`, `#312e81`, `#9f1239`); `.status-pill` de 11,2 a 12,5px (`:629`); bajar `.pc-amt` de `1.25rem/800` a `1rem/700`. → `/impeccable typeset`

### [P1] Opaca para teclado y lector de pantalla
- `#pedidos-search` con `outline: none` (`pedidos_list.css:151`) y sin `:focus-within` de reemplazo. Confirmado sobre 90 pulsaciones de Tab: el control más usado no muestra foco.
- `.pedido-card` es `div role="link" aria-label="Ver detalles del pedido PED-1"` (`:9-15`): cliente, monto, estado y «5 d tarde» nunca se anuncian. 20 ítems idénticos en la lista de enlaces. Además anida `<button>`/`<a>` dentro de rol `link` (inválido).
- Sin `aria-live`: la búsqueda reemplaza `innerHTML` en silencio.
- 13 paradas de foco invisibles: el drawer cerrado (`translateX(-280px)`) no es `inert`.
**Fix:** anillo `:focus-visible` en `.search-pill:focus-within`; contenido real en el `aria-label`; `aria-live="polite"` con `sr-only`; `inert` en el drawer. → `/impeccable audit`

### [P1] Toda acción irreversible expulsa del contexto
`facturar_pedido` y `eliminar_pedido` devuelven `redirect(url_for('lista_pedidos'))` sin argumentos en TODOS los caminos (`app.py:6854, 6861, 6880`, `7977`-`8106`). Con default `por_preparar`, quien estaba en «Preparados» p.3 buscando «Renaissance» cae en p.1 sin filtro ni búsqueda. Facturar es actividad por lote: cuatro facturas = reconstruir filtro y búsqueda cuatro veces. Destruye el cierre emocional.
**Fix:** `<input type="hidden" name="next" value="{{ request.full_path }}">` en ambos forms + redirect a `next` validado del mismo origen. Mejor: `facturar_pedido` acepta `X-Requested-With: fetch` y devuelve el parcial re-renderizado → la tarjeta pasa a `Facturado` en el lugar. → `/impeccable harden`

### [P1] Como cola de trabajo no escala a 910 pedidos, y el orden miente
1. 54% del viewport móvil es cromo (`firstCardTop=417` de 774): entran 1,8 tarjetas. Las 2 cifras y las 5 píldoras son el MISMO control (ambas escriben `#pedidos-estado`; «Por preparar» 11 = Pendientes 7 + Preparados 4). Una variable renderizada tres veces.
2. 2 de 5 píldoras fuera de pantalla sin degradado, flecha ni asomo.
3. Paginación móvil solo prev/next sobre 46 páginas (escritorio sí tiene primera/última).
4. Cada toque de página salta al tope (`pedidos.html:237`).
5. Orden de columna client-side sobre los 20 cargados, ordenando por clave XCG oculta mostrando moneda nativa. Salida literal: `…3146.08 XCG, 1939.07 USD, 2001.47 USD`.
**Fix:** un solo control segmentado (`Vencidos · Hoy · Por preparar · Facturados · Todos`), eliminar `.pedidos-cifras`; `mask-image` en `#pedidos-filtros`; «Cargar 20 más» conservando scroll; borrar el `window.scrollTo` de `:237`; orden server-side con `?orden=` y borrar `prepararTablaOrdenable`. → `/impeccable distill`

## Banderas rojas por persona

**Alex (experto impaciente):** Cmd+click sobre `.pedido-card` abre en la MISMA pestaña (`window.location.href` sobre `div[role=link]`, `pedidos.html:245`). `th[data-sort="total"]` ordena 20 de 910 por clave invisible. Sin selección múltiple: 4 preparados = 4 submits que reinician el filtro.

**Sam (lector de pantalla / teclado / zoom 200%):** buscador sin indicador de foco; la tarjeta anuncia solo «Ver detalles del pedido PED-1»; las tres píldoras de estado fallan contraste; **a 195px CSS (zoom 200% sobre iPhone de 390px) `scrollWidth 251 > clientWidth 189` y el CTA «+ Nuevo» requiere scroll horizontal** (a 390 y 320px no hay overflow: 384/384 y 1434/1434); sin `aria-live`.

**Casey (móvil, una mano):** «Preparados» y «Facturados» invisibles; `.pc-meta-nota` (`:81-86`) muestra la nota como icono de 13px cuyo `title` solo dice «Este pedido tiene una nota» — el contenido es inalcanzable en el dispositivo primario (en escritorio sí se ve, `:288`); paginar la lanza al tope de un documento de 1668px; el tacho de 48px a 8px de `Facturar`, que ya no pregunta; 1,8 tarjetas visibles.

## Observaciones menores

- **Sin modo oscuro.** `pedidos_list.css:6-12` fuerza `background: #f8fafc !important` en `html`, `body`, `.app-container`, `.app-content`, `.app-shell`. Alternar `body[data-theme]` da estilos de contenido byte-idénticos; solo cambia el tabbar. De noche: marco negro alrededor de una lista al 100% de luminancia. El toggle del topbar no hace nada acá.
- **366 `!important`** entre `pedidos_list.css` (234) y `pedidos_inline.css` (132) para una pantalla.
- `a.tab` a 10px con 2,19:1 en la pestaña activa (`#2563eb` sobre el `#3a3a3e` del `backdrop-filter`).
- CSS muerto: `.chips-row`, `.fchip`, `.estado-select` (`pedidos_list.css:154-200`).
- `1 / 1` de paginación con una sola página, junto a «1–11 de 11».
- Columna CONTEXTO de escritorio: valor dominante es el literal «Sin notas» a 2,47:1; con nota, duplicada (bajo el cliente y como chip).
- `pedidos.html:161` hace `form.submit()` ante error de fetch sin mensaje.
- Rendimiento sano: CLS 0, FCP/LCP 172ms, 0 errores de consola, 0 requests fallidos, 856 nodos. Pero tarjetas móviles y filas de escritorio están ambas siempre en el DOM (11+11); 10 archivos CSS separados + 158KB `fa-solid-900.woff2`.

## Preguntas

1. Si el default es «Por preparar», ¿por qué la plata es el elemento más grande de cada tarjeta?
2. Tres widgets para una variable: ¿qué se pierde si queda un solo control segmentado?
3. ¿Esta pantalla es una cola o un archivo? ¿Y si la lista fuera estrictamente la cola (~30 filas, sin paginación) y las 910 vivieran detrás del buscador?
4. ¿Y si `Facturar` no necesitara confirm, sino que la tarjeta pasara a `Facturado` en el lugar con «Deshacer» por 5 segundos?
5. Si le sacás los strings en español, ¿alguien adivinaría de qué negocio es?
