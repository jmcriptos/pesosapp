"""Teclear el mismo dígito dos veces seguidas (p. ej. "11") no debe disparar
el zoom por doble toque del móvil en los teclados numéricos."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _reglas_con_manipulation(ruta):
    css = (ROOT / ruta).read_text(encoding='utf-8')
    css = re.sub(r'/\*.*?\*/', '', css, flags=re.S)
    selectores = set()
    for sel, cuerpo in re.findall(r'([^{}]+)\{([^{}]*)\}', css):
        if re.search(r'touch-action:\s*manipulation', cuerpo):
            selectores.update(s.strip() for s in sel.split(','))
    return selectores


def test_teclado_pesar_sin_zoom_doble_toque():
    sel = _reglas_con_manipulation('static/css/pesar.css')
    for esperado in ('.pesar-keypad-card', '.pesar-key', '.pesar-edit-key', '.pesar-edit-keypad'):
        assert esperado in sel


def test_teclado_temperaturas_sin_zoom_doble_toque():
    sel = _reglas_con_manipulation('static/css/operaciones.css')
    for esperado in ('.ops-keypad', '.ops-key', '.ops-step'):
        assert esperado in sel
