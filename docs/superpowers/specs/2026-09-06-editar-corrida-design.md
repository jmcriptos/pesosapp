# Editar corridas de producción

Fecha: 2026-09-06. Aprobado por JM en chat. Rama `claude/maquila-fullscreen-e63552`.

## Qué se puede corregir

| Sección   | Abierta                                   | Cerrada                                                                 |
|-----------|-------------------------------------------|-------------------------------------------------------------------------|
| Cabecera  | cliente, producto, receta, lote, fechas, notas | receta, lote, fechas, notas. Cliente y producto fijos (ya se descontó de ese cliente; las cajas son de ese producto). Lote y fechas bloqueados si alguna caja salió en un pedido **facturado**; si salieron a pedidos no facturados, se propagan a `CajaPesada`. |
| Cajas     | peso y quitar (anular con motivo)         | igual, pero solo cajas **disponibles** (sin `caja_pesada_id`, no anuladas) |
| Consumo   | no aplica (se declara al cerrar)          | por diferencia, ver abajo. Motivo y firma obligatorios.                 |

Anuladas: no editables (`CorridaNoEditable`).

## Consumo por diferencia

Para cada ingrediente, `delta = nuevo − viejo`:

- `delta > 0`: `repartir_fifo` por el delta → nuevos `CorridaConsumoOrigen`
  (o se suma al origen existente de la misma línea) + `salida` en el ledger.
- `delta < 0`: se devuelve `|delta|` recorriendo los orígenes en orden inverso
  (LIFO), bajando `origen.cantidad` y escribiendo `ajuste` positivo anclado a la
  misma `recepcion_linea_id`. Un origen que llega a cero se borra (no es ledger).
- Ingrediente quitado = delta hasta cero (se borra el `CorridaConsumo` al quedar en 0).
- Ingrediente nuevo = delta desde cero (se crea `CorridaConsumo`).
- `cantidad_teorica` se recalcula contra el peso producido actual, con la receta actual.

Identidad que se preserva: `saldo_de_linea = peso_total − Σ salidas + Σ ajustes`.
Ledger append-only: cero UPDATE/DELETE sobre `movimiento_ingrediente`.

## Guardas (todas antes de la primera escritura)

1. Corrida anulada → `CorridaNoEditable`.
2. Cerrada + cambia cliente o producto → `CorreccionImposible`.
3. Cerrada + cambia lote/fechas + alguna caja en pedido facturado → `CorridaFacturada`.
4. Caja no disponible (asignada o anulada) editada o quitada → `CorreccionImposible`.
5. Caja con peso ≤ 0 → `CorridaInvalida`.
6. Consumo con cantidad < 0 → `CorridaInvalida`; delta > 0 sin saldo → `SaldoInsuficiente`.
7. Cambia el consumo (algún delta ≠ 0) y falta motivo → `MotivoRequerido`; falta firma → `FirmaRequerida`.
8. Quitar una caja exige motivo (queda en `motivo_anulacion`).

## Dónde queda el rastro

- Movimientos: `motivo='Corrección de P-…: <ingrediente> viejo → nuevo. <motivo>'`.
- `corrida.notas` recibe al pie `Corregida: <motivo>` cuando hubo motivo.
- La firma de corrección reemplaza `firma_cierre`.
- Cajas quitadas: `anulada_en` + `motivo_anulacion`.

Sin cambios de esquema.

## Código

- `maquila/servicios.py`: `editar_corrida(corrida, *, vendedor_id, cabecera, cajas, consumos=None, motivo=None, firma=None, firma_mimetype=None)`, contrato try/commit/rollback.
- `maquila/routes.py`: `GET/POST /maquila/corridas/<id>/editar`, super_admin, re-pinta con `request.form` al rechazar.
- `templates/maquila/corrida_editar.html` + enlace «Corregir» en `corrida_detalle.html`.
- `tests/test_maquila_editar_corrida.py`.
