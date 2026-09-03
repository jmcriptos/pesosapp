# Módulo de maquila — Plan de implementación

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Registrar los ingredientes que un cliente entrega para maquila y seguir su rastro, kilo a kilo, hasta la factura del producto terminado que sale de ellos.

**Architecture:** Paquete `maquila/` con Blueprint, importado al final de `app.py` para resolver el ciclo de importación. El saldo de ingredientes nunca se guarda: se deriva de un ledger append-only (`movimiento_ingrediente`). El consumo de una corrida se reparte FIFO contra las recepciones; las cajas producidas se asignan FEFO a los pedidos, creando las `CajaPesada` con lote y fechas heredados.

**Tech Stack:** Flask 3.1.3, Flask-SQLAlchemy 3.1.1, Jinja2, htmx (ya en uso en `pesar`), pytest, xlsxwriter.

**Spec:** `docs/superpowers/specs/2026-09-03-maquila-ingredientes-design.md`

## Global Constraints

- **Pesos y cantidades en `db.Numeric`, nunca `db.Float`.** Los saldos se suman miles de veces.
- **Dinero y aritmética en `Decimal`**, nunca `float`. Convertir con `Decimal(str(x))`.
- **`db` se importa desde `app`**, no desde `extensions` (que es código muerto: `app.py:138` dice «Inicializar SQLAlchemy directamente»).
- **`app.py` solo se toca en un sitio**: tres líneas al final, antes de `if __name__ == '__main__':`.
- **El ledger es append-only.** Ningún `UPDATE` ni `DELETE` sobre `movimiento_ingrediente`, jamás. Las correcciones son movimientos nuevos.
- **Fechas en UTC naive** (`datetime.utcnow()`), convertidas a `America/Curacao` solo para mostrar y para agrupar por día. `app.py` ya expone `DASHBOARD_TIMEZONE`.
- **Todo acceso es `@requiere_rol(['super_admin'])`.**
- **Todo `<script>` inline lleva `nonce="{{ csp_nonce() }}"`** o no ejecuta en producción.
- **Manejadores por `data-*`**, nunca `onclick=` inline.
- **La firma en canvas usa un color fijo** (`#0f172a`), nunca leído de `document.body`: los tokens claros están scopeados a `.ops-*` y `body` devuelve el token oscuro.
- **El botón de guardar va en footer `position:sticky; bottom:0`**, o queda debajo de la tabbar fija.
- **Correr los tests así:** `.venv/bin/python -m pytest tests/ -q` — **sin** exportar `DATABASE_URL` a un archivo, o hay state-bleed masivo entre tests.
- Prefijo de rutas: `/maquila`. Nombre del blueprint: `maquila`. Endpoints se referencian como `maquila.<funcion>`.

## Estructura de archivos

```
maquila/
  __init__.py      # registrar_maquila(app): importa modelos y registra el blueprint
  models.py        # los doce modelos
  servicios.py     # ledger, FIFO, FEFO, códigos, recepción, corrida: funciones puras
  reportes.py      # las cuatro consultas de auditoría
  routes.py        # el Blueprint y sus vistas
templates/maquila/
  base_maquila.html    index.html
  ingredientes.html    recepciones.html    recepcion_nueva.html    recepcion_detalle.html
  recetas.html         receta_form.html
  corridas.html        corrida_detalle.html
  reporte_saldos.html  reporte_kardex.html  reporte_rendimiento.html  reporte_trazabilidad.html
  _asignar_cajas.html   # parcial htmx, se incrusta en pesar.html
static/css/maquila.css
tests/
  test_maquila_ledger.py      test_maquila_fifo.py        test_maquila_recepcion.py
  test_maquila_corrida.py     test_maquila_fefo.py        test_maquila_reportes.py
  test_maquila_rutas.py
scripts/maquila_migracion.sql
```

`servicios.py` concentra toda la lógica de negocio en funciones puras que reciben ids y devuelven objetos: es lo que permite probar el 80% del módulo sin levantar HTTP. `routes.py` solo traduce request → servicio → template.

---

### Task 1: Andamiaje — paquete, modelos y registro en `app.py`

**Files:**
- Create: `maquila/__init__.py`, `maquila/models.py`, `maquila/routes.py`
- Create: `templates/maquila/base_maquila.html`, `templates/maquila/index.html`
- Modify: `app.py` (tres líneas antes de `if __name__ == '__main__':`)
- Test: `tests/test_maquila_rutas.py`

**Interfaces:**
- Consumes: `db`, `Cliente`, `Producto`, `CajaPesada`, `Vendedor`, `requiere_rol` desde `app`.
- Produces: los doce modelos de `maquila.models`; `maquila.registrar_maquila(app)`; endpoint `maquila.index` en `/maquila`.

- [ ] **Step 1: Escribir el test que falla**

Crear `tests/test_maquila_rutas.py`:

```python
"""Tests de acceso y andamiaje del módulo de maquila."""
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
        rv = Rol(nombre='vendedor', descripcion='Vendedor')
        terr = Territorio(nombre='t1', descripcion='T1')
        _db.session.add_all([ra, rv, terr])
        _db.session.flush()
        admin = Vendedor(username='admin', email='a@t.com', nombre_completo='Admin',
                         rol_id=ra.id, territorio_id=terr.id, activo=True)
        admin.set_password('pw')
        vend = Vendedor(username='vend', email='v@t.com', nombre_completo='Vend',
                        rol_id=rv.id, territorio_id=terr.id, activo=True)
        vend.set_password('pw')
        _db.session.add_all([admin, vend])
        _db.session.commit()
        IDS['admin'] = admin.id
        yield flask_app
        _db.drop_all()


def _login(app, username):
    c = app.test_client()
    c.post('/login', data={'username': username, 'password': 'pw'}, follow_redirects=True)
    return c


def test_las_tablas_de_maquila_existen(app):
    """create_all() debe ver los modelos: si maquila.models no está importado,
    las tablas no se crean y todo el módulo falla sin explicación visible."""
    with app.app_context():
        nombres = set(_db.inspect(_db.engine).get_table_names())
    esperadas = {
        'ingrediente', 'recepcion_ingrediente', 'recepcion_linea', 'recepcion_bulto',
        'recepcion_foto', 'receta', 'receta_ingrediente', 'corrida_produccion',
        'corrida_caja', 'corrida_consumo', 'corrida_consumo_origen',
        'movimiento_ingrediente',
    }
    assert esperadas <= nombres


def test_admin_entra_al_indice(app):
    c = _login(app, 'admin')
    r = c.get('/maquila')
    assert r.status_code == 200


def test_vendedor_no_entra(app):
    c = _login(app, 'vend')
    r = c.get('/maquila', follow_redirects=False)
    assert r.status_code == 302


def test_anonimo_no_entra(app):
    r = app.test_client().get('/maquila', follow_redirects=False)
    assert r.status_code == 302
```

- [ ] **Step 2: Correr el test y ver que falla**

Run: `.venv/bin/python -m pytest tests/test_maquila_rutas.py -q`
Expected: FAIL — las tablas no existen y `/maquila` da 404.

- [ ] **Step 3: Escribir los modelos**

Crear `maquila/models.py`:

```python
"""Modelos del módulo de maquila.

`db` se importa de `app` (no de `extensions`, que es código muerto). El ciclo
de importación se resuelve porque `app.py` importa este paquete AL FINAL,
cuando `db` y los modelos base ya existen.
"""
from datetime import datetime

from app import db


class Ingrediente(db.Model):
    __tablename__ = 'ingrediente'
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(120), nullable=False, unique=True)
    unidad = db.Column(db.String(10), nullable=False, default='kg')
    activo = db.Column(db.Boolean, nullable=False, default=True)
    notas = db.Column(db.Text, nullable=True)

    def __repr__(self):
        return f'<Ingrediente {self.id} {self.nombre}>'


class RecepcionIngrediente(db.Model):
    __tablename__ = 'recepcion_ingrediente'
    id = db.Column(db.Integer, primary_key=True)
    codigo = db.Column(db.String(20), nullable=False, unique=True, index=True)
    cliente_id = db.Column(db.Integer, db.ForeignKey('cliente.id'), nullable=False, index=True)
    recibido_en = db.Column(db.Date, nullable=False)
    documento_cliente = db.Column(db.String(100), nullable=True)
    temperatura = db.Column(db.Numeric(5, 2), nullable=True)
    transportista = db.Column(db.String(120), nullable=True)
    firma = db.Column(db.LargeBinary, nullable=True)
    firma_mimetype = db.Column(db.String(50), nullable=True)
    notas = db.Column(db.Text, nullable=True)
    registrado_por = db.Column(db.Integer, db.ForeignKey('vendedor.id'), nullable=False)
    registrado_en = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    anulada_en = db.Column(db.DateTime, nullable=True)
    anulada_por = db.Column(db.Integer, db.ForeignKey('vendedor.id'), nullable=True)
    motivo_anulacion = db.Column(db.Text, nullable=True)

    cliente = db.relationship('Cliente')
    lineas = db.relationship('RecepcionLinea', back_populates='recepcion',
                             cascade='all, delete-orphan')
    fotos = db.relationship('RecepcionFoto', back_populates='recepcion',
                            cascade='all, delete-orphan')

    @property
    def anulada(self):
        return self.anulada_en is not None


class RecepcionLinea(db.Model):
    __tablename__ = 'recepcion_linea'
    id = db.Column(db.Integer, primary_key=True)
    recepcion_id = db.Column(db.Integer, db.ForeignKey('recepcion_ingrediente.id', ondelete='CASCADE'),
                             nullable=False, index=True)
    ingrediente_id = db.Column(db.Integer, db.ForeignKey('ingrediente.id'), nullable=False, index=True)
    lote_cliente = db.Column(db.String(50), nullable=True)
    fecha_vencimiento = db.Column(db.Date, nullable=True)
    peso_total = db.Column(db.Numeric(10, 3), nullable=False, default=0)

    recepcion = db.relationship('RecepcionIngrediente', back_populates='lineas')
    ingrediente = db.relationship('Ingrediente')
    bultos = db.relationship('RecepcionBulto', back_populates='linea',
                             cascade='all, delete-orphan', order_by='RecepcionBulto.numero')


class RecepcionBulto(db.Model):
    __tablename__ = 'recepcion_bulto'
    id = db.Column(db.Integer, primary_key=True)
    recepcion_linea_id = db.Column(db.Integer, db.ForeignKey('recepcion_linea.id', ondelete='CASCADE'),
                                   nullable=False, index=True)
    numero = db.Column(db.Integer, nullable=False)
    peso = db.Column(db.Numeric(8, 3), nullable=False)

    linea = db.relationship('RecepcionLinea', back_populates='bultos')

    __table_args__ = (
        db.UniqueConstraint('recepcion_linea_id', 'numero', name='uq_bulto_linea_numero'),
    )


class RecepcionFoto(db.Model):
    __tablename__ = 'recepcion_foto'
    id = db.Column(db.Integer, primary_key=True)
    recepcion_id = db.Column(db.Integer, db.ForeignKey('recepcion_ingrediente.id', ondelete='CASCADE'),
                             nullable=False, index=True)
    imagen = db.Column(db.LargeBinary, nullable=False)
    mimetype = db.Column(db.String(50), nullable=False)
    subida_en = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    recepcion = db.relationship('RecepcionIngrediente', back_populates='fotos')


class Receta(db.Model):
    __tablename__ = 'receta'
    id = db.Column(db.Integer, primary_key=True)
    producto_id = db.Column(db.Integer, db.ForeignKey('producto.id'), nullable=False, index=True)
    cliente_id = db.Column(db.Integer, db.ForeignKey('cliente.id'), nullable=True, index=True)
    nombre = db.Column(db.String(120), nullable=False)
    base_kg = db.Column(db.Numeric(10, 3), nullable=False, default=100)
    activa = db.Column(db.Boolean, nullable=False, default=True)
    creada_en = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    creada_por = db.Column(db.Integer, db.ForeignKey('vendedor.id'), nullable=True)

    producto = db.relationship('Producto')
    cliente = db.relationship('Cliente')
    ingredientes = db.relationship('RecetaIngrediente', back_populates='receta',
                                   cascade='all, delete-orphan')


class RecetaIngrediente(db.Model):
    __tablename__ = 'receta_ingrediente'
    id = db.Column(db.Integer, primary_key=True)
    receta_id = db.Column(db.Integer, db.ForeignKey('receta.id', ondelete='CASCADE'),
                          nullable=False, index=True)
    ingrediente_id = db.Column(db.Integer, db.ForeignKey('ingrediente.id'), nullable=False)
    cantidad = db.Column(db.Numeric(10, 3), nullable=False)

    receta = db.relationship('Receta', back_populates='ingredientes')
    ingrediente = db.relationship('Ingrediente')

    __table_args__ = (
        db.UniqueConstraint('receta_id', 'ingrediente_id', name='uq_receta_ingrediente'),
    )


class CorridaProduccion(db.Model):
    __tablename__ = 'corrida_produccion'
    id = db.Column(db.Integer, primary_key=True)
    codigo = db.Column(db.String(20), nullable=False, unique=True, index=True)
    cliente_id = db.Column(db.Integer, db.ForeignKey('cliente.id'), nullable=False, index=True)
    producto_id = db.Column(db.Integer, db.ForeignKey('producto.id'), nullable=False, index=True)
    receta_id = db.Column(db.Integer, db.ForeignKey('receta.id'), nullable=True)
    lote = db.Column(db.String(50), nullable=False, index=True)
    fecha_produccion = db.Column(db.Date, nullable=False)
    fecha_vencimiento = db.Column(db.Date, nullable=True)
    estado = db.Column(db.String(20), nullable=False, default='abierta')
    notas = db.Column(db.Text, nullable=True)
    registrado_por = db.Column(db.Integer, db.ForeignKey('vendedor.id'), nullable=False)
    registrado_en = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    cerrada_por = db.Column(db.Integer, db.ForeignKey('vendedor.id'), nullable=True)
    cerrada_en = db.Column(db.DateTime, nullable=True)

    cliente = db.relationship('Cliente')
    producto = db.relationship('Producto')
    receta = db.relationship('Receta')
    cajas = db.relationship('CorridaCaja', back_populates='corrida',
                            cascade='all, delete-orphan', order_by='CorridaCaja.numero')
    consumos = db.relationship('CorridaConsumo', back_populates='corrida',
                               cascade='all, delete-orphan')

    __table_args__ = (
        db.UniqueConstraint('cliente_id', 'lote', name='uq_corrida_cliente_lote'),
    )

    @property
    def peso_producido(self):
        """Suma de las cajas vivas. NO se guarda: un número guardado puede mentir."""
        from decimal import Decimal
        total = Decimal('0')
        for caja in self.cajas:
            if caja.anulada_en is None:
                total += Decimal(str(caja.peso))
        return total


class CorridaCaja(db.Model):
    __tablename__ = 'corrida_caja'
    id = db.Column(db.Integer, primary_key=True)
    corrida_id = db.Column(db.Integer, db.ForeignKey('corrida_produccion.id', ondelete='CASCADE'),
                           nullable=False, index=True)
    numero = db.Column(db.Integer, nullable=False)
    peso = db.Column(db.Numeric(8, 3), nullable=False)
    # ON DELETE SET NULL: si se borra la línea del pedido, la CajaPesada cae por
    # cascada y esta caja vuelve al stock sola, sin que ningún código lo recuerde.
    caja_pesada_id = db.Column(db.Integer,
                               db.ForeignKey('caja_pesada.id', ondelete='SET NULL'),
                               nullable=True, unique=True, index=True)
    anulada_en = db.Column(db.DateTime, nullable=True)
    motivo_anulacion = db.Column(db.Text, nullable=True)

    corrida = db.relationship('CorridaProduccion', back_populates='cajas')
    caja_pesada = db.relationship('CajaPesada')

    __table_args__ = (
        db.UniqueConstraint('corrida_id', 'numero', name='uq_corrida_caja_numero'),
    )

    @property
    def disponible(self):
        return self.caja_pesada_id is None and self.anulada_en is None


class CorridaConsumo(db.Model):
    __tablename__ = 'corrida_consumo'
    id = db.Column(db.Integer, primary_key=True)
    corrida_id = db.Column(db.Integer, db.ForeignKey('corrida_produccion.id', ondelete='CASCADE'),
                           nullable=False, index=True)
    ingrediente_id = db.Column(db.Integer, db.ForeignKey('ingrediente.id'), nullable=False)
    cantidad_teorica = db.Column(db.Numeric(10, 3), nullable=False, default=0)
    cantidad_real = db.Column(db.Numeric(10, 3), nullable=False)

    corrida = db.relationship('CorridaProduccion', back_populates='consumos')
    ingrediente = db.relationship('Ingrediente')
    origenes = db.relationship('CorridaConsumoOrigen', back_populates='consumo',
                               cascade='all, delete-orphan')

    __table_args__ = (
        db.UniqueConstraint('corrida_id', 'ingrediente_id', name='uq_corrida_consumo'),
    )


class CorridaConsumoOrigen(db.Model):
    __tablename__ = 'corrida_consumo_origen'
    id = db.Column(db.Integer, primary_key=True)
    corrida_consumo_id = db.Column(db.Integer, db.ForeignKey('corrida_consumo.id', ondelete='CASCADE'),
                                   nullable=False, index=True)
    recepcion_linea_id = db.Column(db.Integer, db.ForeignKey('recepcion_linea.id'),
                                   nullable=False, index=True)
    cantidad = db.Column(db.Numeric(10, 3), nullable=False)
    automatico = db.Column(db.Boolean, nullable=False, default=True)

    consumo = db.relationship('CorridaConsumo', back_populates='origenes')
    recepcion_linea = db.relationship('RecepcionLinea')


class MovimientoIngrediente(db.Model):
    """Ledger append-only. Nunca se hace UPDATE ni DELETE sobre esta tabla."""
    __tablename__ = 'movimiento_ingrediente'
    id = db.Column(db.Integer, primary_key=True)
    cliente_id = db.Column(db.Integer, db.ForeignKey('cliente.id'), nullable=False, index=True)
    ingrediente_id = db.Column(db.Integer, db.ForeignKey('ingrediente.id'), nullable=False, index=True)
    recepcion_linea_id = db.Column(db.Integer, db.ForeignKey('recepcion_linea.id'),
                                   nullable=True, index=True)
    tipo = db.Column(db.String(20), nullable=False)          # entrada|salida|ajuste|devolucion
    cantidad = db.Column(db.Numeric(10, 3), nullable=False)  # CON SIGNO
    origen_tipo = db.Column(db.String(20), nullable=False)   # recepcion|corrida|manual
    origen_id = db.Column(db.Integer, nullable=True)
    motivo = db.Column(db.Text, nullable=True)
    registrado_por = db.Column(db.Integer, db.ForeignKey('vendedor.id'), nullable=False)
    registrado_en = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    cliente = db.relationship('Cliente')
    ingrediente = db.relationship('Ingrediente')
    recepcion_linea = db.relationship('RecepcionLinea')
    vendedor = db.relationship('Vendedor')

    __table_args__ = (
        db.Index('ix_mov_cliente_ingr_fecha', 'cliente_id', 'ingrediente_id', 'registrado_en'),
    )
```

- [ ] **Step 4: Escribir el blueprint mínimo**

Crear `maquila/routes.py`:

```python
"""Vistas del módulo de maquila. Solo traducen request → servicio → template."""
from flask import Blueprint, render_template

from app import requiere_rol
from flask_login import login_required

bp = Blueprint('maquila', __name__, url_prefix='/maquila')


@bp.route('/')
@login_required
@requiere_rol(['super_admin'])
def index():
    return render_template('maquila/index.html', clientes=[])
```

Crear `maquila/__init__.py`:

```python
"""Módulo de maquila: ingredientes del cliente, producción y trazabilidad."""


def registrar_maquila(app):
    """Importa los modelos y registra el blueprint.

    Los modelos DEBEN quedar importados aunque nadie los use aquí: si no,
    `db.create_all()` no ve las tablas y todo el módulo falla en silencio.
    """
    from . import models  # noqa: F401
    from .routes import bp

    app.register_blueprint(bp)
    return bp
```

- [ ] **Step 5: Escribir las plantillas mínimas**

Crear `templates/maquila/base_maquila.html`:

```html
{% extends "base.html" %}
{% block content %}
<div class="ops-wrap maquila-wrap">
  <header class="ops-head">
    <h1 class="ops-title">{% block maquila_title %}Maquila{% endblock %}</h1>
    <nav class="maquila-nav">
      <a href="{{ url_for('maquila.index') }}">Resumen</a>
    </nav>
  </header>
  {% block maquila_body %}{% endblock %}
</div>
{% endblock %}
```

Crear `templates/maquila/index.html`:

```html
{% extends "maquila/base_maquila.html" %}
{% block title %}Maquila{% endblock %}
{% block maquila_title %}Maquila{% endblock %}
{% block maquila_body %}
  {% if not clientes %}
    <p class="ops-empty">Todavía no hay recepciones de ingredientes registradas.</p>
  {% endif %}
{% endblock %}
```

- [ ] **Step 6: Enganchar el módulo en `app.py`**

Añadir **justo antes** de `if __name__ == '__main__':` al final de `app.py`:

```python
# Módulo de maquila. Se importa AL FINAL a propósito: `maquila` importa `db`,
# los modelos base y `requiere_rol` de este archivo, y a esta altura ya existen.
from maquila import registrar_maquila  # noqa: E402
registrar_maquila(app)
```

- [ ] **Step 7: Correr los tests**

Run: `.venv/bin/python -m pytest tests/test_maquila_rutas.py -q`
Expected: PASS, 4 tests.

- [ ] **Step 8: Correr la suite completa para verificar que nada se rompió**

Run: `.venv/bin/python -m pytest tests/ -q`
Expected: mismo número de fallos que antes de empezar (anotar el baseline antes de tocar nada).

- [ ] **Step 9: Commit**

```bash
git add maquila/ templates/maquila/ tests/test_maquila_rutas.py app.py
git commit -m "feat(maquila): los doce modelos y el blueprint, enganchados al final de app.py"
```

