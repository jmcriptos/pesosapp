# Permisos por rol configurables (#2) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Que `tiene_permiso` lea los permisos de la base (tablas `RolPermiso`/`Permiso`), editables desde una pantalla del super_admin (matriz recurso × acción), e incorporar los registros HACCP al sistema de permisos.

**Architecture:** Cambios en `app.py`: `tiene_permiso` pasa de un diccionario hardcodeado a leer `RolPermiso` (con fallback al diccionario, ahora extraído a `_permiso_default`); una función de siembra idempotente `_sembrar_permisos()`; las rutas de registros pasan de `requiere_rol` a `requiere_permiso_recurso('registros', …)`; y una ruta+plantilla de administración de la matriz. Sin cambios al decorador `requiere_permiso_recurso` (ya llama a `tiene_permiso`).

**Tech Stack:** Flask, SQLAlchemy, Jinja2, pytest, Postgres (prod) / SQLite (tests y local).

**Spec:** `docs/superpowers/specs/2026-05-31-permisos-configurables-design.md`

**Ejecutar tests con** `.venv/bin/python -m pytest ...`.

---

## File Structure

- **Modificar** `app.py`:
  - `_PERMISOS_DEFAULT` + `_permiso_default()` (fallback) y nuevo cuerpo de `Vendedor.tiene_permiso` (~295–337).
  - `PERMISOS_RECURSOS`, `PERMISOS_DEFAULTS`, `_sembrar_permisos()` (helpers de módulo).
  - Decoradores de ~25 rutas de registros: `requiere_rol`/`login_required` → `requiere_permiso_recurso('registros', …)`; y los context vars `es_admin`/`puede_verificar` de las 4 rutas index/historial.
  - Nueva ruta `gestionar_permisos` (`/admin/roles-permisos`).
- **Crear** `templates/admin/roles_permisos.html`.
- **Crear** `tests/test_permisos.py`.
- **DB**: sembrar `Permiso`/`RolPermiso` local y Heroku (las tablas ya existen).

---

## Task 1: `tiene_permiso` lee de la base (con fallback)

**Files:**
- Create: `tests/test_permisos.py`
- Modify: `app.py` (método `tiene_permiso` ~295; helpers nuevos antes de la clase `Vendedor` o a nivel módulo)

- [ ] **Step 1: Crear `tests/test_permisos.py` con fixture y tests del motor**

```python
"""Tests de permisos configurables (#2)."""
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
        ra = Rol(nombre='super_admin', descripcion='Admin')
        rs = Rol(nombre='supervisor', descripcion='Supervisor')
        rv = Rol(nombre='vendedor', descripcion='Vendedor')
        terr = Territorio(nombre='t1', descripcion='T1')
        _db.session.add_all([ra, rs, rv, terr])
        _db.session.flush()
        admin = Vendedor(username='admin', email='admin@t.com', nombre_completo='Admin',
                         rol_id=ra.id, territorio_id=terr.id, activo=True)
        admin.set_password('pw')
        vend = Vendedor(username='vend', email='vend@t.com', nombre_completo='Vend',
                        rol_id=rv.id, territorio_id=terr.id, activo=True)
        vend.set_password('pw')
        _db.session.add_all([admin, vend])
        _db.session.commit()
        IDS['ra'] = ra.id; IDS['rs'] = rs.id; IDS['rv'] = rv.id
        IDS['admin'] = admin.id; IDS['vend'] = vend.id
        yield flask_app
        _db.drop_all()


def _login(app, username):
    c = app.test_client()
    c.post('/login', data={'username': username, 'password': 'pw'}, follow_redirects=True)
    return c


def test_super_admin_siempre_true(app):
    from app import Vendedor
    with app.app_context():
        a = _db.session.get(Vendedor, IDS['admin'])
        assert a.tiene_permiso('pedidos', 'eliminar') is True
        assert a.tiene_permiso('registros', 'editar') is True


def test_fallback_sin_filas(app):
    from app import Vendedor
    with app.app_context():
        v = _db.session.get(Vendedor, IDS['vend'])
        # sin RolPermiso sembrado → usa defaults
        assert v.tiene_permiso('pedidos', 'editar') is True
        assert v.tiene_permiso('pedidos', 'eliminar') is False
        assert v.tiene_permiso('registros', 'crear') is True
        assert v.tiene_permiso('registros', 'editar') is False


def test_lee_de_rolpermiso(app):
    from app import Vendedor, Permiso, RolPermiso
    with app.app_context():
        p = Permiso(nombre='pedidos', recurso='pedidos', categoria='recurso')
        _db.session.add(p); _db.session.flush()
        rp = RolPermiso(rol_id=IDS['rv'], permiso_id=p.id,
                        puede_leer=True, puede_crear=False, puede_editar=False, puede_eliminar=False)
        _db.session.add(rp); _db.session.commit()
        v = _db.session.get(Vendedor, IDS['vend'])
        assert v.tiene_permiso('pedidos', 'leer') is True
        assert v.tiene_permiso('pedidos', 'crear') is False   # la fila DB manda sobre el default
```

