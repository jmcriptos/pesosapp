# Ajustes al Registro de Limpieza — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Agregar al registro de limpieza (FR-HACCP-LIMP-01) los campos ppm, "Verificó" (verificación independiente) y método de verificación, con sus reglas de validación, y sembrar el catálogo oficial de áreas/productos.

**Architecture:** Tres columnas nuevas en `RegistroLimpieza` (auto-migradas vía `_ensure_haccp_columns`), un seed idempotente del catálogo, validación de servidor en `limpieza_registrar` espejada por JS en el bottom-sheet, y propagación a Historial/PDF/Excel. Modelos y rutas viven todos en `app.py`; el sheet en `templates/registros/limpieza.html`.

**Tech Stack:** Flask, SQLAlchemy, Jinja2, JS vanilla inline, ReportLab (PDF), pytest. CSS en `static/css/operaciones.css` (servido directo, sin minificar).

---

## File Structure

- `app.py`
  - Modelo `RegistroLimpieza` (~línea 2345): +3 columnas, +1 relación, fix `foreign_keys`.
  - `_ensure_haccp_columns` (~línea 182): +3 columnas al dict `wanted`.
  - Nuevo: constantes de catálogo + `_seed_catalogo_limpieza()` (junto a `_ensure_haccp_columns`, ~línea 198).
  - Bloque de arranque (~línea 10454): llamar al seed.
  - `limpieza_index` (~línea 10019): pasar `vendedores` y `operador_id` al template.
  - `limpieza_registrar` (~línea 10076): validación ppm/verificó/método + persistencia.
  - `_build_limpieza_pdf` (~línea 10295): columnas ppm + Verificó, método en detalle.
  - `limpieza_export` excel (~línea 10410): columnas nuevas.
- `templates/registros/limpieza.html`: campos en el sheet + JS de gating.
- `templates/registros/limpieza_historial.html`: columnas ppm + Verificó.
- `static/css/operaciones.css`: estilo del hint de rango ppm.
- `tests/test_registro_limpieza.py`: tests nuevos + actualizar los que postean a `/registrar`.

---

## Task 1: Modelo de datos y migración

**Files:**
- Modify: `app.py` (modelo `RegistroLimpieza` ~2361-2364; `_ensure_haccp_columns` ~185)
- Test: `tests/test_registro_limpieza.py`

- [ ] **Step 1: Escribir el test que falla**

Añadir al final de `tests/test_registro_limpieza.py`:

```python
def test_registro_campos_haccp(app):
    from app import RegistroLimpieza
    with app.app_context():
        r = RegistroLimpieza(area_id=IDS['area'], registrado_por=IDS['vend'],
                             verificado_por=IDS['admin'], conforme=True,
                             concentracion_ppm=250, metodo_verificacion='visual')
        _db.session.add(r)
        _db.session.commit()
        got = _db.session.get(RegistroLimpieza, r.id)
        assert got.concentracion_ppm == 250
        assert got.metodo_verificacion == 'visual'
        assert got.verificado_por_vendedor.nombre_completo == 'Admin'
        assert got.registrado_por_vendedor.nombre_completo == 'Vend'
```

- [ ] **Step 2: Correr el test y verque falla**

Run: `python -m pytest tests/test_registro_limpieza.py::test_registro_campos_haccp -v`
Expected: FAIL — `AttributeError`/`TypeError` (columnas/relación inexistentes).

- [ ] **Step 3: Agregar columnas y relación al modelo**

En `app.py`, en `RegistroLimpieza`, reemplazar el bloque de la firma + relaciones
(actualmente líneas ~2361-2364):

```python
    firma_png = db.Column(db.Text, nullable=True)  # data URL PNG de la firma del responsable
    # Ajustes auditoría de inocuidad (FR-HACCP-LIMP-01):
    concentracion_ppm = db.Column(db.Integer, nullable=True)   # ppm de Sani-T-10 Plus
    verificado_por = db.Column(db.Integer, db.ForeignKey('vendedor.id'), nullable=True)
    metodo_verificacion = db.Column(db.String(20), nullable=True)  # visual|atp|hisopado

    area = db.relationship('AreaLimpieza')
    # Dos FKs a vendedor -> foreign_keys explícito en ambas relaciones.
    registrado_por_vendedor = db.relationship('Vendedor', foreign_keys=[registrado_por])
    verificado_por_vendedor = db.relationship('Vendedor', foreign_keys=[verificado_por])
```

- [ ] **Step 4: Agregar columnas al auto-migrador**

En `app.py`, en `_ensure_haccp_columns`, reemplazar la línea del dict `wanted` para
`registro_limpieza` (actualmente línea ~185):

```python
            'registro_limpieza': [('firma_png', 'TEXT'), ('concentracion_ppm', 'INTEGER'),
                                  ('verificado_por', 'INTEGER'), ('metodo_verificacion', 'VARCHAR(20)')],
```