---

### Task 2: El ledger — movimientos y saldos

**Files:**
- Create: `maquila/servicios.py`
- Test: `tests/test_maquila_ledger.py`

**Interfaces:**
- Consumes: `maquila.models.MovimientoIngrediente`, `RecepcionLinea`.
- Produces:
  - `registrar_movimiento(*, cliente_id, ingrediente_id, tipo, cantidad, origen_tipo, vendedor_id, origen_id=None, recepcion_linea_id=None, motivo=None) -> MovimientoIngrediente` — añade a la sesión, **no** hace commit.
  - `saldo_de_linea(recepcion_linea_id) -> Decimal`
  - `saldo_cliente_ingrediente(cliente_id, ingrediente_id) -> Decimal`
  - `saldos_de_cliente(cliente_id) -> list[dict]` con claves `ingrediente_id`, `ingrediente`, `unidad`, `recibido`, `consumido`, `ajustes`, `saldo`.
  - `class MotivoRequerido(ValueError)`

- [ ] **Step 1: Escribir los tests que fallan**

Crear `tests/test_maquila_ledger.py`:

```python
"""El ledger: un movimiento sube o baja el saldo, y nada más lo toca."""
import os
from datetime import date
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
        from app import Rol, Territorio, Vendedor, Cliente
        from maquila.models import Ingrediente, RecepcionIngrediente, RecepcionLinea
        ra = Rol(nombre='super_admin', descripcion='Admin')
        terr = Territorio(nombre='t1', descripcion='T1')
        _db.session.add_all([ra, terr])
        _db.session.flush()
        v = Vendedor(username='admin', email='a@t.com', nombre_completo='Admin',
                     rol_id=ra.id, territorio_id=terr.id, activo=True)
        v.set_password('pw')
        cli = Cliente(nombre='Maquila SA')
        ing = Ingrediente(nombre='Carne de res')
        _db.session.add_all([v, cli, ing])
        _db.session.flush()
        rec = RecepcionIngrediente(codigo='R-2026-0001', cliente_id=cli.id,
                                   recibido_en=date(2026, 9, 1), registrado_por=v.id)
        _db.session.add(rec)
        _db.session.flush()
        linea = RecepcionLinea(recepcion_id=rec.id, ingrediente_id=ing.id,
                               peso_total=Decimal('100.000'))
        _db.session.add(linea)
        _db.session.commit()
        IDS.update(vendedor=v.id, cliente=cli.id, ingrediente=ing.id, linea=linea.id)
        yield flask_app
        _db.drop_all()


def test_una_entrada_sube_el_saldo(app):
    from maquila import servicios
    with app.app_context():
        servicios.registrar_movimiento(
            cliente_id=IDS['cliente'], ingrediente_id=IDS['ingrediente'],
            tipo='entrada', cantidad=Decimal('100'), origen_tipo='recepcion',
            origen_id=1, vendedor_id=IDS['vendedor'], recepcion_linea_id=IDS['linea'])
        _db.session.commit()
        assert servicios.saldo_cliente_ingrediente(
            IDS['cliente'], IDS['ingrediente']) == Decimal('100')


def test_una_salida_baja_el_saldo(app):
    from maquila import servicios
    with app.app_context():
        servicios.registrar_movimiento(
            cliente_id=IDS['cliente'], ingrediente_id=IDS['ingrediente'],
            tipo='entrada', cantidad=Decimal('100'), origen_tipo='recepcion',
            origen_id=1, vendedor_id=IDS['vendedor'], recepcion_linea_id=IDS['linea'])
        servicios.registrar_movimiento(
            cliente_id=IDS['cliente'], ingrediente_id=IDS['ingrediente'],
            tipo='salida', cantidad=Decimal('-30'), origen_tipo='corrida',
            origen_id=1, vendedor_id=IDS['vendedor'], recepcion_linea_id=IDS['linea'])
        _db.session.commit()
        assert servicios.saldo_cliente_ingrediente(
            IDS['cliente'], IDS['ingrediente']) == Decimal('70')
        assert servicios.saldo_de_linea(IDS['linea']) == Decimal('70')


def test_la_salida_se_normaliza_a_negativo(app):
    """Pasar 30 en una salida debe guardarse como -30: el signo es del tipo,
    no de quien llama. Es el error más fácil de cometer desde una ruta."""
    from maquila import servicios
    with app.app_context():
        mov = servicios.registrar_movimiento(
            cliente_id=IDS['cliente'], ingrediente_id=IDS['ingrediente'],
            tipo='salida', cantidad=Decimal('30'), origen_tipo='corrida',
            origen_id=1, vendedor_id=IDS['vendedor'], recepcion_linea_id=IDS['linea'])
        _db.session.commit()
        assert mov.cantidad == Decimal('-30')


def test_un_ajuste_sin_motivo_se_rechaza(app):
    from maquila import servicios
    with app.app_context():
        with pytest.raises(servicios.MotivoRequerido):
            servicios.registrar_movimiento(
                cliente_id=IDS['cliente'], ingrediente_id=IDS['ingrediente'],
                tipo='ajuste', cantidad=Decimal('5'), origen_tipo='manual',
                vendedor_id=IDS['vendedor'])


def test_saldos_de_cliente_desglosa_recibido_y_consumido(app):
    from maquila import servicios
    with app.app_context():
        servicios.registrar_movimiento(
            cliente_id=IDS['cliente'], ingrediente_id=IDS['ingrediente'],
            tipo='entrada', cantidad=Decimal('100'), origen_tipo='recepcion',
            origen_id=1, vendedor_id=IDS['vendedor'], recepcion_linea_id=IDS['linea'])
        servicios.registrar_movimiento(
            cliente_id=IDS['cliente'], ingrediente_id=IDS['ingrediente'],
            tipo='salida', cantidad=Decimal('40'), origen_tipo='corrida',
            origen_id=1, vendedor_id=IDS['vendedor'], recepcion_linea_id=IDS['linea'])
        _db.session.commit()
        filas = servicios.saldos_de_cliente(IDS['cliente'])
        assert len(filas) == 1
        fila = filas[0]
        assert fila['recibido'] == Decimal('100')
        assert fila['consumido'] == Decimal('40')
        assert fila['saldo'] == Decimal('60')
        assert fila['ingrediente'] == 'Carne de res'
```

- [ ] **Step 2: Correr y ver que falla**

Run: `.venv/bin/python -m pytest tests/test_maquila_ledger.py -q`
Expected: FAIL — `No module named 'maquila.servicios'`.

- [ ] **Step 3: Escribir el servicio**

Crear `maquila/servicios.py`:

```python
"""Lógica de negocio del módulo de maquila.

Funciones puras sobre la sesión de SQLAlchemy: reciben ids, devuelven objetos o
Decimals. Ninguna hace commit — eso es responsabilidad de quien llama, para que
una recepción o un cierre de corrida quepan en una sola transacción.
"""
from decimal import Decimal

from sqlalchemy import func

from app import db
from .models import Ingrediente, MovimientoIngrediente

TIPOS_NEGATIVOS = {'salida'}
TIPOS_CON_MOTIVO = {'ajuste', 'devolucion'}
CERO = Decimal('0')


class MotivoRequerido(ValueError):
    """Un ajuste o una devolución sin motivo no es auditable."""


def _dec(valor):
    return valor if isinstance(valor, Decimal) else Decimal(str(valor or 0))


def registrar_movimiento(*, cliente_id, ingrediente_id, tipo, cantidad,
                         origen_tipo, vendedor_id, origen_id=None,
                         recepcion_linea_id=None, motivo=None):
    """Añade un movimiento al ledger. No hace commit.

    El signo lo pone el tipo, no quien llama: una `salida` siempre se guarda
    negativa aunque llegue en positivo.
    """
    if tipo in TIPOS_CON_MOTIVO and not (motivo or '').strip():
        raise MotivoRequerido(f'Un movimiento de tipo "{tipo}" exige un motivo')

    cantidad = _dec(cantidad)
    if tipo in TIPOS_NEGATIVOS:
        cantidad = -abs(cantidad)

    mov = MovimientoIngrediente(
        cliente_id=cliente_id,
        ingrediente_id=ingrediente_id,
        recepcion_linea_id=recepcion_linea_id,
        tipo=tipo,
        cantidad=cantidad,
        origen_tipo=origen_tipo,
        origen_id=origen_id,
        motivo=(motivo or None),
        registrado_por=vendedor_id,
    )
    db.session.add(mov)
    return mov


def saldo_de_linea(recepcion_linea_id):
    """Cuánto queda de una línea de recepción concreta. Es lo que usa el FIFO."""
    total = (db.session.query(func.sum(MovimientoIngrediente.cantidad))
             .filter(MovimientoIngrediente.recepcion_linea_id == recepcion_linea_id)
             .scalar())
    return _dec(total)


def saldo_cliente_ingrediente(cliente_id, ingrediente_id):
    total = (db.session.query(func.sum(MovimientoIngrediente.cantidad))
             .filter(MovimientoIngrediente.cliente_id == cliente_id,
                     MovimientoIngrediente.ingrediente_id == ingrediente_id)
             .scalar())
    return _dec(total)


def saldos_de_cliente(cliente_id):
    """Una fila por ingrediente con movimiento, desglosando entradas y salidas."""
    filas = (db.session.query(
                MovimientoIngrediente.ingrediente_id,
                Ingrediente.nombre,
                Ingrediente.unidad,
                func.sum(MovimientoIngrediente.cantidad).label('saldo'))
             .join(Ingrediente, Ingrediente.id == MovimientoIngrediente.ingrediente_id)
             .filter(MovimientoIngrediente.cliente_id == cliente_id)
             .group_by(MovimientoIngrediente.ingrediente_id,
                       Ingrediente.nombre, Ingrediente.unidad)
             .order_by(Ingrediente.nombre)
             .all())

    desglose = dict(
        db.session.query(
            MovimientoIngrediente.ingrediente_id,
            func.sum(MovimientoIngrediente.cantidad))
        .filter(MovimientoIngrediente.cliente_id == cliente_id,
                MovimientoIngrediente.cantidad > 0,
                MovimientoIngrediente.tipo == 'entrada')
        .group_by(MovimientoIngrediente.ingrediente_id).all())

    salidas = dict(
        db.session.query(
            MovimientoIngrediente.ingrediente_id,
            func.sum(MovimientoIngrediente.cantidad))
        .filter(MovimientoIngrediente.cliente_id == cliente_id,
                MovimientoIngrediente.tipo == 'salida')
        .group_by(MovimientoIngrediente.ingrediente_id).all())

    ajustes = dict(
        db.session.query(
            MovimientoIngrediente.ingrediente_id,
            func.sum(MovimientoIngrediente.cantidad))
        .filter(MovimientoIngrediente.cliente_id == cliente_id,
                MovimientoIngrediente.tipo.in_(('ajuste', 'devolucion')))
        .group_by(MovimientoIngrediente.ingrediente_id).all())

    resultado = []
    for ingrediente_id, nombre, unidad, saldo in filas:
        resultado.append({
            'ingrediente_id': ingrediente_id,
            'ingrediente': nombre,
            'unidad': unidad,
            'recibido': _dec(desglose.get(ingrediente_id)),
            'consumido': abs(_dec(salidas.get(ingrediente_id))),
            'ajustes': _dec(ajustes.get(ingrediente_id)),
            'saldo': _dec(saldo),
        })
    return resultado
```

- [ ] **Step 4: Correr los tests**

Run: `.venv/bin/python -m pytest tests/test_maquila_ledger.py -q`
Expected: PASS, 5 tests.

- [ ] **Step 5: Commit**

```bash
git add maquila/servicios.py tests/test_maquila_ledger.py
git commit -m "feat(maquila): el ledger, que es de donde sale todo saldo"
```

---

### Task 3: FIFO — repartir el consumo contra las recepciones

**Files:**
- Modify: `maquila/servicios.py`
- Test: `tests/test_maquila_fifo.py`

**Interfaces:**
- Consumes: `saldo_de_linea`, `_dec` de Task 2.
- Produces:
  - `repartir_fifo(cliente_id, ingrediente_id, cantidad) -> list[tuple[int, Decimal]]` — pares `(recepcion_linea_id, cantidad)`, la recepción más antigua primero. Lanza `SaldoInsuficiente` si no alcanza; no escribe nada.
  - `class SaldoInsuficiente(Exception)` con atributos `.ingrediente_id`, `.pedido` (Decimal), `.disponible` (Decimal), `.faltante` (Decimal).
  - `lineas_con_saldo(cliente_id, ingrediente_id) -> list[tuple[RecepcionLinea, Decimal]]`

- [ ] **Step 1: Escribir los tests que fallan**

Crear `tests/test_maquila_fifo.py`:

```python
"""FIFO: se consume primero lo que entró primero, y si no alcanza se avisa."""
import os
from datetime import date
from decimal import Decimal

import pytest

os.environ.setdefault('SECRET_KEY', 'test-secret')
os.environ.setdefault('FLASK_ENV', 'testing')
os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')

from app import app as flask_app, db as _db

IDS = {}


def _recibir(cliente_id, ingrediente_id, vendedor_id, codigo, dia, kg):
    """Crea una recepción de una línea y su movimiento de entrada."""
    from maquila import servicios
    from maquila.models import RecepcionIngrediente, RecepcionLinea
    rec = RecepcionIngrediente(codigo=codigo, cliente_id=cliente_id,
                               recibido_en=date(2026, 9, dia),
                               registrado_por=vendedor_id)
    _db.session.add(rec)
    _db.session.flush()
    linea = RecepcionLinea(recepcion_id=rec.id, ingrediente_id=ingrediente_id,
                           peso_total=Decimal(str(kg)))
    _db.session.add(linea)
    _db.session.flush()
    servicios.registrar_movimiento(
        cliente_id=cliente_id, ingrediente_id=ingrediente_id, tipo='entrada',
        cantidad=Decimal(str(kg)), origen_tipo='recepcion', origen_id=rec.id,
        vendedor_id=vendedor_id, recepcion_linea_id=linea.id)
    _db.session.commit()
    return linea.id


@pytest.fixture
def app():
    flask_app.config.update(TESTING=True, WTF_CSRF_ENABLED=False,
                            SQLALCHEMY_DATABASE_URI='sqlite:///:memory:')
    with flask_app.app_context():
        _db.create_all()
        from app import Rol, Territorio, Vendedor, Cliente
        from maquila.models import Ingrediente
        ra = Rol(nombre='super_admin', descripcion='Admin')
        terr = Territorio(nombre='t1', descripcion='T1')
        _db.session.add_all([ra, terr])
        _db.session.flush()
        v = Vendedor(username='admin', email='a@t.com', nombre_completo='Admin',
                     rol_id=ra.id, territorio_id=terr.id, activo=True)
        v.set_password('pw')
        cli = Cliente(nombre='Maquila SA')
        ing = Ingrediente(nombre='Carne de res')
        _db.session.add_all([v, cli, ing])
        _db.session.commit()
        IDS.update(vendedor=v.id, cliente=cli.id, ingrediente=ing.id)
        yield flask_app
        _db.drop_all()


def test_consume_de_la_recepcion_mas_antigua(app):
    from maquila import servicios
    with app.app_context():
        vieja = _recibir(IDS['cliente'], IDS['ingrediente'], IDS['vendedor'],
                         'R-2026-0001', 1, 100)
        _recibir(IDS['cliente'], IDS['ingrediente'], IDS['vendedor'],
                 'R-2026-0002', 5, 100)
        reparto = servicios.repartir_fifo(IDS['cliente'], IDS['ingrediente'],
                                          Decimal('60'))
        assert reparto == [(vieja, Decimal('60'))]


def test_reparte_entre_varias_cuando_una_no_alcanza(app):
    from maquila import servicios
    with app.app_context():
        vieja = _recibir(IDS['cliente'], IDS['ingrediente'], IDS['vendedor'],
                         'R-2026-0001', 1, 100)
        nueva = _recibir(IDS['cliente'], IDS['ingrediente'], IDS['vendedor'],
                         'R-2026-0002', 5, 100)
        reparto = servicios.repartir_fifo(IDS['cliente'], IDS['ingrediente'],
                                          Decimal('150'))
        assert reparto == [(vieja, Decimal('100')), (nueva, Decimal('50'))]


def test_salta_las_recepciones_agotadas(app):
    from maquila import servicios
    with app.app_context():
        vieja = _recibir(IDS['cliente'], IDS['ingrediente'], IDS['vendedor'],
                         'R-2026-0001', 1, 100)
        nueva = _recibir(IDS['cliente'], IDS['ingrediente'], IDS['vendedor'],
                         'R-2026-0002', 5, 100)
        servicios.registrar_movimiento(
            cliente_id=IDS['cliente'], ingrediente_id=IDS['ingrediente'],
            tipo='salida', cantidad=Decimal('100'), origen_tipo='corrida',
            origen_id=1, vendedor_id=IDS['vendedor'], recepcion_linea_id=vieja)
        _db.session.commit()
        reparto = servicios.repartir_fifo(IDS['cliente'], IDS['ingrediente'],
                                          Decimal('30'))
        assert reparto == [(nueva, Decimal('30'))]


def test_sin_saldo_suficiente_lanza_y_no_escribe_nada(app):
    from maquila import servicios
    from maquila.models import MovimientoIngrediente
    with app.app_context():
        _recibir(IDS['cliente'], IDS['ingrediente'], IDS['vendedor'],
                 'R-2026-0001', 1, 50)
        antes = MovimientoIngrediente.query.count()
        with pytest.raises(servicios.SaldoInsuficiente) as exc:
            servicios.repartir_fifo(IDS['cliente'], IDS['ingrediente'],
                                    Decimal('80'))
        assert exc.value.faltante == Decimal('30')
        assert exc.value.disponible == Decimal('50')
        assert MovimientoIngrediente.query.count() == antes


def test_cantidad_cero_o_negativa_se_rechaza(app):
    from maquila import servicios
    with app.app_context():
        with pytest.raises(ValueError):
            servicios.repartir_fifo(IDS['cliente'], IDS['ingrediente'], Decimal('0'))
```

- [ ] **Step 2: Correr y ver que falla**

Run: `.venv/bin/python -m pytest tests/test_maquila_fifo.py -q`
Expected: FAIL — `module 'maquila.servicios' has no attribute 'repartir_fifo'`.

- [ ] **Step 3: Implementar**

Añadir a `maquila/servicios.py` (y ampliar el import de modelos a
`from .models import Ingrediente, MovimientoIngrediente, RecepcionIngrediente, RecepcionLinea`):

```python
class SaldoInsuficiente(Exception):
    """No hay ingrediente suficiente del cliente para cubrir el consumo.

    Se bloquea a propósito: un saldo negativo envenena todos los reportes hacia
    abajo y deja al FIFO sin ninguna recepción honesta de dónde tirar. La salida
    legítima es registrar un ajuste de entrada con su motivo.
    """

    def __init__(self, ingrediente_id, pedido, disponible):
        self.ingrediente_id = ingrediente_id
        self.pedido = pedido
        self.disponible = disponible
        self.faltante = pedido - disponible
        super().__init__(
            f'Faltan {self.faltante} del ingrediente {ingrediente_id}: '
            f'se piden {pedido} y hay {disponible}')


def lineas_con_saldo(cliente_id, ingrediente_id):
    """Líneas de recepción del cliente con saldo > 0, más antigua primero.

    Ordena por fecha de recepción y desempata por id, para que el reparto sea
    determinista aunque dos recepciones lleguen el mismo día.
    """
    lineas = (RecepcionLinea.query
              .join(RecepcionIngrediente,
                    RecepcionIngrediente.id == RecepcionLinea.recepcion_id)
              .filter(RecepcionIngrediente.cliente_id == cliente_id,
                      RecepcionIngrediente.anulada_en.is_(None),
                      RecepcionLinea.ingrediente_id == ingrediente_id)
              .order_by(RecepcionIngrediente.recibido_en.asc(),
                        RecepcionLinea.id.asc())
              .all())
    con_saldo = []
    for linea in lineas:
        saldo = saldo_de_linea(linea.id)
        if saldo > CERO:
            con_saldo.append((linea, saldo))
    return con_saldo


def repartir_fifo(cliente_id, ingrediente_id, cantidad):
    """Reparte `cantidad` contra las recepciones más antiguas del cliente.

    Devuelve pares (recepcion_linea_id, cantidad). No escribe nada: quien llama
    decide si convierte el reparto en movimientos.
    """
    cantidad = _dec(cantidad)
    if cantidad <= CERO:
        raise ValueError('La cantidad a repartir debe ser positiva')

    disponibles = lineas_con_saldo(cliente_id, ingrediente_id)
    total_disponible = sum((saldo for _, saldo in disponibles), CERO)
    if total_disponible < cantidad:
        raise SaldoInsuficiente(ingrediente_id, cantidad, total_disponible)

    reparto = []
    restante = cantidad
    for linea, saldo in disponibles:
        if restante <= CERO:
            break
        toma = saldo if saldo < restante else restante
        reparto.append((linea.id, toma))
        restante -= toma
    return reparto
```

- [ ] **Step 4: Correr los tests**

Run: `.venv/bin/python -m pytest tests/test_maquila_fifo.py -q`
Expected: PASS, 5 tests.

- [ ] **Step 5: Commit**

```bash
git add maquila/servicios.py tests/test_maquila_fifo.py
git commit -m "feat(maquila): FIFO contra las recepciones, y un no rotundo cuando no alcanza"
```

---

### Task 4: Recepción — códigos correlativos, alta y anulación

**Files:**
- Modify: `maquila/servicios.py`
- Test: `tests/test_maquila_recepcion.py`

