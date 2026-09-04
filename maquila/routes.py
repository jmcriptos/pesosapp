"""Vistas del módulo de maquila. Solo traducen request → servicio → template."""
import io
from datetime import datetime, time, timedelta, timezone
from decimal import Decimal, InvalidOperation

import xlsxwriter
from flask import (Blueprint, Response, abort, flash, redirect,
                   render_template, request, url_for)
from flask_login import current_user, login_required

from . import app_module, reportes, servicios
from .models import (CorridaCaja, CorridaProduccion, Ingrediente, Receta,
                     RecetaIngrediente, RecepcionIngrediente, RecepcionFoto,
                     RecepcionLinea)

# NO reemplazar por `from app import Cliente, Producto, db, requiere_rol,
# DetallePedido, _excel_safe, DASHBOARD_TIMEZONE`: revienta `python app.py`
# (el preview local) con un ImportError circular. Ver el comentario largo en
# maquila/__init__.py.
Cliente = app_module.Cliente
Producto = app_module.Producto
DetallePedido = app_module.DetallePedido
db = app_module.db
requiere_rol = app_module.requiere_rol
_excel_safe = app_module._excel_safe
DASHBOARD_TIMEZONE = getattr(app_module, 'DASHBOARD_TIMEZONE', None)

bp = Blueprint('maquila', __name__, url_prefix='/maquila')

MAX_FOTO_BYTES = 2 * 1024 * 1024

# Lista blanca de mimetypes de foto: lo que declara el navegador al subir NO
# es confiable (un SVG con <script> adentro se serviría después como
# Content-Type de imagen y se ejecutaría desde el origen de la app). Se aplica
# tanto al aceptar la subida como al servir la foto — la segunda comprobación
# cubre datos que hayan quedado guardados de antes de este chequeo.
MIMETYPES_FOTO_PERMITIDOS = {'image/jpeg', 'image/png', 'image/webp'}


def _decimal(valor):
    """Convierte texto de formulario a Decimal. Vacío o basura → None."""
    if valor in (None, ''):
        return None
    try:
        return Decimal(str(valor).replace(',', '.').strip())
    except (InvalidOperation, ValueError):
        return None


def _fecha(valor):
    if not valor:
        return None
    try:
        return datetime.strptime(valor, '%Y-%m-%d').date()
    except ValueError:
        return None


def _entero(valor):
    """Convierte texto de formulario a int. Vacío o basura → None.

    Mismo criterio que `_decimal`: un `producto_id`/`cliente_id`/
    `ingrediente_id` con basura (o ausente) no puede tirar un 500 — tiene que
    poder tratarse como "falta este dato" y avisar con un flash.
    """
    if valor in (None, ''):
        return None
    try:
        return int(valor)
    except (TypeError, ValueError):
        return None


def _ventana_utc(desde, hasta):
    """Convierte un rango de fechas LOCALES (America/Curacao) a la ventana UTC
    equivalente, para filtrar `MovimientoIngrediente.registrado_en` (que se
    guarda en UTC naive).

    El kardex MUESTRA cada fecha convertida a hora local, pero si el filtro
    compara la fecha local pedida directo contra ese UTC crudo, los
    movimientos de las últimas horas del día local (que en UTC ya caen al día
    siguiente) quedan afuera aunque la columna los muestre como del día
    pedido — el mismo error de fondo que ya mordió en temperaturas. El día
    `hasta` es inclusivo: cubre el día local entero, no solo su medianoche.
    """
    if DASHBOARD_TIMEZONE is None:
        return desde, hasta
    desde_utc = None
    if desde:
        desde_utc = (datetime.combine(desde, time.min, tzinfo=DASHBOARD_TIMEZONE)
                     .astimezone(timezone.utc).replace(tzinfo=None))
    hasta_utc = None
    if hasta:
        siguiente_medianoche = (datetime.combine(hasta, time.min, tzinfo=DASHBOARD_TIMEZONE)
                                + timedelta(days=1))
        hasta_utc = (siguiente_medianoche.astimezone(timezone.utc).replace(tzinfo=None)
                    - timedelta(microseconds=1))
    return desde_utc, hasta_utc


def _reparto_con_lineas(corrida, consumos):
    """Arma el reparto FIFO de cada ingrediente y junta las líneas de
    recepción que toca, para que la plantilla pueda mostrar el código de la
    recepción, su fecha y el lote del cliente en vez de un id pelado que no
    le dice nada a quien está parado frente al bulto físico."""
    reparto = {}
    lineas_por_id = {}
    for ingrediente_id, cantidad in consumos.items():
        try:
            tramos = servicios.repartir_fifo(corrida.cliente_id, ingrediente_id, cantidad)
        except (servicios.SaldoInsuficiente, ValueError):
            reparto[ingrediente_id] = None
            continue
        reparto[ingrediente_id] = tramos
        for linea_id, _cantidad_tramo in tramos:
            if linea_id not in lineas_por_id:
                lineas_por_id[linea_id] = db.session.get(RecepcionLinea, linea_id)
    return reparto, lineas_por_id


