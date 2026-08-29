# El radar de clientes

**Fecha:** 2026-08-29
**Estado:** diseño pendiente de revisión
**Origen:** etapa 2 del tablero de pedidos
(`docs/superpowers/specs/2026-08-28-pedidos-tablero-design.md`)

## Qué cambia respecto de lo que decía la etapa 1

La etapa 1 dejó anotado que la etapa 2 sería «el historial de pedidos dentro
del cliente». Los datos de producción dicen que eso vale poco y que hay una
pregunta más urgente sin responder. El cambio de rumbo lo aprobó JM.

**Por qué el historial vale poco:** el buscador del listado ya encuentra por
nombre de cliente, y `_calcular_pedido_habitual` ya precarga el alta con lo de
las últimas 4 visitas — «repetir y ajustar» existe y está vivo en
`nuevo_pedido`. Un expediente sería, en buena parte, una tercera puerta a lo
mismo.

**Cuál es la pregunta sin responder:** *¿a quién le vendo esta semana?*

## Problema

`/clientes` es la cuarta pestaña de la barra inferior. Es lo que el vendedor
toca esperando «mis clientes», y hoy recibe un CRUD: las 62 filas **ordenadas
por `Cliente.id` ascendente** —o sea, por orden de alta en la base—, cada una
con el nombre, un chip de moneda y el ID de QuickBooks, más editar y borrar.

Es una vista de administración de base de datos en el lugar donde vive la
pregunta comercial. El ID de QuickBooks no le sirve a nadie en la calle.

Y mientras tanto, medido hoy en producción:

| Grupo | Clientes |
|---|---|
| Compraron hace poco, dentro de su ritmo | 26 |
| **Se pasaron de su propio ritmo (≤90 días)** | **5** |
| Sin comprar hace más de 90 días | 18 |
| Nunca compraron | 13 |
| **Total** | **62** |

Los cinco atrasados, con su ritmo propio:

| Cliente | Días sin comprar | Su ritmo | Veces su ritmo | Pedidos |
|---|---|---|---|---|
| Rio Frio Center | 85 | 15 d | 5,7× | 15 |
| Liza Convenience Store | 32 | 13 d (estimado) | 2,5× | 1 |
| Arco Iris | 50 | 18 d | 2,8× | 27 |
| Roberto Da Silva | 14 | 6 d | 2,3× | 16 |
| New California | 79 | 41 d | 1,9× | 11 |

Arco Iris hizo 27 pedidos y lleva 50 días sin comprar. Rio Frio Center, 15
pedidos y 85 días. **Nada en la app muestra eso.** Son relaciones que se
apagaron sin que nadie se enterara.

## Diseño

`/clientes` pasa a ser el radar. El alta, la edición y el borrado siguen
existiendo pero dejan de ser el contenido principal.

### La regla

**Ritmo propio** = mediana de días entre **días distintos con pedido** del
cliente.

Entre días distintos, no entre pedidos: hay clientes que cargan varios pedidos
la misma fecha, y midiendo entre pedidos su mediana da **0 días**. Con esa
cuenta, Best Buy aparecía atrasado con «ritmo 0d» —un falso positivo y encima
ilegible—. Midiendo entre fechas, su ritmo real lo saca de la lista y a Roberto
Da Silva le da su ritmo verdadero de 6 días.

Hace falta un mínimo de **2 intervalos** (3 fechas distintas con pedido) para
que el ritmo sea propio. Por debajo se usa el **ritmo del negocio: 13 días**
—la mediana global entre días con pedido— y la fila lo dice: «ritmo estimado».
Son 9 clientes con 1 o 2 pedidos; se ordenan junto al resto en vez de esconderse
en un cajón, pero sin fingir una precisión que no existe.

**Atraso** = días sin comprar ÷ ritmo. Un cliente entra en Atrasados cuando
supera **1,5×** su ritmo.

El umbral está elegido contra los datos, no a ojo: con 1,5× salen 5 clientes,
que es una semana de trabajo. Más bajo se llena de ruido; más alto llega tarde.

### Los grupos

En este orden, y con estos nombres:

1. **Atrasados** (5) — pasaron 1,5× su ritmo y compraron dentro de los últimos
   90 días. Ordenados por veces-su-ritmo, de mayor a menor. Es el contenido
   principal de la pantalla.
2. **Al día** (26) — el resto de los que compraron en 90 días. Mismo orden, así
   que arriba quedan los que se están por pasar.