**Interfaces:**
- Consumes: `registrar_movimiento`, `saldo_de_linea`, `_dec`, `CERO`.
- Produces:
  - `siguiente_codigo(prefijo, anio=None) -> str` — `'R-2026-0042'`. `prefijo` es `'R'` o `'P'`.
  - `crear_recepcion(*, cliente_id, recibido_en, vendedor_id, lineas, documento_cliente=None, temperatura=None, transportista=None, notas=None, firma=None, firma_mimetype=None, fotos=None) -> RecepcionIngrediente`
    donde `lineas` es una lista de dicts `{'ingrediente_id': int, 'lote_cliente': str|None, 'fecha_vencimiento': date|None, 'bultos': [Decimal, ...], 'peso_total': Decimal|None}` y `fotos` una lista de `(bytes, mimetype)`. **Hace commit** (es una transacción completa).
  - `anular_recepcion(recepcion, vendedor_id, motivo)` — escribe los movimientos inversos. Lanza `RecepcionConsumida` si alguna línea ya se consumió.
  - `class RecepcionConsumida(Exception)`
  - `class RecepcionInvalida(ValueError)`

- [ ] **Step 1: Escribir los tests que fallan**

Crear `tests/test_maquila_recepcion.py`:

```python
"""Alta y anulación de recepciones de ingredientes."""
import os
from datetime import date
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
        from app import Rol, Territorio, Vendedor, Cliente
        from maquila.models import Ingrediente
        ra = Rol(nombre='super_admin', descripcion='Admin')
        terr = Territorio(nombre='t1', descripcion='T1')
        _db.session.add_all([ra, terr])
        _db.session.flush()
        v = Vendedor(username='admin', email='a@t.com', nombre_completo='Admin',
                     rol_id=ra.id, territorio_id=terr.id, activo=True)
        v.set_password('pw')
        cli = Cliente(nombre='Maquila SA')
        ing = Ingrediente(nombre='Carne de res')
        ing2 = Ingrediente(nombre='Grasa')
        _db.session.add_all([v, cli, ing, ing2])
        _db.session.commit()
        IDS.update(vendedor=v.id, cliente=cli.id,
                   ingrediente=ing.id, ingrediente2=ing2.id)
        yield flask_app
        _db.drop_all()


def test_el_codigo_es_correlativo_por_anio(app):
    from maquila import servicios
    with app.app_context():
        assert servicios.siguiente_codigo('R', 2026) == 'R-2026-0001'
        servicios.crear_recepcion(
            cliente_id=IDS['cliente'], recibido_en=date(2026, 9, 1),
            vendedor_id=IDS['vendedor'],
            lineas=[{'ingrediente_id': IDS['ingrediente'],
                     'bultos': [Decimal('10')]}])
        assert servicios.siguiente_codigo('R', 2026) == 'R-2026-0002'


def test_el_peso_total_es_la_suma_de_los_bultos(app):
    from maquila import servicios
    with app.app_context():
        rec = servicios.crear_recepcion(
            cliente_id=IDS['cliente'], recibido_en=date(2026, 9, 1),
            vendedor_id=IDS['vendedor'],
            lineas=[{'ingrediente_id': IDS['ingrediente'],
                     'bultos': [Decimal('10.5'), Decimal('9.5'), Decimal('20')]}])
        assert rec.lineas[0].peso_total == Decimal('40.000')
        assert len(rec.lineas[0].bultos) == 3
        assert [b.numero for b in rec.lineas[0].bultos] == [1, 2, 3]


def test_a_granel_se_acepta_el_peso_total_sin_bultos(app):
    from maquila import servicios
    with app.app_context():
        rec = servicios.crear_recepcion(
            cliente_id=IDS['cliente'], recibido_en=date(2026, 9, 1),
            vendedor_id=IDS['vendedor'],
            lineas=[{'ingrediente_id': IDS['ingrediente'],
                     'peso_total': Decimal('75.5')}])
        assert rec.lineas[0].peso_total == Decimal('75.500')
        assert rec.lineas[0].bultos == []


def test_sin_documento_del_cliente_es_valido(app):
    """El cliente a veces manda la carne sin ningún papel."""
    from maquila import servicios
    with app.app_context():
        rec = servicios.crear_recepcion(
            cliente_id=IDS['cliente'], recibido_en=date(2026, 9, 1),
            vendedor_id=IDS['vendedor'], documento_cliente=None,
            lineas=[{'ingrediente_id': IDS['ingrediente'],
                     'bultos': [Decimal('10')]}])
        assert rec.documento_cliente is None
        assert rec.codigo.startswith('R-')


def test_el_alta_escribe_un_movimiento_de_entrada_por_linea(app):
    from maquila import servicios
    from maquila.models import MovimientoIngrediente
    with app.app_context():
        servicios.crear_recepcion(
            cliente_id=IDS['cliente'], recibido_en=date(2026, 9, 1),
            vendedor_id=IDS['vendedor'],
            lineas=[{'ingrediente_id': IDS['ingrediente'], 'bultos': [Decimal('10')]},
                    {'ingrediente_id': IDS['ingrediente2'], 'bultos': [Decimal('4')]}])
        movs = MovimientoIngrediente.query.all()
        assert len(movs) == 2
        assert all(m.tipo == 'entrada' and m.origen_tipo == 'recepcion' for m in movs)
        assert sorted(m.cantidad for m in movs) == [Decimal('4.000'), Decimal('10.000')]


def test_una_recepcion_sin_lineas_se_rechaza(app):
    from maquila import servicios
    with app.app_context():
        with pytest.raises(servicios.RecepcionInvalida):
            servicios.crear_recepcion(
                cliente_id=IDS['cliente'], recibido_en=date(2026, 9, 1),
                vendedor_id=IDS['vendedor'], lineas=[])


def test_anular_una_recepcion_intacta_escribe_los_inversos(app):
    from maquila import servicios
    from maquila.models import MovimientoIngrediente
    with app.app_context():
        rec = servicios.crear_recepcion(
            cliente_id=IDS['cliente'], recibido_en=date(2026, 9, 1),
            vendedor_id=IDS['vendedor'],
            lineas=[{'ingrediente_id': IDS['ingrediente'], 'bultos': [Decimal('10')]}])
        servicios.anular_recepcion(rec, IDS['vendedor'], 'Llegó en mal estado')
        _db.session.commit()
        assert rec.anulada is True
        assert servicios.saldo_cliente_ingrediente(
            IDS['cliente'], IDS['ingrediente']) == Decimal('0')
        # No se borró nada: quedan los dos movimientos.
        assert MovimientoIngrediente.query.count() == 2


def test_anular_una_recepcion_ya_consumida_se_rechaza(app):
    from maquila import servicios
    with app.app_context():
        rec = servicios.crear_recepcion(
            cliente_id=IDS['cliente'], recibido_en=date(2026, 9, 1),
            vendedor_id=IDS['vendedor'],
            lineas=[{'ingrediente_id': IDS['ingrediente'], 'bultos': [Decimal('10')]}])
        servicios.registrar_movimiento(
            cliente_id=IDS['cliente'], ingrediente_id=IDS['ingrediente'],
            tipo='salida', cantidad=Decimal('4'), origen_tipo='corrida',
            origen_id=1, vendedor_id=IDS['vendedor'],
            recepcion_linea_id=rec.lineas[0].id)
        _db.session.commit()
        with pytest.raises(servicios.RecepcionConsumida):
            servicios.anular_recepcion(rec, IDS['vendedor'], 'Error de captura')


def test_anular_sin_motivo_se_rechaza(app):
    from maquila import servicios
    with app.app_context():
        rec = servicios.crear_recepcion(
            cliente_id=IDS['cliente'], recibido_en=date(2026, 9, 1),
            vendedor_id=IDS['vendedor'],
            lineas=[{'ingrediente_id': IDS['ingrediente'], 'bultos': [Decimal('10')]}])
        with pytest.raises(servicios.MotivoRequerido):
            servicios.anular_recepcion(rec, IDS['vendedor'], '   ')
```

- [ ] **Step 2: Correr y ver que falla**

Run: `.venv/bin/python -m pytest tests/test_maquila_recepcion.py -q`
Expected: FAIL — `has no attribute 'siguiente_codigo'`.

- [ ] **Step 3: Implementar**

Añadir a `maquila/servicios.py` (ampliar el import de modelos con
`RecepcionBulto`, `RecepcionFoto` y añadir `from datetime import date as _date, datetime`):

```python
class RecepcionInvalida(ValueError):
    """Faltan datos mínimos para dar de alta la recepción."""


class RecepcionConsumida(Exception):
    """La recepción ya alimentó una corrida: anularla rompería la cadena.

    La corrección legítima a esta altura es un ajuste con motivo, no una
    anulación.
    """


_PREFIJOS = {'R': RecepcionIngrediente}


def siguiente_codigo(prefijo, anio=None):
    """Siguiente correlativo del año, con el formato R-2026-0042.

    Cuenta los códigos existentes del año en vez de llevar una tabla de
    secuencias: a la escala de esta app (decenas de recepciones al mes) es
    exacto y no añade una pieza más que mantener.
    """
    from .models import CorridaProduccion
    modelos = {'R': RecepcionIngrediente, 'P': CorridaProduccion}
    modelo = modelos.get(prefijo)
    if modelo is None:
        raise ValueError(f'Prefijo de código desconocido: {prefijo}')

    anio = anio or _date.today().year
    patron = f'{prefijo}-{anio}-%'
    ultimo = (db.session.query(func.max(modelo.codigo))
              .filter(modelo.codigo.like(patron))
              .scalar())
    siguiente = 1 if not ultimo else int(ultimo.rsplit('-', 1)[1]) + 1
    return f'{prefijo}-{anio}-{siguiente:04d}'


def crear_recepcion(*, cliente_id, recibido_en, vendedor_id, lineas,
                    documento_cliente=None, temperatura=None, transportista=None,
                    notas=None, firma=None, firma_mimetype=None, fotos=None):
    """Da de alta una recepción completa en una sola transacción.

    Cabecera, líneas, bultos, fotos y un movimiento de entrada por línea. Si
    algo falla, no queda media recepción.
    """
    if not lineas:
        raise RecepcionInvalida('Una recepción necesita al menos una línea')

    recepcion = RecepcionIngrediente(
        codigo=siguiente_codigo('R', recibido_en.year),
        cliente_id=cliente_id,
        recibido_en=recibido_en,
        documento_cliente=(documento_cliente or None),
        temperatura=(_dec(temperatura) if temperatura not in (None, '') else None),
        transportista=(transportista or None),
        notas=(notas or None),
        firma=firma,
        firma_mimetype=firma_mimetype,
        registrado_por=vendedor_id,
    )
    db.session.add(recepcion)
    db.session.flush()

    for datos in lineas:
        bultos = [_dec(p) for p in (datos.get('bultos') or [])]
        if bultos:
            peso_total = sum(bultos, CERO)
        else:
            peso_total = _dec(datos.get('peso_total'))
        if peso_total <= CERO:
            raise RecepcionInvalida(
                'Cada línea necesita bultos pesados o un peso total positivo')

        linea = RecepcionLinea(
            recepcion_id=recepcion.id,
            ingrediente_id=datos['ingrediente_id'],
            lote_cliente=(datos.get('lote_cliente') or None),
            fecha_vencimiento=datos.get('fecha_vencimiento'),
            peso_total=peso_total,
        )
        db.session.add(linea)
        db.session.flush()

        for numero, peso in enumerate(bultos, start=1):
            db.session.add(RecepcionBulto(
                recepcion_linea_id=linea.id, numero=numero, peso=peso))

        registrar_movimiento(
            cliente_id=cliente_id,
            ingrediente_id=linea.ingrediente_id,
            tipo='entrada',
            cantidad=peso_total,
            origen_tipo='recepcion',
            origen_id=recepcion.id,
            vendedor_id=vendedor_id,
            recepcion_linea_id=linea.id,
        )

    for imagen, mimetype in (fotos or []):
        db.session.add(RecepcionFoto(
            recepcion_id=recepcion.id, imagen=imagen, mimetype=mimetype))

    db.session.commit()
    return recepcion


def anular_recepcion(recepcion, vendedor_id, motivo):
    """Anula una recepción escribiendo los movimientos inversos.

    Solo se permite si ninguna línea se consumió: el saldo de cada una tiene que
    seguir igual a su peso. No borra ninguna fila — el ledger es append-only.
    """
    if not (motivo or '').strip():
        raise MotivoRequerido('Anular una recepción exige un motivo')
    if recepcion.anulada:
        raise RecepcionInvalida('La recepción ya estaba anulada')

    for linea in recepcion.lineas:
        if saldo_de_linea(linea.id) != _dec(linea.peso_total):
            raise RecepcionConsumida(
                f'La línea {linea.id} de {recepcion.codigo} ya se consumió; '
                f'la corrección a esta altura es un ajuste, no una anulación')

    for linea in recepcion.lineas:
        registrar_movimiento(
            cliente_id=recepcion.cliente_id,
            ingrediente_id=linea.ingrediente_id,
            tipo='ajuste',
            cantidad=-_dec(linea.peso_total),
            origen_tipo='recepcion',
            origen_id=recepcion.id,
            vendedor_id=vendedor_id,
            recepcion_linea_id=linea.id,
            motivo=f'Anulación de {recepcion.codigo}: {motivo.strip()}',
        )

    recepcion.anulada_en = datetime.utcnow()
    recepcion.anulada_por = vendedor_id
    recepcion.motivo_anulacion = motivo.strip()
    return recepcion
```

- [ ] **Step 4: Correr los tests**

Run: `.venv/bin/python -m pytest tests/test_maquila_recepcion.py -q`
Expected: PASS, 9 tests.

- [ ] **Step 5: Commit**

```bash
git add maquila/servicios.py tests/test_maquila_recepcion.py
git commit -m "feat(maquila): recepciones con código propio, porque el cliente no siempre manda papel"
```

---

### Task 5: Recetas — cuál aplica y cuánto propone

**Files:**
- Modify: `maquila/servicios.py`
- Test: `tests/test_maquila_receta.py`

**Interfaces:**
- Consumes: `_dec`, `CERO`.
- Produces:
  - `receta_activa(producto_id, cliente_id) -> Receta | None` — la del cliente gana; si no hay, la genérica (`cliente_id IS NULL`).
  - `consumo_teorico(receta, kg_producidos) -> dict[int, Decimal]` — `{ingrediente_id: cantidad}`.
  - `validar_receta_unica(producto_id, cliente_id, receta_id=None)` — lanza `RecetaDuplicada` si ya hay otra activa para esa combinación.
  - `class RecetaDuplicada(ValueError)`

- [ ] **Step 1: Escribir los tests que fallan**

Crear `tests/test_maquila_receta.py`:

```python
"""Qué receta aplica y cuánto propone consumir."""
import os
from decimal import Decimal

import pytest

os.environ.setdefault('SECRET_KEY', 'test-secret')
os.environ.setdefault('FLASK_ENV', 'testing')
os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')

from app import app as flask_app, db as _db

IDS = {}


def _receta(producto_id, cliente_id, base_kg, items, activa=True):
    """items: [(ingrediente_id, cantidad_por_base)]"""
    from maquila.models import Receta, RecetaIngrediente
    r = Receta(producto_id=producto_id, cliente_id=cliente_id, nombre='R',
               base_kg=Decimal(str(base_kg)), activa=activa)
    _db.session.add(r)
    _db.session.flush()
    for ingrediente_id, cantidad in items:
        _db.session.add(RecetaIngrediente(receta_id=r.id,
                                          ingrediente_id=ingrediente_id,
                                          cantidad=Decimal(str(cantidad))))
    _db.session.commit()
    return r


@pytest.fixture
def app():
    flask_app.config.update(TESTING=True, WTF_CSRF_ENABLED=False,
                            SQLALCHEMY_DATABASE_URI='sqlite:///:memory:')
    with flask_app.app_context():
        _db.create_all()
        from app import Rol, Territorio, Vendedor, Cliente, Producto
        from maquila.models import Ingrediente
        ra = Rol(nombre='super_admin', descripcion='Admin')
        terr = Territorio(nombre='t1', descripcion='T1')
        _db.session.add_all([ra, terr])
        _db.session.flush()
        v = Vendedor(username='admin', email='a@t.com', nombre_completo='Admin',
                     rol_id=ra.id, territorio_id=terr.id, activo=True)
        v.set_password('pw')
        cli = Cliente(nombre='Maquila SA')
        prod = Producto(nombre='Chorizo', se_pesa=True, tax_rate=10)
        ing = Ingrediente(nombre='Carne de res')
        ing2 = Ingrediente(nombre='Grasa')
        _db.session.add_all([v, cli, prod, ing, ing2])
        _db.session.commit()
        IDS.update(vendedor=v.id, cliente=cli.id, producto=prod.id,
                   ingrediente=ing.id, ingrediente2=ing2.id)
        yield flask_app
        _db.drop_all()


def test_la_receta_del_cliente_le_gana_a_la_generica(app):
    from maquila import servicios
    with app.app_context():
        _receta(IDS['producto'], None, 100, [(IDS['ingrediente'], 90)])
        propia = _receta(IDS['producto'], IDS['cliente'], 100,
                         [(IDS['ingrediente'], 80)])
        elegida = servicios.receta_activa(IDS['producto'], IDS['cliente'])
        assert elegida.id == propia.id


def test_sin_receta_propia_cae_a_la_generica(app):
    from maquila import servicios
    with app.app_context():
        generica = _receta(IDS['producto'], None, 100, [(IDS['ingrediente'], 90)])
        elegida = servicios.receta_activa(IDS['producto'], IDS['cliente'])
        assert elegida.id == generica.id


def test_una_receta_inactiva_no_se_elige(app):
    from maquila import servicios
    with app.app_context():
        _receta(IDS['producto'], IDS['cliente'], 100,
                [(IDS['ingrediente'], 80)], activa=False)
        assert servicios.receta_activa(IDS['producto'], IDS['cliente']) is None


def test_el_consumo_teorico_escala_con_lo_producido(app):
    from maquila import servicios
    with app.app_context():
        r = _receta(IDS['producto'], IDS['cliente'], 100,
                    [(IDS['ingrediente'], 80), (IDS['ingrediente2'], 25)])
        teorico = servicios.consumo_teorico(r, Decimal('250'))
        assert teorico[IDS['ingrediente']] == Decimal('200.000')
        assert teorico[IDS['ingrediente2']] == Decimal('62.500')


def test_dos_recetas_activas_iguales_se_rechazan_al_guardar(app):
    from maquila import servicios
    with app.app_context():
        _receta(IDS['producto'], IDS['cliente'], 100, [(IDS['ingrediente'], 80)])
        with pytest.raises(servicios.RecetaDuplicada):
            servicios.validar_receta_unica(IDS['producto'], IDS['cliente'])
```

- [ ] **Step 2: Correr y ver que falla**

Run: `.venv/bin/python -m pytest tests/test_maquila_receta.py -q`
Expected: FAIL — `has no attribute 'receta_activa'`.

- [ ] **Step 3: Implementar**

Añadir a `maquila/servicios.py` (ampliar el import de modelos con `Receta`):

```python
class RecetaDuplicada(ValueError):
    """Ya existe otra receta activa para ese producto y ese cliente.

    Se rechaza al guardar la receta, no al usarla: descubrir el empate cuando ya
    estás cerrando una corrida es descubrirlo tarde.
    """


def receta_activa(producto_id, cliente_id):
    """La receta que aplica: la del cliente gana; si no hay, la genérica."""
    propia = (Receta.query
              .filter_by(producto_id=producto_id, cliente_id=cliente_id, activa=True)
              .first())
    if propia:
        return propia
    return (Receta.query
            .filter(Receta.producto_id == producto_id,
                    Receta.cliente_id.is_(None),
                    Receta.activa.is_(True))
            .first())


def validar_receta_unica(producto_id, cliente_id, receta_id=None):
    query = Receta.query.filter(Receta.producto_id == producto_id,
                                Receta.activa.is_(True))
    if cliente_id is None:
        query = query.filter(Receta.cliente_id.is_(None))
    else:
        query = query.filter(Receta.cliente_id == cliente_id)
    if receta_id is not None:
        query = query.filter(Receta.id != receta_id)
    if query.first():
        raise RecetaDuplicada(
            'Ya hay una receta activa para ese producto y ese cliente')


def consumo_teorico(receta, kg_producidos):
    """Cuánto debería consumirse de cada ingrediente para producir esos kilos."""
    kg_producidos = _dec(kg_producidos)
    base = _dec(receta.base_kg)
    if base <= CERO:
        raise ValueError('La base de la receta debe ser positiva')
    factor = kg_producidos / base
    return {item.ingrediente_id: (_dec(item.cantidad) * factor).quantize(Decimal('0.001'))
            for item in receta.ingredientes}
```

- [ ] **Step 4: Correr los tests**

Run: `.venv/bin/python -m pytest tests/test_maquila_receta.py -q`
Expected: PASS, 5 tests.

- [ ] **Step 5: Commit**

```bash
git add maquila/servicios.py tests/test_maquila_receta.py
git commit -m "feat(maquila): la receta que aplica y el consumo que propone"
```

---

### Task 6: Corrida de producción — apertura, cajas y cierre

**Files:**
- Modify: `maquila/servicios.py`
- Test: `tests/test_maquila_corrida.py`

**Interfaces:**
- Consumes: `repartir_fifo`, `registrar_movimiento`, `consumo_teorico`, `receta_activa`, `siguiente_codigo`.
- Produces:
  - `abrir_corrida(*, cliente_id, producto_id, lote, fecha_produccion, vendedor_id, fecha_vencimiento=None, receta_id=None, notas=None) -> CorridaProduccion` (hace commit)
  - `agregar_caja_producida(corrida, peso) -> CorridaCaja` (no hace commit)
  - `cerrar_corrida(corrida, consumos_reales, vendedor_id, reparto_manual=None) -> CorridaProduccion` — `consumos_reales` es `{ingrediente_id: Decimal}`; `reparto_manual` es `{ingrediente_id: [(recepcion_linea_id, Decimal), ...]}`. Hace commit.
  - `anular_corrida(corrida, vendedor_id, motivo)` — devuelve los ingredientes al saldo y libera las cajas. Lanza `CorridaFacturada` si alguna caja salió en un pedido ya facturado.
  - `class CorridaInvalida(ValueError)`, `class CorridaFacturada(Exception)`
  - `merma_de_corrida(corrida) -> Decimal`

- [ ] **Step 1: Escribir los tests que fallan**