def _clientes_con_maquila():
    """Cliente de maquila no es un campo: es todo cliente con recepciones."""
    return (Cliente.query
            .join(RecepcionIngrediente,
                  RecepcionIngrediente.cliente_id == Cliente.id)
            .filter(RecepcionIngrediente.anulada_en.is_(None))
            .distinct()
            .order_by(Cliente.nombre)
            .all())


@bp.route('', strict_slashes=False)
@login_required
@requiere_rol(['super_admin'])
def index():
    tarjetas = []
    for cliente in _clientes_con_maquila():
        filas = servicios.saldos_de_cliente(cliente.id)
        abiertas = (CorridaProduccion.query
                    .filter_by(cliente_id=cliente.id, estado='abierta').count())
        ultima = (RecepcionIngrediente.query
                  .filter_by(cliente_id=cliente.id)
                  .order_by(RecepcionIngrediente.recibido_en.desc()).first())
        tarjetas.append({'cliente': cliente, 'saldos': filas,
                         'corridas_abiertas': abiertas, 'ultima': ultima})
    return render_template('maquila/index.html', tarjetas=tarjetas)


@bp.route('/ingredientes', methods=['GET', 'POST'])
@login_required
@requiere_rol(['super_admin'])
def ingredientes():
    if request.method == 'POST':
        nombre = (request.form.get('nombre') or '').strip()
        if not nombre:
            flash('El ingrediente necesita un nombre', 'error')
        elif Ingrediente.query.filter_by(nombre=nombre).first():
            flash(f'Ya existe un ingrediente llamado {nombre}', 'error')
        else:
            db.session.add(Ingrediente(
                nombre=nombre,
                unidad=(request.form.get('unidad') or 'kg'),
                notas=(request.form.get('notas') or None)))
            db.session.commit()
            flash(f'Ingrediente {nombre} agregado', 'success')
        return redirect(url_for('maquila.ingredientes'))

    return render_template('maquila/ingredientes.html',
                           ingredientes=Ingrediente.query.order_by(
                               Ingrediente.nombre).all())


@bp.route('/ingredientes/<int:ingrediente_id>/toggle', methods=['POST'])
@login_required
@requiere_rol(['super_admin'])
def toggle_ingrediente(ingrediente_id):
    ing = db.session.get(Ingrediente, ingrediente_id) or abort(404)
    ing.activo = not ing.activo
    db.session.commit()
    return redirect(url_for('maquila.ingredientes'))


@bp.route('/recepciones')
@login_required
@requiere_rol(['super_admin'])
def recepciones():
    query = RecepcionIngrediente.query
    cliente_id = request.args.get('cliente_id', type=int)
    if cliente_id:
        query = query.filter_by(cliente_id=cliente_id)
    return render_template(
        'maquila/recepciones.html',
        recepciones=query.order_by(RecepcionIngrediente.recibido_en.desc(),
                                   RecepcionIngrediente.id.desc()).all(),
        clientes=Cliente.query.order_by(Cliente.nombre).all(),
        cliente_id=cliente_id)


