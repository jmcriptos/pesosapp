# Etiquetas por unidades y logo del cliente

**Fecha:** 2026-08-27
**Estado:** diseño aprobado, pendiente de implementación

## Problema

Dos necesidades independientes que caen sobre el mismo código de etiquetas:

1. **Productos vendidos por caja.** Se fabrican dos productos que se venden por
   caja, no por peso. Cada caja necesita su etiqueta identificándola por la
   cantidad de unidades que contiene, no por kilos. Hoy la etiqueta imprime
   siempre el rótulo `Net Weight:`, y para productos que no se pesan cae en un
   parche que produce `Net Weight: 3 uds` — una contradicción visible en la
   etiqueta impresa.
2. **Logo del cliente.** Se fabrican productos para DeliNova (QBO 1454) y sus
   etiquetas deben salir con el logo de DeliNova en lugar del de Jomar. No hay
   ningún mecanismo para asociar una imagen a un cliente, ni infraestructura de
   subida de archivos en la app.

## Decisiones tomadas

| Decisión | Elección | Motivo |
|---|---|---|
| Qué número va en la etiqueta de caja | Unidades por caja, fijo del producto | Toda caja del mismo producto lleva la misma cantidad; no hace falta capturarlo por caja |
| Cuántas etiquetas por pedido | Una por caja física | Cada caja se rotula individualmente |
| Logo de Jomar vs cliente | El del cliente reemplaza al de Jomar | Es producto de marca del cliente |
| Alcance del logo | Todas las etiquetas de ese cliente | Simple, sin decisión producto por producto |
| Dónde se guarda el logo | Bytes en la base de datos | Heroku borra el disco en cada reinicio; permite cargar logos sin deploy |
| Productos por caja sin unidades cargadas | Cambian a `Boxes: 3` | Coherencia: ningún producto por caja debe decir "Net Weight" |
| Pantalla de Facturación | También recibe el logo del cliente | Sigue en uso |
| Formatos afectados | 4x2 térmica y A4 | Se usan los dos |

## Dónde se imprimen etiquetas hoy

Tres puntos de entrada, con distinto alcance en este cambio:

1. **Desde el pedido** — `detalles_pedido` → tarjeta "Generar etiquetas".
   Rutas `generar_etiqueta_detalle` (4x2) y `generar_etiqueta_detalle_a4`.
   Conoce cliente, cajas, lote y fechas. **Recibe las dos funciones nuevas.**
2. **Desde Facturación** — ruta `generar_etiqueta` (`app.py:9996`), por cliente
   y rango de fechas, leyendo la tabla `Facturacion`. Dibuja la etiqueta con
   coordenadas escritas a mano, duplicando lo que hace `label_utils`.
   **Recibe el logo del cliente y se unifica con `label_utils`.**
3. **Etiquetas de vencimiento** — ruta `etiquetas_vencimiento`, formulario
   suelto sin cliente ni pedido. **Sin cambios**: mantiene el logo de Jomar.

## Modelo de datos

Tres columnas nuevas, todas nullable (no hay que migrar datos existentes):

```
producto.unidades_por_caja   INTEGER        -- NULL = producto sin unidades declaradas
cliente.logo_etiqueta        BYTEA / BLOB   -- NULL = usa el logo de Jomar
cliente.logo_mimetype        VARCHAR(50)    -- 'image/png' | 'image/jpeg'
```

`unidades_por_caja` se agrega a `Producto.to_dict()`.

## Generación de etiquetas por unidades

### El rótulo deja de estar escrito adentro del dibujo

`draw_order_label` y `draw_order_label_a4` reciben hoy `weight=` y tienen la
palabra `"Net Weight:"` escrita fija en el cuerpo de la función. Se reemplaza
ese parámetro por el par `medida_rotulo` / `medida_valor`:

```python
draw_order_label(..., medida_rotulo="Net Weight:", medida_valor="1.50 kg")
draw_order_label(..., medida_rotulo="Units:",      medida_valor="24")
```

El layout, las posiciones y los tamaños de fuente no cambian (rótulo 15.6 bold
alineado a la derecha en `LABEL_X_RIGHT`, valor 16.8 bold). Una sola función
sirve para los tres casos; no se agrega una segunda función de dibujo.

### Qué par emite cada caso

