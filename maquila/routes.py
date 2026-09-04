"""Vistas del módulo de maquila. Solo traducen request → servicio → template."""
from datetime import datetime
from decimal import Decimal, InvalidOperation

from flask import (Blueprint, Response, abort, flash, redirect,
                   render_template, request, url_for)
from flask_login import current_user, login_required

from . import app_module, servicios
from .models import (CorridaCaja, CorridaProduccion, Ingrediente, Receta,
                     RecetaIngrediente, RecepcionIngrediente, RecepcionFoto)

# NO reemplazar por `from app import Cliente, Producto, db, requiere_rol`:
# revienta `python app.py` (el preview local) con un ImportError circular.
# Ver el comentario largo en maquila/__init__.py para el porqué.
Cliente = app_module.Cliente
Producto = app_module.Producto
db = app_module.db
requiere_rol = app_module.requiere_rol

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
                'ingrediente_id': int(ingrediente_id),
                'lote_cliente': (lotes[i] if i < len(lotes) else '') or None,
                'fecha_vencimiento': _fecha(vencimientos[i] if i < len(vencimientos) else ''),
                'bultos': bultos,
                'peso_total': _decimal(totales[i] if i < len(totales) else ''),
            })

        fotos = []
        for archivo in request.files.getlist('fotos'):
            if not archivo or not archivo.filename:
                continue
            mimetype = archivo.mimetype or ''
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
        producto_id = int(request.form['producto_id'])
        cliente_id = request.form.get('cliente_id', type=int) or None
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
        for ingrediente_id, cantidad in zip(
                request.form.getlist('item_ingrediente_id'),
                request.form.getlist('item_cantidad')):
            valor = _decimal(cantidad)
            if ingrediente_id and valor and valor > 0:
                db.session.add(RecetaIngrediente(
                    receta_id=receta.id, ingrediente_id=int(ingrediente_id),
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
        try:
            corrida = servicios.abrir_corrida(
                cliente_id=int(request.form['cliente_id']),
                producto_id=int(request.form['producto_id']),
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
        teoricos={}, ingredientes=[], reparto={})


@bp.route('/corridas/<int:corrida_id>')
@login_required
@requiere_rol(['super_admin'])
def corrida_detalle(corrida_id):
    corrida = db.session.get(CorridaProduccion, corrida_id) or abort(404)
    teoricos = {}
    if corrida.receta and corrida.peso_producido > 0:
        teoricos = servicios.consumo_teorico(corrida.receta, corrida.peso_producido)

    # El reparto FIFO se muestra ANTES de confirmar, para poder corregirlo.
    reparto = {}
    for ingrediente_id, cantidad in teoricos.items():
        try:
            reparto[ingrediente_id] = servicios.repartir_fifo(
                corrida.cliente_id, ingrediente_id, cantidad)
        except (servicios.SaldoInsuficiente, ValueError):
            reparto[ingrediente_id] = None

    return render_template(
        'maquila/corrida_detalle.html', corrida=corrida, teoricos=teoricos,
        reparto=reparto,
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
    for ingrediente_id, cantidad in zip(
            request.form.getlist('consumo_ingrediente_id'),
            request.form.getlist('consumo_real')):
        valor = _decimal(cantidad)
        if ingrediente_id and valor and valor > 0:
            consumos[int(ingrediente_id)] = valor

    try:
        servicios.cerrar_corrida(corrida, consumos, current_user.id)
    except servicios.SaldoInsuficiente as exc:
        db.session.rollback()
        ing = db.session.get(Ingrediente, exc.ingrediente_id)
        flash(f'Faltan {exc.faltante} de {ing.nombre if ing else exc.ingrediente_id}: '
              f'se piden {exc.pedido} y hay {exc.disponible}. '
              f'Registra un ajuste de entrada con su motivo antes de cerrar.', 'error')
        return redirect(url_for('maquila.corrida_detalle', corrida_id=corrida_id))
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
