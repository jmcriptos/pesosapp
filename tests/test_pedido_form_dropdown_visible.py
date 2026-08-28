"""El buscador de productos del pedido nuevo tiene que verse.

`.pn-shell` es la pantalla entera: `position: fixed; inset: 0; z-index: 1200`,
opaca. El dropdown de Tom Select se monta en `<body>` a propósito
(`dropdownParent: 'body'`), para escapar del `overflow: hidden` de las
tarjetas — pero eso lo deja FUERA de `.pn-shell`, en el contexto de apilado
raíz, con el `z-index: 1000` que trae Tom Select por defecto.

1000 < 1200, así que la pantalla se pintaba encima: las opciones se
renderizaban, bien posicionadas y opacas, y quedaban tapadas. Al vendedor le
llegaba como "no me muestra ningún producto para seleccionar" (2026-08-28).
"""
import os
import re

CSS_DIR = os.path.join(os.path.dirname(__file__), '..', 'static', 'css')
CSS_PANTALLA = os.path.join(CSS_DIR, 'pedido_nuevo.css')
CSS_FORMS = os.path.join(CSS_DIR, 'forms.css')


def _z_index_de(ruta, selector_parcial):
    """(valor, es_important) del primer bloque cuyo selector contenga el texto."""
    with open(ruta, encoding='utf-8') as fh:
        css = fh.read()
    # Sin comentarios: llevan ejemplos con selectores que no son reglas.
    css = re.sub(r'/\*.*?\*/', '', css, flags=re.S)
    for selectores, cuerpo in re.findall(r'([^{}]+)\{([^{}]*)\}', css):
        if selector_parcial not in selectores:
            continue
        m = re.search(r'z-index\s*:\s*(\d+)\s*(!important)?', cuerpo)
        if m:
            return int(m.group(1)), bool(m.group(2))
    return None, False


def test_el_shell_sigue_creando_su_contexto_de_apilado():
    """Guard del supuesto: si `.pn-shell` deja de tener z-index, este test
    deja de tener sentido y hay que revisar el arreglo, no borrarlo."""
    z_shell, _ = _z_index_de(CSS_PANTALLA, '.pn-shell')
    assert z_shell is not None, (
        '`.pn-shell` ya no declara z-index: revisar si el dropdown sigue '
        'necesitando superarlo.'
    )


def test_el_dropdown_de_productos_se_pinta_sobre_la_pantalla():
    z_shell, _ = _z_index_de(CSS_PANTALLA, '.pn-shell')
    z_dropdown, dropdown_important = _z_index_de(CSS_PANTALLA, '.pn-dropdown')

    assert z_dropdown is not None, (
        'El dropdown se monta en <body>, fuera de `.pn-shell`. Sin un z-index '
        f'propio se queda en el 1000 de Tom Select y la pantalla '
        f'(z-index {z_shell}) lo tapa.'
    )
    assert z_dropdown > z_shell, (
        f'El dropdown ({z_dropdown}) tiene que superar a `.pn-shell` ({z_shell}) '
        f'o las opciones quedan renderizadas pero tapadas.'
    )


def test_el_z_index_del_dropdown_le_gana_al_global_de_forms():
    """`forms.css` clava `.ts-dropdown { z-index: N !important }` para toda la
    app. Declarar el z-index de esta pantalla sin `!important` NO alcanza: la
    regla queda escrita pero pierde, y el bug sigue vivo aunque el CSS «diga»
    lo correcto. Este test verifica el valor EFECTIVO, no el declarado."""
    z_global, global_important = _z_index_de(CSS_FORMS, '.ts-dropdown')
    z_dropdown, dropdown_important = _z_index_de(CSS_PANTALLA, '.pn-dropdown')

    if z_global is None:
        return  # forms.css ya no fija z-index: no hay a quién ganarle

    assert z_dropdown > z_global, (
        f'El dropdown de la pantalla ({z_dropdown}) no supera al global de '
        f'forms.css ({z_global}).'
    )
    if global_important:
        assert dropdown_important, (
            f'`forms.css` fija z-index {z_global} con !important; sin '
            f'!important esta regla pierde y el dropdown vuelve a quedar tapado.'
        )