3. **Dormidos** (18) — más de 90 días. **Sección plegada**, con la cuenta en el
   encabezado. Ordenados por cantidad de pedidos históricos, de mayor a menor:
   en un cliente dormido lo que importa es cuánto se perdió, no cuánto hace.
4. **Nunca compraron** (13) — sin ningún pedido. Sección plegada al final,
   alfabética. No son un fracaso comercial: son altas hechas para dejarlas
   listas.

### La fila

```
⚠  Arco Iris                                        [+ Pedido]
   50 días sin comprar · su ritmo: 18 d · 27 pedidos
```

Nombre primero y grande — es lo que se busca con el ojo. Debajo, en una línea:
días sin comprar, ritmo, cantidad de pedidos. La acción principal es **crear un
pedido para ese cliente**, que enlaza a `/pedidos/nuevo?cliente=<id>` —el
camino que ya existe y que además precarga el habitual—. Editar queda como
icono secundario.

**La fila no muestra importes, y es deliberado.** El importe que ve el usuario
lo calcula Python con `peso_real`; el SQL no lo reproduce (está anotado en el
spec del tablero y por eso «Total» no es ordenable en el listado). Mostrar plata
acá obligaría a calcular 942 pedidos en cada carga, o a mostrar un número que se
contradiga con el del pedido. La cantidad de pedidos alcanza como medida de lo
que está en juego.

### Estados vacíos

- **Nadie atrasado** → «Todos al día» con tono tranquilo, y las otras secciones
  debajo. Es un buen resultado, no una pantalla rota.
- **Vendedor sin clientes visibles** → el vacío que ya existe en `clientes.html`.
- La búsqueda por nombre que ya funciona (`data-buscar`) **no se toca**: filtra
  sobre las secciones.

### Visibilidad

Sin regla nueva. Se reutiliza la que ya aplica `mostrar_clientes`: `super_admin`
ve todos, el vendedor ve `obtener_clientes_visibles()`. El radar solo cambia el
orden y el agrupamiento de ese conjunto.

### Rendimiento

62 clientes y 942 pedidos. El ritmo y el último pedido salen de **una sola
consulta agregada** con `GROUP BY cliente_id`, no de recorrer clientes
preguntando por sus pedidos. Nada de N+1: hoy la pantalla hace una query y tiene
que seguir haciendo una.

## Verificación

### Tests de agrupación

Cada caso cae en **un solo** grupo y en el correcto:

- compró hace 3× su ritmo, hace menos de 90 días → Atrasados;
- compró hace menos de 1,5× su ritmo → Al día;
- último pedido hace 120 días → Dormidos, **y no** en Atrasados;
- sin ningún pedido → Nunca compraron, **y no** en Dormidos;
- **dos pedidos el mismo día y nada más** → su ritmo NO es 0. Éste es el que
  importa: es el falso positivo que encontró la exploración, y sin test vuelve.

### Tests de ritmo

- 3+ fechas distintas → ritmo propio, marcado «propio»;
- 1 o 2 fechas → ritmo 13, marcado «estimado»;
- el orden dentro de Atrasados es por veces-su-ritmo descendente.

### Verificación en el navegador

Contraste ≥ 4,5:1 en las tres líneas de la fila y en los encabezados de sección;
área táctil ≥ 44px en la acción principal, en el icono de editar y en el
plegado; y que las secciones plegadas se puedan abrir con teclado y anuncien su
estado (`aria-expanded`).

## Fuera de alcance

- El expediente del cliente. Si más adelante hace falta, la fila del radar es su
  puerta natural.
- Tocar `_calcular_pedido_habitual` o el flujo de alta.
- Mostrar importes (ver arriba).
- Notificaciones o avisos automáticos por cliente atrasado.
- Rellenar datos de los 13 clientes sin pedidos.

## Riesgo

**Bajo.** Es una pantalla de lectura sobre datos que ya existen, sin escrituras
ni cambios de modelo. Lo que se reemplaza es el orden y la presentación de
`/clientes`; el alta, la edición y el borrado siguen siendo los mismos
endpoints.

El riesgo real es de producto, no técnico: que la regla marque como atrasado a
quien no lo está. Por eso el umbral se fijó contra los datos y por eso la fila
muestra el ritmo y la cantidad de pedidos — para que el vendedor pueda no
estar de acuerdo con la máquina.
