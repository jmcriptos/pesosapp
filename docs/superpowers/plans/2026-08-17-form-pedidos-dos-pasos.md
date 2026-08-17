# Formulario de pedidos en dos pasos — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Eliminar los saltos de layout y el desorden del formulario de pedidos partiéndolo en dos pasos renderizados por el servidor, según `docs/superpowers/specs/2026-08-17-flujo-form-pedidos-design.md`.

**Architecture:** Paso 1 (`templates/pedido_cliente.html`, nuevo) elige cliente y grupo; paso 2 (`templates/pedido_form.html`, reestructurado) llega del servidor con precios por cliente y líneas habituales sembradas — igual que hoy funciona la edición. El async de carga (`/api/precios/...`, `/api/.../pedido-habitual`) desaparece del template; los endpoints quedan vivos (los usan los tests). El POST de crear/editar **no cambia ni un campo**.

**Tech Stack:** Flask + Jinja + SQLAlchemy, TomSelect, JS vanilla inline con `nonce="{{ csp_nonce() }}"`, pytest.

**Ejecución multi-agente (pedido de JM):** un subagente fresco por tarea, modelo anotado en cada una (`Agente:`). Las tareas van EN SERIE (comparten `app.py` y `pedido_form.html`); la paralelización aquí sería conflicto, no velocidad. El orquestador (Fable) revisa entre tareas y hace la verificación en navegador final.

## Global Constraints

- El POST de `/pedidos/nuevo` y `/pedidos/<id>/editar` no cambia: mismos campos (`cliente_id`, `notas`, `tipo_cambio`, `fecha_entrega`, `productos[i][id|nombre|cajas|precio]`), mismas validaciones, mismos flashes.
- `test_authz_idor.py::test_vendedor_ajeno_no_abre_editar_pedido` exige que el guard de edición corra ANTES de renderizar (302/403 sin template). No mover el guard.
- Scripts inline siempre con `nonce="{{ csp_nonce() }}"`; handlers por delegación/`data-*` (convenciones de `base.js`); TODO dato de API/DB que entre por `innerHTML` pasa por `escapeHtml` (ya global).
- Correr tests: `cd /Users/josedasilva/Projects/pesosapp/.claude/worktrees/partial-box-quantities-c4b5d0 && /Users/josedasilva/Projects/pesosapp/.venv/bin/python -m pytest <target> -q` (nunca forzar `DATABASE_URL`).
- Commits pequeños al terminar cada tarea, mensaje en español, con `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`.
- No tocar: panel de añadir (`ph-add-panel`), stepper, regla de grupos del buscador, `pedido_a_json`, precios/POST, minificados (`base.min.js` no se toca — el JS del form es inline del template).
- Cantidades fraccionarias (recién desplegado): el seed server-side de líneas debe conservar floats (0.5) tal cual; el filtro `fmt_cajas` existe para display Python/Jinja; en JS `Number` imprime limpio.

## Hechos del codebase que los implementadores necesitan

- `_calcular_pedido_habitual(cliente_id, grupo_clave=None, visitas=_HABITUAL_VISITAS)` → `(lineas, meta)`. `lineas`: `[{id, nombre, cajas, cajas_habitual, precio, visitas}]` (precio float|None). `meta`: `{visitas: int, ultima_fecha: 'YYYY-MM-DD'|None, cadencia_dias: int|None, grupos: list, grupo: str|None}`. Con cliente multi-grupo y `grupo_clave` None o inválida → `meta['grupo'] is None` y `meta['grupos']` trae >1 items `{clave, etiqueta, pedidos, ultima_fecha, ejemplos: list[str]}`.
- `_clave_grupo(_grupo_facturable(p))` → `'pesable:10'|'importado:10'|...` o `''`.
- Jerarquía de precios: `obtener_precio_producto_cliente(cliente_id, producto_id, 'base')` → Decimal|None; fallback `obtener_precio_default_producto(producto_id, 'base')`.
- `nuevo_pedido` está en `app.py` ~5941 (GET arma `productos_dicts` con precio DEFAULT hoy); `editar_pedido` ~6060 (ya arma `productos_dicts` con precio POR CLIENTE — ese bloque es el patrón a extraer).
- El template actual siembra líneas así (pedido_form.html ~183): `productosAgregados = (productos_pedido || []).map(p => ({id, nombre, cajas, precio, habitual: null, activa: true}))`.
- Ningún test lee IDs/clases del HTML del form (verificado 2026-08-17); 4 tests llegan al GET por redirect de POST fallido y solo buscan substrings de flashes ('cuarto', 'mayor que 0', 'impuestos distintos') que además existen en comentarios del template.

---

### Task 1: Helper de catálogo por cliente + contexto del paso 2 en `nuevo_pedido`

**Agente: opus** (lógica de rutas, permisos y grupos — el corazón del cambio).

**Files:**
- Modify: `app.py` (helper nuevo junto a `_validar_grupo_unico` ~5893; GET de `nuevo_pedido` ~5944-5969; GET de `editar_pedido` ~6068-6085 solo para usar el helper)
- Create: `tests/test_pedido_dos_pasos.py`
- Create: `templates/pedido_cliente.html` (ESQUELETO mínimo para que el GET renderice; la Task 2 lo termina)

