# El grupo de facturación es el impuesto

Fecha: 2026-08-28
Estado: implementado y desplegado (v872)

Nota de proceso: este documento se escribió **después** de implementar, no
antes. El cambio salió de una pregunta operativa en medio de otra tarea
(«necesito que se agrupen por impuesto») y la evidencia que lo justifica
apareció al ir a buscarla en producción. Queda como registro de por qué se dio
marcha atrás con una decisión aprobada nueve días antes.

## El problema

La pantalla de grupos ofrecía cuatro opciones: `Pesables` e `Importados`,
cruzados con los impuestos 10 y 14. Un pedido no podía mezclarlas, así que un
cliente que quería un pesable y un importado del **mismo impuesto** tenía que
hacer dos pedidos separados —y recibir dos facturas— sin que QuickBooks lo
exigiera.

La causa está en la clave del grupo:

```python
return ('pesable' if producto.se_pesa else 'importado', float(producto.tax_rate or 0))
```

El docstring de `_grupo_facturable` justificaba el `tax_rate` («QuickBooks no
factura en un mismo documento líneas con impuestos distintos») y arrastraba el
`se_pesa` sin justificarlo. Son dos cosas distintas: **`se_pesa` describe cómo
se PREPARA el producto** —si pasa por la báscula— y no tiene nada que decir
sobre cómo lo factura QuickBooks.

## La evidencia

El docstring afirmaba: *«Los 910 pedidos históricos cumplen esta partición sin
una sola excepción»*. Se volvió a medir sobre los 941 pedidos de hoy:

| Qué se midió | Pedidos |
|---|---|
| Mezclan **impuestos** distintos | **0** |
| Mezclan pesable con importado | 7 |
| …de esos, con un **mismo** impuesto | **7** |

Los 7 son de agosto de 2026 —ids 1272, 1277, 1279, 1280, 1287, 1289 y 1297,
todos con tax 14— y **los 7 tienen `invoice_id_qbo`**: QuickBooks los facturó
sin quejarse.

O sea que la afirmación del docstring era falsa. La mitad de la partición que
importa (el impuesto) se cumple sin excepción; la otra mitad (`se_pesa`) la
contradice la propia operación siete veces.

Consulta usada:

```sql
WITH lineas AS (
  SELECT dp.pedido_id, p.se_pesa, p.tax_rate
  FROM detalle_pedido dp JOIN producto p ON p.id = dp.producto_id
  WHERE dp.es_linea_pedido = true
)
SELECT COUNT(DISTINCT se_pesa) AS tipos, COUNT(DISTINCT tax_rate) AS impuestos
FROM lineas GROUP BY pedido_id;
```

Tres de esos siete (1287, 1289, 1297) son **posteriores** al deploy de la
partición estricta (v869, 19 ago). Se creyeron imposibles y existen igual, así
que hay al menos un camino de alta o edición que no pasa por
`_validar_grupo_unico` —que solo se invoca desde `_extraer_lineas_pedido_form`—
o bien alguien cambió el `se_pesa` de un producto después de tomado el pedido.
No se investigó cuál: con el grupo por impuesto los siete pasan a ser
legítimos, así que deja de ser un síntoma. **Queda anotado como cabo suelto**
por si aparece otra restricción que dependa de ese guard.

## La decisión

**El grupo es el `tax_rate`, y nada más.**

```python
return float(producto.tax_rate or 0)
```

Mezclar impuestos sigue prohibido: es el único candado real y el que la
operación nunca violó en 941 pedidos.

| | Antes | Ahora |
|---|---|---|
| Clave | `pesable:14` | `imp:14` |
| Etiqueta | `Pesables · imp. 14` | `Impuesto 14` |
| Grupos en el catálogo de prod | 4 | 2 |
| Productos ofrecidos en imp. 14 | 19 pesables **o** 2 importados | 21, juntos |

