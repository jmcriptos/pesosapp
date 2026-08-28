# Tablero de entregas en /pedidos — Plan de implementación

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Que `/pedidos` deje de ser una lista de 942 pedidos y pase a ser un tablero de cuatro grupos por fecha de entrega, conservando la lista plana bajo parámetros de URL.

**Architecture:** La ruta `lista_pedidos` decide el modo por la presencia de parámetros reconocidos. En modo tablero consulta lo no facturado más las entregas de hoy, lo reparte con una función pura en cuatro grupos y renderiza un parcial nuevo. En modo lista no cambia nada de lo que ya existe. La búsqueda es la puerta del archivo: escribir manda parámetros y por lo tanto cambia de modo.

**Tech Stack:** Flask + SQLAlchemy + Jinja2, JS sin framework, pytest.

**Spec:** `docs/superpowers/specs/2026-08-28-pedidos-tablero-design.md`

## Global Constraints

- `hoy_local` es el día en `DASHBOARD_TIMEZONE` (America/Curaçao, UTC−4), nunca `date.today()`.
- Los cuatro grupos son **disjuntos**: un pedido no puede aparecer dos veces.
- Un grupo vacío **no se dibuja** — ni encabezado ni cero.
- Todo enlace existente a `/pedidos?...` sigue funcionando y cae en modo lista. En particular `/pedidos?estado=pendiente`, del aviso del dashboard (`app.py:1915`).
- Correr la suite con `.venv/bin/python -m pytest tests/ -q`, **sin** forzar `DATABASE_URL`.
- `base.min.js` es lo que carga `base.html`: si se toca `base.js`, regenerar con `cp static/js/base.js static/js/base.min.js`.
- Verificación visual: medir **el render** (`getBoundingClientRect().height`, `getComputedStyle`), nunca la propiedad que el propio código acaba de escribir.

## Decisión que el plan agrega al spec

El spec no dice qué pasa con el `estado` por defecto en modo lista. Hoy es `por_preparar`, y eso se vuelve incorrecto en cuanto existe el tablero: si alguien busca «Mangusa» desde el tablero, la búsqueda saldría filtrada a lo no facturado y **no encontraría nada del archivo**, que es justamente lo que se estaba buscando.

**El default de `estado` en modo lista pasa a `todos`.** El tablero se queda con el trabajo del día; la lista es el archivo y busca en todo. Esto se implementa en la Tarea 2 y se prueba explícitamente.

---

### Task 1: La función que reparte los grupos

Función pura, sin base de datos ni HTTP, para poder probar las nueve situaciones de borde de un tirón.

**Files:**
- Modify: `app.py` (agregar junto a `_volver_a`, cerca de la línea 3287)
- Test: `tests/test_pedidos_tablero.py` (crear)

**Interfaces:**
- Produces: `_agrupar_tablero(pedidos, hoy_local) -> list[tuple[str, str, list[Pedido]]]` — lista de `(clave, etiqueta, pedidos)` **omitiendo los grupos vacíos**. Claves: `atrasados`, `hoy`, `proximos`, `sin_fecha`.

- [ ] **Step 1: Escribir el test que falla**

Crear `tests/test_pedidos_tablero.py`:

