# Producción propia: lotes, mermas y rendimiento — Diseño

> Fecha: 2026-10-03 · Módulo: `produccion/` · Rutas: `/produccion`

## Qué resuelve

Registrar la producción de Jomar por lote y controlar la merma y el
rendimiento de cada uno, **sin verificar disponibilidad de ingredientes**.

El módulo de maquila ya tiene corridas de producción, pero trabaja sobre
material ajeno: cada kilo entra por una recepción, vive en un ledger y una
corrida no cierra si el saldo no alcanza. Para la producción propia eso no
sirve: no hay recepciones de los ingredientes de la casa y el bloqueo por
saldo solo estorba. Lo que hace falta es anotar lo que entró, lo que salió y
dónde se fue la diferencia.

## Decisiones

- **Sin ledger ni saldo.** Lo declarado se guarda tal cual. No existe
  «saldo insuficiente». El control es a posteriori: merma y rendimiento por
  lote, y sus reportes.
- **Separación total de maquila.** Producción tiene su propio catálogo:
  **insumos** (`produccion_insumo`) y **fórmulas** (`produccion_formula`,
  `produccion_formula_insumo`), administrados en `/produccion/insumos` y
  `/produccion/formulas` por quien tiene permiso de editar. Ningún modelo
  ni tabla de maquila entra en el módulo (hay un test que lo garantiza).
  La pestaña «Producción» de maquila pasó a llamarse «Corridas» para no
  confundirse.
- **Seis tablas nuevas**: las tres del catálogo más `lote_produccion`,
  `lote_consumo`, `lote_merma`. Nada de maquila se modifica.
- **El peso producido sale de la balanza de pedidos.** Al pesar cajas
  para un pedido, la pantalla de pesar ofrece un desplegable «Lote de
  producción» con los lotes **abiertos** del producto activo; elegir uno
  atribuye la caja al lote (`produccion_lote_caja`), escribe el número de
  lote y las fechas de la etiqueta y su peso cuenta como producto
  terminado del lote. `peso_producido` es una propiedad derivada: cajas
  atribuidas + `peso_adicional` (lo que no pasó por un pedido: muestras,
  stock que se congela, un remanente; se declara a mano). Si una caja se
  borra del pedido («Deshacer»), el vínculo cae por `ON DELETE CASCADE` y
  el lote deja de contarla. Un lote cerrado no admite más cajas.
- **Ningún total se guarda.** Merma, rendimiento y «sin identificar» se
  derivan en cada lectura (`servicios.balance`). El teórico por insumo
  sigue en vivo al peso producido mientras el lote está abierto (cada
  caja pesada lo mueve) y queda congelado al **cerrar**: desde ahí
  cambiar la fórmula no reescribe el rendimiento de ese lote.
- **Balance en kilos.** Solo los insumos con unidad `kg` entran en el
  consumido. La tripa (`ud`) se registra y se compara contra su teórico,
  pero no suma kilos.
- **Merma identificada vs. sin identificar.** Las mermas se anotan por
  causa (cocción y ahumado, recorte, descarte, pérdida en proceso,
  muestras, otra). `merma_total = consumido − producido`;
  `sin_identificar = merma_total − identificada`. La cifra sin identificar
  es un dato, no un error: cerrar no la exige.
- **Merma negativa se muestra.** Si el producto pesa más que lo que entró
  (salmuera o agua no declarada como insumo), el rendimiento sale
  > 100 % y la pantalla lo dice en vez de esconderlo.
- **Umbral de merma alta: 10 %** (`servicios.UMBRAL_MERMA_ALTA_PCT`), igual
  que el reporte de rendimiento de maquila.
- **Estados**: `abierta` → `cerrada` (cuenta en reportes) → se puede
  `reabrir` con motivo. `anulada` con motivo, desde cualquier estado; no se
  borra nada. Reabrir y anular dejan un sello en las notas del lote.
- **Unicidad de lote** por producto entre lotes vivos (no anulados), validada
  en el servicio: un lote anulado por error de tecleo se puede volver a
  registrar con el mismo número.
- **Permisos configurables**: recurso `produccion` en admin → roles.
  Defaults: super_admin todo; supervisor leer/crear/editar; vendedor
  leer/crear. `leer` abre las pantallas, `crear` registra, `editar` corrige,
  cierra y reabre, `eliminar` anula. El menú muestra «Producción» a quien
  puede leer.
- **Código correlativo** `PR-AAAA-NNNN`, mismo criterio que maquila.

## Pantallas

| Ruta | Qué hace |
|------|----------|
| `/produccion` | Resumen: KPI de 30 días (producido, rendimiento, merma, sin identificar, lotes con merma alta), lotes abiertos, últimos cerrados |
| `/produccion/lotes` | Listado con filtros (producto, estado, fechas) |
| `/produccion/lotes/nuevo` · `/<id>/editar` | Un formulario: cabecera, producto terminado, insumos usados (teórico en vivo desde la fórmula), mermas por causa, vista previa del balance en el pie. «Guardar» o «Guardar y cerrar» |
| `/produccion/lotes/<id>` | Detalle: balance (rendimiento en grande), cajas pesadas por pedido, consumo con varianzas, mermas con «sin identificar», acciones (cerrar, reabrir, anular) |
| `/pedidos/<id>/pesar` | (pantalla existente) desplegable «Lote de producción» por producto; `registrar_caja_pesada` acepta `lote_produccion_id` y vincula la caja |
| `/produccion/reportes/rendimiento` (+ `/export`) | Por producto (ponderado por kilos, mín–máx) y por lote, con Excel de tres hojas |
| `/produccion/reportes/mermas` | Por causa (todas, también las que suman 0) y por producto |
| `/produccion/insumos` | Catálogo de insumos propios (alta y activar/desactivar) |
| `/produccion/formulas` · `/nueva` · `/<id>` | Fórmulas por producto: base en kg e insumos con cantidad |

## Despliegue

Las tablas se crean solas al arrancar si faltan (`produccion.asegurar_tablas`,
mismo criterio que `_ensure_haccp_columns`). El script
Si encuentra `lote_produccion.peso_producido` (versión 2026-10-03 AM), la
renombra a `peso_adicional` conservando el valor. Si encuentra las tablas
de lotes de la primera versión (atadas a
`ingrediente`/`receta` de maquila, reconocibles porque `lote_consumo` no
tiene `insumo_id`), las **tira y recrea** con el catálogo propio; los lotes
de prueba de esa versión se pierden. `scripts/produccion_migracion.sql` hace
lo mismo a mano. Después del deploy:

1. En admin → roles, revisar la columna «Producción» para supervisor y vendedor.
2. Cargar insumos y fórmulas en `/produccion/insumos` y `/produccion/formulas`.

## Tests

`tests/test_produccion.py`: tablas (y que se crean solas), independencia de
maquila, permisos, catálogo (insumos y fórmulas por servicio y por ruta),
servicios (alta sin recepciones,
códigos, balance, teórico como snapshot, unicidad, validaciones, cerrar,
reabrir, anular), reportes (ponderación, filtros, mermas por causa) y rutas
(alta por formulario con coma decimal, rechazo que conserva lo tecleado,
guardar y cerrar, Excel).