**Interfaces:**
- Produces: `_productos_dicts_para_cliente(cliente_id)` → list[dict] `{id, nombre, precio: float|None, grupo: str}` (precio None si no hay en ninguna lista — el form muestra «sin precio»).
- Produces: `_texto_hero_habitual(meta)` → str («Compra cada N días · última vez el D mmm» / «Sin pedidos anteriores»).
- Produces: `_texto_origen_lineas(n_lineas, visitas)` → str («3 líneas cargadas con las cantidades de sus últimas 4 visitas. Ajusta lo que cambie y envía.» / «» si n_lineas==0).
- Produces: contexto de `pedido_form.html`: `cliente` (obj), `productos`, `productos_pedido` (`[{id, nombre, cajas, precio, habitual}]`, habitual None para líneas de edición), `pedido`, `hero_meta_texto`, `origen_texto`, `grupo_clave` (str), `tipo_cambio_valor` (float).
- Produces: contexto de `pedido_cliente.html`: `clientes`, `destino` (URL base a la que navegar), `cliente_pendiente` (obj|None), `grupos_cliente` (list|None).

- [ ] **Step 1: Tests que fallan** — crear `tests/test_pedido_dos_pasos.py` con el fixture calcado de `tests/test_pedido_habitual.py:19-78` (mismo app fixture, logged_client, `_ids()`, `_crear_pedido()` — copiarlos literal) y estos tests:

```python
def test_paso1_sin_cliente_muestra_selector(app, logged_client):
    resp = logged_client.get('/pedidos/nuevo')
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert 'id="paso-cliente"' in html
    assert 'id="form-nuevo-pedido"' not in html   # el paso 1 no trae el form del pedido


def test_paso2_cliente_con_historial_siembra_lineas(app, logged_client):
    cliente_id, prods = _ids()
    chuleta = prods['Chuleta de cerdo ahumada 5 kg']
    _crear_pedido(cliente_id, [(chuleta, 7)], dias_atras=3)

    resp = logged_client.get(f'/pedidos/nuevo?cliente={cliente_id}')
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert 'id="form-nuevo-pedido"' in html
    assert 'Chuleta de cerdo ahumada 5 kg' in html
    assert '"habitual": 7' in html or '"habitual":7' in html
    # (el hidden cliente_id llega con la Task 3; aquí el select transicional
    # debe traer al cliente preseleccionado)
    assert 'selected' in html


def test_paso2_multigrupo_sin_grupo_repregunta(app, logged_client):
    cliente_id, prods = _ids()
    _crear_pedido(cliente_id, [(prods['Chuleta de cerdo ahumada 5 kg'], 3)], dias_atras=7)
    _crear_pedido(cliente_id, [(prods['Ham di Pasku 4 kg'], 2)], dias_atras=3)

    resp = logged_client.get(f'/pedidos/nuevo?cliente={cliente_id}')
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert 'id="paso-cliente"' in html
    assert 'Qué pedido vas a tomar' in html
    assert f'cliente={cliente_id}&amp;grupo=pesable:10' in html or f'cliente={cliente_id}&grupo=pesable:10' in html


def test_paso2_multigrupo_con_grupo_precarga_solo_ese(app, logged_client):
    cliente_id, prods = _ids()
    for dias in (14, 7):
        _crear_pedido(cliente_id, [(prods['Chuleta de cerdo ahumada 5 kg'], 3)], dias_atras=dias)
        _crear_pedido(cliente_id, [(prods['Ham di Pasku 4 kg'], 2)], dias_atras=dias - 1)

    resp = logged_client.get(f'/pedidos/nuevo?cliente={cliente_id}&grupo=pesable:10')
    html = resp.get_data(as_text=True)
    assert 'id="form-nuevo-pedido"' in html
    assert 'Chuleta de cerdo ahumada 5 kg' in html
    assert 'Ham di Pasku 4 kg' not in html.split('const productos =')[0]  # no en líneas sembradas


def test_paso2_cliente_inexistente_redirige_paso1(app, logged_client):
    resp = logged_client.get('/pedidos/nuevo?cliente=99999', follow_redirects=False)
    assert resp.status_code in (302, 303)


def test_catalogo_paso2_trae_precio_del_cliente(app, logged_client):
    from app import PrecioClienteProducto
    cliente_id, prods = _ids()
    pid = prods['Chuleta de cerdo ahumada 5 kg']
    _db.session.add(PrecioClienteProducto(
        cliente_id=cliente_id, producto_id=pid, precio_base=99.55))
    _db.session.commit()
    _crear_pedido(cliente_id, [(pid, 3)], dias_atras=3)

    html = logged_client.get(f'/pedidos/nuevo?cliente={cliente_id}').get_data(as_text=True)
    assert '99.55' in html
```

  NOTA: si `PrecioClienteProducto` usa otros nombres de columna, mirar el modelo en `app.py` (grep `class PrecioClienteProducto`) y ajustar SOLO el test — la jerarquía se consulta vía `obtener_precio_producto_cliente`, no a mano.

