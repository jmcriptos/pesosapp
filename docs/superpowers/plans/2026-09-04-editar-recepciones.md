# Editar recepciones — Plan de implementación

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Poder corregir una recepción de ingredientes ya registrada —incluidas cantidades que ya alimentaron una corrida— sin que el saldo y la pantalla dejen de coincidir.

**Architecture:** `peso_total` se corrige al valor real Y se escribe un movimiento de ajuste por la diferencia, atado a esa línea. Eso preserva `peso_total − consumido == saldo_de_linea`, que es la identidad de la que cuelga el FIFO. El ledger sigue siendo append-only: no se edita ni se borra ningún movimiento anterior. Una sola pantalla de edición, espejo de la de captura, con un POST y una transacción.

**Tech Stack:** Flask 3.1.3, Flask-SQLAlchemy 3.1.1, Jinja2, pytest.

**Spec:** `docs/superpowers/specs/2026-09-04-editar-recepciones-design.md`

## Global Constraints

- **Cantidades en `Decimal`, nunca `float`.**
- **Toda escritura al ledger por `servicios.registrar_movimiento`.** Ningún `db.session.add(MovimientoIngrediente(...))` directo.
- **El ledger es append-only:** ni un `UPDATE`, ni un `DELETE` sobre `movimiento_ingrediente`.
- **Se escribe movimiento SOLO para las líneas cuya cantidad cambió.** Sin esto el kardex se vuelve ilegible en un mes.
- **Nunca `from app import X`** dentro de `maquila/`: se resuelve por `sys.modules` desde `maquila/__init__.py` (`app_module = sys.modules.get('app') or sys.modules['__main__']`). Un import por nombre rompe `python app.py`.
- **Nada de `type=int` dentro de una plantilla Jinja.** No tiene los builtins de Python. Los ids se resuelven en la ruta y se pasan resueltos.
- **Cantidades en pantalla con `|fmt_cant(unidad)`**, nunca `Decimal` crudo. La unidad nunca se asume: sale de `linea.ingrediente.unidad`.
- **Cada `<td>` con su `data-label`**, o la ficha de móvil sale sin etiquetas.
- **`data-confirm` va en el `<form>`**, no en el botón, salvo formularios con varios submits.
- **Todo `<script>` inline con `nonce="{{ csp_nonce() }}"`.**
- **La firma con color fijo `#0f172a`**, nunca leído de `document.body`.
- **Todo selector CSS nuevo prefijado con `.maquila-wrap`.**
- **Acceso `@login_required` + `@requiere_rol(['super_admin'])`; todo POST con `csrf_token`.**
- **Correr los tests así:** `.venv/bin/python -m pytest tests/<archivo> -q` — sin exportar `DATABASE_URL` a un archivo. La suite completa la corre el coordinador.
- Baseline de la suite al empezar: **1027 passed, 1 skipped, 0 failed**.

## Estructura de archivos

```
maquila/models.py       + RecepcionLinea.anulada_en y su propiedad `anulada`
maquila/servicios.py    + editar_recepcion, RecepcionNoEditable, CorreccionImposible
maquila/routes.py       + GET/POST /recepciones/<id>/editar
templates/maquila/recepcion_editar.html   (nuevo)
templates/maquila/recepcion_detalle.html  + botón Editar, y ocultar líneas anuladas
scripts/maquila_editar_migracion.sql      (nuevo)
tests/test_maquila_editar_recepcion.py    (nuevo)
```

La lógica vive en `servicios.py` como el resto del módulo; la ruta solo traduce
formulario → servicio → plantilla. Es lo que permite probar el riesgo sin HTTP.

---

### Task 1: La columna que marca una línea quitada

**Files:**
- Modify: `maquila/models.py` (clase `RecepcionLinea`, ~línea 95)
- Create: `scripts/maquila_editar_migracion.sql`
- Test: `tests/test_maquila_editar_recepcion.py`

**Interfaces:**
- Produces: `RecepcionLinea.anulada_en` (`DateTime`, nullable) y la propiedad `RecepcionLinea.anulada` (bool).

- [ ] **Step 1: Escribir el test que falla**

Crear `tests/test_maquila_editar_recepcion.py`:

```python
"""Editar una recepción sin que el saldo y la pantalla dejen de coincidir."""
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
        rv = Rol(nombre='vendedor', descripcion='Vendedor')
        terr = Territorio(nombre='t1', descripcion='T1')
        _db.session.add_all([ra, rv, terr])
        _db.session.flush()
        v = Vendedor(username='admin', email='a@t.com', nombre_completo='Admin',
                     rol_id=ra.id, territorio_id=terr.id, activo=True)
        v.set_password('pw')
        vend = Vendedor(username='vend', email='v@t.com', nombre_completo='Vend',
                        rol_id=rv.id, territorio_id=terr.id, activo=True)
        vend.set_password('pw')
        cli = Cliente(nombre='Maquila SA')
        otro = Cliente(nombre='Otro cliente')
        prod = Producto(nombre='Chorizo', se_pesa=True, tax_rate=10)
        carne = Ingrediente(nombre='Carne de res', unidad='kg')
        grasa = Ingrediente(nombre='Grasa', unidad='kg')
        _db.session.add_all([v, vend, cli, otro, prod, carne, grasa])
        _db.session.commit()
        IDS.update(vendedor=v.id, cliente=cli.id, otro_cliente=otro.id,
                   producto=prod.id, carne=carne.id, grasa=grasa.id)
        yield flask_app
        _db.drop_all()


def _recepcion(kg=100, ingrediente=None, dia=1):
    """Una recepción de una línea, a granel."""
    from maquila import servicios
    return servicios.crear_recepcion(
        cliente_id=IDS['cliente'], recibido_en=date(2026, 9, dia),
        vendedor_id=IDS['vendedor'],
        lineas=[{'ingrediente_id': ingrediente or IDS['carne'],
                 'peso_total': Decimal(str(kg))}])


def test_una_linea_nueva_no_nace_anulada(app):
    with app.app_context():
        rec = _recepcion()
        linea = rec.lineas[0]
        assert linea.anulada_en is None
        assert linea.anulada is False
```

