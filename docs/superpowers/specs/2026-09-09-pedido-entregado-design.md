# El estado `entregado` deja de ser un fantasma

**Fecha:** 2026-09-09
**Estado:** diseño propuesto, pendiente de revisión de JM
**Origen:** JM, mirando el código: «veo que tenemos un estado entregado pero no
lo estamos usando».

## Problema

`entregado` existe en tres lugares del código y **nada lo asigna nunca**.

| Dónde | Qué hace hoy |
|---|---|
| `app.py:6609` | Un filtro que **excluye** los entregados del listado y del tablero |
| `templates/partials/_detail_timeline.html:11` | El 4º paso de la barra de progreso del detalle |
| `templates/partials/_detail_hero.html:46` | Un icono de camión que nunca se dibuja |

Los únicos estados que el código escribe son `pendiente` (default), `preparado`
(`app.py:8591`, `app.py:9000`) y `facturado` (`app.py:9382`).

Producción, 2026-09-09:

| estado | pedidos | más viejo | más nuevo |
|---|---|---|---|
| `facturado` | 964 | 2025-05-26 | hoy |
| `pendiente` | 9 | 2026-09-07 | hoy |

Cero `entregado`. Cero `preparado`: la cola pasa tan rápido por ahí que nunca
hay ninguno quieto.

### Por qué importa, y no es solo código muerto

**1. `facturado` está haciendo doble trabajo.** JM confirmó el flujo: se prepara,
se factura —a veces el día anterior— y la entrega física ocurre **después**. O
sea que `facturado` significa «facturado», pero el tablero lo lee como
«terminado». No hay forma de contestar *¿qué está facturado pero todavía no
llegó al cliente?*.

**2. Un facturado sin entregar desaparece del tablero al día siguiente.**
`_agrupar_tablero` (`app.py:3902`) hace `continue` sobre cualquier `facturado`
que no sea de hoy. Si algo se factura el lunes para entregar el lunes y no sale
en el camión, el martes no está en ningún grupo: ni Atrasados, ni Hoy, ni
Próximos. Es **trabajo invisible**, que el spec del tablero ya declaró como el
peor fallo posible en una herramienta operativa — y acá está ocurriendo por una
puerta que ese spec no miró.

**3. La barra de progreso miente en los 973 pedidos.** Muestra 4 pasos y el
cuarto es inalcanzable, así que una factura cobrada y entregada hace un año se
ve como 3 de 4, incompleta para siempre.

**4. El filtro de `app.py:6609` es una mina.** Está puesto sobre `base_query`,
antes de los conteos y de todo lo demás, así que un pedido en `entregado`
desaparece del tablero, de la lista, de `?estado=todos` y hasta del total que
dice «Ver los N pedidos». El estado que significa «esto salió bien» sería el
que borra el pedido de la vista.

## Diseño

### La transición

`POST /pedidos/<id>/entregar` pone `estado = 'entregado'`. Un botón
**«Entregado»** en la tarjeta, que el chofer toca desde el teléfono al dejar la
mercadería.

**Solo desde `facturado`.** No se puede marcar entregado algo que no se facturó:
si se pudiera, ese pedido saldría de la cola sin haber generado factura y no la
generaría nunca. Es plata que se pierde en silencio, que es la peor forma de
perderla. Un `preparado` que ya salió al cliente hay que facturarlo primero.

**Con deshacer.** El chofer va a tocar la tarjeta equivocada alguna vez: un
toque irreversible en un teléfono que se maneja con una mano, en la calle, es
un callejón sin salida. «Deshacer» devuelve a `facturado` y queda registrado
como un evento más, no como un borrado.

Regla exacta, para que no quede a interpretación: **la ruta acepta la vuelta
`entregado → facturado` siempre** (no hay ventana de tiempo: una regla horaria
solo agrega un caso raro que falla justo cuando hace falta), pero **la tarjeta
solo dibuja el botón dentro del grupo «Hoy»**. Así el chofer lo tiene donde
está trabajando y el archivo de 960 pedidos no se llena de botones que
invitan a un toque equivocado.

Rastro por `_log_pedido_evento(pedido, 'entregado', …)`, igual que el resto de
las transiciones. La hora del evento es la hora real de la entrega, que es un
dato que hoy no existe en ningún lado.

### El tablero pasa a decir tres cosas en vez de dos

Grupo **Hoy**, después del cambio:

| Estado | Qué significa en el tablero |
|---|---|
| `pendiente` | por preparar |
| `preparado` | preparado, falta facturar |
| `facturado` | **por entregar** ← lo que hoy no se puede nombrar |
| `entregado` | hecho, marcado como tal |

Y **Atrasados** gana lo que hoy se pierde: un `facturado` con `fecha_entrega`
vencida y sin entregar es exactamente el pedido del punto 2 del problema.

