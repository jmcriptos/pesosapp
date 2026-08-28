# El listado de pedidos deja de ser una lista y pasa a ser un tablero

**Fecha:** 2026-08-28
**Estado:** diseño aprobado, pendiente de plan de implementación
**Alcance:** etapa 1 de 2. La etapa 2 (historial de pedidos dentro del cliente)
tiene su propio spec cuando llegue.

## Problema

`/pedidos` intenta ser dos cosas a la vez y es mediocre en las dos: la cola de
trabajo del día y el archivo de todo lo facturado. Los números de producción
muestran que no son mitad y mitad.

| Dato | Valor |
|---|---|
| Pedidos totales | 942 (el más viejo, 2025-05-26) |
| En `pendiente` o `preparado` (28/08 18:40) | **0** — los 942 están facturados |
| Ritmo | ~15 por semana (≈3 por día) |
| Del pedido a la factura | mediana **21 h**; 64 de 184 el mismo día |
| Con `fecha_entrega` | 32 de 942 — y **32 de 32** de los creados desde que existe la columna (16/08) |
| Con notas | 45 de 942 |
| Clientes distintos | 49 |
| Usuarios activos | 2 |

De ahí salen tres hechos que mandan sobre el diseño:

1. **La cola es diminuta y efímera.** A 3 pedidos por día que viven ~1 día, en
   cualquier momento hay unos 3 abiertos. No necesita paginación, ni filtros,
   ni ordenamiento por columna: entra entera en una pantalla.

2. **El default está vacío casi siempre.** Medido en el log del router el
   2026-08-28: `GET /pedidos?estado=por_preparar&partial=1` → 1173 bytes, que
   es el estado vacío. La pantalla abre en «Por preparar» y no hay nada que
   preparar, porque la cola se vacía cada día.

3. **`fecha_entrega` no es un dato roto, es un dato nuevo.** El formulario la
   carga siempre (32/32 desde el 16/08). Los 910 sin fecha son exactamente el
   archivo histórico. **El dato ya separa solo la cola del archivo**; no hay que
   inventar la frontera.

Las dos intenciones que JM declaró en el brainstorming:

- Abre `/pedidos` sobre todo para **trabajar lo de hoy**, y «hoy» significa
  **lo que hay que entregar hoy** (por `fecha_entrega`, no por fecha del pedido
  ni por estado).
- Consulta el archivo **por cliente** («qué le mandamos a Mangusa»), no
  cronológicamente.

Hoy la pantalla no sirve ninguna de las dos: los dos filtros que ocupan el tope
(«Por preparar» y «Hoy») no responden a «lo de hoy» —uno filtra por estado y se
vacía a media tarde, el otro depende de un campo que tienen 32 de 942—, y el
archivo solo se alcanza paginando 48 veces o buscando por nombre de casualidad.

## Diseño

### Dos modos, decididos por la URL

- **`/pedidos`** → **tablero**.
- **`/pedidos?…`** con al menos uno de los parámetros **reconocidos**
  —`q`, `estado`, `page`, `orden`, `per_page`, `solo_notas`— y con valor no
  vacío → **lista plana**, exactamente la que existe hoy, con sus filtros, su
  paginación y su orden server-side.

Un parámetro que la ruta no conoce (`?utm_source=…`, cualquier cosa que pegue
un cliente de correo) **no cambia el modo**: sigue siendo tablero. Se mira la
lista blanca, no `request.args` a secas, porque si no un parámetro de
seguimiento pegado a un enlace compartido convertiría el tablero en lista sin
que nadie lo pidiera.

El criterio es la presencia de parámetros y no un toggle, y eso **no es
casualidad**: es lo que hace que todos los enlaces y marcadores existentes
sigan funcionando sin tocarlos. En particular `/pedidos?estado=pendiente`, que
dispara el aviso del dashboard (`app.py:1915`).

Nada de lo construido el 2026-08-28 se tira: la lista plana con su orden en
servidor, su paginación con primera/última y su estado vacío es el modo lista.

### El tablero: cuatro grupos fijos

Sin píldoras de estado, sin paginación, sin orden por columna.

| Grupo | Predicado | Notas |
|---|---|---|
| **Atrasados** | `fecha_entrega < hoy_local` y `estado != 'facturado'` | En rojo. |
| **Hoy** | `fecha_entrega = hoy_local`, **cualquier estado** | Los facturados se muestran marcados como hechos. |
| **Próximos** | `fecha_entrega > hoy_local` y `estado != 'facturado'` | Sin techo de días: si hay uno a tres semanas, es trabajo pendiente igual. |
| **Sin fecha** | `fecha_entrega IS NULL` y `estado != 'facturado'` | Red de seguridad. Hoy estaría vacío. |

`hoy_local` es el día en `DASHBOARD_TIMEZONE` (America/Curaçao, UTC−4), nunca
`date.today()` del servidor.

Orden dentro de cada grupo: `fecha_entrega` ascendente, `id` descendente para
desempatar.

Un grupo vacío **no se dibuja** — ni encabezado ni cero. Una pantalla que
afirma cosas que no son entrena a desconfiar de ella.

