# Cambiar mi contraseña — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Permitir que un usuario `Vendedor` autenticado cambie su propia contraseña desde la app, forzando re-login tras el cambio.

**Architecture:** Una ruta nueva en `app.py` (`/mi-cuenta/cambiar-contrasena`) que valida en el handler y usa `set_password`/`check_password` del modelo `Vendedor`; un template HTML que sigue el patrón `mobile-form-*`; y enlaces de acceso en el menú de usuario de `base.html`. Sin Flask-WTF Forms (el proyecto usa forms HTML + CSRF global).

**Tech Stack:** Flask, Flask-Login (`logout_user`, `current_user`, `login_required`), SQLAlchemy, Jinja2, pytest.

---

### Task 1: Ruta `cambiar_password` + template (TDD)

**Files:**
- Test: `tests/test_cambiar_password.py` (crear)
- Modify: `app.py` (agregar ruta después de la función `logout`, ~línea 511)
- Create: `templates/cambiar_password.html`

- [ ] **Step 1: Escribir los tests que fallan**

Crear `tests/test_cambiar_password.py`:

```python
"""Tests para autoservicio de cambio de contraseña."""
import os
import pytest

os.environ.setdefault('SECRET_KEY', 'test-secret')
os.environ.setdefault('FLASK_ENV', 'testing')
os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')

from app import app as flask_app, db as _db

OLD = 'OldPass123'
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
        rol = Rol(nombre='vendedor', descripcion='Vendedor')
        terr = Territorio(nombre='t1', descripcion='T1')
        _db.session.add_all([rol, terr])
        _db.session.flush()
        v = Vendedor(username='user1', email='u1@t.com', nombre_completo='User Uno',
                     rol_id=rol.id, territorio_id=terr.id, activo=True)
        v.set_password(OLD)
        _db.session.add(v)
        _db.session.commit()
        IDS['user'] = v.id
        yield flask_app
        _db.drop_all()


def _login(app):
    c = app.test_client()
    c.post('/login', data={'username': 'user1', 'password': OLD},
           follow_redirects=True)
    return c


URL = '/mi-cuenta/cambiar-contrasena'


def _sigue_con_old(app):
    from app import Vendedor
    with app.app_context():
        v = _db.session.get(Vendedor, IDS['user'])
        assert v.check_password(OLD), "La contraseña NO debió cambiar"


def test_no_autenticado_redirige(app):
    c = app.test_client()
    resp = c.post(URL, data={'actual': OLD, 'nueva': 'NuevaPass1', 'confirmar': 'NuevaPass1'},
                  follow_redirects=False)
    assert resp.status_code == 302
    assert '/login' in resp.headers.get('Location', '')
    _sigue_con_old(app)


def test_actual_incorrecta(app):
    c = _login(app)
    resp = c.post(URL, data={'actual': 'malaclave', 'nueva': 'NuevaPass1', 'confirmar': 'NuevaPass1'})
    assert resp.status_code == 200
    _sigue_con_old(app)


def test_confirmacion_no_coincide(app):
    c = _login(app)
    resp = c.post(URL, data={'actual': OLD, 'nueva': 'NuevaPass1', 'confirmar': 'OtraCosa1'})
    assert resp.status_code == 200
    _sigue_con_old(app)


def test_nueva_muy_corta(app):
    c = _login(app)
    resp = c.post(URL, data={'actual': OLD, 'nueva': 'corta', 'confirmar': 'corta'})
    assert resp.status_code == 200
    _sigue_con_old(app)


def test_nueva_igual_a_actual(app):
    c = _login(app)
    resp = c.post(URL, data={'actual': OLD, 'nueva': OLD, 'confirmar': OLD})
    assert resp.status_code == 200
    _sigue_con_old(app)


def test_exito_cambia_y_desloguea(app):
    from app import Vendedor
    c = _login(app)
    nueva = 'NuevaPass1'
    resp = c.post(URL, data={'actual': OLD, 'nueva': nueva, 'confirmar': nueva},
                  follow_redirects=False)
    assert resp.status_code == 302
    assert '/login' in resp.headers.get('Location', '')
    with app.app_context():
        v = _db.session.get(Vendedor, IDS['user'])
        assert v.check_password(nueva)
        assert not v.check_password(OLD)
    # La sesión quedó cerrada: una ruta protegida ahora redirige a login
    r2 = c.get('/dashboard', follow_redirects=False)
    assert r2.status_code == 302
    assert '/login' in r2.headers.get('Location', '')
```

