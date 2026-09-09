/* signed_decimal.js — Decimales tecleados en un teclado móvil.
 *
 * Dos problemas, el mismo campo:
 *   1) el teclado numérico de iOS trae el separador decimal del idioma del
 *      dispositivo (coma en español) y no trae tecla de menos;
 *   2) un <input type="number"> DESCARTA la coma sin avisar — medido en el
 *      navegador: teclear «12,5» deja el campo en «125». No es que «no deje
 *      poner la coma»: es una caja de 12,5 kg registrada como 125 kg.
 *
 * Por eso los campos decimales de la app son type="text" + inputmode="decimal"
 * y se normalizan acá, en vivo, para que el operario vea el punto mientras
 * teclea. Dos marcas:
 *
 *   data-decimal          → coma→punto (pesos y cantidades: nunca negativos)
 *   data-signed-decimal   → coma→punto + botón «±» para poner el signo sin
 *                           depender del teclado, que en el teléfono no trae
 *                           «−» (el CSS del botón está en operaciones.css)
 *
 * El backend ya normaliza coma→punto y acepta negativos; esto es la capa de UI.
 */
(function () {
  'use strict';

  function normalize(value, conSigno) {
    var v = String(value).replace(/,/g, '.');
    var negative = conSigno && v.indexOf('-') !== -1;
    v = v.replace(/[^0-9.]/g, '');
    var parts = v.split('.');
    if (parts.length > 2) {
      v = parts[0] + '.' + parts.slice(1).join('');
    }
    return (negative ? '-' : '') + v;
  }

  function limpiar(input, conSigno) {
    var caret = input.selectionStart;
    var before = input.value;
    var after = normalize(before, conSigno);
    if (after === before) return;
    input.value = after;
    try { input.setSelectionRange(caret, caret); } catch (e) { /* noop */ }
  }

  // `data-decimal` se atiende por DELEGACIÓN, no con un listener por campo:
  // las líneas de una recepción se clonan de un <template> después de que este
  // script corrió, y un listener por elemento no alcanzaría a las nuevas.
  document.addEventListener('input', function (e) {
    var input = e.target;
    if (!input || !input.matches || !input.matches('input[data-decimal]')) return;
    limpiar(input, false);
  });

  function reflect(input, btn) {
    btn.classList.toggle('is-negative', input.value.charAt(0) === '-');
  }

  function enhance(input) {
    if (input.dataset.signedDecimalReady) return;
    input.dataset.signedDecimalReady = '1';

    var wrap = document.createElement('div');
    wrap.className = 'signed-decimal-wrap';
    input.parentNode.insertBefore(wrap, input);
    wrap.appendChild(input);

    var btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'signo-toggle';
    btn.textContent = '±'; // ±
    btn.title = 'Cambiar signo (+/−). Útil para bajo cero.';
    btn.setAttribute('aria-label', 'Cambiar el signo del valor, positivo o negativo');
    wrap.appendChild(btn);

    input.addEventListener('input', function () {
      limpiar(input, true);
      reflect(input, btn);
    });

    btn.addEventListener('click', function () {
      var v = input.value;
      input.value = (v.charAt(0) === '-') ? v.slice(1) : ('-' + v);
      reflect(input, btn);
      input.focus();
    });

    reflect(input, btn);
  }

  function init() {
    var inputs = document.querySelectorAll('input[data-signed-decimal]');
    Array.prototype.forEach.call(inputs, enhance);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
