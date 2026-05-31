# Registro de temperaturas de cámaras (HACCP) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Registrar temperaturas de cámaras de frío/congelación con responsable, hora y acción correctiva obligatoria fuera de rango, con historial y exportación a PDF para el inspector.

**Architecture:** Dos modelos nuevos en `app.py` (`Camara`, `LecturaTemperatura`); rutas bajo `/registros/temperaturas` (registrar/ver para cualquier usuario, administrar cámaras solo super_admin); plantillas mobile-first que extienden `base.html`; PDF tabular con reportlab Platypus servido inline en iOS reutilizando `_is_ios_request()` y `etiquetas_ios_share.js`.

**Tech Stack:** Flask, SQLAlchemy, Flask-Login, Jinja2, reportlab Platypus, pytest.

**Convenciones:** correr tests con `.venv311/bin/python -m pytest`. Modelos y rutas viven en `app.py`. `Decimal`, `datetime`, `date`, `func`, `Vendedor`, `db`, `requiere_rol`, `_is_ios_request` ya existen e importados. No hay `db.create_all()` al arranque (Flask-Migrate); las tablas nuevas se crean con `db.create_all()` (idempotente) — local en los tests vía fixture, y en producción en el paso de deploy (Task 6).

---

### Task 1: Modelos `Camara` y `LecturaTemperatura` (TDD)

**Files:**
- Test: `tests/test_registro_temperaturas.py` (crear)
- Modify: `app.py` (agregar los modelos después de la clase `CajaPesada`, antes de `class PedidoEvento`)

- [ ] **Step 1: Escribir el test que falla**

Crear `tests/test_registro_temperaturas.py`:

```python
"""Tests del registro de temperaturas de cámaras (HACCP)."""
import os
from decimal import Decimal

import pytest

os.environ.setdefault('SECRET_KEY', 'test-secret')
os.environ.setdefault('FLASK_ENV', 'testing')
os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')

from app import app as flask_app, db as _db

IDS = {}


@pytest.fixture
def app():
    flask_app.config.update(
        TESTING=True,
        WTF_CSRF_ENABLED=False,
        SQLALCHEMY_DATABASE_URI='sqlite:///:memory:',
    )
    with flask_app.app_context():
        _db.create_all()
        from app import Rol, Territorio, Vendedor, Camara
        rol_admin = Rol(nombre='super_admin', descripcion='Admin')
        rol_vend = Rol(nombre='vendedor', descripcion='Vendedor')
        terr = Territorio(nombre='t1', descripcion='T1')
        _db.session.add_all([rol_admin, rol_vend, terr])
        _db.session.flush()
        admin = Vendedor(username='admin', email='a@t.com', nombre_completo='Admin',
                         rol_id=rol_admin.id, territorio_id=terr.id, activo=True)
        admin.set_password('pw')
        vend = Vendedor(username='vend', email='v@t.com', nombre_completo='Vend',
                        rol_id=rol_vend.id, territorio_id=terr.id, activo=True)
        vend.set_password('pw')
        _db.session.add_all([admin, vend])
        cam = Camara(nombre='Congelación 1', tipo='congelacion',
                     temp_min=Decimal('-25'), temp_max=Decimal('-18'), activa=True)
        _db.session.add(cam)
        _db.session.commit()
        IDS['camara'] = cam.id
        IDS['admin'] = admin.id
        IDS['vend'] = vend.id
        yield flask_app
        _db.drop_all()


def _login(app, username):
    c = app.test_client()
    c.post('/login', data={'username': username, 'password': 'pw'}, follow_redirects=True)
    return c


def test_camara_fuera_de_rango():
    from app import Camara
    from decimal import Decimal
    cam = Camara(nombre='C', tipo='refrigeracion', temp_min=Decimal('0'), temp_max=Decimal('4'))
    assert cam.fuera_de_rango(2) is False
    assert cam.fuera_de_rango(0) is False      # límite inferior incluido
    assert cam.fuera_de_rango(4) is False      # límite superior incluido
    assert cam.fuera_de_rango(5) is True
    assert cam.fuera_de_rango(-1) is True


def test_lectura_persiste(app):
    from app import Camara, LecturaTemperatura
    from decimal import Decimal
    with app.app_context():
        lec = LecturaTemperatura(
            camara_id=IDS['camara'], temperatura=Decimal('-20'),
            registrado_por=IDS['admin'], fuera_de_rango=False,
        )
        _db.session.add(lec)
        _db.session.commit()
        got = _db.session.get(LecturaTemperatura, lec.id)
        assert got is not None
        assert got.camara.nombre == 'Congelación 1'
        assert got.registrado_en is not None
```

- [ ] **Step 2: Correr y verificar que falla**

Run: `.venv311/bin/python -m pytest tests/test_registro_temperaturas.py -q`
Expected: FAIL (no existen `Camara` / `LecturaTemperatura`).

- [ ] **Step 3: Agregar los modelos**

En `app.py`, justo después de la clase `CajaPesada` (que termina antes de `class PedidoEvento`), agregar:

```python
class Camara(db.Model):
    __tablename__ = 'camara'
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(120), nullable=False)
    tipo = db.Column(db.String(20), nullable=False, default='refrigeracion')  # refrigeracion|congelacion
    temp_min = db.Column(db.Numeric(5, 2), nullable=False)
    temp_max = db.Column(db.Numeric(5, 2), nullable=False)
    activa = db.Column(db.Boolean, nullable=False, default=True)
    creado_en = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    def fuera_de_rango(self, temperatura):
        """True si la temperatura está fuera del rango aceptable [min, max]."""
        t = Decimal(str(temperatura))
        return t < self.temp_min or t > self.temp_max

    def __repr__(self):
        return f'<Camara {self.id} {self.nombre}>'


class LecturaTemperatura(db.Model):
    __tablename__ = 'lectura_temperatura'
    id = db.Column(db.Integer, primary_key=True)
    camara_id = db.Column(db.Integer, db.ForeignKey('camara.id'), nullable=False, index=True)
    temperatura = db.Column(db.Numeric(5, 2), nullable=False)
    registrado_por = db.Column(db.Integer, db.ForeignKey('vendedor.id'), nullable=True)
    registrado_en = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)
    fuera_de_rango = db.Column(db.Boolean, nullable=False, default=False)
    accion_correctiva = db.Column(db.Text, nullable=True)

    camara = db.relationship('Camara')
    registrado_por_vendedor = db.relationship('Vendedor')

    def __repr__(self):
        return f'<LecturaTemperatura {self.id} camara={self.camara_id} {self.temperatura}>'
```

- [ ] **Step 4: Correr y verificar que pasa**

Run: `.venv311/bin/python -m pytest tests/test_registro_temperaturas.py -q`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add app.py tests/test_registro_temperaturas.py
git commit -m "feat(haccp): modelos Camara y LecturaTemperatura"
```

---

### Task 2: Administración de cámaras (solo super_admin)

**Files:**
- Modify: `app.py` (rutas nuevas; ubicarlas juntas, p. ej. cerca del final de las rutas, antes de `if __name__ == '__main__'`)
- Create: `templates/registros/camaras.html`
- Test: `tests/test_registro_temperaturas.py` (añadir casos)

- [ ] **Step 1: Escribir los tests que fallan**

Añadir a `tests/test_registro_temperaturas.py`:

```python
def test_camaras_no_admin_bloqueado(app):
    from app import Camara
    c = _login(app, 'vend')
    resp = c.post('/registros/temperaturas/camaras/nueva',
                  data={'nombre': 'X', 'tipo': 'refrigeracion', 'temp_min': '0', 'temp_max': '4'},
                  follow_redirects=False)
    assert resp.status_code in (302, 403)
    with app.app_context():
        assert Camara.query.filter_by(nombre='X').first() is None


def test_camaras_admin_crea(app):
    from app import Camara
    c = _login(app, 'admin')
    resp = c.post('/registros/temperaturas/camaras/nueva',
                  data={'nombre': 'Refri 2', 'tipo': 'refrigeracion', 'temp_min': '0', 'temp_max': '4'},
                  follow_redirects=True)
    assert resp.status_code == 200
    with app.app_context():
        assert Camara.query.filter_by(nombre='Refri 2').first() is not None


def test_camaras_rango_invalido_rechazado(app):
    from app import Camara
    c = _login(app, 'admin')
    c.post('/registros/temperaturas/camaras/nueva',
           data={'nombre': 'Mala', 'tipo': 'refrigeracion', 'temp_min': '5', 'temp_max': '1'},
           follow_redirects=True)
    with app.app_context():
        assert Camara.query.filter_by(nombre='Mala').first() is None


def test_camaras_toggle(app):
    from app import Camara
    c = _login(app, 'admin')
    c.post(f'/registros/temperaturas/camaras/{IDS["camara"]}/toggle', follow_redirects=True)
    with app.app_context():
        assert _db.session.get(Camara, IDS['camara']).activa is False
```

- [ ] **Step 2: Correr y verificar que fallan**

Run: `.venv311/bin/python -m pytest tests/test_registro_temperaturas.py -q`
Expected: FAIL (rutas inexistentes → 404).

- [ ] **Step 3: Implementar las rutas de cámaras**

En `app.py`, antes de `if __name__ == '__main__':`, agregar:

```python
# ───────────────────────── HACCP: Cámaras ─────────────────────────
_TIPOS_CAMARA = ('refrigeracion', 'congelacion')


def _parse_rango_camara(form):
    """Devuelve (nombre, tipo, temp_min, temp_max, error)."""
    nombre = (form.get('nombre') or '').strip()
    tipo = (form.get('tipo') or '').strip()
    if not nombre:
        return None, None, None, None, 'El nombre es obligatorio.'
    if tipo not in _TIPOS_CAMARA:
        return None, None, None, None, 'Tipo de cámara no válido.'
    try:
        temp_min = Decimal(str(form.get('temp_min')).replace(',', '.'))
        temp_max = Decimal(str(form.get('temp_max')).replace(',', '.'))
    except (InvalidOperation, TypeError, ValueError):
        return None, None, None, None, 'Temperaturas mínima y máxima deben ser números.'
    if temp_min > temp_max:
        return None, None, None, None, 'La temperatura mínima no puede ser mayor que la máxima.'
    return nombre, tipo, temp_min, temp_max, None


