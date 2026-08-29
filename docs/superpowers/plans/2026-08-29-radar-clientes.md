# Radar de clientes — plan de implementación

> **Para agentes:** SUB-SKILL REQUERIDA: usar superpowers:subagent-driven-development
> (recomendado) o superpowers:executing-plans para ejecutar tarea por tarea. Los
> pasos usan casillas (`- [ ]`) para seguimiento.

**Goal:** convertir `/clientes` —hoy un CRUD ordenado por `Cliente.id`— en el
radar que responde «¿a quién le vendo esta semana?», agrupando los clientes por
cuánto se pasaron de su propio ritmo de compra.

**Architecture:** dos funciones PURAS en `app.py` (`_ritmo_cliente` y
`_agrupar_radar`) que no tocan la sesión y se testean con objetos sueltos, más
un armador de contexto que hace **una sola** consulta. La plantilla solo dibuja
lo que recibe. Es el mismo patrón que `_agrupar_tablero`, que ya funciona y ya
tiene tests.

**Tech Stack:** Flask + SQLAlchemy + Jinja2, CSS propio (`gestion.css`), JS
vanilla en el bloque `scripts` de la plantilla, pytest.

**Spec:** `docs/superpowers/specs/2026-08-29-radar-clientes-design.md`

## Global Constraints

- **Una sola consulta** para todo el radar. Nada de recorrer clientes
  preguntando por sus pedidos: hoy la pantalla hace una query y tiene que
  seguir haciendo una.
- **No mostrar importes.** El importe lo calcula Python con `peso_real` y el
  SQL no lo reproduce. Está en el spec y en el spec del tablero.
- **`fecha_pedido` es UTC naive** (`db.DateTime, default=datetime.utcnow`).
  Toda fecha que se compare contra `hoy_local` se convierte antes a la zona del
  negocio con `_fecha_local`. Ver el bloque de Timezones de CLAUDE.md.
- **El ritmo se mide entre FECHAS DISTINTAS con pedido**, nunca entre pedidos:
  entre pedidos, un cliente que carga varios el mismo día da mediana 0.
- La visibilidad no cambia: `super_admin` ve todos, el vendedor ve
  `obtener_clientes_visibles()`. No se inventa regla nueva.
- Ritmo del negocio por defecto: **13 días**. Umbral de atraso: **1,5×**.
  Dormido: **más de 90 días**.
- Todo `<script>` inline lleva `nonce="{{ csp_nonce() }}"` o no ejecuta.
- Correr la suite con `.venv/bin/python -m pytest tests/ -q`, **sin** forzar
  `DATABASE_URL`.

## Estructura de archivos

| Archivo | Responsabilidad |
|---|---|
| `app.py` | `_fecha_local`, `_ritmo_cliente`, `_agrupar_radar`, `_contexto_radar` y el cambio en `mostrar_clientes` |
| `templates/clientes.html` | Secciones del radar en vez de la lista plana; alta/edición/borrado intactos |
| `static/css/gestion.css` | Estilos `.radar-*` |
| `tests/test_radar_clientes.py` | Nuevo. Ritmo, agrupación, contrato de la pantalla |

---

### Task 1: El ritmo de un cliente

**Files:**
- Modify: `app.py` (junto a `_agrupar_tablero`, ~línea 3312)
- Test: `tests/test_radar_clientes.py` (crear)

**Interfaces:**
- Produce: `_fecha_local(dt) -> date`
- Produce: `_ritmo_cliente(fechas: list[date]) -> tuple[int, bool]` — devuelve
  `(dias, es_propio)`. `es_propio=False` significa que se usó el ritmo del
  negocio porque el cliente no tiene historial suficiente.
- Produce: constantes `_RADAR_RITMO_NEGOCIO = 13`, `_RADAR_MIN_INTERVALOS = 2`

- [ ] **Paso 1: escribir los tests que fallan**