@bp.route('/recepciones/nueva', methods=['GET', 'POST'])
@login_required
@requiere_rol(['super_admin'])
def recepcion_nueva():
    if request.method == 'POST':
        lineas = []
        ingredientes_ids = request.form.getlist('linea_ingrediente_id')
        lotes = request.form.getlist('linea_lote_cliente')
        vencimientos = request.form.getlist('linea_fecha_vencimiento')
        totales = request.form.getlist('linea_peso_total')
        bultos_crudos = request.form.getlist('linea_bultos')

        for i, ingrediente_id in enumerate(ingredientes_ids):
            if not ingrediente_id:
                continue
            crudos = (bultos_crudos[i] if i < len(bultos_crudos) else '') or ''
            bultos = [b for b in (_decimal(x) for x in crudos.split(',') if x.strip())
                      if b is not None]
            lineas.append({
                'ingrediente_id': _entero(ingrediente_id),
                'lote_cliente': (lotes[i] if i < len(lotes) else '') or None,
                'fecha_vencimiento': _fecha(vencimientos[i] if i < len(vencimientos) else ''),
                'bultos': bultos,
                'peso_total': _decimal(totales[i] if i < len(totales) else ''),
            })

        fotos = []
        for archivo in request.files.getlist('fotos'):
            if not archivo or not archivo.filename:
                continue
            # Normalizado a minúsculas: un cliente que mande "Image/JPEG" no
            # puede perder la recepción entera (cabecera, líneas, bultos y
            # firma ya tecleadas) por una comparación sensible a mayúsculas.
            mimetype = (archivo.mimetype or '').lower()
            if mimetype not in MIMETYPES_FOTO_PERMITIDOS:
                flash(f'Formato de foto no permitido ({mimetype or "desconocido"}): '
                     'subí JPEG, PNG o WEBP', 'error')
                return redirect(url_for('maquila.recepcion_nueva'))
            datos = archivo.read(MAX_FOTO_BYTES + 1)
            if len(datos) > MAX_FOTO_BYTES:
                flash('Una foto supera los 2 MB: redúcela antes de subirla', 'error')
                return redirect(url_for('maquila.recepcion_nueva'))
            fotos.append((datos, mimetype))

        firma_b64 = request.form.get('firma_png') or ''
        firma = None
        if firma_b64.startswith('data:image/png;base64,'):
            import base64
            import binascii
            try:
                firma = base64.b64decode(firma_b64.split(',', 1)[1], validate=True)
            except (binascii.Error, ValueError):
                firma = None
                flash('La firma no se pudo leer: la recepción se guardó sin firma', 'error')

        try:
            recepcion = servicios.crear_recepcion(
                cliente_id=int(request.form['cliente_id']),
                recibido_en=_fecha(request.form.get('recibido_en')),
                vendedor_id=current_user.id,
                lineas=lineas,
                documento_cliente=(request.form.get('documento_cliente') or None),
                temperatura=_decimal(request.form.get('temperatura')),
                transportista=(request.form.get('transportista') or None),
                notas=(request.form.get('notas') or None),
                firma=firma,
                firma_mimetype='image/png' if firma else None,
                fotos=fotos)
        except servicios.RecepcionInvalida as exc:
            db.session.rollback()
            flash(str(exc), 'error')
            return redirect(url_for('maquila.recepcion_nueva'))
        except Exception:
            db.session.rollback()
            flash('No se pudo registrar la recepción: ocurrió un error inesperado', 'error')
            return redirect(url_for('maquila.recepcion_nueva'))

        flash(f'Recepción {recepcion.codigo} registrada', 'success')
        return redirect(url_for('maquila.recepcion_detalle',
                                recepcion_id=recepcion.id))

    return render_template(
        'maquila/recepcion_nueva.html',
        clientes=Cliente.query.order_by(Cliente.nombre).all(),
        ingredientes=Ingrediente.query.filter_by(activo=True)
                                      .order_by(Ingrediente.nombre).all())


@bp.route('/recepciones/<int:recepcion_id>')
@login_required
@requiere_rol(['super_admin'])
def recepcion_detalle(recepcion_id):
    recepcion = db.session.get(RecepcionIngrediente, recepcion_id) or abort(404)
    saldos_linea = {l.id: servicios.saldo_de_linea(l.id) for l in recepcion.lineas}
    return render_template('maquila/recepcion_detalle.html',
                           recepcion=recepcion, saldos_linea=saldos_linea)


@bp.route('/recepciones/<int:recepcion_id>/anular', methods=['POST'])
@login_required
@requiere_rol(['super_admin'])
def recepcion_anular(recepcion_id):
    recepcion = db.session.get(RecepcionIngrediente, recepcion_id) or abort(404)
    try:
        servicios.anular_recepcion(recepcion, current_user.id,
                                   request.form.get('motivo', ''))
        db.session.commit()
        flash(f'Recepción {recepcion.codigo} anulada', 'success')
    except (servicios.RecepcionConsumida, servicios.MotivoRequerido,
            servicios.RecepcionInvalida) as exc:
        db.session.rollback()
        flash(str(exc), 'error')
    except Exception:
        db.session.rollback()
        flash('No se pudo anular la recepción: ocurrió un error inesperado', 'error')
    return redirect(url_for('maquila.recepcion_detalle', recepcion_id=recepcion_id))


@bp.route('/recepciones/foto/<int:foto_id>')
@login_required
@requiere_rol(['super_admin'])
def recepcion_foto(foto_id):
    foto = db.session.get(RecepcionFoto, foto_id) or abort(404)
    # Defensa en profundidad: aunque la subida ya filtra por la lista blanca,
    # una foto guardada antes de este chequeo podría tener otro mimetype.
    mimetype = (foto.mimetype if foto.mimetype in MIMETYPES_FOTO_PERMITIDOS
               else 'application/octet-stream')
    resp = Response(foto.imagen, mimetype=mimetype)
    resp.headers['X-Content-Type-Options'] = 'nosniff'
    resp.headers['Content-Disposition'] = 'inline'
    return resp