Crear `tests/test_maquila_corrida.py`:

```python
"""La corrida: se pesan las cajas, se declara el consumo y se cierra."""
import os
from datetime import date
from decimal import Decimal

import pytest

os.environ.setdefault('SECRET_KEY', 'test-secret')
os.environ.setdefault('FLASK_ENV', 'testing')
os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')

from app import app as flask_app, db as _db

IDS = {}


def _recibir(codigo, dia, kg, ingrediente_id=None):
    from maquila import servicios
    return servicios.crear_recepcion(
        cliente_id=IDS['cliente'], recibido_en=date(2026, 9, dia),
        vendedor_id=IDS['vendedor'],
        lineas=[{'ingrediente_id': ingrediente_id or IDS['ingrediente'],
                 'peso_total': Decimal(str(kg))}])


@pytest.fixture
def app():
    flask_app.config.update(TESTING=True, WTF_CSRF_ENABLED=False,
                            SQLALCHEMY_DATABASE_URI='sqlite:///:memory:')
    with flask_app.app_context():
        _db.create_all()
        from app import Rol, Territorio, Vendedor, Cliente, Producto
        from maquila.models import Ingrediente
        ra = Rol(nombre='super_admin', descripcion='Admin')
        terr = Territorio(nombre='t1', descripcion='T1')
        _db.session.add_all([ra, terr])
        _db.session.flush()
        v = Vendedor(username='admin', email='a@t.com', nombre_completo='Admin',
                     rol_id=ra.id, territorio_id=terr.id, activo=True)
        v.set_password('pw')
        cli = Cliente(nombre='Maquila SA')
        prod = Producto(nombre='Chorizo', se_pesa=True, tax_rate=10)
        ing = Ingrediente(nombre='Carne de res')
        _db.session.add_all([v, cli, prod, ing])
        _db.session.commit()
        IDS.update(vendedor=v.id, cliente=cli.id, producto=prod.id,
                   ingrediente=ing.id)
        yield flask_app
        _db.drop_all()


def _corrida_con_cajas(pesos):
    from maquila import servicios
    c = servicios.abrir_corrida(
        cliente_id=IDS['cliente'], producto_id=IDS['producto'], lote='L-0903',
        fecha_produccion=date(2026, 9, 3), vendedor_id=IDS['vendedor'])
    for p in pesos:
        servicios.agregar_caja_producida(c, Decimal(str(p)))
    _db.session.commit()
    return c


def test_el_peso_producido_es_la_suma_de_las_cajas(app):
    with app.app_context():
        c = _corrida_con_cajas([10, 10.5, 9.5])
        assert c.peso_producido == Decimal('30.000')


def test_dos_corridas_del_mismo_cliente_no_repiten_lote(app):
    from maquila import servicios
    with app.app_context():
        _corrida_con_cajas([10])
        with pytest.raises(servicios.CorridaInvalida):
            servicios.abrir_corrida(
                cliente_id=IDS['cliente'], producto_id=IDS['producto'],
                lote='L-0903', fecha_produccion=date(2026, 9, 4),
                vendedor_id=IDS['vendedor'])


def test_cerrar_descuenta_del_saldo_por_fifo(app):
    from maquila import servicios
    from maquila.models import CorridaConsumoOrigen
    with app.app_context():
        r1 = _recibir('R1', 1, 30)
        r2 = _recibir('R2', 5, 100)
        c = _corrida_con_cajas([40])
        servicios.cerrar_corrida(c, {IDS['ingrediente']: Decimal('50')},
                                 IDS['vendedor'])
        assert c.estado == 'cerrada'
        assert servicios.saldo_cliente_ingrediente(
            IDS['cliente'], IDS['ingrediente']) == Decimal('80')
        origenes = CorridaConsumoOrigen.query.order_by(
            CorridaConsumoOrigen.id).all()
        assert len(origenes) == 2
        assert origenes[0].recepcion_linea_id == r1.lineas[0].id
        assert origenes[0].cantidad == Decimal('30.000')
        assert origenes[1].recepcion_linea_id == r2.lineas[0].id
        assert origenes[1].cantidad == Decimal('20.000')


def test_cerrar_sin_saldo_suficiente_no_escribe_nada(app):
    from maquila import servicios
    from maquila.models import MovimientoIngrediente, CorridaConsumo
    with app.app_context():
        _recibir('R1', 1, 20)
        c = _corrida_con_cajas([40])
        antes = MovimientoIngrediente.query.count()
        with pytest.raises(servicios.SaldoInsuficiente):
            servicios.cerrar_corrida(c, {IDS['ingrediente']: Decimal('50')},
                                     IDS['vendedor'])
        _db.session.rollback()
        assert MovimientoIngrediente.query.count() == antes
        assert CorridaConsumo.query.count() == 0
        assert _db.session.get(type(c), c.id).estado == 'abierta'


def test_cerrar_guarda_el_teorico_como_snapshot(app):
    from maquila import servicios
    from maquila.models import Receta, RecetaIngrediente, CorridaConsumo
    with app.app_context():
        _recibir('R1', 1, 200)
        rec = Receta(producto_id=IDS['producto'], cliente_id=IDS['cliente'],
                     nombre='R', base_kg=Decimal('100'), activa=True)
        _db.session.add(rec)
        _db.session.flush()
        _db.session.add(RecetaIngrediente(receta_id=rec.id,
                                          ingrediente_id=IDS['ingrediente'],
                                          cantidad=Decimal('120')))
        _db.session.commit()
        c = servicios.abrir_corrida(
            cliente_id=IDS['cliente'], producto_id=IDS['producto'], lote='L-1',
            fecha_produccion=date(2026, 9, 3), vendedor_id=IDS['vendedor'],
            receta_id=rec.id)
        servicios.agregar_caja_producida(c, Decimal('50'))
        _db.session.commit()
        servicios.cerrar_corrida(c, {IDS['ingrediente']: Decimal('55')},
                                 IDS['vendedor'])
        consumo = CorridaConsumo.query.one()
        assert consumo.cantidad_teorica == Decimal('60.000')  # 120 * 50/100
        assert consumo.cantidad_real == Decimal('55.000')


def test_la_merma_es_consumido_menos_producido(app):
    from maquila import servicios
    with app.app_context():
        _recibir('R1', 1, 200)
        c = _corrida_con_cajas([40])
        servicios.cerrar_corrida(c, {IDS['ingrediente']: Decimal('50')},
                                 IDS['vendedor'])
        assert servicios.merma_de_corrida(c) == Decimal('10.000')


def test_una_corrida_cerrada_no_se_puede_cerrar_dos_veces(app):
    from maquila import servicios
    with app.app_context():
        _recibir('R1', 1, 200)
        c = _corrida_con_cajas([40])
        servicios.cerrar_corrida(c, {IDS['ingrediente']: Decimal('50')},
                                 IDS['vendedor'])
        with pytest.raises(servicios.CorridaInvalida):
            servicios.cerrar_corrida(c, {IDS['ingrediente']: Decimal('10')},
                                     IDS['vendedor'])


def test_cerrar_sin_cajas_producidas_se_rechaza(app):
    from maquila import servicios
    with app.app_context():
        _recibir('R1', 1, 200)
        c = servicios.abrir_corrida(
            cliente_id=IDS['cliente'], producto_id=IDS['producto'], lote='L-9',
            fecha_produccion=date(2026, 9, 3), vendedor_id=IDS['vendedor'])
        with pytest.raises(servicios.CorridaInvalida):
            servicios.cerrar_corrida(c, {IDS['ingrediente']: Decimal('10')},
                                     IDS['vendedor'])


def test_anular_una_corrida_devuelve_el_ingrediente_al_saldo(app):
    from maquila import servicios
    with app.app_context():
        _recibir('R1', 1, 200)
        c = _corrida_con_cajas([40])
        servicios.cerrar_corrida(c, {IDS['ingrediente']: Decimal('50')},
                                 IDS['vendedor'])
        servicios.anular_corrida(c, IDS['vendedor'], 'Se contaminó el lote')
        _db.session.commit()
        assert c.estado == 'anulada'
        assert servicios.saldo_cliente_ingrediente(
            IDS['cliente'], IDS['ingrediente']) == Decimal('200')
```

- [ ] **Step 2: Correr y ver que falla**

Run: `.venv/bin/python -m pytest tests/test_maquila_corrida.py -q`
Expected: FAIL — `has no attribute 'abrir_corrida'`.

- [ ] **Step 3: Implementar**

Añadir a `maquila/servicios.py` (ampliar el import de modelos con
`CorridaProduccion`, `CorridaCaja`, `CorridaConsumo`, `CorridaConsumoOrigen`):

```python
class CorridaInvalida(ValueError):
    """La corrida no está en condiciones de hacer lo que se le pide."""


class CorridaFacturada(Exception):
    """Alguna caja de la corrida ya salió en un pedido facturado.

    A esa altura la cifra ya está en QuickBooks: deshacerla en la app dejaría
    los dos sistemas contando cosas distintas.
    """


def abrir_corrida(*, cliente_id, producto_id, lote, fecha_produccion, vendedor_id,
                  fecha_vencimiento=None, receta_id=None, notas=None):
    lote = (lote or '').strip()
    if not lote:
        raise CorridaInvalida('La corrida necesita un lote')

    repetido = CorridaProduccion.query.filter_by(
        cliente_id=cliente_id, lote=lote).first()
    if repetido:
        raise CorridaInvalida(
            f'El cliente ya tiene la corrida {repetido.codigo} con el lote {lote}')

    if receta_id is None:
        sugerida = receta_activa(producto_id, cliente_id)
        receta_id = sugerida.id if sugerida else None

    corrida = CorridaProduccion(
        codigo=siguiente_codigo('P', fecha_produccion.year),
        cliente_id=cliente_id,
        producto_id=producto_id,
        receta_id=receta_id,
        lote=lote,
        fecha_produccion=fecha_produccion,
        fecha_vencimiento=fecha_vencimiento,
        estado='abierta',
        notas=(notas or None),
        registrado_por=vendedor_id,
    )
    db.session.add(corrida)
    db.session.commit()
    return corrida


def agregar_caja_producida(corrida, peso):
    """Añade una caja pesada a la corrida. No hace commit."""
    if corrida.estado != 'abierta':
        raise CorridaInvalida('Solo se pueden añadir cajas a una corrida abierta')
    peso = _dec(peso)
    if peso <= CERO:
        raise CorridaInvalida('El peso de la caja debe ser positivo')

    numeros = [c.numero for c in corrida.cajas]
    caja = CorridaCaja(corrida_id=corrida.id,
                       numero=(max(numeros) + 1 if numeros else 1),
                       peso=peso)
    db.session.add(caja)
    return caja


def cerrar_corrida(corrida, consumos_reales, vendedor_id, reparto_manual=None):
    """Cierra la corrida: snapshot del teórico, reparto FIFO y salidas del ledger.

    Todo en una transacción. Si un ingrediente no tiene saldo, no se escribe
    nada: `SaldoInsuficiente` sube y quien llama hace rollback.
    """
    if corrida.estado != 'abierta':
        raise CorridaInvalida(f'La corrida {corrida.codigo} no está abierta')
    if not corrida.cajas:
        raise CorridaInvalida('No se puede cerrar una corrida sin cajas producidas')
    if not consumos_reales:
        raise CorridaInvalida('Hay que declarar el consumo de al menos un ingrediente')

    producido = corrida.peso_producido
    teoricos = {}
    if corrida.receta:
        teoricos = consumo_teorico(corrida.receta, producido)

    reparto_manual = reparto_manual or {}

    for ingrediente_id, cantidad in consumos_reales.items():
        cantidad = _dec(cantidad)
        if cantidad <= CERO:
            continue

        if ingrediente_id in reparto_manual:
            tramos = [(linea_id, _dec(c)) for linea_id, c in reparto_manual[ingrediente_id]]
            suma = sum((c for _, c in tramos), CERO)
            if suma != cantidad:
                raise CorridaInvalida(
                    f'El reparto manual del ingrediente {ingrediente_id} suma {suma} '
                    f'y el consumo declarado es {cantidad}')
            automatico = False
        else:
            tramos = repartir_fifo(corrida.cliente_id, ingrediente_id, cantidad)
            automatico = True

        consumo = CorridaConsumo(
            corrida_id=corrida.id,
            ingrediente_id=ingrediente_id,
            cantidad_teorica=teoricos.get(ingrediente_id, CERO),
            cantidad_real=cantidad,
        )
        db.session.add(consumo)
        db.session.flush()

        for linea_id, tramo in tramos:
            db.session.add(CorridaConsumoOrigen(
                corrida_consumo_id=consumo.id,
                recepcion_linea_id=linea_id,
                cantidad=tramo,
                automatico=automatico,
            ))
            registrar_movimiento(
                cliente_id=corrida.cliente_id,
                ingrediente_id=ingrediente_id,
                tipo='salida',
                cantidad=tramo,
                origen_tipo='corrida',
                origen_id=corrida.id,
                vendedor_id=vendedor_id,
                recepcion_linea_id=linea_id,
            )

    corrida.estado = 'cerrada'
    corrida.cerrada_por = vendedor_id
    corrida.cerrada_en = datetime.utcnow()
    db.session.commit()
    return corrida


def merma_de_corrida(corrida):
    """Kilos consumidos menos kilos producidos. Se deriva, no se guarda."""
    consumido = sum((_dec(c.cantidad_real) for c in corrida.consumos), CERO)
    return consumido - corrida.peso_producido


def anular_corrida(corrida, vendedor_id, motivo):
    """Devuelve los ingredientes al saldo y libera las cajas no entregadas."""
    if not (motivo or '').strip():
        raise MotivoRequerido('Anular una corrida exige un motivo')
    if corrida.estado == 'anulada':
        raise CorridaInvalida('La corrida ya estaba anulada')

    for caja in corrida.cajas:
        if caja.caja_pesada_id is None:
            continue
        pedido = getattr(getattr(caja.caja_pesada, 'detalle_pedido', None), 'pedido', None)
        if pedido is not None and pedido.estado == 'facturado':
            raise CorridaFacturada(
                f'La caja {caja.numero} de {corrida.codigo} salió en el pedido '
                f'{pedido.id}, que ya está facturado')

    for consumo in corrida.consumos:
        for origen in consumo.origenes:
            registrar_movimiento(
                cliente_id=corrida.cliente_id,
                ingrediente_id=consumo.ingrediente_id,
                tipo='ajuste',
                cantidad=_dec(origen.cantidad),
                origen_tipo='corrida',
                origen_id=corrida.id,
                vendedor_id=vendedor_id,
                recepcion_linea_id=origen.recepcion_linea_id,
                motivo=f'Anulación de {corrida.codigo}: {motivo.strip()}',
            )

    for caja in corrida.cajas:
        if caja.anulada_en is None:
            caja.anulada_en = datetime.utcnow()
            caja.motivo_anulacion = motivo.strip()

    corrida.estado = 'anulada'
    corrida.notas = ((corrida.notas or '') +
                     f'\nAnulada: {motivo.strip()}').strip()
    return corrida
```

- [ ] **Step 4: Correr los tests**

Run: `.venv/bin/python -m pytest tests/test_maquila_corrida.py -q`
Expected: PASS, 9 tests.

- [ ] **Step 5: Commit**

```bash
git add maquila/servicios.py tests/test_maquila_corrida.py
git commit -m "feat(maquila): corridas que consumen de verdad y no dejan el saldo en rojo"
```

---

### Task 7: FEFO — asignar cajas producidas a un pedido

**Files:**
- Modify: `maquila/servicios.py`
- Test: `tests/test_maquila_fefo.py`

**Interfaces:**
- Consumes: `CorridaCaja`, `CorridaProduccion`; `CajaPesada` y `DetallePedido` de `app`.
- Produces:
  - `cajas_disponibles(cliente_id, producto_id) -> list[CorridaCaja]` — orden FEFO: vencimiento más próximo primero, luego fecha de producción, luego id.
  - `proponer_fefo(detalle) -> list[CorridaCaja]` — hasta `detalle.cajas_objetivo` menos las ya pesadas.
  - `asignar_cajas(detalle, corrida_cajas, vendedor_id) -> list[CajaPesada]` — crea las `CajaPesada` copiando peso, lote y fechas. Hace commit. Lanza `CajaNoDisponible` si alguna ya está tomada.
  - `class CajaNoDisponible(Exception)`

- [ ] **Step 1: Escribir los tests que fallan**

Crear `tests/test_maquila_fefo.py`:

```python
"""FEFO: sale primero lo que vence antes, y el peso viaja con su lote."""
import os
from datetime import date
from decimal import Decimal

import pytest

os.environ.setdefault('SECRET_KEY', 'test-secret')
os.environ.setdefault('FLASK_ENV', 'testing')
os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')

from app import app as flask_app, db as _db

IDS = {}


def _corrida(lote, vence_dia, pesos):
    from maquila import servicios
    c = servicios.abrir_corrida(
        cliente_id=IDS['cliente'], producto_id=IDS['producto'], lote=lote,
        fecha_produccion=date(2026, 9, 1), vendedor_id=IDS['vendedor'],
        fecha_vencimiento=date(2026, 12, vence_dia))
    for p in pesos:
        servicios.agregar_caja_producida(c, Decimal(str(p)))
    _db.session.commit()
    return c


def _pedido_con_linea(cajas_pedidas):
    from app import Pedido, DetallePedido
    p = Pedido(cliente_id=IDS['cliente'], estado='pendiente')
    _db.session.add(p)
    _db.session.flush()
    d = DetallePedido(pedido_id=p.id, producto_id=IDS['producto'],
                      cajas=cajas_pedidas, cajas_pedidas=cajas_pedidas,
                      peso=0, precio_unitario=0, subtotal=0,
                      es_linea_pedido=True)
    _db.session.add(d)
    _db.session.commit()
    return p, d


@pytest.fixture
def app():
    flask_app.config.update(TESTING=True, WTF_CSRF_ENABLED=False,
                            SQLALCHEMY_DATABASE_URI='sqlite:///:memory:')
    with flask_app.app_context():
        _db.create_all()
        from app import Rol, Territorio, Vendedor, Cliente, Producto
        ra = Rol(nombre='super_admin', descripcion='Admin')
        terr = Territorio(nombre='t1', descripcion='T1')
        _db.session.add_all([ra, terr])
        _db.session.flush()
        v = Vendedor(username='admin', email='a@t.com', nombre_completo='Admin',
                     rol_id=ra.id, territorio_id=terr.id, activo=True)
        v.set_password('pw')
        cli = Cliente(nombre='Maquila SA')
        prod = Producto(nombre='Chorizo', se_pesa=True, tax_rate=10)
        _db.session.add_all([v, cli, prod])
        _db.session.commit()
        IDS.update(vendedor=v.id, cliente=cli.id, producto=prod.id)
        yield flask_app
        _db.drop_all()


def test_ofrece_primero_la_caja_que_vence_antes(app):
    from maquila import servicios
    with app.app_context():
        tarde = _corrida('L-TARDE', 31, [10])
        pronto = _corrida('L-PRONTO', 5, [10])
        disponibles = servicios.cajas_disponibles(IDS['cliente'], IDS['producto'])
        assert [c.corrida_id for c in disponibles] == [pronto.id, tarde.id]


def test_propone_solo_las_cajas_que_faltan(app):
    from maquila import servicios
    with app.app_context():
        _corrida('L-1', 5, [10, 10, 10, 10])
        _pedido, detalle = _pedido_con_linea(2)
        propuesta = servicios.proponer_fefo(detalle)
        assert len(propuesta) == 2


def test_asignar_copia_peso_lote_y_fechas_a_la_caja_pesada(app):
    from maquila import servicios
    with app.app_context():
        c = _corrida('L-0903', 20, [12.345])
        _pedido, detalle = _pedido_con_linea(1)
        creadas = servicios.asignar_cajas(detalle, [c.cajas[0]], IDS['vendedor'])
        assert len(creadas) == 1
        cp = creadas[0]
        assert cp.peso == Decimal('12.345')
        assert cp.lote == 'L-0903'
        assert cp.fecha_elaboracion == date(2026, 9, 1)
        assert cp.fecha_vencimiento == date(2026, 12, 20)
        assert c.cajas[0].caja_pesada_id == cp.id
        assert c.cajas[0].disponible is False


def test_una_caja_asignada_ya_no_se_ofrece(app):
    from maquila import servicios
    with app.app_context():
        c = _corrida('L-1', 5, [10, 10])
        _pedido, detalle = _pedido_con_linea(1)
        servicios.asignar_cajas(detalle, [c.cajas[0]], IDS['vendedor'])
        disponibles = servicios.cajas_disponibles(IDS['cliente'], IDS['producto'])
        assert len(disponibles) == 1
        assert disponibles[0].numero == 2


def test_no_se_puede_asignar_la_misma_caja_dos_veces(app):
    from maquila import servicios
    with app.app_context():
        c = _corrida('L-1', 5, [10])
        _p1, d1 = _pedido_con_linea(1)
        _p2, d2 = _pedido_con_linea(1)
        servicios.asignar_cajas(d1, [c.cajas[0]], IDS['vendedor'])
        with pytest.raises(servicios.CajaNoDisponible):
            servicios.asignar_cajas(d2, [c.cajas[0]], IDS['vendedor'])


def test_borrar_la_linea_del_pedido_devuelve_la_caja_al_stock(app):
    """ON DELETE SET NULL: nadie tiene que acordarse de liberar la caja."""
    from maquila import servicios
    from maquila.models import CorridaCaja
    with app.app_context():
        c = _corrida('L-1', 5, [10])
        _pedido, detalle = _pedido_con_linea(1)
        servicios.asignar_cajas(detalle, [c.cajas[0]], IDS['vendedor'])
        caja_id = c.cajas[0].id
        _db.session.delete(detalle)
        _db.session.commit()
        assert _db.session.get(CorridaCaja, caja_id).caja_pesada_id is None
        assert len(servicios.cajas_disponibles(IDS['cliente'], IDS['producto'])) == 1
```

- [ ] **Step 2: Correr y ver que falla**

