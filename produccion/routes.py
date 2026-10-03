"""Vistas del módulo de producción propia. Solo traducen
request → servicio → template."""
import io
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation

import xlsxwriter
from flask import (Blueprint, Response, abort, flash, redirect,
                   render_template, request, url_for)
from flask_login import current_user, login_required
from sqlalchemy.orm import selectinload

from maquila.models import Ingrediente

from . import app_module, reportes, servicios
from .models import LoteConsumo, LoteProduccion, TIPOS_MERMA

# NO reemplazar por `from app import ...`: ver produccion/__init__.py.
Producto = app_module.Producto
db = app_module.db
requiere_permiso_recurso = app_module.requiere_permiso_recurso
_excel_safe = app_module._excel_safe
DASHBOARD_TIMEZONE = getattr(app_module, 'DASHBOARD_TIMEZONE', None)

bp = Blueprint('produccion', __name__, url_prefix='/produccion')
Vendedor = app_module.Vendedor


@bp.context_processor
def _permisos_en_plantilla():
    """`permiso_produccion('editar')` en las plantillas: los botones de cerrar,
    corregir y anular solo se muestran a quien el servidor dejaría pasar.
    Esconderlos no es la seguridad (eso lo hace el decorador en cada ruta);
    es no ofrecer un botón que termina en «No tienes permisos»."""
    # No se llama `puede_produccion`: base.html define un `set` con ese
    # nombre (el booleano del menú) y en los bloques hijos pisa el nuestro.
    def permiso_produccion(accion):
        return (current_user.is_authenticated
                and isinstance(current_user, Vendedor)
                and current_user.tiene_permiso(RECURSO, accion))
    return {'permiso_produccion': permiso_produccion}

# El recurso del sistema de permisos configurables (admin → roles). Leer
# abre las pantallas; crear registra lotes; editar corrige, cierra y
# reabre; eliminar anula.
RECURSO = 'produccion'


def _ahora_local():
    if DASHBOARD_TIMEZONE is None:
        return datetime.now()
    return datetime.now(DASHBOARD_TIMEZONE)


def _hoy_local():
    return _ahora_local().date()


def _decimal(valor):
    """Texto de formulario → Decimal. Vacío o basura → None. La coma
    decimal se acepta: en planta se teclea «12,5»."""
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
    if valor in (None, ''):
        return None
    try:
        return int(str(valor).strip())
    except (TypeError, ValueError):
        return None


def _en(lista, i):
    return lista[i] if i < len(lista) else ''


def _productos():
    return Producto.query.order_by(Producto.nombre).all()


def _ingredientes_activos():
    return (Ingrediente.query.filter_by(activo=True)
            .order_by(Ingrediente.nombre).all())


def _ingredientes_para(lote=None):
    """Los activos, más los que el lote ya usa aunque se hayan desactivado:
    si faltara su fila, guardar sin tocarla lo borraría en silencio."""
    activos = _ingredientes_activos()
    if lote is None:
        return activos
    ids_activos = {i.id for i in activos}
    faltantes = [c.ingrediente for c in lote.consumos
                 if c.ingrediente and c.ingrediente_id not in ids_activos]
    if not faltantes:
        return activos
    return sorted(activos + faltantes, key=lambda i: i.nombre.lower())


def _leer_cabecera(form):
    return {
        'producto_id': _entero(form.get('producto_id')),
        'lote': (form.get('lote') or '').strip(),
        'fecha_produccion': _fecha(form.get('fecha_produccion')),
        'fecha_vencimiento': _fecha(form.get('fecha_vencimiento')),
        'peso_producido': _decimal(form.get('peso_producido')),
        'unidades_producidas': _entero(form.get('unidades_producidas')),
        'cajas_producidas': _entero(form.get('cajas_producidas')),
        'notas': form.get('notas'),
    }


def _leer_consumos(form):
    """{ingrediente_id: Decimal} con lo tecleado. Un campo vacío no viaja
    como consumo; un negativo viaja tal cual para que el servicio lo
    rechace con su mensaje, en vez de desaparecer en silencio."""
    consumos = {}
    for ingrediente_id_raw, cantidad in zip(form.getlist('consumo_ingrediente_id'),
                                            form.getlist('consumo_real')):
        ingrediente_id = _entero(ingrediente_id_raw)
        valor = _decimal(cantidad)
        if ingrediente_id is None or valor is None:
            continue
        consumos[ingrediente_id] = valor
    return consumos