@bp.route('/recetas')
@login_required
@requiere_rol(['super_admin'])
def recetas():
    return render_template('maquila/recetas.html',
                           recetas=Receta.query.order_by(Receta.id.desc()).all())


@bp.route('/recetas/nueva', methods=['GET', 'POST'])
@bp.route('/recetas/<int:receta_id>', methods=['GET', 'POST'])
@login_required
@requiere_rol(['super_admin'])
def receta_form(receta_id=None):
    receta = db.session.get(Receta, receta_id) if receta_id else None
    if receta_id and receta is None:
        abort(404)

    if request.method == 'POST':
        producto_id = _entero(request.form.get('producto_id'))
        cliente_id = request.form.get('cliente_id', type=int) or None
        if producto_id is None:
            flash('Elegí un producto para la receta', 'error')
            return redirect(url_for('maquila.recetas'))
        try:
            servicios.validar_receta_unica(producto_id, cliente_id,
                                           receta_id=receta.id if receta else None)
        except servicios.RecetaDuplicada as exc:
            flash(str(exc), 'error')
            return redirect(url_for('maquila.recetas'))

        if receta is None:
            receta = Receta(creada_por=current_user.id)
            db.session.add(receta)
        receta.producto_id = producto_id
        receta.cliente_id = cliente_id
        receta.nombre = (request.form.get('nombre') or 'Receta').strip()
        receta.base_kg = _decimal(request.form.get('base_kg')) or Decimal('100')
        receta.activa = bool(request.form.get('activa'))
        db.session.flush()

        RecetaIngrediente.query.filter_by(receta_id=receta.id).delete()
        for ingrediente_id_raw, cantidad in zip(
                request.form.getlist('item_ingrediente_id'),
                request.form.getlist('item_cantidad')):
            ingrediente_id = _entero(ingrediente_id_raw)
            valor = _decimal(cantidad)
            if ingrediente_id and valor and valor > 0:
                db.session.add(RecetaIngrediente(
                    receta_id=receta.id, ingrediente_id=ingrediente_id,
                    cantidad=valor))
        db.session.commit()
        flash('Receta guardada', 'success')
        return redirect(url_for('maquila.recetas'))

    return render_template(
        'maquila/receta_form.html', receta=receta,
        clientes=Cliente.query.order_by(Cliente.nombre).all(),
        productos=Producto.query.order_by(Producto.nombre).all(),
        ingredientes=Ingrediente.query.filter_by(activo=True)
                                      .order_by(Ingrediente.nombre).all())


@bp.route('/corridas')
@login_required
@requiere_rol(['super_admin'])
def corridas():
    query = CorridaProduccion.query
    cliente_id = request.args.get('cliente_id', type=int)
    if cliente_id:
        query = query.filter_by(cliente_id=cliente_id)
    return render_template(
        'maquila/corridas.html',
        corridas=query.order_by(CorridaProduccion.fecha_produccion.desc(),
                                CorridaProduccion.id.desc()).all(),
        clientes=Cliente.query.order_by(Cliente.nombre).all(),
        cliente_id=cliente_id)


@bp.route('/corridas/nueva', methods=['GET', 'POST'])
@login_required
@requiere_rol(['super_admin'])
def corrida_nueva():
    if request.method == 'POST':
        cliente_id = _entero(request.form.get('cliente_id'))
        producto_id = _entero(request.form.get('producto_id'))
        if cliente_id is None or producto_id is None:
            flash('Elegí un cliente y un producto válidos', 'error')
            return redirect(url_for('maquila.corridas'))
        try:
            corrida = servicios.abrir_corrida(
                cliente_id=cliente_id,
                producto_id=producto_id,
                lote=request.form.get('lote', ''),
                fecha_produccion=_fecha(request.form.get('fecha_produccion')),
                fecha_vencimiento=_fecha(request.form.get('fecha_vencimiento')),
                vendedor_id=current_user.id,
                notas=(request.form.get('notas') or None))
        except servicios.CorridaInvalida as exc:
            db.session.rollback()
            flash(str(exc), 'error')
            return redirect(url_for('maquila.corridas'))
        flash(f'Corrida {corrida.codigo} abierta', 'success')
        return redirect(url_for('maquila.corrida_detalle', corrida_id=corrida.id))

    return render_template(
        'maquila/corrida_detalle.html', corrida=None,
        clientes=Cliente.query.order_by(Cliente.nombre).all(),
        productos=Producto.query.order_by(Producto.nombre).all(),
        consumo_actual={}, reparto_origen='teorico', ingredientes=[],
        reparto={}, lineas_reparto={}, merma=None, falta_ingrediente_id=None)


