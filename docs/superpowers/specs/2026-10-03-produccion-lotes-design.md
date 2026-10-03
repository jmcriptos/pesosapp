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
- **Se reusan `Ingrediente` y `Receta` de maquila.** Es el mismo catálogo
  físico y la misma fórmula. Para producción propia aplica la receta
  **genérica** del producto (la que no tiene cliente). Las recetas y los
  ingredientes se administran en `/maquila/recetas` y `/maquila/ingredientes`
  (solo super_admin); el nav de producción enlaza allá.
- **Tres tablas nuevas**: `lote_produccion`, `lote_consumo`, `lote_merma`.
  Nada de maquila se modifica.
- **Ningún total se guarda.** `peso_producido` es un dato (lo que marcó la
  balanza); merma, rendimiento y «sin identificar» se derivan en cada
  lectura (`servicios.balance`). El teórico por ingrediente sí es un
  snapshot al guardar, para que cambiar la receta mañana no reescriba el
  rendimiento de ayer.
- **Balance en kilos.** Solo los ingredientes con unidad `kg` entran en el
  consumido. La tripa (`ud`) se registra y se compara contra su teórico,
  pero no suma kilos (misma regla que maquila).
- **Merma identificada vs. sin identificar.** Las mermas se anotan por
  causa (cocción y ahumado, recorte, descarte, pérdida en proceso,
  muestras, otra). `merma_total = consumido − producido`;
  `sin_identificar = merma_total − identificada`. La cifra sin identificar
  es un dato, no un error: cerrar no la exige.
- **Merma negativa se muestra.** Si el producto pesa más que lo que entró
  (salmuera o agua no declarada como ingrediente), el rendimiento sale
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
| `/produccion/lotes/nuevo` · `/<id>/editar` | Un formulario: cabecera, producto terminado, ingredientes usados (teórico en vivo desde la receta), mermas por causa, vista previa del balance. «Guardar» o «Guardar y cerrar» |
| `/produccion/lotes/<id>` | Detalle: balance (rendimiento en grande), consumo con varianzas, mermas con «sin identificar», acciones (cerrar, reabrir, anular) |
| `/produccion/reportes/rendimiento` (+ `/export`) | Por producto (ponderado por kilos, mín–máx) y por lote, con Excel de tres hojas |
| `/produccion/reportes/mermas` | Por causa (todas, también las que suman 0) y por producto |

## Despliegue

1. `heroku pg:psql --app pesosapp -f scripts/produccion_migracion.sql`
2. push y `heroku restart --app pesosapp`
3. En admin → roles, revisar la columna «Producción» para supervisor y vendedor.

## Tests

`tests/test_produccion.py`: tablas, permisos, servicios (alta sin recepciones,
códigos, balance, teórico como snapshot, unicidad, validaciones, cerrar,
reabrir, anular), reportes (ponderación, filtros, mermas por causa) y rutas
(alta por formulario con coma decimal, rechazo que conserva lo tecleado,
guardar y cerrar, Excel).
