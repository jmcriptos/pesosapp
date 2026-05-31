"""Regresión: en iOS (incluida la PWA standalone) las etiquetas se entregan
con la hoja de compartir nativa (Web Share API), no con un iframe ni pestaña
nueva. El comportamiento real de iOS solo se prueba en dispositivo; aquí se
verifica el cableado a nivel de fuente + el helper del servidor.
"""
import os

ROOT = os.path.join(os.path.dirname(__file__), '..')


def _read(rel):
    with open(os.path.join(ROOT, rel), encoding='utf-8') as fh:
        return fh.read()


def test_existe_helper_web_share():
    js = _read('static/js/etiquetas_ios_share.js')
    assert 'esDispositivoIOS' in js
    assert 'navigator.share' in js
    assert 'navigator.canShare' in js
    assert 'iP(hone|ad|od)' in js  # detección por dispositivo (cubre Chrome iOS)
    # Compartir SOLO el archivo: un title/text hace que iOS guarde un .txt extra.
    # Se verifica la llamada exacta, sin claves adicionales en el objeto share.
    assert 'navigator.share({ files: [file] })' in js
    assert 'navigator.share({ files: [file],' not in js


def test_detalles_pedido_usa_web_share_en_ios():
    html = _read('templates/detalles_pedido.html')
    assert 'etiquetas_ios_share.js' in html, "Falta incluir el helper de compartir"
    assert 'compartirEtiquetaIOS' in html, "Falta usar la hoja de compartir en iOS"
    # Ya no debe quedar el intento viejo de pestaña nueva
    assert "formEtiquetas.target = '_blank'" not in html


def test_etiquetas_vencimiento_usa_web_share_en_ios():
    html = _read('templates/form_generar_etiquetas.html')
    assert 'etiquetas_ios_share.js' in html, "Falta incluir el helper de compartir"
    assert 'compartirEtiquetaIOS' in html, "Falta usar la hoja de compartir en iOS"
    assert "form.target = '_blank'" not in html


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


def test_nombre_archivo_etiquetas_estructura():
    """El PDF de etiquetas de pedido se nombra etiquetas_<cliente>_<pedido_id>."""
    py = _read('app.py')
    assert 'f"etiquetas_{nombre_cliente}_{pedido_id}.pdf"' in py
    html = _read('templates/detalles_pedido.html')
    assert 'ETIQ_FILENAME' in html
    assert "'etiquetas_'" in html and 'pedido.id' in html
