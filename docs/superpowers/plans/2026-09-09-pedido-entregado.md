# Estado `entregado` — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Que `entregado` deje de ser un estado fantasma y pase a ser el estado real de «el pedido llegó al cliente», marcado por el chofer desde el teléfono.

**Architecture:** Se agrega una transición `facturado → entregado` (con su vuelta atrás) y se corrige el significado de `facturado` en las tres capas donde hoy hace doble trabajo: las guardas de inmutabilidad, el agrupado del tablero y las métricas del dashboard. La regla de inmutabilidad, hoy repetida catorce veces, pasa a tener un solo dueño. Cierra con un backfill de 960 filas en producción.

**Tech Stack:** Flask + SQLAlchemy (modelos en `app.py`, no hay `models.py`), Jinja2, pytest, PostgreSQL en producción / SQLite en tests.

**Spec:** `docs/superpowers/specs/2026-09-09-pedido-entregado-design.md`

## Global Constraints

- **Correr los tests así:** `.venv/bin/python -m pytest tests/ -q` desde la raíz, con el venv de `/Users/josedasilva/Projects/pesosapp/.venv`. **NO** forzar `DATABASE_URL`: `conftest.py` usa `sqlite:///:memory:` y un `DATABASE_URL` de archivo causa state-bleed masivo entre tests.
- **Un solo `app.test_client()` por test.** Un segundo cliente en el mismo test queda autenticado como el usuario del primero, y los tests de autorización pasarían en vacío.
- **Jinja no tiene los builtins de Python.** Nada de `timedelta`, `int`, `type` dentro de una plantilla: es un 500 en runtime, y solo en la rama que se dibuja.
- **El día local es `datetime.now(DASHBOARD_TIMEZONE).date()`**, nunca `date.today()` ni `CURRENT_DATE` de Postgres. La base de producción corre en UTC y Curaçao es UTC−4.
- **CSS de esta pantalla:** toda regla nueva va blindada con `body[data-pedidos-list-screen]`. Sin ese guard, `dark-theme.css` gana y deja texto claro sobre fondo claro.
- **`data-confirm` va en el `<form>`, nunca en el `<button>`:** `base.js` delega sobre `submit`, donde `e.target` ya es el formulario.
- **No hay migración de esquema.** `Pedido.estado` es `String(30)`; el backfill es un `UPDATE`, no un `ALTER`.
- **Estados válidos del pedido tras este cambio:** `pendiente`, `preparado`, `facturado`, `entregado`.

---

### Task 1: Un solo dueño para la inmutabilidad post-facturación

Es la tarea más importante y va primera: sin ella, cualquier commit posterior que introduzca `entregado` abre un agujero por el que un pedido ya facturado en QuickBooks vuelve a ser editable.

**Files:**
- Modify: `app.py` — agregar helper cerca de `_pedido_facturado_en_periodo_local` (~línea 1084)
- Modify: `app.py:7830, 8091, 8156, 8205, 8359, 8380, 8457, 8485, 8548, 8580, 8621, 8664, 8984, 9294`
- Test: `tests/test_pedido_inmutable.py` (crear)

**Interfaces:**
- Consumes: nada.
- Produces: `PEDIDO_INMUTABLE: tuple[str, ...]` y `_pedido_es_inmutable(pedido) -> bool`. Las tareas 2, 3 y 4 lo usan.

- [ ] **Step 1: Escribir el test que falla**

Crear `tests/test_pedido_inmutable.py`. Copiar el fixture `app`, `_seed` y `_login` de `tests/test_pedido_mover_entrega.py` (mismo patrón: rol `super_admin` + `vendedor`, un cliente, un producto), pero sembrando **un pedido en `entregado`** además de los otros:

```python
def test_un_pedido_entregado_no_se_puede_editar(app):
    c = _login(app, 'jefe')
    resp = c.post(f'/pedidos/{IDS["entregado"]}/editar', data={}, follow_redirects=False)
    assert resp.status_code in (302, 409), 'un entregado ya salió: su factura está en QBO'


def test_un_pedido_entregado_no_se_puede_eliminar(app):
    from app import Pedido
    c = _login(app, 'jefe')
    c.post(f'/pedidos/{IDS["entregado"]}/eliminar')
    assert _db.session.get(Pedido, IDS['entregado']) is not None


def test_un_pedido_entregado_no_se_puede_pesar(app):
    c = _login(app, 'jefe')
    resp = c.get(f'/pedidos/{IDS["entregado"]}/pesar', follow_redirects=False)
    assert resp.status_code == 302


def test_un_pedido_entregado_no_vuelve_a_preparado(app):
    from app import Pedido
    c = _login(app, 'jefe')
    c.post(f'/pedidos/{IDS["entregado"]}/marcar_preparado')
    assert _db.session.get(Pedido, IDS['entregado']).estado == 'entregado'


def test_un_pedido_entregado_no_se_vuelve_a_facturar(app):
    from unittest.mock import patch
    c = _login(app, 'jefe')
    with patch('app.requests.post') as mock_post:
        c.post(f'/pedidos/{IDS["entregado"]}/facturar')
    mock_post.assert_not_called()


def test_el_facturado_sigue_siendo_inmutable(app):
    """La regla vieja no se pierde al generalizarla."""
    from app import Pedido
    c = _login(app, 'jefe')
    c.post(f'/pedidos/{IDS["facturado"]}/eliminar')
    assert _db.session.get(Pedido, IDS['facturado']) is not None
```

- [ ] **Step 2: Correr los tests y verlos fallar**

Run: `.venv/bin/python -m pytest tests/test_pedido_inmutable.py -q`
Expected: los cinco primeros FALLAN (el pedido entregado se edita, se borra, se pesa, vuelve a preparado y se re-factura). `test_el_facturado_sigue_siendo_inmutable` PASA — es el control: si también falla, el seed está mal, no el código.

- [ ] **Step 3: Agregar el helper**

En `app.py`, justo antes de `def _pedido_facturado_en_periodo_local(` (~línea 1084):

```python
# Estados en los que el pedido ya salió del taller: su factura está en
# QuickBooks y cualquier cambio local divergiría de ella. `entregado` entra
# acá por la misma razón que `facturado` y no por una nueva: se factura ANTES
# de entregar, así que todo lo entregado está facturado.
PEDIDO_INMUTABLE = ('facturado', 'entregado')


def _pedido_es_inmutable(pedido):
    """True si el pedido ya no admite cambios locales.

    Esta regla estaba escrita catorce veces como `estado == 'facturado'`. Al
    aparecer `entregado` las catorce lo dejaban pasar, o sea que marcar un
    pedido como entregado lo volvía editable, borrable y pesable otra vez —
    justo después de que su factura salió a QuickBooks. Una regla, un dueño.
    """
    return (pedido.estado or '').strip().lower() in PEDIDO_INMUTABLE
```

