# Restaurar pesos individuales de cajas en Description de QBO — Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Hacer que `pedido_a_json` emita una línea del payload por cada `CajaPesada` (en lugar de una línea agregada por `DetallePedido`) para que el nodo "Generar Numero Factura" de N8N reconstruya los pesos individuales en el campo `Line.Description` de la factura QBO.

**Architecture:** Cambio localizado en una sola función (`app.py:2803 pedido_a_json`). Se reemplaza el loop de productos pesables por un loop anidado sobre `detalle.cajas_pesadas`. Se descarta el helper `_formatear_cajas_pesadas` (intento previo fallido, presente en cambios no comiteados). Cero cambios en N8N. TDD: test que verifica el payload antes de modificar la función.

**Tech Stack:** Python 3, Flask, SQLAlchemy, pytest, Heroku (deploy via git push).

**Spec:** `docs/superpowers/specs/2026-04-22-restaurar-pesos-cajas-qbo-description-design.md`

---

## Task 1: Limpiar cambios no comiteados en app.py

**Context:** El working tree tiene modificaciones no comiteadas en `app.py` (agregan el helper `_formatear_cajas_pesadas` y lo usan para concatenar pesos al campo `descripcion`). Ese intento no resuelve el problema — N8N no lee `l.description` para la `Line.Description` de QBO — y choca con el fix real. Hay que descartarlo antes de empezar.

**Files:**
- Modify: `app.py` (revertir hunks 2788-2825)

- [ ] **Step 1: Respaldar los cambios con `git stash`**

Run:
```bash
git stash push -m "intento previo pesos cajas qbo (descartado, ver plan 2026-04-22)" app.py
```

Expected: Mensaje `Saved working directory and index state On main: intento previo pesos cajas qbo ...`.

- [ ] **Step 2: Verificar que `app.py` quedó en estado HEAD limpio**

Run:
```bash
git diff --stat app.py && git status
```

Expected: `git diff --stat app.py` sin output (sin diff), `git status` muestra `app.py` limpio (ya no modificado). `scripts/upload_precios_cliente.py` sigue untracked — OK, no nos toca.

- [ ] **Step 3: Confirmar el contenido actual de `pedido_a_json`**

Run:
```bash
sed -n '2800,2830p' app.py
```

Expected: El primer loop sobre `_pedido_detalles_pesables(pedido)` usa `qty = float(detalle.peso_real)` y hace un solo `lineas.append(...)` por detalle. NO existe `_formatear_cajas_pesadas` ni el string `detalle_cajas` en esa zona.

---

## Task 2: Escribir test failing para `pedido_a_json` con cajas pesadas

**Context:** El test existente (`tests/test_facturacion.py`) mockea N8N pero nunca inspecciona el payload que produce `pedido_a_json`. Agregamos un test nuevo en un archivo dedicado que monta un pedido con 3 cajas pesadas con pesos distintos y verifica que el payload contiene 3 líneas (una por caja) con los pesos correctos.

**Files:**
- Create: `tests/test_pedido_a_json.py`

- [ ] **Step 1: Crear el test con fixtures y 2 aserciones clave**

Create `tests/test_pedido_a_json.py`:

```python
"""Tests for pedido_a_json payload structure — specifically that it emits
one line per CajaPesada so N8N can reconstruct individual box weights
in the QBO invoice Description column.
"""
import os
from datetime import date, datetime
from decimal import Decimal

import pytest

os.environ.setdefault('SECRET_KEY', 'test-secret')
os.environ.setdefault('FLASK_ENV', 'testing')
os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')

from app import app as flask_app, db as _db


@pytest.fixture
def app():
    flask_app.config.update(
        TESTING=True,
        WTF_CSRF_ENABLED=False,
        SQLALCHEMY_DATABASE_URI='sqlite:///:memory:',
    )
    with flask_app.app_context():
        _db.create_all()
        yield flask_app
        _db.drop_all()


def _build_pedido_pesable_con_cajas(app, pesos):
    """Crea un pedido con 1 producto pesable y N CajaPesada con los pesos
    indicados. Devuelve (pedido, producto) dentro del app_context activo."""
    from app import (
        Rol, Territorio, Vendedor, Cliente, Producto,
        Pedido, DetallePedido, CajaPesada,
    )

    rol = Rol(nombre='super_admin', descripcion='Admin')
    _db.session.add(rol)
    territorio = Territorio(nombre='t1', descripcion='T1')
    _db.session.add(territorio)
    _db.session.flush()

    vendedor = Vendedor(
        username='tester', email='t@test.com', nombre_completo='Tester',
        rol_id=rol.id, territorio_id=territorio.id, activo=True,
    )
    vendedor.set_password('x')
    _db.session.add(vendedor)

    cliente = Cliente(
        nombre='Cliente QBO', territorio_id=territorio.id, qbo_id='QBO-C1',
    )
    _db.session.add(cliente)

    producto = Producto(
        nombre='Atún Van Camps 170g', descripcion='Atún', temperatura='Seco',
        se_pesa=True, tax_rate=6.0, qbo_id='QBO-P1',
    )
    _db.session.add(producto)
    _db.session.flush()

    pedido = Pedido(cliente_id=cliente.id, estado='preparado', tipo_cambio=1.0)
    _db.session.add(pedido)
    _db.session.flush()

    detalle = DetallePedido(
        pedido_id=pedido.id,
        producto_id=producto.id,
        cajas=len(pesos),
        cajas_pedidas=len(pesos),
        peso=0,
        precio_unitario=Decimal('10.00'),
        subtotal=Decimal('0'),
        es_linea_pedido=True,
    )
    _db.session.add(detalle)
    _db.session.flush()

    for idx, peso in enumerate(pesos, start=1):
        caja = CajaPesada(
            detalle_pedido_id=detalle.id,
            numero=idx,
            peso=Decimal(str(peso)),
            lote=f'L{idx}',
            fecha_elaboracion=date(2026, 1, 1),
            fecha_vencimiento=date(2026, 6, 1),
            pesado_por=vendedor.id,
            pesado_en=datetime(2026, 4, 22, 12, 0, 0),
        )
        _db.session.add(caja)
    _db.session.commit()
    return pedido, producto


def test_pedido_a_json_emite_una_linea_por_caja(app):
    """Cada CajaPesada debe producir una línea independiente en el payload
    con qty=peso de esa caja, preservando el orden por `numero`."""
    from app import pedido_a_json

    with app.app_context():
        pesos = [2.50, 3.10, 2.80]
        pedido, producto = _build_pedido_pesable_con_cajas(app, pesos)

        payload = pedido_a_json(pedido)

        assert len(payload['lines']) == 3, (
            f"Esperaba 3 líneas (una por caja), recibí {len(payload['lines'])}"
        )
        qtys = [line['qty'] for line in payload['lines']]
        assert qtys == pesos, f"Pesos en orden esperado={pesos}, recibido={qtys}"

        for line in payload['lines']:
            assert line['product_qbo_id'] == producto.qbo_id
            assert line['unit_price'] == 10.00
            assert line['descripcion'] == producto.nombre


def test_pedido_a_json_total_y_amounts_coinciden(app):
    """El total del payload debe ser sum(peso_i * precio_unitario) y cada
    `amount` debe ser qty * unit_price redondeado a 2 decimales."""
    from app import pedido_a_json

    with app.app_context():
        pesos = [2.50, 3.10, 2.80]
        pedido, _producto = _build_pedido_pesable_con_cajas(app, pesos)

        payload = pedido_a_json(pedido)

        expected_amounts = [round(p * 10.00, 2) for p in pesos]
        assert [line['amount'] for line in payload['lines']] == expected_amounts
        assert payload['total'] == round(sum(expected_amounts), 2)
```

- [ ] **Step 2: Correr el test y verificar que falla**

Run:
```bash
pytest tests/test_pedido_a_json.py -v
```

Expected: Ambos tests fallan. El primero falla con algo como
`Esperaba 3 líneas (una por caja), recibí 1` porque la versión actual emite
una sola línea agregada con `qty=8.40`. El segundo también falla porque
`payload['lines']` tiene 1 sola entrada con `amount=84.00`.

- [ ] **Step 3: Commit del test fallido**

```bash
git add tests/test_pedido_a_json.py
git commit -m "test(facturacion): verify pedido_a_json emits one line per CajaPesada

Red test for the QBO Description weights restore. Expects pedido_a_json
to emit one payload line per weighed box (qty = that box weight), so the
N8N workflow can reconstruct Line.Description as the tab-joined list of
individual weights.

Currently failing — the aggregate single-line behavior introduced in
0154c2b1 causes QBO to show only the total weight."
```

---

## Task 3: Modificar `pedido_a_json` para emitir una línea por caja

**Context:** Reemplazar el loop actual que emite una línea agregada por un loop que itera `detalle.cajas_pesadas` y emite una línea por caja. El segundo loop (productos no pesables) queda intacto.

**Files:**
- Modify: `app.py:2803-2837` (función `pedido_a_json`, primer loop)

- [ ] **Step 1: Reemplazar el loop de productos pesables**

Use the Edit tool to replace this block in `app.py` (inside function `pedido_a_json`):

Old (current in HEAD):
```python
    for detalle in _pedido_detalles_pesables(pedido):
        if not detalle.cajas_pesadas_count:
            continue

        qty = float(detalle.peso_real)
        if qty == 0:
            continue

        productos_con_cajas.add(detalle.producto_id)

        descripcion = detalle.producto.nombre
        lote = detalle.lote_principal
        if lote:
            descripcion += f" (Lote {lote})"

        subtotal = float(detalle.precio_unitario) * qty
        total += subtotal

        lineas.append({
            "product_qbo_id": detalle.producto.qbo_id,
            "descripcion": descripcion,
            "qty": qty,
            "unit_price": float(detalle.precio_unitario),
            "amount": round(subtotal, 2),
            "tax_rate": detalle.producto.tax_rate
        })
```

