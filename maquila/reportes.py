"""Las cuatro consultas de auditoría.

Todo se deriva del ledger y de las tablas de producción: no hay ningún total
guardado que pueda mentir.
"""
from decimal import Decimal

from app import db, Pedido, DetallePedido, CajaPesada, Vendedor
from .models import (CorridaCaja, CorridaConsumo, CorridaConsumoOrigen,
                     CorridaProduccion, Ingrediente, MovimientoIngrediente,
                     RecepcionIngrediente, RecepcionLinea)
from .servicios import _dec, saldo_de_linea, saldos_de_cliente, CERO

try:
    from app import DASHBOARD_TIMEZONE
except ImportError:  # pragma: no cover
    DASHBOARD_TIMEZONE = None


def _local(dt):
    """UTC naive → hora de Curazao.

    Los movimientos se guardan en UTC naive. Mostrar `registrado_en` en crudo es
    el error que ya metió lecturas de temperatura en el bucket AM/PM equivocado:
    a las 8:00 locales le corresponden las 12:00 UTC.
    """
    if dt is None or DASHBOARD_TIMEZONE is None:
        return dt
    from datetime import timezone
    return dt.replace(tzinfo=timezone.utc).astimezone(DASHBOARD_TIMEZONE)


def saldos(cliente_id):
    """Saldo por ingrediente, con las líneas de recepción todavía abiertas."""
    filas = saldos_de_cliente(cliente_id)
    lineas = (db.session.query(RecepcionLinea, RecepcionIngrediente)
              .join(RecepcionIngrediente,
                    RecepcionIngrediente.id == RecepcionLinea.recepcion_id)
              .filter(RecepcionIngrediente.cliente_id == cliente_id,
                      RecepcionIngrediente.anulada_en.is_(None))
              .order_by(RecepcionIngrediente.recibido_en.asc())
              .all())

    abiertas = {}
    for linea, recepcion in lineas:
        saldo = saldo_de_linea(linea.id)
        if saldo <= CERO:
            continue
        abiertas.setdefault(linea.ingrediente_id, []).append({
            'codigo': recepcion.codigo,
            'recibido_en': recepcion.recibido_en,
            'lote_cliente': linea.lote_cliente,
            'saldo': saldo,
        })

    for fila in filas:
        fila['lineas_abiertas'] = abiertas.get(fila['ingrediente_id'], [])
    return filas


def kardex(cliente_id, ingrediente_id=None, desde=None, hasta=None):
    """Movimientos en orden cronológico, con el saldo acumulado."""
    query = (db.session.query(MovimientoIngrediente, Ingrediente, Vendedor)
             .join(Ingrediente, Ingrediente.id == MovimientoIngrediente.ingrediente_id)
             .outerjoin(Vendedor, Vendedor.id == MovimientoIngrediente.registrado_por)
             .filter(MovimientoIngrediente.cliente_id == cliente_id))
    if ingrediente_id:
        query = query.filter(MovimientoIngrediente.ingrediente_id == ingrediente_id)
    if desde:
        query = query.filter(MovimientoIngrediente.registrado_en >= desde)
    if hasta:
        query = query.filter(MovimientoIngrediente.registrado_en <= hasta)

    movimientos = query.order_by(MovimientoIngrediente.registrado_en.asc(),
                                 MovimientoIngrediente.id.asc()).all()

    acumulado = {}
    filas = []
    for mov, ingrediente, vendedor in movimientos:
        clave = mov.ingrediente_id
        acumulado[clave] = acumulado.get(clave, CERO) + _dec(mov.cantidad)
        filas.append({
            'id': mov.id,
            'fecha': _local(mov.registrado_en),
            'tipo': mov.tipo,
            'ingrediente_id': mov.ingrediente_id,
            'ingrediente': ingrediente.nombre,
            'cantidad': _dec(mov.cantidad),
            'saldo_acumulado': acumulado[clave],
            'origen': f'{mov.origen_tipo}:{mov.origen_id}' if mov.origen_id else mov.origen_tipo,
            'origen_tipo': mov.origen_tipo,
            'origen_id': mov.origen_id,
            'responsable': vendedor.nombre_completo if vendedor else '—',
            'motivo': mov.motivo,
        })
    return filas