- [ ] **Step 2: Correr → fallan**

Run: `.venv/bin/python -m pytest tests/test_permisos.py -v`
Expected: FAIL (`test_lee_de_rolpermiso` falla: el default da crear=True para pedidos; aún no lee la base)

- [ ] **Step 3: Añadir el fallback y reescribir `tiene_permiso`**

En `app.py`, agregar a nivel de módulo ANTES de `class Vendedor` (justo después de los imports / cerca del inicio, p. ej. tras la creación de `db`):

```python
_PERMISOS_DEFAULT = {
    'super_admin': {
        'productos': ['leer', 'crear', 'editar', 'eliminar'],
        'clientes': ['leer', 'crear', 'editar', 'eliminar'],
        'pedidos': ['leer', 'crear', 'editar', 'eliminar'],
        'vendedores': ['leer', 'crear', 'editar', 'eliminar'],
        'precios': ['leer', 'crear', 'editar', 'eliminar'],
        'reportes': ['leer', 'crear', 'editar', 'eliminar'],
        'importaciones': ['leer', 'crear', 'editar', 'eliminar'],
        'facturacion': ['leer', 'crear', 'editar', 'eliminar'],
        'registros': ['leer', 'crear', 'editar', 'eliminar'],
    },
    'supervisor': {
        'productos': ['leer'],
        'clientes': ['leer', 'editar'],
        'pedidos': ['leer', 'crear', 'editar'],
        'vendedores': ['leer'],
        'precios': ['leer'],
        'reportes': ['leer'],
        'importaciones': [],
        'facturacion': ['leer'],
        'registros': ['leer', 'crear', 'editar'],
    },
    'vendedor': {
        'productos': ['leer'],
        'clientes': ['leer', 'editar'],
        'pedidos': ['leer', 'crear', 'editar'],
        'vendedores': [],
        'precios': ['leer'],
        'reportes': [],
        'importaciones': [],
        'facturacion': [],
        'registros': ['leer', 'crear'],
    },
}


def _permiso_default(rol_nombre, recurso, accion):
    """Defaults de permisos (fallback cuando no hay filas en RolPermiso)."""
    return accion in _PERMISOS_DEFAULT.get(rol_nombre, {}).get(recurso, [])
```

Luego REEMPLAZAR el cuerpo del método `tiene_permiso` (app.py ~295–337) por:

```python
    def tiene_permiso(self, permiso_nombre, tipo_acceso='leer'):
        """Verifica un permiso leyendo de RolPermiso; super_admin siempre pasa;
        si no hay filas sembradas, cae a los defaults (_permiso_default)."""
        if not self.activo:
            return False
        if self.rol and self.rol.nombre == 'super_admin':
            return True
        rp = (RolPermiso.query.join(Permiso)
              .filter(RolPermiso.rol_id == self.rol_id,
                      Permiso.recurso == permiso_nombre).first())
        if rp is None:
            return _permiso_default(self.rol.nombre if self.rol else '', permiso_nombre, tipo_acceso)
        return bool({'leer': rp.puede_leer, 'crear': rp.puede_crear,
                     'editar': rp.puede_editar, 'eliminar': rp.puede_eliminar}.get(tipo_acceso, False))
```

