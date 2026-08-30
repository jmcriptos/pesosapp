# tests/test_pedido_form_borrador_alta_vs_edicion_cruce.py
"""REVISIÓN FINAL DE RAMA — el hallazgo bloqueante que ninguna tarea pudo
ver sola, porque cada una leía UNA función del fuente por vez.

La clave del borrador (`borrador:<cliente>:<grupo>`) era la MISMA para el
alta y la edición, y la edición la ESCRIBÍA SIN LEERLA NUNCA — una
asimetría en el orden del arranque (`ofrecerBorrador()` corría con
`grupoActual` todavía `null` en edición, así que nunca encontraba nada que
ofrecer; pero la primera línea que trae el servidor fijaba `grupoActual`
un poco más abajo, y de ahí en más cada repintado guardaba). Dos daños
reproducidos en el navegador:

  (a) Abrir una edición PISA en silencio un alta a medio escribir del
      mismo cliente+grupo.
  (b) Abrir una edición y salir SIEMBRA un borrador fantasma que la
      pantalla de alta ofrece como "pedido sin enviar" — aceptarlo carga
      las líneas del pedido viejo rotuladas "Añadido", un duplicado real
      listo para facturarse.

Los 55 tests de las Tasks 3 y 4 (`test_pedido_form_no_perder_pedido.py`,
`test_pedido_form_envio_fetch.py`) leen una función del fuente A LA VEZ, vía
regex sobre el texto — nunca las EJECUTAN, y mucho menos en secuencia. Por
eso el defecto sobrevivió seis revisiones. Este archivo es distinto: extrae
las funciones reales de `pedido_form.html` (mismo texto que corre en el
navegador, no una reimplementación) y las EJECUTA con Node en dos "cargas
de pantalla" sucesivas que comparten el mismo `localStorage` en memoria —
igual que dos pestañas/navegaciones reales del mismo teléfono — para probar
que abrir una edición no deja rastro en la clave del alta.

Requiere `node` en PATH (hay v16 instalado en este entorno; ver progress.md
de este lote). Si no está disponible, el test se salta con motivo explícito
en vez de fallar en cualquier máquina que no lo tenga.
"""
import json
import pathlib
import re
import shutil
import subprocess

import pytest

_ROOT = pathlib.Path(__file__).resolve().parent.parent
_PEDIDO_FORM_HTML = _ROOT / 'templates' / 'pedido_form.html'

_NODE = shutil.which('node')


def _js():
    return _PEDIDO_FORM_HTML.read_text(encoding='utf-8')


def _funcion_completa(texto, nombre):
    """Texto completo `function nombre(...) { ... }`, rastreando llaves —
    mismo algoritmo que `_cuerpo_funcion` en test_pedido_form_no_perder_pedido.py,
    pero devolviendo la declaración entera (con firma), no solo el cuerpo:
    el driver de Node necesita poder LLAMAR a estas funciones por nombre."""
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
    """Junta, en el orden correcto, todo lo que las funciones del borrador
    necesitan para correr fuera del navegador: la constante de vigencia, y
    las cuatro funciones (`claveBorrador`, `guardarBorrador`,
    `borrarBorrador`, `ofrecerBorrador`) más `fechaDesdeIso`, de la que
    `ofrecerBorrador` depende para no imponer una entrega vieja en
    silencio."""
    texto = _js()

    m_ventana = re.search(r'const BORRADOR_VENTANA_MS = [^;]+;', texto)
    assert m_ventana, 'no se encontró BORRADOR_VENTANA_MS en pedido_form.html'

    piezas = [m_ventana.group(0)]
    for nombre in ('fechaDesdeIso', 'claveBorrador', 'guardarBorrador',
                   'borrarBorrador', 'ofrecerBorrador'):
        piezas.append(_funcion_completa(texto, nombre))
    return '\n\n'.join(piezas)


