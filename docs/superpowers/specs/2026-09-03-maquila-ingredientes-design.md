# Módulo de maquila: recepción de ingredientes y trazabilidad hasta la factura

**Fecha:** 2026-09-03
**Estado:** diseño aprobado, pendiente de plan de implementación

## Problema

Jomar presta servicio de transformación a un cliente: el cliente suministra la
carne, Jomar la convierte en embutidos y se la devuelve, cobrando una tarifa por
kilo terminado. Hoy la app no tiene dónde registrar esos ingredientes. No se sabe
cuánto material del cliente hay en planta, ni qué recepción se convirtió en qué
producto, ni cómo justificar ante un auditor el camino de un kilo desde que entró
por la puerta hasta que salió en una factura.

El modelo `Recepcion` que ya existe en `app.py` no sirve: registra compras a un
*proveedor* contra una factura de compra, para inventario propio. No tiene cliente,
ni lote, ni vínculo con pedido. Queda intacto; este módulo no lo toca.

## Qué se construye

Un módulo que cierra esta cadena completa:

```
recepcion_linea → corrida_consumo_origen → corrida_produccion (lote)
              → corrida_caja → caja_pesada → detalle_pedido → pedido → doc_number_qbo
```

Es decir: dado un kilo entregado y facturado, se puede retroceder hasta la
entrega concreta del cliente de la que salió; y dada una entrega del cliente,
se puede avanzar hasta las facturas en las que terminó.

## Decisiones tomadas

| Decisión | Elegido | Descartado y por qué |
|---|---|---|
| Granularidad del rastro | Recepción → producción → pedido (3 pasos) | Un saldo simple no permite decir qué entrega produjo qué |
| Catálogo de ingredientes | Tabla propia `ingrediente` | Reusar `Producto` con un flag mete insumos en listas de precios y en QuickBooks el día que alguien olvide un filtro |
| Ingredientes en QBO | **No pasan por QBO nunca.** El terminado sí, como `Producto` normal | — |
| Entrega del terminado | El flujo de Pedido existente, sin cambios en facturación | — |
| Consumo de ingredientes | Receta que propone el consumo teórico, ajustable a lo real | Declarar a mano sin receta no da varianza |
| Origen del consumo | FIFO automático contra recepciones, editable | Selección manual: es el paso que se salta cuando hay prisa |
| Pesaje de las cajas | **En la corrida de producción**, no en el pedido | — |
| Asignación de cajas al pedido | FEFO automático, editable | — |
| Faltante de producción | Se completa pesando a mano como hoy; esas cajas quedan sin origen y el reporte las marca | Bloquear frena despachos parciales que el cliente acepta |
| Acceso | `@requiere_rol(['super_admin'])` | — |
| Ubicación del código | Paquete `maquila/` con Blueprint | `app.py` ya tiene 13.857 líneas |

## Modelo de datos

Doce tablas nuevas. El eje es el **ledger**: nada modifica un saldo salvo
escribiendo un movimiento, y los movimientos no se editan ni se borran jamás.

### Catálogo

**`ingrediente`**
- `id`, `nombre` (String 120, único), `unidad` (String 10, default `'kg'`), `activo` (Boolean), `notas`

Catálogo compartido entre clientes. La propiedad del material la expresa el
ledger (que lleva `cliente_id`), no el catálogo. Sin `qbo_id`, sin `tax_rate`,
sin precio: un ingrediente no puede llegar a una factura porque `pedido_a_json`
solo sabe leer `Producto`.

### Recepción

**`recepcion_ingrediente`** (cabecera)
- `codigo` String(20) único indexado — `R-2026-0042`, generado por la app
- `cliente_id` FK → `cliente`
- `recibido_en` Date
- `documento_cliente` String(100) **nullable** — a veces el cliente no manda nada
- `temperatura` Numeric(5,2) nullable — control HACCP al recibir
- `transportista` String(120) nullable
- `firma` LargeBinary nullable + `firma_mimetype` String(50)
- `notas` Text nullable
- `registrado_por` FK → `vendedor`, `registrado_en` DateTime (UTC naive)
- `anulada_en` DateTime nullable, `anulada_por` FK nullable, `motivo_anulacion` Text nullable

