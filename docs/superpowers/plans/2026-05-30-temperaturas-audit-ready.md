# Registro de temperaturas audit-ready (HACCP) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Volver auditable el registro de temperaturas: configuración del documento/instrumento, acción correctiva estructurada, verificación en la app y un PDF con control de documento.

**Architecture:** Dos modelos nuevos en `app.py` (`RegistroConfig` singleton, `RevisionRegistro`) + 4 columnas nuevas en `LecturaTemperatura`; rutas bajo `/registros/temperaturas/*`; plantillas mobile-first con `registros.css`; PDF reportlab con pie de página numerado.

**Tech Stack:** Flask, SQLAlchemy, Flask-Login, Jinja2, reportlab Platypus, pytest.

**Convenciones:** tests con `.venv311/bin/python -m pytest`. Ya importados (no re-importar): `db, datetime, date, Decimal, InvalidOperation, func, request, flash, redirect, url_for, render_template, login_required, current_user, Vendedor, Camara, LecturaTemperatura, requiere_rol, BytesIO, landscape, A4, inch, colors, SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image, getSampleStyleSheet, ParagraphStyle, TA_LEFT, os, basedir, DASHBOARD_TIMEZONE`, `canvas` (de `from reportlab.pdfgen import canvas`).

---

### Task 1: Modelos + helper de configuración (TDD)

**Files:**
- Modify: `app.py` (modelos tras `class LecturaTemperatura`; 4 columnas dentro de `LecturaTemperatura`; helper `_get_registro_config` junto a los helpers HACCP)
- Test: `tests/test_temperaturas_audit.py` (crear)

- [ ] **Step 1: Escribir el test que falla**

Crear `tests/test_temperaturas_audit.py`:

```python
"""Tests de las mejoras audit-ready del registro de temperaturas."""
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
    flask_app.config.update(TESTING=True, WTF_CSRF_ENABLED=False,
                            SQLALCHEMY_DATABASE_URI='sqlite:///:memory:')
    with flask_app.app_context():
        _db.create_all()
        from app import Rol, Territorio, Vendedor, Camara
        roles = {}
        for n in ('super_admin', 'supervisor', 'vendedor'):
            r = Rol(nombre=n, descripcion=n)
            _db.session.add(r); roles[n] = r
        terr = Territorio(nombre='t1', descripcion='T1')
        _db.session.add(terr); _db.session.flush()
        for u, rol in (('admin', 'super_admin'), ('super', 'supervisor'), ('vend', 'vendedor')):
            v = Vendedor(username=u, email=f'{u}@t.com', nombre_completo=u.title(),
                         rol_id=roles[rol].id, territorio_id=terr.id, activo=True)
            v.set_password('pw'); _db.session.add(v)
        cam = Camara(nombre='Cava 1', tipo='refrigeracion',
                     temp_min=Decimal('0'), temp_max=Decimal('4'), activa=True)
        _db.session.add(cam); _db.session.commit()
        IDS['camara'] = cam.id
        yield flask_app
        _db.drop_all()


def _login(app, username):
    c = app.test_client()
    c.post('/login', data={'username': username, 'password': 'pw'}, follow_redirects=True)
    return c


def test_get_registro_config_singleton(app):
    from app import _get_registro_config, RegistroConfig
    with app.app_context():
        c1 = _get_registro_config()
        c2 = _get_registro_config()
        assert c1.id == c2.id
        assert RegistroConfig.query.count() == 1
        assert c1.codigo_documento  # tiene un valor por defecto


def test_revision_y_columnas_accion_existen(app):
    from app import RevisionRegistro, LecturaTemperatura
    from datetime import date
    with app.app_context():
        rev = RevisionRegistro(periodo_desde=date(2026, 5, 1), periodo_hasta=date(2026, 5, 31))
        _db.session.add(rev)
        lec = LecturaTemperatura(camara_id=IDS['camara'], temperatura=Decimal('2'),
                                 fuera_de_rango=False, accion_tomada='x', accion_disposicion='y',
                                 accion_causa='c', accion_responsable='r')
        _db.session.add(lec); _db.session.commit()
        assert RevisionRegistro.query.count() == 1
        got = LecturaTemperatura.query.get(lec.id)
        assert got.accion_tomada == 'x' and got.accion_disposicion == 'y'
```

- [ ] **Step 2: Correr y verificar que falla**

Run: `.venv311/bin/python -m pytest tests/test_temperaturas_audit.py -q`
Expected: FAIL (no existen `_get_registro_config`/`RegistroConfig`/`RevisionRegistro`/columnas).

