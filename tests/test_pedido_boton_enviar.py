"""El botón principal del alta de pedido no puede quedar apagado por CSS.

Regresión real: un rediseño del pie movió «Continuar» DENTRO de
`.pn-footer-row` y lo acompañó con dos reglas:

    #pn-shell .pn-footer .pn-enviar     { display: none; }
    #pn-shell .pn-footer-row .pn-enviar { display: inline-flex; }

La primera apaga TODOS los `.pn-enviar` de CUALQUIER pie; la segunda solo
revive los que están dentro de la fila. «Enviar pedido» (paso 04) y «Tomar
otro pedido» (confirmación) son hijos directos de su pie, sin fila: quedaban
con `display:none` y el vendedor no podía cerrar el pedido. No era un bug de
iOS — pasaba en cualquier navegador, siempre.
"""
import re
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
CSS = BASE / 'static' / 'css' / 'pedido_nuevo.css'
TPL = BASE / 'templates' / 'pedido_form.html'


def _reglas(css):
    """(selector, cuerpo) de cada bloque de primer nivel."""
    return re.findall(r'([^{}]+?)\s*\{([^{}]*)\}', css)


def test_ninguna_regla_general_apaga_el_boton_principal():
    apagados = []
    for selector, cuerpo in _reglas(CSS.read_text(encoding='utf-8')):
        if not re.search(r'display\s*:\s*none', cuerpo):
            continue
        for sel in (s.strip() for s in selector.split(',')):
            # Solo importan las reglas cuyo objetivo FINAL es el botón: una
            # regla sobre un ancestro (un paso oculto) es legítima.
            if not sel.endswith('.pn-enviar'):
                continue
            # `.pn-footer-row` puede recolocar su propio botón: ese caso está
            # acotado a la fila y no alcanza a los otros pies.
            if '.pn-footer-row' in sel:
                continue
            apagados.append(sel)

    assert not apagados, (
        'Estas reglas apagan el botón principal fuera de .pn-footer-row, '
        'dejando sin acción a la revisión y a la confirmación: '
        + ', '.join(apagados)
    )


def test_los_tres_botones_principales_siguen_en_la_plantilla():
    """Si alguno se renombra, el test de arriba dejaría de proteger nada."""
    html = TPL.read_text(encoding='utf-8')
    for boton in ('pn-continuar', 'pn-enviar', 'pn-conf-otro'):
        assert f'id="{boton}"' in html, f'falta el botón {boton}'