```python
# tests/test_radar_clientes.py
"""El radar de clientes: ritmo propio, agrupación y contrato de la pantalla.

Spec: docs/superpowers/specs/2026-08-29-radar-clientes-design.md
"""
import os
from datetime import date, datetime, timedelta, timezone

import pytest

os.environ.setdefault('SECRET_KEY', 'test-secret')
os.environ.setdefault('FLASK_ENV', 'testing')
os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')

from app import _ritmo_cliente, _RADAR_RITMO_NEGOCIO


HOY = date(2026, 8, 29)


def _fechas(*dias_atras):
    return [HOY - timedelta(days=d) for d in dias_atras]


def test_ritmo_propio_con_tres_fechas_o_mas():
    # Compra cada 7 días: 0, 7, 14, 21 atrás → intervalos [7,7,7]
    ritmo, propio = _ritmo_cliente(_fechas(0, 7, 14, 21))
    assert (ritmo, propio) == (7, True)


def test_ritmo_es_la_mediana_no_el_promedio():
    """Un intervalo raro no debe mover el ritmo: por eso mediana."""
    # intervalos [5, 5, 100] → mediana 5, promedio 36,7
    ritmo, propio = _ritmo_cliente(_fechas(0, 5, 10, 110))
    assert (ritmo, propio) == (5, True)


def test_con_menos_de_tres_fechas_usa_el_ritmo_del_negocio():
    for fechas in ([], _fechas(3), _fechas(3, 10)):
        ritmo, propio = _ritmo_cliente(fechas)
        assert ritmo == _RADAR_RITMO_NEGOCIO
        assert propio is False


def test_varios_pedidos_el_mismo_dia_no_dan_ritmo_cero():
    """LA regresión que motivó medir entre fechas y no entre pedidos.

    Best Buy carga varios pedidos la misma fecha. Midiendo entre PEDIDOS su
    mediana daba 0 días, lo que lo marcaba atrasado contra una división por
    cero y encima imprimía «ritmo 0d» en la fila. Midiendo entre fechas
    distintas, su ritmo es real.
    """
    fechas = _fechas(0, 0, 0, 14, 14, 28)     # tres fechas, no seis
    ritmo, propio = _ritmo_cliente(fechas)
    assert ritmo == 14
    assert propio is True
    assert ritmo > 0, 'un ritmo de 0 días divide por cero al calcular el atraso'


def test_el_ritmo_nunca_es_menor_a_un_dia():
    ritmo, _ = _ritmo_cliente(_fechas(0, 1, 2, 3))
    assert ritmo >= 1
```

- [ ] **Paso 2: correr y ver que falla**

Correr: `.venv/bin/python -m pytest tests/test_radar_clientes.py -q`
Esperado: FAIL con `ImportError: cannot import name '_ritmo_cliente'`

- [ ] **Paso 3: implementar**

Agregar en `app.py`, inmediatamente antes de `def _agrupar_tablero`:

```python
# ── El radar de clientes ──────────────────────────────────────────────────────
# Spec: docs/superpowers/specs/2026-08-29-radar-clientes-design.md

_RADAR_RITMO_NEGOCIO = 13    # mediana global entre días distintos con pedido
_RADAR_MIN_INTERVALOS = 2    # o sea, 3 fechas distintas
_RADAR_UMBRAL = 1.5          # se pasó de su ritmo esta cantidad de veces
_RADAR_DORMIDO_DIAS = 90


def _fecha_local(dt):
    """La fecha CALENDARIO de un `fecha_pedido`, en la zona del negocio.

    `Pedido.fecha_pedido` se guarda UTC naive (`default=datetime.utcnow`) y el
    radar cuenta días contra `hoy_local` (America/Curaçao, UTC−4). Sin
    convertir, un pedido cargado a la 01:00 UTC cuenta como del día siguiente y
    corre el ritmo un día. Mismo patrón que `_camaras_con_lectura_hoy`.
    """
    if dt is None:
        return None
    if hasattr(dt, 'hour'):
        return dt.replace(tzinfo=timezone.utc).astimezone(DASHBOARD_TIMEZONE).date()
    return dt


def _ritmo_cliente(fechas, ritmo_negocio=_RADAR_RITMO_NEGOCIO):
    """Cada cuántos días vuelve este cliente, y si el dato es suyo o prestado.

    Mide entre FECHAS DISTINTAS con pedido, no entre pedidos. Hay clientes que
    cargan varios pedidos la misma fecha; entre pedidos su mediana da 0 días,
    lo que los marca atrasados por división contra cero y además imprime
    «ritmo 0d» en la fila. Best Buy era exactamente ese caso y salía como falso
    positivo en la validación contra producción.

    Con menos de tres fechas no hay ritmo que calcular: se devuelve el del
    negocio y `es_propio=False`, para que la fila pueda decir «estimado» en vez
    de fingir una precisión que no existe.
    """
    unicas = sorted({f for f in fechas if f is not None})
    intervalos = sorted((b - a).days for a, b in zip(unicas, unicas[1:]))
    if len(intervalos) < _RADAR_MIN_INTERVALOS:
        return ritmo_negocio, False
    n = len(intervalos)
    medio = n // 2
    mediana = (intervalos[medio] if n % 2
               else (intervalos[medio - 1] + intervalos[medio]) / 2)
    return max(int(round(mediana)), 1), True
```

- [ ] **Paso 4: correr y ver que pasa**

Correr: `.venv/bin/python -m pytest tests/test_radar_clientes.py -q`
Esperado: 5 passed

- [ ] **Paso 5: commit**

```bash
git add app.py tests/test_radar_clientes.py
git commit -m "feat(radar): el ritmo de compra de un cliente, medido entre fechas"
```

---

### Task 2: El reparto en grupos

**Files:**
- Modify: `app.py` (debajo de `_ritmo_cliente`)
- Test: `tests/test_radar_clientes.py`

