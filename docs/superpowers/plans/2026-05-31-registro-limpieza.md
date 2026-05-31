# Registros de limpieza + Productos/diluciones (HACCP) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Añadir a los registros HACCP de PesosApp un sistema de registros de limpieza y desinfección, con un catálogo consultable de productos (dilución/procedimiento) vinculado a las áreas/equipos, resultado Conforme/No conforme con acción correctiva, PDF auditable, verificación por período, y un hub de Registros.

**Architecture:** Espeja exactamente la feature de temperaturas ya existente. Modelos en `app.py`, rutas en `app.py` (se anexan después de la ruta `registro_config`, antes de `if __name__`), plantillas Jinja en `templates/registros/`, CSS reutilizado de `static/css/registros.css`. Sin imports nuevos (ReportLab, BytesIO, joinedload, func, make_response, send_file, basedir, DASHBOARD_TIMEZONE, `_is_ios_request`, `requiere_rol`, `Vendedor` ya están importados/definidos para temperaturas).

**Tech Stack:** Flask, SQLAlchemy, Jinja2, ReportLab (PDF), pytest, Postgres (prod) / SQLite (tests).

**Spec:** `docs/superpowers/specs/2026-05-31-registro-limpieza-design.md`

---

## File Structure

- **Modificar** `app.py`:
  - Modelos nuevos tras `RevisionRegistro` (~línea 2133): `ProductoLimpieza`, `AreaLimpieza`, `RegistroLimpieza`, `LimpiezaConfig`, `RevisionLimpieza`.
  - Rutas + helpers nuevos tras la ruta `registro_config` (~línea 9073), antes de `if __name__ == '__main__':`.
- **Crear** plantillas en `templates/registros/`: `index.html` (hub), `limpieza.html`, `limpieza_historial.html`, `areas_limpieza.html`, `productos_limpieza.html`, `limpieza_config.html`.
- **Modificar** `templates/base.html`: los dos enlaces de menú "Registros" (drawer y dropdown) pasan de `temperaturas_index` a `registros_index`.
- **Crear** `tests/test_registro_limpieza.py`.
- **DB**: crear 5 tablas en local y en Heroku (`heroku pg:psql`).

---

## Task 1: Modelos

**Files:**
- Create: `tests/test_registro_limpieza.py`
- Modify: `app.py` (insertar tras línea ~2133, después de la clase `RevisionRegistro`)

- [ ] **Step 1: Crear el archivo de test con fixture y el primer test (de persistencia de modelos)**

Crear `tests/test_registro_limpieza.py` con este contenido completo:

```python
"""Tests del registro de limpieza (HACCP)."""
import os

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
        from app import Rol, Territorio, Vendedor, ProductoLimpieza, AreaLimpieza
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
        prod = ProductoLimpieza(nombre='Sanitizante clorado', dilucion='10 ml / 1 L', activo=True)
        _db.session.add(prod)
        _db.session.flush()
        area = AreaLimpieza(nombre='Sierra de cortar', tipo='equipo',
                            producto_id=prod.id, frecuencia_texto='Diaria', activa=True)
        _db.session.add(area)
        _db.session.commit()
        IDS['producto'] = prod.id
        IDS['area'] = area.id
        IDS['admin'] = admin.id
        IDS['vend'] = vend.id
        yield flask_app
        _db.drop_all()


def _login(app, username):
    c = app.test_client()
    c.post('/login', data={'username': username, 'password': 'pw'}, follow_redirects=True)
    return c


def test_registro_persiste(app):
    from app import RegistroLimpieza
    with app.app_context():
        r = RegistroLimpieza(area_id=IDS['area'], registrado_por=IDS['admin'], conforme=True)
        _db.session.add(r)
        _db.session.commit()
        got = _db.session.get(RegistroLimpieza, r.id)
        assert got is not None
        assert got.area.nombre == 'Sierra de cortar'
        assert got.area.producto.nombre == 'Sanitizante clorado'
        assert got.registrado_en is not None
```

- [ ] **Step 2: Correr el test para verificar que falla**

Run: `python -m pytest tests/test_registro_limpieza.py::test_registro_persiste -v`
Expected: FAIL — `ImportError: cannot import name 'ProductoLimpieza' from 'app'`

- [ ] **Step 3: Añadir los 5 modelos en `app.py`**

Insertar tras la clase `RevisionRegistro` (después de la línea `return f'<RevisionRegistro {self.id} por={self.revisado_por}>'`, ~línea 2133):

```python
class ProductoLimpieza(db.Model):
    """Catálogo consultable de productos de limpieza: dilución y procedimiento (SSOP)."""
    __tablename__ = 'producto_limpieza'
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(120), nullable=False)
    dilucion = db.Column(db.String(255), nullable=False)
    procedimiento = db.Column(db.Text, nullable=True)
    notas_seguridad = db.Column(db.Text, nullable=True)
    activo = db.Column(db.Boolean, nullable=False, default=True)
    creado_en = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    def __repr__(self):
        return f'<ProductoLimpieza {self.id} {self.nombre}>'


class AreaLimpieza(db.Model):
    """Equipo o espacio a limpiar, con su producto/método/frecuencia (ficha fija)."""
    __tablename__ = 'area_limpieza'
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(120), nullable=False)
    tipo = db.Column(db.String(20), nullable=False, default='equipo')  # equipo|espacio
    producto_id = db.Column(db.Integer, db.ForeignKey('producto_limpieza.id'), nullable=True)
    metodo = db.Column(db.Text, nullable=True)
    frecuencia_texto = db.Column(db.String(120), nullable=True)
    activa = db.Column(db.Boolean, nullable=False, default=True)
    creado_en = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    producto = db.relationship('ProductoLimpieza')

    def __repr__(self):
        return f'<AreaLimpieza {self.id} {self.nombre}>'


class RegistroLimpieza(db.Model):
    """Registro de una limpieza ejecutada (HACCP/SSOP)."""
    __tablename__ = 'registro_limpieza'
    id = db.Column(db.Integer, primary_key=True)
    area_id = db.Column(db.Integer, db.ForeignKey('area_limpieza.id'), nullable=False, index=True)
    registrado_por = db.Column(db.Integer, db.ForeignKey('vendedor.id'), nullable=True)
    registrado_en = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)
    conforme = db.Column(db.Boolean, nullable=False, default=True)
    observacion = db.Column(db.Text, nullable=True)
    accion_causa = db.Column(db.Text, nullable=True)
    accion_tomada = db.Column(db.Text, nullable=True)
    accion_responsable = db.Column(db.String(120), nullable=True)
    accion_disposicion = db.Column(db.Text, nullable=True)

    area = db.relationship('AreaLimpieza')
    registrado_por_vendedor = db.relationship('Vendedor')

    def __repr__(self):
        return f'<RegistroLimpieza {self.id} area={self.area_id} conforme={self.conforme}>'


class LimpiezaConfig(db.Model):
    """Configuración (fila única) del registro de limpieza para el PDF."""
    __tablename__ = 'limpieza_config'
    id = db.Column(db.Integer, primary_key=True)
    codigo_documento = db.Column(db.String(60), nullable=False, default='FR-HACCP-LIMP-01')
    version = db.Column(db.String(20), nullable=False, default='1')
    frecuencia_texto = db.Column(db.String(120), nullable=False, default='Según programa de limpieza')
    responsable_verificacion = db.Column(db.String(120), nullable=True)
    actualizado_en = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    def __repr__(self):
        return f'<LimpiezaConfig {self.codigo_documento} v{self.version}>'


class RevisionLimpieza(db.Model):
    """Verificación HACCP: un responsable revisa los registros de limpieza de un período."""
    __tablename__ = 'revision_limpieza'
    id = db.Column(db.Integer, primary_key=True)
    revisado_por = db.Column(db.Integer, db.ForeignKey('vendedor.id'), nullable=True)
    revisado_en = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    periodo_desde = db.Column(db.Date, nullable=True)
    periodo_hasta = db.Column(db.Date, nullable=True)
    nota = db.Column(db.Text, nullable=True)

    revisado_por_vendedor = db.relationship('Vendedor')

    def __repr__(self):
        return f'<RevisionLimpieza {self.id} por={self.revisado_por}>'
```

- [ ] **Step 4: Correr el test para verificar que pasa**

Run: `python -m pytest tests/test_registro_limpieza.py::test_registro_persiste -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app.py tests/test_registro_limpieza.py
git commit -m "feat(haccp): modelos de registro de limpieza (producto, area, registro, config, revision)"
```

---

## Task 2: Catálogo de productos de limpieza (consulta + CRUD admin)

**Files:**
- Modify: `app.py` (anexar tras la ruta `registro_config`, ~línea 9073)
- Create: `templates/registros/productos_limpieza.html`
- Test: `tests/test_registro_limpieza.py`

- [ ] **Step 1: Añadir los tests de productos**

Agregar al final de `tests/test_registro_limpieza.py`:

```python
def test_productos_admin_crea(app):
    from app import ProductoLimpieza
    c = _login(app, 'admin')
    c.post('/registros/limpieza/productos/nuevo',
           data={'nombre': 'Detergente alcalino', 'dilucion': '20 ml / 1 L',
                 'procedimiento': 'Fregar y enjuagar'}, follow_redirects=True)
    with app.app_context():
        p = ProductoLimpieza.query.filter_by(nombre='Detergente alcalino').first()
        assert p is not None
        assert p.dilucion == '20 ml / 1 L'


def test_productos_sin_dilucion_rechazado(app):
    from app import ProductoLimpieza
    c = _login(app, 'admin')
    c.post('/registros/limpieza/productos/nuevo',
           data={'nombre': 'Sin dilucion', 'dilucion': ''}, follow_redirects=True)
    with app.app_context():
        assert ProductoLimpieza.query.filter_by(nombre='Sin dilucion').first() is None


def test_productos_consulta_visible_para_todos(app):
    c = _login(app, 'vend')
    resp = c.get('/registros/limpieza/productos')
    assert resp.status_code == 200
    assert 'Sanitizante clorado' in resp.data.decode('utf-8')
```