```python
# tests/test_pedidos_tablero.py
"""El tablero de entregas: reparto en grupos y contrato de modos.

Spec: docs/superpowers/specs/2026-08-28-pedidos-tablero-design.md
"""
import os
from datetime import date, timedelta

import pytest

os.environ.setdefault('SECRET_KEY', 'test-secret')
os.environ.setdefault('FLASK_ENV', 'testing')
os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')

from app import _agrupar_tablero, Pedido


HOY = date(2026, 8, 28)


def _p(estado, dias=None, id=1):
    """Pedido suelto, sin sesión: `_agrupar_tablero` es pura."""
    return Pedido(
        id=id,
        estado=estado,
        fecha_entrega=None if dias is None else HOY + timedelta(days=dias),
    )


def _claves(grupos):
    return [clave for clave, _etiqueta, _pedidos in grupos]


def _pedidos_de(grupos, clave):
    for c, _etiqueta, pedidos in grupos:
        if c == clave:
            return pedidos
    return []


def test_atrasado_sin_facturar_va_a_atrasados():
    grupos = _agrupar_tablero([_p('pendiente', dias=-3)], HOY)
    assert _claves(grupos) == ['atrasados']


def test_entrega_hoy_va_a_hoy_en_cualquier_estado():
    grupos = _agrupar_tablero(
        [_p('pendiente', dias=0, id=1),
         _p('preparado', dias=0, id=2),
         _p('facturado', dias=0, id=3)],
        HOY,
    )
    assert _claves(grupos) == ['hoy']
    assert len(_pedidos_de(grupos, 'hoy')) == 3


def test_el_facturado_de_hoy_no_se_cuela_en_otro_grupo():
    """Decisión del spec: se queda en «Hoy», marcado hecho. En ningún otro."""
    grupos = _agrupar_tablero([_p('facturado', dias=0)], HOY)
    assert _claves(grupos) == ['hoy']


def test_entrega_futura_sin_facturar_va_a_proximos():
    grupos = _agrupar_tablero([_p('preparado', dias=5)], HOY)
    assert _claves(grupos) == ['proximos']


def test_sin_facturar_y_sin_fecha_nunca_es_invisible():
    """El test que más importa: si falla, la pantalla esconde trabajo."""
    grupos = _agrupar_tablero([_p('pendiente', dias=None)], HOY)
    assert _claves(grupos) == ['sin_fecha']
    assert len(_pedidos_de(grupos, 'sin_fecha')) == 1


def test_el_archivo_no_entra_al_tablero():
    """Facturado que no se entrega hoy: ni atrasados, ni próximos, ni sin fecha."""
    grupos = _agrupar_tablero(
        [_p('facturado', dias=-30, id=1),
         _p('facturado', dias=None, id=2),
         _p('facturado', dias=9, id=3)],
        HOY,
    )
    assert grupos == []


def test_los_grupos_vacios_no_se_dibujan():
    grupos = _agrupar_tablero([_p('pendiente', dias=0)], HOY)
    assert _claves(grupos) == ['hoy'], 'no debe aparecer ningún grupo vacío'


def test_los_grupos_van_en_orden_de_urgencia():
    grupos = _agrupar_tablero(
        [_p('pendiente', dias=4, id=1),
         _p('pendiente', dias=None, id=2),
         _p('pendiente', dias=0, id=3),
         _p('pendiente', dias=-2, id=4)],
        HOY,
    )
    assert _claves(grupos) == ['atrasados', 'hoy', 'proximos', 'sin_fecha']


def test_ningun_pedido_aparece_dos_veces():
    pedidos = [_p('pendiente', dias=-1, id=1), _p('facturado', dias=0, id=2),
               _p('preparado', dias=3, id=3), _p('pendiente', dias=None, id=4)]
    grupos = _agrupar_tablero(pedidos, HOY)
    vistos = [p.id for _c, _e, ps in grupos for p in ps]
    assert sorted(vistos) == [1, 2, 3, 4]
    assert len(vistos) == len(set(vistos)), 'un pedido cayó en dos grupos'
```

- [ ] **Step 2: Correr el test y verificar que falla**

Run: `.venv/bin/python -m pytest tests/test_pedidos_tablero.py -q`
Expected: FAIL con `ImportError: cannot import name '_agrupar_tablero' from 'app'`

- [ ] **Step 3: Implementar la función**

En `app.py`, inmediatamente después de `_volver_a` (que termina cerca de la línea 3310):

```python
def _agrupar_tablero(pedidos, hoy_local):
    """Reparte los pedidos del tablero en los cuatro grupos del spec.

    Grupos DISJUNTOS y en orden de urgencia. Devuelve
    `[(clave, etiqueta, pedidos), ...]` omitiendo los vacíos, para que la
    plantilla no tenga que decidir qué dibujar: un encabezado «Atrasados 0»
    es ruido, y una pantalla que afirma cosas que no son enseña a
    desconfiar de ella.

    «Hoy» lleva CUALQUIER estado, facturados incluidos: si desaparecieran al
    facturarse, el tablero se vaciaría a media tarde y se perdería la otra
    mitad del trabajo, que es ver si el día cerró completo.

    «Sin fecha» es una guardia. Hoy estaría siempre vacío —el formulario
    carga `fecha_entrega` en el 100% de los pedidos desde el 16/08— pero un
    pedido sin facturar y sin fecha no entraría en ningún otro grupo y sería
    trabajo INVISIBLE, que es el peor fallo posible en una herramienta
    operativa.
    """
    atrasados, hoy, proximos, sin_fecha = [], [], [], []

    for pedido in pedidos:
        entrega = pedido.fecha_entrega
        if entrega == hoy_local:
            hoy.append(pedido)
        elif pedido.estado == 'facturado':
            # Facturado que no se entrega hoy: es archivo, no tablero.
            continue
        elif entrega is None:
            sin_fecha.append(pedido)
        elif entrega < hoy_local:
            atrasados.append(pedido)
        else:
            proximos.append(pedido)

    grupos = [
        ('atrasados', 'Atrasados', atrasados),
        ('hoy', 'Hoy', hoy),
        ('proximos', 'Próximos', proximos),
        ('sin_fecha', 'Sin fecha de entrega', sin_fecha),
    ]
    return [g for g in grupos if g[2]]
```