- [ ] **Step 2: Correr los tests para verificar que fallan**

Run: `python -m pytest tests/test_cambiar_password.py -q`
Expected: FAIL (la ruta no existe → 404; los asserts de status/redirect fallan).

- [ ] **Step 3: Implementar la ruta**

En `app.py`, justo después de la función `logout` (que termina en ~línea 511), agregar:

```python
@app.route('/mi-cuenta/cambiar-contrasena', methods=['GET', 'POST'])
@login_required
def cambiar_password():
    # Solo para usuarios Vendedor; el usuario legacy usa variable de entorno.
    if not isinstance(current_user, Vendedor):
        flash('Esta función no está disponible para el usuario del sistema.', 'warning')
        return redirect(url_for('dashboard'))

    if request.method == 'POST':
        actual    = request.form.get('actual') or ''
        nueva     = request.form.get('nueva') or ''
        confirmar = request.form.get('confirmar') or ''

        if not current_user.check_password(actual):
            flash('La contraseña actual es incorrecta.', 'error')
            return render_template('cambiar_password.html')
        if nueva != confirmar:
            flash('La nueva contraseña y su confirmación no coinciden.', 'error')
            return render_template('cambiar_password.html')
        if len(nueva) < 8:
            flash('La nueva contraseña debe tener al menos 8 caracteres.', 'error')
            return render_template('cambiar_password.html')
        if nueva == actual:
            flash('La nueva contraseña debe ser distinta de la actual.', 'error')
            return render_template('cambiar_password.html')

        current_user.set_password(nueva)
        db.session.commit()
        app.logger.info(
            f'Contraseña cambiada para usuario {current_user.username} (id={current_user.id})'
        )
        logout_user()
        flash('Contraseña actualizada. Inicia sesión nuevamente.', 'success')
        return redirect(url_for('login'))

    return render_template('cambiar_password.html')
```

- [ ] **Step 4: Crear el template**

Crear `templates/cambiar_password.html`:

```html
{% extends "base.html" %}

{% block title %}Cambiar contraseña{% endblock %}

{% block header_title %}
    <span class="fw-700 color-white">Cambiar contraseña</span>
{% endblock %}

{% block content %}
<div class="mobile-form-container">
    <form method="POST" autocomplete="off">
        <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">

        <div class="mobile-card">
            <div class="mobile-card-header">
                <i class="fas fa-key"></i>
                Cambiar mi contraseña
            </div>
            <div class="mobile-card-body">
                <div class="mobile-form-group">
                    <label class="mobile-form-label" for="actual">Contraseña actual</label>
                    <input type="password" id="actual" name="actual"
                           class="mobile-form-control" required>
                </div>
                <div class="mobile-form-group">
                    <label class="mobile-form-label" for="nueva">Nueva contraseña</label>
                    <input type="password" id="nueva" name="nueva"
                           class="mobile-form-control" minlength="8" required>
                </div>
                <div class="mobile-form-group">
                    <label class="mobile-form-label" for="confirmar">Confirmar nueva contraseña</label>
                    <input type="password" id="confirmar" name="confirmar"
                           class="mobile-form-control" minlength="8" required>
                </div>
            </div>
        </div>

        <div class="mobile-form-actions">
            <a href="{{ url_for('dashboard') }}" class="mobile-btn mobile-btn-secondary">
                <i class="fas fa-times"></i>
                Cancelar
            </a>
            <button type="submit" class="mobile-btn mobile-btn-primary">
                <i class="fas fa-save"></i>
                Guardar
            </button>
        </div>
    </form>
</div>
{% endblock %}
```

- [ ] **Step 5: Correr los tests y verificar que pasan**

Run: `python -m pytest tests/test_cambiar_password.py -q`
Expected: PASS (6 passed).

- [ ] **Step 6: Commit**

```bash
git add tests/test_cambiar_password.py app.py templates/cambiar_password.html
git commit -m "feat(cuenta): autoservicio de cambio de contraseña con re-login"
```

---