- [ ] **Step 2: Correr los tests para verificar que fallan**

Run: `python -m pytest tests/test_registro_limpieza.py -k productos -v`
Expected: FAIL — 404 / `BuildError` (rutas inexistentes)

- [ ] **Step 3: Añadir helper, constante y rutas de productos en `app.py`**

Anexar tras la ruta `registro_config` (después de su `return render_template('registros/config.html', cfg=cfg)`, ~línea 9073):

```python
# ───────────────────────── HACCP: Limpieza ─────────────────────────
_TIPOS_AREA_LIMPIEZA = ('equipo', 'espacio')


def _get_limpieza_config():
    """Devuelve la fila única de LimpiezaConfig; la crea con valores por defecto."""
    cfg = LimpiezaConfig.query.first()
    if cfg is None:
        cfg = LimpiezaConfig()
        db.session.add(cfg)
        db.session.commit()
    return cfg


def _parse_producto_limpieza(form):
    """Devuelve (nombre, dilucion, procedimiento, notas, error)."""
    nombre = (form.get('nombre') or '').strip()
    dilucion = (form.get('dilucion') or '').strip()
    if not nombre:
        return None, None, None, None, 'El nombre del producto es obligatorio.'
    if not dilucion:
        return None, None, None, None, 'La dilución es obligatoria.'
    procedimiento = (form.get('procedimiento') or '').strip() or None
    notas = (form.get('notas_seguridad') or '').strip() or None
    return nombre, dilucion, procedimiento, notas, None


@app.route('/registros/limpieza/productos')
@login_required
def productos_limpieza_index():
    productos = ProductoLimpieza.query.order_by(ProductoLimpieza.nombre).all()
    es_admin = isinstance(current_user, Vendedor) and current_user.rol.nombre == 'super_admin'
    return render_template('registros/productos_limpieza.html', productos=productos, es_admin=es_admin)


@app.route('/registros/limpieza/productos/nuevo', methods=['POST'])
@login_required
@requiere_rol(['super_admin'])
def producto_limpieza_nuevo():
    nombre, dilucion, procedimiento, notas, error = _parse_producto_limpieza(request.form)
    if error:
        flash(error, 'danger')
        return redirect(url_for('productos_limpieza_index'))
    db.session.add(ProductoLimpieza(nombre=nombre, dilucion=dilucion,
                                    procedimiento=procedimiento, notas_seguridad=notas, activo=True))
    db.session.commit()
    flash('Producto creado.', 'success')
    return redirect(url_for('productos_limpieza_index'))


@app.route('/registros/limpieza/productos/<int:producto_id>/editar', methods=['POST'])
@login_required
@requiere_rol(['super_admin'])
def producto_limpieza_editar(producto_id):
    producto = ProductoLimpieza.query.get_or_404(producto_id)
    nombre, dilucion, procedimiento, notas, error = _parse_producto_limpieza(request.form)
    if error:
        flash(error, 'danger')
        return redirect(url_for('productos_limpieza_index'))
    producto.nombre, producto.dilucion = nombre, dilucion
    producto.procedimiento, producto.notas_seguridad = procedimiento, notas
    db.session.commit()
    flash('Producto actualizado.', 'success')
    return redirect(url_for('productos_limpieza_index'))


@app.route('/registros/limpieza/productos/<int:producto_id>/toggle', methods=['POST'])
@login_required
@requiere_rol(['super_admin'])
def producto_limpieza_toggle(producto_id):
    producto = ProductoLimpieza.query.get_or_404(producto_id)
    producto.activo = not producto.activo
    db.session.commit()
    flash('Producto actualizado.', 'success')
    return redirect(url_for('productos_limpieza_index'))
```

- [ ] **Step 4: Crear la plantilla `templates/registros/productos_limpieza.html`**

```html
{% extends "base.html" %}
{% block title %}Productos y diluciones — Limpieza{% endblock %}
{% block header_title %}<span class="fw-700 color-white">Productos y diluciones</span>{% endblock %}
{% block extra_css %}
<link rel="stylesheet" href="{{ url_for('static', filename='css/registros.css') }}">
{% endblock %}
{% block content %}
<div class="mobile-form-container reg-wrap">

  <div class="reg-toolbar">
    <a href="{{ url_for('limpieza_index') }}" class="reg-btn"><i class="fas fa-soap"></i> Registrar limpieza</a>
  </div>

  {% if es_admin %}
  <div class="mobile-card">
    <div class="mobile-card-header"><i class="fas fa-plus-circle"></i> Nuevo producto</div>
    <div class="mobile-card-body">
      <form method="POST" action="{{ url_for('producto_limpieza_nuevo') }}" autocomplete="off">
        <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
        <div class="mobile-form-group">
          <label class="mobile-form-label" for="nombre">Nombre del producto</label>
          <input type="text" id="nombre" name="nombre" class="mobile-form-control" placeholder="Ej: Sanitizante clorado" required>
        </div>
        <div class="mobile-form-group">
          <label class="mobile-form-label" for="dilucion">Dilución correcta</label>
          <input type="text" id="dilucion" name="dilucion" class="mobile-form-control" placeholder="Ej: 10 ml por 1 L de agua" required>
        </div>
        <div class="mobile-form-group">
          <label class="mobile-form-label" for="procedimiento">Procedimiento</label>
          <textarea id="procedimiento" name="procedimiento" class="mobile-form-control" rows="3" placeholder="Pasos de aplicación"></textarea>
        </div>
        <div class="mobile-form-group">
          <label class="mobile-form-label" for="notas_seguridad">Notas de seguridad</label>
          <textarea id="notas_seguridad" name="notas_seguridad" class="mobile-form-control" rows="2" placeholder="EPP, precauciones"></textarea>
        </div>
        <div class="mobile-form-actions">
          <button type="submit" class="mobile-btn mobile-btn-primary"><i class="fas fa-save"></i> Crear producto</button>
        </div>
      </form>
    </div>
  </div>
  {% endif %}

  <h3 class="reg-name" style="margin:4px 2px;"><i class="fas fa-flask"></i> Productos</h3>
  <div class="reg-list">
    {% for p in productos %}
    <article class="reg-card {{ 'is-ok' if p.activo else 'is-muted' }}">
      <div class="reg-card-head">
        <div>
          <div class="reg-name">{{ p.nombre }}</div>
          <div class="reg-sub">Dilución: <strong>{{ p.dilucion }}</strong></div>
        </div>
        <span class="reg-pill {{ 'ok' if p.activo else '' }}">{{ 'Activo' if p.activo else 'Inactivo' }}</span>
      </div>
      {% if p.procedimiento %}
      <div class="reg-accion"><i class="fas fa-list-ol"></i> <strong>Procedimiento:</strong> {{ p.procedimiento }}</div>
      {% endif %}
      {% if p.notas_seguridad %}
      <div class="reg-accion"><i class="fas fa-shield-halved"></i> <strong>Seguridad:</strong> {{ p.notas_seguridad }}</div>
      {% endif %}

      {% if es_admin %}
      <div class="reg-actions">
        <form method="POST" action="{{ url_for('producto_limpieza_toggle', producto_id=p.id) }}">
          <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
          <button type="submit" class="reg-btn">
            <i class="fas fa-{{ 'eye-slash' if p.activo else 'eye' }}"></i> {{ 'Desactivar' if p.activo else 'Activar' }}
          </button>
        </form>
      </div>
      <details class="reg-edit">
        <summary><i class="fas fa-pen"></i> Editar</summary>
        <div class="reg-edit-body">
          <form method="POST" action="{{ url_for('producto_limpieza_editar', producto_id=p.id) }}" autocomplete="off">
            <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
            <div class="mobile-form-group">
              <label class="mobile-form-label">Nombre</label>
              <input type="text" name="nombre" class="mobile-form-control" value="{{ p.nombre }}" required>
            </div>
            <div class="mobile-form-group">
              <label class="mobile-form-label">Dilución</label>
              <input type="text" name="dilucion" class="mobile-form-control" value="{{ p.dilucion }}" required>
            </div>
            <div class="mobile-form-group">
              <label class="mobile-form-label">Procedimiento</label>
              <textarea name="procedimiento" class="mobile-form-control" rows="3">{{ p.procedimiento or '' }}</textarea>
            </div>
            <div class="mobile-form-group">
              <label class="mobile-form-label">Notas de seguridad</label>
              <textarea name="notas_seguridad" class="mobile-form-control" rows="2">{{ p.notas_seguridad or '' }}</textarea>
            </div>
            <div class="mobile-form-actions">
              <button type="submit" class="mobile-btn mobile-btn-primary"><i class="fas fa-save"></i> Guardar cambios</button>
            </div>
          </form>
        </div>
      </details>
      {% endif %}
    </article>
    {% else %}
    <div class="reg-empty"><i class="fas fa-flask"></i>No hay productos registrados.{% if es_admin %} Crea el primero arriba.{% endif %}</div>
    {% endfor %}
  </div>

</div>
{% endblock %}
```

- [ ] **Step 5: Correr los tests para verificar que pasan**

Run: `python -m pytest tests/test_registro_limpieza.py -k productos -v`
Expected: PASS (3 tests)

- [ ] **Step 6: Commit**

```bash
git add app.py templates/registros/productos_limpieza.html tests/test_registro_limpieza.py
git commit -m "feat(haccp): catalogo de productos de limpieza (dilucion/procedimiento) consultable + CRUD admin"
```

---

## Task 3: Catálogo de áreas/equipos (CRUD admin)

**Files:**
- Modify: `app.py` (anexar tras las rutas de productos)
- Create: `templates/registros/areas_limpieza.html`
- Test: `tests/test_registro_limpieza.py`

- [ ] **Step 1: Añadir los tests de áreas**

Agregar al final de `tests/test_registro_limpieza.py`:

```python
def test_areas_no_admin_bloqueado(app):
    from app import AreaLimpieza
    c = _login(app, 'vend')
    resp = c.post('/registros/limpieza/areas/nueva',
                  data={'nombre': 'X', 'tipo': 'equipo'}, follow_redirects=False)
    assert resp.status_code in (302, 403)
    with app.app_context():
        assert AreaLimpieza.query.filter_by(nombre='X').first() is None


def test_areas_admin_crea(app):
    from app import AreaLimpieza
    c = _login(app, 'admin')
    resp = c.post('/registros/limpieza/areas/nueva',
                  data={'nombre': 'Mesa de empaque', 'tipo': 'espacio',
                        'producto_id': IDS['producto'], 'frecuencia_texto': 'Por turno'},
                  follow_redirects=True)
    assert resp.status_code == 200
    with app.app_context():
        a = AreaLimpieza.query.filter_by(nombre='Mesa de empaque').first()
        assert a is not None
        assert a.tipo == 'espacio'
        assert a.producto_id == IDS['producto']


def test_areas_tipo_invalido_rechazado(app):
    from app import AreaLimpieza
    c = _login(app, 'admin')
    c.post('/registros/limpieza/areas/nueva',
           data={'nombre': 'Mala', 'tipo': 'xxx'}, follow_redirects=True)
    with app.app_context():
        assert AreaLimpieza.query.filter_by(nombre='Mala').first() is None


def test_areas_admin_edita(app):
    from app import AreaLimpieza
    c = _login(app, 'admin')
    c.post(f'/registros/limpieza/areas/{IDS["area"]}/editar',
           data={'nombre': 'Sierra (editada)', 'tipo': 'equipo',
                 'producto_id': '', 'frecuencia_texto': 'Semanal'}, follow_redirects=True)
    with app.app_context():
        a = _db.session.get(AreaLimpieza, IDS['area'])
        assert a.nombre == 'Sierra (editada)'
        assert a.producto_id is None


def test_areas_toggle(app):
    from app import AreaLimpieza
    c = _login(app, 'admin')
    c.post(f'/registros/limpieza/areas/{IDS["area"]}/toggle', follow_redirects=True)
    with app.app_context():
        assert _db.session.get(AreaLimpieza, IDS['area']).activa is False
```

- [ ] **Step 2: Correr los tests para verificar que fallan**

Run: `python -m pytest tests/test_registro_limpieza.py -k areas -v`
Expected: FAIL — 404 / `BuildError`

- [ ] **Step 3: Añadir las rutas de áreas en `app.py`**

Anexar tras la ruta `producto_limpieza_toggle`:

```python
def _parse_area_limpieza(form):
    """Devuelve (nombre, tipo, producto_id, metodo, frecuencia, error)."""
    nombre = (form.get('nombre') or '').strip()
    tipo = (form.get('tipo') or '').strip()
    if not nombre:
        return None, None, None, None, None, 'El nombre es obligatorio.'
    if tipo not in _TIPOS_AREA_LIMPIEZA:
        return None, None, None, None, None, 'Tipo de área no válido.'
    producto_id = form.get('producto_id', type=int) or None
    if producto_id and db.session.get(ProductoLimpieza, producto_id) is None:
        return None, None, None, None, None, 'El producto seleccionado no existe.'
    metodo = (form.get('metodo') or '').strip() or None
    frecuencia = (form.get('frecuencia_texto') or '').strip() or None
    return nombre, tipo, producto_id, metodo, frecuencia, None


@app.route('/registros/limpieza/areas')
@login_required
@requiere_rol(['super_admin'])
def areas_limpieza_list():
    areas = AreaLimpieza.query.options(joinedload(AreaLimpieza.producto)).order_by(AreaLimpieza.nombre).all()
    productos = ProductoLimpieza.query.filter_by(activo=True).order_by(ProductoLimpieza.nombre).all()
    return render_template('registros/areas_limpieza.html', areas=areas, productos=productos)


@app.route('/registros/limpieza/areas/nueva', methods=['POST'])
@login_required
@requiere_rol(['super_admin'])
def area_limpieza_nueva():
    nombre, tipo, producto_id, metodo, frecuencia, error = _parse_area_limpieza(request.form)
    if error:
        flash(error, 'danger')
        return redirect(url_for('areas_limpieza_list'))
    db.session.add(AreaLimpieza(nombre=nombre, tipo=tipo, producto_id=producto_id,
                                metodo=metodo, frecuencia_texto=frecuencia, activa=True))
    db.session.commit()
    flash('Área creada.', 'success')
    return redirect(url_for('areas_limpieza_list'))


@app.route('/registros/limpieza/areas/<int:area_id>/editar', methods=['POST'])
@login_required
@requiere_rol(['super_admin'])
def area_limpieza_editar(area_id):
    area = AreaLimpieza.query.get_or_404(area_id)
    nombre, tipo, producto_id, metodo, frecuencia, error = _parse_area_limpieza(request.form)
    if error:
        flash(error, 'danger')
        return redirect(url_for('areas_limpieza_list'))
    area.nombre, area.tipo, area.producto_id = nombre, tipo, producto_id
    area.metodo, area.frecuencia_texto = metodo, frecuencia
    db.session.commit()
    flash('Área actualizada.', 'success')
    return redirect(url_for('areas_limpieza_list'))


@app.route('/registros/limpieza/areas/<int:area_id>/toggle', methods=['POST'])
@login_required
@requiere_rol(['super_admin'])
def area_limpieza_toggle(area_id):
    area = AreaLimpieza.query.get_or_404(area_id)
    area.activa = not area.activa
    db.session.commit()
    flash('Área actualizada.', 'success')
    return redirect(url_for('areas_limpieza_list'))
```

- [ ] **Step 4: Crear la plantilla `templates/registros/areas_limpieza.html`**

```html
{% extends "base.html" %}
{% block title %}Áreas y equipos — Limpieza{% endblock %}
{% block header_title %}<span class="fw-700 color-white">Áreas y equipos</span>{% endblock %}
{% block extra_css %}
<link rel="stylesheet" href="{{ url_for('static', filename='css/registros.css') }}">
{% endblock %}
{% block content %}
<div class="mobile-form-container reg-wrap">

  <div class="reg-toolbar">
    <a href="{{ url_for('limpieza_index') }}" class="reg-btn"><i class="fas fa-soap"></i> Registrar limpieza</a>
    <a href="{{ url_for('productos_limpieza_index') }}" class="reg-btn"><i class="fas fa-flask"></i> Productos</a>
  </div>

  <div class="mobile-card">
    <div class="mobile-card-header"><i class="fas fa-plus-circle"></i> Nueva área / equipo</div>
    <div class="mobile-card-body">
      <form method="POST" action="{{ url_for('area_limpieza_nueva') }}" autocomplete="off">
        <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
        <div class="mobile-form-group">
          <label class="mobile-form-label" for="nombre">Nombre</label>
          <input type="text" id="nombre" name="nombre" class="mobile-form-control" placeholder="Ej: Sierra de cortar" required>
        </div>
        <div class="mobile-form-group">
          <label class="mobile-form-label" for="tipo">Tipo</label>
          <select id="tipo" name="tipo" class="mobile-form-control" required>
            <option value="equipo">Equipo</option>
            <option value="espacio">Espacio</option>
          </select>
        </div>
        <div class="mobile-form-group">
          <label class="mobile-form-label" for="producto_id">Producto de limpieza</label>
          <select id="producto_id" name="producto_id" class="mobile-form-control">
            <option value="">— Sin asignar —</option>
            {% for p in productos %}
            <option value="{{ p.id }}">{{ p.nombre }} ({{ p.dilucion }})</option>
            {% endfor %}
          </select>
        </div>
        <div class="mobile-form-group">
          <label class="mobile-form-label" for="frecuencia_texto">Frecuencia</label>
          <input type="text" id="frecuencia_texto" name="frecuencia_texto" class="mobile-form-control" placeholder="Ej: Diaria, Por turno">
        </div>
        <div class="mobile-form-group">
          <label class="mobile-form-label" for="metodo">Instrucciones específicas (opcional)</label>
          <textarea id="metodo" name="metodo" class="mobile-form-control" rows="2" placeholder="Detalles propios de esta área"></textarea>
        </div>
        <div class="mobile-form-actions">
          <button type="submit" class="mobile-btn mobile-btn-primary"><i class="fas fa-save"></i> Crear área</button>
        </div>
      </form>
    </div>
  </div>

  <h3 class="reg-name" style="margin:4px 2px;"><i class="fas fa-list"></i> Áreas y equipos</h3>
  <div class="reg-list">
    {% for a in areas %}
    <article class="reg-card {{ 'is-ok' if a.activa else 'is-muted' }}">
      <div class="reg-card-head">
        <div>
          <div class="reg-name">{{ a.nombre }}</div>
          <div class="reg-sub">
            {% if a.producto %}Producto: <strong>{{ a.producto.nombre }}</strong>{% else %}Sin producto asignado{% endif %}
            {% if a.frecuencia_texto %} · {{ a.frecuencia_texto }}{% endif %}
          </div>
        </div>
        <div class="reg-chips">
          <span class="reg-pill info">{{ 'Equipo' if a.tipo == 'equipo' else 'Espacio' }}</span>
          <span class="reg-pill {{ 'ok' if a.activa else '' }}">{{ 'Activa' if a.activa else 'Inactiva' }}</span>
        </div>
      </div>

      <div class="reg-actions">
        <form method="POST" action="{{ url_for('area_limpieza_toggle', area_id=a.id) }}">
          <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
          <button type="submit" class="reg-btn">
            <i class="fas fa-{{ 'eye-slash' if a.activa else 'eye' }}"></i> {{ 'Desactivar' if a.activa else 'Activar' }}
          </button>
        </form>
      </div>

      <details class="reg-edit">
        <summary><i class="fas fa-pen"></i> Editar</summary>
        <div class="reg-edit-body">
          <form method="POST" action="{{ url_for('area_limpieza_editar', area_id=a.id) }}" autocomplete="off">
            <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
            <div class="mobile-form-group">
              <label class="mobile-form-label">Nombre</label>
              <input type="text" name="nombre" class="mobile-form-control" value="{{ a.nombre }}" required>
            </div>
            <div class="mobile-form-group">
              <label class="mobile-form-label">Tipo</label>
              <select name="tipo" class="mobile-form-control" required>
                <option value="equipo" {{ 'selected' if a.tipo == 'equipo' }}>Equipo</option>
                <option value="espacio" {{ 'selected' if a.tipo == 'espacio' }}>Espacio</option>
              </select>
            </div>
            <div class="mobile-form-group">
              <label class="mobile-form-label">Producto de limpieza</label>
              <select name="producto_id" class="mobile-form-control">
                <option value="">— Sin asignar —</option>
                {% for p in productos %}
                <option value="{{ p.id }}" {{ 'selected' if a.producto_id == p.id }}>{{ p.nombre }} ({{ p.dilucion }})</option>
                {% endfor %}
              </select>
            </div>
            <div class="mobile-form-group">
              <label class="mobile-form-label">Frecuencia</label>
              <input type="text" name="frecuencia_texto" class="mobile-form-control" value="{{ a.frecuencia_texto or '' }}">
            </div>
            <div class="mobile-form-group">
              <label class="mobile-form-label">Instrucciones específicas</label>
              <textarea name="metodo" class="mobile-form-control" rows="2">{{ a.metodo or '' }}</textarea>
            </div>
            <div class="mobile-form-actions">
              <button type="submit" class="mobile-btn mobile-btn-primary"><i class="fas fa-save"></i> Guardar cambios</button>
            </div>
          </form>
        </div>
      </details>
    </article>
    {% else %}
    <div class="reg-empty"><i class="fas fa-broom"></i>No hay áreas. Crea la primera arriba.</div>
    {% endfor %}
  </div>

</div>
{% endblock %}
```