**Interfaces:**
- Consume: `_ritmo_cliente`, `_RADAR_UMBRAL`, `_RADAR_DORMIDO_DIAS`
- Produce: `_agrupar_radar(filas, hoy_local) -> list[tuple[str, str, list[dict]]]`
  con las CUATRO claves siempre presentes y en este orden: `atrasados`,
  `al_dia`, `dormidos`, `sin_pedidos`. Se devuelven aunque estén vacías —al
  revés que `_agrupar_tablero`— porque «Atrasados: 0» tiene su propio estado
  vacío tranquilo y la plantilla necesita poder distinguirlo.
- Cada fila de entrada es un dict con `id`, `nombre`, `ultimo` (`date` o
  `None`), `n_pedidos` (int), `ritmo` (int), `ritmo_propio` (bool). La función
  le agrega `dias_sin_comprar` y `veces_su_ritmo`.

- [ ] **Paso 1: escribir los tests que fallan**

Agregar a `tests/test_radar_clientes.py`:

```python
from app import _agrupar_radar


def _fila(nombre, dias_desde_ultimo=None, ritmo=10, n_pedidos=5, propio=True):
    return {
        'id': abs(hash(nombre)) % 10000,
        'nombre': nombre,
        'ultimo': None if dias_desde_ultimo is None else HOY - timedelta(days=dias_desde_ultimo),
        'n_pedidos': n_pedidos,
        'ritmo': ritmo,
        'ritmo_propio': propio,
    }


def _grupo(grupos, clave):
    for c, _etiqueta, filas in grupos:
        if c == clave:
            return filas
    raise AssertionError(f'falta el grupo {clave}')


def test_las_cuatro_claves_siempre_estan_y_en_orden():
    grupos = _agrupar_radar([], HOY)
    assert [c for c, _e, _f in grupos] == ['atrasados', 'al_dia', 'dormidos', 'sin_pedidos']


def test_pasado_de_su_ritmo_va_a_atrasados():
    # ritmo 10, lleva 30 días → 3× su ritmo
    grupos = _agrupar_radar([_fila('Arco Iris', 30, ritmo=10)], HOY)
    assert [f['nombre'] for f in _grupo(grupos, 'atrasados')] == ['Arco Iris']
    assert _grupo(grupos, 'al_dia') == []


def test_dentro_de_su_ritmo_va_a_al_dia():
    grupos = _agrupar_radar([_fila('Mangusa', 6, ritmo=7)], HOY)
    assert [f['nombre'] for f in _grupo(grupos, 'al_dia')] == ['Mangusa']
    assert _grupo(grupos, 'atrasados') == []


def test_el_umbral_es_una_vez_y_media():
    """Justo en el límite NO está atrasado; apenas encima, sí."""
    assert _grupo(_agrupar_radar([_fila('Justo', 15, ritmo=10)], HOY), 'atrasados') == []
    assert len(_grupo(_agrupar_radar([_fila('Pasado', 16, ritmo=10)], HOY), 'atrasados')) == 1


def test_mas_de_noventa_dias_es_dormido_y_no_atrasado():
    """Disjuntos: un dormido está pasadísimo de su ritmo, pero va en un grupo solo."""
    grupos = _agrupar_radar([_fila('Everyday', 173, ritmo=10)], HOY)
    assert [f['nombre'] for f in _grupo(grupos, 'dormidos')] == ['Everyday']
    assert _grupo(grupos, 'atrasados') == []


def test_sin_ningun_pedido_va_a_su_propio_grupo():
    grupos = _agrupar_radar([_fila('Alta Nueva', None, n_pedidos=0)], HOY)
    assert [f['nombre'] for f in _grupo(grupos, 'sin_pedidos')] == ['Alta Nueva']
    assert _grupo(grupos, 'dormidos') == [], 'no compró nunca, no está dormido'


def test_atrasados_ordena_por_veces_su_ritmo():
    grupos = _agrupar_radar([
        _fila('poco', 20, ritmo=10),    # 2,0×
        _fila('mucho', 60, ritmo=10),   # 6,0×
        _fila('medio', 40, ritmo=10),   # 4,0×
    ], HOY)
    assert [f['nombre'] for f in _grupo(grupos, 'atrasados')] == ['mucho', 'medio', 'poco']


def test_dormidos_ordena_por_cantidad_de_pedidos():
    """En un dormido importa cuánto se perdió, no cuánto hace."""
    grupos = _agrupar_radar([
        _fila('chico', 120, n_pedidos=2),
        _fila('grande', 100, n_pedidos=40),
    ], HOY)
    assert [f['nombre'] for f in _grupo(grupos, 'dormidos')] == ['grande', 'chico']


def test_sin_pedidos_ordena_alfabetico():
    grupos = _agrupar_radar([
        _fila('Zeta', None, n_pedidos=0),
        _fila('alfa', None, n_pedidos=0),
    ], HOY)
    assert [f['nombre'] for f in _grupo(grupos, 'sin_pedidos')] == ['alfa', 'Zeta']


def test_cada_cliente_cae_en_un_solo_grupo():
    filas = [_fila('a', 30, ritmo=10), _fila('b', 5, ritmo=10),
             _fila('c', 200, ritmo=10), _fila('d', None, n_pedidos=0)]
    grupos = _agrupar_radar(filas, HOY)
    vistos = [f['nombre'] for _c, _e, fs in grupos for f in fs]
    assert sorted(vistos) == ['a', 'b', 'c', 'd']
    assert len(vistos) == len(set(vistos))
```