# El driver de Node: dos "cargas de pantalla" en secuencia, compartiendo un
# único localStorage en memoria (el mismo teléfono, la misma pestaña PWA).
_DRIVER_JS = r"""
'use strict';
const assert = require('assert');

// ── Harness mínimo: localStorage real (no un mock que siempre "funciona"
// distinto de localStorage de verdad), confirm() controlable, y los dos
// elementos del DOM que estas funciones tocan. ──────────────────────────
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

const inputFechaEntrega = { value: '' };
const notasEl = { value: '' };
function $(id) { return id === 'notas' ? notasEl : null; }

// ── Fuente real, extraída de templates/pedido_form.html ────────────────
%(FUENTE)s

// ── Estado de módulo que estas funciones cierran por closure (igual que
// en pedido_form.html): `let`, porque ofrecerBorrador/guardarBorrador
// reasignan grupoActual/productosAgregados/intentoId/esEdicion entre
// "pantallas". ───────────────────────────────────────────────────────
let esEdicion = false;
let clienteId = 3;
let grupoActual = null;
let productosAgregados = [];
let intentoId = 'intento-inicial';
const productos = [
    { id: 501, nombre: 'Chuleta ahumada 5kg', precio: 131.08, grupo: 'imp:10' },
];

const resultados = {};

// ═══ PANTALLA A: abrir /pedidos/27/editar ══════════════════════════════
// Mismo orden que el arranque real de pedido_form.html: ofrecerBorrador()
// corre con grupoActual TODAVÍA null (nada fijado por el paso 1 en una
// edición sin grupo del servidor); recién después el arranque fija
// grupoActual desde la primera línea que trajo el pedido, y de ahí en más
// cada actualizarTablaProductos() real llama a guardarBorrador() — acá se
// invoca directo, que es lo único que actualizarTablaProductos le agrega
// al margen del pintado en el DOM.
esEdicion = true;
grupoActual = null;
productosAgregados = [];

ofrecerBorrador();  // arranque, línea 959 del template — grupoActual aún null

// El servidor ya resolvió las líneas del pedido 27 en este grupo:
productosAgregados = [
    { id: 501, nombre: 'Chuleta ahumada 5kg', cajas: 3, precio: 131.08, habitual: null, activa: true },
];
if (productosAgregados.length && !grupoActual) {
    grupoActual = 'imp:10';  // grupoDeProducto(productosAgregados[0].id)
}
guardarBorrador();  // lo que actualizarTablaProductos() dispara al repintar

resultados.claveDeAltaExisteTrasEdicion =
    localStorage.getItem('borrador:3:imp:10') !== null;
resultados.confirmLlamadasEnPantallaA = confirmLlamadas;

// ═══ PANTALLA B: /pedidos/nuevo?cliente=3&grupo=imp:10, MISMO teléfono ═
esEdicion = false;
clienteId = 3;
grupoActual = 'imp:10';  // viene resuelto del paso 1, como en el alta real
productosAgregados = [];
confirmRespuesta = true;  // si algo quedó para ofrecer, el vendedor diría que sí

ofrecerBorrador();  // arranque del alta, misma línea 959

resultados.lineasOfrecidasEnPantallaB = productosAgregados.length;
resultados.confirmLlamadasEnPantallaB = confirmLlamadas;
resultados.localStorageTrasLasDosPantallas = Object.keys(localStorage._store);

process.stdout.write(JSON.stringify(resultados));
"""


def _correr_driver(fuente):
    assert _NODE, 'node no está en PATH'
    script = _DRIVER_JS % {'FUENTE': fuente}
    proc = subprocess.run(
        [_NODE, '-e', script],
        capture_output=True, text=True, timeout=30,
    )
    assert proc.returncode == 0, (
        f'el driver de Node falló (código {proc.returncode}):\n'
        f'--- stdout ---\n{proc.stdout}\n--- stderr ---\n{proc.stderr}'
    )
    return json.loads(proc.stdout)


