"""Texto suelto legible sobre el contenido claro de todas las pantallas.

`dark-theme.css` se carga en TODAS y pinta elementos sueltos para fondo oscuro:
`label { color:#f1f5f9 !important }` (:175) y el bloque «Text Globals»
(:968-974) con `p`, `small`, `strong`, `h1..h6`.

Pero el marco oscuro es solo el marco. Medido en dashboard, precios, productos
y pedidos: el `<body>` es #0b0e14 y `main.app-content` es #f8fafc en las cuatro.
Esos colores caen sobre fondo CLARO en todas — un `label` daba 1.05:1 y un `p`
2.45:1. El caso real: la etiqueta del checkbox «Se pesa» del form de productos,
que medí en 1.10:1.

Había un guard equivalente en gestion.css, pero dentro de
`@media (prefers-color-scheme: dark)`: solo protegía a quien tuviera el SISTEMA
en modo oscuro, no el caso normal.

NO se toca `dark-theme.css`: envolver sus reglas en `body:not(...)` les subiría
la especificidad de (0,0,1) a (0,3,1) y empezarían a ganar donde hoy pierden.

Esto se afirma sobre el CSS porque pytest no computa estilos; la medición en
navegador (1.10 -> 7.58 en «Se pesa») queda en el commit.
"""
import os
import re

import pytest

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _css(ruta):
    with open(os.path.join(RAIZ, ruta), encoding='utf-8') as fh:
        return fh.read()


def _sin_comentarios(css):
    """Los comentarios de estas hojas citan CSS con llaves adentro; sin sacarlos
    el parseo de bloques se corrompe."""
    return re.sub(r'/\*.*?\*/', '', css, flags=re.S)


def _regla(css, selector):
    """El bloque cuyo selector contiene exactamente ese selector."""
    for m in re.finditer(r'([^{}]+)\{([^}]*)\}', _sin_comentarios(css)):
        selectores = [s.strip() for s in m.group(1).split(',')]
        if selector in selectores:
            return m.group(2)
    return None


@pytest.mark.parametrize('elemento', ['label', 'p', 'small', 'strong'])
def test_el_contenido_claro_reclama_el_color_del_texto_suelto(elemento):
    css = _css('static/css/app-mobile.css')
    cuerpo = _regla(css, f'main.app-content {elemento}')
    assert cuerpo and 'color' in cuerpo, (
        f'<{elemento}> queda con el color que dark-theme.css pone para fondo oscuro'
    )


def test_el_guard_de_label_usa_important():
    """`label` en dark-theme.css es !important: solo otro !important lo gana."""
    cuerpo = _regla(_css('static/css/app-mobile.css'), 'main.app-content label')
    assert cuerpo and '!important' in cuerpo, (
        'sin !important el guard pierde contra dark-theme.css:175'
    )


def test_el_guard_carga_despues_del_tema_oscuro():
    """El orden de la cascada es lo que hace innecesario subir especificidad."""
    base = _css('templates/base.html')
    assert base.index('dark-theme.css') < base.index('app-mobile.css'), (
        'app-mobile.css tiene que cargarse después de dark-theme.css'
    )


def test_el_guard_no_toca_fondos_ni_layout():
    """Solo color: un guard que además pintara fondos rompería componentes que
    hoy se dibujan bien encima del contenido."""
    css = _css('static/css/app-mobile.css')
    for elemento in ('label', 'p', 'small', 'strong'):
        cuerpo = _regla(css, f'main.app-content {elemento}') or ''
        assert 'background' not in cuerpo, f'el guard de <{elemento}> toca fondos'
        assert 'font-size' not in cuerpo, f'el guard de <{elemento}> toca tamaños'


def test_no_se_toco_el_tema_oscuro_global():
    """Regresión: el marco oscuro (topbar, tabbar) sigue dependiendo de estas
    reglas. Scopearlas allá era el camino riesgoso que se descartó."""
    css = _css('static/css/dark-theme.css')
    assert re.search(r'^label \{[^}]*color', css, re.M)
    assert re.search(r'^p \{[^}]*color', css, re.M)