def _leer_mermas(form):
    tipos = form.getlist('merma_tipo')
    cantidades = form.getlist('merma_cantidad')
    motivos = form.getlist('merma_motivo')
    mermas = []
    for i in range(max(len(tipos), len(cantidades), len(motivos))):
        cantidad_raw = (_en(cantidades, i) or '').strip()
        mermas.append({
            'tipo': _en(tipos, i),
            # Basura en la cantidad («abc») llega como None y el servicio
            # la rechaza como «necesita una cantidad positiva».
            'cantidad': _decimal(cantidad_raw) if cantidad_raw else None,
            'motivo': _en(motivos, i),
        })
    return mermas


def _form_de_lote(lote):
    """Lo guardado, en el mismo formato en que viaja el POST, para que la
    plantilla del formulario tenga UNA sola forma de leer valores."""
    return {
        'producto_id': str(lote.producto_id),
        'lote': lote.lote,
        'fecha_produccion': lote.fecha_produccion.strftime('%Y-%m-%d'),
        'fecha_vencimiento': (lote.fecha_vencimiento.strftime('%Y-%m-%d')
                              if lote.fecha_vencimiento else ''),
        'peso_producido': str(lote.peso_producido or ''),
        'unidades_producidas': ('' if lote.unidades_producidas is None
                                else str(lote.unidades_producidas)),
        'cajas_producidas': ('' if lote.cajas_producidas is None
                             else str(lote.cajas_producidas)),
        'notas': lote.notas or '',
    }


def _render_form(lote=None, form=None, consumos=None, mermas=None):
    """El formulario de alta o edición, vacío, con lo guardado o con lo
    que se acaba de teclear y el servidor rechazó. Un rechazo no puede
    devolver el formulario en blanco: veinte consumos son diez minutos de
    trabajo con guantes."""
    if form is None and lote is not None:
        form = _form_de_lote(lote)
        consumos = {c.ingrediente_id: c.cantidad_real for c in lote.consumos}
        mermas = [{'tipo': m.tipo, 'cantidad': m.cantidad, 'motivo': m.motivo or ''}
                  for m in lote.mermas]
    form = form or {}
    consumos = consumos or {}
    mermas = mermas or []
    # Las claves del dict de consumos viajan como str: la plantilla compara
    # contra `i.id|string` y así da igual si vienen del POST o de la base.
    consumos_str = {str(k): ('' if v is None else str(v)) for k, v in consumos.items()}
    return render_template(
        'produccion/lote_form.html',
        lote=lote, form=form, consumos=consumos_str, mermas=mermas,
        productos=_productos(),
        ingredientes=_ingredientes_para(lote),
        recetas_json=reportes.recetas_genericas_json(),
        tipos_merma=TIPOS_MERMA,
        hoy=_hoy_local())


def _tras_guardar(lote):
    """Después de guardar: al detalle, o cerrar en el mismo paso si el botón
    fue «Guardar y cerrar». Cerrar exige el permiso de editar (el de crear
    alcanza para guardar); si falta, lo guardado queda y se avisa. Si el
    cierre se rechaza (falta peso o consumo), lo guardado también queda:
    el lote sigue abierto y el detalle dice qué falta."""
    if request.form.get('accion') != 'cerrar':
        return redirect(url_for('produccion.lote_detalle', lote_id=lote.id))
    if not current_user.tiene_permiso(RECURSO, 'editar'):
        flash('Guardado, pero cerrar un lote requiere permiso de editar producción', 'error')
        return redirect(url_for('produccion.lote_detalle', lote_id=lote.id))
    try:
        servicios.cerrar_lote(lote, current_user.id)
    except servicios.LoteInvalido as exc:
        db.session.rollback()
        flash(f'Quedó guardado pero abierto: {exc}', 'error')
        return redirect(url_for('produccion.lote_detalle', lote_id=lote.id))
    b = servicios.balance(lote)
    rend = f' Rendimiento {b["rendimiento_pct"]} %.' if b['rendimiento_pct'] is not None else ''
    flash(f'Lote {lote.codigo} cerrado.{rend}', 'success')
    return redirect(url_for('produccion.lote_detalle', lote_id=lote.id))


