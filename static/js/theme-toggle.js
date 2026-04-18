/*
 * Theme toggle — reads saved theme from localStorage, applies to body.dataset.theme,
 * wires up any [data-theme-toggle] button to flip and persist.
 * Loaded near the top of <body> (not deferred) so the saved theme is applied
 * before the first paint and there is no flash from the default to the saved value.
 */
(function () {
  var KEY = 'pesos_theme';
  var root = document.body;
  if (!root) return;

  try {
    var saved = localStorage.getItem(KEY);
    if (saved === 'light' || saved === 'dark') {
      root.dataset.theme = saved;
    }
  } catch (e) { /* localStorage blocked — silent */ }

  function sync(current) {
    var buttons = document.querySelectorAll('[data-theme-toggle]');
    for (var i = 0; i < buttons.length; i++) {
      buttons[i].setAttribute('aria-pressed', String(current === 'dark'));
    }
  }

  document.addEventListener('click', function (ev) {
    var btn = ev.target.closest && ev.target.closest('[data-theme-toggle]');
    if (!btn) return;
    var next = root.dataset.theme === 'dark' ? 'light' : 'dark';
    root.dataset.theme = next;
    try { localStorage.setItem(KEY, next); } catch (e) {}
    sync(next);
  });

  sync(root.dataset.theme || 'dark');
})();
