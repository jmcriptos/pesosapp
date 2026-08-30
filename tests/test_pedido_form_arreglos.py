# tests/test_pedido_form_arreglos.py
"""Task 2 (lote mecánico) del form de alta de pedidos: los ocho arreglos
eran "sin decisión, se miden antes y después" pero se despacharon sin un
solo test — la suite verde solo probaba que nada MÁS se había roto, no que
estos ocho siguieran arreglados. Este archivo cierra eso para lo que se
puede afirmar sin navegador (la mayoría).

Lo que genuinamente necesita un navegador real —el anillo `:focus-visible`
pintado de verdad, y que el desplegable de Tom Select oculte «Añadir»/
Entrega/Notas mientras está abierto sin reabrirse solo por el reenfoque
interno de la librería— se verificó a mano con Playwright (ver
`task-2-report.md`, rondas 1 y 2) y queda sin cobertura de pytest: es
trabajo para la Task 6, que sí tiene navegador en su alcance.

No hay harness de JS en este repo (Jest, Playwright-en-tests): los tests que
tocan `construirChipsEntrega` y la unidad de cajas no EJECUTAN ese código,
leen el archivo real y afirman la FORMA que sostiene el arreglo — mismo
patrón que ya usa `test_pedido_impuesto.py` para lo que vive en JS puro.
"""
import pathlib
import re

import pytest

_ROOT = pathlib.Path(__file__).resolve().parent.parent
_PEDIDO_FORM_HTML = _ROOT / 'templates' / 'pedido_form.html'
_PEDIDO_NUEVO_CSS = _ROOT / 'static' / 'css' / 'pedido_nuevo.css'


def _js_pedido_form():
    return _PEDIDO_FORM_HTML.read_text(encoding='utf-8')


def _css_pedido_nuevo():
    return _PEDIDO_NUEVO_CSS.read_text(encoding='utf-8')


# ── 1. La entrega por defecto no cae en fin de semana ───────────────────────

def test_manana_pasa_por_el_mismo_filtro_de_fin_de_semana_que_el_tercer_chip():
    """`construirChipsEntrega` fabricaba `manana` (hoy+1) y la usaba tal
    cual como default del pedido nuevo, sin el `while (getDay()===0||===6)`
    que sí protegía al tercer chip: un vendedor que abría el form un sábado
    se encontraba con el domingo preseleccionado — un día sin reparto.

    Verificado a mano en el preview (hoy sábado 29/08/2026): antes del
    arreglo el default hubiera sido `2026-08-30` (domingo); después,
    `2026-08-31` (lunes), rotulado «Lun 31». Este test no reproduce esa
    ejecución (no hay harness de JS) — lee `construirChipsEntrega` del
    archivo real y afirma la forma que sostiene el arreglo, para que un
    refactor futuro no la reintroduzca en silencio.
    """
    texto = _js_pedido_form()
    m = re.search(r'function construirChipsEntrega\(\) \{\n(.*?)\n\}\n', texto, re.S)
    assert m, 'no se encontró construirChipsEntrega en pedido_form.html'
    cuerpo = m.group(1)

    # Dos filtros de fin de semana: el del default (nuevo en esta tarea) y
    # el del tercer chip (ya existía). Si vuelve a haber uno solo, el bug
    # volvió.
    filtros = re.findall(
        r'while\s*\([^)]*getDay\(\)\s*===\s*0[^)]*getDay\(\)\s*===\s*6[^)]*\)',
        cuerpo,
    )
    assert len(filtros) >= 2, (
        f'se esperaban al menos dos filtros de fin de semana (default + '
        f'tercer chip); se encontraron {len(filtros)}'
    )

    # El filtro del default tiene que correr ANTES de armar el array
    # `opciones` (donde se decide qué texto e ISO lleva cada chip) — si
    # corriera después, no alcanzaría a proteger al default.
    pos_while = cuerpo.index('while')
    pos_opciones = cuerpo.index('const opciones')
    assert pos_while < pos_opciones, (
        'el filtro de fin de semana corre después de armar los chips: no '
        'protege al default'
    )

    # El patrón que causaba el bug —"mañana" cruda, sin pasar por el
    # filtro— no puede reaparecer.
    assert 'isoDe(manana)' not in cuerpo, (
        'el default volvió a usar isoDe(manana) sin filtrar fin de semana'
    )

    # Y el chip tiene que rotular con el día cuando el resultado no es
    # literalmente mañana (decir "Mañana" en domingo sería mentira).
    assert re.search(r"esManana\s*\?\s*'Mañana'", cuerpo), (
        'el segundo chip ya no distingue si el default es literalmente '
        'mañana o el próximo día hábil'
    )


# ── 5. Plurales de `_texto_hero_habitual` ───────────────────────────────────