- [ ] **Step 4: Reemplazar las catorce guardas**

En cada una de estas líneas, cambiar `if pedido.estado == 'facturado':` por `if _pedido_es_inmutable(pedido):`. **Los mensajes de flash no se tocan**: dicen «facturado» y un pedido entregado también lo está.

Líneas: `7830`, `8091`, `8156`, `8205`, `8359`, `8380`, `8457`, `8485`, `8548`, `8580`, `8621`, `8664`, `8984`, `9294`.

Buscarlas con: `grep -n "estado == 'facturado'" app.py`

**Cuidado — NO tocar estas, que no son guardas de inmutabilidad:**
- `1086` (`_pedido_facturado_en_periodo_local`) → es Task 6.
- `2213, 2337, 2441, 2501, 5451, 5860, 5890, 5926, 5147` → métricas, Task 6.
- `3902, 6631-6634, 6714, 6737, 6760, 6797` → tablero y lista, Tasks 3 y 4.
- `9382` (`pedido.estado = 'facturado'`) → es una asignación, no una guarda.
- `9073-9209` → un diccionario local de precios que se llama `facturado`; no tiene nada que ver.

- [ ] **Step 5: Correr los tests y verlos pasar**

Run: `.venv/bin/python -m pytest tests/test_pedido_inmutable.py -q`
Expected: los 6 PASAN.

Después la suite entera: `.venv/bin/python -m pytest tests/ -q`
Expected: 1181 passed, 1 skipped (o más, con los nuevos). Cero fallos.

- [ ] **Step 6: Verificar que la guarda protege de verdad**

Revertir UNA de las catorce a `== 'facturado'` (por ejemplo la de eliminar, `8156`), correr `tests/test_pedido_inmutable.py` y confirmar que `test_un_pedido_entregado_no_se_puede_eliminar` **falla**. Volver a dejarla como estaba. En este repo ya pasó dos veces que un test verde no protegía nada.

- [ ] **Step 7: Commit**

```bash
git add app.py tests/test_pedido_inmutable.py
git commit -m "refactor(pedidos): un solo dueño para la inmutabilidad post-facturación

La regla «un pedido facturado no se toca» estaba escrita catorce veces como
\`estado == 'facturado'\`. Con \`entregado\` en escena, las catorce lo dejarían
pasar: marcar entregado volvería el pedido editable, borrable y pesable otra
vez, con su factura ya en QuickBooks.

Ahora es \`_pedido_es_inmutable\`, que cubre los dos estados. Los mensajes no
cambian: un pedido entregado también está facturado.

Sin cambio de comportamiento para \`facturado\`, que es lo que el test de
control comprueba."
```

---

### Task 2: La transición `facturado → entregado` y su vuelta

**Files:**
- Modify: `app.py` — ruta nueva junto a `mover_entrega_pedido` (~línea 8070)
- Test: `tests/test_pedido_entregado.py` (crear)

**Interfaces:**
- Consumes: `_pedido_es_inmutable` (Task 1) — **no** se usa como guarda acá; esta ruta necesita su propia regla porque justamente cambia un estado inmutable de forma controlada.
- Produces: endpoints `entregar_pedido` (`POST /pedidos/<id>/entregar`) y `deshacer_entrega_pedido` (`POST /pedidos/<id>/entrega/deshacer`). La Task 5 los llama por `url_for`.

- [ ] **Step 1: Escribir los tests que fallan**

Crear `tests/test_pedido_entregado.py`, con el mismo fixture/`_seed`/`_login` que `tests/test_pedido_mover_entrega.py`. El seed tiene que dejar en `IDS` **exactamente estas cinco claves**, que también usa la Task 5 sobre este mismo archivo:

| Clave | Estado | `fecha_entrega` |
|---|---|---|
| `pendiente` | `pendiente` | hoy local |
| `preparado` | `preparado` | hoy local |
| `facturado` | `facturado` | hoy local |
| `entregado_hoy` | `entregado` | hoy local |
| `entregado_viejo` | `entregado` | hoy local − 30 días |

Todos del **Cliente A**, salvo que la Task 5 no necesita otro. `vend_b` no tiene al Cliente A asignado, que es lo que usa el test de IDOR. El día local se calcula con `datetime.now(DASHBOARD_TIMEZONE).date()`, nunca con `date.today()`.

```python
def test_un_facturado_se_marca_entregado(app):
    from app import Pedido
    c = _login(app, 'jefe')
    resp = c.post(f'/pedidos/{IDS["facturado"]}/entregar')
    assert resp.status_code == 302
    assert _db.session.get(Pedido, IDS['facturado']).estado == 'entregado'


def test_un_pendiente_no_se_marca_entregado(app):
    """El guarda que protege la factura: si se pudiera, el pedido saldría de la
    cola sin factura y no la generaría nunca."""
    from app import Pedido
    c = _login(app, 'jefe')
    c.post(f'/pedidos/{IDS["pendiente"]}/entregar')
    assert _db.session.get(Pedido, IDS['pendiente']).estado == 'pendiente'


def test_un_preparado_no_se_marca_entregado(app):
    from app import Pedido
    c = _login(app, 'jefe')
    c.post(f'/pedidos/{IDS["preparado"]}/entregar')
    assert _db.session.get(Pedido, IDS['preparado']).estado == 'preparado'


def test_marcar_entregado_deja_rastro_con_la_hora(app):
    import json
    from app import PedidoEvento
    c = _login(app, 'jefe')
    c.post(f'/pedidos/{IDS["facturado"]}/entregar')
    ev = PedidoEvento.query.filter_by(
        pedido_id=IDS['facturado'], tipo='entregado').one()
    assert json.loads(ev.meta) == {'anterior': 'facturado', 'nueva': 'entregado'}
    assert ev.created_at is not None


def test_deshacer_devuelve_a_facturado(app):
    from app import Pedido
    c = _login(app, 'jefe')
    c.post(f'/pedidos/{IDS["entregado_hoy"]}/entrega/deshacer')
    assert _db.session.get(Pedido, IDS['entregado_hoy']).estado == 'facturado'


def test_deshacer_deja_su_propio_rastro(app):
    from app import PedidoEvento
    c = _login(app, 'jefe')
    c.post(f'/pedidos/{IDS["entregado_hoy"]}/entrega/deshacer')
    assert PedidoEvento.query.filter_by(
        pedido_id=IDS['entregado_hoy'], tipo='entrega_deshecha').count() == 1


def test_deshacer_no_toca_un_facturado(app):
    from app import Pedido
    c = _login(app, 'jefe')
    c.post(f'/pedidos/{IDS["facturado"]}/entrega/deshacer')
    assert _db.session.get(Pedido, IDS['facturado']).estado == 'facturado'


def test_vendedor_ajeno_no_marca_entregado(app):
    from app import Pedido
    c = _login(app, 'vend_b')          # vend_b no ve al Cliente A
    resp = c.post(f'/pedidos/{IDS["facturado"]}/entregar')
    assert resp.status_code in (302, 403)
    assert _db.session.get(Pedido, IDS['facturado']).estado == 'facturado'


def test_next_a_otro_host_no_redirige_afuera(app):
    c = _login(app, 'jefe')
    resp = c.post(f'/pedidos/{IDS["facturado"]}/entregar',
                  data={'next': 'https://evil.com/x'})
    assert 'evil.com' not in resp.headers.get('Location', '')
```