- [ ] **Step 2: Verificar que fallan** — `pytest tests/test_pedido_dos_pasos.py -q` → los 6 FAIL (paso-cliente no existe, ?cliente se ignora hoy).

- [ ] **Step 3: Helpers en `app.py`** (pegarlos justo después de `_parsear_fecha_entrega`):

```python
def _productos_dicts_para_cliente(cliente_id):
    """Catálogo para el form con el precio que vería ESTE cliente (jerarquía).

    precio None = sin precio en ninguna lista → el buscador dice «sin precio»
    en vez de 0.00, que se lee como gratis.
    """
    productos = Producto.query.all()
    dicts = []
    for p in productos:
        precio = obtener_precio_producto_cliente(cliente_id, p.id, 'base')
        if precio is None:
            precio = obtener_precio_default_producto(p.id, 'base')
        dicts.append({
            'id': p.id,
            'nombre': p.nombre,
            'precio': float(precio) if precio is not None else None,
            'grupo': _clave_grupo(_grupo_facturable(p)),
        })
    return dicts


def _texto_hero_habitual(meta):
    """Línea de cadencia/historial que antes armaba el JS (actualizarHero)."""
    partes = []
    if meta.get('cadencia_dias'):
        partes.append(f"Compra cada {meta['cadencia_dias']} días")
    if meta.get('ultima_fecha'):
        try:
            f = datetime.strptime(meta['ultima_fecha'], '%Y-%m-%d').date()
            meses = ['ene', 'feb', 'mar', 'abr', 'may', 'jun',
                     'jul', 'ago', 'sep', 'oct', 'nov', 'dic']
            partes.append(f'última vez el {f.day} {meses[f.month - 1]}')
        except (ValueError, TypeError):
            pass
    if not partes:
        total = sum(g.get('pedidos', 0) for g in meta.get('grupos', []))
        if total:
            n = len(meta.get('grupos', []))
            partes.append(f"{total} {'pedido' if total == 1 else 'pedidos'} en {n} grupos")
        else:
            partes.append('Sin pedidos anteriores')
    return ' · '.join(partes)


def _texto_origen_lineas(n_lineas, visitas):
    """Aviso de dónde salen las líneas precargadas (antes lo armaba el JS)."""
    if not n_lineas:
        return ''
    lineas_txt = f"{n_lineas} {'línea cargada' if n_lineas == 1 else 'líneas cargadas'}"
    if visitas == 1:
        return (f'Partimos de su pedido habitual: {lineas_txt} con su última '
                'visita, la única que tiene registrada. Ajusta lo que cambie y envía.')
    return (f'Partimos de su pedido habitual: {lineas_txt} con las cantidades '
            f'de sus últimas {visitas} visitas. Ajusta lo que cambie y envía.')
```

- [ ] **Step 4: GET de `nuevo_pedido`** — en `app.py`, dentro de `nuevo_pedido()`: dejar la resolución de `clientes` como está; BORRAR el bloque `productos_dicts` de precio default (~5957-5969); el POST queda idéntico salvo los `redirect(url_for('nuevo_pedido'))` de error de línea/validación, que pasan a `redirect(url_for('nuevo_pedido', cliente=cliente_id))` para no perder el paso 2 (solo los redirects DESPUÉS de conocer `cliente_id`). Al final, reemplazar el `return render_template('pedido_form.html', ...)` del GET por:

```python
    # ── GET: dos pasos ────────────────────────────────────────────
    cliente_id_arg = request.args.get('cliente', type=int)
    if not cliente_id_arg:
        return render_template(
            'pedido_cliente.html',
            clientes=clientes,
            destino=url_for('nuevo_pedido'),
            cliente_pendiente=None,
            grupos_cliente=None,
        )

    cliente = db.session.get(Cliente, cliente_id_arg)
    permitidos = {c.id for c in clientes}
    if cliente is None or cliente.id not in permitidos:
        flash('Cliente no válido para este vendedor', 'error')
        return redirect(url_for('nuevo_pedido'))

    grupo_arg = request.args.get('grupo') or None
    lineas_hab, meta = _calcular_pedido_habitual(cliente.id, grupo_clave=grupo_arg)

    if meta['grupo'] is None and len(meta['grupos']) > 1:
        # Multi-grupo sin elegir (o clave inválida): re-preguntar en paso 1.
        return render_template(
            'pedido_cliente.html',
            clientes=clientes,
            destino=url_for('nuevo_pedido'),
            cliente_pendiente=cliente,
            grupos_cliente=meta['grupos'],
        )

    productos_pedido = [{
        'id': l['id'],
        'nombre': l['nombre'],
        'cajas': l['cajas'],
        'precio': l['precio'],
        'habitual': l['cajas_habitual'],
    } for l in lineas_hab]

    return render_template(
        'pedido_form.html',
        cliente=cliente,
        productos=_productos_dicts_para_cliente(cliente.id),
        productos_pedido=productos_pedido,
        pedido=None,
        hero_meta_texto=_texto_hero_habitual(meta),
        origen_texto=_texto_origen_lineas(len(productos_pedido), meta['visitas']),
        grupo_clave=meta['grupo'] or '',
        tipo_cambio_valor=1.78 if (cliente.moneda or 'XCG') == 'USD' else 1.0,
    )
```

  Y en `editar_pedido` GET, reemplazar el bloque `productos_dicts` (~6072-6085) por `productos_dicts = _productos_dicts_para_cliente(pedido.cliente_id)` (la Task 4 lo extiende con `?cliente`); pasar además al render actual de edición: `cliente=pedido.cliente`, `hero_meta_texto=''`, `origen_texto=''`, `grupo_clave=''`, `tipo_cambio_valor=float(pedido.tipo_cambio or 1.0)`, y `habitual` None en cada item de `productos_pedido`.