@bp.route('/corridas/<int:corrida_id>')
@login_required
@requiere_rol(['super_admin'])
def corrida_detalle(corrida_id):
    corrida = db.session.get(CorridaProduccion, corrida_id) or abort(404)
    consumo_actual = {}
    if corrida.receta and corrida.peso_producido > 0:
        consumo_actual = servicios.consumo_teorico(corrida.receta, corrida.peso_producido)

    # El reparto FIFO se muestra ANTES de confirmar, para poder corregirlo.
    # Acá parte siempre del teórico de la receta: si el operario edita el
    # consumo real, `corrida_recalcular` vuelve a esta misma plantilla con el
    # reparto recalculado contra lo declarado (`reparto_origen='declarado'`).
    reparto, lineas_reparto = _reparto_con_lineas(corrida, consumo_actual)
    merma = servicios.merma_de_corrida(corrida) if corrida.estado != 'abierta' else None

    # Si venimos de un cierre rechazado por falta de saldo (`corrida_cerrar`
    # abajo), el ingrediente que faltó viaja en la query string para poder
    # ofrecer un link directo a la pantalla de ajustes, precargado con el
    # cliente y el ingrediente correctos: el operario llega en un clic en vez
    # de tener que ir a `/maquila/ajustes` y volver a elegir todo a mano.
    falta_ingrediente_id = request.args.get('falta_ingrediente_id', type=int)

    return render_template(
        'maquila/corrida_detalle.html', corrida=corrida, consumo_actual=consumo_actual,
        reparto=reparto, reparto_origen='teorico', lineas_reparto=lineas_reparto,
        merma=merma, falta_ingrediente_id=falta_ingrediente_id,
        ingredientes=Ingrediente.query.filter_by(activo=True)
                                      .order_by(Ingrediente.nombre).all(),
        clientes=[], productos=[])


@bp.route('/corridas/<int:corrida_id>/recalcular', methods=['POST'])
@login_required
@requiere_rol(['super_admin'])
def corrida_recalcular(corrida_id):
    """Recalcula el reparto FIFO contra el consumo REAL que el operario acaba
    de editar, sin cerrar nada. Sin este paso, el reparto que se ve en
    pantalla queda desactualizado apenas se toca el consumo teórico: sería
    mostrar una promesa que `cerrar_corrida` no cumple."""
    corrida = db.session.get(CorridaProduccion, corrida_id) or abort(404)
    if corrida.estado != 'abierta':
        flash(f'La corrida {corrida.codigo} no está abierta', 'error')
        return redirect(url_for('maquila.corrida_detalle', corrida_id=corrida_id))

    consumos = {}
    for ingrediente_id_raw, cantidad in zip(
            request.form.getlist('consumo_ingrediente_id'),
            request.form.getlist('consumo_real')):
        ingrediente_id = _entero(ingrediente_id_raw)
        valor = _decimal(cantidad)
        if ingrediente_id and valor and valor > 0:
            consumos[ingrediente_id] = valor

    reparto, lineas_reparto = _reparto_con_lineas(corrida, consumos)

    return render_template(
        'maquila/corrida_detalle.html', corrida=corrida, consumo_actual=consumos,
        reparto=reparto, reparto_origen='declarado', lineas_reparto=lineas_reparto,
        merma=None, falta_ingrediente_id=None,
        ingredientes=Ingrediente.query.filter_by(activo=True)
                                      .order_by(Ingrediente.nombre).all(),
        clientes=[], productos=[])


@bp.route('/corridas/<int:corrida_id>/caja', methods=['POST'])
@login_required
@requiere_rol(['super_admin'])
def corrida_caja(corrida_id):
    corrida = db.session.get(CorridaProduccion, corrida_id) or abort(404)
    try:
        servicios.agregar_caja_producida(corrida,
                                         _decimal(request.form.get('peso')))
        db.session.commit()
    except servicios.CorridaInvalida as exc:
        db.session.rollback()
        flash(str(exc), 'error')
    return redirect(url_for('maquila.corrida_detalle', corrida_id=corrida_id))