- [ ] **Step 5: Correr los tests para verificar que pasan**

Run: `python -m pytest tests/test_registro_limpieza.py -k areas -v`
Expected: PASS (5 tests)

- [ ] **Step 6: Commit**

```bash
git add app.py templates/registros/areas_limpieza.html tests/test_registro_limpieza.py
git commit -m "feat(haccp): catalogo de areas/equipos de limpieza (CRUD admin) vinculado a productos"
```

---

## Task 4: Pantalla de registro de limpieza

**Files:**
- Modify: `app.py` (anexar tras las rutas de áreas)
- Create: `templates/registros/limpieza.html`
- Test: `tests/test_registro_limpieza.py`

- [ ] **Step 1: Añadir los tests de registro**

Agregar al final de `tests/test_registro_limpieza.py`:

```python
def test_registrar_requiere_login(app):
    client = app.test_client()
    resp = client.post('/registros/limpieza/registrar',
                       data={'area_id': IDS['area'], 'conforme': 'si'},
                       follow_redirects=False)
    assert resp.status_code == 302
    assert '/login' in resp.headers.get('Location', '')


def test_registrar_conforme(app):
    from app import RegistroLimpieza
    c = _login(app, 'vend')
    resp = c.post('/registros/limpieza/registrar',
                  data={'area_id': IDS['area'], 'conforme': 'si'}, follow_redirects=True)
    assert resp.status_code == 200
    with app.app_context():
        r = RegistroLimpieza.query.filter_by(area_id=IDS['area']).first()
        assert r is not None
        assert r.conforme is True
        assert r.registrado_por == IDS['vend']


def test_registrar_no_conforme_sin_accion_rechazado(app):
    from app import RegistroLimpieza
    c = _login(app, 'vend')
    c.post('/registros/limpieza/registrar',
           data={'area_id': IDS['area'], 'conforme': 'no'}, follow_redirects=True)
    with app.app_context():
        assert RegistroLimpieza.query.filter_by(area_id=IDS['area']).count() == 0


def test_registrar_no_conforme_con_accion(app):
    from app import RegistroLimpieza
    c = _login(app, 'vend')
    c.post('/registros/limpieza/registrar',
           data={'area_id': IDS['area'], 'conforme': 'no',
                 'accion_tomada': 'Se volvio a limpiar',
                 'accion_disposicion': 'Quedo conforme'}, follow_redirects=True)
    with app.app_context():
        r = RegistroLimpieza.query.filter_by(area_id=IDS['area']).first()
        assert r is not None
        assert r.conforme is False
        assert 'volvio a limpiar' in r.accion_tomada


def test_principal_muestra_area(app):
    c = _login(app, 'vend')
    resp = c.get('/registros/limpieza')
    assert resp.status_code == 200
    body = resp.data.decode('utf-8')
    assert 'Sierra de cortar' in body
    assert 'Sanitizante clorado' in body
```

- [ ] **Step 2: Correr los tests para verificar que fallan**

Run: `python -m pytest tests/test_registro_limpieza.py -k "registrar or principal_muestra" -v`
Expected: FAIL — 404 / `BuildError`

- [ ] **Step 3: Añadir las rutas de registro en `app.py`**

Anexar tras la ruta `area_limpieza_toggle`:

```python
def _areas_con_registro_hoy():
    """Set de area_id con al menos un registro de limpieza HOY (día local de negocio)."""
    ahora_local = datetime.now(DASHBOARD_TIMEZONE)
    inicio_local = ahora_local.replace(hour=0, minute=0, second=0, microsecond=0)
    inicio_utc = inicio_local.astimezone(timezone.utc).replace(tzinfo=None)
    fin_utc = (inicio_local + timedelta(days=1)).astimezone(timezone.utc).replace(tzinfo=None)
    filas = db.session.query(RegistroLimpieza.area_id).filter(
        RegistroLimpieza.registrado_en >= inicio_utc,
        RegistroLimpieza.registrado_en < fin_utc,
    ).distinct().all()
    return {row[0] for row in filas}


@app.route('/registros/limpieza')
@login_required
def limpieza_index():
    areas = (AreaLimpieza.query.options(joinedload(AreaLimpieza.producto))
             .filter_by(activa=True).order_by(AreaLimpieza.nombre).all())
    con_registro_hoy = _areas_con_registro_hoy()
    es_admin = isinstance(current_user, Vendedor) and current_user.rol.nombre == 'super_admin'
    return render_template('registros/limpieza.html', areas=areas,
                           con_registro_hoy=con_registro_hoy, es_admin=es_admin)


@app.route('/registros/limpieza/registrar', methods=['POST'])
@login_required
def limpieza_registrar():
    area = AreaLimpieza.query.filter_by(id=request.form.get('area_id', type=int), activa=True).first()
    if area is None:
        flash('Área no válida.', 'danger')
        return redirect(url_for('limpieza_index'))
    conforme = (request.form.get('conforme') or 'si') != 'no'
    observacion = (request.form.get('observacion') or '').strip() or None
    causa = (request.form.get('accion_causa') or '').strip()
    tomada = (request.form.get('accion_tomada') or '').strip()
    responsable = (request.form.get('accion_responsable') or '').strip()
    disposicion = (request.form.get('accion_disposicion') or '').strip()

    if not conforme and (not tomada or not disposicion):
        flash(f'El registro de {area.nombre} es No conforme. Indica al menos la acción tomada '
              f'y la disposición.', 'danger')
        return redirect(url_for('limpieza_index'))

    db.session.add(RegistroLimpieza(
        area_id=area.id,
        registrado_por=current_user.id if isinstance(current_user, Vendedor) else None,
        conforme=conforme,
        observacion=observacion,
        accion_causa=(causa or None) if not conforme else None,
        accion_tomada=(tomada or None) if not conforme else None,
        accion_responsable=(responsable or None) if not conforme else None,
        accion_disposicion=(disposicion or None) if not conforme else None,
    ))
    db.session.commit()
    flash('Limpieza registrada.' + (' (No conforme — registrada con acción correctiva.)' if not conforme else ''),
          'success' if conforme else 'warning')
    return redirect(url_for('limpieza_index'))
```

- [ ] **Step 4: Crear la plantilla `templates/registros/limpieza.html`**