@app.route('/registros/temperaturas/camaras')
@login_required
@requiere_rol(['super_admin'])
def camaras_list():
    camaras = Camara.query.order_by(Camara.nombre).all()
    return render_template('registros/camaras.html', camaras=camaras)


@app.route('/registros/temperaturas/camaras/nueva', methods=['POST'])
@login_required
@requiere_rol(['super_admin'])
def camara_nueva():
    nombre, tipo, temp_min, temp_max, error = _parse_rango_camara(request.form)
    if error:
        flash(error, 'danger')
        return redirect(url_for('camaras_list'))
    db.session.add(Camara(nombre=nombre, tipo=tipo, temp_min=temp_min,
                          temp_max=temp_max, activa=True))
    db.session.commit()
    flash('Cámara creada.', 'success')
    return redirect(url_for('camaras_list'))


@app.route('/registros/temperaturas/camaras/<int:camara_id>/editar', methods=['POST'])
@login_required
@requiere_rol(['super_admin'])
def camara_editar(camara_id):
    camara = Camara.query.get_or_404(camara_id)
    nombre, tipo, temp_min, temp_max, error = _parse_rango_camara(request.form)
    if error:
        flash(error, 'danger')
        return redirect(url_for('camaras_list'))
    camara.nombre, camara.tipo, camara.temp_min, camara.temp_max = nombre, tipo, temp_min, temp_max
    db.session.commit()
    flash('Cámara actualizada.', 'success')
    return redirect(url_for('camaras_list'))


@app.route('/registros/temperaturas/camaras/<int:camara_id>/toggle', methods=['POST'])
@login_required
@requiere_rol(['super_admin'])
def camara_toggle(camara_id):
    camara = Camara.query.get_or_404(camara_id)
    camara.activa = not camara.activa
    db.session.commit()
    flash('Cámara actualizada.', 'success')
    return redirect(url_for('camaras_list'))
```

Asegurar que `InvalidOperation` esté importado: si `from decimal import Decimal` no incluye `InvalidOperation`, cambiar ese import a `from decimal import Decimal, InvalidOperation` (verificar el import existente cerca del inicio de `app.py` y ampliarlo si hace falta).

- [ ] **Step 4: Crear la plantilla `templates/registros/camaras.html`**

```html
{% extends "base.html" %}
{% block title %}Cámaras — Registros{% endblock %}
{% block header_title %}<span class="fw-700 color-white">Cámaras</span>{% endblock %}
{% block content %}
<div class="mobile-form-container">

  <div class="mobile-card">
    <div class="mobile-card-header"><i class="fas fa-snowflake"></i> Nueva cámara</div>
    <div class="mobile-card-body">
      <form method="POST" action="{{ url_for('camara_nueva') }}" autocomplete="off">
        <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
        <div class="mobile-form-group">
          <label class="mobile-form-label" for="nombre">Nombre</label>
          <input type="text" id="nombre" name="nombre" class="mobile-form-control" required>
        </div>
        <div class="mobile-form-group">
          <label class="mobile-form-label" for="tipo">Tipo</label>
          <select id="tipo" name="tipo" class="mobile-form-control" required>
            <option value="refrigeracion">Refrigeración</option>
            <option value="congelacion">Congelación</option>
          </select>
        </div>
        <div class="mobile-form-group">
          <label class="mobile-form-label" for="temp_min">Temp. mínima (°C)</label>
          <input type="text" inputmode="decimal" id="temp_min" name="temp_min" class="mobile-form-control" required>
        </div>
        <div class="mobile-form-group">
          <label class="mobile-form-label" for="temp_max">Temp. máxima (°C)</label>
          <input type="text" inputmode="decimal" id="temp_max" name="temp_max" class="mobile-form-control" required>
        </div>
        <div class="mobile-form-actions">
          <button type="submit" class="mobile-btn mobile-btn-primary"><i class="fas fa-save"></i> Crear</button>
        </div>
      </form>
    </div>
  </div>

  <div class="mobile-card">
    <div class="mobile-card-header"><i class="fas fa-list"></i> Cámaras registradas</div>
    <div class="mobile-card-body">
      {% for c in camaras %}
        <div class="mobile-form-group" style="border-bottom:1px solid #e5e7eb; padding-bottom:8px;">
          <strong>{{ c.nombre }}</strong> — {{ 'Refrigeración' if c.tipo == 'refrigeracion' else 'Congelación' }}
          <br><small>Rango: {{ c.temp_min }}°C a {{ c.temp_max }}°C · {{ 'Activa' if c.activa else 'Inactiva' }}</small>
          <form method="POST" action="{{ url_for('camara_toggle', camara_id=c.id) }}" style="display:inline; margin-left:8px;">
            <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
            <button type="submit" class="mobile-btn mobile-btn-secondary">{{ 'Desactivar' if c.activa else 'Activar' }}</button>
          </form>
        </div>
      {% else %}
        <p>No hay cámaras. Crea la primera arriba.</p>
      {% endfor %}
    </div>
  </div>