### Task 2: Enlaces de acceso en el menú de usuario

**Files:**
- Modify: `templates/base.html` (dropdown de usuario ~línea 436 y drawer ~línea 308)

- [ ] **Step 1: Agregar enlace en el dropdown de usuario (desktop)**

En `templates/base.html`, dentro de `<div class="dropdown-menu">`, insertar el enlace ENTRE "Ir al dashboard" y "Cerrar Sesión":

Buscar:
```html
                                <a href="/dashboard" class="dropdown-item">
                                    <i class="fas fa-chart-pie"></i><span>Ir al dashboard</span>
                                </a>
                                <a href="/logout" class="dropdown-item logout-item">
```
Reemplazar por:
```html
                                <a href="/dashboard" class="dropdown-item">
                                    <i class="fas fa-chart-pie"></i><span>Ir al dashboard</span>
                                </a>
                                <a href="{{ url_for('cambiar_password') }}" class="dropdown-item">
                                    <i class="fas fa-key"></i><span>Cambiar contraseña</span>
                                </a>
                                <a href="/logout" class="dropdown-item logout-item">
```

- [ ] **Step 2: Agregar enlace en el drawer (móvil)**

En `templates/base.html`, en la sección del drawer con "Cerrar Sesión", insertar el enlace ANTES del de logout:

Buscar:
```html
            <div class="drawer-section">
                <a href="/logout" class="drawer-item drawer-item-logout">
                    <i class="fas fa-sign-out-alt"></i><span>Cerrar Sesión</span>
                </a>
            </div>
```
Reemplazar por:
```html
            <div class="drawer-section">
                <a href="{{ url_for('cambiar_password') }}" class="drawer-item">
                    <i class="fas fa-key"></i><span>Cambiar contraseña</span>
                </a>
                <a href="/logout" class="drawer-item drawer-item-logout">
                    <i class="fas fa-sign-out-alt"></i><span>Cerrar Sesión</span>
                </a>
            </div>
```

- [ ] **Step 3: Verificar que las páginas siguen renderizando (url_for resuelve)**

Run: `python -m pytest tests/test_reskin_smoke.py -q`
Expected: PASS (no `BuildError`; el enlace `url_for('cambiar_password')` resuelve porque la ruta existe de Task 1).

- [ ] **Step 4: Commit**

```bash
git add templates/base.html
git commit -m "feat(cuenta): enlace 'Cambiar contraseña' en menú de usuario"
```

---

### Task 3: Verificación final

**Files:** ninguno (solo verificación)

- [ ] **Step 1: Correr la suite completa**

Run: `python -m pytest tests/ -q`
Expected: los 6 tests nuevos pasan; el conteo de fallas pre-existentes (22, no relacionadas: dashboard_kpis, etiquetas, consolidar_flujo, una de facturacion) no aumenta. Es decir: `passed` sube en 6, `failed` se mantiene en 22.

- [ ] **Step 2: Smoke manual (opcional, si hay app corriendo)**

Iniciar sesión, abrir el menú de usuario → "Cambiar contraseña", probar: clave actual incorrecta (error), confirmación distinta (error), clave corta (error), y cambio exitoso (redirige a login y la clave nueva funciona).

---

## Self-Review

**Spec coverage:**
- Ruta autoservicio solo para Vendedor → Task 1 (guard `isinstance`).
- Validaciones (actual correcta, nueva==confirmar, ≥8, ≠actual) → Task 1 Step 3.
- Éxito: set_password + commit + log + logout + redirect a login → Task 1 Step 3.
- Template `mobile-form-*` → Task 1 Step 4.
- Enlaces en dropdown + drawer → Task 2.
- Tests de todos los casos → Task 1 Step 1.
- Mínimo 8 y forzar re-login → reflejado en validación y `logout_user()` + test `test_exito_cambia_y_desloguea`.

**Placeholder scan:** Sin TBD/TODO; todo el código está completo.

**Type consistency:** Endpoint `cambiar_password`, template `cambiar_password.html`, campos de form `actual`/`nueva`/`confirmar` usados consistentemente en route, template y tests. `check_password`/`set_password` existen en el modelo `Vendedor`. `logout_user`, `flash`, `redirect`, `url_for`, `render_template` ya importados en `app.py`.
