/* static/js/pedido_totales.js
 *
 * Aritmética PURA del desglose Subtotal / OB / Total de la revisión del
 * form de pedidos (paso 04, `templates/pedido_form.html`). Extraída de
 * `pintarTotales()` en ese archivo para poder ejercitarla desde Node, sin
 * navegador ni harness de JS en la suite — `pintarTotales()` sigue viviendo
 * en el template y ahora es solo el "controlador" que le pasa los tres
 * insumos (subtotal, código de grupo, flag de exportación) a
 * `calcularTotalesPedido()` de acá y escribe el resultado en el DOM.
 *
 * NUNCA es el payload que se le manda a QuickBooks — ese sigue viajando tal
 * cual en los hidden de cada línea (ver `pedido_a_json` en app.py).
 * `precio_base` se guarda tax-exclusive: el OB se lo suma QuickBooks al
 * facturar, así que "Total" acá tiene que sumarlo también o miente.
 *
 * Un código nuevo entra en `_OB_POR_CODIGO` (app.py), nunca acá — el mapa
 * que este archivo consume viaja del servidor (`const OB_POR_CODIGO` en el
 * template), es el mismo diccionario, no una copia.
 *
 * UMD mínimo: `require('./pedido_totales.js')` en Node (pruebas) y
 * `<script src="...">` en el navegador (`window.calcularTotalesPedido`,
 * carga same-origin — pasa 'self' en script-src sin necesitar nonce).
 */
(function (root, factory) {
    if (typeof module === 'object' && module.exports) {
        module.exports = factory();
    } else {
        root.calcularTotalesPedido = factory();
    }
}(typeof self !== 'undefined' ? self : this, function () {
    'use strict';

    /**
     * @param {number} subtotal - suma de precio*cajas de las líneas activas.
     * @param {Object} opciones
     * @param {boolean} opciones.esExportacion - `_es_exportacion` del cliente
     *   (manda sobre el grupo: un cliente USD sale exento sea cual sea la
     *   mercadería, mismo criterio que `_tax_code_de_linea` en el payload).
     * @param {?number} opciones.codigo - código de QBO del grupo fijado del
     *   pedido en curso (10, 14…), o null si no hay grupo todavía.
     * @param {Object} opciones.obPorCodigo - mapa código -> % de OB (mismo
     *   `_OB_POR_CODIGO` de app.py, viaja al template como `OB_POR_CODIGO`).
     * @returns {{filaObHidden: boolean, filaTotalHidden: boolean,
     *   notaHidden: boolean, nota: ?string, obLabel: ?string,
     *   obMonto: ?number, total: ?number}}
     */
    function calcularTotalesPedido(subtotal, opciones) {
        opciones = opciones || {};
        const esExportacion = !!opciones.esExportacion;
        const codigo = (opciones.codigo === undefined) ? null : opciones.codigo;
        const obPorCodigo = opciones.obPorCodigo || {};

        if (esExportacion) {
            // La exportación manda sobre el grupo: un cliente en USD se
            // factura exento sea cual sea la mercadería. No es que el grupo
            // no pague OB — es que la venta es exportación — así que se dice
            // explícito y no se confunde con un grupo que de por sí es 0%.
            return {
                filaObHidden: true,
                filaTotalHidden: false,
                notaHidden: false,
                nota: 'Exportación · exenta de OB. El total es el subtotal.',
                obLabel: null,
                obMonto: null,
                total: subtotal,
            };
        }

        const pct = (codigo === null) ? undefined : obPorCodigo[codigo];

        if (pct === undefined || pct === null) {
            // Código sin traducir: no se inventa un total que la factura
            // después desmiente. Solo el subtotal, y un aviso de que falta
            // el impuesto.
            return {
                filaObHidden: true,
                filaTotalHidden: true,
                notaHidden: false,
                nota: 'La factura suma el impuesto de este grupo; este subtotal no lo incluye.',
                obLabel: null,
                obMonto: null,
                total: null,
            };
        }

        if (pct === 0) {
            // «OB 0% — 0.00» es ruido: el grupo no paga impuesto, así que el
            // total inclusivo es el subtotal y no hay nada que desglosar.
            return {
                filaObHidden: true,
                filaTotalHidden: false,
                notaHidden: true,
                nota: null,
                obLabel: null,
                obMonto: null,
                total: subtotal,
            };
        }

        const ob = subtotal * pct / 100;
        return {
            filaObHidden: false,
            filaTotalHidden: false,
            notaHidden: true,
            nota: null,
            obLabel: 'OB ' + pct + '%',
            obMonto: ob,
            total: subtotal + ob,
        };
    }

    return calcularTotalesPedido;
}));