- [ ] **Step 5: Esqueleto `templates/pedido_cliente.html`** (mínimo para que los tests pasen; la Task 2 lo deja bonito):

```html
{% extends "base.html" %}
{% block title %}Nuevo Pedido — PesosApp{% endblock %}
{% block body_attrs %}data-theme="dark" data-hue="blue" data-glass="heavy" data-pedido-form-screen="1" data-pedido-habitual="1"{% endblock %}
{% block extra_css %}
<link rel="stylesheet" href="{{ url_for('static', filename='css/pedido_form_inline.css') }}">
<link rel="stylesheet" href="{{ url_for('static', filename='css/pedido_form.css') }}">
<link rel="stylesheet" href="{{ url_for('static', filename='css/pedido_habitual.css') }}">
{% endblock %}
{% block content %}
<div class="pedido-form-shell" id="paso-cliente">
  <div class="pedido-form-topnav">
    <a href="{{ url_for('lista_pedidos') }}" class="pedido-form-close" aria-label="Cerrar"><i class="fas fa-times"></i></a>
    <div class="pedido-form-topnav-title">
      <div class="pedido-form-topnav-heading">Nuevo pedido</div>
      <div class="pedido-form-topnav-meta">¿Para qué cliente?</div>
    </div>
    <span class="pedido-form-topnav-placeholder" aria-hidden="true"></span>
  </div>
  <div class="mobile-form-container">
    <div class="ph-card">
      <label class="ph-label" for="cliente_id">Cliente</label>
      <select id="cliente_id" class="mobile-form-control" data-destino="{{ destino }}">
        <option value=""></option>
        {% for cliente in clientes|sort(attribute='nombre') %}
          <option value="{{ cliente.id }}" {% if cliente_pendiente and cliente_pendiente.id == cliente.id %}selected{% endif %}>
            {{ cliente.nombre }}{% if cliente.moneda == 'USD' %} (USD){% endif %}
          </option>
        {% endfor %}
      </select>
    </div>

    {% if grupos_cliente %}
    <div class="ph-grupos" id="ph-grupos">
      <div class="ph-grupos-title">¿Qué pedido vas a tomar?</div>
      <div class="ph-grupos-body">
        {{ cliente_pendiente.nombre }} compra de más de un grupo y un pedido no
        puede mezclarlos: QuickBooks no factura junto lo que paga impuestos distintos.
      </div>
      <div class="ph-grupos-lista">
        {% for g in grupos_cliente %}
        <a class="ph-grupo-opt"
           href="{{ destino }}?cliente={{ cliente_pendiente.id }}&grupo={{ g.clave|urlencode }}">
          <span class="ph-grupo-nombre">{{ g.etiqueta }}</span>
          {% if g.ejemplos %}<span class="ph-grupo-ejemplos">{{ g.ejemplos|join(', ') }}…</span>{% endif %}
          <span class="ph-grupo-meta">{{ g.pedidos }} {{ 'pedido' if g.pedidos == 1 else 'pedidos' }}</span>
        </a>
        {% endfor %}
      </div>
    </div>
    {% endif %}
  </div>
</div>
{% endblock %}
{% block scripts %}
<script nonce="{{ csp_nonce() }}">
document.addEventListener('DOMContentLoaded', function () {
    const sel = document.getElementById('cliente_id');
    new TomSelect('#cliente_id', {
        maxOptions: 1000, closeAfterSelect: true, placeholder: 'Buscar cliente…',
        dropdownParent: 'body', sortField: { field: 'text', direction: 'asc' },
    });
    sel.addEventListener('change', function () {
        if (!this.value) return;
        window.location.assign(this.dataset.destino + '?cliente=' + encodeURIComponent(this.value));
    });
});
</script>
{% endblock %}
```

- [ ] **Step 6: Compatibilidad transitoria del paso 2** — `pedido_form.html` aún es el template viejo (Task 3 lo reordena). Para que renderice con el contexto nuevo SIN romper: en la línea ~183 del seed añadir `habitual` (`habitual: ('habitual' in p) ? p.habitual : null,` — Jinja manda la clave siempre), y en el bloque del select de cliente marcar `selected` cuando `cliente` venga en contexto (`{% if (pedido and pedido.cliente_id == cliente_i.id) or (cliente and cliente.id == cliente_i.id) %}` — ojo con el nombre de la variable de loop para no chocar con `cliente`; renombrar el loop var a `cliente_i`). El JS viejo (fetch precios/habitual) puede seguir corriendo en esta tarea: con líneas sembradas, `cargarPedidoHabitual` respeta lo existente (guard `productosAgregados.length` línea ~481).