def test_texto_hero_habitual_pluraliza_dias():
    # Función de texto puro (sin DB): no necesita app context. `app` (el
    # fixture de conftest.py) no se usa a propósito — ese fixture llama a
    # `_db.engine.table_names()`, quitado en SQLAlchemy 2.0, y rompe en
    # cualquier test que lo pida; es un bug preexistente y ajeno a esta
    # tarea (no está entre los ocho arreglos ni en los archivos de su
    # alcance), así que no se toca acá.
    from app import _texto_hero_habitual
    assert _texto_hero_habitual({'cadencia_dias': 1}) == 'Compra cada 1 día'
    assert _texto_hero_habitual({'cadencia_dias': 7}) == 'Compra cada 7 días'


def test_texto_hero_habitual_pluraliza_pedidos_y_grupos():
    from app import _texto_hero_habitual
    assert _texto_hero_habitual({'grupos': [{'pedidos': 1}]}) == '1 pedido en 1 grupo'
    assert _texto_hero_habitual(
        {'grupos': [{'pedidos': 1}, {'pedidos': 2}]}
    ) == '3 pedidos en 2 grupos'


# ── 3. `--pn-apagado` contra su fondo REAL ──────────────────────────────────

def _reglas_planas(css):
    """(selector, cuerpo) de cada bloque `selector { cuerpo }` del CSS, A
    CUALQUIER PROFUNDIDAD — rastreando una pila de llaves en vez de un
    regex plano tipo `[^{}]+\\{([^}]*)\\}`. Ese regex plano se desincroniza
    apenas aparece un bloque anidado (el `@media (min-width: 640px) {
    .pn-shell { ... } }` del arreglo de max-width, punto 7): confunde el
    `}` de cierre del `.pn-shell` interno con el del `@media`, y arrastra
    ese desfase a TODAS las reglas que vienen después en el archivo — se
    comprobó a mano que así fallaba en encontrar `.pn-step-unidad` y
    `.pn-linea`, mucho más abajo. Esta versión sí desciende a los bloques
    anidados, así que también sirve para leer selectores DENTRO de un
    `@media`."""
    css = re.sub(r'/\*.*?\*/', '', css, flags=re.S)  # comentarios fuera primero
    reglas = []
    pila = []  # (selector, posición de apertura)
    inicio_selector = 0
    for i, c in enumerate(css):
        if c == '{':
            pila.append((css[inicio_selector:i].strip(), i))
            inicio_selector = i + 1
        elif c == '}':
            if pila:
                selector, pos_apertura = pila.pop()
                reglas.append((selector, css[pos_apertura + 1:i]))
            inicio_selector = i + 1
    return reglas


def _encontrar_regla(css, selector):
    """Devuelve el cuerpo `{...}` de la primera regla cuyo selector —
    posiblemente parte de un grupo separado por comas, en varias líneas, o
    anidado dentro de un `@media`— incluya `selector` EXACTO (no como
    substring de otro selector más largo, p. ej. `.pn-linea` vs
    `.pn-linea.es-cambiada`)."""
    for sel_texto, cuerpo in _reglas_planas(css):
        selectores = [s.strip() for s in sel_texto.split(',')]
        if selector in selectores:
            return cuerpo
    raise AssertionError(f'no se encontró la regla {selector!r} en el CSS')


def _valor_de_propiedad(cuerpo_regla, propiedad):
    m = re.search(re.escape(propiedad) + r'\s*:\s*([^;]+);', cuerpo_regla)
    assert m, f'la regla no define {propiedad!r}'
    return m.group(1).strip()


def _resolver_color(css, valor):
    """`valor` puede ser un hex literal o `var(--token)` (con o sin
    `!important`/fallback): lo resuelve al hex real definido en `.pn-shell`,
    en vez de quedarse con el nombre del token."""
    valor = valor.replace('!important', '').strip()
    m = re.match(r'#[0-9a-fA-F]{6}$', valor)
    if m:
        return valor
    m = re.match(r'var\((--[\w-]+)', valor)
    assert m, f'valor de color no resoluble: {valor!r}'
    token = m.group(1)
    tm = re.search(re.escape(token) + r'\s*:\s*(#[0-9a-fA-F]{6})', css)
    assert tm, f'no se encontró la definición de {token!r}'
    return tm.group(1)