- [ ] **Step 3: Agregar las 4 columnas a `LecturaTemperatura`**

En `app.py`, en la clase `LecturaTemperatura`, justo después de la línea
`accion_correctiva = db.Column(db.Text, nullable=True)`, agregar:

```python
    accion_causa = db.Column(db.Text, nullable=True)
    accion_tomada = db.Column(db.Text, nullable=True)
    accion_responsable = db.Column(db.String(120), nullable=True)
    accion_disposicion = db.Column(db.Text, nullable=True)
```

- [ ] **Step 4: Agregar los modelos nuevos**

En `app.py`, inmediatamente DESPUÉS de la clase `LecturaTemperatura` (tras su
`def __repr__`), agregar:

```python
class RegistroConfig(db.Model):
    """Configuración (fila única) del registro de temperaturas para el PDF."""
    __tablename__ = 'registro_config'
    id = db.Column(db.Integer, primary_key=True)
    codigo_documento = db.Column(db.String(60), nullable=False, default='FR-HACCP-TEMP-01')
    version = db.Column(db.String(20), nullable=False, default='1')
    frecuencia_texto = db.Column(db.String(120), nullable=False, default='2 veces al día')
    termometro = db.Column(db.String(120), nullable=True)
    termometro_calibrado_en = db.Column(db.Date, nullable=True)
    actualizado_en = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    def __repr__(self):
        return f'<RegistroConfig {self.codigo_documento} v{self.version}>'


class RevisionRegistro(db.Model):
    """Verificación HACCP: un responsable revisa los registros de un período."""
    __tablename__ = 'revision_registro'
    id = db.Column(db.Integer, primary_key=True)
    revisado_por = db.Column(db.Integer, db.ForeignKey('vendedor.id'), nullable=True)
    revisado_en = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    periodo_desde = db.Column(db.Date, nullable=True)
    periodo_hasta = db.Column(db.Date, nullable=True)
    nota = db.Column(db.Text, nullable=True)

    revisado_por_vendedor = db.relationship('Vendedor')

    def __repr__(self):
        return f'<RevisionRegistro {self.id} por={self.revisado_por}>'
```

- [ ] **Step 5: Agregar el helper `_get_registro_config`**

En `app.py`, justo antes del comentario `# ───────────────────────── HACCP: Cámaras ─────────────────────────` (donde están las rutas HACCP), agregar:

```python
def _get_registro_config():
    """Devuelve la fila única de RegistroConfig; la crea con valores por
    defecto si aún no existe."""
    cfg = RegistroConfig.query.first()
    if cfg is None:
        cfg = RegistroConfig()
        db.session.add(cfg)
        db.session.commit()
    return cfg
```

- [ ] **Step 6: Correr y verificar que pasa**

Run: `.venv311/bin/python -m pytest tests/test_temperaturas_audit.py -q`
Expected: PASS (2 tests).

- [ ] **Step 7: Commit**

```bash
git add app.py tests/test_temperaturas_audit.py
git commit -m "feat(haccp): modelos RegistroConfig, RevisionRegistro y columnas de acción correctiva"
```

---

### Task 2: Pantalla de configuración (super_admin)

**Files:**
- Modify: `app.py` (rutas config, junto a las rutas HACCP, antes de `if __name__ == '__main__':`)
- Create: `templates/registros/config.html`
- Modify: `templates/registros/temperaturas.html` (enlace "Configuración" en el toolbar)
- Test: `tests/test_temperaturas_audit.py` (append)

- [ ] **Step 1: Escribir los tests que fallan**

Append a `tests/test_temperaturas_audit.py`:

```python
def test_config_no_admin_bloqueado(app):
    c = _login(app, 'vend')
    resp = c.post('/registros/temperaturas/config',
                  data={'codigo_documento': 'X', 'version': '9', 'frecuencia_texto': 'f'},
                  follow_redirects=False)
    assert resp.status_code in (302, 403)
    from app import RegistroConfig
    with app.app_context():
        cfg = RegistroConfig.query.first()
        assert cfg is None or cfg.codigo_documento != 'X'


def test_config_admin_guarda(app):
    c = _login(app, 'admin')
    resp = c.post('/registros/temperaturas/config',
                  data={'codigo_documento': 'FR-9', 'version': '2',
                        'frecuencia_texto': '3 veces/día', 'termometro': 'TP-1',
                        'termometro_calibrado_en': '2026-01-15'},
                  follow_redirects=True)
    assert resp.status_code == 200
    from app import RegistroConfig
    with app.app_context():
        cfg = RegistroConfig.query.first()
        assert cfg.codigo_documento == 'FR-9'
        assert cfg.termometro == 'TP-1'
        assert cfg.termometro_calibrado_en.isoformat() == '2026-01-15'
```

