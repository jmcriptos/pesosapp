# Restaurar pesos individuales de cajas en Description de QBO

**Fecha:** 2026-04-22
**Estado:** Diseño aprobado, listo para plan

## Problema

Cuando un pedido con productos pesables se factura a QuickBooks, la columna
`Description` de cada línea ya no muestra los pesos individuales de cada caja.
Solo muestra el peso total agregado (ej. `"27.35"`) en vez de la lista
`"2.50  3.10  2.80  3.20  2.95  3.05  2.75  3.20"`.

Los clientes necesitan ver los pesos individuales en la factura para
verificar cada caja al recibir la mercancía.

## Causa raíz

El bug se introdujo en el commit `0154c2b1` ("feat(ui): pantalla Pesar + glass
reskin flujo pedidos + dashboard light") al cambiar el modelo de datos de
cajas pesadas.

### Contrato previo (funcional)

La app emitía **una línea del payload por cada caja pesada**. Cada línea
llevaba `qty = peso_de_esa_caja`. El nodo "Generar Numero Factura" en N8N
agrupa líneas por `product_qbo_id + unit_price`:

```js
for (const l of body.lines ?? []) {
  const key = `${l.product_qbo_id}_${l.unit_price}`;
  const e = map.get(key) ?? { ...l, qty: 0, descriptions: [] };
  e.qty += Number(l.qty);
  e.descriptions.push(formatDecimal(l.qty));  // <- acumula cada peso
  map.set(key, e);
}
...
Description: l.descriptions.join('\t'),
```

Con N líneas entrantes del mismo producto, `descriptions` contenía los N
pesos individuales y la `Description` en QBO los mostraba tabulados.

### Contrato actual (roto)

Tras `0154c2b1`, `pedido_a_json` emite **una sola línea por producto pesable**
con `qty = detalle.peso_real` (suma de todas las cajas). N8N recibe 1 línea,
agrupa 1 línea, y `descriptions = [peso_total]` → la Description solo muestra
el total.

## Decisión de diseño

**Restaurar el contrato previo desde el lado de la app, sin tocar N8N.**

Razones:
- N8N funciona correctamente; el bug es exclusivamente del lado del app.
- Cambiar N8N requiere editar el workflow y re-desplegarlo — más riesgo.
- Mantener la semántica de "una línea por caja" es compatible con el resto
  del workflow (agrupación, impuestos, class detection) sin modificar nada.

## Cambio específico

En `app.py`, función `pedido_a_json` (línea 2803), dentro del loop de
productos pesables, reemplazar el `append` agregado por un loop interno
que itera `detalle.cajas_pesadas`:

```python
for detalle in _pedido_detalles_pesables(pedido):
    if not detalle.cajas_pesadas_count:
        continue

    productos_con_cajas.add(detalle.producto_id)

    for caja in sorted(detalle.cajas_pesadas, key=lambda c: (c.numero, c.id)):
        qty = float(caja.peso or 0)
        if qty == 0:
            continue
        subtotal = float(detalle.precio_unitario) * qty
        total += subtotal
        lineas.append({
            "product_qbo_id": detalle.producto.qbo_id,
            "descripcion": detalle.producto.nombre,
            "qty": qty,
            "unit_price": float(detalle.precio_unitario),
            "amount": round(subtotal, 2),
            "tax_rate": detalle.producto.tax_rate,
        })
```

Notas:
- `descripcion` lleva solo el nombre del producto (sin lote, sin pesos).
  N8N **no** lo lee para construir `Line.Description` (la arma desde
  `descriptions[]` acumulado a partir de `qty`), pero **sí** lo usa como
  fallback para `productName` en la detección de classes
  (`l.product_name || l.name || l.description || ''`). Mantenerlo con el
  nombre preserva el class detection (Cocidos y Ahumados, Mantova, Atún
  Van Camps, Tomate, Untables Underwood) y el `ItemRef.name`.
- El orden `(c.numero, c.id)` preserva el orden de pesaje, por lo que la
  secuencia en la factura coincide con el orden físico de las cajas.
- El segundo loop (productos no pesables / legacy prep lines) queda igual.

## Resultado esperado

En cada línea de factura QBO con producto pesable:

- **Product/Service** (ItemRef): nombre del producto, resuelto por QBO
  desde `product_qbo_id`.
- **Qty**: peso total (sumado por N8N = `detalle.peso_real`).
- **Description**: pesos individuales tabulados, ej.
  `2.50\t3.10\t2.80\t3.20\t2.95\t3.05\t2.75\t3.20`.

## Verificaciones / efectos secundarios

- **Total de la factura**: cada sub-línea lleva `amount = qty * unit_price`.
  La suma es idéntica a `peso_real * unit_price`. ✅
- **Impuestos**: N8N calcula tax sobre el subtotal agregado (post-grouping),
  no sobre las sub-líneas individuales. ✅
- **Class detection**: sigue funcionando gracias a `descripcion = producto.nombre`,
  que N8N lee como fallback de `productName` para el keyword matching. ✅
- **Multi-currency**: `currency` y `tipo_cambio` son a nivel de pedido, no
  por línea. ✅
- **Productos no pesables**: segundo loop intacto. ✅

## Plan de verificación

1. Ejecutar tests locales (`pytest tests/test_facturacion*`).
2. Deploy a Heroku.
3. Tomar un pedido preparado con al menos 2 productos pesables (cada uno con
   ≥3 cajas pesadas con pesos distintos) y facturar.
4. Confirmar en QBO que la factura muestra los pesos individuales en
   Description de cada línea.
5. Confirmar que el total de la factura coincide con el total calculado en
   el app (dashboard + listado).

## Qué NO cambia

- N8N workflow (ningún nodo).
- Modelo de datos (`DetallePedido`, `CajaPesada`).
- UI del flujo "Pesar" / "Preparar" / "Facturar".
- Lógica del dashboard (usa `_calcular_venta_pedido`, no este payload).
- Ruta `/pedidos/<id>/facturar` (solo cambia el contenido del payload que
  construye `pedido_a_json`).