- [ ] **Paso 2: correr y ver que falla**

Correr: `.venv/bin/python -m pytest tests/test_radar_clientes.py -q`
Esperado: FAIL con `ImportError: cannot import name '_agrupar_radar'`

- [ ] **Paso 3: implementar**

```python
def _agrupar_radar(filas, hoy_local):
    """Reparte los clientes en los cuatro grupos del radar.

    DISJUNTOS: un dormido está pasadísimo de su ritmo, pero aparece sólo en
    Dormidos. Y las cuatro claves se devuelven SIEMPRE, aunque vengan vacías
    —al revés que `_agrupar_tablero`—, porque «Atrasados: 0» no es ruido: es un
    buen resultado y tiene su propio estado vacío tranquilo, y la plantilla
    necesita poder distinguirlo de «no hay clientes».
    """
    atrasados, al_dia, dormidos, sin_pedidos = [], [], [], []

    for fila in filas:
        if not fila.get('n_pedidos') or not fila.get('ultimo'):
            sin_pedidos.append(fila)
            continue

        dias = (hoy_local - fila['ultimo']).days
        ritmo = max(fila.get('ritmo') or _RADAR_RITMO_NEGOCIO, 1)
        fila['dias_sin_comprar'] = dias
        fila['veces_su_ritmo'] = round(dias / ritmo, 1)

        if dias > _RADAR_DORMIDO_DIAS:
            dormidos.append(fila)
        elif dias > _RADAR_UMBRAL * ritmo:
            atrasados.append(fila)
        else:
            al_dia.append(fila)

    atrasados.sort(key=lambda f: f['veces_su_ritmo'], reverse=True)
    al_dia.sort(key=lambda f: f['veces_su_ritmo'], reverse=True)
    dormidos.sort(key=lambda f: (f['n_pedidos'], -f['dias_sin_comprar']), reverse=True)
    sin_pedidos.sort(key=lambda f: (f['nombre'] or '').lower())

    return [
        ('atrasados', 'Atrasados', atrasados),
        ('al_dia', 'Al día', al_dia),
        ('dormidos', 'Dormidos', dormidos),
        ('sin_pedidos', 'Nunca compraron', sin_pedidos),
    ]
```

- [ ] **Paso 4: correr y ver que pasa**

Correr: `.venv/bin/python -m pytest tests/test_radar_clientes.py -q`
Esperado: 15 passed

- [ ] **Paso 5: commit**

```bash
git add app.py tests/test_radar_clientes.py
git commit -m "feat(radar): reparto en atrasados / al día / dormidos / sin pedidos"
```

---

### Task 3: El contexto, en una sola consulta

**Files:**
- Modify: `app.py` (`_contexto_radar` nueva, y `mostrar_clientes` ~línea 10276)
- Test: `tests/test_radar_clientes.py`

**Interfaces:**
- Consume: `_fecha_local`, `_ritmo_cliente`, `_agrupar_radar`
- Produce: `_contexto_radar(clientes, hoy_local) -> list[tuple[str, str, list[dict]]]`
- `mostrar_clientes` pasa a la plantilla `grupos=` además de `clientes=` (que se
  conserva porque el JS de alta y borrado la sigue usando).

- [ ] **Paso 1: escribir los tests que fallan**

```python
def test_el_radar_hace_una_sola_consulta_de_pedidos(logged_client, app):
    """Con 62 clientes, una query por cliente serían 62 viajes a la base."""
    from sqlalchemy import event
    from app import db

    consultas = []

    def espiar(conn, cursor, statement, params, context, many):
        if 'pedido' in statement.lower():
            consultas.append(statement)

    with app.app_context():
        event.listen(db.engine, 'before_cursor_execute', espiar)
        try:
            resp = logged_client.get('/clientes')
        finally:
            event.remove(db.engine, 'before_cursor_execute', espiar)

    assert resp.status_code == 200
    assert len(consultas) <= 1, (
        f'el radar hizo {len(consultas)} consultas a pedido: '
        'tiene que ser una sola agregada'
    )


def test_fecha_pedido_se_cuenta_en_la_zona_del_negocio(app):
    """`fecha_pedido` es UTC naive; el radar cuenta días calendario locales.

    Un pedido a las 02:00 UTC del día 10 es todavía el día 9 en Curaçao
    (UTC−4). Contarlo como del 10 corre el ritmo un día entero.
    """
    from app import _fecha_local
    from datetime import datetime
    assert _fecha_local(datetime(2026, 8, 10, 2, 0)) == date(2026, 8, 9)
    assert _fecha_local(datetime(2026, 8, 10, 12, 0)) == date(2026, 8, 10)
```

Las fixtures `app` y `logged_client` se copian tal cual de
`tests/test_pedidos_lista_acciones.py` (líneas 32-65), agregando un `Cliente`
con pedidos para que el radar tenga algo que agrupar.