- [ ] **Step 5: Correr el test y verificar que pasa**

Run: `python -m pytest tests/test_registro_limpieza.py::test_registro_campos_haccp -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add app.py tests/test_registro_limpieza.py
git commit -m "Limpieza: columnas ppm, verificado_por y metodo_verificacion"
```

---

## Task 2: Seed idempotente del catálogo

**Files:**
- Modify: `app.py` (constantes + `_seed_catalogo_limpieza` ~tras línea 197; llamada en arranque ~10454)
- Test: `tests/test_registro_limpieza.py`

- [ ] **Step 1: Escribir el test que falla**

Añadir a `tests/test_registro_limpieza.py`:

```python
def test_seed_catalogo_idempotente(app):
    from app import _seed_catalogo_limpieza, ProductoLimpieza, AreaLimpieza
    with app.app_context():
        _seed_catalogo_limpieza()
        _seed_catalogo_limpieza()  # segunda corrida no duplica
        assert ProductoLimpieza.query.filter_by(nombre='Sani-T-10 Plus').count() == 1
        assert ProductoLimpieza.query.filter_by(nombre='Big Punch').count() == 1
        eq = AreaLimpieza.query.filter_by(nombre='Embutidora Vemag').first()
        assert eq is not None and eq.tipo == 'equipo'
        assert eq.sanitizante.nombre == 'Sani-T-10 Plus'
        esp = AreaLimpieza.query.filter_by(nombre='Almacenes').first()
        assert esp is not None and esp.tipo == 'espacio'
        assert esp.sanitizante_id is None
```

- [ ] **Step 2: Correr el test y verificar que falla**

Run: `python -m pytest tests/test_registro_limpieza.py::test_seed_catalogo_idempotente -v`
Expected: FAIL — `ImportError: cannot import name '_seed_catalogo_limpieza'`.

- [ ] **Step 3: Implementar el seed**

En `app.py`, justo después de `_ensure_haccp_columns` (antes de
`N8N_HACCP_ALERT_WEBHOOK_URL`, ~línea 199), insertar:

```python
# Catálogo oficial del programa de limpieza (PG-HACCP-LIMP-01).
_CAT_LIMP_DETERGENTES = ['Big Punch', 'POOFF']
_CAT_LIMP_SANITIZANTE = 'Sani-T-10 Plus'
_CAT_LIMP_EQUIPOS = ['Tanque de salmueras', 'Inyectadora Inject Star', 'Embutidora Vemag',
                     'Molino Torrey', 'Rebanadora Icone 700', 'Mezclador MPR 400',
                     'Horno Ahumador', 'Carros para horno']
_CAT_LIMP_ESPACIOS = ['Sala de Producción', 'Sala de Mezclado', 'Sala de Cocción y Ahumado',
                      'Almacenes', 'Pisos y drenajes', 'Camión de reparto']


def _seed_catalogo_limpieza():
    """Crea (idempotente) productos y áreas oficiales del programa de limpieza.
    No borra ni desactiva nada. A los equipos creados aquí les asigna Sani-T-10 Plus
    como sanitizante (activa el gate de ppm). Seguro de correr en cada arranque."""
    try:
        from sqlalchemy import inspect as _sa_inspect, func as _sa_func
        insp = _sa_inspect(db.engine)
        tables = set(insp.get_table_names())
        if 'producto_limpieza' not in tables or 'area_limpieza' not in tables:
            return

        def _get_or_create_producto(nombre):
            p = (ProductoLimpieza.query
                 .filter(_sa_func.lower(ProductoLimpieza.nombre) == nombre.lower()).first())
            if p is None:
                p = ProductoLimpieza(nombre=nombre, dilucion='Según ficha técnica', activo=True)
                db.session.add(p)
                db.session.flush()
            return p

        for nombre in _CAT_LIMP_DETERGENTES:
            _get_or_create_producto(nombre)
        sani = _get_or_create_producto(_CAT_LIMP_SANITIZANTE)

        def _ensure_area(nombre, tipo, sanitizante_id=None):
            existe = (AreaLimpieza.query
                      .filter(_sa_func.lower(AreaLimpieza.nombre) == nombre.lower()).first())
            if existe is None:
                db.session.add(AreaLimpieza(nombre=nombre, tipo=tipo,
                                            sanitizante_id=sanitizante_id, activa=True))

        for nombre in _CAT_LIMP_EQUIPOS:
            _ensure_area(nombre, 'equipo', sanitizante_id=sani.id)
        for nombre in _CAT_LIMP_ESPACIOS:
            _ensure_area(nombre, 'espacio')
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        app.logger.warning(f'[HACCP] no se pudo sembrar catálogo de limpieza: {e}')
```

- [ ] **Step 4: Llamar al seed en el arranque**

En `app.py`, en el bloque de arranque (~línea 10454), reemplazar:

```python
with app.app_context():
    _ensure_haccp_columns()
```