- [ ] **Step 7: Correr los tests nuevos** — `pytest tests/test_pedido_dos_pasos.py -q` → 6 PASS.

- [ ] **Step 8: Suite de regresión rápida** — `pytest tests/test_pedido_habitual.py tests/test_cajas_fraccionarias.py tests/test_authz_idor.py tests/test_editar_pedido_preserva_pesos.py -q` → todo verde.

- [ ] **Step 9: Commit** — `git add -A && git commit -m "feat(pedidos): paso 1 de cliente y paso 2 sembrado del servidor"`

### Task 2: Paso 1 pulido (pantalla de cliente)

**Agente: sonnet** (template + estilos, contratos ya definidos).

**Files:**
- Modify: `templates/pedido_cliente.html`
- Modify: `static/css/pedido_form.css` (solo AÑADIR reglas al final)

**Interfaces:**
- Consumes: contexto de Task 1 (`clientes`, `destino`, `cliente_pendiente`, `grupos_cliente`).
- Produces: nada nuevo para otras tareas (solo UI).

- [ ] **Step 1: Foco inmediato** — en el script del template, tras instanciar TomSelect: si NO hay `cliente_pendiente` (o sea, primera entrada), `ts.focus()` para que el teclado quede listo:

```js
const ts = new TomSelect('#cliente_id', { /* opciones de Task 1 */ });
{% if not cliente_pendiente %}setTimeout(() => ts.focus(), 150);{% endif %}
```

- [ ] **Step 2: Estados de carga honestos** — al navegar (change), deshabilitar el select y mostrar un aviso para que el round-trip no parezca cuelgue: añadir bajo la card `<p class="ph-motivo" id="paso-cliente-estado" aria-live="polite"></p>` y en el handler `document.getElementById('paso-cliente-estado').textContent = 'Cargando su pedido habitual…';`.

- [ ] **Step 3: CSS** — al FINAL de `static/css/pedido_form.css` añadir (los `.ph-grupo-opt` existentes son `<button>`; ahora también son `<a>`):

```css
/* Paso 1: la tarjeta de grupos ahora usa anchors */
#paso-cliente .ph-grupo-opt { display: flex; flex-direction: column; align-items: flex-start; gap: 2px; text-decoration: none; color: inherit; }
#paso-cliente .ph-grupos { margin-top: 16px; }
#paso-cliente .ph-card { margin-top: 8px; }
```

- [ ] **Step 4: Verificación manual ligera** — `pytest tests/test_pedido_dos_pasos.py -q` sigue verde (no cambió contrato).

- [ ] **Step 5: Commit** — `git commit -am "feat(pedidos): paso 1 pulido (foco, estado de carga, estilos)"`

### Task 3: Paso 2 reestructurado (template sin async)

**Agente: opus** (la tarea más grande: reordenar secciones y extirpar el async sin romper el JS restante).

**Files:**
- Modify: `templates/pedido_form.html`
- Modify: `static/css/pedido_form.css` (añadir reglas de cabecera al final)
- Modify: `tests/test_pedido_dos_pasos.py` (añadir tests de markup)

**Interfaces:**
- Consumes: contexto de Task 1 (`cliente`, `productos`, `productos_pedido` con `habitual`, `hero_meta_texto`, `origen_texto`, `grupo_clave`, `tipo_cambio_valor`, `pedido`).
- Produces: el orden final de secciones y los IDs estables `ph-cliente-head`, `ph-cambiar-cliente` (Task 4 los usa).

- [ ] **Step 1: Tests de markup que fallan** — añadir a `tests/test_pedido_dos_pasos.py`:

```python
def test_paso2_orden_de_secciones(app, logged_client):
    cliente_id, prods = _ids()
    _crear_pedido(cliente_id, [(prods['Chuleta de cerdo ahumada 5 kg'], 7)], dias_atras=3)
    html = logged_client.get(f'/pedidos/nuevo?cliente={cliente_id}').get_data(as_text=True)

    i_head = html.index('id="ph-cliente-head"')
    i_lineas = html.index('id="productos-body"')
    i_add = html.index('id="ph-add-toggle"')
    i_entrega = html.index('id="ph-entrega-chips"')
    i_notas = html.index('id="notas"')
    assert i_head < i_lineas < i_add < i_entrega < i_notas

    assert '<select name="cliente_id"' not in html          # ya no hay select de cliente
    assert f'name="cliente_id" value="{cliente_id}"' in html.replace("'", '"')
    assert '/api/precios/cliente' not in html               # sin fetch de precios
    assert '/api/clientes' not in html                      # sin fetch de habitual
    # OJO: no usar 'pedido-habitual' como token — el body lleva
    # data-pedido-habitual="1" y el CSS pedido_habitual.css, que se quedan.


def test_paso2_sin_historial_abre_panel(app, logged_client):
    from app import Cliente
    nuevo = Cliente.query.filter_by(nombre='Cliente Nuevo').first()
    html = logged_client.get(f'/pedidos/nuevo?cliente={nuevo.id}').get_data(as_text=True)
    assert 'Sin pedidos anteriores' in html
    assert 'id="ph-add-panel"' in html
    # el panel arranca abierto: el atributo hidden no está en su tag
    panel_tag = html.split('id="ph-add-panel"')[0].rsplit('<div', 1)[1]
    assert 'hidden' not in panel_tag
```