NOTA: `Permiso` y `RolPermiso` se definen MÁS ABAJO en `app.py` (~2287). Como `tiene_permiso` los referencia en tiempo de ejecución (no de definición), no hay problema de orden.

- [ ] **Step 4: Correr → pasan**

Run: `.venv/bin/python -m pytest tests/test_permisos.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Confirmar que NO se rompen los tests de registros (usan el fallback)**

Run: `.venv/bin/python -m pytest tests/test_registro_limpieza.py tests/test_registro_temperaturas.py -q`
Expected: PASS (los roles caen al fallback con los mismos accesos de antes)

- [ ] **Step 6: Commit**

```bash
git add app.py tests/test_permisos.py
git commit -m "feat(permisos): tiene_permiso lee de RolPermiso con fallback a defaults

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 2: Función de siembra `_sembrar_permisos()`

**Files:**
- Modify: `app.py` (helpers de módulo, cerca de `_permiso_default`)
- Test: `tests/test_permisos.py`

- [ ] **Step 1: Añadir el test**

Agregar al final de `tests/test_permisos.py`:

```python
def test_sembrar_crea_filas_y_es_idempotente(app):
    from app import Vendedor, Permiso, RolPermiso, _sembrar_permisos
    with app.app_context():
        _sembrar_permisos()
        assert Permiso.query.filter_by(recurso='registros').first() is not None
        assert Permiso.query.count() == 5
        v = _db.session.get(Vendedor, IDS['vend'])
        assert v.tiene_permiso('registros', 'crear') is True
        assert v.tiene_permiso('registros', 'editar') is False
        n_rp = RolPermiso.query.count()
        # idempotente: re-sembrar no duplica ni resetea
        _sembrar_permisos()
        assert RolPermiso.query.count() == n_rp
```

- [ ] **Step 2: Correr → falla**

Run: `.venv/bin/python -m pytest tests/test_permisos.py::test_sembrar_crea_filas_y_es_idempotente -v`
Expected: FAIL — `ImportError: cannot import name '_sembrar_permisos'`

- [ ] **Step 3: Añadir constantes y la función de siembra**

En `app.py`, junto a `_permiso_default` (nivel módulo), agregar:

```python
PERMISOS_RECURSOS = ['productos', 'clientes', 'pedidos', 'precios', 'registros']

PERMISOS_DEFAULTS = {
    'vendedor':    {'productos': ['leer'], 'clientes': ['leer', 'editar'],
                    'pedidos': ['leer', 'crear', 'editar'], 'precios': ['leer'],
                    'registros': ['leer', 'crear']},
    'supervisor':  {'productos': ['leer'], 'clientes': ['leer', 'editar'],
                    'pedidos': ['leer', 'crear', 'editar'], 'precios': ['leer'],
                    'registros': ['leer', 'crear', 'editar']},
    'super_admin': {r: ['leer', 'crear', 'editar', 'eliminar'] for r in PERMISOS_RECURSOS},
}


def _sembrar_permisos():
    """Crea (idempotente, no destructivo) las filas Permiso por recurso y las
    filas RolPermiso por rol con los defaults. No sobreescribe filas existentes."""
    for rec in PERMISOS_RECURSOS:
        if not Permiso.query.filter_by(recurso=rec).first():
            db.session.add(Permiso(nombre=rec, recurso=rec, categoria='recurso',
                                   descripcion=f'Recurso {rec}'))
    db.session.flush()
    permisos = {p.recurso: p for p in Permiso.query.all()}
    for rol_nombre, recursos in PERMISOS_DEFAULTS.items():
        rol = Rol.query.filter_by(nombre=rol_nombre).first()
        if not rol:
            continue
        for rec, acciones in recursos.items():
            p = permisos.get(rec)
            if p is None:
                continue
            existe = RolPermiso.query.filter_by(rol_id=rol.id, permiso_id=p.id).first()
            if existe is None:
                db.session.add(RolPermiso(
                    rol_id=rol.id, permiso_id=p.id,
                    puede_leer='leer' in acciones, puede_crear='crear' in acciones,
                    puede_editar='editar' in acciones, puede_eliminar='eliminar' in acciones))
    db.session.commit()
```

