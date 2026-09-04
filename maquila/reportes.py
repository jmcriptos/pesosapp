"""Las cuatro consultas de auditoría.

Todo se deriva del ledger y de las tablas de producción: no hay ningún total
guardado que pueda mentir.
"""
from datetime import timezone
from decimal import Decimal

from sqlalchemy.orm import joinedload, selectinload

from . import app_module
from .models import (CorridaCaja, CorridaConsumo, CorridaConsumoOrigen,
                     CorridaProduccion, Ingrediente, MovimientoIngrediente,
                     RecepcionIngrediente, RecepcionLinea)
from . import servicios
from .servicios import _dec, saldos_por_linea, saldos_de_cliente, CERO

# NO reemplazar por `from app import db, Pedido, DetallePedido, CajaPesada,
# Vendedor`: revienta `python app.py` (el preview local) con un ImportError
# circular. Ver el comentario largo en maquila/__init__.py para el porqué.
# Este archivo no está en el camino de arranque hoy (routes.py no lo
# importa), pero lleva el mismo tratamiento para no dejar la misma trampa
# latente en cuanto una tarea futura lo enganche.
db = app_module.db
Pedido = app_module.Pedido
DetallePedido = app_module.DetallePedido
CajaPesada = app_module.CajaPesada
Vendedor = app_module.Vendedor
DASHBOARD_TIMEZONE = getattr(app_module, 'DASHBOARD_TIMEZONE', None)


def _local(dt):
    """UTC naive → hora de Curazao.

    Los movimientos se guardan en UTC naive. Mostrar `registrado_en` en crudo es
    el error que ya metió lecturas de temperatura en el bucket AM/PM equivocado:
    a las 8:00 locales le corresponden las 12:00 UTC.
    """
    if dt is None or DASHBOARD_TIMEZONE is None:
        return dt
    return dt.replace(tzinfo=timezone.utc).astimezone(DASHBOARD_TIMEZONE)


def saldos(cliente_id):
    """Saldo por ingrediente, con las líneas de recepción todavía abiertas."""
    filas = saldos_de_cliente(cliente_id)
    lineas = (db.session.query(RecepcionLinea, RecepcionIngrediente)
              .join(RecepcionIngrediente,
                    RecepcionIngrediente.id == RecepcionLinea.recepcion_id)
              .filter(RecepcionIngrediente.cliente_id == cliente_id,
                      RecepcionIngrediente.anulada_en.is_(None),
                      RecepcionLinea.anulada_en.is_(None))
              .order_by(RecepcionIngrediente.recibido_en.asc(),
                        RecepcionLinea.id.asc())
              .all())

    saldos_linea = saldos_por_linea(linea.id for linea, _ in lineas)
    abiertas = {}
    for linea, recepcion in lineas:
        saldo = saldos_linea[linea.id]
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
            # La unidad viaja con el dato: «Tripa natural» se cuenta en
            # unidades, y mostrarla en kg cambiaría un error de lectura por
            # uno de dato.
            'unidad': ingrediente.unidad,
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
    # Todo lo que el bucle de abajo toca por corrida viaja precargado: sin
    # esto cada fila del reporte costaba cinco consultas (cliente, producto,
    # cajas, consumos y el ingrediente de cada consumo).
    query = (CorridaProduccion.query
             .filter(CorridaProduccion.estado == 'cerrada')
             .options(selectinload(CorridaProduccion.cliente),
                      selectinload(CorridaProduccion.producto),
                      selectinload(CorridaProduccion.cajas),
                      selectinload(CorridaProduccion.consumos)
                      .selectinload(CorridaConsumo.ingrediente)))
    if cliente_id:
        query = query.filter(CorridaProduccion.cliente_id == cliente_id)
    if desde:
        query = query.filter(CorridaProduccion.fecha_produccion >= desde)
    if hasta:
        query = query.filter(CorridaProduccion.fecha_produccion <= hasta)

    filas = []
    for corrida in query.order_by(CorridaProduccion.fecha_produccion.desc()).all():
        # Solo lo denominado en peso: mezclar kg con unidades da un total que
        # no es nada. Ver servicios.consumo_en_peso.
        consumido = servicios.consumo_en_peso(corrida)
        otras_unidades = sorted({
            c.ingrediente.unidad for c in corrida.consumos
            if c.ingrediente and c.ingrediente.unidad != servicios.UNIDAD_PESO
        })
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
                'unidad': consumo.ingrediente.unidad,
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
            # Si la corrida consumió algo que no se pesa, la pantalla lo dice
            # en vez de esconderlo dentro de un total de kilos.
            'otras_unidades': otras_unidades,
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
        'unidad': ingrediente.unidad,
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
            'fecha_pedido': _local(pedido.fecha_pedido),
            'doc_number_qbo': pedido.doc_number_qbo,
            'invoice_id_qbo': pedido.invoice_id_qbo,
            'cajas': 0,
            'peso': CERO,
        })
        entrada['cajas'] += 1
        entrada['peso'] += _dec(pesada.peso)
    return list(por_pedido.values())