El orden pasa a ser por impuesto ascendente. Se mantiene lo que ya funcionaba:
los grupos salen del **catálogo** y no del historial (así cada uno conserva su
posición y el vendedor aprende el gesto), el historial del cliente decora la
tarjeta, y cada tarjeta lleva dos productos de ejemplo — `tax_rate` es un
código de QuickBooks, no un porcentaje, así que «Impuesto 14» por sí solo no le
dice nada a nadie.

## Compatibilidad de las claves

La clave viaja en la URL (`?grupo=`) y en un hidden del formulario, así que hay
marcadores guardados y pestañas abiertas con la forma vieja.
`_normalizar_clave_grupo` se queda con la parte del impuesto:

```
pesable:14  -> imp:14
importado:14 -> imp:14
imp:14      -> imp:14
14          -> imp:14
basura      -> ''      (cae en la pantalla de grupos, como cualquier clave inválida)
```

Se normaliza en las dos entradas: el `GET` que abre el paso del pedido y el
`POST` que lo guarda. Sin esto, un enlace viejo mandaba al vendedor de vuelta a
elegir grupo sin explicación.

## La trampa del impuesto 0

Al pasar la clave de tupla a número apareció un agujero: **`0.0` es falsy**. Los
guards escritos como `if not grupo` habrían tratado el impuesto 0 como «sin
grupo», dejando esos productos sin clave ni etiqueta. Pasaron a `is None`.

Hoy no hay productos con `tax_rate` 0 en producción, pero la columna arranca en
`0.0` por defecto: un producto recién creado sin impuesto elegido caía justo
ahí. Hay un test que lo fija.

## Qué no cambia

- El guard de servidor sigue corriendo en alta y edición.
- La preparación y el pesaje siguen mirando `se_pesa` por línea; un pedido
  mixto muestra el pesaje para sus pesables y las líneas de preparación para el
  resto, que es lo que ya hacían los 7 pedidos de producción.
- `pedido_a_json` no se tocó: sigue mandando peso para lo pesado y cajas para
  lo demás.
- El paso 2 sigue existiendo para todos los clientes.

## Tests

Nuevos, en `tests/test_grupo_por_impuesto.py`: un pesable y un importado del
mismo impuesto son el mismo grupo; impuestos distintos siguen separados; el
catálogo colapsa cuatro combinaciones en dos grupos; los ejemplos de la tarjeta
mezclan tipos; el impuesto 0 tiene clave propia; las claves viejas resuelven, y
un enlace viejo aterriza en el grupo correcto a nivel de ruta.

Actualizados: 17 tests en cuatro archivos estaban acoplados a las claves
viejas. Casi todo era test rot, salvo uno **semántico** que conviene tener
presente: `test_servidor_rechaza_pedido_mezclado` mezclaba un pesable y un
importado del **mismo** impuesto y esperaba rechazo. Como eso ahora es
legítimo, pasó a mezclar impuestos —el candado que queda— y se sumó el espejo
`test_servidor_acepta_pesable_e_importado_del_mismo_impuesto`, que fija la
conducta nueva a nivel de ruta.

Suite completa: 596 passed, 1 skipped.

## El costo

- Los vendedores ven dos tarjetas donde ayer veían cuatro, sin aviso previo.
  Hay que contárselo.
- Se pierde el filtro por tipo dentro del buscador del paso 3: quien quiera
  solo pesables ahora los ve mezclados con los importados de su impuesto. No
  apareció como necesidad; si aparece, es un filtro de la pantalla y no un
  grupo de facturación.

## Referencias

- Implementación: `_grupo_facturable`, `_clave_grupo`, `_normalizar_clave_grupo`,
  `_etiqueta_grupo`, `_grupos_del_catalogo` (`app.py`).
- Diseño anterior, del que esto corrige la partición:
  [2026-08-19-grupo-siempre-elegido-design.md](2026-08-19-grupo-siempre-elegido-design.md).
- Commit: `734d6adc` — desplegado en v872.