- [ ] **Step 2: Correr y verificar que fallan**

Run: `.venv311/bin/python -m pytest tests/test_temperaturas_audit.py -q`
Expected: FAIL (ruta config inexistente → 404).

- [ ] **Step 3: Implementar la ruta config**

En `app.py`, antes de `if __name__ == '__main__':`, agregar:

```python
@app.route('/registros/temperaturas/config', methods=['GET', 'POST'])
@login_required
@requiere_rol(['super_admin'])
def registro_config():
    cfg = _get_registro_config()
    if request.method == 'POST':
        cfg.codigo_documento = (request.form.get('codigo_documento') or '').strip() or 'FR-HACCP-TEMP-01'
        cfg.version = (request.form.get('version') or '').strip() or '1'
        cfg.frecuencia_texto = (request.form.get('frecuencia_texto') or '').strip() or '2 veces al día'
        cfg.termometro = (request.form.get('termometro') or '').strip() or None
        cal = (request.form.get('termometro_calibrado_en') or '').strip()
        try:
            cfg.termometro_calibrado_en = datetime.strptime(cal, '%Y-%m-%d').date() if cal else None
        except ValueError:
            cfg.termometro_calibrado_en = None
        cfg.actualizado_en = datetime.utcnow()
        db.session.commit()
        flash('Configuración guardada.', 'success')
        return redirect(url_for('registro_config'))
    return render_template('registros/config.html', cfg=cfg)
```

- [ ] **Step 4: Crear `templates/registros/config.html`**

```html
{% extends "base.html" %}
{% block title %}Configuración del registro{% endblock %}
{% block header_title %}<span class="fw-700 color-white">Configuración del registro</span>{% endblock %}
{% block extra_css %}
<link rel="stylesheet" href="{{ url_for('static', filename='css/registros.css') }}">
{% endblock %}
{% block content %}
<div class="mobile-form-container reg-wrap">
  <div class="reg-toolbar">
    <a href="{{ url_for('temperaturas_index') }}" class="reg-btn"><i class="fas fa-temperature-half"></i> Temperaturas</a>
  </div>
  <div class="mobile-card">
    <div class="mobile-card-header"><i class="fas fa-gear"></i> Datos del documento e instrumento</div>
    <div class="mobile-card-body">
      <form method="POST" action="{{ url_for('registro_config') }}" autocomplete="off">
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
          <label class="mobile-form-label" for="frecuencia_texto">Frecuencia de monitoreo</label>
          <input type="text" id="frecuencia_texto" name="frecuencia_texto" class="mobile-form-control" value="{{ cfg.frecuencia_texto }}" placeholder="Ej: 2 veces al día (mañana y tarde)">
        </div>
        <div class="mobile-form-group">
          <label class="mobile-form-label" for="termometro">Termómetro / instrumento</label>
          <input type="text" id="termometro" name="termometro" class="mobile-form-control" value="{{ cfg.termometro or '' }}" placeholder="Ej: Termómetro digital TP-01">
        </div>
        <div class="mobile-form-group">
          <label class="mobile-form-label" for="termometro_calibrado_en">Última calibración</label>
          <input type="date" id="termometro_calibrado_en" name="termometro_calibrado_en" class="mobile-form-control" value="{{ cfg.termometro_calibrado_en.isoformat() if cfg.termometro_calibrado_en else '' }}">
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

- [ ] **Step 5: Enlace en el toolbar de `temperaturas.html`**

En `templates/registros/temperaturas.html`, reemplazar:
```html
    {% if es_admin %}
    <a href="{{ url_for('camaras_list') }}" class="reg-btn"><i class="fas fa-snowflake"></i> Cámaras</a>
    {% endif %}
```
por:
```html
    {% if es_admin %}
    <a href="{{ url_for('camaras_list') }}" class="reg-btn"><i class="fas fa-snowflake"></i> Cámaras</a>
    <a href="{{ url_for('registro_config') }}" class="reg-btn"><i class="fas fa-gear"></i> Configuración</a>
    {% endif %}