</div>
{% endblock %}
```

- [ ] **Step 5: Correr y verificar que pasan**

Run: `.venv311/bin/python -m pytest tests/test_registro_temperaturas.py -q`
Expected: PASS (todos).

- [ ] **Step 6: Commit**

```bash
git add app.py templates/registros/camaras.html tests/test_registro_temperaturas.py
git commit -m "feat(haccp): administración de cámaras (super_admin)"
```

---

### Task 3: Registrar lectura + pantalla principal (estado de hoy)

**Files:**
- Modify: `app.py` (rutas, junto a las de Task 2)
- Create: `templates/registros/temperaturas.html`
- Test: `tests/test_registro_temperaturas.py` (añadir casos)

- [ ] **Step 1: Escribir los tests que fallan**

Añadir a `tests/test_registro_temperaturas.py`:

```python
def test_registrar_requiere_login(app):
    client = app.test_client()
    resp = client.post('/registros/temperaturas/registrar',
                        data={'camara_id': IDS['camara'], 'temperatura': '-20'},
                        follow_redirects=False)
    assert resp.status_code == 302
    assert '/login' in resp.headers.get('Location', '')


def test_registrar_en_rango(app):
    from app import LecturaTemperatura
    c = _login(app, 'vend')
    resp = c.post('/registros/temperaturas/registrar',
                  data={'camara_id': IDS['camara'], 'temperatura': '-20'},
                  follow_redirects=True)
    assert resp.status_code == 200
    with app.app_context():
        lec = LecturaTemperatura.query.filter_by(camara_id=IDS['camara']).first()
        assert lec is not None
        assert lec.fuera_de_rango is False
        assert lec.registrado_por == IDS['vend']


def test_registrar_fuera_de_rango_sin_accion_rechazado(app):
    from app import LecturaTemperatura
    c = _login(app, 'vend')
    c.post('/registros/temperaturas/registrar',
           data={'camara_id': IDS['camara'], 'temperatura': '-5', 'accion_correctiva': ''},
           follow_redirects=True)
    with app.app_context():
        assert LecturaTemperatura.query.filter_by(camara_id=IDS['camara']).count() == 0


def test_registrar_fuera_de_rango_con_accion(app):
    from app import LecturaTemperatura
    c = _login(app, 'vend')
    c.post('/registros/temperaturas/registrar',
           data={'camara_id': IDS['camara'], 'temperatura': '-5',
                 'accion_correctiva': 'Se movió el producto a otra cámara'},
           follow_redirects=True)
    with app.app_context():
        lec = LecturaTemperatura.query.filter_by(camara_id=IDS['camara']).first()
        assert lec is not None
        assert lec.fuera_de_rango is True
        assert 'otra cámara' in lec.accion_correctiva


def test_principal_muestra_estado(app):
    c = _login(app, 'vend')
    resp = c.get('/registros/temperaturas')
    assert resp.status_code == 200
    assert 'Congelación 1' in resp.data.decode('utf-8')
```

- [ ] **Step 2: Correr y verificar que fallan**

Run: `.venv311/bin/python -m pytest tests/test_registro_temperaturas.py -q`
Expected: FAIL (rutas inexistentes).

- [ ] **Step 3: Implementar las rutas**

En `app.py`, junto a las rutas de Task 2:

```python
def _camaras_con_lectura_hoy():
    """Set de camara_id que ya tienen al menos una lectura HOY (fecha local)."""
    hoy = date.today()
    filas = db.session.query(LecturaTemperatura.camara_id).filter(
        func.date(LecturaTemperatura.registrado_en) == hoy
    ).distinct().all()
    return {row[0] for row in filas}


@app.route('/registros/temperaturas')
@login_required
def temperaturas_index():
    camaras = Camara.query.filter_by(activa=True).order_by(Camara.nombre).all()
    con_lectura_hoy = _camaras_con_lectura_hoy()
    es_admin = isinstance(current_user, Vendedor) and current_user.rol.nombre == 'super_admin'
    return render_template('registros/temperaturas.html',
                           camaras=camaras,
                           con_lectura_hoy=con_lectura_hoy,
                           es_admin=es_admin)


@app.route('/registros/temperaturas/registrar', methods=['POST'])
@login_required
def temperatura_registrar():
    camara = Camara.query.filter_by(id=request.form.get('camara_id', type=int), activa=True).first()
    if camara is None:
        flash('Cámara no válida.', 'danger')
        return redirect(url_for('temperaturas_index'))
    try:
        temperatura = Decimal(str(request.form.get('temperatura')).replace(',', '.'))
    except (InvalidOperation, TypeError, ValueError):
        flash('La temperatura debe ser un número.', 'danger')
        return redirect(url_for('temperaturas_index'))

    accion = (request.form.get('accion_correctiva') or '').strip()
    fuera = camara.fuera_de_rango(temperatura)
    if fuera and not accion:
        flash(f'La lectura {temperatura}°C está fuera del rango de {camara.nombre} '
              f'({camara.temp_min}°C a {camara.temp_max}°C). Describe la acción correctiva.', 'danger')
        return redirect(url_for('temperaturas_index'))

    db.session.add(LecturaTemperatura(
        camara_id=camara.id,
        temperatura=temperatura,
        registrado_por=current_user.id if isinstance(current_user, Vendedor) else None,
        fuera_de_rango=fuera,
        accion_correctiva=accion or None,
    ))
    db.session.commit()
    flash('Lectura registrada.' + (' (Fuera de rango — registrada con acción correctiva.)' if fuera else ''),
          'success' if not fuera else 'warning')
    return redirect(url_for('temperaturas_index'))