```html
{% extends "base.html" %}
{% block title %}Limpieza — Registros{% endblock %}
{% block header_title %}<span class="fw-700 color-white">Registro de limpieza</span>{% endblock %}
{% block extra_css %}
<link rel="stylesheet" href="{{ url_for('static', filename='css/registros.css') }}">
{% endblock %}
{% block content %}
<div class="mobile-form-container reg-wrap">

  <div class="reg-toolbar">
    <a href="{{ url_for('limpieza_historial') }}" class="reg-btn"><i class="fas fa-clock-rotate-left"></i> Historial</a>
    <a href="{{ url_for('productos_limpieza_index') }}" class="reg-btn"><i class="fas fa-flask"></i> Productos y diluciones</a>
    {% if es_admin %}
    <a href="{{ url_for('areas_limpieza_list') }}" class="reg-btn"><i class="fas fa-broom"></i> Áreas/equipos</a>
    <a href="{{ url_for('limpieza_config') }}" class="reg-btn"><i class="fas fa-gear"></i> Configuración</a>
    {% endif %}
  </div>

  <div class="reg-list">
    {% for a in areas %}
    <article class="reg-card {{ 'is-ok' if a.id in con_registro_hoy else 'is-warn' }}">
      <div class="reg-card-head">
        <div>
          <div class="reg-name">{{ a.nombre }}</div>
          <div class="reg-sub">
            <span class="reg-pill info">{{ 'Equipo' if a.tipo == 'equipo' else 'Espacio' }}</span>
            {% if a.frecuencia_texto %} {{ a.frecuencia_texto }}{% endif %}
          </div>
        </div>
        {% if a.id in con_registro_hoy %}
          <span class="reg-pill ok"><i class="fas fa-check-circle"></i> Hoy</span>
        {% else %}
          <span class="reg-pill warn"><i class="fas fa-hourglass-half"></i> Falta hoy</span>
        {% endif %}
      </div>

      {% if a.producto %}
      <div class="reg-accion"><i class="fas fa-flask"></i>
        <strong>{{ a.producto.nombre }}</strong> · Dilución: {{ a.producto.dilucion }}
        {% if a.producto.procedimiento %}<br><strong>Procedimiento:</strong> {{ a.producto.procedimiento }}{% endif %}
      </div>
      {% endif %}
      {% if a.metodo %}
      <div class="reg-accion"><i class="fas fa-circle-info"></i> {{ a.metodo }}</div>
      {% endif %}

      <form method="POST" action="{{ url_for('limpieza_registrar') }}" autocomplete="off" class="reg-inline-form">
        <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
        <input type="hidden" name="area_id" value="{{ a.id }}">
        <div class="mobile-form-group">
          <label class="mobile-form-label" for="conforme_{{ a.id }}">Resultado</label>
          <select id="conforme_{{ a.id }}" name="conforme" class="mobile-form-control">
            <option value="si">Conforme</option>
            <option value="no">No conforme</option>
          </select>
        </div>
        <div class="mobile-form-group">
          <label class="mobile-form-label">Observación (opcional)</label>
          <input type="text" name="observacion" class="mobile-form-control" placeholder="Notas de la limpieza">
        </div>
        <details class="reg-edit">
          <summary><i class="fas fa-triangle-exclamation"></i> Acción correctiva (solo si es No conforme)</summary>
          <div class="reg-edit-body">
            <div class="mobile-form-group">
              <label class="mobile-form-label">Causa</label>
              <input type="text" name="accion_causa" class="mobile-form-control" placeholder="¿Por qué no quedó conforme?">
            </div>
            <div class="mobile-form-group">
              <label class="mobile-form-label">Acción tomada <small style="font-weight:400; opacity:.8;">(obligatoria si No conforme)</small></label>
              <textarea name="accion_tomada" class="mobile-form-control" rows="2" placeholder="¿Qué se hizo? Ej: se volvió a limpiar"></textarea>
            </div>
            <div class="mobile-form-group">
              <label class="mobile-form-label">Responsable de la acción</label>
              <input type="text" name="accion_responsable" class="mobile-form-control">
            </div>
            <div class="mobile-form-group">
              <label class="mobile-form-label">Disposición <small style="font-weight:400; opacity:.8;">(obligatoria si No conforme)</small></label>
              <textarea name="accion_disposicion" class="mobile-form-control" rows="2" placeholder="Resultado tras la corrección"></textarea>
            </div>
          </div>
        </details>
        <div class="reg-actions">
          <button type="submit" class="reg-btn reg-btn-primary"><i class="fas fa-save"></i> Registrar limpieza</button>
        </div>
      </form>
    </article>
    {% else %}
    <div class="reg-empty">
      <i class="fas fa-broom"></i>
      No hay áreas activas.{% if es_admin %} <a href="{{ url_for('areas_limpieza_list') }}">Crea una</a>.{% endif %}
    </div>
    {% endfor %}
  </div>

</div>
{% endblock %}
```

- [ ] **Step 5: Correr los tests para verificar que pasan**

Run: `python -m pytest tests/test_registro_limpieza.py -k "registrar or principal_muestra" -v`
Expected: PASS (5 tests)

- [ ] **Step 6: Commit**

```bash
git add app.py templates/registros/limpieza.html tests/test_registro_limpieza.py
git commit -m "feat(haccp): pantalla de registro de limpieza (conforme/no conforme + accion correctiva)"
```

---

## Task 5: Historial, verificación de período y PDF auditable

**Files:**
- Modify: `app.py` (anexar tras `limpieza_registrar`: helpers de filtro, historial, revisar, builder PDF y ruta de export)
- Create: `templates/registros/limpieza_historial.html`
- Test: `tests/test_registro_limpieza.py`

- [ ] **Step 1: Añadir los tests de historial y verificación**

Agregar al final de `tests/test_registro_limpieza.py`:

```python
def test_historial_lista_registros(app):
    c = _login(app, 'vend')
    c.post('/registros/limpieza/registrar',
           data={'area_id': IDS['area'], 'conforme': 'si'}, follow_redirects=True)
    resp = c.get('/registros/limpieza/historial')
    assert resp.status_code == 200
    assert 'Sierra de cortar' in resp.data.decode('utf-8')


def test_revisar_no_admin_bloqueado(app):
    from app import RevisionLimpieza
    c = _login(app, 'vend')
    resp = c.post('/registros/limpieza/revisar',
                  data={'fecha_inicio': '2026-05-01', 'fecha_fin': '2026-05-31'},
                  follow_redirects=False)
    assert resp.status_code in (302, 403)
    with app.app_context():
        assert RevisionLimpieza.query.count() == 0


def test_revisar_marca_periodo(app):
    from app import RevisionLimpieza
    c = _login(app, 'admin')
    c.post('/registros/limpieza/revisar',
           data={'fecha_inicio': '2026-05-01', 'fecha_fin': '2026-05-31'},
           follow_redirects=True)
    with app.app_context():
        rev = RevisionLimpieza.query.first()
        assert rev is not None
        assert rev.revisado_por == IDS['admin']
```

- [ ] **Step 2: Correr los tests para verificar que fallan**

Run: `python -m pytest tests/test_registro_limpieza.py -k "historial or revisar" -v`
Expected: FAIL — 404 / `BuildError`

- [ ] **Step 3: Añadir las rutas de historial y revisión en `app.py`**

Anexar tras la ruta `limpieza_registrar`:

```python
def _revision_limpieza_que_cubre(fi, ff):
    """RevisionLimpieza más reciente que cubre el período [fi, ff] ('YYYY-MM-DD')."""
    def _d(s):
        try:
            return datetime.strptime(s, '%Y-%m-%d').date() if s else None
        except ValueError:
            return None
    d_fi, d_ff = _d(fi), _d(ff)
    q = RevisionLimpieza.query
    if d_fi and d_ff:
        q = q.filter(RevisionLimpieza.periodo_desde.isnot(None),
                     RevisionLimpieza.periodo_hasta.isnot(None),
                     RevisionLimpieza.periodo_desde <= d_fi,
                     RevisionLimpieza.periodo_hasta >= d_ff)
    return q.order_by(RevisionLimpieza.revisado_en.desc()).first()


def _filtrar_registros_limpieza(args):
    """Aplica filtros opcionales (fecha_inicio, fecha_fin, area_id) y devuelve
    los registros ordenados por fecha desc. Acepta request.args o request.form."""
    q = RegistroLimpieza.query.options(
        joinedload(RegistroLimpieza.area).joinedload(AreaLimpieza.producto),
        joinedload(RegistroLimpieza.registrado_por_vendedor),
    )
    fi = args.get('fecha_inicio')
    ff = args.get('fecha_fin')
    area = args.get('area_id', type=int)
    if fi:
        try:
            q = q.filter(func.date(RegistroLimpieza.registrado_en) >= datetime.strptime(fi, '%Y-%m-%d').date())
        except ValueError:
            pass
    if ff:
        try:
            q = q.filter(func.date(RegistroLimpieza.registrado_en) <= datetime.strptime(ff, '%Y-%m-%d').date())
        except ValueError:
            pass
    if area:
        q = q.filter(RegistroLimpieza.area_id == area)
    return q.order_by(RegistroLimpieza.registrado_en.desc()).all()


@app.route('/registros/limpieza/historial')
@login_required
def limpieza_historial():
    registros = _filtrar_registros_limpieza(request.args)
    areas = AreaLimpieza.query.order_by(AreaLimpieza.nombre).all()
    puede_verificar = isinstance(current_user, Vendedor) and current_user.rol.nombre in ('super_admin', 'supervisor')
    revision = _revision_limpieza_que_cubre(request.args.get('fecha_inicio'), request.args.get('fecha_fin'))
    return render_template('registros/limpieza_historial.html',
                           registros=registros, areas=areas, filtros=request.args,
                           puede_verificar=puede_verificar, revision=revision)


@app.route('/registros/limpieza/revisar', methods=['POST'])
@login_required
@requiere_rol(['super_admin', 'supervisor'])
def limpieza_revisar():
    fi = request.form.get('fecha_inicio') or None
    ff = request.form.get('fecha_fin') or None
    def _d(s):
        try:
            return datetime.strptime(s, '%Y-%m-%d').date() if s else None
        except ValueError:
            return None
    db.session.add(RevisionLimpieza(
        revisado_por=current_user.id if isinstance(current_user, Vendedor) else None,
        periodo_desde=_d(fi), periodo_hasta=_d(ff),
    ))
    db.session.commit()
    flash('Período marcado como revisado.', 'success')
    return redirect(url_for('limpieza_historial', fecha_inicio=fi or '', fecha_fin=ff or ''))


def _build_limpieza_pdf(registros, fecha_inicio, fecha_fin, config, revision):
    """Construye el PDF tabular audit-ready del registro de limpieza."""
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=landscape(A4),
                            leftMargin=0.4 * inch, rightMargin=0.4 * inch,
                            topMargin=0.5 * inch, bottomMargin=0.7 * inch)
    cell = ParagraphStyle(name='cell', fontSize=8, leading=10, alignment=TA_LEFT)
    empresa_style = ParagraphStyle(name='reg_empresa', fontSize=10, leading=13,
                                   fontName='Helvetica-Bold', alignment=TA_LEFT,
                                   textColor=colors.HexColor('#1877ff'))
    titulo_style = ParagraphStyle(name='reg_titulo', fontSize=15, leading=18,
                                  fontName='Helvetica-Bold', alignment=TA_LEFT)
    sub_style = ParagraphStyle(name='reg_sub', fontSize=9, leading=12,
                               alignment=TA_LEFT, textColor=colors.HexColor('#475569'))

    if fecha_inicio or fecha_fin:
        periodo = f'Período: {fecha_inicio or "inicio"} a {fecha_fin or "hoy"}'
    else:
        periodo = 'Período: todas las fechas'
    generado = datetime.now(DASHBOARD_TIMEZONE).strftime('%Y-%m-%d %H:%M')

    encabezado = [
        Paragraph('Jomar Foods B.V.', empresa_style),
        Paragraph('Registro de limpieza y desinfección', titulo_style),
        Paragraph(f'Documento: {config.codigo_documento} &middot; Versión: {config.version}', sub_style),
        Paragraph(f'{periodo} &middot; Generado: {generado}', sub_style),
    ]
    logo_path = os.path.join(basedir, 'static', 'logo_etiquetas.png')
    if os.path.exists(logo_path):
        logo = Image(logo_path, width=52, height=52)
        head_tbl = Table([[logo, encabezado]], colWidths=[64, None])
        head_tbl.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('LEFTPADDING', (0, 0), (-1, -1), 0),
            ('RIGHTPADDING', (0, 0), (-1, -1), 0),
        ]))
        head_tbl.hAlign = 'LEFT'
        elements = [head_tbl, Spacer(1, 14)]
    else:
        elements = encabezado + [Spacer(1, 14)]

    def _accion_txt(r):
        partes = []
        if r.accion_causa: partes.append(f'Causa: {r.accion_causa}')
        if r.accion_tomada: partes.append(f'Acción: {r.accion_tomada}')
        if r.accion_responsable: partes.append(f'Resp.: {r.accion_responsable}')
        if r.accion_disposicion: partes.append(f'Disposición: {r.accion_disposicion}')
        return ' | '.join(partes)

    encabezados = ['Fecha/Hora', 'Área', 'Tipo', 'Producto', 'Resultado',
                   'Responsable', 'Observación / Acción correctiva']
    data = [encabezados]
    for r in registros:
        accion = _accion_txt(r)
        if r.observacion and accion:
            obs_accion = f'Obs.: {r.observacion} | {accion}'
        else:
            obs_accion = accion or (r.observacion or '')
        data.append([
            Paragraph(r.registrado_en.strftime('%Y-%m-%d %H:%M'), cell),
            Paragraph(r.area.nombre if r.area else '—', cell),
            Paragraph('Equipo' if (r.area and r.area.tipo == 'equipo') else 'Espacio', cell),
            Paragraph(r.area.producto.nombre if (r.area and r.area.producto) else '—', cell),
            Paragraph('No conforme' if not r.conforme else 'Conforme', cell),
            Paragraph(r.registrado_por_vendedor.nombre_completo if r.registrado_por_vendedor else '—', cell),
            Paragraph(obs_accion, cell),
        ])
    tabla = Table(data, repeatRows=1)
    estilo = TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1f2937')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTSIZE', (0, 0), (-1, 0), 8),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
    ])
    for i, r in enumerate(registros, start=1):
        if not r.conforme:
            estilo.add('BACKGROUND', (0, i), (-1, i), colors.HexColor('#fee2e2'))
    tabla.setStyle(estilo)
    elements.append(tabla)

    elements.append(Spacer(1, 18))
    if revision:
        nombre = revision.revisado_por_vendedor.nombre_completo if revision.revisado_por_vendedor else '—'
        rev_txt = f'<b>Verificación:</b> Revisado por {nombre} el {revision.revisado_en.strftime("%Y-%m-%d %H:%M")}'
    else:
        rev_txt = '<b>Verificación:</b> Revisado por: ______________________      Fecha: __________'
    elements.append(Paragraph(rev_txt, sub_style))

    footer_left = (f'Frecuencia: {config.frecuencia_texto or "N/D"}   |   '
                   f'Responsable de verificación: {config.responsable_verificacion or "N/D"}')
    footer_doc = f'{config.codigo_documento} v{config.version}'
    page_w = landscape(A4)[0]

    class _NumberedCanvas(canvas.Canvas):
        def __init__(self, *a, **k):
            canvas.Canvas.__init__(self, *a, **k)
            self._saved_states = []
        def showPage(self):
            self._saved_states.append(dict(self.__dict__))
            self._startPage()
        def save(self):
            total = len(self._saved_states)
            for st in self._saved_states:
                self.__dict__.update(st)
                self.setFont('Helvetica', 7)
                self.setFillColor(colors.HexColor('#475569'))
                self.drawString(0.4 * inch, 0.35 * inch, footer_left)
                self.drawRightString(page_w - 0.4 * inch, 0.35 * inch,
                                     f'{footer_doc}  ·  Página {self._pageNumber} de {total}')
                canvas.Canvas.showPage(self)
            canvas.Canvas.save(self)

    doc.build(elements, canvasmaker=_NumberedCanvas)
    buffer.seek(0)
    return buffer


@app.route('/registros/limpieza/export', methods=['POST'])
@login_required
def limpieza_export():
    registros = _filtrar_registros_limpieza(request.form)
    fi = request.form.get('fecha_inicio') or ''
    ff = request.form.get('fecha_fin') or ''
    config = _get_limpieza_config()
    revision = _revision_limpieza_que_cubre(fi, ff)
    buffer = _build_limpieza_pdf(registros, fi, ff, config, revision)
    filename = f"registro_limpieza_{fi or 'inicio'}_{ff or 'fin'}.pdf"
    response = make_response(send_file(buffer, mimetype='application/pdf',
                                       as_attachment=not _is_ios_request(),
                                       download_name=filename))
    response.headers['Content-Type'] = 'application/pdf'
    return response
```

> El builder `_build_limpieza_pdf` y la ruta `limpieza_export` se definen aquí (junto con historial/revisar) para que `url_for('limpieza_export')`, usado por la plantilla del historial, resuelva correctamente. El test del PDF se añade en la Task 6.

- [ ] **Step 4: Crear la plantilla `templates/registros/limpieza_historial.html`**

```html
{% extends "base.html" %}
{% block title %}Historial limpieza{% endblock %}
{% block header_title %}<span class="fw-700 color-white">Historial de limpieza</span>{% endblock %}
{% block extra_css %}
<link rel="stylesheet" href="{{ url_for('static', filename='css/registros.css') }}">
{% endblock %}
{% block content %}
<div class="mobile-form-container reg-wrap">

  <div class="reg-toolbar">
    <a href="{{ url_for('limpieza_index') }}" class="reg-btn"><i class="fas fa-soap"></i> Registrar</a>
  </div>

  <div class="mobile-card">
    <div class="mobile-card-header"><i class="fas fa-filter"></i> Filtros</div>
    <div class="mobile-card-body">
      <form method="GET" action="{{ url_for('limpieza_historial') }}">
        <div class="reg-field-row">
          <div class="mobile-form-group">
            <label class="mobile-form-label" for="fecha_inicio">Desde</label>
            <input type="date" id="fecha_inicio" name="fecha_inicio" class="mobile-form-control" value="{{ filtros.get('fecha_inicio', '') }}">
          </div>
          <div class="mobile-form-group">
            <label class="mobile-form-label" for="fecha_fin">Hasta</label>
            <input type="date" id="fecha_fin" name="fecha_fin" class="mobile-form-control" value="{{ filtros.get('fecha_fin', '') }}">
          </div>
        </div>
        <div class="mobile-form-group">
          <label class="mobile-form-label" for="area_id">Área / equipo</label>
          <select id="area_id" name="area_id" class="mobile-form-control">
            <option value="">Todas</option>
            {% for a in areas %}
            <option value="{{ a.id }}" {{ 'selected' if filtros.get('area_id') == a.id|string }}>{{ a.nombre }}</option>
            {% endfor %}
          </select>
        </div>
        <div class="mobile-form-actions">
          <button type="submit" class="mobile-btn mobile-btn-primary"><i class="fas fa-search"></i> Filtrar</button>
          <button type="submit" form="export-form" class="mobile-btn mobile-btn-success"><i class="fas fa-file-pdf"></i> Exportar PDF</button>
        </div>
      </form>
      <form id="export-form" method="POST" action="{{ url_for('limpieza_export') }}" target="etiquetas-download-frame">
        <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
        <input type="hidden" name="fecha_inicio" value="{{ filtros.get('fecha_inicio', '') }}">
        <input type="hidden" name="fecha_fin" value="{{ filtros.get('fecha_fin', '') }}">
        <input type="hidden" name="area_id" value="{{ filtros.get('area_id', '') }}">
      </form>
    </div>
  </div>

  {% if revision %}
  <div class="reg-card is-ok">
    <div class="reg-name"><i class="fas fa-clipboard-check"></i> Período verificado</div>
    <div class="reg-sub">Revisado por <strong>{{ revision.revisado_por_vendedor.nombre_completo if revision.revisado_por_vendedor else '—' }}</strong> el {{ revision.revisado_en.strftime('%Y-%m-%d %H:%M') }}</div>
  </div>
  {% endif %}
  {% if puede_verificar %}
  <form method="POST" action="{{ url_for('limpieza_revisar') }}">
    <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
    <input type="hidden" name="fecha_inicio" value="{{ filtros.get('fecha_inicio', '') }}">
    <input type="hidden" name="fecha_fin" value="{{ filtros.get('fecha_fin', '') }}">
    <button type="submit" class="reg-btn reg-btn-primary"><i class="fas fa-clipboard-check"></i> Marcar período como revisado</button>
  </form>
  {% endif %}
  <h3 class="reg-name" style="margin:4px 2px;"><i class="fas fa-list"></i> Registros</h3>
  <div class="reg-list">
    {% for r in registros %}
    <article class="reg-row {{ 'is-danger' if not r.conforme else '' }}">
      <div class="reg-row-main">
        <div class="reg-name">{{ r.area.nombre }}</div>
        <div class="reg-sub">{{ r.registrado_en.strftime('%Y-%m-%d %H:%M') }}{% if r.registrado_por_vendedor %} · {{ r.registrado_por_vendedor.nombre_completo }}{% endif %}</div>
        {% if r.observacion %}
        <div class="reg-accion"><i class="fas fa-comment"></i> {{ r.observacion }}</div>
        {% endif %}
        {% if not r.conforme and (r.accion_tomada or r.accion_disposicion or r.accion_causa) %}
        <div class="reg-accion"><i class="fas fa-wrench"></i>
          {% if r.accion_causa %}<strong>Causa:</strong> {{ r.accion_causa }} · {% endif %}
          {% if r.accion_tomada %}<strong>Acción:</strong> {{ r.accion_tomada }} · {% endif %}
          {% if r.accion_responsable %}<strong>Resp.:</strong> {{ r.accion_responsable }} · {% endif %}
          {% if r.accion_disposicion %}<strong>Disposición:</strong> {{ r.accion_disposicion }}{% endif %}
        </div>
        {% endif %}
      </div>
      <div style="text-align:right;">
        {% if not r.conforme %}<span class="reg-pill danger">No conforme</span>{% else %}<span class="reg-pill ok">Conforme</span>{% endif %}
      </div>
    </article>
    {% else %}
    <div class="reg-empty"><i class="fas fa-clipboard-list"></i>No hay registros para los filtros seleccionados.</div>
    {% endfor %}
  </div>

</div>
<script src="{{ url_for('static', filename='js/etiquetas_ios_share.js') }}"></script>
<script>
  (function () {
    var exportForm = document.getElementById('export-form');
    if (!exportForm) return;
    function syncFiltros() {
      ['fecha_inicio', 'fecha_fin', 'area_id'].forEach(function (name) {
        var visible = document.getElementById(name);
        var hidden = exportForm.querySelector('[name="' + name + '"]');
        if (visible && hidden) hidden.value = visible.value;
      });
    }
    exportForm.addEventListener('submit', function (e) {
      syncFiltros();
      if (window.esDispositivoIOS && window.esDispositivoIOS()) {
        e.preventDefault();
        var fd = new FormData(exportForm);
        window.compartirEtiquetaIOS(exportForm.action, fd, 'registro_limpieza.pdf');
      }
    });
  })();
</script>
{% endblock %}
```

