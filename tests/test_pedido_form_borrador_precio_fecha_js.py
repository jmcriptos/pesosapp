# tests/test_pedido_form_borrador_precio_fecha_js.py
"""`ofrecerBorrador()` (`templates/pedido_form.html`) tenía un defecto
medido en el navegador: un borrador viejo de `localStorage` pisaba el
precio de catálogo con uno cacheado — el vendedor veía Total 314.82 cuando
el real era 416.83 (30% abajo), y le cotizaba ese número al cliente
mientras la factura salía con el otro. El arreglo re-cotiza SIEMPRE contra
el `productos` que el servidor sirvió en esta carga, le puso caducidad al
borrador (`BORRADOR_VENTANA_MS`, 36 h), no impone una fecha de entrega
restaurada que ya quedó en el pasado, y toma el nombre del producto del
catálogo (no el que quedó cacheado en el borrador).

Estaba arreglado pero sin ningún test: la re-revisión probó cuatro
mutaciones puntuales sobre `ofrecerBorrador()` y ninguna la detectaba. Este
archivo cierra ese agujero — mismo método que
`test_pedido_form_borrador_alta_vs_edicion_cruce.py`: extrae las funciones
REALES de `pedido_form.html` (mismo texto que corre en el navegador, no una
reimplementación) y las ejecuta con Node, sembrando `localStorage` a mano
con el borrador exacto que dispara cada caso.

Requiere `node` en PATH. Si no está disponible, se salta con motivo
explícito.
"""
import json
import pathlib
import re
import shutil
import subprocess
import time

import pytest

_ROOT = pathlib.Path(__file__).resolve().parent.parent
_PEDIDO_FORM_HTML = _ROOT / 'templates' / 'pedido_form.html'

_NODE = shutil.which('node')

# Mismos datos concretos medidos en el navegador que trae la tarea: un
# borrador con precio cacheado 99.00 para el producto que hoy vale 131.08
# en el catálogo servido en esta carga.
_PRECIO_CACHEADO = 99.00
_PRECIO_CATALOGO = 131.08
_CAJAS = 3


def _js():
    return _PEDIDO_FORM_HTML.read_text(encoding='utf-8')


def _funcion_completa(texto, nombre):
    """Texto completo `function nombre(...) { ... }`, rastreando llaves —
    mismo algoritmo que en `test_pedido_form_borrador_alta_vs_edicion_cruce.py`:
    el driver de Node necesita poder LLAMAR a estas funciones por nombre,
    así que se extrae la declaración entera (con firma), no solo el
    cuerpo."""
    m = re.search(r'function\s+' + re.escape(nombre) + r'\s*\([^)]*\)\s*\{', texto)
    assert m, f'no se encontró function {nombre}() en pedido_form.html'
    inicio = m.end()
    profundidad = 1
    i = inicio
    while profundidad > 0:
        if texto[i] == '{':
            profundidad += 1
        elif texto[i] == '}':
            profundidad -= 1
        i += 1
    return texto[m.start():i]


def _extraer_fuente_borrador():
    """Junta, en el orden correcto, todo lo que `ofrecerBorrador` necesita
    para correr fuera del navegador: la constante de vigencia, y las
    funciones de las que depende (`fechaDesdeIso` para no imponer una
    entrega vieja, `claveBorrador`/`borrarBorrador` para la caducidad)."""
    texto = _js()

    m_ventana = re.search(r'const BORRADOR_VENTANA_MS = [^;]+;', texto)
    assert m_ventana, 'no se encontró BORRADOR_VENTANA_MS en pedido_form.html'

    piezas = [m_ventana.group(0)]
    for nombre in ('fechaDesdeIso', 'claveBorrador', 'guardarBorrador',
                   'borrarBorrador', 'ofrecerBorrador'):
        piezas.append(_funcion_completa(texto, nombre))
    return '\n\n'.join(piezas)


