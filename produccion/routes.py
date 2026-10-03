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

from . import app_module, reportes, servicios
from .models import (Formula, Insumo, LoteConsumo, LoteProduccion, TIPOS_MERMA,
                     UNIDADES)

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


def _insumos_activos():
    return Insumo.query.filter_by(activo=True).order_by(Insumo.nombre).all()


def _insumos_para(lote=None):
    """Los activos, más los que el lote ya usa aunque se hayan desactivado:
    si faltara su fila, guardar sin tocarla lo borraría en silencio."""
    activos = _insumos_activos()
    if lote is None:
        return activos
    ids_activos = {i.id for i in activos}
    faltantes = [c.insumo for c in lote.consumos
                 if c.insumo and c.insumo_id not in ids_activos]
    if not faltantes:
        return activos
    return sorted(activos + faltantes, key=lambda i: i.nombre.lower())


def _insumos_para_formula(formula=None):
    """Igual que `_insumos_para`, para la fórmula: un insumo desactivado
    que la fórmula ya lleva tiene que seguir en su fila."""
    activos = _insumos_activos()
    if formula is None:
        return activos
    ids_activos = {i.id for i in activos}
    faltantes = [f.insumo for f in formula.insumos
                 if f.insumo and f.insumo_id not in ids_activos]
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
    """{insumo_id: Decimal} con lo tecleado. Un campo vacío no viaja como
    consumo; un negativo viaja tal cual para que el servicio lo rechace
    con su mensaje, en vez de desaparecer en silencio."""
    consumos = {}
    for insumo_id_raw, cantidad in zip(form.getlist('consumo_insumo_id'),
                                       form.getlist('consumo_real')):
        insumo_id = _entero(insumo_id_raw)
        valor = _decimal(cantidad)
        if insumo_id is None or valor is None:
            continue
        consumos[insumo_id] = valor
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
        consumos = {c.insumo_id: c.cantidad_real for c in lote.consumos}
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
        insumos=_insumos_para(lote),
        formulas_json=reportes.formulas_json(),
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
                          .selectinload(LoteConsumo.insumo))
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

    hoja3 = libro.add_worksheet('Consumo por insumo')
    encabezados3 = ['Código', 'Lote', 'Producto', 'Insumo', 'Unidad',
                    'Teórico', 'Real', 'Diferencia', 'Diferencia %']
    for col, titulo in enumerate(encabezados3):
        hoja3.write(0, col, titulo, negrita)
    n = 1
    for f in filas:
        for v in f['varianzas']:
            hoja3.write(n, 0, _excel_safe(f['codigo']))
            hoja3.write(n, 1, _excel_safe(f['lote']))
            hoja3.write(n, 2, _excel_safe(f['producto']))
            hoja3.write(n, 3, _excel_safe(v['insumo']))
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


# ------------------------------------------------------------- catálogo

@bp.route('/insumos', methods=['GET', 'POST'])
@login_required
@requiere_permiso_recurso(RECURSO, 'leer')
def insumos():
    if request.method == 'POST':
        if not current_user.tiene_permiso(RECURSO, 'editar'):
            flash('Dar de alta insumos requiere permiso de editar producción', 'error')
            return redirect(url_for('produccion.insumos'))
        try:
            insumo = servicios.crear_insumo(
                nombre=request.form.get('nombre'),
                unidad=request.form.get('unidad') or 'kg',
                notas=request.form.get('notas'))
            flash(f'Insumo {insumo.nombre} agregado', 'success')
        except servicios.InsumoInvalido as exc:
            flash(str(exc), 'error')
        return redirect(url_for('produccion.insumos'))
    return render_template('produccion/insumos.html',
                           insumos=Insumo.query.order_by(Insumo.nombre).all(),
                           unidades=UNIDADES)


@bp.route('/insumos/carga', methods=['POST'])
@login_required
@requiere_permiso_recurso(RECURSO, 'editar')
def insumos_carga():
    """Carga masiva: el textarea viaja en `lineas`. Si se rechaza, vuelve
    la pantalla con el texto puesto, para corregir la línea y reenviar."""
    texto = request.form.get('lineas') or ''
    try:
        creados, omitidos = servicios.cargar_insumos(texto)
    except servicios.InsumoInvalido as exc:
        flash(f'{exc}. No se cargó ninguno; el texto se conserva.', 'error')
        return render_template('produccion/insumos.html',
                               insumos=Insumo.query.order_by(Insumo.nombre).all(),
                               unidades=UNIDADES, lineas=texto)
    partes = [f'{len(creados)} insumo{"s" if len(creados) != 1 else ""} cargado{"s" if len(creados) != 1 else ""}']
    if omitidos:
        partes.append(f'{len(omitidos)} ya existía{"n" if len(omitidos) != 1 else ""} '
                      f'({", ".join(omitidos[:6])}{"…" if len(omitidos) > 6 else ""})')
    flash('; '.join(partes), 'success' if creados else 'error')
    return redirect(url_for('produccion.insumos'))