def test_pn_apagado_llega_al_minimo_de_contraste_contra_su_fondo_real():
    """`--pn-apagado` (el nombre del producto recién quitado del pedido,
    `.es-quitada .pn-linea-nombre`) daba 2.3:1 sobre el papel — reprobado
    para AA (mínimo 4.5:1 en 17px normal). El fondo real no es un literal
    en la propia regla: se compone subiendo por los ancestros
    (`.pn-linea-nombre` → `.pn-linea-info` → `.pn-linea`, los tres
    transparentes) hasta `.pn-cuerpo`, que sí pinta —`--pn-papel`, fijado
    por el blindaje `!important` contra el tema global, no por la regla
    base de `.pn-cuerpo`—.

    Este test recorre esa misma cadena en vez de asumir el fondo: confirma
    que los tres ancestros siguen transparentes (si alguno empezara a
    pintar fondo propio, el cálculo de abajo dejaría de ser el contraste
    que el vendedor realmente ve) y calcula la razón WCAG contra el fondo
    que de verdad se compone, leyendo los colores DEL ARCHIVO — no un hex
    copiado a mano que podría desviarse en silencio del CSS real.
    """
    css = _css_pedido_nuevo()

    for selector in ('.pn-linea-nombre', '.pn-linea-info', '.pn-linea'):
        cuerpo = _encontrar_regla(css, selector)
        assert 'background' not in cuerpo, (
            f'{selector} ahora pinta fondo propio: la cadena de ancestros '
            f'que este test asume para el fondo real ya no vale'
        )

    color = _resolver_color(css, 'var(--pn-apagado)')
    fondo_raw = _valor_de_propiedad(
        _encontrar_regla(css, '.pn-shell .pn-cuerpo'), 'background')
    fondo = _resolver_color(css, fondo_raw)

    def luminancia(hex_color):
        h = hex_color.lstrip('#')
        canales = [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)]

        def lineal(v):
            return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4

        r, g, b = (lineal(c) for c in canales)
        return 0.2126 * r + 0.7152 * g + 0.0722 * b

    def razon(fg, bg):
        l1, l2 = luminancia(fg), luminancia(bg)
        alto, bajo = max(l1, l2), min(l1, l2)
        return (alto + 0.05) / (bajo + 0.05)

    r = razon(color, fondo)
    assert r >= 4.5, (
        f'--pn-apagado ({color}) sobre el fondo real de .pn-cuerpo '
        f'({fondo}) da {r:.2f}:1, por debajo de 4.5:1'
    )


# ── 4. Unidad de cajas visible (no solo en un aria-label) ──────────────────

def test_unidad_de_cajas_visible_en_stepper_y_en_revision():
    """«· 4» no decía cajas en ningún lado salvo un `aria-label`. Se
    comprueba el markup exacto que arma cada línea, en vez de solo buscar
    la palabra "cajas" suelta en el archivo (que ya aparecía, por ejemplo,
    en el placeholder del input — eso no habría cazado el bug)."""
    texto = _js_pedido_form()

    # Stepper de la línea (paso 2): el número va con una unidad visible al
    # lado, dentro del mismo control — no solo en el aria-label de los
    # botones +/-.
    assert (
        '<span class="pn-step-valor" aria-live="polite">${fmtCajas(p.cajas)}'
        '<small class="pn-step-unidad">cj</small></span>'
    ) in texto

    # Revisión (paso 3): "Producto · N cajas", pluralizado.
    assert (
        "${escapeHtml(p.nombre)} · ${fmtCajas(p.cajas)} "
        "${p.cajas === 1 ? 'caja' : 'cajas'}"
    ) in texto

    # La unidad no puede quedar escondida por CSS: sin `display:none` ni
    # `visibility:hidden` en su propia regla.
    css = _css_pedido_nuevo()
    cuerpo = _encontrar_regla(css, '.pn-step-unidad')
    assert 'display: none' not in cuerpo and 'display:none' not in cuerpo
    assert 'visibility: hidden' not in cuerpo and 'visibility:hidden' not in cuerpo


# ── 7. `.pn-shell` con `max-width` en escritorio ────────────────────────────

def test_pn_shell_tiene_max_width_en_escritorio():
    """Sin tope, a 1280px el flujo se estiraba edge-to-edge (863.5px de
    hueco medidos en el preview entre el producto y su precio en la
    revisión). Confirma que hay un media query de escritorio que acota
    `.pn-shell` a un ancho razonable de columna, no a todo el viewport."""
    css = _css_pedido_nuevo()
    m = re.search(
        r'@media \(min-width:\s*(\d+)px\)\s*\{\s*\.pn-shell\s*\{([^}]*)\}',
        css, re.S,
    )
    assert m, 'no se encontró el media query de escritorio para .pn-shell'
    breakpoint_px = int(m.group(1))
    cuerpo = m.group(2)

    max_width_m = re.search(r'max-width\s*:\s*(\d+)px', cuerpo)
    assert max_width_m, '.pn-shell no fija max-width dentro del media query'
    max_width_px = int(max_width_m.group(1))

    # Rango generoso a propósito: este test protege que exista un tope
    # razonable de columna, no un número de diseño exacto que se pueda
    # ajustar sin que cuente como regresión.
    assert 0 < max_width_px <= 900, f'max-width demasiado ancho: {max_width_px}px'
    assert 0 < breakpoint_px <= 900