def rendimiento(cliente_id=None, desde=None, hasta=None):
    """Por corrida: cuánto entró, cuánto salió, cuánta merma y qué varianza."""
    query = CorridaProduccion.query.filter(CorridaProduccion.estado == 'cerrada')
    if cliente_id:
        query = query.filter(CorridaProduccion.cliente_id == cliente_id)
    if desde:
        query = query.filter(CorridaProduccion.fecha_produccion >= desde)
    if hasta:
        query = query.filter(CorridaProduccion.fecha_produccion <= hasta)

    filas = []
    for corrida in query.order_by(CorridaProduccion.fecha_produccion.desc()).all():
        consumido = sum((_dec(c.cantidad_real) for c in corrida.consumos), CERO)
        producido = corrida.peso_producido
        merma = consumido - producido
        merma_pct = ((merma / consumido) * 100).quantize(Decimal('0.1')) \
            if consumido > CERO else CERO

        varianzas = []
        for consumo in corrida.consumos:
            teorica = _dec(consumo.cantidad_teorica)
            real = _dec(consumo.cantidad_real)
            varianzas.append({
                'ingrediente': consumo.ingrediente.nombre,
                'teorica': teorica,
                'real': real,
                'diferencia': real - teorica,
                'pct': (((real - teorica) / teorica) * 100).quantize(Decimal('0.1'))
                       if teorica > CERO else None,
            })

        filas.append({
            'corrida_id': corrida.id,
            'corrida': corrida.codigo,
            'lote': corrida.lote,
            'cliente': corrida.cliente.nombre if corrida.cliente else '—',
            'producto': corrida.producto.nombre if corrida.producto else '—',
            'fecha': corrida.fecha_produccion,
            'consumido': consumido,
            'producido': producido,
            'merma': merma,
            'merma_pct': merma_pct,
            'varianzas': varianzas,
        })
    return filas


def _atras_desde_corrida(corrida):
    """Las recepciones que alimentaron esta corrida."""
    origenes = (db.session.query(CorridaConsumoOrigen, RecepcionLinea,
                                 RecepcionIngrediente, Ingrediente)
                .join(CorridaConsumo,
                      CorridaConsumo.id == CorridaConsumoOrigen.corrida_consumo_id)
                .join(RecepcionLinea,
                      RecepcionLinea.id == CorridaConsumoOrigen.recepcion_linea_id)
                .join(RecepcionIngrediente,
                      RecepcionIngrediente.id == RecepcionLinea.recepcion_id)
                .join(Ingrediente, Ingrediente.id == RecepcionLinea.ingrediente_id)
                .filter(CorridaConsumo.corrida_id == corrida.id)
                .all())
    return [{
        'codigo': recepcion.codigo,
        'recibido_en': recepcion.recibido_en,
        'documento_cliente': recepcion.documento_cliente,
        'lote_cliente': linea.lote_cliente,
        'ingrediente': ingrediente.nombre,
        'cantidad': _dec(origen.cantidad),
        'automatico': origen.automatico,
        'sin_origen': False,
    } for origen, linea, recepcion, ingrediente in origenes]


def _adelante_desde_corrida(corrida):
    """Los pedidos y facturas en que salieron las cajas de esta corrida."""
    filas = (db.session.query(CorridaCaja, CajaPesada, DetallePedido, Pedido)
             .join(CajaPesada, CajaPesada.id == CorridaCaja.caja_pesada_id)
             .join(DetallePedido, DetallePedido.id == CajaPesada.detalle_pedido_id)
             .join(Pedido, Pedido.id == DetallePedido.pedido_id)
             .filter(CorridaCaja.corrida_id == corrida.id)
             .all())
    por_pedido = {}
    for caja, pesada, _detalle, pedido in filas:
        entrada = por_pedido.setdefault(pedido.id, {
            'pedido_id': pedido.id,
            'estado': pedido.estado,
            'fecha_pedido': pedido.fecha_pedido,
            'doc_number_qbo': pedido.doc_number_qbo,
            'invoice_id_qbo': pedido.invoice_id_qbo,
            'cajas': 0,
            'peso': CERO,
        })
        entrada['cajas'] += 1
        entrada['peso'] += _dec(pesada.peso)
    return list(por_pedido.values())