- [ ] **Paso 2: correr y ver que falla**

Correr: `.venv/bin/python -m pytest tests/test_radar_clientes.py -q`
Esperado: FAIL — `_fecha_local` no está exportada o `/clientes` hace N consultas

- [ ] **Paso 3: implementar**

```python
def _contexto_radar(clientes, hoy_local):
    """Arma las filas del radar con UNA consulta de pedidos.

    Trae `(cliente_id, fecha_pedido)` de todos los clientes visibles de una vez
    y agrupa en Python. La mediana se calcula acá y no en SQL a propósito:
    `percentile_cont` no existe en SQLite y los tests corren sobre SQLite, así
    que la regla viviría sin cobertura justo donde es más fácil equivocarse.
    """
    por_id = {c.id: c for c in clientes}
    if not por_id:
        return _agrupar_radar([], hoy_local)

    fechas_por_cliente = defaultdict(list)
    filas = (db.session.query(Pedido.cliente_id, Pedido.fecha_pedido)
             .filter(Pedido.cliente_id.in_(list(por_id)))
             .all())
    for cliente_id, fecha in filas:
        local = _fecha_local(fecha)
        if local is not None:
            fechas_por_cliente[cliente_id].append(local)

    radar = []
    for cliente_id, cliente in por_id.items():
        fechas = fechas_por_cliente.get(cliente_id, [])
        ritmo, propio = _ritmo_cliente(fechas)
        radar.append({
            'id': cliente_id,
            'nombre': cliente.nombre,
            'moneda': cliente.moneda,
            'qbo_id': cliente.qbo_id,
            'ultimo': max(fechas) if fechas else None,
            'n_pedidos': len(fechas),
            'ritmo': ritmo,
            'ritmo_propio': propio,
        })
    return _agrupar_radar(radar, hoy_local)
```

`n_pedidos` cuenta **filas de pedido**, no fechas distintas: es «cuántas veces
me compró», que es lo que la fila promete.

Agregar `from collections import defaultdict` arriba con los demás imports:
**verificado que hoy NO está importado en `app.py`**.

Y en `mostrar_clientes`, reemplazar el `return`:

```python
    hoy_local = datetime.now(DASHBOARD_TIMEZONE).date()
    return render_template(
        'clientes.html',
        clientes=clientes,
        grupos=_contexto_radar(clientes, hoy_local),
    )
```

- [ ] **Paso 4: correr y ver que pasa**

Correr: `.venv/bin/python -m pytest tests/test_radar_clientes.py -q`
Esperado: 17 passed

- [ ] **Paso 5: commit**

```bash
git add app.py tests/test_radar_clientes.py
git commit -m "feat(radar): contexto del radar en una sola consulta, en hora local"
```

---

### Task 4: La pantalla

**Files:**
- Modify: `templates/clientes.html` (el `<ul id="lista-clientes">`, líneas 58-86)
- Test: `tests/test_radar_clientes.py`

**Interfaces:**
- Consume: `grupos` del contexto
- Produce: markup con `data-radar-grupo="<clave>"` por sección y
  `.gestion-row.radar-row` por cliente, conservando `id="cliente-{{ id }}"` y
  `data-buscar` porque el JS de borrado y de búsqueda dependen de los dos.

**La fila REUTILIZA el patrón gestión, no lo reemplaza.** `.gestion-row`,
`.gestion-row-main`, `.gestion-row-sub` y `.gestion-row-actions` ya existen en
`gestion.css:146-190` con la forma exacta que el radar necesita (flex, contenido
+ acciones, y una guarda `[hidden]`). Escribir una fila nueva desde cero sería
duplicar layout y además rompería
`tests/test_gestion_ui.py::test_clientes_patron_gestion`, que afirma
`gestion-row` como contrato del sistema de diseño — y lo afirma con razón: esta
pantalla sigue siendo una pantalla de gestión. `.radar-row` es sólo el
modificador.

- [ ] **Paso 1: escribir los tests que fallan**

```python
def test_la_pantalla_dibuja_las_secciones_del_radar(logged_client):
    html = logged_client.get('/clientes').get_data(as_text=True)
    for clave in ['atrasados', 'al_dia', 'dormidos', 'sin_pedidos']:
        assert f'data-radar-grupo="{clave}"' in html


def test_la_fila_dice_dias_ritmo_y_pedidos(logged_client):
    html = logged_client.get('/clientes').get_data(as_text=True)
    assert 'días sin comprar' in html
    assert 'su ritmo' in html


def test_el_ritmo_prestado_se_declara_estimado(logged_client, app):
    """Un cliente con un solo pedido no tiene ritmo propio y la fila lo dice."""
    html = logged_client.get('/clientes').get_data(as_text=True)
    assert 'estimado' in html


def test_la_accion_principal_es_crear_un_pedido_para_ese_cliente(logged_client, app):
    with app.app_context():
        from app import Cliente
        cid = Cliente.query.first().id
    html = logged_client.get('/clientes').get_data(as_text=True)
    assert f'/pedidos/nuevo?cliente={cid}' in html


def test_sigue_estando_el_id_de_fila_que_usa_el_borrado(logged_client, app):
    """`eliminar-cliente` hace getElementById('cliente-'+id) para sacar la fila."""
    with app.app_context():
        from app import Cliente
        cid = Cliente.query.first().id
    html = logged_client.get('/clientes').get_data(as_text=True)
    assert f'id="cliente-{cid}"' in html
    assert 'data-buscar=' in html, 'la búsqueda client-side depende de este atributo'


def test_sin_atrasados_la_pantalla_lo_dice_con_calma(logged_client, app):
    """El vacío de «Atrasados» es un buen resultado, no una pantalla rota."""
    with app.app_context():
        from app import Pedido, db as _db
        _db.session.query(Pedido).delete()
        _db.session.commit()
    html = logged_client.get('/clientes').get_data(as_text=True)
    assert 'Todos al día' in html
```

