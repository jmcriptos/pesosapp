# Story 3.0: Consolidar flujo de pedidos y preservar datos para OFR

Status: review

## Story

As a **administrador del negocio**,
I want **que el flujo de pedidos se consolide en una sola vista (/detalles), eliminando la ruta duplicada (/preparar), preservando las cantidades originales del vendedor, y que se agregue un botón "Marcar como Listo" con validación automática de trazabilidad**,
so that **los datos de pedido vs despacho se preservan para calcular el OFR (Order Fill Rate) y el preparador tiene un flujo claro sin duplicación**.

## Acceptance Criteria

1. **Ruta `/preparar` eliminada con redirect**: Dado que un usuario accede a `/pedidos/<id>/preparar`, cuando la ruta se ejecuta, entonces redirige 301 a `/pedidos/<id>/detalles`. El template `preparar_pedido.html` ya no se usa.
2. **Línea original del vendedor no se borra**: Dado que el vendedor creó un pedido con "10 cajas de Chuleta Ahumada" (línea con cajas=10, peso=0), cuando el preparador agrega líneas de pesada en `/detalles`, entonces la línea original (peso=0, trazabilidad vacía) se mantiene intacta como referencia. El preparador NO necesita borrarla.
3. **Campo `es_linea_pedido` distingue líneas**: Dado que existen líneas del vendedor y líneas del preparador en el mismo pedido, cuando el sistema muestra/procesa detalles, entonces las líneas con `es_linea_pedido=True` son las originales del vendedor y las de `es_linea_pedido=False` son las de preparación.
4. **Botón "Marcar como Listo"**: Dado que un pedido está en estado `pendiente` y tiene líneas de preparación, cuando el admin/preparador hace clic en "Marcar como Listo", entonces el sistema valida automáticamente que TODAS las líneas de preparación (`es_linea_pedido=False`) tengan lote, fecha_fabricacion y fecha_expiracion completos. Si falta algún dato, muestra error con los productos incompletos. Si todo está completo, cambia el estado a `listo`.
5. **Productos de importación con fecha de vencimiento**: Dado que un producto tiene `se_pesa=False` (importación/distribución), cuando el preparador marca el pedido como listo, entonces el sistema valida que al menos la `fecha_expiracion` esté presente en la línea original del vendedor (estas líneas no necesitan líneas de preparación separadas).
6. **Facturación filtra líneas correctamente**: Dado que un pedido tiene líneas originales (peso=0) y líneas de preparación (peso>0), cuando se factura, entonces `pedido_a_json()` solo incluye las líneas de preparación (`es_linea_pedido=False`) para productos `se_pesa=True`, y las líneas originales para productos `se_pesa=False`.
7. **Etiquetas filtra líneas correctamente**: Dado que se generan etiquetas 4x2 o A4, cuando el sistema procesa los detalles, entonces solo genera etiquetas para líneas de preparación (con peso real y trazabilidad), no para líneas originales del vendedor.
8. **Línea original muestra estado visual en `/detalles`**: Dado que una línea es del vendedor (`es_linea_pedido=True`), cuando se muestra en la tabla de productos, entonces se distingue visualmente (color diferente, etiqueta "Pedido original") y los botones editar/eliminar están deshabilitados para esa línea.
9. **Sin regresiones**: Login, dashboard, creación de pedidos en `/pedidos/nuevo`, facturación y etiquetas siguen funcionando correctamente.

## Tasks / Subtasks

