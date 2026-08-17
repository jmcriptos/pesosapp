# Cantidades fraccionarias de caja en pedidos

**Fecha:** 2026-08-17 · **Estado:** aprobado para implementación (sesión autónoma; JM revisa en el PR)

## Problema

Clientes piden fracciones de caja (media caja de atún Van Camps 160g, media de
cooked shoulder 500g). El formulario de pedidos rechaza cantidades < 1: el
input es entero (`parseInt`, `min="1"`), el servidor valida con `int()` en
`_extraer_lineas_pedido_form`, y las columnas `DetallePedido.cajas` y
`cajas_pedidas` son `db.Integer`.

## Decisiones

- **Granularidad: múltiplos de 0.25, mínimo 0.25, máximo 9999.** Cubre media
  caja (0.5) y cuarto (0.25); rechaza typos como `0.3`. Al ser 0.25 = 2⁻²,
  todos los valores y sus sumas son exactos en float — sin ruido decimal en
  subtotales ni deltas del form.
- **Aplica a todos los productos.** Sin flag por producto (YAGNI). Vale tanto
  para importados como para pesables.
- **Tipo de dato: `db.Float`** en `cajas` y `cajas_pedidas`. Sin unidades
  sintéticas (cuartos como enteros) ni SKUs "media caja" — invasivos o
  inmantenibles.
- **Pesaje: el objetivo de cajas físicas se redondea hacia arriba.**
  `cajas_objetivo` pasa de `int(...)` a `ceil(...)`: pedir 0.5 exige pesar 1
  caja (la media caja física); 2.5 exige 3. La factura de pesables sale del
  peso real, así que el monto siempre es correcto.
- **Factura QBO: sin cambios.** `pedido_a_json` ya emite `qty` como float y
  QuickBooks acepta cantidades decimales.
- **Precarga habitual:** la mediana se calcula sobre las cantidades reales
  (float), con `_mediana_cajas`: si todas las visitas son enteras se comporta
  exactamente como hoy (`_mediana_int`); si hay fracciones, redondea la
  mediana al 0.25 más cercano. Un cliente que siempre pide 0.5 precarga 0.5,
  y ningún cliente actual cambia de sugerencia. `_mediana_int` sigue para
  `cadencia_dias`.
- **Display:** filtro Jinja `fmt_cajas` (3 → "3", 0.5 → "0.5", 3.0 → "3")
  para que las columnas Float no rendericen "3.0 cajas" en templates. En JS
  no hace falta: `Number` ya imprime limpio.

## Cambios por capa

**Modelo (app.py)**
- `cajas`, `cajas_pedidas` → `db.Float`.
- `cajas_objetivo` → `ceil`. Consumidores (pesar UI, "faltan N cajas",
  totales de pesaje) siguen recibiendo enteros.

**Parseo/validación (app.py)**
- Helper `_parse_cajas(raw)`: float, en [0.25, 9999], múltiplo de 0.25;
  `ValueError` si no.
- `_extraer_lineas_pedido_form` lo usa (mensajes de error existentes + uno
  nuevo para "múltiplo de 0.25").
- `agregar_detalle` y `actualizar_detalle` (el modal manda cajas en el campo
  `peso` para importados): `int(peso)` → `_parse_cajas`, con flash y redirect
  en error (hoy `int("0.5")` lanzaría ValueError → 500, y `int(0.5)` truncaba
  a 0).

**Precarga habitual (app.py)**
- Acumular `det.cajas_pedidas or det.cajas` (float) en vez de
  `cajas_objetivo`; mediana con `_mediana_cajas`.

**Display (app.py + templates)**
- Filtro `fmt_cajas`; aplicar en `_detail_productos_card.html` (34, 80),
  `_detail_hero.html` (49), `dashboard.html` (295), `admin/reportes.html`
  (55). `_detalle_legacy_to_label_item` deja de truncar con `int()`.

**Formulario de pedido (pedido_form.html)**
- Input: `min="0.25" step="0.25" inputmode="decimal"`, `parseInt` →
  `parseFloat` + validación múltiplo de 0.25 con mensaje claro.
- Stepper se mantiene en ±1 caja (0.5 + 1 = 1.5; bajar de 0.25 quita la
  línea, regla actual de ≤ 0).

**Modal de detalles (detalles_pedido.html)**
- `inputMode` 'numeric' → 'decimal' y placeholder "0" → "0.00" en los dos
  puntos que configuran el campo Cajas (modal de edición y form de agregar).

**Migración**
- Alembic version file para el repo.
- Prod (manual, como siempre):
  `heroku pg:psql --app pesosapp -c "ALTER TABLE detalle_pedido ALTER COLUMN cajas TYPE double precision, ALTER COLUMN cajas_pedidas TYPE double precision;"`
  y `heroku restart --app pesosapp`. SQLite local no necesita nada (afinidad
  dinámica).

## Fuera de alcance

- Fracciones en el flujo de pesaje por caja física (CajaPesada no cambia).
- Flag por producto para permitir/prohibir fracciones.
- Remediación de datos históricos (no hay: los enteros existentes son floats
  válidos).

## Testing

TDD con `tests/test_cajas_fraccionarias.py`: parseo (acepta 0.5/0.25/1.75,
rechaza 0.3/0/-1/abc/>9999), crear y editar pedido con 0.5 (línea original +
prep de importado + total), `cajas_objetivo` ceil, `pedido_a_json` con qty
0.5, `_mediana_cajas` (enteros idéntico a hoy; fracciones al cuarto),
`fmt_cajas`, y el modal (`actualizar_detalle`) con "0.5". Suite completa
además, por las regresiones de markup conocidas.