Se mantiene la decisión ya aprobada del spec del tablero: **lo hecho no
desaparece de «Hoy»**, se muestra marcado. Antes «hecho» era `facturado`; ahora
es `entregado`. El motivo no cambia — si desapareciera, el tablero se vacía a
media tarde y se pierde la otra mitad del trabajo, que es ver si el día cerró
completo.

### La lista deja de esconder

- Se **elimina** `Pedido.estado != 'entregado'` de `app.py:6609`.
- `entregado` entra en la lista blanca de `estado` (`app.py:6541`), así que
  `?estado=entregado` es una vista legítima.
- `orden_optimizado` (`app.py:6630`) hunde `entregado` igual que `facturado`:
  el trabajo terminado no compite por el tope, y dentro de ese bloque se ordena
  por `id` descendente (lo último, primero), no por fecha de entrega
  ascendente — la misma corrección que se le hizo a `facturado` cuando «se
  perdió un pedido después de facturarlo».
- `status_counts` cuenta `entregado`.
- El conteo de `vencido` (`app.py:6711`) excluye `entregado` además de
  `facturado`: un pedido entregado no está vencido, se entregó.

### Lo que ya estaba y ahora funciona

La barra de progreso del detalle y el icono de camión del hero no se tocan:
están escritos y correctos, simplemente nunca se activaban. Al existir la
transición, el 4º paso se alcanza y el detalle deja de mostrar todos los
pedidos como incompletos.

Falta la píldora: `pedidos_list.css` tiene `.status-pill` para `pendiente`,
`preparado` y `facturado` (líneas 609-623) pero no para `entregado`, así que
saldría sin estilo. Hay que agregarla, con el blindaje
`body[data-pedidos-list-screen]` que el archivo ya usa —sin él, `dark-theme.css`
deja el texto claro sobre fondo claro— y lo mismo para `.estado-badge`
de la tabla de escritorio.

### El backfill

Sin esto, el día del deploy los 960 facturados viejos reaparecen como trabajo
pendiente: 910 en «Sin fecha de entrega» y 50 en «Atrasados». El tablero pasa
de 20 tarjetas a 980.

Reparto de los 964 facturados en producción:

| Población | Cuántos | Qué se hace |
|---|---|---|
| Sin `fecha_entrega` (el archivo pre-16/08) | 910 | → `entregado` |
| Con `fecha_entrega` anterior al día local | 50 | → `entregado` |
| Con `fecha_entrega` del día local, facturados hoy | 4 | **se dejan en `facturado`** |

Los 960 primeros están entregados hace semanas o meses; afirmarlo no es
inventar un dato, es escribir el que ya era cierto. Los 4 de hoy (PED-1323,
1324, 1333, 1336) son justamente el estado que este spec viene a poder nombrar:
facturados esta mañana, todavía sin entregar. Dejarlos en `facturado` hace que
el primer día con la función ya muestre trabajo real en «por entregar».

```sql
UPDATE pedido SET estado = 'entregado'
WHERE estado = 'facturado'
  AND (fecha_entrega IS NULL
       OR fecha_entrega < (now() AT TIME ZONE 'America/Curacao')::date);
```

**`CURRENT_DATE` NO sirve acá, y no es teoría: se probó.** La base de producción
corre en UTC (`current_setting('TimeZone')` = `UTC`), así que a partir de las
20:00 de Curaçao `CURRENT_DATE` ya es el día siguiente. Corriendo la cuenta con
`CURRENT_DATE` a las 19:55 locales del 09/09, los afectados daban **964** en vez
de 960: los 4 pedidos que se están entregando HOY entraban en el `UPDATE` y
quedaban marcados como entregados sin haber salido. Con la fecha de Curaçao dan
960 y los 4 se quedan en `facturado`, que es lo correcto.

Es exactamente la misma trampa que ya documentó el expediente de Temperaturas
(`registrado_en` en UTC, buckets AM/PM en el día equivocado). Vale para el
`UPDATE` y vale para cualquier consulta de verificación que se corra alrededor.

**Contar antes de escribir.** El `SELECT` equivalente tiene que dar 960
afectados y 4 intocados; si da otra cosa, el día cambió o algo se movió, y hay
que mirar antes de correr el `UPDATE`.

**Orden: primero el deploy, después el UPDATE, en el mismo minuto.** Al revés,
entre el UPDATE y el deploy el código viejo sigue teniendo el filtro de
`app.py:6609` y los 960 desaparecerían del archivo — se leería como pérdida de
datos. En el orden propuesto, la ventana muestra 50 falsos atrasados durante un
par de minutos, que es molesto pero no asusta, y se corrige solo.

No es una migración de esquema: `estado` es un `String(30)` y no hay `ALTER`
que correr. Igual va a mano por `heroku pg:psql`, como todo en este repo.

### Fuera de alcance

