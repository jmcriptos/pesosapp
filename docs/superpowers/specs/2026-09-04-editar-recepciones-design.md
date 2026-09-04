# Editar recepciones de ingredientes

**Fecha:** 2026-09-04
**Estado:** diseño aprobado, pendiente de plan de implementación
**Módulo:** maquila — ver `docs/superpowers/specs/2026-09-03-maquila-ingredientes-design.md`

## Problema

Una recepción se registra en planta, de pie, con guantes, con el camión esperando.
Los errores de tipeo son normales. Hoy no hay forma de corregirlos: lo único que
el módulo permite es **anular** la recepción entera, y solo mientras ninguna de
sus líneas se haya consumido. En cuanto una corrida tomó material de esa
recepción, el dato queda congelado con el error adentro.

Esto tiene que servir también para el caso difícil: corregir una cantidad que
**ya alimentó una corrida de producción**, quizá facturada.

## El hecho que decide el diseño

Medido sobre datos reales antes de diseñar nada:

```
Línea 1 | peso registrado: 67.300 | saldo actual: 3.200
  ya consumido por corridas: 64.100
```

**`saldo_de_linea` sale del ledger, no de `peso_total`.** Editar el peso sin
tocar el ledger haría que la pantalla dijera 90 mientras el saldo se sigue
calculando sobre 100: el número que se ve y el que manda dejarían de coincidir.

Corolario que también se verificó: **la merma NO cambia.** Sale de
`CorridaConsumo.cantidad_real`, no de la recepción. Ningún rendimiento que ya se
le mostró al cliente se mueve solo al corregir una recepción. Ese era el riesgo
que parecía mayor y no aplica.

## Decisiones tomadas

| Decisión | Elegido | Descartado y por qué |
|---|---|---|
| Alcance | Cantidades ya consumidas incluidas | Limitarlo a lo intacto dejaba sin resolver el caso que motivó el pedido |
| Mecánica | `peso_total` se corrige **y** se escribe un ajuste por la diferencia | Mutar sin tocar el ledger desincroniza pantalla y saldo (medido arriba) |
| Qué se ve | El número corregido, limpio. El rastro **solo en el kardex** | Mostrar «corregido de 100» en el detalle: JM prefirió la pantalla limpia |
| Qué se puede editar | Todo: cantidades, bultos, cabecera, líneas (agregar/quitar), fotos, firma | — |
| Pantalla | Una sola, espejo de la de captura | Formularios sueltos por sección: más rutas, más caminos de error |
| Acceso | `@requiere_rol(['super_admin'])` | — |

## Mecánica de la corrección

Al corregir la cantidad de una línea de 100 a 90:

1. `recepcion_linea.peso_total` pasa a 90 — es el número que muestra la pantalla.
2. Se escribe **un** `MovimientoIngrediente` de tipo `ajuste`, cantidad `-10`,
   `origen_tipo='recepcion'`, `origen_id` de la recepción, `recepcion_linea_id`
   de la línea, con el motivo que dio el usuario.

Con eso se preserva la identidad de la que cuelga el FIFO:

```
peso_total − consumido == saldo_de_linea
```

El ledger sigue siendo append-only: no se edita ni se borra ningún movimiento
anterior. La entrada original de 100 kg queda para siempre; el ajuste la corrige.

**El motivo es obligatorio cuando cambia una cantidad**, y no lo valida esta
funcionalidad: `registrar_movimiento` ya rechaza un `ajuste` sin motivo con
`MotivoRequerido`. Para cabecera, fotos y firma no se pide, porque no hay nada
que justificar.

### Solo se escribe lo que cambió

El guardado compara valores anteriores y nuevos, y **escribe movimiento
únicamente para las líneas cuya cantidad efectivamente cambió**.

No es una optimización. Sin esto, cada guardado dejaría un ajuste de cero por
línea, y el kardex —el único de los cuatro reportes que hoy le sirve a un
auditor— se volvería ilegible en un mes de uso.

## Guardas

Las tres bloquean con un mensaje que nombra el problema; ninguna corrige por su
cuenta.

1. **No se puede corregir una línea por debajo de lo ya consumido.** Bajar a 59
   cuando ya salieron 64,1 dejaría el saldo en −5: no es un error de tipeo, es un
   dato imposible. Es la misma regla que el módulo ya aplica al cerrar corridas.
2. **No se puede quitar una línea que ya alimentó una corrida.** Esa carne está
   en un producto terminado, quizá facturado. Se corrige su cantidad; no se
   borra.
3. **No se puede cambiar el cliente si alguna línea ya se consumió.** Una
   recepción cargada al cliente equivocado se corrige mientras está intacta;
   después no, porque la corrida que consumió de ella pertenece al cliente
   original y cambiarlo movería carne de un cliente a otro — exactamente la
   corrupción del rastro que el módulo existe para impedir, y la misma que
   `asignar_detalle` ya bloquea del lado de las cajas.
4. **No se puede editar una recepción anulada.**

Además se reusa la validación que ya tiene el alta: **una cantidad corregida
tiene que ser positiva**, y cada bulto individual también (`RecepcionInvalida`).
Corregir a cero no es corregir: es quitar la línea, y para eso está su propia
acción con su propia guarda.

## Quitar una línea no la borra

Se le escribe el movimiento inverso por su saldo y se marca como anulada. El
módulo no borra nada, nunca: borrar la fila además dejaría huérfanos los
`movimiento_ingrediente` que la referencian.

