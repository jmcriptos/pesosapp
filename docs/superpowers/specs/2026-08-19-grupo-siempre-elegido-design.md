# Toma de pedido: el grupo se elige siempre

Fecha: 2026-08-19
Estado: aprobado, pendiente de implementar

## El problema

El flujo de nuevo pedido se bifurca según el historial del cliente:

- Cliente que compra de **2+ grupos** de facturación → pantalla «¿Qué pedido vas
  a tomar?» y recién después el pedido.
- Cliente de **un solo grupo** o **sin historial** → directo al pedido, con el
  grupo resuelto por el sistema (el único que compra) o sin resolver.

En producción son 22 clientes por el primer camino y 40 por el segundo, así que
el vendedor no puede aprender un gesto: la pantalla aparece o no según a quién
le esté vendiendo.

De ahí salió el bug de Luna Park (2026-08-19, arreglado en `46a80dd7`): 28
pedidos, todos de importados, y como el sistema le resolvía el grupo solo, no
había forma de tomarle un pedido de pesables. El fix abrió una salida; este
diseño ataca la causa: **que el sistema elija por el vendedor**.

## La decisión

El grupo se elige **siempre**, para todos los clientes, en su propia pantalla.
Nunca lo decide el sistema.

## Flujo

| Paso | URL | Pantalla |
|------|-----|----------|
| 01 Cliente | `/pedidos/nuevo` | Lista de clientes (sin cambios) |
| 02 Grupo | `?cliente=N` | Los grupos del catálogo, orden fijo |
| 03 Pedido | `?cliente=N&grupo=<clave>` | Armar el pedido (hoy es el 02) |
| 04 Revisar | — | Revisar y enviar (sin cambios) |

Los contadores de las pantallas pasan de `01 / 03`, `01b / 03`, `02 / 03`,
`03 / 03` a `01 / 04`, `02 / 04`, `03 / 04`, `04 / 04`.

Desaparece el paso «01b» —ya no es una bifurcación sino un paso de pleno
derecho— y desaparece `?grupo=nuevo`: con todos los grupos listados no queda
ninguno inalcanzable. Una clave inválida o una URL vieja con `grupo=nuevo` cae
en la pantalla de grupos, que es lo que ya hace hoy una clave inválida.

## Pantalla de grupos

**Los grupos salen del catálogo, no del historial.** Es la diferencia que hace
que la posición de cada uno nunca se mueva: se derivan de los pares
(`se_pesa`, `tax_rate`) presentes en `Producto`. Hoy son tres:

1. Importados · imp. 10
2. Pesables · imp. 10
3. Pesables · imp. 14

Orden fijo: importados antes que pesables, y dentro de cada tipo por `tax_rate`
ascendente. Si mañana aparece un impuesto nuevo entra en su posición por la
misma regla, sin tocar código. Un grupo sin productos en el catálogo no se
lista: no se podría pedir nada de él.

Cada tarjeta muestra:

- La etiqueta del grupo (`_etiqueta_grupo`).
- Dos productos de ejemplo del catálogo — `tax_rate` es un código de
  QuickBooks, no un porcentaje, así que por sí solo no le dice nada al
  vendedor.
- El historial **de este cliente** en ese grupo: «28 pedidos · última vez 18
  ago», o «sin pedidos» si nunca compró de ahí.

El orden no cambia con el historial; el dato del historial sí se muestra. El
vendedor aprende la posición y lee el contexto.

## Paso del pedido

Sin cambios de fondo: el grupo llega siempre fijado por el servidor y, si hay
historial en ese grupo, el pedido habitual llega precargado.

Dos ajustes de pantalla:

- **Botón pequeño con el grupo actual** en la cabecera, bajo el nombre del
  cliente, que vuelve a la pantalla de grupos. Reemplaza el párrafo «Solo se
  ven productos de X» + enlace «Pedir de otro grupo» que se desplegó en
  `46a80dd7`.
- La flecha de volver lleva a la pantalla de grupos, no a la de clientes.

## Qué no cambia

- **La edición de pedidos.** Ahí el grupo lo determinan las líneas que el
  pedido ya tiene; no hay nada que preguntar. «Cambiar cliente» sigue yendo a
  la lista de clientes y volviendo a la edición.
- **El invariante.** Un pedido no puede mezclar grupos, y `_validar_grupo_unico`
  lo sigue validando en el servidor: esta pantalla no es la única puerta de
  entrada.
- **El cálculo del habitual.** Sigue siendo la mediana de las últimas visitas
  dentro del grupo elegido.

## Qué se simplifica

- `_calcular_pedido_habitual` pierde la rama «con un solo grupo se resuelve
  solo»: al paso 3 nunca se llega sin grupo elegido.
- `_grupos_del_cliente` cambia de sentido: pasa de «qué grupos compra este
  cliente» (que definía las opciones) a «cuánto compró en cada grupo» (que
  ahora solo decora tarjetas fijas). La lista de opciones la arma una función
  nueva sobre el catálogo.
- El candado provisional del JS (`sincronizarCandadoProvisional`) queda vivo
  solo para la edición, que es el único camino que llega sin grupo del
  servidor.

## El costo

Los 40 clientes que hoy entran directo al pedido suman un toque. A cambio, el
gesto es el mismo siempre y el grupo nunca lo decide el sistema. Es la compra
explícita de este diseño.

## Tests

**A actualizar** — asumen que un cliente de un solo grupo o sin historial entra
directo al paso del pedido, y ahora tienen que pasar por `&grupo=`:

- `test_pedido_dos_pasos.py`: `test_paso2_cliente_con_historial_siembra_lineas`,
  `test_paso2_orden_de_secciones`, `test_paso2_sin_historial_abre_panel`,
  `test_catalogo_paso2_trae_precio_del_cliente`, y los de permisos que entran
  por `?cliente=`.
- `test_pedido_form_fixes.py`: los que se apoyan en `?cliente=` sin grupo, más
  los tres de la salida del candado, que cambian de forma con el botón nuevo.
- `test_pedido_habitual.py`: revisar los que ejercitan la precarga.

**Nuevos:**

- Los tres tipos de cliente —multi-grupo, un solo grupo, sin historial— ven la
  misma pantalla de grupos con las mismas opciones.
- El orden de los grupos es el mismo sin importar el historial del cliente.
- Cada tarjeta trae el historial de ESE cliente («sin pedidos» cuando no hay).
- Un grupo sin productos en el catálogo no se lista.
- `?grupo=nuevo` (URL vieja) y una clave inválida caen en la pantalla de
  grupos.
- El paso del pedido trae el botón de grupo y vuelve a la pantalla de grupos.

## Referencias

- Fix que abrió la salida del candado: `46a80dd7`.
- Diseño del flujo en dos pasos: `2026-08-17-flujo-form-pedidos-design.md`.