La firma va como bytes en la base, no como archivo: Heroku borra el disco en cada
reinicio (mismo motivo que `Cliente.logo_etiqueta`).

**`recepcion_linea`**
- `recepcion_id` FK CASCADE indexado, `ingrediente_id` FK
- `lote_cliente` String(50) **nullable**, `fecha_vencimiento` Date **nullable**
- `peso_total` Numeric(10,3)

**Esta línea es la unidad de trazabilidad hacia atrás.** El código interno de su
recepción hace de lote de origen cuando el cliente no declara ninguno, que es el
caso frecuente.

**`recepcion_bulto`**
- `recepcion_linea_id` FK CASCADE indexado, `numero` Integer, `peso` Numeric(8,3)
- `UniqueConstraint(recepcion_linea_id, numero)`

Espejo de `CajaPesada`. Cuando hay bultos, `recepcion_linea.peso_total` se
recalcula como su suma. Cuando el material llega a granel, se captura el total
directo y no hay bultos.

**`recepcion_foto`**
- `recepcion_id` FK CASCADE indexado, `imagen` LargeBinary, `mimetype` String(50), `subida_en` DateTime

Las imágenes se reducen en el navegador antes de subir. Cuatro fotos de iPhone en
crudo por recepción hinchan la fila y la memoria del dyno.

### Receta

**`receta`**
- `producto_id` FK → `producto` (el terminado), `cliente_id` FK nullable
- `nombre` String(120), `base_kg` Numeric(10,3) default 100
- `activa` Boolean, `creada_en`, `creada_por`

**`receta_ingrediente`**
- `receta_id` FK CASCADE, `ingrediente_id` FK, `cantidad` Numeric(10,3)
- `UniqueConstraint(receta_id, ingrediente_id)`

Consumo teórico = `cantidad × kg_producidos / base_kg`.

Al abrir una corrida se autoselecciona la receta activa **del cliente** para ese
producto; si no existe, la activa genérica (`cliente_id IS NULL`). Si hay varias
activas para la misma combinación, se rechaza al guardar la receta, no al usarla.

### Producción

**`corrida_produccion`**
- `codigo` String(20) único indexado — `P-2026-0031`
- `cliente_id` FK indexado, `producto_id` FK (el terminado), `receta_id` FK nullable
- `lote` String(50) indexado — el que se estampa en las cajas
- `fecha_produccion` Date, `fecha_vencimiento` Date nullable
- `estado` String(20) — `abierta` | `cerrada` | `anulada`
- `registrado_por`, `registrado_en`, `cerrada_por`, `cerrada_en`, `notas`
- `UniqueConstraint(cliente_id, lote)`

`peso_producido` **no se guarda**: es la suma de `corrida_caja`.

**`corrida_caja`**
- `corrida_id` FK CASCADE indexado, `numero` Integer, `peso` Numeric(8,3)
- `caja_pesada_id` FK → `caja_pesada` **nullable, único, `ON DELETE SET NULL`**
- `anulada_en` DateTime nullable, `motivo_anulacion` Text nullable
- `UniqueConstraint(corrida_id, numero)`

**Una caja está disponible si `caja_pesada_id IS NULL AND anulada_en IS NULL`.**
El estado se deriva, no se guarda. Si alguien borra la línea del pedido, el
`ON DELETE SET NULL` devuelve la caja al stock sin que ningún código tenga que
acordarse; el índice único garantiza que no pueda estar en dos pedidos. (Postgres y SQLite
admiten varios `NULL` en una columna única, que es exactamente lo que hace falta:
muchas cajas disponibles a la vez, una sola asignada a cada `CajaPesada`.)