@bp.route('', strict_slashes=False)
@login_required
@requiere_permiso_recurso(RECURSO, 'leer')
def index():
    hoy = _hoy_local()
    desde = hoy - timedelta(days=29)
    abiertos = (LoteProduccion.query
                .filter_by(estado='abierta')
                .options(selectinload(LoteProduccion.producto))
                .order_by(LoteProduccion.fecha_produccion.desc(),
                          LoteProduccion.id.desc()).all())
    recientes = (LoteProduccion.query
                 .filter(LoteProduccion.estado == 'cerrada')
                 .options(selectinload(LoteProduccion.producto),
                          selectinload(LoteProduccion.mermas),
                          selectinload(LoteProduccion.consumos)
                          .selectinload(LoteConsumo.ingrediente))
                 .order_by(LoteProduccion.fecha_produccion.desc(),
                           LoteProduccion.id.desc())
                 .limit(8).all())
    return render_template(
        'produccion/index.html',
        abiertos=abiertos,
        recientes=[reportes.fila_de_lote(l) for l in recientes],
        resumen=reportes.resumen_periodo(desde, hoy),
        desde=desde, hoy=hoy)


@bp.route('/lotes')
@login_required
@requiere_permiso_recurso(RECURSO, 'leer')
def lotes():
    producto_id = request.args.get('producto_id', type=int)
    estado = request.args.get('estado') or ''
    desde = _fecha(request.args.get('desde'))
    hasta = _fecha(request.args.get('hasta'))
    estados = (estado,) if estado in ('abierta', 'cerrada', 'anulada') else None
    filas = [reportes.fila_de_lote(l)
             for l in reportes._lotes(producto_id, desde, hasta, estados=estados)]
    return render_template(
        'produccion/lotes.html',
        filas=filas, productos=_productos(),
        producto_id=producto_id, estado=estado, args=request.args)


@bp.route('/lotes/nuevo', methods=['GET', 'POST'])
@login_required
@requiere_permiso_recurso(RECURSO, 'crear')
def lote_nuevo():
    if request.method == 'POST':
        cabecera = _leer_cabecera(request.form)
        consumos = _leer_consumos(request.form)
        mermas = _leer_mermas(request.form)
        try:
            lote = servicios.crear_lote(
                vendedor_id=current_user.id, consumos=consumos, mermas=mermas,
                **cabecera)
        except servicios.LoteInvalido as exc:
            flash(f'{exc}. Lo tecleado se conserva.', 'error')
            return _render_form(None, request.form, consumos, mermas)
        except Exception:
            db.session.rollback()
            flash('No se pudo registrar el lote: ocurrió un error inesperado. '
                  'Lo tecleado se conserva.', 'error')
            return _render_form(None, request.form, consumos, mermas)
        flash(f'Lote {lote.codigo} registrado', 'success')
        return _tras_guardar(lote)

    form = {}
    producto_id = request.args.get('producto_id', type=int)
    if producto_id:
        form['producto_id'] = str(producto_id)
    return _render_form(None, form or None)


@bp.route('/lotes/<int:lote_id>')
@login_required
@requiere_permiso_recurso(RECURSO, 'leer')
def lote_detalle(lote_id):
    lote = db.session.get(LoteProduccion, lote_id) or abort(404)
    return render_template(
        'produccion/lote_detalle.html',
        lote=lote,
        balance=servicios.balance(lote),
        registrado_por=reportes.nombre_vendedor(lote.registrado_por),
        cerrado_por=reportes.nombre_vendedor(lote.cerrado_por),
        anulado_por=reportes.nombre_vendedor(lote.anulado_por),
        cerrado_en=reportes._local(lote.cerrado_en),
        anulado_en=reportes._local(lote.anulado_en),
        umbral=servicios.UMBRAL_MERMA_ALTA_PCT)


@bp.route('/lotes/<int:lote_id>/editar', methods=['GET', 'POST'])
@login_required
@requiere_permiso_recurso(RECURSO, 'editar')
def lote_editar(lote_id):
    lote = db.session.get(LoteProduccion, lote_id) or abort(404)
    if lote.estado != 'abierta':
        flash(f'{lote.codigo} está {lote.estado}: '
              + ('reabrilo para corregirlo' if lote.estado == 'cerrada'
                 else 'no se puede editar'), 'error')
        return redirect(url_for('produccion.lote_detalle', lote_id=lote_id))

    if request.method == 'POST':
        cabecera = _leer_cabecera(request.form)
        consumos = _leer_consumos(request.form)
        mermas = _leer_mermas(request.form)
        try:
            servicios.editar_lote(lote, cabecera=cabecera,
                                  consumos=consumos, mermas=mermas)
        except (servicios.LoteInvalido, servicios.LoteNoEditable) as exc:
            db.session.rollback()
            flash(f'{exc}. Lo tecleado se conserva.', 'error')
            return _render_form(lote, request.form, consumos, mermas)
        except Exception:
            db.session.rollback()
            flash('No se pudo guardar la corrección: ocurrió un error inesperado. '
                  'Lo tecleado se conserva.', 'error')
            return _render_form(lote, request.form, consumos, mermas)
        flash(f'{lote.codigo} guardado', 'success')
        return _tras_guardar(lote)

    return _render_form(lote)


