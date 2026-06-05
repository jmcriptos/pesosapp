# Eliminar tareas y registros de limpieza — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Permitir borrar tareas del catálogo de limpieza (`AreaLimpieza`, solo si no tienen historial) y registros firmados del historial (`RegistroLimpieza`, solo admins), con confirmación y traza de auditoría.

**Architecture:** Dos rutas POST nuevas en `app.py` con permiso `registros:editar`, más botones de borrado (patrón `onsubmit="return confirm(...)"` ya usado en pedidos/clientes) en las plantillas de administración de áreas y de historial. Toda eliminación se audita con `_audit`.

**Tech Stack:** Flask, SQLAlchemy, Jinja2, pytest. Sin migraciones (no cambia el esquema).

---

## File Structure

- `app.py`
  - Nueva ruta `area_limpieza_eliminar` (junto a `area_limpieza_toggle`, ~línea 10053).
  - Nueva ruta `limpieza_registro_eliminar` (junto a `limpieza_registrar`/`limpieza_historial`).
- `templates/registros/areas_limpieza.html`: botón papelera por fila (celda de acciones, ~línea 72-80).
- `templates/registros/limpieza_historial.html`: botón papelera por fila (celda Estado), solo si `puede_verificar`.
- `tests/test_registro_limpieza.py`: tests de ambas rutas (éxito, bloqueo por historial, bloqueo por permiso).

---

## Task 1: Borrar tarea del catálogo (`AreaLimpieza`)

**Files:**
- Modify: `app.py` (nueva ruta tras `area_limpieza_toggle`, ~línea 10061)
- Modify: `templates/registros/areas_limpieza.html` (celda de acciones ~72-80)
- Test: `tests/test_registro_limpieza.py`

- [ ] **Step 1: Escribir los tests que fallan**

Añadir a `tests/test_registro_limpieza.py`:

```python
def test_area_eliminar_sin_registros(app):
    from app import AreaLimpieza
    c = _login(app, 'admin')
    with app.app_context():
        a = AreaLimpieza(nombre='Duplicado seed', tipo='equipo', activa=True)
        _db.session.add(a)
        _db.session.commit()
        aid = a.id
    c.post(f'/registros/limpieza/areas/{aid}/eliminar', follow_redirects=True)
    with app.app_context():
        assert _db.session.get(AreaLimpieza, aid) is None


def test_area_eliminar_con_registros_bloqueado(app):
    from app import AreaLimpieza, RegistroLimpieza
    c = _login(app, 'admin')
    with app.app_context():
        r = RegistroLimpieza(area_id=IDS['area'], registrado_por=IDS['admin'], conforme=True)
        _db.session.add(r)
        _db.session.commit()
    c.post(f'/registros/limpieza/areas/{IDS["area"]}/eliminar', follow_redirects=True)
    with app.app_context():
        assert _db.session.get(AreaLimpieza, IDS['area']) is not None


def test_area_eliminar_no_admin_bloqueado(app):
    from app import AreaLimpieza
    c = _login(app, 'vend')
    resp = c.post(f'/registros/limpieza/areas/{IDS["area"]}/eliminar', follow_redirects=False)
    assert resp.status_code in (302, 403)
    with app.app_context():
        assert _db.session.get(AreaLimpieza, IDS['area']) is not None
```

- [ ] **Step 2: Correr y verificar que fallan**

Run: `python -m pytest tests/test_registro_limpieza.py -k "area_eliminar" -v`
Expected: FAIL (404, la ruta no existe aún → los asserts de borrado/bloqueo fallan).

- [ ] **Step 3: Implementar la ruta**

En `app.py`, justo después de la función `area_limpieza_toggle` (que termina ~línea 10061),
insertar:

```python
@app.route('/registros/limpieza/areas/<int:area_id>/eliminar', methods=['POST'])
@login_required
@requiere_permiso_recurso('registros', 'editar')
def area_limpieza_eliminar(area_id):
    area = AreaLimpieza.query.get_or_404(area_id)
    n = RegistroLimpieza.query.filter_by(area_id=area_id).count()
    if n > 0:
        flash(f'La tarea «{area.nombre}» tiene {n} registro(s) en el historial; no se puede '
              f'borrar. Desactívala en su lugar.', 'danger')
        return redirect(url_for('areas_limpieza_list'))
    nombre = area.nombre
    db.session.delete(area)
    db.session.commit()
    _audit('config', 'Eliminó tarea de limpieza', nombre)
    flash('Tarea eliminada.', 'success')
    return redirect(url_for('areas_limpieza_list'))
```

