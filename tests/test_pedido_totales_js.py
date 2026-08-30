# tests/test_pedido_totales_js.py
"""El desglose Subtotal/OB/Total de la revisión del form de pedidos
(`pintarTotales` en `templates/pedido_form.html`) solo tenía una
verificación manual de una sola vez en navegador (Task 6) — ni un test de
pytest ni de JS protegía que Subtotal + OB = Total, que el grupo 14 (OB 0%)
no dibuje la fila de OB, o que la exportación gane sobre el grupo (mismo
`_es_exportacion` que decide el payload a QuickBooks).

La aritmética se extrajo a `static/js/pedido_totales.js`
(`calcularTotalesPedido`), un módulo UMD sin DOM que corre igual en el
navegador y en Node — hay Node v16 instalado en este entorno. Este archivo
la ejercita con Node vía `subprocess` (no hay harness de JS en la suite de
pytest) para los tres casos del hallazgo.
"""
import json
import pathlib
import shutil
import subprocess

import pytest

_ROOT = pathlib.Path(__file__).resolve().parent.parent
_MODULO = _ROOT / 'static' / 'js' / 'pedido_totales.js'
_NODE = shutil.which('node')


def _calcular(subtotal, es_exportacion, codigo, ob_por_codigo):
    """Corre `calcularTotalesPedido(subtotal, opciones)` en Node y devuelve
    el resultado como dict de Python, vía JSON — el mismo módulo que carga
    `pedido_form.html` en el navegador, `require`-ado tal cual."""
    assert _NODE, 'node no está en PATH'
    script = (
        "const calcularTotalesPedido = require(%(ruta)s);"
        "const r = calcularTotalesPedido(%(subtotal)s, {"
        "  esExportacion: %(exportacion)s,"
        "  codigo: %(codigo)s,"
        "  obPorCodigo: %(mapa)s,"
        "});"
        "process.stdout.write(JSON.stringify(r));"
    ) % {
        'ruta': json.dumps(str(_MODULO)),
        'subtotal': json.dumps(subtotal),
        'exportacion': json.dumps(es_exportacion),
        'codigo': json.dumps(codigo),
        'mapa': json.dumps(ob_por_codigo),
    }
    proc = subprocess.run([_NODE, '-e', script], capture_output=True, text=True, timeout=30)
    assert proc.returncode == 0, (
        f'Node falló (código {proc.returncode}):\n'
        f'--- stdout ---\n{proc.stdout}\n--- stderr ---\n{proc.stderr}'
    )
    return json.loads(proc.stdout)


# Mismo diccionario que `_OB_POR_CODIGO` en app.py: código 10 -> OB 6%,
# código 14 -> OB 0%.
_OB_POR_CODIGO = {'10': 6.0, '14': 0.0}


@pytest.mark.skipif(_NODE is None, reason='node no está instalado en este entorno')
def test_grupo_10_desglosa_ob_6_por_ciento_y_subtotal_mas_ob_es_total():
    r = _calcular(200.0, False, 10, _OB_POR_CODIGO)
    assert r['filaObHidden'] is False
    assert r['filaTotalHidden'] is False
    assert r['obMonto'] == pytest.approx(12.0)  # 200 * 6%
    assert r['total'] == pytest.approx(212.0)
    assert r['total'] == pytest.approx(200.0 + r['obMonto']), (
        'Subtotal + OB != Total — la cuenta que el vendedor le cotiza al '
        'cliente no cierra con lo que la factura va a cobrar'
    )
    assert r['obLabel'] == 'OB 6%'


@pytest.mark.skipif(_NODE is None, reason='node no está instalado en este entorno')
def test_grupo_14_no_dibuja_la_fila_de_ob_y_total_es_el_subtotal():
    """«OB 0% — 0.00» es ruido: el grupo 14 no paga impuesto, así que la
    fila de OB queda oculta y el total inclusivo es igual al subtotal."""
    r = _calcular(350.0, False, 14, _OB_POR_CODIGO)
    assert r['filaObHidden'] is True
    assert r['filaTotalHidden'] is False
    assert r['total'] == pytest.approx(350.0)
    assert r['obMonto'] is None


@pytest.mark.skipif(_NODE is None, reason='node no está instalado en este entorno')
def test_exportacion_gana_sobre_el_grupo_aunque_el_grupo_cobre_ob():
    """Un cliente USD (exportación) se factura exento sea cual sea la
    mercadería — mismo criterio que `_tax_code_de_linea`/`_es_exportacion`
    en app.py, que manda sobre el grupo también en el payload. Acá: grupo
    10 (que SÍ cobra OB 6% a un cliente XCG) tiene que salir exento igual
    cuando `esExportacion` es true."""
    r = _calcular(500.0, True, 10, _OB_POR_CODIGO)
    assert r['filaObHidden'] is True
    assert r['filaTotalHidden'] is False
    assert r['total'] == pytest.approx(500.0)
    assert r['notaHidden'] is False
    assert 'Exportación' in r['nota']