@bp.route('/corridas/<int:corrida_id>/cerrar', methods=['POST'])
@login_required
@requiere_rol(['super_admin'])
def corrida_cerrar(corrida_id):
    corrida = db.session.get(CorridaProduccion, corrida_id) or abort(404)

    consumos = {}
    for ingrediente_id_raw, cantidad in zip(
            request.form.getlist('consumo_ingrediente_id'),
            request.form.getlist('consumo_real')):
        ingrediente_id = _entero(ingrediente_id_raw)
        valor = _decimal(cantidad)
        if ingrediente_id and valor and valor > 0:
            consumos[ingrediente_id] = valor

    try:
        servicios.cerrar_corrida(corrida, consumos, current_user.id)
    except servicios.SaldoInsuficiente as exc:
        db.session.rollback()
        ing = db.session.get(Ingrediente, exc.ingrediente_id)
        flash(f'Faltan {exc.faltante} de {ing.nombre if ing else exc.ingrediente_id}: '
              f'se piden {exc.pedido} y hay {exc.disponible}. '
              f'Registra un ajuste de entrada con su motivo antes de cerrar.', 'error')
        # El ingrediente que faltó viaja en la query string para que
        # corrida_detalle pueda ofrecer un link directo a /maquila/ajustes,
        # precargado con el cliente y el ingrediente correctos.
        return redirect(url_for('maquila.corrida_detalle', corrida_id=corrida_id,
                                falta_ingrediente_id=exc.ingrediente_id))
    except servicios.CorridaInvalida as exc:
        db.session.rollback()
        flash(str(exc), 'error')
        return redirect(url_for('maquila.corrida_detalle', corrida_id=corrida_id))

    flash(f'Corrida {corrida.codigo} cerrada. '
          f'Merma: {servicios.merma_de_corrida(corrida)} kg', 'success')
    return redirect(url_for('maquila.corrida_detalle', corrida_id=corrida_id))


@bp.route('/corridas/<int:corrida_id>/anular', methods=['POST'])
@login_required
@requiere_rol(['super_admin'])
def corrida_anular(corrida_id):
    corrida = db.session.get(CorridaProduccion, corrida_id) or abort(404)
    try:
        servicios.anular_corrida(corrida, current_user.id,
                                 request.form.get('motivo', ''))
        db.session.commit()
        flash(f'Corrida {corrida.codigo} anulada', 'success')
    except (servicios.CorridaFacturada, servicios.CorridaInvalida,
            servicios.MotivoRequerido) as exc:
        db.session.rollback()
        flash(str(exc), 'error')
    return redirect(url_for('maquila.corrida_detalle', corrida_id=corrida_id))