- [ ] **Step 2: Verificar que fallan** — `pytest tests/test_pedido_dos_pasos.py -q` → los 2 nuevos FAIL.

- [ ] **Step 3: Reestructurar el markup** de `pedido_form.html` en este orden (dentro del `<form>` actual, conservando IDs y clases existentes de líneas/panel/notas/footer):

```html
<input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
<input type="hidden" name="cliente_id" value="{{ (pedido.cliente_id if pedido else cliente.id) }}">
<input type="hidden" name="tipo_cambio" id="tipo_cambio" value="{{ tipo_cambio_valor }}">

<!-- ── Cabecera del cliente (server-rendered, nada aparece después) ── -->
<div class="ph-hero ph-cliente-head" id="ph-cliente-head">
  <div class="ph-cliente-head-row">
    <div class="ph-hero-nombre">{{ (pedido.cliente.nombre if pedido else cliente.nombre) }}
      {% set moneda_head = (pedido.cliente.moneda if pedido and pedido.cliente else cliente.moneda) or 'XCG' %}
      {% if moneda_head == 'USD' %}<span class="ph-cliente-moneda">USD · {{ '%.2f'|format(tipo_cambio_valor) }}</span>{% endif %}
    </div>
    <a class="ph-cambiar-cliente" id="ph-cambiar-cliente"
       href="{% if pedido %}{{ url_for('editar_pedido', pedido_id=pedido.id, cambiar=1) }}{% else %}{{ url_for('nuevo_pedido') }}{% endif %}">Cambiar</a>
  </div>
  {% if hero_meta_texto %}<div class="ph-hero-meta">{{ hero_meta_texto }}</div>{% endif %}
  {% if origen_texto %}<div class="ph-hero-origen">{{ origen_texto }}</div>{% endif %}
</div>

<!-- líneas -->
<div id="productos-body" class="ph-lineas"></div>

<!-- añadir (igual que hoy, pero sin hidden si no hay líneas) -->
<button type="button" class="ph-add-toggle" id="ph-add-toggle"
        aria-expanded="{{ 'false' if productos_pedido else 'true' }}" aria-controls="ph-add-panel">
    <span aria-hidden="true">＋</span> Añadir otro producto
</button>
<div class="ph-add-panel" id="ph-add-panel" {% if productos_pedido %}hidden{% endif %}>
    <!-- contenido del panel EXACTAMENTE como está hoy (producto TomSelect + Cajas + Añadir + motivo) -->
</div>

<!-- entrega (movida aquí, markup idéntico al actual) -->
<!-- notas (igual) -->
<!-- footer sticky (igual) -->
```

  Se ELIMINA del markup: el `<select>` de cliente + su card, `#tipo-cambio-group` visible (el hidden de arriba lo reemplaza), `#ph-hero` dinámico, `#ph-banner`, `#ph-grupos`.

- [ ] **Step 4: Podar el JS del template.** Borrar: `actualizarPreciosCliente`, `cargarPedidoHabitual`, `mostrarSelectorGrupos`, `actualizarHero`, `habilitarAgregar` y sus llamadas, `cargarPreciosDe`, el listener `change` de cliente, el TomSelect de cliente, `actualizarMoneda` (reemplazar por `const monedaActual = {{ moneda_head|tojson }};` — cuidado: se usa en el render de TomSelect de producto y en `actualizarResumen`), las referencias DOM muertas (`clienteSelect`, `heroEl`, `heroNombre`, `heroMeta`, `bannerEl`, `bannerBody`, `gruposEl`, `gruposLista`) y el check de cliente del submit (el hidden siempre está). Sembrar estado desde el servidor:

```js
const productos = {{ productos|tojson }};
const productos_pedido = {{ productos_pedido|default([])|tojson }};
const esEdicion = {{ 'true' if pedido else 'false' }};
let grupoActual = {{ grupo_clave|tojson }} || null;
const monedaActual = {{ moneda_head|tojson }};

let productosAgregados = (productos_pedido || []).map(p => ({
    id: p.id, nombre: p.nombre, cajas: p.cajas, precio: p.precio,
    habitual: ('habitual' in p) ? p.habitual : null, activa: true,
}));
```

  En `DOMContentLoaded` queda: `construirChipsEntrega()`, fijar `grupoActual` desde la primera línea si vino vacío (código actual), `actualizarTablaProductos()`, `cargarProductosEnSelect()`, delegación de tbody/chips/addToggle, TomSelect de producto, botón Añadir, Enter handlers, submit (solo check de líneas). El botón Añadir arranca HABILITADO (los precios ya vienen resueltos).

