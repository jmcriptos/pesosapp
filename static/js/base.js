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

  // US01: Event delegation para reemplazar todos los inline event handlers
  // Click events
  document.addEventListener('click', function(e) {
    const el = e.target.closest('[data-action]');
    if (!el) return;
    
    const action = el.dataset.action;
    const id = el.dataset.id;
    const idx = el.dataset.idx;
    const enabled = el.dataset.enabled;
    
    switch (action) {
      case 'eliminar-precio':
        if (typeof eliminarPrecio === 'function') {
          eliminarPrecio(id);
        }
        break;
      case 'eliminar-producto':
        if (typeof eliminarProducto === 'function') {
          eliminarProducto(idx);
        }
        break;
      case 'toggle-vendedor':
        if (typeof toggleVendedor === 'function') {
          toggleVendedor(id, enabled === 'true');
        }
        break;
      case 'editar-precio':
        if (typeof editarPrecio === 'function') {
          const productoId = el.dataset.productoId;
          const precioBase = el.dataset.precioBase;
          const margenJomar = el.dataset.margenJomar;
          const margenRetail = el.dataset.margenRetail;
          editarPrecio(id, productoId, precioBase, margenJomar, margenRetail);
        }
        break;
      case 'editar-vendedor':
        if (typeof editarVendedor === 'function') {
          editarVendedor(id);
        }
        break;
      case 'desasignar':
        if (typeof desasignar === 'function') {
          desasignar(id);
        }
        break;
      case 'mostrar-consultor-precios':
        if (typeof mostrarConsultorPrecios === 'function') {
          mostrarConsultorPrecios();
        }
        break;
      case 'cerrar-consultor-precios':
        if (typeof cerrarConsultorPrecios === 'function') {
          cerrarConsultorPrecios();
        }
        break;
      case 'imprimir-etiqueta':
        if (typeof imprimirEtiqueta === 'function') {
          imprimirEtiqueta(id);
        }
        break;
      case 'descargar-etiqueta':
        if (typeof descargarEtiqueta === 'function') {
          descargarEtiqueta(id);
        }
        break;
      case 'export-csv':
        alert('Funcionalidad próximamente');
        break;
      case 'export-excel':
        alert('Funcionalidad próximamente');
        break;
      case 'export-pdf':
        alert('Funcionalidad próximamente');
        break;
    }
  });

  // Form submit events with confirmation
  document.addEventListener('submit', function(e) {
    const form = e.target.closest('form[data-confirm]');
    if (form) {
      const message = form.dataset.confirm;
      if (!confirm(message)) {
        e.preventDefault();
        return false;
      }
    }
  });

  // US01: Helper para calcular clases de porcentaje para gauges
  window.calculateGaugeClasses = function(percentage, maxValue) {
    if (maxValue === 0) return { width: 'w-pct-0', needle: 'needle-0' };
    
    const pct = Math.min(100, Math.max(0, (percentage / maxValue) * 100));
    const widthClass = `w-pct-${Math.round(pct / 5) * 5}`;
    const needleClass = `needle-${Math.round((pct / 100) * 180 / 5) * 5}`;
    
    return { width: widthClass, needle: needleClass };
  };
});

// US01: Helper para enviar CSRF en fetch/AJAX por defecto
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


