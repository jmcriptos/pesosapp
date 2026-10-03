"""Las consultas de control: rendimiento por lote (con resumen por
producto) y mermas por causa. Todo se deriva de los lotes cerrados; nada
viene de un total guardado."""
from datetime import timezone
from decimal import Decimal

from sqlalchemy.orm import selectinload

from . import app_module, servicios
from .models import Formula, LoteConsumo, LoteProduccion, TIPOS_MERMA
from .servicios import CERO, _dec, _pct

db = app_module.db
Vendedor = app_module.Vendedor
DASHBOARD_TIMEZONE = getattr(app_module, 'DASHBOARD_TIMEZONE', None)


def _local(dt):
    """UTC naive → hora de Curazao, solo para mostrar."""
    if dt is None or DASHBOARD_TIMEZONE is None:
        return dt
    return dt.replace(tzinfo=timezone.utc).astimezone(DASHBOARD_TIMEZONE)


def _lotes(producto_id=None, desde=None, hasta=None, estados=('cerrada',)):
    """Los lotes del filtro con todo lo que el balance toca precargado:
    sin esto cada fila costaba cuatro consultas."""
    query = (LoteProduccion.query
             .options(selectinload(LoteProduccion.producto),
                      selectinload(LoteProduccion.formula),
                      selectinload(LoteProduccion.mermas),
                      selectinload(LoteProduccion.consumos)
                      .selectinload(LoteConsumo.insumo)))
    if estados:
        query = query.filter(LoteProduccion.estado.in_(estados))
    if producto_id:
        query = query.filter(LoteProduccion.producto_id == producto_id)
    if desde:
        query = query.filter(LoteProduccion.fecha_produccion >= desde)
    if hasta:
        query = query.filter(LoteProduccion.fecha_produccion <= hasta)
    return query.order_by(LoteProduccion.fecha_produccion.desc(),
                          LoteProduccion.id.desc()).all()


def fila_de_lote(lote):
    """Una fila de reporte: cabecera del lote más su balance."""
    b = servicios.balance(lote)
    b.update({
        'lote_id': lote.id,
        'codigo': lote.codigo,
        'lote': lote.lote,
        'producto_id': lote.producto_id,
        'producto': lote.producto.nombre if lote.producto else '—',
        'fecha': lote.fecha_produccion,
        'estado': lote.estado,
        'unidades': lote.unidades_producidas,
        'cajas': lote.cajas_producidas,
    })
    return b


def rendimiento(producto_id=None, desde=None, hasta=None):
    """Por lote cerrado: consumido, producido, merma y rendimiento. Y un
    resumen por producto con los totales PONDERADOS (suma de kilos, no
    promedio de porcentajes: un lote de 10 kg no pesa lo mismo que uno de
    400 en el rendimiento del mes)."""
    filas = [fila_de_lote(l) for l in _lotes(producto_id, desde, hasta)]

    acum = {}
    for f in filas:
        r = acum.setdefault(f['producto_id'], {
            'producto_id': f['producto_id'], 'producto': f['producto'],
            'lotes': 0, 'consumido': CERO, 'producido': CERO,
            'merma_identificada': CERO,
            'rend_min': None, 'rend_max': None, 'lotes_merma_alta': 0,
        })
        r['lotes'] += 1
        r['consumido'] += f['consumido']
        r['producido'] += f['producido']
        r['merma_identificada'] += f['merma_identificada']
        if f['merma_alta']:
            r['lotes_merma_alta'] += 1
        rp = f['rendimiento_pct']
        if rp is not None:
            r['rend_min'] = rp if r['rend_min'] is None else min(r['rend_min'], rp)
            r['rend_max'] = rp if r['rend_max'] is None else max(r['rend_max'], rp)

    resumen = []
    for r in sorted(acum.values(), key=lambda x: x['producto'].lower()):
        merma = r['consumido'] - r['producido']
        r['merma_total'] = merma
        r['merma_sin_identificar'] = merma - r['merma_identificada']
        r['merma_pct'] = _pct(merma, r['consumido'])
        r['rendimiento_pct'] = _pct(r['producido'], r['consumido'])
        resumen.append(r)
    return filas, resumen