@bp.route('/lotes/<int:lote_id>/cerrar', methods=['POST'])
@login_required
@requiere_permiso_recurso(RECURSO, 'editar')
def lote_cerrar(lote_id):
    lote = db.session.get(LoteProduccion, lote_id) or abort(404)
    try:
        servicios.cerrar_lote(lote, current_user.id)
    except servicios.LoteInvalido as exc:
        db.session.rollback()
        flash(str(exc), 'error')
        return redirect(url_for('produccion.lote_detalle', lote_id=lote_id))
    b = servicios.balance(lote)
    rend = f' Rendimiento {b["rendimiento_pct"]} %.' if b['rendimiento_pct'] is not None else ''
    flash(f'Lote {lote.codigo} cerrado.{rend}', 'success')
    return redirect(url_for('produccion.lote_detalle', lote_id=lote_id))


@bp.route('/lotes/<int:lote_id>/reabrir', methods=['POST'])
@login_required
@requiere_permiso_recurso(RECURSO, 'editar')
def lote_reabrir(lote_id):
    lote = db.session.get(LoteProduccion, lote_id) or abort(404)
    try:
        servicios.reabrir_lote(lote, current_user.id, request.form.get('motivo', ''))
        flash(f'Lote {lote.codigo} reabierto: corregilo y volvé a cerrarlo', 'success')
    except (servicios.MotivoRequerido, servicios.LoteInvalido) as exc:
        db.session.rollback()
        flash(str(exc), 'error')
    return redirect(url_for('produccion.lote_detalle', lote_id=lote_id))


@bp.route('/lotes/<int:lote_id>/anular', methods=['POST'])
@login_required
@requiere_permiso_recurso(RECURSO, 'eliminar')
def lote_anular(lote_id):
    lote = db.session.get(LoteProduccion, lote_id) or abort(404)
    try:
        servicios.anular_lote(lote, current_user.id, request.form.get('motivo', ''))
        flash(f'Lote {lote.codigo} anulado', 'success')
    except (servicios.MotivoRequerido, servicios.LoteInvalido) as exc:
        db.session.rollback()
        flash(str(exc), 'error')
    return redirect(url_for('produccion.lote_detalle', lote_id=lote_id))


def _filtros_reporte():
    return (request.args.get('producto_id', type=int),
            _fecha(request.args.get('desde')),
            _fecha(request.args.get('hasta')))


@bp.route('/reportes/rendimiento')
@login_required
@requiere_permiso_recurso(RECURSO, 'leer')
def reporte_rendimiento():
    producto_id, desde, hasta = _filtros_reporte()
    filas, resumen = reportes.rendimiento(producto_id, desde, hasta)
    return render_template(
        'produccion/reporte_rendimiento.html',
        filas=filas, resumen=resumen, productos=_productos(),
        producto_id=producto_id, args=request.args,
        umbral=servicios.UMBRAL_MERMA_ALTA_PCT)


