/* Productos — lógica de la pantalla /productos.
   Extraída de static/scripts.js (sección "Manejo de Productos") en la tanda 1
   de la migración del lote oscuro, reescrita en vanilla: base.js ya parchea
   window.fetch con X-CSRFToken y expone window.escapeHtml/window.mostrarMensaje.

   OJO: NO definir window.eliminarProducto — ese nombre global está reservado
   por la convención [data-remove-producto] de base.js (form de pedidos). */
(function () {
    'use strict';

    var form = document.getElementById('form-crear-producto');
    var lista = document.getElementById('lista-productos');
    if (!form || !lista) return; // guarda: solo corre en /productos

    // base.min.js stale (caché CDN/PWA) puede no traer mostrarMensaje aún
    function aviso(msg, tipo) {
        if (window.mostrarMensaje) { window.mostrarMensaje(msg, tipo); }
        else { alert(msg); }
    }

    // Flash diferido (tras crear + reload). OJO: este script se carga en
    // {% block scripts %}, que base.html renderiza ANTES de base.min.js —
    // window.mostrarMensaje aún no existe en parse-time; diferir a
    // DOMContentLoaded (base.min.js es script síncrono y ya habrá cargado).
    var flash = sessionStorage.getItem('gestionFlash');
    if (flash) {
        sessionStorage.removeItem('gestionFlash');
        document.addEventListener('DOMContentLoaded', function () {
            aviso(flash, 'success');
        });
    }

    // Abrir/cerrar el form de crear
    var createCard = document.getElementById('crear-producto-card');
    document.getElementById('btn-nuevo-producto').addEventListener('click', function () {
        var abrir = createCard.hidden;
        createCard.hidden = !abrir;
        if (abrir) document.getElementById('nombre').focus();
    });
    document.getElementById('btn-cancelar-producto').addEventListener('click', function () {
        createCard.hidden = true;
    });

    // Búsqueda client-side (nombre + proveedor, ver data-buscar en el template)
    document.getElementById('buscar-producto').addEventListener('input', function () {
        var q = this.value.trim().toLowerCase();
        lista.querySelectorAll('.gestion-row').forEach(function (row) {
            row.hidden = !!q && row.dataset.buscar.indexOf(q) === -1;
        });
    });

    // Crear producto — el endpoint responde JSON; reload para que la fila la
    // renderice el servidor (única fuente de markup; reemplaza al viejo
    // agregarProductoATabla que insertaba filas desalineadas por JS).
    form.addEventListener('submit', function (e) {
        e.preventDefault();
        var submitBtn = form.querySelector('button[type="submit"]');
        submitBtn.disabled = true; // evita doble submit (doble tap en móvil)
        fetch(form.action, {
            method: 'POST',
            body: new FormData(form),
            headers: { 'X-Requested-With': 'XMLHttpRequest' }
        })
            .then(function (r) {
                return r.json().catch(function () { return { error: 'Error al crear el producto' }; });
            })
            .then(function (res) {
                if (res.error) {
                    submitBtn.disabled = false;
                    aviso(res.error, 'error');
                    return;
                }
                sessionStorage.setItem('gestionFlash', res.message || 'Producto creado');
                window.location.reload();
            })
            .catch(function () {
                submitBtn.disabled = false;
                aviso('Error al crear el producto', 'error');
            });
    });

    // Eliminar producto (delegación scoped a la lista)
    lista.addEventListener('click', function (e) {
        var btn = e.target.closest('.eliminar-producto');
        if (!btn) return;
        if (!confirm('¿Eliminar este producto?')) return;
        fetch('/productos/' + btn.dataset.id + '/eliminar', {
            method: 'POST',
            headers: { 'X-Requested-With': 'XMLHttpRequest' }
        })
            .then(function (r) { return r.json().catch(function () { return {}; }); })
            .then(function (res) {
                // Fail-closed: solo tratar como éxito el JSON con message del
                // endpoint; una respuesta HTML (login/403) cae al error.
                if (res.message) {
                    var row = document.getElementById('producto-' + btn.dataset.id);
                    if (row) row.remove();
                    aviso(res.message, 'success');
                } else {
                    aviso(res.error || 'Error al eliminar el producto.', 'error');
                }
            })
            .catch(function () { aviso('Error al eliminar el producto.', 'error'); });
    });
})();
