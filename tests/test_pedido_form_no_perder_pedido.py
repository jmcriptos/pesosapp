# tests/test_pedido_form_no_perder_pedido.py
"""Task 3 del form de alta de pedidos: el paso 04 (revisión) no era una
entrada de historial, así que el swipe de "atrás" de iOS —el gesto que todo
el mundo hace en la PWA instalada— salía del formulario entero y destruía
el pedido, justo en el momento en que más duele (revisando, con el cliente
pidiendo un cambio de última hora). Tres arreglos: el paso 04 entra al
historial (`pushState`/`popstate`), `beforeunload` avisa si hay líneas
activas y no se está enviando, y un borrador en `localStorage` (clave
`borrador:<cliente>:<grupo>`) sobrevive a un cierre accidental.

No hay harness de JS en este repo (mismo aviso que en
`test_pedido_form_arreglos.py`): estos tests leen el archivo real y afirman
la FORMA que sostiene cada arreglo, no lo ejecutan. La verificación con
navegador real (swipe, recarga con borrador, envío que lo borra) es de la
Task 6.
"""
import pathlib
import re

_ROOT = pathlib.Path(__file__).resolve().parent.parent
_PEDIDO_FORM_HTML = _ROOT / 'templates' / 'pedido_form.html'


def _js():
    return _PEDIDO_FORM_HTML.read_text(encoding='utf-8')


def _cuerpo_funcion(texto, nombre):
    """Cuerpo `{...}` de `function nombre(...) { ... }`, rastreando llaves
    (no un regex `[^}]*` que se corta en la primera `}` interna — varias de
    estas funciones tienen sus propios bloques anidados)."""
    m = re.search(r'function\s+' + re.escape(nombre) + r'\s*\([^)]*\)\s*\{', texto)
    assert m, f'no se encontró function {nombre}() en pedido_form.html'
    inicio = m.end()
    profundidad = 1
    i = inicio
    while profundidad > 0:
        if texto[i] == '{':
            profundidad += 1
        elif texto[i] == '}':
            profundidad -= 1
        i += 1
    return texto[inicio:i - 1]


# ── 1. El paso 04 entra al historial ────────────────────────────────────────

def test_entrar_a_revision_empuja_historial():
    texto = _js()
    cuerpo = _cuerpo_funcion(texto, 'entrarARevision')
    assert 'mostrarPaso(\'revision\')' in cuerpo or 'mostrarPaso("revision")' in cuerpo
    assert 'history.pushState' in cuerpo
    # El estado tiene que llevar una marca reconocible: sin ella, popstate no
    # podría distinguir "estoy en revisión" de cualquier otra entrada de
    # historial ajena a este formulario.
    assert re.search(r"pushState\(\s*\{[^}]*pnPaso[^}]*:\s*['\"]revision['\"]", cuerpo)


def test_pushstate_no_revienta_la_pantalla_si_falla():
    """localStorage puede fallar; el historial también (Safari privado,
    algún bloqueo raro). Un pushState que revienta no puede tirar abajo el
    paso 03→04."""
    texto = _js()
    cuerpo = _cuerpo_funcion(texto, 'entrarARevision')
    m = re.search(r'try\s*\{([\s\S]*?history\.pushState[\s\S]*?)\}\s*catch', cuerpo)
    assert m, 'history.pushState no está envuelto en try/catch en entrarARevision'


def test_popstate_vuelve_al_paso_03_no_navega_afuera():
    """El corazón del arreglo: un `popstate` (swipe, o el botón atrás del
    navegador) tiene que aterrizar en `mostrarPaso('pedido')`, no dejar que
    el navegador siga su navegación normal (que sería salir del form)."""
    texto = _js()
    m = re.search(r"addEventListener\(\s*['\"]popstate['\"]\s*,\s*function[^{]*\{(.*?)\n\}\);", texto, re.S)
    assert m, 'no se encontró un listener de popstate a nivel de window'
    cuerpo = m.group(1)
    assert "mostrarPaso('pedido')" in cuerpo or 'mostrarPaso("pedido")' in cuerpo
    assert "mostrarPaso('revision')" in cuerpo or 'mostrarPaso("revision")' in cuerpo