```

- [ ] **Step 4: Crear la plantilla `templates/registros/temperaturas.html`**

```html
{% extends "base.html" %}
{% block title %}Temperaturas — Registros{% endblock %}
{% block header_title %}<span class="fw-700 color-white">Temperaturas de cámaras</span>{% endblock %}
{% block content %}
<div class="mobile-form-container">

  <div class="mobile-form-actions" style="margin-bottom:12px;">
    <a href="{{ url_for('temperaturas_historial') }}" class="mobile-btn mobile-btn-secondary"><i class="fas fa-clock-rotate-left"></i> Historial</a>
    {% if es_admin %}
    <a href="{{ url_for('camaras_list') }}" class="mobile-btn mobile-btn-secondary"><i class="fas fa-snowflake"></i> Cámaras</a>
    {% endif %}
  </div>

  {% for c in camaras %}
  <div class="mobile-card">
    <div class="mobile-card-header">
      <i class="fas fa-temperature-half"></i> {{ c.nombre }}
      {% if c.id in con_lectura_hoy %}
        <span style="margin-left:auto; color:#16a34a;"><i class="fas fa-check-circle"></i> Hoy ✓</span>
      {% else %}
        <span style="margin-left:auto; color:#d97706;"><i class="fas fa-hourglass-half"></i> Falta hoy</span>
      {% endif %}
    </div>
    <div class="mobile-card-body">
      <small>Rango: {{ c.temp_min }}°C a {{ c.temp_max }}°C</small>
      <form method="POST" action="{{ url_for('temperatura_registrar') }}" autocomplete="off">
        <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
        <input type="hidden" name="camara_id" value="{{ c.id }}">
        <div class="mobile-form-group">
          <label class="mobile-form-label" for="temperatura_{{ c.id }}">Temperatura (°C)</label>
          <input type="text" inputmode="decimal" id="temperatura_{{ c.id }}" name="temperatura"
                 class="mobile-form-control" placeholder="Ej: -20" required>
        </div>
        <div class="mobile-form-group">
          <label class="mobile-form-label" for="accion_{{ c.id }}">Acción correctiva <small>(obligatoria si está fuera de rango)</small></label>
          <textarea id="accion_{{ c.id }}" name="accion_correctiva" class="mobile-form-control" rows="2" placeholder="Solo si la temperatura está fuera de rango"></textarea>
        </div>
        <div class="mobile-form-actions">
          <button type="submit" class="mobile-btn mobile-btn-primary"><i class="fas fa-save"></i> Registrar lectura</button>
        </div>
      </form>
    </div>
  </div>
  {% else %}
  <div class="mobile-card"><div class="mobile-card-body">
    <p>No hay cámaras activas.{% if es_admin %} <a href="{{ url_for('camaras_list') }}">Crea una</a>.{% endif %}</p>
  </div></div>
  {% endfor %}

</div>
{% endblock %}
```

- [ ] **Step 5: Correr y verificar que pasan**

Run: `.venv311/bin/python -m pytest tests/test_registro_temperaturas.py -q`
Expected: PASS (todos).

- [ ] **Step 6: Commit**

```bash
git add app.py templates/registros/temperaturas.html tests/test_registro_temperaturas.py
git commit -m "feat(haccp): registrar lectura de temperatura + estado de hoy"
```

---

### Task 4: Historial de lecturas

**Files:**
- Modify: `app.py` (ruta `temperaturas_historial`)
- Create: `templates/registros/temperaturas_historial.html`
- Test: `tests/test_registro_temperaturas.py` (añadir caso)

- [ ] **Step 1: Escribir el test que falla**

Añadir a `tests/test_registro_temperaturas.py`:

```python
def test_historial_lista_lecturas(app):
    c = _login(app, 'vend')
    c.post('/registros/temperaturas/registrar',
           data={'camara_id': IDS['camara'], 'temperatura': '-20'}, follow_redirects=True)
    resp = c.get('/registros/temperaturas/historial')
    assert resp.status_code == 200
    body = resp.data.decode('utf-8')
    assert 'Congelación 1' in body
    assert '-20' in body
```

- [ ] **Step 2: Correr y verificar que falla**

Run: `.venv311/bin/python -m pytest tests/test_registro_temperaturas.py::test_historial_lista_lecturas -q`
Expected: FAIL (404).

- [ ] **Step 3: Implementar la ruta**

En `app.py`, junto a las otras rutas de temperaturas:

```python
def _filtrar_lecturas(args):
    """Aplica filtros opcionales (fecha_inicio, fecha_fin, camara_id) y
    devuelve las lecturas ordenadas por fecha desc."""
    q = LecturaTemperatura.query
    fi = args.get('fecha_inicio')
    ff = args.get('fecha_fin')
    cam = args.get('camara_id', type=int)
    if fi:
        try:
            q = q.filter(func.date(LecturaTemperatura.registrado_en) >= datetime.strptime(fi, '%Y-%m-%d').date())
        except ValueError:
            pass
    if ff:
        try:
            q = q.filter(func.date(LecturaTemperatura.registrado_en) <= datetime.strptime(ff, '%Y-%m-%d').date())
        except ValueError:
            pass
    if cam:
        q = q.filter(LecturaTemperatura.camara_id == cam)
    return q.order_by(LecturaTemperatura.registrado_en.desc()).all()