- [ ] **Step 4: Correr y verificar que pasan**

Run: `python -m pytest tests/test_registro_limpieza.py -k "area_eliminar" -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Agregar el botón a la UI**

En `templates/registros/areas_limpieza.html`, en la celda de acciones, reemplazar el bloque
del toggle (actualmente líneas ~72-80) por el mismo bloque con el botón de borrado añadido
al final:

```html
          <div class="ops-cell-right" style="gap:6px">
            <button type="button" class="cam-edit js-area-edit" data-target="aedit-{{ a.id }}" title="Editar"><i class="fas fa-pen"></i></button>
            <form method="POST" action="{{ url_for('area_limpieza_toggle', area_id=a.id) }}">
              <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
              <button type="submit" class="cam-edit" title="{{ 'Activa' if a.activa else 'Inactiva' }}" style="color:{{ 'var(--color-success)' if a.activa else 'var(--color-text-subtle)' }} !important">
                <i class="fas {{ 'fa-circle-check' if a.activa else 'fa-circle' }}" style="font-size:18px"></i>
              </button>
            </form>
            <form method="POST" action="{{ url_for('area_limpieza_eliminar', area_id=a.id) }}"
                  onsubmit="return confirm('¿Eliminar la tarea «{{ a.nombre }}»? No se puede deshacer.')">
              <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
              <button type="submit" class="cam-edit" title="Eliminar" style="color:var(--color-danger) !important">
                <i class="fas fa-trash" style="font-size:15px"></i>
              </button>
            </form>
          </div>
```

- [ ] **Step 6: Verificar render del botón en el test de listado**

Add a quick assertion test to `tests/test_registro_limpieza.py`:

```python
def test_areas_list_muestra_boton_eliminar(app):
    c = _login(app, 'admin')
    body = c.get('/registros/limpieza/areas').data.decode('utf-8')
    assert 'area_limpieza_eliminar' in body or '/eliminar' in body
```

Run: `python -m pytest tests/test_registro_limpieza.py::test_areas_list_muestra_boton_eliminar -v`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add app.py templates/registros/areas_limpieza.html tests/test_registro_limpieza.py
git commit -m "Limpieza: eliminar tarea del catálogo (bloqueada si tiene historial)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 2: Borrar registro del historial (`RegistroLimpieza`)

**Files:**
- Modify: `app.py` (nueva ruta cerca de `limpieza_historial`)
- Modify: `templates/registros/limpieza_historial.html` (celda Estado de cada fila)
- Test: `tests/test_registro_limpieza.py`

- [ ] **Step 1: Escribir los tests que fallan**

Añadir a `tests/test_registro_limpieza.py`:

```python
def test_registro_historial_eliminar_admin(app):
    from app import RegistroLimpieza
    c = _login(app, 'admin')
    with app.app_context():
        r = RegistroLimpieza(area_id=IDS['area'], registrado_por=IDS['admin'], conforme=True)
        _db.session.add(r)
        _db.session.commit()
        rid = r.id
    c.post(f'/registros/limpieza/registro/{rid}/eliminar', follow_redirects=True)
    with app.app_context():
        assert _db.session.get(RegistroLimpieza, rid) is None


def test_registro_historial_eliminar_no_admin_bloqueado(app):
    from app import RegistroLimpieza
    c = _login(app, 'vend')
    with app.app_context():
        r = RegistroLimpieza(area_id=IDS['area'], registrado_por=IDS['vend'], conforme=True)
        _db.session.add(r)
        _db.session.commit()
        rid = r.id
    resp = c.post(f'/registros/limpieza/registro/{rid}/eliminar', follow_redirects=False)
    assert resp.status_code in (302, 403)
    with app.app_context():
        assert _db.session.get(RegistroLimpieza, rid) is not None