```

- [ ] **Step 6: Correr y commit**

Run: `.venv311/bin/python -m pytest tests/test_temperaturas_audit.py tests/test_reskin_smoke.py -q` → PASS.
```bash
git add app.py templates/registros/config.html templates/registros/temperaturas.html tests/test_temperaturas_audit.py
git commit -m "feat(haccp): pantalla de configuración del registro (super_admin)"
```

---

### Task 3: Acción correctiva estructurada

**Files:**
- Modify: `app.py` (reemplazar la función `temperatura_registrar`)
- Modify: `templates/registros/temperaturas.html` (bloque colapsable de 4 campos)
- Test: `tests/test_temperaturas_audit.py` (append)

- [ ] **Step 1: Escribir los tests que fallan**

Append:

```python
def _camara_fuera(app):
    # La cámara 'Cava 1' tiene rango 0..4; 9 está fuera.
    return IDS['camara']


def test_fuera_de_rango_sin_obligatorios_rechazado(app):
    from app import LecturaTemperatura
    c = _login(app, 'vend')
    c.post('/registros/temperaturas/registrar',
           data={'camara_id': IDS['camara'], 'temperatura': '9',
                 'accion_tomada': '', 'accion_disposicion': ''}, follow_redirects=True)
    with app.app_context():
        assert LecturaTemperatura.query.filter_by(camara_id=IDS['camara']).count() == 0


def test_fuera_de_rango_con_obligatorios_guarda(app):
    from app import LecturaTemperatura
    c = _login(app, 'vend')
    c.post('/registros/temperaturas/registrar',
           data={'camara_id': IDS['camara'], 'temperatura': '9',
                 'accion_causa': 'puerta abierta', 'accion_tomada': 'se cerró',
                 'accion_responsable': 'Juan', 'accion_disposicion': 'producto OK'},
           follow_redirects=True)
    with app.app_context():
        lec = LecturaTemperatura.query.filter_by(camara_id=IDS['camara']).first()
        assert lec is not None and lec.fuera_de_rango is True
        assert lec.accion_tomada == 'se cerró'
        assert lec.accion_disposicion == 'producto OK'
        assert lec.accion_causa == 'puerta abierta'


def test_en_rango_ignora_accion(app):
    from app import LecturaTemperatura
    c = _login(app, 'vend')
    c.post('/registros/temperaturas/registrar',
           data={'camara_id': IDS['camara'], 'temperatura': '2',
                 'accion_tomada': 'no aplica'}, follow_redirects=True)
    with app.app_context():
        lec = LecturaTemperatura.query.filter_by(camara_id=IDS['camara']).first()
        assert lec is not None and lec.fuera_de_rango is False
        assert lec.accion_tomada is None
```

- [ ] **Step 2: Correr y verificar que fallan**

Run: `.venv311/bin/python -m pytest tests/test_temperaturas_audit.py -q`
Expected: FAIL (la ruta aún usa `accion_correctiva` único; los campos estructurados no se guardan / la regla no aplica).

- [ ] **Step 3: Reemplazar `temperatura_registrar`**

En `app.py`, reemplazar TODA la función `temperatura_registrar` por:

```python
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

    fuera = camara.fuera_de_rango(temperatura)
    causa = (request.form.get('accion_causa') or '').strip()
    tomada = (request.form.get('accion_tomada') or '').strip()
    responsable = (request.form.get('accion_responsable') or '').strip()
    disposicion = (request.form.get('accion_disposicion') or '').strip()

    if fuera and (not tomada or not disposicion):
        flash(f'La lectura {temperatura}°C está fuera del rango de {camara.nombre} '
              f'({camara.temp_min}°C a {camara.temp_max}°C). Indica al menos la acción tomada '
              f'y la disposición del producto.', 'danger')
        return redirect(url_for('temperaturas_index'))

    db.session.add(LecturaTemperatura(
        camara_id=camara.id,
        temperatura=temperatura,
        registrado_por=current_user.id if isinstance(current_user, Vendedor) else None,
        fuera_de_rango=fuera,
        accion_causa=(causa or None) if fuera else None,
        accion_tomada=(tomada or None) if fuera else None,
        accion_responsable=(responsable or None) if fuera else None,
        accion_disposicion=(disposicion or None) if fuera else None,
    ))
    db.session.commit()
    flash('Lectura registrada.' + (' (Fuera de rango — registrada con acción correctiva.)' if fuera else ''),
          'success' if not fuera else 'warning')
    return redirect(url_for('temperaturas_index'))