- [ ] **Step 2: Correr y verlos fallar**

Run: `.venv/bin/python -m pytest tests/test_pedido_entregado.py -q`
Expected: FALLAN con 404 (las rutas no existen). Los tres de «no cambia nada» pueden pasar en vacío — es esperado, el Step 6 los pone a prueba.

- [ ] **Step 3: Escribir las dos rutas**

En `app.py`, inmediatamente después de `mover_entrega_pedido` (que termina con `return _volver_a('lista_pedidos')`, ~línea 8140):

```python
@app.route('/pedidos/<int:pedido_id>/entregar', methods=['POST'])
@login_required
@requiere_permiso_recurso('pedidos', 'editar')
def entregar_pedido(pedido_id):
    """Marca el pedido como entregado al cliente.

    Hasta ahora `facturado` hacía de «terminado», pero acá se factura ANTES de
    que salga el camión —a veces el día anterior—, así que no había forma de
    contestar «¿qué está facturado pero todavía no llegó?». El chofer marca
    esto desde el teléfono al dejar la mercadería, y la hora del evento es la
    hora real de la entrega.
    """
    pedido = Pedido.query.get_or_404(pedido_id)

    if not _user_can_manage_pedido(pedido):
        flash('No tienes permisos para modificar este pedido', 'error')
        return _volver_a('lista_pedidos')

    if pedido.estado == 'entregado':
        return _volver_a('lista_pedidos')

    # SOLO desde facturado. Si se pudiera marcar entregado un pedido sin
    # factura, ese pedido saldría de la cola sin haberla generado y no la
    # generaría nunca: es plata que se pierde en silencio, que es la peor
    # forma de perderla. Un preparado que ya salió hay que facturarlo primero.
    if pedido.estado != 'facturado':
        flash(f'PED-{pedido.id} todavía no está facturado. '
              f'Se factura primero y después se marca entregado.', 'warning')
        return _volver_a('lista_pedidos')

    pedido.estado = 'entregado'
    _log_pedido_evento(
        pedido, 'entregado', 'Pedido entregado al cliente',
        meta={'anterior': 'facturado', 'nueva': 'entregado'},
    )
    db.session.commit()
    flash(f'PED-{pedido.id} entregado.', 'success')
    return _volver_a('lista_pedidos')


@app.route('/pedidos/<int:pedido_id>/entrega/deshacer', methods=['POST'])
@login_required
@requiere_permiso_recurso('pedidos', 'editar')
def deshacer_entrega_pedido(pedido_id):
    """Vuelve un `entregado` a `facturado`.

    El chofer va a tocar la tarjeta equivocada alguna vez: un toque
    irreversible en un teléfono que se maneja con una mano, en la calle, es un
    callejón sin salida. No hay ventana de tiempo —una regla horaria solo
    agrega un caso raro que falla justo cuando hace falta—; lo que acota es la
    tarjeta, que solo dibuja el botón dentro del grupo «Hoy».
    """
    pedido = Pedido.query.get_or_404(pedido_id)

    if not _user_can_manage_pedido(pedido):
        flash('No tienes permisos para modificar este pedido', 'error')
        return _volver_a('lista_pedidos')

    if pedido.estado != 'entregado':
        return _volver_a('lista_pedidos')

    pedido.estado = 'facturado'
    _log_pedido_evento(
        pedido, 'entrega_deshecha', 'Se deshizo la marca de entregado',
        meta={'anterior': 'entregado', 'nueva': 'facturado'},
    )
    db.session.commit()
    flash(f'PED-{pedido.id} vuelve a «por entregar».', 'info')
    return _volver_a('lista_pedidos')
```

- [ ] **Step 4: Correr y verlos pasar**

Run: `.venv/bin/python -m pytest tests/test_pedido_entregado.py -q`
Expected: los 9 PASAN.

- [ ] **Step 5: Correr la suite entera**

Run: `.venv/bin/python -m pytest tests/ -q`
Expected: cero fallos.

- [ ] **Step 6: Verificar que los guardas protegen**

Cambiar `if pedido.estado != 'facturado':` por `if False:` y confirmar que `test_un_pendiente_no_se_marca_entregado` y `test_un_preparado_no_se_marca_entregado` **fallan**. Restaurar. Repetir con el guarda de `_user_can_manage_pedido` y `test_vendedor_ajeno_no_marca_entregado`.

- [ ] **Step 7: Commit**

```bash
git add app.py tests/test_pedido_entregado.py
git commit -m "feat(pedidos): la transición facturado → entregado, con vuelta atrás

Acá se factura ANTES de que salga el camión, así que \`facturado\` no significa
«llegó al cliente». El chofer marca la entrega desde el teléfono y la hora del
evento es la hora real.

Solo desde \`facturado\`: marcar entregado algo sin factura lo sacaría de la
cola sin generarla nunca. Y con deshacer, porque un toque irreversible en la
calle, con una mano, es un callejón sin salida."
```

---

### Task 3: El tablero deja de dar por cerrado lo que no salió

**Files:**
- Modify: `app.py:3877-3918` (`_agrupar_tablero`)
- Modify: `app.py:6797` (la consulta que alimenta el tablero)
- Test: `tests/test_pedidos_tablero.py` (extender)

**Interfaces:**
- Consumes: nada de las tareas anteriores.
- Produces: ningún símbolo nuevo. Cambia el contrato de `_agrupar_tablero`: «hecho» pasa de `facturado` a `entregado`.

- [ ] **Step 1: Escribir los tests que fallan**

En `tests/test_pedidos_tablero.py`, que ya tiene el helper `_p(estado, dias, id)` y `_claves`/`_pedidos_de`, agregar:

```python
def test_el_facturado_sin_entregar_con_fecha_vencida_NO_desaparece():
    """El agujero que motivó todo esto: se factura antes de que salga el
    camión, así que un facturado con la entrega vencida es trabajo que no se
    hizo. Hoy `_agrupar_tablero` lo saltea y nadie se entera."""
    grupos = _agrupar_tablero([_p('facturado', dias=-2)], HOY)
    assert _claves(grupos) == ['atrasados']


def test_el_facturado_de_hoy_es_trabajo_no_archivo():
    grupos = _agrupar_tablero([_p('facturado', dias=0)], HOY)
    assert _claves(grupos) == ['hoy']


def test_el_facturado_futuro_va_a_proximos():
    grupos = _agrupar_tablero([_p('facturado', dias=3)], HOY)
    assert _claves(grupos) == ['proximos']


def test_el_entregado_de_hoy_se_queda_en_hoy():
    """Decisión heredada del spec del tablero: lo hecho no desaparece, se
    marca. Si desapareciera, el tablero se vacía a media tarde y se pierde la
    otra mitad del trabajo, que es ver si el día cerró completo."""
    grupos = _agrupar_tablero([_p('entregado', dias=0)], HOY)
    assert _claves(grupos) == ['hoy']


def test_el_entregado_fuera_de_hoy_es_archivo():
    grupos = _agrupar_tablero(
        [_p('entregado', dias=-30, id=1),
         _p('entregado', dias=None, id=2),
         _p('entregado', dias=9, id=3)],
        HOY,
    )
    assert grupos == []
```

Y **corregir el test existente** `test_el_archivo_no_entra_al_tablero`, que hoy afirma que un `facturado` viejo no entra al tablero. Después de este cambio eso es falso a propósito: pasa a usar `entregado`.

```python
def test_el_archivo_no_entra_al_tablero():
    """El archivo ahora es `entregado`, no `facturado`: un facturado sin
    entregar es trabajo pendiente, no archivo."""
    grupos = _agrupar_tablero(
        [_p('entregado', dias=-30, id=1),
         _p('entregado', dias=None, id=2),
         _p('entregado', dias=9, id=3)],
        HOY,
    )
    assert grupos == []
```

- [ ] **Step 2: Correr y verlos fallar**

Run: `.venv/bin/python -m pytest tests/test_pedidos_tablero.py -q`
Expected: `test_el_facturado_sin_entregar_con_fecha_vencida_NO_desaparece` falla con `[] != ['atrasados']` — el `continue` de `app.py:3902` lo saltea. Los de `entregado` fallan porque hoy `entregado` cae en `sin_fecha`/`atrasados` según el caso.

- [ ] **Step 3: Cambiar el agrupado**

En `app.py`, dentro de `_agrupar_tablero`, reemplazar el bloque del loop (líneas ~3896-3908):

```python
    for pedido in pedidos:
        entrega = pedido.fecha_entrega
        if entrega == hoy_local:
            hoy.append(pedido)
        elif pedido.estado == 'entregado':
            # Entregado y no es de hoy: es archivo, no tablero.
            #
            # Antes acá decía `facturado`, y ese era el agujero: se factura
            # ANTES de que salga el camión, así que un facturado con la entrega
            # vencida es trabajo que NO se hizo, y este `continue` lo hacía
            # desaparecer del tablero al día siguiente. Ni Atrasados, ni Hoy,
            # ni Próximos: trabajo invisible, que es el peor fallo posible en
            # una herramienta operativa.
            continue
        elif entrega is None:
            sin_fecha.append(pedido)
        elif entrega < hoy_local:
            atrasados.append(pedido)
        else:
            proximos.append(pedido)
```

Y actualizar el docstring de la función: donde dice «`Hoy` lleva CUALQUIER estado, facturados incluidos», que diga «entregados incluidos, marcados como hechos».

- [ ] **Step 4: Cambiar la consulta que alimenta el tablero**

En `app.py:6797`, dentro de `lista_pedidos`:

```python
        pedidos_tablero = base_query_tablero.filter(
            or_(Pedido.estado != 'entregado', Pedido.fecha_entrega == hoy_local)
        ).order_by(
```

Era `Pedido.estado != 'facturado'`. Sin este cambio, el `_agrupar_tablero` corregido nunca vería los facturados atrasados porque la consulta ya los filtró antes.

- [ ] **Step 5: Correr y verlos pasar**

Run: `.venv/bin/python -m pytest tests/test_pedidos_tablero.py -q`
Expected: todos PASAN.

- [ ] **Step 6: Commit**

```bash
git add app.py tests/test_pedidos_tablero.py
git commit -m "fix(pedidos): el facturado sin entregar dejaba de existir al día siguiente

\`_agrupar_tablero\` hacía \`continue\` sobre cualquier facturado que no fuera de
hoy. Como se factura ANTES de que salga el camión, un pedido facturado el lunes
para entregar el lunes que no sale, el martes no está en ningún grupo: ni
Atrasados, ni Hoy, ni Próximos. Trabajo invisible.

Ahora el archivo es \`entregado\` y \`facturado\` vuelve a ser trabajo: aparece en
Atrasados si se pasó la fecha."
```

---

### Task 4: La lista deja de esconder los entregados

**Files:**
- Modify: `app.py:6541-6543` (lista blanca de `estado`)
- Modify: `app.py:6609` (el filtro que esconde)
- Modify: `app.py:6630-6636` (`orden_optimizado`)
- Modify: `app.py:6653, 6694` (los dicts de `status_counts`)
- Modify: `app.py:6714, 6737` (el cálculo de `vencido`)
- Modify: `app.py:6760` (el `case` del orden por estado)
- Test: `tests/test_pedidos_lista_entregado.py` (crear)

**Interfaces:**
- Consumes: nada.
- Produces: `?estado=entregado` como filtro válido; `status_counts['entregado']`.

- [ ] **Step 1: Escribir los tests que fallan**

Crear `tests/test_pedidos_lista_entregado.py` con el mismo fixture/seed (un pedido `entregado`, uno `facturado`, uno `pendiente`):

```python
def test_el_entregado_no_desaparece_de_la_lista(app):
    """`app.py:6609` filtraba `estado != 'entregado'` sobre base_query, antes
    de los conteos: el pedido desaparecía del tablero, de la lista, de
    ?estado=todos y hasta del total. El estado que significa «salió bien» era
    el que borraba el pedido de la vista."""
    c = _login(app, 'jefe')
    html = c.get('/pedidos?estado=todos').get_data(as_text=True)
    assert f'PED-{IDS["entregado"]}' in html


def test_hay_filtro_por_entregado(app):
    c = _login(app, 'jefe')
    html = c.get('/pedidos?estado=entregado').get_data(as_text=True)
    assert f'PED-{IDS["entregado"]}' in html
    assert f'PED-{IDS["pendiente"]}' not in html


def test_el_entregado_cuenta_en_el_total(app):
    c = _login(app, 'jefe')
    html = c.get('/pedidos?estado=todos').get_data(as_text=True)
    # El pie dice «1–N de TOTAL»; con 3 pedidos sembrados el total es 3.
    assert 'de 3' in html or '1–3' in html


def test_un_entregado_no_esta_vencido(app):
    """Se entregó: no hay nada atrasado que hacer con él."""
    c = _login(app, 'jefe')
    html = c.get('/pedidos?estado=vencido').get_data(as_text=True)
    assert f'PED-{IDS["entregado"]}' not in html


def test_un_facturado_con_entrega_pasada_SI_esta_vencido(app):
    """El contrapunto: facturado ya no significa terminado."""
    c = _login(app, 'jefe')
    html = c.get('/pedidos?estado=vencido').get_data(as_text=True)
    assert f'PED-{IDS["facturado_vencido"]}' in html
```