Run: `.venv/bin/python -m pytest tests/test_maquila_fefo.py -q`
Expected: FAIL — `has no attribute 'cajas_disponibles'`.

**Nota para quien implementa:** SQLite no aplica claves foráneas por defecto, así
que `ON DELETE SET NULL` puede no dispararse en los tests. Si
`test_borrar_la_linea_del_pedido_devuelve_la_caja_al_stock` falla por eso, activar
el pragma en `maquila/models.py` con un listener de conexión:

```python
from sqlalchemy import event
from sqlalchemy.engine import Engine


@event.listens_for(Engine, 'connect')
def _activar_foreign_keys_sqlite(dbapi_connection, connection_record):
    """SQLite ignora las FK salvo que se le pida. En Postgres es un no-op."""
    if dbapi_connection.__class__.__module__.startswith('sqlite3'):
        cursor = dbapi_connection.cursor()
        cursor.execute('PRAGMA foreign_keys=ON')
        cursor.close()
```

- [ ] **Step 3: Implementar**

Añadir a `maquila/servicios.py`:

```python
# Las corridas sin vencimiento van al final del orden FEFO. Se usa un coalesce en
# vez de NULLS LAST porque ese modificador no es portable entre SQLite y Postgres
# y cambió de nombre entre versiones de SQLAlchemy.
_SIN_VENCIMIENTO = _date(9999, 12, 31)


class CajaNoDisponible(Exception):
    """La caja producida ya salió en otro pedido o está anulada."""


def cajas_disponibles(cliente_id, producto_id):
    """Cajas producidas del cliente para ese producto, en orden FEFO.

    Vencimiento más próximo primero; a igualdad, la corrida más antigua. Las
    corridas anuladas no cuentan.
    """
    return (CorridaCaja.query
            .join(CorridaProduccion, CorridaProduccion.id == CorridaCaja.corrida_id)
            .filter(CorridaProduccion.cliente_id == cliente_id,
                    CorridaProduccion.producto_id == producto_id,
                    CorridaProduccion.estado != 'anulada',
                    CorridaCaja.caja_pesada_id.is_(None),
                    CorridaCaja.anulada_en.is_(None))
            .order_by(func.coalesce(CorridaProduccion.fecha_vencimiento,
                                    _SIN_VENCIMIENTO).asc(),
                      CorridaProduccion.fecha_produccion.asc(),
                      CorridaCaja.numero.asc())
            .all())


def proponer_fefo(detalle):
    """Las cajas que la app sugiere para esta línea de pedido.

    Solo las que faltan: si ya se pesaron tres a mano y el objetivo son cinco,
    propone dos.
    """
    faltan = detalle.cajas_objetivo - detalle.cajas_pesadas_count
    if faltan <= 0:
        return []
    disponibles = cajas_disponibles(detalle.pedido.cliente_id, detalle.producto_id)
    return disponibles[:faltan]


def asignar_cajas(detalle, corrida_cajas, vendedor_id):
    """Convierte cajas producidas en CajaPesada del pedido.

    Copia peso, lote y fechas desde la corrida: el pesador no re-teclea nada y
    el lote deja de depender de que alguien lo escriba bien.
    """
    from app import CajaPesada

    if not corrida_cajas:
        return []

    numeros = [c.numero for c in (detalle.cajas_pesadas or [])]
    siguiente = (max(numeros) + 1) if numeros else 1

    creadas = []
    for caja in corrida_cajas:
        if not caja.disponible:
            raise CajaNoDisponible(
                f'La caja {caja.numero} de {caja.corrida.codigo} ya no está disponible')

        pesada = CajaPesada(
            detalle_pedido_id=detalle.id,
            numero=siguiente,
            peso=caja.peso,
            lote=caja.corrida.lote,
            fecha_elaboracion=caja.corrida.fecha_produccion,
            fecha_vencimiento=(caja.corrida.fecha_vencimiento
                               or caja.corrida.fecha_produccion),
            pesado_por=vendedor_id,
        )
        db.session.add(pesada)
        db.session.flush()

        caja.caja_pesada_id = pesada.id
        creadas.append(pesada)
        siguiente += 1

    db.session.commit()
    return creadas
```

- [ ] **Step 4: Correr los tests**

Run: `.venv/bin/python -m pytest tests/test_maquila_fefo.py -q`
Expected: PASS, 6 tests.

- [ ] **Step 5: Correr la suite completa**

Run: `.venv/bin/python -m pytest tests/ -q`
Expected: sin regresiones respecto al baseline. Si `test_pesar.py` o
`test_cajas_fraccionarias.py` fallan, es que el listener del pragma cambió el
comportamiento de algún borrado en cascada existente — investigar antes de seguir.

- [ ] **Step 6: Commit**

```bash
git add maquila/servicios.py maquila/models.py tests/test_maquila_fefo.py
git commit -m "feat(maquila): el peso de producción viaja al pedido con su lote y sus fechas"
```

---

### Task 8: Los cuatro reportes de auditoría

**Files:**
- Create: `maquila/reportes.py`
- Test: `tests/test_maquila_reportes.py`

**Interfaces:**
- Consumes: todos los modelos y `servicios.saldos_de_cliente`.
- Produces:
  - `saldos(cliente_id) -> list[dict]` — igual que `saldos_de_cliente`, más `lineas_abiertas`: `[{'codigo','recibido_en','lote_cliente','saldo'}]`.
  - `kardex(cliente_id, ingrediente_id=None, desde=None, hasta=None) -> list[dict]` con `fecha`, `tipo`, `ingrediente`, `cantidad`, `saldo_acumulado`, `origen`, `responsable`, `motivo`.
  - `rendimiento(cliente_id=None, desde=None, hasta=None) -> list[dict]` con `corrida`, `lote`, `producto`, `consumido`, `producido`, `merma`, `merma_pct`, `varianzas`.
  - `trazar(termino) -> dict` con `encontrado` (bool), `tipo`, `hacia_atras`, `hacia_adelante`.

- [ ] **Step 1: Escribir los tests que fallan**

Crear `tests/test_maquila_reportes.py`:

```python
"""Los reportes de auditoría: saldo, kardex, rendimiento y trazabilidad."""
import os
from datetime import date
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
        from app import Rol, Territorio, Vendedor, Cliente, Producto
        from maquila.models import Ingrediente
        ra = Rol(nombre='super_admin', descripcion='Admin')
        terr = Territorio(nombre='t1', descripcion='T1')
        _db.session.add_all([ra, terr])
        _db.session.flush()
        v = Vendedor(username='admin', email='a@t.com', nombre_completo='Admin',
                     rol_id=ra.id, territorio_id=terr.id, activo=True)
        v.set_password('pw')
        cli = Cliente(nombre='Maquila SA')
        prod = Producto(nombre='Chorizo', se_pesa=True, tax_rate=10)
        ing = Ingrediente(nombre='Carne de res')
        _db.session.add_all([v, cli, prod, ing])
        _db.session.commit()
        IDS.update(vendedor=v.id, cliente=cli.id, producto=prod.id,
                   ingrediente=ing.id)
        yield flask_app
        _db.drop_all()


def _cadena_completa():
    """Recepción → corrida → caja → pedido facturado. Devuelve las piezas."""
    from maquila import servicios
    from app import Pedido, DetallePedido
    rec = servicios.crear_recepcion(
        cliente_id=IDS['cliente'], recibido_en=date(2026, 9, 1),
        vendedor_id=IDS['vendedor'], documento_cliente='GUIA-77',
        lineas=[{'ingrediente_id': IDS['ingrediente'],
                 'peso_total': Decimal('200')}])
    corrida = servicios.abrir_corrida(
        cliente_id=IDS['cliente'], producto_id=IDS['producto'], lote='L-0903',
        fecha_produccion=date(2026, 9, 3), vendedor_id=IDS['vendedor'],
        fecha_vencimiento=date(2026, 12, 3))
    servicios.agregar_caja_producida(corrida, Decimal('40'))
    _db.session.commit()
    servicios.cerrar_corrida(corrida, {IDS['ingrediente']: Decimal('50')},
                             IDS['vendedor'])
    pedido = Pedido(cliente_id=IDS['cliente'], estado='facturado',
                    doc_number_qbo='1234')
    _db.session.add(pedido)
    _db.session.flush()
    detalle = DetallePedido(pedido_id=pedido.id, producto_id=IDS['producto'],
                            cajas=1, cajas_pedidas=1, peso=0,
                            precio_unitario=0, subtotal=0, es_linea_pedido=True)
    _db.session.add(detalle)
    _db.session.commit()
    servicios.asignar_cajas(detalle, [corrida.cajas[0]], IDS['vendedor'])
    return rec, corrida, pedido


def test_saldos_lista_las_lineas_todavia_abiertas(app):
    from maquila import reportes
    with app.app_context():
        _cadena_completa()
        filas = reportes.saldos(IDS['cliente'])
        assert len(filas) == 1
        assert filas[0]['saldo'] == Decimal('150')
        abiertas = filas[0]['lineas_abiertas']
        assert len(abiertas) == 1
        assert abiertas[0]['codigo'] == 'R-2026-0001'
        assert abiertas[0]['saldo'] == Decimal('150')


def test_el_kardex_acumula_el_saldo_en_orden(app):
    from maquila import reportes
    with app.app_context():
        _cadena_completa()
        filas = reportes.kardex(IDS['cliente'])
        assert [f['tipo'] for f in filas] == ['entrada', 'salida']
        assert filas[0]['saldo_acumulado'] == Decimal('200')
        assert filas[1]['saldo_acumulado'] == Decimal('150')
        assert filas[0]['responsable'] == 'Admin'


def test_el_rendimiento_calcula_merma_y_porcentaje(app):
    from maquila import reportes
    with app.app_context():
        _cadena_completa()
        filas = reportes.rendimiento(IDS['cliente'])
        assert len(filas) == 1
        fila = filas[0]
        assert fila['consumido'] == Decimal('50.000')
        assert fila['producido'] == Decimal('40.000')
        assert fila['merma'] == Decimal('10.000')
        assert fila['merma_pct'] == Decimal('20.0')


def test_trazar_un_lote_llega_hasta_la_factura(app):
    from maquila import reportes
    with app.app_context():
        rec, corrida, pedido = _cadena_completa()
        r = reportes.trazar('L-0903')
        assert r['encontrado'] is True
        assert r['tipo'] == 'corrida'
        assert rec.codigo in [x['codigo'] for x in r['hacia_atras']]
        adelante = r['hacia_adelante']
        assert adelante[0]['pedido_id'] == pedido.id
        assert adelante[0]['doc_number_qbo'] == '1234'


def test_trazar_por_codigo_de_recepcion_avanza_hasta_el_pedido(app):
    from maquila import reportes
    with app.app_context():
        _rec, _corrida, pedido = _cadena_completa()
        r = reportes.trazar('R-2026-0001')
        assert r['encontrado'] is True
        assert r['tipo'] == 'recepcion'
        assert r['hacia_adelante'][0]['pedido_id'] == pedido.id


def test_trazar_algo_que_no_existe_no_revienta(app):
    from maquila import reportes
    with app.app_context():
        r = reportes.trazar('NO-EXISTE')
        assert r['encontrado'] is False
        assert r['hacia_atras'] == []
        assert r['hacia_adelante'] == []


def test_una_caja_pesada_a_mano_se_marca_sin_origen(app):
    from maquila import reportes
    from app import Pedido, DetallePedido, CajaPesada
    with app.app_context():
        _cadena_completa()
        pedido = Pedido(cliente_id=IDS['cliente'], estado='pendiente')
        _db.session.add(pedido)
        _db.session.flush()
        detalle = DetallePedido(pedido_id=pedido.id, producto_id=IDS['producto'],
                                cajas=1, cajas_pedidas=1, peso=0,
                                precio_unitario=0, subtotal=0,
                                es_linea_pedido=True)
        _db.session.add(detalle)
        _db.session.flush()
        _db.session.add(CajaPesada(detalle_pedido_id=detalle.id, numero=1,
                                   peso=Decimal('9'), lote='A-MANO',
                                   fecha_elaboracion=date(2026, 9, 3),
                                   fecha_vencimiento=date(2026, 12, 3)))
        _db.session.commit()
        r = reportes.trazar(str(pedido.id))
        assert r['encontrado'] is True
        assert r['hacia_atras'][0]['sin_origen'] is True
```

- [ ] **Step 2: Correr y ver que falla**

Run: `.venv/bin/python -m pytest tests/test_maquila_reportes.py -q`
Expected: FAIL — `No module named 'maquila.reportes'`.

- [ ] **Step 3: Implementar**

Crear `maquila/reportes.py`:

```python
"""Las cuatro consultas de auditoría.

Todo se deriva del ledger y de las tablas de producción: no hay ningún total
guardado que pueda mentir.
"""
from decimal import Decimal

from app import db, Pedido, DetallePedido, CajaPesada, Vendedor
from .models import (CorridaCaja, CorridaConsumo, CorridaConsumoOrigen,
                     CorridaProduccion, Ingrediente, MovimientoIngrediente,
                     RecepcionIngrediente, RecepcionLinea)
from .servicios import _dec, saldo_de_linea, saldos_de_cliente, CERO

try:
    from app import DASHBOARD_TIMEZONE
except ImportError:  # pragma: no cover
    DASHBOARD_TIMEZONE = None


def _local(dt):
    """UTC naive → hora de Curazao.

    Los movimientos se guardan en UTC naive. Mostrar `registrado_en` en crudo es
    el error que ya metió lecturas de temperatura en el bucket AM/PM equivocado:
    a las 8:00 locales le corresponden las 12:00 UTC.
    """
    if dt is None or DASHBOARD_TIMEZONE is None:
        return dt
    from datetime import timezone
    return dt.replace(tzinfo=timezone.utc).astimezone(DASHBOARD_TIMEZONE)


def saldos(cliente_id):
    """Saldo por ingrediente, con las líneas de recepción todavía abiertas."""
    filas = saldos_de_cliente(cliente_id)
    lineas = (db.session.query(RecepcionLinea, RecepcionIngrediente)
              .join(RecepcionIngrediente,
                    RecepcionIngrediente.id == RecepcionLinea.recepcion_id)
              .filter(RecepcionIngrediente.cliente_id == cliente_id,
                      RecepcionIngrediente.anulada_en.is_(None))
              .order_by(RecepcionIngrediente.recibido_en.asc())
              .all())

    abiertas = {}
    for linea, recepcion in lineas:
        saldo = saldo_de_linea(linea.id)
        if saldo <= CERO:
            continue
        abiertas.setdefault(linea.ingrediente_id, []).append({
            'codigo': recepcion.codigo,
            'recibido_en': recepcion.recibido_en,
            'lote_cliente': linea.lote_cliente,
            'saldo': saldo,
        })

    for fila in filas:
        fila['lineas_abiertas'] = abiertas.get(fila['ingrediente_id'], [])
    return filas


def kardex(cliente_id, ingrediente_id=None, desde=None, hasta=None):
    """Movimientos en orden cronológico, con el saldo acumulado."""
    query = (db.session.query(MovimientoIngrediente, Ingrediente, Vendedor)
             .join(Ingrediente, Ingrediente.id == MovimientoIngrediente.ingrediente_id)
             .outerjoin(Vendedor, Vendedor.id == MovimientoIngrediente.registrado_por)
             .filter(MovimientoIngrediente.cliente_id == cliente_id))
    if ingrediente_id:
        query = query.filter(MovimientoIngrediente.ingrediente_id == ingrediente_id)
    if desde:
        query = query.filter(MovimientoIngrediente.registrado_en >= desde)
    if hasta:
        query = query.filter(MovimientoIngrediente.registrado_en <= hasta)

    movimientos = query.order_by(MovimientoIngrediente.registrado_en.asc(),
                                 MovimientoIngrediente.id.asc()).all()

    acumulado = {}
    filas = []
    for mov, ingrediente, vendedor in movimientos:
        clave = mov.ingrediente_id
        acumulado[clave] = acumulado.get(clave, CERO) + _dec(mov.cantidad)
        filas.append({
            'id': mov.id,
            'fecha': _local(mov.registrado_en),
            'tipo': mov.tipo,
            'ingrediente_id': mov.ingrediente_id,
            'ingrediente': ingrediente.nombre,
            'cantidad': _dec(mov.cantidad),
            'saldo_acumulado': acumulado[clave],
            'origen': f'{mov.origen_tipo}:{mov.origen_id}' if mov.origen_id else mov.origen_tipo,
            'origen_tipo': mov.origen_tipo,
            'origen_id': mov.origen_id,
            'responsable': vendedor.nombre_completo if vendedor else '—',
            'motivo': mov.motivo,
        })
    return filas


def rendimiento(cliente_id=None, desde=None, hasta=None):
    """Por corrida: cuánto entró, cuánto salió, cuánta merma y qué varianza."""
    query = CorridaProduccion.query.filter(CorridaProduccion.estado == 'cerrada')
    if cliente_id:
        query = query.filter(CorridaProduccion.cliente_id == cliente_id)
    if desde:
        query = query.filter(CorridaProduccion.fecha_produccion >= desde)
    if hasta:
        query = query.filter(CorridaProduccion.fecha_produccion <= hasta)

    filas = []
    for corrida in query.order_by(CorridaProduccion.fecha_produccion.desc()).all():
        consumido = sum((_dec(c.cantidad_real) for c in corrida.consumos), CERO)
        producido = corrida.peso_producido
        merma = consumido - producido
        merma_pct = ((merma / consumido) * 100).quantize(Decimal('0.1')) \
            if consumido > CERO else CERO

        varianzas = []
        for consumo in corrida.consumos:
            teorica = _dec(consumo.cantidad_teorica)
            real = _dec(consumo.cantidad_real)
            varianzas.append({
                'ingrediente': consumo.ingrediente.nombre,
                'teorica': teorica,
                'real': real,
                'diferencia': real - teorica,
                'pct': (((real - teorica) / teorica) * 100).quantize(Decimal('0.1'))
                       if teorica > CERO else None,
            })

        filas.append({
            'corrida_id': corrida.id,
            'corrida': corrida.codigo,
            'lote': corrida.lote,
            'cliente': corrida.cliente.nombre if corrida.cliente else '—',
            'producto': corrida.producto.nombre if corrida.producto else '—',
            'fecha': corrida.fecha_produccion,
            'consumido': consumido,
            'producido': producido,
            'merma': merma,
            'merma_pct': merma_pct,
            'varianzas': varianzas,
        })
    return filas


def _atras_desde_corrida(corrida):
    """Las recepciones que alimentaron esta corrida."""
    origenes = (db.session.query(CorridaConsumoOrigen, RecepcionLinea,
                                 RecepcionIngrediente, Ingrediente)
                .join(CorridaConsumo,
                      CorridaConsumo.id == CorridaConsumoOrigen.corrida_consumo_id)
                .join(RecepcionLinea,
                      RecepcionLinea.id == CorridaConsumoOrigen.recepcion_linea_id)
                .join(RecepcionIngrediente,
                      RecepcionIngrediente.id == RecepcionLinea.recepcion_id)
                .join(Ingrediente, Ingrediente.id == RecepcionLinea.ingrediente_id)
                .filter(CorridaConsumo.corrida_id == corrida.id)
                .all())
    return [{
        'codigo': recepcion.codigo,
        'recibido_en': recepcion.recibido_en,
        'documento_cliente': recepcion.documento_cliente,
        'lote_cliente': linea.lote_cliente,
        'ingrediente': ingrediente.nombre,
        'cantidad': _dec(origen.cantidad),
        'automatico': origen.automatico,
        'sin_origen': False,
    } for origen, linea, recepcion, ingrediente in origenes]


def _adelante_desde_corrida(corrida):
    """Los pedidos y facturas en que salieron las cajas de esta corrida."""
    filas = (db.session.query(CorridaCaja, CajaPesada, DetallePedido, Pedido)
             .join(CajaPesada, CajaPesada.id == CorridaCaja.caja_pesada_id)
             .join(DetallePedido, DetallePedido.id == CajaPesada.detalle_pedido_id)
             .join(Pedido, Pedido.id == DetallePedido.pedido_id)
             .filter(CorridaCaja.corrida_id == corrida.id)
             .all())
    por_pedido = {}
    for caja, pesada, _detalle, pedido in filas:
        entrada = por_pedido.setdefault(pedido.id, {
            'pedido_id': pedido.id,
            'estado': pedido.estado,
            'fecha_pedido': pedido.fecha_pedido,
            'doc_number_qbo': pedido.doc_number_qbo,
            'invoice_id_qbo': pedido.invoice_id_qbo,
            'cajas': 0,
            'peso': CERO,
        })
        entrada['cajas'] += 1
        entrada['peso'] += _dec(pesada.peso)
    return list(por_pedido.values())


def trazar(termino):
    """Traza en ambos sentidos desde un lote, un código o un número de pedido.

    Acepta: lote de corrida, código de corrida (P-…), código de recepción (R-…),
    id de pedido o DocNumber de QuickBooks.
    """
    vacio = {'encontrado': False, 'tipo': None, 'termino': termino,
             'hacia_atras': [], 'hacia_adelante': [], 'corridas': []}
    termino = (termino or '').strip()
    if not termino:
        return vacio

    corrida = (CorridaProduccion.query
               .filter((CorridaProduccion.lote == termino) |
                       (CorridaProduccion.codigo == termino))
               .first())
    if corrida:
        return {'encontrado': True, 'tipo': 'corrida', 'termino': termino,
                'corridas': [corrida],
                'hacia_atras': _atras_desde_corrida(corrida),
                'hacia_adelante': _adelante_desde_corrida(corrida)}

    recepcion = RecepcionIngrediente.query.filter_by(codigo=termino).first()
    if recepcion:
        ids = [l.id for l in recepcion.lineas]
        corridas = (CorridaProduccion.query
                    .join(CorridaConsumo,
                          CorridaConsumo.corrida_id == CorridaProduccion.id)
                    .join(CorridaConsumoOrigen,
                          CorridaConsumoOrigen.corrida_consumo_id == CorridaConsumo.id)
                    .filter(CorridaConsumoOrigen.recepcion_linea_id.in_(ids))
                    .distinct().all()) if ids else []
        adelante = []
        for c in corridas:
            adelante.extend(_adelante_desde_corrida(c))
        return {'encontrado': True, 'tipo': 'recepcion', 'termino': termino,
                'corridas': corridas,
                'hacia_atras': [{
                    'codigo': recepcion.codigo,
                    'recibido_en': recepcion.recibido_en,
                    'documento_cliente': recepcion.documento_cliente,
                    'lote_cliente': l.lote_cliente,
                    'ingrediente': l.ingrediente.nombre,
                    'cantidad': _dec(l.peso_total),
                    'automatico': None,
                    'sin_origen': False,
                } for l in recepcion.lineas],
                'hacia_adelante': adelante}

    pedido = None
    if termino.isdigit():
        pedido = db.session.get(Pedido, int(termino))
    if pedido is None:
        pedido = Pedido.query.filter_by(doc_number_qbo=termino).first()
    if pedido is None:
        return vacio

    atras, corridas, vistas = [], [], set()
    for detalle in pedido.detalles:
        for pesada in (detalle.cajas_pesadas or []):
            caja = CorridaCaja.query.filter_by(caja_pesada_id=pesada.id).first()
            if caja is None:
                atras.append({
                    'codigo': '—', 'recibido_en': None, 'documento_cliente': None,
                    'lote_cliente': pesada.lote,
                    'ingrediente': detalle.producto.nombre if detalle.producto else '—',
                    'cantidad': _dec(pesada.peso), 'automatico': None,
                    'sin_origen': True,
                })
                continue
            if caja.corrida_id not in vistas:
                vistas.add(caja.corrida_id)
                corridas.append(caja.corrida)
                atras.extend(_atras_desde_corrida(caja.corrida))

    return {'encontrado': True, 'tipo': 'pedido', 'termino': termino,
            'corridas': corridas, 'hacia_atras': atras,
            'hacia_adelante': [{
                'pedido_id': pedido.id, 'estado': pedido.estado,
                'fecha_pedido': pedido.fecha_pedido,
                'doc_number_qbo': pedido.doc_number_qbo,
                'invoice_id_qbo': pedido.invoice_id_qbo,
                'cajas': sum(d.cajas_pesadas_count for d in pedido.detalles),
                'peso': sum((_dec(d.peso_real) for d in pedido.detalles), CERO),
            }]}
```