- [ ] **Step 2: Correr y ver que falla**

Run: `.venv/bin/python -m pytest tests/test_maquila_editar_recepcion.py -q`
Expected: FAIL — `AttributeError: 'RecepcionLinea' object has no attribute 'anulada_en'`.

- [ ] **Step 3: Agregar la columna**

En `maquila/models.py`, dentro de `class RecepcionLinea`, después de `peso_total`:

```python
    # Quitar una línea no la borra: el módulo no borra nada, nunca, y además
    # borrar la fila dejaría huérfanos los movimiento_ingrediente que la
    # referencian. Mismo patrón que recepcion_ingrediente.anulada_en y
    # corrida_caja.anulada_en.
    anulada_en = db.Column(db.DateTime, nullable=True)
```

Y después de las relaciones de esa clase:

```python
    @property
    def anulada(self):
        return self.anulada_en is not None
```

- [ ] **Step 4: Correr el test**

Run: `.venv/bin/python -m pytest tests/test_maquila_editar_recepcion.py -q`
Expected: PASS, 1 test.

- [ ] **Step 5: Escribir el SQL de producción**

Crear `scripts/maquila_editar_migracion.sql`:

```sql
-- Editar recepciones. Correr ANTES del push a Heroku:
--   heroku pg:psql --app pesosapp -f scripts/maquila_editar_migracion.sql
--   heroku restart --app pesosapp
-- Aditivo y nullable: no toca ninguna fila existente.
BEGIN;

ALTER TABLE recepcion_linea ADD COLUMN anulada_en TIMESTAMP;

COMMIT;
```

- [ ] **Step 6: Commit**

```bash
git add maquila/models.py scripts/maquila_editar_migracion.sql tests/test_maquila_editar_recepcion.py
git commit -m "feat(maquila): una línea de recepción se puede marcar quitada, no borrar"
```

---

### Task 2: El servicio de edición

**Files:**
- Modify: `maquila/servicios.py`
- Test: `tests/test_maquila_editar_recepcion.py` (ampliar)

**Interfaces:**
- Consumes: `registrar_movimiento`, `saldo_de_linea`, `_dec`, `CERO`, `MotivoRequerido`, `RecepcionInvalida` — todos ya existen en `servicios.py`.
- Produces:
  - `editar_recepcion(recepcion, *, vendedor_id, cabecera, lineas, motivo=None, fotos_a_borrar=None, fotos_nuevas=None, firma=None, firma_mimetype=None) -> RecepcionIngrediente`. **Hace commit.**
    - `cabecera`: dict con `cliente_id`, `recibido_en`, `documento_cliente`, `temperatura`, `transportista`, `notas`.
    - `lineas`: lista de dicts. Una línea existente trae `id`; una nueva no. `{'id': int|None, 'ingrediente_id': int, 'lote_cliente': str|None, 'fecha_vencimiento': date|None, 'bultos': [Decimal,...], 'peso_total': Decimal|None, 'quitar': bool}`.
  - `class RecepcionNoEditable(Exception)`
  - `class CorreccionImposible(ValueError)`
  - `consumido_de_linea(linea) -> Decimal`

- [ ] **Step 1: Escribir los tests que fallan**

Añadir a `tests/test_maquila_editar_recepcion.py`:

```python
def _consumir(linea_id, ingrediente_id, kg):
    """Simula que una corrida tomó material de esa línea."""
    from maquila import servicios
    servicios.registrar_movimiento(
        cliente_id=IDS['cliente'], ingrediente_id=ingrediente_id,
        tipo='salida', cantidad=Decimal(str(kg)), origen_tipo='corrida',
        origen_id=1, vendedor_id=IDS['vendedor'], recepcion_linea_id=linea_id)
    _db.session.commit()


def _cabecera(rec, **cambios):
    base = {'cliente_id': rec.cliente_id, 'recibido_en': rec.recibido_en,
            'documento_cliente': rec.documento_cliente,
            'temperatura': rec.temperatura, 'transportista': rec.transportista,
            'notas': rec.notas}
    base.update(cambios)
    return base


def _linea_dict(linea, **cambios):
    base = {'id': linea.id, 'ingrediente_id': linea.ingrediente_id,
            'lote_cliente': linea.lote_cliente,
            'fecha_vencimiento': linea.fecha_vencimiento,
            'bultos': [], 'peso_total': Decimal(str(linea.peso_total)),
            'quitar': False}
    base.update(cambios)
    return base


def test_corregir_escribe_exactamente_un_movimiento_por_la_diferencia(app):
    from maquila import servicios
    from maquila.models import MovimientoIngrediente
    with app.app_context():
        rec = _recepcion(100)
        linea = rec.lineas[0]
        antes = MovimientoIngrediente.query.count()

        servicios.editar_recepcion(
            rec, vendedor_id=IDS['vendedor'], cabecera=_cabecera(rec),
            lineas=[_linea_dict(linea, peso_total=Decimal('90'))],
            motivo='Se tecleó mal')

        movs = MovimientoIngrediente.query.order_by(
            MovimientoIngrediente.id).all()
        assert len(movs) == antes + 1
        assert movs[-1].tipo == 'ajuste'
        assert movs[-1].cantidad == Decimal('-10.000')
        assert movs[-1].recepcion_linea_id == linea.id
        assert 'tecleó mal' in movs[-1].motivo
        assert linea.peso_total == Decimal('90.000')


def test_tras_corregir_se_mantiene_la_identidad_del_fifo(app):
    """peso_total − consumido == saldo_de_linea. De ahí cuelga el reparto."""
    from maquila import servicios
    with app.app_context():
        rec = _recepcion(100)
        linea = rec.lineas[0]
        _consumir(linea.id, IDS['carne'], 40)

        servicios.editar_recepcion(
            rec, vendedor_id=IDS['vendedor'], cabecera=_cabecera(rec),
            lineas=[_linea_dict(linea, peso_total=Decimal('90'))],
            motivo='Se tecleó mal')

        consumido = servicios.consumido_de_linea(linea)
        assert consumido == Decimal('40.000')
        assert (Decimal(str(linea.peso_total)) - consumido
                == servicios.saldo_de_linea(linea.id))


def test_editar_solo_la_cabecera_no_toca_el_ledger(app):
    from maquila import servicios
    from maquila.models import MovimientoIngrediente
    with app.app_context():
        rec = _recepcion(100)
        linea = rec.lineas[0]
        antes = MovimientoIngrediente.query.count()

        servicios.editar_recepcion(
            rec, vendedor_id=IDS['vendedor'],
            cabecera=_cabecera(rec, transportista='Rudsel Martina',
                               documento_cliente='GD-999'),
            lineas=[_linea_dict(linea)])

        assert MovimientoIngrediente.query.count() == antes
        assert rec.transportista == 'Rudsel Martina'
        assert rec.documento_cliente == 'GD-999'


def test_guardar_sin_cambiar_nada_no_escribe_nada(app):
    from maquila import servicios
    from maquila.models import MovimientoIngrediente
    with app.app_context():
        rec = _recepcion(100)
        linea = rec.lineas[0]
        antes = MovimientoIngrediente.query.count()
        servicios.editar_recepcion(
            rec, vendedor_id=IDS['vendedor'], cabecera=_cabecera(rec),
            lineas=[_linea_dict(linea)])
        assert MovimientoIngrediente.query.count() == antes


def test_corregir_por_debajo_de_lo_consumido_se_rechaza(app):
    from maquila import servicios
    from maquila.models import MovimientoIngrediente
    with app.app_context():
        rec = _recepcion(100)
        linea = rec.lineas[0]
        _consumir(linea.id, IDS['carne'], 64)
        antes = MovimientoIngrediente.query.count()

        with pytest.raises(servicios.CorreccionImposible):
            servicios.editar_recepcion(
                rec, vendedor_id=IDS['vendedor'], cabecera=_cabecera(rec),
                lineas=[_linea_dict(linea, peso_total=Decimal('59'))],
                motivo='Imposible')

        _db.session.rollback()
        assert MovimientoIngrediente.query.count() == antes
        assert Decimal(str(rec.lineas[0].peso_total)) == Decimal('100.000')


def test_corregir_a_cero_o_negativo_se_rechaza(app):
    from maquila import servicios
    with app.app_context():
        rec = _recepcion(100)
        linea = rec.lineas[0]
        for valor in (Decimal('0'), Decimal('-5')):
            with pytest.raises(servicios.RecepcionInvalida):
                servicios.editar_recepcion(
                    rec, vendedor_id=IDS['vendedor'], cabecera=_cabecera(rec),
                    lineas=[_linea_dict(linea, peso_total=valor)],
                    motivo='x')
            _db.session.rollback()


def test_corregir_sin_motivo_se_rechaza(app):
    from maquila import servicios
    with app.app_context():
        rec = _recepcion(100)
        linea = rec.lineas[0]
        with pytest.raises(servicios.MotivoRequerido):
            servicios.editar_recepcion(
                rec, vendedor_id=IDS['vendedor'], cabecera=_cabecera(rec),
                lineas=[_linea_dict(linea, peso_total=Decimal('90'))])


def test_quitar_una_linea_intacta_escribe_su_inverso_y_la_marca(app):
    from maquila import servicios
    with app.app_context():
        rec = _recepcion(100)
        linea = rec.lineas[0]
        servicios.editar_recepcion(
            rec, vendedor_id=IDS['vendedor'], cabecera=_cabecera(rec),
            lineas=[_linea_dict(linea, quitar=True)],
            motivo='No vino')
        assert linea.anulada is True
        assert servicios.saldo_de_linea(linea.id) == Decimal('0')


def test_quitar_una_linea_consumida_se_rechaza(app):
    from maquila import servicios
    with app.app_context():
        rec = _recepcion(100)
        linea = rec.lineas[0]
        _consumir(linea.id, IDS['carne'], 40)
        with pytest.raises(servicios.CorreccionImposible):
            servicios.editar_recepcion(
                rec, vendedor_id=IDS['vendedor'], cabecera=_cabecera(rec),
                lineas=[_linea_dict(linea, quitar=True)],
                motivo='No vino')
        _db.session.rollback()
        assert rec.lineas[0].anulada is False


def test_agregar_una_linea_escribe_su_entrada(app):
    from maquila import servicios
    from maquila.models import MovimientoIngrediente
    with app.app_context():
        rec = _recepcion(100)
        linea = rec.lineas[0]
        servicios.editar_recepcion(
            rec, vendedor_id=IDS['vendedor'], cabecera=_cabecera(rec),
            lineas=[_linea_dict(linea),
                    {'id': None, 'ingrediente_id': IDS['grasa'],
                     'lote_cliente': None, 'fecha_vencimiento': None,
                     'bultos': [Decimal('12'), Decimal('8')],
                     'peso_total': None, 'quitar': False}])
        entradas = MovimientoIngrediente.query.filter_by(
            ingrediente_id=IDS['grasa'], tipo='entrada').all()
        assert len(entradas) == 1
        assert entradas[0].cantidad == Decimal('20.000')


def test_cambiar_el_cliente_con_material_consumido_se_rechaza(app):
    from maquila import servicios
    with app.app_context():
        rec = _recepcion(100)
        linea = rec.lineas[0]
        _consumir(linea.id, IDS['carne'], 40)
        with pytest.raises(servicios.CorreccionImposible):
            servicios.editar_recepcion(
                rec, vendedor_id=IDS['vendedor'],
                cabecera=_cabecera(rec, cliente_id=IDS['otro_cliente']),
                lineas=[_linea_dict(linea)])
        _db.session.rollback()


def test_cambiar_el_cliente_con_todo_intacto_se_acepta(app):
    from maquila import servicios
    with app.app_context():
        rec = _recepcion(100)
        linea = rec.lineas[0]
        servicios.editar_recepcion(
            rec, vendedor_id=IDS['vendedor'],
            cabecera=_cabecera(rec, cliente_id=IDS['otro_cliente']),
            lineas=[_linea_dict(linea)])
        assert rec.cliente_id == IDS['otro_cliente']


def test_editar_una_recepcion_anulada_se_rechaza(app):
    from maquila import servicios
    with app.app_context():
        rec = _recepcion(100)
        linea = rec.lineas[0]
        servicios.anular_recepcion(rec, IDS['vendedor'], 'Llegó mal')
        _db.session.commit()
        with pytest.raises(servicios.RecepcionNoEditable):
            servicios.editar_recepcion(
                rec, vendedor_id=IDS['vendedor'], cabecera=_cabecera(rec),
                lineas=[_linea_dict(linea, peso_total=Decimal('90'))],
                motivo='x')


def test_corregir_la_fecha_reordena_el_fifo_siguiente(app):
    """El FIFO ordena por recibido_en: corregir la fecha cambia contra qué
    línea consumirán las corridas FUTURAS, y no toca ningún reparto ya hecho."""
    from maquila import servicios
    from maquila.models import CorridaConsumoOrigen
    with app.app_context():
        vieja = _recepcion(50, dia=1)
        nueva = _recepcion(50, dia=20)
        origenes_antes = CorridaConsumoOrigen.query.count()

        # Antes de corregir, el FIFO toma de la del día 1.
        assert servicios.repartir_fifo(
            IDS['cliente'], IDS['carne'], Decimal('10')
        )[0][0] == vieja.lineas[0].id

        # Se corrige la fecha de la vieja: ahora es la MÁS reciente.
        servicios.editar_recepcion(
            vieja, vendedor_id=IDS['vendedor'],
            cabecera=_cabecera(vieja, recibido_en=date(2026, 9, 25)),
            lineas=[_linea_dict(vieja.lineas[0])])

        assert servicios.repartir_fifo(
            IDS['cliente'], IDS['carne'], Decimal('10')
        )[0][0] == nueva.lineas[0].id
        # Nada del pasado se reescribió.
        assert CorridaConsumoOrigen.query.count() == origenes_antes


def test_el_fifo_reparte_bien_contra_una_linea_corregida(app):
    from maquila import servicios
    with app.app_context():
        rec = _recepcion(100)
        linea = rec.lineas[0]
        servicios.editar_recepcion(
            rec, vendedor_id=IDS['vendedor'], cabecera=_cabecera(rec),
            lineas=[_linea_dict(linea, peso_total=Decimal('90'))],
            motivo='Se tecleó mal')
        reparto = servicios.repartir_fifo(IDS['cliente'], IDS['carne'],
                                          Decimal('90'))
        assert reparto == [(linea.id, Decimal('90'))]
        with pytest.raises(servicios.SaldoInsuficiente):
            servicios.repartir_fifo(IDS['cliente'], IDS['carne'],
                                    Decimal('91'))
```