def mermas(producto_id=None, desde=None, hasta=None):
    """Dónde se fueron los kilos, por causa y por producto, en el periodo.

    Devuelve `por_tipo` (todas las causas, incluidas las que sumaron 0,
    para que la pantalla muestre la lista completa y se vea qué no se
    está registrando), `por_producto` y los totales del periodo.
    """
    lotes = _lotes(producto_id, desde, hasta)
    consumido = producido = identificada = CERO
    por_tipo = {clave: CERO for clave, _ in TIPOS_MERMA}
    lotes_por_tipo = {clave: 0 for clave, _ in TIPOS_MERMA}
    por_producto = {}
    for lote in lotes:
        b = servicios.balance(lote)
        consumido += b['consumido']
        producido += b['producido']
        identificada += b['merma_identificada']
        vistos = set()
        for m in lote.mermas:
            por_tipo[m.tipo] = por_tipo.get(m.tipo, CERO) + _dec(m.cantidad)
            if m.tipo not in vistos:
                lotes_por_tipo[m.tipo] = lotes_por_tipo.get(m.tipo, 0) + 1
                vistos.add(m.tipo)
        p = por_producto.setdefault(lote.producto_id, {
            'producto_id': lote.producto_id,
            'producto': lote.producto.nombre if lote.producto else '—',
            'lotes': 0, 'consumido': CERO, 'producido': CERO,
            'identificada': CERO, 'tipos': {},
        })
        p['lotes'] += 1
        p['consumido'] += b['consumido']
        p['producido'] += b['producido']
        p['identificada'] += b['merma_identificada']
        for mt in b['mermas_por_tipo']:
            p['tipos'][mt['tipo']] = p['tipos'].get(mt['tipo'], CERO) + mt['cantidad']

    merma_total = consumido - producido
    etiquetas = dict(TIPOS_MERMA)
    filas_tipo = [{
        'tipo': clave, 'etiqueta': etiquetas.get(clave, clave),
        'cantidad': cantidad, 'lotes': lotes_por_tipo.get(clave, 0),
        'pct_consumido': _pct(cantidad, consumido),
        'pct_merma': _pct(cantidad, merma_total) if merma_total > CERO else None,
    } for clave, cantidad in sorted(por_tipo.items(), key=lambda kv: -kv[1])]

    filas_producto = []
    for p in sorted(por_producto.values(), key=lambda x: x['producto'].lower()):
        p['merma_total'] = p['consumido'] - p['producido']
        p['sin_identificar'] = p['merma_total'] - p['identificada']
        p['merma_pct'] = _pct(p['merma_total'], p['consumido'])
        p['tipos'] = [{'tipo': t, 'etiqueta': etiquetas.get(t, t), 'cantidad': c}
                      for t, c in sorted(p['tipos'].items(), key=lambda kv: -kv[1])]
        filas_producto.append(p)

    return {
        'lotes': len(lotes),
        'consumido': consumido,
        'producido': producido,
        'merma_total': merma_total,
        'merma_pct': _pct(merma_total, consumido),
        'identificada': identificada,
        'sin_identificar': merma_total - identificada,
        'pct_identificada': _pct(identificada, merma_total) if merma_total > CERO else None,
        'por_tipo': filas_tipo,
        'por_producto': filas_producto,
    }


def resumen_periodo(desde, hasta):
    """Los números del índice: lo cerrado entre dos fechas, ponderado."""
    filas = [fila_de_lote(l) for l in _lotes(None, desde, hasta)]
    consumido = sum((f['consumido'] for f in filas), CERO)
    producido = sum((f['producido'] for f in filas), CERO)
    identificada = sum((f['merma_identificada'] for f in filas), CERO)
    merma = consumido - producido
    return {
        'lotes': len(filas),
        'consumido': consumido,
        'producido': producido,
        'merma_total': merma,
        'merma_pct': _pct(merma, consumido),
        'rendimiento_pct': _pct(producido, consumido),
        'identificada': identificada,
        'sin_identificar': merma - identificada,
        'lotes_merma_alta': sum(1 for f in filas if f['merma_alta']),
    }


def nombre_vendedor(vendedor_id):
    if not vendedor_id:
        return None
    v = db.session.get(Vendedor, vendedor_id)
    return v.nombre_completo if v else None


def formulas_json():
    """{producto_id: {...}} con la fórmula activa de cada producto, para que
    el formulario calcule el teórico mientras se teclea el peso. Si hubiera
    más de una activa (no debería: `guardar_formula` lo impide), gana la
    más nueva, igual que `servicios.formula_para`."""
    salida = {}
    formulas = (Formula.query
                .filter(Formula.activa.is_(True))
                .options(selectinload(Formula.insumos))
                .order_by(Formula.id.asc()).all())
    for f in formulas:
        salida[str(f.producto_id)] = {
            'id': f.id,
            'nombre': f.nombre,
            'base_kg': str(_dec(f.base_kg)),
            'items': {str(i.insumo_id): str(_dec(i.cantidad)) for i in f.insumos},
        }
    return salida