- [ ] **Step 4: Correr los tests**

Run: `.venv/bin/python -m pytest tests/test_maquila_reportes.py -q`
Expected: PASS, 7 tests.

- [ ] **Step 5: Commit**

```bash
git add maquila/reportes.py tests/test_maquila_reportes.py
git commit -m "feat(maquila): los cuatro reportes, derivados y sin totales guardados que mientan"
```

---

### Task 9: Pantallas de ingredientes y recepciones

**Files:**
- Modify: `maquila/routes.py`
- Create: `templates/maquila/ingredientes.html`, `templates/maquila/recepciones.html`, `templates/maquila/recepcion_nueva.html`, `templates/maquila/recepcion_detalle.html`, `static/css/maquila.css`
- Modify: `templates/maquila/index.html`, `templates/maquila/base_maquila.html`
- Test: `tests/test_maquila_rutas.py` (ampliar)

**Interfaces:**
- Consumes: `servicios.crear_recepcion`, `anular_recepcion`, `saldos_de_cliente`; `reportes.saldos`.
- Produces: endpoints `maquila.ingredientes`, `maquila.crear_ingrediente`, `maquila.toggle_ingrediente`, `maquila.recepciones`, `maquila.recepcion_nueva`, `maquila.recepcion_detalle`, `maquila.recepcion_anular`, `maquila.recepcion_foto`.

- [ ] **Step 1: Escribir los tests que fallan**

Añadir al final de `tests/test_maquila_rutas.py`:

```python
def test_alta_de_ingrediente(app):
    from maquila.models import Ingrediente
    c = _login(app, 'admin')
    r = c.post('/maquila/ingredientes', data={'nombre': 'Tripa natural',
                                              'unidad': 'ud'},
               follow_redirects=True)
    assert r.status_code == 200
    with app.app_context():
        assert Ingrediente.query.filter_by(nombre='Tripa natural').count() == 1


def test_alta_de_recepcion_por_la_ruta(app):
    from maquila.models import Ingrediente, RecepcionIngrediente
    with app.app_context():
        from app import Cliente
        cli = Cliente(nombre='Maquila SA')
        ing = Ingrediente(nombre='Carne de res')
        _db.session.add_all([cli, ing])
        _db.session.commit()
        cli_id, ing_id = cli.id, ing.id

    c = _login(app, 'admin')
    r = c.post('/maquila/recepciones/nueva', data={
        'cliente_id': str(cli_id),
        'recibido_en': '2026-09-03',
        'documento_cliente': '',
        'temperatura': '-18.5',
        'linea_ingrediente_id': [str(ing_id)],
        'linea_lote_cliente': [''],
        'linea_fecha_vencimiento': [''],
        'linea_peso_total': [''],
        'linea_bultos': ['12.5,11.5'],
    }, follow_redirects=True)
    assert r.status_code == 200
    with app.app_context():
        rec = RecepcionIngrediente.query.one()
        assert rec.codigo == 'R-2026-0001'
        assert rec.documento_cliente is None
        assert rec.lineas[0].peso_total == Decimal('24.000')
        assert len(rec.lineas[0].bultos) == 2


def test_el_indice_lista_los_clientes_con_recepciones(app):
    from maquila.models import Ingrediente
    from maquila import servicios
    with app.app_context():
        from app import Cliente
        cli = Cliente(nombre='Maquila SA')
        ing = Ingrediente(nombre='Carne de res')
        _db.session.add_all([cli, ing])
        _db.session.commit()
        servicios.crear_recepcion(
            cliente_id=cli.id, recibido_en=date(2026, 9, 1),
            vendedor_id=IDS['admin'],
            lineas=[{'ingrediente_id': ing.id, 'peso_total': Decimal('50')}])
    c = _login(app, 'admin')
    r = c.get('/maquila')
    assert r.status_code == 200
    assert b'Maquila SA' in r.data
```

Y añadir arriba del archivo, junto a los imports: `from datetime import date` y
`from decimal import Decimal`.

- [ ] **Step 2: Correr y ver que falla**

Run: `.venv/bin/python -m pytest tests/test_maquila_rutas.py -q`
Expected: FAIL — 404 en `/maquila/ingredientes` y `/maquila/recepciones/nueva`.

- [ ] **Step 3: Escribir las rutas**

Reemplazar `maquila/routes.py` por:

```python
"""Vistas del módulo de maquila. Solo traducen request → servicio → template."""
from datetime import datetime
from decimal import Decimal, InvalidOperation

from flask import (Blueprint, Response, abort, flash, redirect,
                   render_template, request, url_for)
from flask_login import current_user, login_required

from app import Cliente, Producto, db, requiere_rol
from . import reportes, servicios
from .models import (CorridaProduccion, Ingrediente, RecepcionIngrediente,
                     RecepcionFoto)

bp = Blueprint('maquila', __name__, url_prefix='/maquila')

MAX_FOTO_BYTES = 2 * 1024 * 1024


def _decimal(valor):
    """Convierte texto de formulario a Decimal. Vacío o basura → None."""
    if valor in (None, ''):
        return None
    try:
        return Decimal(str(valor).replace(',', '.').strip())
    except (InvalidOperation, ValueError):
        return None


def _fecha(valor):
    if not valor:
        return None
    try:
        return datetime.strptime(valor, '%Y-%m-%d').date()
    except ValueError:
        return None


def _clientes_con_maquila():
    """Cliente de maquila no es un campo: es todo cliente con recepciones."""
    return (Cliente.query
            .join(RecepcionIngrediente,
                  RecepcionIngrediente.cliente_id == Cliente.id)
            .filter(RecepcionIngrediente.anulada_en.is_(None))
            .distinct()
            .order_by(Cliente.nombre)
            .all())


@bp.route('/')
@login_required
@requiere_rol(['super_admin'])
def index():
    tarjetas = []
    for cliente in _clientes_con_maquila():
        filas = servicios.saldos_de_cliente(cliente.id)
        abiertas = (CorridaProduccion.query
                    .filter_by(cliente_id=cliente.id, estado='abierta').count())
        ultima = (RecepcionIngrediente.query
                  .filter_by(cliente_id=cliente.id)
                  .order_by(RecepcionIngrediente.recibido_en.desc()).first())
        tarjetas.append({'cliente': cliente, 'saldos': filas,
                         'corridas_abiertas': abiertas, 'ultima': ultima})
    return render_template('maquila/index.html', tarjetas=tarjetas)


@bp.route('/ingredientes', methods=['GET', 'POST'])
@login_required
@requiere_rol(['super_admin'])
def ingredientes():
    if request.method == 'POST':
        nombre = (request.form.get('nombre') or '').strip()
        if not nombre:
            flash('El ingrediente necesita un nombre', 'error')
        elif Ingrediente.query.filter_by(nombre=nombre).first():
            flash(f'Ya existe un ingrediente llamado {nombre}', 'error')
        else:
            db.session.add(Ingrediente(
                nombre=nombre,
                unidad=(request.form.get('unidad') or 'kg'),
                notas=(request.form.get('notas') or None)))
            db.session.commit()
            flash(f'Ingrediente {nombre} agregado', 'success')
        return redirect(url_for('maquila.ingredientes'))

    return render_template('maquila/ingredientes.html',
                           ingredientes=Ingrediente.query.order_by(
                               Ingrediente.nombre).all())


@bp.route('/ingredientes/<int:ingrediente_id>/toggle', methods=['POST'])
@login_required
@requiere_rol(['super_admin'])
def toggle_ingrediente(ingrediente_id):
    ing = db.session.get(Ingrediente, ingrediente_id) or abort(404)
    ing.activo = not ing.activo
    db.session.commit()
    return redirect(url_for('maquila.ingredientes'))


@bp.route('/recepciones')
@login_required
@requiere_rol(['super_admin'])
def recepciones():
    query = RecepcionIngrediente.query
    cliente_id = request.args.get('cliente_id', type=int)
    if cliente_id:
        query = query.filter_by(cliente_id=cliente_id)
    return render_template(
        'maquila/recepciones.html',
        recepciones=query.order_by(RecepcionIngrediente.recibido_en.desc(),
                                   RecepcionIngrediente.id.desc()).all(),
        clientes=Cliente.query.order_by(Cliente.nombre).all(),
        cliente_id=cliente_id)


@bp.route('/recepciones/nueva', methods=['GET', 'POST'])
@login_required
@requiere_rol(['super_admin'])
def recepcion_nueva():
    if request.method == 'POST':
        lineas = []
        ingredientes_ids = request.form.getlist('linea_ingrediente_id')
        lotes = request.form.getlist('linea_lote_cliente')
        vencimientos = request.form.getlist('linea_fecha_vencimiento')
        totales = request.form.getlist('linea_peso_total')
        bultos_crudos = request.form.getlist('linea_bultos')

        for i, ingrediente_id in enumerate(ingredientes_ids):
            if not ingrediente_id:
                continue
            crudos = (bultos_crudos[i] if i < len(bultos_crudos) else '') or ''
            bultos = [b for b in (_decimal(x) for x in crudos.split(',') if x.strip())
                      if b is not None]
            lineas.append({
                'ingrediente_id': int(ingrediente_id),
                'lote_cliente': (lotes[i] if i < len(lotes) else '') or None,
                'fecha_vencimiento': _fecha(vencimientos[i] if i < len(vencimientos) else ''),
                'bultos': bultos,
                'peso_total': _decimal(totales[i] if i < len(totales) else ''),
            })

        fotos = []
        for archivo in request.files.getlist('fotos'):
            if not archivo or not archivo.filename:
                continue
            datos = archivo.read(MAX_FOTO_BYTES + 1)
            if len(datos) > MAX_FOTO_BYTES:
                flash('Una foto supera los 2 MB: redúcela antes de subirla', 'error')
                return redirect(url_for('maquila.recepcion_nueva'))
            fotos.append((datos, archivo.mimetype or 'image/jpeg'))

        firma_b64 = request.form.get('firma_png') or ''
        firma = None
        if firma_b64.startswith('data:image/png;base64,'):
            import base64
            firma = base64.b64decode(firma_b64.split(',', 1)[1])

        try:
            recepcion = servicios.crear_recepcion(
                cliente_id=int(request.form['cliente_id']),
                recibido_en=_fecha(request.form.get('recibido_en')),
                vendedor_id=current_user.id,
                lineas=lineas,
                documento_cliente=(request.form.get('documento_cliente') or None),
                temperatura=_decimal(request.form.get('temperatura')),
                transportista=(request.form.get('transportista') or None),
                notas=(request.form.get('notas') or None),
                firma=firma,
                firma_mimetype='image/png' if firma else None,
                fotos=fotos)
        except servicios.RecepcionInvalida as exc:
            db.session.rollback()
            flash(str(exc), 'error')
            return redirect(url_for('maquila.recepcion_nueva'))

        flash(f'Recepción {recepcion.codigo} registrada', 'success')
        return redirect(url_for('maquila.recepcion_detalle',
                                recepcion_id=recepcion.id))

    return render_template(
        'maquila/recepcion_nueva.html',
        clientes=Cliente.query.order_by(Cliente.nombre).all(),
        ingredientes=Ingrediente.query.filter_by(activo=True)
                                      .order_by(Ingrediente.nombre).all())


@bp.route('/recepciones/<int:recepcion_id>')
@login_required
@requiere_rol(['super_admin'])
def recepcion_detalle(recepcion_id):
    recepcion = db.session.get(RecepcionIngrediente, recepcion_id) or abort(404)
    saldos_linea = {l.id: servicios.saldo_de_linea(l.id) for l in recepcion.lineas}
    return render_template('maquila/recepcion_detalle.html',
                           recepcion=recepcion, saldos_linea=saldos_linea)


@bp.route('/recepciones/<int:recepcion_id>/anular', methods=['POST'])
@login_required
@requiere_rol(['super_admin'])
def recepcion_anular(recepcion_id):
    recepcion = db.session.get(RecepcionIngrediente, recepcion_id) or abort(404)
    try:
        servicios.anular_recepcion(recepcion, current_user.id,
                                   request.form.get('motivo', ''))
        db.session.commit()
        flash(f'Recepción {recepcion.codigo} anulada', 'success')
    except (servicios.RecepcionConsumida, servicios.MotivoRequerido,
            servicios.RecepcionInvalida) as exc:
        db.session.rollback()
        flash(str(exc), 'error')
    return redirect(url_for('maquila.recepcion_detalle', recepcion_id=recepcion_id))


@bp.route('/recepciones/foto/<int:foto_id>')
@login_required
@requiere_rol(['super_admin'])
def recepcion_foto(foto_id):
    foto = db.session.get(RecepcionFoto, foto_id) or abort(404)
    return Response(foto.imagen, mimetype=foto.mimetype)
```

- [ ] **Step 4: Escribir las plantillas**

Reemplazar `templates/maquila/base_maquila.html` por:

```html
{% extends "base.html" %}
{% block extra_css %}
<link rel="stylesheet" href="{{ url_for('static', filename='css/maquila.css') }}">
{% endblock %}
{% block content %}
<div class="ops-wrap maquila-wrap">
  <header class="ops-head">
    <h1 class="ops-title">{% block maquila_title %}Maquila{% endblock %}</h1>
    <nav class="maquila-nav">
      <a href="{{ url_for('maquila.index') }}">Resumen</a>
      <a href="{{ url_for('maquila.recepciones') }}">Recepciones</a>
      <a href="{{ url_for('maquila.corridas') }}">Producción</a>
      <a href="{{ url_for('maquila.recetas') }}">Recetas</a>
      <a href="{{ url_for('maquila.ingredientes') }}">Ingredientes</a>
      <a href="{{ url_for('maquila.reporte_trazabilidad') }}">Trazabilidad</a>
    </nav>
  </header>
  {% block maquila_body %}{% endblock %}
</div>
{% endblock %}
```

**Nota:** este `base_maquila.html` referencia endpoints que aún no existen
(`maquila.corridas`, `maquila.recetas`, `maquila.reporte_trazabilidad`). Se crean
en las Tasks 10 y 12. Hasta entonces, dejar solo los enlaces de Resumen,
Recepciones e Ingredientes y añadir los otros cuando cada task los cree — un
`url_for` a un endpoint inexistente revienta el render de TODAS las pantallas.

Crear `templates/maquila/recepcion_nueva.html`:

```html
{% extends "maquila/base_maquila.html" %}
{% block title %}Nueva recepción{% endblock %}
{% block maquila_title %}Nueva recepción{% endblock %}
{% block maquila_body %}
<form method="POST" enctype="multipart/form-data" class="ops-sheet-form" id="rec-form">
  <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">

  <section class="ops-card">
    <h2>Cabecera</h2>
    <div class="ops-field">
      <label for="cliente_id">Cliente</label>
      <select id="cliente_id" name="cliente_id" required>
        {% for c in clientes %}<option value="{{ c.id }}">{{ c.nombre }}</option>{% endfor %}
      </select>
    </div>
    <div class="ops-field">
      <label for="recibido_en">Fecha</label>
      <input type="date" id="recibido_en" name="recibido_en" required>
    </div>
    <div class="ops-field">
      <label for="documento_cliente">Documento del cliente <small>(opcional)</small></label>
      <input type="text" id="documento_cliente" name="documento_cliente"
             placeholder="Guía o remisión, si la mandaron">
    </div>
    <div class="ops-field">
      <label for="temperatura">Temperatura °C</label>
      <input type="number" step="0.1" id="temperatura" name="temperatura">
    </div>
    <div class="ops-field">
      <label for="transportista">Transportista</label>
      <input type="text" id="transportista" name="transportista">
    </div>
  </section>

  <section class="ops-card">
    <h2>Ingredientes</h2>
    <div id="rec-lineas"></div>
    <button type="button" class="btn" id="rec-add-linea">Agregar ingrediente</button>
  </section>

  <section class="ops-card">
    <h2>Evidencia</h2>
    <div class="ops-field">
      <label for="fotos">Fotos</label>
      <input type="file" id="fotos" name="fotos" accept="image/*" capture="environment" multiple>
    </div>
    <div class="ops-firma-label">Firma de quien entrega</div>
    <div class="ops-firma-pad"><canvas id="firmaPad" width="600" height="200"></canvas></div>
    <button type="button" class="ops-firma-clear" id="firmaClear">Borrar firma</button>
    <input type="hidden" name="firma_png" id="firma_png">
  </section>

  <footer class="ops-sticky-footer">
    <button type="submit" class="btn btn-primary">Guardar recepción</button>
  </footer>
</form>

<template id="rec-linea-tpl">
  <div class="rec-linea">
    <select name="linea_ingrediente_id" required>
      {% for i in ingredientes %}<option value="{{ i.id }}">{{ i.nombre }}</option>{% endfor %}
    </select>
    <input type="text" name="linea_lote_cliente" placeholder="Lote del cliente (opcional)">
    <input type="date" name="linea_fecha_vencimiento">
    <input type="text" name="linea_bultos" placeholder="Bultos: 12.5, 11.5">
    <input type="number" step="0.001" name="linea_peso_total" placeholder="o peso total">
  </div>
</template>

<script nonce="{{ csp_nonce() }}">
(function () {
  var cont = document.getElementById('rec-lineas');
  var tpl = document.getElementById('rec-linea-tpl');
  function addLinea() { cont.appendChild(tpl.content.cloneNode(true)); }
  document.getElementById('rec-add-linea').addEventListener('click', addLinea);
  addLinea();

  // Color FIJO: los tokens claros están scopeados a .ops-*, así que leerlos de
  // document.body devuelve el token OSCURO y la firma sale blanca sobre blanco.
  var TINTA = '#0f172a';
  var canvas = document.getElementById('firmaPad');
  var ctx = canvas.getContext('2d');
  var dibujando = false, hayFirma = false;
  ctx.lineWidth = 2; ctx.lineCap = 'round'; ctx.strokeStyle = TINTA;

  function pos(e) {
    var r = canvas.getBoundingClientRect();
    var p = e.touches ? e.touches[0] : e;
    return { x: (p.clientX - r.left) * canvas.width / r.width,
             y: (p.clientY - r.top) * canvas.height / r.height };
  }
  function start(e) { dibujando = true; hayFirma = true; var q = pos(e);
                      ctx.beginPath(); ctx.moveTo(q.x, q.y); e.preventDefault(); }
  function move(e) { if (!dibujando) return; var q = pos(e);
                     ctx.lineTo(q.x, q.y); ctx.stroke(); e.preventDefault(); }
  function end() { dibujando = false; }

  ['mousedown', 'touchstart'].forEach(function (ev) { canvas.addEventListener(ev, start); });
  ['mousemove', 'touchmove'].forEach(function (ev) { canvas.addEventListener(ev, move); });
  ['mouseup', 'mouseleave', 'touchend'].forEach(function (ev) { canvas.addEventListener(ev, end); });

  document.getElementById('firmaClear').addEventListener('click', function () {
    ctx.clearRect(0, 0, canvas.width, canvas.height); hayFirma = false;
  });

  document.getElementById('rec-form').addEventListener('submit', function () {
    if (hayFirma) document.getElementById('firma_png').value = canvas.toDataURL('image/png');
  });

  // Reducir las fotos antes de subir: cuatro imágenes de iPhone en crudo
  // hinchan la fila y la memoria del dyno.
  var input = document.getElementById('fotos');
  input.addEventListener('change', function () {
    var dt = new DataTransfer();
    var pendientes = input.files.length;
    if (!pendientes) return;
    Array.prototype.forEach.call(input.files, function (file) {
      var img = new Image();
      img.onload = function () {
        var max = 1280;
        var escala = Math.min(1, max / Math.max(img.width, img.height));
        var c = document.createElement('canvas');
        c.width = Math.round(img.width * escala);
        c.height = Math.round(img.height * escala);
        c.getContext('2d').drawImage(img, 0, 0, c.width, c.height);
        c.toBlob(function (blob) {
          dt.items.add(new File([blob], file.name.replace(/\.\w+$/, '') + '.jpg',
                                { type: 'image/jpeg' }));
          if (--pendientes === 0) { input.files = dt.files; }
        }, 'image/jpeg', 0.8);
      };
      img.src = URL.createObjectURL(file);
    });
  });
})();
</script>
{% endblock %}
```