@bp.route('/reportes/rendimiento/export')
@login_required
@requiere_permiso_recurso(RECURSO, 'leer')
def reporte_rendimiento_export():
    producto_id, desde, hasta = _filtros_reporte()
    filas, resumen = reportes.rendimiento(producto_id, desde, hasta)

    buffer = io.BytesIO()
    libro = xlsxwriter.Workbook(buffer, {'in_memory': True})
    negrita = libro.add_format({'bold': True})
    kg = libro.add_format({'num_format': '#,##0.000'})
    pct = libro.add_format({'num_format': '0.0'})

    hoja = libro.add_worksheet('Lotes')
    encabezados = ['Código', 'Lote', 'Producto', 'Fecha', 'Consumido kg',
                   'Producido kg', 'Rendimiento %', 'Merma kg', 'Merma %',
                   'Merma identificada kg', 'Sin identificar kg', 'Unidades', 'Cajas']
    for col, titulo in enumerate(encabezados):
        hoja.write(0, col, titulo, negrita)
    for n, f in enumerate(filas, start=1):
        hoja.write(n, 0, _excel_safe(f['codigo']))
        hoja.write(n, 1, _excel_safe(f['lote']))
        hoja.write(n, 2, _excel_safe(f['producto']))
        hoja.write(n, 3, f['fecha'].strftime('%Y-%m-%d') if f['fecha'] else '')
        hoja.write_number(n, 4, float(f['consumido']), kg)
        hoja.write_number(n, 5, float(f['producido']), kg)
        _num_o_vacio(hoja, n, 6, f['rendimiento_pct'], pct)
        _num_o_vacio(hoja, n, 7, f['merma_total'], kg)
        _num_o_vacio(hoja, n, 8, f['merma_pct'], pct)
        hoja.write_number(n, 9, float(f['merma_identificada']), kg)
        _num_o_vacio(hoja, n, 10, f['merma_sin_identificar'], kg)
        _num_o_vacio(hoja, n, 11, f['unidades'])
        _num_o_vacio(hoja, n, 12, f['cajas'])

    hoja2 = libro.add_worksheet('Por producto')
    encabezados2 = ['Producto', 'Lotes', 'Consumido kg', 'Producido kg',
                    'Rendimiento %', 'Merma kg', 'Merma %', 'Identificada kg',
                    'Sin identificar kg', 'Rend. mín %', 'Rend. máx %', 'Lotes con merma alta']
    for col, titulo in enumerate(encabezados2):
        hoja2.write(0, col, titulo, negrita)
    for n, r in enumerate(resumen, start=1):
        hoja2.write(n, 0, _excel_safe(r['producto']))
        hoja2.write_number(n, 1, r['lotes'])
        hoja2.write_number(n, 2, float(r['consumido']), kg)
        hoja2.write_number(n, 3, float(r['producido']), kg)
        _num_o_vacio(hoja2, n, 4, r['rendimiento_pct'], pct)
        hoja2.write_number(n, 5, float(r['merma_total']), kg)
        _num_o_vacio(hoja2, n, 6, r['merma_pct'], pct)
        hoja2.write_number(n, 7, float(r['merma_identificada']), kg)
        hoja2.write_number(n, 8, float(r['merma_sin_identificar']), kg)
        _num_o_vacio(hoja2, n, 9, r['rend_min'], pct)
        _num_o_vacio(hoja2, n, 10, r['rend_max'], pct)
        hoja2.write_number(n, 11, r['lotes_merma_alta'])

    hoja3 = libro.add_worksheet('Consumo por ingrediente')
    encabezados3 = ['Código', 'Lote', 'Producto', 'Ingrediente', 'Unidad',
                    'Teórico', 'Real', 'Diferencia', 'Diferencia %']
    for col, titulo in enumerate(encabezados3):
        hoja3.write(0, col, titulo, negrita)
    n = 1
    for f in filas:
        for v in f['varianzas']:
            hoja3.write(n, 0, _excel_safe(f['codigo']))
            hoja3.write(n, 1, _excel_safe(f['lote']))
            hoja3.write(n, 2, _excel_safe(f['producto']))
            hoja3.write(n, 3, _excel_safe(v['ingrediente']))
            hoja3.write(n, 4, _excel_safe(v['unidad']))
            hoja3.write_number(n, 5, float(v['teorica']), kg)
            hoja3.write_number(n, 6, float(v['real']), kg)
            hoja3.write_number(n, 7, float(v['diferencia']), kg)
            _num_o_vacio(hoja3, n, 8, v['pct'], pct)
            n += 1

    libro.close()
    buffer.seek(0)
    sufijo = f'_{desde.strftime("%Y%m%d")}' if desde else ''
    return Response(
        buffer.read(),
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        headers={'Content-Disposition':
                 f'attachment; filename=rendimiento_produccion{sufijo}.xlsx'})


def _num_o_vacio(hoja, fila, col, valor, formato=None):
    if valor is None:
        hoja.write_blank(fila, col, None)
    elif formato is None:
        hoja.write_number(fila, col, float(valor))
    else:
        hoja.write_number(fila, col, float(valor), formato)


@bp.route('/reportes/mermas')
@login_required
@requiere_permiso_recurso(RECURSO, 'leer')
def reporte_mermas():
    producto_id, desde, hasta = _filtros_reporte()
    return render_template(
        'produccion/reporte_mermas.html',
        datos=reportes.mermas(producto_id, desde, hasta),
        productos=_productos(), producto_id=producto_id, args=request.args,
        umbral=servicios.UMBRAL_MERMA_ALTA_PCT)