- [ ] **Step 4: Correr el test y verificar que pasa**

Run: `.venv/bin/python -m pytest tests/test_pedidos_tablero.py -q`
Expected: PASS, 9 tests

- [ ] **Step 5: Commit**

```bash
git add app.py tests/test_pedidos_tablero.py
git commit -m "feat(pedidos): la función que reparte el tablero en cuatro grupos"
```

---

### Task 2: El modo lo decide la URL

**Files:**
- Modify: `app.py` — `lista_pedidos` (desde línea 5812)
- Modify: `templates/pedidos.html` — envolver la lista y llamar al tablero
- Create: `templates/_pedidos_tablero.html` — parcial mínimo (la versión completa es la Tarea 3)
- Modify: `tests/test_pedidos_lista_entrega.py` — apuntar a `?estado=todos`
- Test: `tests/test_pedidos_tablero.py` (agregar)

**Interfaces:**
- Consumes: `_agrupar_tablero(pedidos, hoy_local)` de la Tarea 1.
- Produces: la plantilla recibe `grupos` (lista de tuplas) y `modo_tablero` (bool). `grupos` es `None` en modo lista.

- [ ] **Step 1: Escribir los tests que fallan**

Agregar al final de `tests/test_pedidos_tablero.py`:

```python
# ── Contrato de modos ────────────────────────────────────────────────────────

@pytest.fixture
def app():
    from app import app as flask_app, db as _db
    flask_app.config.update(
        TESTING=True, WTF_CSRF_ENABLED=False,
        SQLALCHEMY_DATABASE_URI='sqlite:///:memory:',
    )
    with flask_app.app_context():
        _db.create_all()
        from app import Rol, Territorio, Vendedor, Cliente
        rol = Rol(nombre='super_admin', descripcion='Admin')
        _db.session.add(rol)
        territorio = Territorio(nombre='test', descripcion='Test')
        _db.session.add(territorio)
        _db.session.flush()
        vendedor = Vendedor(
            username='admin', email='admin@test.com', nombre_completo='Admin',
            rol_id=rol.id, territorio_id=territorio.id, activo=True,
        )
        vendedor.set_password('testpass')
        _db.session.add(vendedor)
        _db.session.add(Cliente(nombre='Cliente Uno', territorio_id=territorio.id))
        _db.session.commit()
        yield flask_app
        _db.drop_all()


@pytest.fixture
def logged_client(app):
    client = app.test_client()
    client.post('/login', data={'username': 'admin', 'password': 'testpass'},
                follow_redirects=True)
    return client


def _crear(estado, dias=None):
    from app import Pedido, Cliente, db as _db, DASHBOARD_TIMEZONE
    from datetime import datetime
    hoy = datetime.now(DASHBOARD_TIMEZONE).date()
    p = Pedido(cliente_id=Cliente.query.first().id, estado=estado)
    if dias is not None:
        p.fecha_entrega = hoy + timedelta(days=dias)
    _db.session.add(p)
    _db.session.commit()
    return p


def test_pedidos_sin_parametros_es_tablero(logged_client):
    _crear('pendiente', dias=0)
    html = logged_client.get('/pedidos').get_data(as_text=True)
    assert 'data-tablero="1"' in html, 'no se renderizó el tablero'
    assert 'pagination-info-mobile' not in html, 'el tablero no debe paginar'


def test_un_parametro_reconocido_devuelve_la_lista(logged_client):
    _crear('pendiente', dias=0)
    html = logged_client.get('/pedidos?estado=todos').get_data(as_text=True)
    assert 'data-tablero="1"' not in html
    assert 'filter-pill' in html, 'la lista conserva sus píldoras'


def test_el_enlace_del_dashboard_sigue_funcionando(logged_client):
    """`/pedidos?estado=pendiente` lo dispara el aviso del dashboard
    (app.py:1915). Si se rompe, se rompe en producción sin que nadie toque
    nada."""
    _crear('pendiente', dias=0)
    r = logged_client.get('/pedidos?estado=pendiente')
    assert r.status_code == 200
    html = r.get_data(as_text=True)
    assert 'data-tablero="1"' not in html, 'un enlace viejo cayó en el tablero'


def test_un_parametro_desconocido_no_cambia_el_modo(logged_client):
    """Un `?utm_source=` pegado por un cliente de correo no puede convertir
    el tablero en lista."""
    _crear('pendiente', dias=0)
    html = logged_client.get('/pedidos?utm_source=whatsapp').get_data(as_text=True)
    assert 'data-tablero="1"' in html


def test_un_parametro_vacio_no_cambia_el_modo(logged_client):
    _crear('pendiente', dias=0)
    html = logged_client.get('/pedidos?q=').get_data(as_text=True)
    assert 'data-tablero="1"' in html


def test_buscar_desde_el_tablero_busca_en_todo(logged_client):
    """Sin esto, buscar «Mangusa» desde el tablero saldría filtrado a lo no
    facturado y no encontraría NADA del archivo, que es justo lo que se
    estaba buscando."""
    _crear('facturado', dias=-40)
    html = logged_client.get('/pedidos?q=Cliente').get_data(as_text=True)
    assert 'pedidos-empty' not in html, (
        'la búsqueda sin `estado` explícito no alcanzó el archivo'
    )
```