> Nota: la plantilla y el `<script>` referencian `url_for('limpieza_export')`, endpoint que ya quedó registrado en el Step 3 de esta misma tarea, por lo que el historial renderiza sin `BuildError`.

- [ ] **Step 5: Correr los tests para verificar que pasan**

Run: `python -m pytest tests/test_registro_limpieza.py -k "historial or revisar" -v`
Expected: PASS (3 tests)

- [ ] **Step 6: Commit**

```bash
git add app.py templates/registros/limpieza_historial.html tests/test_registro_limpieza.py
git commit -m "feat(haccp): historial de limpieza, verificacion de periodo y PDF auditable"
```

---

## Task 6: Verificación del PDF de limpieza

**Files:**
- Test: `tests/test_registro_limpieza.py`

> El builder `_build_limpieza_pdf` y la ruta `limpieza_export` ya se implementaron en la Task 5 (eran prerequisito para que la plantilla del historial renderizara). Esta tarea solo agrega el test que verifica que el endpoint devuelve un PDF. **No vuelvas a añadir el builder ni la ruta** (un segundo `@app.route('/registros/limpieza/export')` rompería el arranque por endpoint duplicado).

- [ ] **Step 1: Añadir el test de export**

Agregar al final de `tests/test_registro_limpieza.py`:

```python
def test_export_devuelve_pdf(app):
    c = _login(app, 'vend')
    c.post('/registros/limpieza/registrar',
           data={'area_id': IDS['area'], 'conforme': 'si'}, follow_redirects=True)
    resp = c.post('/registros/limpieza/export',
                  data={'fecha_inicio': '2000-01-01', 'fecha_fin': '2100-01-01'},
                  follow_redirects=False)
    assert resp.status_code == 200
    assert 'application/pdf' in resp.headers.get('Content-Type', '')
```

- [ ] **Step 2: Correr el test para verificar que pasa**

Run: `python -m pytest tests/test_registro_limpieza.py::test_export_devuelve_pdf -v`
Expected: PASS (la ruta `limpieza_export` ya existe desde la Task 5; el test confirma que genera el PDF sin error).

- [ ] **Step 3: Commit**

```bash
git add tests/test_registro_limpieza.py
git commit -m "test(haccp): verifica que el export de limpieza devuelve PDF"
```

---

## Task 7: Pantalla de configuración del registro de limpieza

**Files:**
- Modify: `app.py` (anexar tras `limpieza_export`)
- Create: `templates/registros/limpieza_config.html`
- Test: `tests/test_registro_limpieza.py`

- [ ] **Step 1: Añadir los tests de config**

Agregar al final de `tests/test_registro_limpieza.py`:

```python
def test_config_no_admin_bloqueado(app):
    c = _login(app, 'vend')
    resp = c.get('/registros/limpieza/config', follow_redirects=False)
    assert resp.status_code in (302, 403)


def test_config_admin_guarda(app):
    from app import LimpiezaConfig
    c = _login(app, 'admin')
    c.post('/registros/limpieza/config',
           data={'codigo_documento': 'FR-HACCP-LIMP-02', 'version': '2',
                 'frecuencia_texto': 'Diaria', 'responsable_verificacion': 'Jefe de calidad'},
           follow_redirects=True)
    with app.app_context():
        cfg = LimpiezaConfig.query.first()
        assert cfg.codigo_documento == 'FR-HACCP-LIMP-02'
        assert cfg.responsable_verificacion == 'Jefe de calidad'
```

- [ ] **Step 2: Correr los tests para verificar que fallan**

Run: `python -m pytest tests/test_registro_limpieza.py -k config -v`
Expected: FAIL — 404 / `BuildError`

- [ ] **Step 3: Añadir la ruta de config en `app.py`**

Anexar tras la ruta `limpieza_export`:

```python
@app.route('/registros/limpieza/config', methods=['GET', 'POST'])
@login_required
@requiere_rol(['super_admin'])
def limpieza_config():
    cfg = _get_limpieza_config()
    if request.method == 'POST':
        cfg.codigo_documento = (request.form.get('codigo_documento') or '').strip() or 'FR-HACCP-LIMP-01'
        cfg.version = (request.form.get('version') or '').strip() or '1'
        cfg.frecuencia_texto = (request.form.get('frecuencia_texto') or '').strip() or 'Según programa de limpieza'
        cfg.responsable_verificacion = (request.form.get('responsable_verificacion') or '').strip() or None
        cfg.actualizado_en = datetime.utcnow()
        db.session.commit()
        flash('Configuración guardada.', 'success')
        return redirect(url_for('limpieza_config'))
    return render_template('registros/limpieza_config.html', cfg=cfg)
```

- [ ] **Step 4: Crear la plantilla `templates/registros/limpieza_config.html`**

```html
{% extends "base.html" %}
{% block title %}Configuración del registro de limpieza{% endblock %}
{% block header_title %}<span class="fw-700 color-white">Configuración de limpieza</span>{% endblock %}
{% block extra_css %}
<link rel="stylesheet" href="{{ url_for('static', filename='css/registros.css') }}">
{% endblock %}
{% block content %}
<div class="mobile-form-container reg-wrap">
  <div class="reg-toolbar">
    <a href="{{ url_for('limpieza_index') }}" class="reg-btn"><i class="fas fa-soap"></i> Registrar limpieza</a>
  </div>
  <div class="mobile-card">
    <div class="mobile-card-header"><i class="fas fa-gear"></i> Datos del documento</div>
    <div class="mobile-card-body">
      <form method="POST" action="{{ url_for('limpieza_config') }}" autocomplete="off">
        <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
        <div class="reg-field-row">
          <div class="mobile-form-group">
            <label class="mobile-form-label" for="codigo_documento">Código de documento</label>
            <input type="text" id="codigo_documento" name="codigo_documento" class="mobile-form-control" value="{{ cfg.codigo_documento }}">
          </div>
          <div class="mobile-form-group">
            <label class="mobile-form-label" for="version">Versión</label>
            <input type="text" id="version" name="version" class="mobile-form-control" value="{{ cfg.version }}">
          </div>
        </div>
        <div class="mobile-form-group">
          <label class="mobile-form-label" for="frecuencia_texto">Frecuencia de limpieza</label>
          <input type="text" id="frecuencia_texto" name="frecuencia_texto" class="mobile-form-control" value="{{ cfg.frecuencia_texto }}" placeholder="Ej: Según programa de limpieza">
        </div>
        <div class="mobile-form-group">
          <label class="mobile-form-label" for="responsable_verificacion">Responsable de verificación</label>
          <input type="text" id="responsable_verificacion" name="responsable_verificacion" class="mobile-form-control" value="{{ cfg.responsable_verificacion or '' }}" placeholder="Ej: Jefe de calidad">
        </div>
        <div class="mobile-form-actions">
          <button type="submit" class="mobile-btn mobile-btn-primary"><i class="fas fa-save"></i> Guardar configuración</button>
        </div>
      </form>
    </div>
  </div>
</div>
{% endblock %}
```

- [ ] **Step 5: Correr los tests para verificar que pasan**

Run: `python -m pytest tests/test_registro_limpieza.py -k config -v`
Expected: PASS (2 tests)

- [ ] **Step 6: Commit**

```bash
git add app.py templates/registros/limpieza_config.html tests/test_registro_limpieza.py
git commit -m "feat(haccp): pantalla de configuracion del registro de limpieza"
```

---

## Task 8: Hub de Registros y navegación

**Files:**
- Modify: `app.py` (anexar tras `limpieza_config`)
- Create: `templates/registros/index.html`
- Modify: `templates/base.html` (2 enlaces de menú)
- Test: `tests/test_registro_limpieza.py`

- [ ] **Step 1: Añadir el test del hub**

Agregar al final de `tests/test_registro_limpieza.py`:

```python
def test_hub_registros_ok(app):
    c = _login(app, 'vend')
    resp = c.get('/registros')
    assert resp.status_code == 200
    body = resp.data.decode('utf-8')
    assert 'Temperaturas' in body
    assert 'Limpieza' in body
```

- [ ] **Step 2: Correr el test para verificar que falla**

Run: `python -m pytest tests/test_registro_limpieza.py::test_hub_registros_ok -v`
Expected: FAIL — 404 / `BuildError`

- [ ] **Step 3: Añadir la ruta hub en `app.py`**

Anexar tras la ruta `limpieza_config`:

```python
@app.route('/registros')
@login_required
def registros_index():
    return render_template('registros/index.html')
```

- [ ] **Step 4: Crear la plantilla `templates/registros/index.html`**

