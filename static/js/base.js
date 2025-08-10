// Configuración global para CSRF en AJAX
document.addEventListener('DOMContentLoaded', function() {
    // Configurar CSRF token para todas las peticiones AJAX
    const csrfToken = document.querySelector('meta[name="csrf-token"]')?.getAttribute('content');
    
    if (csrfToken) {
        // Para fetch API
        const originalFetch = window.fetch;
        window.fetch = function(url, options = {}) {
            if (options.method && ['POST', 'PUT', 'DELETE', 'PATCH'].includes(options.method.toUpperCase())) {
                options.headers = {
                    ...options.headers,
                    'X-CSRFToken': csrfToken
                };
            }
            return originalFetch(url, options);
        };
        
        // Para jQuery AJAX (si está disponible)
        if (window.jQuery) {
            $.ajaxSetup({
                beforeSend: function(xhr) {
                    if (['POST', 'PUT', 'DELETE', 'PATCH'].includes(this.type?.toUpperCase())) {
                        xhr.setRequestHeader('X-CSRFToken', csrfToken);
                    }
                }
            });
        }
    }

    // Menú de usuario
    const userMenuToggle = document.getElementById('userMenuToggle');
    const userDropdown = document.getElementById('userDropdown');
    
    if (userMenuToggle && userDropdown) {
        // Toggle del menú
        userMenuToggle.addEventListener('click', function(e) {
            e.stopPropagation();
            userDropdown.classList.toggle('show');
            
            // Añadir efecto de click
            this.classList.add('clicked');
            setTimeout(() => this.classList.remove('clicked'), 200);
        });
        
        // Cerrar menú al hacer click fuera
        document.addEventListener('click', function(e) {
            if (!userMenuToggle.contains(e.target) && !userDropdown.contains(e.target)) {
                userDropdown.classList.remove('show');
            }
        });
        
        // Prevenir que el dropdown se cierre al hacer click dentro
        userDropdown.addEventListener('click', function(e) {
            e.stopPropagation();
        });
    }
    
    // Prevenir zoom en doble tap en iOS
    document.addEventListener('touchend', function(event) {
        if (event.touches.length > 1) {
            event.preventDefault();
        }
    });

    // Añadir efecto de toque activo en móviles
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