@app.route('/registros/temperaturas/historial')
@login_required
def temperaturas_historial():
    lecturas = _filtrar_lecturas(request.args)
    camaras = Camara.query.order_by(Camara.nombre).all()
    return render_template('registros/temperaturas_historial.html',
                           lecturas=lecturas, camaras=camaras,
                           filtros=request.args)
```

- [ ] **Step 4: Crear la plantilla `templates/registros/temperaturas_historial.html`**

```html
{% extends "base.html" %}
{% block title %}Historial temperaturas{% endblock %}
{% block header_title %}<span class="fw-700 color-white">Historial de temperaturas</span>{% endblock %}
{% block content %}
<div class="mobile-form-container">

  <div class="mobile-card">
    <div class="mobile-card-header"><i class="fas fa-filter"></i> Filtros</div>
    <div class="mobile-card-body">
      <form method="GET" action="{{ url_for('temperaturas_historial') }}">
        <div class="mobile-form-group">
          <label class="mobile-form-label" for="fecha_inicio">Desde</label>
          <input type="date" id="fecha_inicio" name="fecha_inicio" class="mobile-form-control" value="{{ filtros.get('fecha_inicio', '') }}">
        </div>
        <div class="mobile-form-group">
          <label class="mobile-form-label" for="fecha_fin">Hasta</label>
          <input type="date" id="fecha_fin" name="fecha_fin" class="mobile-form-control" value="{{ filtros.get('fecha_fin', '') }}">
        </div>
        <div class="mobile-form-group">
          <label class="mobile-form-label" for="camara_id">Cámara</label>
          <select id="camara_id" name="camara_id" class="mobile-form-control">
            <option value="">Todas</option>
            {% for c in camaras %}
            <option value="{{ c.id }}" {{ 'selected' if filtros.get('camara_id') == c.id|string }}>{{ c.nombre }}</option>
            {% endfor %}
          </select>
        </div>
        <div class="mobile-form-actions">
          <button type="submit" class="mobile-btn mobile-btn-primary"><i class="fas fa-search"></i> Filtrar</button>
          <button type="submit" form="export-form" class="mobile-btn mobile-btn-success"><i class="fas fa-file-pdf"></i> Exportar PDF</button>
        </div>
      </form>
      <form id="export-form" method="POST" action="{{ url_for('temperaturas_export') }}" target="etiquetas-download-frame">
        <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
        <input type="hidden" name="fecha_inicio" value="{{ filtros.get('fecha_inicio', '') }}">
        <input type="hidden" name="fecha_fin" value="{{ filtros.get('fecha_fin', '') }}">
        <input type="hidden" name="camara_id" value="{{ filtros.get('camara_id', '') }}">
      </form>
    </div>
  </div>

  <div class="mobile-card">
    <div class="mobile-card-header"><i class="fas fa-list"></i> Lecturas</div>
    <div class="mobile-card-body">
      {% for l in lecturas %}
        <div class="mobile-form-group" style="border-bottom:1px solid #e5e7eb; padding-bottom:8px; {% if l.fuera_de_rango %}color:#dc2626;{% endif %}">
          <strong>{{ l.camara.nombre }}</strong> — {{ l.temperatura }}°C
          {% if l.fuera_de_rango %}<span style="font-weight:700;"> (FUERA DE RANGO)</span>{% endif %}
          <br><small>{{ l.registrado_en.strftime('%Y-%m-%d %H:%M') }}
          {% if l.registrado_por_vendedor %} · {{ l.registrado_por_vendedor.nombre_completo }}{% endif %}</small>
          {% if l.accion_correctiva %}<br><small>Acción: {{ l.accion_correctiva }}</small>{% endif %}
        </div>
      {% else %}
        <p>No hay lecturas para los filtros seleccionados.</p>
      {% endfor %}
    </div>
  </div>

</div>
{% endblock %}
```

- [ ] **Step 5: Correr y verificar que pasa**

Run: `.venv311/bin/python -m pytest tests/test_registro_temperaturas.py -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add app.py templates/registros/temperaturas_historial.html tests/test_registro_temperaturas.py
git commit -m "feat(haccp): historial de lecturas con filtros"
```

---

### Task 5: Exportar PDF (reportlab) con compartir en iOS

**Files:**
- Modify: `app.py` (ruta `temperaturas_export` + helper PDF)
- Modify: `templates/registros/temperaturas_historial.html` (incluir el helper de compartir + interceptar en iOS)
- Test: `tests/test_registro_temperaturas.py` (añadir caso)

- [ ] **Step 1: Escribir el test que falla**

Añadir a `tests/test_registro_temperaturas.py`:

```python
def test_export_devuelve_pdf(app):
    c = _login(app, 'vend')
    c.post('/registros/temperaturas/registrar',
           data={'camara_id': IDS['camara'], 'temperatura': '-20'}, follow_redirects=True)
    resp = c.post('/registros/temperaturas/export',
                  data={'fecha_inicio': '2000-01-01', 'fecha_fin': '2100-01-01'},
                  follow_redirects=False)
    assert resp.status_code == 200
    assert 'application/pdf' in resp.headers.get('Content-Type', '')
