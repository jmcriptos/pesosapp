"""Regresión: en iOS las etiquetas se abren en pestaña nueva, no en el iframe.

iOS (incluido Chrome para iPhone, que usa WebKit) no dispara descargas desde
un iframe oculto. Ambos formularios deben detectar iOS y poner target=_blank.
Verificación a nivel de fuente (el comportamiento real de iOS solo se prueba
en dispositivo).
"""
import os

ROOT = os.path.join(os.path.dirname(__file__), '..')


def _read(rel):
    with open(os.path.join(ROOT, rel), encoding='utf-8') as fh:
        return fh.read()


def test_detalles_pedido_abre_pestana_en_ios():
    html = _read('templates/detalles_pedido.html')
    assert '_esIOS' in html, "Falta la detección de iOS en etiquetas de pedido"
    # Detecta por dispositivo (cubre Chrome iOS = CriOS), no por navegador
    assert 'iP(hone|ad|od)' in html
    assert "formEtiquetas.target = '_blank'" in html


def test_etiquetas_vencimiento_abre_pestana_en_ios():
    html = _read('templates/form_generar_etiquetas.html')
    assert '_esIOS' in html, "Falta la detección de iOS en etiquetas de vencimiento"
    assert 'iP(hone|ad|od)' in html
    assert "form.target = '_blank'" in html