def test_volver_pasa_por_el_mismo_camino_que_el_swipe():
    """El botón «volver» del paso 04 (`pn-volver-pedido`) no puede llamar a
    `mostrarPaso('pedido')` directo: si lo hiciera, dejaría la entrada de
    historial de `entrarARevision` colgada sin consumir, y la PRÓXIMA vez
    que el vendedor tocara atrás (o cerrara con swipe) volvería a saltar a
    la revisión en vez de salir del form — historial roto por ida y vuelta.
    Tiene que ir por `salirDeRevision`, que usa `history.back()` cuando hay
    una entrada empujada."""
    texto = _js()
    assert "$('pn-volver-pedido').addEventListener('click', salirDeRevision)" in texto, (
        'el botón de volver de la revisión ya no delega en salirDeRevision()'
    )
    cuerpo = _cuerpo_funcion(texto, 'salirDeRevision')
    assert 'history.back()' in cuerpo
    # Y tiene que haber un camino directo por si no se pudo empujar nada.
    assert "mostrarPaso('pedido')" in cuerpo or 'mostrarPaso("pedido")' in cuerpo


def test_continuar_delega_en_entrarARevision_no_en_mostrarpaso_directo():
    texto = _js()
    m = re.search(
        r"\$\('pn-continuar'\)\.addEventListener\('click', function \(\) \{(.*?)\n    \}\);",
        texto, re.S,
    )
    assert m, 'no se encontró el listener de pn-continuar'
    cuerpo = m.group(1)
    assert 'entrarARevision()' in cuerpo
    assert 'mostrarPaso(' not in cuerpo, (
        'pn-continuar llama a mostrarPaso directo: se saltea el pushState '
        'de entrarARevision y el paso 04 vuelve a no ser una entrada de '
        'historial'
    )


# ── 2. beforeunload ──────────────────────────────────────────────────────

def test_beforeunload_avisa_con_lineas_activas_y_no_enviando():
    texto = _js()
    m = re.search(
        r"addEventListener\(\s*['\"]beforeunload['\"]\s*,\s*function\s*\(e\)\s*\{(.*?)\n    \}\);",
        texto, re.S,
    )
    assert m, 'no se encontró un listener de beforeunload'
    cuerpo = m.group(1)

    # No debe avisar mientras se está enviando: saltaría justo cuando el
    # propio envío es la causa de la navegación.
    assert re.search(r'if\s*\(\s*enviando\s*\)\s*return', cuerpo), (
        'beforeunload no corta cuando enviando es true — saltaría el aviso '
        'absurdo al enviar'
    )
    # Y no debe avisar sin líneas activas.
    assert 'productosAgregados.some(p => p.activa)' in cuerpo
    assert 'e.preventDefault()' in cuerpo
    assert 'e.returnValue' in cuerpo


def test_beforeunload_registrado_antes_del_submit_en_el_mismo_bloque():
    """No es estrictamente necesario por orden de ejecución (son listeners
    separados), pero confirma que `enviando` ya existe como variable
    compartida entre ambos: si `beforeunload` se declarara en un scope sin
    acceso a `enviando`, referenciarla sería un ReferenceError la primera
    vez que el navegador disparara el evento."""
    texto = _js()
    idx_let = texto.index('let enviando = false;')
    idx_beforeunload = texto.index("addEventListener('beforeunload'")
    idx_submit = texto.index("formPedido.addEventListener('submit'")
    assert idx_let < idx_beforeunload < idx_submit, (
        'enviando/beforeunload/submit no están en el orden esperado dentro '
        'del mismo bloque de arranque'
    )


# ── 3. Borrador en localStorage ─────────────────────────────────────────

def test_clave_de_borrador_junta_cliente_y_grupo():
    texto = _js()
    cuerpo = _cuerpo_funcion(texto, 'claveBorrador')
    assert re.search(r'`borrador:\$\{clienteId\}:\$\{grupoActual\}`', cuerpo), (
        'la clave del borrador ya no es borrador:<cliente>:<grupo>'
    )
    # Sin grupo conocido no hay clave: guardarBorrador/ofrecerBorrador deben
    # poder no-opear en ese momento sin reventar.
    assert re.search(r'if\s*\(\s*!grupoActual\s*\)\s*return\s+null', cuerpo)