# El driver de Node: siembra `localStorage` a mano con el borrador exacto
# (control total sobre `ts`, precio y nombre cacheados, sin pasar por
# `guardarBorrador`) y corre `ofrecerBorrador()` una sola vez, igual que el
# arranque real de la pantalla de alta con cliente+grupo ya resueltos
# (`/pedidos/nuevo?cliente=3&grupo=imp:10`).
_DRIVER_JS = r"""
'use strict';
const assert = require('assert');

function crearLocalStorage() {
    const store = Object.create(null);
    return {
        getItem: (k) => (k in store ? store[k] : null),
        setItem: (k, v) => { store[k] = String(v); },
        removeItem: (k) => { delete store[k]; },
        _store: store,
    };
}

const localStorage = crearLocalStorage();
let confirmRespuesta = true;
let confirmLlamadas = 0;
function confirm(_msg) { confirmLlamadas++; return confirmRespuesta; }

const inputFechaEntrega = { value: %(FECHA_INICIAL)s };
const notasEl = { value: '' };
function $(id) { return id === 'notas' ? notasEl : null; }

// ── Fuente real, extraída de templates/pedido_form.html ────────────────
%(FUENTE)s

let esEdicion = false;
let clienteId = 3;
let grupoActual = 'imp:10';  // ya resuelto, como en el alta con cliente+grupo en la URL
let productosAgregados = [];
let intentoId = 'intento-original';
const productos = [
    { id: 501, nombre: 'Chuleta ahumada 5kg', precio: %(PRECIO_CATALOGO)s, grupo: 'imp:10' },
];

// Siembra el borrador exacto de este caso — el mismo `localStorage` que
// dejó una carga anterior de la pantalla, sin pasar por guardarBorrador()
// para poder fijar ts/precio/nombre a mano.
const clave = claveBorrador();
localStorage.setItem(clave, JSON.stringify(%(DATOS)s));

ofrecerBorrador();

const resultado = {
    productosAgregados: productosAgregados,
    fechaEntregaTrasOfrecer: inputFechaEntrega.value,
    confirmLlamadas: confirmLlamadas,
    borradorSobreviveTrasOfrecer: localStorage.getItem(clave) !== null,
};
process.stdout.write(JSON.stringify(resultado));
"""


def _correr(datos_borrador, fecha_inicial=''):
    assert _NODE, 'node no está en PATH'
    fuente = _extraer_fuente_borrador()
    script = _DRIVER_JS % {
        'FUENTE': fuente,
        'DATOS': json.dumps(datos_borrador),
        'FECHA_INICIAL': json.dumps(fecha_inicial),
        'PRECIO_CATALOGO': json.dumps(_PRECIO_CATALOGO),
    }
    proc = subprocess.run([_NODE, '-e', script], capture_output=True, text=True, timeout=30)
    assert proc.returncode == 0, (
        f'el driver de Node falló (código {proc.returncode}):\n'
        f'--- stdout ---\n{proc.stdout}\n--- stderr ---\n{proc.stderr}'
    )
    return json.loads(proc.stdout)


def _ts_hace(horas):
    return int((time.time() - horas * 3600) * 1000)


@pytest.mark.skipif(_NODE is None, reason='node no está instalado en este entorno')
def test_ofrecer_borrador_recotiza_contra_el_catalogo_no_el_precio_cacheado():
    """El defecto original: un borrador con precio cacheado 99.00 para un
    producto que hoy vale 131.08 en el catálogo de ESTA carga no puede
    restaurar el 99.00 — eso es lo que le hizo cantar 314.82 en vez de
    416.83 al vendedor."""
    datos = {
        'lineas': [
            {'id': 501, 'nombre': 'Chuleta ahumada 5kg', 'cajas': _CAJAS,
             'precio': _PRECIO_CACHEADO, 'habitual': None, 'activa': True},
        ],
        'fecha_entrega': '',
        'notas': '',
        'intento_id': 'intento-1',
        'ts': _ts_hace(0),
    }
    r = _correr(datos)

    assert r['confirmLlamadas'] == 1, 'un borrador fresco tiene que ofrecerse'
    assert len(r['productosAgregados']) == 1
    linea = r['productosAgregados'][0]
    assert linea['precio'] == pytest.approx(_PRECIO_CATALOGO), (
        f"se restauró el precio cacheado del borrador ({linea['precio']}) en vez "
        f"del precio del catálogo de esta carga ({_PRECIO_CATALOGO}) — el defecto "
        "original: 314.82 cotizado contra 416.83 real"
    )
    subtotal = linea['cajas'] * linea['precio']
    assert subtotal == pytest.approx(_CAJAS * _PRECIO_CATALOGO)
    assert subtotal != pytest.approx(_CAJAS * _PRECIO_CACHEADO)