por:

```python
with app.app_context():
    _ensure_haccp_columns()
    _seed_catalogo_limpieza()
```

- [ ] **Step 5: Correr el test y verificar que pasa**

Run: `python -m pytest tests/test_registro_limpieza.py::test_seed_catalogo_idempotente -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add app.py tests/test_registro_limpieza.py
git commit -m "Limpieza: seed idempotente del catálogo oficial (areas y productos)"
```

---

## Task 3: Validación de servidor en `limpieza_registrar`

**Files:**
- Modify: `app.py` (`limpieza_registrar` ~10076-10123)
- Test: `tests/test_registro_limpieza.py` (tests nuevos + actualizar existentes)

- [ ] **Step 1: Actualizar tests existentes que postean a `/registrar`**

`verificado_por` pasa a ser obligatorio, así que los posts existentes deben incluirlo
(operador = 'vend', verificador = admin → distintos). En
`tests/test_registro_limpieza.py`, editar estos cuatro `data={...}`:

- `test_registrar_conforme`:
```python
                  data={'area_id': IDS['area'], 'conforme': 'si',
                        'verificado_por': IDS['admin']}, follow_redirects=True)
```
- `test_registrar_no_conforme_con_accion`:
```python
           data={'area_id': IDS['area'], 'conforme': 'no',
                 'verificado_por': IDS['admin'],
                 'accion_tomada': 'Se volvio a limpiar',
                 'accion_disposicion': 'Quedo conforme'}, follow_redirects=True)
```
- `test_historial_lista_registros`:
```python
           data={'area_id': IDS['area'], 'conforme': 'si',
                 'verificado_por': IDS['admin']}, follow_redirects=True)
```
- `test_export_devuelve_pdf`:
```python
           data={'area_id': IDS['area'], 'conforme': 'si',
                 'verificado_por': IDS['admin']}, follow_redirects=True)
```

`test_registrar_no_conforme_sin_accion_rechazado` se deja igual (sigue debiendo rechazar).

- [ ] **Step 2: Escribir los tests nuevos que fallan**

Añadir a `tests/test_registro_limpieza.py`. Usan un área con sanitizante creada en el test:

```python
def _crear_area_con_sani(app):
    from app import AreaLimpieza, ProductoLimpieza
    with app.app_context():
        sani = ProductoLimpieza(nombre='Sani-T-10 Plus', dilucion='Según ficha técnica', activo=True)
        _db.session.add(sani)
        _db.session.flush()
        a = AreaLimpieza(nombre='Mesa con sani', tipo='equipo',
                         sanitizante_id=sani.id, activa=True)
        _db.session.add(a)
        _db.session.commit()
        return a.id


def test_registrar_verifico_obligatorio(app):
    from app import RegistroLimpieza
    c = _login(app, 'vend')
    c.post('/registros/limpieza/registrar',
           data={'area_id': IDS['area'], 'conforme': 'si'}, follow_redirects=True)
    with app.app_context():
        assert RegistroLimpieza.query.filter_by(area_id=IDS['area']).count() == 0


def test_registrar_verifico_distinto_operador(app):
    from app import RegistroLimpieza
    c = _login(app, 'vend')  # operador = vend
    c.post('/registros/limpieza/registrar',
           data={'area_id': IDS['area'], 'conforme': 'si',
                 'verificado_por': IDS['vend']}, follow_redirects=True)
    with app.app_context():
        assert RegistroLimpieza.query.filter_by(area_id=IDS['area']).count() == 0


def test_registrar_ppm_obligatorio_con_sanitizante(app):
    from app import RegistroLimpieza
    area_id = _crear_area_con_sani(app)
    c = _login(app, 'vend')
    c.post('/registros/limpieza/registrar',
           data={'area_id': area_id, 'conforme': 'si',
                 'verificado_por': IDS['admin']}, follow_redirects=True)
    with app.app_context():
        assert RegistroLimpieza.query.filter_by(area_id=area_id).count() == 0


def test_registrar_ppm_fuera_rango_bloquea_conforme(app):
    from app import RegistroLimpieza
    area_id = _crear_area_con_sani(app)
    c = _login(app, 'vend')
    c.post('/registros/limpieza/registrar',
           data={'area_id': area_id, 'conforme': 'si', 'concentracion_ppm': '120',
                 'verificado_por': IDS['admin']}, follow_redirects=True)
    with app.app_context():
        assert RegistroLimpieza.query.filter_by(area_id=area_id).count() == 0


def test_registrar_ppm_en_rango_conforme_ok(app):
    from app import RegistroLimpieza
    area_id = _crear_area_con_sani(app)
    c = _login(app, 'vend')
    c.post('/registros/limpieza/registrar',
           data={'area_id': area_id, 'conforme': 'si', 'concentracion_ppm': '250',
                 'verificado_por': IDS['admin'], 'metodo_verificacion': 'visual'},
           follow_redirects=True)
    with app.app_context():
        r = RegistroLimpieza.query.filter_by(area_id=area_id).first()
        assert r is not None
        assert r.concentracion_ppm == 250
        assert r.verificado_por == IDS['admin']
        assert r.metodo_verificacion == 'visual'


def test_registrar_ppm_fuera_rango_permitido_si_no_conforme(app):
    from app import RegistroLimpieza
    area_id = _crear_area_con_sani(app)
    c = _login(app, 'vend')
    c.post('/registros/limpieza/registrar',
           data={'area_id': area_id, 'conforme': 'no', 'concentracion_ppm': '120',
                 'verificado_por': IDS['admin'],
                 'accion_tomada': 'Se reajustó la dilución',
                 'accion_disposicion': 'Se volvió a medir'}, follow_redirects=True)
    with app.app_context():
        r = RegistroLimpieza.query.filter_by(area_id=area_id).first()
        assert r is not None
        assert r.conforme is False
        assert r.concentracion_ppm == 120
```