```

- [ ] **Step 4: Bloque colapsable en `temperaturas.html`**

En `templates/registros/temperaturas.html`, reemplazar el bloque del campo único de acción correctiva:
```html
        <div class="mobile-form-group">
          <label class="mobile-form-label" for="accion_{{ c.id }}">Acción correctiva <small style="font-weight:400; opacity:.8;">(obligatoria si está fuera de rango)</small></label>
          <textarea id="accion_{{ c.id }}" name="accion_correctiva" class="mobile-form-control" rows="2" placeholder="Solo si la temperatura está fuera de rango"></textarea>
        </div>
```
por:
```html
        <details class="reg-edit">
          <summary><i class="fas fa-triangle-exclamation"></i> Acción correctiva (solo si está fuera de rango)</summary>
          <div class="reg-edit-body">
            <div class="mobile-form-group">
              <label class="mobile-form-label">Causa</label>
              <input type="text" name="accion_causa" class="mobile-form-control" placeholder="¿Por qué se salió de rango?">
            </div>
            <div class="mobile-form-group">
              <label class="mobile-form-label">Acción tomada <small style="font-weight:400; opacity:.8;">(obligatoria si fuera de rango)</small></label>
              <textarea name="accion_tomada" class="mobile-form-control" rows="2" placeholder="¿Qué se hizo?"></textarea>
            </div>
            <div class="mobile-form-group">
              <label class="mobile-form-label">Responsable de la acción</label>
              <input type="text" name="accion_responsable" class="mobile-form-control">
            </div>
            <div class="mobile-form-group">
              <label class="mobile-form-label">Disposición del producto <small style="font-weight:400; opacity:.8;">(obligatoria si fuera de rango)</small></label>
              <textarea name="accion_disposicion" class="mobile-form-control" rows="2" placeholder="¿Qué pasó con el producto afectado?"></textarea>
            </div>
          </div>
        </details>
```

- [ ] **Step 5: Correr y commit**

Run: `.venv311/bin/python -m pytest tests/test_temperaturas_audit.py tests/test_registro_temperaturas.py -q` → PASS.
```bash
git add app.py templates/registros/temperaturas.html tests/test_temperaturas_audit.py
git commit -m "feat(haccp): acción correctiva estructurada (causa/acción/responsable/disposición)"
```

---

### Task 4: Verificación de registros (revisar)

**Files:**
- Modify: `app.py` (helper `_revision_que_cubre`; ruta `temperatura_revisar`; actualizar `temperaturas_historial`)
- Modify: `templates/registros/temperaturas_historial.html` (bloque de verificación + acción estructurada en filas)
- Test: `tests/test_temperaturas_audit.py` (append)

- [ ] **Step 1: Escribir los tests que fallan**

Append:

```python
def test_revisar_supervisor_crea_revision(app):
    from app import RevisionRegistro
    c = _login(app, 'super')
    resp = c.post('/registros/temperaturas/revisar',
                  data={'fecha_inicio': '2026-05-01', 'fecha_fin': '2026-05-31'},
                  follow_redirects=True)
    assert resp.status_code == 200
    with app.app_context():
        assert RevisionRegistro.query.count() == 1


def test_revisar_vendedor_bloqueado(app):
    from app import RevisionRegistro
    c = _login(app, 'vend')
    resp = c.post('/registros/temperaturas/revisar',
                  data={'fecha_inicio': '2026-05-01', 'fecha_fin': '2026-05-31'},
                  follow_redirects=False)
    assert resp.status_code in (302, 403)
    with app.app_context():
        assert RevisionRegistro.query.count() == 0
```

- [ ] **Step 2: Correr y verificar que fallan**

Run: `.venv311/bin/python -m pytest tests/test_temperaturas_audit.py -q`
Expected: FAIL (ruta `/revisar` 404).

- [ ] **Step 3: Helper + ruta + actualizar historial**

En `app.py`, junto a `_filtrar_lecturas`, agregar el helper:

```python
def _revision_que_cubre(fi, ff):
    """RevisionRegistro más reciente que cubre el período [fi, ff] ('YYYY-MM-DD').
    Si no hay fechas, devuelve la más reciente. None si no existe ninguna."""
    def _d(s):
        try:
            return datetime.strptime(s, '%Y-%m-%d').date() if s else None
        except ValueError:
            return None
    d_fi, d_ff = _d(fi), _d(ff)
    q = RevisionRegistro.query
    if d_fi and d_ff:
        q = q.filter(RevisionRegistro.periodo_desde.isnot(None),
                     RevisionRegistro.periodo_hasta.isnot(None),
                     RevisionRegistro.periodo_desde <= d_fi,
                     RevisionRegistro.periodo_hasta >= d_ff)
    return q.order_by(RevisionRegistro.revisado_en.desc()).first()