- [ ] **Step 2: Correr y verlos fallar**

Run: `.venv/bin/python -m pytest tests/test_pedidos_lista_entregado.py -q`
Expected: FALLAN. El primero es el que más importa: si pasa sin tocar nada, el seed no está creando el pedido entregado.

- [ ] **Step 3: Sacar el filtro que esconde**

En `app.py`, en la construcción de `base_query` (~línea 6606-6610), eliminar el `.filter(...)` completo:

```python
    ).options(
        joinedload(Pedido.cliente),
        selectinload(Pedido.detalles).selectinload(DetallePedido.cajas_pesadas),
        selectinload(Pedido.detalles).selectinload(DetallePedido.producto),
    )
```

Es decir: se borra `.filter(\n        Pedido.estado != 'entregado'\n    )`. **No se reemplaza por nada**: los entregados son parte del archivo y tienen que verse.

- [ ] **Step 4: Agregar `entregado` a la lista blanca**

`app.py:6541-6543`:

```python
    estado = estado if estado in {
        'todos', 'pendiente', 'preparado', 'facturado', 'entregado',
        'hoy', 'vencido', 'por_preparar',
    } else 'todos'
```

- [ ] **Step 5: Hundir `entregado` al fondo, no `facturado`**

`app.py:6630-6636`. El bloque `orden_optimizado` pasa a:

```python
    orden_optimizado = [
        db.case((Pedido.estado == 'entregado', 1), else_=0),
        db.case((Pedido.estado == 'entregado', 0),
                (Pedido.fecha_entrega.is_(None), 1), else_=0),
        db.case((Pedido.estado == 'entregado', None),
                else_=Pedido.fecha_entrega).asc(),
        Pedido.id.desc(),
    ]
```

El motivo del bloque no cambia y hay que conservar el comentario que ya está: dentro del trabajo terminado no hay urgencia que ordenar, y ordenarlo por `fecha_entrega` ascendente dejaba lo último hecho fuera de la primera página — de ahí salió «se perdió el pedido después de facturarlo».

- [ ] **Step 6: Conteos y vencidos**

`app.py:6653` y `6694`, agregar la clave a los dos dicts de `status_counts`:

```python
                    'facturado': 0,
                    'entregado': 0,
```

`app.py:6714` (el conteo de `vencido`) y `6737` (el filtro de `?estado=vencido`): cambiar `Pedido.estado != 'facturado'` por `Pedido.estado != 'entregado'`. Un facturado con la entrega pasada **sí** está vencido; un entregado no.

`app.py:6760`, el `case` del orden por columna «estado», agregar el escalón:

```python
            'estado': db.case(
                (Pedido.estado == 'pendiente', 0),
                (Pedido.estado == 'preparado', 1),
                (Pedido.estado == 'facturado', 2),
                (Pedido.estado == 'entregado', 3),
                else_=4,
            ),
```

- [ ] **Step 7: Correr y verlos pasar**

Run: `.venv/bin/python -m pytest tests/test_pedidos_lista_entregado.py tests/test_pedidos_tablero.py -q`
Expected: todos PASAN.

Después la suite entera. **Rotura esperada:** cualquier test que cuente pedidos en `/pedidos` puede cambiar de número al dejar de esconder los entregados. Revisar `tests/test_pedidos_lista_entrega.py` y `tests/test_dashboard_verdad_y_enlaces.py`, que leen markup exacto. Si fallan por el conteo y no por la funcionalidad, ajustar el número esperado — **no** el código.

- [ ] **Step 8: Commit**

```bash
git add app.py tests/test_pedidos_lista_entregado.py
git commit -m "fix(pedidos): marcar entregado ya no borra el pedido de la pantalla

\`app.py:6609\` filtraba \`estado != 'entregado'\` sobre base_query, antes de los
conteos. Un pedido entregado desaparecía del tablero, de la lista, de
?estado=todos y hasta del total «Ver los N pedidos». El estado que significa
«esto salió bien» era el que lo borraba de la vista.

Además \`entregado\` pasa a ser lo que se hunde al fondo del listado (era
\`facturado\`) y deja de contar como vencido, mientras que un facturado con la
entrega pasada ahora sí cuenta."
```

---

### Task 5: El botón en la tarjeta

**Files:**
- Modify: `templates/_pedido_card_cuerpo.html` (bloque `.pc-actions`, ~línea 113 en adelante)
- Modify: `static/css/pedidos_list.css` (después del bloque `.status-pill.facturado`, ~línea 623)
- Test: `tests/test_pedido_entregado.py` (extender)

**Interfaces:**
- Consumes: `entregar_pedido` y `deshacer_entrega_pedido` (Task 2), vía `url_for`.
- Produces: nada que otras tareas usen.

- [ ] **Step 1: Escribir los tests que fallan**

Agregar a `tests/test_pedido_entregado.py`. Reusar el helper `_tarjeta(html, pedido_id)` de `tests/test_pedido_mover_entrega.py` (**copiarlo, no importarlo**: recorta el bloque de UNA tarjeta buscando `data-href="/pedidos/<id>/detalles"`, porque `PED-<id>` aparece varias veces dentro de la misma tarjeta y un recorte por ese texto da falsos rojos).

```python
def test_la_tarjeta_de_un_facturado_ofrece_entregar(app):
    c = _login(app, 'jefe')
    tarjeta = _tarjeta(c.get('/pedidos').get_data(as_text=True), IDS['facturado'])
    assert f'/pedidos/{IDS["facturado"]}/entregar' in tarjeta


def test_la_tarjeta_de_un_pendiente_no_ofrece_entregar(app):
    """Todavía no está facturado: la ruta lo rechaza, así que el botón solo
    serviría para hacer rebotar al chofer."""
    c = _login(app, 'jefe')
    tarjeta = _tarjeta(c.get('/pedidos').get_data(as_text=True), IDS['pendiente'])
    assert '/entregar' not in tarjeta


def test_el_entregado_de_hoy_ofrece_deshacer(app):
    c = _login(app, 'jefe')
    tarjeta = _tarjeta(c.get('/pedidos').get_data(as_text=True), IDS['entregado_hoy'])
    assert f'/pedidos/{IDS["entregado_hoy"]}/entrega/deshacer' in tarjeta


def test_el_entregado_del_archivo_no_ofrece_deshacer(app):
    """En el archivo el botón es solo un toque equivocado esperando."""
    c = _login(app, 'jefe')
    html = c.get('/pedidos?estado=entregado').get_data(as_text=True)
    tarjeta = _tarjeta(html, IDS['entregado_viejo'])
    assert '/entrega/deshacer' not in tarjeta
```