- [ ] **Step 2: Correr y verificar que fallan**

Run: `.venv/bin/python -m pytest tests/test_pedidos_tablero.py -q -k "tablero or dashboard or parametro or buscar"`
Expected: FAIL — `data-tablero="1"` no existe todavía

- [ ] **Step 3: Decidir el modo en la ruta**

En `app.py`, dentro de `lista_pedidos`, **antes** de leer `estado` (cerca de la línea 5820):

```python
    # El modo lo decide la presencia de parámetros RECONOCIDOS, no un toggle:
    # así todo enlace y marcador existente sigue funcionando sin tocarlo, en
    # particular `/pedidos?estado=pendiente`, que dispara el aviso del
    # dashboard. Se mira la lista blanca y no `request.args` a secas porque si
    # no, un `?utm_source=` pegado a un enlace compartido convertiría el
    # tablero en lista sin que nadie lo pidiera.
    PARAMS_DE_LISTA = ('q', 'estado', 'page', 'orden', 'per_page', 'solo_notas')
    modo_tablero = not any(
        (request.args.get(p) or '').strip() for p in PARAMS_DE_LISTA
    )
```

Cambiar el default de `estado` (línea ~5821). Era `por_preparar`:

```python
    # El default pasa de `por_preparar` a `todos` porque el tablero ya se
    # quedó con el trabajo del día. Si la lista siguiera abriendo en
    # `por_preparar`, buscar «Mangusa» desde el tablero saldría filtrado a lo
    # no facturado y no encontraría nada del archivo — que es exactamente lo
    # que se estaba buscando.
    estado = (request.args.get('estado', 'todos', type=str) or 'todos').strip().lower()
```

- [ ] **Step 4: Construir los grupos y pasarlos a la plantilla**

En `lista_pedidos`, justo **antes** del bloque `plantilla = ...` (cerca de la línea 6090):

```python
    # ── Tablero ──
    # Consulta propia, no la paginada: el tablero son todos los pedidos con
    # trabajo pendiente más las entregas de hoy. A 3 pedidos por día son unas
    # pocas filas, así que no pagina.
    grupos = None
    if modo_tablero:
        pedidos_tablero = base_query_tablero.filter(
            or_(Pedido.estado != 'facturado', Pedido.fecha_entrega == hoy_local)
        ).order_by(
            Pedido.fecha_entrega.asc().nullslast(),
            Pedido.id.desc(),
        ).all()
        for pedido, total in pedidos_tablero:
            _decorar_pedido(pedido, total)
        grupos = _agrupar_tablero([p for p, _t in pedidos_tablero], hoy_local)
```

Esto necesita dos cosas que hay que extraer primero, porque hoy viven inline:

1. **`base_query_tablero`**: guardar una copia de `base_query` justo después de calcular `status_counts` y **antes** de aplicar los filtros de estado (cerca de la línea 5978, antes de `if estado == 'por_preparar'`):

```python
    # Copia sin los filtros de bandeja: el tablero arma los suyos.
    base_query_tablero = base_query
```

2. **`_decorar_pedido(pedido, total)`**: extraer el cuerpo del bucle `for pedido, total in pedidos_query:` (líneas ~6045-6072) a una función, porque el tablero necesita exactamente la misma decoración (`total_calculado`, `moneda`, `tiene_pesables`, `total_xcg`) y duplicarla es garantía de que se desincronicen. Ponerla junto a `_agrupar_tablero`:

```python
def _decorar_pedido(pedido, total_sql):
    """Los campos calculados que la lista y el tablero necesitan por igual.

    El SQL computa el total como cajas pedidas × precio. Para reflejar el
    avance real se sustituye por `_calcular_venta_pedido`, que para pesables
    usa peso_real × precio y cae a la línea original solo si no hay cajas
    pesadas todavía.
    """
    venta_real = _calcular_venta_pedido(pedido)
    pedido.total_calculado = float(venta_real) if venta_real and venta_real > 0 else float(total_sql)
    # El factor sale de la MONEDA y no del `tipo_cambio` guardado: XCG vale 1
    # por definición, y hay 381 pedidos en XCG estampados con 1.78 en
    # producción (expediente conocido, sin remediar) que se inflarían un 78%.
    pedido.moneda = (pedido.cliente.moneda if pedido.cliente else 'XCG') or 'XCG'
    pedido.tiene_pesables = _pedido_tiene_productos_pesables(pedido)
    pedido.total_xcg = (
        pedido.total_calculado if pedido.moneda == 'XCG'
        else pedido.total_calculado * float(pedido.tipo_cambio or 1.78)
    )
```

y reemplazar el bucle original por:

```python
    pedidos = []
    for pedido, total in pedidos_query:
        _decorar_pedido(pedido, total)
        pedidos.append(pedido)
```

Y agregar `grupos` y `modo_tablero` al `render_template` final:

```python
    return render_template(
        plantilla,
        pedidos=pedidos,
        pagination=pagination,
        filtros=filtros,
        status_counts=status_counts,
        url_actual=url_actual,
        grupos=grupos,
        modo_tablero=modo_tablero,
        hoy_local=hoy_local,
    )
```

- [ ] **Step 5: Parcial mínimo del tablero**

Crear `templates/_pedidos_tablero.html` (versión mínima; la Tarea 3 la completa):

```jinja
<div class="pedidos-tablero" data-tablero="1">
  {% for clave, etiqueta, pedidos_grupo in grupos %}
  <section class="tablero-grupo tablero-grupo-{{ clave }}">
    <h2 class="tablero-titulo">{{ etiqueta }} <span class="tablero-cuenta">{{ pedidos_grupo|length }}</span></h2>
    <ul class="tablero-lista">
      {% for pedido in pedidos_grupo %}
      <li>PED-{{ pedido.id }} — {{ pedido.cliente.nombre if pedido.cliente else '—' }}</li>
      {% endfor %}
    </ul>
  </section>
  {% endfor %}
</div>
```

En `templates/pedidos.html`, envolver el bloque que ya existe **sin editar una sola línea de su interior**. Las anclas exactas:

- **Primera línea a envolver:** el comentario que empieza `{# UN solo control para UNA sola variable.` (hoy línea ~48).
- **Última línea a envolver:** el `  </div>` que cierra `<div id="pedidos-resultados" …>` (hoy línea ~94).

Insertar **antes** de la primera ancla:

```jinja
  {% if modo_tablero %}
  {% include '_pedidos_tablero.html' %}
  {% else %}
```

e insertar **después** de la última ancla:

```jinja
  {% endif %}
```

Todo lo de adentro —el `{% set vistas %}`, las píldoras, la región `aria-live` y el `<div id="pedidos-resultados">`— queda exactamente igual. Si el diff muestra cambios dentro de ese rango, algo se rompió: revertir y volver a envolver.

El `<p class="pedidos-error" id="pedidos-error" hidden>` que va después queda **fuera** del `if`, porque el buscador puede fallar en los dos modos.

Mantener el `<form class="filter-bar">` **fuera** del `if`: el buscador vive en los dos modos. En modo tablero el hidden de `estado` debe renderizar vacío, para que buscar mande solo `q`:

```jinja
    <input type="hidden" name="estado" id="pedidos-estado" value="{{ '' if modo_tablero else filtros.estado }}">
```

- [ ] **Step 6: Arreglar la rotura conocida**

`tests/test_pedidos_lista_entrega.py` lee los contadores con `GET /pedidos`, que ahora es el tablero. En `_counts()` (línea ~74), cambiar la URL:

```python
    html = logged_client.get('/pedidos?estado=todos').get_data(as_text=True)
```

Y en `test_la_cifra_y_su_filtro_coinciden`, cualquier `logged_client.get('/pedidos')` pasa a `logged_client.get('/pedidos?estado=todos')`.

- [ ] **Step 7: Correr la suite completa**