- [ ] **Step 4: Correr → pasa**

Run: `.venv/bin/python -m pytest tests/test_permisos.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add app.py tests/test_permisos.py
git commit -m "feat(permisos): _sembrar_permisos idempotente (Permiso + RolPermiso por defaults)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 3: Convertir rutas de TEMPERATURAS a permiso 'registros'

**Files:**
- Modify: `app.py` (decoradores + context vars de las rutas de temperaturas)
- Test: `tests/test_permisos.py`

Mapeo (acción de `registros`):
- `temperaturas_index`, `temperatura_registrar` → **crear**
- `temperaturas_historial`, `temperaturas_export` → **leer**
- `camaras_list`, `camara_nueva`, `camara_editar`, `camara_toggle`, `registro_config`, `temperatura_revisar` → **editar**

- [ ] **Step 1: Añadir el test de enforcement (falla antes de convertir)**

Agregar al final de `tests/test_permisos.py`:

```python
def _set_rolpermiso(rec, leer=False, crear=False, editar=False, eliminar=False, rol_id=None):
    from app import Permiso, RolPermiso
    rol_id = rol_id or IDS['rv']
    p = Permiso.query.filter_by(recurso=rec).first()
    if p is None:
        p = Permiso(nombre=rec, recurso=rec, categoria='recurso'); _db.session.add(p); _db.session.flush()
    rp = RolPermiso.query.filter_by(rol_id=rol_id, permiso_id=p.id).first()
    if rp is None:
        rp = RolPermiso(rol_id=rol_id, permiso_id=p.id); _db.session.add(rp)
    rp.puede_leer, rp.puede_crear, rp.puede_editar, rp.puede_eliminar = leer, crear, editar, eliminar
    _db.session.commit()


def test_temp_registrar_sin_crear_bloqueado(app):
    with app.app_context():
        _set_rolpermiso('registros', leer=True, crear=False, editar=False)  # vendedor sin crear
    c = _login(app, 'vend')
    resp = c.get('/registros/temperaturas', follow_redirects=False)
    assert resp.status_code == 302  # redirigido por falta de permiso


def test_temp_config_requiere_editar(app):
    with app.app_context():
        _set_rolpermiso('registros', leer=True, crear=True, editar=False)
    c = _login(app, 'vend')
    resp = c.get('/registros/temperaturas/camaras', follow_redirects=False)
    assert resp.status_code == 302  # sin editar → bloqueado
```

- [ ] **Step 2: Correr → fallan**

Run: `.venv/bin/python -m pytest tests/test_permisos.py -k "temp_registrar or temp_config" -v`
Expected: FAIL (hoy `temperaturas_index` es `@login_required` → 200; `camaras_list` usa `requiere_rol` → 302 sólo por no ser super_admin, pero el test quiere que sea por permiso editar — verificá que falle el de registrar)

- [ ] **Step 3: Convertir los decoradores en `app.py`**

Para cada ruta de temperaturas, ajustar el decorador (mantener `@app.route` y `@login_required`; reemplazar `@requiere_rol([...])` por el de permiso, o AGREGAR el de permiso si solo tenía `@login_required`):

- `temperaturas_index`: tras `@login_required` agregar `@requiere_permiso_recurso('registros', 'crear')`.
- `temperatura_registrar`: tras `@login_required` agregar `@requiere_permiso_recurso('registros', 'crear')`.
- `temperaturas_historial`: tras `@login_required` agregar `@requiere_permiso_recurso('registros', 'leer')`.
- `temperaturas_export`: tras `@login_required` agregar `@requiere_permiso_recurso('registros', 'leer')`.
- `camaras_list`, `camara_nueva`, `camara_editar`, `camara_toggle`, `registro_config`: reemplazar `@requiere_rol(['super_admin'])` por `@requiere_permiso_recurso('registros', 'editar')`.
- `temperatura_revisar`: reemplazar `@requiere_rol(['super_admin', 'supervisor'])` por `@requiere_permiso_recurso('registros', 'editar')`.

- [ ] **Step 4: Actualizar context vars de `temperaturas_index` y `temperaturas_historial`**

En `temperaturas_index`, reemplazar:
```python
    es_admin = isinstance(current_user, Vendedor) and current_user.rol.nombre == 'super_admin'