- **No se crea un usuario ni un rol de chofer.** En producción hay 2 usuarios
  activos y los dos son `super_admin` (`admin`, `jcarrasco`); el único
  `vendedor` está inactivo desde junio 2025. Así que «el chofer marca en la
  calle» hoy significa que entra con una de esas dos cuentas. Funciona, pero
  una cuenta propia con permisos acotados es un trabajo aparte.
- No se captura firma, foto ni receptor de la entrega. Solo el hecho y la hora.
- No se toca el flujo de facturación ni el de preparación.
- No se rellena `fecha_entrega` en los 910 históricos (sigue igual que en el
  spec del tablero).
- No se agrega «entregado» a la tabla de escritorio del modo lista más allá del
  badge: esa vista es el archivo.

## Verificación

### Tests de la transición

- Un `facturado` pasa a `entregado` y deja evento con los dos estados en `meta`.
- Un `pendiente` y un `preparado` **se rechazan**: es el guarda que protege la
  factura. Hay que comprobarlo rompiéndolo a propósito — en este repo ya pasó
  dos veces que un test verde no protegía nada.
- Deshacer devuelve a `facturado` y deja su propio evento.
- IDOR: un vendedor que no ve ese cliente no puede marcar entregado.
- `next` no permite salir del host.

### Tests de agrupación

Extendiendo `tests/test_pedidos_tablero.py`, que ya cubre los cuatro grupos:

- `facturado` con entrega de hoy → **Hoy**, y NO marcado como hecho.
- `facturado` con entrega vencida → **Atrasados**. Éste es el test que más
  importa: es el trabajo invisible del punto 2, y si falla el pedido se pierde.
- `entregado` con entrega de hoy → **Hoy**, marcado hecho.
- `entregado` fuera de hoy → **en ningún grupo** (es archivo).

### Tests de la lista

- `?estado=entregado` devuelve los entregados. Si `app.py:6609` sobrevive, este
  test falla — que es el punto.
- `status_counts.total` incluye los entregados.
- Un `entregado` no cuenta como vencido.

### Verificación en navegador

Midiendo **el render**, no la propiedad que el código acaba de escribir: la
píldora `entregado` con su color real (`getComputedStyle`), y el recorrido
completo en el preview —facturar, marcar entregado, ver el salto de grupo,
deshacer— a 375px y en escritorio.

### Rotura conocida de antemano

El dashboard cuenta pedidos por estado con `filter_by(estado='facturado')`
(`app.py:2244` y `app.py:2424`; el de `app.py:5433` es `pedidos_pendientes`
y no lo toca este cambio). Si el
dashboard debe seguir contando los entregados como facturados es una pregunta
abierta: **hoy un pedido entregado dejaría de contar como venta facturada en el
dashboard**, y eso sería una regresión silenciosa en las cifras. Hay que
decidirlo antes de implementar (ver Pendiente).

## El dashboard (decidido por JM, 2026-09-09)

`ventas_mes` sale de QuickBooks y no de estos estados, así que la cifra grande
no se mueve. Pero los dos contadores de `pedidos_facturados` (`app.py:2244` y
`app.py:2424`) filtran por `estado='facturado'` y, tras el backfill, pasarían
de 964 a 4 — una regresión silenciosa en números que JM mira todos los días.

**Decisión: los dos contadores pasan a `estado.in_(['facturado', 'entregado'])`.**
«Cuántos pedidos se facturaron» sigue siendo verdad: un pedido entregado se
facturó igual, entregarlo no lo desfactura. Ninguna cifra existente se mueve.

Corolario para la implementación: **cualquier consulta que hoy pregunte
`estado == 'facturado'` con el sentido de «ya se facturó» tiene que pasar a
incluir `entregado`.** Las que preguntan con el sentido de «está terminado»
—el tablero— son las que cambian de dueño y pasan a mirar `entregado`. Los dos
sentidos vivían en la misma palabra y por eso hay que revisarlos uno por uno,
no con un reemplazo global.

## Archivos que toca

| Archivo | Qué |
|---|---|
| `app.py` (`entregar_pedido`, nuevo) | La transición y el deshacer |
| `app.py` (`_agrupar_tablero`) | `entregado` es lo hecho; `facturado` vuelve a ser trabajo |
| `app.py` (`lista_pedidos`) | Sacar el filtro de la línea 6609; lista blanca, orden, conteos |
| `app.py` (conteos del dashboard) | Según lo que se decida en «Pendiente» |
| `templates/_pedido_card_cuerpo.html` | Botón «Entregado» y «Deshacer» |
| `static/css/pedidos_list.css` | `.status-pill.entregado` y `.estado-badge.estado-entregado` |
| `tests/test_pedido_entregado.py` (nuevo) | Transición, guardas, IDOR |
| `tests/test_pedidos_tablero.py` | Los cuatro casos nuevos de agrupación |
| — (producción) | El `UPDATE` de los 960, después del deploy |