- [ ] **Paso 2: correr y ver que falla**

Correr: `.venv/bin/python -m pytest tests/test_radar_clientes.py -q`
Esperado: FAIL — no existe `data-radar-grupo`

- [ ] **Paso 3: implementar**

Reemplazar el bloque `<ul id="lista-clientes" class="gestion-list">…</ul>`
(líneas 58-86) por:

```jinja
  <ul id="lista-clientes" class="gestion-list radar-list">
    {% for clave, etiqueta, filas in grupos %}
      {% if filas or clave == 'atrasados' %}
      <li class="radar-seccion" data-radar-grupo="{{ clave }}">
        {% if clave in ['dormidos', 'sin_pedidos'] %}
        <button type="button" class="radar-titulo radar-titulo-plegable"
                aria-expanded="false" aria-controls="radar-{{ clave }}">
          <i class="fas fa-chevron-right radar-chevron" aria-hidden="true"></i>
          {{ etiqueta }} <span class="radar-cuenta">{{ filas|length }}</span>
        </button>
        {% else %}
        <h2 class="radar-titulo">
          {% if clave == 'atrasados' %}<i class="fas fa-triangle-exclamation" aria-hidden="true"></i>{% endif %}
          {{ etiqueta }} <span class="radar-cuenta">{{ filas|length }}</span>
        </h2>
        {% endif %}

        {# «Atrasados» vacío es un buen resultado y se dice así, tranquilo: la
           pantalla no puede parecer rota cuando el trabajo está al día. #}
        {% if clave == 'atrasados' and not filas %}
          <p class="radar-vacio">Todos al día. Nadie se pasó de su ritmo.</p>
        {% else %}
        <ul class="radar-grupo" id="radar-{{ clave }}"
            {% if clave in ['dormidos', 'sin_pedidos'] %}hidden{% endif %}>
          {% for f in filas %}
          <li class="gestion-row radar-row" id="cliente-{{ f.id }}" data-buscar="{{ f.nombre|lower }}">
            <div class="gestion-row-main">
              <span class="gestion-row-name">{{ f.nombre }}</span>
              <span class="gestion-row-sub radar-meta">
                {% if f.n_pedidos %}
                  {{ f.dias_sin_comprar }} días sin comprar
                  · su ritmo: {{ f.ritmo }} d{% if not f.ritmo_propio %} <em>(estimado)</em>{% endif %}
                  · {{ f.n_pedidos }} pedido{{ 's' if f.n_pedidos != 1 }}
                {% else %}
                  Sin pedidos todavía
                {% endif %}
              </span>
            </div>
            <div class="gestion-row-actions">
              <a class="radar-action-main" href="{{ url_for('nuevo_pedido', cliente=f.id) }}">
                <i class="fas fa-plus" aria-hidden="true"></i> Pedido
              </a>
              <a href="{{ url_for('editar_cliente', cliente_id=f.id) }}"
                 class="gestion-icon-btn gestion-icon-edit"
                 aria-label="Editar {{ f.nombre }}"><i class="fas fa-pen" aria-hidden="true"></i></a>
              <button type="button" class="gestion-icon-btn gestion-icon-delete eliminar-cliente"
                      data-id="{{ f.id }}"
                      aria-label="Eliminar {{ f.nombre }}"><i class="fas fa-trash" aria-hidden="true"></i></button>
            </div>
          </li>
          {% endfor %}
        </ul>
        {% endif %}
      </li>
      {% endif %}
    {% else %}
    <li class="gestion-empty">No hay clientes registrados todavía.</li>
    {% endfor %}
  </ul>
```

`url_for('nuevo_pedido', cliente=f.id)` genera `/pedidos/nuevo?cliente=<id>`.
Verificado: `nuevo_pedido` lo lee en `app.py:6751`
(`request.args.get('cliente', type=int)`) y con él salta directo al paso de
productos con el habitual precargado.

- [ ] **Paso 4: correr y ver que pasa**

Correr: `.venv/bin/python -m pytest tests/test_radar_clientes.py -q`
Esperado: 23 passed

- [ ] **Paso 5: commit**