def test_sincronizar_candado_provisional_borra_el_borrador_antes_de_soltar_el_grupo():
    """Ronda de corrección 1: cliente sin habitual → una línea del grupo A
    fija `grupoActual = A` y guarda `borrador:<cliente>:A` → se quita esa
    línea → `sincronizarCandadoProvisional` soltaba `grupoActual = null` SIN
    borrar antes ese borrador — `claveBorrador()` ya no podía encontrarlo
    (devuelve null sin grupo), así que quedaba huérfano en localStorage para
    siempre y podía reaparecer en una sesión futura sin relación, ofreciendo
    «¿seguir donde lo dejaste?» con un pedido abandonado hace semanas.

    El orden importa: `borrarBorrador()` tiene que llamarse ANTES de
    `grupoActual = null`, mientras la clave todavía apunta al grupo que se
    suelta."""
    texto = _js()
    cuerpo = _cuerpo_funcion(texto, 'sincronizarCandadoProvisional')

    assert 'borrarBorrador();' in cuerpo, (
        'sincronizarCandadoProvisional ya no limpia el borrador del grupo '
        'que suelta — vuelve a quedar huérfano en localStorage'
    )
    idx_borrar = cuerpo.index('borrarBorrador();')
    idx_suelta = cuerpo.index('grupoActual = null;')
    assert idx_borrar < idx_suelta, (
        'borrarBorrador() se llama DESPUÉS de grupoActual = null: para '
        'entonces claveBorrador() ya devuelve null y no encuentra nada que '
        'borrar — el borrador del grupo que se suelta queda huérfano igual'
    )


def test_guardar_borrador_incluye_lineas_fecha_y_notas():
    texto = _js()
    cuerpo = _cuerpo_funcion(texto, 'guardarBorrador')
    assert 'lineas: productosAgregados' in cuerpo
    assert 'fecha_entrega: inputFechaEntrega.value' in cuerpo
    assert 'notas:' in cuerpo


def test_guardar_borrador_localstorage_en_try_catch():
    """localStorage puede fallar (modo privado de Safari, cuota llena): que
    la pantalla siga andando sin borrador es el requisito explícito de la
    tarea, no un detalle de implementación."""
    texto = _js()
    cuerpo = _cuerpo_funcion(texto, 'guardarBorrador')
    m = re.search(r'try\s*\{([^{}]*localStorage\.setItem[^{}]*)\}\s*catch', cuerpo, re.S)
    assert m, 'localStorage.setItem no está envuelto en try/catch en guardarBorrador'


def test_ofrecer_borrador_lee_con_try_catch_y_pregunta_antes_de_aplicar():
    texto = _js()
    cuerpo = _cuerpo_funcion(texto, 'ofrecerBorrador')

    m_get = re.search(r'try\s*\{([^{}]*localStorage\.getItem[^{}]*)\}\s*catch', cuerpo, re.S)
    assert m_get, 'localStorage.getItem no está envuelto en try/catch en ofrecerBorrador'

    m_parse = re.search(r'try\s*\{([^{}]*JSON\.parse[^{}]*)\}\s*catch', cuerpo, re.S)
    assert m_parse, 'JSON.parse no está envuelto en try/catch en ofrecerBorrador'

    # No alcanza con que `confirm(` aparezca ANTES que la asignación en el
    # texto: eso lo cumpliría igual `confirm('¿seguir?'); productosAgregados
    # = datos.lineas;` — llamar a confirm() e IGNORAR el resultado, aplicando
    # el borrador siempre. Hay que exigir la ESTRUCTURA: un guard
    # `if (!confirm(...)) return;` cuyo `return` corte la función ANTES de
    # que la asignación pueda correr — no solo que las dos líneas aparezcan
    # en cierto orden.
    m_guard = re.search(
        r'if\s*\(\s*!\s*confirm\([^)]*\)\s*\)\s*\{?\s*return;\s*\}?',
        cuerpo,
    )
    assert m_guard, (
        'no se encontró el guard `if (!confirm(...)) return;` en '
        'ofrecerBorrador — sin él, el resultado de confirm() se puede '
        'ignorar y el borrador se aplicaría siempre, sin preguntar'
    )

    resto = cuerpo[m_guard.end():]
    assert 'productosAgregados = datos.lineas' in resto, (
        'la asignación de productosAgregados no está DESPUÉS del guard de '
        'confirm(): puede estar corriendo sin depender de la respuesta del '
        'vendedor'
    )