@bp.route('/insumos/<int:insumo_id>/toggle', methods=['POST'])
@login_required
@requiere_permiso_recurso(RECURSO, 'editar')
def insumo_toggle(insumo_id):
    insumo = db.session.get(Insumo, insumo_id) or abort(404)
    insumo.activo = not insumo.activo
    db.session.commit()
    return redirect(url_for('produccion.insumos'))


@bp.route('/formulas')
@login_required
@requiere_permiso_recurso(RECURSO, 'leer')
def formulas():
    return render_template(
        'produccion/formulas.html',
        formulas=(Formula.query
                  .options(selectinload(Formula.producto),
                           selectinload(Formula.insumos))
                  .order_by(Formula.activa.desc(), Formula.id.desc()).all()))


def _leer_items_formula(form):
    """{insumo_id: Decimal} de las listas paralelas del form. Un insumo
    repetido se rechaza: adivinar cuál de las dos filas vale es adivinar
    la fórmula."""
    items = {}
    for insumo_id_raw, cantidad in zip(form.getlist('item_insumo_id'),
                                       form.getlist('item_cantidad')):
        insumo_id = _entero(insumo_id_raw)
        valor = _decimal(cantidad)
        if insumo_id is None or valor is None or valor <= 0:
            continue
        if insumo_id in items:
            raise servicios.FormulaInvalida(
                'Hay un insumo repetido en la fórmula: dejá una sola fila por insumo')
        items[insumo_id] = valor
    return items


@bp.route('/formulas/nueva', methods=['GET', 'POST'])
@bp.route('/formulas/<int:formula_id>', methods=['GET', 'POST'])
@login_required
@requiere_permiso_recurso(RECURSO, 'editar')
def formula_form(formula_id=None):
    formula = db.session.get(Formula, formula_id) if formula_id else None
    if formula_id and formula is None:
        abort(404)

    if request.method == 'POST':
        try:
            items = _leer_items_formula(request.form)
            formula = servicios.guardar_formula(
                formula,
                producto_id=_entero(request.form.get('producto_id')),
                nombre=request.form.get('nombre'),
                base_kg=_decimal(request.form.get('base_kg')),
                activa=bool(request.form.get('activa')),
                items=items,
                vendedor_id=current_user.id)
        except servicios.FormulaInvalida as exc:
            flash(f'{exc}. Lo tecleado se conserva.', 'error')
            return _render_formula(formula, request.form)
        except Exception:
            db.session.rollback()
            flash('No se pudo guardar la fórmula: ocurrió un error inesperado. '
                  'Lo tecleado se conserva.', 'error')
            return _render_formula(formula, request.form)
        flash(f'Fórmula «{formula.nombre}» guardada', 'success')
        return redirect(url_for('produccion.formulas'))

    return _render_formula(formula)


def _render_formula(formula=None, form=None):
    """La fórmula vacía, con lo guardado o con lo rechazado. Las filas de
    insumos viajan como lista de (insumo_id str, cantidad str) para que la
    plantilla tenga una sola forma de pintarlas."""
    if form is not None and hasattr(form, 'getlist'):
        filas = list(zip(form.getlist('item_insumo_id'), form.getlist('item_cantidad')))
        datos = {
            'producto_id': form.get('producto_id', ''),
            'nombre': form.get('nombre', ''),
            'base_kg': form.get('base_kg', ''),
            'activa': bool(form.get('activa')),
        }
    elif formula is not None:
        filas = [(str(i.insumo_id), str(i.cantidad)) for i in formula.insumos]
        datos = {
            'producto_id': str(formula.producto_id),
            'nombre': formula.nombre,
            'base_kg': str(formula.base_kg),
            'activa': formula.activa,
        }
    else:
        filas = []
        datos = {'producto_id': '', 'nombre': '', 'base_kg': '100', 'activa': True}
    return render_template(
        'produccion/formula_form.html',
        formula=formula, datos=datos, filas=filas,
        productos=_productos(), insumos=_insumos_para_formula(formula))
