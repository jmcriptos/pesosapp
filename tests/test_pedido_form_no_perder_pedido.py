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


def test_borrar_borrador_solo_cuando_el_servidor_confirma():
    """Task 4 cambió el envío a `fetch`, así que ya no hay que borrar el
    borrador "a ciegas" al dejar pasar la validación del cliente (que es lo
    que exigía esta prueba hasta la Task 3, documentado como límite conocido
    en el informe de esa tarea): ahora se puede saber si el servidor aceptó
    el pedido de verdad, y borrar recién ahí. Si el fetch falla (sin señal)
    o el servidor lo rechaza (precio inválido, etc.), el borrador tiene que
    sobrevivir para que el reintento no parta de cero."""
    texto = _js()

    m_submit = re.search(
        r"formPedido\.addEventListener\('submit', function \(e\) \{(.*?)\n    \}\);",
        texto, re.S,
    )
    assert m_submit, 'no se encontró el listener de submit'
    cuerpo_submit = m_submit.group(1)
    assert 'borrarBorrador' not in cuerpo_submit, (
        'el submit vuelve a borrar el borrador antes de saber si el '
        'servidor aceptó el pedido — el mismo riesgo que la Task 4 tenía '
        'que cerrar'
    )

    cuerpo_confirmar = _cuerpo_funcion(texto, 'confirmarEnvio')
    assert 'borrarBorrador();' in cuerpo_confirmar, (
        'confirmarEnvio (solo se llama tras un fetch exitoso, ok:true del '
        'servidor) ya no borra el borrador'
    )

    # Fallo de red o rechazo del servidor: el borrador tiene que sobrevivir
    # para el reintento.
    cuerpo_error = _cuerpo_funcion(texto, 'mostrarErrorEnvio')
    assert 'borrarBorrador' not in cuerpo_error, (
        'mostrarErrorEnvio (fetch fallido o el servidor rechazó el pedido) '
        'borra el borrador — un reintento partiría de cero'
    )


def test_submit_siempre_usa_fetch_nunca_el_post_clasico():
    """Un corte de señal a mitad de un POST clásico deja la página de error
    del navegador y el pedido se pierde — la pantalla vive en la calle,
    donde la señal falla (comentario de `pedido_cliente.html`). El submit
    tiene que prevenir SIEMPRE la navegación por defecto y pasar por
    `fetch`, nunca dejar que el form navegue solo."""
    texto = _js()
    m_submit = re.search(
        r"formPedido\.addEventListener\('submit', function \(e\) \{(.*?)\n    \}\);",
        texto, re.S,
    )
    assert m_submit, 'no se encontró el listener de submit'
    cuerpo_submit = m_submit.group(1)

    # `e.preventDefault()` tiene que correr ANTES que cualquier `if`
    # (incondicional): así no depende de ninguna validación, se corta la
    # navegación del navegador pase lo que pase — a diferencia del código
    # viejo, donde solo se prevenía dentro de las ramas que cortaban.
    idx_prevent = cuerpo_submit.index('e.preventDefault();')
    idx_if = cuerpo_submit.index('if (')
    assert idx_prevent < idx_if, (
        'e.preventDefault() no corre antes del primer if — la navegación '
        'por defecto queda condicionada a alguna validación, no es '
        'incondicional'
    )
    assert 'enviarPedido()' in cuerpo_submit, (
        'el submit no llama a enviarPedido() — el fetch nunca se dispara'
    )

    cuerpo_enviar = _cuerpo_funcion(texto, 'enviarPedido')
    assert re.search(r'await\s+fetch\(', cuerpo_enviar), (
        'enviarPedido no usa fetch — sigue habiendo un camino sin AJAX'
    )
    assert "'X-Requested-With': 'XMLHttpRequest'" in cuerpo_enviar, (
        'el fetch no manda X-Requested-With: el servidor no puede '
        'distinguirlo de un POST clásico y seguiría redirigiendo en vez de '
        'devolver JSON'
    )


def test_fallo_de_red_o_rechazo_del_servidor_muestran_error_en_el_shell():
    """Ni la excepción del `fetch` (sin señal) ni un `resp.ok` falso o un
    `ok:false` del servidor pueden dejar la pantalla en silencio o navegar
    afuera: los dos tienen que caer en `mostrarErrorEnvio`, que reactiva el
    botón (con la bandera `enviando` en `false` — el cabo suelto de la
    Task 3, botón trabado en "Enviando…" si el envío fallaba sin navegar) y
    muestra el aviso DENTRO del shell."""
    texto = _js()
    cuerpo_enviar = _cuerpo_funcion(texto, 'enviarPedido')

    m_catch = re.search(r'catch\s*\([^)]*\)\s*\{([\s\S]*?)\n\s{8}\}', cuerpo_enviar)
    assert m_catch, 'no se encontró el catch del fetch en enviarPedido'
    assert 'mostrarErrorEnvio(' in m_catch.group(1), (
        'el catch del fetch (fallo de red) no llama a mostrarErrorEnvio'
    )

    assert re.search(r'!resp\.ok\s*\|\|[^)]*datos\.ok\s*!==\s*true', cuerpo_enviar), (
        'enviarPedido no distingue un rechazo del servidor (resp.ok falso u '
        'ok:false en el JSON) — un pedido rechazado se trataría como éxito'
    )

    cuerpo_error = _cuerpo_funcion(texto, 'mostrarErrorEnvio')
    assert re.search(r'enviando\s*=\s*false', cuerpo_error), (
        'mostrarErrorEnvio no baja la bandera enviando — el botón queda '
        'trabado en "Enviando…" (el cabo suelto que dejó la Task 3)'
    )
    assert 'btn.disabled = false' in cuerpo_error
    assert "$('pn-envio-error')" in cuerpo_error or 'pn-envio-error' in cuerpo_error, (
        'mostrarErrorEnvio no toca el banner de error dentro del shell'
    )


def test_confirmacion_apaga_lineas_activas_para_no_avisar_de_mas():
    """Tras `confirmarEnvio` el pedido ya está en el servidor: si
    `productosAgregados` siguiera con líneas activas, `beforeunload`
    seguiría preguntando "¿seguro que quieres salir?" sobre un pedido que
    ya se mandó."""
    texto = _js()
    cuerpo = _cuerpo_funcion(texto, 'confirmarEnvio')
    assert re.search(r'p\.activa\s*=\s*false', cuerpo), (
        'confirmarEnvio no desactiva las líneas — beforeunload seguiría '
        'avisando sobre un pedido ya enviado'
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