Las claves `entregado_hoy` y `entregado_viejo` ya vienen del seed declarado en la Task 2; no hay que agregar nada.

- [ ] **Step 2: Correr y verlos fallar**

Run: `.venv/bin/python -m pytest tests/test_pedido_entregado.py -q`
Expected: los cuatro nuevos FALLAN.

- [ ] **Step 3: Agregar los botones a la tarjeta**

En `templates/_pedido_card_cuerpo.html`, dentro de `<div class="pc-actions">`, después del bloque `{% if puede_facturar %}…{% endif %}` y antes de `{% if puede_editar %}`:

```jinja
          {# La acción del chofer. Solo sobre un facturado: la ruta rechaza
             cualquier otro estado, así que el botón en un pendiente solo
             serviría para hacerlo rebotar. #}
          {% if pedido.estado == 'facturado' %}
          <form action="{{ url_for('entregar_pedido', pedido_id=pedido.id) }}" method="POST"
                class="pc-action-form">
            <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
            <input type="hidden" name="next" value="{{ url_actual or url_for('lista_pedidos') }}">
            <button type="submit" class="pc-action-main"
                    data-submit-label="Marcando…"
                    aria-label="Marcar PED-{{ pedido.id }} como entregado">
              <i class="fa-solid fa-truck" aria-hidden="true"></i> Entregado
            </button>
          </form>
          {% endif %}
          {# Deshacer, SOLO mientras el pedido esté en el día. La ruta lo
             acepta siempre; lo que acota es la tarjeta, para que el archivo de
             960 pedidos no se llene de botones que invitan a un toque
             equivocado. #}
          {% if pedido.estado == 'entregado' and pedido.fecha_entrega == hoy_local %}
          <form action="{{ url_for('deshacer_entrega_pedido', pedido_id=pedido.id) }}" method="POST"
                class="pc-action-form">
            <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
            <input type="hidden" name="next" value="{{ url_actual or url_for('lista_pedidos') }}">
            <button type="submit" class="pc-action-btn" title="Deshacer la entrega"
                    aria-label="Deshacer la entrega de PED-{{ pedido.id }}">
              <i class="fa-solid fa-rotate-left"></i>
            </button>
          </form>
          {% endif %}
```

**Nota:** `data-submit-label` solo lo lee el handler de `form[data-confirm]` en `base.js`. Este formulario **no** confirma —marcar entregado es reversible—, así que ese atributo no hace nada. Se deja fuera: en el commit anterior de esta rama ya se quitó por atributo muerto. Escribir el `<button>` **sin** `data-submit-label`.

Además, actualizar la línea de `tiene_acciones` (~línea 64) para que un entregado del día dibuje el bloque:

```jinja
      {% set puede_entregar  = pedido.estado == 'facturado' %}
      {% set puede_deshacer  = pedido.estado == 'entregado' and pedido.fecha_entrega == hoy_local %}
      {% set tiene_acciones = puede_editar or puede_facturar or puede_eliminar or tiene_factura or puede_entregar or puede_deshacer %}
```

Y usar `puede_entregar` / `puede_deshacer` en los dos `{% if %}` de arriba en vez de repetir la condición.

- [ ] **Step 4: Agregar la píldora de estado**

En `static/css/pedidos_list.css`, después del bloque `.status-pill.facturado` (~línea 623):

```css
/* `entregado` es el único estado que faltaba: la píldora salía sin fondo y con
   el color que le diera `dark-theme.css`. Gris azulado y no verde: el verde ya
   es `facturado`, y dos verdes contiguos en la misma tarjeta no distinguen
   nada. */
body[data-pedidos-list-screen] .status-pill.entregado {
  background: color-mix(in srgb, var(--color-text-subtle, #64748b) 18%, transparent) !important;
  color: #334155 !important;
}

body[data-pedidos-list-screen] .estado-badge.estado-entregado {
  background: color-mix(in srgb, var(--color-text-subtle, #64748b) 18%, transparent) !important;
  color: #334155 !important;
}
```

- [ ] **Step 5: El test que le faltaba al spec — que el detalle deje de mentir**

El spec promete que «la barra de progreso deja de mentir en los 973 pedidos», pero eso hoy **no lo comprueba nadie**. La buena noticia es que no hay que escribir código: `_detail_timeline.html:13` ya tiene `{'...': 2, 'entregado': 3}` en su `active_map` y `_detail_hero.html:46` ya tiene el icono de camión. Estaban escritos y correctos; lo único que faltaba era que algún pedido llegara a ese estado.

Como no hay código que escribir, el test es una **red contra la regresión**: si alguien toca ese mapa, se entera.

```python
def test_el_detalle_de_un_entregado_llega_al_ultimo_paso(app):
    """Los 973 pedidos se veían como 3 de 4 para siempre porque el 4º paso era
    inalcanzable. `active_map` ya contemplaba `entregado`; faltaba que algún
    pedido llegara ahí."""
    c = _login(app, 'jefe')
    html = c.get(f'/pedidos/{IDS["entregado_hoy"]}/detalles').get_data(as_text=True)
    # El 4º paso es el ACTUAL, y por lo tanto ninguno queda pendiente.
    assert 'detail-stepper-item is-current' in html
    assert 'detail-stepper-item is-pending' not in html, \
        'con el pedido entregado ningún paso del progreso queda gris'
```

Correr: `.venv/bin/python -m pytest tests/test_pedido_entregado.py -k detalle -q`

Si falla, **no tocar el test**: leer el HTML que devuelve y ajustar la aserción a las clases reales que emite `_detail_timeline.html` (`is-done` / `is-current` / `is-pending`). Lo que tiene que quedar comprobado es que ningún paso queda en `is-pending`.

- [ ] **Step 6: Correr y verlos pasar**

Run: `.venv/bin/python -m pytest tests/test_pedido_entregado.py -q`
Expected: todos PASAN.

- [ ] **Step 7: Verificar en el navegador**

Levantar el preview (`preview_start` con la config `pesosapp` del worktree; si el template no se recarga, **reiniciar el server**: sin `debug`, Jinja cachea las plantillas). Login `admin` / `Preview123!`.

