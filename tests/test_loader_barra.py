"""Regresión: el loader es una barra superior (NProgress), sin overlay/anillo/%.

Verifica a nivel de fuente que base.html y base_inline.css ya no contienen el
markup/estilos del overlay viejo y sí la barra de progreso.
"""
import os

ROOT = os.path.join(os.path.dirname(__file__), '..')


def _read(rel):
    with open(os.path.join(ROOT, rel), encoding='utf-8') as fh:
        return fh.read()


def test_base_html_usa_barra_sin_overlay():
    html = _read('templates/base.html')
    # La barra existe
    assert 'id="appLoadingBar"' in html
    # El overlay viejo fue eliminado
    assert 'appLoadingScreen' not in html, "Quedó el overlay app-loading-screen"
    assert 'appLoadingPercent' not in html, "Quedó el porcentaje"
    assert 'app-loading-ring' not in html, "Quedó el anillo"
    assert 'app-loading-screen' not in html, "Quedó la clase del overlay"
    assert 'app-loading-label' not in html, "Quedó el label Cargando…"


def test_base_inline_css_sin_overlay():
    css = _read('static/css/base_inline.css')
    assert '.app-loading-bar' in css, "Debe conservar la barra"
    assert 'app-loading-screen' not in css, "Quedó CSS del overlay"
    assert 'app-loading-ring' not in css, "Quedó CSS del anillo"
    assert 'app-loading-percent' not in css, "Quedó CSS del porcentaje"
    assert 'app-loading-label' not in css, "Quedó CSS del label"
    assert 'app-loading-shimmer' not in css, "Quedó el keyframe shimmer viejo"
