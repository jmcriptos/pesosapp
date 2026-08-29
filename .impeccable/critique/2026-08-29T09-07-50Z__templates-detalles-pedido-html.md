---
target: detalle del pedido
total_score: 12
max_score: 40
na_heuristics: 
p0_count: 1
p1_count: 3
timestamp: 2026-08-29T09-07-50Z
slug: templates-detalles-pedido-html
---
`Method: dual-agent (A: revisión de diseño · B: detector + evidencia de navegador)`

Primera crítica de la pantalla de **detalle de pedido**. Nunca había sido mirada. Contexto: el listado del que se llega pasó por cuatro rondas y hoy está en 26/40.

## Design Health Score — 12/40 (Crítico)

| # | Heurística | Score |
|---|---|---|
| 1 Visibilidad | 1 | 2 Mundo real | 2 | 3 Control y libertad | 1 | 4 Consistencia | 1 | 5 Prevención de errores | **0** |
| 6 Reconocer > recordar | 2 | 7 Flexibilidad | 1 | 8 Minimalismo | 1 | 9 Recuperación | 1 | 10 Ayuda | 2 |

Carga cognitiva: **7 fallos de 8** (crítica). Detector CLI: `[]`, exit 0.

## P0 — Facturar no pregunta nada (verificado por el controlador)

`templates/partials/_detail_action_bar.html:33-39`: el `<form>` de `facturar_pedido` lleva el token CSRF y NADA más. Verificado en el HTML servido de PED-4 y PED-12: los únicos `data-confirm` de la página son los cinco de «¿Eliminar X del pedido?» y el de «¿Marcar este pedido como preparado?».

O sea: la acción REVERSIBLE confirma y la IRREVERSIBLE no. Es exactamente la misma inversión de la jerarquía de seguridad que se arregló en el listado el 2026-08-28, en otro archivo que nadie abrió. Y en el listado —un toque atrás— Facturar confirma con cliente, importe, líneas y «No se puede deshacer», así que el usuario ya aprendió que pregunta.

Botón de 290px de ancho, 56px de alto, a 19px del borde de la tabbar, bajo el pulgar.

Arreglo: copiar el `data-confirm` y el `data-submit-label` de `_pedido_card_cuerpo.html:147-151`.

## Correcciones al informe de los agentes

1. **«El hero dice Facturado en pedidos sin facturar» NO está pasando en producción.** La plantilla (`_detail_hero.html:33-35`) imprime `fecha_facturacion` sin condicionar por estado —guarda que falta, fragilidad real— pero el caso sucio lo generó la propia siembra de datos de la crítica. Verificado contra prod: 942 pedidos, 942 facturados, **0 casos con fecha_facturacion y estado != facturado**. Es latente, no activo.
2. **Los botones de producto NO están bloqueados por la barra fija.** El agente B reportó `hitPass:false`. Llevando cada botón a la vista con `scrollIntoView` y midiendo, **los 11 reciben su propio toque**. Midió en la posición de scroll en que estaban. Lo real de esa medición son los TAMAÑOS.

## Hallazgos reales

- **No existe `fecha_entrega` en ninguna de las 7 plantillas del detalle**, y la ruta no pasa `hoy_local` (`app.py:7206-7218`), así que «vencido» y «N d tarde» son imposibles de calcular. Toda la estructura del listado —que agrupa, ordena y colorea por ese campo— se evapora al entrar.
- **Cero vuelta al listado.** La pantalla más profunda no tiene salida; el listado, un nivel arriba, sí tiene «← Volver al tablero de hoy». La pestaña «Pedidos» de la tabbar se ve `active` mientras estás acá.
- **Datos pintados como texto deshabilitado**: `#94a3b8` sobre blanco = **2,56:1** en los kg, el precio/kg y las etiquetas CAJAS/PESO/TOTAL del hero. Y `.btn-secondary` (Factura PDF / Revisar precios) blanco sobre `#95a5a6` = **2,56:1**: las dos únicas acciones de un pedido facturado parecen apagadas.
- **Destinos de toque a la mitad**: «Editar» de línea 78×**27**, borrar **30×30**, a 8px uno de otro. En el listado esos mismos controles son cuadrados de 44px separados y de distinto color.
- **~295 líneas de JS muerto** (`detalles_pedido.html:320-614`) que controlan `#form-detalle`, `#producto_id`, `#peso`, `#lote` — ninguno existe en el DOM. Se envían en cada carga.
- **ARIA de pestañas roto a medias**: `role="tab"` y `aria-selected` sin `aria-controls`, sin `role="tabpanel"`, sin ids. Anuncia una pestaña que no controla nada.
- **El modal no atrapa el foco** (verificado por B: Tab escapa a la página de atrás), no tiene `role="dialog"` ni `aria-modal`. Escape sí cierra.
- **Sin `<h1>`**; el árbol arranca en h2. 17 iconos decorativos sin `aria-hidden`.
- **Cuatro estilos de botón primario** coexistiendo, tres de ellos apilados cuando se abre etiquetas.
- **Las píldoras de estado usan otra paleta que el listado**: «pendiente» es ámbar allá y ROJO acá. El usuario aprendió que rojo = atrasado.
- **El importe pierde los decimales** (`3,988` sin monospace) justo en la pantalla desde la que se factura: no se puede conciliar contra 3.988,47.
- El `<select>` FORMATO de etiquetas no lo lee ninguna ruta: elegir A4 y apretar «4x2 Térmica» genera 4x2.
- El estado `entregado` del stepper no se asigna nunca en toda la app: el 25% de la barra de progreso es inalcanzable.
- En escritorio: 1266px de blanco entre el nombre del producto y su cantidad, en la misma fila.
- 14 hojas de estilo por vista, 84KB de HTML para un pedido de 5 líneas.

## Fortalezas
1. **La tarjeta de producto** (`_detail_productos_card.html:24-86`): PESADO/POR PESAR/IMPORTADO, `cajas_pesadas/cajas_objetivo` como fracción, kg en columna aparte. Específica del negocio, se escanea en un segundo.
2. **El texto del reintento de facturación**: «Si la factura ya existe en QuickBooks, reenviarlo crea un DUPLICADO» nombra la consecuencia concreta. Es el mejor microcopy de la pantalla.
3. **El bloque de notas**: la nota de reparto se lee entera sin tocar nada. Continúa bien la decisión tomada en el listado.

## La pregunta de fondo
Si el listado ya da cliente, estado, líneas, importe, entrega y atraso, y ofrece Pesar/Preparar/Facturar/Editar/Eliminar/PDF/Revisar precios, **¿qué viene a hacer el usuario acá?** Hoy la respuesta honesta es: ver las líneas y generar etiquetas. Todo lo demás es repetición con otra tipografía. ¿Es un detalle, o es la lista de líneas con un hero encima?