- [ ] **Step 3: Correr los tests y verificar que fallan**

Run: `python -m pytest tests/test_registro_limpieza.py -k "verifico or ppm" -v`
Expected: FAIL (la validación aún no existe; los registros se crean igual).

- [ ] **Step 4: Implementar la validación**

En `app.py`, en `limpieza_registrar`, reemplazar el bloque desde la validación de
no-conforme hasta justo antes de `firma = ...` (actualmente líneas ~10091-10095):

```python
    if not conforme and (not tomada or not disposicion):
        flash(f'El registro de {area.nombre} es No conforme. Indica al menos la acción tomada '
              f'y la disposición.', 'danger')
        return redirect(url_for('limpieza_index'))
```

por:

```python
    if not conforme and (not tomada or not disposicion):
        flash(f'El registro de {area.nombre} es No conforme. Indica al menos la acción tomada '
              f'y la disposición.', 'danger')
        return redirect(url_for('limpieza_index'))

    # Concentración (ppm): obligatoria solo si el área tiene sanitizante.
    ppm_raw = (request.form.get('concentracion_ppm') or '').strip()
    ppm = None
    if ppm_raw:
        try:
            ppm = int(ppm_raw)
        except ValueError:
            flash('La concentración (ppm) debe ser un número entero.', 'danger')
            return redirect(url_for('limpieza_index'))
    requiere_ppm = area.sanitizante_id is not None
    if requiere_ppm and ppm is None:
        flash(f'Indica la concentración (ppm) de Sani-T-10 Plus para {area.nombre}.', 'danger')
        return redirect(url_for('limpieza_index'))
    if requiere_ppm and conforme and (ppm < 150 or ppm > 400):
        flash(f'ppm fuera de rango (150–400) en {area.nombre}: corrige y vuelve a medir, '
              f'o marca No conforme.', 'danger')
        return redirect(url_for('limpieza_index'))

    # Verificación independiente: persona distinta del operador.
    operador_id = current_user.id if isinstance(current_user, Vendedor) else None
    verificado_por_id = request.form.get('verificado_por', type=int)
    verificador = (Vendedor.query.filter_by(id=verificado_por_id, activo=True).first()
                   if verificado_por_id else None)
    if verificador is None:
        flash('Selecciona quién verificó la limpieza (persona distinta del operador).', 'danger')
        return redirect(url_for('limpieza_index'))
    if operador_id is not None and verificador.id == operador_id:
        flash('La verificación debe hacerla una persona distinta del operador.', 'danger')
        return redirect(url_for('limpieza_index'))

    # Método de verificación (opcional): visual | atp | hisopado.
    metodo = (request.form.get('metodo_verificacion') or '').strip().lower()
    if metodo not in ('visual', 'atp', 'hisopado'):
        metodo = None
```

Luego, en la construcción del `RegistroLimpieza` (actualmente líneas ~10101-10111),
añadir los tres campos nuevos al final de los kwargs:

```python
    registro = RegistroLimpieza(
        area_id=area.id,
        registrado_por=current_user.id if isinstance(current_user, Vendedor) else None,
        conforme=conforme,
        observacion=observacion,
        firma_png=firma,
        accion_causa=(causa or None) if not conforme else None,
        accion_tomada=(tomada or None) if not conforme else None,
        accion_responsable=(responsable or None) if not conforme else None,
        accion_disposicion=(disposicion or None) if not conforme else None,
        concentracion_ppm=ppm,
        verificado_por=verificador.id,
        metodo_verificacion=metodo,
    )
```

Finalmente, incluir el ppm en la alerta de no-conforme. Reemplazar (actualmente ~10116-10118):

```python
    if not conforme:
        _haccp_alerta('clean', f'{area.nombre}: limpieza no conforme',
                      observacion or 'Registro marcado no conforme', tomada)
```

por:

```python
    if not conforme:
        detalle_ppm = f' · ppm={ppm}' if ppm is not None else ''
        _haccp_alerta('clean', f'{area.nombre}: limpieza no conforme',
                      (observacion or 'Registro marcado no conforme') + detalle_ppm, tomada)
```

- [ ] **Step 5: Correr la suite de limpieza completa y verificar que pasa**

Run: `python -m pytest tests/test_registro_limpieza.py -v`
Expected: PASS (tests nuevos + los actualizados + los preexistentes).

- [ ] **Step 6: Commit**

```bash
git add app.py tests/test_registro_limpieza.py
git commit -m "Limpieza: validación ppm (gate 150-400), verificó independiente y método"
```

---

## Task 4: UI del bottom-sheet (campos + gating JS)

**Files:**
- Modify: `app.py` (`limpieza_index` ~10066-10073)
- Modify: `templates/registros/limpieza.html` (form ~157-202; JS ~291-374)
- Modify: `static/css/operaciones.css`
- Test: `tests/test_registro_limpieza.py`

- [ ] **Step 1: Escribir el test que falla**

Añadir a `tests/test_registro_limpieza.py`:

```python
def test_index_sheet_tiene_campos_nuevos(app):
    c = _login(app, 'vend')
    body = c.get('/registros/limpieza').data.decode('utf-8')
    assert 'name="verificado_por"' in body
    assert 'name="concentracion_ppm"' in body
    assert 'name="metodo_verificacion"' in body
```

- [ ] **Step 2: Correr el test y verificar que falla**

Run: `python -m pytest tests/test_registro_limpieza.py::test_index_sheet_tiene_campos_nuevos -v`
Expected: FAIL (los campos aún no están en el template).

- [ ] **Step 3: Pasar `vendedores` y `operador_id` al template**

En `app.py`, en `limpieza_index`, justo antes del `return render_template(...)`
(actualmente ~10066), añadir:

```python
    vendedores = (Vendedor.query.filter_by(activo=True)
                  .order_by(Vendedor.nombre_completo).all())
    operador_id = current_user.id if isinstance(current_user, Vendedor) else None
```

y agregar ambos al `render_template`:

```python
    return render_template('registros/limpieza.html', areas=areas,
                           registros_info=registros_info,
                           con_registro_hoy=con_registro_hoy,
                           cumplimiento=cumplimiento,
                           cumplimiento_prom=cumplimiento_prom,
                           hoy=hoy, ahora_local=ahora_local, es_admin=es_admin,
                           vendedores=vendedores, operador_id=operador_id)
```

- [ ] **Step 4: Agregar los campos al sheet**

En `templates/registros/limpieza.html`, dentro de `#firmaForm`, insertar tras el bloque
de "Fecha y hora" (después de la línea ~166 `</div>` que cierra `.ops-when`) y antes del
comentario `<!-- Ficha SSOP ... -->`:

```html
      <!-- Concentración ppm (solo si el área usa sanitizante) -->
      <div class="ops-field ops-ppm-field" id="firmaPpmField" hidden style="margin-bottom:12px">
        <label>Concentración Sani-T-10 Plus (ppm) *</label>
        <input type="number" name="concentracion_ppm" id="firmaPpm"
               inputmode="numeric" min="0" step="1" placeholder="150–400">
        <div class="ops-ppm-hint" id="firmaPpmHint"></div>
      </div>

      <!-- Verificación independiente -->
      <div class="ops-field" style="margin-bottom:12px">
        <label>Verificó (otra persona) *</label>
        <select name="verificado_por" id="firmaVerifico" required>
          <option value="">Selecciona…</option>
          {% for v in vendedores %}{% if not (operador_id and v.id == operador_id) %}
          <option value="{{ v.id }}">{{ v.nombre_completo or v.username }}</option>
          {% endif %}{% endfor %}
        </select>
      </div>

      <!-- Método de verificación (recomendado) -->
      <div class="ops-field" style="margin-bottom:12px">
        <label>Método de verificación</label>
        <select name="metodo_verificacion" id="firmaMetodo">
          <option value="">—</option>
          <option value="visual">Visual</option>
          <option value="atp">ATP</option>
          <option value="hisopado">Hisopado</option>
        </select>
      </div>
```

- [ ] **Step 5: Extender el gating JS**

En `templates/registros/limpieza.html`, en el `<script>`, reemplazar la función
`updateConfirm` (actualmente línea ~297):

```javascript
  function updateConfirm() { confirmBtn.disabled = !(hasSign && correctiveValid()); }
```

por (añade refs y validadores de ppm + verificador):