Comprobar **midiendo el render**, no leyendo el CSS:
1. La píldora `entregado`: `getComputedStyle` sobre `.status-pill.entregado` — que `backgroundColor` no sea `rgba(0,0,0,0)` y el contraste contra el fondo de la tarjeta se lea.
2. Facturar → marcar entregado → el pedido queda en «Hoy» marcado hecho.
3. Deshacer → vuelve a «por entregar» en el mismo grupo.
4. A 375px: que la fila de acciones no desborde. `document.documentElement.scrollWidth <= innerWidth`.
5. `document.elementFromPoint` sobre el centro del botón «Entregado» devuelve el botón y no otra cosa.
6. Abrir el detalle de un pedido entregado: los cuatro pasos con tilde, ninguno gris.

- [ ] **Step 8: Commit**

```bash
git add templates/_pedido_card_cuerpo.html static/css/pedidos_list.css tests/test_pedido_entregado.py
git commit -m "feat(pedidos): botón «Entregado» en la tarjeta, con deshacer en el día

El botón aparece solo sobre un facturado (la ruta rechaza el resto) y el
deshacer solo mientras el pedido siga en el grupo «Hoy», que es donde trabaja
el chofer: en el archivo de 960 sería un toque equivocado esperando.

Agrega la píldora \`entregado\`, que era el único estado sin estilo propio."
```

---

### Task 6: Que el dashboard siga diciendo la verdad

Decisión de JM (2026-09-09): los contadores cuentan `facturado + entregado`.

**Files:**
- Modify: `app.py:1084-1096` (`_pedido_facturado_en_periodo_local`)
- Modify: `app.py:2213, 2244, 2337, 2424, 2441, 2501, 5147, 5451, 5860, 5890, 5926`
- Test: `tests/test_dashboard_entregado.py` (crear)

**Interfaces:**
- Consumes: `PEDIDO_INMUTABLE` (Task 1). Coincide exactamente con «se facturó»: se factura antes de entregar, así que todo lo entregado está facturado.
- Produces: nada nuevo.

- [ ] **Step 1: Escribir el test que falla**

```python
def test_un_pedido_entregado_sigue_contando_como_facturado(app):
    """Tras el backfill, 960 pedidos pasan a `entregado`. Si el dashboard
    sigue contando solo `facturado`, las cifras caen de 964 a 4 sin que nadie
    haya dejado de facturar: una regresión silenciosa en números que JM mira
    todos los días."""
    from app import _pedido_facturado_en_periodo_local, Pedido
    from datetime import date, datetime
    p = Pedido(estado='entregado', fecha_facturacion=datetime(2026, 9, 1, 12, 0))
    assert _pedido_facturado_en_periodo_local(p, date(2026, 9, 1)) is True


def test_un_pendiente_no_cuenta_como_facturado(app):
    from app import _pedido_facturado_en_periodo_local, Pedido
    from datetime import date, datetime
    p = Pedido(estado='pendiente', fecha_facturacion=datetime(2026, 9, 1, 12, 0))
    assert _pedido_facturado_en_periodo_local(p, date(2026, 9, 1)) is False
```

- [ ] **Step 2: Correr y verlo fallar**

Run: `.venv/bin/python -m pytest tests/test_dashboard_entregado.py -q`
Expected: el primero FALLA (`False is not True`), el segundo PASA.

- [ ] **Step 3: Arreglar el helper — que cubre nueve llamadores de una**

`app.py:1086`:

```python
def _pedido_facturado_en_periodo_local(pedido, fecha_inicio, fecha_fin=None):
    """True si el pedido ya se facturó y su fecha_facturacion local cae en el rango.

    `entregado` cuenta: se factura ANTES de entregar, así que un pedido
    entregado se facturó igual — entregarlo no lo desfactura. Sin esto, el
    backfill de 960 pedidos haría caer todas las métricas del dashboard sin
    que nadie hubiera dejado de facturar.
    """
    if pedido.estado not in PEDIDO_INMUTABLE or not pedido.fecha_facturacion:
        return False
```

El resto de la función no se toca. Esto arregla de una a los llamadores de las líneas 2220, 2226, 2232, 2344, 2354, 2447, 2508, 5457 y 6299.

- [ ] **Step 4: Arreglar las consultas SQL, que no pasan por el helper**

En cada una, cambiar `Pedido.estado == 'facturado'` por `Pedido.estado.in_(PEDIDO_INMUTABLE)`:
`2213`, `2337`, `2441`, `2501`, `5451`, `5860`.

Los dos contadores de `2244` y `2424`:

```python
            pedidos_facturados = Pedido.query.filter(
                Pedido.estado.in_(PEDIDO_INMUTABLE)).count()
```

```python
            'pedidos_facturados': Pedido.query.filter(
                Pedido.estado.in_(PEDIDO_INMUTABLE)).count(),
```

`5147`, el `case` del ranking por vendedor:

```python
                db.case([(Pedido.estado.in_(PEDIDO_INMUTABLE), 1)], else_=0)
```

`5890` y `5926`, que comparan strings normalizados en Python:

```python
                and (p.estado or '').strip().lower() in PEDIDO_INMUTABLE
```

```python
            es_facturado = estado_normalizado in PEDIDO_INMUTABLE and bool(fecha_fact_local)
```

- [ ] **Step 5: Correr y verlos pasar**

Run: `.venv/bin/python -m pytest tests/test_dashboard_entregado.py tests/test_dashboard_kpis.py -q`
Expected: PASAN.

Después la suite entera. **Rotura esperada:** `tests/test_dashboard_kpis.py` y `tests/test_dashboard_verdad_y_enlaces.py` leen markup exacto (`<div class="kpi-value">N<small>XCG</small>`). Si alguno falla por un número, verificar a mano si el número nuevo es el correcto antes de tocarlo.

- [ ] **Step 6: Commit**

```bash
git add app.py tests/test_dashboard_entregado.py
git commit -m "fix(dashboard): un pedido entregado se facturó igual

Tras el backfill, 960 pedidos pasan a \`entregado\`. Todas las métricas que
filtran \`estado == 'facturado'\` habrían caído de 964 a 4 sin que nadie dejara
de facturar — una regresión silenciosa en números que se miran todos los días.

Acá se factura ANTES de entregar, así que \`PEDIDO_INMUTABLE\` (facturado +
entregado) es exactamente «ya se facturó». El helper
\`_pedido_facturado_en_periodo_local\` cubre nueve llamadores de una; las seis
consultas SQL y los dos contadores van uno por uno.

Decidido con JM el 2026-09-09."
```

---

### Task 7: Deploy y backfill

**No es una tarea de código.** Es el runbook, y el orden importa.

**Files:** ninguno. Se opera sobre producción.