```

- [ ] **Step 2: Correr y verificar que falla**

Run: `.venv311/bin/python -m pytest tests/test_registro_temperaturas.py::test_export_devuelve_pdf -q`
Expected: FAIL (404).

- [ ] **Step 3: Implementar el helper PDF y la ruta**

En `app.py`, junto a las rutas de temperaturas:

```python
def _build_temperaturas_pdf(lecturas, fecha_inicio, fecha_fin):
    """Construye el PDF tabular del registro de temperaturas. Devuelve BytesIO."""
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=landscape(A4),
                            leftMargin=0.4 * inch, rightMargin=0.4 * inch,
                            topMargin=0.5 * inch, bottomMargin=0.5 * inch)
    styles = getSampleStyleSheet()
    cell = ParagraphStyle(name='cell', fontSize=8, leading=10, alignment=TA_LEFT)
    elements = [
        Paragraph('Registro de temperaturas de cámaras', styles['Title']),
        Paragraph(f'Período: {fecha_inicio or "—"} a {fecha_fin or "—"}', styles['Normal']),
        Spacer(1, 10),
    ]
    encabezados = ['Fecha/Hora', 'Cámara', 'Tipo', 'Rango (°C)', 'Lectura (°C)',
                   'En rango', 'Responsable', 'Acción correctiva']
    data = [encabezados]
    for l in lecturas:
        data.append([
            Paragraph(l.registrado_en.strftime('%Y-%m-%d %H:%M'), cell),
            Paragraph(l.camara.nombre if l.camara else '—', cell),
            Paragraph('Refrig.' if (l.camara and l.camara.tipo == 'refrigeracion') else 'Congel.', cell),
            Paragraph(f'{l.camara.temp_min} a {l.camara.temp_max}' if l.camara else '—', cell),
            Paragraph(str(l.temperatura), cell),
            Paragraph('NO' if l.fuera_de_rango else 'Sí', cell),
            Paragraph(l.registrado_por_vendedor.nombre_completo if l.registrado_por_vendedor else '—', cell),
            Paragraph(l.accion_correctiva or '', cell),
        ])
    tabla = Table(data, repeatRows=1)
    estilo = TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1f2937')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTSIZE', (0, 0), (-1, 0), 8),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
    ])
    for i, l in enumerate(lecturas, start=1):
        if l.fuera_de_rango:
            estilo.add('BACKGROUND', (0, i), (-1, i), colors.HexColor('#fee2e2'))
    tabla.setStyle(estilo)
    elements.append(tabla)
    doc.build(elements)
    buffer.seek(0)
    return buffer


@app.route('/registros/temperaturas/export', methods=['POST'])
@login_required
def temperaturas_export():
    lecturas = _filtrar_lecturas(request.form)
    fi = request.form.get('fecha_inicio') or ''
    ff = request.form.get('fecha_fin') or ''
    buffer = _build_temperaturas_pdf(lecturas, fi, ff)
    filename = f"registro_temperaturas_{fi or 'inicio'}_{ff or 'fin'}.pdf"
    response = make_response(send_file(buffer, mimetype='application/pdf',
                                       as_attachment=not _is_ios_request(),
                                       download_name=filename))
    response.headers['Content-Type'] = 'application/pdf'
    return response
```

Nota: `_filtrar_lecturas` acepta tanto `request.args` (GET historial) como `request.form` (POST export) porque ambos exponen `.get(...)`; el parámetro `camara_id` vacío se ignora (`type=int` sobre '' devuelve None).

- [ ] **Step 4: Conectar compartir en iOS en la plantilla del historial**

En `templates/registros/temperaturas_historial.html`, al inicio del `{% block content %}` (o reutilizando un bloque de scripts si existe), incluir el helper y un script que, en iOS, intercepte el submit del `#export-form` y use la hoja de compartir. Añadir justo antes de `{% endblock %}` del content:

```html
<script src="{{ url_for('static', filename='js/etiquetas_ios_share.js') }}"></script>
<script>
  (function () {
    var exportForm = document.getElementById('export-form');
    if (!exportForm) return;
    exportForm.addEventListener('submit', function (e) {
      if (window.esDispositivoIOS && window.esDispositivoIOS()) {
        e.preventDefault();
        var fd = new FormData(exportForm);
        window.compartirEtiquetaIOS(exportForm.action, fd, 'registro_temperaturas.pdf');
      }
    });
  })();
</script>
```

- [ ] **Step 5: Correr y verificar que pasa**

Run: `.venv311/bin/python -m pytest tests/test_registro_temperaturas.py -q`
Expected: PASS (todos).

- [ ] **Step 6: Commit**