```javascript
  var ppmField = document.getElementById('firmaPpmField');
  var ppmInput = document.getElementById('firmaPpm');
  var ppmHint = document.getElementById('firmaPpmHint');
  var verifico = document.getElementById('firmaVerifico');

  function ppmValid() {
    if (ppmField.hidden) return true;            // área sin sanitizante
    var raw = ppmInput.value.trim();
    if (raw === '') { return conformeInput.value === 'no'; }
    var n = parseInt(raw, 10);
    if (isNaN(n)) return false;
    if (conformeInput.value === 'no') return true;  // no conforme documenta el desvío
    return n >= 150 && n <= 400;
  }
  function renderPpmHint() {
    if (ppmField.hidden) { ppmHint.textContent = ''; return; }
    var raw = ppmInput.value.trim();
    if (raw === '') { ppmHint.textContent = 'Mide con tira reactiva (150–400 ppm).'; ppmHint.className = 'ops-ppm-hint'; return; }
    var n = parseInt(raw, 10);
    if (!isNaN(n) && n >= 150 && n <= 400) { ppmHint.textContent = 'En rango ✓'; ppmHint.className = 'ops-ppm-hint is-ok'; }
    else { ppmHint.textContent = 'Fuera de rango (150–400): corrige y vuelve a medir, o marca No conforme.'; ppmHint.className = 'ops-ppm-hint is-bad'; }
  }
  function verifierValid() { return !!verifico.value; }

  function updateConfirm() {
    renderPpmHint();
    confirmBtn.disabled = !(hasSign && correctiveValid() && ppmValid() && verifierValid());
  }
  ppmInput.addEventListener('input', updateConfirm);
  verifico.addEventListener('change', updateConfirm);
```

- [ ] **Step 6: Mostrar/ocultar ppm al abrir el sheet**

En `templates/registros/limpieza.html`, dentro de `openFirma`, en la sección `// reset`
(actualmente ~339-341), añadir tras `corrective.hidden = true;`:

```javascript
    // ppm visible solo si el área tiene sanitizante (data-area-sani presente).
    ppmField.hidden = !btn.dataset.areaSani;
```

(El `form.reset()` ya limpia ppm/verificó/método; `setupCanvas(); clearSign();` al final
dispara `updateConfirm` vía `clearSign`.)

- [ ] **Step 7: Bloquear el submit si ppm/verificó inválidos**

En `templates/registros/limpieza.html`, en el handler de `submit` (actualmente ~362-363),
reemplazar:

```javascript
    if (!hasSign || !correctiveValid()) { e.preventDefault(); return; }
```

por:

```javascript
    if (!hasSign || !correctiveValid() || !ppmValid() || !verifierValid()) { e.preventDefault(); return; }
```

- [ ] **Step 8: Estilo del hint ppm**

En `static/css/operaciones.css`, al final del archivo, añadir:

```css
.ops-ppm-hint { margin-top: 6px; font-size: 12px; color: #94a3b8; }
.ops-ppm-hint.is-ok { color: #16a34a; }
.ops-ppm-hint.is-bad { color: #ef4444; }
```

- [ ] **Step 9: Correr el test y verificar que pasa**

Run: `python -m pytest tests/test_registro_limpieza.py::test_index_sheet_tiene_campos_nuevos -v`
Expected: PASS

- [ ] **Step 10: Verificación visual en el navegador**

Levantar el preview, abrir `/registros/limpieza`, abrir el sheet de un equipo con
sanitizante: debe verse el campo ppm con hint, el select "Verificó" sin el operador, y
el botón Confirmar deshabilitado hasta firma + ppm en rango + verificador. En un espacio
sin sanitizante el campo ppm no aparece. (Workflow de preview_*.)

- [ ] **Step 11: Commit**

```bash
git add app.py templates/registros/limpieza.html static/css/operaciones.css tests/test_registro_limpieza.py
git commit -m "Limpieza: campos ppm/verificó/método en el sheet con gating de confirmación"
```

---

## Task 5: Propagación a Historial, PDF y Excel

**Files:**
- Modify: `templates/registros/limpieza_historial.html` (~66-75)
- Modify: `app.py` (`_build_limpieza_pdf` ~10335-10364; `limpieza_export` excel ~10411-10420)
- Test: `tests/test_registro_limpieza.py`

- [ ] **Step 1: Escribir el test que falla**

Añadir a `tests/test_registro_limpieza.py` (registra con ppm y verifica que aparece en el historial):

```python
def test_historial_muestra_ppm_y_verifico(app):
    area_id = _crear_area_con_sani(app)
    c = _login(app, 'vend')
    c.post('/registros/limpieza/registrar',
           data={'area_id': area_id, 'conforme': 'si', 'concentracion_ppm': '250',
                 'verificado_por': IDS['admin']}, follow_redirects=True)
    body = c.get('/registros/limpieza/historial').data.decode('utf-8')
    assert '250' in body          # ppm
    assert 'Admin' in body        # verificó
```

- [ ] **Step 2: Correr el test y verificar que falla**

Run: `python -m pytest tests/test_registro_limpieza.py::test_historial_muestra_ppm_y_verifico -v`
Expected: FAIL (la columna Verificó/ppm aún no se renderiza; "Admin" no aparece como verificador).