Crear `templates/maquila/ingredientes.html`, `templates/maquila/recepciones.html` y
`templates/maquila/recepcion_detalle.html` con el contenido que detalla el
**Apéndice** al final de este plan. Ojo con el `data-confirm` de la anulación: va
en el `<form>`, **no en el botón** — `base.js` delega sobre `submit` y ahí
`e.target` ya es el form; puesto en el botón no lo lee nadie y la acción sale sin
preguntar (le pasó a Facturar en producción).

Crear `static/css/maquila.css` con las clases usadas (`.maquila-wrap`,
`.maquila-nav`, `.rec-linea`, `.ops-sticky-footer`). El footer:

```css
.ops-sticky-footer {
  position: sticky;
  bottom: 0;
  padding: 12px;
  background: var(--maquila-surface, #ffffff);
  border-top: 1px solid rgba(15, 23, 42, .12);
  z-index: 10;
}
```

Sin `position: sticky` el botón queda debajo de la tabbar fija y no se puede pulsar.

- [ ] **Step 5: Correr los tests**

Run: `.venv/bin/python -m pytest tests/test_maquila_rutas.py -q`
Expected: PASS, 7 tests.

- [ ] **Step 6: Commit**

```bash
git add maquila/routes.py templates/maquila/ static/css/maquila.css tests/test_maquila_rutas.py
git commit -m "feat(maquila): registrar lo que entra, con o sin papel del cliente"
```

---

### Task 10: Pantallas de recetas y corridas

**Files:**
- Modify: `maquila/routes.py`, `templates/maquila/base_maquila.html`
- Create: `templates/maquila/recetas.html`, `templates/maquila/receta_form.html`, `templates/maquila/corridas.html`, `templates/maquila/corrida_detalle.html`
- Test: `tests/test_maquila_rutas.py` (ampliar)

**Interfaces:**
- Consumes: `servicios.abrir_corrida`, `agregar_caja_producida`, `cerrar_corrida`, `anular_corrida`, `consumo_teorico`, `receta_activa`, `validar_receta_unica`, `repartir_fifo`.
- Produces: endpoints `maquila.recetas`, `maquila.receta_form`, `maquila.corridas`, `maquila.corrida_nueva`, `maquila.corrida_detalle`, `maquila.corrida_caja`, `maquila.corrida_cerrar`, `maquila.corrida_anular`.

- [ ] **Step 1: Escribir los tests que fallan**

Añadir a `tests/test_maquila_rutas.py`:

```python
def _cliente_producto_ingrediente(app):
    from app import Cliente, Producto
    from maquila.models import Ingrediente
    with app.app_context():
        cli = Cliente(nombre='Maquila SA')
        prod = Producto(nombre='Chorizo', se_pesa=True, tax_rate=10)
        ing = Ingrediente(nombre='Carne de res')
        _db.session.add_all([cli, prod, ing])
        _db.session.commit()
        return cli.id, prod.id, ing.id


def test_abrir_una_corrida_por_la_ruta(app):
    from maquila.models import CorridaProduccion
    cli_id, prod_id, _ing = _cliente_producto_ingrediente(app)
    c = _login(app, 'admin')
    r = c.post('/maquila/corridas/nueva', data={
        'cliente_id': str(cli_id), 'producto_id': str(prod_id),
        'lote': 'L-0903', 'fecha_produccion': '2026-09-03',
        'fecha_vencimiento': '2026-12-03'}, follow_redirects=True)
    assert r.status_code == 200
    with app.app_context():
        corrida = CorridaProduccion.query.one()
        assert corrida.lote == 'L-0903'
        assert corrida.codigo == 'P-2026-0001'


def test_cerrar_una_corrida_sin_saldo_avisa_y_no_cierra(app):
    """El bloqueo tiene que llegar como mensaje, no como un 500."""
    from maquila import servicios
    from maquila.models import CorridaProduccion
    from decimal import Decimal as D
    cli_id, prod_id, ing_id = _cliente_producto_ingrediente(app)
    with app.app_context():
        corrida = servicios.abrir_corrida(
            cliente_id=cli_id, producto_id=prod_id, lote='L-1',
            fecha_produccion=date(2026, 9, 3), vendedor_id=IDS['admin'])
        servicios.agregar_caja_producida(corrida, D('40'))
        _db.session.commit()
        corrida_id = corrida.id

    c = _login(app, 'admin')
    r = c.post(f'/maquila/corridas/{corrida_id}/cerrar', data={
        'consumo_ingrediente_id': [str(ing_id)],
        'consumo_real': ['50']}, follow_redirects=True)
    assert r.status_code == 200
    assert b'Faltan' in r.data
    with app.app_context():
        assert _db.session.get(CorridaProduccion, corrida_id).estado == 'abierta'
```

- [ ] **Step 2: Correr y ver que falla**

Run: `.venv/bin/python -m pytest tests/test_maquila_rutas.py -q`
Expected: FAIL — 404 en `/maquila/corridas/nueva`.

- [ ] **Step 3: Implementar las rutas**

Añadir a `maquila/routes.py` (ampliar imports con `CorridaCaja`, `Receta`,
`RecetaIngrediente`):

```python
@bp.route('/recetas')
@login_required
@requiere_rol(['super_admin'])
def recetas():
    return render_template('maquila/recetas.html',
                           recetas=Receta.query.order_by(Receta.id.desc()).all())


@bp.route('/recetas/nueva', methods=['GET', 'POST'])
@bp.route('/recetas/<int:receta_id>', methods=['GET', 'POST'])
@login_required
@requiere_rol(['super_admin'])
def receta_form(receta_id=None):
    receta = db.session.get(Receta, receta_id) if receta_id else None
    if receta_id and receta is None:
        abort(404)

    if request.method == 'POST':
        producto_id = int(request.form['producto_id'])
        cliente_id = request.form.get('cliente_id', type=int) or None
        try:
            servicios.validar_receta_unica(producto_id, cliente_id,
                                           receta_id=receta.id if receta else None)
        except servicios.RecetaDuplicada as exc:
            flash(str(exc), 'error')
            return redirect(url_for('maquila.recetas'))

        if receta is None:
            receta = Receta(creada_por=current_user.id)
            db.session.add(receta)
        receta.producto_id = producto_id
        receta.cliente_id = cliente_id
        receta.nombre = (request.form.get('nombre') or 'Receta').strip()
        receta.base_kg = _decimal(request.form.get('base_kg')) or Decimal('100')
        receta.activa = bool(request.form.get('activa'))
        db.session.flush()

        RecetaIngrediente.query.filter_by(receta_id=receta.id).delete()
        for ingrediente_id, cantidad in zip(
                request.form.getlist('item_ingrediente_id'),
                request.form.getlist('item_cantidad')):
            valor = _decimal(cantidad)
            if ingrediente_id and valor and valor > 0:
                db.session.add(RecetaIngrediente(
                    receta_id=receta.id, ingrediente_id=int(ingrediente_id),
                    cantidad=valor))
        db.session.commit()
        flash('Receta guardada', 'success')
        return redirect(url_for('maquila.recetas'))

    return render_template(
        'maquila/receta_form.html', receta=receta,
        clientes=Cliente.query.order_by(Cliente.nombre).all(),
        productos=Producto.query.order_by(Producto.nombre).all(),
        ingredientes=Ingrediente.query.filter_by(activo=True)
                                      .order_by(Ingrediente.nombre).all())


@bp.route('/corridas')
@login_required
@requiere_rol(['super_admin'])
def corridas():
    query = CorridaProduccion.query
    cliente_id = request.args.get('cliente_id', type=int)
    if cliente_id:
        query = query.filter_by(cliente_id=cliente_id)
    return render_template(
        'maquila/corridas.html',
        corridas=query.order_by(CorridaProduccion.fecha_produccion.desc(),
                                CorridaProduccion.id.desc()).all(),
        clientes=Cliente.query.order_by(Cliente.nombre).all(),
        cliente_id=cliente_id)


@bp.route('/corridas/nueva', methods=['GET', 'POST'])
@login_required
@requiere_rol(['super_admin'])
def corrida_nueva():
    if request.method == 'POST':
        try:
            corrida = servicios.abrir_corrida(
                cliente_id=int(request.form['cliente_id']),
                producto_id=int(request.form['producto_id']),
                lote=request.form.get('lote', ''),
                fecha_produccion=_fecha(request.form.get('fecha_produccion')),
                fecha_vencimiento=_fecha(request.form.get('fecha_vencimiento')),
                vendedor_id=current_user.id,
                notas=(request.form.get('notas') or None))
        except servicios.CorridaInvalida as exc:
            db.session.rollback()
            flash(str(exc), 'error')
            return redirect(url_for('maquila.corridas'))
        flash(f'Corrida {corrida.codigo} abierta', 'success')
        return redirect(url_for('maquila.corrida_detalle', corrida_id=corrida.id))

    return render_template(
        'maquila/corrida_detalle.html', corrida=None,
        clientes=Cliente.query.order_by(Cliente.nombre).all(),
        productos=Producto.query.order_by(Producto.nombre).all(),
        teoricos={}, ingredientes=[], reparto={})


@bp.route('/corridas/<int:corrida_id>')
@login_required
@requiere_rol(['super_admin'])
def corrida_detalle(corrida_id):
    corrida = db.session.get(CorridaProduccion, corrida_id) or abort(404)
    teoricos = {}
    if corrida.receta and corrida.peso_producido > 0:
        teoricos = servicios.consumo_teorico(corrida.receta, corrida.peso_producido)

    # El reparto FIFO se muestra ANTES de confirmar, para poder corregirlo.
    reparto = {}
    for ingrediente_id, cantidad in teoricos.items():
        try:
            reparto[ingrediente_id] = servicios.repartir_fifo(
                corrida.cliente_id, ingrediente_id, cantidad)
        except (servicios.SaldoInsuficiente, ValueError):
            reparto[ingrediente_id] = None

    return render_template(
        'maquila/corrida_detalle.html', corrida=corrida, teoricos=teoricos,
        reparto=reparto,
        ingredientes=Ingrediente.query.filter_by(activo=True)
                                      .order_by(Ingrediente.nombre).all(),
        clientes=[], productos=[])


@bp.route('/corridas/<int:corrida_id>/caja', methods=['POST'])
@login_required
@requiere_rol(['super_admin'])
def corrida_caja(corrida_id):
    corrida = db.session.get(CorridaProduccion, corrida_id) or abort(404)
    try:
        servicios.agregar_caja_producida(corrida,
                                         _decimal(request.form.get('peso')))
        db.session.commit()
    except servicios.CorridaInvalida as exc:
        db.session.rollback()
        flash(str(exc), 'error')
    return redirect(url_for('maquila.corrida_detalle', corrida_id=corrida_id))


@bp.route('/corridas/<int:corrida_id>/cerrar', methods=['POST'])
@login_required
@requiere_rol(['super_admin'])
def corrida_cerrar(corrida_id):
    corrida = db.session.get(CorridaProduccion, corrida_id) or abort(404)

    consumos = {}
    for ingrediente_id, cantidad in zip(
            request.form.getlist('consumo_ingrediente_id'),
            request.form.getlist('consumo_real')):
        valor = _decimal(cantidad)
        if ingrediente_id and valor and valor > 0:
            consumos[int(ingrediente_id)] = valor

    try:
        servicios.cerrar_corrida(corrida, consumos, current_user.id)
    except servicios.SaldoInsuficiente as exc:
        db.session.rollback()
        ing = db.session.get(Ingrediente, exc.ingrediente_id)
        flash(f'Faltan {exc.faltante} de {ing.nombre if ing else exc.ingrediente_id}: '
              f'se piden {exc.pedido} y hay {exc.disponible}. '
              f'Registra un ajuste de entrada con su motivo antes de cerrar.', 'error')
        return redirect(url_for('maquila.corrida_detalle', corrida_id=corrida_id))
    except servicios.CorridaInvalida as exc:
        db.session.rollback()
        flash(str(exc), 'error')
        return redirect(url_for('maquila.corrida_detalle', corrida_id=corrida_id))

    flash(f'Corrida {corrida.codigo} cerrada. '
          f'Merma: {servicios.merma_de_corrida(corrida)} kg', 'success')
    return redirect(url_for('maquila.corrida_detalle', corrida_id=corrida_id))


@bp.route('/corridas/<int:corrida_id>/anular', methods=['POST'])
@login_required
@requiere_rol(['super_admin'])
def corrida_anular(corrida_id):
    corrida = db.session.get(CorridaProduccion, corrida_id) or abort(404)
    try:
        servicios.anular_corrida(corrida, current_user.id,
                                 request.form.get('motivo', ''))
        db.session.commit()
        flash(f'Corrida {corrida.codigo} anulada', 'success')
    except (servicios.CorridaFacturada, servicios.CorridaInvalida,
            servicios.MotivoRequerido) as exc:
        db.session.rollback()
        flash(str(exc), 'error')
    return redirect(url_for('maquila.corrida_detalle', corrida_id=corrida_id))
```

- [ ] **Step 4: Escribir las plantillas**

Crear `recetas.html`, `receta_form.html`, `corridas.html` y `corrida_detalle.html`
con el contenido que detalla el **Apéndice** al final de este plan.
`corrida_detalle.html` es la pantalla clave: lleva cajas producidas, consumo con el
teórico prellenado y editable, y el reparto FIFO mostrado **antes** del botón de
cerrar, no después.

Añadir los enlaces `maquila.corridas` y `maquila.recetas` a la nav de
`base_maquila.html`.

- [ ] **Step 5: Correr los tests**

Run: `.venv/bin/python -m pytest tests/test_maquila_rutas.py -q`
Expected: PASS, 9 tests.

- [ ] **Step 6: Commit**

```bash
git add maquila/routes.py templates/maquila/ tests/test_maquila_rutas.py
git commit -m "feat(maquila): producir, ver el reparto antes de confirmarlo, y cerrar"
```

---

### Task 11: Asignar cajas desde la pantalla de pesar

**Files:**
- Modify: `maquila/routes.py`
- Create: `templates/maquila/_asignar_cajas.html`
- Modify: `templates/pesar.html`, `app.py` (`_build_pesar_context`, ~línea 4198)
- Test: `tests/test_maquila_pesar.py`

**Interfaces:**
- Consumes: `servicios.proponer_fefo`, `asignar_cajas`, `cajas_disponibles`.
- Produces: endpoints `maquila.asignar_detalle` (POST) y `maquila.panel_asignar` (GET, parcial); clave `maquila_propuesta` en el contexto de `pesar`.

Este es el cambio más delicado del plan porque toca una pantalla que ya funciona
para 49 clientes. **La regla es que un cliente sin corridas no vea absolutamente
ninguna diferencia.**

- [ ] **Step 1: Escribir los tests que fallan**

Crear `tests/test_maquila_pesar.py`:

```python
"""La asignación FEFO dentro de pesar, sin molestar a quien no hace maquila."""
import os
from datetime import date
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
        from app import (Rol, Territorio, Vendedor, Cliente, Producto,
                         Pedido, DetallePedido)
        ra = Rol(nombre='super_admin', descripcion='Admin')
        terr = Territorio(nombre='t1', descripcion='T1')
        _db.session.add_all([ra, terr])
        _db.session.flush()
        v = Vendedor(username='admin', email='a@t.com', nombre_completo='Admin',
                     rol_id=ra.id, territorio_id=terr.id, activo=True)
        v.set_password('pw')
        cli = Cliente(nombre='Maquila SA')
        otro = Cliente(nombre='Cliente normal')
        prod = Producto(nombre='Chorizo', se_pesa=True, tax_rate=10)
        _db.session.add_all([v, cli, otro, prod])
        _db.session.flush()
        for cliente in (cli, otro):
            p = Pedido(cliente_id=cliente.id, estado='pendiente')
            _db.session.add(p)
            _db.session.flush()
            d = DetallePedido(pedido_id=p.id, producto_id=prod.id, cajas=2,
                              cajas_pedidas=2, peso=0, precio_unitario=0,
                              subtotal=0, es_linea_pedido=True)
            _db.session.add(d)
            _db.session.flush()
            clave = 'maquila' if cliente is cli else 'normal'
            IDS[f'pedido_{clave}'] = p.id
            IDS[f'detalle_{clave}'] = d.id
        _db.session.commit()
        IDS.update(vendedor=v.id, cliente=cli.id, producto=prod.id)
        yield flask_app
        _db.drop_all()


def _login(app):
    c = app.test_client()
    c.post('/login', data={'username': 'admin', 'password': 'pw'},
           follow_redirects=True)
    return c


def _corrida_con_cajas(n):
    from maquila import servicios
    c = servicios.abrir_corrida(
        cliente_id=IDS['cliente'], producto_id=IDS['producto'], lote='L-0903',
        fecha_produccion=date(2026, 9, 1), vendedor_id=IDS['vendedor'],
        fecha_vencimiento=date(2026, 12, 1))
    for i in range(n):
        servicios.agregar_caja_producida(c, Decimal('10'))
    _db.session.commit()
    return c


def test_pesar_de_un_cliente_sin_corridas_no_cambia(app):
    """Regresión: los otros 48 clientes no deben ver nada nuevo."""
    c = _login(app)
    r = c.get(f"/pedidos/{IDS['pedido_normal']}/pesar")
    assert r.status_code == 200
    assert b'Asignar de produccion' not in r.data
    assert b'Asignar de producci' not in r.data


def test_pesar_de_un_cliente_con_corridas_ofrece_la_propuesta(app):
    with app.app_context():
        _corrida_con_cajas(3)
    c = _login(app)
    r = c.get(f"/pedidos/{IDS['pedido_maquila']}/pesar")
    assert r.status_code == 200
    assert 'Asignar de producción'.encode() in r.data


def test_asignar_crea_las_cajas_pesadas_con_su_lote(app):
    from app import CajaPesada
    with app.app_context():
        corrida = _corrida_con_cajas(3)
        ids = [c.id for c in corrida.cajas[:2]]
    c = _login(app)
    r = c.post(f"/maquila/asignar/{IDS['detalle_maquila']}",
               data={'corrida_caja_id': [str(i) for i in ids]},
               follow_redirects=True)
    assert r.status_code == 200
    with app.app_context():
        pesadas = CajaPesada.query.filter_by(
            detalle_pedido_id=IDS['detalle_maquila']).all()
        assert len(pesadas) == 2
        assert {p.lote for p in pesadas} == {'L-0903'}
        assert {p.numero for p in pesadas} == {1, 2}
```

- [ ] **Step 2: Correr y ver que falla**

Run: `.venv/bin/python -m pytest tests/test_maquila_pesar.py -q`
Expected: FAIL — no aparece el bloque de asignación y `/maquila/asignar/...` da 404.

- [ ] **Step 3: Añadir las rutas**

Añadir a `maquila/routes.py` (ampliar imports con `DetallePedido` de `app` y
`CorridaCaja` de `.models`):

```python
@bp.route('/asignar/<int:detalle_id>', methods=['POST'])
@login_required
@requiere_rol(['super_admin'])
def asignar_detalle(detalle_id):
    detalle = db.session.get(DetallePedido, detalle_id) or abort(404)
    ids = request.form.getlist('corrida_caja_id', type=int)
    cajas = [db.session.get(CorridaCaja, i) for i in ids]
    cajas = [c for c in cajas if c is not None]

    try:
        creadas = servicios.asignar_cajas(detalle, cajas, current_user.id)
    except servicios.CajaNoDisponible as exc:
        db.session.rollback()
        flash(str(exc), 'error')
    else:
        flash(f'{len(creadas)} caja(s) asignadas desde producción', 'success')

    return redirect(url_for('pesar_pedido', pedido_id=detalle.pedido_id,
                            detalle_id=detalle.id))
```

- [ ] **Step 4: Pasar la propuesta al contexto de pesar**

En `app.py`, dentro de `_build_pesar_context` (~línea 4198), añadir al dict que
devuelve:

```python
        'maquila_propuesta': _maquila_propuesta(detalles),
```

Y definir justo encima de `_build_pesar_context`:

```python
def _maquila_propuesta(detalles):
    """Cajas producidas que la app sugiere para cada línea, en orden FEFO.

    Devuelve {} cuando el cliente no tiene corridas: la pantalla de pesar se
    comporta entonces exactamente como antes de que existiera este módulo.
    """
    try:
        from maquila import servicios as maquila_servicios
    except ImportError:
        return {}

    propuesta = {}
    for detalle in detalles:
        cajas = maquila_servicios.proponer_fefo(detalle)
        if cajas:
            propuesta[detalle.id] = cajas
    return propuesta
```

- [ ] **Step 5: Incrustar el parcial en `pesar.html`**

Crear `templates/maquila/_asignar_cajas.html`:

```html
{% set propuesta = maquila_propuesta.get(active_detalle.id) %}
{% if propuesta %}
<section class="pesar-lote-card maquila-asignar">
  <div class="pesar-lote-head"><span>Asignar de producción</span></div>
  <form method="POST"
        action="{{ url_for('maquila.asignar_detalle', detalle_id=active_detalle.id) }}"
        data-confirm="¿Asignar estas cajas producidas a este pedido?">
    <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
    <ul class="maquila-cajas">
      {% for caja in propuesta %}
      <li>
        <label>
          <input type="checkbox" name="corrida_caja_id" value="{{ caja.id }}" checked>
          Caja {{ caja.numero }} · {{ caja.peso }} kg ·
          lote {{ caja.corrida.lote }} ·
          vence {{ caja.corrida.fecha_vencimiento or '—' }}
        </label>
      </li>
      {% endfor %}
    </ul>
    <button type="submit" class="btn btn-primary">Asignar al pedido</button>
  </form>
</section>
{% endif %}
```