def test_ofrecer_borrador_se_llama_antes_de_pintar_el_arranque():
    """Si `ofrecerBorrador()` corriera DESPUÉS del primer render (o después
    de `construirChipsEntrega`), el primer `actualizarTablaProductos()` de
    un pedido nuevo (cero líneas) llamaría a `guardarBorrador()` → 0 líneas
    activas → `borrarBorrador()` — borrando el borrador ANTES de que se
    llegara a ofrecer. El orden es lo que evita esa carrera."""
    texto = _js()
    idx_dom = texto.index("document.addEventListener('DOMContentLoaded'")
    idx_ofrecer = texto.index('ofrecerBorrador();', idx_dom)
    idx_chips = texto.index('construirChipsEntrega();', idx_dom)
    idx_tabla = texto.index('actualizarTablaProductos();', idx_dom)
    assert idx_dom < idx_ofrecer < idx_chips < idx_tabla


def test_borrar_borrador_al_enviar_con_exito():
    """El envío real (el que pasa la validación de líneas y deja avanzar el
    submit) tiene que limpiar el borrador — ANTES de deshabilitar el botón,
    da igual el orden exacto, pero tiene que estar en la rama que de verdad
    deja pasar el POST, no en la que lo corta."""
    texto = _js()
    m = re.search(
        r"formPedido\.addEventListener\('submit', function \(e\) \{(.*?)\n    \}\);",
        texto, re.S,
    )
    assert m, 'no se encontró el listener de submit'
    cuerpo = m.group(1)

    idx_enviando = cuerpo.index('enviando = true;')
    idx_borrar = cuerpo.index('borrarBorrador();')
    assert idx_borrar > idx_enviando, (
        'borrarBorrador() se llama antes de confirmar que el envío pasa '
        'las validaciones (enviando = true)'
    )

    # Las dos ramas que CORTAN el envío (doble toque, sin líneas) no pueden
    # borrar el borrador: ahí el pedido no se mandó.
    ramas_de_corte = re.findall(r'if \([^)]*\) \{\s*e\.preventDefault\(\);.*?\n        \}', cuerpo, re.S)
    for rama in ramas_de_corte:
        assert 'borrarBorrador' not in rama, (
            f'una rama que corta el envío llama a borrarBorrador(): {rama!r}'
        )


def test_notas_dispara_guardado_de_borrador():
    texto = _js()
    assert "$('notas').addEventListener('input', guardarBorrador)" in texto, (
        'las notas ya no disparan guardarBorrador en cada cambio'
    )


def test_lineas_y_entrega_disparan_guardado_de_borrador():
    """Líneas (altas, steppers, restaurar) pasan TODAS por
    `actualizarTablaProductos`; la entrega por `seleccionarEntrega`. Que el
    guardado viva ahí (y no repetido en cada call-site) es lo que garantiza
    "en cada cambio" sin tener que acordarse de llamar a mano en cada lugar
    nuevo que toque una línea."""
    texto = _js()
    cuerpo_tabla = _cuerpo_funcion(texto, 'actualizarTablaProductos')
    assert cuerpo_tabla.count('guardarBorrador();') >= 2, (
        'actualizarTablaProductos no guarda el borrador en sus dos salidas '
        '(lista vacía y lista con líneas)'
    )
    cuerpo_entrega = _cuerpo_funcion(texto, 'seleccionarEntrega')
    assert 'guardarBorrador();' in cuerpo_entrega