**Interfaces:**
- Consumes: las tareas 1 a 6, todas mergeadas y con la suite en verde.

- [ ] **Step 1: Confirmar que la suite está entera**

Run: `.venv/bin/python -m pytest tests/ -q`
Expected: cero fallos. **Si hay uno solo, no se sigue.**

- [ ] **Step 2: Contar ANTES de escribir**

```bash
heroku pg:psql --app pesosapp -c "
WITH hoy AS (SELECT (now() AT TIME ZONE 'America/Curacao')::date AS d)
SELECT
  count(*) FILTER (WHERE fecha_entrega IS NULL)                AS sin_fecha,
  count(*) FILTER (WHERE fecha_entrega < (SELECT d FROM hoy))  AS entrega_pasada,
  count(*) FILTER (WHERE fecha_entrega >= (SELECT d FROM hoy)) AS se_quedan,
  count(*)                                                     AS total
FROM pedido WHERE estado = 'facturado';"
```

Expected (medido el 2026-09-09): `sin_fecha=910`, `entrega_pasada=50`, `se_quedan=4`, `total=964`. Los números van a haber cambiado con los días; lo que **tiene** que cumplirse es que `se_quedan` sea un puñado (los facturados sin entregar del día) y no cientos. Si `se_quedan` da un número grande, **parar y mirar**: significa que hay facturados con fecha futura que no se entendieron.

- [ ] **Step 3: Deploy**

```bash
git push origin HEAD:main
```

El push a main dispara el auto-deploy a Heroku. Esperar a que `heroku releases --app pesosapp -n 1` muestre el commit nuevo.

**El deploy va ANTES del UPDATE.** Al revés, entre el UPDATE y el deploy el código viejo todavía tiene el filtro de `app.py:6609` y los 960 desaparecerían del archivo: se leería como pérdida de datos. En este orden la ventana muestra unos 50 falsos atrasados durante un par de minutos, que es molesto pero no asusta.

- [ ] **Step 4: El backfill**

**Primero la tabla de respaldo, después el `UPDATE`.** Sin ella el backfill no deja rastro de qué filas tocó, y entonces no hay vuelta atrás: para deshacerlo habría que correr `UPDATE ... WHERE estado='entregado'`, que también des-entregaría los pedidos que el chofer marcó legítimamente desde el teléfono después del deploy. Con la lista de ids guardada, el rollback se acota a esas filas y a ninguna más.

```bash
heroku pg:psql --app pesosapp -c "
CREATE TABLE backfill_entregado_20260910 AS
SELECT id FROM pedido WHERE estado='facturado'
  AND (fecha_entrega IS NULL OR fecha_entrega < (now() AT TIME ZONE 'America/Curacao')::date - 1);"
```

```bash
heroku pg:psql --app pesosapp -c "
UPDATE pedido SET estado = 'entregado'
WHERE estado = 'facturado'
  AND (fecha_entrega IS NULL
       OR fecha_entrega < (now() AT TIME ZONE 'America/Curacao')::date - 1);"
```

**`CURRENT_DATE` NO sirve.** La base corre en UTC, así que pasadas las 20:00 de Curaçao ya es el día siguiente y el `UPDATE` se llevaría puestos los pedidos que se están entregando hoy, marcándolos entregados sin haber salido. Se comprobó: a las 19:55 locales del 09/09, `CURRENT_DATE` daba 964 afectados en vez de 960.

**El `- 1` es deliberado** (decisión tomada, no un descuido): deja fuera también los pedidos de ayer. Nadie confirmó que hayan salido, y es preferible que el chofer los marque a mano a darlos por entregados desde una consulta.

Expected: el `UPDATE` tiene que afectar exactamente tantas filas como tenga la tabla de respaldo. Verificarlo:

```bash
heroku pg:psql --app pesosapp -c "SELECT count(*) FROM backfill_entregado_20260910;"
```

Si los dos números no coinciden, entre las dos consultas alguien facturó o entregó algo: parar y mirar antes del Step 5.

**El rollback,** si hiciera falta, es solo sobre esas filas:

```sql
UPDATE pedido SET estado='facturado'
WHERE id IN (SELECT id FROM backfill_entregado_20260910);
```

La tabla se borra recién cuando el backfill se dé por bueno (una semana, digamos), y ese `DROP TABLE` merece su propia línea en el spec.

- [ ] **Step 5: Verificar el reparto**

```bash
heroku pg:psql --app pesosapp -c "SELECT estado, count(*) FROM pedido GROUP BY estado ORDER BY 2 DESC;"
```

Expected: `entregado` ≈ 960, `facturado` ≈ 4, `pendiente` ≈ 9.

- [ ] **Step 6: Verificar la app viva**

```bash
curl -s -o /dev/null -w "%{http_code}\n" https://app.jomarfoods.com/login
heroku logs --app pesosapp -n 40 | grep -iE "error|traceback|at=error"
```

Expected: 200 y sin errores. Contra `app.jomarfoods.com` y no contra el origen Heroku: Cloudflare está en el medio.

Y **abrir `/pedidos` con sesión real**: el tablero tiene que mostrar los pedidos del día y no 980 tarjetas. Si aparecen cientos, el backfill no corrió o corrió a medias — revisar el Step 5 antes que el código.

- [ ] **Step 7: Anotar el número final en el spec**

Agregar al spec, en la sección del backfill, cuántas filas se movieron realmente y en qué fecha. Commit:

```bash
git add docs/superpowers/specs/2026-09-09-pedido-entregado-design.md
git commit -m "docs(pedidos): el backfill de \`entregado\`, ejecutado"
```

---

## Notas de ejecución

**Orden.** Las tareas 1 a 6 se pueden hacer en orden y commitear por separado; cada una deja la suite en verde. La Task 1 **tiene** que ir primera: cualquier commit que introduzca `entregado` antes de ella deja pedidos ya facturados en QuickBooks editables otra vez.

**El deploy es todo junto.** No pushear las tareas 1-6 de a una: entre la Task 3 (el tablero deja de dar por cerrado lo facturado) y el backfill de la Task 7, producción mostraría 980 tarjetas en el tablero. Se mergea a main una sola vez, al final, siguiendo la Task 7.

**Tests acoplados a markup.** Varios tests de este repo (`test_dashboard_kpis`, `test_etiquetas`, `test_consolidar_flujo`, `test_pedidos_lista_entrega`) leen HTML exacto con regex y se rompen al refactorizar plantillas aunque la app ande. Si uno falla, verificar primero si es eso antes de tocar el código.

**La comprobación barata que este repo aprendió a los golpes:** ante un test verde que debería proteger algo, revertir el arreglo y mirar si falla. Está como Step explícito en las tareas 1 y 2 porque son las que protegen la factura.
