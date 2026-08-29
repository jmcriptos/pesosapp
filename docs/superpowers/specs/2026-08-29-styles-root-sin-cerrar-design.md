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

---

## Resultado de la ejecución (2026-08-29)

Ejecutado en `fix/styles-root-cerrar`. **Dos de los criterios de aceptación
estaban mal planteados y se corrigen acá.**

### Lo que el spec acertó

La llave se cerró (371/371 en fuente y minificado) y la verificación por línea
base no encontró ni una regresión: **4760 elementos iguales, 9 mejoras, 0
roturas**, sobre 14 pantallas × claro/oscuro × móvil/escritorio. El scroll del
documento es idéntico (1833px antes y después, el último elemento termina en el
mismo píxel), así que no hay contenido recortado.

El efecto más grande no estaba previsto en el spec: **toda la app se renderizaba
en Arial**. `html, body { font-family: Arial, sans-serif }` —línea 42, una de
las 339 anidadas— le ganaba a la pila de fuentes real por el impulso del
`:root`. Al cerrar la llave vuelve `-apple-system`. Es la corrección más visible
del cambio y no figuraba entre los síntomas medidos.

Las 9 mejoras: el segmentado de las pantallas `.ops-*` (4,10 → 6,92), las
pestañas del dashboard (4,10 → 4,55) y el botón primario de la barra de
acciones (4,10 → 5,17), todas en modo oscuro.

### Lo que el spec se equivocó, y es lo importante

**Los cuatro síntomas medidos NO los causaba el anidamiento.** Los criterios 3 y
4 —«los cuatro síntomas quedan resueltos sin las guardas» y «el workaround de
`-webkit-text-fill-color` se elimina»— son inalcanzables con este cambio, y se
comprobó ejecutándolos: al quitar las guardas, con la llave ya cerrada, los
cuatro síntomas volvieron intactos (píldoras, encabezados y «Facturar» otra vez
en blanco sobre `#1877ff`, 4,10:1; el buscador otra vez claro sobre blanco).

La causa real es una sola regla, en `static/styles.css:1920`, dentro del
`@media (prefers-color-scheme: dark)`:

```css
button:not(.btn-chip):not(.cam-edit) { background-color: #1877ff !important; }
```

Especificidad (0,2,1) **y `!important`**. Le gana a `.filter-pill` (0,1,0) por
mérito propio, sin necesidad de ningún impulso: cerrar la llave no le quita el
`!important` ni la baja por debajo de una clase. Las tres rondas de guardas no
quedaron cortas por atacar los selectores equivocados, sino porque cada ronda
descubría otro `<button>` alcanzado por una regla que pinta **todos** los
botones de la app.

Las guardas se restauraron. Siguen haciendo trabajo real.

### Lo que queda abierto

El arreglo de fondo de esos cuatro síntomas es esa regla, no el anidamiento. Y
hay una decisión de producto encima: JM descartó el modo oscuro el 2026-08-28 y
el toggle se eliminó de toda la app (ver `sin-modo-oscuro-decision`), pero el
bloque `@media (prefers-color-scheme: dark)` de `styles.css` sigue ahí y se
activa solo, según el sistema operativo del usuario. Los cuatro síntomas —y
buena parte de los ~738 `!important` de `dark-theme.css`— existen para contener
un modo oscuro que el producto ya decidió no tener.

Eliminar ese bloque es candidato a ser el arreglo de fondo, y es más barato que
seguir escribiendo guardas. Pero es una decisión de producto y no entra en este
spec.

---

## Continuación: se elimina el modo oscuro por sistema (2026-08-29)

Decisión de JM sobre el cabo suelto que dejó la sección anterior. Se eliminan
los **9 bloques `@media (prefers-color-scheme: dark)`** que quedaban repartidos
en 7 hojas (823 líneas), y con ellos la regla que causaba los cuatro síntomas.

El modo oscuro se había descartado como producto el 2026-08-28 y el toggle se
quitó de toda la app, pero estos bloques no dependían del toggle: se activaban
solos según el sistema operativo. Un iPhone con el sistema en oscuro veía una
variante que ya nadie mantenía.

**Se conserva el marco oscuro** —topbar y tabbar— que vive en `dark-theme.css`
y en las reglas `[data-theme]` de `app-mobile.css`. No es un tema alternativo:
es el diseño.

### Criterio de aceptación, y su resultado

1. **En claro no cambia nada.** Huella por pantalla de color, fondo compuesto,
   tamaño y peso de cada elemento con texto visible, sobre 28 combinaciones
   pantalla × ancho: las 28 idénticas a la línea base. ✅
2. **En oscuro deja de haber divergencia.** De 72 elementos que renderizaban
   distinto en oscuro (19 en `/recepciones`, 6 en `/registros/temperaturas`,
   1 por pantalla en el resto) a **0**. 2434 elementos medidos. ✅
3. Criterios 3 y 4 del spec original, imposibles antes, ahora cumplidos: las
   tres rondas de guardas de `pedidos_list.css` quedaron muertas al irse
   `button:not(.btn-chip):not(.cam-edit)` y se eliminaron (−4432 caracteres),
   incluido el `-webkit-text-fill-color` del buscador. Verificado que su
   ausencia no mueve ni un píxel: las 28 huellas siguen idénticas. ✅

### Dos errores propios durante la ejecución, por si alguien repite esto

Ambos de la misma familia: **buscar `@media (prefers-color-scheme: dark)` con
una expresión regular que no distingue código de comentario.**

1. La nota que insertaba en lugar de cada bloque contenía esa misma cadena. El
   bucle re-escaneaba, matcheaba su propia nota y seguía borrando: `styles.css`
   pasó de 371 llaves a 310.
2. Ya sin la cadena en la nota, `app-mobile.css` y `gestion.css` **tienen
   comentarios que explican el problema** y por tanto la contienen. El escaneo
   los matcheó y se llevó CSS incondicional, entre otras cosas
   `main.app-content label { color: #475569 !important }`. Esto sí se coló a la
   verificación y apareció como «8 de 28 pantallas cambiaron en claro» — que es
   justamente lo que la comprobación existe para atrapar.

La versión correcta enmascara el contenido de los comentarios en una copia de
igual longitud antes de buscar y de contar llaves, y recoge todos los tramos en
una sola pasada para borrarlos de atrás hacia adelante.