```
por:
```python
    es_admin = (not isinstance(current_user, Vendedor)) or current_user.tiene_permiso('registros', 'editar')
```

En `temperaturas_historial`, reemplazar:
```python
    puede_verificar = isinstance(current_user, Vendedor) and current_user.rol.nombre in ('super_admin', 'supervisor')
```
por:
```python
    puede_verificar = (not isinstance(current_user, Vendedor)) or current_user.tiene_permiso('registros', 'editar')
```

- [ ] **Step 5: Correr los tests + la suite de temperaturas (no regresión)**

Run: `.venv/bin/python -m pytest tests/test_permisos.py -k "temp_registrar or temp_config" tests/test_registro_temperaturas.py -v`
Expected: PASS (los 2 nuevos + toda la suite de temperaturas, que usa super_admin/fallback)

- [ ] **Step 6: Commit**

```bash
git add app.py tests/test_permisos.py
git commit -m "feat(permisos): rutas de temperaturas usan permiso configurable 'registros'

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 4: Convertir rutas de LIMPIEZA a permiso 'registros'

**Files:**
- Modify: `app.py` (decoradores + context vars de las rutas de limpieza)
- Test: `tests/test_permisos.py`

Mapeo:
- `limpieza_index`, `limpieza_registrar` → **crear**
- `limpieza_historial`, `limpieza_export`, `productos_limpieza_index`, `registros_index` → **leer**
- `areas_limpieza_list`, `area_limpieza_nueva/editar/toggle`, `producto_limpieza_nuevo/editar/toggle`, `limpieza_revisar`, `limpieza_config` → **editar**

- [ ] **Step 1: Añadir el test**

Agregar al final de `tests/test_permisos.py`:

```python
def test_limpieza_registrar_sin_crear_bloqueado(app):
    with app.app_context():
        _set_rolpermiso('registros', leer=True, crear=False, editar=False)
    c = _login(app, 'vend')
    resp = c.get('/registros/limpieza', follow_redirects=False)
    assert resp.status_code == 302


def test_limpieza_areas_requiere_editar(app):
    with app.app_context():
        _set_rolpermiso('registros', leer=True, crear=True, editar=False)
    c = _login(app, 'vend')
    resp = c.get('/registros/limpieza/areas', follow_redirects=False)
    assert resp.status_code == 302


def test_registros_hub_requiere_leer(app):
    with app.app_context():
        _set_rolpermiso('registros', leer=False, crear=False, editar=False)
    c = _login(app, 'vend')
    resp = c.get('/registros', follow_redirects=False)
    assert resp.status_code == 302
```

- [ ] **Step 2: Correr → fallan**

Run: `.venv/bin/python -m pytest tests/test_permisos.py -k "limpieza_registrar or limpieza_areas or hub_requiere" -v`
Expected: FAIL (hoy esas rutas son `@login_required` → 200)

- [ ] **Step 3: Convertir los decoradores en `app.py`**

- `limpieza_index`, `limpieza_registrar`: tras `@login_required` agregar `@requiere_permiso_recurso('registros', 'crear')`.
- `limpieza_historial`, `limpieza_export`, `productos_limpieza_index`, `registros_index`: tras `@login_required` agregar `@requiere_permiso_recurso('registros', 'leer')`.
- `areas_limpieza_list`, `area_limpieza_nueva`, `area_limpieza_editar`, `area_limpieza_toggle`, `producto_limpieza_nuevo`, `producto_limpieza_editar`, `producto_limpieza_toggle`, `limpieza_config`: reemplazar `@requiere_rol(['super_admin'])` por `@requiere_permiso_recurso('registros', 'editar')`.
- `limpieza_revisar`: reemplazar `@requiere_rol(['super_admin', 'supervisor'])` por `@requiere_permiso_recurso('registros', 'editar')`.

- [ ] **Step 4: Actualizar context vars de `limpieza_index` y `limpieza_historial`**