def trazar(termino):
    """Traza en ambos sentidos desde un lote, un código o un número de pedido.

    Acepta: lote de corrida, código de corrida (P-…), código de recepción (R-…),
    id de pedido o DocNumber de QuickBooks.
    """
    vacio = {'encontrado': False, 'tipo': None, 'termino': termino,
             'hacia_atras': [], 'hacia_adelante': [], 'corridas': []}
    termino = (termino or '').strip()
    if not termino:
        return vacio

    corrida = (CorridaProduccion.query
               .filter((CorridaProduccion.lote == termino) |
                       (CorridaProduccion.codigo == termino))
               .first())
    if corrida:
        return {'encontrado': True, 'tipo': 'corrida', 'termino': termino,
                'corridas': [corrida],
                'hacia_atras': _atras_desde_corrida(corrida),
                'hacia_adelante': _adelante_desde_corrida(corrida)}

    recepcion = RecepcionIngrediente.query.filter_by(codigo=termino).first()
    if recepcion:
        ids = [l.id for l in recepcion.lineas]
        corridas = (CorridaProduccion.query
                    .join(CorridaConsumo,
                          CorridaConsumo.corrida_id == CorridaProduccion.id)
                    .join(CorridaConsumoOrigen,
                          CorridaConsumoOrigen.corrida_consumo_id == CorridaConsumo.id)
                    .filter(CorridaConsumoOrigen.recepcion_linea_id.in_(ids))
                    .distinct().all()) if ids else []
        adelante = []
        for c in corridas:
            adelante.extend(_adelante_desde_corrida(c))
        return {'encontrado': True, 'tipo': 'recepcion', 'termino': termino,
                'corridas': corridas,
                'hacia_atras': [{
                    'codigo': recepcion.codigo,
                    'recibido_en': recepcion.recibido_en,
                    'documento_cliente': recepcion.documento_cliente,
                    'lote_cliente': l.lote_cliente,
                    'ingrediente': l.ingrediente.nombre,
                    'cantidad': _dec(l.peso_total),
                    'automatico': None,
                    'sin_origen': False,
                } for l in recepcion.lineas],
                'hacia_adelante': adelante}

    pedido = None
    if termino.isdigit():
        pedido = db.session.get(Pedido, int(termino))
    if pedido is None:
        pedido = Pedido.query.filter_by(doc_number_qbo=termino).first()
    if pedido is None:
        return vacio

    atras, corridas, vistas = [], [], set()
    for detalle in pedido.detalles:
        for pesada in (detalle.cajas_pesadas or []):
            caja = CorridaCaja.query.filter_by(caja_pesada_id=pesada.id).first()
            if caja is None:
                atras.append({
                    'codigo': '—', 'recibido_en': None, 'documento_cliente': None,
                    'lote_cliente': pesada.lote,
                    'ingrediente': detalle.producto.nombre if detalle.producto else '—',
                    'cantidad': _dec(pesada.peso), 'automatico': None,
                    'sin_origen': True,
                })
                continue
            if caja.corrida_id not in vistas:
                vistas.add(caja.corrida_id)
                corridas.append(caja.corrida)
                atras.extend(_atras_desde_corrida(caja.corrida))

    return {'encontrado': True, 'tipo': 'pedido', 'termino': termino,
            'corridas': corridas, 'hacia_atras': atras,
            'hacia_adelante': [{
                'pedido_id': pedido.id, 'estado': pedido.estado,
                'fecha_pedido': pedido.fecha_pedido,
                'doc_number_qbo': pedido.doc_number_qbo,
                'invoice_id_qbo': pedido.invoice_id_qbo,
                'cajas': sum(d.cajas_pesadas_count for d in pedido.detalles),
                'peso': sum((_dec(d.peso_real) for d in pedido.detalles), CERO),
            }]}