- [ ] **Task 1: Migración DB — agregar campo `es_linea_pedido`** (AC: #3)
  - [ ] 1.1 Crear migración Alembic: `ALTER TABLE detalle_pedido ADD COLUMN es_linea_pedido BOOLEAN DEFAULT TRUE NOT NULL`
  - [ ] 1.2 `server_default=sa.text('TRUE')` — PostgreSQL boolean (aprendizaje de Story 2.2: usar TRUE/FALSE, no 0/1)
  - [ ] 1.3 Agregar campo al modelo `DetallePedido` en `app.py:894`: `es_linea_pedido = db.Column(db.Boolean, default=True, nullable=False)`
  - [ ] 1.4 Default=True porque las líneas existentes son del vendedor; las nuevas líneas de preparación se crearán con `es_linea_pedido=False`

- [ ] **Task 2: Ruta `/preparar` → redirect 301** (AC: #1)
  - [ ] 2.1 Reemplazar el cuerpo de `preparar_pedido()` en `app.py:3443-3495` con: `return redirect(url_for('detalles_pedido', pedido_id=pedido_id), code=301)`
  - [ ] 2.2 Eliminar `templates/preparar_pedido.html`
  - [ ] 2.3 Verificar que no hay otros links internos apuntando a `/preparar` (buscar en templates y app.py)

- [ ] **Task 3: Ruta `POST /pedidos/<id>/marcar_listo`** (AC: #4, #5)
  - [ ] 3.1 Crear nueva ruta `marcar_listo(pedido_id)` con `methods=['POST']`, `@login_required`
  - [ ] 3.2 Verificar inmutabilidad: si `pedido.estado == 'facturado'` → flash error + redirect
  - [ ] 3.3 Validación para productos `se_pesa=True`: verificar que existen líneas de preparación (`es_linea_pedido=False`) con lote + fecha_fab + fecha_exp
  - [ ] 3.4 Validación para productos `se_pesa=False` (importación): verificar que la línea original tiene al menos `fecha_expiracion`
  - [ ] 3.5 Si hay errores → flash con lista detallada de productos incompletos, no cambiar estado
  - [ ] 3.6 Si todo valida → `pedido.estado = 'listo'`, `db.session.commit()`, flash success + redirect

- [ ] **Task 4: Modificar formulario "Agregar producto" en `/detalles`** (AC: #2, #3)
  - [ ] 4.1 En `detalles_pedido()` POST handler (`app.py:3044`): al crear `DetallePedido`, setear `es_linea_pedido=False`
  - [ ] 4.2 NO modificar la lógica de preload JS ni el formulario — funciona perfecto como está

- [ ] **Task 5: Botón "Marcar como Listo" en template** (AC: #4, #8)
  - [ ] 5.1 En `detalles_pedido.html`, agregar botón "Marcar como Listo" después de la tabla de productos
  - [ ] 5.2 Solo visible cuando `pedido.estado == 'pendiente'`
  - [ ] 5.3 Estilo: `mobile-btn mobile-btn-primary` (azul, diferente del verde de "Agregar")
  - [ ] 5.4 Form con POST a `/pedidos/<id>/marcar_listo` + CSRF token
  - [ ] 5.5 Diferenciar visualmente las líneas `es_linea_pedido=True` (gris, etiqueta "Pedido") de las líneas de preparación

- [ ] **Task 6: Actualizar `pedido_a_json()` para filtrar líneas** (AC: #6)
  - [ ] 6.1 En `pedido_a_json()` (`app.py:1309-1337`): para productos `se_pesa=True`, solo incluir líneas con `es_linea_pedido=False`
  - [ ] 6.2 Para productos `se_pesa=False`, incluir las líneas originales (son las únicas)
  - [ ] 6.3 Mantener la lógica de `cajas or peso` y `tax_rate`

- [ ] **Task 7: Actualizar rutas de etiquetas para filtrar líneas** (AC: #7)
  - [ ] 7.1 En `generar_etiqueta_detalle()` (`app.py:3186-3295`): filtrar solo líneas de preparación (`es_linea_pedido=False`) para productos que se pesan
  - [ ] 7.2 En `generar_etiqueta_detalle_a4()` (`app.py:3300-3418`): mismo filtro
  - [ ] 7.3 Incluir líneas originales de productos de importación (tienen fecha_expiracion pero no peso)

- [ ] **Task 8: Escribir tests** (AC: #1-#9)
  - [ ] 8.1 Test: GET `/preparar` → redirect 301 a `/detalles`
  - [ ] 8.2 Test: POST agregar detalle → `es_linea_pedido=False`
  - [ ] 8.3 Test: POST marcar_listo con trazabilidad completa → estado `listo`
  - [ ] 8.4 Test: POST marcar_listo sin trazabilidad → error, estado sigue `pendiente`
  - [ ] 8.5 Test: POST marcar_listo con producto importación sin fecha_exp → error
  - [ ] 8.6 Test: POST marcar_listo pedido facturado → error
  - [ ] 8.7 Test: pedido_a_json filtra líneas originales para se_pesa=True
  - [ ] 8.8 Test: etiquetas solo generan para líneas de preparación
  - [ ] 8.9 Test: regresión — login, dashboard, facturación siguen funcionando

## Dev Notes

### Contexto del Cambio

Este story surge de una revisión del flujo de pedidos en Party Mode. Se identificó que:
- `/preparar` y `/detalles` eran rutas duplicadas
- El preparador ya trabaja exclusivamente en `/detalles` usando el formulario "Agregar producto" con preload
- Al borrar la línea original del vendedor y recrear líneas de pesada, se perdía el dato de "cuánto pidió el vendedor"
- Sin ese dato, el OFR (Epic 3, Story 3-1) no se puede calcular
- Los productos de importación/distribución no registraban trazabilidad

### Flujo Actual vs Propuesto

**ACTUAL (problemático):**
```
Vendedor: /pedidos/nuevo → crea línea (cajas=10, peso=0)
Preparador: /detalles → BORRA línea original → agrega 10 líneas nuevas con peso
→ Dato de "10 cajas pedidas" SE PIERDE
```

**PROPUESTO:**
```
Vendedor: /pedidos/nuevo → crea línea (cajas=10, peso=0, es_linea_pedido=True)
Preparador: /detalles → NO borra → agrega líneas de pesada (es_linea_pedido=False)
Preparador: clic "Marcar como Listo" → valida trazabilidad → estado=listo
→ Línea original PRESERVADA → OFR calculable: count(líneas pesada) / cajas original
```

### Modelo DetallePedido — Campo Nuevo

```python
class DetallePedido(db.Model):
    # ... campos existentes ...
    es_linea_pedido = db.Column(db.Boolean, default=True, nullable=False)
    # True = línea creada por vendedor en /pedidos/nuevo (referencia para OFR)
    # False = línea creada por preparador en /detalles (dato real de despacho)
```

### Cálculo OFR (para referencia de Story 3-1)

```python
# Por producto en un pedido:
linea_original = DetallePedido.query.filter_by(pedido_id=pid, producto_id=prod_id, es_linea_pedido=True).first()
lineas_pesadas = DetallePedido.query.filter_by(pedido_id=pid, producto_id=prod_id, es_linea_pedido=False).count()
ofr_linea = min(1.0, lineas_pesadas / linea_original.cajas) if linea_original.cajas > 0 else 1.0
```

### Código Actual — Rutas Afectadas

**Ruta preparar_pedido**: `app.py:3443-3495` → reemplazar con redirect 301
**Ruta detalles_pedido**: `app.py:3023-3114` → modificar POST para `es_linea_pedido=False`
**Ruta marcar_listo**: NUEVA — validación + estado
**pedido_a_json()**: `app.py:1309-1337` → filtrar líneas
**Etiquetas 4x2**: `app.py:3186-3295` → filtrar líneas
**Etiquetas A4**: `app.py:3300-3418` → filtrar líneas
**Template**: `templates/detalles_pedido.html` → botón + visual diferenciador

### JavaScript del Formulario "Agregar Producto" — NO TOCAR

El JS de autocomplete (`detalles_pedido.html:1209-1355`) es el corazón del flujo del preparador:
- localStorage persiste: producto_id, lote, fecha_fab, fecha_exp (NO peso)
- Expiration auto-calculada desde fecha fabricación + shelf life del producto
- Normalización decimal (coma → punto) en tiempo real
- Enter navega entre campos: prod → peso → lote → fab → exp
- Después de submit, peso se limpia y recibe focus automático

**Este JS NO se toca.** Es exactamente lo que el preparador necesita.

### Patrón de Validación Consistente

Seguir el patrón establecido en Story 2.3:
- Iterar `pedido.detalles`, recoger errores en lista
- Flash con cada error individual
- Si hay errores → redirect sin cambiar estado
- Si todo valida → commit + flash success

### Migración — Cuidado PostgreSQL

- Usar `server_default=sa.text('TRUE')` — NO `sa.text('1')` (error aprendido en Story 2.2)
- `down_revision` debe apuntar a la última migración: `c1b6a56753d6` (add_se_pesa)
- Verificar con `flask db heads` antes de crear migración

### Facturación — Cambio en pedido_a_json()

La función `pedido_a_json()` actualmente itera TODOS los `pedido.detalles`. Con el cambio:
- Para `se_pesa=True`: solo incluir `d` donde `d.es_linea_pedido == False` (líneas de preparación con peso real)
- Para `se_pesa=False`: incluir `d` donde `d.es_linea_pedido == True` (línea original del vendedor)
- La lógica de precio y subtotal no cambia

### Template — Diferenciación Visual

En la tabla de productos de `detalles_pedido.html`, las líneas `es_linea_pedido=True` deben:
- Tener fondo gris claro (`background-color: #f8f9fa`)
- Mostrar badge "Pedido" al lado del nombre del producto
- NO mostrar botones editar/eliminar (son inmutables)
- Las líneas de preparación (`es_linea_pedido=False`) se muestran normalmente con todos los botones

### Learnings de Stories Anteriores

- **Tests:** `python -m pytest -p no:postgresql tests/ -v`
- **Pre-existing failures:** 3 tests en `test_csrf.py` (no relacionados)
- **Test DB:** SQLite in-memory via `db.create_all()` en fixture
- **Fixture pattern:** Crear Rol(super_admin), Territorio, Vendedor, Cliente, Producto(se_pesa, temperatura, qbo_id), Pedido+DetallePedido en fixture `app()`
- **Login en tests:** POST `/login` con data `username/password` y `follow_redirects=True`
- **Mock N8N:** Para tests de facturación, mock `requests.post` en `app.requests.post`
- **PostgreSQL boolean defaults:** Usar `TRUE`/`FALSE` en `server_default`, NUNCA `0`/`1`
- **Null safety:** Siempre usar `or 0` para numéricos, `or 'N/A'` para strings de trazabilidad
- **label_utils.py:** `weight` parameter acepta string pre-formateado (ej: "12.50 kg")

### IMPORTANTE: No Tocar

- **JavaScript de autocomplete** en `detalles_pedido.html:1209-1355` — funciona perfecto
- **Formulario "Agregar producto"** — solo cambiar `es_linea_pedido=False` en el backend
- **`utils/label_utils.py`** — funciones de dibujo no se modifican
- **Rutas de facturación** — solo modificar `pedido_a_json()`, no la lógica de N8N
- **`requirements.txt`** — NO agregar dependencias

### Project Structure Notes

- Ruta preparar_pedido en `app.py:3443-3495` → reemplazar con redirect
- Ruta detalles_pedido en `app.py:3023-3114` → modificar POST
- Ruta editar_detalle en `app.py:3140-3179` → no cambiar
- Ruta eliminar_detalle en `app.py:3117-3137` → no cambiar
- Ruta facturar_pedido en `app.py:3503-3594` → no cambiar directamente
- `pedido_a_json()` en `app.py:1309-1337` → modificar filtro
- Etiquetas 4x2 en `app.py:3186-3295` → agregar filtro
- Etiquetas A4 en `app.py:3300-3418` → agregar filtro
- Template en `templates/detalles_pedido.html` → agregar botón + visual
- Modelo DetallePedido en `app.py:894-911` → agregar campo
- `templates/preparar_pedido.html` → ELIMINAR

### References

- [Source: app.py:3443-3495] — Ruta preparar_pedido (a eliminar)
- [Source: app.py:3023-3114] — Ruta detalles_pedido (a modificar POST)
- [Source: app.py:1309-1337] — pedido_a_json() (a modificar filtro)
- [Source: app.py:3186-3295] — Ruta etiquetas 4x2 (agregar filtro)
- [Source: app.py:3300-3418] — Ruta etiquetas A4 (agregar filtro)
- [Source: app.py:894-911] — Modelo DetallePedido (agregar campo)
- [Source: app.py:773-794] — Modelo Producto (se_pesa, temperatura)
- [Source: templates/detalles_pedido.html:1209-1355] — JS autocomplete (NO TOCAR)
- [Source: _bmad-output/planning-artifacts/epics.md#Epic-3] — Epic 3 context
- [Source: _bmad-output/planning-artifacts/epics.md#FR9] — Diferencia pedida vs preparada
- [Source: _bmad-output/planning-artifacts/epics.md#FR20] — OFR línea por línea
- [Source: _bmad-output/implementation-artifacts/2-3-trazabilidad-obligatoria-preparacion.md] — Patrón validación
- [Source: _bmad-output/implementation-artifacts/2-5-verificar-etiquetas-pedidos.md] — Patrón etiquetas
- [Source: Party Mode Discussion 2026-02-08] — Decisiones de diseño con John, Sally, Winston, Amelia, Mary, Bob

## Dev Agent Record

### Agent Model Used

{{agent_model_name_version}}

### Debug Log References

### Completion Notes List

### Change Log

### File List