```

Agregar la ruta (antes de `if __name__ == '__main__':`):

```python
@app.route('/registros/temperaturas/revisar', methods=['POST'])
@login_required
@requiere_rol(['super_admin', 'supervisor'])
def temperatura_revisar():
    fi = request.form.get('fecha_inicio') or None
    ff = request.form.get('fecha_fin') or None
    def _d(s):
        try:
            return datetime.strptime(s, '%Y-%m-%d').date() if s else None
        except ValueError:
            return None
    db.session.add(RevisionRegistro(
        revisado_por=current_user.id if isinstance(current_user, Vendedor) else None,
        periodo_desde=_d(fi), periodo_hasta=_d(ff),
    ))
    db.session.commit()
    flash('Período marcado como revisado.', 'success')
    return redirect(url_for('temperaturas_historial', fecha_inicio=fi or '', fecha_fin=ff or ''))
```

Reemplazar la función `temperaturas_historial` por:

```python
@app.route('/registros/temperaturas/historial')
@login_required
def temperaturas_historial():
    lecturas = _filtrar_lecturas(request.args)
    camaras = Camara.query.order_by(Camara.nombre).all()
    puede_verificar = isinstance(current_user, Vendedor) and current_user.rol.nombre in ('super_admin', 'supervisor')
    revision = _revision_que_cubre(request.args.get('fecha_inicio'), request.args.get('fecha_fin'))
    return render_template('registros/temperaturas_historial.html',
                           lecturas=lecturas, camaras=camaras, filtros=request.args,
                           puede_verificar=puede_verificar, revision=revision)
```

- [ ] **Step 4: Bloque de verificación + acción estructurada en el historial**

En `templates/registros/temperaturas_historial.html`, INSERTAR, justo antes de la línea `<h3 class="reg-name" style="margin:4px 2px;"><i class="fas fa-list"></i> Lecturas</h3>`:

```html
  {% if revision %}
  <div class="reg-card is-ok">
    <div class="reg-name"><i class="fas fa-clipboard-check"></i> Período verificado</div>
    <div class="reg-sub">Revisado por <strong>{{ revision.revisado_por_vendedor.nombre_completo if revision.revisado_por_vendedor else '—' }}</strong> el {{ revision.revisado_en.strftime('%Y-%m-%d %H:%M') }}</div>
  </div>
  {% endif %}
  {% if puede_verificar %}
  <form method="POST" action="{{ url_for('temperatura_revisar') }}">
    <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
    <input type="hidden" name="fecha_inicio" value="{{ filtros.get('fecha_inicio', '') }}">
    <input type="hidden" name="fecha_fin" value="{{ filtros.get('fecha_fin', '') }}">
    <button type="submit" class="reg-btn reg-btn-primary"><i class="fas fa-clipboard-check"></i> Marcar período como revisado</button>
  </form>
  {% endif %}
```

Y reemplazar el bloque `{% if l.accion_correctiva %}...{% endif %}` dentro de cada fila por una que muestre los campos estructurados o el legacy:
```html
        {% if l.accion_tomada or l.accion_disposicion or l.accion_causa or l.accion_correctiva %}
        <div class="reg-accion"><i class="fas fa-wrench"></i>
          {% if l.accion_causa %}<strong>Causa:</strong> {{ l.accion_causa }} · {% endif %}
          {% if l.accion_tomada %}<strong>Acción:</strong> {{ l.accion_tomada }} · {% endif %}
          {% if l.accion_responsable %}<strong>Resp.:</strong> {{ l.accion_responsable }} · {% endif %}
          {% if l.accion_disposicion %}<strong>Disposición:</strong> {{ l.accion_disposicion }}{% endif %}
          {% if not (l.accion_tomada or l.accion_disposicion or l.accion_causa) and l.accion_correctiva %}{{ l.accion_correctiva }}{% endif %}
        </div>
        {% endif %}