- [ ] **Step 3: Añadir columnas al historial**

En `templates/registros/limpieza_historial.html`, reemplazar el `ops-thead`
(actualmente línea ~66):

```html
        <div class="ops-thead"><div>Fecha · Hora</div><div>Tarea</div><div>Proceso</div><div>Responsable</div><div style="text-align:right">Estado</div></div>
```

por (agrega ppm y Verificó):

```html
        <div class="ops-thead"><div>Fecha · Hora</div><div>Tarea</div><div>ppm</div><div>Responsable</div><div>Verificó</div><div style="text-align:right">Estado</div></div>
```

y reemplazar la fila (actualmente líneas ~69-75) por:

```html
        <div class="ops-trow {{ 'is-bad' if not r.conforme }}" data-resp="{{ resp }}">
          <div class="ops-cell-muted ops-cell-mono">{{ r.registrado_en | hora_local('%d/%m · %H:%M') }}</div>
          <div class="ops-cell-strong">{{ r.area.nombre }}</div>
          <div class="ops-cell-muted ops-cell-mono">{{ r.concentracion_ppm if r.concentracion_ppm is not none else '—' }}</div>
          <div class="ops-cell-muted">{{ resp }}{% if r.firma_png %} <img src="{{ r.firma_png }}" alt="firma" style="height:20px;vertical-align:middle;margin-left:6px;border-radius:3px;background:#fff;border:1px solid var(--color-border-subtle)">{% endif %}</div>
          <div class="ops-cell-muted">{{ r.verificado_por_vendedor.nombre_completo if r.verificado_por_vendedor else '—' }}</div>
          <div class="ops-cell-right">{% if r.conforme %}<span class="estado-chip ok"><i class="fas fa-pen-nib"></i> Firmada</span>{% else %}<span class="estado-chip bad"><i class="fas fa-triangle-exclamation"></i> No conforme</span>{% endif %}</div>
        </div>
```

Nota: el `ops-thead`/`ops-trow` usan grid; el número de columnas se define en
`static/css/operaciones.css`. Verificar la regla `grid-template-columns` de `.ops-thead`
y `.ops-trow` en el contexto del historial y ajustarla de 5 a 6 columnas si está fijada
ahí (buscar `grid-template-columns` cerca de las reglas `.ops-trow`).

- [ ] **Step 4: Añadir columnas al PDF**

En `app.py`, en `_build_limpieza_pdf`:

(a) Incluir el método en la línea de detalle. En `_detalle(r)`, tras la línea
`if r.observacion: bits.append(...)` (~10343), añadir:

```python
        if r.metodo_verificacion:
            bits.append(f'<b>Método verif.:</b> {_pdf_xe(r.metodo_verificacion.capitalize())}')
```

(b) Reemplazar el bloque de headers/aligns/widths + construcción de filas
(actualmente líneas ~10347-10363):

```python
    headers = ['Fecha/Hora', 'Área', 'Tipo', 'Producto', 'Resultado', 'Responsable']
    aligns = ['L', 'L', 'L', 'L', 'C', 'L']
    widths = [92, 150, 78, 168, 96, 196]
    filas = []
    for r in registros:
        filas.append({
            'cols': [
                _fmt_local(r.registrado_en),
                r.area.nombre if r.area else '—',
                'Equipo' if (r.area and r.area.tipo == 'equipo') else 'Espacio',
                _producto_proceso(r.area),
                'No conforme' if not r.conforme else 'Conforme',
                r.registrado_por_vendedor.nombre_completo if r.registrado_por_vendedor else '—',
            ],
            'desvio': not r.conforme,
            'detalle': _detalle(r),
        })
```

por (agrega columnas ppm y Verificó; ajusta anchos para landscape A4 ≈ 784 pt):

```python
    headers = ['Fecha/Hora', 'Área', 'Tipo', 'Producto', 'ppm', 'Resultado', 'Responsable', 'Verificó']
    aligns = ['L', 'L', 'L', 'L', 'C', 'C', 'L', 'L']
    widths = [80, 120, 55, 130, 40, 75, 122, 122]
    filas = []
    for r in registros:
        filas.append({
            'cols': [
                _fmt_local(r.registrado_en),
                r.area.nombre if r.area else '—',
                'Equipo' if (r.area and r.area.tipo == 'equipo') else 'Espacio',
                _producto_proceso(r.area),
                str(r.concentracion_ppm) if r.concentracion_ppm is not None else '—',
                'No conforme' if not r.conforme else 'Conforme',
                r.registrado_por_vendedor.nombre_completo if r.registrado_por_vendedor else '—',
                r.verificado_por_vendedor.nombre_completo if r.verificado_por_vendedor else '—',
            ],
            'desvio': not r.conforme,
            'detalle': _detalle(r),
        })
```