**`corrida_consumo`**
- `corrida_id` FK CASCADE indexado, `ingrediente_id` FK
- `cantidad_teorica` Numeric(10,3) — **snapshot** de la receta al cerrar
- `cantidad_real` Numeric(10,3)
- `UniqueConstraint(corrida_id, ingrediente_id)`

El snapshot es lo que hace que editar una receta hoy no cambie la varianza de un
reporte del mes pasado.

**`corrida_consumo_origen`** (el reparto FIFO)
- `corrida_consumo_id` FK CASCADE indexado, `recepcion_linea_id` FK indexado
- `cantidad` Numeric(10,3), `automatico` Boolean default True

Invariante: `SUM(cantidad)` por consumo == `corrida_consumo.cantidad_real`.

### Ledger

**`movimiento_ingrediente`**
- `cliente_id` FK indexado, `ingrediente_id` FK indexado
- `recepcion_linea_id` FK nullable indexado
- `tipo` String(20) — `entrada` | `salida` | `ajuste` | `devolucion`
- `cantidad` Numeric(10,3) **con signo** (+ entrada, − salida)
- `origen_tipo` String(20) — `recepcion` | `corrida` | `manual`
- `origen_id` Integer nullable
- `motivo` Text nullable — **obligatorio** para `ajuste` y `devolucion`
- `registrado_por` FK, `registrado_en` DateTime
- Índice compuesto `(cliente_id, ingrediente_id, registrado_en)`

Saldo del cliente = `SUM(cantidad)`. Saldo de una línea de recepción = la misma
suma filtrada por `recepcion_linea_id`, que es justo lo que FIFO necesita.

### Cambio a tabla existente

Ninguno. El vínculo `corrida_caja.caja_pesada_id` evita añadir columnas a
`caja_pesada`, y una caja pesada sin `corrida_caja` que la apunte es,
correctamente, una caja sin origen de producción.

## Flujos y pantallas

Todo bajo `/maquila` con `@requiere_rol(['super_admin'])`. Patrón visual `.ops-*`
de Temperaturas/Limpieza: mobile-first, sheets a pantalla completa, teclado
numérico para pesos. Aunque solo entre admin, se opera de pie en planta con un
iPhone.

### `/maquila` — índice

Una tarjeta por cliente con maquila activa: saldo total de ingredientes, corridas
abiertas, cajas producidas sin entregar, última recepción.

**"Cliente de maquila" no es un campo nuevo en `Cliente`**: es todo cliente que
tenga al menos una recepción no anulada. Se deriva, para no añadir un flag que
alguien tenga que acordarse de marcar.

### `/maquila/recepciones/nueva`

Tres pasos en una pantalla:

1. **Cabecera** — cliente, fecha, documento del cliente (vacío es válido y no
   dispara ningún aviso), temperatura, transportista.
2. **Líneas** — por ingrediente: lote del cliente y vencimiento, ambos opcionales;
   luego los bultos, pesados con teclado numérico y sumados en vivo. También se
   admite un peso total sin desglose.
3. **Evidencia** — fotos (`capture` de cámara, redimensionadas en el navegador) y
   firma de quien entrega en canvas.

Un solo POST, una sola transacción: genera el `codigo`, escribe cabecera + líneas
+ bultos y **un movimiento `entrada` por línea**.

### `/maquila/corridas/<id>` — cierre de corrida

- Se abre con cliente, producto terminado, receta (se autoselecciona la activa),
  lote, fecha de producción y vencimiento.
- Se pesan las cajas producidas una a una (`corrida_caja`), con el mismo teclado.
- Al cerrar, la app calcula el consumo teórico desde la receta y lo presenta como
  sugerencia **editable**; el operario lo corrige a lo real.
- **Antes de confirmar** se muestra el reparto FIFO resultante, editable.
  Enseñarlo después de guardar sería enseñarlo cuando ya no sirve.