- [ ] **Step 2: Correr y ver que fallan**

Run: `.venv/bin/python -m pytest tests/test_maquila_editar_recepcion.py -q`
Expected: FAIL — `module 'maquila.servicios' has no attribute 'editar_recepcion'`.

- [ ] **Step 3: Implementar el servicio**

Añadir a `maquila/servicios.py`:

```python
class RecepcionNoEditable(Exception):
    """La recepción está anulada: no hay nada que corregir."""


class CorreccionImposible(ValueError):
    """La corrección pedida dejaría el rastro en un estado imposible.

    Corregir por debajo de lo ya consumido, quitar una línea que ya alimentó
    una corrida, o mover a otro cliente una recepción de la que ya se consumió.
    """


def consumido_de_linea(linea):
    """Cuánto salió ya de esta línea hacia corridas de producción."""
    return _dec(linea.peso_total) - saldo_de_linea(linea.id)


def editar_recepcion(recepcion, *, vendedor_id, cabecera, lineas, motivo=None,
                     fotos_a_borrar=None, fotos_nuevas=None,
                     firma=None, firma_mimetype=None):
    """Corrige una recepción en una sola transacción.

    `peso_total` pasa al valor real Y se escribe un ajuste por la diferencia,
    de modo que `peso_total − consumido == saldo_de_linea` se mantiene: es la
    identidad de la que cuelga el FIFO. El ledger sigue append-only.

    Solo se escribe movimiento para las líneas cuya cantidad cambió. Sin eso,
    cada guardado dejaría un ajuste de cero por línea y el kardex —el único
    reporte que hoy le sirve a un auditor— se volvería ilegible.
    """
    if recepcion.anulada:
        raise RecepcionNoEditable(
            f'{recepcion.codigo} está anulada: no se puede editar')

    vivas = [l for l in recepcion.lineas if not l.anulada]
    consumidas = {l.id: consumido_de_linea(l) for l in vivas}
    hay_consumo = any(c > CERO for c in consumidas.values())

    # --- Guardas: todas antes de escribir nada ---
    nuevo_cliente = cabecera.get('cliente_id')
    if nuevo_cliente is not None and nuevo_cliente != recepcion.cliente_id \
            and hay_consumo:
        raise CorreccionImposible(
            f'{recepcion.codigo} ya alimentó una corrida: cambiarle el cliente '
            f'movería carne de un cliente a otro')

    por_id = {l.id: l for l in vivas}
    planes = []
    for datos in lineas:
        linea_id = datos.get('id')
        if linea_id is None:
            planes.append(('nueva', None, datos))
            continue
        linea = por_id.get(linea_id)
        if linea is None:
            raise CorreccionImposible(
                f'La línea {linea_id} no pertenece a {recepcion.codigo}')

        if datos.get('quitar'):
            if consumidas[linea.id] > CERO:
                raise CorreccionImposible(
                    f'La línea {linea.id} ya cedió {consumidas[linea.id]} a una '
                    f'corrida: se corrige su cantidad, no se quita')
            planes.append(('quitar', linea, datos))
            continue

        bultos = [_dec(b) for b in (datos.get('bultos') or [])]
        for i, peso in enumerate(bultos, start=1):
            if peso <= CERO:
                raise RecepcionInvalida(
                    f'Bulto {i} de la línea {linea.id} tiene peso no positivo: {peso}')
        nuevo_peso = sum(bultos, CERO) if bultos else _dec(datos.get('peso_total'))
        if nuevo_peso <= CERO:
            raise RecepcionInvalida(
                f'La línea {linea.id} necesita una cantidad positiva; '
                f'para dejarla en cero, quitala')
        if nuevo_peso < consumidas[linea.id]:
            raise CorreccionImposible(
                f'La línea {linea.id} ya cedió {consumidas[linea.id]} a una '
                f'corrida: no se puede corregir a {nuevo_peso}')
        planes.append(('editar', linea, {**datos, '_peso': nuevo_peso,
                                         '_bultos': bultos}))

    cambia_cantidad = any(
        (accion == 'nueva') or (accion == 'quitar') or
        (accion == 'editar' and datos['_peso'] != _dec(linea.peso_total))
        for accion, linea, datos in planes)
    if cambia_cantidad and not (motivo or '').strip():
        raise MotivoRequerido(
            'Corregir una cantidad exige un motivo')

    # --- Escritura ---
    try:
        for campo in ('cliente_id', 'recibido_en', 'documento_cliente',
                      'temperatura', 'transportista', 'notas'):
            if campo in cabecera:
                valor = cabecera[campo]
                if campo == 'temperatura' and valor not in (None, ''):
                    valor = _dec(valor)
                setattr(recepcion, campo, valor or None
                        if campo in ('documento_cliente', 'transportista', 'notas')
                        else valor)

        for accion, linea, datos in planes:
            if accion == 'quitar':
                registrar_movimiento(
                    cliente_id=recepcion.cliente_id,
                    ingrediente_id=linea.ingrediente_id,
                    tipo='ajuste', cantidad=-_dec(linea.peso_total),
                    origen_tipo='recepcion', origen_id=recepcion.id,
                    vendedor_id=vendedor_id, recepcion_linea_id=linea.id,
                    motivo=f'Línea quitada de {recepcion.codigo}: {motivo.strip()}')
                linea.anulada_en = datetime.utcnow()

            elif accion == 'editar':
                linea.lote_cliente = datos.get('lote_cliente') or None
                linea.fecha_vencimiento = datos.get('fecha_vencimiento')
                anterior = _dec(linea.peso_total)
                nuevo = datos['_peso']
                if datos['_bultos']:
                    RecepcionBulto.query.filter_by(
                        recepcion_linea_id=linea.id).delete()
                    for numero, peso in enumerate(datos['_bultos'], start=1):
                        db.session.add(RecepcionBulto(
                            recepcion_linea_id=linea.id, numero=numero, peso=peso))
                if nuevo != anterior:
                    linea.peso_total = nuevo
                    registrar_movimiento(
                        cliente_id=recepcion.cliente_id,
                        ingrediente_id=linea.ingrediente_id,
                        tipo='ajuste', cantidad=(nuevo - anterior),
                        origen_tipo='recepcion', origen_id=recepcion.id,
                        vendedor_id=vendedor_id, recepcion_linea_id=linea.id,
                        motivo=(f'Corrección de {recepcion.codigo}: '
                                f'{anterior} → {nuevo}. {motivo.strip()}'))

            else:  # nueva
                bultos = [_dec(b) for b in (datos.get('bultos') or [])]
                for i, peso in enumerate(bultos, start=1):
                    if peso <= CERO:
                        raise RecepcionInvalida(
                            f'Bulto {i} de la línea nueva tiene peso no positivo: {peso}')
                peso_total = sum(bultos, CERO) if bultos else _dec(datos.get('peso_total'))
                if peso_total <= CERO:
                    raise RecepcionInvalida(
                        'Una línea nueva necesita bultos pesados o un peso total positivo')
                nueva = RecepcionLinea(
                    recepcion_id=recepcion.id,
                    ingrediente_id=datos['ingrediente_id'],
                    lote_cliente=datos.get('lote_cliente') or None,
                    fecha_vencimiento=datos.get('fecha_vencimiento'),
                    peso_total=peso_total)
                db.session.add(nueva)
                db.session.flush()
                for numero, peso in enumerate(bultos, start=1):
                    db.session.add(RecepcionBulto(
                        recepcion_linea_id=nueva.id, numero=numero, peso=peso))
                registrar_movimiento(
                    cliente_id=recepcion.cliente_id,
                    ingrediente_id=nueva.ingrediente_id,
                    tipo='entrada', cantidad=peso_total,
                    origen_tipo='recepcion', origen_id=recepcion.id,
                    vendedor_id=vendedor_id, recepcion_linea_id=nueva.id)

        for foto_id in (fotos_a_borrar or []):
            foto = db.session.get(RecepcionFoto, foto_id)
            if foto is not None and foto.recepcion_id == recepcion.id:
                db.session.delete(foto)

        for imagen, mimetype in (fotos_nuevas or []):
            db.session.add(RecepcionFoto(
                recepcion_id=recepcion.id, imagen=imagen, mimetype=mimetype))

        if firma is not None:
            recepcion.firma = firma
            recepcion.firma_mimetype = firma_mimetype

        db.session.commit()
    except Exception:
        db.session.rollback()
        raise
    return recepcion
```