Nota: el `4` pasado a `_registro_pdf_tabla(headers, aligns, widths, 4, filas)`
(~línea 10364) es el índice de la columna de estado/resultado para el coloreado del
desvío; con la columna nueva "ppm" insertada antes de "Resultado", actualizarlo a `5`:

```python
    elements.append(_registro_pdf_tabla(headers, aligns, widths, 5, filas))
```

- [ ] **Step 5: Añadir columnas al Excel**

En `app.py`, en `limpieza_export` (rama excel), reemplazar `headers` y `rows`
(actualmente líneas ~10411-10420):

```python
        headers = ['Fecha', 'Hora', 'Área / tarea', 'Proceso (limpieza → sanitización)', 'Resultado', 'Registró', 'Observación',
                   'Causa', 'Acción tomada', 'Responsable acción', 'Disposición']
        rows = [[
            _fmt_local(r.registrado_en, '%Y-%m-%d'), _fmt_local(r.registrado_en, '%H:%M'),
            r.area.nombre if r.area else '', _producto_proceso(r.area),
            'Conforme' if r.conforme else 'No conforme',
            r.registrado_por_vendedor.nombre_completo if r.registrado_por_vendedor else '',
            r.observacion or '', r.accion_causa or '', r.accion_tomada or '',
            r.accion_responsable or '', r.accion_disposicion or '',
        ] for r in registros]
```

por:

```python
        headers = ['Fecha', 'Hora', 'Área / tarea', 'Proceso (limpieza → sanitización)', 'ppm', 'Resultado',
                   'Registró', 'Verificó', 'Método verif.', 'Observación',
                   'Causa', 'Acción tomada', 'Responsable acción', 'Disposición']
        rows = [[
            _fmt_local(r.registrado_en, '%Y-%m-%d'), _fmt_local(r.registrado_en, '%H:%M'),
            r.area.nombre if r.area else '', _producto_proceso(r.area),
            r.concentracion_ppm if r.concentracion_ppm is not None else '',
            'Conforme' if r.conforme else 'No conforme',
            r.registrado_por_vendedor.nombre_completo if r.registrado_por_vendedor else '',
            r.verificado_por_vendedor.nombre_completo if r.verificado_por_vendedor else '',
            (r.metodo_verificacion or '').capitalize(),
            r.observacion or '', r.accion_causa or '', r.accion_tomada or '',
            r.accion_responsable or '', r.accion_disposicion or '',
        ] for r in registros]
```

- [ ] **Step 6: Correr la suite completa y verificar que pasa**

Run: `python -m pytest tests/test_registro_limpieza.py -v`
Expected: PASS (incluye `test_historial_muestra_ppm_y_verifico` y `test_export_devuelve_pdf`).

- [ ] **Step 7: Verificación visual del historial y PDF**

En el preview, abrir `/registros/limpieza/historial`: deben verse las columnas ppm y
Verificó alineadas. Exportar el PDF y confirmar que las 8 columnas caben en landscape A4
sin desbordes y el método aparece en la línea de detalle.

- [ ] **Step 8: Commit**

```bash
git add app.py templates/registros/limpieza_historial.html tests/test_registro_limpieza.py
git commit -m "Limpieza: ppm/verificó/método en historial, PDF y Excel"
```

---

## Cierre

- [ ] **Correr toda la suite de tests del proyecto**

Run: `python -m pytest tests/ -q`
Expected: PASS (sin regresiones).

- [ ] **Recordatorio de despliegue**

`git push` a `main` auto-despliega a Heroku. En el primer arranque, `_ensure_haccp_columns`
crea las 3 columnas en Postgres y `_seed_catalogo_limpieza` crea productos/áreas faltantes
(idempotente). No requiere ALTER manual ni `flask db upgrade`.

---

## Self-Review (cobertura de la spec)

- §3 Concentración (ppm) → Task 1 (columna) + Task 3 (obligatorio si sanitizante, gate) + Task 4 (UI) + Task 5 (vistas). ✓
- §3 Verificó → Task 1 (columna+relación) + Task 3 (obligatorio, distinto) + Task 4 (select sin operador) + Task 5. ✓
- §3 Acción correctiva → ya existía; sin cambios. ✓
- §3 Método de verificación → Task 1 + Task 3 (validación opcional) + Task 4 (select) + Task 5 (detalle/columna). ✓
- §3 Tipo/frecuencia → fuera de alcance (ya cubierto por `frecuencia_texto`). ✓
- §4 Verificación independiente → Task 3 (verificador ≠ operador) + Task 4. ✓
- §4 ppm fuera de rango bloquea Conforme → Task 3 (servidor) + Task 4 (cliente). ✓
- §4 No conforme → acción correctiva → ya existía. ✓
- §4 Catálogo controlado → ya existía (select de áreas) + Task 2 (catálogo oficial). ✓
- §5 Catálogo de áreas/equipos → Task 2 (seed idempotente). ✓
- §6 Convención de códigos → ya en `LimpiezaConfig`/PDF; sin cambios. ✓
