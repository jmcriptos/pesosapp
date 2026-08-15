// Escape global para insertar datos del servidor en HTML sin riesgo de XSS.
window.escapeHtml = function (value) {
    return String(value == null ? '' : value)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');
};

// Flash message global (una sola fuente; antes vivía duplicado en scripts.js
// con jQuery). Requiere un <div id="flash-message" class="flash-message"> en
// el template. tipo: 'success' | cualquier otro valor → estilo error.
window.mostrarMensaje = function (mensaje, tipo) {
    var el = document.getElementById('flash-message');
    if (!el) { alert(mensaje); return; }
    el.className = 'flash-message ' + (tipo === 'success' ? 'success' : 'error');
    el.textContent = mensaje; // textContent evita XSS con datos del servidor
    el.style.display = 'block';
    clearTimeout(el._flashTimer);
    el._flashTimer = setTimeout(function () { el.style.display = 'none'; }, 3000);
};

// Logout por POST (anti CSRF): intercepta cualquier enlace a /logout y lo envía
// como formulario POST con token CSRF.
document.addEventListener('click', function (ev) {
    const link = ev.target.closest('a[href$="/logout"], a[href="/logout"]');
    if (!link) return;
    ev.preventDefault();
    const token = document.querySelector('meta[name="csrf-token"]')?.getAttribute('content');
    const form = document.createElement('form');
    form.method = 'POST';
    form.action = link.getAttribute('href');
    if (token) {
        const input = document.createElement('input');
        input.type = 'hidden';
        input.name = 'csrf_token';
        input.value = token;
        form.appendChild(input);
    }
    document.body.appendChild(form);
    form.submit();
});

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

    // Drawer lateral
    const drawerToggle = document.getElementById('drawerToggle');
    const drawer = document.getElementById('drawer');
    const drawerOverlay = document.getElementById('drawerOverlay');

    if (drawerToggle && drawer && drawerOverlay) {
        drawerToggle.setAttribute('aria-expanded', 'false');

        function openDrawer() {
            drawer.classList.add('open');
            drawerOverlay.classList.add('open');
            drawerToggle.setAttribute('aria-expanded', 'true');
            document.body.style.overflow = 'hidden';
        }
        function closeDrawer() {
            drawer.classList.remove('open');
            drawerOverlay.classList.remove('open');
            drawerToggle.setAttribute('aria-expanded', 'false');
            document.body.style.overflow = '';
        }

        drawerToggle.addEventListener('click', function(e) {
            e.stopPropagation();
            openDrawer();
        });

        drawerOverlay.addEventListener('click', closeDrawer);

        // Cerrar al seleccionar un item
        drawer.querySelectorAll('.drawer-item').forEach(function(item) {
            item.addEventListener('click', closeDrawer);
        });

        // Swipe para cerrar
        let touchStartX = 0;
        drawer.addEventListener('touchstart', function(e) {
            touchStartX = e.touches[0].clientX;
        }, { passive: true });
        drawer.addEventListener('touchend', function(e) {
            const diff = touchStartX - e.changedTouches[0].clientX;
            if (diff > 60) closeDrawer();
        }, { passive: true });

        const drawerDesktopMedia = window.matchMedia('(min-width: 1024px)');
        const syncDrawerState = () => {
            if (drawerDesktopMedia.matches) {
                closeDrawer();
            }
        };

        if (typeof drawerDesktopMedia.addEventListener === 'function') {
            drawerDesktopMedia.addEventListener('change', syncDrawerState);
        } else if (typeof drawerDesktopMedia.addListener === 'function') {
            drawerDesktopMedia.addListener(syncDrawerState);
        }
    }

    function bindDesktopDropdown(toggleId, dropdownId) {
        const toggle = document.getElementById(toggleId);
        const dropdown = document.getElementById(dropdownId);

        if (!toggle || !dropdown) {
            return;
        }

        const closeDropdown = () => {
            dropdown.classList.remove('show');
            toggle.setAttribute('aria-expanded', 'false');
        };

        toggle.setAttribute('aria-expanded', 'false');

        toggle.addEventListener('click', function(e) {
            e.stopPropagation();

            document.querySelectorAll('.desktop-ops-dropdown.show, .user-dropdown.show').forEach(function(menu) {
                if (menu !== dropdown) {
                    menu.classList.remove('show');
                }
            });
            document.querySelectorAll('#desktopOpsToggle, #userMenuToggle').forEach(function(button) {
                if (button !== toggle) {
                    button.setAttribute('aria-expanded', 'false');
                }
            });

            const isOpen = dropdown.classList.toggle('show');
            toggle.setAttribute('aria-expanded', String(isOpen));

            if (toggleId === 'userMenuToggle') {
                toggle.classList.add('clicked');
                setTimeout(() => toggle.classList.remove('clicked'), 200);
            }
        });

        document.addEventListener('click', function(e) {
            if (!toggle.contains(e.target) && !dropdown.contains(e.target)) {
                closeDropdown();
            }
        });

        dropdown.addEventListener('click', function(e) {
            e.stopPropagation();
        });

        dropdown.querySelectorAll('a').forEach(function(link) {
            link.addEventListener('click', closeDropdown);
        });

        document.addEventListener('keydown', function(e) {
            if (e.key === 'Escape') {
                closeDropdown();
            }
        });

        const desktopDropdownMedia = window.matchMedia('(max-width: 1023px)');
        const syncDropdownState = () => {
            if (desktopDropdownMedia.matches) {
                closeDropdown();
            }
        };

        if (typeof desktopDropdownMedia.addEventListener === 'function') {
            desktopDropdownMedia.addEventListener('change', syncDropdownState);
        } else if (typeof desktopDropdownMedia.addListener === 'function') {
            desktopDropdownMedia.addListener(syncDropdownState);
        }
    }

    bindDesktopDropdown('desktopOpsToggle', 'desktopOpsDropdown');
    bindDesktopDropdown('userMenuToggle', 'userDropdown');
    
    // Prevenir zoom en doble tap en iOS
    document.addEventListener('touchend', function(event) {
        if (event.touches && event.touches.length > 1) {
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

    // CSP-safe: auto-submit del formulario al cambiar (reemplaza onchange="this.form.submit()")
    document.addEventListener('change', function(e) {
        const el = e.target.closest('[data-autosubmit]');
        if (el && el.form) {
            el.form.submit();
        }
    });

    // CSP-safe: detener propagación de click (reemplaza onclick="event.stopPropagation()")
    document.querySelectorAll('[data-stop-propagation]').forEach(function(el) {
        el.addEventListener('click', function(ev) { ev.stopPropagation(); });
    });

    // CSP-safe: acciones de click vía data-* (reemplazan onclick="fn()") delegadas en document
    document.addEventListener('click', function(e) {
        if (e.target.closest('[data-drawer-open]')) {
            e.preventDefault();
            document.getElementById('drawerToggle')?.click();
            return;
        }
        if (e.target.closest('[data-edit-close]') && typeof window.closeEditModal === 'function') {
            window.closeEditModal();
            return;
        }
        if (e.target.closest('[data-etiquetas-toggle]') && typeof window.toggleEtiquetas === 'function') {
            window.toggleEtiquetas();
            return;
        }
        const rmProd = e.target.closest('[data-remove-producto]');
        if (rmProd && typeof window.eliminarProducto === 'function') {
            window.eliminarProducto(Number(rmProd.dataset.removeProducto));
        }
    });

    // Factura PDF: Web Share API en el PWA de iOS (una descarga normal no
    // funciona en standalone), con enlace de descarga como fallback.
    document.addEventListener('click', async function (e) {
        const btn = e.target.closest('[data-factura-share]');
        if (!btn) return;

        const url = btn.dataset.facturaUrl;
        const nombre = btn.dataset.facturaNombre || 'Factura.pdf';
        const original = btn.innerHTML;
        btn.disabled = true;
        btn.textContent = 'Generando...';

        try {
            const resp = await fetch(url, { credentials: 'same-origin' });
            if (!resp.ok) throw new Error('HTTP ' + resp.status);
            const blob = await resp.blob();
            const file = new File([blob], nombre, { type: 'application/pdf' });

            if (navigator.canShare && navigator.canShare({ files: [file] })) {
                await navigator.share({ files: [file], title: nombre });
            } else {
                const objectUrl = URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = objectUrl;
                a.download = nombre;
                document.body.appendChild(a);
                a.click();
                a.remove();
                setTimeout(() => URL.revokeObjectURL(objectUrl), 10000);
            }
        } catch (err) {
            if (err && err.name === 'AbortError') return;  // el usuario canceló
            alert('No se pudo generar la factura. Intente de nuevo.');
        } finally {
            btn.disabled = false;
            btn.innerHTML = original;
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
        // Solo adjuntar el token CSRF a métodos no seguros y a URLs del mismo origen,
        // para no filtrar el token a servicios externos.
        const method = ((init && init.method) || (input && input.method) || 'GET').toUpperCase();
        let sameOrigin = true;
        try {
            const url = new URL((input && input.url) || input, window.location.href);
            sameOrigin = (url.origin === window.location.origin);
        } catch (e) {
            sameOrigin = true; // rutas relativas → mismo origen
        }
        if (['POST', 'PUT', 'PATCH', 'DELETE'].includes(method) && sameOrigin) {
            init.headers = init.headers || {};
            if (init.headers instanceof Headers) {
                if (!init.headers.has('X-CSRFToken') && !init.headers.has('X-CSRF-Token')) {
                    init.headers.set('X-CSRFToken', token);
                }
            } else if (!init.headers['X-CSRFToken'] && !init.headers['X-CSRF-Token']) {
                init.headers['X-CSRFToken'] = token;
            }
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