```

- [ ] **Step 2: Correr y verificar que fallan**

Run: `python -m pytest tests/test_registro_limpieza.py -k "registro_historial_eliminar" -v`
Expected: FAIL (404, ruta inexistente).

- [ ] **Step 3: Implementar la ruta**

En `app.py`, justo después de la función `limpieza_registrar` (antes de
`_revision_limpieza_que_cubre`), insertar:

```python
@app.route('/registros/limpieza/registro/<int:registro_id>/eliminar', methods=['POST'])
@login_required
@requiere_permiso_recurso('registros', 'editar')
def limpieza_registro_eliminar(registro_id):
    registro = RegistroLimpieza.query.get_or_404(registro_id)
    nombre = registro.area.nombre if registro.area else '—'
    cuando = _fmt_local(registro.registrado_en)
    db.session.delete(registro)
    db.session.commit()
    _audit('clean', 'Eliminó registro de limpieza', f'{nombre} · {cuando}')
    flash('Registro eliminado.', 'success')
    return redirect(request.referrer or url_for('limpieza_historial'))
```

- [ ] **Step 4: Correr y verificar que pasan**

Run: `python -m pytest tests/test_registro_limpieza.py -k "registro_historial_eliminar" -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Agregar el botón a la UI (solo admins)**

En `templates/registros/limpieza_historial.html`, reemplazar la celda de Estado de cada fila
(actualmente la línea que empieza con `<div class="ops-cell-right">{% if r.conforme %}`) por:

```html
          <div class="ops-cell-right" style="display:flex;align-items:center;justify-content:flex-end;gap:8px">
            {% if r.conforme %}<span class="estado-chip ok"><i class="fas fa-pen-nib"></i> Firmada</span>{% else %}<span class="estado-chip bad"><i class="fas fa-triangle-exclamation"></i> No conforme</span>{% endif %}
            {% if puede_verificar %}
            <form method="POST" action="{{ url_for('limpieza_registro_eliminar', registro_id=r.id) }}"
                  onsubmit="return confirm('¿Eliminar este registro de limpieza? No se puede deshacer.')">
              <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
              <button type="submit" class="cam-edit" title="Eliminar registro" style="color:var(--color-danger) !important">
                <i class="fas fa-trash" style="font-size:14px"></i>
              </button>
            </form>
            {% endif %}
          </div>
```

IMPORTANT: Read the current exact markup of that estado cell first (it was last edited in the ppm/Verificó change) and replace it precisely. The chip markup must be preserved as-is; only the wrapping `<div>` flex styles and the conditional delete form are added.

- [ ] **Step 6: Verificar que el botón aparece para admin y no para vend**

Add to `tests/test_registro_limpieza.py`:

```python
def test_historial_boton_eliminar_solo_admin(app):
    from app import RegistroLimpieza
    with app.app_context():
        r = RegistroLimpieza(area_id=IDS['area'], registrado_por=IDS['admin'], conforme=True)
        _db.session.add(r)
        _db.session.commit()
    admin_body = _login(app, 'admin').get('/registros/limpieza/historial').data.decode('utf-8')
    vend_body = _login(app, 'vend').get('/registros/limpieza/historial').data.decode('utf-8')
    assert 'limpieza_registro_eliminar' in admin_body or '/registro/' in admin_body
    assert 'Eliminar registro' in admin_body
    assert 'Eliminar registro' not in vend_body
```

Run: `python -m pytest tests/test_registro_limpieza.py::test_historial_boton_eliminar_solo_admin -v`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add app.py templates/registros/limpieza_historial.html tests/test_registro_limpieza.py
git commit -m "Limpieza: eliminar registro del historial (solo admins, con auditoría)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Cierre

- [ ] **Correr la suite de limpieza completa**

Run: `python -m pytest tests/test_registro_limpieza.py -q`
Expected: PASS (todos: nuevos + preexistentes).

- [ ] **Verificación visual (preview)**

Levantar el servidor con una BD sqlite sembrada, entrar como admin:
- En `/registros/limpieza/areas`: una tarea sin registros se borra; una con registros muestra
  el flash de bloqueo y sigue ahí.
- En `/registros/limpieza/historial`: el botón papelera aparece (admin), borra un registro
  con confirmación; como `vend` el botón no aparece.

---

## Self-Review (cobertura del spec)

- §3 Borrar tarea sin historial / bloquear con historial / permiso editar → Task 1 (ruta + 3 tests). ✓
- §3 UI botón papelera en áreas con confirm → Task 1 Step 5-6. ✓
- §4 Borrar registro, solo admins, auditoría, redirect con referrer → Task 2 (ruta + 2 tests). ✓
- §4 UI botón solo si `puede_verificar` → Task 2 Step 5-6. ✓
- §5 CSRF + permiso `registros:editar` + `_audit` → ambas rutas/forms. ✓
- §6 Tests enumerados → cubiertos por Task 1 y Task 2 (+2 de render). ✓
