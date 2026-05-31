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


# Chrome para iPhone manda 'CriOS' (no 'Safari') pero incluye 'iPhone' en el UA
_UA_IPHONE_CHROME = ('Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) '
                     'AppleWebKit/605.1.15 (KHTML, like Gecko) CriOS/120.0 Mobile/15E148 Safari/604.1')
_UA_IPAD = 'Mozilla/5.0 (iPad; CPU OS 16_0 like Mac OS X) AppleWebKit/605.1.15'
_UA_ANDROID = ('Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36 '
               '(KHTML, like Gecko) Chrome/120.0 Mobile Safari/537.36')


def test_is_ios_request_detecta_iphone_chrome():
    from app import app as flask_app, _is_ios_request
    with flask_app.test_request_context(headers={'User-Agent': _UA_IPHONE_CHROME}):
        assert _is_ios_request() is True
    with flask_app.test_request_context(headers={'User-Agent': _UA_IPAD}):
        assert _is_ios_request() is True


def test_is_ios_request_android_es_falso():
    from app import app as flask_app, _is_ios_request
    with flask_app.test_request_context(headers={'User-Agent': _UA_ANDROID}):
        assert _is_ios_request() is False