@pytest.mark.skipif(_NODE is None, reason='node no está instalado en este entorno')
def test_abrir_una_edicion_no_escribe_ni_ofrece_el_borrador_del_alta():
    """La secuencia exacta del hallazgo, ejecutada de verdad (no leída de a
    una función): abrir una edición (Pantalla A) no puede dejar NINGÚN
    rastro en `localStorage` bajo la clave `borrador:<cliente>:<grupo>` del
    alta — ni escribiéndola directo, ni quedando disponible para que la
    Pantalla B (el alta del MISMO cliente+grupo, la siguiente vez que el
    vendedor toca "Nuevo pedido") la encuentre y la ofrezca como "pedido
    sin enviar"."""
    fuente = _extraer_fuente_borrador()
    r = _correr_driver(fuente)

    assert r['claveDeAltaExisteTrasEdicion'] is False, (
        'abrir una edición ESCRIBIÓ borrador:3:imp:10 — la misma clave que '
        'usa el alta de ese cliente+grupo. Un alta a medio escribir en esa '
        'clave se hubiera pisado sin aviso al abrir esta edición'
    )
    assert r['confirmLlamadasEnPantallaA'] == 0, (
        'ofrecerBorrador() preguntó "¿seguir donde lo dejaste?" DENTRO de '
        'una edición — no debería haber nada que ofrecer, la edición no '
        'lee (ni debería leer) esta clave'
    )

    assert r['lineasOfrecidasEnPantallaB'] == 0, (
        'la Pantalla B (alta nueva del mismo cliente+grupo) restauró líneas '
        'de un borrador — son las líneas del PEDIDO 27 que la edición '
        'sembró: un "Sí" en el confirm() de más abajo las carga como si el '
        'vendedor las hubiera tecleado, un duplicado real'
    )
    assert r['confirmLlamadasEnPantallaB'] == 0, (
        'la Pantalla B llegó a preguntar "¿seguir donde lo dejaste?" con '
        'datos que en realidad son del pedido editado en la Pantalla A — '
        'la trampa que un "Sí" distraído convierte en un pedido duplicado'
    )
    assert r['localStorageTrasLasDosPantallas'] == [], (
        'quedó algo en localStorage después de las dos pantallas — '
        f'{r["localStorageTrasLasDosPantallas"]!r}'
    )


@pytest.mark.skipif(_NODE is None, reason='node no está instalado en este entorno')
def test_el_alta_normal_si_guarda_y_se_ofrece_a_si_misma():
    """Control negativo: el fix no puede haber apagado el borrador del alta
    en general — dos "pantallas" de ALTA seguidas (recarga a mitad de
    camino, no una edición de por medio) tienen que seguir viendo el
    mismo borrador."""
    fuente = _extraer_fuente_borrador()
    driver = _DRIVER_JS % {'FUENTE': fuente}
    # Mismo driver, pero la Pantalla A es un ALTA (no edición) que agrega
    # una línea antes de "recargar" en la Pantalla B.
    driver = driver.replace('esEdicion = true;\ngrupoActual = null;',
                             'esEdicion = false;\ngrupoActual = null;')
    proc = subprocess.run([_NODE, '-e', driver], capture_output=True, text=True, timeout=30)
    assert proc.returncode == 0, (
        f'el driver de Node falló (código {proc.returncode}):\n'
        f'--- stdout ---\n{proc.stdout}\n--- stderr ---\n{proc.stderr}'
    )
    r = json.loads(proc.stdout)

    assert r['claveDeAltaExisteTrasEdicion'] is True, (
        'con esEdicion=false, un alta con líneas activas ya no guarda su '
        'propio borrador — el fix de esta ronda rompió el caso normal'
    )
    assert r['lineasOfrecidasEnPantallaB'] == 1, (
        'la Pantalla B (misma alta, mismo cliente+grupo) ya no recibe la '
        'oferta de su propio borrador — el fix de esta ronda rompió el '
        'caso normal del alta'
    )
