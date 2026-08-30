# tests/test_pedido_form_modo_busqueda.py
"""Mientras se elige un producto, la LISTA es la pantalla.

Medido en el iPhone con el teclado abierto (visor de 508px): la cabecera se
llevaba 318px y el pie 166, así que el cuerpo útil quedaba en 25px —el 5%— y de
41 productos entraban 3 enteros. Con el modo búsqueda: cabecera 98, pie fuera,
y 6 productos enteros (13 sin teclado).

Estos tests son de CONTRATO sobre el fuente: la geometría real solo se puede
medir en un navegador. Afirman las tres cosas que, si se caen, devuelven el
problema — y están escritos para fallar si alguna se cae, no para acompañar.
"""
import os
import re

os.environ.setdefault('SECRET_KEY', 'test-secret')
os.environ.setdefault('FLASK_ENV', 'testing')
os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PLANTILLA = os.path.join(RAIZ, 'templates', 'pedido_form.html')
CSS = os.path.join(RAIZ, 'static', 'css', 'pedido_nuevo.css')


def _texto(ruta):
    with open(ruta, encoding='utf-8') as fh:
        return fh.read()


def _cuerpo_de(fuente, firma):
    """El cuerpo de una función/callback, rastreando llaves."""
    i = fuente.index(firma)
    abre = fuente.index('{', i)
    prof, j = 1, abre + 1
    while j < len(fuente) and prof:
        if fuente[j] == '{':
            prof += 1
        elif fuente[j] == '}':
            prof -= 1
        j += 1
    return fuente[abre:j]


def test_el_modo_se_enciende_al_abrir_el_desplegable_y_se_apaga_al_cerrarlo():
    """Va con el desplegable, no con el panel de alta.

    El panel queda abierto DESPUÉS de añadir: atar el modo ahí escondería el
    total justo cuando el vendedor quiere ver que su línea entró.
    """
    fuente = _texto(PLANTILLA)
    abrir = _cuerpo_de(fuente, 'onDropdownOpen: function')
    cerrar = _cuerpo_de(fuente, 'onDropdownClose: function')

    assert 'modoBusqueda(true)' in abrir, 'el modo no se enciende al abrir la lista'
    assert 'modoBusqueda(false)' in cerrar, (
        'el modo no se apaga al cerrar: la cabecera y el pie no vuelven'
    )
    # Y no debe atarse al panel de alta, que sigue abierto tras añadir.
    toggle = _cuerpo_de(fuente, "addToggle.addEventListener('click'")
    assert 'modoBusqueda' not in toggle, (
        'el modo quedó atado al panel de alta: tras añadir un producto el '
        'vendedor no vería el total de su propio pedido'
    )


def test_el_alto_del_desplegable_se_mide_DESPUES_de_replegar_la_cabecera():
    """El orden es el arreglo, no un detalle.

    Replegar la cabecera y clavar el buscador arriba MUEVE el control. Si el
    espacio disponible se lee antes, se calcula contra la posición vieja: fue
    exactamente el fallo del primer intento —el desplegable quedaba en 138px
    con la pantalla medio vacía—.
    """
    abrir = _cuerpo_de(_texto(PLANTILLA), 'onDropdownOpen: function')
    assert abrir.index('modoBusqueda(true)') < abrir.index('getBoundingClientRect'), (
        'se mide el espacio antes de replegar la cabecera: el desplegable '
        'queda calculado contra la posición vieja del control'
    )


def test_se_levanta_tambien_el_tope_interno_de_tom_select():
    """Tom Select le pone `max-height: 200px` a su propio `.ts-dropdown-content`.

    Sin tocar ese nivel, el desplegable queda clavado en ~202px por más
    pantalla libre que haya: se veían 6 productos de 41 con espacio de sobra.
    """
    abrir = _cuerpo_de(_texto(PLANTILLA), 'onDropdownOpen: function')
    assert 'ts-dropdown-content' in abrir, (
        'no se levanta el max-height interno de Tom Select'
    )
    assert re.search(r"contenido\.style\.maxHeight\s*=", abrir), (
        'el contenido del desplegable no recibe el alto calculado'
    )


def test_el_css_repliega_la_cabecera_y_esconde_el_pie():
    """Los tres bloques que liberan la pantalla, anclados en #pn-shell.

    El ancla importa: el `:root` roto del proyecto le gana a cualquier selector
    de clases suelto (ver la nota de pantalla-pedido-nuevo-ab).
    """
    css = _texto(CSS)
    for regla in ('.pn-sobretitulo', '.pn-head-nota', '.pn-footer', '#ph-add-panel'):
        assert re.search(
            r'#pn-shell\.pn-modo-busqueda[^{]*' + re.escape(regla), css
        ), f'falta la regla de modo búsqueda para {regla}, o no está anclada en #pn-shell'

    # El panel se clava arriba: sin esto la cabecera se repliega pero el
    # buscador se queda donde estaba en el scroll (medido: y=423 de 508).
    panel = css[css.index('#pn-shell.pn-modo-busqueda #ph-add-panel'):]
    panel = panel[:panel.index('}')]
    assert 'position: fixed' in panel, 'el buscador no se clava arriba'
    assert '--pn-head-alto' in panel, (
        'el tope se clava con un número fijo en vez del alto real de la cabecera'
    )