```bash
git add app.py templates/registros/temperaturas_historial.html tests/test_registro_temperaturas.py
git commit -m "feat(haccp): exportar registro de temperaturas a PDF (compartir en iOS)"
```

---

### Task 6: Navegación, verificación y creación de tablas en producción

**Files:**
- Modify: `templates/base.html` (enlaces de navegación)

- [ ] **Step 1: Agregar enlace en el dropdown de usuario (desktop)**

En `templates/base.html`, dentro de `<div class="dropdown-menu">`, insertar entre "Ir al dashboard" y "Cambiar contraseña":

Buscar:
```html
                                <a href="/dashboard" class="dropdown-item">
                                    <i class="fas fa-chart-pie"></i><span>Ir al dashboard</span>
                                </a>
                                <a href="{{ url_for('cambiar_password') }}" class="dropdown-item">
```
Reemplazar por:
```html
                                <a href="/dashboard" class="dropdown-item">
                                    <i class="fas fa-chart-pie"></i><span>Ir al dashboard</span>
                                </a>
                                <a href="{{ url_for('temperaturas_index') }}" class="dropdown-item">
                                    <i class="fas fa-temperature-half"></i><span>Registros</span>
                                </a>
                                <a href="{{ url_for('cambiar_password') }}" class="dropdown-item">
```

- [ ] **Step 2: Agregar enlace en el drawer (móvil)**

En `templates/base.html`, buscar:
```html
            <div class="drawer-section">
                <a href="{{ url_for('cambiar_password') }}" class="drawer-item">
                    <i class="fas fa-key"></i><span>Cambiar contraseña</span>
                </a>
```
Reemplazar por:
```html
            <div class="drawer-section">
                <a href="{{ url_for('temperaturas_index') }}" class="drawer-item">
                    <i class="fas fa-temperature-half"></i><span>Registros</span>
                </a>
                <a href="{{ url_for('cambiar_password') }}" class="drawer-item">
                    <i class="fas fa-key"></i><span>Cambiar contraseña</span>
                </a>
```

- [ ] **Step 3: Verificar render + suite completa**

Run: `.venv311/bin/python -m pytest tests/test_registro_temperaturas.py tests/test_reskin_smoke.py -q`
Expected: PASS (el smoke confirma que `url_for('temperaturas_index')` resuelve en base.html).

Run: `.venv311/bin/python -m pytest tests/ -q`
Expected: los tests nuevos pasan; el conteo de fallas pre-existentes (22) no aumenta.

- [ ] **Step 4: Commit**

```bash
git add templates/base.html
git commit -m "feat(haccp): enlace 'Registros' en el menú de usuario"
```

- [ ] **Step 5: Deploy + crear tablas en Heroku**

```bash
git push origin main
git push heroku main
# Crear las tablas nuevas (idempotente, no altera tablas existentes):
heroku run --no-tty --app pesosapp python -c "from app import app, db; app.app_context().push(); db.create_all(); print('tablas creadas/verificadas')"
```
Expected: el comando imprime "tablas creadas/verificadas". Verificar la app en vivo: el menú muestra "Registros" y `/registros/temperaturas` carga.

---

## Self-Review

**Spec coverage:**
- Modelo Camara (nombre, tipo, min/max, activa) → Task 1.
- Modelo LecturaTemperatura (camara, temp, responsable, hora, fuera_de_rango persistido, acción) → Task 1.
- Regla fuera de rango exige acción correctiva → Task 3 (route) + tests.
- fuera_de_rango calculado y persistido al guardar → Task 3 (usa Camara.fuera_de_rango, guarda bool).
- Permisos: registrar/ver cualquier autenticado; cámaras solo super_admin → Task 2 (requiere_rol) + Task 3 (login_required) + tests.
- Pantallas: principal con estado hoy (Task 3), registrar (Task 3), historial filtrable (Task 4), export PDF (Task 5).
- Export inline en iOS + hoja de compartir → Task 5 (_is_ios_request + etiquetas_ios_share.js).
- Navegación "Registros" → Task 6.
- Migración/tablas en Heroku → Task 6 Step 5.
- Pruebas listadas en el spec → cubiertas en Tasks 1-5.

**Placeholder scan:** Sin TBD/TODO; todo el código (modelos, rutas, plantillas, tests, comandos) está completo.

**Type/identifier consistency:** Endpoints usados en plantillas y nav coinciden con los `def`: `camaras_list`, `camara_nueva`, `camara_editar`, `camara_toggle`, `temperaturas_index`, `temperatura_registrar`, `temperaturas_historial`, `temperaturas_export`. Modelos `Camara`/`LecturaTemperatura` y campos (`temp_min`, `temp_max`, `fuera_de_rango`, `accion_correctiva`, `registrado_por`, `registrado_en`, `registrado_por_vendedor`) usados consistentemente en rutas, plantillas y tests. `Camara.fuera_de_rango()` definido en Task 1 y usado en Task 3. `_filtrar_lecturas` definido en Task 4 y reutilizado en Task 5. `_is_ios_request` y `etiquetas_ios_share.js` ya existen (sesión previa). Requiere ampliar el import de `decimal` a `Decimal, InvalidOperation` (indicado en Task 2 Step 3).