- [ ] **Step 4: Correr los tests**

Run: `.venv/bin/python -m pytest tests/test_maquila_editar_recepcion.py -q`
Expected: PASS, 16 tests (1 de la Task 1 + 15 de esta).

- [ ] **Step 5: Commit**

```bash
git add maquila/servicios.py tests/test_maquila_editar_recepcion.py
git commit -m "feat(maquila): corregir una recepción sin desincronizar el saldo"
```

---

### Task 3: La pantalla de edición

**Files:**
- Modify: `maquila/routes.py`, `templates/maquila/recepcion_detalle.html`
- Create: `templates/maquila/recepcion_editar.html`
- Test: `tests/test_maquila_editar_recepcion.py` (ampliar)

**Interfaces:**
- Consumes: `servicios.editar_recepcion`, `RecepcionNoEditable`, `CorreccionImposible`, `MotivoRequerido`, `RecepcionInvalida`; los helpers `_decimal`, `_fecha`, `_entero`, `MIMETYPES_FOTO_PERMITIDOS` ya existen en `routes.py`.
- Produces: endpoint `maquila.recepcion_editar` (`GET`/`POST` en `/maquila/recepciones/<int:recepcion_id>/editar`).

- [ ] **Step 1: Escribir los tests que fallan**

Añadir a `tests/test_maquila_editar_recepcion.py`:

```python
def _login(app, username):
    c = app.test_client()
    c.post('/login', data={'username': username, 'password': 'pw'},
           follow_redirects=True)
    return c


def test_la_pantalla_de_edicion_carga(app):
    with app.app_context():
        rec = _recepcion(100)
        rec_id = rec.id
    c = _login(app, 'admin')
    r = c.get(f'/maquila/recepciones/{rec_id}/editar')
    assert r.status_code == 200
    assert b'Carne de res' in r.data


def test_un_vendedor_no_entra_a_editar(app):
    with app.app_context():
        rec = _recepcion(100)
        rec_id = rec.id
    c = _login(app, 'vend')
    r = c.get(f'/maquila/recepciones/{rec_id}/editar', follow_redirects=False)
    assert r.status_code == 302


def test_corregir_por_la_ruta(app):
    from maquila.models import RecepcionLinea
    with app.app_context():
        rec = _recepcion(100)
        rec_id, linea_id = rec.id, rec.lineas[0].id
        ing = rec.lineas[0].ingrediente_id
    c = _login(app, 'admin')
    r = c.post(f'/maquila/recepciones/{rec_id}/editar', data={
        'cliente_id': str(IDS['cliente']),
        'recibido_en': '2026-09-01',
        'motivo': 'Se tecleó mal',
        'linea_id': [str(linea_id)],
        'linea_ingrediente_id': [str(ing)],
        'linea_lote_cliente': [''],
        'linea_fecha_vencimiento': [''],
        'linea_bultos': [''],
        'linea_peso_total': ['90'],
        'linea_quitar': [''],
    }, follow_redirects=True)
    assert r.status_code == 200
    with app.app_context():
        assert _db.session.get(RecepcionLinea, linea_id).peso_total == Decimal('90.000')


def test_una_correccion_imposible_da_mensaje_no_500(app):
    with app.app_context():
        rec = _recepcion(100)
        rec_id, linea_id = rec.id, rec.lineas[0].id
        ing = rec.lineas[0].ingrediente_id
        _consumir(linea_id, ing, 64)
    c = _login(app, 'admin')
    r = c.post(f'/maquila/recepciones/{rec_id}/editar', data={
        'cliente_id': str(IDS['cliente']),
        'recibido_en': '2026-09-01',
        'motivo': 'Imposible',
        'linea_id': [str(linea_id)],
        'linea_ingrediente_id': [str(ing)],
        'linea_lote_cliente': [''],
        'linea_fecha_vencimiento': [''],
        'linea_bultos': [''],
        'linea_peso_total': ['59'],
        'linea_quitar': [''],
    }, follow_redirects=True)
    assert r.status_code == 200
    assert 'ya cedió'.encode() in r.data
```

- [ ] **Step 2: Correr y ver que fallan**

Run: `.venv/bin/python -m pytest tests/test_maquila_editar_recepcion.py -q`
Expected: FAIL — 404 en `/maquila/recepciones/<id>/editar`.

- [ ] **Step 3: Escribir la ruta**

Añadir a `maquila/routes.py` (ampliar el import de `.models` con `RecepcionLinea`
si hace falta):

```python
@bp.route('/recepciones/<int:recepcion_id>/editar', methods=['GET', 'POST'])
@login_required
@requiere_rol(['super_admin'])
def recepcion_editar(recepcion_id):
    recepcion = db.session.get(RecepcionIngrediente, recepcion_id) or abort(404)

    if recepcion.anulada:
        flash(f'{recepcion.codigo} está anulada: no se puede editar', 'error')
        return redirect(url_for('maquila.recepcion_detalle',
                                recepcion_id=recepcion_id))

    if request.method == 'POST':
        lineas = []
        ids = request.form.getlist('linea_id')
        ingredientes = request.form.getlist('linea_ingrediente_id')
        lotes = request.form.getlist('linea_lote_cliente')
        vencimientos = request.form.getlist('linea_fecha_vencimiento')
        bultos_crudos = request.form.getlist('linea_bultos')
        totales = request.form.getlist('linea_peso_total')
        quitar = request.form.getlist('linea_quitar')

        for i, ingrediente_id in enumerate(ingredientes):
            if not ingrediente_id:
                continue
            crudos = (bultos_crudos[i] if i < len(bultos_crudos) else '') or ''
            bultos = [b for b in (_decimal(x) for x in crudos.split(',') if x.strip())
                      if b is not None]
            bruto_id = (ids[i] if i < len(ids) else '') or ''
            lineas.append({
                'id': _entero(bruto_id) if bruto_id else None,
                'ingrediente_id': _entero(ingrediente_id),
                'lote_cliente': (lotes[i] if i < len(lotes) else '') or None,
                'fecha_vencimiento': _fecha(vencimientos[i] if i < len(vencimientos) else ''),
                'bultos': bultos,
                'peso_total': _decimal(totales[i] if i < len(totales) else ''),
                'quitar': bool((quitar[i] if i < len(quitar) else '').strip()),
            })

        fotos_nuevas = []
        for archivo in request.files.getlist('fotos'):
            if not archivo or not archivo.filename:
                continue
            mimetype = (archivo.mimetype or '').lower()
            if mimetype not in MIMETYPES_FOTO_PERMITIDOS:
                flash('Formato de foto no permitido', 'error')
                return redirect(url_for('maquila.recepcion_editar',
                                        recepcion_id=recepcion_id))
            datos = archivo.read(MAX_FOTO_BYTES + 1)
            if len(datos) > MAX_FOTO_BYTES:
                flash('Una foto supera los 2 MB: redúcela antes de subirla', 'error')
                return redirect(url_for('maquila.recepcion_editar',
                                        recepcion_id=recepcion_id))
            fotos_nuevas.append((datos, mimetype))

        firma = None
        firma_b64 = request.form.get('firma_png') or ''
        if firma_b64.startswith('data:image/png;base64,'):
            import base64
            import binascii
            try:
                firma = base64.b64decode(firma_b64.split(',', 1)[1], validate=True)
            except (binascii.Error, ValueError):
                firma = None
                flash('La firma no se pudo leer: se guardó sin cambiarla', 'error')

        try:
            servicios.editar_recepcion(
                recepcion, vendedor_id=current_user.id,
                cabecera={
                    'cliente_id': _entero(request.form.get('cliente_id')),
                    'recibido_en': _fecha(request.form.get('recibido_en')),
                    'documento_cliente': request.form.get('documento_cliente'),
                    'temperatura': _decimal(request.form.get('temperatura')),
                    'transportista': request.form.get('transportista'),
                    'notas': request.form.get('notas'),
                },
                lineas=lineas,
                motivo=request.form.get('motivo'),
                fotos_a_borrar=request.form.getlist('borrar_foto', type=int),
                fotos_nuevas=fotos_nuevas,
                firma=firma,
                firma_mimetype='image/png' if firma else None)
        except (servicios.CorreccionImposible, servicios.RecepcionInvalida,
                servicios.MotivoRequerido, servicios.RecepcionNoEditable) as exc:
            db.session.rollback()
            flash(str(exc), 'error')
            return redirect(url_for('maquila.recepcion_editar',
                                    recepcion_id=recepcion_id))
        except Exception:
            db.session.rollback()
            flash('No se pudo guardar la corrección', 'error')
            return redirect(url_for('maquila.recepcion_editar',
                                    recepcion_id=recepcion_id))

        flash(f'{recepcion.codigo} corregida', 'success')
        return redirect(url_for('maquila.recepcion_detalle',
                                recepcion_id=recepcion_id))

    vivas = [l for l in recepcion.lineas if not l.anulada]
    return render_template(
        'maquila/recepcion_editar.html',
        recepcion=recepcion,
        lineas=vivas,
        consumido={l.id: servicios.consumido_de_linea(l) for l in vivas},
        clientes=Cliente.query.order_by(Cliente.nombre).all(),
        ingredientes=Ingrediente.query.filter_by(activo=True)
                                      .order_by(Ingrediente.nombre).all())
```