Run: `.venv/bin/python -m pytest tests/ -q`
Expected: PASS. Si falla algo distinto de lo previsto, **parar y reportar** antes de tocar más tests: puede ser una regresión real y no acoplamiento a markup.

- [ ] **Step 8: Commit**

```bash
git add app.py templates/pedidos.html templates/_pedidos_tablero.html tests/
git commit -m "feat(pedidos): el modo lo decide la URL, y sin parámetros es tablero"
```

---

### Task 3: El tablero de verdad

**Files:**
- Modify: `templates/_pedidos_tablero.html`
- Modify: `static/css/pedidos_list.css`
- Test: `tests/test_pedidos_tablero.py` (agregar)

**Interfaces:**
- Consumes: `grupos`, `status_counts`, `hoy_local`, `url_actual` del contexto de la Tarea 2.

- [ ] **Step 1: Escribir los tests que fallan**

Agregar a `tests/test_pedidos_tablero.py`:

```python
def test_el_facturado_de_hoy_se_ve_marcado_como_hecho(logged_client):
    _crear('facturado', dias=0)
    html = logged_client.get('/pedidos').get_data(as_text=True)
    assert 'tablero-hecho' in html, 'el facturado de hoy no se marca como hecho'


def test_el_tablero_vacio_no_alarma(logged_client):
    """Un día sin entregas pendientes es un día bien cerrado, no un error.

    Se afirma sobre el bloque del vacío y NO sobre la página entera: el aviso
    de red (`#pedidos-error`) vive fuera del tablero y está en el HTML siempre,
    escondido. Buscar «error» en toda la página lo encontraría y el test
    fallaría sin que nada esté mal.
    """
    import re
    html = logged_client.get('/pedidos').get_data(as_text=True)
    assert 'Nada para entregar hoy' in html
    bloque = re.search(r'tablero-vacio.*?</div>', html, re.S)
    assert bloque, 'no se renderizó el bloque de vacío'
    texto = bloque.group(0).lower()
    for palabra in ('error', 'falló', 'no se pudo', 'problema'):
        assert palabra not in texto, f'el vacío del tablero alarma: «{palabra}»'


def test_el_tablero_ofrece_la_salida_al_archivo(logged_client):
    _crear('pendiente', dias=0)
    html = logged_client.get('/pedidos').get_data(as_text=True)
    assert 'estado=todos' in html, 'falta el enlace de escape al archivo'


def test_el_tablero_corta_en_50_por_grupo(logged_client):
    for i in range(55):
        _crear('pendiente', dias=0)
    html = logged_client.get('/pedidos').get_data(as_text=True)
    assert html.count('tablero-fila') <= 50
    assert 'y 5 más' in html
```

- [ ] **Step 2: Correr y verificar que fallan**

Run: `.venv/bin/python -m pytest tests/test_pedidos_tablero.py -q -k "hecho or vacio or salida or corta"`
Expected: FAIL

- [ ] **Step 3: Escribir el parcial completo**

Reemplazar `templates/_pedidos_tablero.html` entero:

```jinja
{# El tablero de entregas. Cuatro grupos fijos por `fecha_entrega`, sin
   píldoras de estado, sin paginación y sin orden por columna: a 3 pedidos por
   día son unas pocas filas y entran enteras en una pantalla.
   Spec: docs/superpowers/specs/2026-08-28-pedidos-tablero-design.md #}
<div class="pedidos-tablero" data-tablero="1">
  {% for clave, etiqueta, pedidos_grupo in grupos %}
  <section class="tablero-grupo tablero-grupo-{{ clave }}">
    <h2 class="tablero-titulo">
      {{ etiqueta }}<span class="tablero-cuenta">{{ pedidos_grupo|length }}</span>
    </h2>

    {% for pedido in pedidos_grupo[:50] %}
    {% set hecho = pedido.estado == 'facturado' %}
    <div class="pedido-card tablero-fila{% if hecho %} tablero-hecho{% endif %}"
         data-href="{{ url_for('detalles_pedido', pedido_id=pedido.id) }}"
         data-estado="{{ (pedido.estado or '')|lower }}">
      {% include '_pedido_card_cuerpo.html' %}
    </div>
    {% endfor %}

    {% if pedidos_grupo|length > 50 %}
    {# Techo de seguridad. Con 3 pedidos por día no debería verse nunca; es
       barato contra que una anomalía de datos dibuje 942 filas. Apunta a la
       lista completa y no a un filtro por grupo porque «Próximos» y «Sin
       fecha» no tienen equivalente en la lista blanca de `estado`. #}
    <a class="tablero-mas" href="{{ url_for('lista_pedidos', estado='todos') }}">
      y {{ pedidos_grupo|length - 50 }} más
    </a>
    {% endif %}
  </section>
  {% endfor %}

  {% if not grupos %}
  <div class="pedidos-empty tablero-vacio">
    <i class="fa fa-clipboard-check" aria-hidden="true"></i>
    <p>Nada para entregar hoy.</p>
    <p class="pedidos-empty-hint">Cuando cargues un pedido con fecha de entrega, aparece acá.</p>
  </div>
  {% endif %}

  <a class="tablero-archivo" href="{{ url_for('lista_pedidos', estado='todos') }}">
    Ver los {{ status_counts.total }} pedidos
  </a>
</div>
```

- [ ] **Step 4: Extraer el cuerpo de la tarjeta a su propio parcial**

El `{% include '_pedido_card_cuerpo.html' %}` del paso anterior **no existe todavía**. Se crea moviendo —sin editar— el interior de `.pedido-card` que hoy vive en `templates/_pedidos_resultados.html`, para que la tarjeta del tablero y la de la lista sean literalmente el mismo archivo. Duplicarla es garantía de que en tres semanas una tenga el botón de facturar arreglado y la otra no.

**Anclas exactas en `_pedidos_resultados.html`** (versión al 2026-08-28, commit `53c9dd13`):

- **Primera línea a mover** (hoy línea 25): `      <div class="pc-top">`
- **Última línea a mover** (hoy línea 208): el `      </div>` que cierra `.pc-foot` — es el que está inmediatamente **antes** del `    </div>` que cierra `.pedido-card` (línea 209) y del `    {% else %}` del bucle (línea 210).

Comprobar el corte antes de mover:

```bash
sed -n '25p;206,210p' templates/_pedidos_resultados.html
# Debe imprimir, en orden:
#       <div class="pc-top">
#         </div>          ← cierra .pc-actions
#         {% endif %}
#       </div>            ← cierra .pc-foot   ← ÚLTIMA LÍNEA A MOVER
#     </div>              ← cierra .pedido-card  ← ESTA SE QUEDA
#     {% else %}
```

Mover ese rango tal cual a `templates/_pedido_card_cuerpo.html`, encabezado con:

```jinja
{# Cuerpo de la tarjeta de un pedido: cabecera, nota, metadatos y acciones.
   Vive en su propio parcial porque lo usan la lista (_pedidos_resultados) y el
   tablero (_pedidos_tablero), y son la misma tarjeta. Depende del contexto:
   `pedido`, `hoy_local` y `url_actual`. #}
```

y reemplazar el rango original en `_pedidos_resultados.html` por una sola línea:

```jinja
      {% include '_pedido_card_cuerpo.html' %}
```

Verificar que el movimiento fue neutral para la lista:

```bash
.venv/bin/python -m pytest tests/test_pedidos_lista_acciones.py tests/test_pedidos_lista_entrega.py -q
```

Expected: PASS. Esos tests afirman el `data-confirm` en el `<form>`, el `next` y los contadores — si el corte se llevó una línea de más o de menos, fallan ahí.

- [ ] **Step 5: Estilos**

Agregar al final de `static/css/pedidos_list.css`:

```css
/* ── Tablero de entregas ───────────────────────────────────────────────── */
body[data-pedidos-list-screen] .tablero-grupo {
  margin-bottom: var(--space-5, 24px);
}

body[data-pedidos-list-screen] .tablero-titulo {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 0 0 10px;
  font-size: 0.95rem;
  font-weight: 800;
  letter-spacing: 0.02em;
  text-transform: uppercase;
  color: var(--color-text-muted);
}

body[data-pedidos-list-screen] .tablero-cuenta {
  font-weight: 700;
  font-variant-numeric: tabular-nums;
  color: var(--color-text-subtle);
}

/* Atrasados es el único grupo que se pinta: es el único que significa
   «esto ya se pasó de fecha». Si se pintaran todos, ninguno destacaría. */
body[data-pedidos-list-screen] .tablero-grupo-atrasados .tablero-titulo {
  color: #9f1239;
}

/* Hecho: se ve, pero deja de pedir atención. No se esconde, porque media
   parte de «trabajar lo de hoy» es ver que el día cerró completo. */
body[data-pedidos-list-screen] .tablero-hecho {
  opacity: 0.62;
}

body[data-pedidos-list-screen] .tablero-hecho .pc-actions {
  opacity: 1;
}

body[data-pedidos-list-screen] .tablero-archivo,
body[data-pedidos-list-screen] .tablero-mas {
  display: inline-flex;
  align-items: center;
  min-height: var(--touch-min, 48px);
  padding: 0 16px;
  color: var(--color-primary-soft-fg);
  font-weight: 700;
  font-size: 0.9rem;
  text-decoration: none;
}

body[data-pedidos-list-screen] .tablero-archivo:hover,
body[data-pedidos-list-screen] .tablero-mas:hover {
  text-decoration: underline;
  text-underline-offset: 3px;
}
```

- [ ] **Step 6: Correr los tests**

Run: `.venv/bin/python -m pytest tests/ -q`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add templates/ static/css/pedidos_list.css tests/
git commit -m "feat(pedidos): el tablero dibuja sus grupos, lo hecho y la salida al archivo"
```

---

### Task 4: Buscar cambia de modo, y la verificación visual

**Files:**
- Modify: `templates/pedidos.html` (el script inline)
- Test: manual en navegador + `tests/test_pedidos_tablero.py`

- [ ] **Step 1: Escribir el test que falla**

```python
def test_al_borrar_la_busqueda_se_vuelve_al_tablero(logged_client):
    """Sin parámetros con valor, vuelve el tablero. Es el contrato que hace
    que borrar el buscador devuelva al trabajo del día."""
    _crear('pendiente', dias=0)
    html = logged_client.get('/pedidos?q=').get_data(as_text=True)
    assert 'data-tablero="1"' in html
```

- [ ] **Step 2: Correr y verificar**

Run: `.venv/bin/python -m pytest tests/test_pedidos_tablero.py -q -k "borrar"`
Expected: PASS ya (lo cubre la Tarea 2). Si falla, el modo no está mirando valores vacíos.

- [ ] **Step 3: Ajustar el JS de la búsqueda**

En `templates/pedidos.html`, dentro del script inline: en modo tablero **no existe** `#pedidos-resultados`, así que `cargarResultados` no tiene dónde escribir. La búsqueda desde el tablero tiene que navegar de verdad.

Al principio del IIFE (después de leer `resultados`, cerca de la línea 111):

```js
    // En el tablero no hay bloque de resultados que reemplazar: buscar navega
    // a la lista. Desde la lista sí se hace por fetch, para no cerrar el
    // teclado de iOS a cada tecla.
    var enTablero = !resultados;
    if (enTablero && searchInput) {
      var debounceTablero = null;
      searchInput.addEventListener('input', function () {
        clearTimeout(debounceTablero);
        var q = searchInput.value.trim();
        if (!q) return;
        debounceTablero = setTimeout(function () {
          location.href = '{{ url_for("lista_pedidos") }}?q=' + encodeURIComponent(q);
        }, 450);
      });
      return;   // nada más de este script aplica al tablero
    }
```

- [ ] **Step 4: Verificación en navegador**

Levantar el preview con datos representativos y medir **el render**, no las propiedades:

```bash
SCRATCH=/tmp/preview && cp instance/local.db $SCRATCH/tablero.db
DATABASE_URL="sqlite:///$SCRATCH/tablero.db" SECRET_KEY=dev \
  .venv/bin/python -c "import app as m; m.app.run(port=5017)"
```

Comprobar, en 390×844 y 1440×900 en una sola ronda:

1. `/pedidos` dibuja los grupos que corresponden y **ninguno vacío**.
2. Un pedido facturado con entrega hoy se ve atenuado pero sus botones siguen usables (`getComputedStyle(...).opacity` en el botón, no en la tarjeta).
3. Escribir en el buscador navega a `?q=…` y muestra la lista.
4. `document.documentElement.scrollWidth === clientWidth` en los dos anchos.
5. Cada destino de toque del tablero mide ≥48px de alto medido con `getBoundingClientRect()`.
6. Cero errores de consola.

- [ ] **Step 5: Correr la suite completa y el detector**

```bash
.venv/bin/python -m pytest tests/ -q
node ~/.claude/plugins/cache/impeccable/impeccable/4.1.2/skills/impeccable/scripts/detect.mjs --json templates/pedidos.html templates/_pedidos_tablero.html
```

- [ ] **Step 6: Commit**

```bash
git add templates/pedidos.html tests/
git commit -m "feat(pedidos): buscar desde el tablero entra al archivo"
```

---

## Fuera de alcance de este plan

- Rellenar `fecha_entrega` en los 910 históricos.
- Tocar el formulario de alta.
- El historial por cliente (etapa 2, con su propio spec).