```bash
git add templates/clientes.html tests/test_radar_clientes.py
git commit -m "feat(radar): /clientes muestra el radar en vez del CRUD por id"
```

---

### Task 5: Plegado, búsqueda y estilos

**Files:**
- Modify: `templates/clientes.html` (bloque `scripts`, ~línea 122)
- Modify: `static/css/gestion.css` (al final)
- Test: `tests/test_radar_clientes.py`

**Interfaces:**
- Consume: `.radar-seccion`, `.radar-titulo-plegable`, `.radar-row`

- [ ] **Paso 1: escribir el test que falla**

```python
def test_la_busqueda_esconde_las_secciones_que_quedan_vacias(logged_client):
    """Si «Mangusa» sólo está en «Al día», no puede quedar un encabezado
    «Atrasados 5» encima de cero filas: la pantalla estaría mintiendo."""
    html = logged_client.get('/clientes').get_data(as_text=True)
    assert 'radar-seccion' in html
    assert 'seccionesVacias' in html, (
        'el JS de búsqueda tiene que replegar las secciones sin coincidencias'
    )
```

- [ ] **Paso 2: correr y ver que falla**

Correr: `.venv/bin/python -m pytest tests/test_radar_clientes.py -q -k busqueda`
Esperado: FAIL — no existe `seccionesVacias`

- [ ] **Paso 3: implementar el JS**

Reemplazar el manejador de búsqueda existente (el bloque
`document.getElementById('buscar-cliente').addEventListener('input', …)`) por:

```javascript
  // Búsqueda client-side. Ahora hay secciones, así que esconder filas no
  // alcanza: una sección cuyo encabezado dice «Atrasados 5» encima de cero
  // filas visibles estaría afirmando algo falso.
  function seccionesVacias() {
    document.querySelectorAll('.radar-seccion').forEach(function (sec) {
      var visibles = sec.querySelectorAll('.radar-row:not([hidden])').length;
      sec.hidden = visibles === 0;
    });
  }

  document.getElementById('buscar-cliente').addEventListener('input', function () {
    var q = this.value.trim().toLowerCase();
    document.querySelectorAll('#lista-clientes .radar-row').forEach(function (row) {
      row.hidden = !!q && row.dataset.buscar.indexOf(q) === -1;
    });
    // Buscando se abren los grupos plegados: si el cliente que buscás está en
    // «Dormidos», encontrarlo y no verlo es peor que no encontrarlo.
    document.querySelectorAll('.radar-grupo').forEach(function (g) {
      if (q) g.hidden = false;
    });
    document.querySelectorAll('.radar-titulo-plegable').forEach(function (b) {
      if (q) b.setAttribute('aria-expanded', 'true');
    });
    seccionesVacias();
  });

  // Plegado de «Dormidos» y «Nunca compraron»
  document.getElementById('lista-clientes').addEventListener('click', function (e) {
    var btn = e.target.closest('.radar-titulo-plegable');
    if (!btn) return;
    var grupo = document.getElementById(btn.getAttribute('aria-controls'));
    if (!grupo) return;
    var abrir = grupo.hidden;
    grupo.hidden = !abrir;
    btn.setAttribute('aria-expanded', abrir ? 'true' : 'false');
  });
```

**OJO:** el borrado usa `document.getElementById('lista-clientes')
.addEventListener('click', …)` con `e.target.closest('.eliminar-cliente')`. El
manejador de plegado va en el MISMO elemento; los dos hacen `closest` sobre
clases distintas y conviven, pero hay que dejar los dos listeners, no
reemplazar uno por el otro.

- [ ] **Paso 4: los estilos**

Agregar al final de `static/css/gestion.css`:

```css
/* ── El radar de clientes ────────────────────────────────────────────────────
   Spec: docs/superpowers/specs/2026-08-29-radar-clientes-design.md
   Colores explícitos y no heredados: esta pantalla ya sufrió el bleed de
   `label { color:#f1f5f9 !important }` (ver operaciones-css-bleed). */
.radar-list { list-style: none; padding: 0; margin: 0; }
.radar-seccion { margin-bottom: 20px; }

.radar-titulo {
  display: flex; align-items: center; gap: 8px;
  margin: 0 0 8px; padding: 0;
  font-size: 0.8rem; font-weight: 800; letter-spacing: 0.06em;
  text-transform: uppercase; color: #475569;
  background: none; border: 0; width: 100%; text-align: left;
}
.radar-titulo-plegable { min-height: 44px; cursor: pointer; }
.radar-titulo-plegable[aria-expanded="true"] .radar-chevron { transform: rotate(90deg); }
.radar-chevron { transition: transform 0.15s ease; }
.radar-cuenta {
  font-weight: 700; color: #64748b;
  background: #f1f5f9; border-radius: 99px; padding: 1px 8px; font-size: 0.75rem;
}
[data-radar-grupo="atrasados"] .radar-titulo { color: #b45309; }
[data-radar-grupo="atrasados"] .radar-cuenta { color: #92400e; background: #fef3c7; }

.radar-grupo { list-style: none; padding: 0; margin: 0; }

/* La FILA no se redefine: `.gestion-row`, `.gestion-row-main`,
   `.gestion-row-sub` y `.gestion-row-actions` ya traen la forma exacta
   (gestion.css:146-190), incluida la guarda `[hidden]`. Acá va sólo lo que el
   radar agrega encima.
   #475569 sobre #ffffff = 7,58:1. El #94a3b8 que suele aparecer en estas metas
   da 2,56:1, y esta pantalla se usa a plena luz, en la calle. */
.radar-meta { color: #475569; }
.radar-meta em { font-style: normal; color: #64748b; }

.radar-action-main {
  display: inline-flex; align-items: center; gap: 6px;
  min-height: 44px; padding: 0 14px; border-radius: 10px;
  background: #e0e7ff; color: #4338ca;        /* 6,41:1 */
  font-size: 0.85rem; font-weight: 700; text-decoration: none;
}
.radar-action-main:hover { background: #c7d2fe; }
.radar-vacio {
  margin: 0; padding: 14px 12px; border-radius: 12px;
  background: #f8fafc; color: #475569; font-size: 0.9rem;
}
```

- [ ] **Paso 5: correr la suite entera**

Correr: `.venv/bin/python -m pytest tests/ -q`
Esperado: todo verde.

El test acoplado al markup de esta pantalla es
`tests/test_gestion_ui.py::test_clientes_patron_gestion`, que afirma
`id="buscar-cliente"`, `id="crear-cliente-card"`, `id="btn-nuevo-cliente"`,
`id="form-cliente"`, el nombre del cliente semilla y `gestion-row`. **Con el
markup de la Task 4 los seis siguen siendo ciertos**, porque el alta no se toca
y la fila conserva `gestion-row`. Si aun así falla, LEERLO antes de tocarlo: que
ese test se ponga rojo significa que se rompió el patrón de gestión, no que el
test esté viejo.

- [ ] **Paso 6: commit**

```bash
git add templates/clientes.html static/css/gestion.css tests/test_radar_clientes.py
git commit -m "feat(radar): plegado accesible, búsqueda por sección y estilos"
```

---

### Task 6: Verificación en el navegador

**Files:** ninguno por defecto; se corrigen los que la medición señale.

- [ ] **Paso 1: levantar la app local**

```bash
export SECRET_KEY=preview-secret FLASK_ENV=preview \
       DATABASE_URL="sqlite:///$(pwd)/instance/local.db"
.venv/bin/python -c "from app import app; app.run(host='127.0.0.1', port=5002)"
```

Si da 500 por columnas faltantes, sincronizar el esquema local antes (patrón
anotado en la memoria del proyecto: comparar `db.metadata.sorted_tables` contra
`PRAGMA table_info` y hacer los `ALTER` que falten).

- [ ] **Paso 2: medir el RENDER, no las reglas**

Con Playwright, en `/clientes`, a 390px y a 1280px:

1. **Contraste** de `.radar-row-name`, `.radar-row-meta`, `.radar-titulo` y
   `.radar-action-main`, componiendo el fondo contra los ancestros y contando
   los degradados como fondo (un `background-image` pinta por encima del
   `background-color`; medir sólo `backgroundColor` da falsos «blanco sobre
   blanco»). Piso: 4,5:1, o 3:1 desde 18px.
2. **Área táctil** de `.radar-action-main`, del icono de editar, del de borrar y
   del encabezado plegable: `getBoundingClientRect()` ≥ 44×44.
3. **Plegado con teclado:** tabular hasta «Dormidos», Enter, y comprobar que
   `aria-expanded` pasa a `"true"` **y** que las filas se ven de verdad
   (`offsetParent !== null`), no sólo que cambió el atributo.
4. **Búsqueda:** teclear el nombre de un cliente dormido y comprobar que la fila
   queda visible y que ninguna sección muestra encabezado con cero filas.

- [ ] **Paso 3: arreglar lo que la medición muestre, en un lote**

- [ ] **Paso 4: confirmar con una segunda medición y parar**

- [ ] **Paso 5: commit**

```bash
git add -A
git commit -m "fix(radar): correcciones de la verificación en el navegador"
```

---

## Notas para quien ejecute

- **No deducir el estado de una regla CSS ni de una propiedad que vos mismo
  seteaste.** En este repo ya pasó tres veces: `[hidden]` perdiendo contra un
  `display` de autor, un `position: sticky` inerte porque el ancestro no
  scrollea, y un `color` pisado mientras `-webkit-text-fill-color` seguía
  pintando. Medir lo que se ve.
- El bleed de modo oscuro **ya no existe**: los `@media (prefers-color-scheme:
  dark)` se eliminaron el 2026-08-29. Si aparece un color raro, no es eso;
  buscar una regla con `!important` que gane por especificidad propia.
- `main.app-content label { color: #475569 !important }` de `app-mobile.css`
  alcanza a cualquier `<label>` de esta pantalla. El radar no usa `label`, pero
  el formulario de alta que sigue arriba sí.