**Cambio de esquema:** una columna nueva, `recepcion_linea.anulada_en`
(`DateTime`, nullable), siguiendo el patrón que ya tienen
`recepcion_ingrediente.anulada_en` y `corrida_caja.anulada_en`. Es el único
cambio de esquema de este trabajo.

Una línea anulada desaparece de la pantalla de la recepción y del cálculo de
totales, pero sigue existiendo en el kardex y en la trazabilidad.

## La pantalla

`GET/POST /maquila/recepciones/<id>/editar`, con las mismas cuatro secciones que
la de captura para que nadie tenga que aprender otra cosa. El botón vive en el
detalle de la recepción, que hoy es un callejón sin salida: lo único que se puede
hacer ahí es anular.

- **Cabecera** precargada y editable directo: cliente (con la guarda de arriba),
  fecha, documento, temperatura, transportista, notas.

  Ojo con la fecha: **el FIFO ordena por `recibido_en`**, así que corregirla
  cambia contra qué línea consumirán las corridas **futuras**. Es el
  comportamiento correcto —si la fecha estaba mal, el orden también lo estaba—
  y no reescribe nada del pasado: los repartos ya hechos viven en
  `corrida_consumo_origen` y no se tocan. Se documenta acá para que nadie lo
  reporte como bug.
- **Líneas**, cada una con sus valores actuales. Si tiene bultos, se editan los
  bultos y el total se recalcula como su suma; si vino a granel, se edita el
  total. Cada línea con su «quitar», y abajo el «agregar ingrediente».
- **Fotos** existentes en miniatura, cada una con su borrar, más el input para
  sumar otras. Se reducen en el navegador antes de subir, igual que en la
  captura.
- **Firma**: se muestra la que hay, con un «volver a firmar» que revela el
  canvas.

**Un solo POST, una sola transacción**, con la misma autoprotección que las
cuatro funciones «todo o nada» del módulo: `try / commit / except Exception:
rollback; raise`. Si algo falla, no queda media edición.

## Servicios

En `maquila/servicios.py`, siguiendo las convenciones del módulo:

- `editar_recepcion(recepcion, *, vendedor_id, cabecera, lineas, motivo=None,
  fotos_nuevas=None, fotos_a_borrar=None, firma=None) -> RecepcionIngrediente`
  Hace commit. Calcula deltas, escribe solo los ajustes necesarios, aplica las
  guardas antes de escribir nada.
- `class RecepcionNoEditable(Exception)` — recepción anulada.
- `class CorreccionImposible(ValueError)` — corregir por debajo de lo consumido,
  o quitar una línea consumida. El mensaje nombra la línea, lo consumido y lo
  que se pidió.

`saldo_de_linea`, `registrar_movimiento` y `MotivoRequerido` ya existen y se
reusan tal cual.

## Pruebas

En `tests/test_maquila_editar_recepcion.py`. El grueso va sobre los servicios,
que es donde vive el riesgo:

- Corregir una cantidad escribe **exactamente un** movimiento por la diferencia.
- Tras corregir se mantiene `peso_total − consumido == saldo_de_linea`.
- Editar **solo la cabecera** no escribe ningún movimiento.
- Guardar sin cambiar nada no escribe ningún movimiento.
- Corregir por debajo de lo consumido se rechaza y no escribe nada.
- Quitar una línea consumida se rechaza; quitar una intacta escribe su inverso y
  la marca anulada.
- Corregir una cantidad sin motivo se rechaza con `MotivoRequerido`.
- Editar una recepción anulada se rechaza.
- El FIFO sigue repartiendo correctamente contra una línea corregida.
- Agregar una línea escribe su entrada.
- La corrección aparece en el kardex con su motivo y su responsable.
- Cambiar el cliente de una recepción con material consumido se rechaza; con
  todo intacto, se acepta.
- Corregir una cantidad a cero o a un valor negativo se rechaza.
- Corregir `recibido_en` cambia el orden del FIFO siguiente y no altera ningún
  `corrida_consumo_origen` ya escrito.

## Migración

Un solo `ALTER TABLE`:

```sql
ALTER TABLE recepcion_linea ADD COLUMN anulada_en TIMESTAMP;
```

Va **a mano y antes del push**, como todo en este proyecto: no hay release phase
y `alembic_version` está desacoplado en producción. Es aditivo y nullable, así
que no toca ninguna fila existente.

## Trampas conocidas del módulo que aplican acá

- **Nunca `from app import X`** dentro de `maquila/`: se resuelve por
  `sys.modules` desde `maquila/__init__.py`, o `python app.py` revienta.
- **Nada de `type=int` dentro de una plantilla Jinja.** No tiene los builtins de
  Python; `int` ahí es `Undefined` y werkzeug revienta al llamarlo — pero solo
  cuando el parámetro viene en la query, que es lo que hizo que este bug llegara
  a producción sin que ningún test lo viera.
- **Cantidades con `|fmt_cant(unidad)`**, nunca `Decimal` crudo, y la unidad
  nunca se asume.
- **`data-confirm` va en el `<form>`**, no en el botón, salvo formularios con
  varios submits.
- **Todo `<script>` inline con `nonce="{{ csp_nonce() }}"`.**
- **Cada `<td>` con su `data-label`**, o la ficha de móvil sale sin etiquetas.
- **La firma con color fijo** (`#0f172a`), nunca leído de `document.body`.
- **Todo selector CSS nuevo prefijado con `.maquila-wrap`.**