New:
```python
    for detalle in _pedido_detalles_pesables(pedido):
        if not detalle.cajas_pesadas_count:
            continue

        productos_con_cajas.add(detalle.producto_id)

        # Una línea del payload por cada CajaPesada: N8N agrupa por
        # (product_qbo_id, unit_price) y acumula cada qty individual en
        # descriptions[] para escribirlo en Line.Description de QBO.
        cajas_ordenadas = sorted(
            detalle.cajas_pesadas, key=lambda c: (c.numero, c.id)
        )
        for caja in cajas_ordenadas:
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

- [ ] **Step 2: Correr los tests nuevos y verificar que pasan**

Run:
```bash
pytest tests/test_pedido_a_json.py -v
```

Expected: Ambos tests pasan (`PASSED` cada uno).

- [ ] **Step 3: Correr la suite de facturación completa (regresión)**

Run:
```bash
pytest tests/test_facturacion.py tests/test_pedido_a_json.py -v
```

Expected: Todos los tests de `test_facturacion.py` siguen pasando (mockean N8N y no dependen del número de líneas en el payload). Los 2 tests nuevos pasan.

Nota: Si `test_facturacion.py` tenía fallos pre-existentes (ver commit `4fa3ec92` del 2026-04-19), esos mismos fallos pueden seguir apareciendo — no los introduce este cambio. Confirmar comparando con `git stash` (si es necesario, hacer `git stash` antes de la suite para correr en HEAD puro y comparar).

- [ ] **Step 4: Commit del fix**

```bash
git add app.py
git commit -m "fix(facturacion): emit one payload line per CajaPesada

Restore pre-0154c2b1 contract: pedido_a_json now emits one line per
weighed box instead of one aggregated line per DetallePedido. The N8N
workflow 'Generar Numero Factura' groups by (product_qbo_id, unit_price)
and accumulates each incoming qty in descriptions[], which becomes
Line.Description in the QBO invoice — so individual box weights are
visible again in the Description column.

Cero cambios en N8N; descripcion sigue llevando el nombre del producto
para preservar el class detection por keywords del workflow.

Spec: docs/superpowers/specs/2026-04-22-restaurar-pesos-cajas-qbo-description-design.md

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 4: Deploy a Heroku y verificación en producción

**Context:** `git push origin main` auto-despliega a Heroku (ver `MEMORY.md`). Después confirmamos con una factura real que los pesos aparecen en Description.

**Files:** Ninguno (solo comandos).

- [ ] **Step 1: Push a main**

Run:
```bash
git push origin main
```

Expected: Push exitoso. Heroku detecta el deploy y empieza el build (tarda ~1-2 min).

- [ ] **Step 2: Esperar y monitorear el deploy de Heroku**

Run:
```bash
heroku releases --app pesosapp | head -5
```

Expected: El release más reciente corresponde al commit recién hecho, con `state=succeeded`. Si `state=failed`, leer logs con `heroku logs --tail --app pesosapp`.

- [ ] **Step 3: Verificación funcional con factura real**

Paso manual (coordinar con el usuario):

1. Abrir la app en `https://pesosapp-caa46963237c.herokuapp.com`.
2. Tomar un pedido existente en estado `preparado` con ≥1 producto pesable
   que tenga ≥3 cajas pesadas con pesos distintos (o crear uno de prueba).
3. Facturar el pedido desde el listado de pedidos.
4. Abrir la factura generada en QuickBooks Online.
5. Confirmar que, para cada línea con producto pesable, la columna
   **Description** muestra los pesos individuales separados por tab
   (ej. `2.50   3.10   2.80   3.20   2.95`).
6. Confirmar que:
   - El **Qty** de la línea es la suma de esos pesos.
   - El **Amount** es `Qty × Unit Price`.
   - El **total** de la factura coincide con el total mostrado en el app.
   - La línea tiene la **Class** correcta asignada (Cocidos y Ahumados,
     Atún Van Camps, etc.).

Si falla cualquiera de esas verificaciones, revisar logs de Heroku y del
workflow N8N, y abrir un task de debugging antes de marcar el plan como
completado.

---

## Task 5: (Opcional) Limpiar stash descartado

**Context:** El stash creado en Task 1 contenía el intento fallido previo. Una vez verificado que el fix real funciona en producción, el stash puede borrarse para mantener la lista limpia.

**Files:** Ninguno.

- [ ] **Step 1: Listar stashes**

Run:
```bash
git stash list
```

Expected: Ver el stash `intento previo pesos cajas qbo (descartado, ver plan 2026-04-22)` en la lista.

- [ ] **Step 2: Borrar el stash**

Run:
```bash
git stash drop <stash-ref>
```

Donde `<stash-ref>` es `stash@{N}` correspondiente al intento previo. Expected: `Dropped stash@{N} (<hash>)`.

Si el usuario prefiere conservar el stash "por si acaso", omitir este task.

---

## Notas finales

- **No tocamos N8N.** Todo el fix es del lado de la app.
- **El primer commit queda atómico** (un solo `app.py` editado) y el test fallido queda en su propio commit previo — así el historial cuenta la historia del bug + fix en dos pasos legibles.
- **No se agrega nada al payload** que no existiera antes de `0154c2b1`. Es una restauración exacta del contrato previo.