@bp.route('/ajustes', methods=['GET', 'POST'])
@login_required
@requiere_rol(['super_admin'])
def ajustes():
    """Ajuste manual del saldo de un cliente/ingrediente, con motivo obligatorio.

    Es la escotilla que le falta a `corrida_cerrar`: cuando el consumo real
    supera lo recibido —que es lo normal, no un caso borde—, la corrida no
    cierra hasta que alguien registre acá la diferencia. `registrar_movimiento`
    ya exige motivo para `tipo='ajuste'` (MotivoRequerido); acá solo se
    traduce esa excepción a un flash.
    """
    if request.method == 'POST':
        cliente_id = _entero(request.form.get('cliente_id'))
        ingrediente_id = _entero(request.form.get('ingrediente_id'))
        cantidad = _decimal(request.form.get('cantidad'))
        sentido = request.form.get('sentido')
        motivo = request.form.get('motivo', '')

        if cliente_id is None or ingrediente_id is None:
            flash('Elegí un cliente y un ingrediente válidos', 'error')
            return redirect(url_for('maquila.ajustes', cliente_id=cliente_id))
        if cantidad is None or cantidad <= 0:
            flash('La cantidad del ajuste tiene que ser un número positivo', 'error')
            return redirect(url_for('maquila.ajustes', cliente_id=cliente_id))
        if sentido not in ('entrada', 'salida'):
            flash('Elegí si el ajuste es una entrada o una salida', 'error')
            return redirect(url_for('maquila.ajustes', cliente_id=cliente_id))

        # `cliente_id` viaja en la query string (llega desde el link del
        # mensaje de error de `corrida_cerrar`, o de un enlace viejo, o
        # tecleado a mano): un cliente borrado o un id inventado no puede
        # llegar hasta el INSERT y reventar con un IntegrityError de FK.
        # Se valida ANTES de tocar `registrar_movimiento`, con el mismo
        # criterio que el resto del módulo (mensaje, no 500).
        if db.session.get(Cliente, cliente_id) is None:
            flash('Ese cliente no existe', 'error')
            return redirect(url_for('maquila.ajustes', cliente_id=cliente_id))
        if db.session.get(Ingrediente, ingrediente_id) is None:
            flash('Ese ingrediente no existe', 'error')
            return redirect(url_for('maquila.ajustes', cliente_id=cliente_id))

        # El signo lo pone esta pantalla, no `registrar_movimiento`: para
        # `tipo='ajuste'` esa función guarda la cantidad tal cual llega (el
        # signo automático solo existe para `tipo='salida'`).
        cantidad_con_signo = cantidad if sentido == 'entrada' else -cantidad

        try:
            servicios.registrar_movimiento(
                cliente_id=cliente_id,
                ingrediente_id=ingrediente_id,
                tipo='ajuste',
                cantidad=cantidad_con_signo,
                origen_tipo='manual',
                vendedor_id=current_user.id,
                motivo=motivo,
            )
            db.session.commit()
        except servicios.MotivoRequerido as exc:
            db.session.rollback()
            flash(str(exc), 'error')
            return redirect(url_for('maquila.ajustes', cliente_id=cliente_id))
        except Exception:
            # Resguardo genérico, mismo patrón que `recepcion_nueva` y
            # `recepcion_anular`: la validación de arriba cubre el caso
            # esperado (cliente/ingrediente borrado), pero esta ruta escribe
            # en el ledger y no puede ser la única del módulo sin una red
            # detrás para cualquier otro error inesperado.
            db.session.rollback()
            flash('No se pudo registrar el ajuste: ocurrió un error inesperado', 'error')
            return redirect(url_for('maquila.ajustes', cliente_id=cliente_id))

        flash('Ajuste registrado', 'success')
        return redirect(url_for('maquila.ajustes', cliente_id=cliente_id))

    cliente_id = request.args.get('cliente_id', type=int)
    ajustes_de_cliente = []
    if cliente_id:
        for mov in servicios.ajustes_manuales_de_cliente(cliente_id):
            ajustes_de_cliente.append({
                'fecha': reportes._local(mov.registrado_en),
                'ingrediente': mov.ingrediente.nombre,
                'unidad': mov.ingrediente.unidad,
                'cantidad': mov.cantidad,
                'responsable': mov.vendedor.nombre_completo if mov.vendedor else '—',
                'motivo': mov.motivo,
            })

    return render_template(
        'maquila/ajustes.html',
        clientes=_clientes_con_maquila(),
        ingredientes=Ingrediente.query.filter_by(activo=True)
                                      .order_by(Ingrediente.nombre).all(),
        cliente_id=cliente_id,
        ingrediente_id_sugerido=request.args.get('ingrediente_id', type=int),
        ajustes=ajustes_de_cliente)


@bp.route('/asignar/<int:detalle_id>', methods=['POST'])
@login_required
@requiere_rol(['super_admin'])
def asignar_detalle(detalle_id):
    detalle = db.session.get(DetallePedido, detalle_id) or abort(404)

    # Mismo corte que `registrar_caja_pesada` en app.py: la cifra de un
    # pedido facturado ya está en QuickBooks, no se puede seguir metiendo
    # cajas ahí aunque el POST llegue directo (sin pasar por la pantalla).
    if detalle.pedido.estado == 'facturado':
        flash('No se puede asignar cajas en un pedido facturado', 'error')
        return redirect(url_for('pesar_pedido', pedido_id=detalle.pedido_id,
                                detalle_id=detalle.id))

    ids = request.form.getlist('corrida_caja_id', type=int)
    cajas = [db.session.get(CorridaCaja, i) for i in ids]
    cajas = [c for c in cajas if c is not None]

    # El checklist que arma `_asignar_cajas.html` siempre ofrece ids
    # correctos, pero el servidor no puede confiar en eso: un POST con un id
    # cambiado a mano podría pegar el lote de OTRO cliente (o de otro
    # producto) a este pedido, que es exactamente lo que este módulo existe
    # para blindar. Se rechaza el lote entero — nada se escribe — si una
    # sola caja no es del cliente/producto de esta línea.
    ajenas = [caja for caja in cajas
             if caja.corrida.cliente_id != detalle.pedido.cliente_id
             or caja.corrida.producto_id != detalle.producto_id]
    if ajenas:
        flash('Alguna caja seleccionada no es de este cliente o producto: '
             'no se asignó ninguna', 'error')
        return redirect(url_for('pesar_pedido', pedido_id=detalle.pedido_id,
                                detalle_id=detalle.id))

    try:
        creadas = servicios.asignar_cajas(detalle, cajas, current_user.id)
    except servicios.CajaNoDisponible as exc:
        db.session.rollback()
        flash(str(exc), 'error')
    else:
        flash(f'{len(creadas)} caja(s) asignadas desde producción', 'success')

    return redirect(url_for('pesar_pedido', pedido_id=detalle.pedido_id,
                            detalle_id=detalle.id))