En `templates/pesar.html`, justo **antes** de `<div class="pesar-lote-card">`
(línea ~45), insertar:

```html
        {% if maquila_propuesta and active_detalle %}
          {% include 'maquila/_asignar_cajas.html' %}
        {% endif %}
```

El `{% if %}` externo evita que la plantilla explote si algún otro camino renderiza
`pesar.html` sin pasar por `_build_pesar_context`.

**El `data-confirm` va en el `<form>`, nunca en el `<button>`:** `base.js` delega
sobre `submit`, donde `e.target` ya es el form. En el botón no lo lee nadie y la
asignación sale sin preguntar.

- [ ] **Step 6: Correr los tests**

Run: `.venv/bin/python -m pytest tests/test_maquila_pesar.py tests/test_pesar.py tests/test_cajas_fraccionarias.py -q`
Expected: PASS. `test_pesar.py` es la red de seguridad: si falla, el cambio en
`_build_pesar_context` rompió algo del flujo existente.

- [ ] **Step 7: Correr la suite completa**

Run: `.venv/bin/python -m pytest tests/ -q`
Expected: sin regresiones respecto al baseline.

- [ ] **Step 8: Commit**

```bash
git add maquila/routes.py templates/maquila/_asignar_cajas.html templates/pesar.html app.py tests/test_maquila_pesar.py
git commit -m "feat(maquila): asignar cajas producidas al pedido, invisible para quien no hace maquila"
```

---

### Task 12: Pantallas de reportes, export y navegación

**Files:**
- Modify: `maquila/routes.py`, `templates/maquila/base_maquila.html`, `templates/base.html`
- Create: `templates/maquila/reporte_saldos.html`, `reporte_kardex.html`, `reporte_rendimiento.html`, `reporte_trazabilidad.html`
- Test: `tests/test_maquila_rutas.py` (ampliar)

**Interfaces:**
- Consumes: `reportes.saldos`, `kardex`, `rendimiento`, `trazar`.
- Produces: endpoints `maquila.reporte_saldos`, `maquila.reporte_kardex`, `maquila.reporte_kardex_export`, `maquila.reporte_rendimiento`, `maquila.reporte_trazabilidad`.

- [ ] **Step 1: Escribir los tests que fallan**

Añadir a `tests/test_maquila_rutas.py`:

```python
def test_el_kardex_responde_y_exporta(app):
    from maquila import servicios
    from maquila.models import Ingrediente
    cli_id, _prod_id, ing_id = _cliente_producto_ingrediente(app)
    with app.app_context():
        servicios.crear_recepcion(
            cliente_id=cli_id, recibido_en=date(2026, 9, 1),
            vendedor_id=IDS['admin'],
            lineas=[{'ingrediente_id': ing_id, 'peso_total': Decimal('50')}])
    c = _login(app, 'admin')
    r = c.get(f'/maquila/reportes/kardex?cliente_id={cli_id}')
    assert r.status_code == 200
    assert b'Carne de res' in r.data

    x = c.get(f'/maquila/reportes/kardex/export?cliente_id={cli_id}')
    assert x.status_code == 200
    assert x.headers['Content-Type'].startswith(
        'application/vnd.openxmlformats')


def test_trazabilidad_sin_resultado_no_revienta(app):
    c = _login(app, 'admin')
    r = c.get('/maquila/reportes/trazabilidad?q=NO-EXISTE')
    assert r.status_code == 200
    assert 'Sin resultados'.encode() in r.data
```

- [ ] **Step 2: Correr y ver que falla**

Run: `.venv/bin/python -m pytest tests/test_maquila_rutas.py -q`
Expected: FAIL — 404 en las rutas de reportes.

- [ ] **Step 3: Implementar las rutas**

Añadir a `maquila/routes.py` (con `import io` y `import xlsxwriter` arriba):

```python
@bp.route('/reportes/saldos')
@login_required
@requiere_rol(['super_admin'])
def reporte_saldos():
    cliente_id = request.args.get('cliente_id', type=int)
    filas = reportes.saldos(cliente_id) if cliente_id else []
    return render_template('maquila/reporte_saldos.html', filas=filas,
                           cliente_id=cliente_id,
                           clientes=_clientes_con_maquila())


@bp.route('/reportes/kardex')
@login_required
@requiere_rol(['super_admin'])
def reporte_kardex():
    cliente_id = request.args.get('cliente_id', type=int)
    filas = reportes.kardex(
        cliente_id,
        ingrediente_id=request.args.get('ingrediente_id', type=int),
        desde=_fecha(request.args.get('desde')),
        hasta=_fecha(request.args.get('hasta'))) if cliente_id else []
    return render_template(
        'maquila/reporte_kardex.html', filas=filas, cliente_id=cliente_id,
        clientes=_clientes_con_maquila(),
        ingredientes=Ingrediente.query.order_by(Ingrediente.nombre).all(),
        args=request.args)


@bp.route('/reportes/kardex/export')
@login_required
@requiere_rol(['super_admin'])
def reporte_kardex_export():
    cliente_id = request.args.get('cliente_id', type=int) or abort(400)
    filas = reportes.kardex(
        cliente_id,
        ingrediente_id=request.args.get('ingrediente_id', type=int),
        desde=_fecha(request.args.get('desde')),
        hasta=_fecha(request.args.get('hasta')))

    buffer = io.BytesIO()
    libro = xlsxwriter.Workbook(buffer, {'in_memory': True})
    hoja = libro.add_worksheet('Kardex')
    negrita = libro.add_format({'bold': True})
    encabezados = ['Fecha', 'Tipo', 'Ingrediente', 'Cantidad',
                   'Saldo', 'Origen', 'Responsable', 'Motivo']
    for col, titulo in enumerate(encabezados):
        hoja.write(0, col, titulo, negrita)

    for fila_num, fila in enumerate(filas, start=1):
        hoja.write(fila_num, 0, fila['fecha'].strftime('%Y-%m-%d %H:%M'))
        hoja.write(fila_num, 1, fila['tipo'])
        hoja.write(fila_num, 2, _excel_safe(fila['ingrediente']))
        hoja.write(fila_num, 3, float(fila['cantidad']))
        hoja.write(fila_num, 4, float(fila['saldo_acumulado']))
        hoja.write(fila_num, 5, _excel_safe(fila['origen']))
        hoja.write(fila_num, 6, _excel_safe(fila['responsable']))
        hoja.write(fila_num, 7, _excel_safe(fila['motivo'] or ''))

    libro.close()
    buffer.seek(0)
    return Response(
        buffer.read(),
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        headers={'Content-Disposition':
                 f'attachment; filename=kardex_{cliente_id}.xlsx'})


@bp.route('/reportes/rendimiento')
@login_required
@requiere_rol(['super_admin'])
def reporte_rendimiento():
    return render_template(
        'maquila/reporte_rendimiento.html',
        filas=reportes.rendimiento(
            cliente_id=request.args.get('cliente_id', type=int),
            desde=_fecha(request.args.get('desde')),
            hasta=_fecha(request.args.get('hasta'))),
        clientes=_clientes_con_maquila(), args=request.args)


@bp.route('/reportes/trazabilidad')
@login_required
@requiere_rol(['super_admin'])
def reporte_trazabilidad():
    termino = request.args.get('q', '')
    resultado = reportes.trazar(termino) if termino else None
    return render_template('maquila/reporte_trazabilidad.html',
                           resultado=resultado, termino=termino)
```

Añadir `_excel_safe` al import desde `app`: es el helper que ya existe contra
inyección de fórmulas en CSV/Excel.

- [ ] **Step 4: Escribir las plantillas de reportes**

Las cuatro extienden `maquila/base_maquila.html` y son tablas dentro de
`.ops-card`, con un `<form method="GET">` de filtros arriba. Las tres primeras
están detalladas en el **Apéndice**; `reporte_trazabilidad.html` es la que más
importa y va completa aquí:

```html
{% extends "maquila/base_maquila.html" %}
{% block title %}Trazabilidad{% endblock %}
{% block maquila_title %}Trazabilidad{% endblock %}
{% block maquila_body %}
<form method="GET" class="ops-card">
  <label for="q">Lote, código de recepción, código de corrida, pedido o factura</label>
  <input type="search" id="q" name="q" value="{{ termino }}" required>
  <button type="submit" class="btn btn-primary">Trazar</button>
</form>

{% if resultado and not resultado.encontrado %}
  <p class="ops-empty">Sin resultados para «{{ termino }}».</p>
{% elif resultado %}
  <section class="ops-card">
    <h2>Hacia atrás — de dónde salió</h2>
    <table>
      <thead><tr><th>Recepción</th><th>Fecha</th><th>Documento</th>
        <th>Lote cliente</th><th>Ingrediente</th><th>Cantidad</th></tr></thead>
      <tbody>
        {% for f in resultado.hacia_atras %}
        <tr {% if f.sin_origen %}class="maquila-sin-origen"{% endif %}>
          <td>{{ f.codigo }}{% if f.sin_origen %} <em>(pesada a mano, sin origen)</em>{% endif %}</td>
          <td>{{ f.recibido_en or '—' }}</td>
          <td>{{ f.documento_cliente or '—' }}</td>
          <td>{{ f.lote_cliente or '—' }}</td>
          <td>{{ f.ingrediente }}</td>
          <td>{{ f.cantidad }}</td>
        </tr>
        {% endfor %}
      </tbody>
    </table>
  </section>

  <section class="ops-card">
    <h2>Hacia adelante — dónde terminó</h2>
    <table>
      <thead><tr><th>Pedido</th><th>Estado</th><th>Cajas</th>
        <th>Peso</th><th>Factura QBO</th></tr></thead>
      <tbody>
        {% for f in resultado.hacia_adelante %}
        <tr>
          <td><a href="{{ url_for('detalles_pedido', pedido_id=f.pedido_id) }}">#{{ f.pedido_id }}</a></td>
          <td>{{ f.estado }}</td>
          <td>{{ f.cajas }}</td>
          <td>{{ f.peso }}</td>
          <td>{{ f.doc_number_qbo or '—' }}</td>
        </tr>
        {% endfor %}
      </tbody>
    </table>
  </section>
{% endif %}
{% endblock %}
```

Dar a `.maquila-sin-origen` un fondo ámbar en `maquila.css`: una caja sin origen
tiene que verse, no disimularse.

- [ ] **Step 5: Añadir el módulo a la navegación de la app**

En `templates/base.html`, junto a los otros enlaces de gestión (drawer ~línea 284 y
escritorio ~línea 406), añadir un enlace a `/maquila` visible solo para
super_admin:

```html
{% if current_user.is_authenticated and current_user.rol and current_user.rol.nombre == 'super_admin' %}
<a href="{{ url_for('maquila.index') }}" class="drawer-item {{ 'active' if is_maquila }}">
  <i class="fas fa-industry"></i> Maquila
</a>
{% endif %}
```

Y añadir arriba, junto a los otros `{% set %}` (~línea 237):

```html
{% set is_maquila = current_path.startswith('/maquila') %}
```

Añadir también los enlaces de reportes a la nav de `base_maquila.html`.

- [ ] **Step 6: Correr los tests**

Run: `.venv/bin/python -m pytest tests/test_maquila_rutas.py -q`
Expected: PASS, 11 tests.

- [ ] **Step 7: Correr la suite completa**

Run: `.venv/bin/python -m pytest tests/ -q`
Expected: sin regresiones. `test_gestion_ui.py` y `test_reskin_smoke.py` son los
candidatos a romperse por el cambio en `base.html` — si fallan, mirar si esperan
un número exacto de enlaces.

- [ ] **Step 8: Commit**

```bash
git add maquila/routes.py templates/maquila/ templates/base.html static/css/maquila.css tests/test_maquila_rutas.py
git commit -m "feat(maquila): los reportes de auditoría y la puerta de entrada al módulo"
```

---

### Task 13: Migración de producción

**Files:**
- Create: `scripts/maquila_migracion.sql`

**Interfaces:**
- Consumes: el esquema definido en `maquila/models.py`.
- Produces: el guion SQL que crea las doce tablas en Postgres.

`alembic_version` en producción está desacoplado y no hay release phase. Los
`CREATE TABLE` van **a mano y antes del push**, o el dyno arranca dando 500 en cada
pantalla que toque el módulo.

- [ ] **Step 1: Generar el SQL desde los modelos**

Ejecutar en local para obtener el DDL exacto en dialecto Postgres:

```bash
.venv/bin/python -c "
import os
os.environ.setdefault('FLASK_ENV','testing')
os.environ.setdefault('SECRET_KEY','x')
os.environ.setdefault('DATABASE_URL','sqlite:///:memory:')
from sqlalchemy.schema import CreateTable, CreateIndex
from sqlalchemy.dialects import postgresql
from app import db
import maquila.models as m
tablas = ['ingrediente','recepcion_ingrediente','recepcion_linea','recepcion_bulto',
          'recepcion_foto','receta','receta_ingrediente','corrida_produccion',
          'corrida_caja','corrida_consumo','corrida_consumo_origen',
          'movimiento_ingrediente']
for nombre in tablas:
    t = db.metadata.tables[nombre]
    print(str(CreateTable(t).compile(dialect=postgresql.dialect())).strip() + ';')
    for ix in t.indexes:
        print(str(CreateIndex(ix).compile(dialect=postgresql.dialect())).strip() + ';')
" > scripts/maquila_migracion.sql
```

- [ ] **Step 2: Revisar el SQL a ojo**

Abrir `scripts/maquila_migracion.sql` y verificar:
- Las doce tablas están, **en orden de dependencia** (`ingrediente` antes que
  `recepcion_linea`, `recepcion_ingrediente` antes que `recepcion_linea`,
  `corrida_produccion` antes que `corrida_caja`, `corrida_consumo` antes que
  `corrida_consumo_origen`).
- `corrida_caja.caja_pesada_id` lleva `ON DELETE SET NULL` y un `UNIQUE`.
- `recepcion_linea`, `recepcion_bulto`, `recepcion_foto`, `receta_ingrediente`,
  `corrida_caja`, `corrida_consumo` y `corrida_consumo_origen` llevan
  `ON DELETE CASCADE`.
- Ninguna sentencia toca una tabla existente. **Si aparece un `ALTER TABLE`, algo
  está mal: este módulo no modifica ningún esquema previo.**

Añadir al principio del archivo:

```sql
-- Módulo de maquila. Correr ANTES del push a Heroku:
--   heroku pg:psql --app pesosapp -f scripts/maquila_migracion.sql
--   heroku restart --app pesosapp
-- No modifica ninguna tabla existente: solo crea las doce nuevas.
BEGIN;
```

y al final:

```sql
COMMIT;
```

- [ ] **Step 3: Probar el guion contra una base limpia**

```bash
createdb maquila_prueba && psql maquila_prueba -f scripts/maquila_migracion.sql
```

Expected: `COMMIT` sin errores. Si falla por una foreign key a `cliente`,
`producto`, `vendedor` o `caja_pesada`, es que el orden es incorrecto **o** que la
prueba se corrió sobre una base sin el esquema de la app — en ese caso probar sobre
un dump de producción restaurado.

Limpiar: `dropdb maquila_prueba`.

- [ ] **Step 4: Correr la suite completa una última vez**

Run: `.venv/bin/python -m pytest tests/ -q`
Expected: sin regresiones respecto al baseline anotado en la Task 1.

- [ ] **Step 5: Commit**

```bash
git add scripts/maquila_migracion.sql
git commit -m "chore(maquila): el SQL de producción, que va antes del push y no después"
```

- [ ] **Step 6: Despliegue (lo hace JM, no el agente)**

En este orden, sin saltarse ninguno:

```bash
heroku pg:psql --app pesosapp -f scripts/maquila_migracion.sql
```

```bash
git push heroku main
```

```bash
heroku restart --app pesosapp
```

Verificar después: entrar a `https://app.jomarfoods.com/maquila` como super_admin y
comprobar que la pantalla carga y que **la pantalla de pesar de un cliente sin
corridas sigue igual**.

---

## Apéndice: contenido exacto de las plantillas descritas por encima

Las Tasks 9, 10 y 12 muestran completas las dos plantillas con lógica de verdad
(`recepcion_nueva.html` y `reporte_trazabilidad.html`). Las demás son tablas y
formularios; aquí va qué lleva cada una, para que nadie tenga que inventarlo.

Todas: `{% extends "maquila/base_maquila.html" %}`, contenido dentro de
`<section class="ops-card">`, y todo `<form method="POST">` con
`<input type="hidden" name="csrf_token" value="{{ csrf_token() }}">`.

**`ingredientes.html`** — Formulario de alta (nombre, unidad `kg`/`ud`, notas) y
tabla: Nombre · Unidad · Estado · Acción. La acción es un `<form method="POST">` a
`maquila.toggle_ingrediente` con un botón «Activar»/«Desactivar».

**`recepciones.html`** — `<form method="GET">` con un `<select name="cliente_id">`
y `data-autosubmit`. Tabla: Código · Fecha · Cliente · Líneas
(`recepcion.lineas|length`) · Peso total (suma de `l.peso_total`) · Estado
(`Anulada` si `recepcion.anulada`, si no `Vigente`). El código enlaza a
`maquila.recepcion_detalle`. Botón «Nueva recepción» arriba.

**`recepcion_detalle.html`** — Cabecera con código, cliente, fecha, documento
(o «Sin documento del cliente»), temperatura y transportista. Tabla de líneas:
Ingrediente · Lote cliente · Vencimiento · Peso · **Saldo**
(`saldos_linea[l.id]`) · Bultos (`l.bultos|length`). Galería de fotos con
`<img src="{{ url_for('maquila.recepcion_foto', foto_id=f.id) }}">`. La firma con
`{% if recepcion.firma %}` y una etiqueta `<img>` a un endpoint equivalente, o
simplemente el texto «Firmada por {{ recepcion.transportista }}». Al final, si no
está anulada, un `<form method="POST">` a `maquila.recepcion_anular` con un input
`motivo` obligatorio y `data-confirm="¿Anular esta recepción?"` **en el form**.

**`recetas.html`** — Tabla: Nombre · Producto · Cliente (o «Genérica») · Base kg ·
Ingredientes (`receta.ingredientes|length`) · Activa. Nombre enlaza a
`maquila.receta_form`. Botón «Nueva receta».

**`receta_form.html`** — Campos: `nombre`, `producto_id` (select de `productos`),
`cliente_id` (select con una opción vacía = genérica), `base_kg` (number, default
100), `activa` (checkbox). Debajo, filas repetibles con `item_ingrediente_id`
(select de `ingredientes`) e `item_cantidad` (number step 0.001), más un botón
«Agregar ingrediente» que clona un `<template>` — mismo patrón que las líneas de
`recepcion_nueva.html`, con su `<script nonce="{{ csp_nonce() }}">`. Guardar en
`.ops-sticky-footer`.

**`corridas.html`** — Filtro por cliente igual que `recepciones.html`. Tabla:
Código · Lote · Cliente · Producto · Fecha · Cajas (`corrida.cajas|length`) ·
Producido (`corrida.peso_producido`) · Estado. Código enlaza a
`maquila.corrida_detalle`. Botón «Nueva corrida».

**`corrida_detalle.html`** — Cuando `corrida` es `None` (ruta `corrida_nueva`),
solo el formulario de apertura: `cliente_id`, `producto_id`, `lote`,
`fecha_produccion`, `fecha_vencimiento`, `notas`. Cuando hay corrida, tres bloques:

1. *Cajas producidas* — `<form method="POST">` a `maquila.corrida_caja` con un
   input `peso`, y la lista de `corrida.cajas` (número, peso, y «asignada al
   pedido N» si `caja.caja_pesada_id`). Total = `corrida.peso_producido`.
2. *Consumo* — dentro del `<form>` de cierre: una fila por ingrediente con
   `<input type="hidden" name="consumo_ingrediente_id" value="{{ i.id }}">` y
   `<input type="number" step="0.001" name="consumo_real"
   value="{{ teoricos.get(i.id, '') }}">`. El teórico llega prellenado y editable.
3. *Reparto FIFO* — para cada `ingrediente_id, tramos` de `reparto`: si `tramos`
   es `None`, una fila con clase `maquila-sin-saldo` y el texto «sin saldo
   suficiente»; si no, una fila por tramo con la línea de recepción y la cantidad.
   Este bloque va **antes** del botón de cerrar.

Cerrar va en `.ops-sticky-footer`, con
`data-confirm="Cerrar la corrida descuenta los ingredientes. ¿Continuar?"` en el
`<form>`. Si `corrida.estado != 'abierta'`, en vez del formulario se muestra la
merma (`consumido − producido`) y, si no está anulada, el formulario de anulación
con `motivo`.

**`reporte_saldos.html`** — Selector de cliente con `data-autosubmit`. Tabla:
Ingrediente · Recibido · Consumido · Ajustes · **Saldo**. Debajo de cada fila, las
`lineas_abiertas` en una sublista: Código · Fecha · Lote cliente · Saldo.

**`reporte_kardex.html`** — Filtros: cliente, ingrediente, desde, hasta. Tabla:
Fecha (`f.fecha.strftime('%Y-%m-%d %H:%M')`, ya en hora de Curazao) · Tipo ·
Ingrediente · Cantidad · **Saldo acumulado** · Origen · Responsable · Motivo.
Botón «Exportar XLSX» que es un enlace a `maquila.reporte_kardex_export`
arrastrando los mismos `request.args`.

**`reporte_rendimiento.html`** — Filtros: cliente, desde, hasta. Tabla: Corrida ·
Lote · Producto · Fecha · Consumido · Producido · **Merma** · **Merma %**. Cada
fila desplegable con sus `varianzas`: Ingrediente · Teórica · Real · Diferencia ·
%. Pintar en rojo las diferencias por encima del 10%.

---

## Baseline antes de empezar

Antes de la Task 1, correr y **anotar el resultado**:

```bash
.venv/bin/python -m pytest tests/ -q
```

Varios tests del repo están acoplados a markup HTML exacto y pueden venir ya
fallando. Sin ese número anotado, es imposible distinguir una regresión propia de
un fallo preexistente.