- [ ] **Step 5: Confirmación al Cambiar con líneas manuales** (solo pedido nuevo):

```js
document.getElementById('ph-cambiar-cliente').addEventListener('click', function (e) {
    const manuales = productosAgregados.some(p => p.activa && (p.habitual === null || p.habitual === undefined));
    if (!esEdicion && manuales &&
        !confirm('Tienes líneas añadidas a mano; al cambiar de cliente se pierden. ¿Continuar?')) {
        e.preventDefault();
    }
});
```

- [ ] **Step 6: CSS de cabecera** — al final de `static/css/pedido_form.css`:

```css
.ph-cliente-head-row { display: flex; align-items: baseline; justify-content: space-between; gap: 12px; }
.ph-cambiar-cliente { font-size: 0.85rem; text-decoration: underline; opacity: 0.85; white-space: nowrap; }
.ph-cliente-moneda { font-size: 0.8rem; opacity: 0.8; margin-left: 8px; }
.ph-hero-origen { margin-top: 6px; font-size: 0.85rem; opacity: 0.85; }
```

- [ ] **Step 7: Tests** — `pytest tests/test_pedido_dos_pasos.py -q` → todo PASS (incluidos los de Task 1: el seed y los tokens no cambiaron de nombre).

- [ ] **Step 8: Regresión dirigida** — `pytest tests/test_pedido_habitual.py tests/test_cajas_fraccionarias.py tests/test_consolidar_flujo.py tests/test_ofr.py -q` → verde ('impuestos distintos' vive en el flash del servidor; conservar el comentario del grupo en el JS no es necesario para los tests pero no estorba).

- [ ] **Step 9: Commit** — `git commit -am "feat(pedidos): paso 2 server-rendered, sin async ni saltos"`

### Task 4: Edición — cambiar cliente por round-trip re-cotizado

**Agente: opus** (permisos + re-cotización: la parte con más filo).

**Files:**
- Modify: `app.py` (`editar_pedido` GET)
- Modify: `tests/test_pedido_dos_pasos.py`

**Interfaces:**
- Consumes: `_productos_dicts_para_cliente`, IDs `ph-cliente-head`/`ph-cambiar-cliente` de Task 3, `pedido_cliente.html` con `destino`.
- Produces: query params `?cambiar=1` y `?cliente=M` en la ruta de edición.

- [ ] **Step 1: Tests que fallan** — añadir a `tests/test_pedido_dos_pasos.py` (fixture: crear pedido por POST como en `test_cajas_fraccionarias.py::test_editar_pedido_a_media_caja`, con producto y precio de form 20.00):

```python
def _crear_pedido_por_post(logged_client, cliente_id, producto_id, cajas='2', precio='20.00'):
    resp = logged_client.post('/pedidos/nuevo', data={
        'cliente_id': cliente_id, 'notas': '',
        'productos[0][id]': producto_id,
        'productos[0][cajas]': cajas,
        'productos[0][precio]': precio,
    }, follow_redirects=True)
    assert resp.status_code == 200
    from app import Pedido
    return Pedido.query.order_by(Pedido.id.desc()).first().id


def test_editar_muestra_cambiar_y_sin_select(app, logged_client):
    cliente_id, prods = _ids()
    pid = _crear_pedido_por_post(logged_client, cliente_id, prods['Aceite vegetal 12 x 1 L'])
    html = logged_client.get(f'/pedidos/{pid}/editar').get_data(as_text=True)
    assert 'id="ph-cambiar-cliente"' in html
    assert '<select name="cliente_id"' not in html
    assert f'cambiar=1' in html


def test_editar_cambiar_muestra_paso1(app, logged_client):
    cliente_id, prods = _ids()
    pid = _crear_pedido_por_post(logged_client, cliente_id, prods['Aceite vegetal 12 x 1 L'])
    html = logged_client.get(f'/pedidos/{pid}/editar?cambiar=1').get_data(as_text=True)
    assert 'id="paso-cliente"' in html
    assert f'/pedidos/{pid}/editar' in html   # destino apunta de vuelta a la edición


def test_editar_con_cliente_recotiza(app, logged_client):
    from app import Cliente, PrecioClienteProducto
    cliente_id, prods = _ids()
    otro = Cliente.query.filter_by(nombre='Cliente Nuevo').first()
    pid_prod = prods['Aceite vegetal 12 x 1 L']
    _db.session.add(PrecioClienteProducto(
        cliente_id=otro.id, producto_id=pid_prod, precio_base=33.44))
    _db.session.commit()

    pid = _crear_pedido_por_post(logged_client, cliente_id, pid_prod)
    html = logged_client.get(f'/pedidos/{pid}/editar?cliente={otro.id}').get_data(as_text=True)
    assert f'name="cliente_id" value="{otro.id}"' in html.replace("'", '"')
    assert '33.44' in html                       # línea re-cotizada para el cliente nuevo
```

- [ ] **Step 2: Verificar que fallan** — `pytest tests/test_pedido_dos_pasos.py -q`.

- [ ] **Step 3: Implementar el GET de edición** — en `editar_pedido`, después del guard IDOR (NO moverlo) y antes del POST branch no hace falta nada; en la rama GET (tras el POST branch), reemplazar el armado del contexto:

```python
    # ── GET (dos pasos): ?cambiar=1 → selector; ?cliente=M → re-cotizar ──
    if request.args.get('cambiar'):
        if isinstance(current_user, Vendedor) and current_user.rol.nombre != 'super_admin':
            clientes_visibles = current_user.obtener_clientes_visibles()
        else:
            clientes_visibles = Cliente.query.all()
        return render_template(
            'pedido_cliente.html',
            clientes=clientes_visibles,
            destino=url_for('editar_pedido', pedido_id=pedido.id),
            cliente_pendiente=pedido.cliente,
            grupos_cliente=None,
        )

    cliente_efectivo = pedido.cliente
    override_id = request.args.get('cliente', type=int)
    if override_id and override_id != pedido.cliente_id:
        override = db.session.get(Cliente, override_id)
        permitido = True
        if isinstance(current_user, Vendedor) and current_user.rol.nombre != 'super_admin':
            permitido = current_user.puede_crear_pedido_para_cliente(override_id)
        if override is None or not permitido:
            flash('Cliente no válido para este vendedor; se mantiene el original', 'error')
        else:
            cliente_efectivo = override

    productos_dicts = _productos_dicts_para_cliente(cliente_efectivo.id)

    productos_pedido = []
    for d in pedido.detalles:
        if not d.es_linea_pedido:
            continue
        precio = obtener_precio_producto_cliente(cliente_efectivo.id, d.producto_id, 'base')
        if precio is None:
            precio = obtener_precio_default_producto(d.producto_id, 'base')
        productos_pedido.append({
            'id': d.producto_id,
            'nombre': d.producto.nombre if d.producto else '—',
            'cajas': d.cajas,
            'precio': float(precio) if precio is not None else float(d.precio_unitario or 0),
            'habitual': None,
        })

    return render_template(
        'pedido_form.html',
        cliente=cliente_efectivo,
        productos=productos_dicts,
        productos_pedido=productos_pedido,
        pedido=pedido,
        hero_meta_texto='',
        origen_texto=('Precios re-cotizados para este cliente; nada se guarda '
                      'hasta «Actualizar pedido».') if cliente_efectivo.id != pedido.cliente_id else '',
        grupo_clave='',
        tipo_cambio_valor=1.78 if (cliente_efectivo.moneda or 'XCG') == 'USD' else float(pedido.tipo_cambio or 1.0),
    )
```

  OJO template: el hidden `cliente_id` del paso 2 debe usar `cliente.id` SIEMPRE que se pase `cliente` (Task 3 usa `pedido.cliente_id if pedido else cliente.id` — cambiar a `cliente.id` a secas, porque en edición `cliente` ya es el efectivo; verificar que Task 3 pasó `cliente=cliente_efectivo`). El título del topnav de edición sigue mostrando `PED-{{ pedido.id }}`.

- [ ] **Step 4: Tests** — `pytest tests/test_pedido_dos_pasos.py -q` → PASS; `pytest tests/test_authz_idor.py -q` → PASS (el guard no se movió).

- [ ] **Step 5: Commit** — `git commit -am "feat(pedidos): edición con cambio de cliente re-cotizado por round-trip"`

### Task 5: Suite completa y limpieza

**Agente: sonnet.**

**Files:**
- Modify: lo que la suite señale (esperado: nada o ajustes menores en tests con strings del template viejo).

- [ ] **Step 1:** `pytest tests/ -q` (suite completa). Si `test_pedido_habitual.py::test_servidor_rechaza_pedido_mezclado` (o su gemelo) fallara por el substring 'impuestos distintos': confirmar que el flash de `app.py:~5915` sigue llegando al HTML del redirect (`follow_redirects=True` re-renderiza el GET; el flash se muestra vía base.html). NO resucitar comentarios del template para que pasen tests.
- [ ] **Step 2:** Grep de código muerto: `grep -n "actualizarPreciosCliente\|cargarPedidoHabitual\|mostrarSelectorGrupos\|actualizarHero\|habilitarAgregar" templates/ static/js/ -r` → cero resultados (fuera de `pedido_habitual.css` que puede conservar clases).
- [ ] **Step 3:** Commit si hubo ajustes — `git commit -am "test: ajustes por el form en dos pasos"`

### Task 6: Verificación en navegador (orquestador)

**Agente: Fable (yo, inline — el navegador es de esta sesión).**

- [ ] Paso 1 → cliente con historial → paso 2 sembrado sin ningún salto (screenshot).
- [ ] Cliente multi-grupo → re-pregunta de grupo → paso 2 del grupo elegido.
- [ ] Cliente sin historial → paso 2 vacío con panel abierto.
- [ ] Crear pedido con media caja (0,5) → línea 0.5, subtotal correcto (no regresionar lo de hoy).
- [ ] Edición: Cambiar → selector → re-cotización visible → Actualizar pedido.
- [ ] Consola sin errores; `preview_logs` sin 500.
- [ ] Commit final si hubo retoques + resumen a JM. NO desplegar sin su OK explícito.