En `limpieza_index`, reemplazar:
```python
    es_admin = isinstance(current_user, Vendedor) and current_user.rol.nombre == 'super_admin'
```
por:
```python
    es_admin = (not isinstance(current_user, Vendedor)) or current_user.tiene_permiso('registros', 'editar')
```

En `limpieza_historial`, reemplazar:
```python
    puede_verificar = isinstance(current_user, Vendedor) and current_user.rol.nombre in ('super_admin', 'supervisor')
```
por:
```python
    puede_verificar = (not isinstance(current_user, Vendedor)) or current_user.tiene_permiso('registros', 'editar')
```

NOTA: `productos_limpieza_index` también calcula `es_admin = ... == 'super_admin'`; reemplazarlo igual por `(not isinstance(current_user, Vendedor)) or current_user.tiene_permiso('registros', 'editar')` (controla si se ven los formularios de CRUD de productos).

- [ ] **Step 5: Correr tests + suite de limpieza (no regresión)**

Run: `.venv/bin/python -m pytest tests/test_permisos.py -k "limpieza_registrar or limpieza_areas or hub_requiere" tests/test_registro_limpieza.py -v`
Expected: PASS (los 3 nuevos + toda la suite de limpieza)

- [ ] **Step 6: Commit**

```bash
git add app.py tests/test_permisos.py
git commit -m "feat(permisos): rutas de limpieza usan permiso configurable 'registros'

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 5: Pantalla de administración de permisos

**Files:**
- Modify: `app.py` (nueva ruta `gestionar_permisos`, anexar tras `gestionar_vendedores` ~3118)
- Create: `templates/admin/roles_permisos.html`
- Test: `tests/test_permisos.py`

- [ ] **Step 1: Añadir los tests**

Agregar al final de `tests/test_permisos.py`:

```python
def test_permisos_no_admin_bloqueado(app):
    c = _login(app, 'vend')
    resp = c.get('/admin/roles-permisos', follow_redirects=False)
    assert resp.status_code in (302, 403)


def test_permisos_admin_ve_matriz(app):
    c = _login(app, 'admin')
    resp = c.get('/admin/roles-permisos')
    assert resp.status_code == 200
    body = resp.data.decode('utf-8')
    assert 'registros' in body
    assert f'perm_{IDS["rv"]}_pedidos_editar' in body


def test_permisos_post_cambia_acceso(app):
    from app import Vendedor
    c = _login(app, 'admin')
    # marcar para vendedor: pedidos leer+crear (sin editar) y registros leer
    c.post('/admin/roles-permisos', data={
        f'perm_{IDS["rv"]}_pedidos_leer': '1',
        f'perm_{IDS["rv"]}_pedidos_crear': '1',
        f'perm_{IDS["rv"]}_registros_leer': '1',
    }, follow_redirects=True)
    with app.app_context():
        v = _db.session.get(Vendedor, IDS['vend'])
        assert v.tiene_permiso('pedidos', 'crear') is True
        assert v.tiene_permiso('pedidos', 'editar') is False
        assert v.tiene_permiso('registros', 'crear') is False
