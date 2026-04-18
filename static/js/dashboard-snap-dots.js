/* Dashboard snap-dots indicator.
   Spec: docs/superpowers/specs/2026-04-18-dashboard-snap-layout-design.md

   For each .snap-dots[data-snap-dots-for="<panel>"] container:
   - Find the matching .dash-panel[data-dash-panel="<panel>"]
   - Create one <span> per [data-snap-card] inside that panel
   - Use IntersectionObserver to mark the most-visible card's dot as
     .is-current
   - Toggle the container's .is-active by reading which #dash-tabs
     button.active matches its data-snap-dots-for attribute.
*/
(function () {
  'use strict';

  function initSnapDots(container) {
    var panelKey = container.dataset.snapDotsFor;
    if (!panelKey) return;
    var panel = document.querySelector(
      '.dash-panel[data-dash-panel="' + panelKey + '"]'
    );
    if (!panel) return;
    var cards = panel.querySelectorAll('[data-snap-card]');
    if (!cards.length) return;

    container.innerHTML = '';
    var dots = [];
    cards.forEach(function () {
      var dot = document.createElement('span');
      container.appendChild(dot);
      dots.push(dot);
    });

    var observer = new IntersectionObserver(
      function (entries) {
        entries.forEach(function (entry) {
          if (!entry.isIntersecting) return;
          var idx = Array.prototype.indexOf.call(cards, entry.target);
          if (idx < 0) return;
          dots.forEach(function (d, i) {
            d.classList.toggle('is-current', i === idx);
          });
        });
      },
      { root: panel, threshold: 0.6 }
    );
    cards.forEach(function (card) { observer.observe(card); });
  }

  function updateActiveDots() {
    document.querySelectorAll('.snap-dots').forEach(function (container) {
      var panelKey = container.dataset.snapDotsFor;
      var activeBtn = document.querySelector(
        '#dash-tabs button.active[data-panel="' + panelKey + '"]'
      );
      container.classList.toggle('is-active', !!activeBtn);
    });
  }

  document.addEventListener('DOMContentLoaded', function () {
    document.querySelectorAll('.snap-dots').forEach(initSnapDots);
    updateActiveDots();

    // The existing tab JS toggles .active on #dash-tabs button. Listen for
    // clicks to refresh which dot column is shown.
    var tabs = document.getElementById('dash-tabs');
    if (tabs) tabs.addEventListener('click', function () {
      // Defer one frame so the existing tab JS finishes updating .active.
      window.requestAnimationFrame(updateActiveDots);
    });
  });
})();