# ── El origen de las líneas, plegado ─────────────────────────────────────────

def test_el_parrafo_del_habitual_va_plegado_con_un_resumen_a_la_vista():
    """Presente pero plegado: el hecho a la vista, la explicación a un toque.

    `<details>`/`<summary>` y no un toggle a mano: trae el plegado, el teclado
    y el anuncio a lectores de pantalla sin una línea de JS.
    """
    fuente = _texto(PLANTILLA)
    assert '<details class="pn-head-detalle">' in fuente
    assert 'pn-head-resumen' in fuente, 'falta el resumen visible del plegado'
    assert 'origen_resumen' in fuente, 'el resumen no viene del servidor'


def test_el_parrafo_plegado_NO_deja_caja_en_pantalla():
    """El bug que este test existe para impedir, cometido al escribir esto.

    Con el `<details>` cerrado, el párrafo conservaba su caja —65px de alto—
    y se derramaba fuera de la cabecera; lo único que lo tapaba era el fondo
    pintándose encima (`elementFromPoint` devolvía `.pn-head` en ese punto).
    O sea: plegado a medias, ocupando el espacio que el plegado venía a
    liberar.

    Es el mismo modo de fallo que ya llegó a producción con `[hidden]`
    perdiendo contra un `display` de autor. Por eso el plegado se escribe
    explícito en vez de confiar en el navegador.
    """
    css = _texto(CSS)
    assert re.search(
        r'\.pn-head-detalle:not\(\[open\]\)\s+\.pn-head-detalle-cuerpo\s*\{[^}]*display:\s*none',
        css,
    ), (
        'falta el `display: none` explícito del cuerpo plegado: sin él el '
        'párrafo sigue ocupando su caja aunque el <details> esté cerrado'
    )


def test_el_resumen_llega_a_44px_de_area_tactil():
    """El objetivo es el renglón entero, no la flechita."""
    css = _texto(CSS)
    bloque = css[css.index('.pn-head-detalle > summary {'):]
    bloque = bloque[:bloque.index('}')]
    assert 'min-height: 44px' in bloque, 'el resumen no llega al mínimo táctil'


# ── La cabecera compacta al scrollear ────────────────────────────────────────

def test_la_cabecera_se_encoge_al_scrollear_y_vuelve_al_subir():
    """Con 293px de cabecera y 166 de pie entraban CUATRO líneas en el iPhone.

    Medido: cabecera 293 → 70 al scrollear, y el espacio para las líneas pasa
    de 385 a 632px. El umbral no es 0 para que un rebote de scroll no la haga
    parpadear.
    """
    fuente = _texto(PLANTILLA)
    cuerpo = _cuerpo_de(fuente, "cuerpoPedido.addEventListener('scroll'")
    assert 'pn-head-compacta' in cuerpo, 'el scroll no encoge la cabecera'
    assert 'scrollTop >' in cuerpo, 'no hay umbral: la cabecera va a parpadear'
    assert 'toggle(' in cuerpo, (
        'la clase se agrega sin quitarse: la cabecera no volvería al subir'
    )


def test_en_compacto_el_cliente_y_el_grupo_SIGUEN_a_la_vista():
    """Lo que no se puede perder al encoger.

    El vendedor tiene que saber siempre de quién es el pedido y de qué grupo:
    el grupo restringe qué productos puede cargar, y equivocarse de cliente es
    un pedido entero mal. Se esconde el contexto que ya cumplió (el
    sobretítulo, la cadencia, el origen de las líneas), nunca la identidad.
    """
    css = _texto(CSS)
    bloque = css[css.index('#pn-shell.pn-head-compacta .pn-sobretitulo'):]
    bloque = bloque[:bloque.index('}')]
    for prohibido in ('.pn-titulo-cliente', '.pn-grupo-chip'):
        assert prohibido not in bloque, (
            f'{prohibido} se esconde al encoger la cabecera: el vendedor '
            'pierde de vista de quién es el pedido o de qué grupo'
        )
    # Y el chip conserva su área táctil, que sigue siendo la salida de grupo.
    compacto_chip = css[css.index('#pn-shell.pn-head-compacta .pn-grupo-chip'):]
    compacto_chip = compacto_chip[:compacto_chip.index('}')]
    assert 'height' not in compacto_chip, (
        'se le tocó el alto al chip en compacto: es el objetivo táctil de la '
        'única salida para cambiar de grupo'
    )
