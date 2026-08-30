# Crítica — /pedidos/nuevo (formulario de alta de pedidos)

**Fecha:** 2026-08-29 · **Método:** dual-agent (A: revisión de diseño · B: detector + navegador)
**Objetivo:** `templates/pedido_form.html`, `templates/pedido_cliente.html`, `static/css/pedido_nuevo.css`
**Modo:** Operate · **Salud de diseño: 16/40** (las diez heurísticas aplican)

| # | Heurística | Pts |
|---|---|---|
| 1 | Visibilidad del estado | 2 |
| 2 | Correspondencia con el mundo real | 1 |
| 3 | Control y libertad | 1 |
| 4 | Consistencia y estándares | 2 |
| 5 | Prevención de errores | 2 |
| 6 | Reconocer antes que recordar | 2 |
| 7 | Flexibilidad y eficiencia | 1 |
| 8 | Estético y minimalista | 2 |
| 9 | Diagnóstico y recuperación | 2 |
| 10 | Ayuda y documentación | 1 |

## Prioridades

- **P0 — El total no dice que es sin impuesto, y los grupos se nombran con códigos.**
  **CORRECCIÓN (2026-08-30):** la primera versión de este hallazgo decía que un
  pedido «Impuesto 14» se facturaba 14% más caro. Era falso. `tax_rate` es un
  **código de QuickBooks, no un porcentaje** —el propio código lo advierte tres
  veces— y la app ya traduce: `templates/productos.html:108` muestra
  **código 10 = OB 6%** y **código 14 = OB 0%**. En producción solo existen
  esos dos (41 y 23 productos).
  Lo real: `precio_base` es tax-exclusive, así que un pedido del grupo 10 se
  factura **6% por encima** de lo que muestra la pantalla, y uno del grupo 14
  se factura igual. `pedido_form.html:128-130` imprime «Total XCG» sin
  calificar. Y el formulario nombra los grupos con el código crudo mientras la
  pantalla de productos ya los nombra en castellano.
- **P1 — Sin borrador, sin offline, sin estado de fallo.** No hay service worker en el repo (verificado). El submit es POST clásico: si cae la red se pierde el pedido entero. El propio código dice «en ruta la señal falla» (`pedido_cliente.html:102`) y con eso blindó el buscador de clientes, no el envío.
- **P2 — El paso 4 no es entrada de historial.** `mostrarPaso('revision')` solo togglea `hidden`, sin `pushState`. El swipe-back de la PWA en la revisión destruye el pedido. No hay `beforeunload`.
- **P3 — El paso 2 (grupo) es un peaje.** Los 62 clientes ven los mismos dos grupos, con los mismos ejemplos alfabéticos del catálogo. 27 de 49 clientes compran de un solo grupo. El banner explica la restricción de QuickBooks y nunca el remedio.
- **P4 — El momento de éxito miente.** `flash('Pedido creado con precios registrados.')` es incondicional (verificado, `app.py:6906`): lo dice también sobre un pedido con tres líneas SIN PRECIO y total 0.00. Y el flujo colapsa a otro mundo visual al redirigir.
- **P5 — El default de entrega cae en fin de semana.** El `while (getDay()===0||getDay()===6)` se aplica solo al tercer chip, no a «Mañana», que es el default (verificado, `pedido_form.html:265-269`).

## Evidencia mecánica (Assessment B)

- El detector sobre las plantillas crudas dio `[]` exit 0 — **falso**: no resuelve `url_for()` de Jinja y corrió sin CSS. Contra el HTML renderizado: 11 hallazgos, exit 2.
- De esos 11, la mayoría son del shell compartido (`dark-theme.css`, `app-mobile.css`) y no de estas plantillas; `nested-cards` y `side-tab` son falsos positivos (referencian `.metric-card`, ausente de la página).
- Hallazgos reales y propios de la plantilla: `.pn-grupo-chip` mide **131×40** (falla el mínimo de 44 por 4px); el dropdown de Tom Select **tapa** el botón «Añadir» (71%) y la etiqueta «Entrega» (79%).
- Contraste: los botones de acción dan 18,23:1 (sólidos, sin degradado). El texto secundario `#727268` da 4,69:1 — pasa por 0,19. `--pn-apagado` `#a8a8a0` sobre hueso da **2,3:1** y es el nombre del producto recién quitado.

## Menores de nota

Cantidades sin unidad visible; precio unitario y de línea en pantallas distintas; 313px de cabecera congelada en iPhone (43px de área útil con teclado abierto); sin `max-width` en escritorio (1.100px entre producto y precio); `outline:none` sin reemplazo en los cuatro inputs; «Compra cada 1 días»; las notas del cliente no se recuerdan entre pedidos.