- Al confirmar, en una transacción: snapshot de teóricas, `corrida_consumo_origen`
  por tramo, y un movimiento `salida` por tramo.

### Asignación de cajas al pedido

En la pantalla de preparación del pedido, para clientes con corridas: la app
propone las cajas disponibles de ese cliente y producto, **vencimiento más próximo
primero**, hasta cubrir `detalle.cajas_objetivo`. Se muestra el reparto y se puede
cambiar. Al confirmar, cada caja producida **crea una `CajaPesada`** copiando peso,
lote, fecha de elaboración y vencimiento, y se apunta a ella.

Si no alcanzan las cajas producidas, el resto se pesa a mano en `pesar` como con
cualquier otro cliente. Esas cajas quedan sin `corrida_caja` que las apunte y el
reporte de trazabilidad las marca como **sin origen** en vez de disimularlo.

Para clientes sin corridas, `pesar` se comporta exactamente como hoy.

### Resto

Catálogo de ingredientes (ABM), recetas con su editor, y listados de recepciones y
corridas con filtro por cliente y fecha.

**Fuera de alcance a propósito:** imprimir etiquetas de los bultos con el código
interno al recibirlos. El motor de etiquetas existe y engancharlo sería fácil, pero
no se pidió y el código cumple su función de trazabilidad viviendo en la base.

## Reportes de auditoría

1. **Saldo por cliente** — ingrediente × (recibido, consumido, ajustes, saldo), con
   detalle de las líneas de recepción que aún tienen saldo abierto.
2. **Kardex** — filtro por cliente, ingrediente y rango de fechas; movimientos en
   orden cronológico con responsable y origen enlazado. Export a XLSX.
3. **Rendimiento** — por corrida y agregado por período: kg consumidos, kg
   producidos, merma en kg y %, y varianza real contra teórica por ingrediente.
4. **Trazabilidad de lote** — buscador único que acepta un lote, un código de
   recepción, un número de pedido o un número de factura, y pinta la cadena en
   ambos sentidos hasta el `doc_number_qbo`.

## Reglas e invariantes

1. **El ledger no se edita ni se borra, nunca.** Ni un `UPDATE`. Toda corrección es
   un movimiento nuevo con motivo.
2. **Saldo insuficiente al cerrar una corrida: se bloquea**, nombrando el
   ingrediente y cuánto falta. La salida legítima es un ajuste de entrada con
   motivo. Un saldo negativo envenena todos los reportes hacia abajo y deja al FIFO
   sin ninguna recepción honesta de dónde tirar.
3. **Anular una recepción solo se permite si ninguna de sus líneas se consumió.**
   Si ya se consumió, la corrección es un ajuste. La anulación escribe movimientos
   inversos; no borra filas.
4. **Una corrida cerrada es inmutable.** Corregir = anular y crear otra. No se puede
   anular si alguna de sus cajas ya salió en un pedido facturado: a esa altura la
   cifra ya está en QuickBooks.
5. **Merma y rendimiento se derivan, no se guardan.** A la escala real de esta base
   (57 productos, 780 pedidos) calcularlos al vuelo es instantáneo, y un número
   guardado es un número que puede mentir.
6. **Fechas en UTC naive, convertidas a `America/Curacao`** para mostrar y para
   agrupar por día. Es el error que ya metió lecturas de temperatura en el bucket
   equivocado.
7. **Pesos en `Numeric`, no `Float`.** Los saldos se suman miles de veces y el error
   de coma flotante se acumula justo donde tiene que cuadrar.

## Organización del código

`app.py` tiene 13.857 líneas y el proyecto no usa Blueprints. Este módulo son doce
tablas, ~20 rutas y cuatro reportes. Va en un paquete propio:

```
maquila/
  __init__.py      # create_blueprint()
  models.py        # los doce modelos
  servicios.py     # ledger, FIFO, FEFO, saldos: funciones puras
  reportes.py      # las cuatro consultas
  routes.py        # el Blueprint
templates/maquila/
static/css/maquila.css
```

**Corrección al diseño original.** Había asumido que `db` vivía en `extensions.py`.
No es así: ese archivo es código muerto. `app.py:138` dice literalmente «Inicializar
SQLAlchemy directamente (sin models.extensions)» y hace `db = SQLAlchemy(app)`; nadie
importa `extensions`. `db` vive en `app.py` y no hay de dónde más sacarlo.

La salida es la convencional en Flask, y resulta **menos** invasiva que lo que había
propuesto: `maquila/` importa de `app` lo que necesita (`db`, `Cliente`, `Producto`,
`DetallePedido`, `CajaPesada`, `Vendedor`, `requiere_rol`), y `app.py` importa
`maquila` **al final del archivo**, cuando todo eso ya está definido. Python guarda el
módulo a medio inicializar en `sys.modules`, así que el ciclo se resuelve solo.

Consecuencias:

- **`requiere_rol` no se mueve a ningún lado.** `maquila/routes.py` lo importa de `app`
  como cualquier otra cosa. **Cero cambios a código existente.**
- El único cambio en `app.py` son **tres líneas al final**, justo antes del bloque
  `if __name__ == '__main__':`.
- `maquila/models.py` tiene que quedar importado sí o sí, o el `db.create_all()` de
  `tests/conftest.py` no ve las tablas nuevas y todos los tests del módulo fallan sin
  una explicación visible.

## Trampas conocidas de esta app

- **La firma se dibuja con color fijo**, nunca leído de `body`. Los tokens claros
  están scopeados a `.ops-*`, así que `getComputedStyle(document.body)` devuelve el
  token oscuro; eso ya produjo una firma blanca sobre blanco.
- **El botón de guardar va en footer `position:sticky`**, o queda debajo de la
  tabbar fija y no se puede pulsar.
- **Todo `<script>` inline lleva `nonce="{{ csp_nonce() }}"`** o no ejecuta: la CSP
  por nonces está activa en producción sin `'unsafe-inline'`.
- **Manejadores por `data-*`**, no inline, siguiendo las convenciones de `base.js`.
- **Si se toca `base.js`, hay que regenerar `base.min.js`** (`cp`, no hay minificador
  real en el repo). Este módulo no debería necesitarlo.

## Migraciones

`alembic_version` en producción está desacoplado y no hay release phase: los `ALTER`
y `CREATE` van a mano **antes** del push, o el dyno arranca dando 500. Se entrega un
guion SQL explícito con las doce tablas en orden de dependencia, para correr con
`heroku pg:psql --app pesosapp`, y `heroku restart` después.

Ninguna tabla existente cambia de esquema, así que el riesgo de la migración se
limita a crear tablas nuevas.

## Pruebas

TDD, con el grueso en `servicios.py`, que es puro y se prueba sin HTTP:

- Un movimiento de entrada sube el saldo; uno de salida lo baja.
- FIFO reparte contra la recepción más antigua y salta las agotadas.
- FIFO reparte entre varias recepciones cuando una no alcanza.
- Cerrar con saldo insuficiente falla y no escribe ningún movimiento.
- FEFO elige la caja de vencimiento más próximo.
- Borrar la línea de un pedido devuelve la caja producida al stock.
- Una caja producida no puede asignarse a dos pedidos.
- Anular una recepción consumida se rechaza; una intacta escribe los inversos.
- La cadena completa de trazabilidad devuelve el `doc_number_qbo`.

Cuidado con los tests existentes acoplados a markup HTML exacto: este módulo no
toca dashboard, pedidos ni detalles, así que no debería romperlos, pero
`test_pedido_dos_pasos.py` y los de etiquetas se corren igual antes de dar nada por
bueno.
