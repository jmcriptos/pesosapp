/* signed_decimal.js — Entrada de decimales con signo en teclados móviles.
 *
 * Problema: en iOS, inputmode="decimal" muestra un teclado numérico cuyo
 * separador decimal depende del idioma del dispositivo (coma en español) y que
 * NO incluye tecla de signo menos. Eso impide registrar temperaturas bajo cero
 * y obliga a usar coma en lugar de punto.
 *
 * Para cada <input data-signed-decimal> este script:
 *   1) convierte la coma en punto en vivo (el valor siempre usa punto), y
 *   2) agrega un botón "±" para alternar el signo sin depender del teclado.
 *
 * El backend ya normaliza coma→punto y acepta negativos; esto es la capa de UI.
 */
(function () {
  'use strict';

  function normalize(value) {
    var v = String(value).replace(/,/g, '.');
    var negative = v.indexOf('-') !== -1;
    v = v.replace(/[^0-9.]/g, '');
    var parts = v.split('.');
    if (parts.length > 2) {
      v = parts[0] + '.' + parts.slice(1).join('');
    }
    return (negative ? '-' : '') + v;
  }

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
      var caret = input.selectionStart;
      var before = input.value;
      var after = normalize(before);
      if (after !== before) {
        input.value = after;
        try { input.setSelectionRange(caret, caret); } catch (e) { /* noop */ }
      }
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