@bp.route('/reportes/saldos')
@login_required
@requiere_rol(['super_admin'])
def reporte_saldos():
    cliente_id = request.args.get('cliente_id', type=int)
    filas = reportes.saldos(cliente_id) if cliente_id else []
    return render_template('maquila/reporte_saldos.html', filas=filas,
                           cliente_id=cliente_id,
                           clientes=_clientes_con_maquila())


@bp.route('/reportes/kardex')
@login_required
@requiere_rol(['super_admin'])
def reporte_kardex():
    cliente_id = request.args.get('cliente_id', type=int)
    desde_utc, hasta_utc = _ventana_utc(_fecha(request.args.get('desde')),
                                        _fecha(request.args.get('hasta')))
    ingrediente_id = request.args.get('ingrediente_id', type=int)
    filas = reportes.kardex(
        cliente_id,
        ingrediente_id=ingrediente_id,
        desde=desde_utc,
        hasta=hasta_utc) if cliente_id else []
    # El id seleccionado va RESUELTO a la plantilla. Jinja no tiene los
    # builtins de Python, así que un `args.get(..., type=int)` allá adentro
    # pasa `Undefined` como conversor y werkzeug revienta al llamarlo — pero
    # solo cuando el parámetro viene en la query, que es justo lo que ningún
    # test cubría. El parseo se hace acá, donde `int` existe.
    return render_template(
        'maquila/reporte_kardex.html', filas=filas, cliente_id=cliente_id,
        ingrediente_id=ingrediente_id,
        clientes=_clientes_con_maquila(),
        ingredientes=Ingrediente.query.order_by(Ingrediente.nombre).all(),
        args=request.args)


@bp.route('/reportes/kardex/export')
@login_required
@requiere_rol(['super_admin'])
def reporte_kardex_export():
    cliente_id = request.args.get('cliente_id', type=int) or abort(400)
    desde_utc, hasta_utc = _ventana_utc(_fecha(request.args.get('desde')),
                                        _fecha(request.args.get('hasta')))
    filas = reportes.kardex(
        cliente_id,
        ingrediente_id=request.args.get('ingrediente_id', type=int),
        desde=desde_utc,
        hasta=hasta_utc)

    buffer = io.BytesIO()
    libro = xlsxwriter.Workbook(buffer, {'in_memory': True})
    hoja = libro.add_worksheet('Kardex')
    negrita = libro.add_format({'bold': True})
    encabezados = ['Fecha', 'Tipo', 'Ingrediente', 'Cantidad',
                   'Saldo', 'Origen', 'Responsable', 'Motivo']
    for col, titulo in enumerate(encabezados):
        hoja.write(0, col, titulo, negrita)

    for fila_num, fila in enumerate(filas, start=1):
        hoja.write(fila_num, 0, fila['fecha'].strftime('%Y-%m-%d %H:%M'))
        hoja.write(fila_num, 1, _excel_safe(fila['tipo']))
        hoja.write(fila_num, 2, _excel_safe(fila['ingrediente']))
        hoja.write(fila_num, 3, fila['cantidad'])
        hoja.write(fila_num, 4, fila['saldo_acumulado'])
        hoja.write(fila_num, 5, _excel_safe(fila['origen']))
        hoja.write(fila_num, 6, _excel_safe(fila['responsable']))
        hoja.write(fila_num, 7, _excel_safe(fila['motivo'] or ''))

    libro.close()
    buffer.seek(0)
    return Response(
        buffer.read(),
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        headers={'Content-Disposition':
                 f'attachment; filename=kardex_{cliente_id}.xlsx'})


@bp.route('/reportes/rendimiento')
@login_required
@requiere_rol(['super_admin'])
def reporte_rendimiento():
    cliente_id = request.args.get('cliente_id', type=int)
    return render_template(
        'maquila/reporte_rendimiento.html',
        filas=reportes.rendimiento(
            cliente_id=cliente_id,
            desde=_fecha(request.args.get('desde')),
            hasta=_fecha(request.args.get('hasta'))),
        # Resuelto acá, no en la plantilla: ver la nota en reporte_kardex.
        cliente_id=cliente_id,
        clientes=_clientes_con_maquila(), args=request.args)


@bp.route('/reportes/trazabilidad')
@login_required
@requiere_rol(['super_admin'])
def reporte_trazabilidad():
    termino = request.args.get('q', '')
    resultado = reportes.trazar(termino) if termino else None
    return render_template('maquila/reporte_trazabilidad.html',
                           resultado=resultado, termino=termino)
