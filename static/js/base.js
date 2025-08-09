document.addEventListener('DOMContentLoaded', function() {
  // Menú de usuario
  const userMenuToggle = document.getElementById('userMenuToggle');
  const userDropdown = document.getElementById('userDropdown');

  if (userMenuToggle && userDropdown) {
    userMenuToggle.addEventListener('click', function(e) {
      e.stopPropagation();
      userDropdown.classList.toggle('show');
      this.classList.add('clicked');
      setTimeout(() => this.classList.remove('clicked'), 200);
    });

    document.addEventListener('click', function(e) {
      if (!userMenuToggle.contains(e.target) && !userDropdown.contains(e.target)) {
        userDropdown.classList.remove('show');
      }
    });

    userDropdown.addEventListener('click', function(e) {
      e.stopPropagation();
    });
  }

  // Prevenir zoom en doble tap en iOS
  document.addEventListener('touchend', function(event) {
    if (event.touches && event.touches.length > 1) {
      event.preventDefault();
    }
  });

  // Efecto de toque activo en móviles
  const navItems = document.querySelectorAll('.nav-item');
  navItems.forEach(item => {
    item.addEventListener('touchstart', function() {
      this.style.transform = 'scale(0.95)';
    });
    item.addEventListener('touchend', function() {
      this.style.transform = 'scale(1)';
    });
  });

  // Auto-cerrar alertas después de 5 segundos
  const alerts = document.querySelectorAll('.alert');
  alerts.forEach(alert => {
    setTimeout(() => {
      alert.style.opacity = '0';
      setTimeout(() => alert.remove(), 300);
    }, 5000);
  });
});

// Helper para enviar CSRF en fetch por defecto
(() => {
  const meta = document.querySelector('meta[name="csrf-token"]');
  const token = meta ? meta.getAttribute('content') : null;
  if (!token) return;

  const originalFetch = window.fetch;
  window.fetch = function(input, init = {}) {
    init.headers = init.headers || {};
    // No sobrescribir si ya fue seteado
    if (!init.headers['X-CSRFToken'] && !init.headers['X-CSRF-Token']) {
      init.headers['X-CSRFToken'] = token;
    }
    return originalFetch(input, init);
  };

  // Soporte para jQuery si está presente
  if (window.$ && typeof window.$.ajaxSetup === 'function') {
    window.$.ajaxSetup({
      beforeSend: function(xhr, settings) {
        // Solo métodos no seguros
        const method = (settings && settings.type) ? settings.type.toUpperCase() : 'GET';
        if (['POST', 'PUT', 'PATCH', 'DELETE'].includes(method)) {
          xhr.setRequestHeader('X-CSRFToken', token);
        }
      }
    });
  }
})();


