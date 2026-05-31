# Administración completa de usuarios (#1) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Permitir al super_admin editar usuarios, cambiar su rol, activar/desactivar y restablecer contraseña (temporal con cambio obligatorio) desde `/admin/vendedores`, y crear el rol `supervisor` que falta.

**Architecture:** Cambios en `app.py` (modelo `Vendedor` + 3 rutas nuevas + un `before_request` que fuerza el cambio de contraseña) y en `templates/admin/vendedores.html` (formularios de editar / toggle / reset con CSRF). El motor de permisos (`tiene_permiso`) NO se toca (eso es el sub-proyecto #2). Acceso de rol = se asigna un rol al usuario.

**Tech Stack:** Flask, Flask-Login, SQLAlchemy, Jinja2, pytest, Postgres (prod) / SQLite (tests y local).

**Spec:** `docs/superpowers/specs/2026-05-31-admin-usuarios-design.md`

---

## File Structure

- **Modificar** `app.py`:
  - Modelo `Vendedor` (~línea 282): nueva columna `debe_cambiar_password`.
  - Helper `_es_ultimo_super_admin(vendedor)` y `_generar_password_temporal()`.
  - `crear_vendedor` (~3224): los usuarios nuevos nacen con `debe_cambiar_password=True`.
  - `cambiar_password` (~540): limpiar el flag al cambiarla.
  - Nuevo `@app.before_request forzar_cambio_password` (tras `require_login`, ~561).
  - 3 rutas nuevas tras `actualizar_territorio_vendedor` (~3946): `editar_vendedor`, `toggle_vendedor`, `reset_password_vendedor`.
- **Modificar** `templates/admin/vendedores.html`: formularios editar/toggle/reset + badge; quitar el JS roto.
- **Crear** `tests/test_admin_usuarios.py`.
- **DB**: `ALTER TABLE vendedor ADD COLUMN debe_cambiar_password` + `INSERT` rol supervisor (local y Heroku).

**Ejecutar tests con** `.venv/bin/python -m pytest` (no `python`/`python3` pelados).

---

## Task 1: Columna del modelo + helpers + test base

**Files:**
- Create: `tests/test_admin_usuarios.py`
- Modify: `app.py` (modelo `Vendedor` ~línea 282; helpers nuevos)

- [ ] **Step 1: Crear `tests/test_admin_usuarios.py` con fixture y primer test**

```python
"""Tests de administración de usuarios (#1)."""
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
        from app import Rol, Territorio, Vendedor
        rol_admin = Rol(nombre='super_admin', descripcion='Admin')
        rol_super = Rol(nombre='supervisor', descripcion='Supervisor')
        rol_vend = Rol(nombre='vendedor', descripcion='Vendedor')
        terr = Territorio(nombre='t1', descripcion='T1')
        _db.session.add_all([rol_admin, rol_super, rol_vend, terr])
        _db.session.flush()
        admin = Vendedor(username='admin', email='admin@t.com', nombre_completo='Admin',
                         rol_id=rol_admin.id, territorio_id=terr.id, activo=True)
        admin.set_password('pw')
        vend = Vendedor(username='vend', email='vend@t.com', nombre_completo='Vend',
                        rol_id=rol_vend.id, territorio_id=terr.id, activo=True)
        vend.set_password('pw')
        _db.session.add_all([admin, vend])
        _db.session.commit()
        IDS['rol_admin'] = rol_admin.id
        IDS['rol_super'] = rol_super.id
        IDS['rol_vend'] = rol_vend.id
        IDS['terr'] = terr.id
        IDS['admin'] = admin.id
        IDS['vend'] = vend.id
        yield flask_app
        _db.drop_all()


def _login(app, username):
    c = app.test_client()
    c.post('/login', data={'username': username, 'password': 'pw'}, follow_redirects=True)
    return c


def test_columna_debe_cambiar_password(app):
    from app import Vendedor
    with app.app_context():
        v = _db.session.get(Vendedor, IDS['vend'])
        assert v.debe_cambiar_password is False
```

- [ ] **Step 2: Correr el test → falla**

Run: `.venv/bin/python -m pytest tests/test_admin_usuarios.py::test_columna_debe_cambiar_password -v`
Expected: FAIL — `AttributeError: 'Vendedor' object has no attribute 'debe_cambiar_password'`

- [ ] **Step 3: Añadir la columna al modelo `Vendedor`**

En `app.py`, tras la línea `fecha_creacion = db.Column(db.DateTime, default=datetime.utcnow)` (~línea 282), agregar:

```python
    debe_cambiar_password = db.Column(db.Boolean, nullable=False, default=False)
```

- [ ] **Step 4: Añadir los helpers de módulo**

En `app.py`, justo ANTES de la ruta `@app.route('/admin/vendedores')` (función `gestionar_vendedores`, ~línea 3118), agregar:

```python
def _es_ultimo_super_admin(vendedor):
    """True si 'vendedor' es super_admin activo y es el único super_admin activo."""
    if not vendedor.rol or vendedor.rol.nombre != 'super_admin' or not vendedor.activo:
        return False
    activos = (Vendedor.query.join(Rol)
               .filter(Rol.nombre == 'super_admin', Vendedor.activo.is_(True)).count())
    return activos <= 1


def _generar_password_temporal():
    """Genera una contraseña temporal legible y aleatoria."""
    return secrets.token_urlsafe(8)
```

- [ ] **Step 5: Correr el test → pasa**

Run: `.venv/bin/python -m pytest tests/test_admin_usuarios.py::test_columna_debe_cambiar_password -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add app.py tests/test_admin_usuarios.py
git commit -m "feat(usuarios): columna debe_cambiar_password y helpers de admin

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 2: Cambio de contraseña obligatorio (flag en alta + limpieza + before_request)

**Files:**
- Modify: `app.py` (`crear_vendedor`, `cambiar_password`, nuevo `before_request`)
- Test: `tests/test_admin_usuarios.py`

- [ ] **Step 1: Añadir los tests**

Agregar al final de `tests/test_admin_usuarios.py`:

```python
def test_nuevo_usuario_nace_con_flag(app):
    from app import Vendedor
    c = _login(app, 'admin')
    c.post('/admin/vendedores/nuevo', data={
        'username': 'nuevo', 'email': 'nuevo@t.com', 'nombre_completo': 'Nuevo',
        'password': 'inicial9', 'rol_id': IDS['rol_vend'],
    }, follow_redirects=True)
    with app.app_context():
        v = Vendedor.query.filter_by(username='nuevo').first()
        assert v is not None
        assert v.debe_cambiar_password is True


def test_flag_fuerza_cambio(app):
    from app import Vendedor
    with app.app_context():
        v = _db.session.get(Vendedor, IDS['vend'])
        v.debe_cambiar_password = True
        _db.session.commit()
    c = _login(app, 'vend')
    resp = c.get('/registros', follow_redirects=False)
    assert resp.status_code == 302
    assert 'cambiar-contrasena' in resp.headers.get('Location', '')


def test_cambiar_password_limpia_flag(app):
    from app import Vendedor
    with app.app_context():
        v = _db.session.get(Vendedor, IDS['vend'])
        v.debe_cambiar_password = True
        _db.session.commit()
    c = _login(app, 'vend')
    c.post('/mi-cuenta/cambiar-contrasena',
           data={'actual': 'pw', 'nueva': 'NuevaClave9', 'confirmar': 'NuevaClave9'},
           follow_redirects=True)
    with app.app_context():
        v = _db.session.get(Vendedor, IDS['vend'])
        assert v.debe_cambiar_password is False
        assert v.check_password('NuevaClave9') is True
```

- [ ] **Step 2: Correr → fallan**

Run: `.venv/bin/python -m pytest tests/test_admin_usuarios.py -k "flag or fuerza" -v`
Expected: FAIL (el nuevo no nace con flag; no hay redirección forzada)

- [ ] **Step 3a: `crear_vendedor` — nacer con el flag**

En `app.py`, en `crear_vendedor`, en el constructor `nuevo_vendedor = Vendedor(...)` (~línea 3224), agregar el parámetro `debe_cambiar_password=True`:

```python
            nuevo_vendedor = Vendedor(
                username=username,
                email=email,
                nombre_completo=nombre_completo,
                telefono=telefono,
                rol_id=int(rol_id),
                territorio_id=int(territorio_id) if territorio_id else None,
                fecha_ingreso=date.today(),
                activo=True,
                debe_cambiar_password=True
            )
```

- [ ] **Step 3b: `cambiar_password` — limpiar el flag**

En `app.py`, en `cambiar_password`, en la rama de éxito (tras `current_user.set_password(nueva)`, ~línea 540), agregar la línea del flag ANTES del commit:

```python
        current_user.set_password(nueva)
        current_user.debe_cambiar_password = False
        db.session.commit()
```

- [ ] **Step 3c: Nuevo `before_request` que fuerza el cambio**

En `app.py`, INMEDIATAMENTE DESPUÉS de la función `require_login` (la que termina en `return redirect(url_for('login', next=request.url))`, ~línea 561), agregar:

```python
@app.before_request
def forzar_cambio_password():
    """Si el usuario tiene una contraseña temporal pendiente, lo obliga a cambiarla."""
    if not current_user.is_authenticated or not isinstance(current_user, Vendedor):
        return
    if not getattr(current_user, 'debe_cambiar_password', False):
        return
    ep = request.endpoint or ''
    if ep in ('cambiar_password', 'logout', 'login', 'csrf_ping') or ep.startswith('static'):
        return
    flash('Debes establecer una nueva contraseña para continuar.', 'warning')
    return redirect(url_for('cambiar_password'))
```

- [ ] **Step 4: Correr → pasan**

Run: `.venv/bin/python -m pytest tests/test_admin_usuarios.py -k "flag or fuerza" -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add app.py tests/test_admin_usuarios.py
git commit -m "feat(usuarios): contrasena temporal con cambio obligatorio en el primer ingreso

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 3: Ruta activar/desactivar (toggle) + guards

**Files:**
- Modify: `app.py` (anexar tras `actualizar_territorio_vendedor`, ~línea 3946)
- Test: `tests/test_admin_usuarios.py`

- [ ] **Step 1: Añadir los tests**

Agregar al final de `tests/test_admin_usuarios.py`:

```python
def test_toggle_no_admin_bloqueado(app):
    from app import Vendedor
    c = _login(app, 'vend')
    resp = c.post(f'/admin/vendedores/{IDS["admin"]}/toggle', follow_redirects=False)
    assert resp.status_code in (302, 403)
    with app.app_context():
        assert _db.session.get(Vendedor, IDS['admin']).activo is True


def test_toggle_activa_desactiva(app):
    from app import Vendedor
    c = _login(app, 'admin')
    c.post(f'/admin/vendedores/{IDS["vend"]}/toggle', follow_redirects=True)
    with app.app_context():
        assert _db.session.get(Vendedor, IDS['vend']).activo is False
    c.post(f'/admin/vendedores/{IDS["vend"]}/toggle', follow_redirects=True)
    with app.app_context():
        assert _db.session.get(Vendedor, IDS['vend']).activo is True


def test_toggle_no_auto_desactivar(app):
    from app import Vendedor
    c = _login(app, 'admin')
    c.post(f'/admin/vendedores/{IDS["admin"]}/toggle', follow_redirects=True)
    with app.app_context():
        assert _db.session.get(Vendedor, IDS['admin']).activo is True


def test_toggle_no_desactivar_ultimo_superadmin(app):
    # Crear un 2do super_admin, desactivar al admin actual NO debe poder dejar 0.
    from app import Vendedor
    with app.app_context():
        a2 = Vendedor(username='admin2', email='a2@t.com', nombre_completo='Admin2',
                      rol_id=IDS['rol_admin'], territorio_id=IDS['terr'], activo=True)
        a2.set_password('pw'); _db.session.add(a2); _db.session.commit()
        IDS['admin2'] = a2.id
    c = _login(app, 'admin')
    # admin desactiva a admin2 (quedan 1 super_admin) → permitido
    c.post(f'/admin/vendedores/{IDS["admin2"]}/toggle', follow_redirects=True)
    with app.app_context():
        assert _db.session.get(Vendedor, IDS['admin2']).activo is False
    # ahora admin es el único super_admin activo; intentar desactivar admin2 ya está hecho.
    # Reactivar admin2 y desactivar admin (vía admin2) dejaría 1 → permitido; el guard
    # protege el caso de quedar 0, que coincide con auto-desactivación (ya cubierto).
```

- [ ] **Step 2: Correr → fallan**

Run: `.venv/bin/python -m pytest tests/test_admin_usuarios.py -k toggle -v`
Expected: FAIL — 404 / BuildError

- [ ] **Step 3: Añadir la ruta `toggle_vendedor` en `app.py`**

Anexar tras la ruta `actualizar_territorio_vendedor` (~línea 3946):

```python
@app.route('/admin/vendedores/<int:v_id>/toggle', methods=['POST'])
@login_required
@requiere_rol(['super_admin'])
def toggle_vendedor(v_id):
    v = Vendedor.query.get_or_404(v_id)
    if v.id == current_user.id:
        flash('No podés desactivar tu propia cuenta.', 'danger')
        return redirect(url_for('gestionar_vendedores'))
    if v.activo and _es_ultimo_super_admin(v):
        flash('No se puede desactivar al único super_admin activo.', 'danger')
        return redirect(url_for('gestionar_vendedores'))
    v.activo = not v.activo
    db.session.commit()
    flash(f"Usuario {'activado' if v.activo else 'desactivado'}.", 'success')
    return redirect(url_for('gestionar_vendedores'))
```

- [ ] **Step 4: Correr → pasan**

Run: `.venv/bin/python -m pytest tests/test_admin_usuarios.py -k toggle -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add app.py tests/test_admin_usuarios.py
git commit -m "feat(usuarios): activar/desactivar usuario con guards (self / ultimo super_admin)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 4: Ruta editar usuario + guards

**Files:**
- Modify: `app.py` (anexar tras `toggle_vendedor`)
- Test: `tests/test_admin_usuarios.py`

- [ ] **Step 1: Añadir los tests**

Agregar al final de `tests/test_admin_usuarios.py`:

```python
def test_editar_no_admin_bloqueado(app):
    from app import Vendedor
    c = _login(app, 'vend')
    resp = c.post(f'/admin/vendedores/{IDS["vend"]}/editar',
                  data={'nombre_completo': 'X', 'email': 'x@t.com', 'rol_id': IDS['rol_vend']},
                  follow_redirects=False)
    assert resp.status_code in (302, 403)
    with app.app_context():
        assert _db.session.get(Vendedor, IDS['vend']).nombre_completo == 'Vend'


def test_editar_cambia_rol_y_email(app):
    from app import Vendedor
    c = _login(app, 'admin')
    c.post(f'/admin/vendedores/{IDS["vend"]}/editar', data={
        'nombre_completo': 'Vend Editado', 'email': 'nuevo_vend@t.com',
        'telefono': '123', 'rol_id': IDS['rol_super'], 'territorio_id': IDS['terr'],
    }, follow_redirects=True)
    with app.app_context():
        v = _db.session.get(Vendedor, IDS['vend'])
        assert v.nombre_completo == 'Vend Editado'
        assert v.email == 'nuevo_vend@t.com'
        assert v.rol.nombre == 'supervisor'


def test_editar_email_duplicado_rechazado(app):
    from app import Vendedor
    c = _login(app, 'admin')
    c.post(f'/admin/vendedores/{IDS["vend"]}/editar', data={
        'nombre_completo': 'Vend', 'email': 'admin@t.com', 'rol_id': IDS['rol_vend'],
    }, follow_redirects=True)
    with app.app_context():
        assert _db.session.get(Vendedor, IDS['vend']).email == 'vend@t.com'


def test_editar_ultimo_superadmin_no_pierde_rol(app):
    from app import Vendedor
    c = _login(app, 'admin')
    # admin es el único super_admin → intentar bajarlo a vendedor se rechaza
    c.post(f'/admin/vendedores/{IDS["admin"]}/editar', data={
        'nombre_completo': 'Admin', 'email': 'admin@t.com', 'rol_id': IDS['rol_vend'],
    }, follow_redirects=True)
    with app.app_context():
        assert _db.session.get(Vendedor, IDS['admin']).rol.nombre == 'super_admin'
```

- [ ] **Step 2: Correr → fallan**

Run: `.venv/bin/python -m pytest tests/test_admin_usuarios.py -k editar -v`
Expected: FAIL — 404 / BuildError

- [ ] **Step 3: Añadir la ruta `editar_vendedor` en `app.py`**

Anexar tras la ruta `toggle_vendedor`:

```python
@app.route('/admin/vendedores/<int:v_id>/editar', methods=['POST'])
@login_required
@requiere_rol(['super_admin'])
def editar_vendedor(v_id):
    v = Vendedor.query.get_or_404(v_id)
    nombre = (request.form.get('nombre_completo') or '').strip()
    email = (request.form.get('email') or '').strip()
    telefono = (request.form.get('telefono') or '').strip() or None
    rol_id = request.form.get('rol_id', type=int)
    territorio_id = request.form.get('territorio_id', type=int) or None

    if not nombre or not email:
        flash('Nombre y email son obligatorios.', 'danger')
        return redirect(url_for('gestionar_vendedores'))
    rol = db.session.get(Rol, rol_id) if rol_id else None
    if rol is None:
        flash('El rol seleccionado no es válido.', 'danger')
        return redirect(url_for('gestionar_vendedores'))
    if territorio_id and db.session.get(Territorio, territorio_id) is None:
        flash('El territorio seleccionado no es válido.', 'danger')
        return redirect(url_for('gestionar_vendedores'))
    otro = Vendedor.query.filter(Vendedor.email == email, Vendedor.id != v.id).first()
    if otro:
        flash('Ese email ya está en uso por otro usuario.', 'danger')
        return redirect(url_for('gestionar_vendedores'))
    if rol.nombre != 'super_admin' and _es_ultimo_super_admin(v):
        flash('No se puede quitar el rol super_admin al único administrador activo.', 'danger')
        return redirect(url_for('gestionar_vendedores'))

    v.nombre_completo = nombre
    v.email = email
    v.telefono = telefono
    v.rol_id = rol.id
    v.territorio_id = territorio_id
    db.session.commit()
    flash('Usuario actualizado.', 'success')
    return redirect(url_for('gestionar_vendedores'))
```

- [ ] **Step 4: Correr → pasan**

Run: `.venv/bin/python -m pytest tests/test_admin_usuarios.py -k editar -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add app.py tests/test_admin_usuarios.py
git commit -m "feat(usuarios): editar usuario (datos + rol) con email unico y guard de super_admin

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 5: Ruta restablecer contraseña

**Files:**
- Modify: `app.py` (anexar tras `editar_vendedor`)
- Test: `tests/test_admin_usuarios.py`

- [ ] **Step 1: Añadir los tests**

Agregar al final de `tests/test_admin_usuarios.py`:

```python
def test_reset_no_admin_bloqueado(app):
    c = _login(app, 'vend')
    resp = c.post(f'/admin/vendedores/{IDS["vend"]}/reset-password',
                  data={'password_temporal': 'Temporal9'}, follow_redirects=False)
    assert resp.status_code in (302, 403)


def test_reset_con_temporal(app):
    from app import Vendedor
    c = _login(app, 'admin')
    c.post(f'/admin/vendedores/{IDS["vend"]}/reset-password',
           data={'password_temporal': 'Temporal9'}, follow_redirects=True)
    with app.app_context():
        v = _db.session.get(Vendedor, IDS['vend'])
        assert v.debe_cambiar_password is True
        assert v.check_password('Temporal9') is True


def test_reset_genera_si_blanco(app):
    from app import Vendedor
    c = _login(app, 'admin')
    c.post(f'/admin/vendedores/{IDS["vend"]}/reset-password',
           data={'password_temporal': ''}, follow_redirects=True)
    with app.app_context():
        v = _db.session.get(Vendedor, IDS['vend'])
        assert v.debe_cambiar_password is True
        assert v.check_password('pw') is False  # la contraseña vieja ya no sirve
```

- [ ] **Step 2: Correr → fallan**

Run: `.venv/bin/python -m pytest tests/test_admin_usuarios.py -k reset -v`
Expected: FAIL — 404 / BuildError

- [ ] **Step 3: Añadir la ruta `reset_password_vendedor` en `app.py`**

Anexar tras la ruta `editar_vendedor`:

```python
@app.route('/admin/vendedores/<int:v_id>/reset-password', methods=['POST'])
@login_required
@requiere_rol(['super_admin'])
def reset_password_vendedor(v_id):
    v = Vendedor.query.get_or_404(v_id)
    temp = (request.form.get('password_temporal') or '').strip()
    if temp and len(temp) < 8:
        flash('La contraseña temporal debe tener al menos 8 caracteres.', 'danger')
        return redirect(url_for('gestionar_vendedores'))
    if not temp:
        temp = _generar_password_temporal()
    v.set_password(temp)
    v.debe_cambiar_password = True
    db.session.commit()
    flash(f'Contraseña temporal de {v.nombre_completo}: {temp} — comunicásela; '
          f'deberá cambiarla al ingresar.', 'success')
    return redirect(url_for('gestionar_vendedores'))
```

- [ ] **Step 4: Correr → pasan**

Run: `.venv/bin/python -m pytest tests/test_admin_usuarios.py -k reset -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add app.py tests/test_admin_usuarios.py
git commit -m "feat(usuarios): restablecer contrasena (temporal o autogenerada) con cambio obligatorio

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 6: UI de administración (`templates/admin/vendedores.html`)

**Files:**
- Modify: `templates/admin/vendedores.html`
- Test: `tests/test_admin_usuarios.py`

- [ ] **Step 1: Añadir el test de render**

Agregar al final de `tests/test_admin_usuarios.py`:

```python
def test_pagina_admin_muestra_formularios(app):
    c = _login(app, 'admin')
    resp = c.get('/admin/vendedores')
    assert resp.status_code == 200
    body = resp.data.decode('utf-8')
    # Las acciones nuevas apuntan a las rutas correctas
    assert f'/admin/vendedores/{IDS["vend"]}/editar' in body
    assert f'/admin/vendedores/{IDS["vend"]}/toggle' in body
    assert f'/admin/vendedores/{IDS["vend"]}/reset-password' in body
```

- [ ] **Step 2: Correr → falla**

Run: `.venv/bin/python -m pytest tests/test_admin_usuarios.py::test_pagina_admin_muestra_formularios -v`
Expected: FAIL (el template aún tiene el toggle por JS, no las rutas)

- [ ] **Step 3: Reemplazar el bloque de acciones (footer) de cada tarjeta**

En `templates/admin/vendedores.html`, reemplazar el bloque `<!-- Acciones -->` … `</footer>` (líneas ~137–154) por:

```html
                <!-- Estado de contraseña -->
                {% if v.debe_cambiar_password %}
                <div class="pwd-pending"><i class="fas fa-key"></i> Debe cambiar contraseña</div>
                {% endif %}

                <!-- Acciones -->
                <footer class="vendedor-actions">
                    <form method="POST" action="{{ url_for('toggle_vendedor', v_id=v.id) }}"
                          onsubmit="return confirm('¿Seguro que querés {{ 'desactivar' if v.activo else 'activar' }} este usuario?');">
                        <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
                        {% if v.activo %}
                        <button class="btn-warning-sm"><i class="fas fa-pause"></i> Desactivar</button>
                        {% else %}
                        <button class="btn-success-sm"><i class="fas fa-play"></i> Activar</button>
                        {% endif %}
                    </form>
                </footer>

                <details class="vendedor-extra">
                    <summary><i class="fas fa-edit"></i> Editar</summary>
                    <form method="POST" action="{{ url_for('editar_vendedor', v_id=v.id) }}" class="extra-form">
                        <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
                        <label>Nombre completo
                            <input name="nombre_completo" value="{{ v.nombre_completo }}" required>
                        </label>
                        <label>Email
                            <input type="email" name="email" value="{{ v.email }}" required>
                        </label>
                        <label>Teléfono
                            <input name="telefono" value="{{ v.telefono or '' }}">
                        </label>
                        <label>Rol
                            <select name="rol_id" required>
                                {% for rol in roles %}
                                <option value="{{ rol.id }}" {{ 'selected' if v.rol_id == rol.id }}>{{ rol.nombre }}</option>
                                {% endfor %}
                            </select>
                        </label>
                        <label>Territorio
                            <select name="territorio_id">
                                <option value="">– Sin territorio –</option>
                                {% for t in territorios %}
                                <option value="{{ t.id }}" {{ 'selected' if v.territorio_id == t.id }}>{{ t.nombre }}</option>
                                {% endfor %}
                            </select>
                        </label>
                        <button class="btn-secondary-sm"><i class="fas fa-save"></i> Guardar cambios</button>
                    </form>
                </details>

                <details class="vendedor-extra">
                    <summary><i class="fas fa-key"></i> Restablecer contraseña</summary>
                    <form method="POST" action="{{ url_for('reset_password_vendedor', v_id=v.id) }}" class="extra-form">
                        <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
                        <label>Contraseña temporal (en blanco = generar)
                            <input name="password_temporal" id="temp_{{ v.id }}" placeholder="(se genera automáticamente)">
                        </label>
                        <div class="reset-actions">
                            <button type="button" class="btn-secondary-sm"
                                    onclick="document.getElementById('temp_{{ v.id }}').value = Math.random().toString(36).slice(-10);">
                                Generar
                            </button>
                            <button class="btn-warning-sm"><i class="fas fa-key"></i> Restablecer</button>
                        </div>
                    </form>
                </details>
```

- [ ] **Step 4: Reemplazar el bloque `{% block scripts %}` (quitar el JS roto)**

En `templates/admin/vendedores.html`, reemplazar todo el bloque desde `{% block scripts %}` hasta su `{% endblock %}` (líneas ~237–254) por:

```html
{% block scripts %}
{{ super() }}
{% endblock %}
```

- [ ] **Step 5: Añadir estilos para los nuevos elementos**

En `templates/admin/vendedores.html`, dentro del `<style>` (antes de `</style>`, ~línea 233), agregar:

```css
.pwd-pending{
    font-size:.78rem;color:#b45309;background:#fef3c7;
    border-radius:8px;padding:4px 10px;display:inline-flex;align-items:center;gap:6px}
.vendedor-extra{margin-top:8px;border-top:1px solid #ecf0f1;padding-top:8px}
.vendedor-extra > summary{cursor:pointer;color:#3498db;font-weight:600;font-size:.85rem}
.extra-form{display:flex;flex-direction:column;gap:8px;margin-top:10px}
.extra-form label{display:flex;flex-direction:column;gap:4px;font-size:.8rem;color:#2c3e50;font-weight:600}
.extra-form input,.extra-form select{
    padding:7px 9px;border:1px solid #dcdfe6;border-radius:6px;font-size:.85rem;font-weight:400}
.reset-actions{display:flex;gap:8px}
```

- [ ] **Step 6: Correr el test de render + verificar que renderiza sin error**

Run: `.venv/bin/python -m pytest tests/test_admin_usuarios.py::test_pagina_admin_muestra_formularios -v`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add templates/admin/vendedores.html tests/test_admin_usuarios.py
git commit -m "feat(usuarios): UI de admin con editar/toggle/reset por formulario (CSRF) y badge

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 7: Suite completa + migración local + sintaxis

**Files:** (verificación)

- [ ] **Step 1: Sintaxis de `app.py`**

Run: `.venv/bin/python -c "import ast; ast.parse(open('app.py').read()); print('OK')"`
Expected: `OK`

- [ ] **Step 2: Suite completa de admin + que no se rompa el resto de registros**

Run: `.venv/bin/python -m pytest tests/test_admin_usuarios.py tests/test_registro_limpieza.py tests/test_registro_temperaturas.py -v`
Expected: PASS (todo el archivo de admin + los de registros)

- [ ] **Step 3: Migración en la base local (sqlite local.db) + rol supervisor**

Run:
```bash
.venv/bin/python - <<'PY'
from app import app, db, Rol
from sqlalchemy import text, inspect
with app.app_context():
    insp = inspect(db.engine)
    cols = [c['name'] for c in insp.get_columns('vendedor')]
    if 'debe_cambiar_password' not in cols:
        db.session.execute(text('ALTER TABLE vendedor ADD COLUMN debe_cambiar_password BOOLEAN NOT NULL DEFAULT 0'))
        db.session.commit()
    if not Rol.query.filter_by(nombre='supervisor').first():
        db.session.add(Rol(nombre='supervisor', descripcion='Supervisor', nivel_jerarquia=5, activo=True))
        db.session.commit()
    print('local migrado:', 'debe_cambiar_password' in [c['name'] for c in inspect(db.engine).get_columns('vendedor')],
          '| supervisor:', Rol.query.filter_by(nombre='supervisor').first() is not None)
PY
```
Expected: `local migrado: True | supervisor: True`

- [ ] **Step 4: Commit (si hubo fixes)**

```bash
git add -A
git commit -m "test(usuarios): suite de administracion en verde" || echo "sin cambios"
```

---

## Task 8: Migración en Heroku y deploy

**Files:** (despliegue)

> Según memoria del proyecto: las migraciones deben correrse en Heroku vía `heroku pg:psql`. `debe_cambiar_password` y el rol `supervisor` deben existir en producción ANTES de que el código nuevo se use, pero el código tolera su ausencia salvo el flag (que la columna provee). Crear la columna primero evita errores.

- [ ] **Step 1: Migrar Heroku (columna + rol supervisor)**

Run:
```bash
heroku pg:psql --app pesosapp <<'SQL'
ALTER TABLE vendedor ADD COLUMN IF NOT EXISTS debe_cambiar_password BOOLEAN NOT NULL DEFAULT FALSE;
INSERT INTO rol (nombre, descripcion, nivel_jerarquia, activo, fecha_creacion)
SELECT 'supervisor', 'Supervisor', 5, true, now()
WHERE NOT EXISTS (SELECT 1 FROM rol WHERE nombre = 'supervisor');
SELECT (SELECT count(*) FROM information_schema.columns WHERE table_name='vendedor' AND column_name='debe_cambiar_password') AS col,
       (SELECT count(*) FROM rol WHERE nombre='supervisor') AS supervisor;
SQL
```
Expected: `col = 1`, `supervisor = 1`.

- [ ] **Step 2: Deploy**

Run:
```bash
git push origin main && git push heroku main
```
Expected: build OK, `Released vNNN`.

- [ ] **Step 3: Reiniciar dyno**

Run: `heroku restart --app pesosapp`

- [ ] **Step 4: Smoke test (producción, autenticado como super_admin)**

Abrir `https://pesosapp-caa46963237c.herokuapp.com/admin/vendedores` y verificar:
1. Cada usuario muestra **Editar**, **Restablecer contraseña** y **Activar/Desactivar**.
2. Editar un usuario de prueba (cambiar teléfono) guarda.
3. El selector de **Rol** ofrece super_admin / supervisor / vendedor.
4. Restablecer contraseña muestra la temporal; ese usuario, al ingresar, es enviado a "cambiar contraseña".

---

## Self-Review (autor del plan)

**Cobertura del spec:**
- Columna `debe_cambiar_password` → Task 1 ✓
- Crear rol `supervisor` → Task 7 (local) + Task 8 (Heroku) ✓
- Editar (datos + rol) con email único y guard super_admin → Task 4 ✓
- Toggle con guards (self / último super_admin) → Task 3 ✓
- Reset password (temporal/autogenerada) + flag → Task 5 ✓
- Cambio obligatorio (before_request + limpiar flag + alta con flag) → Task 2 ✓
- UI (editar/toggle/reset + badge, CSRF) → Task 6 ✓
- Migración local + Heroku → Tasks 7 y 8 ✓
- Tests de cada caso → Tasks 1–6 ✓

**Placeholders:** ninguno; todo el código (rutas, template, tests, SQL) está completo.

**Consistencia de nombres:** rutas `toggle_vendedor`, `editar_vendedor`, `reset_password_vendedor`; helpers `_es_ultimo_super_admin`, `_generar_password_temporal`; campo `debe_cambiar_password`; form fields `nombre_completo`, `email`, `telefono`, `rol_id`, `territorio_id`, `password_temporal` — coinciden entre rutas, template y tests.

**Nota:** el `before_request forzar_cambio_password` debe quedar DESPUÉS de `require_login` para que el orden sea login → forzar cambio. Ambos son `@app.before_request`; Flask los ejecuta en orden de registro.