```

- [ ] **Step 2: Correr → fallan**

Run: `.venv/bin/python -m pytest tests/test_permisos.py -k "permisos_" -v`
Expected: FAIL — 404 / BuildError

- [ ] **Step 3: Añadir la ruta en `app.py`** — anexar tras `gestionar_vendedores`:

```python
@app.route('/admin/roles-permisos', methods=['GET', 'POST'])
@login_required
@requiere_rol(['super_admin'])
def gestionar_permisos():
    acciones = ['leer', 'crear', 'editar', 'eliminar']
    roles = (Rol.query.filter(Rol.nombre.in_(['supervisor', 'vendedor']))
             .order_by(Rol.nombre).all())
    if request.method == 'POST':
        _sembrar_permisos()  # garantiza filas Permiso
        permisos = {p.recurso: p for p in Permiso.query.all()}
        for rol in roles:
            for rec in PERMISOS_RECURSOS:
                p = permisos.get(rec)
                if p is None:
                    continue
                rp = RolPermiso.query.filter_by(rol_id=rol.id, permiso_id=p.id).first()
                if rp is None:
                    rp = RolPermiso(rol_id=rol.id, permiso_id=p.id)
                    db.session.add(rp)
                rp.puede_leer = bool(request.form.get(f'perm_{rol.id}_{rec}_leer'))
                rp.puede_crear = bool(request.form.get(f'perm_{rol.id}_{rec}_crear'))
                rp.puede_editar = bool(request.form.get(f'perm_{rol.id}_{rec}_editar'))
                rp.puede_eliminar = bool(request.form.get(f'perm_{rol.id}_{rec}_eliminar'))
        db.session.commit()
        flash('Permisos actualizados.', 'success')
        return redirect(url_for('gestionar_permisos'))

    permisos = {p.recurso: p for p in Permiso.query.all()}
    matriz = {}
    for rol in roles:
        matriz[rol.id] = {}
        for rec in PERMISOS_RECURSOS:
            p = permisos.get(rec)
            rp = RolPermiso.query.filter_by(rol_id=rol.id, permiso_id=p.id).first() if p else None
            matriz[rol.id][rec] = {
                a: (getattr(rp, f'puede_{a}') if rp else _permiso_default(rol.nombre, rec, a))
                for a in acciones
            }
    return render_template('admin/roles_permisos.html',
                           roles=roles, recursos=PERMISOS_RECURSOS,
                           acciones=acciones, matriz=matriz)
```

- [ ] **Step 4: Crear `templates/admin/roles_permisos.html`**

```html
{% extends "base.html" %}
{% block title %}Roles y permisos{% endblock %}
{% block header_title %}🔐 Roles y permisos{% endblock %}
{% block content %}
<div class="admin-container perms-wrap">
  <p class="perms-intro">Definí qué puede hacer cada rol. <strong>super_admin</strong> siempre tiene acceso total.</p>

  <form method="POST" action="{{ url_for('gestionar_permisos') }}">
    <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
    {% for rol in roles %}
    <section class="perms-rol">
      <h3>{{ rol.nombre }}</h3>
      <table class="perms-table">
        <thead>
          <tr><th>Recurso</th>{% for a in acciones %}<th>{{ a }}</th>{% endfor %}</tr>
        </thead>
        <tbody>
          {% for rec in recursos %}
          <tr>
            <td class="perms-rec">{{ rec }}</td>
            {% for a in acciones %}
            <td>
              <input type="checkbox" name="perm_{{ rol.id }}_{{ rec }}_{{ a }}"
                     {{ 'checked' if matriz[rol.id][rec][a] }}>
            </td>
            {% endfor %}
          </tr>
          {% endfor %}
        </tbody>
      </table>
    </section>
    {% endfor %}
    <button type="submit" class="btn-primary-lg"><i class="fas fa-save"></i> Guardar permisos</button>
  </form>