@pytest.mark.skipif(_NODE is None, reason='node no está instalado en este entorno')
def test_ofrecer_borrador_descarta_sin_preguntar_pasada_la_ventana_de_36h():
    """Un borrador de hace 37 horas (más viejo que `BORRADOR_VENTANA_MS`,
    36 h) es un pedido fósil: se descarta directo, nunca se ofrece con
    confirm(), y no queda vivo en localStorage para la próxima carga."""
    datos = {
        'lineas': [
            {'id': 501, 'nombre': 'Chuleta ahumada 5kg', 'cajas': _CAJAS,
             'precio': _PRECIO_CACHEADO, 'habitual': None, 'activa': True},
        ],
        'fecha_entrega': '',
        'notas': '',
        'intento_id': 'intento-viejo',
        'ts': _ts_hace(37),
    }
    r = _correr(datos)

    assert r['confirmLlamadas'] == 0, (
        'preguntó "¿seguir donde lo dejaste?" con un borrador de 37 horas — '
        'un pedido fósil no se ofrece'
    )
    assert r['productosAgregados'] == [], (
        'restauró líneas de un borrador de 37 horas — pasada la ventana de '
        '36h no se restaura nada'
    )
    assert r['borradorSobreviveTrasOfrecer'] is False, (
        'el borrador fósil siguió vivo en localStorage después de '
        'ofrecerBorrador() — tenía que borrarse'
    )


@pytest.mark.skipif(_NODE is None, reason='node no está instalado en este entorno')
def test_ofrecer_borrador_no_impone_una_fecha_de_entrega_ya_pasada():
    """Una fecha de entrega restaurada del borrador que ya quedó en el
    pasado (2026-01-05) no se impone en silencio — el input de fecha se
    deja como estaba, para que el arranque de la pantalla ponga su propio
    default. Una fecha futura sí se restaura (control: el mecanismo de
    restaurar fecha no está simplemente apagado)."""
    datos_pasada = {
        'lineas': [
            {'id': 501, 'nombre': 'Chuleta ahumada 5kg', 'cajas': _CAJAS,
             'precio': _PRECIO_CACHEADO, 'habitual': None, 'activa': True},
        ],
        'fecha_entrega': '2026-01-05',
        'notas': '',
        'intento_id': 'intento-fecha-pasada',
        'ts': _ts_hace(0),
    }
    r_pasada = _correr(datos_pasada, fecha_inicial='')
    assert r_pasada['fechaEntregaTrasOfrecer'] == '', (
        'una fecha de entrega restaurada del pasado (2026-01-05) se impuso '
        f"en el input ({r_pasada['fechaEntregaTrasOfrecer']!r}) — un pedido "
        'con entrega ya vencida'
    )

    datos_futura = dict(datos_pasada, fecha_entrega='2026-12-31',
                         intento_id='intento-fecha-futura')
    r_futura = _correr(datos_futura, fecha_inicial='')
    assert r_futura['fechaEntregaTrasOfrecer'] == '2026-12-31', (
        'una fecha de entrega futura del borrador NO se restauró — el '
        'mecanismo de restaurar fecha quedó apagado de más'
    )


@pytest.mark.skipif(_NODE is None, reason='node no está instalado en este entorno')
def test_ofrecer_borrador_toma_el_nombre_del_producto_del_catalogo():
    """El nombre mostrado tiene que salir del catálogo de esta carga, no
    del que quedó cacheado en el borrador — un producto puede haberse
    renombrado desde que se guardó el borrador."""
    datos = {
        'lineas': [
            {'id': 501, 'nombre': 'Nombre viejo cacheado', 'cajas': _CAJAS,
             'precio': _PRECIO_CACHEADO, 'habitual': None, 'activa': True},
        ],
        'fecha_entrega': '',
        'notas': '',
        'intento_id': 'intento-nombre',
        'ts': _ts_hace(0),
    }
    r = _correr(datos)

    assert len(r['productosAgregados']) == 1
    assert r['productosAgregados'][0]['nombre'] == 'Chuleta ahumada 5kg', (
        f"se restauró el nombre cacheado del borrador "
        f"({r['productosAgregados'][0]['nombre']!r}) en vez del nombre del "
        "catálogo de esta carga ('Chuleta ahumada 5kg')"
    )