Decidido en `_caja_pesada_to_label_item` y `_detalle_legacy_to_label_item`,
que dejan de devolver `peso_label` y pasan a devolver `medida_rotulo` y
`medida_valor`:

| Caso | Rótulo | Valor | Etiquetas |
|---|---|---|---|
| Producto pesado (`CajaPesada`) | `Net Weight:` | `1.50 kg` | una por caja pesada (sin cambio) |
| Línea legacy con `peso > 0` | `Net Weight:` | `1.50 kg` | una (sin cambio) |
| Por caja **con** `unidades_por_caja` | `Units:` | `24` | **una por caja física** |
| Por caja **sin** `unidades_por_caja` | `Boxes:` | `3` | una (solo cambia el rótulo) |

La asimetría de la última fila es deliberada: cambiarle también la repetición
alteraría la cantidad de etiquetas que hoy se imprimen para productos que no
son parte de este pedido de cambio.

### Cuántas etiquetas por caja física

`_build_label_items_for_pedido` repite el ítem `max(1, detalle.cajas_objetivo)`
veces cuando el producto tiene `unidades_por_caja`. Se reutiliza la propiedad
`DetallePedido.cajas_objetivo` (`app.py:2309`), que ya redondea hacia arriba
con el criterio correcto: media caja pedida sigue siendo una caja física. El
`max(1, ...)` cubre el caso degenerado de una línea con cajas en 0 o NULL, que
si no produciría cero etiquetas.

## Logo del cliente

### Resolución del logo

Nueva función en `utils/label_utils.py`:

```python
def resolve_label_logo(basedir, logo_bytes=None):
    """Devuelve un ImageReader sobre los bytes del cliente, o la ruta del logo
    de Jomar si el cliente no tiene uno."""
```

Recibe **bytes**, no el objeto `Cliente`: `label_utils` no debe importar
modelos de `app.py`. Quien llama pasa `pedido.cliente.logo_etiqueta`.

ReportLab dibuja desde memoria vía `ImageReader(BytesIO(...))`, sin archivo
temporal — nada que Heroku pueda perder en un reinicio.

`draw_logo` y el bloque equivalente de `draw_order_label_a4` hoy hacen
`os.path.exists(logo_path)`, que falla con un `ImageReader`. Se reemplaza por
un helper `_logo_dibujable(logo)` que devuelve `True` si es un `ImageReader`
y hace `os.path.exists` si es una ruta.

La caja del logo sigue siendo 1.20" × 1.20" con `preserveAspectRatio=True` y
`mask='auto'` (respeta la transparencia del PNG). El logo de DeliNova es
cuadrado, así que la llena sin aire sobrante.

### Subida

Se extiende el formulario que ya existe, `templates/cliente_form.html`:

- `enctype="multipart/form-data"` en el `<form>`.
- Campo de archivo `logo`, con vista previa del logo actual si lo hay.
- Casilla `quitar_logo` para volver al logo de Jomar.

Validación en el POST de `editar_cliente`, en este orden:

1. Tamaño ≤ 1 MB (medido sobre los bytes leídos; `MAX_CONTENT_LENGTH` global
   es de 16 MB y no sirve como control).
2. `PIL.Image.open(BytesIO(data)).verify()` — que sea una imagen real, no un
   archivo renombrado.
3. `img.format` en `{'PNG', 'JPEG'}`.

El `mimetype` se guarda desde esa lista blanca, **nunca** desde el
`content-type` que manda el navegador.

Si falla cualquier paso: `flash` con el motivo y no se toca el logo guardado.

### Vista previa

Ruta nueva `GET /clientes/<int:cliente_id>/logo`:

- `@login_required` y el mismo control de permisos que `editar_cliente`
  (super_admin, o vendedor con acceso a ese cliente).
- 404 si el cliente no tiene logo.
- `Content-Type` desde la lista blanca guardada y
  `X-Content-Type-Options: nosniff`, porque sirve contenido subido por usuarios.

## Pantalla de Facturación

El bloque de dibujo manual de `generar_etiqueta` (`app.py:10035`–`10057`) se
reemplaza por una llamada a `draw_order_label_a4`, usando `create_a4_page_pdf()`
y `get_a4_label_positions()` en lugar de las constantes locales.

Beneficio adicional: hoy el nombre del producto se dibuja en una sola línea a
18pt sin control de ancho, así que **un nombre largo se sale de la etiqueta**.
`draw_center_wrap_text` lo achica y lo parte en dos líneas.

