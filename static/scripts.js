$(document).ready(function() {
    console.log("scripts.js cargado correctamente");

    /*** Variables Globales ***/
    let productIndex = 0;

    /*** Funciones ***/

    // Escapa texto para insertarlo de forma segura en HTML (previene XSS
    // almacenado al construir filas de tabla con datos del servidor).
    function escapeHtml(value) {
        return String(value == null ? '' : value)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#39;');
    }

    // Función para mostrar mensajes flash
    function mostrarMensaje(mensaje, tipo) {
        let flashMessage = $('#flash-message');
        flashMessage.removeClass(); // Remover clases anteriores
        flashMessage.addClass('flash-message'); // Clase base
        if (tipo === 'success') {
            flashMessage.addClass('success');
        } else if (tipo === 'error') {
            flashMessage.addClass('error');
        }
        flashMessage.html(mensaje);
        flashMessage.fadeIn(500).delay(3000).fadeOut(500);
    }

    // Función para cargar los productos en un select específico
    function cargarProductos(selectElement) {
        $.ajax({
            url: '/api/productos',
            method: 'GET',
            success: function(data) {
                console.log("Productos recibidos del servidor:", data);
                selectElement.empty();
                selectElement.append('<option value="">Seleccionar Producto</option>');
                if (data && Array.isArray(data) && data.length > 0) {
                    data.forEach(function(producto) {
                        let option = new Option(producto.nombre, producto.id);
                        selectElement.append(option);
                    });
                } else {
                    selectElement.append(new Option("No hay productos disponibles", ""));
                }
            },
            error: function(jqXHR, textStatus, errorThrown) {
                console.error('Error al cargar los productos:', textStatus, errorThrown);
                alert(`Error al cargar los productos: ${textStatus}`);
            }
        });
    }

    /*** Manejo de Recepciones ***/

    // Función para cargar las recepciones desde la base de datos
    function cargarRecepciones() {
        $.ajax({
            url: '/api/recepciones',
            method: 'GET',
            success: function(data) {
                let tbody = $('#recepciones-table-body');
                tbody.empty();

                if (data && Array.isArray(data) && data.length > 0) {
                    data.forEach(function(recepcion) {
                        let row = `
                            <tr id="recepcion-${recepcion.id}">
                                <td>${recepcion.id}</td>
                                <td>${escapeHtml(recepcion.producto)}</td>
                                <td>${escapeHtml(recepcion.peso)}</td>
                                <td>${escapeHtml(recepcion.recibido_en)}</td>
                                <td>${escapeHtml(recepcion.proveedor)}</td>
                                <td>${escapeHtml(recepcion.numero_factura)}</td>
                                <td><button class="eliminar-recepcion btn btn-danger" data-id="${recepcion.id}">Eliminar</button></td>
                            </tr>`;
                        tbody.append(row);
                    });

                    // Asignar el evento para eliminar recepciones después de recargar la tabla
                    $('.eliminar-recepcion').off('click').on('click', function() {
                        let recepcionId = $(this).data('id');
                        let row = $(this).closest('tr');
                        eliminarRecepcion(recepcionId, row);
                    });

                } else {
                    tbody.append('<tr><td colspan="7">No hay recepciones registradas</td></tr>');
                }
            },
            error: function(jqXHR, textStatus, errorThrown) {
                alert(`Error al cargar las recepciones: ${textStatus}`);
            }
        });
    }

    // Función para eliminar una recepción
    function eliminarRecepcion(id, row) {
        if (confirm("¿Estás seguro de que quieres eliminar esta recepción?")) {
            $.ajax({
                url: `/recepciones/${id}`,
                type: 'DELETE',
                dataType: 'json',
                success: function(response) {
                    if (response.message) {
                        mostrarMensaje(response.message, 'success');
                    }

                    // Eliminar la fila de la tabla
                    row.remove();
                },
                error: function(xhr, status, error) {
                    console.error('Error al eliminar la recepción:', error);
                    let errorMessage = 'Error al eliminar la recepción.';
                    if (xhr.responseJSON && xhr.responseJSON.error) {
                        errorMessage = xhr.responseJSON.error;
                    }
                    mostrarMensaje(errorMessage, 'error');
                }
            });
        }
    }

    // Función para registrar una nueva recepción
    $('#form-recepcion').off('submit').on('submit', function(e) {
        e.preventDefault();

        let formData = $(this).serialize();

        $.ajax({
            url: '/recepciones',
            method: 'POST',
            data: formData,
            dataType: 'json',
            success: function(response) {
                if (response.message) {
                    mostrarMensaje(response.message, 'success');
                }

                if (response.recepcion) {
                    let recepcion = response.recepcion;
                    let nuevaFila = `
                        <tr id="recepcion-${recepcion.id}">
                            <td>${recepcion.id}</td>
                            <td>${escapeHtml(recepcion.producto)}</td>
                            <td>${escapeHtml(recepcion.peso)}</td>
                            <td>${escapeHtml(recepcion.recibido_en)}</td>
                            <td>${escapeHtml(recepcion.proveedor)}</td>
                            <td>${escapeHtml(recepcion.numero_factura)}</td>
                            <td><button class="eliminar-recepcion btn btn-danger" data-id="${recepcion.id}">Eliminar</button></td>
                        </tr>
                    `;
                    $('#recepciones-table-body').prepend(nuevaFila);

                    // Asignar el evento de eliminar al nuevo botón
                    $(`#recepcion-${recepcion.id} .eliminar-recepcion`).click(function(event) {
                        event.preventDefault();
                        eliminarRecepcion($(this).data('id'), $(this).closest('tr'));
                    });

                    // Prellenar el formulario con los datos del último registro, exceptuando el peso
                    preRellenarFormulario(recepcion);
                }

                // Limpiar el campo de peso
                $('#peso').val('');
            },
            error: function(xhr, status, error) {
                console.error('Error al registrar la recepción:', status, error);
                let errorMessage = 'Error al registrar la recepción.';
                if (xhr.responseJSON && xhr.responseJSON.error) {
                    errorMessage = xhr.responseJSON.error;
                }
                mostrarMensaje(errorMessage, 'error');
            }
        });
    });

    // Función para prellenar el formulario con los datos del último registro (excepto el campo de peso)
    function preRellenarFormulario(recepcion) {
        if (recepcion) {
            $('#producto_id').val(recepcion.producto_id);
            $('#proveedor').val(recepcion.proveedor);
            $('#numero_factura').val(recepcion.numero_factura);
            $('#fecha_recepcion').val(recepcion.recibido_en);
        }
    }

    /*** Manejo de Productos ***/

    // Manejar el envío del formulario para crear un producto
    document.getElementById('form-crear-producto').addEventListener('submit', function(e) {
        e.preventDefault();

        const form = e.target;
        const data = new FormData(form);

        fetch(form.action, {
            method: 'POST',
            body: data,
            headers: {
                'X-Requested-With': 'XMLHttpRequest'
            }
        })
        .then(res => res.json().catch(() => ({ error: 'Error al crear el producto' })))
        .then(data => {
            if (data.error) {
                mostrarMensaje(data.error, 'danger');
            } else {
                agregarProductoATabla(data.producto);
                form.reset();
                mostrarMensaje(data.message || 'Producto creado', 'success');
            }
        })
        .catch(err => {
            console.error(err);
            mostrarMensaje('Error al crear el producto', 'danger');
        });
    });


    // Asignar eventos de eliminar a los botones existentes y futuros
    $(document).on('click', '.eliminar-producto', function(event) {
        event.preventDefault();
        console.log('Botón eliminar producto clicado');
        eliminarProducto($(this).data('id'), $(this).closest('tr'));
    });

    // Función para eliminar producto
    function eliminarProducto(productoId, row) {
        console.log('Función eliminarProducto llamada con id:', productoId);
        if (confirm('¿Estás seguro de que deseas eliminar este producto?')) {
            $.ajax({
                url: `/productos/${productoId}/eliminar`,
                type: 'POST',
                dataType: 'json',
                data: {
                    accion: 'eliminar'
                },
                success: function(response) {
                    console.log('Respuesta del servidor:', response);
                    if (response.message) {
                        mostrarMensaje(response.message, 'success');
                    } else if (response.error) {
                        mostrarMensaje(response.error, 'error');
                    }

                    // Eliminar la fila de la tabla
                    row.remove();
                },
                error: function(xhr, status, error) {
                    console.error('Error al eliminar el producto:', error);
                    console.error('Estado:', status);
                    console.error('Respuesta del servidor:', xhr.responseText);
                    mostrarMensaje('Error al eliminar el producto.', 'error');
                }
            });
        }
    }

    /*** Manejo de Clientes ***/

    // Manejar el envío del formulario para crear un cliente
    $('#form-cliente').submit(function(event) {
        event.preventDefault();

        var formData = $(this).serialize();

        $.ajax({
            type: 'POST',
            url: '/clientes/nuevo',
            data: formData,
            dataType: 'json',
            success: function(response) {
                console.log("Respuesta del servidor:", response);

                if (response.message) {
                    mostrarMensaje(response.message, 'success');
                }

                if (response.cliente) {
                    // Agregar el nuevo cliente a la tabla
                    let cliente = response.cliente;
                    let nuevaFila = `
                        <tr id="cliente-${cliente.id}">
                            <td>${cliente.id}</td>
                            <td>${escapeHtml(cliente.nombre)}</td>
                            <td>
                                <button class="eliminar-cliente btn btn-danger" data-id="${cliente.id}">Eliminar</button>
                            </td>
                        </tr>
                    `;
                    $('table tbody').append(nuevaFila);
                }

                // Limpiar el formulario
                $('#form-cliente')[0].reset();
            },
            error: function(xhr, status, error) {
                console.error('Error al crear el cliente:', error);
                mostrarMensaje('Error al crear el cliente.', 'error');
            }
        });
    });

    // Función para eliminar un cliente
    function eliminarCliente(clienteId, row) {
        if (confirm('¿Estás seguro de que deseas eliminar este cliente?')) {
            $.ajax({
                url: `/clientes/${clienteId}`,
                type: 'DELETE',
                dataType: 'json',
                success: function(response) {
                    if (response.message) {
                        mostrarMensaje(response.message, 'success');
                    } else if (response.error) {
                        mostrarMensaje(response.error, 'error');
                    }

                    // Eliminar la fila de la tabla
                    row.remove();
                },
                error: function(xhr, status, error) {
                    console.error('Error al eliminar el cliente:', error);
                    mostrarMensaje('Error al eliminar el cliente.', 'error');
                }
            });
        }
    }

    // Asignar eventos de eliminar a los botones existentes
    $(document).on('click', '.eliminar-cliente', function(event) {
        event.preventDefault();
        eliminarCliente($(this).data('id'), $(this).closest('tr'));
    });

    /*** Manejo de Facturación ***/

    function cargarFacturaciones(clienteId) {
        $.ajax({
            url: '/ultimos_facturaciones',
            method: 'GET',
            data: { cliente_id: clienteId },
            success: function(data) {
                let tbody = $('#ultimas-facturaciones-table-body');
                tbody.empty();

                if (data.length > 0) {
                    data.forEach(function(facturacion) {
                        let row = `
                            <tr id="facturacion-${facturacion.id}">
                                <td>${facturacion.id}</td>
                                <td>${escapeHtml(facturacion.producto)}</td>
                                <td>${escapeHtml(facturacion.peso)}</td>
                                <td>${escapeHtml(facturacion.cliente)}</td>
                                <td>${escapeHtml(facturacion.lote)}</td>
                                <td>${escapeHtml(facturacion.fecha_fabricacion)}</td>
                                <td>${escapeHtml(facturacion.fecha_expiracion)}</td>
                                <td>${escapeHtml(facturacion.fecha_registro)}</td>
                                <td>
                                    <i class="fas fa-trash-alt eliminar-facturacion" data-id="${facturacion.id}"></i>
                                </td>
                            </tr>`;
                        tbody.append(row);
                    });
                } else {
                    tbody.append('<tr><td colspan="9">No hay facturaciones para este cliente hoy.</td></tr>');
                }
            },
            error: function(jqXHR, textStatus, errorThrown) {
                console.error('Error al cargar las facturaciones:', textStatus, errorThrown);
                alert('Error al cargar las facturaciones');
            }
        });
    }

    // Función para eliminar facturaciones
    $(document).on('click', '.eliminar-facturacion', function() {
        let facturacionId = $(this).data('id');

        if (confirm("¿Estás seguro de que quieres eliminar este peso?")) {
            $.ajax({
                url: `/facturacion/eliminar/${facturacionId}`,
                method: 'DELETE',
                dataType: 'json',
                success: function(response) {
                    if (response.message) {
                        mostrarMensaje(response.message, 'success');
                    }
                    $(`#facturacion-${facturacionId}`).remove();
                },
                error: function(xhr, status, error) {
                    console.error('Error al eliminar el peso:', error);
                    let errorMessage = 'Error al eliminar el peso.';
                    if (xhr.responseJSON && xhr.responseJSON.error) {
                        errorMessage = xhr.responseJSON.error;
                    }
                    mostrarMensaje(errorMessage, 'error');
                }
            });
        }
    });

    // Registrar facturación
    $('#form-facturacion').off('submit').on('submit', function(e) {
        e.preventDefault();
        let formData = $(this).serialize();
        let clienteId = $('#cliente-facturacion').val();

        $.ajax({
            url: '/facturacion/registrar',
            method: 'POST',
            data: formData,
            dataType: 'json',
            success: function(response) {
                console.log("Respuesta del servidor:", response);

                if (response.message) {
                    mostrarMensaje(response.message, 'success');
                }

                $('#peso-facturacion').val('');
                cargarFacturaciones(clienteId);
            },
            error: function(xhr, status, error) {
                console.error('Error al registrar el peso:', error);
                let errorMessage = 'Error al registrar el peso.';
                if (xhr.responseJSON && xhr.responseJSON.error) {
                    errorMessage = xhr.responseJSON.error;
                }
                mostrarMensaje(errorMessage, 'error');
            }
        });
    });

    // Actualizar la fecha de expiración automáticamente
    function actualizarFechaExpiracion() {
        let fechaFabricacionValor = $('#fecha-fabricacion-facturacion').val();
        console.log("Valor de fecha de fabricación:", fechaFabricacionValor);

        if (fechaFabricacionValor) {
            let fechaFabricacion = new Date(fechaFabricacionValor);
            if (!isNaN(fechaFabricacion.getTime())) {
                fechaFabricacion.setDate(fechaFabricacion.getDate() + 365);
                let fechaExpiracion = fechaFabricacion.toISOString().split('T')[0];
                $('#fecha-expiracion-facturacion').val(fechaExpiracion);
            } else {
                console.error("Fecha de fabricación inválida.");
                $('#fecha-expiracion-facturacion').val('');
            }
        } else {
            console.error("El campo de fecha de fabricación está vacío.");
            $('#fecha-expiracion-facturacion').val('');
        }
    }

    // Evento para actualizar la fecha de expiración al cambiar la fecha de fabricación
    $('#fecha-fabricacion-facturacion').on('change', function() {
        actualizarFechaExpiracion();
    });

    // Cargar y guardar el cliente seleccionado en localStorage
    var ultimoClienteId = localStorage.getItem('ultimoClienteId');
    if (ultimoClienteId) {
        $('#cliente-facturacion').val(ultimoClienteId);
    }

    $('#cliente-facturacion').on('change', function() {
        var clienteSeleccionado = $(this).val();
        localStorage.setItem('ultimoClienteId', clienteSeleccionado);
        cargarFacturaciones(clienteSeleccionado);
    });

    // Inicializar la página
    function cargarUltimoCliente() {
        var ultimoClienteId = localStorage.getItem('ultimoClienteId');
        if (ultimoClienteId) {
            $('#cliente-facturacion').val(ultimoClienteId);
        }
    }

    /*** Manejo de Importación ***/

    // ✅ NUEVA FUNCIÓN para agregar productos a la tabla
    function agregarProductoATabla(producto) {
        const fila = `
            <tr id="producto-${producto.id}">
                <td class="text-center">${producto.id}</td>
                <td>${escapeHtml(producto.nombre)}</td>
                <td>${escapeHtml(producto.descripcion)}</td>
                <td class="text-center">${escapeHtml(producto.temperatura || '—')}</td>
                <td class="text-center">${escapeHtml(producto.qbo_id || '—')}</td>
                <td class="text-center">${escapeHtml(producto.tax_rate)}</td>
                <td class="text-center">
                    <a href="/productos/${producto.id}/editar" class="btn btn-sm btn-primary" title="Editar">
                        <i class="fas fa-edit"></i>
                    </a>
                    <i class="fas fa-trash-alt eliminar-producto"
                       data-id="${producto.id}"
                       style="color: #dc3545; cursor: pointer;"
                       title="Eliminar"></i>
                </td>
            </tr>
        `;
        $('table tbody').append(fila);

        // Reasignar evento al nuevo botón de eliminar
        $(`#producto-${producto.id} .eliminar-producto`).click(function() {
            eliminarProducto(producto.id, $(`#producto-${producto.id}`));
        });
    }

    // Función para eliminar una fila de productos
    function eliminarFilaProducto(button) {
        console.log('Función eliminarFilaProducto llamada');
        $(button).closest('tr').remove();
        calcularTotales();
    }

    // Función de cálculo de totales
    function calcularTotales() {
        console.log("Calculando totales...");
        const fleteTotal = parseFloat($('#flete_total').val()) || 0;
        const gastosAduanal = parseFloat($('#gastos_agente_aduanal').val()) || 0;
        const arancel = parseFloat($('#arancel').val()) / 100 || 0;
        const ob = parseFloat($('#ob').val()) / 100 || 0;
        const fleteLocal = parseFloat($('#flete_local').val()) || 0;
        const tipoCambioAng = parseFloat($('#tipo_cambio_ang').val()) || 1;

        const rows = $('#productos-body tr');
        let totalFOBGeneral = 0;

        // Calcular el FOB por cada producto y sumar el total FOB general
        rows.each(function() {
            const qtyTotal = parseFloat($(this).find('input[name$="[qty_total]"]').val()) || 0;
            const priceFOB = parseFloat($(this).find('input[name$="[price_fob]"]').val()) || 0;
            const totalFOB = qtyTotal * priceFOB;

            $(this).find('input[name$="[total_fob]"]').val(totalFOB.toFixed(2));
            totalFOBGeneral += totalFOB;
        });

        // Distribuir el flete proporcionalmente y calcular el CIF por cada producto
        rows.each(function() {
            const totalFOB = parseFloat($(this).find('input[name$="[total_fob]"]').val()) || 0;
            const fleteProporcional = (totalFOB / totalFOBGeneral) * fleteTotal;
            const totalCIF = totalFOB + fleteProporcional;

            $(this).find('input[name$="[flete_proporcional]"]').val(fleteProporcional.toFixed(2));
            $(this).find('input[name$="[total_cif]"]').val(totalCIF.toFixed(2));

            // Calcular el CIF en ANG
            const cifAng = totalCIF * tipoCambioAng;
            $(this).find('input[name$="[cif_ang]"]').val(cifAng.toFixed(2));

            // Calcular Arancel (ANG)
            const arancelAng = cifAng * arancel;
            $(this).find('input[name$="[arancel_ang]"]').val(arancelAng.toFixed(2));

            // Calcular OB (ANG)
            const obAng = cifAng * ob;
            $(this).find('input[name$="[ob_ang]"]').val(obAng.toFixed(2));

            // Calcular OB (4.5%)
            const ob45 = obAng * 0.045;
            $(this).find('input[name$="[ob_45]"]').val(ob45.toFixed(2));

            // Calcular el Costo Total Almacén
            const costoTotalAlmacen = cifAng + arancelAng + obAng + fleteLocal + gastosAduanal - ob45;
            $(this).find('input[name$="[costo_total_almacen]"]').val(costoTotalAlmacen.toFixed(2));

            // Calcular el Costo por Unidad (ANG)
            const qtyTotal = parseFloat($(this).find('input[name$="[qty_total]"]').val()) || 1;
            const costoUnidad = costoTotalAlmacen / qtyTotal;
            $(this).find('input[name$="[costo_unidad_ang]"]').val(costoUnidad.toFixed(2));
        });
    }

    // Evento para agregar producto
    $('.add-row').on('click', function() {
        console.log("Botón 'Agregar Producto' clicado");
        agregarProducto();
    });

    // Evento para eliminar producto en la importación
    $(document).on('click', '.eliminar-fila', function() {
        eliminarFilaProducto(this);
    });

    // Eventos para recalcular totales
    $('#tipo_cambio_ang, #flete_total, #gastos_agente_aduanal, #arancel, #ob, #flete_local, #moneda').on('input change', calcularTotales);
    $(document).on('input', '#productos-body input', calcularTotales);
    $(document).on('change', '#productos-body select', calcularTotales);

    // Inicializar la primera fila de productos
    agregarProducto();

    // Inicializar otras funciones
    cargarRecepciones();
    let clienteId = $('#cliente-facturacion').val();
    cargarFacturaciones(clienteId);
    cargarUltimoCliente();
    actualizarFechaExpiracion();

});