```

- [ ] **Step 5: Correr y commit**

Run: `.venv311/bin/python -m pytest tests/test_temperaturas_audit.py tests/test_registro_temperaturas.py tests/test_reskin_smoke.py -q` → PASS.
```bash
git add app.py templates/registros/temperaturas_historial.html tests/test_temperaturas_audit.py
git commit -m "feat(haccp): verificación de registros por período (super_admin/supervisor)"
```

---

### Task 5: PDF audit-ready (encabezado, límite crítico, verificación, pie numerado)

**Files:**
- Modify: `app.py` (`_build_temperaturas_pdf` firma + cuerpo; `temperaturas_export` para pasar config y revisión)
- Test: `tests/test_temperaturas_audit.py` (append)

- [ ] **Step 1: Escribir el test que falla**

Append:

```python
def test_export_pdf_audit(app):
    c = _login(app, 'admin')
    # una lectura en rango
    c.post('/registros/temperaturas/registrar',
           data={'camara_id': IDS['camara'], 'temperatura': '2'}, follow_redirects=True)
    resp = c.post('/registros/temperaturas/export',
                  data={'fecha_inicio': '2000-01-01', 'fecha_fin': '2100-01-01'},
                  follow_redirects=False)
    assert resp.status_code == 200
    assert 'application/pdf' in resp.headers.get('Content-Type', '')