Riesgo aceptado: la copia legacy está corrida ~25pt a la izquierda y usa
fuentes 10/14/18 contra 9.5/15.6/16.8. Al unificar, las etiquetas de esta
pantalla saldrán con el espaciado canónico — parecidas pero no idénticas a las
actuales. Se comunicó y se aceptó.

El valor de peso se mantiene como el número pelado (`f"{peso:.2f}"`, sin "kg")
para no cambiar el contenido más allá del layout.

## Pruebas

**Test existente a actualizar:** `tests/test_etiquetas.py:161` y `:186` afirman
sobre el kwarg `weight`; pasan a afirmar sobre `medida_rotulo`/`medida_valor`.

**Tests nuevos** (`tests/test_etiquetas_unidades_logo.py`):

- Producto con `unidades_por_caja=24` y 3 cajas → `draw_order_label` invocado
  3 veces con `medida_rotulo="Units:"`, `medida_valor="24"`.
- Cajas fraccionarias: 2.25 cajas → 3 etiquetas.
- Línea con cajas en 0 → 1 etiqueta, no cero.
- Producto por caja sin `unidades_por_caja` → 1 invocación con
  `medida_rotulo="Boxes:"`.
- Producto pesado → sigue recibiendo `medida_rotulo="Net Weight:"` (regresión).
- `resolve_label_logo` devuelve `ImageReader` con bytes y la ruta de Jomar sin
  ellos.
- Un pedido de un cliente con logo hace que `draw_order_label` reciba un
  `ImageReader` y no la ruta de Jomar; un cliente sin logo recibe la ruta.
  (Se afirma sobre el argumento, no sobre los bytes del PDF: ReportLab
  recomprime las imágenes y buscarlas dentro del PDF sería frágil.)
- Subida: PNG válido se guarda; archivo que no es imagen se rechaza; archivo
  > 1 MB se rechaza; `quitar_logo` borra ambas columnas.
- `GET /clientes/<id>/logo`: 200 con `image/png` y `nosniff`; 404 sin logo;
  403 para un vendedor sin acceso a ese cliente.

Suite completa con `.venv/bin/python -m pytest tests/ -q`, sin forzar
`DATABASE_URL`.

## Migración y despliegue

Migración de Flask-Migrate más el ALTER en producción (el `ALTER` local **no**
alcanza — ver CLAUDE.md):

```
heroku pg:psql --app pesosapp -c "ALTER TABLE producto ADD COLUMN unidades_por_caja INTEGER;"
heroku pg:psql --app pesosapp -c "ALTER TABLE cliente ADD COLUMN logo_etiqueta BYTEA;"
heroku pg:psql --app pesosapp -c "ALTER TABLE cliente ADD COLUMN logo_mimetype VARCHAR(50);"
heroku restart --app pesosapp
```

Después del deploy, en producción:

1. Cargar el logo de DeliNova (QBO 1454) desde "Editar Cliente".
2. Cargar `unidades_por_caja` en los dos productos vendidos por caja.
3. Imprimir un pedido de prueba en 4x2 y en A4 y verificar en papel.

## Fuera de alcance

- Redimensionar o normalizar el logo al subirlo: se guarda el original y
  ReportLab escala al dibujar.
- Logos apaisados: la caja es cuadrada; un logo horizontal quedaría chico con
  aire arriba y abajo. DeliNova es cuadrado, así que no aplica hoy.
- Etiquetas de vencimiento: siguen con el logo de Jomar.
- Capturar unidades caja por caja: se descartó a favor del valor fijo del
  producto.
- Eliminar la duplicación entre `draw_order_label` y `draw_order_label_a4`:
  deuda preexistente, no se toca en este cambio.

## Riesgos

| Riesgo | Mitigación |
|---|---|
| Las etiquetas de Facturación cambian de espaciado | Comunicado y aceptado; verificar impresión antes de dar por cerrado |
| Cambiar la firma de `draw_order_label` rompe llamadas | Solo 3 llamadas en `app.py` más los tests; todas se actualizan en el mismo cambio |
| Servir imágenes subidas por usuarios | Lista blanca de mimetype, validación con Pillow, `nosniff` |
| Peso de las filas de `cliente` en Postgres | ~100 KB por cliente con logo; despreciable a esta escala |
