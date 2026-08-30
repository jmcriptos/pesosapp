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


def _cuerpo_bloque(texto, patron_apertura):
    r"""Como `_cuerpo_funcion`, pero para cualquier bloque `{...}` que no es
    una función con nombre (un `try`, un `catch`, un `if`): `patron_apertura`
    es una regex que tiene que terminar justo en la `{` de apertura. Mismo
    rastreo de llaves — nunca acoplado a cuántos espacios de indentación
    tiene el bloque, a diferencia de un regex `\n\s{N}\}` que se rompe si
    alguien reordena o reindenta el código sin cambiar su estructura."""
    m = re.search(patron_apertura, texto)
    assert m, f'no se encontró el patrón {patron_apertura!r}'
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

    # Rastreo de llaves, no `\n\s{8}\}`: acoplarse a la indentación exacta
    # rompería este test por el motivo equivocado si alguien reordena las
    # funciones del bloque (cambia la profundidad de anidamiento) sin tocar
    # la estructura que el test dice proteger.
    cuerpo_catch = _cuerpo_bloque(cuerpo_enviar, r'catch\s*\([^)]*\)\s*\{')
    assert 'mostrarErrorEnvio(' in cuerpo_catch, (
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


# ── Ronda de corrección 1 (revisión externa, sobre este mismo lote) ────────

def _llamadas_seguidas_de_return(texto, nombre_funcion):
    """Para cada llamada `nombre_funcion(...)` en `texto`, dice si el `;`
    que la cierra está seguido (ignorando espacios) de `return;` — con
    rastreo de paréntesis, no un `[^)]*` que se corta en el primer `)`
    interno de un argumento (ej.
    `mostrarErrorEnvio((datos && datos.error) || '...')`)."""
    resultados = []
    for m in re.finditer(re.escape(nombre_funcion) + r'\(', texto):
        i = m.end()
        profundidad = 1
        while profundidad > 0:
            if texto[i] == '(':
                profundidad += 1
            elif texto[i] == ')':
                profundidad -= 1
            i += 1
        resto = texto[i:]
        resultados.append(bool(re.match(r'\s*;\s*return\s*;', resto)))
    return resultados


def test_cada_mostrarerrorenvio_va_seguido_de_return():
    """Si a algún `mostrarErrorEnvio(...)` de `enviarPedido` se le cae el
    `return;` de después, un pedido RECHAZADO sigue de largo a
    `confirmarEnvio`: borra el borrador y pinta "Pedido PED-undefined
    enviado" sobre un pedido que el servidor nunca guardó. Es la propiedad
    central de la Task 4 y no tenía ni un test que la protegiera."""
    texto = _js()
    cuerpo_enviar = _cuerpo_funcion(texto, 'enviarPedido')
    resultados = _llamadas_seguidas_de_return(cuerpo_enviar, 'mostrarErrorEnvio')
    assert len(resultados) >= 3, (
        f'se esperaban al menos 3 llamadas a mostrarErrorEnvio en '
        f'enviarPedido (red cortada, sesión expirada, rechazo del '
        f'servidor), se encontraron {len(resultados)}'
    )
    assert all(resultados), (
        'alguna llamada a mostrarErrorEnvio() en enviarPedido no está '
        'seguida de return; — el flujo seguiría de largo hacia '
        'confirmarEnvio() con un pedido que el servidor rechazó o que '
        'nunca llegó a guardarse'
    )


def test_guard_anti_doble_submit_corta_antes_de_marcar_enviando():
    """El guard cambió de forma en este mismo lote (pasó a estar DESPUÉS
    de un `e.preventDefault()` incondicional) sin que ni una línea lo
    protegiera. Tiene que cortar (`if (enviando) return;`) ANTES de
    `enviando = true` y de deshabilitar el botón — si no, dos toques casi
    simultáneos podrían colarse los dos antes de que la bandera se
    levante."""
    texto = _js()
    m_submit = re.search(
        r"formPedido\.addEventListener\('submit', function \(e\) \{(.*?)\n    \}\);",
        texto, re.S,
    )
    assert m_submit, 'no se encontró el listener de submit'
    cuerpo_submit = m_submit.group(1)

    m_guard = re.search(r'if\s*\(\s*enviando\s*\)\s*return;', cuerpo_submit)
    assert m_guard, 'no se encontró el guard if (enviando) return; en el submit'

    idx_guard = m_guard.start()
    idx_enviando_true = cuerpo_submit.index('enviando = true;')
    idx_disabled = cuerpo_submit.index('btn.disabled = true;')
    assert idx_guard < idx_enviando_true < idx_disabled, (
        'el guard anti-doble-submit no corre ANTES de enviando = true y de '
        'deshabilitar el botón — un doble toque casi simultáneo podría '
        'colarse'
    )


def test_mostrarpaso_conoce_los_ids_de_confirmacion():
    """`mostrarPaso` es la única función que decide qué se ve. Si no
    conociera `pn-head-confirmacion`/`pn-footer-confirmacion`, nada los
    volvería a ocultar y un swipe de atrás después de enviar apilaría la
    cabecera de "revisar y enviar" sobre la de la confirmación — el bug
    que describió el revisor."""
    texto = _js()
    cuerpo = _cuerpo_funcion(texto, 'mostrarPaso')
    for ident in ('pn-head-confirmacion', 'pn-footer-confirmacion'):
        assert ident in cuerpo, (
            f"mostrarPaso no toca #{ident} — queda sin ocultar/mostrar "
            "según el paso"
        )
    # El cuerpo de la revisión se REUTILIZA en 'confirmado', no es una
    # pantalla nueva (ver el comentario junto al head de confirmación).
    assert re.search(r'esRevision\s*\|\|\s*esConfirmado', cuerpo), (
        "pn-cuerpo-revision no se muestra también en el paso 'confirmado' "
        "— la confirmación dejaría de reutilizar el cuerpo de la revisión"
    )


def test_confirmarenvio_reemplaza_la_entrada_de_revision():
    """`entrarARevision` empujó `{pnPaso:'revision'}`; si `confirmarEnvio`
    no la consume (con `replaceState`, no un `pushState` nuevo), esa
    entrada queda viva en el historial y un swipe de atrás cae ahí, con la
    revisión editable sobre un pedido ya enviado."""
    texto = _js()
    cuerpo = _cuerpo_funcion(texto, 'confirmarEnvio')
    assert ("mostrarPaso('confirmado')" in cuerpo
            or 'mostrarPaso("confirmado")' in cuerpo), (
        "confirmarEnvio no llama a mostrarPaso('confirmado')"
    )
    assert re.search(
        r"history\.replaceState\(\s*\{[^}]*pnPaso[^}]*:\s*['\"]confirmado['\"]",
        cuerpo,
    ), (
        "confirmarEnvio no hace history.replaceState({pnPaso:'confirmado'}) "
        "— la entrada de 'revision' que empujó entrarARevision queda sin "
        "consumir"
    )
    assert 'history.pushState' not in cuerpo, (
        'confirmarEnvio usa pushState en vez de replaceState — eso apila '
        "una entrada nueva en vez de reemplazar la de 'revision'"
    )


def test_popstate_no_reabre_nada_en_estado_confirmado():
    texto = _js()
    m = re.search(
        r"addEventListener\(\s*['\"]popstate['\"]\s*,\s*function[^{]*\{(.*?)\n\}\);",
        texto, re.S,
    )
    assert m, 'no se encontró un listener de popstate a nivel de window'
    cuerpo = m.group(1)
    assert ("mostrarPaso('confirmado')" in cuerpo
            or 'mostrarPaso("confirmado")' in cuerpo), (
        "popstate no tiene una rama para pnPaso:'confirmado' — un swipe de "
        "atrás justo después de enviar caería en la rama de 'revision' o "
        "'pedido', reabriendo el form sobre un pedido ya mandado"
    )


def test_confirmarenvio_no_pinta_sin_precio_si_se_cobro_un_respaldo():
    """`sin_precio` del servidor es "no está en la lista de precios
    ACTUAL", no "se cobró gratis": `editar_pedido` siembra el precio
    HISTÓRICO como último recurso (`_resolver_precio_unitario_pedido`), así
    que puede haber `sin_precio: true` con un `precio` real que SÍ se
    cobró (ej. 25.50, subtotal 102.00). Nulear el precio ahí pintaría "SIN
    PRECIO" y un total que EXCLUYE una línea que la base cobró de verdad —
    la misma mentira que este arreglo cerró en el flash, pero al revés."""
    texto = _js()
    cuerpo = _cuerpo_funcion(texto, 'confirmarEnvio')
    m = re.search(
        r'linea\.precio\s*=\s*\(([^)]*)\)\s*\?\s*null\s*:\s*l\.precio;',
        cuerpo,
    )
    assert m, (
        'no se encontró la asignación condicional de linea.precio en '
        'confirmarEnvio'
    )
    condicion = m.group(1)
    assert 'sin_precio' in condicion, (
        'la condición para nulear el precio ya no mira l.sin_precio'
    )
    assert re.search(r'precio\s*===\s*0', condicion), (
        'confirmarEnvio nulea el precio con solo sin_precio (sin exigir '
        'precio === 0): una línea con sin_precio=true pero un precio real '
        'cobrado (respaldo histórico de editar_pedido) se pintaría "SIN '
        'PRECIO" con un total que la excluye, mintiendo sobre lo que se '
        'cobró de verdad'
    )


def test_sesion_expirada_detecta_el_redirect_a_login_antes_de_parsear_json():
    """Una sesión vencida no devuelve un 401 acá: devuelve un 302 a
    /login que `fetch` sigue solo (`resp.ok` da `true`, con el HTML del
    login adentro). Sin detectar esto ANTES de `resp.json()`, la sesión
    dura 8 h en una PWA que vive abierta todo el día — un vendedor con la
    sesión vencida caía en el genérico "el servidor rechazó el pedido" y
    reintentaba para siempre sin saber que tenía que volver a entrar."""
    texto = _js()
    cuerpo = _cuerpo_funcion(texto, 'enviarPedido')
    assert 'resp.redirected' in cuerpo, (
        'enviarPedido no chequea resp.redirected — no puede distinguir un '
        '302 a /login de una respuesta JSON normal'
    )
    assert '/login' in cuerpo, (
        'enviarPedido no busca /login en la URL de la respuesta'
    )
    # El código en sí (no la línea del `if`, que un comentario que MENCIONE
    # "resp.json()" en prosa podría adelantar en el texto): el chequeo real
    # tiene que preceder a la llamada real `await resp.json()`.
    m_check = re.search(r'if\s*\(\s*resp\.redirected', cuerpo)
    m_call = re.search(r'await\s+resp\.json\(\)', cuerpo)
    assert m_check, 'no se encontró el if (resp.redirected...) real'
    assert m_call, 'no se encontró la llamada real await resp.json()'
    assert m_check.start() < m_call.start(), (
        'el chequeo de sesión expirada corre DESPUÉS de la llamada real a '
        'resp.json() — para entonces ya reventó parseando el HTML del '
        'login como JSON'
    )
    idx_mostrar_sesion = cuerpo.index('mostrarErrorEnvio', m_check.start())
    assert idx_mostrar_sesion < m_call.start(), (
        'el aviso de sesión expirada no corre antes de intentar resp.json()'
    )


def test_intento_id_se_genera_una_sola_vez_no_en_cada_envio():
    """Si `crypto.randomUUID()` se llamara DENTRO de `enviarPedido`, cada
    intento (incluido un reintento) mandaría un id distinto y el servidor
    nunca podría reconocer dos intentos como el mismo pedido — el índice
    único quedaría de adorno."""
    texto = _js()
    assert re.search(r'let\s+intentoId\s*=\s*generarIntentoId\(\)\s*;', texto), (
        'intentoId no se genera con generarIntentoId() en el scope de '
        'módulo, al cargar la pantalla'
    )
    cuerpo_enviar = _cuerpo_funcion(texto, 'enviarPedido')
    assert 'randomUUID' not in cuerpo_enviar and 'generarIntentoId' not in cuerpo_enviar, (
        'enviarPedido genera un intento_id nuevo — se regeneraría en cada '
        'envío/reintento y el servidor nunca vería el mismo id dos veces'
    )


def test_generar_intento_id_no_mata_el_script_fuera_de_https():
    """`crypto.randomUUID()` exige contexto seguro (HTTPS o localhost):
    llamarlo sin guarda en `http://192.168.x.x` (probar la PWA por LAN,
    un caso real de desarrollo) revienta con un TypeError — y como la
    generación corre SUELTA al tope del script, antes de cualquier
    función, ese error mataba TODO el bloque: sin buscador, sin steppers,
    sin poder tomar un pedido. `generarIntentoId` tiene que envolver la
    llamada real en un try/catch con un respaldo que no dependa de
    `crypto`."""
    texto = _js()
    cuerpo = _cuerpo_funcion(texto, 'generarIntentoId')
    m = re.search(r'try\s*\{([^{}]*crypto\.randomUUID\(\)[^{}]*)\}\s*catch', cuerpo, re.S)
    assert m, (
        'generarIntentoId no envuelve crypto.randomUUID() en un try/catch '
        '— un contexto inseguro (HTTP, no localhost) tira TypeError y para '
        'entonces ya mató el resto del script'
    )
    resto = cuerpo[m.end():]
    assert re.search(r'return\s+[\'"]', resto), (
        'el catch de generarIntentoId no devuelve un respaldo — sin él, '
        'intentoId queda undefined en un contexto inseguro'
    )


def test_confirmarenvio_regenera_intento_id():
    """Sin esto, volver con el gesto de atrás (bfcache) — el `pageshow`
    de más abajo reactiva el botón y baja `enviando` — dejaba el form
    listo para reenviar con un intento_id que el servidor YA había
    consumido: un pedido nuevo armado desde ese estado se hubiera
    confundido con un reintento del que ya se mandó."""
    texto = _js()
    cuerpo = _cuerpo_funcion(texto, 'confirmarEnvio')
    assert re.search(r'intentoId\s*=\s*generarIntentoId\(\)\s*;', cuerpo), (
        'confirmarEnvio no regenera intentoId al terminar — un intento_id '
        'ya consumido queda listo para reusarse tras un envío exitoso'
    )


def test_hidden_intento_id_se_sincroniza_antes_de_enviar():
    texto = _js()
    assert 'name="intento_id"' in texto, (
        'no está el <input type="hidden" name="intento_id"> en el form'
    )
    m_submit = re.search(
        r"formPedido\.addEventListener\('submit', function \(e\) \{(.*?)\n    \}\);",
        texto, re.S,
    )
    assert m_submit, 'no se encontró el listener de submit'
    cuerpo_submit = m_submit.group(1)
    assert "$('intento_id').value = intentoId;" in cuerpo_submit, (
        'el submit no sincroniza el hidden intento_id con la variable '
        'intentoId antes de mandar el fetch — FormData(formPedido) '
        'levantaría un valor viejo o vacío'
    )
    idx_sync = cuerpo_submit.index("$('intento_id').value = intentoId;")
    idx_enviar = cuerpo_submit.index('enviarPedido();')
    assert idx_sync < idx_enviar, (
        'el hidden se sincroniza DESPUÉS de llamar a enviarPedido()'
    )


def test_borrador_guarda_y_restaura_el_intento_id():
    """Sin esto, una recarga a mitad de camino (`ofrecerBorrador` restaura
    el borrador) generaría un intentoId NUEVO al cargar la página — un
    reintento después de esa recarga ya no sería reconocible como el mismo
    intento para el servidor, y crearía un segundo pedido."""
    texto = _js()
    cuerpo_guardar = _cuerpo_funcion(texto, 'guardarBorrador')
    assert 'intento_id: intentoId' in cuerpo_guardar, (
        'guardarBorrador no guarda intentoId junto con las líneas/fecha/notas'
    )

    cuerpo_ofrecer = _cuerpo_funcion(texto, 'ofrecerBorrador')
    assert re.search(r'intentoId\s*=\s*datos\.intento_id', cuerpo_ofrecer), (
        'ofrecerBorrador no restaura intentoId desde el borrador'
    )


def test_banner_de_error_tiene_role_alert():
    texto = _js()
    m = re.search(r'<div class="pn-aviso" id="pn-envio-error"[^>]*>', texto)
    assert m, 'no se encontró el div #pn-envio-error'
    assert 'role="alert"' in m.group(0), (
        'el banner de error de envío no tiene role="alert"'
    )


def test_banner_de_error_se_limpia_al_volver_a_entrar_a_revision():
    """Un rechazo o un corte de red deja el banner visible en el footer de
    la revisión; si el vendedor vuelve al paso 02 a corregir algo y entra
    de nuevo, ese banner viejo no puede seguir ahí sobre un intento nuevo
    que todavía no falló."""
    texto = _js()
    m = re.search(
        r"\$\('pn-continuar'\)\.addEventListener\('click', function \(\) \{(.*?)\n    \}\);",
        texto, re.S,
    )
    assert m, 'no se encontró el listener de pn-continuar'
    cuerpo = m.group(1)
    assert 'ocultarErrorEnvio()' in cuerpo, (
        'pn-continuar no limpia el banner de error al volver a entrar a '
        'revisión — un rechazo viejo seguiría visible sobre un intento '
        'nuevo que todavía no falló'
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