def _agregar_adelante(listas_por_corrida):
    """Combina el 'hacia_adelante' de varias corridas, sumando por pedido.

    Si dos corridas de la misma recepción pusieron cajas en el mismo pedido,
    sin esto el pedido saldría dos veces con `cajas`/`peso` parciales —
    ninguna fila con el total real.
    """
    por_pedido = {}
    for entradas in listas_por_corrida:
        for entrada in entradas:
            pid = entrada['pedido_id']
            if pid not in por_pedido:
                por_pedido[pid] = dict(entrada)
            else:
                por_pedido[pid]['cajas'] += entrada['cajas']
                por_pedido[pid]['peso'] += entrada['peso']
    return list(por_pedido.values())


def _desde_pedido(pedido):
    """Hacia atrás (recepciones vía corrida) y hacia adelante (el pedido mismo)."""
    atras, corridas, vistas = [], [], set()
    pesadas = [(detalle, pesada) for detalle in pedido.detalles
               for pesada in (detalle.cajas_pesadas or [])]
    # Una consulta para todas las cajas del pedido, no una por caja pesada.
    # `caja_pesada_id` es único, así que el dict no pisa nada.
    cajas_por_pesada = {}
    if pesadas:
        cajas_por_pesada = {
            caja.caja_pesada_id: caja
            for caja in (CorridaCaja.query
                         .filter(CorridaCaja.caja_pesada_id.in_(
                             [pesada.id for _, pesada in pesadas]))
                         .options(joinedload(CorridaCaja.corrida))
                         .all())}
    for detalle, pesada in pesadas:
        caja = cajas_por_pesada.get(pesada.id)
        if caja is None:
            atras.append({
                'codigo': '—', 'recibido_en': None, 'documento_cliente': None,
                'lote_cliente': pesada.lote,
                'ingrediente': None,
                'producto': detalle.producto.nombre if detalle.producto else '—',
                # Una caja pesada a mano es producto terminado: siempre kg.
                'unidad': 'kg',
                'cantidad': _dec(pesada.peso), 'automatico': None,
                'sin_origen': True,
            })
            continue
        if caja.corrida_id not in vistas:
            vistas.add(caja.corrida_id)
            corridas.append(caja.corrida)
            atras.extend(_atras_desde_corrida(caja.corrida))

    adelante = {
        'pedido_id': pedido.id, 'estado': pedido.estado,
        'fecha_pedido': _local(pedido.fecha_pedido),
        'doc_number_qbo': pedido.doc_number_qbo,
        'invoice_id_qbo': pedido.invoice_id_qbo,
        'cajas': sum(d.cajas_pesadas_count for d in pedido.detalles),
        'peso': sum((_dec(d.peso_real) for d in pedido.detalles), CERO),
    }
    return atras, corridas, adelante


# Tope de dígitos para tratar `termino` como un posible `Pedido.id`. Sin este
# tope, un término como '999999999999999999999' revienta con `OverflowError`
# (el int no entra en el C long que usa psycopg2 para bindear el parámetro) y
# en Postgres además deja la transacción abortada. 15 dígitos es más que de
# sobra para cualquier id real de esta app.
_MAX_DIGITOS_ID_TERMINO = 15