Los grupos son disjuntos y cubren todo lo no facturado, más las entregas de hoy
ya facturadas. Un pedido no puede aparecer dos veces.

#### Las dos decisiones que no salieron de la pregunta original

**Los facturados de hoy se quedan en «Hoy», marcados como hechos.** Estrictamente
«lo que hay que entregar hoy» los sacaría al facturarse, pero entonces el
tablero se vacía a media tarde y se pierde la otra mitad del trabajo: ver que el
día cerró completo. Aprobado por JM.

**«Sin fecha» existe aunque hoy esté vacío.** Un pedido sin facturar y sin
`fecha_entrega` no entraría en ningún otro grupo y sería **trabajo invisible**.
Es el peor fallo posible en una herramienta operativa, así que el grupo existe
como guardia permanente. Aprobado por JM.

#### Techo de seguridad

Cada grupo dibuja como máximo 50 filas y, si las supera, muestra debajo un
enlace a `?estado=todos` con el texto «y N más». Con 3 pedidos por día no
debería pasar nunca; es seguro barato contra que una anomalía de datos
convierta el tablero en una página de 942 filas.

El enlace apunta a la lista completa y **no** a un filtro por grupo, porque dos
de los cuatro grupos —«Próximos» y «Sin fecha»— no tienen equivalente en la
lista blanca de `estado` y habría que inventarles uno para un caso que no va a
ocurrir.

### La búsqueda es la puerta del archivo

Escribir en el buscador cambia de modo: desde el tablero, teclear «Mangusa»
lleva a la lista plana buscando en los 942 —cola y archivo juntos—, con el
mismo fetch parcial que ya existe. Borrar la búsqueda vuelve al tablero.

En el pie del tablero, un enlace de escape: **«Ver los N pedidos»**, donde N es
el total vivo que ya calcula `status_counts.total` — no un número escrito a
mano, que envejecería mal a 15 pedidos por semana.

Esto cubre el «por cliente» de forma provisional (el buscador ya matchea
`Cliente.nombre`) hasta que la etapa 2 le dé su lugar propio dentro del cliente.

### Estados vacíos

- Tablero sin nada en ningún grupo → «Nada para entregar hoy», con el acceso al
  archivo debajo. Calmo, no alarmante: un día sin entregas pendientes es un día
  bien cerrado, no un error.
- Búsqueda sin resultados → el vacío que ya existe, que distingue «no coincide»
  de «no hay pedidos» y ofrece «Ver todos los pedidos». **No se toca.**

### Fuera de alcance

- No se rellena `fecha_entrega` en los 910 históricos.
- No se toca el formulario de alta ni la captura de la fecha.
- No se agregan estados nuevos al modelo.
- El historial por cliente es la etapa 2.

## Verificación

### Tests de agrupación

Un pedido en cada situación cae en **un solo** grupo y en el correcto:

- atrasado sin facturar → Atrasados;
- entrega hoy y ya facturado → Hoy marcado hecho, y **no** en Atrasados ni en
  Próximos;
- entrega futura sin facturar → Próximos;
- **sin facturar y sin `fecha_entrega` → «Sin fecha»**. Éste es el test que más
  importa: si falla, la pantalla esconde trabajo.

### Tests del contrato de modos

- `GET /pedidos` devuelve tablero y **no** trae marcadores de paginación.
- `GET /pedidos?estado=pendiente` devuelve la lista plana, igual que hoy. Es
  literalmente el enlace del dashboard: si se rompe, se rompe en producción sin
  que nadie toque nada.
- Buscar desde el tablero devuelve resultados de todos los estados.

### Verificación en navegador

Midiendo **el render** (altura real, `getComputedStyle`), nunca la propiedad que
el propio código acaba de escribir. Móvil (390×844) y escritorio (1440×900) en
una sola ronda.

### Rotura conocida de antemano

`tests/test_pedidos_lista_entrega.py` lee los contadores haciendo
`GET /pedidos` y buscando `.filter-pill-count`. En modo tablero no hay
píldoras, así que sus cuatro tests van a fallar. **No es que la app se rompa**:
es el mismo acoplamiento a markup que ya rompió esos tests el 2026-08-28 por la
mañana. Hay que apuntarlos a `/pedidos?estado=todos`, que es donde las píldoras
siguen viviendo.

## Archivos que toca

| Archivo | Qué |
|---|---|
| `app.py` (`lista_pedidos`) | Decidir modo por presencia de parámetros; construir los cuatro grupos para el tablero |
| `templates/pedidos.html` | Tablero vs lista; el buscador queda en los dos |
| `templates/_pedidos_tablero.html` (nuevo) | Los grupos |
| `templates/_pedido_card_cuerpo.html` (nuevo) | El cuerpo de la tarjeta, extraído para que el tablero y la lista usen literalmente la misma |
| `templates/_pedidos_resultados.html` | Es el modo lista. Solo cambia por la extracción de la tarjeta a su parcial: nada de su lógica se toca |
| `static/css/pedidos_list.css` | Encabezados de grupo, marca de «hecho» |
| `tests/test_pedidos_tablero.py` (nuevo) | Agrupación y contrato de modos |
| `tests/test_pedidos_lista_entrega.py` | Apuntar a `?estado=todos` |