- [ ] **Step 4: Escribir la plantilla**

Crear `templates/maquila/recepcion_editar.html`. **Leé primero
`templates/maquila/recepcion_nueva.html` entero** y espejalo: la reducción de
fotos en el navegador, el canvas de firma y el footer sticky se copian de ahí
tal cual, ya están corregidos.

Van completos los dos bloques donde están las trampas, porque son los que un
espejo descuidado rompe:

```html
{#- El cliente seleccionado se compara contra el valor que ya trae el objeto.
    NUNCA `args.get('cliente_id', type=int)`: Jinja no tiene los builtins de
    Python, `int` ahí es Undefined, y werkzeug revienta al llamarlo — pero solo
    cuando el parámetro viene en la query, que es cómo ese bug llegó a
    producción sin que ningún test lo viera. -#}
<div class="ops-field">
  <label for="cliente_id">Cliente</label>
  <select id="cliente_id" name="cliente_id" required>
    {% for c in clientes %}
    <option value="{{ c.id }}" {{ 'selected' if c.id == recepcion.cliente_id else '' }}>{{ c.nombre }}</option>
    {% endfor %}
  </select>
</div>
```

```html
{#- Una línea existente. Los cinco campos llevan etiqueta asociada: la fila
    repetible de recepcion_nueva.html NO las tiene y es un hallazgo abierto de
    accesibilidad — no lo repitas al espejar. -#}
{% for l in lineas %}
<div class="rec-linea">
  <input type="hidden" name="linea_id" value="{{ l.id }}">

  <label for="ing-{{ l.id }}">Ingrediente</label>
  <select id="ing-{{ l.id }}" name="linea_ingrediente_id" required>
    {% for i in ingredientes %}
    <option value="{{ i.id }}" {{ 'selected' if i.id == l.ingrediente_id else '' }}>{{ i.nombre }}</option>
    {% endfor %}
  </select>

  <label for="lote-{{ l.id }}">Lote del cliente</label>
  <input type="text" id="lote-{{ l.id }}" name="linea_lote_cliente" value="{{ l.lote_cliente or '' }}">

  <label for="venc-{{ l.id }}">Vencimiento</label>
  <input type="date" id="venc-{{ l.id }}" name="linea_fecha_vencimiento"
         value="{{ l.fecha_vencimiento.strftime('%Y-%m-%d') if l.fecha_vencimiento else '' }}">

  <label for="bultos-{{ l.id }}">Bultos</label>
  <input type="text" id="bultos-{{ l.id }}" name="linea_bultos" inputmode="decimal"
         value="{{ l.bultos|map(attribute='peso')|join(', ') }}">

  <label for="total-{{ l.id }}">Peso total</label>
  {#- El value va CRUDO: es un input numérico, no texto para leer. fmt_cant
      metería una coma de miles y rompería el parseo. -#}
  <input type="number" step="0.001" id="total-{{ l.id }}" name="linea_peso_total"
         value="{{ l.peso_total }}">

  <label class="rec-quitar">
    <input type="checkbox" name="linea_quitar" value="1"
           {{ 'disabled' if consumido[l.id] > 0 else '' }}>
    Quitar esta línea
  </label>

  {% if consumido[l.id] > 0 %}
  <p class="maquila-nota-unidad">
    Ya se consumieron {{ consumido[l.id]|fmt_cant(l.ingrediente.unidad) }} de esta línea:
    no se puede quitar ni corregir por debajo de eso.
  </p>
  {% endif %}
</div>
{% endfor %}
```

**Importante sobre `linea_quitar`:** un checkbox no marcado no se envía, así que
las listas paralelas se desalinearían. En el `<script nonce>` de la plantilla,
antes de enviar, poné un `<input type="hidden" name="linea_quitar" value="">`
por cada línea y dejá que el checkbox marcado lo sobreescriba — o construí la
lista en el submit. Sin esto, marcar «quitar» en la segunda línea quita la
primera.

El resto de la estructura:

- Extiende `maquila/base_maquila.html`; `<form method="POST" enctype="multipart/form-data">` con `csrf_token`.
- **Cabecera**: `cliente_id` (select con el actual `selected` — comparando contra `recepcion.cliente_id`, **nunca** con `type=int` en la plantilla), `recibido_en` precargada con `recepcion.recibido_en.strftime('%Y-%m-%d')`, `documento_cliente`, `temperatura`, `transportista`, `notas`.
- **Líneas**: por cada una de `lineas`, un bloque con `linea_id` oculto, el select de ingrediente con el actual seleccionado, `linea_lote_cliente`, `linea_fecha_vencimiento`, `linea_bultos` (los actuales separados por coma), `linea_peso_total` (con `|fmt_cant` **solo para mostrar** el consumido; el `value` del input va crudo), y un checkbox `linea_quitar`. Debajo de cada línea, si `consumido[l.id] > 0`, la leyenda `Ya se consumieron {{ consumido[l.id]|fmt_cant(l.ingrediente.unidad) }} de esta línea`.
  Los cinco campos de cada fila llevan **`<label>` asociado o `aria-label`** — la fila repetible de la pantalla de captura no los tiene y es un hallazgo abierto; no lo repitas.
- Botón «Agregar ingrediente» que clona un `<template>`, con `<script nonce="{{ csp_nonce() }}">`. Las filas nuevas mandan `linea_id` vacío.
- **Fotos**: las existentes como `<img src="{{ url_for('maquila.recepcion_foto', foto_id=f.id) }}">` con un checkbox `borrar_foto` de valor `f.id`; más el input `fotos` con la reducción en navegador de `recepcion_nueva.html`.
- **Firma**: si `recepcion.firma`, mostrar que ya hay una y un botón que revela el canvas; el canvas con **color fijo `#0f172a`**, el botón de borrar **dentro** de `.ops-firma-pad`, y `.has-sign` al primer trazo.
- **Motivo**: un campo `motivo`, con la leyenda de que solo hace falta si cambiás una cantidad.
- Guardar en `.ops-sticky-footer`, con `data-confirm` **en el `<form>`**.

En `templates/maquila/recepcion_detalle.html`, agregar el botón, y filtrar las
líneas anuladas de la tabla (`{% for l in recepcion.lineas if not l.anulada %}`):

```html
<a class="btn btn-primary" href="{{ url_for('maquila.recepcion_editar', recepcion_id=recepcion.id) }}">Editar</a>
```

- [ ] **Step 5: Correr los tests**

Run: `.venv/bin/python -m pytest tests/test_maquila_editar_recepcion.py -q`
Expected: PASS, 20 tests.

- [ ] **Step 6: Commit**

```bash
git add maquila/routes.py templates/maquila/ tests/test_maquila_editar_recepcion.py
git commit -m "feat(maquila): la pantalla para corregir una recepción"
```

---

### Task 4: Que la corrección se lea en el kardex

**Files:**
- Test: `tests/test_maquila_editar_recepcion.py` (ampliar)
- Modify: `maquila/reportes.py` **solo si el test lo exige**

**Interfaces:**
- Consumes: `reportes.kardex(cliente_id, ...)`.

El spec dice que el rastro de la corrección vive **solo en el kardex**. Esta
tarea verifica que efectivamente se lea ahí, con su motivo y su responsable. Si
ya funciona sin tocar nada —que es lo probable, porque `kardex()` lista todo
movimiento del cliente— la tarea es solo el test.

- [ ] **Step 1: Escribir el test**

```python
def test_la_correccion_se_lee_en_el_kardex(app):
    from maquila import servicios, reportes
    with app.app_context():
        rec = _recepcion(100)
        linea = rec.lineas[0]
        servicios.editar_recepcion(
            rec, vendedor_id=IDS['vendedor'], cabecera=_cabecera(rec),
            lineas=[_linea_dict(linea, peso_total=Decimal('90'))],
            motivo='Se tecleó mal en planta')

        filas = reportes.kardex(IDS['cliente'])
        ajustes = [f for f in filas if f['tipo'] == 'ajuste']
        assert len(ajustes) == 1
        assert ajustes[0]['cantidad'] == Decimal('-10.000')
        assert 'Se tecleó mal en planta' in ajustes[0]['motivo']
        assert ajustes[0]['responsable'] == 'Admin'
        assert ajustes[0]['unidad'] == 'kg'
```

- [ ] **Step 2: Correr el test**

Run: `.venv/bin/python -m pytest tests/test_maquila_editar_recepcion.py::test_la_correccion_se_lee_en_el_kardex -q`
Expected: PASS sin tocar `reportes.py`. Si falla, arreglar en `reportes.py` lo
que falte y volver a correr.

- [ ] **Step 3: Commit**

```bash
git add tests/test_maquila_editar_recepcion.py
git commit -m "test(maquila): la corrección de una recepción se lee en el kardex"
```

---

### Task 5: Despliegue

**Files:**
- Consumes: `scripts/maquila_editar_migracion.sql` (Task 1).

- [ ] **Step 1: Correr la suite completa**

Run: `.venv/bin/python -m pytest tests/ -q`
Expected: **1027 + 21 = 1048 passed, 1 skipped, 0 failed**. Cualquier fallo
nuevo es de este trabajo.

- [ ] **Step 2: Verificar que `python app.py` sigue arrancando**

```bash
FLASK_ENV=testing SECRET_KEY=x DATABASE_URL='sqlite:///:memory:' PORT=5099 timeout 20 .venv/bin/python app.py
```
Expected: aparece «Running on», sin ningún `ImportError`.

- [ ] **Step 3: Probar el guion contra Postgres**

Restaurar el esquema en una base local y correr el guion con `ON_ERROR_STOP=1`.
Verificar con `\d recepcion_linea` que la columna quedó. Limpiar después.

- [ ] **Step 4: Migración de producción — la hace JM, en este orden**

```bash
heroku pg:psql --app pesosapp -f scripts/maquila_editar_migracion.sql
```

```bash
git push origin main && git push heroku main
```

```bash
heroku restart --app pesosapp
```

El SQL va **antes** del push: no hay release phase y `alembic_version` está
desacoplado. Al revés, el dyno arranca dando 500 en toda pantalla que lea una
recepción.
