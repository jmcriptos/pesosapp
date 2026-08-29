# Cerrar el `:root` de styles.css

**Fecha:** 2026-08-29
**Estado:** diseño pendiente de aprobación
**Origen:** tercera crítica del listado de pedidos (`.impeccable/critique/2026-08-29T07-15-17Z__templates-pedidos-html.md`)

## Problema

`static/styles.css` abre `:root {` en la **línea 2** y **nunca lo cierra**. El archivo termina con profundidad de llaves 1.

Como los navegadores modernos soportan anidamiento CSS, todo lo que viene después no se parsea como reglas de nivel superior sino como reglas **anidadas dentro de `:root`**. Medido:

| | |
|---|---|
| Bloques que quedan anidados | **339** |
| De ellos, con `!important` | 41 |
| Bloques `@media` anidados | 15 |
| Balance de llaves del archivo | 371 abiertas / 370 cerradas |

El efecto es que **339 reglas ganan la especificidad de `:root`** (+0,1,0) sobre lo que sus autores escribieron. Una regla pensada como `button { … }` (0,0,1) pasa a valer (0,1,1) y le gana a `.filter-pill` (0,1,0). Con `!important` encima, le gana a casi cualquier cosa.

### Qué rompe hoy, medido

Todos verificados en el navegador con `page.emulateMedia({colorScheme:'dark'})`:

| Síntoma | Ratio |
|---|---|
| Las 5 píldoras de filtro, texto blanco sobre fondo blanco | **1,00:1** |
| El buscador del listado escribe blanco sobre blanco | **1,05:1** |
| «Facturar» se pinta como CTA azul y la jerarquía de seguridad se invierte | 4,10:1 |
| Los 4 encabezados ordenables se pintan como botones encendidos | 4,10:1 |

Y **no se puede razonar sobre ellas desde el navegador**: los selectores que genera ese anidamiento hacen que `element.matches(selector)` lance excepción, así que ni siquiera se pueden enumerar por CSSOM para saber cuál está ganando. La única forma de diagnosticar es por descarte.

### Por qué esto ya no se puede seguir parcheando

Se agregaron guardas de especificidad en `pedidos_list.css` en **tres rondas distintas** —2026-08-28 (dos veces) y 2026-08-29— y las tres veces la lista quedó corta:

1. Primera: `--color-primary-soft-fg` y `--color-danger-soft-fg`.
2. Segunda: `button.pc-action-main`, `button.row-action-main`, `button.pc-action-btn`, `.pedidos-error-btn`.
3. Tercera: `button.filter-pill`, `button.th-orden`, el input del buscador, `--color-danger-soft`.

Cada ronda es una lista de selectores contra una causa que no es una lista. Y el arreglo del buscador terminó dependiendo de `-webkit-text-fill-color`, una propiedad no estándar, porque **no existe guarda de especificidad capaz de apuntar a una regla que no se puede nombrar**.

Además el bleed no es exclusivo de pedidos: `dark-theme.css` y las pantallas `.ops-*` ya arrastran ~738 y ~366 `!important` respectivamente, y buena parte de esa deuda existe para ganarle a esto.

## Diseño

Cerrar la llave. El cambio es de un carácter; el trabajo es la verificación.

### El cambio

Agregar `}` al final del bloque `:root` de `static/styles.css`, después de la última custom property y **antes** de la primera regla que hoy queda anidada (`.app-container`). Regenerar `static/styles.min.css` desde la fuente.

### Lo que hay que verificar, y por qué es el 95% del trabajo

Cerrar la llave **baja la especificidad de 339 reglas de golpe**. Todo lo que hoy funciona porque esas reglas ganan, deja de funcionar. En particular:

- Los **41 bloques con `!important`** pierden el impulso de `:root` pero conservan el `!important`, así que su comportamiento relativo cambia solo frente a otras reglas `!important`.
- Los **15 `@media` anidados** pasan a ser `@media` de nivel superior. Su contenido deja de heredar `:root` y podría dejar de aplicar donde hoy aplica, o empezar a aplicar donde hoy no.
- Todas las guardas de especificidad que se escribieron **para ganarle a este bleed** pasan a ser innecesarias, y algunas podrían ahora ganar donde no deberían.

Se verifica pantalla por pantalla, **en claro y en oscuro**, midiendo el render y no las reglas:

| Pantalla | Por qué |
|---|---|
| `/pedidos` (tablero y lista) | Es la que motivó el spec; tiene tres guardas acumuladas |
| `/pedidos/<id>/detalles` | Usa `detalles_pedido.css` + paneles con `hidden` |
| `/pedidos/nuevo` y `/pedidos/<id>/editar` | `pedido_nuevo.css`, con su propio `[hidden]` y su blindaje anclado en `#pn-shell` |
| `/pedidos/<id>/pesar` | `pesar.css`, pantalla de operación en planta |
| `/dashboard` | `dashboard_snap.css`, KPIs y gráficos |
| `/clientes`, `/productos` | `gestion.css`, con `[hidden]` en las tarjetas de alta |
| `/precios` | `precios.css`, con modal |
| `/registros/*` | Las pantallas `.ops-*`, que son las que más `!important` acumulan |
| `/facturacion`, `/recepciones` | Sirven `scripts.js` directo |

Para cada una: cargar en claro y en oscuro, medir contraste de texto principal, secundario y de los botones de acción, y confirmar que ningún control queda invisible ni cambia de color respecto de la línea base.

**La línea base se captura ANTES de tocar nada**: una pasada por las mismas pantallas guardando, por cada elemento con texto visible, su `color` y su fondo efectivo compuesto. El criterio de aceptación es la comparación contra esa línea base, no una inspección a ojo.

### Criterio de aceptación

1. `static/styles.css` balancea llaves (371/371) y `static/styles.min.css` se regenera desde él.
2. Ninguna de las pantallas de la tabla cambia el color renderizado de su texto respecto de la línea base, en claro ni en oscuro — salvo donde el cambio sea **la corrección buscada** (los cuatro síntomas medidos arriba), y esos casos se enumeran uno por uno.
3. Los cuatro síntomas quedan resueltos **sin** las guardas de especificidad que hoy los tapan; esas guardas se eliminan en el mismo cambio y su ausencia se verifica.
4. El workaround de `-webkit-text-fill-color` del buscador se elimina.
5. La suite pasa (728 al momento de escribir esto).

### Fuera de alcance

- Reducir los `!important` de `dark-theme.css` o de las pantallas `.ops-*`. Es deuda del mismo origen, pero limpiarla es un trabajo aparte y mucho mayor.
- Rediseñar la paleta o los tokens.
- Tocar el comportamiento de modo oscuro más allá de que deje de romper.

## Riesgo

**Alto y ancho, pero acotable.** Es el cambio de un carácter con el radio de impacto más grande del repositorio: afecta a todas las pantallas a la vez. A favor: es trivialmente reversible (un commit), la app tiene 728 tests, y la verificación por línea base convierte «¿se rompió algo?» en una comparación mecánica en vez de un juicio.

Se recomienda hacerlo en rama, con la línea base capturada primero, y **no desplegarlo el mismo día que otro cambio**: si algo se rompe en producción, hay que poder atribuirlo sin ambigüedad.