```html
{% extends "base.html" %}
{% block title %}Registros HACCP{% endblock %}
{% block header_title %}<span class="fw-700 color-white">Registros HACCP</span>{% endblock %}
{% block extra_css %}
<link rel="stylesheet" href="{{ url_for('static', filename='css/registros.css') }}">
{% endblock %}
{% block content %}
<div class="mobile-form-container reg-wrap">
  <div class="reg-list">
    <a class="reg-card" style="display:block; text-decoration:none;" href="{{ url_for('temperaturas_index') }}">
      <div class="reg-card-head">
        <div>
          <div class="reg-name"><i class="fas fa-temperature-half"></i> Temperaturas</div>
          <div class="reg-sub">Registro de temperaturas de cámaras</div>
        </div>
        <i class="fas fa-chevron-right"></i>
      </div>
    </a>
    <a class="reg-card" style="display:block; text-decoration:none;" href="{{ url_for('limpieza_index') }}">
      <div class="reg-card-head">
        <div>
          <div class="reg-name"><i class="fas fa-soap"></i> Limpieza</div>
          <div class="reg-sub">Registro de limpieza y desinfección</div>
        </div>
        <i class="fas fa-chevron-right"></i>
      </div>
    </a>
  </div>
</div>
{% endblock %}
```

- [ ] **Step 5: Actualizar los 2 enlaces "Registros" en `templates/base.html`**

Cambiar el enlace del drawer (busca el bloque con `class="drawer-item"` y `<span>Registros</span>`):

Reemplazar:
```html
                <a href="{{ url_for('temperaturas_index') }}" class="drawer-item">
                    <i class="fas fa-temperature-half"></i><span>Registros</span>
                </a>
```
por:
```html
                <a href="{{ url_for('registros_index') }}" class="drawer-item">
                    <i class="fas fa-clipboard-list"></i><span>Registros</span>
                </a>
```

Cambiar el enlace del dropdown (busca el bloque con `class="dropdown-item"` y `<span>Registros</span>`):

Reemplazar:
```html
                                <a href="{{ url_for('temperaturas_index') }}" class="dropdown-item">
                                    <i class="fas fa-temperature-half"></i><span>Registros</span>
                                </a>
```
por:
```html
                                <a href="{{ url_for('registros_index') }}" class="dropdown-item">
                                    <i class="fas fa-clipboard-list"></i><span>Registros</span>
                                </a>
```

- [ ] **Step 6: Correr el test del hub y la suite completa**

Run: `python -m pytest tests/test_registro_limpieza.py -v`
Expected: PASS (todos)

- [ ] **Step 7: Commit**

```bash
git add app.py templates/registros/index.html templates/base.html tests/test_registro_limpieza.py
git commit -m "feat(haccp): hub de Registros (temperaturas + limpieza) y enlaces de menu"
```

---

## Task 9: Suite completa + creación de tablas locales + verificación de sintaxis

**Files:**
- (verificación, sin cambios de código nuevos salvo eventuales fixes)

- [ ] **Step 1: Verificar sintaxis de `app.py`**

Run: `python -c "import ast; ast.parse(open('app.py').read()); print('OK sintaxis')"`
Expected: `OK sintaxis`

- [ ] **Step 2: Correr toda la suite de tests del proyecto**

Run: `python -m pytest tests/test_registro_limpieza.py tests/test_registro_temperaturas.py -v`
Expected: PASS (ambos archivos, sin romper temperaturas)

- [ ] **Step 3: Crear las tablas en la base local (si se usa Postgres local)**

Si el entorno local usa Postgres (no SQLite), crear las tablas. En un shell de Python del proyecto:

```bash
python -c "from app import app, db; ctx=app.app_context(); ctx.push(); db.create_all(); print('tablas creadas')"
```

Expected: `tablas creadas` (crea solo las que faltan; no toca las existentes).

- [ ] **Step 4: Commit (si hubo fixes)**

```bash
git add -A
git commit -m "test(haccp): suite de registro de limpieza en verde" || echo "sin cambios"
```

---

## Task 10: Migración en Heroku y deploy

**Files:**
- (despliegue, sin cambios de código)

> Según memoria del proyecto: **siempre correr migraciones en Heroku**; `db.create_all()` local no afecta producción. Crear las tablas con SQL explícito vía `heroku pg:psql`.

- [ ] **Step 1: Crear las 5 tablas en Heroku**

Run:
```bash
heroku pg:psql --app pesosapp <<'SQL'
CREATE TABLE IF NOT EXISTS producto_limpieza (
    id SERIAL PRIMARY KEY,
    nombre VARCHAR(120) NOT NULL,
    dilucion VARCHAR(255) NOT NULL,
    procedimiento TEXT,
    notas_seguridad TEXT,
    activo BOOLEAN NOT NULL DEFAULT TRUE,
    creado_en TIMESTAMP NOT NULL DEFAULT (now() AT TIME ZONE 'utc')
);
CREATE TABLE IF NOT EXISTS area_limpieza (
    id SERIAL PRIMARY KEY,
    nombre VARCHAR(120) NOT NULL,
    tipo VARCHAR(20) NOT NULL DEFAULT 'equipo',
    producto_id INTEGER REFERENCES producto_limpieza(id),
    metodo TEXT,
    frecuencia_texto VARCHAR(120),
    activa BOOLEAN NOT NULL DEFAULT TRUE,
    creado_en TIMESTAMP NOT NULL DEFAULT (now() AT TIME ZONE 'utc')
);
CREATE TABLE IF NOT EXISTS registro_limpieza (
    id SERIAL PRIMARY KEY,
    area_id INTEGER NOT NULL REFERENCES area_limpieza(id),
    registrado_por INTEGER REFERENCES vendedor(id),
    registrado_en TIMESTAMP NOT NULL DEFAULT (now() AT TIME ZONE 'utc'),
    conforme BOOLEAN NOT NULL DEFAULT TRUE,
    observacion TEXT,
    accion_causa TEXT,
    accion_tomada TEXT,
    accion_responsable VARCHAR(120),
    accion_disposicion TEXT
);
CREATE INDEX IF NOT EXISTS ix_registro_limpieza_area_id ON registro_limpieza(area_id);
CREATE INDEX IF NOT EXISTS ix_registro_limpieza_registrado_en ON registro_limpieza(registrado_en);
CREATE TABLE IF NOT EXISTS limpieza_config (
    id SERIAL PRIMARY KEY,
    codigo_documento VARCHAR(60) NOT NULL DEFAULT 'FR-HACCP-LIMP-01',
    version VARCHAR(20) NOT NULL DEFAULT '1',
    frecuencia_texto VARCHAR(120) NOT NULL DEFAULT 'Según programa de limpieza',
    responsable_verificacion VARCHAR(120),
    actualizado_en TIMESTAMP NOT NULL DEFAULT (now() AT TIME ZONE 'utc')
);
CREATE TABLE IF NOT EXISTS revision_limpieza (
    id SERIAL PRIMARY KEY,
    revisado_por INTEGER REFERENCES vendedor(id),
    revisado_en TIMESTAMP NOT NULL DEFAULT (now() AT TIME ZONE 'utc'),
    periodo_desde DATE,
    periodo_hasta DATE,
    nota TEXT
);
SQL
```
Expected: `CREATE TABLE` / `CREATE INDEX` sin errores.

- [ ] **Step 2: Deploy a producción**

Run:
```bash
git push origin main && git push heroku main
```
Expected: build OK, `Released vNNN` en Heroku.

- [ ] **Step 3: Reiniciar el dyno**

Run: `heroku restart --app pesosapp`
Expected: `Restarting dynos... done`

- [ ] **Step 4: Verificación manual (smoke test en producción)**

Abrir `https://pesosapp-caa46963237c.herokuapp.com/registros` autenticado como super_admin y verificar:
1. El hub muestra Temperaturas y Limpieza.
2. Crear un producto en Productos y diluciones.
3. Crear un área/equipo vinculada a ese producto.
4. Registrar una limpieza Conforme y una No conforme (con acción correctiva).
5. Ver el historial y exportar el PDF.
6. Marcar el período como revisado.

---

## Self-Review (completado por el autor del plan)

**1. Cobertura del spec:**
- Modelos (5) → Task 1 ✓
- ProductoLimpieza consulta + CRUD → Task 2 ✓
- AreaLimpieza CRUD vinculado a producto → Task 3 ✓
- Registro Conforme/No conforme + acción correctiva → Task 4 ✓
- Historial + verificación de período → Task 5 ✓
- PDF auditable → Task 5 (builder/ruta) + Task 6 (test) ✓
- Config documento → Task 7 ✓
- Hub /registros + navegación → Task 8 ✓
- Integración "ver dilución/procedimiento al registrar" → plantilla `limpieza.html` en Task 4 ✓
- DB local + Heroku → Tasks 9 y 10 ✓

**2. Placeholders:** ninguno; todo el código (rutas, plantillas, tests, SQL) está completo.

**3. Consistencia de tipos/nombres:** endpoints usados en plantillas coinciden con funciones definidas: `limpieza_index`, `limpieza_registrar`, `limpieza_historial`, `limpieza_revisar`, `limpieza_export`, `limpieza_config`, `productos_limpieza_index`, `producto_limpieza_nuevo/editar/toggle`, `areas_limpieza_list`, `area_limpieza_nueva/editar/toggle`, `registros_index`. Campos del modelo (`conforme`, `observacion`, `accion_*`, `producto_id`, `frecuencia_texto`) consistentes entre modelos, rutas, plantillas y tests.

**Nota de orden de ejecución:** la plantilla `limpieza_historial.html` referencia `url_for('limpieza_export')`. Por eso el builder `_build_limpieza_pdf` y la ruta `limpieza_export` se definen dentro de la **Task 5** (no en la Task 6), de modo que el endpoint ya está registrado cuando el historial se renderiza y los tests de la Task 5 pasan sin `BuildError`. La **Task 6** solo agrega el test del PDF; no debe redefinir la ruta (evita endpoint duplicado).