</div>
{% endblock %}
{% block extra_css %}
{{ super() }}
<style>
.perms-wrap{max-width:900px;margin:0 auto}
.perms-intro{color:#475569;margin-bottom:16px}
.perms-rol{background:#fff;border:1px solid #e2e8f0;border-radius:12px;padding:16px;margin-bottom:16px}
.perms-rol h3{margin:0 0 10px;text-transform:capitalize;color:#0f172a}
.perms-table{width:100%;border-collapse:collapse;font-size:.9rem}
.perms-table th,.perms-table td{padding:8px;text-align:center;border-bottom:1px solid #f1f5f9}
.perms-table th:first-child,.perms-rec{text-align:left;font-weight:600;color:#334155;text-transform:capitalize}
.btn-primary-lg{background:linear-gradient(135deg,#1877ff,#4dabf7);color:#fff;border:none;
    padding:12px 28px;border-radius:10px;font-weight:600;display:inline-flex;align-items:center;gap:8px}
</style>
{% endblock %}
```

- [ ] **Step 5: Correr → pasan**

Run: `.venv/bin/python -m pytest tests/test_permisos.py -v`
Expected: PASS (todos)

- [ ] **Step 6: Commit**

```bash
git add app.py templates/admin/roles_permisos.html tests/test_permisos.py
git commit -m "feat(permisos): pantalla /admin/roles-permisos (matriz editable por super_admin)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 6: Suite completa + siembra local + sintaxis

**Files:** (verificación)

- [ ] **Step 1: Sintaxis**

Run: `.venv/bin/python -c "import ast; ast.parse(open('app.py').read()); print('OK')"`
Expected: `OK`

- [ ] **Step 2: Suite completa relevante**

Run: `.venv/bin/python -m pytest tests/test_permisos.py tests/test_admin_usuarios.py tests/test_registro_limpieza.py tests/test_registro_temperaturas.py -v`
Expected: PASS

- [ ] **Step 3: Sembrar permisos en la base local**

Run:
```bash
.venv/bin/python -c "from app import app, db, _sembrar_permisos; ctx=app.app_context(); ctx.push(); _sembrar_permisos(); print('sembrado')"
```
Expected: `sembrado`

- [ ] **Step 4: Commit (si hubo fixes)**

```bash
git add -A && git commit -m "test(permisos): suite completa en verde" || echo "sin cambios"
```

---

## Task 7: Siembra en Heroku y deploy

**Files:** (despliegue)

> La siembra debe correr para que las rutas convertidas tengan permisos en
> producción. El código tiene fallback a defaults, así que aunque la siembra no
> corriera, el comportamiento sería el de hoy — pero la pantalla de edición
> necesita las filas. Las tablas `permiso`/`rol_permiso` ya existen en prod.

- [ ] **Step 1: Deploy**

Run:
```bash
git push origin main && git push heroku main
```
Expected: build OK, `Released vNNN`.

- [ ] **Step 2: Sembrar en Heroku (one-off dyno)**

Run:
```bash
heroku run --app pesosapp -- python -c "from app import app, _sembrar_permisos; ctx=app.app_context(); ctx.push(); _sembrar_permisos(); print('sembrado')"
```
Expected: `sembrado`

- [ ] **Step 3: Reiniciar dyno**

Run: `heroku restart --app pesosapp`

- [ ] **Step 4: Smoke test (producción, super_admin)**

Abrir `https://pesosapp-caa46963237c.herokuapp.com/admin/roles-permisos` y verificar:
1. Se ve la matriz para supervisor y vendedor con los 5 recursos.
2. Cambiar un permiso (p. ej. dar `registros: editar` a vendedor) y guardar; al recargar queda marcado.
3. Un usuario vendedor de prueba refleja el cambio (puede/no puede según lo marcado).

---

## Self-Review (autor del plan)

**Cobertura del spec:**
- `tiene_permiso` lee de RolPermiso + super_admin bypass + fallback → Task 1 ✓
- Recursos = productos/clientes/pedidos/precios/registros → Tasks 1–2 (defaults, siembra) ✓
- Siembra idempotente local + Heroku → Tasks 2, 6, 7 ✓
- Registros HACCP convertidos (leer/crear/editar) + context vars → Tasks 3 y 4 ✓
- Pantalla /admin/roles-permisos → Task 5 ✓
- Tests de cada caso → Tasks 1–5 ✓
- No-regresión de registros (fallback) → Tasks 1/3/4 corren las suites existentes ✓

**Placeholders:** ninguno; todo el código (motor, siembra, decoradores, ruta, plantilla, tests) está completo.

**Consistencia de nombres:** `tiene_permiso`, `_permiso_default`, `_PERMISOS_DEFAULT`, `_sembrar_permisos`, `PERMISOS_RECURSOS`, `PERMISOS_DEFAULTS`, ruta `gestionar_permisos` (`/admin/roles-permisos`), recurso `'registros'`, campos `puede_leer/crear/editar/eliminar`, inputs `perm_<rol_id>_<rec>_<accion>` — coinciden entre motor, siembra, ruta, plantilla y tests.

**Nota:** la conversión de decoradores no rompe los tests existentes de registros porque el fallback (`_permiso_default`) replica los accesos actuales (vendedor: registros leer/crear; super_admin: bypass; supervisor: leer/crear/editar). Por eso Tasks 1/3/4 corren esas suites como red de seguridad.