```

- [ ] **Step 2: Correr y verificar que pasa parcialmente / sigue verde**

Run: `.venv311/bin/python -m pytest tests/test_temperaturas_audit.py::test_export_pdf_audit -q`
Expected: PASS ya hoy (el export existe), pero la firma de `_build_temperaturas_pdf` cambiará; este test garantiza que sigue devolviendo PDF tras los cambios.

- [ ] **Step 3: Reemplazar `_build_temperaturas_pdf`**

En `app.py`, reemplazar TODA la función `_build_temperaturas_pdf` por (nueva firma con `config` y `revision`):

```python
def _build_temperaturas_pdf(lecturas, fecha_inicio, fecha_fin, config, revision):
    """Construye el PDF tabular audit-ready del registro de temperaturas."""
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
        Paragraph('Registro de temperaturas de cámaras', titulo_style),
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

    def _accion_txt(l):
        if l.accion_tomada or l.accion_disposicion or l.accion_causa or l.accion_responsable:
            partes = []
            if l.accion_causa: partes.append(f'Causa: {l.accion_causa}')
            if l.accion_tomada: partes.append(f'Acción: {l.accion_tomada}')
            if l.accion_responsable: partes.append(f'Resp.: {l.accion_responsable}')
            if l.accion_disposicion: partes.append(f'Disposición: {l.accion_disposicion}')
            return ' | '.join(partes)
        return l.accion_correctiva or ''

    encabezados = ['Fecha/Hora', 'Cámara', 'Tipo', 'Límite crítico (°C)', 'Lectura (°C)',
                   'En rango', 'Responsable', 'Acción correctiva']
    data = [encabezados]
    for l in lecturas:
        data.append([
            Paragraph(l.registrado_en.strftime('%Y-%m-%d %H:%M'), cell),
            Paragraph(l.camara.nombre if l.camara else '—', cell),
            Paragraph('Refrigeración' if (l.camara and l.camara.tipo == 'refrigeracion') else 'Congelación', cell),
            Paragraph(f'{l.camara.temp_min} a {l.camara.temp_max}' if l.camara else '—', cell),
            Paragraph(str(l.temperatura), cell),
            Paragraph('NO' if l.fuera_de_rango else 'Sí', cell),
            Paragraph(l.registrado_por_vendedor.nombre_completo if l.registrado_por_vendedor else '—', cell),
            Paragraph(_accion_txt(l), cell),
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

    # Bloque de verificación
    elements.append(Spacer(1, 18))
    if revision:
        nombre = revision.revisado_por_vendedor.nombre_completo if revision.revisado_por_vendedor else '—'
        rev_txt = f'<b>Verificación:</b> Revisado por {nombre} el {revision.revisado_en.strftime("%Y-%m-%d %H:%M")}'
    else:
        rev_txt = '<b>Verificación:</b> Revisado por: ______________________      Fecha: __________'
    elements.append(Paragraph(rev_txt, sub_style))

    # Pie de página con frecuencia, instrumento y "Página X de Y"
    cal = config.termometro_calibrado_en.strftime('%Y-%m-%d') if config.termometro_calibrado_en else 'N/D'
    footer_left = (f'Frecuencia: {config.frecuencia_texto or "N/D"}   |   '
                   f'Instrumento: {config.termometro or "N/D"} (cal.: {cal})')
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
```

- [ ] **Step 4: Actualizar `temperaturas_export` para pasar config + revisión**

En `app.py`, reemplazar el cuerpo de `temperaturas_export` (la parte que llama a `_build_temperaturas_pdf`). La función completa queda:

```python
@app.route('/registros/temperaturas/export', methods=['POST'])
@login_required
def temperaturas_export():
    lecturas = _filtrar_lecturas(request.form)
    fi = request.form.get('fecha_inicio') or ''
    ff = request.form.get('fecha_fin') or ''
    config = _get_registro_config()
    revision = _revision_que_cubre(fi, ff)
    buffer = _build_temperaturas_pdf(lecturas, fi, ff, config, revision)
    filename = f"registro_temperaturas_{fi or 'inicio'}_{ff or 'fin'}.pdf"
    response = make_response(send_file(buffer, mimetype='application/pdf',
                                       as_attachment=not _is_ios_request(),
                                       download_name=filename))
    response.headers['Content-Type'] = 'application/pdf'
    return response
```

- [ ] **Step 5: Correr y commit**

Run: `.venv311/bin/python -m pytest tests/test_temperaturas_audit.py tests/test_registro_temperaturas.py -q` → PASS.
```bash
git add app.py tests/test_temperaturas_audit.py
git commit -m "feat(haccp): PDF audit-ready (documento/versión, límite crítico, verificación, pie numerado)"
```

---

### Task 6: Verificación final + deploy + migración en Heroku

**Files:** ninguno (verificación + deploy; lo ejecuta el controlador, no un subagente)

- [ ] **Step 1: Suite completa**

Run: `.venv311/bin/python -m pytest tests/ -q`
Expected: todos los tests nuevos de `test_temperaturas_audit.py` pasan; las fallas pre-existentes (22, ajenas) no aumentan.

- [ ] **Step 2: Deploy**

```bash
git push origin main
git push heroku main
```

- [ ] **Step 3: Crear tablas nuevas en Heroku (idempotente)**

```bash
heroku run --no-tty --app pesosapp python -c "from app import app, db; app.app_context().push(); db.create_all(); print('tablas ok')"
```
Crea `registro_config` y `revision_registro` (no altera las existentes).

- [ ] **Step 4: Agregar las 4 columnas a la tabla existente (ALTER TABLE)**

`db.create_all()` NO altera tablas existentes; las columnas nuevas de
`lectura_temperatura` se agregan con SQL (ver MEMORY.md):
```bash
heroku pg:psql --app pesosapp -c "ALTER TABLE lectura_temperatura ADD COLUMN IF NOT EXISTS accion_causa TEXT; ALTER TABLE lectura_temperatura ADD COLUMN IF NOT EXISTS accion_tomada TEXT; ALTER TABLE lectura_temperatura ADD COLUMN IF NOT EXISTS accion_responsable VARCHAR(120); ALTER TABLE lectura_temperatura ADD COLUMN IF NOT EXISTS accion_disposicion TEXT;"
```

- [ ] **Step 5: Verificación en vivo**

Confirmar que `/registros/temperaturas/config` carga (super_admin), que se puede registrar una lectura, marcar un período como revisado, y exportar el PDF con encabezado/pie/verificación.

---

## Self-Review

**Spec coverage:**
- RegistroConfig (singleton) + helper → Task 1.
- RevisionRegistro → Task 1.
- 4 columnas en LecturaTemperatura → Task 1.
- Config screen (super_admin) → Task 2.
- Acción correctiva estructurada (obligatorios acción+disposición) → Task 3.
- Verificación en la app (super_admin/supervisor) + display → Task 4.
- PDF: documento/versión, "Límite crítico", acción estructurada, bloque verificación, pie con frecuencia+instrumento+calibración+Página X de Y → Task 5.
- Migración (tablas vía create_all; columnas vía ALTER TABLE) → Task 6.
- Navegación (enlace Configuración) → Task 2.
- Pruebas TDD por parte → Tasks 1–5.

**Placeholder scan:** Sin TBD/TODO; todo el código (modelos, rutas, plantillas, tests, comandos SQL) está completo.

**Type/identifier consistency:** Endpoints `registro_config`, `temperatura_revisar`, `temperaturas_export`, `temperaturas_historial`, `temperatura_registrar` coinciden entre rutas y plantillas. Campos `accion_causa/accion_tomada/accion_responsable/accion_disposicion` usados consistentemente en modelo, ruta, plantillas, PDF y tests. `_get_registro_config`, `_revision_que_cubre` definidos antes de su uso (Tasks 1/4) y consumidos en Task 5. `_build_temperaturas_pdf` recibe `config, revision` (Task 5) y `temperaturas_export` se los pasa (Task 5). `RegistroConfig.termometro_calibrado_en` es Date (config form parsea/serializa ISO).