def trazar(termino):
    """Traza en ambos sentidos desde un lote, un código o un número de pedido.

    Acepta: lote de corrida, código de corrida (P-…), código de recepción (R-…),
    id de pedido o DocNumber de QuickBooks.

    `trazar` nunca elige en silencio: un lote solo es único por
    `(cliente_id, lote)`, no globalmente, y un término numérico puede calzar
    a la vez con un `Pedido.id` y con el `doc_number_qbo` de OTRO pedido. Si
    el término calza con más de una cosa, el resultado vuelve con
    `ambiguo: True` y TODOS los candidatos, en vez de adivinar cuál.
    """
    vacio = {'encontrado': False, 'tipo': None, 'termino': termino,
             'ambiguo': False, 'hacia_atras': [], 'hacia_adelante': [],
             'corridas': []}
    termino = (termino or '').strip()
    if not termino:
        return vacio

    corridas_candidatas = (CorridaProduccion.query
                            .filter((CorridaProduccion.lote == termino) |
                                    (CorridaProduccion.codigo == termino))
                            .order_by(CorridaProduccion.id.asc())
                            .all())
    if len(corridas_candidatas) == 1:
        corrida = corridas_candidatas[0]
        return {'encontrado': True, 'tipo': 'corrida', 'termino': termino,
                'ambiguo': False,
                'corridas': [corrida],
                'hacia_atras': _atras_desde_corrida(corrida),
                'hacia_adelante': _adelante_desde_corrida(corrida)}
    if len(corridas_candidatas) > 1:
        hacia_atras, hacia_adelante = [], []
        for c in corridas_candidatas:
            cliente_nombre = c.cliente.nombre if c.cliente else '—'
            for fila in _atras_desde_corrida(c):
                fila['corrida_id'] = c.id
                fila['cliente'] = cliente_nombre
                hacia_atras.append(fila)
            for fila in _adelante_desde_corrida(c):
                fila['corrida_id'] = c.id
                fila['cliente'] = cliente_nombre
                hacia_adelante.append(fila)
        return {'encontrado': True, 'tipo': 'corrida', 'termino': termino,
                'ambiguo': True,
                'corridas': corridas_candidatas,
                'hacia_atras': hacia_atras,
                'hacia_adelante': hacia_adelante}

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
        adelante = _agregar_adelante(_adelante_desde_corrida(c) for c in corridas)
        return {'encontrado': True, 'tipo': 'recepcion', 'termino': termino,
                'ambiguo': False,
                'corridas': corridas,
                'hacia_atras': [{
                    'codigo': recepcion.codigo,
                    'recibido_en': recepcion.recibido_en,
                    'documento_cliente': recepcion.documento_cliente,
                    'lote_cliente': l.lote_cliente,
                    'ingrediente': l.ingrediente.nombre,
                    'unidad': l.ingrediente.unidad,
                    'cantidad': _dec(l.peso_total),
                    'automatico': None,
                    'sin_origen': False,
                } for l in recepcion.lineas],
                'hacia_adelante': adelante}

    termino_es_id_valido = (termino.isdigit()
                            and len(termino) <= _MAX_DIGITOS_ID_TERMINO)
    pedido_por_id = db.session.get(Pedido, int(termino)) if termino_es_id_valido else None
    # `.all()`, no `.first()`: la numeración de QuickBooks es manual en n8n y
    # admite la carrera (decisión de JM), así que dos pedidos pueden compartir
    # DocNumber. Quedarse con el primero sería elegir en silencio.
    pedidos_por_docnum = (Pedido.query.filter_by(doc_number_qbo=termino)
                          .order_by(Pedido.id.asc()).all())

    candidatos, vistos = [], set()
    for p in (pedido_por_id, *pedidos_por_docnum):
        if p is not None and p.id not in vistos:
            vistos.add(p.id)
            candidatos.append(p)

    if not candidatos:
        return vacio

    if len(candidatos) == 1:
        atras, corridas, adelante = _desde_pedido(candidatos[0])
        return {'encontrado': True, 'tipo': 'pedido', 'termino': termino,
                'ambiguo': False,
                'corridas': corridas, 'hacia_atras': atras,
                'hacia_adelante': [adelante]}

    hacia_atras, hacia_adelante, corridas = [], [], []
    for p in candidatos:
        atras, c, adelante = _desde_pedido(p)
        for fila in atras:
            fila['pedido_id'] = p.id
        hacia_atras.extend(atras)
        corridas.extend(c)
        hacia_adelante.append(adelante)
    return {'encontrado': True, 'tipo': 'pedido', 'termino': termino,
            'ambiguo': True,
            'corridas': corridas, 'hacia_atras': hacia_atras,
            'hacia_adelante': hacia_adelante}
